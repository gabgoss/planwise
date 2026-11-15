"""Tests for scripts/lint_markdown.py: one positive, one mutation and one usage control per rule."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import lint_markdown as lm
import pytest

REAL_CATALOG = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "references" / "callout-conventions.md"

CATALOG = """# Callouts

## 1. Callout Catalog

### `> [!constraint]` — Binding Rule

### `> [!pitfall]` — Pitfall

### `> [!binding]` — Policy

### `> [!binding]` — Sequential Chain PATTERN

### Group A: not a type

## 2. Other Section

### `> [!outside]` — heading outside section 1
"""

BASE = """# Title

## Section

> [!constraint] Name
> A rule sentence.

| A | B |
|---|---|
| x | y |

See [other](other.md) and [site](https://example.com/page).
"""


def run(tmp_path, content, *flags, name="doc.md"):
    catalog = tmp_path / "catalog.md"
    catalog.write_text(CATALOG, encoding="utf-8")
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return lm.main([*flags, "--catalog", str(catalog), str(target)])


def test_type_list_reads_section_one_only_and_skips_the_pattern_heading():
    assert lm.read_type_list(CATALOG) == ["constraint", "pitfall", "binding"]


def test_real_catalog_holds_nineteen_distinct_types():
    # read from callout-conventions.md section 1 at run time, not a copied constant
    assert len(lm.read_type_list(REAL_CATALOG.read_text(encoding="utf-8"))) == 19


def test_positive_control_clean_document_exits_zero(tmp_path, capsys):
    assert run(tmp_path, BASE) == 0
    assert "rule counts: callout-type=0, pitfall-shape=0" in capsys.readouterr().out


def test_callout_type_outside_the_list_is_report_only_until_strict(tmp_path, capsys):
    # callout-conventions.md section 1: [!example] is outside the catalogued types,
    # so it is reported, not failed, until the list is adjudicated
    mutated = BASE + "\n> [!example] Sample\n> body\n"
    assert run(tmp_path, mutated) == 0
    assert "callout-type" in capsys.readouterr().out
    assert run(tmp_path, mutated, "--strict") == 1


def test_pitfall_with_both_fields_passes_and_without_solution_fails(tmp_path, capsys):
    # callout-conventions.md pitfall entry: MUST have both Problem and Solution
    good = BASE + "\n> [!pitfall] P\n> **Problem:** a\n> **Solution:** b\n"
    bad = BASE + "\n> [!pitfall] P\n> **Problem:** a\n"
    assert run(tmp_path, good) == 0
    assert run(tmp_path, bad) == 1
    assert "pitfall-shape" in capsys.readouterr().out


def test_three_level_nesting_fails_and_two_levels_pass(tmp_path, capsys):
    # callout-conventions.md section 5: limit nesting to 2 levels
    two = BASE + "\n> [!constraint] A\n> > [!binding] B\n"
    three = BASE + "\n> [!constraint] A\n> > [!binding] B\n> > > [!binding] C\n"
    assert run(tmp_path, two) == 0
    assert run(tmp_path, three) == 1
    assert "callout-nesting" in capsys.readouterr().out


def test_two_h1_fails(tmp_path, capsys):
    # markdown-conventions.md section 1: exactly one H1
    assert run(tmp_path, BASE + "\n# Second Title\n") == 1
    assert "heading-h1" in capsys.readouterr().out


def test_h1_inside_a_fence_is_not_a_heading(tmp_path):
    assert run(tmp_path, BASE + "\n```\n# not a heading\n```\n") == 0


def test_skipped_heading_level_fails(tmp_path, capsys):
    # markdown-conventions.md section 1: never skip heading levels
    assert run(tmp_path, BASE + "\n#### Deep\n") == 1
    assert "heading-skip" in capsys.readouterr().out


def test_local_link_without_extension_fails(tmp_path, capsys):
    # markdown-conventions.md section 6: include the file extension in links
    assert run(tmp_path, BASE + "\nSee [foo](foo).\n") == 1
    assert "link-extension" in capsys.readouterr().out


def test_anchor_scheme_and_code_span_links_pass(tmp_path):
    extra = "\n[a](#top) [b](other.md#part) [c](mailto:x@y.z) and `[d](nope)`\n"
    assert run(tmp_path, BASE + extra) == 0


def test_empty_table_cell_fails_and_separator_row_is_skipped(tmp_path, capsys):
    # plain-presentation.md Tables: never leave a cell empty
    mutated = BASE.replace("| x | y |", "| x |  |")
    assert run(tmp_path, mutated) == 1
    out = capsys.readouterr().out
    assert "table-empty-cell" in out
    assert out.count("table-empty-cell:") == 1


def test_pipe_inside_a_code_span_is_not_an_empty_cell(tmp_path):
    mutated = BASE.replace("| x | y |", "| `a | b` | y |")
    assert run(tmp_path, mutated) == 0


def test_rule_file_needs_a_description(tmp_path, capsys):
    # markdown-conventions.md section 3: description on rule and skill files
    path = "rules/a-rule.md"
    assert run(tmp_path, BASE, name=path) == 1
    assert "frontmatter-description" in capsys.readouterr().out
    assert run(tmp_path, "---\ndescription: What it does\n---\n" + BASE, name=path) == 0


def test_plain_file_needs_no_description(tmp_path):
    assert run(tmp_path, BASE, name="notes/plain.md") == 0


def test_frontmatter_comment_is_not_a_heading(tmp_path):
    assert run(tmp_path, "---\ndescription: x\n# a yaml comment\n---\n" + BASE) == 0


def test_usage_control_exits_two(tmp_path, capsys):
    assert lm.main([]) == 2
    assert lm.main(["--bogus", "x.md"]) == 2
    assert lm.main(["--catalog"]) == 2
    catalog = tmp_path / "catalog.md"
    catalog.write_text(CATALOG, encoding="utf-8")
    assert lm.main(["--catalog", str(catalog), str(tmp_path / "missing.md")]) == 2
    assert lm.main(["--catalog", str(tmp_path / "nope.md"), str(catalog)]) == 2
    assert "Error:" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_exits_zero(flag, capsys):
    assert lm.main([flag]) == 0
    assert "Exit codes" in capsys.readouterr().out
