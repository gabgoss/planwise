"""Shared test helpers for the Token Saver engine test split.

`_engine()` is consumed by three sibling test modules that each exercise a
piece of the split — `test_token_saver.py` (the config surface, via the
facade), `test_context_calibration.py` (the calibration engine), and
`test_read_limits.py` (the Read-tool gating engine) — so it lives here rather
than being copy-pasted three times.
"""

import importlib
import sys


def _engine():
    """Import (or re-import) the not-yet-implemented token_saver engine module.

    Imported lazily so a missing module surfaces as a per-test error (TDD red)
    rather than aborting collection of the whole file at import time.
    """
    if "token_saver" in sys.modules:
        return importlib.reload(sys.modules["token_saver"])
    return importlib.import_module("token_saver")


# ---------------------------------------------------------------------------
# Cross-seam fixtures for the rule_descope_migration monolith's 5-way split.
#
# These symbols are consumed by more than one of the five seam test modules
# (test_rule_descope_migration.py plus the four siblings it was split into),
# so they live here rather than being duplicated. `_flatten_report` moved
# here alongside `_report_section` even though it is only directly called
# from the seam-1 (anchor) module, because `_report_section`'s own body
# calls it -- and a function's free-variable lookups resolve in the module
# where the function is DEFINED, not where it is imported. Leaving
# `_flatten_report` on the anchor while `_report_section` lives here would
# raise NameError the first time any non-anchor seam called `_report_section`.
# ---------------------------------------------------------------------------
import shutil  # noqa: E402
import tempfile  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))  # noqa: E402

import init_project as ip  # noqa: E402
import artifact_upgrade  # noqa: E402 -- patch-target home for _UpgradeArtifactsFixtureBase's INSTALLED_RULES override (upgrade_artifacts())
import doctor_sweeps  # noqa: E402 -- patch-target home for _UpgradeArtifactsFixtureBase's second, independent INSTALLED_RULES override (lint_installed_divergence())


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


# The four rules de-scoped WITHOUT a plans: template (contrast with
# EXPECTED_DESCOPED_PLANS, which stays in test_rule_descope_migration.py --
# the anchor re-exports its own EXPECTED_DESCOPED = EXPECTED_DESCOPED_PLANS |
# EXPECTED_DESCOPED_ALL by importing this set back). Lives here, not the
# anchor, because _MigrationFixtureBase.write_shipped() below references it
# directly and a moved method's free-variable lookups resolve in the module
# where the method is DEFINED, not where the class is imported.
EXPECTED_DESCOPED_ALL = {
    "agent-orchestration.md",
    "agent-orchestration-delegated.md",
    "callout-conventions.md",
    "markdown-conventions.md",
}


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
        # Patched in BOTH artifact_upgrade (upgrade_artifacts()) and doctor_sweeps
        # (lint_installed_divergence(), reused by TestInstalledDivergenceLint below)
        # -- each module holds its own independent INSTALLED_RULES binding.
        rules_patch = mock.patch.object(
            artifact_upgrade, "INSTALLED_RULES", [(self.RULE_FILENAME, self.RULE_PATHS_TEMPLATE)]
        )
        rules_patch.start()
        self.addCleanup(rules_patch.stop)

        rules_patch_doctor_sweeps = mock.patch.object(
            doctor_sweeps, "INSTALLED_RULES", [(self.RULE_FILENAME, self.RULE_PATHS_TEMPLATE)]
        )
        rules_patch_doctor_sweeps.start()
        self.addCleanup(rules_patch_doctor_sweeps.stop)

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


