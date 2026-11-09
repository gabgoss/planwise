#!/usr/bin/env python3
"""Read-only check: is the running planwise copy the project's marketplace install?

`/planwise init` runs this before it creates anything. Claude Code can run
planwise from any copy it loads: a project-scope marketplace install, a
user-scope install, an account-synced copy, or a `--plugin-dir` dev tree. Init
used to trust whichever copy ran it, so a stale copy could pin its own
`plugin_root` into a new project. This module compares the running copy with
the install record Claude Code keeps, and returns one verdict:

- `OK`: the running root is the install that applies to this project, and its
  version is not older than the marketplace clone's.
- `NOT_MARKETPLACE_INSTALL`: no `planwise@{marketplace}` install applies to this
  project, or the one that applies has a different `installPath`.
- `BEHIND_MARKETPLACE`: the running copy is the applicable install, but the
  marketplace clone carries a newer version.

The install that applies is the first match in this order: the `local` entry for
this `projectPath`, then the `project` entry for it, then the `user` entry.
Paths compare with case and separators normalised.

`check()` reads files only. The CLI's `--refresh` flag first runs
`claude plugin marketplace update {marketplace}`. A failed refresh prints a
`refresh failed:` line and the check runs against the clone as it is.

CLI: python -B install_check.py [--project-root PATH] [--running-root PATH]
                                [--config-dir PATH] [--refresh] [--json]
Prints one `INSTALL_CHECK: {verdict} ...` line. Exit 0 for every verdict, and 1
for a usage error.
"""

import argparse
import json
import os
import posixpath
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

PLUGIN_NAME = "planwise"
OK = "OK"
NOT_MARKETPLACE_INSTALL = "NOT_MARKETPLACE_INSTALL"
BEHIND_MARKETPLACE = "BEHIND_MARKETPLACE"
SCOPE_ORDER = ("local", "project", "user")
REFRESH_TIMEOUT = 120


def norm(path) -> str:
    """Case- and separator-normalised form of a path, for comparison only."""
    text = str(path).replace("\\", "/")
    text = posixpath.normpath(text) if text else text
    return text.rstrip("/").lower()


def version_tuple(text) -> tuple:
    parts = [int(p) for p in "".join(c if c.isdigit() else " " for c in str(text or "")).split()]
    return tuple(parts)


def compare_versions(a: str, b: str) -> int:
    """-1, 0 or 1 per numeric component, zero-padded."""
    ta, tb = version_tuple(a), version_tuple(b)
    size = max(len(ta), len(tb))
    ta, tb = ta + (0,) * (size - len(ta)), tb + (0,) * (size - len(tb))
    return (ta > tb) - (ta < tb)


def default_config_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def plugin_version(root) -> "str | None":
    data = _read_json(Path(root) / ".claude-plugin" / "plugin.json")
    if isinstance(data, dict) and data.get("version"):
        return str(data["version"])
    return None


def marketplace_name(running_root, installed: dict) -> "str | None":
    """The marketplace a cache path names, else the only `planwise@*` key."""
    parts = norm(running_root).split("/")
    for i in range(len(parts) - 3):
        if parts[i:i + 2] == ["plugins", "cache"] and parts[i + 3] == PLUGIN_NAME:
            # norm() lower-cases; recover the key's own spelling from the install record.
            lowered = parts[i + 2]
            for key in installed:
                if key.lower() == f"{PLUGIN_NAME}@{lowered}":
                    return key.split("@", 1)[1]
            return lowered
    keys = [k for k in installed if k.split("@", 1)[0] == PLUGIN_NAME and "@" in k]
    if len(keys) == 1:
        return keys[0].split("@", 1)[1]
    return None


def applicable_entry(entries: list, project_root) -> "dict | None":
    """The install entry that applies to the project: local, then project, then user."""
    want = norm(project_root)
    for scope in SCOPE_ORDER:
        matches = [
            e for e in entries
            if isinstance(e, dict) and e.get("scope") == scope
            and (scope == "user" or norm(e.get("projectPath", "")) == want)
        ]
        if matches:
            return max(matches, key=lambda e: str(e.get("lastUpdated", "")))
    return None


def marketplace_clone(config_dir, marketplace) -> "tuple[str | None, str | None]":
    """The version the marketplace clone carries, and the clone's `lastUpdated`."""
    known = _read_json(Path(config_dir) / "plugins" / "known_marketplaces.json")
    if not isinstance(known, dict) or not isinstance(known.get(marketplace), dict):
        return None, None
    record = known[marketplace]
    last_updated = record.get("lastUpdated")
    location = record.get("installLocation")
    if not location:
        return None, last_updated
    clone = Path(location)
    manifest = _read_json(clone / ".claude-plugin" / "marketplace.json")
    source = None
    if isinstance(manifest, dict):
        for plugin in manifest.get("plugins") or []:
            if isinstance(plugin, dict) and plugin.get("name") == PLUGIN_NAME:
                source = plugin.get("source")
                break
    if isinstance(source, str):
        version = plugin_version(clone / source)
        if version:
            return version, last_updated
    return plugin_version(clone / "plugins" / PLUGIN_NAME), last_updated


def check(running_root, project_root, config_dir) -> dict:
    """Return the verdict for the running copy. Reads files only; never writes."""
    result = {
        "verdict": NOT_MARKETPLACE_INSTALL,
        "running_root": Path(str(running_root)).as_posix(),
        "running_version": plugin_version(running_root),
        "marketplace": None,
        "marketplace_version": None,
        "clone_last_updated": None,
        "scope": None,
        "install_path": None,
        "reason": "",
    }
    data = _read_json(Path(config_dir) / "plugins" / "installed_plugins.json")
    installed = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(installed, dict):
        result["reason"] = "installed_plugins.json is missing or unreadable"
        return result
    marketplace = marketplace_name(running_root, installed)
    result["marketplace"] = marketplace
    if marketplace is None:
        result["reason"] = "no planwise marketplace install is recorded"
        return result
    version, last_updated = marketplace_clone(config_dir, marketplace)
    result["marketplace_version"] = version
    result["clone_last_updated"] = last_updated
    entry = applicable_entry(installed.get(f"{PLUGIN_NAME}@{marketplace}") or [], project_root)
    if entry is None:
        result["reason"] = f"no {PLUGIN_NAME}@{marketplace} install applies to this project"
        return result
    result["scope"] = entry.get("scope")
    install_path = entry.get("installPath") or ""
    result["install_path"] = Path(install_path).as_posix() if install_path else None
    if norm(install_path) != norm(running_root):
        result["reason"] = "the running copy is not the install that applies to this project"
        return result
    running = result["running_version"]
    if version and running and compare_versions(running, version) < 0:
        result["verdict"] = BEHIND_MARKETPLACE
        result["reason"] = f"the marketplace carries {version}, newer than the running {running}"
        return result
    result["verdict"] = OK
    return result


def refresh(marketplace) -> "str | None":
    """Run `claude plugin marketplace update`. Return None on success, else the cause."""
    if not marketplace:
        return "no marketplace name to refresh"
    exe = shutil.which("claude")
    if exe is None:
        return "claude is not on PATH"
    try:
        proc = subprocess.run(
            [exe, "plugin", "marketplace", "update", marketplace],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=REFRESH_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return f"exit {proc.returncode}" + (f": {detail[-1]}" if detail else "")
    return None


def format_line(result: dict) -> str:
    def val(key):
        value = result.get(key)
        return "none" if value in (None, "") else str(value)

    return (
        f"INSTALL_CHECK: {result['verdict']} running={val('running_version')} "
        f"marketplace={val('marketplace_version')} marketplace_name={val('marketplace')} "
        f"scope={val('scope')} install_path={val('install_path')} running_root={val('running_root')}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check that the running planwise copy is the project's install.")
    parser.add_argument("--project-root", default=os.getcwd())
    parser.add_argument("--running-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--refresh", action="store_true",
                        help="run `claude plugin marketplace update` before the check")
    parser.add_argument("--json", action="store_true", help="also print the result as one JSON line")
    args = parser.parse_args(argv)
    config_dir = Path(args.config_dir) if args.config_dir else default_config_dir()

    if args.refresh:
        data = _read_json(config_dir / "plugins" / "installed_plugins.json")
        installed = data.get("plugins") if isinstance(data, dict) else None
        name = marketplace_name(args.running_root, installed if isinstance(installed, dict) else {})
        cause = refresh(name)
        if cause is not None:
            _, last_updated = marketplace_clone(config_dir, name) if name else (None, None)
            print(f"refresh failed: {cause}")
            print(f"Using the marketplace clone as it is (lastUpdated={last_updated or 'unknown'}).")

    result = check(args.running_root, args.project_root, config_dir)
    print(format_line(result))
    if result["reason"]:
        print(f"reason: {result['reason']}")
    if args.json:
        print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
