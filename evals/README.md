# planwise eval suite

Drives a **live** `claude` CLI against the shipped `plugins/planwise` plugin
and grades what it actually does — plan structure, on-disk write sets,
containment, agent-dispatch envelopes. It spends real money and lives
outside the ship boundary: `./plugins/planwise` is the only tree the
marketplace copies, and nothing under `evals/` ever enters it.

This suite has its own `pytest.ini`. It is **deliberately unreachable** from
the repo-root `pytest.ini` — that file's `testpaths` stays `tests` on
purpose, so a bare `pytest` at the repo root never collects, and never
spends, a cent. Do not add `evals` to the root ini's `testpaths`; that would
turn this from an opt-in suite into a run-by-default one.

## Running it

Four invocation lines, cheapest first:

```
pytest -c evals/pytest.ini evals                                     # $0 (see note below)
pytest -c evals/pytest.ini evals -m "smoke"                          # 4 rows,  ~$0.59-1.03,   ~46-75 s
pytest -c evals/pytest.ini evals -m "smoke or full"                  # 53 rows, ~$16.38-26.98, ~28-54 min
pytest -c evals/pytest.ini evals -m "smoke or full or prerelease"    # 54 rows, ~$19.13-32.48, ~32-65 min
```

The `evals` path argument is not optional decoration: pytest scopes collection
to the invocation directory when cwd differs from the config's rootdir, and
`testpaths` does not override that. Omitting the argument from a `cloned-repos/planwise`
cwd collects the repo's own `tests/` directory instead (`norecursedirs = tests`
in `evals/pytest.ini` exists as a backstop against exactly that).

The marker-less form collects `evals/selftest/` **and** every live case row
under `evals/cases/` — `python_files` matches both — but stays $0 because of
two things holding together, not because the case rows are out of reach:
every case row self-skips from **inside its module-scoped `scratch` fixture**
when no explicit `-m` marker expression was passed, and the selftest that
regression-tests the tier-count gate runs its own nested marker-scoped pytest
with `--collect-only` rather than actually executing the rows it counts. If either half regresses
— a new case row without the skip guard, or a nested-subprocess selftest that
drops `--collect-only` — the bare form silently starts spending money again.

The guard belongs in the **fixture**, not the test body. Pytest resolves a
test's fixtures before entering its body, so a body-level skip runs only
after fixture setup has already built the scratch root, copied the plugin
subtree, and — for a template-based row — driven a live `init`. A row that
places its guard in the body is not $0.

`--strict-markers` is set: a typo'd `-m` expression is a hard error, not a
silent zero-selection.

## The three denominators

The suite's size is reported three different ways on purpose — they answer
different questions and are not interchangeable:

- **54 rows** — the deliverable. What the cost table above prices.
- **50 case dirs** — fixture-build effort. 54 rows minus the 4 rows that
  share another row's captured envelope (their fixture is already built).
- **54 CLI calls** — API spend. 50 base calls plus 4 idempotency second
  runs (cases that invoke the CLI twice inside one case dir to check
  re-run-in-place behavior).

## CI / release-gate composition

Ordered cheapest-and-most-deterministic first. Wiring this into an actual CI
config is out of scope here — this table is the deliverable, not a workflow
file:

| # | Step | When | Cost | Gate behaviour |
|---|---|---|---:|---|
| 1 | `claude plugin validate --strict` | every push | $0 | hard fail |
| 2 | `pytest` (root ini — `tests/` only, unchanged) | every push | $0 | hard fail |
| 3 | `pytest -c evals/pytest.ini evals` (selftests, no `-m`) | every push | $0 | hard fail |
| 4 | `pytest -c evals/pytest.ini evals -m "smoke"` | every push | ~$1 | hard fail if the CLI gate is satisfied; visible SKIP otherwise |
| 5 | `pytest -c evals/pytest.ini evals -m "smoke or full"` | branch touches `plugins/planwise/**` | ~$16-27 | hard fail |
| 6 | `pytest -c evals/pytest.ini evals -m "smoke or full or prerelease"` | release tag | ~$19-33 | hard fail; run with `PLANWISE_EVAL_REQUIRE_CLI=1` |

## The CLI gate

Strictness is an explicit environment opt-in; the selected count is always
visible either way:

- **`PLANWISE_EVAL_REQUIRE_CLI` unset (default):** a missing `claude` CLI or
  missing credentials produces a skip with the reason named — a contributor
  without credentials gets a green run and an honest SKIP count instead of a
  wall of failures.
- **`PLANWISE_EVAL_REQUIRE_CLI=1`:** a missing CLI is a hard collection
  error instead. Use this on a release gate — "zero evals ran" must never
  pass silently as green.
- Every run prints `EVALS SELECTED: n / declared m (tier=…)`, whether or not
  anything ends up skipped. A skip that reports `0/4` is visible; a silent
  zero is not.

## Shared-envelope `-k` hazard

Four rows (the `review`/agent-dispatch family) are graded off one captured
E1 or E2 envelope instead of an independent CLI call each — that's why rows
(54) exceeds case dirs (50) above: those four rows share a fixture instead
of building their own. The hazard: **`-k` filtering down to a single row
from one of these groups still pays the full invocation**, because the
session-scoped envelope fixture is what actually drives the CLI, not the
individual test. Running one row from a shared-envelope group costs the
same as running all of them. There is no cheap way to select "just one"
agent-dispatch assertion.

## Retention

By default, a failing row's scratch case dir is **retained** for
post-mortem instead of being torn down (`--eval-keep-failed`, on by
default). Pass `--no-eval-keep-failed` to tear down failing case dirs too.
Passing rows are always torn down, regardless of this setting.

## [BUDGET WATCH]

The T6 turn-weight class (full pipeline + a plan-authoring dispatch) is
**extrapolated, not yet measured** — one row, 15.3-17.7% of total suite
cost. It is a rate-probe candidate, not a trim target: there is no budget
pressure, and Tier R (`smoke or full or prerelease`) runs that row anyway,
so measuring it is free at the margin. Until it's measured, every Tier R
cost figure in this document carries a labelled uncertainty band on that one
row, and the T6 rate is never blended into a headline per-case figure as
though it were measured.
