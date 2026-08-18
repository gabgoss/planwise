#!/usr/bin/env python3
"""Shared scaffolding for index-drift reconcile scripts.

A reconcile script (e.g. one comparing a denormalized index against its
source of truth) pairs a read-only `detect_drift(config)` with a
race-safe `reconcile(config)` and exposes both through an identical
`--config`/`--write`/`--json` CLI. The domain logic — what counts as
drift, and how to heal it — is intentionally NOT here; only the
scaffolding that would otherwise be re-implemented identically by every
such script lives in this module:

  - `write_json_result(result, prefix)`: write a detect_drift result to a
    JSON temp file, returning its path.
  - `format_drift_report(...)`: the shared drift/anomaly report banner
    shape, parameterized by the caller's domain-specific messages and
    per-row line renderers.
  - `run_reconcile_cli(...)`: the shared `--config`/`--write`/`--json`
    argparse wiring and control flow, parameterized by the caller's own
    config loader, index-path resolver, and detect_drift/reconcile/
    format_report functions.
  - `read_text_preserving_newlines` / `write_text_preserving_newlines`:
    the race-safe-reread + CRLF discipline a destructive reconcile write
    depends on. A destructive write must re-read the index immediately
    before writing (race-safe: a row healed by a concurrent writer since
    an earlier detect() call is read as non-drifted and left untouched)
    and must preserve the file's original line endings exactly — reading
    and writing with `newline=""` disables Python's universal-newline
    translation, so a CRLF file's `\\r\\n` round-trips byte-for-byte
    instead of being rewritten to the platform's `os.linesep` on every
    line, including ones the caller never touched.

Stdlib-only.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable


def read_text_preserving_newlines(path: Path) -> str:
    """Read a file's raw text with newline="" so its original line endings
    (LF or CRLF) survive untranslated into the returned string. Pair with
    `write_text_preserving_newlines` for a byte-exact round-trip on any
    line the caller does not modify. See the module docstring for the
    full race-safe-reread + CRLF discipline this supports.
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text_preserving_newlines(path: Path, content: str) -> None:
    """Write text verbatim with newline="" so no os.linesep translation
    occurs, preserving the file's original CRLF/LF exactly.
    """
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)


def write_json_result(result: dict, prefix: str) -> str:
    """Write a detect_drift result to a JSON temp file and return its path.

    `prefix` names the caller (e.g. "reconcile-plans-") so concurrent
    callers' temp directories stay distinguishable.
    """
    tmp_dir = tempfile.mkdtemp(prefix=prefix)
    json_path = os.path.join(tmp_dir, "drift.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return json_path


def format_drift_report(
    result: dict,
    *,
    no_drift_message: str,
    no_drift_only_message: str,
    drift_header: str,
    drift_line: Callable[[dict], str],
    anomaly_line: Callable[[dict], str],
) -> str:
    """Render a human-readable drift + anomaly report.

    Shared banner shape: an early-return "nothing to report" message when
    both `result["drifts"]` and `result["anomalies"]` are empty; otherwise
    a drift section (the caller-supplied header followed by one
    `drift_line` per drift, or `no_drift_only_message` when there are
    anomalies but no drifts) followed by a blank-line-separated anomaly
    section when anomalies exist. `drift_header` is a fully-formatted
    string (it already embeds the drift count) rather than a template,
    since callers' headers differ beyond a simple count substitution.
    `drift_line`/`anomaly_line` render one row each, since callers'
    drift/anomaly dict shapes differ.
    """
    drifts = result["drifts"]
    anomalies = result["anomalies"]
    lines = []

    if not drifts and not anomalies:
        return no_drift_message

    if drifts:
        lines.append(drift_header)
        for d in drifts:
            lines.append(drift_line(d))
    else:
        lines.append(no_drift_only_message)

    if anomalies:
        if lines:
            lines.append("")
        lines.append(f"Anomalies ({len(anomalies)}):")
        for a in anomalies:
            lines.append(anomaly_line(a))

    return "\n".join(lines)


def run_reconcile_cli(
    *,
    description: str,
    load_config: Callable[[], dict],
    resolve_index_path: Callable[[dict], Path],
    missing_index_message: Callable[[Path], str],
    detect_drift: Callable[[dict], dict],
    reconcile: Callable[[dict], int],
    format_report: Callable[[dict], str],
    json_prefix: str,
) -> None:
    """Shared CLI scaffold for a reconcile script's `main()`.

    Builds the `--config`/`--write`/`--json` argparse surface, resolves
    the index path, exits 1 with `missing_index_message(index_path)` on
    stderr if it does not exist, then dispatches: `--write` reconciles
    (printing the written count, plus a fresh `--json` detect_drift dump
    if requested); otherwise runs `detect_drift` and prints
    `format_report(result)` (plus `--json` if requested).

    Domain logic stays with the caller: `load_config`,
    `resolve_index_path`, `detect_drift`, `reconcile`, and `format_report`
    are all supplied by it, since different callers locate their index
    differently (a function call vs. a config dict key) and implement
    different drift semantics. `--config` is declared for the `--help`
    surface and so an explicit `--config <path>` on the command line does
    not trip `parse_known_args`; `load_config` itself is responsible for
    reading it back out of `sys.argv` (matching `config_loader.load_config`'s
    own contract), not this scaffold.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml; overrides default config search.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Reconcile drifted rows (re-reads the index immediately before writing).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Additionally write a JSON temp file and print its path.",
    )

    args, _ = parser.parse_known_args()

    config = load_config()
    index_path = resolve_index_path(config)

    if not index_path.exists():
        print(missing_index_message(index_path), file=sys.stderr)
        sys.exit(1)

    if args.write:
        written = reconcile(config)
        print(f"Reconciled {written} row(s).")
        if args.json:
            result = detect_drift(config)
            json_path = write_json_result(result, json_prefix)
            print(f"JSON: {json_path}")
        return

    result = detect_drift(config)
    print(format_report(result))

    if args.json:
        json_path = write_json_result(result, json_prefix)
        print(f"JSON: {json_path}")
