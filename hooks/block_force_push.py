"""PreToolUse Bash hook: block force pushes from running automatically.

A `git push` carrying a force indicator (`--force`, `-f`, `--force-with-lease`,
or a `+`-prefixed refspec) can overwrite commits on the remote. This hook
denies such a push (exit 2). It does not make force pushing impossible: the
block message points the user at the `!` prefix, which runs a command outside
the agent tool layer and so bypasses this hook. The effect is that a force
push always takes a deliberate human action and never runs silently.

Policy: aegis/rules/development-workflow.md (Force Push section).
"""

import shlex

from _common import allow, block, read_input

# Shell tokens that end one command and start another. A force indicator only
# counts when it shares a segment with its own `git push`.
SEPARATORS = {"&&", "||", ";", "|", "&"}

FORCE_FLAGS = {"-f", "--force", "--force-with-lease"}

BLOCK_MSG = (
    "BLOCKED: force push is not run automatically. `git push` with --force, "
    "-f, --force-with-lease, or a +refspec rewrites remote history. If this "
    "force push is genuinely needed, ask the user to run it themselves with "
    "the `!` prefix (e.g. `! git push --force-with-lease origin master`), "
    "which bypasses this hook. "
    "Policy: aegis/rules/development-workflow.md (Force Push section)."
)


def is_force_flag(token: str) -> bool:
    """True when the token is a force-push flag.

    Covers the long forms, `--force-with-lease=<arg>`, and bundled short flags
    such as `-fu` (a single dash, no second dash, with an `f` among the
    letters). `--force` is matched via the literal set above.
    """
    if token in FORCE_FLAGS or token.startswith("--force-with-lease="):
        return True
    return (
        token.startswith("-")
        and not token.startswith("--")
        and len(token) > 1
        and "f" in token[1:]
    )


def is_git_token(token: str) -> bool:
    """True for `git` invoked bare or by path (`/usr/bin/git`, `./git`)."""
    return token == "git" or token.endswith("/git")


def is_plus_refspec(token: str) -> bool:
    """True for a `+`-prefixed refspec (`+master`, `+HEAD:master`).

    A leading `+` on a refspec forces the update of that single ref, so it is
    a force push even with no `--force` flag present.
    """
    return len(token) > 1 and token.startswith("+")


def push_segments(tokens: list[str]) -> list[list[str]]:
    """Split a shlex-tokenized command on separators (&&, ||, ;, |, &).

    Works on a token list (not the raw string) so that a `--force` appearing
    inside a quoted commit message stays inside its single token and is never
    mistaken for a bare flag.
    """
    result: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in SEPARATORS:
            if current:
                result.append(current)
            current = []
        else:
            current.append(token)
    if current:
        result.append(current)
    return result


def is_force_push(command: str) -> bool:
    """True when any shell segment is a `git push` carrying a force indicator."""
    try:
        tokens = shlex.split(command, comments=True)
    except ValueError:
        # Unparseable command. A force push is unlikely to be unparseable, and
        # blocking on ambiguity would be noisy; allow it through.
        return False
    for segment in push_segments(tokens):
        if not any(is_git_token(t) for t in segment) or "push" not in segment:
            continue
        push_args = segment[segment.index("push") + 1 :]
        if any(is_force_flag(t) or is_plus_refspec(t) for t in push_args):
            return True
    return False


def main() -> None:
    data = read_input()
    command = (data.get("tool_input") or {}).get("command") or ""
    if "push" not in command:
        allow()
    if is_force_push(command):
        block(BLOCK_MSG)
    allow()


if __name__ == "__main__":
    main()
