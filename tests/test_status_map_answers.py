"""status_map answers: the upgrade asks one question for each open item status outside the valid
statuses, and the answers file refuses a malformed `status_map` before any write.

The projects come from `upgrade_card_project`, which runs the plugin's own `init_project`. An item
comes from the real writer, `update_backlog.py --create`, and only its `status:` line is rewritten to a
value the writer itself refuses. The questions come from `index_shape_preflight.py` run as a
subprocess, the way the upgrade handler runs it. Nothing here writes under `plugins/planwise/`.
"""
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for upgrade_card_project

import init_project  # noqa: I001 -- composition root first, so the import-order trap never fires
import doctor_probes
import index_shape_preflight
import migration_answers
import upgrade_card_project as ucp
import upgrade_preflight
from constants import VALID_STATUSES

PREFLIGHT = SCRIPTS / "index_shape_preflight.py"
UPDATE_BACKLOG = SCRIPTS / "update_backlog.py"
HANDLER = SCRIPTS.parent / "handlers" / "upgrade.md"
LEGACY_INDEX = ("# Backlog Index\n\n## Backlog Items\n\n"
                "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n\n"
                "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n")
GH_OK = {"path": "/usr/bin/gh", "note": "", "version": "2.0", "authenticated": True, "timed_out": False}


@pytest.fixture(autouse=True)
def _isolate(_isolated_home, monkeypatch):
    ucp.isolate(monkeypatch)


def run_script(script: Path, *args: str):
    return subprocess.run([sys.executable, "-B", str(script), *args], capture_output=True, text=True, check=False)


def add_item(root: Path, item_id: str, status: str) -> Path:
    """An open item from the real writer, with its `status:` line rewritten to `status`."""
    name = f"BB-{item_id}-01-INFRA-Sample.md"
    done = run_script(UPDATE_BACKLOG, "--config", str(ucp.config_path(root)), "--create", "--id", item_id,
                      "--feature", f"Sample item {item_id}", "--priority", "Medium", "--abbrev", "INFRA",
                      "--files", name)
    assert done.returncode == 0, done.stdout + done.stderr
    path = root / "planwise" / "Backlog" / name
    data = path.read_bytes()
    assert data.count(b"status: NOT_STARTED") == 1  # control: the line the rewrite targets exists once
    path.write_bytes(data.replace(b"status: NOT_STARTED", f"status: {status}".encode()))
    return path


def preflight(root: Path) -> dict:
    done = run_script(PREFLIGHT, "--config", str(ucp.config_path(root)), "--questions")
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def status_questions(root: Path) -> list:
    return [q for q in preflight(root)["backlog"]["questions"] if q["id"] == "item-status"]


def load(tmp_path: Path, document) -> dict:
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return migration_answers.load_answers(path)


def test_a_clean_backlog_asks_no_status_question(tmp_path):
    root = ucp.make_up_to_date(tmp_path)
    add_item(root, "001", "NOT_STARTED")
    assert preflight(root)["backlog"]["questions"] == []


def test_one_question_for_each_distinct_out_of_set_status(tmp_path):
    root = ucp.make_up_to_date(tmp_path)
    add_item(root, "001", "OPEN")
    add_item(root, "002", "OPEN")
    add_item(root, "003", "Done")
    add_item(root, "004", "NOT_STARTED")
    asked = status_questions(root)
    assert [q["statuses"] for q in asked] == [["Done"], ["OPEN"]]
    assert [q["items"] for q in asked] == [["003"], ["001", "002"]]
    assert "2 open backlog item(s) (001, 002)" in asked[1]["prompt"] and "'OPEN'" in asked[1]["prompt"]


def test_every_option_answer_loads_as_written(tmp_path):
    root = ucp.make_up_to_date(tmp_path)
    add_item(root, "001", "OPEN")
    (question,) = status_questions(root)
    assert 2 <= len(question["options"]) <= 4  # AskUserQuestion takes 2 to 4 options
    assert {o["label"] for o in question["options"]} <= VALID_STATUSES
    for option in question["options"]:
        assert option["answer"] == {"status_map": [f"OPEN->{option['label']}"]}
        assert load(tmp_path, option["answer"]) == option["answer"]


def test_the_prompt_names_the_statuses_no_option_carries():
    question = index_shape_preflight.status_question("OPEN", ["001"])
    offered = {o["label"] for o in question["options"]}
    left_out = VALID_STATUSES - offered
    assert left_out and all(status in question["prompt"] for status in left_out)
    assert not any(status in question["prompt"] for status in offered)


def test_a_long_id_list_is_capped_in_the_prompt_only():
    ids = [f"{n:03d}" for n in range(1, 13)]
    question = index_shape_preflight.status_question("OPEN", ids)
    assert "(001, 002, 003, 004, 005, 006, 007, 008, 009, 010 and 2 more)" in question["prompt"]
    assert question["items"] == ids


def test_the_question_is_asked_whatever_the_index_shape(tmp_path):
    root = ucp.make_up_to_date(tmp_path)
    add_item(root, "001", "OPEN")
    generated = preflight(root)["backlog"]
    assert generated["shape"] == "generated" and [q["id"] for q in generated["questions"]] == ["item-status"]
    index = root / "planwise" / "Backlog" / "00-Index-Backlog.md"
    index.write_bytes(LEGACY_INDEX.encode("utf-8"))
    legacy = preflight(root)["backlog"]
    assert legacy["shape"] == "legacy"  # control: the rewrite changed the shape
    assert [q["id"] for q in legacy["questions"]] == ["item-status"]


def test_a_blank_status_and_an_archived_item_ask_nothing(tmp_path):
    root = ucp.make_up_to_date(tmp_path)
    blank = add_item(root, "001", '""')
    assert blank.read_bytes().count(b'status: ""') == 1
    kept = add_item(root, "002", "OPEN")
    archive = root / "planwise" / "Backlog" / "Archive"
    archive.mkdir(exist_ok=True)
    kept.replace(archive / kept.name)
    assert status_questions(root) == []
    add_item(root, "003", "OPEN")  # control: the same status on an open item is asked
    assert [q["items"] for q in status_questions(root)] == [["003"]]


def test_the_preflight_writes_nothing(tmp_path):
    root = ucp.make_up_to_date(tmp_path)
    add_item(root, "001", "OPEN")
    before = ucp.hash_tree(root)
    assert status_questions(root)  # control: the run did see the item
    assert ucp.hash_tree(root) == before


@pytest.mark.parametrize("entries", [
    [],
    ["OPEN->NOT_STARTED"],
    ["OPEN->NOT_STARTED", "DONE->COMPLETE", "On Hold->BLOCKED"],
    ["in-progress->IN_PROGRESS"],
    ["OPEN->NOT_STARTED", "OPEN->NOT_STARTED"],
])
def test_a_well_formed_status_map_loads(tmp_path, entries):
    assert load(tmp_path, {"status_map": entries}) == {"status_map": entries}


@pytest.mark.parametrize("entry", [
    "OPEN",  # no arrow
    "->NOT_STARTED",  # no status
    "OPEN->",  # no target
    "OPEN->DONE",  # the target is not a valid status
    "OPEN->not_started",  # the target is not upper case
    "NOT_STARTED->COMPLETE",  # the status is already valid
    " OPEN->COMPLETE",  # an edge space
    "OPEN ->COMPLETE",  # an edge space before the arrow
    "OP\nEN->COMPLETE",  # a control character
    "A->B->COMPLETE",  # an arrow inside the status
    "OPEN=>NOT_STARTED",  # the wrong arrow
    5,  # not a string
    None,
])
def test_a_malformed_status_map_entry_is_refused(tmp_path, entry):
    with pytest.raises(migration_answers.AnswersError) as caught:
        load(tmp_path, {"status_map": [entry]})
    assert "status_map" in caught.value.reason and "<status>-><target>" in caught.value.fix


@pytest.mark.parametrize("value", ["OPEN->NOT_STARTED", {"OPEN": "NOT_STARTED"}, 5])
def test_a_status_map_that_is_not_a_list_is_refused(tmp_path, value):
    with pytest.raises(migration_answers.AnswersError) as caught:
        load(tmp_path, {"status_map": value})
    assert "is a " in caught.value.reason and "not a list" in caught.value.reason


def test_one_status_maps_to_one_target(tmp_path):
    with pytest.raises(migration_answers.AnswersError) as caught:
        load(tmp_path, {"status_map": ["OPEN->NOT_STARTED", "OPEN->COMPLETE"]})
    assert "both NOT_STARTED and COMPLETE" in caught.value.reason


def test_the_unknown_key_message_lists_status_map(tmp_path):
    with pytest.raises(migration_answers.AnswersError) as caught:
        load(tmp_path, {"statuses": []})
    assert "status_map" in caught.value.fix and "edge_drops" in caught.value.fix


def upgrade_argv(root: Path, answers: Path) -> list:
    return ["init_project.py", "--project-root", str(root), "--name", root.name, "--root", "planwise",
            "--plans-dir", "Plans", "--backlog-dir", "Backlog", "--lessons-dir", "LessonsLearned",
            "--scope", "project", "--upgrade", "--upgrade-pair", ucp.PAIR, "--migration-answers", str(answers)]


def test_the_upgrade_refuses_a_malformed_status_map_before_any_write(tmp_path, monkeypatch):
    root = ucp.make_project(tmp_path)
    add_item(root, "001", "OPEN")
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"status_map": ["OPEN->DONE"]}), encoding="utf-8")
    before = (ucp.hash_tree(root), ucp.hash_tree(Path.home()))
    err, code = io.StringIO(), None
    monkeypatch.setattr(sys, "argv", upgrade_argv(root, answers))
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(SystemExit) as caught:
            init_project.main()
        code = caught.value.code
    assert code == 2
    assert "Upgrade refused" in err.getvalue() and '"status_map" entry' in err.getvalue()  # it reached the validator
    assert (ucp.hash_tree(root), ucp.hash_tree(Path.home())) == before


def test_a_pending_status_question_breaks_the_noop_proof(tmp_path, capsys, monkeypatch):
    root = ucp.make_up_to_date(tmp_path)
    monkeypatch.setattr(doctor_probes, "_gh_environment", lambda: dict(GH_OK))
    capsys.readouterr()
    assert upgrade_preflight.run(["upgrade", "--project-root", str(root)]) == 0
    control = capsys.readouterr().out
    assert "Nothing to do" in control and "Migration questions (0)" in control  # control: the untouched project
    add_item(root, "001", "OPEN")
    assert upgrade_preflight.run(["upgrade", "--project-root", str(root)]) == 0
    card = capsys.readouterr().out
    assert "Nothing to do" not in card and "Migration questions (1)" in card
    assert "item-status" in card and "upgrade_run.py" in card
    config_path, config = upgrade_preflight.resolve_config(root.resolve())
    ok, reason, _ = upgrade_preflight.noop_proof("up-to-date", [], config, config_path, {}, "project")
    assert (ok, reason) == (False, "1 migration question(s) are pending")


def test_the_handler_names_the_status_family_and_auto_mode():
    text = HANDLER.read_text(encoding="utf-8")
    step = text[text.index("### Step 2.3b"):text.index("### Step 2.4")]
    assert '"status_map": ["OPEN->NOT_STARTED"]' in step
    assert "Auto Mode answers no status question" in step
    assert "picks Other on a status question" in step  # the typed-status route is stated
