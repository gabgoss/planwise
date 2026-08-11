#!/usr/bin/env python3
"""Read-tool mechanical limit gates and the file-risk classifier.

These are FIXED, empirically-measured harness facts about the Read tool
(`READ_FILE_BYTE_CAP`, `READ_PAGE_CAP_TOKENS`, `TOKENS_PER_LINE`, ...) — NOT
derived from a `/context` report and NOT written by any calibration routine.
A file can fit a project's measured session budget yet still be unreadable in
a single Read call; `classify_file` folds these mechanical gates with an
optional cost-budget gate (an externally-derived thresholds dict) and takes
the max severity.

Pure functions only — no filesystem writes, no subprocess. Re-validate the
constants via a headless CLI probe if the harness changes (see
`READ_LIMITS_MEASURED_*` so a doctor-style sweep can flag staleness).
"""

import os

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

_LEVELS = ("Green", "Notice", "Warn", "Critical")
_LEVEL_RANK = {name: i for i, name in enumerate(_LEVELS)}


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
