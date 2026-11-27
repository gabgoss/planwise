#!/usr/bin/env python
"""Count the three scaffold deviation classes in a plan folder, reading the plan templates at run time.

The templates stay the single source of every heading and every required line.
This script imports their parsing from `scaffold_plan.py` and carries no heading
text of its own. The harmonizer runs it after a scaffold, and a proof run grades
a scaffold with it.

Command (run with `python -B`):

    check PATH [--templates DIR]
        PATH is one plan folder, normally `Exec-{Abbrev}/`. The script walks PATH
        for *.md, skips `Outputs/`, and takes each file's kind from its name as
        `scaffold_plan.py check-headings` does. --templates defaults to this
        plugin's own templates/ folder.

Output lines, one per deviation, then one total line that is always last:

    CLASS_A <file> missing "<template heading>"
    CLASS_B <file> missing "<template line prefix, checklist item or skeleton line>"
    CLASS_C <PATH parent> missing Scaffold-{Abbrev}/
    deviations: A=<n> B=<n> C=<n>

<file> is the path relative to PATH with forward slashes.

Classes:
    A  A graded `##` heading of the file kind's template is absent. Orchestration,
       sprint, task and Recovery files are graded. A Master Plan is never graded here,
       because a scaffolded one is written from a different template. Orchestration,
       sprint and task files are graded on the headings marked REQUIRED. A Recovery
       file is graded on every template `##` heading with no OPTIONAL marker.
       An Orchestration whose `**Mode:**` line reads DELEGATED is also graded on each `##`
       heading marked `REQUIRED for DELEGATED mode`. Any other conditional marker is not graded.
    B  A required template line is absent: `**Total Estimated:**` and `**Mode:**`
       in an Orchestration, `**Total Sessions:**` in a Master Plan, and each
       `- [ ] **{Label}**` item of the Orchestration template's
       `## Post-Session Checklist` section. A checklist item counts as present
       with its box empty or checked (`- [x]`), and only its bold label is
       compared, so a reworded label is reported as missing.
       In a DELEGATED Orchestration, each `##` line inside the fence of the template's
       `## Spawn-Prompt Skeleton` section is required inside that fence of the file. A
       trailing `(...)` note is ignored. With the section absent, Class A reports it.
    C  PATH is an `Exec-{Abbrev}` folder and its parent holds no `Scaffold-{Abbrev}/`.
       For any other folder name Class C is not graded and the total prints C=0.

Headings and required lines count only outside a fence, except the skeleton lines. Fence
tracking resyncs as `scaffold_plan.py check-headings` does, so one unbalanced fence cannot
hide later headings.

Exit codes: 0 clean, 1 one or more deviations, 2 PATH missing or not a folder, a
template unreadable (`ERROR: template unreadable`), or a plan file unreadable or not
UTF-8 (`ERROR: cannot read plan file <path>`).
"""

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a direct run must not grow scripts/__pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import scaffold_plan as sp

DEFAULT_TEMPLATES = sp.DEFAULT_TEMPLATES
# Kinds graded for Class A. The master kind is absent on purpose: file_kind maps every
# -Master-Plan.md to templates/master-plan.md, but a scaffolded Master Plan is written
# from templates/scaffolding-master-plan.md, whose headings differ.
CLASS_A_KINDS = ("orchestration", "sprint", "task", "recovery")
REQUIRED_MARKER = re.compile(r"<!--\s*REQUIRED\s*-->\s*$")
# templates/recovery.md marks no H2 REQUIRED. Every Recovery H2 that carries no
# OPTIONAL marker is required, so a Recovery file cut before its last required
# heading loses a graded one. A cut after that heading is not detected.
UNMARKED_KINDS = ("recovery",)
OPTIONAL_MARKER = re.compile(r"<!--\s*OPTIONAL\b")
# The Orchestration H2s marked `REQUIRED for DELEGATED mode` are graded only in an
# Orchestration whose `**Mode:**` line reads DELEGATED. They sit in the same dict
# as the bare-marker lists, under this key.
DELEGATED_MARKER = re.compile(r"<!--\s*REQUIRED for DELEGATED mode\s*-->\s*$")
DELEGATED_KEY = "orchestration-delegated"
# The `##` lines inside this section's ```markdown fence are body text of the spawn
# prompt, so no heading check sees them. Class B grades them in a DELEGATED Orchestration.
SKELETON_SECTION = "## Spawn-Prompt Skeleton"
FENCE_RUN_RE = re.compile(r"^(`{3,})(.*)$")
TRAILING_NOTE_RE = re.compile(r"\s*\(.*\)$")
# Class B lines: (file kind, field label). The prefix is read from the template line
# that carries the label at run time:
#   orchestration -> templates/orchestration.md `**Total Estimated:** ~{XX}K tokens`
#   orchestration -> templates/orchestration.md `**Mode:** {DIRECT | DELEGATED}`
#   master        -> templates/master-plan.md and templates/scaffolding-master-plan.md `**Total Sessions:**`
# Class B also grades the checklist items of one template section, per CLASS_B_CHECKLISTS:
#   orchestration -> templates/orchestration.md `## Post-Session Checklist`, every `- [ ] **{Label}**` line
# The labels are read from that section only, because the template carries other
# `- [ ] **...**` lines in other sections.
CLASS_B_LINES = (
    ("orchestration", "Total Estimated"),
    ("orchestration", "Mode"),
    ("master", "Total Sessions"),
)
CLASS_B_CHECKLISTS = (
    ("orchestration", "Post-Session Checklist"),
)
CHECKLIST_ITEM_RE = re.compile(r"^- \[ \] \*\*(.+?)\*\*")
EXEC_RE = re.compile(r"^Exec-(.+)$")


def template_body(templates_dir, kind):
    return sp.extract_body(Path(templates_dir) / sp.TEMPLATE_FILES[kind])


def _marked_headings(templates_dir, kind, marker):
    """The (heading text, pattern) of each H2 of the kind's template that carries `marker`."""
    _pre, secs = sp.split_sections(template_body(templates_dir, kind))
    return [(sp.norm_heading(s[0]), sp.heading_pattern(sp.norm_heading(s[0])))
            for s in secs if marker.search(s[0].rstrip("\r"))]


def required_headings(templates_dir):
    """Per graded kind: list of (heading text, pattern) for each required H2.

    A required H2 is one marked REQUIRED, or, for a kind in UNMARKED_KINDS, one
    with no OPTIONAL marker. The extra key DELEGATED_KEY holds the Orchestration
    H2s marked `REQUIRED for DELEGATED mode`, which `scan` grades only in a
    DELEGATED Orchestration.
    """
    out = {kind: _marked_headings(templates_dir, kind, REQUIRED_MARKER)
           for kind in CLASS_A_KINDS if kind not in UNMARKED_KINDS}
    for kind in UNMARKED_KINDS:
        _pre, secs = sp.split_sections(template_body(templates_dir, kind))
        out[kind] = [(sp.norm_heading(s[0]), sp.heading_pattern(sp.norm_heading(s[0])))
                     for s in secs if not OPTIONAL_MARKER.search(s[0])]
    out[DELEGATED_KEY] = _marked_headings(templates_dir, "orchestration", DELEGATED_MARKER)
    return out


def checklist_labels(templates_dir, kind, section):
    """The `- [ ] **{Label}**` labels of one `## {section}` section of the kind's template."""
    _pre, secs = sp.split_sections(template_body(templates_dir, kind))
    sec = next((s for s in secs if sp.norm_heading(s[0]) == f"## {section}"), None)
    if sec is None:
        raise ValueError(f"template for kind {kind} has no ## {section} section")
    labels = [m.group(1) for ln in sec[1:] if (m := CHECKLIST_ITEM_RE.match(ln.rstrip("\r")))]
    if not labels:
        raise ValueError(f"template for kind {kind} has no - [ ] **...** item under ## {section}")
    return labels


def line_prefixes(templates_dir):
    """Per kind: (reported line, pattern) for each required line Class B grades.

    The `**Label:**` prefixes come from the template lines named in CLASS_B_LINES. The
    checklist items come from the template sections named in CLASS_B_CHECKLISTS, and
    their pattern accepts an empty or a checked box.
    """
    out = {}
    for kind, label in CLASS_B_LINES:
        pat = re.compile(r"^(\*\*" + re.escape(label) + r":\*\*)")
        prefix = next((m.group(1) for ln in template_body(templates_dir, kind).split("\n")
                       if (m := pat.match(ln))), None)
        if prefix is None:
            raise ValueError(f"template for kind {kind} has no line starting **{label}:**")
        out.setdefault(kind, []).append((prefix, re.compile(re.escape(prefix))))
    for kind, section in CLASS_B_CHECKLISTS:
        for label in checklist_labels(templates_dir, kind, section):
            out.setdefault(kind, []).append(
                (f"- [ ] **{label}**", re.compile(r"- \[[ xX]\] \*\*" + re.escape(label) + r"\*\*")))
    return out


def skeleton_h2_lines(section):
    """The `## ` lines inside the first ```markdown fence of one section.

    `section` is the list of lines that starts at the SKELETON_SECTION heading. In the
    fence, a run at least as long as the opening one nests with an info string and
    closes without one. A shorter run is plain text, so a four-backtick skeleton may
    hold any ``` block.
    """
    found, run, depth, wanted = [], 0, 0, False
    for ln in section[1:]:
        m = FENCE_RUN_RE.match(ln)
        if depth:
            if m and len(m.group(1)) >= run:
                depth += 1 if m.group(2).strip() else -1
                if wanted and not depth:
                    break
            elif wanted and ln.startswith("## "):
                found.append(sp.norm_heading(ln))
        elif m:
            run, depth, wanted = len(m.group(1)), 1, m.group(2).strip() == "markdown"
        elif ln.startswith("## "):
            break
    return found


def holds_skeleton_line(held, line):
    """Whether `held` carries the template's skeleton line, with or without a task note.

    The trailing parenthetical is a note on both sides: `## Operational Ceiling Notice
    (tasks 01 and 02)` matches `## Operational Ceiling Notice`.
    """
    stem = TRAILING_NOTE_RE.sub("", line)
    return any(x == stem or (x.startswith(f"{stem} (") and x.endswith(")")) for x in held)


def skeleton_lines(templates_dir):
    """The skeleton `## ` lines of the Orchestration template."""
    body = template_body(templates_dir, "orchestration").split("\n")
    start = next((k for k, ln in enumerate(body) if sp.norm_heading(ln) == SKELETON_SECTION), len(body))
    lines = skeleton_h2_lines(body[start:])
    if not lines:
        raise ValueError(f"template for kind orchestration has no ## line in its {SKELETON_SECTION} fence")
    return lines


class PlanReadError(Exception):
    """A plan file could not be read or decoded."""


def outside_fence(text, patterns):
    """Return (H2 headings, other lines), both outside any fence.

    The headings are a dict from each heading to the index of its first line. Fence tracking resyncs the way `scaffold_plan.check_text` does. An H2 met inside
    a fence counts, and resets the depth, when it matches a template heading and the
    fence never closes later. One unbalanced fence then cannot hide every later heading.
    """
    heads, plain, depth = {}, [], 0
    lines = text.split("\n")
    for k, ln in enumerate(lines):
        if ln.startswith("## "):
            h = sp.norm_heading(ln)
            if depth and (not sp._matches(h, patterns) or sp._fence_closes_later(lines, k, depth)):
                continue
            depth = 0
            heads.setdefault(h, k)
            continue
        after = sp.fence_step(ln, depth)
        if depth == 0 and after == 0:
            plain.append(ln)
        depth = after
    return heads, plain


def class_a(heads, required):
    return [h for h, pat in required
            if not any(pat == x if isinstance(pat, str) else pat.match(x) for x in heads)]


def class_b(plain, checks):
    """The reported line of each check whose pattern matches no plain line at its start."""
    return [shown for shown, pat in checks if not any(pat.match(ln) for ln in plain)]


def load_templates(templates_dir):
    required = required_headings(templates_dir)
    prefixes = line_prefixes(templates_dir)
    patterns = {kind: pats for kind, (pats, _catch) in sp.template_heading_sets(templates_dir).items()}
    return required, prefixes, patterns, skeleton_lines(templates_dir)


def scan(root, tpl):
    required, prefixes, patterns, skeleton = tpl
    findings = []
    for f in sp.collect_plan_files([root]):
        kind = sp.file_kind(str(f))
        if kind is None:
            continue
        rel = f.relative_to(root).as_posix()
        try:
            text = sp.read_lf(f)
        except (OSError, UnicodeDecodeError) as exc:
            raise PlanReadError(f"cannot read plan file {rel}: {exc}") from exc
        heads, plain = outside_fence(text, patterns[kind])
        if kind in CLASS_A_KINDS:
            findings += [("A", f'CLASS_A {rel} missing "{h}"') for h in class_a(heads, required[kind])]
        if kind == "orchestration" and sp.DELEGATED_MODE_RE.search("\n".join(plain)):
            findings += [("A", f'CLASS_A {rel} missing "{h}"') for h in class_a(heads, required[DELEGATED_KEY])]
            if SKELETON_SECTION in heads:
                held = skeleton_h2_lines(text.split("\n")[heads[SKELETON_SECTION]:])
                findings += [("B", f'CLASS_B {rel} missing "{ln}"')
                             for ln in skeleton if not holds_skeleton_line(held, ln)]
        findings += [("B", f'CLASS_B {rel} missing "{p}"') for p in class_b(plain, prefixes.get(kind, []))]
    return findings


def class_c(root):
    m = EXEC_RE.match(root.name)
    if not m:
        return []
    abbrev = m.group(1)
    if (root.parent / f"Scaffold-{abbrev}").is_dir():
        return []
    return [("C", f"CLASS_C {root.parent.as_posix()} missing Scaffold-{abbrev}/")]


def cmd_check(args):
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"ERROR: not a folder: {args.path}")
        return 2
    try:
        tpl = load_templates(args.templates)
    except (OSError, UnicodeDecodeError, StopIteration, ValueError, KeyError) as exc:
        print(f"ERROR: template unreadable: {exc}")
        return 2
    try:
        findings = scan(root, tpl)
    except PlanReadError as exc:
        print(f"ERROR: {exc}")
        return 2
    findings += class_c(root)
    for _cls, line in findings:
        print(line)
    counts = {c: sum(1 for k, _ in findings if k == c) for c in "ABC"}
    print(f"deviations: A={counts['A']} B={counts['B']} C={counts['C']}")
    return 1 if findings else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Count scaffold deviation classes A, B and C in a plan folder.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="grade one plan folder")
    c.add_argument("path", metavar="PATH")
    c.add_argument("--templates", default=str(DEFAULT_TEMPLATES))
    args = ap.parse_args(argv)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
