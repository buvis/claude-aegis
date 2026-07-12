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

`dev/local/` is garbage-collected by the **purge-devlocal** skill (buvis dotfiles; trash-first - moves land in `.trash/<date>/` with a manifest and are emptied after 30d). Never hand-delete; run the skill. Place artifacts so the GC can reason about them:

- **Root**: only the named keepers - `project-capsule.md`, `decisions.md`, `troubleshooting.md`, `assumptions.md`, `ecc-cursor`, `upstream-cursor`. No logs, workspaces, or reports at root.
- **PRD satellites** (`designs/`, `reviews/`, `plans/`): carry the PRD number (`00XXX`) in the filename. Trashed when their PRD reaches `prds/done/` or vanishes; kept while it sits in `backlog/` or `wip/`.
- **Ephemeral** (`tmp/`): scratch, logs, reviewer outputs, one-off workspaces. PRD-number the filename when known so it dies with the PRD; unnumbered tmp is trashed after 7d.
- **`autopilot/`**: loop state and batch reports; trashed after 14d.
- **Curated** (`discovery/`, `specs/`, `notes/`, `walkthroughs/`, `audit-results/`, `spikes/`): never trashed, only flagged when their PRD is gone - the user decides.
- New artifact types: pick an existing dir before inventing one; a new top-level dir is kept-but-unclassified forever (a GC blind spot).
