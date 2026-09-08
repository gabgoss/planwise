#!/usr/bin/env python3
"""Bump the plugin's version across both manifest files in one command.

The plugin declares its version in two files that must always agree: the
repo-root marketplace manifest, and the plugin's own manifest one level
under `plugins/planwise/`. A release bump that edits only one of them
leaves the pair disagreeing -- the test suite guards against that landing
unnoticed, but this script is the tool that keeps the release step itself
from ever creating the mismatch: one command edits both files together
instead of two manual edits that can drift apart.

Usage:
    python tools/bump_version.py 1.2.0
    python tools/bump_version.py 1.2.0 --dry-run

Edits exactly the `"version": "..."` line in each manifest -- every other
line (formatting, key order, surrounding keys) is left untouched -- and
preserves each file's original line endings (CRLF or LF) exactly rather
than normalizing them to the running platform's default.

This tool intentionally lives outside `plugins/planwise/`: the marketplace
ships that entire subtree verbatim to every consumer, and a maintainer-only
release helper has no reason to be part of that distribution.
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN_PATH = REPO_ROOT / "plugins" / "planwise" / ".claude-plugin" / "plugin.json"

# Matches a JSON `"version": "..."` line, capturing the prefix up to the
# opening quote and any trailing comma/whitespace, so the substitution can
# replace only the quoted value in between.
VERSION_LINE = re.compile(r'^(\s*"version"\s*:\s*)"[^"]*"(,?\s*)$', re.MULTILINE)


def read_text_preserving_newlines(path: Path) -> str:
    """Read a file's raw text with newline="" so its original line endings
    (LF or CRLF) survive untranslated into the returned string.
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text_preserving_newlines(path: Path, content: str) -> None:
    """Write text verbatim with newline="" so no os.linesep translation
    occurs, preserving the file's original CRLF/LF exactly.
    """
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)


def bump_manifest_version(path: Path, new_version: str, dry_run: bool = False) -> bool:
    """Rewrite the `"version"` line in `path` to `new_version`.

    Returns True if a change was made (or would be made, under --dry-run),
    False if the file already declares `new_version`. Raises ValueError if
    no `"version"` line is found -- this never appends a missing key, since
    both manifests are expected to already declare one.
    """
    text = read_text_preserving_newlines(path)
    match = VERSION_LINE.search(text)
    if not match:
        raise ValueError(f'{path}: no "version" line found -- refusing to guess where to add one')

    current_version_match = re.search(r'"version"\s*:\s*"([^"]*)"', match.group(0))
    current_version = current_version_match.group(1) if current_version_match else None
    if current_version == new_version:
        return False

    new_text = VERSION_LINE.sub(rf'\1"{new_version}"\2', text, count=1)
    if not dry_run:
        write_text_preserving_newlines(path, new_text)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Bump the plugin version in both manifest files together."
    )
    parser.add_argument("version", help='Target version string, e.g. "1.2.0"')
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without writing either file",
    )
    args = parser.parse_args(argv)

    changed = []
    for path in (MARKETPLACE_PATH, PLUGIN_PATH):
        if not path.exists():
            print(f"ERROR: {path} does not exist", file=sys.stderr)
            return 2
        try:
            did_change = bump_manifest_version(path, args.version, dry_run=args.dry_run)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if did_change:
            changed.append(path)
            verb = "Would bump" if args.dry_run else "Bumped"
            print(f"{verb} {path} to {args.version!r}")
        else:
            print(f"{path} already at {args.version!r} -- no change")

    if args.dry_run:
        print(f"Dry run: {len(changed)} of 2 manifest(s) would change.")
    else:
        print(f"Done: {len(changed)} of 2 manifest(s) changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
