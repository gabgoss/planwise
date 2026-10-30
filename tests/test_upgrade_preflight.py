"""upgrade_preflight: the upgrade card, its branches, its NEXT block and the read-only proof.

Every project is built by tests/upgrade_card_project.py from this repo's own plugin tree, inside
`tmp_path`. `_isolate` below patches the CLI-version probe, so no init starts `claude`.
"""
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import doctor_cli
import doctor_probes
import upgrade_card_project as ucp
import upgrade_preflight
import upgrade_run

BEGIN, END, HEREDOC = upgrade_preflight.BEGIN, upgrade_preflight.END, upgrade_preflight.HEREDOC
GH_OK = {"path": "/usr/bin/gh", "note": "", "version": "2.0", "authenticated": True, "timed_out": False}
DIVERGED = [name for name, *_rest in ucp.DIVERGENCES]


@pytest.fixture(autouse=True)
def _isolate(_isolated_home, monkeypatch):
    ucp.isolate(monkeypatch)


def run_card(capsys, root, *flags) -> str:
    capsys.readouterr()
    assert upgrade_preflight.run(["upgrade", "--project-root", str(root), *flags]) == 0
    return capsys.readouterr().out


def table_rows(card: str) -> dict:
    rows = {}
    for line in card.splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if line.startswith("| ") and len(cells) == 5 and cells[0].endswith(".md"):
            rows[cells[0]] = cells
    return rows


def next_block(card: str) -> str:
    return card[card.index("\nNEXT\n"):]


def run_line(card: str) -> str:
    return next(line for line in card.splitlines() if line.startswith("python -B ") and "upgrade_run.py" in line)


def heredoc_document(card: str) -> str:
    lines = card.splitlines()
    head = lines.index(run_line(card))
    return lines[head + 1]


def tree_and_home(root: Path) -> tuple:
    return ucp.hash_tree(root), ucp.hash_tree(Path.home())


def test_card_markers_and_rows(tmp_path, capsys):
    card = run_card(capsys, ucp.make_project(tmp_path))
    lines = card.splitlines()
    assert lines[0] == BEGIN and lines[-1] == END
    assert f"pair: {ucp.PAIR}  branch: upgrade" in card
    assert f"Diverged rules ({len(DIVERGED)}):" in card
    assert "| filename | set | installed_sha256 | inline | agent |" in card
    rows = table_rows(card)
    assert sorted(rows) == sorted(DIVERGED)
    assert all(cells[1] == "installed" for cells in rows.values())
    assert len(card) < 30000


def test_row_sha_equals_installed_hash(tmp_path, capsys):
    root = ucp.make_project(tmp_path)
    card = run_card(capsys, root)
    shas = dict(item.split("=", 1) for item in next(
        line for line in card.splitlines() if line.startswith("shas: "))[len("shas: "):].split())
    assert sorted(shas) == sorted(DIVERGED)
    rows = table_rows(card)
    for name, sha in shas.items():
        assert sha == ucp.installed_sha(root / ucp.RULES / name)
        assert rows[name][2] == f"{sha[:4]}…{sha[-4:]}"


def test_diverged_rows_takes_sha_from_row(tmp_path, monkeypatch):
    root = ucp.make_project(tmp_path)
    cfg = upgrade_preflight.build_cfg(upgrade_preflight.resolve_config(root)[1], root)
    real = doctor_cli._list_diverged_rows(cfg)
    marker = "f" * 64  # not the hash of any file: only the row can supply it
    monkeypatch.setattr(doctor_cli, "_list_diverged_rows", lambda c: [dict(r, installed_sha256=marker) for r in real])
    rows = upgrade_preflight.diverged_rows(cfg)
    assert [r["filename"] for r in rows] == [r["filename"] for r in real] and len(rows) == len(DIVERGED)
    assert {r["installed_sha256"] for r in rows} == {marker}


def test_inline_verdicts_and_agent_flag(tmp_path, capsys):
    rows = table_rows(run_card(capsys, ucp.make_project(tmp_path)))
    assert [(rows[n][3], rows[n][4]) for n, *_rest in ucp.DIVERGENCES] == \
        [(inline, agent) for _n, _t, inline, agent in ucp.DIVERGENCES]
    assert {cells[4] for cells in rows.values()} == {"yes", "no"}  # the agent column is exercised both ways


def test_earlier_pair_transfers(tmp_path, capsys):
    root = ucp.make_project(tmp_path)
    assert "Earlier-pair transfers (0):" in run_card(capsys, root)
    ucp.seed_transfer(root, ucp.EARLIER_PAIR, "rule-authoring.md", ucp.shipped("rule-authoring.md"),
                      source="rule-authoring.md")
    card = run_card(capsys, root)
    assert "Earlier-pair transfers (1):" in card
    assert f"{ucp.EARLIER_PAIR}/rule-authoring.md: now-upstream" in card


def test_run_normalises_router_argv(tmp_path, capsys):
    """The router passes empty strings and unexpanded `$name` placeholders; the card drops both."""
    root = ucp.make_project(tmp_path)
    plain = run_card(capsys, root)
    capsys.readouterr()
    assert upgrade_preflight.run(["upgrade", "", "$flag1", "  ", "--project-root", str(root), "$flag2"]) == 0
    assert capsys.readouterr().out == plain
    assert upgrade_preflight.run(["", "$sub", "--project-root", str(root)]) == 0
    assert capsys.readouterr().out == plain


def test_read_only_proof_pre_upgrade(tmp_path, capsys):
    root = ucp.make_project(tmp_path)
    before = tree_and_home(root)
    assert len(before[0]) > 10 and before[1]  # the walk sees the project and the home settings file
    assert BEGIN in run_card(capsys, root)
    assert tree_and_home(root) == before


def test_read_only_proof_discriminates(tmp_path, capsys):
    root = ucp.make_project(tmp_path)
    before = ucp.hash_tree(root)
    run_card(capsys, root)
    assert ucp.hash_tree(root) == before
    ucp.config_path(root).write_text("changed\n", encoding="utf-8")
    assert ucp.hash_tree(root) != before


def test_read_only_proof_up_to_date_runs_every_report(tmp_path, capsys, monkeypatch):
    root = ucp.make_up_to_date(tmp_path)
    monkeypatch.setattr(doctor_probes, "_gh_environment", lambda: dict(GH_OK))
    calls = []
    real = upgrade_preflight._run_script

    def spy(argv, extra_env=None):
        calls.append([Path(a).name for a in argv[2:]])
        return real(argv, extra_env)

    monkeypatch.setattr(upgrade_preflight, "_run_script", spy)
    before = tree_and_home(root)
    card = run_card(capsys, root)
    assert tree_and_home(root) == before
    assert "Nothing to do" in card  # every report ran and passed
    flags = {(c[0], c[-1]) for c in calls}
    assert flags == {("migrate_backlog_index.py", "--report"), ("migrate_lessons_index.py", "--report"),
                     ("generate_plans_index.py", "--json"), ("index_shape_preflight.py", "--questions"),
                     ("generate_lessons_index.py", "--json")}
    assert len(calls) == 6  # the questions report runs once for the card and once for the no-op proof
    assert all("--check" in c for c in calls if c[0] in ("generate_plans_index.py", "generate_lessons_index.py"))


def test_user_settings_line(tmp_path, capsys):
    root = ucp.make_project(tmp_path)
    home = (Path.home() / ".claude" / "settings.json").as_posix()
    assert f"user settings: {home} (step 2: home settings)" in run_card(capsys, root)
    flag = (tmp_path / "elsewhere" / "settings.json").as_posix()
    card = run_card(capsys, root, "--user-settings", flag)
    assert f"user settings: {flag} (step 1: --user-settings flag)" in card
    assert f'--user-settings "{flag}"' in run_line(card)


def test_missing_config_fallback(tmp_path, capsys):
    root = ucp.make_no_config(tmp_path)
    out = run_card(capsys, root)
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0].startswith(f"PLANWISE_UPGRADE_FALLBACK: config.yaml not found at {root.resolve().as_posix()}/config.yaml")
    assert BEGIN not in out and END not in out and "NEXT" not in out


def test_branch_repoint(tmp_path, capsys):
    root = ucp.make_project(tmp_path, name="repoint", pinned=ucp.TO)
    ucp.edit_config(root, r"^plugin_root: .*$", f'plugin_root: "{(tmp_path / "old-cache").as_posix()}"')
    card = run_card(capsys, root)
    assert "branch: repoint" in card
    assert "yes" in {cells[4] for cells in table_rows(card).values()}  # an agent row exists...
    assert "rule-comparator" not in card  # ...and a repoint still spawns no comparator


def test_branch_downgrade(tmp_path, capsys):
    card = run_card(capsys, ucp.make_downgrade(tmp_path))
    assert "branch: downgrade" in card and "--allow-downgrade" in run_line(card)
    assert "read handlers/upgrade.md, Step 1" in next_block(card)
    assert "handlers/full" not in card and "full-handler" not in card


def test_up_to_date_noop_next(tmp_path, capsys, monkeypatch):
    root = ucp.make_up_to_date(tmp_path)
    assert "Nothing to do" not in run_card(capsys, root)  # control: gh absent is a pending offer
    monkeypatch.setattr(doctor_probes, "_gh_environment", lambda: dict(GH_OK))
    card = run_card(capsys, root)
    assert "branch: up-to-date" in card
    assert f'Nothing to do. Report: "Plugin version: {ucp.TO} — already up to date."' in card
    assert "upgrade_run.py" not in card


def test_pre_upgrade_noop_false_with_reason(tmp_path, capsys):
    root = ucp.make_project(tmp_path)
    card = run_card(capsys, root)
    assert "Nothing to do" not in card and "upgrade_run.py" in card
    config_path = ucp.config_path(root)
    ok, reason, argvs = upgrade_preflight.noop_proof("upgrade", [], {}, config_path, {}, "project")
    assert (ok, argvs) == (False, [])
    assert reason == "branch is upgrade, not up-to-date"
    ok, reason, _ = upgrade_preflight.noop_proof("up-to-date", [{"filename": "x"}], {}, config_path, {}, "project")
    assert not ok and "diverged" in reason


def test_next_block_literal_verdict_stdin_form(tmp_path, capsys):
    block = next_block(run_card(capsys, ucp.make_project(tmp_path)))
    assert f"--verdicts-stdin <<'{HEREDOC}'" in block
    assert f"\n{HEREDOC}\n" in block
    for field in ("installed_sha256", "source", "tolerated_fragments", "rationale"):
        assert f'"{field}"' in block


def test_heredoc_fallback_names_verdicts_file(tmp_path, capsys):
    fallback = "`--verdicts-file {path}` instead of `--verdicts-stdin`"
    assert fallback in next_block(run_card(capsys, ucp.make_project(tmp_path)))
    no_agent = ucp.make_project(tmp_path, name="no-agent",
                                diverged=[d for d in ucp.DIVERGENCES if d[3] == "no"])
    card = run_card(capsys, no_agent)
    assert {cells[4] for cells in table_rows(card).values()} == {"no"}
    assert "--verdicts-file" not in card and "--verdicts-stdin" not in card


def test_token_saver_question_only_when_off(tmp_path, capsys):
    off = run_card(capsys, ucp.make_project(tmp_path))
    assert "token_saver: off" in off and "Token Saver question:" in next_block(off)
    assert "--token-saver" not in run_line(off)
    on = run_card(capsys, ucp.make_project(tmp_path, name="on", token_saver=True))
    assert "token_saver: on" in on and "Token Saver question" not in on
    assert "--token-saver" in run_line(on)


def test_comparator_count_rule_in_next(tmp_path, capsys):
    block = next_block(run_card(capsys, ucp.make_project(tmp_path)))
    assert upgrade_preflight.COMPARATOR_LINE in block
    assert "omit the line when the comparator step did not run" in block


def test_card_has_no_version_notice(tmp_path, capsys):
    for root in (ucp.make_project(tmp_path), ucp.make_up_to_date(tmp_path)):
        lines = run_card(capsys, root).splitlines()
        assert lines[1].startswith("UPGRADE CARD")
        assert not any(line.startswith("planwise:") for line in lines)


def test_migration_questions_block(tmp_path, capsys):
    assert "Migration questions (0):" in run_card(capsys, ucp.make_project(tmp_path))
    card = run_card(capsys, ucp.make_project(tmp_path, name="asked", diverged=(), question=True))
    assert "Migration questions (1):" in card
    assert "backlog [reciprocal-edge]:" in card
    assert "the Token Saver question and every migration question listed above" in next_block(card)
    words = shlex.split(run_line(card).split(" <<", 1)[0])
    assert "--answers-json" in words and "--verdicts-stdin" in words
    entries, answers, error = upgrade_run.parse_stdin(heredoc_document(card), True)
    assert (entries, error) == ([], "")
    assert list(answers) == ["edge_drops"] and answers["edge_drops"]  # keyed by answer kind, not question id


DROP_DRAFTS = (r"^  drafts: notify\n", "")


def test_feedback_questions_only_when_drafts_key_absent(tmp_path, capsys):
    kept = run_card(capsys, ucp.make_project(tmp_path))
    assert "feedback_drafts: set" in kept
    assert "Feedback drafts question:" not in kept and "Feedback posting question:" not in kept
    assert "--feedback-drafts" not in kept and "--feedback-enabled" not in kept
    root = ucp.make_project(tmp_path, name="nodrafts")
    ucp.edit_config(root, *DROP_DRAFTS)
    card = run_card(capsys, root)
    assert "feedback_drafts: absent" in card
    block = next_block(card)
    assert f"Feedback drafts question: {upgrade_preflight.FEEDBACK_DRAFTS_QUESTION}" in block
    assert f"Feedback posting question: {upgrade_preflight.FEEDBACK_ENABLED_QUESTION}" in block
    assert "--feedback-drafts {value}" in block and "--feedback-enabled" in block
    assert "Unattended: add neither" in block
    assert "--feedback-drafts" not in run_line(card)  # the model adds the flags from the answers


def test_feedback_posting_question_recommends_yes():
    question = upgrade_preflight.FEEDBACK_ENABLED_QUESTION
    assert '"Yes (Recommended)"' in question and '"No"' in question
    assert question.index('"Yes (Recommended)"') < question.index('"No"')
    assert "recommended" not in question.replace("(Recommended)", "")


@pytest.mark.parametrize("handler", ["upgrade.md", "init.md"])
def test_feedback_posting_question_handlers_carry_the_constant_verbatim(handler):
    text = (Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "handlers" / handler).read_text(
        encoding="utf-8")
    assert upgrade_preflight.FEEDBACK_ENABLED_QUESTION in text


def test_feedback_questions_merge_under_the_question_limit(tmp_path, capsys):
    root = ucp.make_project(tmp_path, name="merged", diverged=(), question=True)
    ucp.edit_config(root, *DROP_DRAFTS)
    block = next_block(run_card(capsys, root))
    assert "Ask one AskUserQuestion with the Token Saver question and the feedback drafts question" in block
    assert "and every migration question listed above" in block  # 1 + 2 + 1 = 4, the limit
    assert upgrade_preflight.question_steps(False, [("backlog", {})] * 2, "absent")[0].startswith(
        "Ask the Token Saver question and the feedback drafts question and the feedback posting question in one ")
    on = upgrade_preflight.question_steps(True, [], "no-block")
    assert on[0] == "Ask one AskUserQuestion with the feedback drafts question and the feedback posting question."
    assert upgrade_preflight.question_steps(True, [], "set") == []


def test_feedback_drafts_header_states(tmp_path, capsys):
    root = ucp.make_project(tmp_path, name="noblock")
    ucp.edit_config(root, r"^feedback:$", "unrelated_block:")  # the block is renamed away: no `feedback` key
    card = run_card(capsys, root)
    assert "feedback_drafts: no block" in card
    assert "Feedback drafts question:" in next_block(card)


def test_absent_drafts_key_breaks_noop_proof(tmp_path, capsys, monkeypatch):
    root = ucp.make_up_to_date(tmp_path)
    monkeypatch.setattr(doctor_probes, "_gh_environment", lambda: dict(GH_OK))
    assert "Nothing to do" in run_card(capsys, root)  # control: the untouched project passes
    ucp.edit_config(root, *DROP_DRAFTS)
    card = run_card(capsys, root)
    assert "Nothing to do" not in card and "feedback_drafts: absent" in card
    config_path, config = upgrade_preflight.resolve_config(root.resolve())
    ok, reason, argvs = upgrade_preflight.noop_proof("up-to-date", [], config, config_path, {}, "project")
    assert (ok, reason, argvs) == (False, "config has no feedback.drafts key", [])


def test_gh_state_uses_shared_probe(monkeypatch):
    """gh_state reads doctor_probes._gh_environment and runs nothing itself, with or without gh on PATH."""
    which_calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail(f"gh_state ran a process: {a}"))
    cases = [({"path": "/usr/bin/gh", "authenticated": True, "timed_out": False}, "ok"),
             ({"path": "/usr/bin/gh", "authenticated": False, "timed_out": False}, "unauthenticated"),
             ({"path": None, "authenticated": False, "timed_out": False}, "absent"),
             ({"path": "/usr/bin/gh", "authenticated": False, "timed_out": True}, "timed-out")]
    for on_path in ("/usr/bin/gh", None):
        monkeypatch.setattr("shutil.which", lambda name, *a, on_path=on_path, **k: which_calls.append(name) or on_path)
        for env, expected in cases:
            probes = []
            monkeypatch.setattr(doctor_probes, "_gh_environment",
                                lambda env=env, probes=probes: probes.append(1) or dict(env))
            assert upgrade_preflight.gh_state() == expected
            assert probes == [1]
    assert "gh" not in which_calls
