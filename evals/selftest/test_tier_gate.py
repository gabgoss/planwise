"""Regression tests for the tier-count gate (evals/conftest.py's
`pytest_collection_finish`) and the harness.tiers registry's unit contract.

Two defects found by adversarial review, before this file existed, are
pinned here:

1. The tier-count assertion originally ran in `pytest_collection_modifyitems`
   — the SAME hookspec pytest's own `-m` marker deselection uses — before
   deselection had finished for every implementation of that hookspec. It
   therefore compared the PRE-deselection item count against a tier's
   declared count (observed: `EVALS SELECTED 90` — the full selftest total —
   for a 4-row `smoke` tier). Moving the assertion to `pytest_collection_finish`
   fixes it; the tests below prove the fix discriminates.
2. `tiers.py`'s two registries used different units: `EXPECTED_AT_COMPLETION`
   held CUMULATIVE tier totals (4 / 53 / 54, matching the invocation table)
   while `declared_count_for()` SUMS `CURRENT_ON_DISK` per family. A later
   edit that copied the cumulative values into `CURRENT_ON_DISK` would
   demand 57 rows for `smoke or full` (a 53-row tier) and 111 for the
   54-row release tier.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from harness import tiers

REPO_ROOT = Path(__file__).resolve().parents[2]  # cloned-repos/planwise
_SELECTED_RE = re.compile(r"EVALS SELECTED: (\d+) / declared (\d+|None)")


# --- declared_count_for() arithmetic, pinned in the corrected (per-family) units ---


def test_declared_count_for_smoke_only():
    assert tiers.declared_count_for("smoke") == tiers.CURRENT_ON_DISK["smoke"]


def test_declared_count_for_smoke_or_full_sums_two_families():
    expected = tiers.CURRENT_ON_DISK["smoke"] + tiers.CURRENT_ON_DISK["full"]
    assert tiers.declared_count_for("smoke or full") == expected


def test_declared_count_for_release_tier_sums_all_three_families():
    expected = (
        tiers.CURRENT_ON_DISK["smoke"]
        + tiers.CURRENT_ON_DISK["full"]
        + tiers.CURRENT_ON_DISK["prerelease"]
    )
    assert tiers.declared_count_for("smoke or full or prerelease") == expected


def test_declared_count_for_unregistered_expression_returns_none():
    assert tiers.declared_count_for("") is None
    assert tiers.declared_count_for("nonsense") is None
    assert tiers.declared_count_for("prerelease") is None  # not a registered tier alone


# --- unit-consistency pin: both registries must be per-family, same keys ---


def test_expected_and_current_share_the_same_keys():
    assert set(tiers.EXPECTED_AT_COMPLETION) == set(tiers.CURRENT_ON_DISK)


def test_expected_at_completion_is_per_family_and_sums_to_cumulative_totals():
    """Pins the unit contract itself. A regression that puts the CUMULATIVE
    tier totals back into EXPECTED_AT_COMPLETION (4, 53, 54 — copy-pasted
    straight from the invocation table) sums to 4, 57, 111, not 4, 53, 54 —
    this assertion catches that reintroduction directly."""
    assert tiers.EXPECTED_AT_COMPLETION["smoke"] == 4
    cumulative_full_tier = (
        tiers.EXPECTED_AT_COMPLETION["smoke"] + tiers.EXPECTED_AT_COMPLETION["full"]
    )
    cumulative_release_tier = (
        cumulative_full_tier + tiers.EXPECTED_AT_COMPLETION["prerelease"]
    )
    assert cumulative_full_tier == 53
    assert cumulative_release_tier == 54


def test_current_on_disk_never_exceeds_expected_per_family():
    """CURRENT_ON_DISK is a partial, in-progress count — each family's
    current value must never exceed its own expected-at-completion value.
    This comparison is only meaningful because both dicts share units."""
    for family, expected in tiers.EXPECTED_AT_COMPLETION.items():
        assert tiers.CURRENT_ON_DISK[family] <= expected


# --- post-deselection count, verified against a real subprocess pytest run ---


def _run_pytest_marker(marker_expr: str) -> subprocess.CompletedProcess[str]:
    inline = (
        "import os, sys, pytest; "
        f"os.chdir({str(REPO_ROOT)!r}); "
        "sys.exit(pytest.main(["
        "'-c', 'evals/pytest.ini', 'evals', '-m', "
        f"{marker_expr!r}, '-q']))"
    )
    return subprocess.run(
        [sys.executable, "-c", inline],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_smoke_selection_count_matches_declared_after_marker_deselection():
    """Regression guard: the tier-count assertion must count items AFTER
    pytest's own `-m` deselection, not before it. Proven to discriminate by
    temporarily reverting the `pytest_collection_finish` fix back to the
    original `pytest_collection_modifyitems` placement, watching this test
    fail (selected=90, declared=0, mismatch), and restoring the fix — see
    the task report for the mutation-proof record.
    """
    result = _run_pytest_marker("smoke")
    match = _SELECTED_RE.search(result.stdout)
    assert match, f"EVALS SELECTED line missing from stdout:\n{result.stdout}"
    selected, declared = match.group(1), match.group(2)
    assert declared != "None", "smoke must be a registered tier"
    assert selected == declared, (
        f"selected={selected} declared={declared} — the assertion must count "
        f"items AFTER marker deselection, not the pre-deselection total "
        f"(full stdout:\n{result.stdout})"
    )
    assert result.returncode != 4, (
        f"exit 4 means pytest.UsageError fired, i.e. a genuine count "
        f"mismatch slipped past the assertions above "
        f"(stdout:\n{result.stdout})"
    )
