#!/usr/bin/env python3
"""Executable-shape reading of one backlog item: its refined sections and the shape gate.

A refined item carries three `##` sections: `## Resolution` (the chosen
solution as numbered steps), `## Verification` (a fenced command block) and
`## Open Questions` (absent, or `None.`). This module reads those sections
from an item body and reports whether the item passes the shape gate the
backlog router checks before it routes a refined item to a task list.

This is a library with no CLI. It reads no file. The backlog router
(`score_backlog`) imports this module and re-exports its public names, and
this module imports nothing from the router. Fence detection builds on the
shared scanner in `scoped_rules` (`fence_flags`), so the router and the loop
writers agree on every fence indented 0 to 3 spaces. A fence indented 4 or
more spaces, such as one nested under a list bullet, is recognised here too
(`fence_flags_any_indent`).
"""

import re

# The private blanking helper is imported, not copied: scoped_rules owns the
# one implementation of blanking the fences its scanner finds.
from scoped_rules import _blank_fenced_blocks as _blank_shared_fences
from scoped_rules import fence_flags, strip_loop_sections

_H2_RE = re.compile(r"^## ")
# The three sections of a refined (executable) item: the chosen solution with
# numbered steps, the verification recipe, and the open questions.
REFINED_SECTION_HEADINGS: tuple[str, ...] = ("Resolution", "Verification", "Open Questions")
# An open question inside `## Open Questions` is a `### Q{n}` block; it is
# answered when a line like `Answer: {text}` follows its heading. The answer
# text must hold a character other than `*` or whitespace, so a bare
# `**Answer:**` (the closing `**` and nothing else) is not an answer.
_QUESTION_HEADING_RE = re.compile(r"^### Q\d+")
_ANSWER_LINE_RE = re.compile(r"^\s*(?:[-*]\s+)?\*{0,2}Answer\*{0,2}\s*:[\s*]*[^\s*]")
# A thematic break (`---`, `***`, `___`) on its own line. It ends the
# `## Open Questions` reading, so an item footer after it is not a question.
_THEMATIC_BREAK_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*\r?$")
# The empty forms of `## Open Questions`, compared lower-case.
_EMPTY_QUESTIONS = ("none", "none.")
_NUMBERED_RE = re.compile(r"^(\d+)\.\s")
# A fence line at any indent: leading whitespace, a run of 3+ backticks or
# 3+ tildes, then the rest of the line.
_ANY_INDENT_FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})(.*)$")
# The indent at which the shared scanner stops recognising a fence.
_DEEP_FENCE_INDENT = 4
# YAML 1.1 spellings of true, compared lower-case, for a flag read as text.
_TRUE_TEXT = ("true", "yes", "on", "y")


def _indent_width(prefix: str) -> int:
    """Column width of a run of leading spaces and tabs (a tab is 4 columns)."""
    return len(prefix.expandtabs(4))


def fence_flags_any_indent(text: str) -> list[bool]:
    """One flag per line of `text.split("\\n")`: True when the line is fenced.

    Every line `scoped_rules.fence_flags` marks fenced is fenced here too,
    and those lines are left to that scanner alone, so the two agree on
    every fence indented 0 to 3 spaces. On the lines it marks unfenced, a
    fence indented 4 or more spaces also opens (a fence nested under a list
    bullet; a backtick fence's info string holds no backtick). It closes on
    a line of the same character, at least as many times, with nothing
    after but whitespace (the CommonMark close rule), at any indent. Every
    line between, whatever its indent, is fenced. The fence also ends before
    a line the shared scanner marks fenced, and otherwise runs to the end of
    the text.
    """
    shared = fence_flags(text)
    flags = list(shared)
    fence: tuple[str, int] | None = None  # (character, run length) of an open deep fence
    for index, line in enumerate(text.split("\n")):
        if shared[index]:
            fence = None
            continue
        match = _ANY_INDENT_FENCE_RE.match(line)
        if fence is not None:
            flags[index] = True
            if (
                match
                and match.group(2)[0] == fence[0]
                and len(match.group(2)) >= fence[1]
                and not match.group(3).strip()
            ):
                fence = None
            continue
        if (
            match
            and _indent_width(match.group(1)) >= _DEEP_FENCE_INDENT
            and not (match.group(2)[0] == "`" and "`" in match.group(3))
        ):
            fence = (match.group(2)[0], len(match.group(2)))
            flags[index] = True
    return flags


def _blank_fenced_blocks(body: str) -> str:
    """Return `body` with every fenced code block's lines blanked out.

    Line positions are preserved (each stripped line becomes an empty
    string) so a line number reported from the result still points into the
    original body. A heading, numbered step, or keyword quoted inside a
    template block, a pseudocode fence, or a WRONG/CORRECT exemplar is text
    the item *shows*, not a property the item *has*; counting it would
    classify an item by the examples it carries.

    The fences indented 0 to 3 spaces are blanked by
    `scoped_rules._blank_fenced_blocks`, the blanking the backlog loop's
    writers use, so the router and the loop agree on every such fence. The
    deeper fences `fence_flags_any_indent` adds are then blanked as well.
    """
    shared = _blank_shared_fences(body).split("\n")
    return "\n".join("" if fenced else line for line, fenced in zip(shared, fence_flags_any_indent(body)))


def _longest_numbered_run(text: str) -> tuple[int, int]:
    """(total top-level numbered items, longest consecutively-numbered run).

    A run continues while each numbered line's number is exactly one more
    than the previous numbered line's, whatever sits between them (nested
    bullets, prose, blank lines). The longest run is the closest mechanical
    reading of "discrete steps". It also feeds SUB_ITEMS, because a list is a
    run: two lists of 2 and 4 are not 6 parts of the work. The total stays
    in the report as `numbered_items`.
    """
    total = 0
    longest = 0
    run = 0
    previous: int | None = None
    for line in text.split("\n"):
        match = _NUMBERED_RE.match(line)
        if not match:
            continue
        number = int(match.group(1))
        total += 1
        run = run + 1 if previous is not None and number == previous + 1 else 1
        previous = number
        longest = max(longest, run)
    return total, longest


def _section_spans(blanked: str) -> dict[str, tuple[int, int]]:
    """`{heading: (start line, end line)}` for every `##` section of a blanked body.

    The span runs from the heading line up to the next `##` heading or the
    end of the body. When a heading repeats, the first section keeps it.
    """
    lines = blanked.split("\n")
    starts = [(index, line[3:].rstrip()) for index, line in enumerate(lines) if _H2_RE.match(line)]
    spans: dict[str, tuple[int, int]] = {}
    for position, (start, name) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        spans.setdefault(name, (start, end))
    return spans


def read_item_sections(body: str, blanked: str | None = None) -> dict[str, str]:
    """Every `##` section of `body`, keyed by its heading text.

    A heading is detected over `_blank_fenced_blocks(body)`, so a `## `
    line inside a fenced example never opens a section. Each value is the
    original text from the heading line up to the next `##` heading or the
    end of the body. When a heading repeats, the first section keeps it.
    A caller that already blanked `body` passes the result as `blanked`.
    """
    lines = body.split("\n")
    spans = _section_spans(_blank_fenced_blocks(body) if blanked is None else blanked)
    return {name: "\n".join(lines[start:end]) for name, (start, end) in spans.items()}


def _reads_true(value) -> bool:
    """True for the YAML boolean `True` and for the text `true`, `yes`, `on`
    or `y` in any case (the YAML 1.1 truthy spellings), so a flag read as
    text when PyYAML is absent means what PyYAML would have typed."""
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() in _TRUE_TEXT


def _open_questions_state(section: str | None) -> str:
    """`absent`, `empty`, `unanswered` or `answered` for a `## Open Questions` section.

    `section` is the section's text with fenced blocks already blanked,
    heading line first. The reading stops at the first thematic break
    (`---`, `***`, `___` on its own line), so an item footer after the
    section is ignored. `empty` is a section with no `### Q` block whose
    first non-blank line is `None` or `None.` (any case), or which has no
    non-blank line at all. A section with `### Q` blocks is `answered` when
    every block carries an answer line and every non-blank line above the
    first block is `None` or `None.`, else `unanswered`: free text above the
    blocks is an open question with no block shape. Any other text opening
    a section with no block reads `unanswered` for the same reason.
    """
    if section is None:
        return "absent"
    lines: list[str] = []
    for line in section.split("\n")[1:]:
        if _THEMATIC_BREAK_RE.match(line):
            break
        lines.append(line)
    blocks: list[bool] = []
    preamble_open = False
    for line in lines:
        if _QUESTION_HEADING_RE.match(line):
            blocks.append(False)
        elif blocks and _ANSWER_LINE_RE.match(line):
            blocks[-1] = True
        elif not blocks and line.strip() and line.strip().lower() not in _EMPTY_QUESTIONS:
            preamble_open = True
    if blocks:
        return "answered" if all(blocks) and not preamble_open else "unanswered"
    rest = [line.strip() for line in lines if line.strip()]
    if not rest or rest[0].lower() in _EMPTY_QUESTIONS:
        return "empty"
    return "unanswered"


def compute_item_shape(frontmatter: dict, *, body: str | None = None, blanked: str | None = None) -> dict:
    """The executable-shape reading of one item: its `refined` and
    `needs_plan` flags and whether its refined sections pass the shape gate.

    Reads `frontmatter["_body"]` and the two flags; opens no file. The body
    is read with the loop-written sections removed
    (`scoped_rules.strip_loop_sections`). The route signals read a narrower
    body: they also leave out `## Open Questions`, and a refined item's
    large-scope signals read `## Resolution` only. The shape gate needs
    `## Open Questions`, so it keeps that section. A caller that already holds that stripped body passes it as `body`,
    and its fence-blanked form as `blanked`, so neither is computed twice.

    The gate passes when the item is refined, `## Resolution` holds at
    least one numbered step, `## Verification` holds a fenced block at any
    indent, and `## Open Questions` is absent or empty. `missing` names each
    failed part, in that order, and is empty when the gate passes or the
    item is not refined.
    """
    if body is None:
        body = strip_loop_sections(frontmatter.get("_body") or "")[0]
        blanked = None
    if blanked is None:
        blanked = _blank_fenced_blocks(body)
    lines = body.split("\n")
    blank_lines = blanked.split("\n")
    spans = _section_spans(blanked)
    refined = _reads_true(frontmatter.get("refined"))
    needs_plan = _reads_true(frontmatter.get("needs_plan"))

    def blanked_section(name: str) -> str | None:
        if name not in spans:
            return None
        start, end = spans[name]
        return "\n".join(blank_lines[start:end])

    resolution = blanked_section("Resolution")
    resolution_steps = _longest_numbered_run(resolution)[1] if resolution else 0
    # A fenced line is one the blanking emptied: blank now, not blank in the body.
    has_verification = "Verification" in spans and any(
        lines[index].strip() and not blank_lines[index]
        for index in range(*spans["Verification"])
    )
    open_questions = _open_questions_state(blanked_section("Open Questions"))

    shape_ok = (
        refined and resolution_steps >= 1 and has_verification
        and open_questions in ("absent", "empty")
    )
    missing: list[str] = []
    if refined and not shape_ok:
        if resolution_steps < 1:
            missing.append("## Resolution with at least one numbered step")
        if not has_verification:
            missing.append("## Verification")
        if open_questions not in ("absent", "empty"):
            missing.append("## Open Questions must be empty")
    return {
        "refined": refined,
        "needs_plan": needs_plan,
        "resolution_steps": resolution_steps,
        "has_verification": has_verification,
        "open_questions": open_questions,
        "shape_ok": shape_ok,
        "missing": missing,
    }
