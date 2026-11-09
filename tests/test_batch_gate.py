"""Tests for scripts/batch_gate.py: the labels and items batch checks.

Each predicate runs once on a known-bad input that fires and once on the same
input repaired, which must not fire.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import batch_gate

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "batch_gate.py"

GOOD = """# Title

## Scope
text
### Findings
#### Detail
"""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path)


# ---- labels -------------------------------------------------------------


def test_section_labels_reads_levels_two_to_four_outside_fences():
    lines = [
        "# Title",
        "## Kept",
        "```",
        "## Inside fence",
        "```",
        "~~~~",
        "### Also inside",
        "~~~",
        "still inside, a shorter fence does not close",
        "~~~~",
        "### After",
        "##### Too deep",
        "##NoSpace",
    ]
    assert batch_gate.section_labels(lines) == {"## Kept", "### After"}


def test_labels_divergent_set_exits_1_and_lists_labels(tmp_path):
    a = _write(tmp_path / "a.md", GOOD)
    b = _write(tmp_path / "b.md", GOOD.replace("### Findings", "### Results"))
    res = _run("labels", a, b)
    assert res.returncode == 1, res.stdout + res.stderr
    assert res.stdout.startswith("labels: 2 files")
    assert "adds:  ### Results" in res.stdout
    assert "lacks: ### Findings" in res.stdout
    assert res.stderr == ""


def test_labels_repaired_set_exits_0(tmp_path):
    a = _write(tmp_path / "a.md", GOOD)
    b = _write(tmp_path / "b.md", GOOD.replace("text", "other body text"))
    res = _run("labels", a, b)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "labels: identical" in res.stdout


def test_labels_level_change_is_divergence(tmp_path):
    a = _write(tmp_path / "a.md", GOOD)
    b = _write(tmp_path / "b.md", GOOD.replace("### Findings", "## Findings"))
    assert _run("labels", a, b).returncode == 1


def test_labels_crlf_file_matches_lf_file(tmp_path):
    a = _write(tmp_path / "a.md", GOOD)
    b = tmp_path / "b.md"
    b.write_bytes(GOOD.replace("\n", "\r\n").encode("utf-8"))
    assert _run("labels", a, str(b)).returncode == 0


def test_labels_unreadable_file_exits_2(tmp_path):
    a = _write(tmp_path / "a.md", GOOD)
    res = _run("labels", a, str(tmp_path / "absent.md"))
    assert res.returncode == 2
    assert "cannot read" in res.stderr


def test_labels_single_file_is_a_usage_error(tmp_path):
    a = _write(tmp_path / "a.md", GOOD)
    assert _run("labels", a).returncode == 2


# ---- items --------------------------------------------------------------


def test_items_missing_and_duplicate_exit_1(tmp_path):
    ids = _write(tmp_path / "ids.txt", "# required ids\nitem-1\nitem-2\nitem-3\n\n")
    p1 = _write(tmp_path / "p1.md", "| item-1 | a |\n| item-2 | b |\n")
    p2 = _write(tmp_path / "p2.md", "| item-2 | again |\n| item-10 | not item-1 |\n")
    res = _run("items", "--ids", ids, p1, p2)
    assert res.returncode == 1, res.stdout + res.stderr
    assert res.stdout.startswith("items: 3 ids, 2 files")
    assert "MISSING: item-3" in res.stdout
    assert "DUPLICATE: item-1 (2:" in res.stdout
    assert "DUPLICATE: item-2 (2:" in res.stdout


def test_items_repaired_batch_exits_0(tmp_path):
    ids = _write(tmp_path / "ids.txt", "item-1\nitem-2\nitem-3\n")
    p1 = _write(tmp_path / "p1.md", "| item-1 | a |\n| item-2 | b |\n")
    p2 = _write(tmp_path / "p2.md", "| item-3 | c |\n| item-10 | other |\n")
    res = _run("items", "--ids", ids, p1, p2)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "MISSING" not in res.stdout
    assert "DUPLICATE" not in res.stdout


def test_items_token_boundary_ignores_longer_ids():
    counts = batch_gate.count_items(["a-1"], {"f": "a-1 a-10 xa-1 a-1b a-1."})
    assert counts == {"a-1": {"f": 2}}


def test_items_empty_id_list_exits_2(tmp_path):
    ids = _write(tmp_path / "ids.txt", "# only a comment\n\n")
    p1 = _write(tmp_path / "p1.md", "item-1\n")
    res = _run("items", "--ids", ids, p1)
    assert res.returncode == 2
    assert res.stdout.startswith("items: 0 ids, 1 files")
