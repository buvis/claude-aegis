"""PreToolUse Bash hook: deny when a dedicated tool would be cleaner.

Hard deny (exit 2) when any segment of a Bash command invokes one of
`grep|find|cat|head|tail` - either as a standalone command or inside a
pipe/chain/subshell. `cat|head|tail` have a dedicated Read tool (`offset`/
`limit`). The native Grep/Glob tools are unavailable in this build (an upstream
native-build bug), so `grep`/`find` route to `rg` for a targeted search or the
`Explore` agent for broad fan-out, not to Grep/Glob.

`rg` is allowed (faster than grep, respects .gitignore).
`jq` is allowed; the right replacement for `cat file | jq '...'` is
`jq '...' file`, not Read.

Policy: see this plugin's rules/tools.md.
"""

import re

from _common import allow, block, read_input

DENY = {
    "grep": (
        "Use `rg` for a targeted search, or the `Explore` agent for a broad "
        "fan-out across many files. The native Grep tool is unavailable in this build."
    ),
    "find": (
        "Use `rg --files` (add `-g <glob>` to filter) to locate files, or the "
        "`Explore` agent for a broad search. The native Glob tool is unavailable "
        "in this build."
    ),
    "cat": "Use the Read tool, or pass the filename straight to the next tool (e.g. `jq '...' file`).",
    "head": (
        "On a file, use the Read tool with offset/limit. On command output "
        "(`cmd | head`), run the command bare (the Bash tool already truncates "
        "long output), or redirect to a file and Read that."
    ),
    "tail": (
        "On a file, use the Read tool with offset/limit. On command output "
        "(`cmd | tail`), run the command bare (the Bash tool already truncates "
        "long output), or redirect to a file and Read that."
    ),
}

# Quoted spans are data, not commands. Strip them before splitting so a denied
# word inside a string (`git commit -m 'see a | grep b'`) is never parsed as a
# real pipeline segment and wrongly blocked. Safe here because the input is a
# shell command, where quotes are genuine delimiters.
QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")

# Split a command into segments on shell separators: | ; && || and subshell openers $( `
SEGMENT_RE = re.compile(r"\|\|?|&&|;|\$\(|`")

# Inside one segment, strip leading subshell openers like $(  or `
SUBSHELL_OPEN_RE = re.compile(r"^\s*(\$\(|`)\s*")

# Wrappers whose effective command is their next argument
WRAPPERS = {"xargs", "time", "nice", "sudo", "command", "env"}


def first_meaningful_token(segment: str) -> str:
    """Return the first token of a segment, peeling subshell openers and wrappers.

    For `xargs grep foo` returns `grep`. For `$(cat file)` returns `cat`. Leading
    env-var assignments (`LC_ALL=C grep`) and wrappers (`sudo`, `time`, ...) are
    peeled so the denied binary behind them is still seen.
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
    data = read_input()
    cmd = ((data.get("tool_input") or {}).get("command") or "").strip()
    if not cmd:
        allow()
    scan = QUOTED_RE.sub("", cmd)
    for segment in SEGMENT_RE.split(scan):
        first = first_meaningful_token(segment)
        target = DENY.get(first)
        if target:
            block(
                f"Blocked bash `{first}`. {target} "
                f"This applies inside pipes, chains, and subshells too "
                f"(e.g. `{first} ... | other`). Policy: aegis/rules/tools.md."
            )
    allow()


if __name__ == "__main__":
    main()
