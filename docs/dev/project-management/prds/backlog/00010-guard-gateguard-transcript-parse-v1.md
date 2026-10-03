# Guard gateguard transcript parsing

## Overview

### Problem Statement

`transcript_has_read_of` (hooks/gateguard_fact_force.py:339-381) promises in its docstring (:343-345) that a malformed transcript never causes a crash, but it only guards `json.JSONDecodeError` (:365-366) and `OSError` (:350, :379-380). A transcript line that parses as valid JSON yet is not an object - e.g. `["Read", "/x/y.py"]` - passes the cheap pre-filter at :361 (the raw line contains `"Read"` and the target path) and reaches `entry.get("message")` at :367, raising AttributeError. Nothing above catches it: `main()` (:556-562) runs `prune_stale_state_files()`, `read_input()`, and `evaluate()` bare. The traceback exits with code 1, which PreToolUse treats as a non-blocking error - Claude Code shows the stderr and lets the Edit proceed ungated. Verified live (assessment A1, 2026-07-08): a transcript containing `["Read","/x/y.py"]` while editing `/x/y.py` makes the hook exit 1. Aegis's fail-open behavior is deliberate everywhere else; this is the one accidental fail-open, and it fires exactly when the gate is doing its job, because the pre-filter only forwards lines that mention the gated file. Severity MED, safety.

### Target Users

Solo developer relying on gateguard's fact-forcing gate; any aegis installer whose transcript JSONL carries non-object lines (summary records, harness format variations).

### Success Metrics

- A transcript line that is valid JSON but not an object is skipped: the hook exits 0 and still emits the correct gate decision based on the remaining lines.
- Any unexpected exception anywhere in the hook yields exit 0 (fail open) with a one-line stderr diagnostic naming the exception type - never a traceback with exit 1.
- The regression test reproducing A1 fails against current code (exit 1) and passes after the fix; `python -m pytest hooks/tests/ -q` fully green.

## Functional Decomposition

### Capability: Malformed-entry tolerance in the transcript scan

#### Feature: Non-dict JSON line guard

- **Description**: Skip transcript lines whose JSON parses to anything other than an object, honoring the docstring's no-crash promise.
- **Inputs**: Raw JSONL lines read inside `transcript_has_read_of` (hooks/gateguard_fact_force.py:358-378).
- **Outputs**: The malformed line is skipped; scanning continues; the return value reflects the remaining well-formed lines.
- **Behavior**: Immediately after `entry = json.loads(raw_line)` (:364), add `if not isinstance(entry, dict): continue`. Skip the line, never abort the scan - a later genuine Read entry must still count.

### Capability: Crash-proof entrypoint

#### Feature: Top-level fail-open guard in main()

- **Description**: A last-resort guard so no future bug in any code path can turn into an exit-1 ungated tool call.
- **Inputs**: Any exception raised by `prune_stale_state_files()`, `read_input()`, or `evaluate()` (:556-562).
- **Outputs**: Exit 0 (allow) plus a single stderr line: `gateguard: internal error (<ExceptionName>), failing open`.
- **Behavior**: Wrap the body of `main()` in `try/except Exception`. Catch `Exception`, not `BaseException`, so KeyboardInterrupt and SystemExit pass through. The deny path is unaffected: a deny is a returned JSON string written to stdout, never an exception.

## Structural Decomposition

### Repository Structure

```
claude-aegis/
├── hooks/
│   ├── gateguard_fact_force.py               # Maps to: both capabilities (EDIT, two small guards)
│   └── tests/
│       └── test_gateguard_fact_force.py      # Maps to: both capabilities (EDIT, regression tests)
└── CHANGELOG.md                              # Maps to: release notes (EDIT)
```

### Module: hooks/gateguard_fact_force.py

- **Maps to capability**: Malformed-entry tolerance; Crash-proof entrypoint
- **Responsibility**: Unchanged (fact-forcing PreToolUse gate); this PRD only makes its failure mode match its docstring.
- **Exports**: `transcript_has_read_of()` (isinstance guard added), `main()` (top-level guard added). No signature changes.

### Module: hooks/tests/test_gateguard_fact_force.py

- **Maps to capability**: Both capabilities (test surface)
- **Responsibility**: Lock exit-0-plus-correct-decision on malformed transcript lines, and exit 0 on simulated internal errors.
- **Exports**: pytest test functions; no public API.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **Regression test (A1 repro)**: subprocess test; fails today with exit 1 and so defines done.

### Core Layer (Phase 1)

- **isinstance guard + main() guard**: Depends on [regression test] - the fix lands only after the red run is recorded.

### Integration Layer (Phase 2)

- **CHANGELOG entry**: Depends on [Phase 1].

## Implementation Phases

### Phase 0: Foundation

**Goal**: The A1 crash is pinned by a failing test.

**Tasks**:

- [ ] Write the subprocess regression test: a transcript file containing the line `["Read", "<target>"]`, an Edit payload for that same, never-actually-Read code file (no deps) - Acceptance: against current code the test FAILS because the hook exits 1 with an AttributeError traceback; the red run is recorded in the task notes (mandatory fail-first for a bug fix).

**Exit Criteria**: Red run recorded; the test asserts exit 0 plus a deny decision on stdout (the file was never genuinely Read, so the gate must still deny).

### Phase 1: Core

**Goal**: The hook survives any malformed transcript and any internal error, failing open by design.

**Tasks**:

- [ ] Add `if not isinstance(entry, dict): continue` after :364 (depends on: Phase 0) - Acceptance: Phase 0 test green; a companion test with the malformed line FOLLOWED by a genuine Read tool_use entry for the target allows (proves skip-line, not abort-scan); parametrized non-dict shapes (list, string) both skip cleanly.
- [ ] Wrap the `main()` body in try/except Exception returning 0 with the one-line stderr diagnostic (depends on: Phase 0) - Acceptance: an in-process unit test monkeypatching `evaluate` to raise RuntimeError observes return value 0, the diagnostic on stderr, and no traceback.

**Exit Criteria**: `python -m pytest hooks/tests/ -q` fully green (entire suite, no skips).

### Phase 2: Integration

**Goal**: The fix is released properly.

**Tasks**:

- [ ] CHANGELOG `### Fixed` entry prefixed `**aegis**:` describing the user-visible effect (gateguard no longer crashes - and silently skips gating - on malformed transcript lines) (depends on: Phase 1) - Acceptance: entry present under [Unreleased].

**Exit Criteria**: Suite green; CHANGELOG updated.

## Test Strategy

### Critical Scenarios

- **Happy path (regression)**: transcript contains `["Read", "/tmp/t.py"]`; Edit payload targets `/tmp/t.py` → Expected: exit 0, deny JSON on stdout (gate still active), no traceback.
- **Edge case**: the same malformed line followed by a genuine assistant Read tool_use entry for the target → Expected: exit 0, allow (no deny) - the guard skips the line, not the scan.
- **Edge case**: non-dict variants (JSON list, JSON string) containing the pre-filter tokens → Expected: each skipped, exit 0.
- **Error case**: `evaluate` raises (simulated via monkeypatch) → Expected: `main()` returns 0, stderr carries the one-line diagnostic, stdout empty (allow).

## Risks

- **The broad except hides real bugs**: an internal error now exits 0 quietly. Mitigation: the stderr diagnostic names the exception type (visible in hook debug output); the specific isinstance guard keeps the known case handled precisely; once 00005 lands, CI runs the suite on every push.
- **Collision with the 00004/00007 gateguard merge**: both edit gateguard_fact_force.py. Mitigation: this PRD touches only `transcript_has_read_of` and `main()`; the merge touches `_is_destructive`/`_eval_bash`. Disjoint functions, trivial rebase in either order.
