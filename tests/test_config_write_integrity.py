#!/usr/bin/env python3
"""Unit tests for config.yaml write integrity across every config writer.

Two coupled defects used to corrupt a consumer's config.yaml on the upgrade
path. `migrate_config()`'s added-keys branch re-emitted the WHOLE file through
`yaml.safe_dump`, which reflowed every inline flow value into a block mapping
and destroyed every interior comment. `token_saver._write_back()` then spliced
its new single-line value over only the PARENT line of the reflowed
`token_saver_context_breakdown:` block, leaving the old children orphaned
beneath a complete value — an unparseable file that nothing noticed until the
next command died on a raw parser traceback.

These tests pin the contract that closes both:

  * migrate_config() splices an added top-level key onto the user's ORIGINAL
    text; everything outside the appended block survives byte-for-byte
    (interior comments, an inline flow-mapping breakdown, inline trigger lists),
    and the added key is present and parseable.
  * _write_back() replaces a BLOCK-STYLE value's parent line AND its whole child
    block, leaving no orphans, and still preserves a trailing inline comment on
    the ordinary single-line case.
  * set_token_saver() rides the same editor and is covered on both shapes.
  * A write whose result would not parse is rolled back: the on-disk file is
    byte-for-byte unchanged and the call raises.
  * End-to-end: a migrate that ADDS a key followed by a calibrate-style
    write-back leaves a parseable config carrying the new key, the new measured
    values, and the user's original comments.
  * `/planwise doctor` reports an unparseable config and names the orphaned-block
    cause when that signature is present.

Fixture field values follow a real on-disk config's shape (flow-style
breakdown, quoted measured-on date, inline trigger lists); each test builds an
isolated temp tree and none read or mutate the live project's config.

Run with:  python -m pytest tests/test_config_write_integrity.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader  # noqa: E402
import init_project as ip  # noqa: E402
import token_saver as ts  # noqa: E402

try:
    import yaml  # noqa: E402

    HAS_YAML = True
except ImportError:  # pragma: no cover - the suite needs PyYAML
    HAS_YAML = False


# A template carrying every migratable top-level key, with the hand-authored
# comment blocks the real shipped template has above `context:` and `upgrade:`.
TEMPLATE = """# Agentic Project Management — Project Configuration
plugin_root: "{plugin-root}"
plugin_version: "{plugin-version}"
project:
  name: "{project-name}"
  install_scope: "{install-scope}"
  planwise_root: "{planwise-root}"
  plans_dir: "{plans-dir}"
  backlog_dir: "{backlog-dir}"
  lessons_dir: "{lessons-dir}"

# Context window tier — used by all handlers to scale token budgets.
# plan_tier: "pro" (200K) or "max" (1M). Subagents inherit this tier.
context:
  plan_tier: "{plan-tier}"
  context_window: {context-window}
  token_saver: {token-saver}
  token_saver_session_target: 150000
  token_saver_runner_overhead: 0      # measured subagent footprint (calibrated)
  token_saver_orchestrator_overhead: 0  # measured orchestrator footprint (calibrated)
  token_saver_context_breakdown: {}   # measured per-category /context breakdown
  token_saver_overhead_measured_on: ""  # ISO date of the last calibration

categorization:
  buckets:
    - id: A
      slug: database
      name: "Database / SQL"
  decision_tree_order: [A]
  default_bucket: A

# customization_handoff: how upgrade disposes a customization-bearing rule.
upgrade:
  customization_handoff: report+relocate
  github_issue: false                  # opt-in gh issue (interactive only)
  descope_preserve_paths_edits: true

scoring:
  priority_high: 30
"""

# An annotated user config in the real on-disk shape: interior comments, an
# inline flow-mapping breakdown, and inline trigger lists. Every migratable
# top-level key is present EXCEPT `upgrade:`, so a migrate adds exactly one.
ANNOTATED_CONFIG = """# Agentic Project Management — Project Configuration
plugin_root: "/plugins/planwise"
plugin_version: "1.0.3"

project:
  name: AnnotatedProject          # keep this name, tooling greps for it
  install_scope: project
  planwise_root: planwise
  plans_dir: Plans
  backlog_dir: Backlog
  lessons_dir: LessonsLearned

# Measured on a real session — do NOT hand-edit, re-run calibrate instead.
context:
  plan_tier: max
  context_window: 1000000
  token_saver: true
  token_saver_session_target: 150000
  token_saver_runner_overhead: 29500      # measured subagent footprint
  token_saver_orchestrator_overhead: 29492
  token_saver_context_breakdown: {system_prompt: 3900, system_tools: 18100, custom_agents: 959, memory_files: 4300, skills: 2200, messages: 8, free_space: 970500}
  token_saver_overhead_measured_on: "2026-07-08"
  token_saver_injection_ceiling: 40000
  token_saver_session_start_range: {min: 24800, median: 29500, max: 36200}
  token_saver_injected_rules_estimate: 4300
  token_saver_orchestrator_advisory: measured
  token_saver_session_checkpoint: {window: 400000, turns: 194}

# Routing buckets for lessons curate. Order matters.
categorization:
  buckets:
    - id: A
      slug: database
      name: "Database / SQL"
      triggers:
        technology: [sql, mssql, postgres, sqlite, pyodbc]
        domain: [DB, SCHEMA]
    - id: B
      slug: code
      name: "Application Code"
      triggers:
        technology: [python, javascript, typescript]
  decision_tree_order: [A, B]
  default_bucket: B  # Catch-all when no bucket's triggers match.

scoring:
  priority_high: 30
"""


class _ConfigFixtureBase(unittest.TestCase):
    """Builds an isolated temp project tree with a config.yaml and a template."""

    def setUp(self):
        if not HAS_YAML:
            self.skipTest("PyYAML required for config write-integrity tests")
        self.tmp = Path(tempfile.mkdtemp(prefix="pw_config_write_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"
        self.planwise_dir = self.project_root / "planwise"
        self.planwise_dir.mkdir(parents=True, exist_ok=True)
        self.plugin_root.mkdir(parents=True, exist_ok=True)
        (self.plugin_root / "config.yaml.template").write_text(TEMPLATE, encoding="utf-8")

        self.cfg = ip.InitConfig(
            project_name="AnnotatedProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
            plan_tier="max",
        )

    def config_path(self) -> Path:
        return self.planwise_dir / "config.yaml"

    def write_config(self, text: str) -> Path:
        path = self.config_path()
        path.write_text(text, encoding="utf-8")
        return path

    def read_config(self) -> str:
        return self.config_path().read_text(encoding="utf-8")

    def load_config(self) -> dict:
        return yaml.safe_load(self.read_config()) or {}


# ---------------------------------------------------------------------------
# migrate_config() — the added-keys branch never round-trips the user's data
# ---------------------------------------------------------------------------
class TestMigrateAddedKeyPreservesUserText(_ConfigFixtureBase):

    def test_added_key_leaves_everything_else_byte_for_byte(self):
        self.write_config(ANNOTATED_CONFIG)
        _path, added, present = ip.migrate_config(self.cfg)

        self.assertIn("upgrade", added, "the absent top-level key must be added")
        for key in ("plugin_root", "plugin_version", "context", "categorization"):
            self.assertIn(key, present, f"{key} was present and must be reported so")

        result = self.read_config()
        self.assertTrue(
            result.startswith(ANNOTATED_CONFIG),
            "the user's original text must survive byte-for-byte; the added key "
            "is appended, never re-emitted around",
        )

    def test_added_key_preserves_flow_styles_and_interior_comments(self):
        self.write_config(ANNOTATED_CONFIG)
        ip.migrate_config(self.cfg)
        result = self.read_config()

        # The inline flow-mapping breakdown stays on ONE line — the downstream
        # targeted line editor depends on it.
        self.assertIn(
            "token_saver_context_breakdown: {system_prompt: 3900, system_tools: 18100,",
            result,
            "the inline flow-mapping breakdown must not be reflowed to a block",
        )
        # Inline trigger lists stay inline.
        self.assertIn("technology: [sql, mssql, postgres, sqlite, pyodbc]", result)
        self.assertIn("domain: [DB, SCHEMA]", result)
        # Interior comments — header, standalone, and inline — all survive.
        self.assertIn("# Measured on a real session", result)
        self.assertIn("# Routing buckets for lessons curate", result)
        self.assertIn("# keep this name, tooling greps for it", result)
        self.assertIn("# measured subagent footprint", result)
        self.assertIn("# Catch-all when no bucket's triggers match.", result)

    def test_added_key_lands_with_its_template_comment_and_values(self):
        self.write_config(ANNOTATED_CONFIG)
        ip.migrate_config(self.cfg)

        data = self.load_config()
        self.assertEqual(data["upgrade"]["customization_handoff"], "report+relocate")
        self.assertIs(data["upgrade"]["github_issue"], False)
        self.assertIs(data["upgrade"]["descope_preserve_paths_edits"], True)
        # The template's own commentary travels with the block.
        result = self.read_config()
        self.assertIn("# customization_handoff: how upgrade disposes", result)
        self.assertIn("# opt-in gh issue (interactive only)", result)

    def test_added_key_result_parses_and_keeps_user_values(self):
        self.write_config(ANNOTATED_CONFIG)
        ip.migrate_config(self.cfg)

        data = self.load_config()
        self.assertEqual(data["plugin_version"], "1.0.3")
        self.assertEqual(data["context"]["token_saver_runner_overhead"], 29500)
        self.assertEqual(
            data["context"]["token_saver_context_breakdown"]["free_space"], 970500
        )
        self.assertEqual(data["context"]["token_saver_overhead_measured_on"], "2026-07-08")
        self.assertEqual(data["categorization"]["default_bucket"], "B")

    def test_migrate_that_adds_a_key_is_idempotent(self):
        self.write_config(ANNOTATED_CONFIG)
        ip.migrate_config(self.cfg)
        first = self.read_config()
        ip.migrate_config(self.cfg)
        self.assertEqual(
            first, self.read_config(), "re-running migrate must be a byte-for-byte no-op"
        )

    def test_whole_block_context_add_still_backfills_token_saver_subkeys(self):
        """A config with NO `context:` gets the whole block, sub-keys included."""
        self.write_config("project:\n  name: NoCtx\n")
        ip.migrate_config(self.cfg)

        context = self.load_config().get("context", {})
        for key in (
            "token_saver",
            "token_saver_session_target",
            "token_saver_runner_overhead",
            "token_saver_orchestrator_overhead",
            "token_saver_context_breakdown",
            "token_saver_overhead_measured_on",
        ):
            self.assertIn(key, context, f"whole-block add must land context.{key}")
        self.assertIs(
            context["token_saver"],
            False,
            "migration is toggle-neutral — the engine lands OFF",
        )
        self.assertEqual(context["context_window"], 1000000)


# ---------------------------------------------------------------------------
# _write_back() — block-mapping values and the ordinary single-line case
# ---------------------------------------------------------------------------
BLOCK_STYLE_CONFIG = """project:
  name: BlockStyle
context:
  plan_tier: max
  context_window: 1000000
  token_saver: true
  token_saver_session_target: 150000
  token_saver_runner_overhead: 26000
  token_saver_orchestrator_overhead: 24000
  token_saver_context_breakdown:
    system_prompt: 2600
    system_tools: 18100
    custom_agents: 959
    memory_files: 4300
    skills: 2200
    messages: 8
    free_space: 975000
  token_saver_overhead_measured_on: "2026-06-01"
scoring:
  priority_high: 30
"""


class TestWriteBackBlockMapping(_ConfigFixtureBase):

    def test_block_mapping_value_is_replaced_whole(self):
        path = self.write_config(BLOCK_STYLE_CONFIG)
        new_value = ts._format_breakdown(
            {"System prompt": 3900, "System tools": 18100, "Free space": 970500}
        )
        ts._write_back(path, {"token_saver_context_breakdown": new_value})

        result = self.read_config()
        # No orphaned children left behind.
        self.assertNotIn("system_prompt: 2600", result)
        self.assertNotIn("free_space: 975000", result)
        # ... and the file still parses, with the new value in place.
        data = yaml.safe_load(result)
        self.assertEqual(
            data["context"]["token_saver_context_breakdown"],
            {"system_prompt": 3900, "system_tools": 18100, "free_space": 970500},
        )

    def test_block_replacement_leaves_neighbouring_keys_untouched(self):
        path = self.write_config(BLOCK_STYLE_CONFIG)
        ts._write_back(path, {"token_saver_context_breakdown": "{}"})

        data = self.load_config()
        self.assertEqual(data["context"]["token_saver_runner_overhead"], 26000)
        self.assertEqual(data["context"]["token_saver_overhead_measured_on"], "2026-06-01")
        self.assertEqual(data["scoring"]["priority_high"], 30)
        self.assertIs(data["context"]["token_saver"], True)

    def test_block_parent_with_inline_comment_is_still_consumed(self):
        """A block parent may carry its own trailing comment — still a block."""
        annotated = BLOCK_STYLE_CONFIG.replace(
            "  token_saver_context_breakdown:\n",
            "  token_saver_context_breakdown:   # measured per-category breakdown\n",
        )
        path = self.write_config(annotated)
        ts._write_back(path, {"token_saver_context_breakdown": "{a: 1}"})

        result = self.read_config()
        self.assertNotIn("system_prompt: 2600", result)
        self.assertIn("# measured per-category breakdown", result)
        self.assertEqual(
            yaml.safe_load(result)["context"]["token_saver_context_breakdown"], {"a": 1}
        )

    def test_lone_comment_under_a_valueless_key_is_not_swallowed(self):
        """A bare comment is the user's note on an empty value, not a block."""
        commented = BLOCK_STYLE_CONFIG.replace(
            "  token_saver_context_breakdown:\n    system_prompt: 2600\n"
            "    system_tools: 18100\n    custom_agents: 959\n    memory_files: 4300\n"
            "    skills: 2200\n    messages: 8\n    free_space: 975000\n",
            "  token_saver_context_breakdown:\n    # not measured yet\n",
        )
        path = self.write_config(commented)
        ts._write_back(path, {"token_saver_context_breakdown": "{}"})

        result = self.read_config()
        self.assertIn("# not measured yet", result, "a lone note must survive")
        self.assertEqual(
            yaml.safe_load(result)["context"]["token_saver_context_breakdown"], {}
        )

    def test_flow_style_single_line_still_rewrites_and_keeps_inline_comment(self):
        """Guard against regressing the ordinary single-line path."""
        self.write_config(ANNOTATED_CONFIG)
        path = self.config_path()
        ts._write_back(
            path,
            {
                "token_saver_runner_overhead": 54000,
                "token_saver_context_breakdown": "{system_prompt: 3900}",
            },
        )

        result = self.read_config()
        self.assertIn(
            "  token_saver_runner_overhead: 54000      # measured subagent footprint",
            result,
            "the value must be rewritten in place and the inline comment kept",
        )
        data = yaml.safe_load(result)
        self.assertEqual(
            data["context"]["token_saver_context_breakdown"], {"system_prompt": 3900}
        )
        self.assertEqual(data["context"]["token_saver_orchestrator_overhead"], 29492)
        self.assertIn("# Measured on a real session", result)


class TestSetTokenSaverPath(_ConfigFixtureBase):
    """`/planwise token-saver on|off` rides the same editor as calibrate."""

    def test_toggle_off_then_on_over_a_block_style_config(self):
        path = self.write_config(BLOCK_STYLE_CONFIG)

        self.assertEqual(ts.set_token_saver(path, False), {"token_saver": False})
        self.assertIs(self.load_config()["context"]["token_saver"], False)
        # The block-mapping breakdown is untouched by the toggle and still parses.
        self.assertEqual(
            self.load_config()["context"]["token_saver_context_breakdown"]["free_space"],
            975000,
        )

        self.assertEqual(ts.set_token_saver(path, True), {"token_saver": True})
        self.assertIs(self.load_config()["context"]["token_saver"], True)

    def test_toggle_over_an_annotated_flow_style_config_preserves_comments(self):
        path = self.write_config(ANNOTATED_CONFIG)
        ts.set_token_saver(path, False)

        result = self.read_config()
        self.assertIs(yaml.safe_load(result)["context"]["token_saver"], False)
        self.assertIn("# Measured on a real session", result)
        self.assertIn("technology: [sql, mssql, postgres, sqlite, pyodbc]", result)
        self.assertIn(
            "token_saver_context_breakdown: {system_prompt: 3900, system_tools: 18100,",
            result,
        )


# ---------------------------------------------------------------------------
# Post-write parse check + rollback
# ---------------------------------------------------------------------------
class TestCheckedWriteRollback(_ConfigFixtureBase):

    def test_unparseable_write_is_rolled_back_and_raises(self):
        path = self.write_config(ANNOTATED_CONFIG)
        with self.assertRaises(config_loader.ConfigWriteError) as caught:
            config_loader.write_config_checked(path, "context:\n  broken: [unclosed\n")

        self.assertIn(str(path), str(caught.exception), "the error must name the path")
        self.assertEqual(
            self.read_config(),
            ANNOTATED_CONFIG,
            "a rolled-back write must leave the file byte-for-byte unchanged",
        )

    def test_parseable_write_is_kept(self):
        path = self.write_config(ANNOTATED_CONFIG)
        config_loader.write_config_checked(path, "project:\n  name: Replaced\n")
        self.assertEqual(self.load_config()["project"]["name"], "Replaced")

    def test_missing_file_is_removed_again_on_rollback(self):
        path = self.config_path()
        self.assertFalse(path.exists())
        with self.assertRaises(config_loader.ConfigWriteError):
            config_loader.write_config_checked(path, "a: [unclosed\n")
        self.assertFalse(path.exists(), "a rolled-back create must leave no file")

    def test_write_back_rolls_back_a_corrupting_value(self):
        """A value that would brick the file must never reach disk."""
        path = self.write_config(ANNOTATED_CONFIG)
        with self.assertRaises(config_loader.ConfigWriteError):
            ts._write_back(
                path, {"token_saver_runner_overhead": "26000\n  bogus: [unclosed"}
            )
        self.assertEqual(
            self.read_config(),
            ANNOTATED_CONFIG,
            "a rolled-back _write_back must leave the config unchanged",
        )

    def test_bump_plugin_version_fallback_appends_instead_of_re_dumping(self):
        """The legacy no-pin path appends the key as text, comments intact."""
        legacy = ANNOTATED_CONFIG.replace('plugin_version: "1.0.3"\n', "")
        path = self.write_config(legacy)
        ip._bump_plugin_version(path, "1.0.4")

        result = self.read_config()
        self.assertTrue(
            result.startswith(legacy),
            "the fallback must append, never re-emit the file",
        )
        self.assertEqual(self.load_config()["plugin_version"], "1.0.4")
        self.assertIn("# Measured on a real session", result)
        self.assertIn(
            "token_saver_context_breakdown: {system_prompt: 3900, system_tools: 18100,",
            result,
        )

    def test_bump_plugin_version_happy_path_edits_the_line(self):
        path = self.write_config(ANNOTATED_CONFIG)
        ip._bump_plugin_version(path, "1.0.4")
        self.assertEqual(self.load_config()["plugin_version"], "1.0.4")
        self.assertIn("# Measured on a real session", self.read_config())

    def test_flip_token_saver_on_routes_through_the_checked_writer(self):
        path = self.write_config(ANNOTATED_CONFIG.replace("token_saver: true", "token_saver: false"))
        self.assertTrue(ip._flip_token_saver_on(path))
        self.assertIs(self.load_config()["context"]["token_saver"], True)
        self.assertIn("# Measured on a real session", self.read_config())


# ---------------------------------------------------------------------------
# End-to-end: migrate-that-adds-a-key followed by a calibrate-style write
# ---------------------------------------------------------------------------
class TestUpgradePathEndToEnd(_ConfigFixtureBase):

    def test_migrate_then_calibrate_write_leaves_a_parseable_config(self):
        self.write_config(ANNOTATED_CONFIG)

        # Step 1 — the upgrade's migrate adds a new top-level key.
        _path, added, _present = ip.migrate_config(self.cfg)
        self.assertIn("upgrade", added)

        # Step 2 — recalibration writes the measured values back, exactly as
        # calibrate() does (flow-style breakdown, quoted ISO date).
        measured = {
            "System prompt": 3900,
            "System tools": 18100,
            "Custom agents": 959,
            "Memory files": 4300,
            "Skills": 2200,
            "Messages": 8,
            "Free space": 968400,
        }
        ts._write_back(
            self.config_path(),
            {
                "token_saver_runner_overhead": 31200,
                "token_saver_orchestrator_overhead": 31192,
                "token_saver_context_breakdown": ts._format_breakdown(measured),
                "token_saver_overhead_measured_on": '"2026-08-08"',
            },
        )

        # The config still parses ...
        data = self.load_config()
        # ... carries the migrate-added key ...
        self.assertEqual(data["upgrade"]["customization_handoff"], "report+relocate")
        # ... the new calibration values ...
        self.assertEqual(data["context"]["token_saver_runner_overhead"], 31200)
        self.assertEqual(data["context"]["token_saver_orchestrator_overhead"], 31192)
        self.assertEqual(
            data["context"]["token_saver_context_breakdown"]["free_space"], 968400
        )
        self.assertEqual(data["context"]["token_saver_overhead_measured_on"], "2026-08-08")
        # ... and the user's original comments.
        result = self.read_config()
        self.assertIn("# Measured on a real session", result)
        self.assertIn("# Routing buckets for lessons curate", result)
        self.assertIn("# keep this name, tooling greps for it", result)
        self.assertIn("technology: [sql, mssql, postgres, sqlite, pyodbc]", result)
        # No orphaned block was produced anywhere.
        self.assertIsNone(ip._detect_orphaned_block_signature(result))

    def test_calibrate_fallback_write_over_a_migrated_config(self):
        """calibrate()'s failed-capture path writes through the same editor."""
        self.write_config(ANNOTATED_CONFIG)
        ip.migrate_config(self.cfg)

        result = ts.calibrate(config_path=self.config_path(), capture=lambda *_a: None)
        self.assertFalse(result["calibrated"])

        data = self.load_config()
        self.assertEqual(
            data["context"]["token_saver_runner_overhead"], ts.FALLBACK_RUNNER_OVERHEAD
        )
        self.assertEqual(data["context"]["token_saver_context_breakdown"], {})
        self.assertEqual(data["upgrade"]["customization_handoff"], "report+relocate")
        self.assertIn("# Measured on a real session", self.read_config())


# ---------------------------------------------------------------------------
# Doctor detection of an unparseable config
# ---------------------------------------------------------------------------
BRICKED_CONFIG = """project:
  name: Bricked
context:
  plan_tier: max
  token_saver_context_breakdown: {system_prompt: 3900, free_space: 970500}
    system_prompt: 2600
    free_space: 975000
  token_saver_overhead_measured_on: "2026-06-01"
"""


class TestDoctorConfigParseCheck(_ConfigFixtureBase):

    def test_orphaned_block_signature_is_detected(self):
        self.assertEqual(
            ip._detect_orphaned_block_signature(BRICKED_CONFIG),
            "token_saver_context_breakdown",
        )

    def test_clean_config_has_no_orphan_signature(self):
        self.assertIsNone(ip._detect_orphaned_block_signature(ANNOTATED_CONFIG))
        self.assertIsNone(ip._detect_orphaned_block_signature(BLOCK_STYLE_CONFIG))

    def test_doctor_reports_an_unparseable_config_with_the_cause(self):
        self.write_config(BRICKED_CONFIG)
        check = ip._doctor_config_parse_check(self.cfg)

        self.assertIsNotNone(check)
        self.assertEqual(check["state"], "unparseable")
        self.assertIn("does not parse as YAML", check["report"])
        self.assertIn("token_saver_context_breakdown", check["report"])
        self.assertIn("action:", check["report"])

    def test_doctor_reports_a_clean_config_as_ok(self):
        self.write_config(ANNOTATED_CONFIG)
        check = ip._doctor_config_parse_check(self.cfg)
        self.assertIsNotNone(check)
        self.assertEqual(check["state"], "ok")
        self.assertIn("parses cleanly", check["report"])

    def test_doctor_skips_the_check_when_no_config_exists(self):
        self.assertIsNone(ip._doctor_config_parse_check(self.cfg))

    def test_version_gate_stays_green_on_a_bricked_config(self):
        """The regression this stage exists for: the gate cannot see the break."""
        self.write_config(BRICKED_CONFIG.replace(
            "project:\n", f'plugin_version: "{self.cfg.plugin_version}"\nproject:\n'
        ))
        gate = ip._doctor_version_gate(self.cfg)
        self.assertEqual(gate["state"], "ok")
        self.assertEqual(ip._doctor_config_parse_check(self.cfg)["state"], "unparseable")


if __name__ == "__main__":
    unittest.main()
