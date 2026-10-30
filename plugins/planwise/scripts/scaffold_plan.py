#!/usr/bin/env python
"""Render a plan skeleton from the plan templates and one metadata-only JSON spec.

The templates stay the single source of every heading and every line of body
text. This script reads them at run time, substitutes metadata, derives the
tables a spec can compute, and turns every remaining prose placeholder into a
FILL marker (`<!-- FILL: {name} -->`) for the model to write. It never carries
template text of its own, and the spec never names a heading.

Commands (run with `python -B`):

    render --spec SPEC.json --out PLAN_DIR [--templates DIR] [--date YYYY-MM-DD]
        Lint the spec, then write the plan tree into PLAN_DIR:
          {ABBREV}-Master-Plan.md
          Sprint-{NN}-{Name}/{ABBREV}-S{NN}-Sprint-Plan.md
          Sprint-{NN}-{Name}/Session-{NN}-{Name}/{ABBREV}-S{NN}-{NN}-Orchestration.md
          Sprint-{NN}-{Name}/Session-{NN}-{Name}/{ABBREV}-S{NN}-{NN}-Recovery.md
          Sprint-{NN}-{Name}/Session-{NN}-{Name}/{ABBREV}-S{NN}-{NN}-{NN}-{Agent}-{Name}.md
          Sprint-{NN}-{Name}/Session-{NN}-{Name}/Outputs/.gitkeep
        --templates defaults to this plugin's own templates/ folder.
        --date sets every date placeholder; it defaults to the spec's `created`.
        Exit 0 rendered, 1 rendered but a placeholder survived outside a FILL
        marker, 2 refused (spec lint errors, unreadable spec, non-empty PLAN_DIR,
        or a render failure on a lint-clean spec, reported in one line).

    lint-spec --spec SPEC.json [--templates DIR]
        Validate the spec. Each error quotes the offending row or key.
        Exit 0 clean, 1 errors found, 2 unreadable spec.

    check-headings PATH... [--templates DIR]
        Heading conformance. PATH is a plan file or a folder (walked for *.md,
        skipping Outputs/). The file kind comes from the name. Every H2 outside
        the kind's template H2 set is `stray`, and so is every H2 after the
        template's last H2 (the catch-all section, where plan-specific sections
        go as H3s). An H2 inside an open fence is fence content when the
        fence closes later in the file. A fence that never closes is stuck, and
        a template H2 inside it resets the fence depth to 0 and counts as a
        heading. Prints one line per file and a `stray_h2=<n>` total.
        Exit 0 no stray H2, 1 stray H2 found, 2 a PATH does not exist.

Spec format (JSON, UTF-8). Required keys are marked *; every other key is
optional and takes the default shown. Any key not listed here is a lint error.

    plan:      plan_name*, abbrev* (2-6 of A-Z0-9, letter first), created*
               (YYYY-MM-DD), ordering* (the declared ordering string),
               sprints* (list), token_saver ("inherit"), resolves ("none"),
               prerequisite_for ("None - standalone project"),
               parallel_pairs ([] - each a [sprint number, sprint number] pair),
               dependencies ([] - rows {dependency, required_for, status}),
               decisions ([] - rows {id, decision, rationale}),
               optional_sections ([] - Master Plan OPTIONAL sections to keep)
    sprint:    number*, name* (PascalCase), purpose*, sessions* (list),
               optional_sections ([] - Sprint Plan OPTIONAL sections to keep)
    session:   number*, name*, objective*, mode* (DIRECT or DELEGATED),
               prerequisite*, tasks* (list),
               optional_sections ([] - Orchestration or Recovery OPTIONAL
               sections to keep; each name is kept in whichever of the two
               templates carries it)
    task:      number*, name*, title*, agent* (Opus, Sonnet or Haiku),
               estimate_k* (number), depends_on* (list of same-session task
               numbers, or literal strings such as "cross-session: <id>"),
               outputs* (list of paths), required_context* (list of typed rows,
               below), token_budget (absent: the field line is dropped),
               cross_sprint_refs (absent: dropped),
               optional_sections ([] - task-file OPTIONAL sections to keep)

    Required Context rows. The task-file template carries three row forms (a
    file row, a span row and a command-corpus row), so a row names its form in
    `kind`. Every kind also needs priority*, kib*, tokens_k* and purpose*.
      kind "path" (the default when `kind` is absent): path* - one file.
      kind "span": path* plus span* - the part of the file the task reads,
          written as the template's span form or a line range, for example
          "§2–§5 (§5 runs to EOF)" or "lines 1-80". The path is checked like a
          plain path; the span text is kept verbatim.
      kind "command": command* plus lines* and bytes* - the command whose
          OUTPUT the task reads, and that output's measured size from a dry run
          (a number or a short text such as "~9,400"). A command's output is not
          a file, so it carries no path and no path check.
    Why these names: `path` keeps the plain row's own key, so a span row is a
    path row plus one field. `span` holds the free text because a span is
    either a section range or a line range. `lines` and `bytes` are the two
    measured quantities the template's command-corpus row prints. Each typed
    row renders in the template's own row form: the purpose cell keeps the
    template row's class suffix, and the command cell keeps the template's
    size tail.

An `optional_sections` entry is the heading text without `## ` and without its
marker comment, for example "Out of Scope". Every OPTIONAL section, including
the catch-all last section, is omitted unless its document's list names it.

Lint rules: a missing required key; a key not listed above (the spec is
metadata only and declares no headings); a name that is not PascalCase; an
agent outside Opus, Sonnet and Haiku; a sprint, session or task `number` that
is not an integer (a bool is not an integer); a duplicate sprint number, a
duplicate session number within a sprint, or a duplicate task number within a
session (two rendered files would share a path); an `estimate_k`, `kib` or
`tokens_k` that is not a number; `outputs` that is not a non-empty list of
non-empty strings; a `depends_on` that is not a list of integers and strings,
or whose number is not an earlier task of the same session; a
`parallel_pairs` entry that is not a list of two different declared sprint
numbers; a `sprints`, `sessions`, `tasks`, `required_context`, `dependencies`,
`decisions` or `optional_sections` value that is not a list; an
optional_sections entry that is not an OPTIONAL heading of that document's
template; a Required Context row with an unknown kind or a missing field of its
kind (the row is quoted); and a path or span row whose path is prose, not a
path. The prose rule: the value holds two or more whitespace-separated words,
and either it has no path separator (/ or \\) and no extension, or
`token_saver_scan.unresolved_reason` classes it as not a path (prose or command
output). A one-word value is always a path, so `Makefile`, `Dockerfile`,
`src/orchard/` and `src/output_writer.py` pass. A command-corpus row belongs in
kind "command", never in a plain row's path.

Rendering rules: the body is the text between a template's first ```markdown
line and its last fence line, so reference text after the closing fence (the
recovery template's status-value tables) is never rendered. HTML comments on
plain lines are stripped, except a trailing single-line REQUIRED, OPTIONAL or
CONDITIONAL marker. Callouts, fenced code and the spawn-prompt skeleton fence
pass through unchanged, comments included (the skeleton keeps only its Abbrev,
XX and YY substitutions). A comment that opens on a plain line is stripped up
to its close, even across a line that looks like a callout or a fence.
A template line whose braces open past its end is joined with the next lines
until they balance, and a field handler then rewrites the whole joined span.
Fence state is a depth: a fence line with an info string opens a level, a bare
fence line closes one (or opens one at depth 0), and every H2 section starts
at depth 0, so an odd fence count cannot spread past its own section.
"""

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True  # a direct run must not grow scripts/__pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

from token_saver_scan import unresolved_reason

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATES = PLUGIN_ROOT / "templates"
TEMPLATE_FILES = {
    "master": "master-plan.md",
    "sprint": "sprint-plan.md",
    "orchestration": "orchestration.md",
    "recovery": "recovery.md",
    "task": "task-file.md",
}
AGENTS = ("Opus", "Sonnet", "Haiku")
MODES = ("DIRECT", "DELEGATED")
KEEP_COMMENT = re.compile(r"<!--\s*(REQUIRED|OPTIONAL|CONDITIONAL)\b")
FILL = "<!-- FILL: {%s} -->"
FENCE_RE = re.compile(r"^```(.*)$")
TASK_FILE_RE = re.compile(r"-S\d{2}-\d{2}-\d{2}-[A-Za-z]+-[^/\\]+\.md$")
NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
ABBREV_RE = re.compile(r"^[A-Z][A-Z0-9]{1,5}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCHEMA = {
    "plan": ({"plan_name", "abbrev", "created", "ordering", "sprints"},
             {"token_saver", "resolves", "prerequisite_for", "parallel_pairs",
              "dependencies", "decisions", "optional_sections"}),
    "sprint": ({"number", "name", "purpose", "sessions"}, {"optional_sections"}),
    "session": ({"number", "name", "objective", "mode", "prerequisite", "tasks"},
                {"optional_sections"}),
    "task": ({"number", "name", "title", "agent", "estimate_k", "depends_on",
              "outputs", "required_context"},
             {"token_budget", "cross_sprint_refs", "optional_sections"}),
    "rc:path": ({"priority", "path", "kib", "tokens_k", "purpose"}, {"kind"}),
    "rc:span": ({"kind", "priority", "path", "span", "kib", "tokens_k", "purpose"}, set()),
    "rc:command": ({"kind", "priority", "command", "lines", "bytes", "kib", "tokens_k", "purpose"}, set()),
    "dependencies": ({"dependency", "required_for", "status"}, set()),
    "decisions": ({"id", "decision", "rationale"}, set()),
}
DEFAULTS = {
    "token_saver": "inherit",
    "resolves": "none",
    "prerequisite_for": "None - standalone project",
    "parallel_pairs": [],
    "dependencies": [],
    "decisions": [],
}


# ---------------------------------------------------------------- text helpers

def brace_spans(text):
    """Outermost balanced brace groups as (start, end, inner); nested groups included."""
    spans, stack = [], []
    for i, ch in enumerate(text):
        if ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            a = stack.pop()
            if not stack:
                spans.append((a, i + 1, text[a + 1:i]))
    return spans


def brace_sub(text, fn):
    out, pos = [], 0
    for a, b, inner in brace_spans(text):
        out.append(text[pos:a])
        out.append(fn(inner, text[a:b]))
        pos = b
    out.append(text[pos:])
    return "".join(out)


def norm(name):
    return " ".join(name.split())


def norm_heading(line):
    """A heading line without its trailing marker comment and trailing whitespace."""
    return re.sub(r"\s*<!--.*?-->\s*$", "", line.rstrip("\r")).rstrip()


def fence_step(line, depth):
    """Fence depth after `line`: an info-string fence opens a level, a bare one closes."""
    m = FENCE_RE.match(line)
    if not m:
        return depth
    if m.group(1).strip():
        return depth + 1
    return depth - 1 if depth else 1


def read_lf(path):
    return Path(path).read_bytes().decode("utf-8").replace("\r\n", "\n")


def extract_body(path):
    """Template text between the first ```markdown line and the last fence line."""
    lines = read_lf(path).split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith("```markdown"))
    end = max(i for i, ln in enumerate(lines) if ln.startswith("```"))
    return "\n".join(lines[start + 1:end])


def strip_comments(text):
    s = text
    for m in reversed(list(re.finditer(r"<!--.*?-->", s, re.DOTALL))):
        c, a, b = m.group(0), m.start(), m.end()
        ls = s.rfind("\n", 0, a) + 1
        le = s.find("\n", b)
        le = len(s) if le < 0 else le
        before, after = s[ls:a], s[b:le]
        if "\n" not in c and KEEP_COMMENT.match(c) and before.strip():
            continue
        if not before.strip() and not after.strip():
            s = s[:ls] + s[le + 1:]
        else:
            s = s[:a].rstrip(" \t") + s[b:]
    return s


def comment_open_after(line, inside):
    """Whether an HTML comment is still open at the end of `line`, given its state at the start."""
    pos = 0
    while True:
        k = line.find("-->" if inside else "<!--", pos)
        if k < 0:
            return inside
        inside, pos = not inside, k + (3 if inside else 4)


def strip_plain_comments(text):
    """Strip comments on plain lines only; callouts, fences and the skeleton fence pass through.

    Line classes follow `process()`, so a line this function protects is a line
    `process()` passes through. A comment opened on a plain line is stripped up
    to its close, even across a line that would otherwise be protected.
    """
    out, run, depth, skel, in_comment = [], [], 0, False, False

    def flush():
        if run:
            # The added newline lets a comment-only last line drop with its own line ending.
            s = strip_comments("\n".join(run) + "\n")
            if s:
                out.extend(s[:-1].split("\n") if s.endswith("\n") else s.split("\n"))
            run.clear()

    for ln in text.split("\n"):
        if not in_comment and (skel or (depth == 0 and ln.startswith("```markdown")) or depth
                               or ln.startswith("```") or ln.lstrip().startswith(">")):
            flush()
            out.append(ln)
            if skel:
                skel = ln.strip() != "```"
            elif depth == 0 and ln.startswith("```markdown"):
                skel = True
            else:
                depth = fence_step(ln, depth)
            continue
        run.append(ln)
        in_comment = comment_open_after(ln, in_comment)
    flush()
    return "\n".join(out)


def split_sections(body):
    """Split at `## ` lines outside the spawn-prompt skeleton fence."""
    pre, secs, cur, skel = [], [], None, False
    for ln in body.split("\n"):
        if skel:
            if ln.strip() == "```":
                skel = False
        elif ln.startswith("```markdown"):
            skel = True
        elif ln.startswith("## "):
            cur = [ln]
            secs.append(cur)
            continue
        (cur if cur is not None else pre).append(ln)
    return pre, secs


def heading_text(line):
    """`## Out of Scope <!-- OPTIONAL -->` -> `Out of Scope`."""
    return norm(norm_heading(line)[3:])


def optional_headings(templates_dir):
    out = {}
    for kind, fname in TEMPLATE_FILES.items():
        _pre, secs = split_sections(extract_body(Path(templates_dir) / fname))
        out[kind] = {heading_text(s[0]) for s in secs if "<!-- OPTIONAL" in s[0]}
    return out


# ---------------------------------------------------------------- recorder

class Rec:
    """Per template, per distinct placeholder name, the set of dispositions seen."""

    def __init__(self):
        self.data = {}

    def add(self, tmpl, name, kind):
        self.data.setdefault(tmpl, {}).setdefault(norm(name), set()).add(kind)

    def names(self, tmpl, text, kind):
        for _a, _b, inner in brace_spans(text):
            self.add(tmpl, inner, kind)

    def classes(self, tmpl):
        out = {}
        for name, kinds in self.data.get(tmpl, {}).items():
            for k in ("metadata", "derived", "fill", "inert"):
                if k in kinds:
                    out[name] = k
                    break
        return out


def M(value):
    return ("metadata", value)


def D(value):
    return ("derived", value)


# ---------------------------------------------------------------- substitution

def lookup(vals, name):
    if name in vals:
        return vals[name]
    for k, v in vals.items():
        if k.endswith("*") and name.startswith(k[:-1]):
            return v
    return None


def sub_line(line, env, extra=None):
    vals = dict(env.vals)
    if extra:
        vals.update(extra)

    def repl(inner, _whole):
        name = norm(inner)
        hit = lookup(vals, name)
        if hit:
            env.rec.add(env.tmpl, name, hit[0])
            return str(hit[1])
        env.rec.add(env.tmpl, name, "fill")
        return FILL % name

    return brace_sub(line, repl)


def skel_line(line, env):
    keep = {k: env.vals[k] for k in ("Abbrev", "XX", "YY") if k in env.vals}

    def repl(inner, whole):
        name = norm(inner)
        if name in keep:
            env.rec.add(env.tmpl, name, keep[name][0])
            return str(keep[name][1])
        env.rec.add(env.tmpl, name, "inert")
        return whole

    return brace_sub(line, repl)


def session_total(session):
    return sum(t["estimate_k"] for t in session["tasks"])


def sprint_total(sprint):
    return sum(session_total(s) for s in sprint["sessions"])


def output_phrase(outs):
    q = [f"`{o}`" for o in outs]
    return q[0] if len(q) == 1 else ", ".join(q[:-1]) + ", and " + q[-1]


def is_int(value):
    """A JSON integer. A bool is not one, although Python counts it as an int."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def int_deps(task):
    return [d for d in task["depends_on"] if is_int(d)]


def layers(tasks):
    lv = {}
    for t in tasks:
        lv[t["number"]] = 1 + max([lv[d] for d in int_deps(t)] or [0])
    out = {}
    for n, k in sorted(lv.items()):
        out.setdefault(k, []).append(n)
    return out


def dep_text(task, sep=", "):
    parts = [f"{d:02d}" if isinstance(d, int) else str(d) for d in task["depends_on"]]
    return sep.join(parts) or "-"


def write_paths(sprint):
    paths = []
    for s in sprint["sessions"]:
        for t in s["tasks"]:
            for o in t["outputs"]:
                if not o.startswith("Outputs/") and o not in paths:
                    paths.append(o)
    return paths


# ---------------------------------------------------------------- engine

def process(lines, env, handlers):
    out, i, depth, skel = [], 0, 0, False
    while i < len(lines):
        line = lines[i]
        if skel:
            out.append(skel_line(line, env))
            skel = line.strip() != "```"
            i += 1
            continue
        if depth == 0 and line.startswith("```markdown"):
            skel = True
            out.append(line)
            i += 1
            continue
        if depth or line.startswith("```") or line.lstrip().startswith(">"):
            env.rec.names(env.tmpl, line, "inert")
            out.append(line)
            depth = fence_step(line, depth)
            i += 1
            continue
        start = i
        if line.count("{") > line.count("}"):
            for j in range(1, 4):
                if i + j < len(lines):
                    cand = "\n".join(lines[i:i + j + 1])
                    if cand.count("{") == cand.count("}"):
                        line, i = cand, i + j
                        break
        # A handler sees the joined span as one line at `start`; its consumed count then
        # advances from the span's last fragment, because view[start + k] is lines[i + k].
        view = lines if start == i else lines[:start] + [line] + lines[i + 1:]
        for rx, fn in handlers:
            if rx.match(line):
                res = fn(view, start, env)
                if res is not None:
                    new, consumed = res
                    out.extend(new)
                    i += consumed
                    break
        else:
            out.extend(sub_line(line, env).split("\n"))
            i += 1
    return out


def consume(env, lines, i, n, kind):
    env.rec.names(env.tmpl, "\n".join(lines[i:i + n]), kind)


def table_run(lines, i):
    """Number of consecutive table rows starting at line i (the template's example rows)."""
    j = i
    while j < len(lines) and lines[j].startswith("|"):
        j += 1
    return j - i


def H(pattern, fn):
    return (re.compile(pattern), fn)


FIELD_RE = re.compile(r"^(\*\*[^*]+:\*\*).*$", re.DOTALL)


def field_sub(line, value):
    """Replace everything after a `**Label:**` with `value`, across a joined multi-line span too."""
    return FIELD_RE.sub(lambda m: f"{m.group(1)} {value}", line)


def h_field(key, drop_if_absent=False):
    """Replace the value after a `**Label:**` field with a spec value."""
    def fn(lines, i, env):
        value = env.item.get(key, DEFAULTS.get(key))
        if value is None:
            if drop_if_absent:
                env.rec.names(env.tmpl, lines[i], "inert")
                return ([], 1)
            return None
        env.rec.names(env.tmpl, lines[i], "metadata")
        return ([field_sub(lines[i], value)], 1)
    return fn


def h_derived(name, total_fn):
    def fn(lines, i, env):
        return ([sub_line(lines[i], env, {name: D(total_fn(env))})], 1)
    return fn


# ---- master handlers

def m_sprint_rows(lines, i, env):
    n = table_run(lines, i)
    consume(env, lines, i, n, "metadata")
    rows = []
    for s in env.spec["sprints"]:
        row = re.sub(r"^\| \d+ \|", f"| {s['number']:02d} |", lines[i], count=1)
        rows.append(sub_line(row, env, {"SprintName": M(s["name"]), "What this sprint delivers": M(s["purpose"]),
                                        "count": D(len(s["sessions"]))}))
    return (rows, n)


def m_ordering(lines, i, env):
    consume(env, lines, i, 1, "metadata")
    return ([re.sub(r"`.*`", lambda _m: f"`{env.spec['ordering']}`", lines[i])], 1)


def m_writesets(lines, i, env):
    n = table_run(lines, i)
    consume(env, lines, i, n, "derived")
    rows = []
    for s in env.spec["sprints"]:
        cells = ", ".join(f"`{p}`" for p in write_paths(s)) or "none"
        rows.append(f"| Sprint-{s['number']:02d} | {cells} |")
    return (rows, n)


def m_intersection(lines, i, env):
    n = table_run(lines, i)
    consume(env, lines, i, n, "derived")
    pairs = env.spec.get("parallel_pairs") or []
    if not pairs:
        return (["| none declared | n/a - no parallel pair declared | serial order, no parallelism claimed |"], n)
    by_num = {s["number"]: s for s in env.spec["sprints"]}
    rows = []
    for a, b in pairs:
        shared = sorted(set(write_paths(by_num[a])) & set(write_paths(by_num[b])))
        inter = ", ".join(f"`{p}`" for p in shared) or "∅"
        verdict = "✅ disjoint — parallel stands" if not shared else "❌ NOT disjoint — serialized"
        rows.append(f"| Sprint-{a:02d} ∥ Sprint-{b:02d} | {inter} | {verdict} |")
    return (rows, n)


def m_rows(key, fields):
    def fn(lines, i, env):
        items = env.spec.get(key) or []
        if not items:
            return None
        n = table_run(lines, i)
        consume(env, lines, i, n, "metadata")
        return (["| " + " | ".join(str(r[f]) for f in fields) + " |" for r in items], n)
    return fn


def m_tracking(lines, i, env):
    n = table_run(lines, i)
    consume(env, lines, i, n, "metadata")
    rows = []
    for s in env.spec["sprints"]:
        for se in s["sessions"]:
            row = re.sub(r"Sprint-\d+", f"Sprint-{s['number']:02d}", lines[i], count=1)
            row = re.sub(r"Session-\d+-", f"Session-{se['number']:02d}-", row, count=1)
            rows.append(sub_line(row, env, {"Name": M(se["name"])}))
    return (rows, n)


def m_sprint_criteria(lines, i, env):
    j = i
    while j < len(lines) and lines[j].strip():
        j += 1
    block = lines[i:j]
    out = []
    for s in env.spec["sprints"]:
        for k, ln in enumerate(block):
            if k == 0:
                env.rec.names(env.tmpl, ln, "metadata")
                out.append(re.sub(r"Sprint-\d+", f"Sprint-{s['number']:02d}", ln, count=1))
            else:
                out.append(sub_line(ln, env))
    return (out, j - i)


MASTER = [
    H(r"\*\*Token Saver:\*\*", h_field("token_saver")),
    H(r"\*\*Resolves:\*\*", h_field("resolves")),
    H(r"\| \d+ \| \{SprintName\}", m_sprint_rows),
    H(r"\*\*Declared ordering:\*\*", m_ordering),
    H(r"\| Sprint-\d+ \| `\{path/or/directory\}`", m_writesets),
    H(r"\| Sprint-\d+ ∥ Sprint-\d+ \|", m_intersection),
    H(r"\| \{Document or prior plan\}", m_rows("dependencies", ("dependency", "required_for", "status"))),
    H(r"\| D1 \| \{what was decided", m_rows("decisions", ("id", "decision", "rationale"))),
    H(r"\| Sprint-\d+ \| Session-\d+-\{Name\}", m_tracking),
    H(r"### Sprint-\d+ Complete When:", m_sprint_criteria),
]


# ---- sprint-plan handlers

def s_session_rows(lines, i, env):
    n = table_run(lines, i)
    consume(env, lines, i, n, "metadata")
    rows = []
    for k, se in enumerate(env.sprint["sessions"], 1):
        sid = session_id(env.spec, env.sprint, se)
        rows.append(f"| {k} | {sid} | {se['name']} | {se['objective']} | ~{session_total(se)}K |")
    return (rows, n)


def s_writeset_rows(lines, i, env):
    rows = []
    for se in env.sprint["sessions"]:
        for t in se["tasks"]:
            tid = task_id(env.spec, env.sprint, se, t)
            rows.extend(f"| `{o}` | {tid} |" for o in t["outputs"] if not o.startswith("Outputs/"))
    if not rows:
        return None
    n = table_run(lines, i)
    consume(env, lines, i, n, "derived")
    return (rows, n)


def s_session_block(lines, i, env):
    j = i
    while j < len(lines) and lines[j].strip() != "---":
        j += 1
    block = lines[i:j]
    out = []
    for k, se in enumerate(env.sprint["sessions"]):
        env2 = copy.copy(env)
        env2.session = se
        env2.vals = dict(env.vals)
        env2.vals.update({"SessionName": M(se["name"]), "What this session accomplishes": M(se["objective"])})
        yy = f"{se['number']:02d}"
        text = [ln.replace("Session 01", "Session " + yy).replace("-01)", f"-{yy})") for ln in block]
        out.extend(process(text, env2, SPRINT_INNER))
        if k < len(env.sprint["sessions"]) - 1:
            out.extend(["", "---", ""])
    return (out, j - i)


def task_rows(lines, i, env):
    """The session's task table (sprint plan and orchestration): number, title, agent, estimate, dependencies."""
    n = table_run(lines, i)
    consume(env, lines, i, n, "metadata")
    rows = [f"| {t['number']} | {t['title']} | {t['agent']} | ~{t['estimate_k']}K | {dep_text(t)} |"
            for t in env.session["tasks"]]
    return (rows, n)


SPRINT_INNER = [H(r"\| 1 \| \{Task description\} \|", task_rows)]
SPRINT = [
    H(r"\*\*Estimated Tokens:\*\* ~\{XX\}K", h_derived("XX", lambda env: sprint_total(env.sprint))),
    H(r"\| 1 \| \{ABBREV\}-S\{XX\}-01 \|", s_session_rows),
    H(r"\| `\{path/or/directory\}` \| \{ABBREV\}", s_writeset_rows),
    H(r"### Session 01: \{SessionName\}", s_session_block),
]


# ---- orchestration handlers

def o_layers(lines, i, env):
    env.rec.names(env.tmpl, lines[i], "derived")
    lv = layers(env.session["tasks"])
    txt = " · ".join(f"L{k} = {{" + ", ".join(str(n) for n in v) + "}" for k, v in lv.items())
    return ([field_sub(lines[i], txt)], 1)


def o_intersection(lines, i, env):
    n = table_run(lines, i)
    consume(env, lines, i, n, "derived")
    tasks = {t["number"]: t for t in env.session["tasks"]}
    rows = []
    for k, members in layers(env.session["tasks"]).items():
        targets = [set(tasks[m]["outputs"]) for m in members]
        shared = set()
        for a in range(len(targets)):
            for b in range(a + 1, len(targets)):
                shared |= targets[a] & targets[b]
        wt = " / ".join(", ".join(f"`{o}`" for o in tasks[m]["outputs"]) for m in members)
        verdict = ("✅ single member" if len(members) == 1 else
                   "✅ disjoint — parallel stands" if not shared else "❌ NOT disjoint — serialized")
        mem = ", ".join(str(m) for m in members)
        inter = ", ".join(f"`{s}`" for s in sorted(shared)) or "∅"
        rows.append(f"| L{k} | {{{mem}}} | {wt} | {inter} | {verdict} |")
    return (rows, n)


def o_task_files(lines, i, env):
    n = table_run(lines, i)
    consume(env, lines, i, n, "metadata")
    rows = []
    for t in env.session["tasks"]:
        fn = task_filename(env.spec, env.sprint, env.session, t)
        rows.append(f"| {t['number']} | [{fn}]({fn}) | {t['agent']} |")
    return (rows, n)


ORCH = [
    H(r"\| 1 \| \{Task 1\} \| [A-Z][a-z]+ \|", task_rows),
    H(r"\*\*Total Estimated:\*\* ~\{XX\}K", h_derived("XX", lambda env: session_total(env.session))),
    H(r"\*\*Declared layers:\*\*", o_layers),
    H(r"\| L1 \| \{1, 2\}", o_intersection),
    H(r"\| 1 \| \[\{Abbrev\}-S", o_task_files),
]


# ---- recovery handlers

def r_step_rows(lines, i, env):
    n = table_run(lines, i)
    consume(env, lines, i, n, "metadata")
    rows = []
    for t in env.session["tasks"]:
        row = re.sub(r"^\| \d+ \|", f"| {t['number']} |", lines[i], count=1)
        rows.append(sub_line(row, env, {"Task 1": M(t["name"]), "Agent": M(t["agent"])}))
    return (rows, n)


def passthrough(lines, i, env):
    env.rec.names(env.tmpl, lines[i], "inert")
    return ([lines[i]], 1)


RECOVERY = [
    H(r"\| 1 \| \{Task 1\} \| \{Agent\} \|", r_step_rows),
    H(r"\| Source Task \|", passthrough),
]


# ---- task-file handlers

def t_depends(lines, i, env):
    consume(env, lines, i, 1, "metadata")
    return ([field_sub(lines[i], dep_text(env.task))], 1)


def t_output(lines, i, env):
    consume(env, lines, i, 1, "derived")
    return ([field_sub(lines[i], output_phrase(env.task["outputs"]))], 1)


ROW_CLASS = {"span": "span row", "command": "command-corpus row"}


def row_forms(example_rows):
    """Per typed kind, the template example row's purpose suffix and (for commands) its size tail.

    The template marks each typed example row by its class name in the purpose cell
    ("… — span row, …", "… — command-corpus row, …"); the text after the purpose
    placeholder is kept verbatim, so a rendered row reads in the template's own form.
    """
    forms = {}
    for kind, label in ROW_CLASS.items():
        row = next((r for r in example_rows if label in r), None)
        if row is None:
            forms[kind] = ("", None)
            continue
        suffix = re.search(r"\{why needed\}([^|]*?)\s*\|\s*$", row)
        tail = re.search(r"(\s+—\s+)(\{N\}[^|]*?)\s*\|", row)
        forms[kind] = (suffix.group(1) if suffix else "", tail.groups() if tail else None)
    return forms


def resolution_forms(body):
    """Per typed kind, the template's resolution-record form, split around its description.

    The task template's Required Context comment gives one record form per typed
    row class, each under a bullet naming the class (`span row`, `command-corpus
    row`) and each dated `{YYYY-MM-DD}:`. Returns {kind: (lead, tail)} where the
    description between them is replaced by the row's own span or command.
    """
    forms, bullet = {}, ""
    for ln in body.split("\n"):
        if ln.lstrip().startswith("- "):
            bullet = ln.lower()
        m = re.search(r"([A-Z][\w-]*(?: [a-z]+)*) \{YYYY-MM-DD\}:\s*(.*)$", ln)
        if not m:
            continue
        parts = re.match(r"^(.*?)(\s+\S+\s+\{N\}.*)$", m.group(2))
        kind = next((k for k, label in ROW_CLASS.items() if label in bullet), None)
        if kind and parts and kind not in forms:
            forms[kind] = (m.group(1) + " {YYYY-MM-DD}: ", parts.group(2))
    return forms


def row_cell(row):
    if rc_kind(row) == "command":
        return f"`{row['command']}`"
    if rc_kind(row) == "span":
        return f"`{row['path']}` {row['span']}"
    return f"`{row['path']}`"


def resolution_gaps(text, task):
    """Typed rows of `task` with no resolution record line in the rendered task text."""
    records = [ln for ln in text.split("\n") if not ln.startswith("|")]
    return [r for r in task["required_context"]
            if rc_kind(r) in ROW_CLASS and not any(row_cell(r) in ln for ln in records)]


def t_context_rows(lines, i, env):
    n = table_run(lines, i)
    consume(env, lines, i, n, "metadata")
    forms = row_forms(lines[i:i + n])
    rows, records = [], []
    for r in env.task["required_context"]:
        kind = rc_kind(r)
        suffix, tail = forms.get(kind, ("", None))
        record = env.res_forms.get(kind)
        if kind in ROW_CLASS and record is None:
            suffix = ""  # the suffix points to a resolution record the template gives no form for
        elif record:
            vals = {"YYYY-MM-DD": M(env.vals["today"][1])}
            if kind == "command":
                vals.update({"N": M(r["lines"]), "B": M(r["bytes"])})
            records.append(sub_line(record[0], env, vals) + row_cell(r) + sub_line(record[1], env, vals))
        cell = row_cell(r)
        if kind == "command" and tail:
            cell += tail[0] + sub_line(tail[1], env, {"N": M(r["lines"]), "B": M(r["bytes"])})
        rows.append(f"| {r['priority']} | {cell} | {r['kib']:.1f} | ~{r['tokens_k']:.1f}K | {r['purpose']}{suffix} |")
    if records:
        # Plain lines, not an HTML comment: a FILL marker nested in a comment would close it early.
        rows.append("")
        rows.extend(records)
    return (rows, n)


def t_subtotal(lines, i, env):
    reads = round(sum(r["tokens_k"] for r in env.task["required_context"]), 1)
    return ([sub_line(lines[i], env, {"R": D(reads), "T": D(env.task["estimate_k"])})], 1)


TASK = [
    H(r"\*\*Token Budget:\*\*", h_field("token_budget", drop_if_absent=True)),
    H(r"\*\*Cross-Sprint Refs:\*\*", h_field("cross_sprint_refs", drop_if_absent=True)),
    H(r"\*\*Depends On:\*\*", t_depends),
    H(r"\*\*Output:\*\*", t_output),
    H(r"\| 1 \| \{file path\}", t_context_rows),
    H(r"\*\*Context subtotal:\*\*", t_subtotal),
]


# ---------------------------------------------------------------- documents

def sprint_dir(sprint):
    return f"Sprint-{sprint['number']:02d}-{sprint['name']}"


def session_dir(sprint, session):
    return f"{sprint_dir(sprint)}/Session-{session['number']:02d}-{session['name']}"


def session_id(spec, sprint, session):
    return f"{spec['abbrev']}-S{sprint['number']:02d}-{session['number']:02d}"


def task_id(spec, sprint, session, task):
    return f"{session_id(spec, sprint, session)}-{task['number']:02d}"


def task_filename(spec, sprint, session, task):
    return f"{task_id(spec, sprint, session, task)}-{task['agent']}-{task['name']}.md"


def sprint_plan_path(spec, sprint):
    return f"{sprint_dir(sprint)}/{spec['abbrev']}-S{sprint['number']:02d}-Sprint-Plan.md"


def plan_paths(spec):
    """Every path the render writes, relative to the plan folder, in render order."""
    a = spec["abbrev"]
    paths = [f"{a}-Master-Plan.md"]
    for sp in spec["sprints"]:
        paths.append(sprint_plan_path(spec, sp))
        for se in sp["sessions"]:
            sd, sid = session_dir(sp, se), session_id(spec, sp, se)
            paths.append(f"{sd}/{sid}-Orchestration.md")
            paths.append(f"{sd}/{sid}-Recovery.md")
            paths.extend(f"{sd}/{task_filename(spec, sp, se, t)}" for t in se["tasks"])
            paths.append(f"{sd}/Outputs/.gitkeep")
    return paths


def render_doc(body, env, handlers, include_optional=()):
    pre, secs = split_sections(body)
    out = process(strip_plain_comments("\n".join(pre)).split("\n"), env, handlers)
    for sec in secs:
        raw = "\n".join(sec)
        if "<!-- OPTIONAL" in sec[0] and heading_text(sec[0]) not in include_optional:
            env.rec.names(env.tmpl, raw, "inert")
            continue
        out.extend(process(strip_plain_comments(raw).split("\n"), env, handlers))
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return text.rstrip("\n") + "\n"


def render_all(spec, templates_dir=DEFAULT_TEMPLATES, date=None):
    """Return ({relative path: text}, Rec). The spec must already pass lint_spec."""
    rec, files = Rec(), {}
    bodies = {k: extract_body(Path(templates_dir) / f) for k, f in TEMPLATE_FILES.items()}
    day = date or spec["created"]
    base = {
        "PlanName": M(spec["plan_name"]), "ABBREV": M(spec["abbrev"]), "Abbrev": M(spec["abbrev"]),
        "today's date": M(day), "today": M(day), "timestamp": M(day),
        "next plan*": M(spec.get("prerequisite_for", DEFAULTS["prerequisite_for"])),
    }

    def env_for(tmpl, item, **kw):
        e = SimpleNamespace(tmpl=tmpl, rec=rec, spec=spec, item=item, vals=dict(base),
                            sprint=None, session=None, task=None)
        for k, v in kw.items():
            setattr(e, k, v)
        return e

    def put(rel, text):
        # lint_spec rejects duplicate numbers; this guard keeps a missed case from dropping a file silently.
        if rel in files:
            raise AssertionError(f"render would overwrite {rel}, a path it already produced")
        files[rel] = text

    a = spec["abbrev"]
    res_forms = resolution_forms(bodies["task"])
    menv = env_for("master", spec)
    menv.vals["sum of all sessions"] = D(sum(len(s["sessions"]) for s in spec["sprints"]))
    put(f"{a}-Master-Plan.md", render_doc(bodies["master"], menv, MASTER, spec.get("optional_sections", ())))
    for sp in spec["sprints"]:
        xx = f"{sp['number']:02d}"
        senv = env_for("sprint", sp, sprint=sp)
        senv.vals.update({"XX": M(xx), "Sprint Name": M(sp["name"]), "SprintName": M(sp["name"])})
        put(sprint_plan_path(spec, sp), render_doc(bodies["sprint"], senv, SPRINT, sp.get("optional_sections", ())))
        for se in sp["sessions"]:
            sd, sid = session_dir(sp, se), session_id(spec, sp, se)
            common = {"XX": M(xx), "YY": M(f"{se['number']:02d}"), "SprintName": M(sp["name"]),
                      "Session Name": M(se["name"]), "SessionName": M(se["name"])}
            opt = se.get("optional_sections", ())
            oenv = env_for("orchestration", se, sprint=sp, session=se)
            oenv.vals.update(common)
            oenv.vals.update({"DIRECT | DELEGATED": M(se["mode"]), "previous session*": M(se["prerequisite"]),
                              "2-3 sentences describing what this session*": M(se["objective"])})
            put(f"{sd}/{sid}-Orchestration.md", render_doc(bodies["orchestration"], oenv, ORCH, opt))
            renv = env_for("recovery", se, sprint=sp, session=se)
            renv.vals.update(common)
            put(f"{sd}/{sid}-Recovery.md", render_doc(bodies["recovery"], renv, RECOVERY, opt))
            for t in se["tasks"]:
                tenv = env_for("task", t, sprint=sp, session=se, task=t, res_forms=res_forms)
                tenv.vals.update(common)
                tenv.vals.update({"##": M(f"{t['number']:02d}"), "Agent": M(t["agent"]), "TaskName": M(t["name"]),
                                  "Haiku|Sonnet|Opus": M(t["agent"]), "X": M(t["estimate_k"])})
                put(f"{sd}/{task_filename(spec, sp, se, t)}",
                    render_doc(bodies["task"], tenv, TASK, t.get("optional_sections", ())))
            put(f"{sd}/Outputs/.gitkeep", "")
    return files, rec


def write_tree(files, out_dir):
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(str(out))
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))


def unmasked_braces(text):
    """Brace names that survive outside FILL markers, callouts, fences and the skeleton fence."""
    hits, depth, skel = [], 0, False
    for ln in text.split("\n"):
        if skel:
            skel = ln.strip() != "```"
            continue
        if depth == 0 and ln.startswith("```markdown"):
            skel = True
            continue
        if ln.startswith("## "):
            depth = 0
        if depth or ln.startswith(("```", "| Source Task |")) or ln.lstrip().startswith(">"):
            depth = fence_step(ln, depth)
            continue
        cleaned = re.sub(r"<!-- FILL: \{.+?\} -->", "", ln)
        # Layer-member sets such as {1, 2} are the rendered notation of the dispatch layers, not placeholders.
        hits.extend(inner for _a, _b, inner in brace_spans(cleaned) if not re.fullmatch(r"\d+(, \d+)*", inner))
    return hits


# ---------------------------------------------------------------- spec lint

def _keys(obj, kind, where, errors):
    if not isinstance(obj, dict):
        errors.append(f"{where}: expected an object, got {json.dumps(obj, ensure_ascii=False)}")
        return False
    required, optional = SCHEMA[kind]
    for k in sorted(required - obj.keys()):
        errors.append(f"{where}: missing required key '{k}'")
    for k in sorted(obj.keys() - required - optional):
        errors.append(f"{where}: unknown key '{k}' (the spec is metadata only and declares no headings)")
    return not (required - obj.keys())


def _name(obj, key, where, errors):
    if not NAME_RE.match(str(obj.get(key, ""))):
        errors.append(f"{where}: '{key}' must be PascalCase letters and digits, got {json.dumps(obj.get(key))}")


def _list_of(obj, key, where, errors, what, item_ok=None, nonempty=False):
    """Check that obj[key] (default []) is a list whose items pass item_ok; quote the value when not."""
    value = obj.get(key, [])
    if (not isinstance(value, list) or (nonempty and not value)
            or (item_ok is not None and not all(item_ok(v) for v in value))):
        errors.append(f"{where}: '{key}' must be {what}, got {json.dumps(value, ensure_ascii=False)}")
        return False
    return True


def _number(obj, label, where, errors, taken):
    """An integer `number`, unique among its siblings (a duplicate gives two files one path)."""
    n = obj["number"]
    if not is_int(n):
        errors.append(f"{where}: 'number' must be an integer, got {json.dumps(n, ensure_ascii=False)}")
        return
    if n in taken:
        errors.append(f"{where}: duplicate {label} number {n}; each {label} needs its own number, "
                      "or two rendered files share one path")
    taken.add(n)


def _pairs(spec, numbers, errors):
    if not _list_of(spec, "parallel_pairs", "plan", errors, "a list of [sprint number, sprint number] pairs"):
        return
    for pair in spec.get("parallel_pairs", []):
        # Element types first: set() over an unhashable element would raise, not report.
        ok = (isinstance(pair, list) and len(pair) == 2 and all(is_int(n) for n in pair)
              and pair[0] != pair[1] and set(pair) <= numbers)
        if not ok:
            errors.append(f"plan.parallel_pairs: {json.dumps(pair, ensure_ascii=False)} is not a pair of "
                          "two different declared sprint numbers")


def _optional(obj, kinds, opt, where, errors):
    if not _list_of(obj, "optional_sections", where, errors, "a list of section names",
                    item_ok=lambda v: isinstance(v, str)):
        return
    allowed = set().union(*(opt[k] for k in kinds))
    for name in obj.get("optional_sections", []):
        if name not in allowed:
            errors.append(f"{where}: optional_sections entry {json.dumps(name)} is not an OPTIONAL "
                          f"section of {' or '.join(TEMPLATE_FILES[k] for k in kinds)}")


def lint_spec(spec, templates_dir=DEFAULT_TEMPLATES, project_root=None):
    """Return a list of error strings; an empty list means the spec renders."""
    errors = []
    root = Path(project_root) if project_root else Path.cwd()
    opt = optional_headings(templates_dir)
    if not _keys(spec, "plan", "plan", errors):
        return errors
    if not ABBREV_RE.match(str(spec["abbrev"])):
        errors.append(f"plan: 'abbrev' must be 2-6 of A-Z and 0-9, letter first, got {json.dumps(spec['abbrev'])}")
    if not DATE_RE.match(str(spec["created"])):
        errors.append(f"plan: 'created' must be YYYY-MM-DD, got {json.dumps(spec['created'])}")
    _optional(spec, ("master",), opt, "plan", errors)
    for key in ("dependencies", "decisions"):
        if _list_of(spec, key, "plan", errors, "a list of rows"):
            for k, row in enumerate(spec.get(key, [])):
                _keys(row, key, f"plan.{key}[{k}]", errors)
    if not _list_of(spec, "sprints", "plan", errors, "a list of sprints"):
        return errors
    numbers = {s["number"] for s in spec["sprints"] if isinstance(s, dict) and is_int(s.get("number"))}
    _pairs(spec, numbers, errors)
    sprint_numbers = set()
    for si, sp in enumerate(spec["sprints"]):
        sw = f"sprint[{si}]"
        if not _keys(sp, "sprint", sw, errors):
            continue
        _number(sp, "sprint", sw, errors, sprint_numbers)
        _name(sp, "name", sw, errors)
        _optional(sp, ("sprint",), opt, sw, errors)
        if not _list_of(sp, "sessions", sw, errors, "a list of sessions"):
            continue
        session_numbers = set()
        for ei, se in enumerate(sp["sessions"]):
            ew = f"{sw}.session[{ei}]"
            if not _keys(se, "session", ew, errors):
                continue
            _number(se, "session", ew, errors, session_numbers)
            _name(se, "name", ew, errors)
            _optional(se, ("orchestration", "recovery"), opt, ew, errors)
            if se["mode"] not in MODES:
                errors.append(f"{ew}: 'mode' must be DIRECT or DELEGATED, got {json.dumps(se['mode'])}")
            if _list_of(se, "tasks", ew, errors, "a list of tasks"):
                _lint_tasks(se["tasks"], ew, opt, root, errors)
    return errors


def _lint_tasks(tasks, ew, opt, root, errors):
    seen, task_numbers = set(), set()
    for ti, t in enumerate(tasks):
        tw = f"{ew}.task[{ti}]"
        ok = _keys(t, "task", tw, errors)
        if isinstance(t, dict) and is_int(t.get("number")) and not ok:
            seen.add(t["number"])
        if not ok:
            continue
        _number(t, "task", tw, errors, task_numbers)
        _name(t, "name", tw, errors)
        _optional(t, ("task",), opt, tw, errors)
        if t["agent"] not in AGENTS:
            errors.append(f"{tw}: 'agent' must be Opus, Sonnet or Haiku, got {json.dumps(t['agent'])}")
        if not is_number(t["estimate_k"]):
            errors.append(f"{tw}: 'estimate_k' must be a number, got {json.dumps(t['estimate_k'])}")
        _list_of(t, "outputs", tw, errors, "a non-empty list of non-empty path strings",
                 item_ok=lambda v: isinstance(v, str) and bool(v.strip()), nonempty=True)
        if _list_of(t, "depends_on", tw, errors, "a list of task numbers (integers) and literal strings",
                    item_ok=lambda v: is_int(v) or isinstance(v, str)):
            for d in int_deps(t):
                if d not in seen:
                    errors.append(f"{tw}: depends_on {d} is not an earlier task of this session")
        if is_int(t["number"]):
            seen.add(t["number"])
        if _list_of(t, "required_context", tw, errors, "a list of Required Context rows"):
            for ri, row in enumerate(t["required_context"]):
                _lint_rc_row(row, f"{tw}.required_context[{ri}]", root, errors)


def rc_kind(row):
    return row.get("kind", "path") if isinstance(row, dict) else None


def _lint_rc_row(row, where, root, errors):
    quoted = json.dumps(row, ensure_ascii=False)
    kind = rc_kind(row)
    if f"rc:{kind}" not in SCHEMA:
        errors.append(f"{where}: Required Context row kind must be path, span or command: {quoted}")
        return
    required, optional = SCHEMA[f"rc:{kind}"]
    missing, unknown = sorted(required - row.keys()), sorted(row.keys() - required - optional)
    if missing or unknown:
        detail = "; ".join(filter(None, [missing and f"missing {', '.join(missing)}",
                                         unknown and f"unknown {', '.join(unknown)}"]))
        errors.append(f"{where}: Required Context {kind} row is malformed ({detail}): {quoted}")
        return
    for key in ("kib", "tokens_k"):
        if not is_number(row[key]):
            errors.append(f"{where}: Required Context '{key}' must be a number, got "
                          f"{json.dumps(row[key], ensure_ascii=False)}: {quoted}")
    if kind in ("path", "span"):
        if not isinstance(row["path"], str) or not row["path"].strip():
            errors.append(f"{where}: Required Context 'path' must be a non-empty string: {quoted}")
            return
        reason = prose_reason(row["path"], root)
        if reason:
            errors.append(f"{where}: Required Context path is prose, not a path ({reason}); a command's "
                          f"output belongs in a kind \"command\" row: {quoted}")


def prose_reason(path, root):
    """Why a path cell is prose, or None when it reads as a path (the prose rule in the module docstring).

    Only a value of two or more whitespace-separated words can be prose. Such a
    value is prose when it has no path separator and no extension, or when
    `unresolved_reason` classes it as not a path. A one-word value is always a
    path: `Makefile`, `src/orchard/` and `src/output_writer.py` all pass.
    """
    if len(path.split()) < 2:
        return None
    if not re.search(r"[/\\]", path) and not Path(path).suffix:
        return "words with no path separator and no extension"
    reason = unresolved_reason(path, root)
    return reason if reason.startswith("not a path") else None


# ---------------------------------------------------------------- heading conformance

def file_kind(name):
    n = name.replace("\\", "/").rsplit("/", 1)[-1]
    for suffix, kind in (("-Master-Plan.md", "master"), ("-Sprint-Plan.md", "sprint"),
                         ("-Orchestration.md", "orchestration"), ("-Recovery.md", "recovery")):
        if n.endswith(suffix):
            return kind
    return "task" if TASK_FILE_RE.search(n) else None


def heading_pattern(heading):
    """Exact text, or a regex when the template heading carries a placeholder (an instance heading)."""
    spans = brace_spans(heading)
    if not spans:
        return heading
    parts, pos = [], 0
    for a, b, _inner in spans:
        parts.append(re.escape(heading[pos:a]) + ".+?")
        pos = b
    parts.append(re.escape(heading[pos:]))
    return re.compile("".join(parts) + r"\Z")


def template_heading_sets(templates_dir=DEFAULT_TEMPLATES):
    """Per kind: (ordered template H2 patterns, catch-all heading = the template's last H2)."""
    out = {}
    for kind, fname in TEMPLATE_FILES.items():
        _pre, secs = split_sections(extract_body(Path(templates_dir) / fname))
        heads = [norm_heading(s[0]) for s in secs]
        out[kind] = ([heading_pattern(h) for h in heads], heads[-1])
    return out


def _matches(heading, patterns):
    return any(p == heading if isinstance(p, str) else p.match(heading) for p in patterns)


def _fence_closes_later(lines, k, depth):
    """Whether the fence open at line k returns to depth 0 on some later line."""
    for ln in lines[k + 1:]:
        depth = fence_step(ln, depth)
        if depth == 0:
            return True
    return False


def check_text(text, patterns, catch_all):
    """Return (H2 count, stray H2 list). Fence-aware; a template H2 inside a stuck fence resyncs it.

    A fence is stuck when it never closes later in the file. A template H2 inside
    a fence that does close is fence content (a pasted example), so it leaves the
    depth alone and the fence's own closing line still closes it.
    """
    count, strays, depth, after = 0, [], 0, False
    lines = text.replace("\r\n", "\n").split("\n")
    for k, ln in enumerate(lines):
        if ln.startswith("## "):
            h = norm_heading(ln)
            if depth and (not _matches(h, patterns) or _fence_closes_later(lines, k, depth)):
                continue
            depth = 0
            count += 1
            if after or not _matches(h, patterns):
                strays.append(h)
            if h == catch_all:
                after = True
            continue
        depth = fence_step(ln, depth)
    return count, strays


def collect_plan_files(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files.extend(f for f in sorted(p.rglob("*.md")) if "Outputs" not in f.relative_to(p).parts)
        else:
            files.append(p)
    return files


def check_headings(paths, templates_dir=DEFAULT_TEMPLATES):
    """Per file: {path, kind, h2, stray}; kind None means the name is not a plan file (skipped)."""
    sets = template_heading_sets(templates_dir)
    results = []
    for f in collect_plan_files(paths):
        kind = file_kind(str(f))
        if kind is None:
            results.append({"path": str(f), "kind": None, "h2": 0, "stray": []})
            continue
        count, strays = check_text(read_lf(f), *sets[kind])
        results.append({"path": str(f), "kind": kind, "h2": count, "stray": strays})
    return results


# ---------------------------------------------------------------- CLI

def load_spec(path):
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8")), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"cannot read spec {path}: {exc}"


# Every error class a malformed spec value can raise inside render_all (LookupError covers KeyError
# and IndexError, ArithmeticError covers a zero division).
SPEC_VALUE_ERRORS = (ArithmeticError, AssertionError, AttributeError, LookupError, StopIteration,
                     TypeError, ValueError)


def cmd_render(args):
    spec, err = load_spec(args.spec)
    if err:
        print(f"REFUSED: {err}. Fix: pass a readable UTF-8 JSON spec.")
        return 2
    errors = lint_spec(spec, args.templates)
    if errors:
        for e in errors:
            print(f"LINT: {e}")
        print(f"REFUSED: {len(errors)} spec lint error(s). Fix: correct the spec, then re-run "
              f"`scaffold_plan.py lint-spec --spec {args.spec}` until it prints `lint=clean`.")
        return 2
    out = Path(args.out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        print(f"REFUSED: {out} exists and is not an empty folder. Fix: pass a new or empty --out folder; "
              "the renderer never overwrites plan files.")
        return 2
    try:
        files, _rec = render_all(spec, args.templates, args.date)
    except SPEC_VALUE_ERRORS as exc:  # defence in depth: lint_spec should reject any spec that fails here
        reason = " ".join(f"{type(exc).__name__}: {exc}".split())
        print(f"REFUSED: the render failed on a lint-clean spec ({reason}). Fix: correct the spec; "
              "lint-spec did not catch this case.")
        return 2
    write_tree(files, out)
    fills = sum(t.count("<!-- FILL: ") for t in files.values())
    leaked = {rel: unmasked_braces(t) for rel, t in files.items() if rel.endswith(".md")}
    leaked = {rel: names for rel, names in leaked.items() if names}
    print(f"rendered {len(files)} files to {out}; fill_markers={fills}; surviving_placeholders="
          f"{sum(len(v) for v in leaked.values())}")
    for rel, names in leaked.items():
        print(f"SURVIVING: {rel}: {', '.join(names)}")
    return 1 if leaked else 0


def cmd_lint(args):
    spec, err = load_spec(args.spec)
    if err:
        print(f"ERROR: {err}")
        return 2
    errors = lint_spec(spec, args.templates)
    for e in errors:
        print(f"LINT: {e}")
    print("lint=clean" if not errors else f"lint_errors={len(errors)}")
    return 1 if errors else 0


def cmd_check(args):
    missing = [p for p in args.paths if not Path(p).exists()]
    if missing:
        print(f"ERROR: no such path: {', '.join(missing)}")
        return 2
    results = check_headings(args.paths, args.templates)
    total = 0
    for r in results:
        if r["kind"] is None:
            print(f"{r['path']}: skip (not a plan file name)")
            continue
        total += len(r["stray"])
        tail = "; ".join(r["stray"])
        print(f"{r['path']}: kind={r['kind']} h2={r['h2']} stray={len(r['stray'])}" + (f" [{tail}]" if tail else ""))
    print(f"stray_h2={total} files={sum(1 for r in results if r['kind'])}")
    return 1 if total else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render, lint and check plan skeletons from the plan templates.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="render the plan tree from a spec")
    r.add_argument("--spec", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--templates", default=str(DEFAULT_TEMPLATES))
    r.add_argument("--date", help="YYYY-MM-DD for every date placeholder (default: the spec's created)")
    s = sub.add_parser("lint-spec", help="validate a spec")
    s.add_argument("--spec", required=True)
    s.add_argument("--templates", default=str(DEFAULT_TEMPLATES))
    c = sub.add_parser("check-headings", help="report H2 headings outside the template set")
    c.add_argument("paths", nargs="+", metavar="PATH")
    c.add_argument("--templates", default=str(DEFAULT_TEMPLATES))
    args = ap.parse_args(argv)
    if args.cmd == "render":
        if args.date and not DATE_RE.match(args.date):
            print(f"REFUSED: --date {args.date} is not YYYY-MM-DD. Fix: pass a date such as 2026-01-31.")
            return 2
        return cmd_render(args)
    if args.cmd == "lint-spec":
        return cmd_lint(args)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
