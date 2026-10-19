"""Tests for scripts/feedback_drafts.py: every command, every branch, every delete."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import feedback_drafts as fd

# The directory the imported module actually lives in, so file-reading tests follow the import.
SCRIPTS_DIR = Path(fd.__file__).resolve().parent

BUG_BODY = (
    "### What happened\n\nIt broke.\n\n"
    "### What I expected\n\nIt works.\n\n"
    "### Steps to reproduce\n\nRun it.\n\n"
    "### Environment\n\n- planwise version: 1.0.0\n- Subcommand involved: not command-specific\n"
    "- OS / shell: test\n"
)
HEADINGS = ["### What happened", "### What I expected", "### Steps to reproduce", "### Environment"]


def iso(days_ago: float = 0) -> str:
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_draft(
    directory: Path,
    name: str,
    *,
    draft_id: str = "id-1",
    created_at: str = "",
    status: str = "queued",
    title: str = "A title",
    kind: str = "bug",
    drafted_by: str = "model",
    crlf: bool = False,
    body: str = BUG_BODY,
) -> Path:
    """Write a draft as bytes, so a CRLF fixture really holds CRLF."""
    created = created_at or iso(1)
    front = (
        "---\n"
        f"draft_id: {draft_id}\n"
        f"created_at: {created}\n"
        f"drafted_by: {drafted_by}\n"
        "producer: prompt\n"
        "trigger: model_judgment\n"
        f"kind: {kind}\n"
        f"title: {title}\n"
        "subcommand: not command-specific\n"
        "source_session_id: unknown\n"
        "plugin_version: 1.0.0\n"
        "cli_version: unknown\n"
        "model: unknown\n"
        "os: test\n"
        f"status: {status}\n"
        "---\n"
    )
    text = front + "\n" + body
    if crlf:
        text = text.replace("\n", "\r\n")
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def run(argv, capsys):
    code = fd.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


def fm_value(path: Path, key: str) -> str:
    for line in path.read_bytes().decode("utf-8").splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


@pytest.fixture
def fdir(tmp_path):
    directory = tmp_path / "drafts"
    directory.mkdir()
    return directory


def fill_queue(directory: Path, count: int, first_age: int = 2) -> list:
    """`count` queued drafts, oldest first by created_at (ages descend)."""
    paths = []
    for index in range(count):
        age = first_age + (count - index)
        paths.append(
            make_draft(
                directory,
                f"2026-01-01-draft-bug-q{index:02d}.md",
                draft_id=f"q{index:02d}",
                created_at=iso(age),
                title=f"Queued title {index}",
            )
        )
    return paths


# ---------------------------------------------------------------- admit


def test_admit_fills_ids_and_status(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-new.md", draft_id="pending", created_at="pending", status="pending")
    code, out, _ = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    assert fm_value(path, "draft_id") not in ("", "pending")
    assert fm_value(path, "created_at") not in ("", "pending")
    assert fm_value(path, "status") == "queued"
    assert fm_value(path, "draft_id") in out


def test_admit_passes_through_filled_ids(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-new.md", draft_id="keep-me", created_at=iso(3))
    before = path.read_bytes()
    code, _, _ = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    assert path.read_bytes() == before


def test_cap_deletes_the_oldest_queued_model_draft_only(fdir, capsys):
    queue = fill_queue(fdir, fd.QUEUE_CAP)
    newest = make_draft(fdir, "2026-01-01-draft-bug-new.md", draft_id="pending", created_at="pending", status="pending", title="Brand new")
    code, _, _ = run(["admit", str(newest), "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    assert not queue[0].exists()
    assert all(p.exists() for p in queue[1:])
    assert newest.exists()


def test_eviction_never_deletes_a_discarded_draft(fdir, capsys):
    discarded = make_draft(fdir, "2026-01-01-draft-bug-gone.md", draft_id="d1", created_at=iso(25), status="discarded", title="Old discarded")
    queue = fill_queue(fdir, fd.QUEUE_CAP)
    newest = make_draft(fdir, "2026-01-01-draft-bug-new.md", draft_id="pending", created_at="pending", status="pending", title="Brand new")
    run(["admit", str(newest), "--feedback-dir", str(fdir)], capsys)
    assert discarded.exists()
    assert not queue[0].exists()


def test_hand_written_draft_is_never_listed_touched_or_deleted(fdir, capsys):
    hand = fdir / "2026-10-07-bug-x.md"
    hand.write_bytes(b"### What happened\n\nHand written.\n")
    foreign = make_draft(fdir, "2026-01-01-draft-bug-theirs.md", draft_id="u1", created_at=iso(90), drafted_by="user", title="Theirs")
    marker = fdir / "2026-10-07-bug-x.md.posted"
    marker.write_bytes(b"posted: 2026-10-08\n")
    hand_before, foreign_before, marker_before = hand.read_bytes(), foreign.read_bytes(), marker.read_bytes()

    fill_queue(fdir, fd.QUEUE_CAP)
    newest = make_draft(fdir, "2026-01-01-draft-bug-new.md", draft_id="pending", created_at="pending", status="pending", title="Brand new")
    run(["admit", str(newest), "--feedback-dir", str(fdir)], capsys)
    code, out, _ = run(["list", "--json", "--all", "--feedback-dir", str(fdir)], capsys)
    run(["expire", "--feedback-dir", str(fdir)], capsys)

    listed = {item["path"] for item in json.loads(out)}
    assert code == 0
    assert "2026-10-07-bug-x.md" not in listed
    assert "2026-01-01-draft-bug-theirs.md" not in listed
    assert hand.read_bytes() == hand_before
    assert foreign.read_bytes() == foreign_before
    assert marker.read_bytes() == marker_before


def test_expiry_at_29_days_leaves_queued(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-a.md", draft_id="a1", created_at=iso(29))
    code, _, _ = run(["expire", "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    assert fm_value(path, "status") == "queued"


def test_expiry_at_31_days_flips_expired_and_deletes_nothing(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-a.md", draft_id="a1", created_at=iso(31))
    code, _, _ = run(["expire", "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    assert path.exists()
    assert fm_value(path, "status") == "expired"


def test_is_expired_boundary_is_exclusive(fdir):
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    limit = timedelta(days=fd.EXPIRY_DAYS)
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    at = make_draft(fdir, "2026-01-01-draft-bug-at.md", draft_id="at", created_at=(now - limit).strftime(stamp))
    past = make_draft(fdir, "2026-01-01-draft-bug-past.md", draft_id="past", created_at=(now - limit - timedelta(seconds=1)).strftime(stamp))
    blank = make_draft(fdir, "2026-01-01-draft-bug-blank.md", draft_id="blank", created_at="not-a-time")
    drafts = {d.path: d for d in fd._iter_drafts(fdir)}
    assert not fd.is_expired(drafts[at], now)
    assert fd.is_expired(drafts[past], now)
    assert not fd.is_expired(drafts[blank], now)


def test_count_queued_matches_list_and_writes_nothing(fdir, capsys, monkeypatch):
    now = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(fd, "_now", lambda: now)
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    limit = timedelta(days=fd.EXPIRY_DAYS)
    make_draft(fdir, "2026-01-01-draft-bug-fresh.md", draft_id="fresh", created_at=(now - timedelta(days=1)).strftime(stamp))
    make_draft(fdir, "2026-01-01-draft-bug-at.md", draft_id="at", created_at=(now - limit).strftime(stamp))
    make_draft(fdir, "2026-01-01-draft-bug-past.md", draft_id="past", created_at=(now - limit - timedelta(seconds=1)).strftime(stamp))
    make_draft(fdir, "2026-01-01-draft-bug-gone.md", draft_id="gone", status="discarded")
    before = {p.name: p.read_bytes() for p in fdir.iterdir()}

    assert fd.count_queued(fdir) == 2
    assert {p.name: p.read_bytes() for p in fdir.iterdir()} == before

    code, out, _ = run(["list", "--json", "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    assert sum(1 for item in json.loads(out) if item["status"] == "queued") == 2


def test_count_queued_on_an_absent_directory_is_zero(tmp_path):
    assert fd.count_queued(tmp_path / "missing") == 0


def test_duplicate_title_exits_3_removes_file_and_prints_one_line(fdir, capsys):
    make_draft(fdir, "2026-01-01-draft-bug-first.md", draft_id="f1", created_at=iso(2), title="Same Title!")
    dup = make_draft(fdir, "2026-01-01-draft-bug-second.md", draft_id="pending", created_at="pending", status="pending", title="same   title")
    code, _, err = run(["admit", str(dup), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert not dup.exists()
    assert len(err.strip().splitlines()) == 1


def test_oversize_exits_3_and_removes_file(fdir, capsys):
    big = make_draft(fdir, "2026-01-01-draft-bug-big.md", draft_id="pending", created_at="pending", status="pending", body=BUG_BODY + "x" * (fd.MAX_BYTES + 10))
    code, _, err = run(["admit", str(big), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert not big.exists()
    assert len(err.strip().splitlines()) == 1


def test_malformed_frontmatter_exits_3_and_is_never_deleted(fdir, capsys):
    path = fdir / "2026-01-01-draft-bug-bad.md"
    path.write_bytes(b"---\ndrafted_by: model\ndraft_id: pending\n\n### What happened\n\nNo closing delimiter.\n")
    before = path.read_bytes()
    code, _, err = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert path.read_bytes() == before
    assert len(err.strip().splitlines()) == 1


def test_body_line_cannot_authorize_a_delete(fdir, capsys):
    path = fdir / "2026-01-01-draft-bug-body.md"
    path.write_bytes(b"---\ntitle: x\n\n### What happened\n\ndrafted_by: model\n")
    code, _, _ = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert path.exists()


def test_drafted_by_with_trailing_comment_follows_the_parsed_value(fdir, capsys):
    path = make_draft(
        fdir,
        "2026-01-01-draft-bug-note.md",
        draft_id="pending",
        created_at="pending",
        status="pending",
        drafted_by="model # note",
        body=BUG_BODY + "x" * (fd.MAX_BYTES + 10),
    )
    parsed = fd._parse_fm(path.read_bytes().decode("utf-8"))
    code, _, _ = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert path.exists() == (parsed is None or parsed.get("drafted_by") != "model")


def test_admit_outside_the_feedback_directory_exits_2_and_keeps_the_file(tmp_path, fdir, capsys):
    outside = make_draft(
        tmp_path / "elsewhere",
        "2026-01-01-draft-bug-big.md",
        draft_id="pending",
        created_at="pending",
        status="pending",
        body=BUG_BODY + "x" * (fd.MAX_BYTES + 10),
    )
    before = outside.read_bytes()
    code, _, err = run(["admit", str(outside), "--feedback-dir", str(fdir)], capsys)
    assert code == 2
    assert outside.read_bytes() == before
    assert len(err.strip().splitlines()) == 1


def test_admit_inside_archive_exits_2_and_changes_nothing(fdir, capsys):
    archive = fdir / "Archive"
    siblings = fill_queue(archive, fd.QUEUE_CAP)
    old = make_draft(archive, "2026-01-01-draft-bug-old.md", draft_id="o1", created_at=iso(90), title="Old archived")
    target = make_draft(archive, "2026-01-01-draft-bug-new.md", draft_id="pending", created_at="pending", status="pending", title="Brand new")
    snapshot = {p: p.read_bytes() for p in [*siblings, old, target]}
    code, _, _ = run(["admit", str(target), "--feedback-dir", str(archive)], capsys)
    assert code == 2
    assert {p: p.read_bytes() for p in archive.iterdir()} == snapshot


def test_admit_replaces_a_draft_id_that_belongs_to_another_draft(fdir, capsys):
    first = make_draft(fdir, "2026-01-01-draft-bug-one.md", draft_id="dup", title="First one")
    second = make_draft(fdir, "2026-01-01-draft-bug-two.md", draft_id="dup", title="Second one")
    code, out, err = run(["admit", str(second), "--feedback-dir", str(fdir)], capsys)
    new_id = fm_value(second, "draft_id")
    assert code == 0
    assert new_id not in ("dup", "")
    assert new_id in out
    assert "dup" in err and new_id in err
    assert len(err.strip().splitlines()) == 1
    assert run(["discard", new_id, "--feedback-dir", str(fdir)], capsys)[0] == 0
    assert fm_value(second, "status") == "discarded"
    assert fm_value(first, "status") == "queued"


def test_admit_exits_3_when_eviction_deletes_the_admitted_draft(fdir, capsys):
    queue = fill_queue(fdir, fd.QUEUE_CAP)
    old = make_draft(fdir, "2026-01-01-draft-bug-old.md", draft_id="o1", created_at=iso(20), title="Backfilled old")
    code, out, err = run(["admit", str(old), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert "admitted" not in out
    assert "evicted on admission" in err
    assert not old.exists()
    assert all(p.exists() for p in queue)


def test_malformed_file_not_provably_a_model_draft_is_kept(fdir, capsys):
    path = fdir / "2026-01-01-draft-bug-plain.md"
    path.write_bytes(b"### What happened\n\nNo frontmatter at all.\n")
    code, _, _ = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert path.exists()


def test_name_mismatch_exits_2_and_leaves_file_untouched(fdir, capsys):
    path = fdir / "2026-10-07-bug-x.md"
    path.write_bytes(b"anything\n")
    code, _, _ = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 2
    assert path.read_bytes() == b"anything\n"


def test_admit_refuses_a_status_that_is_not_a_known_value(fdir, capsys):
    for index, status in enumerate(["Queued", "queud"]):
        path = make_draft(fdir, f"2026-01-01-draft-bug-s{index}.md", draft_id="pending", created_at="pending", status=status, title=f"Status {index}")
        code, out, err = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
        assert code == 3, status
        assert "admitted" not in out
        assert len(err.strip().splitlines()) == 1


@pytest.mark.parametrize("status", ["expired", "discarded", "promoted"])
def test_admit_leaves_a_draft_in_a_later_lifecycle_state_untouched(fdir, capsys, status):
    path = make_draft(fdir, "2026-01-01-draft-bug-tracked.md", draft_id="t1", created_at=iso(40), status=status, title="Tracked record")
    before = path.read_bytes()
    code, out, err = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 2
    assert "admitted" not in out
    assert status in err
    assert path.read_bytes() == before


def test_admit_names_each_draft_it_evicts(fdir, capsys):
    queue = fill_queue(fdir, fd.QUEUE_CAP)
    new = make_draft(fdir, "2026-01-01-draft-bug-newest.md", draft_id="n1", created_at=iso(0), title="Newest one")
    code, out, err = run(["admit", str(new), "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    assert "admitted n1" in out
    assert not queue[0].exists()
    assert "evicted q00" in err and queue[0].name in err


def test_a_project_under_a_folder_named_archive_still_works(tmp_path, capsys):
    directory = tmp_path / "archive" / "proj" / "planwise" / "Feedback"
    path = make_draft(directory, "2026-01-01-draft-bug-a.md", draft_id="pending", created_at="pending", status="pending")
    assert run(["admit", str(path), "--feedback-dir", str(directory)], capsys)[0] == 0
    code, out, _ = run(["list", "--json", "--feedback-dir", str(directory)], capsys)
    assert code == 0
    assert len(json.loads(out)) == 1


@pytest.mark.parametrize("command", [["list"], ["expire"], ["discard", "x1"], ["promote", "x1"]])
def test_a_relative_or_missing_feedback_dir_exits_1(tmp_path, capsys, command):
    for bad in ("relative/Feedback", str(tmp_path / "does-not-exist")):
        code, out, err = run([*command, "--feedback-dir", bad], capsys)
        assert code == 1, bad
        assert "no drafts" not in out
        assert len(err.strip().splitlines()) == 1


def test_list_through_config_says_when_the_directory_does_not_exist(tmp_path, capsys):
    root = tmp_path / "planwise"
    root.mkdir()
    config = root / "config.yaml"
    config.write_bytes(b"project:\n  name: demo\n  feedback_dir: Drafts\n")
    code, out, _ = run(["list", "--config", str(config)], capsys)
    assert code == 0
    assert "does not exist" in out


def test_admit_clamps_a_future_created_at_to_now(fdir, capsys):
    future = iso(-5)
    path = make_draft(fdir, "2026-01-01-draft-bug-future.md", draft_id="f1", created_at=future, title="From the future")
    code, _, err = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    stored = fm_value(path, "created_at")
    assert stored != future
    assert fd._parse_created(stored) <= datetime.now(timezone.utc)
    assert future in err and stored in err
    assert len(err.strip().splitlines()) == 1
    listed = json.loads(run(["list", "--json", "--feedback-dir", str(fdir)], capsys)[1])
    assert [item["draft_id"] for item in listed] == ["f1"]


def test_admit_exits_3_when_the_draft_expires_on_admission(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-old.md", draft_id="o1", created_at="2020-01-01T00:00:00Z", title="Long ago")
    code, out, err = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert "admitted" not in out
    assert "expired on admission" in err
    assert path.exists()
    assert fm_value(path, "status") == "expired"


def test_admit_exits_3_on_an_unparseable_created_at(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-odd.md", draft_id="pending", created_at="last tuesday", status="pending", title="Odd date")
    code, out, err = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert "admitted" not in out
    assert len(err.strip().splitlines()) == 1


def test_admit_without_a_directory_option_exits_2_and_changes_nothing(fdir, capsys):
    stale = make_draft(fdir, "2026-01-01-draft-bug-stale.md", draft_id="s1", created_at=iso(90), title="Stale queued")
    target = make_draft(fdir, "2026-01-01-draft-bug-new.md", draft_id="pending", created_at="pending", status="pending", title="Brand new")
    before = {p: p.read_bytes() for p in (stale, target)}
    code, out, err = run(["admit", str(target)], capsys)
    assert code == 2
    assert "admitted" not in out
    assert len(err.strip().splitlines()) == 1
    assert {p: p.read_bytes() for p in (stale, target)} == before


@pytest.mark.parametrize("command", [["list"], ["expire"], ["discard", "x1"], ["promote", "x1"]])
def test_every_directory_command_refuses_an_archive_directory(fdir, capsys, command):
    archived = make_draft(fdir / "Archive", "2026-01-01-draft-bug-old.md", draft_id="x1", created_at=iso(90))
    before = archived.read_bytes()
    code, _, err = run([*command, "--feedback-dir", str(fdir / "Archive")], capsys)
    assert code == 1
    assert len(err.strip().splitlines()) == 1
    assert archived.read_bytes() == before


def test_admit_refuses_a_duplicated_frontmatter_key(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-dup.md", draft_id="pending", created_at="pending", status="pending", title="Doubled key")
    path.write_bytes(path.read_bytes().replace(b"status: pending\n", b"status: pending\nstatus: queued\n", 1))
    code, out, err = run(["admit", str(path), "--feedback-dir", str(fdir)], capsys)
    assert code == 3
    assert "admitted" not in out
    assert "duplicate key status" in err


def test_write_leaves_no_temp_file_when_the_replace_fails(fdir, monkeypatch):
    path = make_draft(fdir, "2026-01-01-draft-bug-a.md", draft_id="a1")
    before = path.read_bytes()

    def broken_replace(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(fd.os, "replace", broken_replace)
    with pytest.raises(OSError, match="replace failed"):
        fd._write(path, "new text")
    monkeypatch.undo()
    assert sorted(p.name for p in fdir.iterdir()) == [path.name]
    assert path.read_bytes() == before
    fd._write(path, "new text")
    assert path.read_bytes() == b"new text"
    assert sorted(p.name for p in fdir.iterdir()) == [path.name]


def test_malformed_config_yaml_exits_1_with_one_line(tmp_path, capsys):
    pytest.importorskip("yaml")
    root = tmp_path / "planwise"
    root.mkdir()
    config = root / "config.yaml"
    config.write_bytes(b"project: {name: [unclosed\n  feedback_dir: Drafts\n")
    code, _, err = run(["list", "--config", str(config)], capsys)
    assert code == 1
    assert len(err.strip().splitlines()) == 1
    assert "cannot resolve the feedback directory" in err
    assert "Traceback" not in err


# ---------------------------------------------------------------- promote, discard


def test_promote_writes_standard_draft_and_flips_status(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-a.md", draft_id="a1", title="Hello, World!")
    code, out, _ = run(["promote", "a1", "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    target = Path(out.strip())
    assert target.parent == fdir
    assert target.name.endswith("-bug-hello-world.md")
    text = target.read_bytes().decode("utf-8")
    assert not text.startswith("---")
    assert "draft_id" not in text
    positions = [text.index(h) for h in HEADINGS]
    assert positions == sorted(positions)
    assert text.rstrip("\n").splitlines()[-1] == fd.PROVENANCE_LINE
    assert text.index("### Environment") < text.index(fd.PROVENANCE_LINE)
    assert fm_value(path, "status") == "promoted"
    assert fm_value(path, "promoted_to") == target.name


def test_second_promote_exits_3(fdir, capsys):
    make_draft(fdir, "2026-01-01-draft-bug-a.md", draft_id="a1")
    assert run(["promote", "a1", "--feedback-dir", str(fdir)], capsys)[0] == 0
    code, _, _ = run(["promote", "a1", "--feedback-dir", str(fdir)], capsys)
    assert code == 3


def test_promote_and_discard_unknown_id_exit_1(fdir, capsys):
    assert run(["promote", "nope", "--feedback-dir", str(fdir)], capsys)[0] == 1
    assert run(["discard", "nope", "--feedback-dir", str(fdir)], capsys)[0] == 1


def test_discard_flips_only_the_status_line(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-a.md", draft_id="a1")
    before = path.read_bytes().decode("utf-8").split("\n")
    code, _, _ = run(["discard", "a1", "--feedback-dir", str(fdir)], capsys)
    after = path.read_bytes().decode("utf-8").split("\n")
    assert code == 0
    changed = [(b, a) for b, a in zip(before, after, strict=True) if b != a]
    assert changed == [("status: queued", "status: discarded")]


def test_crlf_frontmatter_round_trips_except_the_one_line(fdir, capsys):
    path = make_draft(fdir, "2026-01-01-draft-bug-a.md", draft_id="a1", crlf=True)
    before = path.read_bytes()
    run(["discard", "a1", "--feedback-dir", str(fdir)], capsys)
    after = path.read_bytes()
    assert after == before.replace(b"status: queued", b"status: discarded")
    assert b"\r\n" in after
    assert after.count(b"\n") == after.count(b"\r\n")


# ---------------------------------------------------------------- list, directory resolution


def test_archive_contents_are_ignored(fdir, capsys):
    archived = make_draft(fdir / "Archive", "2026-01-01-draft-bug-old.md", draft_id="x1", created_at=iso(90))
    before = archived.read_bytes()
    code, out, _ = run(["list", "--json", "--all", "--feedback-dir", str(fdir)], capsys)
    run(["expire", "--feedback-dir", str(fdir)], capsys)
    assert code == 0
    assert json.loads(out) == []
    assert archived.read_bytes() == before
    assert run(["discard", "x1", "--feedback-dir", str(fdir)], capsys)[0] == 1


def test_list_json_has_frontmatter_keys_plus_relative_path(fdir, capsys):
    make_draft(fdir, "2026-01-01-draft-bug-a.md", draft_id="a1")
    make_draft(fdir, "2026-01-01-draft-bug-b.md", draft_id="b1", status="discarded", title="Other")
    _, out, _ = run(["list", "--json", "--feedback-dir", str(fdir)], capsys)
    items = json.loads(out)
    assert len(items) == 1
    assert list(items[0]) == [*fd.FRONTMATTER_KEYS, "path"]
    assert items[0]["path"] == "2026-01-01-draft-bug-a.md"
    _, out_all, _ = run(["list", "--json", "--all", "--feedback-dir", str(fdir)], capsys)
    assert len(json.loads(out_all)) == 2


def test_config_resolves_directory_and_feedback_dir_wins(tmp_path, capsys):
    root = tmp_path / "planwise"
    root.mkdir()
    config = root / "config.yaml"
    config.write_bytes(b"project:\n  name: demo\n  feedback_dir: Drafts\n")
    make_draft(root / "Drafts", "2026-01-01-draft-bug-a.md", draft_id="a1")
    other = tmp_path / "other"
    make_draft(other, "2026-01-01-draft-bug-b.md", draft_id="b1", title="Other")

    _, out, _ = run(["list", "--json", "--config", str(config)], capsys)
    assert [i["draft_id"] for i in json.loads(out)] == ["a1"]
    _, out2, _ = run(["list", "--json", "--config", str(config), "--feedback-dir", str(other)], capsys)
    assert [i["draft_id"] for i in json.loads(out2)] == ["b1"]


def test_missing_directory_option_exits_1(capsys):
    code, _, err = run(["list"], capsys)
    assert code == 1
    assert "--feedback-dir" in err


def test_direct_run_of_list_on_an_empty_directory_prints_empty_array(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    done = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS_DIR / "feedback_drafts.py"), "list", "--feedback-dir", str(empty), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0
    assert json.loads(done.stdout) == []


# ---------------------------------------------------------------- enable-posting


CONFIG_TEXT = "# top comment\nproject:\n  name: demo\n\nfeedback:\n  # keep this comment\n  enabled: false   # trailing note\n  repo: gabgoss/planwise\n\nother: 1\n"


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_enable_posting_flips_once_then_is_a_no_op(tmp_path, capsys, eol):
    config = tmp_path / "config.yaml"
    original = CONFIG_TEXT.replace("\n", eol).encode("utf-8")
    config.write_bytes(original)
    code, out, _ = run(["enable-posting", "--config", str(config)], capsys)
    assert code == 0
    assert "false -> true" in out
    flipped = config.read_bytes()
    assert flipped == original.replace(b"enabled: false", b"enabled: true")
    code2, out2, _ = run(["enable-posting", "--config", str(config)], capsys)
    assert code2 == 0
    assert "true -> true" in out2
    assert config.read_bytes() == flipped


def test_enable_posting_inserts_when_block_or_line_is_absent(tmp_path, capsys):
    no_line = tmp_path / "a.yaml"
    no_line.write_bytes(b"feedback:\n  repo: gabgoss/planwise\n")
    assert run(["enable-posting", "--config", str(no_line)], capsys)[0] == 0
    assert no_line.read_bytes() == b"feedback:\n  enabled: true\n  repo: gabgoss/planwise\n"

    no_block = tmp_path / "b.yaml"
    no_block.write_bytes(b"project:\n  name: demo\n")
    assert run(["enable-posting", "--config", str(no_block)], capsys)[0] == 0
    assert no_block.read_bytes() == b"project:\n  name: demo\nfeedback:\n  enabled: true\n"


def test_enable_posting_missing_config_exits_1(tmp_path, capsys):
    assert run(["enable-posting", "--config", str(tmp_path / "none.yaml")], capsys)[0] == 1


def test_enable_posting_inserts_with_the_block_indent(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_bytes(b"feedback:\n    repo: a/b\n    drafts: quiet\n")
    assert run(["enable-posting", "--config", str(config)], capsys)[0] == 0
    assert config.read_bytes() == b"feedback:\n    enabled: true\n    repo: a/b\n    drafts: quiet\n"
    if fd.yaml is not None:
        assert fd.yaml.safe_load(config.read_bytes())["feedback"]["enabled"] is True


@pytest.mark.skipif(fd.yaml is None, reason="needs PyYAML to check the result")
def test_enable_posting_never_writes_a_config_that_would_not_parse(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    original = b"feedback:\n  - one\n  - two\n"
    config.write_bytes(original)
    code, out, err = run(["enable-posting", "--config", str(config)], capsys)
    assert code == 1
    assert "-> true" not in out
    assert len(err.strip().splitlines()) == 1
    assert config.read_bytes() == original


def test_enable_posting_keeps_a_quoted_true_as_written(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    original = b'feedback:\n  enabled: "true"\n'
    config.write_bytes(original)
    assert run(["enable-posting", "--config", str(config)], capsys)[0] == 0
    assert config.read_bytes() == original


# ---------------------------------------------------------------- posting-state


@pytest.mark.parametrize(
    ("text", "state"),
    [
        (b"feedback:\n  enabled: true\n", "enabled"),
        (b'feedback:\n  enabled: "True"   # quoted\n', "enabled"),
        (b"feedback:\n  enabled: false\n", "disabled"),
        (b"feedback:\n  # note\n  enabled: no\n", "disabled"),
        (b"feedback:\n  repo: gabgoss/planwise\n", "absent"),
        (b"feedback:\n  enabled:\n  repo: gabgoss/planwise\n", "absent"),
        (b"project:\n  name: demo\n", "absent"),
        (b"", "absent"),
        (b"feedback:\r\n  enabled: false\r\n", "disabled"),
    ],
)
def test_posting_state_tells_absent_from_an_explicit_decision(tmp_path, capsys, text, state):
    config = tmp_path / "config.yaml"
    config.write_bytes(text)
    code, out, err = run(["posting-state", "--config", str(config)], capsys)
    assert (code, out.strip(), err) == (0, state, "")
    assert config.read_bytes() == text


def test_posting_state_missing_config_exits_1(tmp_path, capsys):
    code, out, err = run(["posting-state", "--config", str(tmp_path / "none.yaml")], capsys)
    assert code == 1
    assert out == ""
    assert "not found" in err


def test_posting_state_refuses_a_feedback_key_that_is_not_a_block(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    original = b"feedback: {enabled: true}\n"
    config.write_bytes(original)
    code, out, err = run(["posting-state", "--config", str(config)], capsys)
    assert code == 1
    assert out == ""
    assert "block mapping" in err
    assert config.read_bytes() == original


# ---------------------------------------------------------------- disable-drafts


def _disable(config: Path, capsys):
    return run(["disable-drafts", "--config", str(config)], capsys)


def test_disable_drafts_flips_notify_to_off_and_keeps_the_rest(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    original = b"# top\nproject:\n  name: x\nfeedback:\n  enabled: false  # c\n  drafts: notify  # keep me\n  repo: a/b\n"
    config.write_bytes(original)
    code, out, _ = _disable(config, capsys)
    assert code == 0
    assert "notify -> off" in out
    assert config.read_bytes() == original.replace(b"drafts: notify", b"drafts: off")


def test_disable_drafts_keeps_crlf(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    original = b"feedback:\r\n  drafts: quiet\r\n"
    config.write_bytes(original)
    assert _disable(config, capsys)[0] == 0
    assert config.read_bytes() == b"feedback:\r\n  drafts: off\r\n"


def test_disable_drafts_inserts_when_the_key_or_block_is_absent(tmp_path, capsys):
    no_key = tmp_path / "a.yaml"
    no_key.write_bytes(b"feedback:\n  repo: a/b\n")
    code, out, _ = _disable(no_key, capsys)
    assert code == 0
    assert "unset -> off" in out
    assert no_key.read_bytes() == b"feedback:\n  drafts: off\n  repo: a/b\n"
    no_block = tmp_path / "b.yaml"
    no_block.write_bytes(b"project:\n  name: demo\n")
    assert _disable(no_block, capsys)[0] == 0
    assert no_block.read_bytes() == b"project:\n  name: demo\nfeedback:\n  drafts: off\n"


def test_disable_drafts_missing_config_exits_1(tmp_path, capsys):
    assert _disable(tmp_path / "none.yaml", capsys)[0] == 1


@pytest.mark.skipif(fd.yaml is None, reason="needs PyYAML to check the result")
def test_disable_drafts_indented_comment_line_does_not_set_the_indent(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_bytes(b"feedback:\n  # a note indented less than the children\n    repo: a/b\n")
    assert _disable(config, capsys)[0] == 0
    assert config.read_bytes() == b"feedback:\n    drafts: off\n  # a note indented less than the children\n    repo: a/b\n"
    assert fd.yaml.safe_load(config.read_bytes())["feedback"]["drafts"] is False


@pytest.mark.skipif(fd.yaml is None, reason="needs PyYAML to check the result")
def test_disable_drafts_column_zero_comment_inside_the_block_adds_no_duplicate_key(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_bytes(b"feedback:\n  repo: a/b\n# a note at column 0\n  drafts: notify\n")
    assert _disable(config, capsys)[0] == 0
    assert config.read_bytes() == b"feedback:\n  repo: a/b\n# a note at column 0\n  drafts: off\n"
    assert config.read_bytes().count(b"drafts:") == 1


@pytest.mark.parametrize("quoted", [b'"notify"', b"'quiet'"])
def test_disable_drafts_replaces_a_quoted_value(tmp_path, capsys, quoted):
    config = tmp_path / "config.yaml"
    config.write_bytes(b"feedback:\n  drafts: " + quoted + b"\n")
    assert _disable(config, capsys)[0] == 0
    assert config.read_bytes() == b"feedback:\n  drafts: off\n"


def test_disable_drafts_is_idempotent(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_bytes(b'feedback:\n  drafts: notify\n  enabled: "true"\n')
    assert _disable(config, capsys)[0] == 0
    first = config.read_bytes()
    code, out, _ = _disable(config, capsys)
    assert code == 0
    assert "off -> off" in out
    assert config.read_bytes() == first
    quoted = tmp_path / "q.yaml"
    quoted.write_bytes(b'feedback:\n  drafts: "off"\n')
    assert _disable(quoted, capsys)[0] == 0
    assert quoted.read_bytes() == b'feedback:\n  drafts: "off"\n'


@pytest.mark.skipif(fd.yaml is None, reason="needs PyYAML to read the config back")
def test_disable_drafts_round_trips_through_the_config_loader(tmp_path, capsys):
    import config_loader

    config = tmp_path / "config.yaml"
    config.write_bytes(b"project:\n  name: demo\nfeedback:\n  drafts: notify\n")
    assert config_loader.get_feedback_config(fd.yaml.safe_load(config.read_bytes()))["drafts"] == "notify"
    assert _disable(config, capsys)[0] == 0
    assert config_loader.get_feedback_config(fd.yaml.safe_load(config.read_bytes()))["drafts"] == "off"


@pytest.mark.skipif(fd.yaml is None, reason="needs PyYAML to check the result")
def test_disable_drafts_never_writes_a_config_that_would_not_parse(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    original = b"feedback:\n  - one\n  - two\n"
    config.write_bytes(original)
    code, out, err = _disable(config, capsys)
    assert code == 1
    assert "-> off" not in out
    assert len(err.strip().splitlines()) == 1
    assert config.read_bytes() == original


def _can_symlink(tmp_path: Path) -> bool:
    probe = tmp_path / "probe-link"
    try:
        probe.symlink_to(tmp_path)
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


def test_writes_keep_a_symlink_and_change_its_target(tmp_path, capsys):
    if not _can_symlink(tmp_path):
        pytest.skip("symlinks are not available here")
    real = tmp_path / "real.yaml"
    real.write_bytes(b"feedback:\n  enabled: false\n")
    link = tmp_path / "config.yaml"
    link.symlink_to(real)
    assert run(["enable-posting", "--config", str(link)], capsys)[0] == 0
    assert link.is_symlink()
    assert real.read_bytes() == b"feedback:\n  enabled: true\n"

    directory = tmp_path / "drafts"
    target = make_draft(tmp_path / "store", "2026-01-01-draft-bug-a.md", draft_id="a1")
    directory.mkdir()
    linked = directory / target.name
    linked.symlink_to(target)
    assert run(["discard", "a1", "--feedback-dir", str(directory)], capsys)[0] == 0
    assert linked.is_symlink()
    assert fm_value(target, "status") == "discarded"


# ---------------------------------------------------------------- slugify (cross-pinned with the TypeScript slug table)


def test_slugify_lowercases_and_turns_punctuation_runs_into_one_hyphen():
    assert fd.slugify("Hello, World!") == "hello-world"


def test_slugify_trims_leading_and_trailing_hyphens():
    assert fd.slugify("  --A__b  ") == "a-b"


def test_slugify_cuts_to_40_characters():
    assert fd.slugify("a" * 50) == "a" * 40
    assert len(fd.slugify("a" * 50)) == 40


def test_slugify_strips_the_hyphen_a_cut_exposes():
    title = "a" * 39 + "!!!b"
    slug = fd.slugify(title)
    assert slug == "a" * 39
    assert not slug.endswith("-")


def test_slugify_turns_empty_results_into_untitled():
    assert fd.slugify("!!!") == "untitled"
    assert fd.slugify("") == "untitled"


# ---------------------------------------------------------------- constants


def test_cross_pinned_constants_are_single_line_literals():
    source = (SCRIPTS_DIR / "feedback_drafts.py").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in source if line.startswith("DRAFT_NAME_RE = re.compile(")) == 1
    assert sum(1 for line in source if line.startswith("FRONTMATTER_KEYS = (") and line.endswith(")")) == 1
    assert len(fd.FRONTMATTER_KEYS) == 14
