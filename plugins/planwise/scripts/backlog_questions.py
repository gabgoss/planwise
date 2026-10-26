#!/usr/bin/env python3
"""Open-question blocks in backlog item files: write, fold, answer and list.

An item's open questions live under `## Open Questions` as `### Q{n}.`
blocks, each ending in an `Answer:` line (`templates/backlog-item.md`
§ Executable shape). The backlog loop records a skipped item's question as
one such block through `append_question`. Older loop runs wrote a
`## Loop Decision Needed` section instead; `--fold` moves each one into a
block.

Library:

  append_question(path, run_id, text)  write one `### Q{n}. Loop decision (run R)` block
  validate_question_text(text)         the refusals every loop question passes
  check_question_target(path)          the refusals of the item file itself, before any write

Subcommands, each printing short human lines and then ONE final line that is
a single-line JSON object:

  --fold (--id N | --all) [--dry-run]  move every `## Loop Decision Needed`
                                       section into a block; --dry-run
                                       prints the plan and writes nothing
  --answer --id N --q K --text-file F  fill the empty `Answer:` line of `### Q{K}.`
  --list [--id N] [--json]             print every unanswered block over the
                                       backlog index, then the count of
                                       sections still to fold; reads only.
                                       --json prints the JSON line alone

Exit codes: 0 ok, 1 usage error or refusal. A refusal writes nothing to the
refused file. `--fold --all` refuses an item and goes on with the next one,
and exits 1 when it refused any.

Items are found through the backlog index (hub and overflow leaves), never by
globbing the backlog directory, so `Backlog-Runs/` is never read. Every item
file keeps its own line endings: a CRLF file stays CRLF.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Import shared helpers from the sibling scripts
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from config_loader import load_config
from item_shape import (
    _ANSWER_LINE_RE,
    _QUESTION_HEADING_RE,
    _THEMATIC_BREAK_RE,
    fence_flags_any_indent,
)
from markdown_parser import normalize_id
from reconcile_common import (
    read_text_preserving_newlines,
    write_text_preserving_newlines,
)
from scoped_rules import (
    LOOP_SECTION_END,
    LOOP_WRITTEN_HEADINGS,
    TOP_HEADING_RE,
    fence_left_open,
    loop_sections,
)
from score_backlog import _read_hub_family_items, get_first_file_path

EXIT_OK = 0
EXIT_USAGE = 1
QUESTIONS_TITLE = "Open Questions"
QUESTIONS_HEADING = f"## {QUESTIONS_TITLE}"
RELATED_HEADING = "## Related"
LEGACY_HEADING = f"## {LOOP_WRITTEN_HEADINGS[0]}"
QUESTION_MAX_CHARS = 1200
# The outcomes of append_question.
QUESTION_APPENDED = "appended"
QUESTION_SAME_RUN = "same_run"
UNKNOWN_RUN = "unknown"
_LOOP_TITLE = "Loop decision (run "
_TAG_RE = re.compile(r"<!-- loop-decision run=([^\s>]+) -->")
# The tag, hash and end-marker lines a legacy section carries.
_LOOP_MARKER_RE = re.compile(r"^<!-- loop-decision[ -]")
_LEVEL_3_RE = re.compile(r"^###(?:[ \t]|\r?$)")
_ANY_HEADING_RE = re.compile(r"^#{1,6}(?:[ \t]|\r?$)")
_EMPTY_ANSWER_RE = re.compile(r"^\s*(?:[-*]\s+)?\*{0,2}Answer\*{0,2}\s*:[\s*]*$")
_EMPTY_FORMS = ("none", "none.")


class QuestionError(Exception):
    """A refusal or usage error: the message names what to change."""


def _eol(raw: str) -> str:
    return "\r\n" if "\r\n" in raw else "\n"


def _read(path: Path) -> tuple[str, str]:
    """The file's text with LF line ends, and the line end to write back."""
    raw = read_text_preserving_newlines(path)
    return raw.replace("\r\n", "\n"), _eol(raw)


def _write(path: Path, text: str, eol: str) -> None:
    write_text_preserving_newlines(path, text if eol == "\n" else text.replace("\n", eol))


def validate_question_text(
    text: str, label: str = "--decision", max_chars: int | None = QUESTION_MAX_CHARS
) -> str:
    """Return the question text stripped, with LF line ends; raise QuestionError to refuse it.

    Refused: more than `max_chars` characters (no cap when None), a heading
    line of level 1, 2 or 3 (a `### ` line would split the block), a fence
    the text opens and never closes, the legacy end-marker line, an empty
    text, and, outside a fence, a thematic-break line (it would end the
    section before the block's `Answer:` line) or an `Answer:` line, filled
    or empty (the block would read answered, or the answer would land in
    the question).
    """
    if max_chars is not None and len(text) > max_chars:
        raise QuestionError(
            f"{label} is {len(text)} characters; the cap is {max_chars}. "
            "Write it as: Question: ... Options: (A) ... (B) ... Evidence: at most 3 lines."
        )
    body = text.replace("\r\n", "\n").strip()
    lines = body.split("\n")
    if any(TOP_HEADING_RE.match(line) for line in lines):
        raise QuestionError(
            f"{label} has a heading line of level 1 or 2; a decision line may not start with `## `, "
            f"`# `, or be a bare `#` or `##`, because it would end the {QUESTIONS_HEADING} section. "
            "Reword or indent that line."
        )
    if any(_LEVEL_3_RE.match(line) for line in lines):
        raise QuestionError(
            f"{label} has a heading line of level 3; a line may not start with `### ` or be a bare "
            "`###`, because it would split the question block. Reword or indent that line."
        )
    if fence_left_open(body):
        raise QuestionError(
            f"{label} opens a fenced block that it never closes; an open fence would hide "
            "the rest of the item file. Close the fence or remove it."
        )
    if LOOP_SECTION_END in body:
        raise QuestionError(
            f"{label} contains {LOOP_SECTION_END}, the line that ends a legacy {LEGACY_HEADING} "
            "section. Remove it."
        )
    if not body:
        raise QuestionError(f"{label} needs the question, the options and the evidence")
    flags = fence_flags_any_indent(body)
    unfenced = [line for line, fenced in zip(lines, flags) if not fenced]
    if any(_THEMATIC_BREAK_RE.match(line) for line in unfenced):
        raise QuestionError(
            f"{label} has a thematic-break line (`---`, `***` or `___`); it would end the "
            f"{QUESTIONS_HEADING} section before the block's Answer: line. Reword or remove that line."
        )
    if any(_ANSWER_LINE_RE.match(line) or _EMPTY_ANSWER_RE.match(line) for line in unfenced):
        raise QuestionError(
            f"{label} has an `Answer:` line; the question block would read as answered, or the "
            "answer would land inside the question. Reword that line."
        )
    return body


def _target_refusal(text: str) -> str | None:
    """Why LF item text cannot take a new block, or None when it can."""
    if fence_left_open(text):
        return "opens a fenced block it never closes, so a new block would be hidden inside it"
    lines = text.split("\n")
    if lines and lines[0].rstrip() == "---" and not any(line.rstrip() == "---" for line in lines[1:]):
        return "opens a frontmatter block it never closes, so a new block has no safe place"
    return None


def check_question_target(path: Path) -> None:
    """Raise QuestionError when the item file cannot take a new block; write nothing."""
    reason = _target_refusal(_read(path)[0])
    if reason is not None:
        raise QuestionError(f"the item file {path.name} {reason}. Repair the file first.")


def _questions_span(text: str) -> tuple[int, int] | None:
    """Character span of the first `## Open Questions` section, or None."""
    spans = loop_sections(text, (QUESTIONS_TITLE,))
    return (spans[0][0], spans[0][1]) if spans else None


def _q_number(line: str) -> int:
    return int(_QUESTION_HEADING_RE.match(line).group(0)[len("### Q"):])


def _blocks(section: str) -> tuple[list[str], list[bool], list[tuple[int, int]]]:
    """The section's lines, their fence flags, and each `### Q` block's line range."""
    lines = section.split("\n")
    flags = fence_flags_any_indent(section)
    starts = [i for i, line in enumerate(lines) if not flags[i] and _QUESTION_HEADING_RE.match(line)]
    ranges = [(s, starts[n + 1] if n + 1 < len(starts) else len(lines)) for n, s in enumerate(starts)]
    return lines, flags, ranges


def _answered(lines: list[str], flags: list[bool], start: int, end: int) -> bool:
    return any(not flags[i] and _ANSWER_LINE_RE.match(lines[i]) for i in range(start + 1, end))


def _block_lines(number: int, run_id: str, question: str) -> list[str]:
    return [
        f"### Q{number}. {_LOOP_TITLE}{run_id})",
        f"<!-- loop-decision run={run_id} -->",
        *question.split("\n"),
        "",
        "Answer:",
    ]


def _insert_block(text: str, run_id: str, question: str) -> str:
    """Return LF text with one block added under `## Open Questions`.

    An existing section gets the block at its end, numbered one past its
    highest `### Q`; a section that reads `None.` or is blank has that
    content replaced. With no section, one is inserted before `## Related`,
    else before the footer's thematic break, else at the end.
    """
    span = _questions_span(text)
    if span is not None:
        start, end = span
        lines, _flags, ranges = _blocks(text[start:end])
        body = lines[1:]
        while body and not body[-1].strip():
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
        filled = [line.strip().lower() for line in body if line.strip()]
        if not ranges and (not filled or filled in ([form] for form in _EMPTY_FORMS)):
            body = []
        number = max((_q_number(lines[s]) for s, _e in ranges), default=0) + 1
        new = [lines[0], "", *body, *([""] if body else []), *_block_lines(number, run_id, question)]
        rest = text[end:]
        return text[:start] + "\n".join(new) + "\n" + ("\n" if rest else "") + rest
    section = [QUESTIONS_HEADING, "", *_block_lines(1, run_id, question)]
    lines = text.split("\n")
    flags = fence_flags_any_indent(text)
    at = next(
        (i for i, line in enumerate(lines) if not flags[i] and line.rstrip() == RELATED_HEADING), None
    )
    if at is None:
        # The footer's thematic break: the last one with no level-1 or level-2
        # heading after it, below the frontmatter's closing `---`.
        body_start = 0
        if lines and lines[0].rstrip() == "---":
            body_start = next((i + 1 for i in range(1, len(lines)) if lines[i].rstrip() == "---"), 0)
        for i in range(len(lines) - 1, body_start - 1, -1):
            if flags[i]:
                continue
            if TOP_HEADING_RE.match(lines[i]):
                break
            if _THEMATIC_BREAK_RE.match(lines[i]):
                at = i
                break
    if at is None:
        head = text.rstrip("\n")
        return (head + "\n\n" if head else "") + "\n".join(section) + "\n"
    before = lines[:at]
    while before and not before[-1].strip():
        before.pop()
    return "\n".join([*before, *([""] if before else []), *section, "", *lines[at:]])


def append_question(path: Path, run_id: str, text: str) -> str:
    """Write one `### Q{n}. Loop decision (run {run_id})` block into the item file.

    Returns "appended", or "same_run" when a block tagged with this run id
    already stands under `## Open Questions` (nothing is written, so a
    retry never stacks a second copy). The text passes
    `validate_question_text` first, and the file passes
    `check_question_target`: a fence or a frontmatter block that never
    closes is refused, because the block would have no safe place.
    Raises QuestionError on a refusal, before any write.
    """
    question = validate_question_text(text)
    body, eol = _read(path)
    reason = _target_refusal(body)
    if reason is not None:
        raise QuestionError(f"the item file {path.name} {reason}. Repair the file first.")
    span = _questions_span(body)
    if span is not None:
        lines, flags, _ranges = _blocks(body[span[0]:span[1]])
        tag = f"<!-- loop-decision run={run_id} -->"
        if any(not flags[i] and line.strip() == tag for i, line in enumerate(lines)):
            return QUESTION_SAME_RUN
    _write(path, _insert_block(body, run_id, question), eol)
    return QUESTION_APPENDED


def _legacy_parts(section: str) -> tuple[str, str]:
    """`(run id, question text)` of one `## Loop Decision Needed` section.

    The question is every line after the heading except the loop's marker
    lines and the loop's own callout: the first run of `>` lines, when
    only blank and marker lines stand above it. Every later `>` line is the
    user's text and is kept, and so are fenced lines.
    """
    lines = section.split("\n")
    flags = fence_flags_any_indent(section)
    run_id = UNKNOWN_RUN
    kept: list[str] = []
    callout = "before"  # before -> inside -> done
    for line, fenced in zip(lines[1:], flags[1:]):
        if fenced:
            callout = "done"
            kept.append(line)
            continue
        content = line.rstrip()
        tag = _TAG_RE.fullmatch(content)
        if tag and run_id == UNKNOWN_RUN:
            run_id = tag.group(1)
        if _LOOP_MARKER_RE.match(content):
            continue
        if content.startswith(">") and callout != "done":
            callout = "inside"
            continue
        if callout == "inside" or content.strip():
            callout = "done"
        kept.append(content)
    return run_id, "\n".join(kept).strip("\n")


def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in reversed(spans):
        head, tail = text[:start].rstrip("\n"), text[end:].lstrip("\n")
        text = tail if not head else head + "\n" if not tail else head + "\n\n" + tail
    return text


def fold_item(path: Path, dry_run: bool = False) -> dict:
    """Fold every legacy section of one item file into `### Q` blocks.

    Returns `{"status", "sections", "runs"}` with status `none` (nothing to
    fold), `planned` (dry run), `folded`, or `refused` (with `reason`;
    nothing written).
    """
    text, eol = _read(path)
    sections = loop_sections(text, LOOP_WRITTEN_HEADINGS)
    if not sections:
        return {"status": "none", "sections": 0, "runs": []}
    parts = [_legacy_parts(text[start:end]) for start, end, _bounded in sections]
    runs = [run for run, _question in parts]
    refused = {"status": "refused", "sections": len(parts), "runs": runs}
    reason = _target_refusal(text)
    if reason is not None:
        return {**refused, "reason": f"the item file {reason}"}
    try:
        questions = [
            validate_question_text(question, f"the question of run {run}", None) for run, question in parts
        ]
    except QuestionError as exc:
        return {**refused, "reason": str(exc)}
    folded = _remove_spans(text, [(start, end) for start, end, _bounded in sections])
    for run, question in zip(runs, questions):
        folded = _insert_block(folded, run, question)
    if not dry_run:
        _write(path, folded, eol)
    return {"status": "planned" if dry_run else "folded", "sections": len(parts), "runs": runs}


def answer_question(path: Path, number: int, text: str, today: str | None = None) -> None:
    """Fill the empty `Answer:` line of `### Q{number}.` with `Answer: {date}: {text}`.

    Later lines of a multi-line text are indented two spaces. Raises
    QuestionError, before any write, on an empty text, a heading line, an
    unfenced thematic-break line in the text (it would end the section), an
    unclosed fence (in the text, the item file, or the item as it would be
    written), an absent block, an answered block, or a block with no empty
    `Answer:` line.
    """
    answer = text.replace("\r\n", "\n").strip()
    if not answer:
        raise QuestionError("the answer text is empty")
    if any(_ANY_HEADING_RE.match(line) for line in answer.split("\n")):
        raise QuestionError("the answer text has a heading line; reword or indent that line")
    if fence_left_open(answer):
        raise QuestionError("the answer text opens a fenced block that it never closes")
    answer_lines = answer.split("\n")
    if any(
        not fenced and _THEMATIC_BREAK_RE.match(line)
        for line, fenced in zip(answer_lines, fence_flags_any_indent(answer))
    ):
        raise QuestionError(
            f"the answer text has a thematic-break line (`---`, `***` or `___`); it would end the "
            f"{QUESTIONS_HEADING} section. Reword or remove that line."
        )
    body, eol = _read(path)
    if fence_left_open(body):
        raise QuestionError(f"the item file {path.name} opens a fenced block it never closes")
    span = _questions_span(body)
    if span is None:
        raise QuestionError(f"the item file {path.name} has no {QUESTIONS_HEADING} section")
    lines, flags, ranges = _blocks(body[span[0]:span[1]])
    block = next(((s, e) for s, e in ranges if _q_number(lines[s]) == number), None)
    if block is None:
        raise QuestionError(f"Q{number} is not in the {QUESTIONS_HEADING} section of {path.name}")
    if _answered(lines, flags, *block):
        raise QuestionError(f"Q{number} is already answered")
    at = next((i for i in range(block[0] + 1, block[1]) if not flags[i] and _EMPTY_ANSWER_RE.match(lines[i])), None)
    if at is None:
        raise QuestionError(f"Q{number} has no empty Answer: line")
    first, *rest = answer.split("\n")
    date = today or datetime.now().astimezone().date().isoformat()
    lines[at:at + 1] = [f"Answer: {date}: {first}", *(("  " + line) if line.strip() else "" for line in rest)]
    result = body[:span[0]] + "\n".join(lines) + body[span[1]:]
    if fence_left_open(result):
        # A fence opened on the Answer: line itself is not a fence, so its
        # closing line, indented, would open one instead.
        raise QuestionError(
            "the answer would leave a fenced block open in the item file; "
            "start the answer with a plain line and put the fence on the lines after it"
        )
    _write(path, result, eol)


def unanswered_questions(text: str) -> list[dict]:
    """Every unanswered `### Q` block of LF item text: `{"q", "question", "options"}`."""
    span = _questions_span(text)
    if span is None:
        return []
    lines, flags, ranges = _blocks(text[span[0]:span[1]])
    found = []
    for start, end in ranges:
        if _answered(lines, flags, start, end):
            continue
        title = lines[start][_QUESTION_HEADING_RE.match(lines[start]).end():].lstrip(". ").strip()
        body = [lines[i].strip() for i in range(start + 1, end) if not flags[i] and lines[i].strip()]
        body = [line for line in body if not _LOOP_MARKER_RE.match(line)]
        if not title or title.startswith(_LOOP_TITLE):
            title = next((line for line in body if not _EMPTY_ANSWER_RE.match(line)), title)
        options = next((line for line in body if line.startswith("Options:")), None)
        found.append({"q": _q_number(lines[start]), "question": title, "options": options})
    return found


def _item_paths(config: dict, item_id: str | None = None) -> list[tuple[str, Path]]:
    """`(id, path)` of every item file the backlog index names, or of one id."""
    found: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for row in _read_hub_family_items(config["_index_path"], config["_backlog_dir"]):
        if item_id is not None and normalize_id(row["id"]) != normalize_id(item_id):
            continue
        path = get_first_file_path(row, config["_backlog_dir"])
        if path is None or not path.exists() or path in seen:
            continue
        seen.add(path)
        found.append((row["id"], path))
    return found


def _one_item(config: dict, item_id: str) -> Path:
    items = _item_paths(config, item_id)
    if len(items) != 1:
        raise QuestionError(f"--id {item_id} needs exactly one item file; found {len(items)}")
    return items[0][1]


def cmd_fold(args, config: dict) -> tuple[list[str], dict, int]:
    if bool(args.id) == bool(args.all):
        raise QuestionError("--fold needs exactly one of --id N or --all")
    if args.id:
        _one_item(config, args.id)
    results = []
    for item_id, path in _item_paths(config, args.id):
        result = fold_item(path, dry_run=args.dry_run)
        if result["status"] != "none":
            results.append({"id": item_id, "file": path.name, **result})
    verb = "Would fold" if args.dry_run else "Folded"
    lines = []
    for result in results:
        if result["status"] == "refused":
            lines.append(f"Refused {result['id']}: {result['reason']}")
        else:
            lines.append(f"{verb} {result['id']}: {result['sections']} section(s), runs {', '.join(result['runs'])}")
    refused = [result["id"] for result in results if result["status"] == "refused"]
    done = len(results) - len(refused)
    lines.append(f"{verb} {done} item(s); refused {len(refused)}." + (" Nothing written." if args.dry_run else ""))
    payload = {"dry_run": args.dry_run, "items": results, "folded": done, "refused": refused}
    return lines, payload, EXIT_USAGE if refused else EXIT_OK


def cmd_answer(args, config: dict) -> tuple[list[str], dict, int]:
    if not args.id or args.q is None or args.text_file is None:
        raise QuestionError("--answer needs --id N, --q K and --text-file F")
    try:
        text = args.text_file.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise QuestionError(f"--text-file could not be read: {exc}")
    answer_question(_one_item(config, args.id), args.q, text)
    return [f"Answered {args.id} Q{args.q}."], {"id": args.id, "q": args.q, "answered": True}, EXIT_OK


def cmd_list(args, config: dict) -> tuple[list[str], dict, int]:
    if args.id:
        _one_item(config, args.id)
    questions: list[dict] = []
    legacy_items: list[str] = []
    legacy = 0
    for item_id, path in _item_paths(config, args.id):
        text, _eol_unused = _read(path)
        questions.extend({"id": item_id, **found} for found in unanswered_questions(text))
        count = len(loop_sections(text, LOOP_WRITTEN_HEADINGS))
        if count:
            legacy += count
            legacy_items.append(item_id)
    lines = []
    for found in questions:
        lines.append(f"{found['id']} Q{found['q']}: {found['question']}")
        if found["options"]:
            lines.append(f"  {found['options']}")
    lines.append(f"Unanswered questions: {len(questions)}")
    if legacy:
        lines.append(f"Legacy {LEGACY_HEADING} sections: {legacy} in {len(legacy_items)} item(s); run --fold --all first")
    payload = {"questions": questions, "legacy_sections": legacy, "legacy_items": legacy_items}
    return ([] if args.json else lines), payload, EXIT_OK


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; this module's usage exit is 1."""

    def error(self, message):
        raise QuestionError(f"usage error: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Open-question blocks in backlog item files.", allow_abbrev=False)
    parser.add_argument("--config", type=Path, default=None, help="Path to config.yaml.")
    parser.add_argument("--fold", action="store_true", help="Fold legacy Loop Decision Needed sections.")
    parser.add_argument("--answer", action="store_true", help="Answer one ### Q block.")
    parser.add_argument("--list", action="store_true", help="List the unanswered ### Q blocks.")
    parser.add_argument("--id", default=None, help="One item id.")
    parser.add_argument("--all", action="store_true", help="With --fold: every item the index names.")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="With --fold: write nothing.")
    parser.add_argument("--q", type=int, default=None, help="With --answer: the question number K.")
    parser.add_argument("--text-file", type=Path, default=None, dest="text_file",
                        help="With --answer: a file holding the answer text.")
    parser.add_argument("--json", action="store_true", help="With --list: print the JSON line only.")
    return parser


def _fix_stdout() -> None:
    encoding = getattr(sys.stdout, "encoding", None)
    if encoding and encoding.lower() != "utf-8" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _fix_stdout()
    try:
        args = build_parser().parse_args(argv)
        actions = [name for name in ("fold", "answer", "list") if getattr(args, name)]
        if len(actions) != 1:
            raise QuestionError("give exactly one of --fold, --answer, --list")
        try:
            config = load_config(Path(__file__), config_path=args.config)
        except FileNotFoundError as exc:
            raise QuestionError(str(exc))
        handler = {"fold": cmd_fold, "answer": cmd_answer, "list": cmd_list}[actions[0]]
        lines, payload, code = handler(args, config)
    except QuestionError as exc:
        lines, payload, code = [str(exc)], {"error": str(exc)}, EXIT_USAGE
    for line in lines:
        print(line)
    print(json.dumps(payload, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
