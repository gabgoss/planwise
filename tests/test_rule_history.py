#!/usr/bin/env python3
"""The rule-history manifest and its check in the shared divergence primitive.

A rule from an older release has no body in the current shipped file to be a
subset of, so the structural comparison reads its dropped blocks as a
customization. The shipped manifests/rule-history.json lists a digest of every
body each installed, de-scoped and style rule has shipped. `_classify_diverged`
returns SUBSET at exact confidence, source `shipped-history`, for an installed
body that matches any listed digest. Upgrade then adopts the shipped body with no
transfer.

These tests pin: an unedited older body is adopted with no transfer and no
upgrade-transfers folder; the same body without a manifest entry still
transfers; a customized body still classifies HAS_UNIQUE and transfers; the
preflight card marks the history row `no` for the agent; the fast path never
consults the structural primitive; a missing or malformed manifest degrades to
the structural comparison; and the shipped manifest lists the current body of
every rule (no git needed, so a shallow CI checkout is fine).

Run with:  python -m unittest tests/test_rule_history.py
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import doctor_cli
import init_project as ip  # noqa: F401 -- the scripts package's import root; resolves the import cycle
import rule_divergence
import structural_compare
import upgrade_preflight
from rule_registry import DESCOPED_RULES, INSTALLED_RULES
from style_rules import STYLE_RULES

from conftest import _UpgradeArtifactsFixtureBase, _verdict

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

_NAMING = (
    "## Naming\n\nName every agent file with a lowercase noun phrase joined by "
    "hyphens and keep it under forty characters.\n\n"
)
_LEGACY = (
    "## Legacy Checklist\n\nRun the legacy checklist before every release and "
    "record the result in the release notes by hand.\n\n"
)
_SCOPE = (
    "## Scope\n\nThis rule applies to every file under the agents directory and "
    "to nothing else in the project tree.\n"
)
_AUTOMATION = (
    "\n## Automation\n\nThe release workflow now runs the former checklist "
    "automatically and posts the result itself.\n"
)
OLD_BODY = "# Fixture Rule\n\n" + _NAMING + _LEGACY + _SCOPE
CURRENT_BODY = "# Fixture Rule\n\n" + _NAMING + _SCOPE + _AUTOMATION  # the checklist moved out
EDITED_BODY = OLD_BODY + (
    "\n## My Local Tweak\n\nKeep the custom reviewer name in every agent "
    "description so the team can find it quickly.\n"
)
CUSTOM_PATHS = ".claude/agents/**, custom/**"


class _HistoryFixture(_UpgradeArtifactsFixtureBase):
    """The upgrade fixture, with the manifest path moved into the temp tree.

    The patch hides the real shipped manifest, so no fixture body can match a
    real digest by accident. With no file written, `load_rule_history` returns {}.
    """

    def setUp(self):
        super().setUp()
        self.manifest_path = self.tmp / "rule-history.json"
        patch = mock.patch.object(rule_divergence, "RULE_HISTORY_MANIFEST", self.manifest_path)
        patch.start()
        self.addCleanup(patch.stop)

    def digest_of(self, body: str, paths_value: str | None = None) -> str:
        return rule_divergence.rule_history_digest(
            self._rule_text(body, paths_value or self.RULE_PATHS_TEMPLATE))

    def write_manifest(self, *digests: str) -> Path:
        self.manifest_path.write_text(
            json.dumps({"schema_version": 1, "rules": {self.RULE_FILENAME: list(digests)}}),
            encoding="utf-8")
        return self.manifest_path


class TestOlderShippedBodyIsAdopted(_HistoryFixture):
    def test_unedited_older_body_is_refreshed_with_no_transfer(self):
        self.enable_relocate()
        shipped_raw = self.write_shipped_rule(CURRENT_BODY).read_text(encoding="utf-8")
        installed = self.write_installed_rule(OLD_BODY, CUSTOM_PATHS)
        self.write_manifest(self.digest_of(OLD_BODY))

        refreshed, _unchanged, conflicts, _untracked, refreshed_subsets, transferred = self.run_upgrade()

        self.assertIn(str(installed), refreshed)
        self.assertIn(str(installed), refreshed_subsets)
        self.assertEqual(transferred, [], "an unedited older body holds nothing to transfer")
        self.assertEqual(conflicts, [])
        self.assertFalse(self.transfer_dir().exists(), "no upgrade-transfers folder is created")
        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(rule_divergence.normalize_rule_for_diff(updated),
                         rule_divergence.normalize_rule_for_diff(shipped_raw))
        self.assertEqual(rule_divergence._extract_paths_value(updated), CUSTOM_PATHS,
                         "the project's paths: value survives the adoption")

    def test_same_body_without_a_manifest_entry_still_transfers(self):
        """Direction control: with no history the primitive reads the dropped
        checklist as unique, so the test above discriminates the manifest."""
        self.enable_relocate()
        self.write_shipped_rule(CURRENT_BODY)
        self.write_installed_rule(OLD_BODY, CUSTOM_PATHS)

        _refreshed, _unchanged, _conflicts, _untracked, _subsets, transferred = self.run_upgrade()

        self.assertEqual(len(transferred), 1)
        self.assertIn("Legacy Checklist", Path(transferred[0][1]).read_text(encoding="utf-8"))

    def test_customized_body_still_transfers(self):
        self.enable_relocate()
        self.write_shipped_rule(CURRENT_BODY)
        installed = self.write_installed_rule(EDITED_BODY, CUSTOM_PATHS)
        self.write_manifest(self.digest_of(OLD_BODY))  # lists the unedited body only

        _refreshed, _unchanged, _conflicts, _untracked, refreshed_subsets, transferred = self.run_upgrade()

        self.assertNotIn(str(installed), refreshed_subsets)
        self.assertEqual(len(transferred), 1)
        self.assertIn("My Local Tweak", Path(transferred[0][1]).read_text(encoding="utf-8"))

    def test_customized_body_classifies_has_unique(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        verdict = rule_divergence._classify_diverged(
            rule_divergence.normalize_rule_for_diff(self._rule_text(EDITED_BODY, CUSTOM_PATHS)),
            rule_divergence.normalize_rule_for_diff(self._rule_text(CURRENT_BODY, self.RULE_PATHS_TEMPLATE)),
        )
        self.assertEqual(verdict.classification, "HAS_UNIQUE")
        self.assertNotEqual(verdict.source, "shipped-history")


class TestDispositionReasonNamesTheVerdictSource(_HistoryFixture):
    """The DISPOSITIONS.md row says why the shipped body was adopted. A history
    match reads "matched an earlier shipped body". A structural subset keeps the
    stale-subset text, so the history test below discriminates the source."""

    def disposition_log(self) -> str:
        log_path = (self.project_root / self.cfg.planwise_root / "upgrade-backups"
                    / "1.0.0-to-1.1.0" / "DISPOSITIONS.md")
        return log_path.read_text(encoding="utf-8")

    def test_history_adoption_row_names_the_earlier_shipped_body(self):
        self.enable_relocate()
        self.write_shipped_rule(CURRENT_BODY)
        self.write_installed_rule(OLD_BODY, CUSTOM_PATHS)
        self.write_manifest(self.digest_of(OLD_BODY))

        self.run_upgrade()

        log = self.disposition_log()
        self.assertIn("auto-adopted shipped", log)
        self.assertIn("matched an earlier shipped body", log)
        self.assertNotIn("stale subset", log)

    def test_structural_subset_adoption_row_keeps_the_stale_subset_text(self):
        """Direction control: no manifest entry, and a body that is a clean
        structural subset of the shipped body, so the source is not history."""
        self.enable_relocate()
        self.write_shipped_rule(CURRENT_BODY)
        installed = self.write_installed_rule("# Fixture Rule\n\n" + _NAMING, CUSTOM_PATHS)

        _refreshed, _unchanged, _conflicts, _untracked, refreshed_subsets, _moved = self.run_upgrade()

        self.assertIn(str(installed), refreshed_subsets, "the control must be a structural subset")
        log = self.disposition_log()
        self.assertIn("stale subset", log)
        self.assertNotIn("matched an earlier shipped body", log)


class TestClassifierFastPath(_HistoryFixture):
    def classify(self, body: str, paths_value: str = CUSTOM_PATHS, **kwargs):
        return rule_divergence._classify_diverged(
            rule_divergence.normalize_rule_for_diff(self._rule_text(body, paths_value)),
            rule_divergence.normalize_rule_for_diff(self._rule_text(CURRENT_BODY, self.RULE_PATHS_TEMPLATE)),
            **kwargs,
        )

    def test_history_match_returns_exact_subset_from_shipped_history(self):
        self.write_manifest(self.digest_of(OLD_BODY))

        verdict = self.classify(OLD_BODY)

        self.assertEqual((verdict.classification, verdict.confidence), ("SUBSET", "exact"))
        self.assertEqual(verdict.source, "shipped-history")
        self.assertEqual(verdict.unique_blocks, [])
        self.assertEqual(verdict.notes, "")
        self.assertTrue(rule_divergence._destructively_removable(verdict))
        self.assertFalse(rule_divergence._verdict_not_analyzed(verdict))

    def test_primitive_is_not_consulted_on_a_history_match(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        with mock.patch.object(structural_compare, "classify_blocks",
                               side_effect=AssertionError("the fast path must not run the primitive")):
            verdict = self.classify(OLD_BODY)
        self.assertEqual(verdict.source, "shipped-history")

    def test_history_match_beats_an_override_verdict(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        verdict = self.classify(OLD_BODY, override=_verdict("HAS_UNIQUE", "unique"))
        self.assertEqual(verdict.classification, "SUBSET")

    def test_override_is_returned_when_no_history_matches(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        override = _verdict("HAS_UNIQUE", "unique", unique_blocks=["x"])
        self.assertIs(self.classify(EDITED_BODY, override=override), override)

    def test_match_is_independent_of_the_installed_paths_value(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        self.assertEqual(self.classify(OLD_BODY, paths_value="other/**").source, "shipped-history")

    def test_crlf_rendering_matches(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        crlf = self._rule_text(OLD_BODY, CUSTOM_PATHS).replace("\n", "\r\n")
        verdict = rule_divergence._classify_diverged(
            rule_divergence.normalize_rule_for_diff(crlf.replace("\r\n", "\n")),
            rule_divergence.normalize_rule_for_diff(self._rule_text(CURRENT_BODY, self.RULE_PATHS_TEMPLATE)),
        )
        self.assertEqual(verdict.source, "shipped-history")
        self.assertEqual(rule_divergence.rule_history_digest(crlf),
                         rule_divergence.rule_history_digest(crlf.replace("\r\n", "\n")))

    def test_digest_is_idempotent_over_normalization(self):
        text = self._rule_text(OLD_BODY, CUSTOM_PATHS)
        self.assertEqual(rule_divergence.rule_history_digest(text),
                         rule_divergence.rule_history_digest(rule_divergence.normalize_rule_for_diff(text)))

    def test_one_byte_edit_changes_the_digest(self):
        self.assertNotEqual(self.digest_of(OLD_BODY), self.digest_of(OLD_BODY + "x\n"))

    def test_missing_manifest_degrades_to_the_primitive(self):
        self.assertEqual(rule_divergence.load_rule_history(), {})
        self.assertEqual(self.classify(OLD_BODY).classification, "HAS_UNIQUE")

    def test_malformed_manifest_is_ignored_not_fatal(self):
        for text in ("{not json", "[]", '{"rules": 5}', '{"schema_version": 1}'):
            with self.subTest(text=text):
                self.manifest_path.write_text(text, encoding="utf-8")
                self.assertEqual(rule_divergence.load_rule_history(), {})
                self.assertEqual(self.classify(OLD_BODY).classification, "HAS_UNIQUE")

    def test_manifest_is_read_once_across_many_classifications(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        real_read = Path.read_text
        reads: list[Path] = []

        def counting(path, *args, **kwargs):
            reads.append(path)
            return real_read(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", counting):
            for _ in range(5):
                self.classify(OLD_BODY)
        self.assertEqual([p for p in reads if p == self.manifest_path], [self.manifest_path])

    def test_a_rewritten_manifest_is_reloaded(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        self.assertEqual(self.classify(OLD_BODY).source, "shipped-history")
        self.write_manifest()  # an empty digest list is a different size
        self.assertEqual(self.classify(OLD_BODY).classification, "HAS_UNIQUE")

    def test_loader_returns_digest_sets_keyed_by_filename(self):
        self.write_manifest("a" * 64, "b" * 64)
        self.assertEqual(rule_divergence.load_rule_history(),
                         {self.RULE_FILENAME: {"a" * 64, "b" * 64}})


class TestPreflightRow(_HistoryFixture):
    def rows_for(self, body: str) -> list[dict]:
        self.write_shipped_rule(CURRENT_BODY)
        installed = self.write_installed_rule(body, CUSTOM_PATHS)
        row = {
            "filename": self.RULE_FILENAME,
            "installed": installed.relative_to(self.project_root).as_posix(),
            "shipped": (self.refs_dir / self.RULE_FILENAME).relative_to(self.plugin_root).as_posix(),
            "installed_sha256": "0" * 64,
        }
        with mock.patch.object(doctor_cli, "_list_diverged_rows", return_value=[row]):
            return upgrade_preflight.diverged_rows(self.cfg)

    def test_history_row_needs_no_agent(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        (row,) = self.rows_for(OLD_BODY)
        self.assertEqual((row["inline"], row["agent"]), ("SUBSET/exact", "no"))

    def test_customized_row_still_needs_the_agent(self):
        self.write_manifest(self.digest_of(OLD_BODY))
        (row,) = self.rows_for(EDITED_BODY)
        self.assertEqual((row["inline"], row["agent"]), ("HAS_UNIQUE/unique", "yes"))


class TestShippedManifest(unittest.TestCase):
    """The regeneration guard: every listed rule's CURRENT shipped body must be in
    the manifest, so a reference edit cannot land without
    `python tools/gen_rule_history.py`."""

    def setUp(self):
        path = PLUGIN / "manifests" / "rule-history.json"
        self.assertTrue(path.is_file(), f"missing {path}")
        self.assertEqual(path, rule_divergence.RULE_HISTORY_MANIFEST)
        self.doc = json.loads(path.read_text(encoding="utf-8"))
        self.listed = sorted({n for n, _ in INSTALLED_RULES} | {n for n, _ in DESCOPED_RULES}
                             | {n for n, _ in STYLE_RULES})

    def test_schema_and_normalization_are_declared(self):
        self.assertEqual(self.doc["schema_version"], 1)
        self.assertIn("rule_history_digest", self.doc["normalization"])

    def test_every_listed_rule_has_a_row(self):
        self.assertEqual(len(self.listed), 22)
        self.assertEqual(sorted(self.doc["rules"]), self.listed)
        for name, digests in self.doc["rules"].items():
            with self.subTest(rule=name):
                self.assertTrue(digests, f"{name} lists no digest")

    def test_every_rule_has_its_current_body_recorded(self):
        history = rule_divergence.load_rule_history()
        for name in self.listed:
            with self.subTest(rule=name):
                live = PLUGIN / "references" / name
                self.assertTrue(live.is_file(), f"references/{name} is not shipped")
                digest = rule_divergence.rule_history_digest(live.read_text(encoding="utf-8-sig"))
                self.assertIn(
                    digest, history.get(name, set()),
                    f"references/{name} was edited without regenerating the rule-history "
                    f"manifest. Run: python tools/gen_rule_history.py")


if __name__ == "__main__":
    unittest.main()
