"""Pins the two consumer doctor stages: their Part 3 headings and their output.

Stage headings are pinned by reading the Part 3 handler and the registration
comments in doctor_cli.py. The fixture tests run each stage function on a
known-bad project and on a clean twin, built in tmp_path. The regression tests
cover backlog-item matching, the skipped trees, an unreadable plans index, the
redirected verdict and the plugin-target filter.
"""

import re
import sys
from pathlib import Path
from types import SimpleNamespace

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import doctor_citation_stage
from doctor_citation_stage import run_section_citation_stage
from doctor_read_gate_stage import run_read_gate_stage

DOCTOR_HANDLER = PLUGIN_ROOT / "handlers" / "doctor.md"
DOCTOR_HANDLER_PART3 = PLUGIN_ROOT / "handlers" / "doctor-Part-3-TokenSaverAndBookkeepingReadGates.md"
DOCTOR_CLI = PLUGIN_ROOT / "scripts" / "doctor_cli.py"

READ_GATE_HEADING = "Consumer Read-Gate Scan"
CITATION_HEADING = "Consumer Section-Citation Check"

_STAGE_HEADING_RE = re.compile(r"^### Stage ([0-9]+[a-z]?): (.+)$", re.MULTILINE)

# The padded rule is 602 lines of 100 bytes: Warn by tokens, under the line cap.
_PADDED_RULE = ("a" * 99 + "\n") * 602


def _cfg(project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(project_root=project_root, planwise_root="planwise", plugin_root=PLUGIN_ROOT)


def _project(root: Path) -> Path:
    (root / "planwise" / "Backlog").mkdir(parents=True)
    (root / "planwise" / "config.yaml").write_text("project:\n  name: fixture\n", encoding="utf-8")
    (root / ".claude" / "rules").mkdir(parents=True)
    return root


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _item(root: Path, name: str, title: str, status: str = "OPEN", body: str = "") -> None:
    _write(root / "planwise" / "Backlog" / name, f"---\ntitle: {title}\nstatus: {status}\n---\n\n{body}\n")


def _warn_row(shown: str) -> re.Pattern:
    return re.compile(rf"^  Warn  reason=read  {re.escape(shown)}  \(~[0-9]+ tokens\)$", re.MULTILINE)


def _filing_line(name: str) -> str:
    return f"Refactor `{name}` below the read warn"


_PLANS_INDEX = (
    "| Abbrev | Name | Status | Created | Last Updated | Path |\n"
    "|---|---|---|---|---|---|\n"
    "| FIX | Fixture | IN_PROGRESS | 2026-01-01 | 2026-01-01 | Fixture/ |\n"
)


def _plugin(root: Path) -> Path:
    """A minimal plugin root: one plain reference and a two-Part family."""
    _write(root / "references" / "known.md", "# Known\n\n## 1. One\n\nText.\n")
    _write(root / "references" / "fam-Part-1-Alpha.md", "# Fam Part 1\n\n## 1. Alpha\n\nText.\n")
    _write(root / "references" / "fam-Part-2-Beta.md", "# Fam Part 2\n\n## 2. Beta\n\nText.\n")
    return root


class TestPart3StageHeadings:
    def test_part3_carries_both_consumer_stage_headings(self):
        part3 = DOCTOR_HANDLER_PART3.read_text(encoding="utf-8-sig")
        headings = {text: num for num, text in _STAGE_HEADING_RE.findall(part3)}
        assert READ_GATE_HEADING in headings
        assert CITATION_HEADING in headings

        cli = DOCTOR_CLI.read_text(encoding="utf-8-sig")
        read_gate_reg = re.search(r"^\s*# Stage ([0-9]+): consumer read-gate scan", cli, re.MULTILINE)
        citation_reg = re.search(r"^\s*# Stage ([0-9]+): consumer section-citation check", cli, re.MULTILINE)
        assert read_gate_reg and citation_reg
        assert headings[READ_GATE_HEADING] == read_gate_reg.group(1)
        assert headings[CITATION_HEADING] == citation_reg.group(1)

        part_rows = [ln for ln in DOCTOR_HANDLER.read_text(encoding="utf-8-sig").splitlines() if ln.startswith("| 3 |")]
        assert len(part_rows) == 1
        assert READ_GATE_HEADING in part_rows[0]
        assert CITATION_HEADING in part_rows[0]


class TestConsumerReadGateStage:
    def test_fixture_read_gate_names_padded_rule(self, tmp_path, capsys):
        root = _project(tmp_path / "bad")
        (root / ".claude" / "rules" / "padded.md").write_text(_PADDED_RULE, encoding="utf-8")
        run_read_gate_stage(_cfg(root))
        out = capsys.readouterr().out
        assert _warn_row(".claude/rules/padded.md").search(out)
        assert "/planwise backlog" in out
        assert _filing_line("padded.md") in out

    def test_fixture_read_gate_clean_twin_summary_only(self, tmp_path, capsys):
        root = _project(tmp_path / "clean")
        (root / ".claude" / "rules" / "small.md").write_text("A short rule.\n", encoding="utf-8")
        run_read_gate_stage(_cfg(root))
        out = capsys.readouterr().out
        assert "No file at Warn or Critical (1 file(s) scanned)." in out
        assert "padded.md" not in out

    def test_backlog_match_needs_an_open_item_whose_title_names_the_file(self, tmp_path, capsys):
        root = _project(tmp_path / "items")
        _write(root / ".claude" / "rules" / "padded.md", _PADDED_RULE)
        _item(root, "BB-001-Mention.md", "Unrelated work", body="A passing mention of padded.md.")
        _item(root, "BB-002-Closed.md", "Refactor `padded.md` below the read warn", status="COMPLETE")
        _item(root, "BB-003-Longer.md", "Refactor `my-padded.md` below the read warn")
        run_read_gate_stage(_cfg(root))
        out = capsys.readouterr().out
        assert "named by" not in out
        assert _filing_line("padded.md") in out

        _item(root, "BB-004-Open.md", "Refactor `padded.md` below the read warn")
        run_read_gate_stage(_cfg(root))
        out = capsys.readouterr().out
        assert "backlog: named by BB-004-Open.md\n" in out
        assert _filing_line("padded.md") not in out

    def test_shared_basename_matches_and_files_by_project_path(self, tmp_path, capsys):
        root = _project(tmp_path / "shared")
        _write(root / ".claude" / "skills" / "a" / "SKILL.md", _PADDED_RULE)
        _write(root / ".claude" / "skills" / "b" / "SKILL.md", _PADDED_RULE)
        _item(root, "BB-001-SkillA.md", "Refactor `.claude/skills/a/SKILL.md` below the read warn")
        run_read_gate_stage(_cfg(root))
        out = capsys.readouterr().out
        assert out.count("backlog: named by BB-001-SkillA.md") == 1
        assert _filing_line(".claude/skills/b/SKILL.md") in out
        assert _filing_line("SKILL.md") not in out

    def test_installed_copies_under_rules_planwise_are_skipped(self, tmp_path, capsys):
        root = _project(tmp_path / "managed")
        _write(root / ".claude" / "rules" / "planwise" / "padded.md", _PADDED_RULE)
        _write(root / ".claude" / "rules" / "small.md", "A short rule.\n")
        run_read_gate_stage(_cfg(root))
        out = capsys.readouterr().out
        assert "No file at Warn or Critical (1 file(s) scanned)." in out
        assert "padded.md" not in out

    def test_plan_outputs_and_reviews_are_skipped(self, tmp_path, capsys):
        root = _project(tmp_path / "plan")
        _write(root / "planwise" / "Plans" / "00-Index-Plans.md", _PLANS_INDEX)
        plan = root / "planwise" / "Plans" / "Fixture"
        _write(plan / "FIX-Master-Plan.md", _PADDED_RULE)
        _write(plan / "Sprint-01-One" / "Outputs" / "report.md", _PADDED_RULE)
        _write(plan / "Reviews" / "review.md", _PADDED_RULE)
        run_read_gate_stage(_cfg(root))
        out = capsys.readouterr().out
        assert "Active plan(s): FIX" in out
        assert _warn_row("planwise/Plans/Fixture/FIX-Master-Plan.md").search(out)
        assert "report.md" not in out
        assert "review.md" not in out

    def test_unreadable_plans_index_still_scans_claude_trees(self, tmp_path, capsys):
        root = _project(tmp_path / "badindex")
        plans = root / "planwise" / "Plans"
        plans.mkdir(parents=True)
        (plans / "00-Index-Plans.md").write_bytes(b"| Abbrev | Name |\n\xff\xfe\x80 not utf-8\n")
        _write(root / ".claude" / "rules" / "padded.md", _PADDED_RULE)
        run_read_gate_stage(_cfg(root))
        out = capsys.readouterr().out
        assert "Active plan: could not be resolved (" in out
        assert _warn_row(".claude/rules/padded.md").search(out)


class TestConsumerSectionCitationStage:
    def test_fixture_citation_names_dangling(self, tmp_path, capsys):
        root = _project(tmp_path / "bad")
        (root / ".claude" / "rules" / "cites.md").write_text(
            "# Cites\n\nSee `rule-authoring.md` §99 for the layout.\n", encoding="utf-8"
        )
        run_section_citation_stage(_cfg(root))
        out = capsys.readouterr().out
        assert "§99" in out
        assert "cites.md" in out
        assert "dangling section citation" in out

    def test_fixture_citation_clean_twin_summary_only(self, tmp_path, capsys):
        root = _project(tmp_path / "clean")
        (root / ".claude" / "rules" / "small.md").write_text(
            "# Small\n\nSee `rule-authoring.md` §7 for the layout.\n", encoding="utf-8"
        )
        run_section_citation_stage(_cfg(root))
        out = capsys.readouterr().out
        assert "No dangling section citation in .claude/rules/" in out
        assert "§99" not in out
        assert "cites.md" not in out

    def test_redirected_citation_names_the_file_that_holds_the_section(self, tmp_path, capsys):
        root = _project(tmp_path / "redirect")
        plugin = _plugin(tmp_path / "plugin")
        _write(root / ".claude" / "rules" / "cites.md", "# Cites\n\nSee `fam-Part-1-Alpha.md` §2 for beta.\n")
        run_section_citation_stage(SimpleNamespace(project_root=root, planwise_root="planwise", plugin_root=plugin))
        out = capsys.readouterr().out
        assert ".claude/rules/cites.md:3:" in out
        assert "references/fam-Part-2-Beta.md" in out

    def test_only_plugin_targets_are_reported(self, tmp_path, capsys):
        root = _project(tmp_path / "targets")
        plugin = _plugin(tmp_path / "plugin")
        _write(root / ".claude" / "rules" / "local.md", "# Local\n\n## 1. Only\n")
        _write(
            root / ".claude" / "rules" / "cites.md",
            "# Cites\n\n"
            "See `known.md` §9 for one.\n\n"
            "See `references/gone.md` §3 for two.\n\n"
            "See `local.md` §5 for three.\n\n"
            "See `planwise/Plans/Some/Plan.md` §2 for four.\n",
        )
        run_section_citation_stage(SimpleNamespace(project_root=root, planwise_root="planwise", plugin_root=plugin))
        out = capsys.readouterr().out
        assert ".claude/rules/cites.md:3:" in out
        assert ".claude/rules/cites.md:5:" in out
        assert ".claude/rules/cites.md:7:" not in out
        assert ".claude/rules/cites.md:9:" not in out
        assert "2 citation(s) to project files skipped" in out

    def test_installed_copies_are_excluded_from_the_check(self, tmp_path, monkeypatch):
        root = _project(tmp_path / "exclude")
        calls = []
        monkeypatch.setattr(doctor_citation_stage, "check_tree", lambda *a, **kw: calls.append(kw) or [])
        run_section_citation_stage(_cfg(root))
        managed = (root / ".claude" / "rules" / "planwise").resolve()
        assert len(calls) == 1
        assert [Path(p).resolve() for p in calls[0].get("exclude", ())] == [managed]
