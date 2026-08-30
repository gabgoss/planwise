#!/usr/bin/env python3
"""Measure files against the Read-tool gates: bytes, KiB, lines, and tokens.

Gives handlers and agents a zero-context way to know a file's size and
estimated token cost BEFORE reading it, and ready-to-paste rows for task-file
Required Context tables and generated-artifact frontmatter.

Tokens are estimated as bytes / bytes-per-token (`read_limits.BYTES_PER_TOKEN`,
empirically measured per model family and content class); there is no offline
Claude tokenizer, so the estimate is deliberately gate-conservative — with no
`--model` it uses the overall most-restrictive measured ratio.

Each file is classified against the three Read-tool gates, in priority order
(tokens first, then bytes, then lines — whichever comes first):

  OK    below every warn threshold — readable in one Read call with margin.
  WARN  at/over the token warn (22,000) or byte warn (245,760 = 240 KiB).
  OVER  at/over the token page-cap (25,000), the byte refusal cap
        (262,144 = 256 KiB), or the defensive 2,000-line first-page window.

The binding split targets for generated artifacts are the WARN thresholds:
a generated runner-read artifact must land OK on every gate.

Usage:
  python measure_files.py FILE [FILE ...] [--model MODEL] [--content CLASS]
                          [--json] [--md]

  --model    haiku | sonnet | opus | fable — use that family's
             gate-conservative bytes-per-token ratio (omit for the overall
             most-restrictive default).
  --content  dense-md | prose | code — refine the ratio within the model
             family (requires --model to have an effect).
  --json     additionally write the result to a JSON temp file and print
             `JSON: {path}` as the last line.
  --md       emit a ready-to-paste markdown table instead of the plain report.

Exit codes: 0 on success (whatever the levels), 1 if any named file is
missing/unreadable. Stdlib-only.
"""

import argparse
import json
import os
import sys
import tempfile

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from read_limits import (  # noqa: E402
    READ_BYTE_WARN,
    READ_FILE_BYTE_CAP,
    READ_LINE_CAP,
    READ_PAGE_CAP_TOKENS,
    READ_TOKEN_WARN,
    _count_lines,
    bytes_per_token,
    estimate_tokens,
)

_MODELS = ("haiku", "sonnet", "opus", "fable")
_CONTENT_CLASSES = ("dense-md", "prose", "code")


def measure_file(path: str, model: str | None = None, content: str | None = None) -> dict:
    """Measure one existing file: bytes, KiB, lines, estimated tokens, level.

    Returns {path, bytes, kib, lines, tokens, ratio, level, gates} where
    level is OK|WARN|OVER and gates lists every fired gate in priority order
    (tokens, then bytes, then lines).
    """
    num_bytes = os.path.getsize(path)
    lines = _count_lines(path)
    ratio = bytes_per_token(model, content)
    tokens = estimate_tokens(num_bytes, model, content)

    gates = []
    if tokens >= READ_PAGE_CAP_TOKENS:
        gates.append(f"token cap (>= {READ_PAGE_CAP_TOKENS:,})")
    elif tokens >= READ_TOKEN_WARN:
        gates.append(f"token warn (>= {READ_TOKEN_WARN:,})")
    if num_bytes >= READ_FILE_BYTE_CAP:
        gates.append(f"byte cap (>= {READ_FILE_BYTE_CAP:,})")
    elif num_bytes >= READ_BYTE_WARN:
        gates.append(f"byte warn (>= {READ_BYTE_WARN:,})")
    if lines >= READ_LINE_CAP:
        gates.append(f"line cap (>= {READ_LINE_CAP:,})")

    if (
        tokens >= READ_PAGE_CAP_TOKENS
        or num_bytes >= READ_FILE_BYTE_CAP
        or lines >= READ_LINE_CAP
    ):
        level = "OVER"
    elif tokens >= READ_TOKEN_WARN or num_bytes >= READ_BYTE_WARN:
        level = "WARN"
    else:
        level = "OK"

    return {
        "path": path,
        "bytes": num_bytes,
        "kib": round(num_bytes / 1024, 1),
        "lines": lines,
        "tokens": tokens,
        "ratio": ratio,
        "level": level,
        "gates": gates,
    }


def measure_files(
    paths: list[str], model: str | None = None, content: str | None = None
) -> dict:
    """Measure a list of files; missing/unreadable paths go to `errors`."""
    files, errors = [], []
    for p in paths:
        try:
            files.append(measure_file(p, model, content))
        except OSError as exc:
            errors.append({"path": p, "error": str(exc)})
    return {
        "model": model or "default",
        "content": content,
        "ratio": bytes_per_token(model, content),
        "files": files,
        "errors": errors,
        "summary": {
            "total": len(files),
            "ok": sum(1 for f in files if f["level"] == "OK"),
            "warn": sum(1 for f in files if f["level"] == "WARN"),
            "over": sum(1 for f in files if f["level"] == "OVER"),
        },
    }


def format_report(result: dict) -> str:
    lines = [
        f"Read-gate measurement — ratio {result['ratio']} B/tok "
        f"(model={result['model']}"
        + (f", content={result['content']}" if result["content"] else "")
        + ")",
        "",
    ]
    for f in result["files"]:
        lines.append(f["path"])
        lines.append(f"  bytes:  {f['bytes']:,} ({f['kib']:,} KiB)")
        lines.append(f"  lines:  {f['lines']:,}")
        lines.append(f"  tokens: ~{f['tokens']:,}")
        detail = f" — {'; '.join(f['gates'])}" if f["gates"] else ""
        lines.append(f"  level:  {f['level']}{detail}")
    s = result["summary"]
    lines.append("")
    lines.append(
        f"{s['total']} file(s): {s['ok']} OK, {s['warn']} WARN, {s['over']} OVER"
    )
    return "\n".join(lines)


def format_md(result: dict) -> str:
    rows = [
        "| File | KiB | Lines | ~Tokens | Level |",
        "|------|----:|------:|--------:|-------|",
    ]
    for f in result["files"]:
        rows.append(
            f"| {f['path']} | {f['kib']:,} | {f['lines']:,} "
            f"| ~{f['tokens']:,} | {f['level']} |"
        )
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure files against the Read-tool gates (tokens first, then "
            "bytes, then lines): bytes, KiB, lines, estimated tokens, level."
        )
    )
    parser.add_argument("paths", nargs="+", help="file path(s) to measure")
    parser.add_argument("--model", choices=_MODELS, default=None,
                        help="model family whose bytes-per-token ratio to use")
    parser.add_argument("--content", choices=_CONTENT_CLASSES, default=None,
                        help="content class refining the ratio (with --model)")
    parser.add_argument("--json", action="store_true",
                        help="also write a JSON temp file and print its path")
    parser.add_argument("--md", action="store_true",
                        help="emit a markdown table instead of the plain report")
    args = parser.parse_args(argv)

    result = measure_files(args.paths, args.model, args.content)

    print(format_md(result) if args.md else format_report(result))

    if args.json:
        tmp_dir = tempfile.mkdtemp(prefix="planwise-measure-")
        json_path = os.path.join(tmp_dir, "measure.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"JSON: {json_path}")

    if result["errors"]:
        for e in result["errors"]:
            print(f"ERROR: {e['path']}: {e['error']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
