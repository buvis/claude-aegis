# Fix prefer_tools stream false positives

## Overview

### Problem Statement

GitHub issue #1 (the repo's only open issue, 2026-05-18): `prefer_tools.py` denies `head`/`tail` even when they trim the **output of a pipe** rather than read a file (`cargo test | tail -20`). The deny message says "use Read with offset/limit", but Read and Grep only read files, not a process's stdout — the advice is unfollowable, so the denial just costs a turn and pushes the agent into a clumsier redirect-to-file-then-Read dance. The hook splits commands into pipe segments (`SEGMENT_RE`) but treats every segment identically; it never distinguishes "reads a file" (replaceable by Read) from "consumes the upstream stream" (no dedicated-tool replacement).

`grep` in a pipe (`ps aux | grep foo`) is different: `rg` reads stdin and is policy-allowed, so a 1:1 replacement exists — the verdict can stay deny, but the message must name the followable alternative.

### Target Users

Solo developer whose agent sessions burn a deny + apology + retry turn on every stream-trim, and any aegis installer hitting issue #1.

### Success Metrics

- `cargo test | tail -20` and `some-cmd | head -5` are allowed; `tail -100 file.log` and `head file` are still denied.
- `ps aux | grep foo` is still denied, with a message naming `rg` as the stream replacement and the Grep tool for files.
- GitHub issue #1 is closed referencing the fix.
- Existing suite stays green; both directions of the new rule are locked by tests.

## Functional Decomposition

### Capability: Stream-aware verdicts

A denied binary that consumes the upstream pipe with no file operand has no dedicated-tool replacement and must be allowed.

#### Feature: Pipe-consumer detection for head/tail

- **Description**: Allow `head`/`tail` when they appear as a non-first pipeline segment and carry no file operand.
- **Inputs**: The segment list from `SEGMENT_RE`, with position information (first vs. subsequent within a `|` pipeline — note `SEGMENT_RE` today also splits on `;`, `&&`, `||`, `$(`, and backtick, which do NOT feed a stream; only `|` does).
- **Outputs**: Allow for `cmd | tail -20`; deny preserved for `tail -20 file.log`, `tail file`, and `tail -f log` (first-segment file reads, including follow mode, are out of scope and keep today's verdict).
- **Behavior**: Track the separator that introduced each segment. For a `|`-introduced segment whose first meaningful token is `head`/`tail`: parse the remaining tokens; if every token is a flag or a flag operand (`-n 20`, `-n20`, `--lines=20`, legacy `-20`, `-c 100`), it consumes stdin → allow. Any non-flag operand means a file argument → deny as today. `cat file | tail` still dies at the `cat` segment (first in pipeline), which is correct.

#### Feature: Followable grep message

- **Description**: Keep denying `grep` in pipe positions but point at `rg`, which reads stdin.
- **Inputs**: A `|`-introduced segment whose first meaningful token is `grep`.
- **Outputs**: Deny with a message distinguishing the two replacements: Grep tool for file searches, `rg` for filtering a stream.
- **Behavior**: Message-only change; verdict unchanged. Coordinate wording with PRD 00003's "Followable Suggestions" feature (same file, same templates) — if 00003 has landed, extend its wording; if not, write the stream wording so 00003 can extend it.

### Capability: Documented policy

The hook cites `aegis/rules/tools.md`; the rule text must match the new behavior.

#### Feature: rules/tools.md stream exception

- **Description**: Document that stream-trimming `head`/`tail` after a `|` is allowed and why (no dedicated-tool replacement exists).
- **Inputs**: Current `rules/tools.md`.
- **Outputs**: An updated policy paragraph the deny message can keep citing truthfully.
- **Behavior**: State the rule, the rationale (Read/Grep read files, not process stdout), and the boundary (file-reading forms remain denied).

## Structural Decomposition

### Repository Structure

```
hooks/
├── prefer_tools.py                  # Maps to: Pipe-consumer detection, Followable grep message (EDIT)
└── tests/
    └── test_prefer_tools.py         # Maps to: both features (EDIT/NEW cases)
rules/
└── tools.md                         # Maps to: stream exception (EDIT)
CHANGELOG.md                         # Maps to: release notes (EDIT)
```

### Module: hooks/prefer_tools.py

- **Maps to capability**: Stream-aware verdicts
- **Responsibility**: Segment-position-aware verdicts; honest replacement suggestions.
- **Exports**:
  - `main()` - entrypoint (unchanged)
  - `first_meaningful_token()` - unchanged
  - a private segment iterator yielding (separator, segment) pairs replacing the bare `SEGMENT_RE.split`

### Module: hooks/tests/test_prefer_tools.py

- **Maps to capability**: Stream-aware verdicts (test surface)
- **Responsibility**: Lock allow/deny in both directions for every flag-operand form of head/tail; lock the grep message wording.
- **Exports**: pytest test functions; no public API.

### Module: rules/tools.md

- **Maps to capability**: Documented policy
- **Responsibility**: Keep the cited policy truthful after the behavior change.
- **Exports**: n/a (documentation).

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **separator-aware segment iterator + head/tail verdict**: the core fix.

### Core Layer (Phase 1)

- **grep message + rules/tools.md**: Depends on [Phase 0] - wording describes the implemented boundary.

### Integration Layer (Phase 2)

- **CHANGELOG + issue closure**: Depends on [Phase 0, Phase 1].

## Implementation Phases

### Phase 0: Foundation

**Goal**: Stream-trimming head/tail allowed; file-reading forms still denied.

**Tasks**:

- [ ] TDD the separator-aware segment iteration: only `|` marks a stream-fed segment; `;`/`&&`/`||`/`$(`/backtick segments keep first-segment semantics (no deps) - Acceptance: `cargo test | tail -20` allows; `cargo test && tail f.log` denies; `echo $(tail f.log)` denies.
- [ ] TDD the no-file-operand check for head/tail flag forms (`-n 20`, `-n20`, `--lines=20`, `-20`, `-c 100`) (depends on: previous) - Acceptance: each flag form after `|` allows; `cmd | tail -20 file.log` denies; `tail -f log` denies (unchanged).

**Exit Criteria**: `python -m pytest hooks/tests/test_prefer_tools.py -q` green with the new matrix; full suite green.

### Phase 1: Core

**Goal**: Messages and written policy match the new boundary.

**Tasks**:

- [ ] Update the grep deny message for pipe positions (Grep tool for files, `rg` for streams); coordinate with PRD 00003 wording if landed (depends on: Phase 0) - Acceptance: message test asserts both replacements are named.
- [ ] Update `rules/tools.md` with the stream exception and rationale (depends on: Phase 0) - Acceptance: rule text matches hook behavior; deny messages still cite a truthful path.

**Exit Criteria**: No message or rule text contradicts the implemented verdicts.

### Phase 2: Integration

**Goal**: Change is released-ready and the issue is closed.

**Tasks**:

- [ ] Add CHANGELOG `[Unreleased]` `### Fixed` entry for the stream false positive (depends on: Phase 1) - Acceptance: entry present, prefixed `**aegis**:`, describing the user-visible effect.
- [ ] Close GitHub issue #1 with a comment linking the fix commit (depends on: Phase 1) - Acceptance: issue state is closed with the reference.
- [ ] Update the operator's GLOBAL rule `~/.claude/rules/tools.md` (outside this repo, lives in the `~/.buvis` dotfiles bare repo): it currently says "Don't pipe command output to `tail`/`head`/`grep` to trim it. The `prefer_tools.py` hook blocks this" and teaches the redirect-to-file-then-Read workaround. After this PRD ships, that text contradicts the hook. Rewrite it to: stream-trimming `cmd | tail`/`cmd | head` is allowed; file-reading forms are still denied (use Read); use `rg` instead of `grep` on streams. Commit via `git --git-dir=~/.buvis --work-tree=~` (no CHANGELOG there per dotfiles rules) (depends on: Phase 1) - Acceptance: the global rule no longer claims the hook blocks stream pipes; wording matches the shipped behavior.

**Exit Criteria**: CHANGELOG updated; issue #1 closed; global tools rule consistent with the hook; full suite green.

## Test Strategy

### Critical Scenarios

- **Happy path**: `cargo test | tail -20` → Expected: allowed, no denial turn.
- **Edge case**: `cmd | tail -20 file.log` (file operand in pipe position) → Expected: denied (reads the file, Read replaces it).
- **Edge case**: `cargo test && tail out.log` (`&&` is not a stream) → Expected: denied.
- **Edge case**: `cat file | tail -5` → Expected: denied at the `cat` segment (unchanged).
- **Error case**: `ps aux | grep foo` → Expected: denied with `rg`-for-streams wording.

## Risks

- **Loophole abuse**: agents could launder file reads as `cmd | tail` (e.g. `true | tail file` is caught by the operand check, but creative forms may not be). Mitigation: the operand check denies any non-flag token; add adversarial tests; accept that a determined launder costs more than complying.
- **Flag-operand parsing diverges from coreutils reality**: misreading `-n 20` as a file operand re-introduces the false positive; misreading a file as a flag operand opens a hole. Mitigation: enumerate the documented head/tail flag forms (GNU + BSD) in a named constant with tests per form.
- **Conflict with PRD 00003** (same file, same templates): Mitigation: sequence after 00003 or rebase message wording; both PRDs name the coordination explicitly.
- **Policy drift with the user's global `~/.claude/rules/tools.md`** (which still teaches redirect-to-file for trimming and claims the hook blocks stream pipes): handled by the dedicated Phase 2 task above — the global rule edit ships with this PRD, not as a someday-followup.
