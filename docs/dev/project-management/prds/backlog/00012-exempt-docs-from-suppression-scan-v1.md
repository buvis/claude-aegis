# Exempt working docs from the suppression-marker scan

## Overview

### Problem Statement

`block_suppression_markers.py` scans every Edit/Write/MultiEdit regardless of target file type: `count_markers` (:33-41) applies SUPPRESSION_PATTERNS to any text, and `main` (:55-93) never inspects the file's extension (it reads `file_path` only to diff old Write content). Prose that merely names a marker therefore blocks: a doc line quoting Python's hash-prefixed noqa comment or JS's double-slash eslint-disable comment counts as an "added suppression". This is a pure false positive - no linter runs on `.md`/`.rst`/`.txt`, so a marker string in prose suppresses nothing. Live proof (assessment A2, 2026-07-08): writing the evolution assessment itself was blocked because one table row named the markers, and aegis's own `rules/coding-style.md` - the policy document for this very hook - names them too, so editing it is blocked. Gateguard already answers the "is this a working doc" question with `_WORKING_DOC_EXTENSIONS` (gateguard_fact_force.py:133: `.md`/`.markdown`/`.txt`/`.rst`); this hook should reuse that answer, not grow a second one. Severity MED for annoyance frequency, LOW risk.

Alternative considered and rejected: anchoring the patterns to line starts. Real suppressions sit mid-line as trailing comments, so anchoring would miss genuine additions in code while still blocking docs whose fenced examples start a line with a marker.

### Target Users

Solo developer writing assessments, PRDs, and rules files that discuss linting policy; any aegis installer editing prose in a repo with the hook active.

### Success Metrics

- Editing or writing a `.md`/`.markdown`/`.txt`/`.rst` file whose new content names suppression markers is allowed (exit 0).
- The same new content targeting a `.py` file still blocks (exit 2) naming the marker.
- The working-doc extension tuple has exactly one definition, in `_common.py`, imported by both gateguard and this hook.
- The regression test fails against current code (blocked) and passes after; `python -m pytest hooks/tests/ -q` fully green.

## Functional Decomposition

### Capability: Shared working-doc extension constant

#### Feature: Hoist the tuple into _common

- **Description**: One definition of "working-doc extension" for the whole plugin.
- **Inputs**: The existing tuple at gateguard_fact_force.py:133.
- **Outputs**: `WORKING_DOC_EXTENSIONS = (".md", ".markdown", ".txt", ".rst")` exported from `hooks/_common.py`.
- **Behavior**: gateguard imports it aliased to the current private name so its call site (:333) stays unchanged. Pure move - zero behavior change in gateguard, locked by its existing tests.

### Capability: Doc exemption in the suppression hook

#### Feature: Extension gate before scanning

- **Description**: Allow immediately when the target file is a working doc.
- **Inputs**: `tool_input.file_path` (present in Edit, Write, and MultiEdit payloads).
- **Outputs**: Allow (exit 0) for working-doc extensions; the unchanged scan otherwise.
- **Behavior**: In `main()` before the per-tool dispatch (:62): if `file_path` is a string and `file_path.lower().endswith(WORKING_DOC_EXTENSIONS)`, allow. A missing or non-string `file_path` keeps today's conservative path: scan. Markers added to docs are inert for linters, so the exemption opens no enforcement hole.

## Structural Decomposition

### Repository Structure

```
claude-aegis/
├── hooks/
│   ├── _common.py                                # Maps to: shared constant (EDIT)
│   ├── gateguard_fact_force.py                   # Maps to: shared constant (EDIT, import alias)
│   ├── block_suppression_markers.py              # Maps to: extension gate (EDIT)
│   └── tests/
│       └── test_block_suppression_markers.py     # Maps to: both capabilities (EDIT)
├── README.md                                     # Maps to: hook table scope note (EDIT)
└── CHANGELOG.md                                  # Maps to: release notes (EDIT)
```

### Module: hooks/_common.py

- **Maps to capability**: Shared working-doc extension constant
- **Responsibility**: Unchanged (shared hook helpers); gains one documented constant.
- **Exports**: existing `read_input`/`block`/`allow` plus `WORKING_DOC_EXTENSIONS`.

### Module: hooks/block_suppression_markers.py

- **Maps to capability**: Doc exemption in the suppression hook
- **Responsibility**: Unchanged for code files; working docs exit early.
- **Exports**: `main()`, `count_markers()`, `diff_added()` - signatures unchanged.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **Constant hoist + gateguard alias**: pure refactor; the existing suite is the lock.

### Core Layer (Phase 1)

- **Extension gate + regression tests**: Depends on [constant hoist].

### Integration Layer (Phase 2)

- **README + CHANGELOG**: Depends on [Phase 1].

## Implementation Phases

### Phase 0: Foundation

**Goal**: One shared definition of working-doc extensions.

**Tasks**:

- [ ] Move the tuple to `_common.WORKING_DOC_EXTENSIONS`; import it in gateguard under the existing private alias (no deps) - Acceptance: full suite green with zero test edits; one new test asserts gateguard's alias IS the `_common` constant (pins the reuse).

**Exit Criteria**: `python -m pytest hooks/tests/ -q` green.

### Phase 1: Core

**Goal**: Docs pass; code files stay guarded.

**Tasks**:

- [ ] Write the regression test - an Edit payload targeting `notes.md` whose new_string names markers (build fixture strings with the existing `marker()` helper, test_block_suppression_markers.py:22) - and watch it fail red against current code (depends on: Phase 0) - Acceptance: red run recorded (currently exit 2).
- [ ] Add the extension gate in `main()` (depends on: previous) - Acceptance: regression test green; matrix green: identical content to `app.py` blocks; `NOTES.TXT` (uppercase) allows; MultiEdit on `README.markdown` allows; Write without `file_path` but with marker-bearing content still blocks.

**Exit Criteria**: Full suite green.

### Phase 2: Integration

**Goal**: Documented and released.

**Tasks**:

- [ ] Update the README hook table row for this hook to say it scans code files only, with working docs (`.md`/`.markdown`/`.txt`/`.rst`) exempt (depends on: Phase 1) - Acceptance: the row matches behavior.
- [ ] CHANGELOG `### Fixed` entry prefixed `**aegis**:` (docs naming lint-suppression markers are no longer blocked) (depends on: Phase 1) - Acceptance: entry under [Unreleased].

**Exit Criteria**: Suite green; docs match behavior.

## Test Strategy

### Critical Scenarios

- **Happy path (regression)**: Edit to `docs/notes.md` adding a sentence that names the hash-prefixed noqa marker → Expected: allow, exit 0 (fails red before the fix).
- **Happy path (still guarded)**: identical new_string targeting `app.py` → Expected: exit 2, message names the marker.
- **Edge case**: Write to `NOTES.TXT` → Expected: allow (case-insensitive extension match).
- **Edge case**: MultiEdit on `README.markdown` with a marker-naming edit → Expected: allow.
- **Error case**: Write payload with no `file_path` and marker-bearing content → Expected: block (conservative default unchanged).

## Risks

- **Markers inside doc code fences are never flagged**: accepted - linters do not run on prose, so nothing is suppressed. Noted in the README row.
- **gateguard file collision**: 00004/00007, 00010, and 00011 also edit gateguard_fact_force.py; this PRD's gateguard change is one import line. Mitigation: mechanical rebase whichever lands first.
- **Writing the tests trips this very hook**: fixture strings containing literal markers would block the implementing session's own Write into the test file. Mitigation: the existing `marker()` helper (test_block_suppression_markers.py:22) builds markers by concatenation; all new fixtures must use it.
