# Exempt the Autopilot Loop from Style Hooks

## Overview

### Problem Statement
On 2026-06-09, inside autopilot sessions alone, aegis hooks blocked the agent ~1,000 times: 619 `prefer_tools.py` denials (bash `grep`/`find`/`cat` and pipe patterns) and 374 gateguard fact-gates. Each denial wastes a full model turn (the blocked call, the apology, the retry) at roughly 100K+ cache-read tokens per turn, and 7% of all autopilot tool calls returned errors. These hooks earn their keep in interactive sessions by training better tool habits — but an unattended loop has no habits to train; it just pays.

Two aggravations: `prefer_tools.py` recommends the native Grep/Glob tools, which are currently absent from every session (upstream Claude Code bug, zero Grep/Glob calls in 96 sessions in the audit week), so the advice is unfollowable; and gateguard fact-gates fire on `/tmp/` throwaway scripts (three times during the audit itself), which are not the duplicate-implementation risk the gate exists to catch.

### Target Users
The solo developer whose autopilot quota and wall-clock are spent on style-enforcement retries inside `autoclaude` loops, while keeping full hook protection in interactive sessions.

### Success Metrics
- Replaying a sample of the 2026-06-09 in-loop blocked commands with `_AUTOPILOT_LOOP` set yields ≥90% allows.
- Interactive behavior (env unset) is byte-identical: same denials, same messages.
- Gateguard no longer fires on `/tmp/` or `$TMPDIR` file creation in any session.
- `prefer_tools.py` denial text suggests `rg` as the fallback whenever it recommends Grep/Glob.

## Functional Decomposition

### Capability: Loop-Aware prefer_tools
The hook keeps teaching interactively and stops taxing the loop.

#### Feature: Loop Exemption
- **Description**: When `_AUTOPILOT_LOOP` is set in the hook's environment, `prefer_tools.py` allows the command and surfaces a one-line advisory instead of denying.
- **Inputs**: `os.environ["_AUTOPILOT_LOOP"]` (exported by `autoclaude`, inherited by the claude process and its hooks); the existing match/deny logic.
- **Outputs**: In loop mode, exit 0 with a JSON envelope on stdout: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "additionalContext": "<one-line advisory>"}}` — plain stdout on exit 0 is NOT shown to the model for PreToolUse, so the advisory must ride `additionalContext` (verify against current hook docs before coding; the context-mode plugin uses this mechanism today). Interactive mode keeps the unchanged exit-2 denial via `_common.block`.
- **Behavior**: The advisory keeps the nudge visible in transcripts without costing a retry turn. All pattern matching stays identical; only the verdict changes. Note `prefer_tools.py` currently signals only via `_common.allow`/`block` exit codes; loop mode adds the JSON-envelope path alongside.

#### Feature: Followable Suggestions
- **Description**: Denial/advisory text accounts for the native-tool absence.
- **Inputs**: The current message templates naming Grep/Glob.
- **Outputs**: Messages suggest the native tool first and `rg` (already allowed by policy) as the explicit fallback, e.g. "use Grep, or `rg` if Grep is unavailable in this session".
- **Behavior**: No detection magic (a hook cannot see the session's tool registry); just honest wording so the agent's first retry succeeds either way.

### Capability: Scratch-Aware Gateguard
The fact-gate targets repo code, not throwaway scratch.

#### Feature: Tmp Exemption
- **Description**: `gateguard_fact_force.py` skips paths under `/tmp/`, `/private/tmp/`, `/private/var/folders/`, and `$TMPDIR`.
- **Inputs**: The existing exemption machinery in `gateguard_fact_force.py`: `_WORKING_DOC_DIR_SEGMENTS` checked by `is_working_doc_path()` (already covers `/dev/local/`, `~/.claude/{plans,projects,scratch,sessions,cache}`, and `/prds/{backlog,wip,done}/`).
- **Outputs**: Extended exemption predicate plus tests.
- **Behavior**: Repo files keep the full gate in every mode, loop or not — gateguard is a quality gate, not a style nudge, so it gets no loop exemption, only the scratch-path carve-out. Tmp prefixes are absolute-path prefixes, not directory segments, so they need a prefix check alongside the existing segment check (`/tmp/` as a segment would wrongly exempt `src/tmp/`).

## Structural Decomposition

### Repository Structure

```
hooks/
├── prefer_tools.py                          # Maps to: Loop Exemption, Followable Suggestions (EDIT)
├── gateguard_fact_force.py                  # Maps to: Tmp Exemption (EDIT)
└── tests/
    ├── test_prefer_tools.py                 # Maps to: Loop Exemption, Followable Suggestions (EDIT/NEW cases)
    └── test_gateguard_fact_force.py         # Maps to: Tmp Exemption (EDIT/NEW cases)
```

### Module: loop-aware-style
- **Maps to capability**: Loop-Aware prefer_tools
- **Responsibility**: Same matching, mode-dependent verdict, honest suggestions.
- **Exports**:
  - `prefer_tools.py` with env-gated verdict and updated templates

### Module: scratch-gateguard
- **Maps to capability**: Scratch-Aware Gateguard
- **Responsibility**: Path-exemption predicate covering OS scratch locations.
- **Exports**:
  - `gateguard_fact_force.py` with extended exemptions

## Dependency Graph

### Foundation Layer (Phase 0)
- **loop-aware-style**: No dependencies.
- **scratch-gateguard**: No dependencies. Both are independent single-file edits; built first and in parallel.

### Core Layer (Phase 1)
- No core modules — both features are foundation-layer; Phase 1 is verification against the audit corpus.

### Integration Layer (Phase 2)
- No integration modules.

## Implementation Phases

### Phase 0: Foundation
**Goal**: Both hooks behave per the new contract under test.

**Tasks**:
- [ ] TDD `prefer_tools.py`: env set -> allow + advisory; env unset -> deny unchanged; templates mention `rg` fallback (no deps) - Acceptance: test matrix green; existing tests untouched except message-text assertions.
- [ ] TDD `gateguard_fact_force.py`: `/tmp/`, `/private/var/folders/`, `$TMPDIR` paths pass; repo paths still gated in both modes (no deps) - Acceptance: test matrix green.
- [ ] Add CHANGELOG `[Unreleased]` entries (loop advisory mode + tmp exemption are user-visible behavior changes: `### Changed`) (depends on: both TDD tasks) - Acceptance: entries present, prefixed `**aegis**:`, describing the user-visible effect.

**Exit Criteria**: Both suites green; all hooks remain Python-only per the cross-platform rule; CHANGELOG updated.

### Phase 1: Core
**Goal**: Proven against real traffic.

**Tasks**:
- [ ] Replay verification: extract a sample (≥50) of 2026-06-09 in-loop blocked commands from transcripts; run both hooks in loop mode against them (depends on: Phase 0) - Acceptance: ≥90% allow rate recorded in the PRD audit log with the residual denials listed and justified.

**Exit Criteria**: Replay numbers recorded; plugin version bumped per the release flow.

## Test Strategy

### Critical Scenarios
- **Happy path**: loop session runs `grep -r foo src/` -> Expected: allowed, one advisory line, no retry turn.
- **Edge case**: interactive session, same command -> Expected: denied with the same message as today plus the `rg` fallback wording.
- **Edge case**: loop session writes a new repo source file -> Expected: gateguard still gates (no loop exemption for fact-forcing).
- **Error case**: `_AUTOPILOT_LOOP` set but empty string -> Expected: treated as set (mirrors the SKILL's own `${_AUTOPILOT_LOOP-}` check semantics — decide and test explicitly).

## Risks

- **Loop sessions drift into sloppy shell habits**: Mitigation: advisory line keeps the signal in transcripts; gateguard and warden remain fully active; revisit if transcript advisories trend up.
- **Env var not visible to hook process**: Mitigation: verified mechanism — autoclaude exports it and hooks inherit the claude process env (the SKILL's loop-detection check relies on the same fact); Phase 0 test runs the real hook in a subprocess with the env set.
- **Exemption too broad** (`$TMPDIR` symlinks): Mitigation: the existing `is_working_doc_path()` does NOT resolve paths (it substring-matches the raw path), so handle macOS aliasing explicitly — match both the literal prefixes (`/tmp/`, `/private/tmp/`, `/private/var/folders/`, `$TMPDIR` value) and their `Path.resolve()` forms, with tests for the `/tmp` → `/private/tmp` symlink case.
