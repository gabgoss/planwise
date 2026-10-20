#!/usr/bin/env python3
"""Render the finished `/planwise list` answer in one call.

Prints, in order: the drift banner (unless `--no-check`), a five-column plans
table (Abbrev, Name, Status, Created, Last Updated; the Path column is dropped
on purpose to keep the block small), and a one-line summary. `skill_preflight.py`
calls this script when the skill is invoked, and the handler's fallback calls
the same route.

CLI: python -B list_plans.py [--config PATH] [--active] [--no-check]

Every failure prints exactly one `PLANWISE_LIST_FALLBACK: <cause>` line and the
exit code is 0 on every path. Stderr stays empty on success. This script reads
files and never writes one.

All row parsing, status normalisation and drift detection come from the
plugin's own modules (`reconcile_plans`, `generate_plans_index`,
`config_loader`, `reconcile_common`); nothing here re-implements them.
"""

import argparse
import contextlib
import io
import sys
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
import config_loader
import reconcile_plans
from generate_plans_index import plans_index_path
from reconcile_common import read_text_preserving_newlines

try:
    import yaml
except ImportError:  # pragma: no cover - config_loader has a stdlib fallback parser
    yaml = None

MARKER = "PLANWISE_LIST_FALLBACK:"
BANNER_RAN = "planwise list — plans index drift audit"
BANNER_COULD_NOT_RUN = "planwise list — plans index drift audit could not run"
BANNER_LEGACY = "planwise list — legacy-shaped plans index — run /planwise upgrade"
ACTIVE_STATUSES = {"PLANNING", "READY_TO_EXECUTE", "REVIEWED", "APPROVED", "NEEDS_FIXES", "IN_PROGRESS"}
COLUMNS = ("Abbrev", "Name", "Status", "Created", "Last Updated")


def resolve_config_path(cli_config: str | None) -> Path | None:
    """`--config` if given, else the cwd-bounded upward search (cwd/config.yaml, then cwd/*/config.yaml)."""
    if cli_config:
        return Path(cli_config)
    # The handler's rule a) is `planwise/config.yaml`. The upward search visits
    # subdirectories alphabetically, so a decoy such as `app/config.yaml` would win without this check.
    preferred = Path.cwd() / "planwise" / "config.yaml"
    if preferred.is_file() and config_loader._is_planwise_config(preferred):
        return preferred
    return config_loader.find_config_upward(Path.cwd(), stop_at=Path.cwd())


def load(config_path: Path) -> dict:
    """Load the config in-process. Any stderr the loader writes is swallowed."""
    with contextlib.redirect_stderr(io.StringIO()):
        return config_loader.load_config(config_path=config_path)


def _could_not_run_lines(result: dict, index_path: Path) -> list[str]:
    """The detect-mode text for a `could-not-run` result."""
    total = result["total"]
    lines = [f"Drift audit could not run: 0 of {total} rows compared"]
    if index_path.is_file():
        lines.append("No index row matched a Master Plan on disk.")
    else:
        lines.append(f"The index is missing and the tree holds {total} Master Plans.")
    return lines


def _incomplete_lines(result: dict) -> list[str]:
    """The detect-mode text for an `incomplete` result, with the unparsed-row detail."""
    lines = [f"Drift audit incomplete: {result['compared']} of {result['total']} rows compared"]
    for anomaly in result["anomalies"]:
        if anomaly["class"] == "unparsed-rows":
            for item in anomaly["lines"]:
                lines.append(f"  - line {item['line']}: table-shaped but yields no row ({item['reason']})")
    return lines


def render_banner(result: dict, index_path: Path) -> list[str]:
    """Banner lines for a `detect_drift` result. Only a complete `ran` result may print the all-clear."""
    status = result["status"]
    compared, total = result["compared"], result["total"]
    if status == "index-missing":
        return [f"{MARKER} Plans index not found at {index_path}"]
    if status == "legacy-shape":
        return [BANNER_LEGACY, "", reconcile_plans._legacy_message(index_path)]
    if status == "could-not-run":
        lines = _could_not_run_lines(result, index_path)
        missing = sum(1 for d in result["drifts"] if d.get("class") == "missing-row")
        if missing:
            lines.append(f"{missing} Master Plan(s) on disk have no row in the index (missing-row).")
        return [BANNER_COULD_NOT_RUN, "", *lines]
    if status == "incomplete" or (compared != total and not result["drifts"] and not result["anomalies"]):
        # The second clause mirrors reconcile_plans._report_detect: rows went uncompared with nothing to report.
        return [BANNER_COULD_NOT_RUN, "", *_incomplete_lines(result)]
    return [BANNER_RAN, "", reconcile_plans._format_report(result), f"{compared} of {total} rows compared."]


def render_table(rows: list[dict]) -> list[str]:
    """Markdown table of the five columns, cells verbatim, one line per row."""
    lines = [
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "|".join("-" * (len(c) + 2) for c in COLUMNS) + "|",
    ]
    for row in rows:
        cells = (row["abbrev"], row["name"], row["status"], row["created"], row["last_updated"])
        # The parser unescapes `\|` to `|`, so re-escape it to keep the row at five cells.
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return lines


def filter_active(rows: list[dict]) -> list[dict]:
    """Rows whose leading status token is one of the six active statuses."""
    return [r for r in rows if reconcile_plans.base_token(r["status"]) in ACTIVE_STATUSES]


def summary_line(n: int, active: bool) -> str:
    if active:
        return (
            f"{n} active plan(s) shown (filtered to PLANNING, READY_TO_EXECUTE, REVIEWED, APPROVED, "
            "NEEDS_FIXES and IN_PROGRESS). Run `/planwise list` to see all."
        )
    return f"{n} plan(s) shown. Run `/planwise plan` to create a new plan."


def _build(args: argparse.Namespace) -> list[str]:
    """The full output lines, or a single marker line. Raises nothing the caller must handle except bugs."""
    cwd = Path.cwd()
    config_path = resolve_config_path(args.config)
    if config_path is None:
        return [f"{MARKER} config.yaml not found at {cwd}/config.yaml or {cwd}/*/config.yaml"]
    if not config_path.is_file():
        return [f"{MARKER} config.yaml not found at {config_path}"]
    try:
        config = load(config_path)
    except Exception as exc:
        parse_errors = (ValueError,) + ((yaml.YAMLError,) if yaml is not None else ())
        if isinstance(exc, parse_errors):
            return [f"{MARKER} config.yaml parse error at {config_path}: {exc}"]
        raise

    index_path = plans_index_path(config)
    if not index_path.is_file():
        return [f"{MARKER} Plans index not found at {index_path}"]

    out: list[str] = []
    if not args.no_check:
        out.extend(render_banner(reconcile_plans.detect_drift(config), index_path))
        out.append("")

    rows = reconcile_plans.parse_plans_index(read_text_preserving_newlines(index_path))
    if args.active:
        rows = filter_active(rows)
    if args.active and not rows:
        out.append("No active plans found (status PLANNING, READY_TO_EXECUTE, REVIEWED, APPROVED, NEEDS_FIXES or IN_PROGRESS).")
        out.append("Use `/planwise list` to see all plans.")
    else:
        out.extend(render_table(rows))
    out.append("")
    out.append(summary_line(len(rows), args.active))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the /planwise list answer.")
    parser.add_argument("--config", default=None, help="Path to config.yaml; default is the cwd-bounded search.")
    parser.add_argument("--active", action="store_true", help="Show only the six active-status plans.")
    parser.add_argument("--no-check", action="store_true", help="Skip the drift banner.")
    try:
        args, _ = parser.parse_known_args(argv)
        lines = _build(args)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - one marker line and exit 0; SystemExit covers argparse errors
        lines = [f"{MARKER} {type(exc).__name__}: {exc}"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
