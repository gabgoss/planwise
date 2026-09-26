---
description: Canonical procedure for auditing a planwise index (plans / backlog / lessons) for drift against its source of truth — script invocation, JSON result shape, banner, and the write-on-consent reconcile flow every caller shares.
---

# Index Drift Audit

A planwise index (the plans index, the backlog index, the lessons index) is a denormalized cache of a fact whose source of truth lives elsewhere — a Master Plan's own `Status:` field, a backlog item's on-disk location, or the highest lesson ID that exists anywhere. A cache can also sit inside the file that holds its source: a legacy body status line in a backlog item repeats the item's frontmatter `status:`. Nothing re-checks the cache against its source between the routine writes that keep it current, so it can drift stale between them. Every caller of this procedure runs the SAME read-only detect pass against a different index and offers the SAME write-on-consent reconcile; none re-implements another's comparison.

## Invocation

Standalone detect pass, read-only — writes nothing unless the caller's user explicitly consents to reconcile (below):

```bash
python "{plugin_root}/scripts/{reconcile_script}" --config "{planwise_root}/config.yaml" --json
```

A binding may add a mode flag to this command line and to its `--write` counterpart, as the body-status binding adds `--body-status`.

Read the JSON file at the path it prints (`JSON: {path}`), shaped `{"drifts": [...], "anomalies": [...]}` (the lessons binding uses a different shape entirely — see Per-Index Bindings). `drifts` are rows out of sync with the source of truth; `anomalies` are rows whose source cannot be resolved at all (deleted/renamed — reported, never fabricated).

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

The Lessons binding below is the worked instance: its `drift` class is defined as the counter being *behind* the true next ID, `counter_ahead` is an anomaly kind that is never healed, and `extra-row` keeps a missing record's ID inside the max.

## Banner

```
planwise {command} — {index} index {qualifier }drift audit

Drift detected ({K} row(s) out of sync):
  ! {row-identifier}: {index-value}  ->  {source-value}

Anomalies ({N}):
  ? {row-identifier}: {reason}
```

If both are empty: `No drift detected. {index} matches its source of truth.` `{command}` is the invoking handler (`doctor`, `list`, `backlog`); `{index}` and the row/value wording take the per-index binding below. `{qualifier}` is optional and is omitted entirely (along with the trailing space) for a plain row-drift audit; when present it names the audit's sub-kind — e.g. `archival ` (backlog archival state-coupling), `body-status ` (backlog item body status lines) or `counter ` (lessons-index counter drift) — immediately before `drift audit`. The body-status binding audits item files rather than an index, so its banner names `backlog item` where the template names `{index} index`.

## Write-on-Consent

After reporting, the caller MAY offer to reconcile via `AskUserQuestion` (prompt wording is the per-index binding's). On agreement, run the `--write` counterpart:

```bash
python "{plugin_root}/scripts/{reconcile_script}" --config "{planwise_root}/config.yaml" --write
```

The script re-reads the index immediately before writing (race-safe against a concurrent update to the index elsewhere), reconciles only rows still drifted, and never touches an anomaly row. Report `Reconciled {N} row(s).` Declining leaves the index untouched — the report above already recorded what was found. The two backlog bindings are the exceptions. Each `--write` re-scans item files and never edits the index. The archival binding moves closed item files into `Archive/` and reports `Moved {N} file(s) to Archive/.` The caller then regenerates the index — see [Backlog — `reconcile_backlog.py`](#backlog--reconcile_backlogpy). The body-status binding strips drifted lines in place and reports `Stripped {N} body status line(s).` No regeneration follows a strip — see [Backlog item body status — `reconcile_backlog.py --body-status`](#backlog-item-body-status--reconcile_backlogpy---body-status).

## Per-Index Bindings

### Plans — `reconcile_plans.py`

- Source of truth: each row's Master Plan `Status:` field.
- Drift: index `Status` ≠ Master Plan `Status`. Row identifier: `{ABBR}`.
- Anomaly: Master Plan not found at the row's linked path.
- Banner drift line: `{ABBR}: index={X}  ->  Master Plan={Y}`.
- Consent prompt: "Reconcile {K} drifted row(s) in the plans index to match their Master Plan status?"

### Backlog — `reconcile_backlog.py`

- Source of truth: each item file's frontmatter `status:` compared with the file's location. The audit reads item files, never an index, so it works the same on a generated index and a legacy one. Archival is **state-coupled, not transition-coupled**: a COMPLETE/CLOSED item's file must live under `Archive/`. The generator renders each File link from wherever the file sits, so the file's location is the one fact to audit.
- Drift: a COMPLETE/CLOSED item file in the top-level backlog dir. Row identifier: `{ID}`.
- Anomaly: an open item file inside `Archive/`, a file with no readable frontmatter status, two files carrying one id, or a closed file whose name already exists in `Archive/`. None of these files is ever moved.
- Banner drift line: `{ID} ({STATUS}): {file} — {reason}`.
- Consent prompt: "Archive {K} closed item file(s) — move them into `Archive/`?"
- The `--write` run re-scans the item files and moves only files still drifted. It never edits or writes an index file. After a move, run `generate_backlog_index.py --write` so the index links follow the moved files. A legacy index's stale links are the migrator's concern, not this audit's.

### Backlog item body status — `reconcile_backlog.py --body-status`

- Source of truth: each item file's frontmatter `status:`, the item's only status field. The audit reads item files under `{backlog_dir}/` and its `Archive/`, never an index. It runs only when `--body-status` is on the command line. Without the flag, `reconcile_backlog.py` runs the archival binding above, unchanged. Plain `--help` does not list the flag, so this binding and the handlers that cite it are its only documentation. `--body-status --help` describes the mode.
- Invariant: an item file carries no `**Status:**` line in its header block. The header block is the run of lines after the first H1 (`# `) line that follows the frontmatter, up to the first line that is exactly `---` or starts with `## `. An older item writer can leave such a line under the title, and nothing keeps it in sync with frontmatter.
- Fenced code never counts. A fenced line is never the H1, never closes the header block, and is never a hit. The scanner follows the CommonMark fence rules:
  - An opener is 0-3 spaces of indent, then a run of 3 or more backticks or 3 or more tildes.
  - A backtick opener's info string holds no backtick.
  - A closer uses the opener's character, with a run at least as long, followed only by whitespace.
  - Inside a fence only a closer is checked. An unterminated fence runs to the end of the file.
- Drift: a header-block line that starts with `**Status:**` at column 0, whether or not it agrees with frontmatter. Row identifier: `{id}`. Each drift carries a `kind`. `disagrees` means the body value's first token differs from frontmatter `status:`. `redundant` means it agrees today. The comparison drops every `*` and backtick and any trailing `.,;:` from that token, and is case-insensitive. An empty body value is `disagrees`. Both kinds are drift, and both are stripped on consent.
- A file with no such line reports nothing: absence is the goal state, not an anomaly. A quoted or indented status line, a mid-line mention, and a near-miss bold form such as `**Status flip:**` never match.
- Anomalies cover five conditions, none ever stripped:

  | Condition | Reported reason |
  |-----------|-----------------|
  | The file cannot be read or decoded (`line` is `null`) | `file could not be read ({error}) — never stripped` |
  | A header-block status line in a file whose frontmatter `status:` cannot be read (`status` is `?`) | `header-block status line in a file whose frontmatter status cannot be read — never stripped` |
  | Two or more header-block status lines in one file | `{N} header-block status lines (lines {a, b}) — never stripped` |
  | No H1 title, and a column-0 status line outside a fence before the first `## ` heading | `no H1 title, so the header block is undefined, but a column-0 status line precedes the first ## heading — never stripped` |
  | A header-block status line that still holds a carriage return (`\r`) mid-line once its own line ending is removed | `status line holds a bare carriage return (\r) mid-line, so the reported value is not the whole line — never stripped` |

- Banner: `planwise {command} — backlog item body-status drift audit`. The script's drift header is `Body status drift detected ({K} header-block status line(s) to strip):`.
- Banner drift line: `  - {id} ({status}): {file} line {line} — body says {body_status} ({kind})`. An anomaly line is `  - {id} ({status}): {file} line {line} — {reason}`.
- With nothing to report the script prints `No body status drift detected. No item file carries a header-block status line.` When it finds anomalies but no drift, its no-drift line is `No body status drift detected.`
- Consent prompt: "Strip {K} body status line(s) from backlog item files ({D} disagree with frontmatter, {R} redundant)? Frontmatter is not changed."
- The `--body-status --write` run re-scans every item file at write time and strips only lines still drifted. It removes each drifted line together with its own line ending (`\n` or `\r\n`) and keeps every other byte. A drifted last line with no line ending loses only its own bytes. It never edits frontmatter, never touches an anomaly file, and never edits or writes an index.
- Each strip is an atomic write. The script writes a temporary file in the item's own directory, then replaces the item file with it (`os.replace`). A failed write removes the temporary file and leaves the item file unchanged.
- The run prints `  + {file}: stripped line {n}` for each stripped file, or `  ! {file}: {error}` for a failed one, then `Stripped {N} body status line(s).` Any failed write makes the script exit 1 and name each failed file on stderr.
- No index regeneration follows a strip. The index generator reads frontmatter only, and a strip never changes frontmatter.

### Lessons — `generate_lessons_index.py --check`

- Source of truth: lesson-file frontmatter is authoritative; the index (hub, overflow leaves, Archive shards) is a regenerated build artifact with exactly one writer, `generate_lessons_index.py --write` — there is no separate reconciler script for this index.
- This binding's mode flags differ from the generic form above: `--check` (this procedure's read-only detect pass — every report mode runs the full scan/render/compare pipeline, so `--check` is an explicit synonym for the default) and `--write` (write-on-consent, which regenerates the whole index rather than patching one row or one line).
- The JSON shape also differs from the generic `{"drifts": [...], "anomalies": [...]}`: `--check --json` prints `{"files": [...], "truncated": [...], "drift": [...], "anomalies": [...], "shape": ..., "basis": ...}` (note `drift`, singular, and the extra keys). Each finding is `{"class", "id", "detail"}`.
- The counter is a generated line with one writer, computed as `max(derived_next_id, on-disk counter)`: the generator reads the existing counter line only as a floor, so a retired id is never reissued. `stale-counter` fires when the on-disk counter is BELOW the computed value — ordinary drift, healed on `--write`. `counter_ahead` fires when it is ABOVE the computed value — an anomaly, never healed; an id may have been retired deliberately, and lowering it would let a later capture reuse an id that cross-references still name.
- File-level findings stay reportable:

  | `class` | Meaning | Ever healed? |
  |---------|---------|---------------|
  | `extra-row` | A generated row names an id with no lesson file on disk (neither the lessons dir nor `Archive/`) | Yes — the next full `--write` rebuilds the index from lesson files, so the stray row does not survive |
  | `missing-row` | A lesson file exists with no generated row yet — the same off-capture authoring signal from the other direction | Yes — added on the next `--write` |
  | `duplicate-id` | Two lesson files claim one id, or one id has two rows | No — `--write` refuses (exit 2) until resolved; deciding which file is correct needs a human |
  | `id-mismatch` | A lesson file's filename number disagrees with its own frontmatter `id:` | No — `--write` refuses (exit 2) until resolved |
  | `row-shape` | A row's cell count disagrees with the header | No — reported only |
  | `location-anomaly` | A lesson's directory disagrees with its status | No — location is never a routing input; the generator never moves a file |

- Banner drift line: `{class}: {id} — {detail}`, per the finding shape above.
- Consent prompt: "Regenerate the lessons index to resolve {K} drifted finding(s)?" — `--write` on the reconciler prints the regenerate command rather than editing any single row or line; there is no per-row heal.
- A stale counter is worth surfacing beyond the number itself: it means some lesson was authored off the capture path, so that lesson's generated-index row and its categorisation entry were hand-made too and may carry their own gaps. Say so in the report rather than presenting the regenerate as a bookkeeping nit.

---

*Consumed by [`handlers/doctor.md`](../handlers/doctor.md) Stages 11/12/13 and 19 (all four bindings, always-on — no `--no-check` escape hatch), [`handlers/list.md`](../handlers/list.md) (plans), [`handlers/backlog.md`](../handlers/backlog.md) (both backlog bindings, each skippable with `--no-check`) and [`lessons-curate-workflow.md`](lessons-curate-workflow.md) (lessons) — each citing this canonical instead of restating the detect/reconcile flow.*
