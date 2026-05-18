"""PreToolUse hook (Bash + Monitor): block hand-rolled task-completion poll loops.

Waiting for a background task by polling it in a shell loop (`while`/`until`
+ `sleep`, combined with a `wc`/`stat`/`du` size check, a `*.output` /
`tasks/` path, or a `kill -0` / `pgrep` process-liveness check) is the wrong
technique:

- It is fragile: a slow stream that pauses looks "stable", so the loop
  declares completion early and a truncated result gets read.
- The shell control flow cannot be statically analyzed, so it forces a
  permission prompt that stalls an unattended autopilot run.

The `TaskOutput` tool already does this correctly: it blocks until the
task completes or the deadline and returns status.

Scope is deliberately tight - this catches task-completion polling, not
every loop. Legitimate `Monitor` poll loops (e.g. `while true` polling a
remote API) are not affected.

Policy: aegis/rules/tools.md.
"""

import re

from _common import allow, block, read_input

LOOP_RE = re.compile(r"\b(?:while|until)\b")
SLEEP_RE = re.compile(r"\bsleep\b")
SIZE_POLL_RE = re.compile(r"\bwc\s+-[a-z]|\bstat\s|\bdu\s")
TASK_OUTPUT_RE = re.compile(r"\.output\b|/tasks/")
PROC_POLL_RE = re.compile(r"\bkill\s+-0\b|\bpgrep\b")

MSG = """\
BLOCKED: hand-rolled task-completion poll loop detected.

Polling a background task in a shell loop (`while`/`until` + `sleep`, with a
`wc`/`stat` size check, a `*.output` / `tasks/` path, or a `kill -0` / `pgrep`
process-liveness check) is fragile - a slow stream looks "stable" and you read
a truncated result - and its shell control flow forces a permission prompt
that stalls unattended runs.

Use the TaskOutput tool instead:
  TaskOutput(task_id, block=true, timeout=600000)
It blocks until the task completes or the deadline (600000 ms = 10 min, the max
per call) and returns status. Then Read the task's output file.
Policy: aegis/rules/tools.md."""


def main() -> None:
    data = read_input()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        allow()
    if (
        LOOP_RE.search(cmd)
        and SLEEP_RE.search(cmd)
        and (
            SIZE_POLL_RE.search(cmd)
            or TASK_OUTPUT_RE.search(cmd)
            or PROC_POLL_RE.search(cmd)
        )
    ):
        block(MSG)
    allow()


if __name__ == "__main__":
    main()
