#!/usr/bin/env python3
"""Direct unit tests for config_loader's shared `context:`-block editor.

`config_loader.find_context_block` (locate) and `config_loader.splice_context_block`
(replace-or-append) are the single shared home for the YAML `context:`-block
text surgery `init_project.py::merge_context_subkeys` and
`token_saver.py::_write_back` each need. Both consumers delegate locating the
block to `find_context_block`, but only `_write_back` rides the
replace-or-append splice — `merge_context_subkeys` keeps its own additive-only,
skip-if-present policy local (it must NEVER overwrite a user's already-set
value), which is exactly what the policy test below pins.

These tests cover the shared functions' own DIRECT call surface. The
consumer-level contracts (block-mapping replacement end-to-end, rollback on an
unparseable write, comment/flow-style preservation through a full
migrate-then-calibrate flow) are already pinned by test_config_write_integrity.py
and are not duplicated here.

Run with:  python -m pytest tests/test_config_loader_context_block.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader  # noqa: E402
import init_project as ip  # noqa: E402


# ---------------------------------------------------------------------------
# find_context_block — the shared LOCATE half
# ---------------------------------------------------------------------------
class TestFindContextBlock(unittest.TestCase):

    def test_locates_block_with_commented_subkeys(self):
        lines = (
            "project:\n"
            "  name: X\n"
            "# Context window tier.\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  # measured overhead\n"
            "  token_saver: false\n"
            "scoring:\n"
            "  priority_high: 30\n"
        ).split("\n")
        result = config_loader.find_context_block(lines)
        self.assertIsNotNone(result)
        header_idx, end, indent = result
        self.assertEqual(lines[header_idx], "context:")
        self.assertEqual(indent, "  ")
        # end is the index of the first line of the NEXT top-level key.
        self.assertEqual(lines[end], "scoring:")

    def test_indent_taken_from_first_indented_member_not_a_comment(self):
        lines = (
            "context:\n"
            "    # over-indented comment first\n"
            "  plan_tier: pro\n"
            "next_key:\n"
        ).split("\n")
        _header_idx, _end, indent = config_loader.find_context_block(lines)
        self.assertEqual(indent, "  ", "a comment line must not set the subkey indent")

    def test_trailing_blank_and_comment_lines_trimmed_from_block_end(self):
        lines = (
            "context:\n"
            "  plan_tier: pro\n"
            "\n"
            "# a comment introducing the NEXT key\n"
            "scoring:\n"
            "  priority_high: 30\n"
        ).split("\n")
        _header_idx, end, _indent = config_loader.find_context_block(lines)
        # block ends right after plan_tier, not swallowing the blank/comment run.
        self.assertEqual(lines[end - 1], "  plan_tier: pro")

    def test_block_at_end_of_file_has_no_following_top_level_key(self):
        # No trailing newline, so the split produces no trailing blank element
        # to trim — end lands exactly at len(lines).
        lines = "project:\n  name: X\ncontext:\n  plan_tier: pro".split("\n")
        _header_idx, end, _indent = config_loader.find_context_block(lines)
        self.assertEqual(end, len(lines))

    def test_absent_context_block_returns_none(self):
        lines = "project:\n  name: X\nscoring:\n  priority_high: 30\n".split("\n")
        self.assertIsNone(config_loader.find_context_block(lines))


# ---------------------------------------------------------------------------
# splice_context_block — the shared SPLICE half, replace path
# ---------------------------------------------------------------------------
class TestSpliceContextBlockReplace(unittest.TestCase):

    def test_replace_preserves_comments_and_key_order(self):
        text = (
            "project:\n"
            "  name: X\n"
            "context:\n"
            "  plan_tier: pro          # tier comment\n"
            "  token_saver: false      # engine off\n"
            "  context_window: 200000\n"
            "scoring:\n"
            "  priority_high: 30\n"
        )
        result = config_loader.splice_context_block(text, {"token_saver": "true"})
        self.assertIn("token_saver: true      # engine off", result)
        # Neighbouring lines and their comments are untouched, in original order.
        lines = result.split("\n")
        self.assertLess(
            lines.index("  plan_tier: pro          # tier comment"),
            lines.index("  token_saver: true      # engine off"),
        )
        self.assertLess(
            lines.index("  token_saver: true      # engine off"),
            lines.index("  context_window: 200000"),
        )
        self.assertIn("  priority_high: 30", result)

    def test_replace_matches_key_anywhere_in_text_not_only_inside_block(self):
        # The splice's key search is a whole-text regex, matching the original
        # implementation's targeted-line-editor behaviour (not block-scoped).
        text = 'plugin_version: "1.0.0"\ncontext:\n  plan_tier: pro\n'
        result = config_loader.splice_context_block(text, {"plugin_version": '"1.0.1"'})
        self.assertIn('plugin_version: "1.0.1"', result)
        self.assertNotIn("1.0.0", result)

    def test_block_style_child_replacement_leaves_no_orphans(self):
        text = (
            "context:\n"
            "  plan_tier: pro\n"
            "  token_saver_context_breakdown:\n"
            "    system_prompt: 2600\n"
            "    free_space: 975000\n"
            '  token_saver_overhead_measured_on: "2026-06-01"\n'
        )
        result = config_loader.splice_context_block(
            text, {"token_saver_context_breakdown": "{system_prompt: 3900}"}
        )
        self.assertNotIn("system_prompt: 2600", result)
        self.assertNotIn("free_space: 975000", result)
        self.assertIn("token_saver_context_breakdown: {system_prompt: 3900}", result)
        # The sibling key below the consumed block survives untouched.
        self.assertIn('token_saver_overhead_measured_on: "2026-06-01"', result)

    def test_block_parent_inline_comment_survives_child_consumption(self):
        text = (
            "context:\n"
            "  breakdown:   # measured per-category\n"
            "    a: 1\n"
            "    b: 2\n"
            "scoring:\n"
            "  priority_high: 30\n"
        )
        result = config_loader.splice_context_block(text, {"breakdown": "{c: 3}"})
        self.assertIn("# measured per-category", result)
        self.assertNotIn("a: 1", result)
        self.assertIn("breakdown: {c: 3}   # measured per-category", result)

    def test_lone_comment_under_a_valueless_key_is_not_swallowed(self):
        text = "context:\n  breakdown:\n    # not measured yet\n"
        result = config_loader.splice_context_block(text, {"breakdown": "{}"})
        self.assertIn("# not measured yet", result, "a lone note must survive")
        self.assertIn("breakdown: {}", result)

    def test_idempotent_re_splice(self):
        text = "context:\n  token_saver: false\n"
        once = config_loader.splice_context_block(text, {"token_saver": "true"})
        twice = config_loader.splice_context_block(once, {"token_saver": "true"})
        self.assertEqual(once, twice, "re-splicing the same value must be a no-op")


# ---------------------------------------------------------------------------
# splice_context_block — the shared SPLICE half, append path
# ---------------------------------------------------------------------------
class TestSpliceContextBlockAppend(unittest.TestCase):

    def test_missing_key_appended_under_context_block(self):
        text = "context:\n  plan_tier: pro\nscoring:\n  priority_high: 30\n"
        result = config_loader.splice_context_block(text, {"token_saver": "true"})
        lines = result.split("\n")
        self.assertIn("  token_saver: true", lines)
        # Appended strictly before the next top-level key.
        self.assertLess(lines.index("  token_saver: true"), lines.index("scoring:"))

    def test_absent_context_block_appends_at_end_of_text(self):
        text = "project:\n  name: X\n"
        result = config_loader.splice_context_block(text, {"token_saver": "true"})
        self.assertTrue(result.rstrip("\n").endswith("  token_saver: true"))

    def test_mixed_replace_and_append_in_one_call(self):
        text = "context:\n  plan_tier: pro\n"
        result = config_loader.splice_context_block(
            text, {"plan_tier": "max", "token_saver": "true"}
        )
        self.assertIn("plan_tier: max", result)
        self.assertIn("token_saver: true", result)


# ---------------------------------------------------------------------------
# File round-trip — the boundary that owns CRLF/LF normalization (Path's own
# universal-newlines read/write, untouched by this refactor); this proves the
# pure text function composes cleanly with the real file read/write path.
# ---------------------------------------------------------------------------
class TestSpliceContextBlockFileRoundTrip(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pw_context_block_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_file_round_trip_preserves_untouched_lines_and_comments(self):
        path = self.tmp / "config.yaml"
        original = (
            "project:\n"
            "  name: RoundTrip\n"
            "context:\n"
            "  plan_tier: pro          # tier comment\n"
            "  token_saver: false      # engine off\n"
            "scoring:\n"
            "  priority_high: 30\n"
        )
        path.write_text(original, encoding="utf-8")

        text = path.read_text(encoding="utf-8")
        text = config_loader.splice_context_block(text, {"token_saver": "true"})
        config_loader.write_config_checked(path, text)

        result = path.read_text(encoding="utf-8")
        self.assertIn("token_saver: true      # engine off", result)
        self.assertIn("plan_tier: pro          # tier comment", result)
        self.assertIn("priority_high: 30", result)


# ---------------------------------------------------------------------------
# merge_context_subkeys — REQUIRED policy regression gate
# ---------------------------------------------------------------------------
class TestMergeContextSubkeysSkipIfPresentPolicy(unittest.TestCase):
    """merge_context_subkeys must SKIP an existing sub-key, never replace it —
    the opposite policy from splice_context_block's replace-if-present.

    test_config_write_integrity.py::test_migrate_that_adds_a_key_is_idempotent
    cannot distinguish skip-if-present from replace-if-present: its fixture's
    sub-key values already equal the migrated defaults, so they read the same
    either way. This test uses NON-default, user-set values specifically so a
    future change that routes merge_context_subkeys through the shared
    replace-if-present splice function is caught here rather than silently
    shipping a --migrate that clobbers a user's calibration.
    """

    def test_non_default_user_value_survives_byte_identical(self):
        text = (
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n"
            "  token_saver: true\n"
            "  token_saver_runner_overhead: 26000\n"
        )
        result = ip.merge_context_subkeys(text)

        # The user's non-default values must be untouched, byte-for-byte —
        # NOT reset to the additions' defaults (false / 0).
        self.assertIn("  token_saver: true\n", result)
        self.assertIn("  token_saver_runner_overhead: 26000\n", result)

        # The absent sub-keys are still backfilled with their defaults.
        self.assertIn("token_saver_session_target: 150000", result)
        self.assertIn("token_saver_orchestrator_overhead: 0", result)
        self.assertIn("token_saver_context_breakdown: {}", result)


if __name__ == "__main__":
    unittest.main()
