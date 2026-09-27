#!/usr/bin/env python3
"""Migrate a hand-authored lessons index into the generator's shape.

A legacy hub carries content the generator drops on regeneration: header
history, the Rule Promotion Log, and hand-written prose. This relocates it,
backfills missing frontmatter, appends over-title Title-cell prose, then
runs the generator with `--replace-legacy`.

`--dry-run` (default): reports the plan, writes nothing. `--write`: stages
every relocated output, replaces with the index last, runs the generator's
`--write --replace-legacy` for the index and companion, checks both,
verifies from disk, writes the ledger. `--report`: read-only JSON, never
writes, exit 0.

Recognise-or-refuse: refuses (exit 2), listing every refusal in one run,
each grouped under the flag that closes it --
`--backfill-frontmatter`, `--quote-titles`, `--reconcile`,
`--harvest-cells`, `--relocate-prose` -- or, behind no flag, an
unresolvable id, a malformed row, an existing rename target, or foreign
content at a changelog/promotion-log path.

Repairs are off by default; `lessons_migration.py` runs every flag on with
backups first, for `/planwise upgrade`/`init`. The only production caller
of `--replace-legacy`.

Atomic/resumable: outputs stage beside their targets, index last,
unchanged; a re-run matches its own prior output rather than refusing.

Exit codes: 0 clean/nothing to do, 1 needed/write-failure, 2 refused.
"""
import argparse
import contextlib
import io
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_lessons_index as gen
import migrate_lessons_repairs as repairs
import migrate_lessons_support as sup
import parse_lessons
from backlog_index_schema import _changelog_filename, _index_naming
from config_loader import load_config
from lessons_bootstrap import NOTES_SEED_CONTENT
from migrate_backlog_support import JOURNAL_MODE, ReplaceError
from parse_lessons import format_id
from reconcile_common import read_text_preserving_newlines as read_text

Refusal = sup.Refusal

RECONCILE_MODES = ("index-wins", "frontmatter-wins")
LEDGER_FILENAME = "00-Lessons-Migration-Ledger.json"

# The legacy Master Table's fixed 9-column layout (the header never varies).
ROLE_ORDER = ("id", "title", "category", "severity", "language",
              "technology", "domain", "source", "status")

_GENERATOR_EXIT_KEYS = ("index_write_exit", "companion_write_exit",
                        "index_check_exit", "companion_check_exit")

# `--check` finding classes `--write` never heals: an index `--check` that
# exits 1 with only these is the reading the lessons handler's own index
# gate passes, so a migration ending there has succeeded.
ACCEPTED_CHECK_CLASSES = frozenset({"location-anomaly", "counter_ahead"})

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class RepairOptions:
    """Which repairs `plan_migration` may make. Every repair is off by default."""
    backfill_frontmatter: bool = False
    quote_titles: bool = False
    reconcile: str | None = None
    harvest_cells: bool = False
    relocate_prose: bool = False

    @classmethod
    def all_on(cls, reconcile: str = "index-wins") -> "RepairOptions":
        return cls(backfill_frontmatter=True, quote_titles=True, reconcile=reconcile,
                   harvest_cells=True, relocate_prose=True)


def _today() -> str:
    """Today's local date, ISO form."""
    return datetime.now().astimezone().date().isoformat()


def generator_verdict(exits: dict | None) -> str:
    """"clean" when every generator step exited 0; "accepted" when the
    only nonzero step is the index `--check` exiting 1 with every finding
    in `ACCEPTED_CHECK_CLASSES`; "failed" otherwise, including a step that
    never ran, any other finding class, and any exit 2."""
    exits = exits or {}
    if all(exits.get(k) == 0 for k in _GENERATOR_EXIT_KEYS):
        return "clean"
    classes = exits.get("index_check_findings") or []
    others_clean = all(exits.get(k) == 0 for k in _GENERATOR_EXIT_KEYS if k != "index_check_exit")
    if others_clean and exits.get("index_check_exit") == 1 and classes and set(classes) <= ACCEPTED_CHECK_CLASSES:
        return "accepted"
    return "failed"


def generator_succeeded(exits: dict | None) -> bool:
    return generator_verdict(exits) != "failed"


def migration_date(ledger_file: Path) -> str:
    """The date to stamp into planned text. An unfinished earlier run's
    journal or ledger pins the date it used, and a resume reuses it, so a
    resumed run on a later day plans byte-identical text and recognises
    its own earlier output rather than refusing it as foreign. Today's
    date otherwise."""
    try:
        data = json.loads(read_text(ledger_file))
    except (OSError, ValueError):
        return _today()
    if not isinstance(data, dict):
        return _today()
    verification = data.get("verification") or {}
    unfinished = (data.get("mode") == JOURNAL_MODE or not generator_succeeded(data.get("generator"))
                  or not verification.get("verified", False))
    pinned = data.get("migration_date")
    if unfinished and isinstance(pinned, str) and _ISO_DATE_RE.match(pinned):
        return pinned
    return _today()


def say(code: int, msg: str, json_mode: bool, err: bool = False) -> int:
    print(msg, file=sys.stderr if (err or json_mode) else sys.stdout)
    return code


def ledger_path_for(lessons_dir: Path) -> Path:
    """The migration ledger's path (mirrors the backlog ledger's convention)."""
    return lessons_dir / LEDGER_FILENAME


def _captured(func, *args, **kwargs):
    """Call `func`, keeping its stdout and stderr out of the caller's own output."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        result = func(*args, **kwargs)
    return result, buf.getvalue().strip()


def _row_map(cells: list) -> dict:
    return {name: cells[i] for i, name in enumerate(ROLE_ORDER) if i < len(cells)}


def _resolve_rows(lessons_dir: Path, archive_dir: Path, rows: list, refusals: list) -> dict:
    """`{id: (path, row)}` per Master Table row; appends `(fix, detail)`
    to `refusals` for a malformed row or an id resolving to zero or >1
    files, and leaves that row out."""
    by_id: dict = {}
    for lesson_id, path in parse_lessons.lesson_files(lessons_dir, archive_dir):
        by_id.setdefault(lesson_id, []).append(path)
    resolved = {}
    for row in rows:
        if row.malformed or row.id == -1:
            refusals.append((sup.FIX_ROW, (f"Master Table row at line {row.line} does not parse as a "
                                           f"lesson row: {row.reason or 'unrecognised shape'}")))
            continue
        matches = by_id.get(row.id, [])
        if len(matches) != 1:
            refusals.append((sup.FIX_RESOLVE, (f"lesson id {format_id(row.id)} (Master Table line "
                                               f"{row.line}) resolves to {len(matches)} file(s) under "
                                               "the lessons directory and Archive/; expected exactly one")))
            continue
        resolved[row.id] = (matches[0], row)
    return resolved


def _existing_or_none(path: Path, planned_text: str, index_name: str):
    """None when `path` may be written: absent, header-only (the bootstrap
    shape), or already matching `planned_text` (a resumed run). Otherwise
    the refusal naming the foreign content."""
    if not path.exists():
        return None
    existing = read_text(path)
    if sup.header_only(existing, index_name) or existing == planned_text:
        return None
    return (f"{path} already exists with content this migration did not write; move it aside "
            "or delete it, then re-run")


# --- Planning ---


def plan_migration(config: dict, index_path: Path, text: str, detail, options: RepairOptions) -> dict:
    """Plan a `legacy` hub's migration in memory. Nothing is written. Every
    refusal is collected in one pass, then raised once as a
    `sup.RefusalSet` grouping each under the flag or hand fix that closes
    it. The seed's empty placeholder rows are skipped and counted. Order:
    locate regions, walk the Master Table, resolve rows to files,
    backfill/quote/reconcile/harvest, extract the changelog and promotion
    log, disposition prose, plan the companion rename."""
    lessons_dir = config["_lessons_dir"]
    archive_dir = lessons_dir / "Archive"
    naming = _index_naming(index_path)
    index_nl = sup.newline_of(text)
    today = migration_date(ledger_path_for(lessons_dir))
    refusals: list = []

    regions = sup.locate_regions(text)
    rows, placeholder_lines = sup.split_placeholder_rows(
        parse_lessons.parse_legacy_master_table(text, source=index_path))
    resolved = _resolve_rows(lessons_dir, archive_dir, rows, refusals)

    valid_statuses = gen._resolve_valid_statuses(config)
    lesson_texts: dict = {}
    backfill_records, quote_records, reconcile_cells, cells_records = [], [], [], []

    for lesson_id in sorted(resolved):
        path, row = resolved[lesson_id]
        row_map = _row_map(row.cells)
        original_text = read_text(path)
        source_text = original_text
        nl = sup.newline_of(source_text)

        try:
            plan_bf = repairs.backfill_plan(path, source_text, row_map, valid_statuses, today,
                                            project_root=config["_project_root"], lessons_dir=lessons_dir)
        except repairs.RepairRefused as exc:
            refusals.append((sup.FIX_LESSON, str(exc)))
            continue
        if plan_bf:
            if not options.backfill_frontmatter:
                refusals.append((sup.FIX_BACKFILL, f"{path} is missing frontmatter key(s): {', '.join(sorted(plan_bf))}"))
            else:
                values = {key: value for key, (value, _source) in plan_bf.items()}
                source_text = repairs.insert_missing_keys(source_text, values, nl)
                backfill_records.append({"path": str(path), "keys_added": sorted(plan_bf),
                                         "sources": {k: s for k, (_v, s) in plan_bf.items()}})

        quoted_text, changed = repairs.quote_title_if_needed(source_text)
        if changed:
            if not options.quote_titles:
                refusals.append((sup.FIX_QUOTES, f"{path} has a title: value an inline # would truncate"))
            else:
                source_text = quoted_text
                quote_records.append(str(path))

        row_status = row_map.get("status")
        try:
            reconciled_text, changed, reconcile_detail = repairs.reconcile_status(
                source_text, row_status, options.reconcile, valid_statuses)
        except repairs.RepairRefused as exc:
            refusals.append((sup.FIX_RECONCILE, (f"{path} disagrees with its Master Table row "
                                                 f"(line {row.line}): {str(exc).split(';')[0]}")))
        else:
            if changed:
                source_text = reconciled_text
                reconcile_cells.append({"path": str(path), "detail": reconcile_detail})

        raw_map, has_block, _bom, _nl = repairs.partial_frontmatter(source_text)
        frontmatter_title = (raw_map or {}).get("title", "") if has_block else ""
        units = repairs.cell_units(row_map.get("title", ""), frontmatter_title)
        if units:
            if not options.harvest_cells:
                body_key = repairs.exact_key(source_text)
                if any(not repairs.contains_exact(repairs.exact_key(u), body_key) for u in units):
                    refusals.append((sup.FIX_HARVEST, f"{path} lacks a Title-cell sentence of line {row.line}"))
            else:
                new_text, appended, skipped = repairs.append_index_note(source_text, units, nl, today)
                if new_text != source_text:
                    source_text = new_text
                if appended or skipped:
                    cells_records.append({"path": str(path), "appended": len(appended),
                                          "skipped_present": len(skipped)})

        if source_text != original_text:
            lesson_texts[path] = source_text

    header_segments = sup.extract_header_changelog(text)
    log_placeholder_lines: list = []
    log_leftover: list = []
    promo_rows = sup.walk_promotion_log(text, refusals, log_placeholder_lines, log_leftover)
    log_residue, residue_lines = sup.promotion_log_residue(log_leftover)

    # Keyed by occurrence (`sup.locate_regions`): a repeated heading is
    # dispositioned once per occurrence, and only the first Master Table /
    # Rule Promotion Log is structural -- a repeat of either is prose.
    drop_sections, relocate_sections = [], []
    for key, section in regions["sections"].items():
        heading = section["heading"]
        if key == sup.PROMOTION_LOG_HEADING and log_residue:
            relocate_sections.append((heading, log_residue))
            if not options.relocate_prose:
                refusals.append((sup.FIX_RELOCATE, (
                    f"section '{heading}' carries text that is not a promotion-log row (line(s) "
                    f"{', '.join(str(n) for n in residue_lines)}) and would be dropped")))
        if key in (sup.MASTER_TABLE_HEADING, sup.PROMOTION_LOG_HEADING):
            continue
        disposition, _why = sup.section_disposition(heading, section["body"], sup.SEED_BODIES)
        if disposition == "drop":
            drop_sections.append(heading)
        else:
            relocate_sections.append((heading, section["body"]))
            if not options.relocate_prose:
                refusals.append((sup.FIX_RELOCATE, (f"prose section '{heading}' (line "
                                                    f"{section['line_start'] + 1}) differs from the "
                                                    "shipped seed and would be dropped")))

    changelog_segments = list(header_segments)
    if relocate_sections:
        changelog_segments.insert(0, sup.render_relocated_entry(relocate_sections, today))
    changelog_outputs = (sup.render_changelog(changelog_segments, naming.hub_name, index_nl, today)
                         if changelog_segments else [])
    changelog_path = lessons_dir / _changelog_filename(naming)
    promo_outputs = sup.render_promotion_logs(promo_rows, naming, index_nl) if promo_rows else []
    for name, out_text in changelog_outputs + promo_outputs:
        blocker = _existing_or_none(lessons_dir / name, out_text, naming.hub_name)
        if blocker:
            refusals.append((sup.FIX_FOREIGN, blocker))

    companion_path = lessons_dir / gen.COMPANION_FILENAME
    notes_path = lessons_dir / gen.NOTES_FILENAME
    companion_rename = None
    if companion_path.is_file():
        companion_text = read_text(companion_path)
        if _companion_needs_rename(companion_text):
            notes_text = read_text(notes_path) if notes_path.exists() else None
            if notes_text is not None and notes_text != companion_text and not _is_notes_seed(notes_text):
                refusals.append((sup.FIX_FOREIGN, (f"{notes_path} already exists; the hand-written "
                                                   "companion cannot be renamed onto it")))
            companion_rename = companion_text
    if refusals:
        raise sup.RefusalSet(refusals)

    outputs = [(path, txt) for path, txt in sorted(lesson_texts.items(), key=lambda kv: str(kv[0]))]
    outputs += [(lessons_dir / name, txt) for name, txt in changelog_outputs]
    outputs += [(lessons_dir / name, txt) for name, txt in promo_outputs]
    if companion_rename is not None:
        outputs.append((notes_path, companion_rename))
    outputs.append((index_path, text))  # unchanged bytes; the generator overwrites it next -- replaced last

    interrupted = any((lessons_dir / name).exists() for name, _t in changelog_outputs + promo_outputs)

    return {
        "index_path": index_path, "lessons_dir": lessons_dir, "migration_date": today,
        "naming": naming, "regions": regions,
        "rows": len(rows), "resolved": resolved,
        "backfill": backfill_records, "quotes": quote_records, "reconcile": reconcile_cells,
        "reconcile_mode": options.reconcile, "cells": cells_records,
        "drop_sections": drop_sections, "relocate_sections": relocate_sections,
        "header_segments": header_segments, "changelog_outputs": changelog_outputs,
        "changelog_path": changelog_path, "promo_rows": promo_rows, "promo_outputs": promo_outputs,
        "companion_rename": companion_rename, "notes_path": notes_path,
        "outputs": outputs, "interrupted": interrupted, "dests": [],
        "placeholders": {"master_table": len(placeholder_lines), "promotion_log": len(log_placeholder_lines)},
    }


def _companion_needs_rename(companion_text: str) -> bool:
    """True for a non-empty companion the generator's `--replace-legacy`
    write would overwrite: legacy-shaped, or not generated-shaped at all
    (a foreign file). Either kind is hand content, so it moves to the
    notes file first and is never silently overwritten. Mirrors the
    generator's own overwrite test, on CRLF-normalised text."""
    norm = companion_text.replace("\r\n", "\n")
    return bool(norm.strip()) and (gen.is_legacy_companion(norm) or not gen.is_generated_companion(norm))


def _is_notes_seed(notes_text: str) -> bool:
    """True when the notes file holds exactly what the lessons bootstrap
    seeds it with (`NOTES_SEED_CONTENT`, BOM removed, line endings
    ignored). A file with no hand content yet counts as absent: the
    companion rename replaces it, and the backup and rollback cover it
    like any other existing target (`writable_paths` names it)."""
    return sup.seed_normalized(notes_text) == sup.seed_normalized(NOTES_SEED_CONTENT)


def writable_paths(plan: dict) -> list:
    """Every path a `--write` of this plan can create, rewrite or remove,
    as the disk stands when called: each planned output, the ledger, the
    companion and its notes file, and every generated-index file on disk
    (the generator rewrites each one, or removes it as stale). Called
    before a write it names what to back up; called after a failed one it
    also names every file that write created."""
    lessons_dir = plan["lessons_dir"]
    paths = [path for path, _text in plan["outputs"]]
    paths += [ledger_path_for(lessons_dir), lessons_dir / gen.COMPANION_FILENAME, plan["notes_path"]]
    paths += [Path(p) for p in parse_lessons.generated_index_files(
        lessons_dir, lessons_dir / "Archive", plan["index_path"])]
    seen, out = set(), []
    for path in paths:
        if path.resolve() not in seen:
            seen.add(path.resolve())
            out.append(path)
    return out


def plan_targets(plan: dict) -> list:
    """Every existing file a `--write` of this plan may rewrite or remove,
    for a caller to back up first (`writable_paths`, existing files only)."""
    return [path for path in writable_paths(plan) if path.is_file()]


# --- Verification, ledger ---


def verify_written(plan: dict) -> list:
    """Re-read every planned output from disk and name each region or file
    that does not match. `unaccounted == 0` when this returns empty."""
    misses = []
    outputs_on_disk = {}
    for path, expected_text in plan["outputs"]:
        try:
            outputs_on_disk[path] = read_text(path)
        except OSError as exc:
            misses.append(f"{path} could not be re-read after the write ({exc})")
            continue
        if path != plan["index_path"] and outputs_on_disk[path] != expected_text:
            misses.append(f"{path.name} does not match the staged text")

    all_text = "\n".join(outputs_on_disk.values())
    for seg in plan["header_segments"]:
        body = seg["text"] if isinstance(seg, dict) else seg
        if body and body not in all_text:
            misses.append(f"a header-history span ({body[:60]!r}) is missing from every output")
    for heading, body in plan["relocate_sections"]:  # every occurrence of a repeated heading
        if body.strip() and body.strip() not in all_text:
            misses.append(f"the relocated '{heading}' section ({body.strip()[:40]!r}) is missing "
                          "from every output")
    for row in plan["promo_rows"]:
        cells = list(row["cells"]) + [""] * (4 - len(row["cells"]))
        line = "| " + " | ".join(cells) + " |"
        if line not in all_text:
            misses.append(f"promotion-log row for lesson {row.get('lesson_id')} "
                          f"(line {row['line']}) is missing from every output")
    return misses


def _relocated_bytes(sections: list) -> dict:
    """Relocated UTF-8 bytes per heading, summed over every occurrence."""
    out: dict = {}
    for heading, body in sections:
        out[heading] = out.get(heading, 0) + len(body.encode("utf-8"))
    return out


def build_ledger(plan: dict, exits: dict | None = None, misses: list | None = None) -> dict:
    return {
        "run_date": _today(),
        "mode": "dry-run" if exits is None else "write",
        "regions": {"header_segments": len(plan["header_segments"]),
                    "counter_present": plan["regions"]["counter"] is not None,
                    "sections_seen": sorted(plan["regions"]["sections"])},
        "changelog": {"path": str(plan["changelog_path"]),
                      "entries": len(plan["header_segments"]) + (1 if plan["relocate_sections"] else 0),
                      "parts": [str(plan["index_path"].parent / name) for name, _t in plan["changelog_outputs"]]},
        "promotion_log": {"rows": len(plan["promo_rows"]),
                          "files": [str(plan["index_path"].parent / name) for name, _t in plan["promo_outputs"]]},
        "placeholder_rows_skipped": plan["placeholders"],
        "backfill": plan["backfill"],
        "quotes": plan["quotes"],
        "reconcile": {"mode": plan["reconcile_mode"], "cells": plan["reconcile"]},
        "cells": plan["cells"],
        "prose": {"drop": plan["drop_sections"], "relocate": [h for h, _b in plan["relocate_sections"]],
                  "bytes": _relocated_bytes(plan["relocate_sections"])},
        "companion": {"renamed": str(plan["notes_path"]) if plan["companion_rename"] is not None else None},
        "migration_date": plan["migration_date"],
        "generator": exits or {k: None for k in _GENERATOR_EXIT_KEYS},
        "generator_verdict": None if exits is None else generator_verdict(exits),
        "unaccounted": 0 if misses is None else len(misses),
        "verification": None if misses is None else {"verified": not misses, "misses": misses},
    }


def format_report(plan: dict) -> str:
    return "\n".join([
        f"rows: {plan['rows']}",
        f"header segments: {len(plan['header_segments'])}",
        f"promotion log rows: {len(plan['promo_rows'])}",
        f"backfill: {len(plan['backfill'])} file(s)",
        f"quotes: {len(plan['quotes'])} file(s)",
        f"reconcile: {plan['reconcile_mode'] or 'off'}, {len(plan['reconcile'])} cell(s)",
        (f"cells: {sum(c['appended'] for c in plan['cells'])} unit(s) appended across "
         f"{len(plan['cells'])} file(s)"),
        f"prose: {len(plan['drop_sections'])} dropped, {len(plan['relocate_sections'])} relocated",
        f"companion: {'renamed' if plan['companion_rename'] is not None else 'no legacy companion found'}",
    ])


# --- Generator invocation, in process ---


def _check_index_findings(lessons_dir: Path, archive_dir: Path, index_path: Path, naming,
                          config: dict) -> tuple:
    """`(exit, findings)` of the read-only `--check` pipeline, in process:
    the same findings `--check --json` prints as `drift` and `anomalies`."""
    try:
        result, next_id_info, report, location_anomalies = gen._run_lessons_report_pipeline(
            lessons_dir, archive_dir, index_path, naming, config)
    except gen.LessonsGeneratorError:
        return gen.LessonsDisposition.REFUSED, []
    findings, _shape = gen._check_lessons_drift(
        result.items, report, lessons_dir, archive_dir, index_path, naming,
        next_id_info["next"], config, location_anomalies, result.duplicate_ids, result.id_mismatches)
    return gen.lessons_exit_code_for(write_mode=False, findings=findings), findings


def _check_index(lessons_dir: Path, archive_dir: Path, index_path: Path, naming, config: dict) -> int:
    """The read-only `--check` pipeline's exit code, callable in process with no argv."""
    return _check_index_findings(lessons_dir, archive_dir, index_path, naming, config)[0]


def _run_generator_steps(lessons_dir: Path, archive_dir: Path, index_path: Path, naming, config: dict) -> dict:
    """Both generator writes (index, companion) then both checks, each
    captured; returns the four exit codes plus the index check's finding
    classes, which `generator_verdict` reads."""
    index_write_exit, _out = _captured(
        gen._cmd_write_lessons, lessons_dir, archive_dir, index_path, naming, config,
        replace_legacy=True, json_out=False)
    companion_write_exit, _out = _captured(
        gen._run_companion_cli, SimpleNamespace(write=True, json=False, replace_legacy=True),
        lessons_dir, archive_dir, index_path, naming, config)
    (index_check_exit, findings), _out = _captured(
        _check_index_findings, lessons_dir, archive_dir, index_path, naming, config)
    companion_check_exit, _out = _captured(
        gen._run_companion_cli, SimpleNamespace(write=False, json=False, replace_legacy=False),
        lessons_dir, archive_dir, index_path, naming, config)
    return {"index_write_exit": index_write_exit, "companion_write_exit": companion_write_exit,
            "index_check_exit": index_check_exit, "companion_check_exit": companion_check_exit,
            "index_check_findings": sorted({f["class"] for f in findings})}


# --- Execute ---


def execute(plan: dict, ledger_file: Path, index_path: Path, config: dict, json_mode: bool) -> int:
    outputs = plan["outputs"]
    journal = {"mode": JOURNAL_MODE, "migration_date": plan["migration_date"],
               "targets": [str(p) for p, _t in outputs]}
    try:
        staged = sup.stage_all([(ledger_file, json.dumps(journal, indent=2) + "\n"), *outputs])
    except OSError as exc:
        return say(1, f"FAIL: staging failed ({exc}); nothing on disk changed.", json_mode, err=True)
    try:
        sup.replace_all(staged)
    except ReplaceError as exc:
        done = ", ".join(p.name for p in exc.done) or "none"
        return say(1, f"FAIL: replace stopped at {exc.path.name} ({exc.cause}). Replaced: {done}. "
                      "Rerun --write to resume; every repair is idempotent.", json_mode, err=True)

    lessons_dir = config["_lessons_dir"]
    archive_dir = lessons_dir / "Archive"
    naming = plan["naming"]
    generator_error = None
    try:
        exits = _run_generator_steps(lessons_dir, archive_dir, index_path, naming, config)
    except Exception as exc:  # noqa: BLE001 -- a generator crash must not crash this migrator
        exits, generator_error = {k: None for k in _GENERATOR_EXIT_KEYS}, repr(exc)

    misses = verify_written(plan)
    ledger = build_ledger(plan, exits, misses)
    try:
        sup.replace_all(sup.stage_all([(ledger_file, json.dumps(ledger, indent=2) + "\n")]))
    except (OSError, ReplaceError) as exc:
        return say(1, f"FAIL: migration written and verified={not misses}, but the ledger write "
                      f"failed ({exc}).", json_mode, err=True)

    if json_mode:
        print(json.dumps(ledger, indent=2))
    failed_generator = generator_error is not None or not generator_succeeded(exits)
    if misses or failed_generator:
        reasons = list(misses)
        if generator_error:
            reasons.append(f"generator step raised: {generator_error}; re-run --write to resume")
        elif failed_generator:
            reasons.append(f"generator step failed: {exits}")
        return say(1, "FAIL: " + "; ".join(reasons), json_mode, err=True)
    return say(0, f"WROTE: migration complete; ledger at {ledger_file}. Index and companion are "
                  "generated and clean.", json_mode)


def _resume_or_clean(config: dict, index_path: Path, ledger_file: Path, args, js: bool) -> int:
    """Shape is `generated`: resume at the generator step when the ledger
    says it did not finish; otherwise nothing to do."""
    if not ledger_file.exists():
        return say(0, "CLEAN: index is already in the generated shape; nothing to do.", js)
    try:
        ledger = json.loads(read_text(ledger_file))
    except (OSError, ValueError):
        return say(0, "CLEAN: index is already in the generated shape; nothing to do.", js)
    exits = ledger.get("generator") if isinstance(ledger, dict) else None
    finished = isinstance(exits, dict) and generator_succeeded(exits)
    if finished:
        return say(0, "CLEAN: index is already in the generated shape; nothing to do.", js)
    if not args.write:
        return say(1, "DRY-RUN: an earlier run's generator step did not finish; --write resumes it.", js)
    lessons_dir = config["_lessons_dir"]
    archive_dir = lessons_dir / "Archive"
    naming = _index_naming(index_path)
    new_exits = _run_generator_steps(lessons_dir, archive_dir, index_path, naming, config)
    if isinstance(ledger, dict):
        ledger["generator"], ledger["mode"] = new_exits, "write"
        ledger["generator_verdict"] = generator_verdict(new_exits)
        try:
            sup.replace_all(sup.stage_all([(ledger_file, json.dumps(ledger, indent=2) + "\n")]))
        except (OSError, ReplaceError):
            pass
    if not generator_succeeded(new_exits):
        return say(1, f"FAIL: generator step still failing: {new_exits}", js, err=True)
    return say(0, "WROTE: resumed at the generator step; index and companion are generated "
                  "and clean.", js)


# --- Read-only report ---


def build_report(config: dict, index_path: Path) -> dict:
    """The read-only readiness report: `--report` never writes, always
    exits 0."""
    text = read_text(index_path)
    shape, detail = sup.classify_shape(text)
    report = {"shape": shape, "detail": detail if shape == "unrecognized" else "", "index": str(index_path),
              "changelog": "missing", "promotion_log": "missing", "companion": "missing",
              "lessons": {"total": 0, "without_frontmatter": 0, "partial_frontmatter": 0,
                          "titles_needing_quotes": 0, "status_mismatches": 0},
              "cells": {"rows_with_over_title_units": 0, "units": 0},
              "prose_sections": {"drop": 0, "relocate": 0},
              "ready_with_all_repairs": shape == "generated", "would_refuse": []}
    lessons_dir = config.get("_lessons_dir")
    if lessons_dir is None:
        return report
    naming = _index_naming(index_path)
    changelog_path = lessons_dir / _changelog_filename(naming)
    if changelog_path.exists():
        c_text = read_text(changelog_path)
        report["changelog"] = "header-only" if sup.header_only(c_text, naming.hub_name) else "populated"
    companion_path = lessons_dir / gen.COMPANION_FILENAME
    if companion_path.exists():
        c_text = read_text(companion_path)
        norm = c_text.replace("\r\n", "\n")
        report["companion"] = ("generated" if not _companion_needs_rename(c_text)
                               else "legacy" if gen.is_legacy_companion(norm) else "foreign")
    if shape != "legacy":
        return report

    valid_statuses = gen._resolve_valid_statuses(config)
    archive_dir = lessons_dir / "Archive"
    rows, _skipped = sup.split_placeholder_rows(parse_lessons.parse_legacy_master_table(text, source=index_path))
    promo_rows = sup.walk_promotion_log(text, [])
    if promo_rows:
        hub_promo = lessons_dir / gen._promotion_log_filename(naming)
        report["promotion_log"] = ("header-only" if hub_promo.exists()
                                   and sup.header_only(read_text(hub_promo), naming.hub_name) else "populated")
    resolved = _resolve_rows(lessons_dir, archive_dir, rows, [])

    report["lessons"]["total"] = len(resolved)
    over_title_rows, over_title_units, today = 0, 0, _today()
    for lesson_id in sorted(resolved):
        path, row = resolved[lesson_id]
        row_map = _row_map(row.cells)
        source_text = read_text(path)
        try:
            plan_bf = repairs.backfill_plan(path, source_text, row_map, valid_statuses, today,
                                            project_root=config["_project_root"], lessons_dir=lessons_dir)
        except repairs.RepairRefused:
            plan_bf = {}
        if plan_bf:
            key = "without_frontmatter" if len(plan_bf) >= len(ROLE_ORDER) - 2 else "partial_frontmatter"
            report["lessons"][key] += 1
        _quoted, changed = repairs.quote_title_if_needed(source_text)
        if changed:
            report["lessons"]["titles_needing_quotes"] += 1
        raw_map, has_block, _bom, _nl = repairs.partial_frontmatter(source_text)
        current_status = (raw_map or {}).get("status", "").strip().strip("'\"") if has_block else ""
        row_status = str(row_map.get("status", "")).strip()
        if row_status and current_status and row_status != current_status:
            report["lessons"]["status_mismatches"] += 1
        frontmatter_title = (raw_map or {}).get("title", "") if has_block else ""
        units = repairs.cell_units(row_map.get("title", ""), frontmatter_title)
        body_key = repairs.exact_key(source_text)
        over = [u for u in units if not repairs.contains_exact(repairs.exact_key(u), body_key)]
        if over:
            over_title_rows += 1
            over_title_units += len(over)
    report["cells"] = {"rows_with_over_title_units": over_title_rows, "units": over_title_units}

    regions = sup.locate_regions(text)
    log_leftover: list = []
    sup.walk_promotion_log(text, [], None, log_leftover)
    if sup.promotion_log_residue(log_leftover)[0]:
        report["prose_sections"]["relocate"] += 1
    for key, section in regions["sections"].items():
        if key in (sup.MASTER_TABLE_HEADING, sup.PROMOTION_LOG_HEADING):
            continue
        disposition, _why = sup.section_disposition(section["heading"], section["body"], sup.SEED_BODIES)
        report["prose_sections"]["drop" if disposition == "drop" else "relocate"] += 1

    try:
        plan_migration(config, index_path, text, detail, RepairOptions.all_on())
        report["ready_with_all_repairs"] = True
    except Refusal as exc:  # every refusal, one line each, when the plan collected several
        report["would_refuse"] = exc.lines() if isinstance(exc, sup.RefusalSet) else [str(exc)]
    except Exception as exc:  # noqa: BLE001 -- --report never raises, whatever the input
        report["error"] = f"planning raised {exc!r}"
    return report


def _safe_report(config: dict, index_path: Path) -> dict:
    """`build_report`, except that no input can make it raise: an
    unexpected exception becomes an `error` field beside the shape."""
    try:
        return build_report(config, index_path)
    except Exception as exc:  # noqa: BLE001 -- --report never raises, whatever the input
        try:
            shape = sup.classify_shape(read_text(index_path))[0]
        except Exception:  # noqa: BLE001
            shape = "unknown"
        return {"shape": shape, "index": str(index_path), "error": repr(exc)}


# --- CLI ---


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="migrate_lessons_index.py", description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--config", type=Path, default=None, help="Path to config.yaml; overrides default search.")
    p.add_argument("--dry-run", action="store_true", help="Report the plan; write nothing (default behavior).")
    p.add_argument("--write", action="store_true", help="Perform the migration.")
    p.add_argument("--report", action="store_true",
                   help="Print a read-only JSON shape and readiness report; never writes; exit 0.")
    p.add_argument("--json", action="store_true", help="Emit the plan or ledger as JSON on stdout only.")
    p.add_argument("--backfill-frontmatter", action="store_true",
                   help="Fill a missing frontmatter key from the H1, the row, git, or mtime.")
    p.add_argument("--quote-titles", action="store_true",
                   help="Quote a title: value an inline # would otherwise truncate.")
    p.add_argument("--reconcile", choices=RECONCILE_MODES, default=None,
                   help="Settle a row/frontmatter status disagreement: the row wins, or the file.")
    p.add_argument("--harvest-cells", action="store_true",
                   help="Append every over-title Title-cell sentence to the lesson body, skipping "
                        "one already present verbatim.")
    p.add_argument("--relocate-prose", action="store_true",
                   help="Relocate a prose section differing from the seed into the changelog, "
                        "instead of refusing.")
    p.add_argument("--force", action="store_true", help="Proceed on a dirty working tree.")
    p.add_argument("--allow-untracked-tree", action="store_true",
                   help="Proceed when git cannot vouch for the tree.")
    return p


def options_from_args(args) -> RepairOptions:
    return RepairOptions(
        backfill_frontmatter=getattr(args, "backfill_frontmatter", False),
        quote_titles=getattr(args, "quote_titles", False),
        reconcile=getattr(args, "reconcile", None),
        harvest_cells=getattr(args, "harvest_cells", False),
        relocate_prose=getattr(args, "relocate_prose", False),
    )


def run(config: dict, args) -> int:
    """Run one migration, or `--report`, for an already-loaded `config` and
    parsed `args`."""
    js = args.json
    lessons_dir, index_path = config.get("_lessons_dir"), config.get("_lessons_index")
    if lessons_dir is None or index_path is None:
        return say(2, "REFUSED: config.yaml declares no project.lessons_dir.", js, err=True)
    if not index_path.exists():
        return say(2, f"REFUSED: index not found at {index_path}", js, err=True)
    if getattr(args, "report", False):
        print(json.dumps(_safe_report(config, index_path), indent=2))
        return 0

    archive_dir = lessons_dir / "Archive"
    inputs = [index_path, *sorted(lessons_dir.glob("LL-*.md"))]
    if archive_dir.is_dir():
        inputs += sorted(archive_dir.glob("LL-*.md"))
    dirty, reason = sup.git_state(config["_project_root"], inputs)
    if dirty is None and not args.allow_untracked_tree:
        return say(2, f"REFUSED: cannot determine the working-tree state -- {reason}. Commit the "
                      "lessons tree to git first, or pass --allow-untracked-tree.", js, err=True)
    if dirty is None:
        say(0, f"WARNING: proceeding without a git safety net -- {reason}.", js, err=True)

    text = read_text(index_path)
    shape, detail = sup.classify_shape(text)
    if shape == "unrecognized":
        return say(2, f"REFUSED: unrecognised index shape -- {detail}", js, err=True)

    ledger_file = ledger_path_for(lessons_dir)
    if shape == "generated":
        return _resume_or_clean(config, index_path, ledger_file, args, js)

    try:
        plan = plan_migration(config, index_path, text, detail, options_from_args(args))
    except Refusal as exc:
        return say(2, f"REFUSED: {exc}", js, err=True)

    paths = (index_path, ledger_file)
    refusal = sup.tree_gate(dirty, plan, paths, index_path, args.force)
    if refusal:
        return say(2, f"REFUSED: {refusal}", js, err=True)
    if not args.write:
        print(json.dumps(build_ledger(plan), indent=2) if js else format_report(plan))
        return say(1, "DRY-RUN: migration needed; no files written.", js)
    return execute(plan, ledger_file, index_path, config, js)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args()
    js = args.json
    if args.dry_run and args.write:
        return say(2, "REFUSED: --dry-run and --write are mutually exclusive.", js, err=True)
    if args.report and args.write:
        return say(2, "REFUSED: --report and --write are mutually exclusive; --report never writes.",
                   js, err=True)
    return run(load_config(Path(__file__)), args)


if __name__ == "__main__":
    sys.exit(main())
