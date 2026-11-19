"""Tests for scripts/set_verify_commands.py: each config state, the comment-keeping insert, and the checked write."""

import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import config_loader
import set_verify_commands as svc

# The directory the imported module actually lives in, so file-reading tests follow the import.
SCRIPTS_DIR = Path(svc.__file__).resolve().parent

CMDS = ["python -m ruff check .", "python -m pytest -q"]


def write(tmp_path: Path, text: str) -> Path:
    """Write the config as bytes, so the fixture holds exactly the text given."""
    path = tmp_path / "config.yaml"
    path.write_bytes(text.encode("utf-8"))
    return path


def set_commands(path: Path, commands: "list[str]") -> int:
    argv = ["--config", str(path)]
    for command in commands:
        argv += ["--command", command]
    return svc.main(argv)


def loaded_verify(path: Path):
    config = config_loader.load_config(config_path=path)
    return config["build_commands"]["verify"]


def test_empty_list_is_filled_and_round_trips_through_the_loader(tmp_path):
    path = write(tmp_path, "project:\n  name: demo\nbuild_commands:\n  default: make\n  verify: []\nplugin_version: \"1\"\n")
    assert set_commands(path, CMDS) == 0
    assert loaded_verify(path) == CMDS
    config = config_loader.load_config(config_path=path)
    assert config["build_commands"]["default"] == "make"
    assert config["plugin_version"] == "1"


def test_bare_verify_key_is_filled(tmp_path):
    path = write(tmp_path, "build_commands:\n  verify:\nother: 1\n")
    assert set_commands(path, CMDS) == 0
    assert loaded_verify(path) == CMDS
    assert config_loader.load_config(config_path=path)["other"] == 1


def test_non_empty_list_leaves_the_file_byte_identical(tmp_path, capsys):
    original = "build_commands:\n  verify:\n    - keep me   # note\nother: 1\n"
    path = write(tmp_path, original)
    before = path.read_bytes()
    assert set_commands(path, CMDS) == 0
    assert path.read_bytes() == before
    assert "already holds commands" in capsys.readouterr().out


def test_non_empty_flow_list_is_left_alone(tmp_path):
    path = write(tmp_path, "build_commands:\n  verify: [a, b]\n")
    before = path.read_bytes()
    assert set_commands(path, CMDS) == 0
    assert path.read_bytes() == before


def test_block_without_verify_gets_the_key_and_keeps_every_comment(tmp_path):
    original = (
        "# top comment\n"
        "project:\n  name: demo   # name comment\n\n"
        "build_commands:\n"
        "  # about default\n"
        "  default: make   # run all\n"
        "plugin_root: x\n"
        "# tail comment\n"
    )
    path = write(tmp_path, original)
    assert set_commands(path, CMDS) == 0
    text = path.read_text(encoding="utf-8")
    for comment in ("# top comment", "# name comment", "# about default", "# run all", "# tail comment"):
        assert comment in text
    assert loaded_verify(path) == CMDS
    config = config_loader.load_config(config_path=path)
    assert config["build_commands"]["default"] == "make"
    assert config["plugin_root"] == "x"
    assert text.index("verify:") < text.index("plugin_root")


def test_block_at_end_of_file_without_a_trailing_newline(tmp_path):
    path = write(tmp_path, "build_commands:\n  default: make")
    assert set_commands(path, CMDS) == 0
    assert loaded_verify(path) == CMDS


def test_missing_block_is_appended(tmp_path):
    path = write(tmp_path, "project:\n  name: demo\n")
    assert set_commands(path, CMDS) == 0
    assert loaded_verify(path) == CMDS
    assert config_loader.load_config(config_path=path)["project"]["name"] == "demo"


def test_verify_key_nested_deeper_is_not_mistaken_for_the_block_key(tmp_path):
    path = write(tmp_path, "build_commands:\n  extra:\n    verify: x\n")
    assert set_commands(path, CMDS) == 0
    config = config_loader.load_config(config_path=path)
    assert config["build_commands"]["verify"] == CMDS
    assert config["build_commands"]["extra"] == {"verify": "x"}


def test_four_space_block_keeps_its_indent(tmp_path):
    path = write(tmp_path, "build_commands:\n    default: make\n")
    assert set_commands(path, CMDS) == 0
    assert loaded_verify(path) == CMDS
    assert "    verify:\n      - python -m ruff check ." in path.read_text(encoding="utf-8")


def test_zero_commands_write_nothing(tmp_path, capsys):
    path = write(tmp_path, "build_commands:\n  verify: []\n")
    before = path.read_bytes()
    with mock.patch.object(svc, "write_config_checked") as writer:
        assert set_commands(path, []) == 0
    writer.assert_not_called()
    assert path.read_bytes() == before
    assert "nothing written" in capsys.readouterr().out


def test_blank_commands_count_as_zero(tmp_path):
    path = write(tmp_path, "build_commands:\n  verify: []\n")
    before = path.read_bytes()
    assert set_commands(path, ["", "   "]) == 0
    assert path.read_bytes() == before


def test_repeated_command_is_written_once(tmp_path):
    path = write(tmp_path, "build_commands:\n  verify: []\n")
    assert set_commands(path, ["pytest", "pytest", "ruff check ."]) == 0
    assert loaded_verify(path) == ["pytest", "ruff check ."]


@pytest.mark.parametrize(
    "command",
    ["echo a: b", "echo # not a comment", "'quoted' start", "[bracket] first", "- dash first", "ends with colon:", "it's here: yes"],
)
def test_command_a_plain_scalar_cannot_hold_is_quoted_and_round_trips(tmp_path, command):
    path = write(tmp_path, "build_commands:\n  verify: []\n")
    assert set_commands(path, [command]) == 0
    assert loaded_verify(path) == [command]


def test_command_with_a_line_break_is_refused(tmp_path, capsys):
    path = write(tmp_path, "build_commands:\n  verify: []\n")
    before = path.read_bytes()
    assert set_commands(path, ["a\nb"]) == 2
    assert path.read_bytes() == before
    assert "line break" in capsys.readouterr().err


def test_inline_build_commands_mapping_is_refused_unchanged(tmp_path, capsys):
    path = write(tmp_path, "build_commands: {default: make}\n")
    before = path.read_bytes()
    assert set_commands(path, CMDS) == 1
    assert path.read_bytes() == before
    assert "not a block mapping" in capsys.readouterr().err


def test_missing_config_exits_one(tmp_path, capsys):
    assert set_commands(tmp_path / "config.yaml", CMDS) == 1
    assert "not found" in capsys.readouterr().err
    assert not (tmp_path / "config.yaml").exists()


def test_result_that_does_not_parse_is_refused_through_the_checked_writer(tmp_path, capsys):
    """A splice that breaks the YAML is rolled back by write_config_checked, and the writer exits 1."""
    if not config_loader.HAS_YAML:
        pytest.skip("the parse check needs PyYAML")
    original = "build_commands:\n  default: make\n"
    path = write(tmp_path, original)
    with mock.patch.object(svc, "splice_verify", return_value=("build_commands: [\n", "written")):
        assert set_commands(path, CMDS) == 1
    # The checked writer restores through text mode, so the comparison is on text, not on line-ending bytes.
    assert path.read_text(encoding="utf-8") == original
    assert "does not parse" in capsys.readouterr().err


def test_write_goes_through_write_config_checked(tmp_path):
    path = write(tmp_path, "build_commands:\n  verify: []\n")
    with mock.patch.object(svc, "write_config_checked", wraps=svc.write_config_checked) as writer:
        assert set_commands(path, CMDS) == 0
    assert writer.call_count == 1
    assert loaded_verify(path) == CMDS


def test_cli_runs_from_the_scripts_folder_entry_point(tmp_path):
    path = write(tmp_path, "build_commands:\n  verify: []\n")
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS_DIR / "set_verify_commands.py"), "--config", str(path), "--command", "pytest"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert loaded_verify(path) == ["pytest"]


def test_script_carries_no_bookkeeping_identifier():
    text = (SCRIPTS_DIR / "set_verify_commands.py").read_text(encoding="utf-8")
    assert re.search(r"(LL-[0-9]|BB-[0-9]|BLI-[0-9]|PLG-[0-9]|\bD-[0-9]|Sprint-[0-9]|Session-[0-9])", text) is None
