#!/usr/bin/env python3
"""Token Saver facade: re-exports the calibration engine and the Read-tool
limit gates as a single import surface.

This module used to hold both concerns directly; they now live in two sibling
modules split along their own natural seam:

  * `context_calibration` — the *measured carrying-cost budget* (parse a
    captured `/context` report -> derive overheads/thresholds -> calibrate
    and write back to config.yaml). These numbers are MEASURED, not
    hardcoded.
  * `read_limits` — the *Read-tool mechanical limits*: FIXED,
    empirically-measured harness facts (byte cap, per-model token page-cap)
    plus `classify_file`, which folds them with an optional cost-budget gate.

`token_saver` remains importable exactly as before — every name either
module exposed, including the underscore-prefixed helpers some callers reach
through this facade, is re-exported here by explicit name so no caller needs
to change.
"""

from context_calibration import (
    DEFAULT_GROWTH_MARGIN,
    DEFAULT_OUTPUT_RESERVE,
    DEFAULT_WARN_CEILING,
    FALLBACK_ORCHESTRATOR_OVERHEAD,
    FALLBACK_RUNNER_OVERHEAD,
    _format_breakdown,
    _normalize_tokens,
    _write_back,
    attribution,
    calibrate,
    capture_context,
    derive_overheads,
    derive_thresholds,
    parse_context_report,
    set_token_saver,
)
from read_limits import (
    READ_BYTE_WARN,
    READ_FILE_BYTE_CAP,
    READ_LIMITS_MEASURED_CLI,
    READ_LIMITS_MEASURED_ON,
    READ_PAGE_CAP_TOKENS,
    READ_TOKEN_WARN,
    TOKENS_PER_LINE,
    _LEVEL_RANK,
    _LEVELS,
    _count_lines,
    _cost_level,
    _max_level,
    _read_level,
    classify_file,
)

__all__ = [
    "DEFAULT_GROWTH_MARGIN",
    "DEFAULT_OUTPUT_RESERVE",
    "DEFAULT_WARN_CEILING",
    "FALLBACK_ORCHESTRATOR_OVERHEAD",
    "FALLBACK_RUNNER_OVERHEAD",
    "READ_BYTE_WARN",
    "READ_FILE_BYTE_CAP",
    "READ_LIMITS_MEASURED_CLI",
    "READ_LIMITS_MEASURED_ON",
    "READ_PAGE_CAP_TOKENS",
    "READ_TOKEN_WARN",
    "TOKENS_PER_LINE",
    "_LEVEL_RANK",
    "_LEVELS",
    "_count_lines",
    "_cost_level",
    "_format_breakdown",
    "_max_level",
    "_normalize_tokens",
    "_read_level",
    "_write_back",
    "attribution",
    "calibrate",
    "capture_context",
    "classify_file",
    "derive_overheads",
    "derive_thresholds",
    "parse_context_report",
    "set_token_saver",
]
