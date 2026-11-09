"""Idempotent `.gitignore` line helper.

Init and upgrade both call `ensure_line` to keep model-written feedback drafts
out of a consumer's commits. The helper only ever appends: it never removes,
reorders, or rewrites an existing line, and it never rewrites existing bytes.
An existing file is opened in append mode, so its permissions are kept, a
symlink is followed, and nothing can truncate it. A line the user negated
(`!<line>`) counts as an opt-out and is never re-added.
"""

from pathlib import Path, PureWindowsPath

# Model drafts are `YYYY-MM-DD-draft-<kind>-<slug>.md`: `-draft-` sits directly
# after the date. A user-owned draft is `YYYY-MM-DD-<kind>-<slug>.md`, so a slug
# that merely contains "draft" must not match.
MODEL_DRAFT_PATTERN = "{planwise_root}/{feedback_dir}/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-draft-*.md"

# Characters that carry a gitignore meaning inside a pattern.
_GLOB_CHARS = frozenset("[]*?")


def _relative_segment(value: str, label: str) -> str:
    """Return `value` as a forward-slash relative path, or raise ValueError.

    A gitignore pattern is relative to the repository root and is matched
    literally only when it has no glob characters, so an absolute path, a `..`
    component or a glob character cannot be expressed as this entry.
    """
    text = str(value).replace("\\", "/")
    if not text.strip("/"):
        raise ValueError(f"{label} is empty")
    if text.startswith("/") or PureWindowsPath(str(value)).drive:
        raise ValueError(f"{label} is an absolute path: {value}")
    parts = [part for part in text.split("/") if part]
    if ".." in parts:
        raise ValueError(f"{label} leaves the project with '..': {value}")
    if _GLOB_CHARS & set(text):
        raise ValueError(f"{label} contains a gitignore glob character: {value}")
    return "/".join(parts)


def model_draft_line(planwise_root: str, feedback_dir: str) -> str:
    """Render the `.gitignore` line for model-written drafts, with forward slashes.

    Raises ValueError when either path cannot be expressed as a literal,
    repository-relative gitignore pattern.
    """
    root = _relative_segment(planwise_root, "planwise_root")
    if root[0] in "!#":
        raise ValueError(f"planwise_root starts with a gitignore control character: {planwise_root}")
    sub = _relative_segment(feedback_dir, "feedback_dir")
    return MODEL_DRAFT_PATTERN.format(planwise_root=root, feedback_dir=sub)


def _dominant_eol(data: bytes) -> bytes:
    """Return b"\\r\\n" when CRLF endings outnumber bare LF endings, else b"\\n"."""
    crlf = data.count(b"\r\n")
    bare_lf = data.count(b"\n") - crlf
    return b"\r\n" if crlf > bare_lf else b"\n"


def line_state(data: bytes, line: str) -> str:
    """Classify `data` against `line` as "present", "negated" or "absent".

    The one predicate behind `ensure_line` and the read-only `read_state`, so
    the writer and any checker agree on what counts as present. A line matches
    ignoring trailing whitespace. When the data holds both the line and its
    `!<line>` negation, the later one decides, as it does in git.
    """
    wanted = line.rstrip().encode("utf-8")
    negated = b"!" + wanted
    state = "absent"
    for existing in data.split(b"\n"):
        stripped = existing.rstrip()
        if stripped == wanted:
            state = "present"
        elif stripped == negated:
            state = "negated"
    return state


def read_state(gitignore_path: Path, line: str) -> str:
    """Return `line_state` for the file at `gitignore_path` and write nothing.

    A missing file reads as "absent", the state `ensure_line` would create it from.
    """
    if not gitignore_path.exists():
        return "absent"
    return line_state(gitignore_path.read_bytes(), line)


def ensure_line(gitignore_path: Path, line: str) -> bool:
    """Make sure `line` is present in the file at `gitignore_path`.

    Returns True when the file was written (created, or the line appended) and
    False when nothing was written: an identical line (ignoring trailing
    whitespace) already exists, or the user negated it with `!<line>`.
    """
    wanted = line.rstrip().encode("utf-8")
    if not gitignore_path.exists():
        with open(gitignore_path, "wb") as handle:
            handle.write(wanted + b"\n")
        return True

    data = gitignore_path.read_bytes()
    if line_state(data, line) != "absent":
        return False

    eol = _dominant_eol(data)
    prefix = b"" if (not data or data.endswith(b"\n")) else eol
    with open(gitignore_path, "ab") as handle:
        handle.write(prefix + wanted + eol)
    return True
