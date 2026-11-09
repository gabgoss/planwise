"""Pins the two consumer doctor stages: their Part 3 headings and their output.

Stage headings are pinned by reading the Part 3 handler and the registration
comments in doctor_cli.py. The fixture tests run each stage function on a
known-bad project and on a clean twin, built in tmp_path. The regression tests
cover backlog-item matching, the skipped trees, an unreadable plans index, the
redirected verdict and the plugin-target filter. The agreement tests compare
each stage's reported state with its actor on one fixture tree per state:
Stage 25 with the checker's own verdict, Stage 24 with
``read_limits.classify_file(path, None)``.
"""

import math
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import doctor_citation_stage
import read_limits
from check_section_citations import check_tree
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


# ------------------------------------------------ reporter-actor agreement
#
# Each test builds one fixture tree, asks the actor for its disposition, runs
# the reporter stage on the same tree, and asserts the two agree. Fixtures are
# built from the actor's own predicate, never from the reporter's text.

_STAGE_ROW_RE = re.compile(r"^  (\.claude/rules/\S+):([0-9]+): (.*)$", re.MULTILINE)


def _stage_rows(out: str) -> dict[tuple[str, int], str]:
    """The reporter's state per printed row, read from the stage's own row shapes."""
    rows = {}
    for shown, line, rest in _STAGE_ROW_RE.findall(out):
        if rest.startswith("unreadable — "):
            state = "unreadable"
        elif " is not in " in rest:
            state = "dangling"
        elif " now lives in " in rest:
            state = "redirected"
        elif " does not resolve" in rest:
            state = "unresolved-target"
        else:
            state = f"unknown: {rest}"
        rows[(shown, int(line))] = state
    return rows


def _checker_rows(root: Path, plugin: Path) -> dict[tuple[str, int], object]:
    """The actor: the checker's own findings for the consumer rules, keyed as the stage prints them."""
    rules = root / ".claude" / "rules"
    found = check_tree(plugin, extra_roots=(rules,), exclude=(rules / "planwise",))
    return {
        (Path(f.path).resolve().relative_to(root.resolve()).as_posix(), f.line): f
        for f in found
        if rules.resolve() in Path(f.path).resolve().parents
    }


CITATION_STATES = [
    pytest.param("See `known.md` §9 for one.\n", "dangling", id="dangling"),
    pytest.param("See `fam-Part-1-Alpha.md` §2 for beta.\n", "redirected", id="redirected"),
    pytest.param("See `references/gone.md` §3 for two.\n", "unresolved-target", id="unresolved-target"),
]


@pytest.mark.parametrize("body, state", CITATION_STATES)
def test_stage25_reported_state_equals_the_checker_disposition(tmp_path, capsys, body, state):
    root = _project(tmp_path / "proj")
    plugin = _plugin(tmp_path / "plugin")
    _write(root / ".claude" / "rules" / "cites.md", "# Cites\n\n" + body)
    actor = _checker_rows(root, plugin)
    (key,) = [k for k, f in actor.items() if f.verdict != "ok"]
    assert actor[key].verdict == state
    run_section_citation_stage(SimpleNamespace(project_root=root, planwise_root="planwise", plugin_root=plugin))
    reported = _stage_rows(capsys.readouterr().out)
    assert reported == {key: actor[key].verdict}


def test_stage25_ok_disposition_prints_the_no_dangling_line(tmp_path, capsys):
    root = _project(tmp_path / "proj")
    plugin = _plugin(tmp_path / "plugin")
    _write(root / ".claude" / "rules" / "cites.md", "# Cites\n\nSee `known.md` §1 for one.\n")
    actor = _checker_rows(root, plugin)
    assert [f.verdict for f in actor.values()] == ["ok"]
    run_section_citation_stage(SimpleNamespace(project_root=root, planwise_root="planwise", plugin_root=plugin))
    out = capsys.readouterr().out
    assert _stage_rows(out) == {}
    assert out.startswith("No dangling section citation in .claude/rules/")


def test_stage25_unreadable_rule_is_reported_and_the_other_rule_still_prints(tmp_path, capsys):
    root = _project(tmp_path / "proj")
    plugin = _plugin(tmp_path / "plugin")
    rules = root / ".claude" / "rules"
    _write(rules / "cites.md", "# Cites\n\nSee `known.md` §9 for one.\n")
    (rules / "bad.md").write_bytes(b"# Bad\n\nSee \xa7 1 here.\n")  # a cp1252 section sign
    actor = _checker_rows(root, plugin)
    assert sorted(f.verdict for f in actor.values()) == ["dangling", "unreadable"]
    run_section_citation_stage(SimpleNamespace(project_root=root, planwise_root="planwise", plugin_root=plugin))
    out = capsys.readouterr().out
    assert _stage_rows(out) == {k: f.verdict for k, f in actor.items()}
    (bad,) = [f for f in actor.values() if f.verdict == "unreadable"]
    assert "byte 0xa7 at offset 11" in bad.note and f".claude/rules/bad.md:3: unreadable — {bad.note}" in out
    assert out.rstrip().endswith(doctor_citation_stage._UNREADABLE_REMEDY)


def test_stage25_scans_only_the_rules_root(tmp_path, monkeypatch):
    root = _project(tmp_path / "scope")
    calls = []
    monkeypatch.setattr(doctor_citation_stage, "check_tree", lambda *a, **kw: calls.append(kw) or [])
    run_section_citation_stage(_cfg(root))
    rules = (root / ".claude" / "rules").resolve()
    assert [Path(p).resolve() for p in calls[0]["scan_roots"]] == [rules]
    assert [Path(p).resolve() for p in calls[0]["extra_roots"]] == [rules]


def _sized(path: Path, num_bytes: int, line_bytes: int = 100) -> Path:
    """A file of ``num_bytes`` bytes in lines of ``line_bytes`` (the last may be shorter)."""
    row = "a" * (line_bytes - 1) + "\n"
    full, rest = divmod(num_bytes, line_bytes)
    return _write(path, row * full + "b" * rest)


def _level_fixture(rules: Path, level: str) -> Path:
    """A rule file sized from the actor's own thresholds at the conservative ratio."""
    ratio = read_limits.bytes_per_token(None)
    warn_bytes = math.ceil(read_limits.READ_TOKEN_WARN * ratio)
    cap_bytes = math.ceil(read_limits.READ_PAGE_CAP_TOKENS * ratio)
    sizes = {"Green": 1000, "Warn": (warn_bytes + cap_bytes) // 2, "Critical": cap_bytes + 1000}
    return _sized(rules / f"{level.lower()}.md", sizes[level])


@pytest.mark.parametrize("level", ["Green", "Warn", "Critical"])
def test_stage24_printed_level_equals_classify_file(tmp_path, capsys, level):
    root = _project(tmp_path / "proj")
    path = _level_fixture(root / ".claude" / "rules", level)
    actor = read_limits.classify_file(str(path.resolve()), None)["level"]
    assert actor == level
    run_read_gate_stage(_cfg(root))
    out = capsys.readouterr().out
    printed = re.findall(rf"^  (\w+)  reason=\w+  {re.escape('.claude/rules/' + path.name)}  ", out, re.MULTILINE)
    # The stage's documented contract: Warn and Critical print, Green and Notice do not.
    if actor in ("Warn", "Critical"):
        assert printed == [actor]
    else:
        assert printed == []
        assert "No file at Warn or Critical (1 file(s) scanned)." in out


def test_stage24_notice_level_is_silent_and_unreachable_at_the_stage_ratio(tmp_path, capsys, monkeypatch):
    # With no cost thresholds the actor's read gate yields Green, Warn or
    # Critical only, so no file reaches Notice at the stage's call. The
    # reporter's mapping of Notice is pinned through the actor's own entry.
    root = _project(tmp_path / "proj")
    path = _level_fixture(root / ".claude" / "rules", "Green")
    ratio = read_limits.bytes_per_token(None)
    for tokens in (0, read_limits.READ_TOKEN_WARN - 1, read_limits.READ_TOKEN_WARN, read_limits.READ_PAGE_CAP_TOKENS):
        _sized(path, int(tokens * ratio))
        assert read_limits.classify_file(str(path), None)["level"] != "Notice"
    real = read_limits.classify_file

    def notice(p, model, *a, **kw):
        return {**real(p, model, *a, **kw), "level": "Notice"}

    monkeypatch.setattr(read_limits, "classify_file", notice)
    assert read_limits.classify_file(str(path), None)["level"] == "Notice"
    run_read_gate_stage(_cfg(root))
    out = capsys.readouterr().out
    assert "No file at Warn or Critical (1 file(s) scanned)." in out
    assert path.name not in out
