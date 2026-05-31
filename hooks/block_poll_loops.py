"""PreToolUse hook (Bash + Monitor): block hand-rolled task-completion poll loops.

Waiting for a background task by polling it in a shell loop is the wrong
technique:

- It is fragile: a slow stream that pauses looks "stable", so the loop
  declares completion early and a truncated result gets read.
- The shell control flow cannot be statically analyzed, so it forces a
  permission prompt that stalls an unattended autopilot run.

The `TaskOutput` tool already does this correctly: it blocks until the
task completes or the deadline and returns status.

What counts as the antipattern (all must hold):

- a `while`/`until` loop, and
- a `sleep`, and
- EITHER a process-liveness loop (`kill -0` / `pgrep` - the loop waits for a
  process to die), OR a file poll (`wc`/`stat`/`du`, a `*.output` / `tasks/`
  path) that carries a completion exit (a `break`, an `until` loop, or a
  conditional `while` header such as `while [ ! -s out ]`).

The completion-exit requirement is what keeps the scope tight: a `while true;
do du -sh /var; sleep 60; done` style metric/monitor loop never breaks on the
polled value, so it is a legitimate Monitor pattern, not a task wait, and is
left alone. Process-liveness loops are inherently completion waits, so they
need no separate exit signal.

Policy: aegis/rules/tools.md.
"""

import re

from _common import allow, block, read_input

LOOP_RE = re.compile(r"\b(?:while|until)\b")
SLEEP_RE = re.compile(r"\bsleep\b")
SIZE_POLL_RE = re.compile(r"\bwc\s+-[a-z]|\bstat\s|\bdu\s")
TASK_OUTPUT_RE = re.compile(r"\.output\b|/tasks/")
PROC_POLL_RE = re.compile(r"\bkill\s+-0\b|\bpgrep\b")
# A completion exit signals the loop waits for a condition rather than running
# forever: an explicit `break`, an `until` loop, or a `while` whose header is a
# real (changing) condition such as `while [ ! -s out ]`. An always-true header
# (`while true`, `while :`, `while [ 1 ]`, `while (( 1 ))`, `while [ true ]`,
# `while sleep N`) is an infinite metric/monitor loop, not a task wait, and is
# excluded via the negative lookahead below.
INFINITE_HEADER = r"true\b|:|\[\s*1\s*\]|\[\s*true\s*\]|\[\[\s*1\s*\]\]|\(\(\s*1\s*\)\)|sleep\b"
EXIT_RE = re.compile(rf"\bbreak\b|\buntil\b|\bwhile\s+(?!{INFINITE_HEADER})")

MSG = """\
BLOCKED: hand-rolled task-completion poll loop detected.

Polling a background task in a shell loop (`while`/`until` + `sleep`, with a
`wc`/`stat` size check or `*.output` / `tasks/` path plus a completion `break`,
or a `kill -0` / `pgrep` process-liveness check) is fragile - a slow stream
looks "stable" and you read a truncated result - and its shell control flow
forces a permission prompt that stalls unattended runs.

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
    if not (LOOP_RE.search(cmd) and SLEEP_RE.search(cmd)):
        allow()
    polls_file = SIZE_POLL_RE.search(cmd) or TASK_OUTPUT_RE.search(cmd)
    if PROC_POLL_RE.search(cmd) or (polls_file and EXIT_RE.search(cmd)):
        block(MSG)
    allow()


if __name__ == "__main__":
    main()
