# Working Documents

The `block_working_document_redirects.py` hook blocks shell redirects writing
into either development-artifact tree. Use the Write tool instead.

Durable work-management artifacts belong in the tracked
`docs/dev/project-management/` tree: PRDs, plans, reviews, decisions,
discovery, audits, and automation state. Never gitignore this directory.

Temporary assets belong in `docs/dev/tmp/`, which is globally gitignored.
Never put remotely useful project-management records there.

Always use the Write tool for both trees, even when the current working
directory is elsewhere. Never use Bash shell redirects (`cat >`, `echo >`,
`>>`, `>|`, `&>`, `tee`) to write files under them.

## Why

- Write exposes the content in the transcript.
- Shell redirects can silently corrupt quoting or content.
- Write participates in permission and policy hooks.

The user's `~/.claude/hooks/enforce_prd_location.py` enforces the tracked
tree's layout: named keepers in `meta/`, PRDs in
`prds/{backlog,wip,hold,done}/`, and other durable artifacts in an existing
curated directory. `purge-devtmp` garbage-collects only `docs/dev/tmp/`;
it never sweeps tracked project-management records.
