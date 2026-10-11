"""version_notice.py: one line when the config pin and the dispatching plugin differ."""
import json
import re
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
SCRIPT = PLUGIN / "scripts" / "version_notice.py"
SKILL = PLUGIN / "skills" / "planwise" / "SKILL.md"


def _run(tmp_path, pinned, shipped="1.0.5.3", config_text=None, write_config=True):
    root = tmp_path / "plugin"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "planwise", "version": shipped}), encoding="utf-8"
    )
    config = tmp_path / "planwise" / "config.yaml"
    if write_config:
        config.parent.mkdir(parents=True)
        text = config_text if config_text is not None else f'plugin_version: "{pinned}"\n'
        config.write_text(text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--config", str(config), "--plugin-root", str(root)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


def test_equal_versions_print_nothing(tmp_path):
    result = _run(tmp_path, "1.0.5.3")
    assert result.returncode == 0
    assert result.stdout == ""


def test_pinned_behind_prints_notice(tmp_path):
    result = _run(tmp_path, "1.0.5.2")
    assert result.returncode == 0
    assert result.stdout.strip() == (
        "planwise: dispatching from 1.0.5.3, config pins 1.0.5.2"
        " — run /planwise upgrade to refresh"
    )


def test_pinned_ahead_prints_reverse_notice(tmp_path):
    result = _run(tmp_path, "1.0.6")
    assert result.returncode == 0
    assert result.stdout.strip() == (
        "planwise: config pins 1.0.6, but this session is dispatching the older 1.0.5.3"
        " — update the plugin, or restart the session so the newer install dispatches"
    )
    assert "/planwise upgrade" not in result.stdout


def test_unreadable_pin_prints_nothing(tmp_path):
    result = _run(tmp_path, "abc")
    assert result.returncode == 0
    assert result.stdout == ""


def test_unreadable_shipped_version_prints_nothing(tmp_path):
    result = _run(tmp_path, "1.0.5.2", shipped="dev")
    assert result.returncode == 0
    assert result.stdout == ""


def test_fifth_component_is_compared_not_truncated(tmp_path):
    result = _run(tmp_path, "1.0.5.3.9")
    assert result.returncode == 0
    assert "config pins 1.0.5.3.9" in result.stdout
    assert "older 1.0.5.3" in result.stdout


def test_trailing_zero_components_are_equal(tmp_path):
    result = _run(tmp_path, "1.0.5.3.0")
    assert result.returncode == 0
    assert result.stdout == ""


PLANWISE_CONFIG = 'project:\n  name: "X"\nplugin_version: "1.0.0"\n'


def _write(path, text=PLANWISE_CONFIG):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_resolve_config_prefers_root_planwise_dir(tmp_path):
    import version_notice

    _write(tmp_path / "planwise" / "config.yaml")
    _write(tmp_path / "other" / "config.yaml")
    assert version_notice.resolve_config(tmp_path) == (tmp_path / "planwise" / "config.yaml").resolve()


def test_resolve_config_single_level_fallback(tmp_path):
    import version_notice

    _write(tmp_path / "docs" / "config.yaml")
    assert version_notice.resolve_config(tmp_path) == (tmp_path / "docs" / "config.yaml").resolve()


def test_resolve_config_none_when_absent_or_foreign(tmp_path):
    import version_notice

    assert version_notice.resolve_config(tmp_path) is None
    _write(tmp_path / "a" / "config.yaml", "a: 1\n")
    assert version_notice.resolve_config(tmp_path) is None


def test_resolve_config_cwd_is_the_planwise_dir(tmp_path):
    import version_notice

    config = _write(tmp_path / "planwise" / "config.yaml")
    assert version_notice.resolve_config(tmp_path / "planwise") == config.resolve()


def test_resolve_config_direct_cwd_config_wins_over_children(tmp_path):
    import version_notice

    direct = _write(tmp_path / "config.yaml")
    _write(tmp_path / "a" / "config.yaml")
    assert version_notice.resolve_config(tmp_path) == direct.resolve()


def test_resolve_config_skips_a_foreign_config_for_a_planwise_one(tmp_path):
    import version_notice

    _write(tmp_path / "a" / "config.yaml", "a: 1\n")
    real = _write(tmp_path / "b" / "config.yaml")
    assert version_notice.resolve_config(tmp_path) == real.resolve()


def test_resolve_config_agrees_with_the_list_resolver(tmp_path):
    """Same answer as list_plans.resolve_config_path(None) for each layout.

    list_plans runs in a child process: importing it reconfigures stdout.
    """
    import version_notice

    layouts = {
        "root": ["planwise/config.yaml"],
        "in-dir": ["planwise/config.yaml", "__cwd__=planwise"],
        "direct": ["config.yaml", "z/config.yaml"],
        "decoy": ["app/config.yaml", "planwise/config.yaml"],
        "siblings": ["a/config.yaml", "b/config.yaml"],
        "none": [],
    }
    probe = (
        "import sys\n"
        f"sys.path.insert(0, {str(PLUGIN / 'scripts')!r})\n"
        "import list_plans\n"
        "print(list_plans.resolve_config_path(None) or '')\n"
    )
    for name, items in layouts.items():
        root = tmp_path / name
        root.mkdir()
        cwd = root
        for item in items:
            if item.startswith("__cwd__="):
                cwd = root / item.split("=", 1)[1]
            else:
                _write(root / item)
        done = subprocess.run(
            [sys.executable, "-B", "-c", probe], capture_output=True, text=True,
            encoding="utf-8", cwd=str(cwd), check=True)
        expected = done.stdout.strip()
        found = version_notice.resolve_config(cwd)
        assert (str(found) if found else "") == expected, name


def test_missing_config_prints_nothing(tmp_path):
    result = _run(tmp_path, "1.0.5.2", write_config=False)
    assert result.returncode == 0
    assert result.stdout == ""


def test_malformed_config_prints_nothing(tmp_path):
    result = _run(tmp_path, "", config_text="plugin_version: [unclosed\n  : : {\n")
    assert result.returncode == 0
    assert result.stdout == ""


def test_default_plugin_root_is_the_dispatching_plugin(tmp_path):
    shipped = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    config = tmp_path / "planwise" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text('plugin_version: "0.0.1"\n', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--config", str(config)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0
    assert f"dispatching from {shipped}, config pins 0.0.1" in result.stdout


def test_skill_list_rule_displays_the_block_after_any_notice_line():
    text = SKILL.read_text(encoding="utf-8")
    rule = re.search(r"^1\. \*\*Block present, no fallback line\.\*\*[^\n]*", text, re.MULTILINE)
    assert rule is not None
    assert "verbatim as the whole answer, after any `planwise:` notice line" in rule.group(0)
    assert len(SKILL.read_bytes()) <= 11480


def test_skill_passes_the_injected_notice_through_before_routing_table():
    text = SKILL.read_text(encoding="utf-8")
    table = re.search(r"^\| Subcommand \| Handler \|", text, re.MULTILINE)
    assert table is not None
    before = text[: table.start()]
    assert "also prints a `planwise: " in before
    assert "verbatim" in before
    assert "version_notice.py" not in text
    assert not re.search(r"run `python[^`]*version_notice", text)
