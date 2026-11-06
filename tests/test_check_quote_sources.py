"""Tests for scripts/check_quote_sources.py (the quote-source checker)."""

from __future__ import annotations

import os
import shutil
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
        "Prose ends the labelled run.\n"
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


def test_quote_cutting_a_word_does_not_match(tmp_path):
    deliverable = "Quote:\n\n```\nun passed\n```\n"
    result = _run(tmp_path, deliverable, "the run passed\n")
    assert result.returncode == 1
    assert "UNMATCHED" in result.stdout
    assert _run(tmp_path, "Quote:\n\n```\nrun passed\n```\n", "the run passed\n").returncode == 0


def test_empty_labelled_block_is_its_own_finding(tmp_path):
    result = _run(tmp_path, "Verbatim:\n\n```\n```\n", SOURCE_TEXT)
    assert result.returncode == 1
    assert "EMPTY " in result.stdout
    assert "0 unmatched; 1 empty" in result.stdout


def test_prose_using_the_word_is_not_a_label():
    raw = "Use double quotes around the path:\n\n```bash\nls \"a b\"\n```\n"
    assert cqs.extract_quote_blocks(raw) == []


def test_accepted_label_line_shapes():
    for label in ("Verbatim", "**Quote:**", "Quoted from the source:", "The line (verbatim):", "Source quote:"):
        blocks = cqs.extract_quote_blocks(f"{label}\n\n```\nx\n```\n")
        assert [b.lines for b in blocks] == [["x"]], label


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


TABLE_EXACT = (
    "# Report\n"
    "\n"
    "| # | Claim (verbatim) | Line |\n"
    "|---|---|---:|\n"
    "| C1 | Some context line. | 3 |\n"
)


def _cells(raw: str) -> list[tuple[str, int, list[str]]]:
    return [(b.kind, b.line, b.lines) for b in cqs.extract_quote_blocks(raw)]


def test_table_cell_exact_exits_zero(tmp_path):
    result = _run(tmp_path, TABLE_EXACT, SOURCE_TEXT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 quote block(s) checked" in result.stdout
    assert "0 unmatched" in result.stdout


def test_table_cell_one_changed_word_names_the_cell_line(tmp_path):
    changed = TABLE_EXACT.replace("Some context line.", "Some contest line.")
    result = _run(tmp_path, changed, SOURCE_TEXT)
    assert result.returncode == 1
    assert "deliverable.md:5 (table-cell)" in result.stdout
    assert "Some contest line." in result.stdout
    assert "1 unmatched" in result.stdout


def test_table_cell_escaped_pipe_is_one_cell(tmp_path):
    deliverable = "| Quote | Note |\n|---|---|\n| run a \\| b now | n/a |\n"
    assert _cells(deliverable) == [("table-cell", 3, ["run a | b now"])]
    assert _run(tmp_path, deliverable, "then run a | b now today\n").returncode == 0


def test_table_cell_two_quoted_spans_are_each_compared(tmp_path):
    two = (
        "| Holding sentence (verbatim) |\n"
        "|---|\n"
        '| "Some context line." (line 3); pair "Another line after it." (line 5) |\n'
    )
    blocks = cqs.extract_quote_blocks(two)
    assert len(blocks) == 1
    assert [span.lines for span in blocks[0].spans] == [["Some context line."], ["Another line after it."]]
    matched = _run(tmp_path, two, SOURCE_TEXT)
    assert matched.returncode == 0
    assert "SPAN-ONLY" in matched.stdout
    changed = _run(tmp_path, two.replace("Another line", "Another row"), SOURCE_TEXT)
    assert changed.returncode == 1
    assert "first line: Another row after it." in changed.stdout
    assert "1 quote block(s) checked" in changed.stdout
    assert "1 unmatched" in changed.stdout
    assert "0 span-only" in changed.stdout


def test_table_unlabelled_column_extracts_nothing():
    assert _cells("| Claim | Note |\n|---|---|\n| one | two |\n") == []
    assert _cells("| Note | Quote |\n|---|---|\n| one | two |\n") == [("table-cell", 3, ["two"])]


def test_table_header_label_is_whole_word():
    assert _cells("| Unquoted note |\n|---|\n| one |\n") == []


def test_table_inside_a_fence_extracts_nothing():
    table = "| Quote |\n|---|\n| one |\n"
    assert _cells("```\n" + table + "```\n") == []
    assert _cells("~~~text\n" + table + "~~~\n") == []


def test_labelled_header_without_a_separator_row_is_not_a_table():
    assert _cells("| Quote |\n| one |\n") == []
    assert _cells("| Quote | Note |\n|---|\n| one | two |\n") == []


def test_table_empty_cell_is_not_a_quote_site(tmp_path):
    deliverable = "| Quote | Note |\n|---|---|\n|  | two |\n"
    assert _cells(deliverable) == []
    result = _run(tmp_path, deliverable, SOURCE_TEXT)
    assert result.returncode == 0
    assert "0 quote block(s) checked" in result.stdout


def test_table_ends_at_the_first_non_row_line():
    raw = "| Quote |\n|---|\n| one |\n\n| two |\n"
    assert _cells(raw) == [("table-cell", 3, ["one"])]


def test_table_crlf_deliverable_keeps_no_carriage_return():
    assert _cells(TABLE_EXACT.replace("\n", "\r\n")) == [("table-cell", 5, ["Some context line."])]


def test_unmatched_line_survives_a_narrow_stdout_encoding(tmp_path):
    deliv = _write(tmp_path / "deliverable.md", "| Quote |\n|---|\n| a → b |\n")
    src = _write(tmp_path / "source.md", SOURCE_TEXT)
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(deliv), "--source", str(src)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
    )
    assert result.returncode == 1, result.stderr
    assert "UNMATCHED" in result.stdout
    assert "1 unmatched" in result.stdout


def test_table_pipe_in_code_span_keeps_the_column():
    raw = "| # | Quote | Line |\n|---|---|---|\n| C1 | `a|b` | 3 |\n"
    assert _cells(raw) == [("table-cell", 3, ["`a|b`"])]


REAL = "the real line\n"


def test_row_wider_than_the_header_is_a_malformed_finding(tmp_path):
    deliverable = "| Id | Quote | Note |\n|---|---|---|\n| 1 | the real | invented tail | n |\n"
    result = _run(tmp_path, deliverable, REAL)
    assert result.returncode == 1
    assert "MALFORMED" in result.stdout
    assert "deliverable.md:3 (table-row)" in result.stdout
    assert "0 quote block(s) checked" in result.stdout
    assert "1 malformed" in result.stdout


def test_row_narrower_than_the_header_is_a_malformed_finding(tmp_path):
    result = _run(tmp_path, "| Id | Note | Quote |\n|---|---|---|\n| 1 | n |\n", REAL)
    assert result.returncode == 1
    assert "deliverable.md:3 (table-row)" in result.stdout
    assert "1 malformed" in result.stdout


def test_row_the_code_aware_retry_repairs_is_not_malformed(tmp_path):
    result = _run(tmp_path, "| Id | Quote | Note |\n|---|---|---|\n| 1 | `a|b` | n |\n", "see `a|b` here\n")
    assert result.returncode == 0, result.stdout
    assert "0 malformed" in result.stdout


def test_altered_cell_around_a_matching_span_is_reported_span_only(tmp_path):
    deliverable = '| Quote |\n|---|\n| Error: file "foo" missing |\n'
    result = _run(tmp_path, deliverable, 'Error: file "foo" not found\n')
    assert result.returncode == 0, result.stdout
    assert "SPAN-ONLY" in result.stdout
    assert "deliverable.md:3" in result.stdout
    assert result.stdout.rstrip().endswith("0 unmatched; 0 empty; 0 malformed; 1 span-only")


def test_cell_that_is_one_span_and_nothing_else_is_a_full_match(tmp_path):
    result = _run(tmp_path, '| Quote |\n|---|\n|   "the real line"   |\n', REAL)
    assert result.returncode == 0, result.stdout
    assert "SPAN-ONLY" not in result.stdout
    assert "0 span-only" in result.stdout
    altered = _run(tmp_path, '| Quote |\n|---|\n| "the fake line" |\n', REAL)
    assert altered.returncode == 1
    assert "first line: the fake line" in altered.stdout


def test_exact_cell_holding_double_quotes_passes_whole(tmp_path):
    result = _run(tmp_path, '| Quote |\n|---|\n| Error: file "foo" not found |\n', 'Error: file "foo" not found\n')
    assert result.returncode == 0, result.stdout
    assert "SPAN-ONLY" not in result.stdout
    assert "0 span-only" in result.stdout


def test_inch_marks_are_compared_as_a_whole_cell_first(tmp_path):
    deliverable = '| Quote |\n|---|\n| a 5" disk and a 3" disk |\n'
    exact = _run(tmp_path, deliverable, 'a 5" disk and a 3" disk\n')
    assert exact.returncode == 0, exact.stdout
    assert "0 span-only" in exact.stdout
    assert _run(tmp_path, deliverable, 'a 5" disk and a 4" disk\n').returncode == 1


def test_blank_quoted_span_does_not_crash_the_comparison(tmp_path):
    result = _run(tmp_path, '| Quote |\n|---|\n| say " " here |\n', REAL)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "UNMATCHED" in result.stdout


def test_code_span_pipe_in_a_header_cell_keeps_the_table(tmp_path):
    deliverable = "| `a|b` | Quote |\n|---|---|\n| x | invented |\n"
    assert _cells(deliverable) == [("table-cell", 3, ["invented"])]
    assert _run(tmp_path, deliverable, REAL).returncode == 1


def test_backticks_in_a_backtick_info_string_open_no_fence():
    raw = "```inline``` is prose\n\nQuote:\n\n```\ninvented\n```\n"
    assert _cells(raw) == [("fenced", 6, ["invented"])]


def test_tilde_info_string_may_hold_backticks():
    assert _cells("~~~quote `x`\nalpha\n~~~\n") == [("fenced", 2, ["alpha"])]


def test_byte_order_mark_does_not_hide_a_first_line_fence(tmp_path):
    result = _run(tmp_path, "﻿```quote\ninvented\n```\n", REAL)
    assert result.returncode == 1
    assert "1 quote block(s) checked" in result.stdout
    assert _run(tmp_path, "```quote\n# Title\n```\n", "﻿# Title\n").returncode == 0


def test_blockquote_run_after_a_labelled_run_is_a_further_block(tmp_path):
    raw = "Verbatim:\n> the real line\n\n> invented\n\n\n> third\n"
    assert _cells(raw) == [
        ("blockquote", 2, ["the real line"]),
        ("blockquote", 4, ["invented"]),
        ("blockquote", 7, ["third"]),
    ]
    assert _run(tmp_path, raw, REAL).returncode == 1


def test_prose_between_runs_ends_the_label():
    assert _cells("Verbatim:\n> alpha\n\nProse.\n\n> beta\n") == [("blockquote", 2, ["alpha"])]


def test_lazy_continuation_line_joins_a_labelled_run(tmp_path):
    raw = "Verbatim:\n> the real\ninvented tail\n\nProse after it.\n"
    assert _cells(raw) == [("blockquote", 2, ["the real", "invented tail"])]
    assert _run(tmp_path, raw, "the real\nline\n").returncode == 1


def test_a_heading_or_list_item_is_not_a_lazy_continuation():
    assert _cells("Verbatim:\n> alpha\n# Head\n") == [("blockquote", 2, ["alpha"])]
    assert _cells("Verbatim:\n> alpha\n- item\n") == [("blockquote", 2, ["alpha"])]
    assert _cells("Verbatim:\n> alpha\n---\n") == [("blockquote", 2, ["alpha"])]


def test_four_space_fence_under_a_list_item_is_read_and_dedented(tmp_path):
    raw = "1. Quote:\n\n    ```\n    the real line\n    ```\n"
    assert _cells(raw) == [("fenced", 4, ["the real line"])]
    assert _run(tmp_path, raw, REAL).returncode == 0


def test_two_space_fence_body_loses_the_opener_indent(tmp_path):
    raw = "Quote:\n\n  ```\n  the real line\n    kept two\nflush\n  ```\n"
    assert _cells(raw) == [("fenced", 4, ["the real line", "  kept two", "flush"])]


def test_deeply_indented_fence_line_does_not_close_a_flush_fence():
    raw = "Quote:\n\n```\nalpha\n    ```\nbeta\n```\n"
    assert _cells(raw) == [("fenced", 4, ["alpha", "    ```", "beta"])]


def test_indented_blockquote_is_read(tmp_path):
    raw = "1. Quote:\n\n    > the real line\n"
    assert _cells(raw) == [("blockquote", 3, ["the real line"])]
    assert _run(tmp_path, raw, REAL).returncode == 0


def test_isolated_interpreter_resolves_the_sibling_import(tmp_path):
    deliv = _write(tmp_path / "deliverable.md", "Quote:\n\n```\nthe real line\n```\n")
    src = _write(tmp_path / "source.md", REAL)
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), str(deliv), "--source", str(src)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 quote block(s) checked" in result.stdout


def test_missing_sibling_module_exits_two_with_an_error_line(tmp_path):
    lone = tmp_path / "lone"
    lone.mkdir()
    shutil.copy(SCRIPT, lone / SCRIPT.name)
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(lone / SCRIPT.name), "x.md", "--source", "x.md"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("error:")


def test_placeholder_cells_are_not_quote_sites(tmp_path):
    for cell in ("none", "n/a", "none (gap)", "None", "N/A", "NONE (GAP)"):
        assert _cells(f"| Quote |\n|---|\n| {cell} |\n") == [], cell
    assert _cells("| Quote |\n|---|\n| none of it |\n") == [("table-cell", 3, ["none of it"])]
    assert _run(tmp_path, "| Quote |\n|---|\n| n/a |\n", REAL).returncode == 0


def test_header_label_is_the_whole_cell_or_a_final_parenthetical():
    for header in ("Quote", "quoted", "Verbatim", "Claim (verbatim)", "Holding sentence (verbatim)"):
        assert _cells(f"| {header} |\n|---|\n| one |\n") == [("table-cell", 3, ["one"])], header
    for header in ("Quote source", "Verbatim?", "Source (verbatim) note", "Claim verbatim"):
        assert _cells(f"| {header} |\n|---|\n| one |\n") == [], header


def test_fence_info_label_is_a_whole_token():
    assert _cells('```python title="quote.py"\nx = 1\n```\n') == []
    assert _cells("```text verbatim\nalpha\n```\n") == [("fenced", 2, ["alpha"])]


def test_one_wrapping_code_span_or_emphasis_pair_is_not_compared(tmp_path):
    for cell in ("`the real line`", "**the real line**", "*the real line*", "_the real line_"):
        result = _run(tmp_path, f"| Quote |\n|---|\n| {cell} |\n", REAL)
        assert result.returncode == 0, cell + result.stdout
    assert _run(tmp_path, "| Quote |\n|---|\n| **the fake line** |\n", REAL).returncode == 1


def test_cell_is_compared_in_its_escaped_pipe_form_too(tmp_path):
    deliverable = "| Quote |\n|---|\n| run a \\| b now |\n"
    assert _run(tmp_path, deliverable, "| run a \\| b now | x |\n").returncode == 0


def test_second_table_after_the_first_with_no_blank_line():
    assert _cells("| Quote |\n|---|\n| one |\n| Note |\n|---|\n| two |\n") == [("table-cell", 3, ["one"])]
    assert _cells("| Note |\n|---|\n| one |\n| Quote |\n|---|\n| two |\n") == [("table-cell", 6, ["two"])]
    assert _cells("| Quote |\n|---|\n| one |\n| Quote |\n|---|\n| two |\n") == [
        ("table-cell", 3, ["one"]),
        ("table-cell", 6, ["two"]),
    ]


def test_thematic_break_after_a_row_does_not_reread_the_row_as_a_header():
    assert _cells("| Quote |\n|---|\n| one |\n---\n") == [("table-cell", 3, ["one"])]


def test_labelled_blockquote_wrapping_a_fence_drops_the_fence_lines(tmp_path):
    raw = "Verbatim:\n> ```\n> the real line\n> ```\n"
    assert _cells(raw) == [("blockquote", 2, ["the real line"])]
    assert _run(tmp_path, raw, REAL).returncode == 0
