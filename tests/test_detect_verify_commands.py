"""Tests for scripts/detect_verify_commands.py: each signal, the confidence rule, and read-only behaviour."""

import builtins
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import detect_verify_commands as dvc

# The directory the imported module actually lives in, so file-reading tests follow the import.
SCRIPTS_DIR = Path(dvc.__file__).resolve().parent

PYPROJECT = (
    "[project]\nname = \"demo\"\n\n"
    "[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n\n"
    "[tool.ruff]\nline-length = 100\n"
)


def run(root: Path, capsys) -> "list[dict]":
    """Run the CLI entry point in process and return the printed rows."""
    code = dvc.main(["--root", str(root)])
    assert code == 0
    out = capsys.readouterr().out
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def by_command(rows: "list[dict]") -> "dict[str, dict]":
    return {row["command"]: row for row in rows}


@pytest.fixture
def on_path():
    """Make every executable resolve, so a high confidence needs only the signal."""
    with mock.patch.object(dvc.shutil, "which", side_effect=lambda name: f"/bin/{name}"):
        yield


def test_pyproject_prints_one_test_and_one_lint_candidate(tmp_path, capsys, on_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    rows = run(tmp_path, capsys)
    assert [(r["kind"], r["source"]) for r in rows] == [("test", "pyproject.toml"), ("lint", "pyproject.toml")]
    assert [r["command"] for r in rows] == ["pytest", "ruff check ."]
    assert {r["confidence"] for r in rows} == {"high"}


def test_each_row_is_one_json_line_with_the_four_keys_in_order(tmp_path, capsys, on_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    dvc.main(["--root", str(tmp_path)])
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    for line in lines:
        assert list(json.loads(line)) == ["command", "kind", "source", "confidence"]


def test_empty_directory_prints_nothing_and_exits_zero(tmp_path, capsys):
    assert dvc.main(["--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_cli_on_an_empty_directory_prints_nothing_and_exits_zero(tmp_path):
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS_DIR / "detect_verify_commands.py"), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_root_that_is_not_a_directory_exits_one(tmp_path, capsys):
    assert dvc.main(["--root", str(tmp_path / "missing")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not a directory" in captured.err


def test_unresolved_executable_lowers_confidence(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    with mock.patch.object(dvc.shutil, "which", return_value=None):
        rows = run(tmp_path, capsys)
    assert {r["confidence"] for r in rows} == {"low"}
    assert len(rows) == 2


def test_only_the_missing_tool_drops_to_low(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    with mock.patch.object(dvc.shutil, "which", side_effect=lambda name: "/bin/pytest" if name == "pytest" else None):
        rows = by_command(run(tmp_path, capsys))
    assert rows["pytest"]["confidence"] == "high"
    assert rows["ruff check ."]["confidence"] == "low"


@pytest.mark.parametrize(
    ("name", "body", "command", "kind"),
    [
        ("pytest.ini", "[pytest]\ntestpaths = tests\n", "pytest", "test"),
        ("setup.cfg", "[tool:pytest]\naddopts = -q\n", "pytest", "test"),
        ("setup.cfg", "[flake8]\nmax-line-length = 100\n", "flake8", "lint"),
        ("ruff.toml", "line-length = 100\n", "ruff check .", "lint"),
        (".ruff.toml", "line-length = 100\n", "ruff check .", "lint"),
        (".flake8", "[flake8]\nmax-line-length = 100\n", "flake8", "lint"),
        ("Cargo.toml", "[package]\nname = \"x\"\n", "cargo test", "test"),
    ],
)
def test_config_signal_gives_a_high_candidate(tmp_path, capsys, on_path, name, body, command, kind):
    (tmp_path / name).write_text(body, encoding="utf-8")
    rows = run(tmp_path, capsys)
    assert rows == [{"command": command, "kind": kind, "source": name, "confidence": "high"}]


def test_go_mod_gives_test_and_vet(tmp_path, capsys, on_path):
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    rows = run(tmp_path, capsys)
    assert [(r["command"], r["kind"]) for r in rows] == [("go test ./...", "test"), ("go vet ./...", "lint")]


def test_package_json_scripts(tmp_path, capsys, on_path):
    scripts = {"scripts": {"test": "jest", "lint": "eslint ."}}
    (tmp_path / "package.json").write_text(json.dumps(scripts), encoding="utf-8")
    rows = by_command(run(tmp_path, capsys))
    assert rows["npm test"]["kind"] == "test"
    assert rows["npm run lint"]["kind"] == "lint"
    assert rows["npm test"]["source"] == "package.json"


def test_package_json_skips_the_npm_init_placeholder(tmp_path, capsys, on_path):
    placeholder = 'echo "Error: no test specified" && exit 1'
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": placeholder}}), encoding="utf-8")
    assert run(tmp_path, capsys) == []


def test_malformed_package_json_prints_nothing(tmp_path, capsys, on_path):
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    assert run(tmp_path, capsys) == []


def test_dotnet_signal_is_always_low(tmp_path, capsys, on_path):
    (tmp_path / "App.csproj").write_text("<Project />\n", encoding="utf-8")
    (tmp_path / "App.sln").write_text("\n", encoding="utf-8")
    rows = run(tmp_path, capsys)
    assert rows == [{"command": "dotnet test", "kind": "test", "source": "App.csproj", "confidence": "low"}]


def test_makefile_targets_are_low(tmp_path, capsys, on_path):
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n\nlint:\n\truff .\n\ncheck: test lint\n", encoding="utf-8")
    rows = by_command(run(tmp_path, capsys))
    assert {row["confidence"] for row in rows.values()} == {"low"}
    assert (rows["make test"]["kind"], rows["make lint"]["kind"], rows["make check"]["kind"]) == (
        "test",
        "lint",
        "other",
    )


def test_ci_run_lines_keep_tests_and_lints_and_drop_installs(tmp_path, capsys, on_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n  build:\n    steps:\n"
        "      - run: python -m pip install -r requirements.txt\n"
        "      - run: python -m pytest -q\n"
        "      - name: Lint\n        run: ruff check src\n"
        "      - run: echo done\n"
        "      - run: |\n          make everything\n",
        encoding="utf-8",
    )
    rows = run(tmp_path, capsys)
    assert [(r["command"], r["kind"], r["confidence"]) for r in rows] == [
        ("python -m pytest -q", "test", "low"),
        ("ruff check src", "lint", "low"),
    ]
    assert {r["source"] for r in rows} == {".github/workflows/ci.yml"}


def test_a_command_named_by_two_sources_prints_once_with_the_first_source(tmp_path, capsys, on_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    rows = run(tmp_path, capsys)
    assert [r["command"] for r in rows].count("pytest") == 1
    assert by_command(rows)["pytest"]["source"] == "pyproject.toml"


def test_pyproject_without_the_tool_tables_prints_nothing(tmp_path, capsys, on_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"demo\"\n", encoding="utf-8")
    assert run(tmp_path, capsys) == []


WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def test_detector_opens_nothing_for_writing_and_starts_no_subprocess(tmp_path):
    """Run every signal reader with open, os.open and Popen patched, and assert no write and no process."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}}), encoding="utf-8")
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    (tmp_path / "App.csproj").write_text("<Project />\n", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("steps:\n  - run: pytest\n", encoding="utf-8")

    real_open = builtins.open
    real_os_open = os.open
    opened: list[str] = []
    os_opened: list[int] = []

    def spy_open(file, mode="r", *args, **kwargs):
        opened.append(mode)
        return real_open(file, mode, *args, **kwargs)

    def spy_os_open(path, flags, *args, **kwargs):
        os_opened.append(flags)
        return real_os_open(path, flags, *args, **kwargs)

    with (
        mock.patch("builtins.open", side_effect=spy_open),
        mock.patch("os.open", side_effect=spy_os_open),
        mock.patch("subprocess.Popen", side_effect=AssertionError("the detector started a subprocess")) as popen,
    ):
        rows = dvc.detect(tmp_path)

    assert rows, "the fixture holds signals, so a vacuous run would hide a blind detector"
    assert opened, "the read helper must reach the patched open"
    assert all(set(mode) <= set("rbt") and "w" not in mode and "a" not in mode and "+" not in mode for mode in opened)
    assert all(flags & WRITE_FLAGS == 0 for flags in os_opened)
    popen.assert_not_called()


def test_detector_leaves_the_tree_unchanged(tmp_path, capsys, on_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    before = sorted((p.name, p.stat().st_size) for p in tmp_path.rglob("*"))
    run(tmp_path, capsys)
    assert sorted((p.name, p.stat().st_size) for p in tmp_path.rglob("*")) == before


def test_script_carries_no_bookkeeping_identifier():
    import re

    text = (SCRIPTS_DIR / "detect_verify_commands.py").read_text(encoding="utf-8")
    assert re.search(r"(LL-[0-9]|BB-[0-9]|BLI-[0-9]|PLG-[0-9]|\bD-[0-9]|Sprint-[0-9]|Session-[0-9])", text) is None
