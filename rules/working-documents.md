# Working Documents

The `block_devlocal_redirects.py` hook blocks shell redirects writing into `dev/local/`. Use the Write tool instead.

## dev/local/ section

All self-created working documents go in `dev/local/` in the repo root. Ensure `dev/local/` is in `.gitignore`.

Always use the Write tool for `dev/local/` files, even when the current working directory is elsewhere. Never use Bash shell redirects (`cat >`, `echo >`, `>>`, `>|`, `&>`, `tee`) to write files under `dev/local/`.

## Why

- Write tool gives the model accountability for the file's content (it appears in the transcript).
- Shell redirects bypass content auditing and can introduce quoting bugs that silently corrupt the file.
- The Write tool integrates with permission prompts; shell redirects do not.

## Layout (GC contract)

`dev/local/` is garbage-collected by the **purge-devlocal** skill (buvis dotfiles; trash-first - moves land in `.trash/<date>/` with a manifest and are emptied after 30d). Never hand-delete; run the skill.

The layout is also enforced **at write time** by the user's `~/.claude/hooks/enforce_prd_location.py`: a non-keeper file at root, a new top-level dir, a write into `.trash/`, and a file placed directly in `prds/` all block with a message naming the right home. Getting the layout wrong fails the write rather than quietly creating a GC blind spot.

Place artifacts so the GC can reason about them:

- **`meta/`**: the named keepers - `project-capsule.md`, `decisions.md`, `troubleshooting.md`, `assumptions.md`, `agoge-profile.md`, `ecc-cursor`, `upstream-cursor`. This is their canonical home (moved there 2026-08-23). Read `meta/` first and fall back to the root copy for stores that have not migrated; always write to `meta/`.
- **Root**: directories, plus compat symlinks pointing into `meta/` for the keepers above. The symlinks exist only so plugin releases that predate the move keep resolving, and they retire with `~/.claude` PRD 00139. Nothing else belongs at root - no logs, workspaces, or reports.
- **PRDs** (`prds/`): only the lifecycle subdirs `backlog/`, `wip/`, `hold/`, `done/`. A file directly in `prds/` is blocked.
- **PRD satellites** (`designs/`, `reviews/`, `plans/`): carry the PRD number (`00XXX`) in the filename. Trashed when their PRD reaches `prds/done/` or vanishes; kept while it sits in `backlog/`, `wip/`, or `hold/`.
- **Ephemeral** (`tmp/`): scratch, logs, reviewer outputs, one-off workspaces. PRD-number the filename when known so it dies with the PRD; unnumbered tmp is trashed after 7d while a PRD sits in `prds/wip/`, and after 3d when `wip/` is empty (no loop in flight).
- **`autopilot/`**: loop state and batch reports; trashed after 14d.
- **Curated** (`discovery/`, `specs/`, `notes/`, `walkthroughs/`, `audit-results/`, `spikes/`): never trashed, only flagged when their PRD is gone - the user decides.
- New artifact types: pick an existing dir before inventing one. An unrecognized top-level dir is not kept forever - it ages out after 7d, and the write hook blocks creating one in the first place. A genuinely new keeper gets added to `KEEP_NAMES` in both the hook and the GC before it is used.
