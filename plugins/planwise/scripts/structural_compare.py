"""Structural comparison primitive for markdown rule/agent files.

Segments a markdown document into structural blocks (frontmatter, headings,
top-level callouts, and preamble/body text), normalizes each block's raw
text into an order- and whitespace-insensitive token multiset, and
classifies an "installed" copy of a file against a "shipped" reference copy
as either a strict SUBSET of the shipped content or as containing genuinely
unique (installed-only) content.

The single verdict this module produces — SUBSET vs HAS_UNIQUE, with a
confidence level of exact / contained / reorg / unique — is the shared
decision primitive for telling "this installed file is safe to silently
refresh/remove" apart from "this file carries a customization and must be
preserved."

Pure stdlib only; imports nothing project-specific.
"""

import collections
import dataclasses
import re
import unicodedata

MIN_BLOCK_TOKENS = 4
UNIQUE_SAMPLE_LIMIT = 12

_CONFIDENCE_ORDER = ("exact", "contained", "reorg", "unique")

# --- Segmentation patterns -------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_CALLOUT_RE = re.compile(r"^>\s*\[!(\w+)\]\s*(.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

_PATHS_LINE_RE = re.compile(r"^paths:.*$\n?", re.MULTILINE)

# --- normalize_tokens patterns ----------------------------------------------

_LEADING_QUOTE_RE = re.compile(r"^>\s?", re.MULTILINE)
_ANCHOR_BRACE_RE = re.compile(r"\{#[^}]*\}")
_HTML_ANCHOR_OPEN_RE = re.compile(r"<a\s+name=[^>]*>(?:\s*</a>)?", re.IGNORECASE)
_HTML_ANCHOR_CLOSE_RE = re.compile(r"</a>", re.IGNORECASE)
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_LEADING_ENUM_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s", re.MULTILINE)
_FENCE_MARKER_RE = re.compile(r"^\s*(```|~~~)\S*[ \t]*$", re.MULTILINE)
_HEADING_MARKER_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_BULLET_RE = re.compile(r"^[-*+]\s+", re.MULTILINE)
_ORDERED_LIST_RE = re.compile(r"^\d+[.)]\s+", re.MULTILINE)
_CHECKBOX_RE = re.compile(r"\[[ xX]\]")
_PUNCT_ONLY_RE = re.compile(r"^\W+$")


@dataclasses.dataclass
class Block:
    kind: str                      # "frontmatter" | "heading" | "callout" | "preamble"
    label: str                     # heading text / "[!type] <title>" / "" for preamble
    raw_text: str
    tokens: collections.Counter
    is_noise: bool


@dataclasses.dataclass
class StructuralVerdict:
    classification: str            # "SUBSET" | "HAS_UNIQUE"
    confidence: str                # "exact" | "contained" | "reorg" | "unique"
    unique_blocks: list             # installed-only block labels; [] when SUBSET
    shared_blocks: int
    total_installed_blocks: int
    installed_only_chars: int
    unique_sample_tokens: list
    source: str = "inline"         # "inline" | "agent"
    notes: str = ""

    def as_dict(self) -> dict:
        """Return every field as a plain dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StructuralVerdict":
        """Build a StructuralVerdict from a dict, tolerating extra keys."""
        field_names = {f.name for f in dataclasses.fields(cls)}
        kwargs = {k: v for k, v in d.items() if k in field_names}
        return cls(**kwargs)


def split_frontmatter(content: str):
    """Split off YAML frontmatter, removing the ``paths:`` key.

    Returns ``(frontmatter_minus_paths, body)``:

    - ``frontmatter_minus_paths`` is ``None`` when ``content`` has no
      frontmatter delimiters (does not start with ``"---\\n"``, or no
      closing ``"\\n---\\n"`` is found); ``body`` is then the original
      ``content``, unchanged.
    - Otherwise ``frontmatter_minus_paths`` is the frontmatter text with the
      single ``paths:`` line removed and trailing whitespace stripped
      (possibly ``""`` if ``paths:`` was the only key), and ``body`` is the
      text following the closing delimiter.

    This replicates the current frontmatter-split behavior byte-for-byte:
    reconstructing ``"" -> body``, otherwise
    ``f"---\\n{frontmatter}\\n---\\n{body}"``, must equal the pre-refactor
    output exactly.
    """
    if not content.startswith("---\n"):
        return None, content
    end = content.find("\n---\n", 4)
    if end == -1:
        return None, content
    frontmatter_text = content[4:end]
    body = content[end + 5:]
    cleaned = _PATHS_LINE_RE.sub("", frontmatter_text, count=1)
    cleaned = cleaned.rstrip()
    return cleaned, body


def normalize_tokens(text: str) -> collections.Counter:
    """Normalize block text into an order-/whitespace-insensitive token multiset.

    Seven-step pipeline: strip the leading callout-blockquote marker; fold
    case and Unicode form; drop anchors and link targets (keeping link
    text); strip leading heading enumeration; strip structural markers
    (headings, bullets, ordered numbers, table pipes, checkboxes, emphasis,
    backticks, fences); split on whitespace, dropping empty and
    pure-punctuation tokens; count into a Counter.

    Code content is kept as tokens — it is not discarded.
    """
    # 1. strip a leading `>` blockquote marker from each line.
    text = _LEADING_QUOTE_RE.sub("", text)

    # 2. lowercase + NFKC normalize (folds smart quotes, width variants, etc).
    text = unicodedata.normalize("NFKC", text).lower()

    # 3. remove anchors and link targets, keeping link text.
    text = _HTML_ANCHOR_OPEN_RE.sub("", text)
    text = _HTML_ANCHOR_CLOSE_RE.sub("", text)
    text = _ANCHOR_BRACE_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)

    # 4. strip leading heading enumeration ("1.2.3. " / "1. ").
    text = _LEADING_ENUM_RE.sub("", text)

    # 5. strip structural markers.
    text = _FENCE_MARKER_RE.sub("", text)
    text = _HEADING_MARKER_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = _ORDERED_LIST_RE.sub("", text)
    text = _CHECKBOX_RE.sub("", text)
    text = text.replace("|", " ")
    text = text.replace("`", "")
    text = text.replace("*", "").replace("_", "")

    # 6. split on whitespace, dropping empty / pure-punctuation tokens.
    raw_tokens = text.split()
    tokens = [t for t in raw_tokens if t and not _PUNCT_ONLY_RE.match(t)]

    # 7. multiset: repetition is signal, order is not.
    return collections.Counter(tokens)


def _make_block(kind: str, label: str, raw_text: str) -> Block:
    tokens = normalize_tokens(raw_text)
    is_noise = sum(tokens.values()) < MIN_BLOCK_TOKENS
    return Block(kind=kind, label=label, raw_text=raw_text, tokens=tokens, is_noise=is_noise)


def segment_blocks(content: str) -> list:
    """Segment markdown content into a list of Block objects.

    Frontmatter (minus ``paths:``) is emitted as a pseudo-block. The body is
    then walked line-by-line, tracking whether the walk is inside a fenced
    code block (``in_fence``), one open heading/preamble block, and an
    optional open top-level callout block. While ``in_fence``, no line is
    ever treated as structural (headings / callouts / blockquotes inside a
    fence stay inert) — this is the highest-impact correctness edge, since
    documentation fixtures pervasively show fenced ``> [!x]`` / ``###``
    example text that must not be split into real blocks.
    """
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if content.startswith("﻿"):
        content = content[1:]

    frontmatter, body = split_frontmatter(content)

    blocks: list = []
    if frontmatter is not None:
        blocks.append(_make_block("frontmatter", "", frontmatter))

    current_kind = "preamble"
    current_label = ""
    current_lines: list = []
    callout: dict | None = None
    in_fence = False

    def flush_current() -> None:
        nonlocal current_lines
        blocks.append(_make_block(current_kind, current_label, "\n".join(current_lines)))
        current_lines = []

    def flush_callout() -> None:
        nonlocal callout
        if callout is not None:
            blocks.append(_make_block("callout", callout["label"], "\n".join(callout["lines"])))
            callout = None

    for line in body.split("\n"):
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            in_fence = not in_fence
            if callout is not None:
                callout["lines"].append(line)
            else:
                current_lines.append(line)
            continue

        if in_fence:
            # In-fence lines are never structural — append verbatim.
            if callout is not None:
                callout["lines"].append(line)
            else:
                current_lines.append(line)
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush_callout()
            flush_current()
            current_kind = "heading"
            current_label = heading_match.group(2).strip()
            current_lines.append(line)
            continue

        callout_match = _CALLOUT_RE.match(line)
        if callout_match:
            flush_callout()
            title = callout_match.group(2).strip()
            label = f"[!{callout_match.group(1)}] {title}".rstrip()
            callout = {"label": label, "lines": [line]}
            continue

        if line.startswith(">") and callout is not None:
            # Blockquote continuation (also absorbs nested "> >" lines,
            # which never matched _CALLOUT_RE above).
            callout["lines"].append(line)
            continue

        # Any other line (prose / table row / body "---" / blank line)
        # ends any open callout and belongs to the current block.
        flush_callout()
        current_lines.append(line)

    flush_callout()
    flush_current()

    return blocks


def multiset_subset(a: collections.Counter, b: collections.Counter) -> bool:
    """True when every element of multiset ``a`` appears in ``b`` with >= count."""
    return not (a - b)


def classify_blocks(installed_raw: str, shipped_raw: str, *, source: str = "inline") -> StructuralVerdict:
    """Classify installed content against shipped content as SUBSET or HAS_UNIQUE.

    Every non-noise installed block is matched against the shipped blocks at
    its best level — exact (equal Counter) > contained (multiset-subset of a
    single shipped block) > reorg (multiset-subset of the block union of all
    shipped blocks only) > unique (not contained anywhere). The overall
    classification is HAS_UNIQUE if any installed block is unique, else
    SUBSET; confidence is the worst level present across all blocks.
    """
    installed_blocks = segment_blocks(installed_raw)
    shipped_blocks = segment_blocks(shipped_raw)

    inst = [b for b in installed_blocks if not b.is_noise]
    ship = [b for b in shipped_blocks if not b.is_noise]

    ship_global: collections.Counter = collections.Counter()
    for sb in ship:
        ship_global.update(sb.tokens)

    unique_blocks: list = []
    unique_sample_tokens: list = []
    levels_present: set = set()
    shared_count = 0
    installed_only_chars = 0

    for ib in inst:
        level = "unique"
        for sb in ship:
            if ib.tokens == sb.tokens:
                level = "exact"
                break
        if level != "exact":
            for sb in ship:
                if multiset_subset(ib.tokens, sb.tokens):
                    level = "contained"
                    break
        if level not in ("exact", "contained"):
            level = "reorg" if multiset_subset(ib.tokens, ship_global) else "unique"

        levels_present.add(level)

        if level == "unique":
            unique_blocks.append(ib.label)
            installed_only_chars += len(ib.raw_text)
            for tok in ib.tokens:
                if len(unique_sample_tokens) >= UNIQUE_SAMPLE_LIMIT:
                    break
                unique_sample_tokens.append(tok)
        else:
            shared_count += 1

    classification = "HAS_UNIQUE" if "unique" in levels_present else "SUBSET"

    confidence = "exact"
    for level in reversed(_CONFIDENCE_ORDER):
        if level in levels_present:
            confidence = level
            break

    return StructuralVerdict(
        classification=classification,
        confidence=confidence,
        unique_blocks=unique_blocks,
        shared_blocks=shared_count,
        total_installed_blocks=len(inst),
        installed_only_chars=installed_only_chars,
        unique_sample_tokens=unique_sample_tokens[:UNIQUE_SAMPLE_LIMIT],
        source=source,
    )


def is_subset(v: StructuralVerdict) -> bool:
    return v.classification == "SUBSET"


def is_safe_to_remove(v: StructuralVerdict) -> bool:
    return v.classification == "SUBSET" and v.confidence in {"exact", "contained"}
