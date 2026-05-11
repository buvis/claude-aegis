# Working Documents

The `block_devlocal_redirects.py` hook blocks shell redirects writing into `dev/local/`. Use the Write tool instead.

## dev/local/ section

All self-created working documents go in `dev/local/` in the repo root. Ensure `dev/local/` is in `.gitignore`.

Always use the Write tool for `dev/local/` files, even when the current working directory is elsewhere. Never use Bash shell redirects (`cat >`, `echo >`, `>>`, `&>`, `tee`) to write files under `dev/local/`.

## Why

- Write tool gives the model accountability for the file's content (it appears in the transcript).
- Shell redirects bypass content auditing and can introduce quoting bugs that silently corrupt the file.
- The Write tool integrates with permission prompts; shell redirects do not.
