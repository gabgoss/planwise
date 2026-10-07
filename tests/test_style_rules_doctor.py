#!/usr/bin/env python3
"""Doctor-side tests for the always-on style rules (Stage 23).

Covers the six states of `lint_style_rules`, the report lines of
`format_style_report`, the read-only stage `run_style_stage`, the reworded
over-scope message in `doctor_cli.py`, and the seam that calls the stage from
`doctor_cli._run_doctor`. The install and upgrade side lives in
`tests/test_style_rules.py`.

The stage reads `~/.claude/rules/` through `Path.home()`. The autouse fixture
`_isolated_home` in `tests/conftest.py` redirects `Path.home()`, `HOME` and
`USERPROFILE` to a fresh directory for every test, so each test here takes its
home from `Path.home()` and adds no redirect of its own. One test asserts that
the redirect lands under pytest's temp root.

`_run_doctor` is never called, because it runs stages that may probe the live
CLI. `doctor_cli` is imported to read its source text only. None of these tests
reads `init_project.INSTALLED_RULES`.

Run with:  python -m pytest -q tests/test_style_rules_doctor.py
"""

import ast
import hashlib
import inspect
import math
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip

# isort: split
import doctor_cli
import style_rules as sr
import upgrade_io

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
REFERENCES = PLUGIN_ROOT / "references"

LANGUAGE = "plain-language.md"
PRESENTATION = "plain-presentation.md"
BOTH = [LANGUAGE, PRESENTATION]
BYTES_PER_TOKEN = 2.6

needs_yaml = unittest.skipUnless(upgrade_io.HAS_YAML, "the style: block is read through PyYAML")

# The strings below are copied from the report spec, never computed from the code under test.
COPIES_TAIL = "Delete all but one. The rule costs its tokens once per copy until you do."
CUSTOMIZED_LINE = (
    "  The installed copy differs from the shipped file. Doctor treats it as your customization, not an error."
)
MISSING_LINE = "  The key is on but no copy is installed. Run /planwise upgrade."
OFF_LINE = "  The key is off. Confirm this is intended."
MISMATCH_LINE = (
    "  The key is off but a copy is installed. Run /planwise upgrade to remove an untouched copy."
)
MISMATCH_EDITED_LINE = (
    "  The key is off but the installed copy differs from the shipped file. "
    "Upgrade keeps an edited copy. Delete it by hand if you no longer want it."
)
MISMATCH_SYMLINK_LINE = (
    "  The key is off but the installed copy is a symlink. "
    "Upgrade does not remove a symlink. Delete it by hand."
)
ALSO_LOADS_LINE = "  Upgrade installs the rule. Copies that will also load: {}."
STILL_LOAD_LINE = "  Other copies still load: {}. Upgrade does not remove them."
FAILED_LINE = "Style rules: the check failed: {}"


def _shipped_lf(filename: str) -> bytes:
    """The shipped rule with LF line endings, whatever the working tree stores."""
    return (REFERENCES / filename).read_bytes().replace(b"\r\n", b"\n")


def _edited(filename: str, tag: str = "A") -> bytes:
    """The shipped rule plus one team line, which counts as a user edit."""
    return _shipped_lf(filename) + f"\nTeam addition {tag}: always cite the ticket.\n".encode()


def _paths_only(filename: str) -> bytes:
    """The shipped rule with only a `paths:` line added to its frontmatter."""
    text = _shipped_lf(filename)
    assert text.startswith(b"---\n"), "the shipped rule is expected to carry frontmatter"
    return text.replace(b"---\n", b'---\npaths: "src/**"\n', 1)


def _stale_subset(filename: str) -> bytes:
    """The shipped rule cut before one whole section, so every block left is shipped text."""
    return _shipped_lf(filename).split(b"\n## Honesty")[0] + b"\n"


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _setup_env(case: unittest.TestCase) -> None:
    """A temp project next to the redirected home, on `case`.

    The home comes from `Path.home()`, which the autouse fixture redirects.
    """
    case.tmp = Path(tempfile.mkdtemp(prefix="srd_doctor_"))
    case.addCleanup(shutil.rmtree, case.tmp, ignore_errors=True)
    case.project_root = case.tmp / "project"
    case.project_root.mkdir()
    case.home = Path.home()
    case.cfg = _make_cfg(case.project_root)


def _make_cfg(project_root: Path, scope: str = "project"):
    """A config over the temp project and the REAL plugin tree."""
    return ip.InitConfig(
        project_name="DoctorStyleFixture",
        project_root=project_root,
        plugin_root=PLUGIN_ROOT,
        install_scope=scope,
    )


def _write_config(case: unittest.TestCase, text: str) -> Path:
    config_dir = case.project_root / case.cfg.planwise_root
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "config.yaml"
    path.write_bytes(text.encode("utf-8"))
    return path


def _project_managed(case: unittest.TestCase, filename: str) -> Path:
    return case.project_root / ".claude" / "rules" / "planwise" / filename


def _home_managed(case: unittest.TestCase, filename: str) -> Path:
    return case.home / ".claude" / "rules" / "planwise" / filename


def _by_name(results: list[dict], filename: str) -> dict:
    return next(r for r in results if r["filename"] == filename)


def _tree_hash(*roots: Path) -> tuple[list[str], str]:
    """The sorted file list and one SHA-256 over every path and byte under `roots`."""
    digest = hashlib.sha256()
    files: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            rel = f"{root.name}/{path.relative_to(root).as_posix()}"
            digest.update(rel.encode("utf-8"))
            if path.is_file():
                files.append(rel)
                digest.update(path.read_bytes())
    return files, digest.hexdigest()


def _result(**overrides) -> dict:
    """A `lint_style_rules` result built by hand, for the formatter tests."""
    base = {
        "filename": LANGUAGE, "key": "plain_language", "enabled": True, "present": True,
        "state": "OK", "bytes": 1040, "lines": 20, "tokens": 400,
        "path": "/proj/.claude/rules/planwise/plain-language.md", "duplicate_paths": [],
        "conflict": False, "symlinks": [], "loading_tokens": 400,
        "other_path": "/home/.claude/rules/planwise/plain-language.md",
        "verdict": "identical",
    }
    base.update(overrides)
    # The ordered loading paths follow from the managed path and the duplicates, unless a test sets them.
    base.setdefault("loading_paths", ([base["path"]] if base["present"] else []) + list(base["duplicate_paths"]))
    return base


class TestLintStyleRules(unittest.TestCase):
    """`lint_style_rules`: one result per rule, with its state and size."""

    @pytest.fixture(autouse=True)
    def _pytest_temp_root(self, tmp_path_factory):
        self.pytest_temp_root = tmp_path_factory.getbasetemp().resolve()

    def setUp(self):
        _setup_env(self)

    def lint(self, filename: str = LANGUAGE, cfg=None) -> dict:
        return _by_name(sr.lint_style_rules(cfg or self.cfg), filename)

    # -- the redirected home --------------------------------------------------

    def test_path_home_resolves_under_the_pytest_temp_root(self):
        self.assertTrue(Path.home().resolve().is_relative_to(self.pytest_temp_root))
        self.assertTrue(self.home.resolve().is_relative_to(self.pytest_temp_root))
        self.assertFalse(self.project_root.resolve().is_relative_to(self.home.resolve()))

    # -- one test per state ---------------------------------------------------

    def test_ok_when_the_managed_copy_matches_the_shipped_file(self):
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "OK")
        self.assertTrue(result["present"])
        self.assertEqual(result["duplicate_paths"], [])
        self.assertFalse(result["conflict"])

    def test_ok_with_an_external_copy_and_no_managed_copy(self):
        external = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "OK")
        self.assertFalse(result["present"])
        self.assertEqual(result["duplicate_paths"], [str(external)])

    def test_duplicate_for_a_top_level_copy_in_the_project(self):
        external = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "DUPLICATE")
        self.assertEqual(result["duplicate_paths"], [str(external)])

    def test_duplicate_for_a_copy_in_a_project_subdirectory(self):
        nested = _write(self.project_root / ".claude" / "rules" / "team" / LANGUAGE, _shipped_lf(LANGUAGE))
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "DUPLICATE")
        self.assertEqual(result["duplicate_paths"], [str(nested)])

    def test_duplicate_for_a_copy_in_a_subdirectory_of_the_home_rules_tree(self):
        nested = _write(self.home / ".claude" / "rules" / "team" / LANGUAGE, _shipped_lf(LANGUAGE))
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "DUPLICATE")
        self.assertEqual(result["duplicate_paths"], [str(nested)])

    def test_duplicate_for_the_other_scopes_managed_copy_beside_an_installed_copy(self):
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        other = _write(_home_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "DUPLICATE")
        self.assertEqual(result["duplicate_paths"], [str(other)])
        self.assertEqual(result["other_path"], str(other))

    def test_duplicate_lists_every_path_when_three_copies_load(self):
        top = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        nested = _write(self.home / ".claude" / "rules" / "team" / LANGUAGE, _shipped_lf(LANGUAGE))
        managed = _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "DUPLICATE")
        self.assertEqual(result["duplicate_paths"], sorted([str(top), str(nested)]))
        loading = [result["path"], *result["duplicate_paths"]]
        self.assertEqual(len(loading), 3)
        self.assertEqual(result["path"], str(managed))
        per_copy = math.ceil(len(_shipped_lf(LANGUAGE)) / BYTES_PER_TOKEN)
        self.assertEqual(result["loading_tokens"], 3 * per_copy)

    def test_customized_when_the_managed_copy_carries_an_edit(self):
        _write(_project_managed(self, LANGUAGE), _edited(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "CUSTOMIZED")
        self.assertTrue(result["present"])

    def test_customized_when_only_the_paths_line_differs(self):
        _write(_project_managed(self, LANGUAGE), _paths_only(LANGUAGE))
        self.assertEqual(self.lint()["state"], "CUSTOMIZED")

    def test_missing_when_the_key_is_on_and_nothing_is_installed(self):
        result = self.lint()
        self.assertEqual(result["state"], "MISSING")
        self.assertFalse(result["present"])
        self.assertEqual(result["duplicate_paths"], [])
        self.assertEqual(result["loading_tokens"], 0)

    @needs_yaml
    def test_off_when_the_key_is_off_and_nothing_is_installed(self):
        _write_config(self, "style:\n  plain_language: off\n")
        result = self.lint()
        self.assertEqual(result["state"], "OFF")
        self.assertFalse(result["enabled"])
        self.assertEqual(result["duplicate_paths"], [])
        self.assertEqual(result["symlinks"], [])
        self.assertFalse(result["conflict"])
        self.assertEqual(result["other_path"], "")
        self.assertEqual(result["loading_tokens"], 0)
        self.assertEqual(self.lint(PRESENTATION)["state"], "MISSING")

    @needs_yaml
    def test_mismatch_when_the_key_is_off_and_an_identical_copy_is_installed(self):
        _write_config(self, "style:\n  plain_language: off\n")
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "MISMATCH")
        self.assertTrue(result["present"])
        self.assertEqual(result["duplicate_paths"], [])
        self.assertEqual(result["symlinks"], [])
        self.assertEqual(result["loading_tokens"], math.ceil(len(_shipped_lf(LANGUAGE)) / BYTES_PER_TOKEN))

    @needs_yaml
    def test_mismatch_when_the_key_is_off_and_an_edited_copy_is_installed(self):
        _write_config(self, "style:\n  plain_language: off\n")
        _write(_project_managed(self, LANGUAGE), _edited(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "MISMATCH")
        self.assertTrue(result["present"])

    # -- scope, sizes and line endings ----------------------------------------

    def test_user_scope_reads_the_installed_copy_from_the_redirected_home(self):
        user_cfg = _make_cfg(self.project_root, "user")
        managed = _write(_home_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result = self.lint(cfg=user_cfg)
        self.assertEqual(result["path"], str(managed))
        self.assertTrue(result["present"])
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["other_path"], str(_project_managed(self, LANGUAGE)))

    def test_sizes_describe_the_installed_copy_when_it_is_present(self):
        data = _edited(LANGUAGE)
        _write(_project_managed(self, LANGUAGE), data)
        result = self.lint()
        self.assertEqual(result["bytes"], len(data))
        self.assertEqual(result["lines"], len(data.splitlines()))
        self.assertEqual(result["tokens"], math.ceil(len(data) / BYTES_PER_TOKEN))

    def test_sizes_describe_the_shipped_file_when_the_copy_is_absent(self):
        data = (REFERENCES / LANGUAGE).read_bytes()
        result = self.lint()
        self.assertEqual(result["bytes"], len(data))
        self.assertEqual(result["lines"], len(data.splitlines()))
        self.assertEqual(result["tokens"], math.ceil(len(data) / BYTES_PER_TOKEN))

    def test_tokens_equal_ceil_of_bytes_over_2_6_for_every_rule(self):
        for filename in BOTH:
            with self.subTest(filename=filename):
                result = self.lint(filename)
                self.assertGreater(result["bytes"], 0)
                self.assertEqual(result["tokens"], math.ceil(result["bytes"] / BYTES_PER_TOKEN))

    def test_crlf_and_lf_copies_of_the_same_text_both_count_as_identical(self):
        lf = _shipped_lf(LANGUAGE)
        for label, data in (("lf", lf), ("crlf", lf.replace(b"\n", b"\r\n"))):
            with self.subTest(endings=label):
                _write(_project_managed(self, LANGUAGE), data)
                self.assertEqual(self.lint()["state"], "OK")

    # -- conflict -------------------------------------------------------------

    def test_conflict_is_true_when_both_managed_copies_carry_different_edits(self):
        _write(_project_managed(self, LANGUAGE), _edited(LANGUAGE, "A"))
        _write(_home_managed(self, LANGUAGE), _edited(LANGUAGE, "B"))
        result = self.lint()
        self.assertTrue(result["conflict"])
        self.assertEqual(result["state"], "DUPLICATE")

    def test_conflict_is_false_when_both_managed_copies_carry_the_same_edits(self):
        _write(_project_managed(self, LANGUAGE), _edited(LANGUAGE, "A"))
        _write(_home_managed(self, LANGUAGE), _edited(LANGUAGE, "A"))
        result = self.lint()
        self.assertFalse(result["conflict"])
        self.assertEqual(result["state"], "DUPLICATE")

    def test_conflict_is_false_when_a_copy_outside_the_managed_paths_differs(self):
        _write(_project_managed(self, LANGUAGE), _edited(LANGUAGE, "A"))
        _write(self.project_root / ".claude" / "rules" / LANGUAGE, _edited(LANGUAGE, "B"))
        result = self.lint()
        self.assertFalse(result["conflict"])
        self.assertEqual(result["state"], "DUPLICATE")

    # -- symlinks -------------------------------------------------------------

    def test_symlinks_lists_a_symlinked_copy(self):
        linked = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        real = Path.is_symlink

        def fake(path):
            # A real symlink needs a Windows privilege, so fake the check.
            return path == linked or real(path)

        with mock.patch.object(Path, "is_symlink", fake):
            result = self.lint()
        self.assertEqual(result["symlinks"], [str(linked)])
        self.assertEqual(self.lint()["symlinks"], [])

    # -- doctor predicts what upgrade does on the same tree -------------------

    def _report(self, filename: str = LANGUAGE, cfg=None) -> tuple[dict, list[str]]:
        """The result and its printable lines, from the first line of the rule's own report."""
        result = self.lint(filename, cfg)
        lines = sr.format_style_report([result])
        return result, lines

    def _upgrade_row(self, cfg=None, filename: str = LANGUAGE) -> tuple[str, str]:
        rows = sr.reconcile_style_switches(cfg or self.cfg, "1.0.0", "1.0.1")
        return next((disposition, detail) for name, disposition, detail in rows if name == filename)

    def test_user_scope_with_only_a_project_copy_is_missing_and_lists_the_copy(self):
        user_cfg = _make_cfg(self.project_root, "user")
        project_copy = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        result, lines = self._report(cfg=user_cfg)
        self.assertEqual(result["state"], "MISSING")
        self.assertFalse(result["present"])
        self.assertEqual(result["duplicate_paths"], [str(project_copy)])
        self.assertEqual(result["loading_tokens"], math.ceil(len(_shipped_lf(LANGUAGE)) / BYTES_PER_TOKEN))
        self.assertIn("copy=absent state=MISSING", lines[0])
        self.assertEqual(lines[1], MISSING_LINE)
        self.assertEqual(lines[2], ALSO_LOADS_LINE.format(project_copy))
        # Upgrade installs the global copy, as the doctor line says.
        self.assertEqual(self._upgrade_row(user_cfg)[0], "installed")
        self.assertTrue(_home_managed(self, LANGUAGE).is_file())

    def test_user_scope_with_a_home_copy_outside_the_managed_directory_is_ok_external(self):
        user_cfg = _make_cfg(self.project_root, "user")
        home_copy = _write(self.home / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        result = self.lint(cfg=user_cfg)
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["duplicate_paths"], [str(home_copy)])
        self.assertEqual(self._upgrade_row(user_cfg)[0], "duplicate")
        self.assertFalse(_home_managed(self, LANGUAGE).exists())

    def test_project_scope_with_only_a_project_copy_is_ok_external_and_upgrade_installs_nothing(self):
        external = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["duplicate_paths"], [str(external)])
        self.assertEqual(self._upgrade_row()[0], "duplicate")
        self.assertFalse(_project_managed(self, LANGUAGE).exists())

    @needs_yaml
    def test_a_key_that_is_off_still_lists_and_counts_a_copy_in_the_other_scope(self):
        _write_config(self, "style:\n  plain_language: off\n")
        other = _write(_home_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result, lines = self._report()
        self.assertEqual(result["state"], "OFF")
        self.assertEqual(result["duplicate_paths"], [str(other)])
        self.assertEqual(result["loading_tokens"], math.ceil(len(_shipped_lf(LANGUAGE)) / BYTES_PER_TOKEN))
        self.assertFalse(result["conflict"])
        self.assertEqual(lines[1], OFF_LINE)
        self.assertEqual(lines[2], STILL_LOAD_LINE.format(other))
        disposition, detail = self._upgrade_row()
        self.assertEqual(disposition, "skipped")
        self.assertIn(f"other copies still load: {other}", detail)

    @needs_yaml
    def test_a_mismatch_line_is_followed_by_the_copies_that_still_load(self):
        _write_config(self, "style:\n  plain_language: off\n")
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        top = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        nested = _write(self.home / ".claude" / "rules" / "team" / LANGUAGE, _shipped_lf(LANGUAGE))
        result, lines = self._report()
        self.assertEqual(result["state"], "MISMATCH")
        self.assertEqual(result["duplicate_paths"], sorted([str(top), str(nested)]))
        self.assertEqual(result["loading_tokens"], 3 * math.ceil(len(_shipped_lf(LANGUAGE)) / BYTES_PER_TOKEN))
        self.assertEqual(lines[1], MISMATCH_LINE)
        self.assertEqual(lines[2], STILL_LOAD_LINE.format(", ".join(sorted([str(top), str(nested)]))))

    def test_a_stale_subset_copy_is_customized_exactly_as_upgrade_calls_it(self):
        _write(_project_managed(self, LANGUAGE), _stale_subset(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["state"], "CUSTOMIZED")
        self.assertEqual(result["verdict"], "diverged")
        disposition, _detail = self._upgrade_row()
        self.assertEqual(disposition, "customized")

    @needs_yaml
    def test_an_edited_copy_under_an_off_key_reads_as_the_kept_copy_upgrade_keeps(self):
        _write_config(self, "style:\n  plain_language: off\n")
        edited = _write(_project_managed(self, LANGUAGE), _edited(LANGUAGE))
        result, lines = self._report()
        self.assertEqual(result["state"], "MISMATCH")
        self.assertEqual(lines[1], MISMATCH_EDITED_LINE)
        self.assertEqual(self._upgrade_row()[0], "preserved")
        self.assertTrue(edited.is_file())

    @needs_yaml
    def test_a_symlinked_copy_under_an_off_key_is_left_for_the_user_to_delete(self):
        _write_config(self, "style:\n  plain_language: off\n")
        linked = _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        real = Path.is_symlink

        def fake(path):
            # A real symlink needs a Windows privilege, so fake the check.
            return path == linked or real(path)

        with mock.patch.object(Path, "is_symlink", fake):
            result, lines = self._report()
            disposition, _detail = self._upgrade_row()
        self.assertEqual(result["state"], "MISMATCH")
        self.assertEqual(result["symlinks"], [str(linked)])
        self.assertEqual(lines[1], MISMATCH_SYMLINK_LINE)
        # The MISMATCH line already names the symlink, so the generic line is left out.
        self.assertNotIn(f"  {linked} is a symlink. Upgrade never writes through it.", lines)
        self.assertEqual(disposition, "symlink")
        self.assertTrue(linked.is_file())

    @needs_yaml
    def test_an_off_key_with_a_symlinked_installed_copy_prints_one_line_that_mentions_the_symlink(self):
        _write_config(self, "style:\n  plain_language: off\n")
        linked = _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        other_link = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        real = Path.is_symlink

        def fake(path):
            # A real symlink needs a Windows privilege, so fake the check.
            return path in (linked, other_link) or real(path)

        with mock.patch.object(Path, "is_symlink", fake):
            result, lines = self._report()
        mentions_installed = [line for line in lines if "installed copy is a symlink" in line or str(linked) in line]
        self.assertEqual(len(mentions_installed), 1, lines)
        self.assertEqual(mentions_installed[0], MISMATCH_SYMLINK_LINE)
        # Every other symlinked path keeps its own line.
        self.assertEqual(result["symlinks"], [str(linked), str(other_link)])
        self.assertIn(f"  {other_link} is a symlink. Upgrade never writes through it.", lines)

    @needs_yaml
    def test_an_identical_copy_under_an_off_key_is_the_one_upgrade_removes(self):
        _write_config(self, "style:\n  plain_language: off\n")
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        _result, lines = self._report()
        self.assertEqual(lines[1], MISMATCH_LINE)
        self.assertEqual(self._upgrade_row()[0], "removed")

    # -- cost: the stage reads each thing once ---------------------------------

    def test_the_stage_never_runs_the_divergence_classifier_and_checks_edits_once_per_copy(self):
        _write(_project_managed(self, LANGUAGE), _edited(LANGUAGE, "A"))
        _write(_home_managed(self, LANGUAGE), _edited(LANGUAGE, "B"))
        _write(self.project_root / ".claude" / "rules" / "team" / LANGUAGE, _edited(LANGUAGE, "C"))
        real_edits = sr._has_edits
        seen: list[Path] = []

        def counting(shipped, copy, *rest):
            seen.append(copy)
            return real_edits(shipped, copy, *rest)

        with (
            mock.patch.object(sr, "_classify_copy", side_effect=AssertionError("classifier ran")),
            mock.patch.object(sr, "_has_edits", counting),
        ):
            result = self.lint()
        self.assertEqual(result["state"], "DUPLICATE")
        self.assertEqual(len(seen), len(set(seen)), seen)

    def test_the_lint_reads_each_file_once_per_rule(self):
        _write(_project_managed(self, LANGUAGE), _edited(LANGUAGE, "A"))
        _write(_home_managed(self, LANGUAGE), _edited(LANGUAGE, "B"))
        _write(self.project_root / ".claude" / "rules" / "team" / LANGUAGE, _edited(LANGUAGE, "C"))
        real_text, real_bytes = Path.read_text, Path.read_bytes
        reads: list[Path] = []

        def counting_text(path, *args, **kwargs):
            reads.append(path)
            return real_text(path, *args, **kwargs)

        def counting_bytes(path):
            reads.append(path)
            return real_bytes(path)

        with (
            mock.patch.object(Path, "read_text", counting_text),
            mock.patch.object(Path, "read_bytes", counting_bytes),
        ):
            results = sr.lint_style_rules(self.cfg, config={})
        self.assertEqual(_by_name(results, LANGUAGE)["state"], "DUPLICATE")
        repeated = sorted({str(p) for p in reads if reads.count(p) > 1})
        self.assertEqual(repeated, [], "a file was read more than once")

    def test_the_loading_paths_are_stored_in_the_order_the_report_lists_them(self):
        top = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE))
        managed = _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        result = self.lint()
        self.assertEqual(result["loading_paths"], [str(managed), str(top)])
        self.assertEqual(self.lint(PRESENTATION)["loading_paths"], [])


class TestFormatStyleReport(unittest.TestCase):
    """`format_style_report`: the exact lines for each state."""

    def setUp(self):
        _setup_env(self)

    def test_main_line_for_each_state_matches_the_template(self):
        cases = [
            (_result(state="OK"),
             "Style rule plain-language.md: key=on copy=present state=OK bytes=1040 lines=20 ~tokens=400"),
            (_result(state="OK", present=False, duplicate_paths=["/x/plain-language.md"]),
             "Style rule plain-language.md: key=on copy=external state=OK bytes=1040 lines=20 ~tokens=400"),
            (_result(state="DUPLICATE", duplicate_paths=["/x/plain-language.md"]),
             "Style rule plain-language.md: key=on copy=present state=DUPLICATE bytes=1040 lines=20 ~tokens=400"),
            (_result(state="CUSTOMIZED"),
             "Style rule plain-language.md: key=on copy=present state=CUSTOMIZED bytes=1040 lines=20 ~tokens=400"),
            (_result(state="MISSING", present=False),
             "Style rule plain-language.md: key=on copy=absent state=MISSING bytes=1040 lines=20 ~tokens=400"),
            (_result(state="OFF", enabled=False, present=False),
             "Style rule plain-language.md: key=off copy=absent state=OFF bytes=1040 lines=20 ~tokens=400"),
            (_result(state="MISMATCH", enabled=False),
             "Style rule plain-language.md: key=off copy=present state=MISMATCH bytes=1040 lines=20 ~tokens=400"),
        ]
        for result, expected in cases:
            with self.subTest(state=result["state"], present=result["present"]):
                self.assertEqual(sr.format_style_report([result])[0], expected)

    def test_each_states_indented_line_matches_the_template(self):
        cases = [
            (_result(state="OK", present=False, duplicate_paths=["/x/plain-language.md"]),
             "  The rule loads from /x/plain-language.md. Planwise installs no second copy."),
            (_result(state="DUPLICATE", duplicate_paths=["/x/a.md", "/y/b.md"]),
             "  Copies that load: /proj/.claude/rules/planwise/plain-language.md, /x/a.md, /y/b.md. " + COPIES_TAIL),
            (_result(state="CUSTOMIZED"), CUSTOMIZED_LINE),
            (_result(state="MISSING", present=False), MISSING_LINE),
            (_result(state="OFF", enabled=False, present=False), OFF_LINE),
            (_result(state="MISMATCH", enabled=False), MISMATCH_LINE),
        ]
        for result, expected in cases:
            with self.subTest(state=result["state"]):
                lines = sr.format_style_report([result])
                self.assertEqual(lines[1], expected)
                self.assertEqual(len(lines), 3)

    def test_ok_with_a_managed_copy_has_no_indented_line(self):
        lines = sr.format_style_report([_result(state="OK")])
        self.assertEqual(len(lines), 2)
        self.assertFalse(any(line.startswith("  ") for line in lines))

    def test_duplicate_line_lists_every_copy_in_the_stated_order(self):
        result = _result(state="DUPLICATE", duplicate_paths=["/x/a.md", "/y/b.md", "/z/c.md"])
        expected = (
            "  Copies that load: /proj/.claude/rules/planwise/plain-language.md, /x/a.md, /y/b.md, /z/c.md. "
            + COPIES_TAIL
        )
        self.assertEqual(sr.format_style_report([result])[1], expected)

    def test_duplicate_line_without_a_managed_copy_starts_at_the_first_duplicate(self):
        result = _result(state="DUPLICATE", present=False, duplicate_paths=["/x/a.md", "/y/b.md"])
        self.assertEqual(
            sr.format_style_report([result])[1],
            "  Copies that load: /x/a.md, /y/b.md. " + COPIES_TAIL,
        )

    def test_conflict_line_matches_and_appears_only_when_conflict_is_true(self):
        expected = (
            "  The two managed copies carry different edits: /proj/.claude/rules/planwise/plain-language.md "
            "and /home/.claude/rules/planwise/plain-language.md. Upgrade leaves both unchanged. "
            "Merge them by hand."
        )
        with_conflict = sr.format_style_report([_result(state="DUPLICATE", duplicate_paths=["/h"], conflict=True)])
        self.assertEqual(with_conflict[2], expected)
        without = sr.format_style_report([_result(state="DUPLICATE", duplicate_paths=["/h"], conflict=False)])
        self.assertNotIn(expected, without)
        self.assertEqual(len(without), 3)

    def test_each_symlink_line_matches_and_prints_once_per_entry(self):
        result = _result(state="DUPLICATE", duplicate_paths=["/x/a.md"], symlinks=["/x/a.md", "/y/b.md"])
        lines = sr.format_style_report([result])
        self.assertEqual(lines[2], "  /x/a.md is a symlink. Upgrade never writes through it.")
        self.assertEqual(lines[3], "  /y/b.md is a symlink. Upgrade never writes through it.")
        self.assertEqual(len(lines), 5)

    def test_symlink_lines_follow_the_conflict_line(self):
        result = _result(state="DUPLICATE", duplicate_paths=["/x/a.md"], conflict=True, symlinks=["/x/a.md"])
        lines = sr.format_style_report([result])
        self.assertIn("The two managed copies carry different edits", lines[2])
        self.assertEqual(lines[3], "  /x/a.md is a symlink. Upgrade never writes through it.")

    def test_summary_counts_both_copies_for_a_duplicate_and_nothing_for_missing_and_off(self):
        duplicate = _result(state="DUPLICATE", duplicate_paths=["/x/a.md"], loading_tokens=800)
        missing = _result(filename=PRESENTATION, state="MISSING", present=False, loading_tokens=0)
        off = _result(filename=PRESENTATION, state="OFF", enabled=False, present=False, loading_tokens=0)
        summary = "Style rules inject about {} tokens in every session, subagents included (global, always-on)."
        self.assertEqual(sr.format_style_report([duplicate, missing])[-1], summary.format(800))
        self.assertEqual(sr.format_style_report([missing, off])[-1], summary.format(0))

    def test_summary_counts_every_loading_copy_at_its_own_size(self):
        top = _write(self.project_root / ".claude" / "rules" / LANGUAGE, _shipped_lf(LANGUAGE) + b"x" * 301)
        nested = _write(self.home / ".claude" / "rules" / "team" / LANGUAGE, _shipped_lf(LANGUAGE) + b"y" * 7)
        managed = _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        sizes = [len(p.read_bytes()) for p in (top, nested, managed)]
        per_copy = sum(math.ceil(size / BYTES_PER_TOKEN) for size in sizes)
        results = sr.lint_style_rules(self.cfg)
        lines = sr.format_style_report(results)
        # Every copy is rounded up on its own, so this differs from rounding the byte total once.
        self.assertNotEqual(per_copy, math.ceil(sum(sizes) / BYTES_PER_TOKEN))
        language_tokens = _by_name(results, LANGUAGE)["loading_tokens"]
        self.assertEqual(language_tokens, per_copy)
        expected = language_tokens + _by_name(results, PRESENTATION)["loading_tokens"]
        self.assertEqual(
            lines[-1],
            f"Style rules inject about {expected} tokens in every session, subagents included (global, always-on).",
        )

    def test_ceiling_line_appears_only_when_a_ceiling_is_passed(self):
        result = _result(loading_tokens=1500)
        for ceiling in (None, 0):
            with self.subTest(ceiling=ceiling):
                lines = sr.format_style_report([result], ceiling)
                self.assertEqual(len(lines), 2)
                self.assertFalse(any("token_saver_injection_ceiling" in line for line in lines))
        lines = sr.format_style_report([result], 40000)
        self.assertEqual(len(lines), 3)

    def test_ceiling_line_shows_the_rounded_percentage(self):
        # 1500 / 40000 is 3.75 percent: rounded it reads 4, and floored it would read 3.
        lines = sr.format_style_report([_result(loading_tokens=1500)], 40000)
        self.assertEqual(lines[-1], "That is 4% of token_saver_injection_ceiling (40000).")
        # 1234 / 40000 is 3.085 percent, and rounds down to 3.
        lines = sr.format_style_report([_result(loading_tokens=1234)], 40000)
        self.assertEqual(lines[-1], "That is 3% of token_saver_injection_ceiling (40000).")


class TestRunStyleStage(unittest.TestCase):
    """`run_style_stage`: emits every line in order, writes nothing, and keeps warnings off `emit`."""

    @pytest.fixture(autouse=True)
    def _capture(self, capsys):
        self.capsys = capsys

    def setUp(self):
        _setup_env(self)

    def test_every_line_goes_to_emit_in_order_and_the_results_are_returned(self):
        _write(_project_managed(self, LANGUAGE), _shipped_lf(LANGUAGE))
        emitted: list[str] = []
        results = sr.run_style_stage(self.cfg, emit=emitted.append)
        self.assertEqual(results, sr.lint_style_rules(self.cfg))
        # No config sets a ceiling, so the report has no ceiling line.
        self.assertEqual(emitted, sr.format_style_report(results))
        # The managed copy is OK, so it has no indented line and the next rule follows at once.
        self.assertTrue(emitted[0].startswith("Style rule plain-language.md: "))
        self.assertTrue(emitted[1].startswith("Style rule plain-presentation.md: "))
        self.assertTrue(emitted[-1].startswith("Style rules inject about "))

    @needs_yaml
    def test_the_ceiling_comes_from_the_project_config(self):
        _write_config(self, "context:\n  token_saver_injection_ceiling: 20000\n")
        emitted: list[str] = []
        sr.run_style_stage(self.cfg, emit=emitted.append)
        self.assertTrue(emitted[-1].endswith("of token_saver_injection_ceiling (20000)."))

    def test_an_absent_ceiling_key_prints_no_ceiling_line(self):
        emitted: list[str] = []
        sr.run_style_stage(self.cfg, emit=emitted.append)
        self.assertTrue(emitted[-1].startswith("Style rules inject about "), emitted)
        self.assertFalse(any("token_saver_injection_ceiling" in line for line in emitted), emitted)

    @needs_yaml
    def test_a_ceiling_in_another_config_file_is_not_used(self):
        # A `<other>/config.yaml` holds a ceiling, but the stage reads only the planwise-root config.
        other = self.project_root / "elsewhere" / "config.yaml"
        _write(other, b"context:\n  token_saver_injection_ceiling: 5000\n")
        emitted: list[str] = []
        sr.run_style_stage(self.cfg, emit=emitted.append)
        self.assertFalse(any("token_saver_injection_ceiling" in line for line in emitted), emitted)

    @needs_yaml
    def test_a_ceiling_that_is_not_a_positive_integer_prints_no_ceiling_line(self):
        for value in ("0", "-5", "abc", "true"):
            with self.subTest(value=value):
                _write_config(self, f"context:\n  token_saver_injection_ceiling: {value}\n")
                emitted: list[str] = []
                sr.run_style_stage(self.cfg, emit=emitted.append)
                self.assertFalse(any("token_saver_injection_ceiling" in line for line in emitted), emitted)

    def test_the_module_does_not_import_a_doctor_module(self):
        self.assertNotIn("doctor_sweeps", inspect.getsource(sr))

    @needs_yaml
    def test_the_stage_is_read_only_for_the_project_and_the_home_tree(self):
        _write_config(self, "style:\n  plain_presentation: off\n")
        _write(_project_managed(self, LANGUAGE), _edited(LANGUAGE, "A"))
        _write(_home_managed(self, LANGUAGE), _edited(LANGUAGE, "B"))
        _write(self.project_root / ".claude" / "rules" / "team" / LANGUAGE, _shipped_lf(LANGUAGE))
        _write(_project_managed(self, PRESENTATION), _shipped_lf(PRESENTATION))
        before_project = _tree_hash(self.project_root)
        before_home = _tree_hash(self.home)
        self.assertGreater(len(before_project[0]), 3)
        self.assertGreater(len(before_home[0]), 0)
        sr.run_style_stage(self.cfg, emit=lambda line: None)
        self.assertEqual(_tree_hash(self.project_root), before_project)
        self.assertEqual(_tree_hash(self.home), before_home)

    def test_an_absent_style_block_gives_both_rules_key_on(self):
        self.assertFalse((self.project_root / self.cfg.planwise_root / "config.yaml").exists())
        emitted: list[str] = []
        results = sr.run_style_stage(self.cfg, emit=emitted.append)
        self.assertEqual([r["enabled"] for r in results], [True, True])
        for filename in BOTH:
            with self.subTest(filename=filename):
                main = next(line for line in emitted if line.startswith(f"Style rule {filename}: "))
                self.assertIn(" key=on ", main)

    @needs_yaml
    def test_a_malformed_style_value_warns_on_stderr_and_never_through_emit(self):
        _write_config(self, "style:\n  plain_language: maybe\n")
        emitted: list[str] = []
        results = sr.run_style_stage(self.cfg, emit=emitted.append)
        captured = self.capsys.readouterr()
        self.assertIn("Warning: style.plain_language is 'maybe', not on or off; treated as on.", captured.err)
        self.assertEqual(captured.err.count("Warning:"), 1)
        self.assertFalse(any("Warning" in line for line in emitted))
        self.assertNotIn("Warning", captured.out)
        self.assertTrue(_by_name(results, LANGUAGE)["enabled"])

    def test_a_failing_lint_emits_one_line_returns_nothing_and_raises_nothing(self):
        emitted: list[str] = []
        with mock.patch.object(sr, "lint_style_rules", side_effect=RuntimeError("boom")):
            results = sr.run_style_stage(self.cfg, emit=emitted.append)
        self.assertEqual(results, [])
        self.assertEqual(emitted, [FAILED_LINE.format("boom")])

    def test_a_failing_formatter_emits_one_line_and_no_partial_report(self):
        emitted: list[str] = []
        with mock.patch.object(sr, "format_style_report", side_effect=ValueError("bad row")):
            results = sr.run_style_stage(self.cfg, emit=emitted.append)
        self.assertEqual(results, [])
        self.assertEqual(emitted, [FAILED_LINE.format("bad row")])

    def test_the_stage_loads_the_config_once_and_lint_still_works_alone(self):
        real_load = sr._load_raw_config
        calls: list[object] = []

        def counting(cfg):
            calls.append(cfg)
            return real_load(cfg)

        with mock.patch.object(sr, "_load_raw_config", counting):
            sr.run_style_stage(self.cfg, emit=lambda line: None)
        self.assertEqual(len(calls), 1)
        with mock.patch.object(sr, "_load_raw_config", counting):
            self.assertEqual(len(sr.lint_style_rules(self.cfg)), 2)
        self.assertEqual(len(calls), 2)


class TestOverscopeMessage(unittest.TestCase):
    """The over-scope message in `doctor_cli.py` names path-scoped rules only."""

    def test_the_message_says_path_scoped_and_the_old_sentence_is_gone(self):
        source = inspect.getsource(doctor_cli)
        self.assertIn("All installed path-scoped rules are scoped to code paths", source)
        self.assertNotIn("All installed rules are scoped to code paths", source)


class TestStageSeam(unittest.TestCase):
    """`_run_doctor` calls the style stage. Its source is read, and it is never run."""

    def test_run_doctor_source_names_the_stage_and_its_call(self):
        source = inspect.getsource(doctor_cli._run_doctor)
        self.assertIn("run_style_stage", source)
        self.assertIn("Stage 23", source)

    def test_run_doctor_body_calls_run_style_stage(self):
        # The docstring of `_run_doctor` also names the stage, so the text check above
        # alone would still pass after the call was deleted. Parse the source and look
        # for a real call instead.
        tree = ast.parse(textwrap.dedent(inspect.getsource(doctor_cli._run_doctor)))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "run_style_stage"
        ]
        self.assertEqual(len(calls), 1)

    def test_run_doctor_imports_and_calls_the_stage_inside_one_guarded_block(self):
        # Chosen form: parse the source of `_run_doctor` and inspect the tree. The function is never run.
        tree = ast.parse(textwrap.dedent(inspect.getsource(doctor_cli._run_doctor)))
        imports = [
            n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "style_rules"
        ]
        self.assertEqual(len(imports), 1)
        guarded = [
            t for t in ast.walk(tree)
            if isinstance(t, ast.Try)
            and any(imports[0] is n for stmt in t.body for n in ast.walk(stmt))
        ]
        self.assertEqual(len(guarded), 1, "the import of style_rules is outside every try block")
        block = guarded[0]
        in_body = [n for stmt in block.body for n in ast.walk(stmt)]
        self.assertTrue(
            any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "run_style_stage" for n in in_body),
            "the call is not in the same try block as the import",
        )
        caught = [h.type.id for h in block.handlers if isinstance(h.type, ast.Name)]
        self.assertEqual(caught, ["Exception"])

    def test_the_guard_prints_the_same_line_the_stage_prints(self):
        source = inspect.getsource(doctor_cli._run_doctor)
        self.assertIn('print(f"Style rules: the check failed: {exc}")', source)


if __name__ == "__main__":
    unittest.main()
