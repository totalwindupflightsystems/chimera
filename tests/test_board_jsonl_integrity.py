"""Tripwire: a tracked board JSONL file must never contain a glued line.

Context (incident class, not this checkout). A board writer once appended a
row to ``.coding-hermes/board/tasks.jsonl`` while the file's last line lacked
a trailing newline, gluing three JSON objects onto ONE physical line. Every
line-wise consumer (jq, boardctl, the stand-in picker) silently dropped that
physical line, so three tasks vanished from all reports while the file looked
perfectly fine to ``git diff``.

This module fails loudly if that class ever comes back in the files this repo
tracks. The fleet's appenders (``~/.hermes/scripts/board_append.py``,
``qa_board_append.py``) already enforce the newline invariant (DAGGER-0943);
this guard protects this repo's tracked boards against any OTHER writer.

Shape: :func:`check_lines` is the pure detector (bytes in, problem strings
out) so the glue detection itself is unit-tested below with synthetic glued
bytes; the tracked-file tests are a thin wrapper over it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Exactly the tracked board files this test guards.
TRACKED_BOARD_FILES = (
    REPO_ROOT / ".coding-hermes" / "board" / "tasks.jsonl",
    REPO_ROOT / ".coding-hermes" / "board" / "events.jsonl",
)


def check_lines(data: bytes) -> list[str]:
    """Check raw board-file bytes; return a list of human-readable problems.

    An empty file is valid. A non-empty file must end with exactly one
    ``b"\\n"`` and every non-empty line must be one complete JSON object.
    A glued (multi-object) line fails ``json.loads`` with "Extra data"; a
    line-wrapping mistake yields a non-dict — both are reported.
    """
    problems: list[str] = []
    if not data:
        return problems
    if not data.endswith(b"\n"):
        problems.append("file does not end with a trailing newline")
    elif data.endswith(b"\n\n"):
        problems.append("file ends with a double trailing newline")
    for lineno, line in enumerate(data.split(b"\n"), start=1):
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"line {lineno} is not a single JSON object: {line[:80]!r} ({exc})")
            continue
        if not isinstance(parsed, dict):
            problems.append(f"line {lineno} is JSON but not an object: {line[:80]!r}")
    return problems


def _format_problems(path: Path, problems: list[str]) -> str:
    return "\n".join(f"  {path.name}: {p}" for p in problems)


class TestCheckLines:
    """Unit tests for the pure detector, including the synthetic glue case."""

    def test_empty_bytes_clean(self) -> None:
        assert check_lines(b"") == []

    def test_single_object_clean(self) -> None:
        assert check_lines(b'{"id": "A"}\n') == []

    def test_glued_line_reported(self) -> None:
        # The incident shape: last line lacks \n, next object appended -> one
        # physical line carrying two (or more) JSON objects.
        glued = b'{"id": "A"}\n{"id": "B"}{"id": "C"}'
        problems = check_lines(glued)
        assert problems, "glued bytes must be reported"
        assert len(problems) == 2  # missing trailing newline + the glued line
        glued_problems = [p for p in problems if "Extra data" in p]
        assert glued_problems, f"glue must surface as Extra data: {problems}"
        assert "line 2" in glued_problems[0]
        assert '{"id": "B"}' in glued_problems[0]  # offending line preview present

    def test_double_trailing_newline_reported(self) -> None:
        assert check_lines(b'{"id": "A"}\n\n') == ["file ends with a double trailing newline"]

    def test_non_dict_line_reported(self) -> None:
        problems = check_lines(b"[1, 2, 3]\n")
        assert problems == ["line 1 is JSON but not an object: b'[1, 2, 3]'"]


@pytest.mark.parametrize("path", TRACKED_BOARD_FILES, ids=lambda p: p.name)
def test_tracked_board_jsonl_integrity(path: Path) -> None:
    """Each tracked board file: clean trailing newline, one dict per line."""
    if not path.exists():
        pytest.skip(f"{path} not present in this checkout")
    data = path.read_bytes()
    problems = check_lines(data)
    if problems:
        pytest.fail(f"glued/malformed lines in {path}:\n{_format_problems(path, problems)}")
