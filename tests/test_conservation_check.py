"""Tests for scripts/conservation_check.py.

Every pre-edit input is a literal fixture written here, never the output of
the script under test, so a defect in the extractor cannot hide by agreeing
with itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "plugins" / "planwise" / "scripts"
SCRIPT = SCRIPTS / "conservation_check.py"
sys.path.insert(0, str(SCRIPTS))

import conservation_check

FIXTURE = """# Sample Discipline

## 8. Section Group

### 8.7 Verify the gate's input set

> [!constraint] A — First sub-rule
> Body of A. See §8.7 and § 5.

> [!practice] B — Second sub-rule
> Body of B cites §8.9.

#### Reviewer Check 075 — Size Gate

Body text.

```bash
# comment inside a fence
echo hi
```

### 8.9 A recorded figure needs its own check

> [!constraint] Sub-rule A — Third sub-rule
> Body cites §8.7 again.
"""


def _write(path: Path, text: str, newline: str = "\n") -> Path:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _pair(tmp_path: Path, after_text: str, before_text: str = FIXTURE):
    before = _write(tmp_path / "before.md", before_text)
    after = _write(tmp_path / "after.md", after_text)
    return str(before), str(after)


def test_positive_control_file_against_itself_exits_0(tmp_path):
    before, after = _pair(tmp_path, FIXTURE)
    proc = _run("--before", before, "--after", after)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # 5 headings, 3 labels, 3 distinct section tokens (§8.7, §5, §8.9)
    assert "compared 11 tokens (headings 5, labels 3, section tokens 3)" in proc.stdout


def test_inventory_from_literal_fixture():
    inv = conservation_check.extract_tokens(FIXTURE)
    assert [t for t, _ in inv["heading"]] == [
        "Sample Discipline",
        "8. Section Group",
        "8.7 Verify the gate's input set",
        "Reviewer Check 075 — Size Gate",
        "8.9 A recorded figure needs its own check",
    ]
    assert sorted(t for t, _ in inv["label"]) == ["§8.7 A", "§8.7 B", "§8.9 Sub-rule A"]
    assert set(inv["section"]) == {"§8.7", "§5", "§8.9"}


def test_mutation_heading_removed_exits_1_naming_it(tmp_path):
    mutated = FIXTURE.replace("#### Reviewer Check 075 — Size Gate\n", "")
    before, after = _pair(tmp_path, mutated)
    proc = _run("--before", before, "--after", after)
    assert proc.returncode == 1
    assert 'missing: heading "Reviewer Check 075 — Size Gate" (pre-edit line 13)' in proc.stdout


def test_mutation_section_token_removed_exits_1(tmp_path):
    mutated = FIXTURE.replace("See §8.7 and", "See it and").replace(
        "Body cites §8.7 again.", "Body cites it again."
    )
    before, after = _pair(tmp_path, mutated)
    proc = _run("--before", before, "--after", after)
    assert proc.returncode == 1
    assert "missing: section-token §8.7 (pre-edit line 8)" in proc.stdout


def test_section_tokens_compare_as_a_set(tmp_path):
    # One of two §8.7 occurrences removed: the token still survives.
    mutated = FIXTURE.replace("Body cites §8.7 again.", "Body cites it again.")
    before, after = _pair(tmp_path, mutated)
    proc = _run("--before", before, "--after", after)
    assert proc.returncode == 0, proc.stdout


LETTERED = "# Lettered\n\nSee §9.A.3 for the rule, and §8.7. Then stop.\n"


def test_dotted_letter_token_positive_control_exits_0(tmp_path):
    before, after = _pair(tmp_path, LETTERED, before_text=LETTERED)
    proc = _run("--before", before, "--after", after)
    assert proc.returncode == 0, proc.stdout
    assert "section tokens 2" in proc.stdout


def test_mutation_dotted_letter_token_changed_exits_1(tmp_path):
    mutated = LETTERED.replace("§9.A.3", "§9.B.3")
    before, after = _pair(tmp_path, mutated, before_text=LETTERED)
    proc = _run("--before", before, "--after", after)
    assert proc.returncode == 1
    assert "missing: section-token §9.A.3 (pre-edit line 3)" in proc.stdout


def test_sentence_final_period_is_not_part_of_the_token():
    inv = conservation_check.extract_tokens(LETTERED)
    assert set(inv["section"]) == {"§9.A.3", "§8.7"}


def test_mutation_sub_rule_letter_removed_exits_1(tmp_path):
    mutated = FIXTURE.replace("> [!practice] B — Second sub-rule", "> [!practice] Second sub-rule")
    before, after = _pair(tmp_path, mutated)
    proc = _run("--before", before, "--after", after)
    assert proc.returncode == 1
    assert "missing: label §8.7 B (pre-edit line 10)" in proc.stdout


def test_moved_token_in_allowed_sibling_exits_0(tmp_path):
    mutated = FIXTURE.replace("#### Reviewer Check 075 — Size Gate\n", "")
    before, after = _pair(tmp_path, mutated)
    sibling = _write(tmp_path / "sibling.md", "# Part 2\n\n#### Reviewer Check 075 — Size Gate\n")
    proc = _run("--before", before, "--after", after, "--allow-moved", str(sibling))
    assert proc.returncode == 0, proc.stdout
    assert f'moved: heading "Reviewer Check 075 — Size Gate" -> {sibling}' in proc.stdout
    assert "missing:" not in proc.stdout


def test_moved_without_allow_is_missing(tmp_path):
    mutated = FIXTURE.replace("#### Reviewer Check 075 — Size Gate\n", "")
    before, after = _pair(tmp_path, mutated)
    _write(tmp_path / "sibling.md", "#### Reviewer Check 075 — Size Gate\n")
    proc = _run("--before", before, "--after", after)
    assert proc.returncode == 1
    assert "moved:" not in proc.stdout


def test_fence_control_heading_like_line_in_fence_is_never_counted(tmp_path):
    mutated = FIXTURE.replace("# comment inside a fence", "# a rewritten fenced comment")
    before, after = _pair(tmp_path, mutated)
    proc = _run("--before", before, "--after", after)
    assert proc.returncode == 0, proc.stdout
    assert "headings 5" in proc.stdout


def test_crlf_before_against_lf_after_exits_0(tmp_path):
    before = _write(tmp_path / "before.md", FIXTURE, newline="\r\n")
    after = _write(tmp_path / "after.md", FIXTURE)
    assert b"\r\n" in before.read_bytes()
    proc = _run("--before", str(before), "--after", str(after))
    assert proc.returncode == 0, proc.stdout
    assert "compared 11 tokens" in proc.stdout


def test_before_rev_that_does_not_resolve_exits_2(tmp_path):
    after = _write(tmp_path / "after.md", FIXTURE)
    proc = _run(
        "--before-rev",
        "no-such-revision-0000",
        "--repo",
        str(REPO_ROOT),
        "--path",
        "plugins/planwise/scripts/conservation_check.py",
        "--after",
        str(after),
    )
    assert proc.returncode == 2
    assert "error:" in proc.stderr


def test_usage_error_both_before_forms_exits_2(tmp_path):
    before, after = _pair(tmp_path, FIXTURE)
    proc = _run("--before", before, "--before-rev", "HEAD", "--after", after)
    assert proc.returncode == 2


def _direct_run_leaves_pycache(root: Path, strip_flag: bool) -> bool:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    source = (SCRIPTS / "conservation_check.py").read_text(encoding="utf-8")
    if strip_flag:
        source = source.replace("sys.dont_write_bytecode = True", "pass")
    (scripts / "conservation_check.py").write_text(source, encoding="utf-8")
    (scripts / "markdown_parser.py").write_bytes((SCRIPTS / "markdown_parser.py").read_bytes())
    doc = _write(root / "doc.md", FIXTURE)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    proc = subprocess.run(
        [sys.executable, str(scripts / "conservation_check.py"), "--before", str(doc), "--after", str(doc)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return (scripts / "__pycache__").exists()


def test_direct_run_writes_no_pycache_next_to_the_script(tmp_path):
    assert not _direct_run_leaves_pycache(tmp_path / "fixed", strip_flag=False)
    # Control: the same copy without the flag does write bytecode, so the
    # assertion above can fail.
    assert _direct_run_leaves_pycache(tmp_path / "control", strip_flag=True)


def test_missing_after_file_exits_2(tmp_path):
    before = _write(tmp_path / "before.md", FIXTURE)
    proc = _run("--before", str(before), "--after", str(tmp_path / "absent.md"))
    assert proc.returncode == 2
