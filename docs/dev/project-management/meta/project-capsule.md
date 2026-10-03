# Project Capsule: claude-aegis

Generated: 2026-06-09 (refreshed after 00002 completion review)

## Key Invariants

- **Hooks are fail-open.** Every hook returns `{}`/allow on empty or malformed stdin (see `_common.read_input`, which now also returns `{}` on a TTY). A bad payload must never block a valid tool call; gateguard additionally fails open on malformed-but-valid-JSON payloads and state-dir IO errors.
- **Two signaling styles.** Seven hooks signal via exit code (0 = allow, 2 = block with reason on stderr, via `_common.block`/`allow`). gateguard uses the structured JSON envelope (`hookSpecificOutput.permissionDecision = deny`) and always exits 0. PRD 00003 will add a third shape: allow + `additionalContext` advisory (loop mode).
- **Stdlib only, Python 3.10+.** No third-party imports in any hook.
- **`${CLAUDE_PLUGIN_ROOT}` for hook paths in `hooks.json`; `Path.home()` for runtime state.** gateguard's state dir resolves via `Path.home()/.claude/cache/gateguard` (or `GATEGUARD_STATE_DIR`).
- **hooks.json ordering matters.** Cheap exit-code denies fire before the expensive JSON-envelope gate; gateguard is LAST in both the `Edit|Write|MultiEdit` and `Bash` matcher blocks.
- **gateguard is a speed bump, not a sandbox.** It forces facts before destructive actions; Warden owns command safety. Bypass-closing PRDs (00004) scope to verified shell-level forms only — no interpreter-payload (`python -c`) enumeration.
- **State-write concurrency is an accepted limitation** (documented in the gateguard module docstring): unlocked read-modify-write, atomic `os.replace`, lost marks self-heal.

## Architecture Decisions

- Each hook is a single self-contained script in `hooks/`, registered declaratively in `hooks/hooks.json`, with policy docs in `rules/` cited by error messages. Tests live in `hooks/tests/`, subprocess-based (no in-process import of the hook).
- `dev/bin/release` does SemVer bumps across `plugin.json`, `marketplace.json`, and the central marketplace. Version/tag/push are operator-manual; agents never release.
- `prefer_tools.py` splits commands on ALL separators (`|`, `;`, `&&`, `||`, `$(`, backtick) and judges each segment identically — it has no notion of "stream-fed segment", which is the root of issue #1 (PRD 00006 fixes this).
- gateguard's `_is_destructive` recurses into `<shell> -c` payloads via `_find_shell_c_payload`; quote-stripping happens only at the regex stage so `grep 'rm -rf'` stays allowed.

## Component Boundaries

- `hooks/_common.py` — shared `read_input` (TTY-aware) /`allow`/`block`. All eight hooks import it; gateguard imports only `read_input`.
- `hooks/hooks.json` — single registration source. Three matcher blocks: `Edit|Write|MultiEdit` (protect_config, block_suppression_markers, gateguard), `Bash` (validate_commit_msg, block_devlocal_redirects, prefer_tools, block_poll_loops, block_force_push, gateguard), `Monitor` (block_poll_loops). No test guards this file's integrity yet (PRD 00005 adds one — the 0.1.2 loader bug class).
- `skills/gateguard/SKILL.md` — aegis's first bundled skill; explains how to answer a `[Fact-Forcing Gate]` deny.
- gateguard exemptions: `_WORKING_DOC_DIR_SEGMENTS` (dev/local, ~/.claude/{plans,projects,scratch,sessions,cache}, prds/{backlog,wip,done}) via `is_working_doc_path()` — segment-substring based, does NOT resolve paths. No tmp coverage yet (PRD 00003 adds prefix-based tmp exemption).

## Active Work

- **PRD 00002 (gateguard hardening): IMPLEMENTED on master** (commits `c7d2b44..cda911c`, all nine deferrals closed). The PRD file sits in `backlog/` with a status banner; **awaiting user confirmation to move backlog/ -> done/** (rule forbids that move without explicit sign-off).
- **Dirty working tree (deliberate)**: `hooks/tests/test_gateguard_fact_force.py` carries three uncommitted tests (`bc12`-`bc15`); one is a RED test — `bash -O extglob -c "rm -rf /"` bypasses the gate (operand-taking option before `-c` ends the payload scan). PRD 00004 Phase 0 adopts these tests. Suite: 212 pass / 1 fail until then. `.serena/` is untracked (foreign tool dir, not ours).
- **Backlog (2026-06-09 review)**: 00003 (loop/style-hook exemption; corrected: real filenames, `additionalContext` advisory mechanism, no-path-resolution fact, CHANGELOG task added), 00004 (close gateguard bypasses: operand-flag `-c`, `eval` quoted payload, `find -delete`), 00005 (add CI: pytest matrix + hooks.json integrity test), 00006 (fix prefer_tools stream false positives, closes issue #1; sequence after 00003 — same file).
- Suggested order: 00004 (closes a live gate hole, adopts the red test) -> 00005 (CI guards everything after) -> 00003 -> 00006.

## GitHub State

- Repo `buvis/claude-aegis`, branch `master`. Latest tag v0.1.5 (2026-05-31); no GitHub Releases (tag-only). `[Unreleased]` carries the full gateguard Added + four Fixed entries — **0.2.0 is release-ready once the red test is resolved** (operator runs `dev/bin/release minor` manually).
- 1 open issue: **#1** prefer_tools piped tail/head false positive → now tracked by PRD 00006.
- No open PRs, no CI at all (no `.github/` — PRD 00005).

## Project Health

- Master itself is green (212 tests pass on committed code); the working tree is deliberately red (1 in-flight TDD test, see Active Work). No CI safety net. Debt is low and enumerated in the four backlog PRDs.

## Project Memories

(none on file)
