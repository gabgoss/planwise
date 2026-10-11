"""Normalise an agent verdict's `notes` field from its machine channel.

The upgrade writer reads a non-empty `notes` on a SUBSET verdict as "this file
carries tolerated installed-only content" and routes the file to the
customization-handling path. An agent that writes commentary into `notes` on a
clean SUBSET therefore flips a safe refresh into a transfer. The agent protocol
gives the agent a separate key, `tolerated_fragments` (a list of strings), for
the one thing `notes` was reserved for. This module turns that key into `notes`
so the three `notes` gates and the transfer header stay unchanged.

Safety bias: an absent `tolerated_fragments` key means legacy behaviour, so an
agent that follows an older protocol can never cause a silent overwrite. An
empty list beside prose `notes` is contradictory, so a clean-looking entry is
ignored and the inline primitive decides. An entry with `unique_blocks` or a
"unique" confidence is returned unchanged, so its prose `notes` still routes
it to the transfer path. A HAS_UNIQUE entry is never rewritten, because
the transfer header writes its `notes` summary.
"""


def sanitize_agent_entry(entry: dict) -> "dict | None":
    """Return a copy of `entry` with `notes` taken from `tolerated_fragments`.

    The rewrite applies only when `source` is "agent", `classification` is
    "SUBSET" and the `tolerated_fragments` key is present. Then `notes` becomes
    the fragments joined by newlines (an empty list gives ""), and `rationale`
    (free commentary) is dropped from the copy.

    Items that are empty after `.strip()` are dropped before the join. Returns
    None, and the caller must ignore the cached verdict, when the key is not a
    list of strings or when no real fragment remains while `notes` is
    non-empty and the entry otherwise looks clean. Any other entry is returned unchanged. The input is never mutated, because the verdicts
    dict is shared between writer sites.
    """
    if not (
        entry.get("source") == "agent"
        and entry.get("classification") == "SUBSET"
        and "tolerated_fragments" in entry
    ):
        return entry
    fragments = entry["tolerated_fragments"]
    if not isinstance(fragments, list) or not all(isinstance(f, str) for f in fragments):
        return None
    kept = [f for f in fragments if f.strip()]
    if not kept and entry.get("notes"):
        if entry.get("unique_blocks") or entry.get("confidence") == "unique":
            return entry
        return None
    sanitized = dict(entry)
    sanitized["notes"] = "\n".join(kept)
    sanitized.pop("rationale", None)
    return sanitized
