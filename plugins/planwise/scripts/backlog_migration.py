"""Migrate a hand-authored backlog index during `/planwise upgrade` and `/planwise init`.

One idempotent routine, `migrate_backlog_if_legacy`, and one banner emitter.
The trigger is the index's shape, not a version, so a refused run re-fires on
the next upgrade and a finished one never repeats:

- `legacy` (hand-authored): plan every repair in memory, back up each file the
  plan rewrites byte-exact, run the migrator's staged write, then back up every
  generated file and regenerate and check the index. A row-prose unit the
  dedup cannot call present or missing (AMBIGUOUS) is parked verbatim in the
  migration ledger, never appended and never a refusal; the banner names the
  parked count.
- `migrated` (generated): re-split a changelog that has grown over the per-file
  read budget, with backups; otherwise do nothing and print nothing.
- `unrecognized`: report the classifier's reason and touch nothing.
- `deferred`: a hand-authored index met by a caller that passed `defer_legacy` (plain
  `init`): write nothing and name `/planwise upgrade` as the step that migrates it.

Recognise-or-refuse, never best-effort. Every step before the backup is
read-only, and a failed backup means no write is attempted. A failed write
restores every file it touched to this run's pre-image, then reports
`write_failed`. The first pre-image wins: a backup an earlier run left in the
same version pair is kept, never overwritten -- a later run whose target has
since changed gets a numbered sibling (`{name}.{n}.bak`) instead, so its own
restore point is not lost. The routine never raises: any
unexpected exception becomes state `error`, so it never fails the caller. The
git working-tree state is reported for information only, because the backup
under `{planwise_root}/upgrade-backups/{from}-to-{to}/backlog/` is the restore
point.
"""
import contextlib
import dataclasses
import hashlib
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
CREATED = "created; no pre-image (the file did not exist before this run)"


@dataclasses.dataclass
class BacklogMigrationReport:
    """Outcome of `migrate_backlog_if_legacy`, with banner-ready fields."""
    state: str  # absent | generated | unrecognized | deferred | refused | backup_failed | write_failed | migrated | changelog_split | error
    index_path: Path | None
    detail: str = ""
    fix: str = ""
    backup_dir: Path | None = None
    backed_up: list[str] = dataclasses.field(default_factory=list)
    kept: list[str] = dataclasses.field(default_factory=list)  # backups an earlier run made; left as they were
    written: list[str] = dataclasses.field(default_factory=list)
    ledger_path: Path | None = None
    diverged: dict = dataclasses.field(default_factory=dict)  # backup dst (str) -> sibling pre-image (str)
    counts: dict = dataclasses.field(default_factory=dict)
    git_dirty: bool | None = None
    generator_write_exit: int | None = None
    generator_check_exit: int | None = None


def migrate_backlog_if_legacy(cfg: "InitConfig", from_version: str, to_version: str,
                              *, reconcile: str | None = None,
                              defer_legacy: bool = False) -> BacklogMigrationReport:
    """Migrate the project's backlog index when it is hand-authored. Never raises.

    `defer_legacy` makes the call detect-only for a hand-authored index: it writes nothing,
    reports state `deferred`, and names `/planwise upgrade` as the step that migrates it. A
    generated index is handled the same either way. Plain `init` sets it, because a
    row/frontmatter reconcile only has something to resolve once a project already carries
    item frontmatter, and `/planwise upgrade` is where the reconcile choice is accepted."""
    report = BacklogMigrationReport(state="absent", index_path=None)
    try:
        _migrate(cfg, from_version, to_version, reconcile, report, defer_legacy)
    except Exception as exc:  # noqa: BLE001 -- the caller's upgrade must never fail on this step
        report.state, report.detail = "error", repr(exc)
    return report


def _migrate(cfg, from_version: str, to_version: str, reconcile: str | None, report,
             defer_legacy: bool = False) -> None:
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
    if defer_legacy:
        report.state = "deferred"
        report.detail = "the index is hand-authored; this run changed no backlog file"
        report.fix = "run /planwise upgrade, which migrates it"
        return
    inputs = [index_path, *sorted(config["_backlog_dir"].glob("*.md")), *sorted(config["_archive_dir"].glob("*.md"))]
    dirty, _reason = chk.git_state(config["_project_root"], inputs)
    report.git_dirty = None if dirty is None else bool(dirty)
    mode = reconcile or "index-wins"
    options = mig.RepairOptions.unattended(mode)  # AMBIGUOUS units are parked in the ledger, never refused
    try:
        plan = mig.plan_migration(config, index_path, text, detail, options)
    except mig.Refusal as exc:
        _refuse(report, exc, f"{command} --write --backfill-frontmatter --write-edges "
                                  f"--extract-dependency-notes --reconcile {mode} --append-ambiguous")
        return
    paths = mig.artifact_paths(index_path)
    backlog_dir = config["_backlog_dir"]
    if plan is not None:
        targets = mig.plan_targets(plan) + ([paths[1]] if paths[1].is_file() else [])  # a ledger or journal left earlier
        pre = _backup(targets, backlog_dir, report, [*(p for p, _t in plan["outputs"]), paths[1]])
        if pre is None:
            return
        try:
            rc, output = _captured(mig.execute, plan, paths, index_path, False)
        except (OSError, sup.ReplaceError) as exc:
            rc, output = 1, f"migration write failed: {exc}"
        report.detail = output
        if rc != 0:
            _write_failed(report, pre, "re-run /planwise upgrade; the migration restarts from the restored files")
            return
        backed = {Path(p).resolve() for p in targets}
        for path in [*(p for p, _t in plan["outputs"]), paths[1]]:
            reason = _kept_at(path, backlog_dir, report) if path.resolve() in backed else CREATED
            _log(cfg, from_version, to_version, path, "backlog-migrated", reason, report)
    else:
        report.detail = "an earlier run migrated the index; this run regenerated it only (its counts are in that ledger)"
    if not _regenerate(cfg, from_version, to_version, config, index_path, report):
        if report.state != "backup_failed":
            report.state, report.fix = "write_failed", f"fix what the generator names, {RERUN}"
        return
    report.state = "migrated"
    if plan is not None:  # counts describe this run's migrator write, never an earlier run's ledger
        _fill_counts(paths[1], mode, report)
    _count_shards(config, index_path, report)


def _resplit_changelog(cfg, from_version: str, to_version: str, config: dict, index_path: Path, report) -> None:
    """A generated index: re-split an over-budget changelog, with backups, or stay silent."""
    try:
        plan = mig.plan_changelog_resplit(config, index_path)
    except mig.Refusal as exc:
        _refuse(report, exc, "")
        return
    if plan is None:
        report.state = "generated"
        return
    remove = list(plan["remove"])
    targets = list(dict.fromkeys([*plan["targets"], *remove]))
    backlog_dir = config["_backlog_dir"]
    pre = _backup(targets, backlog_dir, report, [p for p, _t in plan["outputs"]])
    if pre is None:
        return
    expected = len(plan["outputs"])
    try:
        written, output = _captured(mig.execute_outputs, plan["outputs"], remove)
    except (OSError, sup.ReplaceError) as exc:
        written, output = None, f"changelog re-split failed: {exc}"
    if written != expected:
        report.detail = output if written is None else f"changelog re-split wrote {written} of {expected} part(s)"
        _write_failed(report, pre, "re-run /planwise upgrade; the re-split restarts from the restored files")
        return
    backed = {Path(p).resolve() for p in targets}
    for path, _text in plan["outputs"]:
        reason = "rewritten; " + _kept_at(path, backlog_dir, report) if path.resolve() in backed else "new part; " + CREATED
        _log(cfg, from_version, to_version, path, "backlog-changelog-split", reason, report)
    for path in remove:
        _log(cfg, from_version, to_version, path, "backlog-changelog-split",
             "removed; " + _kept_at(path, backlog_dir, report), report)
    report.state = "changelog_split"
    report.counts["changelog_parts"] = expected


def _refuse(report, exc, command: str) -> None:
    """State `refused`: the refusal's reason as the detail, and the edit it names as the fix."""
    action = exc.fix
    if command and "--append-ambiguous" in str(exc):
        action += f"; or append them with: {command}"
    report.state, report.detail, report.fix = "refused", exc.reason, f"{action}\n{RERUN}"


def _rel(path: Path, backlog_dir: Path) -> Path:
    """`path` relative to the backlog directory, keeping `Archive/`. A path outside it goes under
    `_outside/{digest of its directory}/`, so two same-named files never share one backup."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(backlog_dir).resolve())
    except ValueError:
        digest = hashlib.sha256(str(resolved.parent).encode("utf-8")).hexdigest()[:12]
        return Path("_outside") / digest / resolved.name


def _kept_at(path: Path, backlog_dir: Path, report) -> str:
    """The DISPOSITIONS reason naming where `path`'s pre-image sits, whether an earlier run made
    it, and a second pre-image location when this run's own bytes diverged from that kept one."""
    rel = _rel(path, backlog_dir)
    dst = report.backup_dir / rel
    earlier = " (made by an earlier run in this version pair; kept, not overwritten)"
    sibling = report.diverged.get(str(dst))
    extra = ""
    if sibling:
        sibling_rel = Path(sibling).relative_to(report.backup_dir)
        extra = (f"; current bytes differed, also backed up to "
                 f"upgrade-backups/{report.backup_dir.parent.name}/backlog/{sibling_rel.as_posix()}")
    return (f"pre-image at upgrade-backups/{report.backup_dir.parent.name}/backlog/{rel.as_posix()}"
            + (earlier if str(dst) in report.kept else "") + extra)


def _next_free_sibling(dst: Path) -> Path:
    """The first `{dst.name}.{n}.bak` that does not already exist, starting at n=1."""
    n = 1
    while True:
        candidate = dst.with_name(f"{dst.name}.{n}.bak")
        if not candidate.exists():
            return candidate
        n += 1


def _matching_sibling(dst: Path, current: bytes) -> Path | None:
    """An existing `{dst.name}.{n}.bak` whose bytes equal `current`, so a re-run adds no duplicate."""
    n = 1
    while True:
        candidate = dst.with_name(f"{dst.name}.{n}.bak")
        if not candidate.exists():
            return None
        if candidate.read_bytes() == current:
            return candidate
        n += 1


def _backup(targets: list, backlog_dir: Path, report, also: list = ()) -> dict | None:
    """Copy every existing target byte-exact before any write, and return this run's pre-image of
    each target and each path in `also` (None for a file that does not exist yet). The first
    pre-image wins: a backup already present is kept, never overwritten. When that kept backup's
    bytes no longer match the target's own current bytes -- a later operation in the same version
    pair found the target changed since the kept backup was made -- the current pre-image is ALSO
    written to a new sibling (`{name}.{n}.bak`, next free `n`), so this run's own restore point is
    not lost; a same-pair re-run whose bytes still match the kept backup writes nothing new. None
    means stop: nothing was written."""
    for src in targets:
        dst = report.backup_dir / _rel(src, backlog_dir)
        if str(dst) in report.backed_up:
            continue
        try:
            if dst.exists():
                report.kept.append(str(dst))
                current = Path(src).read_bytes() if Path(src).is_file() else None
                if current is not None and current != dst.read_bytes():
                    sibling = _matching_sibling(dst, current)
                    if sibling is None:
                        sibling = _next_free_sibling(dst)
                        upgrade_io._copy_bytes_exact(Path(src), sibling)
                        report.backed_up.append(str(sibling))
                    report.diverged[str(dst)] = str(sibling)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                upgrade_io._copy_bytes_exact(Path(src), dst)
        except OSError as exc:
            return _backup_failed(report, src, exc)
        report.backed_up.append(str(dst))
    try:
        return {Path(p): Path(p).read_bytes() if Path(p).exists() else None for p in [*targets, *also]}
    except OSError as exc:
        return _backup_failed(report, "a pre-image", exc)


def _backup_failed(report, src, exc) -> None:
    report.state = "backup_failed"
    report.detail = f"could not back up {src}: {exc}"
    report.fix = "free the backup location or fix its permissions, then " + RERUN


def _write_failed(report, pre: dict, fix: str) -> None:
    """State `write_failed`, after putting every path back to its pre-image: rewrite a changed
    file and delete one this run created. If that restore fails, `detail` names the backups."""
    report.state, report.fix = "write_failed", fix
    try:
        for path, data in pre.items():
            if data is None:
                path.unlink(missing_ok=True)
            elif not path.is_file() or path.read_bytes() != data:
                path.write_bytes(data)
    except OSError as exc:
        report.detail += f"\nrestore failed ({exc}); the tree is partly written -- restore it from {report.backup_dir}"
        report.fix = f"copy the backed-up files back from {report.backup_dir} by hand, {RERUN}"
        return
    report.detail += "\nthe tree was restored: every file this step touched is back to its pre-run bytes"


def _log(cfg, from_version: str, to_version: str, path: Path, action: str, reason: str, report) -> None:
    upgrade_io._append_disposition_log(cfg, from_version, to_version, Path(path), action, reason)
    report.written.append(str(path))


def _captured(func, *args):
    """Call `func`, keeping its stdout and stderr out of the caller's banner."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        result = func(*args)
    return result, buf.getvalue().strip()


def _regenerate(cfg, from_version: str, to_version: str, config: dict, index_path: Path, report) -> bool:
    """Back up every existing file the generator's write overwrites or removes (the hub, its overflow
    leaves and the Archive shards), write the hub and shards, then check them. True only when both
    exit 0. A non-zero exit is reported, not raised; the generator rolls back its own failed write."""
    naming = gen._index_naming(index_path)
    backlog_dir, archive_dir = config["_backlog_dir"], config["_archive_dir"]
    targets = list({Path(p).resolve(): None for p in
                    [index_path, *gen._list_disk_generated_files(backlog_dir, archive_dir, naming)]})
    if _backup(targets, backlog_dir, report) is None:
        return False
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        report.generator_write_exit = int(gen._cmd_write(backlog_dir, archive_dir, index_path, naming, config,
                                                         json_out=False))
        report.generator_check_exit = int(gen._cmd_check(backlog_dir, archive_dir, index_path, naming, config,
                                                         json_out=False))
    if report.generator_write_exit == 0:
        logged = {Path(p).resolve() for p in report.written}
        for path in (p for p in targets if p not in logged):
            _log(cfg, from_version, to_version, path, "backlog-migrated",
                 "regenerated or removed by the index generator; " + _kept_at(path, backlog_dir, report), report)
        known = logged | set(targets)  # a generated file absent before the write has no pre-image
        created = [Path(p).resolve() for p in gen._list_disk_generated_files(backlog_dir, archive_dir, naming)]
        for path in (p for p in dict.fromkeys(created) if p not in known):
            _log(cfg, from_version, to_version, path, "backlog-migrated",
                 "written by the index generator; " + CREATED, report)
    if report.generator_write_exit or report.generator_check_exit:
        report.detail = (report.detail + "\n" + buf.getvalue().strip()).strip()
        return False
    return True


def _fill_counts(ledger_path: Path, mode: str, report) -> None:
    """Counts come from the ledger, and only from a finished write (mode "write"). A ledger in an
    unexpected shape leaves the counts unset and never changes the state."""
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
    try:
        counts = _ledger_counts(ledger, mode)
    except (KeyError, TypeError, AttributeError) as exc:
        report.detail = (report.detail + f"\nledger shape not recognised ({exc!r}); counts left unset").strip()
        return
    report.counts.update(counts)


def _ledger_counts(ledger: dict, mode: str) -> dict:
    log, notes, cells = ledger["changelog"], ledger["dependency_notes"], ledger["reconcile"]["cells"]
    return {
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
        "parked_units": ledger["dedup"].get("parked_units", 0),
        "parked_bytes": ledger["dedup"].get("parked_bytes", 0),
        "reconciled_cells": len(cells),
        "reconcile_mode": ledger["reconcile"]["mode"] or mode,
        "reconciled": [f"{c['id']}.{c['key']}: {c['frontmatter']} -> {c['index']}" for c in cells],
    }


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
        return [(f"Backlog changelog: re-split into {c.get('changelog_parts')} part(s), each ≤ {READ_TOKEN_WARN} "
                 f"tokens; backups: {report.backup_dir}")]
    if report.state == "deferred":
        return ["Backlog index migration: DEFERRED (index and item files left untouched)",
                f"  reason: {report.detail}", f"  fix:    {fix}"]
    if report.state == "refused":
        return ["Backlog index migration: REFUSED (index and item files left untouched)",
                f"  reason: {report.detail}", f"  fix:    {fix}"]
    if report.state == "unrecognized":
        return [f"Backlog index migration: {index} is not a hand-authored or generated index — left untouched",
                *(f"  detail: {line}" for line in report.detail.splitlines() or [""])]
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
            (f"    changelog:              {c['changelog_path']} + {parts - 1} part(s) ({c['changelog_entries']} "
             f"entries, {c['changelog_bytes']} bytes; each file ≤ {READ_TOKEN_WARN} tokens; {accounted})"),
            f"    frontmatter backfilled: {c['backfilled']} item file(s) ({c['partial']} had a partial block)",
            f"    blocks: edges written:  {c['edges']}",
            f"    dependency notes moved: {c['dependency_notes']} bullet(s) into {c['dependency_note_files']} item file(s)",
            f"    feature-cell prose moved: {c['prose_units']} unit(s)",
            *([f"    {mig.parked_line(c['parked_units'], c['parked_bytes'], report.ledger_path)}"]
              if c.get("parked_units") else []),
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
    except Exception as exc:  # noqa: BLE001 -- a banner must never fail the caller
        lines = [f"Backlog index migration: {report.state} ({report.detail or exc!r})"]
    for line in lines:
        _say(line)
    _say()
