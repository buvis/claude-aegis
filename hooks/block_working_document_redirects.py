"""Block shell redirects into development-artifact directories.

Files in docs/dev/project-management/ and docs/dev/tmp/ must use Write.
Policy: aegis/rules/working-documents.md.
"""

import re

from _common import allow, block, read_input

# `>|` is the noclobber-override redirect; allow the optional `|` after the
# operator. The target may itself be quoted (`> "docs/dev/project-management/x"`), so quotes are
# NOT stripped first - the path is matched in place, quotes and all.
WORKING_DIR_RE = r"docs/dev/(?:project-management|tmp)/"
REDIRECT_RE = re.compile(rf"(>>?|&>)\|?\s*[^\s&|;]*{WORKING_DIR_RE}")
# Exclude `<` so reading from either tree and teeing elsewhere is not blocked.
TEE_RE = re.compile(rf"\btee\b[^|;&<]*{WORKING_DIR_RE}")

REDIRECT_MSG = """\
BLOCKED: shell redirects into `docs/dev/project-management/` or `docs/dev/tmp/` are not allowed.

Use the Write tool for development artifacts instead.
Policy: aegis/rules/working-documents.md."""

TEE_MSG = """\
BLOCKED: `tee` writes into `docs/dev/project-management/` or `docs/dev/tmp/` are not allowed.

Use the Write tool for development artifacts instead.
Policy: aegis/rules/working-documents.md."""


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
