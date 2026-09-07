"""Installed-vs-shipped rule divergence classification.

The shared primitive the rule de-scope migration, the artifact refresh, and
the doctor sweeps all call to decide whether an installed file still matches
its shipped counterpart. Includes the structural_compare ImportError
degradation (documented design: a missing/broken structural_compare degrades
to a conservative preserve-on-doubt verdict rather than crashing).
"""

import re
import types

# The frontmatter split/parse primitives, bound under this module's long-standing
# private names so `init_project`'s re-export block and any external caller keep
# resolving them. The implementations live in one module now; before, three of
# them were mirrored here and disagreed with each other on BOM handling and on
# their absence signal.
from frontmatter_parser import (
    BOM_CHAR as _BOM_CHAR,  # noqa: F401 -- re-exported for callers of rule_divergence
    FM_KEY_LINE_RE as _FM_KEY_LINE_RE,  # noqa: F401 -- re-exported for callers of rule_divergence
    PATHS_LINE_RE as _FALLBACK_PATHS_LINE_RE,  # noqa: F401 -- re-exported for callers of rule_divergence
    parse_frontmatter_map as _parse_frontmatter_map,  # noqa: F401 -- re-exported for callers of rule_divergence
    split_frontmatter_block as _split_frontmatter_block,  # noqa: F401 -- re-exported for callers of rule_divergence
    split_frontmatter_without_paths as _split_frontmatter_fallback,  # noqa: F401 -- re-exported for callers of rule_divergence
)


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

    Calls the shared frontmatter_parser split directly, so this normalization
    keeps producing the same output whether or not structural_compare is
    importable — the split no longer travels through it, which is what used to
    require a byte-identical inline mirror here. (Sibling helpers
    update_frontmatter/_extract_paths_value still carry their own inline
    frontmatter handling — keep the two consistent with this split when
    editing either.)
    """
    cleaned_frontmatter, body = _split_frontmatter_fallback(content)
    if not cleaned_frontmatter:
        return body
    return f"---\n{cleaned_frontmatter}\n---\n{body}"


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

