"""A stand-in for the GitHub CLI that the feedback driver tests put first on PATH.

Every call appends its argv as one JSON line to the file named by FAKE_GH_LOG, then answers:

- `--version` prints a version line and exits 0.
- `issue list` prints a JSON array chosen by FAKE_GH_SCENARIO: `empty` (the default) prints `[]`;
  a path to a JSON file holding `{"responses": [{"match": "...", "rows": [...]}], "recent": [...]}`
  prints the rows of the first response whose `match` is a substring of the `--search` value, `[]`
  when none matches, and `recent` for a call without `--search`. A row may carry `age_days` or
  `age_minutes` in place of `createdAt`; the fake turns it into a UTC timestamp that long ago.
- `issue view N` prints one JSON object with `number`, `state` and `labels`, in the shape a real
  `gh issue view N --json number,state,labels` prints. The scenario file's `views` map answers
  first: `{"views": {"42": {"state": "CLOSED", "labels": ["resolved"]}}}`. A `null` entry there
  makes the call fail. Without an entry, the fake answers from the first `responses` or `recent` row
  with that number, using its `state` and its optional `labels` list of names. An issue no row
  names prints an error and exits 1, as a real `gh` does for an unknown issue.
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


def _label(name: str) -> dict:
    """One label in the shape a real `gh issue view --json labels` prints: id, name, description, color."""
    return {"id": f"LA_fake_{name}", "name": name, "description": "", "color": "ededed"}


def _issue_view(argv: list) -> "dict | None":
    """The reply for `issue view N`, or None when the scenario knows no such issue."""
    scenario = os.environ.get("FAKE_GH_SCENARIO", "empty")
    if scenario == "empty" or not os.path.isfile(scenario) or len(argv) < 3:
        return None
    with open(scenario, encoding="utf-8") as handle:
        data = json.load(handle)
    number = argv[2]
    views = data.get("views", {})
    if number in views:
        view = views[number]
        if view is None:
            return None
        return {"labels": [_label(name) for name in view.get("labels", [])], "number": int(number), "state": view["state"]}
    rows = [row for response in data.get("responses", []) for row in response["rows"]] + data.get("recent", [])
    for row in rows:
        if str(row.get("number")) == number:
            return {"labels": [_label(name) for name in row.get("labels", [])], "number": int(number), "state": row.get("state", "OPEN")}
    return None


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
    if argv[:2] == ["issue", "view"]:
        view = _issue_view(argv)
        if view is None:
            print("fake gh: could not resolve to an issue", file=sys.stderr)
            return 1
        print(json.dumps(view))
    return 0


if __name__ == "__main__":
    sys.exit(main())
