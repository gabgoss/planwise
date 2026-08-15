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


class ConfigWriteError(RuntimeError):
    """A config.yaml write produced an unparseable file and was rolled back."""


def write_config_checked(config_path, text: str) -> None:
    """Write `text` to `config_path`, then verify the result still parses.

    Every writer that edits config.yaml routes through here. The writers are
    deliberately *targeted* (regex line splices and text-block appends) so the
    user's comments, key order, and flow styles survive — but a targeted edit
    that goes wrong produces a file that no longer parses, and nothing else in
    the pipeline notices until the NEXT command dies on a raw parser traceback.
    This helper closes that gap: it writes, re-reads, and parses the result; on
    failure it restores the pre-write bytes (or removes the file when it did not
    exist before) and raises ConfigWriteError naming the path.

    When PyYAML is unavailable the parse check degrades to a documented no-op —
    the write proceeds unverified, mirroring the HAS_YAML fallbacks elsewhere in
    this module. Verification needs a real parser: the minimal
    `_parse_yaml_simple` reader above accepts malformed input silently and would
    hand back a false all-clear.
    """
    path = Path(config_path)
    try:
        previous = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        previous = None

    path.write_text(text, encoding="utf-8")

    if not HAS_YAML:
        return

    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        if previous is None:
            path.unlink()
            restored = "the file was removed"
        else:
            path.write_text(previous, encoding="utf-8")
            restored = "the file is unchanged"
        raise ConfigWriteError(
            f"{path}: the edited config does not parse as YAML — the write was "
            f"rolled back and {restored}. Parser said: {exc}"
        ) from exc


def find_context_block(lines: list[str]) -> tuple[int, int, str] | None:
    """Locate the top-level `context:` block in a list of YAML lines.

    Returns (header_index, block_end_exclusive, subkey_indent) where:
      * header_index is the index of the `context:` line,
      * block_end_exclusive is the index of the first line AFTER the block
        (the next top-level key, or len(lines) at EOF),
      * subkey_indent is the leading whitespace string used for the block's
        sub-keys (taken from the first indented member, or "  " if none).

    Returns None when no top-level `context:` block exists.

    This is the shared LOCATE half of the config.yaml `context:`-block text
    surgery: every writer that targets the block — the additive,
    skip-if-present sub-key merge and the replace-or-append splice below —
    locates it this same way, so this is their one shared home. Callers that
    need the SPLICE half (replace-or-append) use splice_context_block(); a
    caller that instead must never overwrite an existing sub-key locates the
    block here and keeps its own skip-if-present loop local.
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


def _block_value_end(text: str, line_end: int, key_indent: int) -> int:
    """Return the offset just past a block-mapping value following a key line.

    `line_end` is the end offset of the matched `key:` line (the position of its
    newline, or EOF); `key_indent` is that line's indent width. Consumes each
    following line indented STRICTLY deeper than the key — deeper-indented
    comment lines included, since they sit inside the block. Stops at the first
    blank line or any line indented at or below the key, so a trailing blank
    line and a comment introducing the NEXT key are never swallowed.

    Returns `line_end` unchanged unless at least one deeper-indented NON-comment
    child was found — a lone comment under a valueless key is the user's note on
    an empty value, not a block mapping, and must survive the rewrite.
    """
    end = line_end
    pos = line_end
    saw_child = False
    while pos < len(text) and text[pos] == "\n":
        nxt = text.find("\n", pos + 1)
        line = text[pos + 1:] if nxt == -1 else text[pos + 1:nxt]
        if not line.strip():
            break
        indent = len(line) - len(line.lstrip())
        if indent <= key_indent:
            break
        if not line.lstrip().startswith("#"):
            saw_child = True
        end = pos + 1 + len(line)
        pos = end
    return end if saw_child else line_end


def splice_context_block(text: str, values: dict) -> str:
    """Replace-or-append each (key, value) pair against a `context:` block.

    For every key in `values`:
      * If a `key:` line exists ANYWHERE in `text` (the search is a plain
        whole-text regex, not scoped to inside the block — matching a
        top-level key like `plugin_version` works the same way), its value is
        REPLACED IN PLACE. A trailing inline comment on that line is
        preserved. When the key's own line carries no value (the real value
        lives in an indented block below it — either hand-authored or
        produced by an earlier whole-file re-dump), the entire child block is
        consumed and replaced too, so no orphaned children are left behind.
      * If the key is absent, `{subkey_indent}{key}: {value}` is appended
        directly under the `context:` block (or at end-of-text when no
        `context:` block exists).

    This is a targeted text splice — never a YAML round-trip — so comments,
    key order, and flow styles everywhere else in `text` survive untouched.
    Each value in `values` is rendered VERBATIM (an already-formatted YAML
    literal), not Python-to-YAML converted.

    This function ALWAYS replaces an existing key — it is the opposite policy
    from an additive, skip-if-present merge. A caller that must never
    overwrite an existing sub-key (e.g. a --migrate that must not clobber a
    user's already-calibrated values) does not use this function for that
    policy; it locates the block via find_context_block() and keeps its own
    skip-if-present loop local.
    """
    lines = text.split("\n")
    block = find_context_block(lines)
    subkey_indent = block[2] if block is not None else "  "

    appended: list[str] = []
    for key, value in values.items():
        pattern = re.compile(
            rf"^(?P<indent>\s*){re.escape(key)}:(?P<rest>[^\n]*)$", re.MULTILINE
        )
        m = pattern.search(text)
        if m:
            # Preserve a trailing inline comment on the line (the value is
            # everything up to an unquoted `#`). Splice via slicing rather than
            # re.sub so the replacement is never re-interpreted for backrefs.
            cm = re.search(r"(\s+#.*)$", m.group("rest"))
            comment = cm.group(1) if cm else ""
            replacement = f"{m.group('indent')}{key}: {value}{comment}"
            end = m.end()
            # An empty value on the key line (once its inline comment is set
            # aside) means the real value may live in an indented block below —
            # consume that block along with the parent line.
            value_part = m.group("rest")[: cm.start(1)] if cm else m.group("rest")
            if not value_part.strip():
                end = _block_value_end(text, m.end(), len(m.group("indent")))
            text = text[: m.start()] + replacement + text[end:]
        else:
            appended.append(f"{subkey_indent}{key}: {value}")

    if appended:
        lines = text.split("\n")
        # Recompute the insertion point on the (possibly) mutated text.
        block2 = find_context_block(lines)
        insert_at = block2[1] if block2 is not None else len(lines)
        lines = lines[:insert_at] + appended + lines[insert_at:]
        text = "\n".join(lines)

    return text


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

      * customization_handoff        -> "report"
      * github_issue                 -> False    (opt-in, interactive only)
      * descope_preserve_paths_edits -> True     (keep today's behavior:
                                                   preserve a paths-only-edited
                                                   de-scoped rule; False opts in
                                                   to removing it)

    `customization_handoff` disposition semantics (consumed by the `--upgrade`
    writer's customization-bearing branch):

      * "report"          — conservative: preserve the installed file in place
                            + write a `.new` sidecar; NO automated transfer,
                            NO adoption. This stays the ABSENT-KEY fallback so
                            configs that predate the key keep the safe
                            pre-existing behavior.
      * "report+relocate" — automated transfer-then-adopt: the customization
                            is verified-written to a dormant preservation file
                            under `{planwise_root}/upgrade-transfers/` first,
                            then shipped is adopted in place. The shipped
                            config.yaml.template pins this value EXPLICITLY —
                            new installs get the automated flow while the
                            absent-key fallback above stays conservative.
      * "report+issue"    — same conservative disposition as "report" for the
                            writer; the extra "+issue" meaning (routing an
                            upstream-tagged customization to a GitHub issue)
                            is interactive/handler-side only and additionally
                            requires `github_issue: true`.
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


def get_feedback_config(config: dict) -> dict:
    """Extract the `feedback:` block from config, with conservative defaults.

    Mirrors get_upgrade_config: reads the three `feedback.*` keys and falls
    back to documented backward-compatible defaults when the block (or a key)
    is absent, explicitly null, or malformed — a config that predates the
    feedback surface. Defaults are the safe status quo:

      * enabled             -> False                  (opt-in, interactive only)
      * repo                -> "gabgoss/planwise"      (upstream target)
      * include_environment -> True                    (auto-filled Environment block)
    """
    feedback = config.get("feedback", {})
    if not isinstance(feedback, dict):
        feedback = {}
    repo = feedback.get("repo", "gabgoss/planwise")
    if not isinstance(repo, str) or not repo.strip():
        repo = "gabgoss/planwise"
    return {
        "enabled": _as_bool_flag(feedback.get("enabled"), False),
        "repo": repo,
        "include_environment": _as_bool_flag(feedback.get("include_environment"), True),
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
