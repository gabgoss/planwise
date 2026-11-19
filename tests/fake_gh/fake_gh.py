"""A stand-in for the GitHub CLI that the feedback driver tests put first on PATH.

Every call appends its argv as one JSON line to the file named by FAKE_GH_LOG, then answers:

- `--version` prints a version line and exits 0.
- `issue list` prints a JSON array chosen by FAKE_GH_SCENARIO: `empty` (the default) prints `[]`;
  a path to a JSON file holding `{"responses": [{"match": "...", "rows": [...]}], "recent": [...]}`
  prints the rows of the first response whose `match` is a substring of the `--search` value, `[]`
  when none matches, and `recent` for a call without `--search`. A row may carry `age_days` or
  `age_minutes` in place of `createdAt`; the fake turns it into a UTC timestamp that long ago.
- any other call prints nothing and exits 0.

FAKE_GH_SLEEP (seconds) and FAKE_GH_EXIT (an exit code) apply to every call except `--version`,
or, when FAKE_GH_MATCH is set, only to calls whose space-joined argv contains it.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone


def _rows(rows: list) -> list:
    now = datetime.now(timezone.utc)
    out = []
    for row in rows:
        row = dict(row)
        if "age_days" in row:
            row["createdAt"] = (now - timedelta(days=row.pop("age_days"))).strftime("%Y-%m-%dT%H:%M:%SZ")
        if "age_minutes" in row:
            row["createdAt"] = (now - timedelta(minutes=row.pop("age_minutes"))).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append(row)
    return out


def _issue_list(argv: list) -> list:
    scenario = os.environ.get("FAKE_GH_SCENARIO", "empty")
    if scenario == "empty" or not os.path.isfile(scenario):
        return []
    with open(scenario, encoding="utf-8") as handle:
        data = json.load(handle)
    if "--search" not in argv:
        return _rows(data.get("recent", []))
    search = argv[argv.index("--search") + 1]
    for response in data.get("responses", []):
        if response["match"] in search:
            return _rows(response["rows"])
    return []


def main() -> int:
    argv = sys.argv[1:]
    log = os.environ.get("FAKE_GH_LOG")
    if log:
        with open(log, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(argv) + "\n")
    if argv[:1] == ["--version"]:
        print("gh version 0.0.0-fake (test double)")
        return 0
    match = os.environ.get("FAKE_GH_MATCH")
    if match is None or match in " ".join(argv):
        delay = float(os.environ.get("FAKE_GH_SLEEP", "0") or 0)
        if delay > 0:
            time.sleep(delay)
        code = int(os.environ.get("FAKE_GH_EXIT", "0") or 0)
        if code:
            print("fake gh: failing on request", file=sys.stderr)
            return code
    if argv[:2] == ["issue", "list"]:
        print(json.dumps(_issue_list(argv)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
