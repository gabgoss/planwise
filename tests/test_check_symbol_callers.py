"""Tests for check_symbol_callers.py."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_symbol_callers as csc
import pytest


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    scripts = tmp_path / "plugins" / "planwise" / "scripts"
    scripts.mkdir(parents=True)
    (tmp_path / "plugins" / "planwise" / "handlers").mkdir()
    (scripts / "lib.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    sha = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return tmp_path, scripts, sha


def _run(root, sha, capsys):
    code = csc.main(["--repo", str(root), "--base", sha, "--", "plugins/planwise/scripts"])
    return code, capsys.readouterr().out


def test_called_function_is_silent(repo, capsys):
    root, scripts, sha = repo
    (scripts / "lib.py").write_text("def old():\n    return 1\n\n\ndef wired(x):\n    return x\n", encoding="utf-8")
    (scripts / "user.py").write_text("from lib import wired\n\nprint(wired(2))\n", encoding="utf-8")
    _git(root, "add", "-A")
    code, out = _run(root, sha, capsys)
    assert code == 0
    assert out.splitlines()[0] == "1 added symbols scanned"
    assert "function wired (plugins/planwise/scripts/lib.py:5): 1 call sites" in out
    assert "ZERO" not in out


def test_uncalled_function_fires(repo, capsys):
    root, scripts, sha = repo
    (scripts / "lib.py").write_text("def old():\n    return 1\n\n\ndef orphan(x):\n    return x\n", encoding="utf-8")
    code, out = _run(root, sha, capsys)
    assert code == 1
    assert "ZERO function orphan" in out


def test_same_name_call_in_an_unrelated_module_is_not_a_caller(repo, capsys):
    root, scripts, sha = repo
    (scripts / "lib.py").write_text("def old():\n    return 1\n\n\ndef orphan(x):\n    return x\n", encoding="utf-8")
    (scripts / "other.py").write_text("def orphan(x):\n    return x\n\n\norphan(1)\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "other")
    code, out = _run(root, sha, capsys)
    assert code == 1
    assert "ZERO function orphan (plugins/planwise/scripts/lib.py:5)" in out


def test_untracked_file_is_read_as_added(repo, capsys):
    root, scripts, sha = repo
    (scripts / "fresh.py").write_text("def lonely():\n    return 0\n", encoding="utf-8")
    code, out = _run(root, sha, capsys)
    assert code == 1
    assert "ZERO function lonely (plugins/planwise/scripts/fresh.py:1)" in out


def test_repo_below_the_top_level_keys_paths_from_the_top_level(repo, capsys):
    # --repo names a folder inside the repository: git diff still prints
    # top-level paths, so a same-module caller and an untracked caller count.
    root, scripts, sha = repo
    (scripts / "lib.py").write_text("def old():\n    return helper()\n\n\ndef helper():\n    return 1\n",
                                    encoding="utf-8")
    (scripts / "fresh.py").write_text("def newer():\n    return 2\n\n\nnewer()\n", encoding="utf-8")
    code = csc.main(["--repo", str(root / "plugins" / "planwise"), "--base", sha, "--", "scripts"])
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "2 added symbols scanned"
    assert "function helper (plugins/planwise/scripts/lib.py:5): 1 call sites" in out
    assert "function newer (plugins/planwise/scripts/fresh.py:1): 1 call sites" in out
    assert "ZERO" not in out
    assert code == 0


def test_test_tree_caller_is_a_false_witness(repo, capsys):
    root, scripts, sha = repo
    (scripts / "lib.py").write_text("def old():\n    return 1\n\n\ndef orphan(x):\n    return x\n", encoding="utf-8")
    tests = root / "plugins" / "planwise" / "scripts" / "tests"
    tests.mkdir()
    (tests / "helper.py").write_text("orphan(1)\n", encoding="utf-8")
    (scripts / "test_lib.py").write_text("orphan(1)\n", encoding="utf-8")
    code, out = _run(root, sha, capsys)
    assert code == 1
    assert "ZERO function orphan" in out


def test_param_needs_activating_argument(repo, capsys):
    root, scripts, sha = repo
    (scripts / "lib.py").write_text("def old(hint=None):\n    return 1\n", encoding="utf-8")
    (scripts / "user.py").write_text("from lib import old\n\nold()\n", encoding="utf-8")
    code, out = _run(root, sha, capsys)
    assert code == 1
    assert "ZERO param old(hint=)" in out
    (scripts / "user.py").write_text("from lib import old\n\nold(hint=3)\n", encoding="utf-8")
    code, out = _run(root, sha, capsys)
    assert code == 0
    assert "param old(hint=)" in out


def test_flag_needs_an_invocation_naming_the_script(repo, capsys):
    root, scripts, sha = repo
    (scripts / "tool.py").write_text('import argparse\np = argparse.ArgumentParser()\np.add_argument("--deep")\n',
                                     encoding="utf-8")
    code, out = _run(root, sha, capsys)
    assert code == 1
    assert "ZERO flag --deep" in out
    handler = root / "plugins" / "planwise" / "handlers" / "h.md"
    handler.write_text("Run `python -B {plugin_root}/scripts/tool.py --deep`.\n", encoding="utf-8")
    code, out = _run(root, sha, capsys)
    assert code == 0
    assert "plugins/planwise/handlers/h.md:1" in out


def test_config_key_read(repo, capsys):
    root, scripts, sha = repo
    (scripts / "cfg.py").write_text('def load(c):\n    return c.get("deep_mode")\n', encoding="utf-8")
    (scripts / "user.py").write_text("from cfg import load\nload({})\n", encoding="utf-8")
    code, out = _run(root, sha, capsys)
    assert code == 1
    assert "ZERO config-key deep_mode" in out


def test_empty_diff_reads_zero_scanned(repo, capsys):
    root, _, sha = repo
    code, out = _run(root, sha, capsys)
    assert code == 0
    assert out.splitlines() == ["0 added symbols scanned"]


def test_bad_base_exits_two(repo, capsys):
    root, _, _ = repo
    assert csc.main(["--repo", str(root), "--base", "0" * 40, "--", "plugins/planwise/scripts"]) == 2
    assert capsys.readouterr().err.startswith("Error:")


def test_paths_are_required():
    with pytest.raises(SystemExit) as info:
        csc.main(["--repo", ".", "--base", "HEAD"])
    assert info.value.code == 2


def test_modified_def_reports_only_the_new_parameter():
    diff = (
        "+++ b/s/a.py\n@@ -1,1 +1,1 @@\n-def f(a, b=1):\n+def f(a, b=1, c=2):\n"
    )
    labels = [s.label() for s in csc.parse_diff(diff)]
    assert labels == ["param f(c=)"]
