---
id: 900
title: "The export helper writes its summary file even when the row list is empty"
priority: Low
status: NOT_STARTED
abbrev: BUG
created: 2026-10-30
blocks: []
route_hint: A
route_evidence: "one function in one file; the current code is quoted and the replacement is described in prose"
route_dated: 2026-10-30
---

# BUG-900-ExportHelperWritesEmptySummary: The export helper writes its summary file even when the row list is empty

**Priority:** Low
**Domain:** BUG (report export)
**Surfaced by:** a hand run of the export on an empty backlog

---

## Summary

`write_summary` in `scripts/export_report.py` creates `summary.md` for every run. A run with no rows leaves a file that holds a heading and nothing else. A reader then takes the empty file for a finished report.

## Problem

The helper opens the output path before it looks at the rows. The current code reads:

```python
def write_summary(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Summary\n\n")
        for row in rows:
            handle.write(f"- {row['id']}: {row['title']}\n")
    return len(rows)
```

Three callers use the return value. Each one treats `0` as "nothing to report" and prints a note. None of them removes the file, so the note and the file disagree.

The fixture is the one case that matters: an empty `rows` list. A list with one row already writes a correct file.

## Proposed Solution

Return `0` from `write_summary` before the file is opened when `rows` is empty. The function then creates no file for an empty list, and the three callers keep their note.

The change is one early return at the top of the function. The loop and the heading stay as they are. The callers need no edit, because they read only the return value.

## Acceptance Criteria

- [ ] `write_summary` returns `0` and creates no file when `rows` is empty.
- [ ] `write_summary` writes the same file as today when `rows` holds one or more rows.
- [ ] The export tests pass.

## Files Touched

| Path | Role | Notes |
|------|------|-------|
| `scripts/export_report.py` | EDIT | `write_summary` only |
| `tests/test_export_report.py` | EDIT | one test for the empty list |

## Related

- None.

---

*Created: 2026-10-30*
