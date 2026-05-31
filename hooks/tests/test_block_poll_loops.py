"""Tests for hooks/block_poll_loops.py."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "block_poll_loops.py"

# The observed real-world antipattern: poll a task .output file for byte stability.
OBSERVED = (
    'f=/private/tmp/claude-501/x/tasks/bq1qn3o2e.output; prev=-1; stable=0; '
    'while true; do cur=$(wc -c < "$f" 2>/dev/null || echo 0); '
    'if [ "$cur" = "$prev" ]; then stable=$((stable+1)); else stable=0; fi; '
    'if [ "$stable" -ge 4 ]; then echo "output stable at $cur bytes"; break; fi; '
    'prev=$cur; sleep 5; done'
)


def run_hook(cmd: str | None) -> subprocess.CompletedProcess[str]:
    if cmd is None:
        payload = ""
    else:
        payload = json.dumps({"tool_input": {"command": cmd}})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=5,
    )


class TestBlocks(unittest.TestCase):
    def test_blocks_observed_byte_stability_loop(self) -> None:
        r = run_hook(OBSERVED)
        self.assertEqual(r.returncode, 2)
        self.assertIn("TaskOutput", r.stderr)

    def test_blocks_size_poll_with_break(self) -> None:
        # A size poll that breaks on stability is the real antipattern.
        cmd = 'while true; do c=$(wc -c < f); [ "$c" = "$p" ] && break; p=$c; sleep 5; done'
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)

    def test_blocks_until_sleep_stat(self) -> None:
        # `until <file-state>` makes the loop a completion poll.
        r = run_hook('until [ -s f ]; do stat f; sleep 1; done')
        self.assertEqual(r.returncode, 2)

    def test_blocks_output_file_break(self) -> None:
        r = run_hook('while :; do test -s run.output && break; sleep 1; done')
        self.assertEqual(r.returncode, 2)

    def test_blocks_kill0_pgrep_liveness_loop(self) -> None:
        # Process-liveness wait: no size check, no .output path - the loop runs
        # while a process is alive, which is itself a completion wait.
        cmd = (
            'while kill -0 $(pgrep -f sonnet-run.sh | head -1) 2>/dev/null; '
            'do sleep 5; done; echo done'
        )
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("TaskOutput", r.stderr)

    def test_blocks_until_pgrep_loop(self) -> None:
        r = run_hook('until [ -z "$(pgrep -f codex-run.sh)" ]; do sleep 3; done')
        self.assertEqual(r.returncode, 2)

    def test_blocks_while_condition_output_poll(self) -> None:
        # Completion test in the `while` header (no `break`) is still a task wait.
        r = run_hook('while [ ! -s job.output ]; do sleep 1; done')
        self.assertEqual(r.returncode, 2)

    def test_blocks_while_condition_existence_poll(self) -> None:
        r = run_hook('while ! test -f /tmp/x/tasks/job; do sleep 3; done')
        self.assertEqual(r.returncode, 2)

    def test_blocks_while_condition_size_threshold_poll(self) -> None:
        cmd = 'while [ $(wc -c < /tmp/x/tasks/job.output) -lt 1000 ]; do sleep 5; done'
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)


class TestAllows(unittest.TestCase):
    def test_allows_metric_loop_without_completion_exit(self) -> None:
        # A bare size loop that never breaks on the polled value is a live
        # monitor, not a task-completion wait.
        r = run_hook('while true; do wc -c < out; sleep 2; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_disk_usage_monitor(self) -> None:
        # The Monitor tool's own documented pattern.
        r = run_hook('while true; do du -sh /var/log; sleep 60; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_log_growth_monitor(self) -> None:
        r = run_hook('while true; do wc -l access.log; sleep 10; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_mtime_watch_monitor(self) -> None:
        r = run_hook('while true; do stat -c%Y src.c; sleep 1; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_bracket_one_monitor(self) -> None:
        # `while [ 1 ]` is an infinite monitor, same as `while true`.
        r = run_hook('while [ 1 ]; do du -sh /var/log; sleep 60; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_arith_true_monitor(self) -> None:
        r = run_hook('while (( 1 )); do stat -c%Y src.c; sleep 1; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_while_sleep_paced_monitor(self) -> None:
        r = run_hook('while sleep 5; do wc -l access.log; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_tasks_path_loop_without_exit(self) -> None:
        r = run_hook('while true; do cat /tmp/x/tasks/abc; sleep 3; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_legit_monitor_api_poll(self) -> None:
        r = run_hook('while true; do gh api repos/o/r/issues/1; sleep 30; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_until_grep_ready(self) -> None:
        r = run_hook('until grep -q "Ready" dev.log; do sleep 0.5; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_wc_without_loop(self) -> None:
        r = run_hook('wc -c < some.output')
        self.assertEqual(r.returncode, 0)

    def test_allows_tail_f_of_task_output(self) -> None:
        r = run_hook('tail -f /tmp/x/tasks/abc.output')
        self.assertEqual(r.returncode, 0)

    def test_allows_loop_without_sleep(self) -> None:
        r = run_hook('while read l; do wc -c <<< "$l"; done < f')
        self.assertEqual(r.returncode, 0)

    def test_allows_oneshot_kill0_liveness_check(self) -> None:
        r = run_hook('kill -0 999 && echo alive')
        self.assertEqual(r.returncode, 0)

    def test_allows_pgrep_without_loop(self) -> None:
        r = run_hook('pgrep -fl sonnet-run.sh')
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_command(self) -> None:
        r = run_hook("")
        self.assertEqual(r.returncode, 0)

    def test_allows_missing_command_field(self) -> None:
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"tool_input": {}}),
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_stdin(self) -> None:
        r = run_hook(None)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
