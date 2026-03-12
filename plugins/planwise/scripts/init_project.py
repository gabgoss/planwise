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
"""

import argparse
import dataclasses
import re
import shutil
import sys
from enum import Enum
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


class ConfigResult(Enum):
    CREATED = "created"
    SKIPPED_EXISTS = "skipped_exists"
    SKIPPED_NO_TEMPLATE = "skipped_no_template"


@dataclasses.dataclass
class InitConfig:
    project_name: str
    project_root: Path
    plugin_root: Path
    planwise_root: str = "planwise"
    plans_dir: str = "Plans"
    backlog_dir: str = "Backlog"
    lessons_dir: str = "LessonsLearned"


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
        if dst.exists():
            continue
        try:
            shutil.copy2(src, dst)
        except FileNotFoundError:
            print(f"  Warning: seed file not found: {src}", file=sys.stderr)
            continue
        copied.append(dst_rel)
    return copied


def generate_config(cfg: InitConfig) -> tuple[ConfigResult, str]:
    """Generate config.yaml from template. Returns (status, path)."""
    template_path = cfg.plugin_root / "config.yaml.template"
    config_rel = f"{cfg.planwise_root}/config.yaml"
    dst = cfg.project_root / cfg.planwise_root / "config.yaml"

    if dst.exists():
        return ConfigResult.SKIPPED_EXISTS, config_rel

    try:
        content = template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ConfigResult.SKIPPED_NO_TEMPLATE, config_rel

    content = content.replace("{project-name}", cfg.project_name)
    content = content.replace('planwise_root: "planwise"', f'planwise_root: "{cfg.planwise_root}"')
    content = content.replace('plans_dir: "Plans"', f'plans_dir: "{cfg.plans_dir}"')
    content = content.replace('backlog_dir: "Backlog"', f'backlog_dir: "{cfg.backlog_dir}"')
    content = content.replace('lessons_dir: "LessonsLearned"', f'lessons_dir: "{cfg.lessons_dir}"')

    dst.write_text(content, encoding="utf-8")
    return ConfigResult.CREATED, config_rel


def _format_paths_yaml(paths: list[str]) -> str:
    """Format paths as a YAML array block."""
    return "paths:\n" + "\n".join(f'  - "{p}"' for p in paths)


def update_frontmatter(content: str, paths: list[str]) -> str:
    """Update or add paths: field in YAML frontmatter as a YAML array."""
    paths_block = _format_paths_yaml(paths)

    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end == -1:
            return f"---\n{paths_block}\n---\n\n{content}"

        frontmatter = content[4:end]
        body = content[end + 5:]

        if re.search(r"^paths:", frontmatter, re.MULTILINE):
            frontmatter = re.sub(
                r"^paths:.*(?:\n  - .*)*", paths_block,
                frontmatter, count=1, flags=re.MULTILINE
            )
        else:
            frontmatter = frontmatter.rstrip() + "\n" + paths_block

        return f"---\n{frontmatter}\n---\n{body}"
    else:
        return f"---\n{paths_block}\n---\n\n{content}"


def install_rules(cfg: InitConfig) -> list[str]:
    """Copy reference files as rules with updated paths: frontmatter.
    Skips if destination exists. Returns list of installed rules."""
    installed = []
    refs_dir = cfg.plugin_root / "references"
    rules_dir = cfg.project_root / ".claude" / "rules" / "planwise"

    plans_paths = [f"{cfg.planwise_root}/{cfg.plans_dir}/**"]
    all_paths = [
        f"{cfg.planwise_root}/{cfg.plans_dir}/**",
        f"{cfg.planwise_root}/{cfg.backlog_dir}/**",
        f"{cfg.planwise_root}/{cfg.lessons_dir}/**",
    ]

    rules = [
        ("agent-authoring.md", [".claude/agents/**"]),
        ("skill-authoring.md", [".claude/skills/**"]),
        ("rule-authoring.md", [".claude/rules/**"]),
        ("session-planning-protocol.md", plans_paths),
        ("session-plan-requirements.md", plans_paths),
        ("session-context-budget.md", plans_paths),
        ("session-execution-protocol.md", plans_paths),
        ("agent-orchestration.md", all_paths),
        ("callout-conventions.md", all_paths),
        ("markdown-conventions.md", all_paths),
    ]

    for filename, paths in rules:
        dst = rules_dir / filename
        if dst.exists():
            continue
        src = refs_dir / filename
        try:
            content = src.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"  Warning: reference not found: {src}", file=sys.stderr)
            continue

        content = update_frontmatter(content, paths)
        dst.write_text(content, encoding="utf-8")
        installed.append(filename)

    return installed


def main():
    parser = argparse.ArgumentParser(description="Initialize planwise project structure")
    parser.add_argument("--name", required=True, help="Project name")
    parser.add_argument("--root", default="planwise", help="Planwise root directory")
    parser.add_argument("--plans-dir", default="Plans", help="Plans subdirectory name")
    parser.add_argument("--backlog-dir", default="Backlog", help="Backlog subdirectory name")
    parser.add_argument("--lessons-dir", default="LessonsLearned", help="Lessons subdirectory name")
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

    rules = install_rules(cfg)
    if rules:
        print("Rules installed to .claude/rules/planwise/:")
        for r in rules:
            print(f"  + {r}")
    else:
        print("Rules: already exist, skipped")
    print()

    print("Done!")


if __name__ == "__main__":
    main()
