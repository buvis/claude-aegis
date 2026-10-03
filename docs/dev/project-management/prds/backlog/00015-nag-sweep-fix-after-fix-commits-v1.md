# Nag for a Portfolio Sweep After a Fix Commit

Source: `~/.claude/dev/local/discovery/00151-sweep-fixes-across-repos.md`
(Q1/Q2, revised at the 2026-08-28 review). Companion to `agent-skills`
PRD `00002-add-sweep-fix-skill-v1`, which builds the `/sweep-fix` skill this
nag names.

## Overview

### Problem Statement

`rules/development-workflow.md` § Bug Fix Discipline asks "Is this mistake
somewhere else also?" after every fix, and nothing reminds anyone. Skills
self-fire about once in thirty on real work, so a manual `/sweep-fix` skill
alone will be forgotten exactly when it matters - right after a fix lands. A
deterministic reminder is the half a standing rule cannot supply.

### Target Users

The solo maintainer, in the seconds after `git commit` of a `fix:` change made
through the Bash tool.

### Success Metrics

- A `fix:` commit made through the Bash tool prints exactly one nag line naming
  the short sha and the sweep command.
- A `feat:` commit prints nothing.
- The nag never blocks: it is a `PostToolUse` handler, whose exit 2 cannot gate.

## Functional Decomposition

### Capability: Fix-commit detection

#### Feature: Recognise a completed fix commit

- **Description**: Decide whether the Bash call that just ran created a commit
  whose conventional type is `fix`.
- **Inputs**: The `PostToolUse` payload for a `Bash` call - the command string and
  its result.
- **Outputs**: Either nothing, or the short sha of the new commit.
- **Behavior**: Fires only for a `git commit` that succeeded. The conventional
  type is read from the committed message, not from the command line, so
  `-F`, `-m` and editor commits behave the same. `fix`, `fix(scope)` and the
  breaking `fix!:` / `fix(scope)!:` all count; every other type
  (`feat`, `chore`, `refactor`, ...) counts as no.

### Capability: Reminder output

#### Feature: Print one nag line

- **Description**: Tell the model a sweep is available for this sha.
- **Inputs**: The short sha.
- **Outputs**: One line on stderr naming the short sha and `/sweep-fix {sha}`.
- **Behavior**: One line, once, per qualifying commit. Never more than one line,
  never a block, never a question. `PostToolUse` exit 2 cannot block, so the
  handler informs and exits 0 on every path, including its own errors.

## Structural Decomposition

### Repository Structure

```
hooks/
├── hooks.json                    # Maps to: Fix-commit detection (registration)
├── nag_sweep_fix.py              # Maps to: both capabilities
└── tests/
    └── test_nag_sweep_fix.py     # Tests for the handler
```

### Module: nag_sweep_fix.py

- **Maps to capability**: Fix-commit detection, Reminder output
- **Responsibility**: Read the `PostToolUse` payload, decide whether a `fix`
  commit just landed, print at most one reminder line.
- **Exports**:
  - `is_fix_commit(command, output)` - short sha or `None`
  - `main()` - hook entry point, always exit 0

### Module: hooks.json

- **Maps to capability**: Fix-commit detection
- **Responsibility**: Register the handler. Today the manifest carries
  `PreToolUse` only (`Edit|Write|MultiEdit`, `Bash`, `Monitor`); this adds the
  plugin's first `PostToolUse` block, matcher `Bash`.
- **Exports**: The `PostToolUse` / `Bash` registration entry, timeout 5.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **nag_sweep_fix.py**: the detection and output logic, testable without any
  registration.

### Core Layer (Phase 1)

- **hooks.json**: Depends on [nag_sweep_fix.py]

### Integration Layer (Phase 2)

- **release and install**: Depends on [hooks.json, nag_sweep_fix.py]. A plugin
  PRD is not done until the plugin is released and `/plugin update` has run;
  the handler is inert in the installed cache until then.

## Implementation Phases

### Phase 0: Foundation

**Goal**: The decision and the message exist and are pinned by tests.

**Tasks**:

- [ ] Add `hooks/nag_sweep_fix.py` with `is_fix_commit()` and a `main()` that
  always exits 0 (no deps)
  - Acceptance: `is_fix_commit` returns a sha for `fix:`, `fix(scope):`, `fix!:`
    and `fix(scope)!:`, and `None` for `feat:`, `chore:`, a failed commit, and a
    `git commit` that created nothing.
- [ ] Add `hooks/tests/test_nag_sweep_fix.py` (no deps)
  - Acceptance: a `fix:` payload produces exactly one stderr line containing the
    short sha and `/sweep-fix`; a `feat:` payload produces no output; both exit 0.

**Exit Criteria**: `uv run --with pytest pytest hooks/tests/test_nag_sweep_fix.py`
passes with zero failures.

### Phase 1: Core

**Goal**: The handler is wired into the plugin's hook manifest.

**Tasks**:

- [ ] Add a `PostToolUse` block with matcher `Bash` to `hooks/hooks.json`
  registering `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/nag_sweep_fix.py`, timeout 5
  (depends on: Phase 0)
  - Premise: `hooks/hooks.json` today has no `PostToolUse` key and its
    `PreToolUse` matchers are `Edit|Write|MultiEdit`, `Bash`, `Monitor`. Re-check
    at execution time; if a `PostToolUse` block already exists, append to it
    rather than creating one, and report the difference.
  - Acceptance: `python3 -c "import json; json.load(open('hooks/hooks.json'))"`
    parses, and the manifest contains exactly one registration of
    `nag_sweep_fix.py`.
- [ ] Add the CHANGELOG entry under `[Unreleased]` / Added (depends on: Phase 0)
  - Acceptance: `CHANGELOG.md` carries one `**aegis**:` line describing the nag.

**Exit Criteria**: The manifest parses and the full aegis hook suite passes.

### Phase 2: Integration

**Goal**: The nag is live on this machine, not merely committed.

**Tasks**:

- [ ] Release aegis and install it (depends on: Phase 1)
  - Acceptance: `nag_sweep_fix.py` is present in the installed cache under
    `~/.claude/plugins/cache/buvis-plugins/aegis/<version>/hooks/`, and that
    version's `hooks.json` carries the `PostToolUse` registration - verified in
    the shipped cache, not from the version string.

**Exit Criteria**: A real `fix:` commit made through the Bash tool prints the nag
line once.

## Test Strategy

### Critical Scenarios

- **Happy path**: `git commit -m "fix(warden): stop swallowing errors"` →
  exactly one stderr line naming the short sha and `/sweep-fix {sha}`.
- **Happy path**: `git commit -m "fix!: drop the legacy flag"` → nagged
  (breaking fixes still count).
- **Edge case**: `git commit -m "feat: add the thing"` → no output at all.
- **Edge case**: a commit whose message came from `-F` or an editor → the type is
  still read from the committed message, so the nag behaves identically.
- **Error case**: the commit failed (nothing created) → no output, exit 0.
- **Error case**: the handler itself raises → exit 0 with no output; it can never
  interfere with a commit.

## Risks

- **Nag fatigue**: one line, `fix:` only, always naming the sha. If a month of
  nags goes unacted, delete the hook rather than tune it.
- **Blind spot accepted**: commits made by hand in a terminal, or by another
  agent, are never nagged. Rejected alternatives were a global `core.hooksPath`
  git hook (silently overrides any repo's own hooks) and per-repo hooks (26
  installs, lost on clone).
- **Release gate**: the handler does nothing until aegis is released and
  installed. Phase 2 exists precisely so the PRD is not called done on an inert
  file, the failure recorded in `feedback_plugin_prd_not_done_until_released`.
- **Wrong-shape detection**: reading the conventional type off the command line
  instead of the committed message would miss `-F` and editor commits; the tests
  pin the message-side read.
