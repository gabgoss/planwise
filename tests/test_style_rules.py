#!/usr/bin/env python3
"""Install-side tests for the two always-on style rules.

Covers the `style:` config reader, the pinned bytes of the two shipped rule
files, default-on install and the per-key switches, install scope, the
duplicate check, the config template and `--migrate`, the manifest row, and
the `init` seam in `init_project.install_rules`. The classes from `TestUpgradeInstall`
on cover the upgrade side: key transitions, the cross-scope sync, the announcement
and the untracked allowlist, driven through `_run_upgrade` and `upgrade_artifacts`.

Every test class derives from `_StyleFixtureBase`, which redirects
`pathlib.Path.home` to a temporary directory. `style_rule_dir` and
`find_existing_copy` both call `Path.home()`, so without the redirect a
duplicate check would read the developer's real `~/.claude/rules/` and the
result would depend on the machine.

None of these tests reads `init_project.INSTALLED_RULES`. Other test modules
patch that name per module (see conftest.py), and the four path-scoped rule
names are literals here.

Run with:  python -m pytest -q tests/test_style_rules.py
"""

import contextlib
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen
import init_project as ip

# isort: split
# artifact_upgrade must load after init_project: the two import each other, and only that order resolves.
import artifact_upgrade as au
import read_limits
import rule_divergence as rd
import style_rules as sr
import upgrade_io

try:
    import yaml
except ImportError:  # pragma: no cover -- PyYAML is a dev dependency here
    yaml = None

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
REFERENCES = PLUGIN_ROOT / "references"
TEMPLATE = PLUGIN_ROOT / "config.yaml.template"
MANIFEST = PLUGIN_ROOT / "manifests" / "artifacts.yaml"

LANGUAGE = "plain-language.md"
PRESENTATION = "plain-presentation.md"
BOTH = [LANGUAGE, PRESENTATION]

# LF-normalised SHA-256 of each shipped rule, copied from the baseline record.
# They are literals on purpose: the authoring repo that holds the record is
# not available to this repo's tests, so a test must not recompute them from
# anything outside the plugin tree.
PINNED_LF_SHA256 = {
    LANGUAGE: "08a337764550c2e2984ece3fe35a335d7d43168e7101ed33f66d1520889aad43",
    PRESENTATION: "9d69c65a8da96336d3cc14b55cdb4c4665983f2fab4c3ea6279c315e22f07a7e",
}

# The four path-scoped rules `install_rules` writes, in the order it returns
# them (the order of `INSTALLED_RULES`; a literal here, never read from it).
FOUR_RULES = [
    "agent-authoring.md",
    "skill-authoring.md",
    "rule-authoring.md",
    "artifact-self-containment.md",
]

IDENTIFIER_PATTERN = re.compile(r"(LL-[0-9]|BB-[0-9]|BLI-[0-9]|PLG-[0-9]|\bD-[0-9]|Sprint-[0-9])")
BYTES_PER_TOKEN = 2.6
TOKEN_LIMIT = 1200

HAS_YAML = yaml is not None and config_gen.HAS_YAML


def _shipped_bytes(filename: str) -> bytes:
    return (REFERENCES / filename).read_bytes()


class _StyleFixtureBase(unittest.TestCase):
    """A temporary project and home, with `Path.home()` redirected to the home."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="srd_style_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.home = self.tmp / "home"
        self.project_root.mkdir()
        self.home.mkdir()

        patcher = mock.patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.cfg = self.make_cfg()

    # -- builders ----------------------------------------------------------

    def make_cfg(self, scope: str = "project"):
        """A config over the temp project and the REAL plugin tree."""
        return ip.InitConfig(
            project_name="StyleFixture",
            project_root=self.project_root,
            plugin_root=PLUGIN_ROOT,
            install_scope=scope,
        )

    def write_config(self, text: str) -> Path:
        """Write `<project>/planwise/config.yaml` byte-for-byte (no newline translation)."""
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / "config.yaml"
        path.write_bytes(text.encode("utf-8"))
        return path

    def write_style_config(self, **keys: str) -> Path:
        lines = ["style:"] + [f"  {key}: {value}" for key, value in keys.items()]
        return self.write_config("\n".join(lines) + "\n")

    # -- paths -------------------------------------------------------------

    @property
    def project_rules_dir(self) -> Path:
        return self.project_root / ".claude" / "rules" / "planwise"

    @property
    def home_rules_dir(self) -> Path:
        return self.home / ".claude" / "rules" / "planwise"

    def make_rules_dir(self) -> None:
        """`install_rules` does not create its directory; init creates it earlier."""
        self.project_rules_dir.mkdir(parents=True, exist_ok=True)

    def write_top_level_copy(self, base: Path, filename: str, data: bytes) -> Path:
        """Write a same-name rule at the top level of `<base>/.claude/rules/`."""
        path = base / ".claude" / "rules" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


class TestStyleConfig(_StyleFixtureBase):
    """`get_style_config`, `parse_switch` and `enabled_style_rules`."""

    def test_absent_config_enables_both(self):
        self.assertFalse((self.project_root / "planwise" / "config.yaml").exists())
        self.assertEqual(sr.enabled_style_rules(self.cfg), sr.STYLE_RULES)
        self.assertEqual(sr.get_style_config({}), {"plain_language": True, "plain_presentation": True})
        self.assertEqual(sr.get_style_config(None), {"plain_language": True, "plain_presentation": True})

    def test_absent_block_enables_both(self):
        config = {"project": {"name": "x"}}
        self.assertEqual(sr.get_style_config(config), {"plain_language": True, "plain_presentation": True})

    def test_non_dict_block_enables_both(self):
        for block in ("off", ["plain_language", "off"], 0, 7, None, True, False):
            with self.subTest(block=block):
                self.assertEqual(
                    sr.get_style_config({"style": block}),
                    {"plain_language": True, "plain_presentation": True},
                )

    def test_each_key_absent_defaults_to_on(self):
        self.assertEqual(
            sr.get_style_config({"style": {"plain_language": "off"}}),
            {"plain_language": False, "plain_presentation": True},
        )
        self.assertEqual(
            sr.get_style_config({"style": {"plain_presentation": "off"}}),
            {"plain_language": True, "plain_presentation": False},
        )
        self.assertEqual(
            sr.get_style_config({"style": {}}),
            {"plain_language": True, "plain_presentation": True},
        )

    def test_on_and_off_strings_in_mixed_case(self):
        for text in ("on", "ON", "On", "oN", " on "):
            with self.subTest(text=text):
                self.assertIs(sr.parse_switch(text, False), True)
        for text in ("off", "OFF", "Off", "oFf", " off "):
            with self.subTest(text=text):
                self.assertIs(sr.parse_switch(text, True), False)
        self.assertEqual(
            sr.get_style_config({"style": {"plain_language": "OFF", "plain_presentation": "On"}}),
            {"plain_language": False, "plain_presentation": True},
        )

    def test_yaml_booleans(self):
        self.assertEqual(
            sr.get_style_config({"style": {"plain_language": False, "plain_presentation": True}}),
            {"plain_language": False, "plain_presentation": True},
        )
        self.assertIs(sr.parse_switch(True, False), True)
        self.assertIs(sr.parse_switch(False, True), False)

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_unquoted_off_in_a_config_file_reads_as_off(self):
        """YAML 1.1 reads a bare `off` as the boolean False; the reader must still honour it."""
        self.write_style_config(plain_language="off", plain_presentation="on")
        self.assertEqual(sr.enabled_style_rules(self.cfg), [(PRESENTATION, "plain_presentation")])

    def test_unknown_string_gives_the_default(self):
        for text in ("maybe", "", "enabled", "yes please"):
            with self.subTest(text=text):
                self.assertIs(sr.parse_switch(text, True), True)
                self.assertIs(sr.parse_switch(text, False), False)
        self.assertEqual(
            sr.get_style_config({"style": {"plain_language": "maybe", "plain_presentation": "??"}}),
            {"plain_language": True, "plain_presentation": True},
        )

    def test_number_gives_the_default(self):
        for number in (0, 1, 2, -1, 2.5):
            with self.subTest(number=number):
                self.assertIs(sr.parse_switch(number, True), True)
                self.assertIs(sr.parse_switch(number, False), False)
        self.assertEqual(
            sr.get_style_config({"style": {"plain_language": 0, "plain_presentation": 1}}),
            {"plain_language": True, "plain_presentation": True},
        )

    def test_odd_values_never_raise(self):
        for value in (None, [], {}, object(), b"off", (1, 2), float("nan")):
            with self.subTest(value=value):
                result = sr.get_style_config({"style": {"plain_language": value, "plain_presentation": value}})
                self.assertEqual(set(result), {"plain_language", "plain_presentation"})

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_unparseable_config_file_enables_both(self):
        self.write_config("style: [unclosed\n  plain_language: off\n")
        self.assertEqual(sr.enabled_style_rules(self.cfg), sr.STYLE_RULES)


class TestShippedRuleBytes(_StyleFixtureBase):
    """The two shipped files match the pinned hashes and the content limits."""

    def test_lf_normalised_sha256_matches_the_pinned_constant(self):
        for filename, pinned in PINNED_LF_SHA256.items():
            with self.subTest(filename=filename):
                lf = _shipped_bytes(filename).replace(b"\r\n", b"\n")
                self.assertEqual(hashlib.sha256(lf).hexdigest(), pinned)

    def test_the_pinned_constants_are_well_formed(self):
        self.assertEqual(set(PINNED_LF_SHA256), set(BOTH))
        for filename, pinned in PINNED_LF_SHA256.items():
            with self.subTest(filename=filename):
                self.assertRegex(pinned, r"^[0-9a-f]{64}$")

    def test_neither_file_has_a_paths_line(self):
        for filename in BOTH:
            with self.subTest(filename=filename):
                text = _shipped_bytes(filename).decode("utf-8")
                self.assertIsNone(re.search(r"^\s*paths:", text, re.MULTILINE))

    def test_neither_file_matches_the_identifier_pattern(self):
        for filename in BOTH:
            with self.subTest(filename=filename):
                text = _shipped_bytes(filename).decode("utf-8")
                self.assertIsNone(IDENTIFIER_PATTERN.search(text))

    def test_each_file_is_under_the_token_limit(self):
        for filename in BOTH:
            with self.subTest(filename=filename):
                size = len(_shipped_bytes(filename))
                self.assertLess(size / BYTES_PER_TOKEN, TOKEN_LIMIT)


class TestInstallDefaultsAndSwitches(_StyleFixtureBase):
    """`install_style_rules` with and without a `style:` block."""

    def test_no_style_block_installs_both(self):
        installed, skipped = sr.install_style_rules(self.cfg)
        self.assertEqual(installed, BOTH)
        self.assertEqual(skipped, [])
        for filename in BOTH:
            self.assertTrue((self.project_rules_dir / filename).is_file(), filename)

    def test_a_config_without_a_style_block_installs_both(self):
        self.write_config("project:\n  name: x\n")
        installed, _skipped = sr.install_style_rules(self.cfg)
        self.assertEqual(installed, BOTH)

    def test_both_keys_off_installs_neither(self):
        self.write_style_config(plain_language="off", plain_presentation="off")
        installed, skipped = sr.install_style_rules(self.cfg)
        self.assertEqual(installed, [])
        self.assertEqual(skipped, [])
        for filename in BOTH:
            self.assertFalse((self.project_rules_dir / filename).exists(), filename)

    def test_plain_language_off_installs_only_the_presentation_rule(self):
        self.write_style_config(plain_language="off")
        installed, _skipped = sr.install_style_rules(self.cfg)
        self.assertEqual(installed, [PRESENTATION])
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())
        self.assertTrue((self.project_rules_dir / PRESENTATION).is_file())

    def test_plain_presentation_off_installs_only_the_language_rule(self):
        self.write_style_config(plain_presentation="off")
        installed, _skipped = sr.install_style_rules(self.cfg)
        self.assertEqual(installed, [LANGUAGE])
        self.assertFalse((self.project_rules_dir / PRESENTATION).exists())
        self.assertTrue((self.project_rules_dir / LANGUAGE).is_file())

    def test_an_existing_installed_file_is_left_byte_for_byte_unchanged(self):
        self.project_rules_dir.mkdir(parents=True)
        existing = self.project_rules_dir / LANGUAGE
        custom = b"# my own edits\r\nkeep this exactly\r\n"
        existing.write_bytes(custom)

        installed, skipped = sr.install_style_rules(self.cfg)

        self.assertEqual(existing.read_bytes(), custom)
        self.assertNotIn(LANGUAGE, installed)
        self.assertEqual(installed, [PRESENTATION])
        self.assertEqual(skipped, [])

    def test_the_return_value_lists_exactly_the_files_written(self):
        self.write_style_config(plain_presentation="off")
        installed, _skipped = sr.install_style_rules(self.cfg)
        on_disk = sorted(path.name for path in self.project_rules_dir.iterdir())
        self.assertEqual(sorted(installed), on_disk)

        default_root = self.tmp / "other-project"
        default_root.mkdir()
        other = ip.InitConfig(
            project_name="Other",
            project_root=default_root,
            plugin_root=PLUGIN_ROOT,
        )
        installed, _skipped = sr.install_style_rules(other)
        on_disk = sorted(path.name for path in (default_root / ".claude" / "rules" / "planwise").iterdir())
        self.assertEqual(sorted(installed), on_disk)
        self.assertEqual(sorted(installed), sorted(BOTH))

    def test_installed_bytes_equal_shipped_bytes(self):
        sr.install_style_rules(self.cfg)
        for filename in BOTH:
            with self.subTest(filename=filename):
                self.assertEqual((self.project_rules_dir / filename).read_bytes(), _shipped_bytes(filename))

    def _open_failing_for(self, filename: str, error: OSError, partial: bytes = b""):
        """A stand-in for `open` that fails for one rule, after writing `partial` bytes if given."""
        real_open = open

        def fake_open(path, mode="r", *args, **kwargs):
            if Path(path).name != filename:
                return real_open(path, mode, *args, **kwargs)
            if partial:
                with real_open(path, mode) as f:
                    f.write(partial)
            raise error

        return mock.patch.object(sr, "open", fake_open, create=True)

    def test_a_permission_error_on_one_rule_warns_and_the_other_rule_still_installs(self):
        stderr = io.StringIO()
        failing_open = self._open_failing_for(LANGUAGE, PermissionError(13, "Permission denied"))
        with failing_open, contextlib.redirect_stderr(stderr):
            installed, reports = sr.install_style_rules(self.cfg)

        self.assertEqual(installed, [PRESENTATION])
        self.assertEqual(reports, [])
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())
        self.assertEqual((self.project_rules_dir / PRESENTATION).read_bytes(), _shipped_bytes(PRESENTATION))
        warnings = [line for line in stderr.getvalue().splitlines() if line.startswith("  Warning:")]
        self.assertEqual(len(warnings), 1, stderr.getvalue())
        self.assertIn(LANGUAGE, warnings[0])
        self.assertIn(str(self.project_rules_dir / LANGUAGE), warnings[0])
        self.assertIn("Permission denied", warnings[0])

    def test_a_write_error_after_a_partial_write_skips_the_rule_and_deletes_nothing(self):
        stderr = io.StringIO()
        error = OSError(28, "No space left on device")
        failing_open = self._open_failing_for(LANGUAGE, error, partial=b"par")
        with failing_open, contextlib.redirect_stderr(stderr):
            installed, _reports = sr.install_style_rules(self.cfg)

        self.assertEqual(installed, [PRESENTATION])
        # The truncated file stays: this module has no delete path, and the upgrade refresh repairs it.
        self.assertEqual((self.project_rules_dir / LANGUAGE).read_bytes(), b"par")
        self.assertIn("No space left on device", stderr.getvalue())

    def test_an_error_creating_the_directory_warns_and_skips_every_rule_without_raising(self):
        stderr = io.StringIO()
        cfg = self.make_cfg("user")
        failing_mkdir = mock.patch.object(Path, "mkdir", side_effect=PermissionError(13, "Permission denied"))
        with failing_mkdir, contextlib.redirect_stderr(stderr):
            installed, reports = sr.install_style_rules(cfg)

        self.assertEqual(installed, [])
        self.assertEqual(reports, [])
        warnings = [line for line in stderr.getvalue().splitlines() if line.startswith("  Warning:")]
        self.assertEqual(len(warnings), 2, stderr.getvalue())
        for line, filename in zip(warnings, BOTH):
            self.assertIn(filename, line)
            self.assertIn(str(self.home_rules_dir), line)
            self.assertIn("Permission denied", line)


class TestInstallScope(_StyleFixtureBase):
    """The install directory follows the install scope."""

    def test_home_redirect_is_active(self):
        self.assertEqual(Path.home(), self.home)
        self.assertEqual(ip.Path.home(), self.home)
        self.assertEqual(sr.Path.home(), self.home)

    def test_project_scope_installs_under_the_project(self):
        cfg = self.make_cfg("project")
        installed, _skipped = sr.install_style_rules(cfg)
        self.assertEqual(installed, BOTH)
        for filename in BOTH:
            self.assertTrue((self.project_rules_dir / filename).is_file(), filename)
        self.assertEqual(list(self.home.rglob("*")), [])

    def test_local_scope_installs_under_the_project(self):
        cfg = self.make_cfg("local")
        installed, _skipped = sr.install_style_rules(cfg)
        self.assertEqual(installed, BOTH)
        for filename in BOTH:
            self.assertTrue((self.project_rules_dir / filename).is_file(), filename)
        self.assertEqual(list(self.home.rglob("*")), [])

    def test_user_scope_installs_under_the_home_and_writes_nothing_under_the_project(self):
        cfg = self.make_cfg("user")
        installed, _skipped = sr.install_style_rules(cfg)
        self.assertEqual(installed, BOTH)
        for filename in BOTH:
            self.assertTrue((self.home_rules_dir / filename).is_file(), filename)
        self.assertEqual(list(self.project_root.rglob("*")), [])

    def test_user_scope_creates_the_directory_when_it_does_not_exist(self):
        cfg = self.make_cfg("user")
        self.assertFalse((self.home / ".claude").exists())
        sr.install_style_rules(cfg)
        self.assertTrue(self.home_rules_dir.is_dir())

    def test_user_scope_installs_despite_a_project_planwise_copy_and_reports_it(self):
        project_copy = self.project_rules_dir / LANGUAGE
        project_copy.parent.mkdir(parents=True)
        project_copy.write_bytes(_customized_bytes(LANGUAGE))
        cfg = self.make_cfg("user")

        installed, reports = sr.install_style_rules(cfg)

        self.assertEqual(installed, BOTH)
        self.assertEqual(reports, [(LANGUAGE, project_copy, "HAS_UNIQUE", True)])
        for filename in BOTH:
            self.assertEqual((self.home_rules_dir / filename).read_bytes(), _shipped_bytes(filename), filename)
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertFalse((self.project_rules_dir / PRESENTATION).exists())

    def test_user_scope_installs_despite_a_project_top_level_copy_and_reports_it(self):
        project_copy = self.write_top_level_copy(self.project_root, LANGUAGE, _shipped_bytes(LANGUAGE))
        cfg = self.make_cfg("user")

        installed, reports = sr.install_style_rules(cfg)

        self.assertEqual(installed, BOTH)
        self.assertEqual(reports, [(LANGUAGE, project_copy, "identical", True)])
        self.assertTrue((self.home_rules_dir / LANGUAGE).is_file())
        self.assertEqual(project_copy.read_bytes(), _shipped_bytes(LANGUAGE))

    def test_user_scope_reports_each_project_copy_it_finds(self):
        top = self.write_top_level_copy(self.project_root, LANGUAGE, _shipped_bytes(LANGUAGE))
        nested = self.project_rules_dir / LANGUAGE
        nested.parent.mkdir(parents=True)
        nested.write_bytes(_stale_subset_bytes(LANGUAGE))

        installed, reports = sr.install_style_rules(self.make_cfg("user"))

        self.assertEqual(installed, BOTH)
        self.assertEqual(
            reports,
            [(LANGUAGE, top, "identical", True), (LANGUAGE, nested, "SUBSET", True)],
        )

    def test_user_scope_reports_no_project_copy_when_nothing_was_written(self):
        # The warning text says "installed", so a rule that failed to install must not carry it.
        self.write_top_level_copy(self.project_root, LANGUAGE, _shipped_bytes(LANGUAGE))
        cfg = self.make_cfg("user")
        shipped = REFERENCES / LANGUAGE
        real_read_bytes = Path.read_bytes

        def fake_read_bytes(path):
            if path == shipped:
                raise FileNotFoundError(path)
            return real_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", fake_read_bytes), contextlib.redirect_stderr(io.StringIO()):
            installed, reports = sr.install_style_rules(cfg)

        self.assertEqual(installed, [PRESENTATION])
        self.assertEqual(reports, [])


def _customized_bytes(filename: str) -> bytes:
    """The shipped rule plus a section that exists only in the copy."""
    return _shipped_bytes(filename) + (
        b"\n## A Local Section\n- This instruction was added by the user and exists nowhere in the shipped rule.\n"
    )


def _stale_subset_bytes(filename: str) -> bytes:
    """The shipped rule cut before one whole section, so every block it holds is shipped text."""
    return _shipped_bytes(filename).split(b"\n## Honesty")[0] + b"\n"


class TestDuplicateSkip(_StyleFixtureBase):
    """A same-name file anywhere under a `.claude/rules/` tree stops a project or local install."""

    def _assert_duplicate_stops_install(self, base: Path, data: bytes, verdict: str) -> None:
        existing = self.write_top_level_copy(base, LANGUAGE, data)

        installed, reports = sr.install_style_rules(self.cfg)

        self.assertEqual(installed, [PRESENTATION])
        self.assertEqual(reports, [(LANGUAGE, existing, verdict, False)])
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())
        self.assertTrue((self.project_rules_dir / PRESENTATION).is_file())
        self.assertEqual(existing.read_bytes(), data)

    def test_identical_copy_at_the_project_top_level_stops_the_install(self):
        self._assert_duplicate_stops_install(self.project_root, _shipped_bytes(LANGUAGE), "identical")

    def test_differing_copy_at_the_project_top_level_stops_the_install(self):
        self._assert_duplicate_stops_install(self.project_root, b"# customized by the user\n", "HAS_UNIQUE")

    def test_identical_copy_at_the_home_top_level_stops_the_install(self):
        self._assert_duplicate_stops_install(self.home, _shipped_bytes(LANGUAGE), "identical")

    def test_differing_copy_at_the_home_top_level_stops_the_install(self):
        self._assert_duplicate_stops_install(self.home, b"# customized by the user\n", "HAS_UNIQUE")

    def test_a_same_name_file_inside_another_subdirectory_stops_a_project_install(self):
        project_other = self.project_root / ".claude" / "rules" / "other" / LANGUAGE
        home_other = self.home / ".claude" / "rules" / "elsewhere" / PRESENTATION
        for path in (project_other, home_other):
            path.parent.mkdir(parents=True)
            path.write_bytes(b"# unrelated copy\n")

        installed, reports = sr.install_style_rules(self.cfg)

        self.assertEqual(installed, [])
        self.assertEqual(
            reports,
            [
                (LANGUAGE, project_other, "HAS_UNIQUE", False),
                (PRESENTATION, home_other, "HAS_UNIQUE", False),
            ],
        )
        for filename in BOTH:
            self.assertFalse((self.project_rules_dir / filename).exists(), filename)
        self.assertEqual(project_other.read_bytes(), b"# unrelated copy\n")
        self.assertEqual(home_other.read_bytes(), b"# unrelated copy\n")

    def test_a_project_install_is_stopped_by_a_copy_in_the_home_planwise_directory(self):
        home_copy = self.home_rules_dir / LANGUAGE
        home_copy.parent.mkdir(parents=True)
        home_copy.write_bytes(_shipped_bytes(LANGUAGE))

        installed, reports = sr.install_style_rules(self.make_cfg("project"))

        self.assertEqual(installed, [PRESENTATION])
        self.assertEqual(reports, [(LANGUAGE, home_copy, "identical", False)])
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())

    def test_a_local_install_is_stopped_by_a_nested_copy_in_the_project(self):
        nested = self.project_root / ".claude" / "rules" / "team" / "deep" / LANGUAGE
        nested.parent.mkdir(parents=True)
        nested.write_bytes(_shipped_bytes(LANGUAGE))

        installed, reports = sr.install_style_rules(self.make_cfg("local"))

        self.assertEqual(installed, [PRESENTATION])
        self.assertEqual(reports, [(LANGUAGE, nested, "identical", False)])

    def test_the_install_target_is_never_its_own_duplicate_on_a_rerun(self):
        for scope in ("project", "user"):
            with self.subTest(scope=scope):
                # Start each scope from an empty project and home.
                shutil.rmtree(self.project_root / ".claude", ignore_errors=True)
                shutil.rmtree(self.home / ".claude", ignore_errors=True)
                cfg = self.make_cfg(scope)
                first_installed, first_reports = sr.install_style_rules(cfg)
                self.assertEqual(first_installed, BOTH)
                self.assertEqual(first_reports, [])

                second_installed, second_reports = sr.install_style_rules(cfg)
                self.assertEqual(second_installed, [])
                self.assertEqual(second_reports, [])
                for filename in BOTH:
                    self.assertIsNone(sr.find_existing_copy(cfg, filename))
                    self.assertEqual(sr.find_existing_copies(cfg, filename), [])

    def test_find_existing_copies_orders_project_hits_before_home_hits_and_skips_missing_trees(self):
        self.assertEqual(sr.find_existing_copies(self.cfg, LANGUAGE), [])

        home_top = self.write_top_level_copy(self.home, LANGUAGE, _shipped_bytes(LANGUAGE))
        project_b = self.project_root / ".claude" / "rules" / "b" / LANGUAGE
        project_a = self.project_root / ".claude" / "rules" / "a" / LANGUAGE
        for path in (project_b, project_a):
            path.parent.mkdir(parents=True)
            path.write_bytes(_shipped_bytes(LANGUAGE))

        hits = sr.find_existing_copies(self.cfg, LANGUAGE)

        self.assertEqual([path for path, _verdict in hits], [project_a, project_b, home_top])

    def test_a_file_reached_through_both_trees_is_reported_once(self):
        cfg = ip.InitConfig(
            project_name="StyleFixture",
            project_root=self.home,
            plugin_root=PLUGIN_ROOT,
            install_scope="project",
        )
        copy = self.write_top_level_copy(self.home, LANGUAGE, _shipped_bytes(LANGUAGE))

        self.assertEqual(sr.find_existing_copies(cfg, LANGUAGE), [(copy, "identical")])

    def test_a_user_install_is_stopped_by_a_copy_at_the_home_top_level(self):
        home_copy = self.write_top_level_copy(self.home, LANGUAGE, _shipped_bytes(LANGUAGE))
        cfg = self.make_cfg("user")

        installed, reports = sr.install_style_rules(cfg)

        self.assertEqual(installed, [PRESENTATION])
        self.assertEqual(reports, [(LANGUAGE, home_copy, "identical", False)])
        self.assertFalse((self.home_rules_dir / LANGUAGE).exists())
        self.assertEqual(sr.find_existing_copy(cfg, LANGUAGE), (home_copy, "identical"))

    def test_a_user_install_is_never_blocked_by_a_copy_that_only_the_project_holds(self):
        project_copy = self.write_top_level_copy(self.project_root, LANGUAGE, _shipped_bytes(LANGUAGE))
        cfg = self.make_cfg("user")

        self.assertIsNone(sr.find_existing_copy(cfg, LANGUAGE))
        self.assertEqual(sr.find_existing_copy(self.make_cfg("project"), LANGUAGE), (project_copy, "identical"))

    def test_a_user_install_is_blocked_by_the_home_copy_even_when_a_project_copy_comes_first(self):
        self.write_top_level_copy(self.project_root, LANGUAGE, _shipped_bytes(LANGUAGE))
        home_copy = self.write_top_level_copy(self.home, LANGUAGE, _customized_bytes(LANGUAGE))

        found = sr.find_existing_copy(self.make_cfg("user"), LANGUAGE)

        self.assertEqual(found, (home_copy, "HAS_UNIQUE"))

    def _assert_home_copy_resolving_outside_still_blocks(self, home_copy: Path) -> None:
        installed, reports = sr.install_style_rules(self.make_cfg("user"))

        self.assertEqual(installed, [PRESENTATION])
        self.assertEqual(reports, [(LANGUAGE, home_copy, "identical", False)])
        self.assertFalse((self.home_rules_dir / LANGUAGE).exists())
        self.assertEqual(sr.find_existing_copy(self.make_cfg("user"), LANGUAGE), (home_copy, "identical"))

    def test_a_user_install_is_stopped_by_a_home_symlink_that_points_outside_the_home_rules_tree(self):
        outside = self.tmp / "dotfiles" / LANGUAGE
        outside.parent.mkdir()
        outside.write_bytes(_shipped_bytes(LANGUAGE))
        link = self.home / ".claude" / "rules" / LANGUAGE
        link.parent.mkdir(parents=True)
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create a symlink on this machine: {exc!r}")

        self._assert_home_copy_resolving_outside_still_blocks(link)

    def test_a_home_walked_hit_that_resolves_outside_the_home_tree_still_blocks_a_user_install(self):
        # The symlink test above skips where symlinks need privileges. This one forces the same
        # branch by making the resolved path of the home copy fall outside the home tree.
        home_copy = self.write_top_level_copy(self.home, LANGUAGE, _shipped_bytes(LANGUAGE))
        elsewhere = (self.tmp / "dotfiles" / LANGUAGE).resolve()
        real_resolve = Path.resolve

        def fake_resolve(path, *args, **kwargs):
            if path == home_copy:
                return elsewhere
            return real_resolve(path, *args, **kwargs)

        with mock.patch.object(Path, "resolve", fake_resolve):
            self._assert_home_copy_resolving_outside_still_blocks(home_copy)

    def test_a_same_name_copy_with_different_case_stops_a_project_install(self):
        # Compare the name the walk found, so the test holds on a case-insensitive filesystem too:
        # a lookup by the lower-case pattern would report the pattern's spelling, not the file's.
        differently_cased = "Plain-Language.md"
        existing = self.project_root / ".claude" / "rules" / "team" / differently_cased
        existing.parent.mkdir(parents=True)
        existing.write_bytes(_shipped_bytes(LANGUAGE))

        hits = sr.find_existing_copies(self.cfg, LANGUAGE)
        installed, reports = sr.install_style_rules(self.cfg)

        self.assertEqual([path.name for path, _verdict in hits], [differently_cased])
        self.assertEqual(installed, [PRESENTATION])
        self.assertEqual([path.name for _f, path, _v, _i in reports], [differently_cased])
        self.assertEqual(reports[0][0], LANGUAGE)
        self.assertEqual(reports[0][2:], ("identical", False))
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())

    def _verdict_of(self, data: bytes) -> tuple[Path, str]:
        copy = self.write_top_level_copy(self.project_root, LANGUAGE, data)
        found = sr.find_existing_copy(self.cfg, LANGUAGE)
        self.assertIsNotNone(found)
        self.assertEqual(found[0], copy)
        return found

    def test_verdict_identical_and_its_exact_line(self):
        path, verdict = self._verdict_of(_shipped_bytes(LANGUAGE))
        self.assertEqual(verdict, "identical")
        self.assertEqual(
            sr.format_duplicate_line(LANGUAGE, path, verdict),
            f"Style rule {LANGUAGE}: not installed, an identical copy exists at {path}.",
        )

    def test_verdict_for_a_copy_with_user_edits_and_its_exact_line(self):
        path, verdict = self._verdict_of(_customized_bytes(LANGUAGE))
        self.assertEqual(verdict, "HAS_UNIQUE")
        self.assertEqual(
            sr.format_duplicate_line(LANGUAGE, path, verdict),
            f"Style rule {LANGUAGE}: not installed, a customized copy exists at {path}.",
        )

    def test_verdict_for_a_stale_subset_and_its_exact_line(self):
        path, verdict = self._verdict_of(_stale_subset_bytes(LANGUAGE))
        self.assertEqual(verdict, "SUBSET")
        self.assertEqual(
            sr.format_duplicate_line(LANGUAGE, path, verdict),
            f"Style rule {LANGUAGE}: not installed, an older copy exists at {path}.",
        )

    def test_verdict_for_an_unreadable_copy_is_not_analyzed(self):
        path, verdict = self._verdict_of(b"\xff\xfe\x00 not valid utf-8 \x80\x81\n")
        self.assertEqual(verdict, "NOT_ANALYZED")
        self.assertEqual(
            sr.format_duplicate_line(LANGUAGE, path, verdict),
            f"Style rule {LANGUAGE}: not installed, a copy that could not be compared exists at {path}.",
        )

    def test_verdict_when_the_classifier_degrades_is_not_analyzed(self):
        import rule_divergence

        degraded = mock.Mock(source=rule_divergence._DEGRADED_VERDICT_SOURCE)
        with mock.patch.object(rule_divergence, "_classify_diverged", return_value=degraded):
            _path, verdict = self._verdict_of(_customized_bytes(LANGUAGE))
        self.assertEqual(verdict, "NOT_ANALYZED")

    def test_format_duplicate_line_gives_the_two_exact_sentences(self):
        path = Path("/some/dir/.claude/rules") / LANGUAGE
        self.assertEqual(
            sr.format_duplicate_line(LANGUAGE, path, "identical"),
            f"Style rule {LANGUAGE}: not installed, an identical copy exists at {path}.",
        )
        self.assertEqual(
            sr.format_duplicate_line(LANGUAGE, path, "HAS_UNIQUE"),
            f"Style rule {LANGUAGE}: not installed, a customized copy exists at {path}.",
        )
        # A verdict the table does not know reads as a customized copy, as before.
        self.assertEqual(
            sr.format_duplicate_line(LANGUAGE, path, "diverged"),
            f"Style rule {LANGUAGE}: not installed, a customized copy exists at {path}.",
        )

    def test_format_duplicate_line_when_installed_names_the_copy_that_loads_alongside(self):
        path = Path("/some/project/.claude/rules/planwise") / LANGUAGE
        descriptions = {
            "identical": "an identical copy",
            "HAS_UNIQUE": "a customized copy",
            "SUBSET": "an older copy",
            "NOT_ANALYZED": "a copy that could not be compared",
        }
        for verdict, desc in descriptions.items():
            with self.subTest(verdict=verdict):
                self.assertEqual(
                    sr.format_duplicate_line(LANGUAGE, path, verdict, installed=True),
                    f"Style rule {LANGUAGE}: installed for all projects, but {desc} also exists at {path}; "
                    "that project loads both until /planwise upgrade reconciles them.",
                )
                self.assertEqual(
                    sr.format_duplicate_line(LANGUAGE, path, verdict, True),
                    sr.format_duplicate_line(LANGUAGE, path, verdict, installed=True),
                )


@unittest.skipUnless(HAS_YAML, "PyYAML not installed")
class TestTemplateAndMigration(_StyleFixtureBase):
    """The shipped template carries the block, and `--migrate` adds it safely."""

    def _style_block_lines(self) -> list[str]:
        text = TEMPLATE.read_text(encoding="utf-8")
        match = re.search(r"^style:\n((?:[ \t]+.*\n|\n)*)", text, re.MULTILINE)
        self.assertIsNotNone(match, "config.yaml.template has no top-level style: block")
        return match.group(1).splitlines()

    def test_template_contains_the_style_block_with_both_keys_on(self):
        lines = self._style_block_lines()
        self.assertIn("  plain_language: on", [line.rstrip() for line in lines])
        self.assertIn("  plain_presentation: on", [line.rstrip() for line in lines])

    def test_a_config_generated_from_the_template_reads_as_both_on(self):
        (self.project_root / "planwise").mkdir()
        config_gen.generate_config(self.cfg)
        loaded = yaml.safe_load((self.project_root / "planwise" / "config.yaml").read_text(encoding="utf-8"))
        self.assertIsInstance(loaded.get("style"), dict)
        self.assertEqual(sr.get_style_config(loaded), {"plain_language": True, "plain_presentation": True})

    def test_migrate_adds_the_block_keeps_comments_and_keys_and_is_idempotent(self):
        original = (
            "# hand-written header comment\n"
            "project:\n"
            '  name: "Kept"   # inline comment survives\n'
            "custom_key: 42\n"
            "# trailing comment\n"
        )
        path = self.write_config(original)

        _path, added, _present = config_gen.migrate_config(self.cfg)

        self.assertIn("style", added)
        merged = path.read_bytes().decode("utf-8")
        for kept in (
            "# hand-written header comment",
            '  name: "Kept"   # inline comment survives',
            "custom_key: 42",
            "# trailing comment",
        ):
            self.assertIn(kept, merged)
        loaded = yaml.safe_load(merged)
        self.assertEqual(loaded["custom_key"], 42)
        self.assertEqual(loaded["project"]["name"], "Kept")
        self.assertEqual(sr.get_style_config(loaded), {"plain_language": True, "plain_presentation": True})
        self.assertRegex(merged, r"(?m)^  plain_language: on\s*$")
        self.assertRegex(merged, r"(?m)^  plain_presentation: on\s*$")

        before_second = path.read_bytes()
        _path, added_again, present_again = config_gen.migrate_config(self.cfg)
        self.assertEqual(added_again, [])
        self.assertIn("style", present_again)
        self.assertEqual(path.read_bytes(), before_second)

    def test_a_config_that_already_sets_plain_language_off_keeps_off(self):
        original = "# keep me\nstyle:\n  plain_language: off\n"
        path = self.write_config(original)

        _path, added, present = config_gen.migrate_config(self.cfg)

        self.assertNotIn("style", added)
        self.assertIn("style", present)
        merged = path.read_bytes().decode("utf-8")
        self.assertIn("# keep me", merged)
        self.assertRegex(merged, r"(?m)^  plain_language: off\s*$")
        self.assertEqual(merged.count("plain_language"), 1)
        loaded = yaml.safe_load(merged)
        self.assertEqual(sr.get_style_config(loaded)["plain_language"], False)


@unittest.skipUnless(yaml is not None, "PyYAML not installed")
class TestManifestRow(_StyleFixtureBase):
    """The artifacts manifest records the style rules and the keys that switch them."""

    def test_style_rules_row_lists_the_two_style_keys(self):
        doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        rows = [row for row in doc["artifacts"] if row.get("id") == "style_rules"]
        self.assertEqual(len(rows), 1, "the manifest must hold exactly one style_rules row")
        style_keys = [key for key in rows[0]["config_keys"] if key.startswith("style.")]
        self.assertEqual(sorted(style_keys), ["style.plain_language", "style.plain_presentation"])


class TestInitSeam(_StyleFixtureBase):
    """`init_project.install_rules` installs the enabled style rules after the four."""

    def run_seam(self, cfg=None) -> tuple[list[str], str]:
        """Call `install_rules` itself, with stdout captured and the home redirected."""
        cfg = cfg if cfg is not None else self.cfg
        self.make_rules_dir()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            names = ip.install_rules(cfg)
        return names, out.getvalue()

    def test_default_config_project_scope_returns_six_names(self):
        names, out = self.run_seam()

        self.assertIsInstance(names, list)
        self.assertTrue(all(isinstance(name, str) for name in names))
        self.assertEqual(len(names), 6)
        self.assertEqual(names[:4], FOUR_RULES)
        self.assertEqual(names[4:], BOTH)
        for name in names:
            self.assertTrue((self.project_rules_dir / name).is_file(), name)
        # The path-scoped rules keep their `paths:` line; the style rules never get one.
        for name in FOUR_RULES:
            self.assertRegex((self.project_rules_dir / name).read_text(encoding="utf-8"), r"(?m)^paths:")
        for name in BOTH:
            self.assertNotRegex((self.project_rules_dir / name).read_text(encoding="utf-8"), r"(?m)^paths:")
        # The "Rules installed to" banner is printed by main(), not here.
        self.assertEqual(out, "")

    def test_both_keys_off_returns_exactly_the_four_names(self):
        self.write_style_config(plain_language="off", plain_presentation="off")
        names, _out = self.run_seam()
        self.assertEqual(names, FOUR_RULES)
        for filename in BOTH:
            self.assertFalse((self.project_rules_dir / filename).exists(), filename)

    def test_plain_language_off_returns_five_names(self):
        self.write_style_config(plain_language="off")
        names, _out = self.run_seam()
        self.assertEqual(names, FOUR_RULES + [PRESENTATION])
        self.assertTrue((self.project_rules_dir / PRESENTATION).is_file())
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())

    def test_plain_presentation_off_returns_five_names(self):
        self.write_style_config(plain_presentation="off")
        names, _out = self.run_seam()
        self.assertEqual(names, FOUR_RULES + [LANGUAGE])
        self.assertTrue((self.project_rules_dir / LANGUAGE).is_file())
        self.assertFalse((self.project_rules_dir / PRESENTATION).exists())

    def _assert_duplicate_is_skipped_and_printed(self, base: Path, data: bytes, verdict: str) -> None:
        existing = self.write_top_level_copy(base, LANGUAGE, data)

        names, out = self.run_seam()

        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())
        self.assertNotIn(LANGUAGE, names)
        self.assertEqual(names, FOUR_RULES + [PRESENTATION])
        line = sr.format_duplicate_line(LANGUAGE, existing, verdict)
        self.assertIn(line, out.splitlines())
        self.assertEqual(existing.read_bytes(), data)

    def test_identical_copy_at_the_project_top_level_is_skipped_and_printed(self):
        self._assert_duplicate_is_skipped_and_printed(self.project_root, _shipped_bytes(LANGUAGE), "identical")

    def test_differing_copy_at_the_project_top_level_is_skipped_and_printed(self):
        self._assert_duplicate_is_skipped_and_printed(self.project_root, b"# customized\n", "HAS_UNIQUE")

    def test_identical_copy_at_the_home_top_level_is_skipped_and_printed(self):
        self._assert_duplicate_is_skipped_and_printed(self.home, _shipped_bytes(LANGUAGE), "identical")

    def test_differing_copy_at_the_home_top_level_is_skipped_and_printed(self):
        self._assert_duplicate_is_skipped_and_printed(self.home, b"# customized\n", "HAS_UNIQUE")

    def test_user_scope_with_a_project_planwise_copy_installs_and_prints_the_installed_line(self):
        project_copy = self.project_rules_dir / LANGUAGE
        project_copy.parent.mkdir(parents=True)
        project_copy.write_bytes(_customized_bytes(LANGUAGE))

        names, out = self.run_seam(self.make_cfg("user"))

        self.assertEqual(names, FOUR_RULES + BOTH)
        for name in BOTH:
            self.assertTrue((self.home_rules_dir / name).is_file(), name)
        line = (
            f"Style rule {LANGUAGE}: installed for all projects, but a customized copy also exists "
            f"at {project_copy}; that project loads both until /planwise upgrade reconciles them."
        )
        self.assertEqual(out.splitlines().count(line), 1, out)
        self.assertEqual(line, sr.format_duplicate_line(LANGUAGE, project_copy, "HAS_UNIQUE", True))
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))

    def test_a_style_rule_write_error_leaves_the_four_path_scoped_names_returned(self):
        real_open = open

        def fake_open(path, mode="r", *args, **kwargs):
            if Path(path).name == LANGUAGE:
                raise PermissionError(13, "Permission denied")
            return real_open(path, mode, *args, **kwargs)

        stderr = io.StringIO()
        with mock.patch.object(sr, "open", fake_open, create=True), contextlib.redirect_stderr(stderr):
            names, out = self.run_seam()

        self.assertEqual(names, FOUR_RULES + [PRESENTATION])
        for name in FOUR_RULES:
            self.assertTrue((self.project_rules_dir / name).is_file(), name)
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())
        self.assertEqual(out, "")
        self.assertIn(LANGUAGE, stderr.getvalue())

    def test_user_scope_puts_the_style_rules_under_the_home(self):
        # The `Style rules installed to <dir>.` line is printed inline by
        # `init_project.main()`, not by `install_rules`, so it is asserted by
        # the `test_main_*` tests below, which run `main()` itself.
        cfg = self.make_cfg("user")
        names, _out = self.run_seam(cfg)

        self.assertEqual(names, FOUR_RULES + BOTH)
        for name in FOUR_RULES:
            self.assertTrue((self.project_rules_dir / name).is_file(), name)
        for name in BOTH:
            self.assertTrue((self.home_rules_dir / name).is_file(), name)
            self.assertFalse((self.project_rules_dir / name).exists(), name)

    def test_project_scope_prints_no_style_rules_installed_line(self):
        _names, out = self.run_seam()
        self.assertNotIn("Style rules installed to", out)

    def run_main(self, scope: str) -> str:
        """Run `init_project.main()` itself over the temp project; return its stdout."""
        argv = ["init_project.py", "--name", "StyleFixture",
                "--project-root", str(self.project_root), "--scope", scope]
        out = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            ip.main()
        return out.getvalue()

    def test_main_user_scope_prints_the_style_rules_installed_line(self):
        # `main()` prints the line inline (inside `if rules:` and the user-scope
        # branch), so only a full `main()` run reaches it.
        out = self.run_main("user")

        expected = f"Style rules installed to {sr.style_rule_dir(self.make_cfg('user'))}."
        self.assertEqual(expected, f"Style rules installed to {self.home_rules_dir}.")
        self.assertEqual(out.splitlines().count(expected), 1, out)
        for name in BOTH:
            self.assertTrue((self.home_rules_dir / name).is_file(), name)
            self.assertFalse((self.project_rules_dir / name).exists(), name)

    def test_main_project_scope_prints_no_style_rules_installed_line(self):
        out = self.run_main("project")

        self.assertIn("Rules installed to .claude/rules/planwise/:", out)
        self.assertNotIn("Style rules installed to", out)
        for name in BOTH:
            self.assertTrue((self.project_rules_dir / name).is_file(), name)


# ---------------------------------------------------------------------------
# Upgrade side: `reconcile_style_switches`, `sync_cross_scope`, the style loop in
# `upgrade_artifacts`, the announcement, and `_run_upgrade` at both version pins.
# ---------------------------------------------------------------------------

OLD_VERSION = "1.0.0"
TARGET_VERSION = "1.1.0"
PAIR_DIR = f"{OLD_VERSION}-to-{TARGET_VERSION}"
CURRENT_PAIR_DIR = f"{TARGET_VERSION}-to-{TARGET_VERSION}"
UPSTREAM_SECTION = b"\n## An Upstream Section\n- This instruction ships in the new version and is absent from the installed copy.\n"
ANNOUNCEMENT_FIRST_LINE = "Style rules: planwise now installs two global rules, on by default."


def _lf(data: bytes) -> bytes:
    """Line endings normalised, because a text-mode adoption write follows the platform."""
    return data.replace(b"\r\n", b"\n")


def _grown_bytes(filename: str) -> bytes:
    """The shipped rule plus a section a newer plugin version adds."""
    return _shipped_bytes(filename) + UPSTREAM_SECTION


def _dispositions(rows) -> dict[str, str]:
    return {name: disposition for name, disposition, _detail in rows}


def _style_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("Style rule ")]


def _put(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@unittest.skipUnless(HAS_YAML, "PyYAML not installed")
class _UpgradeFixtureBase(_StyleFixtureBase):
    """A project whose config targets `TARGET_VERSION`, driven through the upgrade entry points.

    `artifact_upgrade.INSTALLED_RULES` is patched to empty so only the two style rules are in
    play (the four path-scoped rules are not refreshed here). The feedback-dir write and the CLI
    version refresh are patched out so a config's bytes change only when a test says so.
    Per-module patching matches the other upgrade tests; `init_project.INSTALLED_RULES` is never read.
    """

    def make_cfg(self, scope: str = "project", plugin_root: Path | None = None):
        return ip.InitConfig(
            project_name="StyleFixture",
            project_root=self.project_root,
            plugin_root=plugin_root or PLUGIN_ROOT,
            install_scope=scope,
            plugin_version=TARGET_VERSION,
        )

    def setUp(self):
        super().setUp()
        patches = (
            ("INSTALLED_RULES", []),
            ("_apply_feedback_dir", lambda *args, **kwargs: None),
            ("refresh_verified_cli_version", lambda *args, **kwargs: ""),
        )
        for name, value in patches:
            patcher = mock.patch.object(au, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_pin(self, pin: str, style: dict | None = None, handoff: str | None = None) -> Path:
        lines = [f'plugin_version: "{pin}"']
        if handoff:
            lines += ["upgrade:", f'  customization_handoff: "{handoff}"']
        if style:
            lines.append("style:")
            lines += [f"  {key}: {value}" for key, value in style.items()]
        return self.write_config("\n".join(lines) + "\n")

    def run_upgrade(self, cfg=None) -> tuple[int, str, str]:
        """Call `_run_upgrade` itself, with stdout and stderr captured."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = au._run_upgrade(cfg or self.cfg)
        return code, out.getvalue(), err.getvalue()

    def run_pinned(self) -> str:
        """Run `_run_upgrade` at a current pin and check what holds for every such run.

        The exit code is 0, the output ends with `Already up to date.`, and `config.yaml` is
        byte-identical. Returns the stdout.
        """
        config = self.project_root / self.cfg.planwise_root / "config.yaml"
        before = config.read_bytes()
        code, out, err = self.run_upgrade()
        self.assertEqual(code, 0, err)
        self.assertTrue(out.rstrip().endswith("Already up to date."), out)
        self.assertEqual(config.read_bytes(), before)
        return out

    def backup_root(self, pair: str = PAIR_DIR) -> Path:
        return self.project_root / self.cfg.planwise_root / "upgrade-backups" / pair

    def reconcile(self, cfg=None):
        return sr.reconcile_style_switches(cfg or self.cfg, OLD_VERSION, TARGET_VERSION)

    def snapshot(self, path: Path) -> tuple[bytes, int]:
        return path.read_bytes(), path.stat().st_mtime_ns


class TestUpgradeInstall(_UpgradeFixtureBase):
    """A version-change run installs what the keys ask for and leaves an agreeing state alone."""

    def test_a_version_change_run_on_a_config_with_no_style_block_installs_both_and_writes_the_block(self):
        config = self.write_pin(OLD_VERSION)

        code, out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        for filename in BOTH:
            self.assertEqual((self.project_rules_dir / filename).read_bytes(), _shipped_bytes(filename), filename)
            self.assertIn(f"Style rule {filename}: installed", out)
        text = config.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^style:\s*$")
        self.assertRegex(text, r"(?m)^  plain_language: on\s*$")
        self.assertRegex(text, r"(?m)^  plain_presentation: on\s*$")

    def test_key_on_and_file_absent_is_installed(self):
        self.write_style_config(plain_language="on", plain_presentation="on")

        rows = self.reconcile()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "installed", PRESENTATION: "installed"})
        for filename in BOTH:
            self.assertEqual((self.project_rules_dir / filename).read_bytes(), _shipped_bytes(filename), filename)
        self.assertEqual(len(sr.format_reconcile_lines(rows)), 2)

    def test_both_keys_on_and_files_identical_is_unchanged_with_no_write_and_no_printed_line(self):
        self.write_style_config(plain_language="on", plain_presentation="on")
        sr.install_style_rules(self.cfg)
        before = {filename: self.snapshot(self.project_rules_dir / filename) for filename in BOTH}

        rows = self.reconcile()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "unchanged", PRESENTATION: "unchanged"})
        self.assertEqual(sr.format_reconcile_lines(rows), [])
        for filename in BOTH:
            self.assertEqual(self.snapshot(self.project_rules_dir / filename), before[filename], filename)
        self.assertFalse(self.backup_root().exists())


class TestUpgradeSwitches(_UpgradeFixtureBase):
    """Each key transition reconciles one rule against its switch."""

    def test_on_to_off_with_an_identical_copy_removes_it_after_the_backup_exists(self):
        sr.install_style_rules(self.cfg)
        self.write_style_config(plain_language="off", plain_presentation="on")
        backup = self.backup_root() / ".claude" / "rules" / "planwise" / LANGUAGE
        seen: list[bool] = []
        real_unlink = Path.unlink

        def spying_unlink(path, *args, **kwargs):
            if path.name == LANGUAGE:
                seen.append(backup.is_file() and backup.read_bytes() == _shipped_bytes(LANGUAGE))
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", spying_unlink):
            rows = self.reconcile()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "removed", PRESENTATION: "unchanged"})
        self.assertEqual(seen, [True], "the backup must exist, with the shipped bytes, when the file is deleted")
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())
        self.assertTrue((self.project_rules_dir / PRESENTATION).is_file())
        self.assertEqual(backup.read_bytes(), _shipped_bytes(LANGUAGE))
        log = (self.backup_root() / "DISPOSITIONS.md").read_text(encoding="utf-8")
        self.assertIn("removed", log)
        self.assertEqual(
            [line.split(" — ")[0] for line in sr.format_reconcile_lines(rows)],
            [f"Style rule {LANGUAGE}: removed"],
        )

    def test_a_failed_backup_gives_preserved_and_the_file_stays(self):
        sr.install_style_rules(self.cfg)
        self.write_style_config(plain_language="off")

        with mock.patch.object(upgrade_io, "_write_backup_preimage", return_value=False):
            rows = self.reconcile()

        self.assertEqual(_dispositions(rows)[LANGUAGE], "preserved")
        self.assertIn("backup", {name: detail for name, _d, detail in rows}[LANGUAGE])
        self.assertEqual((self.project_rules_dir / LANGUAGE).read_bytes(), _shipped_bytes(LANGUAGE))

    def test_on_to_off_with_an_edited_copy_is_preserved_and_reported(self):
        self.project_rules_dir.mkdir(parents=True)
        edited = _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))
        self.write_style_config(plain_language="off", plain_presentation="on")

        rows = self.reconcile()

        self.assertEqual(_dispositions(rows)[LANGUAGE], "preserved")
        self.assertEqual(edited.read_bytes(), _customized_bytes(LANGUAGE))
        lines = sr.format_reconcile_lines(rows)
        self.assertTrue(any(line.startswith(f"Style rule {LANGUAGE}: preserved") for line in lines), lines)
        self.assertFalse(self.backup_root().exists())

    def test_off_to_on_installs_the_rule(self):
        self.write_style_config(plain_language="off", plain_presentation="off")
        self.assertEqual(_dispositions(self.reconcile()), {LANGUAGE: "skipped", PRESENTATION: "skipped"})
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())

        self.write_style_config(plain_language="on", plain_presentation="off")
        rows = self.reconcile()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "installed", PRESENTATION: "skipped"})
        self.assertEqual((self.project_rules_dir / LANGUAGE).read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertFalse((self.project_rules_dir / PRESENTATION).exists())

    def test_both_off_and_both_absent_is_skipped_and_nothing_happens(self):
        self.write_style_config(plain_language="off", plain_presentation="off")

        rows = self.reconcile()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "skipped", PRESENTATION: "skipped"})
        self.assertEqual(sr.format_reconcile_lines(rows), [])
        self.assertFalse(self.project_rules_dir.exists())
        self.assertFalse(self.backup_root().exists())

    def test_a_version_change_run_keeps_an_edited_copy_whose_key_is_off(self):
        self.write_pin(OLD_VERSION, style={"plain_language": "off", "plain_presentation": "on"})
        edited = _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))

        code, out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        self.assertEqual(edited.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertIn(f"Style rule {LANGUAGE}: preserved", out)
        self.assertFalse(self.backup_root().joinpath(".claude", "rules", "planwise", LANGUAGE).exists())

    def test_a_version_change_run_removes_an_identical_copy_whose_key_is_off(self):
        sr.install_style_rules(self.cfg)
        self.write_pin(OLD_VERSION, style={"plain_language": "off", "plain_presentation": "on"})

        code, out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())
        self.assertIn(f"Style rule {LANGUAGE}: removed", out)
        backup = self.backup_root() / ".claude" / "rules" / "planwise" / LANGUAGE
        self.assertEqual(backup.read_bytes(), _shipped_bytes(LANGUAGE))

    def test_an_os_error_on_one_rule_gives_failed_and_the_other_rule_still_reconciles(self):
        sr.install_style_rules(self.cfg)
        (self.project_rules_dir / PRESENTATION).unlink()
        self.write_style_config(plain_language="off", plain_presentation="on")
        real_unlink = Path.unlink

        def failing_unlink(path, *args, **kwargs):
            if path.name == LANGUAGE:
                raise PermissionError(13, "Permission denied")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", failing_unlink):
            rows = self.reconcile()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "failed", PRESENTATION: "installed"})
        self.assertIn("Permission denied", {name: detail for name, _d, detail in rows}[LANGUAGE])
        self.assertTrue((self.project_rules_dir / LANGUAGE).is_file())
        self.assertTrue((self.project_rules_dir / PRESENTATION).is_file())
        self.assertTrue(any(line.startswith(f"Style rule {LANGUAGE}: failed") for line in sr.format_reconcile_lines(rows)))


class TestUpgradeAtCurrentPin(_UpgradeFixtureBase):
    """`_run_upgrade` with the pinned version equal to the target: a key change works without a version change."""

    def test_on_to_off_with_an_identical_copy_removes_it(self):
        sr.install_style_rules(self.cfg)
        self.write_pin(TARGET_VERSION, style={"plain_language": "off", "plain_presentation": "on"})

        out = self.run_pinned()

        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())
        self.assertTrue((self.project_rules_dir / PRESENTATION).is_file())
        self.assertIn(f"Style rule {LANGUAGE}: removed", out)
        # At a current pin the version pair is the target twice.
        backup = self.backup_root(CURRENT_PAIR_DIR) / ".claude" / "rules" / "planwise" / LANGUAGE
        self.assertEqual(backup.read_bytes(), _shipped_bytes(LANGUAGE))

    def test_off_to_on_installs_the_rule(self):
        self.write_pin(TARGET_VERSION, style={"plain_language": "off", "plain_presentation": "off"})
        out = self.run_pinned()
        self.assertEqual(_style_lines(out), [])
        self.assertFalse(self.project_rules_dir.exists())

        self.write_pin(TARGET_VERSION, style={"plain_language": "on", "plain_presentation": "off"})
        out = self.run_pinned()

        self.assertEqual((self.project_rules_dir / LANGUAGE).read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertFalse((self.project_rules_dir / PRESENTATION).exists())
        self.assertIn(f"Style rule {LANGUAGE}: installed", out)

    def test_key_on_and_copy_absent_is_installed(self):
        self.write_pin(TARGET_VERSION)

        out = self.run_pinned()

        for filename in BOTH:
            self.assertEqual((self.project_rules_dir / filename).read_bytes(), _shipped_bytes(filename), filename)
            self.assertIn(f"Style rule {filename}: installed", out)

    def test_an_agreeing_state_writes_no_file_and_prints_no_style_rule_line(self):
        sr.install_style_rules(self.cfg)
        self.write_pin(TARGET_VERSION, style={"plain_language": "on", "plain_presentation": "on"})
        before = {filename: self.snapshot(self.project_rules_dir / filename) for filename in BOTH}

        out = self.run_pinned()

        self.assertNotIn("Style rule", out)
        for filename in BOTH:
            self.assertEqual(self.snapshot(self.project_rules_dir / filename), before[filename], filename)
        self.assertFalse(self.backup_root(CURRENT_PAIR_DIR).exists())

        # Both keys off and both files absent also agree.
        shutil.rmtree(self.project_rules_dir)
        self.write_pin(TARGET_VERSION, style={"plain_language": "off", "plain_presentation": "off"})
        out = self.run_pinned()
        self.assertNotIn("Style rule", out)
        self.assertFalse(self.project_rules_dir.exists())

    def test_an_edited_copy_under_an_on_key_is_reported_customized_and_its_bytes_do_not_change(self):
        self.write_pin(TARGET_VERSION)
        edited = _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))

        out = self.run_pinned()

        self.assertIn(f"Style rule {LANGUAGE}: customized", out)
        self.assertEqual(edited.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertFalse((self.project_root / self.cfg.planwise_root / "upgrade-conflicts").exists())


class TestUpgradeRefresh(_UpgradeFixtureBase):
    """A version-change refresh of a managed copy, against a temporary plugin tree whose shipped copy differs."""

    def setUp(self):
        super().setUp()
        self.plugin = self.tmp / "plugin"
        (self.plugin / "references").mkdir(parents=True)
        (self.plugin / "references" / LANGUAGE).write_bytes(_grown_bytes(LANGUAGE))
        (self.plugin / "references" / PRESENTATION).write_bytes(_shipped_bytes(PRESENTATION))
        self.refresh_cfg = self.make_cfg("project", plugin_root=self.plugin)
        self.dst = self.project_rules_dir / LANGUAGE

    def refresh(self):
        return au.upgrade_artifacts(self.refresh_cfg, {"artifacts": []}, OLD_VERSION, TARGET_VERSION)

    def conflict_dir(self) -> Path:
        return self.project_root / self.cfg.planwise_root / "upgrade-conflicts" / PAIR_DIR

    def test_an_untouched_installed_copy_is_refreshed_to_the_new_shipped_bytes_with_no_paths_line(self):
        _put(self.dst, _shipped_bytes(LANGUAGE))
        _put(self.project_rules_dir / PRESENTATION, _shipped_bytes(PRESENTATION))

        refreshed, unchanged, conflicts, untracked, subsets, transferred = self.refresh()

        self.assertEqual(refreshed, [str(self.dst)])
        self.assertEqual(subsets, [str(self.dst)])
        # The style loop records only what it changes, so an identical copy is not listed.
        self.assertEqual(unchanged, [])
        self.assertEqual((self.project_rules_dir / PRESENTATION).read_bytes(), _shipped_bytes(PRESENTATION))
        self.assertEqual((conflicts, untracked, transferred), ([], [], []))
        self.assertEqual(_lf(self.dst.read_bytes()), _lf(_grown_bytes(LANGUAGE)))
        self.assertNotRegex(self.dst.read_text(encoding="utf-8"), r"(?m)^\s*paths:")
        backup = self.backup_root() / ".claude" / "rules" / "planwise" / LANGUAGE
        self.assertEqual(backup.read_bytes(), _shipped_bytes(LANGUAGE))

    def test_an_edited_copy_under_report_and_relocate_is_transferred_and_then_adopted(self):
        self.write_pin(OLD_VERSION, handoff="report+relocate")
        _put(self.dst, _customized_bytes(LANGUAGE))

        refreshed, _unchanged, conflicts, _untracked, _subsets, transferred = self.refresh()

        self.assertEqual(conflicts, [])
        self.assertEqual(refreshed, [str(self.dst)])
        self.assertEqual(len(transferred), 1)
        self.assertEqual(transferred[0][0], str(self.dst))
        transfer = Path(transferred[0][1])
        self.assertIn("A Local Section", transfer.read_text(encoding="utf-8"))
        self.assertEqual(_lf(self.dst.read_bytes()), _lf(_grown_bytes(LANGUAGE)))
        backup = self.backup_root() / ".claude" / "rules" / "planwise" / LANGUAGE
        self.assertEqual(backup.read_bytes(), _customized_bytes(LANGUAGE))

    def test_an_edited_copy_under_report_gets_a_sidecar_and_the_installed_file_is_unchanged(self):
        self.write_pin(OLD_VERSION, handoff="report")
        _put(self.dst, _customized_bytes(LANGUAGE))
        sidecar = self.conflict_dir() / ".claude" / "rules" / "planwise" / f"{LANGUAGE}.new"

        refreshed, _unchanged, conflicts, _untracked, _subsets, transferred = self.refresh()

        self.assertEqual(conflicts, [(str(self.dst), str(sidecar))])
        self.assertEqual((refreshed, transferred), ([], []))
        self.assertEqual(self.dst.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(_lf(sidecar.read_bytes()), _lf(_grown_bytes(LANGUAGE)))
        index = (self.conflict_dir() / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn(str(self.dst), index)
        self.assertIn(str(sidecar), index)
        self.assertFalse((self.project_root / self.cfg.planwise_root / "upgrade-transfers").exists())

    def test_an_edited_copy_is_never_overwritten_without_a_verified_transfer(self):
        self.write_pin(OLD_VERSION, handoff="report+relocate")
        _put(self.dst, _customized_bytes(LANGUAGE))

        with mock.patch.object(au, "_transfer_customization", return_value=None):
            refreshed, _unchanged, conflicts, _untracked, _subsets, transferred = self.refresh()

        self.assertEqual((refreshed, transferred), ([], []))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(self.dst.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertTrue(Path(conflicts[0][1]).is_file())


class TestUpgradeScopeAndDuplicates(_UpgradeFixtureBase):
    """The install scope picks the tree, and a same-name copy elsewhere stops the install."""

    def test_user_scope_installs_under_the_redirected_home_and_writes_nothing_under_the_project(self):
        cfg = self.make_cfg("user")

        rows = self.reconcile(cfg)

        self.assertEqual(_dispositions(rows), {LANGUAGE: "installed", PRESENTATION: "installed"})
        for filename in BOTH:
            self.assertEqual((self.home_rules_dir / filename).read_bytes(), _shipped_bytes(filename), filename)
        self.assertFalse(self.project_rules_dir.exists())
        self.assertEqual(list(self.project_root.rglob("*")), [])

    def test_user_scope_removes_under_the_redirected_home_and_writes_nothing_under_the_project_rules_dir(self):
        cfg = self.make_cfg("user")
        sr.install_style_rules(cfg)
        self.write_style_config(plain_language="off", plain_presentation="on")

        rows = self.reconcile(cfg)

        self.assertEqual(_dispositions(rows), {LANGUAGE: "removed", PRESENTATION: "unchanged"})
        self.assertFalse((self.home_rules_dir / LANGUAGE).exists())
        self.assertTrue((self.home_rules_dir / PRESENTATION).is_file())
        self.assertFalse(self.project_rules_dir.exists())
        # A path outside the project is backed up under its bare file name.
        self.assertEqual((self.backup_root() / LANGUAGE).read_bytes(), _shipped_bytes(LANGUAGE))

    def _assert_a_top_level_copy_gives_duplicate(self, base: Path) -> None:
        existing = self.write_top_level_copy(base, LANGUAGE, _shipped_bytes(LANGUAGE))

        rows = self.reconcile()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "duplicate", PRESENTATION: "installed"})
        self.assertFalse((self.project_rules_dir / LANGUAGE).exists())
        self.assertTrue((self.project_rules_dir / PRESENTATION).is_file())
        self.assertEqual(existing.read_bytes(), _shipped_bytes(LANGUAGE))
        line = next(line for line in sr.format_reconcile_lines(rows) if LANGUAGE in line)
        self.assertTrue(line.startswith(f"Style rule {LANGUAGE}: duplicate — "), line)
        self.assertIn(str(existing), line)
        self.assertEqual(line.count("Style rule"), 1, "the duplicate line must not repeat its prefix")

    def test_a_same_name_top_level_copy_in_the_project_gives_duplicate_and_no_install(self):
        self._assert_a_top_level_copy_gives_duplicate(self.project_root)

    def test_a_same_name_top_level_copy_in_the_redirected_home_gives_duplicate_and_no_install(self):
        self._assert_a_top_level_copy_gives_duplicate(self.home)

    def _style_helper_calls(self, cfg) -> list:
        """The calls `upgrade_artifacts` makes to the diverged-copy helper."""
        with mock.patch.object(au, "_resolve_diverged_rule") as helper:
            au.upgrade_artifacts(cfg, {"artifacts": []}, OLD_VERSION, TARGET_VERSION)
        return helper.call_args_list

    def _assert_the_managed_copy_reaches_the_helper(self, cfg, managed: Path) -> None:
        calls = self._style_helper_calls(cfg)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[4], managed)

    def test_a_rule_with_a_project_top_level_copy_still_passes_its_managed_copy_to_the_diverged_copy_helper(self):
        _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))
        self.write_top_level_copy(self.project_root, LANGUAGE, _shipped_bytes(LANGUAGE))

        self._assert_the_managed_copy_reaches_the_helper(self.cfg, self.project_rules_dir / LANGUAGE)

    def test_a_rule_with_a_home_top_level_copy_still_passes_its_managed_copy_to_the_diverged_copy_helper(self):
        _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))
        self.write_top_level_copy(self.home, LANGUAGE, _shipped_bytes(LANGUAGE))

        self._assert_the_managed_copy_reaches_the_helper(self.cfg, self.project_rules_dir / LANGUAGE)

    def test_a_user_scope_rule_with_a_project_tree_copy_still_passes_its_managed_copy_to_the_diverged_copy_helper(self):
        cfg = self.make_cfg("user")
        _put(self.home_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))
        self.write_top_level_copy(self.project_root, LANGUAGE, _customized_bytes(LANGUAGE))

        self._assert_the_managed_copy_reaches_the_helper(cfg, self.home_rules_dir / LANGUAGE)

    def test_a_rule_with_a_managed_copy_in_the_other_scope_is_never_passed_to_the_diverged_copy_helper(self):
        _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))
        _put(self.home_rules_dir / LANGUAGE, _shipped_bytes(LANGUAGE))

        self.assertEqual(self._style_helper_calls(self.cfg), [])

        cfg = self.make_cfg("user")

        self.assertEqual(self._style_helper_calls(cfg), [])

    def test_a_lone_managed_copy_with_no_other_copy_still_reaches_the_diverged_copy_helper(self):
        _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))

        calls = self._style_helper_calls(self.cfg)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[3], LANGUAGE)
        self.assertEqual(calls[0].args[4], self.project_rules_dir / LANGUAGE)


class TestUpgradeAnnouncement(_UpgradeFixtureBase):
    """The one-time notice, printed by the run that adds the `style:` block."""

    def _announcement_in(self, out: str) -> list[str]:
        lines = out.splitlines()
        start = lines.index(ANNOUNCEMENT_FIRST_LINE)
        return lines[start:start + 6]

    def test_the_six_lines_appear_once_when_the_block_was_added(self):
        self.write_pin(OLD_VERSION)

        code, out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines().count(ANNOUNCEMENT_FIRST_LINE), 1, out)
        notice = self._announcement_in(out)
        self.assertEqual(len(notice), 6)
        self.assertEqual(notice, sr.style_announcement(self.cfg, ["style"]))

    def test_the_lines_carry_both_token_numbers_and_both_key_names(self):
        tokens = [read_limits.estimate_tokens((REFERENCES / name).stat().st_size) for name in BOTH]

        notice = sr.style_announcement(self.cfg, ["style"])

        self.assertEqual(len(notice), 6)
        self.assertIn(LANGUAGE, notice[1])
        self.assertIn(f"about {tokens[0]} tokens per session", notice[1])
        self.assertIn(PRESENTATION, notice[2])
        self.assertIn(f"about {tokens[1]} tokens per session", notice[2])
        self.assertIn(f"about {sum(tokens)} tokens", notice[3])
        self.assertIn("style.plain_language", notice[5])
        self.assertIn("style.plain_presentation", notice[5])

    def test_the_config_path_line_uses_the_projects_own_planwise_root_name(self):
        notice = sr.style_announcement(self.cfg, ["style"])
        self.assertIn("planwise/config.yaml", notice[4])

        renamed = ip.InitConfig(
            project_name="StyleFixture",
            project_root=self.project_root,
            plugin_root=PLUGIN_ROOT,
            planwise_root="docs-root",
            plugin_version=TARGET_VERSION,
        )
        notice = sr.style_announcement(renamed, ["style"])
        self.assertIn("docs-root/config.yaml", notice[4])
        self.assertNotIn("planwise/config.yaml", notice[4])

    def test_no_announcement_prints_when_the_block_was_already_present(self):
        self.write_pin(OLD_VERSION, style={"plain_language": "on", "plain_presentation": "on"})

        code, out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        self.assertNotIn(ANNOUNCEMENT_FIRST_LINE, out)
        self.assertEqual(sr.style_announcement(self.cfg, ["context"]), [])
        self.assertEqual(sr.style_announcement(self.cfg, None), [])

    def test_no_announcement_prints_on_a_current_pin_run(self):
        self.write_pin(TARGET_VERSION)

        out = self.run_pinned()

        self.assertNotIn(ANNOUNCEMENT_FIRST_LINE, out)


class TestUntrackedAllowlist(_UpgradeFixtureBase):
    """A style file is never listed as untracked, whatever its key reads."""

    def untracked(self, cfg=None) -> list[str]:
        return au.upgrade_artifacts(cfg or self.cfg, {"artifacts": []}, OLD_VERSION, TARGET_VERSION)[3]

    def test_an_edited_style_file_kept_under_an_off_key_is_not_listed_as_untracked(self):
        self.write_style_config(plain_language="off", plain_presentation="on")
        edited = _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))

        self.assertEqual(self.untracked(), [])
        self.assertEqual(edited.read_bytes(), _customized_bytes(LANGUAGE))

    def test_a_stray_unrelated_file_in_the_rules_directory_is_still_listed(self):
        self.write_style_config(plain_language="off", plain_presentation="on")
        _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))
        stray = _put(self.project_rules_dir / "stray-notes.md", b"# not a planwise rule\n")

        self.assertEqual(self.untracked(), [str(stray)])

    def test_a_project_scope_style_file_in_the_project_planwise_directory_is_not_listed_at_user_scope(self):
        cfg = self.make_cfg("user")
        _put(self.project_rules_dir / LANGUAGE, _shipped_bytes(LANGUAGE))

        self.assertEqual(self.untracked(cfg), [])


class TestCrossScopeSync(_UpgradeFixtureBase):
    """One copy of an enabled rule across the project and home trees: edits win, else the shipped file."""

    def sync(self):
        return sr.sync_cross_scope(self.cfg, OLD_VERSION, TARGET_VERSION)

    def pair(self, project_data: bytes, home_data: bytes) -> tuple[Path, Path]:
        return (
            _put(self.project_rules_dir / LANGUAGE, project_data),
            _put(self.home_rules_dir / LANGUAGE, home_data),
        )

    def test_exactly_one_edited_copy_reaches_the_other_copy_and_the_overwritten_copy_is_backed_up(self):
        project_copy, home_copy = self.pair(_customized_bytes(LANGUAGE), _shipped_bytes(LANGUAGE))

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "synced"})
        self.assertEqual(home_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        # The overwritten copy sits outside the project, so its backup carries the bare file name.
        self.assertEqual((self.backup_root() / LANGUAGE).read_bytes(), _shipped_bytes(LANGUAGE))

    def test_the_edit_also_travels_from_the_home_copy_to_the_project_copy(self):
        project_copy, home_copy = self.pair(_shipped_bytes(LANGUAGE), _customized_bytes(LANGUAGE))

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "synced"})
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(home_copy.read_bytes(), _customized_bytes(LANGUAGE))
        backup = self.backup_root() / ".claude" / "rules" / "planwise" / LANGUAGE
        self.assertEqual(backup.read_bytes(), _shipped_bytes(LANGUAGE))

    def test_neither_copy_edited_both_copies_end_with_the_shipped_bytes(self):
        older = _stale_subset_bytes(LANGUAGE)
        oldest = _shipped_bytes(LANGUAGE).split(b"\n## Structure")[0] + b"\n"
        self.assertNotEqual(older, oldest)
        project_copy, home_copy = self.pair(older, oldest)

        rows = self.sync()

        self.assertEqual([disposition for _name, disposition, _detail in rows], ["synced", "synced"])
        self.assertEqual(project_copy.read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertEqual(home_copy.read_bytes(), _shipped_bytes(LANGUAGE))

    def test_two_different_edits_change_neither_file_and_the_conflict_names_both_paths(self):
        project_copy, home_copy = self.pair(
            _shipped_bytes(LANGUAGE) + b"\n## Project Edit\n- Only the project copy holds this.\n",
            _shipped_bytes(LANGUAGE) + b"\n## Home Edit\n- Only the home copy holds this.\n",
        )
        before = (project_copy.read_bytes(), home_copy.read_bytes())

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "conflict"})
        self.assertEqual((project_copy.read_bytes(), home_copy.read_bytes()), before)
        self.assertIn(str(project_copy), rows[0][2])
        self.assertIn(str(home_copy), rows[0][2])
        self.assertFalse(self.backup_root().exists())

    def test_two_byte_identical_copies_are_not_written(self):
        project_copy, home_copy = self.pair(_customized_bytes(LANGUAGE), _customized_bytes(LANGUAGE))
        before = (self.snapshot(project_copy), self.snapshot(home_copy))

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "unchanged"})
        self.assertEqual(sr.format_reconcile_lines(rows), [])
        self.assertEqual((self.snapshot(project_copy), self.snapshot(home_copy)), before)
        self.assertFalse(self.backup_root().exists())

    def test_the_sync_runs_at_a_current_pin_through_run_upgrade_and_config_bytes_do_not_change(self):
        project_copy, home_copy = self.pair(_customized_bytes(LANGUAGE), _shipped_bytes(LANGUAGE))
        self.write_pin(TARGET_VERSION)

        out = self.run_pinned()

        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(home_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertIn(f"Style rule {LANGUAGE}: synced", out)

    def test_an_off_key_never_syncs(self):
        self.write_style_config(plain_language="off", plain_presentation="on")
        project_copy, home_copy = self.pair(_customized_bytes(LANGUAGE), _shipped_bytes(LANGUAGE))

        self.assertEqual(self.sync(), [])

        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(home_copy.read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertFalse(self.backup_root().exists())

    def test_same_name_copies_outside_the_managed_paths_are_named_and_never_touched(self):
        project_copy, home_copy = self.pair(_customized_bytes(LANGUAGE), _shipped_bytes(LANGUAGE))
        second_project = _put(self.project_root / ".claude" / "rules" / "sub" / LANGUAGE, b"# a second project copy\n")
        second_home = _put(self.home / ".claude" / "rules" / "elsewhere" / LANGUAGE, b"# a second home copy\n")

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "synced"})
        for path in (second_project, second_home):
            self.assertIn(str(path), rows[0][2])
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(home_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(second_project.read_bytes(), b"# a second project copy\n")
        self.assertEqual(second_home.read_bytes(), b"# a second home copy\n")

    def _assert_a_project_tree_edit_survives_a_version_change_run(self, handoff: str) -> None:
        cfg = self.make_cfg("user")
        self.write_pin(OLD_VERSION, handoff=handoff)
        project_copy = self.write_top_level_copy(self.project_root, LANGUAGE, _customized_bytes(LANGUAGE))

        code, out, err = self.run_upgrade(cfg)

        self.assertEqual(code, 0, err)
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        # The project-tree copy is outside the managed path, so the sync never copies it to the global copy.
        self.assertEqual((self.home_rules_dir / LANGUAGE).read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertNotIn("Customizations transferred", out)
        self.assertNotIn("Conflicts", out)
        transfers = self.project_root / cfg.planwise_root / "upgrade-transfers"
        self.assertEqual(list(transfers.rglob("*.md")) if transfers.exists() else [], [])

    def test_at_user_scope_a_project_tree_edit_survives_a_version_change_run_under_report(self):
        self._assert_a_project_tree_edit_survives_a_version_change_run("report")

    def test_at_user_scope_a_project_tree_edit_survives_a_version_change_run_under_report_and_relocate(self):
        self._assert_a_project_tree_edit_survives_a_version_change_run("report+relocate")

    def test_an_identical_unedited_stale_pair_ends_with_the_shipped_bytes_and_each_overwrite_is_backed_up(self):
        stale = _stale_subset_bytes(LANGUAGE)
        project_copy, home_copy = self.pair(stale, stale)

        rows = self.sync()

        self.assertEqual([disposition for _name, disposition, _detail in rows], ["synced", "synced"])
        self.assertEqual(project_copy.read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertEqual(home_copy.read_bytes(), _shipped_bytes(LANGUAGE))
        backups = sorted(self.backup_root().rglob(LANGUAGE))
        self.assertEqual(len(backups), 2, backups)
        for backup in backups:
            self.assertEqual(backup.read_bytes(), stale, backup)
        self.assertEqual(_dispositions(self.sync()), {LANGUAGE: "unchanged"})

    def test_a_failed_sync_backup_gives_failed_and_the_target_is_not_overwritten(self):
        project_copy, home_copy = self.pair(_customized_bytes(LANGUAGE), _shipped_bytes(LANGUAGE))

        with mock.patch.object(upgrade_io, "_write_backup_preimage", return_value=False):
            rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "failed"})
        self.assertEqual(home_copy.read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertTrue(any(line.startswith(f"Style rule {LANGUAGE}: failed") for line in sr.format_reconcile_lines(rows)))


class TestReviewFixes(_UpgradeFixtureBase):
    """Regression tests for ten defects found by an adversarial review of the upgrade seam."""

    def sync(self):
        return sr.sync_cross_scope(self.cfg, OLD_VERSION, TARGET_VERSION)

    def pair(self, project_data: bytes, home_data: bytes) -> tuple[Path, Path]:
        return (
            _put(self.project_rules_dir / LANGUAGE, project_data),
            _put(self.home_rules_dir / LANGUAGE, home_data),
        )

    @staticmethod
    def with_paths(data: bytes) -> bytes:
        """The rule with a `paths:` key added inside its existing frontmatter block."""
        text = _lf(data)
        assert text.startswith(b"---\n"), "the shipped rule is expected to carry frontmatter"
        return text.replace(b"---\n", b'---\npaths: "src/**"\n', 1)

    @contextlib.contextmanager
    def symlinked(self, *targets: Path):
        """Make `Path.is_symlink` report True for `targets`, so the test needs no symlink privilege."""
        real = Path.is_symlink

        def fake(path):
            return path in targets or real(path)

        with mock.patch.object(Path, "is_symlink", fake):
            yield

    def stderr_of(self, call):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = call()
        return result, err.getvalue()

    # -- 1. the sync reads and writes the two managed paths only ----------------

    def test_a_project_tree_copy_outside_the_managed_path_is_never_a_source_for_the_global_copy(self):
        deep = _put(self.project_root / ".claude" / "rules" / "sub" / LANGUAGE, _customized_bytes(LANGUAGE))
        home_copy = _put(self.home_rules_dir / LANGUAGE, _shipped_bytes(LANGUAGE))

        rows = self.sync()

        self.assertEqual(rows, [])
        self.assertEqual(home_copy.read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertEqual(deep.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertFalse(self.backup_root().exists())

    def test_a_home_tree_copy_outside_the_managed_path_is_never_a_target_for_the_project_copy(self):
        project_copy = _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))
        deep = _put(self.home / ".claude" / "rules" / "elsewhere" / LANGUAGE, _shipped_bytes(LANGUAGE))

        self.assertEqual(self.sync(), [])

        self.assertEqual(deep.read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertFalse(self.backup_root().exists())

    def test_other_same_name_copies_are_named_in_the_row_and_do_not_make_a_conflict(self):
        project_copy, home_copy = self.pair(_customized_bytes(LANGUAGE), _shipped_bytes(LANGUAGE))
        deep_project = _put(self.project_root / ".claude" / "rules" / "sub" / LANGUAGE, b"# a deep project copy\n")
        deep_home = _put(self.home / ".claude" / "rules" / "elsewhere" / LANGUAGE, b"# a deep home copy\n")

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "synced"})
        self.assertEqual(home_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(deep_project.read_bytes(), b"# a deep project copy\n")
        self.assertEqual(deep_home.read_bytes(), b"# a deep home copy\n")
        self.assertIn(str(deep_project), rows[0][2])
        self.assertIn(str(deep_home), rows[0][2])

    # -- 2. what counts as an edit ---------------------------------------------

    def test_a_paths_only_edit_counts_as_an_edit_and_reaches_the_other_copy(self):
        edited = self.with_paths(_shipped_bytes(LANGUAGE))
        project_copy, home_copy = self.pair(edited, _stale_subset_bytes(LANGUAGE))

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "synced"})
        self.assertEqual(project_copy.read_bytes(), edited)
        self.assertEqual(home_copy.read_bytes(), edited)

    def test_a_subset_verdict_below_exact_or_contained_confidence_counts_as_an_edit(self):
        reorg = types.SimpleNamespace(classification="SUBSET", confidence="reorg", notes="", source="inline")
        project_copy, home_copy = self.pair(_customized_bytes(LANGUAGE), _shipped_bytes(LANGUAGE))

        with mock.patch.object(rd, "_classify_diverged", return_value=reorg):
            rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "synced"})
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(home_copy.read_bytes(), _customized_bytes(LANGUAGE))

    # -- 3. the refresh keeps an installed paths value --------------------------

    def test_the_style_refresh_keeps_a_user_added_paths_line(self):
        self.write_pin(OLD_VERSION, handoff="report+relocate")
        dst = _put(self.project_rules_dir / LANGUAGE, self.with_paths(_stale_subset_bytes(LANGUAGE)))

        code, _out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        text = _lf(dst.read_bytes()).decode("utf-8")
        self.assertIn('paths: "src/**"', text.split("\n---\n")[0])
        self.assertIn("## Honesty", text)

    # -- 4. the customized detail tells the truth for each exit -----------------

    def test_a_version_change_run_does_not_say_the_edited_copy_is_kept(self):
        self.write_pin(OLD_VERSION, handoff="report+relocate")
        _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))

        code, out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        lines = [line for line in _style_lines(out) if line.startswith(f"Style rule {LANGUAGE}: customized")]
        self.assertEqual(len(lines), 1, out)
        self.assertNotIn("is kept", lines[0])
        self.assertIn("customization handoff", lines[0])

    def test_a_current_pin_run_says_the_edited_copy_is_kept(self):
        self.write_pin(TARGET_VERSION)
        copy = _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))

        out = self.run_pinned()

        lines = [line for line in _style_lines(out) if line.startswith(f"Style rule {LANGUAGE}: customized")]
        self.assertEqual(len(lines), 1, out)
        self.assertIn("is kept", lines[0])
        self.assertEqual(copy.read_bytes(), _customized_bytes(LANGUAGE))

    # -- 5. a backup is never overwritten ---------------------------------------

    def test_a_second_backup_with_different_bytes_takes_the_first_free_suffix(self):
        dst = _put(self.project_rules_dir / LANGUAGE, b"first\n")
        backup = self.backup_root() / ".claude" / "rules" / "planwise" / LANGUAGE
        args = (self.cfg, OLD_VERSION, TARGET_VERSION, dst)

        self.assertTrue(upgrade_io._write_backup_preimage(*args))
        self.assertEqual(backup.read_bytes(), b"first\n")
        before = backup.stat().st_mtime_ns

        dst.write_bytes(b"second\n")
        self.assertTrue(upgrade_io._write_backup_preimage(*args))
        self.assertEqual(backup.read_bytes(), b"first\n")
        self.assertEqual(backup.with_name(f"{LANGUAGE}.1").read_bytes(), b"second\n")

        self.assertTrue(upgrade_io._write_backup_preimage(*args))
        self.assertFalse(backup.with_name(f"{LANGUAGE}.2").exists())

        dst.write_bytes(b"third\n")
        self.assertTrue(upgrade_io._write_backup_preimage(*args))
        self.assertEqual(backup.with_name(f"{LANGUAGE}.2").read_bytes(), b"third\n")
        self.assertEqual(backup.stat().st_mtime_ns, before)

    def test_a_backup_of_identical_bytes_is_not_rewritten(self):
        dst = _put(self.project_rules_dir / LANGUAGE, b"same\n")
        backup = self.backup_root() / ".claude" / "rules" / "planwise" / LANGUAGE
        self.assertTrue(upgrade_io._write_backup_preimage(self.cfg, OLD_VERSION, TARGET_VERSION, dst))
        before = backup.stat().st_mtime_ns

        self.assertTrue(upgrade_io._write_backup_preimage(self.cfg, OLD_VERSION, TARGET_VERSION, dst))

        self.assertEqual(backup.stat().st_mtime_ns, before)
        self.assertEqual(sorted(p.name for p in backup.parent.iterdir()), [LANGUAGE])

    # -- 6. a symlinked copy is never written or deleted ------------------------

    def test_the_sync_does_not_overwrite_a_symlinked_copy_and_reports_it(self):
        project_copy, home_copy = self.pair(_customized_bytes(LANGUAGE), _shipped_bytes(LANGUAGE))

        with self.symlinked(home_copy):
            rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "symlink"})
        self.assertIn(str(home_copy), rows[0][2])
        self.assertEqual(home_copy.read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertFalse(self.backup_root().exists())

    def test_the_sync_does_not_write_through_a_real_symlink(self):
        project_copy = _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))
        real_target = _put(self.tmp / "elsewhere" / LANGUAGE, _shipped_bytes(LANGUAGE))
        link = self.home_rules_dir / LANGUAGE
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(real_target, link)
        except (OSError, NotImplementedError):
            self.skipTest("this account cannot create symlinks")

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "symlink"})
        self.assertEqual(real_target.read_bytes(), _shipped_bytes(LANGUAGE))
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))

    def test_the_removal_does_not_delete_a_symlinked_copy_and_reports_it(self):
        self.write_style_config(plain_language="off", plain_presentation="on")
        copy = _put(self.project_rules_dir / LANGUAGE, _shipped_bytes(LANGUAGE))

        with self.symlinked(copy):
            rows = self.reconcile()

        self.assertEqual(_dispositions(rows)[LANGUAGE], "symlink")
        self.assertIn(str(copy), {name: detail for name, _d, detail in rows}[LANGUAGE])
        self.assertTrue(copy.is_file())
        self.assertFalse(self.backup_root().exists())

    def test_the_style_refresh_does_not_rewrite_a_symlinked_copy(self):
        self.write_pin(OLD_VERSION, handoff="report+relocate")
        copy = _put(self.project_rules_dir / LANGUAGE, _stale_subset_bytes(LANGUAGE))

        with self.symlinked(copy):
            code, out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        self.assertEqual(copy.read_bytes(), _stale_subset_bytes(LANGUAGE))
        self.assertNotIn("Customizations transferred", out)
        self.assertFalse(self.backup_root().exists())

    # -- 7. a malformed switch warns and means on -------------------------------

    def test_a_malformed_value_and_an_unknown_key_each_warn_once_and_mean_on(self):
        self.write_config("style:\n  plain_language: 0\n  plain_languge: maybe\n  plain_presentation: on\n")

        rows, err = self.stderr_of(self.reconcile)

        self.assertEqual(_dispositions(rows), {LANGUAGE: "installed", PRESENTATION: "installed"})
        warnings = [line for line in err.splitlines() if "Warning" in line]
        self.assertEqual(len(warnings), 2, err)
        bad_value = [line for line in warnings if "plain_language" in line and "plain_languge" not in line]
        bad_key = [line for line in warnings if "plain_languge" in line]
        self.assertEqual((len(bad_value), len(bad_key)), (1, 1), err)
        self.assertIn("0", bad_value[0])
        self.assertIn("maybe", bad_key[0])
        for line in warnings:
            self.assertIn("treated as on", line)

    def test_a_style_value_that_is_not_a_block_warns_and_means_on(self):
        self.write_config("style: off\n")

        rows, err = self.stderr_of(self.reconcile)

        self.assertEqual(_dispositions(rows), {LANGUAGE: "installed", PRESENTATION: "installed"})
        warnings = [line for line in err.splitlines() if "Warning" in line]
        self.assertEqual(len(warnings), 1, err)
        self.assertIn("style", warnings[0])
        self.assertIn("treated as on", warnings[0])

    def test_accepted_spellings_in_any_case_and_yaml_booleans_print_no_warning(self):
        self.write_config('style:\n  plain_language: "Off"\n  plain_presentation: false\n')

        rows, err = self.stderr_of(self.reconcile)

        self.assertEqual(err, "")
        self.assertEqual(_dispositions(rows), {LANGUAGE: "skipped", PRESENTATION: "skipped"})

    def test_a_current_pin_run_warns_once_per_malformed_value(self):
        self.write_pin(TARGET_VERSION, style={"plain_language": 0, "plain_presentation": "on"})

        code, _out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        self.assertEqual(len([line for line in err.splitlines() if "style.plain_language" in line]), 1, err)

    # -- 8. an off key reports the copies that still load -----------------------

    def test_an_off_key_names_the_other_copies_that_still_load_on_a_removal(self):
        self.write_style_config(plain_language="off", plain_presentation="on")
        _put(self.project_rules_dir / LANGUAGE, _shipped_bytes(LANGUAGE))
        home_copy = _put(self.home_rules_dir / LANGUAGE, _shipped_bytes(LANGUAGE))

        rows = self.reconcile()

        by_name = {name: (disposition, detail) for name, disposition, detail in rows}
        self.assertEqual(by_name[LANGUAGE][0], "removed")
        self.assertIn(str(home_copy), by_name[LANGUAGE][1])
        self.assertIn("still load", by_name[LANGUAGE][1])
        self.assertTrue(any(str(home_copy) in line for line in sr.format_reconcile_lines(rows)))

    def test_an_off_key_with_no_managed_copy_prints_a_skipped_row_when_another_copy_loads(self):
        self.write_style_config(plain_language="off", plain_presentation="on")
        home_copy = _put(self.home_rules_dir / LANGUAGE, _shipped_bytes(LANGUAGE))

        rows = self.reconcile()

        by_name = {name: (disposition, detail) for name, disposition, detail in rows}
        self.assertEqual(by_name[LANGUAGE][0], "skipped")
        self.assertIn(str(home_copy), by_name[LANGUAGE][1])
        lines = [line for line in sr.format_reconcile_lines(rows) if line.startswith(f"Style rule {LANGUAGE}: skipped")]
        self.assertEqual(len(lines), 1, rows)
        self.assertIn("still load", lines[0])

    # -- 9. a raising reconcile on the main path never aborts the upgrade -------

    def test_a_raising_reconcile_on_the_version_change_path_warns_and_the_run_continues(self):
        self.write_pin(OLD_VERSION)

        with mock.patch.object(sr, "reconcile_style_switches", side_effect=RuntimeError("boom")):
            code, _out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        self.assertIn("boom", err)
        self.assertIn(TARGET_VERSION, (self.project_root / self.cfg.planwise_root / "config.yaml").read_text(encoding="utf-8"))

    # -- 10. the sync ignores line endings and a BOM ----------------------------

    def test_the_same_edit_saved_with_crlf_and_a_bom_is_not_a_conflict(self):
        edited = _lf(_customized_bytes(LANGUAGE))
        crlf_bom = b"\xef\xbb\xbf" + edited.replace(b"\n", b"\r\n")
        project_copy, home_copy = self.pair(crlf_bom, edited)

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "unchanged"})
        self.assertEqual(project_copy.read_bytes(), crlf_bom)
        self.assertEqual(home_copy.read_bytes(), edited)
        self.assertFalse(self.backup_root().exists())

    def test_a_copy_whose_line_endings_differ_from_shipped_is_not_rewritten(self):
        shipped = _lf(_shipped_bytes(LANGUAGE))
        crlf = shipped.replace(b"\n", b"\r\n")
        project_copy, home_copy = self.pair(crlf, shipped)

        rows = self.sync()

        self.assertEqual(_dispositions(rows), {LANGUAGE: "unchanged"})
        self.assertEqual(project_copy.read_bytes(), crlf)
        self.assertEqual(home_copy.read_bytes(), shipped)
        self.assertFalse(self.backup_root().exists())

    # -- 3b. the refresh skips only when the sync owns the file -----------------

    def test_an_unmanaged_project_copy_does_not_block_the_refresh_of_a_stale_global_copy_at_user_scope(self):
        cfg = self.make_cfg("user")
        self.write_pin(OLD_VERSION, handoff="report+relocate")
        global_copy = _put(self.home_rules_dir / LANGUAGE, _stale_subset_bytes(LANGUAGE))
        project_copy = self.write_top_level_copy(self.project_root, LANGUAGE, _customized_bytes(LANGUAGE))

        code, _out, err = self.run_upgrade(cfg)

        self.assertEqual(code, 0, err)
        self.assertEqual(_lf(global_copy.read_bytes()), _lf(_shipped_bytes(LANGUAGE)))
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))

    def test_the_refresh_leaves_a_copy_to_the_sync_when_the_other_managed_copy_exists(self):
        self.write_pin(OLD_VERSION, handoff="report+relocate")
        project_copy, home_copy = (
            _put(self.project_rules_dir / LANGUAGE, _stale_subset_bytes(LANGUAGE)),
            _put(self.home_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE)),
        )

        code, out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        self.assertEqual(project_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertEqual(home_copy.read_bytes(), _customized_bytes(LANGUAGE))
        self.assertNotIn("Customizations transferred", out)


def _paths_only_bytes(filename: str) -> bytes:
    """The shipped rule with LF endings and one `paths:` line added to its frontmatter."""
    text = _lf(_shipped_bytes(filename))
    assert text.startswith(b"---\n"), "the shipped rule is expected to carry frontmatter"
    return text.replace(b"---\n", b'---\npaths: "src/**"\n', 1)


class TestPathsOnlyEdit(_UpgradeFixtureBase):
    """A copy whose only edit is a `paths:` line is an edit, whatever the key says."""

    def _install_paths_only_copy(self) -> Path:
        return _put(self.project_rules_dir / LANGUAGE, _paths_only_bytes(LANGUAGE))

    def test_the_installed_copy_with_only_a_paths_line_reads_as_diverged(self):
        self._install_paths_only_copy()
        self.assertEqual(sr.compare_installed(self.cfg, LANGUAGE), "diverged")

    def test_a_key_that_is_off_keeps_a_copy_whose_only_edit_is_a_paths_line(self):
        copy = self._install_paths_only_copy()
        self.write_style_config(plain_language="off", plain_presentation="on")

        rows = self.reconcile()

        self.assertEqual(_dispositions(rows)[LANGUAGE], "preserved")
        self.assertTrue(copy.is_file(), "upgrade must not delete the edited copy")
        self.assertEqual(copy.read_bytes(), _paths_only_bytes(LANGUAGE))
        self.assertFalse(self.backup_root().joinpath(".claude", "rules", "planwise", LANGUAGE).exists())

    def test_a_key_that_is_on_reports_a_paths_only_copy_as_customized(self):
        copy = self._install_paths_only_copy()
        self.write_style_config(plain_language="on", plain_presentation="on")

        rows = self.reconcile()

        self.assertEqual(_dispositions(rows)[LANGUAGE], "customized")
        self.assertTrue(copy.is_file())
        self.assertEqual(copy.read_bytes(), _paths_only_bytes(LANGUAGE))

    def test_a_paths_only_duplicate_is_not_reported_as_identical(self):
        copy = self.write_top_level_copy(self.project_root, LANGUAGE, _paths_only_bytes(LANGUAGE))

        found = sr.find_existing_copy(self.cfg, LANGUAGE)

        self.assertIsNotNone(found)
        self.assertEqual(found[0], copy)
        self.assertNotEqual(found[1], "identical")
        # The verdict is one the line formatter renders as an edited copy, never an identical one.
        line = sr.format_duplicate_line(LANGUAGE, found[0], found[1])
        self.assertEqual(line, f"Style rule {LANGUAGE}: not installed, a customized copy exists at {copy}.")

    def test_a_duplicate_with_the_shipped_paths_value_and_text_is_still_identical(self):
        self.write_top_level_copy(self.project_root, LANGUAGE, _lf(_shipped_bytes(LANGUAGE)))
        found = sr.find_existing_copy(self.cfg, LANGUAGE)
        self.assertEqual(found[1], "identical")


class TestHandoffDetail(_UpgradeFixtureBase):
    """The `customized` detail names the handoff only when the refresh would run one."""

    def _detail(self, data: bytes) -> str:
        _put(self.project_rules_dir / LANGUAGE, data)
        rows = sr.reconcile_style_switches(self.cfg, OLD_VERSION, TARGET_VERSION, True)
        disposition, detail = next((d, t) for name, d, t in rows if name == LANGUAGE)
        self.assertEqual(disposition, "customized")
        return detail

    def test_a_version_change_with_a_paths_only_edit_says_the_copy_is_kept(self):
        detail = self._detail(_paths_only_bytes(LANGUAGE))
        self.assertIn("is kept", detail)
        self.assertNotIn("handoff", detail)

    def test_a_version_change_with_a_body_edit_still_names_the_handoff(self):
        detail = self._detail(_customized_bytes(LANGUAGE))
        self.assertIn("customization handoff", detail)
        self.assertNotIn("is kept", detail)

    def test_a_version_change_with_a_symlinked_body_edited_copy_says_the_copy_is_kept(self):
        copy = _put(self.project_rules_dir / LANGUAGE, _customized_bytes(LANGUAGE))
        real = Path.is_symlink

        def fake(path):
            # A real symlink needs a Windows privilege, so fake the check.
            return path == copy or real(path)

        with mock.patch.object(Path, "is_symlink", fake):
            rows = sr.reconcile_style_switches(self.cfg, OLD_VERSION, TARGET_VERSION, True)
        disposition, detail = next((d, t) for name, d, t in rows if name == LANGUAGE)
        self.assertEqual(disposition, "customized")
        self.assertIn("is kept", detail)
        self.assertNotIn("handoff", detail)

    def test_the_printed_detail_agrees_with_what_the_refresh_does_for_a_paths_only_edit(self):
        self.write_pin(OLD_VERSION, handoff="report+relocate")
        copy = _put(self.project_rules_dir / LANGUAGE, _paths_only_bytes(LANGUAGE))

        code, out, err = self.run_upgrade()

        self.assertEqual(code, 0, err)
        lines = [line for line in _style_lines(out) if line.startswith(f"Style rule {LANGUAGE}: customized")]
        self.assertEqual(len(lines), 1, out)
        self.assertIn("is kept", lines[0])
        self.assertEqual(copy.read_bytes(), _paths_only_bytes(LANGUAGE))


if __name__ == "__main__":
    unittest.main()
