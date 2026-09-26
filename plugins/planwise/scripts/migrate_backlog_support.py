#!/usr/bin/env python3
"""Helpers for `migrate_backlog_index.py`: recognise the hand-authored index,
compare rows with frontmatter, extract the changelog footer, classify prose
against an item body, and stage writes. Only `replace_all` changes a target."""
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from backlog_index_budget import _measure
from backlog_index_schema import _changelog_filename, _index_naming
from markdown_parser import split_row_raw
from read_limits import READ_BYTE_WARN, READ_FILE_BYTE_CAP, READ_PAGE_CAP_TOKENS, READ_TOKEN_WARN
from reconcile_common import read_text_preserving_newlines as read_text


class Refusal(Exception):
    """A condition that stops the run before any write (exit 2)."""


SHINGLE_N = 5
DEFAULT_HIGH = 0.75
DEFAULT_LOW = 0.35
LEGACY_HEADING = "## Backlog Items"
NOTES_HEADING = "## Migration Notes"
NOTES_HEADING_DEPS = "## Dependency Notes (migrated from the backlog index)"
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


def refuse_unless_generated(index_path: Path, read_text) -> tuple[str, str] | None:
    """Classify the on-disk index at `index_path` via `classify_shape`.
    Returns `None` when the file is absent, classifies `migrated`, or is a
    `legacy`-shaped table whose single footer is already a migration
    pointer (`migrate_backlog_index.py` has already extracted it, so only
    the table itself is left in the old shape -- the same signal
    `_changelog_state` already keys on). Otherwise `(shape, detail)`,
    naming the shape a caller should refuse writing over or reading drift
    from. `read_text` is the caller's own text-reading function, kept
    injectable rather than imported here, so this stays pure and prints
    nothing."""
    if not index_path.exists():
        return None
    text = read_text(index_path)
    shape, detail = classify_shape(text)
    if shape == "migrated":
        return None
    if shape == "legacy":
        footer = FOOTER_TEXT_RE.search(text)
        if footer and POINTER_RE.match(footer.group(0)):
            return None
    return shape, detail


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


def row_diffs(cells: list, roles: dict, fields: dict) -> list:
    """Return one dict per cell that disagrees with frontmatter: `key`, the
    `row` value (None when no frontmatter value could carry it), the
    `frontmatter` value, `prose` (the cell holds text other than ids), and
    the `message`."""
    out = []
    id_cell = cells[roles["id"]]
    if ids_in(id_cell) != [fields["id"]]:
        out.append({"key": "id", "row": None, "frontmatter": fields["id"], "prose": False,
                    "message": f"id cell {id_cell!r} but {fields['_path'].name} has frontmatter id {fields['id']!r}"})
    for role in COMPARED_ROLES:
        if role not in roles:
            continue
        cell = cells[roles[role]]
        if role == "blocks":
            if not blocks_text_ok(cell):
                out.append({"key": role, "row": None, "frontmatter": sorted(fields["blocks"]), "prose": True,
                            "message": f"id {fields['id']}: Blocks cell {cell!r} carries text other than ids"})
                continue
            row_value, fm_value = ids_in(cell), sorted(fields["blocks"])
        else:
            row_value, fm_value = plain(cell), fields[role]
        if row_value != fm_value:
            out.append({"key": role, "row": row_value, "frontmatter": fm_value, "prose": False, "message":
                        f"id {fields['id']}: {role.capitalize()} cell {row_value!r} but frontmatter {fm_value!r}"})
    return out


def compare_row(cells: list, roles: dict, fields: dict) -> list:
    """Return one message per cell that disagrees with frontmatter."""
    return [diff["message"] for diff in row_diffs(cells, roles, fields)]


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


def append_notes(body: str, units: list, nl: str, heading_text: str = NOTES_HEADING) -> str:
    """Append `units` under `heading_text`, adding the heading unless it is already the last `## ` section."""
    h2 = [ln.strip() for ln in body.splitlines() if ln.startswith("## ")]
    heading = "" if h2 and h2[-1] == heading_text else f"{heading_text}{nl}{nl}"
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


# --- changelog budget: numbered parts, each under the read-gate warn ---

CONTINUED = " (continued)"
BACKLINK_RE = re.compile(r"^\[← [^\]]*\]\([^)]*\)$")
PARTS_LINE_RE = re.compile(r"^Parts: .*$")
ENTRY_HEADING_RE = re.compile(r"^## Entry (\d+)( \(continued\))?$", re.M)


def changelog_part_filename(naming, k: int) -> str:
    """`{stem}-Part-{kk}{suffix}`, derived from `_changelog_filename`'s own
    result -- never from the hub name directly."""
    stem_path = Path(_changelog_filename(naming))
    return f"{stem_path.stem}-Part-{k:02d}{stem_path.suffix}"


def changelog_part_pattern(naming) -> re.Pattern:
    stem_path = Path(_changelog_filename(naming))
    return re.compile(rf"^{re.escape(stem_path.stem)}-Part-(\d{{2,}}){re.escape(stem_path.suffix)}$")


def changelog_tokens(text: str) -> int:
    """Token estimate for changelog text, via the generator's own budget
    basis. `_measure` expects `\\n`-only text, so CRLF is normalised first."""
    return _measure(text.replace("\r\n", "\n"))[1]


def _changelog_level(num_bytes: int, tokens: int) -> str:
    """OK|WARN|OVER against the same gates `measure_files.py` reports."""
    if tokens >= READ_PAGE_CAP_TOKENS or num_bytes >= READ_FILE_BYTE_CAP:
        return "OVER"
    if tokens >= READ_TOKEN_WARN or num_bytes >= READ_BYTE_WARN:
        return "WARN"
    return "OK"


def _entry_section(label: str, body: str, nl: str) -> str:
    return f"## Entry {label}{nl}{nl}{body}{nl}{nl}"


def _entry_chunks(segments: list, nl: str, budget: int, target: int | None = None) -> list:
    """Split each footer entry into one or more (label, body) chunks. An
    entry whose own section reaches `target` (default `budget`) is split at
    blank-line boundaries into 'N' and 'N (continued)' pieces. A single
    paragraph whose own section alone still exceeds `budget` raises
    `Refusal`, naming the entry and its token count -- a data error this
    tool cannot decide. Each body takes `nl` line endings."""
    target = budget if target is None else target
    chunks = []
    for i, seg in enumerate(segments, start=1):
        body = seg.decode("utf-8").replace("\r\n", "\n").replace("\n", nl)
        if changelog_tokens(_entry_section(str(i), body, nl)) < target:
            chunks.append((str(i), body))
            continue
        paras = body.split(nl + nl)
        pieces, buf = [], []
        for para in paras:
            candidate = buf + [para]
            if buf and changelog_tokens(_entry_section(str(i), (nl + nl).join(candidate), nl)) >= target:
                pieces.append((nl + nl).join(buf))
                buf = [para]
            else:
                buf = candidate
        if buf:
            pieces.append((nl + nl).join(buf))
        for j, piece in enumerate(pieces):
            label = str(i) if j == 0 else f"{i}{CONTINUED}"
            tokens = changelog_tokens(_entry_section(label, piece, nl))
            if tokens >= budget:
                raise Refusal(
                    f"changelog entry {i} has a paragraph of ~{tokens} tokens, over the "
                    f"{budget}-token per-file budget; add a blank line inside it by hand, then re-run")
            chunks.append((label, piece))
    return chunks


def _pack_changelog(rendered: list, budget: int, header1_tokens: int, other_tokens: int) -> list:
    """Greedily pack rendered (label, body, section_text) chunks into parts,
    each part's running total (header + sections) kept under `budget`."""
    parts, current, current_tokens = [], [], header1_tokens
    for _label, _body, text in rendered:
        tok = changelog_tokens(text)
        if current and current_tokens + tok >= budget:
            parts.append(current)
            current, current_tokens = [], other_tokens
        current.append(text)
        current_tokens += tok
    parts.append(current)
    return parts


def split_changelog(segments: list, naming, index_name: str, nl: str, budget: int = READ_TOKEN_WARN) -> list:
    """Pure. Pack `## Entry N` sections greedily, in entry
    order, into numbered parts each under `budget`. Part 1 carries the
    backlink to the index and, when N > 1, a `Parts:` line to parts 2..N;
    every later part backlinks to part 1. When N = 1 the result is
    byte-identical to `changelog_text`. Every chunk is sized against
    `budget` less the larger header, so a part's first chunk fits beside
    its header. A part that still measures over (its header plus one
    paragraph that cannot be split) is refused by `check_parts_budget`,
    which each caller runs. Returns [(filename, text), ...]."""
    part1_name = _changelog_filename(naming)
    part1_bare_header = f"[← {index_name}]({index_name}){nl}{nl}"
    other_header = f"[← {part1_name}]({part1_name}){nl}{nl}"
    other_tokens = changelog_tokens(other_header)
    header1, parts_bodies = part1_bare_header, None
    for _attempt in range(100):
        reserved = changelog_tokens(header1)
        chunks = _entry_chunks(segments, nl, budget, budget - max(reserved, other_tokens))
        rendered = [(label, body, _entry_section(label, body, nl)) for label, body in chunks]
        parts_bodies = _pack_changelog(rendered, budget, reserved, other_tokens)
        n = len(parts_bodies)
        part_names = [changelog_part_filename(naming, k) for k in range(2, n + 1)]
        parts_line = "Parts: " + ", ".join(f"[{nm}]({nm})" for nm in part_names) + nl
        header1 = part1_bare_header if n <= 1 else f"[← {index_name}]({index_name}){nl}{nl}{parts_line}{nl}"
        if changelog_tokens(header1) <= reserved:
            break
    out = []
    for k, body_list in enumerate(parts_bodies, start=1):
        header = header1 if k == 1 else other_header
        name = part1_name if k == 1 else changelog_part_filename(naming, k)
        out.append((name, header + "".join(body_list)))
    return out


def check_parts_budget(split: list, budget: int = READ_TOKEN_WARN) -> list:
    """Return `split` unchanged, or raise `Refusal` naming the first part
    that measures at or over `budget`."""
    for name, text in split:
        tokens = changelog_tokens(text)
        if tokens >= budget:
            raise Refusal(f"changelog part {name} would measure ~{tokens} tokens, over the {budget}-token "
                          "per-file budget: an entry in it has a paragraph too large to sit beside the part's "
                          "header; add a blank line inside it by hand, then re-run")
    return split


JOURNAL_MODE = "write-in-progress"


def journal_paths(ledger_path: Path) -> set:
    """The resolved paths an interrupted `--write` was replacing, read from
    the in-progress journal it left at the ledger path; empty otherwise."""
    try:
        data = json.loads(read_text(ledger_path))
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict) or data.get("mode") != JOURNAL_MODE:
        return set()
    return {Path(p).resolve() for p in data.get("targets", ())}


def joined_entries(texts: list) -> str:
    """Every part's entry text, in order, with the backlink/Parts lines and
    the `## Entry` section headers removed -- the basis `verify_written` and
    `unaccounted` check footer segments against."""
    chunks = []
    for text in texts:
        norm = text.replace("\r\n", "\n")
        kept = [ln for ln in norm.split("\n")
                if not (BACKLINK_RE.match(ln.strip()) or PARTS_LINE_RE.match(ln) or ENTRY_HEADING_RE.match(ln.strip()))]
        chunks.append("\n".join(kept))
    return "\n".join(chunks)


def parse_changelog(texts: list) -> list:
    """Inverse of `split_changelog`. `texts` are the changelog part files in
    part order, part 1 first. Strips the backlink and `Parts:` lines and
    re-joins continuation sections. Any other text outside an `## Entry`
    section raises `Refusal`, naming the part and the line. Returns the
    segment bytes in entry order."""
    assembled = []
    for pi, text in enumerate(texts):
        lines = text.replace("\r\n", "\n").split("\n")
        i, n = 0, len(lines)
        if i >= n or not BACKLINK_RE.match(lines[i].strip()):
            found = lines[i] if i < n else ""
            raise Refusal(f"part {pi + 1} line {i + 1}: expected the backlink line, found {found!r}")
        i += 1
        if i < n and lines[i] == "":
            i += 1
        if i < n and PARTS_LINE_RE.match(lines[i]):
            i += 1
            if i < n and lines[i] == "":
                i += 1
        remainder = lines[i:]
        headings = []
        for j, line in enumerate(remainder):
            stripped = line.strip()
            match = ENTRY_HEADING_RE.match(stripped)
            if stripped.startswith("## ") and not match:
                raise Refusal(f"part {pi + 1} line {i + j + 1}: unrecognised section heading {line!r}")
            if match:
                headings.append((j, int(match.group(1)), bool(match.group(2))))
        if not headings or headings[0][0] != 0:
            bad = remainder[0] if remainder else ""
            raise Refusal(f"part {pi + 1} line {i + 1}: text outside any '## Entry' section: {bad!r}")
        for h, (start, num, is_cont) in enumerate(headings):
            body_start = start + 1
            if body_start < len(remainder) and remainder[body_start] == "":
                body_start += 1
            end = headings[h + 1][0] if h + 1 < len(headings) else len(remainder)
            body_lines = remainder[body_start:end]
            while body_lines and body_lines[-1] == "":
                body_lines.pop()
            assembled.append((num, is_cont, "\n".join(body_lines)))
    result, current = [], None
    for num, is_cont, body in assembled:
        if not is_cont:
            if current is not None:
                result.append("\n\n".join(current["parts"]))
            current = {"num": num, "parts": [body]}
        else:
            if current is None or current["num"] != num:
                raise Refusal(f"entry {num} (continued) has no matching entry heading before it")
            current["parts"].append(body)
    if current is not None:
        result.append("\n\n".join(current["parts"]))
    return [body.encode("utf-8") for body in result]


def changelog_budget_status(config: dict, index_path: Path) -> list:
    """{path, tokens, level} for part 1 plus every existing `Part-NN` file.
    Empty when no changelog exists yet."""
    naming = _index_naming(index_path)
    part1_path = index_path.with_name(_changelog_filename(naming))
    if not part1_path.exists():
        return []
    pattern = changelog_part_pattern(naming)
    files = [part1_path] + sorted(p for p in index_path.parent.iterdir() if pattern.match(p.name))
    out = []
    for path in files:
        text = read_text(path)
        num_bytes, tokens = _measure(text.replace("\r\n", "\n"))
        out.append({"path": str(path), "tokens": tokens, "level": _changelog_level(num_bytes, tokens)})
    return out


def plan_changelog_resplit(config: dict, index_path: Path):
    """Re-split an already-migrated changelog that has grown over budget.
    Returns None when every existing changelog file already measures within
    budget; otherwise {"outputs": [(path, text)], "targets": [...], "parts":
    [...], "remove": [...]}. `remove` lists each existing `Part-NN` file
    the new layout no longer uses; its entries now sit in `outputs`. The
    parts keep part 1's line endings. No other plan step runs."""
    naming = _index_naming(index_path)
    part1_path = index_path.with_name(_changelog_filename(naming))
    if not part1_path.exists():
        return None
    pattern = changelog_part_pattern(naming)
    numbered = [(1, part1_path)]
    numbered += [(int(pattern.match(p.name).group(1)), p)
                 for p in index_path.parent.iterdir() if pattern.match(p.name)]
    numbered.sort(key=lambda kp: kp[0])
    targets = [p for _k, p in numbered]
    texts_on_disk = [read_text(p) for p in targets]
    ok = all(_changelog_level(*_measure(t.replace("\r\n", "\n"))) == "OK" for t in texts_on_disk)
    if ok:
        return None
    segments = parse_changelog(texts_on_disk)
    nl = newline_of(texts_on_disk[0])
    split = check_parts_budget(split_changelog(segments, naming, index_path.name, nl))
    outputs = [(index_path.with_name(name), text) for name, text in split]
    parts_meta = [{"path": str(path), "tokens": changelog_tokens(text),
                   "entries": len(ENTRY_HEADING_RE.findall(text.replace("\r\n", "\n")))}
                  for path, text in outputs]
    written = {path for path, _text in outputs}
    return {"outputs": outputs, "targets": targets, "parts": parts_meta,
            "remove": [path for path in targets if path not in written]}
