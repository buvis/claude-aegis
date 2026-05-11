"""PreToolUse Bash hook: deny when a dedicated tool would be cleaner.

Hard deny (exit 2) when any segment of a Bash command invokes one of
`grep|find|cat|head|tail` - either as a standalone command or inside a
pipe/chain. The model has dedicated Grep/Glob/Read tools that are
faster, cheaper, and produce structured output. `Grep` accepts
`head_limit` and `output_mode`, `Read` accepts `offset`/`limit`, so the
common pipe patterns (`grep ... | head`, `cat file | jq`) have first-
class replacements.

`rg` is allowed (faster than grep, respects .gitignore).
`jq` is allowed; the right replacement for `cat file | jq '...'` is
`jq '...' file`, not Read.

Policy: see this plugin's rules/tools.md.
"""

import json
import re
import sys

DENY = {
    "grep": "Grep (supports head_limit, output_mode, glob filters)",
    "find": "Glob",
    "cat": "Read (or pass the filename directly to the next tool, e.g. `jq '...' file`)",
    "head": "Read with offset/limit (or Grep's head_limit)",
    "tail": "Read with offset/limit",
}

# Split a command into segments on shell separators: | ; && || and subshell openers $( `
SEGMENT_RE = re.compile(r"\|\|?|&&|;|\$\(|`")

# Inside one segment, strip leading subshell openers like $(  or `
SUBSHELL_OPEN_RE = re.compile(r"^\s*(\$\(|`)\s*")

# Wrappers whose effective command is their next argument
WRAPPERS = {"xargs", "time", "nice", "sudo", "command", "env"}


def first_meaningful_token(segment: str) -> str:
    """Return the first token of a segment, peeling subshell openers and wrappers.

    For `xargs grep foo` returns `grep`. For `$(cat file)` returns `cat`.
    """
    seg = segment.strip()
    # Peel any number of subshell openers
    while True:
        m = SUBSHELL_OPEN_RE.match(seg)
        if not m:
            break
        seg = seg[m.end() :].lstrip()
    tokens = re.split(r"\s+", seg)
    # Skip env var assignments like `FOO=bar grep ...`
    i = 0
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
        i += 1
    # Peel wrappers (and their flags)
    while i < len(tokens) and tokens[i] in WRAPPERS:
        i += 1
        while i < len(tokens) and tokens[i].startswith("-"):
            i += 1
    return tokens[i] if i < len(tokens) else ""


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)
    if not isinstance(data, dict):
        sys.exit(0)

    cmd = (data.get("tool_input") or {}).get("command") or ""
    cmd = cmd.strip()
    if not cmd:
        sys.exit(0)

    for segment in SEGMENT_RE.split(cmd):
        first = first_meaningful_token(segment)
        target = DENY.get(first)
        if target:
            print(
                f"Blocked: use the {target} tool instead of bash `{first}`. "
                f"It is faster, returns structured output, and respects file ignores. "
                f"This applies inside pipes/chains too: `grep ... | head` -> Grep with "
                f"head_limit; `cat file | jq '...'` -> `jq '...' file`. "
                f"Policy: aegis/rules/tools.md.",
                file=sys.stderr,
            )
            sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
