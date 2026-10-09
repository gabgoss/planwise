#!/usr/bin/env python3
"""Migrate a hand-authored plans index during `/planwise upgrade` and
`/planwise init`.

One idempotent routine, `migrate_plans_if_legacy`, and one banner emitter, on
`lessons_migration.py`'s shape. The trigger is the index's shape, not a
version, so a refused run re-fires on the next upgrade and a finished one
never repeats:

- `legacy` (hand-authored): plan every move in memory, back up each file the
  plan rewrites byte-exact, append the index's notes to the Master Plans, then
  run the generator for the index and check it.
- `generated`: check the index and stay silent either way.
- `unrecognized`: report the classifier's reason and touch nothing.

Recognise-or-refuse, never best-effort. Every step before the backup is
read-only, and a failed backup means no write is attempted. A failed write
restores every file it touched to this run's pre-image and removes every file
it created, then reports `write_failed`. The first pre-image wins: a backup an
earlier run left in the same version pair is kept, never overwritten. The
routine never raises: any unexpected exception becomes state `error`, so it
never fails the caller. The git working-tree state is reported for
information only, because the backup under
`{planwise_root}/upgrade-backups/{from}-to-{to}/plans/` is the restore point.

The state vocabulary is shared with the backlog and lessons migrations.
`changelog_split` is in it and is never returned, because the plans index has
no changelog.
"""
import contextlib
import dataclasses
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import config_loader
    import generate_plans_index as gen
    import migrate_plans_index as mig
    from config_gen import InitConfig
    from migrate_backlog_checks import git_state
    from migrate_backlog_support import Refusal
    from migrate_plans_ledger import ledger_counts, read_ledger_summary
    from reconcile_common import read_text_preserving_newlines as read_text
except ImportError as exc:
    raise ImportError(
        f"plans_migration could not import a sibling module ({exc}); "
        "the scripts/ directory appears to be partially installed"
    ) from exc

RERUN = ("then re-run /planwise upgrade (the migration re-fires on a hand-authored index; "
         "nothing else repeats)")
MIGRATOR = "migrate_plans_index.py"
STATES = ("absent", "generated", "unrecognized", "deferred", "refused", "backup_failed", "write_failed", "migrated",
          "changelog_split", "error")
SILENT_STATES = ("absent", "generated")


@dataclasses.dataclass
class PlansMigrationReport:
    """Outcome of `migrate_plans_if_legacy`, with banner-ready fields."""
    state: str  # absent | generated | unrecognized | deferred | refused | backup_failed | write_failed | migrated | changelog_split | error
    index_path: Path | None
    detail: str = ""
    fix: str = ""
    backup_dir: Path | None = None
    backed_up: list = dataclasses.field(default_factory=list)
    kept: list = dataclasses.field(default_factory=list)  # backups an earlier run made; left as they were
    written: list = dataclasses.field(default_factory=list)  # paths with a DISPOSITIONS row
    ledger_path: Path | None = None
    diverged: dict = dataclasses.field(default_factory=dict)  # backup dst (str) -> sibling pre-image (str)
    counts: dict = dataclasses.field(default_factory=dict)
    git_dirty: bool | None = None


def migrate_plans_if_legacy(cfg: "InitConfig", from_version: str, to_version: str,
                            *, reconcile: str | None = None,
                            defer_legacy: bool = False) -> PlansMigrationReport:
    """Migrate the project's plans index when it is hand-authored. Never raises.

    `reconcile` exists so the signature matches the backlog and lessons
    routines. The plans migration has exactly one resolution for a status
    disagreement, the Master Plan's, so the keyword is accepted and ignored.

    `defer_legacy` makes the call detect-only for a hand-authored index: it writes nothing,
    reports state `deferred`, and names `/planwise upgrade` as the step that migrates it. A
    generated index is handled the same either way. Plain `init` sets it."""
    report = PlansMigrationReport(state="absent", index_path=None)
    try:
        _migrate(cfg, from_version, to_version, report, defer_legacy)
    except Exception as exc:  # noqa: BLE001 -- the caller's upgrade must never fail on this step
        report.state, report.detail = "error", repr(exc)
    return report


def _migrate(cfg, from_version: str, to_version: str, report, defer_legacy: bool = False) -> None:
    config_path = Path(cfg.project_root) / cfg.planwise_root / "config.yaml"
    if not config_path.is_file():
        return
    config = config_loader.load_config(Path(__file__), config_path=config_path)
    plans_dir, index_path = config.get("_plans_dir"), config.get("_plans_index")
    if plans_dir is None or index_path is None or not Path(index_path).is_file():
        return
    report.index_path = index_path
    report.backup_dir = (Path(cfg.project_root) / cfg.planwise_root / "upgrade-backups"
                         / f"{from_version}-to-{to_version}" / "plans")
    text = read_text(index_path)
    shape, detail = mig.classify_shape(text)
    command = f"python {Path(cfg.plugin_root) / 'scripts' / MIGRATOR} --config {config_path}"
    if shape == "absent":
        return
    if shape == "unrecognized":
        report.state, report.detail, report.fix = "unrecognized", detail, f"{command} --report"
        return
    if shape == "generated":
        report.state = "generated"
        report.detail = f"index --check exit {gen.check_plans_index(config).exit_code}"
        return
    if defer_legacy:
        report.state = "deferred"
        report.detail = "the index is hand-authored; this run changed no plans file"
        report.fix = "run /planwise upgrade, which migrates it"
        return

    ledger_file = mig.ledger_path_for(plans_dir)
    try:
        plan = mig.plan_migration(config, index_path, text, mig.migration_date(ledger_file))
    except Refusal as exc:
        _refuse(report, exc)
        return
    targets = mig.plan_targets(plan)
    dirty, _reason = git_state(config["_project_root"], targets)
    report.git_dirty = None if dirty is None else bool(dirty)
    try:
        backups = mig.backup_targets(targets, plans_dir, report.backup_dir)
    except mig.BackupFailed as exc:
        report.state, report.detail = "backup_failed", str(exc)
        report.fix = "free the backup location or fix its permissions, " + RERUN
        return
    report.backed_up, report.kept, report.diverged = backups.backed_up, backups.kept, backups.diverged
    report.written += mig.log_backups(cfg, from_version, to_version, backups, plans_dir, report.backup_dir)
    plan["backup_dir"] = report.backup_dir

    existed = {p: p.exists() for p in mig.writable_paths(plan)}
    try:
        rc, output = _captured(mig.execute, plan, ledger_file, index_path, config, False)
    except Exception as exc:  # noqa: BLE001 -- any failure mid-write is rolled back, never left half-written
        rc, output = 1, f"migration write failed: {exc!r}"
    report.detail = output
    if rc != 0:
        created = [p for p, was in existed.items() if not was and p.is_file()]
        _write_failed(report, backups.pre, created)
        return
    report.state = "migrated"
    _fill_counts(ledger_file, report)


def _refuse(report, exc) -> None:
    """State `refused`: the refusal's reason as the detail, and its fix as the fix."""
    report.state, report.detail = "refused", exc.reason
    report.fix = f"{exc.fix}\n{RERUN}"


def _write_failed(report, pre: dict, created: list) -> None:
    """State `write_failed`, after putting every pre-existing path the write could touch back to its
    pre-image and removing every file it created. The plans tree then equals its pre-run bytes."""
    report.state = "write_failed"
    report.fix = "re-run /planwise upgrade; the migration restarts from the restored files"
    problem = mig.restore(pre, created)
    if problem:
        report.detail += f"\nrestore failed ({problem}); the tree is partly written -- restore it from {report.backup_dir}"
        report.fix = f"copy the backed-up files back from {report.backup_dir} by hand, {RERUN}"
        return
    report.detail += ("\nthe tree was restored: every file this step touched is back to its pre-run bytes, "
                      f"and the {len(created)} file(s) it created are removed")


def _captured(func, *args):
    """Call `func`, keeping its stdout and stderr out of the caller's banner."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        result = func(*args)
    return result, buf.getvalue().strip()


def _fill_counts(ledger_path: Path, report) -> None:
    """Counts come from the ledger's `## Summary`, and only from a finished write. A ledger in an unexpected
    shape leaves the counts unset and never changes the state."""
    if not Path(ledger_path).is_file():
        return
    report.ledger_path = ledger_path
    summary = read_ledger_summary(read_text(ledger_path))
    if summary.get("Mode") != "write":
        report.detail = (report.detail + f"\nledger mode is {summary.get('Mode')!r}, not 'write'; counts left unset").strip()
        return
    report.counts.update(ledger_counts(summary))


def _backups_note(report) -> str:
    """`N file(s) this run`, plus the count an earlier run made and this one kept."""
    kept = f"; {len(report.kept)} kept from an earlier run" if report.kept else ""
    return f"{len(report.backed_up)} file(s) this run{kept}"


def _say(line: str = "") -> None:
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"))


def _banner_lines(report: PlansMigrationReport) -> list:
    index = report.index_path
    fix = report.fix.replace("\n", "\n          ")
    if report.state == "deferred":
        return ["Plans index migration: DEFERRED (index and Master Plans left untouched)",
                f"  reason: {report.detail}", f"  fix:    {fix}"]
    if report.state == "refused":
        return ["Plans index migration: REFUSED (index and Master Plans left untouched)",
                "  reason: " + report.detail.replace("\n", "\n          "), f"  fix:    {fix}"]
    if report.state == "unrecognized":
        return [f"Plans index migration: {index} is not a hand-authored or generated index -- left untouched",
                *(f"  detail: {line}" for line in report.detail.splitlines() or [""])]
    if report.state == "backup_failed":
        return ["Plans index migration: BACKUP FAILED -- no write was attempted",
                f"  {report.detail}", f"  fix:    {fix}"]
    if report.state == "write_failed":
        return ["Plans index migration: WRITE FAILED", f"  {report.detail}",
                f"  backups: {report.backup_dir} ({_backups_note(report)})", f"  fix:    {fix}"]
    if report.state == "error":
        return ["Plans index migration: ERROR (nothing else in this run depends on it)", f"  {report.detail}"]
    return _migrated_lines(report)


def _row(label: str, value) -> str:
    return f"    {label + ':':<25}{value}"


def _migrated_lines(report: PlansMigrationReport) -> list:
    c = report.counts
    lines = ["Plans index migration:",
             f"  migrated: {report.index_path} -> generated from the Master Plans ({c.get('rows_post', '?')} row(s))"]
    if "appended" in c:
        lines += [
            _row("index notes appended", f"{c['appended']} item(s) into {c['master_plans']} Master Plan(s), "
                                         f"{c['already_present']} already present"),
            _row("unattributed notes", f"{c['unattributed']} (kept verbatim in the ledger)"),
            _row("uncarried index lines", f"{c.get('uncarried_lines', '?')} (listed verbatim in the ledger)"),
            _row("status changes", f"{c['status_changes']} (the Master Plan's Status line won)"),
            _row("rows", f"PRE {c['rows_pre']}, mapped {c['rows_mapped']}, POST {c['rows_post']}, "
                         f"added {c['rows_added']}"),
            _row("unresolved rows", f"{c['unresolved_rows']} (listed in the ledger; the generator dropped them)"),
        ]
    elif report.detail:
        lines.append(_row("counts", f"unavailable -- {report.detail.splitlines()[-1]}"))
    lines.append(_row("ledger", report.ledger_path or "none"))
    if report.backed_up or report.kept:
        lines.append(_row("backups", f"{report.backup_dir} ({_backups_note(report)}, listed in DISPOSITIONS.md)"))
    else:
        lines.append(_row("backups", "none (no file was rewritten this run)"))
    dirty = {True: "yes", False: "no", None: "unknown"}[report.git_dirty]
    lines.append(_row("git tree was dirty", f"{dirty} (informational -- the backup above is the restore point)"))
    verdict = c.get("generator_verdict")
    lines.append(_row("generator --check", "clean" if verdict == "clean" else
                      ("clean apart from tree anomalies" if verdict == "accepted" else "not clean; re-run /planwise upgrade")))
    return lines


def _emit_plans_migration_banner(report: PlansMigrationReport) -> None:
    """Print one banner block for the report; silent on `absent` and `generated`. Never raises."""
    if report.state in SILENT_STATES:
        return
    try:
        lines = _banner_lines(report)
    except Exception as exc:  # noqa: BLE001 -- a banner must never fail the caller
        lines = [f"Plans index migration: {report.state} ({report.detail or exc!r})"]
    for line in lines:
        _say(line)
    _say()
