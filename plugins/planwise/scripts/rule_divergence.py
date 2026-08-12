"""Installed-vs-shipped rule divergence classification.

The shared primitive the rule de-scope migration, the artifact refresh, and
the doctor sweeps all call to decide whether an installed file still matches
its shipped counterpart. Includes the structural_compare ImportError
degradation (documented design: a missing/broken structural_compare degrades
to a conservative preserve-on-doubt verdict rather than crashing).
"""

import re
import types


try:
    import structural_compare
    # is_safe_to_remove/is_subset gate the disposition sites below;
    # classify_blocks/StructuralVerdict are re-exported for downstream verdict consumers.
    from structural_compare import classify_blocks, is_safe_to_remove, is_subset, StructuralVerdict  # noqa: F401
    HAS_STRUCTURAL_COMPARE = True
except ImportError:
    # A missing/broken structural_compare must degrade (preserve-on-doubt via
    # _classify_diverged) rather than hard-crash the whole CLI at import time.
    structural_compare = None
    HAS_STRUCTURAL_COMPARE = False

    # Degraded predicates so the disposition call sites stay callable when the
    # primitive module is unavailable. Both read attributes off the verdict
    # object (duck-typed against the degraded HAS_UNIQUE stand-in).
    def is_subset(v):           # noqa: E306
        return getattr(v, "classification", "HAS_UNIQUE") == "SUBSET"

    def is_safe_to_remove(v):   # noqa: E306
        return is_subset(v) and getattr(v, "confidence", "unique") in {"exact", "contained"}


def _destructively_removable(v) -> bool:
    """True when a verdict clears every destructive-disposition gate.

    SUBSET at exact/contained confidence (is_safe_to_remove) AND no
    tolerated installed-only content — a non-empty verdict.notes means the
    matcher tolerated installed-only content it could not prove was noise.
    Shared by every site that deletes or overwrites an installed file based
    on a structural verdict, in both the real and degraded import modes.
    """
    return is_safe_to_remove(v) and not (getattr(v, "notes", "") or "")


def normalize_rule_for_diff(content: str) -> str:
    """Return the rule body with the `paths:` frontmatter key removed.

    Per-project install rewrites the `paths:` line via update_frontmatter().
    To detect whether the installed body matches the shipped body, we strip
    that single key from BOTH sides before comparing. Everything else in the
    frontmatter and the body content must match exactly for the file to be
    considered "unmodified by user."

    Uses a pure regex line-strip (no YAML round-trip) so the shipped
    reference's placeholder paths value (which contains literal curly
    braces) and the installed file's resolved paths value are normalized
    identically.

    Delegates the split to structural_compare.split_frontmatter() when the
    module is importable, with a byte-identical inline fallback when it is
    not, so a degraded install keeps diffing correctly. (Sibling helpers
    update_frontmatter/_extract_paths_value retain their own inline
    frontmatter handling — keep the three consistent when editing any.)
    """
    if structural_compare is not None:
        cleaned_frontmatter, body = structural_compare.split_frontmatter(content)
    else:
        cleaned_frontmatter, body = _split_frontmatter_fallback(content)
    if not cleaned_frontmatter:
        return body
    return f"---\n{cleaned_frontmatter}\n---\n{body}"


_FALLBACK_PATHS_LINE_RE = re.compile(r"^paths:.*$\n?", re.MULTILINE)


def _split_frontmatter_fallback(content: str):
    """Byte-identical inline mirror of structural_compare.split_frontmatter.

    Used only when the structural_compare module is unavailable, so
    normalize_rule_for_diff keeps producing the same output in a degraded
    install. Returns (None, content) when there is no frontmatter, else
    (frontmatter_minus_paths, body).
    """
    if not content.startswith("---\n"):
        return None, content
    end = content.find("\n---\n", 4)
    if end == -1:
        return None, content
    frontmatter_text = content[4:end]
    body = content[end + 5:]
    cleaned = _FALLBACK_PATHS_LINE_RE.sub("", frontmatter_text, count=1)
    return cleaned.rstrip(), body


def _extract_paths_value(content: str) -> str | None:
    """Return the `paths:` frontmatter value from a rule file, or None.

    Reads only the leading `---` frontmatter block; returns the verbatim value
    after `paths:` (stripped of surrounding whitespace). Returns None when the
    file has no frontmatter or no paths: key.
    """
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end == -1:
        return None
    frontmatter_text = content[4:end]
    match = re.search(r"^paths:(.*)$", frontmatter_text, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


# Unambiguous marker for the degraded not-analyzed stand-in `_classify_diverged`
# manufactures when structural_compare is unavailable at call time. Checked
# ONLY by `_verdict_not_analyzed()` — a real verdict (inline or agent-sourced)
# never carries this value, so a genuine HAS_UNIQUE verdict that happens to
# have empty unique_blocks and non-empty notes can never be misidentified as
# "never analyzed" (the old shape-based detection's false-positive hazard).
_DEGRADED_VERDICT_SOURCE = "not-analyzed"


def _classify_diverged(
    installed_norm: str,
    shipped_norm: str,
    *,
    override: "StructuralVerdict | None" = None,
) -> "StructuralVerdict":
    """Return the structural verdict for a normalized installed/shipped pair.

    If `override` (an agent-produced verdict) is supplied, it is returned
    as-is. Otherwise this delegates to structural_compare.classify_blocks().
    On ImportError (structural_compare missing/broken), degrades to a
    conservative HAS_UNIQUE verdict so the caller preserves the file rather
    than risk deleting a genuine customization — the safe error over the
    dangerous one. The degraded verdict is a duck-typed stand-in (attribute-
    compatible with StructuralVerdict), since the real class is unavailable
    exactly when this path fires. Its `source` is the explicit
    `_DEGRADED_VERDICT_SOURCE` marker (not a shape heuristic) so
    `_verdict_not_analyzed()` can never mistake a genuine verdict for this
    stand-in. Module-level (not nested) so tests can monkeypatch
    `ip._classify_diverged` directly.
    """
    if override is not None:
        return override
    try:
        from structural_compare import classify_blocks as _classify_blocks
    except ImportError:
        return types.SimpleNamespace(
            classification="HAS_UNIQUE",
            confidence="unique",
            unique_blocks=[],
            shared_blocks=0,
            total_installed_blocks=0,
            installed_only_chars=0,
            unique_sample_tokens=[],
            source=_DEGRADED_VERDICT_SOURCE,
            notes="structural_compare unavailable; degraded to preserve",
        )
    return _classify_blocks(installed_norm, shipped_norm)


_FM_KEY_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(.*)$")


# UTF-8 byte-order mark as a code point — kept as chr() so this source file
# stays pure ASCII (an invisible literal BOM in source is exactly the bug
# class the guard below exists to defeat).
_BOM_CHAR = chr(0xFEFF)


def _split_frontmatter_block(content: str) -> "tuple[str, str] | None":
    """Split `content` into (frontmatter_text, body). BOM-tolerant.

    Returns None when there is no complete, well-delimited frontmatter block
    (missing opening `---`, or no closing delimiter). A leading UTF-8 BOM is
    stripped before the delimiter check so a BOM'd file cannot silently
    defeat frontmatter-anchored logic.
    """
    content = content.lstrip(_BOM_CHAR)
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end == -1:
        return None
    return content[4:end], content[end + 5:]


def _parse_frontmatter_map(frontmatter_text: str) -> "dict[str, str] | None":
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
        m = _FM_KEY_LINE_RE.match(line)
        if m:
            current_key = m.group(1)
            result[current_key] = m.group(2).strip()
            continue
        if current_key is None:
            return None            # leading continuation with no key — unparseable
        result[current_key] += "\n" + line.rstrip()
    return result


def _verdict_not_analyzed(v) -> bool:
    """True for the degraded stand-in verdict `_classify_diverged` manufactures
    when structural_compare is unavailable at call time. The installed file
    was never actually analyzed, so the automated transfer-then-adopt path
    must NOT act on it — there is no verdict evidence to base an adoption on.
    The caller preserves the file in place and writes a shipped sidecar for
    manual merge (the always-safe degradation).

    Detection is by the explicit `source == _DEGRADED_VERDICT_SOURCE` marker
    ONLY — never by verdict shape. A genuine verdict (inline primitive or
    agent-sourced) that happens to be HAS_UNIQUE with empty unique_blocks and
    non-empty notes must NOT match: it carries real analysis evidence and
    routes through the normal customization-bearing disposition.
    """
    return getattr(v, "source", "") == _DEGRADED_VERDICT_SOURCE

