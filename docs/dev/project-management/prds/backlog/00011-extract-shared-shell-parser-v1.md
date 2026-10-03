# Extract shared shell parser

## Overview

### Problem Statement

Four aegis hooks parse shell commands, each with a private toolkit that has already diverged (assessment A4+A6, 2026-07-08). The quote-stripping regex is byte-identical in two hooks (`_QUOTED_RE`, gateguard_fact_force.py:54; `QUOTED_RE`, prefer_tools.py:48). Three different separator notions exist: prefer_tools.py:51 splits on `|`, `||`, `&&`, `;`, `$(`, backtick and misses single `&`; block_force_push.py:19 splits shlex tokens on `&&`, `||`, `;`, `|`, `&`; block_devlocal_redirects.py:14 embeds its own separator class `[^\s&|;]` inside REDIRECT_RE. gateguard's Bash path (:103-114) tokenizes with bare `shlex.split` (:106) and no separator awareness. Wrapper peeling exists only in prefer_tools (:57, :60-84). `_common.py` is 43 lines - the shared layer exists but holds none of this.

The divergence has produced live holes and a live false positive:

- `/bin/cat file` is allowed - prefer_tools returns the first token raw (prefer_tools.py:84), never basenamed.
- `sleep 1 & cat file` is allowed - single `&` is not in SEGMENT_RE.
- `timeout 5 grep pat .` is allowed - `timeout` is not in WRAPPERS.
- `git commit -m "block > dev/local/"` is blocked - REDIRECT_RE matches inside a quoted string (assessment A7).

### Target Users

Solo developer maintaining eight hooks; any future hook author who needs shell parsing and must not write a fourth splitter.

### Success Metrics

- Exactly one quote-stripping regex and one separator definition exist under `hooks/` (an rg sweep finds them only in `shell_parse.py`).
- The unified separator set `&&`, `||`, `;`, `|`, `&` (plus `$(` and backtick openers at string level) is locked by parametrized tests.
- All three A6 holes close: `/bin/cat file`, `sleep 1 & cat file`, and `timeout 5 grep pat` are denied by prefer_tools.
- The A7 false positive closes: `git commit -m "block > dev/local/"` is allowed while `echo x > "dev/local/y.md"` stays blocked.
- The entire existing suite stays green - block_force_push and gateguard behavior unchanged.

## Functional Decomposition

### Capability: Canonical shell parsing module

#### Feature: Quoted-span handling

- **Description**: One definition of what counts as quoted shell data.
- **Inputs**: A raw command string.
- **Outputs**: `quoted_spans(command) -> list[tuple[int, int]]` (start/end offsets of each single- or double-quoted span); `strip_quoted(command) -> str`.
- **Behavior**: One module-level regex (today's byte-identical pattern). `strip_quoted` is built on the same regex so the two views can never diverge.

#### Feature: Tokenizing

- **Description**: One shlex entry point with the fail-open convention decided once.
- **Inputs**: A raw command string.
- **Outputs**: `tokenize(command) -> list[str] | None` - None on `ValueError` (unparseable quoting).
- **Behavior**: Callers treat None as not-analyzable and allow, matching today's block_force_push (:89-92) and gateguard (:107-108) stances.

#### Feature: Segmentation on the unified separator set

- **Description**: Split a command into per-command segments; one separator set for everyone.
- **Inputs**: A raw command string (string level) or a token list (token level).
- **Outputs**: `SEPARATORS` constant (`&&`, `||`, `;`, `|`, `&`); `split_segments(command) -> list[str]` (strips quotes, then splits on separators plus `$(`/backtick subshell openers); `split_token_segments(tokens) -> list[list[str]]`.
- **Behavior**: String level serves the regex-based hooks (prefer_tools); token level serves the shlex-based hooks (block_force_push). Both derive from the same SEPARATORS constant so the sets cannot drift again.

#### Feature: First-binary resolution

- **Description**: Resolve the effective binary a segment runs, through paths, env assignments, and wrappers.
- **Inputs**: One segment string.
- **Outputs**: `first_binary(segment) -> str` - basename of the effective first command token, `""` when none.
- **Behavior**: Peel subshell openers, `VAR=value` assignments, and wrappers with their flags. Wrapper set: today's `xargs`, `time`, `nice`, `sudo`, `command`, `env` plus `timeout`, `nohup`, `stdbuf`, `doas`. Wrappers whose flags or positionals take separate-token operands are handled per wrapper (`timeout DURATION`, `nice -n N`). The final token is `os.path.basename`'d so `/bin/cat` resolves to `cat`.

### Capability: Migrations onto the shared module

#### Feature: prefer_tools migration

- **Description**: Replace the hook's private parsing with the shared module; close all three A6 holes.
- **Inputs**: Bash `tool_input.command`.
- **Outputs**: Same deny/allow decisions plus the three newly-denied A6 cases; DENY table and messages unchanged.
- **Behavior**: QUOTED_RE, SEGMENT_RE, SUBSHELL_OPEN_RE, WRAPPERS, and `first_meaningful_token` are deleted in favor of `split_segments` + `first_binary`.

#### Feature: block_force_push migration

- **Description**: Behavior-preserving swap of the parsing plumbing.
- **Inputs**: Bash `tool_input.command`.
- **Outputs**: Identical decisions to today.
- **Behavior**: The local shlex call, SEPARATORS set, and `push_segments` (:64-82) are replaced by `tokenize` + `split_token_segments` + shared `SEPARATORS`. `is_git_token`, `is_force_flag`, and `is_plus_refspec` stay untouched. The existing test file is the lock: it must pass unmodified.

#### Feature: block_devlocal_redirects migration

- **Description**: Stop matching redirect text inside quoted strings (A7) without losing quoted-target detection.
- **Inputs**: Bash `tool_input.command`.
- **Outputs**: Same blocks as today, minus matches that begin inside a quoted span.
- **Behavior**: Keep REDIRECT_RE/TEE_RE, but discard any match whose start offset falls inside a `quoted_spans` span. The quoted-target case (`> "dev/local/x"`) still blocks: the operator sits outside quotes and the existing regex already matches a quoted target.

#### Feature: gateguard Bash-path migration

- **Description**: Point gateguard's destructive-command scan at the shared primitives.
- **Inputs**: Bash `tool_input.command`.
- **Outputs**: Identical decisions to today.
- **Behavior**: Delete `_QUOTED_RE`/`_strip_quoted` (:54-64) and the bare `shlex.split` (:106) in favor of shared `strip_quoted`/`tokenize`. DESTRUCTIVE_BASH, `_find_shell_c_payload`, and all gate semantics untouched.

## Structural Decomposition

### Repository Structure

```
claude-aegis/
├── hooks/
│   ├── shell_parse.py                        # Maps to: canonical module (NEW)
│   ├── prefer_tools.py                       # Maps to: prefer_tools migration (EDIT)
│   ├── block_force_push.py                   # Maps to: force-push migration (EDIT)
│   ├── block_devlocal_redirects.py           # Maps to: devlocal migration (EDIT)
│   ├── gateguard_fact_force.py               # Maps to: gateguard migration (EDIT, imports only)
│   └── tests/
│       ├── test_shell_parse.py               # Maps to: canonical module (NEW)
│       ├── test_prefer_tools.py              # Maps to: A6 regressions (EDIT)
│       └── test_block_devlocal_redirects.py  # Maps to: A7 regression (EDIT)
└── CHANGELOG.md                              # Maps to: release notes (EDIT)
```

### Module: hooks/shell_parse.py

- **Maps to capability**: Canonical shell parsing module
- **Responsibility**: The one place shell commands are quote-stripped, tokenized, segmented, and resolved to a binary. Stdlib only, Python 3.10+, importable from any hook (same directory, like `_common`).
- **Exports**: `SEPARATORS`, `WRAPPERS`, `quoted_spans()`, `strip_quoted()`, `tokenize()`, `split_segments()`, `split_token_segments()`, `first_binary()`.

### Module: hooks/tests/test_shell_parse.py

- **Maps to capability**: Canonical shell parsing module (test surface)
- **Responsibility**: Lock the separator set (parametrized: every separator yields a new segment; quoted separators do not; subshell openers do), wrapper peeling including operand wrappers, basenaming, and tokenize's None-on-ValueError contract.
- **Exports**: pytest test functions; no public API.

## Dependency Graph

External sequencing: land after 00005 (CI) so all four migrations run on the ubuntu/macos x 3.10/3.13 matrix, and after the 00004+00007 gateguard merge to avoid rebasing overlapping edits to gateguard_fact_force.py.

### Foundation Layer (Phase 0)

No dependencies - built first.

- **shell_parse.py + test_shell_parse.py**: pure functions, no hook changes yet; the existing suite stays untouched and green.

### Core Layer (Phase 1)

- **Four hook migrations**: Depend on [shell_parse.py]. Each is an independent edit; prefer_tools and devlocal add fail-first regression tests, force_push and gateguard are behavior-preserving.

### Integration Layer (Phase 2)

- **Duplicate-code sweep + CHANGELOG**: Depends on [Phase 1] - the old private regexes must be gone, not shadowed.

## Implementation Phases

### Phase 0: Foundation

**Goal**: The canonical module exists and its contracts are locked.

**Tasks**:

- [ ] TDD `hooks/shell_parse.py` (no deps) - Acceptance: parametrized tests cover every SEPARATORS member, `$(`/backtick openers, quoted-separator immunity, `first_binary` on `/bin/cat file`, `timeout 5 grep pat`, `nice -n 10 find .`, `LC_ALL=C grep x`, and `tokenize` returning None on an unterminated quote; suite green.

**Exit Criteria**: `python -m pytest hooks/tests/test_shell_parse.py -q` green; existing suite untouched and green.

### Phase 1: Core

**Goal**: All four hooks parse through shell_parse; the A6 and A7 defects are fixed and pinned.

**Tasks**:

- [ ] Write A6 regression tests in test_prefer_tools.py (`/bin/cat f`, `sleep 1 & cat f`, `timeout 5 grep p`) and watch all three fail red (depends on: Phase 0) - Acceptance: three red runs recorded against current code.
- [ ] Migrate prefer_tools.py onto `split_segments` + `first_binary` (depends on: previous) - Acceptance: A6 tests green; every existing prefer_tools test green.
- [ ] Write the A7 regression test in test_block_devlocal_redirects.py (`git commit -m "block > dev/local/"` allowed), watch it fail red, then migrate the hook to quoted-span filtering (depends on: Phase 0) - Acceptance: A7 test green; `echo x > "dev/local/y.md"` and the tee cases still blocked (existing tests green).
- [ ] Migrate block_force_push.py and gateguard's Bash path onto `tokenize`/`split_token_segments`/`strip_quoted` (depends on: Phase 0) - Acceptance: zero test edits needed; full suite green (behavior-preserving refactor locked by existing tests).

**Exit Criteria**: `python -m pytest hooks/tests/ -q` fully green; no hook defines its own quote or separator regex.

### Phase 2: Integration

**Goal**: No duplicated parsing remains; the fixes are released.

**Tasks**:

- [ ] Sweep for leftovers (depends on: Phase 1) - Acceptance: an rg sweep across hooks/ finds the quoted-span pattern and separator definitions only in shell_parse.py; the result is pasted in the task notes.
- [ ] CHANGELOG `### Fixed` entries prefixed `**aegis**:` for the three A6 holes and the A7 false positive (depends on: Phase 1) - Acceptance: entries under [Unreleased]; the extraction itself is refactor and exempt.

**Exit Criteria**: Suite green in CI on the full matrix; CHANGELOG updated.

## Test Strategy

### Critical Scenarios

- **Happy path**: `git status && cat file` → Expected: denied naming `cat` (existing behavior preserved).
- **Edge case**: `sleep 1 & cat file` → Expected: denied (single `&` is now a separator).
- **Edge case**: `/bin/cat file` and `timeout 5 grep pat` → Expected: denied (basename plus wrapper peel).
- **Edge case**: `git commit -m "block > dev/local/"` → Expected: allowed; `echo x > "dev/local/y.md"` → Expected: blocked (quoted target still detected).
- **Edge case**: a force flag inside a quoted commit message on the same line as a plain `git push` → Expected: allowed (token-level segmentation keeps quoted flags inert; existing force-push behavior).
- **Error case**: `echo "unterminated` → Expected: `tokenize` returns None; force_push allows (unchanged stance); prefer_tools' string-level path is unaffected.

## Risks

- **Behavior drift in block_force_push**: the tightest hook gains nothing here and must lose nothing. Mitigation: its migration changes no separator membership (`&` was already present) and keeps token-level semantics; the existing test file must pass unmodified or the migration is wrong.
- **Single-`&` splitting meets the `&>` redirect**: `cmd &> file` string-splits into a `> file` segment. Harmless - `>` is not in the DENY table - but a test pins it so the behavior is chosen, not accidental.
- **shlex keeps unspaced separators glued** (`a&&b` is one token at token level): unchanged from today for force_push; string-level `split_segments` covers the hooks that need finer splitting. Documented in the module docstring.
- **File collisions**: 00004/00007 and 00010 also edit gateguard_fact_force.py. Mitigation: this PRD's gateguard change is import-level only; sequence after the gateguard merge lands; the rebase is mechanical.
