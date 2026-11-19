#!/usr/bin/env python3
"""Regenerate plugins/planwise/manifests/rule-history.json from git history.

Dev-repo tool. It needs this repository's git history, which a consumer
install does not carry, so it lives outside the shipped subtree. The manifest
it writes DOES ship: `rule_divergence._classify_diverged` reads it to recognise
an installed rule whose body equals a body the plugin shipped at any earlier
commit. Upgrade then adopts the current shipped body with no comparator, no
transfer and no HAS_UNIQUE verdict.

For every filename in rule_registry.INSTALLED_RULES, rule_registry.DESCOPED_RULES
and style_rules.STYLE_RULES the tool walks `git log --all` for
plugins/planwise/references/<filename>, digests every distinct blob the file has
ever had (plus the working-tree body), and writes the sorted digest list. Every
commit's body is included, released or not. A superset is harmless, because no
user edit produces a body that equals an unreleased commit by accident.

Usage (from the plugin repo root, or with absolute paths):
    python tools/gen_rule_history.py            # rewrite the manifest
    python tools/gen_rule_history.py --check    # exit 1 if it would change

The digest is rule_divergence.rule_history_digest(). The classifier and this
tool share that one function, so they can never disagree.
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "plugins" / "planwise" / "scripts"
REFERENCES_REL = Path("plugins") / "planwise" / "references"
sys.path.insert(0, str(SCRIPTS))

# init_project is the scripts package's import root. Import it first, as every
# test and handler entry point does, so the sibling modules below resolve
# without tripping the import cycle.
import init_project  # noqa: F401 -- sys.path must be set first; resolves the import cycle
from rule_divergence import RULE_HISTORY_MANIFEST, rule_history_digest
from rule_registry import DESCOPED_RULES, INSTALLED_RULES
from style_rules import STYLE_RULES

MANIFEST = RULE_HISTORY_MANIFEST


def listed_rule_filenames() -> list[str]:
    """Every rule reference the upgrade can compare, in a stable order."""
    names = [name for name, _ in INSTALLED_RULES]
    names += [name for name, _ in DESCOPED_RULES]
    names += [name for name, _ in STYLE_RULES]
    return sorted(set(names))


def _git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True,
                          capture_output=True).stdout


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8-sig")


def historical_digests(filename: str) -> set[str]:
    rel = (REFERENCES_REL / filename).as_posix()
    digests: set[str] = set()
    seen_blobs: set[str] = set()
    shas = _git("log", "--all", "--format=%H", "--", rel).decode().split()
    for sha in shas:
        probe = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", "-q",
                                f"{sha}:{rel}"], capture_output=True, check=False)
        if probe.returncode != 0:
            continue  # the file did not exist at this commit (deleted or renamed)
        blob = probe.stdout.decode().strip()
        if blob in seen_blobs:
            continue
        seen_blobs.add(blob)
        digests.add(rule_history_digest(_decode(_git("cat-file", "-p", blob))))
    live = REPO / REFERENCES_REL / filename
    if live.is_file():
        digests.add(rule_history_digest(live.read_text(encoding="utf-8-sig")))
    return digests


def build_manifest() -> dict:
    rules = {name: sorted(historical_digests(name)) for name in listed_rule_filenames()}
    return {
        "schema_version": 1,
        "generated_on": datetime.datetime.now().astimezone().date().isoformat(),
        "normalization": "read as utf-8-sig (BOM stripped), CRLF -> LF, paths: and "
                         "consult-when: keys removed, sha256 hex "
                         "(rule_divergence.rule_history_digest)",
        "purpose": "Every body each installed, de-scoped and style rule reference has "
                   "ever shipped with. rule_divergence._classify_diverged returns SUBSET "
                   "at exact confidence for an installed body matching any listed digest, "
                   "so an unedited older rule is adopted without a transfer. Regenerate "
                   "with tools/gen_rule_history.py after editing a listed reference; "
                   "tests/test_rule_history.py enforces it.",
        "rules": rules,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when the on-disk manifest's rules block differs")
    args = parser.parse_args(argv)

    fresh = build_manifest()
    if args.check:
        try:
            current = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"rule-history manifest missing or unreadable: {MANIFEST}", file=sys.stderr)
            return 1
        if current.get("rules") != fresh["rules"]:
            print("rule-history manifest is stale — run tools/gen_rule_history.py",
                  file=sys.stderr)
            return 1
        print("rule-history manifest is current.")
        return 0

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(fresh, indent=2) + "\n", encoding="utf-8")
    total = sum(len(v) for v in fresh["rules"].values())
    print(f"wrote {MANIFEST} — {len(fresh['rules'])} rules, {total} distinct bodies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
