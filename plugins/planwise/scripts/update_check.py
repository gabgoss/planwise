#!/usr/bin/env python3
"""Is a newer planwise available, installed or needed by this project?

`check` computes one verdict from the running plugin root, the project root and
an optional latest version, and prints one JSON line. Precedence runs top to
bottom, and the first match wins:

- `CURRENT` (pin newer): a config is found and its pin is newer than the
  running copy. A newer install is already in use elsewhere.
- `RESTART`: the running copy is a marketplace cache copy, an install entry
  applies to the project with a different `installPath`, and that install is
  newer than the running copy.
- `PLUGIN_BEHIND`: the running root is the applicable install, and the latest
  version is newer than the running copy.
- `PROJECT_BEHIND`: a config is found and its pin is older than the running copy.
- `CURRENT`: none of the above.

A `--plugin-dir` run is not a marketplace cache copy, so `RESTART` and
`PLUGIN_BEHIND` cannot apply to it. `PROJECT_BEHIND` still can.

"Latest" is the higher of `--latest` and the marketplace clone's version. Both
tag shapes parse: `planwise--vX.Y.Z` and a bare version such as `1.0.5.4`. A
prerelease (`1.0.9-rc1`) is never "latest".

`update` runs `claude plugin marketplace update <mp>`, then
`claude plugin update planwise@<mp> --scope <scope> --json`. It never passes
`-y` or `--accept-command`, because the CLI ignores both inside a Claude Code
session. When the marketplace declares a command that needs a person to accept it,
the CLI refuses with exit code 1. The refusal is reported as `NEEDS_CONFIRM` with
exit code 3: `command` holds the declared command, and `retry` holds the command
the person runs in a terminal. The pending-upgrade marker lives in the plugin
store, which only the TypeScript module can write, so this script writes no
marker file.

`check()` reads files only. It makes no network call and starts no process.

CLI: python -B update_check.py check  --running-root R --project-root P [--latest V] [--data-dir D]
     python -B update_check.py update --running-root R --project-root P [--data-dir D]
Exit codes: check 0, usage 2. update 0 updated, 3 NEEDS_CONFIRM, 1 failed, 2 usage.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

import install_check

CURRENT = "CURRENT"
RESTART = "RESTART"
PLUGIN_BEHIND = "PLUGIN_BEHIND"
PROJECT_BEHIND = "PROJECT_BEHIND"

UPDATED = "UPDATED"
NEEDS_CONFIRM = "NEEDS_CONFIRM"
FAILED = "FAILED"
EXIT_UPDATED, EXIT_FAILED, EXIT_USAGE, EXIT_NEEDS_CONFIRM = 0, 1, 2, 3

# Where the pending-upgrade marker lives and where the opt-out is read. The
# marker lives in the plugin store, which Python cannot read. The opt-out is a
# userConfig option, which the TypeScript module reads. So `pending` and
# `opt_out` are always null here.
MARKER_HOME = "store"
OPT_OUT_HOME = "userConfig"

UPDATE_TIMEOUT = 300
TAG_PREFIX = "planwise--v"
_PLAIN_VERSION = re.compile(r"\d+(?:\.\d+)+")
# The key a `claude plugin ... --json` result uses when a marketplace declares a command that a
# person must accept. Measured on CLI 2.1.330 on `plugin install`, and named by the help of
# `plugin update`. See confirm_command().
_SHOWN_COMMAND_KEY = "shownCommand"
_OUTCOME_OK = "ok"


# --- version helpers -------------------------------------------------------

def parse_version(text) -> "str | None":
    """The plain version a tag or version string names, else None.

    Accepts `planwise--vX.Y.Z` and a bare dotted version. A prerelease suffix
    (`-rc1`, `-beta`) or any other text returns None, so it is never "latest".
    """
    if text is None:
        return None
    value = str(text).strip().removeprefix(TAG_PREFIX)
    return value if _PLAIN_VERSION.fullmatch(value) else None


def newer(a, b) -> bool:
    """True when both versions parse and `a` is newer than `b`."""
    return bool(a) and bool(b) and install_check.compare_versions(a, b) > 0


def highest(*versions) -> "str | None":
    """The highest parseable version, else None. Prereleases are skipped."""
    best = None
    for candidate in versions:
        parsed = parse_version(candidate)
        if parsed and (best is None or install_check.compare_versions(parsed, best) > 0):
            best = parsed
    return best


# --- file readers ----------------------------------------------------------

def _installed_plugins(config_dir: Path) -> dict:
    data = install_check._read_json(config_dir / "plugins" / "installed_plugins.json")
    installed = data.get("plugins") if isinstance(data, dict) else None
    return installed if isinstance(installed, dict) else {}


def marketplace_record(config_dir: Path, marketplace) -> "dict | None":
    """The marketplace's record in `known_marketplaces.json`, else None."""
    if not marketplace:
        return None
    known = install_check._read_json(config_dir / "plugins" / "known_marketplaces.json")
    record = known.get(marketplace) if isinstance(known, dict) else None
    return record if isinstance(record, dict) else None


def repo_of(record) -> "str | None":
    """`owner/name` for a `github` source, None for any other source or no record."""
    source = record.get("source") if isinstance(record, dict) else None
    if isinstance(source, dict) and source.get("source") == "github":
        repo = source.get("repo")
        if isinstance(repo, str) and re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            return repo
    return None


def auto_update_of(record) -> "bool | None":
    value = record.get("autoUpdate") if isinstance(record, dict) else None
    return value if isinstance(value, bool) else None


def read_pin(project_root) -> "tuple[str | None, str | None]":
    """The project's `plugin_version:` pin and its config path, through the
    config lookup `version_notice.py` uses. Imported here, not at module level,
    so `version_notice.py` can import this module without a cycle."""
    try:
        import version_notice

        config = version_notice.resolve_config(Path(project_root))
        if config is None:
            return None, None
        pin = version_notice._pinned_version(config) or None
        return pin, Path(config).as_posix()
    except Exception:  # noqa: BLE001 - a banner check must never fail on a config
        return None, None


def is_cache_copy(running_root) -> bool:
    """True when the running root sits in a marketplace cache, not a `--plugin-dir` tree."""
    parts = install_check.norm(running_root).split("/")
    return any(
        parts[i:i + 2] == ["plugins", "cache"] and parts[i + 3] == install_check.PLUGIN_NAME
        for i in range(len(parts) - 3)
    )


# --- check -----------------------------------------------------------------

def check(running_root, project_root, latest=None, data_dir=None) -> dict:
    """Return the verdict and its fields. Reads files only.

    `data_dir` is accepted for the CLI contract and unused: the pending marker
    lives in the plugin store, so `pending` is always None.
    """
    del data_dir  # the store branch reads no marker file
    config_dir = install_check.default_config_dir()
    running = install_check.plugin_version(running_root)
    installed_map = _installed_plugins(config_dir)
    marketplace = install_check.marketplace_name(running_root, installed_map)
    entry = None
    if marketplace:
        key = f"{install_check.PLUGIN_NAME}@{marketplace}"
        entry = install_check.applicable_entry(installed_map.get(key) or [], project_root)
    install_path = (entry or {}).get("installPath") or ""
    installed = None
    if entry is not None:
        installed = (install_check.plugin_version(install_path) if install_path else None) or (
            str(entry["version"]) if entry.get("version") else None
        )
    clone = install_check.marketplace_clone(config_dir, marketplace)[0] if marketplace else None
    record = marketplace_record(config_dir, marketplace)
    pin, config_path = read_pin(project_root)
    result = {
        "verdict": CURRENT,
        "running": running,
        "installed": installed,
        "clone": clone,
        "latest": highest(latest, clone),
        "pin": pin,
        "marketplace": marketplace,
        "scope": (entry or {}).get("scope"),
        "repo": repo_of(record),
        "auto_update": auto_update_of(record),
        "config_path": config_path,
        "pending": None,
        "opt_out": None,
    }
    result["verdict"] = verdict_of(result, running_root, install_path)
    return result


def verdict_of(fields: dict, running_root, install_path) -> str:
    """Apply the verdict table top to bottom; the first match wins."""
    running, pin = fields["running"], fields["pin"]
    if newer(pin, running):
        return CURRENT
    cache = is_cache_copy(running_root)
    is_applicable = bool(install_path) and install_check.norm(install_path) == install_check.norm(running_root)
    if cache and install_path and not is_applicable and newer(fields["installed"], running):
        return RESTART
    if cache and is_applicable and newer(fields["latest"], running):
        return PLUGIN_BEHIND
    if newer(running, pin):
        return PROJECT_BEHIND
    return CURRENT


# --- update ----------------------------------------------------------------

def _last_json(text) -> "dict | None":
    """The last JSON object in the text: the whole text first, then line by line."""
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (TypeError, ValueError):
        pass
    for line in reversed((text or "").splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def confirm_command(result) -> "str | None":
    """The marketplace-declared command that a person must accept, else None.

    When a marketplace declares a command (a command-source install, or the headersHelper that
    fetches an archive), the CLI shows it and does not run it without `-y` or a person at a
    terminal. Its `--json` result then carries `shownCommand`, an object whose `command` is the
    declared command. The top-level `command` key is the CLI subcommand ("install" or "update"),
    never a command to run, so this function never reads it.

    A result with `outcome` "ok" is a finished update and never a request, even when it echoes a
    `shownCommand`.
    """
    if not isinstance(result, dict) or result.get("outcome") == _OUTCOME_OK:
        return None
    shown = result.get(_SHOWN_COMMAND_KEY)
    if not isinstance(shown, dict):
        return None
    value = shown.get("command")
    return value.strip() if isinstance(value, str) and value.strip() else None


def update(running_root, project_root, data_dir=None) -> "tuple[int, dict]":
    """Refresh the marketplace, then update the plugin. Returns (exit code, report)."""
    del data_dir  # the store branch writes no marker file
    config_dir = install_check.default_config_dir()
    installed_map = _installed_plugins(config_dir)
    marketplace = install_check.marketplace_name(running_root, installed_map)
    entry = None
    if marketplace:
        key = f"{install_check.PLUGIN_NAME}@{marketplace}"
        entry = install_check.applicable_entry(installed_map.get(key) or [], project_root)
    report = {"result": FAILED, "command": None, "retry": None, "marketplace": marketplace,
              "scope": (entry or {}).get("scope"), "argv": None, "refresh": None, "detail": ""}
    if entry is None or not report["scope"]:
        report["detail"] = "no planwise marketplace install applies to this project"
        return EXIT_FAILED, report
    report["refresh"] = install_check.refresh(marketplace)
    exe = shutil.which("claude")
    if exe is None:
        report["detail"] = "claude is not on PATH"
        return EXIT_FAILED, report
    scope = report["scope"]
    argv = [exe, "plugin", "update", f"{install_check.PLUGIN_NAME}@{marketplace}", "--scope", scope, "--json"]
    report["argv"] = argv
    cwd = str(project_root) if scope in ("project", "local") else None
    try:
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=UPDATE_TIMEOUT, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        report["detail"] = f"{type(exc).__name__}: {exc}"
        return EXIT_FAILED, report
    parsed = _last_json(proc.stdout)
    command = confirm_command(parsed)
    if command:
        # `command` is the marketplace's declared command, for the person to review. `retry` is
        # what the person runs in a terminal, where the CLI can ask. This script never accepts it.
        retry = f"claude plugin update {install_check.PLUGIN_NAME}@{marketplace} --scope {scope}"
        report.update(result=NEEDS_CONFIRM, command=command, retry=retry,
                      detail="a marketplace-declared command needs a person to accept it in a terminal")
        return EXIT_NEEDS_CONFIRM, report
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout or "").strip().splitlines()
        report["detail"] = f"exit {proc.returncode}" + (f": {lines[-1]}" if lines else "")
        return EXIT_FAILED, report
    report["result"] = UPDATED
    report["detail"] = "restart required to apply"
    return EXIT_UPDATED, report


# --- CLI -------------------------------------------------------------------

def _emit(data: dict) -> None:
    sys.stdout.buffer.write((json.dumps(data, separators=(",", ":")) + "\n").encode("utf-8"))
    sys.stdout.flush()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compute the planwise update verdict, or update the plugin.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "update"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--running-root", required=True)
        cmd.add_argument("--project-root", required=True)
        cmd.add_argument("--data-dir", default=None)
        if name == "check":
            cmd.add_argument("--latest", default=None)
    args = parser.parse_args(argv)
    if args.command == "check":
        _emit(check(args.running_root, args.project_root, latest=args.latest, data_dir=args.data_dir))
        return 0
    code, report = update(args.running_root, args.project_root, data_dir=args.data_dir)
    _emit(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
