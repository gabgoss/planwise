#!/usr/bin/env python3
"""Tests for `generate_plans_index`: render, check, write and the CLI.

Each test builds a temp planwise tree (config.yaml, a Plans directory and
Master Plan files) under `tmp_path`, loads it through `--config` injected into
`sys.argv`, and drives `main()`. None reads or writes the live project.

Every guard carries a producing test (the input the guard exists for) and a
non-producing test (a near-miss the guard must let through).

Run with:  python -m pytest tests/test_generate_plans_index.py -q
"""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import generate_plans_index as gpi
from generate_backlog_index import _measure

LEGACY_INDEX = (
    "# Plans Index\n\n"
    "<!-- hand-written note -->\n"
    "<!-- second note -->\n\n"
    "| Abbrev | Name | Status | Created | Last Updated | Path |\n"
    "|--------|------|--------|---------|--------------|------|\n"
    "| ALP | Alpha | COMPLETE | 2026-01-01 | 2026-02-01 | Alpha/ |\n\n"
    "## Notes\n\n"
    "hand written prose\n"
)

PUBLIC_API = [
    "PLAN_STATUS_MEANINGS",
    "CheckResult",
    "PlansRender",
    "RenderedRow",
    "RowFindings",
    "check_plans_index",
    "WriteResult",
    "diff_index_rows",
    "index_matches_render",
    "is_generated_plans_index_file",
    "main",
    "plans_index_path",
    "render_plans_index",
    "write_plans_index",
]


def make_tree(tmp_path: Path, extra_yaml: str = "") -> Path:
    """Create `planwise/config.yaml` and an empty `planwise/Plans`. Return the config path."""
    planwise = tmp_path / "planwise"
    (planwise / "Plans").mkdir(parents=True)
    config_path = planwise / "config.yaml"
    config_path.write_text(
        'project:\n  name: "PlansIndexFixture"\n  plans_dir: "Plans"\n' + extra_yaml, encoding="utf-8"
    )
    return config_path


def plans_dir_of(config_path: Path) -> Path:
    return config_path.parent / "Plans"


def index_of(config_path: Path) -> Path:
    return plans_dir_of(config_path) / "00-Index-Plans.md"


def write_master_plan(
    config_path: Path,
    folder: str,
    abbrev: str,
    status: str | None = "COMPLETE",
    created: str | None = "2026-01-01",
    updated: str | None = "2026-02-01",
    filename: str | None = None,
) -> Path:
    """Write one Master Plan. A `None` argument omits that line from the file."""
    directory = plans_dir_of(config_path) / folder
    directory.mkdir(parents=True, exist_ok=True)
    lines = [f"# {abbrev} Master Plan", ""]
    if status is not None:
        lines.append(f"**Status:** {status}")
    if created is not None:
        lines.append(f"**Created:** {created}")
    lines.extend(["", "Body text.", ""])
    if updated is not None:
        lines.append(f"*Last Updated: {updated}*")
    path = directory / (filename or f"{abbrev}-Master-Plan.md")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load(config_path: Path) -> dict:
    return config_loader.load_config(config_path=config_path)


@pytest.fixture
def cli(monkeypatch, capsys):
    """Run `main()` with the given argv tail and return (exit code, stdout, stderr)."""

    def run(config_path: Path, *flags: str):
        monkeypatch.setattr(sys, "argv", ["generate_plans_index", "--config", str(config_path), *flags])
        code = gpi.main()
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


@pytest.fixture
def two_plans(tmp_path):
    config_path = make_tree(tmp_path)
    write_master_plan(config_path, "Alpha", "ALP", created="2026-01-01")
    write_master_plan(config_path, "Beta", "BET", status="IN_PROGRESS", created="2026-02-01")
    return config_path


def finding_classes(items: list) -> list:
    return [item["class"] for item in items]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


class TestRender:
    def test_render_has_six_columns_one_row_per_master_plan_and_the_generated_line(self, two_plans):
        render = gpi.render_plans_index(load(two_plans))
        lines = render.text.split("\n")
        assert lines[0] == "# Plans Index"
        assert lines[2].startswith("Generated: ")
        assert "| Abbrev | Name | Status | Created | Last Updated | Path |" in lines
        assert "| ALP | Alpha | COMPLETE | 2026-01-01 | 2026-02-01 | Alpha/ |" in lines
        assert "| BET | Beta | IN_PROGRESS | 2026-02-01 | 2026-02-01 | Beta/ |" in lines
        assert [row.abbrev for row in render.rows] == ["ALP", "BET"]
        assert render.anomalies == [] and render.warnings == []

    def test_render_writes_nothing(self, two_plans):
        gpi.render_plans_index(load(two_plans))
        assert not index_of(two_plans).exists()

    def test_rows_sort_by_created_then_path_with_missing_created_last(self, tmp_path):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Zeta", "ZET", created="2026-01-01")
        write_master_plan(config_path, "Beta", "BET", created="2026-03-01")
        write_master_plan(config_path, "Alpha", "ALP", created="2026-03-01")
        write_master_plan(config_path, "Mid", "MID", created=None)
        paths = [row.path for row in gpi.render_plans_index(load(config_path)).rows]
        assert paths == ["Zeta/", "Alpha/", "Beta/", "Mid/"]

    def test_a_missing_created_warns_and_does_not_fail_the_exit(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Mid", "MID", created=None)
        code, _, _ = cli(config_path, "--write")
        assert code == 0
        render = gpi.render_plans_index(load(config_path))
        assert finding_classes(render.warnings) == ["missing-field"]
        assert render.warnings[0]["field"] == "created" and "Mid/MID-Master-Plan.md" in render.warnings[0]["message"]
        assert "| MID | Mid | COMPLETE | - | 2026-02-01 | Mid/ |" in render.text
        code, _, _ = cli(config_path, "--check")
        assert code == 0

    def test_a_missing_last_updated_warns_with_its_own_field(self, tmp_path):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Mid", "MID", updated=None)
        render = gpi.render_plans_index(load(config_path))
        assert [w["field"] for w in render.warnings] == ["last_updated"]

    def test_every_cell_passes_through_the_escape(self):
        row = gpi.RenderedRow("A|B", "N|M", "COMPLETE", "-", "-", "P/", "P/A-Master-Plan.md")
        assert row.line() == r"| A\|B | N\|M | COMPLETE | - | - | P/ |"

    def test_depth_four_master_plan_never_renders_and_no_path_starts_with_plans(self, two_plans):
        deep = plans_dir_of(two_plans) / "Alpha" / "Meta-X" / "Deep" / "Nested"
        deep.mkdir(parents=True)
        (deep / "ZZZ-Master-Plan.md").write_text("**Status:** COMPLETE\n", encoding="utf-8")
        sprint = plans_dir_of(two_plans) / "Alpha" / "Sprint-01"
        sprint.mkdir()
        (sprint / "SPR-Master-Plan.md").write_text("**Status:** COMPLETE\n", encoding="utf-8")
        render = gpi.render_plans_index(load(two_plans))
        assert [row.abbrev for row in render.rows] == ["ALP", "BET"]
        assert not any(row.path.startswith("Plans/") for row in render.rows)
        assert "ZZZ" not in render.text and "SPR" not in render.text

    def test_a_meta_folder_renders_with_its_suffix_in_the_name_and_path(self, tmp_path):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Gamma/Meta-Discovery", "GAM", filename="GAM-META-Master-Plan.md")
        row = gpi.render_plans_index(load(config_path)).rows[0]
        assert (row.abbrev, row.name, row.path) == ("GAM", "Gamma (Meta / Discovery)", "Gamma/Meta-Discovery/")


class TestEmptyPlansDir:
    def test_write_renders_header_empty_table_and_full_legend_and_exits_zero(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        code, _, _ = cli(config_path, "--write")
        assert code == 0
        text = index_of(config_path).read_text(encoding="utf-8")
        lines = text.split("\n")
        assert lines[0] == "# Plans Index"
        assert lines[2].startswith("Generated: ")
        separator = lines.index("|--------|------|--------|---------|--------------|------|")
        assert lines[separator + 1] == "" and lines[separator + 2] == "## Status Legend"
        # Lines opening `| `: the table header, the legend header and one legend row per status.
        # The two separator rows open `|-`, and the empty table has no data row.
        assert text.count("\n| ") == 1 + 1 + len(config_loader.DEFAULT_PLAN_STATUSES)
        for status in config_loader.DEFAULT_PLAN_STATUSES:
            assert f"| {status} | " in text

    def test_the_empty_render_reads_back_as_the_generated_shape_and_checks_clean(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        cli(config_path, "--write")
        code, out, _ = cli(config_path, "--check")
        assert code == 0, out


# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------


class TestLegend:
    def test_every_default_value_appears_with_its_meaning(self, tmp_path):
        config_path = make_tree(tmp_path)
        text = gpi.render_plans_index(load(config_path)).text
        for status in config_loader.DEFAULT_PLAN_STATUSES:
            meaning = gpi.PLAN_STATUS_MEANINGS[status]
            assert meaning != gpi.PROJECT_DEFINED
            assert f"| {status} | {meaning} |" in text

    def test_a_configured_extra_value_renders_project_defined(self, tmp_path):
        extra = "plan_statuses:\n  - NOT_STARTED\n  - ON_HOLD\n  - COMPLETE\n"
        config_path = make_tree(tmp_path, extra)
        text = gpi.render_plans_index(load(config_path)).text
        assert "| ON_HOLD | (project-defined) |" in text
        assert "| NOT_STARTED | Plan created but no work begun |" in text
        assert "| IN_PROGRESS |" not in text

    def test_the_legend_follows_config_order(self, tmp_path):
        extra = "plan_statuses:\n  - COMPLETE\n  - NOT_STARTED\n"
        text = gpi.render_plans_index(load(make_tree(tmp_path, extra))).text
        assert text.index("| COMPLETE |") < text.index("| NOT_STARTED |")

    def test_a_pipe_in_a_configured_status_is_escaped_in_the_legend(self, tmp_path):
        config_path = make_tree(tmp_path, 'plan_statuses:\n  - "A|B"\n')
        assert r"| A\|B | (project-defined) |" in gpi.render_plans_index(load(config_path)).text


# ---------------------------------------------------------------------------
# Status anomalies
# ---------------------------------------------------------------------------


class TestStatusAnomalies:
    def test_unknown_status_renders_as_is_writes_and_exits_one(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="DONE")
        code, _, _ = cli(config_path, "--write")
        assert code == 1
        assert "| ALP | Alpha | DONE | 2026-01-01 | 2026-02-01 | Alpha/ |" in index_of(config_path).read_text(encoding="utf-8")

    def test_check_names_the_file_and_the_raw_line(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="DONE")
        cli(config_path, "--write")
        code, out, _ = cli(config_path, "--check")
        assert code == 1
        assert "unknown-status" in out and "Alpha/ALP-Master-Plan.md" in out and "'DONE'" in out

    def test_a_narrative_status_that_normalizes_to_a_known_token_is_clean(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="✅ **COMPLETE (2026-08-12) — shipped")
        code, _, _ = cli(config_path, "--write")
        assert code == 0
        assert "| ALP | Alpha | COMPLETE |" in index_of(config_path).read_text(encoding="utf-8")

    def test_title_case_status_has_no_token_so_it_renders_the_first_word_as_unknown(self, tmp_path):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="Complete")
        render = gpi.render_plans_index(load(config_path))
        assert render.rows[0].status == "Complete"
        assert finding_classes(render.anomalies) == ["unknown-status"]

    def test_a_tokenless_status_strips_emphasis_from_the_first_word(self, tmp_path):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="_paused_ until further notice")
        render = gpi.render_plans_index(load(config_path))
        assert render.rows[0].status == "paused"
        assert finding_classes(render.anomalies) == ["unknown-status"]

    def test_a_tokenless_status_keeps_its_interior_underscores(self, tmp_path):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="in_progress")
        render = gpi.render_plans_index(load(config_path))
        assert render.rows[0].status == "in_progress"
        assert finding_classes(render.anomalies) == ["unknown-status"]
        assert render.anomalies[0]["status"] == "in_progress"

    def test_a_configured_status_with_underscore_and_digit_round_trips(self, tmp_path):
        config_path = make_tree(tmp_path, "plan_statuses:\n  - ON_HOLD2\n")
        write_master_plan(config_path, "Alpha", "ALP", status="ON_HOLD2")
        render = gpi.render_plans_index(load(config_path))
        assert render.rows[0].status == "ON_HOLD2"
        assert render.anomalies == []

    def test_a_missing_status_line_renders_a_dash_and_exits_one(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status=None)
        render = gpi.render_plans_index(load(config_path))
        assert render.rows[0].status == "-"
        assert finding_classes(render.anomalies) == ["missing-status"]
        code, _, _ = cli(config_path, "--write")
        assert code == 1
        assert "| ALP | Alpha | - |" in index_of(config_path).read_text(encoding="utf-8")

    def test_an_undecodable_master_plan_is_unreadable_and_exits_one(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        broken = write_master_plan(config_path, "Beta", "BET")
        broken.write_bytes(b"# BET Master Plan\n\n**Status:** \xff\xfe COMPLETE\n")
        render = gpi.render_plans_index(load(config_path))
        assert finding_classes(render.anomalies) == ["unreadable-file"]
        assert "Beta/BET-Master-Plan.md" in render.anomalies[0]["message"]
        assert render.rows[0].cells == ("BET", "Beta", "-", "-", "-", "Beta/")
        code, _, _ = cli(config_path, "--write")
        assert code == 1
        assert "| BET | Beta | - | - | - | Beta/ |" in index_of(config_path).read_text(encoding="utf-8")
        code, out, _ = cli(config_path, "--check")
        assert code == 1
        assert "unreadable-file" in out and "cannot read the Master Plan" in out

    def test_a_configured_status_outside_the_default_set_is_known(self, tmp_path):
        config_path = make_tree(tmp_path, "plan_statuses:\n  - DONE\n")
        write_master_plan(config_path, "Alpha", "ALP", status="DONE")
        assert gpi.render_plans_index(load(config_path)).anomalies == []


class TestDuplicateRows:
    def test_two_master_plans_in_one_directory_render_both_rows_and_exit_one(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP")
        write_master_plan(config_path, "Alpha", "ALT", filename="ALT-Master-Plan.md")
        render = gpi.render_plans_index(load(config_path))
        assert [row.abbrev for row in render.rows] == ["ALP", "ALT"]
        assert finding_classes(render.anomalies) == ["duplicate-row"]
        message = render.anomalies[0]["message"]
        assert "Alpha/" in message and "Alpha/ALP-Master-Plan.md" in message and "Alpha/ALT-Master-Plan.md" in message
        code, _, _ = cli(config_path, "--write")
        assert code == 1

    def test_distinct_paths_raise_no_duplicate(self, two_plans):
        assert gpi.render_plans_index(load(two_plans)).anomalies == []

    def test_a_repeated_path_row_on_disk_is_named_with_both_line_numbers(self, two_plans, cli):
        cli(two_plans, "--write")
        text = index_of(two_plans).read_text(encoding="utf-8").split("\n")
        alpha_line = next(i for i, line in enumerate(text) if line.startswith("| ALP |"))
        text.insert(alpha_line + 1, text[alpha_line])
        index_of(two_plans).write_text("\n".join(text), encoding="utf-8")
        code, out, _ = cli(two_plans, "--check")
        assert code == 1
        duplicate = [f for f in gpi.check_plans_index(load(two_plans)).findings if f["class"] == "duplicate-row"]
        assert len(duplicate) == 1
        assert duplicate[0]["lines"] == [alpha_line + 1, alpha_line + 2]
        assert f"lines {alpha_line + 1}, {alpha_line + 2}" in out


# ---------------------------------------------------------------------------
# Write: idempotence, line endings
# ---------------------------------------------------------------------------


class TestWrite:
    def test_a_second_write_is_byte_identical_and_check_then_passes(self, two_plans, cli):
        assert cli(two_plans, "--write")[0] == 0
        first = index_of(two_plans).read_bytes()
        assert cli(two_plans, "--write")[0] == 0
        assert index_of(two_plans).read_bytes() == first
        assert cli(two_plans, "--check")[0] == 0

    def test_a_missing_index_is_written_with_lf(self, two_plans, cli):
        cli(two_plans, "--write")
        assert b"\r" not in index_of(two_plans).read_bytes()

    def test_an_existing_crlf_index_keeps_crlf_on_every_line(self, two_plans, cli):
        cli(two_plans, "--write")
        index_of(two_plans).write_bytes(index_of(two_plans).read_bytes().replace(b"\n", b"\r\n"))
        write_master_plan(two_plans, "Gamma", "GAM", created="2026-03-01")
        assert cli(two_plans, "--write")[0] == 0
        data = index_of(two_plans).read_bytes()
        assert data.count(b"\r\n") > 0
        assert data.count(b"\n") == data.count(b"\r\n")
        assert b"| GAM |" in data
        assert cli(two_plans, "--check")[0] == 0

    def test_dry_run_prints_the_render_and_writes_nothing(self, two_plans, cli):
        code, out, _ = cli(two_plans, "--dry-run")
        assert code == 0
        assert "| ALP | Alpha |" in out and "## Status Legend" in out
        assert not index_of(two_plans).exists()

    def test_no_mode_flag_defaults_to_dry_run(self, two_plans, cli):
        code, out, _ = cli(two_plans)
        assert code == 0 and "| ALP | Alpha |" in out
        assert not index_of(two_plans).exists()

    def test_dry_run_exits_one_on_an_anomaly(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="DONE")
        assert cli(config_path, "--dry-run")[0] == 1
        assert not index_of(config_path).exists()

    def test_a_failed_replace_leaves_the_prior_index_intact(self, two_plans, cli, monkeypatch):
        cli(two_plans, "--write")
        before = index_of(two_plans).read_bytes()
        write_master_plan(two_plans, "Alpha", "ALP", status="IN_PROGRESS")
        files_before = sorted(path.name for path in plans_dir_of(two_plans).rglob("*"))
        real_replace = os.replace
        calls = []

        def failing_replace(source, target):
            calls.append(target)
            if len(calls) == 1:
                raise OSError("simulated replace failure")
            return real_replace(source, target)

        monkeypatch.setattr(os, "replace", failing_replace)
        try:
            code = cli(two_plans, "--write")[0]
        except OSError:
            code = None

        assert calls, "the write never reached os.replace"
        assert code is None or code != 0
        assert index_of(two_plans).read_bytes() == before
        assert sorted(path.name for path in plans_dir_of(two_plans).rglob("*")) == files_before

    def test_write_plans_index_writes_and_prints_nothing(self, two_plans, capsys):
        result = gpi.write_plans_index(load(two_plans))
        assert (result.exit_code, result.written, result.refusal) == (0, True, None)
        assert result.render.rows and index_of(two_plans).read_text(encoding="utf-8") != ""
        assert capsys.readouterr() == ("", "")

    def test_write_plans_index_reports_an_anomaly_exit_after_writing(self, tmp_path):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="DONE")
        result = gpi.write_plans_index(load(config_path))
        assert (result.exit_code, result.written, result.refusal) == (1, True, None)
        assert index_of(config_path).exists()

    def test_write_plans_index_refuses_a_legacy_index_with_its_message_and_writes_nothing(self, two_plans, capsys):
        index_of(two_plans).write_bytes(LEGACY_INDEX.encode("utf-8"))
        result = gpi.write_plans_index(load(two_plans))
        assert (result.exit_code, result.written) == (2, False)
        assert "hand-authored plans index" in result.refusal and "--replace-legacy" in result.refusal
        assert index_of(two_plans).read_bytes() == LEGACY_INDEX.encode("utf-8")
        assert capsys.readouterr() == ("", "")

    def test_write_plans_index_replaces_a_legacy_index_on_request_and_offers_the_drop_listing(self, two_plans):
        index_of(two_plans).write_bytes(LEGACY_INDEX.encode("utf-8"))
        result = gpi.write_plans_index(load(two_plans), replace_legacy=True)
        assert (result.exit_code, result.written, result.refusal) == (0, True, None)
        assert "2 comment line(s)" in result.drop_listing and "## Notes" in result.drop_listing

    def test_write_plans_index_refuses_over_budget_with_its_message_and_writes_nothing(self, two_plans, monkeypatch):
        monkeypatch.setattr(gpi, "HUB_TOKEN_BUDGET", 10)
        result = gpi.write_plans_index(load(two_plans))
        assert (result.exit_code, result.written) == (2, False)
        assert "10-token budget" in result.refusal and "Nothing was written" in result.refusal
        assert not index_of(two_plans).exists()

    def test_index_matches_render_masks_the_generated_line_and_reads_crlf(self, two_plans):
        config = load(two_plans)
        gpi.write_plans_index(config)
        render = gpi.render_plans_index(config)
        disk = index_of(two_plans).read_text(encoding="utf-8")
        assert gpi.index_matches_render(disk, render)
        old = next(line for line in disk.split("\n") if line.startswith("Generated: "))
        assert gpi.index_matches_render(disk.replace(old, "Generated: 1999-01-01").replace("\n", "\r\n"), render)
        assert not gpi.index_matches_render(disk.replace("Alpha", "Alfa"), render)
        assert not gpi.index_matches_render("", render)


# ---------------------------------------------------------------------------
# Legacy guard
# ---------------------------------------------------------------------------


class TestLegacyGuard:
    def test_write_refuses_a_legacy_index_and_leaves_its_bytes(self, two_plans, cli):
        index_of(two_plans).write_bytes(LEGACY_INDEX.encode("utf-8"))
        code, _, err = cli(two_plans, "--write")
        assert code == 2
        assert index_of(two_plans).read_bytes() == LEGACY_INDEX.encode("utf-8")
        assert "/planwise upgrade" in err and "--replace-legacy" in err
        assert err.index("/planwise upgrade") < err.index("--replace-legacy")

    def test_write_replace_legacy_writes_and_lists_what_it_drops(self, two_plans, cli):
        index_of(two_plans).write_bytes(LEGACY_INDEX.encode("utf-8"))
        code, _, err = cli(two_plans, "--write", "--replace-legacy")
        assert code == 0
        assert "2 comment line(s)" in err and "## Notes" in err
        assert "## Status Legend" not in err
        text = index_of(two_plans).read_text(encoding="utf-8")
        assert "hand written prose" not in text and "Generated: " in text
        assert cli(two_plans, "--check")[0] == 0

    def test_replace_legacy_keeps_a_crlf_convention(self, two_plans, cli):
        index_of(two_plans).write_bytes(LEGACY_INDEX.replace("\n", "\r\n").encode("utf-8"))
        assert cli(two_plans, "--write", "--replace-legacy")[0] == 0
        data = index_of(two_plans).read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n") > 0

    def test_check_on_a_legacy_index_exits_two_naming_the_upgrade(self, two_plans, cli):
        index_of(two_plans).write_bytes(LEGACY_INDEX.encode("utf-8"))
        code, _, err = cli(two_plans, "--check")
        assert code == 2
        assert err.startswith("Error: ") and "is a hand-authored plans index" in err and "/planwise upgrade" in err

    def test_check_json_on_a_legacy_index_still_prints_the_shape_and_exits_two(self, two_plans, cli):
        index_of(two_plans).write_bytes(LEGACY_INDEX.encode("utf-8"))
        code, out, _ = cli(two_plans, "--check", "--json")
        assert code == 2
        payload = json.loads(out)
        assert payload["shape"] == "legacy" and finding_classes(payload["findings"]) == ["legacy-shape"]

    def test_a_generated_shape_index_is_not_refused(self, two_plans, cli):
        cli(two_plans, "--write")
        assert cli(two_plans, "--write")[0] == 0

    def test_an_unrecognized_file_without_a_table_is_not_legacy(self, two_plans, cli):
        index_of(two_plans).write_text("notes only\n", encoding="utf-8")
        assert cli(two_plans, "--write")[0] == 0


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


class TestBudget:
    def test_write_refuses_over_budget_naming_bytes_tokens_and_budget(self, two_plans, cli, monkeypatch):
        monkeypatch.setattr(gpi, "HUB_TOKEN_BUDGET", 10)
        render = gpi.render_plans_index(load(two_plans))
        code, _, err = cli(two_plans, "--write")
        assert code == 2
        assert not index_of(two_plans).exists()
        assert f"{render.num_bytes} bytes" in err and f"{render.tokens} tokens" in err and "10-token budget" in err

    def test_write_over_budget_leaves_an_existing_index_untouched(self, two_plans, cli, monkeypatch):
        cli(two_plans, "--write")
        before = index_of(two_plans).read_bytes()
        write_master_plan(two_plans, "Gamma", "GAM")
        monkeypatch.setattr(gpi, "HUB_TOKEN_BUDGET", 10)
        assert cli(two_plans, "--write")[0] == 2
        assert index_of(two_plans).read_bytes() == before

    def test_check_over_budget_exits_one_with_only_the_over_budget_finding(self, two_plans, cli, monkeypatch):
        cli(two_plans, "--write")
        monkeypatch.setattr(gpi, "HUB_TOKEN_BUDGET", 10)
        result = gpi.check_plans_index(load(two_plans))
        assert result.exit_code == 1
        assert finding_classes(result.findings) == ["over-budget"]
        assert cli(two_plans, "--check")[0] == 1

    def test_the_real_budget_passes_and_is_the_shared_constant_not_a_literal(self, two_plans, cli):
        from generate_backlog_index import HUB_TOKEN_BUDGET

        assert gpi.HUB_TOKEN_BUDGET == HUB_TOKEN_BUDGET == 12500
        assert cli(two_plans, "--write")[0] == 0
        assert cli(two_plans, "--check")[0] == 0

    def test_a_render_at_the_budget_writes_and_one_token_over_refuses(self, two_plans, cli, monkeypatch):
        tokens = gpi.render_plans_index(load(two_plans)).tokens
        monkeypatch.setattr(gpi, "HUB_TOKEN_BUDGET", tokens)
        assert cli(two_plans, "--write")[0] == 0
        monkeypatch.setattr(gpi, "HUB_TOKEN_BUDGET", tokens - 1)
        assert cli(two_plans, "--write")[0] == 2

    def test_dry_run_over_budget_exits_one_and_names_it(self, two_plans, cli, monkeypatch):
        monkeypatch.setattr(gpi, "HUB_TOKEN_BUDGET", 10)
        code, out, _ = cli(two_plans, "--dry-run")
        assert code == 1 and "over-budget" in out


class TestJson:
    def test_write_json_carries_the_budget_fields_and_measures_the_file_that_ships(self, two_plans, cli):
        code, out, _ = cli(two_plans, "--write", "--json")
        assert code == 0
        payload = json.loads(out)
        for key in ("page_cap_ratio", "bytes", "tokens", "budget", "anomalies", "warnings", "findings", "index", "rows"):
            assert key in payload
        shipped = index_of(two_plans).read_bytes().decode("utf-8").replace("\r\n", "\n")
        assert (payload["bytes"], payload["tokens"]) == _measure(shipped)
        assert payload["budget"] == gpi.HUB_TOKEN_BUDGET and payload["rows"] == 2 and payload["written"] is True

    def test_check_json_carries_compared_and_the_findings(self, two_plans, cli):
        cli(two_plans, "--write")
        write_master_plan(two_plans, "Gamma", "GAM")
        code, out, _ = cli(two_plans, "--check", "--json")
        payload = json.loads(out)
        assert code == 1 and payload["compared"] == 2
        assert finding_classes(payload["findings"]) == ["missing-row"]
        assert payload["shape"] == "generated"

    def test_the_json_output_lists_anomalies_and_warnings(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="DONE", created=None)
        payload = json.loads(cli(config_path, "--dry-run", "--json")[1])
        assert finding_classes(payload["anomalies"]) == ["unknown-status"]
        assert finding_classes(payload["warnings"]) == ["missing-field"]


# ---------------------------------------------------------------------------
# Drift classes
# ---------------------------------------------------------------------------


class TestDrift:
    def test_an_unchanged_tree_checks_clean_with_every_path_compared(self, two_plans, cli):
        cli(two_plans, "--write")
        result = gpi.check_plans_index(load(two_plans))
        assert result.exit_code == 0 and result.findings == [] and result.compared == 2

    def test_an_added_master_plan_is_a_missing_row(self, two_plans, cli):
        cli(two_plans, "--write")
        write_master_plan(two_plans, "Gamma", "GAM", created="2026-03-01")
        result = gpi.check_plans_index(load(two_plans))
        assert result.exit_code == 1
        assert [(f["class"], f["path"]) for f in result.findings] == [("missing-row", "Gamma/")]

    def test_a_deleted_master_plan_is_an_orphan_row(self, two_plans, cli):
        cli(two_plans, "--write")
        shutil.rmtree(plans_dir_of(two_plans) / "Beta")
        result = gpi.check_plans_index(load(two_plans))
        assert [(f["class"], f["path"]) for f in result.findings] == [("orphan-row", "Beta/")]

    def test_a_changed_status_line_is_a_stale_row_naming_the_field(self, two_plans, cli):
        cli(two_plans, "--write")
        write_master_plan(two_plans, "Alpha", "ALP", status="IN_PROGRESS")
        result = gpi.check_plans_index(load(two_plans))
        stale = [f for f in result.findings if f["class"] == "stale-row"]
        assert len(stale) == 1
        assert (stale[0]["field"], stale[0]["disk"], stale[0]["rendered"]) == ("status", "COMPLETE", "IN_PROGRESS")
        assert result.exit_code == 1

    def test_one_stale_row_finding_per_differing_field(self, two_plans, cli):
        cli(two_plans, "--write")
        write_master_plan(two_plans, "Alpha", "ALP", status="BLOCKED", updated="2026-05-05")
        fields = sorted(f["field"] for f in gpi.check_plans_index(load(two_plans)).findings)
        assert fields == ["last_updated", "status"]

    def test_a_changed_legend_alone_is_a_stale_shape(self, two_plans, cli):
        cli(two_plans, "--write")
        text = index_of(two_plans).read_text(encoding="utf-8")
        index_of(two_plans).write_text(text.replace("Active execution underway", "Working"), encoding="utf-8")
        result = gpi.check_plans_index(load(two_plans))
        assert finding_classes(result.findings) == ["stale-shape"]
        assert "Working" in result.findings[0]["disk"] and result.exit_code == 1

    def test_a_hand_edited_comment_inside_the_table_is_a_stale_shape(self, two_plans, cli):
        cli(two_plans, "--write")
        text = index_of(two_plans).read_text(encoding="utf-8")
        marker = "|--------|------|--------|---------|--------------|------|\n"
        index_of(two_plans).write_text(text.replace(marker, marker + "<!-- note -->\n"), encoding="utf-8")
        assert finding_classes(gpi.check_plans_index(load(two_plans)).findings) == ["stale-shape"]

    def test_reordered_rows_are_a_stale_shape_even_when_every_cell_matches(self, two_plans, cli):
        cli(two_plans, "--write")
        lines = index_of(two_plans).read_text(encoding="utf-8").split("\n")
        alpha = next(i for i, line in enumerate(lines) if line.startswith("| ALP |"))
        lines[alpha], lines[alpha + 1] = lines[alpha + 1], lines[alpha]
        index_of(two_plans).write_text("\n".join(lines), encoding="utf-8")
        result = gpi.check_plans_index(load(two_plans))
        assert finding_classes(result.findings) == ["stale-shape"]
        assert "order" in result.findings[0]["message"]

    def test_a_byte_difference_no_row_explains_is_a_stale_shape(self, two_plans, cli):
        cli(two_plans, "--write")
        data = index_of(two_plans).read_bytes()
        assert data.count(b"Beta/ |\n") == 1
        index_of(two_plans).write_bytes(data.replace(b"Beta/ |\n", b"Beta/ |\r\r\n"))
        result = gpi.check_plans_index(load(two_plans))
        assert finding_classes(result.findings) == ["stale-shape"]
        assert "no row finding explains it" in result.findings[0]["message"]
        assert result.exit_code == 1
        assert cli(two_plans, "--check")[0] == 1

    def test_a_row_with_matching_cells_but_different_spacing_is_a_stale_row(self, two_plans, cli):
        cli(two_plans, "--write")
        text = index_of(two_plans).read_text(encoding="utf-8")
        index_of(two_plans).write_text(text.replace("| ALP | Alpha |", "|ALP|Alpha|"), encoding="utf-8")
        result = gpi.check_plans_index(load(two_plans))
        assert [(f["class"], f["field"]) for f in result.findings] == [("stale-row", "line-format")]

    def test_a_table_line_with_the_wrong_cell_count_is_named_as_unparsed(self, two_plans, cli):
        cli(two_plans, "--write")
        text = index_of(two_plans).read_text(encoding="utf-8")
        index_of(two_plans).write_text(text.replace("| BET |", "| BET | extra | cells |"), encoding="utf-8")
        classes = finding_classes(gpi.check_plans_index(load(two_plans)).findings)
        assert "unparsed-row" in classes and "missing-row" in classes

    def test_a_row_outside_the_table_region_is_named_as_unparsed(self, two_plans, cli):
        cli(two_plans, "--write")
        written = index_of(two_plans).read_text(encoding="utf-8")
        stray = "| ZZZ | Zed | COMPLETE | 2026-01-09 | 2026-01-09 | Zed/ |\n"
        after_heading = written.replace("| BET |", "\n## Notes\n\n| BET |", 1)
        after_legend = written + stray
        for label, text, marker in (("heading", after_heading, "| BET |"), ("legend", after_legend, "| ZZZ |")):
            index_of(two_plans).write_text(text, encoding="utf-8")
            line = next(n for n, content in enumerate(text.split("\n"), 1) if content.startswith(marker))
            result = gpi.check_plans_index(load(two_plans))
            unparsed = [f for f in result.findings if f["class"] == "unparsed-row"]
            assert [f["line"] for f in unparsed] == [line], label
            assert unparsed[0]["reason"] == "outside-table-region", label
            assert result.exit_code == 1, label
            code, out, _ = cli(two_plans, "--check")
            assert code == 1 and f"line {line} is table-shaped but yields no row" in out, label

    def test_a_missing_index_is_exit_one_with_every_rendered_row_missing(self, two_plans, cli):
        result = gpi.check_plans_index(load(two_plans))
        assert result.exit_code == 1 and not result.exists
        assert finding_classes(result.findings) == ["missing-index", "missing-row", "missing-row"]
        assert cli(two_plans, "--check")[0] == 1
        assert not index_of(two_plans).exists()

    def test_a_missing_index_over_an_empty_plans_dir_is_still_exit_one(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        assert cli(config_path, "--check")[0] == 1

    def test_check_masks_the_generated_line_and_a_crlf_file(self, two_plans, cli):
        cli(two_plans, "--write")
        text = index_of(two_plans).read_text(encoding="utf-8")
        old = next(line for line in text.split("\n") if line.startswith("Generated: "))
        edited = text.replace(old, "Generated: 1999-01-01").replace("\n", "\r\n")
        index_of(two_plans).write_bytes(edited.encode("utf-8"))
        assert cli(two_plans, "--check")[0] == 0

    def test_check_never_writes(self, two_plans, cli):
        cli(two_plans, "--write")
        write_master_plan(two_plans, "Gamma", "GAM")
        before = index_of(two_plans).read_bytes()
        cli(two_plans, "--check")
        assert index_of(two_plans).read_bytes() == before

    def test_an_anomaly_in_the_tree_fails_check_even_when_the_file_matches_the_render(self, tmp_path, cli):
        config_path = make_tree(tmp_path)
        write_master_plan(config_path, "Alpha", "ALP", status="DONE")
        cli(config_path, "--write")
        result = gpi.check_plans_index(load(config_path))
        assert result.findings == [] and finding_classes(result.anomalies) == ["unknown-status"]
        assert result.exit_code == 1


class TestDiffIndexRows:
    def _rows(self):
        rendered = [
            gpi.RenderedRow("ALP", "Alpha", "COMPLETE", "2026-01-01", "2026-02-01", "Alpha/", "Alpha/ALP-Master-Plan.md"),
            gpi.RenderedRow("BET", "Beta", "COMPLETE", "2026-01-02", "2026-02-01", "Beta/", "Beta/BET-Master-Plan.md"),
        ]
        return rendered

    def _disk(self, rendered):
        table = gpi.parse_index_table(
            "| Abbrev | Name | Status | Created | Last Updated | Path |\n"
            "|--------|------|--------|---------|--------------|------|\n"
            + "".join(row.line() + "\n" for row in rendered)
        )
        return table.rows

    def test_identical_rows_have_no_finding_and_a_compared_count(self):
        rendered = self._rows()
        findings = gpi.diff_index_rows(self._disk(rendered), rendered)
        assert findings == [] and findings.compared == 2

    def test_a_repeated_disk_path_is_counted_not_collapsed(self):
        rendered = self._rows()
        disk = self._disk(rendered + [rendered[0]])
        findings = gpi.diff_index_rows(disk, rendered)
        assert finding_classes(findings) == ["duplicate-row"]
        assert findings[0]["lines"] == [3, 5]
        assert findings.compared == 2

    def test_a_corrupted_copy_placed_first_is_still_reported(self):
        rendered = self._rows()
        corrupted = gpi.RenderedRow("ALP", "Alpha", "BLOCKED", "2026-01-01", "2026-02-01", "Alpha/", "x")
        disk = self._disk([corrupted, rendered[0], rendered[1]])
        classes = finding_classes(gpi.diff_index_rows(disk, rendered))
        assert sorted(classes) == ["duplicate-row", "stale-row"]

    def test_a_path_rendered_twice_and_on_disk_once_is_a_missing_row(self):
        rendered = self._rows()
        findings = gpi.diff_index_rows(self._disk(rendered), rendered + [rendered[0]])
        assert finding_classes(findings) == ["missing-row"]


# ---------------------------------------------------------------------------
# Naming and the public surface
# ---------------------------------------------------------------------------


class TestNaming:
    def test_plans_index_path_returns_the_configured_index(self, tmp_path):
        config = load(make_tree(tmp_path))
        assert gpi.plans_index_path(config) == config["_plans_index"]
        assert gpi.plans_index_path(config).name == "00-Index-Plans.md"

    def test_is_generated_plans_index_file_is_true_only_for_that_name(self, tmp_path):
        config = load(make_tree(tmp_path))
        assert gpi.is_generated_plans_index_file("00-Index-Plans.md", config)
        assert not gpi.is_generated_plans_index_file("00-Index-Backlog.md", config)
        assert not gpi.is_generated_plans_index_file("Alpha-Master-Plan.md", config)

    def test_a_custom_index_name_is_honored(self, tmp_path):
        config_path = make_tree(tmp_path, "")
        config_path.write_text(
            'project:\n  name: "X"\n  plans_dir: "Plans"\n  index_files:\n    plans: "My-Plans.md"\n',
            encoding="utf-8",
        )
        config = load(config_path)
        assert gpi.is_generated_plans_index_file("My-Plans.md", config)
        assert not gpi.is_generated_plans_index_file("00-Index-Plans.md", config)


class TestFacade:
    @pytest.mark.parametrize("name", PUBLIC_API)
    def test_every_public_api_name_resolves_on_the_module(self, name):
        assert hasattr(gpi, name), f"generate_plans_index no longer exposes {name}"

    def test_the_module_lists_exactly_the_public_api_in_all(self):
        assert sorted(gpi.__all__) == sorted(PUBLIC_API)
