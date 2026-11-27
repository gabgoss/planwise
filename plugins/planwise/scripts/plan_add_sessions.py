"""The `add-sessions` command of `plan_build.py`: render named sessions into an existing built plan.

`plan_build.py` documents the command line and the report. Three rules hold for every
run, and they are why this is not a `build` with a filter:

    No existing path is written. A rendered path that exists refuses the whole run.
    No existing file changes. A gate that rewrites one gets its bytes put back.
    No existing manifest hash moves. A hand edit stays a hand edit to the next build.

The Sprint Plan and the Master Plan are hand-edited prose, so the run prints their new
lines and edits neither file.
"""

import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a direct import must not grow scripts/__pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import plan_build as pb
import scaffold_plan as sp

# The gates whose detail lines name the file they are about. A scan line names the cited file and never the
# task that cites it, and the index gate speaks about the whole plan, so neither is cut.
FILE_GATES = ("estimates", "headings", "deviations")
FAILED_CALL_RE = re.compile(r"\bexit=[1-9]|: ERROR:")  # an estimates call that failed may name no file
UNGRADED = "cannot grade the tree"  # the deviation gate graded nothing


def _group(rel):
    """The session of a rendered path, the plan group of a plan document, or None for any other file."""
    doc = pb.doc_id(rel)
    return None if doc is None else pb.session_of(doc)


def session_files(tree, sessions):
    """The rendered files of the named sessions: each session document, and each other file in its folder."""
    folders = tuple({f"{rel.rsplit('/', 1)[0]}/" for rel in tree if _group(rel) in sessions})
    return {rel: text for rel, text in tree.items()
            if _group(rel) in sessions or (pb.doc_id(rel) is None and rel.startswith(folders))}


def named_sessions(core, sessions):
    """[(sprint, session)] of the core spec for each named SXX-YY, in spec order."""
    return [(sprint, session) for sprint in core["sprints"] for session in sprint["sessions"]
            if f"S{sprint['number']:02d}-{session['number']:02d}" in sessions]


def plan_documents(skeleton, pairs):
    """The Master Plan and the Sprint Plan of each sprint that holds a named session."""
    wanted = {"MASTER", *(f"S{sprint['number']:02d}" for sprint, _session in pairs)}
    return {rel: text for rel, text in skeleton.items() if pb.doc_id(rel) in wanted}


def row_patterns(core, pairs):
    """One test per named session: a line holds its session id, or its sprint and session folders.

    The Sprint Plan names a session by id. The Master Plan tracking row names it by
    `Sprint-XX` and the session folder.
    """
    tests = []
    for sprint, session in pairs:
        sid = re.compile(rf"(?<!\w){re.escape(sp.session_id(core, sprint, session))}(?!\d)")
        folder = sp.session_dir(sprint, session).rsplit("/", 1)[1]
        folder_re = re.compile(rf"(?<![\w-]){re.escape(folder)}(?![\w-])")
        sprint_re = re.compile(rf"(?<!\w)Sprint-{sprint['number']:02d}(?!\d)")
        tests.append((sid, folder_re, sprint_re))
    return tests


def add_row_lines(plan_files, tests):
    """One `ADD-ROW: {rel}: {line}` per line of the plan documents that names a session."""
    return [f"ADD-ROW: {rel}: {line.rstrip()}" for rel, text in plan_files.items() for line in text.splitlines()
            if any(sid.search(line) or (folder.search(line) and sprint.search(line)) for sid, folder, sprint in tests)]


def sessions_line(core, pairs):
    """The session counts of the spec: one per sprint that holds a named session, then the plan's."""
    sprints = {sprint["number"]: len(sprint["sessions"]) for sprint, _session in pairs}
    total = sum(len(sprint["sessions"]) for sprint in core["sprints"])
    return f"SESSIONS: sprint={','.join(str(sprints[n]) for n in sorted(sprints))} plan={total}"


def block_lines(plan_files, core, pairs, out, templates):
    """The `BLOCK:` lines to copy: each named session's `## Session Details` block.

    A Sprint Plan that does not exist under `out` is printed whole, because this command writes none.
    """
    patterns = sp.template_heading_sets(templates)["sprint"][0]
    lines = []
    for rel, text in plan_files.items():
        if pb.doc_id(rel) == "MASTER":
            continue
        body = text.split("\n")
        if not (out / rel).is_file():
            lines.extend(f"BLOCK: {rel}: {line.rstrip()}" for line in body)
            continue
        levels = pb.heading_levels(body, patterns)
        for sid, _folder, _sprint in row_patterns(core, pairs):
            for start in (k for k, level in levels.items() if level == 3 and sid.search(body[k])):
                end = pb.before_separator(body, start, pb.section_end(body, levels, start))
                lines.extend(f"BLOCK: {rel}: {line.rstrip()}" for line in body[start:end])
    return lines


def held_sessions(out, old):
    """The sessions the plan on disk already holds, by its manifest and by its Orchestration files."""
    listed = {_group(rel) for rel in old if (out / rel).is_file()}
    found = {_group(path.name) for path in out.rglob("*-Orchestration.md")}
    return (listed | found) - {None, pb.PLAN_GROUP}


def moved_sessions(out, old, tree):
    """The built Orchestration files on disk that the spec no longer renders at their path."""
    return [rel for rel in old
            if (pb.doc_id(rel) or "").endswith("-ORCH") and (out / rel).is_file() and rel not in tree]


def only_new(report, files):
    """(the gate report cut to the lines about a new file, the count of the lines cut).

    A line is about a new file when it names one. A line that reports a failed estimates
    call or an ungraded tree stays, because it may name no file. A finding with no detail
    line stays too.
    """
    names = tuple(rel.rsplit("/", 1)[-1] for rel in files if pb.doc_id(rel) is not None)
    kept_report, outside = [], 0
    for name, status, figures, details in report:
        if name in FILE_GATES and details and figures != "crashed=1":
            kept = [line for line in details if any(new in line for new in names) or UNGRADED in line
                    or (name == "estimates" and FAILED_CALL_RE.search(line))]
            outside += len(details) - len(kept)
            status, details = ("finding" if kept else "ok"), kept
        kept_report.append((name, status, figures, details))
    return kept_report, outside


def hold_bytes(out):
    """{path: bytes} of every Markdown file already under `out`."""
    return {path: path.read_bytes() for path in sorted(Path(out).rglob("*.md")) if path.is_file()}


def put_back(held, out):
    """Restore each held file that changed. Return their paths relative to `out`."""
    changed = []
    for path, data in held.items():
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
            changed.append(path.relative_to(Path(out)).as_posix())
    return changed


def read_built_manifest(path):
    """(file hashes, stale hashes, marker record) of the manifest a build wrote."""
    return pb.read_manifest(path), pb.read_stale(path), pb.read_markers(path)


def record_added(path, out, added, old, stale, markers):
    """Add the new files to the manifest. Every earlier hash stays as the last build wrote it."""
    hashes = {**old, **{rel: pb.file_hash(Path(out) / rel) for rel in added}}
    pb.store_manifest(path, hashes, {rel: digest for rel, digest in stale.items() if rel not in added}, markers)


def cmd_add_sessions(args):
    refusal = pb.build_inputs_refusal(args)
    if refusal:
        print(refusal)
        return 2
    ready = pb.render_command(args, args.date)
    if ready is None:
        return 2
    caps, spec, core, skeleton, index = ready
    sessions = list(dict.fromkeys(args.sessions))
    in_spec = {pb.session_of(doc) for doc in index} - {pb.PLAN_GROUP}
    unknown = [s for s in sessions if s not in in_spec]
    if unknown:
        for s in unknown:
            print(f"REFUSED: session {s} is not in the spec. Fix: pass a session such as S01-01.")
        return 2
    abbrev = core["abbrev"]
    if pb.is_meta(spec):
        root = f"Meta-{abbrev}"
        if Path(args.out).resolve().name == root:
            print(f"REFUSED: --out {args.out} already ends in {root}, and the build adds that folder. "
                  "Fix: pass its parent folder.")
            return 2
        args.out = str(Path(args.out) / root)
    out = Path(args.out)
    if not out.is_dir():
        print(f"REFUSED: {args.out} is not a built plan folder. Fix: pass the folder that build wrote.")
        return 2
    path = pb.manifest_path(args.spec, spec)
    try:
        old, stale, known = read_built_manifest(path)
    except pb.MANIFEST_ERRORS as exc:
        print(f"REFUSED: cannot read {path.name} ({type(exc).__name__}: {exc}). "
              "Fix: run build for this plan first, or restore the file.")
        return 2
    if not any((out / rel).is_file() for rel in old):
        print(f"REFUSED: {args.out} holds no file that {path.name} lists. Fix: pass the folder that build wrote.")
        return 2

    docs, load_errors, figures = pb.load_all_bodies(args.spec, args.bodies_dir, core, index, spec)
    lint = [line for group in (pb.PLAN_GROUP, *sessions)  # the plan bodies fill the printed rows
            for line in pb.lint_bodies(index, docs, load_errors, group, known)[0]]
    if lint:
        pb.refuse_errors(lint, "bodies lint", "correct the bodies files, then re-run this command.")
        return 2
    pairs = named_sessions(core, sessions)
    skeleton_new = session_files(skeleton, sessions)
    files, left = pb.apply_bodies(skeleton_new, docs, args.templates)
    plan_files, _left = pb.apply_bodies(plan_documents(skeleton, pairs), docs, args.templates)
    if pb.is_meta(spec):
        plan_level = f"{pb.OUTPUTS_DIR}/.gitkeep"  # `meta_tree` adds it, and the built plan already holds it
        skeleton_new, files, plan_files = ({rel: text for rel, text in pb.meta_tree(tree, abbrev).items()
                                            if rel != plan_level} for tree in (skeleton_new, files, plan_files))
    over = sp.path_cap_lines(list(files), args.out, caps)
    if over:
        print("\n".join(over))
        return 2
    existing = [rel for rel in files if os.path.lexists(out / rel)]
    if existing:
        for rel in existing:
            print(f"EXISTS: {rel}")
        print(f"REFUSED: {len(existing)} path(s) already exist under {args.out}. "
              "Fix: name only sessions the plan does not hold yet.")
        return 2
    again = [s for s in sessions if s in held_sessions(out, old)]
    if again:
        for s in again:
            print(f"REFUSED: session {s} is already in the plan under {args.out}. "
                  "Fix: name only sessions the plan does not hold yet.")
        return 2
    moved = moved_sessions(out, old, skeleton)
    if moved:
        for rel in moved:
            print(f"MOVED: {rel}")
        print(f"REFUSED: the spec renames, renumbers or drops {len(moved)} built session(s). "
              "Fix: restore their names and numbers in the spec, and give each new session an unused number.")
        return 2

    leaked ={rel: names for rel, text in skeleton_new.items()
              if rel.endswith(".md") and (names := sp.unmasked_braces(text))}
    new_index = {doc: info for doc, info in index.items() if pb.session_of(doc) in sessions}
    # A manifest with no marker record keeps none: a record of the new documents alone would hide that.
    markers = None if known is None else {**known, **pb.known_markers(known, new_index, docs)}
    held = hold_bytes(out)
    landed = []
    try:
        pb.write_built(files, out, landed)
        record_added(path, out, landed, old, stale, markers)
    except OSError as exc:
        reason = " ".join(f"{type(exc).__name__}: {exc}".split())
        for rel in landed:
            print(f"LANDED: {rel}")
        print(f"FAILED: the write stopped after {len(landed)} of {len(files)} files ({reason}). "
              "Fix: delete the LANDED files, free the --out folder, then re-run.")
        print(f"fill_remaining={left}\nexit=3")
        return 3
    print(f"added {len(files)} files to {args.out}; fill_remaining={left}; surviving_placeholders="
          f"{sum(len(v) for v in leaked.values())}")
    for rel, names in leaked.items():
        print(f"SURVIVING: {rel}: {', '.join(names)}")

    try:
        report = pb.run_chain(args, files, abbrev)
    finally:
        restored = put_back(held, out)
    report, outside = only_new(report, files)
    pb.print_gates(report, len(files))
    print(f"outside={outside}")
    for rel in restored:
        print(f"KEPT: {rel}: a gate rewrote this file, and the run put its bytes back")
    for line in pb.delta_lines(args.out, files, figures):
        print(line)
    try:
        record_added(path, out, landed, old, stale, markers)  # the estimates gate rewrote the new task files
    except OSError as exc:
        for rel in landed:
            print(f"LANDED: {rel}")
        print(f"REFUSED: the manifest rewrite failed ({type(exc).__name__}: {exc}). Fix: delete the LANDED files, "
              "free the --out folder, then re-run. Do not run build --force, which overwrites hand edits.")
        print(f"fill_remaining={left}\nexit=3")
        return 3

    for rel in plan_files:
        if pb.doc_id(rel) != "MASTER" and not (out / rel).is_file():
            print(f"NOTE: {rel} does not exist under {args.out}. This command writes no Sprint Plan, so add it by hand.")
    printed = [*add_row_lines(plan_files, row_patterns(core, pairs)),
               *block_lines(plan_files, core, pairs, out, args.templates)]
    for line in printed:
        print(line)
    unfilled = sum("<!-- FILL:" in line for line in printed)
    if unfilled:
        print(f"NOTE: {unfilled} printed line(s) still hold a FILL marker. Write its body in the plan bodies file.")
    print(sessions_line(core, pairs))
    findings = any(status == "finding" for _name, status, _figures, _details in report)
    code = 1 if left or leaked or unfilled or findings else 0
    print(f"fill_remaining={left}\nexit={code}")
    return code
