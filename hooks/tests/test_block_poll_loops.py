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

    def test_blocks_while_sleep_wc_c(self) -> None:
        r = run_hook('while true; do wc -c < out; sleep 2; done')
        self.assertEqual(r.returncode, 2)

    def test_blocks_until_sleep_stat(self) -> None:
        r = run_hook('until [ -s f ]; do stat f; sleep 1; done')
        self.assertEqual(r.returncode, 2)

    def test_blocks_while_sleep_tasks_path(self) -> None:
        r = run_hook('while true; do cat /tmp/x/tasks/abc; sleep 3; done')
        self.assertEqual(r.returncode, 2)

    def test_blocks_while_sleep_output_file(self) -> None:
        r = run_hook('while :; do test -s run.output && break; sleep 1; done')
        self.assertEqual(r.returncode, 2)

    def test_blocks_multiline_loop(self) -> None:
        r = run_hook('while true\ndo\n  wc -l f\n  sleep 5\ndone')
        self.assertEqual(r.returncode, 2)

    def test_blocks_kill0_pgrep_liveness_loop(self) -> None:
        # The observed real-world antipattern: poll process liveness, no size
        # check and no .output/tasks path - the size-poll branch alone misses it.
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


class TestAllows(unittest.TestCase):
    def test_allows_legit_monitor_api_poll(self) -> None:
        # Monitor's documented pattern: poll a remote API, no size check.
        r = run_hook('while true; do gh api repos/o/r/issues/1; sleep 30; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_until_grep_ready(self) -> None:
        r = run_hook('until grep -q "Ready" dev.log; do sleep 0.5; done')
        self.assertEqual(r.returncode, 0)

    def test_allows_wc_without_loop(self) -> None:
        r = run_hook('wc -c < some.output')
        self.assertEqual(r.returncode, 0)

    def test_allows_output_reference_without_loop(self) -> None:
        r = run_hook('echo run.output')
        self.assertEqual(r.returncode, 0)

    def test_allows_tail_f_of_task_output(self) -> None:
        r = run_hook('tail -f /tmp/x/tasks/abc.output')
        self.assertEqual(r.returncode, 0)

    def test_allows_loop_without_sleep(self) -> None:
        r = run_hook('while read l; do wc -c <<< "$l"; done < f')
        self.assertEqual(r.returncode, 0)

    def test_allows_oneshot_kill0_liveness_check(self) -> None:
        # A bare liveness probe with no loop is not the antipattern.
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
