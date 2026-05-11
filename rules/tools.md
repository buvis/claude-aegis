# Prefer Tools Over Bash

The `prefer-tools.py` hook blocks Bash commands that invoke `grep`, `find`, `cat`, `head`, or `tail` when a dedicated tool would be cleaner.

## Rule

Any segment of a Bash command that starts with one of these binaries is denied. This applies whether the binary is standalone, inside a pipe, inside a chain (`&&`, `;`), behind `xargs`, or inside `$(...)` / backticks.

| Bash command | Use instead | Why |
|---|---|---|
| `cat file` | `Read` (or pass the filename directly: `jq '...' file`) | Returns line-numbered output, respects size limits |
| `head -n file` / `tail -n file` | `Read` with `offset` / `limit` | Same |
| `grep -r pattern path` | `Grep` (supports `head_limit`, `output_mode`, glob filters) | Faster, respects ignores, structured output |
| `find path -name "*.x"` | `Glob` | Designed for filename patterns |

Pipe patterns have first-class replacements:

- `grep ... | head` → `Grep` with `head_limit`
- `cat file | jq '...'` → `jq '...' file`
- `find ... | xargs y` → `Glob`, then call `y` per file

`rg` for ad-hoc shell recon is allowed (faster than grep, respects `.gitignore`). For code search inside the model, prefer `Grep`.
