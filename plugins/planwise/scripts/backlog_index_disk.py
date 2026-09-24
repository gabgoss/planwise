"""Backlog index disk access: lists on-disk generated files, detects their
line-ending convention, and writes the hub and shards as one atomic unit.

Re-exported unchanged by the `generate_backlog_index` facade.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_schema import IndexNaming, is_generated_index_file
from reconcile_common import read_text_preserving_newlines

def _list_disk_generated_files(backlog_dir: Path, archive_dir: Path, naming: IndexNaming) -> list:
    """Every on-disk file matching `is_generated_index_file` under `naming`
    (Finding F5 -- the project's real config-derived naming, never a
    hardcoded stem, so a custom `archive_dir` is actually looked in and a
    custom hub name is actually recognized), hub or Archive shard, whether
    or not this run's fresh set still produces it. The stale ones --
    present here but absent from the fresh set -- are what `--check`
    reports as drift and `--write` removes as part of the same atomic
    replace (never any other file, never an item file).
    """
    found = []
    for directory in (backlog_dir, archive_dir):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if is_generated_index_file(path.name, naming):
                found.append(path)
    return found


def detect_line_ending(backlog_dir: Path, archive_dir: Path, naming: IndexNaming) -> str:
    """Detect the existing generated-file line-ending convention, once per
    `--write` run, so the hub and every shard share the SAME one.

    `build_index_files` always renders with `\\n` internally -- unchanged by
    this function, and unchanged by anything below it. This is purely a
    `--write`-time conversion applied to the staged bytes right before they
    are written, per Step 8's "write through the newline-preserving
    helpers": that requirement is to preserve the file's EXISTING style,
    not merely to avoid *translating* whichever style the write happens to
    use, so detection has to run before the convert-and-write.

    Reads the existing hub first via `read_text_preserving_newlines` (no
    universal-newline translation) -- the canonical file, named via
    `naming.hub_name` (Finding F5). Falls back to the first on-disk file
    `is_generated_index_file` matches when the hub does not exist yet (a
    shard can exist without a hub only in a transient state). Returns
    `"\\n"` when nothing generated exists at all -- there is no existing
    convention to preserve, so a first-ever `--write` is free to pick
    either, and `\\n` is what `build_index_files` already renders.
    """
    hub_path = backlog_dir / naming.hub_name
    candidate = hub_path if hub_path.exists() else None
    if candidate is None:
        for path in _list_disk_generated_files(backlog_dir, archive_dir, naming):
            candidate = path
            break
    if candidate is None:
        return "\n"
    content = read_text_preserving_newlines(candidate)
    crlf_count = content.count("\r\n")
    lf_count = content.count("\n") - crlf_count
    return "\r\n" if crlf_count >= lf_count else "\n"

# --------------------------------------------------------------------------
# Atomic multi-file write
# --------------------------------------------------------------------------


def _atomic_write_files(files_to_write: dict, files_to_delete: list) -> None:
    """Write every fresh file and remove every stale one as a single unit:
    hub and every shard together, or not at all.

    Phase 1 stages each new file's content into a temp file beside its
    final location (same directory, so `os.replace` below is atomic on that
    file). Nothing that already exists is touched during staging. Backups
    of every final path this call is about to touch (write or delete) are
    captured before the commit phase begins. Phase 2 -- the commit -- calls
    `os.replace` for every staged file and then removes every stale file.
    `os.replace` is atomic per file but cannot replace a file another
    process holds open; if it (or the delete) raises partway through the
    commit phase, every change this call already committed is rolled back
    from the captured backups, and any temp file that never reached the
    rename step is discarded -- so a mid-write failure leaves the prior
    on-disk state intact rather than a half-regenerated set where the hub
    lists shards that were never written.
    """
    staged = []  # (tmp_path, final_path)
    try:
        for final_path, content in files_to_write.items():
            final_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(final_path.parent), prefix=final_path.name + ".", suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            staged.append((Path(tmp_name), final_path))
    except OSError:
        for tmp_path, _final in staged:
            tmp_path.unlink(missing_ok=True)
        raise

    backups: dict = {}
    for _tmp_path, final_path in staged:
        backups[final_path] = final_path.read_bytes() if final_path.exists() else None
    for final_path in files_to_delete:
        backups[final_path] = final_path.read_bytes() if final_path.exists() else None

    committed_replaces: list = []
    committed_deletes: list = []
    try:
        for tmp_path, final_path in staged:
            os.replace(tmp_path, final_path)
            committed_replaces.append(final_path)
        for final_path in files_to_delete:
            if final_path.exists():
                final_path.unlink()
            committed_deletes.append(final_path)
    except OSError:
        for final_path in committed_replaces:
            original = backups.get(final_path)
            if original is None:
                final_path.unlink(missing_ok=True)
            else:
                final_path.write_bytes(original)
        for final_path in committed_deletes:
            original = backups.get(final_path)
            if original is not None:
                final_path.write_bytes(original)
        for tmp_path, final_path in staged:
            if final_path not in committed_replaces:
                tmp_path.unlink(missing_ok=True)
        raise

