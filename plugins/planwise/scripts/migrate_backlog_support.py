#!/usr/bin/env python3
"""Helpers for `migrate_backlog_index.py`: recognise the hand-authored index,
compare rows with frontmatter, extract the changelog footer, classify prose
against an item body, and stage writes. Only `replace_all` changes a target."""
import os
import re
import shutil
import tempfile
from pathlib import Path

from markdown_parser import split_row_raw

TITLE_BUDGET = 120
SHINGLE_N = 5
DEFAULT_HIGH = 0.75
DEFAULT_LOW = 0.35
LEGACY_HEADING = "## Backlog Items"
ALLOWED_SECTION_PREFIXES = ("## Shards", "## Dependencies")
SOFT_MARKER = "**Soft dependencies**"
NOTES_HEADING = "## Migration Notes"
METADATA_PREFIXES = ("**Purpose:**", "**Last Updated:**")  # preamble lines with no item content
MIGRATED_HEADER = ["ID", "Title", "Priority", "Status", "Domain", "Created", "Blocks", "Score", "File"]
COLUMN_ROLES = {"id": "id", "feature": "feature", "title": "feature", "priority": "priority", "status": "status",
                "abbrev": "abbrev", "domain": "abbrev", "created": "created", "blocks": "blocks",
                "score": "score", "files": "file", "file": "file"}  # legacy column name -> role
REQUIRED_ROLES = ("id", "feature", "file")
COMPARED_ROLES = ("priority", "status", "abbrev", "created", "blocks")  # rendered from frontmatter
FOOTER_RE = re.compile(rb"(?m)^\*Last Updated:[^\r\n]*")
FOOTER_TEXT_RE = re.compile(r"(?m)^\*Last Updated:[^\r\n]*")
POINTER_RE = re.compile(r"^\*Last Updated: \d{4}-\d{2}-\d{2} — moved to \[([^\]]+)\]\(([^)]+)\)\*$")
DEP_HEADING_RE = re.compile(r"(?m)^## Dependencies[^\r\n]*")
PREFIX = b"*Last Updated:"
MARKER = b"Prior entry:"
_SEP_RE = re.compile(r"^\|[-\s|:]+\|$")
_LINK_HREF_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_LINK_TEXT_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BOLD_RE = re.compile(r"\*\*(.*?)\*\*")
_CODE_RE = re.compile(r"`([^`]*)`")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")
_DIGITS_RE = re.compile(r"\d+")
_SENT_SPLIT_RE = re.compile(r"(?:(?<=[.!?])|(?<=[.!?]\*\*)|(?<=[.!?]`))\s+(?=[A-Z0-9`\"'(\[*_-])")

# Module-level aliases so a test can inject a failure into one phase.
_mkstemp = tempfile.mkstemp
_replace = os.replace


# --- table recognition ---

def row_cells(line: str) -> list:
    segs = split_row_raw(line.strip())
    if segs and segs[0] == "":
        segs = segs[1:]
    if segs and segs[-1] == "":
        segs = segs[:-1]
    return [s.strip() for s in segs]


def find_table(lines: list, after_heading: str | None = None):
    """Return (header_cells, header_index) of the first table after `after_heading`, else (None, None)."""
    start = 0
    if after_heading is not None:
        hits = [i for i, raw in enumerate(lines) if raw.strip() == after_heading]
        if not hits:
            return None, None
        start = hits[0] + 1
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if after_heading is not None and s.startswith("## "):
            return None, None
        if s.startswith("|"):
            if i + 1 < len(lines) and _SEP_RE.match(lines[i + 1].strip()):
                return row_cells(lines[i]), i
            return None, None
    return None, None


def table_end(lines: list, header_idx: int) -> int:
    i = header_idx + 2
    while i < len(lines) and lines[i].strip().startswith("|"):
        i += 1
    return i


def iter_rows(lines: list, header_idx: int) -> list:
    rows = []
    for i in range(header_idx + 2, table_end(lines, header_idx)):
        cells = row_cells(lines[i])
        if cells and cells[0] and not set(cells[0]) <= {"-"}:
            rows.append((i, cells))
    return rows


def column_map(header: list):
    """Map each role to its column index. Returns (roles, None) or (None, reason)."""
    roles = {}
    for i, name in enumerate(header):
        role = COLUMN_ROLES.get(name.strip().lower())
        if role is None:
            return None, f"unrecognised column {name!r} in the '{LEGACY_HEADING}' table"
        if role in roles:
            return None, f"column {name!r} repeats the role of another column"
        roles[role] = i
    missing = [r for r in REQUIRED_ROLES if r not in roles]
    if missing:
        return None, f"'{LEGACY_HEADING}' table lacks required column role(s): {', '.join(missing)}"
    return roles, None


def classify_shape(text: str):
    """Return (shape, detail). `shape` is "legacy", "migrated" or
    "unrecognized". `detail` is (header_idx, roles) for "legacy", else a reason."""
    lines = text.split("\n")
    if not any(raw.strip() == LEGACY_HEADING for raw in lines):
        header, _ = find_table(lines)
        if header == MIGRATED_HEADER:
            return "migrated", None
        if header is None:
            return "unrecognized", "no markdown table found in the index"
        return "unrecognized", f"table header {header!r} matches neither the legacy nor the generated shape"
    header, header_idx = find_table(lines, LEGACY_HEADING)
    if header is None:
        return "unrecognized", f"'{LEGACY_HEADING}' heading present but no table follows it"
    roles, err = column_map(header)
    if err:
        return "unrecognized", err
    footers = FOOTER_TEXT_RE.findall(text)
    if len(footers) != 1:
        return "unrecognized", f"found {len(footers)} '*Last Updated:' footer line(s); expected exactly 1"
    return "legacy", (header_idx, roles)


def unrecognised_content(text: str, header_idx: int) -> list:
    """Name every line regeneration would drop that this tool does not move:
    preamble prose (other than one `# ` title and metadata lines), prose
    between the items heading and its table, an unknown `##` section, and
    text after the table other than the footer."""
    lines = text.split("\n")
    problems, titled = [], False
    first_h2 = next((i for i, raw in enumerate(lines) if raw.strip().startswith("## ")), len(lines))
    for i in range(first_h2):
        s = lines[i].strip()
        if s.startswith("# ") and not titled:
            titled = True
        elif s and s != "---" and not s.startswith(METADATA_PREFIXES):
            problems.append(f"line {i + 1}: preamble text {s[:60]!r}")
    heading_idx = next(i for i, raw in enumerate(lines) if raw.strip() == LEGACY_HEADING)
    problems += [f"line {i + 1}: text between '{LEGACY_HEADING}' and its table, {lines[i].strip()[:60]!r}"
                 for i in range(heading_idx + 1, header_idx) if lines[i].strip()]
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s.startswith("## ") and s != LEGACY_HEADING and not s.startswith(ALLOWED_SECTION_PREFIXES):
            problems.append(f"line {i + 1}: section {s!r}")
    for i in range(table_end(lines, header_idx), len(lines)):
        s = lines[i].strip()
        if s.startswith("## "):
            break
        if s and s != "---" and not s.startswith("*Last Updated:"):
            problems.append(f"line {i + 1}: text after the table, {s[:60]!r}")
    return problems


def has_soft_dependencies(text: str) -> bool:
    """True when a `## Dependencies` block still carries free-text soft prose.
    This tool has no extraction path for it, so the caller refuses."""
    m = DEP_HEADING_RE.search(text)
    if m is None:
        return False
    footer_m = FOOTER_TEXT_RE.search(text, m.end())
    end = footer_m.start() if footer_m else len(text)
    return SOFT_MARKER in text[m.start():end]


# --- row versus frontmatter ---

def _strip_markdown(text: str) -> str:
    text = _LINK_TEXT_RE.sub(r"\1", text)
    text = _BOLD_RE.sub(r"\1", text)
    return _CODE_RE.sub(r"\1", text)


def _plain(cell: str) -> str:
    return _WS_RE.sub(" ", _strip_markdown(cell)).strip()


def _ids(text: str) -> list:
    return sorted({d.zfill(3) for d in _DIGITS_RE.findall(text)})


def resolve_item_file(files_cell: str, backlog_dir: Path, archive_dir: Path, index_dir: Path):
    m = _LINK_HREF_RE.search(files_cell)
    if not m:
        return None
    href = m.group(1).strip()
    name = Path(href).name
    for candidate in (index_dir / href, backlog_dir / href, backlog_dir / name, archive_dir / name):
        if candidate.is_file():
            return candidate.resolve()
    return None


def compare_row(cells: list, roles: dict, fields: dict) -> list:
    """Return one message per cell that disagrees with frontmatter."""
    out = []
    id_cell = cells[roles["id"]]
    if _ids(_plain(id_cell)) != [fields["id"]]:
        out.append(f"id cell {id_cell!r} but {fields['_path'].name} has frontmatter id {fields['id']!r}")
    for role in COMPARED_ROLES:
        if role not in roles:
            continue
        cell = cells[roles[role]]
        if role == "blocks":
            row_value, fm_value = _ids(_plain(cell)), sorted(fields["blocks"])
        else:
            row_value, fm_value = _plain(cell), fields[role]
        if row_value != fm_value:
            out.append(f"id {fields['id']}: {role.capitalize()} cell {row_value!r} but frontmatter {fm_value!r}")
    return out


# --- changelog footer (byte-exact) ---

def extract_changelog(data: bytes) -> dict:
    m = FOOTER_RE.search(data)
    footer = data[m.start():m.end()]
    segments = footer.split(MARKER)
    segments[0] = segments[0][len(PREFIX):]
    content = sum(len(s) for s in segments)
    markers = footer.count(MARKER) * len(MARKER)
    return {
        "segments": segments, "source_bytes": len(footer), "entry_content_bytes": content,
        "marker_bytes_discarded": markers, "pointer_bytes_retained": len(PREFIX),
        "unaccounted": len(footer) - content - markers - len(PREFIX),
    }


def changelog_text(segments: list, index_name: str, nl: str) -> str:
    parts = [f"[← {index_name}]({index_name}){nl}{nl}"]
    for i, seg in enumerate(segments, start=1):
        parts += [f"## Entry {i}{nl}{nl}", seg.decode("utf-8"), nl + nl]
    return "".join(parts)


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


# --- dedup: is a unit of row prose already in the item file? ---

def normalize(text: str) -> str:
    text = _PUNCT_RE.sub(" ", _strip_markdown(text).lower())
    return _WS_RE.sub(" ", text).strip()


def candidate_span(cell: str, budget: int = TITLE_BUDGET):
    if len(cell) <= budget:
        return len(cell), ""
    starts = [m.end() for m in _SENT_SPLIT_RE.finditer(cell) if m.end() <= budget]
    start = starts[-1] if starts else 0
    return start, cell[start:]


def split_units(candidate: str) -> list:
    candidate = candidate.strip()
    return [p.strip() for p in _SENT_SPLIT_RE.split(candidate) if p.strip()] if candidate else []


def row_units(cell: str, title: str) -> list:
    """Every unit of Feature-cell prose regeneration would drop. The title
    head counts too, unless it matches the frontmatter title."""
    start, rest = candidate_span(cell)
    head = cell[:start]
    units = [] if normalize(head) in ("", normalize(title)) else split_units(head)
    return [u.replace("\\|", "|") for u in units + split_units(rest)]


def shingles(text: str, n: int = SHINGLE_N) -> set:
    return {text[i:i + n] for i in range(len(text) - n + 1)} if len(text) >= n else ({text} if text else set())


def body_index(text: str) -> dict:
    """Normalized lines with their shingles, plus paragraphs: runs of
    non-blank lines joined, so a hard-wrapped sentence is one string."""
    norm_lines = [normalize(ln) for ln in text.replace("\r\n", "\n").split("\n")]
    paras, current = [], []
    for norm in norm_lines:
        if norm:
            current.append(norm)
        elif current:
            paras.append(" ".join(current))
            current = []
    if current:
        paras.append(" ".join(current))
    return {"lines": [(n, shingles(n)) for n in norm_lines], "paras": paras}


def extend_index(index: dict, unit: str) -> None:
    """Add a planned append, so later units dedup against it too."""
    norm = normalize(unit)
    index["lines"].append((norm, shingles(norm)))
    index["paras"].append(norm)


def score_unit(unit: str, index: dict, n: int = SHINGLE_N):
    """Return (best single-line containment, best two-line-window containment).
    A whole-word match inside one paragraph scores 1.0 on both."""
    norm = normalize(unit)
    unit_sh = shingles(norm, n)
    if not unit_sh:
        return 0.0, 0.0
    if any(f" {norm} " in f" {para} " for para in index["paras"]):
        return 1.0, 1.0
    best, window, prev = 0.0, 0.0, set()
    for _norm_line, line_sh in index["lines"]:
        best = max(best, len(unit_sh & line_sh) / len(unit_sh))
        window = max(window, len(unit_sh & (line_sh | prev)) / len(unit_sh))
        prev = line_sh
    return best, window


def classify_unit(score: float, window: float, high: float, low: float) -> str:
    if max(score, window) >= high:
        return "ALREADY-PRESENT"
    return "MISSING" if window <= low else "AMBIGUOUS"


def append_notes(body: str, units: list, nl: str) -> str:
    h2 = [ln.strip() for ln in body.splitlines() if ln.startswith("## ")]
    heading = "" if h2 and h2[-1] == NOTES_HEADING else f"{NOTES_HEADING}{nl}{nl}"
    return body.rstrip("\r\n") + nl + nl + heading + (nl + nl).join(units) + nl


def prior_notes(body: str) -> str:
    """The text of the last `## Migration Notes` section this tool wrote, or ""."""
    lines = body.replace("\r\n", "\n").split("\n")
    starts = [i for i, ln in enumerate(lines) if ln.strip() == NOTES_HEADING]
    if not starts:
        return ""
    tail = lines[starts[-1] + 1:]
    end = next((i for i, ln in enumerate(tail) if ln.startswith("## ")), len(tail))
    return "\n".join(tail[:end])


# --- staging and replacement ---

class ReplaceError(Exception):
    """A replace failed part-way. `done` lists the paths already replaced."""
    def __init__(self, path: Path, done: list, cause: Exception):
        super().__init__(f"{path}: {cause}")
        self.path, self.done, self.cause = path, done, cause


def discard(staged: list) -> None:
    for tmp, _target in staged:
        try:
            tmp.unlink()
        except OSError:
            pass


def default_mode() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def stage_all(outputs: list) -> list:
    """Write each (path, text) to a temp file beside the path, carrying the target's
    permission mode (a new file gets the umask default, never mkstemp's 0600).
    On any failure, remove every temp and re-raise. No target changes."""
    staged = []
    try:
        for path, text in outputs:
            fd, tmp = _mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".staged")
            staged.append((Path(tmp), path))
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            if path.exists():
                shutil.copymode(path, tmp)
            else:
                os.chmod(tmp, default_mode())
    except BaseException:
        discard(staged)
        raise
    return staged


def replace_all(staged: list) -> list:
    done = []
    for i, (tmp, path) in enumerate(staged):
        try:
            _replace(tmp, path)
        except OSError as exc:
            discard(staged[i:])
            raise ReplaceError(path, done, exc) from exc
        done.append(path)
    return done
