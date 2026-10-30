"""Tests for scripts/scaffold_plan.py: one known-good and one known-bad case per gate."""

import copy
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import scaffold_plan as sp

TEMPLATES = sp.DEFAULT_TEMPLATES


def _task(number, name, agent, deps, outputs, rc_path="src/orchard/ledger.py"):
    return {
        "number": number, "name": name, "title": f"{name} work", "agent": agent, "estimate_k": 20 + number,
        "depends_on": deps, "outputs": outputs,
        "required_context": [{"priority": 1, "path": rc_path, "kib": 4.0, "tokens_k": 1.5, "purpose": "the module"}],
    }


def make_spec():
    """Invented sample vocabulary: one sprint, two sessions, two tasks each."""
    return {
        "plan_name": "OrchardLedger", "abbrev": "QZX", "created": "2030-01-15",
        "ordering": "Sprint one only", "resolves": "none",
        "dependencies": [{"dependency": "Ledger schema", "required_for": "first session", "status": "Resolved"}],
        "decisions": [{"id": "D1", "decision": "Keep the ledger flat", "rationale": "One writer"}],
        "sprints": [{
            "number": 1, "name": "LedgerCore", "purpose": "Build the ledger core",
            "sessions": [
                {"number": 1, "name": "ReadPath", "objective": "Read the ledger", "mode": "DELEGATED",
                 "prerequisite": "None (first session)",
                 "tasks": [_task(1, "ParseRows", "Sonnet", [], ["src/orchard/parse.py", "Outputs/QZX-parse.md"]),
                           _task(2, "IndexRows", "Opus", [1], ["src/orchard/index.py"])]},
                {"number": 2, "name": "WritePath", "objective": "Write the ledger", "mode": "DIRECT",
                 "prerequisite": "The read path session",
                 "tasks": [_task(1, "WriteRows", "Sonnet", [], ["src/orchard/write.py"]),
                           _task(2, "VerifyRows", "Sonnet", [1], ["Outputs/QZX-verify.md"])]},
            ],
        }],
    }


@pytest.fixture(scope="module")
def rendered():
    files, _rec = sp.render_all(make_spec(), TEMPLATES)
    return files


def _write(tmp_path, files, name="plan"):
    out = tmp_path / name
    sp.write_tree(files, out)
    return out


def _walk(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ---- FILL invariant

def test_fill_invariant_clean_render(rendered):
    for rel, text in rendered.items():
        if rel.endswith(".md"):
            assert sp.unmasked_braces(text) == [], rel


def test_fill_invariant_fires_on_known_bad_line():
    assert sp.unmasked_braces("plain {leaked} text\n") == ["leaked"]
    assert sp.unmasked_braces("ok <!-- FILL: {fine} --> text\n") == []


# ---- lint-spec

def test_lint_good_spec_is_clean():
    assert sp.lint_spec(make_spec(), TEMPLATES) == []


def test_lint_quotes_a_prose_required_context_row():
    spec = make_spec()
    prose = "the ledger parser and its helpers"
    spec["sprints"][0]["sessions"][0]["tasks"][0]["required_context"][0]["path"] = prose
    errors = sp.lint_spec(spec, TEMPLATES)
    assert len(errors) == 1
    assert "prose, not a path" in errors[0]
    assert json.dumps(spec["sprints"][0]["sessions"][0]["tasks"][0]["required_context"][0]) in errors[0]


def test_lint_rejects_missing_field_bad_agent_and_heading_keys():
    spec = make_spec()
    tasks = spec["sprints"][0]["sessions"][1]["tasks"]
    del tasks[0]["title"]
    tasks[1]["agent"] = "Mini"
    spec["extra_sections"] = ["Ledger Notes"]
    spec["optional_sections"] = ["Risk Mitigation"]
    errors = "\n".join(sp.lint_spec(spec, TEMPLATES))
    assert "missing required key 'title'" in errors
    assert "'agent' must be Opus, Sonnet or Haiku" in errors
    assert "unknown key 'extra_sections'" in errors
    assert '"Risk Mitigation" is not an OPTIONAL section' in errors


def test_cli_lint_exit_codes(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(make_spec()), encoding="utf-8")
    bad_spec = make_spec()
    bad_spec["sprints"][0]["sessions"][0]["tasks"][1]["required_context"][0]["path"] = "Grep output of the ledger"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(bad_spec), encoding="utf-8")
    assert sp.main(["lint-spec", "--spec", str(good)]) == 0
    assert sp.main(["lint-spec", "--spec", str(bad)]) == 1


# ---- typed Required Context rows

SPAN_ROW = {"kind": "span", "priority": 2, "path": "docs/orchard-guide.md", "span": "lines 10-40",
            "kib": 2.0, "tokens_k": 0.8, "purpose": "the ledger rules"}
COMMAND_ROW = {"kind": "command", "priority": 3, "command": "Grep 'ledger' over src/orchard", "lines": 12,
               "bytes": "~900", "kib": 0.9, "tokens_k": 0.4, "purpose": "call sites"}
TASK_REL = "Sprint-01-LedgerCore/Session-01-ReadPath/QZX-S01-01-01-Sonnet-ParseRows.md"


def _spec_with_rows(*rows):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["tasks"][0]["required_context"].extend(copy.deepcopy(list(rows)))
    return spec


@pytest.mark.parametrize("row", [SPAN_ROW, COMMAND_ROW], ids=["span", "command"])
def test_typed_row_passes_lint_and_renders_in_template_form(row):
    spec = _spec_with_rows(row)
    assert sp.lint_spec(spec, TEMPLATES) == []
    files, _ = sp.render_all(spec, TEMPLATES)
    task = files[TASK_REL]
    assert sp.unmasked_braces(task) == []
    line = next(ln for ln in task.split("\n") if ln.startswith(f"| {row['priority']} |"))
    if row["kind"] == "span":
        assert "`docs/orchard-guide.md` lines 10-40" in line
        assert "— span row" in line
    else:
        assert "`Grep 'ledger' over src/orchard` — 12 lines / ~900 bytes returned" in line
        assert "— command-corpus row" in line


@pytest.mark.parametrize("row,field", [(SPAN_ROW, "span"), (COMMAND_ROW, "bytes")], ids=["span", "command"])
def test_typed_row_missing_a_field_fails_lint_quoted(row, field):
    bad = {k: v for k, v in row.items() if k != field}
    errors = sp.lint_spec(_spec_with_rows(bad), TEMPLATES)
    assert len(errors) == 1
    assert f"missing {field}" in errors[0]
    assert json.dumps(bad) in errors[0]


def test_typed_rows_get_a_resolution_record_and_its_removal_is_detected():
    spec = _spec_with_rows(SPAN_ROW, COMMAND_ROW)
    task = spec["sprints"][0]["sessions"][0]["tasks"][0]
    text = sp.render_all(spec, TEMPLATES)[0][TASK_REL]
    records = [ln for ln in text.split("\n") if not ln.startswith("|") and "2030-01-15: `" in ln]
    assert len(records) == 2, records
    assert any("`docs/orchard-guide.md` lines 10-40" in ln for ln in records)
    assert any("`Grep 'ledger' over src/orchard`" in ln and "12" in ln and "~900" in ln for ln in records)
    assert sp.unmasked_braces(text) == []
    assert sp.resolution_gaps(text, task) == []
    stripped = "\n".join(ln for ln in text.split("\n") if ln not in records)
    assert len(sp.resolution_gaps(stripped, task)) == 2


def test_unknown_row_kind_fails_lint():
    errors = sp.lint_spec(_spec_with_rows(dict(SPAN_ROW, kind="glob")), TEMPLATES)
    assert len(errors) == 1 and "kind must be path, span or command" in errors[0]


# ---- check-headings

def test_check_headings_fresh_render_has_no_stray(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    results = sp.check_headings([out], TEMPLATES)
    assert len([r for r in results if r["kind"]]) == 10
    assert [r for r in results if r["stray"]] == []
    assert sp.main(["check-headings", str(out)]) == 0


def test_check_headings_flags_a_hand_added_h2(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    target = out / "QZX-Master-Plan.md"
    target.write_bytes(target.read_bytes().replace(b"## Dependencies", b"## Ledger Notes\n\nx\n\n## Dependencies"))
    results = sp.check_headings([target], TEMPLATES)
    assert results[0]["stray"] == ["## Ledger Notes"]
    assert sp.main(["check-headings", str(out)]) == 1


def test_check_headings_plan_specific_h3_accepted_and_later_h2_stray(tmp_path):
    spec = make_spec()
    spec["optional_sections"] = ["Plan-Specific Sections"]
    files, _rec = sp.render_all(spec, TEMPLATES)
    text = files["QZX-Master-Plan.md"]
    assert "\n## Plan-Specific Sections" in text
    ok = text + "\n### Ledger Notes\n\nkept\n"
    assert sp.check_text(ok, *sp.template_heading_sets(TEMPLATES)["master"])[1] == []
    bad = ok + "\n## References\n"
    assert sp.check_text(bad, *sp.template_heading_sets(TEMPLATES)["master"])[1] == ["## References"]


def test_check_headings_ignores_h2_inside_a_fence():
    patterns, catch = sp.template_heading_sets(TEMPLATES)["task"]
    text = "## Objective\n\n```markdown\n## Not A Section\n```\n\n## Notes for Agent\n"
    assert sp.check_text(text, patterns, catch) == (2, [])


# ---- file set

def test_rendered_paths_equal_the_spec_derived_set(tmp_path, rendered):
    out = _write(tmp_path, rendered)
    expected = sorted(sp.plan_paths(make_spec()))
    assert _walk(out) == expected
    assert len(expected) == 12  # master + sprint + 2 sessions x (orchestration, recovery, 2 tasks, .gitkeep)
    task = next(out.rglob("QZX-S01-01-01-Sonnet-ParseRows.md"))
    task.rename(task.with_name("QZX-S01-01-01-Sonnet-ParseRowz.md"))
    assert _walk(out) != expected


# ---- line endings, post-fence sections, OPTIONAL sections

def test_crlf_template_input_gives_lf_output(tmp_path):
    lf_dir, crlf_dir = tmp_path / "lf", tmp_path / "crlf"
    lf_dir.mkdir()
    crlf_dir.mkdir()
    for name in sp.TEMPLATE_FILES.values():
        text = (TEMPLATES / name).read_bytes().replace(b"\r\n", b"\n")
        (lf_dir / name).write_bytes(text)
        (crlf_dir / name).write_bytes(text.replace(b"\n", b"\r\n"))
    lf_files, _ = sp.render_all(make_spec(), lf_dir)
    crlf_files, _ = sp.render_all(make_spec(), crlf_dir)
    assert crlf_files == lf_files
    assert all("\r" not in t for t in crlf_files.values())


def test_recovery_post_fence_sections_are_not_rendered(rendered):
    recovery = next(t for rel, t in rendered.items() if rel.endswith("-Recovery.md"))
    post_fence = [ln for ln in sp.read_lf(TEMPLATES / "recovery.md").split("\n")[
        max(i for i, ln in enumerate(sp.read_lf(TEMPLATES / "recovery.md").split("\n")) if ln.startswith("```")):]
        if ln.startswith("## ")]
    assert post_fence, "the recovery template carries no H2 after its closing fence"
    for heading in post_fence:
        assert heading not in recovery


def test_optional_section_omitted_unless_opted_in():
    spec = make_spec()
    plain, _ = sp.render_all(spec, TEMPLATES)
    assert "## Out of Scope" not in plain["QZX-Master-Plan.md"]
    opted = copy.deepcopy(spec)
    opted["optional_sections"] = ["Out of Scope"]
    files, _ = sp.render_all(opted, TEMPLATES)
    assert "## Out of Scope" in files["QZX-Master-Plan.md"]
    assert sp.unmasked_braces(files["QZX-Master-Plan.md"]) == []


def test_schema_pin_fence_parity_is_bounded(rendered):
    depth = 0
    for line in ("```", "**Schema Pin**", "```sql", "DDL", "```", "Live as of", "```"):
        depth = sp.fence_step(line, depth)
    assert depth == 0
    task = rendered["Sprint-01-LedgerCore/Session-01-ReadPath/QZX-S01-01-01-Sonnet-ParseRows.md"]
    assert "Live as of: {YYYY-MM-DD}" in task
    assert "> [!constraint] No `~?` Placeholders in Token Estimates" in task


# ---- refusal

def test_render_refuses_a_non_empty_out(tmp_path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(make_spec()), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.md").write_text("x", encoding="utf-8")
    assert sp.main(["render", "--spec", str(spec_path), "--out", str(out)]) == 2
    assert _walk(out) == ["keep.md"]
    fresh = tmp_path / "fresh"
    assert sp.main(["render", "--spec", str(spec_path), "--out", str(fresh)]) == 0
    assert _walk(fresh) == sorted(sp.plan_paths(make_spec()))
    shutil.rmtree(fresh)


# ---- review fixes: one known-good and one known-bad case per correctness finding

def _bare_env():
    return SimpleNamespace(tmpl="t", rec=sp.Rec(), vals={}, spec={}, item={})


def test_comments_stripped_on_plain_lines_only():
    body = ("## Notes\n\nplain <!-- gone one -->\n<!-- gone two -->\n> <!-- callout kept -->\n"
            "```text\n<!-- fence kept -->\n```\n")
    text = sp.render_doc(body, _bare_env(), [])
    assert "gone" not in text
    assert "> <!-- callout kept -->" in text
    assert "<!-- fence kept -->" in text


def test_task_file_keeps_the_callout_exemplar_comment(rendered):
    task = rendered[TASK_REL]
    assert "> <!-- netted to ~34K by the targeted-read discipline" in task
    assert "Delete rows 3 and 4 above" not in task  # a plain-line comment is still stripped


def _two_sprint_spec():
    spec = make_spec()
    second = copy.deepcopy(spec["sprints"][0])
    second.update(number=2, name="LedgerExtras")
    spec["sprints"].append(second)
    return spec


def _t0(spec):
    return spec["sprints"][0]["sessions"][0]["tasks"][0]


TYPE_CASES = {
    "outputs_empty": (lambda s: _t0(s).update(outputs=[]), "'outputs' must be a non-empty list"),
    "outputs_string": (lambda s: _t0(s).update(outputs="src/a.py"), "'outputs' must be a non-empty list"),
    "kib_string": (lambda s: _t0(s)["required_context"][0].update(kib="4"), "'kib' must be a number"),
    "tokens_k_string": (lambda s: _t0(s)["required_context"][0].update(tokens_k="1.5"),
                        "'tokens_k' must be a number"),
    "sprint_number_string": (lambda s: s["sprints"][0].update(number="1"), "'number' must be an integer"),
    "task_number_bool": (lambda s: _t0(s).update(number=True), "'number' must be an integer"),
    "depends_on_bool": (lambda s: s["sprints"][0]["sessions"][0]["tasks"][1].update(depends_on=[True]),
                        "'depends_on' must be a list of task numbers"),
    "pair_unhashable": (lambda s: s.update(parallel_pairs=[[[1], 1]]), "is not a pair of two different"),
    "pair_self": (lambda s: s.update(parallel_pairs=[[1, 1]]), "is not a pair of two different"),
}


def test_typed_fields_known_good_pair_and_types_lint_clean():
    spec = _two_sprint_spec()
    spec["parallel_pairs"] = [[1, 2]]
    assert sp.lint_spec(spec, TEMPLATES) == []
    files, _ = sp.render_all(spec, TEMPLATES)
    assert "| Sprint-01 ∥ Sprint-02 |" in files["QZX-Master-Plan.md"]


@pytest.mark.parametrize("case", sorted(TYPE_CASES))
def test_typed_field_errors_are_lint_lines_and_render_refuses(tmp_path, capsys, case):
    mutate, expected = TYPE_CASES[case]
    spec = make_spec()
    mutate(spec)
    errors = sp.lint_spec(spec, TEMPLATES)
    assert any(expected in e for e in errors), errors
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    assert sp.main(["render", "--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 2
    assert not (tmp_path / "out").exists()
    assert any(ln.startswith("LINT: ") and expected in ln for ln in capsys.readouterr().out.splitlines())


DUPLICATE_CASES = {
    "sprint": (lambda s: s["sprints"][1].update(number=1), "duplicate sprint number 1"),
    "session": (lambda s: s["sprints"][0]["sessions"][1].update(number=1), "duplicate session number 1"),
    "task": (lambda s: s["sprints"][0]["sessions"][0]["tasks"][1].update(number=1), "duplicate task number 1"),
}


@pytest.mark.parametrize("case", sorted(DUPLICATE_CASES))
def test_duplicate_numbers_fail_lint(case):
    mutate, expected = DUPLICATE_CASES[case]
    spec = _two_sprint_spec()
    assert sp.lint_spec(spec, TEMPLATES) == []
    mutate(spec)
    assert any(expected in e for e in sp.lint_spec(spec, TEMPLATES))


def test_render_all_refuses_to_overwrite_a_path_it_produced():
    spec = make_spec()
    assert len(sp.render_all(spec, TEMPLATES)[0]) == 12
    spec["sprints"][0]["sessions"][1].update(number=1, name="ReadPath")
    with pytest.raises(AssertionError, match="already produced"):
        sp.render_all(spec, TEMPLATES)


@pytest.mark.parametrize("path", ["Makefile", "Dockerfile", "src/orchard/", "src/output_writer.py",
                                  "docs/output-format.md"])
def test_one_word_paths_are_not_prose(path):
    spec = make_spec()
    _t0(spec)["required_context"][0]["path"] = path
    assert sp.lint_spec(spec, TEMPLATES) == []


@pytest.mark.parametrize("path", ["the ledger parser and its helpers", "Grep 'ledger' over src/orchard"])
def test_multi_word_prose_paths_still_fail_lint(path):
    spec = make_spec()
    _t0(spec)["required_context"][0]["path"] = path
    errors = sp.lint_spec(spec, TEMPLATES)
    assert len(errors) == 1 and "prose, not a path" in errors[0]


def test_template_h2_inside_a_closed_fence_does_not_desync():
    patterns, catch = sp.template_heading_sets(TEMPLATES)["task"]
    pasted = "## Objective\n\n```markdown\n## Objective\n```\n\n## Ledger Notes\n"
    assert sp.check_text(pasted, patterns, catch) == (2, ["## Ledger Notes"])


def test_template_h2_inside_a_stuck_fence_still_resyncs():
    patterns, catch = sp.template_heading_sets(TEMPLATES)["task"]
    stuck = "## Objective\n\n```\nnever closed\n\n## Notes for Agent\n"
    assert sp.check_text(stuck, patterns, catch) == (2, [])


OUTPUT_LINE = "**Output:** {path where deliverable should be saved, e.g., Outputs/{Abbrev}-{description}.md}"


def test_handler_rewrites_a_wrapped_field_line_whole(tmp_path, rendered):
    expected = "**Output:** `src/orchard/parse.py`, and `Outputs/QZX-parse.md`"
    assert expected in rendered[TASK_REL].split("\n")
    for name in sp.TEMPLATE_FILES.values():
        text = sp.read_lf(TEMPLATES / name)
        if name == "task-file.md":
            assert OUTPUT_LINE in text
            text = text.replace(OUTPUT_LINE, OUTPUT_LINE.replace("saved, e.g.", "saved,\ne.g."))
        (tmp_path / name).write_bytes(text.encode("utf-8"))
    task = sp.render_all(make_spec(), tmp_path)[0][TASK_REL]
    assert expected in task.split("\n")
    assert "e.g., Outputs/" not in task


def test_render_reports_a_residual_failure_in_one_line(tmp_path, capsys, monkeypatch):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(make_spec()), encoding="utf-8")

    def boom(*_args):
        raise ValueError("first\nsecond")

    monkeypatch.setattr(sp, "render_all", boom)
    assert sp.main(["render", "--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 2
    out = capsys.readouterr().out.splitlines()
    assert out == [("REFUSED: the render failed on a lint-clean spec (ValueError: first second). "
                    "Fix: correct the spec; lint-spec did not catch this case.")]
