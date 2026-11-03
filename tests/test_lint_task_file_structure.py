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


# --- content rules: used-helper, field-mapping, schema-pin ----------------------

DOC_TEMPLATE = """# Task: Sonnet-Doc

**Task ID:** AB-S01-01-01
**Output:** {output}

## Required Context

{context}

## Execution Steps

{steps}

{extra}
## Expected Output

- the report

{verification}## Notes for Agent

{notes}
"""

VERIFICATION_BLOCK = E11_INLINE.split("## Verification Commands")[1].split("## Success Criteria")[0]


def _doc(context="- `notes/input.md`", steps="1. Write the report.", extra="", notes="- none",
         code=True):
    """A task file. By default it is a code task: a .py output with its verification."""
    output = "`scripts/widget.py` (new)" if code else "`notes/report.md` (new)"
    verification = "## Verification Commands" + VERIFICATION_BLOCK if code else ""
    return DOC_TEMPLATE.format(context=context, steps=steps, extra=extra, notes=notes,
                               output=output, verification=verification)


def _by_rule(text: str, rule: str) -> list:
    return [f for f in lint.lint_text(text, TASK_NAME) if f.rule == rule]


COPY_CONTEXT = "| 1 | `scripts/retry_helpers.py` | copy the backoff helper from it |"
HELPER_HEADING = "### USED-Helper Enumeration\n\n- `backoff` - used\n"


def test_used_helper_known_bad_fires_one_warning():
    findings = _by_rule(_doc(context=COPY_CONTEXT), lint.RULE_USED_HELPER)
    assert len(findings) == 1
    assert findings[0].severity == lint.SEVERITY_WARNING
    assert "verify-before-cite.md §9.B.7" in findings[0].message


def test_used_helper_known_good_with_either_heading_level():
    for heading in (HELPER_HEADING, HELPER_HEADING.replace("###", "##")):
        text = _doc(context=COPY_CONTEXT, extra=heading)
        assert _by_rule(text, lint.RULE_USED_HELPER) == []


def test_used_helper_no_trigger_fires_nothing():
    plain = _doc(context="| 1 | `scripts/retry_helpers.py` | the module this task reads |")
    assert _by_rule(plain, lint.RULE_USED_HELPER) == []
    assert _by_rule(_doc(), lint.RULE_USED_HELPER) == []


def test_used_helper_heading_must_be_line_anchored():
    prose = _doc(context=COPY_CONTEXT, notes="- this task lacks a USED-Helper Enumeration")
    assert len(_by_rule(prose, lint.RULE_USED_HELPER)) == 1


MERGE_STEPS = "1. Write a MERGE statement for the widgets table."
MAPPING_HEADING = "### Field Mapping\n\n| Source | DDL |\n|---|---|\n"


def test_field_mapping_known_bad_fires_one_warning():
    findings = _by_rule(_doc(steps=MERGE_STEPS), lint.RULE_FIELD_MAPPING)
    assert len(findings) == 1
    assert findings[0].severity == lint.SEVERITY_WARNING
    assert "§9.B.8" in findings[0].message


def test_field_mapping_known_good_and_crlf():
    text = _doc(steps=MERGE_STEPS, extra=MAPPING_HEADING)
    assert _by_rule(text, lint.RULE_FIELD_MAPPING) == []
    assert _by_rule(text.replace("\n", "\r\n"), lint.RULE_FIELD_MAPPING) == []


def test_field_mapping_no_trigger_and_fence_and_case():
    assert _by_rule(_doc(steps="1. Write a SELECT statement."), lint.RULE_FIELD_MAPPING) == []
    fenced = _doc(steps="1. Run:\n\n```\nMERGE INTO widgets\n```")
    assert len(_by_rule(fenced, lint.RULE_FIELD_MAPPING)) == 1
    lower_fence = _doc(steps="1. Run:\n\n```\nmerge into widgets\n```")
    assert len(_by_rule(lower_fence, lint.RULE_FIELD_MAPPING)) == 1
    inline = _doc(steps="1. Run `ON CONFLICT DO NOTHING`.")
    assert len(_by_rule(inline, lint.RULE_FIELD_MAPPING)) == 1
    lower_prose = _doc(steps="1. Merge the lists, merge the rows and do an upsert.")
    assert _by_rule(lower_prose, lint.RULE_FIELD_MAPPING) == []
    mention = _doc(steps=MERGE_STEPS, notes="- no ### Field Mapping here")
    assert len(_by_rule(mention, lint.RULE_FIELD_MAPPING)) == 1


SQL_STEPS = "1. Run `INSERT INTO widgets (id) VALUES (1)`."
PIN_HEADING = "### Schema Pin\n\n```sql\nCREATE TABLE widgets (id int);\n```\n"
PRE_SQL = "- Pre-SQL Schema Verification: read the DDL first."


def test_schema_pin_both_absent_is_warning_naming_neither():
    findings = _by_rule(_doc(steps=SQL_STEPS), lint.RULE_SCHEMA_PIN)
    assert len(findings) == 1
    assert findings[0].severity == lint.SEVERITY_WARNING
    assert "§9.B.5" in findings[0].message
    assert "neither" in findings[0].message


def test_schema_pin_exactly_one_absent_is_warning():
    pin_only = _by_rule(_doc(steps=SQL_STEPS, extra=PIN_HEADING), lint.RULE_SCHEMA_PIN)
    block_only = _by_rule(_doc(steps=SQL_STEPS, notes=PRE_SQL), lint.RULE_SCHEMA_PIN)
    for findings in (pin_only, block_only):
        assert len(findings) == 1
        assert findings[0].severity == lint.SEVERITY_WARNING
        assert "one of the two is absent" in findings[0].message


def test_schema_pin_known_good_with_template_heading_and_bold_form():
    good = _doc(steps=SQL_STEPS, extra=PIN_HEADING, notes=PRE_SQL)
    assert _by_rule(good, lint.RULE_SCHEMA_PIN) == []
    bold = _doc(steps=SQL_STEPS, extra="**Schema Pin** - ddl.sql#widgets\n", notes=PRE_SQL)
    assert _by_rule(bold, lint.RULE_SCHEMA_PIN) == []


def test_schema_pin_lower_case_prose_never_triggers():
    prose = _doc(steps="1. Update the docs and insert a note. Merge the lists.")
    assert _by_rule(prose, lint.RULE_SCHEMA_PIN) == []
    assert _by_rule(_doc(), lint.RULE_SCHEMA_PIN) == []


def test_schema_pin_fenced_lower_case_statement_triggers():
    fenced = _doc(steps="1. Run:\n\n```\nalter table widgets add column x int;\n```")
    assert len(_by_rule(fenced, lint.RULE_SCHEMA_PIN)) == 1


def test_structure_subsections_inside_execution_steps_are_not_triggers():
    # DDL inside the Schema Pin subsection is the pin, not a step that emits SQL.
    text = _doc(steps="1. Read the table.\n\n" + PIN_HEADING.replace("```sql", "```"))
    assert _by_rule(text, lint.RULE_SCHEMA_PIN) == []
    steps = "1. Read.\n\n### Field Mapping (Required for MERGE tasks)\n\nMERGE rows map.\n"
    assert _by_rule(_doc(steps=steps), lint.RULE_FIELD_MAPPING) == []


def test_content_rules_honour_exemption():
    bad = _doc(steps=MERGE_STEPS)
    assert _by_rule(bad, lint.RULE_FIELD_MAPPING) != []
    exempt = bad + "<!-- VERIFICATION: not-applicable (doc-only) -->\n"
    assert lint.lint_text(exempt, TASK_NAME) == []


def test_documentation_task_is_outside_every_content_rule():
    steps = "1. Copy `scripts/retry_helpers.py` rows and merge the lists. Run MERGE INTO t."
    text = _doc(context=COPY_CONTEXT, steps=steps + "\n2. Run `INSERT INTO t`.", code=False)
    assert lint.lint_text(text, TASK_NAME) == []


def test_code_task_with_lower_case_prose_merge_has_no_field_mapping_finding():
    text = _doc(steps="1. Merge the two lists, then merge the results.")
    assert _by_rule(text, lint.RULE_FIELD_MAPPING) == []


def test_code_task_with_fenced_merge_and_no_mapping_has_one_finding():
    text = _doc(steps="1. Emit:\n\n```\nMERGE INTO widgets USING src ON (a = b)\n```")
    assert len(_by_rule(text, lint.RULE_FIELD_MAPPING)) == 1


# --- cross-repo fix-task rules (verify-cross-repo-fix-discipline.md §7) ---------

XR_TASK = """# Task: Sonnet-Fix

**Task ID:** AB-S01-01-01
**Output:** {output}

## Required Context

| Priority | File | Purpose |
|----------|------|---------|
{rows}

## Execution Steps

{steps}

## Expected Output

{expected}

## Success Criteria

{criteria}
"""

XR_TARGET = "vendor/upstream/lib/mod.md"
XR_YAML = "vendor/upstream/conf/app.yaml"
XR_GOOD_ROW = (f"| 1 | `{XR_TARGET}` | **BINDING SOURCE — full read required, do not work "
               "from audit excerpts** |")
XR_BAD_ROW = f"| 1 | `{XR_TARGET}` | the module this task edits |"
XR_GOOD_STEPS = (f"1. Read `{XR_TARGET}` in full before any fix reasoning. Do NOT begin from "
                 "audit excerpts.\n2. Edit the `## Usage` section.")
XR_BAD_STEPS = "1. Read the audit notes.\n2. Edit the `## Usage` section."


def _xr_text(output=f"`{XR_TARGET}`", rows=XR_GOOD_ROW, steps=XR_GOOD_STEPS,
             expected="- the fixed module", criteria="- [ ] The section is fixed"):
    return XR_TASK.format(output=output, rows=rows, steps=steps, expected=expected,
                          criteria=criteria)


def _xr_file(tmp_path: Path, text: str) -> Path:
    """A plan repository holding a nested repository at vendor/upstream, and the task."""
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / "vendor" / "upstream" / ".git").mkdir(parents=True)
    for rel in (XR_TARGET, XR_YAML, "docs/guide.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("# file\n", encoding="utf-8")
    task_dir = root / "plans" / "s1"
    task_dir.mkdir(parents=True)
    return _write(task_dir, text)


def _xr(tmp_path: Path, rule=None, **parts) -> list:
    path = _xr_file(tmp_path, _xr_text(**parts))
    findings = lint.lint_text(path.read_text(encoding="utf-8"), str(path))
    return [f for f in findings if rule is None or f.rule == rule]


def test_cross_repo_binding_known_bad_is_one_blocker(tmp_path):
    findings = _xr(tmp_path, rows=XR_BAD_ROW)
    assert [(f.rule, f.severity) for f in findings] == [
        (lint.RULE_CROSS_REPO_BINDING, lint.SEVERITY_BLOCKER)]
    assert "verify-cross-repo-fix-discipline.md §7.2" in findings[0].message


def test_cross_repo_known_good_has_no_finding(tmp_path):
    assert _xr(tmp_path) == []


def test_cross_repo_binding_row_must_be_priority_one(tmp_path):
    row = XR_GOOD_ROW.replace("| 1 |", "| 2 |", 1)
    assert len(_xr(tmp_path, lint.RULE_CROSS_REPO_BINDING, rows=row)) == 1


def test_cross_repo_exempt_audit_task_reads_only(tmp_path):
    # A §7.6 audit task: the cross-repo file is read, the output is an in-repo report.
    findings = _xr(tmp_path, output="`plans/s1/Outputs/report.md`", rows=XR_BAD_ROW,
                   steps=XR_BAD_STEPS)
    assert findings == []


def test_cross_repo_in_repo_target_is_not_cross_repo(tmp_path):
    findings = _xr(tmp_path, output="`docs/guide.md`", rows="| 1 | `docs/guide.md` | edit |",
                   steps=XR_BAD_STEPS)
    assert findings == []


def test_cross_repo_undecided_root_is_a_warning_naming_the_path():
    findings = lint.lint_text(_xr_text(rows=XR_BAD_ROW, steps=XR_BAD_STEPS), TASK_NAME)
    assert [(f.rule, f.severity) for f in findings] == [
        (lint.RULE_CROSS_REPO_BINDING, lint.SEVERITY_WARNING)]
    assert XR_TARGET in findings[0].message


def test_cross_repo_step1_known_bad_is_one_blocker(tmp_path):
    findings = _xr(tmp_path, steps=XR_BAD_STEPS)
    assert [(f.rule, f.severity) for f in findings] == [
        (lint.RULE_CROSS_REPO_STEP_ONE, lint.SEVERITY_BLOCKER)]
    assert "verify-cross-repo-fix-discipline.md §7.3:" in findings[0].message


def test_cross_repo_step1_accepts_bold_read(tmp_path):
    steps = XR_GOOD_STEPS.replace("1. Read", "1. **Read**", 1)
    assert _xr(tmp_path, steps=steps) == []


def test_cross_repo_parser_gate_known_bad_is_one_warning(tmp_path):
    output = f"`{XR_TARGET}`, `{XR_YAML}`"
    rows = XR_GOOD_ROW + f"\n| 1 | `{XR_YAML}` | **BINDING SOURCE — full read required** |"
    findings = _xr(tmp_path, output=output, rows=rows)
    assert [(f.rule, f.severity) for f in findings] == [
        (lint.RULE_CROSS_REPO_PARSER, lint.SEVERITY_WARNING)]
    assert "§7.3d" in findings[0].message
    good = "- [ ] `python -c \"import yaml; yaml.safe_load(open('app.yaml'))\"` exits 0"
    assert _xr(tmp_path / "g", output=output, rows=rows, criteria=good) == []


def test_cross_repo_parser_gate_ignores_expected_output_mention(tmp_path):
    expected = f"- the fix; re-read `{XR_YAML}` for the version"
    assert _xr(tmp_path, expected=expected) == []


def test_cross_repo_naked_line_ref_known_bad_is_one_warning(tmp_path):
    steps = XR_GOOD_STEPS + "\n3. Replace line 40 of the file."
    findings = _xr(tmp_path, steps=steps)
    assert [(f.rule, f.severity) for f in findings] == [
        (lint.RULE_CROSS_REPO_LINE_REF, lint.SEVERITY_WARNING)]
    assert "§7.3a" in findings[0].message


@pytest.mark.parametrize("step, expected", [
    ("3. Replace line 40, the `def load()` function.", 0),
    ('3. Replace line 40 under "## Usage".', 0),
    ("3. Keep the §6 citation (line 40 at audit time).", 0),
    (f"3. Replace `{XR_TARGET}` line 40.", 1),
    ("3. Insert the step at Step 4.4.", 1),
    ("3. Edit L40.", 1),
])
def test_cross_repo_naked_line_ref_content_anchor_precision(tmp_path, step, expected):
    findings = _xr(tmp_path, lint.RULE_CROSS_REPO_LINE_REF, steps=XR_GOOD_STEPS + "\n" + step)
    assert len(findings) == expected


def test_cross_repo_line_ref_in_step_one_is_not_checked(tmp_path):
    steps = XR_GOOD_STEPS.replace("Do NOT begin", "Line 40 is a hint. Do NOT begin", 1)
    assert _xr(tmp_path, steps=steps) == []


def test_cross_repo_rules_survive_the_verification_exemption(tmp_path):
    text = _xr_text(rows=XR_BAD_ROW) + "<!-- VERIFICATION: not-applicable (doc fix) -->\n"
    path = _xr_file(tmp_path, text)
    rules = [f.rule for f in lint.lint_text(text, str(path))]
    assert rules == [lint.RULE_CROSS_REPO_BINDING]


def test_cross_repo_cli_exits_1(tmp_path):
    path = _xr_file(tmp_path, _xr_text(rows=XR_BAD_ROW))
    assert lint.main([str(path.parent)]) == lint.EXIT_FINDING


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
