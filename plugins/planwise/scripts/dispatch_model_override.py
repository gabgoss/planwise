#!/usr/bin/env python3
"""Choose the dispatch model for one DELEGATED task, per the model-floor rules.

Enforces two sections of
``references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md``:

* §1.19 "Model-Floor Bridge": a task whose ``Agent:`` maps to a 200K-window
  model (Haiku 4.5) is raised to the 1M tier when its projected load
  ``I + R + ~54K + O`` exceeds the model's safe budget ``B`` (the window minus
  about 35K of headroom, so about 165K for Haiku 4.5), or when the flagged
  plan-path rule surface ``R`` alone reaches about 110K. A raise logs one
  ``MODEL FLOOR:`` line. Every other current model has a 1M window, so the
  floor stays inert for it.
* §1.20 "1M-Exception Dispatch": a task whose ``**Token Budget:**`` field
  carries ``1M-exception`` is raised to Opus/1M when the effective Token Saver
  setting is on and the declared model has a 200K window. A declared model
  that already has 1M keeps its model and logs ``1M EXCEPTION: inert``. A
  ``read``-reason Critical never raises: it logs ``paged-read required`` and
  keeps its declared model.

Model windows: Sonnet (4.6 and later), Haiku 5.5, Opus (4.6 and later) and
Fable have 1M; Haiku 4.5 has 200K. A bare Haiku (``Agent: Haiku``) is taken
as Haiku 5.5, the current model the alias names. A project pinned to Haiku 4.5
writes ``Agent: Haiku 4.5`` (``haiku-4.5`` also parses).

Inputs:

* the task file. ``**Agent:**`` gives the declared model, ``**Task ID:**``
  the id (else the file stem), ``**Token Budget:**`` the optional §1.20
  marker, written ``1M (cost)`` by the task template (``1M-exception`` is also
  read). ``I`` is the leading ``~N.NK`` figure of the ``**Context
  subtotal:**`` line and ``O`` its ``~N.NK (output`` or ``~N.NK output``
  figure; ``--input-k`` and ``--output-k`` override them.
* ``--surface-tokens N`` (the ``approx_tokens`` sum that
  ``init_project.py --doctor`` reports for flagged rules), or
  ``--doctor-report FILE`` (a saved ``--doctor`` stdout; the script reads its
  "Total always-on injected budget from flagged rules" line).
* ``--token-saver on|off``: the effective Token Saver setting for the plan.

Output: ``model: <chosen>`` on the first line, then the log line(s).

Exit contract: 0 on a decision, 2 on a usage error or an unreadable input.

What it cannot see: the Required Context rows marked "projected, re-measure at
dispatch" (step 1 of §1.19). Pass the re-measured figure with ``--input-k``.
It does not run ``--doctor`` itself, and it encodes no project-local model
policy: only the two shipped sections above.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

OVERHEAD_K = 54.0
HEADROOM_K = 35.0
SURFACE_ALONE_K = 110.0
WINDOW_K = {"haiku 4.5": 200.0, "haiku 5.5": 1000.0, "haiku": 1000.0,
            "sonnet": 1000.0, "opus": 1000.0, "fable": 1000.0}
RAISED_MODEL = "Opus"

FIELD_RE = r"(?m)^\*\*{name}:\*\*[ \t]*([^\r\n]*)"
FIGURE_RE = re.compile(r"~(\d+(?:\.\d+)?)K")
OUTPUT_RE = re.compile(r"~(\d+(?:\.\d+)?)K (?:\(output|output\b)")
ONE_M_RE = re.compile(r"1M-exception|\b1M\s*\(cost\)")
DOCTOR_TOTAL_RE = re.compile(r"Total always-on injected budget from flagged rules: ~(\d+) tokens")
DOCTOR_NONE = "No overscoped rules found."
READ_REASON_RE = re.compile(r"(?i)\bread[- ]reason\b|\breason=read\b|\bpaged-read\b")


class UsageError(Exception):
    """An input the script cannot decide on (exit 2)."""


def field(text: str, name: str) -> str | None:
    """Return the value of a ``**Name:**`` header line, or None."""
    match = re.search(FIELD_RE.format(name=re.escape(name)), text)
    return match.group(1).strip() if match else None


def subtotal_figures(text: str) -> tuple[float | None, float | None]:
    """Return (I, O) in K from the ``**Context subtotal:**`` line."""
    line = field(text, "Context subtotal")
    if line is None:
        return None, None
    first = FIGURE_RE.search(line)
    output = OUTPUT_RE.search(line)
    return (float(first.group(1)) if first else None,
            float(output.group(1)) if output else None)


def surface_from_report(report: str) -> int:
    """Return the flagged-rule token total from a saved ``--doctor`` report."""
    match = DOCTOR_TOTAL_RE.search(report)
    if match:
        return int(match.group(1))
    if DOCTOR_NONE in report:
        return 0
    raise UsageError("doctor report carries neither the flagged-rule total nor the no-overscope line")


def fmt(value: float) -> str:
    """Format a K figure with at most one decimal."""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def decide(task_id: str, declared: str, i_k: float, o_k: float, r_tokens: int,
           token_budget: str | None, token_saver: bool) -> tuple[str, list[str]]:
    """Return (chosen model, log lines) for one task."""
    key = re.sub(r"[\s_-]+", " ", declared.strip().lower())
    if key not in WINDOW_K:
        raise UsageError(f"unknown Agent model {declared!r}; expected Haiku, Haiku 4.5, "
                         "Haiku 5.5, Sonnet, Opus or Fable")
    budget = token_budget or ""
    lines: list[str] = []
    window = WINDOW_K[key]
    if token_saver and ONE_M_RE.search(budget):
        if window <= 200.0:
            lines.append(f"1M EXCEPTION: raised {task_id} {declared}→1M "
                         "(oversized indivisible file — cost-reason Critical, cannot be split)")
            return RAISED_MODEL, lines
        lines.append(f"1M EXCEPTION: inert for {task_id} {declared} "
                     "(declared model already has a 1M window)")
    r_k = r_tokens / 1000.0
    b_k = window - HEADROOM_K
    total = i_k + r_k + OVERHEAD_K + o_k
    terms = (f"inputs ~{fmt(i_k)}K + plan-path rules ~{fmt(r_k)}K + overhead ~{fmt(OVERHEAD_K)}K"
             f" + output ~{fmt(o_k)}K = ~{fmt(total)}K")
    chosen = declared
    if window <= 200.0 and (total > b_k or r_k >= SURFACE_ALONE_K):
        chosen = RAISED_MODEL
        lines.append(f"MODEL FLOOR: raised {task_id} {declared}→1M "
                     f"({terms} > {declared} safe budget ~{fmt(b_k)}K)")
    else:
        lines.append(f"MODEL FLOOR: inert for {task_id} {declared} "
                     f"({terms} <= {declared} safe budget ~{fmt(b_k)}K)")
    if READ_REASON_RE.search(budget):
        lines.append(f"paged-read required: {task_id} keeps {chosen} "
                     "(read-reason Critical — page the file, the 1M exception does not apply)")
    return chosen, lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("task", help="task file path")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--surface-tokens", type=int,
                        help="flagged plan-path rule tokens from init_project.py --doctor")
    source.add_argument("--doctor-report", help="saved init_project.py --doctor stdout")
    parser.add_argument("--token-saver", choices=("on", "off"), required=True,
                        help="effective Token Saver setting for the plan")
    parser.add_argument("--input-k", type=float, help="measured input tokens, in K")
    parser.add_argument("--output-k", type=float, help="expected output tokens, in K")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    try:
        try:
            text = Path(args.task).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise UsageError(f"cannot read task file {args.task}: {exc}") from exc
        declared = field(text, "Agent")
        if not declared:
            raise UsageError(f"{args.task}: no **Agent:** field")
        task_id = field(text, "Task ID") or Path(args.task).stem
        i_k, o_k = subtotal_figures(text)
        i_k = args.input_k if args.input_k is not None else i_k
        o_k = args.output_k if args.output_k is not None else o_k
        if i_k is None or o_k is None:
            raise UsageError(f"{args.task}: no input or output figure; pass --input-k and --output-k")
        if args.surface_tokens is not None:
            if args.surface_tokens < 0:
                raise UsageError("--surface-tokens must be 0 or more")
            r_tokens = args.surface_tokens
        else:
            try:
                report = Path(args.doctor_report).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise UsageError(f"cannot read doctor report {args.doctor_report}: {exc}") from exc
            r_tokens = surface_from_report(report)
        chosen, lines = decide(task_id, declared, i_k, o_k, r_tokens,
                               field(text, "Token Budget"), args.token_saver == "on")
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"model: {chosen}")
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
