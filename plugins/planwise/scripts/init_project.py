#!/usr/bin/env python3
"""Initialize planwise project structure.

Creates directories, copies seed files, generates config.yaml,
and installs reference files as path-scoped rules.

Usage:
    python init_project.py --name "MyProject" [options]

Options:
    --name          Project name (required)
    --root          Planwise root directory (default: planwise)
    --plans-dir     Plans subdirectory name (default: Plans)
    --backlog-dir   Backlog subdirectory name (default: Backlog)
    --lessons-dir   Lessons subdirectory name (default: LessonsLearned)
    --scope         Install scope: project, user, or local (default: project)
    --plan-tier     Claude plan tier: pro (200K) or max (1M). Default: pro.
"""

import argparse
import dataclasses
import datetime
import hashlib
import json
import os
import re
import sys
import types
from datetime import date
from enum import Enum
from pathlib import Path

try:
    from config_loader import get_upgrade_config
except ImportError:
    # Partial-install tolerance, mirroring the structural_compare guard below:
    # a half-synced scripts tree must not kill the whole CLI at import time.
    # Mirrors config_loader.get_upgrade_config()'s conservative defaults.
    def get_upgrade_config(config: dict) -> dict:   # noqa: D103
        return {
            "customization_handoff": "report",
            "github_issue": False,
            "descope_preserve_paths_edits": True,
        }
from constants import InstallScope

try:
    import structural_compare
    # is_safe_to_remove/is_subset gate the disposition sites below;
    # classify_blocks/StructuralVerdict are re-exported for downstream verdict consumers.
    from structural_compare import classify_blocks, is_safe_to_remove, is_subset, StructuralVerdict  # noqa: F401
    HAS_STRUCTURAL_COMPARE = True
except ImportError:
    # A missing/broken structural_compare must degrade (preserve-on-doubt via
    # _classify_diverged) rather than hard-crash the whole CLI at import time.
    structural_compare = None
    HAS_STRUCTURAL_COMPARE = False

    # Degraded predicates so the disposition call sites stay callable when the
    # primitive module is unavailable. Both read attributes off the verdict
    # object (duck-typed against the degraded HAS_UNIQUE stand-in).
    def is_subset(v):           # noqa: E306
        return getattr(v, "classification", "HAS_UNIQUE") == "SUBSET"

    def is_safe_to_remove(v):   # noqa: E306
        return is_subset(v) and getattr(v, "confidence", "unique") in {"exact", "contained"}


def _destructively_removable(v) -> bool:
    """True when a verdict clears every destructive-disposition gate.

    SUBSET at exact/contained confidence (is_safe_to_remove) AND no
    tolerated installed-only content — a non-empty verdict.notes means the
    matcher tolerated installed-only content it could not prove was noise.
    Shared by every site that deletes or overwrites an installed file based
    on a structural verdict, in both the real and degraded import modes.
    """
    return is_safe_to_remove(v) and not (getattr(v, "notes", "") or "")


try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


PLAN_TIER_WINDOWS = {
    "pro": 200000,
    "max": 1000000,
}

# Fallback categorization used when the user's config.yaml has no
# `categorization:` block. Mirrors the buckets baked into
# config.yaml.template; consumed by render_categorization_file() and by the
# `--migrate` flow when seeding the block on an existing config.
DEFAULT_CATEGORIZATION = {
    "buckets": [
        {
            "id": "A",
            "slug": "database",
            "name": "Database / SQL",
            "description": "Lessons that touch the live database, schema, or DDL semantics.",
        },
        {
            "id": "B",
            "slug": "code",
            "name": "Application Code",
            "description": "Lessons about language-level patterns, type-checking, lint, runtime behaviour.",
        },
        {
            "id": "C",
            "slug": "process",
            "name": "Planwise / Process",
            "description": "Lessons about planning, scaffolding, dispatch, signoff, review.",
            "sub_buckets": [],
        },
        {
            "id": "D",
            "slug": "tooling",
            "name": "Tooling / Ergonomics",
            "description": "Toolchain, shell, notebook, IDE, harness ergonomics.",
        },
    ],
    "decision_tree_order": ["A", "B", "C", "D"],
    "default_bucket": "D",
    "edge_cases_section": True,
}

# Top-level keys that `--migrate` will copy from config.yaml.template into an
# existing user config when absent. Existing keys are NEVER overwritten — the
# flow is purely additive. Order matches the on-disk layout of the template
# so merged output stays readable.
MIGRATABLE_TOP_LEVEL_KEYS = [
    "plugin_root",
    "plugin_version",   # paired with plugin_root: version pin set on init, bumped by upgrade
    "context",
    "categorization",
    "upgrade",          # HAS_UNIQUE handoff routing + de-scope paths-only-edit policy
]

# Sub-keys under `context:` that `--migrate` adds to an EXISTING context block.
# The top-level merge above skips `context` whenever the user's config already
# has it (every installed config does), so the six Token Saver sub-keys would
# never reach an existing install without this nested merge. Each tuple is
# (sub_key, default_value_literal) where the literal is rendered verbatim into
# the YAML line. Existing sub-keys are NEVER overwritten — purely additive.
MIGRATABLE_CONTEXT_SUBKEYS: list[tuple[str, str]] = [
    ("token_saver", "false"),
    ("token_saver_session_target", "150000"),
    ("token_saver_runner_overhead", "0"),
    ("token_saver_orchestrator_overhead", "0"),
    ("token_saver_context_breakdown", "{}"),
    ("token_saver_overhead_measured_on", '""'),
]

# Files copied from references/ into .claude/rules/planwise/ on init.
# Each tuple is (source_filename, paths_template). paths_template uses
# {plans_path} / {all_paths} placeholders resolved at install/upgrade time
# from cfg.planwise_root + cfg.plans_dir / cfg.backlog_dir / cfg.lessons_dir.
# The upgrade flow consults this list as the authoritative refresh allowlist.
#
# Only the four `.claude/**`-scoped authoring rules are installed as
# path-scoped rules. They guide agents/skills/rules authoring, trigger on
# `.claude/**` file activity, and stay small. The sixteen plan/backlog/lessons
# rules that used to be installed here are now handler-loaded on demand from
# references/ — see DESCOPED_RULES below and migrate_installed_rules().
INSTALLED_RULES: list[tuple[str, str]] = [
    ("agent-authoring.md", ".claude/agents/**"),
    ("skill-authoring.md", ".claude/skills/**"),
    ("rule-authoring.md", ".claude/rules/**"),
    ("artifact-self-containment.md", ".claude/rules/**, .claude/agents/**, .claude/skills/**, .claude/commands/**, CLAUDE.md"),
]

# Rules removed from the install set during the rule de-scope. Each tuple is
# (source_filename, old_paths_template) where old_paths_template is the
# {plans_path} / {all_paths} placeholder the rule carried BEFORE de-scoping.
# migrate_installed_rules() resolves each template back to the pre-migration
# default paths: value to recognise an untouched installed copy and remove it;
# the orchestrator now loads these rules on demand from references/ instead of
# injecting them as always-on path-scoped rules.
DESCOPED_RULES: list[tuple[str, str]] = [
    ("session-planning-protocol.md", "{plans_path}"),
    ("session-plan-requirements.md", "{plans_path}"),
    ("session-context-budget.md", "{plans_path}"),
    ("session-execution-protocol.md", "{plans_path}"),
    ("scaffolding-hygiene.md", "{plans_path}"),
    ("discovery-and-exit-criteria.md", "{plans_path}"),
    ("ei-fidelity.md", "{plans_path}"),
    ("schema-pin-requirement.md", "{plans_path}"),
    ("task-content-fidelity.md", "{plans_path}"),
    ("verification-gates.md", "{plans_path}"),
    ("verify-against-shipped-artifact.md", "{plans_path}"),
    ("verification-task-authoring.md", "{plans_path}"),
    ("agent-orchestration.md", "{all_paths}"),
    ("agent-orchestration-delegated.md", "{all_paths}"),
    ("callout-conventions.md", "{all_paths}"),
    ("markdown-conventions.md", "{all_paths}"),
]

# Version this de-scope migration ships in. migrate_installed_rules() only
# acts when from_version < RESCOPE_MIGRATION_VERSION <= to_version, so the
# removal runs exactly once on the upgrade that crosses this boundary. This is
# PINNED to the version the de-scope first shipped in and MUST NOT be bumped to
# track plugin.json. Once plugin.json moves past it, the one-shot migration is
# spent for those installs; `/planwise doctor`'s stale sweep (Stage 8 +
# --prune-stale) is then the only remaining reach.
RESCOPE_MIGRATION_VERSION = "1.0.3"

# Frozen filename list for the post-boundary orphaned-mirror sweep: the agent
# files formerly mirrored into .claude/agents/ on init. No live install list
# remains after the mirror drop; this frozen copy lets the sweep recognize an
# orphaned mirror without re-deriving the set.
FORMERLY_MIRRORED_AGENTS = [
    "fix-agent.md",
    "plan-reviewer.md",
    "structural-reviewer.md",
    "task-runner.md",
    "rule-comparator.md",
]


def _find_context_block(lines: list[str]) -> tuple[int, int, str] | None:
    """Locate the top-level `context:` block in a list of YAML lines.

    Returns (header_index, block_end_exclusive, subkey_indent) where:
      * header_index is the index of the `context:` line,
      * block_end_exclusive is the index of the first line AFTER the block
        (the next top-level key, or len(lines) at EOF),
      * subkey_indent is the leading whitespace string used for the block's
        sub-keys (taken from the first indented member, or "  " if none).

    Returns None when no top-level `context:` block exists.
    """
    header_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^context:\s*$", line):
            header_idx = i
            break
    if header_idx is None:
        return None

    subkey_indent = "  "
    found_indent = False
    end = len(lines)
    for j in range(header_idx + 1, len(lines)):
        line = lines[j]
        if line.strip() == "" or line.lstrip().startswith("#"):
            # Blank/comment lines belong to the block only if more content
            # follows at sub-key indent; tentatively include and keep scanning.
            continue
        indent_match = re.match(r"^(\s+)\S", line)
        if indent_match:
            if not found_indent:
                subkey_indent = indent_match.group(1)
                found_indent = True
            continue
        # A non-indented, non-blank, non-comment line ends the block.
        end = j
        break

    # Trim trailing blank/comment lines back out of the block so insertions
    # land directly after the last real sub-key.
    while end - 1 > header_idx:
        prev = lines[end - 1]
        if prev.strip() == "" or prev.lstrip().startswith("#"):
            end -= 1
        else:
            break

    return header_idx, end, subkey_indent


def _existing_context_subkeys(lines: list[str], start: int, end: int) -> set[str]:
    """Return the set of sub-key names already present in a context block."""
    keys: set[str] = set()
    for k in range(start, end):
        m = re.match(r"^\s+([a-zA-Z_]\w*):", lines[k])
        if m:
            keys.add(m.group(1))
    return keys


def _context_subkeys_delta(before: str, after: str) -> list[str]:
    """Return the context sub-keys present in `after` but not in `before`.

    Used for migrate reporting (which Token Saver sub-keys the nested merge
    added). Order follows MIGRATABLE_CONTEXT_SUBKEYS.
    """
    before_lines = before.split("\n")
    after_lines = after.split("\n")
    before_block = _find_context_block(before_lines)
    after_block = _find_context_block(after_lines)
    before_keys: set[str] = set()
    after_keys: set[str] = set()
    if before_block is not None:
        h, e, _ = before_block
        before_keys = _existing_context_subkeys(before_lines, h + 1, e)
    if after_block is not None:
        h, e, _ = after_block
        after_keys = _existing_context_subkeys(after_lines, h + 1, e)
    gained = after_keys - before_keys
    return [
        f"context.{k}" for k, _ in MIGRATABLE_CONTEXT_SUBKEYS if k in gained
    ]


def merge_context_subkeys(text: str, token_saver_value: str = "false") -> str:
    """Add any missing Token Saver sub-keys to an existing `context:` block.

    Targeted, comment-preserving, in-place text edit — NOT a yaml round-trip.
    Existing sub-keys are left byte-for-byte untouched (never overwritten), so
    re-running this is idempotent and non-destructive. Returns the text
    unchanged when there is no top-level `context:` block (the caller handles
    the whole-block-add path).

    `token_saver_value` overrides the literal written for the `token_saver`
    toggle (so generation can honour --token-saver while migration defaults to
    "false").
    """
    lines = text.split("\n")
    block = _find_context_block(lines)
    if block is None:
        return text
    header_idx, end, subkey_indent = block
    existing = _existing_context_subkeys(lines, header_idx + 1, end)

    additions: list[str] = []
    for sub_key, default in MIGRATABLE_CONTEXT_SUBKEYS:
        if sub_key in existing:
            continue
        value = token_saver_value if sub_key == "token_saver" else default
        additions.append(f"{subkey_indent}{sub_key}: {value}")

    if not additions:
        return text

    new_lines = lines[:end] + additions + lines[end:]
    return "\n".join(new_lines)


class ConfigResult(Enum):
    CREATED = "created"
    SKIPPED_EXISTS = "skipped_exists"
    SKIPPED_NO_TEMPLATE = "skipped_no_template"
    SKIPPED_NO_YAML = "skipped_no_yaml"
    CREATED_FROM_DEFAULT = "created_from_default"
    SKIPPED_BAD_CONFIG = "skipped_bad_config"


@dataclasses.dataclass
class SkippedArtifact:
    """A render the init script did not produce, with banner-ready context.

    Aggregated in main() so Step 10 surfaces every skip with reason + the
    consumer skill affected + the remediation hint, instead of letting a
    silent skip surface only when the downstream skill runs.
    """
    artifact: str           # human-readable artifact path
    reason: str             # short reason (e.g., "config.yaml: categorization block missing")
    consumer: str           # downstream skill or handler that needs this artifact
    remediation: str        # concrete next-step the user should take


@dataclasses.dataclass
class InitConfig:
    project_name: str
    project_root: Path
    plugin_root: Path
    planwise_root: str = "planwise"
    plans_dir: str = "Plans"
    backlog_dir: str = "Backlog"
    lessons_dir: str = "LessonsLearned"
    install_scope: str = "project"
    plan_tier: str = "pro"
    plugin_version: str = "0.0.0"
    token_saver: bool = False

    @property
    def context_window(self) -> int:
        return PLAN_TIER_WINDOWS[self.plan_tier]


def get_plugin_root() -> Path:
    """Return the plugin root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def read_plugin_version(plugin_root: Path) -> str:
    """Read the plugin version from .claude-plugin/plugin.json.

    Returns the version string. Falls back to "0.0.0" if the file is
    missing or malformed — callers use this as the "unknown / never pinned"
    sentinel so the upgrade flow treats the project as pre-versioning.
    """
    plugin_json = plugin_root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(plugin_json.read_text(encoding="utf-8"))
        return str(data.get("version", "0.0.0"))
    except (FileNotFoundError, json.JSONDecodeError):
        return "0.0.0"


def resolve_rule_paths_value(cfg: "InitConfig", paths_template: str) -> str:
    """Substitute {plans_path} / {all_paths} placeholders into a paths: value."""
    plans_path = f"{cfg.planwise_root}/{cfg.plans_dir}/**"
    all_paths = ", ".join([
        plans_path,
        f"{cfg.planwise_root}/{cfg.backlog_dir}/**",
        f"{cfg.planwise_root}/{cfg.lessons_dir}/**",
    ])
    return paths_template.replace("{plans_path}", plans_path).replace("{all_paths}", all_paths)


def create_directories(cfg: InitConfig) -> list[str]:
    """Create planwise directories. Returns list of created paths."""
    created = []
    dirs = [
        cfg.project_root / cfg.planwise_root / cfg.plans_dir,
        cfg.project_root / cfg.planwise_root / cfg.backlog_dir,
        cfg.project_root / cfg.planwise_root / cfg.lessons_dir,
        cfg.project_root / ".claude" / "rules" / "planwise",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        created.append(str(d.relative_to(cfg.project_root)))
    return created


def copy_seed_files(cfg: InitConfig) -> list[str]:
    """Copy seed index files. Skips if destination exists. Returns list of copied files."""
    copied = []
    seeds = [
        ("00-Index-Backlog.md", f"{cfg.planwise_root}/{cfg.backlog_dir}/00-Index-Backlog.md"),
        ("00-Index-LessonsLearned.md", f"{cfg.planwise_root}/{cfg.lessons_dir}/00-Index-LessonsLearned.md"),
        ("00-Index-Plans.md", f"{cfg.planwise_root}/{cfg.plans_dir}/00-Index-Plans.md"),
    ]
    seed_dir = cfg.plugin_root / "seed"
    for src_name, dst_rel in seeds:
        src = seed_dir / src_name
        dst = cfg.project_root / dst_rel
        try:
            src_content = src.read_bytes()
        except FileNotFoundError:
            print(f"  Warning: seed file not found: {src}", file=sys.stderr)
            continue
        try:
            with open(dst, "xb") as f:
                f.write(src_content)
        except FileExistsError:
            continue
        copied.append(dst_rel)
    return copied


def generate_config(cfg: InitConfig) -> tuple[ConfigResult, str]:
    """Generate config.yaml from template. Returns (status, path)."""
    template_path = cfg.plugin_root / "config.yaml.template"
    config_rel = f"{cfg.planwise_root}/config.yaml"
    dst = cfg.project_root / cfg.planwise_root / "config.yaml"

    try:
        content = template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ConfigResult.SKIPPED_NO_TEMPLATE, config_rel

    content = content.replace("{plugin-root}", str(get_plugin_root()).replace("\\", "/"))
    content = content.replace("{project-name}", cfg.project_name)
    content = content.replace("{install-scope}", cfg.install_scope)
    content = content.replace("{planwise-root}", cfg.planwise_root)
    content = content.replace("{plans-dir}", cfg.plans_dir)
    content = content.replace("{backlog-dir}", cfg.backlog_dir)
    content = content.replace("{lessons-dir}", cfg.lessons_dir)
    content = content.replace("{plan-tier}", cfg.plan_tier)
    content = content.replace("{context-window}", str(cfg.context_window))
    content = content.replace("{plugin-version}", cfg.plugin_version)
    content = content.replace("{token-saver}", "true" if cfg.token_saver else "false")

    # Ensure the six Token Saver sub-keys are present even if the shipped
    # template predates them (older template, or a fixture without them) —
    # the nested merge is additive and respects the --token-saver toggle.
    content = merge_context_subkeys(
        content, token_saver_value="true" if cfg.token_saver else "false"
    )

    try:
        with open(dst, "x", encoding="utf-8") as f:
            f.write(content)
    except FileExistsError:
        return ConfigResult.SKIPPED_EXISTS, config_rel
    return ConfigResult.CREATED, config_rel


def _render_bucket_section(bucket: dict, code_bucket_inherited: bool = False) -> list[str]:
    """Render one top-level bucket plus its sub-buckets to a list of lines."""
    bucket_id = str(bucket.get("id", "?"))
    bucket_name = str(bucket.get("name", ""))
    description = str(bucket.get("description", ""))
    code_bucket = bool(bucket.get("code_bucket", code_bucket_inherited))

    if code_bucket:
        header_row = "| ID | Title | Module | Severity |"
        sep_row = "|----|-------|--------|----------|"
    else:
        header_row = "| ID | Title | Severity |"
        sep_row = "|----|-------|----------|"

    lines = [
        f"## {bucket_id}. {bucket_name} (0)",
        "",
        description,
        "",
        header_row,
        sep_row,
    ]

    for sub in bucket.get("sub_buckets") or []:
        if not isinstance(sub, dict):
            continue
        sub_id = str(sub.get("id", "?"))
        sub_name = str(sub.get("name", ""))
        lines.extend([
            "",
            f"### {sub_id}. {sub_name} (0)",
            "",
            header_row,
            sep_row,
        ])

    return lines


def render_categorization_file(cfg: "InitConfig") -> tuple[ConfigResult, str]:
    """Render 00-Categorization-By-Domain.md from config + categorization schema.

    Idempotent — returns SKIPPED_EXISTS if the file already exists.
    Returns SKIPPED_NO_YAML if PyYAML is unavailable (the init handler's
    Step 5.1 fallback renders the file via Claude in that case).

    When the user's config has no `categorization:` block (or the block is
    empty), the renderer falls back to DEFAULT_CATEGORIZATION and returns
    CREATED_FROM_DEFAULT so the banner can flag it. The user can edit the
    buckets afterwards, or run `--migrate` to add the template block to
    their config for full customisation.
    """
    dst_rel = f"{cfg.planwise_root}/{cfg.lessons_dir}/00-Categorization-By-Domain.md"
    dst = cfg.project_root / dst_rel
    if dst.exists():
        return ConfigResult.SKIPPED_EXISTS, dst_rel

    if not HAS_YAML:
        return ConfigResult.SKIPPED_NO_YAML, dst_rel

    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    config_present = config_path.exists()
    cat: dict | None = None
    used_default = False
    lessons_index = "00-Index-LessonsLearned.md"

    if config_present:
        try:
            config_text = config_path.read_text(encoding="utf-8")
            full = yaml.safe_load(config_text) or {}
            if isinstance(full, dict):
                candidate = full.get("categorization")
                if isinstance(candidate, dict):
                    buckets_candidate = candidate.get("buckets") or []
                    if [b for b in buckets_candidate if isinstance(b, dict)]:
                        cat = candidate
                lessons_index = (
                    full.get("project", {})
                    .get("index_files", {})
                    .get("lessons", "00-Index-LessonsLearned.md")
                )
        except yaml.YAMLError:
            # Bad config — fall through to default, surface via banner.
            pass

    if cat is None:
        cat = DEFAULT_CATEGORIZATION
        used_default = True

    buckets = cat.get("buckets") or []
    buckets = [b for b in buckets if isinstance(b, dict)]
    if not buckets:
        # Defensive — DEFAULT_CATEGORIZATION always has buckets, but guard anyway.
        return ConfigResult.SKIPPED_BAD_CONFIG, dst_rel

    decision_tree_order = cat.get("decision_tree_order") or [b.get("id") for b in buckets]
    buckets_by_id = {b.get("id"): b for b in buckets}
    ordered_buckets = [buckets_by_id[bid] for bid in decision_tree_order if bid in buckets_by_id]
    for b in buckets:
        if b.get("id") not in {bb.get("id") for bb in ordered_buckets}:
            ordered_buckets.append(b)

    bucket_blocks = []
    for b in ordered_buckets:
        bucket_blocks.append("\n".join(_render_bucket_section(b)))

    today = date.today().isoformat()
    scope_paragraph = f"Lessons captured during {cfg.project_name} sessions."

    rendered = (
        "# Lessons Learned — Categorization by Domain\n"
        "\n"
        f"**Purpose:** Group lessons in `{cfg.lessons_dir}/` by domain for scope-specific review and rule-promotion decisions.\n"
        f"**Last Updated:** {today}\n"
        f"**Companion to:** [{lessons_index}]({lessons_index}) (chronological master table)\n"
        "\n"
        "---\n"
        "\n"
        "## Scope\n"
        "\n"
        f"{scope_paragraph}\n"
        "\n"
        "---\n"
        "\n"
        + "\n\n".join(bucket_blocks)
        + "\n"
        "\n"
        "---\n"
        "\n"
        "## Cross-cutting observations\n"
        "\n"
        "_Populated by `/planwise lessons curate` as patterns emerge across buckets._\n"
        "\n"
        "---\n"
        "\n"
        "## Classification edge cases\n"
        "\n"
        "| ID | Why it could fit elsewhere | Final bucket |\n"
        "|----|---------------------------|---------------|\n"
        "\n"
        "---\n"
    )

    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dst, "x", encoding="utf-8") as f:
            f.write(rendered)
    except FileExistsError:
        return ConfigResult.SKIPPED_EXISTS, dst_rel
    return (
        ConfigResult.CREATED_FROM_DEFAULT if used_default else ConfigResult.CREATED,
        dst_rel,
    )


def _seed_lessons_index(cfg: "InitConfig") -> tuple[ConfigResult, str]:
    """Seed the lessons index from the plugin seed dir if missing. Idempotent.

    Mirrors copy_seed_files for the lessons index alone, so the upgrade-side
    backfill can recreate it without re-seeding backlog/plans. Returns
    SKIPPED_EXISTS when the file is already present (never overwrites a
    populated index) and SKIPPED_NO_TEMPLATE when the plugin seed file is
    absent.
    """
    src_name = "00-Index-LessonsLearned.md"
    dst_rel = f"{cfg.planwise_root}/{cfg.lessons_dir}/{src_name}"
    dst = cfg.project_root / dst_rel
    if dst.exists():
        return ConfigResult.SKIPPED_EXISTS, dst_rel
    src = cfg.plugin_root / "seed" / src_name
    try:
        src_content = src.read_bytes()
    except FileNotFoundError:
        return ConfigResult.SKIPPED_NO_TEMPLATE, dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dst, "xb") as f:
            f.write(src_content)
    except FileExistsError:
        return ConfigResult.SKIPPED_EXISTS, dst_rel
    return ConfigResult.CREATED, dst_rel


@dataclasses.dataclass
class LessonsBootstrap:
    """Outcome of bootstrap_lessons_artifacts, with banner-ready fields.

    Carries the per-artifact ConfigResult so each caller (fresh init / upgrade)
    can render its own banner from the same routine.
    """
    index_result: ConfigResult
    index_rel: str
    cat_result: ConfigResult
    cat_rel: str

    @property
    def created_any(self) -> bool:
        created = {ConfigResult.CREATED, ConfigResult.CREATED_FROM_DEFAULT}
        return self.index_result in created or self.cat_result in created


def bootstrap_lessons_artifacts(cfg: "InitConfig") -> LessonsBootstrap:
    """Ensure the lessons scaffolding (index seed + categorization file) exists.

    The single idempotent, non-destructive routine wired into BOTH fresh init
    and _run_upgrade(): each sub-step is a no-op when its file is already
    present (SKIPPED_EXISTS), so an already-complete project is left untouched
    and a user-customised file is preserved verbatim. On an upgrade-adopted
    project this backfills 00-Categorization-By-Domain.md — the file that
    gates /planwise lessons curate and promote-batch — which the legacy
    fresh-init-only render never created.
    """
    index_result, index_rel = _seed_lessons_index(cfg)
    cat_result, cat_rel = render_categorization_file(cfg)
    return LessonsBootstrap(index_result, index_rel, cat_result, cat_rel)


def _emit_lessons_bootstrap_banner(boot: "LessonsBootstrap") -> None:
    """Print the upgrade-side banner for any backfilled lessons scaffolding.

    Names only what was actually created (CREATED / CREATED_FROM_DEFAULT),
    reusing the same lines the fresh-init Step 5 banner prints; stays silent
    when both artifacts already existed so an up-to-date project reports
    nothing.
    """
    if not boot.created_any:
        return
    print("Lessons scaffolding backfilled:")
    if boot.index_result == ConfigResult.CREATED:
        print(f"  + {boot.index_rel}")
    if boot.cat_result == ConfigResult.CREATED:
        print(f"  + {boot.cat_rel}")
    elif boot.cat_result == ConfigResult.CREATED_FROM_DEFAULT:
        print(
            f"  + {boot.cat_rel} (rendered with default buckets — "
            "config.yaml `categorization:` block missing)"
        )
        print("                  Add the block to customise buckets, or run --migrate to seed it from the template.")
    print()


def update_frontmatter(content: str, paths_value: str) -> str:
    """Update or add paths: field in YAML frontmatter."""
    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end == -1:
            return f"---\npaths: {paths_value}\n---\n\n{content}"

        frontmatter = content[4:end]
        body = content[end + 5:]

        if re.search(r"^paths:", frontmatter, re.MULTILINE):
            frontmatter = re.sub(
                r"^paths:.*$", f"paths: {paths_value}",
                frontmatter, count=1, flags=re.MULTILINE
            )
        else:
            frontmatter = frontmatter.rstrip() + f"\npaths: {paths_value}"

        return f"---\n{frontmatter}\n---\n{body}"
    else:
        return f"---\npaths: {paths_value}\n---\n\n{content}"


def install_rules(cfg: InitConfig) -> list[str]:
    """Copy reference files as rules with updated paths: frontmatter.
    Skips if destination exists. Returns list of installed rules."""
    installed = []
    refs_dir = cfg.plugin_root / "references"
    rules_dir = cfg.project_root / ".claude" / "rules" / "planwise"

    for filename, paths_template in INSTALLED_RULES:
        paths_value = resolve_rule_paths_value(cfg, paths_template)
        dst = rules_dir / filename
        src = refs_dir / filename
        try:
            content = src.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"  Warning: reference not found: {src}", file=sys.stderr)
            continue

        content = update_frontmatter(content, paths_value)
        try:
            with open(dst, "x", encoding="utf-8") as f:
                f.write(content)
        except FileExistsError:
            continue
        installed.append(filename)

    return installed


def load_artifact_manifest(plugin_root: Path) -> dict:
    """Load manifests/artifacts.yaml from the plugin root.

    The manifest enumerates every artifact the init script produces, the
    config keys it depends on, and the behaviour to take when a key is
    missing. Returns an empty schema if the file or PyYAML is absent so the
    script remains usable in degraded environments — the runtime fallback
    constants (DEFAULT_CATEGORIZATION, MIGRATABLE_TOP_LEVEL_KEYS) carry the
    same defaults the manifest documents.
    """
    if not HAS_YAML:
        return {"artifacts": []}
    manifest_path = plugin_root / "manifests" / "artifacts.yaml"
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"artifacts": []}
    try:
        loaded = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {"artifacts": []}
    if not isinstance(loaded, dict):
        return {"artifacts": []}
    return loaded


def migrate_config(cfg: InitConfig) -> tuple[str, list[str], list[str]]:
    """Merge missing top-level keys from config.yaml.template into the user's config.

    Idempotent. Existing top-level keys are NEVER overwritten. Reports both
    the keys that were added and the keys that were already present so the
    caller can build a Step 10 banner section.

    Returns (config_path_str, added_keys, present_keys).
    Raises FileNotFoundError when the user's config is absent (run /planwise
    init before --migrate).
    """
    if not HAS_YAML:
        raise RuntimeError(
            "PyYAML is required for --migrate. Install with `pip install pyyaml`."
        )

    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"{config_path} does not exist — run /planwise init before --migrate."
        )

    template_path = cfg.plugin_root / "config.yaml.template"
    template_text = template_path.read_text(encoding="utf-8")

    # Render template placeholders before parsing so the merged values are
    # concrete (e.g., `context_window: 200000` instead of `{context-window}`).
    template_text = template_text.replace("{plugin-root}", str(cfg.plugin_root).replace("\\", "/"))
    template_text = template_text.replace("{project-name}", cfg.project_name)
    template_text = template_text.replace("{install-scope}", cfg.install_scope)
    template_text = template_text.replace("{planwise-root}", cfg.planwise_root)
    template_text = template_text.replace("{plans-dir}", cfg.plans_dir)
    template_text = template_text.replace("{backlog-dir}", cfg.backlog_dir)
    template_text = template_text.replace("{lessons-dir}", cfg.lessons_dir)
    template_text = template_text.replace("{plan-tier}", cfg.plan_tier)
    template_text = template_text.replace("{context-window}", str(cfg.context_window))
    template_text = template_text.replace("{plugin-version}", cfg.plugin_version)

    template_data = yaml.safe_load(template_text) or {}
    user_text = config_path.read_text(encoding="utf-8")
    user_data = yaml.safe_load(user_text) or {}

    if not isinstance(user_data, dict) or not isinstance(template_data, dict):
        raise RuntimeError(f"{config_path} is not a YAML mapping — cannot merge.")

    added: list[str] = []
    present: list[str] = []
    for key in MIGRATABLE_TOP_LEVEL_KEYS:
        if key in template_data and key not in user_data:
            user_data[key] = template_data[key]
            added.append(key)
        elif key in user_data:
            present.append(key)

    if not added:
        # No top-level keys to add — but an existing `context:` block may still
        # be missing the Token Saver sub-keys. Do a targeted, comment-preserving
        # nested merge directly on the user's file text (NO yaml round-trip, so
        # comments/order survive and re-running stays byte-for-byte idempotent).
        merged_text = merge_context_subkeys(user_text)
        if merged_text != user_text:
            config_path.write_text(merged_text, encoding="utf-8")
            sub_added = _context_subkeys_delta(user_text, merged_text)
            added.extend(sub_added)
        return str(config_path), added, present

    # Re-emit the file. PyYAML's default dump is acceptable here; the user
    # can reflow manually if needed. Block style + indent 2 keeps the result
    # closest to the template's hand-authored layout.
    merged_yaml = yaml.safe_dump(
        user_data,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
        allow_unicode=True,
    )

    # Preserve the original leading comment header if present.
    header_lines: list[str] = []
    for line in user_text.splitlines():
        if line.startswith("#") or line.strip() == "":
            header_lines.append(line)
        else:
            break
    if header_lines and not header_lines[-1].strip() == "":
        header_lines.append("")
    header = "\n".join(header_lines)
    if header:
        merged_yaml = header + "\n" + merged_yaml

    # The whole-block-add path (context copied from the template) may still
    # lack the Token Saver sub-keys when the shipped template predates them —
    # backfill them into the freshly-written block so every migrate target
    # ends up with the full surface.
    merged_yaml = merge_context_subkeys(merged_yaml)

    config_path.write_text(merged_yaml, encoding="utf-8")
    return str(config_path), added, present


def get_settings_path(cfg: InitConfig) -> Path:
    """Return the settings.json path based on install scope."""
    if cfg.install_scope == InstallScope.USER:
        return Path.home() / ".claude" / "settings.json"
    elif cfg.install_scope == InstallScope.LOCAL:
        return cfg.project_root / ".claude" / "settings.local.json"
    else:  # project
        return cfg.project_root / ".claude" / "settings.json"


def configure_settings(cfg: InitConfig) -> tuple[str | None, str | None]:
    """Apply all settings.json mutations in a single read-write cycle.

    Configures Agent Teams env var and plugin read permissions.
    Returns (settings_path, plugin_dir) — either may be None if skipped.
    """
    settings_path = get_settings_path(cfg)
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        settings = {}
    except json.JSONDecodeError:
        print(f"  Warning: {settings_path} contains invalid JSON — skipping settings configuration.", file=sys.stderr)
        print("  Fix the file manually and re-run /planwise init.", file=sys.stderr)
        return None, None

    # Agent Teams
    env = settings.setdefault("env", {})
    env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"

    # Plugin permissions
    # Grant the version-agnostic plugin-family root (cfg.plugin_root.parent) rather
    # than the version-pinned leaf (cfg.plugin_root). The family root is stable across
    # upgrades, so _run_upgrade() intentionally stays settings-free — there is nothing
    # to refresh. Dedup is parent-aware and normalized for Windows separator/case
    # differences so a broader existing grant is recognized and honoured.
    permissions = settings.setdefault("permissions", {})
    additional_dirs = permissions.setdefault("additionalDirectories", [])
    grant_dir = str(cfg.plugin_root.parent)  # version-agnostic plugin-family root

    def _norm(p):
        return os.path.normcase(os.path.normpath(p))

    def _covers(existing, target):
        """True when existing equals target or is an ancestor directory of target."""
        e, t = _norm(existing), _norm(target)
        return e == t or t.startswith(e + os.sep)

    if any(_covers(d, grant_dir) for d in additional_dirs):
        plugin_dir = None  # already covered by an equal or broader entry → idempotent no-op
    else:
        # Prune version-pinned sibling entries now subsumed by the family-root grant.
        # Only removes entries that are strict descendants of grant_dir (i.e. stale
        # per-version pins for this plugin); unrelated user entries are never touched.
        additional_dirs[:] = [d for d in additional_dirs if not _covers(grant_dir, d)]
        additional_dirs.append(grant_dir)
        plugin_dir = grant_dir

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return str(settings_path), plugin_dir


def _print_skipped_banner(skipped: list[SkippedArtifact]) -> None:
    """Emit the Step 10 SKIPPED section if any artifact was not produced.

    Surfaces every (artifact, reason, consumer, remediation) tuple so the
    user is informed at init-time instead of discovering the gap later when
    the downstream skill fails. Silent on empty input.
    """
    if not skipped:
        return
    print("Skipped (action required):")
    for s in skipped:
        print(f"  ! {s.artifact}")
        print(f"      reason:      {s.reason}")
        print(f"      affects:     {s.consumer}")
        print(f"      remediation: {s.remediation}")
    print()


def normalize_rule_for_diff(content: str) -> str:
    """Return the rule body with the `paths:` frontmatter key removed.

    Per-project install rewrites the `paths:` line via update_frontmatter().
    To detect whether the installed body matches the shipped body, we strip
    that single key from BOTH sides before comparing. Everything else in the
    frontmatter and the body content must match exactly for the file to be
    considered "unmodified by user."

    Uses a pure regex line-strip (no YAML round-trip) so the shipped
    reference's placeholder paths value (which contains literal curly
    braces) and the installed file's resolved paths value are normalized
    identically.

    Delegates the split to structural_compare.split_frontmatter() when the
    module is importable, with a byte-identical inline fallback when it is
    not, so a degraded install keeps diffing correctly. (Sibling helpers
    update_frontmatter/_extract_paths_value retain their own inline
    frontmatter handling — keep the three consistent when editing any.)
    """
    if structural_compare is not None:
        cleaned_frontmatter, body = structural_compare.split_frontmatter(content)
    else:
        cleaned_frontmatter, body = _split_frontmatter_fallback(content)
    if not cleaned_frontmatter:
        return body
    return f"---\n{cleaned_frontmatter}\n---\n{body}"


_FALLBACK_PATHS_LINE_RE = re.compile(r"^paths:.*$\n?", re.MULTILINE)


def _split_frontmatter_fallback(content: str):
    """Byte-identical inline mirror of structural_compare.split_frontmatter.

    Used only when the structural_compare module is unavailable, so
    normalize_rule_for_diff keeps producing the same output in a degraded
    install. Returns (None, content) when there is no frontmatter, else
    (frontmatter_minus_paths, body).
    """
    if not content.startswith("---\n"):
        return None, content
    end = content.find("\n---\n", 4)
    if end == -1:
        return None, content
    frontmatter_text = content[4:end]
    body = content[end + 5:]
    cleaned = _FALLBACK_PATHS_LINE_RE.sub("", frontmatter_text, count=1)
    return cleaned.rstrip(), body


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable integer tuple.

    Non-numeric / missing components degrade to 0 so a malformed or sentinel
    value ("0.0.0", "", or a partial "1.1") still orders sensibly against a
    well-formed version. Used by the de-scope migration version gate.
    """
    parts: list[int] = []
    for component in str(version).split("."):
        digits = re.match(r"\d+", component.strip())
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def _extract_paths_value(content: str) -> str | None:
    """Return the `paths:` frontmatter value from a rule file, or None.

    Reads only the leading `---` frontmatter block; returns the verbatim value
    after `paths:` (stripped of surrounding whitespace). Returns None when the
    file has no frontmatter or no paths: key.
    """
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end == -1:
        return None
    frontmatter_text = content[4:end]
    match = re.search(r"^paths:(.*)$", frontmatter_text, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


# Unambiguous marker for the degraded not-analyzed stand-in `_classify_diverged`
# manufactures when structural_compare is unavailable at call time. Checked
# ONLY by `_verdict_not_analyzed()` — a real verdict (inline or agent-sourced)
# never carries this value, so a genuine HAS_UNIQUE verdict that happens to
# have empty unique_blocks and non-empty notes can never be misidentified as
# "never analyzed" (the old shape-based detection's false-positive hazard).
_DEGRADED_VERDICT_SOURCE = "not-analyzed"


def _classify_diverged(
    installed_norm: str,
    shipped_norm: str,
    *,
    override: "StructuralVerdict | None" = None,
) -> "StructuralVerdict":
    """Return the structural verdict for a normalized installed/shipped pair.

    If `override` (an agent-produced verdict) is supplied, it is returned
    as-is. Otherwise this delegates to structural_compare.classify_blocks().
    On ImportError (structural_compare missing/broken), degrades to a
    conservative HAS_UNIQUE verdict so the caller preserves the file rather
    than risk deleting a genuine customization — the safe error over the
    dangerous one. The degraded verdict is a duck-typed stand-in (attribute-
    compatible with StructuralVerdict), since the real class is unavailable
    exactly when this path fires. Its `source` is the explicit
    `_DEGRADED_VERDICT_SOURCE` marker (not a shape heuristic) so
    `_verdict_not_analyzed()` can never mistake a genuine verdict for this
    stand-in. Module-level (not nested) so tests can monkeypatch
    `ip._classify_diverged` directly.
    """
    if override is not None:
        return override
    try:
        from structural_compare import classify_blocks as _classify_blocks
    except ImportError:
        return types.SimpleNamespace(
            classification="HAS_UNIQUE",
            confidence="unique",
            unique_blocks=[],
            shared_blocks=0,
            total_installed_blocks=0,
            installed_only_chars=0,
            unique_sample_tokens=[],
            source=_DEGRADED_VERDICT_SOURCE,
            notes="structural_compare unavailable; degraded to preserve",
        )
    return _classify_blocks(installed_norm, shipped_norm)


def _load_verdicts_cache(cfg: "InitConfig", from_version: str, to_version: str) -> dict:
    """Load the interactive fan-out's verdicts.json cache, if present.

    Path: ``{planwise_root}/upgrade-conflicts/{from}-to-{to}/verdicts.json``. This
    is the ONLY place the cache is read from disk — every ``--upgrade`` writer
    site (the Site-1 de-scope migration and the Sites-2/3 artifact refresh)
    calls this helper once, then looks up its own filename to build an
    override. A missing file, an unreadable file, or malformed (non-dict)
    JSON all degrade to ``{}`` — no ``verdicts.json`` is the headless-complete
    baseline; the writer never requires the cache to run.
    """
    path = (
        cfg.project_root / cfg.planwise_root / "upgrade-conflicts"
        / f"{from_version}-to-{to_version}" / "verdicts.json"
    )
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _load_verdict_override(
    verdicts: dict, filename: str, installed_raw: str
) -> "StructuralVerdict | None":
    """Return a StructuralVerdict built from a verdicts.json cache entry, or None.

    Degrades to None (the conservative inline-primitive path, per
    `_classify_diverged`'s own preserve-on-doubt fallback) whenever: the
    filename has no cache entry, `structural_compare` itself is unavailable
    (`StructuralVerdict` is not importable in degraded mode), the entry is not
    a dict (a string/list/number/null cache value — malformed cache, never
    crash), or `from_dict` raises (`ValueError` when `classification`/
    `confidence` is missing, or `AttributeError` when the entry is dict-shaped
    but a nested field is the wrong type for `.items()`-style access — a
    partial/malformed agent verdict must NEVER crash the `--upgrade` run).

    Freshness-bound: each entry must also carry `installed_sha256` — the
    sha256 hex digest of the installed file's bytes at the time the
    comparator analyzed it. It is re-hashed against `installed_raw` here; a
    missing or mismatched hash means the cached verdict was computed against
    different bytes than what's on disk NOW (a later edit, a partial rerun, a
    stale carried-over cache) — the override is ignored (one-line stderr
    note) rather than trusted against content it doesn't provably describe.

    A well-formed SUBSET verdict may legitimately carry a non-empty `notes`
    field (installed-only sub-noise-floor fragments) — that is not malformed
    and deserializes cleanly.
    """
    if not HAS_STRUCTURAL_COMPARE or filename not in verdicts:
        return None
    entry = verdicts[filename]
    if not isinstance(entry, dict):
        print(
            f"  Warning: verdicts.json entry for {filename} is not an object "
            "— ignoring cached verdict",
            file=sys.stderr,
        )
        return None
    current_hash = hashlib.sha256(installed_raw.encode("utf-8")).hexdigest()
    cached_hash = entry.get("installed_sha256")
    if not cached_hash or cached_hash != current_hash:
        print(
            f"  Warning: verdicts.json entry for {filename} has a missing or "
            "stale installed_sha256 — ignoring cached verdict",
            file=sys.stderr,
        )
        return None
    try:
        return StructuralVerdict.from_dict(entry)
    except (ValueError, TypeError, AttributeError):
        return None


def _write_backup_preimage(
    cfg: "InitConfig", from_version: str, to_version: str, dst: Path
) -> bool:
    """Copy dst's CURRENT bytes to upgrade-backups/{from}-to-{to}/, mirroring
    its project-relative path. Call this BEFORE any destructive overwrite or
    removal of `dst`.

    Returns True on success, False on any OSError (a stderr warning is
    printed). Callers MUST treat False as "abort the destructive step; leave
    the file untouched" — the same failed-backup-blocks-destruction contract
    `_run_prune_stale()` already applies to its own removals. Never raises.
    """
    backup_root = (
        cfg.project_root / cfg.planwise_root / "upgrade-backups"
        / f"{from_version}-to-{to_version}"
    )
    try:
        rel = dst.relative_to(cfg.project_root)
    except ValueError:
        rel = Path(dst.name)
    try:
        backup_path = backup_root / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")
        return True
    except OSError as exc:
        print(
            f"  Warning: could not back up {dst} before a destructive write: {exc}",
            file=sys.stderr,
        )
        return False


def _append_disposition_log(
    cfg: "InitConfig",
    from_version: str,
    to_version: str,
    dst: Path,
    action: str,
    reason: str,
) -> None:
    """Append a DISPOSITIONS.md row recording an ALREADY-COMPLETED destructive
    action.

    Call this ONLY after the destructive write/removal has actually
    succeeded — logging before the fact can produce a false row plus stranded
    state if the write later fails (the interleaving `upgrade_artifacts()`'s
    transfer-then-adopt sites now avoid: transfer, verify, back up, THEN
    write, and only log once that write is confirmed).

    Best-effort: an OSError here is a stderr warning only — the disposition
    itself already happened, so losing the log row (not the file) is the
    worst case. Never raises.
    """
    backup_root = (
        cfg.project_root / cfg.planwise_root / "upgrade-backups"
        / f"{from_version}-to-{to_version}"
    )
    try:
        rel = dst.relative_to(cfg.project_root)
    except ValueError:
        rel = Path(dst.name)
    try:
        log_path = backup_root / "DISPOSITIONS.md"
        header = "" if log_path.exists() else (
            f"# Upgrade dispositions: {from_version} -> {to_version}\n\n"
            "Pre-change copies of every file this upgrade deleted or overwrote\n"
            "live alongside this log, mirroring their project-relative paths.\n\n"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{header}- {date.today().isoformat()} `{rel}` — {action}: {reason}\n")
    except OSError as exc:
        print(
            f"  Warning: could not log disposition for {dst}: {exc}",
            file=sys.stderr,
        )


def _record_disposition(
    cfg: "InitConfig",
    from_version: str,
    to_version: str,
    dst: Path,
    action: str,
    reason: str,
) -> bool:
    """Back up dst's pre-image and append a DISPOSITIONS.md row in one call —
    the convenience wrapper for the SIMPLE destructive sites where the
    caller's own destructive write immediately follows this call with no
    intermediate step that could itself independently fail (e.g. `dst.unlink()`
    right after).

    Returns True iff the backup succeeded; callers MUST skip the destructive
    action when this returns False (same failed-backup-blocks-destruction
    contract as `_write_backup_preimage()`). Sites where the destructive write
    can itself fail AFTER a successful transfer (the transfer-then-adopt
    sites in `upgrade_artifacts()`) call `_write_backup_preimage()` and
    `_append_disposition_log()` directly instead, logging only once the write
    is confirmed to have succeeded.
    """
    ok = _write_backup_preimage(cfg, from_version, to_version, dst)
    if ok:
        _append_disposition_log(cfg, from_version, to_version, dst, action, reason)
    return ok


def _load_raw_config(cfg: "InitConfig") -> dict:
    """Load config.yaml as a plain dict, degrading to {} on any failure.

    Shared by every writer site that needs the `upgrade:` block (the de-scope
    migration's `descope_preserve_paths_edits`, the artifact refresh's
    `customization_handoff`) — tolerant on purpose so a missing/unparsable
    config.yaml degrades to `get_upgrade_config()`'s conservative defaults
    rather than aborting the run.
    """
    if not HAS_YAML:
        return {}
    try:
        loaded = yaml.safe_load(
            (cfg.project_root / cfg.planwise_root / "config.yaml").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError, yaml.YAMLError):
        # ValueError covers UnicodeDecodeError (non-UTF-8 config) — the load
        # is tolerant on purpose; degrade to {} = conservative defaults.
        return {}
    return loaded if isinstance(loaded, dict) else {}


def migrate_installed_rules(
    cfg: "InitConfig",
    from_version: str,
    to_version: str,
) -> dict:
    """Remove install-set rules that the de-scope moved to handler-loading.

    Version-gated: acts only when
    ``from_version < RESCOPE_MIGRATION_VERSION <= to_version`` (the single
    upgrade that crosses the de-scope boundary). Outside that window it is a
    pure no-op and touches nothing.

    For each (filename, old_template) in DESCOPED_RULES, the installed copy at
    ``.claude/rules/planwise/{filename}`` is dispositioned as follows.
    Normalized-identical body (fast path — the structural primitive is never
    invoked): paths also match -> removed (provably untouched); paths differ ->
    removed with an INFO notice (scoping is moot once the rule is
    handler-loaded), unless ``upgrade.descope_preserve_paths_edits`` is true ->
    preserved. Diverged body: classified via ``_classify_diverged()`` — a
    stale SUBSET is removed only when the verdict is high-confidence
    (exact/contained) AND its ``notes`` field is empty (non-empty notes means
    the matcher tolerated installed-only content, e.g. sub-noise-floor
    fragments — preserved instead) AND the paths-edit preserve opt-out does
    not apply (a paths-customized copy is kept even over a stale body while
    ``descope_preserve_paths_edits`` is true); a reorg-confidence SUBSET (no
    notes) is always preserved with an explanatory notice — a confidence gap,
    not a genuine customization, so ``customization_handoff`` never applies.
    A notes-flagged SUBSET or a genuine HAS_UNIQUE (customization-bearing)
    verdict is gated on the effective ``upgrade.customization_handoff``,
    read via the SAME accessor the artifact refresh writer uses — BUT the
    paths-edit preserve opt-out takes PRECEDENCE over that gate too, exactly
    as it does for the high-confidence-subset branch above: a paths-
    customized copy (``paths_match`` False) with ``descope_preserve_paths_edits``
    true is preserved in place even when the body ALSO carries a genuine
    customization — a file customized in both paths: and body must never get
    WEAKER protection than one customized in paths: alone. Only when that
    opt-out does not apply does ``customization_handoff`` decide the
    disposition: ``report+relocate`` (the shipped template default)
    verified-transfers the customization to the upgrade transfer helper's
    dormant preservation home (``_transfer_customization()``) and, ONLY on
    that verified success, backs up and removes the stale installed file;
    any other value (``report``, the absent-key fallback, or
    ``report+issue``) preserves in place with a re-home notice, unchanged
    from prior behavior. A failed transfer or a failed pre-removal backup
    means NO removal — the file is preserved in place and the failure
    reported; a customization is never destroyed without a verified copy
    elsewhere. The degraded not-analyzed stand-in
    (structural_compare unavailable) always preserves regardless of
    ``customization_handoff`` — there is no verdict evidence yet to transfer
    on. Every plain removal (the fast-path and high-confidence branches)
    mirrors the pre-image under ``{planwise_root}/upgrade-backups/`` via
    ``_record_disposition()``; a transfer-then-remove instead backs up via
    ``_write_backup_preimage()`` and logs via ``_append_disposition_log()``
    only once the removal itself has succeeded (mirroring the artifact
    refresh's own transfer-then-adopt ordering). The migration never
    defaults a preserve notice to recommending deletion. A per-file OSError
    is contained as a ``skipped`` entry — the loop always completes and
    reports. Rules outside DESCOPED_RULES are never inspected or modified.

    Returns ``{"removed": [...], "preserved": [...], "skipped": [...]}`` where
    each list holds human-readable strings (filename + reason). The shape is
    intentionally loose so the upgrade banner can fold it in directly.
    """
    report: dict[str, list[str]] = {"removed": [], "preserved": [], "skipped": []}

    # Version gate — run exactly once, on the upgrade that crosses the boundary.
    gate = _version_tuple(RESCOPE_MIGRATION_VERSION)
    if not (_version_tuple(from_version) < gate <= _version_tuple(to_version)):
        return report

    refs_dir = cfg.plugin_root / "references"
    rules_dir = cfg.project_root / ".claude" / "rules" / "planwise"

    # The paths-edit opt-out lives under the `upgrade:` block in config.yaml.
    # InitConfig does not carry the raw config dict, so load it at the site;
    # tolerant on purpose — an absent/unparsable config degrades to {} and
    # get_upgrade_config() supplies the conservative defaults.
    config = _load_raw_config(cfg)
    upgrade_config = get_upgrade_config(config)   # dict contract; bind once, read twice below

    preserve_paths_edits = upgrade_config["descope_preserve_paths_edits"]

    # `upgrade.customization_handoff` gates Site-1's own transfer-then-remove
    # path over a preserved, customization-bearing de-scoped rule — read via
    # the SAME accessor and gated exactly like the artifact refresh writer's
    # (Sites 2/3) customization-bearing branch: `report+relocate` (the
    # shipped template default) enables the automated transfer-then-remove
    # flow below; `report` (also the absent-key fallback) and `report+issue`
    # (whose extra gh-issue meaning is handler-side only) stay conservative —
    # preserve in place, no transfer, no removal.
    relocate_enabled = upgrade_config["customization_handoff"] == "report+relocate"

    # verdicts.json entries apply across every --upgrade writer site, not just
    # the artifact refresh (Sites 2/3) — the interactive fan-out's --list-diverged
    # scope includes DESCOPED_RULES, so a de-scoped rule can carry a cached
    # agent verdict too. Same helper, same degrade-to-None-on-absence contract.
    verdicts = _load_verdicts_cache(cfg, from_version, to_version)

    def _transfer_then_remove_or_preserve(
        dst: Path, filename: str, installed_raw: str, verdict, preserve_message: str,
        *, paths_match: bool,
    ) -> None:
        """Disposition for a customization-bearing preserved de-scoped rule.

        Mirrors the artifact refresh writer's (Sites 2/3) customization_handoff
        gate and reuses its `_transfer_customization()` helper exactly: under
        `report+relocate`, the customization is verified-transferred to the
        upgrade transfer helper's dormant preservation home BEFORE the stale
        installed copy is backed up and removed. A failed transfer or a
        failed pre-removal backup means NO removal — the file stays in place
        and the failure is reported (never destroy the only copy of a
        customization). Any other handoff value preserves in place, exactly
        as before (no writes).

        The paths-edit preserve opt-out (`descope_preserve_paths_edits`) takes
        PRECEDENCE over `customization_handoff` here, exactly as it does in the
        sibling high-confidence-subset branch above: a paths-customized copy
        (`paths_match` False) is preserved in place even when the body ALSO
        carries a genuine customization, rather than transferred-then-removed
        under `report+relocate`. A file customized in BOTH paths: and body
        must never receive WEAKER protection than one customized in paths:
        alone.
        """
        if not paths_match and preserve_paths_edits:
            report["preserved"].append(
                f"{filename}: kept (paths-customized; preserve opt-out covers paths: "
                "edits even when the body also carries a customization) — re-home or "
                "re-scope to the code dirs it governs")
            return

        if not relocate_enabled:
            report["preserved"].append(preserve_message)
            return

        transfer_path = _transfer_customization(
            cfg, filename, "rule", installed_raw, verdict, from_version, to_version,
        )
        if transfer_path is None:
            report["preserved"].append(
                f"{filename}: kept — automated transfer failed; installed file "
                "left in place (no removal without a verified transfer)")
            return

        if not _write_backup_preimage(cfg, from_version, to_version, dst):
            report["preserved"].append(
                f"{filename}: kept — customization transferred to {transfer_path}, "
                "but the pre-removal backup failed; installed file left in place "
                "(no removal without a pre-image)")
            return

        try:
            dst.unlink()
        except OSError as exc:
            report["skipped"].append(
                f"{filename}: skipped — customization transferred to "
                f"{transfer_path} and backed up, but removal failed ({exc}); "
                "installed file left in place")
            return

        _append_disposition_log(
            cfg, from_version, to_version, dst, "removed (customization transferred)",
            f"customization transferred to {transfer_path}")
        report["removed"].append(
            f"{filename}: removed — customization transferred to "
            f"{transfer_path} (re-home it there: port to a project-local rule, "
            "re-scope paths:, or upstream the change); the rule is now "
            "handler-loaded from references/")

    for filename, old_template in DESCOPED_RULES:
        dst = rules_dir / filename
        try:
            if not dst.exists():
                # Already absent (fresh install on the new version, or a prior
                # migration run already removed it) — nothing to do, stay idempotent.
                report["skipped"].append(f"{filename}: not installed — nothing to migrate")
                continue

            # utf-8-sig: a leading BOM must not defeat the frontmatter-anchored
            # comparison helpers (startswith("---\n") returns False on a BOM'd
            # file, silently flipping the disposition) — strip it at read time.
            installed_raw = dst.read_text(encoding="utf-8-sig")
            src = refs_dir / filename
            try:
                shipped_raw = src.read_text(encoding="utf-8-sig")
            except FileNotFoundError:
                # Cannot prove the body is untouched without the shipped reference —
                # preserve the installed copy rather than risk deleting a custom one.
                report["preserved"].append(
                    f"{filename}: kept — shipped reference unavailable to compare; "
                    "re-home to a project-local rule or upstream the edit if it is custom"
                )
                continue

            installed_norm = normalize_rule_for_diff(installed_raw)
            shipped_norm = normalize_rule_for_diff(shipped_raw)
            installed_paths = _extract_paths_value(installed_raw)
            paths_match = installed_paths == resolve_rule_paths_value(cfg, old_template)

            if installed_norm == shipped_norm:
                # FAST PATH — normalized-identical; primitive NOT called.
                if paths_match:
                    if _record_disposition(
                            cfg, from_version, to_version, dst, "removed",
                            "untouched de-scoped rule (normalized-identical, paths match)"):
                        dst.unlink()
                        report["removed"].append(
                            f"{filename}: removed — untouched de-scoped rule "
                            "(now handler-loaded from references/)")
                    else:
                        # Failed backup = no deletion (same contract as the
                        # prune writer): the pre-image is the only recovery
                        # path once the file is gone.
                        report["skipped"].append(
                            f"{filename}: skipped — backup write failed; installed "
                            "file left in place (no removal without a pre-image)")
                elif preserve_paths_edits:
                    report["preserved"].append(
                        f"{filename}: kept (paths-customized; preserve opt-out enabled) — "
                        "re-home or re-scope to the code dirs it governs")
                else:
                    if _record_disposition(
                            cfg, from_version, to_version, dst, "removed",
                            "body matches shipped; custom paths: dropped (opt-out disabled)"):
                        dst.unlink()
                        report["removed"].append(
                            f"{filename}: removed [INFO] — body matches shipped; custom paths: "
                            "dropped (scoping is moot once the rule is handler-loaded)")
                    else:
                        report["skipped"].append(
                            f"{filename}: skipped — backup write failed; installed "
                            "file left in place (no removal without a pre-image)")
            else:
                verdict = _classify_diverged(
                    installed_norm, shipped_norm,
                    override=_load_verdict_override(verdicts, filename, installed_raw),
                )
                verdict_notes = getattr(verdict, "notes", "") or ""
                if _destructively_removable(verdict):
                    # Deletion needs BOTH the high-confidence subset verdict AND a
                    # clean notes field — non-empty notes means the primitive
                    # tolerated installed-only content (e.g. sub-noise-floor
                    # fragments), which is exactly what deletion must not destroy.
                    if not paths_match and preserve_paths_edits:
                        # The paths-edit preserve opt-out covers the diverged path
                        # too: a stale body does not forfeit a paths: customization.
                        report["preserved"].append(
                            f"{filename}: kept (paths-customized; body is a stale subset "
                            "but the preserve opt-out covers paths: edits) — re-home or "
                            "re-scope to the code dirs it governs")
                    else:
                        reason = "stale subset of the grown shipped reference"
                        if not paths_match:
                            reason += "; custom paths: dropped (opt-out disabled)"
                        if _record_disposition(
                                cfg, from_version, to_version, dst, "removed", reason):
                            dst.unlink()
                            suffix = (
                                " [INFO] custom paths: dropped (opt-out disabled)"
                                if not paths_match else "")
                            report["removed"].append(
                                f"{filename}: removed — stale subset of the grown shipped "
                                f"reference (now handler-loaded from references/){suffix}")
                        else:
                            report["skipped"].append(
                                f"{filename}: skipped — backup write failed; installed "
                                "file left in place (no removal without a pre-image)")
                elif is_subset(verdict):
                    if verdict_notes:
                        # SUBSET verdict flagged installed-only content the matcher
                        # tolerated as noise — genuine customization-bearing
                        # content. Under `report+relocate` this transfers then
                        # removes (the same customization-bearing gate the
                        # artifact refresh applies); otherwise it preserves as
                        # before, surfacing the primitive's own note either way.
                        _transfer_then_remove_or_preserve(
                            dst, filename, installed_raw, verdict,
                            f"{filename}: kept — subset verdict carries installed-only "
                            f"content ({verdict_notes}); preserved rather than risk "
                            "deleting a short customization. Review manually before "
                            "removal.",
                            paths_match=paths_match)
                    else:                                  # SUBSET but confidence == reorg
                        # Headless-inconclusive reorg is a confidence gap, not a
                        # genuine customization — it always preserves regardless
                        # of customization_handoff (nothing to transfer).
                        report["preserved"].append(
                            f"{filename}: kept — headless inconclusive (content reorganized, "
                            "not a clean subset); run /planwise upgrade interactively to "
                            "agent-verify, or /planwise doctor, before removal")
                else:                                      # HAS_UNIQUE
                    unique_blocks = getattr(verdict, "unique_blocks", []) or []
                    if _verdict_not_analyzed(verdict):
                        # Degraded stand-in (analysis never ran) — always
                        # preserved regardless of customization_handoff,
                        # mirroring the artifact refresh's own bypass: there is
                        # no verdict evidence yet to transfer on. Do NOT assert
                        # "0 customized blocks"; say why it was preserved
                        # unexamined.
                        report["preserved"].append(
                            f"{filename}: kept — {verdict_notes}. The installed copy was "
                            "NOT analyzed and may carry customizations; diff it against "
                            "references/ before deleting anything manually.")
                    else:
                        # Genuine HAS_UNIQUE — customization-bearing. Under
                        # `report+relocate` this transfers then removes;
                        # otherwise it preserves as before.
                        blocks = ", ".join(unique_blocks[:3]) or "see verdict"
                        _transfer_then_remove_or_preserve(
                            dst, filename, installed_raw, verdict,
                            f"{filename}: kept ({len(unique_blocks)} customized block(s): "
                            f"{blocks}) — the orchestrator now loads this rule from "
                            "references/; re-home: port to a project-local rule, re-scope "
                            "paths: to code dirs, or upstream the change. Installed copy "
                            "unchanged.",
                            paths_match=paths_match)
        except OSError as exc:
            # Per-file containment: one unreadable/read-only file must not abort
            # the migration mid-loop (earlier deletions would then go unreported).
            report["skipped"].append(
                f"{filename}: skipped — disposition failed ({exc}); installed file "
                "left in place")

    return report


def lint_rule_overscope(cfg: "InitConfig") -> list[dict]:
    """Flag installed rules scoped to plan/backlog/lessons globs. Read-only.

    Walks every ``.claude/rules/**/*.md`` file (recursive, including
    project-authored rules), parses its paths: frontmatter, and records a flag
    when the value references the plans, backlog, or lessons globs derived from
    cfg. Each flagged entry carries the path, a line count, an approximate
    injected-token estimate (~13 tokens/line), and the matched glob so the
    caller can render a re-scope hint.

    Never writes or deletes anything — purely diagnostic.
    """
    rules_root = cfg.project_root / ".claude" / "rules"
    if not rules_root.exists():
        return []

    plans_glob = f"{cfg.planwise_root}/{cfg.plans_dir}/**"
    backlog_glob = f"{cfg.planwise_root}/{cfg.backlog_dir}/**"
    lessons_glob = f"{cfg.planwise_root}/{cfg.lessons_dir}/**"
    watched_globs = (plans_glob, backlog_glob, lessons_glob)

    flagged: list[dict] = []
    for md_file in sorted(rules_root.rglob("*.md")):
        if not md_file.is_file():
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # A non-UTF-8/unreadable file cannot be over-scope-linted, and it
            # must never crash the always-exit-0 doctor path — skip it here;
            # the Stage 9 divergence lint surfaces it as UNVERIFIABLE.
            continue
        paths_value = _extract_paths_value(content)
        if not paths_value:
            continue
        matched = next((g for g in watched_globs if g in paths_value), None)
        if matched is None:
            continue
        line_count = content.count("\n") + (0 if content.endswith("\n") else 1)
        flagged.append({
            "path": str(md_file),
            "line_count": line_count,
            "approx_tokens": line_count * 13,
            "matched_glob": matched,
        })
    return flagged


def sweep_stale_descoped_rules(cfg: "InitConfig") -> list[dict]:
    """Post-boundary stale de-scoped rule sweep. Read-only.

    Mirrors lint_rule_overscope(): walks the still-installed DESCOPED_RULES
    under .claude/rules/planwise/ — the leftovers the one-shot
    migrate_installed_rules() never reached (its version gate is spent for any
    install already past RESCOPE_MIGRATION_VERSION) — classifies each against
    the shipped references/ copy, and recommends a disposition. NEVER writes or
    deletes; purely diagnostic.

    Each finding is a dict:
      {path, filename, line_count, approx_tokens (=line_count*13),
       verdict: "REMOVABLE" | "PRESERVE" | "RELOCATE", confidence, reason
       [, unique_blocks]}

    REMOVABLE requires BOTH a high-confidence subset verdict (is_subset AND
    is_safe_to_remove) AND an empty verdict.notes field — non-empty notes means
    the matcher tolerated installed-only content (e.g. sub-noise-floor
    fragments) it could not prove was noise, which flips the disposition to
    PRESERVE rather than risk deleting a genuine short customization.
    """
    rules_planwise = cfg.project_root / ".claude" / "rules" / "planwise"
    rules_root = cfg.project_root / ".claude" / "rules"
    refs_dir = cfg.plugin_root / "references"
    findings: list[dict] = []
    if not rules_root.exists():
        return findings

    descoped_names = {fn for fn, _ in DESCOPED_RULES}

    for filename, _old_template in DESCOPED_RULES:
        dst = rules_planwise / filename
        if not dst.is_file():
            continue  # already migrated/removed — nothing stale here
        try:
            installed_raw = dst.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # An unclassifiable file must never be deletable — preserve
            # unread rather than guess at its disposition.
            findings.append({"path": str(dst), "filename": filename,
                             "line_count": 0, "approx_tokens": 0,
                             "verdict": "PRESERVE", "confidence": "unknown",
                             "reason": f"unreadable ({exc}) — cannot classify; preserved"})
            continue
        line_count = installed_raw.count("\n") + (0 if installed_raw.endswith("\n") else 1)
        base = {"path": str(dst), "filename": filename,
                "line_count": line_count, "approx_tokens": line_count * 13}
        try:
            shipped_raw = (refs_dir / filename).read_text(encoding="utf-8")
        except FileNotFoundError:
            findings.append({**base, "verdict": "PRESERVE", "confidence": "unknown",
                             "reason": "shipped reference unavailable — cannot prove "
                                       "stale; re-home if customized"})
            continue

        inst_norm = normalize_rule_for_diff(installed_raw)
        ship_norm = normalize_rule_for_diff(shipped_raw)
        if inst_norm == ship_norm:
            findings.append({**base, "verdict": "REMOVABLE", "confidence": "exact",
                             "reason": "untouched de-scoped rule the one-shot migration "
                                       "never reached; handler-loaded from references/"})
            continue

        v = _classify_diverged(inst_norm, ship_norm)
        # `v.notes` (set by classify_blocks) flags sub-noise-floor installed-only
        # content tolerated during matching — surface it in the reason whenever
        # present so a human sees the caveat before acting on the verdict.
        notes_suffix = f" ({v.notes})" if getattr(v, "notes", "") else ""
        if _destructively_removable(v):
            findings.append({**base, "verdict": "REMOVABLE", "confidence": v.confidence,
                             "reason": "stale subset of the now-grown shipped reference; "
                                       "handler-loaded from references/"})
        elif is_subset(v) and is_safe_to_remove(v):
            # Safe-to-remove EXCEPT the notes field is non-empty — the matcher
            # tolerated installed-only content (e.g. sub-noise-floor fragments).
            # Deletion needs BOTH the high-confidence subset verdict AND a clean
            # notes field; preserve rather than risk destroying a short
            # customization. The automated transfer-then-adopt flow (and the
            # assisted relocation handoff) apply to the --upgrade artifact
            # refresh, not this read-only sweep, so this finding stays PRESERVE
            # here and the customization is re-homed by hand.
            findings.append({**base, "verdict": "PRESERVE", "confidence": v.confidence,
                             "unique_blocks": v.unique_blocks,
                             "reason": "subset, but the matcher tolerated installed-only "
                                       "content" + notes_suffix + "; preserved rather than "
                                       "risk deleting a customization — re-home to "
                                       ".claude/rules/<project>/<name>.md, do NOT delete"})
        else:
            findings.append({**base, "verdict": "PRESERVE", "confidence": v.confidence,
                             "unique_blocks": v.unique_blocks,
                             "reason": "genuine customization (unique content) — re-home "
                                       "to .claude/rules/<project>/<name>.md, do NOT delete"
                                       + notes_suffix})

    # Hack-detection bonus: the old prefix-rename workaround produced files named
    # "<anything>-<shipped-descoped-name>.md" to dodge the de-scope. Flag the
    # fingerprint and point at the proper project-scoped home.
    for md in sorted(rules_root.rglob("*.md")):
        if not md.is_file():
            continue
        for dn in descoped_names:
            if md.name != dn and md.name.endswith("-" + dn):
                try:
                    raw = md.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                lc = raw.count("\n") + (0 if raw.endswith("\n") else 1)
                findings.append({"path": str(md), "filename": md.name,
                                 "line_count": lc, "approx_tokens": lc * 13,
                                 "verdict": "RELOCATE", "confidence": "fingerprint",
                                 "reason": "prefix-rename hack fingerprint of a de-scoped "
                                           "rule — migrate to .claude/rules/<project>/<name>.md"})
                break
    return findings


def lint_installed_divergence(cfg: "InitConfig") -> list[dict]:
    """Read-only: report still-installed rules whose body diverges
    from the plugin-shipped reference.

    Generalizes the de-scoped-rule sweep (sweep_stale_descoped_rules, above)
    from DESCOPED_RULES to the still-installed set: walks INSTALLED_RULES,
    comparing each installed copy to its shipped reference with the same
    normalization the writer uses (normalize_rule_for_diff()), reading BOTH
    sides with ``utf-8-sig`` — the same encoding the artifact refresh writer
    reads with — so a BOM'd-but-untouched installed file is never falsely
    reported diverged (a BOM defeats normalize_rule_for_diff's
    frontmatter-anchored detection under plain ``utf-8``). A
    normalized-identical pair is skipped before `_classify_diverged` is ever
    called — the byte-identical fast path.

    A diverged pair is classified via `_classify_diverged()` and recommended:
      * The degraded not-analyzed stand-in (`_verdict_not_analyzed()` —
        structural_compare unavailable, no analysis ran) -> an explicit
        NOT_ANALYZED row, never a confident recommendation (mirrors the
        migrate/upgrade NOT-analyzed notice convention).
      * SUBSET with empty ``notes`` -> recommend `/planwise upgrade`
        (auto-adopts shipped; matches the writer's own auto-adopt gate,
        `is_subset(verdict) and not verdict.notes`).
      * SUBSET with non-empty ``notes`` (the matcher tolerated
        installed-only content) -> a recommendation that upgrade will
        transfer that content first (or preserve it in place, depending on
        `upgrade.customization_handoff`) before adopting shipped — NOT the
        unconditional auto-adopt wording, since the writer's auto-adopt gate
        does not fire on a non-empty notes field.
      * HAS_UNIQUE -> re-home per the "Choosing a Home for a Rule
        Customization" decide callout.

    A missing shipped reference (broken/partial install) and an unreadable
    installed or shipped file (`OSError` or `UnicodeDecodeError` — e.g.
    non-UTF-8 content) both surface as an explicit UNVERIFIABLE row rather
    than a silent skip: a silent skip would let the caller's all-clear line
    print on a broken or partially-unreadable install, and an uncaught
    `UnicodeDecodeError` would crash the always-on bare `/planwise doctor`
    path. A rule that is simply not installed (no destination file)
    stays a silent skip — that is the normal, expected case, not a broken
    install. NEVER writes or deletes; purely diagnostic, like the
    de-scoped-rule sweep and lint_rule_overscope(). Wired into
    `_run_doctor()`, which calls `lint_installed_divergence(cfg)` immediately
    after the Stage 8 sweep call so the bare `/planwise doctor` emits this
    report too; the caller's all-clear line ("All installed rules
    match shipped") must print ONLY when this returns `[]` — i.e. nothing
    diverged AND nothing was unverifiable/not-analyzed.

    Each finding is a dict:
      {path, kind ("rule"), classification ("SUBSET" |
       "HAS_UNIQUE" | "NOT_ANALYZED" | "UNVERIFIABLE"), line_count,
       approx_tokens (=line_count*13), recommendation}
    """
    rules_dst_dir = cfg.project_root / ".claude" / "rules" / "planwise"
    refs_dir = cfg.plugin_root / "references"

    def _check(dst: Path, src: Path, kind: str, norm) -> dict | None:
        if not dst.is_file():
            return None   # not installed — nothing to check, not a broken install

        # utf-8-sig: mirrors the artifact refresh writer's own read encoding
        # (see upgrade_artifacts()) so a leading BOM cannot defeat the
        # frontmatter-anchored comparison and falsely report a divergence.
        try:
            installed_raw = dst.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            # A non-UTF-8 (or otherwise unreadable) installed file must
            # never crash the always-exit-0 doctor path — report it as
            # unverifiable instead of letting the exception escape.
            return {"path": str(dst), "kind": kind, "classification": "UNVERIFIABLE",
                    "line_count": 0, "approx_tokens": 0,
                    "recommendation": f"unreadable ({exc}) — cannot verify divergence"}

        line_count = installed_raw.count("\n") + (0 if installed_raw.endswith("\n") else 1)
        base = {"path": str(dst), "kind": kind,
                "line_count": line_count, "approx_tokens": line_count * 13}

        if not src.is_file():
            # Missing shipped reference = a broken/partial install — an
            # explicit unverifiable row, never a silent skip that would let
            # the caller's all-clear line print over it.
            return {**base, "classification": "UNVERIFIABLE",
                    "recommendation": "shipped reference unavailable — cannot verify divergence"}
        try:
            shipped_raw = src.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            return {**base, "classification": "UNVERIFIABLE",
                    "recommendation": f"shipped reference unreadable ({exc}) — cannot verify divergence"}

        inst_norm, ship_norm = norm(installed_raw), norm(shipped_raw)
        if inst_norm == ship_norm:
            return None

        v = _classify_diverged(inst_norm, ship_norm)
        notes = getattr(v, "notes", "") or ""

        if _verdict_not_analyzed(v):
            # Degraded stand-in (structural_compare unavailable at call
            # time) — no analysis actually ran. Must NOT be reported as a
            # confident HAS_UNIQUE recommendation; mirrors the migrate/
            # upgrade NOT-analyzed notice convention.
            return {**base, "classification": "NOT_ANALYZED",
                    "recommendation": "NOT analyzed — structural comparison unavailable; "
                                       "diff it against references/ before acting manually"}

        if is_subset(v):
            if notes:
                # Non-empty notes = the matcher tolerated installed-only
                # content (e.g. sub-noise-floor fragments) — the writer's
                # own auto-adopt gate (`is_subset(verdict) and not
                # verdict.notes`) does NOT fire here; /planwise upgrade
                # instead routes this file through the customization-bearing
                # transfer-then-adopt (or preserve) gate, never an
                # unconditional auto-adopt.
                recommendation = (
                    "recommend /planwise upgrade — installed-only content flagged "
                    f"({notes}); upgrade will transfer it (or preserve it in place, "
                    "depending on upgrade.customization_handoff) before adopting "
                    "shipped, not auto-adopt unconditionally"
                )
            else:
                recommendation = "recommend /planwise upgrade (auto-adopts shipped)"
            return {**base, "classification": "SUBSET", "recommendation": recommendation}

        # HAS_UNIQUE — re-home per the rule decide-callout.
        recommendation = 're-home per the "Choosing a Home for a Rule Customization" decide callout'
        return {**base, "classification": "HAS_UNIQUE", "recommendation": recommendation}

    findings: list[dict] = []
    for filename, _paths_template in INSTALLED_RULES:
        row = _check(rules_dst_dir / filename, refs_dir / filename, "rule", normalize_rule_for_diff)
        if row:
            findings.append(row)
    return findings


def _run_prune_stale(cfg: "InitConfig") -> int:
    """WRITER (opt-in): delete ONLY the REMOVABLE stale de-scoped rules, log to PRUNED.md.

    Explicit opt-in companion to the read-only --doctor Stage 8 sweep. Runs
    the plugin version-state gate first (mirroring _run_doctor): an
    uninitialized or version-drifted install refuses to prune and returns 0
    with the tree untouched. On a gate-ok install it runs
    sweep_stale_descoped_rules(cfg), unlinks every REMOVABLE finding (never a
    PRESERVE / RELOCATE one), and writes the full disposition (removed +
    preserved + why) to a per-run, never-overwritten folder:
    {planwise_root}/upgrade-backups/prune-{YYYY-MM-DD}/PRUNED.md, or
    prune-{YYYY-MM-DD}-2/, -3/, ... when a folder for today already exists (a
    second run the same day never clobbers an earlier run's log). Before each
    deletion, a pre-image of the file is copied into that same prune folder
    alongside PRUNED.md, so a prune is recoverable; a failed backup copy means
    the file is left in place rather than deleted. A failed unlink after a
    successful backup is reported as REMOVE_FAILED (not REMOVABLE) and its
    orphan backup copy is removed. Exits 0.
    """
    gate = _doctor_version_gate(cfg)
    if gate["state"] != "ok":
        print(gate["report"])
        print()
        print("Nothing pruned — see the version-state gate above.")
        return 0

    findings = sweep_stale_descoped_rules(cfg)
    removable = [f for f in findings if f["verdict"] == "REMOVABLE"]
    kept = [f for f in findings if f["verdict"] != "REMOVABLE"]

    today = datetime.date.today().isoformat()  # YYYY-MM-DD
    backups_root = cfg.project_root / cfg.planwise_root / "upgrade-backups"
    out_dir = backups_root / f"prune-{today}"
    suffix = 2
    while out_dir.exists():
        out_dir = backups_root / f"prune-{today}-{suffix}"
        suffix += 1
    out_dir.mkdir(parents=True, exist_ok=True)

    removed: list[dict] = []
    for f in removable:
        try:
            src = Path(f["path"])
            (out_dir / f["filename"]).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            src.unlink()
            removed.append(f)
        except OSError as exc:
            f["verdict"] = "REMOVE_FAILED"
            f["reason"] = f"could not remove ({exc}) — left in place"
            kept.append(f)
            (out_dir / f["filename"]).unlink(missing_ok=True)

    lines = [f"# Stale de-scoped rule prune — {today}", ""]
    lines.append(f"## Removed ({len(removed)})")
    for f in removed:
        lines.append(f"- `{f['filename']}` (~{f['approx_tokens']} tokens) — {f['reason']}")
    lines.append("")
    lines.append(f"## Preserved ({len(kept)})")
    for f in kept:
        lines.append(f"- `{f['filename']}` [{f['verdict']}] — {f['reason']}")
    if removed:
        lines.append("")
        lines.append("Pre-image copies of every removed file above sit alongside this "
                      "log in this same folder, named after their original filename.")
    (out_dir / "PRUNED.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Pruned {len(removed)} stale de-scoped rule(s); "
          f"preserved {len(kept)}. Log: {out_dir / 'PRUNED.md'}")
    return 0


def _list_diverged_rows(cfg: "InitConfig") -> list[dict]:
    """Read-only: return the diverged rule minority as a list of dict rows.

    Walks DESCOPED_RULES and INSTALLED_RULES present on disk; compares
    installed vs shipped using the SAME normalization the writer uses
    (`normalize_rule_for_diff()`). A row is emitted only when the bodies
    differ — the byte/normalized-identical majority is skipped and never
    reaches the primitive. Stable-sorted by (kind, filename) so a downstream
    fan-out batch is reproducible. Returns `[]` when nothing diverges. Never
    writes or deletes anything; a per-file OSError is skipped rather than
    raised so one unreadable file cannot hide the rest of the diverged set.
    """
    refs_dir = cfg.plugin_root / "references"
    rules_dst_dir = cfg.project_root / ".claude" / "rules" / "planwise"

    rows: list[dict] = []

    for filename, _template in list(INSTALLED_RULES) + list(DESCOPED_RULES):
        dst = rules_dst_dir / filename
        src = refs_dir / filename
        if not dst.is_file() or not src.is_file():
            continue
        try:
            installed_raw = dst.read_text(encoding="utf-8")
            shipped_raw = src.read_text(encoding="utf-8")
        except OSError:
            continue
        if normalize_rule_for_diff(installed_raw) != normalize_rule_for_diff(shipped_raw):
            rows.append({
                "filename": filename,
                "kind": "rule",
                "installed": dst.relative_to(cfg.project_root).as_posix(),
                "shipped": src.relative_to(cfg.plugin_root).as_posix(),
            })

    rows.sort(key=lambda r: (r["kind"], r["filename"]))
    return rows


def _run_list_diverged(cfg: "InitConfig") -> int:
    """Execute the --list-diverged diagnostic. Prints json.dumps(rows) (an
    empty array when nothing diverges) and returns 0. Read-only — mutates
    nothing; the cheap gate that decides whether a fan-out is even worth
    spawning. See `_list_diverged_rows()` for the comparison logic.
    """
    print(json.dumps(_list_diverged_rows(cfg)))
    return 0


_FM_KEY_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(.*)$")

# UTF-8 byte-order mark as a code point — kept as chr() so this source file
# stays pure ASCII (an invisible literal BOM in source is exactly the bug
# class the guard below exists to defeat).
_BOM_CHAR = chr(0xFEFF)


def _split_frontmatter_block(content: str) -> "tuple[str, str] | None":
    """Split `content` into (frontmatter_text, body). BOM-tolerant.

    Returns None when there is no complete, well-delimited frontmatter block
    (missing opening `---`, or no closing delimiter). A leading UTF-8 BOM is
    stripped before the delimiter check so a BOM'd file cannot silently
    defeat frontmatter-anchored logic.
    """
    content = content.lstrip(_BOM_CHAR)
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end == -1:
        return None
    return content[4:end], content[end + 5:]


def _parse_frontmatter_map(frontmatter_text: str) -> "dict[str, str] | None":
    """Parse a frontmatter block into a {key: value-text} map, or None.

    A top-level `key: value` line maps to its stripped scalar value; any
    continuation lines (indented content, `- ` list items, block scalars)
    are appended verbatim with their newlines, so a multi-line value is
    detectable via `"\\n" in value` AND two different multi-line values
    never compare equal. Returns None when a line cannot be attributed to
    any key (structurally unparseable — the guard treats that as
    cannot-guard).
    """
    result: dict[str, str] = {}
    current_key: "str | None" = None
    for line in frontmatter_text.split("\n"):
        if not line.strip():
            continue
        m = _FM_KEY_LINE_RE.match(line)
        if m:
            current_key = m.group(1)
            result[current_key] = m.group(2).strip()
            continue
        if current_key is None:
            return None            # leading continuation with no key — unparseable
        result[current_key] += "\n" + line.rstrip()
    return result


def _verdict_not_analyzed(v) -> bool:
    """True for the degraded stand-in verdict `_classify_diverged` manufactures
    when structural_compare is unavailable at call time. The installed file
    was never actually analyzed, so the automated transfer-then-adopt path
    must NOT act on it — there is no verdict evidence to base an adoption on.
    The caller preserves the file in place and writes a shipped sidecar for
    manual merge (the always-safe degradation).

    Detection is by the explicit `source == _DEGRADED_VERDICT_SOURCE` marker
    ONLY — never by verdict shape. A genuine verdict (inline primitive or
    agent-sourced) that happens to be HAS_UNIQUE with empty unique_blocks and
    non-empty notes must NOT match: it carries real analysis evidence and
    routes through the normal customization-bearing disposition.
    """
    return getattr(v, "source", "") == _DEGRADED_VERDICT_SOURCE


def _transfer_customization(
    cfg: "InitConfig",
    filename: str,
    kind: str,
    installed_raw: str,
    verdict: "StructuralVerdict",
    from_version: str,
    to_version: str,
) -> "Path | None":
    """Move a customization-bearing installed file's content to a dormant
    preservation home BEFORE the writer adopts the shipped body over it.

    Per the automated-transfer-first upgrade policy: a notes-flagged SUBSET
    (installed-only content the matcher tolerated as noise) or a HAS_UNIQUE
    verdict (genuine customization) must never simply be overwritten — the
    customization is written to a separate file, the write is VERIFIED
    (read back and compared), and ONLY THEN may the caller adopt shipped in
    place. Writes the full installed body (the carrier of the customization —
    a granular per-block extract is not available at this layer) to
    ``{planwise_root}/upgrade-transfers/{from}-to-{to}/{filename}`` (beside
    ``upgrade-backups/``), alongside a minimal generic provenance header
    (source filename, kind, upgrade pair, date, verdict summary). The
    transfer file is a dormant preservation document — it lives OUTSIDE
    ``.claude/rules/`` so it is NEVER loaded as a rule and can never collide
    with the managed tree (including on a project literally named
    "planwise"). Promotion into an active ``.claude/rules/<project>/`` rule
    with real ``paths:`` scoping is an interactive, opt-in handler action.
    Never clobbers a pre-existing file at the target (e.g. from a prior
    interrupted run) — collisions are uniquified with a numeric loop
    (``{stem}-{from}-to-{to}``, then ``-2``, ``-3``, ...) until a
    non-existent name is found.

    Returns the transfer file Path on a verified success, or None on ANY
    failure (OSError writing or reading back, or a content mismatch on
    read-back — a filesystem lie is never trusted). The caller MUST treat
    None as "do not adopt/remove; preserve the installed file in place and
    report."
    """
    target_dir = (
        cfg.project_root / cfg.planwise_root / "upgrade-transfers"
        / f"{from_version}-to-{to_version}"
    )
    target = target_dir / filename
    if target.exists():
        stem, suffix = target.stem, target.suffix
        candidate = target_dir / f"{stem}-{from_version}-to-{to_version}{suffix}"
        counter = 2
        while candidate.exists():
            candidate = (
                target_dir / f"{stem}-{from_version}-to-{to_version}-{counter}{suffix}"
            )
            counter += 1
        target = candidate

    unique_blocks = getattr(verdict, "unique_blocks", None) or []
    notes = getattr(verdict, "notes", "") or ""
    header_lines = [
        "---",
        f"source_filename: {filename}",
        f"source_kind: {kind}",
        f"upgrade: {from_version} -> {to_version}",
        f"transferred: {date.today().isoformat()}",
        f"classification: {getattr(verdict, 'classification', 'HAS_UNIQUE')}",
    ]
    if unique_blocks:
        header_lines.append(f"unique_blocks: {unique_blocks!r}")
    if notes:
        header_lines.append(f"notes: {notes!r}")
    header_lines.append("---")
    provenance = (
        "\n".join(header_lines) + "\n\n"
        f"# Transferred customization: {filename}\n\n"
        "This file was auto-transferred from the installed copy before a "
        f"plugin upgrade ({from_version} -> {to_version}) adopted the shipped "
        "body in its place. Review and re-home the content below (port to a "
        "project-local rule, re-scope, or upstream the change), then delete "
        "this file once it is no longer needed.\n\n---\n\n"
    )
    transfer_text = provenance + installed_raw

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(transfer_text, encoding="utf-8")
        if target.read_text(encoding="utf-8") != transfer_text:
            return None
    except OSError:
        return None
    return target


def upgrade_artifacts(
    cfg: "InitConfig",
    manifest: dict,
    from_version: str,
    to_version: str,
) -> tuple[list[str], list[str], list[tuple[str, str]], list[str], list[str], list[tuple[str, str]]]:
    """Refresh artifacts whose upgrade_behavior is `refresh_or_sidecar`.

    Returns a 6-tuple:
      refreshed: list of destination paths overwritten cleanly (includes every
        `transferred` entry below — its customization was moved out first)
      unchanged: list of destination paths whose installed body already matched the shipped body
      conflicts: list of (destination_path, sidecar_path) tuples — installed body diverged
        and was not adopted: the customization transfer-first write FAILED, the verdict was
        the degraded not-analyzed stand-in (structural_compare unavailable — no evidence to
        adopt on), a pre-image backup could not be written (failed backup = no destructive
        write), the adoption write itself failed after a verified transfer, or
        `upgrade.customization_handoff` is `report`/`report+issue` (conservative mode: a
        customization-bearing file is preserved in place, never auto-transferred). The file
        is left untouched and a shipped sidecar written for manual merge
      untracked: list of destination paths found in the install dirs but NOT in the manifest allowlist
      refreshed_subsets: subset of `refreshed` whose entries were auto-adopted because the
        installed body was a stale SUBSET of the (grown) shipped body (rules: any confidence;
        agents: exact/contained, or reorg-confidence via the frontmatter-preservation guard) —
        surfaced separately so the caller can print a "N were stale subsets, auto-adopted
        shipped" banner sub-line
      transferred: list of (destination_path, transfer_path) tuples — a customization-bearing
        verdict (HAS_UNIQUE or notes-flagged subset) whose content was VERIFIED-written to
        `transfer_path` (a dormant preservation file under
        `{planwise_root}/upgrade-transfers/{from}-to-{to}/`) before shipped was adopted at
        destination_path; see `_transfer_customization()`

    Config gate (`upgrade.customization_handoff`, read via `get_upgrade_config()`):
    `report+relocate` (the shipped template default) enables the automated
    transfer-then-adopt path below; `report` (the absent-key fallback) and
    `report+issue` (whose extra meaning — gh-issue routing — is handler-side only)
    are conservative for disposition purposes: customization-bearing files are
    preserved in place + sidecar'd, with NO transfer and NO adoption.

    Destructive gates: rules refresh on `is_subset` with empty verdict notes (the project
    paths: line is re-applied via update_frontmatter). Agents are overwritten whole-file:
    they auto-adopt on `is_safe_to_remove` (exact/contained, no notes) unchanged, OR on a
    pure reorg-confidence subset (no notes) via the frontmatter-preservation guard —
    detect-don't-guess: the guard splices a customized single-line model:/tools:/maxTurns:
    pin into shipped's frontmatter, and returns None (routing the file to the
    customization-bearing path instead) for ANY frontmatter delta it cannot provably
    preserve (non-guarded keys, block-style values, BOM'd/unparseable frontmatter). Any
    OTHER divergence (HAS_UNIQUE, or any confidence level whose notes flag tolerated
    installed-only content) is customization-bearing: under `report+relocate`,
    `_transfer_customization()` moves the content to the upgrade-transfers/ preservation
    file, verifies the write, and ONLY THEN adopts shipped in place. Carve-outs fall back
    to the conservative preserve + sidecar branch: a FAILED transfer (never adopt/remove
    without a verified transfer), the degraded not-analyzed stand-in verdict
    (`_verdict_not_analyzed()` — analysis never ran, so there is nothing to adopt on), a
    failed pre-image backup, and a failed adoption write.

    Destructive-write ordering at every adoption site: pre-image backup FIRST
    (`_write_backup_preimage()`; failure aborts the adoption), THEN the adoption write,
    and ONLY on its success the DISPOSITIONS.md row (`_append_disposition_log()`) and
    result bookkeeping — a failed write can never leave a false log row. An adoption
    removes the sidecar it obsoletes. A per-file OSError is contained (stderr warning,
    file left untouched) — the loops always complete.
    """
    refreshed: list[str] = []
    unchanged: list[str] = []
    conflicts: list[tuple[str, str]] = []
    untracked: list[str] = []
    refreshed_subsets: list[str] = []
    transferred: list[tuple[str, str]] = []

    conflict_dir = (
        cfg.project_root / cfg.planwise_root / "upgrade-conflicts"
        / f"{from_version}-to-{to_version}"
    )

    # verdicts.json (if the interactive fan-out produced one) supersedes the
    # inline primitive per-file — loaded once, looked up per diverged file.
    verdicts = _load_verdicts_cache(cfg, from_version, to_version)

    # `upgrade.customization_handoff` gates the automated transfer-then-adopt
    # path. Only the explicit `report+relocate` value (the shipped template
    # default) enables it; `report` (also the absent-key fallback) and
    # `report+issue` (extra gh-issue meaning is handler-side) stay
    # conservative: preserve in place + sidecar, no transfer, no adoption.
    handoff = get_upgrade_config(_load_raw_config(cfg))["customization_handoff"]
    relocate_enabled = handoff == "report+relocate"

    def _write_conflict_sidecar(dst: Path, sidecar_dst: Path, shipped_raw: str) -> None:
        sidecar_dst.parent.mkdir(parents=True, exist_ok=True)
        sidecar_dst.write_text(shipped_raw, encoding="utf-8")
        conflicts.append((str(dst), str(sidecar_dst)))

    # --- planwise_rules ---
    refs_dir = cfg.plugin_root / "references"
    rules_dst_dir = cfg.project_root / ".claude" / "rules" / "planwise"

    for filename, paths_template in INSTALLED_RULES:
        src = refs_dir / filename
        dst = rules_dst_dir / filename
        try:
            # utf-8-sig: a leading BOM must not defeat the frontmatter-anchored
            # comparison/guard helpers (see the comparator's non-substantive
            # framing rules — BOM is never a customization).
            shipped_raw = src.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            print(f"  Warning: shipped reference not found: {src}", file=sys.stderr)
            continue

        try:
            installed_raw = dst.read_text(encoding="utf-8-sig") if dst.exists() else None

            if installed_raw is None:
                # Fresh install — write via update_frontmatter() to set paths:.
                paths_value = resolve_rule_paths_value(cfg, paths_template)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(update_frontmatter(shipped_raw, paths_value), encoding="utf-8")
                refreshed.append(str(dst))
            elif normalize_rule_for_diff(shipped_raw) == normalize_rule_for_diff(installed_raw):
                # Bodies match after stripping per-project paths: — no rewrite needed.
                unchanged.append(str(dst))  # FAST PATH — primitive NOT called
            else:
                verdict = _classify_diverged(
                    normalize_rule_for_diff(installed_raw),
                    normalize_rule_for_diff(shipped_raw),
                    override=_load_verdict_override(verdicts, filename, installed_raw),
                )
                sidecar_dst = (
                    conflict_dir / ".claude" / "rules" / "planwise" / f"{filename}.new")
                if is_subset(verdict) and not (getattr(verdict, "notes", "") or ""):
                    # Stale subset — adopt shipped in place, preserve the project
                    # paths:. Non-empty notes = the matcher tolerated installed-only
                    # content (sub-noise-floor fragments) — that flips to the
                    # customization-bearing branch below: an overwrite must not
                    # destroy a short customization without moving it first.
                    # Failed backup = no destructive write.
                    if not _write_backup_preimage(cfg, from_version, to_version, dst):
                        _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                    else:
                        preserved_paths = (
                            _extract_paths_value(installed_raw)
                            or resolve_rule_paths_value(cfg, paths_template))
                        dst.write_text(
                            update_frontmatter(shipped_raw, preserved_paths), encoding="utf-8")
                        _append_disposition_log(
                            cfg, from_version, to_version, dst, "auto-adopted shipped",
                            "installed rule body was a stale subset of the grown shipped body")
                        refreshed.append(str(dst))
                        refreshed_subsets.append(str(dst))     # banner sub-count
                        if sidecar_dst.exists():
                            # A prior interrupted run flagged this file — the adoption
                            # resolves that conflict; drop the obsoleted sidecar so a
                            # stale INDEX row cannot invite merging outdated content back.
                            sidecar_dst.unlink()
                elif _verdict_not_analyzed(verdict):
                    # Degraded stand-in — the file was never analyzed, so the
                    # automated transfer-then-adopt has no verdict evidence to
                    # act on. Preserve in place + shipped sidecar (always safe).
                    _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                elif not relocate_enabled:
                    # customization_handoff is report/report+issue — conservative
                    # mode: never auto-transfer or adopt over a customization-
                    # bearing verdict. Preserve in place + shipped sidecar.
                    _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                else:
                    # HAS_UNIQUE or noise-flagged subset — customization-bearing.
                    # Ordering: transfer + verify -> pre-image backup (abort on
                    # failure) -> adoption write -> ONLY on success the
                    # DISPOSITIONS row + transferred bookkeeping. A failed
                    # transfer or backup must never destroy the only copy; a
                    # failed adoption write must never leave a false log row.
                    transfer_path = _transfer_customization(
                        cfg, filename, "rule", installed_raw, verdict,
                        from_version, to_version,
                    )
                    if transfer_path is None or not _write_backup_preimage(
                            cfg, from_version, to_version, dst):
                        _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                    else:
                        preserved_paths = (
                            _extract_paths_value(installed_raw)
                            or resolve_rule_paths_value(cfg, paths_template))
                        try:
                            dst.write_text(
                                update_frontmatter(shipped_raw, preserved_paths),
                                encoding="utf-8")
                        except OSError as exc:
                            print(
                                f"  Warning: could not adopt shipped at {dst}: {exc}; "
                                f"preserved in place (customization already transferred "
                                f"to {transfer_path})",
                                file=sys.stderr,
                            )
                            _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                        else:
                            _append_disposition_log(
                                cfg, from_version, to_version, dst,
                                "adopted shipped (customization transferred)",
                                f"customization transferred to {transfer_path}")
                            refreshed.append(str(dst))
                            transferred.append((str(dst), str(transfer_path)))
                            if sidecar_dst.exists():
                                sidecar_dst.unlink()
        except OSError as exc:
            # Per-file containment: a read-only/locked file must not abort the
            # whole refresh mid-loop with earlier dispositions unreported.
            print(
                f"  Warning: could not upgrade {dst}: {exc}; installed file left untouched",
                file=sys.stderr,
            )

    # --- Untracked detection ---
    rule_allowlist = {r[0] for r in INSTALLED_RULES}

    for md_file in rules_dst_dir.glob("*.md"):
        if md_file.name not in rule_allowlist:
            untracked.append(str(md_file))

    # --- Conflict INDEX.md ---
    if conflicts:
        index_path = conflict_dir / "INDEX.md"
        lines = [
            f"# Plugin upgrade conflicts: {from_version} -> {to_version}",
            "",
            "| # | Installed file | Sidecar | Notes |",
            "|---|---------------|---------|-------|",
        ]
        for i, (dst_path, sidecar_path) in enumerate(conflicts, start=1):
            lines.append(f"| {i} | {dst_path} | {sidecar_path} | (diff and merge manually) |")
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif conflict_dir.exists():
        # No conflicts this run: if a prior interrupted run's sidecars were all
        # resolved (adopted or hand-merged+deleted), retire the stale INDEX so it
        # cannot instruct merging content the adoption already superseded.
        index_path = conflict_dir / "INDEX.md"
        if index_path.exists() and not any(conflict_dir.rglob("*.new")):
            index_path.unlink()

    return refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred


def _bump_plugin_version(config_path: Path, new_version: str) -> None:
    """Update the plugin_version: line in config.yaml in-place, preserving formatting.

    Prefers a line-level edit over PyYAML round-trip so the user's comment
    layout is preserved. Falls back to PyYAML re-emit if the line isn't found
    (e.g., legacy config that never got the migrate-added key).
    """
    text = config_path.read_text(encoding="utf-8")
    pattern = re.compile(r'^(\s*plugin_version:\s*)("[^"]*"|\S+)\s*$', re.MULTILINE)
    if pattern.search(text):
        new_text = pattern.sub(rf'\1"{new_version}"', text)
        config_path.write_text(new_text, encoding="utf-8")
        return
    # Fallback — append the key under the existing top-level set.
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{config_path} is not a YAML mapping — cannot pin version.")
    data["plugin_version"] = new_version
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def _flip_token_saver_on(config_path: Path) -> bool:
    """Flip `token_saver: false` to `true` in the config, comment-preserving.

    Targets the bare `token_saver:` key only — never touches `token_saver_*`
    measured lines (they have a different key suffix before the colon).
    Only flips false -> true; an existing `true` is a no-op and is never
    reverted to false. Idempotent: re-running on an already-true config
    returns False without writing the file.

    Returns True when the value was changed, False when it was already true
    or the key was absent (so the caller can decide whether to print a banner).
    """
    text = config_path.read_text(encoding="utf-8")
    # The pattern anchors on line boundaries (MULTILINE) and matches exactly
    # `token_saver:` followed by optional whitespace, the literal `false`, and
    # an optional trailing inline comment. `token_saver_session_target:` etc.
    # cannot match because the underscore separator comes before the colon.
    pattern = re.compile(
        r'^(\s*token_saver:[ \t]*)false([ \t]*(?:#[^\n]*)?)$',
        re.MULTILINE,
    )
    if not pattern.search(text):
        return False
    new_text = pattern.sub(r'\g<1>true\g<2>', text)
    config_path.write_text(new_text, encoding="utf-8")
    return True


def _run_upgrade(cfg: "InitConfig") -> int:
    """Execute the --upgrade flow and print a banner. Returns exit code."""
    if not HAS_YAML:
        print(
            "Upgrade failed: PyYAML is required for --upgrade. Install with `pip install pyyaml`.",
            file=sys.stderr,
        )
        return 2

    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    if not config_path.exists():
        print(
            f"Upgrade failed: {config_path} does not exist — run /planwise init before --upgrade.",
            file=sys.stderr,
        )
        return 2

    # 1. Read pinned vs. target version.
    try:
        user_cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"Upgrade failed: cannot parse {config_path}: {exc}", file=sys.stderr)
        return 2
    pinned_version = str(user_cfg.get("plugin_version", "0.0.0"))
    target_version = cfg.plugin_version

    if pinned_version == target_version:
        print(f"Plugin version: {pinned_version}")
        print("Already up to date.")
        return 0

    print(f"Plugin upgrade: {pinned_version} -> {target_version}")
    print()

    # 2. Run additive config merge.
    try:
        _, added, _present = migrate_config(cfg)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Upgrade failed during migrate phase: {exc}", file=sys.stderr)
        return 2
    if added:
        print("Config keys added:")
        for key in added:
            print(f"  + {key}")
        print()

    # 2a. Honor --token-saver: flip context.token_saver false->true when the
    # user opts in this run. Runs AFTER migrate so the key is guaranteed to be
    # present (migrate seeds it as "false" when absent). Never flips true->false;
    # idempotent when the config already reads true.
    if cfg.token_saver and _flip_token_saver_on(config_path):
        print("Token Saver enabled.")
        print()

    # 2b. Backfill lessons scaffolding (index seed + categorization file).
    # Fresh init renders these, but the legacy fresh-init-only path meant an
    # upgrade-adopted project never got 00-Categorization-By-Domain.md — the
    # file that hard-gates /planwise lessons curate and promote-batch. Runs
    # AFTER migrate_config so a freshly-migrated `categorization:` block is
    # picked up; idempotent and non-destructive — a no-op (silent) when both
    # files already exist, preserving any user-customised content verbatim.
    lessons_boot = bootstrap_lessons_artifacts(cfg)
    _emit_lessons_bootstrap_banner(lessons_boot)

    # 3. Refresh artifacts.
    manifest = load_artifact_manifest(cfg.plugin_root)
    refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = upgrade_artifacts(
        cfg, manifest, pinned_version, target_version
    )

    if refreshed:
        print(f"Refreshed: {len(refreshed)}")
        if refreshed_subsets:
            print(
                f"  ({len(refreshed_subsets)} were stale subsets, auto-adopted shipped)"
            )
        for r in refreshed:
            print(f"  + {r}")
    if unchanged:
        print(f"Unchanged: {len(unchanged)} (installed body already matches shipped)")
    if untracked:
        print(f"Untracked preserved: {len(untracked)}")
        for u in untracked:
            print(f"  = {u}")
    print()

    if transferred:
        print(f"Customizations transferred before adoption: {len(transferred)}")
        for dst, transfer_path in transferred:
            print(f"  ~ {dst}")
            print(f"      moved to: {transfer_path}")
        print("  Review each transferred file and re-home it (project-local rule, "
              "re-scope, or upstream the change).")
        print()

    if conflicts:
        print("Conflicts (preserved in place — action required):")
        for dst, sidecar in conflicts:
            print(f"  ! {dst}")
            print("      reason:      installed body diverged and was not auto-adopted "
                  "(conservative handoff mode, a transfer/backup/adoption write failed, "
                  "or the file could not be analyzed)")
            print(f"      sidecar:     {sidecar}")
            print("      remediation: diff the sidecar against the installed file, merge manually, then delete the .new")
        index_path = (
            cfg.project_root / cfg.planwise_root / "upgrade-conflicts"
            / f"{pinned_version}-to-{target_version}" / "INDEX.md"
        )
        print(f"  See {index_path} for the full conflict list.")
        print()

    # 4. De-scope migration — remove install-set rules that are now
    # handler-loaded, but only the untouched copies. Runs AFTER artifact
    # refresh and BEFORE the version bump so it executes exactly once, on the
    # upgrade that crosses RESCOPE_MIGRATION_VERSION.
    migration = migrate_installed_rules(cfg, pinned_version, target_version)
    if migration["removed"]:
        print("De-scoped rules removed (now handler-loaded from references/):")
        for entry in migration["removed"]:
            print(f"  - {entry}")
        print()
    if migration["preserved"]:
        print("De-scoped rules preserved (customized — action recommended):")
        for entry in migration["preserved"]:
            print(f"  ! {entry}")
        print()

    # 4b. Retire the consumed verdict cache. A verdicts.json entry is bound to
    # the exact (upgrade pair, installed bytes) it was computed against; once
    # this run has consumed it, leaving it in place would let a stale verdict
    # fire on a later re-run or a different pair. Renamed (not deleted) so the
    # analysis remains inspectable next to INDEX.md.
    verdicts_path = (
        cfg.project_root / cfg.planwise_root / "upgrade-conflicts"
        / f"{pinned_version}-to-{target_version}" / "verdicts.json"
    )
    if verdicts_path.exists():
        try:
            consumed_path = verdicts_path.with_name("verdicts.json.consumed")
            if consumed_path.exists():
                consumed_path.unlink()
            verdicts_path.rename(consumed_path)
            print(f"Verdict cache consumed: renamed to {consumed_path.name}")
            print()
        except OSError as exc:
            print(
                f"  Warning: could not retire consumed verdict cache {verdicts_path}: {exc}",
                file=sys.stderr,
            )

    # 5. Post-upgrade advisory: flag any installed rule still scoped to
    # plan/backlog/lessons globs (read-only — never mutates).
    overscoped = lint_rule_overscope(cfg)
    if overscoped:
        total_tokens = sum(item["approx_tokens"] for item in overscoped)
        print("Advisory — rules scoped to plan/backlog/lessons globs:")
        for item in overscoped:
            print(
                f"  ~ {item['path']} ({item['line_count']} lines, "
                f"~{item['approx_tokens']} tokens; matches {item['matched_glob']})"
            )
            print("      hint: re-scope to code paths or convert to a handler-loaded reference")
        print(f"  Total always-on injected budget from flagged rules: ~{total_tokens} tokens")
        print()

    # 6. Commit point: bump plugin_version: in config.yaml LAST.
    _bump_plugin_version(config_path, target_version)
    print(f"Plugin version pinned: {target_version}")
    print()
    print("Upgrade complete.")
    return 0


def _run_migrate(cfg: InitConfig) -> int:
    """Execute the --migrate flow and print a focused report. Returns exit code."""
    try:
        path, added, present = migrate_config(cfg)
    except FileNotFoundError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 2

    print(f"Migration target: {path}")
    if added:
        print("Top-level keys added:")
        for key in added:
            print(f"  + {key}")
    else:
        print("Top-level keys added: (none — config already up to date)")
    if present:
        print("Top-level keys already present (preserved):")
        for key in present:
            print(f"  = {key}")
    print()
    print("Migration complete.")
    return 0


def _resolve_doctor_config_path(cfg: "InitConfig") -> "Path | None":
    """Locate config.yaml for the version-state gate, mirroring the doctor
    Config Gate resolution: the default planwise root first, then any
    `*/config.yaml` one level down from the project root. Returns None when no
    config is found (uninitialized install). Read-only."""
    primary = cfg.project_root / cfg.planwise_root / "config.yaml"
    if primary.exists():
        return primary
    for candidate in sorted(cfg.project_root.glob("*/config.yaml")):
        return candidate
    return None


def _read_pinned_plugin_version(config_path: "Path") -> str:
    """Read the pinned top-level plugin_version from config.yaml WITHOUT
    requiring PyYAML, so the read-only doctor gate works even when yaml is
    unavailable. Returns "0.0.0" (the never-pinned sentinel, matching
    read_plugin_version) when the key is absent or the file can't be read."""
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    m = re.search(r'^\s*plugin_version:\s*("([^"]*)"|(\S+))\s*$', text, re.MULTILINE)
    if not m:
        return "0.0.0"
    return (m.group(2) if m.group(2) is not None else m.group(3)).strip()


def _doctor_version_gate(cfg: "InitConfig") -> dict:
    """Read-only plugin version-state preflight for /planwise doctor.

    Compares the project's pinned plugin_version against the installed plugin
    (cfg.plugin_version, from read_plugin_version()). Returns a dict with:
      state:  "uninitialized" (no config.yaml)     -> recommend /planwise init
              "drift"         (pinned != installed) -> recommend /planwise upgrade
              "ok"            (pinned == installed)  -> proceed with diagnostics
      report: the lines to print verbatim.
    Never mutates anything — doctor only recommends; init/upgrade are the only
    writers (they bump the pin)."""
    installed = cfg.plugin_version
    config_path = _resolve_doctor_config_path(cfg)

    lines = ["Plugin version-state gate"]
    if config_path is None:
        lines.append(f"  ! Not initialized — no config.yaml under {cfg.project_root}.")
        lines.append("    Recommend: /planwise init")
        return {"state": "uninitialized", "report": "\n".join(lines)}

    pinned = _read_pinned_plugin_version(config_path)
    if pinned != installed:
        lines.append(f"  ! Version drift — pinned {pinned} != installed {installed}.")
        lines.append("    Recommend: /planwise upgrade")
        return {"state": "drift", "report": "\n".join(lines)}

    lines.append(f"  plugin version {installed} — up to date")
    return {"state": "ok", "report": "\n".join(lines)}


def _run_doctor(cfg: "InitConfig") -> int:
    """Run the read-only overscope linter + stale-rule sweep and print a report.

    Standalone diagnostic — does not require or perform an upgrade. Walks the
    installed rules, flags any scoped to plan/backlog/lessons globs, and prints
    one row per flagged rule with its size, a re-scope hint, and a total
    always-on injected-budget line. Then runs Stage 8, the post-boundary stale
    de-scoped rule sweep (sweep_stale_descoped_rules()), and prints its report
    too — always-on, independent of whether any rule was overscoped. Then runs
    Stage 9, the installed rule divergence lint (lint_installed_divergence()),
    and prints its report — also always-on. Always exits 0 (diagnostic, not a gate).

    Runs the plugin version-state gate FIRST (always-on, independent of Token
    Saver): an uninitialized or version-drifted install is surfaced with a
    remediation (init / upgrade) and the function returns before linting — no
    point auditing a stale rule surface. Read-only throughout; init/upgrade
    (and the separate opt-in `--prune-stale` writer) are the only writers.
    """
    gate = _doctor_version_gate(cfg)
    print(gate["report"])
    print()
    if gate["state"] != "ok":
        return 0

    overscoped = lint_rule_overscope(cfg)
    print("planwise doctor — rule overscope report")
    print()
    if not overscoped:
        print("No overscoped rules found.")
        print("All installed rules are scoped to code paths (.claude/** or narrower).")
    else:
        total_tokens = sum(item["approx_tokens"] for item in overscoped)
        print(f"Flagged {len(overscoped)} rule(s) scoped to plan/backlog/lessons globs:")
        print()
        for item in overscoped:
            print(
                f"  ~ {item['path']} ({item['line_count']} lines, "
                f"~{item['approx_tokens']} tokens; matches {item['matched_glob']})"
            )
            print("      hint: re-scope to code paths or convert to a handler-loaded reference")
        print()
        print(f"Total always-on injected budget from flagged rules: ~{total_tokens} tokens")

    # Stage 8: post-boundary stale de-scoped rule sweep — read-only, always-on.
    print()
    print("planwise doctor — stale de-scoped rule sweep (post-boundary)")
    print()
    stale = sweep_stale_descoped_rules(cfg)
    if not stale:
        print("No stale de-scoped rules found — install is past the boundary and clean.")
    else:
        print("Stale de-scoped rules still installed under .claude/rules/planwise/:")
        for f in stale:
            mark = "!" if f["verdict"] == "PRESERVE" else "~"
            verdict_label = f["verdict"]
            if verdict_label == "RELOCATE":
                verdict_label += " (prefix-rename fingerprint)"
            print(f"  {mark} {f['filename']}   {verdict_label}")
            print(f"      size:    {f['line_count']} lines (~{f['approx_tokens']} tokens)")
            print(f"      reason:  {f['reason']}")
            if f["verdict"] == "REMOVABLE":
                print("      action:  remove with /planwise doctor --prune-stale")
            elif f["verdict"] == "PRESERVE":
                print("      action:  re-home to .claude/rules/<project>/<name>.md — do NOT delete")
            else:  # RELOCATE
                print("      action:  migrate to .claude/rules/<project>/<name>.md")
        removable = [f for f in stale if f["verdict"] == "REMOVABLE"]
        print()
        print(f"Total REMOVABLE always-on budget: ~{sum(f['approx_tokens'] for f in removable)} "
              f"tokens across {len(removable)} rule(s).")

    # Stage 9: installed rule divergence lint — read-only, always-on.
    print()
    print("planwise doctor — installed rule divergence lint")
    print()
    diverged = lint_installed_divergence(cfg)
    if not diverged:
        print("All installed rules match shipped — no divergence found.")
    else:
        mark_by_classification = {
            "SUBSET": "~", "HAS_UNIQUE": "!", "NOT_ANALYZED": "?", "UNVERIFIABLE": "?",
        }
        for f in diverged:
            mark = mark_by_classification.get(f["classification"], "!")
            print(f"  {mark} {f['path']}   {f['classification']}")
            print(f"      size:    {f['line_count']} lines (~{f['approx_tokens']} tokens)")
            print(f"      action:  {f['recommendation']}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Initialize planwise project structure")
    parser.add_argument("--name", default=None,
                        help="Project name. Required for init/--migrate/--upgrade; "
                             "optional for the read-only --doctor diagnostic.")
    parser.add_argument("--root", default="planwise", help="Planwise root directory")
    parser.add_argument("--plans-dir", default="Plans", help="Plans subdirectory name")
    parser.add_argument("--backlog-dir", default="Backlog", help="Backlog subdirectory name")
    parser.add_argument("--lessons-dir", default="LessonsLearned", help="Lessons subdirectory name")
    parser.add_argument("--scope", default=InstallScope.PROJECT,
                        choices=[s.value for s in InstallScope],
                        help="Install scope: project, user, or local (default: project)")
    parser.add_argument("--plan-tier", default="pro",
                        choices=sorted(PLAN_TIER_WINDOWS.keys()),
                        help="Claude plan tier: pro (200K context) or max (1M context). Default: pro.")
    parser.add_argument("--token-saver", action="store_true",
                        help="Enable the Token Saver budget engine in the project config "
                             "(sets context.token_saver: true). Applies to both init and "
                             "upgrade. Default off — the engine ships dormant and is "
                             "calibrated via /planwise calibrate.")
    parser.add_argument("--project-root", default=None, help="Project root (default: cwd)")
    parser.add_argument("--auto-from", default=None,
                        help="Subroutine mode: caller handler name (e.g., 'plan', 'review'). "
                             "Suppresses team-sharing prompt (Step 9) and replaces Step 10 banner "
                             "with a single line. Used by handlers when invoking init via "
                             "Auto-Init Fallback.")
    parser.add_argument("--migrate", action="store_true",
                        help="Idempotent mode: merge missing top-level keys from "
                             "config.yaml.template into an existing planwise/config.yaml "
                             "without overwriting user customisations. Does not create "
                             "directories, seeds, rules, or settings — use plain /planwise "
                             "init for those.")
    parser.add_argument("--upgrade", action="store_true",
                        help="Refresh installed rules and bump plugin_version: in "
                             "config.yaml after a plugin update.")
    parser.add_argument("--doctor", action="store_true",
                        help="Read-only diagnostic: scan installed rules and report any "
                             "still scoped to plan/backlog/lessons globs (always-on context "
                             "overscope), with size and a re-scope hint. Does not modify "
                             "anything and does not require --upgrade.")
    parser.add_argument("--list-diverged", action="store_true",
                        help="Read-only diagnostic: print a JSON array of installed rule "
                             "files whose body diverges from the plugin-shipped version "
                             "(filename, kind, installed path, shipped path). Prints [] when "
                             "none diverge. Does not modify anything and does not require --name.")
    parser.add_argument("--prune-stale", action="store_true",
                        help="WRITER (opt-in): delete the stale de-scoped rules that "
                             "--doctor's Stage 8 sweep marks REMOVABLE, logging every "
                             "removal to upgrade-backups/prune-<date>[-N]/PRUNED.md. "
                             "Never deletes a customized (PRESERVE) rule.")
    args = parser.parse_args()

    # --doctor, --list-diverged, and --prune-stale are read-only/self-scoped
    # diagnostics that do not use the project name; every other mode
    # (init / --migrate / --upgrade) requires it.
    if not args.doctor and not args.prune_stale and not args.list_diverged and not args.name:
        parser.error("--name is required (omit it only for the read-only --doctor "
                     "or --list-diverged diagnostics, or --prune-stale)")

    _plugin_root = get_plugin_root()
    cfg = InitConfig(
        project_name=args.name or "planwise",
        project_root=Path(args.project_root).resolve() if args.project_root else Path.cwd(),
        plugin_root=_plugin_root,
        planwise_root=args.root,
        plans_dir=args.plans_dir,
        backlog_dir=args.backlog_dir,
        lessons_dir=args.lessons_dir,
        install_scope=args.scope,
        plan_tier=args.plan_tier,
        plugin_version=read_plugin_version(_plugin_root),
        token_saver=args.token_saver,
    )

    if args.prune_stale:
        sys.exit(_run_prune_stale(cfg))

    if args.doctor:
        sys.exit(_run_doctor(cfg))

    if args.list_diverged:
        sys.exit(_run_list_diverged(cfg))

    if args.upgrade:
        if args.migrate:
            print("Note: --migrate is redundant when --upgrade is used (upgrade internally calls migrate).", file=sys.stderr)
        sys.exit(_run_upgrade(cfg))

    if args.migrate:
        sys.exit(_run_migrate(cfg))

    # Aggregated across producers; surfaced in the Step 10 banner.
    skipped: list[SkippedArtifact] = []

    print(f"Initializing planwise for '{cfg.project_name}'...")
    print()

    dirs = create_directories(cfg)
    print("Directories created:")
    for d in dirs:
        print(f"  + {d}")
    print()

    seeds = copy_seed_files(cfg)
    if seeds:
        print("Seed files installed:")
        for s in seeds:
            print(f"  + {s}")
    else:
        print("Seed files: already exist, skipped")
    print()

    result, config_rel = generate_config(cfg)
    if result == ConfigResult.CREATED:
        print(f"Configuration: + {config_rel}")
    elif result == ConfigResult.SKIPPED_EXISTS:
        print("Configuration: already exists, skipped")
    else:
        print("Configuration: warning - template not found")
        skipped.append(SkippedArtifact(
            artifact=config_rel,
            reason="config.yaml.template not found in plugin",
            consumer="all handlers (config gate)",
            remediation="Re-install the planwise plugin or run /planwise init from a clean plugin checkout.",
        ))
    print()

    # Lessons scaffolding (index seed + categorization file) via the shared
    # idempotent routine — the SAME entry point _run_upgrade() backfills from.
    # copy_seed_files() above already seeded the lessons index, so that
    # sub-step is a no-op here; the categorization banner below is unchanged.
    _lessons = bootstrap_lessons_artifacts(cfg)
    cat_result, cat_rel = _lessons.cat_result, _lessons.cat_rel
    if cat_result == ConfigResult.CREATED:
        print(f"Categorization: + {cat_rel}")
    elif cat_result == ConfigResult.CREATED_FROM_DEFAULT:
        print(f"Categorization: + {cat_rel} (rendered with default buckets — config.yaml `categorization:` block missing)")
        print("                  Add the block to customise buckets, or run --migrate to seed it from the template.")
    elif cat_result == ConfigResult.SKIPPED_EXISTS:
        print("Categorization: already exists, skipped")
    elif cat_result == ConfigResult.SKIPPED_NO_YAML:
        print("Categorization: skipped (PyYAML not installed)")
        skipped.append(SkippedArtifact(
            artifact=cat_rel,
            reason="PyYAML not installed (cannot read config.yaml from the script path)",
            consumer="/planwise lessons curate, /planwise lessons promote-batch",
            remediation="Install PyYAML (`pip install pyyaml`), or run /planwise init and let the handler's Step 5.1 fallback render the file via Read+Write.",
        ))
    else:  # SKIPPED_NO_TEMPLATE or SKIPPED_BAD_CONFIG (defensive)
        print("Categorization: skipped (config.yaml unparseable)")
        skipped.append(SkippedArtifact(
            artifact=cat_rel,
            reason="config.yaml could not be parsed (YAML error or unexpected structure)",
            consumer="/planwise lessons curate, /planwise lessons promote-batch",
            remediation=f"Fix YAML errors in {cfg.planwise_root}/config.yaml, then re-run /planwise init or `python init_project.py --migrate`.",
        ))
    print()

    rules = install_rules(cfg)
    if rules:
        print("Rules installed to .claude/rules/planwise/:")
        for r in rules:
            print(f"  + {r}")
    else:
        print("Rules: already exist, skipped")
    print()

    settings_path, plugin_dir = configure_settings(cfg)
    if settings_path:
        print(f"Settings configured ({cfg.install_scope} scope):")
        print(f"  + Agent Teams: {settings_path}")
        if plugin_dir:
            print(f"  + additionalDirectories: {plugin_dir}")
    else:
        print("Settings: skipped (see warning above)")
        skipped.append(SkippedArtifact(
            artifact=str(get_settings_path(cfg)),
            reason="settings.json contains invalid JSON",
            consumer="Agent Teams + plugin permissions (all handlers)",
            remediation=f"Fix the JSON in {get_settings_path(cfg)} and re-run /planwise init.",
        ))
    print()

    # Manifest-driven post-checks: load manifests/artifacts.yaml and surface
    # every artifact whose config key is absent and whose missing_key_behavior
    # is `migrate_only` or `warn_loud`. The manifest is the source of truth —
    # this loop reports whatever the manifest declares, so new artifact rows
    # become loud without any further changes to main().
    manifest = load_artifact_manifest(cfg.plugin_root)
    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    user_cfg: dict = {}
    if HAS_YAML and config_path.exists():
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                user_cfg = loaded
        except yaml.YAMLError:
            user_cfg = {}

    migrate_remediation = (
        f"Run `python {cfg.plugin_root.as_posix()}/scripts/init_project.py "
        f"--name \"{cfg.project_name}\" --migrate` to merge the block from the template."
    )

    for entry in manifest.get("artifacts", []):
        if not isinstance(entry, dict):
            continue
        behavior = entry.get("missing_key_behavior")
        if behavior not in {"migrate_only", "warn_loud"}:
            continue
        config_keys = entry.get("config_keys") or []
        if not config_keys:
            continue

        # An artifact is "missing its config" when any required top-level key
        # (the prefix before any `.`) is absent from the user's config.
        missing_top_keys = []
        for key_path in config_keys:
            if not isinstance(key_path, str):
                continue
            top_key = key_path.split(".", 1)[0]
            if top_key not in user_cfg and top_key not in missing_top_keys:
                missing_top_keys.append(top_key)

        if not missing_top_keys:
            continue

        consumers = entry.get("consumers") or []
        if isinstance(consumers, list):
            consumer_str = ", ".join(str(c) for c in consumers) or "downstream skills using this key"
        else:
            consumer_str = str(consumers)

        for top_key in missing_top_keys:
            artifact_label = entry.get("on_disk") or entry.get("id") or top_key
            artifact_label = (
                str(artifact_label)
                .replace("{planwise_root}", cfg.planwise_root)
                .replace("{plans_dir}", cfg.plans_dir)
                .replace("{backlog_dir}", cfg.backlog_dir)
                .replace("{lessons_dir}", cfg.lessons_dir)
                .replace("{settings_file}", str(get_settings_path(cfg)))
            )
            # If on_disk doesn't already mention the key, append it for clarity.
            if f"key: {top_key}" not in artifact_label:
                artifact_label = f"{cfg.planwise_root}/config.yaml (key: {top_key})"
            skipped.append(SkippedArtifact(
                artifact=str(artifact_label),
                reason=f"config.yaml has no `{top_key}:` block — likely a config that predates this key",
                consumer=consumer_str,
                remediation=migrate_remediation if behavior == "migrate_only" else
                            f"Add the `{top_key}:` block to {cfg.planwise_root}/config.yaml and re-run /planwise init.",
            ))

    # Plugin version drift detection — surfaces a SKIPPED row directing the
    # user at /planwise upgrade if their pinned plugin_version is older than
    # the currently-installed plugin. Independent of the manifest loop above
    # because the check is comparative (pinned vs. shipped), not a presence
    # check on a config key.
    pinned_version = str(user_cfg.get("plugin_version", "0.0.0"))
    if pinned_version != cfg.plugin_version:
        skipped.append(SkippedArtifact(
            artifact=f"{cfg.planwise_root}/config.yaml (key: plugin_version)",
            reason=(
                f"pinned plugin_version `{pinned_version}` is older than the installed plugin "
                f"`{cfg.plugin_version}` — installed rules may be stale"
            ),
            consumer="all handlers (rule and agent freshness)",
            remediation=(
                f"Run `python {cfg.plugin_root.as_posix()}/scripts/init_project.py "
                f"--name \"{cfg.project_name}\" --upgrade` (or `/planwise upgrade`) to refresh artifacts."
            ),
        ))

    if args.auto_from:
        print(f"Init complete — resuming /planwise {args.auto_from}…")
    else:
        _print_skipped_banner(skipped)
        print("Done!")


if __name__ == "__main__":
    main()
