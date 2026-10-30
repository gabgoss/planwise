#!/usr/bin/env python3
"""Fixture tests for scripts/check_section_citations.py.

Every fixture tree is built inside pytest's ``tmp_path``. The checker's default
scan set is ``references/``, ``handlers/``, ``agents/``, ``skills/`` and
``templates/`` under ``--root``, so every fixture file sits under
``<root>/references/``. A file at the root itself is never scanned.

The tests call ``check_tree`` directly for finding-level assertions and run the
script through ``subprocess`` (``python -B``) for exit codes, stderr lines, the
ledger and the JSON Lines output. No test reads the real plugin tree.

Run with:  python -m pytest -q tests/test_check_section_citations.py
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_section_citations as csc

SCRIPT = SCRIPTS / "check_section_citations.py"
PROG = "check_section_citations:"
JSON_KEYS = {"citation", "file", "line", "note", "section", "target", "verdict"}


def _write(root: Path, rel: str, text: str, crlf: bool = False) -> Path:
    """Write ``text`` as exact bytes: LF as given, or every LF turned into CRLF."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    if crlf:
        data = data.replace(b"\n", b"\r\n")
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


def _of(findings, file: str):
    return [f for f in findings if f.file == file]


def _a_md(root: Path, body: str = "## 1. One\n") -> None:
    _write(root, "references/a.md", body)


# ---------------------------------------------------------------- forms

A_HEADINGS = (
    "## 1. One\n\n## 2. Two\n\n## 3. Three\n\n### 1.16.5 Deep Rule\n\n"
    "## 9.B Letter Series\n\n### 9.B.1 First\n\n## Read-Tool Hard Limits\n"
)

FORMS = [
    pytest.param("See `a.md` §2.", ["2"], id="backticked"),
    pytest.param("See a.md §2.", ["2"], id="bare"),
    pytest.param("See [a.md §2](a.md).", ["2"], id="link-text"),
    pytest.param("See `a.md` §1-2.", ["1", "2"], id="hyphen-range"),
    pytest.param("See `a.md` §1–2.", ["1", "2"], id="en-dash-range"),
    pytest.param("See `a.md` §1–§3.", ["1", "3"], id="section-both-ends-range"),
    pytest.param("See `a.md` § Read-Tool Hard Limits.", ["Read-Tool Hard Limits"], id="heading-words"),
    pytest.param("See `a.md` §1.16.5.", ["1.16.5"], id="three-level-number"),
    pytest.param("See `a.md` §9.B.1.", ["9.B.1"], id="letter-series"),
    pytest.param("See `a.md` §1/§2.", ["1", "2"], id="bare-continuation-after-slash"),
]


@pytest.mark.parametrize("line, sections", FORMS)
def test_each_citation_form_resolves_ok(tmp_path, line, sections):
    root = tmp_path / "root"
    _a_md(root, A_HEADINGS)
    _write(root, "references/src.md", line + "\n")
    got = _of(csc.check_tree(root), "references/src.md")
    assert [f.section for f in got] == sections
    assert {f.verdict for f in got} == {"ok"}
    assert {f.target for f in got} == {"references/a.md"}


def test_dual_citation_resolves_each_against_its_own_file(tmp_path):
    root = tmp_path / "root"
    _write(root, "references/a.md", "## 15. Fifteen\n")
    _write(root, "references/b.md", "## 16. Sixteen\n")
    _write(root, "references/src.md", "Compare a.md §15 / b.md §16 here.\n")
    got = _of(csc.check_tree(root), "references/src.md")
    assert [(f.section, f.target, f.verdict) for f in got] == [
        ("15", "references/a.md", "ok"),
        ("16", "references/b.md", "ok"),
    ]


def test_bare_continuation_binds_to_the_same_file(tmp_path):
    root = tmp_path / "root"
    _a_md(root, "## 1. One\n")
    _write(root, "references/src.md", "See `a.md` §1/§9 for both.\n")
    got = _of(csc.check_tree(root), "references/src.md")
    assert [(f.section, f.verdict, f.target) for f in got] == [
        ("1", "ok", "references/a.md"),
        ("9", "dangling", "references/a.md"),
    ]


def test_exact_heading_beats_number_prefix(tmp_path):
    root = tmp_path / "root"
    _write(root, "references/c.md", "## 3. Three\n\n### 3k. Kay\n")
    _write(root, "references/src.md", "intro\nSee `c.md` §3k.\n")
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert (got.verdict, got.target, got.section, got.line) == ("ok", "references/c.md", "3k", 2)
    # The fallback to the number prefix writes a note. An exact match writes none.
    assert "fallback" not in got.note
    # Control: with no `3k` heading the same citation falls back to `## 3.` and says so.
    root2 = tmp_path / "root2"
    _write(root2, "references/c.md", "## 3. Three\n")
    _write(root2, "references/src.md", "intro\nSee `c.md` §3k.\n")
    (fallback,) = _of(csc.check_tree(root2), "references/src.md")
    assert fallback.verdict == "ok"
    assert "number-prefix fallback to 3" in fallback.note


def test_no_cross_file_fallback(tmp_path):
    root = tmp_path / "root"
    _write(root, "references/before-cite.md", "## 9.1 Freshness\n")
    _write(root, "references/other.md", "### 9.B.1 Holds It\n")
    _write(root, "references/src.md", "See `before-cite.md` §9.B.1.\n")
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert (got.verdict, got.target) == ("dangling", "references/before-cite.md")


# ------------------------------------------------------- verdicts, ledger


def _redirect_tree(root: Path) -> None:
    _write(root, "references/d.md", "## 1. One\n")
    _write(root, "references/d-Part-2-X.md", "## 16. Sixteen\n")
    _write(root, "references/src.md", "See `d.md` §16.\n")


def test_redirected_passes_by_default_and_fails_under_strict_parts(tmp_path):
    root = tmp_path / "root"
    _redirect_tree(root)
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert (got.verdict, got.target) == ("redirected", "references/d-Part-2-X.md")
    assert _run("--root", root).returncode == 0
    assert _run("--root", root, "--strict-parts").returncode == 1


def test_unresolved_target_exits_1_and_the_ledger_clears_it(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "line one\nSee `nope.md` §1.\n")
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert got.verdict == "unresolved-target"
    assert _run("--root", root).returncode == 1
    ledger = _write(tmp_path, "ledger.txt", "references/src.md:2 sample name\n")
    assert _run("--root", root, "--ledger", ledger).returncode == 0


def test_ledger_turns_a_dangling_exit_1_into_exit_0(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "text\nSee `a.md` §9.\n")
    assert _run("--root", root).returncode == 1
    ledger = _write(tmp_path, "ledger.txt", "# false positives\nreferences/src.md:2 reviewed\n")
    done = _run("--root", root, "--ledger", ledger)
    assert done.returncode == 0
    # A ledger entry that matches nothing is reported, and does not flip the exit.
    stale = _write(tmp_path, "stale.txt", "references/src.md:2\nreferences/src.md:77\n")
    again = _run("--root", root, "--ledger", stale)
    assert again.returncode == 0
    assert "references/src.md:77" in again.stderr


# --------------------------------------------------------- what is skipped


def test_fenced_code_is_not_scanned(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "```\nSee `a.md` §99.\n```\nSee `a.md` §98.\n")
    got = _of(csc.check_tree(root), "references/src.md")
    # Only the line after the closing fence is scanned.
    assert [(f.section, f.line, f.verdict) for f in got] == [("98", 4, "dangling")]


def test_not_a_citation_forms_produce_no_finding(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "Check 17 failed.\nSee reviewer-084 and Reviewer Check 071.\n")
    assert _of(csc.check_tree(root), "references/src.md") == []


def test_frontmatter_description_is_checked(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "---\ndescription: cites `a.md` §2\n---\n# Doc\n")
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert (got.verdict, got.line, got.section) == ("dangling", 2, "2")


def test_callout_code_block_is_not_scanned(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "> [!constraint] Example\n> ```\n> `a.md` §9\n> ```\n")
    assert _of(csc.check_tree(root), "references/src.md") == []


def test_callout_prose_is_still_scanned(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "> [!constraint] Example\n> see a.md §9\n")
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert (got.verdict, got.line, got.target) == ("dangling", 2, "references/a.md")


# ------------------------------------------------------ bare § resolution


def test_bare_section_resolves_against_the_scanned_file_first(tmp_path):
    root = tmp_path / "root"
    _write(root, "references/b.md", "## 1. One\n")
    _write(root, "references/src.md", "## 4. Four\n\nPer §4 and see `b.md`.\n")
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert (got.verdict, got.target) == ("ok", "references/src.md")


def test_bare_section_falls_back_to_the_file_named_later(tmp_path):
    root = tmp_path / "root"
    _write(root, "references/b.md", "## 16. Sixteen\n")
    _write(root, "references/src.md", "| §16 Title | `b.md` |\n")
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert (got.verdict, got.target) == ("ok", "references/b.md")
    assert "later on the line" in got.note


def test_bare_section_held_by_neither_file_is_dangling_on_the_scanned_file(tmp_path):
    root = tmp_path / "root"
    _write(root, "references/b.md", "## 16. Sixteen\n")
    _write(root, "references/src.md", "Bare §99 then `b.md`.\n")
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert (got.verdict, got.target) == ("dangling", "references/src.md")


# ----------------------------------------------------- bytes and the CLI


def test_lf_and_crlf_trees_give_identical_findings(tmp_path):
    body = {
        "references/a.md": "## 1. One\n\n### 3k. Kay\n",
        "references/src.md": (
            "---\ndescription: see `a.md` §1\n---\n"
            "See `a.md` §3k and `a.md` §9.\n```\nSee `a.md` §77.\n```\nSee `nope.md` §1.\n"
        ),
    }
    out = {}
    for name, crlf in (("lf", False), ("crlf", True)):
        root = tmp_path / name
        for rel, text in body.items():
            _write(root, rel, text, crlf=crlf)
        out[name] = [f.as_json() for f in csc.check_tree(root)]
    crlf_bytes = (tmp_path / "crlf" / "references" / "src.md").read_bytes()
    lf_bytes = (tmp_path / "lf" / "references" / "src.md").read_bytes()
    assert b"\r\n" in crlf_bytes and b"\r" not in lf_bytes
    assert out["lf"] == out["crlf"]
    assert {f["verdict"] for f in out["lf"]} == {"ok", "dangling", "unresolved-target"}


def test_exit_0_on_a_clean_tree(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "See `a.md` §1.\n")
    done = _run("--root", root)
    assert done.returncode == 0
    assert "summary:" in done.stdout


def test_exit_1_on_a_dangling_citation(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "See `a.md` §2.\n")
    done = _run("--root", root)
    assert done.returncode == 1
    assert "dangling" in done.stdout


def test_exit_2_for_a_missing_root(tmp_path):
    done = _run("--root", tmp_path / "does-not-exist")
    assert done.returncode == 2
    lines = (done.stderr + done.stdout).splitlines()
    assert any(line.startswith(PROG) for line in lines)


def test_exit_2_for_a_root_with_no_scan_directory(tmp_path):
    root = tmp_path / "root"
    _write(root, "docs/x.md", "## 1. One\n")  # `docs/` is not a scan directory
    _write(root, "top.md", "See `x.md` §9.\n")  # a root-level file is never scanned
    done = _run("--root", root)
    assert done.returncode == 2
    assert any(line.startswith(PROG) for line in done.stderr.splitlines())


def test_json_output_is_json_lines_with_the_documented_keys(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "See `a.md` §1 and `a.md` §2.\n")
    done = _run("--root", root, "--json")
    assert done.returncode == 1
    lines = [ln for ln in done.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2
    objs = [json.loads(ln) for ln in lines]
    assert all(set(o) == JSON_KEYS for o in objs)
    assert [o["verdict"] for o in objs] == ["ok", "dangling"]
    assert "summary:" in done.stderr and "summary:" not in done.stdout


# ------------------------------------------------- extra roots and exclude


def test_extra_root_directory_resolves_a_citation(tmp_path):
    root = tmp_path / "root"
    extra = tmp_path / "extra"
    _a_md(root)
    _write(extra, "ext.md", "## 1. One\n")
    _write(root, "references/src.md", "See `ext.md` §1.\n")
    (without,) = _of(csc.check_tree(root), "references/src.md")
    assert without.verdict == "unresolved-target"
    (with_extra,) = _of(csc.check_tree(root, extra_roots=[extra]), "references/src.md")
    assert (with_extra.verdict, with_extra.target) == ("ok", "extra/ext.md")


def test_extra_root_file_is_scanned_and_used_for_resolution(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    claude = _write(tmp_path / "proj", "CLAUDE.md", "## 2. Rules\n\nSee `a.md` §77.\n")
    _write(root, "references/src.md", "See `CLAUDE.md` §2.\n")
    found = csc.check_tree(root, extra_roots=[claude])
    (resolved,) = _of(found, "references/src.md")
    assert (resolved.verdict, resolved.target) == ("ok", "CLAUDE.md")
    (scanned,) = _of(found, "CLAUDE.md")
    assert (scanned.verdict, scanned.section) == ("dangling", "77")


def test_exclude_removes_a_directory_from_scanning_and_resolution(tmp_path):
    root = tmp_path / "root"
    gone = root / "references" / "gone"
    _a_md(root)
    _write(root, "references/gone/only.md", "## 1. One\n\nSee `a.md` §99.\n")
    _write(root, "references/src.md", "See `only.md` §1.\n")
    before = csc.check_tree(root)
    assert _of(before, "references/src.md")[0].verdict == "ok"
    assert _of(before, "references/gone/only.md")[0].verdict == "dangling"
    after = csc.check_tree(root, exclude=[gone])
    assert _of(after, "references/src.md")[0].verdict == "unresolved-target"
    assert [f for f in after if f.file.startswith("references/gone")] == []


def test_basename_tie_prefers_root_and_flags_ambiguity_inside_a_root(tmp_path):
    root = tmp_path / "root"
    extra = tmp_path / "extra"
    _write(root, "references/dup.md", "## 1. Root Copy\n")
    _write(extra, "dup.md", "## 2. Extra Copy\n")
    _write(root, "references/x/twin.md", "## 1. One\n")
    _write(root, "references/y/twin.md", "## 1. One\n")
    _write(root, "references/src.md", "See `dup.md` §1.\nSee `dup.md` §2.\nSee `twin.md` §1.\n")
    got = _of(csc.check_tree(root, extra_roots=[extra]), "references/src.md")
    first, second, third = got
    assert (first.verdict, first.target) == ("ok", "references/dup.md")
    # The root copy decides alone: the extra copy's `## 2.` does not rescue §2.
    assert (second.verdict, second.target) == ("dangling", "references/dup.md")
    assert third.verdict == "unresolved-target"
    assert "ambiguous" in third.note


def test_basename_found_only_under_an_extra_root_resolves_there(tmp_path):
    root = tmp_path / "root"
    extra = tmp_path / "extra"
    _a_md(root)
    _write(extra, "dup.md", "## 2. Extra Copy\n")
    _write(root, "references/src.md", "See `dup.md` §2.\n")
    (got,) = _of(csc.check_tree(root, extra_roots=[extra]), "references/src.md")
    assert (got.verdict, got.target) == ("ok", "extra/dup.md")


def test_brace_placeholder_sections_are_skipped(tmp_path):
    root = tmp_path / "root"
    _write(root, "references/a.md", "## 5. Five\n")
    _write(root, "references/src.md", "see a.md §1.{N} and §2{x}\nsee a.md §1\n")
    got = _of(csc.check_tree(root), "references/src.md")
    # Line 1 holds only placeholders and yields nothing. The control line 2 is dangling.
    assert [(f.line, f.verdict, f.section) for f in got] == [(2, "dangling", "1")]


STEP_CASES = [
    pytest.param("## Hub, Leaves and Shards\n", "See `a.md` § Hub, Leaves and Shards. More text\n", "ok", id="full-title-with-commas"),
    pytest.param("## Hub, Leaves and Shards\n", "See `a.md` § Hub, Missing Words\n", "dangling", id="full-title-absent"),
    pytest.param("## Step 2 — Strip framing\n", "See `a.md` § Step 2\n", "ok", id="step-before-em-dash"),
    pytest.param("## Step 20 — X\n", "See `a.md` § Step 2\n", "dangling", id="step-2-not-step-20"),
    pytest.param("### Stage 8b — Y\n", "See `a.md` § Stage 8b\n", "ok", id="stage-letter-suffix-before-em-dash"),
]


@pytest.mark.parametrize("heading, line, verdict", STEP_CASES)
def test_heading_words_full_title_and_step_before_dash(tmp_path, heading, line, verdict):
    root = tmp_path / "root"
    _write(root, "references/a.md", heading)
    _write(root, "references/src.md", line)
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert (got.verdict, got.target) == (verdict, "references/a.md")


@pytest.mark.parametrize(
    "entry, exit_code",
    [
        pytest.param(".hidden/rules/x.md:2", 0, id="dot-directory-absolute-suffix"),
        pytest.param("./.hidden/rules/x.md:2", 0, id="leading-dot-slash-prefix"),
        pytest.param("rules/x.md:2", 0, id="printed-file-key"),
        pytest.param(".hidden/rules/x.md:3", 1, id="different-line-number"),
    ],
)
def test_ledger_matches_a_path_inside_a_dot_directory(tmp_path, entry, exit_code):
    root = tmp_path / "root"
    extra = tmp_path / ".hidden" / "rules"
    _a_md(root)
    _write(root, "references/src.md", "See `a.md` §1.\n")
    _write(extra, "x.md", "intro\nSee `a.md` §9.\n")
    assert _run("--root", root, "--extra-root", extra).returncode == 1
    ledger = _write(tmp_path, "ledger.txt", entry + "\n")
    done = _run("--root", root, "--extra-root", extra, "--ledger", ledger)
    assert done.returncode == exit_code


# ------------------------------------------- pre-commit review fixes


def test_sibling_search_is_exact_only(tmp_path):
    root = tmp_path / "root"
    _write(root, "references/c.md", "## 1. One\n")
    _write(root, "references/c-Part-1-X.md", "## 3 Only\n")
    _write(root, "references/src.md", "See c.md §3k.\n")
    (got,) = _of(csc.check_tree(root), "references/src.md")
    assert got.verdict == "dangling"


def test_exact_heading_beats_number_prefix_across_candidates(tmp_path):
    root = tmp_path / "root"
    _write(root, "references/s.md", "## 3k Kay\n\nEdit a.md now. Then §3k applies.\n")
    _write(root, "references/a.md", "## 3 Three\n")
    (got,) = _of(csc.check_tree(root), "references/s.md")
    assert (got.verdict, got.target) == ("ok", "references/s.md")
    assert "fallback" not in got.note


@pytest.mark.parametrize(
    "line, sections",
    [
        pytest.param("see a.md §5 - 3 rows remain", ["5"], id="spaced-hyphen-prose-number"),
        pytest.param("see a.md §4 – 2026 update", ["4"], id="spaced-en-dash-year"),
        pytest.param("see a.md §13–19", ["13", "19"], id="en-dash-no-space"),
        pytest.param("see a.md §13 – §19", ["13", "19"], id="spaced-en-dash-with-sign"),
        pytest.param("see a.md §5-7", ["5", "7"], id="hyphen-no-space"),
    ],
)
def test_spaced_range_end_needs_its_own_sign(tmp_path, line, sections):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", line + "\n")
    got = _of(csc.check_tree(root), "references/src.md")
    assert [f.section for f in got] == sections


def _readme_tree(root: Path) -> None:
    _a_md(root)
    filler = "x\n" * 4
    _write(root, "references/README.md", filler + "See `a.md` §9.\n")
    _write(root, "skills/x/README.md", filler + "See `a.md` §9.\n")


@pytest.mark.parametrize(
    "entries, exit_code",
    [
        pytest.param(["README.md:5"], 1, id="bare-basename-subtracts-neither"),
        pytest.param(["references/README.md:5"], 1, id="one-path-subtracts-only-that-file"),
        pytest.param(["references/README.md:5", "skills/x/README.md:5"], 0, id="both-paths"),
    ],
)
def test_ledger_basename_does_not_match_two_files(tmp_path, entries, exit_code):
    root = tmp_path / "root"
    _readme_tree(root)
    assert _run("--root", root).returncode == 1
    ledger = _write(tmp_path, "ledger.txt", "\n".join(entries) + "\n")
    assert _run("--root", root, "--ledger", ledger).returncode == exit_code


def test_own_directory_wins_for_a_shared_basename(tmp_path):
    root = tmp_path / "root"
    _write(root, "skills/foo/SKILL.md", "See `helper.md` §2.\n")
    _write(root, "skills/foo/helper.md", "## 2. Two\n")
    _write(root, "skills/bar/helper.md", "## 2. Two\n")
    (got,) = _of(csc.check_tree(root), "skills/foo/SKILL.md")
    assert (got.verdict, got.target) == ("ok", "skills/foo/helper.md")


def test_extra_root_inside_root_does_not_double_the_scan(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "See `a.md` §1 and `a.md` §9.\n")
    plain = csc.check_tree(root)
    nested = csc.check_tree(root, extra_roots=[root / "references"])
    assert len(plain) == len(nested) > 0
    assert _run("--root", root).stdout.splitlines()[-1] == _run(
        "--root", root, "--extra-root", root / "references"
    ).stdout.splitlines()[-1]
