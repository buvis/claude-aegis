# Consolidate aegis PreToolUse hooks into one dispatcher

> Source: 2026-07-14 setup-review walkthrough in the buvis home repo (finding 9).
> Sibling PRD: home `00071-consolidate-hook-dispatchers-v1` does the same for the
> operator's personal hooks. Together: a Bash call drops from 11 interpreter
> spawns to ~4.
> Prior art: everything-claude-code did the same for its 10 PostToolUse hooks
> (sync/async dispatchers, ECC commit 0071fa5c, 2026-07-19): blocking latency
> 81ms -> 49ms median, 10 processes -> 2, even with hooks spawned in parallel
> as the harness does. Validates the approach and the measured-win size.

## Overview

### Problem Statement

aegis registers six separate `python3` hooks on `PreToolUse[Bash]`
(validate_commit_msg, block_devlocal_redirects, prefer_tools, block_poll_loops,
block_force_push, gateguard_fact_force) and three on
`PreToolUse[Edit|Write|MultiEdit]` (protect_config, block_suppression_markers,
gateguard_fact_force). Claude runs each as its own process, so a single Bash
tool call pays six interpreter startups for what is a few hundred microseconds
of actual policy evaluation. On the operator's machine (~100K tool calls per
fortnight) aegis alone is the largest contributor to a measured 0.3-0.9s
per-call hook tax, and every aegis user pays it.

### Target Users

Every aegis user; most acutely operators running unattended loops where the tax
multiplies across ~100K tool calls per fortnight.

### Success Metrics

- `hooks/hooks.json` registers exactly one command per PreToolUse matcher
  (from 6 on Bash and 3 on Edit/Write/MultiEdit).
- Python spawns per gated tool call: 1 (from 6 / 3).
- Zero behavior change: for every payload in the existing suites, the dispatcher
  produces the same decision, same message text, same exit code.
- One broken check never suppresses the others (isolation test).

### Non-Goals

- Changing any policy (what gets blocked). This is a mechanical consolidation.
- Absorbing `rules/tools.md` scar-tissue prose into deny messages (separate idea,
  separate PRD).

## Functional Decomposition

### Capability: Single-process dispatch

#### Feature: PreToolUse dispatcher
- **Description**: `hooks/dispatch.py` reads the payload once and runs every
  check registered for the tool.
- **Inputs**: hook JSON on stdin; a routing table mapping tool-name regex to
  check callables.
- **Outputs**: one aggregated response on stdout; exit 0 or 2.
- **Behavior**: Runs ALL matching checks in the current hooks.json order, never
  short-circuits (parity with Claude running sibling hooks independently). The
  routing table is the single source of truth and mirrors today's matchers.

#### Feature: Checks as importable modules
- **Description**: each of the eight check scripts exposes
  `run(payload: dict) -> tuple[int, str, str]` (exit code, stdout, stderr) while
  keeping its standalone `__main__`.
- **Inputs**: parsed payload dict.
- **Outputs**: the same decision each script produces today.
- **Behavior**: `__main__` becomes a thin `sys.exit(run(read_input()))` wrapper,
  so existing per-script tests and manual pipe-tests keep working unchanged.
  A check without `run()` falls back to subprocess execution (safety net).

#### Feature: Aggregation and isolation
- **Description**: combine per-check results; contain crashes.
- **Inputs**: list of (exit_code, stdout, stderr).
- **Outputs**: single exit code + merged stdout/stderr.
- **Behavior**: any exit 2 makes the final exit 2 and its message is preserved
  verbatim (deny text is the product here - it teaches). JSON stdouts (the
  gateguard `hookSpecificOutput` envelope) merge without losing keys; on
  conflict the earlier check wins and a stderr line names the losing check and
  dropped key, so nothing drops silently. Each check runs in try/except with a
  per-check timeout; a raising check logs a traceback and contributes exit 0.

### Capability: Registration

#### Feature: hooks.json rewiring
- **Description**: replace the nine command entries with one per matcher.
- **Inputs**: `hooks/hooks.json`.
- **Outputs**: PreToolUse `Bash` -> one `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/dispatch.py`;
  PreToolUse `Edit|Write|MultiEdit` -> same; the `Monitor` matcher
  (block_poll_loops) folds into the dispatcher's routing table.
- **Behavior**: `${CLAUDE_PLUGIN_ROOT}` interpolation preserved; timeouts set to
  the max of the folded entries.

## Structural Decomposition

### Repository Structure

```
claude-aegis/
├── hooks/
│   ├── dispatch.py                 # Maps to: PreToolUse dispatcher, Aggregation and isolation
│   ├── hooks.json                  # Maps to: hooks.json rewiring
│   ├── _common.py                  # unchanged (read_input/allow/block)
│   ├── validate_commit_msg.py      # Maps to: Checks as importable modules (gains run())
│   ├── block_devlocal_redirects.py # Maps to: Checks as importable modules
│   ├── prefer_tools.py             # Maps to: Checks as importable modules
│   ├── block_poll_loops.py         # Maps to: Checks as importable modules
│   ├── block_force_push.py         # Maps to: Checks as importable modules
│   ├── gateguard_fact_force.py     # Maps to: Checks as importable modules
│   ├── protect_config.py           # Maps to: Checks as importable modules
│   ├── block_suppression_markers.py# Maps to: Checks as importable modules
│   └── tests/test_dispatch.py      # Maps to: dispatcher + parity tests
└── CHANGELOG.md                    # Changed: one hook process per gated call
```

### Module: dispatch
- **Maps to capability**: Single-process dispatch
- **Responsibility**: route, run, aggregate, isolate
- **Exports**: `main()`, `ROUTES` (matcher regex -> ordered check list)

### Module: checks
- **Maps to capability**: Single-process dispatch
- **Responsibility**: unchanged policy logic, now callable in-process
- **Exports**: `run(payload)` per check module

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies - built first.

- **dispatch**: dispatcher core + aggregation + isolation, tested against stubs

### Core Layer (Phase 1)
- **checks**: Depends on [dispatch] (the `run()` contract)

### Integration Layer (Phase 2)
- **hooks.json rewiring + release**: Depends on [dispatch, checks]

## Implementation Phases

### Phase 0: Foundation
**Goal**: A dispatcher that routes, aggregates, and isolates correctly.

**Tasks**:
- [ ] `hooks/dispatch.py` + `tests/test_dispatch.py` against stub checks (no deps) -
  Acceptance: tests cover block propagation (one stub exits 2 -> final exit 2,
  message verbatim), JSON-envelope merge (a key conflict emits the stderr
  warning naming the losing check), crash isolation (raising stub logged,
  siblings still run), routing (a Bash payload runs exactly the six Bash checks;
  a Read payload runs none).
- [ ] Subprocess fallback for a check lacking `run()` (no deps) - Acceptance: a
  run()-less fixture script still executes with identical exit code and stdout.

**Exit Criteria**: dispatcher suite green; fallback proven.

### Phase 1: Core
**Goal**: All eight checks callable in-process, provably identical.

**Tasks**:
- [ ] Add `run(payload)` to the eight checks, keeping standalone `__main__`
  (depends on: Phase 0) - Acceptance: per check, a parity test feeds the same
  recorded payloads to the subprocess path and to `run()`; exit code, stdout,
  and stderr identical. Existing per-check suites stay green with zero skips
  (report skip counts).

**Exit Criteria**: parity proven for all eight; full suite green.

### Phase 2: Integration
**Goal**: One process per gated call, released.

**Tasks**:
- [ ] Rewire `hooks/hooks.json` (depends on: Phase 1) - Acceptance:
  `jq '[.hooks.PreToolUse[].hooks[]] | length'` returns 2 (one per matcher);
  a live pipe-test of a destructive Bash payload still denies with the gateguard
  fact list, and a `head`-piped payload still denies with the prefer_tools message.
- [ ] Release minor via `dev/bin/release minor` with a CHANGELOG entry under
  Changed (depends on: rewiring) - Acceptance: release published; CHANGELOG names
  the spawn reduction (6 -> 1 per Bash call) and the isolation guarantee.

**Exit Criteria**: Success Metrics all verifiably true.

## Test Strategy

### Critical Scenarios
- **Happy path**: `ls -la` payload -> all six Bash checks run, all allow, exit 0 →
  Expected: byte-identical outcome to six standalone runs.
- **Edge case**: `rm -rf` payload -> gateguard denies while other checks allow →
  Expected: exit 2, gateguard's fact-list message intact, no check skipped.
- **Error case**: one check raises (simulated) → Expected: traceback logged,
  remaining checks still evaluated, decision reflects only the survivors.

## Risks

- **Semantics drift vs native multi-hook behavior**: recorded-payload parity tests
  per check + the run-all/no-short-circuit rule.
- **One process, one crash surface**: per-check try/except and timeouts are Phase 0
  acceptance criteria, not a later hardening pass.
- **Adjacent PRDs touching the same files**: 00011 (shared shell parser) and 00009
  (hook dry-run harness) overlap these modules; whichever lands second rebases on
  the first - the `run()` contract is additive and does not conflict with either.
