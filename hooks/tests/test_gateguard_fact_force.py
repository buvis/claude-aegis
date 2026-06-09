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
    def multiedit(file_path, session="m"):
        return {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": file_path,
                "edits": [
                    {"old_string": "a", "new_string": "b"},
                    {"old_string": "c", "new_string": "d"},
                ],
            },
            "session_id": session,
        }

    def test_first_multiedit_on_unread_file_denies_and_names_it(self):
        r = self.run_hook(self.multiedit("/proj/mod.py", session="m1"))
        reason = self.assertDenied(r)
        self.assertIn("/proj/mod.py", reason)
        self.assertEqual(reason.count("/proj/mod.py"), 1)

    def test_second_multiedit_on_same_target_allows(self):
        payload = self.multiedit("/proj/mod.py", session="m2")
        self.assertDenied(self.run_hook(payload))
        self.assertAllowed(self.run_hook(payload))

    def test_working_doc_target_allows(self):
        r = self.run_hook(self.multiedit("/proj/dev/local/notes.md", session="m3"))
        self.assertAllowed(r)

    def test_prior_read_target_allows(self):
        tpath = self.state_dir / "transcript.jsonl"
        line = {
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/proj/mod.py"}}
                ]
            }
        }
        tpath.write_text(json.dumps(line) + "\n", encoding="utf-8")
        r = self.run_hook(self.multiedit("/proj/mod.py", session="m4"), transcript_path=str(tpath))
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
                "dd if=backup.img of=disk",
            ]
        ):
            with self.subTest(cmd=cmd):
                r = self.run_hook(self.bash(cmd, session=f"bt{i}"))
                self.assertDenied(r)

    def test_dd_absolute_path_denies(self):
        # Absolute-path form (dd if=/dev/zero of=/dev/sda) must deny, same as
        # the bareword form. Both forms are asserted here.
        r_abs = self.run_hook(self.bash("dd if=/dev/zero of=/dev/sda", session="bdd1"))
        self.assertDenied(r_abs)
        r_bare = self.run_hook(self.bash("dd if=backup.img of=disk", session="bdd2"))
        self.assertDenied(r_bare)

    def test_bash_dash_c_destructive_payload_denies(self):
        # The destructive command is INSIDE the bash -c quoted body.
        # A hook that strips all quoted substrings before matching will wrongly allow this.
        r = self.run_hook(self.bash('bash -c "rm -rf /"', session="bc1"))
        self.assertDenied(r)

    def test_sh_dash_c_destructive_payload_denies(self):
        r = self.run_hook(self.bash('sh -c "rm -rf /"', session="bc2"))
        self.assertDenied(r)

    def test_bash_dash_c_single_quoted_destructive_payload_denies(self):
        r = self.run_hook(self.bash("bash -c 'git reset --hard HEAD~1'", session="bc3"))
        self.assertDenied(r)

    def test_grep_quoted_destructive_pattern_allows(self):
        # The destructive tokens are search DATA inside quotes, not a command.
        # Must allow — the gate should not false-positive on grep/rg patterns.
        r = self.run_hook(self.bash("grep -iE 'rm -rf|git reset --hard'", session="bc4"))
        self.assertAllowed(r)

    def test_bash_dash_c_benign_payload_allows(self):
        # A non-destructive bash -c body must NOT be denied.
        # Guards against an over-eager fix that denies every bash -c invocation.
        r = self.run_hook(self.bash('bash -c "ls -la"', session="bc5"))
        self.assertAllowed(r)

    def test_bash_dash_c_with_quoted_search_pattern_allows(self):
        # The destructive token "rm -rf" appears only as DATA inside single quotes
        # within a grep argument — the bash -c body itself is a benign grep, not a
        # destructive command. A raw-scan impl wrongly denies this; a correct impl
        # that re-evaluates the bash -c payload with the same quote-aware allowance
        # must allow it.
        r = self.run_hook(self.bash("bash -c \"grep -iE 'rm -rf' f\"", session="bc6"))
        self.assertAllowed(r)

    def test_path_qualified_shell_destructive_payload_denies(self):
        # Shell referenced by absolute path (/bin/bash, /bin/sh) with -c and a
        # destructive payload. A hook that only matches the bare name will allow.
        r_bash = self.run_hook(self.bash('/bin/bash -c "rm -rf /"', session="bc7"))
        self.assertDenied(r_bash)
        r_sh = self.run_hook(self.bash('/bin/sh -c "rm -rf /"', session="bc8"))
        self.assertDenied(r_sh)

    def test_combined_short_flags_destructive_payload_denies(self):
        # -c bundled with another short flag (e.g. -xc). The payload is the next
        # positional argument after the combined flag, not after a standalone -c.
        r_bash = self.run_hook(self.bash("bash -xc 'rm -rf /'", session="bc9"))
        self.assertDenied(r_bash)
        r_sh = self.run_hook(self.bash("sh -ec 'git reset --hard HEAD~1'", session="bc10"))
        self.assertDenied(r_sh)

    def test_dash_dash_before_payload_destructive_denies(self):
        # An explicit -- end-of-options token sits between -c and the payload.
        r = self.run_hook(self.bash('bash -c -- "rm -rf /"', session="bc11"))
        self.assertDenied(r)

    def test_plain_bash_allowed(self):
        self.assertAllowed(self.run_hook(self.bash("ls -la /tmp", session="b4")))

    def test_readonly_git_allowed(self):
        self.assertAllowed(self.run_hook(self.bash("git status --porcelain", session="b5")))
        self.assertAllowed(self.run_hook(self.bash("git log --oneline", session="b6")))
        self.assertAllowed(self.run_hook(self.bash("git diff --name-only", session="b7")))

    def test_all_readonly_git_forms_allow(self):
        # Equivalence guard: every read-only git form must ALLOW before and
        # after the planned removal of the internal early-return short-circuit.
        readonly_forms = [
            "git status",
            "git status --porcelain",
            "git status --short",
            "git status --branch",
            "git diff",
            "git diff --name-only",
            "git diff --name-status",
            "git log",
            "git log --oneline",
            "git log --max-count=5",
            "git show HEAD",
            "git show 1a2b3c4",
            "git branch --show-current",
            "git rev-parse --abbrev-ref HEAD",
        ]
        for i, cmd in enumerate(readonly_forms):
            with self.subTest(cmd=cmd):
                r = self.run_hook(self.bash(cmd, session=f"rg{i}"))
                self.assertAllowed(r)


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

    def test_non_dict_state_json_treated_as_fresh_and_denies(self):
        # Valid JSON that is not a dict ([], "x", 42) must be treated as an
        # empty default, so the first edit of an unread file still denies.
        # A loader that calls .get() on the parsed value will crash here.
        for i, value in enumerate([[], "x", 42]):
            with self.subTest(value=value):
                session = f"st5_{i}"
                sf = self.state_dir / f"state-{session}.json"
                sf.write_text(json.dumps(value), encoding="utf-8")
                r = self.run_hook(self.edit("/foo.py", session=session))
                self.assertDenied(r)

    def test_state_dir_mkdir_failure_does_not_crash(self):
        # Point GATEGUARD_STATE_DIR at a path whose parent is a regular file,
        # so mkdir(parents=True) raises NotADirectoryError (an OSError subclass).
        # The hook must NOT crash: exit code 0, empty stderr.
        blocker = self.state_dir / "blocker"
        blocker.write_bytes(b"x")
        bad_state_dir = str(blocker / "sub")
        env = self._env()
        env["GATEGUARD_STATE_DIR"] = bad_state_dir
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(self.edit("/foo.py", session="io1")),
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        self.assertEqual(r.returncode, 0, f"hook crashed (non-zero exit): stderr={r.stderr!r}")
        self.assertEqual(r.stderr, "", f"traceback on stderr: {r.stderr!r}")


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


class TestMalformedFieldTypes(GateGuardTestCase):
    def test_wrong_typed_fields_allow_without_crash(self):
        cases = [
            ("tool_name is non-string", {"tool_name": 5, "tool_input": {"file_path": "/a.py"}}),
            ("tool_input is non-dict", {"tool_name": "Edit", "tool_input": "notadict"}),
            ("file_path is non-string", {"tool_name": "Edit", "tool_input": {"file_path": 42}}),
            ("command is non-string", {"tool_name": "Bash", "tool_input": {"command": ["x"]}}),
        ]
        for label, payload in cases:
            with self.subTest(case=label):
                r = self.run_hook(payload)
                self.assertAllowed(r)
                self.assertEqual(r.stderr, "", f"traceback on stderr for case {label!r}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()
