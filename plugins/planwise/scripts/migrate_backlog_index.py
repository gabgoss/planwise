#!/usr/bin/env python3
"""Migrate a hand-authored backlog index into the shape the generator reads.

A hand-authored index carries content with no home in item frontmatter: a
changelog footer, Feature-cell prose that differs from the item's `title:`,
and extra links in a Files cell. Regeneration drops all three. This tool
moves them first, so retiring the old index loses nothing.

Sequence: (1) `--dry-run`, the default, reports the plan and writes nothing.
(2) Review the plan. (3) `--write` stages every output, replaces the
targets, re-reads them from disk to verify, then writes the ledger.
(4) Run `generate_backlog_index.py --write`. (5) Run it with `--check`.
`/planwise upgrade` and `/planwise init` run this whole sequence with every
repair flag on, backing up each file first. `--report` prints a read-only
JSON readiness report instead; it never writes and always exits 0. The
changelog is written as budgeted numbered parts, and `--split-changelog`
re-splits one that has grown over budget.

Recognise-or-refuse, never best-effort. Before any write, the run refuses
(exit 2) and names the cause when: the shape, a column or a `##` section is
not recognised; any line anywhere in the file is prose the regeneration
drops (preamble, items section, Shards, Dependencies); a `## Dependencies`
edge is missing from its item's frontmatter `blocks:`; the generator's own
scan would refuse the tree; a row has an empty ID cell or prose in its
Files or Blocks cell; a row cell disagrees with its item frontmatter; a
dedup unit is AMBIGUOUS without `--append-ambiguous`; `--thresholds` is not
0 <= low < high <= 1; git cannot report the tree state, or ignores the
index or an item file, without `--allow-untracked-tree`; or the tree is
dirty without `--force`. When the run recognises an interrupted migration
of this index, the dirty check exempts exactly the paths that migration
owns, so a plain `--write` resumes. Any other dirty path still refuses.

Repairs are off by default, and a refusal that one closes names its flag.
`--backfill-frontmatter` fills a missing block or missing keys from the
index row, the file name, and git (else the file's mtime).
`--write-edges` writes each `## Dependencies` edge into its item's
`blocks:`. `--extract-dependency-notes` moves each soft-dependency bullet
under `## Dependencies` into its owning item's `## Dependency Notes
(migrated from the backlog index)`. `--reconcile index-wins|frontmatter-wins`
settles a row/frontmatter disagreement. A changelog holding only its
backlink line counts as absent. These still refuse under every flag: a
file with no frontmatter and no index row, a bullet naming no known item,
an unparseable frontmatter block, and a reciprocal edge.

Dedup: a unit is ALREADY-PRESENT only when its whole strict form (case
folded, whitespace collapsed, emphasis stripped) occurs in one paragraph
of the item file or of the appends already planned for it. Similarity
alone yields AMBIGUOUS. A Files-cell link after the first is carried into
the item's `## Migration Notes` block unless the item already links to its
target. A unit already inside that block counts as appended by a prior run.
Each file keeps its newline style and permission mode.

Atomic and resumable: every output is staged beside its target, so a
failure before the replace phase changes nothing. The index is replaced
last. "Already migrated" is a state: the footer points to the changelog,
the changelog exists, and no row prose is missing. That state exits 0.

The changelog sits beside the index and is named by the generator's own
`_changelog_filename`: `00-Changelog-{X}{suffix}` when the index is
`00-Index-{X}{suffix}`, else `00-{stem}-Changelog{suffix}`. The ledger is
`00-{stem}-Migration-Ledger.json`, where `{stem}` is the index stem without
a leading `00-`. The generator's item scan skips `00-` files.
With `--json`, stdout carries only the JSON document.

Exit codes: 0 clean, or nothing to do. 1 migration needed (dry-run), or a
write or verification failure. 2 refused.
"""
import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_backlog_index as gen  # noqa: E402
import migrate_backlog_checks as chk  # noqa: E402
import migrate_backlog_repairs as repairs  # noqa: E402
import migrate_backlog_support as sup  # noqa: E402
from config_loader import load_config  # noqa: E402
from reconcile_common import read_text_preserving_newlines as read_text  # noqa: E402

UNRECOVERABLE = ("resumed: this size includes notes an interrupted earlier run appended; "
                 "the pre-migration size is not recoverable from this file")
RECONCILE_MODES = ("index-wins", "frontmatter-wins")
KEYS = tuple(gen.REQUIRED_KEYS)


Refusal = sup.Refusal  # single class object, so `except Refusal` catches every raiser


@dataclass
class RepairOptions:
    """Which repairs `plan_migration` may make. Every repair is off by default."""
    backfill_frontmatter: bool = False
    write_edges: bool = False
    extract_dependency_notes: bool = False
    reconcile: str | None = None
    append_ambiguous: bool = False
    high: float = sup.DEFAULT_HIGH
    low: float = sup.DEFAULT_LOW

    @classmethod
    def all_on(cls, reconcile: str = "index-wins") -> "RepairOptions":
        return cls(backfill_frontmatter=True, write_edges=True, extract_dependency_notes=True, reconcile=reconcile)


def say(code: int, msg: str, json_mode: bool, err: bool = False) -> int:
    print(msg, file=sys.stderr if (err or json_mode) else sys.stdout)
    return code


def artifact_paths(index_path: Path):
    """Return (changelog, ledger, older changelog name used by earlier versions).

    The changelog name comes from `gen._changelog_filename` -- the SAME
    namer `generate_backlog_index.py`'s own hub footer uses, so the two
    scripts can never disagree on the changelog's name (closeout review
    Finding 1b).
    """
    naming = gen._index_naming(index_path)
    changelog = index_path.with_name(gen._changelog_filename(naming))
    ledger = index_path.with_name(f"00-{naming.archive_stem}-Migration-Ledger.json")
    older = index_path.with_name(f"{index_path.stem}-Changelog{index_path.suffix}")
    return changelog, ledger, older


def _text(texts: dict, path: Path) -> str:
    """The planned text of `path`, else its text on disk."""
    return texts[path] if path in texts else read_text(path)


def _header_only(changelog_text: str, index_path: Path) -> bool:
    """True when a changelog holds nothing but its backlink line (the seed and the generator's bootstrap)."""
    return changelog_text.replace("\r\n", "\n").strip() == f"[← {index_path.name}]({index_path.name})"


def _census(config: dict, index_path: Path):
    """Yield (resolved path, text, raw frontmatter map, has_block) for every item file the generator scans."""
    for path in gen._iter_item_files(config["_backlog_dir"], config["_archive_dir"], index_path):
        body = read_text(path)
        raw, has_block, _bom, _nl = repairs.partial_frontmatter(body)
        yield path.resolve(), body, raw, has_block


def preflight_generator(config: dict, index_path: Path, overrides: dict | None = None,
                        backfill_hint: bool = False) -> dict:
    """Run the generator's own scan now, so its refusal lands before any write.
    `overrides` maps a resolved item path to planned text the scan reads instead."""
    naming = gen._index_naming(index_path)
    view = {path: text.replace("\r\n", "\n") for path, text in (overrides or {}).items()}
    try:
        items, reciprocal, _report = gen._run_report_pipeline(
            config["_backlog_dir"], config["_archive_dir"], index_path, naming, config, overrides=view)
    except gen.GeneratorError as exc:
        hint = ""
        if backfill_hint and ("missing required frontmatter key" in str(exc) or "no well-formed frontmatter" in str(exc)):
            hint = " -- add --backfill-frontmatter to fill the missing frontmatter from the index row, file name and git"
        raise Refusal(f"the generator would refuse this tree -- {exc}{hint}") from exc
    if reciprocal:
        pairs = ", ".join(f"{a}<->{b}" for a, b in reciprocal)
        raise Refusal(f"the generator would refuse to write: reciprocal blocks edge(s) {pairs}")
    return {item["_path"].resolve(): item for item in items}


def resolve_rows(text: str, header_idx: int, roles: dict, config: dict, index_path: Path) -> list:
    """Resolve each row's Files cell to its item file; refuse a row this tool cannot read."""
    rows = []
    for line_no, cells in sup.iter_rows(text.split("\n"), header_idx):
        where = f"row at line {line_no + 1}"
        if len(cells) != len(roles):
            raise Refusal(f"{where}: {len(cells)} cell(s) but the header has {len(roles)}")
        if not cells[roles["id"]].strip():
            raise Refusal(f"{where}: empty ID cell")
        links, leftover = sup.files_links(cells[roles["file"]])
        if leftover:
            raise Refusal(f"{where}: Files cell carries text other than links, {cells[roles['file']]!r}")
        path = sup.resolve_item_file(links[0][1], config["_backlog_dir"], config["_archive_dir"],
                                     index_path.parent) if links else None
        if path is None:
            raise Refusal(f"{where} (id {cells[roles['id']]}): Files cell resolves no item file")
        rows.append({"line": line_no, "cells": cells, "path": path, "links": links})
    return rows


def collect_rows(resolved: list, roles: dict, index_path: Path, items: dict):
    """Return (rows with their prose units, cell/frontmatter disagreements)."""
    rows, diffs = [], []
    for row in resolved:
        path, cells, links = row["path"], row["cells"], row["links"]
        fields = items.get(path)
        if fields is None:
            raise Refusal(f"row at line {row['line'] + 1}: {path.name} is not an item file the generator scans")
        diffs += [{**diff, "id": fields["id"], "path": path} for diff in sup.row_diffs(cells, roles, fields)]
        extra = [sup.link_unit(t, h, index_path.parent, path.parent) for t, h in links[1:]
                 if h.strip() != links[0][1].strip()]
        rows.append({"id": fields["id"], "path": path, "links": extra,
                     "units": sup.row_units(cells[roles["feature"]], fields["title"])})
    return rows, diffs


def _cell(row: dict, roles: dict, role: str) -> str:
    return sup.plain(row["cells"][roles[role]]) if role in roles else ""


def _abbrev(row: dict, roles: dict, path: Path, config: dict, where: str) -> str:
    configured = config.get("abbreviations")
    valid = {str(k) for k in configured} if isinstance(configured, (dict, list, tuple, set)) and configured else None
    seg, cell = (repairs.filename_fields(path.name) or (None, None))[1], _cell(row, roles, "abbrev")
    usable = [v for v in (seg, cell) if v and (valid is None or v in valid)]
    if len(set(usable)) > 1:
        raise Refusal(f"{where}: the file name says abbrev {seg!r} but the index cell says {cell!r} -- "
                      "make them agree by hand, then re-run")
    return usable[0] if usable else ""


def _source_values(keys: list, row: dict, roles: dict, path: Path, config: dict, dates: dict):
    """Return ({key: value} for `keys`, the created-date source or None). Refuses rather than guess."""
    where = f"{path.name} (row at line {row['line'] + 1})"
    values, source = {}, None
    for key in keys:
        if key == "id":
            ids, named = sup.ids_in(row["cells"][roles["id"]]), repairs.first_id_in(path.stem)
            if len(ids) != 1 or (named is not None and named != ids[0]):
                raise Refusal(f"{where}: the ID cell names {ids or 'no id'} and the file name names {named} -- "
                              "make them agree by hand, then re-run")
            values[key] = ids[0]
        elif key == "title":
            values[key] = repairs.title_from_cell(row["cells"][roles["feature"]])
        elif key == "abbrev":
            values[key] = _abbrev(row, roles, path, config, where)
        elif key == "created":
            index_date = _cell(row, roles, "created")
            values[key], source = (index_date, "index") if index_date else dates[path]
        elif key == "blocks":
            values[key] = []
        else:
            values[key] = _cell(row, roles, key)
        if values[key] == "":
            raise Refusal(f"{where}: nothing supplies its {key}: (no such column, or the cell is empty) -- "
                          "add the key by hand, then re-run")
    return values, source


def _rendered(values: dict) -> dict:
    """Each value as `render_frontmatter` writes it (quoting, list form), so a partial block matches a new one."""
    full = {"id": "", "title": "", "priority": "", "status": "", "abbrev": "", "created": "", "blocks": [], **values}
    pairs = dict(line.split(": ", 1) for line in repairs.render_frontmatter(full, "\n").split("\n")[1:8])
    return {key: pairs[key] for key in values}


def plan_backfill(resolved: list, roles: dict, config: dict, index_path: Path, texts: dict) -> list:
    """Plan frontmatter for every scanned item file that lacks a block or keys, into `texts`."""
    by_path = {}
    for row in resolved:
        by_path.setdefault(row["path"], row)
    todo = []
    for path, body, raw, has_block in _census(config, index_path):
        if has_block and raw is None:
            raise Refusal(f"{path.name}: its frontmatter block does not close or cannot be parsed -- "
                          "fix it by hand, then re-run")
        missing = [key for key in KEYS if raw is None or key not in raw]
        if not missing:
            continue
        if path not in by_path:
            raise Refusal(f"{path.name} lacks frontmatter key(s) {', '.join(missing)} and no index row names it, "
                          "so nothing supplies the values -- add them by hand or add its row, then re-run")
        todo.append((path, body, has_block, missing, by_path[path]))
    dated = [path for path, _b, _h, missing, row in todo if "created" in missing and not _cell(row, roles, "created")]
    dates = repairs.created_dates(config["_project_root"], dated, config["_backlog_dir"]) if dated else {}
    planned = []
    for path, body, has_block, missing, row in todo:
        values, source = _source_values(missing, row, roles, path, config, dates)
        nl = sup.newline_of(body)
        if has_block:
            try:
                texts[path] = repairs.insert_missing_keys(body, _rendered(values), nl)
            except ValueError as exc:
                raise Refusal(f"{path.name}: {exc} -- fix the block by hand, then re-run") from exc
        else:
            bom = "﻿" if body.startswith("﻿") else ""
            texts[path] = bom + repairs.render_frontmatter(values, nl) + body[len(bom):]
        planned.append({"path": path, "keys_added": missing, "created_source": source, "partial": has_block})
    return planned


def plan_edges(edges: list, items: dict, texts: dict) -> list:
    """Union each Dependencies edge into its source item's `blocks:` in `texts`."""
    by_id = {item["id"]: (path, item) for path, item in items.items()}
    wanted = {}
    for _line, src, dst in edges:
        if src in by_id and dst not in by_id[src][1]["blocks"]:
            wanted.setdefault(src, set()).add(dst)
    planned = []
    for src in sorted(wanted, key=int):
        path, item = by_id[src]
        union = sorted(set(item["blocks"]) | wanted[src], key=int)
        texts[path] = repairs.replace_key_line(_text(texts, path), "blocks", f"[{', '.join(union)}]")
        planned += [{"src": src, "dst": dst, "path": path} for dst in sorted(wanted[src], key=int)]
    return planned


def plan_reconcile(diffs: list, mode: str | None, texts: dict, items: dict) -> list:
    """Settle each row/frontmatter disagreement per `mode`, or refuse naming both modes."""
    if not diffs:
        return []
    if mode is None:
        raise Refusal(f"{len(diffs)} row cell(s) disagree with item frontmatter: "
                      f"{'; '.join(d['message'] for d in diffs[:10])}. The generator renders frontmatter, so "
                      "reconcile the frontmatter first -- or add --reconcile index-wins to write each row value "
                      "into frontmatter, or --reconcile frontmatter-wins to keep the frontmatter")
    stuck = [d for d in diffs if d["prose"] or (mode == "index-wins" and d["row"] is None)]
    if stuck:
        raise Refusal(f"{len(stuck)} row cell(s) disagree with item frontmatter and --reconcile {mode} cannot "
                      f"settle them: {'; '.join(d['message'] for d in stuck[:10])}. Fix them by hand, then re-run")
    for d in diffs:
        if mode == "index-wins":
            value = f"[{', '.join(d['row'])}]" if d["key"] == "blocks" else d["row"]
            texts[d["path"]] = repairs.replace_key_line(_text(texts, d["path"]), d["key"], value)
            items[d["path"]][d["key"]] = d["row"]
    return [{"id": d["id"], "key": d["key"], "frontmatter": d["frontmatter"], "index": d["row"], "path": d["path"]}
            for d in diffs]


def plan_dedup(rows: list, high: float, low: float, append_ambiguous: bool, texts: dict | None = None) -> list:
    texts = {} if texts is None else texts
    dests = {}
    for row in rows:
        dest = dests.setdefault(row["path"], {"path": row["path"], "units": [], "links": []})
        dest["units"] += [(row["id"], unit) for unit in row["units"]]
        dest["links"] += [(row["id"], link) for link in row["links"]]
    ambiguous = []
    for dest in dests.values():
        dest["body"] = _text(texts, dest["path"])
        dest["bytes_before"] = dest["path"].stat().st_size
        dest["append"], dest["dedup"], dest["ambiguous"], dest["prior"] = [], [], [], []
        notes, index = sup.prior_notes(dest["body"]), sup.body_index(dest["body"])
        for row_id, unit in dest["units"]:
            exact, score, window = sup.score_unit(unit, index)
            verdict = sup.classify_unit(exact, score, window, high, low)
            if verdict == "ALREADY-PRESENT":
                dest["prior" if notes and unit in notes else "dedup"].append((row_id, unit))
                continue
            if verdict == "AMBIGUOUS":
                if not append_ambiguous:
                    label = "near-duplicate" if max(score, window) >= high else "partial overlap"
                    ambiguous.append(f"row {row_id} ({label}, similarity {max(score, window):.2f}): {unit[:80]!r}")
                    continue
                dest["ambiguous"].append(unit)
            dest["append"].append((row_id, unit))
            sup.extend_index(index, unit)
        for row_id, (unit, name) in dest["links"]:
            planned = dest["body"] + "\n" + "\n".join(u for _r, u in dest["append"])
            if sup.link_listed(name, planned):
                dest["prior" if notes and unit in notes else "dedup"].append((row_id, unit))
            else:
                dest["append"].append((row_id, unit))
    if ambiguous:
        raise Refusal(f"{len(ambiguous)} ambiguous dedup unit(s), e.g. {'; '.join(ambiguous[:5])} -- "
                      "review them, then rerun with --append-ambiguous to append them (--force does not)")
    return list(dests.values())


def plan_notes(bullets: list, items: dict, texts: dict) -> list:
    """Append each soft-dependency bullet to its owner's dependency-notes section in `texts`."""
    owners = {item["id"]: path for path, item in items.items()}
    grouped = {}
    for bullet in bullets:
        path = owners.get(bullet["owner"])
        if path is None:
            named = f"id {bullet['owner']}, which has no item file" if bullet["owner"] else "no item id"
            raise Refusal(f"line {bullet['line']}: the soft-dependency bullet {bullet['text'][:60]!r} names {named} "
                          "-- add the item, or move the bullet into its owner's file by hand, then re-run")
        grouped.setdefault(path, []).append(bullet["text"])
    planned = []
    for path, units in grouped.items():
        body = _text(texts, path)
        nl, index, fresh = sup.newline_of(body), sup.body_index(body), []
        for unit in units:
            if not sup.score_unit(unit, index)[0]:
                fresh.append(unit.replace("\n", nl))
                sup.extend_index(index, unit)
        if fresh:
            texts[path] = sup.append_notes(body, fresh, nl, sup.NOTES_HEADING_DEPS)
        planned.append({"path": path, "units": fresh, "bullets": len(fresh), "present": len(units) - len(fresh),
                        "bytes": sum(len(u.encode("utf-8")) for u in fresh)})
    return planned


def plan_changelog(text: str, index_path: Path, changelog_path: Path, pending: int, naming):
    """Return the multi-part changelog plan, or None when the index is
    already migrated. A changelog holding only its backlink
    line is treated as absent. `plan["parts"]` is `[(path, text), ...]`,
    part 1 first."""
    footer = sup.FOOTER_TEXT_RE.search(text).group(0)
    pointer = sup.POINTER_RE.match(footer)
    if pointer:
        if changelog_path.name not in (pointer.group(1), pointer.group(2)):
            raise Refusal(f"the footer points to {pointer.group(2)}, expected {changelog_path.name}")
        if not changelog_path.exists():
            raise Refusal(f"the footer says the changelog moved to {changelog_path.name}, but that "
                          "file is missing -- restore it from version control")
        if pending:
            raise Refusal(f"half-migrated: the footer already points to {changelog_path.name}, but "
                          f"{pending} unit(s) of row prose or item-file repairs are not in their item files. An "
                          "interrupted older run or a hand edit left this state -- restore from version control")
        return None
    extracted = sup.extract_changelog(index_path.read_bytes())
    split = sup.split_changelog(extracted["segments"], naming, index_path.name, sup.newline_of(text))
    pattern = sup.changelog_part_pattern(naming)
    max_planned = len(split)
    for p in index_path.parent.iterdir():
        m = pattern.match(p.name)
        if m and int(m.group(1)) > max_planned:
            raise Refusal(f"{p.name} exists beyond the planned {max_planned} changelog part(s) -- a stale "
                          "part would silently shadow the real ones; remove it or restore the index from "
                          "version control")
    plan = {**extracted, "resumed": False, "header_only": False}
    part1_name, _part1_text = split[0]
    part1_path = index_path.with_name(part1_name)
    if part1_path.exists() and _header_only(read_text(part1_path), index_path):
        plan["header_only"] = True
        plan["parts"] = [(index_path.with_name(name), t) for name, t in split]
        plan["text"] = plan["parts"][0][1]
        return plan
    parts = []
    for name, part_text in split:
        part_path = index_path.with_name(name)
        if part_path.exists():
            existing = read_text(part_path)
            if existing.replace("\r\n", "\n") != part_text.replace("\r\n", "\n"):
                raise Refusal(f"{part_path.name} already exists but does not hold this index's footer "
                              "entries. An interrupted older run or a hand edit left it -- move it aside "
                              "or restore the index from version control")
            plan["resumed"] = True
        parts.append((part_path, part_text))
    plan["parts"] = parts
    plan["text"] = parts[0][1]
    return plan


def _drop_lines(text: str, drop: set) -> str:
    """Remove the 0-based lines in `drop`, and the blank line each removal would leave doubled."""
    kept = []
    for i, line in enumerate(text.split("\n")):
        if i in drop or (i - 1 in drop and not line.strip() and kept and not kept[-1].strip()):
            continue
        kept.append(line)
    return "\n".join(kept)


def _key_lines(text: str, keys: list) -> list:
    """The frontmatter lines of `text` that set one of `keys`."""
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), len(lines))
    return [line for line in lines[1:end] if line.split(":", 1)[0] in keys]


def build_plan(text: str, detail: tuple, config: dict, index_path: Path, paths: tuple, options: RepairOptions):
    header_idx, roles = detail
    problems, edges, found = chk.scan_index(text, header_idx, extract_notes=options.extract_dependency_notes)
    if problems:
        hint = ""
        if not options.extract_dependency_notes and len(chk.scan_index(text, header_idx, True)[0]) < len(problems):
            hint = " -- add --extract-dependency-notes to move the soft-dependency bullets into their owning item files"
        raise Refusal("content regeneration would drop and this tool does not move: " + "; ".join(problems) + hint)
    changelog_path, _ledger, older = paths
    if older != changelog_path and older.exists():
        raise Refusal(f"{older.name} exists from an earlier version of this tool, and the generator "
                      f"would scan it as an item file -- rename it to {changelog_path.name}")
    resolved = resolve_rows(text, header_idx, roles, config, index_path)
    texts = {}
    backfill = plan_backfill(resolved, roles, config, index_path, texts) if options.backfill_frontmatter else []
    no_backfill = not options.backfill_frontmatter
    edge_plan = []
    if options.write_edges and edges:
        edge_plan = plan_edges(edges, preflight_generator(config, index_path, texts, no_backfill), texts)
    items = preflight_generator(config, index_path, texts, no_backfill)
    missing = chk.missing_edges(edges, items)
    if missing:
        raise Refusal(f"{len(missing)} '## Dependencies' edge(s) are missing from frontmatter blocks: "
                      f"{'; '.join(missing[:10])}. The generator renders no Dependencies section, so add "
                      "each edge to its item's blocks: first"
                      + ("" if options.write_edges else " -- or add --write-edges to write each edge into blocks:"))
    rows, diffs = collect_rows(resolved, roles, index_path, items)
    cells = plan_reconcile(diffs, options.reconcile, texts, items)
    written_cells = cells if options.reconcile == "index-wins" else []
    if written_cells:
        items = preflight_generator(config, index_path, texts)
    dests = plan_dedup(rows, options.high, options.low, options.append_ambiguous, texts)
    for dest in dests:
        if dest["append"]:
            units = [unit for _row_id, unit in dest["append"]]
            dest["new_text"] = sup.append_notes(dest["body"], units, sup.newline_of(dest["body"]))
            texts[dest["path"]] = dest["new_text"]
    notes = plan_notes([f for f in found if f["kind"] == "bullet"], items, texts)
    pending = (sum(len(d["append"]) for d in dests) + len(backfill) + len(edge_plan) + len(written_cells)
               + sum(n["bullets"] for n in notes))
    naming = gen._index_naming(index_path)
    changelog = plan_changelog(text, index_path, changelog_path, pending, naming)
    if changelog is None:
        return None
    for entry in backfill:
        entry["lines"] = _key_lines(texts[entry["path"]], entry["keys_added"])
    footer = sup.FOOTER_TEXT_RE.search(text)
    pointer = f"*Last Updated: {date.today().isoformat()} — moved to [{changelog_path.name}]({changelog_path.name})*"
    index_text = text[:footer.start()] + pointer + text[footer.end():]
    drop = {i for f in found for i in range(f["line"] - 1, f["line"] - 1 + f["count"])}
    if drop:
        index_text = _drop_lines(index_text, drop)
    outputs = [(path, texts[path]) for path in sorted(texts, key=str)]
    outputs += list(changelog["parts"]) + [(index_path, index_text)]
    return {"changelog": changelog, "dests": dests, "row_count": len(rows),
            "interrupted": changelog["resumed"] or any(d["prior"] for d in dests) or any(n["present"] for n in notes),
            "index_text": index_text, "backfill": backfill, "edges": edge_plan, "notes": notes,
            "dropped_headings": [f["text"] for f in found if f["kind"] == "heading"],
            "reconcile": {"mode": options.reconcile, "cells": cells}, "outputs": outputs}


def plan_migration(config: dict, index_path: Path, text: str, detail: tuple, options: RepairOptions):
    """Plan the migration of a `legacy` index in memory. Returns the plan, or None when the
    index is already migrated. Raises `Refusal`. Nothing is written."""
    if options.reconcile not in (None, *RECONCILE_MODES):
        raise Refusal(f"unknown reconcile mode {options.reconcile!r}; use one of {', '.join(RECONCILE_MODES)}")
    return build_plan(text, detail, config, index_path, artifact_paths(index_path), options)


def plan_targets(plan: dict) -> list:
    """Every existing file the plan rewrites, for a caller to back up first: the item files,
    the changelog when it exists, and the index. The ledger is new, so it is never a target."""
    return [path for path, _text in plan["outputs"] if path.exists()]


def build_ledger(plan: dict, paths: tuple, measured: dict | None = None, misses: list | None = None,
                 disk_log: str | None = None) -> dict:
    c, dests = plan["changelog"], plan["dests"]
    units = {k: [u for d in dests for _r, u in d[k]] for k in ("append", "dedup", "prior")}
    size = lambda us: sum(len(u.encode("utf-8")) for u in us)  # noqa: E731
    planned_text = sup.joined_entries([t for _p, t in c["parts"]])
    ledger = {
        "run_date": date.today().isoformat(), "mode": "dry-run" if measured is None else "write",
        "changelog": {**{k: v for k, v in c.items() if k not in ("segments", "parts")},
                      "entries": len(c["segments"]), "path": str(paths[0]), "bytes_on_disk": None,
                      "parts": [{"path": str(p), "tokens": sup.changelog_tokens(t),
                                 "entries": len(sup.ENTRY_HEADING_RE.findall(t.replace("\r\n", "\n")))}
                                for p, t in c["parts"]],
                      "unaccounted": sup.unaccounted(c["segments"], planned_text if disk_log is None else disk_log),
                      "unaccounted_basis": "staged changelog text" if disk_log is None else "changelog on disk"},
        "dedup": {"rows": plan["row_count"], "units": sum(len(v) for v in units.values()),
                  "appended_units": len(units["append"]), "appended_bytes": size(units["append"]),
                  "appended_by_prior_run_units": len(units["prior"]),
                  "appended_by_prior_run_bytes": size(units["prior"]),
                  "deduplicated_units": len(units["dedup"]), "deduplicated_bytes": size(units["dedup"]),
                  "ambiguous_appended": sum(len(d["ambiguous"]) for d in dests)},
        "destinations": [{"path": str(d["path"]), "bytes_before": d["bytes_before"],
                          "bytes_before_basis": UNRECOVERABLE if d["prior"] else "pre-migration",
                          "bytes_after": None, "bytes_added": None, "units_appended": len(d["append"]),
                          "units_appended_by_prior_run": len(d["prior"]),
                          "units_deduplicated": len(d["dedup"])} for d in dests],
        "backfill": [{"path": str(b["path"]), "keys_added": b["keys_added"], "created_source": b["created_source"]}
                     for b in plan["backfill"]],
        "edges": [{"src": e["src"], "dst": e["dst"]} for e in plan["edges"]],
        "dependency_notes": [{"path": str(n["path"]), "bullets": n["bullets"], "bytes": n["bytes"],
                              "already_present": n["present"]} for n in plan["notes"]],
        "dependency_headings_dropped": plan["dropped_headings"],
        "reconcile": {"mode": plan["reconcile"]["mode"],
                      "cells": [{k: v for k, v in cell.items() if k != "path"} for cell in plan["reconcile"]["cells"]]},
        "verification": None,
    }
    if measured is not None:
        for entry in ledger["destinations"]:
            entry["bytes_after"] = measured[entry["path"]]
            entry["bytes_added"] = entry["bytes_after"] - entry["bytes_before"]
        ledger["changelog"]["bytes_on_disk"] = measured[str(paths[0])]
        ledger["verification"] = {"verified": not misses, "misses": misses}
    return ledger


def format_report(plan: dict) -> str:
    c, dests = plan["changelog"], plan["dests"]
    count = {k: sum(len(d[k]) for d in dests) for k in ("append", "dedup", "prior")}
    backfill, notes, rec = plan["backfill"], plan["notes"], plan["reconcile"]
    planned_text = sup.joined_entries([t for _p, t in c["parts"]])
    lines = [f"changelog: {len(c['segments'])} entr(y/ies), {c['entry_content_bytes']} content bytes, "
             f"unaccounted={sup.unaccounted(c['segments'], planned_text)}"
             f"{', resuming an interrupted run' if c['resumed'] else ''}"
             f"{', filling a header-only changelog' if c.get('header_only') else ''}",
             f"changelog parts: {len(c['parts'])} file(s), " + ", ".join(
                 f"{p.name}={sup.changelog_tokens(t)}t" for p, t in c["parts"]),
             f"dedup: {sum(count.values())} unit(s) across {plan['row_count']} row(s) -- {count['append']} to "
             f"append, {count['prior']} appended by a prior run, {count['dedup']} already present (deduplicated)",
             f"backfill: {len(backfill)} item file(s) gain frontmatter ({sum(b['partial'] for b in backfill)} "
             "had a partial block)",
             f"edges: {len(plan['edges'])} '## Dependencies' edge(s) to write into blocks:",
             f"dependency notes: {sum(n['bullets'] for n in notes)} bullet(s) into "
             f"{sum(1 for n in notes if n['bullets'])} item file(s), {len(plan['dropped_headings'])} heading line(s) dropped",
             f"reconcile: {rec['mode'] or 'off'}, {len(rec['cells'])} cell(s)"]
    for d in dests:
        lines += [f"  append row {row_id} -> {d['path'].name}: {unit[:70]!r}" for row_id, unit in d["append"]]
    return "\n".join(lines)


def verify_written(plan: dict, paths: tuple, index_path: Path) -> list:
    """Re-read every written file from disk and name each unit, key line or edge not found."""
    misses = []
    part_paths = [p for p, _t in plan["changelog"].get("parts", [(paths[0], None)])]
    log = sup.joined_entries([read_text(p) for p in part_paths])
    for i, seg in enumerate(plan["changelog"]["segments"], start=1):
        if seg.decode("utf-8") not in log:
            misses.append(f"changelog entry {i} is missing from its changelog part(s)")
    for d in plan["dests"]:
        body = read_text(d["path"])
        misses += [f"row {row_id} unit {unit[:70]!r} is missing from {d['path'].name}"
                   for row_id, unit in d["append"] + d["prior"] if unit not in body]
    for b in plan.get("backfill", ()):
        body = read_text(b["path"]).replace("\r\n", "\n")
        misses += [f"backfilled line {line!r} is missing from {b['path'].name}" for line in b["lines"] if line not in body]
    for e in plan.get("edges", ()):
        raw = repairs.partial_frontmatter(read_text(e["path"]))[0] or {}
        if e["dst"] not in sup.ids_in(raw.get("blocks", "")):
            misses.append(f"edge {e['src']} blocks {e['dst']} is missing from {e['path'].name}")
    for n in plan.get("notes", ()):
        body = read_text(n["path"])
        misses += [f"dependency note {u[:70]!r} is missing from {n['path'].name}" for u in n["units"] if u not in body]
    rec = plan.get("reconcile") or {"mode": None, "cells": []}
    for cell in rec["cells"] if rec["mode"] == "index-wins" else ():
        value = f"[{', '.join(cell['index'])}]" if cell["key"] == "blocks" else cell["index"]
        if f"{cell['key']}: {value}" not in read_text(cell["path"]):
            misses.append(f"reconciled {cell['key']}: {value} is missing from {cell['path'].name}")
    if read_text(index_path) != plan["index_text"]:
        misses.append(f"{index_path.name} does not match the staged text")
    return misses


def execute(plan: dict, paths: tuple, index_path: Path, json_mode: bool) -> int:
    outputs = plan["outputs"]
    try:
        staged = sup.stage_all(outputs)
    except OSError as exc:
        return say(1, f"FAIL: staging failed ({exc}); nothing on disk changed.", json_mode, err=True)
    try:
        sup.replace_all(staged)
    except sup.ReplaceError as exc:
        done = ", ".join(p.name for p in exc.done) or "none"
        return say(1, f"FAIL: replace stopped at {exc.path.name} ({exc.cause}). Replaced: {done}. "
                      "Rerun --write to resume; appended units dedup as already present.", json_mode, err=True)
    misses = verify_written(plan, paths, index_path)
    written = {d["path"] for d in plan["dests"]} | {path for path, _text in outputs}
    disk_log = sup.joined_entries([read_text(p) for p, _t in plan["changelog"]["parts"]])
    ledger = build_ledger(plan, paths, {str(p): p.stat().st_size for p in written}, misses, disk_log)
    try:
        sup.replace_all(sup.stage_all([(paths[1], json.dumps(ledger, indent=2) + "\n")]))
    except (OSError, sup.ReplaceError) as exc:
        return say(1, f"FAIL: migration written and verified={not misses}, but the ledger write failed ({exc}).",
                   json_mode, err=True)
    if json_mode:
        print(json.dumps(ledger, indent=2))
    if misses:
        return say(1, "FAIL: verification from disk found " + "; ".join(misses), json_mode, err=True)
    return say(0, f"WROTE: {paths[0].name}, ledger at {paths[1].name}; verified from disk. "
                  "Next: run generate_backlog_index.py --write.", json_mode)


def execute_outputs(outputs: list) -> int:
    """Stage and replace every (path, text) pair; returns the count written.
    Session-02's orchestrator and `--split-changelog` both call this."""
    return len(sup.replace_all(sup.stage_all(outputs)))


def plan_changelog_resplit(config: dict, index_path: Path):
    """Re-split an already-migrated changelog that has grown over budget.
    Returns None when every changelog file is already within budget, else
    `{"outputs": [...], "targets": [...], "parts": [...]}`. Session-02's
    orchestrator calls this name directly."""
    return sup.plan_changelog_resplit(config, index_path)


def _changelog_state(text: str, shape: str, index_path: Path, changelog: Path) -> str:
    if not changelog.exists():
        return "missing"
    existing = read_text(changelog)
    if _header_only(existing, index_path):
        return "header-only"
    if shape != "legacy" or sup.POINTER_RE.match(sup.FOOTER_TEXT_RE.search(text).group(0)):
        return "populated"
    planned = sup.changelog_text(sup.extract_changelog(index_path.read_bytes())["segments"], index_path.name, "\n")
    return "populated" if existing.replace("\r\n", "\n") == planned else "foreign"


def build_report(config: dict, index_path: Path) -> dict:
    """The read-only readiness report: counts, then a plan with every repair on. Never writes."""
    text = read_text(index_path)
    shape, detail = sup.classify_shape(text)
    census = list(_census(config, index_path))
    rows = []
    if shape == "legacy":
        header_idx, roles = detail
        for _line, cells in sup.iter_rows(text.split("\n"), header_idx):
            links = sup.files_links(cells[roles["file"]])[0] if len(cells) == len(roles) else []
            path = sup.resolve_item_file(links[0][1], config["_backlog_dir"], config["_archive_dir"],
                                         index_path.parent) if links else None
            if path is not None:
                rows.append((cells, path))
    referenced = {path for _cells, path in rows}
    bare = [path for path, _b, _raw, has_block in census if not has_block]
    report = {"shape": "generated" if shape == "migrated" else shape,
              "detail": detail if shape == "unrecognized" else "", "index": str(index_path),
              "changelog": _changelog_state(text, shape, index_path, artifact_paths(index_path)[0]),
              "items": {"total": len(census), "without_frontmatter": len(bare),
                        "partial_frontmatter": sum(1 for _p, _b, raw, has in census
                                                   if has and (raw is None or any(k not in raw for k in KEYS))),
                        "unreferenced_without_frontmatter": sum(1 for path in bare if path not in referenced)},
              "dependencies": {"bare_edges": 0, "edges_missing_from_blocks": 0, "soft_dependency_bullets": 0,
                               "unrecognised_lines": 0},
              "row_mismatches": 0, "ready_with_all_repairs": shape == "migrated",
              "would_refuse": [detail] if shape == "unrecognized" else []}
    changelog_path = artifact_paths(index_path)[0]
    if changelog_path.exists():
        files = sup.changelog_budget_status(config, index_path)
        report["changelog_files"] = files
        report["changelog_over_budget"] = any(f["level"] != "OK" for f in files)
    if shape != "legacy":
        return report
    report["detail"] = "hand-authored index; columns: " + ", ".join(sorted(roles, key=roles.get))
    problems, edges, found = chk.scan_index(text, header_idx, extract_notes=True)
    blocks = {}
    for _p, _b, raw, _h in census:
        if raw and "id" in raw:
            blocks[(sup.ids_in(raw["id"]) or [""])[0]] = sup.ids_in(raw.get("blocks", ""))
    report["dependencies"] = {"bare_edges": len(edges),
                              "edges_missing_from_blocks": sum(1 for _l, s, d in edges if d not in blocks.get(s, [])),
                              "soft_dependency_bullets": sum(1 for f in found if f["kind"] == "bullet"),
                              "unrecognised_lines": len(problems)}
    for cells, path in rows:
        try:
            report["row_mismatches"] += len(sup.row_diffs(cells, roles, gen._scan_one_file(path)))
        except gen.GeneratorError:
            continue
    try:
        plan_migration(config, index_path, text, detail, RepairOptions.all_on())
        report["ready_with_all_repairs"] = True
    except Refusal as exc:
        report["would_refuse"] = [str(exc)]
    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="migrate_backlog_index.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=None, help="Path to config.yaml; overrides default search.")
    p.add_argument("--dry-run", action="store_true", help="Report the plan; write nothing (default behavior).")
    p.add_argument("--write", action="store_true", help="Perform the migration.")
    p.add_argument("--json", action="store_true", help="Emit the plan or ledger as JSON on stdout only.")
    p.add_argument("--force", action="store_true", help="Proceed on a dirty working tree.")
    p.add_argument("--allow-untracked-tree", action="store_true",
                   help="Proceed when git cannot vouch for the tree (no repo, git error, no git, or ignored inputs).")
    p.add_argument("--append-ambiguous", action="store_true",
                   help="Append AMBIGUOUS dedup units instead of refusing.")
    p.add_argument("--thresholds", default=f"{sup.DEFAULT_HIGH},{sup.DEFAULT_LOW}",
                   help="'high,low' similarity thresholds, 0 <= low < high <= 1.")
    p.add_argument("--backfill-frontmatter", action="store_true",
                   help="Fill a missing frontmatter block or missing keys from the index row, file name and git.")
    p.add_argument("--write-edges", action="store_true",
                   help="Write each '## Dependencies' edge into its item's frontmatter blocks:.")
    p.add_argument("--extract-dependency-notes", action="store_true",
                   help="Move soft-dependency bullets under '## Dependencies' into their owning item files.")
    p.add_argument("--reconcile", choices=RECONCILE_MODES, default=None,
                   help="Settle a row/frontmatter disagreement: the row's value wins, or the frontmatter's.")
    p.add_argument("--report", action="store_true",
                   help="Print a read-only JSON shape and readiness report; never writes; exit 0.")
    p.add_argument("--split-changelog", action="store_true",
                   help="Re-split an already-migrated changelog that has grown over budget; "
                        "a no-op when every part is already within budget.")
    return p


def options_from_args(args) -> RepairOptions:
    return RepairOptions(
        backfill_frontmatter=getattr(args, "backfill_frontmatter", False),
        write_edges=getattr(args, "write_edges", False),
        extract_dependency_notes=getattr(args, "extract_dependency_notes", False),
        reconcile=getattr(args, "reconcile", None), append_ambiguous=getattr(args, "append_ambiguous", False),
        high=getattr(args, "high", sup.DEFAULT_HIGH), low=getattr(args, "low", sup.DEFAULT_LOW))


def run_split_changelog(config: dict, index_path: Path, args, js: bool) -> int:
    """The `--split-changelog` path: valid only on a `migrated` index. No
    other plan step runs."""
    text = read_text(index_path)
    shape, _detail = sup.classify_shape(text)
    if shape != "migrated":
        return say(2, "REFUSED: --split-changelog requires a migrated index -- run the migration first",
                   js, err=True)
    plan = plan_changelog_resplit(config, index_path)
    if plan is None:
        return say(0, "changelog within budget", js)
    if not args.write:
        if js:
            print(json.dumps({"targets": [str(p) for p in plan["targets"]], "parts": plan["parts"]}, indent=2))
        else:
            print("\n".join(f"would write {p.name}" for p, _t in plan["outputs"]))
        return say(1, "DRY-RUN: changelog split needed; no files written.", js)
    try:
        written = execute_outputs(plan["outputs"])
    except OSError as exc:
        return say(1, f"FAIL: staging failed ({exc}); nothing on disk changed.", js, err=True)
    except sup.ReplaceError as exc:
        done = ", ".join(p.name for p in exc.done) or "none"
        return say(1, f"FAIL: replace stopped at {exc.path.name} ({exc.cause}). Replaced: {done}.", js, err=True)
    return say(0, f"WROTE: {written} changelog part(s), re-split within budget.", js)


def run(config: dict, args) -> int:
    """Run one migration, or the `--report`/`--split-changelog`, for an
    already-loaded `config` and parsed `args`."""
    js = args.json
    index_path = config["_index_path"]
    if not index_path.exists():
        return say(2, f"REFUSED: index not found at {index_path}", js, err=True)
    if getattr(args, "report", False):
        print(json.dumps(build_report(config, index_path), indent=2))
        return 0
    if getattr(args, "split_changelog", False):
        return run_split_changelog(config, index_path, args, js)

    inputs = [index_path, *sorted(config["_backlog_dir"].glob("*.md")), *sorted(config["_archive_dir"].glob("*.md"))]
    dirty, reason = chk.git_state(config["_project_root"], inputs)
    if dirty is None and not args.allow_untracked_tree:
        return say(2, f"REFUSED: cannot determine the working-tree state -- {reason}. Commit the index "
                      "and item files to git first, or pass --allow-untracked-tree.", js, err=True)
    if dirty is None:
        say(0, f"WARNING: proceeding without a git safety net -- {reason}.", js, err=True)

    text = read_text(index_path)
    shape, detail = sup.classify_shape(text)
    if shape == "unrecognized":
        return say(2, f"REFUSED: unrecognised index shape -- {detail}", js, err=True)
    if shape == "migrated":
        return say(0, "CLEAN: index is already in the generated shape; nothing to do.", js)

    paths = artifact_paths(index_path)
    try:
        plan = plan_migration(config, index_path, text, detail, options_from_args(args))
    except Refusal as exc:
        return say(2, f"REFUSED: {exc}", js, err=True)
    if plan is None:
        return say(0, f"CLEAN: already migrated -- the footer points to {paths[0].name} and every row's "
                      "prose is in its item file. Next: run generate_backlog_index.py --write.", js)
    refusal = chk.tree_gate(dirty, plan, paths, index_path, args.force)
    if refusal:
        return say(2, f"REFUSED: {refusal}", js, err=True)
    if not args.write:
        print(json.dumps(build_ledger(plan, paths), indent=2) if js else format_report(plan))
        return say(1, "DRY-RUN: migration needed; no files written.", js)
    return execute(plan, paths, index_path, js)


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
        return say(2, "REFUSED: --report and --write are mutually exclusive; --report never writes.", js, err=True)
    if args.report and args.split_changelog:
        return say(2, "REFUSED: --report and --split-changelog are mutually exclusive.", js, err=True)
    try:
        high_s, low_s = args.thresholds.split(",")
        args.high, args.low = float(high_s), float(low_s)
    except ValueError:
        return say(2, f"REFUSED: --thresholds must be 'high,low' floats, got {args.thresholds!r}.", js, err=True)
    if not 0 <= args.low < args.high <= 1:
        return say(2, f"REFUSED: --thresholds needs 0 <= low < high <= 1, got high={args.high}, low={args.low}.",
                   js, err=True)
    return run(load_config(Path(__file__)), args)


if __name__ == "__main__":
    sys.exit(main())
