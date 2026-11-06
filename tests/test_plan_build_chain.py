"""Tests for the gate chain `plan_build.py build` runs after the write.

Every scratch tree lives under tmp_path. The fixture is invented sample vocabulary.
"""

import contextlib
import io
import json
import re
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

import plan_build as pb
import scaffold_plan as sp
import token_saver_scan as tss
from test_plan_build import _task, bodies_set, make_spec, under

TEMPLATES = sp.DEFAULT_TEMPLATES
GATE_NAMES = ["estimates", "headings", "deviations", "scan", "index"]
GATE_RE = re.compile(r"^gate=(\w+) status=(\w+) files=(\d+)(?: (.*))?$", re.MULTILINE)
CHECKLIST = "## Post-Session Checklist"
SESSION_SIZES = [4, 4, 4, 4, 4, 4, 4, 4, 3]  # 9 sessions, 35 tasks, in one sprint
REPORT_CAP = 30_000  # a cap the plan chose, not an external limit

def big_spec():
    """A 1-sprint, 9-session, 35-task fixture built from the sample spec's own task shape."""
    spec = make_spec()
    base = spec["sprints"][0]["sessions"][0]
    sessions = []
    for number, size in enumerate(SESSION_SIZES, start=1):
        tasks = [_task(t, f"Work{number}x{t}", "Sonnet", [t - 1] if t > 1 else [], [f"src/orchard/m{number}_{t}.py"])
                 for t in range(1, size + 1)]
        sessions.append(dict(base, number=number, name=f"Session{number}", tasks=tasks,
                             prerequisite="None (first session)" if number == 1 else "The earlier session"))
    spec["sprints"][0]["sessions"] = sessions
    return spec


def run_cli(argv):
    """Run `plan_build.main` in process. Return (exit code, stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = pb.main(argv)
    return code, out.getvalue()


class Plan:
    """One plan folder under `root`: spec, bodies, config, a Scaffold sibling and the out folder."""

    def __init__(self, root, spec=None, bodies=None, config="plans: plans\n", scaffold=True, out=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.spec = self.root / "spec.json"
        self.spec.write_text(json.dumps(spec or make_spec()), encoding="utf-8")
        if bodies is None:
            bodies = bodies_set(pb.render_core(str(self.spec), TEMPLATES)[2])
        self.bodies = self.root / "bodies"
        self.bodies.mkdir()
        for name, text in bodies.items():
            (self.bodies / name).write_bytes(text.encode("utf-8"))
        self.config = self.root / "config.yaml"
        self.config.write_text(config, encoding="utf-8")
        self.out = Path(out) if out else self.root / "Exec-QZX"
        if scaffold:
            (self.out.parent / "Scaffold-QZX").mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "QZX-build-manifest.json"

    def run(self, *extra):
        return run_cli(["build", "--spec", str(self.spec), "--bodies-dir", str(self.bodies), "--out", str(self.out),
                        "--config", str(self.config), *extra])


def estimated_plan(root):
    """A plan whose write-back changes bytes: numeric `{O}` and `{W}` bodies, and its context file on disk."""
    plan = Plan(root)
    context = plan.root / "src" / "orchard" / "ledger.py"  # the config folder is the project root
    context.parent.mkdir(parents=True)
    context.write_bytes(b"x = 1\n" * 900)
    return plan


def task_files_changed(plan):
    """The built task files whose bytes differ from what the write put down, and the count of task files."""
    _core, skeleton, _index = pb.render_core(str(plan.spec), TEMPLATES)
    written, _left = pb.apply_bodies(skeleton, pb.load_bodies(plan.bodies, "QZX")[0], TEMPLATES)
    tasks = [rel for rel in written if sp.file_kind(rel) == "task"]
    return [rel for rel in tasks if (plan.out / rel).read_bytes() != written[rel].encode("utf-8")], len(tasks)


def gates(report):
    """{gate name: (status, files, rest)} and the gate names in print order."""
    found = GATE_RE.findall(report)
    return {n: (s, int(f), rest) for n, s, f, rest in found}, [n for n, *_ in found]


def detail_lines(report, name):
    """The indented lines that follow the line of gate `name`."""
    lines, grabbed, on = report.split("\n"), [], False
    for ln in lines:
        if ln.startswith("gate="):
            on = ln.startswith(f"gate={name} ")
        elif on and ln.startswith("  "):
            grabbed.append(ln.strip())
        else:
            on = False
    return grabbed


@pytest.fixture(scope="module")
def big(tmp_path_factory):
    """Build the 35-task fixture once. Return (plan, exit code, report, expected file count)."""
    plan = Plan(tmp_path_factory.mktemp("big"), big_spec())
    count = len(pb.render_core(str(plan.spec), TEMPLATES)[1])
    code, report = plan.run("--skip-index")
    return plan, code, report, count


# ---- the five gates in order, on the 1/9/35 fixture

def test_chain_fixture_has_the_measured_shape():
    sessions = big_spec()["sprints"][0]["sessions"]
    assert (len(big_spec()["sprints"]), len(sessions), sum(len(s["tasks"]) for s in sessions)) == (1, 9, 35)


def test_chain_clean_build_exits_0_and_prints_the_five_gates_in_order(big):
    _plan, code, report, count = big
    assert code == 0, report
    table, order = gates(report)
    assert order == GATE_NAMES
    assert count > 35
    assert {files for _s, files, _r in table.values()} == {count}
    assert [table[n][0] for n in GATE_NAMES] == ["ok", "ok", "ok", "ok", "skipped"]
    assert report.rstrip().endswith("fill_remaining=0\nexit=0")


def test_chain_report_is_under_30000_characters(big):
    _plan, _code, report, _count = big
    assert len(report) < REPORT_CAP, len(report)
    # measured 2026-11-06 on this clean 1/9/35 build: about 400 characters, plus the length of the tmp path in the first line
    assert len(report) < 2_000, len(report)


def test_chain_estimates_runs_once_per_session(big):
    _plan, _code, report, _count = big
    assert "sessions=9 tasks=35 failed=0" in gates(report)[0]["estimates"][2]


def test_chain_second_build_with_no_edit_exits_0(tmp_path):
    plan = estimated_plan(tmp_path / "twice")
    first, _ = plan.run("--skip-index")
    changed, tasks = task_files_changed(plan)
    assert len(changed) == tasks > 0  # the estimates gate rewrote every task file after the write
    second, out = plan.run("--skip-index")
    assert (first, second) == (0, 0), out
    assert "CHANGED:" not in out


def test_chain_manifest_covers_the_files_the_estimates_gate_rewrote(tmp_path):
    plan = estimated_plan(tmp_path / "man")
    assert plan.run("--skip-index")[0] == 0
    changed, tasks = task_files_changed(plan)
    assert len(changed) == tasks > 0  # the estimates gate rewrote every task file after the write
    listed = pb.read_manifest(plan.manifest)
    assert listed and all(pb.file_hash(plan.out / rel) == digest for rel, digest in listed.items())


# ---- one known-bad fixture per gate

def test_chain_headings_finding_on_a_stray_h2(tmp_path):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["objective"] = "Read the ledger\n\n## Stray Heading"
    code, report = Plan(tmp_path / "h", spec).run("--skip-index")
    table, _order = gates(report)
    assert table["headings"][0] == "finding", report
    assert any("Stray Heading" in ln for ln in detail_lines(report, "headings"))
    assert code == 1


def test_chain_deviations_finding_on_a_class_b_case(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    spec = make_spec()
    spec_path = root / "pre.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    index = pb.render_core(str(spec_path), TEMPLATES)[2]
    heading = next(h for h in index["S01-01-ORCH"]["headings"] if h.startswith(CHECKLIST))
    bodies = bodies_set(index, skip=under(index, "S01-01-ORCH", heading))
    name = "QZX-bodies-S01-01.md"
    bodies[name] = bodies[name].replace("<!-- doc: S01-01-ORCH -->\n",
                                        f"<!-- doc: S01-01-ORCH -->\n\n<!-- section: {heading} -->\n\nProse only.\n", 1)
    code, report = Plan(root / "plan", spec, bodies).run("--skip-index")
    table, _order = gates(report)
    assert table["deviations"][0] == "finding", report
    assert "B=" in table["deviations"][2] and "B=0" not in table["deviations"][2]
    assert code == 1


def test_chain_deviations_finding_on_a_class_c_case(tmp_path):
    code, report = Plan(tmp_path / "c", scaffold=False).run("--skip-index")
    table, _order = gates(report)
    assert table["deviations"][0] == "finding", report
    assert "C=1" in table["deviations"][2]
    assert any("CLASS_C" in ln for ln in detail_lines(report, "deviations"))
    assert code == 1


def test_chain_scan_finding_on_a_warn_level_required_context_file(tmp_path):
    root = tmp_path / "s"
    (root / "src").mkdir(parents=True)
    (root / "src" / "big.py").write_bytes(b"x = 1\n" * 18_500)  # about 110 KB
    spec = make_spec()
    for task in spec["sprints"][0]["sessions"][0]["tasks"]:
        task["required_context"] = [{"priority": 1, "path": "src/big.py", "kib": 108.0, "tokens_k": 30.0,
                                     "purpose": "the big module"}]
    plan = Plan(root, spec, config="plans: plans\ncontext:\n  token_saver: true\n")  # the config folder is the project root
    code, report = plan.run("--skip-index")
    table, _order = gates(report)
    assert table["scan"][0] == "finding", report
    assert "exit=1" in table["scan"][2]
    assert code == 1


def test_chain_estimates_finding_on_a_write_estimates_failure(tmp_path, monkeypatch):
    real = tss.main

    def failing(argv=None):
        if argv and "--write-estimates" in argv:
            print("Write-back estimates\n\nERROR: a.md: cannot write\n\nFiles written: 0")  # the real writer prints to stdout
            return 3
        return real(argv)

    monkeypatch.setattr(tss, "main", failing)
    plan = Plan(tmp_path / "e")
    code, report = plan.run("--skip-index")
    table, _order = gates(report)
    assert table["estimates"][0] == "finding", report
    assert "failed=2" in table["estimates"][2]
    details = detail_lines(report, "estimates")
    assert len(details) == 2
    assert all(ln.startswith("session=S01-0") and "exit=3" in ln and "ERROR: a.md: cannot write" in ln for ln in details)
    assert code == 1
    assert list(plan.out.rglob("QZX-S01-01-01-*.md"))  # the write completed


def test_chain_estimates_finding_on_a_non_numeric_output_body(tmp_path):
    plan = Plan(tmp_path / "soon")
    bodies = plan.bodies / "QZX-bodies-S01-01.md"
    text = bodies.read_bytes().decode("utf-8")
    assert "<!-- fill: O -->\n\n4\n" in text
    bodies.write_bytes(text.replace("<!-- fill: O -->\n\n4\n", "<!-- fill: O -->\n\nsoon\n", 1).encode("utf-8"))
    code, report = plan.run("--skip-index")
    table, order = gates(report)
    assert order == GATE_NAMES
    assert table["estimates"][0] == "finding", report
    assert "failed=1" in table["estimates"][2]
    details = detail_lines(report, "estimates")
    assert len(details) == 1
    assert details[0].startswith("session=S01-01 exit=0: ") and "Context subtotal" in details[0]
    assert code == 1


def test_chain_findings_never_stop_the_write_or_the_later_gates(tmp_path):
    code, report = Plan(tmp_path / "all", scaffold=False).run("--skip-index")
    assert code == 1
    assert gates(report)[1] == GATE_NAMES
    assert list(Path(tmp_path / "all" / "Exec-QZX").rglob("*.md"))


def test_chain_detail_lines_are_capped_at_20_with_a_more_line(tmp_path):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["objective"] = "Read\n\n" + "\n\n".join(f"## Stray {k}" for k in range(25))
    _code, report = Plan(tmp_path / "cap", spec).run("--skip-index")
    lines = detail_lines(report, "headings")
    assert len(lines) == 21 and lines[-1].startswith("+") and lines[-1].endswith("more"), lines


# ---- the index step

def index_plan(root, **kw):
    """A project under `root`, with the plan built into the default `Plans` folder next to its config."""
    plans = root / "Plans" / "OrchardLedger"
    plans.mkdir(parents=True)
    return Plan(root, out=plans / "Exec-QZX", config="project_name: Chain\n", **kw)


def test_chain_index_step_runs_as_a_subprocess_and_writes_the_index(tmp_path):
    plan = index_plan(tmp_path / "ix")
    code, report = plan.run()
    table, order = gates(report)
    assert order == GATE_NAMES
    assert table["index"][0] in ("ok", "finding"), report
    assert table["index"][0] != "skipped"
    assert "exit=" in table["index"][2]
    index = (plan.root / "Plans" / "00-Index-Plans.md").read_text(encoding="utf-8")
    assert "Generated from each plan's Master Plan" in index and "QZX" in index
    assert code == 0, report


def test_chain_index_step_failing_prints_a_finding_and_exit_1(tmp_path):
    plan = index_plan(tmp_path / "bad")
    hand = plan.root / "Plans" / "00-Index-Plans.md"
    hand.write_text("# Plans\n\nA hand-written index with no generated table.\n", encoding="utf-8")
    before = hand.read_bytes()
    code, report = plan.run()
    table, _order = gates(report)
    assert table["index"][0] == "finding", report
    assert code == 1
    assert hand.read_bytes() == before  # the refusal wrote nothing


def test_chain_a_gate_that_raises_is_a_finding_and_later_gates_still_run(tmp_path):
    plan = Plan(tmp_path / "boom", config="plans_dir: [unterminated\n")
    code, report = plan.run("--skip-index")
    table, order = gates(report)
    assert order == GATE_NAMES
    assert table["scan"][0] == "finding" and table["estimates"][0] == "finding", report
    assert code == 1
