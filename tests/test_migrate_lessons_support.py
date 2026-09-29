"""Tests for migrate_lessons_support.py. Fixtures are byte-built where CRLF
is asserted (Archive/LL-149: a `write_text` fixture normalises to
`os.linesep` and cannot detect a newline rewrite), and never live under
plugins/planwise/."""
import itertools
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import backlog_index_schema as schema
import migrate_lessons_support as sup

NAMING = schema._index_naming(Path("00-Index-LessonsLearned.md"))

# ---------------------------------------------------------------------------
# Shape classification
# ---------------------------------------------------------------------------

LEGACY_TEXT = (
    "# Lessons Learned Index\n\n**Last Updated:** 2024-01-01\n\n---\n\n"
    "## Master Table\n\n| ID | Title |\n|---|---|\n\n---\n\n"
    "## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File |\n|---|---|---|---|\n\n---\n"
)
GENERATED_TEXT = "Generated: 2024-01-01\n**Next available ID:** LL-001\n\n| ID | Title |\n|---|---|\n"
UNRECOGNIZED_TEXT = "# Some Other Document\n\nJust prose, no table, no heading.\n"


def test_classify_shape_legacy():
    shape, detail = sup.classify_shape(LEGACY_TEXT)
    assert shape == "legacy" and "Master Table" in detail and "Rule Promotion Log" in detail


def test_classify_shape_generated():
    shape, detail = sup.classify_shape(GENERATED_TEXT)
    assert shape == "generated" and "Generated:" in detail


def test_classify_shape_unrecognized():
    shape, detail = sup.classify_shape(UNRECOGNIZED_TEXT)
    assert shape == "unrecognized" and "Generated:" in detail


def test_header_only_changelog_and_log():
    index_name = "00-Index-LessonsLearned.md"
    changelog_opener = f"[← {index_name}]({index_name})\n"
    assert sup.header_only(changelog_opener, index_name)
    log_opener = f"[← {index_name}]({index_name})\n\n{sup._LOG_HEADER}\n{sup._LOG_SEP}\n"
    assert sup.header_only(log_opener, index_name)
    assert not sup.header_only(changelog_opener + "## Entry 1\n\nSomething.\n", index_name)


# ---------------------------------------------------------------------------
# Region location
# ---------------------------------------------------------------------------

REGION_TEXT = (
    "# Lessons Learned Index\n\n"
    "**Last Updated:** 2024-01-01 (moved to changelog)\n\n"
    "<!-- known-condition: schedule note, scheduled fix: next sprint -->\n\n"
    "<!-- Previous: 2023-12-01 - older -->\n\n"
    "**Next available ID:** LL-042\n\n---\n\n"
    "## Master Table\n\n"
    "| ID | Title |\n|---|---|\n| LL-001 | Alpha |\n\n---\n\n"
    "## Quick Reference\n\n"
    "| Action | How |\n|---|---|\n\n---\n\n"
    "## Rule Promotion Log\n\n"
    "| Date | Lesson ID | Artifact Created | File |\n|---|---|---|---|\n"
    "| 2024-01-01 | LL-001 | note | [file](f.md) |\n\n"
    "> **Note on `applied` vs `rule` status**\n\n---\n"
)


def test_locate_regions_every_heading_and_between_master_and_log():
    regions = sup.locate_regions(REGION_TEXT)
    assert set(regions["sections"]) == {"Master Table", "Quick Reference", "Rule Promotion Log"}
    assert regions["header"]["last_updated"] is not None
    assert regions["header"]["known_condition"] is not None
    assert len(regions["header"]["previous"]) == 1
    assert regions["counter"] is not None
    # Master Table's body stops before '## Quick Reference' begins.
    mt = regions["sections"]["Master Table"]
    assert "Quick Reference" not in mt["body"]
    # The Promotion Log's Note line stays inside its own region (no next heading follows it).
    log = regions["sections"]["Rule Promotion Log"]
    assert "Note on `applied` vs `rule`" in log["body"]


def test_locate_regions_hub_with_no_promotion_log():
    text = "# Hub\n\n**Last Updated:** 2024-01-01\n\n---\n\n## Master Table\n\n| ID |\n|---|\n\n---\n"
    regions = sup.locate_regions(text)
    assert "Rule Promotion Log" not in regions["sections"]
    assert "Master Table" in regions["sections"]


def test_duplicate_heading_keeps_every_occurrence():
    text = ("# Hub\n\n## Notes\n\nFirst notes body.\n\n## Master Table\n\n| ID |\n|---|\n\n"
            "## Notes\n\nSecond notes body.\n")
    sections = sup.locate_regions(text)["sections"]
    notes = [s for s in sections.values() if s["heading"] == "Notes"]
    assert len(notes) == 2
    assert [n["body"].strip() for n in notes] == ["First notes body.", "Second notes body."]
    assert sections["Notes"]["body"].strip() == "First notes body."  # the first keeps the bare key
    assert all(s["heading"] == k for k, s in sections.items() if k in ("Master Table",))


def test_naming_convention_body_ignores_the_counter_line():
    a = "## Naming Convention\n\nSame text.\n\n**Next available ID:** LL-001\n\n## Archive\n\nMore.\n"
    b = "## Naming Convention\n\nSame text.\n\n**Next available ID:** LL-099\n\n## Archive\n\nMore.\n"
    ra, rb = sup.locate_regions(a), sup.locate_regions(b)
    assert ra["sections"]["Naming Convention"]["body"] == rb["sections"]["Naming Convention"]["body"]


# ---------------------------------------------------------------------------
# Header changelog extraction
# ---------------------------------------------------------------------------

def test_extract_header_changelog_previous_nested_and_known_condition_flagged():
    text = (
        "# Hub\n\n"
        "**Last Updated:** 2024-02-01 (a short history note)\n\n"
        "<!-- known-condition: fixed by next release, scheduled fix: soon -->\n\n"
        "<!-- Previous: 2024-01-01 - older entry -->\n\n"
        "<!-- Previous: 2023-12-01 - oldest entry -->\n\n"
        "---\n\n## Master Table\n\n| ID |\n|---|\n"
    )
    segments = sup.extract_header_changelog(text)
    kinds = [s["kind"] for s in segments]
    assert kinds.count("previous") == 2
    assert kinds.count("last-updated") == 1
    known = [s for s in segments if s["kind"] == "known-condition"]
    assert len(known) == 1 and known[0]["flag"] == "drop-with-ledger"


def test_extract_header_changelog_empty_when_no_history():
    text = "# Hub\n\n**Last Updated:** 2024-02-01\n\n---\n\n## Master Table\n\n| ID |\n|---|\n"
    segments = sup.extract_header_changelog(text)
    assert segments == []


# ---------------------------------------------------------------------------
# Changelog rendering
# ---------------------------------------------------------------------------

def test_render_changelog_under_budget_is_one_file():
    segments = [{"text": "First entry.", "flag": None}, {"text": "Second entry.", "flag": None}]
    out = sup.render_changelog(segments, "00-Index-LessonsLearned.md", "\n", "2026-09-27")
    assert len(out) == 1
    name, text = out[0]
    assert name == "00-Changelog-LessonsLearned.md"
    assert "## Entry 1" in text and "## Entry 2" in text
    assert text.startswith("[← 00-Index-LessonsLearned.md](00-Index-LessonsLearned.md)")


def test_render_changelog_over_budget_splits_into_one_archive():
    newest = {"text": "Newest small entry.", "flag": None}
    oldest = {"text": "x" * 60_000, "flag": None}  # ~23.1K tokens: over WARN, under PAGE_CAP alone
    out = sup.render_changelog([newest, oldest], "00-Index-LessonsLearned.md", "\n", "2026-09-27")
    assert len(out) == 2
    names = [n for n, _ in out]
    assert names[0] == "00-Changelog-LessonsLearned.md"
    assert names[1] == "00-Changelog-LessonsLearned-Archive-2026.md"
    current_text = out[0][1]
    archive_text = out[1][1]
    assert "Older entries" in current_text and names[1] in current_text
    assert current_text.count("## Entry") == 1  # only the newest stayed
    assert archive_text.startswith(f"[← {names[0]}]({names[0]})")
    assert "00-Index-LessonsLearned.md" in archive_text  # backlink to the hub too


def test_render_changelog_archive_over_page_cap_splits_into_part_02():
    tiny = {"text": "tiny newest entry", "flag": None}
    big1 = {"text": "y" * 35_000, "flag": None}
    big2 = {"text": "z" * 35_000, "flag": None}
    big3 = {"text": "w" * 35_000, "flag": None}
    out = sup.render_changelog([tiny, big1, big2, big3], "00-Index-LessonsLearned.md", "\n", "2026-09-27")
    names = [n for n, _ in out]
    assert names[0] == "00-Changelog-LessonsLearned.md"
    assert "00-Changelog-LessonsLearned-Archive-2026.md" in names
    assert "00-Changelog-LessonsLearned-Archive-2026-Part-02.md" in names
    assert len(names) == 3


def test_render_changelog_byte_identical_on_rerender():
    segments = [{"text": "a" * 30_000, "flag": None}, {"text": "b" * 30_000, "flag": None},
                {"text": "c" * 30_000, "flag": None}]
    first = sup.render_changelog(segments, "00-Index-LessonsLearned.md", "\n", "2026-09-27")
    second = sup.render_changelog(segments, "00-Index-LessonsLearned.md", "\n", "2026-09-27")
    assert first == second


def test_render_relocated_entry_titles_and_subheadings():
    body = sup.render_relocated_entry([("Quick Reference", "Adapted text.")], "2026-09-27")
    assert body.startswith("Relocated hand-written index sections (migrated 2026-09-27)")
    assert "### Quick Reference" in body and "Adapted text." in body


# ---------------------------------------------------------------------------
# Rule Promotion Log
# ---------------------------------------------------------------------------

LOG_TEXT = (
    "## Rule Promotion Log\n\n"
    "| Date | Lesson ID | Artifact Created | File |\n"
    "|------|-----------|-----------------|------|\n"
    "| 2024-01-01 | LL-010 | note ten | [f](f.md) |\n"
    "| 2024-01-02 | LL-060 | note sixty | [f](f.md) |\n"
    "| 2024-01-03 | LL-090 | note ninety | [f](f.md) |\n"
    "| 2024-01-04 | LL-150 | note onefifty | [f](f.md) |\n"
    "| 2024-01-05 | LL-250 | note twofifty | [f](f.md) |\n\n"
    "> **Note on `applied` vs `rule` status**\n\n---\n"
)


def test_walk_promotion_log_five_rows_all_present():
    rows = sup.walk_promotion_log(LOG_TEXT)
    assert len(rows) == 5
    assert [r["lesson_id"] for r in rows] == [10, 60, 90, 150, 250]
    assert all(not r["short"] and not r["fragmented"] for r in rows)


def test_log_destination_covers_all_five_bands():
    assert sup.log_destination(10, NAMING) == "Archive/PromotionLog-LessonsLearned-001-050.md"
    assert sup.log_destination(60, NAMING) == "Archive/PromotionLog-LessonsLearned-051-075.md"
    assert sup.log_destination(90, NAMING) == "Archive/PromotionLog-LessonsLearned-076-100.md"
    assert sup.log_destination(150, NAMING) == "Archive/PromotionLog-LessonsLearned-101-200.md"
    assert sup.log_destination(250, NAMING) == "00-PromotionLog-LessonsLearned.md"


def test_century_log_filenames_match_log_destination_over_century_ids():
    assert set(sup.century_log_filenames(NAMING)) == {
        sup.log_destination(i, NAMING) for i in range(1, 201)
    }


def test_render_promotion_logs_groups_by_destination():
    rows = sup.walk_promotion_log(LOG_TEXT)
    out = dict(sup.render_promotion_logs(rows, NAMING, "\n"))
    assert set(out) == {
        "Archive/PromotionLog-LessonsLearned-001-050.md",
        "Archive/PromotionLog-LessonsLearned-051-075.md",
        "Archive/PromotionLog-LessonsLearned-076-100.md",
        "Archive/PromotionLog-LessonsLearned-101-200.md",
        "00-PromotionLog-LessonsLearned.md",
    }
    hub_text = out["00-PromotionLog-LessonsLearned.md"]
    assert "LL-250" in hub_text and "Parts:" in hub_text
    for name in out:
        if name != "00-PromotionLog-LessonsLearned.md":
            assert name in hub_text


def test_walk_promotion_log_short_row_kept_and_flagged():
    text = (
        "## Rule Promotion Log\n\n"
        "| Date | Lesson ID | Artifact Created | File |\n"
        "|------|-----------|-----------------|------|\n"
        "| 2024-01-01 | LL-159 | note only |\n\n"
        "> **Note on `applied` vs `rule` status**\n\n---\n"
    )
    rows = sup.walk_promotion_log(text)
    assert len(rows) == 1 and rows[0]["short"] and rows[0]["lesson_id"] == 159
    assert len(rows[0]["cells"]) == 3


def test_walk_promotion_log_fragmented_row_is_rejoined():
    text = (
        "## Rule Promotion Log\n\n"
        "| Date | Lesson ID | Artifact Created | File |\n"
        "|------|-----------|-----------------|------|\n"
        "| 2024-01-01 | LL-020 | a note that continues\n"
        "onto the next physical line | [f](f.md) |\n\n"
        "> **Note on `applied` vs `rule` status**\n\n---\n"
    )
    rows = sup.walk_promotion_log(text)
    assert len(rows) == 1 and rows[0]["fragmented"] and rows[0]["lesson_id"] == 20
    assert "continues onto the next physical line" in rows[0]["cells"][2]


def test_walk_promotion_log_unjoinable_line_is_refused_naming_it():
    text = (
        "## Rule Promotion Log\n\n"
        "| Date | Lesson ID | Artifact Created | File |\n"
        "|------|-----------|-----------------|------|\n"
        "| 2024-01-01 | LL-020 | only two cells\n\n"
        "> **Note on `applied` vs `rule` status**\n\n---\n"
    )
    with pytest.raises(sup.Refusal, match="does not resolve to 3 or 4 cells"):
        sup.walk_promotion_log(text)


def test_walk_promotion_log_lone_cr_inside_cell_never_ends_a_row():
    row = "| 2024-01-01 | LL-030 | a note with a lone\rCR inside it | [f](f.md) |"
    text = (
        "## Rule Promotion Log\n\n"
        "| Date | Lesson ID | Artifact Created | File |\n"
        "|------|-----------|-----------------|------|\n"
        f"{row}\n\n"
        "> **Note on `applied` vs `rule` status**\n\n---\n"
    )
    rows = sup.walk_promotion_log(text)
    assert len(rows) == 1 and rows[0]["lesson_id"] == 30
    assert "\r" in rows[0]["cells"][2]


# ---------------------------------------------------------------------------
# Prose-section disposition
# ---------------------------------------------------------------------------

def test_section_disposition_drop_on_seed_equal_text():
    body = sup.SEED_BODIES["Archive"]
    disposition, reason = sup.section_disposition("Archive", body, sup.SEED_BODIES)
    assert disposition == "drop" and "equals the shipped seed" in reason


def test_section_disposition_relocate_on_one_changed_word():
    body = sup.SEED_BODIES["Archive"].replace("fully captured", "completely captured")
    disposition, _ = sup.section_disposition("Archive", body, sup.SEED_BODIES)
    assert disposition == "relocate"


def test_section_disposition_heading_match_is_exact():
    disposition, reason = sup.section_disposition("Archive (reworded)", sup.SEED_BODIES["Archive"], sup.SEED_BODIES)
    assert disposition == "relocate" and "no such section" in reason


# ---------------------------------------------------------------------------
# CRLF end to end -- byte-built fixtures (Archive/LL-149: a `write_text`
# fixture normalises to os.linesep and cannot detect a newline rewrite)
# ---------------------------------------------------------------------------

def test_crlf_preserved_end_to_end(tmp_path):
    crlf_text = (
        "# Hub\r\n\r\n**Last Updated:** 2024-01-01 (old history)\r\n\r\n---\r\n\r\n"
        "## Master Table\r\n\r\n| ID |\r\n|---|\r\n| LL-001 |\r\n\r\n---\r\n"
    )
    path = tmp_path / "legacy.md"
    path.write_bytes(crlf_text.encode("utf-8"))
    on_disk = path.read_bytes().decode("utf-8")
    assert sup.newline_of(on_disk) == "\r\n"
    segments = sup.extract_header_changelog(on_disk)
    out = sup.render_changelog(segments, "00-Index-LessonsLearned.md", "\r\n", "2026-09-27")
    name, text = out[0]
    written = tmp_path / name
    written.write_bytes(text.encode("utf-8"))
    raw = written.read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n")  # every \n is part of a \r\n pair


# ---------------------------------------------------------------------------
# The legacy seed's empty placeholder row in the Rule Promotion Log
# ---------------------------------------------------------------------------

def _log_text(data_rows: str) -> str:
    return ("## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File |\n"
            "|------|-----------|-----------------|------|\n" + data_rows + "\n---\n")


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_walk_promotion_log_skips_the_seed_placeholder_row(nl):
    text = _log_text("| | | | |\n| 2024-01-01 | LL-010 | note | [f](f.md) |\n").replace("\n", nl)
    path_bytes = text.encode("utf-8")
    skipped, refusals = [], []
    rows = sup.walk_promotion_log(path_bytes.decode("utf-8"), refusals, skipped)
    assert [r["lesson_id"] for r in rows] == [10]
    assert skipped == [5] and refusals == []
    assert sup.walk_promotion_log(text) == rows  # the default form skips it too, never raises


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_walk_promotion_log_partly_filled_idless_row_still_refuses_naming_the_line(nl):
    text = _log_text("| 2024-01-01 | | a note | [f](f.md) |\n").replace("\n", nl)
    with pytest.raises(sup.Refusal, match="line 5 has no parseable LL- id"):
        sup.walk_promotion_log(text)
    refusals: list = []
    assert sup.walk_promotion_log(text, refusals) == []
    assert refusals == [(sup.FIX_LOG_ROW, refusals[0][1])] and "line 5" in refusals[0][1]


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_walk_promotion_log_refuses_a_table_with_an_unrecognised_header(nl):
    text = ("## Rule Promotion Log\n\n| When | What |\n|---|---|\n| 2024-01-01 | LL-010 |\n\n---\n"
            ).replace("\n", nl)
    with pytest.raises(sup.Refusal, match="line 3 .*not the recognised header"):
        sup.walk_promotion_log(text)
    refusals: list = []
    leftover: list = []
    assert sup.walk_promotion_log(text, refusals, leftover=leftover) == []
    assert len(refusals) == 1 and refusals[0][0] == sup.FIX_LOG_ROW
    assert sup.promotion_log_residue(leftover) == ("", [])  # the refused table is not also residue


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_walk_promotion_log_collects_every_non_row_line_verbatim(nl):
    text = ("## Rule Promotion Log\n\nIntro prose before the table.\n\n"
            "| Date | Lesson ID | Artifact Created | File |\n|------|-----------|-----------------|------|\n"
            "| 2024-01-01 | LL-010 | note | [f](f.md) |\n\n"
            "> [!note] A callout after the table.\n\n"
            "> **Note on `applied` vs `rule` status:** kept.\n\n---\n").replace("\n", nl)
    leftover: list = []
    rows = sup.walk_promotion_log(text, [], leftover=leftover)
    assert [r["lesson_id"] for r in rows] == [10]
    body, lines = sup.promotion_log_residue(leftover)
    assert lines == [3, 9, 11]
    expected = (f"Intro prose before the table.{nl}{nl}> [!note] A callout after the table.{nl}{nl}"
                f"> **Note on `applied` vs `rule` status:** kept.{nl}{nl}---{nl}")
    assert body == expected


def test_promotion_log_residue_is_empty_for_the_seed_shape():
    leftover: list = []
    sup.walk_promotion_log(_log_text("| | | | |\n"), [], [], leftover=leftover)
    assert sup.promotion_log_residue(leftover) == ("", [])


def test_placeholder_predicate_needs_every_cell_empty():
    assert sup.is_placeholder_row(["", " ", ""])
    assert not sup.is_placeholder_row(["", "x", ""])


# ---------------------------------------------------------------------------
# Fence-aware, non-overlapping regions; byte-verbatim relocation
# ---------------------------------------------------------------------------

def _seed_hub(template_body: str, nl: str = "\n") -> str:
    """A hub laid out like the legacy seed: preamble, Naming Convention with
    its counter plus a multi-line drift comment, the fenced Lesson File
    Template, Archive, and both tables."""
    text = (
        "# Lessons Learned Index\n\n**Last Updated:** 2024-01-01 (history)\n"
        "<!-- Previous: 2023-12-01 (an older\n     two-line entry) -->\n\n---\n\n"
        "## Naming Convention\n\n" + sup.SEED_BODIES["Naming Convention"].replace("\n---\n", "") + "\n"
        "**Next available ID:** LL-001\n"
        "<!-- Derived by globbing the lessons directory (max on disk\n     LL-000). -->\n"
        "<!-- (Superseded field value, kept for the drift record: LL-000.) -->\n\n---\n\n"
        "## Master Table\n\n| ID | Title |\n|---|---|\n| | |\n\n---\n\n"
        "## Lesson File Template\n\n" + template_body + "\n---\n\n"
        "## Archive\n\n" + sup.SEED_BODIES["Archive"] + "\n"
        "## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File |\n|---|---|---|---|\n| | | | |\n"
    )
    return text.replace("\n", nl)


def test_fenced_headings_are_body_text_and_the_seed_template_drops():
    regions = sup.locate_regions(_seed_hub(sup.SEED_BODIES["Lesson File Template"]))
    assert set(regions["sections"]) == {"Naming Convention", "Master Table", "Lesson File Template",
                                        "Archive", "Rule Promotion Log"}
    template = regions["sections"]["Lesson File Template"]["body"]
    assert "## Context" in template and "## Applies To" in template
    assert sup.section_disposition("Lesson File Template", template, sup.SEED_BODIES)[0] == "drop"
    naming = regions["sections"]["Naming Convention"]["body"]
    assert sup.section_disposition("Naming Convention", naming, sup.SEED_BODIES)[0] == "drop"


def test_fence_closes_only_on_the_same_char_at_least_as_long():
    text = ("## Outer\n\n````md\n```\n## Not A Section\n~~~\n````\n\n## After\n\nx\n")
    assert set(sup.locate_regions(text)["sections"]) == {"Outer", "After"}
    unclosed = "## Outer\n\n```\n## Still A Section\n"
    assert set(sup.locate_regions(unclosed)["sections"]) == {"Outer", "Still A Section"}


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_regions_never_overlap_and_cover_every_byte_once(nl):
    text = _seed_hub(sup.SEED_BODIES["Lesson File Template"], nl)
    spans = sup.locate_regions(text)["spans"]
    assert spans[0][2] == 0 and spans[-1][3] == len(text)
    assert all(a[3] == b[2] for a, b in itertools.pairwise(spans))  # contiguous: no gap, no overlap
    assert sum(len(text[s:e].encode("utf-8")) for _k, _n, s, e in spans) == len(text.encode("utf-8"))
    counter = [text[s:e] for kind, _n, s, e in spans if kind == "counter"]
    assert len(counter) == 1 and "Next available ID" in counter[0] and "drift record" in counter[0]
    naming = sup.locate_regions(text)["sections"]["Naming Convention"]["body"]
    assert "Next available ID" not in naming and "<!--" not in naming
    segments = [s["text"] for s in sup.extract_header_changelog(text)]
    assert sum("Derived by globbing" in s for s in segments) == 1
    assert sum("drift record" in s for s in segments) == 1
    assert sum("two-line entry" in s for s in segments) == 1


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_relocated_fenced_section_is_byte_verbatim_apart_from_its_title(nl):
    edited = sup.SEED_BODIES["Lesson File Template"].replace("{What happened", "{What really happened")
    text = _seed_hub(edited, nl)
    regions = sup.locate_regions(text)
    section = regions["sections"]["Lesson File Template"]
    source = "".join(text[s:e] for kind, name, s, e in regions["spans"]
                     if kind == "section" and name == "Lesson File Template")
    title_line = source[:source.index("\n") + 1]
    assert title_line.rstrip("\r\n") == "## Lesson File Template"
    assert section["body"] == source[len(title_line):]
    entry = sup.render_relocated_entry([("Lesson File Template", section["body"])], "2026-09-27")
    (_name, out), = sup.render_changelog([entry], "00-Index-LessonsLearned.md", nl, "2026-09-27")
    assert "#" + source in out  # `## ` -> `### ` on the title line; every other byte unchanged
    assert "### Context" not in out and "## Context" in out


# ---------------------------------------------------------------------------
# `header_only` recognises what the lessons bootstrap actually seeds
# ---------------------------------------------------------------------------

SEED_DIR = SCRIPTS.parent / "seed"
SEED_CHANGELOG = SEED_DIR / "00-Changelog-LessonsLearned.md"
SEED_PROMOTION_LOG = SEED_DIR / "00-PromotionLog-LessonsLearned.md"
CUSTOM_INDEX = "Lessons-Index.md"
LOG_ROW = "| 2024-01-01 | LL-201 | a rule | [r](r.md) |"


@pytest.mark.parametrize("seed", [SEED_CHANGELOG, SEED_PROMOTION_LOG], ids=["changelog", "promotion-log"])
@pytest.mark.parametrize("index_name", ["00-Index-LessonsLearned.md", CUSTOM_INDEX])
def test_header_only_accepts_the_real_shipped_seed_bytes(seed, index_name):
    raw = seed.read_bytes().decode("utf-8")
    assert sup.header_only(raw, index_name)  # a custom hub name still carries the seed's default backlink
    assert sup.header_only(raw.replace("\r\n", "\n"), index_name)
    assert sup.header_only("﻿" + raw.replace("\r\n", "\n").replace("\n", "\r\n"), index_name)


@pytest.mark.parametrize("index_name", ["00-Index-LessonsLearned.md", CUSTOM_INDEX])
@pytest.mark.parametrize("sep", ["|---|---|---|---|", sup._LOG_SEP, "| --- | --- | --- | --- |"])
def test_header_only_accepts_any_dash_separator_for_the_log_header(index_name, sep):
    opener = f"[← {index_name}]({index_name})\n\n{sup._LOG_HEADER}\n{sep}\n"
    assert sup.header_only(opener, index_name)
    assert sup.header_only(opener.replace("\n", "\r\n"), index_name)
    assert not sup.header_only(opener + LOG_ROW + "\n", index_name)


@pytest.mark.parametrize("seed", [SEED_CHANGELOG, SEED_PROMOTION_LOG], ids=["changelog", "promotion-log"])
def test_header_only_rejects_a_seed_file_carrying_one_real_row(seed):
    raw = seed.read_bytes().decode("utf-8")
    nl = sup.newline_of(raw)
    assert not sup.header_only(raw + LOG_ROW + nl, "00-Index-LessonsLearned.md")
    assert not sup.header_only(raw + "## Entry 1" + nl + nl + "Something." + nl, CUSTOM_INDEX)


# ---------------------------------------------------------------------------
# The counter block inside the Rule Promotion Log section is header history,
# never promotion-log residue
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_counter_inside_the_log_section_is_not_residue(nl):
    text = ("# Hub\n\n## Master Table\n\n| ID |\n|---|\n\n"
            "## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File |\n"
            "|------|-----------|-----------------|------|\n| 2024-01-01 | LL-010 | note | [f](f.md) |\n\n"
            "**Next available ID:** LL-011\n<!-- Drift record: the counter read LL-009 once. -->\n\n---\n"
            ).replace("\n", nl)
    refusals: list = []
    leftover: list = []
    rows = sup.walk_promotion_log(text, refusals, leftover=leftover)
    assert [r["lesson_id"] for r in rows] == [10] and refusals == []
    assert sup.promotion_log_residue(leftover) == ("", [])
    assert not any("Next available ID" in raw or "Drift record" in raw for _n, raw in leftover)
    segments = [s["text"] for s in sup.extract_header_changelog(text)]
    assert sum("Drift record" in s for s in segments) == 1  # the header side owns it, once


# ---------------------------------------------------------------------------
# One changelog layout engine (re-review F9): the migrator's output is a
# fixed point of the writer's next `plan_split`
# ---------------------------------------------------------------------------

def _write_family(lessons_dir: Path, out: list, nl: str) -> Path:
    lessons_dir.mkdir(parents=True, exist_ok=True)
    for name, text in out:
        (lessons_dir / name).write_bytes(text.encode("utf-8"))
    return lessons_dir / "00-Index-LessonsLearned.md"


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_migrated_changelog_is_a_fixed_point_of_plan_split(tmp_path, nl):
    """Bodies carrying blank lines at either end, and one entry over the
    page cap so `plan_split` parses and re-lays out the family: a second
    engine that measures those blank lines packs differently, and the next
    upgrade would rewrite what the migration just wrote."""
    import lessons_changelog
    segments = [f"\n\nEntry text {k} " + "p" * 5_000 + "\n" * 400 for k in range(14)]
    segments.append({"text": "o" * 70_000, "flag": None})
    out = sup.render_changelog(segments, "00-Index-LessonsLearned.md", nl, "2026-09-27")
    assert len(out) >= 3
    index_path = _write_family(tmp_path / "LessonsLearned", out, nl)
    assert lessons_changelog.plan_split({}, index_path) is None


def test_render_changelog_refuses_a_body_that_would_not_read_back():
    """An unfenced `## Entry N` line inside a migrated body would split off a
    phantom entry; the engine's read-back check refuses it, naming the entry."""
    segments = [{"text": "Newest.", "flag": None}, {"text": "Body.\n## Entry 7\nmore", "flag": None}]
    with pytest.raises(sup.Refusal, match="Entry 1"):
        sup.render_changelog(segments, "00-Index-LessonsLearned.md", "\n", "2026-09-27")
