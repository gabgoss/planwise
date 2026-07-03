#!/usr/bin/env python3
"""Unit tests (TDD) for the rule de-scope + migration + linter contract.

These tests are written BEFORE the implementation. They pin the compatibility
contract that the de-scope migration must satisfy:

  * INSTALLED_RULES is trimmed to ONLY the four `.claude/**`-scoped rules.
  * DESCOPED_RULES enumerates the sixteen author-time rules removed from the
    install set (handler-loaded from references/ instead).
  * migrate_installed_rules(cfg, from_version, to_version) removes an installed
    de-scoped rule ONLY when its normalized body matches the shipped body AND
    its paths: line equals the resolved OLD default. ANY divergence (body OR
    paths) leaves the file byte-for-byte unchanged and reports it as a notice.
    It never auto-deletes a diverged file and never defaults to suggesting
    deletion of one.
  * lint_rule_overscope(cfg) flags plan-scoped rules (with a size/line field)
    without mutating anything on disk.

Run with:  python -m unittest scripts/test_rule_descope_migration.py

Until init_project.py grows the new symbols, every test below errors with an
AttributeError on the missing symbol (migrate_installed_rules,
lint_rule_overscope, DESCOPED_RULES, RESCOPE_MIGRATION_VERSION, or the trimmed
INSTALLED_RULES). That is the intended TDD red state, not a fixture bug.
"""

import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

# Allow `import init_project` whether unittest is launched from the repo root
# (python -m unittest scripts/test_...) or from inside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import init_project as ip  # noqa: E402


# The four rules that MUST remain in INSTALLED_RULES after the trim. These are
# scoped to `.claude/**` paths (authoring guidance for agents/skills/rules),
# NOT to plan paths, so they stay installed as path-scoped rules.
KEPT_RULES = {
    "agent-authoring.md",
    "skill-authoring.md",
    "rule-authoring.md",
    "artifact-self-containment.md",
}

# The sixteen author-time rules removed from the install set. Each is paired
# with the paths: template it carried BEFORE de-scoping, so the migration can
# reconstruct the OLD default and compare against the installed file.
EXPECTED_DESCOPED_PLANS = {
    "session-planning-protocol.md",
    "session-plan-requirements.md",
    "session-context-budget.md",
    "session-execution-protocol.md",
    "scaffolding-hygiene.md",
    "discovery-and-exit-criteria.md",
    "ei-fidelity.md",
    "schema-pin-requirement.md",
    "task-content-fidelity.md",
    "verification-gates.md",
    "verify-against-shipped-artifact.md",
    "verification-task-authoring.md",
}
EXPECTED_DESCOPED_ALL = {
    "agent-orchestration.md",
    "agent-orchestration-delegated.md",
    "callout-conventions.md",
    "markdown-conventions.md",
}
EXPECTED_DESCOPED = EXPECTED_DESCOPED_PLANS | EXPECTED_DESCOPED_ALL


def _flatten_report(report):
    """Collect every string found anywhere in a migration/linter report.

    The implementation's report shape is not over-constrained by these tests:
    it may be a dataclass, a dict of lists, or nested structures. This walks
    common containers and returns the set of strings encountered so a test can
    assert "this path was reported somewhere" without pinning the exact key.
    """
    found: set[str] = set()

    def walk(obj):
        if obj is None:
            return
        if isinstance(obj, str):
            found.add(obj)
            return
        if isinstance(obj, (list, tuple, set, frozenset)):
            for item in obj:
                walk(item)
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                walk(key)
                walk(value)
            return
        # Dataclass / object: walk its public attributes.
        attrs = getattr(obj, "__dict__", None)
        if attrs:
            for value in attrs.values():
                walk(value)

    walk(report)
    return found


def _report_section(report, *name_fragments):
    """Return the strings under the report section whose key matches a fragment.

    Looks for a dict key (or attribute name) containing any of the given
    case-insensitive fragments (e.g. "removed", "conflict", "notice") and
    returns the flattened strings beneath it. Returns an empty set if no such
    section exists, letting the caller assert presence/absence precisely.
    """
    fragments = tuple(f.lower() for f in name_fragments)

    def match(key):
        return isinstance(key, str) and any(f in key.lower() for f in fragments)

    if isinstance(report, dict):
        out: set[str] = set()
        for key, value in report.items():
            if match(key):
                out |= _flatten_report(value)
        return out

    attrs = getattr(report, "__dict__", None)
    if attrs:
        out = set()
        for key, value in attrs.items():
            if match(key):
                out |= _flatten_report(value)
        return out
    return set()


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    """Map each file under root (relative POSIX path) to its exact bytes."""
    snap: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snap[path.relative_to(root).as_posix()] = path.read_bytes()
    return snap


def _verdict(classification, confidence="contained", unique_blocks=()):
    """Build a canned StructuralVerdict-shaped object for the monkeypatch seam.

    Disposition tests patch `ip._classify_diverged` to return one of these so
    the assertions pin the site's disposition logic, not the real
    structural_compare primitive's segmentation accuracy.
    """
    return types.SimpleNamespace(
        classification=classification, confidence=confidence,
        unique_blocks=list(unique_blocks))


class _MigrationFixtureBase(unittest.TestCase):
    """Builds a temporary project tree with a fake install + references dir."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_descope_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"

        self.rules_dir = self.project_root / ".claude" / "rules" / "planwise"
        self.refs_dir = self.plugin_root / "references"
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self.refs_dir.mkdir(parents=True, exist_ok=True)

        self.cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
        )

        # The resolved OLD default paths values, reused by helpers below.
        self.plans_paths_value = ip.resolve_rule_paths_value(self.cfg, "{plans_path}")
        self.all_paths_value = ip.resolve_rule_paths_value(self.cfg, "{all_paths}")

    # -- helpers ----------------------------------------------------------

    def _rule_text(self, body: str, paths_value: str | None) -> str:
        """Build rule file text: frontmatter (with optional paths:) + body."""
        if paths_value is None:
            return f"---\ndescription: fixture rule\n---\n{body}"
        return (
            "---\n"
            "description: fixture rule\n"
            f"paths: {paths_value}\n"
            "---\n"
            f"{body}"
        )

    def write_shipped(self, filename: str, body: str) -> Path:
        """Write the plugin-shipped reference (carries placeholder paths:)."""
        # Shipped references carry the literal {plans_path}/{all_paths} token,
        # matching how update_frontmatter is applied only at install time.
        if filename in EXPECTED_DESCOPED_ALL:
            placeholder = "{all_paths}"
        else:
            placeholder = "{plans_path}"
        text = self._rule_text(body, placeholder)
        dst = self.refs_dir / filename
        dst.write_text(text, encoding="utf-8")
        return dst

    def write_installed(self, filename: str, body: str, paths_value: str) -> Path:
        """Write an installed rule copy with a concrete resolved paths: line."""
        text = self._rule_text(body, paths_value)
        dst = self.rules_dir / filename
        dst.write_text(text, encoding="utf-8")
        return dst

    def old_default_for(self, filename: str) -> str:
        """Resolved OLD default paths: value for a de-scoped filename."""
        if filename in EXPECTED_DESCOPED_ALL:
            return self.all_paths_value
        return self.plans_paths_value

    def write_upgrade_config(self, **upgrade_overrides) -> Path:
        """Write config.yaml with an `upgrade:` block under the fixture root.

        Exercises the `descope_preserve_paths_edits` opt-out that
        migrate_installed_rules() reads via get_upgrade_config() at the
        Site-1 fast path. Absent unless a test calls this — no config.yaml
        means the conservative defaults apply.
        """
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        lines = ["upgrade:"]
        for key, value in upgrade_overrides.items():
            if value is True:
                yaml_value = "true"
            elif value is False:
                yaml_value = "false"
            else:
                yaml_value = str(value)
            lines.append(f"  {key}: {yaml_value}")
        config_path = config_dir / "config.yaml"
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return config_path


class TestRulePartition(_MigrationFixtureBase):
    """The INSTALLED_RULES trim and the DESCOPED_RULES enumeration."""

    def test_installed_rules_trimmed_to_four_claude_scoped(self):
        installed_names = {entry[0] for entry in ip.INSTALLED_RULES}
        self.assertEqual(
            installed_names,
            KEPT_RULES,
            "INSTALLED_RULES must contain ONLY the four .claude/**-scoped rules "
            "after de-scoping",
        )
        # None of the de-scoped rules may linger in the install set.
        self.assertFalse(
            installed_names & EXPECTED_DESCOPED,
            "No de-scoped rule may remain in INSTALLED_RULES",
        )
        # The kept rules must NOT be plan-scoped templates.
        for filename, paths_template in ip.INSTALLED_RULES:
            self.assertNotIn("{plans_path}", paths_template)

    def test_descoped_rules_enumeration(self):
        descoped = ip.DESCOPED_RULES
        names = {entry[0] for entry in descoped}
        self.assertEqual(
            names,
            EXPECTED_DESCOPED,
            "DESCOPED_RULES must list exactly the 16 de-scoped filenames",
        )
        self.assertEqual(len(descoped), 16, "DESCOPED_RULES must have 16 entries")

        templates = {entry[0]: entry[1] for entry in descoped}
        for filename in EXPECTED_DESCOPED_PLANS:
            self.assertEqual(
                templates[filename],
                "{plans_path}",
                f"{filename} must pair with the {{plans_path}} old template",
            )
        for filename in EXPECTED_DESCOPED_ALL:
            self.assertEqual(
                templates[filename],
                "{all_paths}",
                f"{filename} must pair with the {{all_paths}} old template",
            )

    def test_partition_is_disjoint_and_covers_old_install_set(self):
        installed_names = {entry[0] for entry in ip.INSTALLED_RULES}
        descoped_names = {entry[0] for entry in ip.DESCOPED_RULES}
        self.assertFalse(
            installed_names & descoped_names,
            "INSTALLED_RULES and DESCOPED_RULES must be disjoint",
        )
        self.assertEqual(
            installed_names | descoped_names,
            KEPT_RULES | EXPECTED_DESCOPED,
            "Together the two sets must cover the full pre-de-scope install set",
        )


class TestMigrationBranches(_MigrationFixtureBase):
    """One test per branch of migrate_installed_rules()."""

    def _to_version(self) -> str:
        return str(ip.RESCOPE_MIGRATION_VERSION)

    def test_untouched_rule_is_removed(self):
        filename = "session-planning-protocol.md"
        body = "# Session Planning Protocol\n\nBody content line.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "An untouched de-scoped rule (matching body + old default paths) "
            "must be removed",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry for entry in removed),
            f"{filename} must be reported under the removed section",
        )

    def test_body_diverged_rule_is_preserved_with_notice(self):
        filename = "ei-fidelity.md"
        shipped_body = "# EI Fidelity\n\nOriginal shipped body.\n"
        edited_body = "# EI Fidelity\n\nUSER EDITED this body line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, edited_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists(), "A body-diverged rule must be kept")
        self.assertEqual(
            installed.read_bytes(), before, "Diverged rule must be byte-for-byte unchanged"
        )
        notice = _report_section(report, "conflict", "notice", "preserved", "kept")
        self.assertTrue(
            any(filename in entry for entry in notice),
            f"{filename} must be reported as a conflict/notice, not removed",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(
            any(filename in entry for entry in removed),
            "A diverged rule must NOT appear under removed",
        )

    def test_paths_customized_rule_is_preserved_with_notice(self):
        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nMatching body.\n"
        self.write_shipped(filename, body)
        custom_paths = self.old_default_for(filename) + ", docs/**"
        installed = self.write_installed(filename, body, custom_paths)
        before = installed.read_bytes()

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(), "A paths-customized rule must be kept (body matches but paths differ)"
        )
        self.assertEqual(installed.read_bytes(), before, "Paths-customized rule must be unchanged")
        notice = _report_section(report, "conflict", "notice", "preserved", "kept")
        self.assertTrue(
            any(filename in entry for entry in notice),
            f"{filename} (custom paths:) must be reported as a conflict/notice",
        )

    def test_notice_does_not_default_to_suggesting_delete(self):
        filename = "markdown-conventions.md"
        shipped_body = "# Markdown Conventions\n\nShipped.\n"
        edited_body = "# Markdown Conventions\n\nEdited by user.\n"
        self.write_shipped(filename, shipped_body)
        self.write_installed(filename, edited_body, self.old_default_for(filename))

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        notice = _report_section(report, "conflict", "notice", "preserved", "kept")
        self.assertTrue(notice, "A diverged rule must surface a notice")
        # The notice for a preserved file must not lead with a 'delete' verdict.
        for entry in notice:
            self.assertNotIn(
                "delete",
                entry.lower(),
                "Preserved-file notices must NOT default to suggesting deletion",
            )

    def test_non_descoped_rule_left_unchanged(self):
        # A project-authored rule that is not in DESCOPED_RULES.
        filename = "nhle-foo.md"
        body = "# Project Rule\n\nProject-authored, not shipped.\n"
        plan_scope = f"{self.cfg.planwise_root}/{self.cfg.plans_dir}/**"
        installed = self.write_installed(filename, body, plan_scope)
        before = installed.read_bytes()

        ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists(), "A non-de-scoped rule must be left in place")
        self.assertEqual(
            installed.read_bytes(),
            before,
            "A non-de-scoped, project-authored rule must be byte-for-byte unchanged",
        )

    def test_migration_is_idempotent(self):
        filename = "schema-pin-requirement.md"
        body = "# Schema Pin\n\nBody.\n"
        self.write_shipped(filename, body)
        self.write_installed(filename, body, self.old_default_for(filename))

        first = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())
        first_removed = _report_section(first, "removed", "deleted")
        self.assertTrue(
            any(filename in entry for entry in first_removed),
            "First run must remove the untouched de-scoped rule",
        )
        snapshot = _snapshot_tree(self.project_root)

        # Second run: nothing left to remove, no error, same end state.
        second = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())
        second_removed = _report_section(second, "removed", "deleted")
        self.assertFalse(
            any(filename in entry for entry in second_removed),
            "Second run must find nothing to remove (idempotent)",
        )
        self.assertEqual(
            _snapshot_tree(self.project_root),
            snapshot,
            "Re-running the migration must not change the tree",
        )

    def test_version_gate_makes_migration_a_noop(self):
        filename = "discovery-and-exit-criteria.md"
        body = "# Discovery\n\nBody.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )
        before = _snapshot_tree(self.project_root)

        # from_version already at/after the rescope migration version -> no-op.
        already_migrated = str(ip.RESCOPE_MIGRATION_VERSION)
        ip.migrate_installed_rules(
            self.cfg, already_migrated, self._to_version()
        )

        self.assertTrue(
            installed.exists(),
            "Version gate: when from_version >= RESCOPE_MIGRATION_VERSION the "
            "migration must touch nothing",
        )
        self.assertEqual(
            _snapshot_tree(self.project_root),
            before,
            "Version-gated no-op must leave the tree byte-for-byte identical",
        )

    # -- verdict-driven disposition cases (monkeypatch seam) -----------------

    def test_subset_of_reflowed_shipped_is_removed(self):
        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "A stale SUBSET (contained confidence) of the grown shipped "
            "reference must be removed",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry for entry in removed),
            f"{filename} must be reported under removed",
        )

    def test_has_unique_is_preserved_with_block_count(self):
        filename = "session-context-budget.md"
        shipped_body = "# Session Context Budget\n\nShipped body.\n"
        installed_body = (
            "# Session Context Budget\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists(), "HAS_UNIQUE must be preserved, not removed")
        self.assertEqual(
            installed.read_bytes(), before, "HAS_UNIQUE file must be kept byte-for-byte"
        )
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "1 customized block" in entry
                for entry in preserved
            ),
            f"{filename} must be reported preserved with the unique block count",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(
            any(filename in entry for entry in removed),
            "HAS_UNIQUE must never appear under removed",
        )

    def test_reorg_subset_is_preserved_with_inconclusive_notice(self):
        filename = "session-execution-protocol.md"
        shipped_body = (
            "# Session Execution Protocol\n\nReflowed section A.\nReflowed section B.\n"
        )
        installed_body = "# Session Execution Protocol\n\nSection B.\nSection A.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "reorg")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A reorg SUBSET is headless-inconclusive, not auto-removed",
        )
        self.assertEqual(installed.read_bytes(), before)
        notice = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "inconclusive" in entry.lower()
                for entry in notice
            ),
            f"{filename} must carry a headless-inconclusive notice",
        )

    def test_paths_only_edit_subset_is_removed_with_info(self):
        filename = "scaffolding-hygiene.md"
        body = "# Scaffolding Hygiene\n\nMatching body.\n"
        self.write_shipped(filename, body)
        custom_paths = self.old_default_for(filename) + ", custom/**"
        installed = self.write_installed(filename, body, custom_paths)
        self.write_upgrade_config(descope_preserve_paths_edits=False)

        with mock.patch.object(
            ip, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "Body-identical, paths-only-edited de-scoped rule must be removed "
            "when the preserve opt-out is disabled",
        )
        removed = _report_section(report, "removed", "deleted")
        matches = [entry for entry in removed if filename in entry]
        self.assertTrue(matches, f"{filename} must be reported under removed")
        self.assertTrue(
            any("INFO" in entry for entry in matches),
            "The removed notice must carry the [INFO] token for a paths-only edit",
        )

    def test_paths_only_edit_opt_out_is_preserved(self):
        filename = "task-content-fidelity.md"
        body = "# Task Content Fidelity\n\nMatching body.\n"
        self.write_shipped(filename, body)
        custom_paths = self.old_default_for(filename) + ", custom/**"
        installed = self.write_installed(filename, body, custom_paths)
        before = installed.read_bytes()
        self.write_upgrade_config(descope_preserve_paths_edits=True)

        with mock.patch.object(
            ip, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "Body-identical, paths-only-edited de-scoped rule must be preserved "
            "when the preserve opt-out is enabled",
        )
        self.assertEqual(installed.read_bytes(), before)
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry for entry in preserved),
            f"{filename} must be reported preserved (opt-out enabled)",
        )


class TestLinter(_MigrationFixtureBase):
    """lint_rule_overscope() flags overscoped rules without mutating disk."""

    def test_flags_plan_scoped_rule_only_and_mutates_nothing(self):
        plan_scope = f"{self.cfg.planwise_root}/{self.cfg.plans_dir}/**"
        code_scope = ".claude/**"

        plan_body = "# Plan Scoped Rule\n\n" + ("filler line\n" * 20)
        code_body = "# Code Scoped Rule\n\nShort body.\n"
        self.write_installed("over-scoped-plan.md", plan_body, plan_scope)
        self.write_installed("agent-authoring.md", code_body, code_scope)

        before = _snapshot_tree(self.project_root)
        report = ip.lint_rule_overscope(self.cfg)
        after = _snapshot_tree(self.project_root)

        self.assertEqual(before, after, "lint_rule_overscope must not mutate the disk")

        flagged = _flatten_report(report)
        self.assertTrue(
            any("over-scoped-plan.md" in entry for entry in flagged),
            "The plan-scoped rule must be flagged as overscoped",
        )
        self.assertFalse(
            any("agent-authoring.md" in entry for entry in flagged),
            "The .claude/**-scoped (code-scoped) rule must NOT be flagged",
        )

    def test_report_includes_a_size_or_line_field(self):
        plan_scope = f"{self.cfg.planwise_root}/{self.cfg.plans_dir}/**"
        plan_body = "# Plan Scoped Rule\n\n" + ("filler line\n" * 30)
        self.write_installed("big-plan-rule.md", plan_body, plan_scope)

        report = ip.lint_rule_overscope(self.cfg)

        # Somewhere in the report a size/line metric must accompany the flag.
        def has_numeric(obj):
            if isinstance(obj, (int, float)) and not isinstance(obj, bool):
                return True
            if isinstance(obj, dict):
                return any(has_numeric(v) for v in obj.values()) or any(
                    has_numeric(k) for k in obj.keys()
                )
            if isinstance(obj, (list, tuple, set, frozenset)):
                return any(has_numeric(i) for i in obj)
            attrs = getattr(obj, "__dict__", None)
            if attrs:
                return any(has_numeric(v) for v in attrs.values())
            return False

        self.assertTrue(
            has_numeric(report),
            "The overscope report must carry a size/line field (a numeric metric)",
        )


class TestUpgradeConfigFoundation(unittest.TestCase):
    """Foundation invariants for the `upgrade:` config surface.

    Plain TestCase on purpose: these are pure constant/function assertions
    that need none of the migration fixture's temp project tree.
    """

    _DEFAULTS = {
        "customization_handoff": "report",
        "github_issue": False,
        # True preserves today's behavior (a paths-only-edited de-scoped
        # rule is kept); False is the explicit opt-in to removal.
        "descope_preserve_paths_edits": True,
    }

    def test_get_upgrade_config_defaults_on_absent_block(self):
        import config_loader as cl

        self.assertEqual(
            cl.get_upgrade_config({}),
            self._DEFAULTS,
            "get_upgrade_config({}) must return the conservative defaults",
        )

    def test_get_upgrade_config_defaults_on_non_dict_block(self):
        import config_loader as cl

        self.assertEqual(
            cl.get_upgrade_config({"upgrade": "not-a-dict"}),
            self._DEFAULTS,
            "A non-dict upgrade: block must also fall back to defaults",
        )

    def test_get_upgrade_config_string_booleans_not_truthy_coerced(self):
        import config_loader as cl

        result = cl.get_upgrade_config(
            {"upgrade": {"github_issue": "false", "descope_preserve_paths_edits": "false"}}
        )
        self.assertFalse(
            result["github_issue"],
            'a quoted "false" must mean False, not bool-truthy True',
        )
        self.assertFalse(result["descope_preserve_paths_edits"])
        result = cl.get_upgrade_config({"upgrade": {"github_issue": "true"}})
        self.assertTrue(result["github_issue"])

    def test_get_upgrade_config_null_handoff_falls_back_to_report(self):
        import config_loader as cl

        result = cl.get_upgrade_config({"upgrade": {"customization_handoff": None}})
        self.assertEqual(
            result["customization_handoff"],
            "report",
            "an explicitly-null customization_handoff must fall back to 'report'",
        )

    def test_upgrade_in_migratable_top_level_keys(self):
        self.assertIn(
            "upgrade",
            ip.MIGRATABLE_TOP_LEVEL_KEYS,
            "MIGRATABLE_TOP_LEVEL_KEYS must include 'upgrade' so --migrate "
            "backfills the block into existing configs",
        )

    def test_rule_comparator_in_installed_agents(self):
        self.assertIn(
            "rule-comparator.md",
            ip.INSTALLED_AGENTS,
            "INSTALLED_AGENTS must include 'rule-comparator.md'",
        )


class TestNormalizeRuleForDiffFallback(unittest.TestCase):
    """normalize_rule_for_diff must be byte-identical with and without the
    structural_compare module (the degraded-install fallback path)."""

    SAMPLES = [
        "---\npaths: a/**\ndescription: x\n---\n# H\nbody\n",
        "---\ndescription: x\npaths: '{plans_path}/**'\n---\n# H\nbody\n",
        "---\npaths: a/**\n---\nbody only\n",
        "# no frontmatter\nbody\n",
        "---\nunterminated frontmatter\n",
        "",
    ]

    def test_fallback_split_byte_identical(self):
        for sample in self.SAMPLES:
            with_module = ip.normalize_rule_for_diff(sample)
            saved = ip.structural_compare
            try:
                ip.structural_compare = None
                without_module = ip.normalize_rule_for_diff(sample)
            finally:
                ip.structural_compare = saved
            self.assertEqual(
                with_module,
                without_module,
                f"fallback output diverged for sample: {sample!r}",
            )


class _UpgradeArtifactsFixtureBase(unittest.TestCase):
    """Builds a temp tree for exercising upgrade_artifacts() (Sites 2/3).

    Separate from _MigrationFixtureBase's DESCOPED_RULES-driven tree: this
    fixture monkeypatches the INSTALLED_RULES / INSTALLED_AGENTS module
    globals to a single fixture entry each, so the three-way rules/agents
    branches in upgrade_artifacts() can be exercised without needing every
    real shipped rule/agent file on disk.
    """

    RULE_FILENAME = "agent-authoring.md"
    RULE_PATHS_TEMPLATE = ".claude/agents/**"
    AGENT_FILENAME = "fix-agent.md"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_upgrade_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"

        self.rules_dst_dir = self.project_root / ".claude" / "rules" / "planwise"
        self.refs_dir = self.plugin_root / "references"
        self.agents_dst_dir = self.project_root / ".claude" / "agents"
        self.agents_src_dir = self.plugin_root / "agents"
        for d in (self.rules_dst_dir, self.refs_dir, self.agents_dst_dir, self.agents_src_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
        )
        self.manifest = {"artifacts": []}

        # Scope the module-global allowlists to this fixture's single rule and
        # single agent, so upgrade_artifacts() iterates exactly the files this
        # test controls (no unrelated real-shipped-file warnings/untracked noise).
        rules_patch = mock.patch.object(
            ip, "INSTALLED_RULES", [(self.RULE_FILENAME, self.RULE_PATHS_TEMPLATE)]
        )
        agents_patch = mock.patch.object(ip, "INSTALLED_AGENTS", [self.AGENT_FILENAME])
        rules_patch.start()
        agents_patch.start()
        self.addCleanup(rules_patch.stop)
        self.addCleanup(agents_patch.stop)

    # -- rule helpers ---------------------------------------------------------

    def _rule_text(self, body: str, paths_value: str) -> str:
        return f"---\ndescription: fixture rule\npaths: {paths_value}\n---\n{body}"

    def write_shipped_rule(self, body: str, paths_value: str | None = None) -> Path:
        dst = self.refs_dir / self.RULE_FILENAME
        dst.write_text(
            self._rule_text(body, paths_value or self.RULE_PATHS_TEMPLATE),
            encoding="utf-8",
        )
        return dst

    def write_installed_rule(self, body: str, paths_value: str) -> Path:
        dst = self.rules_dst_dir / self.RULE_FILENAME
        dst.write_text(self._rule_text(body, paths_value), encoding="utf-8")
        return dst

    # -- agent helpers ----------------------------------------------------------

    def write_shipped_agent(self, body: str) -> Path:
        dst = self.agents_src_dir / self.AGENT_FILENAME
        dst.write_text(body, encoding="utf-8")
        return dst

    def write_installed_agent(self, body: str) -> Path:
        dst = self.agents_dst_dir / self.AGENT_FILENAME
        dst.write_text(body, encoding="utf-8")
        return dst

    # -- run + derived paths ------------------------------------------------

    def run_upgrade(self, from_version="1.0.0", to_version="1.1.0"):
        return ip.upgrade_artifacts(self.cfg, self.manifest, from_version, to_version)

    def conflict_dir(self, from_version="1.0.0", to_version="1.1.0") -> Path:
        return (
            self.project_root / self.cfg.planwise_root / "upgrade-conflicts"
            / f"{from_version}-to-{to_version}"
        )


class TestUpgradeArtifactsDisposition(_UpgradeArtifactsFixtureBase):
    """One test per Sites 2/3 disposition branch of upgrade_artifacts()."""

    def test_conflict_subset_refreshes_in_place_no_sidecar(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets = (
                self.run_upgrade()
            )

        self.assertIn(str(installed), refreshed)
        self.assertIn(str(installed), refreshed_subsets)
        self.assertEqual(conflicts, [])

        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated),
            ip.normalize_rule_for_diff(shipped_raw),
            "Refreshed body must equal the shipped body (normalized)",
        )
        self.assertEqual(
            ip._extract_paths_value(updated), custom_paths,
            "The per-project paths: must be preserved across the refresh",
        )
        sidecar = (
            self.conflict_dir() / ".claude" / "rules" / "planwise"
            / f"{self.RULE_FILENAME}.new"
        )
        self.assertFalse(sidecar.exists(), "A SUBSET refresh must NOT write a .new sidecar")

    def test_conflict_has_unique_keeps_and_writes_sidecar_and_index(self):
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets = (
                self.run_upgrade()
            )

        self.assertEqual(
            installed.read_bytes(), before, "HAS_UNIQUE rule must be left untouched"
        )
        self.assertEqual(refreshed_subsets, [])
        self.assertNotIn(str(installed), refreshed)
        self.assertTrue(conflicts, "HAS_UNIQUE must record a conflict")
        dst_path, sidecar_path = conflicts[0]
        self.assertEqual(dst_path, str(installed))
        sidecar = Path(sidecar_path)
        self.assertTrue(sidecar.exists(), ".new sidecar must be written for HAS_UNIQUE")
        self.assertEqual(sidecar.read_text(encoding="utf-8"), shipped_raw)

        index_path = self.conflict_dir() / "INDEX.md"
        self.assertTrue(index_path.exists(), "INDEX.md must be written when conflicts exist")
        index_text = index_path.read_text(encoding="utf-8")
        self.assertIn(str(installed), index_text)

    def test_agent_subset_overwrites_shipped_no_sidecar(self):
        shipped_body = "# Agent\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Agent\n\nShipped superset body.\n"
        self.write_shipped_agent(shipped_body)
        installed = self.write_installed_agent(installed_body)

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets = (
                self.run_upgrade()
            )

        self.assertEqual(
            installed.read_text(encoding="utf-8"), shipped_body,
            "A SUBSET agent must be overwritten with the shipped body verbatim",
        )
        self.assertIn(str(installed), refreshed)
        self.assertIn(str(installed), refreshed_subsets)
        self.assertEqual(conflicts, [])
        sidecar = (
            self.conflict_dir() / ".claude" / "agents" / f"{self.AGENT_FILENAME}.new"
        )
        self.assertFalse(
            sidecar.exists(), "A SUBSET agent refresh must NOT write a .new sidecar"
        )

    def test_agent_has_unique_keeps_and_writes_sidecar(self):
        shipped_body = "# Agent\n\nShipped body.\n"
        installed_body = "# Agent\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_agent(shipped_body)
        installed = self.write_installed_agent(installed_body)
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets = (
                self.run_upgrade()
            )

        self.assertEqual(
            installed.read_bytes(), before, "HAS_UNIQUE agent must be left untouched"
        )
        self.assertEqual(refreshed_subsets, [])
        self.assertNotIn(str(installed), refreshed)
        self.assertTrue(conflicts, "HAS_UNIQUE agent must record a conflict")
        dst_path, sidecar_path = conflicts[0]
        self.assertEqual(dst_path, str(installed))
        sidecar = Path(sidecar_path)
        self.assertTrue(
            sidecar.exists(), ".new sidecar must be written for HAS_UNIQUE agent"
        )
        self.assertEqual(sidecar.read_text(encoding="utf-8"), shipped_body)

    def test_byte_identical_skips_primitive(self):
        body = "# Rule\n\nIdentical body.\n"
        paths_value = ".claude/agents/**"
        self.write_shipped_rule(body, paths_value)
        installed_rule = self.write_installed_rule(body, paths_value)
        agent_body = "# Agent\n\nIdentical body.\n"
        self.write_shipped_agent(agent_body)
        installed_agent = self.write_installed_agent(agent_body)

        original = ip._classify_diverged
        ip._classify_diverged = mock.Mock(
            side_effect=AssertionError("fast path must not consult the primitive")
        )
        self.addCleanup(setattr, ip, "_classify_diverged", original)

        refreshed, unchanged, conflicts, untracked, refreshed_subsets = (
            self.run_upgrade()
        )

        self.assertEqual(conflicts, [])
        self.assertEqual(refreshed_subsets, [])
        self.assertIn(str(installed_rule), unchanged)
        self.assertIn(str(installed_agent), unchanged)


if __name__ == "__main__":
    unittest.main()
