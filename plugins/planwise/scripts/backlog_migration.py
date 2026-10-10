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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import config_loader
    import generate_backlog_index as gen
    import migrate_backlog_checks as chk
    import migrate_backlog_index as mig
    import migrate_backlog_repairs as repairs
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
ABBREV_DESCRIPTION = "{} (added by the upgrade; edit the description)"
YAML_WORDS = {"Y", "N", "YES", "NO", "ON", "OFF", "TRUE", "FALSE", "NULL"}  # unquoted, YAML reads these as non-strings


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
    plan_text, plan_config, added, matched = _abbrev_prepass(config, detail, text, index_path)
    try:
        plan = mig.plan_migration(plan_config, index_path, plan_text, detail, options)
    except mig.Refusal as exc:
        _refuse(report, exc, f"{command} --write --backfill-frontmatter --write-edges "
                                  f"--extract-dependency-notes --reconcile {mode} --append-ambiguous")
        return
    paths = mig.artifact_paths(index_path)
    backlog_dir = config["_backlog_dir"]
    if plan is not None:
        plan["abbreviations"] = {"added": [name for name, _d in added],
                                 "matched": [{"from": m["from"], "to": m["to"]} for m in matched]}
        plan["reconcile"]["cells"] += [{"id": m["id"], "key": "abbrev", "frontmatter": None, "index": m["from"],
                                        "winner": "configured-key", "written": m["to"], "path": m["path"]}
                                       for m in matched]
        targets = mig.plan_targets(plan) + ([paths[1]] if paths[1].is_file() else [])  # a ledger or journal left earlier
        targets += [config_path] if added else []
        pre = _backup(targets, backlog_dir, report, [*(p for p, _t in plan["outputs"]), paths[1]])
        if pre is None:
            return
        if added:  # the plan accepted the new keys; the config is edited only now, after its backup
            try:
                _write_abbreviations(config_path, added)
            except (OSError, ValueError) as exc:
                report.detail = f"could not add the abbreviation(s) to config.yaml: {exc}"
                _write_failed(report, pre, f"fix config.yaml, {RERUN}")
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
        if added:
            _log(cfg, from_version, to_version, config_path, "backlog-migrated",
                 f"added {', '.join(name for name, _d in added)} under abbreviations:; "
                 + _kept_at(config_path, backlog_dir, report), report)
    else:
        report.detail = "an earlier run migrated the index; this run regenerated it only (its counts are in that ledger)"
        if mig.interrupted_journal(paths[1]) is not None and not _settle_journal(cfg, from_version, to_version,
                                                                                  paths, backlog_dir, report):
            return
    if not _regenerate(cfg, from_version, to_version, config, index_path, report):
        if report.state != "backup_failed":
            report.state, report.fix = "write_failed", f"fix what the generator names, {RERUN}"
        return
    report.state = "migrated"
    if plan is not None:  # counts describe this run's migrator write, never an earlier run's ledger
        _fill_counts(paths[1], mode, report)
    _count_shards(config, index_path, report)


def _abbrev_prepass(config: dict, detail: tuple, text: str, index_path: Path):
    """Settle every abbreviation the index cells and item file names carry against `abbreviations:`.
    A cell that differs from a configured key only in case is retargeted to that key in the
    returned index text. An uppercase name no key matches is added to the returned config. Nothing
    is written: returns (index text, config, added [(name, description)], matched [{from, to, id,
    path}]). Anything it cannot read, or a config it cannot extend, comes back unchanged so the
    plan names the problem itself."""
    unchanged = (text, config, [], [])
    valid, configured = sup.configured_abbrevs(config), config.get("abbreviations")
    if valid is None or not isinstance(configured, dict):
        return unchanged
    header_idx, roles = detail
    try:
        rows = mig.resolve_rows(text, header_idx, roles, config, index_path, [])
    except mig.Refusal:
        return unchanged
    lines, matched, added = text.split("\n"), [], {}
    for row in rows:
        seg = (repairs.filename_fields(row["path"].name) or (None, None))[1]
        cell = sup.plain(row["cells"][roles["abbrev"]]) if "abbrev" in roles else ""
        for value in dict.fromkeys(v for v in (seg, cell) if v):
            hit = sup.case_match_abbrev(value, valid)
            if hit and value == cell:
                lines[row["line"]] = mig.retarget_cell(lines[row["line"]], cell, hit)
                matched.append({"from": cell, "to": hit, "path": row["path"],
                                "id": repairs.first_id_in(row["path"].stem) or ""})
            elif value not in valid and not hit and re.fullmatch(r"[A-Z][A-Z0-9]*", value):
                added[value] = ABBREV_DESCRIPTION.format(value)
    new_text = "\n".join(lines)
    if matched:  # keep the retargeting only if re-reading shows each cell now names its configured key
        try:
            again = {r["path"]: sup.plain(r["cells"][roles["abbrev"]])
                     for r in mig.resolve_rows(new_text, header_idx, roles, config, index_path, [])}
        except mig.Refusal:
            again = {}
        if any(again.get(m["path"]) != m["to"] for m in matched):
            new_text, matched = text, []
    if not added:
        return new_text, config, [], matched
    return new_text, {**config, "abbreviations": {**configured, **added}}, list(added.items()), matched


def _write_abbreviations(config_path: Path, added: list) -> None:
    """Splice one `NAME: "description"` line per `added` pair onto the end of the top-level
    `abbreviations:` block of config.yaml, keeping every other byte, comment and key. Raises
    ValueError when the block is not a plain mapping, and OSError after restoring the original bytes
    when the edited file does not load with the new keys."""
    before = config_path.read_bytes()
    crlf = b"\r\n" in before
    lines = before.decode("utf-8").split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(r"abbreviations:\s*(#.*)?\r?$", ln)), None)
    last = indent = None
    for j in range(start + 1 if start is not None else len(lines), len(lines)):
        body = lines[j].rstrip("\r")
        if not body.strip() or body.lstrip().startswith("#"):
            continue
        if not body[0].isspace():
            break
        last, indent = j, indent or body[:len(body) - len(body.lstrip())]
    if last is None:
        raise ValueError("its abbreviations: block is not a plain mapping this step can extend")
    keys = [f'"{n}"' if n in YAML_WORDS else n for n, _d in added]
    new = [f'{indent}{key}: "{d}"' + ("\r" if crlf else "") for key, (_n, d) in zip(keys, added)]
    config_path.write_bytes("\n".join([*lines[:last + 1], *new, *lines[last + 1:]]).encode("utf-8"))
    try:
        reloaded = config_loader.load_config(Path(__file__), config_path=config_path)
        ok = {n for n, _d in added} <= (sup.configured_abbrevs(reloaded) or set())
    except Exception:  # noqa: BLE001 -- any load failure means the edit is rejected
        ok = False
    if not ok:
        config_path.write_bytes(before)
        raise OSError("the edited config.yaml did not load with the new abbreviations; the original bytes were restored")


def _settle_journal(cfg, from_version: str, to_version: str, paths: tuple, backlog_dir: Path, report) -> bool:
    """The index is migrated but the ledger path still holds an interrupted run's journal. Back it up,
    rename it to `-Interrupted-{date}`, log the rename, and go on. False means stop: `report` says why."""
    ledger_path = paths[1]
    pre = _backup([ledger_path], backlog_dir, report, [ledger_path])
    if pre is None:
        return False
    parked = mig.interrupted_journal(ledger_path) or 0
    try:
        renamed = mig.settle_interrupted_journal(ledger_path)
    except (OSError, sup.ReplaceError) as exc:
        report.detail = f"could not rename the interrupted journal {ledger_path.name}: {exc}"
        _write_failed(report, pre, f"rename {ledger_path.name} by hand, {RERUN}")
        return False
    report.counts["journal_renamed_to"], report.counts["journal_parked_units"] = str(renamed), parked
    report.detail += (f"\n{ledger_path.name} held the journal of an interrupted run; it is kept whole as {renamed.name}, "
                      f"and its {parked} parked unit(s) remain there for review")
    _log(cfg, from_version, to_version, renamed, "backlog-migrated",
         f"interrupted journal renamed from {ledger_path.name}; " + _kept_at(ledger_path, backlog_dir, report), report)
    _log(cfg, from_version, to_version, ledger_path, "backlog-migrated",
         "replaced by a ledger note naming the renamed journal; " + _kept_at(ledger_path, backlog_dir, report), report)
    return True


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
        "relocated_lines": len(ledger.get("relocated_index_lines") or []),
        "relocated_bytes": sum(r["bytes"] for r in ledger.get("relocated_index_lines") or []),
        "reconciled_cells": len(cells),
        "reconcile_mode": ledger["reconcile"]["mode"] or mode,
        "reconciled": [_cell_line(c) for c in cells],
        "abbreviations_added": list((ledger.get("abbreviations") or {}).get("added") or []),
        "abbreviations_matched": [f"{m['from']} -> {m['to']}" for m in (ledger.get("abbreviations") or {}).get("matched") or []],
        "oversized_entries": len(ledger.get("oversized_single_entries") or []),
    }


def _cell_line(cell: dict) -> str:
    """One reconciled cell, as the banner lists it: the index value and what the cell settled to."""
    if cell.get("winner"):
        who = "file name wins" if cell["winner"] == "file-name" else "configured key"
        return f"{cell['id']}.{cell['key']}: {cell['index']} -> {cell['written']} ({who})"
    return f"{cell['id']}.{cell['key']}: {cell['frontmatter']} -> {cell['index']}"


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
            *([(f"    relocated index lines:  {c['relocated_lines']} ({c['relocated_bytes']} bytes) "
                f"into {c['changelog_path']}")] if c.get("relocated_lines") else []),
            *([f"    {mig.parked_line(c['parked_units'], c['parked_bytes'], report.ledger_path)}"]
              if c.get("parked_units") else []),
            f"    reconciled cells:       {c['reconciled_cells']} ({c['reconcile_mode']})"
            + (" — " + "; ".join(c["reconciled"][:5]) + reconciled if c["reconciled"] else ""),
            *([(f"    abbreviations added:    {', '.join(c['abbreviations_added'])} (placeholder descriptions in "
                "config.yaml; edit them)")] if c.get("abbreviations_added") else []),
            *([f"    abbreviations matched:  {'; '.join(c['abbreviations_matched'])}"]
              if c.get("abbreviations_matched") else []),
            *([f"    oversized entries kept whole: {c['oversized_entries']} (each under the Read page cap)"]
              if c.get("oversized_entries") else []),
        ]
    elif report.detail:
        lines.append(f"    counts:                 unavailable — {report.detail.splitlines()[-1]}")
    if c.get("journal_renamed_to"):
        held = c.get("journal_parked_units", 0)
        lines.append(f"    interrupted journal:    renamed to {c['journal_renamed_to']}"
                     + (f"; its {held} parked unit(s) remain there and need review" if held else ""))
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
