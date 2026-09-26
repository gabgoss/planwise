---
description: The Lessons Learned index's generated contract — column layout, hub/overflow/Archive-shard membership and budgets, the changelog and promotion-log file contracts, status meanings, naming, the Pointer Fields definition, the title cap, and the one-writer rule. Every consumer of the generated index defers here.
---

# Lessons Schema

The lessons index (`{lessons_dir}/00-Index-LessonsLearned.md`) is a regenerated build artifact. Lesson-file frontmatter is the single source of truth; nothing is ever hand-edited into the index. This reference documents what `scripts/generate_lessons_index.py` actually produces, read from the shipped script rather than from any decision record — a rule authored from a decision table asserts what the decision said, not what shipped.

## Index Format

The generated hub, every overflow leaf, and every Archive shard render the same 10-column table:

```
| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status | File |
```

The header block sits above the table with no `## Master Table` heading — a generated hub carries no such heading at all:

```
Generated: {YYYY-MM-DD}
**Next available ID:** LL-{NNN}

```

The counter is `max(derived_next, the counter value already on disk)`, where `derived_next` comes from the id-scan the generator itself performs. The on-disk value is read only as a floor, never as a source of which ids are known, which makes the counter forward-only: retiring the highest-numbered lesson file lowers `derived_next`, but the next `--write` still floors at the value already shipped, so the counter itself never moves backward. A `--check` run reports an on-disk counter below the derived value as `stale-counter` drift, and one above it as a `counter_ahead` anomaly (an id may have been retired) — never as a healing target. The generator is the counter's only writer.

Two fixed footer pointers close every generated file:

```
[Changelog](00-Changelog-LessonsLearned.md)
[Promotion Log](00-PromotionLog-LessonsLearned.md)
```

Both filenames are derived from the hub's own configured name, never hardcoded — a project with a custom `index_files.lessons` gets footer pointers that agree with it. **The generator never writes either file.** It renders the two links and stops.

The `File` cell is `[NNN](relative path)`, computed from the directory of the generated file the row is rendered into. The same lesson file therefore renders a different relative path depending on which generated file holds the row — a hub row's path is relative to the lessons directory, an Archive-shard row's path is relative to its `Archive/` subdirectory.

## Hub, Overflow Leaves and Archive Shards

Hub membership is decided by frontmatter `status:` alone — `documented` or `orphaned` — **never** by which directory a file sits in. A lesson whose directory disagrees with its status (a hub-status lesson filed under `Archive/`, or a non-hub-status lesson left at top level) is reported as a `location-anomaly` and still routed by its status.

Every other status shards to an Archive century file by `(id - 1) // 100`, zero-indexed: ids 1-100 to one shard, 101-200 to the next, and so on.

| Family | Filename shape | Budget |
|---|---|---|
| Hub | `00-Index-LessonsLearned.md` | 12,500 tokens |
| Hub overflow leaf | `00-Index-LessonsLearned-{min}-{max}.md` (zero-padded ids) | 12,500 tokens, same family as the hub |
| Archive shard | `Archive/Index-LessonsLearned-{min}-{max}.md` | 22,000 tokens |

The hub-family budget is `HUB_TOKEN_BUDGET`; the Archive-shard budget is `READ_TOKEN_WARN`. Both are measured the same way: `_shipped_bytes` counts UTF-8 bytes plus one byte per line (the CRLF worst case), and that byte count is converted to tokens at `MEASUREMENT_BASIS` — `read_limits.estimate_tokens` at its default ratio, `DEFAULT_BYTES_PER_TOKEN = 2.6` bytes/token. Every file entry in a `--json` report carries its own `budget` and `page_cap_ratio`.

An overflow leaf exists only when the hub-family content will not fit one file under budget; each leaf carries a continuation backlink to the others in the same family. Every generated file's non-table content — the footer pointers, a `## Shards` directory line, a header cell, a continuation backlink — is compared as a whole against a fresh render on `--check`; a mismatch there (with no row-level cause) reports as `stale-wrapper`.

## Changelog Contract

`00-Changelog-LessonsLearned.md` opens with a backlink to the hub (`[← 00-Index-LessonsLearned.md](00-Index-LessonsLearned.md)`), then `## Entry N` sections newest-first. An archive part, when the current file grows past its budget, is linked both ways. The current entry replaces the previous value:

> **"Replace the previous value — do not preserve it. History belongs in a changelog file, not in this line."**

The generator's own footer-pointer contract governs this file's *name*, not its *content* — the generator emits the `[Changelog](...)` link and never creates, bootstraps, or writes to the changelog file itself. (This differs from the backlog generator's `--write` path, which bootstraps a missing changelog with a one-line header the first time; the lessons generator's `_cmd_write_lessons` has no equivalent step.) The changelog exists on disk because the installer seeds it (`copy_seed_files` / `_seed_lessons_index`) and because curate/promote-batch workflows append entries to it by hand.

## Promotion-Log Contract

The promotion log is **five files**, not one. Lessons 201 and above append to the hub-side file; 1-200 split by century, and the first century splits further because it runs too large for one file:

| File | Lesson ids |
|---|---|
| `Archive/PromotionLog-LessonsLearned-001-050.md` | 1-50 |
| `Archive/PromotionLog-LessonsLearned-051-075.md` | 51-75 |
| `Archive/PromotionLog-LessonsLearned-076-100.md` | 76-100 |
| `Archive/PromotionLog-LessonsLearned-101-200.md` | 101-200 |
| `00-PromotionLog-LessonsLearned.md` | 201 and above |

The append target is a pure function of the lesson id alone. Each file opens with a backlink to the hub; the hub-side file additionally lists the two-way links to every Archive part. The table is 4 columns (`Date | Lesson ID | Artifact Created | File`), and an append deduplicates by the `(lesson id, artifact)` pair.

> [!binding] This 5-way split is not yet implemented in the shipped generator
> `generate_lessons_index.py` computes only the hub-side filename (`_promotion_log_filename`, `00-PromotionLog-{X}{suffix}`) and, exactly like the changelog, never writes to any promotion-log file — confirmed directly in `_cmd_write_lessons`, which stages no promotion-log content. No shipped script implements the century-boundary append-target function this contract describes: a repo-wide grep for `PromotionLog-LessonsLearned` and for the boundary literals (`001-050`, `051-075`, `076-100`, `101-200`) under `plugins/planwise/` returns zero hits outside this reference and the generator's own filename derivation. `promotion_log.py` was explicitly not shipped by Session 03 (its own Recovery records the append-target function as deferred). This contract is authored from the design decision text because there is no shipped map to author it from instead — the usual "the script wins" rule has no script to defer to here. Treat the append-target function as a specification for a follow-up, not as observed behavior.

## Status Definitions

The value list is declared in `config.yaml` as `lesson_statuses:` (beside the backlog `statuses:`); this table defines what each value means.

| Status | Meaning |
|--------|---------|
| `documented` | Captured; not yet owned by any backlog item. |
| `promoted` | Fully captured into actionable backlog item(s); archived; awaiting landing; the backlog item is the live owner. **archived ≠ landed.** |
| `applied` | Lesson applied to improve a process or pattern |
| `rule` | Lesson promoted to a `.claude/` artifact |
| `orphaned` | Content was fully captured into an owning item that has since closed without landing it, and no live item currently owns it. Work-surfacing: resurfaces ahead of `documented` in the next promotion pass. |

`applied` and `rule` are the two terminal ("landed") statuses; they differ only in *what kind* of artifact absorbed the lesson, never in which pointer field records it — see Pointer Fields below, where `applied-as:` is the single artifact pointer for both.

## Quick Reference

Adapted from the seed for the generated shape — the `Create new lesson` row no longer names a fixed ID, since the counter is now generated, and the template lives in a sibling file rather than "below":

| Action | How |
|--------|-----|
| Find lessons by tag | `/planwise lessons python regex` |
| Find by domain | `/planwise lessons myproject` |
| Find by category | `/planwise lessons anti-pattern` |
| List all lessons | `/planwise lessons` (no arguments) |
| Create new lesson | Use `templates/lesson.md`; the next ID is the hub's generated `**Next available ID:**` line |

## Naming Convention

**Format:** `LL-{NNN}-{Domain}-{Name}.md`

| Component | Description | Example |
|-----------|-------------|---------|
| `LL` | Lessons Learned prefix | LL |
| `{NNN}` | Global sequence number (zero-padded to 3 digits) | 001, 023 |
| `{Domain}` | Abbreviation from config.yaml (`abbreviations` + `lesson_abbreviations`) | DOC, TOOL |
| `{Name}` | PascalCase descriptive name | QueryFilterTranslation |

## Archive

A lesson is moved to `Archive/` when **fully captured** — either single-promote (→ `applied`/`rule`) or promote-batch (→ `promoted`). Archived lessons remain searchable via `/lessons <terms>` (search globs recurse into `Archive/`).

**Location:** `{lessons-dir}/Archive/`

## Pointer Fields — Authoritative Definition

Two frontmatter fields answer two different questions. This table is the single source of truth for their meaning; every other document that mentions them defers here rather than restating the semantics.

| Field | Answers | Value form | Written when |
|-------|---------|-----------|--------------|
| `promoted-to:` | **Who owns the work?** | Backlog item id(s) — `BB-{NNN}`, listing every owner when a lesson decomposed across several items | At capture-archive, when the lesson becomes owned |
| `applied-as:` | **Where did it land?** | Path(s) to the artifact(s) actually created — a scalar, or a YAML list when a lesson landed in several files | At landing, replacing `null` or a `PENDING:BB-{NNN}` marker |

`applied-as:` is the artifact pointer for **both** terminal statuses (`rule` and `applied`) — the `status:` field, not a second pointer key, records which kind of landing it was.

> [!constraint] `rule-as:` is deprecated — read it, never write it
> An older scheme inverted these two fields: `applied-as:` held the owning backlog item and a separate `rule-as:` held the artifact. That scheme is superseded. Tooling MUST still **read** `rule-as:` so pre-existing lessons keep resolving, but MUST NOT **write** it, and MUST NOT treat its presence as an error.
>
> Migrating a legacy lesson is a **value remap between two keys, not a key rename**: the artifact path moves from `rule-as:` into `applied-as:`, and whatever `applied-as:` previously held (an owning backlog item) moves into `promoted-to:`, normalised to id form, since a stored path to a backlog item breaks as soon as that item is archived. Preserve a list-valued pointer as a YAML list; do not flatten it to a delimited string.
>
> WRONG — relabel one key and call it migrated:
> ```yaml
> status: rule
> applied-as: {backlog-dir}/BB-{NNN}-{SB}-{Domain}-{Topic}.md   # still the OWNER, now under the artifact key
> ```
> CORRECT — remap the values, then drop the legacy key:
> ```yaml
> status: rule
> applied-as: references/{artifact}.md §{N}                      # the artifact
> promoted-to: BB-{NNN}                                          # the owner
> ```

## Title Cap

The rendered `Title` cell is the frontmatter `title:` value, truncated to 120 characters (`TITLE_MAX_LEN`) at a word boundary — the cut lands on the last space at or before the limit, never mid-word, and never inside an escape sequence (truncation happens before pipe-escaping). A run that truncates one or more titles prints one stderr summary line naming the count, never a line per title:

```
N title(s) truncated at 120 characters; see --json "truncated" for ids
```

The truncated ids themselves are always available in `--json`'s `"truncated"` list. The full, untruncated title lives in the lesson body — the index cell is a pointer, not the record.

## The One-Writer Rule

The index is never hand-edited. Edit the lesson file, then run the generator:

```
python {plugin_root}/scripts/generate_lessons_index.py --config {config} --write
```

`--dry-run` (also the default with no mode flag) and `--check` both run the full scan → render → split → measure → compare pipeline and report drift/anomalies without writing anything; only `--write` can refuse before touching disk. Exit codes are shared across every mode:

| Exit | Meaning |
|---|---|
| 0 | Clean — no drift, no anomaly, no refusal |
| 1 | Drift or anomaly found (report modes only) |
| 2 | Refused — `--write` hit a duplicate id, a filename/frontmatter id mismatch, or a legacy-shaped on-disk hub without `--replace-legacy`; or any mode hit a missing required frontmatter key or an unshardable row |

`--replace-legacy` allows `--write` to overwrite a legacy-shaped hub (one carrying a `## Master Table` or `## Rule Promotion Log` heading) that would otherwise be refused.
