#!/usr/bin/env python3
"""Selftests for the fixture engine (harness/fixtures.py).

Pure/mocked, $0: `invoke.run_case` is ALWAYS monkeypatched here -- the
`fx-initialized` template build is priced at one T4 case (~$0.71-0.74) and
must never be driven live from a selftest. Tests that touch the module
registry / template cache restore both to their pre-test state on
cleanup, so a registration made by one test never leaks into another.

Run with:
  C:/Python314/python.exe -m pytest -c evals/pytest.ini evals/selftest/test_fixtures.py
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness import fixtures, invoke, scratch


def _make_scratch(tmp: Path, run_id: str) -> scratch.ScratchRoot:
    return scratch.ScratchRoot.create(
        run_id=run_id, base_temp=tmp / "base",
        transcripts_root=tmp / "transcripts",
    )


def _ok_invoke_result(stdout: str) -> invoke.InvokeResult:
    return invoke.InvokeResult(
        outcome="ok", returncode=0, stdout=stdout, stderr="", tier="T4", timeout_s=600,
    )


def _init_envelope_stdout() -> str:
    """A minimal-but-valid init envelope: init event first, result event
    last, `is_error:false`.
    """
    return json.dumps([
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "is_error": False},
    ])


class TestRegistryContract(unittest.TestCase):
    def setUp(self):
        saved_fixtures = dict(fixtures.FIXTURES)
        saved_cache = dict(fixtures._TEMPLATE_CACHE)

        def _restore():
            fixtures.FIXTURES.clear()
            fixtures.FIXTURES.update(saved_fixtures)
            fixtures._TEMPLATE_CACHE.clear()
            fixtures._TEMPLATE_CACHE.update(saved_cache)

        self.addCleanup(_restore)

    def test_derive_registers_exactly_one_entry_with_a_callable(self):
        before = len(fixtures.FIXTURES)

        builder = fixtures.derive("fx-selftest-probe", base="empty")

        self.assertEqual(len(fixtures.FIXTURES), before + 1)
        self.assertIn("fx-selftest-probe", fixtures.FIXTURES)
        self.assertTrue(callable(fixtures.FIXTURES["fx-selftest-probe"]))
        self.assertIs(fixtures.FIXTURES["fx-selftest-probe"], builder)

    def test_unknown_base_raises(self):
        with self.assertRaises(ValueError):
            fixtures.derive("fx-selftest-bad-base", base="not-a-real-base")

    def test_s01_fixtures_are_registered_at_import_time(self):
        self.assertIn("fx-empty-contained", fixtures.FIXTURES)
        self.assertIn("fx-initialized", fixtures.FIXTURES)


class TestEmptyContained(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fixtures_selftest_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.scratch = _make_scratch(self.tmp, "empty")

    def test_yields_a_fresh_empty_dir(self):
        case_dir = fixtures.FIXTURES["fx-empty-contained"](self.scratch)

        self.assertTrue(case_dir.is_dir())
        self.assertEqual(list(case_dir.iterdir()), [])
        self.assertTrue(case_dir.is_relative_to(self.scratch.root))

    def test_two_consumptions_get_different_dirs(self):
        first = fixtures.FIXTURES["fx-empty-contained"](self.scratch)
        second = fixtures.FIXTURES["fx-empty-contained"](self.scratch)

        self.assertNotEqual(first, second)


class TestInitializedTemplate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fixtures_selftest_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(fixtures._TEMPLATE_CACHE.clear)

        self.plugin_source = self.tmp / "plugin-src"
        (self.plugin_source / "handlers").mkdir(parents=True)
        (self.plugin_source / "handlers" / "init.md").write_text("init handler\n")

        self.scratch = _make_scratch(self.tmp, "tmpl")
        self.scratch.copy_plugin_subtree(self.plugin_source)

    def _write_init_write_set(self, template_dir: Path) -> None:
        for rel in fixtures.INIT_WRITE_SET:
            target = template_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("seed\n")

    def test_requires_the_plugin_copy_to_exist_first(self):
        bare_scratch = _make_scratch(self.tmp, "no-copy")

        with patch.object(fixtures.invoke, "run_case") as mock_run_case:
            with self.assertRaises(fixtures.FixtureBuildError):
                fixtures.FIXTURES["fx-initialized"](bare_scratch)
        mock_run_case.assert_not_called()

    def test_drives_init_with_all_six_injected_flags_and_trusts_a_matching_write_set(self):
        captured = {}

        def _fake_run_case(prompt, plugin_dir, cwd, tier):
            captured["prompt"] = prompt
            captured["plugin_dir"] = plugin_dir
            captured["cwd"] = cwd
            captured["tier"] = tier
            self._write_init_write_set(Path(cwd))
            return _ok_invoke_result(_init_envelope_stdout())

        with patch.object(fixtures.invoke, "run_case", side_effect=_fake_run_case):
            case_dir = fixtures.FIXTURES["fx-initialized"](self.scratch)

        # The command shape: every one of the six values injected
        # explicitly, never left to an interactive/implicit default.
        prompt = captured["prompt"]
        self.assertIn("/planwise init", prompt)
        for flag in ("--name", "--root", "--dirs", "--scope", "--tier", "--token-saver"):
            self.assertIn(flag, prompt)
        self.assertEqual(captured["plugin_dir"], self.scratch.plugin_copy)
        self.assertEqual(captured["tier"], "T4")

        # The per-case consumption is its own copy, distinct from the
        # cached template dir, and carries the full trusted write set.
        self.assertTrue(case_dir.is_dir())
        for rel in fixtures.INIT_WRITE_SET:
            self.assertTrue((case_dir / rel).exists())

    def test_build_once_per_run_reuses_the_cached_template(self):
        calls = {"n": 0}

        def _fake_run_case(prompt, plugin_dir, cwd, tier):
            calls["n"] += 1
            self._write_init_write_set(Path(cwd))
            return _ok_invoke_result(_init_envelope_stdout())

        with patch.object(fixtures.invoke, "run_case", side_effect=_fake_run_case):
            fixtures.FIXTURES["fx-initialized"](self.scratch)
            fixtures.FIXTURES["fx-initialized"](self.scratch)

        self.assertEqual(calls["n"], 1)

    def test_write_set_mismatch_refuses_to_trust_the_template(self):
        def _fake_run_case(prompt, plugin_dir, cwd, tier):
            # Deliberately incomplete: only seed part of the pinned set --
            # the failing arm the set-equality check exists to catch.
            partial = list(fixtures.INIT_WRITE_SET)[:3]
            for rel in partial:
                target = Path(cwd) / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("seed\n")
            return _ok_invoke_result(_init_envelope_stdout())

        with patch.object(fixtures.invoke, "run_case", side_effect=_fake_run_case):
            with self.assertRaises(fixtures.FixtureBuildError):
                fixtures.FIXTURES["fx-initialized"](self.scratch)

    def test_a_non_ok_capture_outcome_refuses(self):
        def _fake_run_case(prompt, plugin_dir, cwd, tier):
            return invoke.InvokeResult(
                outcome="timeout", returncode=None, stdout="", stderr="",
                tier="T4", timeout_s=600,
            )

        with patch.object(fixtures.invoke, "run_case", side_effect=_fake_run_case):
            with self.assertRaises(fixtures.FixtureBuildError):
                fixtures.FIXTURES["fx-initialized"](self.scratch)

    def test_a_degenerate_envelope_refuses(self):
        with patch.object(fixtures.invoke, "run_case",
                           return_value=_ok_invoke_result("not-json")):
            with self.assertRaises(fixtures.FixtureBuildError):
                fixtures.FIXTURES["fx-initialized"](self.scratch)


class TestMutationHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fixtures_selftest_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_mutate_write_bytes_is_byte_pinned(self):
        case_dir = self.tmp / "case"
        case_dir.mkdir()
        mutate = fixtures.mutate_write_bytes("nested/file.bin", b"\r\n\x00pinned")

        mutate(case_dir)

        self.assertEqual((case_dir / "nested" / "file.bin").read_bytes(), b"\r\n\x00pinned")

    def test_mutate_delete_removes_an_existing_file(self):
        case_dir = self.tmp / "case"
        case_dir.mkdir()
        (case_dir / "doomed.txt").write_text("bye\n")
        mutate = fixtures.mutate_delete("doomed.txt")

        mutate(case_dir)

        self.assertFalse((case_dir / "doomed.txt").exists())

    def test_mutate_delete_on_a_missing_file_is_a_noop(self):
        case_dir = self.tmp / "case"
        case_dir.mkdir()
        mutate = fixtures.mutate_delete("never-existed.txt")

        mutate(case_dir)  # must not raise

    def test_mutate_yaml_key_sets_a_top_level_key(self):
        case_dir = self.tmp / "case"
        case_dir.mkdir()
        (case_dir / "config.yaml").write_text("existing: true\n")
        mutate = fixtures.mutate_yaml_key("config.yaml", "plugin_version", "1.2.3")

        mutate(case_dir)

        import yaml
        data = yaml.safe_load((case_dir / "config.yaml").read_text())
        self.assertEqual(data["plugin_version"], "1.2.3")
        self.assertTrue(data["existing"])


if __name__ == "__main__":
    unittest.main()
