"""Contract tests for the backlog-item-classifier agent and the re-parent step that dispatches it.

The agent writes the `--map` file that `backlog_item_reparent.py` reads. These tests pin the three
places the two sides must agree:

- the example map in the agent file loads through the real `load_map`, and a corrupted copy of it
  does not (the known-bad arm, so the load test discriminates);
- the gap labels the agent quotes are the labels the real `--list` banner prints, read from a real
  item that the real shape grader flags;
- the agent can write one file and cannot edit an item, and the upgrade handler dispatches it by name.

The agent frontmatter and effort-table rules are pinned by test_agent_frontmatter.py, not here.
"""
import json
import re
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
PLUGIN = TESTS.parent / "plugins" / "planwise"
sys.path.insert(0, str(PLUGIN / "scripts"))
sys.path.insert(0, str(TESTS))

import backlog_item_reparent as rp
import backlog_item_shape as shape
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from test_backlog_item_reparent import long_title_item, old_item
from test_migrate_backlog_items import _project

AGENT = PLUGIN / "agents" / "backlog-item-classifier.md"
HANDLER = PLUGIN / "handlers" / "upgrade-Part-4-PostRunReportsAndBackfills.md"
JSON_BLOCK_RE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


def _agent_text() -> str:
    return AGENT.read_text(encoding="utf-8")


def _example_map() -> str:
    found = JSON_BLOCK_RE.findall(_agent_text())
    assert len(found) == 1, "the agent file must hold exactly one json example"
    return found[0]


def _frontmatter() -> dict:
    block = split_frontmatter_block(_agent_text())
    assert block is not None
    fields = parse_frontmatter_map(block[0])
    assert fields is not None
    return fields


def _unmapped_project(root: Path) -> tuple:
    """`(cfg, from, to)` for a project whose one item holds a heading no synonym names."""
    root.mkdir()
    cfg, _backlog = _project(root, {1: old_item(1, [("Appendix", ["Loose."])])})
    return cfg, "1.0", "1.1"


def _csv(value: str) -> list:
    return [part.strip() for part in value.split("\n")[0].split(",") if part.strip()]


def test_the_example_map_loads_through_the_real_loader(tmp_path):
    path = tmp_path / "map.json"
    path.write_text(_example_map(), encoding="utf-8")
    data = rp.load_map(path)
    raw = json.loads(_example_map())
    assert set(raw) == {"headings", "titles", "summaries"}
    assert all(target in shape.CORE_HEADINGS for target in raw["headings"].values())
    assert all(len(title) < shape.TITLE_MAX_LEN for title in raw["titles"].values())
    assert data["titles"] == raw["titles"] and data["headings"] == raw["headings"]


@pytest.mark.parametrize("old, new, fault", [
    ('"Appendix": "Problem"', '"Appendix": "Notes"', "not one of"),
    ('"summaries"', '"summary"', "unknown key"),
])
def test_a_corrupted_example_map_is_refused(tmp_path, old, new, fault):
    text = _example_map()
    assert old in text, "the corruption must change the real example"
    path = tmp_path / "bad.json"
    path.write_text(text.replace(old, new), encoding="utf-8")
    with pytest.raises(ValueError, match=fault):
        rp.load_map(path)


def test_the_agent_quotes_the_gap_labels_the_real_list_prints(tmp_path):
    cfg, _backlog = _project(tmp_path, {1: long_title_item(1, [("Finding", ["Seen."])])})
    banner = "\n".join(rp._banner_lines(rp.reparent_items(cfg, "1.0", "1.1", apply=False)))
    assert f"title over {shape.TITLE_MAX_LEN} characters" in banner and "no Summary section" in banner
    text = _agent_text()
    assert "`title over {N} characters`" in text and "`no Summary section`" in text
    unmapped = "\n".join(rp._banner_lines(rp.reparent_items(*_unmapped_project(tmp_path / "unmapped"), apply=False)))
    assert "(no core section)" in unmapped and "(no core section)" in text


def test_the_agent_names_each_core_section_and_reads_the_title_limit_from_its_source():
    text = _agent_text()
    for section in shape.CORE_HEADINGS:
        assert f"`{section}`" in text, section
    assert "TITLE_MAX_LEN" in text
    assert not re.search(rf"\b{shape.TITLE_MAX_LEN}\b", text), "the limit is read from the script, never copied into the agent"


def test_the_agent_can_write_the_map_and_cannot_edit_an_item():
    fields = _frontmatter()
    granted, denied = _csv(fields["tools"]), _csv(fields["disallowedTools"])
    assert granted == ["Read", "Write", "Glob", "Grep", "Bash"]
    assert "Edit" in denied and not set(granted) & set(denied)
    assert fields["name"].strip() == AGENT.stem == "backlog-item-classifier"


def test_the_upgrade_handler_dispatches_the_agent_by_its_plugin_name():
    handler = HANDLER.read_text(encoding="utf-8")
    assert "planwise:backlog-item-classifier" in handler
    assert "--map {map_path}" in handler
    assert "backlog_item_reparent.py" in handler
