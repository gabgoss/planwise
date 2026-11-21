"""Tests for the section tail rules of scripts/plan_build.py.

A section body ends before the template's closing `---`, so a trailing `---` in the body is
dropped. The file footer, the text after the last `---` of a span that runs to end of file,
belongs to the file: the build, `omit_section` and the lint all leave it alone.

Fixtures are real renders of the templates. The footer is the template's own closing text
(`**Next Step:** Execute Task 1`), appended the way the orchestration template carries it.
"""

import re
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

import plan_build as pb
import scaffold_plan as sp
from test_plan_build import TASK_DOC, TEMPLATES, make_spec

FOOTER = "**Next Step:** Execute Task 1"
LAST_ORCH = "## Post-Session Checklist"
LAST_TASK = "## Notes for Agent"
DOUBLED = re.compile(r"^---\n\n---$", re.MULTILINE)


@pytest.fixture(scope="module")
def rendered():
    return sp.render_all(make_spec(), TEMPLATES)[0]


def _file(rendered, doc):
    """(relative path, text) of the rendered file for `doc`."""
    (rel,) = [k for k in rendered if pb.doc_id(k) == doc]
    return rel, rendered[rel]


def _patterns(rel):
    return sp.template_heading_sets(TEMPLATES)[sp.file_kind(rel)][0]


def _footed(text):
    """The text with the template's closing footer after its last `---`."""
    return text.rstrip("\n") + f"\n\n{FOOTER}\n"


def _apply(rel, text, heading, body):
    return pb.apply_doc(text, {"fills": {}, "sections": {heading: body}}, _patterns(rel))[0]


@pytest.fixture(scope="module")
def orch(rendered):
    return _file(rendered, "S01-01-ORCH")


# ---- case A: a body that ends in its own separator

def test_a_body_ending_in_a_separator_renders_one_separator(orch):
    rel, text = orch
    heading = pb.doc_index({rel: text}, TEMPLATES)["S01-01-ORCH"]["headings"][0]
    plain = _apply(rel, text, heading, "new first")
    closed = _apply(rel, text, heading, "new first\n\n---")
    assert closed == plain
    assert not DOUBLED.search(closed)
    assert closed.count("\n---\n") == text.count("\n---\n")


def test_a_the_helper_drops_one_closing_separator_and_keeps_a_body_of_only_one():
    # a body of only `---` has no text to keep, so the helper returns it as it is
    assert pb.drop_closing_separator("---") == "---"
    assert pb.drop_closing_separator("text\n\n---\n\n") == "text"
    assert pb.drop_closing_separator("text") == "text"


# ---- case B: the footer of the last section

def test_b_the_last_h2_keeps_its_separator_and_the_footer(orch):
    rel, text = orch
    footed = _footed(text)
    info = pb.doc_index({rel: footed}, TEMPLATES)["S01-01-ORCH"]
    assert info["footers"] == [LAST_ORCH]
    out = _apply(rel, footed, LAST_ORCH, "new body")
    assert out.endswith(f"\n{LAST_ORCH} <!-- REQUIRED -->\n\nnew body\n\n---\n\n{FOOTER}\n")
    ended = _apply(rel, footed, LAST_ORCH, "new body\n\n---")
    assert ended == out


def test_b_control_an_unfooted_file_ends_with_its_separator(orch):
    rel, text = orch
    info = pb.doc_index({rel: text}, TEMPLATES)["S01-01-ORCH"]
    assert info["footers"] == []
    out = _apply(rel, text, LAST_ORCH, "new body")
    assert out.endswith(f"\n{LAST_ORCH} <!-- REQUIRED -->\n\nnew body\n\n---\n")


# ---- case C: an H3 that runs to end of file

def _plan_specific(text, closing):
    return text.rstrip("\n") + f"\n\n## Plan-Specific Sections\n\nIntro line.\n\n### Extra Note\n\nold note\n{closing}"


def test_c_an_h3_that_runs_to_end_of_file_keeps_the_footer(orch):
    rel, text = orch
    footed = _plan_specific(text, f"\n---\n\n{FOOTER}\n")
    info = pb.doc_index({rel: footed}, TEMPLATES)["S01-01-ORCH"]
    assert "### Extra Note" in info["footers"]
    out = _apply(rel, footed, "### Extra Note", "new note")
    assert out.endswith(f"### Extra Note\n\nnew note\n\n---\n\n{FOOTER}\n")
    assert "old note" not in out


# ---- case D: a separator inside a fence is not the footer separator

FENCED = "\n```text\n---\ninside the fence\n```\n"


def test_d_a_separator_inside_a_fence_is_not_a_footer(orch):
    rel, text = orch
    fenced = _plan_specific(text, FENCED)
    info = pb.doc_index({rel: fenced}, TEMPLATES)["S01-01-ORCH"]
    assert info["footers"] == []
    out = _apply(rel, fenced, "### Extra Note", "new note")
    assert out.endswith("### Extra Note\n\nnew note\n")
    assert "inside the fence" not in out


def test_d_control_the_same_lines_outside_a_fence_are_a_footer(orch):
    rel, text = orch
    bare = _plan_specific(text, "\n---\ninside the fence\n")
    info = pb.doc_index({rel: bare}, TEMPLATES)["S01-01-ORCH"]
    assert "### Extra Note" in info["footers"]


# ---- case E: the lint

def _lint(rendered, body_text, with_footer):
    rel, text = _file(rendered, TASK_DOC)
    index = pb.doc_index({rel: _footed(text) if with_footer else text}, TEMPLATES)
    docs, errors = pb.parse_bodies(f"<!-- doc: {TASK_DOC} -->\n\n<!-- section: {LAST_TASK} -->\n\n{body_text}\n", "x.md")
    assert errors == []
    lines, _rows = pb.lint_bodies(index, docs)
    return [ln for ln in lines if "restates the file footer" in ln]


def test_e_lint_names_a_body_that_restates_the_footer(rendered):
    found = _lint(rendered, f"Read the spec first.\n\n---\n\n{FOOTER}", with_footer=True)
    assert len(found) == 1
    assert found[0].startswith(f"doc={TASK_DOC} key=section: {LAST_TASK}: ")


def test_e_lint_passes_the_same_body_without_the_footer(rendered):
    assert _lint(rendered, "Read the spec first.", with_footer=True) == []
    assert _lint(rendered, "Read the spec first.\n\n---", with_footer=True) == []


def test_e_control_a_file_with_no_footer_never_reports_one(rendered):
    assert _lint(rendered, f"Read the spec first.\n\n---\n\n{FOOTER}", with_footer=False) == []


def test_e_an_info_without_a_footers_key_reads_as_no_footer_section():
    body = {"fills": {}, "sections": {"## One": f"text\n\n---\n\n{FOOTER}"}}
    assert pb.footer_errors("S01-01-01", body, {"headings": ["## One"]}) == []


# ---- case F: omission

def test_f_omitting_a_span_that_runs_to_end_of_file_keeps_the_footer(orch):
    rel, text = orch
    out = pb.omit_section(_footed(text), "Post-Session Checklist", _patterns(rel))
    assert out.endswith(f"<!-- OMITTED: Post-Session Checklist (spec omit_sections) -->\n\n---\n\n{FOOTER}\n")
    assert "## Post-Session Checklist" not in out


# ---- case G: no text after the last separator

def test_g_a_span_with_no_text_after_its_last_separator_has_no_footer_stop(rendered):
    for doc in ("MASTER", "S01", "S01-01-ORCH", "S01-01-RECOVERY", TASK_DOC):
        rel, text = _file(rendered, doc)
        info = pb.doc_index({rel: text}, TEMPLATES)[doc]
        assert info["footers"] == [], doc


@pytest.mark.parametrize("lines, expected", [
    (["a", "---", "b"], 1),
    (["a", "---", "b", "---", "c"], 3),
    (["a", "---", ""], 3),
    (["a", "---"], 2),
    (["a", "```text", "---", "b", "```"], 5),
    (["a", "```text", "---", "b", "```", "---", "c"], 5),
])
def test_g_footer_separator_picks_the_last_separator_outside_a_fence_with_text_after_it(lines, expected):
    assert pb.footer_separator(lines, 0, len(lines)) == expected
