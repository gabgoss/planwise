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
"""

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
    """
    dst_rel = f"{cfg.planwise_root}/{cfg.lessons_dir}/00-Categorization-By-Domain.md"
    dst = cfg.project_root / dst_rel
    if dst.exists():
        return ConfigResult.SKIPPED_EXISTS, dst_rel

    if not HAS_YAML:
        return ConfigResult.SKIPPED_NO_YAML, dst_rel

    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ConfigResult.SKIPPED_NO_TEMPLATE, dst_rel

    try:
        full = yaml.safe_load(config_text) or {}
    except yaml.YAMLError:
        return ConfigResult.SKIPPED_NO_TEMPLATE, dst_rel

    cat = full.get("categorization") if isinstance(full, dict) else None
    if not isinstance(cat, dict):
        return ConfigResult.SKIPPED_NO_TEMPLATE, dst_rel

    buckets = cat.get("buckets") or []
    buckets = [b for b in buckets if isinstance(b, dict)]
    if not buckets:
        return ConfigResult.SKIPPED_NO_TEMPLATE, dst_rel

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
    return ConfigResult.CREATED, dst_rel


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
        ("agent-orchestration.md", all_paths),
        ("callout-conventions.md", all_paths),
        ("markdown-conventions.md", all_paths),
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
    parser.add_argument("--project-root", default=None, help="Project root (default: cwd)")
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
    )

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
    print()

    cat_result, cat_rel = render_categorization_file(cfg)
    if cat_result == ConfigResult.CREATED:
        print(f"Categorization: + {cat_rel}")
    elif cat_result == ConfigResult.SKIPPED_EXISTS:
        print("Categorization: already exists, skipped")
    elif cat_result == ConfigResult.SKIPPED_NO_YAML:
        print("Categorization: skipped (PyYAML not installed — install with `pip install pyyaml`, or let the /planwise init handler render via Step 5.1)")
    else:
        print("Categorization: skipped (config.yaml: categorization block missing or unparseable)")
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
    print()

    print("Done!")


if __name__ == "__main__":
    main()
