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
    READ_PAGE_CAP_TOKENS, TOKENS_PER_LINE) gate a path on a byte cap, a per-model
    token page-cap, a will-exceed-once-modified projection, and the cost-or-read
    fold whose `reason` tag names the driver. The read constants are FIXED
    module-level values, NOT `/context`-derived.

Run with:  python -m unittest scripts/test_token_saver.py

Until the new symbols exist, the `token_saver` engine module import errors and
the config/loader tests fail on the missing keys / accessor. That is the
intended TDD red state, not a fixture bug. The engine symbols are imported
lazily inside each test (via _engine()) so unittest reports one red result per
branch rather than aborting collection on a single ImportError.
"""

import importlib
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether unittest is launched from the repo root
# (python -m unittest scripts/test_...) or from inside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_loader  # noqa: E402
import init_project as ip  # noqa: E402


# The six config keys, under `context:`, that the Token Saver surface adds.
TOKEN_SAVER_KEYS = (
    "token_saver",
    "token_saver_session_target",
    "token_saver_runner_overhead",
    "token_saver_orchestrator_overhead",
    "token_saver_context_breakdown",
    "token_saver_overhead_measured_on",
)

# A real captured `/context` report, pasted verbatim. Parser rules:
#   * "System tools (deferred)" is EXCLUDED from total_active.
#   * 25.7k -> 25700, 386 -> 386, ~80 -> 80, "< 20" -> 20.
#   * Plugin attribution sums Agents + Skills rows whose Source starts "Plugin".
CONTEXT_REPORT_FIXTURE = """## Context Usage
**Model:** claude-opus-4-8[1m]
**Tokens:** 25.7k / 1m (3%)
### Estimated usage by category
| Category | Tokens | Percentage |
| System prompt | 2.6k | 0.3% |
| System tools | 19.1k | 1.9% |
| System tools (deferred) | 16.4k | 1.6% |
| Custom agents | 386 | 0.0% |
| Memory files | 2k | 0.2% |
| Skills | 1.7k | 0.2% |
| Messages | 8 | 0.0% |
| Free space | 974.3k | 97.4% |
### Custom Agents
| Agent Type | Source | Tokens |
| planwise:fix-agent | Plugin | 86 |
| planwise:plan-reviewer | Plugin | 117 |
| planwise:structural-reviewer | Plugin | 99 |
| planwise:task-runner | Plugin | 84 |
### Skills
| Skill | Source | Tokens |
| planwise | Plugin (planwise) | ~80 |
| deep-research | Built-in | ~160 |
"""


def _engine():
    """Import (or re-import) the not-yet-implemented token_saver engine module.

    Imported lazily so a missing module surfaces as a per-test error (TDD red)
    rather than aborting collection of the whole file at import time.
    """
    if "token_saver" in sys.modules:
        return importlib.reload(sys.modules["token_saver"])
    return importlib.import_module("token_saver")


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
# Step 6 — /context parser
# ---------------------------------------------------------------------------
class TestContextParser(unittest.TestCase):
    """parse_context_report parses the captured report and attributes plugins."""

    def test_total_active_excludes_deferred_tools(self):
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        total = report["total_active"]
        # ~25.7K, the header total, which excludes "System tools (deferred)".
        self.assertGreaterEqual(total, 25000)
        self.assertLessEqual(total, 26500)
        # The deferred row (16.4k) must NOT be folded into total_active.
        self.assertLess(
            total,
            25700 + 16400 - 1000,
            "total_active must exclude the System tools (deferred) row",
        )

    def test_per_category_dict_populated(self):
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        categories = report["categories"]
        self.assertEqual(categories.get("System prompt"), 2600)
        self.assertEqual(categories.get("System tools"), 19100)
        self.assertEqual(categories.get("Memory files"), 2000)
        self.assertEqual(categories.get("Messages"), 8)

    def test_plugin_attribution_sums_plugin_rows(self):
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        attributed = ts.attribution(report, plugin="planwise")
        # Agents: 86 + 117 + 99 + 84 = 386; Skills: planwise (~80) Plugin row.
        # deep-research (Built-in) is excluded. Total ~= 466.
        self.assertGreaterEqual(attributed, 450)
        self.assertLessEqual(attributed, 480)


# ---------------------------------------------------------------------------
# Step 7 — Derivation formulas
# ---------------------------------------------------------------------------
class TestDerivation(unittest.TestCase):
    """derive_overheads + derive_thresholds compute the budget math."""

    def test_derive_overheads_from_breakdown(self):
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        overheads = ts.derive_overheads(report)
        runner = overheads["runner_overhead"]
        orchestrator = overheads["orchestrator_overhead"]
        # runner_overhead = active footprint (conservative proxy).
        self.assertGreaterEqual(runner, 25000)
        self.assertLessEqual(runner, 26500)
        # orchestrator_overhead = active footprint minus Messages (8).
        self.assertLess(
            orchestrator,
            runner,
            "orchestrator_overhead must be active footprint minus Messages",
        )
        self.assertEqual(runner - orchestrator, 8)

    def test_derive_thresholds_low_overhead(self):
        ts = _engine()
        thresholds = ts.derive_thresholds(150000, 26000)
        # available = 150000 - 26000 - 6000 = 118000
        self.assertEqual(thresholds["available_per_task"], 118000)
        # critical = available - 10000 = 108000
        self.assertEqual(thresholds["critical"], 108000)
        # warn = min(40000, round(0.5*available)) = 40000
        self.assertEqual(thresholds["warn"], 40000)

    def test_derive_thresholds_high_overhead(self):
        ts = _engine()
        thresholds = ts.derive_thresholds(150000, 70000)
        # available = 150000 - 70000 - 6000 = 74000
        self.assertEqual(thresholds["available_per_task"], 74000)
        # critical = available - 10000 = 64000
        self.assertEqual(thresholds["critical"], 64000)
        # warn = min(40000, round(0.5*74000)) = min(40000, 37000) = 37000
        self.assertEqual(thresholds["warn"], 37000)


# ---------------------------------------------------------------------------
# Step 8 — Capture-failure fallback
# ---------------------------------------------------------------------------
class TestCaptureFailureFallback(unittest.TestCase):
    """calibrate() with a failed capture writes conservative fallbacks."""

    def test_capture_none_writes_conservative_fallback(self):
        ts = _engine()

        # Stub capture: simulate a missing CLI by returning None.
        def _stub_capture(*_args, **_kwargs):
            return None

        result = ts.calibrate(capture=_stub_capture)
        self.assertEqual(
            result.get("token_saver_runner_overhead"),
            54000,
            "Failed capture must fall back to runner_overhead=54000",
        )
        self.assertEqual(
            result.get("token_saver_orchestrator_overhead"),
            60000,
            "Failed capture must fall back to orchestrator_overhead=60000",
        )
        # A flag/marker that the thresholds are uncalibrated.
        self.assertFalse(
            result.get("calibrated", True),
            "A failed capture must mark the result uncalibrated",
        )


# ---------------------------------------------------------------------------
# Step 9 — Read-limit constants + classify_file
# ---------------------------------------------------------------------------
class TestReadLimits(unittest.TestCase):
    """FIXED read-limit constants and classify_file gating."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_read_limits_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write_lines(self, name: str, n_lines: int, line: str = "x" * 60) -> str:
        path = self.tmp / name
        path.write_text("\n".join(line for _ in range(n_lines)) + "\n", encoding="utf-8")
        return str(path)

    def _write_bytes(self, name: str, n_bytes: int) -> str:
        path = self.tmp / name
        path.write_bytes(b"a" * n_bytes)
        return str(path)

    def test_read_constants_are_fixed_values(self):
        ts = _engine()
        # FIXED module-level values — NOT /context- or config-derived.
        self.assertEqual(ts.READ_FILE_BYTE_CAP, 262144)
        self.assertEqual(ts.READ_BYTE_WARN, 245760)
        self.assertEqual(ts.READ_PAGE_CAP_TOKENS, 25000)
        self.assertEqual(ts.READ_TOKEN_WARN, 22000)
        self.assertEqual(
            ts.TOKENS_PER_LINE,
            {"haiku": 13, "sonnet": 13, "opus": 19},
        )

    def test_byte_gate_critical_for_every_model(self):
        ts = _engine()
        # ~300 KB straddles the 262144-byte cap.
        path = self._write_bytes("big.bin", 300 * 1024)
        for model in ("haiku", "sonnet", "opus"):
            result = ts.classify_file(path, model)
            self.assertEqual(
                result["level"], "Critical", f"byte gate must trip on {model}"
            )
            self.assertEqual(
                result["reason"], "read", f"byte gate reason must be read on {model}"
            )

    def test_per_model_token_gate(self):
        ts = _engine()
        # ~1600 lines: sonnet 13 tok/line ~= 20.8K (below 25K),
        # opus 19 tok/line ~= 30.4K (above 25K).
        path = self._write_lines("mid.txt", 1600)
        sonnet = ts.classify_file(path, "sonnet")
        opus = ts.classify_file(path, "opus")
        self.assertNotEqual(
            sonnet["level"],
            "Critical",
            "sonnet must stay below the token page-cap for a 1600-line file",
        )
        self.assertEqual(
            opus["level"],
            "Critical",
            "opus (19 tok/line) must trip the token page-cap on a 1600-line file",
        )
        self.assertEqual(opus["reason"], "read")

    def test_will_exceed_once_modified_projection(self):
        ts = _engine()
        # Currently-safe file for opus (~800 lines ~= 15.2K), but a projected
        # addition pushes it past the 25K opus token gate pre-emptively.
        path = self._write_lines("growing.txt", 800)
        safe = ts.classify_file(path, "opus")
        self.assertNotEqual(
            safe["level"], "Critical", "800-line file must be safe for opus today"
        )
        projected = ts.classify_file(path, "opus", projected_added_lines=700)
        self.assertEqual(
            projected["level"],
            "Critical",
            "projected_added_lines must pre-emptively trip the read gate",
        )
        self.assertEqual(projected["reason"], "read")

    def test_cost_read_fold_takes_max(self):
        ts = _engine()
        # A small file (read says Green/Notice) but a cost thresholds dict that
        # says Warn, and a read that says Critical => fold takes max => Critical,
        # reason=read. To force read=Critical we use a large file; cost=Warn via
        # a thresholds dict that classifies the same byte size only as Warn.
        path = self._write_lines("folded.txt", 1600)  # opus: read=Critical
        # cost thresholds chosen so the cost arm classifies this as Warn only.
        cost_thresholds = {"warn": 1000, "critical": 10_000_000}
        result = ts.classify_file(
            path, "opus", thresholds=cost_thresholds
        )
        self.assertEqual(
            result["level"],
            "Critical",
            "fold must take max(cost_level, read_level)",
        )
        self.assertEqual(
            result["reason"],
            "read",
            "fold reason must name the driver (read here)",
        )

    def test_classify_file_reports_bytes_and_tokens(self):
        ts = _engine()
        path = self._write_lines("small.txt", 100)
        result = ts.classify_file(path, "sonnet")
        # The result must carry the real byte size and a token estimate.
        self.assertEqual(result["bytes"], os.path.getsize(path))
        self.assertGreater(result["tokens"], 0)


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


# ---------------------------------------------------------------------------
# Windows shim resolution + parse guard for headless non-report reply
# ---------------------------------------------------------------------------
class TestCaptureContextWindowsInvocation(unittest.TestCase):
    """capture_context() routes through powershell.exe on Windows.

    `/context` only renders when a real console is attached; launched directly
    from pipe stdio (Git Bash / MSYS / a console-less parent) it falls through as
    a prompt and returns conversational text.  powershell.exe attaches a console,
    so the report renders — it also resolves the `claude` shim itself, so no
    shutil.which / shell=True is needed on Windows.
    """

    def test_windows_routes_through_powershell(self):
        import token_saver
        from unittest.mock import MagicMock, patch

        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = CONTEXT_REPORT_FIXTURE

        with patch.object(token_saver.os, "name", "nt"), \
             patch.object(token_saver.subprocess, "run", return_value=fake_proc) as mock_run:
            result = token_saver.capture_context(r"C:\plugins\planwise", "/some/cwd")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        self.assertEqual(cmd[0], "powershell.exe",
                         "capture_context must launch via powershell.exe on Windows")
        self.assertIn("-NoProfile", cmd)
        self.assertIn("-Command", cmd)
        inner = cmd[-1]
        self.assertIn("/context", inner,
                      "the powershell -Command must invoke claude -p /context")
        self.assertIn(r"C:\plugins\planwise", inner,
                      "the powershell -Command must pass the plugin dir")
        self.assertFalse(call_args[1].get("shell"),
                         "powershell.exe is launched directly; shell must be False")
        self.assertIsNotNone(result)

    def test_posix_uses_shell_false(self):
        import token_saver
        from unittest.mock import MagicMock, patch

        fake_bin = "/usr/local/bin/claude"
        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = CONTEXT_REPORT_FIXTURE

        with patch.object(token_saver.os, "name", "posix"), \
             patch.object(token_saver.shutil, "which", return_value=fake_bin), \
             patch.object(token_saver.subprocess, "run", return_value=fake_proc) as mock_run:
            result = token_saver.capture_context("/some/plugin", "/some/cwd")

        call_args = mock_run.call_args
        self.assertFalse(call_args[1].get("shell"),
                         "capture_context must pass shell=False on POSIX")
        self.assertIsNotNone(result)


class TestCalibrateParseGuard(unittest.TestCase):
    """calibrate() treats a non-report (conversational) reply as a failed capture.

    headless `claude -p "/context"` may return plain prose instead of the
    structured `/context` report.  Such a reply has no `**Tokens:**` header and
    no category table.  calibrate() must fall back to the conservative overheads
    (runner=54000 / orchestrator=60000, calibrated=False) — NOT write
    runner_overhead=0 flagged calibrated:True.
    """

    CONVERSATIONAL_REPLY = (
        "Sure! The /context command shows your current context usage. "
        "It displays how many tokens are in use across different categories "
        "such as system prompt, tools, memory files, and messages."
    )

    def test_conversational_reply_falls_back_to_conservative(self):
        ts = _engine()

        def _stub_conversational(*_args, **_kwargs):
            return self.CONVERSATIONAL_REPLY

        result = ts.calibrate(capture=_stub_conversational)
        self.assertEqual(
            result.get("token_saver_runner_overhead"),
            54000,
            "A conversational reply (no Tokens: header, no categories) must fall "
            "back to runner_overhead=54000",
        )
        self.assertEqual(
            result.get("token_saver_orchestrator_overhead"),
            60000,
            "A conversational reply must fall back to orchestrator_overhead=60000",
        )
        self.assertFalse(
            result.get("calibrated", True),
            "A conversational reply must mark the result uncalibrated",
        )

    # A partial/garbled report: a `### category` table with ONLY the excluded
    # rows (deferred tools + free space) and NO `**Tokens:**` header.  It parses
    # to non-empty categories but total_active=0, so a guard keyed only on
    # "no header AND no categories" would let it through and write
    # runner_overhead=0 (== total_active) flagged calibrated:True — exactly the
    # edge the acceptance criterion says to prevent.
    DEGENERATE_REPORT = (
        "## Context Usage\n"
        "### Estimated usage by category\n"
        "| Category | Tokens | Percentage |\n"
        "| System tools (deferred) | 16.4k | 1.6% |\n"
        "| Free space | 974.3k | 97.4% |\n"
    )

    def test_zero_active_total_falls_back_not_calibrated(self):
        ts = _engine()

        # Sanity: the fixture parses to non-empty categories but total_active 0.
        report = ts.parse_context_report(self.DEGENERATE_REPORT)
        self.assertTrue(report["categories"], "fixture must have category rows")
        self.assertEqual(
            report["total_active"],
            0,
            "fixture must yield total_active=0 (only deferred/free-space rows)",
        )

        def _stub_degenerate(*_args, **_kwargs):
            return self.DEGENERATE_REPORT

        result = ts.calibrate(capture=_stub_degenerate)
        self.assertEqual(
            result.get("token_saver_runner_overhead"),
            54000,
            "A report yielding total_active=0 must fall back — never write "
            "runner_overhead=0 flagged calibrated:True",
        )
        self.assertFalse(
            result.get("calibrated", True),
            "A zero-active-total report must be marked uncalibrated",
        )


if __name__ == "__main__":
    unittest.main()
