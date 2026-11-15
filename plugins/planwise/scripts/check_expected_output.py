#!/usr/bin/env python3
"""Compare an Output file's measured tokens with its task's declared output budget.

Rule enforced: references/agent-orchestration-delegated.md §1.4
"Inter-Dispatch Diagnostics Verification", the orchestrator output-size
check. After a dispatch, measure every output file with measure_files.py and
compare it with the task's declared budget. A deviation above 20 % is a
signal to review before the next dispatch.

Input: a task file and one of its Output files.
    The declared budget is the "(output)" figure of the task file's
    "**Context subtotal:**" line, written "~N.NK (output)" or "~N.NK output".
    The figure is read with the pattern ~([0-9.]+)K (\\(output\\)|output\\b). A task file's Expected Output
    section lists headings only and holds no token figure.
    The Output is measured with measure_files.measure_file, the same estimate
    measure_files.py prints. --model picks the tokenizer family (default: the
    most restrictive measured ratio, as measure_files.py uses).

Exit: 0 when the deviation is at most --tolerance percent (default 20); 1
above it, printing the measured tokens, the budget and the deviation; 2 on a
usage error, an unreadable file, or a task file with no "(output)" figure.

What it cannot see: a budget declared anywhere but the Context subtotal line,
and a task with several Output files sharing one figure. The figure covers
every output the task writes, so run it on the task's main Output, or sum by
hand where the task splits its output. Token counts are byte-ratio estimates,
not tokenizer counts.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
from pathlib import Path

from measure_files import measure_file

_SUBTOTAL_RE = re.compile(r"^\s*\*\*Context subtotal:\*\*")
_OUTPUT_FIGURE_RE = re.compile(r"~([0-9.]+)K (?:\(output\)|output\b)")
_MODELS = ("haiku", "sonnet", "opus", "fable")


def declared_budget(text: str) -> int | None:
    """Declared output tokens from the Context subtotal line, or ``None``."""
    for line in text.splitlines():
        if _SUBTOTAL_RE.match(line):
            m = _OUTPUT_FIGURE_RE.search(line)
            if m:
                try:
                    return round(float(m.group(1)) * 1000)
                except ValueError:
                    return None
    return None


def deviation(measured: int, budget: int) -> float:
    """Signed deviation of ``measured`` from ``budget`` in percent."""
    return (measured - budget) * 100.0 / budget


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare an Output's measured tokens with the task's declared output budget (§1.4)."
    )
    parser.add_argument("--task", required=True, help="the task file")
    parser.add_argument("--output", required=True, help="the Output file to measure")
    parser.add_argument("--model", choices=_MODELS, help="tokenizer family for the estimate")
    parser.add_argument("--tolerance", type=float, default=20.0, help="allowed deviation in percent")
    args = parser.parse_args(argv)
    task = Path(args.task)
    try:
        text = task.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"check_expected_output: cannot read {task}: {exc}", file=sys.stderr)
        return 2
    budget = declared_budget(text)
    if not budget:
        print(f"check_expected_output: {task}: no '~N.NK (output)' figure on the Context subtotal line", file=sys.stderr)
        return 2
    try:
        measured = measure_file(args.output, args.model)["tokens"]
    except OSError as exc:
        print(f"check_expected_output: cannot measure {args.output}: {exc}", file=sys.stderr)
        return 2
    dev = deviation(measured, budget)
    line = f"{args.output}: {measured} tokens against a declared {budget} ({dev:+.1f} %, tolerance {args.tolerance:g} %)"
    if abs(dev) > args.tolerance:
        print(f"{line}: review before the next dispatch")
        return 1
    print(f"{line}: within tolerance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
