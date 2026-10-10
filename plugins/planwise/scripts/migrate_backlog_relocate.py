#!/usr/bin/env python3
"""Relocate index-level text that regeneration would drop into one changelog entry.

The scan in `migrate_backlog_checks` names every index line the generator
drops and the migrator does not move: preamble text, text between the
heading and its table, text after the items table, text under `## Shards`
or `## Dependencies`, and an unrecognised `## ` section. This module turns
those problem lines, plus a soft-dependency bullet whose owner has no item
file and an items-table row whose Files cell resolves no item file, into
ordered records. `render_relocated_entry` writes them as one dated
changelog entry, each line byte-exact after its line number and kind, so
no byte of the index is lost and nobody edits the index by hand.

A problem the migrator still refuses (an unrecognised table or table row, a
foreign id prefix, a Dependencies row note) is not a relocation. `split_problems`
separates the two.
"""
import re

TITLE = "Relocated index text (migrated {today})"
_PROBLEM_RE = re.compile(r"^line (\d+): (preamble text|text between |text after the table|text under |section )")
_KINDS = {"preamble text": "preamble", "text between ": "text between the heading and its table",
          "text after the table": "text after the table", "text under ": "text under a section",
          "section ": "unrecognised section"}
_SECTION_BODY_KIND = "unrecognised section text"


_DATE_RE = re.compile(r"(?m)^" + re.escape(TITLE).replace(r"\{today\}", r"(\d{4}-\d{2}-\d{2})") + r"\s*$")


def recorded_date(changelog_text: str):
    """The date of a relocated entry an interrupted run already wrote, else None. A resumed run
    reuses it, so its planned entry matches the text on disk byte for byte."""
    found = _DATE_RE.search(changelog_text)
    return found.group(1) if found else None


def split_problems(problems: list) -> tuple:
    """Return (relocatable problems, problems the migrator still refuses), each in scan order."""
    keep = [p for p in problems if _PROBLEM_RE.match(p)]
    return keep, [p for p in problems if p not in keep]


def collect_relocations(problems: list, lines: list) -> list:
    """Turn relocatable scan problems into `{line, kind, text}` records, in line order.
    `lines` is the index split on newlines. `text` is the whole source line, minus a trailing
    carriage return. An unrecognised section also takes its body, up to the next `## ` heading
    or the footer, with blank and `---` lines left out."""
    found = {}
    for problem in problems:
        match = _PROBLEM_RE.match(problem)
        if not match:
            continue
        number, kind = int(match.group(1)), _KINDS[match.group(2)]
        found[number] = {"line": number, "kind": kind, "text": lines[number - 1].rstrip("\r")}
        if kind != "unrecognised section":
            continue
        for i in range(number, len(lines)):
            body = lines[i].rstrip("\r")
            if body.startswith(("## ", "*Last Updated:")):
                break
            if body.strip() not in ("", "---"):
                found.setdefault(i + 1, {"line": i + 1, "kind": _SECTION_BODY_KIND, "text": body})
    return [found[number] for number in sorted(found)]


def render_relocated_entry(records: list, today: str) -> str:
    """The one changelog entry the records land in: a dated title line, a blank line, then
    `- line {N} ({kind}): {text}` for each record, verbatim and never reflowed."""
    body = "\n".join(f"- line {r['line']} ({r['kind']}): {r['text']}" for r in records)
    return TITLE.format(today=today) + "\n\n" + body


def ledger_rows(records: list) -> list:
    """The ledger's `relocated_index_lines` value: `{line, kind, bytes}` per record."""
    return [{"line": r["line"], "kind": r["kind"], "bytes": len(r["text"].encode("utf-8"))} for r in records]
