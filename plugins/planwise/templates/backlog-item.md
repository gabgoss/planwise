# Backlog Item Template

Use this template when creating new backlog items.

---

## YAML Frontmatter (REQUIRED)

Every backlog item file MUST start with YAML frontmatter:

```yaml
---
id: {XXX}
title: "{Feature Name}"
priority: {High|Medium|Low}
status: NOT_STARTED
abbrev: {ABBREV}
created: {YYYY-MM-DD}
blocks: []
---
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | integer | Yes | 3-digit backlog index number (e.g., 003) |
| `title` | string | Yes | Feature name, **at most 120 characters**, quoted if it contains special chars. The narrative belongs in the body (`## Summary`, `## Problem`, and `**Evidence:**` lines), never in the title |
| `priority` | enum | Yes | `High`, `Medium`, or `Low` |
| `status` | enum | Yes | `NOT_STARTED` for new items |
| `abbrev` | string | Yes | Domain code (see config.yaml) |
| `created` | date | Yes | ISO 8601 date (YYYY-MM-DD) |
| `blocks` | list | Yes | IDs of items this blocks (empty `[]` if none). The single source of truth for blocking — see Gating Mechanism below |
| `route_hint` | enum | No | `A`, `B`, or `C` — the filing author's provisional triage route (Direct Fix / Task List / Session Planning) |
| `route_evidence` | string | No | One line: why that route, from what the author verified live at filing time |
| `route_dated` | date | No | ISO 8601 date the route was judged. A stored route is a dated claim about the repository and rots like any other claim; the date makes that staleness visible at triage |

The three `route_*` fields are optional: an item without them is valid and scores normally, and triage derives its route from the live files exactly as it does for any item. When present they are a **recommendation, never a binding decision** — triage runs every one of its own gates regardless, and a hint that disagrees with the live signals, or whose `route_dated` predates the item's newest evidence, is data about drift, not an override.

### Status Values

| Status | When |
|--------|------|
| `NOT_STARTED` | Default for new items |
| `PLANNING` | Requirements gathering in progress |
| `IN_PROGRESS` | Active development |
| `BLOCKED` | Waiting on dependency |
| `COMPLETE` | Implemented and verified |
| `CLOSED` | Resolved without implementation |

---

## Body Structure

```markdown
# BB-{ID}-{Domain}: {Title}

**Priority:** {High|Medium|Low}
**Domain:** {ABBREV}

---

## Summary

{1-2 paragraph overview of what this item addresses}

## Problem

{Description of the problem or gap}

## Proposed Solution

{Description of the approach}

## Acceptance Criteria

- [ ] {Criterion 1}
- [ ] {Criterion 2}

## Related

- [{Related item}]({filename}.md) - {relationship description}

---

*Created: {YYYY-MM-DD}*
```

### Evidence Lines

Any claim in the body — in `## Problem`, `## Proposed Solution`, or elsewhere — that asserts a condition about the current repository carries an evidence line:

```
**Evidence:** {claim} — verified {YYYY-MM-DD} by `{command_or_query}`
```

The date makes staleness visible at triage; the command makes re-verification a copy-paste rather than a re-derivation. A date with no command is the shape that gets trusted instead of re-run.

### Gating Mechanism (Triage Pivots)

Pivot/triage blocking is declared in the umbrella item's `blocks:` frontmatter, and that field is the **single source of truth** for blocking. The index row's `Blocks` column is its generated projection, never a place to declare blocking: the index is a build artifact regenerated from item files, and a build artifact cannot be a source of truth. An umbrella item represents the pivot; its `blocks:` list records which items it blocks, and the index row's `Blocks` column shows the same list after the next regeneration. See `references/backlog-triage-pivot-detection.md` §2.1.

### Files Touched (Optional)

When an item's scope is understood well enough at filing time, list the files it expects to read, edit, or create:

```markdown
## Files Touched

| Path | Role | Size |
|------|------|------|
| `path/to/existing_file.py` | EDIT | 4.2 KiB / ~1.1K tok |
| `path/to/new_file.py` | CREATE | ~2K tok (estimate) |
```

`Role` is one of `READ` (context only), `EDIT` (modified), or `CREATE` (does not exist yet). Measure an existing file's size with `scripts/measure_files.py`; a `CREATE` row carries a flagged estimate, never a blank cell. This is a filing-time estimate, not a generated roll-up, and may be revised as scope firms up.

---

## Notes

- **YAML frontmatter is the machine-readable source** used by `score_backlog.py` for scoring
- **Frontmatter wins on all three metadata fields.** `priority`, `status`, and `abbrev` are read from YAML only. The body's `**Priority:**` and `**Domain:**` lines are decorative copies kept for human readability; no script maintains them, so whoever hand-edits `priority:` or `abbrev:` updates the matching body line in the same edit
- The `status` field lives in YAML frontmatter only. The body carries no separate status line, so there is nothing to fall out of sync
- `blocks` in YAML lists numeric IDs: `blocks: [004, 007]`
- Bug items carry `abbrev: BUG`. The scoring bonus keys on that field (rendered as the index `Domain` column), never on the title's wording
- Optional sections: `## Dependencies` (free-form prose only — this section does not drive blocked-ness; the machine-parsed blocking relationship is the `blocks:` frontmatter field, see Gating Mechanism above), `## Implementation Notes`, `## Constraints`, `## Files Touched` (the item's own read/edit/create surface — see Files Touched above)
- Footer `*Created: {date}*` should match the YAML `created` field
