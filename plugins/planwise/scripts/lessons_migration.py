#!/usr/bin/env python3
"""Migrate a hand-authored lessons index during `/planwise upgrade` and
`/planwise init`.

One idempotent routine, `migrate_lessons_if_legacy`, and one banner
emitter, on `backlog_migration.py`'s own shape. The trigger is the index's
shape, not a version, so a refused run re-fires on the next upgrade and a
finished one never repeats:

- `legacy` (hand-authored): plan every repair in memory, back up each file
  the plan rewrites byte-exact, run the migrator's staged write, then run
  the generator for the index and the categorization companion and check
  both.
- `generated`: check the index and the companion; stay silent either way.
- `unrecognized`: report the classifier's reason and touch nothing.

Recognise-or-refuse, never best-effort. Every step before the backup is
read-only, and a failed backup means no write is attempted. A failed write
restores every file it touched to this run's pre-image and removes every
file it created, then reports `write_failed`. The first pre-image wins: a backup an earlier run left in
the same version pair is kept, never overwritten -- a later run whose
target has since changed gets a numbered sibling (`{name}.{n}.bak`)
instead, so its own restore point is not lost. The routine never raises:
any unexpected exception becomes state `error`, so it never fails the
caller. The git working-tree state is reported for information only,
because the backup under
`{planwise_root}/upgrade-backups/{from}-to-{to}/lessons/` is the restore
point.
"""
import contextlib
import dataclasses
import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import config_loader
    import generate_lessons_index as gen
    import lessons_changelog as changelog
    import migrate_backlog_index as backlog_mig
    import migrate_lessons_index as mig
    import migrate_lessons_support as sup
    import parse_lessons
    import upgrade_io
    from config_gen import InitConfig
    from migrate_backlog_checks import git_state
    from reconcile_common import read_text_preserving_newlines as read_text
except ImportError as exc:
    raise ImportError(
        f"lessons_migration could not import a sibling module ({exc}); "
        "the scripts/ directory appears to be partially installed"
    ) from exc

RERUN = ("then re-run /planwise upgrade (the migration re-fires on a hand-authored index; "
         "nothing else repeats)")
MIGRATOR = "migrate_lessons_index.py"
SILENT_STATES = ("absent", "generated")
CREATED = "created; no pre-image (the file did not exist before this run)"


@dataclasses.dataclass
class LessonsMigrationReport:
    """Outcome of `migrate_lessons_if_legacy`, with banner-ready fields."""
    state: str  # absent | generated | unrecognized | deferred | refused | backup_failed | write_failed | migrated | changelog_split | error
    index_path: Path | None
    detail: str = ""
    fix: str = ""
    backup_dir: Path | None = None
    backed_up: list = dataclasses.field(default_factory=list)
    kept: list = dataclasses.field(default_factory=list)  # backups an earlier run made; left as they were
    written: list = dataclasses.field(default_factory=list)
    ledger_path: Path | None = None
    diverged: dict = dataclasses.field(default_factory=dict)  # backup dst (str) -> sibling pre-image (str)
    counts: dict = dataclasses.field(default_factory=dict)
    git_dirty: bool | None = None
    companion_regenerated: bool = False


def migrate_lessons_if_legacy(cfg: "InitConfig", from_version: str, to_version: str,
                              *, reconcile: str | None = None,
                              defer_legacy: bool = False) -> LessonsMigrationReport:
    """Migrate the project's lessons index when it is hand-authored. Never raises.

    `defer_legacy` makes the call detect-only for a hand-authored index: it writes nothing,
    reports state `deferred`, and names `/planwise upgrade` as the step that migrates it. A
    generated index is handled the same either way. Plain `init` sets it."""
    report = LessonsMigrationReport(state="absent", index_path=None)
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
    lessons_dir, index_path = config.get("_lessons_dir"), config.get("_lessons_index")
    if lessons_dir is None or index_path is None or not Path(index_path).is_file():
        return
    report.index_path = index_path
    report.backup_dir = (Path(cfg.project_root) / cfg.planwise_root / "upgrade-backups"
                         / f"{from_version}-to-{to_version}" / "lessons")
    text = read_text(index_path)
    shape, detail = sup.classify_shape(text)
    command = f"python {Path(cfg.plugin_root) / 'scripts' / MIGRATOR} --config {config_path}"
    if shape == "unrecognized":
        report.state, report.detail, report.fix = "unrecognized", detail, f"{command} --report"
        return
    if shape == "generated":
        _check_generated(cfg, from_version, to_version, config, index_path, report)
        return
    if defer_legacy:
        report.state = "deferred"
        report.detail = "the index is hand-authored; this run changed no lessons file"
        report.fix = "run /planwise upgrade, which migrates it"
        return

    archive_dir = lessons_dir / "Archive"
    inputs = [index_path, *sorted(lessons_dir.glob("LL-*.md")), *sorted(archive_dir.glob("LL-*.md"))]
    dirty, _reason = git_state(config["_project_root"], inputs)
    report.git_dirty = None if dirty is None else bool(dirty)
    mode = reconcile or "index-wins"
    options = mig.RepairOptions.all_on(mode)
    try:
        plan = mig.plan_migration(config, index_path, text, detail, options)
    except mig.Refusal as exc:
        _refuse(report, exc)
        return

    ledger_file = mig.ledger_path_for(lessons_dir)
    targets = mig.plan_targets(plan)
    pre = _backup(targets, lessons_dir, report)
    if pre is None:
        return
    existed = {p.resolve() for p in Path(lessons_dir).rglob("*") if p.is_file()}
    try:
        rc, output = _captured(mig.execute, plan, ledger_file, index_path, config, False)
    except Exception as exc:  # noqa: BLE001 -- any failure mid-write is rolled back, never left half-written
        rc, output = 1, f"migration write failed: {exc!r}"
    report.detail = output
    if rc != 0:
        created = [p for p in mig.writable_paths(plan) if p.is_file() and p.resolve() not in existed]
        _write_failed(report, pre, created,
                      "re-run /planwise upgrade; the migration restarts from the restored files")
        return
    created = [p for p in mig.writable_paths(plan) if p.is_file() and p.resolve() not in existed]
    _log_dispositions(cfg, from_version, to_version, pre, created, lessons_dir, report)
    report.state = "migrated"
    report.companion_regenerated = True  # execute() always runs the companion --write --replace-legacy step
    _fill_counts(ledger_file, report)
    _count_shards(config, index_path, report)


def _check_generated(cfg, from_version: str, to_version: str, config: dict, index_path: Path, report) -> None:
    """A generated index: check it and the companion, then re-split the
    changelog if it has grown over budget, or renumber it if its entry
    numbers do not strictly descend (the `changelog_split` state). Within
    budget and in order, state stays `generated` and the caller's banner
    never prints."""
    lessons_dir = config["_lessons_dir"]
    archive_dir = lessons_dir / "Archive"
    naming = mig._index_naming(index_path)
    index_exit, _out = _captured(mig._check_index, lessons_dir, archive_dir, index_path, naming, config)
    companion_exit, _out = _captured(
        gen._run_companion_cli, SimpleNamespace(write=False, json=False, replace_legacy=False),
        lessons_dir, archive_dir, index_path, naming, config)
    report.state = "generated"
    report.detail = f"index --check exit {index_exit}, companion --check exit {companion_exit}"
    _resplit_changelog(cfg, from_version, to_version, config, index_path, report)


def write_changelog_plan(plan: dict, lessons_dir: Path, report, rerun: str) -> list | None:
    """Write one `lessons_changelog` plan safely; the upgrade routine and
    the `lessons_changelog.py` CLI both call this. Every existing file the
    plan replaces or removes is backed up byte-exact under
    `report.backup_dir` first (`_backup`: the first pre-image wins). The
    outputs are written in the plan's own order, which puts each file an
    entry moves into before the file it leaves, and the removals come
    last. On any failure (an `OSError`, a partial replace, or text the
    encoder cannot write) every touched file is restored from its pre-image
    -- a file that existed before the run is never deleted -- and the
    report reads `backup_failed` or `write_failed`, its fix ending in
    `rerun` (what the caller re-runs). Returns one `(path, reason)`
    DISPOSITIONS row per file written or removed, or None after a
    failure."""
    outputs, remove = plan["outputs"], list(plan["remove"])
    out_paths = [p for p, _t in outputs]
    targets = list(dict.fromkeys([*(p for p in out_paths if Path(p).is_file()), *remove]))
    pre = _backup(targets, lessons_dir, report, also=out_paths)
    if pre is None:
        report.fix = f"free the backup location or fix its permissions, then {rerun}"
        return None
    try:
        written, output = _captured(backlog_mig.execute_outputs, outputs, remove)
    except Exception as exc:  # noqa: BLE001 -- any write failure is rolled back below, never a traceback
        written, output = None, f"changelog write failed: {exc}"
    if written != len(outputs):
        report.detail = output if written is None else f"changelog write wrote {written} of {len(outputs)} file(s)"
        created = [p for p in out_paths if pre.get(Path(p)) is None and Path(p).is_file()]
        _write_failed(report, pre, created, f"{rerun}; the write restarts from the restored files")
        return None
    rows = [(p, ("rewritten; " + _kept_at(p, lessons_dir, report)) if pre.get(Path(p)) is not None
             else "new part; " + CREATED) for p in out_paths]
    return rows + [(p, "removed; " + _kept_at(p, lessons_dir, report)) for p in remove]


def write_with_dispositions(plan: dict, config: dict, backup_dir: Path, day: str, action: str,
                            rerun_cmd: str, log_header: str) -> tuple:
    """Write `plan` through `write_changelog_plan`, then append one
    DISPOSITIONS row per file it touched to `backup_dir.parent /
    "DISPOSITIONS.md"` (`log_header` written once, the first time this log
    file is created). The one write-then-log path every manual writer into
    an existing family shares: `lessons_changelog.py --append`/`--split`,
    and `promotion_log.py`'s century-file creation and stale-listing
    repair -- never a second scheme invented in either caller. Returns
    `(ok, report)`; a failed write (`rows` is None) logs nothing, since
    there is nothing to log."""
    lessons_dir = Path(config["_lessons_dir"])
    report = LessonsMigrationReport(state="absent", index_path=config.get("_lessons_index"), backup_dir=backup_dir)
    rows = write_changelog_plan(plan, lessons_dir, report, rerun_cmd)
    if rows is None:
        return False, report
    log_path = backup_dir.parent / "DISPOSITIONS.md"
    header = "" if log_path.exists() else log_header
    lines = [f"- {day} `{_rel(p, lessons_dir).as_posix()}` — {action}: {reason}" for p, reason in rows]
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(header + "\n".join(lines) + "\n")
    except OSError as exc:
        print(f"  Warning: could not log dispositions to {log_path}: {exc}", file=sys.stderr)
    return True, report


def _resplit_changelog(cfg, from_version: str, to_version: str, config: dict, index_path: Path, report) -> None:
    """A generated index: re-split an over-budget changelog, or renumber an
    unstable one, with backups; or stay silent (mirrors
    `backlog_migration._resplit_changelog`). A project with no changelog
    file yet -- nothing this routine ever seeds itself, per the generator's
    own footer-pointer contract -- has nothing to re-split; state stays
    `generated`, exactly as when the changelog is within budget and
    numbered in order, or has converged (a file still over budget only
    because one entry is larger than the budget by itself)."""
    try:
        plan = changelog.plan_split(config, index_path)
    except FileNotFoundError:
        return
    except sup.Refusal as exc:
        _refuse_changelog(report, exc)
        return
    if plan is None:
        return
    rows = write_changelog_plan(plan, config["_lessons_dir"], report, "re-run /planwise upgrade")
    if rows is None:
        return
    for path, reason in rows:
        _log(cfg, from_version, to_version, path, "lessons-changelog-split", reason, report)
    report.state = "changelog_split"
    report.counts.update({"changelog_parts": plan["parts"], "changelog_kind": plan["kind"],
                          "changelog_renumbered": plan["renumbered"],
                          "changelog_files_written": len(plan["outputs"])})


def _refuse(report, exc) -> None:
    """State `refused`: the refusal's reason (every refusal line) as the
    detail, and its fix (the group names that close them) as the fix."""
    report.state, report.detail = "refused", exc.reason
    report.fix = f"{exc.fix}\n{RERUN}"


def _refuse_changelog(report, exc) -> None:
    """State `refused` for a changelog-only refusal. The refusal's reason names
    the changelog file and the line it found, and its own fix names the edit
    (or says to keep the changelog and report a defect). The re-run text must
    NOT claim the index is hand-authored -- it is generated -- unlike
    `_refuse`'s shared `RERUN` text, which is written for the legacy-migration
    refusal path and does make that claim."""
    report.state, report.detail = "refused", exc.reason
    report.fix = (f"{exc.fix}\nthen re-run /planwise upgrade "
                  "(the changelog is re-checked on every run; nothing else repeats)")


def _rel(path: Path, lessons_dir: Path) -> Path:
    """`path` relative to the lessons directory, keeping `Archive/`. A path
    outside it goes under `_outside/{digest of its directory}/`, so two
    same-named files never share one backup."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(lessons_dir).resolve())
    except ValueError:
        digest = hashlib.sha256(str(resolved.parent).encode("utf-8")).hexdigest()[:12]
        return Path("_outside") / digest / resolved.name


def _kept_at(path: Path, lessons_dir: Path, report) -> str:
    """The DISPOSITIONS reason naming where `path`'s pre-image sits, whether
    an earlier run made it, and a second pre-image location when this run's
    own bytes diverged from that kept one."""
    rel = _rel(path, lessons_dir)
    dst = report.backup_dir / rel
    earlier = " (made by an earlier run in this version pair; kept, not overwritten)"
    sibling = report.diverged.get(str(dst))
    extra = ""
    if sibling:
        sibling_rel = Path(sibling).relative_to(report.backup_dir)
        extra = (f"; current bytes differed, also backed up to "
                 f"upgrade-backups/{report.backup_dir.parent.name}/lessons/{sibling_rel.as_posix()}")
    return (f"pre-image at upgrade-backups/{report.backup_dir.parent.name}/lessons/{rel.as_posix()}"
            + (earlier if str(dst) in report.kept else "") + extra)


def _next_free_sibling(dst: Path) -> Path:
    n = 1
    while True:
        candidate = dst.with_name(f"{dst.name}.{n}.bak")
        if not candidate.exists():
            return candidate
        n += 1


def _matching_sibling(dst: Path, current: bytes) -> Path | None:
    n = 1
    while True:
        candidate = dst.with_name(f"{dst.name}.{n}.bak")
        if not candidate.exists():
            return None
        if candidate.read_bytes() == current:
            return candidate
        n += 1


def _backup(targets: list, lessons_dir: Path, report, also: list = ()) -> dict | None:
    """Copy every existing target byte-exact before any write, and return
    this run's pre-image of each target and each path in `also` (None for
    a file that does not exist yet). The first pre-image wins. None means
    stop: nothing was written. `report.backed_up` lists only the copies
    this run made; `report.kept` lists the backups an earlier run made,
    left as they were."""
    for src in targets:
        dst = report.backup_dir / _rel(src, lessons_dir)
        if str(dst) in report.backed_up or str(dst) in report.kept:
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
                report.backed_up.append(str(dst))
        except OSError as exc:
            return _backup_failed(report, src, exc)
    try:
        return {Path(p): Path(p).read_bytes() if Path(p).exists() else None for p in [*targets, *also]}
    except OSError as exc:
        return _backup_failed(report, "a pre-image", exc)


def _backup_failed(report, src, exc) -> None:
    report.state = "backup_failed"
    report.detail = f"could not back up {src}: {exc}"
    report.fix = "free the backup location or fix its permissions, then " + RERUN


def _write_failed(report, pre: dict, created: list, fix: str) -> None:
    """State `write_failed`, after putting every pre-existing path the
    write could touch back to its pre-image and unlinking every file it
    created (`created`: the migrator's `writable_paths` that did not exist
    before the write, found after it, so a partial write is covered too).
    The lessons tree then equals its pre-run bytes."""
    report.state, report.fix = "write_failed", fix
    try:
        for path, data in pre.items():
            if data is None:
                path.unlink(missing_ok=True)
            elif not path.is_file() or path.read_bytes() != data:
                path.write_bytes(data)
        for path in created:
            path.unlink(missing_ok=True)
    except OSError as exc:
        report.detail += f"\nrestore failed ({exc}); the tree is partly written -- restore it from {report.backup_dir}"
        report.fix = f"copy the backed-up files back from {report.backup_dir} by hand, {RERUN}"
        return
    report.detail += ("\nthe tree was restored: every file this step touched is back to its pre-run bytes, "
                      f"and the {len(created)} file(s) it created are removed")


def _action_on(path: Path, pre_image: bytes) -> str:
    """What the write did to a file that existed before it."""
    try:
        if not path.is_file():
            return "lessons-deleted"
        return "lessons-unchanged" if path.read_bytes() == pre_image else "lessons-rewritten"
    except OSError:
        return "lessons-unreadable-after-write"


def _log_dispositions(cfg, from_version: str, to_version: str, pre: dict, created: list,
                      lessons_dir: Path, report) -> None:
    """One DISPOSITIONS row per file this run backed up, rewrote, created or
    deleted. Each pre-existing target gets the action the write took on it
    and where its pre-image sits, including a pre-image an earlier run
    made. Each file the write created gets `lessons-created`."""
    seen: set = set()
    for path, data in pre.items():
        if data is None or path.resolve() in seen:
            continue
        seen.add(path.resolve())
        _log(cfg, from_version, to_version, path, _action_on(path, data),
             _kept_at(path, lessons_dir, report), report)
    for path in created:
        if path.resolve() not in seen:
            seen.add(path.resolve())
            _log(cfg, from_version, to_version, path, "lessons-created", CREATED, report)


def _backups_note(report) -> str:
    """`N file(s) this run`, plus the count an earlier run made and this
    one kept, for the banner's backups line."""
    kept = f"; {len(report.kept)} kept from an earlier run" if report.kept else ""
    return f"{len(report.backed_up)} file(s) this run{kept}"


def _log(cfg, from_version: str, to_version: str, path: Path, action: str, reason: str, report) -> None:
    upgrade_io._append_disposition_log(cfg, from_version, to_version, Path(path), action, reason)
    report.written.append(str(path))


def _captured(func, *args):
    """Call `func`, keeping its stdout and stderr out of the caller's banner."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        result = func(*args)
    return result, buf.getvalue().strip()


def _fill_counts(ledger_path: Path, report) -> None:
    """Counts come from the ledger, and only from a finished write. A
    ledger in an unexpected shape leaves the counts unset and never
    changes the state."""
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
        report.counts.update(_ledger_counts(ledger))
    except (KeyError, TypeError, AttributeError) as exc:
        report.detail = (report.detail + f"\nledger shape not recognised ({exc!r}); counts left unset").strip()


def _ledger_counts(ledger: dict) -> dict:
    c, p, cells, prose = ledger["changelog"], ledger["promotion_log"], ledger["cells"], ledger["prose"]
    reconcile, gen_exits = ledger["reconcile"], ledger["generator"]
    return {
        "changelog_entries": c["entries"], "changelog_parts": max(len(c["parts"]), 1), "changelog_path": c["path"],
        "promotion_log_rows": p["rows"], "promotion_log_files": len(p["files"]),
        "backfilled": len(ledger["backfill"]), "quoted": len(ledger["quotes"]),
        "reconciled_cells": len(reconcile["cells"]), "reconcile_mode": reconcile["mode"] or "index-wins",
        "cells_appended": sum(c2["appended"] for c2 in cells), "cells_files": len(cells),
        "cells_skipped": sum(c2["skipped_present"] for c2 in cells),
        "prose_dropped": len(prose["drop"]), "prose_relocated": len(prose["relocate"]),
        "companion_renamed": ledger["companion"]["renamed"],
        # "accepted" (only classes --write never heals) counts as clean.
        "generator_check_clean": mig.generator_succeeded(gen_exits),
    }


def _count_shards(config: dict, index_path: Path, report) -> None:
    try:
        lessons_dir = config["_lessons_dir"]
        files = parse_lessons.generated_index_files(lessons_dir, lessons_dir / "Archive", index_path)
    except OSError:
        return
    hub = Path(index_path).resolve()
    report.counts["shards"] = sum(1 for p in files if Path(p).resolve() != hub)


def _say(line: str = "") -> None:
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"))


def _banner_lines(report: LessonsMigrationReport) -> list:
    index = report.index_path
    fix = report.fix.replace("\n", "\n          ")
    if report.state == "changelog_split":
        return [_changelog_split_line(report)]
    if report.state == "deferred":
        return ["Lessons index migration: DEFERRED (index and lesson files left untouched)",
                f"  reason: {report.detail}", f"  fix:    {fix}"]
    if report.state == "refused":
        return ["Lessons index migration: REFUSED (index and lesson files left untouched)",
                "  reason: " + report.detail.replace("\n", "\n          "), f"  fix:    {fix}"]
    if report.state == "unrecognized":
        return [f"Lessons index migration: {index} is not a hand-authored or generated index -- left untouched",
                *(f"  detail: {line}" for line in report.detail.splitlines() or [""])]
    if report.state == "backup_failed":
        return ["Lessons index migration: BACKUP FAILED -- no write was attempted",
                f"  {report.detail}", f"  fix:    {fix}"]
    if report.state == "write_failed":
        return ["Lessons index migration: WRITE FAILED", f"  {report.detail}",
                f"  backups: {report.backup_dir} ({_backups_note(report)})", f"  fix:    {fix}"]
    if report.state == "error":
        return ["Lessons index migration: ERROR (nothing else in this run depends on it)", f"  {report.detail}"]
    return _migrated_lines(report)


def _changelog_split_line(report: LessonsMigrationReport) -> str:
    """The one `changelog_split` banner line. It states the real limits: the
    main file stays under `READ_TOKEN_WARN`, each archive part under
    `READ_PAGE_CAP_TOKENS`, and a file holding one larger entry keeps it
    whole. A renumber says so, and a renumber alone names no limits.

    A renumber's "across N file(s)" names the files this run actually
    wrote (`changelog_files_written`), never the family's whole file
    count (`changelog_parts`): a renumber that lands on an already-correct
    number leaves that file byte-identical and out of `plan["outputs"]`,
    so the two counts can differ -- a positional family renumbering its
    main file alone, with its archive's lone entry already numbered 1,
    prints "across 1 file(s)", not the family's 2."""
    c = report.counts
    parts, renumbered = c.get("changelog_parts"), c.get("changelog_renumbered", 0)
    written = c.get("changelog_files_written", parts)
    done = f"renumbered {renumbered} entries by position (the oldest is Entry 1)" if renumbered else ""
    if c.get("changelog_kind") == "renumber":
        return f"Lessons changelog: {done} across {written} file(s); backups: {report.backup_dir}"
    split = (f"re-split into {parts} part(s) (main file under {sup.READ_TOKEN_WARN} tokens, each archive part "
             f"under {sup.READ_PAGE_CAP_TOKENS}; a file holding one larger entry keeps it whole)")
    return f"Lessons changelog: {done + ' and ' if done else ''}{split}; backups: {report.backup_dir}"


def _migrated_lines(report: LessonsMigrationReport) -> list:
    c = report.counts
    lines = ["Lessons index migration:",
             f"  migrated: {report.index_path} -> generated hub + {c.get('shards', '?')} shard(s)"]
    if "changelog_entries" in c:
        lines += [
            (f"    changelog:               {c['changelog_path']} + {max(c['changelog_parts'] - 1, 0)} "
             f"part(s) ({c['changelog_entries']} entries)"),
            f"    promotion log:           {c['promotion_log_rows']} row(s) into {c['promotion_log_files']} file(s)",
            f"    frontmatter backfilled:  {c['backfilled']} lesson file(s)",
            f"    titles quoted:           {c['quoted']} lesson file(s)",
            f"    reconciled status cells: {c['reconciled_cells']} ({c['reconcile_mode']})",
            (f"    index notes appended:   {c['cells_appended']} unit(s) into {c['cells_files']} lesson "
             f"file(s), {c['cells_skipped']} already present"),
            f"    prose sections:          {c['prose_dropped']} dropped (seed text), {c['prose_relocated']} relocated",
            ("    companion:               regenerated" + (f"; hand prose in {c['companion_renamed']}"
                                                            if c.get("companion_renamed") else "")),
        ]
    elif report.detail:
        lines.append(f"    counts:                  unavailable -- {report.detail.splitlines()[-1]}")
    lines += [f"    ledger:                  {report.ledger_path or 'none'}"]
    if report.backed_up or report.kept:
        lines.append(f"    backups:                 {report.backup_dir} ({_backups_note(report)}, "
                     "listed in DISPOSITIONS.md)")
    else:
        lines.append("    backups:                 none (no file was rewritten this run)")
    dirty = {True: "yes", False: "no", None: "unknown"}[report.git_dirty]
    lines += [f"    git tree was dirty:      {dirty} (informational -- the backup above is the restore point)",
              ("    generator --check:      clean" if c.get("generator_check_clean")
               else "    generator --check:      not clean; re-run /planwise upgrade")]
    return lines


def _emit_lessons_migration_banner(report: LessonsMigrationReport) -> None:
    """Print one banner block for the report; silent on `absent` and
    `generated`. Never raises."""
    if report.state in SILENT_STATES:
        return
    try:
        lines = _banner_lines(report)
    except Exception as exc:  # noqa: BLE001 -- a banner must never fail the caller
        lines = [f"Lessons index migration: {report.state} ({report.detail or exc!r})"]
    for line in lines:
        _say(line)
    _say()
