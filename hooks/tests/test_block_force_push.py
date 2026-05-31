"""Tests for hooks/block_force_push.py."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "block_force_push.py"


def run_hook(cmd: str) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_input": {"command": cmd}})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=5,
    )


class TestBlocks(unittest.TestCase):
    def test_blocks_long_force(self) -> None:
        r = run_hook("git push --force")
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("force push", r.stderr)

    def test_blocks_short_force(self) -> None:
        r = run_hook("git push -f origin master")
        self.assertEqual(r.returncode, 2)

    def test_blocks_force_with_lease(self) -> None:
        r = run_hook("git push --force-with-lease")
        self.assertEqual(r.returncode, 2)

    def test_blocks_force_with_lease_value(self) -> None:
        r = run_hook("git push --force-with-lease=origin/master")
        self.assertEqual(r.returncode, 2)

    def test_blocks_bundled_short_flags(self) -> None:
        r = run_hook("git push -fu origin master")
        self.assertEqual(r.returncode, 2)

    def test_blocks_plus_refspec(self) -> None:
        r = run_hook("git push origin +master")
        self.assertEqual(r.returncode, 2)

    def test_blocks_plus_refspec_with_colon(self) -> None:
        r = run_hook("git push origin +HEAD:master")
        self.assertEqual(r.returncode, 2)

    def test_blocks_with_git_level_option(self) -> None:
        r = run_hook("git -c foo=bar push --force")
        self.assertEqual(r.returncode, 2)

    def test_blocks_bare_repo_form(self) -> None:
        r = run_hook("git --git-dir=/x --work-tree=/y push --force")
        self.assertEqual(r.returncode, 2)

    def test_blocks_when_chained(self) -> None:
        r = run_hook("git add -A && git push --force")
        self.assertEqual(r.returncode, 2)

    def test_blocks_git_invoked_by_path(self) -> None:
        # An absolute/relative path to git must not slip past the token check.
        r = run_hook("/usr/bin/git push --force origin master")
        self.assertEqual(r.returncode, 2)

    def test_block_message_points_to_bang_prefix(self) -> None:
        r = run_hook("git push --force")
        self.assertIn("!", r.stderr)


class TestAllows(unittest.TestCase):
    def test_allows_plain_push(self) -> None:
        r = run_hook("git push origin master")
        self.assertEqual(r.returncode, 0)

    def test_allows_bare_push(self) -> None:
        r = run_hook("git push")
        self.assertEqual(r.returncode, 0)

    def test_allows_set_upstream(self) -> None:
        # -u must not be mistaken for a force flag.
        r = run_hook("git push -u origin master")
        self.assertEqual(r.returncode, 0)

    def test_allows_force_inside_commit_message(self) -> None:
        # The force flag lives inside a quoted message, not as a bare token.
        r = run_hook('git commit -m "feat: guard git push --force"')
        self.assertEqual(r.returncode, 0)

    def test_allows_force_fetch(self) -> None:
        # Force applies to fetch, not push - no remote history is rewritten.
        r = run_hook("git fetch --force")
        self.assertEqual(r.returncode, 0)

    def test_allows_force_in_separate_segment(self) -> None:
        r = run_hook("git push origin master && echo --force")
        self.assertEqual(r.returncode, 0)

    def test_allows_unrelated_command(self) -> None:
        r = run_hook("ls -la")
        self.assertEqual(r.returncode, 0)

    def test_allows_trailing_comment_mentioning_force(self) -> None:
        # A shell comment is stripped; the real command is a plain push.
        r = run_hook("git push origin master # use --force only if rejected")
        self.assertEqual(r.returncode, 0)

    def test_allows_empty_stdin(self) -> None:
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input="",
            capture_output=True,
            text=True,
            timeout=5,
        )
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


if __name__ == "__main__":
    unittest.main()
