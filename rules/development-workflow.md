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
