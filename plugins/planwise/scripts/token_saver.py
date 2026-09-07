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
    empirically-measured harness facts (the token page-cap with per-model
    bytes-per-token ratios, the byte cap, and the defensive line window)
    plus `classify_file`, which folds them with an optional cost-budget gate.

`token_saver` remains importable exactly as before — every name either
module exposed, including the underscore-prefixed helpers some callers reach
through this facade, is re-exported here by explicit name so no caller needs
to change.

It is also runnable, as the driver for the `handlers/plan.md` Step 8c
large-file scan:

    python token_saver.py --scan --plan {plan_path} --config {config}

The scan walks every task's Required Context, classifies each file against
that task's assigned model, emits the recommendation blocks and the
`PAGED`/`REFACTOR` annotations, and exits non-zero when any file classifies
Warn or worse. The walker lives in `token_saver_scan`; only the entry point
is here, mirroring the split doctor already uses (`doctor_cli` over
`doctor_sweeps`).
"""

from context_calibration import (
    DEFAULT_GROWTH_MARGIN,
    DEFAULT_OUTPUT_RESERVE,
    DEFAULT_WARN_CEILING,
    FALLBACK_ORCHESTRATOR_OVERHEAD,
    FALLBACK_RUNNER_OVERHEAD,
    STRUCTURAL_FLOOR_BYTES_PER_TOKEN,
    _format_breakdown,
    _format_floor,
    _normalize_tokens,
    _write_back,
    always_load_references,
    attribution,
    calibrate,
    capture_context,
    derive_overheads,
    derive_structural_floor,
    derive_thresholds,
    parse_context_report,
    set_token_saver,
)
from read_limits import (
    BYTES_PER_TOKEN,
    DEFAULT_BYTES_PER_TOKEN,
    READ_BYTE_WARN,
    READ_FILE_BYTE_CAP,
    READ_LIMITS_MEASURED_CLI,
    READ_LIMITS_MEASURED_ON,
    READ_LINE_CAP,
    READ_PAGE_CAP_TOKENS,
    READ_TOKEN_WARN,
    _LEVEL_RANK,
    _LEVELS,
    _count_lines,
    _cost_level,
    _max_level,
    _read_level,
    bytes_per_token,
    classify_file,
    estimate_tokens,
)

__all__ = [
    "DEFAULT_GROWTH_MARGIN",
    "DEFAULT_OUTPUT_RESERVE",
    "DEFAULT_WARN_CEILING",
    "FALLBACK_ORCHESTRATOR_OVERHEAD",
    "FALLBACK_RUNNER_OVERHEAD",
    "BYTES_PER_TOKEN",
    "DEFAULT_BYTES_PER_TOKEN",
    "READ_BYTE_WARN",
    "READ_FILE_BYTE_CAP",
    "READ_LIMITS_MEASURED_CLI",
    "READ_LIMITS_MEASURED_ON",
    "READ_LINE_CAP",
    "READ_PAGE_CAP_TOKENS",
    "READ_TOKEN_WARN",
    "_LEVEL_RANK",
    "_LEVELS",
    "_count_lines",
    "_cost_level",
    "STRUCTURAL_FLOOR_BYTES_PER_TOKEN",
    "_format_breakdown",
    "_format_floor",
    "_max_level",
    "_normalize_tokens",
    "_read_level",
    "_write_back",
    "always_load_references",
    "attribution",
    "bytes_per_token",
    "calibrate",
    "capture_context",
    "classify_file",
    "derive_overheads",
    "derive_structural_floor",
    "derive_thresholds",
    "estimate_tokens",
    "parse_context_report",
    "set_token_saver",
]


def main(argv: list[str] | None = None) -> int:
    """Run the Step 8c large-file scan; delegate to the walker module.

    Imported lazily so the facade's import cost stays what it was for the many
    callers that only want the re-exported names.
    """
    from token_saver_scan import main as _scan_main

    return _scan_main(argv)


if __name__ == "__main__":
    import sys

    sys.exit(main())
