---
rework_cap: 4
---

# Extend gateguard destructive detection (git-discard, eval, find -delete, operator knob)

> **Merge note (2026-07-08 assessment):** this PRD is the union of the *remaining* work from former PRD 00004 and all of former PRD 00007 (now deleted). Both edited the same two functions (`_is_destructive`, `DESTRUCTIVE_BASH`) and the same test file; keeping them separate forced two rebases of identical code. Priority within this PRD: the **git working-tree-discard forms are the highest-value item** (silent data loss) — do them first.
>
> **Already shipped, dropped from scope:** former 00004's Phase 0 (operand-taking option before `-c`, e.g. `bash -O extglob -c "rm -rf /"`) landed as commit `ec970f6`; `bash -O extglob -c "rm -rf /"` is denied today and the "uncommitted red tests in the working tree" that 00004 referenced are stale (tree is clean). This PRD does not re-do it.

## Overview

### Problem Statement

PRD 00002 hardened gateguard (MultiEdit real-schema gating, `bash -c` payload inspection, fail-open guards) and shipped; the operand-flag `-c` bypass shipped separately in `ec970f6`. Four verified destructive-command bypasses remain in `_is_destructive()` / `DESTRUCTIVE_BASH` (`hooks/gateguard_fact_force.py`):

1. **Working-tree-discard git forms (HIGHEST value — silent data loss).** `DESTRUCTIVE_BASH` matches only the literal `git checkout --` prefix, so `git checkout -f`, `git checkout .`, `git checkout -qf`, `git checkout HEAD -- src/x.py`, and every `git switch` discard form (`-f`, `--force`, `--discard-changes`) run ungated and can silently destroy uncommitted work — exactly what the fact-forcing gate exists to interrupt.
2. **`eval` with a quoted payload.** `eval "rm -rf /"` is allowed: `eval` is not in `_SHELL_C_NAMES`, and `_strip_quoted` removes the quoted payload before `DESTRUCTIVE_BASH` runs. (Unquoted `eval rm -rf /` is already caught.)
3. **`find ... -delete`.** Recursive deletion with no `rm` token matches nothing in `DESTRUCTIVE_BASH`. (`find ... -exec rm -rf {} \;` is already caught via the unquoted `rm -rf`.)
4. **No operator extension point.** Adding a project-specific destructive pattern (e.g. `terraform destroy`) means editing hook source; upstream ECC exposes this via an env knob (`4afdb90`).

**Scope philosophy (cap the chase):** gateguard is a fact-forcing speed bump, not a sandbox — **Warden owns command safety**. This PRD closes the verified shell-level bypasses above and adds the operator knob. Interpreter payloads (`python -c`, `perl -e`) stay explicitly out of scope. The git-discard forms are the tier that pays off (data loss); eval/find-delete/knob are a lower tier — do not let this PRD accrete an open-ended bypass hunt.

### Target Users

Solo developer (and any future aegis installer) relying on gateguard to force investigation before destructive Bash. Today several common destructive forms — including two git commands that silently discard uncommitted work — walk through the gate. Also serves an operator who needs to extend the destructive set without forking the hook.

### Success Metrics

- `git checkout -f`, `git checkout .`, `git checkout --force`, `git checkout -qf`, `git checkout HEAD -- src/x.py`, `git switch -f`, `git switch --discard-changes` each return a deny envelope on first hit; `git checkout -b feature`, `git checkout feature`, `git switch main`, `git switch -c new`, and `grep 'git checkout -f'` stay allowed.
- `eval "rm -rf /"`, `eval 'git reset --hard'`, and `find . -delete` each deny on first hit; `eval "echo hi"`, `find . -name '*.tmp'` allow.
- With `GATEGUARD_BASH_EXTRA_DESTRUCTIVE='terraform\s+destroy'`, both `terraform destroy` and `bash -c "terraform destroy"` deny; unset/empty/invalid-regex leaves behavior unchanged and an invalid regex logs exactly one `[gateguard]` stderr warning (fail-open).
- `grep -iE 'rm -rf|git reset --hard'` (the quoted-search false-positive) remains allowed.
- `python -m pytest hooks/tests/ -q` green; gateguard statement coverage stays >= 80%.

## Functional Decomposition

### Capability: Working-tree-discard git gating (priority)

`git checkout` / `git switch` forms that discard uncommitted changes must be gated like `git reset --hard` already is.

#### Feature: git checkout discard forms
- **Description**: Gate every checkout form that discards working-tree changes, not just the literal `git checkout --` prefix.
- **Inputs**: `git checkout -f`, `git checkout .`, `git checkout --force`, `git checkout -qf`, `git checkout HEAD -- src/x.py`, `git checkout -b feature`.
- **Outputs**: Deny for discard forms; allow for branch creation/switching.
- **Behavior**: Mirror upstream `0cb8907` token semantics: after `git checkout`, destructive when any later token is `--`, `.`, or `--force`, or is a short-flag bundle (single `-`) containing `f` (`-f`, `-qf`); `-b`/`--track`/branch names stay allowed. Token-based check inside `_is_destructive` (the token loop already exists for shell `-c` discovery); the `_strip_quoted` search-pattern exemption must keep working.

#### Feature: git switch discard forms
- **Description**: Gate `git switch` parity forms (zero coverage today).
- **Inputs**: `git switch -f main`, `git switch --force main`, `git switch --discard-changes main`, `git switch main`, `git switch -c new`.
- **Outputs**: Deny for `-f`/`--force`/`--discard-changes` (and short bundles containing `f`); allow plain switch and `-c`.
- **Behavior**: Same token check as checkout, applied when the git subcommand is `switch`. `-c`/`-C` branch-creation stay allowed in v1.

### Capability: eval payload inspection

`eval` executes its arguments as shell; quoted payloads must be inspected, not stripped.

#### Feature: eval argument scan
- **Description**: When a token's basename is `eval`, join its remaining arguments and recurse with `_is_destructive`.
- **Inputs**: `eval "rm -rf /"`, `eval 'git reset --hard'`, `eval "echo hi"`.
- **Outputs**: Deny for destructive payloads; allow benign.
- **Behavior**: Mirror the `_SHELL_C_NAMES` recursion; payload is `" ".join(tokens[i+1:])`. Bound recursion the same way the shell `-c` recursion is bounded.

### Capability: find -delete detection

#### Feature: DESTRUCTIVE_BASH find fragment
- **Description**: Add a `find ... -delete` fragment to `DESTRUCTIVE_BASH`.
- **Inputs**: `find . -delete`, `find /tmp/x -name '*.log' -delete`, `find . -name '*.tmp'`.
- **Outputs**: Deny when a `find` segment carries `-delete`; allow plain `find`.
- **Behavior**: Extend the regex with a fragment like `\bfind\s[^|;&]*\s-delete\b` (the `-delete` must belong to the same command segment as the `find`); quoted `-delete` stays exempt via `_strip_quoted`.

### Capability: Operator-extensible destructive patterns

#### Feature: GATEGUARD_BASH_EXTRA_DESTRUCTIVE env knob
- **Description**: Let the operator append destructive patterns via an env var holding a regex, without editing hook source (upstream `4afdb90`).
- **Inputs**: `GATEGUARD_BASH_EXTRA_DESTRUCTIVE` (regex source, compiled case-insensitive); the Bash command under evaluation.
- **Outputs**: Deny when the extra regex matches the same quote-stripped text the built-in patterns see, including inside `bash -c`/`sh -c` payloads; no effect when unset/empty; invalid regex ignored (fail-open) with one `[gateguard]` stderr line.
- **Behavior**: Compile the var at the top of `_is_destructive`; since `_find_shell_c_payload` recursion re-enters `_is_destructive`, payloads are covered with no extra plumbing. The Python hook is one-shot per invocation, so compile-once-per-process is the natural shape (document the divergence from upstream memoization in the module docstring).

## Structural Decomposition

### Repository Structure

```
hooks/
├── gateguard_fact_force.py             # Maps to: all four capabilities (EDIT: _is_destructive, DESTRUCTIVE_BASH)
└── tests/
    └── test_gateguard_fact_force.py    # Maps to: all four capabilities (EDIT)
CHANGELOG.md                            # Maps to: release notes (EDIT)
```

### Module: hooks/gateguard_fact_force.py
- **Maps to capability**: all four.
- **Responsibility**: the destructive-Bash classifier (`_is_destructive`, `DESTRUCTIVE_BASH`).
- **Exports**: `main()` (unchanged); `_is_destructive()` gains the checkout/switch token check, the eval branch, and the extra-regex check (private).

### Module: hooks/tests/test_gateguard_fact_force.py
- **Maps to capability**: all four (test surface).
- **Responsibility**: lock every new deny form, every preserved allow form, the quoted-search exemption, and the env-knob contract (set/unset/invalid, payload recursion, single warning).

## Dependency Graph

### Foundation Layer (Phase 0)
No dependencies — built first. **git checkout/switch discard gating**: closes live data-loss bypasses; pure addition to `_is_destructive`.

### Core Layer (Phase 1)
- **eval scan + find -delete fragment + env knob**: depend on [Phase 0] only for file sequencing (same module); logically independent of each other.

### Integration Layer (Phase 2)
- **CHANGELOG**: depends on [Phase 0, Phase 1].

## Implementation Phases

### Phase 0: Foundation (data-loss first)
**Goal**: No git checkout/switch form that discards uncommitted work passes the gate.

**Tasks**:
- [ ] TDD the checkout discard-form token check (no deps) - Acceptance: deny list (`-f`, `.`, `--force`, `-qf`, `HEAD -- path`, bare `--`) and allow list (`-b feature`, plain branch checkout, quoted `grep 'git checkout -f'`) each have a test; tests fail before the fix, pass after.
- [ ] TDD the switch discard-form check (depends on: previous, same function) - Acceptance: `-f`/`--force`/`--discard-changes` deny; `git switch main` and `git switch -c new` allow.

**Exit Criteria**: `python -m pytest hooks/tests/test_gateguard_fact_force.py -q` green including the new cases.

### Phase 1: Core (lower tier)
**Goal**: eval payloads, `find -delete`, and the operator knob are handled.

**Tasks**:
- [ ] TDD the eval branch in `_is_destructive` (depends on: Phase 0) - Acceptance: `eval "rm -rf /"` and `eval 'git reset --hard'` deny; `eval "echo hi"` allows; deep `eval eval ...` nesting does not crash (exit 0).
- [ ] TDD the `find -delete` regex fragment (depends on: Phase 0) - Acceptance: `find . -delete` and `find /x -name '*.log' -delete` deny; `find . -name '*.tmp'` allows; `grep 'find . -delete'` (quoted) allows.
- [ ] TDD `GATEGUARD_BASH_EXTRA_DESTRUCTIVE` (depends on: Phase 0) - Acceptance: set/unset/empty/invalid contracts covered, including `bash -c` payload recursion and the single `[gateguard]` stderr warning for an invalid regex; hook exits 0 in every case.

**Exit Criteria**: all bypass forms deny; all benign counterparts allow; full `hooks/tests/` suite green.

### Phase 2: Integration
**Goal**: Release notes reflect the corrected gate.

**Tasks**:
- [ ] Add CHANGELOG `[Unreleased]` entries (depends on: Phase 1) - Acceptance: a `### Fixed` entry for the checkout/switch + eval + find-delete bypasses and a `### Added` entry for the env knob, both prefixed `**aegis**:`; README checked for contradicted claims (edit only if one exists).

**Exit Criteria**: CHANGELOG updated; `python -m pytest hooks/tests/ -q` green with gateguard coverage >= 80%.

## Test Strategy

### Critical Scenarios
- **Happy path**: `git checkout -f` → deny on first hit, allow on retry (standard gate cycle).
- **Edge case**: `git checkout -b feature`, `git checkout feature-branch` → allow (`-b` bundle contains no `f`).
- **Edge case**: `git checkout HEAD -- src/x.py` → deny (path-restore discards local changes; stricter than the old prefix regex, intentional).
- **Edge case**: `eval "echo hi"`, `find . -name '*.tmp'` → allow.
- **Edge case**: `GATEGUARD_BASH_EXTRA_DESTRUCTIVE='('` → allow (fail-open), exactly one stderr warning, exit 0.
- **Edge case**: 8-layer nested `bash -c "bash -c ..."` and nested `eval` → exit 0, no traceback.
- **Error case**: `grep -iE 'rm -rf|git reset --hard'`, `grep 'git checkout -f'`, `rg "git switch --discard-changes"` → allow (quoted-search exemption preserved).

## Risks
- **Short-flag bundle over-triggers**: a naive "contains f" check could match long options or branch names. Mitigation: apply the bundle rule only to tokens starting with a single `-` (not `--`); lock with the `-b` allow test.
- **Stricter `HEAD -- path` surprises muscle memory**: previously-allowed commands start denying once. Mitigation: this is the gate working as designed (one fact-presentation, then allow); note it in the CHANGELOG entry.
- **eval / knob recursion blowup**: hostile nesting could recurse deeply. Mitigation: reuse the existing recursion shape; assert exit 0 with a nested-crash test.
- **find fragment false-positives**: `-delete` in a different segment (`find . ; rm -delete-log`) could mis-deny. Mitigation: the fragment excludes segment separators (`[^|;&]*`); add a cross-segment allow test.
- **Bypass-hunt scope creep**: this classifier is undecidable against a determined author. Mitigation: cap at the forms above per the "speed bump, not sandbox; Warden owns safety" philosophy; do not extend without a new PRD.
