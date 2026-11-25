#!/usr/bin/env python3
"""Re-parent the headings of old backlog item bodies under the item template, during `/planwise upgrade`.

The router counts every H2 outside the item template as a sub-item signal, so an old item whose body
uses its own headings routes to a planning session. This step moves each such heading under one of
the four core template sections: Summary, Problem, Proposed Solution or Acceptance Criteria.

Two subcommands, both reading the project's `config.yaml`:

- `--list` prints each open item that holds an H2 outside the template, with the core section each
  heading would move under. An `also:` line under an item names a gap a map can fix: a title over
  the cap, or no Summary section. It writes nothing.
- `--apply --upgrade-pair {from}-to-{to}` moves the headings. The caller asks for consent first.

Where a heading goes:

- A built-in synonym table maps a heading to a core section (`Finding` to Problem, `Proposal` to
  Proposed Solution, and so on). The match ignores case and punctuation.
- An optional `--map` JSON file adds or overrides entries. It holds three optional objects:
  `headings` (old heading to core section), `titles` (item id to a new title) and `summaries`
  (item id to Summary text).
- A heading that neither names maps stays where it is and is listed as an action.

What a rewrite does to one item:

- Each mapped H2 becomes an H3 and moves, with its whole block of lines, to the end of its core
  section. A core section the item lacks is created in template order.
- A Summary is written only where the item has none and the map holds Summary text for the item.
- A replaced title moves into a bullet under `## Notes`, and the title line and H1 take the new text.
- It never sets `refined`, and it never touches a frontmatter key other than `title`.

Order of work, so no write happens before its backup and no rewrite goes unchecked:

1. Plan every rewrite in memory. A file whose text would not change is not touched.
2. Capture the route of each file that will change (`score_backlog` signals).
3. Back up each target byte-exact under `upgrade-backups/{from}-to-{to}/backlog-items/`.
4. Write each file atomically, then read it back and run the preservation diff: every non-blank line
   of the original must survive, except the replaced title lines. One miss restores every file this
   run wrote and refuses.
5. Regenerate the index and check it, then capture each route again and print before and after.

A second run finds nothing to move, writes nothing and backs up nothing. The step never raises.
"""
import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

try:
    import backlog_item_shape as shape
    import backlog_migration as bm
    import config_loader
    import migrate_backlog_items as mbi
    import migrate_backlog_support as sup
    from config_gen import InitConfig
    from frontmatter_parser import FM_KEY_LINE_RE, split_frontmatter_block
    from item_shape import _THEMATIC_BREAK_RE, fence_flags_any_indent
    from markdown_parser import normalize_id
    from reconcile_common import read_text_preserving_newlines as read_text
    from score_backlog import TEMPLATE_SECTION_HEADINGS
except ImportError as exc:
    raise ImportError(
        f"backlog_item_reparent could not import a sibling module ({exc}); "
        "the scripts/ directory appears to be partially installed"
    ) from exc

ACTION = "backlog-item-headings-reparented"
CORE = shape.CORE_HEADINGS
# Built-in synonyms: a normalized old heading to the core section it moves under.
SYNONYMS = {
    "overview": "Summary", "description": "Summary", "goal": "Summary", "goals": "Summary",
    "abstract": "Summary", "synopsis": "Summary", "tl dr": "Summary", "what": "Summary",
    "finding": "Problem", "findings": "Problem", "evidence": "Problem", "background": "Problem",
    "context": "Problem", "issue": "Problem", "issues": "Problem", "motivation": "Problem",
    "problem statement": "Problem", "current state": "Problem", "observed behavior": "Problem",
    "root cause": "Problem", "why": "Problem",
    "proposal": "Proposed Solution", "required work": "Proposed Solution", "approach": "Proposed Solution",
    "solution": "Proposed Solution", "fix": "Proposed Solution", "design": "Proposed Solution",
    "implementation": "Proposed Solution", "recommendation": "Proposed Solution",
    "recommended fix": "Proposed Solution", "proposed fix": "Proposed Solution", "how": "Proposed Solution",
    "acceptance": "Acceptance Criteria", "success criteria": "Acceptance Criteria",
    "done when": "Acceptance Criteria", "definition of done": "Acceptance Criteria",
    "exit criteria": "Acceptance Criteria", "criteria": "Acceptance Criteria",
    "expected result": "Acceptance Criteria", "expected behavior": "Acceptance Criteria",
}
_TEMPLATE_ORDER = tuple(TEMPLATE_SECTION_HEADINGS)
_OTHER_RANK = len(_TEMPLATE_ORDER)
_LEGACY = shape._LEGACY_HEADING
# A map summary may not hold a heading line or a code fence, which would change the item's structure.
_STRUCTURAL_LINE_RE = re.compile(r"^(#{1,6}([ \t]|$)|[ \t]*(`{3,}|~{3,}))")
_FOOTER_LINE_RE = re.compile(r"^([*_]).*\1$")  # an italic footer line, such as *Created: 2026-11-18*
_PAIR_PART_RE =re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")  # no path separator, and never `..`
_COUNT_LABELS = {"moved": "headings moved", "created": "core sections created",
                 "summary": "summaries written", "title": "titles replaced"}


@dataclasses.dataclass
class ReparentReport(bm.BacklogMigrationReport):
    """Outcome of one run. `state` is one of: absent, skipped, clean, listed, migrated, refused,
    backup_failed, write_failed, error."""
    scanned: int = 0
    candidates: list = dataclasses.field(default_factory=list)  # (id, [(heading, core section or None)])
    routes: list = dataclasses.field(default_factory=list)  # (id, route before, route after)
    notes: list = dataclasses.field(default_factory=list)  # one action line each
    gaps: dict = dataclasses.field(default_factory=dict)  # id -> what a map can also fix: title over the cap, no Summary


def _norm(heading: str) -> str:
    """A heading as the synonym table keys it: lower case, with each run of punctuation as one space."""
    return re.sub(r"[^a-z0-9]+", " ", heading.lower()).strip()


class MapError(ValueError):
    """A `--map` file that cannot be read or holds an entry the step cannot use."""


def load_map(path) -> dict:
    """Read and check a `--map` JSON file. Raises MapError (a ValueError) that names the first fault."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise MapError(f"the map file could not be read as JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise MapError("the map file must hold one JSON object")
    unknown = sorted(set(data) - {"headings", "titles", "summaries"})
    if unknown:
        raise MapError(f"the map file holds an unknown key: {', '.join(unknown)}")
    for key in ("headings", "titles", "summaries"):
        value = data.get(key, {})
        if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            raise MapError(f"map key {key!r} must be an object of text to text")
    for old, target in data.get("headings", {}).items():
        if target not in CORE:
            raise MapError(f"map heading {old!r} names {target!r}, which is not one of {', '.join(CORE)}")
    for ident, title in data.get("titles", {}).items():
        if not title.strip() or "\n" in title or "\r" in title:
            raise MapError(f"map title for {ident!r} must be one non-empty line of text")
        if len(title.strip()) > shape.TITLE_MAX_LEN:
            raise MapError(f"map title for {ident!r} is over {shape.TITLE_MAX_LEN} characters")
    summaries = {}
    for ident, text in data.get("summaries", {}).items():
        clean = text.replace("\r\n", "\n").replace("\r", "\n")
        bad = next((line for line in clean.split("\n") if _STRUCTURAL_LINE_RE.match(line) or _THEMATIC_BREAK_RE.match(line)), None)
        if bad is not None:
            raise MapError(f"map summary for {ident!r} holds a heading, fence or thematic break line: {bad[:40]!r}")
        summaries[ident] = clean
    return {"headings": dict(data.get("headings", {})), "titles": dict(data.get("titles", {})),
            "summaries": summaries}


def _heading_table(map_data: dict | None) -> dict:
    """The synonym table with the map's heading entries laid over it."""
    table = dict(SYNONYMS)
    for old, target in ((map_data or {}).get("headings") or {}).items():
        table[_norm(old)] = target
    return table


def _by_id(map_data: dict | None, key: str) -> dict:
    return {normalize_id(str(k)): v for k, v in ((map_data or {}).get(key) or {}).items()}


def _h2s(lines: list, flags: list) -> list:
    """`(line index, heading text)` of each unfenced H2."""
    found = []
    for i, line in enumerate(lines):
        match = None if flags[i] else shape._H2_RE.match(line)
        if match:
            found.append((i, match.group(1)))
    return found


def _limit(lines: list, flags: list) -> int:
    """The line where the footer starts, or the line count when the item has no footer break.

    The last thematic break is a footer only when each non-blank line after it is an italic line such
    as `*Created: 2026-11-18*`. A break inside the last section, with plain text after it, is not."""
    at = mbi._footer_break(lines, flags)
    if at is None:
        return len(lines)
    tail = [line.strip() for line in lines[at + 1:] if line.strip()]
    return at if all(_FOOTER_LINE_RE.match(line) for line in tail) else len(lines)


def _rank(name: str) -> int:
    return _TEMPLATE_ORDER.index(name) if name in _TEMPLATE_ORDER else _OTHER_RANK


def _trim_end(lines: list, flags: list, start: int, end: int) -> int:
    """`end` moved up past the blank lines and thematic breaks that close a block, so a separator
    between two sections stays where it is."""
    while end - 1 > start and (not lines[end - 1].strip() or (not flags[end - 1] and _THEMATIC_BREAK_RE.match(lines[end - 1]))):
        end -= 1
    return end


def _plan_moves(lines: list, flags: list, table: dict) -> tuple:
    """`([(start, end, heading, core section)], [unmapped headings])` for the unfenced H2s of a body."""
    found, limit = _h2s(lines, flags), _limit(lines, flags)
    moves, unmapped = [], []
    for k, (start, name) in enumerate(found):
        if name in shape._ALLOWED_HEADINGS or name == _LEGACY:
            continue
        target = table.get(_norm(name))
        if target is None:
            unmapped.append(name)
            continue
        end = found[k + 1][0] if k + 1 < len(found) else limit
        moves.append((start, _trim_end(lines, flags, start, min(end, limit)), name, target))
    return moves, unmapped


def _remove(lines: list, moves: list) -> list:
    """`lines` without the moved ranges. A blank line that the removal would leave doubled is dropped."""
    drop = set()
    for start, end, _name, _target in moves:
        drop.update(range(start, end))
        if start > 0 and not lines[start - 1].strip():
            nxt = end
            while nxt < len(lines) and not lines[nxt].strip():
                drop.add(nxt)
                nxt += 1
    return [line for i, line in enumerate(lines) if i not in drop]


def _blocks_for(lines: list, moves: list) -> dict:
    """The demoted blocks of the moves, grouped by core section in file order."""
    grouped: dict = {}
    for start, end, name, target in moves:
        block = lines[start:end]
        block[0] = f"### {name}"
        grouped.setdefault(target, []).append(block)
    return grouped


def _insert_section(lines: list, target: str, content: list) -> tuple:
    """Put `content` (lines) at the end of the `## {target}` section, or in a new section when the item
    has none. Returns `(lines, created)`."""
    flags = fence_flags_any_indent("\n".join(lines))
    found, limit = _h2s(lines, flags), _limit(lines, flags)
    at = next((k for k, (_i, name) in enumerate(found) if name == target), None)
    if at is not None:
        end = min(found[at + 1][0] if at + 1 < len(found) else limit, limit)
        ins = _trim_end(lines, flags, found[at][0], end)
        tail = [""] if ins >= len(lines) or ins == end else []
        lines[ins:ins] = ["", *content, *tail]
        return lines, False
    rank = _rank(target)
    pos = next((i for i, name in found if _rank(name) > rank), limit)
    head = [""] if pos > 0 and lines[pos - 1].strip() else []
    lines[pos:pos] = [*head, f"## {target}", "", *content, ""]
    return lines, True


def _join_blocks(blocks: list) -> list:
    joined: list = []
    for block in blocks:
        if joined:
            joined.append("")
        joined += block
    return joined


def _title_row(fm_text: str):
    """`(rows, index of the title row, the title text)` of a frontmatter with one `title:` line, else None.
    A double-quoted value is read as JSON, so a title this step wrote reads back as it was given."""
    rows = fm_text.split("\n")
    at = [i for i, row in enumerate(rows) if (m := FM_KEY_LINE_RE.match(row)) and m.group(1) == "title"]
    if len(at) != 1:
        return None
    raw = rows[at[0]].split(":", 1)[1].strip()
    if raw[:1] in (">", "|") or (at[0] + 1 < len(rows) and rows[at[0] + 1][:1] in (" ", "\t")):
        return None  # a folded, literal or wrapped value spans lines, and a one-line rewrite would orphan the rest
    try:
        title = json.loads(raw) if raw.startswith('"') else shape._unquote(raw)
    except ValueError:
        title = shape._unquote(raw)
    return rows, at[0], title


def _replace_title(fm_text: str, body_lines: list, flags: list, new: str) -> tuple | None:
    """Set the `title:` line and the H1's title text to `new`. Returns `(fm_text, body lines, old
    title, the replaced lines)`, or None when the item has no single `title:` line."""
    row = _title_row(fm_text)
    if row is None:
        return None
    rows, at, old = row
    old_line = rows[at].rstrip()
    rows[at] = "title: " + json.dumps(new, ensure_ascii=False)
    replaced = [old_line]
    h1 = mbi._find(body_lines, flags, mbi._H1_RE)
    if h1 is not None and old and body_lines[h1].rstrip().endswith(": " + old):
        replaced.append(body_lines[h1].rstrip())
        body_lines[h1] = body_lines[h1].rstrip()[: -len(old)] + new
    return "\n".join(rows), body_lines, old, replaced


def _plan_item(path: Path, ident: str, table: dict, titles: dict, summaries: dict, notes: list):
    """The rewrite of one item as a plan dict, or None when its text would not change."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    bom = mbi._BOM if text.startswith(mbi._BOM) else ""
    lf = text[len(bom):].replace("\r\n", "\n")
    block = split_frontmatter_block(lf)
    if block is None:
        return None
    fm_text, body = block
    lines = body.split("\n")
    flags = fence_flags_any_indent(body)
    moves, _unmapped = _plan_moves(lines, flags, table)
    changes, moved_lines, bullets = [], [], []
    reference_lines = list(lines)
    for start, _end, name, _target in moves:
        reference_lines[start] = f"### {name}"
    reference = "---\n" + fm_text + "\n---\n" + "\n".join(reference_lines)
    key = normalize_id(ident)
    if moves:
        grouped = _blocks_for(lines, moves)
        lines = _remove(lines, moves)
        for target in CORE:
            if target in grouped:
                lines, created = _insert_section(lines, target, _join_blocks(grouped[target]))
                changes.append(("moved", len(grouped[target]), f"moved {len(grouped[target])} heading(s) under {target}"))
                if created:
                    changes.append(("created", 1, f"created the {target} section"))
    wanted_title = titles.get(key, "").strip()
    current = _title_row(fm_text)
    if wanted_title and current is None:
        notes.append(f"{ident}: the title was left in place (the frontmatter has no one-line title: it is missing, repeated or spans several lines)")
    elif wanted_title and current is not None and current[2] != wanted_title:
        flags_now = fence_flags_any_indent("\n".join(lines))
        replaced = _replace_title(fm_text, lines, flags_now, wanted_title)
        if replaced is not None:
            fm_text, lines, old_title, moved_lines = replaced
            bullets.append(f"- Previous title: {old_title}")
            changes.append(("title", 1, "replaced the title"))
    flags_now = fence_flags_any_indent("\n".join(lines))
    if "Summary" not in [name for _i, name in _h2s(lines, flags_now)] and summaries.get(key, "").strip():
        lines, _created = _insert_section(lines, "Summary", summaries[key].strip().split("\n"))
        changes.append(("summary", 1, "wrote a Summary from the map"))
    if not changes:
        return None
    body = "\n".join(lines)
    if bullets:
        body = mbi._add_notes(body, bullets)
    new = bom + ("---\n" + fm_text + "\n---\n" + body).replace("\n", eol)
    if new.encode("utf-8") == raw:
        return None
    return {"path": path, "id": ident, "data": new.encode("utf-8"), "reference": reference,
            "moved": moved_lines, "changes": changes}


def _candidates(graded: list, table: dict) -> list:
    """`(path, id, [(heading, core section or None)])` for each open item with an H2 outside the template."""
    found = []
    for path, ident, hits in graded:
        if "section-nontemplate" not in hits:
            continue
        parsed = shape._read(path)
        if parsed is None:
            continue
        body = parsed[1]
        flags = fence_flags_any_indent(body)
        pairs = [(name, table.get(_norm(name))) for _i, name in _h2s(body.split("\n"), flags)
                 if name not in shape._ALLOWED_HEADINGS and name != _LEGACY]
        if pairs:
            found.append((path, ident, pairs))
    return found


def _extra_gaps(path: Path, hits: dict) -> list:
    """What a `--map` can also fix on a listed item: a title over the cap, and a missing Summary section."""
    gaps = []
    if "title-over-cap" in hits:
        gaps.append(f"title over {shape.TITLE_MAX_LEN} characters")
    parsed = shape._read(path)
    if parsed is not None:
        body = parsed[1]
        if "Summary" not in [name for _i, name in _h2s(body.split("\n"), fence_flags_any_indent(body))]:
            gaps.append("no Summary section")
    return gaps


def reparent_items(cfg, from_version: str, to_version: str, *, apply: bool = False,
                   map_data: dict | None = None, ids=None) -> ReparentReport:
    """List, or with `apply` move, the non-template headings of the open backlog items. Never raises.

    `ids` limits the run to those item ids. `map_data` is the result of `load_map`."""
    report = ReparentReport(state="absent", index_path=None)
    try:
        _reparent(cfg, from_version, to_version, report, apply, map_data, ids)
    except Exception as exc:  # noqa: BLE001 -- the caller's upgrade must never fail on this step
        report.state, report.detail = "error", repr(exc)
    return report


def _reparent(cfg, from_version: str, to_version: str, report: ReparentReport, apply: bool,
              map_data: dict | None, ids) -> None:
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
                         / f"{from_version}-to-{to_version}" / mbi.BACKUP_FOLDER)
    table = _heading_table(map_data)
    titles, summaries = _by_id(map_data, "titles"), _by_id(map_data, "summaries")
    wanted = {normalize_id(str(i)) for i in ids} if ids else None
    graded, _unreadable = shape.graded_items(backlog_dir)
    report.scanned = len(graded)
    every = _candidates(graded, table)
    found = [c for c in every if wanted is None or normalize_id(c[1]) in wanted]
    report.candidates = [(ident, pairs) for _path, ident, pairs in found]
    hits_of = {ident: hits for _path, ident, hits in graded}
    report.gaps = {ident: gaps for path, ident, _pairs in found if (gaps := _extra_gaps(path, hits_of.get(ident) or {}))}
    used = {normalize_id(ident) for _path, ident, _pairs in found}
    listed = {normalize_id(ident) for _path, ident, _pairs in every}
    report.notes += [f"the map {label} entry for item {key} was not used: "
                     + ("--ids left that item out" if key in listed else "no open item with that id holds a heading outside the template")
                     for label, entries in (("titles", titles), ("summaries", summaries)) for key in sorted(entries) if key not in used]
    if wanted is not None:
        everything = {normalize_id(ident) for _path, ident, _pairs in every}
        report.notes += [f"--ids {key} matched no open item that holds a heading outside the template" for key in sorted(wanted - everything)]
    for _path, ident, pairs in found:
        stuck = [name for name, target in pairs if target is None]
        if stuck:
            report.notes.append(f"{ident}: left as written, no core section for " + ", ".join(f'"{n}"' for n in stuck)
                                + '. Name each one in a --map file under "headings", then re-run')
    if not apply:
        report.state = "listed" if found else "clean"
        return
    plans = []
    for path, ident, _pairs in found:
        planned = _plan_item(path, ident, table, titles, summaries, report.notes)
        if planned is not None:
            plans.append(planned)
    if not plans:
        report.state = "clean"
        return
    _write_plans(cfg, from_version, to_version, report, config, plans)


def _write_plans(cfg, from_version: str, to_version: str, report: ReparentReport, config: dict, plans: list) -> None:
    backlog_dir, index_path = config["_backlog_dir"], config["_index_path"]
    ids = [plan["id"] for plan in plans]
    routes_before = mbi._routes(config, ids)
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
        lost = mbi._dropped(plan["reference"], plan["path"].read_bytes().decode("utf-8", "replace"), plan["moved"])
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
    routes_after = mbi._routes(config, ids)
    report.routes = [(ident, routes_before[ident], routes_after[ident]) for ident in ids]
    report.state = "migrated"


def _banner_lines(report: ReparentReport) -> list:
    head = "Backlog item heading re-parent"
    if report.state == "refused":
        return [f"{head}: REFUSED (every item file was restored to its pre-run bytes)", f"  {report.detail}"]
    if report.state == "backup_failed":
        return [f"{head}: BACKUP FAILED, no write was attempted", f"  {report.detail}", f"  fix:    {report.fix}"]
    if report.state == "write_failed":
        return [f"{head}: WRITE FAILED", f"  {report.detail}",
                f"  backups: {report.backup_dir} ({len(report.backed_up)} file(s))", f"  fix:    {report.fix}"]
    if report.state == "error":
        return [f"{head}: ERROR (nothing else in this run depends on it)", f"  {report.detail}"]
    if report.state == "skipped":
        return [f"{head}: skipped ({report.detail})"]
    lines = [f"{head}:", f"  open items scanned: {report.scanned}"]
    if report.candidates:
        lines.append("  items with a heading outside the template:")
        for ident, pairs in report.candidates:
            lines.append(f"    {ident}: " + "; ".join(f'"{name}" -> {target or "(no core section)"}' for name, target in pairs))
            if report.gaps.get(ident):
                lines.append("      also: " + "; ".join(report.gaps[ident]))
    else:
        lines.append("  no open item holds a heading outside the template")
    if report.state == "migrated":
        repaired = ", ".join(f"{_COUNT_LABELS[tag]} {count}" for tag, count in report.counts.items())
        lines.append(f"  repaired: {len(report.routes)} item file(s) ({repaired})")
        lines.append("  routes before -> after: " + ", ".join(f"{i}: {b} -> {a}" for i, b, a in report.routes))
        lines.append(f"  backups:  {report.backup_dir} ({len(report.backed_up)} file(s), listed in DISPOSITIONS.md)")
        lines.append("  generator --check: " + ("clean" if report.generator_check_exit == 0
                                                else f"exit {report.generator_check_exit}; re-run /planwise upgrade"))
    lines += [f"  action: {note}" for note in report.notes]
    return lines


def _config_for(config_path: Path) -> InitConfig:
    """The `InitConfig` a re-parent run needs, built from the path of `config.yaml`."""
    planwise = config_path.resolve().parent
    return InitConfig(project_name=planwise.parent.name, project_root=planwise.parent,
                      plugin_root=Path(__file__).resolve().parent.parent, planwise_root=planwise.name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Re-parent the headings of old backlog item bodies under the item template.")
    parser.add_argument("--config", required=True, help="path to the project's planwise/config.yaml")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="print the items and the section each heading would move under")
    mode.add_argument("--apply", action="store_true", help="move the headings (back up, write, check, regenerate the index)")
    parser.add_argument("--map", help="JSON file with `headings`, `titles` and `summaries` entries")
    parser.add_argument("--ids", help="comma-separated item ids to limit the run to")
    parser.add_argument("--upgrade-pair", help="{from}-to-{to}, names the backup folder; required with --apply")
    args = parser.parse_args(argv)
    if args.apply and not args.upgrade_pair:
        parser.error("--apply needs --upgrade-pair {from}-to-{to}")
    from_version, _sep, to_version = (args.upgrade_pair or "list-to-list").partition("-to-")
    if not (_PAIR_PART_RE.match(from_version) and _PAIR_PART_RE.match(to_version)):
        parser.error("--upgrade-pair must read {from}-to-{to}, each part a version with no path separator")
    map_data = None
    if args.map:
        try:
            map_data = load_map(args.map)
        except MapError as exc:
            print(f"Backlog item heading re-parent: {exc}", file=sys.stderr)
            return 1
    ids = None
    if args.ids is not None:
        ids = [part.strip() for part in args.ids.split(",") if part.strip()]
        if not ids:
            parser.error("--ids needs at least one item id; leave the flag out to cover every item")
    report = reparent_items(_config_for(Path(args.config)), from_version, to_version, apply=args.apply,
                            map_data=map_data, ids=ids)
    for line in _banner_lines(report) if report.state != "absent" else ["Backlog item heading re-parent: no config.yaml or backlog index was found."]:
        print(line)
    return 1 if report.state in ("refused", "backup_failed", "write_failed", "error", "absent") else 0


if __name__ == "__main__":
    sys.exit(main())
