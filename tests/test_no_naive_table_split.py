#!/usr/bin/env python3
"""Suite-level guard: no script outside markdown_parser.py may hand-roll a
naive `.split("|")`-shaped table-row parse.

A naive split on a bare pipe silently misparses any row whose cell escapes a
literal pipe (`` `git diff --name-only \\| grep dir` `` is the correct way to
write a shell pipeline inside a markdown table cell): readers drop the row
with no warning, writers mutate the neighbouring column. The shared,
escape-aware helper (`split_row_raw` / `split_row_cells`) exists precisely to
prevent that class of defect, and this test is what stops the next script
from reaching past it.

Detection strategy: `tokenize` the source and look for the exact five-token
sequence a real call produces -- `OP(.) NAME(split|strip|lstrip|rstrip)
OP(() STRING("|"|'|') OP())`. This is deliberately NOT a text/regex scan of
the raw source, and that is what makes comment and docstring mentions safe
by construction, with no whole-file exemption list:

  * A `# comment` mentioning the pattern is ONE COMMENT token. Comment
    tokens are dropped from the token stream examined for the five-token
    sequence entirely, so their text is never decomposed into separate
    NAME/OP tokens.
  * A docstring paragraph mentioning the pattern (e.g. `` `line.split("|")`
    `` inside a module docstring) lives entirely inside ONE triple-quoted
    STRING token -- the whole docstring, quotes included, is a single
    token. Its internal text is never re-tokenized, so the five-token
    adjacency the scanner looks for cannot arise from it. Only a STRING
    token whose OWN value is exactly `"|"` or `'|'` -- the real naive-split
    argument -- can ever complete the pattern.

The two real prose mentions this guards against (as module docstring/comment
text) are exactly this shape, which is why they were never in scanner scope
to begin with, and why the fix needed no whole-file exemption list -- only
one NAMED, policy-level exemption for the module that implements pipe
splitting in the first place.

Run with:  python -m pytest tests/test_no_naive_table_split.py -q
"""

import io
import sys
import tokenize
from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
)

# Allow imports whether pytest is launched from the repo root or tests/.
sys.path.insert(0, str(SCRIPTS_DIR))

import markdown_parser
import migrate_backlog_index
import migrate_backlog_support

# The one permitted implementation site. markdown_parser.py is the module
# that OWNS pipe-splitting semantics for every other script; every other
# script must go through its `split_row_raw` / `split_row_cells` helpers
# instead of hand-rolling a split. The exemption is by NAME, not by "every
# file that currently matches" -- as measured, the module's real
# implementation does not itself contain the naive shape at all (it splits
# on a compiled unescaped-pipe regex, never a bare `.split("|")`), so this
# exemption is a standing policy allowance for that module's role, not a
# mask over an existing violation.
_EXEMPT_FILENAMES = frozenset({"markdown_parser.py"})

_TARGET_METHODS = {"split", "strip", "lstrip", "rstrip"}
_PIPE_LITERALS = {'"|"', "'|'"}

# Only these token types can participate in the real call syntax we are
# looking for. Filtering to this allow-list is what drops COMMENT, NL,
# NEWLINE, INDENT, DEDENT, and f-string sub-tokens from the adjacency scan --
# none of those can ever be part of `. split ( "|" )`.
_MEANINGFUL_TYPES = {tokenize.OP, tokenize.NAME, tokenize.STRING, tokenize.NUMBER}


def find_naive_pipe_splits(source: str) -> list[tuple[int, str]]:
    """Return (line_number, method_name) for every real naive pipe split.

    Raises no exception for a file that fails to tokenize -- ``tokenize``
    errors are surfaced by letting the caller decide; every file under
    ``plugins/planwise/scripts/`` is live, executable Python, so a tokenize
    failure there is itself a defect worth seeing rather than swallowing.
    """
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    code_tokens = [t for t in tokens if t.type in _MEANINGFUL_TYPES]

    hits: list[tuple[int, str]] = []
    for i in range(len(code_tokens) - 4):
        dot, name, lparen, string, rparen = code_tokens[i : i + 5]
        if (
            dot.type == tokenize.OP
            and dot.string == "."
            and name.type == tokenize.NAME
            and name.string in _TARGET_METHODS
            and lparen.type == tokenize.OP
            and lparen.string == "("
            and string.type == tokenize.STRING
            and string.string in _PIPE_LITERALS
            and rparen.type == tokenize.OP
            and rparen.string == ")"
        ):
            hits.append((dot.start[0], name.string))
    return hits


def scan_scripts_dir(
    scripts_dir: Path, *, exempt: frozenset = _EXEMPT_FILENAMES
) -> dict[str, list[tuple[int, str]]]:
    """Scan every ``.py`` under ``scripts_dir`` (excluding ``exempt`` names).

    Returns a mapping of relative path -> hits, containing only files with at
    least one hit. An empty dict is the passing result.
    """
    violations: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(scripts_dir.glob("**/*.py")):
        if path.name in exempt:
            continue
        source = path.read_text(encoding="utf-8")
        hits = find_naive_pipe_splits(source)
        if hits:
            violations[str(path.relative_to(scripts_dir))] = hits
    return violations


# ---------------------------------------------------------------------------
# The live-tree gate
# ---------------------------------------------------------------------------
def test_no_naive_pipe_split_outside_markdown_parser():
    violations = scan_scripts_dir(SCRIPTS_DIR)
    assert violations == {}, (
        "naive .split('|')/.strip('|') (or lstrip/rstrip) found outside "
        f"markdown_parser.py: {violations}"
    )


def test_markdown_parser_itself_has_zero_hits_without_its_name_exemption():
    # Proves the exemption above is a policy allowance, not a mask: even
    # scanned WITHOUT the name-based skip, the module's real implementation
    # produces zero hits. Its two prose mentions of the pattern are tolerated
    # by the token-sequence discrimination itself (see module docstring),
    # not by this exemption.
    source = (SCRIPTS_DIR / "markdown_parser.py").read_text(encoding="utf-8")
    assert find_naive_pipe_splits(source) == []


# ---------------------------------------------------------------------------
# Discrimination proof: the scanner must be able to fail AND pass
# ---------------------------------------------------------------------------
def test_scanner_flags_a_planted_real_violation(tmp_path):
    planted = tmp_path / "planted_violation.py"
    planted.write_text(
        'def parse_row(line):\n'
        '    return [c.strip() for c in line.strip().strip("|").split("|")]\n',
        encoding="utf-8",
    )
    hits = find_naive_pipe_splits(planted.read_text(encoding="utf-8"))
    assert hits, "scanner failed to flag a real naive .strip('|').split('|') call"
    assert {method for _, method in hits} == {"strip", "split"}


def test_scanner_flags_the_single_quote_and_lstrip_rstrip_variants(tmp_path):
    planted = tmp_path / "planted_variants.py"
    planted.write_text(
        "a = line.split('|')\n"
        "b = line.rstrip('|')\n"
        'c = line.lstrip("|")\n',
        encoding="utf-8",
    )
    hits = find_naive_pipe_splits(planted.read_text(encoding="utf-8"))
    assert {method for _, method in hits} == {"split", "rstrip", "lstrip"}
    assert len(hits) == 3


def test_scanner_tolerates_comment_and_docstring_only_mentions(tmp_path):
    clean = tmp_path / "clean_prose_only.py"
    clean.write_text(
        '"""Module docstring mentioning the shape of a plain '
        'line.split("|") for illustration only, never executed."""\n'
        "\n"
        "def parse_row(line):\n"
        "    # mirroring str.strip(\"|\") without eating an empty first cell\n"
        "    return line.strip()\n",
        encoding="utf-8",
    )
    assert find_naive_pipe_splits(clean.read_text(encoding="utf-8")) == []


def test_scanner_ignores_split_with_a_non_pipe_argument(tmp_path):
    # A method-name-and-shape match on an unrelated separator must not
    # false-positive -- only the bare pipe literal is the defect class.
    clean = tmp_path / "unrelated_split.py"
    clean.write_text('line.split(",")\nline.strip()\n', encoding="utf-8")
    assert find_naive_pipe_splits(clean.read_text(encoding="utf-8")) == []


def test_scanner_flags_across_a_multiline_call_with_an_interleaved_comment(tmp_path):
    # A stray comment between the open paren and the string argument must
    # not hide a real call from the scanner -- COMMENT/NL tokens are
    # dropped from the adjacency window before matching.
    planted = tmp_path / "planted_multiline.py"
    planted.write_text(
        "def parse_row(line):\n"
        "    return line.split(  # noqa: keep the pipe\n"
        '        "|"\n'
        "    )\n",
        encoding="utf-8",
    )
    hits = find_naive_pipe_splits(planted.read_text(encoding="utf-8"))
    assert hits and hits[0][1] == "split"


def test_scan_scripts_dir_reports_per_file_and_skips_named_exemptions(tmp_path):
    (tmp_path / "markdown_parser.py").write_text(
        'x = line.split("|")\n', encoding="utf-8"
    )
    (tmp_path / "some_other_script.py").write_text(
        'x = line.split("|")\n', encoding="utf-8"
    )
    violations = scan_scripts_dir(tmp_path)
    assert "markdown_parser.py" not in violations
    assert "some_other_script.py" in violations


# ---------------------------------------------------------------------------
# The code-aware retry splitter
# ---------------------------------------------------------------------------
def test_code_aware_split_keeps_a_pipe_inside_backticks():
    line = "| LL-001 | Title `a | b` | process |"
    assert len(markdown_parser.split_row_cells(line)) == 4
    cells = markdown_parser.split_row_cells_code_aware(line)
    assert cells == ["LL-001", "Title `a | b`", "process"]


def test_code_aware_split_matches_plain_split_outside_code():
    rows = [
        "| a | b | c |",
        "| a \\| b | c |",
        "|  padded  | `x` | |",
        "| `y` | z \\| w | `q` |",
    ]
    for row in rows:
        assert markdown_parser.split_row_cells_code_aware(row) == markdown_parser.split_row_cells(row)


def test_an_escaped_backtick_opens_no_span():
    # `\`` is a literal backtick, so the later pipe is a real cell boundary: the row has five cells,
    # not four. A caller comparing that count with a four-cell header keeps the finding.
    line = "| a | x \\` y | z ` | w |"
    plain = markdown_parser.split_row_cells(line)
    assert len(plain) == 4
    assert markdown_parser.split_row_cells_code_aware(line) == plain
    # A backslash before the closing backtick leaves the span open, so the opener is unbalanced.
    assert markdown_parser.split_row_cells_code_aware("| `a \\` | b |") == ["`a \\`", "b"]
    assert markdown_parser.split_row_cells_code_aware("| `a | b \\` | c |") == ["`a", "b \\`", "c"]


def test_a_backtick_pair_across_two_plain_cells_is_a_code_span():
    # CommonMark closes a backtick run at the next run of equal length, wherever it sits. In a table the
    # row is cut into cells first, but this reader's contract is the retry only, and it accepts the
    # merged result only when the count then equals the header's. A pair that spans two cells merges them.
    line = "| a | b` | `c | d |"
    assert len(markdown_parser.split_row_cells(line)) == 4
    assert markdown_parser.split_row_cells_code_aware(line) == ["a", "b` | `c", "d"]


def test_unbalanced_backtick_does_not_swallow_the_row():
    line = "| a | `b | c | d |"
    plain = markdown_parser.split_row_cells(line)
    cells = markdown_parser.split_row_cells_code_aware(line)
    # An opening backtick with no close opens no span, so the count equals the
    # plain split's and a caller comparing it with the header keeps the finding.
    assert len(cells) == len(plain) == 4
    assert len(cells) > 3


# ---------------------------------------------------------------------------
# The backlog resolve_rows retry
# ---------------------------------------------------------------------------
def _resolve_backlog_rows(tmp_path, feature_cell):
    (tmp_path / "item.md").write_text("x\n", encoding="utf-8")
    text = (
        "| ID | Feature | Files |\n"
        "|----|---------|-------|\n"
        f"| 1 | {feature_cell} | [a](item.md) |\n"
    )
    header = migrate_backlog_support.row_cells(text.split("\n")[0])
    roles, _ = migrate_backlog_support.column_map(header)
    config = {"_backlog_dir": tmp_path, "_archive_dir": tmp_path}
    rows = migrate_backlog_index.resolve_rows(text, 0, roles, config, tmp_path / "index.md", [])
    return rows, roles, text


def test_backlog_resolve_rows_retry_accepts_a_piped_code_row(tmp_path):
    rows, roles, _ = _resolve_backlog_rows(tmp_path, "`x | y`")
    assert len(rows) == 1
    assert len(rows[0]["cells"]) == len(roles)
    assert rows[0]["cells"][roles["feature"]] == "`x | y`"


def test_backlog_report_applies_the_same_retry_as_the_write(tmp_path):
    # The row's item file has no frontmatter. The write resolves the piped-code row to it, so the report
    # must count the file as referenced, not as unreferenced.
    (tmp_path / "Archive").mkdir()
    (tmp_path / "BB-001-a.md").write_text("# no frontmatter\n", encoding="utf-8")
    text = ("# Backlog\n\n## Backlog Items\n\n| ID | Feature | Files |\n|----|----|----|\n"
            "| BB-001 | run `a | b` | [a](BB-001-a.md) |\n\n*Last Updated: 2026-01-01*\n")
    index = tmp_path / "00-Index-Backlog.md"
    index.write_text(text, encoding="utf-8")
    header_idx, roles = migrate_backlog_support.classify_shape(text)[1]
    config = {"_backlog_dir": tmp_path, "_archive_dir": tmp_path / "Archive", "_project_root": tmp_path,
              "_planwise_root": tmp_path}
    written = migrate_backlog_index.resolve_rows(text, header_idx, roles, config, index, [])
    assert [r["path"].name for r in written] == ["BB-001-a.md"]
    items = migrate_backlog_index.build_report(config, index)["items"]
    assert items["without_frontmatter"] == 1
    assert items["unreferenced_without_frontmatter"] == 0


def test_backlog_checks_read_the_prefix_of_an_id_after_a_piped_code_cell():
    import migrate_backlog_checks
    lines = ["| Feature | ID | Files |", "|----|----|----|", "| run `a | b` | BB-001 | [a](x.md) |"]
    # the plain split reads the ID column as "b`" and finds no prefix
    assert migrate_backlog_checks.items_prefixes(lines, 0) == frozenset({"BB"})


def test_backlog_checks_read_a_blocks_cell_after_a_piped_code_cell():
    import migrate_backlog_checks
    lines = ["| ID | Feature | Blocks | Files |", "|----|----|----|----|",
             "| BB-001 | run `a | b` | ZZ-002 | [a](x.md) |"]
    problems = []
    migrate_backlog_checks._items_blocks(lines, 0, frozenset({"BB"}), problems)
    assert len(problems) == 1 and "ZZ-002" in problems[0]


def test_backlog_resolve_rows_retry_keeps_an_escaped_pipe(tmp_path):
    rows, roles, _ = _resolve_backlog_rows(tmp_path, r"`x | y` and a\|b")
    ordinary = migrate_backlog_support.row_cells(r"| 1 | a\|b | [a](item.md) |")
    assert ordinary[1] == r"a\|b"
    assert len(rows) == 1
    assert rows[0]["cells"][roles["feature"]] == r"`x | y` and a\|b"
