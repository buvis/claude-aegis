"""Tests for hooks/prefer_tools.py."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "prefer_tools.py"


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
    def test_blocks_bare_grep(self) -> None:
        # Routes to the live alternatives, not the unregistered Grep tool.
        r = run_hook("grep -r foo .")
        self.assertEqual(r.returncode, 2)
        self.assertIn("`rg`", r.stderr)
        self.assertIn("Explore", r.stderr)

    def test_blocks_bare_find(self) -> None:
        # Routes to the live alternatives, not the unregistered Glob tool.
        r = run_hook("find . -name '*.py'")
        self.assertEqual(r.returncode, 2)
        self.assertIn("`rg --files`", r.stderr)
        self.assertIn("Explore", r.stderr)

    def test_blocks_bare_cat(self) -> None:
        r = run_hook("cat file")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Read", r.stderr)

    def test_blocks_head(self) -> None:
        r = run_hook("head -n5 file")
        self.assertEqual(r.returncode, 2)

    def test_blocks_tail(self) -> None:
        r = run_hook("tail file")
        self.assertEqual(r.returncode, 2)

    def test_piped_tail_message_offers_applicable_fix(self) -> None:
        # `uv sync 2>&1 | tail -20` has no file for Read to open; the message
        # must route to running the command bare or redirecting to a file.
        r = run_hook("uv sync 2>&1 | tail -20")
        self.assertEqual(r.returncode, 2)
        self.assertIn("run the command bare", r.stderr)
        self.assertIn("redirect to a file", r.stderr)

    def test_blocks_grep_piped_to_head(self) -> None:
        # The documented pipe case: blocks on the first denied binary.
        r = run_hook("grep foo f | head")
        self.assertEqual(r.returncode, 2)
        self.assertIn("`rg`", r.stderr)

    def test_blocks_cat_before_jq(self) -> None:
        r = run_hook("cat f | jq '.'")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Read", r.stderr)

    def test_blocks_cat_in_chain(self) -> None:
        r = run_hook("ls && cat f")
        self.assertEqual(r.returncode, 2)

    def test_blocks_cat_in_subshell(self) -> None:
        r = run_hook("x=$(cat f)")
        self.assertEqual(r.returncode, 2)

    def test_blocks_xargs_grep(self) -> None:
        # xargs is the one documented wrapper; its argument is the real command.
        r = run_hook("xargs grep foo")
        self.assertEqual(r.returncode, 2)
        self.assertIn("`rg`", r.stderr)

    def test_blocks_xargs_with_flag_then_cat(self) -> None:
        r = run_hook("xargs -r cat")
        self.assertEqual(r.returncode, 2)

    def test_blocks_sudo_wrapped_cat(self) -> None:
        # `sudo cat/grep/...` to inspect root-owned files is a real shortcut.
        r = run_hook("sudo cat /etc/hosts")
        self.assertEqual(r.returncode, 2)

    def test_blocks_env_assignment_prefix(self) -> None:
        # `LC_ALL=C grep` for deterministic output is common; the assignment
        # prefix must not shadow the denied binary.
        r = run_hook("LC_ALL=C grep foo file")
        self.assertEqual(r.returncode, 2)

    def test_blocks_time_wrapped_grep(self) -> None:
        r = run_hook("time grep -r foo .")
        self.assertEqual(r.returncode, 2)


class TestAllows(unittest.TestCase):
    def test_allows_rg(self) -> None:
        # The whole point: rg is the sanctioned alternative.
        r = run_hook("rg foo")
        self.assertEqual(r.returncode, 0)

    def test_allows_jq(self) -> None:
        # The replacement for `cat file | jq` must not itself be blocked.
        r = run_hook("jq '.x' file")
        self.assertEqual(r.returncode, 0)

    def test_allows_denied_word_as_flag_value(self) -> None:
        # `cat`/`grep` appearing as an argument, not a command.
        r = run_hook("git log --grep=cat")
        self.assertEqual(r.returncode, 0)

    def test_allows_denied_word_as_redirect_target(self) -> None:
        r = run_hook("echo hi > cat")
        self.assertEqual(r.returncode, 0)

    def test_allows_denied_word_inside_quoted_message(self) -> None:
        # Quote-aware: a pipe described in a commit message is not a pipeline.
        r = run_hook("git commit -m 'see a | grep b'")
        self.assertEqual(r.returncode, 0)

    def test_allows_denied_word_inside_double_quotes(self) -> None:
        r = run_hook('echo "use cat then grep"')
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

    def test_allows_invalid_json(self) -> None:
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not json",
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
