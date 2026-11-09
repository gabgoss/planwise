#!/usr/bin/env python
"""Build a plan from its spec and bodies files on the skeleton `scaffold_plan.py` renders.

The spec holds metadata and the bodies files hold prose. This script renders the
skeleton in memory, lists what a bodies author must write, lints the bodies files
against that list, and writes the tree with the bodies in place. It carries no
template text of its own, with one exception: FIRST_KEPT_LINES holds the opening of
two template lines, because no template marker says where those two sections end.

Commands (run with `python -B`):

    keys --spec SPEC.json [--templates DIR]
        Render in memory and print the keys of every document, in tree order:
          doc <ID> markers=<n>
            marker <name> count=<n>      one line per name, first occurrence first
            headings: ## One | ### Two   the H2 and H3 headings outside a fence
        A last line reads `fill_markers=<n> docs=<n>`.
        Exit 0 printed, 2 refused (unreadable spec, spec lint error, render failure).

    lint --spec SPEC.json --bodies-dir DIR [--session SXX-YY] [--templates DIR]
        Check the bodies files in DIR against the rendered skeleton. Prints one
        `LINT: doc=<ID> key=<key>: <reason>` line per error, then the summary lines:
          plan missing=<n> errors=<n>
          session=<SXX-YY> keys_missing=<n> errors=<n>
        The `plan` line comes first and covers the MASTER and sprint documents, which
        belong to no session. Each session then prints one `session=` line, so a count
        of those lines is a count of sessions. --session limits the check to one
        session, or to the plan documents when its value is `PLAN`.
        Exit 0 clean, 1 no errors but a marker has no body, 2 refused or any error.

    build --spec SPEC.json --bodies-dir DIR --out PLAN_DIR --config FILE
          [--date YYYY-MM-DD] [--force] [--skip-index] [--templates DIR]
        Run the lint, substitute the bodies into the rendered tree, write the tree to
        PLAN_DIR, and write `<ABBREV>-build-manifest.json` beside the spec, or
        `<ABBREV>-META-build-manifest.json` for a Meta plan. Prints:
          built <n> files to <PLAN_DIR>; fill_remaining=<n>; surviving_placeholders=<n>
        `fill_remaining` equals the lint's `keys_missing` total, because a marker with
        no body stays in the file. The placeholder check reads the skeleton before the
        bodies go in, because a body may hold literal braces. --config must name a
        readable file and feeds the Token Saver steps and the index step. --date sets
        every date placeholder.

        After the write, five gates run in this order, and none stops the others:
          estimates   `token_saver_scan.main` with --scan --write-estimates, once per
                      session, naming each task file of that session with --task
          headings    `scaffold_plan.check_headings` over the tree
          deviations  `scaffold_deviations.scan` (Class A and B) and `class_c`
          scan        the Token Saver scan with --config
          index       `generate_plans_index.py --config FILE --write` as a subprocess,
                      because its `main()` takes no argv. --skip-index skips it.
                      A written index with no row for the built plan's folder is
                      a finding.
        Then `write_manifest(out, spec)` runs again, so the manifest covers the task
        files the estimates gate rewrote. The report, after the `built` line and any
        SURVIVING and STALE lines, holds one line per gate:
          gate=<name> status=<ok|finding|skipped> files=<n> <figures>
        `files` is the number of rendered files the gates were handed. At most 20
        indented detail lines follow a gate line, then `  +<k> more` when cut. The
        figures are `sessions= tasks= failed=` (estimates), `h2= stray=` (headings),
        `A= B= C=` (deviations), `green= notice= warn= critical= handled= exit=` (scan)
        and `exit=` (index). `failed` counts the sessions whose write-back exited
        non-zero or printed an `ERROR:` line or an unreadable entry, and one detail
        line names each such line. The scan maps its exit code 0 to ok and 1, 2 and 3
        to finding, with the code in the line. The report ends with the lines
          fill_remaining=<n>
          exit=<code>
        Exit 0 built clean, 1 built with a marker left, a placeholder surviving or a
        gate finding, 2 refused (nothing written), 3 a write failed. A failure at or
        after the first file write prints
          FAILED: the write stopped after <k> of <n> files (<reason>). ...
        runs no gate, and leaves a manifest of the files that landed. A manifest
        rewrite that fails after the gates also exits 3.

Document ids: `MASTER`, `S01` (Sprint Plan), `S01-01-ORCH`, `S01-01-RECOVERY`, and
`S01-01-03` (task 3 of session 01 of sprint 01).

Bodies format. A bodies file is Markdown. Each directive sits alone on one
line outside a fence. A directive inside a fence is body text. Three key grammars exist.

    <!-- doc: ID -->             opens a document block
    <!-- fill: name -->          opens the body of every occurrence of the marker
    <!-- fill: name [k] -->      opens the body of occurrence k only, counted from 1
    <!-- section: ## Heading --> opens the body of a section; H3 headings work too

One example per grammar, with illustrative names. `keys` prints the real ones:

    <!-- doc: S01-01-03 -->
    <!-- fill: Task Title -->              every occurrence of the marker
    Parse the input file.
    <!-- fill: Task Title [2] -->          the second occurrence only
    Parse the input and write the report.
    <!-- section: ## Notes for Agent -->   the whole section text
    Read the spec first.

A body runs to the next directive, without its outer blank lines. A marker name
compares after `scaffold_plan.norm` folds its whitespace, and it omits the marker's
braces. A heading compares as `keys` prints it. An indexed body wins over the bare
body for its occurrence. A section body replaces the text under its heading, so
every marker in that text counts as covered. The text ends where an omission of the
heading would end, so a marker past a first kept line (see Omission) still needs its
own body. A body the section text would replace is a lint error, so a section cannot
lose a fill or a child section. A bare fill with an occurrence outside the section
keeps a place to land, so it stays legal. Text before the first key of a document
block is not a body, and nothing reads it.

Discovery: `--bodies-dir` reads `<ABBREV>-bodies-plan.md` and every
`<ABBREV>-bodies-SXX-YY*.md`, sorted by name and merged by doc id. A `-part{n}`
suffix therefore adds documents to its session. Each doc id appears once.

Lint errors: an unknown doc; a fill name that occurs nowhere in the doc, or an index
past its count; a section heading absent from the doc; an H2 line outside a fence;
a key outside a document block; a key given twice in one doc; a doc id given twice;
a fence still open at the end of a file; a body inside the span of a section body.

Two rendered files with one doc id refuse all three commands. A task named `Recovery`
or `Orchestration` does this, because `scaffold_plan.file_kind` reads the file suffix.

`keys_missing` counts marker occurrences with no body, so it equals the markers a
build of that session leaves in place. A body with no non-space text counts as no body.

Omission: `omit_sections` on a task names sections of that task file. On a session it
names sections of the session's Orchestration and of each of its task files, and a
document without the heading stays as it is. The key at sprint or plan level is a
lint error. A name is a heading without its `#` marks and without its trailing marker
comment or `(Required ...)` tail. Only a template `##` or `###` heading whose marker
comment says CONDITIONAL, or whose text ends in `(Required when ...)` or
`(Required for ...)`, can be omitted, and `omittable_names` reads that list from the
templates at run time. Any other name is a lint error, and all three commands refuse
it. A cut runs from the heading to the next heading of equal or higher level, so an
H2 takes its H3 sections and its trailing `---` with it. An H3 keeps the `---` that
closes its parent. A cut ends sooner at the section's first kept line, when
FIRST_KEPT_LINES names one: the template sets text that belongs to the whole task
file under those headings. The cut leaves one line at the site:

    <!-- OMITTED: <heading> (spec omit_sections) -->

Omission comes first, so `keys` and `lint` see the tree `build` writes. A body for an
omitted marker or heading is therefore a lint error.

Manifest guard: the manifest maps each written path to its sha256. A rebuild reads it
first. When a listed file differs or is gone, or a new path would land on a file the
manifest does not list, `build` prints one `CHANGED: <path>` line each and exits 2.
A folder that holds files but has no manifest refuses the same way. --force overwrites
in every case. A rebuild never deletes a file that the spec no longer renders. The
manifest moves that path and its hash to its `stale` key, and every build prints one
`STALE: <path>` line until the file is gone. A path that returns to the spec with its
stale hash is no hand edit. A step that rewrites built files calls
`write_manifest(out, spec)` afterwards, so the final manifest matches the final tree.

Build spec format. The spec is the JSON that `scaffold_plan.py` documents under its
"Spec format" section, with its required keys and its lint rules. The build adds
four keys that `scaffold_plan.py` does not know: `meta`, `omit_sections`, `output_k`
and `working_k`. `core_spec` removes them at every level before it renders, so the
core lint never sees them. `scaffold_plan.py` knows `estimate_k` only as a number,
so `core_spec` computes an "auto" estimate first (see below).

    meta           plan level. true or false. See Meta plan below.
    omit_sections  task or session. Names of template sections to cut (Omission).
    estimate_k     task. A number as in `scaffold_plan.py`, or the string "auto".
    output_k       task. A number, in thousands of tokens.
    working_k      task. A number, in thousands of tokens.

Auto estimate. A task with `estimate_k: "auto"` gets the sum of its required_context
`tokens_k`, `output_k` and `working_k`, rounded half up as the write-back rounds, so
2.5 gives 3 where Python `round` gives 2. The session and sprint totals derive from
that figure. An auto task needs `output_k` and `working_k` as numbers, and each
`tokens_k` as a finite number that is not negative. A numeric task needs both keys
or neither. No default exists, so a missing addend is a spec error:
  LINT: task <id> (<name>): <reason>        exit 2, nothing written
`output_k` and `working_k` fill the task file's `{O}` and `{W}` markers on any
task, whatever its `estimate_k`, and a numeric figure stays as written. `keys`
stops listing a marker that a spec key fills, and `lint` and `keys_missing` stop
counting it. A body for a marker that a key fills is a lint error:
  LINT: doc=<ID> key=fill: O: <reason>
`--write-estimates` re-prices only the reads term from the live files and keeps
both addends. The header it leaves can differ from the spec figure, and a
difference never fails the build.

Meta plan. `meta` is on only for the JSON value true. A plan-level value that is
neither true nor false is a lint error. A session or task `meta` key has no effect.
`build` writes to `<out>/Meta-<ABBREV>/`, so `--out` names the parent folder. An
`--out` that already ends in `Meta-<ABBREV>` is refused with exit 2. The Master Plan
becomes `<ABBREV>-META-Master-Plan.md`, each Sprint Plan becomes
`<ABBREV>-META-S<XX>-Sprint-Plan.md`, and the plan-level `Outputs/.gitkeep` is added.
The same renames apply to every link and text, bodies included. A path under
`Exec-<ABBREV>/` keeps the plain name, because it names the Exec plan of the same
abbreviation. A longer name such as `<ABBREV>-Master-Plan-Notes.md` stays too. The
rename runs after the bodies go in, so `keys`, `lint` and the doc ids keep the plain
names (`MASTER`, `S01`). The manifest paths and the five gates read the meta root.
All three commands refuse a session whose mode is not DELEGATED and a session
`Outputs/` file that lacks the prefix `<ABBREV>-META-S<XX>-<YY>-`. An output under
the plan-level `Meta-<ABBREV>/Outputs/` folder is exempt from the prefix. A relative
output reads from its session folder, so `../../Outputs/<name>` is that folder too.
A Meta plan and an Exec plan can share an abbreviation and a spec folder, so a Meta
plan keeps its own manifest. Turning `meta` on for a plan already built therefore
writes a new tree and leaves the old tree and its manifest on disk.

Report. `build` prints, in this order: the `built` line, any SURVIVING and STALE
lines, the five gate lines with their detail lines, one delta line per task file,
then `fill_remaining=<n>` and `exit=<code>`. The delta line reads
  delta task=<doc id> spec=<n> measured=<n>
`spec` is the computed auto figure, or the numeric `estimate_k`. `measured` is the
`**Estimated Tokens:**` header read from the built file after the estimates gate,
and `none` stands for a missing value. A pair that differs is the signal to read.
A delta line never changes the exit code.
"""

import argparse
import copy
import hashlib
import json
import math
import posixpath
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.dont_write_bytecode = True  # a direct run must not grow scripts/__pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import scaffold_plan as sp

BUILD_KEYS = ("meta", "omit_sections", "output_k", "working_k")
AUTO_ESTIMATE = "auto"
AUTO_ESTIMATE_VALUE = 0  # the stand-in for an auto task whose addends are no numbers, which `estimate_errors` refuses
ESTIMATE_KEYS = ("output_k", "working_k")
ESTIMATE_MARKERS = ("O", "W")  # the `{O}` and `{W}` placeholders of the Context subtotal line, in the order of ESTIMATE_KEYS
HEADER_RE = re.compile(r"^\*\*Estimated Tokens:\*\*\s*~(\d+(?:\.\d+)?)K", re.MULTILINE)
PLAN_GROUP = "PLAN"

MARKER_RE = re.compile(r"<!-- FILL: \{(.*?)\} -->")
HEADING_TAIL_RE = re.compile(r"\s*<!--\s*(?:REQUIRED|OPTIONAL|CONDITIONAL)\b.*?-->\s*$")
DOC_FILE_RE = re.compile(r"^[^-]+-S(\d{2,})(?:-(\d{2,}))?(?:-(\d{2,}))?-")
SESSION_RE = re.compile(r"^(S\d{2,}-\d{2,})(?!\d)")

OMIT_KINDS = ("orchestration", "task")
CONDITIONAL_RE = re.compile(r"<!--.*\bCONDITIONAL\b")
REQUIRED_TAIL_RE = re.compile(r"\s*\(Required (?:when|for)\b.*\)\s*$")
SEPARATOR = "---"
# {omittable heading: the start of the first line under it that is not the section's own text}
FIRST_KEPT_LINES = {
    "Schema Pin": "> [!constraint] No `~?` Placeholders in Token Estimates",
    "Cross-Sprint Prerequisite Grep Gate": "**Mapping Disambiguation:**",
}

DOC_KEY_RE = re.compile(r"^<!--\s*doc:\s*(.+?)\s*-->\s*$")
FILL_KEY_RE = re.compile(r"^<!--\s*fill:\s*(.+?)(?:\s+\[(\d+)\])?\s*-->\s*$")
SECTION_KEY_RE = re.compile(r"^<!--\s*section:\s*(#+\s+.+?)\s*-->\s*$")


# ---------------------------------------------------------------- spec and skeleton

def _dicts(obj, key):
    value = obj.get(key) if isinstance(obj, dict) else None
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _num(value):
    """Whether `value` is a finite number that is not a boolean and not negative."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:  # a JSON integer past the float range
        return False


def read_costs(task):
    """The `tokens_k` value of each Required Context row of a task dict."""
    rows = task.get("required_context")
    return [r.get("tokens_k") for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def auto_figure(task):
    """`sum(tokens_k) + output_k + working_k` of a task dict, rounded half up, or AUTO_ESTIMATE_VALUE when an addend is no number."""
    addends = [*read_costs(task), task.get("output_k"), task.get("working_k")]
    if not all(_num(a) for a in addends):
        return AUTO_ESTIMATE_VALUE
    return int(sum(Decimal(str(a)) for a in addends).to_integral_value(rounding=ROUND_HALF_UP))


def core_spec(spec):
    """A copy of the spec holding only what `scaffold_plan.lint_spec` accepts.

    An "auto" estimate takes its computed figure here, before the render, so the session
    and sprint totals derive from it. Both addend keys are read before they are stripped.
    """
    core = copy.deepcopy(spec)
    sprints = _dicts(core, "sprints")
    sessions = [se for sprint in sprints for se in _dicts(sprint, "sessions")]
    tasks = [t for se in sessions for t in _dicts(se, "tasks")]
    for task in tasks:
        if task.get("estimate_k") == AUTO_ESTIMATE:
            task["estimate_k"] = auto_figure(task)
    for obj in [core, *sprints, *sessions, *tasks]:
        if isinstance(obj, dict):
            for key in BUILD_KEYS:
                obj.pop(key, None)
    return core


def _task_rows(spec):
    """[(doc id, task dict)] of a spec whose numbers and names passed `lint_spec`."""
    return [(f"S{sprint['number']:02d}-{session['number']:02d}-{task['number']:02d}", task)
            for sprint in _dicts(spec, "sprints") for session in _dicts(sprint, "sessions")
            for task in _dicts(session, "tasks")]


def estimate_errors(spec):
    """One lint error per task whose `output_k` and `working_k` are not both numbers, or whose auto figure cannot price a read.

    An "auto" estimate needs both, and a `tokens_k` that is finite and not negative
    on every row. A numeric estimate needs both or neither.
    """
    errors = []
    for doc, task in _task_rows(spec):
        auto = task.get("estimate_k") == AUTO_ESTIMATE
        if auto and not all(_num(value) for value in read_costs(task)):
            errors.append(f'task {doc} ({task["name"]}): estimate_k is "auto", so every required_context '
                          "tokens_k must be a finite number that is not negative")
        if not auto and not any(key in task for key in ESTIMATE_KEYS):
            continue
        bad = [key for key in ESTIMATE_KEYS if not _num(task.get(key))]
        if bad:
            need = 'estimate_k is "auto", so' if auto else "the task sets one of them, so"
            errors.append(f"task {doc} ({task['name']}): {need} output_k and working_k must both be numbers "
                          f"(not a number: {', '.join(bad)})")
    return errors


def task_figures(spec):
    """{doc id: (spec figure, {marker: text})} of a linted spec. The marker texts are empty without both keys."""
    figures = {}
    for doc, task in _task_rows(spec):
        fills = {}
        if all(_num(task.get(key)) for key in ESTIMATE_KEYS):
            fills = {name: f"{task[key]:g}" for name, key in zip(ESTIMATE_MARKERS, ESTIMATE_KEYS)}
        figure = auto_figure(task) if task.get("estimate_k") == AUTO_ESTIMATE else task.get("estimate_k")
        figures[doc] = (figure, fills)
    return figures


def doc_id(rel):
    """The doc id of a rendered path, or None for a path that is not a plan document."""
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    kind = sp.file_kind(name)
    if kind == "master":
        return "MASTER"
    m = DOC_FILE_RE.match(name)
    if kind is None or not m:
        return None
    sprint, session, task = m.groups()
    if kind == "sprint":
        return f"S{sprint}"
    if kind == "task":
        return f"S{sprint}-{session}-{task}"
    return f"S{sprint}-{session}-{'ORCH' if kind == 'orchestration' else 'RECOVERY'}"


def session_of(doc):
    """The lint group of a doc id: its SXX-YY session, or the plan group."""
    m = SESSION_RE.match(doc)
    return m.group(1) if m else PLAN_GROUP


def heading_text(line):
    """A heading as `keys` prints it: no trailing REQUIRED, OPTIONAL or CONDITIONAL marker."""
    return sp.norm(HEADING_TAIL_RE.sub("", line))


def heading_name(line):
    """A heading as `omit_sections` names it: no `#` marks, marker comment or Required tail."""
    return REQUIRED_TAIL_RE.sub("", heading_text(line)).lstrip("#").strip()


def heading_levels(lines, patterns):
    """{line index: level} of the H1, H2 and H3 headings outside a fence, in file order.

    An H2 inside a fence follows `scaffold_plan.check_text`: it is fence content unless
    it matches a template H2 and the fence never closes.
    """
    levels, depth = {}, 0
    for k, ln in enumerate(lines):
        if ln.startswith("## "):
            if not depth or (sp._matches(sp.norm_heading(ln), patterns)
                             and not sp._fence_closes_later(lines, k, depth)):
                depth, levels[k] = 0, 2
        elif ln.startswith("### ") and not depth:
            levels[k] = 3
        elif ln.startswith("# ") and not depth:
            levels[k] = 1
        else:
            depth = sp.fence_step(ln, depth)
    return levels


def span_end(levels, k, total):
    """The line index where the section opened at heading line k ends."""
    return next((j for j, level in levels.items() if j > k and level <= levels[k]), total)


def section_end(lines, levels, k):
    """Where the text of the section at heading line k ends, for omission, bodies and the lint alike."""
    end = span_end(levels, k, len(lines))
    kept = FIRST_KEPT_LINES.get(heading_name(lines[k]))
    return next((j for j in range(k + 1, end) if kept and lines[j].startswith(kept)), end)


def before_separator(lines, k, end):
    """The end of a span without the blank lines and the `---` that close it."""
    while end > k + 1 and not lines[end - 1].strip():
        end -= 1
    return end - 1 if end > k + 1 and lines[end - 1].strip() == SEPARATOR else end


def scan_doc(text, patterns):
    """Return (H2 and H3 headings outside a fence, markers as (name, H2, H3), (H3, its H2) pairs) in file order."""
    headings, markers, nested, h2, h3, h2_end, h3_end = [], [], [], None, None, 0, 0
    lines = text.split("\n")
    levels = heading_levels(lines, patterns)
    for k, ln in enumerate(lines):
        h2 = h2 if k < h2_end else None
        h3 = h3 if k < h3_end else None
        level = levels.get(k)
        if level == 2:
            h2, h2_end = heading_text(ln), section_end(lines, levels, k)
            headings.append(h2)
        elif level == 3:
            h3, h3_end = heading_text(ln), section_end(lines, levels, k)
            headings.append(h3)
            if h2:
                nested.append((h3, h2))
        markers.extend((sp.norm(name), h2, h3) for name in MARKER_RE.findall(ln))
    return headings, markers, nested


class DocIdError(ValueError):
    """Two rendered files share one doc id, so one document's bodies would reach the other."""


def doc_index(files, templates_dir=sp.DEFAULT_TEMPLATES):
    """{doc id: {"headings": [...], "markers": [(name, H2, H3), ...], "nested": [(H3, H2), ...]}} in tree order.

    Raise DocIdError when two files share a doc id.
    """
    sets = sp.template_heading_sets(templates_dir)
    index, owners = {}, {}
    for rel, text in files.items():
        doc = doc_id(rel)
        if doc is None:
            continue
        if doc in owners:
            raise DocIdError(f"doc id {doc} belongs to two files: {owners[doc]} and {rel}")
        owners[doc] = rel
        headings, markers, nested = scan_doc(text, sets[sp.file_kind(rel)][0])
        index[doc] = {"headings": headings, "markers": markers, "nested": nested}
    return index


# ---------------------------------------------------------------- omission

def omittable_names(templates_dir=sp.DEFAULT_TEMPLATES):
    """{file kind: [heading name, ...]} of the headings the templates let a spec omit."""
    sets = sp.template_heading_sets(templates_dir)
    names = {}
    for kind in OMIT_KINDS:
        lines = sp.extract_body(Path(templates_dir) / sp.TEMPLATE_FILES[kind]).split("\n")
        names[kind] = [heading_name(lines[k]) for k, level in heading_levels(lines, sets[kind][0]).items()
                       if level > 1 and (CONDITIONAL_RE.search(lines[k])
                                         or REQUIRED_TAIL_RE.search(heading_text(lines[k])))]
    return names


def _omit_names(item, label, allowed, errors):
    """The valid names of one `omit_sections` value. Add one error per invalid name."""
    value = item.get("omit_sections", [])
    if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
        errors.append(f"{label}: omit_sections must be a list of heading names")
        return []
    for name in value:
        if sp.norm(name) not in allowed:
            errors.append(f'{label}: omit_sections names "{name}", which is no CONDITIONAL or '
                          "(Required when|for ...) heading of its template")
    return [sp.norm(name) for name in value if sp.norm(name) in allowed]


def omit_plan(spec, allowed):
    """Return ({doc id: [heading name, ...]}, errors) for the spec's `omit_sections` keys."""
    plan, errors = {}, []
    if "omit_sections" in spec:
        errors.append("plan level: omit_sections belongs on a session or a task")
    for sprint in _dicts(spec, "sprints"):
        if "omit_sections" in sprint:
            errors.append(f"sprint {sprint['number']:02d} level: omit_sections belongs on a session or a task")
        for session in _dicts(sprint, "sessions"):
            sid = f"S{sprint['number']:02d}-{session['number']:02d}"
            shared = _omit_names(session, f"session {sid}", {*allowed["orchestration"], *allowed["task"]}, errors)
            plan[f"{sid}-ORCH"] = shared
            for task in _dicts(session, "tasks"):
                doc = f"{sid}-{task['number']:02d}"
                own = _omit_names(task, f"task {doc}", set(allowed["task"]), errors)
                plan[doc] = list(dict.fromkeys([*shared, *own]))
    return plan, errors


def omit_section(text, name, patterns):
    """Cut the named section and leave the OMITTED line. A doc without the heading stays as it is."""
    lines = text.split("\n")
    levels = heading_levels(lines, patterns)
    k = next((j for j, level in levels.items() if level > 1 and heading_name(lines[j]) == name), None)
    if k is None:
        return text
    end = section_end(lines, levels, k)
    if levels[k] > 2:
        end = before_separator(lines, k, end)
    head, tail = lines[:k], lines[end:]
    while head and not head[-1].strip():
        head.pop()
    while tail and not tail[0].strip():
        tail.pop(0)
    return "\n".join([*head, "", f"<!-- OMITTED: {name} (spec omit_sections) -->", "", *tail])


def omit_files(files, plan, templates_dir):
    """A copy of the rendered tree with every section of `plan` cut."""
    sets = sp.template_heading_sets(templates_dir)
    out = dict(files)
    for rel, text in files.items():
        for name in plan.get(doc_id(rel), ()):
            text = omit_section(text, name, sets[sp.file_kind(rel)][0])
        out[rel] = text
    return out


# ---------------------------------------------------------------- meta plans

META_MODE = "DELEGATED"
OUTPUTS_DIR = "Outputs"


def is_meta(spec):
    """Whether `spec` is a Meta plan. Only `true` at plan level switches it on."""
    return spec.get("meta") is True


def in_session_outputs(path, abbrev):
    """Whether a task output sits under an `Outputs/` folder other than the plan-level `Meta-<ABBREV>/Outputs/`.

    The path reads from its session folder, two folders below the meta root, so `../../Outputs/` is the plan level.
    """
    plain = path.replace("\\", "/").rstrip("/")
    folders = posixpath.normpath(f"Meta-{abbrev}/sprint/session/{plain}").split("/")[:-1]
    return any(name == OUTPUTS_DIR and folders[k - 1:k] != [f"Meta-{abbrev}"] for k, name in enumerate(folders))


def meta_errors(spec):
    """The errors of the plan-level `meta` key: a value that is no boolean, then under `true` one error
    per session that is not DELEGATED and per session output without the META prefix."""
    value = spec.get("meta", False)
    if not isinstance(value, bool):
        return [f"plan level: meta must be true or false, got {json.dumps(value)}"]
    errors, abbrev = [], spec["abbrev"]
    for sprint in _dicts(spec, "sprints") if value else ():
        for session in _dicts(sprint, "sessions"):
            sid = f"S{sprint['number']:02d}-{session['number']:02d}"
            prefix = f"{abbrev}-META-{sid}-"
            if session["mode"] != META_MODE:
                errors.append(f"session {sid}: mode is {session['mode']}, and a meta plan session must be {META_MODE}")
            for task in _dicts(session, "tasks"):
                errors.extend(f'task {sid}-{task["number"]:02d}: output "{path}" must start with {prefix}'
                              for path in task["outputs"] if in_session_outputs(path, abbrev)
                              and not path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].startswith(prefix))
    return errors


def meta_tree(files, abbrev):
    """The tree of a Meta plan: the two plan file kinds renamed, their tokens rewritten, and the plan `Outputs/` folder.

    One pattern serves the paths and the texts, so a link and the file it names cannot
    part. It also takes the `{Abbrev}-S{XX}-Sprint-Plan` form, because the task template
    prints that form as a literal example. The doc ids read the plain names, so this
    runs after the bodies go in. A path under `Exec-<ABBREV>/` matches first and stays
    whole, because the Exec plan keeps the plain names.
    """
    name = re.escape(abbrev)
    token = re.compile(rf"(?<![\w-])Exec-{name}[/\\][^\s()\[\]<>`'\",]*|(?<![\w-])({name}|\{{Abbrev\}})-"
                       r"(?=(?:Master-Plan|S(?:\d{2,}|\{XX\})-Sprint-Plan)(?![\w-]))")

    def rewrite(text):
        return token.sub(lambda m: f"{m.group(1)}-META-" if m.group(1) else m.group(0), text)

    tree = {rewrite(rel): rewrite(text) for rel, text in files.items()}
    tree[f"{OUTPUTS_DIR}/.gitkeep"] = ""
    return tree


def render_core(spec_path, templates_dir, date=None):
    """Lint the core spec, render it and cut its omissions. Print the refusal and return None on failure."""
    spec, err = sp.load_spec(spec_path)
    if err:
        print(f"REFUSED: {err}. Fix: pass a readable UTF-8 JSON spec.")
        return None
    core = core_spec(spec)
    try:
        errors = sp.lint_spec(core, templates_dir)
        if errors:
            for e in errors:
                print(f"LINT: {e}")
            print(f"REFUSED: {len(errors)} spec lint error(s). Fix: correct the spec, then re-run this command.")
            return None
        plan, errors = omit_plan(spec, omittable_names(templates_dir))
        if errors:
            for e in errors:
                print(f"LINT: {e}")
            print(f"REFUSED: {len(errors)} omit_sections error(s). Fix: name only an omittable heading.")
            return None
        errors = meta_errors(spec)
        if errors:
            for e in errors:
                print(f"LINT: {e}")
            print(f"REFUSED: {len(errors)} meta plan error(s). Fix: correct the meta value, the session mode or the output name.")
            return None
        errors = estimate_errors(spec)
        if errors:
            for e in errors:
                print(f"LINT: {e}")
            print(f"REFUSED: {len(errors)} estimate error(s). Fix: give the task both output_k and working_k as numbers, "
                  "and each tokens_k a finite figure that is not negative.")
            return None
        files, _rec = sp.render_all(core, templates_dir, date)
        files = omit_files(files, plan, templates_dir)
        return core, files, doc_index(files, templates_dir)
    except DocIdError as exc:
        print(f"REFUSED: {exc}. Fix: rename the task, so its file name ends in no session or plan document suffix.")
        return None
    except (OSError, UnicodeDecodeError, *sp.SPEC_VALUE_ERRORS) as exc:
        reason = " ".join(f"{type(exc).__name__}: {exc}".split())
        print(f"REFUSED: the render failed ({reason}). Fix: correct the spec or the --templates folder.")
        return None


# ---------------------------------------------------------------- bodies files

def _key_label(name, k):
    return f"fill: {name}" if k is None else f"fill: {name} [{k}]"


def _new_doc(source):
    return {"source": source, "fills": {}, "sections": {}}


def parse_bodies(text, source="bodies"):
    """Return (docs, errors) for one bodies file.

    docs is {doc id: {"source", "fills": {(name, k or None): body}, "sections": {heading: body}}}.
    errors is a list of (doc id or None, message).
    """
    docs, errors = {}, []
    doc, label, slot, key, buf, depth = None, "none", None, None, [], 0

    def close():
        if slot is not None:
            text = "\n".join(buf).strip("\n")
            slot[key] = text if text.strip() else ""  # no non-space text is no body, for every later check
        buf.clear()

    def open_key(table, new_key, new_label):
        nonlocal slot, key, label
        close()
        label = new_label
        if doc is None:
            errors.append((None, f"doc=none key={new_label}: the key sits outside a document block in {source}"))
            slot = None
        elif new_key in table:
            errors.append((doc, f"doc={doc} key={new_label}: the key appears twice in this doc"))
            slot = None
        else:
            slot, key = table, new_key

    for ln in text.split("\n"):
        hit = None
        if not depth:
            hit = DOC_KEY_RE.match(ln) or FILL_KEY_RE.match(ln) or SECTION_KEY_RE.match(ln)
        if hit and hit.re is DOC_KEY_RE:
            close()
            slot, label, doc = None, "none", hit.group(1)
            if doc in docs:
                errors.append((doc, f"doc={doc} key=doc: the doc id appears twice in {source}"))
            docs.setdefault(doc, _new_doc(source))
        elif hit and hit.re is FILL_KEY_RE:
            k = int(hit.group(2)) if hit.group(2) else None
            name = sp.norm(hit.group(1))
            open_key(docs[doc]["fills"] if doc else {}, (name, k), _key_label(name, k))
        elif hit:
            heading = sp.norm(hit.group(1))
            open_key(docs[doc]["sections"] if doc else {}, heading, f"section: {heading}")
        else:
            if ln.startswith("## ") and not depth:
                errors.append((doc, f"doc={doc or 'none'} key={label}: H2 line outside a fence: {ln.rstrip()}"))
            depth = sp.fence_step(ln, depth)
            buf.append(ln)
    close()
    if depth:
        errors.append((doc, f"doc={doc or 'none'} key={label}: a fence is still open at the end of {source}"))
    return docs, errors


def bodies_files(bodies_dir, abbrev):
    """The bodies files of a plan, sorted by name."""
    pattern = re.compile(rf"^{re.escape(abbrev)}-bodies-(?:plan|S\d{{2,}}-\d{{2,}}.*)\.md$")
    return sorted((p for p in Path(bodies_dir).iterdir() if p.is_file() and pattern.match(p.name)),
                  key=lambda p: p.name)


def _file_group(path, abbrev):
    return session_of(path.name[len(f"{abbrev}-bodies-"):])


def load_bodies(bodies_dir, abbrev):
    """Merge a plan's bodies files by doc id. Return (docs, errors as (group, message))."""
    docs, errors = {}, []
    for path in bodies_files(bodies_dir, abbrev):
        try:
            parsed, found = parse_bodies(sp.read_lf(path), path.name)
        except (OSError, UnicodeDecodeError) as exc:
            errors.append((_file_group(path, abbrev), f"doc=none key=none: cannot read bodies file {path.name}: {exc}"))
            continue
        errors.extend((session_of(doc) if doc else _file_group(path, abbrev), msg) for doc, msg in found)
        for doc, body in parsed.items():
            if doc in docs:
                both = f"{docs[doc]['source']} and {path.name}"
                errors.append((session_of(doc), f"doc={doc} key=doc: the doc id appears in both {both}"))
            else:
                docs[doc] = body
    return docs, errors


def key_errors(doc, body, info):
    """The lint errors of one parsed document against its rendered index entry."""
    counts = {}
    for name, _h2, _h3 in info["markers"]:
        counts[name] = counts.get(name, 0) + 1
    errors = []
    for name, k in body["fills"]:
        label = _key_label(name, k)
        if name not in counts:
            errors.append(f"doc={doc} key={label}: the marker occurs nowhere in this doc")
        elif k is not None and not 1 <= k <= counts[name]:
            errors.append(f"doc={doc} key={label}: the marker occurs {counts[name]} time(s) in this doc")
    errors.extend(f"doc={doc} key=section: {heading}: the heading is absent from this doc"
                  for heading in body["sections"] if heading not in info["headings"])
    return errors + overlap_errors(doc, body, info)


def overlap_errors(doc, body, info):
    """One error per body that a section body would replace. An empty body replaces nothing and loses nothing."""
    sections = {heading for heading, text in body["sections"].items() if text}
    covers = {}
    for name, h2, h3 in info["markers"]:
        covers.setdefault(name, []).append(h2 if h2 in sections else h3 if h3 in sections else None)
    lost = []
    for (name, k), text in body["fills"].items():
        spots = covers.get(name, [])
        spots = spots[k - 1:k] if k else spots
        if text and spots and all(spots):  # a bare fill with an occurrence outside the section still lands there
            lost.append((_key_label(name, k), spots[0]))
    lost.extend((f"section: {child}", parent) for child, parent in info["nested"]
                if child in sections and parent in sections)
    return [f"doc={doc} key={label}: the section body of {heading} replaces this key, so its body is lost"
            for label, heading in lost]


def missing_keys(body, info):
    """The number of marker occurrences in this document with no body."""
    fills = body["fills"] if body else {}
    sections = {h for h, text in body["sections"].items() if text} if body else set()
    missing, seen = 0, {}
    for name, h2, h3 in info["markers"]:
        seen[name] = seen.get(name, 0) + 1
        covered = fills.get((name, seen[name])) or fills.get((name, None)) or h2 in sections or h3 in sections
        missing += 0 if covered else 1
    return missing


def section_covers(body, info, name):
    """Whether a section body with text replaces every occurrence of marker `name`."""
    sections = {heading for heading, text in body["sections"].items() if text} if body else ()
    return all(h2 in sections or h3 in sections for marker, h2, h3 in info["markers"] if marker == name)


def fill_estimates(docs, figures, index):
    """Put the spec's `{O}` and `{W}` fills into `docs`, except where a section body replaces the marker.

    Return one (group, error) per marker that a body also fills.
    """
    errors = []
    for doc, (_figure, fills) in figures.items():
        if doc not in index:
            continue
        present = {m[0] for m in index[doc]["markers"]}
        for name, text in fills.items():
            body = docs.get(doc)
            if name not in present:
                continue
            if body and any(n == name and t for (n, _k), t in body["fills"].items()):
                message = (f"doc={doc} key=fill: {name}: the spec fills this marker from "
                           f"output_k and working_k, so a body for it is a second source")
                errors.append((session_of(doc), message))
            elif not section_covers(body, index[doc], name):
                docs.setdefault(doc, _new_doc("spec"))["fills"][(name, None)] = text
    return errors


def load_all_bodies(spec_path, bodies_dir, core, index):
    """Return (docs, load errors, figures): the bodies files with the spec's `{O}` and `{W}` fills merged in."""
    docs, load_errors = load_bodies(bodies_dir, core["abbrev"])
    figures = task_figures(sp.load_spec(spec_path)[0])
    return docs, [*load_errors, *fill_estimates(docs, figures, index)], figures


def lint_bodies(index, docs, load_errors=(), session=None):
    """Return (error lines, summary rows {group, keys_missing, errors}) in report order."""
    groups = {PLAN_GROUP: 0}
    for doc in index:
        groups.setdefault(session_of(doc), 0)
    errors = list(load_errors)
    for doc, body in docs.items():
        if doc in index:
            errors.extend((session_of(doc), msg) for msg in key_errors(doc, body, index[doc]))
        else:
            errors.append((session_of(doc), f"doc={doc} key=doc: the doc is not in the rendered tree"))
    for doc, info in index.items():
        groups[session_of(doc)] += missing_keys(docs.get(doc), info)
    for group, _msg in errors:
        groups.setdefault(group, 0)
    wanted = [g for g in groups if session in (None, g)]
    lines = [msg for group, msg in errors if group in wanted]
    rows = [{"group": g, "keys_missing": groups[g], "errors": sum(1 for e, _m in errors if e == g)} for g in wanted]
    return lines, rows


# ---------------------------------------------------------------- apply

def apply_doc(text, body, patterns):
    """Substitute one document's bodies. Return (text, markers left in place).

    The walk matches `missing_keys`: an occurrence counts from 1 across the whole
    document, a section span covers its markers, and an empty body is no body. One
    pass over the skeleton means marker text inside a body stays as written.
    """
    fills = body["fills"] if body else {}
    sections = {h: t for h, t in body["sections"].items() if t} if body else {}
    lines = text.split("\n")
    levels = heading_levels(lines, patterns)
    seen, left, out, skip = {}, 0, [], 0

    def count(name):
        seen[name] = seen.get(name, 0) + 1
        return seen[name]

    def fill(match):
        nonlocal left
        name = sp.norm(match.group(1))
        value = fills.get((name, count(name))) or fills.get((name, None))
        left += 0 if value else 1
        return value or match.group(0)

    for k, ln in enumerate(lines):
        if k < skip:
            for name in MARKER_RE.findall(ln):
                count(sp.norm(name))
            continue
        out.append(MARKER_RE.sub(fill, ln))
        section = sections.get(heading_text(ln)) if levels.get(k, 0) > 1 else None
        if section:
            end = section_end(lines, levels, k)
            kept = before_separator(lines, k, end)
            skip = kept if kept < end and lines[kept].strip() == SEPARATOR else end
            out.extend(["", section, ""])
    return "\n".join(out), left


def apply_bodies(files, docs, templates_dir):
    """Return (the tree with every body in place, marker occurrences left in place)."""
    sets = sp.template_heading_sets(templates_dir)
    out, left = dict(files), 0
    for rel, text in files.items():
        doc = doc_id(rel)
        if doc is not None:
            out[rel], remaining = apply_doc(text, docs.get(doc), sets[sp.file_kind(rel)][0])
            left += remaining
    return out, left


# ---------------------------------------------------------------- manifest

MANIFEST_ERRORS = (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError, AttributeError)


def manifest_path(spec):
    """`<ABBREV>-build-manifest.json` beside the spec file at path `spec`, with `-META` after the abbreviation on a Meta plan."""
    loaded, err = sp.load_spec(spec)
    if err:
        raise ValueError(err)
    return Path(spec).parent / f"{loaded['abbrev']}{'-META' if is_meta(loaded) else ''}-build-manifest.json"


def read_manifest(path):
    """{relative path: sha256} of the built files in a manifest file."""
    return dict(json.loads(Path(path).read_text(encoding="utf-8"))["files"])


def read_stale(path):
    """{relative path: sha256} of the files a manifest keeps after the spec dropped them."""
    return dict(json.loads(Path(path).read_text(encoding="utf-8")).get("stale", {}))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def store_manifest(path, hashes, stale):
    """Write the two manifest tables, each sorted by path."""
    data = {"files": dict(sorted(hashes.items())), "stale": dict(sorted(stale.items()))}
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))


def write_manifest(out, spec, rels=None, stale=None):
    """Hash the built files under `out` into the manifest beside `spec`. Return its path.

    `rels` names the files, and `stale` holds the dropped paths with their hashes. Both
    default to what the manifest already lists. A step that rewrites built files calls
    this with `out` and `spec` alone.
    """
    path = manifest_path(spec)
    names = read_manifest(path) if rels is None else rels
    kept = read_stale(path) if stale is None else stale
    store_manifest(path, {rel: file_hash(Path(out) / rel) for rel in names}, kept)
    return path


def record_landed(out, spec, landed, stale):
    """Record the files of a write that stopped, so the next build can tell them from hand edits.

    A file the write never reached keeps its earlier hash, because nothing here has
    checked its bytes. The file that stopped the write keeps its earlier hash too.
    """
    path = manifest_path(spec)
    try:
        earlier = read_manifest(path)
    except MANIFEST_ERRORS:
        earlier = {}
    hashes = {rel: digest for rel, digest in earlier.items() if rel not in stale}
    hashes.update({rel: file_hash(Path(out) / rel) for rel in landed})
    store_manifest(path, hashes, stale)


def changed_files(out, manifest, rels, stale=None):
    """The listed files that differ or are gone, and the unlisted `rels` a write would replace.

    An unlisted path that still matches its `stale` hash is the build's own earlier file.
    """
    out, stale = Path(out), stale or {}
    changed = [rel for rel, digest in manifest.items()
               if not (out / rel).is_file() or file_hash(out / rel) != digest]
    replaced = [rel for rel in rels if rel not in manifest and (out / rel).exists()
                and not ((out / rel).is_file() and file_hash(out / rel) == stale.get(rel))]
    return sorted({*changed, *replaced})


def guard_refusal(out, path, rels):
    """Return the refusal lines of a build into `out`, or an empty list when it may write."""
    out = Path(out)
    if not path.exists():
        if out.exists() and any(out.iterdir()):
            return [(f"REFUSED: {out} holds files and {path.name} does not exist. "
                     "Fix: pass an empty folder, or re-run with --force to overwrite.")]
        return []
    try:
        changed = changed_files(out, read_manifest(path), rels, read_stale(path))
    except MANIFEST_ERRORS as exc:
        return [(f"REFUSED: cannot read {path.name} ({type(exc).__name__}: {exc}). "
                 "Fix: restore the file, or re-run with --force to overwrite.")]
    if not changed:
        return []
    return [*(f"CHANGED: {rel}" for rel in changed),
            (f"REFUSED: {len(changed)} file(s) differ from {path.name}. "
             "Fix: keep the edits elsewhere, or re-run with --force to overwrite them.")]


def stale_files(path, rels, out):
    """{path: sha256} of the files on disk that an earlier manifest holds and this build does not write."""
    try:
        earlier = {**read_stale(path), **read_manifest(path)}
    except MANIFEST_ERRORS:
        return {}
    return {rel: digest for rel, digest in sorted(earlier.items())
            if rel not in rels and (Path(out) / rel).is_file()}


def write_built(files, out, landed):
    """Write the tree file by file. Each finished path joins `landed`, so a caller that catches an OSError can count them."""
    out = Path(out)
    for rel, text in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(text.encode("utf-8"))
        landed.append(rel)


# ---------------------------------------------------------------- CLI

def cmd_keys(args):
    built = render_core(args.spec, args.templates)
    if built is None:
        return 2
    _core, _files, index = built
    figures = task_figures(sp.load_spec(args.spec)[0])
    total = 0
    for doc, info in index.items():
        filled = set(figures.get(doc, (None, {}))[1])  # the spec fills these, so no body is needed
        markers = [m for m in info["markers"] if m[0] not in filled]
        total += len(markers)
        print(f"doc {doc} markers={len(markers)}")
        counts = {}
        for name, _h2, _h3 in markers:
            counts[name] = counts.get(name, 0) + 1
        for name, count in counts.items():
            print(f"  marker {name} count={count}")
        print(f"  headings: {' | '.join(info['headings'])}")
    print(f"fill_markers={total} docs={len(index)}")
    return 0


def cmd_lint(args):
    built = render_core(args.spec, args.templates)
    if built is None:
        return 2
    core, _files, index = built
    if args.session and args.session != PLAN_GROUP and args.session not in {session_of(d) for d in index}:
        print(f"REFUSED: session {args.session} is not in the spec. Fix: pass a session such as S01-01.")
        return 2
    if not Path(args.bodies_dir).is_dir():
        print(f"REFUSED: {args.bodies_dir} is not a folder. Fix: pass the folder that holds the bodies files.")
        return 2
    docs, load_errors, _figures = load_all_bodies(args.spec, args.bodies_dir, core, index)
    lines, rows = lint_bodies(index, docs, load_errors, args.session)
    for line in lines:
        print(f"LINT: {line}")
    for row in rows:
        if row["group"] == PLAN_GROUP:
            print(f"plan missing={row['keys_missing']} errors={row['errors']}")
        else:
            print(f"session={row['group']} keys_missing={row['keys_missing']} errors={row['errors']}")
    if lines:
        return 2
    return 1 if any(row["keys_missing"] for row in rows) else 0


def build_inputs_refusal(args):
    """The refusal line of a bad `build` argument, or None."""
    if args.date and not sp.DATE_RE.match(args.date):
        return f"REFUSED: --date {args.date} is not YYYY-MM-DD. Fix: pass a date such as 2026-01-31."
    if not Path(args.config).is_file():
        return f"REFUSED: {args.config} is not a file. Fix: pass the project's config file."
    if not Path(args.bodies_dir).is_dir():
        return f"REFUSED: {args.bodies_dir} is not a folder. Fix: pass the folder that holds the bodies files."
    if Path(args.out).exists() and not Path(args.out).is_dir():
        return f"REFUSED: {args.out} is not a folder. Fix: pass a folder for --out."
    return None


# ---------------------------------------------------------------- gate chain

GATES = ("estimates", "headings", "deviations", "scan", "index")
DETAIL_LIMIT = 20
INDEX_SCRIPT = Path(__file__).resolve().parent / "generate_plans_index.py"
LEVELS_RE = re.compile(r"(\d+) Green, (\d+) Notice, (\d+) Warn, (\d+) Critical \((\d+) handled")
WORKLIST_ITEM_RE = re.compile(r"^  - \S")
UNREADABLE_HEAD_RE = re.compile(r"^Totals not re-rolled \(\d+\)")


def _first_lines(text, limit=3):
    return [ln.strip() for ln in text.splitlines() if ln.strip()][:limit]


def _call_scan(argv):
    """Run `token_saver_scan.main(argv)` in process. Return (exit code, stdout, stderr)."""
    import contextlib
    import io

    import token_saver_scan

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = token_saver_scan.main(argv)
    return code, out.getvalue(), err.getvalue()


def session_tasks(files):
    """{SXX-YY: [relative path of each task file]} of the rendered tree, in tree order."""
    groups = {}
    for rel in files:
        if sp.file_kind(rel.replace("\\", "/").rsplit("/", 1)[-1]) == "task":
            groups.setdefault(session_of(doc_id(rel)), []).append(rel)
    return groups


def writeback_problems(stdout):
    """The `ERROR:` lines and the unreadable entries of a write-back report, which can exit 0 with either."""
    problems, listing = [], False
    for ln in stdout.splitlines():
        entry = listing and ln.startswith("  ")
        if entry or ln.startswith("ERROR:"):
            problems.append(ln.strip())
        listing = entry or bool(UNREADABLE_HEAD_RE.match(ln))
    return problems


def gate_estimates(out, config, files):
    """`token_saver.py --scan --write-estimates`, once per session, over that session's task files."""
    groups = session_tasks(files)
    failed, details = 0, []
    for session, rels in groups.items():
        argv = ["--scan", "--write-estimates", "--plan", str(out), "--config", str(config)]
        for rel in rels:
            argv += ["--task", str(Path(out) / rel)]
        code, stdout, stderr = _call_scan(argv)
        problems = [*_first_lines(stderr, 1), *writeback_problems(stdout)]
        if code or problems:
            failed += 1
            details.extend(f"session={session} exit={code}: {reason}"
                           for reason in problems or ["write-back reported errors"])
    status = "finding" if failed else "ok"
    figures = f"sessions={len(groups)} tasks={sum(len(r) for r in groups.values())} failed={failed}"
    return status, figures, details


def gate_headings(out, templates):
    results = sp.check_headings([Path(out)], templates)
    details = [f"{Path(r['path']).relative_to(Path(out)).as_posix()}: {stray}"
               for r in results for stray in r["stray"]]
    status = "finding" if details else "ok"
    return status, f"h2={sum(r['h2'] for r in results)} stray={len(details)}", details


def gate_deviations(out, templates):
    import scaffold_deviations as sd

    root = Path(out).resolve()
    try:
        found = sd.scan(root, sd.load_templates(templates)) + sd.class_c(root)
    except (OSError, UnicodeDecodeError, StopIteration, ValueError, KeyError, sd.PlanReadError) as exc:
        return "finding", "A=0 B=0 C=0", [f"cannot grade the tree: {type(exc).__name__}: {exc}"]
    counts = {c: sum(1 for k, _line in found if k == c) for c in "ABC"}
    return ("finding" if found else "ok"), f"A={counts['A']} B={counts['B']} C={counts['C']}", [ln for _k, ln in found]


def gate_scan(out, config):
    """The Token Saver scan. Exit 0 is ok, 1 a Warn file or worse, 2 or 3 a refusal. All but 0 are findings."""
    code, stdout, stderr = _call_scan(["--scan", "--plan", str(out), "--config", str(config)])
    levels = LEVELS_RE.search(stdout)
    names = ("green", "notice", "warn", "critical", "handled")
    figures = " ".join(f"{n}={v}" for n, v in zip(names, levels.groups())) + " " if levels else ""
    details = [ln.strip()[2:] for ln in stdout.splitlines() if WORKLIST_ITEM_RE.match(ln)]
    if code in (2, 3):
        details = [*_first_lines(stderr, 1), *details]
    return ("finding" if code else "ok"), f"{figures}exit={code}", details


def gate_index(config, skip, abbrev, out):
    """`generate_plans_index.py --write` as a subprocess: its main() takes no argv, so it cannot run in process.

    The row is matched by abbreviation and folder: its Path must be `out` relative to the plans folder.
    A Meta plan and its Exec plan share one abbreviation, so the abbreviation alone cannot tell them apart.
    A clean write with no such row is a finding, because the index walk never reached the plan.
    """
    if skip:
        return "skipped", "exit=none", []
    import os
    import subprocess

    from config_loader import load_config
    from parse_plans import parse_index_table

    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-B", str(INDEX_SCRIPT), "--config", str(config), "--write", "--json"],
                          capture_output=True, text=True, encoding="utf-8", env=env, check=False)
    figures = f"exit={proc.returncode}"
    if proc.returncode:
        return "finding", figures, _first_lines(proc.stderr, DETAIL_LIMIT + 1)
    index = Path(json.loads(proc.stdout)["index"])
    plans_dir = Path(load_config(config_path=Path(config))["_plans_dir"]).resolve()
    try:
        expected = Path(out).resolve().relative_to(plans_dir).as_posix() + "/"
    except ValueError:
        return "finding", figures, [f"{out} is outside {plans_dir}. Fix: build into a folder the index walk reads."]
    if any(row.abbrev == abbrev and row.path == expected
           for row in parse_index_table(index.read_text(encoding="utf-8")).rows):
        return "ok", figures, []
    return "finding", figures, [(f"{index} holds no row for {abbrev} at {expected}. "
                                 "Fix: build into a folder the index walk reads.")]


def run_chain(args, files, abbrev):
    """Run the five gates in order after the write. No gate stops the others. Return [(name, status, figures, details)]."""
    calls = {
        "estimates": lambda: gate_estimates(args.out, args.config, files),
        "headings": lambda: gate_headings(args.out, args.templates),
        "deviations": lambda: gate_deviations(args.out, args.templates),
        "scan": lambda: gate_scan(args.out, args.config),
        "index": lambda: gate_index(args.config, args.skip_index, abbrev, args.out),
    }
    report = []
    for name in GATES:
        try:
            result = calls[name]()
        except Exception as exc:  # noqa: BLE001 - a gate that raises is a finding, and the next gate still runs
            reason = " ".join(f"{type(exc).__name__}: {exc}".split())
            result = ("finding", "crashed=1", [f"the gate raised {reason[:300]}"])
        report.append((name, *result))
    return report


def print_gates(gates, count):
    """One line per gate, then at most DETAIL_LIMIT detail lines each."""
    for name, status, figures, details in gates:
        print(f"gate={name} status={status} files={count} {figures}")
        for line in details[:DETAIL_LIMIT]:
            print(f"  {line}")
        if len(details) > DETAIL_LIMIT:
            print(f"  +{len(details) - DETAIL_LIMIT} more")


def delta_lines(out, files, figures):
    """One `delta task=<id> spec=<n> measured=<n>` line per task file: the spec figure against the header on disk.

    The write-back prices the reads from the live files, so a gap is information and never a failure.
    """
    lines = []
    for rel in files:
        if sp.file_kind(rel.replace("\\", "/").rsplit("/", 1)[-1]) != "task":
            continue
        doc = doc_id(rel)
        figure = figures.get(doc, (None, {}))[0]
        try:
            found = HEADER_RE.search((Path(out) / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            found = None
        shown = "none" if figure is None else figure if abs(figure) > sys.float_info.max else f"{figure:g}"  # `:g` overflows past the float range
        lines.append(f"delta task={doc} spec={shown} measured={found.group(1) if found else 'none'}")
    return lines


def write_failure(args, exc, landed, total, stale, left):
    """Report a write that stopped. Record what landed, so the next build can tell it from hand edits. Return 3."""
    reason = " ".join(f"{type(exc).__name__}: {exc}".split())
    print(f"FAILED: the write stopped after {len(landed)} of {total} files ({reason}). "
          "Fix: free the --out folder, then re-run.")
    if landed:
        try:
            record_landed(args.out, args.spec, landed, stale)
        except MANIFEST_ERRORS as err:
            print(f"FAILED: the landed files are not in the manifest ({type(err).__name__}: {err}). "
                  "Fix: re-run with --force once the --out folder is free.")
    print(f"fill_remaining={left}\nexit=3")
    return 3


def cmd_build(args):
    refusal = build_inputs_refusal(args)
    if refusal:
        print(refusal)
        return 2
    built = render_core(args.spec, args.templates, args.date)
    if built is None:
        return 2
    core, skeleton, index = built
    docs, load_errors, figures = load_all_bodies(args.spec, args.bodies_dir, core, index)
    lines, _rows = lint_bodies(index, docs, load_errors)
    if lines:
        for line in lines:
            print(f"LINT: {line}")
        print(f"REFUSED: {len(lines)} bodies lint error(s). Fix: correct the bodies files, then re-run this command.")
        return 2
    files, left = apply_bodies(skeleton, docs, args.templates)
    if is_meta(sp.load_spec(args.spec)[0]):
        root = f"Meta-{core['abbrev']}"
        if Path(args.out).resolve().name == root:
            print(f"REFUSED: --out {args.out} already ends in {root}, and the build adds that folder. "
                  "Fix: pass its parent folder.")
            return 2
        args.out = str(Path(args.out) / root)
        refusal = build_inputs_refusal(args)
        if refusal:
            print(refusal)
            return 2
        skeleton, files = meta_tree(skeleton, core["abbrev"]), meta_tree(files, core["abbrev"])
    path = manifest_path(args.spec)
    guard = [] if args.force else guard_refusal(args.out, path, skeleton)
    if guard:
        print("\n".join(guard))
        return 2
    stale = stale_files(path, skeleton, args.out)
    leaked = {rel: sp.unmasked_braces(t) for rel, t in skeleton.items() if rel.endswith(".md")}
    leaked = {rel: names for rel, names in leaked.items() if names}
    landed = []
    try:
        write_built(files, args.out, landed)
        write_manifest(args.out, args.spec, files, stale)
    except OSError as exc:
        return write_failure(args, exc, landed, len(files), stale, left)
    print(f"built {len(files)} files to {args.out}; fill_remaining={left}; surviving_placeholders="
          f"{sum(len(v) for v in leaked.values())}")
    for rel, names in leaked.items():
        print(f"SURVIVING: {rel}: {', '.join(names)}")
    for rel in stale:
        print(f"STALE: {rel}")
    gates = run_chain(args, files, core["abbrev"])
    print_gates(gates, len(files))
    for line in delta_lines(args.out, files, figures):
        print(line)
    try:
        write_manifest(args.out, args.spec)  # the estimates gate rewrote task files after the first manifest
    except MANIFEST_ERRORS as exc:
        print(f"REFUSED: the manifest rewrite failed ({type(exc).__name__}: {exc}). Fix: free the --out folder, then re-run.")
        print(f"fill_remaining={left}\nexit=3")
        return 3
    code = 1 if left or leaked or any(status == "finding" for _n, status, _f, _d in gates) else 0
    print(f"fill_remaining={left}\nexit={code}")
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(description="List a plan's body keys, lint its bodies files, and build it.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keys", help="print every document's markers and headings")
    k.add_argument("--spec", required=True)
    k.add_argument("--templates", default=str(sp.DEFAULT_TEMPLATES))
    s = sub.add_parser("lint", help="check the bodies files against the rendered skeleton")
    s.add_argument("--spec", required=True)
    s.add_argument("--bodies-dir", required=True)
    s.add_argument("--session", help="limit the check to one session, such as S01-01")
    s.add_argument("--templates", default=str(sp.DEFAULT_TEMPLATES))
    b = sub.add_parser("build", help="write the tree with its bodies, and the sha256 manifest")
    b.add_argument("--spec", required=True)
    b.add_argument("--bodies-dir", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--config", required=True)
    b.add_argument("--date", help="YYYY-MM-DD for every date placeholder (default: the spec's created)")
    b.add_argument("--force", action="store_true", help="overwrite files that differ from the manifest")
    b.add_argument("--skip-index", action="store_true", help="do not run generate_plans_index.py --write")
    b.add_argument("--templates", default=str(sp.DEFAULT_TEMPLATES))
    args = ap.parse_args(argv)
    return {"keys": cmd_keys, "lint": cmd_lint, "build": cmd_build}[args.cmd](args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # marker names hold non-ASCII text
    sys.exit(main())
