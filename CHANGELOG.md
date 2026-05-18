# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
