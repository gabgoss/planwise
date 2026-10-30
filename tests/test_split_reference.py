"""Tests for tools/split_reference.py, the dev-repo tool that moves whole sections
of a reference file into a new `{stem}-Part-N-{Topic}.md` sibling.

Every fixture is built in `tmp_path`. The tool is imported by path, the same way
the other dev-repo tool tests reach their module, and it is driven through its
seams: `plan_split`, `write_and_verify`, the module-level `_atomic_write_files`
name, and `main(argv)` returning the exit code.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(TESTS.parent / "tools"))

import check_section_citations
import split_reference as sr
from markdown_parser import extract_headings

from conftest import _snapshot_tree

SOURCE_NAME = "doc.md"
NEW_NAME = "doc-Part-2-Topic.md"

SOURCE_LF = (
    "---\n"
    "description: A fixture reference.\n"
    "---\n"
    "\n"
    "# Fixture Reference\n"
    "\n"
    "## 1. Alpha\n"
    "\n"
    "Alpha body line.\n"
    "\n"
    "## 2. Beta\n"
    "\n"
    "Beta body line.\n"
    "\n"
    "## 3. Gamma\n"
    "\n"
    "Gamma body line.\n"
    "\n"
    "## 4. Delta\n"
    "\n"
    "Delta body line.\n"
)

CITING_LF = (
    "# Citing File\n"
    "\n"
    "In range: doc.md §3 holds the gamma rule.\n"
    "In range, two sections: doc.md §3–§4 hold both.\n"
    "Spanning: doc.md §1–§3 names sections in both parts.\n"
    "Untouched: doc.md §1 stays in the first part.\n"
)


def _bytes(text: str, eol: str) -> bytes:
    return text.replace("\n", eol).encode("utf-8")


def build_tree(root: Path, eol: str = "\n", source: str = SOURCE_LF) -> Path:
    """Write references/doc.md and references/other.md; return the source path."""
    refs = root / "references"
    refs.mkdir(parents=True)
    (refs / SOURCE_NAME).write_bytes(_bytes(source, eol))
    (refs / "other.md").write_bytes(_bytes(CITING_LF, eol))
    return refs / SOURCE_NAME


def argv(source: Path, root: Path, *extra: str) -> list:
    return ["--source", str(source), "--sections", "3-4", "--part-name", "Part-2-Topic",
            "--citing-root", str(root), *extra]


def padded(title_count: int, filler_lines: int) -> str:
    """A four-section source whose sections 1-2 and 3-4 are about equal in size."""
    filler = "".join(f"Filler sentence number {i} for the size fixture.\n"
                     for i in range(filler_lines))
    out = ["---\ndescription: A size fixture.\n---\n\n# Size Fixture\n\n"]
    for n in range(1, title_count + 1):
        out.append(f"## {n}. Section{n}\n\n{filler}\n")
    return "".join(out)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def numbered(text: str) -> list:
    return [h.number for h in extract_headings(text) if h.number]


def run_json(capsys, args: list) -> tuple:
    code = sr.main([*args, "--json"])
    return code, json.loads(capsys.readouterr().out)


# --------------------------------------------------------------------------
# Dry run, hashes, frozen numbers
# --------------------------------------------------------------------------


def test_dry_run_writes_nothing(tmp_path, capsys):
    source = build_tree(tmp_path)
    before = _snapshot_tree(tmp_path)
    code, result = run_json(capsys, argv(source, tmp_path))
    assert code == 0
    assert result["status"] == "planned"
    assert _snapshot_tree(tmp_path) == before


def test_moved_body_and_remainder_hashes_match(tmp_path):
    source = build_tree(tmp_path)
    original = source.read_text(encoding="utf-8", newline="")
    plan = sr.plan_split(source, ["3", "4"], "Part-2-Topic", [tmp_path])

    # Derived here from the fixture text, not from the tool's own slicing.
    gamma = original[original.index("## 3. Gamma"):original.index("## 4. Delta")]
    delta = original[original.index("## 4. Delta"):]
    assert plan.checks["moved_body_sha256"] == {"3": sha(gamma), "4": sha(delta)}
    assert plan.checks["remainder_sha256"] == sha(original[:original.index("## 3. Gamma")])

    new_text = plan.writes[tmp_path / "references" / NEW_NAME]
    assert new_text.count(gamma) == 1
    assert new_text.count(delta) == 1


def test_heading_set_is_frozen_across_the_split(tmp_path):
    source = build_tree(tmp_path)
    before = numbered(source.read_text(encoding="utf-8"))
    assert main_ok(argv(source, tmp_path, "--apply"))
    in_source = numbered(source.read_text(encoding="utf-8"))
    in_new = numbered((source.parent / NEW_NAME).read_text(encoding="utf-8"))
    assert in_source == ["1", "2"]
    assert in_new == ["3", "4"]
    assert sorted(in_source + in_new) == sorted(before)
    assert not set(in_source) & set(in_new)


def main_ok(args: list) -> bool:
    return sr.main(args) == 0


# --------------------------------------------------------------------------
# Line endings
# --------------------------------------------------------------------------


@pytest.mark.parametrize("eol", ["\r\n", "\n"])
def test_line_endings_are_preserved_byte_for_byte(tmp_path, eol):
    source = build_tree(tmp_path, eol)
    other = source.parent / "other.md"
    assert main_ok(argv(source, tmp_path, "--apply"))
    for path in (source, source.parent / NEW_NAME, other):
        data = path.read_bytes()
        crlf = data.count(b"\r\n")
        bare_lf = data.count(b"\n") - crlf
        assert data.count(b"\r") == crlf
        if eol == "\r\n":
            assert crlf > 0 and bare_lf == 0, path.name
        else:
            assert crlf == 0 and bare_lf > 0, path.name


def test_mixed_line_endings_are_refused_without_a_write(tmp_path, capsys):
    source = build_tree(tmp_path, "\r\n")
    data = source.read_bytes()
    source.write_bytes(data.replace(b"Alpha body line.\r\n", b"Alpha body line.\n", 1))
    before = _snapshot_tree(tmp_path)
    code, result = run_json(capsys, argv(source, tmp_path, "--apply"))
    assert code == 1
    assert result["status"] == "refused"
    assert "mixed line endings" in result["reason"]
    assert _snapshot_tree(tmp_path) == before


# --------------------------------------------------------------------------
# Citations
# --------------------------------------------------------------------------


def test_in_range_citation_is_repointed_and_spanning_one_is_reported(tmp_path):
    source = build_tree(tmp_path)
    plan = sr.plan_split(source, ["3", "4"], "Part-2-Topic", [tmp_path])
    repointed = {r["before"] for r in plan.repoints}
    assert repointed == {"doc.md §3", "doc.md §3–§4"}
    assert [s["citation"] for s in plan.spanning] == ["doc.md §1–§3"]

    assert main_ok(argv(source, tmp_path, "--apply"))
    text = (source.parent / "other.md").read_text(encoding="utf-8")
    assert f"{NEW_NAME} §3 holds the gamma rule." in text
    assert f"{NEW_NAME} §3–§4 hold both." in text
    assert "doc.md §1–§3 names sections in both parts." in text  # dual citation stays as is
    assert "doc.md §1 stays in the first part." in text


# --------------------------------------------------------------------------
# Rollback
# --------------------------------------------------------------------------


def test_post_write_mismatch_restores_the_originals(tmp_path, monkeypatch, capsys):
    source = build_tree(tmp_path)
    before = _snapshot_tree(tmp_path)
    real_writer = sr._atomic_write_files
    calls = []

    def corrupting_writer(files, deletes):
        real_writer(files, deletes)
        if not calls:  # only the first (forward) write is corrupted, not the restore
            victim = next(iter(files))
            victim.write_bytes(victim.read_bytes() + b"X")
        calls.append(sorted(p.name for p in files))

    monkeypatch.setattr(sr, "_atomic_write_files", corrupting_writer)
    code, result = run_json(capsys, argv(source, tmp_path, "--apply"))
    assert code == 1
    assert result["status"] == "refused"
    assert "originals restored" in result["reason"]
    assert len(calls) == 2  # forward write, then restore
    assert _snapshot_tree(tmp_path) == before  # includes the new Part being absent again


# --------------------------------------------------------------------------
# Segment index
# --------------------------------------------------------------------------


def test_segment_index_names_the_range_and_the_part_one_file(tmp_path):
    source = build_tree(tmp_path)
    assert main_ok(argv(source, tmp_path, "--apply"))
    new_text = (source.parent / NEW_NAME).read_text(encoding="utf-8")
    description = next(line for line in new_text.splitlines() if line.startswith("description:"))
    assert "§3–§4" in description
    assert SOURCE_NAME in description
    assert "Part 2 of 2" in description

    parent = source.read_text(encoding="utf-8")
    assert "Part 1 of 2" in parent  # the parent's description carries the templated count
    held = [line for line in parent.splitlines() if "held in" in line and NEW_NAME in line]
    assert len(held) == 2  # one pointer per moved section
    assert any("§3" in line for line in held) and any("§4" in line for line in held)


# --------------------------------------------------------------------------
# WARN guard measures the results, not the source
# --------------------------------------------------------------------------


def _set_warn(monkeypatch, tokens: int) -> None:
    monkeypatch.setattr(sr, "READ_TOKEN_WARN", tokens)
    monkeypatch.setattr(sr, "READ_BYTE_WARN", 10**9)


def test_source_at_warn_with_two_ok_results_is_accepted(tmp_path, monkeypatch, capsys):
    source = build_tree(tmp_path, source=padded(4, 60))
    dry = sr.plan_split(source, ["3", "4"], "Part-2-Topic", [tmp_path])
    largest_result = max(m["tokens"] for m in dry.measurements)
    source_tokens = sr.measure_text(source, source.read_text(encoding="utf-8"))["tokens"]
    assert source_tokens > largest_result
    _set_warn(monkeypatch, largest_result + 1)

    assert sr.measure_text(source, source.read_text(encoding="utf-8"))["level"] == "WARN"
    code, result = run_json(capsys, argv(source, tmp_path, "--apply"))
    assert code == 0, result
    assert result["status"] == "applied"
    assert result["waived"] == []
    assert all(m["level"] == "OK" for m in result["plan"]["measurements"])


def test_result_at_warn_is_refused_and_accepted_with_allow_warn(tmp_path, monkeypatch, capsys):
    # Move one small section out of a large file: the remainder stays large.
    source = build_tree(tmp_path, source=padded(4, 60))
    args = ["--source", str(source), "--sections", "4", "--part-name", "Part-2-Topic",
            "--citing-root", str(tmp_path)]
    dry = sr.plan_split(source, ["4"], "Part-2-Topic", [tmp_path])
    by_name = {Path(m["path"]).name: m["tokens"] for m in dry.measurements}
    assert by_name[SOURCE_NAME] > by_name[NEW_NAME]
    _set_warn(monkeypatch, by_name[SOURCE_NAME])  # the remainder reaches it, the new Part does not
    before = _snapshot_tree(tmp_path)

    code, result = run_json(capsys, [*args, "--apply"])
    assert code == 1
    assert "WARN or OVER" in result["reason"] and SOURCE_NAME in result["reason"]
    assert _snapshot_tree(tmp_path) == before

    code, result = run_json(capsys, [*args, "--apply", "--allow-warn"])
    assert code == 0, result
    assert result["status"] == "applied"
    assert [Path(p).name for p in result["waived"]] == [SOURCE_NAME]
    assert (source.parent / NEW_NAME).is_file()


def _write_citer(source: Path, citations: int, filler: int) -> Path:
    body = "# Big Citer\n\n"
    body += "".join(f"Citation line {i}: doc.md §3 holds the gamma rule.\n" for i in range(citations))
    body += "".join(f"Filler sentence number {i} for the size fixture.\n" for i in range(filler))
    citer = source.parent / "citer.md"
    citer.write_bytes(body.encode("utf-8"))
    return citer


def test_citer_already_at_warn_with_unchanged_level_is_reported_not_refused(
        tmp_path, monkeypatch, capsys):
    source = build_tree(tmp_path)
    citer = _write_citer(source, citations=1, filler=60)
    citer_tokens = sr.measure_text(citer, citer.read_text(encoding="utf-8"))["tokens"]
    _set_warn(monkeypatch, citer_tokens - 3)  # the citer is WARN before and after its repoint
    dry = sr.plan_split(source, ["3", "4"], "Part-2-Topic", [tmp_path])
    levels = {Path(m["path"]).name: m["level"] for m in dry.measurements}
    assert levels["citer.md"] == "WARN"
    assert levels[SOURCE_NAME] == levels[NEW_NAME] == "OK"

    code, result = run_json(capsys, argv(source, tmp_path, "--apply"))
    assert code == 0, result
    assert result["status"] == "applied"
    assert result["waived"] == []
    assert [Path(p).name for p in result["pre_existing_level_unchanged"]] == ["citer.md"]
    assert f"{NEW_NAME} §3" in citer.read_text(encoding="utf-8")


def test_citer_pushed_from_ok_to_warn_by_the_repoint_is_refused(tmp_path, monkeypatch, capsys):
    source = build_tree(tmp_path)
    citer = _write_citer(source, citations=20, filler=40)
    before = sr.measure_text(citer, citer.read_text(encoding="utf-8"))["tokens"]
    dry = sr.plan_split(source, ["3", "4"], "Part-2-Topic", [tmp_path])
    after = next(m["tokens"] for m in dry.measurements if Path(m["path"]).name == "citer.md")
    assert after > before  # the longer file name adds bytes to every repointed line
    _set_warn(monkeypatch, after)  # OK before the repoint, WARN after it
    snapshot = _snapshot_tree(tmp_path)

    code, result = run_json(capsys, argv(source, tmp_path, "--apply"))
    assert code == 1
    assert "WARN or OVER" in result["reason"] and "citer.md" in result["reason"]
    assert _snapshot_tree(tmp_path) == snapshot

    code, result = run_json(capsys, argv(source, tmp_path, "--apply", "--allow-warn"))
    assert code == 0, result
    assert [Path(p).name for p in result["waived"]] == ["citer.md"]


# --------------------------------------------------------------------------
# Refusals and usage
# --------------------------------------------------------------------------


def test_description_without_a_part_count_is_refused_on_a_later_split(tmp_path, capsys):
    source = build_tree(tmp_path)
    assert main_ok(argv(source, tmp_path, "--apply"))
    capsys.readouterr()  # drop the first run's text report so the next stdout is pure JSON
    part2 = source.parent / NEW_NAME
    text = part2.read_text(encoding="utf-8")
    old = next(line for line in text.splitlines() if line.startswith("description:"))
    part2.write_text(text.replace(old, "description: Split out of doc.md §3 and §4."),
                     encoding="utf-8", newline="")
    before = _snapshot_tree(tmp_path)
    args = ["--source", str(source), "--sections", "2", "--part-name", "Part-3-More"]
    code, result = run_json(capsys, [*args, "--apply"])
    assert code == 1
    assert "Part k of N" in result["reason"]
    assert _snapshot_tree(tmp_path) == before


def test_part_number_must_append_to_the_family(tmp_path, capsys):
    source = build_tree(tmp_path)
    args = ["--source", str(source), "--sections", "3-4", "--part-name", "Part-5-Topic"]
    code, result = run_json(capsys, args)
    assert code == 1
    assert "append, never insert" in result["reason"]


def test_malformed_part_name_is_a_usage_error(tmp_path):
    source = build_tree(tmp_path)
    with pytest.raises(SystemExit) as raised:
        sr.main(["--source", str(source), "--sections", "3-4", "--part-name", "Topic"])
    assert raised.value.code == 2


# --------------------------------------------------------------------------
# Integration: the citation checker reports no dangling citation afterward
# --------------------------------------------------------------------------


def _dangling(root: Path) -> list:
    return [f for f in check_section_citations.check_tree(root) if f.verdict == "dangling"]


def test_checker_reports_no_dangling_citation_after_the_split(tmp_path):
    source = build_tree(tmp_path)
    assert _dangling(tmp_path) == []
    assert main_ok(argv(source, tmp_path, "--apply"))
    findings = check_section_citations.check_tree(tmp_path)
    assert [f for f in findings if f.verdict in ("dangling", "unresolved-target")] == []
    in_range = [f for f in findings if f.file.endswith("other.md") and f.line in (3, 4)]
    assert in_range and all(f.verdict == "ok" and f.target.endswith(NEW_NAME) for f in in_range)


def test_checker_sees_a_hand_move_with_no_repoint(tmp_path):
    source = build_tree(tmp_path)
    text = source.read_text(encoding="utf-8", newline="")
    cut = text.index("## 3. Gamma")
    source.write_bytes(text[:cut].encode("utf-8"))
    # The new file is not named `doc-Part-N-*.md`: a sibling Part would make the
    # checker report a redirect, which does not fail.
    (source.parent / "moved-elsewhere.md").write_bytes(("# Moved\n\n" + text[cut:]).encode("utf-8"))
    # `doc.md §3` and `doc.md §4` now name sections doc.md no longer holds, so the
    # citations the split tool repoints are the ones that fail here.
    findings = [f for f in _dangling(tmp_path) if f.file.endswith("other.md")]
    assert findings, "the checker cannot see the move, so the clean run above proves nothing"


# --------------------------------------------------------------------------
# Re-splits: a family that an earlier split already made
# --------------------------------------------------------------------------


ALPHA = (
    "---\n"
    "description: The alpha fixture.\n"
    "---\n"
    "\n"
    "# Alpha\n"
    "\n"
    "## 1. One\n\nOne body.\n\n"
    "## 2. Two\n\nTwo body.\n\n"
    "## 3. Three\n\nThree body.\n\n"
    "## 4. Four\n\nFour body.\n\n"
    "## 5. Five\n\nFive body.\n"
)

ALPHA_NESTED = ALPHA.replace(
    "## 3. Three\n\nThree body.\n\n",
    "## 3. Three\n\nThree body.\n\n"
    "### 3.1 Sub one\n\nSub one body.\n\n"
    "### 3.2 Sub two\n\nSub two body.\n\n"
    "### 3.3 Sub three\n\nSub three body.\n\n",
)

NUMBERED_H1 = (
    "---\n"
    "description: Numbered at the top level.\n"
    "---\n"
    "\n"
    "# 1. First\n\nFirst body.\n\n"
    "## 1.1 Inner\n\nInner body.\n\n"
    "# 2. Second\n\nSecond body.\n"
)


def build_alpha(root: Path, text: str = ALPHA) -> Path:
    refs = root / "references"
    refs.mkdir(parents=True)
    path = refs / "alpha.md"
    path.write_bytes(text.encode("utf-8"))
    return path


def split(source: Path, sections: str, part_name: str, root: Path) -> int:
    return sr.main(["--source", str(source), "--sections", sections, "--part-name", part_name,
                    "--citing-root", str(root), "--apply"])


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def pointer_leads(text: str) -> list:
    return [line for line in text.splitlines() if line.startswith(sr._POINTER_LEAD)]


def description(text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith("description:"))


def held_lines(text: str) -> dict:
    """Map `§N` to its "held in" line, for the tool's own held-in shape."""
    return {line.split(" ")[2]: line for line in text.splitlines() if " — held in " in line}


def test_a_second_split_replaces_each_pointer_block(tmp_path):
    alpha = build_alpha(tmp_path)
    assert split(alpha, "4-5", "Part-2-Later", tmp_path) == 0
    assert split(alpha, "2", "Part-3-Second", tmp_path) == 0
    refs = alpha.parent
    texts = {name: read(refs / name)
             for name in ("alpha.md", "alpha-Part-2-Later.md", "alpha-Part-3-Second.md")}
    for name, text in texts.items():
        leads = pointer_leads(text)
        assert len(leads) == 1, (name, leads)
        assert "split across three files" in leads[0], name
    assert "> This part carries §1, §3." in texts["alpha.md"]
    assert "> This part carries §4–§5." in texts["alpha-Part-2-Later.md"]
    assert "> This part carries §2." in texts["alpha-Part-3-Second.md"]
    assert "§1, §3 live in Part 1" in pointer_leads(texts["alpha-Part-2-Later.md"])[0]
    assert "§2 lives in Part 3" in pointer_leads(texts["alpha-Part-2-Later.md"])[0]


def test_a_resplit_of_a_part_rederives_ranges_and_held_in_lines(tmp_path):
    alpha = build_alpha(tmp_path)
    assert split(alpha, "4-5", "Part-2-Later", tmp_path) == 0
    part2 = alpha.parent / "alpha-Part-2-Later.md"
    assert split(part2, "5", "Part-3-Last", tmp_path) == 0
    part3 = alpha.parent / "alpha-Part-3-Last.md"

    assert "holding §4." in description(read(part2))
    assert "§4–§5" not in description(read(part2))
    assert "holding §5." in description(read(part3))
    held = held_lines(read(alpha))
    assert "alpha-Part-2-Later.md" in held["§4"]
    assert "alpha-Part-3-Last.md" in held["§5"]
    assert "> [!note] Moved to Parts 2 and 3" in read(alpha)


def test_range_text_the_tool_cannot_rederive_is_reported(tmp_path):
    alpha = build_alpha(tmp_path)
    assert split(alpha, "4-5", "Part-2-Later", tmp_path) == 0
    part2 = alpha.parent / "alpha-Part-2-Later.md"
    text = part2.read_text(encoding="utf-8", newline="")
    part2.write_text(text.replace(description(text),
                                  "description: Part 2 of 2 of the alpha reference. "
                                  "It covers §4 and §5."),
                     encoding="utf-8", newline="")
    text = alpha.read_text(encoding="utf-8", newline="")
    alpha.write_text(text.replace(held_lines(text)["§4"], "> - §4 Four — see the later part"),
                     encoding="utf-8", newline="")

    plan = sr.plan_split(part2, ["5"], "Part-3-Last", [tmp_path])
    found = [(Path(f["file"]).name, f["kind"]) for f in plan.reports["may_now_be_false"]]
    assert any(name == part2.name and "description" in kind for name, kind in found), found
    assert any(name == "alpha.md" and "held-in" in kind for name, kind in found), found


def test_a_split_of_a_later_part_titles_the_new_part_from_part_one(tmp_path):
    alpha = build_alpha(tmp_path)
    assert split(alpha, "4-5", "Part-2-Later", tmp_path) == 0
    assert split(alpha.parent / "alpha-Part-2-Later.md", "5", "Part-3-Last", tmp_path) == 0
    text = read(alpha.parent / "alpha-Part-3-Last.md")
    assert next(line for line in text.splitlines() if line.startswith("# ")) == \
        "# Alpha — Part 3: Last"


def test_a_nested_held_in_block_moves_with_its_parent_section(tmp_path):
    alpha = build_alpha(tmp_path, ALPHA_NESTED)
    assert split(alpha, "3.2", "Part-2-SubTwo", tmp_path) == 0
    assert split(alpha, "3", "Part-3-Three", tmp_path) == 0
    part3 = read(alpha.parent / "alpha-Part-3-Three.md")
    assert numbered(read(alpha)) == ["1", "2", "4", "5"]
    assert numbered(part3) == ["3", "3.1", "3.3"]
    assert "held in [`alpha-Part-2-SubTwo.md`](alpha-Part-2-SubTwo.md)" in part3


def test_pointer_block_is_written_when_its_slot_moves(tmp_path):
    source = build_alpha(tmp_path, NUMBERED_H1)
    assert split(source, "1", "Part-2-First", tmp_path) == 0
    text = read(source)
    assert len(pointer_leads(text)) == 1
    assert text.index(sr._POINTER_LEAD) < text.index("# 2. Second")


def test_pointer_block_with_no_kept_slot_is_refused(tmp_path, capsys):
    source = build_alpha(tmp_path, NUMBERED_H1)
    before = _snapshot_tree(tmp_path)
    code, result = run_json(capsys, ["--source", str(source), "--sections", "1-2",
                                     "--part-name", "Part-2-All", "--citing-root", str(tmp_path),
                                     "--apply"])
    assert code == 1
    assert "pointer block" in result["reason"]
    assert _snapshot_tree(tmp_path) == before


def test_each_file_is_read_once_per_run(tmp_path, monkeypatch):
    source = build_tree(tmp_path)
    handlers = tmp_path / "handlers"
    handlers.mkdir()
    # A reader the split does not edit: no pending write stands in for its text.
    (handlers / "run.md").write_bytes(b"Read doc.md first.\n")
    counts = {}
    real = sr.read_text_preserving_newlines

    def counting(path):
        key = Path(path).resolve()
        counts[key] = counts.get(key, 0) + 1
        return real(path)

    monkeypatch.setattr(sr, "read_text_preserving_newlines", counting)
    sr.plan_split(source, ["3", "4"], "Part-2-Topic", [tmp_path])
    assert counts and max(counts.values()) == 1, counts


def test_part_file_pattern_is_a_public_constant():
    assert sr.PART_FILE_RE.pattern == r"^(?P<stem>.+?)-Part-(?P<n>[0-9]+)-.+\.md$"
    match = sr.PART_FILE_RE.match("doc-Part-2-Topic.md")
    assert match["stem"] == "doc" and match["n"] == "2"
