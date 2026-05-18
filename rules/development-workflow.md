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

The hook will block `git commit -m ...` invocations that:

- Don't match the conventional format above
- End with a period
- Contain forbidden boilerplate (`Co-Authored-By`, `Signed-Off-By`, `Generated-By`, `Generated with`)

If the message can't be parsed (e.g. unquoted, complex shell construction, heredoc with a non-`EOF` delimiter), the hook allows the commit through rather than blocking on ambiguity.

## Force Push section

The `block_force_push.py` hook enforces the rule in this section.

Force-pushing rewrites history on the remote and can drop other commits. It must never run automatically as part of an agent's work.

A `git push` is treated as a force push when its arguments include:

- `--force` or `-f` (including bundled short flags such as `-fu`)
- `--force-with-lease`, with or without an `=<arg>` value
- a `+`-prefixed refspec (`+master`, `+HEAD:master`), which forces that single ref

When the hook sees one, it blocks the command (exit 2). This does not make force pushing impossible: the block message points at the `!` prefix, which runs a command outside the agent tool layer and so bypasses the hook. A genuine force push therefore always takes a deliberate human action. Plain pushes, `--set-upstream`, and `git fetch --force` are unaffected. A `--force` appearing inside a quoted commit message does not trigger the hook.
