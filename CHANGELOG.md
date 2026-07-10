# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **aegis**: gateguard honors `GATEGUARD_EXEMPT_GLOBS` - comma-separated fnmatch patterns that exempt matching paths from the Edit/Write/MultiEdit fact-forcing gate (generated code, vendored trees, and other targets where the fact list carries no signal). Ported from upstream ECC gateguard.

## [0.2.2] - 2026-07-10

### Fixed

- **aegis**: gateguard no longer gates temp/scratch paths (`/tmp/`, `/var/folders/`, session `scratchpad/` dirs, relative `tmp/`). Throwaway files have no importers or consumers to investigate, and gating them produced consecutive-deny retry storms (observed 14 Write denials in a row in one session) with zero signal.

## [0.2.1] - 2026-07-08

### Fixed

- **aegis**: `prefer_tools.py`'s `head`/`tail` deny message no longer suggests only the Read tool, which cannot read a process's stdout. For `cmd | head/tail` it now routes to running the command bare (Bash truncates long output) or redirecting to a file and Reading that, so a blocked agent recovers in one step instead of guessing.

## [0.2.0] - 2026-06-16

### Added

- **aegis**: `gateguard_fact_force.py` hook - a fact-forcing PreToolUse gate that denies the first Edit/Write per target (and destructive Bash commands like `rm -rf`, `git reset --hard`, `git push --force`) with a fact list to gather before retrying, then allows the retry once the same target recurs in the session. Registered on the `Edit|Write|MultiEdit` and `Bash` matchers. Ships with a companion `skills/gateguard/SKILL.md` operator skill (aegis's first bundled skill) that explains how to respond to a `[Fact-Forcing Gate]` denial.

### Fixed

- **aegis**: gateguard now gates `MultiEdit` on the real top-level `file_path` payload. It previously read a per-edit `file_path` the tool never sends, so MultiEdit calls were never gated.
- **aegis**: gateguard's destructive-Bash detection now catches `dd if=/absolute/path` and destructive payloads inside `bash -c "..."` / `sh -c "..."` (including path-qualified shells like `/bin/bash`, bundled flags like `-xc`, a `--` before the script, and operand-taking options before `-c` such as `bash -O extglob -c ...` or `bash --rcfile FILE -c ...`), while still allowing quoted search patterns such as `grep -iE 'rm -rf'`.
- **aegis**: gateguard now fails open (allows, exit 0) on malformed-but-valid-JSON payloads (non-string `tool_name`, non-dict `tool_input`, non-string `file_path` or `command`) and on state-directory IO failures, instead of crashing.
- **aegis**: shared `_common.read_input()` returns `{}` on an interactive TTY instead of blocking on stdin, so running any hook by hand in a terminal no longer hangs.
- **aegis**: `prefer_tools.py` now routes blocked `grep`/`find` to `rg` (targeted search) or the `Explore` agent (broad fan-out) instead of the native `Grep`/`Glob` tools, which are unregistered in current native builds; the previous message told agents to use a tool that does not exist.

## [0.1.5] - 2026-05-31

### Added

- **aegis**: `block_suppression_markers.py` now detects more suppression forms - ruff/flake8 file-level disables, pyright and mypy ignores, bandit nosec, and biome-ignore.
- **aegis**: dedicated test suites for `prefer_tools.py` and `block_suppression_markers.py` (closes the 0.1.1 known gap); the suite is now 142 subprocess-based tests.

### Changed

- **aegis**: `block_poll_loops.py` now requires a completion exit (a `break`, or an `until` condition) alongside a file poll. A bare metric/monitor loop with no completion `break` (e.g. `while true; do du -sh /var; sleep 60; done`) is no longer blocked; process-liveness loops still are.
- **aegis**: `prefer_tools.py` ignores matches inside quoted strings, so a denied word merely named in a commit message (`git commit -m 'see a | grep b'`) no longer false-blocks.
- **aegis**: all seven hooks now share `_common` (`read_input`/`allow`/`block`); `prefer_tools.py` and `block_suppression_markers.py` no longer reimplement stdin parsing.

### Fixed

- **aegis**: `block_suppression_markers.py` no longer crashes (exit 1 traceback) on empty or malformed input; it now fails open like the other hooks.
- **aegis**: `validate_commit_msg.py` no longer misses boilerplate or bad format in multiple `-m` flags, `--message=`, no-space `-m"x"`, grouped `-am`, or env-var / `git -c`-prefixed commits; heredoc commit construction is now blocked outright.
- **aegis**: `block_force_push.py` now catches `git` invoked by path (`/usr/bin/git push --force`) and no longer false-blocks a plain push whose trailing shell comment mentions `--force`.
- **aegis**: `block_devlocal_redirects.py` now catches the `>|` noclobber-override redirect and no longer blocks a `tee` that only reads from `dev/local/`.
- **aegis**: the plugin and marketplace manifests advertised "five hooks"; corrected to seven (`block_poll_loops` and `block_force_push` were omitted).

## [0.1.4] - 2026-05-18

### Added

- **aegis**: `block_force_push.py` hook - denies any `git push` carrying a force indicator (`--force`, `-f`, `--force-with-lease`, or a `+`-prefixed refspec). The block message points at the `!` prefix, which runs a command outside the agent tool layer, so a force push always takes a deliberate human action and never runs silently. Tokenizes the command with `shlex` and scans per shell segment, so a `--force` inside a quoted commit message does not false-trigger. Registered under the existing `Bash` PreToolUse matcher.

## [0.1.3] - 2026-05-18

### Added

- **aegis**: `block_poll_loops.py` hook - denies hand-rolled task-completion poll loops (`while`/`until` + `sleep` + a `wc`/`stat`/`du` size check, a `*.output`/`tasks/` path, or a `kill -0`/`pgrep` process-liveness check) in `Bash` and `Monitor` tool calls, pointing to the `TaskOutput` tool instead. Registers a new `Monitor` PreToolUse matcher.

## [0.1.2] - 2026-05-11

### Fixed

- **aegis**: wrap `hooks/hooks.json` event config in a top-level `hooks` object so Claude Code's plugin loader accepts the file (previously failed with "expected record, received undefined" at path `hooks`, leaving all five PreToolUse hooks unregistered).

## [0.1.1] - 2026-05-11

### Known gaps

- `prefer_tools.py` and `block_suppression_markers.py` ship without dedicated tests. Add coverage before the next minor release.

## [0.1.0] - 2026-05-11

### Added

- Initial release with five PreToolUse hooks:
  - `prefer_tools.py` — denies `grep|find|cat|head|tail` in Bash, surfacing Grep/Glob/Read alternatives (including inside pipes, chains, and subshells).
  - `block_devlocal_redirects.py` — denies shell redirects (`>`, `>>`, `&>`, `tee`) into `dev/local/`.
  - `block_suppression_markers.py` — denies Edit/Write/MultiEdit that newly adds lint or type-checker suppression comments across Rust, Python, JS/TS, Java, Go, and C/C++.
  - `protect_config.py` — denies Edit/Write/MultiEdit on ESLint, Prettier, Biome, Ruff, Stylelint, Markdownlint, Clippy, SwiftLint, and ShellCheck config files.
  - `validate_commit_msg.py` — denies `git commit -m` messages that don't match the conventional commit format, end with a period, or contain `Co-Authored-By` / `Signed-Off-By` / `Generated-By` trailers.
- Companion `rules/` directory with `tools.md`, `working-documents.md`, `coding-style.md`, and `development-workflow.md` documenting the enforced policy.
- Test suite covering `block_devlocal_redirects`, `protect_config`, and `validate_commit_msg` (49 tests, subprocess-based).
- `dev/bin/release` script for SemVer-aware version bumps.
