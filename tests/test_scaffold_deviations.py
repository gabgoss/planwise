"""Tests for scripts/scaffold_deviations.py: a known-good tree and one known-bad case per class."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import scaffold_plan as sp

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
# DEV_SCRIPT lets a mutation control aim these tests at a scratch copy of the script.
SCRIPT = Path(os.environ.get("DEV_SCRIPT", SCRIPTS / "scaffold_deviations.py"))
PLAN = SCRIPTS / "scaffold_plan.py"
TEMPLATES = sp.DEFAULT_TEMPLATES
TOTAL_RE = re.compile(r"^deviations: A=(\d+) B=(\d+) C=(\d+)$")


def make_spec():
    """Invented sample vocabulary: one sprint, one delegated session, two tasks."""
    task = {
        "name": "ParseRows", "title": "Parse rows", "agent": "Sonnet", "estimate_k": 20, "number": 1,
        "depends_on": [], "outputs": ["src/orchard/parse.py"],
        "required_context": [{"priority": 1, "path": "src/orchard/ledger.py", "kib": 4.0,
                              "tokens_k": 1.5, "purpose": "the module"}],
    }
    second = dict(task, number=2, name="IndexRows", depends_on=[1], outputs=["src/orchard/index.py"])
    return {
        "plan_name": "OrchardLedger", "abbrev": "QZX", "created": "2030-01-15",
        "ordering": "Sprint one only", "resolves": "none",
        "sprints": [{"number": 1, "name": "LedgerCore", "purpose": "Build the ledger core",
                     "sessions": [{"number": 1, "name": "ReadPath", "objective": "Read the ledger",
                                   "mode": "DELEGATED", "prerequisite": "None (first session)",
                                   "tasks": [task, second]}]}],
    }


def run(*args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True, env=env, check=False)


def check(path):
    proc = run("check", str(path), "--templates", str(TEMPLATES))
    lines = proc.stdout.splitlines()
    return proc.returncode, lines


def totals(lines):
    m = TOTAL_RE.match(lines[-1])
    assert m, lines
    return tuple(int(x) for x in m.groups())


@pytest.fixture(scope="module")
def good_root():
    """A rendered plan under Exec-QZX with its Scaffold-QZX sibling, outside the repo."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "good"
        spec = Path(tmp) / "spec.json"
        spec.write_text(json.dumps(make_spec()), encoding="utf-8")
        exec_dir = base / "Exec-QZX"
        proc = subprocess.run([sys.executable, "-B", str(PLAN), "render", "--spec", str(spec),
                               "--out", str(exec_dir)], capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        (base / "Scaffold-QZX").mkdir()
        yield exec_dir


@pytest.fixture
def bad_copy(good_root):
    """A fresh copy of the good tree per test, so one mutation never leaks into another."""
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "copy"
        shutil.copytree(good_root.parent, dest)
        yield dest / "Exec-QZX"


def one(root, pattern):
    hits = sorted(root.rglob(pattern))
    assert len(hits) == 1, hits
    return hits[0]


def edit(path, old, new):
    text = path.read_bytes().decode("utf-8")
    assert old in text, (path, old)
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))


def test_known_good_tree_is_clean(good_root):
    code, lines = check(good_root)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_renamed_heading_is_class_a(bad_copy):
    edit(one(bad_copy, "*-Orchestration.md"), "## Session Objective", "## Session Goal")
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines) == (1, 0, 0)
    assert lines[0].startswith("CLASS_A ") and lines[0].endswith('missing "## Session Objective"')
    assert "\\" not in lines[0]


def test_deleted_total_estimated_is_class_b(bad_copy):
    path = one(bad_copy, "*-Orchestration.md")
    text = path.read_bytes().decode("utf-8")
    kept = [ln for ln in text.split("\n") if not ln.startswith("**Total Estimated:**")]
    assert len(kept) < len(text.split("\n"))
    path.write_bytes("\n".join(kept).encode("utf-8"))
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines) == (0, 1, 0)
    assert lines[0].startswith("CLASS_B ") and lines[0].endswith('missing "**Total Estimated:**"')


def test_missing_scaffold_sibling_is_class_c(bad_copy):
    (bad_copy.parent / "Scaffold-QZX").rmdir()
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines) == (0, 0, 1)
    assert lines[0].startswith("CLASS_C ") and lines[0].endswith("missing Scaffold-QZX/")


def test_nonexistent_path_exits_2(tmp_path):
    code, lines = check(tmp_path / "Exec-NOPE")
    assert code == 2
    assert lines and lines[0].startswith("ERROR")


def test_scaffolding_master_plan_is_not_graded_for_class_a(bad_copy):
    master = one(bad_copy, "*-Master-Plan.md")
    body = sp.extract_body(TEMPLATES / "scaffolding-master-plan.md")
    master.write_bytes(body.encode("utf-8"))
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_non_exec_folder_does_not_grade_class_c(good_root):
    # The same tree under a folder with no Exec- prefix and no sibling: C is not graded.
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "StandardPlan"
        shutil.copytree(good_root, dest)
        code, lines = check(dest)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_skips_outputs_folder(bad_copy):
    out = one(bad_copy, "Outputs")
    (out / "QZX-S01-01-Orchestration.md").write_text("# stray\n", encoding="utf-8")
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def drop_lines(path, prefix):
    text = path.read_bytes().decode("utf-8")
    kept = [ln for ln in text.split("\n") if not ln.startswith(prefix)]
    assert len(kept) < len(text.split("\n")), (path, prefix)
    path.write_bytes("\n".join(kept).encode("utf-8"))


def test_deleted_mode_is_class_b(bad_copy):
    drop_lines(one(bad_copy, "*-Orchestration.md"), "**Mode:**")
    code, lines = check(bad_copy)
    assert code == 1
    _a, b, c = totals(lines)
    assert b >= 1 and c == 0
    assert any(ln.startswith("CLASS_B ") and ln.endswith('missing "**Mode:**"') for ln in lines)


def test_deleted_total_sessions_is_class_b(bad_copy):
    drop_lines(one(bad_copy, "*-Master-Plan.md"), "**Total Sessions:**")
    code, lines = check(bad_copy)
    assert code == 1
    _a, b, c = totals(lines)
    assert b >= 1 and c == 0
    assert any(ln.startswith("CLASS_B ") and ln.endswith('missing "**Total Sessions:**"') for ln in lines)


def test_conditional_marker_headings_are_not_graded(bad_copy):
    # The rendered fixture is DELEGATED. Derive a DIRECT Orchestration: switch the mode and
    # drop every H2 the template marks `REQUIRED for DELEGATED mode`, so the exclusion is exercised.
    path = one(bad_copy, "*-Orchestration.md")
    edit(path, "**Mode:** DELEGATED", "**Mode:** DIRECT")
    text = path.read_bytes().decode("utf-8")
    dropped = ("## Dispatch Layers", "## Spawn-Prompt Skeleton", "## Orchestrator Post-Dispatch Checklist")
    kept = [ln for ln in text.split("\n") if not ln.startswith(dropped)]
    assert len(kept) < len(text.split("\n")) and "## Dispatch Layers" not in "\n".join(kept)
    path.write_bytes("\n".join(kept).encode("utf-8"))
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


@pytest.mark.parametrize("heading", ["## Dispatch Layers", "## Spawn-Prompt Skeleton",
                                     "## Orchestrator Post-Dispatch Checklist"])
def test_delegated_orchestration_missing_delegated_heading_is_class_a(bad_copy, heading):
    # The rendered fixture is DELEGATED. Drop one `REQUIRED for DELEGATED mode` H2 and keep the Mode line.
    path = one(bad_copy, "*-Orchestration.md")
    assert "**Mode:** DELEGATED" in path.read_bytes().decode("utf-8")
    drop_lines(path, heading)
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines) == (1, 0, 0)
    assert lines[0].startswith("CLASS_A ") and lines[0].endswith(f'missing "{heading}"')


def test_delegated_heading_inside_a_fence_is_missing(bad_copy):
    # A heading that appears only inside a code fence does not count as present.
    path = one(bad_copy, "*-Orchestration.md")
    drop_lines(path, "## Spawn-Prompt Skeleton")
    path.write_bytes(path.read_bytes() + b"\n```text\n## Spawn-Prompt Skeleton\n```\n")
    code, lines = check(bad_copy)
    assert code == 1
    assert any(ln.startswith("CLASS_A ") and ln.endswith('missing "## Spawn-Prompt Skeleton"') for ln in lines)


SKELETON_LINES = ["## HARD CONSTRAINTS (non-negotiable)", "## SCOPE BOUNDARY",
                  "## Operational Ceiling Notice", "## Status Block delivery (REQUIRED)"]


@pytest.mark.parametrize("line", SKELETON_LINES)
def test_delegated_skeleton_missing_body_line_is_class_b(bad_copy, line):
    # The line sits inside the skeleton fence of a DELEGATED Orchestration. The gate ignores task estimates.
    path = one(bad_copy, "*-Orchestration.md")
    assert "**Mode:** DELEGATED" in path.read_bytes().decode("utf-8")
    drop_lines(path, line)
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines) == (0, 1, 0)
    assert lines[0].startswith("CLASS_B ") and lines[0].endswith(f'missing "{line}"')


def test_direct_skeleton_body_lines_are_not_graded(bad_copy):
    path = one(bad_copy, "*-Orchestration.md")
    edit(path, "**Mode:** DELEGATED", "**Mode:** DIRECT")
    drop_lines(path, "## Operational Ceiling Notice")
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_skeleton_line_outside_the_fence_is_class_b(bad_copy):
    # A block moved out of the skeleton fence is no longer part of the prompt.
    path = one(bad_copy, "*-Orchestration.md")
    drop_lines(path, "## Operational Ceiling Notice")
    path.write_bytes(path.read_bytes() + b"\n## Operational Ceiling Notice\n")
    code, lines = check(bad_copy)
    assert code == 1
    assert any(ln.startswith("CLASS_B ") and ln.endswith('missing "## Operational Ceiling Notice"') for ln in lines)


def test_skeleton_heading_with_a_task_note_is_present(bad_copy):
    # A scaffolder may name the tasks a block applies to after the template's heading.
    path = one(bad_copy, "*-Orchestration.md")
    edit(path, "## Operational Ceiling Notice", "## Operational Ceiling Notice (tasks 01 and 02)")
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_four_backtick_skeleton_with_an_inner_block_is_read(bad_copy):
    # A skeleton that holds a ``` block is fenced with four backticks.
    path = one(bad_copy, "*-Orchestration.md")
    lines_in = path.read_bytes().decode("utf-8").split("\n")
    heading = next(i for i, ln in enumerate(lines_in) if ln.startswith("## Spawn-Prompt Skeleton"))
    opener = next(i for i in range(heading, len(lines_in)) if lines_in[i].startswith("```markdown"))
    closer = next(i for i in range(opener + 1, len(lines_in)) if lines_in[i].strip() == "```")
    lines_in[opener] = "````markdown"
    lines_in[closer] = "````"
    lines_in[opener + 1:opener + 1] = ["```bash", "git status", "```"]
    path.write_bytes("\n".join(lines_in).encode("utf-8"))
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_quoted_copy_of_the_section_does_not_hide_a_missing_line(bad_copy):
    path = one(bad_copy, "*-Orchestration.md")
    drop_lines(path, "## Operational Ceiling Notice")
    quoted = b"\n````text\n## Spawn-Prompt Skeleton\n```markdown\n## Operational Ceiling Notice\n```\n````\n"
    path.write_bytes(path.read_bytes() + quoted)
    code, lines = check(bad_copy)
    assert code == 1
    assert any(ln.startswith("CLASS_B ") and ln.endswith('missing "## Operational Ceiling Notice"') for ln in lines)


@pytest.mark.parametrize("old,new", [
    # a ``` block inside a three-backtick skeleton
    ("## SCOPE BOUNDARY", "```bash\ngit status\n```\n## SCOPE BOUNDARY"),
    # an example block in the section, ahead of the skeleton fence
    ("```markdown\nYou are dispatched", "```bash\n## not the skeleton\n```\n\n```markdown\nYou are dispatched"),
    # a trailing HTML comment on a skeleton line
    ("## SCOPE BOUNDARY", "## SCOPE BOUNDARY <!-- checked -->"),
])
def test_present_skeleton_lines_are_not_reported(bad_copy, old, new):
    path = one(bad_copy, "*-Orchestration.md")
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    edit(path, old, new)
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_quoted_skeleton_heading_adds_no_class_b(bad_copy):
    # With the real section gone, a copy quoted inside a fence is not graded: Class A alone reports it.
    path = one(bad_copy, "*-Orchestration.md")
    drop_lines(path, "## Spawn-Prompt Skeleton")
    path.write_bytes(path.read_bytes() + b"\n```text\n## Spawn-Prompt Skeleton\n```\n")
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines)[1] == 0, lines


def test_mode_line_only_inside_a_fence_does_not_grade_delegated_headings(bad_copy):
    # A DIRECT Orchestration that quotes a DELEGATED Mode line inside a fence stays ungraded for the DELEGATED H2s.
    path = one(bad_copy, "*-Orchestration.md")
    edit(path, "**Mode:** DELEGATED", "**Mode:** DIRECT")
    drop_lines(path, "## Spawn-Prompt Skeleton")
    path.write_bytes(path.read_bytes() + b"\n```text\n**Mode:** DELEGATED\n```\n")
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_unclosed_fence_does_not_hide_later_headings(bad_copy):
    path = one(bad_copy, "*-Orchestration.md")
    edit(path, "## Session Objective", "```text\n## Session Objective")
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_class_b_line_only_inside_a_fence_is_missing(bad_copy):
    path = one(bad_copy, "*-Orchestration.md")
    drop_lines(path, "**Total Estimated:**")
    path.write_bytes(path.read_bytes() + b"\n```text\n**Total Estimated:** ~1K tokens\n```\n")
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines)[1] >= 1
    assert any(ln.startswith("CLASS_B ") and ln.endswith('missing "**Total Estimated:**"') for ln in lines)


def test_reworded_checklist_item_is_class_b(bad_copy):
    # The Step 8b wording a handler once wrote in place of the template's lessons item.
    path = one(bad_copy, "*-Orchestration.md")
    text = path.read_bytes().decode("utf-8")
    old = next(ln for ln in text.split("\n") if ln.startswith("- [ ] **Capture lessons**"))
    edit(path, old, "- [ ] **Document lessons learned** — record any lessons from this session")
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines) == (0, 1, 0)
    assert lines[0].startswith("CLASS_B ") and lines[0].endswith('missing "- [ ] **Capture lessons**"')


def test_checked_checklist_item_is_present(bad_copy):
    path = one(bad_copy, "*-Orchestration.md")
    edit(path, "- [ ] **Capture lessons**", "- [x] **Capture lessons**")
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])


def test_undecodable_plan_file_names_the_file_not_the_template(bad_copy):
    path = one(bad_copy, "*-Orchestration.md")
    path.write_bytes(path.read_bytes() + b"\n\xff\xfe\n")
    code, lines = check(bad_copy)
    assert code == 2
    assert lines and lines[0].startswith("ERROR: cannot read plan file ")
    assert path.name in lines[0] and "template" not in lines[0]


# The last words of a Recovery file that was reported cut inside the Change Log note.
RECOVERY_CUT = "records its answer in the `"


def test_recovery_missing_last_heading_is_class_a(bad_copy):
    edit(one(bad_copy, "*-Recovery.md"), "## Task List Map", "Task List Map")
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines) == (1, 0, 0)
    assert lines[0].startswith("CLASS_A ") and lines[0].endswith('missing "## Task List Map"')


def test_truncated_recovery_is_class_a(bad_copy):
    path = one(bad_copy, "*-Recovery.md")
    text = path.read_bytes().decode("utf-8")
    assert RECOVERY_CUT in text
    path.write_bytes(text[:text.index(RECOVERY_CUT) + len(RECOVERY_CUT)].encode("utf-8"))
    code, lines = check(bad_copy)
    assert code == 1
    assert totals(lines) == (1, 0, 0)
    assert lines[0].endswith('missing "## Task List Map"')


def test_optional_recovery_section_is_not_required(bad_copy):
    path = one(bad_copy, "*-Recovery.md")
    path.write_bytes(path.read_bytes() + b"\n## User-Action Gate\n\n| Gate | Status | Date Asked | Answer |\n")
    code, lines = check(bad_copy)
    assert (code, lines) == (0, ["deviations: A=0 B=0 C=0"])
