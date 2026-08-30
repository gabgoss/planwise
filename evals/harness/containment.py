"""Containment: the A4b filesystem predicate plus the both-repo
`git status --porcelain` delta.

cwd is NOT a sandbox (EI Part 1 Section 5) -- a handler that finds no local
`config.yaml` can walk up the `--plugin-dir` path's real-project prefix and
act on the live project from a scratch cwd. Two independent checks cover
different halves of that threat:

  * `a4b_scan` -- a pure `rglob` predicate, parent-scoped: did anything land
    outside the case dir, inside its immediate parent. No subprocess.
  * `porcelain_delta` -- the `git status --porcelain` check on BOTH repos
    (outer `planwise-development` and `cloned-repos/planwise`), which is
    what catches a walk-up write that lands outside the parent entirely
    (a4b_scan's blind spot). This is the only place in the harness that
    shells out for a containment check -- graders never do (see
    `graders.py`'s module docstring).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


def a4b_scan(parent: Path, case_dir: Path, exclude: Iterable[Path] = ()) -> list[Path]:
    """Any path under `parent` that is neither `case_dir` itself, one of its
    descendants, nor one of the caller-declared `exclude` entries (or their
    descendants) is a containment leak. Returns the list of leaked paths
    (empty == clean).

    `exclude` is how a caller whose `parent` is a shared scratch root (which
    also holds sibling scaffolding -- the plugin-subtree copy, the
    `fx-initialized` template, other case dirs) declares which of those
    siblings are known-legitimate and must NOT be reported as leaks. This
    predicate deliberately has NO hardcoded knowledge of scratch-layout
    names (`plugin-copy`, the template dir, ...) -- that knowledge belongs
    to the caller that owns the scratch root; a name baked in here would
    silently rot the moment that layout changes. Only entries the caller
    explicitly names are excluded -- an actual stray file planted anywhere
    else under `parent` is still caught.

    Dry-run this against a synthesized leak once per grader implementation
    (plant one stray file outside `case_dir` AND outside every declared
    `exclude` entry) -- a predicate only ever run against clean input has
    never been shown to discriminate.
    """
    excluded = list(exclude)
    leaked = []
    for candidate in parent.rglob("*"):
        if candidate == case_dir or case_dir in candidate.parents:
            continue
        if any(candidate == entry or entry in candidate.parents for entry in excluded):
            continue
        leaked.append(candidate)
    return leaked


@dataclass
class RepoStatus:
    """One repo's porcelain result. `checked` is False when the repo path
    does not exist, is not a git worktree, or the `git` call otherwise
    failed -- kept distinct from `dirty` so a delta that had nothing to
    check is never confused with one that checked and found it clean.
    """

    repo: Path
    checked: bool
    baseline: str | None = None
    current: str | None = None

    @property
    def dirty(self) -> bool | None:
        """None when unchecked. Otherwise: did `current` porcelain output
        differ from the pre-captured `baseline` -- pre-existing repo dirt
        the baseline already recorded is NOT attributed to the case.
        """
        if not self.checked:
            return None
        return (self.current or "") != (self.baseline or "")


@dataclass
class DeltaReport:
    """The both-repo delta. Always consult `any_checked` before trusting
    `all_clean` -- an empty/unchecked report reads as `all_clean is False`,
    which is deliberately NOT the same thing as "checked and dirty".
    """

    statuses: list[RepoStatus] = field(default_factory=list)

    @property
    def any_checked(self) -> bool:
        return any(status.checked for status in self.statuses)

    @property
    def all_clean(self) -> bool:
        checked = [status for status in self.statuses if status.checked]
        return bool(checked) and all(not status.dirty for status in checked)


def _run_git_status(repo: Path) -> str | None:
    """`git -C <repo> status --porcelain`, or None if the repo path does
    not exist, is not a git worktree, or the call otherwise fails. Never
    raises.
    """
    if not repo.is_dir():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def capture_baseline(repos: list[Path]) -> dict[Path, str | None]:
    """Pre-case snapshot: `git status --porcelain` for each repo, taken
    BEFORE the case under test runs. Feed the result into `porcelain_delta`
    as `baseline` so pre-existing, unrelated repo dirt is never
    misattributed to the case.
    """
    return {repo: _run_git_status(repo) for repo in repos}


def porcelain_delta(
    repos: list[Path],
    baseline: dict[Path, str | None] | None = None,
) -> DeltaReport:
    """Run `git -C <repo> status --porcelain` for each repo in `repos` and
    compare against `baseline` (from `capture_baseline`, or None to expect
    an empty tree for every repo). Records which repos were actually
    checked -- a repo whose path does not exist is `checked=False`, never
    silently folded into "clean".

    A repo `capture_baseline` explicitly attempted and FAILED for (present
    as a key in `baseline`, value `None`) is ALSO `checked=False` here,
    regardless of whether the current git call now succeeds. Coercing that
    `None` into `""` would compare this run's status against an
    assumed-empty baseline that was never actually captured -- any
    pre-existing repo dirt would then be misattributed to the case under
    test, exactly what `baseline` exists to prevent. This is distinct from
    a repo simply absent from `baseline` (no baseline was requested for it
    at all), which keeps the documented opt-out default of comparing
    against `""`.
    """
    baseline = baseline or {}
    statuses = []
    for repo in repos:
        baseline_capture_attempted = repo in baseline
        base = baseline.get(repo)
        if baseline_capture_attempted and base is None:
            statuses.append(RepoStatus(repo=repo, checked=False, baseline=None, current=None))
            continue
        current = _run_git_status(repo)
        if current is None:
            statuses.append(RepoStatus(repo=repo, checked=False, baseline=base, current=None))
            continue
        statuses.append(RepoStatus(repo=repo, checked=True, baseline=base or "", current=current))
    return DeltaReport(statuses=statuses)
