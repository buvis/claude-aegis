"""PreToolUse hook: block Edit/Write to linter and formatter config files.

The policy is to fix the source code rather than weaken the linter.
Policy: aegis/rules/coding-style.md (Warnings section).
"""

import os
import re

from _common import allow, block, read_input

# A ruff config that only pins the Python version weakens nothing: it stops
# fixes the supported version cannot run (such as datetime.UTC before 3.11).
RUFF_CONFIGS: frozenset[str] = frozenset({".ruff.toml", "ruff.toml"})
PIN_LINE = re.compile(r'^\s*(?:target-version\s*=\s*"py3\d+"\s*)?(?:#.*)?$')

PROTECTED_BASENAMES: frozenset[str] = frozenset({
    # eslint
    ".eslintrc",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yml",
    ".eslintrc.yaml",
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    "eslint.config.ts",
    "eslint.config.mts",
    "eslint.config.cts",
    # prettier
    ".prettierrc",
    ".prettierrc.js",
    ".prettierrc.cjs",
    ".prettierrc.json",
    ".prettierrc.yml",
    ".prettierrc.yaml",
    "prettier.config.js",
    "prettier.config.cjs",
    "prettier.config.mjs",
    # biome
    "biome.json",
    "biome.jsonc",
    # ruff
    ".ruff.toml",
    "ruff.toml",
    # shellcheck
    ".shellcheckrc",
    # stylelint
    ".stylelintrc",
    ".stylelintrc.json",
    ".stylelintrc.yml",
    # markdownlint
    ".markdownlint.json",
    ".markdownlint.yaml",
    ".markdownlintrc",
    # clippy
    "clippy.toml",
    ".clippy.toml",
    # swiftlint
    ".swiftlint.yml",
    ".swiftlint.yaml",
})


def only_version_pin(file_path: str, tool_input: dict) -> bool:
    """Whether the file as it is and every text the call writes hold only a target-version pin."""
    texts = [tool_input.get(k) for k in ("content", "old_string", "new_string")]
    for edit in tool_input.get("edits") or []:
        texts += [edit.get("old_string"), edit.get("new_string")]
    texts = [t for t in texts if isinstance(t, str)]
    if not texts:
        return False
    try:
        with open(file_path, encoding="utf-8") as existing:
            texts.append(existing.read())
    except FileNotFoundError:
        pass
    except (OSError, UnicodeDecodeError):
        return False
    return all(PIN_LINE.match(line) for text in texts for line in text.splitlines())


def main() -> None:
    data = read_input()
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        allow()
    basename = os.path.basename(file_path)
    if basename in RUFF_CONFIGS and only_version_pin(file_path, tool_input):
        allow()
    if basename in PROTECTED_BASENAMES:
        block(
            f"BLOCKED: editing {basename} is not allowed. "
            "Fix the source code instead of weakening linter/formatter config."
        )
    allow()


if __name__ == "__main__":
    main()
