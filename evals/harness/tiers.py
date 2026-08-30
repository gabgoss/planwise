"""The tier registry.

Declares how many rows each marker (tier) is supposed to select, so
`evals/conftest.py`'s post-collection assertion can catch a zero- or
drifted-selection instead of letting it silently look like a passing tier.

Two counts are kept deliberately separate:

- ``EXPECTED_AT_COMPLETION`` — the row totals the finished suite will carry
  (declared up front, from the suite's cost/rollup arithmetic).
- ``CURRENT_ON_DISK`` — how many rows actually exist for each tier right
  now. A partially-built suite (e.g. the `full` and `prerelease` families
  before their owning rows land) must not false-fail the count assertion
  just because the eventual total hasn't been reached yet.

**Both dicts are PER-FAMILY, unique-row counts — NOT the cumulative tier
totals from the invocation table.** `declared_count_for()` SUMS the
per-family entries for the families a marker expression selects, so the
cumulative tier totals (`smoke` alone = 4 rows; `smoke or full` = 53 rows;
`smoke or full or prerelease` = 54 rows — see `evals/README.md`'s
invocation lines) are a DERIVED property of these dicts, never a value
stored in them directly. Storing a cumulative total in either dict makes
`declared_count_for()` double-count: summing the (wrongly) cumulative
`full` and `prerelease` entries on top of `smoke` would demand far more
rows than the suite actually has.

The conftest assertion is built against ``CURRENT_ON_DISK``. Each family's
row-authoring work bumps its own family's current count as it adds rows;
nobody edits ``EXPECTED_AT_COMPLETION`` — it is the fixed target the
rollup was priced against.
"""

from __future__ import annotations

# Per-family row counts the finished suite will carry, once every family's
# rows have landed. These SUM to the cumulative tier totals from the
# invocation table: smoke (4) + full (49) = 53 rows for `smoke or full`;
# + prerelease (1) = 54 rows for `smoke or full or prerelease`.
EXPECTED_AT_COMPLETION: dict[str, int] = {
    "smoke": 4,
    "full": 49,
    "prerelease": 1,
}

# Per-family row counts that actually exist on disk right now (same units
# as EXPECTED_AT_COMPLETION — per-family, not cumulative). Updated by
# whichever work adds a family's rows — never inferred, always declared
# explicitly here so a drifted count fails loudly instead of silently.
# `smoke` is 4 and now matches EXPECTED_AT_COMPLETION: the four smoke rows
# are authored and live in `evals/cases/`. `full` and `prerelease` remain 0
# until their own families' rows land, which is why this dict exists
# separately at all — a partially-built suite must not false-fail the count
# assertion just because the eventual total has not been reached yet.
CURRENT_ON_DISK: dict[str, int] = {
    "smoke": 4,
    "full": 0,
    "prerelease": 0,
}

# Marker expressions pytest is invoked with, in the order the CI table
# (evals/README.md) runs them, mapped to the CURRENT_ON_DISK tiers they
# cumulatively select.
_TIER_MARKER_EXPRESSIONS: dict[str, tuple[str, ...]] = {
    "smoke": ("smoke",),
    "smoke or full": ("smoke", "full"),
    "smoke or full or prerelease": ("smoke", "full", "prerelease"),
}


def declared_count_for(marker_expr: str) -> int | None:
    """The cumulative current-on-disk row count declared for a `-m` marker
    expression — the SUM of `CURRENT_ON_DISK`'s per-family entries for the
    families that expression selects. `CURRENT_ON_DISK` itself stores
    per-family counts, never a cumulative one, so this function is the only
    place the cumulative total should be computed.

    Returns ``None`` for an expression this registry doesn't recognize (for
    example the bare, marker-less invocation that only runs `evals/selftest/`
    — that count isn't a tier and isn't tracked here). A ``None`` result
    means "nothing to assert", not "zero is expected".
    """
    tiers = _TIER_MARKER_EXPRESSIONS.get(marker_expr.strip())
    if tiers is None:
        return None
    return sum(CURRENT_ON_DISK[tier] for tier in tiers)


# --- Ordering constraints (EI Part 4 Section 6) -----------------------------
# Encoded as data so the fixture engine / case runner can consult it rather
# than re-deriving ordering rules ad hoc.

# Runs first in any tier — the harness canary.
CANARY_FIRST = "EC-help-01"

# Runs last in its family.
FAMILY_LAST: dict[str, str] = {
    "quality": "EC-upgrade-03",
    "agents": "EC-agt-planner-01",
}

# Never shares a case dir; no other case may depend on it having run.
NEVER_SHARES_A_DIR: tuple[str, ...] = ("EC-list-02",)

# Rows that make two invocations inside one case dir (idempotency checks).
TWO_INVOCATIONS: tuple[str, ...] = (
    "EC-ts-on-02",
    "EC-ts-off-02",
    "EC-upgrade-02",
    "EC-list-03",
)

# Shared-envelope groups: rows graded off one captured E1/E2 envelope
# instead of an independent CLI invocation each. Only the anchor row and
# the shared-row count are known at this stage — the agent rows sharing
# each envelope, and the e1_envelope/e2_envelope fixtures themselves, are
# authored by whichever future work adds them; see the placeholder in
# evals/conftest.py.
SHARED_ENVELOPE_GROUPS: dict[str, dict[str, object]] = {
    "E1": {"anchor": "EC-review-noteam-01", "shared_agent_rows": 3},
    "E2": {"anchor": "EC-review-team-01", "shared_agent_rows": 1},
}
