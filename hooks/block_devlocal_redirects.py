"""PreToolUse Bash hook: block shell redirects writing into dev/local/.

Files in dev/local/ must be created via the Write tool.
Policy: aegis/rules/working-documents.md.
"""

import re

from _common import allow, block, read_input

# `>|` is the noclobber-override redirect; allow the optional `|` after the
# operator. The target may itself be quoted (`> "dev/local/x"`), so quotes are
# NOT stripped first - the path is matched in place, quotes and all.
REDIRECT_RE = re.compile(r"(>>?|&>)\|?\s*[^\s&|;]*dev/local/")
# Exclude `<` so reading FROM dev/local and teeing elsewhere is not blocked.
TEE_RE = re.compile(r"\btee\b[^|;&<]*dev/local/")

REDIRECT_MSG = """\
BLOCKED: shell redirect (`>` / `>>` / `&>`) into `dev/local/` is not allowed.

Use the Write tool for `dev/local/` files instead.
Policy: aegis/rules/working-documents.md (dev/local/ section)."""

TEE_MSG = """\
BLOCKED: `tee` writing into `dev/local/` is not allowed.

Use the Write tool for `dev/local/` files instead.
Policy: aegis/rules/working-documents.md (dev/local/ section)."""


def main() -> None:
    data = read_input()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        allow()
    if REDIRECT_RE.search(cmd):
        block(REDIRECT_MSG)
    if TEE_RE.search(cmd):
        block(TEE_MSG)
    allow()


if __name__ == "__main__":
    main()
