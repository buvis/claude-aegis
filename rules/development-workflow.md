# Development Workflow

The `validate_commit_msg.py` hook enforces the rules in the **Commit Messages** section below.

## Commit Messages section

Format: `<type>(<scope>): <description>`

Types: `fix`, `feat`, `perf`, `refactor`, `style`, `test`, `docs`, `build`, `ops`, `chore`

Rules:

- imperative present tense, lowercase description, no period, one line only
- `!` before `:` for breaking changes
- NEVER add `Co-Authored-By`, `Signed-Off-By`, `Generated-By`, or any trailer/footer
- Use simple `git commit -m "<message>"` — no HEREDOC tricks, no multi-line

The hook checks every message a `git commit` carries - across multiple `-m` flags, `--message=`, no-space `-m"x"`, grouped short flags like `-am`, and through env-var or `git -c key=val` prefixes - and blocks when the message:

- Doesn't match the conventional format above
- Ends with a period
- Contains forbidden boilerplate at the start of a line (`Co-Authored-By`, `Signed-Off-By`, `Generated-By`, `Generated with`)

Heredoc commit construction (`git commit -m "$(cat <<EOF ... )"`) is blocked outright, in line with the "no HEREDOC tricks" rule above. When no message can be parsed (e.g. `-F file`, an editor commit, a complex construction), the hook allows the commit through rather than blocking on ambiguity.

## Force Push section

The `block_force_push.py` hook enforces the rule in this section.

Force-pushing rewrites history on the remote and can drop other commits. It must never run automatically as part of an agent's work.

A `git push` is treated as a force push when its arguments include:

- `--force` or `-f` (including bundled short flags such as `-fu`)
- `--force-with-lease`, with or without an `=<arg>` value
- a `+`-prefixed refspec (`+master`, `+HEAD:master`), which forces that single ref

When the hook sees one, it blocks the command (exit 2). This does not make force pushing impossible: the block message points at the `!` prefix, which runs a command outside the agent tool layer and so bypasses the hook. A genuine force push therefore always takes a deliberate human action. Plain pushes, `--set-upstream`, and `git fetch --force` are unaffected. A `--force` appearing inside a quoted commit message does not trigger the hook.
