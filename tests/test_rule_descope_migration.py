#!/usr/bin/env python3
"""Unit tests (TDD) for the rule de-scope + migration + linter contract.

These tests are written BEFORE the implementation. They pin the compatibility
contract that the de-scope migration must satisfy:

  * INSTALLED_RULES is trimmed to ONLY the four `.claude/**`-scoped rules.
  * DESCOPED_RULES enumerates the sixteen author-time rules removed from the
    install set (handler-loaded from references/ instead).
  * migrate_installed_rules(cfg, from_version, to_version) removes an installed
    de-scoped rule when it is provably redundant: normalized body matches the
    shipped body (with paths: equal to the resolved OLD default, or the
    preserve opt-out disabled), or a high-confidence stale SUBSET with a clean
    notes field. A customization-bearing copy (HAS_UNIQUE, or a SUBSET whose
    notes flag tolerated installed-only content) is gated on the effective
    `upgrade.customization_handoff`: `report+relocate` verified-transfers the
    customization to the upgrade transfer helper's preservation home and only
    then backs up and removes the stale file; any other value (including the
    absent-key fallback, `report`) preserves it byte-for-byte with a re-home
    notice. A failed transfer or backup means NO removal. The migration never
    defaults to suggesting deletion of a preserved file.
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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

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


def _verdict(classification, confidence="contained", unique_blocks=(), notes=""):
    """Build a canned StructuralVerdict-shaped object for the monkeypatch seam.

    Disposition tests patch `ip._classify_diverged` to return one of these so
    the assertions pin the site's disposition logic, not the real
    structural_compare primitive's segmentation accuracy.

    `notes` defaults to "" (the common case). Pass a non-empty string to pin
    the notes-gate branches: a SUBSET verdict whose notes flag tolerated
    installed-only content must be preserved/sidecar'd rather than
    removed/refreshed, even at exact/contained confidence.
    """
    return types.SimpleNamespace(
        classification=classification, confidence=confidence,
        unique_blocks=list(unique_blocks), notes=notes)


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
    """One test per branch of migrate_installed_rules().

    No fixture here writes a `customization_handoff` key, so every
    customization-bearing preserve assertion below pins the conservative
    absent-key fallback (`report`): preserve in place, no transfer, no
    removal. The `report+relocate` transfer-then-remove flow is pinned
    separately in TestSite1TransferThenRemove.
    """

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

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to parse the template")
    def test_template_ships_report_relocate_while_absent_key_stays_report(self):
        """The shipped config.yaml.template pins customization_handoff to
        report+relocate EXPLICITLY; the loader's absent-key fallback stays the
        conservative 'report' (pinned by the defaults tests above)."""
        import yaml

        template_path = (
            Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        )
        data = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        self.assertEqual(
            data["upgrade"]["customization_handoff"],
            "report+relocate",
            "the shipped template must opt new installs into the automated "
            "transfer-then-adopt flow explicitly",
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
    fixture monkeypatches the INSTALLED_RULES module global to a single
    fixture entry, so the rule branch in upgrade_artifacts() can be
    exercised without needing every real shipped rule file on disk.
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
        rules_patch.start()
        self.addCleanup(rules_patch.stop)

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

    # -- config helpers -------------------------------------------------------

    def write_upgrade_config(self, **upgrade_overrides) -> Path:
        """Write config.yaml with an `upgrade:` block under the fixture root.

        upgrade_artifacts() reads `upgrade.customization_handoff` via
        get_upgrade_config() at run time; an absent config.yaml means the
        conservative `report` default applies (preserve + sidecar, no
        transfer, no adoption of customization-bearing files).
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

    def enable_relocate(self) -> Path:
        """Opt this fixture into the automated transfer-then-adopt path."""
        return self.write_upgrade_config(customization_handoff="report+relocate")

    # -- run + derived paths ------------------------------------------------

    def run_upgrade(self, from_version="1.0.0", to_version="1.1.0"):
        return ip.upgrade_artifacts(self.cfg, self.manifest, from_version, to_version)

    def conflict_dir(self, from_version="1.0.0", to_version="1.1.0") -> Path:
        return (
            self.project_root / self.cfg.planwise_root / "upgrade-conflicts"
            / f"{from_version}-to-{to_version}"
        )

    def transfer_dir(self, from_version="1.0.0", to_version="1.1.0") -> Path:
        return (
            self.project_root / self.cfg.planwise_root / "upgrade-transfers"
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
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
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

    def test_conflict_has_unique_transfers_customization_then_adopts_shipped(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        # Automated, transfer-first: the customization is moved out FIRST,
        # verified, and only then is shipped adopted in place — the installed
        # copy is NOT left untouched (that was the old sidecar-and-stop policy).
        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated), ip.normalize_rule_for_diff(shipped_raw),
            "HAS_UNIQUE rule must be adopted to shipped once its customization is transferred",
        )
        self.assertEqual(ip._extract_paths_value(updated), custom_paths)
        self.assertIn(str(installed), refreshed)
        self.assertEqual(refreshed_subsets, [], "adoption via transfer is NOT a stale-subset auto-adopt")
        self.assertEqual(conflicts, [], "a successfully transferred HAS_UNIQUE is not a conflict")

        self.assertEqual(len(transferred), 1)
        dst_path, transfer_path = transferred[0]
        self.assertEqual(dst_path, str(installed))
        transfer_file = Path(transfer_path)
        self.assertEqual(
            transfer_file.parent,
            self.transfer_dir(),
            "transfer target is {planwise_root}/upgrade-transfers/<from>-to-<to>/ "
            "(a dormant preservation dir outside .claude/rules/)",
        )
        transferred_text = transfer_file.read_text(encoding="utf-8")
        self.assertIn("# Extra", transferred_text)
        self.assertIn("User-added block.", transferred_text)

        index_path = self.conflict_dir() / "INDEX.md"
        self.assertFalse(
            index_path.exists(),
            "no unresolved conflict remains once the customization is transferred and adopted",
        )

    def test_has_unique_failed_transfer_preserves_and_writes_sidecar(self):
        """The failed-transfer carve-out: when the customization cannot be
        VERIFIED-written to the upgrade-transfers preservation file, the
        installed copy must be preserved byte-for-byte (never adopt/remove
        without a verified transfer) and the conservative shipped sidecar
        written."""
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        shipped = self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(ip, "_transfer_customization", return_value=None):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        self.assertEqual(
            installed.read_bytes(), before,
            "A failed transfer must preserve the installed file byte-for-byte",
        )
        self.assertNotIn(str(installed), refreshed)
        self.assertEqual(transferred, [], "a failed transfer must not be reported as transferred")
        self.assertTrue(conflicts, "a failed transfer must fall back to the conflict branch")
        dst_path, sidecar_path = conflicts[0]
        self.assertEqual(dst_path, str(installed))
        sidecar = Path(sidecar_path)
        self.assertTrue(sidecar.exists(), ".new sidecar must be written on a failed transfer")
        self.assertEqual(sidecar.read_text(encoding="utf-8"), shipped.read_text(encoding="utf-8"))

    def test_byte_identical_skips_primitive(self):
        body = "# Rule\n\nIdentical body.\n"
        paths_value = ".claude/agents/**"
        self.write_shipped_rule(body, paths_value)
        installed_rule = self.write_installed_rule(body, paths_value)

        original = ip._classify_diverged
        ip._classify_diverged = mock.Mock(
            side_effect=AssertionError("fast path must not consult the primitive")
        )
        self.addCleanup(setattr, ip, "_classify_diverged", original)

        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
            self.run_upgrade()
        )

        self.assertEqual(conflicts, [])
        self.assertEqual(refreshed_subsets, [])
        self.assertIn(str(installed_rule), unchanged)


class TestMigrationVerdictNotesAndPathsGates(_MigrationFixtureBase):
    """Site-1 (migrate_installed_rules) safety fixes: the notes gate, the
    paths-preserve opt-out on a diverged (not just fast-path) body, the real
    structural_compare primitive on a genuine strict-prefix subset, the
    upgrade-backups/DISPOSITIONS.md pre-image, per-file OSError containment,
    and the degraded-mode ("NOT analyzed") wording.

    Like TestMigrationBranches, no fixture here sets `customization_handoff`,
    so the customization-bearing preserve assertions pin the conservative
    absent-key fallback (`report`). The `report+relocate` transfer-then-remove
    flow is pinned in TestSite1TransferThenRemove.
    """

    def _to_version(self) -> str:
        return str(ip.RESCOPE_MIGRATION_VERSION)

    def test_notes_gate_preserves_diverged_subset(self):
        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        notes_text = (
            "installed-only tokens present in sub-noise-floor fragments "
            "(tolerated as noise)"
        )

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("SUBSET", "exact", notes=notes_text),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(), "A notes-flagged SUBSET must be preserved, not removed"
        )
        self.assertEqual(installed.read_bytes(), before)
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry and notes_text in entry for entry in preserved),
            "The preserved notice must surface the verdict's notes text",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(
            any(filename in entry for entry in removed),
            "A notes-flagged SUBSET must NOT appear under removed",
        )

    def test_diverged_stale_subset_paths_preserve_opt_out_default(self):
        filename = "verify-against-shipped-artifact.md"
        shipped_body = "# Verify Against Shipped Artifact\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Verify Against Shipped Artifact\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        custom_paths = self.old_default_for(filename) + ", custom/**"
        installed = self.write_installed(filename, installed_body, custom_paths)
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A diverged stale-subset body with customized paths: must be kept "
            "when the preserve opt-out is enabled (the default)",
        )
        self.assertEqual(installed.read_bytes(), before)
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "preserve opt-out covers paths" in entry
                for entry in preserved
            ),
            "The preserved notice must explain the paths opt-out covers the "
            "diverged body too",
        )

    def test_diverged_stale_subset_paths_opt_out_disabled_removed_with_info(self):
        filename = "verification-gates.md"
        shipped_body = "# Verification Gates\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Verification Gates\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        custom_paths = self.old_default_for(filename) + ", custom/**"
        installed = self.write_installed(filename, installed_body, custom_paths)
        self.write_upgrade_config(descope_preserve_paths_edits=False)

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "With the preserve opt-out disabled, a diverged stale-subset body "
            "with customized paths: must be removed",
        )
        removed = _report_section(report, "removed", "deleted")
        matches = [entry for entry in removed if filename in entry]
        self.assertTrue(matches, f"{filename} must be reported under removed")
        self.assertTrue(
            any("INFO" in entry for entry in matches),
            "The removed notice must carry the [INFO] token for the dropped paths: edit",
        )

    def test_real_primitive_subset_rule_removed_site1(self):
        # NO seam patching — exercises the real structural_compare primitive.
        filename = "verification-task-authoring.md"
        old_template = "{plans_path}"
        shipped_old_body = "# Verification Task Authoring\n\nOriginal line.\n"
        shipped_grown_body = shipped_old_body + "Grown extra line.\n"
        self.write_shipped(filename, shipped_grown_body)

        default_paths = self.old_default_for(filename)
        # Build the installed file the way install_rules() actually would:
        # update_frontmatter() on the (old, placeholder-carrying) shipped text.
        shipped_old_text = self._rule_text(shipped_old_body, old_template)
        installed_text = ip.update_frontmatter(shipped_old_text, default_paths)
        installed = self.rules_dir / filename
        installed.write_text(installed_text, encoding="utf-8")
        self.assertEqual(
            ip._extract_paths_value(installed_text), default_paths,
            "Fixture sanity: update_frontmatter must produce the resolved default",
        )

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "A real strict-prefix subset (paths matching the old default) must "
            "be removed by the real classifier, with no verdict override",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(any(filename in entry for entry in removed))

    def test_backup_and_dispositions_written_on_site1_removal(self):
        filename = "session-planning-protocol.md"
        body = "# Session Planning Protocol\n\nBody content line.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(filename, body, self.old_default_for(filename))
        before = installed.read_bytes()
        to_version = self._to_version()

        ip.migrate_installed_rules(self.cfg, "0.0.0", to_version)

        self.assertFalse(installed.exists())
        backup_dir = (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / f"0.0.0-to-{to_version}"
        )
        backup_file = backup_dir / ".claude" / "rules" / "planwise" / filename
        self.assertTrue(
            backup_file.exists(), "Site-1 removal must mirror the pre-image under upgrade-backups/"
        )
        self.assertEqual(backup_file.read_bytes(), before)
        self.assertTrue(
            (backup_dir / "DISPOSITIONS.md").exists(),
            "DISPOSITIONS.md must be written alongside the backup",
        )

    def test_site1_containment_skips_unreadable_entry_and_continues(self):
        # A directory in place of the installed file forces read_text() to
        # raise OSError — the per-file containment must record it as skipped
        # and continue to the next (normal) fixture without raising.
        dir_filename = "callout-conventions.md"
        dir_path = self.rules_dir / dir_filename
        dir_path.mkdir(parents=True, exist_ok=True)

        normal_filename = "schema-pin-requirement.md"
        body = "# Schema Pin\n\nBody.\n"
        self.write_shipped(normal_filename, body)
        normal_installed = self.write_installed(
            normal_filename, body, self.old_default_for(normal_filename)
        )

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            normal_installed.exists(),
            "The normal fixture must still be dispositioned despite the other's failure",
        )
        skipped = _report_section(report, "skipped")
        self.assertTrue(
            any(
                dir_filename in entry and "disposition failed" in entry
                for entry in skipped
            ),
            "The unreadable directory entry must be reported as skipped, not raise",
        )

    def test_degraded_mode_site1_preserved_not_analyzed(self):
        filename = "task-content-fidelity.md"
        shipped_body = "# Task Content Fidelity\n\nShipped body.\n"
        installed_body = (
            "# Task Content Fidelity\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()

        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists(), "Degraded mode must preserve, never remove")
        self.assertEqual(installed.read_bytes(), before)
        preserved = _report_section(report, "preserved", "kept")
        matches = [entry for entry in preserved if filename in entry]
        self.assertTrue(matches)
        self.assertTrue(
            any("NOT analyzed" in entry for entry in matches),
            "Degraded-mode preserve notice must say the copy was NOT analyzed",
        )
        self.assertFalse(
            any("0 customized block(s)" in entry for entry in matches),
            "Degraded mode must never claim '0 customized block(s)' "
            "(analysis never ran)",
        )


class TestSite1TransferThenRemove(_MigrationFixtureBase):
    """The de-scope migration's customization_handoff gate: a
    customization-bearing de-scoped rule (HAS_UNIQUE, or a SUBSET whose notes
    flag tolerated installed-only content) transfers-then-removes under
    `customization_handoff: report+relocate` (the shipped template default),
    and preserves in place under the conservative modes or on ANY
    transfer/backup failure. The paths-edit preserve opt-out
    (`descope_preserve_paths_edits`, default true) takes PRECEDENCE over the
    handoff gate: a paths-customized copy is preserved in place even when the
    body also carries a customization — never weaker protection for the
    more-customized file. The migration reuses the artifact refresh
    writer's `_transfer_customization()` helper and destination convention —
    pinned here so the migration path can never drift onto a second transfer
    writer or a different destination.
    """

    def _to_version(self) -> str:
        return str(ip.RESCOPE_MIGRATION_VERSION)

    def _transfer_dir(self) -> Path:
        return (
            self.project_root / self.cfg.planwise_root / "upgrade-transfers"
            / f"0.0.0-to-{self._to_version()}"
        )

    def _backup_dir(self) -> Path:
        return (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / f"0.0.0-to-{self._to_version()}"
        )

    def test_has_unique_transferred_then_removed_under_relocate(self):
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
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "Under report+relocate a HAS_UNIQUE de-scoped rule must be removed "
            "after its customization is transferred",
        )
        transfer_file = self._transfer_dir() / filename
        self.assertTrue(
            transfer_file.exists(),
            "The customization must land at the transfer helper's destination "
            "(upgrade-transfers/{from}-to-{to}/)",
        )
        self.assertIn(
            installed_body,
            transfer_file.read_text(encoding="utf-8"),
            "The transfer file must carry the full installed body",
        )
        backup_file = (
            self._backup_dir() / ".claude" / "rules" / "planwise" / filename
        )
        self.assertTrue(
            backup_file.exists(),
            "Removal must be preceded by a pre-image backup under upgrade-backups/",
        )
        self.assertEqual(backup_file.read_bytes(), before)
        self.assertTrue(
            (self._backup_dir() / "DISPOSITIONS.md").exists(),
            "The removal must be logged to DISPOSITIONS.md",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry and "transferred" in entry for entry in removed),
            "The removed notice must say the customization was transferred",
        )
        preserved = _report_section(report, "preserved", "kept")
        self.assertFalse(
            any(filename in entry for entry in preserved),
            "A transferred-then-removed file must not also appear under preserved",
        )

    def test_notes_flagged_subset_transferred_then_removed_under_relocate(self):
        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        self.write_upgrade_config(customization_handoff="report+relocate")
        notes_text = (
            "installed-only tokens present in sub-noise-floor fragments "
            "(tolerated as noise)"
        )

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("SUBSET", "exact", notes=notes_text),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "Under report+relocate a notes-flagged SUBSET (customization-bearing) "
            "must be removed after its customization is transferred",
        )
        transfer_file = self._transfer_dir() / filename
        self.assertTrue(transfer_file.exists())
        self.assertIn(installed_body, transfer_file.read_text(encoding="utf-8"))
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry and "transferred" in entry for entry in removed)
        )

    def test_report_mode_preserves_untouched_no_transfer_no_removal(self):
        filename = "ei-fidelity.md"
        shipped_body = "# EI Fidelity\n\nShipped body.\n"
        installed_body = "# EI Fidelity\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report")

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "Under report (conservative) mode a HAS_UNIQUE de-scoped rule must "
            "be preserved in place",
        )
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(
            self._transfer_dir().exists(),
            "report mode must never write a transfer file",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(any(filename in entry for entry in removed))
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(any(filename in entry for entry in preserved))

    def test_transfer_failure_means_no_removal(self):
        filename = "verification-gates.md"
        shipped_body = "# Verification Gates\n\nShipped body.\n"
        installed_body = "# Verification Gates\n\nShipped body.\n# Extra\nCustom.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(ip, "_transfer_customization", return_value=None):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A failed transfer must mean NO removal — never destroy the only "
            "copy of a customization",
        )
        self.assertEqual(installed.read_bytes(), before)
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(any(filename in entry for entry in removed))
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "transfer failed" in entry
                for entry in preserved
            ),
            "The preserved notice must report the failed transfer",
        )

    def test_backup_failure_means_no_removal(self):
        filename = "verify-against-shipped-artifact.md"
        shipped_body = "# Verify Against Shipped Artifact\n\nShipped body.\n"
        installed_body = (
            "# Verify Against Shipped Artifact\n\nShipped body.\n# Extra\nCustom.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(ip, "_write_backup_preimage", return_value=False):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A failed pre-removal backup must mean NO removal",
        )
        self.assertEqual(installed.read_bytes(), before)
        transfer_file = self._transfer_dir() / filename
        self.assertTrue(
            transfer_file.exists(),
            "The verified transfer precedes the backup, so the transfer file "
            "exists even when the backup then fails",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(any(filename in entry for entry in removed))
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry and "backup" in entry for entry in preserved),
            "The preserved notice must report the failed backup",
        )

    def test_paths_and_body_customized_preserved_under_relocate_with_optout_default(self):
        # Regression (R1 finding 1): a rule customized in BOTH paths: AND body
        # must never get WEAKER protection than one customized in paths: alone.
        # With descope_preserve_paths_edits at its default (true, key absent),
        # the paths-opt-out takes precedence over customization_handoff:
        # report+relocate must NOT transfer-then-remove — preserve untouched.
        filename = "task-content-fidelity.md"
        shipped_body = "# Task Content Fidelity\n\nShipped body.\n"
        installed_body = (
            "# Task Content Fidelity\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, "src/custom/**"   # customized paths: line
        )
        before = installed.read_bytes()
        # Only customization_handoff set; descope_preserve_paths_edits absent
        # -> defaults to true via get_upgrade_config().
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A paths+body-customized rule must be preserved in place under "
            "report+relocate while the paths-edit preserve opt-out is on — "
            "the more-customized file must never get weaker protection than "
            "the less-customized one",
        )
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(
            self._transfer_dir().exists(),
            "The paths-opt-out precedence means NO transfer file is written",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(any(filename in entry for entry in removed))
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "paths-customized" in entry
                for entry in preserved
            ),
            "The preserve notice must attribute the preservation to the paths: "
            "customization (existing notice convention)",
        )

    def test_paths_and_body_customized_notes_flagged_subset_also_preserved(self):
        # Same precedence for the OTHER customization-bearing branch (a
        # notes-flagged SUBSET): the paths-opt-out wins over report+relocate.
        filename = "session-planning-protocol.md"
        shipped_body = "# Session Planning Protocol\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Planning Protocol\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, "src/custom/**"   # customized paths: line
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict(
                "SUBSET", "exact",
                notes="installed-only tokens tolerated as sub-noise-floor fragments"),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists())
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(self._transfer_dir().exists())
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry and "paths-customized" in entry for entry in preserved)
        )

    def test_paths_and_body_customized_relocated_when_optout_disabled(self):
        # Counterpart: with descope_preserve_paths_edits explicitly false, the
        # paths: customization no longer blocks the handoff gate — under
        # report+relocate the body customization transfers and the file is
        # removed (same flow as a paths-matching HAS_UNIQUE).
        filename = "discovery-and-exit-criteria.md"
        shipped_body = "# Discovery and Exit Criteria\n\nShipped body.\n"
        installed_body = (
            "# Discovery and Exit Criteria\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, "src/custom/**"   # customized paths: line
        )
        self.write_upgrade_config(
            customization_handoff="report+relocate",
            descope_preserve_paths_edits=False,
        )

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "With the paths-edit opt-out disabled, report+relocate transfers "
            "then removes a paths+body-customized rule",
        )
        transfer_file = self._transfer_dir() / filename
        self.assertTrue(transfer_file.exists())
        self.assertIn(installed_body, transfer_file.read_text(encoding="utf-8"))
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry and "transferred" in entry for entry in removed)
        )

    def test_reorg_subset_still_preserved_under_relocate(self):
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
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "reorg")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A reorg-confidence SUBSET is a confidence gap, not a genuine "
            "customization — it must stay preserved even under report+relocate",
        )
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(
            self._transfer_dir().exists(),
            "A reorg-inconclusive verdict must never trigger a transfer",
        )
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "inconclusive" in entry.lower()
                for entry in preserved
            )
        )

    def test_degraded_not_analyzed_still_preserved_under_relocate(self):
        filename = "task-content-fidelity.md"
        shipped_body = "# Task Content Fidelity\n\nShipped body.\n"
        installed_body = (
            "# Task Content Fidelity\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "The degraded not-analyzed stand-in must preserve even under "
            "report+relocate — there is no verdict evidence to transfer on",
        )
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(
            self._transfer_dir().exists(),
            "Degraded mode must never write a transfer file",
        )
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry and "NOT analyzed" in entry for entry in preserved)
        )

    def test_sweep_stays_read_only_under_relocate(self):
        filename = "callout-conventions.md"
        shipped_body = "# Callout Conventions\n\nShipped body.\n"
        installed_body = (
            "# Callout Conventions\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        self.write_upgrade_config(customization_handoff="report+relocate")
        before = _snapshot_tree(self.project_root)

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertTrue(
            installed.exists(),
            "The doctor sweep is read-only regardless of customization_handoff "
            "— only the upgrade migration and the opt-in pruner write",
        )
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "report+relocate must not leak into the read-only sweep: the tree "
            "must be byte-for-byte unchanged",
        )


class TestUpgradeArtifactsVerdictNotesAndGates(_UpgradeArtifactsFixtureBase):
    """Sites 2/3 (upgrade_artifacts) disposition gates under the automated
    transfer-first policy: a notes-flagged SUBSET transfers-then-adopts (the
    tolerated fragment is moved to a project-owned file before shipped is
    adopted), a pure reorg-confidence agent subset auto-adopts via the
    frontmatter-preservation guard, the any-confidence rule refresh gate, the
    normalized-equal fast path, the real structural_compare primitive,
    upgrade-backups/DISPOSITIONS.md, sidecar/INDEX cleanup, per-file OSError
    containment, and degraded mode (never analyzed -> preserve + sidecar,
    nothing adopted or transferred).
    """

    def test_notes_gate_site2_rule_transfers_then_refreshes(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)
        notes_text = (
            "installed-only tokens present in sub-noise-floor fragments "
            "(tolerated as noise)"
        )

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("SUBSET", "exact", notes=notes_text),
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        # A notes-flagged SUBSET is customization-bearing: the tolerated
        # installed-only fragment is transferred to a project-owned file
        # FIRST, then shipped is adopted in place (paths: preserved).
        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated), ip.normalize_rule_for_diff(shipped_raw),
            "A notes-flagged SUBSET rule must be refreshed to shipped after transfer",
        )
        self.assertEqual(ip._extract_paths_value(updated), custom_paths)
        self.assertIn(str(installed), refreshed)
        self.assertNotIn(
            str(installed), refreshed_subsets,
            "a transferred adoption is NOT counted as a clean stale-subset adopt",
        )
        self.assertEqual(conflicts, [], "a successful transfer resolves the would-be conflict")
        self.assertEqual(len(transferred), 1)
        dst_path, transfer_path = transferred[0]
        self.assertEqual(dst_path, str(installed))
        transferred_text = Path(transfer_path).read_text(encoding="utf-8")
        self.assertIn(
            "Shipped superset body.", transferred_text,
            "the transfer file must carry the installed content (the notes fragment carrier)",
        )
        self.assertIn(notes_text, transferred_text,
                      "the transfer file must surface the verdict's notes")

    def test_reorg_subset_rule_refreshes_in_place(self):
        shipped_body = "# Rule\n\nSection A.\nSection B.\n"
        installed_body = "# Rule\n\nSection B.\nSection A.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "reorg")
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        self.assertIn(
            str(installed), refreshed,
            "Rules keep the any-confidence SUBSET gate — a reorg subset still refreshes",
        )
        self.assertIn(str(installed), refreshed_subsets)
        self.assertEqual(conflicts, [])
        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated), ip.normalize_rule_for_diff(shipped_raw)
        )
        self.assertEqual(ip._extract_paths_value(updated), custom_paths)

    def test_normalized_equal_byte_different_paths_rule_uses_fast_path(self):
        body = "# Rule\n\nIdentical normalized body.\n"
        self.write_shipped_rule(body, ".claude/agents/**")
        installed_rule = self.write_installed_rule(body, ".claude/agents/**, custom/**")

        original = ip._classify_diverged
        ip._classify_diverged = mock.Mock(
            side_effect=AssertionError("fast path must not consult the primitive")
        )
        self.addCleanup(setattr, ip, "_classify_diverged", original)

        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
            self.run_upgrade()
        )

        self.assertEqual(conflicts, [])
        self.assertIn(str(installed_rule), unchanged)
        self.assertNotIn(str(installed_rule), refreshed)

    def test_real_primitive_subset_rule_refreshes(self):
        # NO seam patching — exercises the real structural_compare primitive.
        shipped_body = "# Rule\n\nShipped body.\nGrown extra line.\n"
        installed_body = "# Rule\n\nShipped body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)

        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
            self.run_upgrade()
        )

        self.assertIn(str(installed), refreshed)
        self.assertIn(str(installed), refreshed_subsets)
        self.assertEqual(conflicts, [])
        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated), ip.normalize_rule_for_diff(shipped_raw)
        )
        self.assertEqual(ip._extract_paths_value(updated), custom_paths)

    def test_backup_and_dispositions_written_on_site2_rule_adoption(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, custom_paths)
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            self.run_upgrade()

        backup_dir = (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / "1.0.0-to-1.1.0"
        )
        backup_file = backup_dir / ".claude" / "rules" / "planwise" / self.RULE_FILENAME
        self.assertTrue(
            backup_file.exists(), "Site-2 adoption must mirror the pre-image under upgrade-backups/"
        )
        self.assertEqual(backup_file.read_bytes(), before)
        self.assertTrue((backup_dir / "DISPOSITIONS.md").exists())

    def test_stale_sidecar_removed_on_adoption(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")

        sidecar = (
            self.conflict_dir() / ".claude" / "rules" / "planwise"
            / f"{self.RULE_FILENAME}.new"
        )
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text("stale sidecar from an interrupted prior run", encoding="utf-8")
        self.assertTrue(sidecar.exists())

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        self.assertIn(str(installed), refreshed)
        self.assertFalse(
            sidecar.exists(), "A resolved adoption must remove the stale .new sidecar"
        )

    def test_stale_index_pruned_when_no_conflicts_remain(self):
        body = "# Rule\n\nIdentical body.\n"
        paths_value = ".claude/agents/**"
        self.write_shipped_rule(body, paths_value)
        self.write_installed_rule(body, paths_value)

        conflict_dir = self.conflict_dir()
        conflict_dir.mkdir(parents=True, exist_ok=True)
        index_path = conflict_dir / "INDEX.md"
        index_path.write_text("# stale index from a prior resolved run\n", encoding="utf-8")

        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
            self.run_upgrade()
        )

        self.assertEqual(conflicts, [])
        self.assertFalse(
            index_path.exists(),
            "A stale INDEX.md with no remaining .new sidecars must be pruned",
        )

    def test_site3_containment_skips_unreadable_rule_and_continues(self):
        second_rule = "second-rule.md"
        with mock.patch.object(
            ip, "INSTALLED_RULES",
            [(self.RULE_FILENAME, self.RULE_PATHS_TEMPLATE),
             (second_rule, self.RULE_PATHS_TEMPLATE)],
        ):
            self.write_shipped_rule("# Rule\n\nShipped body.\n")
            # Directory in place of the installed file forces read_text() to
            # raise OSError for this entry only.
            dir_dst = self.rules_dst_dir / self.RULE_FILENAME
            dir_dst.mkdir(parents=True, exist_ok=True)

            second_shipped = self.refs_dir / second_rule
            second_shipped.write_text(
                self._rule_text("# Second Rule\n\nBody.\n", self.RULE_PATHS_TEMPLATE),
                encoding="utf-8",
            )

            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        second_installed = self.rules_dst_dir / second_rule
        self.assertTrue(
            second_installed.exists(),
            "The other rule must still be processed (fresh install) despite "
            "the directory entry's failure",
        )
        self.assertIn(str(second_installed), refreshed)

    def test_degraded_mode_upgrade_artifacts_nothing_refreshed(self):
        shipped_rule_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_rule_body = "# Rule\n\nShipped superset body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        self.write_shipped_rule(shipped_rule_body)
        installed_rule = self.write_installed_rule(installed_rule_body, custom_paths)
        before_rule = installed_rule.read_bytes()

        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        self.assertEqual(installed_rule.read_bytes(), before_rule)
        self.assertNotIn(str(installed_rule), refreshed)
        self.assertEqual(refreshed_subsets, [])
        self.assertEqual(len(conflicts), 1)


class TestClassifyDivergedDegradedFallback(unittest.TestCase):
    """Unit-level pin for the degraded-install verdict `_classify_diverged`
    manufactures when structural_compare is unavailable at call time."""

    def test_classify_diverged_degraded_on_missing_structural_compare(self):
        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            verdict = ip._classify_diverged("installed body", "shipped body")

        self.assertEqual(verdict.classification, "HAS_UNIQUE")
        self.assertTrue(
            getattr(verdict, "notes", ""),
            "The degraded stand-in verdict must carry a non-empty notes field",
        )


class TestDoctorStaleSweep(_MigrationFixtureBase):
    """sweep_stale_descoped_rules() + _run_prune_stale() + the _run_doctor()
    Stage 8 call site.

    The one-shot migrate_installed_rules() version gate is spent for any
    install already past RESCOPE_MIGRATION_VERSION, so these are the only
    remaining reach into stale de-scoped rules: a read-only sweep (recommends
    a disposition) and a separate opt-in writer (--prune-stale). Mirrors
    TestMigrationBranches' `ip._classify_diverged` monkeypatch seam so branch
    selection is tested independently of the structural_compare primitive.
    """

    def test_post_boundary_stale_subset_removable_and_tree_unchanged(self):
        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        # Post-boundary precondition: the one-shot migration's version gate
        # is already spent for this install.
        self.cfg.plugin_version = "1.0.4"
        before = _snapshot_tree(self.project_root)

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1, f"{filename} must produce exactly one finding")
        self.assertEqual(matches[0]["verdict"], "REMOVABLE")
        self.assertTrue(
            installed.exists(), "The bare sweep is read-only — it must never delete"
        )
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "The bare sweep must leave the installed tree byte-for-byte unchanged",
        )

    def test_identical_leftover_removable_exact_fast_path(self):
        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )

        with mock.patch.object(
            ip, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "REMOVABLE")
        self.assertEqual(matches[0]["confidence"], "exact")
        self.assertTrue(installed.exists(), "The sweep never deletes")

    def test_has_unique_is_preserved_with_unique_blocks(self):
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
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertEqual(matches[0]["unique_blocks"], ["# Extra"])
        self.assertEqual(
            installed.read_bytes(), before, "PRESERVE must never mutate the file"
        )

    def test_reorg_subset_is_preserved_not_auto_removed(self):
        filename = "session-execution-protocol.md"
        shipped_body = (
            "# Session Execution Protocol\n\nReflowed section A.\nReflowed section B.\n"
        )
        installed_body = "# Session Execution Protocol\n\nSection B.\nSection A.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "reorg")
        ):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["verdict"], "PRESERVE",
            "A reorg-confidence SUBSET is not auto-removable — it must escalate",
        )
        self.assertTrue(installed.exists())

    def test_prefix_rename_fingerprint_is_relocated(self):
        descoped_name = "callout-conventions.md"
        renamed = self.rules_dir / f"myproj-{descoped_name}"
        renamed.write_text(
            "# Callout Conventions\n\nPrefix-renamed workaround.\n", encoding="utf-8"
        )

        findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == renamed.name]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "RELOCATE")
        self.assertEqual(matches[0]["confidence"], "fingerprint")

    def test_prune_stale_removes_only_removable_and_writes_prunedmd(self):
        import datetime

        removable_filename = "session-planning-protocol.md"
        removable_body = "# Session Planning Protocol\n\nUntouched body.\n"
        self.write_shipped(removable_filename, removable_body)
        removable = self.write_installed(
            removable_filename, removable_body, self.old_default_for(removable_filename)
        )

        # No shipped reference written for this one — the "reference
        # unavailable, cannot prove stale" branch resolves it to PRESERVE.
        preserve_filename = "ei-fidelity.md"
        preserve_body = "# EI Fidelity\n\nNo shipped reference to compare against.\n"
        preserve = self.write_installed(
            preserve_filename, preserve_body, self.old_default_for(preserve_filename)
        )

        # Pin the version-state gate to "ok" so _run_prune_stale() proceeds
        # past the preflight into the sweep/removal logic.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertFalse(removable.exists(), "A REMOVABLE finding must be unlinked")
        self.assertTrue(preserve.exists(), "A PRESERVE finding must never be unlinked")

        today = datetime.date.today().isoformat()
        pruned = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}" / "PRUNED.md"
        )
        self.assertTrue(pruned.exists())
        text = pruned.read_text(encoding="utf-8")
        self.assertIn("## Removed", text)
        self.assertIn(removable_filename, text)
        self.assertIn("## Preserved", text)
        self.assertIn(preserve_filename, text)

    def test_stage8_wired_into_doctor_path(self):
        import contextlib
        import io

        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )

        # A second file with genuine unique content (HAS_UNIQUE -> PRESERVE),
        # so the doctor path's PRESERVE action line is exercised too.
        preserve_filename = "session-context-budget.md"
        preserve_shipped_body = "# Session Context Budget\n\nShipped body.\n"
        preserve_installed_body = (
            "# Session Context Budget\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(preserve_filename, preserve_shipped_body)
        preserve_installed = self.write_installed(
            preserve_filename, preserve_installed_body, self.old_default_for(preserve_filename)
        )

        # Pin the version-state gate to "ok" (pinned == installed) so
        # _run_doctor() proceeds past the preflight into Stage 8.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )
        before = _snapshot_tree(self.project_root)

        def _classify_side_effect(installed_norm, shipped_norm):
            if "Extra" in installed_norm:
                return _verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"])
            return _verdict("SUBSET", "contained")

        buf = io.StringIO()
        with mock.patch.object(
            ip, "_classify_diverged", side_effect=_classify_side_effect
        ):
            with contextlib.redirect_stdout(buf):
                exit_code = ip._run_doctor(self.cfg)

        stdout = buf.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "stale de-scoped rule sweep", stdout,
            "Stage 8 must be invoked by _run_doctor(), not merely defined",
        )
        self.assertTrue(
            any(filename in line and "REMOVABLE" in line for line in stdout.splitlines()),
            "The doctor path must print a REMOVABLE row for the stale subset",
        )
        self.assertIn(
            "action:  remove with /planwise doctor --prune-stale", stdout,
            "REMOVABLE rows must print the documented action line",
        )
        self.assertIn(
            "action:  re-home to .claude/rules/<project>/<name>.md — do NOT delete", stdout,
            "PRESERVE rows must print the documented action line too",
        )
        self.assertTrue(installed.exists())
        self.assertTrue(preserve_installed.exists())
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "The doctor path (bare --doctor) must never write or delete",
        )

    def test_notes_flagged_subset_preserved_and_survives_prune(self):
        import datetime

        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )

        # SUBSET + "contained" is otherwise safe-to-remove — the non-empty
        # notes field is the ONLY thing that must flip this to PRESERVE.
        notes_text = "tolerated a sub-noise-floor installed-only fragment"
        verdict = _verdict("SUBSET", "contained", notes=notes_text)
        with mock.patch.object(ip, "_classify_diverged", return_value=verdict):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["verdict"], "PRESERVE",
            "A subset with non-empty notes must NOT be REMOVABLE, even at "
            "exact/contained confidence",
        )
        self.assertIn(notes_text, matches[0]["reason"])
        self.assertTrue(installed.exists(), "The bare sweep is read-only")

        # Pin the version-state gate to "ok" so _run_prune_stale() proceeds
        # past the preflight into the sweep/removal logic.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        with mock.patch.object(ip, "_classify_diverged", return_value=verdict):
            result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(
            installed.exists(), "A notes-flagged subset must survive --prune-stale"
        )
        today = datetime.date.today().isoformat()
        pruned = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}" / "PRUNED.md"
        )
        text = pruned.read_text(encoding="utf-8")
        preserved_section = text.split("## Preserved", 1)[1]
        self.assertIn(
            filename, preserved_section,
            "The notes-flagged file must be listed under Preserved, not Removed",
        )

    def test_prune_writes_pre_image_backup_alongside_prunedmd(self):
        import datetime

        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )
        original_content = installed.read_bytes()

        # Pin the version-state gate to "ok" so _run_prune_stale() proceeds
        # past the preflight into the sweep/removal logic.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertFalse(installed.exists(), "A REMOVABLE finding must be unlinked")

        today = datetime.date.today().isoformat()
        backup = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}" / filename
        )
        self.assertTrue(
            backup.exists(),
            "A pre-image backup must be written alongside PRUNED.md before deletion",
        )
        self.assertEqual(
            backup.read_bytes(), original_content,
            "The backup must be an exact pre-image of the removed file",
        )

    def test_prune_stale_refuses_when_version_gate_not_ok(self):
        """No config.yaml -> the version-state gate is 'uninitialized'; the
        writer must refuse rather than sweep or delete anything."""
        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )
        before = _snapshot_tree(self.project_root)

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(installed.exists(), "A gate refusal must never delete anything")
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "A gate refusal must leave the installed tree byte-for-byte unchanged",
        )
        backups_root = self.project_root / self.cfg.planwise_root / "upgrade-backups"
        self.assertFalse(
            backups_root.exists(), "A gate refusal must not create any prune folder"
        )

    def test_prune_unlink_failure_marks_remove_failed_no_orphan_backup(self):
        import datetime

        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )

        # Pin the version-state gate to "ok" so _run_prune_stale() proceeds
        # past the preflight into the sweep/removal logic.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        original_unlink = Path.unlink

        def _raising_unlink(self_path, *args, **kwargs):
            if self_path == installed:
                raise OSError("mock: cannot remove")
            return original_unlink(self_path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", _raising_unlink):
            result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(installed.exists(), "A failed unlink must leave the file in place")

        today = datetime.date.today().isoformat()
        out_dir = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}"
        )
        pruned_text = (out_dir / "PRUNED.md").read_text(encoding="utf-8")
        preserved_section = pruned_text.split("## Preserved", 1)[1]
        self.assertIn(
            "[REMOVE_FAILED] — could not remove", preserved_section,
            "A failed unlink must be reported as REMOVE_FAILED, not REMOVABLE",
        )
        self.assertIn(filename, preserved_section)
        self.assertFalse(
            (out_dir / filename).exists(),
            "The orphan pre-image backup must be cleaned up after a failed unlink",
        )

    def test_second_prune_run_same_day_gets_uniquified_folder(self):
        import datetime

        # Pin the version-state gate to "ok" for both runs.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        self.write_installed(filename, body, self.old_default_for(filename))

        result1 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result1, 0)

        # A second REMOVABLE file so the second same-day run has something to prune.
        filename2 = "markdown-conventions.md"
        body2 = "# Markdown Conventions\n\nUntouched body.\n"
        self.write_shipped(filename2, body2)
        self.write_installed(filename2, body2, self.old_default_for(filename2))

        result2 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result2, 0)

        today = datetime.date.today().isoformat()
        backups_root = self.project_root / self.cfg.planwise_root / "upgrade-backups"
        first_dir = backups_root / f"prune-{today}"
        second_dir = backups_root / f"prune-{today}-2"

        self.assertTrue(first_dir.exists())
        self.assertTrue(
            second_dir.exists(), "A second same-day run must get a uniquified folder"
        )
        first_pruned = (first_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn(filename, first_pruned)
        self.assertNotIn(
            filename2, first_pruned,
            "The first run's log must be untouched by the second run",
        )
        second_pruned = (second_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn(filename2, second_pruned)


class TestInstalledDivergenceLint(_UpgradeArtifactsFixtureBase):
    """lint_installed_divergence() + the _run_doctor() Stage 9 call site.

    Generalizes TestDoctorStaleSweep's pattern from DESCOPED_RULES to the
    still-installed set (INSTALLED_RULES). Reuses
    _UpgradeArtifactsFixtureBase because its temp tree layout and its
    INSTALLED_RULES monkeypatch scope already match what
    lint_installed_divergence() walks — no new fixture needed.
    """

    def test_installed_rule_stale_subset_recommends_upgrade(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)
        before = _snapshot_tree(self.project_root)

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1, "the diverged installed rule must produce a finding")
        self.assertEqual(matches[0]["kind"], "rule")
        self.assertEqual(matches[0]["classification"], "SUBSET")
        self.assertIn("/planwise upgrade", matches[0]["recommendation"])
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "The lint is read-only — it must never mutate the installed tree",
        )

    def test_installed_rule_has_unique_still_recommends_decide_callout(self):
        # A rule keeps the pre-existing decide-callout advice for a
        # HAS_UNIQUE verdict.
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["kind"], "rule")
        self.assertEqual(matches[0]["classification"], "HAS_UNIQUE")
        self.assertIn(
            "Choosing a Home for a Rule Customization", matches[0]["recommendation"]
        )

    def test_subset_with_notes_does_not_promise_unconditional_auto_adopt(self):
        # Regression (R1 finding 6): a notes-flagged SUBSET must not get the
        # unconditional "(auto-adopts shipped)" wording — the writer's own
        # auto-adopt gate (`is_subset(verdict) and not verdict.notes`) does
        # not fire on a non-empty notes field.
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)
        notes_text = "installed-only tokens tolerated as sub-noise-floor fragments"

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("SUBSET", "exact", notes=notes_text),
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["classification"], "SUBSET")
        self.assertNotIn(
            "(auto-adopts shipped)", matches[0]["recommendation"],
            "a notes-flagged subset must not promise unconditional auto-adoption",
        )
        self.assertIn("customization_handoff", matches[0]["recommendation"])

    def test_non_utf8_installed_file_reported_unverifiable_not_crashed(self):
        # Regression (R1 findings 2 + 4): a non-UTF-8 installed file must
        # never crash the always-exit-0 doctor path — it must be reported as
        # an explicit unverifiable row instead of raising UnicodeDecodeError.
        self.write_shipped_rule("# Rule\n\nShipped body.\n")
        installed = self.rules_dst_dir / self.RULE_FILENAME
        # Write bytes that are invalid UTF-8 (a lone 0xFF byte).
        installed.write_bytes(b"---\ndescription: fixture rule\npaths: "
                               + self.RULE_PATHS_TEMPLATE.encode("utf-8")
                               + b"\n---\n# Rule\n\xff\xfe garbled\n")

        findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1, "an unreadable installed file must still be reported")
        self.assertEqual(matches[0]["classification"], "UNVERIFIABLE")
        self.assertIn("unreadable", matches[0]["recommendation"])

    def test_non_utf8_installed_file_doctor_path_exits_cleanly(self):
        import contextlib
        import io

        self.write_shipped_rule("# Rule\n\nShipped body.\n")
        (self.rules_dst_dir / self.RULE_FILENAME).write_bytes(
            b"---\ndescription: fixture rule\npaths: "
            + self.RULE_PATHS_TEMPLATE.encode("utf-8")
            + b"\n---\n# Rule\n\xff\xfe garbled\n"
        )
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_doctor(self.cfg)

        self.assertEqual(exit_code, 0, "bare --doctor must always exit 0, even over an unreadable file")
        self.assertIn("UNVERIFIABLE", buf.getvalue())

    def test_bom_identical_installed_file_not_reported(self):
        # Regression (R1 finding 3): both sides must be read with utf-8-sig
        # so a BOM'd-but-untouched installed file is not falsely flagged
        # HAS_UNIQUE (a BOM defeats normalize_rule_for_diff's frontmatter
        # detection under plain utf-8).
        body = "# Rule\n\nUntouched body.\n"
        self.write_shipped_rule(body)
        installed = self.write_installed_rule(body, self.RULE_PATHS_TEMPLATE)
        installed.write_bytes(b"\xef\xbb\xbf" + installed.read_bytes())  # prepend UTF-8 BOM

        with mock.patch.object(
            ip, "_classify_diverged",
            side_effect=AssertionError("a BOM-only difference must never reach the primitive"),
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(matches, [], "a BOM'd-but-untouched file must NOT be reported")

    def test_missing_shipped_reference_reported_unverifiable_no_all_clear(self):
        # Regression (R1 finding 4): a missing shipped reference (broken/
        # partial install) must surface an explicit unverifiable row rather
        # than a silent skip that would let the caller's all-clear line print.
        installed = self.write_installed_rule(
            "# Rule\n\nSome body.\n", self.RULE_PATHS_TEMPLATE
        )
        # Deliberately do NOT call write_shipped_rule() — no shipped reference.

        findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1, "a missing shipped reference must produce a finding")
        self.assertEqual(matches[0]["classification"], "UNVERIFIABLE")
        self.assertIn("shipped reference unavailable", matches[0]["recommendation"])
        self.assertNotEqual(findings, [], "must never silently reduce to the all-clear state")

    def test_degraded_not_analyzed_verdict_reported_explicitly(self):
        # Regression (R1 finding 5): the degraded not-analyzed stand-in
        # (structural_compare unavailable) must produce an explicit
        # NOT_ANALYZED row, never a confident HAS_UNIQUE recommendation.
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)

        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["classification"], "NOT_ANALYZED")
        self.assertNotEqual(
            matches[0]["classification"], "HAS_UNIQUE",
            "an un-analyzed file must never be reported as a confident HAS_UNIQUE verdict",
        )
        self.assertIn("not analyzed", matches[0]["recommendation"].lower())

    def test_normalized_identical_copy_skipped_fast_path(self):
        body = "# Rule\n\nUntouched body.\n"
        self.write_shipped_rule(body)
        self.write_installed_rule(body, self.RULE_PATHS_TEMPLATE)

        with mock.patch.object(
            ip, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        self.assertEqual(findings, [], "A normalized-identical copy must not be reported")

    def test_stage9_wired_into_doctor_path(self):
        import contextlib
        import io

        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)

        # Pin the version-state gate to "ok" (pinned == installed) so
        # _run_doctor() proceeds past the preflight into Stage 8 / Stage 9.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )
        before = _snapshot_tree(self.project_root)

        buf = io.StringIO()
        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            with contextlib.redirect_stdout(buf):
                exit_code = ip._run_doctor(self.cfg)

        stdout = buf.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "installed rule divergence lint", stdout,
            "Stage 9 must be invoked by _run_doctor(), not merely defined",
        )
        self.assertTrue(
            any(str(installed) in line and "SUBSET" in line for line in stdout.splitlines()),
            "The doctor path must print a SUBSET row for the diverged installed rule",
        )
        self.assertIn("recommend /planwise upgrade", stdout)
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "The doctor path (bare --doctor) must never write or delete",
        )


class TestVerdictOverrideShapeAndFreshness(unittest.TestCase):
    """_load_verdict_override(): malformed-entry containment (never crash) and
    the installed_sha256 freshness binding (missing/stale hash => ignored)."""

    INSTALLED_RAW = "---\ndescription: x\n---\n# Rule\n\nInstalled body.\n"

    def _sha(self, text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _valid_entry(self, **overrides) -> dict:
        entry = {
            "classification": "SUBSET",
            "confidence": "contained",
            "unique_blocks": [],
            "shared_blocks": 3,
            "total_installed_blocks": 3,
            "installed_only_chars": 0,
            "unique_sample_tokens": [],
            "source": "agent",
            "notes": "",
            "installed_sha256": self._sha(self.INSTALLED_RAW),
        }
        entry.update(overrides)
        return entry

    def test_non_dict_entries_degrade_to_none_without_crashing(self):
        for bad in ("a plain string", ["a", "list"], 42, None, 3.14, True):
            with self.subTest(entry=bad):
                self.assertIsNone(
                    ip._load_verdict_override({"f.md": bad}, "f.md", self.INSTALLED_RAW),
                    f"a non-dict verdicts.json entry ({bad!r}) must degrade to "
                    "None (inline primitive), never crash",
                )

    def test_missing_installed_sha256_is_ignored(self):
        entry = self._valid_entry()
        del entry["installed_sha256"]
        self.assertIsNone(
            ip._load_verdict_override({"f.md": entry}, "f.md", self.INSTALLED_RAW),
            "an entry with no installed_sha256 must be ignored (no freshness proof)",
        )

    def test_stale_installed_sha256_is_ignored(self):
        entry = self._valid_entry(installed_sha256=self._sha("different bytes now"))
        self.assertIsNone(
            ip._load_verdict_override({"f.md": entry}, "f.md", self.INSTALLED_RAW),
            "a hash computed against different bytes must invalidate the override",
        )

    @unittest.skipUnless(ip.HAS_STRUCTURAL_COMPARE, "requires structural_compare")
    def test_matching_installed_sha256_returns_agent_verdict(self):
        verdict = ip._load_verdict_override(
            {"f.md": self._valid_entry()}, "f.md", self.INSTALLED_RAW
        )
        self.assertIsNotNone(verdict, "a fresh, well-formed entry must deserialize")
        self.assertEqual(verdict.classification, "SUBSET")
        self.assertEqual(verdict.source, "agent")

    def test_malformed_dict_entry_degrades_to_none(self):
        # dict-shaped but missing the required classification/confidence keys.
        entry = {"installed_sha256": self._sha(self.INSTALLED_RAW), "notes": ""}
        self.assertIsNone(
            ip._load_verdict_override({"f.md": entry}, "f.md", self.INSTALLED_RAW)
        )


class TestCustomizationHandoffGating(_UpgradeArtifactsFixtureBase):
    """upgrade.customization_handoff gates the automated transfer-then-adopt
    path: report (also the absent-key default) and report+issue are
    conservative (preserve + sidecar, no transfer, no adoption);
    report+relocate enables the automated flow (pinned by the transfer tests
    in TestUpgradeArtifactsDisposition)."""

    def _run_has_unique_rule(self):
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()
        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            result = self.run_upgrade()
        return installed, before, result

    def test_absent_config_defaults_to_conservative_report(self):
        installed, before, result = self._run_has_unique_rule()
        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = result

        self.assertEqual(installed.read_bytes(), before,
                         "report mode must preserve the installed file byte-for-byte")
        self.assertEqual(transferred, [], "report mode must NOT transfer")
        self.assertNotIn(str(installed), refreshed, "report mode must NOT adopt shipped")
        self.assertTrue(conflicts, "report mode must surface the file as a conflict")
        dst_path, sidecar_path = conflicts[0]
        self.assertEqual(dst_path, str(installed))
        self.assertTrue(Path(sidecar_path).exists(), "a .new sidecar must be written")
        self.assertFalse(
            self.transfer_dir().exists(),
            "report mode must not create the upgrade-transfers dir",
        )

    def test_explicit_report_is_conservative(self):
        self.write_upgrade_config(customization_handoff="report")
        installed, before, result = self._run_has_unique_rule()
        _, _, conflicts, _, _, transferred = result
        self.assertEqual(installed.read_bytes(), before)
        self.assertEqual(transferred, [])
        self.assertTrue(conflicts)

    def test_report_issue_is_conservative_for_disposition(self):
        self.write_upgrade_config(customization_handoff="report+issue")
        installed, before, result = self._run_has_unique_rule()
        _, _, conflicts, _, _, transferred = result
        self.assertEqual(installed.read_bytes(), before,
                         "report+issue must dispose like report (issue routing is "
                         "handler-side, never a writer-side adoption license)")
        self.assertEqual(transferred, [])
        self.assertTrue(conflicts)

class TestDestructiveWriteOrderingAndBackupGates(_UpgradeArtifactsFixtureBase):
    """Failed backup => no destructive write; failed adoption write (after a
    verified transfer) => conflict + NO false DISPOSITIONS row; transfer
    collisions uniquify instead of clobbering."""

    def test_backup_failure_blocks_rule_subset_adoption(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ), mock.patch.object(ip, "_write_backup_preimage", return_value=False):
            refreshed, _, conflicts, _, refreshed_subsets, _ = self.run_upgrade()

        self.assertEqual(installed.read_bytes(), before,
                         "failed backup must block the adoption write")
        self.assertNotIn(str(installed), refreshed)
        self.assertEqual(refreshed_subsets, [])
        self.assertTrue(conflicts, "the blocked adoption must surface as a conflict")

    def test_backup_failure_blocks_transfer_then_adopt(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(ip, "_write_backup_preimage", return_value=False):
            refreshed, _, conflicts, _, _, transferred = self.run_upgrade()

        self.assertEqual(installed.read_bytes(), before,
                         "even with a verified transfer, a failed backup blocks adoption")
        self.assertEqual(transferred, [])
        self.assertTrue(conflicts)

    def test_adoption_write_failure_is_conflict_with_no_false_log_row(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()

        original_write_text = Path.write_text

        def _raising_write_text(self_path, *args, **kwargs):
            if self_path == installed:
                raise OSError("mock: adoption write failed")
            return original_write_text(self_path, *args, **kwargs)

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(Path, "write_text", _raising_write_text):
            refreshed, _, conflicts, _, _, transferred = self.run_upgrade()

        self.assertEqual(installed.read_bytes(), before,
                         "the failed adoption must leave the installed file untouched")
        self.assertEqual(transferred, [],
                         "a failed adoption is NOT reported as transferred")
        self.assertNotIn(str(installed), refreshed)
        self.assertTrue(conflicts, "the failed adoption must surface as a conflict")

        # The transfer file WAS written (before the failure) — the conflict
        # is recoverable from it; and no false "adopted" DISPOSITIONS row.
        transfer_files = (
            list(self.transfer_dir().iterdir()) if self.transfer_dir().exists() else []
        )
        self.assertTrue(transfer_files, "the pre-adoption transfer file must survive")
        dispositions = (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / "1.0.0-to-1.1.0" / "DISPOSITIONS.md"
        )
        if dispositions.exists():
            self.assertNotIn(
                "adopted shipped (customization transferred)",
                dispositions.read_text(encoding="utf-8"),
                "a failed adoption write must not append a false adoption row",
            )

    def test_transfer_collision_uniquifies_never_clobbers(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        self.write_installed_rule(installed_body, ".claude/agents/**")

        tdir = self.transfer_dir()
        tdir.mkdir(parents=True, exist_ok=True)
        stem = Path(self.RULE_FILENAME).stem
        suffix = Path(self.RULE_FILENAME).suffix
        first = tdir / self.RULE_FILENAME
        second = tdir / f"{stem}-1.0.0-to-1.1.0{suffix}"
        first.write_text("pre-existing transfer ONE", encoding="utf-8")
        second.write_text("pre-existing transfer TWO", encoding="utf-8")

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            _, _, conflicts, _, _, transferred = self.run_upgrade()

        self.assertEqual(len(transferred), 1)
        new_transfer = Path(transferred[0][1])
        self.assertEqual(
            new_transfer.name, f"{stem}-1.0.0-to-1.1.0-2{suffix}",
            "the collision loop must uniquify with a numeric suffix",
        )
        self.assertEqual(first.read_text(encoding="utf-8"), "pre-existing transfer ONE",
                         "a pre-existing transfer file must never be clobbered")
        self.assertEqual(second.read_text(encoding="utf-8"), "pre-existing transfer TWO")
        self.assertIn("User-added block.", new_transfer.read_text(encoding="utf-8"))
        self.assertEqual(conflicts, [])


class TestNotAnalyzedMarker(unittest.TestCase):
    """The degraded stand-in is detected by its explicit source marker only —
    a genuine agent verdict of the same SHAPE must never be captured."""

    def test_degraded_standin_carries_explicit_marker(self):
        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            verdict = ip._classify_diverged("installed body", "shipped body")
        self.assertEqual(verdict.source, ip._DEGRADED_VERDICT_SOURCE)
        self.assertTrue(ip._verdict_not_analyzed(verdict))

    def test_genuine_agent_has_unique_with_notes_is_not_captured(self):
        genuine = types.SimpleNamespace(
            classification="HAS_UNIQUE", confidence="unique",
            unique_blocks=[], notes="one tolerated fragment: 'local exemption'",
            source="agent",
        )
        self.assertFalse(
            ip._verdict_not_analyzed(genuine),
            "a genuine agent verdict (HAS_UNIQUE, no unique_blocks, non-empty "
            "notes) must NOT be shape-matched as not-analyzed",
        )

    def test_inline_primitive_verdict_is_not_captured(self):
        inline = types.SimpleNamespace(
            classification="HAS_UNIQUE", confidence="unique",
            unique_blocks=[], notes="tolerated fragments", source="inline",
        )
        self.assertFalse(ip._verdict_not_analyzed(inline))


class TestVerdictCacheConsumption(_UpgradeArtifactsFixtureBase):
    """A successful --upgrade run retires verdicts.json (renamed to
    verdicts.json.consumed) so a stale cached verdict can never fire on a
    later pair or re-run."""

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML (--upgrade hard-requires it)")
    def test_cache_consumed_after_successful_run(self):
        import contextlib
        import io

        # Minimal upgradeable fixture: pinned 1.0.0, target 1.1.0, identical
        # rule + agent so the artifact refresh has nothing to dispose.
        self.cfg.plugin_version = "1.1.0"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            'plugin_version: "1.0.0"\n', encoding="utf-8"
        )
        real_template = Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        shutil.copy(str(real_template), str(self.plugin_root / "config.yaml.template"))

        body = "# Rule\n\nIdentical body.\n"
        self.write_shipped_rule(body, ".claude/agents/**")
        self.write_installed_rule(body, ".claude/agents/**")

        verdicts_path = self.conflict_dir() / "verdicts.json"
        verdicts_path.parent.mkdir(parents=True, exist_ok=True)
        verdicts_path.write_text("{}", encoding="utf-8")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_upgrade(self.cfg)

        self.assertEqual(exit_code, 0)
        self.assertFalse(
            verdicts_path.exists(),
            "a successful --upgrade must retire the consumed verdicts.json",
        )
        consumed = verdicts_path.with_name("verdicts.json.consumed")
        self.assertTrue(
            consumed.exists(),
            "the cache is renamed to .consumed (inspectable, never re-fired)",
        )


class TestMotivatingSixRuleRegression(_MigrationFixtureBase):
    """Reproduce the live incident that motivated the subset-vs-unique work.

    Six de-scoped rules were installed as older/smaller copies of references
    that had since grown. The exact-match migration preserved ALL SIX as
    "body-customized," leaving the always-on over-scope the de-scope was meant
    to remove. Under the structural verdict, the five copies that carry no
    installed-only content must auto-remove (over-scope cleared), and the one
    that DOES carry installed-only content must be surfaced-and-preserved for
    re-home -- never silently removed, never silently mislabeled "customized"
    and left in place unflagged. The per-branch tests above pin each disposition
    in isolation; this pins the aggregate multi-rule outcome the incident was.
    """

    # The exact filenames from the incident (all present in DESCOPED_RULES).
    _STALE_SUBSETS = (
        "agent-orchestration.md",
        "callout-conventions.md",
        "session-context-budget.md",
        "session-execution-protocol.md",
        "session-plan-requirements.md",
    )
    _CUSTOMIZED = "session-planning-protocol.md"
    _MARKER = "INSTALLEDONLYSTALEPROSE"

    def _to_version(self) -> str:
        return str(ip.RESCOPE_MIGRATION_VERSION)

    def _classify(self, installed_norm, shipped_norm, override=None):
        # The one copy carrying installed-only content classifies HAS_UNIQUE;
        # the five clean older copies classify as high-confidence stale subsets.
        if self._MARKER in installed_norm:
            return _verdict("HAS_UNIQUE", "unique",
                            unique_blocks=["# Stale generic block"])
        return _verdict("SUBSET", "contained")

    def test_six_rule_case_clears_overscope_and_flags_customized(self):
        # Five older/smaller copies: installed body is a strict subset of the
        # grown shipped reference (no installed-only content).
        for filename in self._STALE_SUBSETS:
            shipped = (
                f"# {filename}\n\nShared line one.\nShared line two.\n"
                "Line the reference grew later.\n"
            )
            installed = f"# {filename}\n\nShared line one.\nShared line two.\n"
            self.write_shipped(filename, shipped)
            self.write_installed(
                filename, installed, self.old_default_for(filename))

        # The sixth carries stale generic installed-only prose -- not a project
        # edit, but the machine cannot prove that, so it must be preserved.
        self.write_shipped(
            self._CUSTOMIZED,
            f"# {self._CUSTOMIZED}\n\nShared line one.\n"
            "Line the reference grew later.\n")
        self.write_installed(
            self._CUSTOMIZED,
            f"# {self._CUSTOMIZED}\n\nShared line one.\n"
            f"{self._MARKER} carried over from an old plugin era.\n",
            self.old_default_for(self._CUSTOMIZED))

        with mock.patch.object(ip, "_classify_diverged", side_effect=self._classify):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        removed = _report_section(report, "removed", "deleted")
        preserved = _report_section(report, "preserved", "kept")
        skipped = _report_section(report, "skipped")

        # The five clean stale subsets are all removed -> the always-on
        # over-scope the de-scope targeted is physically cleared.
        for filename in self._STALE_SUBSETS:
            self.assertFalse(
                (self.rules_dir / filename).exists(),
                f"{filename}: a clean stale subset of the grown reference must be "
                "removed, not preserved as 'customized' (the original defect)",
            )
            self.assertTrue(
                any(filename in e and "stale subset" in e for e in removed),
                f"{filename} must be reported removed as a stale subset",
            )
            self.assertFalse(
                any(filename in e for e in preserved),
                f"{filename} must not be reported preserved",
            )

        # The sixth is surfaced-and-preserved for re-home: kept on disk AND
        # flagged with a customization notice (not silently removed, not silent).
        self.assertTrue(
            (self.rules_dir / self._CUSTOMIZED).exists(),
            "the copy carrying installed-only content must be preserved",
        )
        self.assertTrue(
            any(self._CUSTOMIZED in e and "customized block" in e for e in preserved),
            "the preserved copy must be surfaced with a re-home notice",
        )
        self.assertFalse(
            any(self._CUSTOMIZED in e for e in removed),
            "a customization-bearing copy must never be removed",
        )

        # Aggregate: every one of the six was dispositioned (none skipped), and
        # the over-scope is cleared down to exactly the one file needing review.
        for filename in (*self._STALE_SUBSETS, self._CUSTOMIZED):
            self.assertFalse(
                any(filename in e for e in skipped),
                f"{filename} must be dispositioned, not skipped",
            )
        surviving = [
            f for f in (*self._STALE_SUBSETS, self._CUSTOMIZED)
            if (self.rules_dir / f).exists()
        ]
        self.assertEqual(
            surviving, [self._CUSTOMIZED],
            "over-scope cleared: only the customization-bearing copy remains",
        )
        self.assertEqual(
            len([e for e in removed
                 if any(f in e for f in self._STALE_SUBSETS)]),
            5,
            "all five stale subsets reported removed",
        )


class _AgentMirrorFixtureBase(unittest.TestCase):
    """Builds a temporary project tree with an installed .claude/agents/ dir
    and a shipped plugin agents/ dir, for exercising
    sweep_orphaned_agent_mirrors() and the folded-in agent half of
    _run_prune_stale().

    Parallels _MigrationFixtureBase (rules), but agents carry no `paths:`
    frontmatter key, so the preserve-vs-remove comparison is a whole-file
    identity norm -- no paths-template plumbing needed here.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_agentmirror_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"

        self.agents_dir = self.project_root / ".claude" / "agents"
        self.agents_src_dir = self.plugin_root / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.agents_src_dir.mkdir(parents=True, exist_ok=True)

        self.cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
        )

    # -- helpers ------------------------------------------------------------

    def write_shipped_agent(self, filename: str, body: str) -> Path:
        dst = self.agents_src_dir / filename
        dst.write_text(body, encoding="utf-8")
        return dst

    def write_installed_agent(self, filename: str, body: str) -> Path:
        dst = self.agents_dir / filename
        dst.write_text(body, encoding="utf-8")
        return dst

    def pin_version_gate_ok(self) -> None:
        """Pin the version-state gate to 'ok', mirroring
        TestDoctorStaleSweep's inline pattern, so the prune writer proceeds
        past the preflight into the sweep/removal logic."""
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )


class TestOrphanedAgentMirrorSweep(_AgentMirrorFixtureBase):
    """sweep_orphaned_agent_mirrors() -- the read-only orphaned-agent-mirror
    sweep. Parallels TestDoctorStaleSweep's sweep half, swapped onto
    FORMERLY_MIRRORED_AGENTS / .claude/agents/ instead of DESCOPED_RULES /
    .claude/rules/planwise/. Each test below pins one preserve-vs-remove
    verdict branch -- the disposition is fixed by the rule, not inferred.

    NOT YET IMPLEMENTED: sweep_orphaned_agent_mirrors() does not exist yet,
    so every test in this class is expected to fail (AttributeError) until
    it is written -- that failure is the tests-first proof.
    """

    def test_byte_identical_mirror_is_removable_fast_path(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        before = _snapshot_tree(self.project_root)

        with mock.patch.object(
            ip, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "REMOVABLE")
        self.assertTrue(installed.exists(), "the sweep is read-only -- never deletes")
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "the bare sweep must leave the installed tree byte-for-byte unchanged",
        )

    def test_stale_subset_diverged_body_is_removable(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[1]
        shipped_body = "---\ndescription: fixture agent\n---\nBody line one.\nGrown extra line.\n"
        installed_body = "---\ndescription: fixture agent\n---\nBody line one.\n"
        self.write_shipped_agent(filename, shipped_body)
        installed = self.write_installed_agent(filename, installed_body)

        with mock.patch.object(
            ip, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "REMOVABLE")
        self.assertTrue(installed.exists(), "the sweep is read-only -- never deletes")

    def test_has_unique_body_is_preserved_with_unique_blocks(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[2]
        shipped_body = "---\ndescription: fixture agent\n---\nShipped body.\n"
        installed_body = (
            "---\ndescription: fixture agent\n---\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped_agent(filename, shipped_body)
        installed = self.write_installed_agent(filename, installed_body)
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertEqual(matches[0]["unique_blocks"], ["# Extra"])
        self.assertEqual(
            installed.read_bytes(), before, "PRESERVE must never mutate the file"
        )

    def test_has_unique_frontmatter_only_is_preserved_not_spliced(self):
        """A customized model:/tools:/maxTurns: pin, body identical -- the key
        conservative guard: agents get NO frontmatter-splice guard (that
        machinery was deleted along with the rule-precedent splice helper).
        PRESERVE, whole file, byte-for-byte, no rewrite."""
        filename = ip.FORMERLY_MIRRORED_AGENTS[3]
        body = "Shared agent body.\nSecond line.\n"
        shipped_text = f"---\ndescription: fixture agent\nmodel: sonnet\n---\n{body}"
        installed_text = f"---\ndescription: fixture agent\nmodel: opus\nmaxTurns: 40\n---\n{body}"
        self.write_shipped_agent(filename, shipped_text)
        installed = self.write_installed_agent(filename, installed_text)
        before = installed.read_bytes()

        with mock.patch.object(
            ip, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["model: opus"]),
        ):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertEqual(
            installed.read_bytes(), before,
            "a frontmatter-only divergence must never be rewritten or spliced",
        )
        self.assertFalse(
            hasattr(ip, "_apply_agent_frontmatter_guard"),
            "the deleted rule-precedent splice guard must not be reintroduced for agents",
        )

    def test_notes_flagged_subset_is_preserved_not_removable(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[4]
        shipped_body = "---\ndescription: fixture agent\n---\nBody line one.\nGrown extra line.\n"
        installed_body = "---\ndescription: fixture agent\n---\nBody line one.\n"
        self.write_shipped_agent(filename, shipped_body)
        installed = self.write_installed_agent(filename, installed_body)

        notes_text = "tolerated a sub-noise-floor installed-only fragment"
        verdict = _verdict("SUBSET", "contained", notes=notes_text)
        with mock.patch.object(ip, "_classify_diverged", return_value=verdict):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["verdict"], "PRESERVE",
            "a subset with non-empty notes must NOT be REMOVABLE, even at "
            "exact/contained confidence",
        )
        self.assertTrue(installed.exists())

    def test_shipped_reference_missing_is_preserved(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        installed = self.write_installed_agent(
            filename, "---\ndescription: fixture agent\n---\nNo shipped reference.\n"
        )
        # No write_shipped_agent() call -- the shipped plugin copy is absent.

        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertTrue(installed.exists())

    def test_unreadable_installed_file_is_preserved_no_crash(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[1]
        self.write_shipped_agent(filename, "---\ndescription: fixture agent\n---\nBody.\n")
        installed = self.agents_dir / filename
        # An invalid UTF-8 byte sequence -- read_text(encoding="utf-8") must
        # raise UnicodeDecodeError, which the sweep must catch and preserve
        # rather than crash on.
        installed.write_bytes(b"---\ndescription: fixture agent\n---\n\xff\xfe not utf-8\n")

        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertTrue(installed.exists())

    def test_not_installed_file_is_silently_skipped(self):
        # Nothing written to .claude/agents/ for any FORMERLY_MIRRORED_AGENTS
        # entry -- none of them is a broken install, so no finding at all.
        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)
        self.assertEqual(findings, [])

    def test_degraded_structural_compare_unavailable_is_preserved(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[2]
        shipped_body = "---\ndescription: fixture agent\n---\nBody line one.\nGrown extra line.\n"
        installed_body = "---\ndescription: fixture agent\n---\nBody line one.\n"
        self.write_shipped_agent(filename, shipped_body)
        installed = self.write_installed_agent(filename, installed_body)

        degraded = types.SimpleNamespace(
            classification="HAS_UNIQUE", confidence="unique", unique_blocks=[],
            shared_blocks=0, total_installed_blocks=0, installed_only_chars=0,
            unique_sample_tokens=[], source=ip._DEGRADED_VERDICT_SOURCE,
            notes="structural_compare unavailable; degraded to preserve",
        )
        with mock.patch.object(ip, "_classify_diverged", return_value=degraded):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["verdict"], "PRESERVE",
            "degraded / not-analyzed must never yield a confident REMOVABLE",
        )
        self.assertTrue(installed.exists())


class TestOrphanedAgentMirrorPrune(_AgentMirrorFixtureBase):
    """The folded-in agent half of _run_prune_stale(): one opt-in writer
    that sweeps both stale de-scoped rules and orphaned agent mirrors in
    the same pass, reusing the same per-run backup folder, PRUNED.md log,
    and version gate. Parallels TestDoctorStaleSweep's writer half.

    NOT YET IMPLEMENTED: _run_prune_stale() does not yet call
    sweep_orphaned_agent_mirrors() at all, so every REMOVABLE-agent
    scenario below currently leaves the fixture file untouched -- that
    failure to unlink/backup/log is the tests-first proof.
    """

    def test_version_gate_refusal_leaves_agent_tree_untouched(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        # No config.yaml written -- the version-state gate is "uninitialized".
        before = _snapshot_tree(self.project_root)

        # Prove the fixture is a genuine REMOVABLE candidate first (this call
        # alone forces the tests-first failure, since sweep_orphaned_agent_
        # mirrors() does not exist yet).
        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)
        self.assertEqual(
            [f["verdict"] for f in findings if f["filename"] == filename], ["REMOVABLE"]
        )

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(installed.exists(), "a gate refusal must never delete anything")
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "a gate refusal must leave the installed tree byte-for-byte unchanged",
        )

    def test_prune_writes_pre_image_backup_before_unlinking_agent(self):
        import datetime

        filename = ip.FORMERLY_MIRRORED_AGENTS[1]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        original_content = installed.read_bytes()
        self.pin_version_gate_ok()

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertFalse(
            installed.exists(), "a REMOVABLE orphaned agent mirror must be unlinked"
        )

        today = datetime.date.today().isoformat()
        out_dir = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}"
        )
        backup = out_dir / filename
        self.assertTrue(
            backup.exists(), "a pre-image backup must be written before unlink"
        )
        self.assertEqual(backup.read_bytes(), original_content)

        pruned_text = (out_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn("## Removed", pruned_text)
        self.assertIn(filename, pruned_text)

    def test_prune_unlink_failure_marks_remove_failed_no_orphan_backup(self):
        import datetime

        filename = ip.FORMERLY_MIRRORED_AGENTS[2]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        self.pin_version_gate_ok()

        original_unlink = Path.unlink

        def _raising_unlink(self_path, *args, **kwargs):
            if self_path == installed:
                raise OSError("mock: cannot remove")
            return original_unlink(self_path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", _raising_unlink):
            result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(installed.exists(), "a failed unlink must leave the file in place")

        today = datetime.date.today().isoformat()
        out_dir = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}"
        )
        pruned_text = (out_dir / "PRUNED.md").read_text(encoding="utf-8")
        preserved_section = pruned_text.split("## Preserved", 1)[1]
        self.assertIn(
            "[REMOVE_FAILED] — could not remove", preserved_section,
            "a failed unlink must be reported as REMOVE_FAILED, not REMOVABLE",
        )
        self.assertIn(filename, preserved_section)
        self.assertFalse(
            (out_dir / filename).exists(),
            "the orphan pre-image backup must be cleaned up after a failed unlink",
        )

    def test_per_run_log_never_overwritten_same_day_gets_suffix(self):
        import datetime

        self.pin_version_gate_ok()

        filename = ip.FORMERLY_MIRRORED_AGENTS[3]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        self.write_installed_agent(filename, body)

        result1 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result1, 0)

        filename2 = ip.FORMERLY_MIRRORED_AGENTS[4]
        body2 = "---\ndescription: fixture agent\n---\nA second untouched agent body.\n"
        self.write_shipped_agent(filename2, body2)
        self.write_installed_agent(filename2, body2)

        result2 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result2, 0)

        today = datetime.date.today().isoformat()
        backups_root = self.project_root / self.cfg.planwise_root / "upgrade-backups"
        first_dir = backups_root / f"prune-{today}"
        second_dir = backups_root / f"prune-{today}-2"

        self.assertTrue(first_dir.exists())
        self.assertTrue(
            second_dir.exists(), "a second same-day run must get a uniquified folder"
        )
        first_pruned = (first_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn(filename, first_pruned)
        self.assertNotIn(
            filename2, first_pruned,
            "the first run's log must be untouched by the second run",
        )
        second_pruned = (second_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn(filename2, second_pruned)

    def test_idempotent_second_run_already_removed_no_findings(self):
        self.pin_version_gate_ok()

        filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)

        result1 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result1, 0)
        self.assertFalse(installed.exists())

        # Second sweep: the file is already gone, so it must produce no
        # finding at all -- not an error, not a re-report.
        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)
        self.assertEqual(
            [f for f in findings if f["filename"] == filename], [],
            "an already-removed mirror must produce no finding on re-sweep",
        )

        result2 = ip._run_prune_stale(self.cfg)
        self.assertEqual(
            result2, 0, "a second run over an already-clean tree must not error"
        )


class TestOrphanedAgentMirrorRegressionsAndSurface(_AgentMirrorFixtureBase):
    """Constant-independence, no-cross-talk, CLI surface, and
    reused-primitive regressions for the orphaned-agent-mirror sweep/prune.

    NOT YET IMPLEMENTED: every scenario below is expected to fail until
    sweep_orphaned_agent_mirrors() exists and _run_prune_stale() is
    extended to call it.
    """

    def test_sweep_references_only_formerly_mirrored_agents_constant(self):
        import inspect

        self.assertFalse(
            hasattr(ip, "INSTALLED_AGENTS"),
            "the deleted mirror-install constant must not be reintroduced",
        )
        source = inspect.getsource(ip.sweep_orphaned_agent_mirrors)
        self.assertNotIn(
            "INSTALLED_AGENTS", source,
            "the sweep must reference only FORMERLY_MIRRORED_AGENTS, never "
            "the removed INSTALLED_AGENTS -- guards the NameError class",
        )
        self.assertIn("FORMERLY_MIRRORED_AGENTS", source)

    def test_no_cross_talk_between_agent_writer_and_rule_tree(self):
        self.pin_version_gate_ok()

        # A REMOVABLE agent mirror ...
        agent_filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        agent_body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(agent_filename, agent_body)
        installed_agent = self.write_installed_agent(agent_filename, agent_body)

        # ... alongside an untouched .claude/rules/planwise/ tree that the
        # agent writer must never reach into.
        rules_dir = self.project_root / ".claude" / "rules" / "planwise"
        rules_dir.mkdir(parents=True, exist_ok=True)
        sentinel_rule = rules_dir / "sentinel-rule.md"
        sentinel_text = "---\ndescription: sentinel\n---\nUntouched.\n"
        sentinel_rule.write_text(sentinel_text, encoding="utf-8")

        # ... and an actively-shipped agent (NOT in the frozen orphan list)
        # that must never be touched even though it lives in the same
        # .claude/agents/ directory as the mirrors being pruned.
        active_agent = self.agents_dir / "general-purpose.md"
        active_text = "---\ndescription: active agent\n---\nLive.\n"
        active_agent.write_text(active_text, encoding="utf-8")

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertFalse(
            installed_agent.exists(), "the REMOVABLE agent mirror must be pruned"
        )
        self.assertTrue(
            sentinel_rule.exists(),
            "the agent writer must never touch .claude/rules/** -- no cross-talk",
        )
        self.assertEqual(sentinel_rule.read_text(encoding="utf-8"), sentinel_text)
        self.assertTrue(
            active_agent.exists(),
            "the writer must only ever touch files named in "
            "FORMERLY_MIRRORED_AGENTS, never an arbitrary installed agent",
        )
        self.assertEqual(active_agent.read_text(encoding="utf-8"), active_text)

    def test_bare_doctor_prints_readonly_orphan_finding_deletion_opt_in(self):
        import contextlib
        import io

        self.pin_version_gate_ok()

        filename = ip.FORMERLY_MIRRORED_AGENTS[1]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        before = _snapshot_tree(self.project_root)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_doctor(self.cfg)
        stdout = buf.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "orphaned agent mirror sweep", stdout,
            "bare doctor must print the read-only orphaned-agent-mirror finding",
        )
        self.assertTrue(
            any(filename in line and "REMOVABLE" in line for line in stdout.splitlines()),
            "the doctor path must print a REMOVABLE row for the orphaned mirror",
        )
        self.assertTrue(installed.exists(), "bare doctor must never delete -- read-only")
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "bare doctor must never write or delete",
        )

        # Deletion is opt-in, under --prune-stale, not the bare doctor path.
        result = ip._run_prune_stale(self.cfg)
        self.assertEqual(result, 0)
        self.assertFalse(
            installed.exists(),
            "the same finding must be actionable via the opt-in --prune-stale writer",
        )

    def test_writer_calls_reused_primitives_not_duplicated_logic(self):
        import inspect

        source = inspect.getsource(ip.sweep_orphaned_agent_mirrors)
        for primitive in (
            "_classify_diverged", "is_subset", "is_safe_to_remove",
            "_destructively_removable",
        ):
            self.assertIn(
                primitive, source,
                f"sweep_orphaned_agent_mirrors() must call the reused primitive "
                f"{primitive}() rather than duplicate comparison logic",
            )


if __name__ == "__main__":
    unittest.main()
