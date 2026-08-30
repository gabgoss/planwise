"""Containment layer for the eval suite: a scratch project root that a
handler can never mistake for (or walk up into) the live authoring repo.

`cwd` alone is NOT a sandbox — a handler that finds no local
`planwise/config.yaml` can walk up the `--plugin-dir` path's own prefix and
land on the real project. This module implements the three remedies:

1. `ScratchRoot.create()` refuses to proceed if any ancestor of the chosen
   scratch root already carries a live `planwise/config.yaml` — the scratch
   tree itself is never planted inside a reachable project.
2. `copy_plugin_subtree()` copies `plugins/planwise` into the scratch root
   ONCE per suite run and verifies a file-count + total-byte manifest
   before trusting the copy; `--plugin-dir` is pointed at the copy, never
   at the live tree, so the passed path leaks no live-project prefix.
3. `teardown()` only ever deletes a path it has first proven sits inside
   the scratch root — a teardown that COULD be pointed at an arbitrary path
   is a defect even when every current caller happens to pass one that is
   safe.

`report_transcript_delta()` is report-only: it counts `~/.claude/projects/`
entries and never deletes anything there. Cleaning up transcript dirs would
itself be a write outside the scratch root, by the very module asserting
containment.
"""

from __future__ import annotations

import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_ANCESTOR_MARKER = Path("planwise") / "config.yaml"


class ScratchContainmentError(RuntimeError):
    """A containment invariant would be violated (or was proven violated)."""


def _count_entries(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for _ in root.iterdir())


def _manifest(tree: Path) -> tuple[int, int]:
    """(file count, total bytes) for every regular file under `tree`."""
    count = 0
    total_bytes = 0
    for path in tree.rglob("*"):
        if path.is_file():
            count += 1
            total_bytes += path.stat().st_size
    return count, total_bytes


def _assert_no_ancestor_project(root: Path) -> None:
    """Refuse if `root` or any of its ancestors carries `planwise/config.yaml`.

    Checked BEFORE the scratch root is created on disk — a refusal here
    must leave nothing behind. Resolves `root` first: an unresolved
    relative path's `.parents` chain terminates at `.` without ever
    reaching the real filesystem ancestry, which would let a relative
    `base_temp` walk straight past this guard.
    """
    resolved_root = root.resolve()
    for ancestor in (resolved_root, *resolved_root.parents):
        marker = ancestor / _ANCESTOR_MARKER
        if marker.is_file():
            raise ScratchContainmentError(
                f"scratch root has a live project ancestor: {marker}"
            )


def _assert_within_root(path: Path, root: Path) -> None:
    """Refuse a delete target that is not (already) inside `root`."""
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ScratchContainmentError(
            f"refusing to delete {resolved_path}: not inside scratch root {resolved_root}"
        )


@dataclass
class ScratchRoot:
    """One suite run's scratch tree: `<TEMP>/planwise-evals-<run_id>/`."""

    run_id: str
    root: Path
    plugin_copy: Path | None = None
    transcripts_root: Path = field(
        default_factory=lambda: Path.home() / ".claude" / "projects"
    )
    _transcript_baseline: int = field(default=0, repr=False)
    case_dirs: list = field(default_factory=list)

    @classmethod
    def create(
        cls,
        run_id: str | None = None,
        base_temp: Path | str | None = None,
        transcripts_root: Path | str | None = None,
    ) -> "ScratchRoot":
        """Choose (and validate) a fresh scratch root; does not create the
        plugin copy or any case dir — call `copy_plugin_subtree()` /
        `new_case_dir()` for those.
        """
        run_id = run_id or uuid.uuid4().hex[:12]
        base = Path(base_temp) if base_temp is not None else Path(tempfile.gettempdir())
        root = (base / f"planwise-evals-{run_id}").resolve()

        _assert_no_ancestor_project(root)

        if root.exists():
            # An explicit run_id supplied twice (or a genuine collision
            # between concurrent runs) must never be silently adopted --
            # copy_plugin_subtree()'s unconditional rmtree(dest) on the
            # SECOND create() would otherwise delete the FIRST run's live
            # plugin copy out from under it.
            raise ScratchContainmentError(
                f"scratch root already exists for run_id {run_id!r}: {root} "
                "-- refusing to adopt another run's tree"
            )
        root.mkdir(parents=True)

        t_root = (
            Path(transcripts_root)
            if transcripts_root is not None
            else Path.home() / ".claude" / "projects"
        )
        baseline = _count_entries(t_root)

        return cls(
            run_id=run_id, root=root, transcripts_root=t_root,
            _transcript_baseline=baseline,
        )

    def new_case_dir(self, name: str) -> Path:
        """A unique path under the scratch root for one case's directory.

        Asserts the path does not already exist. Does NOT create it on
        disk — callers create it (a plain `mkdir`, or as the target of a
        `copytree`) so both an empty base and a template-derived base can
        share this one naming/uniqueness authority.
        """
        case_dir = self.root / name
        if case_dir.exists():
            raise ScratchContainmentError(
                f"case dir already exists, refusing to reuse: {case_dir}"
            )
        self.case_dirs.append(case_dir)
        return case_dir

    def copy_plugin_subtree(self, source: Path | str) -> Path:
        """One per-run copy of `plugins/planwise` into the scratch root.

        `--plugin-dir` is pointed at the RETURNED copy, never at `source` —
        the copy carries no live-project path prefix. Verifies a
        file-count + total-byte manifest against `source` before trusting
        the copy; a mismatch means the suite would silently test a
        stale/partial tree while claiming the pinned one.
        """
        source = Path(source)
        dest = self.root / "plugin-copy"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)

        src_manifest = _manifest(source)
        dst_manifest = _manifest(dest)
        if src_manifest != dst_manifest:
            src_count, src_bytes = src_manifest
            dst_count, dst_bytes = dst_manifest
            raise ScratchContainmentError(
                "plugin subtree copy manifest mismatch: "
                f"source={src_count} files/{src_bytes} bytes, "
                f"copy={dst_count} files/{dst_bytes} bytes"
            )

        self.plugin_copy = dest
        return dest

    def report_transcript_delta(self) -> int:
        """`~/.claude/projects/` entry count now, minus the count captured
        at `create()` time. REPORT only — contains no delete of any kind.
        """
        return _count_entries(self.transcripts_root) - self._transcript_baseline

    def teardown_case(
        self, case_dir: Path, *, failed: bool = False, keep_failed: bool = True,
        retries: int = 3, backoff_s: float = 0.5,
    ) -> bool:
        """Tear down one case dir that belongs to this scratch root."""
        return teardown(
            case_dir, self.root, failed=failed, keep_failed=keep_failed,
            retries=retries, backoff_s=backoff_s,
        )


def teardown(
    case_dir: Path | str,
    scratch_root: Path | str,
    *,
    failed: bool = False,
    keep_failed: bool = True,
    retries: int = 3,
    backoff_s: float = 0.5,
) -> bool:
    """Recursively delete `case_dir` and verify absence.

    Refuses (raises `ScratchContainmentError`, deletes nothing) if
    `case_dir` is not inside `scratch_root` — a teardown that COULD be
    pointed at an arbitrary path is a defect on its own, independent of
    whether any current caller happens to pass a safe one.

    `failed` + `keep_failed` (the `--eval-keep-failed` default-ON posture)
    retains the dir instead of deleting it, for post-mortem inspection.

    Deletion is retried with a short backoff: a timed-out/killed CLI
    process can hold a handle open briefly after the parent returns.
    """
    case_dir = Path(case_dir)
    scratch_root = Path(scratch_root)
    _assert_within_root(case_dir, scratch_root)

    if failed and keep_failed:
        return False

    if not case_dir.exists():
        return True

    last_error: OSError | None = None
    for attempt in range(retries):
        try:
            shutil.rmtree(case_dir)
        except OSError as exc:
            last_error = exc
            time.sleep(backoff_s * (attempt + 1))
            continue
        if not case_dir.exists():
            return True

    raise ScratchContainmentError(
        f"teardown failed to remove {case_dir} after {retries} attempt(s)"
    ) from last_error
