"""Tests for index_shape_preflight.py: the read-only report of the three index shapes and
the questions a migration would ask. The script is driven by subprocess, the way a handler
runs it. Every test asserts the exit code first, so an absent script fails all of them.
Fixtures are written under tmp_path, never under plugins/planwise/."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "index_shape_preflight.py"

HEADER = "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"
NAMES = {"001": "ITM-001-SMP-First.md", "002": "ITM-002-SMP-Second.md"}
TITLES = {"001": "First sample item", "002": "Second sample item"}
DEPS_TABLE = "## Dependencies\n\n| ID | Blocks |\n|---|---|\n| 001 | 002 |\n\n"
MIGRATED_INDEX = ("Generated: 2024-01-01\n\n| ID | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
                  "|---|---|---|---|---|---|---|---|---|\n")
LESSONS_INDEX = "Generated: 2024-01-01\n\n| ID | Title | Status |\n|---|---|---|\n"
PLANS_INDEX = "Generated: 2024-01-01\n\n| Abbrev | Name | Status |\n|---|---|---|\n"
UNRECOGNIZED_INDEX = ("## Backlog Items\n\n| ID | Feature | Owner | Files |\n|---|---|---|---|\n"
                      "| 001 | First sample item | nobody | [001](ITM-001-SMP-First.md) |\n\n" + FOOTER)


def fm(item_id, blocks="[]"):
    keys = {"id": item_id, "title": f'"{TITLES[item_id]}"', "priority": "High", "status": "NOT_STARTED",
            "abbrev": "SMP", "created": "2024-01-01", "blocks": blocks}
    return "\n".join(["---"] + [f"{k}: {v}" for k, v in keys.items()] + ["---", ""]) + "\n"


def item(item_id, blocks="[]"):
    return fm(item_id, blocks) + f"# {TITLES[item_id]}\n\nBody text.\n"


def row(item_id, blocks=""):
    cells = [item_id, TITLES[item_id], "High", "NOT_STARTED", "2024-01-01", blocks, f"[{item_id}]({NAMES[item_id]})"]
    return "| " + " | ".join(cells) + " |\n"


def legacy_index(*rows, deps=""):
    return f"# Backlog Index\n\n## Backlog Items\n\n{HEADER}{''.join(rows)}\n{deps}{FOOTER}"


def project(tmp_path, backlog_index, items=(), lessons=LESSONS_INDEX, plans=PLANS_INDEX):
    """A project tree with the three indexes; returns the config path."""
    planwise = tmp_path / "proj" / "planwise"
    backlog = planwise / "Backlog"
    (backlog / "Archive").mkdir(parents=True)
    (planwise / "LessonsLearned").mkdir()
    (planwise / "Plans").mkdir()
    for item_id, text in items:
        (backlog / NAMES[item_id]).write_bytes(text.encode("utf-8"))
    (backlog / "00-Index-Backlog.md").write_bytes(backlog_index.encode("utf-8"))
    (planwise / "LessonsLearned" / "00-Index-LessonsLearned.md").write_bytes(lessons.encode("utf-8"))
    (planwise / "Plans" / "00-Index-Plans.md").write_bytes(plans.encode("utf-8"))
    (planwise / "config.yaml").write_bytes(b'project:\n  name: "test-project"\n  backlog_dir: "Backlog"\n'
                                           b'  lessons_dir: "LessonsLearned"\n  plans_dir: "Plans"\n')
    return planwise / "config.yaml"


def reciprocal_project(tmp_path):
    index_text = legacy_index(row("001", blocks="002"), row("002", blocks="001"), deps=DEPS_TABLE)
    return project(tmp_path, index_text, [("001", item("001")), ("002", item("002", blocks="[001]"))], )


def preflight(config_path, *args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), "--config", str(config_path), *args],
                          capture_output=True, text=True, check=False)


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_reports_three_shapes_on_a_generated_tree(tmp_path):
    result = preflight(project(tmp_path, MIGRATED_INDEX))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert [out[f]["shape"] for f in ("backlog", "lessons", "plans")] == ["generated"] * 3
    assert out["any_legacy"] is False


def test_reports_legacy_and_any_legacy_true(tmp_path):
    result = preflight(project(tmp_path, legacy_index(row("001")), [("001", item("001"))]))
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["backlog"]["shape"] == "legacy"
    assert out["lessons"]["shape"] == "generated"
    assert out["any_legacy"] is True


def test_questions_lists_the_reciprocal_question(tmp_path):
    result = preflight(reciprocal_project(tmp_path), "--questions")
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    questions = out["backlog"]["questions"]
    assert [q["id"] for q in questions] == ["reciprocal-edge"]
    assert len(questions[0]["options"]) == 3
    assert any("reciprocal" in line for line in out["backlog"]["would_refuse"])


def test_never_writes(tmp_path):
    config_path = reciprocal_project(tmp_path)
    before = snapshot(tmp_path)
    result = preflight(config_path, "--questions")
    assert result.returncode == 0, result.stderr
    assert before and snapshot(tmp_path) == before


def test_report_failure_keeps_the_legacy_shape(tmp_path):
    """A report that raises on a classified legacy index must not turn it unrecognized."""
    sys.path.insert(0, str(SCRIPT.parent))
    import config_loader
    import index_shape_preflight as pre
    import migrate_backlog_support as sup

    config_path = project(tmp_path, legacy_index(row("001")), [("001", item("001"))])
    config = config_loader.load_config(SCRIPT, config_path=config_path)

    def failing_report(cfg, path):
        raise RuntimeError("report boom")

    entry = pre.inspect(config, "_index_path", sup.classify_shape, failing_report, True)
    assert entry["shape"] == "legacy"
    assert "report boom" in entry["report_error"]
    assert entry["would_refuse"] == [] and entry["questions"] == []


def test_exit_zero_on_unrecognized(tmp_path):
    result = preflight(project(tmp_path, UNRECOGNIZED_INDEX, [("001", item("001"))]), "--questions")
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["backlog"]["shape"] == "unrecognized"
    assert out["any_legacy"] is False
