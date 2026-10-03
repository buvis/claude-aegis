---
rework_cap: 4
---

# gateguard hardening and refactor

> **Status (2026-06-09): IMPLEMENTED on master.** Every task in this PRD landed as commits `c7d2b44..cda911c` (MultiEdit real-schema gating, dd if=/abs, bash -c payload inspection incl. path-qualified/combined-flag/`--` forms, malformed-payload and state-IO fail-open, TTY guard in `_common.read_input`, `evaluate()` split, `is_read_only_git` removal, concurrency decision documented, CHANGELOG updated). Suite: 212 passing tests. Awaiting explicit confirmation to move this file to `done/` (it sits in `backlog/`, and backlog->done moves require user sign-off). One NEW bypass found after completion — an operand-taking option before `-c` (`bash -O extglob -c "rm -rf /"`) — is out of this PRD's scope; its red test is already in the working tree and the fix is tracked in PRD 00004.

## Overview

### Problem Statement

PRD 00001 ported `gateguard` into aegis as a deliberate **verbatim** copy — Phase 0 mandated "no behavior changes, only the file path moves." That was the right call for a safe migration, but it knowingly shipped every pre-existing defect of the source hook. The 00001 doubt review and decision gate catalogued nine of them (see `dev/local/autopilot/deferred/202606091318-deferred.json` and `dev/local/reviews/00001-gateguard-migration-v1-audit.md`). The most serious is silent and security-relevant: the fact-forcing gate **never fires on MultiEdit calls at all**, because `evaluate()` reads a per-edit `file_path` that the real Claude Code MultiEdit payload does not carry. Two more destructive-command forms (`dd if=/absolute/path` and destructive payloads inside `bash -c "..."`) also slip through the Bash gate. On top of those, the hook can raise (instead of failing open) on malformed-but-valid-JSON payloads and on state-directory IO failures, and it carries refactor debt (`evaluate()` is 67 lines; `is_read_only_git()` is dead indirection).

This PRD **reverses** 00001's verbatim-port constraint. Its mandate is to make the behavior changes 00001 deferred, test-driven: for each fix, write a test that encodes the **correct** behavior (which currently fails against the ported hook), then change the hook to make it pass. Crucially, some existing tests encode the **wrong** behavior (the MultiEdit tests mirror a per-edit `file_path` schema) and must be rewritten, not preserved.

### Target Users

Solo developer (and any future aegis installer) relying on gateguard to force investigation before edits and destructive Bash. Today they get a gate with three holes a destructive operation can walk through and two paths that can crash the hook. gateguard (0.2.0 from 00001) is **not yet released**, so closing these before first release ships it correct from day one — none of the changes are breaking (no released behavior depends on the holes).

### Success Metrics

- gateguard returns a deny envelope for a first-time MultiEdit on an unread file (single top-level `file_path`), and the MultiEdit tests assert against the **real** payload schema.
- `dd if=/dev/zero of=/dev/sda` (absolute-path form) and `bash -c "rm -rf /"` are both gated; the existing `grep -iE 'rm -rf|...'` false-positive stays allowed.
- Every malformed-but-valid-JSON payload (non-string `tool_name`, non-dict `tool_input`, non-string path/command) and every state-dir IO failure (`mkdir`/`mkstemp`) results in allow + exit 0 (fail-open preserved), with tests.
- `evaluate()` is under 50 lines; `is_read_only_git()` is removed only after a proof that no command's verdict changes.
- All nine 00001 verbatim-port deferrals are closed; `python -m pytest hooks/tests/ -q` is green with gateguard statement coverage ≥ 80%.

## Functional Decomposition

### Capability: Destructive-action gating correctness

The gate must actually fire on the actions it claims to gate. Three holes let actions through silently today.

#### Feature: MultiEdit gating against the real payload schema

- **Description**: Gate MultiEdit calls using the single top-level `tool_input["file_path"]`, not a non-existent per-edit `file_path`.
- **Inputs**: A PreToolUse payload with `tool_name == "MultiEdit"` and `tool_input == {"file_path": "<path>", "edits": [{"old_string": ..., "new_string": ...}, ...]}`.
- **Outputs**: A deny envelope naming the single target file (once) on first hit; allow on prior-Read, working-doc, or already-checked targets.
- **Behavior**: Read the top-level `file_path`; apply the same exemptions and prior-Read skip as `Edit`/`Write`; mark the target checked. The MultiEdit tests are rewritten to the real schema (they currently assert the wrong per-edit shape and must not be preserved).

#### Feature: dd-to-absolute-path detection

- **Description**: `DESTRUCTIVE_BASH` must match `dd if=/absolute/path`, not only `dd if=bareword`.
- **Inputs**: A Bash command string containing a `dd if=...` invocation.
- **Outputs**: Deny for `dd if=/dev/zero of=/dev/sda`; deny preserved for `dd if=backup.img`.
- **Behavior**: The trailing `\b` after `if=` fails when the next char is `/` (non-word). Replace the `dd\s+if=...\b` fragment so it matches when an absolute path or any non-space argument follows (e.g. `dd\s+if=\S`).

#### Feature: bash -c destructive payload detection (quote-aware)

- **Description**: A destructive command inside `bash -c "..."` must be gated, while the legitimate quoted-search false-positive stays allowed.
- **Inputs**: Bash command strings such as `bash -c "rm -rf /"` (must deny) and `grep -iE 'rm -rf|git reset --hard'` (must allow).
- **Outputs**: Deny for the `bash -c` destructive form; allow for the grep/ripgrep search-pattern form.
- **Behavior**: `_strip_quoted` currently removes ALL quoted substrings before matching, which suppresses the `bash -c` payload along with the grep pattern. Replace blanket quote-stripping with a shell-parse-aware check that strips quotes used as search arguments (e.g. to `grep`/`rg`/`egrep`) but still inspects the quoted body of a `bash -c` / `sh -c` invocation. This is the subtlest change; both directions must be locked by tests.

### Capability: Fail-open robustness

The hook's contract is always exit 0; a deny is signalled only via the JSON envelope. Two paths violate it by raising.

#### Feature: Malformed-payload type guards

- **Description**: Valid JSON with unexpected types must allow, not raise.
- **Inputs**: Payloads like `{"tool_name": 5, ...}`, `{"tool_input": "notadict"}`, `{"tool_input": {"file_path": 42}}`, `{"tool_input": {"command": ["x"]}}`.
- **Outputs**: Allow + exit 0 for every such payload (no stdout deny envelope, no traceback).
- **Behavior**: Add type guards at `evaluate()`'s boundary and in the per-tool branches so non-string/non-dict fields short-circuit to allow rather than reaching code that assumes a string or dict.

#### Feature: Failure-safe state load and persist

- **Description**: Malformed-but-valid state JSON and state-dir IO failures must degrade to allow, never disable the gate via an exception.
- **Inputs**: A state file containing valid JSON that is not a dict (e.g. `[]`, `"x"`, `42`); a `STATE_DIR` whose `mkdir`/`mkstemp` raises `OSError`.
- **Outputs**: `load_state` returns a fresh default for a non-dict top level; `save_state` swallows `mkdir`/`mkstemp` `OSError` (the gate still allows; persistence is best-effort).
- **Behavior**: `load_state` already catches `OSError`/`JSONDecodeError` and a non-list `checked`, but a non-dict top-level JSON makes `state.get(...)` raise — guard `isinstance(state, dict)`. In `save_state`, the `STATE_DIR.mkdir(...)` and `tempfile.mkstemp(...)` calls sit OUTSIDE the `try`; move them inside (or guard them) so an IO failure is swallowed like the existing `os.replace` path.

### Capability: Maintainability and carried-over indirection

Refactor debt and one design decision left open by the port. Lowest risk; done last so it reflects the corrected behavior.

#### Feature: Manual-invocation TTY guard (decision)

- **Description**: Restore the source hook's `sys.stdin.isatty()` early return that the `_common.read_input()` swap dropped, so manual terminal invocation does not block on `stdin.read()`.
- **Inputs**: An interactive TTY with no piped stdin.
- **Outputs**: Allow (empty `{}`), no block on read.
- **Behavior**: NOT a runtime regression (Claude Code always pipes JSON). **Decision (recommended)**: add the `isatty()` short-circuit to shared `hooks/_common.py::read_input()` so it returns `{}` on a TTY — this restores gateguard's guard AND improves manual-test ergonomics for all eight hooks, with a small, fail-open blast radius (every hook already treats `{}` as allow). Reject the gateguard-only variant unless the shared change proves problematic.

#### Feature: evaluate() decomposition

- **Description**: Split the 67-line `evaluate()` below the project's 50-line limit with zero behavior change.
- **Inputs**: none (pure refactor).
- **Outputs**: `evaluate()` under 50 lines; per-tool helpers (e.g. `_eval_edit_write`, `_eval_multiedit`, `_eval_bash`).
- **Behavior**: Extract each tool branch into a private helper that returns the deny-JSON-or-None. Behavior is locked by the now-corrected test suite; **no test may change in this feature's task**.

#### Feature: is_read_only_git() removal (verify-then-remove)

- **Description**: Remove `is_read_only_git()` only after proving it changes no verdict.
- **Inputs**: none (pure refactor, contingent on proof).
- **Outputs**: The function and its call site removed, OR kept with a documented rationale if a real edge is found.
- **Behavior**: Its whitelisted read-only forms never match `DESTRUCTIVE_BASH`, so they already fall through to allow. Enumerate the whitelist forms in a test proving each yields the same verdict with the early return removed (including the quoted-substring edge); only then delete it.

#### Feature: State-write concurrency (decision)

- **Description**: Decide how to handle the unlocked read-modify-write in `mark_checked` (load → mutate → atomic replace), where concurrent same-session invocations can clobber each other's `checked` entries.
- **Inputs**: Concurrent gate hits for the same session key.
- **Outputs**: Either a minimal per-session file lock around the read-modify-write, or a documented accepted-limitation note.
- **Behavior**: Real-world risk is minimal — PreToolUse hooks for one session rarely truly race. **Decision (recommended)**: document it as an accepted limitation in the module docstring (the atomic `os.replace` already prevents file corruption; only a lost in-flight mark can occur, which self-heals on the next gate hit). Add a lightweight `fcntl`/lockfile mitigation only if the documented risk is judged unacceptable; justify whichever is chosen.

## Structural Decomposition

### Repository Structure

```
claude-aegis/
├── hooks/
│   ├── _common.py                          # MODIFY: read_input() TTY guard (Feature: TTY guard)
│   ├── gateguard_fact_force.py             # MODIFY: all correctness + robustness + refactor features
│   └── tests/
│       ├── test_gateguard_fact_force.py    # MODIFY: rewrite MultiEdit tests; add regression tests
│       └── test__common.py                 # NEW (if absent): read_input TTY-guard test
├── README.md                               # MODIFY (if wording implies MultiEdit/dd/bash-c are gated today)
└── CHANGELOG.md                            # MODIFY: [Unreleased] entries for the fixes
```

### Module: hooks/gateguard_fact_force.py

- **Maps to capability**: Destructive-action gating correctness; Fail-open robustness; Maintainability
- **Responsibility**: The three-stage DENY → FORCE → ALLOW gate. Carries seven of the nine items (MultiEdit, dd, bash -c, type guards, failure-safe state, evaluate() split, is_read_only_git removal, plus the concurrency decision in its state helpers).
- **Exports**: `main()` (entrypoint). New private helpers from the `evaluate()` split (`_eval_edit_write`, `_eval_multiedit`, `_eval_bash`) stay private. `is_read_only_git` removed (or retained with rationale).

### Module: hooks/_common.py

- **Maps to capability**: Maintainability (TTY guard)
- **Responsibility**: Shared stdin parsing. Gains a `sys.stdin.isatty()` short-circuit in `read_input()` returning `{}` on a TTY.
- **Exports**: `read_input()` (signature unchanged; behavior adds the TTY early return), `block()`, `allow()` (unchanged).

### Module: hooks/tests/test_gateguard_fact_force.py

- **Maps to capability**: all three (the test surface that locks the corrected behavior)
- **Responsibility**: Rewrite the MultiEdit tests to the real payload schema; add regression tests for dd-absolute-path, bash -c, malformed payloads, non-dict state, and state IO failure; enumerate the is_read_only_git whitelist for the removal proof.
- **Exports**: pytest test functions; no public API.

### Module: hooks/tests/test__common.py

- **Maps to capability**: Maintainability (TTY guard)
- **Responsibility**: Assert `read_input()` returns `{}` on a simulated TTY (e.g. patched `isatty`) and still parses piped JSON.
- **Exports**: pytest test functions; created only if no `_common` test file exists.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies — built first. These are the highest-value, security-relevant correctness fixes; doing them first means the later refactor reflects corrected logic.

- **hooks/gateguard_fact_force.py (correctness)**: MultiEdit real-schema gating, dd-absolute-path detection, bash -c quote-aware detection. Each independent of the others.
- **hooks/tests/test_gateguard_fact_force.py (correctness)**: rewritten MultiEdit tests + dd + bash -c regression tests.

### Core Layer (Phase 1)

- **hooks/gateguard_fact_force.py (robustness)**: malformed-payload type guards, failure-safe `load_state`/`save_state`. Depends on [Phase 0] only to avoid editing the same branches twice (logically independent, but sequenced on the same file).
- **hooks/_common.py + hooks/tests/test__common.py**: TTY guard. Depends on [] (independent), grouped here for sequencing.

### Integration Layer (Phase 2)

- **hooks/gateguard_fact_force.py (refactor)**: `evaluate()` decomposition, `is_read_only_git()` verify-then-remove, concurrency decision. Depends on [Phase 0, Phase 1] — refactor must come after all behavior changes so it locks the final behavior and no test churns underneath it.
- **README.md / CHANGELOG.md**: depend on [Phase 0, Phase 1] — describe the corrected behavior.

## Implementation Phases

### Phase 0: Correctness fixes

**Goal**: The gate fires on every destructive action it claims to gate.

**Tasks**:

- [ ] Verify the real MultiEdit payload shape before coding: confirm `tool_input` carries a single top-level `file_path` and `edits` items hold only `old_string`/`new_string` (check the MultiEdit tool spec and/or a captured PreToolUse payload from `~/.claude/projects/*/*.jsonl`). Record the confirmed shape in the task notes (no deps) - Acceptance: the confirmed schema is written down and matches the schema the tests will assert.
- [ ] Rewrite the MultiEdit tests to the real schema, then fix `evaluate()` to read the top-level `file_path` (depends on: previous) - Acceptance: a first-time MultiEdit on an unread file denies and names that file once; prior-Read and working-doc MultiEdit targets allow; `python -m pytest hooks/tests/test_gateguard_fact_force.py -q -k multiedit` is green and the tests fail against the pre-fix hook.
- [ ] Fix the `DESTRUCTIVE_BASH` `dd if=` fragment (no deps) - Acceptance: `dd if=/dev/zero of=/dev/sda` denies AND `dd if=backup.img` still denies; a test covers both the absolute-path and bareword forms.
- [ ] Replace blanket `_strip_quoted` with a shell-parse-aware destructive check (depends on: nothing in this phase, but commit after the dd fix to keep the Bash-branch diff reviewable) - Acceptance: `bash -c "rm -rf /"` denies; `grep -iE 'rm -rf|git reset --hard'` allows; both directions are covered by tests.

**Exit Criteria**: MultiEdit, `dd if=/abs`, and `bash -c` destructive payloads are all gated; the grep false-positive remains allowed; the MultiEdit tests assert the real schema.

### Phase 1: Fail-open robustness

**Goal**: No payload or IO condition can make the hook raise; it always exits 0.

**Tasks**:

- [ ] Add malformed-payload type guards in `evaluate()` and the per-tool branches (depends on: Phase 0) - Acceptance: payloads with non-string `tool_name`, non-dict `tool_input`, non-string `file_path`, and non-string `command` each allow (exit 0, no stdout, no traceback); a parametrized test covers each.
- [ ] Make `load_state` guard a non-dict top-level JSON and make `save_state` swallow `mkdir`/`mkstemp` `OSError` (depends on: Phase 0) - Acceptance: a state file containing `[]`/`"x"`/`42` yields a fresh default (gate still fires correctly); a `STATE_DIR` whose `mkdir` raises results in allow + exit 0; tests cover both (e.g. via `GATEGUARD_STATE_DIR` pointed at an unwritable path).
- [ ] Add the `sys.stdin.isatty()` short-circuit to `_common.read_input()` and test it (depends on: Phase 0) - Acceptance: `read_input()` returns `{}` when `isatty()` is true and still parses piped JSON; `python -m pytest hooks/tests/ -q` (all eight hooks) stays green.

**Exit Criteria**: Every malformed-but-valid-JSON payload and state IO failure allows; the full hooks test suite is green; `read_input()` no longer blocks on a TTY.

### Phase 2: Refactor and decisions

**Goal**: Remove carried-over debt without changing behavior; record the concurrency decision.

**Tasks**:

- [ ] Split `evaluate()` into per-tool private helpers, no behavior change (depends on: Phase 0, Phase 1) - Acceptance: `evaluate()` is under 50 lines; the full `hooks/tests/` suite passes unchanged (no test edits in this task).
- [ ] Prove `is_read_only_git()` redundancy with an enumerating test, then remove it (or keep with a documented rationale) (depends on: Phase 0, Phase 1) - Acceptance: a test enumerates the whitelist read-only git forms and asserts each yields the same verdict with the early return removed; on pass, the function and call site are deleted; coverage stays ≥ 80%.
- [ ] Resolve the state-write concurrency decision: document it as an accepted limitation in the module docstring (recommended), or add a minimal per-session lock; justify the choice in the task notes (depends on: Phase 0, Phase 1) - Acceptance: either the docstring records the limitation and self-healing rationale, or a lock test demonstrates serialized marking; the decision and its justification are written in the commit message.
- [ ] Update README.md (only if its wording implies MultiEdit/dd/bash-c are gated today) and add CHANGELOG.md `[Unreleased]` entries for the fixes (depends on: Phase 0, Phase 1) - Acceptance: CHANGELOG `[Unreleased]` lists the corrected gating under `### Fixed`; README has no claim contradicted by the code.

**Exit Criteria**: `evaluate()` under 50 lines; no dead indirection; concurrency decision recorded; docs match behavior; `python -m pytest hooks/tests/ -q` green with gateguard coverage ≥ 80%.

## Test Strategy

### Critical Scenarios

- **Happy path (MultiEdit gated)**: first-time MultiEdit on an unread file (real schema: top-level `file_path`) → Expected: deny envelope naming that file once; after a prior Read, allow.
- **Edge case (dd absolute path)**: `dd if=/dev/zero of=/dev/sda` → Expected: deny; `dd if=backup.img` → Expected: still deny.
- **Edge case (bash -c vs grep)**: `bash -c "rm -rf /"` → Expected: deny; `grep -iE 'rm -rf|git reset --hard'` → Expected: allow.
- **Error case (malformed payload)**: `tool_name` int, `tool_input` string, `file_path` int, `command` list → Expected: allow + exit 0, no traceback.
- **Error case (state IO)**: non-dict state JSON, and `mkdir`/`mkstemp` raising `OSError` → Expected: allow + exit 0; gate still fires for well-formed state.
- **Refactor invariance**: full `hooks/tests/` suite passes before and after the `evaluate()` split and the `is_read_only_git()` removal with no test changes in those tasks.
- **TTY guard**: `read_input()` on a simulated TTY → Expected: returns `{}` (allow); piped JSON still parses.

## Risks

- **bash -c quote-aware fix regresses the grep false-positive**: the blanket strip exists precisely to allow `grep -iE 'rm -rf|...'`; a naive replacement could re-introduce that false positive or miss the `bash -c` payload. **Mitigation**: lock both directions with tests written first (TDD); treat this as the highest-rework-risk task (`rework_cap: 4`).
- **`_common.read_input()` change blast radius (all eight hooks)**: the TTY guard touches shared infra. **Mitigation**: the change only adds a TTY short-circuit returning `{}`, which every hook already treats as fail-open/allow; test `_common` directly and run the full `hooks/tests/` suite as the gate.
- **`evaluate()` refactor silently changes behavior**: large extractions can drop a branch or reorder a check. **Mitigation**: refactor LAST, after the corrected tests exist; forbid test edits in the refactor task so behavior is locked by the suite.
- **MultiEdit schema assumption is wrong**: the fix is built on the top-level-`file_path` shape. **Mitigation**: Phase 0's first task verifies the real schema against the tool spec / a captured payload before any code changes.
- **Removing `is_read_only_git()` changes a verdict**: an unanticipated command form could rely on the early return. **Mitigation**: verify-then-remove — an enumerating test must prove verdict-equivalence before deletion; keep it with a documented rationale if any edge is found.
