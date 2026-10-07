#!/usr/bin/env python3
"""Re-derive the next-free sequential anchor in a markdown file, and claim it.

A backlog item drafted ahead of execution pins a "next-free" insertion target
-- a top-level `## N.` section number, a `### 9.B.N` subsection number, an
Error Pattern Catalog row number -- to whatever was free at DRAFT time. Any
sibling change that lands before the item is worked consumes that slot, so the
drafted number is a hypothesis, never an address. This script re-derives the
number from the live file, which is the mechanized form of the manual
re-derivation the citation-freshness discipline prescribes.

Two failure modes are covered.

1. STALENESS -- the drafted number was consumed between drafting and
   execution. `--scheme` scans the live file and returns `max_found` and
   `next_free`.

2. CONCURRENT CLAIMS -- two callers re-derive "current max" at the same
   instant, both compute the same next-free number, and both insert there.
   `--claim` records the value in a small per-repository ledger, so a second
   caller for the same (file, scheme, prefix) returns one above the first's
   unconsumed claim instead of the same number.

A claim is self-invalidating: it is consumed, and ignored from then on, as
soon as the live file's own maximum reaches it. Inserting the anchor is what
releases the claim -- there is no separate release step to forget.

What this script deliberately does NOT do: resolve a FILE-LEVEL relocation. A
section family that physically moved to another file is a semantic judgement
about where the content now belongs, not a numbering problem. The script
detects the symptom -- a relocation-redirect marker in the target file -- and
emits a warning so the caller checks before trusting the number. Deciding the
new home stays with the caller.

Usage:
    python resolve_anchor.py --file <path> --scheme heading-toplevel
    python resolve_anchor.py --file <path> --scheme heading-sub --prefix "9.B."
    python resolve_anchor.py --file <path> --scheme table-row --json
    python resolve_anchor.py --file <path> --scheme table-row --claim <id>

Exit codes: 0 on success (a relocation warning is NOT an error), 2 on a usage
or I/O failure.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

LEDGER_NAME = ".anchor-claims.json"

# How long a claim stays honoured before it is treated as abandoned. A claim
# is normally released by its own anchor appearing in the file; this bound
# stops a caller that crashed between claiming and inserting from reserving a
# number forever.
CLAIM_TTL_SECONDS = 24 * 60 * 60

# Markers that say a section family has been relocated out of this file. The
# list is deliberately narrow: each entry is a phrase that carries structural
# meaning in this corpus, not an ordinary turn of prose. Widen it only for a
# marker actually observed in a redirect table.
RELOCATION_MARKERS = (
    "segment index",
    "relocated to",
    "has moved to",
    "now lives in",
)


class ResolveError(Exception):
    """A usage or I/O failure that should exit 2 with a message."""


def anchor_pattern(scheme: str, prefix: str) -> re.Pattern:
    """Return the compiled line pattern whose group 1 is the anchor number."""
    if scheme == "heading-toplevel":
        return re.compile(r"^## (\d+)\.")
    if scheme == "heading-sub":
        if not prefix:
            raise ResolveError("--scheme heading-sub requires --prefix (e.g. --prefix \"9.B.\")")
        return re.compile(r"^### " + re.escape(prefix) + r"(\d+)")
    if scheme == "table-row":
        return re.compile(r"^\|\s*(\d+)\s*\|")
    raise ResolveError(f"Unknown scheme '{scheme}'.")


def scan_max(text: str, pattern: re.Pattern) -> int:
    """Return the highest anchor number present, or 0 when none match."""
    found = [int(m.group(1)) for m in (pattern.match(line) for line in text.splitlines()) if m]
    return max(found) if found else 0


def detect_relocation_markers(text: str) -> list[str]:
    """Return the relocation-redirect markers present in the file, if any."""
    haystack = text.lower()
    return [marker for marker in RELOCATION_MARKERS if marker in haystack]


def repo_root_for(path: Path) -> Path:
    """Return the nearest ancestor holding a .git entry, else the file's dir."""
    resolved = path.resolve()
    for candidate in resolved.parents:
        if (candidate / ".git").exists():
            return candidate
    return resolved.parent


def ledger_path_for(target: Path, override: Path | None) -> Path:
    return override.resolve() if override else repo_root_for(target) / LEDGER_NAME


def _read_ledger(ledger: Path) -> dict:
    if not ledger.exists():
        return {"claims": []}
    try:
        data = json.loads(ledger.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ResolveError(f"Claims ledger at {ledger} is unreadable: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
        raise ResolveError(f"Claims ledger at {ledger} is malformed: expected a 'claims' list.")
    return data


def _claim_key(target: Path, scheme: str, prefix: str) -> tuple[str, str, str]:
    return (target.resolve().as_posix(), scheme, prefix)


def _matching_claims(data: dict, key: tuple[str, str, str]) -> list[dict]:
    return [
        c
        for c in data["claims"]
        if (c.get("file"), c.get("scheme"), c.get("prefix", "")) == key
    ]


def _is_live(claim: dict, max_found: int, now: float) -> bool:
    """A claim still reserves its number only while it is unconsumed and fresh.

    Consumed means the live file's own maximum has reached the claimed value --
    the anchor is physically present now, so the claim has done its job.
    """
    if int(claim.get("claimed_value", 0)) <= max_found:
        return False
    return (now - float(claim.get("epoch", 0))) < CLAIM_TTL_SECONDS


def _write_ledger_atomically(ledger: Path, data: dict) -> None:
    tmp = ledger.with_suffix(ledger.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, ledger)  # atomic within a filesystem


def _acquire_lock(ledger: Path, timeout: float = 10.0) -> Path:
    """Take an exclusive lock beside the ledger so two claims cannot interleave.

    O_CREAT|O_EXCL is the portable primitive here -- it succeeds for exactly
    one caller. A read-modify-write without it can lose a concurrent claim,
    which is the very collision this ledger exists to prevent.
    """
    lock = ledger.with_suffix(ledger.suffix + ".lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ResolveError(
                    f"Could not acquire the claims lock at {lock} within {timeout:.0f}s. "
                    f"If no other resolve_anchor.py is running, delete the lock file."
                )
            time.sleep(0.05)


def record_claim(
    target: Path,
    scheme: str,
    prefix: str,
    claimant: str,
    max_found: int,
    ledger: Path,
) -> tuple[int, list[int]]:
    """Reserve and return the next value above the live max and any live claim.

    Returns (claimed_value, prior_live_values).
    """
    ledger.parent.mkdir(parents=True, exist_ok=True)
    lock = _acquire_lock(ledger)
    try:
        data = _read_ledger(ledger)
        key = _claim_key(target, scheme, prefix)
        now = time.time()

        # Drop every claim the live file (or the TTL) has already settled, for
        # this key and for every other -- the ledger stays small and a stale
        # entry can never reserve a number a second time.
        surviving = []
        for claim in data["claims"]:
            claim_key = (claim.get("file"), claim.get("scheme"), claim.get("prefix", ""))
            if claim_key == key and not _is_live(claim, max_found, now):
                continue
            if claim_key != key and (now - float(claim.get("epoch", 0))) >= CLAIM_TTL_SECONDS:
                continue
            surviving.append(claim)
        data["claims"] = surviving

        live_values = sorted(
            int(c["claimed_value"]) for c in _matching_claims(data, key)
        )
        claimed_value = max([max_found] + live_values) + 1

        data["claims"].append(
            {
                "file": key[0],
                "scheme": scheme,
                "prefix": prefix,
                "claimed_value": claimed_value,
                "claimant": claimant,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "epoch": now,
            }
        )
        _write_ledger_atomically(ledger, data)
        return claimed_value, live_values
    finally:
        lock.unlink(missing_ok=True)


def resolve(args) -> dict:
    target = Path(args.file)
    if not target.is_file():
        raise ResolveError(f"File not found: {target}")
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ResolveError(f"Could not read {target}: {exc}")

    # The prefix is part of the ledger key, so it is normalized away for the
    # schemes that do not use one -- otherwise the same anchor space would be
    # claimed under two different keys.
    prefix = args.prefix if args.scheme == "heading-sub" else ""
    pattern = anchor_pattern(args.scheme, prefix)

    max_found = scan_max(text, pattern)
    result = {
        "file": str(target),
        "scheme": args.scheme,
        "prefix": prefix,
        "max_found": max_found,
        "next_free": max_found + 1,
        "warnings": [],
    }

    markers = detect_relocation_markers(text)
    if markers:
        result["warnings"].append(
            f"WARNING: {target.name} carries a relocation-redirect marker "
            f"({', '.join(markers)}). A section family may have moved to another "
            f"file, in which case this number is correct for the WRONG file. "
            f"Confirm the target file still owns this anchor space before inserting."
        )

    if args.claim:
        ledger = ledger_path_for(target, args.ledger)
        claimed_value, prior = record_claim(
            target, args.scheme, prefix, args.claim, max_found, ledger
        )
        result["claimed"] = claimed_value
        result["claimant"] = args.claim
        result["ledger"] = str(ledger)
        result["prior_live_claims"] = prior
        if claimed_value != result["next_free"]:
            result["warnings"].append(
                f"WARNING: an unconsumed claim already reserves "
                f"{result['next_free']} for this (file, scheme, prefix). "
                f"Claimed {claimed_value} instead."
            )

    return result


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Re-derive the next-free sequential anchor in a markdown file, and "
            "optionally claim it so a concurrent caller cannot take the same number."
        )
    )
    parser.add_argument("--file", required=True, help="Markdown file to scan.")
    parser.add_argument(
        "--scheme",
        required=True,
        choices=["heading-toplevel", "heading-sub", "table-row"],
        help=(
            "heading-toplevel: '## N.'  |  heading-sub: '### {prefix}N' "
            "(needs --prefix)  |  table-row: the first pipe-delimited column."
        ),
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Subsection prefix for --scheme heading-sub, e.g. \"9.B.\".",
    )
    parser.add_argument(
        "--claim",
        metavar="CLAIMANT",
        help=(
            "Reserve the returned value for CLAIMANT in the claims ledger. The "
            "claim is released automatically once the anchor appears in the file."
        ),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help=(
            f"Claims ledger path. Defaults to {LEDGER_NAME} at the target "
            f"file's repository root."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    args = parser.parse_args()

    try:
        result = resolve(args)
    except ResolveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    for warning in result["warnings"]:
        print(warning, file=sys.stderr)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"file:      {result['file']}")
        print(f"scheme:    {result['scheme']}" + (f" (prefix {result['prefix']})" if result["prefix"] else ""))
        print(f"max_found: {result['max_found']}")
        print(f"next_free: {result['next_free']}")
        if "claimed" in result:
            print(f"claimed:   {result['claimed']} for {result['claimant']}")
            print(f"ledger:    {result['ledger']}")


if __name__ == "__main__":
    main()
