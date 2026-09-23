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

The changelog is `00-{stem}-Changelog{suffix}` beside the index, and the
ledger is `00-{stem}-Migration-Ledger.json`, where `{stem}` is the index
stem without a leading `00-`. The generator's item scan skips `00-` files.
With `--json`, stdout carries only the JSON document.

Exit codes: 0 clean, or nothing to do. 1 migration needed (dry-run), or a
write or verification failure. 2 refused.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_backlog_index as gen  # noqa: E402
import migrate_backlog_checks as chk  # noqa: E402
import migrate_backlog_support as sup  # noqa: E402
from config_loader import load_config  # noqa: E402
from reconcile_common import read_text_preserving_newlines as read_text  # noqa: E402

UNRECOVERABLE = ("resumed: this size includes notes an interrupted earlier run appended; "
                 "the pre-migration size is not recoverable from this file")


class Refusal(Exception):
    """A condition that stops the run before any write (exit 2)."""


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


def preflight_generator(config: dict, index_path: Path) -> dict:
    """Run the generator's own scan now, so its refusal lands before any write."""
    naming = gen._index_naming(index_path)
    try:
        items, reciprocal, _report = gen._run_report_pipeline(
            config["_backlog_dir"], config["_archive_dir"], index_path, naming, config)
    except gen.GeneratorError as exc:
        raise Refusal(f"the generator would refuse this tree -- {exc}") from exc
    if reciprocal:
        pairs = ", ".join(f"{a}<->{b}" for a, b in reciprocal)
        raise Refusal(f"the generator would refuse to write: reciprocal blocks edge(s) {pairs}")
    return {item["_path"].resolve(): item for item in items}


def collect_rows(text: str, header_idx: int, roles: dict, config: dict, index_path: Path, items: dict):
    rows, mismatches = [], []
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
        fields = items.get(path)
        if fields is None:
            raise Refusal(f"{where}: {path.name} is not an item file the generator scans")
        mismatches += sup.compare_row(cells, roles, fields)
        extra = [sup.link_unit(t, h, index_path.parent, path.parent) for t, h in links[1:]
                 if h.strip() != links[0][1].strip()]
        rows.append({"id": fields["id"], "path": path, "links": extra,
                     "units": sup.row_units(cells[roles["feature"]], fields["title"])})
    if mismatches:
        raise Refusal(f"{len(mismatches)} row cell(s) disagree with item frontmatter: {'; '.join(mismatches[:10])}. "
                      "The generator renders frontmatter, so reconcile the frontmatter first")
    return rows


def plan_dedup(rows: list, high: float, low: float, append_ambiguous: bool) -> list:
    dests = {}
    for row in rows:
        dest = dests.setdefault(row["path"], {"path": row["path"], "units": [], "links": []})
        dest["units"] += [(row["id"], unit) for unit in row["units"]]
        dest["links"] += [(row["id"], link) for link in row["links"]]
    ambiguous = []
    for dest in dests.values():
        dest["body"] = read_text(dest["path"])
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


def plan_changelog(text: str, index_path: Path, changelog_path: Path, pending: int):
    """Return the changelog plan, or None when the index is already migrated."""
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
                          f"{pending} unit(s) of row prose are not in their item files. An interrupted "
                          "older run or a hand edit left this state -- restore from version control")
        return None
    plan = sup.extract_changelog(index_path.read_bytes())
    plan["text"] = sup.changelog_text(plan["segments"], index_path.name, sup.newline_of(text))
    plan["resumed"] = False
    if changelog_path.exists():
        if read_text(changelog_path).replace("\r\n", "\n") != plan["text"].replace("\r\n", "\n"):
            raise Refusal(f"{changelog_path.name} already exists but does not hold this index's footer "
                          "entries. An interrupted older run or a hand edit left it -- move it aside "
                          "or restore the index from version control")
        plan["resumed"] = True
    return plan


def build_plan(text: str, detail: tuple, config: dict, index_path: Path, paths: tuple, args):
    header_idx, roles = detail
    problems, edges = chk.scan_index(text, header_idx)
    if problems:
        raise Refusal("content regeneration would drop and this tool does not move: " + "; ".join(problems))
    changelog_path, _ledger, older = paths
    if older != changelog_path and older.exists():
        raise Refusal(f"{older.name} exists from an earlier version of this tool, and the generator "
                      f"would scan it as an item file -- rename it to {changelog_path.name}")
    items = preflight_generator(config, index_path)
    missing = chk.missing_edges(edges, items)
    if missing:
        raise Refusal(f"{len(missing)} '## Dependencies' edge(s) are missing from frontmatter blocks: "
                      f"{'; '.join(missing[:10])}. The generator renders no Dependencies section, so add "
                      "each edge to its item's blocks: first")
    rows = collect_rows(text, header_idx, roles, config, index_path, items)
    dests = plan_dedup(rows, args.high, args.low, args.append_ambiguous)
    changelog = plan_changelog(text, index_path, changelog_path, sum(len(d["append"]) for d in dests))
    if changelog is None:
        return None
    for dest in dests:
        if dest["append"]:
            units = [unit for _row_id, unit in dest["append"]]
            dest["new_text"] = sup.append_notes(dest["body"], units, sup.newline_of(dest["body"]))
    footer = sup.FOOTER_TEXT_RE.search(text)
    pointer = f"*Last Updated: {date.today().isoformat()} — moved to [{changelog_path.name}]({changelog_path.name})*"
    return {"changelog": changelog, "dests": dests, "row_count": len(rows),
            "interrupted": changelog["resumed"] or any(d["prior"] for d in dests),
            "index_text": text[:footer.start()] + pointer + text[footer.end():]}


def build_ledger(plan: dict, paths: tuple, measured: dict | None = None, misses: list | None = None,
                 disk_log: str | None = None) -> dict:
    c, dests = plan["changelog"], plan["dests"]
    units = {k: [u for d in dests for _r, u in d[k]] for k in ("append", "dedup", "prior")}
    size = lambda us: sum(len(u.encode("utf-8")) for u in us)  # noqa: E731
    ledger = {
        "run_date": date.today().isoformat(), "mode": "dry-run" if measured is None else "write",
        "changelog": {**{k: v for k, v in c.items() if k not in ("segments", "text")},
                      "entries": len(c["segments"]), "path": str(paths[0]), "bytes_on_disk": None,
                      "unaccounted": sup.unaccounted(c["segments"], c["text"] if disk_log is None else disk_log),
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
    lines = [f"changelog: {len(c['segments'])} entr(y/ies), {c['entry_content_bytes']} content bytes, "
             f"unaccounted={sup.unaccounted(c['segments'], c['text'])}"
             f"{', resuming an interrupted run' if c['resumed'] else ''}",
             f"dedup: {sum(count.values())} unit(s) across {plan['row_count']} row(s) -- {count['append']} to "
             f"append, {count['prior']} appended by a prior run, {count['dedup']} already present (deduplicated)"]
    for d in dests:
        lines += [f"  append row {row_id} -> {d['path'].name}: {unit[:70]!r}" for row_id, unit in d["append"]]
    return "\n".join(lines)


def verify_written(plan: dict, paths: tuple, index_path: Path) -> list:
    """Re-read every written file from disk and name each unit not found."""
    misses = []
    log = read_text(paths[0])
    for i, seg in enumerate(plan["changelog"]["segments"], start=1):
        if seg.decode("utf-8") not in log:
            misses.append(f"changelog entry {i} is missing from {paths[0].name}")
    for d in plan["dests"]:
        body = read_text(d["path"])
        misses += [f"row {row_id} unit {unit[:70]!r} is missing from {d['path'].name}"
                   for row_id, unit in d["append"] + d["prior"] if unit not in body]
    if read_text(index_path) != plan["index_text"]:
        misses.append(f"{index_path.name} does not match the staged text")
    return misses


def execute(plan: dict, paths: tuple, index_path: Path, json_mode: bool) -> int:
    changed = [(d["path"], d["new_text"]) for d in plan["dests"] if d["append"]]
    outputs = changed + [(paths[0], plan["changelog"]["text"]), (index_path, plan["index_text"])]
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
    written = [d["path"] for d in plan["dests"]] + [paths[0], index_path]
    ledger = build_ledger(plan, paths, {str(p): p.stat().st_size for p in written}, misses, read_text(paths[0]))
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
    return p


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
    try:
        high_s, low_s = args.thresholds.split(",")
        args.high, args.low = float(high_s), float(low_s)
    except ValueError:
        return say(2, f"REFUSED: --thresholds must be 'high,low' floats, got {args.thresholds!r}.", js, err=True)
    if not 0 <= args.low < args.high <= 1:
        return say(2, f"REFUSED: --thresholds needs 0 <= low < high <= 1, got high={args.high}, low={args.low}.",
                   js, err=True)

    config = load_config(Path(__file__))
    index_path = config["_index_path"]
    if not index_path.exists():
        return say(2, f"REFUSED: index not found at {index_path}", js, err=True)

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
        plan = build_plan(text, detail, config, index_path, paths, args)
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


if __name__ == "__main__":
    sys.exit(main())
