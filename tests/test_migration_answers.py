"""`migration_answers.load_answers()` accepts the files the handler writes and refuses the rest.

The valid file is built the way the handler builds it: each chosen question option carries a
fragment such as `{"edge_drops": ["002->001"]}`, and the handler concatenates each key's list.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import migration_answers
from migration_answers import AnswersError, load_answers

FRAGMENTS = [
    {"edge_drops": ["002->001"]},
    {"edge_drops": ["001<->003:both", "010->009"]},
]


def _write(tmp_path, payload) -> Path:
    path = tmp_path / "answers.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return path


def test_valid_file_built_from_concatenated_fragments_loads(tmp_path):
    merged = {"edge_drops": [e for frag in FRAGMENTS for e in frag["edge_drops"]]}

    assert load_answers(_write(tmp_path, merged)) == merged
    assert merged["edge_drops"] == ["002->001", "001<->003:both", "010->009"]


def test_unknown_key_is_refused_naming_the_key(tmp_path):
    with pytest.raises(AnswersError) as excinfo:
        load_answers(_write(tmp_path, {"edge_drops": [], "mystery": 1}))

    assert '"mystery"' in excinfo.value.reason
    assert "edge_drops" in excinfo.value.fix


@pytest.mark.parametrize("bad", ["002=>001", "002->", "a->b", "002<->001", "001<->002:one", 7])
def test_bad_edge_drops_entry_is_refused_naming_the_shape(tmp_path, bad):
    with pytest.raises(AnswersError) as excinfo:
        load_answers(_write(tmp_path, {"edge_drops": [bad]}))

    assert repr(bad) in excinfo.value.reason
    assert "<id>-><id>" in excinfo.value.fix
    assert "<id><-><id>:both" in excinfo.value.fix


NEAR_MISS_ENTRIES = ["002->001\n", "١->002", "BLI-002->001", " 002->001", "002->002",
                     "001<->001:both", "001<->002:both\n", "002->2", "1->001", "0001<->01:both", "000->0"]


def test_bom_prefixed_file_is_accepted(tmp_path):
    path = tmp_path / "answers.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"edge_drops": ["002->001"]}).encode("utf-8"))

    assert load_answers(path) == {"edge_drops": ["002->001"]}


@pytest.mark.parametrize("bad", NEAR_MISS_ENTRIES)
def test_near_miss_entry_is_refused(tmp_path, bad):
    with pytest.raises(AnswersError) as excinfo:
        load_answers(_write(tmp_path, {"edge_drops": [bad]}))

    assert repr(bad) in excinfo.value.reason


def test_parse_edge_drop_one_way():
    assert migration_answers.parse_edge_drop("002->001") == [("002", "001")]


def test_parse_edge_drop_both_directions():
    assert migration_answers.parse_edge_drop("001<->002:both") == [("001", "002"), ("002", "001")]


@pytest.mark.parametrize("bad", NEAR_MISS_ENTRIES + ["002=>001", "a->b", 7, None])
def test_parse_edge_drop_returns_none_for_bad_entry(bad):
    assert migration_answers.parse_edge_drop(bad) is None


def test_non_object_json_is_refused(tmp_path):
    with pytest.raises(AnswersError) as excinfo:
        load_answers(_write(tmp_path, '["002->001"]'))

    assert "not an object" in excinfo.value.reason
    assert "edge_drops" in excinfo.value.fix


def test_missing_file_is_refused(tmp_path):
    with pytest.raises(AnswersError) as excinfo:
        load_answers(tmp_path / "absent.json")

    assert "does not exist" in excinfo.value.reason
