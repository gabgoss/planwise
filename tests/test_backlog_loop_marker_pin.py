"""Cross-pin: the marker the Python script prints must match the regex the TypeScript hooks module reads."""

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES_TS = HERE.parent / "plugins" / "planwise" / "hooks" / "loop" / "names.ts"
SCRIPTS_DIR = HERE.parent / "plugins" / "planwise" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import backlog_loop


def _marker_pattern() -> "re.Pattern[str]":
    """Compile the MARKER_RE literal from names.ts, read at call time."""
    source = NAMES_TS.read_text(encoding="utf-8")
    found = re.search(r"^export const MARKER_RE = /(.+)/[a-z]*\s*$", source, re.MULTILINE)
    assert found is not None, "MARKER_RE literal not found in names.ts"
    return re.compile(found.group(1), re.MULTILINE)


class MarkerPinTest(unittest.TestCase):
    def test_python_marker_matches_typescript_regex(self):
        state = "C:/Users/some user/My Project/Backlog-Runs/run-1.json"
        line = backlog_loop.MARKER_FORMAT.format(run="r1", done="BB-1", remaining=2, state=state)
        match = _marker_pattern().search(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.groups(), ("r1", "BB-1", "2", state))

    def test_paraphrase_does_not_match(self):
        text = "Backlog loop finished: run=X done=Y remaining=0 state=Z"
        self.assertIsNone(_marker_pattern().search(text))


if __name__ == "__main__":
    unittest.main()
