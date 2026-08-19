import sys

sys.dont_write_bytecode = True  # MUST precede any import of plugins/planwise/scripts
# `pytest -c evals/pytest.ini` re-roots pytest at evals/, so conftest collection
# is cut at this dir's rootdir and the repo-root conftest.py never loads. Without
# this line first, importing anything through this ini's `pythonpath` entry
# drops plugins/planwise/scripts/__pycache__/ inside the shipped subtree — a
# silent ship-boundary violation reaching every consumer of the marketplace
# artifact. This file is the only thing standing between an import and that.

import argparse
import os
import platform
import shutil
import subprocess

import pytest

from harness import tiers

# --- Responsibility 2: the CLI gate -----------------------------------------
# Resolved once per session, the same way context_calibration.py's own probe
# does: PowerShell's own PATH lookup on Windows, `shutil.which` on POSIX.


def _resolve_cli() -> str | None:
    if platform.system() == "Windows":
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-Command claude -ErrorAction SilentlyContinue).Source",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        path = proc.stdout.strip()
        return path or None
    return shutil.which("claude")


_CLI_PATH: str | None = _resolve_cli()
_REQUIRE_CLI: bool = bool(os.environ.get("PLANWISE_EVAL_REQUIRE_CLI"))


def pytest_configure(config: pytest.Config) -> None:
    """Strictness is an explicit environment opt-in; the count is always
    visible either way.

    - PLANWISE_EVAL_REQUIRE_CLI unset (default): a missing CLI is handled
      per-module by `require_cli()` below (skip, reason named) — a
      contributor without credentials gets a green run and an honest SKIP
      count instead of a hard failure.
    - PLANWISE_EVAL_REQUIRE_CLI=1: a missing CLI is a hard collection
      error here, immediately. On a release gate, "zero evals ran" silently
      passing is worse than a red build.
    """
    if _CLI_PATH is None and _REQUIRE_CLI:
        raise pytest.UsageError(
            "PLANWISE_EVAL_REQUIRE_CLI is set but the `claude` CLI was not "
            "found on PATH. Refusing to collect — a release gate must not "
            "report a green run with zero evals actually invoked."
        )


def require_cli() -> str:
    """Call this at MODULE level (not inside a fixture or test function) in
    an eval case file, so a missing CLI skips the whole file at collection
    time rather than failing one test at a time:

        from conftest import require_cli
        CLI_PATH = require_cli()

    `evals/` is on `sys.path` (this ini's `pythonpath` entry includes `.`),
    so the plain `from conftest import ...` form resolves from any file
    under `evals/`.
    """
    if _CLI_PATH is None:
        pytest.skip(
            "`claude` CLI not found on PATH — skipping (set "
            "PLANWISE_EVAL_REQUIRE_CLI=1 to make this a hard failure instead "
            "of a skip).",
            allow_module_level=True,
        )
    return _CLI_PATH


# --- Responsibility 3: the tier-count assertion -----------------------------
# After marker-based selection, compare the selected count against
# harness/tiers.py's declared count for the requested marker expression. A
# mismatch — including a zero selection — fails loudly. `EVALS SELECTED` is
# printed regardless of mode, so a skip that reports 0/m stays visible
# instead of looking like a tier that simply passed.
#
# This lives in `pytest_collection_finish`, not `pytest_collection_modifyitems`.
# `pytest_collection_modifyitems` is the SAME hookspec pytest's own `-m`
# marker deselection uses, and pluggy calls every implementation of a
# hookspec in an order this file does not control — an earlier version put
# the assertion there and it ran BEFORE the built-in deselection had
# filtered `items`, so it compared the pre-deselection total against the
# declared tier count (observed: 90 selftests reported for a 4-row `smoke`
# tier). `pytest_collection_finish` is a separate hookspec that fires only
# after collection, including every `pytest_collection_modifyitems`
# implementation, has finished — `session.items` there is the final,
# marker-filtered set regardless of hook registration order.


def pytest_collection_finish(session: pytest.Session) -> None:
    marker_expr = session.config.option.markexpr or ""
    declared = tiers.declared_count_for(marker_expr)
    selected = len(session.items)
    tier_label = marker_expr if marker_expr else "(none — selftests only)"
    note = ""
    if declared == 0:
        # 0 selected / 0 declared satisfies the assertion below without
        # raising — but that must never read as "this tier ran and passed".
        # It means every family the tier covers has zero rows on disk yet.
        note = " — NOT YET AUTHORED, not a passing empty tier"
    print(f"\nEVALS SELECTED: {selected} / declared {declared} (tier={tier_label}){note}")
    if declared is None:
        # No tier is registered for this marker expression (e.g. the bare,
        # marker-less selftest invocation) — nothing to assert against.
        return
    if selected != declared:
        raise pytest.UsageError(
            f"EVALS SELECTED {selected} but harness/tiers.py declares "
            f"{declared} for marker expression {tier_label!r}. A tier that "
            "selects nothing, or a drifted count, must never look like a "
            "tier that passed."
        )


# --- Retention: the --eval-keep-failed option -------------------------------
# Registers the CLI flag the README documents, so passing it does not fail
# with pytest's "unrecognized arguments" error. Default matches the fixture
# engine's own teardown default (retain a failing case dir); pass
# `--no-eval-keep-failed` to opt into always tearing down.


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--eval-keep-failed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Retain the scratch case dir of a failing eval row for "
            "post-mortem instead of tearing it down (default: on). Passing "
            "rows are always torn down either way. Pass "
            "--no-eval-keep-failed to opt out."
        ),
    )


@pytest.fixture(scope="session")
def eval_keep_failed(pytestconfig: pytest.Config) -> bool:
    """Whether a failing case's scratch dir should be retained. A case
    passes this through to the fixture engine's own `teardown(...,
    keep_failed=...)` call rather than hardcoding the retention posture."""
    return bool(pytestconfig.getoption("--eval-keep-failed"))


# --- Responsibility 4: shared-envelope fixtures -----------------------------
# e1_envelope / e2_envelope (session-scoped) are NOT implemented by this
# sprint. The sprint that builds the fx-trivial-plan-git / fx-team-plan-git
# fixtures owns them and adds them here.
