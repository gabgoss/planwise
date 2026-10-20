#!/usr/bin/env python3
"""Doctor's scripted probes: the feedback capability probe (Stage 16), the
feedback directory presence check (Stage 17), the capture self-containment
scan (Step 7) and the bookkeeping index read-gate scan (Step 8).

`run_probes(cfg)` loads the project's config.yaml once, then runs the four
probes in order. Each one prints the banner and the verdict lines the doctor
handler specifies. Nothing here asks a question, installs anything or writes
a file.

Every probe is fail-safe: an exception inside one prints a single
`<name>: the check failed: <reason>` line and the next probe still runs, so the
probes never change doctor's exit status. Output carries no timestamp, and
findings are sorted, so two runs over one unchanged tree print the same bytes.
The one exception is Stage 17's queued-draft count: a queued draft expires a
fixed number of days after it was created, so a later run over the same tree
can print a lower count.

Stage 17 imports the feedback-draft helper when it runs, not when this module
loads, so a helper that fails to import costs only that one count.

Stage 16 learns every fact about `gh` from one function, `_gh_environment()`.
That function is the only place in this module that spawns a process, so a
caller that must not reach the network replaces it and nothing else.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_loader
from backlog_index_schema import (
    _changelog_filename,
    _index_naming,
    is_generated_index_file,
)
from doctor_audits import _load_project_config
from read_limits import classify_file

_FEEDBACK_BANNER = "planwise doctor — feedback capability probe"
_FEEDBACK_DIR_BANNER = "planwise doctor — feedback directory presence check"
_READ_GATE_BANNER = "planwise doctor — bookkeeping index read-gate scan"

_GH_TIMEOUT_SECONDS = 5
_ABSENT_GH = {"path": None, "note": "", "version": "", "authenticated": False, "timed_out": False}

_REMEDY_DISABLED = "feedback.enabled is false — /planwise feedback drafts locally and posts nothing"
_REMEDY_NO_GH = (
    "gh not found on PATH or at a known install location — install from "
    "https://cli.github.com/, or run /planwise upgrade to be offered the install"
)
_REMEDY_NO_AUTH = "gh is installed but not authenticated — run: gh auth login"
_QUEUED_LABEL = "model drafts queued:"
_REMEDY_QUEUED = (
    "review them with /planwise feedback --drafts, or post one with /planwise feedback --post <draftId>"
)
_REMEDY_TIMEOUT = (
    f"gh did not answer within {_GH_TIMEOUT_SECONDS} s, so the posting gate is unproven — re-run /planwise doctor"
)

# A path token: a Windows drive path, a Git-Bash drive path (`/c/Users/...`, any
# single drive letter), or a POSIX path under a user/repo root. Case-insensitive.
_PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z])[A-Za-z]:[\\/][^\s`\"'<>|*?]*"
    r"|(?<![\w.\-])/[A-Za-z]/[^\s`\"'<>|*?]+"
    r"|(?<![\w.\-])/(?:Users|home|repos)/[^\s`\"'<>|*?]*",
    re.IGNORECASE,
)
_GIT_BASH_DRIVE_RE = re.compile(r"^/([A-Za-z])/")
_TRANSIENT_RE = re.compile(r"see (?:the )?(?:session|diff|scratch)|session-only|in scratch", re.IGNORECASE)
_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_KNOWN_CONDITION_RE = re.compile(r"<!--\s*known-condition:\s*(.*?)\s*-->")

_NO_NOTE = (
    'No known-condition note recorded — add a "<!-- known-condition: ... -->" '
    "comment naming the plan or item that addresses this, or file a backlog item."
)


# --------------------------------------------------------------------------
# Stage 16: the gh seam
# --------------------------------------------------------------------------

def _known_gh_locations() -> list:
    """The install locations to test after PATH, by platform, in order."""
    if sys.platform == "win32":
        candidates = [Path(r"C:\Program Files\GitHub CLI\gh.exe")]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Programs" / "GitHub CLI" / "gh.exe")
        candidates.append(Path(r"C:\Program Files (x86)\GitHub CLI\gh.exe"))
        return candidates
    if sys.platform == "darwin":
        return [Path("/opt/homebrew/bin/gh"), Path("/usr/local/bin/gh")]
    return [
        Path("/usr/bin/gh"),
        Path("/usr/local/bin/gh"),
        Path("/home/linuxbrew/.linuxbrew/bin/gh"),
        Path.home() / ".local" / "bin" / "gh",
    ]


def _gh_run(gh_path, *args):
    """One timed `gh` call, as `(result, timed_out)`. `(None, False)` when the
    process cannot start, `(None, True)` when it did not answer in time."""
    try:
        result = subprocess.run(
            [str(gh_path), *args],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, True
    except (OSError, subprocess.SubprocessError):
        return None, False
    return result, False


def _resolve_gh() -> tuple:
    """PATH first, then each known install location in order. A candidate counts
    only when its `--version` call exits 0, and the first one that counts wins,
    so a broken PATH shim falls through to the next candidate. Returns
    `(path, note, version_result, timed_out)`: the note is empty for a PATH hit
    and carries the report line for a known-location hit, and `timed_out` is
    true when any candidate did not answer in time."""
    timed_out = False
    found = shutil.which("gh")
    candidates = [(Path(found), "")] if found else []
    for candidate in _known_gh_locations():
        if candidate.is_file():
            candidates.append(
                (candidate, f"gh found at {candidate}, not on this session's PATH — a new terminal will resolve it")
            )
    for path, note in candidates:
        result, slow = _gh_run(path, "--version")
        timed_out = timed_out or slow
        if result is not None and result.returncode == 0:
            return path, note, result, timed_out
    return None, "", None, timed_out


def _gh_environment() -> dict:
    """The seam: every `gh` fact Stage 16 reports, from the only function that
    resolves or spawns `gh`. A `gh` that will not report a version counts as
    not resolvable. `timed_out` is true when a call that decides the answer did
    not respond within the timeout (no candidate answered, or the auth call did
    not), so the caller can tell a slow `gh` from a missing or logged-out one."""
    path, note, version, timed_out = _resolve_gh()
    if path is None:
        return dict(_ABSENT_GH, timed_out=timed_out)
    lines = [line.strip() for line in (version.stdout or "").splitlines() if line.strip()]
    auth, auth_slow = _gh_run(path, "auth", "status")
    return {
        "path": path,
        "note": note,
        "version": lines[0] if lines else "",
        "authenticated": auth is not None and auth.returncode == 0,
        "timed_out": auth_slow,
    }


def _stage_16(config: dict) -> None:
    feedback = config_loader.get_feedback_config(config)
    enabled, drafts = feedback["enabled"], feedback["drafts"]
    env = _gh_environment()
    path, authenticated = env["path"], env["authenticated"]
    timed_out = env.get("timed_out", False)
    if path is None and timed_out:
        resolvable, auth = "unknown — gh did not answer", "unknown"
    elif path is None:
        resolvable, auth = "no", "n/a — gh absent"
    else:
        where = "on PATH" if not env["note"] else f"at {path}"
        resolvable = f"yes — {where}  {env['version']}".rstrip()
        auth = "unknown — gh did not answer" if timed_out else ("yes" if authenticated else "no")
    print(f"  feedback.enabled:  {'true' if enabled else 'false'}")
    print(f"  feedback.drafts:   {drafts}")
    print(f"  gh resolvable:     {resolvable}")
    print(f"  gh authenticated:  {auth}")
    remedies = []
    if not enabled:
        remedies.append(_REMEDY_DISABLED)
    if path is None and not timed_out:
        remedies.append(_REMEDY_NO_GH)
    if path is not None and env["note"]:
        remedies.append(env["note"])
    if timed_out:
        remedies.append(_REMEDY_TIMEOUT)
    elif path is not None and not authenticated:
        remedies.append(_REMEDY_NO_AUTH)
    print()
    for line in remedies:
        print(f"  {line}")
    if remedies:
        print()
    if enabled and path is not None and authenticated:
        print("Upstream posting: ENABLED — reports post directly")
    else:
        feedback_dir = Path(config["_feedback_dir"]).as_posix()
        print(f"Upstream posting: DRAFT-ONLY — reports are saved to {feedback_dir}/ and must be filed by hand")


# --------------------------------------------------------------------------
# Stage 17: the feedback directory
# --------------------------------------------------------------------------

def _queued_model_drafts(feedback_dir: Path) -> int:
    """How many model drafts the helper's `list` would show as queued. The
    helper's own read-only `count_queued` answers, so doctor and `list` share
    one expiry predicate. `list` itself is never called, because it writes."""
    import feedback_drafts

    return feedback_drafts.count_queued(feedback_dir)


def _stage_17(config: dict) -> None:
    feedback_dir = Path(config["_feedback_dir"])
    exists = feedback_dir.is_dir()
    queued, count_failure = None, ""
    if exists:
        try:
            queued = _queued_model_drafts(feedback_dir)
        except Exception as exc:  # noqa: BLE001 -- a failed count must not hide the presence lines
            count_failure = f" (the count failed: {exc})"
    print(f"  feedback directory:  {feedback_dir.as_posix()}")
    print(f"  exists:               {'yes' if exists else 'no'}")
    print(f"  {_QUEUED_LABEL} {'not checked' + count_failure if queued is None else queued}")
    print()
    if exists:
        print(f"Feedback directory: {feedback_dir.as_posix()} — present.")
        if queued:
            print(f"  {_REMEDY_QUEUED}")
        return
    print("  ! feedback directory is absent — the first draft written there will fail.")
    print("      action: create it with /planwise doctor --create-feedback-dir,")
    print("              or run /planwise init / /planwise upgrade (both create it)")


# --------------------------------------------------------------------------
# Step 7: capture self-containment
# --------------------------------------------------------------------------

def _normal(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _inside(token: str, root: str) -> bool:
    """True when `token` is the project root or sits under it. A Git-Bash drive
    path (`/c/Users/x`) is also compared in its `C:/Users/x` form."""
    forms = [token]
    drive = _GIT_BASH_DRIVE_RE.match(token)
    if drive:
        forms.append(f"{drive.group(1).upper()}:/{token[3:]}")
    base = _normal(root)
    return any(_normal(form) == base or _normal(form).startswith(base + os.sep) for form in forms)


def _body(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1)


def _outside_pointer(body: str, project_root: str) -> "str | None":
    """The first external or transient reference in `body`, or None. An
    absolute path that resolves inside the project root is not external."""
    for match in _PATH_TOKEN_RE.finditer(body):
        token = match.group(0).rstrip(".,;:)]}")
        if not _inside(token, project_root):
            return token
    transient = _TRANSIENT_RE.search(body)
    return transient.group(0) if transient else None


def _step_7(config: dict) -> None:
    root = Path(config["_planwise_root"])
    project_root = str(config["_project_root"])
    files = []
    backlog_dir = Path(config["_backlog_dir"])
    if backlog_dir.is_dir():
        files += list(backlog_dir.glob("BB-*.md")) + list(backlog_dir.glob("BLI-*.md"))
    if config.get("_lessons_dir") is not None and Path(config["_lessons_dir"]).is_dir():
        files += list(Path(config["_lessons_dir"]).glob("LL-*.md"))
    findings = []
    for path in sorted(files):
        body = _body(path.read_text(encoding="utf-8", errors="replace"))
        if "```" in body:
            continue
        pointer = _outside_pointer(body, project_root)
        if pointer:
            findings.append((_display(path, root), pointer))
    if not findings:
        print("Capture self-containment: all scanned captures inline their substance.")
        return
    print("Capture self-containment (advisory):")
    for rel, pointer in findings:
        print(f"  ~ {rel}")
        print(f"      pointer:  {pointer}")
        print("      risk:     substance may live only at that pointer — capture could be")
        print("                non-executable if it vanishes")
        print("      remedy:   inline the block/spec/evidence the item depends on")
        print('                (durability test: "executable from this file alone if the origin vanished?")')


# --------------------------------------------------------------------------
# Step 8: bookkeeping index read-gate
# --------------------------------------------------------------------------

def _generated_files(directories, naming) -> list:
    found = set()
    for directory in directories:
        if Path(directory).is_dir():
            found.update(p for p in Path(directory).iterdir() if p.is_file() and is_generated_index_file(p.name, naming))
    return sorted(found)


def _existing_parts(directory: Path, naming) -> list:
    """The `-Part-NN` continuations (NN >= 2) of one changelog family, in order."""
    from migrate_lessons_support import changelog_part_filename

    sample = Path(changelog_part_filename(naming, 2))
    part_re = re.compile(rf"^{re.escape(sample.stem[: -len('-Part-02')])}-Part-(\d{{2,}}){re.escape(sample.suffix)}$")
    found = []
    if directory.is_dir():
        for path in directory.iterdir():
            match = part_re.match(path.name)
            if match and int(match.group(1)) >= 2 and path.is_file():
                found.append((int(match.group(1)), path))
    return [path for _k, path in sorted(found)]


def _changelog_family(lessons_dir: Path, naming) -> list:
    """The lessons changelog main file, its archive part and every `-Part-NN`
    sibling of either. The archive year is read off the one file on disk."""
    import lessons_changelog as lc
    from migrate_lessons_support import _archive_naming

    changelog_name = _changelog_filename(naming)
    files = [lessons_dir / changelog_name] + _existing_parts(lessons_dir, naming)
    archive = lc._existing_archive_main(lessons_dir, lc._archive_base(naming, changelog_name))
    if archive is not None:
        match = lc._ARCHIVE_YEAR_RE.search(archive.stem)
        files.append(archive)
        if match:
            files += _existing_parts(lessons_dir, _archive_naming(naming, changelog_name, match.group(1)))
    return files


def _lessons_files(config: dict) -> list:
    from lessons_index_render import _promotion_log_filename
    from migrate_lessons_support import century_log_filenames

    lessons_dir = Path(config["_lessons_dir"])
    naming = _index_naming(Path(config["_lessons_index"]))
    files = _generated_files([lessons_dir, lessons_dir / "Archive"], naming)
    files += _changelog_family(lessons_dir, naming)
    files.append(lessons_dir / _promotion_log_filename(naming))
    files += [lessons_dir / name for name in century_log_filenames(naming)]
    return sorted(set(files))


def _known_condition(path: Path) -> str:
    head = "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:20])
    match = _KNOWN_CONDITION_RE.search(head)
    return f"Known condition: {match.group(1)}" if match else _NO_NOTE


def _display(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def _classify(path: Path, root: Path) -> dict:
    """`classify_file` with no model and no thresholds, plus the path to print."""
    return dict(classify_file(str(path), model=None), path=path, rel=_display(path, root))


def _index_row(label: str, path: Path, root: Path) -> "tuple[str, dict | None]":
    if not path.is_file():
        return f"  {label}{_display(path, root)} — not found", None
    info = _classify(path, root)
    return f"  {label}{info['rel']} — {info['level']} ({info['bytes']} B / ~{info['tokens']} tok, reason={info['reason']})", info


def _step_8(config: dict) -> None:
    root = Path(config["_planwise_root"])
    naming = _index_naming(Path(config["_index_path"]))
    backlog = _generated_files([Path(config["_backlog_dir"]), Path(config["_archive_dir"])], naming)
    has_lessons = config.get("_lessons_dir") is not None
    lessons = [p for p in _lessons_files(config) if p.is_file()] if has_lessons else []
    rows = [_index_row("plans:    ", Path(config["_plans_index"]), root)]
    if has_lessons:
        from lessons_index_companion import COMPANION_FILENAME

        rows.append(_index_row("companion: ", Path(config["_lessons_dir"]) / COMPANION_FILENAME, root))
    infos = [info for _, info in rows if info is not None]
    infos += [_classify(path, root) for path in backlog + lessons]
    print(f"  backlog:  {len(backlog)} file(s) scanned (hub + overflow + shards)")
    if has_lessons:
        print(f"  lessons:  {len(lessons)} file(s) scanned (hub + overflow + shards + changelog + promotion log)")
    else:
        print("  lessons:  skipped — project.lessons_dir is absent")
    for line, _ in rows:
        print(line)
    flagged = [i for i in infos if i["level"] != "Green"]
    for info in sorted(flagged, key=lambda i: i["rel"]):
        print()
        print(f"  [{info['level']} / reason={info['reason']}] {info['rel']}")
        print(f"      size: {info['bytes']} B / ~{info['tokens']} tok / {info['lines']} lines")
        print("      remedy: paged read (offset/limit/Grep); refactor + backlog item if this")
        print("              index is a core/edited dependency of the current work")
        print(f"      {_known_condition(info['path'])}")
    if not flagged:
        print()
        print(f"Bookkeeping indexes: all Green — {len(infos)} file(s) scanned.")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def run_probes(cfg) -> None:
    """Run the four probes in order. Read-only, and never raises.

    Each probe row carries the lines it prints after its failure line, so a
    reader of the output still finds a line that probe always prints."""
    config, reason = _load_project_config(cfg)
    probes = (
        ("Feedback capability probe", _FEEDBACK_BANNER, _stage_16, ()),
        ("Feedback directory presence check", _FEEDBACK_DIR_BANNER, _stage_17, (f"  {_QUEUED_LABEL} not checked",)),
        ("Capture self-containment scan", None, _step_7, ()),
        ("Bookkeeping index read-gate scan", _READ_GATE_BANNER, _step_8, ()),
    )
    for name, banner, probe, failure_lines in probes:
        print()
        if banner:
            print(banner)
            print()
        try:
            if config is None:
                raise RuntimeError(f"config.yaml could not be loaded ({reason})")
            probe(config)
        except Exception as exc:  # noqa: BLE001 -- a probe must never change doctor's exit status
            print(f"{name}: the check failed: {exc}")
            for line in failure_lines:
                print(line)
