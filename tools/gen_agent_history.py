#!/usr/bin/env python3
"""Regenerate plugins/planwise/manifests/agent-history.json from git history.

Dev-repo tool — it needs this repository's git history, which a consumer
install does not carry, so it lives outside the shipped subtree. The manifest
it writes DOES ship: doctor's orphaned-agent-mirror sweep reads it to recognise
an installed mirror that is byte-exact to a body the agent shipped with at any
earlier commit ("historical-exact"), which is the only way a stale copy stays
classifiable after a release that relocated content OUT of the agent.

For every filename in doctor_sweeps.FORMERLY_MIRRORED_AGENTS the tool walks
`git log --all` for plugins/planwise/agents/<filename>, digests every distinct
blob the file has ever had (plus the working-tree body), and writes the sorted
digest list. Every commit's body is included, released or not: a superset is
harmless — no user edit produces a byte-exact match to an unreleased commit by
accident — and it means a manifest regenerated late still covers what shipped.

Usage (from the plugin repo root, or with absolute paths):
    python tools/gen_agent_history.py            # rewrite the manifest
    python tools/gen_agent_history.py --check    # exit 1 if it would change

Normalization is doctor_sweeps.history_digest() — the sweep and this tool
share one function so they can never disagree.
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "plugins" / "planwise" / "scripts"
AGENTS_REL = Path("plugins") / "planwise" / "agents"
sys.path.insert(0, str(SCRIPTS))

# init_project is the scripts package's import root: doctor_sweeps imports it
# and it imports doctor_sweeps back through artifact_upgrade, so importing
# doctor_sweeps first trips that cycle. Import the root first, as every test
# and handler entry point does, then pull the sweep's public names.
import init_project  # noqa: E402,F401 -- sys.path must be set first; resolves the import cycle
from doctor_sweeps import (  # noqa: E402
    AGENT_HISTORY_MANIFEST,
    FORMERLY_MIRRORED_AGENTS,
    history_digest,
)

MANIFEST = REPO / "plugins" / "planwise" / AGENT_HISTORY_MANIFEST


def _git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True,
                          capture_output=True).stdout


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8-sig")


def historical_digests(filename: str) -> set[str]:
    rel = (AGENTS_REL / filename).as_posix()
    digests: set[str] = set()
    seen_blobs: set[str] = set()
    shas = _git("log", "--all", "--format=%H", "--", rel).decode().split()
    for sha in shas:
        probe = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", "-q",
                                f"{sha}:{rel}"], capture_output=True)
        if probe.returncode != 0:
            continue  # the file did not exist at this commit (deleted/renamed)
        blob = probe.stdout.decode().strip()
        if blob in seen_blobs:
            continue
        seen_blobs.add(blob)
        digests.add(history_digest(_decode(_git("cat-file", "-p", blob))))
    live = REPO / AGENTS_REL / filename
    if live.is_file():
        digests.add(history_digest(live.read_text(encoding="utf-8-sig")))
    return digests


def build_manifest() -> dict:
    agents = {name: sorted(historical_digests(name)) for name in FORMERLY_MIRRORED_AGENTS}
    return {
        "schema_version": 1,
        "generated_on": datetime.date.today().isoformat(),
        "normalization": "read as utf-8-sig (BOM stripped), CRLF -> LF, sha256 hex "
                         "(doctor_sweeps.history_digest)",
        "purpose": "Every body each formerly-mirrored agent has ever shipped with. "
                   "doctor's orphaned-agent-mirror sweep marks an installed mirror "
                   "matching any listed digest REMOVABLE (historical-exact). "
                   "Regenerate with tools/gen_agent_history.py after editing a "
                   "listed agent; tests/test_agent_history.py enforces it.",
        "agents": agents,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when the on-disk manifest's agents block differs")
    args = parser.parse_args(argv)

    fresh = build_manifest()
    if args.check:
        try:
            current = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"agent-history manifest missing or unreadable: {MANIFEST}", file=sys.stderr)
            return 1
        if current.get("agents") != fresh["agents"]:
            print("agent-history manifest is stale — run tools/gen_agent_history.py",
                  file=sys.stderr)
            return 1
        print("agent-history manifest is current.")
        return 0

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(fresh, indent=2) + "\n", encoding="utf-8")
    total = sum(len(v) for v in fresh["agents"].values())
    print(f"wrote {MANIFEST} — {len(fresh['agents'])} agents, {total} distinct bodies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
