#!/usr/bin/env python3
"""Migrate a hand-authored plans index to the generated one.

A hand-authored index carries prose the generator never reads: HTML comments
and narrative text in the Status cells. This migrator moves that text into the
Master Plan it belongs to, then lets `generate_plans_index.py` replace the
index. Nothing is judged by content. Each note goes to the Master Plan of the
nearest table row that precedes it in the file, and each Status-cell
narrative goes to its own row's Master Plan.

What a run does, in order:

1. Classify the index: `absent`, `generated`, `legacy` or `unrecognized`.
2. Plan every move in memory: walk the legacy table, collect every note,
   resolve each row to its Master Plan, attribute each note, compare each
   row's status token with its Master Plan's, render the new index and check
   it against the page budget. Any refusal is raised before a write.
3. Back up every target byte-exact, then append the notes to each Master Plan
   under `## Index Notes (harvested DATE)`. No existing Master Plan byte
   changes: the file before the run is a prefix of the file after it.
4. Run `generate_plans_index.py --write --replace-legacy`, then `--check`,
   re-read every output, and write the ledger.

A note with no preceding row, or whose row has no resolvable Master Plan, is
kept verbatim in the ledger under `## Unattributed Index Notes`. So is an HTML
comment that never closes, whatever row precedes it: an open comment written
into a Master Plan would hide everything appended after it. Any other
non-blank line the generator does not re-render is listed verbatim under
`## Uncarried Index Lines`. A
status disagreement resolves in the Master Plan's favour and is listed as
`status-changed`. A Master Plan's `**Status:**` line is never edited.

A run interrupted between the appends and the generator write resumes: the
notes already appended are recognised and skipped, and the migration date
pinned in the ledger is reused. `--dry-run` and `--report` write nothing.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_plans_index as gen
import parse_plans
from config_loader import load_config
from migrate_backlog_checks import git_state
from migrate_backlog_support import (
    Refusal,
    ReplaceError,
    newline_of,
    replace_all,
    stage_all,
)
from migrate_plans_backup import (  # noqa: F401 -- the routine imports these through here
    BackupFailed,
    Backups,
    backup_targets,
    log_backups,
    rel_path,
    restore,
)
from migrate_plans_ledger import (
    JOURNAL_MODE,
    accounting,
    build_ledger,
    generator_verdict,
    read_ledger_summary,
)
from migrate_plans_scan import (
    KIND_COMMENT,
    KIND_NARRATIVE,
    KIND_PROSE,
    KIND_TABLE_LINE,
    Item,
    classify_lines,
    narrative,
    scan_comments,
)
from reconcile_common import read_text_preserving_newlines as read_text

LEDGER_FILENAME = "00-Plans-Migration-Ledger.md"
CLI_PAIR = "manual"

# The plans index seed as shipped through 1.0.5.1, by sha256: LF (the git blob) and CRLF (Windows checkout).
SEED_SHAPES = {
    "0106791202523aaccdba40b9ae35eddd9b8b965f45252a6cbc652f87cbcc2134": "LF form",
    "6922b74f4110b98dd41bece61a69fc03c61dde7a02efcac1db2a3ff913dd80cc": "CRLF form",
}
BANNER = (
    "> [!note] Historical notes moved from the plans index on {date}, each attached to the row it followed "
    "in the index. They record what was true when written; this Master Plan's **Status:** line is authoritative."
)
HEADING = "## Index Notes (harvested {date})"
_HEADING_RE = re.compile(r"^## Index Notes \(harvested \d{4}-\d{2}-\d{2}\)", re.MULTILINE)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VERDICT_LINE_RE = re.compile(r"^- Generator verdict: [^\r\n]*", re.MULTILINE)


def _today() -> str:
    """Today's local date, ISO form."""
    return datetime.now().astimezone().date().isoformat()


def say(code: int, msg: str, json_mode: bool, err: bool = False) -> int:
    print(msg, file=sys.stderr if (err or json_mode) else sys.stdout)
    return code


def ledger_path_for(plans_dir: Path) -> Path:
    """The migration ledger's path. It is markdown, so a person can read the notes it keeps. It sits at
    the root of the plans directory, where the disk walk never looks, so it can never become a row."""
    return Path(plans_dir) / LEDGER_FILENAME


def _plan_key(path: Path) -> str:
    """One key per Master Plan file, whatever the spelling of the path that reached it: resolved, then
    case-folded where the platform's file system folds case."""
    return os.path.normcase(str(Path(path).resolve()))


# --- Shape ---


def classify_shape(text: str) -> tuple:
    """`(shape, detail)`: `absent` for a blank file, `generated`, `legacy`, or `unrecognized` for content with
    neither the legacy table header nor the generator's marker. The generator is never asked to write over
    an unrecognized file."""
    if not text.strip():
        return "absent", "the index is blank"
    shape = parse_plans.detect_index_shape(text)
    if shape == "generated":
        return "generated", "the index is already generated"
    if shape == "empty":
        return "unrecognized", ("the file has no `| Abbrev |` table header row and no `Generated:` line, "
                                "so it is neither a hand-authored nor a generated plans index")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest in SEED_SHAPES:
        return "legacy", (f"legacy seed shipped through 1.0.5.1 ({SEED_SHAPES[digest]}), "
                          f"{len(text.encode('utf-8'))} B, sha256 {digest[:8]}...{digest[-4:]}")
    return "legacy", "legacy hand-authored index"


# --- Reading the legacy index ---


def _plans_prefix(config: dict) -> str:
    project = config.get("project")
    value = project.get("plans_dir", "Plans") if isinstance(project, dict) else "Plans"
    return str(value).replace("\\", "/").strip("/")


def _resolve(plans_dir: Path, entries: list, path: str, abbrev: str) -> tuple:
    """`(Master Plan file or None, used_child_lookup)` for a row Path already stripped of the plans-dir
    prefix. The plain walk inverse comes first, so a flat plan with a root Master Plan never resolves to a
    child. A one-segment Path with no root Master Plan resolves to its single `Exec-` child, else its single
    `Meta-` child."""
    segments = [s for s in path.split("/") if s]
    if not segments:
        return None, False
    directory = "/".join(segments) + "/"
    candidate = parse_plans.master_plan_path_for(plans_dir, directory, abbrev)
    if candidate.is_file() and _inside(candidate, plans_dir):
        return candidate, False
    here = [e for e in entries if e.path == directory]
    if len(here) == 1:
        return here[0].file, False
    if len(segments) == 1:
        kids = [e for e in entries if e.path.startswith(directory) and e.path != directory]
        for prefix in (parse_plans.EXEC_DIR_PREFIX, parse_plans.META_DIR_PREFIX):
            pool = [e for e in kids if e.path.split("/")[1].startswith(prefix)]
            if pool:
                return (pool[0].file, True) if len(pool) == 1 else (None, False)
    return None, False


def _inside(path: Path, plans_dir: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(plans_dir).resolve())
    except ValueError:
        return False
    return True


# --- Planning ---


def _label(index_path: Path, item: Item) -> str:
    return f"*From {Path(index_path).name} line {item.line} ({item.kind}).*"


def _plan_append(dest: Path, items: list, index_path: Path, date: str, refusals: list):
    """The append for one Master Plan, or None when every item is already there. An item is present when its
    label line and its bytes appear together after an existing harvest heading in the file, with either line
    ending after the label. The file's line ending is read from the text before its first harvest heading, so
    a note appended with its own line endings never changes the ending a later run writes or looks for."""
    try:
        pre = read_text(dest)
    except (OSError, UnicodeDecodeError) as exc:
        refusals.append(f"cannot read {dest} as UTF-8 ({exc}); restore or re-encode it, then re-run")
        return None
    match = _HEADING_RE.search(pre)
    nl = newline_of(pre[:match.start()] if match else pre)
    tail = pre[match.start():] if match else ""
    new = []
    for item in items:
        item.present = bool(tail) and any(_label(index_path, item) + ending + item.text in tail
                                          for ending in ("\n", "\r\n"))
        if not item.present:
            new.append(item)
    if not new:
        return None
    eof_fix = nl if pre and not pre.endswith("\n") else ""
    block = eof_fix + nl + HEADING.format(date=date) + nl + nl + BANNER.format(date=date) + nl
    for item in new:
        block += nl + _label(index_path, item) + nl + item.text + nl
    post = pre + block
    return {"path": dest, "pre": pre, "text": post, "items": new, "newline": nl, "eof_fix": bool(eof_fix),
            "block_bytes": len(block.encode("utf-8")),
            "pre_bytes": len(pre.encode("utf-8")), "post_bytes": len(post.encode("utf-8")),
            "pre_sha256": hashlib.sha256(pre.encode("utf-8")).hexdigest()}


def _analyze(config: dict, index_path: Path, text: str, migration_date: str | None = None) -> dict:
    """Every step of the plan, in memory. Plan-time refusals are collected in `plan["refusals"]`."""
    plans_dir, index_path = Path(config["_plans_dir"]), Path(index_path)
    shape, detail = classify_shape(text)
    date = migration_date or _today()
    table = parse_plans.parse_index_table(text)
    prefix = _plans_prefix(config)
    entries = parse_plans.enumerate_master_plans(plans_dir)
    refusals: list = []

    resolved, prefixed, via_child, unresolved = {}, 0, 0, []
    raw_lines = {line.line_number: line.text for line in table.table_lines}
    for row in table.rows:
        path = row.path.replace("\\", "/")
        if prefix and path.startswith(prefix + "/"):
            path, prefixed = path[len(prefix) + 1:], prefixed + 1
        file, child = _resolve(plans_dir, entries, path, row.abbrev)
        if file is None:
            unresolved.append({"abbrev": row.abbrev, "path": row.path, "line": row.line_number,
                               "text": raw_lines.get(row.line_number, "")})
        else:
            resolved[row.line_number] = file
            via_child += child

    items = scan_comments(text, table)
    in_comment = {n for i in items for n in range(i.line, i.last_line + 1)}
    for line in table.unparsed:
        if line.line_number in in_comment:
            continue  # the comment around it carries its bytes
        reason = line.reason if line.reason == parse_plans.OUTSIDE_REGION_REASON else f"unparsed-row ({line.reason})"
        items.append(Item(line.line_number, KIND_TABLE_LINE, line.text.rstrip("\r"), False, reason=reason))
    items += [Item(s.line_number, KIND_PROSE, s.text.rstrip("\r"), True, reason="prose-inside-table")
              for s in table.skipped if s.kind == "prose"]
    for row in table.rows:
        text_after = narrative(row.status_raw, row.status_token)
        if text_after:
            items.append(Item(row.line_number, KIND_NARRATIVE, text_after, True, row=row))
    items.sort(key=lambda item: item.line)

    rows_by_line = sorted(table.rows, key=lambda r: r.line_number)
    for item in items:
        if item.reason is not None:
            continue
        if item.kind == KIND_NARRATIVE:
            row = item.row
        elif item.in_region:
            row = next((r for r in reversed(rows_by_line) if r.line_number < item.line), None)
        else:
            item.reason = parse_plans.OUTSIDE_REGION_REASON
            continue
        if row is None:
            item.reason = "no-preceding-row"
        elif row.line_number not in resolved:
            item.reason = "unresolvable-master-plan"
        else:
            item.dest, item.basis_line = resolved[row.line_number], row.line_number
    for item in items:
        if item.unclosed:  # an opener left open would hide whatever is appended after it, so it never moves
            item.dest, item.basis_line = None, None
            item.reason = f"{item.reason or 'unclosed-opener'} (opener never closed; treated as a one-line note)"

    groups: dict = {}  # one group per Master Plan file, its items in index order
    for item in items:
        if item.dest is not None:
            groups.setdefault(_plan_key(item.dest), (item.dest, []))[1].append(item)
    appends = []
    for dest, group in groups.values():
        append = _plan_append(dest, group, index_path, date, refusals)
        if append:
            appends.append(append)

    changes, diffs = [], {"created": 0, "last_updated": 0, "name": 0}
    render = gen.render_plans_index(config)
    by_file = {_plan_key(plans_dir / r.file): r for r in render.rows}
    for row in table.rows:
        file = resolved.get(row.line_number)
        if file is None:
            continue
        try:
            fields = parse_plans.read_master_plan_fields(file)
        except (OSError, UnicodeDecodeError):
            continue
        if row.status_token != fields.status_token:
            changes.append({"abbrev": row.abbrev, "path": row.path, "line": row.line_number,
                            "before": row.status_token or row.status_raw, "after": fields.status_token or "-",
                            "raw": row.status_raw})
        rendered = by_file.get(_plan_key(file))
        if rendered is not None:
            diffs["created"] += row.created != rendered.created
            diffs["last_updated"] += row.last_updated != rendered.last_updated
            diffs["name"] += row.name != rendered.name
    mapped = {_plan_key(f) for f in resolved.values()}
    if render.tokens > gen.HUB_TOKEN_BUDGET:
        refusals.append(f"the regenerated plans index would measure {render.num_bytes} bytes ({render.tokens} "
                        f"tokens), over the {gen.HUB_TOKEN_BUDGET}-token budget; the index is one file, so "
                        "shorten the Master Plan set or shard the index before migrating")
    lines = classify_lines(text, table, items)
    index_bytes = text.encode("utf-8")
    plan = {
        "config": config, "plans_dir": plans_dir, "index_path": index_path, "text": text, "shape": shape,
        "detail": detail, "date": date, "table": table, "items": items, "appends": appends,
        "status_changes": changes, "unresolved_rows": unresolved, "diffs": diffs,
        "duplicates": [{"path": d.path, "lines": list(d.line_numbers)} for d in table.duplicates],
        "prefixed_rows": prefixed, "root_path_rows": via_child, "rows_mapped": len(resolved),
        "rows_post": len(render.rows),
        "rows_added": sum(1 for r in render.rows if _plan_key(plans_dir / r.file) not in mapped),
        "render": render, "refusals": refusals, "index_bytes": len(index_bytes), "lines": lines,
        "uncarried": lines["listed"], "index_sha256": hashlib.sha256(index_bytes).hexdigest(), "backup_dir": None,
    }
    gap = accounting(plan)["unaccounted"]
    if gap:
        refusals.append(f"the migrator cannot account for {gap} byte(s) of {index_path.name} (a line falls in no "
                        "category, or in two), so it moves nothing; this is a migrator defect, not an index defect: "
                        "run /planwise feedback with the --report output attached, and keep the index as it is")
    return plan


def plan_migration(config: dict, index_path: Path, text: str, migration_date: str | None = None) -> dict:
    """Plan a legacy index's migration in memory. Nothing is written. Raises `Refusal` naming each refusal and
    the fix that closes it."""
    shape, detail = classify_shape(text)
    if shape != "legacy":
        raise Refusal(f"the index shape is {shape}, not legacy: {detail}",
                      "run the migration only on a hand-authored plans index; this index needs no migration")
    plan = _analyze(config, index_path, text, migration_date)
    if plan["refusals"]:
        raise Refusal("\n".join(plan["refusals"]),
                      fix="close each refusal listed above as its text says, then re-run")
    return plan


def writable_paths(plan: dict) -> list:
    """Every path a write of this plan can create or change: each Master Plan it appends to, the index, and
    the ledger."""
    return [*(a["path"] for a in plan["appends"]), plan["index_path"], ledger_path_for(plan["plans_dir"])]


def plan_targets(plan: dict) -> list:
    """Every existing file a write rewrites, for a caller to back up first: the index, each Master Plan in
    the append set, and the ledger when an earlier migration left one (this run overwrites it)."""
    ledger = ledger_path_for(plan["plans_dir"])
    return [plan["index_path"], *(a["path"] for a in plan["appends"]), *([ledger] if ledger.is_file() else [])]


def verify_written(plan: dict) -> list:
    """Re-read every output and name each miss: a Master Plan that is not its planned text or does not keep
    its pre-image as a prefix, an appended note missing from its file, and any unaccounted source byte."""
    misses = []
    for append in plan["appends"]:
        try:
            now = read_text(append["path"])
        except OSError as exc:
            misses.append(f"{append['path']} could not be re-read after the write ({exc})")
            continue
        if not now.startswith(append["pre"]):
            misses.append(f"{Path(append['path']).name} no longer starts with its pre-write bytes")
        if now != append["text"]:
            misses.append(f"{Path(append['path']).name} does not match the staged text")
        for item in append["items"]:
            if _label(plan["index_path"], item) + append["newline"] + item.text not in now:
                misses.append(f"line {item.line} is missing from {Path(append['path']).name}")
    if accounting(plan)["unaccounted"]:
        misses.append(f"{accounting(plan)['unaccounted']} source byte(s) are unaccounted for")
    return misses


# --- Generator step, verdict ---


def _run_generator_steps(config: dict) -> dict:
    """The generator write (`--replace-legacy`), then its check, in process. Returns the exit codes and the
    figures the ledger records."""
    written = gen.write_plans_index(config, replace_legacy=True)
    check = gen.check_plans_index(config)
    return {
        "write_exit": written.exit_code, "written": written.written, "refusal": written.refusal,
        "check_exit": check.exit_code, "compared": check.compared,
        "check_findings": sorted({f["class"] for f in check.findings}),
        "anomalies": sorted({a["class"] for a in check.anomalies}),
        "warnings": [f"{w['class']}: {w['message']}" for w in check.warnings],
        "budget": gen._budget_fields(check.render.num_bytes, check.render.tokens, gen.HUB_TOKEN_BUDGET),
    }


def migration_date(ledger_file: Path) -> str:
    """The date to stamp into planned text. An unfinished earlier run's ledger pins the date it used, and a
    resume reuses it, so a resumed run on a later day plans byte-identical text and recognises its own
    earlier appends. Today's date otherwise."""
    try:
        summary = read_ledger_summary(read_text(ledger_file))
    except OSError:
        return _today()
    unfinished = (summary.get("Mode") == JOURNAL_MODE or summary.get("Generator verdict") not in ("clean", "accepted")
                  or summary.get("Verified") != "yes")
    pinned = summary.get("Migration date", "")
    return pinned if unfinished and _ISO_DATE_RE.match(pinned) else _today()


# --- Execute ---


def execute(plan: dict, ledger_file: Path, index_path: Path, config: dict, json_mode: bool) -> int:
    """Stage and replace the ledger (as a journal) and every Master Plan append, run the generator, re-read
    every output, then write the final ledger. The index is written last, by the generator."""
    outputs = [(a["path"], a["text"]) for a in plan["appends"]]
    try:
        staged = stage_all([(ledger_file, build_ledger(plan)), *outputs])
    except OSError as exc:
        return say(1, f"FAIL: staging failed ({exc}); nothing on disk changed.", json_mode, err=True)
    try:
        replace_all(staged)
    except ReplaceError as exc:
        done = ", ".join(Path(p).name for p in exc.done) or "none"
        return say(1, f"FAIL: replace stopped at {Path(exc.path).name} ({exc.cause}). Replaced: {done}. "
                      "Re-run --write to resume; every append is idempotent.", json_mode, err=True)
    generator_error = None
    try:
        exits = _run_generator_steps(config)
    except Exception as exc:  # noqa: BLE001 -- a generator crash must not crash this migrator
        exits, generator_error = None, repr(exc)
    misses = verify_written(plan)
    try:
        replace_all(stage_all([(ledger_file, build_ledger(plan, exits, misses, "write", generator_error))]))
    except (OSError, ReplaceError) as exc:
        return say(1, f"FAIL: migration written and verified={not misses}, but the ledger write failed ({exc}).",
                   json_mode, err=True)
    if json_mode:
        print(json.dumps(_summary(plan), indent=2))
    if misses or generator_error or generator_verdict(exits) == "failed":
        reasons = list(misses)
        if generator_error:
            reasons.append(f"generator step raised: {generator_error}; re-run --write to resume")
        elif generator_verdict(exits) == "failed":
            reasons.append(f"generator step failed: {exits}")
        return say(1, "FAIL: " + "; ".join(reasons), json_mode, err=True)
    return say(0, f"WROTE: migration complete; ledger at {ledger_file}. The index is generated and checked.",
               json_mode)


def _resume_or_clean(config: dict, index_path: Path, ledger_file: Path, args, js: bool) -> int:
    """The index is generated: finish the generator step when the ledger says an earlier run did not, else
    nothing to do."""
    clean = "CLEAN: the index is already generated; nothing to do."
    try:
        summary = read_ledger_summary(read_text(ledger_file))
    except OSError:
        return say(0, clean, js)
    if not summary or summary.get("Generator verdict") in ("clean", "accepted"):
        return say(0, clean, js)
    if not args.write:
        return say(1, "DRY-RUN: an earlier run's generator step did not finish; --write resumes it.", js)
    try:
        exits = _run_generator_steps(config)
    except Exception as exc:  # noqa: BLE001 -- a generator crash must not crash this migrator
        return say(1, f"FAIL: generator step raised: {exc!r}; re-run --write to resume.", js, err=True)
    verdict = generator_verdict(exits)
    if verdict == "failed":
        return say(1, f"FAIL: generator step still failing: {exits}", js, err=True)
    try:
        _record_resumed_verdict(ledger_file, verdict)
    except (OSError, ReplaceError) as exc:
        return say(1, f"FAIL: the index is generated and checked, but the ledger update failed ({exc}).",
                   js, err=True)
    return say(0, "WROTE: resumed at the generator step; the index is generated and checked.", js)


def _record_resumed_verdict(ledger_file: Path, verdict: str) -> None:
    """Rewrite the ledger's `Generator verdict` for a resumed generator step, and note the resume date. The
    `Migration date` line is kept, so the ledger still names the run that planned the appends."""
    text = read_text(ledger_file)
    nl = newline_of(text)
    line = f"- Generator verdict: {verdict}{nl}- Generator step resumed: {_today()}"
    replace_all(stage_all([(ledger_file, _VERDICT_LINE_RE.sub(lambda _m: line, text, count=1))]))


# --- Read-only report ---


def _summary(plan: dict) -> dict:
    """The report fields a plan yields, in the order `--report --json` prints them."""
    items, plans_dir = plan["items"], plan["plans_dir"]
    return {
        "shape": plan["shape"], "detail": plan["detail"], "index": str(plan["index_path"]),
        "rows": len(plan["table"].rows), "comments": sum(i.kind == KIND_COMMENT for i in items),
        "narrative_cells": sum(i.kind == KIND_NARRATIVE for i in items),
        "attributable": sum(i.dest is not None for i in items), "unattributed": sum(i.dest is None for i in items),
        "uncarried_lines": len(plan["uncarried"]),
        "root_path_rows": plan["root_path_rows"], "prefixed_rows": plan["prefixed_rows"],
        "status_changes": len(plan["status_changes"]),
        "append_targets": [Path(a["path"]).relative_to(plans_dir).as_posix() for a in plan["appends"]],
        "ready": not plan["refusals"], "would_refuse": list(plan["refusals"]),
    }


def build_report(config: dict, index_path: Path) -> dict:
    """The read-only readiness report. `--report` never writes and always exits 0."""
    text = read_text(index_path)
    shape, detail = classify_shape(text)
    if shape != "legacy":
        return {"shape": shape, "detail": detail, "index": str(index_path), "rows": 0, "comments": 0,
                "narrative_cells": 0, "attributable": 0, "unattributed": 0, "uncarried_lines": 0, "root_path_rows": 0,
                "prefixed_rows": 0, "status_changes": 0, "append_targets": [], "ready": False, "would_refuse": [],
                "questions": []}
    report = _summary(_analyze(config, index_path, text, migration_date(ledger_path_for(config["_plans_dir"]))))
    report["questions"] = []  # a plans refusal is a plain string, so it asks nothing
    return report


def _safe_report(config: dict, index_path: Path) -> dict:
    """`build_report`, except that no input can make it raise: an exception becomes an `error` field."""
    try:
        return build_report(config, index_path)
    except Exception as exc:  # noqa: BLE001 -- --report never raises, whatever the input
        try:
            shape = classify_shape(read_text(index_path))[0]
        except Exception:  # noqa: BLE001
            shape = "unknown"
        return {"shape": shape, "index": str(index_path), "error": repr(exc)}


def format_report(plan: dict) -> str:
    s = _summary(plan)
    rows = f"  rows: PRE {s['rows']}, mapped {plan['rows_mapped']}, POST {plan['rows_post']}, added {plan['rows_added']}"
    notes = (f"  notes: {s['comments']} comment(s), {s['narrative_cells']} Status-cell narrative(s); "
             f"{s['attributable']} attributable, {s['unattributed']} unattributed")
    lines = [f"Plans index migration plan ({plan['detail']}):", rows, notes,
             f"  uncarried index lines (listed verbatim in the ledger): {s['uncarried_lines']}",
             f"  status changes (the Master Plan wins): {s['status_changes']}"]
    lines += [f"  appended to: {target}" for target in s["append_targets"]]
    lines += [f"  unresolved row at line {r['line']}: {r['text']}" for r in plan["unresolved_rows"]]
    lines += [f"  would refuse: {reason}" for reason in s["would_refuse"]]
    return "\n".join(lines)


# --- CLI ---


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="migrate_plans_index.py", description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--config", type=Path, default=None, help="Path to config.yaml; overrides default search.")
    p.add_argument("--dry-run", action="store_true", help="Report the plan; write nothing (default behavior).")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Perform the migration.")
    mode.add_argument("--report", action="store_true",
                      help="Print a read-only JSON shape and readiness report; never writes; exit 0.")
    p.add_argument("--json", action="store_true", help="Emit the plan, ledger figures or report as JSON.")
    p.add_argument("--force", action="store_true", help="Proceed when a Master Plan in the append set is dirty.")
    p.add_argument("--allow-untracked-tree", action="store_true", help="Proceed when git cannot vouch for the tree.")
    return p


def _tree_gate(config: dict, plan: dict, args) -> str | None:
    """A refusal message naming the flag that closes it, or None when the run may proceed. It gates a write
    only: a dry run lists the same message under `would_refuse`."""
    targets = plan_targets(plan)
    dirty, reason = git_state(config["_project_root"], targets)
    if dirty is None:
        if not args.allow_untracked_tree:
            return (f"cannot determine the working-tree state -- {reason}. Commit the plans tree to git first, "
                    "or pass --allow-untracked-tree.")
        if args.write:
            say(0, f"WARNING: proceeding without a git safety net -- {reason}.", args.json, err=True)
        return None
    hot = sorted(str(a["path"]) for a in plan["appends"] if Path(a["path"]).resolve() in dirty)
    if hot and not args.force:
        return (f"{len(hot)} Master Plan(s) the migration appends to have uncommitted changes "
                f"(e.g. {', '.join(hot[:3])}); commit or stash them, or pass --force.")
    return None


def _write(config: dict, plan: dict, ledger_file: Path, args) -> int:
    """Back up, log, then execute. A standalone run never restores: a failed write is resumed by re-running."""
    project_root, planwise_root = Path(config["_project_root"]), Path(config["_planwise_root"])
    try:  # the DISPOSITIONS log joins project_root and planwise_root, so the latter must be relative to it
        relative_root = planwise_root.relative_to(project_root).as_posix()
    except ValueError:
        relative_root = str(planwise_root)
    cfg = SimpleNamespace(project_root=project_root, planwise_root=relative_root)
    backup_dir = planwise_root / "upgrade-backups" / f"{CLI_PAIR}-to-{plan['date']}" / "plans"
    try:
        backups = backup_targets(plan_targets(plan), plan["plans_dir"], backup_dir)
    except BackupFailed as exc:
        return say(1, f"FAIL: {exc}; no write was attempted.", args.json, err=True)
    log_backups(cfg, CLI_PAIR, plan["date"], backups, plan["plans_dir"], backup_dir)
    plan["backup_dir"] = backup_dir
    return execute(plan, ledger_file, plan["index_path"], config, args.json)


def run(config: dict, args) -> int:
    """Run one migration, or `--report`, for an already-loaded `config` and parsed `args`."""
    js = args.json
    plans_dir, index_path = config.get("_plans_dir"), config.get("_plans_index")
    if plans_dir is None or index_path is None:
        return say(2, "REFUSED: config.yaml declares no plans directory.", js, err=True)
    if not Path(index_path).exists():
        return say(2, f"REFUSED: index not found at {index_path}", js, err=True)
    if getattr(args, "report", False):
        print(json.dumps(_safe_report(config, index_path), indent=2))
        return 0
    text = read_text(index_path)
    shape, detail = classify_shape(text)
    if shape == "unrecognized":
        return say(2, f"REFUSED: unrecognised index shape -- {detail}. Inspect it with --report.", js, err=True)
    if shape == "absent":
        return say(0, "CLEAN: the index is blank; `generate_plans_index.py --write` creates it.", js)
    ledger_file = ledger_path_for(plans_dir)
    if shape == "generated":
        return _resume_or_clean(config, index_path, ledger_file, args, js)
    try:
        plan = plan_migration(config, index_path, text, migration_date(ledger_file))
    except Refusal as exc:
        return say(2, f"REFUSED: {exc}", js, err=True)
    refusal = _tree_gate(config, plan, args)
    if not args.write:
        plan["refusals"] += [refusal] if refusal else []
        print(json.dumps(_summary(plan), indent=2) if js else format_report(plan))
        return say(1, "DRY-RUN: migration needed; no files written.", js)
    if refusal:
        return say(2, f"REFUSED: {refusal}", js, err=True)
    return _write(config, plan, ledger_file, args)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args()
    if args.dry_run and args.write:
        return say(2, "REFUSED: --dry-run and --write are mutually exclusive.", args.json, err=True)
    return run(load_config(Path(__file__)), args)


if __name__ == "__main__":
    sys.exit(main())
