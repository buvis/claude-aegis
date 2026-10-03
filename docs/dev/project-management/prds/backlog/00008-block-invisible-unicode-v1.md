# Block invisible Unicode in written content

## Overview

### Problem Statement

Invisible and format Unicode code points can smuggle instructions or content past human review: the Unicode Tag block (U+E0000-U+E007F) is the canonical "ASCII smuggling" prompt-injection vector, and bidi controls, zero-width characters, and zero-width fillers serve homograph and hidden-text attacks. ECC added a CI-side check for these (commits `e3483fd`, `b068069`, reviewed 2026-06-09 via /catchup-ecc). Aegis has no equivalent guard at write time: gateguard sanitizes bidi controls only in the file paths of its own messages, and nothing inspects the content the agent writes into files. A poisoned source (web page, dependency README, pasted snippet) can flow invisibly into the repo through Edit/Write.

### Target Users

Solo developer whose agent regularly writes content derived from external sources, and any future aegis installer wanting write-time protection against invisible-character smuggling.

### Success Metrics

- A Write/Edit/MultiEdit whose new content contains any blocked code point is denied with a message naming each offending code point (U+ hex, Unicode name, line number).
- Clean content, emoji sequences using ZWJ/variation selectors, and a UTF-8 BOM as the very first character of a Write are all allowed.
- Malformed payloads (non-string content, non-dict input) allow - the hook never crashes a tool call.
- `python -m pytest hooks/tests/ -q` green; new hook statement coverage >= 80%.

## Functional Decomposition

### Capability: Invisible code point detection

#### Feature: Blocked-set scan of written content

- **Description**: Scan all content a tool call would write for dangerous invisible code points.
- **Inputs**: PreToolUse payloads - `Write.tool_input.content`, `Edit.tool_input.new_string`, `MultiEdit.tool_input.edits[].new_string`.
- **Outputs**: Block (exit 2 via `_common.block()`, matching the other `block_*` hooks) when any blocked code point is present; allow otherwise.
- **Behavior**: Single pass over each content string. Blocked set (from ECC's `check-unicode-safety.js`, minus emoji-legitimate points):
  - U+E0000-U+E007F (Tag block - deprecated, injection vector)
  - U+202A-U+202E and U+2066-U+2069 (bidi embedding/override/isolate controls)
  - U+200B (zero-width space), U+200C (zero-width non-joiner), U+2060 (word joiner)
  - U+FEFF (zero-width no-break space), except as the very first character of `Write.content` (legitimate BOM)
  - U+180E (Mongolian vowel separator), U+115F/U+1160/U+3164 (Hangul fillers), U+2061-U+2064 (invisible math operators)
  Excluded in v1, documented in the module docstring: U+200D (ZWJ) and variation selectors U+FE00-U+FE0F / U+E0100-U+E01EF - both are legitimate in emoji sequences and blocking them would false-positive on ordinary docs. Revisit only if a real smuggling case using them appears.

### Capability: Actionable deny reporting

#### Feature: Per-violation block message

- **Description**: The block message tells the agent exactly what to remove and where.
- **Inputs**: The list of detected violations (code point, offset) per content field.
- **Outputs**: A block message with one line per violation: `U+XXXX <UNICODE NAME> at line N` (name via `unicodedata.name()`, fallback `<unnamed>`), capped at 10 lines plus a `... and N more` tail, ending with "Remove the invisible characters and retry."
- **Behavior**: Compute line numbers by counting `\n` up to each offset. Cap output so a pathological payload cannot flood the transcript.

### Capability: Fail-open robustness

#### Feature: Malformed-payload guards

- **Description**: Valid JSON with unexpected types must allow, never raise.
- **Inputs**: Payloads with non-string `content`/`new_string`, non-list `edits`, non-dict `tool_input`.
- **Outputs**: Allow + exit 0 for every such payload.
- **Behavior**: Type-guard each field before scanning; reuse `_common.read_input()` for stdin parsing (it already handles bad JSON and TTY).

## Structural Decomposition

### Repository Structure

```
claude-aegis/
├── hooks/
│   ├── block_invisible_unicode.py              # Maps to: all three capabilities (NEW)
│   ├── hooks.json                              # Maps to: registration (EDIT)
│   └── tests/
│       └── test_block_invisible_unicode.py     # Maps to: all three capabilities (NEW)
├── README.md                                   # Maps to: hook inventory (EDIT)
└── CHANGELOG.md                                # Maps to: release notes (EDIT)
```

### Module: hooks/block_invisible_unicode.py

- **Maps to capability**: Invisible code point detection; Actionable deny reporting; Fail-open robustness
- **Responsibility**: Detect blocked invisible code points in to-be-written content and block with a per-violation report.
- **Exports**:
  - `main()` - entrypoint
  - `find_violations(text: str, bom_exempt: bool) -> list` - pure detection helper (unit-test surface)

### Module: hooks/tests/test_block_invisible_unicode.py

- **Maps to capability**: all three (test surface)
- **Responsibility**: Lock the blocked set, the exclusions (ZWJ emoji, BOM), the message format, and fail-open behavior.
- **Exports**: pytest test functions; no public API.

## Dependency Graph

### Foundation Layer (Phase 0)

No dependencies - built first.

- **find_violations + blocked set**: pure function, fully unit-testable.

### Core Layer (Phase 1)

- **main() routing + reporting**: Depends on [find_violations].

### Integration Layer (Phase 2)

- **hooks.json registration, README, CHANGELOG**: Depends on [Phase 0, Phase 1].

## Implementation Phases

### Phase 0: Foundation

**Goal**: Detection is correct and locked by tests.

**Tasks**:

- [ ] TDD `find_violations` over the blocked set (no deps) - Acceptance: one parametrized test per blocked range/point denies; ZWJ emoji sequence (e.g. family emoji), VS16 emoji, plain ASCII, and BOM-at-offset-0 with `bom_exempt=True` all yield no violations; U+FEFF mid-string yields one.

**Exit Criteria**: `python -m pytest hooks/tests/test_block_invisible_unicode.py -q` green.

### Phase 1: Core

**Goal**: The hook blocks real payloads with an actionable message and never crashes.

**Tasks**:

- [ ] TDD `main()` for Write/Edit/MultiEdit payloads (depends on: Phase 0) - Acceptance: Write content with a Tag-block char blocks (exit 2) and the message contains `U+E0041` and the line number; MultiEdit scans every `new_string`; clean payloads allow with exit 0.
- [ ] TDD fail-open guards and message cap (depends on: Phase 0) - Acceptance: non-string/non-dict/non-list field payloads each allow + exit 0; 50 violations produce a 10-line report plus a `... and 40 more` tail.

**Exit Criteria**: Full `hooks/tests/` suite green; new hook coverage >= 80%.

### Phase 2: Integration

**Goal**: The hook is registered and documented.

**Tasks**:

- [ ] Register in `hooks/hooks.json` under PreToolUse matcher `Edit|Write|MultiEdit` (depends on: Phase 1) - Acceptance: entry matches the structure of the existing `block_*` registrations; a manual pipe test (`echo '<payload>' | python3 hooks/block_invisible_unicode.py`) blocks and allows as expected.
- [ ] README hook inventory + CHANGELOG `### Added` entry prefixed `**aegis**:` (depends on: previous) - Acceptance: README lists the hook with its blocked-set summary and the documented ZWJ/VS exclusion; CHANGELOG entry present.

**Exit Criteria**: Hook live in hooks.json; docs and CHANGELOG match behavior; suite green.

## Test Strategy

### Critical Scenarios

- **Happy path**: Write with `"plain ascii text"` → Expected: allow, exit 0.
- **Happy path (block)**: Write content containing U+E0041 → Expected: exit 2, message names `U+E0041` with line number.
- **Edge case**: content with 👨‍👩‍👧 (ZWJ sequence) and ❤️ (VS16) → Expected: allow (documented exclusion).
- **Edge case**: U+FEFF as first char of Write content → Expected: allow; same char mid-string or in an Edit `new_string` → Expected: block.
- **Error case**: `tool_input` is a string, `edits` is a dict, `new_string` is an int → Expected: allow + exit 0, no traceback.

## Risks

- **False positives on legitimate non-Latin text**: U+200C (ZWNJ) is meaningful in Persian/Arabic typography. Mitigation: accepted for v1 (this user writes Latin-script content); the exclusion list is a single named constant, easy to extend; documented in README.
- **Blocked set drifts from upstream ECC additions**: future ECC commits may add code points. Mitigation: /catchup-ecc reviews flag changes to `check-unicode-safety.js`; the set is one constant to update.
- **Hook latency on large writes**: scanning is O(n) single-pass over content already in memory. Mitigation: none needed beyond the design; no regex backtracking.
