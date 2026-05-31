"""PreToolUse Bash hook: validate `git commit` messages.

Enforces conventional commit format (`<type>(<scope>): <description>`),
rejects Co-Authored-By and other generated-by boilerplate, and refuses
heredoc commit construction (policy is a plain, single-line `-m`).

Message extraction covers every `-m` / `--message` value git accepts:
multiple `-m` flags, `--message=`, no-space `-m"x"`, and grouped short
flags like `-am`. When no message can be parsed (e.g. `-F file`, an editor
commit, a complex construction), the hook allows rather than blocking on
ambiguity.

Policy: aegis/rules/development-workflow.md (Commit Messages section).
"""

import re

from _common import allow, block, read_input

CONVENTIONAL_RE = re.compile(
    r"^(fix|feat|perf|refactor|style|test|docs|build|ops|chore)"
    r"(\([a-zA-Z0-9_./-]+\))?!?: [a-z]"
)
# Boilerplate trailers start their own line, possibly behind decoration (an
# emoji, a bullet, `>` quoting). `(?:^|\n)[^A-Za-z\n]*` anchors to a line start
# and skips any non-letter prefix - so it catches `🤖 Generated with Claude
# Code` while still ignoring a subject that merely names the term mid-sentence
# (`fix: document the generated-by rule`).
BOILERPLATE_RE = re.compile(
    r"(?:^|\n)[^A-Za-z\n]*(?:co-authored-by|signed-off-by|generated-by|generated with)",
    re.IGNORECASE,
)
# A real heredoc command-substitution (`$(cat <<DELIM ... )`). Policy forbids
# heredoc commits outright, so detecting the construction is enough - the body
# is not parsed. The `$(` requirement avoids firing on a literal "cat <<" that
# merely appears inside a quoted message.
HEREDOC_TRIGGER_RE = re.compile(r"\$\(\s*cat\s*<<")
# Every `-m` / `--message` value git accepts: -m "x", -m 'x', -m"x", -am "x",
# --message "x", -m=x, --message=x. A bare (unquoted) value is only taken after
# `=`; a space-separated bare token is NOT captured, so a malformed `-m fix: ok`
# (which git itself rejects) is left alone instead of mis-parsed as the message.
MSG_FLAG_RE = re.compile(
    r"(?<![\w=-])(?:--message|-[a-zA-Z]*m)"
    r"(?:=\s*(\"[^\"]*\"|'[^']*'|[^\s]+)"
    r"|\s*(\"[^\"]*\"|'[^']*'))"
)
# A git commit invocation, tolerating env-var and `git -c key=val` prefixes
# (`GIT_EDITOR=true git commit ...`, `git -c core.editor=true commit ...`).
GIT_COMMIT_RE = re.compile(r"\bgit\b[^|;&]*\bcommit\b")

NOT_CONVENTIONAL_TEMPLATE = """\
BLOCKED: commit message does not follow conventional commit format.
  Got: "{subject}"
  Expected: <type>(<scope>): <lowercase description>
  Types: fix|feat|perf|refactor|style|test|docs|build|ops|chore
  Rules: imperative present tense, no capital, no period, one line"""

TRAILING_PERIOD_TEMPLATE = """\
BLOCKED: commit message must not end with a period.
  Got: "{subject}\""""

BOILERPLATE_MSG = (
    "BLOCKED: commit message contains forbidden boilerplate "
    "(Co-Authored-By, Signed-Off-By, etc). Policy: do not include "
    "generated-by or co-authored-by trailers."
)

HEREDOC_MSG = (
    "BLOCKED: heredoc commit construction is not allowed. Use a simple "
    'single-line `git commit -m "<message>"`. '
    "Policy: aegis/rules/development-workflow.md (Commit Messages section)."
)


def extract_messages(command: str) -> list[str]:
    """All `-m` / `--message` values in order; empty when none are present."""
    out = []
    for eq_val, quoted_val in MSG_FLAG_RE.findall(command):
        val = eq_val or quoted_val
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        out.append(val)
    return out


def main() -> None:
    data = read_input()
    command = (data.get("tool_input") or {}).get("command") or ""
    if not GIT_COMMIT_RE.search(command):
        allow()
    if HEREDOC_TRIGGER_RE.search(command):
        block(HEREDOC_MSG)
    msgs = extract_messages(command)
    if not msgs:
        allow()
    full = "\n".join(msgs)
    if BOILERPLATE_RE.search(full):
        block(BOILERPLATE_MSG)
    subject = next(
        (line.strip() for line in full.splitlines() if line.strip()),
        "",
    )
    if not subject:
        allow()
    if not CONVENTIONAL_RE.match(subject):
        block(NOT_CONVENTIONAL_TEMPLATE.format(subject=subject))
    if subject.endswith("."):
        block(TRAILING_PERIOD_TEMPLATE.format(subject=subject))
    allow()


if __name__ == "__main__":
    main()
