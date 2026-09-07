#!/usr/bin/env python3
"""Read-tool mechanical limit gates and the file-risk classifier.

These are FIXED, empirically-measured harness facts about the Read tool
(`READ_FILE_BYTE_CAP`, `READ_PAGE_CAP_TOKENS`, `BYTES_PER_TOKEN`, ...) — NOT
derived from a `/context` report and NOT written by any calibration routine.
A file can fit a project's measured session budget yet still be unreadable in
a single Read call; `classify_file` folds these mechanical gates with an
optional cost-budget gate (an externally-derived thresholds dict) and takes
the max severity.

Pure functions only — no filesystem writes, no subprocess. Re-validate the
constants via a headless CLI probe if the harness changes (see
`READ_LIMITS_MEASURED_*` so a doctor-style sweep can flag staleness).
"""

import math
import os

# ---------------------------------------------------------------------------
# FIXED Read-tool limit constants (empirically re-measured 2026-09-07 on CLI
# 2.1.263 across Haiku 4.5, Sonnet 5, Opus 5, and Fable 5 — the caps are
# identical on all four; only the tokenizer weight differs).
#
# These are mechanical harness facts about the Read tool, NOT derived from a
# `/context` report and NOT written by calibrate(). Re-validate via a headless
# `claude -p --model X` probe if the harness changes (see READ_LIMITS_MEASURED_*
# so `doctor` can flag staleness).
#
# Gate priority: tokens first, then bytes, then lines — whichever comes first.
# The binding split targets for generated artifacts are the WARN thresholds
# (so no warning ever fires), not the hard caps.
# ---------------------------------------------------------------------------

# Token page-cap gate (PRIMARY — binds first on text by ~3.6x): above this a
# single Read without an explicit `limit` returns only the first page
# (~21,200 tokens, ~85% of the cap); an explicit `limit` spanning more than
# the cap hard-errors with zero content (the error reports the exact token
# count). Warn at 22K — the warn threshold produces NO runtime marker, so it
# must be checked proactively (measure_files.py / classify_file).
READ_PAGE_CAP_TOKENS = 25000
READ_TOKEN_WARN = 22000

# Byte gate (SECONDARY, model-independent): without an offset/limit, Read
# refuses a file STRICTLY LARGER than this cap, reporting "exceeds maximum
# allowed size (256KB)". Measured boundary (2026-09-07, CLI 2.1.263): a
# 262,145-byte file refuses; a 262,144-byte file does NOT. `_read_level`
# compares with `>=`, so it flags the one exact-cap size a byte early — a
# deliberate conservatism, and unreachable in practice: 256 KiB of text is
# far past the token gate (measured 100,610 tokens) and already Critical
# there. 256 KiB hard cap; warn at 240 KiB.
READ_FILE_BYTE_CAP = 262144   # 256 * 1024
READ_BYTE_WARN = 245760       # 240 * 1024

# Line gate (DISTANT THIRD, defensive): first-page line window. Measured
# sessions saw 3,000+-line single pages, so this is a defensive gate, not a
# hard-measured harness fact; it can bind alone only on many-short-line files
# that pass the token and byte gates (e.g. 3,000 lines x ~17 B/line).
READ_LINE_CAP = 2000

# Empirical bytes-per-token ratios by model family and content class
# (harness-reported token counts / on-disk bytes). Every cell was measured
# 2026-09-07 on CLI 2.1.263 against a 150 KB corpus of its own content class;
# no cell is derived from another.
#
# The tokenizer splits by model GENERATION, not by model size: Opus 5,
# Sonnet 5 and Fable 5 report the SAME token count for the same file (a 1-2
# token spread over ~54K), and Haiku 4.5 alone is lighter, by ~1.31-1.38x.
# A superseded reading had Sonnet in a "~1.44x lighter Haiku/Sonnet family";
# that grouping is measured false, and it under-estimated Sonnet's token cost
# by ~42% — the unsafe direction, because it returns a passing verdict for a
# file the harness then refuses to read whole.
#
# A SMALLER ratio means MORE tokens per byte, so the gate-conservative choice
# is the smallest ratio available and every cell is rounded DOWN from its
# measurement. Note that code tokenizes DENSER than prose, not lighter.
#
# Measured (bytes / harness-reported tokens), before the rounding down:
#   Claude 5 family   dense-md 2.605 · prose 2.906 · code 2.783
#   Haiku 4.5         dense-md 3.540 · prose 4.023 · code 3.657
DEFAULT_BYTES_PER_TOKEN = 2.6  # most restrictive measured: dense markdown, Claude 5 tokenizer
BYTES_PER_TOKEN = {
    "opus":   {"dense-md": 2.6, "prose": 2.9, "code": 2.7},
    "fable":  {"dense-md": 2.6, "prose": 2.9, "code": 2.7},   # same tokenizer as opus (measured)
    "sonnet": {"dense-md": 2.6, "prose": 2.9, "code": 2.7},   # same tokenizer as opus (measured directly)
    "haiku":  {"dense-md": 3.5, "prose": 4.0, "code": 3.6},   # Haiku 4.5 — the one lighter family
}

# Provenance so `doctor` can flag staleness and a re-validation task can compare
# the constants against the live tool.
READ_LIMITS_MEASURED_ON = "2026-09-07"
READ_LIMITS_MEASURED_CLI = "2.1.263"

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


def bytes_per_token(model: str | None = None, content: str | None = None) -> float:
    """Return the bytes-per-token ratio for a model family / content class.

    Gate-conservative by construction: with no content class the model
    family's smallest (densest) ratio is returned, and with no/unknown model
    the overall most-restrictive measured ratio (DEFAULT_BYTES_PER_TOKEN).
    """
    family = BYTES_PER_TOKEN.get((model or "").lower())
    if not family:
        return DEFAULT_BYTES_PER_TOKEN
    if content and content in family:
        return family[content]
    return min(family.values())


def estimate_tokens(
    num_bytes: int, model: str | None = None, content: str | None = None
) -> int:
    """Estimate a byte count's token cost as bytes / bytes-per-token, rounded up."""
    if num_bytes <= 0:
        return 0
    return math.ceil(num_bytes / bytes_per_token(model, content))


def _read_level(num_bytes: int, tokens: int, line_count: int = 0) -> str:
    """Classify against the three FIXED Read-tool gates (tokens, bytes, lines)."""
    if (
        tokens >= READ_PAGE_CAP_TOKENS
        or num_bytes >= READ_FILE_BYTE_CAP
        or line_count >= READ_LINE_CAP
    ):
        return "Critical"
    if tokens >= READ_TOKEN_WARN or num_bytes >= READ_BYTE_WARN:
        return "Warn"
    return "Green"


def classify_file(
    path: str,
    model: str,
    projected_added_bytes: int = 0,
    thresholds: dict | None = None,
    content: str | None = None,
) -> dict:
    """Classify a file's read/cost risk for a given runner model.

    Folds two independent gates and takes the max severity:
      * cost gate  — token estimate vs the (optional) cost `thresholds` dict.
      * read gate  — the three FIXED mechanical Read-tool limits, in priority
                     order: token page-cap (bytes / the model's bytes-per-token
                     ratio), byte cap, and the defensive line window.

    The token estimate includes `projected_added_bytes` so a currently-safe
    file that an edit will push past a gate is flagged pre-emptively
    (estimate the delta as added lines x that file's observed bytes/line).

    A `read`-reason Critical is NOT resolvable by the 1M context exception:
    every model shares the same mechanical caps, and the Claude 5 family
    tokenizer trips the token gate on FEWER bytes; the remedy is paged reads
    (offset/limit/Grep), and for a core/to-be-edited dependency, a refactor.

    Returns {"level", "reason", "bytes", "tokens", "lines"} where level is in
    Green|Notice|Warn|Critical and reason is "cost"|"read" naming the driver.
    """
    try:
        num_bytes = os.path.getsize(path)
    except OSError:
        num_bytes = 0
    line_count = _count_lines(path)
    tokens = estimate_tokens(num_bytes + max(0, projected_added_bytes), model, content)

    cost = _cost_level(tokens, thresholds)
    read = _read_level(num_bytes + max(0, projected_added_bytes), tokens, line_count)

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
        "lines": line_count,
    }
