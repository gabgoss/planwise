#!/usr/bin/env python3
"""The plans-index migration ledger: its writer, its summary reader and its byte accounting.

The ledger is markdown, so a person can read the notes it keeps under
`## Unattributed Index Notes` and the lines it lists under
`## Uncarried Index Lines`. `## Summary` is machine-read by the upgrade
routine, one `- Label: value` bullet per figure. The ledger is written twice
per run: first as a journal (`Mode: write-in-progress`, which pins the
migration date for a resume), then final (`Mode: write`).

Byte accounting covers every byte of the old index: table structure, seed
scaffold, layout, the items (appended, unattributed or already present) and
the uncarried lines. Each figure is measured on its own, so `Unaccounted` is
the index size minus their sum and is non-zero when a line has no owner or
two.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate_backlog_support import newline_of

JOURNAL_MODE = "write-in-progress"
_SUMMARY_RE = re.compile(r"^- ([^:\n]+): ?(.*?)\r?$", re.MULTILINE)
_SUMMARY_COUNTS = (
    ("Rows before (PRE)", "rows_pre"), ("Rows mapped to a Master Plan", "rows_mapped"),
    ("Rows after (POST)", "rows_post"), ("Rows added from the disk walk", "rows_added"),
    ("Appended items", "appended"), ("Master Plans touched", "master_plans"),
    ("Already-present items", "already_present"), ("Unattributed items", "unattributed"),
    ("Uncarried index lines", "uncarried_lines"),
    ("Status changes", "status_changes"), ("Unresolved rows", "unresolved_rows"),
    ("Duplicate Paths", "duplicates"), ("Created differences", "created_diffs"),
    ("Last Updated differences", "updated_diffs"), ("Name differences", "name_diffs"),
)


def accounting(plan: dict) -> dict:
    """Every byte of the old index by owner. The item figures are summed from the items, the others from the
    lines `classify_lines` gave no item."""
    items, lines = plan["items"], plan["lines"]
    acc = {"index": plan["index_bytes"], "structure": lines["structure"], "scaffold": lines["scaffold"],
           "layout": lines["layout"], "items": sum(i.nbytes for i in items),
           "appended": sum(i.nbytes for i in items if i.dest is not None and not i.present),
           "unattributed": sum(i.nbytes for i in items if i.dest is None),
           "already_present": sum(i.nbytes for i in items if i.dest is not None and i.present),
           "uncarried": lines["uncarried"]}
    owned = sum(acc[k] for k in ("structure", "scaffold", "layout", "appended", "unattributed", "already_present",
                                 "uncarried"))
    acc["unaccounted"] = acc["index"] - owned
    return acc


def generator_verdict(exits: dict | None) -> str:
    """`clean` when the write and the check both exit 0. `accepted` when the index was written and the check
    reports only tree anomalies (an unknown status, say) and no finding. `failed` otherwise."""
    exits = exits or {}
    if exits.get("write_exit") not in (0, 1) or not exits.get("written"):
        return "failed"
    if exits.get("check_exit") == 0:
        return "clean"
    if exits.get("check_exit") == 1 and not exits.get("check_findings") and exits.get("anomalies"):
        return "accepted"
    return "failed"


def _fence(text: str) -> str:
    return "````" if "```" in text else "```"


def _size(path: Path) -> int | str:
    try:
        return Path(path).stat().st_size
    except OSError:
        return "unreadable"


def _summary_lines(plan: dict, mode: str, verdict: str, misses: list | None) -> list:
    items, d = plan["items"], plan["diffs"]
    return [
        "## Summary", "",
        f"- Migration date: {plan['date']}", f"- Mode: {mode}", f"- Shape: {plan['detail']}",
        f"- Rows before (PRE): {len(plan['table'].rows)}", f"- Rows mapped to a Master Plan: {plan['rows_mapped']}",
        f"- Rows after (POST): {plan['rows_post']}", f"- Rows added from the disk walk: {plan['rows_added']}",
        f"- Appended items: {sum(1 for i in items if i.dest is not None and not i.present)}",
        f"- Master Plans touched: {len(plan['appends'])}",
        f"- Already-present items: {sum(1 for i in items if i.present)}",
        f"- Unattributed items: {sum(1 for i in items if i.dest is None)}",
        f"- Uncarried index lines: {len(plan['uncarried'])}",
        f"- Status changes: {len(plan['status_changes'])}", f"- Unresolved rows: {len(plan['unresolved_rows'])}",
        f"- Duplicate Paths: {len(plan['duplicates'])}", f"- Created differences: {d['created']}",
        f"- Last Updated differences: {d['last_updated']}", f"- Name differences: {d['name']}",
        f"- Generator verdict: {verdict}",
        f"- Verified: {'pending' if misses is None else ('yes' if not misses else 'no')}", "",
    ]


def build_ledger(plan: dict, exits: dict | None = None, misses: list | None = None, mode: str = JOURNAL_MODE,
                 generator_error: str | None = None) -> str:
    """The ledger text, in the index's own line ending. Item text is written as read, so a verbatim note
    stays byte-identical to its source."""
    nl = newline_of(plan["text"])
    plans_dir, items = plan["plans_dir"], plan["items"]
    verdict = "pending" if exits is None and generator_error is None else generator_verdict(exits)
    out = ["# Plans Migration Ledger", "", *_summary_lines(plan, mode, verdict, misses)]
    out += ["## Appended Index Notes", "",
            "| # | Source line | Kind | Bytes | Destination | Basis row line | Disposition |",
            "|--:|--:|---|--:|---|--:|---|"]
    for n, item in enumerate((i for i in items if i.dest is not None), 1):
        out.append(f"| {n} | {item.line} | {item.kind} | {item.nbytes} | "
                   f"{Path(item.dest).relative_to(plans_dir).as_posix()} | {item.basis_line} | "
                   f"{'already-present' if item.present else 'appended'} |")
    out += ["", "## Status Changes", "", "| Abbrev | Before | After | Row line | Path | Row cell |",
            "|---|---|---|--:|---|---|"]
    out += [f"| {c['abbrev']} | {c['before']} | {c['after']} | {c['line']} | {c['path']} | {c['raw']} |"
            for c in plan["status_changes"]]
    out += ["", "## Unattributed Index Notes", ""]
    for item in (i for i in items if i.dest is None):
        fence = _fence(item.text)
        out += [f"### Line {item.line}: {item.kind}, {item.nbytes} B, {item.reason}", "", fence, item.text, fence, ""]
    out += ["## Uncarried Index Lines", "",
            ("Non-blank lines of the old index that are no note, no table row and no seed scaffold. The generator "
             "does not re-render them, so they are kept here, verbatim."), ""]
    for number, text in plan["uncarried"]:
        fence = _fence(text)
        out += [f"### Line {number}: {len(text.encode('utf-8'))} B", "", fence, text, fence, ""]
    out += ["## Unresolved Rows", "", "Rows whose Master Plan could not be found. The generator drops them.", ""]
    for row in plan["unresolved_rows"]:
        out += [f"### Line {row['line']}", "", "```", row["text"], "```", ""]
    post = _size(plan["index_path"]) if mode != JOURNAL_MODE else "pending"
    out += ["## Backups", "", f"- Backup folder: {plan['backup_dir'] or 'none'}", "",
            "| Target | Pre bytes | Pre sha256 | Post bytes |", "|---|--:|---|--:|",
            f"| {Path(plan['index_path']).name} | {plan['index_bytes']} | {plan['index_sha256']} | {post} |"]
    out += [f"| {Path(a['path']).relative_to(plans_dir).as_posix()} | {a['pre_bytes']} | {a['pre_sha256']} | "
            f"{a['post_bytes']} |" for a in plan["appends"]]
    out += ["", "## Generator", ""]
    if generator_error:
        out.append(f"- Generator step raised: {generator_error}")
    for key in ("write_exit", "check_exit", "compared", "check_findings", "anomalies"):
        out.append(f"- {key}: {(exits or {}).get(key, 'pending')}")
    budget = (exits or {}).get("budget") or {}
    figures = f"{budget.get('bytes', '?')} / {budget.get('tokens', '?')} / {budget.get('budget', '?')}"
    out += [f"- page_cap_ratio: {budget.get('page_cap_ratio', 'pending')}", f"- bytes / tokens / budget: {figures}"]
    out += [f"- warning {w}" for w in (exits or {}).get("warnings", [])]
    acc = accounting(plan)
    out += ["", "## Byte Accounting", "", f"- Index bytes: {acc['index']}",
            f"- Table structure (header, separators, rows): {acc['structure']}",
            f"- Seed scaffold: {acc['scaffold']}", f"- Layout (blank lines, line endings): {acc['layout']}",
            f"- Source item bytes: {acc['items']}", f"- Appended: {acc['appended']}",
            f"- Unattributed: {acc['unattributed']}", f"- Already present: {acc['already_present']}",
            f"- Uncarried lines: {acc['uncarried']}", f"- Unaccounted: {acc['unaccounted']}"]
    out += [f"- Miss: {m}" for m in (misses or [])]
    return nl.join(out) + nl


def read_ledger_summary(text: str) -> dict:
    """The `## Summary` bullets of a ledger as `{label: value}`. Empty when the section is missing."""
    body = re.search(r"^## Summary\r?\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    return dict(_SUMMARY_RE.findall(body.group(1))) if body else {}


def ledger_counts(summary: dict) -> dict:
    """The integer counts of a ledger summary, keyed as the upgrade routine reports them."""
    counts = {key: int(summary[label]) for label, key in _SUMMARY_COUNTS if str(summary.get(label, "")).isdigit()}
    verdict = summary.get("Generator verdict", "")
    counts["generator_verdict"] = verdict
    counts["generator_check_clean"] = verdict in ("clean", "accepted")
    return counts
