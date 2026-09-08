#!/usr/bin/env python3
"""Guards the two plugin manifest version strings against a one-sided bump.

The plugin's version is declared in two places that must always agree:

  * the repo-root marketplace manifest (`.claude-plugin/marketplace.json`),
    which is what a consumer's marketplace listing resolves
  * the plugin manifest (`plugins/planwise/.claude-plugin/plugin.json`),
    which is what an installed plugin reports

Nothing enforces that a release bump touches both. This test makes a
one-sided bump fail `pytest` immediately, and covers the corrupt-JSON case
that a release checklist otherwise verifies by hand.

`manifest_versions()` is a small pure function so the equality check can be
exercised both against the real on-disk manifests (the load-bearing case)
and against scratch temp-dir copies that prove the check actually
discriminates: a desynced pair fails the equality assertion, and invalid
JSON in either file raises rather than being silently swallowed.

Run with:  python -m pytest tests/test_manifest_version_sync.py -q
"""

import json
import tempfile
import unittest
from pathlib import Path

MARKETPLACE_REL = Path(".claude-plugin") / "marketplace.json"
PLUGIN_REL = Path("plugins") / "planwise" / ".claude-plugin" / "plugin.json"


def manifest_versions(repo_root: Path) -> tuple[str, str]:
    """Return (marketplace_version, plugin_version) read from the two
    manifests under `repo_root`.

    Both files are parsed as JSON before either `version` value is read, so
    a `json.JSONDecodeError` on either manifest propagates to the caller
    instead of being masked by a `KeyError` on the other.
    """
    marketplace_path = repo_root / MARKETPLACE_REL
    plugin_path = repo_root / PLUGIN_REL

    marketplace_data = json.loads(marketplace_path.read_text(encoding="utf-8"))
    plugin_data = json.loads(plugin_path.read_text(encoding="utf-8"))

    return marketplace_data["version"], plugin_data["version"]


class TestManifestVersionsLiveTree(unittest.TestCase):
    """The load-bearing guard: assert against the real, on-disk manifests."""

    def test_live_manifests_parse_and_agree(self):
        repo_root = Path(__file__).resolve().parent.parent

        marketplace_version, plugin_version = manifest_versions(repo_root)

        self.assertEqual(
            marketplace_version,
            plugin_version,
            f"marketplace.json version {marketplace_version!r} does not match "
            f"plugin.json version {plugin_version!r} -- a release bumped only "
            "one manifest; edit both to the same version",
        )


class TestManifestVersionsDiscriminate(unittest.TestCase):
    """Proves the guard actually discriminates, on scratch copies only.

    Never touches the real manifests: each test builds its own temp-dir
    tree at the same relative layout `manifest_versions()` expects, so a
    desynced pair is shown to fail and corrupt JSON is shown to raise.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="pw_manifest_sync_")
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def _write_tree(self, marketplace_text: str, plugin_text: str) -> Path:
        marketplace_path = self.tmp_path / MARKETPLACE_REL
        plugin_path = self.tmp_path / PLUGIN_REL
        marketplace_path.parent.mkdir(parents=True, exist_ok=True)
        plugin_path.parent.mkdir(parents=True, exist_ok=True)
        marketplace_path.write_text(marketplace_text, encoding="utf-8")
        plugin_path.write_text(plugin_text, encoding="utf-8")
        return self.tmp_path

    def test_synced_versions_pass(self):
        root = self._write_tree(
            json.dumps({"version": "2.3.4"}),
            json.dumps({"version": "2.3.4"}),
        )

        marketplace_version, plugin_version = manifest_versions(root)

        self.assertEqual(marketplace_version, plugin_version)

    def test_desynced_versions_fail_the_equality_assertion(self):
        """A one-sided bump: marketplace moved to 2.3.5, plugin.json did not."""
        root = self._write_tree(
            json.dumps({"version": "2.3.5"}),
            json.dumps({"version": "2.3.4"}),
        )

        marketplace_version, plugin_version = manifest_versions(root)

        with self.assertRaises(AssertionError):
            self.assertEqual(
                marketplace_version, plugin_version,
                f"marketplace.json version {marketplace_version!r} does not "
                f"match plugin.json version {plugin_version!r}",
            )

    def test_corrupt_marketplace_json_raises(self):
        root = self._write_tree(
            "{ this is not valid json",
            json.dumps({"version": "2.3.4"}),
        )

        with self.assertRaises(json.JSONDecodeError):
            manifest_versions(root)

    def test_corrupt_plugin_json_raises(self):
        root = self._write_tree(
            json.dumps({"version": "2.3.4"}),
            "{ this is not valid json",
        )

        with self.assertRaises(json.JSONDecodeError):
            manifest_versions(root)


if __name__ == "__main__":
    unittest.main()
