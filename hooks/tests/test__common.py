"""Tests for hooks/_common.py read_input()."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # hooks/
import _common


class _FakeStdin:
    def __init__(self, *, tty: bool, content: str = "") -> None:
        self._tty = tty
        self._content = content

    def isatty(self) -> bool:
        return self._tty

    def read(self) -> str:
        if self._tty:
            raise AssertionError("read() must not be called on a TTY")
        return self._content


class TestReadInput(unittest.TestCase):
    def setUp(self) -> None:
        self._real_stdin = sys.stdin

    def tearDown(self) -> None:
        sys.stdin = self._real_stdin

    def test_returns_empty_dict_on_tty_without_reading(self) -> None:
        sys.stdin = _FakeStdin(tty=True)
        self.assertEqual(_common.read_input(), {})

    def test_parses_piped_json_object(self) -> None:
        sys.stdin = _FakeStdin(tty=False, content='{"tool_name": "Edit"}')
        self.assertEqual(_common.read_input(), {"tool_name": "Edit"})

    def test_returns_empty_dict_for_empty_piped_input(self) -> None:
        sys.stdin = _FakeStdin(tty=False, content="")
        self.assertEqual(_common.read_input(), {})

    def test_returns_empty_dict_for_invalid_piped_json(self) -> None:
        sys.stdin = _FakeStdin(tty=False, content="not json")
        self.assertEqual(_common.read_input(), {})


if __name__ == "__main__":
    unittest.main()
