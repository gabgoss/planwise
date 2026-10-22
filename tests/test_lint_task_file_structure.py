"""Tests for scripts/lint_task_file_structure.py.

The positive fixtures are built from the live ``templates/task-file.md`` task
body, with its slots filled in, so a rule that the shipped template itself
cannot satisfy shows up here as a failing positive control rather than passing
on a fixture written from the script's own rules.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_task_file_structure as lint

SCRIPT = SCRIPTS / "lint_task_file_structure.py"
TEMPLATE = REPO_ROOT / "plugins" / "planwise" / "templates" / "task-file.md"
TASK_NAME = "AB-S01-01-01-Sonnet-Widget.md"

CODE_OUTPUT = "**Output:** `scripts/widget.py` (new), `tests/test_widget.py` (new)"
NOTEBOOK_OUTPUT = "**Output:** `notebooks/report.ipynb` (new)"
SQL_OUTPUT = "**Output:** `db/migrations/0002_add_widget.sql` (new)"

FILLED_SLOTS = {
    "{cmd_before_1}": "ruff check scripts/widget.py",
    "{cmd_before_2}": "wc -l scripts/widget.py",
    "{cmd_after_1}": "ruff check scripts/widget.py",
    "{cmd_after_2}": "pytest -q tests/test_widget.py",
    "{cmd_after_3}": "pytest -q tests/test_widget.py",
}


def _template_body() -> str:
    """Return the task-file body the template wraps in its ```markdown fence."""
    lines = TEMPLATE.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    start = lines.index("```markdown") + 1
    end = lines.index("## Naming Convention")
    while lines[end] != "```":
        end -= 1
    return "\n".join(lines[start:end]) + "\n"


def _with_output(output_line: str) -> str:
    """The template body with its ``**Output:**`` line replaced."""
    return re.sub(r"^\*\*Output:\*\*.*$", lambda _m: output_line, _template_body(),
                  count=1, flags=re.MULTILINE)


def _filled(output_line: str, extra_table_rows: str = "") -> str:
    """The template body with its Output line and Before/After slots filled."""
    body = _with_output(output_line)
    for slot, command in FILLED_SLOTS.items():
        body = body.replace(slot, command)
    if extra_table_rows:
        body = body.replace(
            "| `.{ext}` | `{cmd}` |", extra_table_rows + "\n| `.{ext}` | `{cmd}` |"
        )
    return body


FORMAT_ROW = "| `.py` (format) | `{format-cmd} {path}` |"


def _write(tmp_path: Path, text: str, name: str = TASK_NAME) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _rules(text: str) -> list:
    return [(f.rule, f.message.split(":")[0]) for f in lint.lint_text(text, TASK_NAME)]


E11_INLINE = """# Task: Sonnet-Widget

**Task ID:** AB-S01-01-01
**Output:** `scripts/widget.py` (new)

## Objective

Write the widget.

## Expected Output

- `scripts/widget.py`

## Verification Commands

> [!verify] Before / After Commands
> **Before (runner):**
> ```
> Glob  pattern='**/widget.py'  path='/abs/scripts'
> # pre-edit: No files found → expect 1 file after
> ```
> **After (runner):**
> ```
> python -m ruff check /abs/scripts/widget.py
> # pre-edit: n/a (new file) → expect All checks passed!
> ```

## Success Criteria

- [ ] The widget exists
"""


# --- the template itself ------------------------------------------------------

def test_template_body_with_no_code_output_is_clean():
    assert lint.lint_text(_template_body(), TASK_NAME) == []


# --- verification-section (Reviewer Checks 013, 014) --------------------------

def test_section_positive_template_filled_has_no_section_finding():
    rules = _rules(_filled(CODE_OUTPUT, FORMAT_ROW))
    assert [r for r in rules if r[0] == lint.RULE_SECTION] == []


def test_section_missing_heading_fires_check_013():
    text = E11_INLINE.split("## Verification Commands")[0] + "## Success Criteria\n\n- [ ] x\n"
    rules = _rules(text)
    assert (lint.RULE_SECTION, "Reviewer Check 013") in rules


def test_section_with_only_unfilled_slots_fires_check_014():
    body = _with_output(CODE_OUTPUT)
    # Strip the placeholder vocabulary so only the unfilled slots remain.
    body = re.sub(r"\{[a-z][a-z-]*-cmd\}", "tool", body)
    messages = [f.message for f in lint.lint_text(body, TASK_NAME) if f.rule == lint.RULE_SECTION]
    assert any("template slot left unfilled" in m for m in messages)
    assert any("no {...-cmd} placeholder row and no concrete command" in m for m in messages)


def test_e11_inline_commands_without_table_are_clean():
    assert lint.lint_text(E11_INLINE, TASK_NAME) == []


# --- per-type-commands (Reviewer Checks 034, 035, 036) -------------------------

def test_per_type_positive_code_notebook_and_db():
    assert _rules(_filled(CODE_OUTPUT, FORMAT_ROW)) == []
    notebook = _filled(NOTEBOOK_OUTPUT, "| `.ipynb` | `{exec-cmd} {path}` |")
    assert _rules(notebook) == []
    db = _filled(SQL_OUTPUT).replace(
        "wc -l scripts/widget.py", "{connectivity-check-cmd}"
    )
    assert _rules(db) == []


def test_per_type_template_table_without_format_row_fires_check_035():
    assert (lint.RULE_PER_TYPE, "Reviewer Check 035") in _rules(_filled(CODE_OUTPUT))


def test_per_type_inline_without_lint_fires_check_035():
    text = E11_INLINE.replace("python -m ruff check", "python -B")
    assert (lint.RULE_PER_TYPE, "Reviewer Check 035") in _rules(text)


def test_per_type_notebook_without_exec_fires_check_034():
    text = _filled(NOTEBOOK_OUTPUT).replace("{notebook-exec-cmd}", "tool")
    assert (lint.RULE_PER_TYPE, "Reviewer Check 034") in _rules(text)


def test_per_type_connectivity_only_in_after_fires_check_036():
    text = _filled(SQL_OUTPUT).replace(
        "pytest -q tests/test_widget.py", "{connectivity-check-cmd}", 1
    )
    findings = [f for f in lint.lint_text(text, TASK_NAME) if f.rule == lint.RULE_PER_TYPE]
    assert any("Reviewer Check 036" in f.message and "After block only" in f.message
               for f in findings)


# --- verify-callout (Reviewer Check 015) ---------------------------------------

def test_callout_positive_template_filled():
    rules = _rules(_filled(CODE_OUTPUT, FORMAT_ROW))
    assert [r for r in rules if r[0] == lint.RULE_CALLOUT] == []


def test_callout_absent_fires_check_015():
    text = E11_INLINE.replace("> [!verify] Before / After Commands\n", "")
    assert (lint.RULE_CALLOUT, "Reviewer Check 015") in _rules(text)


def test_callout_without_after_fires_check_015():
    text = E11_INLINE.replace("**After (runner):**", "Then:")
    assert (lint.RULE_CALLOUT, "Reviewer Check 015") in _rules(text)


# --- exemption ------------------------------------------------------------------

def test_exemption_comment_silences_the_file():
    bad = E11_INLINE.split("## Verification Commands")[0]
    exempt = bad + "<!-- VERIFICATION: not-applicable (doc-only rename) -->\n"
    assert lint.lint_text(bad, TASK_NAME) != []
    assert lint.lint_text(exempt, TASK_NAME) == []


def test_exemption_with_empty_reason_does_not_exempt():
    bad = E11_INLINE.split("## Verification Commands")[0]
    assert lint.lint_text(bad + "<!-- VERIFICATION: not-applicable () -->\n", TASK_NAME) != []


# --- exit codes -----------------------------------------------------------------

def test_main_exit_codes(tmp_path, capsys):
    clean = _write(tmp_path, E11_INLINE)
    assert lint.main([str(clean)]) == lint.EXIT_CLEAN
    bad = _write(tmp_path, E11_INLINE.replace("python -m ruff check", "python -B"),
                 "AB-S01-01-02-Sonnet-Bad.md")
    assert lint.main([str(bad)]) == lint.EXIT_FINDING
    out = capsys.readouterr().out
    assert re.search(r"AB-S01-01-02-Sonnet-Bad\.md:\d+: ERROR: ", out)


def test_main_exit_2_on_missing_path_and_on_no_task_file(tmp_path):
    assert lint.main([str(tmp_path / "absent")]) == lint.EXIT_USAGE
    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")
    assert lint.main([str(tmp_path)]) == lint.EXIT_USAGE


def test_directory_walk_keeps_only_task_files(tmp_path):
    _write(tmp_path, E11_INLINE)
    _write(tmp_path, E11_INLINE, "AB-S01-01-Orchestration.md")
    files, missing = lint.collect_task_files([str(tmp_path)])
    assert [p.name for p in files] == [TASK_NAME]
    assert missing == []


# --- the CLI as a subprocess ----------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        (E11_INLINE, 0),
        (E11_INLINE.replace("> [!verify] Before / After Commands\n", ""), 1),
    ],
)
def test_cli_subprocess(tmp_path, text, expected):
    path = _write(tmp_path, text)
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    if expected:
        assert path.as_posix() in result.stdout
        assert "Reviewer Check 015" in result.stdout


def test_cli_subprocess_usage_error(tmp_path):
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(tmp_path / "absent")],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 2
    assert "path not found" in result.stderr
