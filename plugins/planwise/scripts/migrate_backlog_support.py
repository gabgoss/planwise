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

SHINGLE_N = 5
DEFAULT_HIGH = 0.75
DEFAULT_LOW = 0.35
LEGACY_HEADING = "## Backlog Items"
NOTES_HEADING = "## Migration Notes"
MIGRATED_HEADER = ["ID", "Title", "Priority", "Status", "Domain", "Created", "Blocks", "Score", "File"]
COLUMN_ROLES = {"id": "id", "feature": "feature", "title": "feature", "priority": "priority", "status": "status",
                "abbrev": "abbrev", "domain": "abbrev", "created": "created", "blocks": "blocks",
                "score": "score", "files": "file", "file": "file"}  # legacy column name -> role
REQUIRED_ROLES = ("id", "feature", "file")
COMPARED_ROLES = ("priority", "status", "abbrev", "created", "blocks")  # rendered from frontmatter
FOOTER_RE = re.compile(rb"(?m)^\*Last Updated:[^\r\n]*")
FOOTER_TEXT_RE = re.compile(r"(?m)^\*Last Updated:[^\r\n]*")
POINTER_RE = re.compile(r"^\*Last Updated: \d{4}-\d{2}-\d{2} — moved to \[([^\]]+)\]\(([^)]+)\)\*$")
PREFIX = b"*Last Updated:"
MARKER = b"Prior entry:"
SEP_RE = re.compile(r"^\|[-\s|:]+\|$")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.*?)\*\*")
_CODE_RE = re.compile(r"`([^`]*)`")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")
_DIGITS_RE = re.compile(r"\d+")
# A Blocks cell may hold only ids and separators, a dash, or "none". Other
# text in it is prose the regeneration would drop.
_BLOCKS_TEXT_RE = re.compile(r"(\d+([\s,;]+\d+)*)?|[-–—]|none", re.IGNORECASE)
_FILES_GLUE_RE = re.compile(r"[\s,;]+|<br\s*/?>", re.IGNORECASE)
_EXACT_DROP = str.maketrans("", "", "*_`")
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
            if i + 1 < len(lines) and SEP_RE.match(lines[i + 1].strip()):
                return row_cells(lines[i]), i
            return None, None
    return None, None


def iter_rows(lines: list, header_idx: int) -> list:
    """Every line of the table body, with its cells. Nothing is skipped."""
    end = header_idx + 2
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    return [(i, row_cells(lines[i])) for i in range(header_idx + 2, end)]


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


# --- row versus frontmatter ---

def _strip_markdown(text: str) -> str:
    text = _LINK_RE.sub(r"\1", text)
    text = _BOLD_RE.sub(r"\1", text)
    return _CODE_RE.sub(r"\1", text)


def plain(cell: str) -> str:
    return _WS_RE.sub(" ", _strip_markdown(cell)).strip()


def ids_in(cell: str) -> list:
    return sorted({d.zfill(3) for d in _DIGITS_RE.findall(plain(cell))})


def blocks_text_ok(cell: str) -> bool:
    return bool(_BLOCKS_TEXT_RE.fullmatch(plain(cell)))


def files_links(cell: str):
    """Return (links as (text, href) pairs, any text outside the links)."""
    return _LINK_RE.findall(cell), _FILES_GLUE_RE.sub("", _LINK_RE.sub("", cell))


def resolve_item_file(href: str, backlog_dir: Path, archive_dir: Path, index_dir: Path):
    name = Path(href.strip()).name
    for candidate in (index_dir / href.strip(), backlog_dir / href.strip(), backlog_dir / name, archive_dir / name):
        if candidate.is_file():
            return candidate.resolve()
    return None


def link_unit(text: str, href: str, index_dir: Path, item_dir: Path):
    """Return (the link rewritten relative to the item file, the target's file name)."""
    rel = Path(os.path.relpath(index_dir / href.strip(), item_dir)).as_posix()
    return f"[{text}]({rel})", Path(href.strip()).name


def link_listed(name: str, haystack: str) -> bool:
    return f"({name})" in haystack or f"/{name})" in haystack


def compare_row(cells: list, roles: dict, fields: dict) -> list:
    """Return one message per cell that disagrees with frontmatter."""
    out = []
    id_cell = cells[roles["id"]]
    if ids_in(id_cell) != [fields["id"]]:
        out.append(f"id cell {id_cell!r} but {fields['_path'].name} has frontmatter id {fields['id']!r}")
    for role in COMPARED_ROLES:
        if role not in roles:
            continue
        cell = cells[roles[role]]
        if role == "blocks":
            if not blocks_text_ok(cell):
                out.append(f"id {fields['id']}: Blocks cell {cell!r} carries text other than ids")
                continue
            row_value, fm_value = ids_in(cell), sorted(fields["blocks"])
        else:
            row_value, fm_value = plain(cell), fields[role]
        if row_value != fm_value:
            out.append(f"id {fields['id']}: {role.capitalize()} cell {row_value!r} but frontmatter {fm_value!r}")
    return out


# --- changelog footer (byte-exact) ---

def extract_changelog(data: bytes) -> dict:
    m = FOOTER_RE.search(data)
    footer = data[m.start():m.end()]
    segments = footer.split(MARKER)
    segments[0] = segments[0][len(PREFIX):]
    return {
        "segments": segments, "source_bytes": len(footer),
        "entry_content_bytes": sum(len(s) for s in segments),
        "marker_bytes_discarded": footer.count(MARKER) * len(MARKER), "pointer_bytes_retained": len(PREFIX),
    }


def unaccounted(segments: list, changelog: str) -> int:
    """Extracted entry bytes minus the bytes found present in `changelog`."""
    return sum(len(s) for s in segments if s.decode("utf-8") not in changelog)


def changelog_text(segments: list, index_name: str, nl: str) -> str:
    parts = [f"[← {index_name}]({index_name}){nl}{nl}"]
    for i, seg in enumerate(segments, start=1):
        parts += [f"## Entry {i}{nl}{nl}", seg.decode("utf-8"), nl + nl]
    return "".join(parts)


def newline_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


# --- dedup: is a unit of row prose already in the item file? ---

def normalize(text: str) -> str:
    """Loose form for similarity scoring only: no case, no punctuation."""
    text = _PUNCT_RE.sub(" ", _strip_markdown(text).lower())
    return _WS_RE.sub(" ", text).strip()


def exact_key(text: str) -> str:
    """Strict form for the ALREADY-PRESENT test: link text kept, emphasis
    and code markers removed, case folded, whitespace collapsed. Punctuation,
    words and numbers stay."""
    return _WS_RE.sub(" ", _LINK_RE.sub(r"\1", text).translate(_EXACT_DROP).casefold()).strip()


def contains_exact(needle: str, haystack: str) -> bool:
    """True when `needle` occurs in `haystack` with no word character touching either end."""
    start = haystack.find(needle)
    while start != -1:
        end = start + len(needle)
        if (start == 0 or not haystack[start - 1].isalnum()) and (end == len(haystack) or not haystack[end].isalnum()):
            return True
        start = haystack.find(needle, start + 1)
    return False


def split_units(text: str) -> list:
    text = text.strip()
    return [p.strip() for p in _SENT_SPLIT_RE.split(text) if p.strip()] if text else []


def row_units(cell: str, title: str) -> list:
    """Every sentence of the Feature cell except one that is the frontmatter title."""
    def key(text):
        return exact_key(text).rstrip(" .!?")
    return [u.replace("\\|", "|") for u in split_units(cell) if key(u) != key(title)]


def shingles(text: str, n: int = SHINGLE_N) -> set:
    return {text[i:i + n] for i in range(len(text) - n + 1)} if len(text) >= n else ({text} if text else set())


def body_index(text: str) -> dict:
    """Loose lines with their shingles, plus strict paragraphs: runs of
    non-blank lines joined, so a hard-wrapped sentence is one string."""
    raw = text.replace("\r\n", "\n").split("\n")
    paras, current = [], []
    for line in raw:
        key = exact_key(line)
        if key:
            current.append(key)
        elif current:
            paras.append(" ".join(current))
            current = []
    if current:
        paras.append(" ".join(current))
    return {"lines": [(n, shingles(n)) for n in (normalize(ln) for ln in raw)], "paras": paras}


def extend_index(index: dict, unit: str) -> None:
    """Add a planned append, so later units dedup against it too."""
    norm = normalize(unit)
    index["lines"].append((norm, shingles(norm)))
    index["paras"].append(exact_key(unit))


def score_unit(unit: str, index: dict, n: int = SHINGLE_N):
    """Return (exact, best single-line similarity, best two-line-window similarity).
    `exact` is True only when the whole unit's strict form occurs in one paragraph."""
    key = exact_key(unit)
    if key and any(contains_exact(key, para) for para in index["paras"]):
        return True, 1.0, 1.0
    unit_sh = shingles(normalize(unit), n)
    if not unit_sh:
        return False, 0.0, 0.0
    best, window, prev = 0.0, 0.0, set()
    for _norm_line, line_sh in index["lines"]:
        best = max(best, len(unit_sh & line_sh) / len(unit_sh))
        window = max(window, len(unit_sh & (line_sh | prev)) / len(unit_sh))
        prev = line_sh
    return False, best, window


def classify_unit(exact: bool, score: float, window: float, high: float, low: float) -> str:
    """Only an exact match is ALREADY-PRESENT. Similarity alone never is:
    at or below `low` it is MISSING, above it AMBIGUOUS. `high` only labels
    an AMBIGUOUS unit as a near-duplicate in the refusal message."""
    if exact:
        return "ALREADY-PRESENT"
    return "MISSING" if max(score, window) <= low else "AMBIGUOUS"


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
