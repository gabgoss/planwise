#!/usr/bin/env python3
"""Tests for scripts/plan_preflight.py (the `/planwise plan` card behind the skill's injected line).

The router runs as a subprocess, as the skill runs it, with `cwd` set to a
fixture project under `tmp_path`. No test reads the live project.

Run from the project root:
    python -B -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_plan_preflight.py
"""

import contextlib
import hashlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_DIR / "plugins" / "planwise" / "scripts"
SCRIPT = SCRIPTS_DIR / "skill_preflight.py"

sys.path.insert(0, str(SCRIPTS_DIR))

import config_loader
import plan_preflight
import scaffold_plan
import skill_preflight
from generate_plans_index import TABLE_SEPARATOR, render_plans_index

PLAN_BEGIN = "<!-- planwise:plan:begin -->"
PLAN_END = "<!-- planwise:plan:end -->"
PLAN_FALLBACK = "PLANWISE_PLAN_FALLBACK:"
NEW_FIELDS = ("context.plan_authoring", "token_saver", "index_shape", "abbreviations_in_use", "fill_inventory")
NEXT_SENTENCES = (
    ("the config, index gate and abbreviations above are already resolved: "
     "do not re-read config.yaml or the plans index"),
    "do not Read a template",
    "do not Write a task file; write bodies",
)
CONFIG_YAML = (
    "project:\n"
    '  name: "CardFixtureProject"\n'
    '  planwise_root: "planwise"\n'
    '  plans_dir: "Plans"\n'
    '  lessons_dir: "LessonsLearned"\n'
    "  index_files:\n"
    '    plans: "00-Index-Plans.md"\n'
    '    lessons: "00-Index-LessonsLearned.md"\n'
    f"plugin_root: '{(REPO_DIR / 'plugins' / 'planwise').as_posix()}'\n"
    "context:\n"
    "  token_saver: true\n"
    "  plan_authoring: inline\n"
)
LEGACY_PLANS_INDEX = (
    "# Plans Index\n\n"
    "Hand-written list of plans.\n\n"
    "| Abbrev | Name | Status |\n"
    "|---|---|---|\n"
    "| OLD | Older | COMPLETE |\n"
)
FILL_RE = re.compile(r"<!-- FILL: \{(.+?)\} -->")


def run_router(cwd):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "plan", "", ""],
        capture_output=True, text=True, encoding="utf-8", cwd=str(cwd), timeout=120, check=False)


def block(stdout):
    lines = [ln for ln in stdout.splitlines() if ln]
    start = lines.index(PLAN_BEGIN)
    return lines[start:]


def field(lines, key):
    hits = [ln.split(": ", 1)[1] for ln in lines if ln.startswith(f"{key}: ")]
    assert len(hits) == 1, (key, lines)
    return hits[0]


def write_generated_plans_index(planwise_dir, plans):
    config = config_loader.load_config(config_path=planwise_dir / "config.yaml")
    frame = render_plans_index(config).frame
    rows = "".join(f"| {a} | {n} | {s} | 2026-01-01 | 2026-01-01 | {n}/ |\n" for a, n, s in plans)
    text = frame.replace(TABLE_SEPARATOR + "\n", TABLE_SEPARATOR + "\n" + rows, 1)
    (planwise_dir / "Plans" / "00-Index-Plans.md").write_text(text, encoding="utf-8")
    for abbrev, name, status in plans:
        mp_dir = planwise_dir / "Plans" / name
        mp_dir.mkdir(parents=True, exist_ok=True)
        body = f"# {abbrev} Master Plan\n\n**Status:** {status}\n**Created:** 2026-01-01\n\n*Last Updated: 2026-01-01*\n"
        (mp_dir / f"{abbrev}-Master-Plan.md").write_text(body, encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    planwise_dir = tmp_path / "planwise"
    (planwise_dir / "Plans").mkdir(parents=True)
    (planwise_dir / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    write_generated_plans_index(planwise_dir, [("BBB", "Beta", "IN_PROGRESS"), ("AAA", "Alpha", "COMPLETE")])
    return tmp_path


def tree_sha256(root):
    """One sha256 over every file's relative path and bytes under `root`, skipping `.git`."""
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(root).rglob("*") if ".git" not in p.relative_to(root).parts):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8") + b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def numbered_steps(lines):
    """The numbered lines after `NEXT:`, with their numbers stripped."""
    start = next(i for i, ln in enumerate(lines) if ln.startswith("NEXT:"))
    return [ln.split(". ", 1)[1] for ln in lines[start + 1:] if re.match(r"^\d\. ", ln)]


def run_card_in_process(project, monkeypatch):
    """Run `skill_preflight.run(['plan'])` here with `project` as the working directory. Returns (stdout, stderr)."""
    monkeypatch.chdir(project)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        skill_preflight.run(["plan", "", ""])
    return block(out.getvalue()), err.getvalue()


def test_card_prints_the_five_new_fields_once_each(project):
    proc = run_router(project)
    assert (proc.returncode, proc.stderr) == (0, "")
    lines = block(proc.stdout)
    assert lines[-1] == PLAN_END
    assert PLAN_FALLBACK not in proc.stdout
    for key in NEW_FIELDS:
        assert sum(ln.startswith(f"{key}: ") for ln in lines) == 1, key
    assert field(lines, "context.plan_authoring") == "inline"
    assert field(lines, "token_saver") == "true"
    assert field(lines, "abbreviations_in_use") == "AAA, BBB"


def test_card_keeps_the_eight_gate_lines_first_and_unchanged(project):
    lines = block(run_router(project).stdout)
    assert lines[1:9] == skill_preflight.plan_block_lines(project)
    assert lines[9].startswith("context.plan_authoring: ")


def test_card_index_verdict_on_a_generated_and_a_legacy_index(project):
    lines = block(run_router(project).stdout)
    assert field(lines, "index_shape").startswith("any_legacy=false ")
    assert "plans=generated" in field(lines, "index_shape")

    (project / "planwise" / "Plans" / "00-Index-Plans.md").write_text(LEGACY_PLANS_INDEX, encoding="utf-8")
    lines = block(run_router(project).stdout)
    assert field(lines, "index_shape").startswith("any_legacy=true ")
    assert "plans=legacy" in field(lines, "index_shape")


def test_card_legacy_index_prints_the_gate_line_and_no_next(project):
    (project / "planwise" / "Plans" / "00-Index-Plans.md").write_text(LEGACY_PLANS_INDEX, encoding="utf-8")
    lines = block(run_router(project).stdout)
    assert not any(ln.startswith("NEXT:") for ln in lines)
    gate = [ln for ln in lines if ln.startswith("INDEX GATE FIRST: ")]
    assert len(gate) == 1
    assert "plans index is hand-authored" in gate[0]
    assert "references/index-shape-gate.md" in gate[0]
    assert "Nothing above is resolved for building" in gate[0]
    assert field(lines, "abbreviations_in_use") == "(unavailable: legacy index)"


def test_card_inventory_counts_equal_the_renderer_distinct_names(project):
    files, rec = scaffold_plan.render_all(plan_preflight.INVENTORY_SPEC)
    expected = {}
    for rel, text in files.items():
        kind = scaffold_plan.file_kind(rel)
        if kind:
            expected.setdefault(kind, set()).update(FILL_RE.findall(text))
    assert set(expected) == set(scaffold_plan.TEMPLATE_FILES)
    for kind, names in expected.items():
        assert names, kind
        fills = {n for n, c in rec.classes(kind).items() if c == "fill"}
        assert fills <= names, kind  # every name the recorder classes as fill reaches the text as a marker
    lines = block(run_router(project).stdout)
    shown = dict(pair.split("=") for pair in field(lines, "fill_inventory").split())
    assert {k: int(v) for k, v in shown.items()} == {k: len(v) for k, v in expected.items()}


def test_card_inline_next_mirrors_the_default_path(project):
    lines = block(run_router(project).stdout)
    assert sum(ln.startswith("NEXT:") for ln in lines) == 1
    assert "NEXT: inline" in lines
    steps = numbered_steps(lines)
    assert len(steps) == 4
    assert 'plan_build.py" keys --spec ' in steps[0]
    assert "<bodies-dir>/{Abbrev}-bodies-plan.md" in steps[1]
    assert "<bodies-dir>/{Abbrev}-bodies-S{XX}-{YY}.md per session" in steps[1]
    assert 'plan_build.py" lint --spec <spec.json> --bodies-dir <bodies-dir>' in steps[2]
    assert "until exit 0" in steps[2]
    assert 'plan_build.py" build --spec ' in steps[3]
    assert f'--config "{(project / "planwise" / "config.yaml").as_posix()}"' in steps[3]
    for sentence in NEXT_SENTENCES:
        assert sentence in lines, sentence


def test_card_delegated_next_follows_the_delegated_loop(project):
    config = project / "planwise" / "config.yaml"
    config.write_text(CONFIG_YAML.replace("plan_authoring: inline", "plan_authoring: delegated"), encoding="utf-8")
    lines = block(run_router(project).stdout)
    assert field(lines, "context.plan_authoring") == "delegated"
    assert "NEXT: delegated" in lines
    steps = numbered_steps(lines)
    assert len(steps) == 6
    assert 'plan_build.py" keys --spec ' in steps[0]
    assert "{Abbrev}-bodies-plan.md inline" in steps[1]
    assert "{Abbrev}-PlanNotes.md from templates/plan-notes.md" in steps[2]
    assert "planwise:plan-author" in steps[3] and "run_in_background: false" in steps[3]
    assert 'plan_build.py" lint --spec ' in steps[4]
    assert 'plan_build.py" build --spec ' in steps[5]
    assert NEXT_SENTENCES[0] in lines
    assert "do not Read a template" not in lines  # the delegated loop reads templates/plan-notes.md
    assert "do not Read a template other than templates/plan-notes.md" in lines
    assert "do not Write a task file; write bodies" in lines


def test_card_absent_index_prints_a_distinct_unavailable_value(project):
    (project / "planwise" / "Plans" / "00-Index-Plans.md").unlink()
    lines = block(run_router(project).stdout)
    assert field(lines, "abbreviations_in_use") == "(unavailable: absent index)"
    assert NEXT_SENTENCES[0] not in lines  # the abbreviations are not resolved
    assert any("abbreviations_in_use is unavailable" in ln for ln in lines)


def test_card_counts_an_abbreviation_with_only_a_master_plan(project):
    plans = project / "planwise" / "Plans"
    (plans / "Gamma").mkdir()
    (plans / "Gamma" / "CCC-Master-Plan.md").write_text("# CCC Master Plan\n", encoding="utf-8")
    (plans / "Delta" / "Meta-DDD").mkdir(parents=True)
    (plans / "Delta" / "Meta-DDD" / "DDD-META-Master-Plan.md").write_text("# DDD\n", encoding="utf-8")
    (plans / "Epsilon" / "Meta-EEE").mkdir(parents=True)
    lines = block(run_router(project).stdout)
    assert field(lines, "abbreviations_in_use") == "AAA, BBB, CCC, DDD, EEE"


def test_card_addon_failure_keeps_the_eight_lines(project, monkeypatch):
    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(plan_preflight, "fill_inventory", broken)
    lines, err = run_card_in_process(project, monkeypatch)
    assert err == ""
    assert lines[1:9] == skill_preflight.plan_block_lines(project)
    assert field(lines, "fill_inventory") == "(unavailable: RuntimeError)"
    assert field(lines, "context.plan_authoring") == "inline"
    assert not any(ln.startswith("NEXT:") for ln in lines)
    assert any(ln.startswith("CARD INCOMPLETE: ") for ln in lines)
    assert lines[-1] == PLAN_END


def test_card_stderr_from_a_field_never_reaches_the_card(project, monkeypatch):
    real = plan_preflight.fill_inventory

    def noisy():
        print("Warning: noisy field", file=sys.stderr)
        return real()

    monkeypatch.setattr(plan_preflight, "fill_inventory", noisy)
    lines, err = run_card_in_process(project, monkeypatch)
    assert err == ""
    assert any(ln.startswith("NEXT:") for ln in lines)


def test_card_router_loads_config_once_and_never_imports_itself(project):
    code = (
        "import json, runpy, sys\n"
        "sys.dont_write_bytecode = True\n"
        f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
        "import config_loader\n"
        "calls = []\n"
        "real = config_loader.load_config\n"
        "def counted(*a, **k):\n"
        "    calls.append(str(k.get('config_path')))\n"
        "    return real(*a, **k)\n"
        "config_loader.load_config = counted\n"
        "sys.modules['version_notice'] = None  # the notice resolves config on its own path\n"
        f"sys.argv = [{str(SCRIPT)!r}, 'plan', '', '']\n"
        "try:\n"
        f"    runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "print(json.dumps([len(calls), 'skill_preflight' in sys.modules]))\n"
    )
    proc = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True,
                          encoding="utf-8", cwd=str(project), timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "NEXT: inline" in proc.stdout  # positive control: the card ran in full
    loads, second_copy = json.loads(proc.stdout.strip().splitlines()[-1])
    assert loads == 1
    assert second_copy is False


def test_card_missing_config_prints_one_fallback_line(tmp_path):
    proc = run_router(tmp_path)
    assert (proc.returncode, proc.stderr) == (0, "")
    assert block(proc.stdout) == [PLAN_BEGIN, f"{PLAN_FALLBACK} FileNotFoundError: config.yaml not found", PLAN_END]


def test_card_parse_error_is_the_one_fallback_line(project):
    (project / "planwise" / "config.yaml").write_text("project:\n  name: [unclosed\n", encoding="utf-8")
    lines = block(run_router(project).stdout)
    assert len(lines) == 3
    assert lines[1].startswith(PLAN_FALLBACK)


def test_card_writes_nothing_into_the_project(project):
    before = tree_sha256(project)
    proc = run_router(project)
    assert PLAN_END in proc.stdout and PLAN_FALLBACK not in proc.stdout
    assert tree_sha256(project) == before
    # Control: one written byte must change the hash, or the equality above proves nothing.
    with (project / "planwise" / "config.yaml").open("ab") as handle:
        handle.write(b"\n")
    assert tree_sha256(project) != before


