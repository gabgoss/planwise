#!/usr/bin/env python3
"""Apply the confirmed upgrade offers in one call.

CLI: python -B upgrade_apply.py --project-root P [--prune safe-to-discard,inert] [--grants normalize]
     [--task-tools add] [--thrifty-sonic add] [--transfer-delete PATH --pair FROM-to-TO]
     [--prune-stale] [--flip-status PATH=STATUS ...] [--user-settings PATH]

Exit codes: 0 done, 1 a write failed its read-back, 2 a guard refused. Each apply flag is one offer the
person confirmed. Before the first write of any flag, every planned settings write is checked against
upgrade_run.settings_target_refusal, and every --transfer-delete path against transfer_refusal
(containment, symlink, this run's own pair), so a refusal writes nothing. Every settings write then goes
through write_settings, which keeps a pre-image backup: a project settings file's under
upgrade-prune-logs/, a user settings file's beside it. Deletion goes through the shared prune writers,
except --transfer-delete, which carries its own guards.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import upgrade_preflight as pre  # the path insert above makes the siblings importable
import upgrade_run

PRUNABLE = ("safe-to-discard", "inert")
THRIFTY_KEY, TODO_KEY = "CLAUDE_CODE_THRIFTY_SONIC", "CLAUDE_CODE_ENABLE_TODO_TOOLS"
BOM = b"\xef\xbb\xbf"


class Ctx:
    """The resolved project: paths, config and the planwise-side InitConfig."""

    def __init__(self, project_root: Path, user_flag):
        self.project_root = project_root
        self.config_path, self.config = pre.resolve_config(project_root)
        self.cfg = pre.build_cfg(self.config, project_root)
        self.root = self.cfg.planwise_root
        self.user_path = pre.resolve_user_settings(user_flag)[0]
        self.logs = project_root / self.root / "upgrade-prune-logs"
        self.scope = self.cfg.install_scope

    def project_settings(self, name: str = "settings.json") -> Path:
        return self.project_root / ".claude" / name


def norm_real(path) -> str:
    return os.path.normcase(os.path.realpath(path))


def settings_refusal(path: Path, ctx: Ctx) -> str:
    """The refusal line when a settings write to `path` is not allowed, else '' (one shared check)."""
    return upgrade_run.settings_target_refusal(path, ctx.project_root, ctx.user_path)


def is_project_settings(path: Path, ctx: Ctx) -> bool:
    """True when `path` is the project's own .claude/settings.json or .claude/settings.local.json."""
    return any(upgrade_run.same_path(path, ctx.project_settings(name)) for name in upgrade_run.SETTINGS_NAMES)


def planned_settings_writes(ctx: Ctx, args) -> list[Path]:
    """Every settings file the confirmed flags may write, so the target rule runs before the first write."""
    import doctor_cli

    planned: list[Path] = []
    if args.grants and ctx.scope == "project":
        planned += sorted({Path(f["settings_path"]) for f in doctor_cli._sweep_settings_grants(ctx.cfg)})
    if args.task_tools and ctx.scope == "project":
        planned.append(ctx.project_settings())
    if args.thrifty_sonic:
        planned += [ctx.project_settings(), ctx.user_path]
    return planned


def load_settings(path: Path):
    """(data, error): a missing file is ({}, ''), an unusable one is (None, reason)."""
    if not path.exists():
        return {}, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, str(exc)
    return (data, "") if isinstance(data, dict) else (None, "the JSON root is not an object")


def write_settings(path: Path, data: dict, ctx: Ctx) -> int:
    """The one settings writer: guard, pre-image, temp file, os.replace, read-back. Returns 0, 1 or 2."""
    refusal = settings_refusal(path, ctx)
    if refusal:
        print(refusal)
        return 2
    try:
        original = path.read_bytes() if path.exists() else b""
    except OSError as exc:
        print(f"write failed for {path}: {exc}")
        return 1
    text = original.decode("utf-8-sig", errors="replace")
    newline = "\r\n" if "\r\n" in text else "\n"
    body = json.dumps(data, indent=2, ensure_ascii=False).replace("\n", newline)
    if not original or text.endswith("\n"):
        body += newline
    raw = (BOM if original.startswith(BOM) else b"") + body.encode("utf-8")
    tmp = Path(f"{path}.tmp")
    try:
        if original:
            digest = hashlib.sha256(original).hexdigest()[:8]
            if is_project_settings(path, ctx):
                ctx.logs.mkdir(parents=True, exist_ok=True)
                backup = ctx.logs / f"settings-{path.name}-{digest}.bak"
            else:  # a user file can hold tokens, so its pre-image stays in its own folder, outside the project
                backup = path.parent / f"{path.name}.{digest}.bak"
            backup.write_bytes(original)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(raw)
        os.replace(tmp, path)
        back = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        tmp.unlink(missing_ok=True)
        print(f"write failed for {path}: {exc}")
        return 1
    if back != data:
        print(f"read-back mismatch for {path}")
        return 1
    return 0


def merge_env(path: Path, key: str, value: str, ctx: Ctx, label: str) -> int:
    data, error = load_settings(path)
    if data is None:
        print(f"{label}: {path} does not parse ({error}); not applied")
        return 0
    env = data.get("env") if isinstance(data.get("env"), dict) else {}
    if env.get(key) == value:
        print(f"{label}: already applied ({path})")
        return 0
    data["env"] = {**env, key: value}
    code = write_settings(path, data, ctx)
    if code == 0:
        print(f"{label}: set env.{key} in {path}")
    return code


def apply_task_tools(ctx: Ctx) -> int:
    if ctx.scope != "project":
        print(f"scope {ctx.scope}: not applied (task-tools)")
        return 0
    if pre.task_tools_state(ctx.cfg) == "set":
        print("task-tools: already applied")
        return 0
    return merge_env(ctx.project_settings(), TODO_KEY, "1", ctx, "task-tools")


def apply_thrifty(ctx: Ctx) -> int:
    code = 0
    for path in (ctx.project_settings(), ctx.user_path):
        code = max(code, merge_env(path, THRIFTY_KEY, "false", ctx, "thrifty-sonic"))
    return code


def apply_grants(ctx: Ctx) -> int:
    import doctor_cli

    if ctx.scope != "project":
        print(f"scope {ctx.scope}: not applied (grants)")
        return 0
    findings = doctor_cli._sweep_settings_grants(ctx.cfg)
    if not findings:
        print("grants: already applied")
        return 0
    family = str(ctx.cfg.plugin_root.parent)
    code = 0
    for path in sorted({f["settings_path"] for f in findings}):
        data, error = load_settings(path)
        if data is None:
            print(f"grants: {path} does not parse ({error}); not applied")
            continue
        perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
        entries = [e for e in perms.get("additionalDirectories", [])]
        kept = [e for e in entries if not (isinstance(e, str) and doctor_cli._grant_covers(family, e)
                                           and not doctor_cli._grant_covers(e, family))]
        if not any(isinstance(e, str) and doctor_cli._norm_path(e) == doctor_cli._norm_path(family) for e in kept):
            kept.append(family)
        data["permissions"] = {**perms, "additionalDirectories": kept}
        step = write_settings(path, data, ctx)
        if step == 0:
            print(f"grants: normalized {path} to the family root {family}")
        code = max(code, step)
    return code


def apply_prune(ctx: Ctx, classes: list, pair: str, found: list) -> int:
    """Prune `found` (main()'s one sweep, this run's own pre-images left out), then sweep once more."""
    import doctor_cli

    if not found:
        print(f"prune: already applied ({', '.join(classes)})")
        return 0
    # Only the safe-to-discard pass leaves this run's pair out: its consumed verdict cache (inert) is spent.
    if "safe-to-discard" in classes:
        doctor_cli._run_prune_upgrade_leftovers(ctx.cfg, {"safe-to-discard"}, exclude_pairs={pair})
    if "inert" in classes:
        doctor_cli._run_prune_upgrade_leftovers(ctx.cfg, {"inert"})
    after = upgrade_run.prunable_leftovers(ctx.cfg, pair, classes)
    code = 0
    for klass in classes:
        left = [f for f in after if f["klass"] == klass]
        if left:
            print(f"prune: {len(left)} surface(s) of class {klass} remain")
            code = 1
    return code


def run_script(ctx: Ctx, argv: list) -> tuple[int, str]:
    """One plugin script as a child process, through the shared runner."""
    return pre._run_script([sys.executable, "-B", *argv])


def apply_prune_stale(ctx: Ctx) -> int:
    """The shared prune writer, in-process, over the InitConfig built from the whole project config."""
    import doctor_cli
    import doctor_sweeps

    def removable() -> list:
        found = doctor_sweeps.sweep_stale_descoped_rules(ctx.cfg) + doctor_sweeps.sweep_orphaned_agent_mirrors(ctx.cfg)
        return [f for f in found if f["verdict"] == "REMOVABLE"]

    if not removable():
        print("prune-stale: already applied")
        return 0
    doctor_cli._run_prune_stale(ctx.cfg)
    left = removable()
    if left:
        print(f"prune-stale: {len(left)} REMOVABLE row(s) remain: {', '.join(f['filename'] for f in left)}")
        return 1
    return 0


def written_payload(out: str):
    """The JSON report of `generate_plans_index --write --json` when it says the index was written, else None.

    The writer prints that report only after a write. A refusal, a traceback or a missing config prints none,
    so the exit code alone (1 is also the anomaly signal) never decides it.
    """
    lines = out.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.startswith("{")), None)
    if start is None:
        return None
    try:
        payload = json.JSONDecoder().raw_decode("".join(lines[start:]))[0]
    except ValueError:
        return None
    return payload if isinstance(payload, dict) and payload.get("written") is True else None


def apply_flip_status(ctx: Ctx, pairs: list) -> int:
    statuses = [str(s) for s in ctx.config.get("plan_statuses") or []]
    lines = []
    for pair in pairs:
        path, _sep, status = pair.rpartition("=")
        if not path or status not in statuses:
            print(f"flip-status: {status or pair} is not in plan_statuses; skipped {path or pair}")
        else:
            lines.append(f"{path}: {status}")
    if not lines:
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        map_file = Path(tmp) / "status-map.txt"
        map_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        code, out = run_script(ctx, [str(SCRIPTS / "flip_plan_status.py"), "--config", str(ctx.config_path),
                                     str(map_file)])
    print(out.rstrip())
    print(f"flip-status: exit code {code}")
    changed = re.search(r"^changed: (\d+)", out, re.MULTILINE)
    if changed and int(changed.group(1)) > 0:  # exit 1 can follow a partial rewrite: the index follows the files
        index_code, out = run_script(ctx, [str(SCRIPTS / "generate_plans_index.py"), "--config",
                                           str(ctx.config_path), "--write", "--json"])
        payload = written_payload(out)
        if payload is None or index_code not in (0, 1):
            print(out.rstrip())
            print(f"plans index: exit code {index_code}; not written")
            return 1
        anomalies = payload.get("anomalies") or []
        print(f"plans index: wrote {payload.get('index')}")
        for item in anomalies:
            print(f"  anomaly {item.get('class')}: {item.get('message')}" if isinstance(item, dict) else f"  {item}")
        if anomalies:
            print(f"plans index: written; {len(anomalies)} anomalies remain")
    elif code == 0:
        print("flip-status: already applied")
    return 1 if code else 0


def transfer_refusal(ctx: Ctx, target: Path, pair: str) -> str:
    """The guard of --transfer-delete: containment, symlink and this run's own pair folder."""
    base = ctx.project_root / ctx.root / "upgrade-transfers"
    parts = (Path(norm_real(target)).relative_to(Path(norm_real(base))).parts
             if upgrade_run.is_inside(target, base, strict=True) else ())
    if len(parts) < 2 or not upgrade_run.PAIR_RE.fullmatch(parts[0]):
        return f"refusing {target}: not under upgrade-transfers/{{x}}-to-{{y}}/"
    if target.is_symlink() or norm_real(target) != os.path.normcase(os.path.join(norm_real(target.parent), target.name)):
        return f"refusing {target}: a symlink"
    if parts[0].lower() == pair.lower():
        return f"refusing {target}: it belongs to this run's pair {pair}"
    return ""


def handoff_reports_only(ctx: Ctx) -> bool:
    """True when upgrade.customization_handoff is `report`: the config keeps no transfer files."""
    return str((ctx.config.get("upgrade") or {}).get("customization_handoff", "report")) == "report"


def apply_transfer_delete(ctx: Ctx, path_arg: str, pair: str, rows: list) -> int:
    """Delete one now-upstream transfer file. `rows` is the one transfer review main() ran for this call."""
    target = Path(path_arg)
    refusal = transfer_refusal(ctx, target, pair)  # main() ran this before any write; the deleter keeps it
    if refusal:
        print(refusal)
        return 2
    if handoff_reports_only(ctx):
        print("no transfers under this config")
        return 0
    if not target.is_file():
        print(f"transfer-delete: already applied ({target})")
        return 0
    row = next((r for r in rows if norm_real(r["path"]) == norm_real(target)), None)
    if row is None or row["status"] != "now-upstream":
        print(f"transfer-delete: kept {target} (status {row['status'] if row else 'unknown'})")
        return 0
    reason, raw, source = upgrade_run.transfer_check(ctx.cfg, target)  # the same check the offer used
    if reason:
        print(f"transfer-delete: kept {target} ({reason})")
        return 0
    digest = hashlib.sha256(raw).hexdigest()
    try:
        ctx.logs.mkdir(parents=True, exist_ok=True)
        (ctx.logs / f"transfer-{target.name}-{digest[:8]}.bak").write_bytes(raw)
        target.unlink()
    except OSError as exc:
        print(f"transfer-delete: could not remove {target}: {exc}; no log row written")
        return 1
    print(f"transfer-delete: removed {target}")
    if target.exists():
        print(f"transfer-delete: {target} is still there")
        return 1
    print(f"transfer-delete: confirmed {target} is gone")
    try:
        with (ctx.logs / "TRANSFER-DELETES.md").open("a", encoding="utf-8", newline="\n") as log:
            log.write(f"{datetime.datetime.now().astimezone().date().isoformat()} | {target.as_posix()} | {digest} | "
                      f"now-upstream, body equals shipped {source}\n")
    except OSError as exc:
        print(f"transfer-delete: {target} was removed (pre-image kept), but the log row could not be written: {exc}")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply confirmed planwise upgrade offers")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--pair", default=None)
    parser.add_argument("--user-settings", default=None)
    parser.add_argument("--prune", default=None)
    parser.add_argument("--grants", choices=["normalize"], default=None)
    parser.add_argument("--task-tools", choices=["add"], default=None)
    parser.add_argument("--thrifty-sonic", choices=["add"], default=None)
    parser.add_argument("--transfer-delete", action="append", default=[])
    parser.add_argument("--prune-stale", action="store_true")
    parser.add_argument("--flip-status", nargs="+", action="extend", default=[])
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()
    classes = [c.strip() for c in (args.prune or "").split(",") if c.strip()]
    bad = [c for c in classes if c not in PRUNABLE]
    if bad or (args.prune is not None and not classes):
        print(f"error: --prune accepts only {' and '.join(PRUNABLE)}, got {args.prune!r}")
        return 2
    own_pair = bool(args.transfer_delete) or "safe-to-discard" in classes  # both exclude this run's own pair
    if own_pair and not (args.pair and upgrade_run.PAIR_RE.fullmatch(args.pair)):
        print(f"error: {'--transfer-delete' if args.transfer_delete else '--prune safe-to-discard'} "
              "needs --pair FROM-to-TO")
        return 2
    wanted = [args.prune, args.grants, args.task_tools, args.thrifty_sonic, args.transfer_delete,
              args.prune_stale, args.flip_status]
    if not any(wanted):
        print("Nothing to apply.")
        return 0

    try:
        ctx = Ctx(project_root, args.user_settings)
    except Exception as exc:  # noqa: BLE001 - an unreadable config is reported, never a traceback
        print(f"error: cannot read the project config ({exc})")
        return 2
    refusal = upgrade_run.root_refusal(project_root, ctx.root)
    if not refusal and own_pair:
        refusal = upgrade_run.applied_pair_refusal(project_root, ctx.config, args.pair)
    if not refusal:  # the transfer guards run over every path before the first write of any flag
        refusal = next((r for r in (transfer_refusal(ctx, Path(p), args.pair) for p in args.transfer_delete) if r), "")
    if not refusal:  # the settings-target rule runs over every planned write before the first write
        refusal = next((r for r in (settings_refusal(p, ctx) for p in planned_settings_writes(ctx, args)) if r), "")
    if refusal:
        print(refusal)
        return 2
    code = 0
    if classes:
        found = upgrade_run.prunable_leftovers(ctx.cfg, args.pair or "", classes)
        code = max(code, apply_prune(ctx, classes, args.pair or "", found))
    if args.grants:
        code = max(code, apply_grants(ctx))
    if args.task_tools:
        code = max(code, apply_task_tools(ctx))
    if args.thrifty_sonic:
        code = max(code, apply_thrifty(ctx))
    if args.transfer_delete:
        import transfer_review

        rows = [] if handoff_reports_only(ctx) else transfer_review.review_transfers(ctx.cfg, exclude_pair=args.pair)
        for path in args.transfer_delete:
            code = max(code, apply_transfer_delete(ctx, path, args.pair, rows))
    if args.prune_stale:
        code = max(code, apply_prune_stale(ctx))
    if args.flip_status:
        code = max(code, apply_flip_status(ctx, args.flip_status))
    return code


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
