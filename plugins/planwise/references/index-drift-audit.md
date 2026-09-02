---
description: Canonical procedure for auditing a planwise index (plans / backlog / lessons) for drift against its source of truth — script invocation, JSON result shape, banner, and the write-on-consent reconcile flow every caller shares.
---

# Index Drift Audit

A planwise index (the plans index, the backlog index, the lessons index) is a denormalized cache of a fact whose source of truth lives elsewhere — a Master Plan's own `Status:` field, a backlog item's on-disk location, or the highest lesson ID that exists anywhere. Nothing re-checks the cache against its source between the routine writes that keep it current, so it can drift stale between them. Every caller of this procedure runs the SAME read-only detect pass against a different index and offers the SAME write-on-consent reconcile; none re-implements another's comparison.

## Invocation

Standalone detect pass, read-only — writes nothing unless the caller's user explicitly consents to reconcile (below):

```bash
python "{plugin_root}/scripts/{reconcile_script}" --config "{planwise_root}/config.yaml" --json
```

Read the JSON file at the path it prints (`JSON: {path}`), shaped `{"drifts": [...], "anomalies": [...]}` (the lessons binding adds a `next_id` key — see Per-Index Bindings). `drifts` are rows out of sync with the source of truth; `anomalies` are rows whose source cannot be resolved at all (deleted/renamed — reported, never fabricated).

## Result Classes

| Class | Generic meaning | Ever auto-healed? |
|-------|------------------|--------------------|
| `drift` | A row (or, for lessons, the single counter) is out of sync with its source of truth | Yes — on explicit consent via `--write`, and only for rows still drifted at write time |
| `anomaly` | The row's source cannot be resolved (linked file/plan not found, or a file exists with no index row) — a data-integrity signal, not a stale-cache signal | Never — reported only, so nothing is fabricated |

## Monotonic Sequences Heal Forward Only

The two Result Classes above are safe to apply symmetrically only for a certain kind of cached field, and the distinction decides whether a two-way sync is safe at all. Some cached fields describe **current state** — a status, a file location — and heal safely in either direction: the source of truth is unambiguous, and a wrongly-healed value is recoverable by re-running the audit. A field holding the **next value of an allocation sequence** is not a description of state. It is a *promise about future writes*, and the two directions of disagreement mean opposite things:

| Stated vs computed | What it means | Safe to auto-correct? |
|---|---|---|
| Counter **behind** the max | A record was created outside the one writer that bumps the counter | **Yes** — the next write would otherwise collide |
| Counter **ahead** of the max | An identifier was allocated and later withdrawn | **No** — lowering it re-opens a retired identifier |

The consequence is what makes the asymmetry load-bearing: cross-references outlive the record itself. Archived records, promotion logs, commit messages and prose go on naming a retired number, so reissuing it silently repoints every one of them at different content. Nothing errors — the citations simply become false. Lowering is the dangerous direction precisely because it looks like tidying.

**Encode the asymmetry in the classification, not only in the write path**, so the read-only report says the right thing too. A reconciler that classifies both directions as `drift` and merely declines to write one of them still tells its reader that a counter ahead of the max is a stale cache, which is the opposite of true.

WRONG — one comparison, one disposition; a later `--write` heals whatever the detect pass called drift:
```python
if stated != computed:
    drift.append(...)
```
CORRECT — the comparison splits, and only one branch is ever healable:
```python
if stated < computed:
    drift.append(...)      # healable: heal FORWARD on consent, after the pre-write re-read
elif stated > computed:
    anomaly.append(...)    # reportable ONLY — never written, whatever consent was given
```

Two corollaries:

- **A record present in the ledger but missing on disk still bounds the counter.** Its identifier was issued, so excluding it from the max would hand the same number out again. Report the missing file as an anomaly **and** keep its identifier in the max — the two dispositions are independent, and only doing the first re-opens the number.
- **Never heal an anomaly automatically.** Drift has one correct resolution derivable from the data; an anomaly is a disagreement between sources where deciding which side is right needs a human. *A reconciler that heals anomalies has stopped reconciling and started guessing.*

> [!practice] Review prompt for a reconciler spec
> When a spec says "compute the correct value and correct the field to it", ask what the computed value being **lower** than the stated one would mean, and whether anything downstream still names what would be reissued. A spec that reads symmetrically in both directions usually has not been asked the question.

The Lessons binding below is the worked instance: its `drift` class is defined as the counter being *behind* the true next ID, `counter_ahead` is an anomaly kind that is never healed, and `row_without_file` keeps a missing record's ID inside the max.

## Banner

```
planwise {command} — {index} index {qualifier }drift audit

Drift detected ({K} row(s) out of sync):
  ! {row-identifier}: {index-value}  ->  {source-value}

Anomalies ({N}):
  ? {row-identifier}: {reason}
```

If both are empty: `No drift detected. {index} matches its source of truth.` `{command}` is the invoking handler (`doctor`, `list`, `backlog`); `{index}` and the row/value wording take the per-index binding below. `{qualifier}` is optional and is omitted entirely (along with the trailing space) for a plain row-drift audit; when present it names the audit's sub-kind — e.g. `archival ` (backlog archival state-coupling) or `counter ` (lessons-index counter drift) — immediately before `drift audit`.

## Write-on-Consent

After reporting, the caller MAY offer to reconcile via `AskUserQuestion` (prompt wording is the per-index binding's). On agreement, run the `--write` counterpart:

```bash
python "{plugin_root}/scripts/{reconcile_script}" --config "{planwise_root}/config.yaml" --write
```

The script re-reads the index immediately before writing (race-safe against a concurrent update to the index elsewhere), reconciles only rows still drifted, and never touches an anomaly row. Report `Reconciled {N} row(s).` Declining leaves the index untouched — the report above already recorded what was found.

## Per-Index Bindings

### Plans — `reconcile_plans.py`

- Source of truth: each row's Master Plan `Status:` field.
- Drift: index `Status` ≠ Master Plan `Status`. Row identifier: `{ABBR}`.
- Anomaly: Master Plan not found at the row's linked path.
- Banner drift line: `{ABBR}: index={X}  ->  Master Plan={Y}`.
- Consent prompt: "Reconcile {K} drifted row(s) in the plans index to match their Master Plan status?"

### Backlog — `reconcile_backlog.py`

- Source of truth: the on-disk location of each closed item's file. Archival is **state-coupled, not transition-coupled**: a COMPLETE/CLOSED item's file must live under `Archive/` with its index link repointed there.
- Drift: a closed row whose file is not archived, or whose index link is not repointed. Row identifier: `{ID}`.
- Anomaly: the linked file exists in neither the top-level index dir nor `Archive/`.
- Banner drift line: `{ID} ({STATUS}): {file} — {reason}`.
- Consent prompt: "Archive {K} stranded closed row(s) — move the file(s) into `Archive/` and repoint the index link(s)?"

### Lessons — `reconcile_lessons.py`

- Source of truth: the highest lesson ID that exists anywhere across the lessons dir and its `Archive/`.
- Drift: the index's `**Next available ID:** LL-{NNN}` counter is BEHIND the true next ID — at most one entry, since the counter is a single field. Reconcile moves the counter FORWARD only; it never lowers it.
- The JSON additionally carries a `next_id` key (`"LL-NNN"`) — the value the plans/backlog shape omits.
- Anomalies cover four separate conditions, none ever healed automatically:

  | Anomaly `kind` | Meaning |
  |----------------|---------|
  | `missing_counter_line` | The index carries no "Next available ID:" line — nothing to reconcile against; never fabricated at a guessed position |
  | `counter_ahead` | The counter is above the true next ID — an ID may have been retired deliberately, and lowering it would let a later capture reuse an ID that cross-references still name |
  | `row_without_file` | A master-table row whose lesson file exists in neither the lessons dir nor `Archive/` (deleted/renamed — reported, never fabricated). Its ID still bounds the counter: a retired ID is not free for reuse |
  | `file_without_row` | A lesson file on disk with no master-table row — the same off-capture authoring signal from the other direction |

- Banner drift line: `stated {STATED} — expected {EXPECTED}: {reason}`.
- Consent prompt: "Bump the lessons-index counter from {STATED} to {EXPECTED}?"
- A stale counter is worth surfacing beyond the number itself: it means some lesson was authored off the capture path, so that lesson's master-table row and its categorisation entry were hand-made too and may carry their own gaps. Say so in the report rather than presenting the bump as a bookkeeping nit.
- The `--write` run rewrites only the counter line's digits — every other line and the file's original line endings are preserved.

---

*Consumed by [`handlers/doctor.md`](../handlers/doctor.md) Stages 11/12/13 (all three index bindings, always-on — no `--no-check` escape hatch), [`handlers/list.md`](../handlers/list.md) (plans), [`handlers/backlog.md`](../handlers/backlog.md) (backlog) and [`lessons-curate-workflow.md`](lessons-curate-workflow.md) (lessons) — each citing this canonical instead of restating the detect/reconcile flow.*
