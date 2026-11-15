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
    # item-1 in p2's second cell is a cross-reference, not a claim.
    assert "DUPLICATE: item-1" not in res.stdout
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


def test_items_repeat_mentions_in_the_owning_file_exit_0(tmp_path):
    ids = _write(tmp_path / "ids.txt", "L-1\nL-2\nL-3\n")
    a = _write(
        tmp_path / "a.md",
        "## Leads\n\n| id | note |\n|---|---|\n| L-1 | first |\n| L-2 | second |\n\n"
        "L-1 is the strong one; L-2 follows.\n\n"
        "### Findings\n\n| finding | lead |\n|---|---|\n| F1 | L-1 |\n| F2 | L-1 and L-2 |\n",
    )
    b = _write(tmp_path / "b.md", "## Leads\n\n| id | note |\n|---|---|\n| **`L-3`** | third \\| a piped note |\n\nL-3 again.\n")
    res = _run("items", "--ids", ids, a, b)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "exactly one owner" in res.stdout
    # A row or heading inside a fenced block is a sample, never a claim.
    fenced = _write(tmp_path / "c.md", "| L-1 | real |\n\n```\n| L-1 | sample |\n#### L-1 sample\n```\n")
    assert _run("items", "--ids", _write(tmp_path / "one.txt", "L-1\n"), fenced).returncode == 0


def test_items_one_id_claimed_by_two_files_exits_1(tmp_path):
    ids = _write(tmp_path / "ids.txt", "L-1\n")
    a = _write(tmp_path / "a.md", "| L-1 | a |\n")
    b = _write(tmp_path / "b.md", "| [L-1](x.md) | b |\n")
    res = _run("items", "--ids", ids, a, b)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "DUPLICATE: L-1 (2:" in res.stdout
    assert "rows 1" in res.stdout


def test_items_two_rows_for_one_id_in_one_table_exit_1(tmp_path):
    ids = _write(tmp_path / "ids.txt", "L-1\nL-2\n")
    bad = _write(tmp_path / "a.md", "| id | n |\n|---|---|\n| L-1 | a |\n| L-1 | again |\n| L-2 | b |\n")
    res = _run("items", "--ids", ids, bad)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "DUPLICATE: L-1 (2:" in res.stdout and "rows 2" in res.stdout
    assert "DUPLICATE: L-2" not in res.stdout
    fixed = _write(tmp_path / "b.md", "| id | n |\n|---|---|\n| L-1 | a |\n| L-2 | b |\n")
    assert _run("items", "--ids", ids, fixed).returncode == 0


def test_items_unclaimed_id_falls_back_to_file_level_ownership(tmp_path):
    ids = _write(tmp_path / "ids.txt", "L-1\n")
    a = _write(tmp_path / "a.md", "- L-1 was checked\n- L-1 held\n")
    b = _write(tmp_path / "b.md", "prose without the id\n")
    c = _write(tmp_path / "c.md", "also L-1 here\n")
    assert _run("items", "--ids", ids, a, b).returncode == 0
    res = _run("items", "--ids", ids, a, c)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "DUPLICATE: L-1 (3:" in res.stdout and "x2" in res.stdout


def test_items_repeated_heading_claim_in_one_file_exits_1(tmp_path):
    ids = _write(tmp_path / "ids.txt", "HP-01\nHP-02\n")
    bad = _write(tmp_path / "a.md", "#### HP-01 title\ntext\n#### HP-01 again\n#### HP-02 other\n")
    res = _run("items", "--ids", ids, bad)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "DUPLICATE: HP-01 (2:" in res.stdout and "headings 2" in res.stdout
    fixed = _write(tmp_path / "b.md", "#### HP-01 title\ntext\n#### HP-02 other\n")
    assert _run("items", "--ids", ids, fixed).returncode == 0


# ---- labels --expect ----------------------------------------------------


def _task(tmp_path: Path, name: str, labels: list[str]) -> str:
    bullets = "".join(f"- `{label}`\n" for label in labels)
    return _write(
        tmp_path / name,
        "## Expected Output\n\n**Required headings:** <!-- one literal label per line -->\n" + bullets + "\n**Sweep counts:**\n",
    )


def _output(tmp_path: Path, name: str, h2: list[str], h3: list[str]) -> str:
    body = "# Report\n" + "".join(f"## {h}\ntext\n" for h in h2) + "".join(f"### {h}\ntext\n" for h in h3)
    return _write(tmp_path / name, body)


def test_labels_expect_passes_when_h3_tables_differ_per_task(tmp_path):
    h2 = ["Scope", "Findings"]
    t1 = _task(tmp_path, "t1.md", ["## Scope", "## Findings", "### Step Time Split"])
    t2 = _task(tmp_path, "t2.md", ["## Scope", "## Findings", "### Predicates That Defeat an Index"])
    o1 = _output(tmp_path, "o1.md", h2, ["Step Time Split", "Extra Note"])
    o2 = _output(tmp_path, "o2.md", h2, ["Predicates That Defeat an Index"])
    # The plain union diff reads the same layer as divergent: this is the defect.
    assert _run("labels", o1, o2).returncode == 1
    res = _run("labels", "--expect", t1, o1, "--expect", t2, o2)
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.startswith("labels: 2 task/output pairs")
    assert "labels: OK" in res.stdout
    # A label without a "#" marker matches the heading text at any level.
    bare = _task(tmp_path, "bare.md", ["Step Time Split"])
    assert _run("labels", "--expect", bare, o1).returncode == 0


def test_labels_expect_fails_on_a_dropped_required_heading(tmp_path):
    t1 = _task(tmp_path, "t1.md", ["## Scope", "## Findings", "### Step Time Split"])
    good = _output(tmp_path, "good.md", ["Scope", "Findings"], ["Step Time Split"])
    bad = _output(tmp_path, "bad.md", ["Scope"], ["Step Time Split"])
    assert _run("labels", "--expect", t1, good).returncode == 0
    res = _run("labels", "--expect", t1, bad)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "lacks: ## Findings" in res.stdout
    assert "labels: FAIL" in res.stdout
    # A marker pins the level: ## Scope does not match a ### Scope heading.
    wrong_level = _output(tmp_path, "lvl.md", ["Findings"], ["Scope", "Step Time Split"])
    assert _run("labels", "--expect", t1, wrong_level).returncode == 1


def test_labels_expect_task_without_required_headings_exits_2(tmp_path):
    bare = _write(tmp_path / "t.md", "## Expected Output\n\nSomething.\n")
    placeholder_only = _write(tmp_path / "u.md", "**Required headings:** <!-- labels go here -->\n\nNext.\n")
    out = _output(tmp_path, "o.md", ["Scope"], [])
    for task in (bare, placeholder_only):
        res = _run("labels", "--expect", task, out)
        assert res.returncode == 2, res.stdout + res.stderr
        assert "cannot gate" in res.stderr
    # The other usage errors share the exit code: files beside pairs, an unreadable file.
    t1 = _task(tmp_path, "t1.md", ["## Scope"])
    assert _run("labels", "--expect", t1, out, out).returncode == 2
    res = _run("labels", "--expect", t1, str(tmp_path / "absent.md"))
    assert res.returncode == 2
    assert "cannot read" in res.stderr
