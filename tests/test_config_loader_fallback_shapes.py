"""The no-PyYAML fallback reader reads the shapes an `abbreviations:` block can hold.

`config_loader._parse_yaml_simple` is the reader `load_config` uses when PyYAML is not
installed. It reads quoted keys, keys with a hyphen or dot, block scalars (`>` and `|`
with a `-` or `+` chomp indicator) and a nested mapping one level under a section key,
and returns the dict PyYAML returns for them. The backlog migrator re-reads config.yaml
after it adds an abbreviation. A reader that misplaced an entry used to make that check
fail and end the run `write_failed`. These tests hide PyYAML (`HAS_YAML` False) and run
the loader and the migrator over each shape. Fixtures come from the migration suite's
own builders: bytes under tmp_path, never under plugins/planwise/."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_backlog_migration as base
from test_backlog_migration import bm, config_loader, sup

# Each row: id, the `abbreviations:` entries as written, the dict a PyYAML read gives for that block.
SHAPES = [
    ("quoted-keys",
     '  APP: Application features\n  "Y": Yes label\n  \'N\': No label\n  BUG: Bug fixes\n',
     {"APP": "Application features", "Y": "Yes label", "N": "No label", "BUG": "Bug fixes"}),
    ("hyphen-and-dot-keys",
     "  A-B: Hyphen key\n  c.d: Dot key\n  BUG: Bug fixes\n",
     {"A-B": "Hyphen key", "c.d": "Dot key", "BUG": "Bug fixes"}),
    ("folded-block-scalar",
     "  APP: >\n    Application\n    features\n  BUG: Bug fixes\n",
     {"APP": "Application features\n", "BUG": "Bug fixes"}),
    ("literal-block-scalar",
     "  APP: |\n    line one\n    line two\n  BUG: Bug fixes\n",
     {"APP": "line one\nline two\n", "BUG": "Bug fixes"}),
    ("strip-chomped-block-scalar",
     "  APP: >-\n    Application\n    features\n\n  BUG: Bug fixes\n",
     {"APP": "Application features", "BUG": "Bug fixes"}),
    ("keep-chomped-block-scalar",
     "  APP: |+\n    line one\n\n  BUG: Bug fixes\n",
     {"APP": "line one\n\n", "BUG": "Bug fixes"}),
    ("folded-paragraphs",
     "  APP: >\n    first\n    para\n\n    second\n  BUG: Bug fixes\n",
     {"APP": "first para\nsecond\n", "BUG": "Bug fixes"}),
    ("nested-entry",
     "  APP:\n    name: Application\n    note: x\n  BUG: Bug fixes\n",
     {"APP": {"name": "Application", "note": "x"}, "BUG": "Bug fixes"}),
    ("nested-entry-last",
     "  BUG: Bug fixes\n  APP:\n    name: Application\n",
     {"BUG": "Bug fixes", "APP": {"name": "Application"}}),
    ("every-shape-together",
     '  "Y": Yes label\n  APP:\n    name: Application\n  C-D: >\n    folded\n    text\n  BUG: Bug fixes\n',
     {"Y": "Yes label", "APP": {"name": "Application"}, "C-D": "folded text\n", "BUG": "Bug fixes"}),
]
SIBLINGS = "plan_statuses:\n  - DRAFT\n  - LIVE\nproject:\n  name: sample\n"


def _text(entries: str, eol: str = "\n") -> str:
    return ("abbreviations:\n" + entries + SIBLINGS).replace("\n", eol)


@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("name,entries,expected", SHAPES, ids=[s[0] for s in SHAPES])
def test_the_fallback_reader_returns_the_dict_pyyaml_returns(name, entries, expected, eol):
    parsed = config_loader._parse_yaml_simple(_text(entries, eol))
    assert parsed["abbreviations"] == expected, parsed
    assert parsed["plan_statuses"] == ["DRAFT", "LIVE"], "a section after the block was misplaced"
    assert parsed["project"] == {"name": "sample"}
    assert set(parsed) == {"abbreviations", "plan_statuses", "project"}, f"an entry leaked to the top level: {set(parsed)}"


@pytest.mark.parametrize("name,entries,expected", SHAPES, ids=[s[0] for s in SHAPES])
def test_the_expected_dicts_are_what_pyyaml_returns(name, entries, expected):
    yaml = pytest.importorskip("yaml")
    assert yaml.safe_load(_text(entries))["abbreviations"] == expected


@pytest.mark.parametrize("name,entries,expected", SHAPES, ids=[s[0] for s in SHAPES])
def test_load_config_without_pyyaml_reads_each_shape(tmp_path, monkeypatch, name, entries, expected):
    monkeypatch.setattr(config_loader, "HAS_YAML", False)
    path = tmp_path / "planwise" / "config.yaml"
    base._write(path, _text(entries))
    config = config_loader.load_config(Path(bm.__file__), config_path=path)
    assert config["abbreviations"] == expected


@pytest.mark.parametrize("name,entries,expected", SHAPES, ids=[s[0] for s in SHAPES])
def test_the_migrator_without_pyyaml_never_ends_write_failed_on_each_shape(tmp_path, monkeypatch, name, entries, expected):
    monkeypatch.setattr(config_loader, "HAS_YAML", False)
    cfg, backlog = base._project(tmp_path)
    config_path = backlog.parent / "config.yaml"
    config = base.CONFIG.split("abbreviations:")[0] + "abbreviations:\n" + entries
    base._write(config_path, config)
    report = base._migrate(cfg)
    assert report.state == "migrated", (report.state, report.detail)
    reloaded = config_loader.load_config(Path(bm.__file__), config_path=config_path)
    # INFRA is the abbreviation the fixture's third item carries and no shape configures; SMP is added too.
    assert {"INFRA", "SMP"} <= sup.configured_abbrevs(reloaded)
    assert set(expected) <= sup.configured_abbrevs(reloaded)


def test_index_files_nest_inside_project_so_a_custom_index_name_is_honoured_without_pyyaml(tmp_path, monkeypatch):
    # `index_files:` is an indented key with no value. The old reader made it a top-level section,
    # so `project.index_files` was missing and a custom index name was silently ignored.
    monkeypatch.setattr(config_loader, "HAS_YAML", False)
    path = tmp_path / "planwise" / "config.yaml"
    base._write(path, 'project:\n  name: x\n  index_files:\n    backlog: "Custom-Backlog.md"\n')
    config = config_loader.load_config(Path(bm.__file__), config_path=path)
    assert config["project"]["index_files"] == {"backlog": "Custom-Backlog.md"}
    assert "index_files" not in config
    assert config_loader.resolve_index_name(config, "backlog") == "Custom-Backlog.md"


def test_a_block_scalar_in_a_section_that_precedes_a_list_does_not_swallow_it(tmp_path):
    text = "notes:\n  text: |\n    kept\n    as written\nplan_statuses:\n  - A\n  - B\n"
    parsed = config_loader._parse_yaml_simple(text)
    assert parsed == {"notes": {"text": "kept\nas written\n"}, "plan_statuses": ["A", "B"]}


def test_a_key_only_line_followed_by_a_list_keeps_its_earlier_reading():
    # A key-only line whose children are a list (not a mapping) is not a nested entry. The reader
    # leaves that shape as it always did, so no existing config changes meaning.
    text = "section:\n  buckets:\n  - id: A\n"
    before = {"section": {}, "buckets": ["id: A"]}
    assert config_loader._parse_yaml_simple(text) == before
