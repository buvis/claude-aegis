"""Tests for hooks/block_suppression_markers.py.

Marker strings are assembled at runtime via ``marker()`` so this source file
never contains a literal suppression marker - that keeps the file writable even
while an older build of the very hook under test is installed and watching
edits. The hook is still exercised with the real, assembled marker through the
subprocess call.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "block_suppression_markers.py"


def marker(rest: str, lead: str = "#") -> str:
    """Build a suppression marker (e.g. marker(" noqa") -> the noqa comment)."""
    return lead + rest


def run_hook(payload: dict | str | None) -> subprocess.CompletedProcess[str]:
    if payload is None:
        stdin = ""
    elif isinstance(payload, str):
        stdin = payload
    else:
        stdin = json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=5,
    )


def edit(old: str, new: str) -> dict:
    return {"tool_name": "Edit", "tool_input": {"old_string": old, "new_string": new}}


class TestBlocks(unittest.TestCase):
    def test_blocks_added_type_ignore(self) -> None:
        r = run_hook(edit("x = 1", "x = 1  " + marker(" type: ignore")))
        self.assertEqual(r.returncode, 2)
        self.assertIn("BLOCKED", r.stderr)
        self.assertIn("type: ignore", r.stderr)

    def test_blocks_added_noqa(self) -> None:
        r = run_hook(edit("x = 1", "x = 1  " + marker(" noqa")))
        self.assertEqual(r.returncode, 2)

    def test_blocks_rust_allow(self) -> None:
        r = run_hook(edit("fn f() {}", marker("[allow(dead_code)]") + "\nfn f() {}"))
        self.assertEqual(r.returncode, 2)

    def test_blocks_file_level_ruff_noqa(self) -> None:
        # Whole-file ruff suppression: stronger than a per-line one.
        r = run_hook(edit("import os", "import os  " + marker(" ruff: noqa")))
        self.assertEqual(r.returncode, 2)

    def test_blocks_flake8_file_noqa(self) -> None:
        r = run_hook(edit("import os", marker(" flake8: noqa") + "\nimport os"))
        self.assertEqual(r.returncode, 2)

    def test_blocks_pyright_ignore(self) -> None:
        r = run_hook(edit("x = y", "x = y  " + marker(" pyright: ignore")))
        self.assertEqual(r.returncode, 2)

    def test_blocks_mypy_disable(self) -> None:
        r = run_hook(edit("x = y", "x = y  " + marker(" mypy: disable-error-code")))
        self.assertEqual(r.returncode, 2)

    def test_blocks_bandit_nosec(self) -> None:
        r = run_hook(edit("run(s)", "run(s)  " + marker(" nosec B602")))
        self.assertEqual(r.returncode, 2)

    def test_blocks_biome_ignore(self) -> None:
        r = run_hook(edit("const a = 1", marker(" biome-ignore lint", "//") + "\nconst a = 1"))
        self.assertEqual(r.returncode, 2)

    def test_blocks_write_new_file_with_marker(self) -> None:
        # A brand-new file (no old baseline) whose content carries a marker.
        path = os.path.join(tempfile.gettempdir(), "aegis_nonexistent_xyz.ts")
        if os.path.exists(path):
            os.remove(path)
        content = "x;  " + marker(" @ts-ignore", "//")
        r = run_hook({"tool_name": "Write", "tool_input": {"file_path": path, "content": content}})
        self.assertEqual(r.returncode, 2)


class TestAllows(unittest.TestCase):
    def test_allows_marker_carried_through_edit(self) -> None:
        # Same marker in old and new (count delta 0) is not a new addition.
        m = marker(" type: ignore")
        r = run_hook(edit("a  " + m, "b  " + m))
        self.assertEqual(r.returncode, 0)

    def test_allows_edit_without_markers(self) -> None:
        r = run_hook(edit("x = 1", "x = 2"))
        self.assertEqual(r.returncode, 0)

    def test_allows_unrelated_tool(self) -> None:
        r = run_hook({"tool_name": "Read", "tool_input": {"file_path": "/x"}})
        self.assertEqual(r.returncode, 0)

    def test_blocks_marker_with_nearby_apostrophe(self) -> None:
        # Apostrophes in comments/contractions must not hide a real marker.
        new = "x = foo()  " + marker(" type: ignore") + "\n# this won't matter"
        r = run_hook(edit("x = foo()", new))
        self.assertEqual(r.returncode, 2)

    def test_allows_write_preserving_existing_marker(self) -> None:
        m = marker(" type: ignore")
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("old_line  " + m + "\n")
            path = f.name
        try:
            r = run_hook(
                {"tool_name": "Write", "tool_input": {"file_path": path, "content": "new_line  " + m + "\n"}}
            )
            self.assertEqual(r.returncode, 0)
        finally:
            os.remove(path)

    def test_allows_empty_stdin(self) -> None:
        # Regression: bare json.loads used to crash (exit 1) on empty input.
        r = run_hook(None)
        self.assertEqual(r.returncode, 0)

    def test_allows_invalid_json(self) -> None:
        # Regression: must fail open, not raise a traceback.
        r = run_hook("not json")
        self.assertEqual(r.returncode, 0)

    def test_allows_missing_tool_name(self) -> None:
        r = run_hook({"tool_input": {"old_string": "a", "new_string": "b"}})
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
