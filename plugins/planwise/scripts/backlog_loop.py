#!/usr/bin/env python3
"""Run-state writer for `/planwise backlog` loop mode.

The loop triages one backlog item per session. This script owns the run file
that carries the loop across sessions: `{backlog_dir}/Backlog-Runs/{YYYYMMDD-HHMMSS}.json`,
one file per run, never overwritten. It is the only writer of that file. The
contract (questions, per-iteration steps, the marker line) lives in
`handlers/backlog-Part-2-LoopMode.md`.

Subcommands, each printing short human lines and then ONE final line that is a
single-line JSON object:

  --init     build the queue from the open backlog and write a new run file;
             with --dry-run, print the same report and write nothing
  --next     pop the next still-selectable item and make it `current`
  --mark     record a phase, or the closing outcome, for an item. A SKIPPED
             outcome restores the item's pre-loop status; with --decision it
             also writes one `### Q{n}.` block under `## Open Questions` in
             the item file (`backlog_questions.append_question`); a retry in
             the same run writes nothing. With
             --needs-plan it marks the item `needs_plan: true`. A COMPLETE
             outcome with --resolution-file appends the close record to the
             item file. --refined, alone, records the refine outcome;
             --check with --exit, alone, records one verify command's result
  --boundary print the marker line the hooks module watches for
  --end      close the run and print the cross-run summary
  --status   print one run's record, or list every run

Exit codes: 0 ok, 1 usage or config error, 2 run file missing or unparseable
(the file is never touched on this path), 3 ambiguous resume (`current` is in
phase `acting` or `verifying` with no outcome; nothing is written).

`Backlog-Runs/` holds `.json` only. Every backlog reader globs `*.md` at the
top level, so the folder is never read as an item.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Import shared helpers from the sibling scripts
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from backlog_questions import (
    QUESTION_APPENDED,
    QuestionError,
    append_question,
    check_question_target,
    validate_question_text,
)
from config_loader import load_config
from constants import HOLD_STATUSES, OPEN_STATUSES
from item_shape import _reads_true
from markdown_parser import normalize_id
from parse_backlog import (
    FilterCriteria,
    _enumerate_generated_files,
    _index_naming,
    _read_backlog_items,
    build_blocked_by_map,
    collect_archived_closed_ids,
    duplicate_row_ids,
    duplicate_row_ids_message,
    filter_items,
    parse_dependencies_table,
)
from reconcile_common import read_text_preserving_newlines
from scoped_rules import (
    RULE_SCOPES_KEY,
    VERDICT_PLACEMENT,
    fence_left_open,
    load_rule_scopes,
    loop_sections,
)
from score_backlog import (
    _read_hub_family_items,
    compute_item_shape,
    compute_route_signals,
    get_first_file_path,
    load_scored_items,
    read_item_frontmatter,
)
from update_backlog import (
    RESOLUTION_HEADING,
    ResolutionFileError,
    _find_items_by_id,
    append_resolution_section,
    read_resolution_file,
    set_frontmatter_key,
    sync_yaml_status,
)

MARKER_FORMAT = "BACKLOG LOOP: run={run} done={done} remaining={remaining} state={state}"

SCHEMA_VERSION = 1
RUNS_DIRNAME = "Backlog-Runs"
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_RUN_FILE = 2
EXIT_AMBIGUOUS = 3

PHASES = ("selected", "acting", "verifying")
OUTCOMES = ("COMPLETE", "NOT_STARTED", "SKIPPED")
EXCLUDED_REASON = "plans deferred in loop mode"
NO_LONGER_SELECTABLE = "no-longer-selectable"
NO_ELIGIBLE = "No eligible items for the loop."
DECISION_HEADING = "## Loop Decision Needed"
REFINE_OUTCOMES = ("REFINED", "QUESTIONS", "ALREADY_MET", "DECOMPOSE", "NEEDS_PLAN")
# An unrefined default-branch Route C item past the --refine-max cap.
NEEDS_REFINE_REASON = "needs refine"
NEEDS_PLAN_NOTE = "marked for a planning session"
NEEDS_PLAN_REASON = NEEDS_PLAN_NOTE
OPEN_QUESTIONS_REASON = "open questions unanswered"
OPEN_QUESTIONS_NOTE = "open-questions-unanswered"
# The item still carries a legacy `## Loop Decision Needed` section.
DECISION_PENDING_REASON = "decision pending"
DECISION_PENDING_HINT = "decision pending: run scripts/backlog_questions.py --fold, then --answer each question"
# The item's scoped-rule verdict is `placement`: a human decides where a file goes.
PLACEMENT_REASON = "placement"
USER_INPUT_NOTE = "USER INPUT NEEDED: see ## Open Questions in the item file"
ACTIONS = ("init", "next", "mark", "boundary", "end")


class LoopExit(Exception):
    """A command-level failure: the exit code, the message, extra JSON keys."""

    def __init__(self, code: int, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


# ---------------------------------------------------------------------------
# Output and time helpers
# ---------------------------------------------------------------------------


def emit(lines: list[str], payload: dict) -> None:
    """Print the human lines, then the one final single-line JSON object."""
    for line in lines:
        print(line)
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_id_now() -> str:
    """The run id for a run starting now: local time, `YYYYMMDD-HHMMSS`."""
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def allocate_run_path(runs_dir: Path) -> tuple[str, Path]:
    """Return `(run_id, path)` for a new run file that does not exist yet.

    A second run in the same second gets `-2`, a third `-3`, so no run file is
    ever overwritten. The name is claimed by creating an empty file
    exclusively, so two concurrent `--init` calls cannot take the same name.
    `save_run` then replaces the empty file with the run record.
    """
    base = run_id_now()
    run_id = base
    counter = 1
    while True:
        path = runs_dir / f"{run_id}.json"
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            counter += 1
            run_id = f"{base}-{counter}"
            continue
        return run_id, path


def state_text(path: Path) -> str:
    """The absolute run-file path with forward slashes on every platform."""
    return str(path.resolve()).replace("\\", "/")


# ---------------------------------------------------------------------------
# Run file I/O
# ---------------------------------------------------------------------------


def runs_dir_of(config: dict) -> Path:
    return config["_backlog_dir"] / RUNS_DIRNAME


def resolve_run_path(config: dict, run: str | None) -> Path:
    """A `--run` value is a file stem or an absolute path to the run file."""
    if not run:
        raise LoopExit(EXIT_USAGE, "--run is required for this subcommand")
    if os.path.isabs(run) or "/" in run or "\\" in run:
        return Path(run)
    name = run if run.endswith(".json") else f"{run}.json"
    return runs_dir_of(config) / name


def load_run(path: Path) -> dict:
    """Read and validate a run file. Any failure is exit 2, before any write."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise LoopExit(EXIT_RUN_FILE, f"run file missing or unreadable: {state_text(path)}")
    try:
        data = json.loads(text)
    except ValueError:
        raise LoopExit(EXIT_RUN_FILE, f"run file is not valid JSON: {state_text(path)}")
    valid = (
        isinstance(data, dict)
        and data.get("schema_version") == SCHEMA_VERSION
        and isinstance(data.get("queue"), list)
        and isinstance(data.get("items"), dict)
        and isinstance(data.get("history"), list)
        and isinstance(data.get("excluded"), list)
    )
    if not valid:
        raise LoopExit(EXIT_RUN_FILE, f"run file has an unexpected shape: {state_text(path)}")
    return data


def save_run(path: Path, data: dict) -> None:
    """Write atomically: `<path>.tmp` first, then `os.replace`."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp, path)


def add_history(run: dict, event: str, item_id: str | None, detail: str) -> None:
    run["history"].append({"at": now_iso(), "event": event, "id": item_id, "detail": detail})


def resolve_item_key(run: dict, raw_id: str) -> str:
    """The stored key of a popped item, matched on its normalized id."""
    target = normalize_id(raw_id)
    for key in run["items"]:
        if key == raw_id or normalize_id(key) == target:
            return key
    raise LoopExit(EXIT_USAGE, f"unknown item id: {raw_id}")


# ---------------------------------------------------------------------------
# Selection helpers shared by --init and --next
# ---------------------------------------------------------------------------


def hub_family_rows(config: dict) -> list[dict]:
    """The hub plus overflow leaves, read by `parse_backlog`'s own reader.

    Unlike the scored rows, these carry `blocks` from the 9-column row.
    """
    naming = _index_naming(config["_index_path"])
    rows: list[dict] = []
    for path in _enumerate_generated_files(config["_backlog_dir"], naming):
        rows.extend(_read_backlog_items(path))
    return rows


def refuse_repeated_row_ids(rows: list[dict]) -> None:
    """Refuse an index that repeats a row id, the way `parse_backlog.py` does.

    Call it before anything keys `rows` by id. A repeated id would otherwise
    queue twice and let the last copy's Blocks cell replace the first's.
    """
    duplicates = duplicate_row_ids(rows)
    if duplicates:
        raise LoopExit(EXIT_USAGE, duplicate_row_ids_message(duplicates))


def still_selectable(config: dict, rows_by_norm: dict, item_id: str) -> bool:
    """Re-read the item file now; True while it is open and not on hold."""
    row = rows_by_norm.get(normalize_id(item_id))
    if row is None:
        return False
    path = get_first_file_path(row, config["_backlog_dir"])
    if path is None:
        return False
    if not path.exists():
        return False
    # A file with no readable frontmatter says nothing about a status flip, so
    # the hub row's status stands.
    frontmatter = read_item_frontmatter(path)
    status = str(frontmatter.get("status") or row["status"]).strip().upper()
    return status in OPEN_STATUSES and status not in HOLD_STATUSES


def item_status_of(config: dict, rows_by_norm: dict, item_id: str) -> tuple[Path | None, str]:
    """The item file and its status now: frontmatter first, the hub row second."""
    row = rows_by_norm.get(normalize_id(item_id))
    if row is None:
        return None, ""
    path = get_first_file_path(row, config["_backlog_dir"])
    if path is None or not path.exists():
        return None, str(row["status"]).strip().upper()
    frontmatter = read_item_frontmatter(path)
    return path, str(frontmatter.get("status") or row["status"]).strip().upper()


def marked_needs_plan(frontmatter: dict) -> bool:
    """True when the item's frontmatter carries `needs_plan` true.

    The shared truthy reader decides, so `yes`, `on` and `y` read as true
    here exactly as they do in the route; a quoted value is unquoted first.
    """
    value = frontmatter.get("needs_plan")
    if isinstance(value, str):
        value = value.strip().strip("\"'")
    return _reads_true(value)


def score_of(scores: dict, item_id: str) -> int:
    breakdown = scores.get(item_id)
    return breakdown.total if breakdown is not None else 0


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def filed_during_run(run: dict, config: dict) -> list[dict]:
    """Hub rows whose id was not known at init: items filed during the run."""
    known = {normalize_id(i) for i in run.get("known_ids_at_init", [])}
    return [
        row for row in _read_hub_family_items(config["_index_path"], config["_backlog_dir"])
        if normalize_id(row["id"]) not in known
    ]


def summary_lines(run: dict, config: dict) -> list[str]:
    meta = run.get("queue_meta", {})
    order = list(meta)
    for key in run["items"]:
        if key not in meta:
            order.append(key)
    lines = [
        f"Loop summary for run {run.get('run_id')}",
        "| ID | Feature | Route | Outcome | Refine |",
        "|----|---------|-------|---------|--------|",
    ]
    for item_id in order:
        rec = run["items"].get(item_id)
        info = meta.get(item_id, {})
        feature = info.get("feature") or ""
        refine = ((rec or {}).get("refine") or {}).get("outcome") or "-"
        if rec is None:
            route, outcome = info.get("route_at_init") or "-", "NOT_REACHED"
        else:
            # An item marked for a planning session has no loop route, so its
            # null route shows instead of the route it was queued under.
            fallback = "-" if rec.get("needs_plan") else rec.get("route_at_init") or "-"
            route = rec.get("route") or fallback
            outcome = rec.get("outcome") or "OPEN"
        lines.append(f"| {item_id} | {feature} | {route} | {outcome} | {refine} |")
    skipped: dict[str, list[str]] = {}
    for item_id in order:
        rec = run["items"].get(item_id) or {}
        if rec.get("outcome") == "SKIPPED":
            skipped.setdefault(rec.get("note") or "no note", []).append(item_id)
    if skipped:
        lines.append("Skipped (by reason):")
        for note, ids in skipped.items():
            lines.append(f"  {note}:")
            lines.extend(f"    {item_id}" for item_id in ids)
    checked = [(key, rec["checks"]) for key, rec in run["items"].items() if rec.get("checks")]
    if checked:
        lines.append("Checks:")
        for key, checks in checked:
            failed = [check for check in checks if check["exit"] != 0]
            lines.append(f"  {key}: {len(checks) - len(failed)}/{len(checks)} passed")
            lines.extend(f"    exit {check['exit']}: {check['command']}" for check in failed)
    # One header per exclusion reason, in first-seen order. A run file from
    # before reasons were split carries the strong-signal reason on every entry.
    groups: dict[str, list[dict]] = {}
    for entry in run["excluded"]:
        groups.setdefault(entry.get("reason") or EXCLUDED_REASON, []).append(entry)
    for reason, entries in groups.items():
        lines.append(f"Excluded ({reason}):")
        for entry in entries:
            lines.append(f"  {entry['id']} route {entry['route'] or '-'}  {entry.get('feature') or ''}".rstrip())
    needs_plan = [key for key, rec in run["items"].items() if rec.get("needs_plan")]
    if needs_plan:
        lines.append("Marked for a planning session:")
        lines.extend(f"  {key}" for key in needs_plan)
    unattended = [key for key, rec in run["items"].items() if rec.get("unattended_close")]
    if unattended:
        lines.append(f"Closed unattended (criteria already met; see {RESOLUTION_HEADING}):")
        lines.extend(f"  {key}" for key in unattended)
    refined: dict[str, list[str]] = {}
    for key, rec in run["items"].items():
        if rec.get("refine"):
            refined.setdefault(rec["refine"]["outcome"], []).append(key)
    if refined:
        lines.append("Refine outcomes:")
        lines.extend(
            f"  {outcome}: {', '.join(refined[outcome])}" for outcome in REFINE_OUTCOMES if outcome in refined
        )
    if refined.get("QUESTIONS"):
        lines.append("Open questions written (answer in each item's ## Open Questions):")
        lines.extend(f"  {key}" for key in refined["QUESTIONS"])
    needs_input = [key for key, rec in run["items"].items() if rec.get("user_input_needed")]
    if needs_input:
        lines.append("User input needed (see the ### Q block under ## Open Questions in each item file):")
        lines.extend(f"  {key}" for key in needs_input)
    lessons = [(key, rec["lessons"]) for key, rec in run["items"].items() if rec.get("lessons")]
    if lessons:
        lines.append("Lessons filed during this run:")
        lines.extend(f"  {key}: {', '.join(ids)}" for key, ids in lessons)
    filed = filed_during_run(run, config)
    if filed:
        lines.append("Filed during this run (not in the queue):")
        for row in filed:
            lines.append(f"  {row['id']}  {row['feature']}")
    return lines


def apply_end(run: dict) -> None:
    run["ended"] = now_iso()
    closed = sum(1 for rec in run["items"].values() if rec.get("outcome"))
    add_history(run, "end", None, f"closed={closed} queued_at_end={len(run['queue'])}")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_init(args, config: dict) -> int:
    if args.mode is None:
        raise LoopExit(EXIT_USAGE, "--init requires --mode all|specific|n")
    if args.mode == "n" and (args.n is None or args.n < 1):
        raise LoopExit(EXIT_USAGE, "--mode n requires --n with a number of 1 or more")
    if args.mode == "specific" and not (args.items or "").strip():
        raise LoopExit(EXIT_USAGE, "--mode specific requires --items")
    if args.refine_max < 0:
        raise LoopExit(EXIT_USAGE, "--refine-max takes a number of 0 or more")

    # Refuse a repeated row id before the rows are scored or keyed by id, and
    # before any run file is written.
    hub_rows = hub_family_rows(config)
    refuse_repeated_row_ids(hub_rows)

    items, frontmatters, scores, _open_ids = load_scored_items(config)
    if not items:
        raise LoopExit(EXIT_USAGE, "No items found in backlog index.")
    refuse_repeated_row_ids(items)

    # The scored rows carry no `blocks`; join it from parse_backlog's own reader.
    blocks_by_norm = {normalize_id(row["id"]): row.get("blocks", []) for row in hub_rows}
    for item in items:
        item["blocks"] = list(blocks_by_norm.get(normalize_id(item["id"]), []))
    try:
        index_text = config["_index_path"].read_text(encoding="utf-8")
    except OSError:
        index_text = ""
    dependencies = parse_dependencies_table(index_text)
    archived_closed_ids = collect_archived_closed_ids(config) if dependencies else frozenset()
    blocked_by = build_blocked_by_map(dependencies, items, archived_closed_ids)

    criteria = FilterCriteria(
        status=args.status or None, priority=args.priority, abbrev=args.abbrev
    )
    selectable, held = filter_items(items, criteria, blocked_by)

    def by_score(pair: tuple) -> tuple:
        return (-score_of(scores, pair[0]["id"]), pair[0]["id"])

    # Load the rule scopes once for the whole run; every item's route reads them.
    config = {**config, RULE_SCOPES_KEY: load_rule_scopes(config["_project_root"])}

    # First pass, in index order: the reasons that hold whatever the cap.
    verdicts: list[tuple[dict, dict | None, str | None]] = []
    for item in selectable:
        frontmatter = frontmatters.get(item["id"], {})
        if marked_needs_plan(frontmatter):
            # An item marked for a planning session is never queued, so the
            # loop does not pick it up again on every run. No route is computed.
            verdicts.append((item, None, NEEDS_PLAN_REASON))
            continue
        # Read-only pre-flight, in this order: a legacy decision section still
        # waiting for an answer, then a placement verdict. Neither is written.
        if loop_sections(frontmatter.get("_body") or ""):
            verdicts.append((item, None, DECISION_PENDING_REASON))
            continue
        signals = compute_route_signals(item, frontmatter, config)
        shape = signals["shape"]
        if (signals["scoped_rules"] or {}).get("verdict") == VERDICT_PLACEMENT:
            reason = PLACEMENT_REASON
        elif shape["open_questions"] == "unanswered":
            reason = OPEN_QUESTIONS_REASON
        elif signals["route"] == "C" and shape["shape_ok"]:
            # A refined item that fails the shape gate is refined again below.
            reason = EXCLUDED_REASON
        else:
            reason = None
        verdicts.append((item, signals, reason))

    # Refining is opt-in: --mode specific refines every named unrefined item,
    # otherwise the --refine-max highest-scored unrefined items are refined.
    # A refined item whose shape gate fails counts as unrefined here.
    unrefined = sorted(
        ((item, signals) for item, signals, reason in verdicts
         if reason is None and not signals["shape"]["shape_ok"]),
        key=by_score,
    )
    if args.mode == "specific":
        named = {normalize_id(raw.strip()) for raw in args.items.split(",") if raw.strip()}
        refine_ids = {item["id"] for item, _signals in unrefined if normalize_id(item["id"]) in named}
    else:
        refine_ids = {item["id"] for item, _signals in unrefined[: args.refine_max]}

    eligible: list[tuple[dict, dict, str]] = []
    excluded: list[dict] = []
    for item, signals, reason in verdicts:
        if reason is None:
            if item["id"] in refine_ids:
                eligible.append((item, signals, "refine"))
                continue
            if signals["route"] in ("A", "B"):
                eligible.append((item, signals, "run"))
                continue
            # Past the cap, an unrefined Route C item keeps its old exclusion:
            # a strong scope signal defers it to a planning session, and the
            # conservative default branch means it needs refining first.
            reason = EXCLUDED_REASON if signals["large_scope"] else NEEDS_REFINE_REASON
        excluded.append({
            "id": item["id"],
            "route": signals["route"] if signals else None,
            "large_scope": bool(signals and signals["large_scope"]),
            "reason": reason,
            "feature": item["feature"],
            "refined": bool(signals and signals["shape"]["refined"]),
        })
    eligible.sort(key=by_score)

    warnings: list[str] = []
    if args.mode == "specific":
        by_norm = {normalize_id(pair[0]["id"]): pair for pair in eligible}
        excluded_reason = {normalize_id(e["id"]): e["reason"] for e in excluded}
        held_norm = {normalize_id(h["id"]) for h in held}
        known_norm = {normalize_id(i["id"]) for i in items}
        queue_pairs: list[tuple[dict, dict]] = []
        seen: set[str] = set()
        for raw in args.items.split(","):
            raw = raw.strip()
            key = normalize_id(raw)
            if not raw or key in seen:
                continue
            seen.add(key)
            if key in by_norm:
                queue_pairs.append(by_norm[key])
                continue
            if key in excluded_reason:
                # A named unrefined item is always refined, so only a reason
                # that holds whatever the cap can drop it here.
                if excluded_reason[key] in (
                    NEEDS_PLAN_REASON, DECISION_PENDING_REASON, PLACEMENT_REASON, OPEN_QUESTIONS_REASON
                ):
                    why = excluded_reason[key]
                else:
                    why = "route C is deferred in loop mode"
            elif key in held_norm:
                why = "blocked or on hold"
            elif key in known_norm:
                why = "filtered out or not open"
            else:
                why = "not in the backlog index"
            warnings.append(f"warning: item {raw} dropped: {why}")
        if any(line.endswith(f": {DECISION_PENDING_REASON}") for line in warnings):
            warnings.append(DECISION_PENDING_HINT)
    else:
        queue_pairs = list(eligible)
        if args.mode == "n":
            queue_pairs = queue_pairs[: args.n]
    # In --mode specific the hint rides in the warnings; otherwise it follows the report.
    pending_hint = (
        args.mode != "specific" and any(entry["reason"] == DECISION_PENDING_REASON for entry in excluded)
    )

    queue = [pair[0]["id"] for pair in queue_pairs]
    queue_meta = {
        pair[0]["id"]: {
            "route_at_init": pair[1]["route"],
            "score": score_of(scores, pair[0]["id"]),
            "feature": pair[0]["feature"],
            "refined_at_init": pair[1]["shape"]["refined"],
            "disposition_at_init": pair[2],
        }
        for pair in queue_pairs
    }
    report = ["Queue:"]
    for position, item_id in enumerate(queue, start=1):
        info = queue_meta[item_id]
        report.append(
            f"  {position}. {item_id}  score {info['score']}  route {info['route_at_init']}  "
            f"{info['disposition_at_init']}  {info['feature']}"
        )
    if excluded:
        report.append("Excluded:")
        for entry in excluded:
            scope = " (large scope)" if entry["large_scope"] else ""
            report.append(f"  {entry['id']}  route {entry['route'] or '-'}  {entry['reason']}{scope}")
    if pending_hint:
        report.append(DECISION_PENDING_HINT)
    report.extend(warnings)
    result = {
        "queue": [
            {
                "id": i,
                "score": queue_meta[i]["score"],
                "route_at_init": queue_meta[i]["route_at_init"],
                "disposition": queue_meta[i]["disposition_at_init"],
            }
            for i in queue
        ],
        "excluded": excluded,
        "warnings": warnings,
    }
    counts = f"mode={args.mode} queue={len(queue)} excluded={len(excluded)}"
    if not queue:
        if not args.dry_run:
            raise LoopExit(EXIT_USAGE, NO_ELIGIBLE, warnings=warnings)
        # A dry run still shows why nothing queued, then exits as the real run would.
        emit(
            [f"Loop dry run: {counts} (no run file written)", *report, NO_ELIGIBLE],
            {"dry_run": True, "error": NO_ELIGIBLE, **result},
        )
        return EXIT_USAGE
    if args.dry_run:
        # The guard sits before the runs directory and the run file are made.
        emit([f"Loop dry run: {counts} (no run file written)", *report], {"dry_run": True, **result})
        return EXIT_OK

    created = now_iso()
    runs_dir = runs_dir_of(config)
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id, path = allocate_run_path(runs_dir)
    run = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created": created,
        "ended": None,
        "mode": args.mode,
        "n": args.n if args.mode == "n" else None,
        "filters": {
            "priority": args.priority or None,
            "abbrev": args.abbrev or None,
            "status": args.status or None,
        },
        "no_check": bool(args.no_check),
        "refine_max": args.refine_max,
        "excluded": excluded,
        "queue": queue,
        "queue_meta": queue_meta,
        "known_ids_at_init": [item["id"] for item in items],
        "current": None,
        "items": {},
        "history": [{
            "at": created,
            "event": "init",
            "id": None,
            "detail": f"mode={args.mode} n={run_n_text(args)} queue={len(queue)} excluded={len(excluded)}",
        }],
    }
    try:
        save_run(path, run)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    emit([f"Loop run {run_id}: {counts}", *report], {"run": run_id, "state": state_text(path), **result})
    return EXIT_OK


def refuse_if_ended(run: dict, payload: dict) -> None:
    """A run closed by `--end` accepts no more pops or marks (exit 1)."""
    if run.get("ended"):
        raise LoopExit(EXIT_USAGE, "run already ended", ended=run["ended"], **payload)


def run_n_text(args) -> str:
    return str(args.n) if args.mode == "n" else "-"


def cmd_next(args, config: dict) -> int:
    path = resolve_run_path(config, args.run)
    run = load_run(path)
    run_id = path.stem
    base_payload = {"run": run_id, "state": state_text(path)}

    refuse_if_ended(run, base_payload)

    # Any current item without an outcome is ambiguous, whatever its phase: a
    # session that died right after the pop (phase none or `selected`) left the
    # item IN_PROGRESS in the backlog, and popping on would drop it silently.
    current = run.get("current")
    if current:
        record = run["items"].get(current) or {}
        phase = record.get("phase")
        if record.get("outcome") is None:
            lines = [f"HALT: item {current} has no outcome (phase {phase or 'none'}). Nothing was written."]
            emit(lines, {"halt": True, "item": current, "phase": phase, **base_payload})
            return EXIT_AMBIGUOUS

    rows_by_norm: dict | None = None
    skipped: list[str] = []
    skip_notes: list[str] = []
    changed = False
    popped: str | None = None
    refined = False
    disposition = "run"

    def skip(item_id: str, record: dict, note: str) -> None:
        record.update(phase="closed", outcome="SKIPPED", started=None, closed=now_iso(), note=note)
        run["items"][item_id] = record
        # Keep `current` on a closed item, so `--boundary` can still end a
        # run whose queue was skipped to exhaustion.
        run["current"] = item_id
        add_history(run, "mark", item_id, f"outcome=SKIPPED {note}")
        skipped.append(item_id)
        skip_notes.append(f"Skipped {item_id}: {note}")

    while run["queue"]:
        item_id = run["queue"].pop(0)
        changed = True
        if rows_by_norm is None:
            rows = _read_hub_family_items(config["_index_path"], config["_backlog_dir"])
            refuse_repeated_row_ids(rows)
            rows_by_norm = {normalize_id(row["id"]): row for row in rows}
        info = run.get("queue_meta", {}).get(item_id, {})
        now = now_iso()
        record = {
            "route_at_init": info.get("route_at_init"),
            "score": info.get("score"),
            "phase": None,
            "outcome": None,
            "route": None,
            "started": now,
            "closed": None,
            "note": None,
        }
        if not still_selectable(config, rows_by_norm, item_id):
            skip(item_id, record, NO_LONGER_SELECTABLE)
            continue
        # The status before this loop touched the item, so a documented skip can
        # hand the item back the way it was found.
        item_path, status_now = item_status_of(config, rows_by_norm, item_id)
        # The refine state is read from the live file, not from init.
        shape = compute_item_shape(read_item_frontmatter(item_path) if item_path else {})
        if shape["open_questions"] == "unanswered":
            skip(item_id, record, OPEN_QUESTIONS_NOTE)
            continue
        refined = shape["refined"]
        # A refined item whose shape gate fails keeps its init disposition.
        disposition = "run" if shape["shape_ok"] else info.get("disposition_at_init") or "run"
        record["pre_status"] = status_now or None
        run["items"][item_id] = record
        run["current"] = item_id
        add_history(run, "next", item_id, f"remaining={len(run['queue'])}")
        popped = item_id
        break

    if changed:
        save_run(path, run)
    remaining = len(run["queue"])
    lines = list(skip_notes)
    if popped is None:
        lines.append("No items left in the queue.")
        emit(lines, {"next": None, "remaining": 0, **base_payload, "skipped": skipped})
        return EXIT_OK
    info = run.get("queue_meta", {}).get(popped, {})
    lines.append(
        f"Next: {popped}  {info.get('feature') or ''}  (route {info.get('route_at_init')}, "
        f"score {info.get('score')}, {disposition}); {remaining} remaining"
    )
    emit(lines, {
        "next": popped,
        "remaining": remaining,
        **base_payload,
        "route_at_init": info.get("route_at_init"),
        "score": info.get("score"),
        "refined": refined,
        "disposition": disposition,
        "pre_status": run["items"][popped].get("pre_status"),
        "skipped": skipped,
    })
    return EXIT_OK


def mark_lessons(args, config: dict) -> int:
    """Record the lesson ids Phase 8 filed for an item; merges, never duplicates.

    Written under its own history event, so it never changes which event
    `--boundary` reads as the newest mark for the item.
    """
    if args.phase or args.outcome or args.route or args.note or args.decision is not None:
        raise LoopExit(EXIT_USAGE, "--lessons stands alone: give no --phase, --outcome, --route, --note or --decision")
    ids = [part.strip() for part in args.lessons.split(",") if part.strip()]
    if not ids:
        raise LoopExit(EXIT_USAGE, "--lessons needs at least one lesson id")
    path = resolve_run_path(config, args.run)
    run = load_run(path)
    refuse_if_ended(run, {"run": path.stem, "state": state_text(path)})
    key = resolve_item_key(run, args.id)
    record = run["items"][key]
    merged = list(record.get("lessons") or [])
    merged.extend(lesson for lesson in ids if lesson not in merged)
    record["lessons"] = merged
    add_history(run, "lessons", key, ",".join(ids))
    save_run(path, run)
    emit([f"Recorded lessons for {key}: {', '.join(merged)}"], {
        "run": path.stem,
        "id": key,
        "lessons": merged,
        "state": state_text(path),
    })
    return EXIT_OK


def mark_check(args, config: dict) -> int:
    """Record one verify command's exit code for an item into its `checks` list.

    Stands alone like `--lessons`, so no other mark flag is silently dropped.
    Written under its own `check` history event, so it never changes which
    event `--boundary` reads as the newest mark for the item.
    """
    others = (args.phase, args.outcome, args.lessons, args.refined, args.decision, args.note,
              args.route, args.sub_items, args.resolution_file)
    if any(value is not None for value in others) or args.needs_plan:
        raise LoopExit(EXIT_USAGE, "--check stands alone: give no --phase, --outcome, --lessons, --refined, "
                                   "--decision, --note, --route, --needs-plan, --sub-items or --resolution-file")
    if args.exit is None:
        raise LoopExit(EXIT_USAGE, "--check needs --exit with the command's exit code")
    path = resolve_run_path(config, args.run)
    run = load_run(path)
    refuse_if_ended(run, {"run": path.stem, "state": state_text(path)})
    key = resolve_item_key(run, args.id)
    check = {"command": args.check, "exit": args.exit, "at": now_iso()}
    run["items"][key].setdefault("checks", []).append(check)
    add_history(run, "check", key, f"exit={args.exit}")
    save_run(path, run)
    emit([f"Recorded check for {key}: exit {args.exit}"], {
        "run": path.stem,
        "id": key,
        "check": check,
        "state": state_text(path),
    })
    return EXIT_OK


def mark_refined(args, config: dict) -> int:
    """Record the refine step's outcome for an item, with its sub-items for DECOMPOSE.

    Written under its own history event, so it never changes which event
    `--boundary` reads as the newest mark for the item.
    """
    if args.phase or args.outcome or args.route or args.note or args.decision is not None:
        raise LoopExit(EXIT_USAGE, "--refined stands alone: give no --phase, --outcome, --route, --note or --decision")
    sub_items = [part.strip() for part in (args.sub_items or "").split(",") if part.strip()]
    if args.refined == "DECOMPOSE" and not sub_items:
        raise LoopExit(EXIT_USAGE, "--refined DECOMPOSE needs --sub-items with at least one item id")
    if args.refined != "DECOMPOSE" and args.sub_items is not None:
        raise LoopExit(EXIT_USAGE, "--sub-items applies to --refined DECOMPOSE only")
    path = resolve_run_path(config, args.run)
    run = load_run(path)
    refuse_if_ended(run, {"run": path.stem, "state": state_text(path)})
    key = resolve_item_key(run, args.id)
    record = run["items"][key]
    record["refine"] = {"outcome": args.refined, "at": now_iso(), "sub_items": sub_items}
    detail = args.refined + (f" sub_items={','.join(sub_items)}" if sub_items else "")
    add_history(run, "refine", key, detail)
    save_run(path, run)
    emit([f"Recorded refine outcome for {key}: {detail}"], {
        "run": path.stem,
        "id": key,
        "refine": record["refine"],
        "state": state_text(path),
    })
    return EXIT_OK


def cmd_mark(args, config: dict) -> int:
    if not args.id:
        raise LoopExit(EXIT_USAGE, "--mark requires --id")
    if args.check is not None:
        return mark_check(args, config)
    if args.exit is not None:
        raise LoopExit(EXIT_USAGE, "--exit applies to --check only")
    # These guards run before the --refined and --lessons branches, so no
    # flag combined with either is ever silently dropped.
    if args.refined is not None and (
        args.lessons is not None or args.needs_plan or args.resolution_file is not None
    ):
        raise LoopExit(EXIT_USAGE, "--refined stands alone: give no --lessons, --needs-plan or --resolution-file")
    if args.sub_items is not None and args.refined is None:
        raise LoopExit(EXIT_USAGE, "--sub-items applies to --refined DECOMPOSE only")
    if args.lessons is not None and (args.needs_plan or args.resolution_file is not None):
        raise LoopExit(EXIT_USAGE, "--lessons stands alone: give no --needs-plan or --resolution-file")
    if args.decision is not None:
        try:
            validate_question_text(args.decision)
        except QuestionError as exc:
            raise LoopExit(EXIT_USAGE, str(exc))
    if args.needs_plan and args.outcome != "SKIPPED":
        raise LoopExit(EXIT_USAGE, "--needs-plan applies to --outcome SKIPPED only")
    if args.resolution_file is not None and args.outcome != "COMPLETE":
        raise LoopExit(EXIT_USAGE, "--resolution-file applies to --outcome COMPLETE only")
    resolution_text = None
    if args.resolution_file is not None:
        # The one shared reader; a missing, unreadable or empty file is a usage error.
        try:
            resolution_text = read_resolution_file(args.resolution_file)
        except ResolutionFileError as exc:
            raise LoopExit(EXIT_USAGE, str(exc))
    if args.refined is not None:
        return mark_refined(args, config)
    if args.lessons is not None:
        return mark_lessons(args, config)
    if bool(args.phase) == bool(args.outcome):
        raise LoopExit(EXIT_USAGE, "--mark requires exactly one of --phase, --outcome, --lessons or --refined")
    if args.phase and (args.route or args.note or args.decision):
        raise LoopExit(EXIT_USAGE, "--route, --note and --decision apply to --outcome only")
    if args.decision is not None and args.outcome != "SKIPPED":
        raise LoopExit(EXIT_USAGE, "--decision applies to --outcome SKIPPED only")
    path = resolve_run_path(config, args.run)
    run = load_run(path)
    refuse_if_ended(run, {"run": path.stem, "state": state_text(path)})
    key = resolve_item_key(run, args.id)
    record = run["items"][key]
    resolution_path: Path | None = None
    if resolution_text is not None:
        # Both directories: the handler flips the status first, so the item
        # file usually sits in Archive/ by now.
        matches = _find_items_by_id(
            config["_backlog_dir"], config["_archive_dir"], config["_index_path"], key
        )
        if len(matches) != 1:
            raise LoopExit(
                EXIT_USAGE,
                f"--resolution-file needs exactly one item file for {key}; found {len(matches)}",
            )
        resolution_path = matches[0][0]
    restored: str | None = None
    decision_outcome: str | None = None
    needs_plan_written = False
    resolution_written = False
    resolution_outcome: str | None = None
    if args.phase:
        record["phase"] = args.phase
        add_history(run, "mark", key, f"phase={args.phase}")
    else:
        if args.outcome == "SKIPPED":
            # A skip hands the item back the way the loop found it. A documented
            # skip also writes the question into the item file, so the next
            # interactive run finds it.
            skip_rows = _read_hub_family_items(config["_index_path"], config["_backlog_dir"])
            refuse_repeated_row_ids(skip_rows)
            rows_by_norm = {normalize_id(row["id"]): row for row in skip_rows}
            item_path, status_now = item_status_of(config, rows_by_norm, key)
            if args.decision is not None and item_path is None:
                raise LoopExit(EXIT_USAGE, f"--decision could not find the item file for {key}")
            if args.needs_plan and item_path is None:
                raise LoopExit(EXIT_USAGE, f"--needs-plan could not find the item file for {key}")
            if args.decision is not None and fence_left_open(
                read_text_preserving_newlines(item_path).replace("\r\n", "\n")
            ):
                # A block written after an unclosed fence would sit inside
                # it, where no reader sees it. Refuse before any write.
                raise LoopExit(
                    EXIT_USAGE,
                    f"--decision refused: the item file for {key} opens a fenced block it never "
                    "closes, so a new block would be hidden inside it. Close the fence first.",
                )
            if args.decision is not None:
                # Every file-level refusal of append_question, before any write.
                try:
                    check_question_target(item_path)
                except QuestionError as exc:
                    raise LoopExit(EXIT_USAGE, f"--decision refused: {exc}")
            if item_path is not None:
                pre_status = record.get("pre_status")
                loop_set_it = bool(pre_status) and pre_status != "IN_PROGRESS" and status_now == "IN_PROGRESS"
                if loop_set_it and sync_yaml_status(item_path, pre_status).outcome == "changed":
                    restored = pre_status
                if args.needs_plan:
                    outcome = set_frontmatter_key(item_path, "needs_plan", "true").outcome
                    if outcome in ("absent_file", "no_frontmatter"):
                        raise LoopExit(
                            EXIT_USAGE,
                            f"--needs-plan could not write needs_plan into the item file for {key} ({outcome})",
                        )
                    needs_plan_written = outcome in ("changed", "unchanged")
                if args.decision is not None:
                    try:
                        decision_outcome = append_question(item_path, path.stem, args.decision)
                    except QuestionError as exc:
                        raise LoopExit(EXIT_USAGE, f"--decision refused: {exc}")
            if args.decision is not None:
                record["user_input_needed"] = True
            if args.needs_plan:
                record["needs_plan"] = True
        if resolution_path is not None:
            resolution_outcome = append_resolution_section(resolution_path, resolution_text).outcome
            if resolution_outcome == "absent_file":
                raise LoopExit(EXIT_USAGE, f"--resolution-file could not find the item file for {key}")
            record["unattended_close"] = True
            resolution_written = resolution_outcome in ("appended", "closed_block")
            record["resolution_written"] = resolution_written
        now = now_iso()
        record["phase"] = "closed"
        record["outcome"] = args.outcome
        record["closed"] = now
        if args.route:
            record["route"] = args.route
        elif args.needs_plan:
            # An item re-assessed for a planning session has no loop route;
            # any route an earlier mark recorded is cleared.
            record["route"] = None
        else:
            # The route the item was queued under.
            record["route"] = record.get("route_at_init")
        if args.note:
            record["note"] = args.note
        elif args.decision is not None:
            record["note"] = USER_INPUT_NOTE
        elif args.needs_plan:
            record["note"] = NEEDS_PLAN_NOTE
        add_history(run, "mark", key, f"outcome={args.outcome}")
    save_run(path, run)
    what = f"phase={args.phase}" if args.phase else f"outcome={args.outcome}"
    lines = [f"Marked {key}: {what}"]
    if restored:
        lines.append(f"Restored {key} status to {restored}. Regenerate the backlog index.")
    # A same-run retry wrote nothing, so it reports false.
    decision_written = decision_outcome == QUESTION_APPENDED
    if decision_written:
        lines.append("Wrote a ### Q block under ## Open Questions in the item file.")
    if needs_plan_written:
        lines.append(f"Marked {key} needs_plan: true in the item file. Regenerate the backlog index.")
    if resolution_outcome is not None:
        lines.append({
            "appended": "Resolution: appended",
            "closed_block": "Resolution: section present, dated close block appended",
        }.get(resolution_outcome, "Resolution: section already present, left unchanged"))
    emit(lines, {
        "run": path.stem,
        "id": key,
        "phase": record["phase"],
        "outcome": record["outcome"],
        "restored_status": restored,
        "decision_written": decision_written,
        "needs_plan_written": needs_plan_written,
        "resolution_written": resolution_written,
        "state": state_text(path),
    })
    return EXIT_OK


def boundary_recorded(run: dict, item_id: str) -> bool:
    """True when the newest mark or boundary event for the item is a boundary."""
    for event in reversed(run["history"]):
        if event.get("id") == item_id and event.get("event") in ("mark", "boundary"):
            return event["event"] == "boundary"
    return False


def cmd_boundary(args, config: dict) -> int:
    path = resolve_run_path(config, args.run)
    run = load_run(path)
    current = run.get("current")
    record = run["items"].get(current) if current else None
    if not record or not record.get("outcome"):
        lines = ["Boundary refused: the current item carries no outcome. Nothing was written."]
        emit(lines, {"error": "current item has no outcome", "run": path.stem, "state": state_text(path)})
        return EXIT_AMBIGUOUS
    remaining = len(run["queue"])
    changed = False
    if remaining == 0 and not run.get("ended"):
        apply_end(run)
        changed = True
    if not boundary_recorded(run, current):
        add_history(run, "boundary", current, f"remaining={remaining}")
        changed = True
    if changed:
        save_run(path, run)
    marker = MARKER_FORMAT.format(
        run=path.stem, done=current, remaining=remaining, state=state_text(path)
    )
    lines = summary_lines(run, config) if remaining == 0 else []
    lines.append(marker)
    emit(lines, {
        "run": path.stem,
        "done": current,
        "remaining": remaining,
        "state": state_text(path),
        "ended": run.get("ended"),
        "marker": marker,
    })
    return EXIT_OK


def cmd_end(args, config: dict) -> int:
    path = resolve_run_path(config, args.run)
    run = load_run(path)
    already = bool(run.get("ended"))
    if not already:
        apply_end(run)
        save_run(path, run)
    emit(summary_lines(run, config), {
        "run": path.stem,
        "ended": run["ended"],
        "already_ended": already,
        "state": state_text(path),
    })
    return EXIT_OK


def run_overview(run: dict) -> dict:
    closed = sum(1 for rec in run["items"].values() if rec.get("outcome"))
    return {
        "run": run.get("run_id"),
        "mode": run.get("mode"),
        "queued": len(run["queue"]),
        "popped": len(run["items"]),
        "closed": closed,
        "ended": run.get("ended"),
    }


def cmd_status(args, config: dict) -> int:
    if args.run:
        path = resolve_run_path(config, args.run)
        run = load_run(path)
        overview = run_overview(run)
        head = (
            f"Run {path.stem}: mode={overview['mode']} queued={overview['queued']} "
            f"popped={overview['popped']} closed={overview['closed']} ended={overview['ended']}"
        )
        lines = [head, f"current: {run.get('current')}"]
        emit(lines, {"run": path.stem, "state": state_text(path), "record": run})
        return EXIT_OK
    runs_dir = runs_dir_of(config)
    overviews: list[dict] = []
    lines = []
    for path in sorted(runs_dir.glob("*.json")) if runs_dir.is_dir() else []:
        try:
            overview = run_overview(load_run(path))
        except LoopExit as exc:
            overview = {"run": path.stem, "error": exc.message}
            lines.append(f"{path.stem}: unreadable")
        else:
            lines.append(
                f"{path.stem}: mode={overview['mode']} queued={overview['queued']} "
                f"closed={overview['closed']} ended={overview['ended']}"
            )
        overviews.append(overview)
    if not overviews:
        lines.append("No loop runs.")
    emit(lines, {"runs": overviews})
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class LoopParser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; here 2 means a bad run file, so use 1."""

    def error(self, message):
        raise LoopExit(EXIT_USAGE, f"usage error: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = LoopParser(
        description="Run-state writer for /planwise backlog loop mode.", allow_abbrev=False
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml.")
    for name in ACTIONS:
        parser.add_argument(f"--{name}", action="store_true", help=f"The {name} subcommand.")
    parser.add_argument("--run", default=None, help="Run id (file stem) or absolute path to the run file.")
    parser.add_argument("--mode", choices=["all", "specific", "n"], default=None)
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--items", default=None, help="Comma-separated ids for --mode specific.")
    parser.add_argument("--priority", default=None)
    parser.add_argument("--abbrev", default=None)
    parser.add_argument(
        "--status", nargs="?", const="", default=None,
        help="Alone: show run status. With --init: a status filter.",
    )
    parser.add_argument("--no-check", action="store_true", dest="no_check")
    parser.add_argument("--id", default=None)
    parser.add_argument("--phase", choices=list(PHASES), default=None)
    parser.add_argument("--outcome", choices=list(OUTCOMES), default=None)
    parser.add_argument(
        "--route", choices=["A", "B"], default=None,
        help="With --mark --outcome: the route worked. Defaults to the item's route_at_init; "
             "with --needs-plan there is no default and the route stays null.",
    )
    parser.add_argument("--note", default=None)
    parser.add_argument(
        "--lessons", default=None,
        help="With --mark: comma-separated lesson ids Phase 8 filed for the item.",
    )
    parser.add_argument(
        "--decision", default=None,
        help="With --mark --outcome SKIPPED: the question, options and evidence to write "
             "into the item file as a ### Q block under ## Open Questions.",
    )
    parser.add_argument(
        "--needs-plan", action="store_true", dest="needs_plan",
        help="With --mark --outcome SKIPPED: write needs_plan: true into the item file "
             "and record the item for a planning session.",
    )
    parser.add_argument(
        "--resolution-file", type=Path, default=None, dest="resolution_file",
        help=f"With --mark --outcome COMPLETE: a file whose text is appended under {RESOLUTION_HEADING} "
             "in the item file; when the section exists, a dated '### Closed {date}' block is "
             "appended below it",
    )
    parser.add_argument(
        "--refine-max", type=int, default=0, dest="refine_max",
        help="With --init: refine at most N unrefined items, highest score first (default 0). "
             "--mode specific refines every named unrefined item.",
    )
    parser.add_argument(
        "--refined", choices=list(REFINE_OUTCOMES), default=None,
        help="With --mark, alone: record the refine step's outcome for the item.",
    )
    parser.add_argument(
        "--sub-items", default=None, dest="sub_items",
        help="With --mark --refined DECOMPOSE: comma-separated ids of the sub-items filed.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="With --init: print the queue and the exclusions; write no run file.",
    )
    parser.add_argument("--check", default=None, help="With --mark, alone: a verify command that ran.")
    parser.add_argument("--exit", type=int, default=None, help="With --mark --check: its exit code.")
    return parser


def _fix_stdout() -> None:
    encoding = getattr(sys.stdout, "encoding", None)
    if encoding and encoding.lower() != "utf-8" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _fix_stdout()
    try:
        args = build_parser().parse_args(argv)
        actions = [name for name in ACTIONS if getattr(args, name)]
        if args.status is not None and not args.init:
            if args.status != "":
                raise LoopExit(EXIT_USAGE, "--status takes a value only with --init")
            actions.append("status")
        if len(actions) != 1:
            raise LoopExit(
                EXIT_USAGE,
                "give exactly one of --init, --next, --mark, --boundary, --end, --status",
            )
        if args.dry_run and actions[0] != "init":
            raise LoopExit(EXIT_USAGE, "--dry-run applies to --init only")
        try:
            config = load_config(Path(__file__), config_path=args.config)
        except FileNotFoundError as exc:
            raise LoopExit(EXIT_USAGE, str(exc))
        handler = {
            "init": cmd_init, "next": cmd_next, "mark": cmd_mark,
            "boundary": cmd_boundary, "end": cmd_end, "status": cmd_status,
        }[actions[0]]
        return handler(args, config)
    except LoopExit as exc:
        emit([exc.message], {"error": exc.message, **exc.extra})
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
