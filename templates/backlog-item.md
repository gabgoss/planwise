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
| `title` | string | Yes | Feature name, quoted if contains special chars |
| `priority` | enum | Yes | `High`, `Medium`, or `Low` |
| `status` | enum | Yes | `NOT_STARTED` for new items |
| `abbrev` | string | Yes | Domain code (see config.yaml) |
| `created` | date | Yes | ISO 8601 date (YYYY-MM-DD) |
| `blocks` | list | Yes | IDs of items this blocks (empty `[]` if none) |

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
**Status:** NOT_STARTED
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

---

## Notes

- **YAML frontmatter is the machine-readable source** used by `score_backlog.py` for scoring
- **Bold-colon metadata in body is preserved** for human readability
- Both coexist — YAML drives automation, body drives readability
- `blocks` in YAML lists numeric IDs: `blocks: [004, 007]`
- For bug items, include "Bug" or "Fix" in the title (activates scoring bonus)
- Optional sections: `## Dependencies`, `## Implementation Notes`, `## Constraints`
- Footer `*Created: {date}*` should match the YAML `created` field
