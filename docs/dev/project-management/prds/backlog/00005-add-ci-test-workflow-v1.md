# Add CI test workflow

## Overview

### Problem Statement

The repo has 212 passing subprocess tests and zero automation: no `.github/` directory exists, so nothing runs them on push. Every regression guarantee depends on the developer remembering to run pytest locally before committing. The project's own history shows the cost of unverified registration: v0.1.2 shipped with `hooks/hooks.json` malformed ("expected record, received undefined"), leaving ALL hooks silently unregistered — a class of bug no current test covers. The hooks also claim cross-platform stdlib-only Python 3.10+, but are only ever exercised on the developer's macOS machine and Python version.

### Target Users

Solo developer (and any aegis contributor) who needs a red X on a bad push instead of discovering breakage in a live Claude Code session.

### Success Metrics

- Every push to `master` and every PR runs the full `hooks/tests/` suite on ubuntu-latest and macos-latest, on Python 3.10 and 3.13; a failure blocks with a visible red X.
- A malformed `hooks/hooks.json` (missing top-level `hooks` key, dangling script reference, unregistered hook script) fails the suite locally and in CI.
- Statement coverage of `hooks/` is measured and recorded in the CI log on every run.

## Functional Decomposition

### Capability: Automated test execution

Run the existing suite on a matrix that matches the claimed support surface.

#### Feature: GitHub Actions pytest workflow

- **Description**: A single workflow running `python -m pytest hooks/tests/ -q` across an OS x Python matrix.
- **Inputs**: Push to `master`, pull requests; repo checkout; matrix {ubuntu-latest, macos-latest} x {3.10, 3.13}.
- **Outputs**: Pass/fail status per matrix cell; coverage percentage in the job log.
- **Behavior**: `actions/checkout` + `actions/setup-python`, `pip install pytest pytest-cov`, run the suite with `--cov=hooks --cov-report=term`. Hooks are stdlib-only, so no other dependencies. Windows is out of scope (hooks run where Claude Code runs the user's shell; the plugin targets POSIX paths today — document this in the workflow comment rather than silently skipping).

#### Feature: Coverage threshold decision

- **Description**: Measure first, then gate.
- **Inputs**: The coverage number from the first green CI run.
- **Outputs**: Either `--cov-fail-under=80` added to the CI invocation, or a recorded gap with a follow-up note.
- **Behavior**: If measured coverage of `hooks/` is >= 80% (the project target per testing rules), turn the threshold on in the same PRD. If below, do NOT add a failing gate; record the actual number and the shortfall per file in the PRD audit notes so the gap is loud, not hidden.

### Capability: Registration integrity

A test that fails when `hooks.json` and the `hooks/` directory disagree — the 0.1.2 bug class.

#### Feature: hooks.json consistency test

- **Description**: A stdlib-only pytest module validating `hooks/hooks.json` against the filesystem.
- **Inputs**: `hooks/hooks.json`, the set of `hooks/*.py` files (excluding `_common.py` and `tests/`).
- **Outputs**: Assertions that fail with a named culprit.
- **Behavior**: Assert (1) the file parses and has the top-level `hooks` key wrapping `PreToolUse` (regression for 0.1.2); (2) every `command` references a script that exists under `hooks/` via `${CLAUDE_PLUGIN_ROOT}`; (3) every hook script in `hooks/` appears in at least one matcher block (catches a new hook left unregistered); (4) every entry has `"type": "command"` and a numeric `timeout`.

## Structural Decomposition

### Repository Structure

```
.github/
└── workflows/
    └── test.yml                       # Maps to: GitHub Actions pytest workflow (NEW)
hooks/
└── tests/
    └── test_hooks_json.py             # Maps to: hooks.json consistency test (NEW)
README.md                              # Maps to: status badge (EDIT, optional one-liner)
```

### Module: .github/workflows/test.yml

- **Maps to capability**: Automated test execution
- **Responsibility**: Run the suite on the support matrix on every push/PR; report coverage.
- **Exports**: n/a (CI config); job name `test` consumed by the README badge.

### Module: hooks/tests/test_hooks_json.py

- **Maps to capability**: Registration integrity
- **Responsibility**: Fail loudly when hooks.json is malformed, references a missing script, or omits a shipped hook.
- **Exports**: pytest test functions; no public API.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **test_hooks_json.py**: pure local test; valuable even before CI exists.

### Core Layer (Phase 1)

- **test.yml**: Depends on [test_hooks_json.py] only in that the workflow should run a suite already green locally.

### Integration Layer (Phase 2)

- **README badge + coverage decision**: Depends on [test.yml] - needs a first green run and its coverage number.

## Implementation Phases

### Phase 0: Foundation

**Goal**: Registration integrity is locked by a local test.

**Tasks**:

- [ ] TDD `hooks/tests/test_hooks_json.py` with the four assertion groups (no deps) - Acceptance: suite green against current hooks.json; deliberately breaking a copy (drop `hooks` key / dangle a path / unregister gateguard) makes the named assertion fail.

**Exit Criteria**: `python -m pytest hooks/tests/test_hooks_json.py -q` green; mutation checks demonstrated in the task notes.

### Phase 1: Core

**Goal**: The suite runs in CI on the support matrix.

**Tasks**:

- [ ] Add `.github/workflows/test.yml` (matrix ubuntu/macos x 3.10/3.13, pytest + coverage report) (depends on: Phase 0) - Acceptance: pushed branch shows 4 green matrix cells; coverage percentage visible in the log.

**Exit Criteria**: First fully green workflow run on master.

### Phase 2: Integration

**Goal**: Coverage decision recorded; CI visible from the README.

**Tasks**:

- [ ] Apply the coverage threshold decision per the measured number (depends on: Phase 1) - Acceptance: either `--cov-fail-under=80` is active and green, or the actual number + per-file gaps are recorded in the task notes.
- [ ] Add a workflow status badge to README.md (depends on: Phase 1) - Acceptance: badge renders and points at the `test` workflow. No CHANGELOG entry — CI-only changes are exempt per the changelog rules.

**Exit Criteria**: CI green on master, badge visible, coverage stance explicit.

## Test Strategy

### Critical Scenarios

- **Happy path**: push to master with green suite → Expected: 4 green matrix cells.
- **Edge case**: hooks.json missing the top-level `hooks` wrapper (the 0.1.2 bug) → Expected: `test_hooks_json.py` fails naming the missing key.
- **Edge case**: a new hook script added to `hooks/` but not registered → Expected: the registration-completeness assertion fails naming the script.
- **Error case**: a test failing only on Linux or only on 3.10 → Expected: that matrix cell red while others green (the reason the matrix exists).

## Risks

- **Matrix flakiness from subprocess timing**: the suite spawns ~200 subprocesses; slow runners could hit hook timeouts. Mitigation: tests already use explicit `timeout=5` on subprocess calls; if a cell flakes, bump only the test-side timeout, never weaken assertions.
- **Coverage gate lands red**: adding `--cov-fail-under=80` before measuring would block unrelated work. Mitigation: the measure-first decision feature; the gate is only enabled at an observed >= 80%.
- **macOS runner cost/slowness**: macOS minutes are 10x Linux on private repos. Mitigation: repo is public (free); if that changes, drop macos to a master-only trigger.
