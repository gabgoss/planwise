#!/usr/bin/env python3
"""Check a returned runner status block against the Status-Block Return Contract.

Rule enforced: references/agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md
§1.28 "Status-Block Return Contract". Two surfaces state the schema: that
section's field table, and the return table in templates/orchestration.md.
Both list the same eight fields with these line maxima:

    TASK_STATUS 1, TASK_ID 1, ROUTE/FLAGS 1, OUTPUT_FILES 1, LINES_PRODUCED 1,
    VERIFY_RESULTS 5, KEY_FINDINGS 5, ISSUES 3; total 18.

Predicate: every required field is present once and is not blank, each field
stays within its line maximum, the block holds at most 18 lines, no line sits
before the first field, no unknown field key appears, and no fenced block
appears (clause 1 of §1.28: no re-quoted file content).

Counting: a field's lines are its header line when the header carries a value,
plus every non-blank line after it up to the next field. A bare header such as
"KEY_FINDINGS:" followed by bullets counts the bullets only. The block total is
the sum of the field counts, the same sum §1.28 derives its ceiling from.

Modes (--fields):
    eight  (default) all eight fields are required.
    six    ROUTE/FLAGS and VERIFY_RESULTS are tolerated when absent. This is
           the form the task-runner agent and the delegated §1.13 block still
           emit; use it until those surfaces adopt the eight fields.

Input, one of:
    a file path, or "-" for stdin, holding the block as plain text;
    --transcript <agent-*.jsonl>, a subagent transcript. The block is recovered
           with extract_status_block.last_block: the last transcript line that
           holds "TASK_STATUS:" is taken, and the JSON string from that key to
           its closing quote is decoded.

Exit: 0 clean; 1 on a breach (each breach printed with its line number, or a
transcript with no block); 2 on a usage error or an unreadable input.

What it cannot see: it checks Agent-tool runner returns only. A Workflow
script's agent() result is schema JSON, which §1.28 does not govern. It does
not judge content: a restated brief that fits inside its field allocation
passes, and so does an ISSUES value that hides a real issue behind "none". In
transcript mode, a block split across two transcript lines is read from the
last line only.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import re
from pathlib import Path

from extract_status_block import last_block

# The field table of §1.28 "Status-Block Return Contract" (Part-3 of the
# delegated orchestration reference), held as a constant: field -> max lines.
FIELDS: dict[str, int] = {
    "TASK_STATUS": 1,
    "TASK_ID": 1,
    "ROUTE/FLAGS": 1,
    "OUTPUT_FILES": 1,
    "LINES_PRODUCED": 1,
    "VERIFY_RESULTS": 5,
    "KEY_FINDINGS": 5,
    "ISSUES": 3,
}
TOTAL_MAX = 18
OPTIONAL_IN_SIX = frozenset({"ROUTE/FLAGS", "VERIFY_RESULTS"})

_KEY_RE = re.compile(r"^\s*([A-Z][A-Z_/]*[A-Z])\s*:[ \t]*([^\r\n]*)")
_FENCE_RE = re.compile(r"^[ \t>]*(`{3,}|~{3,})")
_TRANSCRIPT_RE = re.compile(r'TASK_STATUS:(?:[^"\\]|\\.)*')


def required_fields(mode: str) -> list[str]:
    """The fields a block must carry under ``mode`` ("six" or "eight")."""
    if mode == "six":
        return [f for f in FIELDS if f not in OPTIONAL_IN_SIX]
    return list(FIELDS)


def check_block(text: str, mode: str = "eight") -> list[str]:
    """Return one message per breach; an empty list means the block conforms."""
    breaches: list[str] = []
    counts: dict[str, int] = {}
    first_line: dict[str, int] = {}
    current: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            breaches.append(f"line {number}: fenced block (no re-quoted file content)")
        if not line.strip():
            continue
        m = _KEY_RE.match(line)
        if m and (m.group(1) in FIELDS or "_" in m.group(1) or "/" in m.group(1)):
            key = m.group(1)
            if key not in FIELDS:
                breaches.append(f"line {number}: unknown field {key}")
                current = None
                continue
            if key in counts:
                breaches.append(f"line {number}: duplicate field {key}")
            else:
                counts[key] = 0
                first_line[key] = number
            current = key
            if m.group(2).strip():
                counts[key] += 1
            continue
        if current is None:
            breaches.append(f"line {number}: text outside a field")
            continue
        counts[current] += 1
    for key in required_fields(mode):
        if key not in counts:
            breaches.append(f"missing field {key}")
    for key, count in counts.items():
        if count == 0:
            breaches.append(f"line {first_line[key]}: field {key} is blank (write none)")
        elif count > FIELDS[key]:
            breaches.append(f"line {first_line[key]}: field {key} has {count} lines, max {FIELDS[key]}")
    total = sum(counts.values())
    if total > TOTAL_MAX:
        breaches.append(f"block has {total} lines, max {TOTAL_MAX}")
    return breaches


def block_from_transcript(path: Path) -> str | None:
    """Recover the last status block from a JSONL transcript, or ``None``."""
    _scanned, _matching, block = last_block(path, _TRANSCRIPT_RE)
    if not block:
        return None
    try:
        return json.loads('"' + block[-1] + '"')
    except json.JSONDecodeError:
        return block[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a runner status block against the §1.28 Status-Block Return Contract."
    )
    parser.add_argument("block", nargs="?", help="block file, or - for stdin")
    parser.add_argument("--transcript", help="agent-*.jsonl transcript to recover the block from")
    parser.add_argument("--fields", choices=("six", "eight"), default="eight")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if bool(args.block) == bool(args.transcript):
        print("check_status_block: give exactly one of a block path or --transcript", file=sys.stderr)
        return 2
    try:
        if args.transcript:
            text = block_from_transcript(Path(args.transcript))
            if text is None:
                print(f"{args.transcript}: no status block found")
                return 1
            source = args.transcript
        elif args.block == "-":
            text = sys.stdin.read()
            source = "<stdin>"
        else:
            text = Path(args.block).read_text(encoding="utf-8")
            source = args.block
    except (OSError, UnicodeDecodeError) as exc:
        print(f"check_status_block: cannot read input: {exc}", file=sys.stderr)
        return 2
    breaches = check_block(text, args.fields)
    print(f"mode {args.fields}: {len(breaches)} breach(es) in {source}")
    for item in breaches:
        print(f"{source}: {item}")
    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
