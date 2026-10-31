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
    CLASS_B <file> missing "<template line prefix>"
    CLASS_C <PATH parent> missing Scaffold-{Abbrev}/
    deviations: A=<n> B=<n> C=<n>

<file> is the path relative to PATH with forward slashes.

Classes:
    A  A `##` heading marked REQUIRED in the file kind's template is absent. Only
       orchestration, sprint and task files are graded. A Master Plan is never
       graded here, because a scaffolded one is written from a different template.
       A marker with a condition (`REQUIRED for DELEGATED mode`) is not graded.
    B  A required formatting line is absent: `**Total Estimated:**` and `**Mode:**`
       in an Orchestration, `**Total Sessions:**` in a Master Plan.
    C  PATH is an `Exec-{Abbrev}` folder and its parent holds no `Scaffold-{Abbrev}/`.
       For any other folder name Class C is not graded and the total prints C=0.

Headings and required lines count only outside a fence. Fence tracking resyncs as
`scaffold_plan.py check-headings` does, so one unbalanced fence cannot hide later headings.

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
CLASS_A_KINDS = ("orchestration", "sprint", "task")
REQUIRED_MARKER = re.compile(r"<!--\s*REQUIRED\s*-->\s*$")
# Class B lines: (file kind, field label). The prefix is read from the template line
# that carries the label at run time:
#   orchestration -> templates/orchestration.md `**Total Estimated:** ~{XX}K tokens`
#   orchestration -> templates/orchestration.md `**Mode:** {DIRECT | DELEGATED}`
#   master        -> templates/master-plan.md and templates/scaffolding-master-plan.md `**Total Sessions:**`
CLASS_B_LINES = (
    ("orchestration", "Total Estimated"),
    ("orchestration", "Mode"),
    ("master", "Total Sessions"),
)
EXEC_RE = re.compile(r"^Exec-(.+)$")


def template_body(templates_dir, kind):
    return sp.extract_body(Path(templates_dir) / sp.TEMPLATE_FILES[kind])


def required_headings(templates_dir):
    """Per graded kind: list of (heading text, pattern) for each H2 marked REQUIRED."""
    out = {}
    for kind in CLASS_A_KINDS:
        _pre, secs = sp.split_sections(template_body(templates_dir, kind))
        out[kind] = [(sp.norm_heading(s[0]), sp.heading_pattern(sp.norm_heading(s[0])))
                     for s in secs if REQUIRED_MARKER.search(s[0].rstrip("\r"))]
    return out


def line_prefixes(templates_dir):
    """Per kind: the `**Label:**` prefixes read from the template lines named in CLASS_B_LINES."""
    out = {}
    for kind, label in CLASS_B_LINES:
        pat = re.compile(r"^(\*\*" + re.escape(label) + r":\*\*)")
        prefix = next((m.group(1) for ln in template_body(templates_dir, kind).split("\n")
                       if (m := pat.match(ln))), None)
        if prefix is None:
            raise ValueError(f"template for kind {kind} has no line starting **{label}:**")
        out.setdefault(kind, []).append(prefix)
    return out


class PlanReadError(Exception):
    """A plan file could not be read or decoded."""


def outside_fence(text, patterns):
    """Return (H2 headings, other lines), both outside any fence.

    Fence tracking resyncs the way `scaffold_plan.check_text` does. An H2 met inside
    a fence counts, and resets the depth, when it matches a template heading and the
    fence never closes later. One unbalanced fence then cannot hide every later heading.
    """
    heads, plain, depth = [], [], 0
    lines = text.split("\n")
    for k, ln in enumerate(lines):
        if ln.startswith("## "):
            h = sp.norm_heading(ln)
            if depth and (not sp._matches(h, patterns) or sp._fence_closes_later(lines, k, depth)):
                continue
            depth = 0
            heads.append(h)
            continue
        after = sp.fence_step(ln, depth)
        if depth == 0 and after == 0:
            plain.append(ln)
        depth = after
    return heads, plain


def class_a(heads, required):
    return [h for h, pat in required
            if not any(pat == x if isinstance(pat, str) else pat.match(x) for x in heads)]


def class_b(plain, prefixes):
    return [p for p in prefixes if not any(ln.startswith(p) for ln in plain)]


def load_templates(templates_dir):
    required = required_headings(templates_dir)
    prefixes = line_prefixes(templates_dir)
    patterns = {kind: pats for kind, (pats, _catch) in sp.template_heading_sets(templates_dir).items()}
    return required, prefixes, patterns


def scan(root, tpl):
    required, prefixes, patterns = tpl
    findings = []
    for f in sp.collect_plan_files([root]):
        kind = sp.file_kind(str(f))
        if kind is None or kind == "recovery":
            continue
        rel = f.relative_to(root).as_posix()
        try:
            text = sp.read_lf(f)
        except (OSError, UnicodeDecodeError) as exc:
            raise PlanReadError(f"cannot read plan file {rel}: {exc}") from exc
        heads, plain = outside_fence(text, patterns[kind])
        if kind in CLASS_A_KINDS:
            findings += [("A", f'CLASS_A {rel} missing "{h}"') for h in class_a(heads, required[kind])]
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
