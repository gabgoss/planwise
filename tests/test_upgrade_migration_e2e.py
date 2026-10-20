"""End-to-end test of the whole upgrade: one project shaped like a 1.0.5.1 install carries every
refusal class the auto-repairs closed, plus one reciprocal `blocks:` edge, and runs through the
preflight and `artifact_upgrade._run_upgrade`.

The preflight lists exactly one question. Without an answer the upgrade refuses only the
backlog, on that edge. With the answers file, built from the question's own option payload,
the banner holds no `REFUSED` line, all three indexes come out generated, and every ledger and
backup the banner names exists on disk.

The fixture is data-driven: `CLASSES` names each refusal class with the family that carries it,
and `FAMILY_BUILDERS` writes one family's files. A later class adds one `CLASSES` row and a line
in its family's builder. Every file is byte-built, so a CRLF source keeps its line endings.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for the sibling imports below

import init_project  # noqa: F401, I001 -- composition root first, so the import-order trap never fires
import artifact_upgrade
import migration_answers
from config_gen import InitConfig, drafts_key_state, read_plugin_version
from test_migrate_lessons_index import LESSON_001, LESSON_003, _index_text as lessons_index_text
from test_migrate_plans_index import A_COMMENT, ALP, BET, GAM, A_PLANS, legacy_index as plans_legacy_index

PREFLIGHT = SCRIPTS / "index_shape_preflight.py"
REAL_PLUGIN_ROOT = SCRIPTS.parent
FROM = "1.0.5.1"
TO = read_plugin_version(REAL_PLUGIN_ROOT)  # measured live, never hardcoded
QUESTION_LABEL = "001 blocks 002"  # the option that keeps `blocks: [002]` on item 001

# One row per refusal class the fixture carries: (family, class, the test that asserts its repair).
CLASSES = (
    ("backlog", "prefixed '## Dependencies' rows with a parenthetical note", "test_upgrade_with_answers"),
    ("backlog", "blockquote after the items table, and a preamble line", "test_every_byte"),
    ("backlog", "row id that disagrees with its file name", "test_upgrade_with_answers"),
    ("backlog", "Feature cell holding a code span with a pipe", "test_upgrade_with_answers"),
    ("backlog", "abbreviation lacking from `abbreviations:`", "test_upgrade_with_answers"),
    ("backlog", "reciprocal `blocks:` edge", "test_preflight, test_upgrade_without_answers"),
    ("lessons", "Master Table row whose lesson file is absent", "test_every_byte"),
    ("lessons", "Title cell holding a code span with a pipe", "test_upgrade_with_answers"),
    ("lessons", "hand-written changelog file already on disk", "test_upgrade_with_answers"),
    ("plans", "`<!--` opener that never closes", "test_upgrade_with_answers"),
    ("plans", "note after a row, three Master Plans", "test_every_byte"),
)

CONFIG = (
    'project:\n  name: "e2e-merged"\n  backlog_dir: "Backlog"\n  lessons_dir: "LessonsLearned"\n'
    '  index_files:\n    backlog: "00-Index-Backlog.md"\n    lessons: "00-Index-LessonsLearned.md"\n'
    '    plans: "00-Index-Plans.md"\n'
    'plans_dir: Plans\n'
    'abbreviations:\n  INFRA: Infrastructure and DevOps\n'  # SMP, the abbreviation the items use, is lacking
    'lesson_statuses:\n- documented\n- promoted\n- applied\n- rule\n- orphaned\n'
)

FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"
BACKLOG_HEADER = "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
CODE_SPAN_TITLE = "Parser handles `x | y` in cells"
BACKLOG_NAMES = {"001": "ITM-001-SMP-First.md", "002": "ITM-002-SMP-Second.md",
                 "003": "ITM-003-SMP-Third.md", "004": "ITM-004-SMP-Fourth.md"}
BACKLOG_TITLES = {"001": "First sample item", "002": "Second sample item", "003": "Third sample item",
                  "004": CODE_SPAN_TITLE}
# Row id and Blocks cell per item. Item 003's row id (013) disagrees with its file name (003).
BACKLOG_ROWS = {"001": ("ITM-001", "ITM-002"), "002": ("ITM-002", "ITM-001"),
                "003": ("ITM-013", ""), "004": ("ITM-004", "")}
# Frontmatter `blocks:` per item. The 001 <-> 002 pair is reciprocal once the Dependencies edge joins it.
BACKLOG_BLOCKS = {"001": "[]", "002": "[001]", "003": "[]", "004": "[]"}
BACKLOG_PREAMBLE = "Maintained by hand. Newest work goes at the top.\n\n"
BACKLOG_QUOTE = "> Sort order is priority first, then id.\n"
BACKLOG_DEPS = ("## Dependencies\n\n| ID | Blocks |\n|---|---|\n| ITM-001 | ITM-002 |\n"
                "| ITM-003 | ITM-004 (soft: shares the cell parser) |\n\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _item(item_id: str) -> str:
    fm = [f"id: {item_id}", f'title: "{BACKLOG_TITLES[item_id]}"', "priority: High", "status: NOT_STARTED",
          "abbrev: SMP", "created: 2024-01-01", f"blocks: {BACKLOG_BLOCKS[item_id]}"]
    return "\n".join(["---", *fm, "---", "", f"# {BACKLOG_TITLES[item_id]}", "", "Body text.", ""])


def _backlog_row(item_id: str) -> str:
    row_id, blocks = BACKLOG_ROWS[item_id]
    cells = [row_id, BACKLOG_TITLES[item_id], "High", "NOT_STARTED", "2024-01-01", blocks,
             f"[{row_id}]({BACKLOG_NAMES[item_id]})"]
    return "| " + " | ".join(cells) + " |\n"


def build_backlog(planwise: Path) -> None:
    backlog = planwise / "Backlog"
    rows = "".join(_backlog_row(i) for i in BACKLOG_NAMES)
    index = (f"# Backlog Index\n\n{BACKLOG_PREAMBLE}## Backlog Items\n\n{BACKLOG_HEADER}{rows}\n"
             f"{BACKLOG_QUOTE}\n{BACKLOG_DEPS}---\n\n{FOOTER}")
    _write(backlog / "00-Index-Backlog.md", index)
    for item_id, name in BACKLOG_NAMES.items():
        _write(backlog / name, _item(item_id))
    (backlog / "Archive").mkdir(parents=True, exist_ok=True)


def build_lessons(planwise: Path) -> None:
    lessons = planwise / "LessonsLearned"
    index = lessons_index_text().replace("| LL-001 | Fixture Lesson One |", "| LL-001 | Fixture Lesson One `a | b` |")
    _write(lessons / "00-Index-LessonsLearned.md", index)
    _write(lessons / "LL-001-PROC-One.md", LESSON_001)
    _write(lessons / "LL-003-PROC-Three.md", LESSON_003)  # LL-002 has a row and no file
    _write(lessons / "00-Changelog-LessonsLearned.md", "# My own changelog\n\n## Entry 7\n\nHand-written history.\n")
    (lessons / "Archive").mkdir(parents=True, exist_ok=True)


def build_plans(planwise: Path) -> None:
    # The `<!--` opener sits between rows, so a later row (Gamma) must still be carried.
    index = plans_legacy_index([ALP, BET, A_COMMENT, "<!-- never closed", GAM])
    plans = planwise / "Plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "00-Index-Plans.md").write_bytes(index)
    for rel, data in A_PLANS.items():
        target = plans / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


FAMILY_BUILDERS = {"backlog": build_backlog, "lessons": build_lessons, "plans": build_plans}


def build_project(tmp_path: Path, pinned: str = FROM) -> InitConfig:
    """Write the merged project under `tmp_path`, pinned at `pinned`, and return its InitConfig."""
    root = tmp_path / "proj"
    planwise = root / "planwise"
    posix_root = str(REAL_PLUGIN_ROOT).replace("\\", "/")
    _write(planwise / "config.yaml", f'plugin_root: "{posix_root}"\nplugin_version: "{pinned}"\n{CONFIG}')
    for family in sorted({family for family, _name, _test in CLASSES}):
        FAMILY_BUILDERS[family](planwise)
    return InitConfig(project_name="e2e-merged", project_root=root, plugin_root=REAL_PLUGIN_ROOT,
                      plugin_version=TO)


def _config_path(cfg) -> Path:
    return cfg.project_root / "planwise" / "config.yaml"


def preflight(cfg) -> dict:
    """The preflight's JSON, from a subprocess. `-B` keeps bytecode out of the shipped tree."""
    result = subprocess.run([sys.executable, "-B", str(PREFLIGHT), "--config", str(_config_path(cfg)), "--questions"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def upgrade(cfg, monkeypatch, capsys, **kwargs) -> tuple:
    """Drive `_run_upgrade` and return (exit code, captured banner)."""
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    code = artifact_upgrade._run_upgrade(cfg, **kwargs)
    return code, capsys.readouterr().out


def refused_lines(banner: str) -> list:
    return [ln for ln in banner.splitlines() if "REFUSED" in ln]


def banner_paths(banner: str, label: str) -> list:
    """Every path the banner prints after `label:`."""
    return [Path(m.group(1).strip()) for m in re.finditer(rf"^\s*{label}:\s+(\S.*)$", banner, re.MULTILINE)]


def answers_from_question(cfg, tmp_path: Path) -> dict:
    """Write the answers file from the preflight question's own option payload, then load it."""
    question = preflight(cfg)["backlog"]["questions"][0]
    option = next(o for o in question["options"] if QUESTION_LABEL in o["label"])
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(option["answer"]), encoding="utf-8")
    return migration_answers.load_answers(path)


def test_preflight_lists_exactly_one_question(tmp_path):
    report = preflight(build_project(tmp_path))
    assert {name: report[name]["shape"] for name in ("backlog", "lessons", "plans")} == \
        {"backlog": "legacy", "lessons": "legacy", "plans": "legacy"}
    assert report["any_legacy"] is True
    questions = [q for name in ("backlog", "lessons", "plans") for q in report[name]["questions"]]
    assert [q["id"] for q in questions] == ["reciprocal-edge"], report
    assert questions[0]["pairs"] == [["001", "002"]]
    assert [o for o in questions[0]["options"] if QUESTION_LABEL in o["label"]]


def test_upgrade_without_answers_refuses_only_the_reciprocal_edge(tmp_path, monkeypatch, capsys):
    cfg = build_project(tmp_path)
    code, banner = upgrade(cfg, monkeypatch, capsys)  # no answers: the control for the next test
    assert code == 0
    lines = refused_lines(banner)
    assert len(lines) == 1 and lines[0].startswith("Backlog index migration: REFUSED"), banner
    backlog_block = banner.split("Backlog index migration:", 1)[1].split("Lessons index migration:", 1)[0]
    assert "reciprocal blocks edge(s) 001<->002" in backlog_block
    fix = next(ln for ln in backlog_block.splitlines() if ln.strip().startswith("fix:"))
    assert "remove the other item's id" in fix and "blocks:" in fix
    # Lessons and plans migrate in the same run: the edge is the only refusal.
    assert "  migrated: " in banner.split("Lessons index migration:", 1)[1].split("Plans index migration:", 1)[0]
    assert "  migrated: " in banner.split("Plans index migration:", 1)[1]
    # The refusal left the backlog untouched, so its index is still hand-authored.
    assert "Backlog index migration:\n  migrated:" not in banner
    after = preflight(cfg)
    assert [after[name]["shape"] for name in ("backlog", "lessons", "plans")] == ["legacy", "generated", "generated"]


def _read(cfg, rel: str) -> str:
    return (cfg.project_root / "planwise" / rel).read_bytes().decode("utf-8")


def test_upgrade_with_answers_has_zero_refused_lines(tmp_path, monkeypatch, capsys):
    cfg = build_project(tmp_path)
    answers = answers_from_question(cfg, tmp_path)
    assert answers == {"edge_drops": ["002->001"]}
    code, banner = upgrade(cfg, monkeypatch, capsys, answers=answers)
    assert code == 0
    assert refused_lines(banner) == [], banner
    assert len(re.findall(r"^  migrated: ", banner, re.MULTILINE)) == 3
    assert _read(cfg, "config.yaml").count('plugin_version: "' + TO + '"') == 1
    # Every ledger and backup the banner names exists, and each backup set is listed in DISPOSITIONS.md.
    ledgers, backups = banner_paths(banner, "ledger"), banner_paths(banner, "backups")
    assert len(ledgers) == 3 and len(backups) == 3
    assert all(path.is_file() for path in ledgers), ledgers
    for path in backups:
        directory = Path(re.sub(r"\s+\(.*\)$", "", str(path)))  # the banner appends a "(N file(s)...)" note
        assert directory.is_dir() and (directory.parent / "DISPOSITIONS.md").is_file(), directory
    # Backlog: the answer kept 001 -> 002, the Dependencies edge unioned in 003 -> 004, the abbreviation was added.
    assert "blocks: [002]" in _read(cfg, "Backlog/ITM-001-SMP-First.md")
    assert "blocks: []" in _read(cfg, "Backlog/ITM-002-SMP-Second.md")
    assert "blocks: [004]" in _read(cfg, "Backlog/ITM-003-SMP-Third.md")
    assert "shares the cell parser" in _read(cfg, "Backlog/ITM-003-SMP-Third.md")
    assert yaml.safe_load(_read(cfg, "config.yaml"))["abbreviations"].keys() >= {"INFRA", "SMP"}
    backlog_ledger = json.loads(_read(cfg, "Backlog/00-Index-Backlog-Migration-Ledger.json"))
    dropped = [{k: v for k, v in e.items() if k != "path"} for e in backlog_ledger["edges"] if e.get("action")]
    assert dropped == [{"src": "002", "dst": "001", "action": "dropped", "source": "answer"}]
    assert next(e for e in backlog_ledger["edges"] if e.get("action"))["path"].endswith("ITM-002-SMP-Second.md")
    assert {"src": "003", "dst": "004", "source": "dependencies-table"} in backlog_ledger["edges"]
    assert backlog_ledger["abbreviations"]["added"] == ["SMP"]
    # The changelog's first entry is the relocated index text.
    first_entry = _read(cfg, "Backlog/00-Changelog-Backlog.md").split("## Entry 1", 1)[1].split("## Entry 2", 1)[0]
    assert BACKLOG_PREAMBLE.strip() in first_entry and BACKLOG_QUOTE.strip() in first_entry
    # Lessons: the hand-written changelog is folded in at the head, and the file-less row is relocated.
    lessons_changelog = _read(cfg, "LessonsLearned/00-Changelog-LessonsLearned.md")
    assert re.search(r"\A.*?\n+## Entry \d+\n+Pre-migration changelog file", lessons_changelog, re.DOTALL)
    assert "Hand-written history." in lessons_changelog
    assert "| LL-002 | Backfilled Title |" in lessons_changelog
    # Plans: the ledger lists the opener line that never closed.
    plans_ledger = _read(cfg, "Plans/00-Plans-Migration-Ledger.md")
    assert "unclosed-opener" in plans_ledger and "<!-- never closed" in plans_ledger


def test_real_upgrade_prints_the_drafts_banner_once(tmp_path, monkeypatch, capsys):
    cfg = build_project(tmp_path)
    answers = answers_from_question(cfg, tmp_path)
    assert drafts_key_state(yaml.safe_load(_read(cfg, "config.yaml"))) == "no-block"
    code, banner = upgrade(cfg, monkeypatch, capsys, answers=answers)
    assert code == 0
    first = [ln for ln in banner.splitlines() if ln.startswith("Feedback drafting:")]
    assert len(first) == 1 and "ON" in first[0], banner
    written = yaml.safe_load(_read(cfg, "config.yaml"))
    assert drafts_key_state(written) == "set"
    assert "drafts: notify" in _read(cfg, "config.yaml")
    code, banner = upgrade(cfg, monkeypatch, capsys)
    assert code == 0
    assert [ln for ln in banner.splitlines() if ln.startswith("Feedback drafting:")] == [], banner


def test_second_run_is_silent(tmp_path, monkeypatch, capsys):
    cfg = build_project(tmp_path)
    upgrade(cfg, monkeypatch, capsys, answers=answers_from_question(cfg, tmp_path))
    index_files = [p for family in ("Backlog", "LessonsLearned", "Plans")
                   for p in sorted((cfg.project_root / "planwise" / family).rglob("*")) if p.is_file()]
    before = {p: p.read_bytes() for p in index_files}
    code, banner = upgrade(cfg, monkeypatch, capsys)
    assert code == 0
    assert "index migration:" not in banner and refused_lines(banner) == [], banner
    assert banner.rstrip().splitlines()[-1] == "Already up to date."
    assert {p: p.read_bytes() for p in index_files} == before
    report = preflight(cfg)
    assert [report[name]["shape"] for name in ("backlog", "lessons", "plans")] == ["generated"] * 3


def test_every_byte_of_the_old_backlog_index_is_accounted(tmp_path, monkeypatch, capsys):
    cfg = build_project(tmp_path)
    upgrade(cfg, monkeypatch, capsys, answers=answers_from_question(cfg, tmp_path))
    backlog = json.loads(_read(cfg, "Backlog/00-Index-Backlog-Migration-Ledger.json"))
    assert backlog["changelog"]["unaccounted"] == 0
    assert (backlog["dedup"]["unaccounted_units"], backlog["dedup"]["unaccounted_bytes"]) == (0, 0)
    assert backlog["verification"] == {"verified": True, "misses": []}
    assert [line["kind"] for line in backlog["relocated_index_lines"]] == ["preamble", "text after the table"]
    plans = _read(cfg, "Plans/00-Plans-Migration-Ledger.md")
    assert "- Unaccounted: 0" in plans and "- Verified: yes" in plans
    assert "- Rows before (PRE): 3" in plans and "- Rows after (POST): 3" in plans
    lessons = json.loads(_read(cfg, "LessonsLearned/00-Lessons-Migration-Ledger.json"))
    assert lessons["unaccounted"] == 0 and lessons["verification"]["verified"] is True
    assert lessons["relocated"]["rows"] == 1
