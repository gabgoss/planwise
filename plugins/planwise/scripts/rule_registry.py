"""Shared rule-install registry: the INSTALLED_RULES / DESCOPED_RULES tables
and the two helpers that resolve a rule's `paths:` value and write it into a
rule file's frontmatter.

This is a leaf module. It imports nothing from init_project, artifact_upgrade,
rule_descope_migration, doctor_sweeps or doctor_cli, so each of those binds
these four names at the top of its own file without forming an import cycle.
init_project re-exports all four, so `from init_project import INSTALLED_RULES`
still resolves for existing callers. Every importing module holds its own
binding of each name, and that per-module binding is what the test suite
patches (`patch.object(artifact_upgrade, "INSTALLED_RULES", ...)`), so a
patch on one module never leaks into another.
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config_gen import InitConfig


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
# references/ — see DESCOPED_RULES below and
# rule_descope_migration.migrate_installed_rules().
# The two global style rules are installed separately by
# `style_rules.install_style_rules` and are not in this table.
INSTALLED_RULES: list[tuple[str, str]] = [
    ("agent-authoring.md", ".claude/agents/**"),
    ("skill-authoring.md", ".claude/skills/**"),
    ("rule-authoring.md", ".claude/rules/**"),
    ("artifact-self-containment.md", ".claude/rules/**, .claude/agents/**, .claude/skills/**, .claude/commands/**, CLAUDE.md"),
]


# Rules removed from the install set during the rule de-scope. Each tuple is
# (source_filename, old_paths_template) where old_paths_template is the
# {plans_path} / {all_paths} placeholder the rule carried BEFORE de-scoping.
# rule_descope_migration.migrate_installed_rules() resolves each template back
# to the pre-migration default paths: value to recognise an untouched installed
# copy and remove it; the orchestrator now loads these rules on demand from
# references/ instead of injecting them as always-on path-scoped rules.
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


def resolve_rule_paths_value(cfg: "InitConfig", paths_template: str) -> str:
    """Substitute {plans_path} / {all_paths} placeholders into a paths: value."""
    plans_path = f"{cfg.planwise_root}/{cfg.plans_dir}/**"
    all_paths = ", ".join([
        plans_path,
        f"{cfg.planwise_root}/{cfg.backlog_dir}/**",
        f"{cfg.planwise_root}/{cfg.lessons_dir}/**",
    ])
    return paths_template.replace("{plans_path}", plans_path).replace("{all_paths}", all_paths)


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
