#!/usr/bin/env python3
"""PreToolUse hook: block Edit/Write/MultiEdit that newly adds lint or
type-checker suppression markers. Policy is to fix the root cause.

Policy: aegis/rules/coding-style.md (Warnings section).
Exit 0 = allow, Exit 2 = block."""

import re

from _common import allow, block, read_input

SUPPRESSION_PATTERNS = [
    (r"#!?\[allow\(", "Rust #[allow(...)] / #![allow(...)]"),
    (r"#\s*type:\s*ignore", "Python # type: ignore"),
    (r"#\s*pyright:\s*ignore", "Python # pyright: ignore"),
    (r"#\s*mypy:\s*(?:ignore|disable)", "Python # mypy: ignore / disable"),
    (r"#\s*noqa", "Python # noqa"),
    (r"#\s*(?:ruff|flake8):\s*noqa", "Python # ruff/flake8: noqa (file-level)"),
    (r"#\s*pylint:\s*disable", "Python # pylint: disable"),
    (r"#\s*nosec", "Python # nosec (bandit)"),
    (r"//\s*eslint-disable", "JS/TS // eslint-disable"),
    (r"/\*\s*eslint-disable", "JS/TS /* eslint-disable */"),
    (r"//\s*biome-ignore", "JS/TS // biome-ignore"),
    (r"//\s*@ts-ignore", "TS // @ts-ignore"),
    (r"//\s*@ts-nocheck", "TS // @ts-nocheck"),
    (r"//\s*@ts-expect-error", "TS // @ts-expect-error"),
    (r"@SuppressWarnings", "Java @SuppressWarnings"),
    (r"//\s*nolint", "Go //nolint"),
    (r"//\s*NOLINT", "C/C++ // NOLINT"),
]


def count_markers(text: str) -> dict[str, int]:
    if not text:
        return {}
    out = {}
    for pattern, label in SUPPRESSION_PATTERNS:
        n = len(re.findall(pattern, text))
        if n:
            out[label] = n
    return out


def diff_added(old_text: str, new_text: str) -> list[tuple[str, int]]:
    old = count_markers(old_text)
    new = count_markers(new_text)
    added = []
    for label, n in new.items():
        delta = n - old.get(label, 0)
        if delta > 0:
            added.append((label, delta))
    return added


def main() -> None:
    payload = read_input()
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {})

    additions: list[tuple[str, int, str]] = []

    if tool == "Edit":
        for label, n in diff_added(inp.get("old_string", ""), inp.get("new_string", "")):
            additions.append((label, n, "Edit"))
    elif tool == "MultiEdit":
        for i, edit in enumerate(inp.get("edits", [])):
            for label, n in diff_added(edit.get("old_string", ""), edit.get("new_string", "")):
                additions.append((label, n, f"MultiEdit edit #{i + 1}"))
    elif tool == "Write":
        new_text = inp.get("content", "")
        path = inp.get("file_path", "")
        old_text = ""
        try:
            with open(path) as f:
                old_text = f.read()
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            pass
        for label, n in diff_added(old_text, new_text):
            additions.append((label, n, "Write"))
    else:
        allow()

    if not additions:
        allow()

    lines = ["BLOCKED: change adds lint/type-checker suppression markers.", ""]
    lines += [f"  + {label} (x{n}, in {where})" for label, n, where in additions]
    lines += [
        "",
        "Policy: fix the root cause, don't silence warnings.",
        "See aegis/rules/coding-style.md (Warnings section).",
    ]
    block("\n".join(lines))


if __name__ == "__main__":
    main()
