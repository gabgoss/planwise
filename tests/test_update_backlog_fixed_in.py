"""Unit tests for update_backlog.py's `--fixed-in` writer.

`--fixed-in SHA` appends one dated `Fixed in:` line per fixing commit under
the item's `## Notes`, and `--completes SHA` marks the completing one. The
class was split out of test_update_backlog.py, and builds on
update_backlog_fixture.py like it.

Each test builds an isolated temp planwise tree; none mutate the live backlog.

Run with:  python -m pytest tests/test_update_backlog_fixed_in.py -q
"""

import sys
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for update_backlog_fixture

from update_backlog_fixture import _UpdateBacklogFixtureBase

SHA_SHORT = "a1b2c3d"
SHA_FIX = "a1b2c3d4e5f6a7b8"
SHA_DONE = "0123456789abcdef0123456789abcdef01234567"

class TestFixedIn(_UpdateBacklogFixtureBase):
    """`--fixed-in SHA` appends one dated `Fixed in:` line per fixing commit
    under the item's `## Notes`, and `--completes SHA` marks the completing
    one. It runs alone on an item that is already COMPLETE, archived or not,
    because the squash-merge commit exists only after the close. Every
    refusal writes nothing."""

    def _item(
        self,
        item_id: str,
        filename: str,
        *,
        status: str = "COMPLETE",
        archived: bool = True,
        notes: bool = True,
        eol: str = "\n",
        extra: list[str] | None = None,
    ) -> Path:
        lines = [
            "---", f"id: {item_id}", f"status: {status}", "created: 2026-11-18", "---",
            "", f"# {filename}", "", "## Summary", "", "A summary.", "",
        ]
        lines += extra or []
        if notes:
            lines += ["## Notes", "", "- an earlier note", ""]
        lines += [
            "## Related", "", "- [x](x.md) - file for this item", "",
            "---", "", "*Created: 2026-11-18*", "",
        ]
        target_dir = self.archive_dir if archived else self.backlog_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_bytes(eol.join(lines).encode("utf-8"))
        return path

    def _fixed_in(self, item_id: str, *extra: str) -> tuple[str, str, object]:
        self.write_index("")
        return self._run_main(["--config", str(self.config_path), "--id", item_id, *extra])

    @staticmethod
    def _section(text: str, heading: str) -> list[str]:
        lines = text.replace("\r\n", "\n").split("\n")
        start = lines.index(heading)
        end = next(
            (n for n in range(start + 1, len(lines)) if lines[n].startswith("## ")),
            len(lines),
        )
        return lines[start + 1:end]

    def _snapshot(self) -> dict[str, bytes]:
        return {str(p): p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()}

    def test_fixed_in_two_commits_one_marked_complete(self):
        path = self._item("201", "two-commits.md")

        out, err, code = self._fixed_in(
            "201", "--fixed-in", SHA_FIX, "--fixed-in", SHA_DONE, "--completes", SHA_DONE
        )

        self.assertIsNone(code, err)
        self.assertIn(f"Fixed in: recorded {SHA_FIX}", out)
        notes = [n for n in self._section(path.read_text(encoding="utf-8"), "## Notes") if n]
        self.assertEqual(notes[0], "- an earlier note")
        self.assertRegex(notes[1], rf"^- \d{{4}}-\d{{2}}-\d{{2}}: Fixed in: {SHA_FIX}$")
        self.assertRegex(
            notes[2], rf"^- \d{{4}}-\d{{2}}-\d{{2}}: Fixed in: {SHA_DONE} \(completes the fix\)$"
        )
        self.assertEqual(len(notes), 3)

    def test_fixed_in_standalone_append_on_an_archived_item_creates_the_notes_section(self):
        path = self._item("202", "archived-no-notes.md", notes=False)
        before = path.read_text(encoding="utf-8")
        self.assertNotIn("## Notes", before)

        _out, err, code = self._fixed_in("202", "--fixed-in", SHA_DONE, "--completes", SHA_DONE)

        self.assertIsNone(code, err)
        after = path.read_text(encoding="utf-8")
        self.assertEqual(after.count("## Notes"), 1)
        self.assertLess(after.index("## Notes"), after.index("## Related"))
        self.assertIn(f"Fixed in: {SHA_DONE} (completes the fix)", after)
        self.assertEqual(path.parent, self.archive_dir)
        self.assertTrue(after.endswith("*Created: 2026-11-18*\n"))

    def test_fixed_in_rerun_is_idempotent_and_matches_a_short_form_of_the_same_sha(self):
        path = self._item("203", "idempotent.md")
        self._fixed_in("203", "--fixed-in", SHA_FIX)
        after_first = path.read_bytes()

        out, err, code = self._fixed_in("203", "--fixed-in", SHA_FIX)
        self.assertIsNone(code, err)
        self.assertIn("already recorded", out)
        self.assertEqual(path.read_bytes(), after_first)

        out, err, code = self._fixed_in("203", "--fixed-in", SHA_SHORT)
        self.assertIsNone(code, err)
        self.assertIn("already recorded", out)
        self.assertEqual(path.read_bytes(), after_first)

    def test_fixed_in_a_new_sha_is_added_beside_a_recorded_one(self):
        path = self._item("204", "add-second.md")
        self._fixed_in("204", "--fixed-in", SHA_FIX)

        out, err, code = self._fixed_in(
            "204", "--fixed-in", SHA_FIX, "--fixed-in", SHA_DONE, "--completes", SHA_DONE
        )

        self.assertIsNone(code, err)
        self.assertIn(f"Fixed in: recorded {SHA_DONE}", out)
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(f"Fixed in: {SHA_FIX}"), 1)
        self.assertEqual(text.count(f"Fixed in: {SHA_DONE}"), 1)

    def test_fixed_in_with_status_complete_the_item_closes_and_records(self):
        self.write_index("| 205 | Open | Low | NOT_STARTED | DOC | - | [01](open.md) |\n")
        open_item = self._item("205", "open.md", status="NOT_STARTED", archived=False)

        out, err, code = self._run_main(
            [
                "--config", str(self.config_path), "--id", "205", "--status=COMPLETE",
                "--fixed-in", SHA_DONE, "--completes", SHA_DONE,
            ]
        )

        self.assertIsNone(code, err)
        self.assertIn("NOT_STARTED → COMPLETE", out)
        self.assertFalse(open_item.exists())
        moved = (self.archive_dir / "open.md").read_text(encoding="utf-8")
        self.assertIn("status: COMPLETE", moved)
        self.assertIn(f"Fixed in: {SHA_DONE} (completes the fix)", moved)

    def test_fixed_in_crlf_item_keeps_crlf_endings(self):
        path = self._item("206", "crlf.md", eol="\r\n")

        _out, err, code = self._fixed_in("206", "--fixed-in", SHA_FIX)

        self.assertIsNone(code, err)
        data = path.read_bytes()
        self.assertIn(f"Fixed in: {SHA_FIX}".encode(), data)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))

    def test_fixed_in_a_fenced_notes_heading_is_not_the_notes_section(self):
        path = self._item(
            "207", "fenced.md", notes=False, extra=["```", "## Notes", "- fenced", "```", ""]
        )

        _out, err, code = self._fixed_in("207", "--fixed-in", SHA_FIX)

        self.assertIsNone(code, err)
        text = path.read_text(encoding="utf-8")
        self.assertIn("```\n## Notes\n- fenced\n```", text)
        self.assertEqual(text.count("## Notes"), 2)
        self.assertLess(text.rindex("## Notes"), text.index("## Related"))
        self.assertGreater(text.index(f"Fixed in: {SHA_FIX}"), text.rindex("## Notes"))

    def test_fixed_in_each_refusal_exits_1_and_writes_nothing(self):
        self._item("208", "refusals.md")
        self._item("209", "not-complete.md", status="IN_PROGRESS", archived=False)
        cases = {
            "short sha": ("208", ["--fixed-in", "abc123"]),
            "non-hex sha": ("208", ["--fixed-in", "HEAD"]),
            "non-hex long sha": ("208", ["--fixed-in", "zzzzzzzzzz"]),
            "completes absent from fixed-in": (
                "208", ["--fixed-in", SHA_FIX, "--completes", SHA_DONE],
            ),
            "completes without fixed-in": ("208", ["--completes", SHA_FIX]),
            "item not COMPLETE": ("209", ["--fixed-in", SHA_FIX]),
            "status other than COMPLETE": (
                "208", ["--status=IN_PROGRESS", "--fixed-in", SHA_FIX],
            ),
            "with --create": (
                "208",
                ["--create", "--feature", "F", "--priority", "Low", "--abbrev", "DOC",
                 "--files", "new.md", "--fixed-in", SHA_FIX],
            ),
            "with --mark-needs-plan": (
                "208", ["--mark-needs-plan", "--fixed-in", SHA_FIX],
            ),
            "unknown id": ("999", ["--fixed-in", SHA_FIX]),
        }
        for name, (item_id, flags) in cases.items():
            with self.subTest(name):
                self.write_index("")
                before = self._snapshot()
                _out, err, code = self._run_main(
                    ["--config", str(self.config_path), "--id", item_id, *flags]
                )
                self.assertEqual(code, 1, err)
                self.assertIn("Error:", err)
                self.assertEqual(self._snapshot(), before)


if __name__ == "__main__":
    unittest.main()
