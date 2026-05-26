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
    "context",
    "categorization",
]

import argparse
import dataclasses
import json
import re
import sys
from datetime import date
from enum import Enum
from pathlib import Path

from constants import InstallScope

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


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

    @property
    def context_window(self) -> int:
        return PLAN_TIER_WINDOWS[self.plan_tier]


def get_plugin_root() -> Path:
    """Return the plugin root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


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
    lessons_index = "00-Index-LessonsLearned.md"
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

    plans_path = f"{cfg.planwise_root}/{cfg.plans_dir}/**"
    all_paths = ", ".join([
        plans_path,
        f"{cfg.planwise_root}/{cfg.backlog_dir}/**",
        f"{cfg.planwise_root}/{cfg.lessons_dir}/**",
    ])

    rules = [
        ("agent-authoring.md", ".claude/agents/**"),
        ("skill-authoring.md", ".claude/skills/**"),
        ("rule-authoring.md", ".claude/rules/**"),
        ("session-planning-protocol.md", plans_path),
        ("session-plan-requirements.md", plans_path),
        ("session-context-budget.md", plans_path),
        ("session-execution-protocol.md", plans_path),
        ("scaffolding-hygiene.md", plans_path),
        ("discovery-and-exit-criteria.md", plans_path),
        ("ei-fidelity.md", plans_path),
        ("schema-pin-requirement.md", plans_path),
        ("task-content-fidelity.md", plans_path),
        ("agent-orchestration.md", all_paths),
        ("callout-conventions.md", all_paths),
        ("markdown-conventions.md", all_paths),
        ("verification-gates.md", plans_path),
        ("verify-against-shipped-artifact.md", plans_path),
    ]

    for filename, paths_value in rules:
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


def install_agents(cfg: InitConfig) -> list[str]:
    """Copy plugin's agents/ files into project's .claude/agents/ directory.

    This enables bare-name agent resolution in consumer projects for handlers
    that spawn agents by name (per PLG-017). Companion to the handler-side
    namespaced-spawn updates (`subagent_type: "planwise:plan-reviewer"`).

    Skips if destination exists. Returns list of installed agent filenames.
    """
    installed = []
    agents_src_dir = cfg.plugin_root / "agents"
    agents_dst_dir = cfg.project_root / ".claude" / "agents"
    agents_dst_dir.mkdir(parents=True, exist_ok=True)

    for src in sorted(agents_src_dir.glob("*.md")):
        dst = agents_dst_dir / src.name
        try:
            content = src.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"  Warning: agent file not found: {src}", file=sys.stderr)
            continue
        try:
            with open(dst, "x", encoding="utf-8") as f:
                f.write(content)
        except FileExistsError:
            continue
        installed.append(src.name)
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
        return str(config_path), [], present

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
    permissions = settings.setdefault("permissions", {})
    additional_dirs = permissions.setdefault("additionalDirectories", [])
    plugin_dir = str(cfg.plugin_root)
    if plugin_dir not in additional_dirs:
        additional_dirs.append(plugin_dir)

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


def main():
    parser = argparse.ArgumentParser(description="Initialize planwise project structure")
    parser.add_argument("--name", required=True, help="Project name")
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
    args = parser.parse_args()

    cfg = InitConfig(
        project_name=args.name,
        project_root=Path(args.project_root).resolve() if args.project_root else Path.cwd(),
        plugin_root=get_plugin_root(),
        planwise_root=args.root,
        plans_dir=args.plans_dir,
        backlog_dir=args.backlog_dir,
        lessons_dir=args.lessons_dir,
        install_scope=args.scope,
        plan_tier=args.plan_tier,
    )

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

    cat_result, cat_rel = render_categorization_file(cfg)
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

    agents = install_agents(cfg)
    if agents:
        print("Agents mirrored to .claude/agents/:")
        for a in agents:
            print(f"  + {a}")
    else:
        print("Agents: already exist, skipped")
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

    if args.auto_from:
        print(f"Init complete — resuming /planwise {args.auto_from}…")
    else:
        _print_skipped_banner(skipped)
        print("Done!")


if __name__ == "__main__":
    main()
