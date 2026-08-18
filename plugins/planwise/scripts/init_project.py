#!/usr/bin/env python3
"""Initialize planwise project structure — CLI entry point + composition root.

Owns fresh-init scaffolding (directories, seed files, rule install, settings),
the INSTALLED_RULES/DESCOPED_RULES tables, and the argparse-driven main()
dispatch. The heavier subsystems live in sibling same-directory modules and
are imported/re-exported here so `import init_project` keeps working
unchanged: upgrade_io (backup/disposition/transfer primitives), config_gen
(InitConfig + config.yaml generation/migration), rule_divergence (installed-
vs-shipped structural classification), rule_descope_migration (rule de-scope
migration), artifact_upgrade (the --upgrade writer), doctor_sweeps + doctor_cli
(the --doctor/--list-diverged/--prune-stale/--prune-upgrade-leftovers
diagnostics), and lessons_bootstrap
(the categorization schema + lessons-scaffolding routine).

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
import json
import os
import re
import sys
from pathlib import Path

# When this file is run directly (`python init_project.py ...`), Python
# registers it as sys.modules["__main__"], NOT sys.modules["init_project"].
# The seam 4/5/6 sibling modules below do `from init_project import X` (R1:
# INSTALLED_RULES/DESCOPED_RULES stay on the residual) -- without this alias,
# that statement would trigger a SECOND, independent import of this same file
# under the "init_project" key, which re-executes from the top and collides
# with the sibling import already in progress (a circular ImportError distinct
# from -- and not fixed by -- the definition-ordering fix below). Aliasing
# first gives every `from init_project import ...` a single, already-partially
# -initialized module object to resolve against, exactly as the normal
# `import init_project` case already has.
if __name__ == "__main__":
    sys.modules.setdefault("init_project", sys.modules[__name__])

from constants import InstallScope

try:
    from upgrade_io import (
        _load_verdicts_cache,  # noqa: F401 -- re-exported for callers of init_project
        _load_verdict_override,  # noqa: F401 -- re-exported for callers of init_project
        _installed_hash,
        _write_backup_preimage,  # noqa: F401 -- re-exported for callers of init_project
        _append_disposition_log,  # noqa: F401 -- re-exported for callers of init_project
        _record_disposition,  # noqa: F401 -- re-exported for callers of init_project
        _load_raw_config,  # noqa: F401 -- re-exported for callers of init_project
        _transfer_customization,  # noqa: F401 -- re-exported for callers of init_project
    )
except ImportError:
    raise ImportError(
        "upgrade_io is required for init_project's backup/disposition/transfer "
        "primitives; the scripts/ directory appears to be partially installed"
    )

try:
    from config_gen import (
        PLAN_TIER_WINDOWS,
        MIGRATABLE_TOP_LEVEL_KEYS,  # noqa: F401 -- re-exported for callers of init_project
        MIGRATABLE_CONTEXT_SUBKEYS,  # noqa: F401 -- re-exported for callers of init_project
        _existing_context_subkeys,  # noqa: F401 -- re-exported for callers of init_project
        _context_subkeys_delta,  # noqa: F401 -- re-exported for callers of init_project
        merge_context_subkeys,  # noqa: F401 -- re-exported for callers of init_project
        extract_top_level_block,  # noqa: F401 -- re-exported for callers of init_project
        ConfigResult,
        InitConfig,
        get_plugin_root,
        read_plugin_version,
        generate_config,
        migrate_config,
        _bump_plugin_version,  # noqa: F401 -- re-exported for callers of init_project
        _flip_token_saver_on,  # noqa: F401 -- re-exported for callers of init_project
        get_upgrade_config,  # noqa: F401 -- re-exported for callers of init_project
        write_config_checked,  # noqa: F401 -- re-exported for callers of init_project
        find_context_block,  # noqa: F401 -- re-exported for callers of init_project
    )
except ImportError:
    raise ImportError(
        "config_gen is required for init_project's config.yaml generation/migration; "
        "the scripts/ directory appears to be partially installed"
    )

try:
    from rule_divergence import (
        is_subset,  # noqa: F401 -- re-exported for callers of init_project
        is_safe_to_remove,  # noqa: F401 -- re-exported for callers of init_project
        HAS_STRUCTURAL_COMPARE,  # noqa: F401 -- re-exported for callers of init_project
        classify_blocks,  # noqa: F401 -- re-exported for callers of init_project
        StructuralVerdict,  # noqa: F401 -- re-exported for callers of init_project
        structural_compare,  # noqa: F401 -- re-exported for callers of init_project
        _destructively_removable,  # noqa: F401 -- re-exported for callers of init_project
        normalize_rule_for_diff,  # noqa: F401 -- re-exported for callers of init_project
        _FALLBACK_PATHS_LINE_RE,  # noqa: F401 -- re-exported for callers of init_project
        _split_frontmatter_fallback,  # noqa: F401 -- re-exported for callers of init_project
        _extract_paths_value,  # noqa: F401 -- re-exported for callers of init_project
        _DEGRADED_VERDICT_SOURCE,  # noqa: F401 -- re-exported for callers of init_project
        _classify_diverged,  # noqa: F401 -- re-exported for callers of init_project
        _FM_KEY_LINE_RE,  # noqa: F401 -- re-exported for callers of init_project
        _BOM_CHAR,  # noqa: F401 -- re-exported for callers of init_project
        _split_frontmatter_block,  # noqa: F401 -- re-exported for callers of init_project
        _parse_frontmatter_map,  # noqa: F401 -- re-exported for callers of init_project
        _verdict_not_analyzed,  # noqa: F401 -- re-exported for callers of init_project
    )
except ImportError:
    raise ImportError(
        "rule_divergence is required for init_project's structural-verdict "
        "classification; the scripts/ directory appears to be partially installed"
    )

try:
    from lessons_bootstrap import (
        DEFAULT_CATEGORIZATION,  # noqa: F401 -- re-exported for callers of init_project
        _render_bucket_section,  # noqa: F401 -- re-exported for callers of init_project
        render_categorization_file,  # noqa: F401 -- re-exported for callers of init_project
        _seed_lessons_index,  # noqa: F401 -- re-exported for callers of init_project
        LessonsBootstrap,  # noqa: F401 -- re-exported for callers of init_project
        bootstrap_lessons_artifacts,
        _emit_lessons_bootstrap_banner,  # noqa: F401 -- re-exported for callers of init_project
    )
except ImportError:
    raise ImportError(
        "lessons_bootstrap is required for init_project's lessons-scaffolding "
        "bootstrap; the scripts/ directory appears to be partially installed"
    )

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


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


try:
    from rule_descope_migration import (
        RESCOPE_MIGRATION_VERSION,  # noqa: F401 -- re-exported for callers of init_project
        _version_tuple,  # noqa: F401 -- re-exported for callers of init_project
        migrate_installed_rules,  # noqa: F401 -- re-exported for callers of init_project
    )
except ImportError:
    raise ImportError(
        "rule_descope_migration is required for init_project's de-scope "
        "migration re-exports; the scripts/ directory appears to be "
        "partially installed"
    )

try:
    from artifact_upgrade import (
        upgrade_artifacts,  # noqa: F401 -- re-exported for callers of init_project
        load_artifact_manifest,
        _repoint_plugin_root,  # noqa: F401 -- re-exported for callers of init_project
        _commit_upgrade_pin,  # noqa: F401 -- re-exported for callers of init_project
        _same_path,  # noqa: F401 -- re-exported for callers of init_project
        _run_upgrade,
    )
except ImportError:
    raise ImportError(
        "artifact_upgrade is required for init_project's artifact-refresh/"
        "upgrade re-exports; the scripts/ directory appears to be partially "
        "installed"
    )

try:
    from doctor_sweeps import (
        lint_rule_overscope,  # noqa: F401 -- re-exported for callers of init_project
        sweep_stale_descoped_rules,  # noqa: F401 -- re-exported for callers of init_project
        sweep_orphaned_agent_mirrors,  # noqa: F401 -- re-exported for callers of init_project
        lint_installed_divergence,  # noqa: F401 -- re-exported for callers of init_project
        FORMERLY_MIRRORED_AGENTS,  # noqa: F401 -- re-exported for callers of init_project
    )
except ImportError:
    raise ImportError(
        "doctor_sweeps is required for init_project's doctor-sweep re-exports; "
        "the scripts/ directory appears to be partially installed"
    )

try:
    from doctor_cli import (
        _run_doctor,
        _run_prune_stale,
        _run_prune_upgrade_leftovers,
        _run_list_diverged,
        _list_diverged_rows,  # noqa: F401 -- re-exported for callers of init_project
        _doctor_version_gate,  # noqa: F401 -- re-exported for callers of init_project
        _resolve_doctor_config_path,  # noqa: F401 -- re-exported for callers of init_project
        _read_pinned_plugin_version,  # noqa: F401 -- re-exported for callers of init_project
        _read_configured_plugin_root,  # noqa: F401 -- re-exported for callers of init_project
        _doctor_config_parse_check,  # noqa: F401 -- re-exported for callers of init_project
        _detect_orphaned_block_signature,  # noqa: F401 -- re-exported for callers of init_project
    )
except ImportError:
    raise ImportError(
        "doctor_cli is required for init_project's doctor-dispatcher "
        "re-exports; the scripts/ directory appears to be partially installed"
    )


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
                        help="WRITER (opt-in): delete the stale de-scoped rules and "
                             "orphaned agent mirrors that --doctor's read-only sweeps mark "
                             "REMOVABLE, logging every removal to "
                             "upgrade-backups/prune-<date>[-N]/PRUNED.md. Never deletes a "
                             "customized (PRESERVE) rule or agent.")
    parser.add_argument("--prune-upgrade-leftovers", action="store_true",
                        help="WRITER (opt-in): delete the leftover upgrade recovery "
                             "directories --doctor's read-only sweep classifies as "
                             "safe-to-discard or inert, logging every removal to "
                             "upgrade-prune-logs/upgrade-leftovers-<date>[-N]/"
                             "PRUNED-LEFTOVERS.md. Distinct from --prune-stale, which "
                             "targets de-scoped rules and orphaned agent mirrors: this "
                             "flag never touches rules or agents, and never deletes an "
                             "action-required or review-then-discard artifact.")
    parser.add_argument("--prune-classes", default=None, metavar="LIST",
                        help="Comma-separated disposition classes to prune, narrowing "
                             "--prune-upgrade-leftovers to the classes the caller "
                             "confirmed (e.g. 'inert' to drop only consumed verdict "
                             "caches while keeping backups). Omit to prune both "
                             "prunable classes. Can only narrow: action-required and "
                             "review-then-discard are never deletable, whatever is passed.")
    parser.add_argument("--hash-installed", default=None, metavar="PATH",
                        help="Read-only diagnostic: print the sha256 digest of PATH's "
                             "normalized-text pre-image (BOM stripped, line endings "
                             "normalized to \\n) and exit. This is the SAME pre-image "
                             "the verdict-override cache reader hashes against, so a "
                             "verdicts.json entry's installed_sha256 must be computed "
                             "with this flag to be trusted. Does not require --name.")
    args = parser.parse_args()

    if args.hash_installed:
        # The upgrade handler interpolates an absolute path here once per verdict
        # entry, so a typo'd or moved path must surface as a one-line error, not a
        # stack trace mid-fan-out. OSError covers missing/dir/permission cases;
        # UnicodeDecodeError covers a non-text file reaching a text-mode read.
        try:
            print(_installed_hash(Path(args.hash_installed)))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"error: cannot hash {args.hash_installed}: {exc}", file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    # --doctor, --list-diverged, and the two --prune-* writers are self-scoped
    # modes that do not use the project name; every other mode
    # (init / --migrate / --upgrade) requires it.
    if (not args.doctor and not args.prune_stale and not args.prune_upgrade_leftovers
            and not args.list_diverged and not args.name):
        parser.error("--name is required (omit it only for the read-only --doctor "
                     "or --list-diverged diagnostics, or --prune-stale / "
                     "--prune-upgrade-leftovers)")

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

    if args.prune_upgrade_leftovers:
        _classes = ({c.strip() for c in args.prune_classes.split(",") if c.strip()}
                    if args.prune_classes else None)
        sys.exit(_run_prune_upgrade_leftovers(cfg, _classes))

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
    config_parse_error: str | None = None
    if HAS_YAML and config_path.exists():
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                user_cfg = loaded
        except yaml.YAMLError as exc:
            # An unparseable config is NOT an empty one. Falling through with
            # `{}` makes every presence check below read its key as absent, so
            # the banner fills with "missing block — run --migrate" rows that
            # cannot succeed (migrate parses the same file) and bury the actual
            # fault. Record the parser message and report THAT instead.
            user_cfg = {}
            first_line = str(exc).strip().splitlines()
            config_parse_error = first_line[0] if first_line else exc.__class__.__name__

    migrate_remediation = (
        f"Run `python {cfg.plugin_root.as_posix()}/scripts/init_project.py "
        f"--name \"{cfg.project_name}\" --migrate` to merge the block from the template."
    )

    if config_parse_error is not None:
        skipped.append(SkippedArtifact(
            artifact=f"{cfg.planwise_root}/config.yaml",
            reason=(
                f"the file does not parse as YAML ({config_parse_error}) — key-presence "
                f"and version checks are suppressed because they cannot be trusted"
            ),
            consumer="every planwise handler — all of them load this file",
            remediation=(
                f"Run `python {cfg.plugin_root.as_posix()}/scripts/init_project.py "
                f"--name \"{cfg.project_name}\" --doctor` to locate the fault (it names "
                f"the offending key when the cause is a recognised one), fix the reported "
                f"line, then re-run this command."
            ),
        ))

    # Both checks below are presence/comparison tests against the parsed config,
    # so neither means anything when the parse failed — skip them rather than
    # emit rows the user cannot act on.
    manifest_artifacts = [] if config_parse_error is not None else manifest.get("artifacts", [])

    for entry in manifest_artifacts:
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
    if config_parse_error is None and pinned_version != cfg.plugin_version:
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

