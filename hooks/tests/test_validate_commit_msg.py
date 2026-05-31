"""Tests for hooks/validate_commit_msg.py."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "validate_commit_msg.py"


def run_hook(cmd: str) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_input": {"command": cmd}})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=5,
    )


class TestAllows(unittest.TestCase):
    def test_allows_valid_with_scope(self) -> None:
        r = run_hook('git commit -m "fix(scope): some change"')
        self.assertEqual(r.returncode, 0)

    def test_allows_valid_no_scope(self) -> None:
        r = run_hook('git commit -m "feat: add new thing"')
        self.assertEqual(r.returncode, 0)

    def test_allows_breaking_marker(self) -> None:
        r = run_hook('git commit -m "fix!: breaking change"')
        self.assertEqual(r.returncode, 0)

    def test_allows_breaking_with_scope(self) -> None:
        r = run_hook('git commit -m "feat(api)!: drop legacy endpoint"')
        self.assertEqual(r.returncode, 0)

    def test_allows_single_quoted(self) -> None:
        r = run_hook("git commit -m 'docs: clarify readme'")
        self.assertEqual(r.returncode, 0)

    def test_allows_amend_without_m(self) -> None:
        r = run_hook("git commit --amend")
        self.assertEqual(r.returncode, 0)

    def test_allows_non_git_commit(self) -> None:
        r = run_hook("git status")
        self.assertEqual(r.returncode, 0)

    def test_allows_unrelated_command(self) -> None:
        r = run_hook("ls -la")
        self.assertEqual(r.returncode, 0)

    def test_allows_commit_from_file(self) -> None:
        # -F supplies the message from a file; nothing to parse, so allow.
        r = run_hook("git commit -F /tmp/msg.txt")
        self.assertEqual(r.returncode, 0)

    def test_allows_unquoted_space_separated_m(self) -> None:
        # Malformed shell (git rejects it); a space-separated bare token is not
        # captured as the message, so the hook does not misleadingly block it.
        r = run_hook("git commit -m fix: ok")
        self.assertEqual(r.returncode, 0)

    def test_allows_message_containing_cat_substring_when_valid(self) -> None:
        # A literal "cat <<" inside a message (no $()) must NOT be treated as a
        # heredoc construction.
        r = run_hook('git commit -m "fix: cat << is fine in body"')
        self.assertEqual(r.returncode, 0)

    def test_allows_subject_mentioning_boilerplate_term(self) -> None:
        # Line-anchored: a subject that merely names a trailer term is fine;
        # only a trailer at the start of its own line is boilerplate.
        r = run_hook('git commit -m "fix: document the generated-by trailer rule"')
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


class TestBlocks(unittest.TestCase):
    def test_blocks_capitalized_subject(self) -> None:
        r = run_hook('git commit -m "Fix typo"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("conventional commit format", r.stderr)

    def test_validates_message_containing_cat_substring(self) -> None:
        # Literal "cat <<" (no $()) still goes through conventional validation.
        r = run_hook('git commit -m "Fix: cat << broken"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("conventional commit format", r.stderr)

    def test_blocks_trailing_period(self) -> None:
        r = run_hook('git commit -m "fix: ends with period."')
        self.assertEqual(r.returncode, 2)
        self.assertIn("must not end with a period", r.stderr)

    def test_blocks_unknown_type(self) -> None:
        r = run_hook('git commit -m "wrong-type: foo"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("conventional commit format", r.stderr)

    def test_blocks_signed_off_by(self) -> None:
        cmd = 'git commit -m "fix: something\n\nSigned-Off-By: someone"'
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("forbidden boilerplate", r.stderr)

    def test_blocks_generated_with(self) -> None:
        cmd = 'git commit -m "fix: thing\n\nGenerated with Some-Tool"'
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("forbidden boilerplate", r.stderr)

    def test_blocks_co_authored_in_inline_message(self) -> None:
        cmd = 'git commit -m "fix: thing\n\nCo-authored-by: alice"'
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)

    def test_blocks_co_authored_by_in_second_m_flag(self) -> None:
        # Idiomatic multi -m (subject + trailer); the second -m must be checked.
        r = run_hook('git commit -m "fix: ok" -m "Co-Authored-By: someone <s@x.com>"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("forbidden boilerplate", r.stderr)

    def test_blocks_long_message_flag(self) -> None:
        r = run_hook('git commit --message="Co-Authored-By: bob"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("forbidden boilerplate", r.stderr)

    def test_blocks_emoji_prefixed_generated_footer(self) -> None:
        # The default Claude Code footer; the emoji prefix must not shield it.
        r = run_hook('git commit -m "feat: add thing\n\n🤖 Generated with Claude Code"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("forbidden boilerplate", r.stderr)

    def test_blocks_no_space_after_m(self) -> None:
        r = run_hook('git commit -m"Bad subject"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("conventional commit format", r.stderr)

    def test_blocks_grouped_short_flags(self) -> None:
        # -am is the common "stage all + message" form.
        r = run_hook('git commit -am "Bad subject"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("conventional commit format", r.stderr)

    def test_blocks_env_prefixed_commit(self) -> None:
        r = run_hook('GIT_EDITOR=true git commit -m "Bad capital"')
        self.assertEqual(r.returncode, 2)
        self.assertIn("conventional commit format", r.stderr)

    def test_blocks_config_prefixed_commit(self) -> None:
        r = run_hook('git -c core.editor=true commit -m "Bad capital"')
        self.assertEqual(r.returncode, 2)


class TestHeredoc(unittest.TestCase):
    """Heredoc commit construction is forbidden outright (policy: plain -m)."""

    def test_blocks_heredoc_valid_message(self) -> None:
        cmd = "git commit -m \"$(cat <<'EOF'\nfix: handle edge case\nEOF\n)\""
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("heredoc", r.stderr)

    def test_blocks_heredoc_unquoted_eof(self) -> None:
        cmd = "git commit -m \"$(cat <<EOF\nfeat: new thing\nEOF\n)\""
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("heredoc", r.stderr)

    def test_blocks_heredoc_non_eof_delimiter(self) -> None:
        # Previously a silent total-validation bypass; now blocked wholesale.
        cmd = "git commit -m \"$(cat <<COMMIT_MSG\nfix: ok\nCOMMIT_MSG\n)\""
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("heredoc", r.stderr)

    def test_blocks_heredoc_with_whitespace_after_dollar_paren(self) -> None:
        cmd = "git commit -m \"$( cat <<EOF\nfix: spaced heredoc\nEOF\n)\""
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)
        self.assertIn("heredoc", r.stderr)

    def test_blocks_heredoc_carrying_boilerplate(self) -> None:
        cmd = (
            "git commit -m \"$(cat <<'EOF'\n"
            "fix: do thing\n\n"
            "Co-Authored-By: someone <s@example.com>\n"
            "EOF\n)\""
        )
        r = run_hook(cmd)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
