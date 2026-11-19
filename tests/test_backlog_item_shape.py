"""Pins doctor Stage 27, the backlog item shape advisory.

Every fixture is built in tmp_path. Each class test writes one item that shows exactly
one drift class and asserts the line the stage prints for it, plus the item id. A
template-shaped control proves a clean item yields no finding.
"""

import contextlib
import io
import re
import sys
from pathlib import Path
from types import SimpleNamespace

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import backlog_item_shape
import doctor_cli
import init_project as ip
from backlog_item_shape import (
    GAP_CLASSES,
    TEMPLATE_FRONTMATTER_KEYS,
    run_item_shape_stage,
    scan_item_shapes,
)

_CONFIG = "project:\n  name: fixture\n  backlog_dir: Backlog\n"
_CLEAN_LINE = "Backlog item shape: 1 open items scanned, each follows the item template.\n"
_CORE = ("Summary", "Problem", "Proposed Solution", "Acceptance Criteria")


def _cfg(root: Path) -> SimpleNamespace:
    return SimpleNamespace(project_root=root, planwise_root="planwise", plugin_root=PLUGIN_ROOT)


def _project(root: Path) -> Path:
    (root / "planwise" / "Backlog" / "Archive").mkdir(parents=True)
    (root / "planwise" / "config.yaml").write_text(_CONFIG, encoding="utf-8")
    return root


def _item(
    root: Path,
    number: int,
    *,
    archive: bool = False,
    status: str = "NOT_STARTED",
    title: str = "A fixture item",
    extra_fm: tuple = (),
    headings: tuple = _CORE,
    extra_body: str = "",
    priority_line: str | None = "**Priority:** Medium",
    domain_line: str | None = "**Domain:** INFRA",
    footer: str | None = "*Created: 2026-11-18*",
) -> Path:
    """Write one item. A priority line, domain line or footer set to None is omitted."""
    lines = [
        "---",
        f"id: {number}",
        f'title: "{title}"',
        "priority: Medium",
        f"status: {status}",
        "abbrev: INFRA",
        "created: 2026-11-18",
        "blocks: []",
        *extra_fm,
        "---",
        "",
        f"# BB-{number}-01-INFRA-Fixture: {title}",
        "",
    ]
    if priority_line is not None:
        lines.append(priority_line)
    if domain_line is not None:
        lines.append(domain_line)
    lines += ["", "---", ""]
    for heading in headings:
        lines += [f"## {heading}", "", "Text.", ""]
    if extra_body:
        lines += [extra_body, ""]
    lines += ["---", ""]
    if footer is not None:
        lines.append(footer)
    folder = root / "planwise" / "Backlog" / ("Archive" if archive else "")
    path = folder / f"BB-{number}-01-INFRA-Fixture.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(root: Path, capsys) -> str:
    capsys.readouterr()
    run_item_shape_stage(_cfg(root))
    return capsys.readouterr().out


def _label(key: str) -> str:
    return dict(GAP_CLASSES)[key]


class TestCleanControl:
    def test_a_template_shaped_item_yields_no_finding(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1)
        assert _run(root, capsys) == _CLEAN_LINE

    def test_the_optional_template_keys_and_sections_are_not_drift(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(
            root,
            1,
            extra_fm=("refined: true", "needs_plan: true", "route_hint: B", "route_evidence: x", "route_dated: 2026-11-18"),
            headings=(*_CORE, "Resolution", "Verification", "Open Questions", "Related", "Files Touched", "Notes"),
        )
        assert _run(root, capsys) == _CLEAN_LINE

    def test_a_heading_inside_a_fenced_block_is_not_a_heading(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, extra_body="```\n## Not A Real Section\n```")
        assert _run(root, capsys) == _CLEAN_LINE


class TestEachClass:
    def _assert_one_class(self, root, capsys, key, ident="1"):
        out = _run(root, capsys)
        lines = out.splitlines()
        assert lines[0] == "Backlog item shape (advisory):"
        assert lines[1] == "  open items scanned: 1"
        assert f"  ~ {_label(key)}: 1 — {ident}" in lines
        assert sum(line.startswith("  ~ ") for line in lines) == 1
        assert lines[-1] == "  action: repair the listed items with /planwise upgrade"

    def test_status_outside_the_valid_statuses(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, status="DONE")
        self._assert_one_class(root, capsys, "status-invalid")

    def test_legacy_loop_decision_section(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, headings=(*_CORE, "Loop Decision Needed"))
        self._assert_one_class(root, capsys, "legacy-decision")

    def test_title_over_the_cap(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, title="T" * 121)
        self._assert_one_class(root, capsys, "title-over-cap")

    def test_title_at_the_cap_is_not_drift(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, title="T" * 120)
        assert _run(root, capsys) == _CLEAN_LINE

    def test_non_template_heading(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, headings=(*_CORE, "Rambling Thoughts"))
        self._assert_one_class(root, capsys, "section-nontemplate")

    def test_missing_core_section(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, headings=("Summary", "Problem", "Acceptance Criteria"))
        self._assert_one_class(root, capsys, "section-missing")

    def test_priority_line_differing_from_the_frontmatter(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, priority_line="**Priority:** High")
        self._assert_one_class(root, capsys, "priority-line")

    def test_priority_line_missing(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, priority_line=None)
        self._assert_one_class(root, capsys, "priority-line")

    def test_domain_line_missing(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, domain_line=None)
        self._assert_one_class(root, capsys, "domain-line")

    def test_domain_line_differing_from_the_frontmatter(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, domain_line="**Domain:** BUG")
        self._assert_one_class(root, capsys, "domain-line")

    def test_footer_missing(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, footer=None)
        self._assert_one_class(root, capsys, "footer")

    def test_footer_differing_from_created(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, footer="*Created: 2026-01-01*")
        self._assert_one_class(root, capsys, "footer")

    def test_non_template_frontmatter_key(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1, extra_fm=("owner: someone",))
        self._assert_one_class(root, capsys, "key-nontemplate")

    def test_every_class_has_a_test_in_this_file(self):
        keys = {key for key, _ in GAP_CLASSES}
        source = Path(__file__).read_text(encoding="utf-8")
        for key in keys:
            assert f'"{key}"' in source, key


class TestScope:
    def test_an_archived_item_is_not_scanned(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1)
        _item(root, 2, archive=True, status="DONE")
        assert _run(root, capsys) == _CLEAN_LINE

    def test_a_closed_item_outside_archive_is_not_scanned(self, tmp_path):
        root = _project(tmp_path)
        _item(root, 1, status="COMPLETE", footer=None)
        result = scan_item_shapes(root / "planwise" / "Backlog")
        assert result.scanned == 0
        assert all(not ids for ids in result.classes.values())

    def test_more_than_ten_ids_print_ten_and_a_remainder(self, tmp_path, capsys):
        root = _project(tmp_path)
        for number in range(1, 13):
            _item(root, number, footer=None)
        out = _run(root, capsys)
        assert f"  ~ {_label('footer')}: 12 — 1, 10, 11, 12, 2, 3, 4, 5, 6, 7, +2 more" in out

    def test_an_item_without_frontmatter_is_counted_as_unreadable(self, tmp_path, capsys):
        root = _project(tmp_path)
        _item(root, 1)
        (root / "planwise" / "Backlog" / "BB-2-01-INFRA-NoFrontmatter.md").write_text("# no frontmatter\n", encoding="utf-8")
        out = _run(root, capsys)
        assert "  open items scanned: 1\n" in out
        assert "  ~ unreadable item files: 1\n" in out

    def test_crlf_files_read_the_same_as_lf_files(self, tmp_path, capsys):
        root = _project(tmp_path)
        path = _item(root, 1)
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        assert _run(root, capsys) == _CLEAN_LINE

    def test_no_backlog_folder_prints_the_nothing_scanned_line(self, tmp_path, capsys):
        (tmp_path / "planwise").mkdir()
        (tmp_path / "planwise" / "config.yaml").write_text(_CONFIG, encoding="utf-8")
        assert _run(tmp_path, capsys) == "Backlog item shape: no backlog folder is configured, nothing scanned.\n"


class TestTemplatePin:
    def test_template_frontmatter_keys_match_the_template_field_table(self):
        text = (PLUGIN_ROOT / "templates" / "backlog-item.md").read_text(encoding="utf-8")
        table = text.split("### Field Definitions", 1)[1].split("### Status Values", 1)[0]
        keys = set(re.findall(r"(?m)^\| `([a-z_]+)` \|", table))
        assert keys, "the Field Definitions table was not found"
        assert keys == set(TEMPLATE_FRONTMATTER_KEYS)

    def test_the_shipped_template_statuses_are_the_valid_statuses(self):
        text = (PLUGIN_ROOT / "templates" / "backlog-item.md").read_text(encoding="utf-8")
        table = text.split("### Status Values", 1)[1].split("\n---\n", 1)[0]
        listed = set(re.findall(r"(?m)^\| `([A-Z_]+)` \|", table))
        from constants import VALID_STATUSES

        assert listed == set(VALID_STATUSES)


class TestRunDoctor:
    def _doctor_cfg(self, root: Path):
        cfg = ip.InitConfig(project_name="Fixture", project_root=root, plugin_root=PLUGIN_ROOT)
        config = root / "planwise" / "config.yaml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(f'plugin_version: "{cfg.plugin_version}"\n' + _CONFIG, encoding="utf-8")
        (root / "planwise" / "Backlog").mkdir(exist_ok=True)
        return cfg

    def test_run_doctor_prints_the_banner_after_stage_26_and_returns_zero(self, tmp_path):
        cfg = self._doctor_cfg(tmp_path)
        _item(tmp_path, 1, status="DONE")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = doctor_cli._run_doctor(cfg)
        out = buf.getvalue()
        assert status == 0
        assert "planwise doctor — backlog item shape" in out
        assert out.index("lesson resolution keys") < out.index("backlog item shape")
        assert f"  ~ {_label('status-invalid')}: 1 — 1" in out

    def test_a_stage_failure_prints_one_line_and_still_returns_zero(self, tmp_path, monkeypatch):
        cfg = self._doctor_cfg(tmp_path)

        def boom(_cfg):
            raise RuntimeError("boom")

        monkeypatch.setattr(backlog_item_shape, "run_item_shape_stage", boom)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = doctor_cli._run_doctor(cfg)
        assert status == 0
        assert "Backlog item shape: the check failed: boom" in buf.getvalue()
