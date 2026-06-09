"""Shared helpers for aegis hooks.

Stdlib only. Python 3.10+. Safe to import from any PreToolUse hook script
shipped by this plugin.

Conventions
-----------
- Hooks read a single JSON object from stdin and signal allow/block via exit
  code: 0 = allow, 2 = block (with a human-readable reason on stderr).
"""

import json
import sys
from typing import Any, NoReturn


def read_input() -> dict[str, Any]:
    """Parse stdin as JSON. Return {} on TTY, empty input, or parse failure.

    Hooks must remain non-fatal on bad input so a malformed payload never
    blocks an otherwise-valid tool call.
    """
    if sys.stdin.isatty():
        return {}
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def block(reason: str) -> NoReturn:
    """Print reason to stderr and exit 2 (block the tool call)."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def allow() -> NoReturn:
    """Exit 0 (allow the tool call)."""
    sys.exit(0)
