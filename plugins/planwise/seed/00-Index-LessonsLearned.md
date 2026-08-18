# Lessons Learned Index

**Purpose:** Central index and taxonomy reference for all lessons learned.
**Last Updated:** YYYY-MM-DD
**Companion:** [00-Categorization-By-Domain.md](00-Categorization-By-Domain.md) — domain bucketing view, sync'd by `/planwise lessons curate`.

---

## Naming Convention

**Format:** `LL-{NNN}-{Domain}-{Name}.md`

| Component | Description | Example |
|-----------|-------------|---------|
| `LL` | Lessons Learned prefix | LL |
| `{NNN}` | Global sequence number (zero-padded to 3 digits) | 001, 023 |
| `{Domain}` | Abbreviation from config.yaml (`abbreviations` + `lesson_abbreviations`) | DOC, TOOL |
| `{Name}` | PascalCase descriptive name | QueryFilterTranslation |

**Next available ID:** LL-001

---

## Status Definitions

| Status | Meaning |
|--------|---------|
| `documented` | Captured; not yet owned by any backlog item. |
| `promoted` | Fully captured into actionable backlog item(s); archived; awaiting landing; the backlog item is the live owner. **archived ≠ landed.** |
| `applied` | Lesson applied to improve a process or pattern |
| `rule` | Lesson promoted to a `.claude/` artifact |
| `orphaned` | Content was fully captured into an owning item that has since closed without landing it, and no live item currently owns it. Work-surfacing: resurfaces ahead of `documented` in the next promotion pass. |

---

## Quick Reference

| Action | How |
|--------|-----|
| Find lessons by tag | `/lessons python regex` |
| Find by domain | `/lessons myproject` |
| Find by category | `/lessons anti-pattern` |
| List all lessons | `/lessons` (no arguments) |
| Create new lesson | Use template below, next ID = LL-001 |

---

## Master Table

| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status |
|----|-------|----------|----------|----------|------------|--------|--------|--------|
| | | | | | | | | |

---

## Lesson File Template

```yaml
---
id: LL-{NNN}
title: {Descriptive title}
date: {YYYY-MM-DD}
source: {session reference}
category: {anti-pattern | pattern | process}
severity: {low | medium | high}
language: [{python | csharp | javascript | ...}]
technology: [{specific tech}]
domain: [{project domains}]
status: documented
applied-as: null
promotion-target: [rule|code|claude-md|agent|skill|settings]   # one or more target types; multi-value = coarse / split-candidate
# promoted-to:                                                  # owning backlog item id(s), e.g. BB-{NNN}; set at capture-archive
# rule-as:                                                      # DEPRECATED alias for applied-as — read for back-compat, never written
---

# LL-{NNN}-{Domain}: {Same title as frontmatter}

## Context

{What happened — specific file, function, input, error.}

## Lesson

{The insight or fix. Include WRONG/CORRECT code examples for anti-patterns.}

## Applies To

{When this lesson is relevant — technologies, file patterns, scenarios.}
```

### Pointer Fields — Authoritative Definition

Two frontmatter fields answer two different questions. This table is the single source of truth for their meaning; every other document that mentions them defers here rather than restating the semantics.

| Field | Answers | Value form | Written when |
|-------|---------|-----------|--------------|
| `promoted-to:` | **Who owns the work?** | Backlog item id(s) — `BB-{NNN}`, listing every owner when a lesson decomposed across several items | At capture-archive, when the lesson becomes owned |
| `applied-as:` | **Where did it land?** | Path(s) to the artifact(s) actually created — a scalar, or a YAML list when a lesson landed in several files | At landing, replacing `null` or a `PENDING:BB-{NNN}` marker |

`applied-as:` is the artifact pointer for **both** terminal statuses (`rule` and `applied`) — the `status:` field, not a second pointer key, records which kind of landing it was.

> [!constraint] `rule-as:` is deprecated — read it, never write it
> An older scheme inverted these two fields: `applied-as:` held the owning backlog item and a separate `rule-as:` held the artifact. That scheme is superseded. Tooling MUST still **read** `rule-as:` so pre-existing lessons keep resolving, but MUST NOT **write** it, and MUST NOT treat its presence as an error.
>
> Migrating a legacy lesson is a **value remap between two keys, not a key rename**: the artifact path moves from `rule-as:` into `applied-as:`, and whatever `applied-as:` previously held (an owning backlog item) moves into `promoted-to:` — normalised to id form, since a stored path to a backlog item breaks as soon as that item is archived. Preserve a list-valued pointer as a YAML list; do not flatten it to a delimited string.
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

---

## Archive

A lesson is moved to `Archive/` when **fully captured** — either single-promote (→ `applied`/`rule`) or promote-batch (→ `promoted`). Archived lessons remain searchable via `/lessons <terms>` (search globs recurse into `Archive/`).

**Location:** `{lessons-dir}/Archive/`

---

## Rule Promotion Log

| Date | Lesson ID | Artifact Created | File |
|------|-----------|-----------------|------|
| | | | |

---
