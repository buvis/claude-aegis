# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
