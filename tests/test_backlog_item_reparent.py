"""Tests for backlog_item_reparent.py: the upgrade step that re-parents non-template item headings.

Every fixture is built in tmp_path as bytes, never under plugins/planwise/. The project and its generated
index come from the sibling test's `_project`, which calls the real index generator. The old-shape bodies
use the headings the step's synonym table names (Finding, Required Work, Done When), and each one is a
whole item file, so the router, the shape detector and the writer all read the real thing.

The known-bad arm of the preservation case is in the file: the same corrupt write, with the diff
switched off, is kept on disk, so the refusal test discriminates.
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for the sibling import below

import backlog_item_reparent as rp
import backlog_item_shape as shape
import backlog_migration as bm
import migrate_backlog_items as mbi
from test_migrate_backlog_items import (
    KEEP,
    LEGACY_INDEX,
    _item_path,
    _project,
    _snapshot,
)

H1 = "# BB-{n:03d}-01-INFRA-Fixture: A fixture item"
CORE_ORDER = ["Summary", "Problem", "Proposed Solution", "Acceptance Criteria"]


def old_item(number, sections, *, eol="\n", extra_fm=(), template_sections=(), footer=True):
    """An item whose body uses its own headings. `sections` is a list of (heading, body lines)."""
    lines = ["---", f"id: {number:03d}", 'title: "A fixture item"', "priority: Medium", "status: NOT_STARTED",
             "abbrev: INFRA", "created: 2026-11-18", "blocks: []", *extra_fm, "---", "",
             H1.format(n=number), "", "**Priority:** Medium", "**Domain:** INFRA", "", "---", ""]
    for heading in template_sections:
        lines += [f"## {heading}", "", "Template text.", ""]
    for heading, body in sections:
        lines += [f"## {heading}", "", *body, ""]
    lines += ["---", ""]
    if footer:
        lines.append("*Created: 2026-11-18*")
    return ("\n".join(lines) + "\n").replace("\n", eol).encode("utf-8")


OLD = [("Finding", ["The router counts this heading as a sub-item.", KEEP]),
       ("Required Work", ["1. Move the heading.", "2. Keep every line.", "3. Show the route."]),
       ("Done When", ["- The old heading is an H3 under a template section."])]


def _run(cfg, **kw):
    return rp.reparent_items(cfg, "1.0", "1.1", apply=True, **kw)


def _h2s(path: Path) -> list:
    body = shape._read(path)[1]
    return [name for _i, name in rp._h2s(body.split("\n"), rp.fence_flags_any_indent(body))]


def _h3s(path: Path) -> list:
    return [line[4:].strip() for line in path.read_text(encoding="utf-8").split("\n") if line.startswith("### ")]


def _nonblank(path: Path) -> list:
    return [line.rstrip() for line in path.read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n") if line.strip()]


def test_a_mapped_item_gets_template_h2s_and_the_old_headings_become_h3s(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)})
    path = _item_path(backlog, 1)
    before = _nonblank(path)
    report = _run(cfg)
    assert report.state == "migrated", report.detail
    assert _h2s(path) == ["Problem", "Proposed Solution", "Acceptance Criteria"]
    assert _h3s(path) == ["Finding", "Required Work", "Done When"]
    after = _nonblank(path)
    old_headings = {f"## {name}" for name, _body in OLD}
    kept = set(after)
    assert all(line in kept for line in before if line not in old_headings), "a prose line was lost"
    assert scan_nontemplate(backlog) == []


def scan_nontemplate(backlog: Path) -> list:
    return shape.scan_item_shapes(backlog).classes["section-nontemplate"]


def test_no_prose_line_is_lost_and_each_line_survives_the_same_number_of_times(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)})
    path = _item_path(backlog, 1)
    before = _nonblank(path)
    _run(cfg)
    after = _nonblank(path)
    old_headings = {f"## {name}" for name, _body in OLD}
    prose = [line for line in before if line not in old_headings]
    for line in set(prose):
        assert after.count(line) >= prose.count(line), line


def test_new_sections_land_in_template_order_before_related(tmp_path):
    items = {1: old_item(1, [("Done When", ["- Done."]), ("Finding", ["Seen."])], template_sections=("Related",))}
    cfg, backlog = _project(tmp_path, items)
    _run(cfg)
    assert _h2s(_item_path(backlog, 1)) == ["Problem", "Acceptance Criteria", "Related"]


def test_a_heading_moves_under_an_existing_core_section(tmp_path):
    items = {1: old_item(1, [("Evidence", ["Seen twice."])], template_sections=("Problem", "Related"))}
    cfg, backlog = _project(tmp_path, items)
    path = _item_path(backlog, 1)
    _run(cfg)
    text = path.read_text(encoding="utf-8")
    assert _h2s(path) == ["Problem", "Related"]
    assert text.index("## Problem") < text.index("### Evidence") < text.index("## Related")
    assert "Template text." in text and "Seen twice." in text


def test_an_unmapped_heading_is_listed_and_the_file_stays_as_written(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, [("Appendix", ["Loose notes."])])})
    before = _snapshot(backlog.parent)
    report = _run(cfg)
    assert report.state == "clean" and report.backed_up == []
    assert any("Appendix" in note for note in report.notes)
    assert _snapshot(backlog.parent) == before
    assert [name for name, target in report.candidates[0][1]] == ["Appendix"]


def test_an_unmapped_heading_beside_a_mapped_one_stays_an_h2(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, [("Finding", ["Seen."]), ("Appendix", ["Loose notes."])])})
    path = _item_path(backlog, 1)
    report = _run(cfg)
    assert report.state == "migrated"
    assert _h2s(path) == ["Problem", "Appendix"]
    assert _h3s(path) == ["Finding"]
    assert any("Appendix" in note for note in report.notes)


def test_the_route_report_shows_the_new_route(tmp_path):
    six = [(name, ["Text."]) for name in ("Finding", "Evidence", "Background")]
    six += [("Required Work", ["1. First step.", "2. Second step.", "3. Third step."]), ("Design", ["Text."]),
            ("Done When", ["- Done."])]
    cfg, _backlog = _project(tmp_path, {1: old_item(1, six)})
    report = _run(cfg)
    assert report.state == "migrated", report.detail
    assert report.routes == [("001", "C", "B")]
    assert any(line.startswith("  routes before -> after: 001: C -> B") for line in rp._banner_lines(report))


def test_nothing_sets_refined(tmp_path):
    items = {1: old_item(1, OLD), 2: old_item(2, OLD, extra_fm=("refined: false",))}
    cfg, backlog = _project(tmp_path, items)
    _run(cfg)
    assert "refined" not in _item_path(backlog, 1).read_text(encoding="utf-8").split("---")[1]
    assert "refined: false" in _item_path(backlog, 2).read_text(encoding="utf-8").split("---")[1]
    assert "refined: true" not in _item_path(backlog, 2).read_text(encoding="utf-8")


def test_a_second_run_writes_nothing_and_backs_up_nothing(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)})
    _run(cfg)
    settled = _snapshot(backlog.parent)
    again = _run(cfg)
    assert again.state == "clean" and again.backed_up == [] and again.written == []
    assert _snapshot(backlog.parent) == settled


def test_a_crlf_item_stays_crlf(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD, eol="\r\n")})
    path = _item_path(backlog, 1)
    report = _run(cfg)
    assert report.state == "migrated" and _h2s(path)[0] == "Problem"
    data = path.read_bytes()
    assert data.count(b"\r\n") == data.count(b"\n") > 0


def test_a_title_entry_is_applied_once_even_beside_an_unmapped_heading(tmp_path):
    items = {1: old_item(1, [("Finding", ["Seen."]), ("Appendix", ["Loose."])])}
    cfg, backlog = _project(tmp_path, items)
    path = _item_path(backlog, 1)
    data = rp.load_map(_write_map(tmp_path, {"titles": {"1": 'A "quoted" title'}}))
    assert _run(cfg, map_data=data).state == "migrated"
    settled = _snapshot(backlog.parent)
    again = _run(cfg, map_data=data)
    assert again.state == "clean" and again.backed_up == []
    assert _snapshot(backlog.parent) == settled
    assert path.read_text(encoding="utf-8").count("Previous title") == 1


def test_the_h1_is_retitled_only_when_it_ends_with_the_old_title_after_a_colon(tmp_path):
    lines, flags = ["# BB-007-01-INFRA-Slug: Prefix"], [False]
    fm = 'id: 007\ntitle: "fix"'
    _fm, body, old, replaced = rp._replace_title(fm, lines, flags, "New words")
    assert old == "fix" and body == ["# BB-007-01-INFRA-Slug: Prefix"] and len(replaced) == 1
    lines = ["# BB-007-01-INFRA-Slug: fix"]
    _fm, body, _old, replaced = rp._replace_title(fm, lines, flags, "New words")
    assert body == ["# BB-007-01-INFRA-Slug: New words"] and len(replaced) == 2


def test_a_map_entry_for_an_item_with_nothing_to_move_is_reported_not_dropped(tmp_path):
    cfg, _backlog = _project(tmp_path, {1: old_item(1, OLD), 2: old_item(2, [], template_sections=("Summary",))})
    data = rp.load_map(_write_map(tmp_path, {"titles": {"2": "Unused"}}))
    report = _run(cfg, map_data=data, ids=["1", "9"])
    assert any("titles entry for item 2" in note for note in report.notes)
    assert any("--ids 9" in note for note in report.notes)


def test_a_heading_inside_a_code_fence_is_not_moved(tmp_path):
    fenced = ["```", "## Finding", "```"]
    cfg, backlog = _project(tmp_path, {1: old_item(1, [("Notes on use", fenced)])})
    before = _snapshot(backlog.parent)
    report = _run(cfg)
    assert [name for name, _t in report.candidates[0][1]] == ["Notes on use"]
    assert _snapshot(backlog.parent) == before


def test_the_map_names_a_heading_a_title_and_a_summary(tmp_path):
    items = {1: old_item(1, [("Appendix", ["Loose notes."]), ("Finding", ["Seen."])])}
    cfg, backlog = _project(tmp_path, items)
    path = _item_path(backlog, 1)
    mapping = {"headings": {"appendix": "Problem"}, "titles": {"1": "A clearer title"},
               "summaries": {"001": "One sentence of summary."}}
    report = _run(cfg, map_data=rp.load_map(_write_map(tmp_path, mapping)))
    assert report.state == "migrated", report.detail
    text = path.read_text(encoding="utf-8")
    assert _h2s(path) == ["Summary", "Problem", "Notes"]
    assert text.index("### Appendix") < text.index("### Finding")  # file order within the section
    assert 'title: "A clearer title"' in text and "A fixture item" in text.split("## Notes")[1]
    assert "# BB-001-01-INFRA-Fixture: A clearer title" in text
    assert "One sentence of summary." in text
    assert report.counts["title"] == 1 and report.counts["summary"] == 1


def test_a_summary_is_written_only_where_none_exists(tmp_path):
    items = {1: old_item(1, [("Finding", ["Seen."])], template_sections=("Summary",))}
    cfg, backlog = _project(tmp_path, items)
    mapping = {"summaries": {"1": "Should not appear."}}
    _run(cfg, map_data=rp.load_map(_write_map(tmp_path, mapping)))
    assert "Should not appear." not in _item_path(backlog, 1).read_text(encoding="utf-8")


def _write_map(tmp_path: Path, data) -> Path:
    path = tmp_path / "map.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("data, fault", [
    ('{"headings": {"Old": "Notes"}}', "not one of"),
    ('{"colors": {}}', "unknown key"),
    ('{"titles": {"1": 5}}', "text to text"),
    ('[1, 2]', "one JSON object"),
    ('not json', "could not be read as JSON"),
    ('{"summaries": {"1": "line one\\r\\n## Extra\\nline"}}', "holds a heading"),
    ('{"summaries": {"1": "text\\n---\\nmore"}}', "thematic break"),
    ('{"titles": {"1": "' + "x" * 200 + '"}}', "characters"),
    ('{"titles": {"1": "Short\\n## Related"}}', "one non-empty line"),
    ('{"titles": {"1": "Short\\r## Related"}}', "one non-empty line"),
    ('{"titles": {"1": "   "}}', "one non-empty line"),
])
def test_a_bad_map_is_refused_and_names_its_fault(tmp_path, data, fault):
    with pytest.raises(ValueError, match=fault):
        rp.load_map(_write_map(tmp_path, data))


def test_the_limit_to_ids_leaves_other_items_alone(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD), 2: old_item(2, OLD)})
    control = _item_path(backlog, 2).read_bytes()
    report = _run(cfg, ids=["1"])
    assert report.state == "migrated"
    assert _item_path(backlog, 2).read_bytes() == control
    assert _h2s(_item_path(backlog, 1))[0] == "Problem"


def test_each_backup_is_byte_exact_and_predates_the_write(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)})
    original = _item_path(backlog, 1).read_bytes()
    report = _run(cfg)
    backup = report.backup_dir / _item_path(backlog, 1).name
    assert backup.read_bytes() == original
    assert report.backup_dir.name == "backlog-items" and report.backup_dir.parent.name == "1.0-to-1.1"


def _drop_the_kept_line(monkeypatch):
    """Corrupt the first write to each path. The restore is a second write to the same path, so it stays exact."""
    real, seen = bm._write_atomic, set()

    def corrupt(path, data):
        if path not in seen:
            seen.add(path)
            data = b"\n".join(line for line in data.split(b"\n") if KEEP.encode() not in line)
        real(path, data)
    monkeypatch.setattr(bm, "_write_atomic", corrupt)


def test_a_preservation_miss_restores_every_file_and_refuses(tmp_path, monkeypatch):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD), 2: old_item(2, OLD)})
    before = _snapshot(backlog.parent)
    _drop_the_kept_line(monkeypatch)
    report = _run(cfg)
    assert report.state == "refused" and "lost" in report.detail
    assert {k: v for k, v in _snapshot(backlog.parent).items() if not k.startswith("upgrade-backups")} == \
        {k: v for k, v in before.items() if not k.startswith("upgrade-backups")}


def test_known_bad_arm_without_the_diff_the_corrupt_write_is_kept(tmp_path, monkeypatch):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)})
    _drop_the_kept_line(monkeypatch)
    monkeypatch.setattr(mbi, "_dropped", lambda *args: [])
    report = _run(cfg)
    assert report.state == "migrated"
    assert KEEP not in _item_path(backlog, 1).read_text(encoding="utf-8")


def test_a_hand_authored_index_is_left_alone(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)}, index=LEGACY_INDEX)
    before = _snapshot(backlog.parent)
    report = _run(cfg)
    assert report.state == "skipped"
    assert _snapshot(backlog.parent) == before


def test_a_project_without_config_reports_absent(tmp_path):
    cfg, _backlog = _project(tmp_path, {})
    (cfg.project_root / "planwise" / "config.yaml").unlink()
    assert _run(cfg).state == "absent"


def test_a_raising_step_never_raises(tmp_path, monkeypatch):
    cfg, _backlog = _project(tmp_path, {1: old_item(1, OLD)})

    def boom(_dir):
        raise RuntimeError("scan failed")
    monkeypatch.setattr(shape, "graded_items", boom)
    report = _run(cfg)
    assert report.state == "error" and "scan failed" in report.detail


def test_list_prints_each_heading_with_its_section_and_writes_nothing(tmp_path, capsys):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD + [("Appendix", ["Loose."])])})
    before = _snapshot(backlog.parent)
    code = rp.main(["--config", str(cfg.project_root / "planwise" / "config.yaml"), "--list"])
    out = capsys.readouterr().out
    assert code == 0
    assert '"Finding" -> Problem' in out and '"Required Work" -> Proposed Solution' in out
    assert '"Appendix" -> (no core section)' in out
    assert _snapshot(backlog.parent) == before


def test_apply_needs_the_upgrade_pair(tmp_path, capsys):
    cfg, _backlog = _project(tmp_path, {1: old_item(1, OLD)})
    with pytest.raises(SystemExit) as caught:
        rp.main(["--config", str(cfg.project_root / "planwise" / "config.yaml"), "--apply"])
    assert caught.value.code == 2
    assert "--upgrade-pair" in capsys.readouterr().err


def test_apply_through_the_command_line_moves_the_headings(tmp_path, capsys):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)})
    code = rp.main(["--config", str(cfg.project_root / "planwise" / "config.yaml"), "--apply",
                    "--upgrade-pair", "1.0-to-1.1"])
    assert code == 0
    assert "routes before -> after" in capsys.readouterr().out
    assert _h2s(_item_path(backlog, 1))[0] == "Problem"


def test_a_summary_with_crlf_is_written_with_lf_inside_the_item(tmp_path):
    cfg, backlog = _project(tmp_path, {1: old_item(1, [("Finding", ["Seen."])])})
    data = rp.load_map(_write_map(tmp_path, {"summaries": {"1": "first\r\nsecond"}}))
    assert data["summaries"]["1"] == "first\nsecond"
    _run(cfg, map_data=data)
    assert b"\r" not in _item_path(backlog, 1).read_bytes()


@pytest.mark.parametrize("pair", ["../..-to-x", "a/b-to-c", "1.0-to-..", "-to-1.1", "1.0-to-"])
def test_an_upgrade_pair_that_could_leave_the_backup_folder_is_refused(tmp_path, capsys, pair):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)})
    before = _snapshot(backlog.parent)
    with pytest.raises(SystemExit) as caught:
        rp.main(["--config", str(cfg.project_root / "planwise" / "config.yaml"), "--apply", "--upgrade-pair", pair])
    assert caught.value.code == 2 and "--upgrade-pair" in capsys.readouterr().err
    assert _snapshot(backlog.parent) == before


def test_a_bad_map_file_exits_1_before_any_write(tmp_path, capsys):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)})
    before = _snapshot(backlog.parent)
    code = rp.main(["--config", str(cfg.project_root / "planwise" / "config.yaml"), "--apply",
                    "--upgrade-pair", "1.0-to-1.1", "--map", str(_write_map(tmp_path, "[]"))])
    assert code == 1 and "one JSON object" in capsys.readouterr().err
    assert _snapshot(backlog.parent) == before


LONG_TITLE = "A fixture item whose title keeps going " + "and going " * 14


def long_title_item(number, sections, **kw):
    """`old_item` with a title over the cap, so the real shape grader flags it."""
    return old_item(number, sections, **kw).replace(b'title: "A fixture item"', b'title: "' + LONG_TITLE.encode() + b'"')


def test_list_names_an_over_cap_title_and_a_missing_summary_under_the_item(tmp_path):
    assert len(LONG_TITLE) > shape.TITLE_MAX_LEN
    items = {1: long_title_item(1, [("Finding", ["Seen."])]),
             2: old_item(2, [("Finding", ["Seen."])], template_sections=("Summary",))}
    cfg, _backlog = _project(tmp_path, items)
    report = rp.reparent_items(cfg, "1.0", "1.1", apply=False)
    gaps = {rp.normalize_id(ident): found for ident, found in report.gaps.items()}
    assert gaps == {"1": [f"title over {shape.TITLE_MAX_LEN} characters", "no Summary section"]}
    lines = rp._banner_lines(report)

    def row_of(number):  # the banner prints the id as the item file spells it, such as 001
        return next(i for i, line in enumerate(lines)
                    if line.startswith("    ") and not line.startswith("     ")
                    and rp.normalize_id(line.strip().split(":")[0]) == str(number))

    assert lines[row_of(1) + 1] == f"      also: title over {shape.TITLE_MAX_LEN} characters; no Summary section"
    assert not any(line.startswith("      also:") for line in lines[row_of(2) + 1:row_of(2) + 2])


def test_a_drafted_title_replaces_an_over_cap_one_and_the_original_survives_in_notes(tmp_path):
    items = {1: long_title_item(1, [("Finding", ["Seen."])])}
    cfg, backlog = _project(tmp_path, items)
    path = _item_path(backlog, 1)
    drafted = "A short drafted title"
    mapping = {"titles": {"1": drafted}, "summaries": {"1": "One sentence of summary."}}
    report = _run(cfg, map_data=rp.load_map(_write_map(tmp_path, mapping)))
    assert report.state == "migrated", report.detail
    text = path.read_text(encoding="utf-8")
    assert f'title: "{drafted}"' in text and len(drafted) < shape.TITLE_MAX_LEN
    assert text.split("## Notes")[1].count(f"- Previous title: {LONG_TITLE}") == 1
    assert _h2s(path) == ["Summary", "Problem", "Notes"]
    assert "title-over-cap" not in dict(shape.graded_items(backlog)[0][0][2])
    again = rp.reparent_items(cfg, "1.0", "1.1", apply=False)
    assert again.candidates == [] and again.gaps == {}


@pytest.mark.parametrize("title_rows", [b"title: >-\n  A folded title", b"title: |\n  A literal title",
                                        b'title: "A wrapped\n  title"'])
def test_a_title_that_spans_lines_is_left_in_place_with_a_note_and_the_headings_still_move(tmp_path, title_rows):
    # The real index generator cannot read a multi-line title, so a project fixture cannot hold one.
    # The writer's own planning step takes the item file directly.
    path = tmp_path / "BB-001-01-INFRA-Fixture.md"
    path.write_bytes(old_item(1, [("Finding", ["Seen."])]).replace(b'title: "A fixture item"', title_rows))
    notes = []
    plan = rp._plan_item(path, "001", rp._heading_table(None), {"1": "A new title"}, {}, notes)
    assert plan is not None
    new = plan["data"].decode("utf-8")
    assert title_rows.decode("utf-8") + "\n" in new and "A new title" not in new and "Previous title" not in new
    assert [change[0] for change in plan["changes"]] == ["moved", "created"]
    assert any("title was left in place" in note for note in notes)


def _footerless_run(tmp_path):
    """Run the writer on a body whose last section holds a rule line and that has no footer.

    A second moved section sits before it, so a tail left behind lands under the wrong section.
    Returns the text of the Problem section."""
    sections = [("Required Work", ["R."]), ("Finding", ["Text A.", "", "---", "", "Text B."])]
    data = old_item(1, sections, footer=False)
    data = data.rstrip()[:-3].rstrip() + b"\n"  # drop the closing rule: the body now ends inside the last section
    cfg, backlog = _project(tmp_path, {1: data})
    assert _run(cfg).state == "migrated"
    text = _item_path(backlog, 1).read_text(encoding="utf-8")
    return text.split("## Problem")[1].split("## Proposed Solution")[0]


def test_a_rule_line_inside_the_last_section_of_a_footerless_body_does_not_cut_the_section(tmp_path):
    problem = _footerless_run(tmp_path)
    assert problem.index("### Finding") < problem.index("Text A.") < problem.index("Text B.")


def test_known_bad_arm_the_old_footer_rule_leaves_the_tail_behind(tmp_path, monkeypatch):
    def old_limit(lines, flags):
        at = rp.mbi._footer_break(lines, flags)
        return len(lines) if at is None else at

    monkeypatch.setattr(rp, "_limit", old_limit)
    problem = _footerless_run(tmp_path)
    assert "Text A." in problem and "Text B." not in problem  # the tail stayed behind, under the next section


def test_a_title_entry_for_an_item_the_ids_flag_left_out_says_so(tmp_path):
    cfg, _backlog = _project(tmp_path, {1: old_item(1, OLD), 2: old_item(2, OLD)})
    data = rp.load_map(_write_map(tmp_path, {"titles": {"2": "Left out"}}))
    report = _run(cfg, map_data=data, ids=["1"])
    assert any("titles entry for item 2 was not used: --ids left that item out" in note for note in report.notes)


@pytest.mark.parametrize("value", [",", " ", ", ,"])
def test_a_blank_ids_flag_is_refused_and_never_widens_the_run(tmp_path, capsys, value):
    cfg, backlog = _project(tmp_path, {1: old_item(1, OLD)})
    before = _snapshot(backlog.parent)
    with pytest.raises(SystemExit) as caught:
        rp.main(["--config", str(cfg.project_root / "planwise" / "config.yaml"), "--apply",
                 "--upgrade-pair", "1.0-to-1.1", "--ids", value])
    assert caught.value.code == 2 and "--ids" in capsys.readouterr().err
    assert _snapshot(backlog.parent) == before


def test_the_synonym_table_targets_only_core_sections_and_its_keys_are_normalized():
    assert set(rp.SYNONYMS.values()) <= set(rp.CORE)
    assert all(key == rp._norm(key) for key in rp.SYNONYMS)
    assert rp._norm("Required Work:") == "required work"
