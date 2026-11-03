"""Tests for scripts/check_quote_sources.py (the quote-source checker)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_quote_sources as cqs

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "planwise"
    / "scripts"
    / "check_quote_sources.py"
)

SOURCE_TEXT = (
    "# Source Output\n"
    "\n"
    "Some context line.\n"
    "CLI build changed: installed unknown (size 1234) differs from newest snapshot 2.1.273\n"
    "Another line after it.\n"
)

DELIVERABLE_EXACT = (
    "# Report\n"
    "\n"
    "The recorded mismatch line (verbatim):\n"
    "\n"
    "```text\n"
    "CLI build changed: installed unknown (size 1234) differs from newest snapshot 2.1.273\n"
    "```\n"
    "\n"
    "```bash\n"
    "echo this unlabelled block is never compared\n"
    "```\n"
)


def _write(path: Path, text: str, newline: str = "\n") -> Path:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


def _run(tmp_path: Path, deliverable: str, source: str, source_newline: str = "\n"):
    deliv = _write(tmp_path / "deliverable.md", deliverable)
    src = _write(tmp_path / "source.md", source, source_newline)
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(deliv), "--source", str(src)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_exact_quote_exits_zero(tmp_path):
    result = _run(tmp_path, DELIVERABLE_EXACT, SOURCE_TEXT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 quote block(s) checked" in result.stdout
    assert "0 unmatched" in result.stdout


def test_one_changed_word_exits_one_and_names_block(tmp_path):
    changed = DELIVERABLE_EXACT.replace("installed unknown", "installed 2.1.273")
    result = _run(tmp_path, changed, SOURCE_TEXT)
    assert result.returncode == 1
    assert "UNMATCHED" in result.stdout
    assert "deliverable.md:6" in result.stdout
    assert "installed 2.1.273" in result.stdout
    assert "1 unmatched" in result.stdout


def test_crlf_source_against_lf_deliverable_exits_zero(tmp_path):
    result = _run(tmp_path, DELIVERABLE_EXACT, SOURCE_TEXT, source_newline="\r\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 unmatched" in result.stdout


def test_trailing_spaces_are_ignored_but_inner_spacing_is_not(tmp_path):
    padded = DELIVERABLE_EXACT.replace("2.1.273\n```\n", "2.1.273   \n```\n", 1)
    assert _run(tmp_path, padded, SOURCE_TEXT).returncode == 0
    inner = DELIVERABLE_EXACT.replace("installed unknown", "installed  unknown")
    assert _run(tmp_path, inner, SOURCE_TEXT).returncode == 1


def test_label_on_fence_info_and_blockquote_label():
    raw = (
        "```quote\n"
        "alpha line\n"
        "```\n"
        "\n"
        "Quoted from the source:\n"
        "> beta line\n"
        "> gamma line\n"
        "\n"
        "> an unlabelled callout is not a quote\n"
    )
    blocks = cqs.extract_quote_blocks(raw)
    assert [(b.kind, b.line, b.lines) for b in blocks] == [
        ("fenced", 2, ["alpha line"]),
        ("blockquote", 6, ["beta line", "gamma line"]),
    ]


def test_unlabelled_blocks_are_not_extracted():
    raw = "Plain prose line.\n\n```python\nx = 1  # quote in a comment\n```\n"
    assert cqs.extract_quote_blocks(raw) == []


def test_unreadable_source_exits_two(tmp_path):
    deliv = _write(tmp_path / "deliverable.md", DELIVERABLE_EXACT)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            str(deliv),
            "--source",
            str(tmp_path / "missing.md"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "cannot read source" in result.stderr


def test_unreadable_deliverable_exits_two(tmp_path):
    src = _write(tmp_path / "source.md", SOURCE_TEXT)
    code = cqs.main([str(tmp_path / "missing.md"), "--source", str(src)])
    assert code == 2
