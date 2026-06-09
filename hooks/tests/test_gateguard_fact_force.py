"""Tests for hooks/gateguard_fact_force.py.

Subprocess-based, mirroring test_prefer_tools.py / test_protect_config.py.

Unlike the other aegis hooks, gateguard signals via a JSON envelope on stdout
(``hookSpecificOutput.permissionDecision == "deny"``) and its exit code is
always 0. These tests therefore assert on stdout, never on the exit code, and
isolate per-session state by pointing GATEGUARD_STATE_DIR at a fresh temp dir.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "gateguard_fact_force.py"

# Env vars the hook consults for session-key resolution. Scrubbed from the
# subprocess env so resolution is driven only by the test payload, never by
# whatever launched the test runner.
_SESSION_ENV = ("CLAUDE_SESSION_ID", "CLAUDE_TRANSCRIPT_PATH", "CLAUDE_PROJECT_DIR")


class GateGuardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # --- subprocess helpers ---

    def _env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in _SESSION_ENV}
        env["GATEGUARD_STATE_DIR"] = str(self.state_dir)
        return env

    def run_hook(self, payload: dict, transcript_path: str | None = None):
        data = dict(payload)
        if transcript_path is not None:
            data["transcript_path"] = transcript_path
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(data),
            capture_output=True,
            text=True,
            timeout=5,
            env=self._env(),
        )

    def run_hook_raw(self, raw: str):
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=raw,
            capture_output=True,
            text=True,
            timeout=5,
            env=self._env(),
        )

    # --- assertion helpers ---

    def assertDenied(self, r, *, contains=()):
        self.assertEqual(r.returncode, 0, "hook must always exit 0")
        self.assertTrue(r.stdout.strip(), f"expected a deny envelope, got: {r.stdout!r}")
        env = json.loads(r.stdout)
        hso = env["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "deny")
        reason = hso["permissionDecisionReason"]
        self.assertTrue(reason.startswith("[Fact-Forcing Gate]"))
        for needle in contains:
            self.assertIn(needle, reason)
        return reason

    def assertAllowed(self, r):
        self.assertEqual(r.returncode, 0, "hook must always exit 0")
        self.assertEqual(r.stdout.strip(), "", f"expected allow (empty stdout), got: {r.stdout!r}")

    @staticmethod
    def edit(file_path, session="s", tool="Edit"):
        return {"tool_name": tool, "tool_input": {"file_path": file_path}, "session_id": session}


class TestEditGate(GateGuardTestCase):
    def test_unread_code_file_denies_with_code_prompt(self):
        r = self.run_hook(self.edit("/proj/mod.py", session="e1"))
        self.assertDenied(
            r,
            contains=["import/require this file", "public functions/classes"],
        )

    def test_second_attempt_same_target_allows(self):
        first = self.run_hook(self.edit("/proj/mod.py", session="e2"))
        self.assertDenied(first)
        retry = self.run_hook(self.edit("/proj/mod.py", session="e2"))
        self.assertAllowed(retry)

    def test_config_file_gets_consumer_prompt(self):
        r = self.run_hook(self.edit("/proj/config.yaml", session="e3"))
        self.assertDenied(
            r,
            contains=["code or tooling that consumes this file", "fields/structure"],
        )

    def test_distinct_targets_each_deny(self):
        self.assertDenied(self.run_hook(self.edit("/a.py", session="e4")))
        # A different file in the same session is still its own first hit.
        self.assertDenied(self.run_hook(self.edit("/b.py", session="e4")))

    def test_sessions_are_isolated(self):
        self.assertDenied(self.run_hook(self.edit("/a.py", session="sessA")))
        # Same target, different session: independent state, denies again.
        self.assertDenied(self.run_hook(self.edit("/a.py", session="sessB")))

    def test_no_extension_defaults_to_code_prompt(self):
        r = self.run_hook(self.edit("/proj/Makefile_noext", session="e5"))
        self.assertDenied(r, contains=["public functions/classes"])

    def test_missing_file_path_allows(self):
        r = self.run_hook({"tool_name": "Edit", "tool_input": {}, "session_id": "e6"})
        self.assertAllowed(r)


class TestWriteGate(GateGuardTestCase):
    def test_new_code_file_denies_with_creation_prompt(self):
        r = self.run_hook(self.edit("/proj/new_mod.py", session="w1", tool="Write"))
        self.assertDenied(
            r,
            contains=["call this new file", "no existing file serves the same purpose"],
        )

    def test_new_config_file_consumer_prompt(self):
        r = self.run_hook(self.edit("/proj/new.json", session="w2", tool="Write"))
        self.assertDenied(r, contains=["code or tooling that will consume this file"])


class TestMultiEditGate(GateGuardTestCase):
    @staticmethod
    def multiedit(paths, session="m"):
        return {
            "tool_name": "MultiEdit",
            "tool_input": {"edits": [{"file_path": p} for p in paths]},
            "session_id": session,
        }

    def test_batch_single_deny_lists_all_files(self):
        r = self.run_hook(self.multiedit(["/x.py", "/y.py", "/z.py"], session="m1"))
        reason = self.assertDenied(r, contains=["MultiEdit batch"])
        for p in ("/x.py", "/y.py", "/z.py"):
            self.assertIn(p, reason)

    def test_batch_retry_allows(self):
        batch = self.multiedit(["/x.py", "/y.py"], session="m2")
        self.assertDenied(self.run_hook(batch))
        self.assertAllowed(self.run_hook(batch))

    def test_duplicate_paths_in_batch_dedup(self):
        r = self.run_hook(self.multiedit(["/dup.py", "/dup.py"], session="m3"))
        reason = self.assertDenied(r)
        # The path is listed once, not twice.
        self.assertEqual(reason.count("/dup.py"), 1)

    def test_all_exempt_batch_allows(self):
        r = self.run_hook(self.multiedit(["/x/dev/local/a.md", "/y/notes.txt"], session="m4"))
        self.assertAllowed(r)


class TestExemptions(GateGuardTestCase):
    def test_working_doc_dir_segment_exempt(self):
        # Non-markdown file under dev/local/ is exempt via the dir segment.
        r = self.run_hook(self.edit("/proj/dev/local/data.bin", session="x1"))
        self.assertAllowed(r)

    def test_prds_wip_dir_exempt(self):
        # Path outside dev/local and with a non-doc extension, so only the
        # /prds/wip/ segment can grant the exemption (isolates that rule).
        r = self.run_hook(self.edit("/proj/prds/wip/spec.py", session="x2"))
        self.assertAllowed(r)

    def test_markdown_extension_exempt(self):
        r = self.run_hook(self.edit("/proj/README.md", session="x3"))
        self.assertAllowed(r)

    def test_working_doc_substring_does_not_match(self):
        # "/dev/local.backup/" must NOT match the "/dev/local/" segment.
        r = self.run_hook(self.edit("/srv/dev/local.backup/code.py", session="x4"))
        self.assertDenied(r)

    def test_settings_json_exempt(self):
        self.assertAllowed(self.run_hook(self.edit("/home/u/.claude/settings.json", session="x5")))
        self.assertAllowed(
            self.run_hook(self.edit("/home/u/.claude/settings.local.json", session="x6"))
        )

    def test_gitignore_filename_exempt(self):
        r = self.run_hook(self.edit("/proj/.gitignore", session="x7"))
        self.assertAllowed(r)


class TestPriorReadSkip(GateGuardTestCase):
    def _transcript(self, file_path):
        tpath = self.state_dir / "transcript.jsonl"
        line = {
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": file_path}}
                ]
            }
        }
        tpath.write_text(json.dumps(line) + "\n", encoding="utf-8")
        return str(tpath)

    def test_edit_after_prior_read_allows(self):
        tpath = self._transcript("/foo.py")
        r = self.run_hook(self.edit("/foo.py", session="r1"), transcript_path=tpath)
        self.assertAllowed(r)

    def test_edit_of_other_file_still_denies(self):
        tpath = self._transcript("/foo.py")
        r = self.run_hook(self.edit("/bar.py", session="r2"), transcript_path=tpath)
        self.assertDenied(r)


class TestDestructiveBash(GateGuardTestCase):
    @staticmethod
    def bash(command, session="b"):
        return {"tool_name": "Bash", "tool_input": {"command": command}, "session_id": session}

    def test_rm_rf_denies_with_rollback_prompt(self):
        r = self.run_hook(self.bash("rm -rf /tmp/scratch", session="b1"))
        self.assertDenied(r, contains=["rollback"])

    def test_destructive_command_retry_allows(self):
        cmd = self.bash("rm -rf /tmp/scratch", session="b2")
        self.assertDenied(self.run_hook(cmd))
        self.assertAllowed(self.run_hook(cmd))

    def test_quoted_destructive_token_is_allowed(self):
        # The destructive token appears only inside quotes (a regex arg),
        # so quote-stripping suppresses the false positive.
        r = self.run_hook(self.bash("grep -iE 'rm -rf|drop table' file.log", session="b3"))
        self.assertAllowed(r)

    def test_various_destructive_tokens_deny(self):
        for i, cmd in enumerate(
            [
                "git reset --hard HEAD~1",
                "git push --force origin master",
                "git clean -f",
                "drop table users",
                "delete from accounts",
                "truncate logs",
                # NOTE: the `dd if=` trigger only fires when `=` is followed by a
                # word char (the regex ends `dd\s+if=` with `\b`). `dd if=/dev/...`
                # (leading `/`) is NOT caught -- a pre-existing source quirk,
                # out of scope for this verbatim port. See task notes.
                "dd if=backup.img of=disk",
            ]
        ):
            with self.subTest(cmd=cmd):
                r = self.run_hook(self.bash(cmd, session=f"bt{i}"))
                self.assertDenied(r)

    def test_plain_bash_allowed(self):
        self.assertAllowed(self.run_hook(self.bash("ls -la /tmp", session="b4")))

    def test_readonly_git_allowed(self):
        self.assertAllowed(self.run_hook(self.bash("git status --porcelain", session="b5")))
        self.assertAllowed(self.run_hook(self.bash("git log --oneline", session="b6")))
        self.assertAllowed(self.run_hook(self.bash("git diff --name-only", session="b7")))


class TestStatePersistence(GateGuardTestCase):
    def _write_state(self, session, checked, last_active):
        sf = self.state_dir / f"state-{session}.json"
        sf.write_text(json.dumps({"checked": checked, "last_active": last_active}), encoding="utf-8")
        return sf

    def test_recent_checked_target_allows(self):
        self._write_state("st1", ["/foo.py"], time.time())
        r = self.run_hook(self.edit("/foo.py", session="st1"))
        self.assertAllowed(r)

    def test_expired_state_refires(self):
        # last_active older than the 30-minute timeout: state is pruned, so the
        # previously-checked target gates again.
        self._write_state("st2", ["/foo.py"], time.time() - 31 * 60)
        r = self.run_hook(self.edit("/foo.py", session="st2"))
        self.assertDenied(r)

    def test_state_file_written_under_state_dir(self):
        self.assertDenied(self.run_hook(self.edit("/foo.py", session="st3")))
        self.assertTrue((self.state_dir / "state-st3.json").exists())

    def test_corrupt_state_file_fails_open_and_denies(self):
        sf = self.state_dir / "state-st4.json"
        sf.write_text("{not valid json", encoding="utf-8")
        # Corrupt state is treated as empty, so the first hit still gates.
        self.assertDenied(self.run_hook(self.edit("/foo.py", session="st4")))


class TestSessionKeyResolution(GateGuardTestCase):
    def test_camelcase_session_id_isolates_state(self):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "/a.py"}, "sessionId": "camel1"}
        self.assertDenied(self.run_hook(payload))
        self.assertAllowed(self.run_hook(payload))

    def test_transcript_fallback_when_no_session_id(self):
        # No session_id/sessionId: the transcript path becomes the state key, so
        # two calls sharing it share state (deny then allow).
        tpath = str(self.state_dir / "tx.jsonl")
        Path(tpath).write_text("\n", encoding="utf-8")
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "/a.py"}}
        self.assertDenied(self.run_hook(payload, transcript_path=tpath))
        self.assertAllowed(self.run_hook(payload, transcript_path=tpath))


class TestPathSanitization(GateGuardTestCase):
    def test_control_chars_stripped_from_reported_path(self):
        r = self.run_hook(self.edit("/proj/ev\nil.py", session="p1"))
        reason = self.assertDenied(r)
        # The raw newline inside the path must not survive into the message body
        # of the path line (sanitize_path replaces control chars with spaces).
        self.assertNotIn("/proj/ev\nil.py", reason)


class TestMalformedInput(GateGuardTestCase):
    def test_empty_stdin_allows(self):
        r = self.run_hook_raw("")
        self.assertAllowed(r)

    def test_invalid_json_allows(self):
        r = self.run_hook_raw("not json at all")
        self.assertAllowed(r)

    def test_non_dict_json_allows(self):
        r = self.run_hook_raw("[1, 2, 3]")
        self.assertAllowed(r)

    def test_unknown_tool_allows(self):
        r = self.run_hook({"tool_name": "Read", "tool_input": {"file_path": "/a.py"}, "session_id": "u1"})
        self.assertAllowed(r)


if __name__ == "__main__":
    unittest.main()
