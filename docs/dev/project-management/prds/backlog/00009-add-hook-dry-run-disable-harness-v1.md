# Add A Dry-Run And Selective-Disable Harness For Python Hooks

> Source: ECC catchup 2026-06-19. Adapts ECC's `scripts/lib/hook-flags.js` (`ECC_DRY_RUN`, `ECC_DISABLED_HOOKS`, profiles) to the Python-hook rule.
> Target repo: **aegis** plugin (owns most of the user's Python hooks); the shared helper is usable by any `~/.claude` Python hook.

## Overview

### Problem Statement
The user runs many Python hooks across plugins (aegis: `block-suppression-markers`, `protect_config`, `prefer_tools`, `block_devlocal_redirects`, `validate_commit_msg`; plus global `~/.claude/hooks`). There is no way to (a) see what a hook **would** decide for a given tool call without it actually blocking, or (b) temporarily disable one misbehaving hook without editing `settings.json` and reloading. `/warden:yolo` bypasses warden only. Debugging a hook today means editing it or `settings.json`, triggering it live, and reverting - slow and error-prone for a hook-heavy setup.

ECC solved this with a JS dispatcher; the Python equivalent is a tiny shared module each hook imports, gating the existing exit-2-block convention behind two env vars.

### Target Users
The maintainer debugging or iterating on hooks. (Hooks must be Python per the global rule - see `~/.claude/CLAUDE.md` and `feedback_hooks_python_only`.)

### Success Metrics
- `BUVIS_HOOK_DRY_RUN=1` makes any adopting hook print `[DryRun] <hook-id> would <decision>: <reason> (tool=…, target=…)` to stderr and exit 0 - no block, no side effects.
- `BUVIS_DISABLED_HOOKS=hook-a,hook-b` makes the named hooks pass through (exit 0) without running their logic.
- One shared `hook_flags.py`; each aegis hook adopts it in ≤3 lines; behavior is unchanged when neither env var is set.
- A self-check covers the dry-run, disabled, and normal paths.

### Non-Goals
- Third-party hooks (`context-mode`) and the TypeScript `warden` binary will not adopt this helper. Warden keeps its own `/warden:yolo`. Coverage = the set of hooks that adopt `emit()`.
- A profile system (`minimal`/`standard`/`strict`). YAGNI for one user; add later only if hook tiers become real.

## Functional Decomposition

### Capability: Hook execution control
Intercept a hook's decision before it takes effect.

#### Feature: Flag reader
- **Description**: Shared helpers for the two env vars.
- **Inputs**: env (`BUVIS_HOOK_DRY_RUN`, `BUVIS_DISABLED_HOOKS`).
- **Outputs**: `is_dry_run() -> bool`, `disabled_hooks() -> set[str]`, `is_disabled(hook_id) -> bool`.
- **Behavior**: pure env reads; empty/absent → falsey.

#### Feature: Decision gate
- **Description**: `emit(decision, reason, *, hook_id, ctx)` - the single exit point hooks call instead of exiting 2 directly.
- **Inputs**: intended decision (`block`/`allow`/`ask`), reason, parsed hook-stdin ctx (tool, target/command).
- **Outputs**: under dry-run → stderr preview + `exit 0`; disabled → stderr warning + `exit 0`; else → the real effect (`exit 2` to block, or the harness JSON / `exit 0`).
- **Behavior**: centralizes the exit-2-block convention (consistent with `reference_hook_permission_decision`: prefer exit-2 block) so dry-run can intercept one place.

#### Feature: Hook adoption
- **Description**: Each aegis hook computes its decision, then routes the block through `emit(...)` with a stable `hook_id`.
- **Inputs**: existing per-hook logic.
- **Outputs**: identical blocking behavior with neither env var set.
- **Behavior**: a 3-line change per hook (import, derive `ctx`, call `emit`).

## Structural Decomposition

### Repository Structure (aegis repo)

```
hooks/
├── lib/
│   └── hook_flags.py         # NEW: readers + emit()
├── block_suppression_markers.py   # adopt emit()
├── protect_config.py              # adopt emit()
├── prefer_tools.py                # adopt emit()
├── block_devlocal_redirects.py    # adopt emit()
├── validate_commit_msg.py         # adopt emit()
└── tests/
    └── test_hook_flags.py    # dry-run / disabled / normal
```

### Module: hook_flags
- **Maps to capability**: Hook execution control.
- **Responsibility**: Read flags; gate the block decision; format the dry-run preview.
- **Exports**: `is_dry_run`, `disabled_hooks`, `is_disabled`, `emit`.

## Dependency Graph

### Foundation Layer (Phase 0)
- **hook_flags + tests**: No dependencies. Helper + self-check.

### Core Layer (Phase 1)
- **aegis hooks**: Depend on [hook_flags]. Adopt `emit()` at each block point.

### Integration Layer (Phase 2)
- **docs**: Depend on [aegis hooks]. README documents the two env vars and which hooks honor them.

## Implementation Phases

### Phase 0: Foundation
**Goal**: The helper exists and is proven.

**Tasks**:
- [ ] Write `hooks/lib/hook_flags.py` with `is_dry_run`, `disabled_hooks`, `is_disabled`, `emit` (no deps) - Acceptance: `emit('block', …)` exits 2 normally; exits 0 with a preview under `BUVIS_HOOK_DRY_RUN=1`; exits 0 with a warning when the id is in `BUVIS_DISABLED_HOOKS`.
- [ ] `test_hook_flags.py` covering all three paths (depends on: helper) - Acceptance: tests green (no framework beyond the repo's existing test runner).

**Exit Criteria**: Helper + self-check green.

### Phase 1: Core
**Goal**: aegis hooks route blocks through `emit()`.

**Tasks**:
- [ ] Adopt `emit()` in each of the five aegis hooks with a stable `hook_id` (depends on: Phase 0) - Acceptance: with neither env var set, each hook blocks exactly as before (existing hook behavior tests green); `BUVIS_DISABLED_HOOKS=<id>` makes that one pass through.

**Exit Criteria**: All aegis hooks honor both flags; zero behavior change in the default (no-flag) case.

### Phase 2: Integration
**Goal**: Make the controls discoverable.

**Tasks**:
- [ ] Document `BUVIS_HOOK_DRY_RUN` and `BUVIS_DISABLED_HOOKS` in the aegis README, listing the hook ids that honor them (depends on: Phase 1) - Acceptance: README lists every adopting hook id.

**Exit Criteria**: Env vars documented with the authoritative hook-id list.

## Test Strategy

### Critical Scenarios
- **Dry-run**: a hook that would block → with `BUVIS_HOOK_DRY_RUN=1` exits 0, prints `[DryRun] … would block: …`, the tool call is not blocked.
- **Disabled**: `BUVIS_DISABLED_HOOKS=<id>` → that hook exits 0 without running its logic and warns on stderr.
- **Normal**: neither var set → blocks as before (exit 2).
- **Preview content**: includes `hook_id`, decision, `tool`, and `target`/`command`.
- **Unknown id in disabled list**: ignored; other hooks unaffected.

## Risks

- **Partial coverage reads as full**: only adopting hooks honor the flags; a non-adopting hook still fires under dry-run. Mitigation: `emit()` adoption is the coverage unit; README lists adopters; never claim global dry-run.
- **Disable footgun**: disabling `protect_config` or `prefer_tools` silently weakens safety. Mitigation: `emit()` prints a stderr warning on **every** disabled-hook run.
- **Stray flag leaks enforcement off**: a lingering `BUVIS_HOOK_DRY_RUN=1` disables blocking everywhere. Mitigation: loud per-run stderr warning; document as a debug-only, per-invocation flag (do not export in a shell profile).
