#!/usr/bin/env python3
"""Shared YAML-frontmatter split and parse primitives.

Every script that reads a `---`-delimited frontmatter block calls into this
module rather than re-deriving the split. Before consolidation the same parse
was implemented independently in four places, and the implementations did not
agree on their return shape, their absence signal, or their BOM handling — so
a caller could not be moved from one to another without reading both, and a
fix to one parser's malformed-input handling did not propagate.

## The contracts

Two split functions ship, because the tree genuinely needs two policies and
collapsing them would silently change what a caller sees. Their differences
are stated here, in one place, instead of being rediscovered per copy:

| Function | Returns | Absence signal | `paths:` | BOM |
|---|---|---|---|---|
| `split_frontmatter_block` | `(frontmatter_text, body)` | `None` | kept | stripped |
| `split_frontmatter_without_paths` | `(frontmatter_minus_paths, body)` | `(None, content)` | removed | not stripped |

`split_frontmatter_block` is the faithful primitive: it hands back the
frontmatter exactly as written, and tolerates a leading UTF-8 BOM so a BOM'd
file cannot silently defeat frontmatter-anchored logic.

`split_frontmatter_without_paths` is the rule-file *normalization* split. An
installed rule's `paths:` value is rewritten per project at install time, so
comparing an installed body against its shipped counterpart requires dropping
that one key from both sides first. It deliberately does NOT strip a BOM: its
callers either strip one upstream or rely on a BOM'd file reading as
"no frontmatter", and changing that here would change a comparison verdict.

`parse_frontmatter_map` turns a frontmatter *text* into a `{key: value-text}`
map without a YAML dependency, preserving continuation lines verbatim. It is
a text-level view, not a typed one — a caller that needs real YAML types
(dates, lists, numbers) parses the text this module hands back with `yaml`
itself.

Stdlib-only, so a partially-installed `scripts/` directory still imports it.
"""

import re

# A top-level `key: value` line. The key charset is deliberately narrow: a
# line that does not match is treated as a continuation of the key above it.
FM_KEY_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(.*)$")

# The single `paths:` line, with its newline, anywhere in a frontmatter block.
PATHS_LINE_RE = re.compile(r"^paths:.*$\n?", re.MULTILINE)

# UTF-8 byte-order mark as a code point — kept as chr() so this source file
# stays pure ASCII (an invisible literal BOM in source is exactly the bug
# class the BOM guard below exists to defeat).
BOM_CHAR = chr(0xFEFF)


def split_frontmatter_block(content: str) -> "tuple[str, str] | None":
    """Split `content` into (frontmatter_text, body). BOM-tolerant.

    Returns None when there is no complete, well-delimited frontmatter block
    (missing opening `---`, or no closing delimiter). A leading UTF-8 BOM is
    stripped before the delimiter check so a BOM'd file cannot silently
    defeat frontmatter-anchored logic.

    The frontmatter text is returned verbatim — no key is removed, and no
    trailing whitespace is stripped. Pair it with `parse_frontmatter_map` for
    a text-level map, or hand it to `yaml.safe_load` for typed values.
    """
    content = content.lstrip(BOM_CHAR)
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end == -1:
        return None
    return content[4:end], content[end + 5:]


def split_frontmatter_without_paths(content: str) -> "tuple[str | None, str]":
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

    Deliberately NOT BOM-tolerant — see the module docstring. Callers
    reconstruct ``"" -> body``, otherwise
    ``f"---\\n{frontmatter}\\n---\\n{body}"``.
    """
    if not content.startswith("---\n"):
        return None, content
    end = content.find("\n---\n", 4)
    if end == -1:
        return None, content
    frontmatter_text = content[4:end]
    body = content[end + 5:]
    cleaned = PATHS_LINE_RE.sub("", frontmatter_text, count=1)
    return cleaned.rstrip(), body


def parse_frontmatter_map(frontmatter_text: str) -> "dict[str, str] | None":
    """Parse a frontmatter block into a {key: value-text} map, or None.

    A top-level `key: value` line maps to its stripped scalar value; any
    continuation lines (indented content, `- ` list items, block scalars)
    are appended verbatim with their newlines, so a multi-line value is
    detectable via `"\\n" in value` AND two different multi-line values
    never compare equal. Returns None when a line cannot be attributed to
    any key (structurally unparseable — the guard treats that as
    cannot-guard).
    """
    result: dict[str, str] = {}
    current_key: "str | None" = None
    for line in frontmatter_text.split("\n"):
        if not line.strip():
            continue
        m = FM_KEY_LINE_RE.match(line)
        if m:
            current_key = m.group(1)
            result[current_key] = m.group(2).strip()
            continue
        if current_key is None:
            return None            # leading continuation with no key — unparseable
        result[current_key] += "\n" + line.rstrip()
    return result
