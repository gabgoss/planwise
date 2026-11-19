"""Installed-vs-shipped rule divergence classification.

The shared primitive the rule de-scope migration, the artifact refresh, and
the doctor sweeps all call to decide whether an installed file still matches
its shipped counterpart. Includes the structural_compare ImportError
degradation (documented design: a missing/broken structural_compare degrades
to a conservative preserve-on-doubt verdict rather than crashing).
"""

import hashlib
import json
import re
import types
from pathlib import Path

# The frontmatter split/parse primitives, bound under this module's long-standing
# private names so `init_project`'s re-export block and any external caller keep
# resolving them. The implementations live in one module now; before, three of
# them were mirrored here and disagreed with each other on BOM handling and on
# their absence signal.
from frontmatter_parser import (
    BOM_CHAR as _BOM_CHAR,  # also re-exported for callers of rule_divergence
)
from frontmatter_parser import (
    FM_KEY_LINE_RE as _FM_KEY_LINE_RE,  # noqa: F401 -- re-exported for callers of rule_divergence
)
from frontmatter_parser import (
    PATHS_LINE_RE as _FALLBACK_PATHS_LINE_RE,  # noqa: F401 -- re-exported for callers of rule_divergence
)
from frontmatter_parser import (
    parse_frontmatter_map as _parse_frontmatter_map,  # noqa: F401 -- re-exported for callers of rule_divergence
)
from frontmatter_parser import (
    split_frontmatter_block as _split_frontmatter_block,  # noqa: F401 -- re-exported for callers of rule_divergence
)
from frontmatter_parser import (
    split_frontmatter_without_paths as _split_frontmatter_fallback,
)

try:
    import structural_compare

    # is_safe_to_remove/is_subset gate the disposition sites below;
    # classify_blocks/StructuralVerdict are re-exported for downstream verdict consumers.
    from structural_compare import (  # noqa: F401
        StructuralVerdict,
        classify_blocks,
        is_safe_to_remove,
        is_subset,
    )
    HAS_STRUCTURAL_COMPARE = True
except ImportError:
    # A missing/broken structural_compare must degrade (preserve-on-doubt via
    # _classify_diverged) rather than hard-crash the whole CLI at import time.
    structural_compare = None
    HAS_STRUCTURAL_COMPARE = False

    # Degraded predicates so the disposition call sites stay callable when the
    # primitive module is unavailable. Both read attributes off the verdict
    # object (duck-typed against the degraded HAS_UNIQUE stand-in).
    def is_subset(v):
        return getattr(v, "classification", "HAS_UNIQUE") == "SUBSET"

    def is_safe_to_remove(v):
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


# The single `consult-when:` line, with its newline, anywhere in a frontmatter
# block. The key is index metadata for the generated reference library, not rule
# content, so a copy installed before the key existed is not a customization.
_CONSULT_WHEN_LINE_RE = re.compile(r"^consult-when:.*$\n?", re.MULTILINE)


def normalize_rule_for_diff(content: str) -> str:
    """Return the rule body with the `paths:` and `consult-when:` keys removed.

    Per-project install rewrites the `paths:` line via update_frontmatter().
    The `consult-when:` line is reference-library index metadata, which an
    installed copy written before the key shipped does not carry. To detect
    whether the installed body matches the shipped body, we strip those two
    keys from BOTH sides before comparing. Everything else in the frontmatter
    and the body content must match exactly for the file to be considered
    "unmodified by user."

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
    if cleaned_frontmatter:
        cleaned_frontmatter = _CONSULT_WHEN_LINE_RE.sub("", cleaned_frontmatter, count=1).rstrip()
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


def normalize_pair(installed_text: str, shipped_text: str, norm=normalize_rule_for_diff) -> tuple[str, str]:
    """Pass an installed rule's text and its shipped text through `norm`.

    Both texts are already read, each as `utf-8-sig`, so the caller owns the read
    and the error label for the file that failed. The result is `(installed,
    shipped)`. The two are equal exactly when the installed rule matches its
    shipped counterpart under `norm`. Three callers share this compare: the
    doctor sweep that checks installed rules, the style-rule verdict and the
    style-rule refresh test.
    """
    return norm(installed_text), norm(shipped_text)


# Unambiguous marker for the degraded not-analyzed stand-in `_classify_diverged`
# manufactures when structural_compare is unavailable at call time. Checked
# ONLY by `_verdict_not_analyzed()` — a real verdict (inline or agent-sourced)
# never carries this value, so a genuine HAS_UNIQUE verdict that happens to
# have empty unique_blocks and non-empty notes can never be misidentified as
# "never analyzed" (the old shape-based detection's false-positive hazard).
_DEGRADED_VERDICT_SOURCE = "not-analyzed"

# Source of the verdict `_classify_diverged` returns when the installed body
# matches a body the plugin shipped in an earlier release.
_HISTORY_VERDICT_SOURCE = "shipped-history"

# Digests of every body each installed, de-scoped and style rule reference has
# ever shipped. Written by `tools/gen_rule_history.py` from the plugin repo's
# git history, so it is never edited by hand.
RULE_HISTORY_MANIFEST = Path(__file__).resolve().parent.parent / "manifests" / "rule-history.json"

# {manifest path: ((mtime_ns, size), parsed digests)}. See `load_rule_history`.
_RULE_HISTORY_CACHE: "dict[str, tuple[tuple[int, int], dict[str, set[str]]]]" = {}


def rule_history_digest(text: str) -> str:
    """Return the sha256 hex of a rule body in its comparison form.

    Drops a leading BOM, folds CRLF to LF, then applies `normalize_rule_for_diff`,
    so a rule installed with a project-specific `paths:` value digests the same as
    the shipped reference. The manifest generator and the classifier call this one
    function, so the two cannot disagree.
    """
    text = text.lstrip(_BOM_CHAR).replace("\r\n", "\n")
    return hashlib.sha256(normalize_rule_for_diff(text).encode("utf-8")).hexdigest()


def load_rule_history(manifest_path: "Path | None" = None) -> "dict[str, set[str]]":
    """Return {rule filename: {digest of every body it ever shipped}}.

    A missing, unreadable or malformed manifest returns {}, so the classifier
    falls back to the structural comparison and never adopts on missing evidence.
    """
    path = RULE_HISTORY_MANIFEST if manifest_path is None else manifest_path
    try:
        stat = path.stat()
    except OSError:
        return {}
    # One upgrade classifies many rules, so the file is read once per process and
    # signature. The signature is a stat call and never reads the file.
    signature = (stat.st_mtime_ns, stat.st_size)
    cached = _RULE_HISTORY_CACHE.get(str(path))
    if cached is not None and cached[0] == signature:
        return {name: set(digests) for name, digests in cached[1].items()}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        loaded = {
            str(name): {str(d) for d in digests}
            for name, digests in doc["rules"].items()
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        loaded = {}
    _RULE_HISTORY_CACHE[str(path)] = (signature, loaded)
    return {name: set(digests) for name, digests in loaded.items()}


def _matches_shipped_history(installed_norm: str) -> bool:
    """True when the installed body equals a body some release shipped.

    A body the plugin shipped holds no user text, so the check takes the union of
    every listed digest and needs no filename.
    """
    history = load_rule_history()
    if not history:
        return False
    digest = rule_history_digest(installed_norm)
    return any(digest in digests for digests in history.values())


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

    The first check is the shipped-history manifest. An installed body that
    matches any body an earlier release shipped is an unedited older rule, so it
    returns SUBSET at exact confidence with source `shipped-history`, before the
    override and before any structural comparison. Every caller inherits this
    without an edit.
    """
    if _matches_shipped_history(installed_norm):
        fields = {
            "classification": "SUBSET",
            "confidence": "exact",
            "unique_blocks": [],
            "shared_blocks": 0,
            "total_installed_blocks": 0,
            "installed_only_chars": 0,
            "unique_sample_tokens": [],
            "source": _HISTORY_VERDICT_SOURCE,
            "notes": "",
        }
        try:
            from structural_compare import StructuralVerdict as _Verdict
        except ImportError:
            # Duck-typed stand-in: the real class is unavailable on this branch.
            return types.SimpleNamespace(**fields)  # pyright: ignore[reportReturnType]
        return _Verdict.from_dict(fields)
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

