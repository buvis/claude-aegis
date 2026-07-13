# Aegis

[![GitHub license](https://img.shields.io/github/license/buvis/claude-aegis)](https://github.com/buvis/claude-aegis/blob/master/LICENSE)

> "What [Athena] holds is the aegis, terror of mortal men." — *Iliad*, V.738

Defensive PreToolUse hooks for [Claude Code](https://claude.ai/code). Eight small Python scripts that catch the most common ways an agent quietly degrades a codebase: reaching for bash text utilities instead of dedicated tools, writing into `dev/local/` with shell redirects, slipping in a lint-suppression comment to make a warning vanish, editing the linter config to weaken a rule, attaching generated-by boilerplate to a commit, hand-rolling a poll loop to wait for a background task, force-pushing over remote history without a second look, or charging into the first edit of a file or a destructive command without investigating what it touches.

## What's inside

| Hook | Tool matcher | What it blocks |
|------|--------------|----------------|
| `prefer_tools.py` | Bash | `grep`, `find`, `cat`, `head`, `tail` — surfaces the Grep/Glob/Read alternative |
| `block_devlocal_redirects.py` | Bash | shell redirects (`>`, `>>`, `&>`, `tee`) into `dev/local/` — use Write |
| `block_suppression_markers.py` | Edit, Write, MultiEdit | newly added lint or type-checker suppression comments across 12 languages |
| `protect_config.py` | Edit, Write, MultiEdit | edits to ~40 well-known linter and formatter config files |
| `validate_commit_msg.py` | Bash | non-conventional commit messages, trailing periods, generated-by trailers |
| `block_poll_loops.py` | Bash, Monitor | hand-rolled task-completion poll loops — points to the `TaskOutput` tool |
| `block_force_push.py` | Bash | `git push --force` / `-f` / `--force-with-lease` / `+refspec` — force pushes never run automatically |
| `gateguard_fact_force.py` | Edit, Write, MultiEdit, Bash | first edit/write/destructive-bash per target — returns a fact list to gather before retry |

Most hooks read a single JSON object from stdin and signal via exit code (0 = allow, 2 = block with a human-readable reason on stderr). `gateguard_fact_force.py` is the exception: it returns a structured JSON envelope on stdout (`hookSpecificOutput.permissionDecision = "deny"` carrying the fact list) and always exits 0. All eight run as PreToolUse hooks; nothing fires after the fact.

`block_force_push.py` does not make force pushing impossible — its block message points at the `!` prefix, which runs a command outside the agent tool layer. The effect is that a force push always takes a deliberate human action and never happens silently.

The `rules/` directory documents the policy each hook enforces. Hooks cite these paths in their error messages so you can look up the "why" without leaving the terminal.

## Operator skill

aegis bundles one skill, `skills/gateguard/SKILL.md`. It auto-loads when `gateguard_fact_force.py` denies a tool call with a `[Fact-Forcing Gate]` message and explains how to respond: run the requested investigation (Grep for importers, Glob for duplicates, Read for schemas), present the facts, then retry the original call. The retry is allowed once the same target is hit again in the session.

## Install

```
/plugin marketplace add buvis/claude-plugins
/plugin install aegis@buvis-plugins
```

Restart Claude Code. Hooks register automatically; nothing to invoke by name.

### Update

```
/plugin update aegis@buvis-plugins
```

### Alternative: install directly from this repo

```
/plugin marketplace add buvis/claude-aegis
/plugin install aegis@claude-aegis
```

## Why "aegis"

The aegis is the shield of Zeus, lent to Athena and Apollo. Single piece of defensive equipment, mythological, distinctive. It fits a plugin whose whole job is to deflect the cheap shots before they hit your codebase: the silent suppression comment, the shell redirect that bypasses your audit trail, the `cat | grep | head` that wastes tokens.

Like the original, it's prophylactic. You won't see it work — you'll just notice the bad patterns never land.

## Releasing

`dev/bin/release [patch|minor|major]` is a thin shim. The shared release
script lives in the central marketplace repo,
[buvis/claude-plugins](https://github.com/buvis/claude-plugins), and every
release also bumps this plugin's entry there. Developing this plugin
therefore needs that repo cloned beside this one:

```bash
git clone git@github.com:buvis/claude-plugins.git ../claude-plugins
```

Repo-specific pre-release checks live in `dev/bin/release-checks`.

## License

MIT — see [LICENSE](LICENSE).
