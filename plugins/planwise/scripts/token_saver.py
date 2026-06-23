#!/usr/bin/env python3
"""Token Saver budget engine: /context parser, overhead/threshold derivation,
calibration capture/write-back, and the FIXED Read-tool limit gates.

Two independent concerns live here:

  1. The *measured carrying-cost budget* — derived from a captured `/context`
     report. `parse_context_report` -> `derive_overheads` -> `derive_thresholds`
     turn a real session footprint into a per-task token ceiling, and
     `calibrate` captures + writes those measured values back into config.yaml.
     These numbers are MEASURED, not hardcoded.

  2. The *Read-tool mechanical limits* — FIXED, empirically-measured harness
     facts (`READ_FILE_BYTE_CAP`, `READ_PAGE_CAP_TOKENS`, `TOKENS_PER_LINE`,
     ...). A file can fit the session budget yet still be unreadable in a single
     Read call. These constants are NOT `/context`-derived and are NOT written
     by `calibrate()`; `classify_file` folds them with the cost thresholds.

Pure functions (parser/derivation/classifier) shell out to nothing, so they are
unit-testable without a live `claude` binary. Only `capture_context` /
`calibrate` touch the filesystem or subprocess. Stdlib-only (re, os, subprocess,
datetime) — this is a script, not a workflow.
"""

import os
import re
import subprocess
from datetime import date

# ---------------------------------------------------------------------------
# FIXED Read-tool limit constants (empirically measured 2026-06-23).
#
# These are mechanical harness facts about the Read tool, NOT derived from a
# `/context` report and NOT written by calibrate(). Re-validate via a headless
# `claude -p --model X` probe if the harness changes (see READ_LIMITS_MEASURED_*
# so `doctor` can flag staleness).
# ---------------------------------------------------------------------------

# Byte gate (model-independent): Read refuses a file >= this size without an
# offset/limit. 256 KiB hard cap; warn at 240 KiB.
READ_FILE_BYTE_CAP = 262144   # 256 * 1024
READ_BYTE_WARN = 245760       # 240 * 1024

# Token page-cap gate (model-dependent): above this a single Read returns only
# the first page (truncates). Warn at 22K.
READ_PAGE_CAP_TOKENS = 25000
READ_TOKEN_WARN = 22000

# Per-model tokens-per-line. Opus tokenizes ~1.44x heavier than Sonnet/Haiku,
# so it trips the page-cap sooner (~1340 lines vs ~1920 for Sonnet/Haiku).
TOKENS_PER_LINE = {"haiku": 13, "sonnet": 13, "opus": 19}

# Provenance so `doctor` can flag staleness and a re-validation task can compare
# the constants against the live tool.
READ_LIMITS_MEASURED_ON = "2026-06-23"
READ_LIMITS_MEASURED_CLI = "2.1.186"

# ---------------------------------------------------------------------------
# Derivation defaults (must match the calibration tests).
# ---------------------------------------------------------------------------
DEFAULT_GROWTH_MARGIN = 6000
DEFAULT_OUTPUT_RESERVE = 10000
DEFAULT_WARN_CEILING = 40000

# Conservative fallback overheads, written when a /context capture fails.
FALLBACK_RUNNER_OVERHEAD = 54000
FALLBACK_ORCHESTRATOR_OVERHEAD = 60000

_LEVELS = ("Green", "Notice", "Warn", "Critical")
_LEVEL_RANK = {name: i for i, name in enumerate(_LEVELS)}


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

        cells = [c.strip() for c in line.strip("|").split("|")]
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
# Read-tool classification
# ---------------------------------------------------------------------------
def _count_lines(path: str) -> int:
    """Count newline-delimited lines in a text file (best-effort, binary-safe)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return 0
    if not data:
        return 0
    lines = data.count(b"\n")
    if not data.endswith(b"\n"):
        lines += 1
    return lines


def _max_level(a: str, b: str) -> str:
    return a if _LEVEL_RANK[a] >= _LEVEL_RANK[b] else b


def _cost_level(tokens: int, thresholds: dict | None) -> str:
    """Classify a token estimate against the cost thresholds, if provided."""
    if not thresholds:
        return "Green"
    critical = thresholds.get("critical")
    warn = thresholds.get("warn")
    if critical is not None and tokens >= critical:
        return "Critical"
    if warn is not None and tokens >= warn:
        return "Warn"
    return "Green"


def _read_level(num_bytes: int, tokens: int) -> str:
    """Classify against the two FIXED Read-tool gates."""
    if num_bytes >= READ_FILE_BYTE_CAP or tokens >= READ_PAGE_CAP_TOKENS:
        return "Critical"
    if num_bytes >= READ_BYTE_WARN or tokens >= READ_TOKEN_WARN:
        return "Warn"
    return "Green"


def classify_file(
    path: str,
    model: str,
    projected_added_lines: int = 0,
    thresholds: dict | None = None,
) -> dict:
    """Classify a file's read/cost risk for a given runner model.

    Folds two independent gates and takes the max severity:
      * cost gate  — token estimate vs the (optional) cost `thresholds` dict.
      * read gate  — the two FIXED mechanical Read-tool limits (byte cap and
                     per-model token page-cap).

    The token estimate includes `projected_added_lines` so a currently-safe
    file that an edit will push past a gate is flagged pre-emptively.

    A `read`-reason Critical is NOT resolvable by the 1M context exception:
    Opus shares the same mechanical gates and trips the token gate sooner; the
    remedy is paged reads (offset/limit/Grep), and for a core/to-be-edited
    dependency, a refactor.

    Returns {"level", "reason", "bytes", "tokens"} where level is in
    Green|Notice|Warn|Critical and reason is "cost"|"read" naming the driver.
    """
    per_line = TOKENS_PER_LINE.get(model, TOKENS_PER_LINE["sonnet"])
    try:
        num_bytes = os.path.getsize(path)
    except OSError:
        num_bytes = 0
    line_count = _count_lines(path)
    tokens = (line_count + max(0, projected_added_lines)) * per_line

    cost = _cost_level(tokens, thresholds)
    read = _read_level(num_bytes, tokens)

    level = _max_level(cost, read)
    # reason names whichever gate drove the final level; ties go to read because
    # a mechanical read failure is the more actionable (un-resolvable-by-1M)
    # signal.
    if _LEVEL_RANK[read] >= _LEVEL_RANK[cost] and read != "Green":
        reason = "read"
    elif cost != "Green":
        reason = "cost"
    else:
        reason = "read"

    return {
        "level": level,
        "reason": reason,
        "bytes": num_bytes,
        "tokens": tokens,
    }


# ---------------------------------------------------------------------------
# Capture + calibration write-back
# ---------------------------------------------------------------------------
def capture_context(plugin_root, cwd) -> str | None:
    """Run `claude -p "/context" --plugin-dir {plugin_root}` and return stdout.

    Returns None on any failure (missing binary, non-zero exit, timeout). Never
    raises — calibration degrades gracefully to the conservative fallback.
    """
    try:
        proc = subprocess.run(
            ["claude", "-p", "/context", "--plugin-dir", str(plugin_root)],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=120,
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

    Regex-replaces only each `token_saver_*:` line value (comments, key order,
    and unrelated lines preserved). NO yaml.safe_dump round-trip. A key absent
    from the file (pre-migration config) is appended under the `context:` block.
    """
    text = config_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Locate the context: block so a missing key can be appended in place.
    header_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^context:\s*$", line):
            header_idx = i
            break

    subkey_indent = "  "
    block_end = len(lines)
    if header_idx is not None:
        found_indent = False
        block_end = len(lines)
        for j in range(header_idx + 1, len(lines)):
            ln = lines[j]
            if ln.strip() == "" or ln.lstrip().startswith("#"):
                continue
            m = re.match(r"^(\s+)\S", ln)
            if m:
                if not found_indent:
                    subkey_indent = m.group(1)
                    found_indent = True
                continue
            block_end = j
            break
        while block_end - 1 > header_idx:
            prev = lines[block_end - 1]
            if prev.strip() == "" or prev.lstrip().startswith("#"):
                block_end -= 1
            else:
                break

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
            text = text[: m.start()] + replacement + text[m.end():]
        else:
            appended.append(f"{subkey_indent}{key}: {value}")

    if appended:
        lines = text.split("\n")
        # Recompute block_end on the (possibly) mutated text for a clean insert.
        h2 = None
        for i, line in enumerate(lines):
            if re.match(r"^context:\s*$", line):
                h2 = i
                break
        insert_at = len(lines)
        if h2 is not None:
            insert_at = len(lines)
            for j in range(h2 + 1, len(lines)):
                ln = lines[j]
                if ln.strip() == "" or ln.lstrip().startswith("#"):
                    continue
                if re.match(r"^(\s+)\S", ln):
                    continue
                insert_at = j
                break
            while insert_at - 1 > h2:
                prev = lines[insert_at - 1]
                if prev.strip() == "" or prev.lstrip().startswith("#"):
                    insert_at -= 1
                else:
                    break
        lines = lines[:insert_at] + appended + lines[insert_at:]
        text = "\n".join(lines)

    config_path.write_text(text, encoding="utf-8")


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

    if not report_text:
        # Conservative fallback — degrade gracefully, do not crash init/upgrade.
        result = {
            "token_saver_runner_overhead": FALLBACK_RUNNER_OVERHEAD,
            "token_saver_orchestrator_overhead": FALLBACK_ORCHESTRATOR_OVERHEAD,
            "token_saver_context_breakdown": {},
            "token_saver_overhead_measured_on": measured_on,
            "calibrated": False,
            "uncalibrated": True,
        }
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
        return result

    report = parse_context_report(report_text)
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
