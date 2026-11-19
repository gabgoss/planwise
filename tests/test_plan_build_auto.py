"""Tests for the auto estimate keys of scripts/plan_build.py.

Shared helpers live in `tests/test_plan_build.py`.
"""

import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

import plan_build as pb
import scaffold_plan as sp
import token_saver_writeback as tsw
from test_plan_build import (
    FILLED_RE,
    META,
    TASK_DOC,
    TEMPLATES,
    Build,
    _write_bodies,
    _write_spec,
    add_keys,
    bodies_set,
    index_of,
    make_spec,
    meta_build,
    meta_spec,
    token_count,
    under,
)

# ---- auto estimates

DELTA_RE = re.compile(r"^delta task=(\S+) spec=(\S+) measured=(\S+)$", re.MULTILINE)
HEADER_FIGURE_RE = re.compile(r"^\*\*Estimated Tokens:\*\* ~(\d+)K$", re.MULTILINE)
READ_K = 1.5  # the tokens_k of the one Required Context row every fixture task holds


def fresh(tmp_path, name):
    folder = tmp_path / name
    folder.mkdir()
    return folder


def auto_spec(auto=(1, 2, 3, 4), spec=None):
    """The sample spec with `estimate_k: "auto"` and distinct output_k and working_k on the numbered tasks (1-4, in order)."""
    spec = spec or make_spec()
    tasks = [t for se in spec["sprints"][0]["sessions"] for t in se["tasks"]]
    for number in auto:
        tasks[number - 1].update(estimate_k="auto", output_k=number + 2, working_k=number * 3)
    return spec


def estimate_bodies(tmp_path, spec):
    """bodies_set for `spec`, minus the two markers its keys fill."""
    skip = {(doc, name) for doc, (_f, fills) in pb.task_figures(spec).items() for name in fills}
    return bodies_set(index_of(tmp_path, spec), skip=skip)


def applied(tmp_path, spec, bodies=None):
    """Render and apply in process, the way `build` does before it writes. Return ({rel: text}, markers left)."""
    folder = fresh(tmp_path, "applied")
    spec_path = _write_spec(folder, spec)
    core, skeleton, idx = pb.render_core(str(spec_path), TEMPLATES)
    bodies_dir = _write_bodies(folder, estimate_bodies(tmp_path, spec) if bodies is None else bodies)
    docs, errors, _figures = pb.load_all_bodies(str(spec_path), bodies_dir, core, idx)
    assert errors == []
    return pb.apply_bodies(skeleton, docs, TEMPLATES)


def task_texts(files):
    return {pb.doc_id(rel): text for rel, text in files.items() if sp.file_kind(rel) == "task"}


def test_auto_known_good_header_is_reads_plus_output_plus_working_and_no_marker_survives(tmp_path):
    files, left = applied(tmp_path, auto_spec())
    texts = task_texts(files)
    assert len(texts) == 4
    for number, (doc, text) in enumerate(texts.items(), start=1):
        header = int(HEADER_FIGURE_RE.search(text).group(1))
        assert header == round(READ_K + (number + 2) + number * 3), doc
        assert f"~{number + 2}K (output) + ~{number * 3}K (working)" in text
        assert "<!-- FILL: {O} -->" not in text and "<!-- FILL: {W} -->" not in text
        assert "~0K" not in text
    assert left == 0


def test_auto_known_bad_a_body_less_marker_stays_unfilled_and_fails_the_build(tmp_path, capsys):
    spec = make_spec()  # numeric estimates and no keys: the bodies path owns {O}
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, spec), skip={(TASK_DOC, "O")}), spec)
    code, out = build.run()
    assert code == 1, out
    assert build.task_file().read_text(encoding="utf-8").count("<!-- FILL: {O} -->") == 1
    assert FILLED_RE.search(out).group(1) == "1"


def test_auto_missing_output_k_exits_2_naming_the_task(tmp_path, capsys):
    spec = auto_spec(auto=(1,))
    del spec["sprints"][0]["sessions"][0]["tasks"][0]["output_k"]
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, make_spec())), spec)
    code, out = build.run()
    assert code == 2
    assert "LINT: task S01-01-01 (ParseRows)" in out and "output_k" in out
    assert not build.out.exists()


def test_auto_a_non_number_addend_exits_2_naming_the_task(tmp_path, capsys):
    spec = auto_spec(auto=(2,))
    spec["sprints"][0]["sessions"][0]["tasks"][1]["working_k"] = "6"
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, make_spec())), spec)
    code, out = build.run()
    assert code == 2
    assert "LINT: task S01-01-02 (IndexRows)" in out and "working_k" in out


def test_auto_mixed_fixture_leaves_a_numeric_estimate_alone(tmp_path):
    files, left = applied(tmp_path, auto_spec(auto=(1,)))
    figures = {doc: int(HEADER_FIGURE_RE.search(text).group(1)) for doc, text in task_texts(files).items()}
    assert figures == {"S01-01-01": round(READ_K + 3 + 3), "S01-01-02": 22, "S01-02-01": 21, "S01-02-02": 22}
    assert left == 0


def test_auto_missing_key_next_to_a_numeric_estimate_exits_2_naming_the_task(tmp_path, capsys):
    spec = make_spec()
    spec["sprints"][0]["sessions"][1]["tasks"][0]["output_k"] = 5
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, make_spec())), spec)
    code, out = build.run()
    assert code == 2
    assert "LINT: task S01-02-01 (WriteRows)" in out and "working_k" in out


def test_auto_numeric_task_with_both_keys_fills_the_markers_and_keeps_its_estimate(tmp_path):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["tasks"][0].update(output_k=4.5, working_k=7)
    files, left = applied(tmp_path, spec)
    text = task_texts(files)["S01-01-01"]
    assert int(HEADER_FIGURE_RE.search(text).group(1)) == 21
    assert "~4.5K (output) + ~7K (working)" in text
    assert left == 0


def test_auto_two_specs_that_differ_only_in_the_keys_build_different_trees(tmp_path):
    low, high = make_spec(), make_spec()
    for spec, output in ((low, 4), (high, 9)):
        spec["sprints"][0]["sessions"][0]["tasks"][0].update(output_k=output, working_k=6)
    first, _ = applied(fresh(tmp_path, "a"), low)
    second, _ = applied(fresh(tmp_path, "b"), high)
    assert [rel for rel in first if first[rel] != second[rel]] == [rel for rel in first if "S01-01-01" in rel]
    assert first != second


def test_auto_a_key_plus_a_body_for_one_marker_exits_2_naming_the_task(tmp_path, capsys):
    spec = auto_spec(auto=(1,))
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, make_spec())), spec)  # the bodies still hold O and W
    code, out = build.run()
    assert code == 2
    assert "LINT: doc=S01-01-01 key=fill: O" in out and "LINT: doc=S01-01-01 key=fill: W" in out
    assert not build.out.exists()


def test_auto_keys_and_lint_stop_counting_a_marker_the_spec_fills(tmp_path, capsys):
    spec = auto_spec(auto=(1,))
    outs = {}
    for name, source in (("plain", make_spec()), ("auto", spec)):
        assert pb.main(["keys", "--spec", str(_write_spec(fresh(tmp_path, name), source))]) == 0
        outs[name] = capsys.readouterr().out

    def markers(out):
        return int(re.search(r"^doc S01-01-01 markers=(\d+)$", out, re.MULTILINE).group(1))

    assert markers(outs["plain"]) - markers(outs["auto"]) == 2
    block = {name: out.split("doc S01-01-01 ")[1].split("\ndoc ")[0] for name, out in outs.items()}
    assert "  marker O " in block["plain"] and "  marker O " not in block["auto"]
    assert "  marker W " in block["plain"] and "  marker W " not in block["auto"]
    folder = fresh(tmp_path, "lint")
    code = pb.main(["lint", "--spec", str(_write_spec(folder, spec)),
                    "--bodies-dir", str(_write_bodies(folder, estimate_bodies(tmp_path, spec)))])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "session=S01-01 keys_missing=0 errors=0" in out


def test_auto_build_prints_one_delta_line_per_task_before_the_closing_lines(tmp_path, capsys):
    spec = auto_spec(auto=(1,))
    build = Build(tmp_path, capsys, estimate_bodies(tmp_path, spec), spec)
    code, out = build.run()
    assert code == 0, out
    found = DELTA_RE.findall(out)
    assert [doc for doc, _s, _m in found] == ["S01-01-01", "S01-01-02", "S01-02-01", "S01-02-02"]
    assert found[0][1] == "8" and found[1][1] == "22"  # round(1.5 + 3 + 3) is 8
    assert all(measured.isdigit() for _d, _s, measured in found)
    lines = out.rstrip().splitlines()
    assert lines[-2:] == ["fill_remaining=0", "exit=0"]
    assert max(i for i, ln in enumerate(lines) if ln.startswith("delta ")) < len(lines) - 2


def test_auto_no_zero_estimate_survives_a_built_tree(tmp_path, capsys):
    spec = auto_spec()
    build = Build(tmp_path, capsys, estimate_bodies(tmp_path, spec), spec)
    code, out = build.run()
    assert code == 0, out
    texts = [p.read_text(encoding="utf-8") for p in build.out.rglob("*.md")]
    assert len(texts) > 4
    assert not any("~0K" in t for t in texts)
    assert not any("<!-- FILL: {O} -->" in t or "<!-- FILL: {W} -->" in t for t in texts)


def test_auto_works_on_a_meta_build_and_prints_the_delta_lines(tmp_path, capsys):
    spec = auto_spec(auto=(1, 3), spec=meta_spec())
    build = meta_build(tmp_path, capsys, spec=spec, bodies=estimate_bodies(tmp_path, spec))
    code, out = build.run()
    assert code == 0, out
    found = {doc: s for doc, s, _m in DELTA_RE.findall(out)}
    assert found == {"S01-01-01": "8", "S01-01-02": "22", "S01-02-01": "16", "S01-02-02": "22"}
    assert token_count(build.root, "<!-- FILL: {O} -->")[0] == 0
    assert (build.root / "Sprint-01-X" / f"{META}-META-S01-Sprint-Plan.md").is_file()


def test_auto_a_section_body_over_a_marker_the_spec_fills_is_no_collision(tmp_path, capsys):
    spec = auto_spec(auto=(1,))
    index = index_of(tmp_path, spec)
    heading = next(h3 or h2 for name, h2, h3 in index[TASK_DOC]["markers"] if name == "O")
    skip = {(TASK_DOC, "O"), (TASK_DOC, "W")} | under(index, TASK_DOC, heading)
    keys = f"<!-- section: {heading} -->\n\nThe author's own text.\n"
    bodies = add_keys(bodies_set(index, skip=skip), TASK_DOC, keys)
    folder = fresh(tmp_path, "lint")
    code = pb.main(["lint", "--spec", str(_write_spec(folder, spec)), "--bodies-dir", str(_write_bodies(folder, bodies))])
    out = capsys.readouterr().out
    assert "LINT:" not in out
    assert code == 0, out
    files, left = applied(tmp_path, spec, bodies)
    assert "The author's own text." in task_texts(files)[TASK_DOC]
    assert left == 0


@pytest.mark.parametrize("tokens_k", [-1.5, float("nan"), float("inf")], ids=["negative", "nan", "infinity"])
def test_auto_a_tokens_k_that_cannot_price_exits_2_naming_the_task(tmp_path, capsys, tokens_k):
    spec = auto_spec(auto=(1,))
    bodies = estimate_bodies(tmp_path, spec)
    spec["sprints"][0]["sessions"][0]["tasks"][0]["required_context"][0]["tokens_k"] = tokens_k
    build = Build(tmp_path, capsys, bodies, spec)
    code, out = build.run()
    assert code == 2, out
    assert "LINT: task S01-01-01 (ParseRows)" in out and "tokens_k" in out
    assert not build.out.exists()


@pytest.mark.parametrize("reads,output,working", [(0.5, 1, 1), (1.5, 1, 2), (1.1, 1.2, 0.2)],
                         ids=["2.5", "4.5", "2.5-from-float-noise"])
def test_auto_figure_rounds_an_exact_half_the_way_the_write_back_does(reads, output, working):
    task = {"required_context": [{"tokens_k": reads}], "output_k": output, "working_k": working}
    total = sum(Decimal(str(value)) for value in (reads, output, working))
    assert f"~{pb.auto_figure(task)}K" == tsw._fmt_k_at(total, 0)


def test_auto_figure_takes_a_total_past_the_decimal_context_precision():
    task = {"required_context": [{"tokens_k": 1}], "output_k": 1e30, "working_k": 1}
    assert pb.auto_figure(task) == 10 ** 30


@pytest.mark.parametrize("keys,figure", [
    ({"estimate_k": 10 ** 400}, 10 ** 400),
    ({"estimate_k": "auto", "output_k": 10 ** 308, "working_k": 10 ** 308}, 2 * 10 ** 308),  # the Decimal sum keeps 28 digits
], ids=["numeric", "auto-total"])
def test_auto_a_figure_past_the_float_range_prints_its_digits_and_the_build_finishes(tmp_path, capsys, keys, figure):
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["tasks"][0].update(keys)
    build = Build(tmp_path, capsys, estimate_bodies(tmp_path, spec), spec)
    code, out = build.run()
    assert code in (0, 1), out
    assert DELTA_RE.findall(out)[0][:2] == (TASK_DOC, str(figure))
    listed = pb.read_manifest(build.manifest)
    assert listed and all(pb.file_hash(build.out / rel) == digest for rel, digest in listed.items())  # the second manifest write ran
    assert out.rstrip().endswith(f"exit={code}")


@pytest.mark.parametrize("command", ["keys", "lint", "build"])
@pytest.mark.parametrize("key", ["output_k", "tokens_k"])
def test_auto_an_integer_past_the_float_range_exits_2_naming_the_task(tmp_path, capsys, command, key):
    spec = auto_spec(auto=(1,))
    task = spec["sprints"][0]["sessions"][0]["tasks"][0]
    (task["required_context"][0] if key == "tokens_k" else task)[key] = 10 ** 400
    build = Build(tmp_path, capsys, {}, spec)
    bodies = ["--bodies-dir", str(build.bodies)]
    argv = {"keys": ["keys", "--spec", str(build.spec)], "lint": ["lint", "--spec", str(build.spec), *bodies],
            "build": build.argv()}[command]
    assert pb.main(argv) == 2
    out = capsys.readouterr().out
    assert "LINT: task S01-01-01 (ParseRows)" in out and key in out
