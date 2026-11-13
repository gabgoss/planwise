"""Pins doctor Stage 26, the lesson resolution keys advisory.

Every fixture is built in tmp_path. Each test names one gap class or one
report shape and asserts the line the stage prints for it, plus the lesson id.
"""

import contextlib
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import doctor_cli
import init_project as ip
from doctor_lesson_keys_stage import run_lesson_keys_stage, scan_lesson_keys
from lessons_index_schema import parse_enforced_by

_VALID = {
    "status": "documented",
    "origin": "planwise",
    "promotion-target": "[rule]",
    "enforced-by": '"test: tests/x.py::t"',
}
_KINDS_BLOCK = "lesson_check_kinds:\n  - hook\n  - test\n  - lint\n  - script\n"
_CONFIG = "project:\n  name: fixture\n  lessons_dir: LessonsLearned\n"
_UPGRADE_LINE = "config.yaml declares no lesson_check_kinds"


def _cfg(root: Path) -> SimpleNamespace:
    return SimpleNamespace(project_root=root, planwise_root="planwise", plugin_root=PLUGIN_ROOT)


def _project(root: Path, config_extra: str = _KINDS_BLOCK, config: str = _CONFIG) -> Path:
    (root / "planwise" / "LessonsLearned" / "Archive").mkdir(parents=True)
    (root / "planwise" / "config.yaml").write_text(config + config_extra, encoding="utf-8")
    return root


def _lesson(root: Path, number: int, archive: bool = False, **keys) -> Path:
    """Write one lesson. A key set to None is omitted."""
    values = {**_VALID, **keys}
    name = f"LL-{number:03d}"
    lines = ["---", f"id: {name}", f"title: Lesson {number}"]
    lines += [f"{k}: {v}" for k, v in values.items() if v is not None]
    lines += ["---", "", "Body.", ""]
    folder = root / "planwise" / "LessonsLearned" / ("Archive" if archive else "")
    path = folder / f"{name}-Fixture.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _run(root: Path, capsys) -> str:
    capsys.readouterr()
    run_lesson_keys_stage(_cfg(root))
    return capsys.readouterr().out


class TestReportShape:
    def test_every_lesson_valid_prints_the_all_clear_line(self, tmp_path, capsys):
        root = _project(tmp_path)
        _lesson(root, 1)
        _lesson(root, 2, archive=True)
        out = _run(root, capsys)
        assert out == (
            "Lesson resolution keys: 2 open lessons scanned, each carries a valid origin and check answer.\n"
        )

    def test_report_opens_with_the_scanned_count_then_gaps_then_action(self, tmp_path, capsys):
        root = _project(tmp_path)
        _lesson(root, 1, origin=None)
        lines = _run(root, capsys).splitlines()
        assert lines[0] == "Lesson resolution keys (advisory):"
        assert lines[1] == "  open lessons scanned: 1"
        assert lines[2] == "  ~ no origin: key: 1 — LL-001"
        assert lines[-1] == (
            "  action: set the keys with /planwise lessons curate or /planwise lessons promote-batch"
        )

    def test_landed_lesson_with_no_keys_is_not_counted_or_reported(self, tmp_path, capsys):
        root = _project(tmp_path)
        _lesson(root, 1)
        _lesson(root, 2, status="rule", origin=None, **{"promotion-target": None, "enforced-by": None})
        out = _run(root, capsys)
        assert "1 open lessons scanned" in out
        assert "LL-002" not in out

    def test_twelve_lessons_with_one_gap_print_ten_ids_and_two_more(self, tmp_path, capsys):
        root = _project(tmp_path)
        for n in range(1, 13):
            _lesson(root, n, origin=None)
        out = _run(root, capsys)
        ids = ", ".join(f"LL-{n:03d}" for n in range(1, 11))
        assert f"  ~ no origin: key: 12 — {ids}, +2 more\n" in out
        assert "LL-011" not in out

    def test_unreadable_lesson_file_is_counted_in_one_line(self, tmp_path, capsys):
        root = _project(tmp_path)
        _lesson(root, 1)
        (root / "planwise" / "LessonsLearned" / "LL-002-Bad.md").write_bytes(b"---\nid: LL-002\n\xff\xfe\n---\n")
        (root / "planwise" / "LessonsLearned" / "LL-003-NoFrontmatter.md").write_text("no block\n", encoding="utf-8")
        out = _run(root, capsys)
        assert "  ~ unreadable lesson files: 2\n" in out
        assert "  open lessons scanned: 1\n" in out
        assert "LL-002" not in out

    def test_archive_folder_is_scanned(self, tmp_path, capsys):
        root = _project(tmp_path)
        _lesson(root, 1, archive=True, origin="nowhere")
        out = _run(root, capsys)
        assert "  ~ origin: outside the known origins: 1 — LL-001" in out


class TestGapClasses:
    @pytest.mark.parametrize(
        "keys, label, ids",
        [
            pytest.param({"origin": None}, "no origin: key", "LL-001", id="origin-missing"),
            pytest.param({"origin": "somewhere"}, "origin: outside the known origins", "LL-001", id="origin-unknown"),
            pytest.param(
                {"promotion-target": None}, "no promotion-target: key", "LL-001", id="target-missing"
            ),
            pytest.param(
                {"promotion-target": "[rule, wiki]"},
                "promotion-target: token outside the known targets",
                "LL-001",
                id="target-unknown",
            ),
            pytest.param({"enforced-by": None}, "no enforced-by: answer", "LL-001", id="check-missing"),
            pytest.param(
                {"enforced-by": '"no colon here"'},
                "enforced-by: answer that does not read as kind: text",
                "LL-001",
                id="check-invalid",
            ),
            pytest.param(
                {"enforced-by": '"ci: pipeline job"'},
                "enforced-by: kind that config does not declare",
                "LL-001",
                id="kind-unknown",
            ),
            pytest.param(
                {"enforced-by": '"none:"'}, "enforced-by: none: with no reason", "LL-001", id="none-no-reason"
            ),
            pytest.param(
                {"origin": "own-code", "promotion-target": "[rule]"},
                "code origin with no code target",
                "LL-001",
                id="origin-target-mismatch",
            ),
        ],
    )
    def test_each_gap_class_prints_its_line_and_the_lesson_id(self, tmp_path, capsys, keys, label, ids):
        root = _project(tmp_path)
        _lesson(root, 1, **keys)
        _lesson(root, 2)
        out = _run(root, capsys)
        assert f"  ~ {label}: 1 — {ids}\n" in out
        assert "LL-002" not in out

    def test_code_origin_with_a_code_target_is_not_reported(self, tmp_path, capsys):
        root = _project(tmp_path)
        _lesson(root, 1, origin="owned-tool", **{"promotion-target": "[rule, code]"})
        assert "code origin" not in _run(root, capsys)
        result = scan_lesson_keys(root / "planwise" / "LessonsLearned", ["test"])
        assert result.classes["origin-target-mismatch"] == []

    def test_one_none_reason_shared_by_three_lessons_is_reported(self, tmp_path, capsys):
        root = _project(tmp_path)
        for n in (1, 2, 3):
            _lesson(root, n, **{"enforced-by": '"none: no check is possible"'})
        out = _run(root, capsys)
        assert "  ~ one none: reason shared by three or more lessons: 3 — LL-001, LL-002, LL-003\n" in out

    def test_one_none_reason_shared_by_two_lessons_is_not_reported(self, tmp_path, capsys):
        root = _project(tmp_path)
        for n in (1, 2):
            _lesson(root, n, **{"enforced-by": '"none: no check is possible"'})
        out = _run(root, capsys)
        assert "shared" not in out

    def test_unfilled_template_target_is_an_unknown_target(self, tmp_path, capsys):
        root = _project(tmp_path)
        _lesson(root, 1, **{"promotion-target": "rule | code | claude-md | agent | skill | settings"})
        out = _run(root, capsys)
        assert "  ~ promotion-target: token outside the known targets: 1 — LL-001\n" in out


class TestEnforcedByForms:
    def test_quoted_and_unquoted_enforced_by_both_parse_and_neither_is_invalid(self, tmp_path, capsys):
        quoted = '"test: tests/x.py::t"'
        unquoted = "test: tests/x.py::t"
        assert parse_enforced_by(quoted) == ("test", "tests/x.py::t")
        assert parse_enforced_by(unquoted) == ("test", "tests/x.py::t")
        root = _project(tmp_path)
        _lesson(root, 1, **{"enforced-by": quoted})
        _lesson(root, 2, **{"enforced-by": unquoted})
        out = _run(root, capsys)
        assert "does not read as kind: text" not in out
        assert out.startswith("Lesson resolution keys: 2 open lessons scanned")


class TestConfiguredKinds:
    def test_a_project_kind_is_accepted_and_the_default_kinds_report_it(self, tmp_path, capsys):
        with_ci = _project(tmp_path / "with", config_extra=_KINDS_BLOCK + "  - ci\n")
        _lesson(with_ci, 1, **{"enforced-by": '"ci: pipeline job"'})
        assert "kind that config does not declare" not in _run(with_ci, capsys)

        default = _project(tmp_path / "default", config_extra=_KINDS_BLOCK)
        _lesson(default, 1, **{"enforced-by": '"ci: pipeline job"'})
        assert "  ~ enforced-by: kind that config does not declare: 1 — LL-001\n" in _run(default, capsys)

    def test_config_without_the_key_prints_the_upgrade_line(self, tmp_path, capsys):
        root = _project(tmp_path, config_extra="")
        _lesson(root, 1)
        out = _run(root, capsys)
        assert (
            "  ~ config.yaml declares no lesson_check_kinds, so the default kinds apply "
            "(hook, test, lint, script). action: run /planwise upgrade\n"
        ) in out

    def test_config_with_the_key_prints_no_upgrade_line(self, tmp_path, capsys):
        root = _project(tmp_path)
        _lesson(root, 1)
        assert _UPGRADE_LINE not in _run(root, capsys)


class TestNoLessonsFolder:
    def test_no_lessons_folder_configured_prints_the_nothing_scanned_line(self, tmp_path, capsys):
        root = _project(tmp_path, config="project:\n  name: fixture\n")
        out = _run(root, capsys)
        assert out == "Lesson resolution keys: no lessons folder is configured, nothing scanned.\n"


class TestRunDoctor:
    def test_run_doctor_prints_the_banner_and_still_returns_zero(self, tmp_path):
        cfg = ip.InitConfig(project_name="Fixture", project_root=tmp_path, plugin_root=PLUGIN_ROOT)
        config = tmp_path / "planwise" / "config.yaml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(f'plugin_version: "{cfg.plugin_version}"\n' + _CONFIG, encoding="utf-8")
        (tmp_path / "planwise" / "LessonsLearned").mkdir()
        _lesson(tmp_path, 1, origin=None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = doctor_cli._run_doctor(cfg)
        out = buf.getvalue()
        assert status == 0
        assert "planwise doctor — lesson resolution keys" in out
        assert out.index("consumer section-citation check") < out.index("lesson resolution keys")
        assert "  ~ no origin: key: 1 — LL-001" in out
