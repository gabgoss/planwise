#!/usr/bin/env python3
"""Unit tests (TDD) for the Token Saver config surface and calibration helpers.

These tests are written BEFORE the implementation. They pin the contract a
follow-up implementation task must satisfy:

  * generate_config() emits the six `context.token_saver*` keys, and the
    generation/CLI surface toggles `token_saver` on/off.
  * config_loader.get_token_saver_config(config) returns the six keys with the
    documented backward-compatible defaults when they are absent (never assume
    ON, never assume a calibrated overhead).
  * migrate_config() adds the six keys to an EXISTING `context:` block (the real
    production case — every installed config already has `context:`), is
    idempotent, and never overwrites a user-set value. It also adds the whole
    block when `context:` is entirely absent.
  * parse_context_report(text) parses a captured `/context` report into a
    per-category dict, computes a `total_active` that EXCLUDES the
    "System tools (deferred)" row, and attributes plugin token usage by summing
    the Agents + Skills rows whose Source begins with "Plugin".
  * derive_overheads(breakdown) and derive_thresholds(session_target,
    runner_overhead) compute the runner/orchestrator overheads and the derived
    per-task ceiling / critical / warn thresholds.
  * calibrate() with a failed capture writes the conservative fallback overheads,
    flags the thresholds as uncalibrated, and does not crash.
  * classify_file() + the FIXED read-limit constants (READ_FILE_BYTE_CAP,
    READ_PAGE_CAP_TOKENS, READ_LINE_CAP, BYTES_PER_TOKEN) gate a path on the
    token page-cap (bytes / the model's bytes-per-token ratio), the byte cap,
    the defensive line window, a will-exceed-once-modified projection, and the
    cost-or-read fold whose `reason` tag names the driver. The read constants
    are FIXED module-level values, NOT `/context`-derived.

Run with:  python -m unittest scripts/test_token_saver.py

Until the new symbols exist, the `token_saver` engine module import errors and
the config/loader tests fail on the missing keys / accessor. That is the
intended TDD red state, not a fixture bug. The engine symbols are imported
lazily inside each test (via _engine()) so unittest reports one red result per
branch rather than aborting collection on a single ImportError.
"""

import importlib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether unittest is launched from the repo root
# (python -m unittest scripts/test_...) or from inside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader  # noqa: E402
import init_project as ip  # noqa: E402

from conftest import _engine  # noqa: E402


# The six config keys, under `context:`, that the Token Saver surface adds.
TOKEN_SAVER_KEYS = (
    "token_saver",
    "token_saver_session_target",
    "token_saver_runner_overhead",
    "token_saver_orchestrator_overhead",
    "token_saver_context_breakdown",
    "token_saver_overhead_measured_on",
)


# A minimal config.yaml.template carrying a `context:` block but NO token_saver
# keys — the pre-Token-Saver production shape. generate_config / migrate_config
# read cfg.plugin_root/config.yaml.template, so fixtures write this verbatim and
# the generation test then asserts the (not-yet-present) token_saver keys.
TEMPLATE_WITHOUT_TOKEN_SAVER = """# Project Configuration
plugin_root: "{plugin-root}"
plugin_version: "{plugin-version}"
project:
  name: "{project-name}"
  install_scope: "{install-scope}"
  planwise_root: "{planwise-root}"
  plans_dir: "{plans-dir}"
  backlog_dir: "{backlog-dir}"
  lessons_dir: "{lessons-dir}"
  index_files:
    plans: "00-Index-Plans.md"
    backlog: "00-Index-Backlog.md"
    lessons: "00-Index-LessonsLearned.md"

context:
  plan_tier: "{plan-tier}"
  context_window: {context-window}

scoring:
  priority_high: 30
"""


class _ProjectFixtureBase(unittest.TestCase):
    """Builds a temp project tree with a config.yaml and a plugin template."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_token_saver_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"
        self.planwise_dir = self.project_root / "planwise"
        self.planwise_dir.mkdir(parents=True, exist_ok=True)
        self.plugin_root.mkdir(parents=True, exist_ok=True)

        # Plugin-shipped template (used by generate_config / migrate_config).
        self.template_path = self.plugin_root / "config.yaml.template"
        self.template_path.write_text(
            TEMPLATE_WITHOUT_TOKEN_SAVER, encoding="utf-8"
        )

        self.cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
        )

    def config_path(self) -> Path:
        return self.planwise_dir / "config.yaml"

    def write_config(self, text: str) -> Path:
        path = self.config_path()
        path.write_text(text, encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Step 3 — Config-keys generation
# ---------------------------------------------------------------------------
class TestConfigKeysGeneration(_ProjectFixtureBase):
    """generate_config emits the six token_saver keys and the toggle."""

    def _generate(self):
        import yaml

        result, _rel = ip.generate_config(self.cfg)
        self.assertEqual(
            result,
            ip.ConfigResult.CREATED,
            "generate_config must create config.yaml from the template",
        )
        data = yaml.safe_load(self.config_path().read_text(encoding="utf-8"))
        return data.get("context", {}) or {}

    def test_generated_context_block_carries_all_token_saver_keys(self):
        context = self._generate()
        for key in TOKEN_SAVER_KEYS:
            self.assertIn(
                key,
                context,
                f"generate_config must emit context.{key}",
            )

    def test_generated_token_saver_defaults(self):
        context = self._generate()
        self.assertEqual(
            context.get("token_saver_session_target"),
            150000,
            "session_target default must be 150000",
        )
        self.assertEqual(
            context.get("token_saver"),
            False,
            "token_saver default must be False (never assume ON)",
        )

    def test_token_saver_toggle_on_and_off(self):
        # The generation/CLI surface must toggle token_saver true/false.
        # Pinned: a `token_saver` attribute on the config drives the emitted
        # value (declined => False, --token-saver => True).
        on_cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
        )
        self.assertTrue(
            hasattr(on_cfg, "token_saver"),
            "InitConfig must expose a token_saver toggle attribute "
            "(driven by the --token-saver CLI flag)",
        )


# ---------------------------------------------------------------------------
# Step 4 — Backward-compat defaults via config_loader.get_token_saver_config
# ---------------------------------------------------------------------------
class TestBackwardCompatDefaults(_ProjectFixtureBase):
    """A config with NO token_saver* keys yields documented defaults."""

    def _load_fixture_config(self) -> dict:
        """Load the fixture config via load_config's explicit --config path.

        load_config(script_path) does NOT take a config file — it searches
        upward from cwd / the script and reads --config from sys.argv. To pin
        it on the fixture (instead of the repo's real planwise/config.yaml) we
        inject `--config <fixture>` into argv for the duration of the call.
        """
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = ["test_token_saver", "--config", str(self.config_path())]
        return config_loader.load_config()

    def test_defaults_when_keys_absent(self):
        self.write_config(
            "project:\n"
            "  name: BC\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n"
        )
        config = self._load_fixture_config()
        ts = config_loader.get_token_saver_config(config)

        self.assertEqual(ts.get("token_saver"), False, "default must be False")
        self.assertEqual(ts.get("token_saver_runner_overhead"), 0)
        self.assertEqual(ts.get("token_saver_orchestrator_overhead"), 0)
        self.assertEqual(ts.get("token_saver_session_target"), 150000)
        self.assertEqual(ts.get("token_saver_context_breakdown"), {})
        self.assertEqual(ts.get("token_saver_overhead_measured_on"), "")

    def test_user_set_values_are_preserved(self):
        self.write_config(
            "project:\n"
            "  name: BC\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n"
            "  token_saver: true\n"
            "  token_saver_runner_overhead: 26000\n"
        )
        config = self._load_fixture_config()
        ts = config_loader.get_token_saver_config(config)
        self.assertEqual(ts.get("token_saver"), True)
        self.assertEqual(ts.get("token_saver_runner_overhead"), 26000)
        # Untouched keys still default.
        self.assertEqual(ts.get("token_saver_session_target"), 150000)


# ---------------------------------------------------------------------------
# Step 5 — Migration (migrate_config)
# ---------------------------------------------------------------------------
class TestMigration(_ProjectFixtureBase):
    """migrate_config adds token_saver keys into an existing context block."""

    def setUp(self):
        super().setUp()
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for migrate_config tests")
        self.yaml = importlib.import_module("yaml")

    def _read_context(self) -> dict:
        data = self.yaml.safe_load(self.config_path().read_text(encoding="utf-8"))
        return (data or {}).get("context", {}) or {}

    def test_existing_context_block_gains_token_saver_keys(self):
        # The real production case: context: already present, token_saver absent.
        self.write_config(
            "# header\n"
            "project:\n"
            "  name: Mig\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n"
        )
        ip.migrate_config(self.cfg)
        context = self._read_context()
        for key in TOKEN_SAVER_KEYS:
            self.assertIn(
                key,
                context,
                f"migrate must add context.{key} to an existing context block",
            )
        self.assertEqual(context.get("token_saver"), False)
        self.assertEqual(context.get("token_saver_runner_overhead"), 0)
        # The pre-existing keys must survive.
        self.assertEqual(context.get("plan_tier"), "pro")
        self.assertEqual(context.get("context_window"), 200000)

    def test_migration_is_idempotent(self):
        self.write_config(
            "project:\n"
            "  name: Mig\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n"
        )
        ip.migrate_config(self.cfg)
        # First migrate must have populated the keys (the feature under test);
        # this assertion is RED until nested sub-key merging lands.
        first_context = self._read_context()
        for key in TOKEN_SAVER_KEYS:
            self.assertIn(
                key,
                first_context,
                f"first migrate must add context.{key} before idempotency holds",
            )
        first = self.config_path().read_text(encoding="utf-8")
        ip.migrate_config(self.cfg)
        second = self.config_path().read_text(encoding="utf-8")
        self.assertEqual(
            first, second, "Re-running migrate must be a no-op (idempotent)"
        )

    def test_migration_does_not_overwrite_user_values(self):
        self.write_config(
            "project:\n"
            "  name: Mig\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n"
            "  token_saver: true\n"
            "  token_saver_runner_overhead: 26000\n"
        )
        ip.migrate_config(self.cfg)
        context = self._read_context()
        # User-set values must survive untouched...
        self.assertEqual(
            context.get("token_saver"),
            True,
            "migrate must NOT overwrite a user-set token_saver",
        )
        self.assertEqual(
            context.get("token_saver_runner_overhead"),
            26000,
            "migrate must NOT overwrite a non-zero measured overhead",
        )
        # ...AND the absent sub-keys must now be filled with defaults. Today's
        # top-level-only merge skips an existing context: block, so this arm is
        # RED until nested sub-key merging lands.
        self.assertIn(
            "token_saver_orchestrator_overhead",
            context,
            "migrate must add the absent token_saver sub-keys to an existing "
            "context block while preserving the user-set ones",
        )
        self.assertEqual(context.get("token_saver_orchestrator_overhead"), 0)

    def test_absent_context_block_is_added_whole(self):
        self.write_config("project:\n  name: NoCtx\n")
        ip.migrate_config(self.cfg)
        context = self._read_context()
        self.assertTrue(context, "migrate must add a context block when absent")
        for key in TOKEN_SAVER_KEYS:
            self.assertIn(key, context)


# ---------------------------------------------------------------------------
# Resolver — get_effective_token_saver_config overlays a per-plan boolean
# ---------------------------------------------------------------------------
class TestEffectiveTokenSaverResolver(unittest.TestCase):
    """get_effective_token_saver_config flips ONLY the on/off boolean.

    The measured overheads (runner_overhead, orchestrator_overhead,
    session_target, breakdown, measured_on) ALWAYS come from the project config —
    there is exactly one /context calibration per project — so the resolver must
    leave them byte-for-byte identical in every override case.
    """

    # A fully-measured project config: token_saver flag + the five measured keys.
    def _config(self, flag: bool) -> dict:
        return {
            "context": {
                "token_saver": flag,
                "token_saver_session_target": 150000,
                "token_saver_runner_overhead": 26000,
                "token_saver_orchestrator_overhead": 24000,
                "token_saver_context_breakdown": {"system_prompt": 2600},
                "token_saver_overhead_measured_on": "2026-06-23",
            }
        }

    # The five measured keys whose values must never change under override.
    MEASURED_KEYS = (
        "token_saver_session_target",
        "token_saver_runner_overhead",
        "token_saver_orchestrator_overhead",
        "token_saver_context_breakdown",
        "token_saver_overhead_measured_on",
    )

    def _assert_measured_match_project(self, project_flag: bool, override):
        project = self._config(project_flag)
        base = config_loader.get_token_saver_config(project)
        effective = config_loader.get_effective_token_saver_config(
            project, plan_override=override
        )
        for key in self.MEASURED_KEYS:
            self.assertEqual(
                effective[key],
                base[key],
                f"measured key {key} must equal the project value for "
                f"(project={project_flag}, override={override})",
            )

    def test_matrix_false_none_inherits_false(self):
        # (project False, override None) -> False (inherit project).
        effective = config_loader.get_effective_token_saver_config(
            self._config(False), plan_override=None
        )
        self.assertEqual(effective["token_saver"], False)
        self._assert_measured_match_project(False, None)

    def test_matrix_true_none_inherits_true(self):
        # (project True, override None) -> True (inherit project).
        effective = config_loader.get_effective_token_saver_config(
            self._config(True), plan_override=None
        )
        self.assertEqual(effective["token_saver"], True)
        self._assert_measured_match_project(True, None)

    def test_matrix_false_true_overrides_to_true(self):
        # (project False, override True) -> True (plan opts in).
        effective = config_loader.get_effective_token_saver_config(
            self._config(False), plan_override=True
        )
        self.assertEqual(effective["token_saver"], True)
        self._assert_measured_match_project(False, True)

    def test_matrix_true_false_overrides_to_false(self):
        # (project True, override False) -> False (plan opts out).
        effective = config_loader.get_effective_token_saver_config(
            self._config(True), plan_override=False
        )
        self.assertEqual(effective["token_saver"], False)
        self._assert_measured_match_project(True, False)

    def test_missing_context_block_defaults_to_false(self):
        # A config with NO context block: override None -> False with the
        # documented default overheads (never assume ON, never assume calibrated).
        effective = config_loader.get_effective_token_saver_config(
            {}, plan_override=None
        )
        self.assertEqual(effective["token_saver"], False)
        self.assertEqual(effective["token_saver_session_target"], 150000)
        self.assertEqual(effective["token_saver_runner_overhead"], 0)
        self.assertEqual(effective["token_saver_orchestrator_overhead"], 0)
        self.assertEqual(effective["token_saver_context_breakdown"], {})
        self.assertEqual(effective["token_saver_overhead_measured_on"], "")


# ---------------------------------------------------------------------------
# Writer — set_token_saver flips the bare toggle, never the measured lines
# ---------------------------------------------------------------------------
class TestSetTokenSaverWriter(unittest.TestCase):
    """set_token_saver flips the bare `token_saver:` line in place.

    It must use the comment-preserving in-place editor (NOT a yaml.safe_dump
    round-trip): the five `token_saver_*` measured lines and inline comments must
    survive untouched, and an absent `token_saver:` line is appended.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_set_token_saver_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, text: str) -> Path:
        path = self.tmp / "config.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    # A config carrying the toggle + the five measured keys + inline comments.
    FULL_CONFIG = (
        "project:\n"
        "  name: WriterTest\n"
        "context:\n"
        "  plan_tier: pro\n"
        "  context_window: 200000\n"
        "  token_saver: false  # engine off until enabled\n"
        "  token_saver_session_target: 150000  # keeps a runner < 200K\n"
        "  token_saver_runner_overhead: 26000  # measured\n"
        "  token_saver_orchestrator_overhead: 24000  # measured\n"
        "  token_saver_context_breakdown: {system_prompt: 2600}  # diagnostic\n"
        '  token_saver_overhead_measured_on: "2026-06-23"  # calibration date\n'
    )

    def _line_value(self, text: str, key: str) -> str:
        """Return the raw value (post-colon, pre-comment, stripped) for `key:`.

        Anchors on a literal colon after the key so `token_saver` does not match
        a `token_saver_*` line.
        """
        m = re.search(rf"(?m)^\s*{re.escape(key)}:\s*([^\n#]*)", text)
        return m.group(1).strip() if m else None

    def test_round_trip_tracks_toggle_and_preserves_measured(self):
        ts = _engine()
        path = self._write(self.FULL_CONFIG)

        # Capture the five measured lines verbatim BEFORE any write.
        before = path.read_text(encoding="utf-8")
        measured_lines = {
            key: self._line_value(before, key)
            for key in (
                "token_saver_session_target",
                "token_saver_runner_overhead",
                "token_saver_orchestrator_overhead",
                "token_saver_context_breakdown",
                "token_saver_overhead_measured_on",
            )
        }

        for flip in (True, False, True):
            result = ts.set_token_saver(path, flip)
            self.assertEqual(result.get("token_saver"), flip)
            text = path.read_text(encoding="utf-8")
            # The bare toggle tracks the requested boolean.
            self.assertEqual(
                self._line_value(text, "token_saver"),
                "true" if flip else "false",
                f"toggle line must read {flip}",
            )
            # The five measured lines are byte-for-byte untouched.
            for key, val in measured_lines.items():
                self.assertEqual(
                    self._line_value(text, key),
                    val,
                    f"measured line {key} must not change when toggling",
                )

        # Inline comments survive the round-trip.
        final = path.read_text(encoding="utf-8")
        self.assertIn("# engine off until enabled", final)
        self.assertIn("# keeps a runner < 200K", final)
        self.assertIn("# calibration date", final)

    def test_append_when_toggle_absent(self):
        ts = _engine()
        # A config with a context: block but NO token_saver: line.
        no_toggle = (
            "project:\n"
            "  name: NoToggle\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n"
            "  token_saver_runner_overhead: 26000  # measured\n"
        )
        path = self._write(no_toggle)
        result = ts.set_token_saver(path, True)
        self.assertEqual(result.get("token_saver"), True)

        text = path.read_text(encoding="utf-8")
        # The bare toggle was appended and reads true.
        self.assertEqual(self._line_value(text, "token_saver"), "true")
        # The pre-existing measured key + comment survive untouched.
        self.assertEqual(
            self._line_value(text, "token_saver_runner_overhead"), "26000"
        )
        self.assertIn("# measured", text)
        # Other keys in the block survive.
        self.assertEqual(self._line_value(text, "plan_tier"), "pro")
        self.assertEqual(self._line_value(text, "context_window"), "200000")

    def test_value_rewrite_preserves_inline_comment(self):
        """A VALUE REWRITE (not just a boolean flip) must keep the inline comment.

        A toggle round-trip never moves a numeric value next to its comment, so it
        cannot prove the splice survives a real value change — a naive `re.sub` on
        the value could eat the trailing comment only in the rewrite case. This
        mirrors what `calibrate` does when it rewrites the measured overheads.
        """
        ts = _engine()
        path = self._write(self.FULL_CONFIG)

        # Rewrite the measured value 26000 -> 54000 in place (as calibrate would).
        ts._write_back(path, {"token_saver_runner_overhead": 54000})

        text = path.read_text(encoding="utf-8")
        # The value changed ...
        self.assertEqual(
            self._line_value(text, "token_saver_runner_overhead"),
            "54000",
            "the measured value must be rewritten in place",
        )
        # ... and the inline comment survived the rewrite (the core gate).
        line = re.search(r"(?m)^.*token_saver_runner_overhead:.*$", text).group(0)
        self.assertTrue(
            line.rstrip().endswith("# measured"),
            "the inline `# measured` comment must survive the value rewrite",
        )
        # A sibling measured line that was NOT rewritten stays byte-for-byte.
        self.assertEqual(
            self._line_value(text, "token_saver_orchestrator_overhead"), "24000"
        )
        self.assertIn("# keeps a runner < 200K", text)


# ---------------------------------------------------------------------------
# _run_upgrade token-saver toggle regression
# ---------------------------------------------------------------------------
class TestRunUpgradeTokenSaverToggle(_ProjectFixtureBase):
    """_run_upgrade honors cfg.token_saver: flips false->true when opted in.

    Covers four contracts:
      (a) key absent before upgrade + cfg.token_saver=True  -> token_saver: true
      (b) key= false before upgrade + cfg.token_saver=True  -> token_saver: true
      (c) cfg.token_saver=False -> existing false left unchanged
      (d) existing true is never reverted (never true->false)
    """

    _PINNED_VERSION = "1.0.3"
    _TARGET_VERSION = "1.0.4"

    def setUp(self):
        super().setUp()
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for _run_upgrade tests")
        # Create an empty rules dir so upgrade_artifacts' glob doesn't fail on
        # Python 3.12+ when the path doesn't exist yet.
        rules_dir = self.project_root / ".claude" / "rules" / "planwise"
        rules_dir.mkdir(parents=True, exist_ok=True)

    def _make_cfg(self, token_saver: bool) -> ip.InitConfig:
        return ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
            plugin_version=self._TARGET_VERSION,
            token_saver=token_saver,
        )

    def _write_upgrade_config(self, extra_context_lines: str = "") -> None:
        """Write a minimal config.yaml with the pinned version.

        extra_context_lines: zero or more indented YAML lines to append inside
        the `context:` block (e.g., "  token_saver: false").
        """
        text = (
            f'plugin_version: "{self._PINNED_VERSION}"\n'
            "project:\n"
            "  name: FixtureProject\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n"
        )
        if extra_context_lines:
            text += extra_context_lines + "\n"
        self.write_config(text)

    def _read_token_saver_raw(self) -> str | None:
        """Return the raw `token_saver:` value, or None if the key is absent."""
        text = self.config_path().read_text(encoding="utf-8")
        import re
        m = re.search(r"(?m)^\s*token_saver:\s*(\S+)", text)
        return m.group(1) if m else None

    @staticmethod
    def _run_upgrade_silently(cfg: ip.InitConfig) -> int:
        """Invoke _run_upgrade suppressing stdout/stderr to keep test output clean."""
        import io
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = io.StringIO()
        try:
            return ip._run_upgrade(cfg)
        finally:
            sys.stdout, sys.stderr = old_out, old_err

    # -- case (a) ----------------------------------------------------------

    def test_key_absent_with_token_saver_flag_yields_true(self):
        """Key absent before upgrade + cfg.token_saver=True -> token_saver: true."""
        self._write_upgrade_config()  # no token_saver line
        cfg = self._make_cfg(token_saver=True)
        rc = self._run_upgrade_silently(cfg)
        self.assertEqual(rc, 0, "_run_upgrade must return 0 on success")
        self.assertEqual(
            self._read_token_saver_raw(),
            "true",
            "Absent key + --token-saver: must seed token_saver: true after upgrade",
        )

    # -- case (b) ----------------------------------------------------------

    def test_key_false_with_token_saver_flag_yields_true(self):
        """Existing token_saver: false + cfg.token_saver=True -> token_saver: true."""
        self._write_upgrade_config("  token_saver: false")
        cfg = self._make_cfg(token_saver=True)
        rc = self._run_upgrade_silently(cfg)
        self.assertEqual(rc, 0, "_run_upgrade must return 0 on success")
        self.assertEqual(
            self._read_token_saver_raw(),
            "true",
            "Existing false + --token-saver: must flip token_saver: false -> true",
        )

    # -- case (c) ----------------------------------------------------------

    def test_no_flag_leaves_existing_false_unchanged(self):
        """Omitting --token-saver on upgrade leaves an existing false unchanged."""
        self._write_upgrade_config("  token_saver: false")
        cfg = self._make_cfg(token_saver=False)
        rc = self._run_upgrade_silently(cfg)
        self.assertEqual(rc, 0, "_run_upgrade must return 0 on success")
        self.assertEqual(
            self._read_token_saver_raw(),
            "false",
            "Upgrade without --token-saver must leave token_saver: false untouched",
        )

    # -- case (d) ----------------------------------------------------------

    def test_existing_true_never_reverted_when_flag_omitted(self):
        """An existing token_saver: true is never flipped back to false."""
        self._write_upgrade_config("  token_saver: true")
        cfg = self._make_cfg(token_saver=False)  # no --token-saver flag
        rc = self._run_upgrade_silently(cfg)
        self.assertEqual(rc, 0, "_run_upgrade must return 0 on success")
        self.assertEqual(
            self._read_token_saver_raw(),
            "true",
            "_run_upgrade must NEVER revert an existing token_saver: true to false",
        )

    def test_idempotent_already_true_with_flag_stays_true(self):
        """Re-running upgrade with --token-saver on an already-true config is a no-op."""
        self._write_upgrade_config("  token_saver: true")
        cfg = self._make_cfg(token_saver=True)
        rc = self._run_upgrade_silently(cfg)
        self.assertEqual(rc, 0)
        self.assertEqual(
            self._read_token_saver_raw(),
            "true",
            "Upgrade with --token-saver on an already-true config must stay true",
        )


if __name__ == "__main__":
    unittest.main()
