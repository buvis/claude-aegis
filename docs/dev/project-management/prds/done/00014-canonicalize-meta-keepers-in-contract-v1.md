# Canonicalize dev/local/meta/ keepers in the working-documents contract

Source: 2026-08-23 `~/.claude` layout change - keepers moved from `dev/local`
root to `dev/local/meta/` (canonical), root now carries compat symlinks only,
and the layout is enforced at write time by the user's
`~/.claude/hooks/enforce_prd_location.py`. The shipped contract prose in
`rules/working-documents.md` still describes the old root-keeper layout.

## Overview

### Problem Statement

`rules/working-documents.md` (the canonical layout contract, v0.3.1) says
"Root: only the named keepers - project-capsule.md, decisions.md, ..." and
"a new top-level dir is kept-but-unclassified forever (a GC blind spot)".
Both statements are now false: keepers live in `dev/local/meta/`, root holds
compat symlinks, foreign top-level dirs age out at 7d, and writes are blocked
at the gate. A contract that misdescribes the enforced layout steers every
session that reads it toward blocked writes.

### Success Metrics

- The shipped rule names `meta/` as the keepers' home, the symlink era, the
  GC horizons (tmp 7d in-flight / 3d idle, foreign 7d, leftover 30d), and the
  write-time enforcement.
- No shipped prose claims new top-level dirs are "kept forever".

## Implementation Phases

### Phase 1: Rewrite and release

1. `rules/working-documents.md` layout section: meta/ keepers (canonical),
   root compat symlinks (retiring via `~/.claude` PRD 00139), updated GC
   horizons, write-time enforcement note.
2. Check `hooks/block_devlocal_redirects.py` prose/messages for root-keeper
   mentions; repoint if any.
3. CHANGELOG entry under `### Changed`.
4. Release and update the installed plugin - a plugin fix is not done until it
   ships (`~/.claude` PRD 00118 precedent).

*Acceptance:* success metrics above; `Tests: none (docs-only)` applies if no
hook code changes.

## Risks

- **Contract drift during the symlink era**: prose must describe BOTH homes
  until 00139 retires the symlinks; write it as canonical-plus-fallback, not
  as two equal options.
