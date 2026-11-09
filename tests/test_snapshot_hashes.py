"""Tests for scripts/snapshot_hashes.py (take and compare modes).

Every fixture tree is built under pytest's tmp_path, never inside the shipped
subtree. Each predicate has a positive control (exit 0) and mutation controls
(exit 1 for a moved, removed, added or line-ending-only change; exit 2 for a
malformed snapshot or a usage error).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import snapshot_hashes


def _tree(root: Path) -> Path:
    tree = root / "tree"
    (tree / "sub").mkdir(parents=True)
    (tree / "a.md").write_bytes(b"alpha\nbeta\n")
    (tree / "sub" / "b.md").write_bytes(b"gamma\n")
    return tree


def _take(tmp_path: Path, label: str, *paths: Path) -> Path:
    out = tmp_path / f"{label}.json"
    code = snapshot_hashes.main(["take", "--label", label, "--out", str(out), *map(str, paths)])
    assert code == 0
    return out


def _compare(*snaps: Path) -> int:
    return snapshot_hashes.main(["compare", *map(str, snaps)])


def test_take_writes_label_timestamp_and_raw_byte_hashes(tmp_path):
    tree = _tree(tmp_path)
    missing = tmp_path / "nope.md"
    snap = json.loads(_take(tmp_path, "before", tree, missing).read_text(encoding="utf-8"))
    assert snap["label"] == "before"
    assert snap["taken_utc"].endswith("+00:00")
    paths = [f["path"] for f in snap["files"]]
    assert paths[:2] == sorted(paths[:2])
    assert paths[0].endswith("tree/a.md") and paths[1].endswith("tree/sub/b.md")
    a = snap["files"][0]
    assert a["present"] is True and a["bytes"] == 11
    assert a["sha256"] == hashlib.sha256(b"alpha\nbeta\n").hexdigest()
    assert snap["files"][2] == {"path": paths[2], "present": False, "sha256": None, "bytes": None}


def test_positive_control_unchanged_tree_compares_zero(tmp_path, capsys):
    tree = _tree(tmp_path)
    s1 = _take(tmp_path, "dispatch", tree)
    s2 = _take(tmp_path, "runner-start", tree)
    s3 = _take(tmp_path, "return", tree)
    assert _compare(s1, s2, s3) == 0
    assert "ok: 2 files agree across 3 snapshots" in capsys.readouterr().out


def test_one_byte_changed_exits_one_naming_file_and_label(tmp_path, capsys):
    tree = _tree(tmp_path)
    s1 = _take(tmp_path, "dispatch", tree)
    s2 = _take(tmp_path, "runner-start", tree)
    (tree / "a.md").write_bytes(b"alphA\nbeta\n")
    s3 = _take(tmp_path, "runner-end", tree)
    s4 = _take(tmp_path, "return", tree)
    capsys.readouterr()
    assert _compare(s1, s2, s3, s4) == 1
    out = capsys.readouterr().out
    assert "moved: " in out and "tree/a.md changed at label 'runner-end'" in out
    assert "sub/b.md" not in out


def test_deleted_file_exits_one_as_removed(tmp_path, capsys):
    tree = _tree(tmp_path)
    s1 = _take(tmp_path, "before", tree)
    (tree / "sub" / "b.md").unlink()
    s2 = _take(tmp_path, "after", tree)
    capsys.readouterr()
    assert _compare(s1, s2) == 1
    out = capsys.readouterr().out
    assert "removed: " in out and "sub/b.md changed at label 'after'" in out


def test_named_missing_file_that_appears_exits_one_as_added(tmp_path, capsys):
    target = tmp_path / "late.md"
    s1 = _take(tmp_path, "before", target)
    target.write_bytes(b"x\n")
    s2 = _take(tmp_path, "after", target)
    capsys.readouterr()
    assert _compare(s1, s2) == 1
    assert "added: " in capsys.readouterr().out


def test_crlf_only_rewrite_exits_one(tmp_path, capsys):
    tree = _tree(tmp_path)
    s1 = _take(tmp_path, "before", tree)
    (tree / "a.md").write_bytes(b"alpha\r\nbeta\r\n")
    s2 = _take(tmp_path, "after", tree)
    capsys.readouterr()
    assert _compare(s1, s2) == 1
    assert "moved: " in capsys.readouterr().out


def test_malformed_json_exits_two(tmp_path):
    tree = _tree(tmp_path)
    good = _take(tmp_path, "before", tree)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert _compare(good, bad) == 2


def test_schema_defect_exits_two(tmp_path):
    tree = _tree(tmp_path)
    good = _take(tmp_path, "before", tree)
    data = json.loads(good.read_text(encoding="utf-8"))
    data["files"][0]["present"] = "yes"
    bad = tmp_path / "schema.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    assert _compare(good, bad) == 2


def test_unreadable_file_exits_two_and_writes_no_snapshot(tmp_path, monkeypatch, capsys):
    tree = _tree(tmp_path)
    real_open = Path.open

    def locked_open(self, mode="r", *args, **kwargs):
        if self.name == "a.md" and "r" in mode:
            raise PermissionError(13, "Permission denied")
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", locked_open)
    out = tmp_path / "locked.json"
    code = snapshot_hashes.main(["take", "--label", "x", "--out", str(out), str(tree)])
    assert code == 2
    assert not out.exists()
    assert "a.md" in capsys.readouterr().err


def test_own_out_inside_named_directory_is_not_hashed(tmp_path):
    tree = _tree(tmp_path)
    out = tree / "pin.json"
    for label in ("first", "second"):
        assert snapshot_hashes.main(["take", "--label", label, "--out", str(out), str(tree)]) == 0
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert len(snap["files"]) == 2
        assert all(not f["path"].endswith("pin.json") for f in snap["files"])


def test_earlier_snapshot_left_in_named_directory_reads_as_added(tmp_path, capsys):
    # Documented limit: only the current run's own --out is skipped.
    tree = _tree(tmp_path)
    s1 = tree / "s1.json"
    s2 = tmp_path / "s2.json"
    assert snapshot_hashes.main(["take", "--label", "one", "--out", str(s1), str(tree)]) == 0
    assert snapshot_hashes.main(["take", "--label", "two", "--out", str(s2), str(tree)]) == 0
    capsys.readouterr()
    assert _compare(s1, s2) == 1
    assert "added: " in capsys.readouterr().out


def test_usage_errors_exit_two(tmp_path):
    tree = _tree(tmp_path)
    one = _take(tmp_path, "only", tree)
    assert _compare(one) == 2
    assert snapshot_hashes.main(["take", "--out", str(tmp_path / "x.json"), str(tree)]) == 2
    assert snapshot_hashes.main([]) == 2
