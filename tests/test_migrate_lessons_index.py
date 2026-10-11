"""Tests for migrate_lessons_index.py: the standalone lessons migrator CLI.

Fixtures are byte-built (`write_bytes`) so the CRLF assertions are
meaningful; a `write_text` fixture normalises to `os.linesep` and cannot
detect a newline rewrite.
"""
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import config_loader
import generate_lessons_index as gen
import lessons_bootstrap
import migrate_lessons_index as mig
import migrate_lessons_support as sup

CONFIG_YAML = (
    'project:\n'
    '  name: "MigrateLessonsIndexFixtureProject"\n'
    '  lessons_dir: "LessonsLearned"\n'
    '  index_files:\n'
    '    lessons: "00-Index-LessonsLearned.md"\n'
    'lesson_statuses:\n'
    '- documented\n- promoted\n- applied\n- rule\n- orphaned\n'
)

MASTER_HEADER = "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status |\n"
MASTER_SEP = "|----|----|----|----|----|----|----|----|----|\n"

LESSON_001 = (
    "---\nid: LL-001\ntitle: Fixture Lesson One\ncategory: process\nseverity: medium\n"
    "language: [python]\ntechnology: [claude-code]\ndomain: [PROC]\nsource: fixture\n"
    "status: documented\n---\n\n# LL-001-PROC: Fixture Lesson One\n\n## Context\n\nSomething happened.\n"
)

LESSON_002_NO_TITLE_NO_CATEGORY = (
    "---\nid: LL-002\nseverity: medium\nlanguage: [python]\ntechnology: [claude-code]\n"
    "domain: [PROC]\nsource: fixture\nstatus: documented\n---\n\n"
    "# LL-002-Backfilled Title\n\n## Context\n\nSomething else happened.\n"
)

LESSON_003 = (
    "---\nid: LL-003\ntitle: Fixture Lesson Three\ncategory: process\nseverity: low\n"
    "language: [python]\ntechnology: [claude-code]\ndomain: [PROC]\nsource: fixture\n"
    "status: documented\n---\n\n# LL-003-PROC: Fixture Lesson Three\n\n## Context\n\nA third thing happened.\n"
)

LESSON_004_HASH_TITLE = (
    "---\nid: LL-004\ntitle: Fixture #Four\ncategory: process\nseverity: low\n"
    "language: [python]\ntechnology: [claude-code]\ndomain: [PROC]\nsource: fixture\n"
    "status: documented\n---\n\n# LL-004-PROC: Fixture Four\n\n## Context\n\nA fourth thing happened.\n"
)

COMPANION_LEGACY = (
    "# Categorization\n\n**Last Updated:** 2024-01-01\n\n"
    "## A. Database (1)\n\n| ID | Title |\n|---|---|\n| **LL-001** | Fixture Lesson One |\n\n"
    "## Cross-cutting observations\n\nSome hand-written note.\n"
)


def _rows(*, harvest=False, status_row="documented", extra_004=False):
    row1_title = "Fixture Lesson One" + (
        " It also does a second thing worth noting here as a distinct sentence." if harvest else ""
    )
    text = (
        MASTER_HEADER + MASTER_SEP +
        f"| LL-001 | {row1_title} | process | medium | python | claude-code | PROC | fixture | documented |\n"
        "| LL-002 | Backfilled Title | process | medium | python | claude-code | PROC | fixture | documented |\n"
        f"| LL-003 | Fixture Lesson Three | process | low | python | claude-code | PROC | fixture | {status_row} |\n"
    )
    if extra_004:
        text += ("| LL-004 | Fixture #Four | process | low | python | claude-code | PROC | fixture | "
                 "documented |\n")
    return text


def _index_text(*, harvest=False, status_row="documented", reworded_quickref=True, promo=True,
                seed_naming=True, extra_004=False):
    naming_body = sup.SEED_BODIES["Naming Convention"] if seed_naming else (
        "**Format:** something else entirely, not the seed's text.\n\n---\n"
    )
    parts = [
        "# Lessons Learned Index\n\n",
        "**Last Updated:** 2024-01-01 (history)\n\n",
        "<!-- Previous: 2023-12-01 - older -->\n\n",
        f"**Next available ID:** LL-{'005' if extra_004 else '004'}\n\n---\n\n",
        "## Naming Convention\n\n", naming_body, "\n---\n\n",
        "## Master Table\n\n", _rows(harvest=harvest, status_row=status_row, extra_004=extra_004), "\n---\n\n",
        "## Quick Reference\n\n",
        ("| Action | How |\n|--------|-----|\n| Search | use /lessons |\n\n---\n\n" if reworded_quickref
         else sup.SEED_BODIES["Quick Reference"] + "\n---\n\n"),
    ]
    if promo:
        parts += [
            "## Rule Promotion Log\n\n",
            "| Date | Lesson ID | Artifact Created | File |\n|------|-----------|-----------------|------|\n",
            "| 2024-01-02 | LL-003 | a rule | [rule.md](rule.md) |\n\n---\n",
        ]
    return "".join(parts)


def _build(tmp_path, *, crlf=False, harvest=False, status_row="documented", reworded_quickref=True,
          promo=True, companion=True, seed_naming=True, extra_004=False, drop_lesson=None,
          index_name="00-Index-LessonsLearned.md"):
    planwise = tmp_path / "planwise"
    lessons_dir = planwise / "LessonsLearned"
    lessons_dir.mkdir(parents=True)
    (lessons_dir / "Archive").mkdir()
    (planwise / "config.yaml").write_bytes(
        CONFIG_YAML.replace('"00-Index-LessonsLearned.md"', f'"{index_name}"').encode("utf-8"))

    index_text = _index_text(harvest=harvest, status_row=status_row, reworded_quickref=reworded_quickref,
                             promo=promo, seed_naming=seed_naming, extra_004=extra_004)
    lessons = {"LL-001-PROC-One.md": LESSON_001, "LL-002-PROC-Two.md": LESSON_002_NO_TITLE_NO_CATEGORY,
              "LL-003-PROC-Three.md": LESSON_003}
    if extra_004:
        lessons["LL-004-PROC-Four.md"] = LESSON_004_HASH_TITLE
    if drop_lesson:
        lessons.pop(drop_lesson, None)
    nl = "\r\n" if crlf else "\n"
    (lessons_dir / index_name).write_bytes(index_text.replace("\n", nl).encode("utf-8"))
    for name, text in lessons.items():
        (lessons_dir / name).write_bytes(text.replace("\n", nl).encode("utf-8"))
    if companion:
        (lessons_dir / gen.COMPANION_FILENAME).write_bytes(COMPANION_LEGACY.replace("\n", nl).encode("utf-8"))

    saved_argv = sys.argv
    sys.argv = ["test_migrate_lessons_index", "--config", str(planwise / "config.yaml")]
    config = config_loader.load_config()
    sys.argv = saved_argv
    return config, lessons_dir / index_name, lessons_dir


def _plan(config, index_path, options=None):
    text = index_path.read_text(encoding="utf-8")
    shape, detail = sup.classify_shape(text)
    assert shape == "legacy"
    return mig.plan_migration(config, index_path, text, detail, options or mig.RepairOptions())


def _run(config, *args):
    ns = mig.build_parser().parse_args(list(args))
    return mig.run(config, ns)


# ---------------------------------------------------------------------------
# Refusals -- each names the flag that closes it
# ---------------------------------------------------------------------------


def test_row_resolving_to_zero_files_relocates_verbatim(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, drop_lesson="LL-002-PROC-Two.md")
    row = next(ln for ln in index_path.read_text(encoding="utf-8").split("\n") if ln.startswith("| LL-002 "))
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["relocated"]["rows"] == 1 and sorted(plan["resolved"]) == [1, 3]
    assert any(h == "Master Table row with no lesson file" and row in body for h, body in plan["relocate_sections"])
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = (lessons_dir / "00-Changelog-LessonsLearned.md").read_bytes().decode("utf-8")
    assert "### Master Table row with no lesson file\n" in changelog and row in changelog
    ledger = _ledger(lessons_dir)
    assert ledger["relocated"]["rows"] == 1 and ledger["unaccounted"] == 0
    assert ledger["verification"]["verified"] is True


def test_refuses_id_resolving_to_more_than_one_file(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    (lessons_dir / "LL-001-PROC-Dup.md").write_bytes(LESSON_001.encode("utf-8"))
    with pytest.raises(mig.Refusal, match="resolves to 2 file"):
        _plan(config, index_path)


def test_refuses_missing_frontmatter_without_backfill_flag(tmp_path):
    config, index_path, _lessons_dir = _build(tmp_path)
    with pytest.raises(mig.Refusal, match="--backfill-frontmatter"):
        _plan(config, index_path)


def test_refuses_title_needing_quotes_without_quote_flag(tmp_path):
    config, index_path, _lessons_dir = _build(tmp_path, extra_004=True)
    with pytest.raises(mig.Refusal, match="--quote-titles"):
        _plan(config, index_path, mig.RepairOptions(backfill_frontmatter=True))


def test_refuses_status_mismatch_without_reconcile_flag(tmp_path):
    config, index_path, _lessons_dir = _build(tmp_path, status_row="orphaned")
    with pytest.raises(mig.Refusal, match="--reconcile"):
        _plan(config, index_path, mig.RepairOptions(backfill_frontmatter=True))


def test_refuses_over_title_unit_without_harvest_flag(tmp_path):
    config, index_path, _lessons_dir = _build(tmp_path, harvest=True)
    with pytest.raises(mig.Refusal, match="--harvest-cells"):
        _plan(config, index_path, mig.RepairOptions(backfill_frontmatter=True))


def test_refuses_prose_section_differing_without_relocate_flag(tmp_path):
    config, index_path, _lessons_dir = _build(tmp_path)
    with pytest.raises(mig.Refusal, match="--relocate-prose"):
        _plan(config, index_path, mig.RepairOptions(backfill_frontmatter=True))


def test_companion_rename_target_already_exists_keeps_its_bytes_and_gains_a_dated_heading(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    (lessons_dir / gen.NOTES_FILENAME).write_bytes(b"already here\n")
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    heading = f"## Companion migrated {plan['migration_date']}"
    assert plan["companion_rename"] == f"already here\n\n{heading}\n\n" + COMPANION_LEGACY
    assert plan["relocated"]["foreign_files"] == [gen.NOTES_FILENAME]


# ---------------------------------------------------------------------------
# --dry-run / --report
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(tmp_path):
    config, _index_path, lessons_dir = _build(tmp_path)
    before = {p: p.read_bytes() for p in lessons_dir.rglob("*") if p.is_file()}
    code = _run(config, "--dry-run", "--backfill-frontmatter", "--quote-titles", "--reconcile", "index-wins",
               "--harvest-cells", "--relocate-prose", "--allow-untracked-tree")
    assert code == 1
    after = {p: p.read_bytes() for p in lessons_dir.rglob("*") if p.is_file()}
    assert before == after


def test_report_never_writes_and_exits_zero_on_legacy(tmp_path):
    config, _index_path, lessons_dir = _build(tmp_path)
    before = {p: p.read_bytes() for p in lessons_dir.rglob("*") if p.is_file()}
    code = _run(config, "--report", "--json")
    assert code == 0
    after = {p: p.read_bytes() for p in lessons_dir.rglob("*") if p.is_file()}
    assert before == after


def test_report_on_generated_shape(tmp_path):
    config, _index_path, _lessons_dir = _build(tmp_path)
    assert _run(config, "--write", "--backfill-frontmatter", "--quote-titles", "--reconcile", "index-wins",
               "--harvest-cells", "--relocate-prose", "--allow-untracked-tree") == 0
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert report["shape"] == "generated"
    assert report["ready_with_all_repairs"] is True


def _entry_numbers(texts: list) -> list:
    return [int(n) for text in texts for n in re.findall(r"^## Entry (\d+)", text, re.MULTILINE)]


def test_render_changelog_numbers_are_stable_ascending_across_the_whole_family():
    """The newest entry gets the highest number and the count descends
    through the main file, the archive and every part -- never restarting
    at 1 in the archive."""
    segments = [{"text": "tiny newest entry", "flag": None}] + [
        {"text": ch * 35_000, "flag": None} for ch in "yzw"]
    out = sup.render_changelog(segments, "00-Index-LessonsLearned.md", "\n", "2026-09-27")
    assert len(out) == 3  # main, archive, -Part-02
    assert _entry_numbers([text for _name, text in out]) == [4, 3, 2, 1]


def test_migrated_changelog_numbers_descend_to_one(tmp_path):
    config, _index_path, lessons_dir = _build(tmp_path)
    assert _run(config, "--write", "--backfill-frontmatter", "--quote-titles", "--reconcile", "index-wins",
               "--harvest-cells", "--relocate-prose", "--allow-untracked-tree") == 0
    numbers = _entry_numbers([(lessons_dir / "00-Changelog-LessonsLearned.md").read_text(encoding="utf-8")])
    assert len(numbers) >= 2
    assert numbers == list(range(len(numbers), 0, -1))


def test_report_on_a_legacy_index_does_not_plan_the_changelog(tmp_path):
    """The upgrade routine plans a changelog re-split only on a generated
    index; the report matches it, so a legacy index's changelog (which the
    migration rewrites anyway) is never reported as a refusal."""
    config, _index_path, lessons_dir = _build(tmp_path)
    filler = "Lorem ipsum filler text describing a fixture entry body in full. " * 90
    body = "".join(f"## Entry {n}\n\n{filler}\n\n" for n in range(30, 0, -1))
    (lessons_dir / "00-Changelog-LessonsLearned.md").write_bytes(
        ("[← 00-Index-LessonsLearned.md](00-Index-LessonsLearned.md)\n\nA rogue paragraph.\n\n" + body)
        .encode("utf-8"))
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert report["shape"] == "legacy"
    assert report["changelog_resplit"] == "not_applicable"
    assert not any("outside any '## Entry' section" in item for item in report["would_refuse"])


def _capture_json(config, *args):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        _run(config, *args)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# --write with every flag: the generated family, --check clean, the ledger
# ---------------------------------------------------------------------------


class TestFullMigration:
    def _migrate(self, tmp_path, crlf=False):
        config, index_path, lessons_dir = _build(tmp_path, harvest=True, crlf=crlf)
        code = _run(config, "--write", "--backfill-frontmatter", "--quote-titles",
                   "--reconcile", "index-wins", "--harvest-cells", "--relocate-prose",
                   "--allow-untracked-tree")
        assert code == 0
        return config, index_path, lessons_dir

    def test_write_produces_generated_family_and_clean_checks(self, tmp_path):
        config, index_path, lessons_dir = self._migrate(tmp_path)
        text = index_path.read_text(encoding="utf-8")
        assert sup.classify_shape(text)[0] == "generated"
        naming = gen._index_naming(index_path)
        assert mig._check_index(lessons_dir, lessons_dir / "Archive", index_path, naming, config) == 0
        from types import SimpleNamespace
        assert gen._run_companion_cli(SimpleNamespace(write=False, json=False, replace_legacy=False),
                                      lessons_dir, lessons_dir / "Archive", index_path, naming, config) == 0

    def test_ledger_sections_present(self, tmp_path):
        _config, _index_path, lessons_dir = self._migrate(tmp_path)
        ledger = json.loads((lessons_dir / mig.LEDGER_FILENAME).read_text(encoding="utf-8"))
        for section in ("regions", "changelog", "promotion_log", "backfill", "quotes", "reconcile",
                        "cells", "prose", "companion", "generator", "unaccounted"):
            assert section in ledger

    def test_notes_file_holds_legacy_companion_bytes_verbatim(self, tmp_path):
        _config, _index_path, lessons_dir = self._migrate(tmp_path)
        notes = lessons_dir / gen.NOTES_FILENAME
        assert notes.is_file()
        assert notes.read_text(encoding="utf-8") == COMPANION_LEGACY
        companion = lessons_dir / gen.COMPANION_FILENAME
        assert "Cross-cutting observations" not in companion.read_text(encoding="utf-8")

    def test_over_title_units_appended_under_dated_heading(self, tmp_path):
        _config, _index_path, lessons_dir = self._migrate(tmp_path)
        lesson_one = next(lessons_dir.glob("LL-001-*.md"))
        body = lesson_one.read_text(encoding="utf-8")
        assert "## Index Note (migrated" in body
        assert "second thing worth noting" in body

    def test_missing_keys_backfilled_with_h1_title(self, tmp_path):
        _config, _index_path, lessons_dir = self._migrate(tmp_path)
        lesson_two = next(lessons_dir.glob("LL-002-*.md"))
        body = lesson_two.read_text(encoding="utf-8")
        assert "title: Backfilled Title" in body
        assert "category: process" in body

    def test_second_write_is_generated_idempotent(self, tmp_path):
        config, _index_path, lessons_dir = self._migrate(tmp_path)
        before = {p: p.read_bytes() for p in lessons_dir.rglob("*") if p.is_file()}
        code = _run(config, "--write", "--backfill-frontmatter", "--quote-titles",
                   "--reconcile", "index-wins", "--harvest-cells", "--relocate-prose",
                   "--allow-untracked-tree")
        assert code == 0
        after = {p: p.read_bytes() for p in lessons_dir.rglob("*") if p.is_file()}
        assert before == after

    def test_crlf_fixture_migrates_clean(self, tmp_path):
        _config, index_path, _lessons_dir = self._migrate(tmp_path, crlf=True)
        assert sup.classify_shape(index_path.read_text(encoding="utf-8"))[0] == "generated"


# ---------------------------------------------------------------------------
# `verify_written`: a planned output that does not land as staged fails the
# write and is named in the ledger; a clean run reports zero unaccounted.
# ---------------------------------------------------------------------------

_WRITE_ARGS = ("--write", "--backfill-frontmatter", "--quote-titles", "--reconcile", "index-wins",
              "--harvest-cells", "--relocate-prose", "--allow-untracked-tree")


def test_verify_written_reports_a_miss_and_fails_the_write(tmp_path, monkeypatch):
    config, _index_path, lessons_dir = _build(tmp_path)
    changelog_path = lessons_dir / "00-Changelog-LessonsLearned.md"
    real_replace_all = sup.replace_all

    def _corrupting_replace_all(staged):
        # Perform the real replace, then alter one already-staged output's
        # bytes on disk -- the seam `verify_written` re-reads from.
        done = real_replace_all(staged)
        if changelog_path in done:
            changelog_path.write_bytes(b"corrupted after replace\n")
        return done

    monkeypatch.setattr(sup, "replace_all", _corrupting_replace_all)
    code = _run(config, *_WRITE_ARGS)
    assert code == 1

    ledger = json.loads((lessons_dir / mig.LEDGER_FILENAME).read_text(encoding="utf-8"))
    assert ledger["verification"]["verified"] is False
    assert ledger["unaccounted"] >= 1
    assert any("00-Changelog-LessonsLearned.md" in m for m in ledger["verification"]["misses"])


def test_verify_written_clean_run_is_verified_with_zero_unaccounted(tmp_path):
    config, _index_path, lessons_dir = _build(tmp_path)
    assert _run(config, *_WRITE_ARGS) == 0
    ledger = json.loads((lessons_dir / mig.LEDGER_FILENAME).read_text(encoding="utf-8"))
    assert ledger["unaccounted"] == 0
    assert ledger["verification"]["verified"] is True


# ---------------------------------------------------------------------------
# Interrupted run: a generator crash on the first --write is recovered by
# a second --write, whose replanned relocation matches what is already on
# disk and which only needs to retry the generator step.
# ---------------------------------------------------------------------------


def test_interrupted_generator_step_recovers_on_rerun(tmp_path):
    config, index_path, _lessons_dir = _build(tmp_path)
    args = ("--write", "--backfill-frontmatter", "--quote-titles", "--reconcile", "index-wins",
           "--harvest-cells", "--relocate-prose", "--allow-untracked-tree")
    with patch("migrate_lessons_index.gen._cmd_write_lessons", side_effect=RuntimeError("boom")):
        code = _run(config, *args)
    assert code == 1
    # The relocation batch (changelog, promotion log, companion notes, lesson repairs) already
    # landed; the index itself is unchanged, so it is still legacy-shaped.
    assert sup.classify_shape(index_path.read_text(encoding="utf-8"))[0] == "legacy"

    code = _run(config, *args)
    assert code == 0
    assert sup.classify_shape(index_path.read_text(encoding="utf-8"))[0] == "generated"


def test_resume_at_generator_step_when_ledger_says_it_did_not_finish(tmp_path):
    config, _index_path, lessons_dir = _build(tmp_path)
    args = ("--write", "--backfill-frontmatter", "--quote-titles", "--reconcile", "index-wins",
           "--harvest-cells", "--relocate-prose", "--allow-untracked-tree")
    assert _run(config, *args) == 0

    ledger_file = mig.ledger_path_for(lessons_dir)
    ledger = json.loads(ledger_file.read_text(encoding="utf-8"))
    ledger["generator"]["companion_check_exit"] = 1
    ledger_file.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")

    code = _run(config, "--write", "--allow-untracked-tree")
    assert code == 0
    ledger_after = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert ledger_after["generator"]["companion_check_exit"] == 0


# ---------------------------------------------------------------------------
# --force / --allow-untracked-tree: proceed on a dirty or untracked tree
# ---------------------------------------------------------------------------


def test_allow_untracked_tree_proceeds_with_no_git_repo(tmp_path):
    config, _index_path, _lessons_dir = _build(tmp_path)
    code = _run(config, "--write", "--backfill-frontmatter", "--quote-titles", "--reconcile", "index-wins",
               "--harvest-cells", "--relocate-prose", "--allow-untracked-tree")
    assert code == 0


def test_force_flag_is_accepted_by_the_parser(tmp_path):
    _config, _index_path, _lessons_dir = _build(tmp_path)
    ns = mig.build_parser().parse_args(["--write", "--force", "--allow-untracked-tree"])
    assert ns.force is True


# ---------------------------------------------------------------------------
# A hub still shaped like the legacy seed: the empty placeholder row in both
# tables, the counter with its multi-line drift comment inside Naming
# Convention, and the Lesson File Template with its fenced `## ` lines.
# ---------------------------------------------------------------------------

PARTLY_FILLED_MASTER_ROW = "| | Some title | process | | | | | | |\n"
PARTLY_FILLED_LOG_ROW = "| 2024-01-02 | | a note | [f](f.md) |\n"


def _seed_shaped_index(extra_master="", extra_log=""):
    return (
        "# Lessons Learned Index\n\n**Purpose:** Central index.\n**Last Updated:** YYYY-MM-DD\n\n---\n\n"
        "## Naming Convention\n\n" + sup.SEED_BODIES["Naming Convention"].replace("\n---\n", "") + "\n"
        "**Next available ID:** LL-002\n"
        "<!-- Derived by globbing the lessons directory (max on disk\n     LL-001). -->\n\n---\n\n"
        "## Master Table\n\n" + MASTER_HEADER + MASTER_SEP + "| | | | | | | | | |\n" + extra_master +
        "| LL-001 | Fixture Lesson One | process | medium | python | claude-code | PROC | fixture | documented |\n"
        "\n---\n\n"
        "## Lesson File Template\n\n" + sup.SEED_BODIES["Lesson File Template"] + "\n---\n\n"
        "## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File |\n"
        "|------|-----------|-----------------|------|\n| | | | |\n" + extra_log + "\n---\n"
    )


def _build_seed_shaped(tmp_path, nl, **extra):
    config, index_path, lessons_dir = _build(tmp_path, crlf=(nl == "\r\n"), companion=False)
    for name in ("LL-002-PROC-Two.md", "LL-003-PROC-Three.md"):
        (lessons_dir / name).unlink()
    text = _seed_shaped_index(**extra).replace("\n", nl)
    index_path.write_bytes(text.encode("utf-8"))
    return config, index_path, lessons_dir, text


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_seed_placeholder_rows_are_skipped_and_counted(tmp_path, nl):
    config, index_path, lessons_dir, _text = _build_seed_shaped(tmp_path, nl)
    # Only --backfill-frontmatter (LL-001 lacks date/applied-as): the seed shape itself needs no flag.
    plan = _plan(config, index_path, mig.RepairOptions(backfill_frontmatter=True))
    assert plan["rows"] == 1 and plan["placeholders"] == {"master_table": 1, "promotion_log": 1}
    assert plan["drop_sections"] == ["Naming Convention", "Lesson File Template"]
    assert plan["relocate_sections"] == []
    assert _run(config, "--write", "--backfill-frontmatter", "--allow-untracked-tree") == 0
    ledger = json.loads((lessons_dir / mig.LEDGER_FILENAME).read_text(encoding="utf-8"))
    assert ledger["placeholder_rows_skipped"] == {"master_table": 1, "promotion_log": 1}
    assert ledger["unaccounted"] == 0 and ledger["verification"]["verified"] is True
    assert sup.classify_shape(index_path.read_text(encoding="utf-8"))[0] == "generated"
    changelog = (lessons_dir / "00-Changelog-LessonsLearned.md").read_bytes().decode("utf-8")
    assert changelog.count("Derived by globbing") == 1  # the drift comment travels once
    assert "### Context" not in changelog


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_partly_filled_idless_master_row_still_refuses_naming_its_line(tmp_path, nl):
    config, index_path, _lessons_dir, text = _build_seed_shaped(
        tmp_path, nl, extra_master=PARTLY_FILLED_MASTER_ROW)
    line = text.split(nl).index(PARTLY_FILLED_MASTER_ROW.rstrip("\n")) + 1
    with pytest.raises(mig.Refusal, match=f"Master Table row at line {line} does not parse"):
        _plan(config, index_path, mig.RepairOptions.all_on())


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_partly_filled_idless_log_row_still_refuses_naming_its_line(tmp_path, nl):
    config, index_path, _lessons_dir, text = _build_seed_shaped(tmp_path, nl, extra_log=PARTLY_FILLED_LOG_ROW)
    line = text.split(nl).index(PARTLY_FILLED_LOG_ROW.rstrip("\n")) + 1
    with pytest.raises(mig.Refusal, match=f"promotion-log row at line {line} has no parseable LL- id"):
        _plan(config, index_path, mig.RepairOptions.all_on())


# ---------------------------------------------------------------------------
# Every refusal in one run, grouped by what closes it
# ---------------------------------------------------------------------------

def test_two_refusal_causes_are_all_reported_in_one_run(tmp_path):
    # LL-001/LL-002 lack keys (--backfill-frontmatter) and Quick Reference differs from the seed
    # (--relocate-prose). LL-003's missing file relocates, so it is no refusal group.
    config, index_path, lessons_dir = _build(tmp_path, drop_lesson="LL-003-PROC-Three.md")
    with pytest.raises(mig.Refusal) as exc:
        _plan(config, index_path)
    message = str(exc.value)
    for fix, needle in ((sup.FIX_BACKFILL, "LL-002-PROC-Two.md"), (sup.FIX_RELOCATE, "'Quick Reference'")):
        assert f"{fix} (" in message and needle in message
    assert {fix for fix, _detail in exc.value.items} == {sup.FIX_BACKFILL, sup.FIX_RELOCATE}

    # --report plans with every repair flag on. The missing LL-003 file and the two foreign files
    # placed at output paths all relocate, so no refusal is left (3 before the relocations).
    (lessons_dir / "00-Changelog-LessonsLearned.md").write_bytes(b"foreign changelog content\n")
    (lessons_dir / gen.NOTES_FILENAME).write_bytes(b"foreign notes content\n")
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert report["would_refuse"] == [] and report["ready_with_all_repairs"] is True


# ---------------------------------------------------------------------------
# Review fixes: a block-less lesson, accepted --check classes, a foreign
# companion, duplicate headings, promotion-log prose, a later-day resume
# ---------------------------------------------------------------------------

_DRY_ARGS = ("--dry-run",) + _WRITE_ARGS[1:]
LESSON_002_NO_BLOCK = "# LL-002-PROC: Backfilled Title\n\n## Context\n\nThis file has no frontmatter block.\n"


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_lesson_file_with_no_frontmatter_block_is_backfilled(tmp_path, nl):
    config, _index_path, lessons_dir = _build(tmp_path, crlf=(nl == "\r\n"))
    path = lessons_dir / "LL-002-PROC-Two.md"
    original = LESSON_002_NO_BLOCK.replace("\n", nl)
    path.write_bytes(original.encode("utf-8"))
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert report["lessons"]["without_frontmatter"] == 1 and report["ready_with_all_repairs"] is True
    assert _run(config, *_DRY_ARGS) == 1
    assert _run(config, *_WRITE_ARGS) == 0
    written = path.read_bytes().decode("utf-8")
    assert written.startswith(f"---{nl}id: LL-002{nl}title: Backfilled Title{nl}")
    assert written.endswith(original)  # the new block is prepended; no original byte moves


def test_report_never_raises_whatever_the_input(tmp_path, monkeypatch):
    config, _index_path, _lessons_dir = _build(tmp_path)

    def boom(*_a, **_k):
        raise ValueError("unexpected input")
    monkeypatch.setattr(mig.repairs, "backfill_plan", boom)
    out = _capture_json(config, "--report", "--json")
    assert _run(config, "--report", "--json") == 0
    report = json.loads(out)
    assert report["shape"] == "legacy" and "unexpected input" in report["error"]


def _ledger(lessons_dir):
    return json.loads((lessons_dir / mig.LEDGER_FILENAME).read_text(encoding="utf-8"))


def test_index_wins_location_anomaly_is_an_accepted_check_result(tmp_path):
    # The row says `applied`, the top-level file says `documented`: index-wins moves the file's
    # status to a non-hub one, which the generator reports as a location-anomaly it never heals.
    config, _index_path, lessons_dir = _build(tmp_path, status_row="applied")
    assert _run(config, *_WRITE_ARGS) == 0
    generator = _ledger(lessons_dir)["generator"]
    assert generator["index_check_exit"] == 1 and generator["index_check_findings"] == ["location-anomaly"]
    assert _ledger(lessons_dir)["generator_verdict"] == "accepted"
    assert _run(config, "--write", "--allow-untracked-tree") == 0  # the resume path does not loop


def test_counter_ahead_is_an_accepted_check_result(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    text = index_path.read_bytes().decode("utf-8").replace("**Next available ID:** LL-004",
                                                           "**Next available ID:** LL-009")
    index_path.write_bytes(text.encode("utf-8"))
    assert _run(config, *_WRITE_ARGS) == 0
    assert _ledger(lessons_dir)["generator"]["index_check_findings"] == ["counter_ahead"]


def test_healable_check_finding_still_fails_the_write(tmp_path, monkeypatch):
    config, _index_path, lessons_dir = _build(tmp_path)
    real = gen._check_lessons_drift

    def with_stale_title(*args, **kwargs):
        findings, shape = real(*args, **kwargs)
        return findings + [{"class": "stale-title", "id": "LL-001", "detail": "x"}], shape
    monkeypatch.setattr(gen, "_check_lessons_drift", with_stale_title)
    assert _run(config, *_WRITE_ARGS) == 1
    assert _ledger(lessons_dir)["generator_verdict"] == "failed"


COMPANION_FOREIGN = "# My Own Categorisation\n\nHand-kept grouping notes, in no known shape.\n"
COMPANION_GENERATED_SHAPE = "Generated: 2024-01-01\n**Companion to:** x\n\n---\n\n## A. Things (0)\n"


def test_foreign_companion_is_renamed_to_the_notes_file_not_overwritten(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, companion=False)
    (lessons_dir / gen.COMPANION_FILENAME).write_bytes(COMPANION_FOREIGN.encode("utf-8"))
    assert _plan(config, index_path, mig.RepairOptions.all_on())["companion_rename"] == COMPANION_FOREIGN
    assert _run(config, *_WRITE_ARGS) == 0
    assert (lessons_dir / gen.NOTES_FILENAME).read_bytes() == COMPANION_FOREIGN.encode("utf-8")
    assert gen.is_generated_companion((lessons_dir / gen.COMPANION_FILENAME).read_text(encoding="utf-8"))


def test_notes_path_collision_appends_under_a_dated_heading(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, companion=False)
    (lessons_dir / gen.COMPANION_FILENAME).write_bytes(COMPANION_FOREIGN.encode("utf-8"))
    (lessons_dir / gen.NOTES_FILENAME).write_bytes(b"other notes\n")
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    expected = f"other notes\n\n## Companion migrated {plan['migration_date']}\n\n" + COMPANION_FOREIGN
    assert plan["companion_rename"] == expected
    assert _run(config, *_WRITE_ARGS) == 0
    assert (lessons_dir / gen.NOTES_FILENAME).read_bytes() == expected.encode("utf-8")
    assert _ledger(lessons_dir)["relocated"]["foreign_files"] == [gen.NOTES_FILENAME]


def test_generated_or_empty_companion_is_not_renamed(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, companion=False)
    for text in (COMPANION_GENERATED_SHAPE, COMPANION_GENERATED_SHAPE.replace("\n", "\r\n"), "\n"):
        (lessons_dir / gen.COMPANION_FILENAME).write_bytes(text.encode("utf-8"))
        assert _plan(config, index_path, mig.RepairOptions.all_on())["companion_rename"] is None


def _with_two_notes(index_path):
    text = index_path.read_bytes().decode("utf-8")
    text = text.replace("## Master Table", "## Notes\n\nFirst hand note.\n\n---\n\n## Master Table", 1)
    text = text.replace("## Quick Reference", "## Notes\n\nSecond hand note.\n\n---\n\n## Quick Reference", 1)
    index_path.write_bytes(text.encode("utf-8"))


def test_duplicate_prose_headings_are_each_dispositioned_relocated_and_verified(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    _with_two_notes(index_path)
    with pytest.raises(mig.Refusal) as exc:
        _plan(config, index_path, mig.RepairOptions(backfill_frontmatter=True))
    assert sum("'Notes'" in detail for fix, detail in exc.value.items if fix == sup.FIX_RELOCATE) == 2
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    notes = [body.strip() for heading, body in plan["relocate_sections"] if heading == "Notes"]
    assert notes == ["First hand note.\n\n---", "Second hand note.\n\n---"]
    assert _run(config, *_WRITE_ARGS) == 0
    changelog_path = lessons_dir / "00-Changelog-LessonsLearned.md"
    changelog = changelog_path.read_bytes().decode("utf-8")
    assert "First hand note." in changelog and "Second hand note." in changelog
    changelog_path.write_bytes(changelog.replace("Second hand note.", "").encode("utf-8"))
    misses = mig.verify_written(plan)
    assert any("'Notes'" in m and "Second hand note" in m for m in misses)


PROMO_WITH_PROSE = (
    "## Rule Promotion Log\n\nIntro prose for the log.\n\n"
    "| Date | Lesson ID | Artifact Created | File |\n|------|-----------|-----------------|------|\n"
    "| 2024-01-02 | LL-003 | a rule | [rule.md](rule.md) |\n\n"
    "> **Note on `applied` vs `rule` status:** a hand note.\n\n---\n"
)
PROMO_RESIDUE = "Intro prose for the log.\n\n> **Note on `applied` vs `rule` status:** a hand note.\n\n---\n"


def test_promotion_log_prose_is_relocated_verbatim_or_refused(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, promo=False)
    index_path.write_bytes((index_path.read_bytes().decode("utf-8") + PROMO_WITH_PROSE).encode("utf-8"))
    with pytest.raises(mig.Refusal) as exc:
        _plan(config, index_path, mig.RepairOptions(backfill_frontmatter=True))
    relocate = [d for fix, d in exc.value.items if fix == sup.FIX_RELOCATE and "Rule Promotion Log" in d]
    assert len(relocate) == 1 and "line" in relocate[0]
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert ("Rule Promotion Log", PROMO_RESIDUE) in plan["relocate_sections"]
    assert len(plan["promo_rows"]) == 1
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = (lessons_dir / "00-Changelog-LessonsLearned.md").read_bytes().decode("utf-8")
    assert "### Rule Promotion Log\n" + PROMO_RESIDUE in changelog
    assert _ledger(lessons_dir)["unaccounted"] == 0


def test_unrecognised_promotion_log_header_relocates_as_residue(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, promo=False)
    table = "| When | What |\n|---|---|\n| 2024-01-02 | LL-003 |\n"
    foreign = f"## Rule Promotion Log\n\n{table}\n---\n"
    index_path.write_bytes((index_path.read_bytes().decode("utf-8") + foreign).encode("utf-8"))
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["relocated"]["promotion_log_lines"] == 3 and plan["promo_rows"] == []
    assert any(h == "Rule Promotion Log" and table in body for h, body in plan["relocate_sections"])
    with pytest.raises(mig.Refusal, match="--relocate-prose"):
        _plan(config, index_path, mig.RepairOptions(backfill_frontmatter=True))
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = (lessons_dir / "00-Changelog-LessonsLearned.md").read_bytes().decode("utf-8")
    assert "### Rule Promotion Log\n" in changelog and table in changelog
    assert _ledger(lessons_dir)["relocated"]["promotion_log_lines"] == 3


def test_foreign_changelog_file_folds_in_as_newest_entry(tmp_path, monkeypatch):
    config, index_path, lessons_dir = _build(tmp_path)
    foreign = "# My own changelog\n\n## Entry 7\n\nHand-written history.\n\n```\nan unclosed fence\n"
    changelog_path = lessons_dir / "00-Changelog-LessonsLearned.md"
    changelog_path.write_bytes(foreign.encode("utf-8"))
    monkeypatch.setattr(mig, "_today", lambda: "2026-01-01")
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["relocated"]["foreign_files"] == [changelog_path.name]
    with patch("migrate_lessons_index.gen._cmd_write_lessons", side_effect=RuntimeError("boom")):
        assert _run(config, *_WRITE_ARGS) == 1
    monkeypatch.setattr(mig, "_today", lambda: "2026-01-02")
    assert _run(config, *_WRITE_ARGS) == 0  # the resume plans the same fold from its own earlier output
    title = "Pre-migration changelog file (migrated 2026-01-01)"
    changelog = changelog_path.read_bytes().decode("utf-8")
    assert changelog.count(title) == 1 and foreign.strip("\n") in changelog
    newest = re.search(r"^## Entry \d+\n\n(.*)", changelog, re.MULTILINE).group(1)
    assert newest == title  # the fold is the first entry in the file
    ledger = _ledger(lessons_dir)
    assert ledger["relocated"]["foreign_files"] == [changelog_path.name] and ledger["unaccounted"] == 0
    plan["folds"].append("a byte sequence nobody wrote")
    assert any("folded foreign file" in miss for miss in mig.verify_written(plan))


def test_foreign_promotion_log_folds_in_as_residue(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    name = gen._promotion_log_filename(mig._index_naming(index_path))
    foreign = "# My promotion notes\n\nKept by hand.\n"
    (lessons_dir / name).write_bytes(foreign.encode("utf-8"))
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["relocated"]["foreign_files"] == [name]
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = (lessons_dir / "00-Changelog-LessonsLearned.md").read_bytes().decode("utf-8")
    assert f"### Pre-migration promotion-log file {name}\n" in changelog
    assert foreign.strip("\n") in changelog
    assert "Kept by hand" not in (lessons_dir / name).read_bytes().decode("utf-8")
    ledger = _ledger(lessons_dir)
    assert ledger["relocated"]["foreign_files"] == [name] and ledger["unaccounted"] == 0


def test_resume_on_a_later_day_recognises_its_own_earlier_output(tmp_path, monkeypatch):
    config, _index_path, lessons_dir = _build(tmp_path, harvest=True)
    monkeypatch.setattr(mig, "_today", lambda: "2026-01-01")
    with patch("migrate_lessons_index.gen._cmd_write_lessons", side_effect=RuntimeError("boom")):
        assert _run(config, *_WRITE_ARGS) == 1
    monkeypatch.setattr(mig, "_today", lambda: "2026-01-02")
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = (lessons_dir / "00-Changelog-LessonsLearned.md").read_text(encoding="utf-8")
    assert "(migrated 2026-01-01)" in changelog and "2026-01-02" not in changelog
    lesson_one = next(lessons_dir.glob("LL-001-*.md")).read_text(encoding="utf-8")
    assert lesson_one.count("## Index Note (migrated") == 1
    assert _ledger(lessons_dir)["migration_date"] == "2026-01-01"


# ---------------------------------------------------------------------------
# What the lessons bootstrap seeds on every upgrade never blocks a migration:
# the categorization notes seed, and the changelog / promotion-log seeds
# ---------------------------------------------------------------------------

SEED_DIR = SCRIPTS.parent / "seed"
CUSTOM_INDEX = "Lessons-Index.md"


def _notes_seed(variant: str) -> str:
    text = lessons_bootstrap.NOTES_SEED_CONTENT
    if variant in ("crlf", "bom-crlf"):
        text = text.replace("\n", "\r\n")
    return ("﻿" + text) if variant == "bom-crlf" else text


@pytest.mark.parametrize("variant", ["lf", "crlf", "bom-crlf"])
def test_seed_equal_notes_file_counts_as_absent_for_the_rename(tmp_path, variant):
    config, index_path, lessons_dir = _build(tmp_path)  # a legacy companion that must move to the notes file
    notes = lessons_dir / gen.NOTES_FILENAME
    notes.write_bytes(_notes_seed(variant).encode("utf-8"))
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["companion_rename"] == COMPANION_LEGACY
    assert any(p.resolve() == notes.resolve() for p in mig.plan_targets(plan))  # backed up before the write
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert report["would_refuse"] == [] and report["ready_with_all_repairs"] is True
    assert _run(config, *_WRITE_ARGS) == 0
    assert notes.read_bytes() == COMPANION_LEGACY.encode("utf-8")


def test_hand_edited_notes_file_keeps_its_bytes_and_gains_the_companion_under_a_dated_heading(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    edited = lessons_bootstrap.NOTES_SEED_CONTENT + "| LL-001 | a judgment call | A. Things |\n"
    (lessons_dir / gen.NOTES_FILENAME).write_bytes(edited.encode("utf-8"))
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["companion_rename"].startswith(edited)
    assert f"## Companion migrated {plan['migration_date']}" in plan["companion_rename"]
    assert _run(config, *_WRITE_ARGS) == 0
    written = (lessons_dir / gen.NOTES_FILENAME).read_bytes().decode("utf-8")
    assert written.startswith(edited) and written.endswith(COMPANION_LEGACY)


def _seed_logs_like_the_bootstrap(lessons_dir, index_name: str) -> list:
    """Copy the shipped changelog and promotion-log seeds to the names the
    bootstrap gives them for `index_name`, byte for byte, as it does."""
    pairs = list(zip(lessons_bootstrap._LESSONS_SEED_SRC_NAMES,
                     lessons_bootstrap._lessons_seed_dst_names(index_name)))[1:]
    for src, dst in pairs:
        (lessons_dir / dst).write_bytes((SEED_DIR / src).read_bytes())
    return [lessons_dir / dst for _src, dst in pairs]


PROMO_WITH_A_HUB_SIDE_ROW = (
    "## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File |\n"
    "|------|-----------|-----------------|------|\n"
    "| 2024-01-02 | LL-003 | a rule | [rule.md](rule.md) |\n"
    "| 2024-01-03 | LL-201 | a later rule | [later.md](later.md) |\n\n---\n"
)


@pytest.mark.parametrize("index_name", ["00-Index-LessonsLearned.md", CUSTOM_INDEX])
def test_bootstrap_seeded_logs_are_header_only_and_never_refuse(tmp_path, index_name):
    config, index_path, lessons_dir = _build(tmp_path, promo=False, index_name=index_name)
    index_path.write_bytes(index_path.read_bytes() + PROMO_WITH_A_HUB_SIDE_ROW.encode("utf-8"))
    changelog, hub_log = _seed_logs_like_the_bootstrap(lessons_dir, index_name)
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert (report["changelog"], report["promotion_log"]) == ("header-only", "header-only")
    assert report["would_refuse"] == [] and report["ready_with_all_repairs"] is True
    _plan(config, index_path, mig.RepairOptions.all_on())  # no refusal
    assert _run(config, *_WRITE_ARGS) == 0
    assert "LL-201" in hub_log.read_text(encoding="utf-8")
    assert "## Entry 1" in changelog.read_text(encoding="utf-8")


def test_report_promotion_log_not_missing_on_a_migrated_tree(tmp_path):
    """Regression: the key used to look only for a hub-level
    `00-PromotionLog-...` file, so a migrated tree whose rows relocated to
    `Archive/PromotionLog-LessonsLearned-001-050.md` (ids 1-3 here) still
    read "missing"."""
    config, _index_path, lessons_dir = _build(tmp_path)  # promo=True by default: embeds rows for LL-001..003
    assert _run(config, *_WRITE_ARGS) == 0
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert report["promotion_log"] != "missing"
    assert (lessons_dir / "Archive" / "PromotionLog-LessonsLearned-001-050.md").is_file()


def test_report_promotion_log_missing_with_no_log_files_at_all(tmp_path):
    config, _index_path, _lessons_dir = _build(tmp_path, promo=False)
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert report["promotion_log"] == "missing"


PROMO_WITH_THE_COUNTER = (
    "## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File |\n"
    "|------|-----------|-----------------|------|\n"
    "| 2024-01-02 | LL-003 | a rule | [rule.md](rule.md) |\n\n"
    "**Next available ID:** LL-004\n<!-- Drift record: the counter read LL-002 once. -->\n\n---\n"
)


def test_counter_inside_the_promotion_log_section_travels_once(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, reworded_quickref=False, promo=False)
    text = index_path.read_bytes().decode("utf-8").replace("**Next available ID:** LL-004\n\n", "", 1)
    index_path.write_bytes((text + PROMO_WITH_THE_COUNTER).encode("utf-8"))
    plan = _plan(config, index_path, mig.RepairOptions(backfill_frontmatter=True))  # no --relocate-prose
    assert all(heading != "Rule Promotion Log" for heading, _body in plan["relocate_sections"])
    assert _run(config, *_WRITE_ARGS) == 0
    texts = [p.read_bytes().decode("utf-8") for p in lessons_dir.rglob("*.md")]
    assert sum(t.count("Drift record") for t in texts) == 1  # header history, relocated once
    assert sum(t.count("**Next available ID:**") for t in texts) == 1  # the generated hub's own counter


# ---------------------------------------------------------------------------
# `build_report` must survive a changelog or promotion-log file that is not
# valid UTF-8: a clean, specific refusal in the relevant field, never the
# opaque `error` fallback `_safe_report` produces for an unhandled exception,
# which discards every other field the report would otherwise carry.
# ---------------------------------------------------------------------------

def test_report_survives_an_undecodable_changelog_file(tmp_path):
    config, _index_path, lessons_dir = _build(tmp_path)
    assert _run(config, *_WRITE_ARGS) == 0
    changelog_path = lessons_dir / "00-Changelog-LessonsLearned.md"
    changelog_path.write_bytes(b"\xff\xfe not valid UTF-8 bytes\n")
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert "error" not in report
    assert report["changelog"] == "unreadable"
    # Matches lessons_changelog.py --split's own refusal for the same input.
    assert report["changelog_resplit"] == "refused"
    assert any("not valid UTF-8" in item for item in report["would_refuse"])
    assert report["ready_with_all_repairs"] is False


def test_report_survives_an_undecodable_promotion_log_file(tmp_path):
    config, _index_path, lessons_dir = _build(tmp_path)  # promo=True by default: seeds LL-001..003 rows
    assert _run(config, *_WRITE_ARGS) == 0
    century_path = lessons_dir / "Archive" / "PromotionLog-LessonsLearned-001-050.md"
    assert century_path.is_file()
    century_path.write_bytes(b"\xff\xfe not valid UTF-8 bytes\n")
    report = json.loads(_capture_json(config, "--report", "--json"))
    assert "error" not in report
    assert report["promotion_log"] == "unreadable"
    assert any("not valid UTF-8" in item for item in report["would_refuse"])
    assert report["ready_with_all_repairs"] is False


# ---------------------------------------------------------------------------
# The migrated hub's `Parts:` line names the century files on disk, and a
# resumed run overwrites a zero-row hub but never one that holds a row.
# One test per cell of the interaction matrix:
#
#   existing state                         | migrating rows     | outcome
#   ---------------------------------------+--------------------+---------------------------
#   stray century file                     | century rows       | hub lists planned + stray
#   stray century file                     | hub-side rows only | hub lists the stray
#   stray century file                     | none               | no hub written, stray kept
#   zero-row hub with a Parts: line        | differs from plan  | overwritten
#   zero-row hub with a prose Parts: line  | differs from plan  | refused, bytes kept
#   hub holding one data row               | differs from plan  | refused, bytes kept
#   hub equal to the planned text          | any                | accepted (resume), no change
#   opener-only / seed hub                 | any                | accepted (existing tests)
# ---------------------------------------------------------------------------

HUB_LOG_NAME = "00-PromotionLog-LessonsLearned.md"
_PROMO_ONLY_HUB_SIDE = (
    "## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File |\n"
    "|------|-----------|-----------------|------|\n"
    "| 2024-01-03 | LL-201 | a later rule | [later.md](later.md) |\n\n---\n"
)


def _on_disk_archive_parts(lessons_dir) -> list:
    return sorted(f"Archive/{p.name}" for p in (lessons_dir / "Archive").glob("PromotionLog-*.md"))


def _hub_parts_hrefs(lessons_dir) -> list:
    text = (lessons_dir / HUB_LOG_NAME).read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.startswith("Parts:")]
    assert len(lines) == 1, f"expected exactly one Parts: line, got {lines!r}"
    return re.findall(r"\]\(([^)]*)\)", lines[0])


def _stray_part(lessons_dir, index_path, which: int) -> str:
    """Create a century file no migrating row routes to; return its hub-relative name."""
    name = sup.century_log_filenames(mig._index_naming(index_path))[which]
    (lessons_dir / name).write_bytes(
        f"[← {index_path.name}]({index_path.name})\n\n{sup._LOG_HEADER}\n{sup._LOG_SEP}\n".encode())
    return name


def test_hub_parts_line_lists_a_stray_century_file_with_no_migrating_row(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)  # LL-003 routes to the 001-050 part
    stray = _stray_part(lessons_dir, index_path, 1)
    before = (lessons_dir / stray).read_bytes()
    assert _run(config, *_WRITE_ARGS) == 0
    assert _hub_parts_hrefs(lessons_dir) == _on_disk_archive_parts(lessons_dir)
    assert stray in _hub_parts_hrefs(lessons_dir)
    assert (lessons_dir / stray).read_bytes() == before  # listed, never rewritten


def test_hub_parts_line_lists_a_stray_century_file_when_only_hub_side_rows_migrate(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, promo=False)
    index_path.write_bytes(index_path.read_bytes() + _PROMO_ONLY_HUB_SIDE.encode("utf-8"))
    stray = _stray_part(lessons_dir, index_path, 2)
    assert _run(config, *_WRITE_ARGS) == 0
    assert _hub_parts_hrefs(lessons_dir) == [stray] == _on_disk_archive_parts(lessons_dir)
    assert "LL-201" in (lessons_dir / HUB_LOG_NAME).read_text(encoding="utf-8")


def test_a_stray_century_file_with_no_migrating_rows_at_all_writes_no_hub(tmp_path):
    """A hub is rendered only when the migration carries promotion-log rows. With none, there
    is nothing to overwrite and nothing to list, so no hub appears; the writer repairs a stale
    listing on its next append."""
    config, index_path, lessons_dir = _build(tmp_path, promo=False)
    stray = _stray_part(lessons_dir, index_path, 1)
    before = (lessons_dir / stray).read_bytes()
    assert _run(config, *_WRITE_ARGS) == 0
    assert not (lessons_dir / HUB_LOG_NAME).exists()
    assert (lessons_dir / stray).read_bytes() == before


def _zero_row_hub_listing(index_path, part_names: list, parts_line: str | None = None) -> bytes:
    listing = parts_line if parts_line is not None else "Parts: " + ", ".join(f"[{p}]({p})" for p in part_names)
    return (f"[← {index_path.name}]({index_path.name})\n{listing}\n\n"
            f"{sup._LOG_HEADER}\n{sup._LOG_SEP}\n").encode()


def test_resume_overwrites_a_zero_row_hub_that_carries_a_parts_line(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)  # planned hub lists the 001-050 part only
    other = sup.century_log_filenames(mig._index_naming(index_path))[1]
    hub = lessons_dir / HUB_LOG_NAME
    hub.write_bytes(_zero_row_hub_listing(index_path, [other]))  # differs from the planned hub
    _plan(config, index_path, mig.RepairOptions.all_on())  # no refusal
    assert _run(config, *_WRITE_ARGS) == 0
    assert _hub_parts_hrefs(lessons_dir) == _on_disk_archive_parts(lessons_dir)
    assert other not in _hub_parts_hrefs(lessons_dir)  # the century file never existed on disk


def test_resume_merges_a_hub_data_row_into_the_planned_log(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    part = sup.century_log_filenames(mig._index_naming(index_path))[1]
    hub = lessons_dir / HUB_LOG_NAME
    row = "| 2024-01-01 | LL-060 | a rule | [r](r.md) |"
    hub.write_bytes(_zero_row_hub_listing(index_path, [part]) + f"{row}\n".encode())
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["relocated"]["foreign_files"] == [HUB_LOG_NAME]
    assert _run(config, *_WRITE_ARGS) == 0
    assert row in (lessons_dir / part).read_bytes().decode("utf-8")  # the row is in the structured log
    assert row not in (lessons_dir / "00-Changelog-LessonsLearned.md").read_bytes().decode("utf-8")
    assert _hub_parts_hrefs(lessons_dir) == _on_disk_archive_parts(lessons_dir) and part in _hub_parts_hrefs(lessons_dir)
    ledger = _ledger(lessons_dir)
    assert ledger["promotion_log"]["rows"] == 2 and ledger["unaccounted"] == 0


def test_resume_folds_in_a_zero_row_hub_whose_line_is_prose_not_a_parts_listing(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    hub = lessons_dir / HUB_LOG_NAME
    hub.write_bytes(_zero_row_hub_listing(index_path, [], parts_line="Parts: see the archive folder"))
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["relocated"]["foreign_files"] == [HUB_LOG_NAME]
    assert _run(config, *_WRITE_ARGS) == 0
    assert "Parts: see the archive folder" in (lessons_dir / "00-Changelog-LessonsLearned.md").read_bytes().decode("utf-8")
    assert "see the archive folder" not in hub.read_bytes().decode("utf-8")


def test_resume_accepts_a_hub_equal_to_the_planned_text(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    planned = {path.name: text for path, text in plan["outputs"]}
    hub = lessons_dir / HUB_LOG_NAME
    hub.write_bytes(planned[HUB_LOG_NAME].encode("utf-8"))
    _plan(config, index_path, mig.RepairOptions.all_on())  # no refusal: a resumed run's own output
    assert _run(config, *_WRITE_ARGS) == 0
    assert _hub_parts_hrefs(lessons_dir) == _on_disk_archive_parts(lessons_dir)


def test_resume_keeps_a_hub_row_beside_hand_prose_that_cannot_parse(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    part = sup.century_log_filenames(mig._index_naming(index_path))[1]
    row = "| 2024-01-01 | LL-060 | a rule | [r](r.md) |"
    hub_text = _zero_row_hub_listing(index_path, [part]) + f"HAND-PROSE kept by hand.\n{row}\n".encode()
    (lessons_dir / HUB_LOG_NAME).write_bytes(hub_text)
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = (lessons_dir / CHANGELOG_NAME).read_bytes().decode("utf-8")
    assert row in (lessons_dir / part).read_bytes().decode("utf-8") and row not in changelog
    assert changelog.count("HAND-PROSE kept by hand.") == 1
    assert _ledger(lessons_dir)["unaccounted"] == 0


# ---------------------------------------------------------------------------
# Review fixes: a resumed run recognises its own folds, relocation spans stay
# inside their section, folds are byte-exact, foreign files keep a copy, and
# each relocated unit is counted once.
# ---------------------------------------------------------------------------

CHANGELOG_NAME = "00-Changelog-LessonsLearned.md"
HUB_MARKER_TEXT = "# My promotion notes\n\nHUB-MARKER kept by hand.\n"
CL_MARKER_TEXT = "# Own changelog\n\nCL-MARKER history.\n"


def _crash_then_replan(config, index_path):
    """A `--write` whose generator step raises, then the plan a resume makes."""
    with patch("migrate_lessons_index.gen._cmd_write_lessons", side_effect=RuntimeError("boom")):
        assert _run(config, *_WRITE_ARGS) == 1
    return _plan(config, index_path, mig.RepairOptions.all_on())


def _changelog_text(lessons_dir) -> str:
    return (lessons_dir / CHANGELOG_NAME).read_bytes().decode("utf-8")


def test_resume_keeps_a_folded_foreign_hub(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    (lessons_dir / HUB_LOG_NAME).write_bytes(HUB_MARKER_TEXT.encode())
    plan = _crash_then_replan(config, index_path)
    assert plan["relocated"]["foreign_files"] == [HUB_LOG_NAME]
    planned = {path.name: text for path, text in plan["outputs"]}
    assert planned[CHANGELOG_NAME] == _changelog_text(lessons_dir)  # the resume re-plans what is on disk
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = _changelog_text(lessons_dir)
    assert changelog.count("HUB-MARKER") == 1 and "Pre-migration changelog file" not in changelog
    assert changelog.count("Relocated hand-written index sections") == 1
    ledger = _ledger(lessons_dir)
    assert ledger["relocated"]["foreign_files"] == [HUB_LOG_NAME] and ledger["unaccounted"] == 0


def test_resume_keeps_both_a_folded_foreign_hub_and_a_folded_foreign_changelog(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    (lessons_dir / HUB_LOG_NAME).write_bytes(HUB_MARKER_TEXT.encode())
    (lessons_dir / CHANGELOG_NAME).write_bytes(CL_MARKER_TEXT.encode())
    plan = _crash_then_replan(config, index_path)
    assert sorted(plan["relocated"]["foreign_files"]) == sorted([HUB_LOG_NAME, CHANGELOG_NAME])
    planned = {path.name: text for path, text in plan["outputs"]}
    assert planned[CHANGELOG_NAME] == _changelog_text(lessons_dir)
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = _changelog_text(lessons_dir)
    assert changelog.count("HUB-MARKER") == 1 and changelog.count("CL-MARKER") == 1
    assert changelog.count("Pre-migration changelog file") == 1
    assert changelog.count("Relocated hand-written index sections") == 1
    assert _ledger(lessons_dir)["unaccounted"] == 0


_LOG_HEADER_LINE = "| Date | Lesson ID | Artifact Created | File |\n"
_LOG_ROW = "| 2024-01-02 | LL-003 | a rule | [rule.md](rule.md) |\n"
_BAD_SEPARATOR = ("## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File (MY-HEADER) |\n"
                  "| not a separator |\n" + _LOG_ROW + "\n---\n")
_NO_SEPARATOR = ("## Rule Promotion Log\n\n| Date | Lesson ID | Artifact Created | File (MY-HEADER) |\n"
                 + _LOG_ROW + "\n---\n")


def _build_with_log(tmp_path, log_text):
    config, index_path, lessons_dir = _build(tmp_path, promo=False)
    index_path.write_bytes(index_path.read_bytes() + log_text.encode("utf-8"))
    return config, index_path, lessons_dir


@pytest.mark.parametrize("log_text", [_BAD_SEPARATOR, _NO_SEPARATOR], ids=["bad-separator", "no-separator"])
def test_recognised_header_without_its_separator_relocates_with_its_table(tmp_path, log_text):
    config, _index_path, lessons_dir = _build_with_log(tmp_path, log_text)
    assert _run(config, *_WRITE_ARGS) == 0
    assert "MY-HEADER" in "".join(p.read_text(encoding="utf-8") for p in lessons_dir.rglob("*.md"))
    table = log_text.split("\n\n")[1] + "\n"
    assert table in _changelog_text(lessons_dir)  # header line, then the table it heads, unbroken
    assert _ledger(lessons_dir)["unaccounted"] == 0


def test_refused_row_span_stays_inside_the_promotion_log_section(tmp_path):
    five_cells = "| 2024-01-02 | LL-003 | a rule | [rule.md](rule.md) | extra |\n"
    log_text = "## Rule Promotion Log\n\n" + _LOG_HEADER_LINE + "|------|---|---|---|\n" + five_cells \
        + "## Extra Notes\nhand prose line\n"
    config, _index_path, lessons_dir = _build_with_log(tmp_path, log_text)
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = _changelog_text(lessons_dir)
    assert changelog.count("hand prose line") == 1 and "\n## Extra Notes\n" not in changelog
    assert f"### Rule Promotion Log\n{five_cells}" in changelog  # the row is the whole residue


def test_refused_row_span_does_not_copy_a_later_sections_counter_line(tmp_path):
    five_cells = "| 2024-01-02 | LL-003 | a rule | [rule.md](rule.md) | extra |\n"
    log_text = "## Rule Promotion Log\n\n" + _LOG_HEADER_LINE + "|------|---|---|---|\n" + five_cells \
        + "## Extra Notes\nhand prose line\n**Next available ID:** LL-004\n\n---\n"
    config, _index_path, lessons_dir = _build_with_log(tmp_path, log_text)
    assert _run(config, *_WRITE_ARGS) == 0
    changelog = _changelog_text(lessons_dir)
    assert changelog.count("Next available ID") == 1  # once, inside its own section
    assert f"### Rule Promotion Log\n{five_cells}### Extra Notes\n" in changelog  # the row alone is the residue


_FOLD_BYTES = {
    "crlf": b"# Mine\r\n\r\nline one\r\nline two\r\n",
    "bom": b"\xef\xbb\xbf# Mine\n\nbody\n",
    "no-trailing-newline": b"# Mine\n\nbody without newline",
    "fences": b"# Mine\n\n```\ncode\n```\n\n````md\n```inner```\n````\n## Entry 9\n",
    "blank-edges": b"\n\n# Mine\n\nbody\n\n\n",
    "lone-cr": b"# Mine\n\nA\rB\n",
    "mixed": b"# Mine\r\nlf line\nend\r\n",
    "trailing-space": b"# Mine\n\nbody   \n   \n",
}


@pytest.mark.parametrize("crlf_index", [False, True], ids=["lf-index", "crlf-index"])
@pytest.mark.parametrize("raw", list(_FOLD_BYTES.values()), ids=list(_FOLD_BYTES))
def test_foreign_changelog_fold_is_byte_exact(tmp_path, raw, crlf_index):
    config, index_path, lessons_dir = _build(tmp_path, crlf=crlf_index)
    (lessons_dir / CHANGELOG_NAME).write_bytes(raw)
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["folds"] == [raw.decode("utf-8")]
    assert _run(config, *_WRITE_ARGS) == 0
    nl = b"\r\n" if crlf_index else b"\n"
    data = (lessons_dir / CHANGELOG_NAME).read_bytes()
    assert nl + raw + nl in data  # only the wrapper lines the migrator adds use the index newline
    assert _ledger(lessons_dir)["verification"]["verified"] is True


@pytest.mark.parametrize("crlf_index", [False, True], ids=["lf-index", "crlf-index"])
def test_foreign_hub_fold_is_byte_exact(tmp_path, crlf_index):
    config, _index_path, lessons_dir = _build(tmp_path, crlf=crlf_index)
    raw = b"\xef\xbb\xbf# Mine\r\nHUB-MARKER\nend\r\n\r\n"
    (lessons_dir / HUB_LOG_NAME).write_bytes(raw)
    assert _run(config, *_WRITE_ARGS) == 0
    nl = b"\r\n" if crlf_index else b"\n"
    assert nl + raw + nl in (lessons_dir / CHANGELOG_NAME).read_bytes()


def test_verify_written_checks_the_exact_fold_bytes(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, crlf=True)
    (lessons_dir / CHANGELOG_NAME).write_bytes(_FOLD_BYTES["mixed"])
    text = mig.read_text(index_path)  # newlines kept: `_plan` reads text mode and would plan LF
    plan = mig.plan_migration(config, index_path, text, sup.classify_shape(text)[1], mig.RepairOptions.all_on())
    assert _run(config, *_WRITE_ARGS) == 0
    assert mig.verify_written(plan) == []
    path = lessons_dir / CHANGELOG_NAME
    path.write_bytes(path.read_bytes().replace(b"# Mine\r\nlf line\nend\r\n", b"# Mine\r\nlf line\r\nend\r\n"))
    assert any("folded foreign file" in miss for miss in mig.verify_written(plan))


def test_standalone_write_keeps_a_recoverable_copy_of_every_foreign_file(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, companion=False)
    foreign = {HUB_LOG_NAME: HUB_MARKER_TEXT.encode(), CHANGELOG_NAME: CL_MARKER_TEXT.encode(),
               gen.NOTES_FILENAME: b"other notes\n"}
    for name, data in foreign.items():
        (lessons_dir / name).write_bytes(data)
    (lessons_dir / gen.COMPANION_FILENAME).write_bytes(COMPANION_FOREIGN.encode())
    _crash_then_replan(config, index_path)
    copies = {name: lessons_dir / (name + mig.relocate.COPY_SUFFIX) for name in foreign}
    assert {name: path.read_bytes() for name, path in copies.items()} == foreign
    assert _run(config, *_WRITE_ARGS) == 0  # the resume must not replace a copy with the migrator's own output
    assert {name: path.read_bytes() for name, path in copies.items()} == foreign


def test_standalone_write_announces_each_new_copy_once_and_lists_all_in_the_ledger(tmp_path, capsys):
    config, index_path, lessons_dir = _build(tmp_path)
    (lessons_dir / HUB_LOG_NAME).write_bytes(HUB_MARKER_TEXT.encode())
    (lessons_dir / CHANGELOG_NAME).write_bytes(CL_MARKER_TEXT.encode())
    capsys.readouterr()
    _crash_then_replan(config, index_path)
    first = capsys.readouterr().out.splitlines()
    copies = {name: lessons_dir / (name + mig.relocate.COPY_SUFFIX) for name in (HUB_LOG_NAME, CHANGELOG_NAME)}
    for name, copy in copies.items():
        assert f"BACKUP: {lessons_dir / name} kept as {copy}" in first
    assert len([ln for ln in first if ln.startswith("BACKUP: ")]) == 2
    assert _run(config, *_WRITE_ARGS) == 0
    assert not [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("BACKUP: ")]  # kept from an earlier run: silent
    assert sorted(_ledger(lessons_dir)["relocated"]["backups"]) == sorted(str(p) for p in copies.values())


def test_a_standalone_write_with_nothing_foreign_writes_no_copy(tmp_path):
    config, _index_path, lessons_dir = _build(tmp_path)
    assert _run(config, *_WRITE_ARGS) == 0
    assert list(lessons_dir.rglob("*" + mig.relocate.COPY_SUFFIX)) == []


def test_resume_recovers_a_hub_fold_that_rotated_into_an_archive_part(tmp_path):
    """A foreign changelog larger than the read budget folds in as the newest
    entry and stays whole in the main file, so the relocated entry carrying
    the hub fold lands in an archive part before the generator step crashes."""
    config, index_path, lessons_dir = _build(tmp_path)
    (lessons_dir / HUB_LOG_NAME).write_bytes(HUB_MARKER_TEXT.encode())
    filler = ("Lorem ipsum filler text describing a fixture entry body in full. " * 15 + "\n") * 120
    (lessons_dir / CHANGELOG_NAME).write_bytes((CL_MARKER_TEXT + filler).encode())
    plan = _crash_then_replan(config, index_path)
    parts = [p for p in lessons_dir.glob("00-Changelog-LessonsLearned-*.md")]
    assert parts and "HUB-MARKER" in "".join(p.read_text(encoding="utf-8") for p in parts)
    assert "HUB-MARKER" not in _changelog_text(lessons_dir)  # the main file holds only the newest entry
    assert {p.name: t for p, t in plan["outputs"]}[parts[0].name] == parts[0].read_bytes().decode("utf-8")
    assert _run(config, *_WRITE_ARGS) == 0
    family = "".join(p.read_text(encoding="utf-8") for p in [lessons_dir / CHANGELOG_NAME, *parts])
    assert family.count("HUB-MARKER") == 1 and family.count("CL-MARKER") == 1
    assert family.count("Pre-migration changelog file") == 1
    assert _ledger(lessons_dir)["unaccounted"] == 0


def test_resume_keeps_a_hub_row_and_hand_prose_once_each(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path)
    part = sup.century_log_filenames(mig._index_naming(index_path))[1]
    row = "| 2024-01-01 | LL-060 | a rule | [r](r.md) |"
    hub_text = _zero_row_hub_listing(index_path, [part]) + f"HAND-PROSE kept by hand.\n{row}\n".encode()
    (lessons_dir / HUB_LOG_NAME).write_bytes(hub_text)
    plan = _crash_then_replan(config, index_path)
    assert {p.name: t for p, t in plan["outputs"]}[CHANGELOG_NAME] == _changelog_text(lessons_dir)
    assert _run(config, *_WRITE_ARGS) == 0
    assert (lessons_dir / part).read_bytes().decode("utf-8").count(row) == 1
    changelog = _changelog_text(lessons_dir)
    assert changelog.count("HAND-PROSE kept by hand.") == 1 and row not in changelog
    assert _ledger(lessons_dir)["unaccounted"] == 0


def test_each_relocated_unit_is_counted_in_one_bucket(tmp_path):
    config, index_path, lessons_dir = _build(tmp_path, drop_lesson="LL-002-PROC-Two.md")
    plan = _plan(config, index_path, mig.RepairOptions.all_on())
    assert plan["prose_relocated"] == ["Quick Reference"] and plan["relocated"]["rows"] == 1
    assert "prose: 1 dropped, 1 relocated" in mig.format_report(plan)
    assert _run(config, *_WRITE_ARGS) == 0
    ledger = _ledger(lessons_dir)
    assert ledger["prose"]["relocate"] == ["Quick Reference"] and ledger["relocated"]["rows"] == 1
