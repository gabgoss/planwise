"""Tests for scripts/scoped_rules.py: rule scopes, globs, destinations, verdicts.

Every fixture tree is built under `tempfile.mkdtemp()` and removed in
`tearDown`; nothing is written under the plugin repo.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from scoped_rules import (
    INJECT_CONTENT_MAX_BYTES,
    LOOP_WRITTEN_HEADINGS,
    SIGNAL_EXCLUDED_HEADINGS,
    expand_braces,
    extract_destinations,
    glob_to_regex,
    load_rule_scopes,
    scoped_rules_block,
    split_paths_value,
    strip_loop_sections,
    strip_sections,
)

BEHAVIOUR_RULE = ".claude/rules/behaviour-rule.md"
PLACEMENT_RULE = ".claude/rules/placement-rule.md"


class _ScratchProject(unittest.TestCase):
    """A scratch project root with helpers to write rules, files and lessons."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scoped_rules_test_"))
        self.root = self.tmp / "project"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_rule(self, name, frontmatter, body="# Rule\n\nBody text.\n", root=None):
        """Write `.claude/rules/<name>` with the given frontmatter lines (None: no frontmatter)."""
        path = (root or self.root) / ".claude" / "rules" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        text = body if frontmatter is None else "---\n" + frontmatter + "\n---\n" + body
        path.write_bytes(text.encode("utf-8"))
        return path

    def write_sized_rule(self, name, paths, size, root):
        """Write a path-scoped rule file of exactly `size` bytes on disk."""
        head = f"---\ndescription: sized fixture\npaths: {paths}\n---\n# Sized\n".encode()
        pad = size - len(head) - 1
        self.assertGreater(pad, 0)
        path = root / ".claude" / "rules" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(head + b"x" * pad + b"\n")
        self.assertEqual(path.stat().st_size, size)
        return path

    def touch(self, rel, root=None):
        """Create an empty file at a project-relative path."""
        path = (root or self.root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content\n", encoding="utf-8")
        return path

    def config(self, root=None, lessons_dir=None):
        return {"_project_root": root or self.root, "_lessons_dir": lessons_dir}

    @staticmethod
    def table(*rows):
        """An item body carrying a `## Files Touched` table with the given (path, role) rows."""
        lines = ["# Item", "", "## Files Touched", "", "| File | Role | Why |", "|---|---|---|"]
        lines += [f"| `{p}` | {r} | fixture |" for p, r in rows]
        return "\n".join(lines + ["", "## Notes", "", "Nothing else."]) + "\n"


# ---------------------------------------------------------------------------
# paths: parsing
# ---------------------------------------------------------------------------

class TestPathsParsing(_ScratchProject):

    def test_unquoted_and_quoted_single_pattern(self):
        self.assertEqual(split_paths_value("src/**"), ["src/**"])
        self.assertEqual(split_paths_value('"**/*.py"'), ["**/*.py"])
        self.assertEqual(split_paths_value("'Docs/**'"), ["Docs/**"])
        self.assertEqual(split_paths_value('"src/**" # trailing comment'), ["src/**"])
        self.write_rule("behaviour-rule.md", 'description: d\npaths: "src/**"')
        scopes = load_rule_scopes(self.root)
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].patterns, ("src/**",))
        self.assertEqual(scopes[0].rel, BEHAVIOUR_RULE)
        self.assertEqual(scopes[0].description, "d")

    def test_comma_list_splits_outside_braces_only(self):
        self.assertEqual(split_paths_value("src/**, Docs/**"), ["src/**", "Docs/**"])
        self.assertEqual(split_paths_value('"**/*.{py,md}"'), ["**/*.{py,md}"])
        self.assertEqual(
            split_paths_value('"{src,Docs}/**", lib/*.{py,md}'),
            ["{src,Docs}/**", "lib/*.{py,md}"],
        )
        self.assertEqual(split_paths_value('"src/**, Docs/**"'), ["src/**", "Docs/**"])
        self.assertEqual(split_paths_value("src/**, , "), ["src/**"])

    def test_yaml_array_any_item_count(self):
        self.assertEqual(split_paths_value('\n  - "src/**"'), ["src/**"])
        self.assertEqual(
            split_paths_value('\n  - "src/**"\n  - Docs/**\n  - \'lib/*.{py,md}\''),
            ["src/**", "Docs/**", "lib/*.{py,md}"],
        )
        self.write_rule(
            "behaviour-rule.md",
            'description: array\npaths:\n  - "src/**"\n  - "Docs/**"\nplacement: false',
        )
        scopes = load_rule_scopes(self.root)
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].patterns, ("src/**", "Docs/**"))
        self.assertFalse(scopes[0].placement)

    def test_paths_only_in_a_fenced_example_yields_no_scope(self):
        fenced_body = (
            "# Example\n\nA rule is scoped like this:\n\n"
            "```yaml\n---\npaths: \"src/**\"\n---\n```\n"
        )
        self.write_rule("a-fenced-example.md", "description: shows paths in a fence", fenced_body)
        self.write_rule("b-scoped.md", 'description: real scope\npaths: "src/**"')
        scopes = load_rule_scopes(self.root)
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].rel, ".claude/rules/b-scoped.md")

    def test_placement_key_reads_true_only_for_true(self):
        cases = {
            "p1.md": "placement: true",
            "p2.md": 'placement: "true"',
            "p3.md": "placement: True",
            "p4.md": "placement: false",
            "p5.md": "placement: yes",
            "p6.md": "placement: truthy",
            "p7.md": "description: no key",
        }
        for name, extra in cases.items():
            self.write_rule(name, f'paths: "src/**"\n{extra}')
        flags = {Path(s.rel).name: s.placement for s in load_rule_scopes(self.root)}
        self.assertEqual(flags, {
            "p1.md": True, "p2.md": True, "p3.md": True,
            "p4.md": False, "p5.md": False, "p6.md": False, "p7.md": False,
        })

    def test_crlf_rule_file_yields_a_scope(self):
        path = self.root / ".claude" / "rules" / "behaviour-rule.md"
        path.parent.mkdir(parents=True)
        path.write_bytes(
            b"---\r\ndescription: crlf\r\npaths: \"src/**\"\r\nplacement: true\r\n---\r\n"
            b"# Rule\r\n\r\nBody.\r\n"
        )
        self.assertIn(b"\r\n", path.read_bytes())
        scopes = load_rule_scopes(self.root)
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].patterns, ("src/**",))
        self.assertTrue(scopes[0].placement)
        self.assertTrue(scopes[0].matches("src/a/b.py"))


# ---------------------------------------------------------------------------
# glob semantics
# ---------------------------------------------------------------------------

class TestGlob(unittest.TestCase):

    def assertMatches(self, pattern, path):
        self.assertIsNotNone(glob_to_regex(pattern).match(path), f"{pattern!r} should match {path!r}")

    def assertNoMatch(self, pattern, path):
        self.assertIsNone(glob_to_regex(pattern).match(path), f"{pattern!r} should not match {path!r}")

    def test_star_crosses_separators(self):
        self.assertMatches("src/*.py", "src/a.py")
        self.assertMatches("src/*.py", "src/a/b/c.py")
        self.assertMatches("*.md", "README.md")
        self.assertMatches("*.md", "Docs/a/b.md")
        self.assertNoMatch("*.md", "Docs/a.py")
        self.assertMatches("src/?.py", "src/a.py")
        self.assertNoMatch("src/?.py", "src/ab.py")
        self.assertNoMatch("src/?/x.py", "src///x.py")

    def test_double_star_and_trailing_dir_glob(self):
        self.assertMatches("**/*.md", "README.md")
        self.assertMatches("**/*.md", "docs/a/b.md")
        self.assertNoMatch("**/*.md", "docs/a/b.py")
        self.assertMatches("docs/**", "docs/a.md")
        self.assertMatches("docs/**", "docs/a/b/c.md")
        self.assertNoMatch("docs/**", "docs")
        self.assertNoMatch("docs/**", "other/docs/a.md")
        self.assertMatches("src/**/*.py", "src/a.py")
        self.assertMatches("src/**/*.py", "src/x/y/a.py")
        self.assertMatches("./src/**", "src/a.py")

    def test_brace_expansion_dir_and_ext(self):
        self.assertEqual(
            sorted(expand_braces("{src,Docs}/**/*.{py,md}")),
            sorted(["src/**/*.py", "src/**/*.md", "Docs/**/*.py", "Docs/**/*.md"]),
        )
        self.assertEqual(expand_braces("src/**"), ["src/**"])
        self.assertEqual(sorted(expand_braces("{a,{b,c}}/x")), ["a/x", "b/x", "c/x"])
        pattern = "{src,Docs}/**/*.{py,md}"
        self.assertMatches(pattern, "src/a.py")
        self.assertMatches(pattern, "Docs/x/b.md")
        self.assertNoMatch(pattern, "lib/a.py")
        self.assertNoMatch(pattern, "src/a.txt")

    def test_literal_pattern_matches_file_or_subtree(self):
        self.assertMatches("Docs", "Docs")
        self.assertMatches("Docs", "Docs/a.md")
        self.assertMatches("Docs/", "Docs/a/b.md")
        self.assertNoMatch("Docs", "Docsx/a.md")
        self.assertNoMatch("Docs", "other/Docs/a.md")
        self.assertMatches("src/main.py", "src/main.py")
        self.assertMatches("./src/main.py", "src/main.py")
        self.assertNoMatch("src/main.py", "src/main.pyc")
        self.assertNoMatch("src/a.b", "src/aXb")


# ---------------------------------------------------------------------------
# destinations
# ---------------------------------------------------------------------------

class TestDestinations(_ScratchProject):

    def test_preloaded_scopes_in_config_are_used_instead_of_a_reload(self):
        self.write_rule("behaviour-rule.md", 'paths: "src/**"')
        self.touch("src/edit.py")
        body = self.table(("src/edit.py", "EDIT"))
        self.assertEqual(scoped_rules_block("001", body, self.config())["rules_scanned"], 1)
        preloaded = {**self.config(), "_rule_scopes": []}
        block = scoped_rules_block("001", body, preloaded)
        self.assertEqual(block["rules_scanned"], 0)
        self.assertEqual(block["rules_to_inject"], [])

    def test_table_rows_win_and_read_rows_are_listed_unclassified(self):
        self.write_rule("behaviour-rule.md", 'paths: "src/**"')
        self.touch("src/edit.py")
        body = self.table(("src/edit.py", "EDIT"), ("src/new.py", "CREATE"), ("src/read.py", "READ"))
        body += "\nThe body also cites `lib/other.py`, which the table overrides.\n"
        dests, source, truncated = extract_destinations(body, self.root)
        self.assertEqual(source, "files-touched")
        self.assertFalse(truncated)
        self.assertEqual([(d.path, d.role) for d in dests],
                         [("src/edit.py", "EDIT"), ("src/new.py", "CREATE"), ("src/read.py", "READ")])
        self.assertEqual([d.exists for d in dests], [True, False, False])
        self.assertEqual({d.source for d in dests}, {"files-touched"})
        block = scoped_rules_block("001", body, self.config())
        read = next(d for d in block["destinations"] if d["role"] == "READ")
        self.assertEqual(read["verdict"], "none")
        self.assertEqual(read["rules"], [])
        self.assertEqual(read["placement_rules"], [])
        edit = next(d for d in block["destinations"] if d["role"] == "EDIT")
        self.assertEqual(edit["rules"], [BEHAVIOUR_RULE])
        empty = "# Item\n\n## Files Touched\n\n| File | Role |\n|---|---|\n\nCites `lib/x.py`.\n"
        dests, source, _ = extract_destinations(empty, self.root)
        self.assertEqual(source, "body")
        self.assertEqual([d.path for d in dests], ["lib/x.py"])

    def test_body_paths_strip_line_suffix_and_skip_globs_urls_and_fences(self):
        lines = [
            "Edit `src/a.py:12` and `src/b.py:3-9` and `src/c.py,` then `src/a.py` again.",
            "Skip `src/**/*.py`, `https://example.com/a/b.md`, `--flag/x.y`, `~/a/b.md`.",
            "Skip `src/dir`, `{x}/a.md`, `$ROOT/a.md`, `a/<n>.md`, `run(a/b.py)`, `a|b/c.md`.",
            "Skip `plain.py` (no slash).",
            "```",
            "`src/fenced.py`",
            "```",
            "~~~",
            "`src/tilde_fenced.py`",
            "~~~",
            "End `Docs/guide.md.`",
        ]
        body = "\n".join(lines)
        dests, source, truncated = extract_destinations(body, self.root)
        self.assertEqual(source, "body")
        self.assertFalse(truncated)
        self.assertEqual([d.path for d in dests], ["src/a.py", "src/b.py", "src/c.py", "Docs/guide.md"])
        many = " ".join(f"`src/f{i:03d}.py`" for i in range(60))
        dests, _, truncated = extract_destinations(many, self.root)
        self.assertTrue(truncated)
        self.assertEqual(len(dests), 50)
        self.assertEqual(dests[0].path, "src/f000.py")

    def test_body_path_role_from_existence(self):
        self.touch("src/exists.py")
        dests, source, _ = extract_destinations("Fix `src/exists.py` and add `src/new.py`.", self.root)
        self.assertEqual(source, "body")
        roles = {d.path: (d.role, d.exists, d.source) for d in dests}
        self.assertEqual(roles, {
            "src/exists.py": ("EDIT", True, "body"),
            "src/new.py": ("CREATE", False, "body"),
        })

    def test_loop_written_section_is_excluded_and_a_fenced_heading_does_not_open_one(self):
        self.assertEqual(LOOP_WRITTEN_HEADINGS, ("Loop Decision Needed",))
        lines = [
            "Intro cites `src/keep.py`.",
            "",
            "```markdown",
            "## Loop Decision Needed",
            "```",
            "After the fence cites `src/after_fence.py`.",
            "",
            "## Loop Decision Needed",
            "",
            "The loop wrote `src/loop.py` here.",
            "```",
            "## Not a heading",
            "```",
            "",
            "## Next",
            "Next cites `src/next.py`.",
        ]
        body = "\n".join(lines)
        stripped, removed = strip_loop_sections(body)
        self.assertEqual(removed, 7)
        self.assertNotIn("src/loop.py", stripped)
        self.assertNotIn("## Not a heading", stripped)
        self.assertIn("src/after_fence.py", stripped)
        self.assertEqual(stripped.count("## Loop Decision Needed"), 1)
        dests, _, _ = extract_destinations(body, self.root)
        self.assertEqual([d.path for d in dests], ["src/keep.py", "src/after_fence.py", "src/next.py"])
        tail = "Cites `src/keep.py`.\n\n## Loop Decision Needed\n\nWrote `src/loop.py`."
        stripped, removed = strip_loop_sections(tail)
        # A section that ends the body also takes the blank line before it.
        self.assertEqual(removed, 4)
        self.assertEqual(stripped, "Cites `src/keep.py`.")
        self.assertEqual(strip_loop_sections("no loop text"), ("no loop text", 0))
        # The count is the section's real line count plus the blank line before
        # a final section; a final newline adds no line.
        section = "\n".join(["## Loop Decision Needed"] + [f"line {i}" for i in range(1, 10)])
        self.assertEqual(strip_loop_sections("Intro.\n\n" + section + "\n"), ("Intro.", 11))
        self.assertEqual(strip_loop_sections("Intro.\n\n" + section), ("Intro.", 11))
        self.assertEqual(
            strip_loop_sections("Intro.\n\n" + section + "\n## Notes\n\nTail.\n"),
            ("Intro.\n\n## Notes\n\nTail.\n", 10),
        )

    def test_effective_count_is_the_same_for_a_legacy_section_and_its_folded_block(self):
        # The effective count is the item's line count with the section never
        # written, whether the section ends the body or sits before a heading.
        head = "# Item\n\n## Problem\n\nText.\n\n"
        related = "## Related\n\n- link\n\n---\n\n*Created: 2026-01-01*\n"
        legacy = (
            "\n## Loop Decision Needed\n\n<!-- loop-decision run=1 -->\n"
            "> [!gate] User input needed\n> Loop run 1.\n\nQuestion?\n"
        )
        folded = "## Open Questions\n\n### Q1. Loop decision (run 1)\n<!-- loop-decision run=1 -->\nQuestion?\n\nAnswer:\n\n"
        shapes = {
            "pristine": head + related,
            "legacy after the footer": head + related + legacy,
            "folded before Related": head + folded + related,
            "folded at the end": head + related.split("---")[0] + folded.rstrip("\n") + "\n",
            "legacy at the end": head + related.split("---")[0] + legacy.lstrip("\n"),
        }
        pristine_lines = shapes["pristine"].count("\n")
        no_footer_lines = (head + related.split("---")[0]).rstrip("\n").count("\n") + 1
        for name, body in shapes.items():
            stripped, removed = strip_sections(body, SIGNAL_EXCLUDED_HEADINGS)
            expected = no_footer_lines if name.endswith("at the end") else pristine_lines
            with self.subTest(shape=name):
                self.assertEqual(body.count("\n") - removed, expected)
                self.assertNotIn("Question?", stripped)

    def test_effective_count_is_the_same_with_a_stripped_section_before_the_final_run(self):
        # Each body pairs with the item that never had its excluded sections.
        # The final run takes every blank line back to the last kept text, so
        # an earlier stripped section changes neither the count nor the text.
        loop, end = "## Loop Decision Needed", "<!-- loop-decision-end -->"
        bounded = f"{loop}\nq\n{end}\n"
        shapes = {
            "marker-bounded then legacy": ("Intro.\n\n" + bounded + f"\n{loop}\nlegacy\n", "Intro.\n"),
            "Open Questions then legacy": (f"Intro.\n\n## Open Questions\nq\n\n{loop}\nlegacy\n", "Intro.\n"),
            "two runs, no blank between": ("Intro.\n\n" + bounded + bounded, "Intro.\n"),
            "two runs, one blank between": ("Intro.\n\n" + bounded + "\n" + bounded, "Intro.\n"),
            "two runs, two blanks between": ("Intro.\n\n" + bounded + "\n\n" + bounded, "Intro.\n"),
            "two runs, no blank before either": ("Intro.\n" + bounded + "\n" + bounded, "Intro.\n"),
            "mid-body run plus a final run": (
                f"Intro.\n\n## Open Questions\nq\n\n## Notes\nn\n\n{loop}\nlegacy\n",
                "Intro.\n\n## Notes\nn\n",
            ),
            "mid-body run plus a final run after two blanks": (
                f"Intro.\n\n## Open Questions\nq\n\n## Notes\nn\n\n\n{loop}\nlegacy\n",
                "Intro.\n\n## Notes\nn\n",
            ),
        }
        for name, (body, never_written) in shapes.items():
            stripped, removed = strip_sections(body, SIGNAL_EXCLUDED_HEADINGS)
            with self.subTest(shape=name):
                self.assertEqual(body.count("\n") - removed, never_written.count("\n"))
                # A final run also takes the newline that ended the last kept line.
                self.assertEqual(stripped, never_written[:-1])

    def test_effective_count_is_the_same_whatever_the_blank_lines_around_a_section(self):
        # A removed run also takes the blank-line separator it owns, so the
        # kept text joins with one separator, as the never-written item does.
        loop, end = "## Loop Decision Needed", "<!-- loop-decision-end -->"
        bounded, legacy = f"{loop}\nq\n{end}\n", f"{loop}\nq\n"
        notes = "\n## Notes\nn\n"
        # Each shape: (body, never-written item, kept text).
        shapes = {
            "marker-bounded mid-body, blank lines on both sides": (
                "Intro.\n\n" + bounded + notes, "Intro.\n\n## Notes\nn\n", "Intro.\n\n## Notes\nn\n"),
            "marker-bounded, then trailing blank lines": ("Intro.\n\n" + bounded + "\n\n", "Intro.\n", "Intro."),
            "legacy mid-body, blank lines on both sides": (
                "Intro.\n\n" + legacy + notes, "Intro.\n\n## Notes\nn\n", "Intro.\n\n## Notes\nn\n"),
            "legacy, then trailing blank lines": ("Intro.\n\n" + legacy + "\n\n", "Intro.\n", "Intro."),
            "two marker-bounded runs mid-body": (
                "Intro.\n\n" + bounded + "\n" + bounded + notes, "Intro.\n\n## Notes\nn\n", "Intro.\n\n## Notes\nn\n"),
            "marker-bounded run that opens the body": (bounded + "\nText.\n", "Text.\n", "Text.\n"),
            "no blank before, the blank after stays": (
                "Intro.\n" + bounded + notes, "Intro.\n\n## Notes\nn\n", "Intro.\n\n## Notes\nn\n"),
            "blank before, no blank after": (
                "Intro.\n\n" + bounded + notes.lstrip("\n"), "Intro.\n\n## Notes\nn\n", "Intro.\n\n## Notes\nn\n"),
        }
        for name, (body, never_written, kept) in shapes.items():
            stripped, removed = strip_sections(body, SIGNAL_EXCLUDED_HEADINGS)
            with self.subTest(shape=name):
                self.assertEqual(body.count("\n") - removed, never_written.count("\n"))
                self.assertEqual(stripped, kept)

    def test_absolute_paths_relativize_or_drop(self):
        outside = Path(tempfile.mkdtemp(prefix="scoped_rules_outside_"))
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        inside_abs = f"{self.root.as_posix()}/src/abs.py"
        outside_abs = f"{outside.as_posix()}/x/y.py"
        self.assertRegex(inside_abs, r"^([A-Za-z]:)?/")
        body = f"Edit `{inside_abs}` but not `{outside_abs}` or `/elsewhere/z.py`; also `./src/rel.py`."
        dests, source, _ = extract_destinations(body, self.root)
        self.assertEqual(source, "body")
        self.assertEqual([d.path for d in dests], ["src/abs.py", "src/rel.py"])
        if inside_abs[1:2] == ":":
            swapped = inside_abs[0].swapcase() + inside_abs[1:]
            dests, _, _ = extract_destinations(f"Edit `{swapped}`.", self.root)
            self.assertEqual([d.path for d in dests], ["src/abs.py"])

    def test_path_only_under_open_questions_is_not_a_destination(self):
        self.write_rule("behaviour-rule.md", 'paths: "src/**"')
        self.touch("src/kept.py")
        self.touch("src/asked.py")
        body = (
            "# Item\n\n## Resolution\n\n1. Edit `src/kept.py`.\n\n"
            "## Open Questions\n\n### Q1. Should `src/asked.py` change too?\n\nAnswer:\n\n"
            "---\n\n*Created: 2026-01-01*\n"
        )
        block = scoped_rules_block("001", body, self.config())
        self.assertEqual([d["path"] for d in block["destinations"]], ["src/kept.py"])
        # Control: the same path under another heading is a destination.
        moved = body.replace("## Open Questions", "## Notes")
        block = scoped_rules_block("001", moved, self.config())
        self.assertEqual([d["path"] for d in block["destinations"]], ["src/kept.py", "src/asked.py"])


# ---------------------------------------------------------------------------
# classify and the block (one test per worked case)
# ---------------------------------------------------------------------------

class TestClassify(_ScratchProject):

    def write_owning_lesson(self, promoted_to="BB-001", target="[rule]"):
        lessons = self.tmp / "lessons"
        archive = lessons / "Archive"
        archive.mkdir(parents=True)
        (archive / "LL-001-PROC-Fixture.md").write_text(
            "---\nid: 001\ntitle: \"Fixture lesson\"\nstatus: ARCHIVED\n"
            f"promoted-to: {promoted_to}\npromotion-target: {target}\n---\n\n# Lesson\n",
            encoding="utf-8",
        )
        return lessons

    def test_edit_under_behaviour_rule_is_inject(self):
        self.write_rule("behaviour-rule.md", 'description: behaviour\npaths: "src/**"')
        self.write_rule("docs-rule.md", 'description: docs\npaths: "Docs/**"')
        self.write_rule("global-rule.md", "description: loads everywhere")
        self.touch("src/app/main.py")
        body = "# Item\n\nThe fix edits `src/app/main.py:40` to correct the parser.\n"
        block = scoped_rules_block("001", body, self.config())
        self.assertEqual(block["verdict"], "inject")
        self.assertEqual(block["source"], "body")
        self.assertEqual(block["rules_to_inject"], [BEHAVIOUR_RULE])
        self.assertEqual(block["destinations"][0]["role"], "EDIT")
        self.assertTrue(block["destinations"][0]["exists"])
        self.assertEqual(block["owning_lessons"], [])
        self.assertFalse(block["truncated"])
        # rules_scanned counts the path-scoped rules only; the global rule is not one.
        self.assertEqual(block["rules_scanned"], 2)
        self.assertEqual(block["inject_form"], "content")
        self.assertEqual(block["rules_bytes"], (self.root / BEHAVIOUR_RULE).stat().st_size)
        # The byte cap flips the injection form at INJECT_CONTENT_MAX_BYTES.
        self.assertEqual(INJECT_CONTENT_MAX_BYTES, 8192)
        for size_b, form in ((4096, "content"), (4097, "paths")):
            root = self.tmp / f"cap_{size_b}"
            self.touch("src/app/main.py", root=root)
            self.write_sized_rule("a-rule.md", '"src/**"', 4096, root)
            self.write_sized_rule("b-rule.md", '"src/app/**"', size_b, root)
            capped = scoped_rules_block("001", body, self.config(root=root))
            self.assertEqual(capped["verdict"], "inject")
            self.assertEqual(capped["rules_scanned"], 2)
            self.assertEqual(capped["rules_bytes"], 4096 + size_b)
            self.assertEqual(capped["inject_form"], form)

    def test_create_under_placement_rule_is_placement(self):
        self.write_rule("placement-rule.md", 'paths: "src/**"\nplacement: true')
        block = scoped_rules_block("001", self.table(("src/new_module.py", "CREATE")), self.config())
        self.assertEqual(block["verdict"], "placement")
        dest = block["destinations"][0]
        self.assertEqual(dest["verdict"], "placement")
        self.assertEqual(dest["placement_rules"], [PLACEMENT_RULE])
        self.assertFalse(dest["content_tree"])

    def test_create_under_behaviour_only_rule_is_inject(self):
        self.write_rule("behaviour-rule.md", 'paths: "src/**"')
        block = scoped_rules_block("001", self.table(("src/new_module.py", "CREATE")), self.config())
        self.assertEqual(block["verdict"], "inject")
        dest = block["destinations"][0]
        self.assertEqual(dest["rules"], [BEHAVIOUR_RULE])
        self.assertEqual(dest["placement_rules"], [])
        self.assertEqual(block["rules_to_inject"], [BEHAVIOUR_RULE])

    def test_create_in_content_tree_without_owning_lesson_is_placement(self):
        self.write_rule("behaviour-rule.md", 'paths: "src/**"')
        block = scoped_rules_block("001", self.table((".claude/rules/new-rule.md", "CREATE")), self.config())
        self.assertEqual(block["verdict"], "placement")
        dest = block["destinations"][0]
        self.assertTrue(dest["content_tree"])
        self.assertEqual(dest["rules"], [])
        self.assertEqual(dest["placement_rules"], [])
        self.assertEqual(block["inject_form"], "none")

    def test_body_cited_missing_content_tree_file_is_placement(self):
        self.write_rule("behaviour-rule.md", 'paths: ".claude/**"')
        body = "# Item\n\nThe old guidance in `.claude/rules/gone.md` says to do it this way.\n"
        block = scoped_rules_block("001", body, self.config())
        self.assertEqual(block["source"], "body")
        self.assertEqual(block["verdict"], "placement")
        dest = block["destinations"][0]
        self.assertEqual((dest["path"], dest["role"], dest["exists"]), (".claude/rules/gone.md", "CREATE", False))
        self.assertTrue(dest["content_tree"])

    def test_owning_lesson_exempts_every_destination(self):
        self.write_rule("placement-rule.md", 'paths: "src/**"\nplacement: true')
        lessons = self.write_owning_lesson()
        body = self.table(("src/new_module.py", "CREATE"), (".claude/rules/new-rule.md", "CREATE"))
        block = scoped_rules_block("001", body, self.config(lessons_dir=lessons))
        self.assertEqual(block["owning_lessons"], ["LL-001-PROC-Fixture"])
        self.assertEqual(block["verdict"], "inject")
        self.assertEqual([d["verdict"] for d in block["destinations"]], ["inject", "none"])
        self.assertEqual(block["rules_to_inject"], [PLACEMENT_RULE])
        unowned = scoped_rules_block("002", body, self.config(lessons_dir=lessons))
        self.assertEqual(unowned["owning_lessons"], [])
        self.assertEqual(unowned["verdict"], "placement")

    def test_edit_in_content_tree_without_owning_lesson_is_inject(self):
        self.write_rule("behaviour-rule.md", 'paths: ".claude/rules/**"')
        self.write_rule("existing.md", "description: an existing global rule")
        block = scoped_rules_block("001", self.table((".claude/rules/existing.md", "EDIT")), self.config())
        self.assertEqual(block["verdict"], "inject")
        dest = block["destinations"][0]
        self.assertEqual((dest["role"], dest["exists"], dest["content_tree"]), ("EDIT", True, True))
        self.assertEqual(dest["rules"], [BEHAVIOUR_RULE])

    def test_read_row_never_matches(self):
        self.write_rule("placement-rule.md", 'paths: "src/**"\nplacement: true')
        self.touch("src/a.py")
        block = scoped_rules_block("001", self.table(("src/a.py", "READ")), self.config())
        self.assertEqual(block["verdict"], "none")
        dest = block["destinations"][0]
        self.assertEqual((dest["verdict"], dest["rules"], dest["placement_rules"]), ("none", [], []))
        self.assertEqual(block["rules_to_inject"], [])
        self.assertEqual(block["inject_form"], "none")

    def test_no_destinations_is_none(self):
        self.write_rule("behaviour-rule.md", 'paths: "src/**"')
        body = "# Item\n\nA prose-only item with `a_flag` and no path-like span.\n"
        block = scoped_rules_block("001", body, self.config())
        self.assertEqual(block["verdict"], "none")
        self.assertEqual(block["source"], "none")
        self.assertEqual(block["destinations"], [])
        self.assertEqual(block["rules_to_inject"], [])
        self.assertEqual(block["rules_bytes"], 0)
        self.assertEqual(block["inject_form"], "none")
        self.assertEqual(block["rules_scanned"], 1)


if __name__ == "__main__":
    unittest.main()
