#!/usr/bin/env python3
"""The plans-index contract is stated on three shipped surfaces, and they cannot drift.

`references/plans-schema.md` defines what each plan status means and defers to
`config.yaml.template` for the list. `generate_plans_index.PLAN_STATUS_MEANINGS`
holds the same meanings for the generated legend. `seed/00-Index-Plans.md` is
the generator's own output over an empty plans directory. The manifest's
`plans_index` row names the generator as a producer. These tests pin each
surface to the others.

Run with:  python -m pytest tests/test_plans_schema_contract.py -q
"""

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen
import generate_plans_index
import yaml
from config_loader import load_config

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
TEMPLATE = PLUGIN / "config.yaml.template"
SCHEMA_REF = PLUGIN / "references" / "plans-schema.md"
SEED = PLUGIN / "seed" / "00-Index-Plans.md"
MANIFEST = PLUGIN / "manifests" / "artifacts.yaml"

_GENERATED_LINE_RE = re.compile(r"^Generated:.*$", re.MULTILINE)

# The hand-authored seed this contract retired, byte for byte as it last shipped.
RETIRED_SEED = (
    "# Plans Index\n"
    "\n"
    "| Abbrev | Name | Status | Created | Last Updated | Path |\n"
    "|--------|------|--------|---------|--------------|------|\n"
    "\n"
    "## Status Legend\n"
    "\n"
    "| Status | Meaning |\n"
    "|--------|---------|\n"
    "| NOT_STARTED | Plan created but no work begun |\n"
    "| PLANNING | Discovery or session planning in progress |\n"
    "| IN_PROGRESS | Active execution underway |\n"
    "| BLOCKED | Waiting on external dependency |\n"
    "| COMPLETE | All sprints and sessions finished |\n"
    "| CLOSED | Archived — no further work expected |\n"
)


def template_plan_statuses(text: str) -> list[str]:
    block = config_gen.extract_top_level_block(text, "plan_statuses")
    if block is None:
        return []
    return re.findall(r"^\s*-\s*([A-Za-z0-9_]+)\s*$", block, re.MULTILINE)


def schema_status_meanings(text: str) -> dict[str, str]:
    """The `## Status Definitions` table as {status: meaning}."""
    section = text.split("## Status Definitions", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|\s*(.+?)\s*\|\s*$", section, re.MULTILINE)
    return dict(rows)


def normalized(text: str) -> str:
    return _GENERATED_LINE_RE.sub("Generated: (masked)", text.replace("\r\n", "\n"))


class TestPlanStatusVocabulary(unittest.TestCase):
    def test_schema_table_template_and_generator_agree(self):
        """The reference's Status Definitions table, the template's
        `plan_statuses:` list and the generator's meanings constant name the
        same ten statuses, and every meaning is equal."""
        self.assertTrue(SCHEMA_REF.is_file(), f"{SCHEMA_REF} is missing")
        self.assertTrue(TEMPLATE.is_file(), f"{TEMPLATE} is missing")

        schema = schema_status_meanings(SCHEMA_REF.read_text(encoding="utf-8"))
        declared = template_plan_statuses(TEMPLATE.read_text(encoding="utf-8"))
        meanings = generate_plans_index.PLAN_STATUS_MEANINGS

        self.assertEqual(len(declared), 10, "the template must declare the ten shipped plan statuses")
        self.assertEqual(set(schema), set(declared))
        self.assertEqual(set(meanings), set(declared))
        for status in declared:
            self.assertEqual(schema[status], meanings[status], f"meaning of {status} differs")

    def test_parser_fires_on_a_known_bad_reference(self):
        """Direction dry-run: the same extractor must see a changed meaning."""
        self.assertTrue(SCHEMA_REF.is_file(), f"{SCHEMA_REF} is missing")
        text = SCHEMA_REF.read_text(encoding="utf-8")
        mutated = text.replace("Waiting on external dependency", "Waiting on something", 1)
        self.assertNotEqual(schema_status_meanings(mutated), schema_status_meanings(text))
        self.assertNotEqual(schema_status_meanings(mutated)["BLOCKED"], generate_plans_index.PLAN_STATUS_MEANINGS["BLOCKED"])


class TestSeedIsTheGeneratorsEmptyRender(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="plans_schema_contract_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "planwise" / "Plans").mkdir(parents=True)
        template = TEMPLATE.read_text(encoding="utf-8")
        block = config_gen.extract_top_level_block(template, "plan_statuses")
        (self.tmp / "planwise" / "config.yaml").write_text(
            "project:\n"
            "  name: seed-contract\n"
            "  planwise_root: planwise\n"
            "  plans_dir: Plans\n"
            "  index_files:\n"
            "    plans: 00-Index-Plans.md\n" + (block or ""),
            encoding="utf-8",
        )

    def test_seed_equals_the_render_over_an_empty_plans_directory(self):
        self.assertTrue(SEED.is_file(), f"{SEED} is missing")
        config = load_config(config_path=self.tmp / "planwise" / "config.yaml")

        render = generate_plans_index.render_plans_index(config)

        self.assertEqual(render.rows, [])
        self.assertEqual(normalized(SEED.read_text(encoding="utf-8")), normalized(render.text))

    def test_seed_is_not_the_retired_hand_shape(self):
        """Direction dry-run: the retired seed carried no `Generated:` line and
        a six-value legend, and the comparison above must tell it apart."""
        self.assertTrue(SEED.is_file(), f"{SEED} is missing")
        text = SEED.read_text(encoding="utf-8")
        self.assertEqual(len(_GENERATED_LINE_RE.findall(text)), 1)
        self.assertEqual(text.count("## Status Legend"), 1)
        config = load_config(config_path=self.tmp / "planwise" / "config.yaml")
        render = generate_plans_index.render_plans_index(config)
        self.assertNotEqual(normalized(RETIRED_SEED), normalized(render.text))


class TestManifestPlansIndexRow(unittest.TestCase):
    def test_row_names_the_generator_and_is_migrate_shape(self):
        self.assertTrue(MANIFEST.is_file(), f"{MANIFEST} is missing")
        rows = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["artifacts"]
        row = next((r for r in rows if r.get("id") == "plans_index"), None)

        self.assertIsNotNone(row, "the manifest has no plans_index row")
        self.assertIn("generate_plans_index.py", row["producer"])
        self.assertEqual(row["upgrade_behavior"], "migrate_shape")


if __name__ == "__main__":
    unittest.main()
