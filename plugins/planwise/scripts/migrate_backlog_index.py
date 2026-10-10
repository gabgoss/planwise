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
JSON readiness report instead, planned as the upgrade plans it, with the
parked count; it never writes and always exits 0. The
changelog is written as budgeted numbered parts, and `--split-changelog`
re-splits one that has grown over budget.

Recognise-or-refuse, never best-effort. Before any write, the run refuses
(exit 2) and names the cause when: the shape, a column or a `##` section is
not recognised; a Shards or Dependencies table or row is not recognised;
a Blocks cell or Dependencies row uses an id prefix the items table does
not write, compared case-insensitively over every items row; a Dependencies
row names its own item; relocated index text measures at or over the page
cap as one changelog entry; a `## Dependencies`
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
file with no frontmatter and no index row, an unparseable frontmatter
block, and a reciprocal edge.

Index text that regeneration would drop is relocated, never refused: a
preamble line, text between the heading and its table, text after the
table, text under `## Shards` or `## Dependencies`, an unrecognised
section, a soft-dependency bullet whose owner has no item file, and a row
whose Files cell resolves no item file. Each lands byte-exact in one dated
changelog entry, and the ledger's `relocated_index_lines` lists it. A run
resumed on a later day reuses the date of the entry already written.

Dedup: a unit is ALREADY-PRESENT only when its whole strict form (case
folded, whitespace collapsed, emphasis stripped) occurs in one paragraph
of the item file or of the appends already planned for it. Similarity
alone yields AMBIGUOUS. `/planwise upgrade` and `/planwise init` plan with
`park_ambiguous`: each AMBIGUOUS unit is kept verbatim in the ledger's
`parked_ambiguous` list, counted as accounted, and appended nowhere. This
CLI never parks, and `--append-ambiguous` wins over parking. A Files-cell link after the first is carried into
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
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_backlog_index as gen
import migrate_backlog_checks as chk
import migrate_backlog_relocate as reloc
import migrate_backlog_repairs as repairs
import migrate_backlog_support as sup
from config_loader import load_config
from reconcile_common import read_text_preserving_newlines as read_text

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
    park_ambiguous: bool = False  # keep AMBIGUOUS units in the ledger; `append_ambiguous` wins over it
    abbrev_precedence: bool = False  # settle each abbrev by file name, then frontmatter, then cell (`abbrev_prepass`)
    high: float = sup.DEFAULT_HIGH
    low: float = sup.DEFAULT_LOW

    @classmethod
    def all_on(cls, reconcile: str = "index-wins") -> "RepairOptions":
        return cls(backfill_frontmatter=True, write_edges=True, extract_dependency_notes=True, reconcile=reconcile)

    @classmethod
    def unattended(cls, reconcile: str = "index-wins") -> "RepairOptions":
        """Every repair on, AMBIGUOUS units parked, and each abbrev settled by precedence: what
        `/planwise upgrade` and `init` run."""
        return cls(backfill_frontmatter=True, write_edges=True, extract_dependency_notes=True, reconcile=reconcile,
                   park_ambiguous=True, abbrev_precedence=True)


def _today() -> str:
    """Today's local date, ISO form."""
    return datetime.now().astimezone().date().isoformat()


def say(code: int, msg: str, json_mode: bool, err: bool = False) -> int:
    print(msg, file=sys.stderr if (err or json_mode) else sys.stdout)
    return code


def artifact_paths(index_path: Path):
    """Return (changelog, ledger, older changelog name used by earlier versions).

    The changelog name comes from `gen._changelog_filename` -- the SAME
    namer `generate_backlog_index.py`'s own hub footer uses, so the two
    scripts can never disagree on the changelog's name.
    """
    naming = gen._index_naming(index_path)
    changelog = index_path.with_name(gen._changelog_filename(naming))
    ledger = index_path.with_name(f"00-{naming.archive_stem}-Migration-Ledger.json")
    older = index_path.with_name(f"{index_path.stem}-Changelog{index_path.suffix}")
    return changelog, ledger, older


def _text(texts: dict, path: Path) -> str:
    """The planned text of `path`, else its text on disk."""
    return texts[path] if path in texts else read_text(path)


_header_only = sup.header_only_changelog


def _census(config: dict, index_path: Path):
    """Yield (resolved path, text, raw frontmatter map, has_block) for every item file the generator scans."""
    for path in gen._iter_item_files(config["_backlog_dir"], config["_archive_dir"], index_path):
        body = read_text(path)
        raw, has_block, _bom, _nl = repairs.partial_frontmatter(body)
        yield path.resolve(), body, raw, has_block


def _non_numeric_hint(message: str, config: dict, index_path: Path, view: dict, backfill_hint: bool) -> str:
    """The fix for the generator's "non-numeric id value" refusal, worded by the key that carries
    the value: `--backfill-frontmatter` normalises a prefixed `id:`, but never a `blocks:` entry."""
    m = re.search(r"non-numeric id value (['\"])(.*)\1", message)
    value = m.group(2).strip().strip("\"'") if m else ""
    raws = [(path, repairs.partial_frontmatter(view.get(path, body))[0] or {})
            for path, body, _raw, _has in _census(config, index_path)] if value else []
    if any(value == str(raw.get("id", "")).strip().strip("\"'") for _p, raw in raws):
        return (" -- add --backfill-frontmatter to normalise an id: of the form {PREFIX}-{NNN}[-{NN}] that "
                "matches its file name and index row") if backfill_hint else ""
    owner = next((path for path, raw in raws if value in str(raw.get("blocks", ""))), None)
    if owner is not None:
        return (f" -- {owner.name} has blocks: entry {value!r}, which is not a bare item id. "
                "--backfill-frontmatter does not rewrite blocks: entries, so fix it by hand, then re-run")
    return ""


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
        elif "non-numeric id value" in str(exc):
            hint = _non_numeric_hint(str(exc), config, index_path, view, backfill_hint)
        fix = hint.removeprefix(" -- ") or "correct the item file the message names so the generator accepts it, then re-run"
        raise Refusal(f"the generator would refuse this tree: {exc}", fix) from exc
    if reciprocal:
        pairs = ", ".join(f"{a}<->{b}" for a, b in reciprocal)
        a, b = reciprocal[0]
        question = {"id": "reciprocal-edge",
                    "prompt": f"Items {a} and {b} each block the other. Keep which direction?",
                    "options": [{"label": f"{a} blocks {b}", "answer": {"drop": f"{b}->{a}"}},
                                {"label": f"{b} blocks {a}", "answer": {"drop": f"{a}->{b}"}},
                                {"label": "Drop both", "answer": {"drop": "both"}}],
                    "pairs": [[x, y] for x, y in reciprocal]}
        raise Refusal(f"the generator would refuse to write: reciprocal blocks edge(s) {pairs}",
                      "keep one direction: remove the other item's id from one of the two blocks: lists, then re-run",
                      question=question)
    return {item["_path"].resolve(): item for item in items}


def resolve_rows(text: str, header_idx: int, roles: dict, config: dict, index_path: Path, relocated: list) -> list:
    """Resolve each row's Files cell to its item file; refuse a row this tool cannot read. A row
    whose Files cell resolves no item file is appended to `relocated` whole and left out."""
    rows = []
    for line_no, cells in sup.iter_rows(text.split("\n"), header_idx):
        where = f"row at line {line_no + 1}"
        if len(cells) != len(roles):
            raise Refusal(f"{where}: {len(cells)} cell(s) but the header has {len(roles)}",
                          "repair the row so it has the header's cell count; a pipe character inside backticks "
                          "is the usual cause")
        if not cells[roles["id"]].strip():
            raise Refusal(f"{where}: empty ID cell", "write the item's id in the ID cell, or delete the row")
        links, leftover = sup.files_links(cells[roles["file"]])
        if leftover:
            raise Refusal(f"{where}: Files cell carries text other than links, {cells[roles['file']]!r}",
                          "replace the Files cell with the item-file link only")
        path = sup.resolve_item_file(links[0][1], config["_backlog_dir"], config["_archive_dir"],
                                     index_path.parent) if links else None
        if path is None:
            relocated.append({"line": line_no + 1, "kind": "row without an item file",
                              "text": text.split("\n")[line_no].rstrip("\r")})
            continue
        rows.append({"line": line_no, "cells": cells, "path": path, "links": links})
    return rows


def collect_rows(resolved: list, roles: dict, index_path: Path, items: dict, valid_abbrevs=None):
    """Return (rows with their prose units, cell/frontmatter disagreements).
    An Abbrev cell that is not a usable abbrev per `valid_abbrevs` is no disagreement."""
    rows, diffs = [], []
    for row in resolved:
        path, cells, links = row["path"], row["cells"], row["links"]
        fields = items.get(path)
        if fields is None:
            raise Refusal(f"row at line {row['line'] + 1}: {path.name} is not an item file the generator scans",
                          "rename the file to the item-file pattern the generator scans, or move it out of the "
                          "backlog directory")
        diffs += [{**diff, "id": fields["id"], "path": path}
                  for diff in sup.row_diffs(cells, roles, fields, valid_abbrevs)]
        extra = [sup.link_unit(t, h, index_path.parent, path.parent) for t, h in links[1:]
                 if h.strip() != links[0][1].strip()]
        rows.append({"id": fields["id"], "path": path, "links": extra,
                     "units": sup.row_units(cells[roles["feature"]], fields["title"])})
    return rows, diffs


def _cell(row: dict, roles: dict, role: str) -> str:
    return sup.plain(row["cells"][roles[role]]) if role in roles else ""


def retarget_cell(line: str, cell: str, value: str) -> str:
    """`line`, a table row, with its first cell that equals `cell` rewritten to `value`."""
    return re.sub(rf"(\|\s*){re.escape(cell)}(\s*\|)", lambda m: f"{m.group(1)}{value}{m.group(2)}", line, count=1)


def _name_win(wins: list, path: Path, item_id: str, key: str, cell: str, value: str) -> None:
    """Record that the file name's `value` settled a disagreement with the index `cell`."""
    wins.append({"id": item_id, "key": key, "frontmatter": None, "index": cell, "winner": "file-name",
                 "written": value, "path": path})


def _settled_by_name(diffs: list, resolved: list, roles: dict, wins: list, prior: list) -> list:
    """`diffs` less each disagreement already settled, which joins `wins` instead: an ID cell that
    disagrees with an `id:` equal to the file name's own id, and a cell that disagrees with a value
    `prior` (an interrupted run's journal) records as a win. A resumed run then keeps what the
    interrupted run wrote, as a clean run would have."""
    recorded = {(str(Path(w["path"]).resolve()), w["key"]): w for w in prior if isinstance(w, dict) and "path" in w}
    kept = []
    for d in diffs:
        won = recorded.get((str(Path(d["path"]).resolve()), d["key"]))
        if d["key"] == "id" and repairs.first_id_in(d["path"].stem) == d["frontmatter"]:
            winner = "file-name"
        elif won is not None and won.get("written") == d["frontmatter"]:
            winner = won.get("winner") or "file-name"
        else:
            kept.append(d)
            continue
        row = next(r for r in resolved if r["path"] == d["path"])
        cell = row["cells"][roles["id"]].strip() if d["key"] == "id" else d["row"]
        wins.append({"id": d["id"], "key": d["key"], "frontmatter": d["frontmatter"], "index": cell,
                     "winner": winner, "written": d["frontmatter"], "path": d["path"]})
    return kept


def _abbrev_record(config: dict, decisions: dict | None) -> dict:
    """The ledger's `abbreviations` section: each name `abbrev_prepass` added to config.yaml, and each
    value a case-insensitive match settled to its configured key."""
    matched = [{"from": d["decision"]["from"], "to": d["decision"]["value"]} for d in (decisions or {}).values()
               if d["decision"] and d["decision"]["source"] == "config-match"]
    return {"added": list(config.get("_abbrevs_added") or []), "matched": matched}


def _abbrev(row: dict, roles: dict, path: Path, config: dict, where: str, wins: list) -> str:
    valid = sup.configured_abbrevs(config)
    seg, cell = (repairs.filename_fields(path.name) or (None, None))[1], _cell(row, roles, "abbrev")
    usable = [v for v in (seg, cell) if sup.abbrev_usable(v, valid)]
    if len(set(usable)) > 1:  # the file name's segment comes first in `usable`
        _name_win(wins, path, repairs.first_id_in(path.stem) or "", "abbrev", cell, usable[0])
        return usable[0]
    unconfigured = sorted({v for v in (seg, cell) if sup.abbrev_usable(v, None)} - (valid or set()))
    if not usable and valid is not None and unconfigured:
        names = " and ".join(unconfigured)
        raise Refusal(f"{where}: its abbrev {names} is not in config.yaml abbreviations: -- add {names} to "
                      "abbreviations: in config.yaml, then re-run")
    return usable[0] if usable else ""


ABBREV_DESCRIPTION = "{} (added by the upgrade; edit the description)"


def abbrev_decisions(resolved: list, roles: dict, configured) -> dict:
    """{item path: its settled abbrev} for each item an index row names: `sup.decide_abbrev` over the
    file name's segment, the frontmatter `abbrev:` read from disk and the Abbrev cell, against
    `configured`. Each value carries those three inputs by source name, `frontmatter` None when the
    item has no `abbrev:` key and `index` "" when the cell carries no abbrev, plus the item's id."""
    out = {}
    for row in resolved:
        path = row["path"]
        if path in out:
            continue
        raw = repairs.partial_frontmatter(read_text(path))[0] or {}
        values = {"file-name": (repairs.filename_fields(path.name) or (None, None))[1],
                  "frontmatter": str(raw.get("abbrev") or "").strip().strip("\"'") if "abbrev" in raw else None,
                  "index": sup.abbrev_token(_cell(row, roles, "abbrev"))}
        out[path] = {**values, "id": repairs.first_id_in(path.stem) or "",
                     "decision": sup.decide_abbrev(*values.values(), configured)}
    return out


def _base_abbrevs(config: dict):
    """The configured keys an abbrev is judged against: those `abbrev_prepass` saw, else the config's."""
    return config["_abbrevs_before"] if "_abbrevs_before" in config else sup.configured_abbrevs(config)


def abbrev_prepass(config: dict, detail: tuple, text: str, index_path: Path, pending=()) -> tuple:
    """Settle every indexed item's abbrev against the configured keys, less `pending` (names an
    interrupted run already added), and return (plan config, added). The plan config records those
    keys as `_abbrevs_before`, every winning name no key holds as `_abbrevs_added`, and the new names
    under `abbreviations:`. `added` lists (name, description) for each name config.yaml lacks. A name
    that loses is never added. Nothing is written. Raises `Refusal` when a name must be added but
    config.yaml cannot take it; a row it cannot read is left for the plan to name."""
    current = sup.configured_abbrevs(config) or set()
    base = (current - set(pending)) or None
    unchanged = ({**config, "_abbrevs_before": base}, [])
    header_idx, roles = detail
    try:
        rows = resolve_rows(text, header_idx, roles, config, index_path, [])
    except Refusal:
        return unchanged
    decisions = abbrev_decisions(rows, roles, base)
    winners = {}
    for path, d in decisions.items():
        if d["decision"] and d["decision"]["appended"]:
            winners.setdefault(d["decision"]["value"], []).append(path.name)
    configured = config.get("abbreviations")
    if not winners or not isinstance(configured, dict):
        return unchanged
    added = [(name, ABBREV_DESCRIPTION.format(name)) for name in winners if name not in current]
    words = [name for name, _d in added if name in sup.YAML_WORDS]
    if words:
        files = ", ".join(f for name in words for f in winners[name])
        raise Refusal(f"the upgrade would add {', '.join(words)} to abbreviations: in config.yaml, but YAML reads "
                      "it bare as a boolean or null and the fallback config reader skips a quoted key",
                      f"rename that abbreviation in {files} (its file name segment, abbrev: line or Abbrev cell), "
                      f"or add it to abbreviations: in config.yaml by hand as a quoted key")
    if added:  # the splice it will make must be possible before anything is written
        sup.splice_abbreviations((Path(config["_planwise_root"]) / "config.yaml").read_bytes(), added)
    return ({**config, "abbreviations": {**configured, **dict(added)}, "_abbrevs_before": base,
             "_abbrevs_added": list(winners)}, added)


def plan_abbrevs(decisions: dict, texts: dict) -> list:
    """Write each settled abbrev over an `abbrev:` line that differs, into `texts` (an item without the
    key gets it from the backfill), and return one reconcile cell for each item whose file name,
    frontmatter or Abbrev cell disagreed with it, `winner` naming the source that settled it."""
    cells = []
    for path, d in decisions.items():
        if d["decision"] is None:
            continue
        value, seg, fm, cell = d["decision"]["value"], d["file-name"], d["frontmatter"], d["index"]
        if fm is not None and fm != value:
            texts[path] = repairs.replace_key_line(_text(texts, path), "abbrev", value)
        if (seg and seg != value) or (fm is not None and fm != value) or (cell and cell != value):
            cells.append({"id": d["id"], "key": "abbrev", "frontmatter": fm, "index": cell,
                          "winner": d["decision"]["source"], "written": value, "path": path})
    return cells


def _source_values(keys: list, row: dict, roles: dict, path: Path, config: dict, dates: dict, wins: list,
                   abbrevs: dict | None = None):
    """Return ({key: value} for `keys`, the created-date source or None). Where the file name and the
    index cell disagree on an id or abbrev, the file name wins and `wins` records the cell; an abbrev
    comes from `abbrevs` (`abbrev_decisions`) instead when given. Refuses rather than guess otherwise."""
    where = f"{path.name} (row at line {row['line'] + 1})"
    values, source = {}, None
    for key in keys:
        if key == "abbrev" and abbrevs is not None:
            decided = abbrevs[path]["decision"]
            values[key] = decided["value"] if decided else ""
        elif key == "id":
            ids, named = sup.row_ids(row["cells"][roles["id"]]), repairs.first_id_in(path.stem)
            if named is None and len(ids) != 1:
                raise Refusal(f"{where}: the ID cell names {ids or 'no id'} and the file name carries no id",
                              "rename the file to carry its id, or leave exactly one id in the ID cell")
            if named is not None and ids != [named]:
                _name_win(wins, path, named, "id", row["cells"][roles["id"]].strip(), named)
            values[key] = named if named is not None else ids[0]
        elif key == "title":
            values[key] = repairs.title_from_cell(row["cells"][roles["feature"]])
        elif key == "abbrev":
            values[key] = _abbrev(row, roles, path, config, where, wins)
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


def _repair_id(path: Path, body: str, raw: dict, row: dict | None, roles: dict, texts: dict,
               id_repairs: list) -> str:
    """Normalise an `id:` of the form "{PREFIX}-{NNN}[-{NN}]" to "{NNN}" in `texts`, and return
    the file's text. Refuses when that id does not name this file and its index row."""
    value = str(raw["id"])
    prefix, row_id, sub = (sup.row_id_parts(row["cells"][roles["id"]]) if row is not None else None) or (None,) * 3
    try:
        fixed = repairs.bare_id(value, path.name, row_id, prefix, sub)
    except ValueError as exc:
        raise Refusal(f"{path.name}: {exc} -- fix its id: line by hand, then re-run") from exc
    if fixed is None:
        return body
    texts[path] = repairs.replace_key_line(body, "id", fixed)
    raw["id"] = fixed
    id_repairs.append({"path": path, "from": value, "to": fixed})
    return texts[path]


def plan_backfill(resolved: list, roles: dict, config: dict, index_path: Path, texts: dict,
                  id_repairs: list | None = None, wins: list | None = None, abbrevs: dict | None = None) -> list:
    """Plan frontmatter for every scanned item file that lacks a block or keys, into `texts`.
    An `id:` of the form "{PREFIX}-{NNN}[-{NN}]" is normalised first; each such repair is
    appended to `id_repairs`. Each id or abbrev the file name settled against its index cell
    is appended to `wins`. A missing abbrev comes from `abbrevs` when given."""
    id_repairs = [] if id_repairs is None else id_repairs
    wins = [] if wins is None else wins
    by_path = {}
    for row in resolved:
        by_path.setdefault(row["path"], row)
    todo = []
    for path, body, raw, has_block in _census(config, index_path):
        if has_block and raw is None:
            raise Refusal(f"{path.name}: its frontmatter block does not close or cannot be parsed -- "
                          "fix it by hand, then re-run")
        if raw is not None and "id" in raw:
            body = _repair_id(path, body, raw, by_path.get(path), roles, texts, id_repairs)
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
        values, source = _source_values(missing, row, roles, path, config, dates, wins, abbrevs)
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
    stuck = [d for d in diffs if d["prose"] or (mode == "index-wins" and d["row"] in (None, ""))]
    if stuck:
        raise Refusal(f"{len(stuck)} row cell(s) disagree with item frontmatter and --reconcile {mode} cannot "
                      f"settle them: {'; '.join(d['message'] for d in stuck[:10])}",
                      "make each named cell and its frontmatter key agree by hand, then re-run")
    for d in diffs:
        if mode == "index-wins":
            value = f"[{', '.join(d['row'])}]" if d["key"] == "blocks" else d["row"]
            texts[d["path"]] = repairs.replace_key_line(_text(texts, d["path"]), d["key"], value)
            items[d["path"]][d["key"]] = d["row"]
    return [{"id": d["id"], "key": d["key"], "frontmatter": d["frontmatter"], "index": d["row"], "path": d["path"]}
            for d in diffs]


def plan_dedup(rows: list, high: float, low: float, append_ambiguous: bool, texts: dict | None = None,
               park_ambiguous: bool = False) -> list:
    """Classify every row unit against its item file. An AMBIGUOUS unit is appended under
    `append_ambiguous`, else parked (kept for the ledger, never appended) under
    `park_ambiguous`, else refused by name."""
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
        dest["append"], dest["dedup"], dest["ambiguous"], dest["prior"], dest["parked"] = [], [], [], [], []
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
                    if park_ambiguous:
                        dest["parked"].append({"row": row_id, "unit": unit, "label": label,
                                               "similarity": round(max(score, window), 2)})
                        continue
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


def remainder_bullet(note: dict) -> str:
    """A `## Dependencies` row note as a bullet that names the targets it was written beside."""
    targets = f"{', '.join(note['targets'])}: " if note["targets"] else ""
    return f"- {targets}{note['text']}"


def plan_notes(bullets: list, items: dict, texts: dict, relocated: list) -> list:
    """Append each soft-dependency bullet to its owner's dependency-notes section in `texts`.
    A bullet whose owner has no item file is appended to `relocated` instead."""
    owners = {item["id"]: path for path, item in items.items()}
    grouped = {}
    for bullet in bullets:
        path = owners.get(bullet["owner"])
        if path is None:
            relocated.append({"line": bullet["line"], "kind": "unknown-owner bullet", "text": bullet["text"]})
            continue
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


def plan_changelog(text: str, index_path: Path, changelog_path: Path, pending: int, naming,
                   relocated: str | None = None):
    """Return the multi-part changelog plan, or None when the index is
    already migrated. A changelog holding only its backlink
    line is treated as absent. `plan["parts"]` is `[(path, text), ...]`,
    part 1 first. A `relocated` entry is written as the first segment."""
    footer = sup.FOOTER_TEXT_RE.search(text).group(0)
    pointer = sup.POINTER_RE.match(footer)
    if pointer:
        if changelog_path.name not in (pointer.group(1), pointer.group(2)):
            raise Refusal(f"the footer points to {pointer.group(2)}, expected {changelog_path.name}",
                          f"point the footer at {changelog_path.name}, then re-run")
        if not changelog_path.exists():
            raise Refusal(f"the footer says the changelog moved to {changelog_path.name}, but that "
                          "file is missing -- restore it from version control")
        if pending:
            raise Refusal(f"half-migrated: the footer already points to {changelog_path.name}, but "
                          f"{pending} unit(s) of row prose or item-file repairs are not in their item files. An "
                          "interrupted older run or a hand edit left this state -- restore from version control")
        return None
    extracted = sup.extract_changelog(index_path.read_bytes())
    if relocated:
        entry = relocated.encode("utf-8")
        extracted = {**extracted, "segments": [entry, *extracted["segments"]],
                     "entry_content_bytes": extracted["entry_content_bytes"] + len(entry)}
    split =sup.check_parts_budget(sup.split_changelog(extracted["segments"], naming, index_path.name,
                                                       sup.newline_of(text)))
    pattern = sup.changelog_part_pattern(naming)
    max_planned = len(split)
    for p in index_path.parent.iterdir():
        m = pattern.match(p.name)
        if m and int(m.group(1)) > max_planned:
            raise Refusal(f"{p.name} exists beyond the planned {max_planned} changelog part(s) -- a stale "
                          "part would silently shadow the real ones; remove it or restore the index from "
                          "version control")
    part1_path = index_path.with_name(split[0][0])
    header_only = part1_path.exists() and _header_only(read_text(part1_path), index_path)
    plan = {**extracted, "resumed": False, "header_only": header_only}
    parts = []
    for k, (name, part_text) in enumerate(split):
        part_path = index_path.with_name(name)
        if part_path.exists() and not (k == 0 and header_only):
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


def _refuse_unusable_abbrevs(texts: dict, valid) -> None:
    """Refuse when a planned text sets an `abbrev:` that differs from the file's own on disk and
    is not a usable abbrev: the migrator never writes an unconfigured abbrev."""
    def abbrev_of(text: str) -> str:
        return str((repairs.partial_frontmatter(text)[0] or {}).get("abbrev", "")).strip().strip("\"'")

    for path, planned in texts.items():
        value = abbrev_of(planned)
        if value != abbrev_of(read_text(path)) and not sup.abbrev_usable(value, valid):
            raise Refusal(f"{path.name}: the migration would write abbrev: {value!r}, which is not a configured "
                          "abbreviation -- set its abbrev: by hand, or add it to abbreviations: in config.yaml, "
                          "then re-run")


def _journal(ledger_path: Path) -> dict:
    """The in-progress journal at the ledger path, or {} when the path holds none."""
    try:
        data = json.loads(read_text(ledger_path))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) and data.get("mode") == sup.JOURNAL_MODE else {}


def pending_abbrevs(ledger_path: Path) -> list:
    """The names an interrupted run recorded as added to config.yaml, read from its journal."""
    return list((_journal(ledger_path).get("abbreviations") or {}).get("added") or [])


def record_pending_abbrevs(ledger_path: Path, abbreviations: dict) -> None:
    """Write a journal naming the abbreviations this run is about to add to config.yaml. A caller
    writes it before it edits config.yaml, so a run killed after that edit still logs the names and
    puts them in its ledger. It lists no targets, so it never reads as an interrupted migrator write."""
    journal = {"mode": sup.JOURNAL_MODE, "targets": [], "parked_ambiguous": [], "abbreviations": abbreviations}
    sup.replace_all(sup.stage_all([(ledger_path, json.dumps(journal, indent=2) + "\n")]))


def interrupted_journal(ledger_path: Path) -> int | None:
    """None unless the index is already migrated but the ledger path still holds the in-progress
    journal: the run stopped after replacing the index and before writing its ledger, so that
    journal is the only record of what it did. Returns the parked units it holds."""
    if not sup.journal_paths(ledger_path):
        return None
    try:
        return len(json.loads(read_text(ledger_path)).get("parked_ambiguous") or [])
    except (OSError, ValueError, AttributeError):
        return 0


def settle_interrupted_journal(ledger_path: Path) -> Path:
    """Rename the in-progress journal to `{stem}-Interrupted-{date}.json` (numeric suffix when that
    name is taken), keeping every byte of it, then write a ledger at the old path that names the new
    file. Returns the renamed path. The caller backs the journal up first."""
    day = _today()
    parked = interrupted_journal(ledger_path) or 0
    abbreviations = _journal(ledger_path).get("abbreviations") or {"added": [], "matched": []}
    renamed = ledger_path.with_name(f"{ledger_path.stem}-Interrupted-{day}.json")
    n = 1
    while renamed.exists():
        n += 1
        renamed = ledger_path.with_name(f"{ledger_path.stem}-Interrupted-{day}-{n}.json")
    ledger_path.rename(renamed)
    note = {"run_date": day, "mode": "journal-renamed", "journal_renamed_to": str(renamed),
            "parked_units_in_journal": parked, "abbreviations": abbreviations,
            "note":"an earlier run replaced the index and stopped before it wrote its ledger. Its journal is "
                    "kept under the name above. The index was already migrated, so this run planned no "
                    f"migration and did not re-derive anything. The {parked} parked unit(s) remain verbatim in "
                    "the renamed journal and need review there."}
    sup.replace_all(sup.stage_all([(ledger_path, json.dumps(note, indent=2) + "\n")]))
    return renamed


def build_plan(text: str, detail: tuple, config: dict, index_path: Path, paths: tuple, options: RepairOptions):
    header_idx, roles = detail
    problems, edges, found = chk.scan_index(text, header_idx, extract_notes=options.extract_dependency_notes)
    movable, problems = reloc.split_problems(problems)
    relocated = reloc.collect_relocations(movable, text.split("\n"))
    scanned = {record["line"] - 1 for record in relocated}  # index lines the plan removes after relocating them
    if problems:
        fixes = []
        if any(chk.FOREIGN_PREFIX in p for p in problems):
            written = " or ".join(f"{p}-" for p in sorted(chk.items_prefixes(text.split("\n"), header_idx)))
            fixes.append("write the cell with the items table's prefix or as bare digits "
                         f"(the items table writes {written or 'bare digits'})")
        if any(chk.SELF_EDGE in p for p in problems):
            fixes.append("remove the row's own id from its Blocks cell, because an item cannot block itself")
        if any(chk.FOREIGN_PREFIX not in p and chk.SELF_EDGE not in p for p in problems):
            flag_closes = (not options.extract_dependency_notes  # a Dependencies row note is still refused without it
                           and len(reloc.split_problems(chk.scan_index(text, header_idx, True)[0])[1]) < len(problems))
            fixes.append("add --extract-dependency-notes to move the soft-dependency bullets into their owning item files"
                         if flag_closes else "move each named line into an item file or the changelog by hand, then re-run")
        raise Refusal("content regeneration would drop and this tool does not move: " + "; ".join(problems),
                      "; ".join(fixes))
    changelog_path, _ledger, older = paths
    if older != changelog_path and older.exists():
        raise Refusal(f"{older.name} exists from an earlier version of this tool, and the generator "
                      f"would scan it as an item file -- rename it to {changelog_path.name}")
    resolved = resolve_rows(text, header_idx, roles, config, index_path, relocated)
    texts, id_repairs, wins = {}, [], []
    decisions = abbrev_decisions(resolved, roles, _base_abbrevs(config)) if options.abbrev_precedence else None
    backfill = (plan_backfill(resolved, roles, config, index_path, texts, id_repairs, wins, decisions)
                if options.backfill_frontmatter else [])
    abbrev_cells = plan_abbrevs(decisions, texts) if decisions is not None else []
    wins += abbrev_cells
    no_backfill = not options.backfill_frontmatter
    edge_plan = []
    if options.write_edges and edges:
        edge_plan = plan_edges(edges, preflight_generator(config, index_path, texts, no_backfill), texts)
    items = preflight_generator(config, index_path, texts, no_backfill)
    missing = chk.missing_edges(edges, items)
    if missing:
        raise Refusal(f"{len(missing)} '## Dependencies' edge(s) are missing from frontmatter blocks: "
                      f"{'; '.join(missing[:10])}. The generator renders no Dependencies section",
                      "add each edge to its item's blocks: first"
                      + ("" if options.write_edges else ", or add --write-edges to write each edge into blocks:"))
    valid_abbrevs = sup.configured_abbrevs(config)
    compared = {k: v for k, v in roles.items() if k != "abbrev"} if decisions is not None else roles
    rows, diffs = collect_rows(resolved, compared, index_path, items, valid_abbrevs)
    settled = {(w["key"], w["path"]) for w in wins}  # the file name already won these cells
    diffs = [d for d in diffs if (d["key"], d["path"]) not in settled]
    diffs = _settled_by_name(diffs, resolved, roles, wins, _journal(paths[1]).get("wins") or [])
    cells = plan_reconcile(diffs, options.reconcile, texts, items)
    written_cells = cells if options.reconcile == "index-wins" else []
    if written_cells:
        items = preflight_generator(config, index_path, texts)
        if chk.missing_edges(edges, items):
            for edge in plan_edges(edges, items, texts):
                known = next((e for e in edge_plan if (e["src"], e["dst"]) == (edge["src"], edge["dst"])), None)
                if known is None:
                    edge_plan.append(edge)
                    known = edge
                known["source"] = "dependencies-table"
                for cell in cells:
                    if cell["key"] == "blocks" and cell["path"] == edge["path"]:
                        cell["written"] = sorted({*cell.get("written", cell["index"]), edge["dst"]}, key=int)
            items =preflight_generator(config, index_path, texts)
    dests = plan_dedup(rows, options.high, options.low, options.append_ambiguous, texts, options.park_ambiguous)
    for dest in dests:
        if dest["append"]:
            units = [unit for _row_id, unit in dest["append"]]
            dest["new_text"] = sup.append_notes(dest["body"], units, sup.newline_of(dest["body"]))
            texts[dest["path"]] = dest["new_text"]
    bullets = [{**f, "kind": "bullet", "text": remainder_bullet(f)} if f["kind"] == "remainder" else f
               for f in found if f["kind"] in ("bullet", "remainder")]
    notes = plan_notes(bullets, items, texts, relocated)
    _refuse_unusable_abbrevs(texts, valid_abbrevs)
    pending = (sum(len(d["append"]) for d in dests) + len(backfill) + len(edge_plan) + len(written_cells)
               + sum(n["bullets"] for n in notes) + len(id_repairs)
               + sum(1 for c in abbrev_cells if c["frontmatter"] not in (None, c["written"])))
    naming = gen._index_naming(index_path)
    relocated.sort(key=lambda record: record["line"])
    when = (reloc.recorded_date(read_text(changelog_path)) if relocated and changelog_path.exists() else None) or _today()
    entry = reloc.render_relocated_entry(relocated, when) if relocated else None
    if entry:
        reloc.check_size(relocated, entry)
    changelog = plan_changelog(text, index_path, changelog_path, pending, naming, entry)
    if changelog is None:
        return None
    for entry in backfill:
        entry["lines"] = _key_lines(texts[entry["path"]], entry["keys_added"])
    lines = text.split("\n")
    for win in wins:  # the staged index states the winning value, so a re-run finds the cell and file agreeing
        if win["index"] and win["index"] != win["written"]:
            row = next(r for r in resolved if r["path"] == win["path"])
            lines[row["line"]] = retarget_cell(lines[row["line"]], win["index"], win["written"])
    retargeted = "\n".join(lines)
    footer = sup.FOOTER_TEXT_RE.search(retargeted)
    pointer = f"*Last Updated: {_today()} — moved to [{changelog_path.name}]({changelog_path.name})*"
    index_text = retargeted[:footer.start()] + pointer + retargeted[footer.end():]
    drop ={i for f in found for i in range(f["line"] - 1, f["line"] - 1 + f["count"])}
    drop |= scanned
    if drop:
        index_text = _drop_lines(index_text, drop)
    outputs = [(path, texts[path]) for path in sorted(texts, key=str)]
    outputs += list(changelog["parts"]) + [(index_path, index_text)]
    return {"changelog": changelog, "dests": dests, "row_count": len(rows),
            "interrupted": changelog["resumed"] or any(d["prior"] for d in dests) or any(n["present"] for n in notes),
            "index_text": index_text, "relocated": relocated, "relocated_entry": entry, "backfill": backfill, "id_repairs": id_repairs, "edges": edge_plan, "notes": notes,
            "dropped_headings": [f["text"] for f in found if f["kind"] == "heading"],
            "abbreviations": _abbrev_record(config, decisions),
            "reconcile": {"mode": options.reconcile, "cells": cells + wins}, "outputs": outputs}


def plan_migration(config: dict, index_path: Path, text: str, detail: tuple, options: RepairOptions):
    """Plan the migration of a `legacy` index in memory. Returns the plan, or None when the
    index is already migrated. Raises `Refusal`. Nothing is written."""
    if options.reconcile not in (None, *RECONCILE_MODES):
        raise Refusal(f"unknown reconcile mode {options.reconcile!r}",
                      f"use one of {', '.join(RECONCILE_MODES)}")
    return build_plan(text, detail, config, index_path, artifact_paths(index_path), options)


def plan_targets(plan: dict) -> list:
    """Every existing file the plan rewrites, for a caller to back up first: the item files,
    the changelog when it exists, and the index. The ledger is new, so it is never a target."""
    return [path for path, _text in plan["outputs"] if path.exists()]


def _size(units) -> int:
    return sum(len(u.encode("utf-8")) for u in units)


def parked_records(dests: list) -> list:
    """Each parked AMBIGUOUS unit, verbatim, with its source row, target item file, score and size."""
    return [{"row": p["row"], "path": str(d["path"]), "unit": p["unit"], "label": p["label"],
             "similarity": p["similarity"], "bytes": _size([p["unit"]])}
            for d in dests for p in d.get("parked", ())]


def units_on_disk(dests: list, ledger_path: Path) -> Counter:
    """Every row prose unit a re-read from disk finds where the plan put it: an appended or
    prior-run unit verbatim in its item file, a parked unit verbatim in the ledger-path file
    (the journal before the ledger is written, the ledger after)."""
    found = Counter()
    for d in dests:
        body = read_text(d["path"])
        found.update(u for _r, u in d.get("append", []) + d.get("prior", []) if u in body)
    if any(d.get("parked") for d in dests):
        try:
            held = json.loads(read_text(ledger_path)).get("parked_ambiguous") or []
        except (OSError, ValueError, AttributeError):
            held = []
        wanted = Counter((p["row"], str(d["path"]), p["unit"]) for d in dests for p in d.get("parked", ()))
        have = Counter((r.get("row"), r.get("path"), r.get("unit")) for r in held if isinstance(r, dict))
        found.update(unit for (_row, _path, unit), n in (wanted & have).items() for _ in range(n))
    return found


def dedup_accounting(dests: list, on_disk: Counter | None = None) -> dict:
    """Byte conservation for row prose: every unit is appended, already present, appended by a
    prior run, or parked in the ledger. `unaccounted_*` counts what is none of these. With
    `on_disk` (from `units_on_disk`), appended, prior-run and parked units count only when the
    re-read found them; an already-present unit counts as the plan classified it, since it was in
    its item file before this run and the run does not remove it."""
    source = Counter(u for d in dests for u in [*(u for _r, u in d.get("units", ())),
                                                *(u for _r, (u, _n) in d.get("links", ()))])
    if on_disk is None:
        placed = Counter(u for d in dests for u in [*(u for k in ("append", "dedup", "prior") for _r, u in d.get(k, ())),
                                                    *(p["unit"] for p in d.get("parked", ()))])
    else:
        placed = on_disk + Counter(u for d in dests for _r, u in d.get("dedup", ()))
    missing = source - placed
    parked = [p["unit"] for d in dests for p in d.get("parked", ())]
    return {"parked_units": len(parked), "parked_bytes": _size(parked),
            "unaccounted_units": sum(missing.values()), "unaccounted_bytes": sum(_size([u]) * n for u, n in missing.items()),
            "unaccounted_basis": "plan" if on_disk is None else "re-read from disk"}


def build_ledger(plan: dict, paths: tuple, measured: dict | None = None, misses: list | None = None,
                 disk_log: str | None = None, on_disk: Counter | None = None) -> dict:
    c, dests = plan["changelog"], plan["dests"]
    units = {k: [u for d in dests for _r, u in d[k]] for k in ("append", "dedup", "prior")}
    units["parked"] = [p["unit"] for d in dests for p in d.get("parked", ())]
    size = _size
    planned_text = sup.joined_entries([t for _p, t in c["parts"]])
    ledger = {
        "run_date": _today(), "mode": "dry-run" if measured is None else "write",
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
                  "ambiguous_appended": sum(len(d["ambiguous"]) for d in dests), **dedup_accounting(dests, on_disk)},
        "destinations": [{"path": str(d["path"]), "bytes_before": d["bytes_before"],
                          "bytes_before_basis": UNRECOVERABLE if d["prior"] else "pre-migration",
                          "bytes_after": None, "bytes_added": None, "units_appended": len(d["append"]),
                          "units_appended_by_prior_run": len(d["prior"]),
                          "units_deduplicated": len(d["dedup"]), "units_parked": len(d.get("parked", ()))}
                         for d in dests],
        "parked_ambiguous": parked_records(dests),
        "backfill": [{"path": str(b["path"]), "keys_added": b["keys_added"], "created_source": b["created_source"]}
                     for b in plan["backfill"]],
        "id_repairs": [{"path": str(r["path"]), "from": r["from"], "to": r["to"]} for r in plan.get("id_repairs", ())],
        "edges": [{"src": e["src"], "dst": e["dst"], **({"source": e["source"]} if "source" in e else {})}
                  for e in plan["edges"]],
        "dependency_notes": [{"path": str(n["path"]), "bullets": n["bullets"], "bytes": n["bytes"],
                              "already_present": n["present"]} for n in plan["notes"]],
        "dependency_headings_dropped": plan["dropped_headings"],
        "relocated_index_lines": reloc.ledger_rows(plan.get("relocated", ())),
        "oversized_single_entries": sup.oversized_single_entries(c["parts"]),
        "abbreviations": plan.get("abbreviations") or {"added": [], "matched": []},
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


def parked_line(units: int, num_bytes: int, ledger: str) -> str:
    """The one line the dry-run report and the upgrade banner print for parked AMBIGUOUS units."""
    return f"parked ambiguous units: {units} ({num_bytes} bytes) — see {ledger}"


def format_report(plan: dict, ledger_name: str = "the migration ledger") -> str:
    c, dests = plan["changelog"], plan["dests"]
    count = {k: sum(len(d[k]) for d in dests) for k in ("append", "dedup", "prior")}
    backfill, notes, rec = plan["backfill"], plan["notes"], plan["reconcile"]
    planned_text = sup.joined_entries([t for _p, t in c["parts"]])
    lines = [(f"changelog: {len(c['segments'])} entr(y/ies), {c['entry_content_bytes']} content bytes, "
              f"unaccounted={sup.unaccounted(c['segments'], planned_text)}"
              f"{', resuming an interrupted run' if c['resumed'] else ''}"
              f"{', filling a header-only changelog' if c.get('header_only') else ''}"),
             f"changelog parts: {len(c['parts'])} file(s), " + ", ".join(
                 f"{p.name}={sup.changelog_tokens(t)}t" for p, t in c["parts"]),
             (f"dedup: {sum(count.values())} unit(s) across {plan['row_count']} row(s) -- {count['append']} to "
              f"append, {count['prior']} appended by a prior run, {count['dedup']} already present (deduplicated)"),
             (f"backfill: {len(backfill)} item file(s) gain frontmatter ({sum(b['partial'] for b in backfill)} "
              f"had a partial block), {len(plan.get('id_repairs', ()))} prefixed id: value(s) normalised"),
             f"edges: {len(plan['edges'])} '## Dependencies' edge(s) to write into blocks:",
             (f"dependency notes: {sum(n['bullets'] for n in notes)} bullet(s) into "
              f"{sum(1 for n in notes if n['bullets'])} item file(s), {len(plan['dropped_headings'])} heading "
              "line(s) dropped"),
             f"reconcile: {rec['mode'] or 'off'}, {len(rec['cells'])} cell(s)"]
    parked = dedup_accounting(dests)
    if parked["parked_units"]:
        lines.append(parked_line(parked["parked_units"], parked["parked_bytes"], ledger_name))
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
            what = "relocated index text entry" if i == 1 and plan.get("relocated_entry") else f"changelog entry {i}"
            misses.append(f"{what} is missing from its changelog part(s)")
    for d in plan["dests"]:
        body = read_text(d["path"])
        misses += [f"row {row_id} unit {unit[:70]!r} is missing from {d['path'].name}"
                   for row_id, unit in d["append"] + d["prior"] if unit not in body]
    lost = dedup_accounting(plan["dests"], units_on_disk(plan["dests"], paths[1]))
    if lost["unaccounted_units"]:
        misses.append(f"{lost['unaccounted_units']} row prose unit(s), {lost['unaccounted_bytes']} bytes, are neither "
                      "in an item file nor parked in the ledger")
    for b in plan.get("backfill", ()):
        body = read_text(b["path"]).replace("\r\n", "\n")
        misses += [f"backfilled line {line!r} is missing from {b['path'].name}" for line in b["lines"] if line not in body]
    for r in plan.get("id_repairs", ()):
        raw = repairs.partial_frontmatter(read_text(r["path"]))[0] or {}
        if str(raw.get("id", "")).strip() != r["to"]:
            misses.append(f"repaired id: {r['to']} is missing from {r['path'].name}")
    for e in plan.get("edges", ()):
        raw = repairs.partial_frontmatter(read_text(e["path"]))[0] or {}
        if e["dst"] not in sup.ids_in(raw.get("blocks", "")):
            misses.append(f"edge {e['src']} blocks {e['dst']} is missing from {e['path'].name}")
    for n in plan.get("notes", ()):
        body = read_text(n["path"])
        misses += [f"dependency note {u[:70]!r} is missing from {n['path'].name}" for u in n["units"] if u not in body]
    rec = plan.get("reconcile") or {"mode": None, "cells": []}
    for cell in rec["cells"]:
        if cell.get("winner"):  # the settled value, whether this run wrote it or the file already held it
            raw = repairs.partial_frontmatter(read_text(cell["path"]))[0] or {}
            if str(raw.get(cell["key"]) or "").strip().strip("\"'") != cell["written"]:
                misses.append(f"reconciled {cell['key']}: {cell['written']} is missing from {cell['path'].name}")
            continue
        if rec["mode"] == "index-wins":
            value = f"[{', '.join(cell.get('written', cell['index']))}]" if cell["key"] == "blocks" else cell["index"]
        else:
            continue
        if f"{cell['key']}: {value}" not in read_text(cell["path"]):
            misses.append(f"reconciled {cell['key']}: {value} is missing from {cell['path'].name}")
    if read_text(index_path) != plan["index_text"]:
        misses.append(f"{index_path.name} does not match the staged text")
    return misses


def verify_parked(ledger_path: Path, records: list) -> list:
    """Re-read the ledger from disk and name each parked unit it does not hold verbatim."""
    if not records:
        return []
    try:
        on_disk = json.loads(read_text(ledger_path)).get("parked_ambiguous") or []
    except (OSError, ValueError, AttributeError) as exc:
        return [f"the ledger could not be re-read to check its {len(records)} parked unit(s) ({exc})"]
    held = Counter((r.get("row"), r.get("path"), r.get("unit")) for r in on_disk if isinstance(r, dict))
    missing = Counter((r["row"], r["path"], r["unit"]) for r in records) - held
    return [f"parked row {row} unit {unit[:70]!r} is missing from {ledger_path.name}"
            for (row, _path, unit), n in missing.items() for _ in range(n)]


def execute(plan: dict, paths: tuple, index_path: Path, json_mode: bool) -> int:
    outputs = plan["outputs"]
    # Parked units live nowhere else once the index is replaced, so the journal -- replaced first --
    # carries them until the finished ledger overwrites it.
    journal = {"mode": sup.JOURNAL_MODE, "targets": [str(p) for p, _text in outputs],
               "parked_ambiguous": parked_records(plan["dests"]),
               "abbreviations": plan.get("abbreviations") or {"added": [], "matched": []},
               "wins": [{"path": str(c["path"]), "key": c["key"], "winner": c["winner"], "written": c["written"]}
                        for c in plan["reconcile"]["cells"] if c.get("winner")]}
    try:  # the journal replaces first, so a rerun owns whatever an interrupted replace left dirty
        staged = sup.stage_all([(paths[1], json.dumps(journal, indent=2) + "\n"), *outputs])
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
    ledger = build_ledger(plan, paths, {str(p): p.stat().st_size for p in written}, misses, disk_log,
                          units_on_disk(plan["dests"], paths[1]))  # the journal still holds the parked units
    try:
        sup.replace_all(sup.stage_all([(paths[1], json.dumps(ledger, indent=2) + "\n")]))
    except (OSError, sup.ReplaceError) as exc:
        return say(1, f"FAIL: migration written and verified={not misses}, but the ledger write failed ({exc}).",
                   json_mode, err=True)
    misses += verify_parked(paths[1], ledger["parked_ambiguous"])
    if json_mode:
        print(json.dumps(ledger, indent=2))
    if misses:
        return say(1, "FAIL: verification from disk found " + "; ".join(misses), json_mode, err=True)
    return say(0, f"WROTE: {paths[0].name}, ledger at {paths[1].name}; verified from disk. "
                  "Next: run generate_backlog_index.py --write.", json_mode)


def execute_outputs(outputs: list, remove: list = ()) -> int:
    """Stage and replace every (path, text) pair, then delete each path in
    `remove`; returns the count written. An upgrade orchestrator and
    `--split-changelog` both call this."""
    written = len(sup.replace_all(sup.stage_all(outputs)))
    for path in remove:
        path.unlink(missing_ok=True)
    return written


def plan_changelog_resplit(config: dict, index_path: Path):
    """Re-split an already-migrated changelog that has grown over budget.
    Returns None when every changelog file is already within budget, else
    `{"outputs": [...], "targets": [...], "parts": [...], "remove": [...]}`.
    An upgrade orchestrator calls this name directly."""
    return sup.plan_changelog_resplit(config, index_path)


_changelog_state = sup.changelog_state


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
              "row_mismatches": 0, "parked_ambiguous": {"units": 0, "bytes": 0},
              "ready_with_all_repairs": shape == "migrated",
              "would_refuse": [detail] if shape == "unrecognized" else [], "questions": []}
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
            report["row_mismatches"] += len(sup.row_diffs(cells, roles, gen._scan_one_file(path),
                                                          sup.configured_abbrevs(config)))
        except (gen.GeneratorError, Refusal):  # the plan below names a Refusal in would_refuse
            continue
    try:  # the unattended upgrade's own pre-pass and options, so readiness and the parked count match it
        pending = pending_abbrevs(artifact_paths(index_path)[1])
        plan_config, _added = abbrev_prepass(config, detail, text, index_path, pending)
        plan = plan_migration(plan_config, index_path, text, detail, RepairOptions.unattended())
        report["ready_with_all_repairs"] = True
        if plan is not None:
            parked = dedup_accounting(plan["dests"])
            report["parked_ambiguous"] = {"units": parked["parked_units"], "bytes": parked["parked_bytes"]}
    except Refusal as exc:
        refusals = [exc]  # the plan stops at its first refusal; each carries its own question, if any
        report["would_refuse"] = [str(r) for r in refusals]
        report["questions"] = [r.question for r in refusals if r.question]
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
                   help="Append AMBIGUOUS dedup units instead of refusing. /planwise upgrade and init park them "
                        "in the ledger instead; this flag wins over parking when both apply.")
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
    try:
        plan = plan_changelog_resplit(config, index_path)
    except Refusal as exc:
        return say(2, f"REFUSED: {exc}", js, err=True)
    if plan is None:
        return say(0, "changelog within budget", js)
    if not args.write:
        if js:
            print(json.dumps({"targets": [str(p) for p in plan["targets"]], "parts": plan["parts"],
                              "remove": [str(p) for p in plan["remove"]]}, indent=2))
        else:
            print("\n".join([f"would write {p.name}" for p, _t in plan["outputs"]]
                            + [f"would remove {p.name}" for p in plan["remove"]]))
        return say(1, "DRY-RUN: changelog split needed; no files written.", js)
    refusal, warning = chk.write_gate(config["_project_root"], [index_path, *plan["targets"]],
                                      args.allow_untracked_tree, args.force)
    if refusal:
        return say(2, f"REFUSED: {refusal}", js, err=True)
    if warning:
        say(0, warning, js, err=True)
    try:
        written = execute_outputs(plan["outputs"], plan["remove"])
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
    if plan is None and interrupted_journal(paths[1]) is not None:
        if not args.write:
            return say(1, f"DRY-RUN: {paths[1].name} is the journal of an interrupted migration; --write would "
                          f"rename it to {paths[1].stem}-Interrupted-{_today()}.json and keep every byte.", js)
        renamed = settle_interrupted_journal(paths[1])
        return say(0, f"WROTE: renamed the interrupted migration's journal to {renamed.name}. "
                      "Next: run generate_backlog_index.py --write.", js)
    if plan is None:
        return say(0, f"CLEAN: already migrated -- the footer points to {paths[0].name} and every row's "
                      "prose is in its item file. Next: run generate_backlog_index.py --write.", js)
    refusal = chk.tree_gate(dirty, plan, paths, index_path, args.force)
    if refusal:
        return say(2, f"REFUSED: {refusal}", js, err=True)
    if not args.write:
        print(json.dumps(build_ledger(plan, paths), indent=2) if js else format_report(plan, paths[1].name))
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
