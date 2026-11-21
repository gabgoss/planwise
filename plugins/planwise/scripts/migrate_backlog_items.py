"""Repair the shape of backlog item files during `/planwise upgrade`.

`migrate_backlog_items` runs after `migrate_backlog_if_legacy`, so the index is already generated.
It grades every open item with the doctor's shape detector (`backlog_item_shape`), then repairs the
drift classes that need no judgment:

- a legacy `## Loop Decision Needed` section is folded into `### Q` blocks (`backlog_questions.fold_item`)
- a missing `**Priority:**` or `**Domain:**` line is added from the frontmatter
- a missing `*Created: ...*` footer is added from `created:`
- a frontmatter key outside the item template moves into a bullet under `## Notes`. A `blocked_by`
  key moves too, and the report says it was not converted into `blocks:`, which runs the other way.

Everything else stays as written and is listed as an action: an over-cap title, a heading outside
the template, a missing core section, an invalid status, and a body line or footer that differs from
the frontmatter. The step never sets `refined` and never raises.

Order of work, so no write happens before its backup and no rewrite goes unchecked:

1. Plan every rewrite in memory. A file whose text would not change is not touched.
2. Capture the route of each file that will change (`score_backlog` signals).
3. Back up each target byte-exact under `upgrade-backups/{from}-to-{to}/backlog-items/`
   (`backlog_migration._backup`). A failed backup means no write is attempted.
4. Write each file atomically, then read it back and run the preservation diff: every non-blank line
   of the original must survive in the written file, except the frontmatter lines that moved into
   `## Notes` and the loop's own marker and callout lines in a folded section. One miss restores
   every file this run wrote and refuses.
5. Regenerate the index and check it, then capture each route again and print before and after.

A second run finds nothing to repair, writes nothing and backs up nothing.
"""
import dataclasses
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import backlog_item_shape as shape
    import backlog_migration as bm
    import backlog_questions as bq
    import config_loader
    import migrate_backlog_support as sup
    import score_backlog
    from frontmatter_parser import (
        FM_KEY_LINE_RE,
        parse_frontmatter_map,
        split_frontmatter_block,
    )
    from item_shape import _THEMATIC_BREAK_RE, fence_flags_any_indent
    from markdown_parser import normalize_id
    from reconcile_common import read_text_preserving_newlines as read_text
    from scoped_rules import TOP_HEADING_RE
except ImportError as exc:
    raise ImportError(
        f"migrate_backlog_items could not import a sibling module ({exc}); "
        "the scripts/ directory appears to be partially installed"
    ) from exc

ACTION = "backlog-items-repaired"
BACKUP_FOLDER = "backlog-items"
# The drift classes this step can repair. Every other class is reported and left as written.
MECHANICAL = ("legacy-decision", "priority-line", "domain-line", "footer", "key-nontemplate")
# The banner's name for each count a rewrite adds.
COUNT_LABELS = {"fold": "legacy sections folded", "lines": "Priority and Domain lines added",
                "footer": "footers added", "keys": "frontmatter keys moved into Notes"}
_BOM = "﻿"
_H1_RE = re.compile(r"^# \S")
_NOTES_RE = re.compile(r"^## Notes[ \t]*$")
_RELATED_RE = re.compile(r"^## Related[ \t]*$")


@dataclasses.dataclass
class ItemRepairReport(bm.BacklogMigrationReport):
    """Outcome of `migrate_backlog_items`. `state` is one of: absent, skipped, clean, migrated,
    refused, backup_failed, write_failed, error."""
    scanned: int = 0
    found: dict = dataclasses.field(default_factory=dict)  # drift class key -> ids, before the repair
    remaining: dict = dataclasses.field(default_factory=dict)  # drift class key -> ids, after it
    routes: list = dataclasses.field(default_factory=list)  # (id, route before, route after)
    notes: list = dataclasses.field(default_factory=list)  # one action line each


def migrate_backlog_items(cfg, from_version: str, to_version: str, answers: dict | None = None) -> ItemRepairReport:
    """Repair the project's open backlog item files. Never raises.

    `answers` is the parsed answers file. Both call sites pass it, and no key is read here."""
    report = ItemRepairReport(state="absent", index_path=None)
    try:
        _migrate(cfg, from_version, to_version, report)
    except Exception as exc:  # noqa: BLE001 -- the caller's upgrade must never fail on this step
        report.state, report.detail = "error", repr(exc)
    return report


def _find(lines: list, flags: list, pattern) -> int | None:
    """Index of the first unfenced line that matches `pattern`."""
    return next((i for i, line in enumerate(lines) if not flags[i] and pattern.match(line)), None)


def _footer_break(lines: list, flags: list) -> int | None:
    """Index of the thematic break that opens the footer: the last one with no level 1 or 2 heading after it."""
    for i in range(len(lines) - 1, -1, -1):
        if flags[i]:
            continue
        if TOP_HEADING_RE.match(lines[i]):
            return None
        if _THEMATIC_BREAK_RE.match(lines[i]):
            return i
    return None


def _fold(raw: bytes, ident: str, notes: list) -> tuple | None:
    """Fold the legacy sections of one item through `fold_item`, on a scratch copy.

    Returns `(folded text with LF line ends, reference text)` or None when the fold was refused.
    The reference is the original text with each section reduced to the question lines that must
    survive, so the preservation diff does not demand the loop's own marker and callout lines."""
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "item.md"
        copy.write_bytes(raw)
        result = bq.fold_item(copy)
        if result["status"] != "folded":
            notes.append(f"{ident}: the legacy section was left in place ({result.get('reason', result['status'])})")
            return None
        folded = copy.read_bytes().decode("utf-8").replace("\r\n", "\n")
    text = raw.decode("utf-8").replace("\r\n", "\n")
    for start, end, _bounded in reversed(bq.loop_sections(text, bq.LOOP_WRITTEN_HEADINGS)):
        _run, question = bq._legacy_parts(text[start:end])
        text = text[:start] + question + "\n" + text[end:]
    return folded, text


def _split_keys(fm_text: str, extras: set) -> tuple:
    """The frontmatter text without the lines of the keys in `extras`, and the removed lines."""
    kept, moved, current = [], [], None
    for line in fm_text.split("\n"):
        match = FM_KEY_LINE_RE.match(line)
        if match:
            current = match.group(1)
        if current in extras:
            if line.strip():
                moved.append(line.rstrip())
            continue
        kept.append(line)
    return "\n".join(kept), moved


def _add_notes(body: str, bullets: list) -> str:
    """Put the bullets under `## Notes`: in the section when it exists, else before `## Related`,
    else before the footer's thematic break, else at the end."""
    lines = body.split("\n")
    flags = fence_flags_any_indent(body)
    at = _find(lines, flags, _NOTES_RE)
    if at is not None:
        rest = lines[at + 1:]
        while rest and not rest[0].strip():
            rest.pop(0)
        return "\n".join([*lines[:at + 1], "", *bullets, "", *rest])
    at = _find(lines, flags, _RELATED_RE)
    if at is None:
        at = _footer_break(lines, flags)
    if at is None:
        return body.rstrip() + "\n\n" + "\n".join(["## Notes", "", *bullets]) + "\n"
    before = lines[:at]
    while before and not before[-1].strip():
        before.pop()
    return "\n".join([*before, "", "## Notes", "", *bullets, "", *lines[at:]])


def _add_lines(body: str, priority: str, domain: str) -> tuple:
    """Add the missing Priority and Domain lines. Returns `(body, names added)`."""
    found_p, found_d = shape._PRIORITY_RE.search(body), shape._DOMAIN_RE.search(body)
    want_p, want_d = found_p is None and bool(priority), found_d is None and bool(domain)
    if not (want_p or want_d):
        return body, []
    lines = body.split("\n")
    new_p, new_d = f"**Priority:** {priority}", f"**Domain:** {domain}"
    if want_p and found_d is not None:  # the Priority line goes straight above an existing Domain line
        lines.insert(body.count("\n", 0, found_d.start()), new_p)
        return "\n".join(lines), ["Priority"]
    if want_d and found_p is not None:  # the Domain line goes straight below an existing Priority line
        lines.insert(body.count("\n", 0, found_p.start()) + 1, new_d)
        return "\n".join(lines), ["Domain"]
    top = _find(lines, fence_flags_any_indent(body), _H1_RE)  # neither line exists: both go under the title
    if top is None:
        return body, []
    wanted = [(name, line) for name, line, flag in (("Priority", new_p, want_p), ("Domain", new_d, want_d)) if flag]
    at = top + 1
    block = [line for _name, line in wanted]
    if at < len(lines) and not lines[at].strip():
        at += 1  # the blank line under the title stays above the added lines
    else:
        block.insert(0, "")
    if at < len(lines) and lines[at].strip():
        block.append("")  # a line directly under the last added line would read as its setext underline
    lines[at:at] = block
    return "\n".join(lines), [name for name, _line in wanted]


def _add_footer(body: str, created: str) -> tuple:
    """Add the `*Created: ...*` footer when the last line is not one. Returns `(body, added)`."""
    if not created or shape._FOOTER_RE.match(shape._last_line(body)):
        return body, False
    lines = body.rstrip().split("\n")
    opener = [] if _THEMATIC_BREAK_RE.match(lines[-1]) else ["", "---"]
    return "\n".join([*lines, *opener, "", f"*Created: {created}*"]) + "\n", True


def _plan_item(path: Path, ident: str, hits: dict, notes: list):
    """The rewrite of one item as a plan dict, or None when its text would not change."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    bom = _BOM if text.startswith(_BOM) else ""
    lf = text[len(bom):].replace("\r\n", "\n")
    reference, changes = lf, []
    if "legacy-decision" in hits:
        folded = _fold(raw[len(bom.encode("utf-8")):], ident, notes)
        if folded is not None:
            lf, reference = folded
            changes.append(("fold", 1, "folded a legacy section"))
    block = split_frontmatter_block(lf)
    if block is None:
        return None
    fm_text, body = block
    fm = parse_frontmatter_map(fm_text) or {}
    unquote = shape._unquote
    extras = {key for key in fm if key not in shape.TEMPLATE_FRONTMATTER_KEYS}
    moved = []
    if extras:
        fm_text, moved = _split_keys(fm_text, extras)
        bullets = []
        for key in fm:
            if key in extras:
                value = " ".join(part.strip() for part in fm[key].split("\n") if part.strip())
                bullets.append(f"- `{key}`: {value}".rstrip())
        body = _add_notes(body, bullets)
        changes.append(("keys", len(extras), "moved " + ", ".join(f"`{key}`" for key in fm if key in extras)
                        + " into Notes"))
        if "blocked_by" in extras:
            notes.append(f"{ident}: `blocked_by` now sits under Notes. Add {ident} to its prerequisite's "
                         "`blocks:` by hand, because the key names the opposite direction")
    body, added = _add_lines(body, unquote(fm.get("priority") or ""), unquote(fm.get("abbrev") or ""))
    if added:
        changes.append(("lines", len(added), "added the " + " and ".join(added) + " line"))
    body, footer = _add_footer(body, unquote(fm.get("created") or ""))
    if footer:
        changes.append(("footer", 1, "added the footer"))
    new = bom + ("---\n" + fm_text + "\n---\n" + body).replace("\n", eol)
    if new.encode("utf-8") == raw:
        return None
    return {"path": path, "id": ident, "data": new.encode("utf-8"), "reference": reference,
            "moved": moved, "changes": changes}


def _dropped(reference: str, written: str, moved: list) -> list:
    """The non-blank lines of `reference` that `written` no longer holds, minus the moved key lines."""
    def lines(text: str) -> Counter:
        return Counter(line.rstrip() for line in text.replace("\r\n", "\n").split("\n") if line.strip())
    missing = lines(reference) - lines(written)
    for line in moved:
        if missing[line.rstrip()] > 0:
            missing[line.rstrip()] -= 1
    return sorted(line for line, count in missing.items() for _ in range(count))


def _routes(config: dict, ids: list) -> dict:
    """The provisional route letter of each id from the live scorer, `?` for one it cannot read."""
    result = {ident: "?" for ident in ids}
    try:
        items, frontmatters, _scores, _open = score_backlog.load_scored_items(config)
        by_id = {normalize_id(item["id"]): item for item in items}
        for ident in ids:
            item = by_id.get(normalize_id(ident))
            if item is not None and item["id"] in frontmatters:
                result[ident] = score_backlog.compute_route_signals(item, frontmatters[item["id"]])["route"]
    except Exception:  # noqa: BLE001 -- the route report is information, never a gate
        return result  # the ids read so far keep their letters, the rest stay `?`
    return result


def _migrate(cfg, from_version: str, to_version: str, report: ItemRepairReport) -> None:
    config_path = Path(cfg.project_root) / cfg.planwise_root / "config.yaml"
    if not config_path.is_file():
        return
    config = config_loader.load_config(Path(__file__), config_path=config_path)
    index_path, backlog_dir = config.get("_index_path"), config.get("_backlog_dir")
    if index_path is None or not Path(index_path).is_file() or backlog_dir is None or not Path(backlog_dir).is_dir():
        return
    report.index_path = index_path
    if sup.classify_shape(read_text(index_path))[0] != "migrated":
        report.state, report.detail = "skipped", "the backlog index is not generated yet; its migration comes first"
        return
    report.backup_dir = (Path(cfg.project_root) / cfg.planwise_root / "upgrade-backups"
                         / f"{from_version}-to-{to_version}" / BACKUP_FOLDER)
    before = shape.scan_item_shapes(backlog_dir)
    report.scanned, report.found = before.scanned, {k: v for k, v in before.classes.items() if v}
    graded, _unreadable = shape.graded_items(backlog_dir)
    plans = []
    for path, ident, hits in graded:
        planned = _plan_item(path, ident, hits, report.notes) if any(key in hits for key in MECHANICAL) else None
        if planned is not None:
            plans.append(planned)
    if not plans:
        report.state, report.remaining = "clean", report.found
        return
    ids = [plan["id"] for plan in plans]
    routes_before = _routes(config, ids)
    pre = bm._backup([plan["path"] for plan in plans], backlog_dir, report)
    if pre is None:
        return
    target = plans[0]["path"]
    try:
        for plan in plans:
            target = plan["path"]
            bm._write_atomic(target, plan["data"])
    except OSError as exc:
        report.detail = f"could not write {target.name}: {exc}"
        bm._write_failed(report, pre, f"fix what the write names, {bm.RERUN}")
        return
    misses = {}
    for plan in plans:
        lost = _dropped(plan["reference"], plan["path"].read_bytes().decode("utf-8", "replace"), plan["moved"])
        if lost:
            misses[plan["id"]] = lost
    if misses:
        report.detail = "preservation diff: " + "; ".join(
            f"{ident} lost {len(lost)} line(s), first: {lost[0][:80]!r}" for ident, lost in misses.items())
        bm._write_failed(report, pre, "report this to the plugin's maintainers with the backups; nothing was kept")
        report.state = "refused"
        return
    for plan in plans:
        reason = "; ".join(text for _tag, _n, text in plan["changes"]) + "; " + bm._kept_at(plan["path"], backlog_dir, report)
        bm._log(cfg, from_version, to_version, plan["path"], ACTION, reason, report)
        for tag, count, _text in plan["changes"]:
            report.counts[tag] = report.counts.get(tag, 0) + count
    if not bm._regenerate(cfg, from_version, to_version, config, index_path, report):
        if report.state != "backup_failed":
            report.state, report.fix = "write_failed", f"fix what the generator names, {bm.RERUN}"
        return
    routes_after = _routes(config, ids)
    report.routes = [(ident, routes_before[ident], routes_after[ident]) for ident in ids]
    report.remaining = {k: v for k, v in shape.scan_item_shapes(backlog_dir).classes.items() if v}
    report.state = "migrated"


def _banner_lines(report: ItemRepairReport) -> list:
    fix = report.fix.replace("\n", "\n          ")
    head = "Backlog item shape repair"
    if report.state == "refused":
        return [f"{head}: REFUSED (every item file was restored to its pre-run bytes)", f"  {report.detail}"]
    if report.state == "backup_failed":
        return [f"{head}: BACKUP FAILED, no write was attempted", f"  {report.detail}", f"  fix:    {fix}"]
    if report.state == "write_failed":
        return [f"{head}: WRITE FAILED", f"  {report.detail}",
                f"  backups: {report.backup_dir} ({len(report.backed_up)} file(s))", f"  fix:    {fix}"]
    if report.state == "error":
        return [f"{head}: ERROR (nothing else in this run depends on it)", f"  {report.detail}"]
    labels = dict(shape.GAP_CLASSES)
    lines = [f"{head}:", f"  open items scanned: {report.scanned}"]
    if report.found:
        lines.append("  found:")
        lines += [f"    ~ {labels[key]}: {len(ids)} — {shape._id_list(ids)}" for key, ids in report.found.items()]
    if report.state == "migrated":
        repaired = ", ".join(f"{COUNT_LABELS[tag]} {count}" for tag, count in report.counts.items())
        lines.append(f"  repaired: {len(report.routes)} item file(s) ({repaired})")
        lines.append("  routes before -> after: " + ", ".join(f"{i}: {b} -> {a}" for i, b, a in report.routes))
        lines.append(f"  backups:  {report.backup_dir} ({len(report.backed_up)} file(s), listed in DISPOSITIONS.md)")
        lines.append("  generator --check: " + ("clean" if report.generator_check_exit == 0
                                                else f"exit {report.generator_check_exit}; re-run /planwise upgrade"))
    if report.remaining:
        lines.append("  left as written, for you to decide:")
        lines += [f"    ~ {labels[key]}: {len(ids)} — {shape._id_list(ids)}" for key, ids in report.remaining.items()]
    lines += [f"  action: {note}" for note in report.notes]
    return lines


def _emit_backlog_items_banner(report: ItemRepairReport) -> None:
    """Print one banner block for the report. Silent when there was nothing to report. Never raises."""
    if report.state in ("absent", "skipped") or (report.state == "clean" and not report.remaining and not report.notes):
        return
    try:
        lines = _banner_lines(report)
    except Exception as exc:  # noqa: BLE001 -- a banner must never fail the caller
        lines = [f"Backlog item shape repair: {report.state} ({report.detail or exc!r})"]
    for line in lines:
        bm._say(line)
    bm._say()
