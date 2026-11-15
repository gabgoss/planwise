"""Controls for scripts/lint_authoring_frontmatter.py.

Each subcommand has a positive control (clean input exits 0), mutation controls
(one defect added exits 1 and names it) and a usage control (exit 2).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import lint_authoring_frontmatter as lint
from frontmatter_parser import parse_frontmatter_map

CLEAN_RULE = '---\ndescription: A clean rule\npaths: src/**, docs/**\n---\n\n# Body\n'
CLEAN_SKILL = (
    '---\nname: good-skill\ndescription: Does a thing. Use when needed.\n'
    'context: fork\nagent: Explore\nallowed-tools: Read, Bash(git *)\n---\n\n# Body\n'
)


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path


def _run(capsys, *argv):
    code = lint.main(list(argv))
    return code, capsys.readouterr().out


def test_parser_returns_list_as_one_string():
    fm = parse_frontmatter_map('description: x\npaths:\n  - "a/**"\n  - "b/**"\nallowed-tools:\n  - Bash(git)')
    assert fm is not None
    assert fm["paths"] == '\n  - "a/**"\n  - "b/**"'
    assert lint._list_items(fm["paths"]) == ["a/**", "b/**"]
    assert "Bash(git)" in fm["allowed-tools"]


def test_rules_positive_control(tmp_path, capsys):
    _write(tmp_path, "good-rule.md", CLEAN_RULE)
    code, out = _run(capsys, "rules", str(tmp_path))
    assert code == 0 and "0 finding(s)" in out


def test_rules_global_rule_passes_and_is_listed(tmp_path, capsys):
    _write(tmp_path, "global-rule.md", "---\ndescription: Always on\n---\nbody\n")
    code, out = _run(capsys, "rules", "--report-global", str(tmp_path))
    assert code == 0 and "treated as a global rule" in out


def test_rules_mutation_broad_paths(tmp_path, capsys):
    # breaks rule-authoring.md section 2: paths must not be an extension glob over markdown
    for value in ('"**/*.md"', '"*.md"', '"**"'):
        _write(tmp_path, "bad-paths.md", f"---\ndescription: d\npaths: {value}\n---\nbody\n")
        code, out = _run(capsys, "rules", str(tmp_path))
        assert code == 1 and "over-broad glob" in out


def test_rules_mutation_broad_paths_in_list(tmp_path, capsys):
    # breaks rule-authoring.md section 2 through the YAML list form
    _write(tmp_path, "bad-list.md", '---\ndescription: d\npaths:\n  - "src/**"\n  - "**/*.md"\n---\nbody\n')
    code, out = _run(capsys, "rules", str(tmp_path))
    assert code == 1 and "**/*.md" in out


def test_rules_mutation_no_description(tmp_path, capsys):
    # breaks rule-authoring.md section 1: description is required
    _write(tmp_path, "no-desc.md", "---\npaths: src/**\n---\nbody\n")
    code, out = _run(capsys, "rules", str(tmp_path))
    assert code == 1 and "missing description" in out


def test_rules_mutation_bad_name(tmp_path, capsys):
    # breaks rule-authoring.md section 4: lowercase with hyphens
    _write(tmp_path, "Bad_Name.md", CLEAN_RULE)
    code, out = _run(capsys, "rules", str(tmp_path))
    assert code == 1 and "not lowercase with hyphens" in out


def test_rules_usage_control(tmp_path, capsys):
    code, _out = _run(capsys, "rules", str(tmp_path / "absent"))
    assert code == 2
    code, _out = _run(capsys, "bogus", str(tmp_path))
    assert code == 2
    code, _out = _run(capsys, "rules", str(tmp_path))  # empty folder: nothing was seen
    assert code == 2


def test_skills_positive_control(tmp_path, capsys):
    skill = _write(tmp_path, "SKILL.md", CLEAN_SKILL)
    code, out = _run(capsys, "skills", str(skill))
    assert code == 0 and "0 finding(s)" in out


def test_skills_mutation_agent_without_fork(tmp_path, capsys):
    # breaks skill-authoring.md section 5b: agent is meaningful only with context: fork
    text = CLEAN_SKILL.replace("context: fork\n", "")
    code, out = _run(capsys, "skills", str(_write(tmp_path, "SKILL.md", text)))
    assert code == 1 and "agent is set without context: fork" in out


def test_skills_mutation_bash_without_glob(tmp_path, capsys):
    # breaks skill-authoring.md section 7b: a Bash pattern ends in a glob
    text = CLEAN_SKILL.replace("Bash(git *)", "Bash(git)")
    code, out = _run(capsys, "skills", str(_write(tmp_path, "SKILL.md", text)))
    assert code == 1 and "Bash(git)" in out


def test_skills_mutation_501_lines(tmp_path, capsys):
    # breaks skill-authoring.md section 1: SKILL.md stays under 500 lines
    text = CLEAN_SKILL + "line\n" * (501 - CLEAN_SKILL.count("\n"))
    skill = _write(tmp_path, "SKILL.md", text)
    assert lint._count_lines(skill) == 501
    code, out = _run(capsys, "skills", str(skill))
    assert code == 1 and "501 lines" in out


def test_skills_mutation_name_and_description(tmp_path, capsys):
    # breaks skill-authoring.md section 2: name is lowercase-hyphen, at most 64 characters, description exists
    text = "---\nname: " + "a" * 65 + "\n---\nbody\n"
    code, out = _run(capsys, "skills", str(_write(tmp_path, "SKILL.md", text)))
    assert code == 1 and "65 characters" in out and "missing description" in out
    text = "---\nname: Bad_Name\ndescription: d\n---\nbody\n"
    code, out = _run(capsys, "skills", str(_write(tmp_path, "SKILL.md", text)))
    assert code == 1 and "not lowercase-hyphen" in out


def test_skills_crlf_input_is_read(tmp_path, capsys):
    text = CLEAN_SKILL.replace("\n", "\r\n")
    code, _out = _run(capsys, "skills", str(_write(tmp_path, "SKILL.md", text)))
    assert code == 0


def test_skills_usage_control(tmp_path, capsys):
    code, _out = _run(capsys, "skills", str(tmp_path / "absent"))
    assert code == 2
    code, _out = _run(capsys, "skills")
    assert code == 2
