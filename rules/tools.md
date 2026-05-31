# Prefer Tools Over Bash

The `prefer_tools.py` hook blocks Bash commands that invoke `grep`, `find`, `cat`, `head`, or `tail` when a dedicated tool would be cleaner.

## Rule

Any segment of a Bash command that starts with one of these binaries is denied. This applies whether the binary is standalone, inside a pipe, inside a chain (`&&`, `;`), behind `xargs`, or inside `$(...)` / backticks. A denied word inside a quoted string (e.g. in a commit message describing `a | grep b`) is data, not a command, and is allowed.

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

# Don't Hand-Roll Task-Completion Poll Loops

The `block_poll_loops.py` hook denies `Bash` and `Monitor` commands that poll a background task's output file in a shell loop.

## Rule

A command is denied when it combines all of:

- a `while` or `until` loop, and
- a `sleep`, and
- EITHER a process-liveness check (`kill -0`, `pgrep` - the loop waits for a process to die), OR a file poll (a size check `wc -c` / `stat` / `du`, or a `*.output` / `tasks/` path) that carries a completion exit (a `break`, or an `until` condition).

The completion-exit requirement keeps the scope tight. A loop that merely emits a metric every N seconds and never breaks on the polled value (`while true; do du -sh /var; sleep 60; done`) is a live monitor, not a task wait, so it is allowed. Process-liveness loops are inherently completion waits and need no separate exit signal.

That shape is a hand-rolled wait for a background task to finish. It is wrong twice over:

- **Fragile.** A slow stream that pauses mid-output looks "stable", so the loop declares completion early and a truncated result gets read.
- **Stalls autopilot.** The shell control flow cannot be statically analyzed, so it forces a permission prompt - which blocks an unattended run.

## Use instead

`TaskOutput(task_id, block=true, timeout=600000)` blocks until the task completes or the deadline (600000 ms = 10 min, the max per call) and returns status. Then `Read` the task's output file.

The scope is deliberately tight: it catches task-completion polling, not every loop. A legitimate `Monitor` poll loop (`while true` polling a remote API, or emitting a metric with no completion `break`) is not affected.
