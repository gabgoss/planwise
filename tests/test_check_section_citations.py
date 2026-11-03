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
        # A relative entry resolves against --root, then each extra root and
        # its parent. It never matches by path suffix, so a path that only
        # ends like the file's absolute path no longer matches.
        pytest.param(".hidden/rules/x.md:2", 1, id="dot-directory-suffix-no-longer-matches"),
        pytest.param("./.hidden/rules/x.md:2", 1, id="leading-dot-slash-suffix-no-longer-matches"),
        pytest.param("rules/x.md:2", 0, id="printed-file-key"),
        pytest.param("./rules/x.md:2:§9", 0, id="leading-dot-slash-printed-key-three-field"),
        pytest.param("{abs}:2:§9", 0, id="absolute-path-three-field"),
        pytest.param("rules/x.md:3", 1, id="different-line-number"),
    ],
)
def test_ledger_matches_a_path_inside_a_dot_directory(tmp_path, entry, exit_code):
    root = tmp_path / "root"
    extra = tmp_path / ".hidden" / "rules"
    _a_md(root)
    _write(root, "references/src.md", "See `a.md` §1.\n")
    x = _write(extra, "x.md", "intro\nSee `a.md` §9.\n")
    assert _run("--root", root, "--extra-root", extra).returncode == 1
    ledger = _write(tmp_path, "ledger.txt", entry.replace("{abs}", x.resolve().as_posix()) + "\n")
    done = _run("--root", root, "--extra-root", extra, "--ledger", ledger)
    assert done.returncode == exit_code


# ------------------------------------------------- citation-keyed ledger


def _two_cites_tree(root: Path) -> None:
    _a_md(root)
    _write(root, "references/src.md", "intro\nSee `a.md` §8 and `a.md` §9.\n")


def test_three_field_entry_subtracts_only_its_own_citation(tmp_path):
    root = tmp_path / "root"
    _two_cites_tree(root)
    one = _write(tmp_path, "one.txt", "references/src.md:2:§8\n")
    done = _run("--root", root, "--ledger", one)
    assert done.returncode == 1
    assert "1 failing after ledger" in done.stdout
    assert "line-keyed" not in done.stderr
    both = _write(tmp_path, "both.txt", "references/src.md:2:§8\nreferences/src.md:2:§9 # EXAMPLE: reason\n")
    assert _run("--root", root, "--ledger", both).returncode == 0


def test_two_field_entry_still_loads_and_prints_a_line_keyed_note(tmp_path):
    root = tmp_path / "root"
    _two_cites_tree(root)
    ledger = _write(tmp_path, "old.txt", "references/src.md:2 reviewed\n")
    done = _run("--root", root, "--ledger", ledger)
    assert done.returncode == 0
    notes = [ln for ln in done.stderr.splitlines() if "line-keyed" in ln]
    assert notes == ["ledger entry is line-keyed; re-key as path:line:citation: references/src.md:2"]


def test_three_field_entry_with_a_different_citation_matches_nothing(tmp_path):
    root = tmp_path / "root"
    _two_cites_tree(root)
    ledger = _write(tmp_path, "l.txt", "references/src.md:2:§7\n")
    done = _run("--root", root, "--ledger", ledger)
    assert done.returncode == 1
    assert "matched no dangling or unresolved-target finding: references/src.md:2:§7" in done.stderr


def test_read_ledger_parses_three_field_and_line_keyed_entries(tmp_path):
    ledger = _write(
        tmp_path,
        "l.txt",
        "# comment\n\nhandlers/p.md:57:§ Decisions\nr\\x.md:4:§1.2 # EXAMPLE\n"
        "C:/abs/y.md:9:19\nreferences/z.md:3 reason text\n",
    )
    got = [(e.path, e.line, e.citation) for e in csc.read_ledger(ledger)]
    assert got == [
        ("handlers/p.md", 57, "§ Decisions"),
        ("r/x.md", 4, "§1.2"),
        ("C:/abs/y.md", 9, "19"),
        ("references/z.md", 3, None),
    ]
    bad = _write(tmp_path, "bad.txt", "no line number here\n")
    with pytest.raises(csc.CitationCheckError):
        csc.read_ledger(bad)


def test_citation_keyed_ledger_catches_a_new_citation_on_a_ledgered_line(tmp_path):
    # Discrimination: a ledgered line gains a second, new dangling citation.
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "intro\nSee `a.md` §8.\n")
    new = _write(tmp_path, "new.txt", "references/src.md:2:§8\n")
    old = _write(tmp_path, "old.txt", "references/src.md:2\n")
    assert _run("--root", root, "--ledger", new).returncode == 0
    assert _run("--root", root, "--ledger", old).returncode == 0
    _write(root, "references/src.md", "intro\nSee `a.md` §8 and `a.md` §97.\n")
    drifted = _run("--root", root, "--ledger", new)
    assert drifted.returncode == 1
    assert "references/src.md:2: dangling: §97" in drifted.stdout
    assert _run("--root", root, "--ledger", old).returncode == 0


def test_relative_entry_never_matches_by_suffix_another_files_finding(tmp_path):
    # The old suffix rule let `references/src.md:2` also hide the extra root's
    # `ext/references/src.md:2`, whose absolute path ends the same way.
    root = tmp_path / "root"
    extra = tmp_path / "ext"
    _a_md(root)
    _write(root, "references/src.md", "intro\nSee `a.md` §9.\n")
    _write(extra, "references/src.md", "intro\nSee `a.md` §8.\n")
    ledger = _write(tmp_path, "l.txt", "references/src.md:2:§9\n")
    done = _run("--root", root, "--extra-root", extra, "--ledger", ledger)
    assert done.returncode == 1
    assert "1 failing after ledger" in done.stdout
    both = _write(tmp_path, "both.txt", "references/src.md:2:§9\next/references/src.md:2:§8\n")
    assert _run("--root", root, "--extra-root", extra, "--ledger", both).returncode == 0


def test_relative_entry_never_resolves_against_the_cwd(tmp_path):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "intro\nSee `a.md` §9.\n")
    # From cwd=tmp_path this path names the file, but the roots do not hold it.
    _write(tmp_path, "l.txt", "root/references/src.md:2:§9\n")
    done = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--root", "root", "--ledger", "l.txt"],
        capture_output=True, text=True, encoding="utf-8", timeout=120, check=False, cwd=tmp_path,
    )
    assert done.returncode == 1
    assert "matched no dangling or unresolved-target finding: root/references/src.md:2:§9" in done.stderr


def test_resolve_ledger_prefers_root_then_extra_roots(tmp_path):
    root = tmp_path / "root"
    extra = tmp_path / "ext"
    _write(root, "references/a.md", "x\n")
    _write(extra, "only.md", "x\n")
    entries = [csc.LedgerEntry("references/a.md", 1, None), csc.LedgerEntry("only.md", 1, None),
               csc.LedgerEntry("ext/only.md", 1, None), csc.LedgerEntry("missing.md", 1, None)]
    got = [e.target for e in csc.resolve_ledger(entries, csc.ledger_bases(root, [extra]))]
    assert got == [
        (root / "references" / "a.md").resolve().as_posix(),
        (extra / "only.md").resolve().as_posix(),
        (extra / "only.md").resolve().as_posix(),
        "",
    ]


# ------------------------------------------------------ unreadable file


def _cp1252_tree(root: Path) -> None:
    _a_md(root)
    _write(root, "references/good.md", "See `a.md` §9.\n")
    path = root / "references" / "bad.md"
    path.write_bytes(b"line one\nSee \xa7 1 here.\n")  # a cp1252 section sign


def test_unreadable_file_is_one_finding_and_other_findings_still_print(tmp_path):
    root = tmp_path / "root"
    _cp1252_tree(root)
    found = csc.check_tree(root)
    (bad,) = _of(found, "references/bad.md")
    assert (bad.verdict, bad.line, bad.citation, bad.fails) == ("unreadable", 2, "", True)
    assert "byte 0xa7 at offset 13" in bad.note
    assert _of(found, "references/good.md")[0].verdict == "dangling"
    done = _run("--root", root)
    assert done.returncode == 1
    assert "references/bad.md:2: unreadable (not UTF-8: byte 0xa7 at offset 13)" in done.stdout
    assert "references/good.md:1: dangling" in done.stdout
    assert "unreadable=1" in done.stdout


def test_unreadable_file_is_not_ledgerable(tmp_path):
    root = tmp_path / "root"
    _cp1252_tree(root)
    ledger = _write(tmp_path, "l.txt", "references/good.md:1:§9\nreferences/bad.md:2\n")
    done = _run("--root", root, "--ledger", ledger)
    assert done.returncode == 1
    assert "1 failing after ledger" in done.stdout
    assert "matched no dangling or unresolved-target finding: references/bad.md:2" in done.stderr
    # Control: with the file repaired the same ledger clears the run.
    (root / "references" / "bad.md").write_bytes(b"line one\nplain text.\n")
    fixed = _run("--root", root, "--ledger", _write(tmp_path, "l2.txt", "references/good.md:1:§9\n"))
    assert fixed.returncode == 0
    assert "unreadable" not in fixed.stdout


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


# ------------------------------------------------------------ redirect table

# Each entry the table must hold: key -> (target basename, target section).
# Membership only: a later entry may join the table without breaking these.
REQUIRED_REDIRECTS = {
    ("verification-gates.md", "9"): ("measurement-discipline.md", "8"),
    ("verification-gates.md", "12"): ("verify-caller-before-complete.md", None),
    ("verification-gates.md", "8"): ("gate-diff-baseline-pinning.md", "8"),
    ("verification-gates.md", "1"): ("gate-runtime-boundary-evidence.md", "1"),
    ("verification-gates.md", "7"): ("gate-runtime-boundary-evidence.md", "7"),
}


@pytest.mark.parametrize("key", sorted(REQUIRED_REDIRECTS), ids=lambda k: f"{k[0]}-{k[1]}")
def test_redirect_table_holds_each_entry_with_its_source(key):
    entry = csc.REDIRECTS[key]
    assert (entry.target, entry.section) == REQUIRED_REDIRECTS[key]
    # The source names the cited file's section that records the move.
    assert entry.source.startswith("verification-gates.md § ")


def _gates_tree(root: Path, md_body: str = "## 8. Empirical\n") -> None:
    _write(root, "references/verification-gates.md", "### 9. Empirical\n\n### 12. Reachability\n\n## 2. Two\n")
    _write(root, "references/measurement-discipline.md", md_body)
    _write(root, "references/verify-caller-before-complete.md", "## 1. One\n")
    _write(root, "references/src.md", "See `verification-gates.md` §9 and `verification-gates.md` §12.\n")


def test_redirect_entry_wins_over_a_stub_heading(tmp_path):
    root = tmp_path / "root"
    _gates_tree(root)
    got = _of(csc.check_tree(root), "references/src.md")
    assert [(f.verdict, f.target, f.section) for f in got] == [
        ("redirected", "references/measurement-discipline.md", "8"),
        ("redirected", "references/verify-caller-before-complete.md", "12"),
    ]
    assert all("source: verification-gates.md § Reserved Section Numbers" in f.note for f in got)
    # Default passes, --strict-parts fails on the table redirects alone.
    assert _run("--root", root).returncode == 0
    strict = _run("--root", root, "--strict-parts")
    assert strict.returncode == 1
    assert "2 failing after ledger" in strict.stdout
    objs = [json.loads(ln) for ln in _run("--root", root, "--json").stdout.splitlines() if ln.strip()]
    mine = [o for o in objs if o["file"] == "references/src.md"]
    assert mine[0]["target"] == "references/measurement-discipline.md"
    assert "redirect table:" in mine[0]["note"] and "source:" in mine[0]["note"]


@pytest.mark.parametrize(
    "md_body, why",
    [
        pytest.param("## 7. Seven\n", "target heading missing", id="target-heading-missing"),
        pytest.param(None, "target file missing", id="target-file-missing"),
    ],
)
def test_redirect_entry_with_a_missing_target_is_dangling(tmp_path, md_body, why):
    root = tmp_path / "root"
    _gates_tree(root, md_body or "")
    if md_body is None:
        (root / "references" / "measurement-discipline.md").unlink()
    first = _of(csc.check_tree(root), "references/src.md")[0]
    assert (first.verdict, first.target, first.section) == ("dangling", "references/verification-gates.md", "9")
    assert why in first.note and "redirect table: verification-gates.md §9" in first.note
    assert _run("--root", root).returncode == 1


def test_subsection_of_a_moved_section_redirects_under_the_target_section(tmp_path):
    root = tmp_path / "root"
    _gates_tree(root, "## 8. Empirical\n\n### 8.2 Two\n")
    _write(root, "references/src.md",
           "See `verification-gates.md` §9.2, `verification-gates.md` §9.3 and "
           "`verification-gates.md` §12.1.\n")
    got = _of(csc.check_tree(root), "references/src.md")
    assert [(f.verdict, f.target, f.section) for f in got] == [
        ("redirected", "references/measurement-discipline.md", "8.2"),
        # The mapped heading is absent from the target, so it stays dangling.
        ("dangling", "references/verification-gates.md", "9.3"),
        ("redirected", "references/verify-caller-before-complete.md", "12.1"),
    ]
    assert "target heading missing" in got[1].note


def test_redirect_table_does_not_apply_outside_plugin_references(tmp_path):
    root = tmp_path / "root"
    _gates_tree(root)
    _write(root, "references/gate-diff-baseline-pinning.md", "## 8. Diff\n")
    rules = tmp_path / "consumer" / ".claude" / "rules"
    _write(rules, "verification-gates.md", "## 8. Our own section\n")
    _write(rules, "use.md", "See `verification-gates.md` §8.\n")
    got = _of(csc.check_tree(root, extra_roots=[rules]), "rules/use.md")
    assert [(f.verdict, f.target, f.section) for f in got] == [("ok", "rules/verification-gates.md", "8")]


def test_citation_without_an_entry_resolves_ok_unchanged(tmp_path):
    root = tmp_path / "root"
    _gates_tree(root)
    _write(root, "references/src.md", "See `verification-gates.md` §2 and `measurement-discipline.md` §8.\n")
    got = _of(csc.check_tree(root), "references/src.md")
    assert [(f.verdict, f.target, f.section, f.note) for f in got] == [
        ("ok", "references/verification-gates.md", "2", ""),
        ("ok", "references/measurement-discipline.md", "8", ""),
    ]
    assert _run("--root", root, "--strict-parts").returncode == 0


# ------------------------------------------------- zone and symbol modes


def _zone_tree(tmp_path: Path, target_body: str) -> tuple[Path, Path]:
    brief = _write(tmp_path, "brief.md", "Step 1\nAdd the row under `## Topic Files` in the index.\n")
    target = _write(tmp_path, "index.md", target_body)
    return brief, target


def test_zone_mode_counts_a_present_zone(tmp_path):
    brief, target = _zone_tree(tmp_path, "# Index\n\n## Topic Files\n\n| a | b |\n")
    (got,) = csc.check_zones(brief.read_text(encoding="utf-8"), [target], "brief.md")
    assert (got.subject, got.count, got.label, got.line) == ("Topic Files", 1, "zone", 2)
    done = _run("--brief", brief, "--zone", target)
    assert done.returncode == 0
    assert 'brief.md:2: zone: zone "Topic Files" count=1' in done.stdout


def test_zone_mode_reports_a_dead_zone(tmp_path):
    brief, target = _zone_tree(tmp_path, "# Index\n\n## Section Map\n")
    (got,) = csc.check_zones(brief.read_text(encoding="utf-8"), [target])
    assert (got.count, got.label, got.fails) == (0, "DEAD-ZONE", True)
    done = _run("--brief", brief, "--zone", target)
    assert done.returncode == 1
    assert 'DEAD-ZONE: zone "Topic Files" count=0' in done.stdout
    # The default citation summary does not print: the mode replaces the scan.
    assert "findings (" not in done.stdout


@pytest.mark.parametrize(
    "line, zones",
    [
        pytest.param('Land it in the "Decisions" section.', ["Decisions"], id="quoted-after-in"),
        pytest.param("Put it below `### Controls Run`.", ["Controls Run"], id="hashes-dropped"),
        pytest.param("Edit the code in `check_tree()` and in `scripts/x.py`.", [], id="code-and-path-skipped"),
        pytest.param("Write it as a `## Topic Files` row.", [], id="no-trigger-word"),
        pytest.param('Set section `None`; each section "keeps its number".', [], id="code-value-and-prose-quote"),
    ],
)
def test_zone_extraction_rule(line, zones):
    assert [z for _, z in csc.extract_zones(line + "\n")] == zones


@pytest.mark.parametrize(
    "rows, label",
    [
        pytest.param("| 3 | Add a row matching the existing table | x.md |\n", "NO-LOCATOR", id="no-locator"),
        pytest.param("<!-- Grep '^## Notes' x.md → 2 -->\n| 3 | Add a row matching the existing table | x.md |\n",
                     "locator", id="locator-recorded"),
        pytest.param("<!-- Grep '^## Notes' x.md → 0 -->\n| 3 | Add a row in native format | x.md |\n",
                     "NO-FALLBACK", id="count-0-no-fallback"),
        pytest.param("<!-- Grep '^## Notes' x.md → 0 -->\n| 3 | native format absent: add an inline note | x.md |\n",
                     "locator", id="count-0-with-fallback"),
    ],
)
def test_locator_evidence_rule(tmp_path, rows, label):
    (got,) = csc.check_locators(rows)
    assert got.label == label
    brief = _write(tmp_path, "brief.md", rows)
    target = _write(tmp_path, "x.md", "## Notes\n")
    assert _run("--brief", brief, "--zone", target).returncode == (0 if label == "locator" else 1)


def test_locator_rule_skips_a_quoted_mention():
    assert csc.check_locators('A row that says "native format" or `matching the existing` is checked.\n') == []


def test_symbol_mode_counts_present_and_reports_phantom(tmp_path):
    src = tmp_path / "src"
    _write(src, "mod.py", "def load_rule_scopes(path):\n    return load_rule_scopes\n")
    spec = _write(tmp_path, "spec.md", "Sprint 1 shipped `mod.load_rule_scopes()` and `ghost_handler()`.\n"
                                       "Run `python -B x.py` and read `notes.md`.\n")
    got = csc.check_symbols(spec.read_text(encoding="utf-8"), [src], "spec.md")
    assert [(f.subject, f.count, f.label) for f in got] == [
        ("mod.load_rule_scopes", 2, "symbol"),
        ("ghost_handler", 0, "phantom"),
    ]
    done = _run("--symbols", spec, "--source", src)
    assert done.returncode == 1
    assert 'phantom: symbol "ghost_handler" count=0' in done.stdout
    listed = _write(tmp_path, "list.txt", "# one per line\nload_rule_scopes\n")
    assert _run("--symbols", listed, "--source", src).returncode == 0


def test_mode_flags_need_their_pair_and_keep_the_default_json_keys(tmp_path):
    assert _run("--zone", tmp_path / "x.md").returncode == 2
    assert _run("--symbols", tmp_path / "x.md").returncode == 2
    assert "DEAD-ZONE" not in csc.VERDICTS and "phantom" not in csc.VERDICTS
    brief, target = _zone_tree(tmp_path, "## Other\n")
    done = _run("--brief", brief, "--zone", target, "--json")
    objs = [json.loads(ln) for ln in done.stdout.splitlines() if ln.strip()]
    assert [o["label"] for o in objs] == ["DEAD-ZONE"]
    assert "summary:" in done.stderr


# ------------------------------------------------- path and file:line modes


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    _write(proj, "planwise/config.yaml", "plugin_version: x\n")
    _write(proj, "plans/Sprint/shared.md", "# Shared\n")
    _write(proj, "plans/Sprint/Session/Outputs/prior.md", "# Prior\n")
    _write(proj, "repo/scripts/tool.py", "x = 1\n")
    return proj


def _task(proj: Path, rc_rows: str, steps: str, output: str = "`Outputs/mine.md`") -> Path:
    return _write(proj, "plans/Sprint/Session/T-01.md", (
        f"# Task\n\n**Output:** {output}\n\n## Required Context\n\n"
        "| Priority | File | Purpose |\n|---|---|---|\n" + rc_rows +
        "\n## Execution Steps\n\n" + steps + "\n## Expected Output\n\n`repo/never/checked.py`\n"))


GOOD_RC = ("| 1 | `../shared.md` — §2 | sibling |\n| 1 | `Outputs/prior.md` | prior |\n"
           "| 2 | `repo/scripts/tool.py` | code |\n| 2 | Command corpus | n/a |\n")


def test_path_mode_resolves_every_path_and_counts_skips(tmp_path):
    proj = _project(tmp_path)
    task = _task(proj, GOOD_RC, "1. Edit `repo/scripts/tool.py:12` and write `Outputs/mine.md`.\n"
                                "2. Skip `Outputs/{Abbrev}-x.md`, `repo/tests/test_*.py` and `python -B x.py`.\n")
    got, skipped = csc.check_paths(task)
    assert [(f.subject, f.label) for f in got] == [
        ("../shared.md", "path"), ("Outputs/prior.md", "path"), ("repo/scripts/tool.py", "path"),
        ("Outputs/mine.md", "expected"),
    ]
    assert "via task folder" in got[0].note and "via project root" in got[2].note
    assert skipped == {"placeholder": 1, "glob": 1}
    done = _run("--paths", task, "--root", proj / "repo")
    assert done.returncode == 0
    assert 'path: path "../shared.md" count=1' in done.stdout
    assert "skipped 1 placeholders, 1 globs" in done.stdout
    # The section after Execution Steps is not read.
    assert "never/checked.py" not in done.stdout


def test_path_mode_exits_1_on_an_unresolved_required_context_path(tmp_path):
    proj = _project(tmp_path)
    bad = GOOD_RC + "| 2 | `Outputs/later.md` (projected) | next |\n| 2 | `repo/scripts/gone.py` | x |\n"
    task = _task(proj, bad, "1. Read the module.\n")
    done = _run("--paths", task, "--project-root", proj, "--root", proj / "repo")
    assert done.returncode == 1
    assert 'unresolved: path "repo/scripts/gone.py"' in done.stdout
    assert 'unresolved: path "Outputs/later.md"' in done.stdout and "row marked projected" in done.stdout
    assert "(unresolved=2, expected=0)" in done.stdout
    # Exit 2 when no project root is found or given.
    lone = _write(tmp_path, "lone/T.md", "## Required Context\n\n| File |\n|---|\n| `a/b.md` |\n")
    assert _run("--paths", lone, "--root", proj / "repo").returncode == 2
    assert _run("--project-root", proj).returncode == 2


def _plugin_repo(proj: Path) -> Path:
    """A plugin repo inside the project: ``.git``, ``plugins/p/scripts/x.py``, ``tests/test_y.py``."""
    repo = proj / "cloned" / "plug"
    (repo / ".git").mkdir(parents=True)
    _write(repo, "plugins/p/scripts/x.py", "x = 1\n")
    _write(repo, "tests/test_y.py", "def test_y():\n    pass\n")
    return repo


def test_path_mode_root_bases_resolve_plugin_relative_paths(tmp_path):
    proj = _project(tmp_path)
    repo = _plugin_repo(proj)
    task = _task(proj, GOOD_RC, "1. Edit `scripts/x.py` and run `tests/test_y.py`.\n")
    # Without --root, path mode keeps its two bases: both paths are unresolved.
    assert _run("--paths", task).returncode == 1
    got, _ = csc.check_paths(task, roots=[repo / "plugins" / "p"])
    by = {f.subject: f for f in got}
    assert by["scripts/x.py"].label == "path" and "via --root" in by["scripts/x.py"].note
    assert by["tests/test_y.py"].label == "path" and "via repository root" in by["tests/test_y.py"].note
    done = _run("--paths", task, "--root", repo / "plugins" / "p")
    assert done.returncode == 0
    assert "via --root" in done.stdout and "via repository root" in done.stdout


def test_path_mode_plugin_relative_path_absent_everywhere_is_unresolved(tmp_path):
    proj = _project(tmp_path)
    repo = _plugin_repo(proj)
    task = _task(proj, GOOD_RC, "1. Edit `scripts/gone.py`.\n")
    done = _run("--paths", task, "--root", repo / "plugins" / "p")
    assert done.returncode == 1
    assert 'unresolved: path "scripts/gone.py"' in done.stdout
    assert "repository root" in done.stdout


def test_path_mode_reads_a_sibling_tasks_output_as_expected(tmp_path):
    proj = _project(tmp_path)
    _write(proj, "plans/Sprint/Session/T-02.md", "# Task\n\n**Output:** `Outputs/sib.md`\n")
    task = _task(proj, GOOD_RC + "| 2 | `Outputs/sib.md` (projected) | next |\n", "1. Read it.\n")
    done = _run("--paths", task, "--root", proj / "repo")
    assert done.returncode == 0
    assert 'expected: path "Outputs/sib.md"' in done.stdout and "Output:** line of T-02.md" in done.stdout


def _cited(proj: Path, total: int, anchor_line: int, crlf: bool) -> None:
    body = "".join("def anchor_here():\n" if i == anchor_line else f"line {i}\n" for i in range(1, total + 1))
    _write(proj, "repo/src/code.py", body, crlf=crlf)


@pytest.mark.parametrize("crlf", [False, True], ids=["lf", "crlf"])
@pytest.mark.parametrize(
    "total, anchor_line, label",
    [
        pytest.param(12, 10, "file-line", id="12-lines-anchor-on-10"),
        pytest.param(5, 3, "stale-line", id="5-line-file"),
        pytest.param(12, 3, "anchor-moved", id="anchor-moved-to-3"),
    ],
)
def test_file_line_mode_controls(tmp_path, total, anchor_line, label, crlf):
    proj = _project(tmp_path)
    _cited(proj, total, anchor_line, crlf)
    doc = _write(proj, "plans/ei.md", "See `repo/src/code.py:10`, where `anchor_here` lives.\n", crlf=crlf)
    (got,) = csc.check_file_lines(doc.read_text(encoding="utf-8"), doc, [proj / "repo"])[0]
    assert (got.subject, got.count, got.label) == ("repo/src/code.py:10", total, label)
    if label == "anchor-moved":
        assert 'anchor "anchor_here" at line 3' in got.note
    done = _run("--file-line", doc, "--root", proj / "repo")
    assert done.returncode == (0 if label == "file-line" else 1)
    assert f"{label}: file-line" in done.stdout


def test_line_count_is_the_same_for_crlf_and_lf_copies(tmp_path):
    for text in ("a\nb\nc\n", "a\nb\nc"):
        lf, crlf = text.encode(), text.replace("\n", "\r\n").encode()
        assert csc.count_lines(lf) == csc.count_lines(crlf) == 3
    assert csc.count_lines(b"") == 0
    proj = _project(tmp_path)
    _write(proj, "repo/a.md", "one\ntwo\n`x`\n", crlf=True)
    _write(proj, "repo/b.md", "one\ntwo\n`x`\n")
    doc = _write(proj, "plans/ei.md", "`a.md`:3-4 and `b.md`:3-4\nplaceholder `{N}.md:2`\n")
    got, skipped = csc.check_file_lines(doc.read_text(encoding="utf-8"), doc, [proj / "repo"])
    assert [(f.subject, f.count, f.label) for f in got] == [("a.md:3-4", 3, "stale-line"),
                                                         ("b.md:3-4", 3, "stale-line")]
    assert skipped == {"placeholder": 1}


def _scope_tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "root"
    extra = tmp_path / "rules"
    _a_md(root)
    _write(root, "references/src.md", "See `a.md` §9.\n")
    _write(extra, "r.md", "See `a.md` §1 and `a.md` §8.\n")
    return root, extra


def test_scan_roots_indexes_every_root_and_scans_only_the_named_ones(tmp_path):
    root, extra = _scope_tree(tmp_path)
    full = csc.check_tree(root, extra_roots=[extra])
    scoped = csc.check_tree(root, extra_roots=[extra], scan_roots=[extra])
    # The root still resolves the extra root's citations; its own file is not scanned.
    assert {f.file for f in full} == {"references/src.md", "rules/r.md"}
    assert [f.as_json() for f in scoped] == [f.as_json() for f in _of(full, "rules/r.md")]
    assert [(f.section, f.verdict, f.target) for f in scoped] == [
        ("1", "ok", "references/a.md"), ("8", "dangling", "references/a.md")]
    # The default (None) scans every root, so an existing caller is unchanged.
    assert csc.check_tree(root, extra_roots=[extra], scan_roots=None) == full
    assert csc.check_tree(root, extra_roots=[extra], scan_roots=[root, extra]) == full
    assert csc.check_tree(root, extra_roots=[extra], scan_roots=[root]) == _of(full, "references/src.md")


def test_scan_root_that_is_not_a_root_is_an_error(tmp_path):
    root, extra = _scope_tree(tmp_path)
    with pytest.raises(csc.CitationCheckError, match="scan root is not"):
        csc.check_tree(root, extra_roots=[extra], scan_roots=[tmp_path])


def test_each_chain_parses_once(monkeypatch):
    calls = []
    real = csc._parse_chain
    monkeypatch.setattr(csc, "_parse_chain", lambda line, pos: calls.append(pos) or real(line, pos))
    got = csc.parse_line("Per §4 here and §5/§6 too.")
    assert [c.section for _, _, c in got] == ["4", "5", "6"]
    # One parse per chain start: §4 alone, then §5 with its continuation §6.
    assert calls == [4, 16]


def test_resolution_is_memoized_per_name_and_citing_directory(tmp_path, monkeypatch):
    root = tmp_path / "root"
    _a_md(root)
    _write(root, "references/src.md", "See `a.md` §1.\nSee `a.md` §2.\nSee `a.md` §1.\n")
    _write(root, "skills/x/s.md", "See `a.md` §1.\n")
    calls = []
    real = csc._Roots._resolve
    monkeypatch.setattr(csc._Roots, "_resolve", lambda self, name, citing=None: calls.append(
        (name, citing.parent.name if citing else None)) or real(self, name, citing))
    found = csc.check_tree(root)
    assert [f.verdict for f in _of(found, "references/src.md")] == ["ok", "dangling", "ok"]
    # One resolution per (name, citing directory), not one per citation.
    assert sorted(calls) == [("a.md", "references"), ("a.md", "x")]


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
