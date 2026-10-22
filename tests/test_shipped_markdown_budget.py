#!/usr/bin/env python3
"""Read-budget ratchet for the shipped markdown (handlers, references,
templates, agents, skill).

The test measures every shipped markdown file with the same call the
`measure_files.py` CLI makes, so the test and the CLI cannot disagree:
`measure_files.measure_files(paths, model=None, content=None)`. A `.md` file
then prices at `DEFAULT_BYTES_PER_TOKEN` (2.6 bytes per token), the strictest
text ratio.

Two pinned constants make the budget a ratchet instead of a snapshot:

- `WARN_ALLOWLIST` holds the basenames at WARN or OVER on the pinned tree. A
  WARN or OVER file outside the list fails (the list is too short). A listed
  file that no longer measures WARN or OVER fails (the list is too long). The
  pair is one state-detecting gate: the list can neither go stale nor hide a
  regrown file.
- `OVER_EXEMPTIONS` holds the basenames allowed to sit at OVER. An OVER file
  outside it fails. An exempted file that no longer measures OVER fails.

The sprint that compresses or splits a file removes its entry in its own
write-set.

`PLANWISE_BUDGET_ROOT` overrides the scanned root (read once at import), so a
scratch copy can exercise every test. A root that does not exist fails the
tests and never skips them.

This is a dev-only gate on our own files and does not ship with the plugin.

Run with:  python -m pytest tests/test_shipped_markdown_budget.py -q
"""

import os
import sys
import tempfile
import unittest
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import measure_files
import read_limits

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "plugins" / "planwise"
BUDGET_ROOT = Path(os.environ.get("PLANWISE_BUDGET_ROOT") or DEFAULT_ROOT)

SCAN_DIRS = ("references", "handlers", "templates", "agents")
SKILL_FILE = Path("skills") / "planwise" / "SKILL.md"
MIN_SCANNED_FILES = 50

# Mirrors read_limits._read_level's vocabulary; _read_level never returns Notice.
LEVEL_MAP = {"OK": "Green", "WARN": "Warn", "OVER": "Critical"}

WORKLIST_LINE = "Backlog filing worklist — {n} file(s) at Warn or worse require an item:"

# WARN_ALLOWLIST pinned @ becccfe10f08ea60e0abe67cab4fd965b4ca2954 (2026-10-20); tokens from CRLF-normalized bytes (checkout-independent)
# Guards READ_TOKEN_WARN (22,000). A listed file must still measure WARN or OVER.
# Figures in the comments are history, never asserted.
# Preflight that the pin still holds (MUST print nothing):
#   git -C <plugin repo> log --oneline becccfe..HEAD -- plugins/planwise/references plugins/planwise/handlers plugins/planwise/templates plugins/planwise/agents plugins/planwise/skills
WARN_ALLOWLIST = frozenset({
    "backlog.md",                                              # 22,867
    "exit-criteria-fidelity.md",                               # 24,006
    "measurement-discipline.md",                               # 22,450
    "read-confirm-act-protocol.md",                            # 23,075
    "run.md",                                                  # 25,251 (OVER)
    "scaffolding-hygiene-Part-2-DerivationAndParallelism.md",  # 23,457
    "scaffolding-hygiene.md",                                  # 24,187
    "task-content-fidelity.md",                                # 22,615
})

# OVER_EXEMPTIONS pinned @ becccfe10f08ea60e0abe67cab4fd965b4ca2954 (2026-10-20); tokens from CRLF-normalized bytes (checkout-independent)
# Guards READ_PAGE_CAP_TOKENS (25,000). An exempted file must still measure OVER.
# The sprint that splits run.md removes this entry in its own write-set.
OVER_EXEMPTIONS = frozenset({
    "run.md",                                                  # 25,251
})


def _scan_paths() -> list[str]:
    paths = []
    for name in SCAN_DIRS:
        paths.extend(str(p) for p in sorted((BUDGET_ROOT / name).glob("*.md")))
    skill = BUDGET_ROOT / SKILL_FILE
    if skill.exists():
        paths.append(str(skill))
    return paths


def _crlf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


@lru_cache(maxsize=1)
def _measure() -> dict:
    """Measure CRLF-normalized copies of the scan set.

    This checkout runs core.autocrlf=true, so on-disk bytes depend on the
    checkout (an LF checkout of run.md measures ~24,949 tokens, a CRLF one
    ~25,251). Every file is measured with all line endings as CRLF, the worst
    case a Windows consumer reads, so the result is checkout-independent. The
    real measure_files implementation still prices the bytes: the normalized
    copies go to a temp dir and the rows' paths map back to the originals.
    """
    assert BUDGET_ROOT.is_dir(), f"PLANWISE_BUDGET_ROOT does not exist: {BUDGET_ROOT}"
    originals = _scan_paths()
    with tempfile.TemporaryDirectory(prefix="planwise-budget-") as tmp:
        tmp_root = Path(tmp)
        mapping = {}
        for src in originals:
            dest = tmp_root / Path(src).relative_to(BUDGET_ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_crlf(Path(src).read_bytes()))
            mapping[str(dest)] = src
        result = measure_files.measure_files(list(mapping), model=None, content=None)
    for row in result["files"]:
        row["path"] = mapping[row["path"]]
    return result


def _rel(path: str) -> str:
    return Path(path).relative_to(BUDGET_ROOT).as_posix()


def _by_basename() -> dict[str, dict]:
    return {Path(f["path"]).name: f for f in _measure()["files"]}


def _non_ok() -> list[dict]:
    return [f for f in _measure()["files"] if f["level"] != "OK"]


class TestShippedMarkdownBudget(unittest.TestCase):

    def test_warn_files_are_allowlisted(self):
        """code-gap-11: every WARN or OVER file has its basename in WARN_ALLOWLIST."""
        non_ok = _non_ok()
        # Printed on every run; pytest shows it with -s or -rP.
        print(WORKLIST_LINE.format(n=len(non_ok)))
        for f in non_ok:
            print(Path(f["path"]).name)

        unlisted = [f for f in non_ok if Path(f["path"]).name not in WARN_ALLOWLIST]
        lines = [WORKLIST_LINE.format(n=len(unlisted))]
        lines += [f"{_rel(f['path'])} {f['level']} ~{f['tokens']:,} tokens" for f in unlisted]
        self.assertEqual(unlisted, [], "\n".join(lines))

    def test_allowlist_has_no_stale_entries(self):
        """code-gap-12: every listed basename still measures WARN or OVER."""
        rows = _by_basename()
        stale = []
        for name in sorted(WARN_ALLOWLIST):
            row = rows.get(name)
            if row is None:
                stale.append(f"{name}: matches no scanned file")
            elif row["level"] == "OK":
                stale.append(f"{name}: measures OK at ~{row['tokens']:,} tokens")
        for name in sorted(OVER_EXEMPTIONS):
            row = rows.get(name)
            if row is None:
                stale.append(f"{name} (OVER_EXEMPTIONS): matches no scanned file")
            elif row["level"] != "OVER":
                stale.append(
                    f"{name} (OVER_EXEMPTIONS): measures {row['level']} at ~{row['tokens']:,} tokens"
                )
        self.assertEqual(
            stale,
            [],
            "stale entry: remove it from WARN_ALLOWLIST or OVER_EXEMPTIONS in the same "
            "write-set that compressed the file:\n" + "\n".join(stale),
        )

    def test_no_file_is_over(self):
        """code-gap-13: no scanned file is OVER unless OVER_EXEMPTIONS pins it."""
        over = [
            f for f in _measure()["files"]
            if f["level"] == "OVER" and Path(f["path"]).name not in OVER_EXEMPTIONS
        ]
        report = [
            f"{_rel(f['path'])} ~{f['tokens']:,} tokens against READ_PAGE_CAP_TOKENS "
            f"({read_limits.READ_PAGE_CAP_TOKENS:,})"
            for f in over
        ]
        self.assertEqual(over, [], "\n".join(report))

    def test_measure_reports_no_errors(self):
        """An unreadable file lands in errors, not an exception, so assert it is empty."""
        self.assertEqual(_measure()["errors"], [])

    def test_measure_level_matches_read_level(self):
        """Parity: measure_file's level equals read_limits._read_level's, mapped."""
        mismatches = []
        for f in _measure()["files"]:
            got = read_limits._read_level(f["bytes"], f["tokens"], f["lines"])
            if LEVEL_MAP[f["level"]] != got:
                mismatches.append(f"{_rel(f['path'])}: measure {f['level']} vs read_limits {got}")
        self.assertEqual(mismatches, [])

    def test_scan_covers_more_than_fifty_files(self):
        """Instrument check, plus Decision 17: the allowlist key is the basename."""
        files = _measure()["files"]
        self.assertGreater(len(files), MIN_SCANNED_FILES)
        names = [Path(f["path"]).name for f in files]
        repeated = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(repeated, [], f"basenames repeat across the scan set: {repeated}")

    def test_budget_root_resolves(self):
        """The root exists, and the test prints the root it received."""
        print(f"PLANWISE_BUDGET_ROOT resolved to: {BUDGET_ROOT.as_posix()}")
        self.assertTrue(BUDGET_ROOT.is_dir(), f"budget root does not exist: {BUDGET_ROOT}")


if __name__ == "__main__":
    unittest.main()
