---
id: 506
title: "Backlog migration restore-on-failure rewrites files with a plain write_bytes, so a kill can truncate them"
priority: Medium
status: NOT_STARTED
abbrev: BUG
created: 2026-10-10
blocks: []
route_hint: A
route_evidence: "one function, one write call; the temp-then-replace pattern already exists in the same session's config.yaml write"
route_dated: 2026-10-10
---

# BB-506-BUG-MigrationRestoreOnFailureNotAtomic: Backlog migration restore-on-failure rewrites files with a plain write_bytes, so a kill can truncate them

**Priority:** Medium
**Domain:** BUG
**Source:** UpgradeRunDefects session URD-S02-02 review, closed 2026-10-10, plugin commit a8ba06c on branch 1.0.5.3

---

## Summary

When the backlog migration fails after writing, `_write_failed` puts every touched file back to its pre-run bytes. It does this with `Path.write_bytes`. That call truncates the target and then writes. A kill, power loss or crash between the truncate and the write completing leaves a truncated file. The restore path is the last line of defence, so it must not be able to destroy the file it restores.

## Problem

**Evidence:** `_write_failed` restores with a plain `write_bytes` — verified 2026-10-10 by Grep for `def _write_failed|write_bytes` in `cloned-repos/planwise/plugins/planwise/scripts/backlog_migration.py`, which returned lines 378 and 387.

Current code (`backlog_migration.py`, lines 378-392 at commit a8ba06c):

```python
def _write_failed(report, pre: dict, fix: str) -> None:
    """State `write_failed`, after putting every path back to its pre-image: rewrite a changed
    file and delete one this run created. If that restore fails, `detail` names the backups."""
    report.state, report.fix = "write_failed", fix
    try:
        for path, data in pre.items():
            if data is None:
                path.unlink(missing_ok=True)
            elif not path.is_file() or path.read_bytes() != data:
                path.write_bytes(data)
    except OSError as exc:
        report.detail += f"\nrestore failed ({exc}); the tree is partly written -- restore it from {report.backup_dir}"
        report.fix = f"copy the backed-up files back from {report.backup_dir} by hand, {RERUN}"
        return
    report.detail += "\nthe tree was restored: every file this step touched is back to its pre-run bytes"
```

Session URD-S02-02 made the `config.yaml` write atomic (write a temp file in the same directory, then `os.replace`). The shared restore path was outside that session's findings and still uses the non-atomic call.

Scope of the exposure: the backup directory named in `report.backup_dir` still holds the pre-run bytes, so data is recoverable by hand. The defect is that a truncated live file can look like a valid but empty or partial index, hub or item file until the user notices.

## Proposed Solution

Restore each file through a helper that writes `data` to a temp file in the same directory as `path`, flushes and fsyncs it, then calls `os.replace(tmp, path)`. Clean up the temp file in a `finally` if the replace did not happen. Reuse the helper the config.yaml write already uses if it can be shared, rather than adding a second copy.

Keep the existing behaviour unchanged:
- A `None` pre-image still deletes the path with `unlink(missing_ok=True)`.
- An unchanged file is still skipped.
- Any `OSError` still ends in the `restore failed` detail that names `report.backup_dir`.

## Acceptance Criteria

- [ ] `_write_failed` no longer calls `write_bytes` on a live path; restore goes through a same-directory temp file and `os.replace`
- [ ] A test patches `os.replace` (or the temp write) to raise mid-restore and asserts the original live file is not truncated and the `restore failed` detail still names the backup directory
- [ ] The existing restore tests pass unchanged: changed file rewritten, created file deleted, unchanged file untouched
- [ ] A Grep for `write_bytes` in `backlog_migration.py` finds no live-path restore call
- [ ] The full plugin suite passes, run as `python -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests`, with zero collected node ids outside `cloned-repos/planwise/tests`

## Related

- [BB-477-01-BUG-MigrationRefusalsAndBackupCleanup.md](BB-477-01-BUG-MigrationRefusalsAndBackupCleanup.md) - earlier hardening of the same migration's refusal and backup paths
- UpgradeRunDefects session URD-S02-02, plugin commit a8ba06c - the session that made the config.yaml write atomic

---

*Created: 2026-10-10*
