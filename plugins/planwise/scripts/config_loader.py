#!/usr/bin/env python3
"""Shared config loader for planwise plugin scripts.

Enhanced fork of the backlog skill's config_loader — uses upward search from cwd
to find config.yaml in the project root (vs the original's skill-relative path).
Do not sync back to .claude/skills/backlog/scripts/config_loader.py.

Pass --config <path> to specify the config file explicitly (overrides search).
"""

import argparse
import re
import sys
from pathlib import Path

# Try yaml import; fall back to regex extraction
try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def find_config_upward(start_path: Path) -> Path | None:
    """Walk upward from start_path to find config.yaml.

    At each directory level, checks:
    1. Direct: {dir}/config.yaml
    2. One level down: {dir}/*/config.yaml (finds planwise/config.yaml)

    Returns the Path to config.yaml if found, or None if not found.
    """
    current = start_path.resolve()
    while current != current.parent:
        # Direct check
        candidate = current / "config.yaml"
        if candidate.exists():
            return candidate
        # One level down (e.g., planwise/config.yaml)
        for subdir in current.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("."):
                candidate = subdir / "config.yaml"
                if candidate.exists():
                    return candidate
        current = current.parent
    return None



def _parse_yaml_simple(text: str) -> dict:
    """Minimal YAML parser for flat and one-level-nested structures.

    Handles the config.yaml format without requiring PyYAML.
    """
    result: dict = {}
    current_section = None

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level key with nested content (ends with ':' and no value)
        if re.match(r"^[a-zA-Z_]\w*:\s*$", stripped):
            current_section = stripped.rstrip(":").strip()
            result[current_section] = {}
            continue

        # Top-level key with scalar value
        top_match = re.match(r"^([a-zA-Z_]\w*):\s+(.+)$", stripped)
        if top_match and current_section is None:
            key, val = top_match.group(1), top_match.group(2).strip().strip("'\"")
            result[key] = _coerce(val)
            continue

        # Nested key-value under a section. Match against the ORIGINAL line —
        # `stripped` has no leading whitespace, so matching it would silently
        # flatten nested keys to the top level (dropping the whole section).
        nested_match = re.match(r"^\s+([a-zA-Z_]\w*):\s+(.+)$", line)
        if nested_match and current_section is not None:
            key, val = nested_match.group(1), nested_match.group(2).strip().strip("'\"")
            result[current_section][key] = _coerce(val)
            continue

        # List item under a section (also matched against the original line)
        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if list_match and current_section is not None:
            val = list_match.group(1).strip().strip("'\"")
            if not isinstance(result[current_section], list):
                result[current_section] = []
            result[current_section].append(_coerce(val))
            continue

        # Top-level key starting a new context resets section
        if re.match(r"^[a-zA-Z_]", stripped):
            current_section = None
            top_match2 = re.match(r"^([a-zA-Z_]\w*):\s*(.*)$", stripped)
            if top_match2:
                key = top_match2.group(1)
                val = top_match2.group(2).strip().strip("'\"")
                if val:
                    result[key] = _coerce(val)
                else:
                    current_section = key
                    result[key] = {}

    return result


def _coerce(val: str):
    """Coerce string values to int, float, or bool where obvious."""
    if val.lower() in ("true", "yes"):
        return True
    if val.lower() in ("false", "no"):
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _get_config_path_from_args() -> Path | None:
    """Parse --config argument from sys.argv without consuming other args."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=Path, default=None)
    known, _ = parser.parse_known_args()
    return known.config


def load_config(script_path: Path | None = None) -> dict:
    """Load config.yaml for the current project.

    Config search order:
    1. --config <path> command-line argument (explicit override)
    2. Search upward from the current working directory for config.yaml
    3. Search upward from script_path (or __file__) for config.yaml

    Args:
        script_path: Path to the calling script. Used as fallback search root.
                     If None, uses __file__.

    Returns:
        Parsed config dict with resolved paths.
    """
    if script_path is None:
        script_path = Path(__file__)

    # 1. Explicit --config argument
    explicit_config = _get_config_path_from_args()
    if explicit_config is not None:
        config_path = explicit_config.resolve()
        if not config_path.exists():
            print(f"Error: config.yaml not found at {config_path}", file=sys.stderr)
            sys.exit(1)
    else:
        # 2. Search upward from cwd
        config_path = find_config_upward(Path.cwd())

        # 3. Fall back: search upward from script location
        if config_path is None:
            config_path = find_config_upward(script_path.resolve().parent)

        if config_path is None:
            print(
                "Error: config.yaml not found. Run '/planwise init' to create it, "
                "or pass --config <path> to specify it explicitly.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(
            f"Warning: --config not provided, found config at {config_path}",
            file=sys.stderr,
        )

    raw = config_path.read_text(encoding="utf-8")

    if HAS_YAML:
        config = yaml.safe_load(raw) or {}
    else:
        config = _parse_yaml_simple(raw)

    # Planwise root is the directory containing config.yaml
    planwise_root = config_path.parent

    config["_planwise_root"] = planwise_root
    # Project root is one level above planwise root
    config["_project_root"] = planwise_root.parent

    # Resolve paths relative to planwise root
    project = config.get("project", {})

    # Validate project.name when config was found via upward search
    if explicit_config is None:
        project_name = project.get("name", "")
        if not project_name or "{" in project_name:
            print(
                f"Warning: config at {config_path} has placeholder or missing "
                f"project.name '{project_name}' — may not be the intended config",
                file=sys.stderr,
            )

    backlog_rel = project.get("backlog_dir", "Backlog")
    config["_backlog_dir"] = planwise_root / backlog_rel
    config["_archive_dir"] = planwise_root / project.get("archive_dir", f"{backlog_rel}/Archive")
    index_files = project.get("index_files", {}) if isinstance(project.get("index_files"), dict) else {}
    config["_index_path"] = config["_backlog_dir"] / index_files.get("backlog", "00-Index-Backlog.md")

    # Resolve plugin root (fall back if config value is missing or stale)
    plugin_root_val = config.get("plugin_root")
    fallback = Path(__file__).resolve().parent.parent
    if plugin_root_val and Path(plugin_root_val).exists():
        config["_plugin_root"] = Path(plugin_root_val)
    else:
        config["_plugin_root"] = fallback

    # Resolve plans path
    plans_rel = project.get("plans_dir", "Plans")
    config["_plans_dir"] = planwise_root / plans_rel

    # Resolve lessons paths (optional)
    lessons_dir = project.get("lessons_dir", "")
    if lessons_dir:
        config["_lessons_dir"] = planwise_root / lessons_dir
        config["_lessons_index"] = config["_lessons_dir"] / index_files.get("lessons", "00-Index-LessonsLearned.md")
    else:
        config["_lessons_dir"] = None
        config["_lessons_index"] = None

    return config


def get_scoring_weights(config: dict) -> dict:
    """Extract scoring weights from config, with defaults."""
    scoring = config.get("scoring", {})
    return {
        "priority_high": scoring.get("priority_high", 30),
        "priority_medium": scoring.get("priority_medium", 20),
        "priority_low": scoring.get("priority_low", 10),
        "bug_fix_bonus": scoring.get("bug_fix_bonus", 15),
        "in_progress_bonus": scoring.get("in_progress_bonus", 10),
        "file_count_bonus": scoring.get("file_count_bonus", 5),
        "planning_penalty": scoring.get("planning_penalty", -5),
        "blocks_bonus": scoring.get("blocks_bonus", 20),
        "momentum_bonus": scoring.get("momentum_bonus", 5),
        "age_bonus_per_week": scoring.get("age_bonus_per_week", 1),
        "age_cap": scoring.get("age_cap", 12),
    }


def get_token_saver_config(config: dict) -> dict:
    """Extract the Token Saver budget surface from config, with defaults.

    Mirrors get_scoring_weights: reads the six `context.token_saver*` keys and
    falls back to documented backward-compatible defaults when a key is absent
    (a config that predates the Token Saver surface). The defaults are
    deliberately conservative — never assume the engine is ON and never assume
    a calibrated (non-zero) overhead:

      * token_saver                       -> False  (engine off until enabled)
      * token_saver_session_target        -> 150000 (keeps a Sonnet runner < 200K)
      * token_saver_runner_overhead       -> 0      (0 == not yet calibrated)
      * token_saver_orchestrator_overhead -> 0      (0 == not yet calibrated)
      * token_saver_context_breakdown     -> {}     (no measured breakdown yet)
      * token_saver_overhead_measured_on  -> ""     (never calibrated)

    The no-PyYAML loader may parse the inline-flow breakdown mapping as an
    opaque string; that is harmless because the breakdown is diagnostic only.
    """
    context = config.get("context", {})
    if not isinstance(context, dict):
        context = {}

    breakdown = context.get("token_saver_context_breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}

    return {
        "token_saver": bool(context.get("token_saver", False)),
        "token_saver_session_target": context.get(
            "token_saver_session_target", 150000
        ),
        "token_saver_runner_overhead": context.get(
            "token_saver_runner_overhead", 0
        ),
        "token_saver_orchestrator_overhead": context.get(
            "token_saver_orchestrator_overhead", 0
        ),
        "token_saver_context_breakdown": breakdown,
        "token_saver_overhead_measured_on": context.get(
            "token_saver_overhead_measured_on", ""
        ),
    }


def _as_bool_flag(value, default: bool) -> bool:
    """Coerce a config flag to bool without Python-truthiness surprises.

    YAML users commonly quote booleans (`github_issue: "false"`), which
    `bool(...)` would coerce to True. Recognized string spellings map to
    their boolean meaning; None, unrecognized strings, and other types fall
    back to the documented default.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "on", "1"):
            return True
        if lowered in ("false", "no", "off", "0"):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def get_upgrade_config(config: dict) -> dict:
    """Extract the `upgrade:` block from config, with conservative defaults.

    Mirrors get_token_saver_config: reads the three `upgrade.*` keys and falls
    back to documented backward-compatible defaults when the block (or a key)
    is absent, explicitly null, or malformed — a config that predates the
    upgrade surface. Defaults are the safe status quo:

      * customization_handoff        -> "report" (never auto-relocate/-issue)
      * github_issue                 -> False    (opt-in, interactive only)
      * descope_preserve_paths_edits -> True     (keep today's behavior:
                                                   preserve a paths-only-edited
                                                   de-scoped rule; False opts in
                                                   to removing it)
    """
    upgrade = config.get("upgrade", {})
    if not isinstance(upgrade, dict):
        upgrade = {}
    handoff = upgrade.get("customization_handoff", "report")
    if not isinstance(handoff, str) or not handoff.strip():
        handoff = "report"
    return {
        "customization_handoff": handoff,
        "github_issue": _as_bool_flag(upgrade.get("github_issue"), False),
        "descope_preserve_paths_edits": _as_bool_flag(
            upgrade.get("descope_preserve_paths_edits"), True
        ),
    }


def get_effective_token_saver_config(config: dict, plan_override=None) -> dict:
    """Overlay an optional per-plan on/off decision onto the project surface.

    The project config carries exactly ONE Token Saver calibration — there is a
    single `/context` measurement per project because the installed plugin+rules
    surface is identical for every plan. A plan may only flip the on/off boolean;
    the measured overheads (runner_overhead, orchestrator_overhead,
    session_target, breakdown, measured_on) ALWAYS come from the project config.

    Args:
        config: the loaded project config dict.
        plan_override: the parsed per-plan decision — True/False when a plan sets
                       one, None when the plan has no override (inherit project).

    Returns:
        The same shape as get_token_saver_config(config), with `token_saver`
        replaced by bool(plan_override) when plan_override is not None and every
        other key left exactly as the project config produced it.
    """
    base = get_token_saver_config(config)
    if plan_override is not None:
        base["token_saver"] = bool(plan_override)
    return base
