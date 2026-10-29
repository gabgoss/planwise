#!/usr/bin/env python3
"""Fail loudly when a plan names a stale versioned plugin-cache script path.

A task file that runs a plugin script through a versioned cache path keeps
running the OLD tool after an upgrade, because the old cache directory stays
on disk. Every gate then passes against the wrong tool. This script scans a
plan's markdown files for paths of the form
`planwise/<digits>.<digits>.<digits>[.<digits>]/scripts/` (regex:
`planwise[\\/](\\d+(?:\\.\\d+){2,3})[\\/]scripts[\\/]`) and reports every one whose
version differs from the pinned `plugin_version` in config.yaml.

When a file holds a stale path, the script also lists each Sonnet-denominated
token target in that file. Those targets were sized with the old
bytes-per-token ratio and may be unreachable under the installed tool.

This script is non-mutating: it only reads files and prints findings. It never
writes, stages, or deletes anything.

Usage (placeholder forms only):
    python check_plan_plugin_paths.py --config {planwise_root}/config.yaml {plan_path}

{plan_path} is a plan folder or one markdown file. Files under a directory
named Outputs or Reviews, and files named *-Recovery.md or *-Summary.md, are
records rather than gates and are skipped.

Exit code: 0 when at least one file was scanned and no path is stale; 1 when a
stale path is found; 2 when the check could not run (config unreadable,
plugin_version absent, plan path missing, or zero files scanned). Exit 2 is
never a pass. The first stdout line is always the coverage line.
"""

import argparse
import re
import sys
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from config_loader import load_config

PATH_RE = re.compile(r"planwise[\\/](\d+(?:\.\d+){2,3})[\\/]scripts[\\/]")
RATIO_RE = re.compile(r"~?\d[\d,]*(?:\.\d+)?K?[ -]Sonnet[ -]tokens?", re.IGNORECASE)
SKIP_DIRS = {"Outputs", "Reviews"}
SKIP_SUFFIXES = ("-Recovery.md", "-Summary.md")


def _not_checked(reason: str) -> None:
    print(f"NOT CHECKED: {reason}")
    sys.exit(2)


def _pinned_version(config_path: Path) -> str:
    if not config_path.is_file():
        _not_checked(f"config file not found: {config_path}")
    try:
        config = load_config(config_path=config_path)
    except (OSError, ValueError, KeyError, TypeError, SystemExit) as exc:
        _not_checked(f"config unreadable: {exc}")
    pinned = config.get("plugin_version") if isinstance(config, dict) else None
    if not pinned:
        _not_checked("plugin_version is absent from the config")
    return str(pinned)


def _collect_files(plan_path: Path) -> list[Path]:
    if plan_path.is_file():
        return [plan_path] if plan_path.suffix == ".md" else []
    files = []
    for path in sorted(plan_path.rglob("*.md")):
        rel_dirs = set(path.relative_to(plan_path).parts[:-1])
        if rel_dirs & SKIP_DIRS or path.name.endswith(SKIP_SUFFIXES):
            continue
        files.append(path)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail when a plan's markdown names a versioned plugin-cache "
        "script path that differs from the pinned plugin_version."
    )
    parser.add_argument("--config", required=True, help="Path to config.yaml")
    parser.add_argument("plan_path", help="Plan folder or one markdown file")
    args = parser.parse_args()

    pinned = _pinned_version(Path(args.config))
    plan_path = Path(args.plan_path)
    if not plan_path.exists():
        _not_checked(f"plan path not found: {plan_path}")

    files = _collect_files(plan_path)
    if not files:
        _not_checked(f"zero markdown files scanned under {plan_path}")

    total_paths = 0
    stale_lines: list[str] = []
    ratio_lines: list[str] = []
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        stale_here = []
        for number, line in enumerate(lines, start=1):
            for match in PATH_RE.finditer(line):
                total_paths += 1
                if match.group(1) != pinned:
                    stale_here.append(
                        f"[STALE] {path}:{number} names {match.group(1)}, pinned {pinned}"
                    )
        stale_lines.extend(stale_here)
        if not stale_here:
            continue
        for number, line in enumerate(lines, start=1):
            for match in RATIO_RE.finditer(line):
                ratio_lines.append(
                    f'[RATIO] {path}:{number} Sonnet-denominated target "{match.group(0)}" '
                    "may carry the old bytes-per-token ratio"
                )

    print(
        f"Coverage: scanned {len(files)} files; {total_paths} versioned paths; "
        f"{len(stale_lines)} stale."
    )
    for line in stale_lines + ratio_lines:
        print(line)
    if stale_lines:
        if ratio_lines:
            print(
                f"{len(ratio_lines)} Sonnet-denominated target(s) share a file with a stale "
                "path. State them in bytes, or re-measure them with the installed tool."
            )
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
