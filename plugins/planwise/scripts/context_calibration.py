#!/usr/bin/env python3
"""Token Saver calibration engine: `/context` report parsing, overhead and
threshold derivation, and the capture/write-back flow.

`parse_context_report` -> `derive_overheads` -> `derive_thresholds` turn a
captured `/context` report into a per-task token ceiling, and `calibrate`
captures a live report, derives those values, and writes them back into
config.yaml. These numbers are MEASURED, not hardcoded.

Pure functions (parser/derivation) shell out to nothing, so they are
unit-testable without a live `claude` binary. Only `capture_context` /
`calibrate` touch the filesystem or subprocess. No third-party dependency —
stdlib (re, os, shutil, subprocess, datetime) plus two sibling script
modules — `config_loader` for the parse-checked config write and
`markdown_parser` for the escape-aware table split; both are imported behind
a partial-install fallback.
"""

import os
import re
import shutil
import subprocess
from datetime import date

try:
    from config_loader import splice_context_block, write_config_checked
except ImportError:  # pragma: no cover - partial-install tolerance
    def write_config_checked(config_path, text: str) -> None:   # noqa: D103
        # Degraded fallback: the post-write parse check lives in config_loader,
        # so a half-synced scripts tree writes unverified rather than failing to
        # import. Same spirit as the no-PyYAML no-op in the real helper.
        config_path.write_text(text, encoding="utf-8")

    def splice_context_block(text: str, values: dict) -> str:   # noqa: D103
        # Unlike write_config_checked's degraded-but-safe no-op above, this
        # helper's own job IS config.yaml write correctness. Duplicating (and
        # risking drift from) the locate/splice/block-extent logic here would
        # let a half-synced scripts tree silently rewrite a user's config.yaml
        # with no signal something is wrong. Fail loudly instead —
        # config_loader is a required sibling module, not an optional one.
        raise ImportError(
            "config_loader is required for config.yaml context-block editing; "
            "the scripts/ directory appears to be partially installed"
        )

try:
    from markdown_parser import split_row_cells
except ImportError:  # pragma: no cover - partial-install tolerance
    _UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")

    def split_row_cells(line: str) -> list:   # noqa: D103
        # Degraded fallback mirroring markdown_parser.split_row_cells. It must
        # stay escape-aware: a naive split on `\|` shifts every column right by
        # one, which is the whole defect this helper exists to prevent.
        stripped = line.strip()
        segments = _UNESCAPED_PIPE.split(stripped)
        if segments and stripped.startswith("|"):
            segments = segments[1:]
        if segments and stripped.endswith("|") and not stripped.endswith("\\|"):
            segments = segments[:-1]
        return [seg.replace("\\|", "|").strip() for seg in segments]

# ---------------------------------------------------------------------------
# Derivation defaults (must match the calibration tests).
# ---------------------------------------------------------------------------
DEFAULT_GROWTH_MARGIN = 6000
DEFAULT_OUTPUT_RESERVE = 10000
DEFAULT_WARN_CEILING = 40000

# Conservative fallback overheads, written when a /context capture fails.
FALLBACK_RUNNER_OVERHEAD = 54000
FALLBACK_ORCHESTRATOR_OVERHEAD = 60000


# ---------------------------------------------------------------------------
# /context parsing
# ---------------------------------------------------------------------------
def _normalize_tokens(raw: str) -> int:
    """Normalize a /context token string to an int.

    Handles `25.7k` -> 25700, `1.7k` -> 1700, `386` -> 386, `~80` -> 80,
    `< 20` / `<20` -> 20, `974.3k` -> 974300, `1m` -> 1000000.
    """
    s = raw.strip().lstrip("~").lstrip("<").strip()
    if not s:
        return 0
    m = re.match(r"^([\d,]+(?:\.\d+)?)\s*([kmKM]?)", s)
    if not m:
        return 0
    number = float(m.group(1).replace(",", ""))
    suffix = m.group(2).lower()
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    return int(round(number))


def parse_context_report(text: str) -> dict:
    """Parse a captured `/context` markdown report into a structured dict.

    Returns:
        {
          "total_active": int,   # active footprint, EXCLUDES System tools (deferred)
          "categories": {name: tokens, ...},  # every category row, incl. deferred
          "agents": [{"name", "source", "tokens"}, ...],
          "skills": [{"name", "source", "tokens"}, ...],
        }

    Rules:
      * "System tools (deferred)" is parsed into `categories` but EXCLUDED from
        `total_active` (and so is "Free space").
      * Token strings normalize via `_normalize_tokens`.
      * total_active prefers the header `**Tokens:** <n> / ...` figure (the
        canonical active total) and falls back to summing the non-deferred,
        non-free-space category rows.
    """
    categories: dict[str, int] = {}
    agents: list[dict] = []
    skills: list[dict] = []

    section = None  # None | "categories" | "agents" | "skills"
    header_total: int | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Header total: **Tokens:** 25.7k / 1m (3%)
        hm = re.match(r"^\*\*Tokens:\*\*\s*([^/]+)/", line)
        if hm:
            header_total = _normalize_tokens(hm.group(1))
            continue

        # Section switches.
        low = line.lower()
        if low.startswith("###") and "category" in low:
            section = "categories"
            continue
        if low.startswith("###") and "agent" in low:
            section = "agents"
            continue
        if low.startswith("###") and "skill" in low:
            section = "skills"
            continue
        if low.startswith("#"):
            # Some other heading — leave current section, it will be reset by
            # the next recognized section header.
            continue

        if not line.startswith("|"):
            continue

        cells = split_row_cells(line)
        # Skip markdown separator rows ( |---|---| ) and header label rows.
        if all(set(c) <= {"-", ":"} and c for c in cells):
            continue

        if section == "categories" and len(cells) >= 2:
            name = cells[0]
            if name.lower() in ("category",):
                continue
            categories[name] = _normalize_tokens(cells[1])
        elif section == "agents" and len(cells) >= 3:
            if cells[0].lower() in ("agent type", "agent"):
                continue
            agents.append(
                {"name": cells[0], "source": cells[1], "tokens": _normalize_tokens(cells[2])}
            )
        elif section == "skills" and len(cells) >= 3:
            if cells[0].lower() in ("skill",):
                continue
            skills.append(
                {"name": cells[0], "source": cells[1], "tokens": _normalize_tokens(cells[2])}
            )

    if header_total is not None:
        total_active = header_total
    else:
        excluded = {"system tools (deferred)", "free space"}
        total_active = sum(
            v for k, v in categories.items() if k.strip().lower() not in excluded
        )

    return {
        "total_active": total_active,
        "categories": categories,
        "agents": agents,
        "skills": skills,
        "has_tokens_header": header_total is not None,
    }


def attribution(report: dict, plugin: str = "") -> int:
    """Sum the Agents + Skills rows whose Source begins with "Plugin".

    Built-in rows are excluded. The `plugin` name is accepted for API symmetry
    with multi-plugin attribution but the gate is simply "Source starts with
    'Plugin'" (matching `Plugin` and `Plugin (planwise)`).
    """
    total = 0
    for row in list(report.get("agents", [])) + list(report.get("skills", [])):
        source = str(row.get("source", "")).strip()
        if source.startswith("Plugin"):
            total += int(row.get("tokens", 0))
    return total


# ---------------------------------------------------------------------------
# Overhead + threshold derivation
# ---------------------------------------------------------------------------
def derive_overheads(report: dict) -> dict:
    """Derive runner/orchestrator overheads from a parsed report.

    runner_overhead       = total_active (a subagent loads <= the orchestrator
                            surface, so the full active footprint is a
                            conservative proxy for the runner's overhead).
    orchestrator_overhead = total_active - Messages (the orchestrator's own
                            conversation grows; subtract the already-counted
                            Messages so the two overheads differ by exactly the
                            Messages footprint).
    """
    total_active = int(report.get("total_active", 0))
    messages = int(report.get("categories", {}).get("Messages", 0))
    return {
        "runner_overhead": total_active,
        "orchestrator_overhead": total_active - messages,
    }


def derive_thresholds(
    session_target: int,
    runner_overhead: int,
    growth_margin: int = DEFAULT_GROWTH_MARGIN,
    output_reserve: int = DEFAULT_OUTPUT_RESERVE,
    warn_ceiling: int = DEFAULT_WARN_CEILING,
) -> dict:
    """Derive the per-task budget thresholds.

        available_per_task = session_target - runner_overhead - growth_margin
        critical           = available_per_task - output_reserve
        warn               = min(warn_ceiling, round(0.5 * available_per_task))
    """
    available_per_task = session_target - runner_overhead - growth_margin
    critical = available_per_task - output_reserve
    warn = min(warn_ceiling, round(0.5 * available_per_task))
    return {
        "available_per_task": available_per_task,
        "critical": critical,
        "warn": warn,
    }


# ---------------------------------------------------------------------------
# Capture + calibration write-back
# ---------------------------------------------------------------------------
def capture_context(plugin_root, cwd) -> str | None:
    """Run `claude -p "/context" --plugin-dir {plugin_root}` and return stdout.

    Returns None on any failure (missing binary, non-zero exit, timeout). Never
    raises — calibration degrades gracefully to the conservative fallback.

    Console-attachment gotcha (Windows): `/context` is an interactive
    slash-command the CLI only executes when a real console is attached.  Run
    directly from pipe stdio / a console-less context (Git Bash, MSYS, or a
    parent that itself has no console), `claude -p "/context"` falls through to a
    plain prompt and returns a conversational reply instead of the token
    breakdown report.  Routing the call through `powershell.exe` attaches a real
    console, so the CLI renders the report — `cmd.exe` and `conhost.exe` do NOT,
    and `winpty` would only if installed.  On POSIX the direct binary invocation
    works, so `shutil.which` resolves the binary and it is launched directly.

    `stdin` is `DEVNULL` so the child never blocks waiting on input; console
    attachment — not stdin — governs whether `/context` renders.
    """
    if os.name == "nt":
        # PowerShell attaches a console so `/context` renders (not a prompt). It
        # resolves the `claude` shim itself, so no shutil.which / shell=True here.
        inner = f'claude -p "/context" --plugin-dir "{plugin_root}"'
        cmd = ["powershell.exe", "-NoProfile", "-Command", inner]
    else:
        claude_bin = shutil.which("claude") or "claude"
        cmd = [claude_bin, "-p", "/context", "--plugin-dir", str(plugin_root)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout
    return out if out and out.strip() else None


def _format_breakdown(categories: dict) -> str:
    """Render a categories dict as a compact single-line YAML flow mapping.

    Keys are snake_cased so the value round-trips under PyYAML and stays on one
    line for the targeted regex write-back. Diagnostic only.
    """
    if not categories:
        return "{}"
    parts = []
    for name, value in categories.items():
        key = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip().lower()).strip("_")
        if not key:
            continue
        parts.append(f"{key}: {int(value)}")
    return "{" + ", ".join(parts) + "}"


def _write_back(config_path, values: dict) -> None:
    """Targeted in-place edit of the six token_saver* lines under `context:`.

    Delegates the locate-and-splice text transformation to the shared
    config.yaml `context:`-block editor (config_loader.splice_context_block):
    each requested key's value is replaced in place — comments, key order,
    and unrelated lines preserved, NO yaml.safe_dump round-trip — or appended
    under the `context:` block when absent. A key whose value is a BLOCK
    mapping rather than an inline one — which a user may hand-author, and
    which an older whole-file re-dump produced — has its parent line AND its
    whole child block replaced by the new single-line value, so no orphaned
    children are left beneath a complete value. This is the REPLACE-if-present
    policy: the opposite of init_project.merge_context_subkeys's additive,
    skip-if-present one (see that function's docstring).

    The write goes through the parse-checked writer, so an edit that would leave
    an unparseable config is rolled back and raised rather than saved.
    """
    text = config_path.read_text(encoding="utf-8")
    text = splice_context_block(text, values)
    write_config_checked(config_path, text)


def set_token_saver(config_path, enabled: bool) -> dict:
    """Flip the project-level `token_saver` toggle in config.yaml in place.

    Reuses the same comment-preserving, targeted in-place editor `calibrate`
    uses (`_write_back`) rather than a `yaml.safe_dump` round-trip, so key order,
    comments, and unrelated lines are preserved.

    The bare `token_saver:` key is anchored distinctly from the measured
    `token_saver_*` lines: `_write_back`'s per-key pattern requires a literal
    colon immediately after the key name, so writing `token_saver` matches ONLY
    the toggle line (`token_saver:`) and never `token_saver_session_target`,
    `token_saver_runner_overhead`, `token_saver_orchestrator_overhead`,
    `token_saver_context_breakdown`, or `token_saver_overhead_measured_on`.

    If the `token_saver:` line is absent (a config predating the surface), it is
    appended under the `context:` block via the same append path `_write_back`
    already uses for the measured keys.

    Returns the written boolean as `{"token_saver": enabled}` so callers can
    confirm the flip.
    """
    _write_back(config_path, {"token_saver": "true" if enabled else "false"})
    return {"token_saver": bool(enabled)}


def calibrate(
    config_path=None,
    plugin_root=None,
    cwd=None,
    capture=None,
) -> dict:
    """Capture /context, derive overheads, and write them back to config.yaml.

    Flow: capture -> parse -> derive. On a successful capture the measured
    runner/orchestrator overheads, the per-category breakdown, and the
    measured-on date are written back via the targeted in-place edit. On a
    failed capture (capture returns None) the conservative fallback overheads
    are written and the result is flagged uncalibrated.

    `capture` is injectable (defaults to `capture_context`) so the pure flow is
    testable without a live `claude` binary. When `config_path` is None the
    write-back is skipped (test/inspection mode) but the same result dict shape
    is returned.

    Returns a dict carrying the six measured values plus a `calibrated` flag:
        {
          "token_saver_runner_overhead": int,
          "token_saver_orchestrator_overhead": int,
          "token_saver_context_breakdown": dict,
          "token_saver_overhead_measured_on": str,
          "calibrated": bool,
          "uncalibrated": bool,   # convenience inverse
        }
    """
    capture_fn = capture if capture is not None else capture_context

    report_text = None
    try:
        report_text = capture_fn(plugin_root, cwd)
    except Exception:
        report_text = None

    measured_on = date.today().isoformat()

    def _write_fallback():
        """Write the conservative fallback overheads back into config.yaml."""
        if config_path is not None:
            _write_back(
                config_path,
                {
                    "token_saver_runner_overhead": FALLBACK_RUNNER_OVERHEAD,
                    "token_saver_orchestrator_overhead": FALLBACK_ORCHESTRATOR_OVERHEAD,
                    "token_saver_context_breakdown": "{}",
                    "token_saver_overhead_measured_on": f'"{measured_on}"',
                },
            )
        return {
            "token_saver_runner_overhead": FALLBACK_RUNNER_OVERHEAD,
            "token_saver_orchestrator_overhead": FALLBACK_ORCHESTRATOR_OVERHEAD,
            "token_saver_context_breakdown": {},
            "token_saver_overhead_measured_on": measured_on,
            "calibrated": False,
            "uncalibrated": True,
        }

    if not report_text:
        # Conservative fallback — degrade gracefully, do not crash init/upgrade.
        return _write_fallback()

    report = parse_context_report(report_text)

    # F2 parse guard: headless `claude -p "/context"` may return conversational
    # text instead of the structured `/context` report (the CLI treats the
    # prompt as a user message, not a slash-command).  Such a reply has no usable
    # category table; a partial/garbled report can also parse to a non-positive
    # active total (e.g. only the excluded deferred/free-space rows).  Either case
    # is NOT a valid capture — treat it like a None return and fall back to the
    # conservative overheads rather than writing runner_overhead=0 (== the active
    # total) flagged calibrated:True.  A header-absent reply whose category sum is
    # still positive remains valid (the parser's documented sum fallback).
    if not report.get("categories") or report.get("total_active", 0) <= 0:
        return _write_fallback()

    overheads = derive_overheads(report)
    breakdown = report.get("categories", {})

    result = {
        "token_saver_runner_overhead": overheads["runner_overhead"],
        "token_saver_orchestrator_overhead": overheads["orchestrator_overhead"],
        "token_saver_context_breakdown": breakdown,
        "token_saver_overhead_measured_on": measured_on,
        "calibrated": True,
        "uncalibrated": False,
    }

    if config_path is not None:
        _write_back(
            config_path,
            {
                "token_saver_runner_overhead": overheads["runner_overhead"],
                "token_saver_orchestrator_overhead": overheads["orchestrator_overhead"],
                "token_saver_context_breakdown": _format_breakdown(breakdown),
                "token_saver_overhead_measured_on": f'"{measured_on}"',
            },
        )

    return result
