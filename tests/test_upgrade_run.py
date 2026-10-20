"""upgrade_run: the verdicts document, the guards, the writer call, the summary and the offers.

Every project is built by tests/upgrade_card_project.py from this repo's own plugin tree, inside
`tmp_path`. `_isolate` below patches the CLI-version probe, and every writer run passes
`--no-calibrate` or stops at `--dry-argv`, so no run starts `claude`.
"""
import io
import json
import os
import re
import shlex
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_loader
import init_project
import upgrade_card_project as ucp
import upgrade_preflight
import upgrade_run
import verdict_sanitize

PAIR = ucp.PAIR


@pytest.fixture(autouse=True)
def _isolate(_isolated_home, monkeypatch):
    ucp.isolate(monkeypatch)


def run(monkeypatch, capsys, root, *argv, stdin=""):
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    capsys.readouterr()
    code = upgrade_run.main(["--project-root", str(root), *argv])
    return code, capsys.readouterr().out


def entry(root, name, **extra):
    """A verdict entry in the card's array form, with the sha the card prints."""
    return {"filename": name, "classification": "SUBSET", "confidence": "contained", "unique_blocks": [],
            "tolerated_fragments": [], "rationale": "", "notes": "",
            "installed_sha256": ucp.installed_sha(root / ucp.RULES / name), **extra}


def verdicts_file(root, pair=PAIR):
    return root / "planwise" / "upgrade-conflicts" / pair / "verdicts.json"


def section(out, start, end=None):
    head = out.index(start)
    return out[head:out.index(end, head)] if end else out[head:]


def test_full_run_with_stdin_verdicts(tmp_path, capsys, monkeypatch):
    root = ucp.make_project(tmp_path)
    ucp.seed_backup(root, ucp.EARLIER_PAIR)  # the safe-to-discard offer names an earlier pair, never this run's
    body = ucp.shipped("agent-authoring.md")
    same = ucp.seed_transfer(root, ucp.EARLIER_PAIR, "same one.md", body)
    # now-upstream but not equal to the shipped rule: apply would keep it, so it is never offered
    lines = body.split("\n")
    ucp.seed_transfer(root, ucp.EARLIER_PAIR, "half.md", "\n".join(lines[:len(lines) // 2]) + "\n")
    entries = [entry(root, name) for name, *_rest in ucp.DIVERGENCES]
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--verdicts-stdin", "--no-calibrate",
                    stdin=json.dumps(entries))
    assert code == 0, out

    config = config_loader.load_config(config_path=ucp.config_path(root))
    assert config["plugin_version"] == ucp.TO
    assert Path(config["plugin_root"]).resolve() == ucp.PLUGIN_ROOT.resolve()
    assert (verdicts_file(root).parent / "verdicts.json.consumed").is_file()
    assert f"Refreshed: {len(entries)}" in out and f"({len(entries)} were stale subsets, auto-adopted shipped)" in out
    changes = section(out, "CONFIG CHANGES", "CHAT SUMMARY")
    assert f"plugin_version: {ucp.FROM} → {ucp.TO}" in changes
    assert re.findall(r"^  (\S+): ", changes, re.MULTILINE) == ["plugin_version"]
    assert f"Stale subsets adopted:    {len(entries)}" in out
    assert "Comparator verdicts:" not in out  # the model prints that line, from the card's count rule
    offers = section(out, "OFFERS")
    assert "prune:safe-to-discard" in offers and "prune:inert" in offers
    assert "transfer-delete:" in offers and "half.md" not in offers, offers
    accept = next(line for line in offers.splitlines() if line.startswith("Accept all: "))
    assert "\\" not in accept  # every path is posix
    words = shlex.split(accept.removeprefix("Accept all: "))  # every argument survives a shell split intact
    assert same.resolve() in {Path(w).resolve() for w in words}, accept

    # an explicit --user-settings travels into the Accept-all line, so apply resolves the same file
    flag = tmp_path / "user" / "settings.json"
    capsys.readouterr()
    upgrade_run.print_offers([{"id": "thrifty-sonic:add", "default": "add", "text": "t",
                               "apply": ["--thrifty-sonic", "add"]}], root, PAIR, str(flag))
    accept = capsys.readouterr().out.splitlines()[-1]
    assert shlex.split(accept.removeprefix("Accept all: "))[-4:] == \
        ["--user-settings", flag.as_posix(), "--thrifty-sonic", "add"], accept
    # one shared helper set: no duplicate of the preflight's config reader
    assert not hasattr(upgrade_run, "load_project_config") and upgrade_run._mapping is upgrade_preflight._mapping


def test_short_sha_entry_rejected(tmp_path, capsys, monkeypatch):
    root = ucp.make_project(tmp_path)
    good = entry(root, "agent-authoring.md")
    short = entry(root, "skill-authoring.md", installed_sha256="abc123")
    missing = {k: v for k, v in entry(root, "rule-authoring.md").items() if k != "installed_sha256"}
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--verdicts-stdin", "--dry-argv",
                    stdin=json.dumps([good, short, missing]))
    assert code == 0, out
    assert "rejected skill-authoring.md" in out and "rejected rule-authoring.md" in out
    assert list(json.loads(verdicts_file(root).read_text(encoding="utf-8"))) == ["agent-authoring.md"]

    verdicts_file(root).unlink()  # the dry run staged it; a later call that does not write it would refuse
    seen = {}

    def failing_writer():
        seen["home"], seen["env"] = Path.home(), os.environ.get("HOME")
        raise SystemExit(1)

    def no_offers(*args, **kwargs):
        raise AssertionError("offers were built after a failed writer")

    monkeypatch.setattr(init_project, "main", failing_writer)
    monkeypatch.setattr(upgrade_run, "build_offers", no_offers)
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--no-calibrate")
    assert code == 1 and "OFFERS: none (writer failed)" in out, out
    assert seen == {"home": Path.home(), "env": os.environ.get("HOME")}  # the writer runs with the real environment

    # a successful write whose offer scan raises still ends with an OFFERS line, not a traceback
    def broken_scan(*args, **kwargs):
        raise RuntimeError("scan broke")

    monkeypatch.setattr(init_project, "main", lambda: None)
    monkeypatch.setattr(upgrade_run, "build_offers", broken_scan)
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--no-calibrate")
    assert code == 1 and "OFFERS: none (the offer scan failed: RuntimeError: scan broke)" in out, out


def test_summary_passes_calibration_lines_through(capsys):
    writer_out = ("Refreshed: 3\n  (1 were stale subsets, auto-adopted shipped)\n"
                  "Token Saver recalibrated:\n  Runner overhead:       0 → 12345\n"
                  "Token Saver calibration skipped (--no-calibrate)\n"
                  "Comparator verdicts: 2/2 (late: 0 resumed, 0 recorded after the writer ran; failed: 0)\n"
                  "Unrelated banner line\n")
    capsys.readouterr()
    upgrade_run.print_summary(writer_out, PAIR, [])
    summary = capsys.readouterr().out
    assert "Token Saver recalibrated:\n  Runner overhead:       0 → 12345" in summary
    assert "Token Saver calibration skipped (--no-calibrate)" in summary
    assert "Comparator verdicts:" not in summary and "Unrelated banner line" not in summary
    assert "Rules refreshed:          3" in summary and "Stale subsets adopted:    1" in summary
    assert not any("Comparator" in prefix for prefix in upgrade_run.PASS_THROUGH)


def test_refusals_write_nothing(tmp_path, capsys, monkeypatch):
    root = ucp.make_project(tmp_path)
    escaped = ucp.make_project(tmp_path, name="escaped")
    ucp.edit_config(escaped, r'^  planwise_root: .*$', '  planwise_root: "../outside"')
    wrong_from = f"{ucp.older_version(ucp.FROM)}-to-{ucp.TO}"
    wrong_to = f"{ucp.FROM}-to-{ucp.newer_version(ucp.TO)}"
    calls = [(root, bad) for bad in (wrong_from, wrong_to, "..\\..\\x-to-y", "../../x-to-y")]
    calls += [(escaped, PAIR), (ucp.make_no_config(tmp_path), PAIR)]
    for project, pair in calls:
        before = ucp.hash_tree(project)
        code, out = run(monkeypatch, capsys, project, "--pair", pair, "--verdicts-stdin", stdin="[]")
        assert code == 2, (project.name, pair, out)
        assert "UPGRADE REFUSED" in out
        assert ucp.hash_tree(project) == before, (project.name, pair)
    assert not verdicts_file(root, wrong_from).parent.exists()
    assert not (tmp_path / "outside").exists()


def test_verdicts_stdin_both_forms(tmp_path, capsys, monkeypatch):
    root = ucp.make_project(tmp_path)
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--verdicts-stdin", "--dry-argv", stdin="[]")
    assert code == 0 and "verdicts: none" in out
    assert not verdicts_file(root).exists()

    one = entry(root, "skill-authoring.md")
    run(monkeypatch, capsys, root, "--pair", PAIR, "--verdicts-stdin", "--dry-argv", stdin=json.dumps([one]))
    from_array = json.loads(verdicts_file(root).read_text(encoding="utf-8"))
    verdicts_file(root).unlink()
    run(monkeypatch, capsys, root, "--pair", PAIR, "--verdicts-stdin", "--dry-argv",
        stdin=json.dumps({"skill-authoring.md": one}))
    from_object = json.loads(verdicts_file(root).read_text(encoding="utf-8"))
    assert from_array == from_object
    assert from_array["skill-authoring.md"]["source"] == "agent"

    verdicts_file(root).unlink()
    fragment = entry(root, "agent-authoring.md", tolerated_fragments=["x"], source="agent")
    run(monkeypatch, capsys, root, "--pair", PAIR, "--verdicts-stdin", "--dry-argv", stdin=json.dumps([fragment]))
    landed = json.loads(verdicts_file(root).read_text(encoding="utf-8"))["agent-authoring.md"]
    assert landed["tolerated_fragments"] == ["x"] and landed["source"] == "agent"
    assert verdict_sanitize.sanitize_agent_entry(landed)["notes"] == "x"


def test_verdicts_file_matches_stdin_and_is_exclusive(tmp_path, capsys, monkeypatch):
    root = ucp.make_project(tmp_path)
    document = json.dumps([entry(root, "skill-authoring.md")])
    run(monkeypatch, capsys, root, "--pair", PAIR, "--verdicts-stdin", "--dry-argv", stdin=document)
    from_stdin = verdicts_file(root).read_bytes()
    verdicts_file(root).unlink()

    path = tmp_path / "verdicts document.json"
    path.write_bytes(b"\xef\xbb\xbf" + document.encode("utf-8"))  # a BOM from an editor is accepted
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--verdicts-file", str(path), "--dry-argv")
    assert code == 0, out
    assert verdicts_file(root).read_bytes() == from_stdin
    verdicts_file(root).unlink()

    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--verdicts-file", str(tmp_path / "absent.json"))
    assert code == 2 and "error: --verdicts-file: cannot read" in out and not verdicts_file(root).exists(), out
    with pytest.raises(SystemExit) as exc:
        upgrade_run.main(["--project-root", str(root), "--pair", PAIR, "--verdicts-stdin", "--verdicts-file", str(path)])
    assert exc.value.code == 2 and "not allowed with argument" in capsys.readouterr().err
    assert not verdicts_file(root).exists()


def test_answers_json_writes_answers_file(tmp_path, capsys, monkeypatch):
    root = ucp.make_project(tmp_path)
    answers_file = verdicts_file(root).parent / "migration-answers.json"
    answers = {"edge_drops": ["002->001"]}
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--answers-json", "--dry-argv",
                    stdin=json.dumps({"verdicts": [], "answers": answers}))
    assert code == 0, out
    assert json.loads(answers_file.read_text(encoding="utf-8")) == answers
    argv = upgrade_run.LAST_ARGV
    assert argv[argv.index("--migration-answers") + 1] == str(answers_file.parent.resolve() / answers_file.name)
    assert json.loads(out.split("writer argv: ", 1)[1]) == argv

    answers_file.unlink()
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--answers-json", "--dry-argv",
                    stdin=json.dumps({"verdicts": [], "answers": {}}))
    assert code == 0, out
    assert not answers_file.exists() and "--migration-answers" not in upgrade_run.LAST_ARGV

    # a staged input this call does not write is refused before any write, dry run or not
    answers_file.write_text("{}", encoding="utf-8")
    verdicts_file(root).write_text("{}", encoding="utf-8")
    folder = answers_file.parent
    listing = sorted(p.name for p in folder.iterdir())
    for extra in (["--dry-argv"], ["--no-calibrate"]):
        upgrade_run.LAST_ARGV = []
        code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--answers-json", *extra,
                        stdin=json.dumps({"verdicts": [], "answers": {}}))
        assert code == 2 and "stale staged input" in out, out
        assert "verdicts.json" in out and "migration-answers.json" in out, out
        assert sorted(p.name for p in folder.iterdir()) == listing and upgrade_run.LAST_ARGV == []
    # passing the input on stdin again is the way through: this call then writes (and owns) both files
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--answers-json", "--dry-argv",
                    stdin=json.dumps({"verdicts": [entry(root, "skill-authoring.md")], "answers": answers}))
    assert code == 0 and "--migration-answers" in upgrade_run.LAST_ARGV, out


def test_no_calibrate_reaches_writer_argv(tmp_path, capsys, monkeypatch):
    root = ucp.make_project(tmp_path)
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--no-calibrate", "--token-saver", "--dry-argv")
    assert code == 0, out
    assert "--no-calibrate" in upgrade_run.LAST_ARGV and "--token-saver" in upgrade_run.LAST_ARGV
    assert json.loads(out.split("writer argv: ", 1)[1]) == upgrade_run.LAST_ARGV
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--dry-argv")
    assert code == 0 and "--no-calibrate" not in upgrade_run.LAST_ARGV, out


def test_feedback_flags_reach_writer_argv(tmp_path, capsys, monkeypatch):
    root = ucp.make_project(tmp_path)
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--feedback-drafts", "quiet", "--feedback-enabled",
                    "--dry-argv")
    assert code == 0, out
    argv = upgrade_run.LAST_ARGV
    assert argv[argv.index("--feedback-drafts") + 1] == "quiet" and "--feedback-enabled" in argv
    assert json.loads(out.split("writer argv: ", 1)[1]) == argv
    code, out = run(monkeypatch, capsys, root, "--pair", PAIR, "--dry-argv")
    assert code == 0 and "--feedback-drafts" not in upgrade_run.LAST_ARGV, out
    assert "--feedback-enabled" not in upgrade_run.LAST_ARGV
    with pytest.raises(SystemExit) as exc:
        upgrade_run.main(["--project-root", str(root), "--pair", PAIR, "--feedback-drafts", "loud"])
    assert exc.value.code == 2 and "invalid choice" in capsys.readouterr().err


def test_summary_passes_feedback_banner_through(capsys):
    writer_out = ("Refreshed: 1\n"
                  "Feedback drafting: ON — Claude may now save local feedback drafts under planwise/Feedback/\n"
                  "  nothing is posted without /planwise feedback --drafts and your approval\n"
                  "  feedback.drafts: notify (default, no answer given); feedback.enabled: unchanged\n"
                  "Unrelated banner line\n")
    capsys.readouterr()
    upgrade_run.print_summary(writer_out, PAIR, [])
    summary = capsys.readouterr().out
    assert "Feedback drafting: ON — Claude may now save local feedback drafts under planwise/Feedback/\n" \
           "  nothing is posted without /planwise feedback --drafts and your approval\n" \
           "  feedback.drafts: notify (default, no answer given); feedback.enabled: unchanged" in summary
    assert "Unrelated banner line" not in summary


def test_flip_offers_screened_by_the_writer_checks(tmp_path):
    """An offer the flip writer would refuse is never built: the offer and the writer share its checks."""
    import flip_plan_status

    root = ucp.make_up_to_date(tmp_path)
    for folder, status in (("Kept", "complete"), ("Glued", "complete now")):
        ucp.write_master_plan(root, folder, folder[:3].upper(), status)
    assert flip_plan_status.status_value_refusal("complete now")
    assert flip_plan_status.status_value_refusal("complete") is None
    config_path, config = upgrade_preflight.resolve_config(root.resolve())
    report = upgrade_preflight._json_call([], "generate_plans_index.py", "--config", str(config_path), "--check",
                                          "--json")
    assert sorted(a["file"] for a in report["anomalies"]) == ["Glued/GLU-Master-Plan.md", "Kept/KEP-Master-Plan.md"]
    offers = upgrade_run.flip_offers(config, config_path)
    assert [o["id"] for o in offers] == ["flip-status:Kept/=COMPLETE"], offers


def test_card_question_document_reaches_writer(tmp_path, capsys, monkeypatch):
    """The card's run command and heredoc document, run as printed, stage the answers file the writer reads."""
    root = ucp.make_project(tmp_path, name="asked", diverged=(), question=True)
    capsys.readouterr()
    upgrade_preflight.run(["upgrade", "--project-root", str(root)])
    lines = capsys.readouterr().out.splitlines()
    head = next(i for i, line in enumerate(lines) if line.startswith("python -B ") and "upgrade_run.py" in line)
    assert lines[head + 2] == upgrade_preflight.HEREDOC
    words = shlex.split(lines[head].split(" <<", 1)[0])
    assert Path(words[2]).name == "upgrade_run.py" and "--answers-json" in words
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines[head + 1]))
    capsys.readouterr()
    code = upgrade_run.main([*words[3:], "--dry-argv"])
    out = capsys.readouterr().out
    assert code == 0, out
    argv = upgrade_run.LAST_ARGV
    staged = Path(argv[argv.index("--migration-answers") + 1])
    assert json.loads(staged.read_text(encoding="utf-8")) == {"edge_drops": ["002->001"]}
