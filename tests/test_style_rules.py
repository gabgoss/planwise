#!/usr/bin/env python3
"""Install-side tests for the two always-on style rules.

Covers the `style:` config reader, the pinned bytes of the two shipped rule
files, default-on install and the per-key switches, install scope, the
duplicate check, the config template and `--migrate`, the manifest row, and
the `init` seam in `init_project.install_rules`.

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
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen
import init_project as ip
import style_rules as sr

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


if __name__ == "__main__":
    unittest.main()
