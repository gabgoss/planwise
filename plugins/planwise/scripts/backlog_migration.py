"""Migrate a hand-authored backlog index during `/planwise upgrade` and `/planwise init`.

One idempotent routine, `migrate_backlog_if_legacy`, and one banner emitter.
The trigger is the index's shape, not a version, so a refused run re-fires on
the next upgrade and a finished one never repeats:

- `legacy` (hand-authored): plan every repair in memory, back up each file the
  plan rewrites byte-exact, run the migrator's staged write, then regenerate
  and check the index.
- `migrated` (generated): re-split a changelog that has grown over the per-file
  read budget, with backups; otherwise do nothing and print nothing.
- `unrecognized`: report the classifier's reason and touch nothing.

Recognise-or-refuse, never best-effort. Every step before the backup is
read-only, and a failed backup means no write is attempted. The routine never
raises: any unexpected exception becomes state `error`, so it never fails the
caller. The git working-tree state is reported for information only, because
the backup under `{planwise_root}/upgrade-backups/{from}-to-{to}/backlog/` is
the restore point.
"""
import contextlib
import dataclasses
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import config_loader
    import generate_backlog_index as gen
    import migrate_backlog_checks as chk
    import migrate_backlog_index as mig
    import migrate_backlog_support as sup
    import upgrade_io
    from config_gen import InitConfig
    from read_limits import READ_TOKEN_WARN
    from reconcile_common import read_text_preserving_newlines as read_text
except ImportError as exc:
    raise ImportError(
        f"backlog_migration could not import a sibling module ({exc}); "
        "the scripts/ directory appears to be partially installed"
    ) from exc

RERUN = ("then re-run /planwise upgrade (the migration re-fires on a hand-authored index; "
         "nothing else repeats)")
MIGRATOR = "migrate_backlog_index.py"
SILENT_STATES = ("absent", "generated")


@dataclasses.dataclass
class BacklogMigrationReport:
    """Outcome of `migrate_backlog_if_legacy`, with banner-ready fields."""
    state: str  # absent | generated | unrecognized | refused | backup_failed | write_failed | migrated | changelog_split | error
    index_path: Path | None
    detail: str = ""
    fix: str = ""
    backup_dir: Path | None = None
    backed_up: list[str] = dataclasses.field(default_factory=list)
    written: list[str] = dataclasses.field(default_factory=list)
    ledger_path: Path | None = None
    counts: dict = dataclasses.field(default_factory=dict)
    git_dirty: bool | None = None
    generator_write_exit: int | None = None
    generator_check_exit: int | None = None


def migrate_backlog_if_legacy(cfg: "InitConfig", from_version: str, to_version: str,
                              *, reconcile: str | None = None) -> BacklogMigrationReport:
    """Migrate the project's backlog index when it is hand-authored. Never raises."""
    report = BacklogMigrationReport(state="absent", index_path=None)
    try:
        _migrate(cfg, from_version, to_version, reconcile, report)
    except Exception as exc:  # the caller's upgrade must never fail on this step
        report.state, report.detail = "error", repr(exc)
    return report


def _migrate(cfg, from_version: str, to_version: str, reconcile: str | None, report) -> None:
    config_path = Path(cfg.project_root) / cfg.planwise_root / "config.yaml"
    if not config_path.is_file():
        return
    config = config_loader.load_config(Path(__file__), config_path=config_path)
    index_path = config.get("_index_path")
    if index_path is None or not Path(index_path).is_file():
        return
    report.index_path = index_path
    report.backup_dir = (Path(cfg.project_root) / cfg.planwise_root / "upgrade-backups"
                         / f"{from_version}-to-{to_version}" / "backlog")
    text = read_text(index_path)
    shape, detail = sup.classify_shape(text)
    command = f"python {Path(cfg.plugin_root) / 'scripts' / MIGRATOR} --config {config_path}"
    if shape == "unrecognized":
        report.state, report.detail, report.fix = "unrecognized", detail, f"{command} --report"
        return
    if shape == "migrated":
        _resplit_changelog(cfg, from_version, to_version, config, index_path, report)
        return
    inputs = [index_path, *sorted(config["_backlog_dir"].glob("*.md")), *sorted(config["_archive_dir"].glob("*.md"))]
    dirty, _reason = chk.git_state(config["_project_root"], inputs)
    report.git_dirty = None if dirty is None else bool(dirty)
    mode = reconcile or "index-wins"
    options = mig.RepairOptions(backfill_frontmatter=True, write_edges=True, extract_dependency_notes=True,
                                reconcile=mode, append_ambiguous=False, high=sup.DEFAULT_HIGH, low=sup.DEFAULT_LOW)
    try:
        plan = mig.plan_migration(config, index_path, text, detail, options)
    except mig.Refusal as exc:
        _refuse(report, str(exc), f"{command} --write --backfill-frontmatter --write-edges "
                                  f"--extract-dependency-notes --reconcile {mode} --append-ambiguous")
        return
    paths = mig.artifact_paths(index_path)
    if plan is not None:
        targets = mig.plan_targets(plan)
        if not _backup(targets, config["_backlog_dir"], report):
            return
        rc, output = _captured(mig.execute, plan, paths, index_path, False)
        report.detail = output
        if rc != 0:
            report.state = "write_failed"
            report.fix = "re-run /planwise upgrade to resume; the migrator's staged write resumes where it stopped"
            return
        backed = {Path(p).resolve() for p in targets}
        for path, _text in plan["outputs"]:
            reason = ("pre-image in backlog/" + _rel(path, config["_backlog_dir"]).as_posix()
                      if path.resolve() in backed else "new file")
            _log(cfg, from_version, to_version, path, "backlog-migrated", reason, report)
    _regenerate(config, index_path, report)
    report.state = "migrated"
    _fill_counts(paths[1], mode, report)
    _count_shards(config, index_path, report)


def _resplit_changelog(cfg, from_version: str, to_version: str, config: dict, index_path: Path, report) -> None:
    """A generated index: re-split an over-budget changelog, with backups, or stay silent."""
    try:
        plan = mig.plan_changelog_resplit(config, index_path)
    except mig.Refusal as exc:
        _refuse(report, str(exc), "")
        return
    if plan is None:
        report.state = "generated"
        return
    remove = list(plan["remove"])
    targets = list(dict.fromkeys([*plan["targets"], *remove]))
    if not _backup(targets, config["_backlog_dir"], report):
        return
    expected = len(plan["outputs"])
    try:
        written, output = _captured(mig.execute_outputs, plan["outputs"], remove)
    except (OSError, sup.ReplaceError) as exc:
        written, output = None, f"changelog re-split failed: {exc}"
    if written != expected:
        report.state = "write_failed"
        report.detail = output if written is None else f"changelog re-split wrote {written} of {expected} part(s)"
        report.fix = "re-run /planwise upgrade; the re-split restarts from the files on disk"
        return
    backed = {Path(p).resolve() for p in targets}
    for path, _text in plan["outputs"]:
        reason = "rewritten; pre-image kept" if path.resolve() in backed else "new part"
        _log(cfg, from_version, to_version, path, "backlog-changelog-split", reason, report)
    for path in remove:
        _log(cfg, from_version, to_version, path, "backlog-changelog-split", "removed; pre-image kept", report)
    report.state = "changelog_split"
    report.counts["changelog_parts"] = expected


def _refuse(report, message: str, command: str) -> None:
    """State `refused`: the migrator's text verbatim, and the exact action it names."""
    action = message.rsplit(" -- ", 1)[1] if " -- " in message else message
    if command and "--append-ambiguous" in message:
        action += f"; or append them with: {command}"
    report.state, report.detail, report.fix = "refused", message, f"{action}\n{RERUN}"


def _rel(path: Path, backlog_dir: Path) -> Path:
    """`path` relative to the backlog directory, keeping `Archive/`; its bare name otherwise."""
    try:
        return Path(path).resolve().relative_to(Path(backlog_dir).resolve())
    except ValueError:
        return Path(Path(path).name)


def _backup(targets: list, backlog_dir: Path, report) -> bool:
    """Copy every existing target byte-exact before any write. False means stop."""
    for src in targets:
        dst = report.backup_dir / _rel(src, backlog_dir)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            upgrade_io._copy_bytes_exact(Path(src), dst)
        except OSError as exc:
            report.state = "backup_failed"
            report.detail = f"could not back up {src}: {exc}"
            report.fix = "free the backup location or fix its permissions, then " + RERUN
            return False
        report.backed_up.append(str(dst))
    return True


def _log(cfg, from_version: str, to_version: str, path: Path, action: str, reason: str, report) -> None:
    upgrade_io._append_disposition_log(cfg, from_version, to_version, Path(path), action, reason)
    report.written.append(str(path))


def _captured(func, *args):
    """Call `func`, keeping its stdout and stderr out of the caller's banner."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        result = func(*args)
    return result, buf.getvalue().strip()


def _regenerate(config: dict, index_path: Path, report) -> None:
    """Write the generated hub and shards, then check them. A non-zero exit is reported, not raised."""
    naming = gen._index_naming(index_path)
    backlog_dir, archive_dir = config["_backlog_dir"], config["_archive_dir"]
    # The migrated index keeps its hand-authored table until this write, so the
    # generator's legacy-shape guard must be told to replace it.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        report.generator_write_exit = int(gen._cmd_write(backlog_dir, archive_dir, index_path, naming, config,
                                                         json_out=False, replace_legacy=True))
        report.generator_check_exit = int(gen._cmd_check(backlog_dir, archive_dir, index_path, naming, config,
                                                         json_out=False))
    if report.generator_write_exit or report.generator_check_exit:
        report.detail = (report.detail + "\n" + buf.getvalue().strip()).strip()


def _fill_counts(ledger_path: Path, mode: str, report) -> None:
    """Counts come from the ledger, and only from a finished write (mode "write")."""
    if not ledger_path.is_file():
        return
    report.ledger_path = ledger_path
    try:
        ledger = json.loads(read_text(ledger_path))
    except (OSError, ValueError) as exc:
        report.detail = (report.detail + f"\nledger unreadable, counts left unset: {exc}").strip()
        return
    observed = ledger.get("mode") if isinstance(ledger, dict) else None
    if observed != "write":
        report.detail = (report.detail + f"\nledger mode is {observed!r}, not 'write'; counts left unset").strip()
        return
    log, notes, cells = ledger["changelog"], ledger["dependency_notes"], ledger["reconcile"]["cells"]
    report.counts.update({
        "backfilled": len(ledger["backfill"]),
        "partial": sum(1 for b in ledger["backfill"] if len(b["keys_added"]) < len(mig.KEYS)),
        "edges": len(ledger["edges"]),
        "dependency_notes": sum(n["bullets"] for n in notes),
        "dependency_note_files": sum(1 for n in notes if n["bullets"]),
        "changelog_entries": log["entries"],
        "changelog_parts": len(log.get("parts") or [log["path"]]),
        "changelog_bytes": log.get("entry_content_bytes", 0),
        "changelog_unaccounted": log.get("unaccounted", 0),
        "changelog_path": log["path"],
        "prose_units": ledger["dedup"]["appended_units"],
        "reconciled_cells": len(cells),
        "reconcile_mode": ledger["reconcile"]["mode"] or mode,
        "reconciled": [f"{c['id']}.{c['key']}: {c['frontmatter']} -> {c['index']}" for c in cells],
    })


def _count_shards(config: dict, index_path: Path, report) -> None:
    try:
        files = gen._list_disk_generated_files(config["_backlog_dir"], config["_archive_dir"],
                                               gen._index_naming(index_path))
    except OSError:
        return
    hub = Path(index_path).resolve()
    report.counts["shards"] = sum(1 for p in files if Path(p).resolve() != hub)


def _say(line: str = "") -> None:
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.replace("≤", "<=").encode("ascii", "replace").decode("ascii"))


def _banner_lines(report: BacklogMigrationReport) -> list:
    c, index = report.counts, report.index_path
    fix = report.fix.replace("\n", "\n          ")
    if report.state == "changelog_split":
        return [f"Backlog changelog: re-split into {c.get('changelog_parts')} part(s), each ≤ {READ_TOKEN_WARN} "
                f"tokens; backups: {report.backup_dir}"]
    if report.state == "refused":
        return ["Backlog index migration: REFUSED (index and item files left untouched)",
                f"  reason: {report.detail}", f"  fix:    {fix}"]
    if report.state == "unrecognized":
        return [f"Backlog index migration: {index} is not a hand-authored or generated index — left untouched",
                f"  reason: {report.detail}; inspect it with: {report.fix}"]
    if report.state == "backup_failed":
        return ["Backlog index migration: BACKUP FAILED — no write was attempted",
                f"  {report.detail}", f"  fix:    {fix}"]
    if report.state == "write_failed":
        return ["Backlog index migration: WRITE FAILED", f"  {report.detail}",
                f"  backups: {report.backup_dir} ({len(report.backed_up)} file(s))", f"  fix:    {fix}"]
    if report.state == "error":
        return ["Backlog index migration: ERROR (nothing else in this run depends on it)", f"  {report.detail}"]
    return _migrated_lines(report)


def _migrated_lines(report: BacklogMigrationReport) -> list:
    c = report.counts
    lines = ["Backlog index migration:",
             f"  migrated: {report.index_path} -> generated hub + {c.get('shards', '?')} shard(s)"]
    if "changelog_entries" in c:
        parts = c["changelog_parts"]
        accounted = ("every footer byte accounted for" if not c["changelog_unaccounted"]
                     else f"{c['changelog_unaccounted']} footer byte(s) unaccounted")
        reconciled = " …" if len(c["reconciled"]) > 5 else ""
        lines += [
            f"    changelog:              {c['changelog_path']} + {parts - 1} part(s) ({c['changelog_entries']} "
            f"entries, {c['changelog_bytes']} bytes; each file ≤ {READ_TOKEN_WARN} tokens; {accounted})",
            f"    frontmatter backfilled: {c['backfilled']} item file(s) ({c['partial']} had a partial block)",
            f"    blocks: edges written:  {c['edges']}",
            f"    dependency notes moved: {c['dependency_notes']} bullet(s) into {c['dependency_note_files']} item file(s)",
            f"    feature-cell prose moved: {c['prose_units']} unit(s)",
            f"    reconciled cells:       {c['reconciled_cells']} ({c['reconcile_mode']})"
            + (" — " + "; ".join(c["reconciled"][:5]) + reconciled if c["reconciled"] else ""),
        ]
    elif report.detail:
        lines.append(f"    counts:                 unavailable — {report.detail.splitlines()[-1]}")
    lines += [f"    ledger:                 {report.ledger_path or 'none'}"]
    if report.backed_up:
        lines.append(f"    backups:                {report.backup_dir} ({len(report.backed_up)} file(s), "
                     "listed in DISPOSITIONS.md)")
    else:
        lines.append("    backups:                none (no file was rewritten this run)")
    dirty = {True: "yes", False: "no", None: "unknown"}[report.git_dirty]
    lines += [f"    git tree was dirty:     {dirty} (informational — the backup above is the restore point)",
              "    generator --check:      " + ("clean" if report.generator_check_exit == 0
                                                 else f"exit {report.generator_check_exit} (write exit "
                                                      f"{report.generator_write_exit}); re-run /planwise upgrade")]
    return lines


def _emit_backlog_migration_banner(report: BacklogMigrationReport) -> None:
    """Print one banner block for the report; silent on `absent` and `generated`. Never raises."""
    if report.state in SILENT_STATES:
        return
    try:
        lines = _banner_lines(report)
    except Exception as exc:  # a banner must never fail the caller
        lines = [f"Backlog index migration: {report.state} ({report.detail or exc!r})"]
    for line in lines:
        _say(line)
    _say()
