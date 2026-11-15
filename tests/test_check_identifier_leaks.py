"""Controls for scripts/check_identifier_leaks.py.

Every identifier below is invented. The plans-index lookup reads a fixture
index the test writes under its own temp directory, so the test passes in a
plugin-only checkout that has no plans index of its own.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "check_identifier_leaks.py"

# Two rows, one invented abbreviation (XYZ). QRS is absent on purpose.
INDEX = """# Plans

| Abbrev | Name | Status | Created | Last Updated | Path |
|--------|------|--------|---------|--------------|------|
| XYZ | Fixture Plan (Exec) | ACTIVE | 2026-01-01 | 2026-01-02 | Fixture/Exec-XYZ/ |
| XYZ | Fixture Plan (Meta / Discovery) | COMPLETE | 2026-01-01 | 2026-01-02 | Fixture/Meta-XYZ/ |
"""

# Positive input. The inline-defined label carries its own definition, so no family flags it.
CLEAN = "A plain sentence about leaks.\nKeep it conservative (R1: the tuples stay on the residual).\n"


def run(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *map(str, args)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "00-Index-Plans.md"
    path.write_text(INDEX, encoding="utf-8")
    return path


def write(tmp_path, name, text):
    path = tmp_path / "subject" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_positive_clean_file_exits_0_and_the_inline_label_stays_unflagged(tmp_path, index):
    subject = write(tmp_path, "clean.md", CLEAN)
    result = run(subject, "--plans-index", index)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "R1" not in result.stdout
    assert "leak=0 sample=0 candidate=0" in result.stdout


MUTATIONS = [
    # Bucket "anything else": a lesson id in citation spelling.
    ("see LL-123", "external-id", "candidate", 1),
    # Bucket "anything else": an identifier glued into a file name.
    ("see notes-PLGInventory.md", "external-id", "candidate", 1),
    # Bucket "anything else": a resolved sprint reference.
    ("customization until Sprint-04", "structure-name", "candidate", 1),
    # Bucket "anything else": an abbreviation the plans index lists.
    ("see XYZ-S01-01-Notes.md", "plan-abbrev", "leak", 1),
    # Bucket "plugin's own scaffold vocabulary": an abbreviation the index does not list.
    ("see QRS-S01-01-Notes.md", "plan-abbrev", "sample", 0),
    # Bucket "anything else": a review-finding citation.
    ("fixed per (Finding F5)", "review-finding", "candidate", 1),
]


@pytest.mark.parametrize(("defect", "family", "verdict", "code"), MUTATIONS)
def test_mutation_one_defect_is_named_with_family_and_class(tmp_path, index, defect, family, verdict, code):
    subject = write(tmp_path, "mutated.md", CLEAN + defect + "\n")
    result = run(subject, "--plans-index", index)
    assert result.returncode == code, result.stdout + result.stderr
    assert f"mutated.md:3: [{family}] {verdict}:" in result.stdout
    assert "R1" not in result.stdout


def test_review_finding_matches_across_a_line_break(tmp_path, index):
    # Bucket "anything else": a finding citation wrapped at the column limit.
    subject = write(tmp_path, "wrapped.md", CLEAN + "see closeout Finding\nF1 for why\n")
    result = run(subject, "--plans-index", index)
    assert result.returncode == 1
    assert "wrapped.md:3: [review-finding] candidate: Finding F1" in result.stdout


def test_without_plans_index_a_plan_abbrev_hit_is_an_unclassified_candidate(tmp_path):
    subject = write(tmp_path, "mutated.md", CLEAN + "see XYZ-S01-01-Notes.md\n")
    result = run(subject)
    assert result.returncode == 1
    assert "[plan-abbrev] candidate: XYZ-S01-01-" in result.stdout


def test_generic_placeholders_never_match(tmp_path, index):
    text = CLEAN + "{Abbrev}-S01-01-{Topic}.md under {Sprint-N} and BLI-{NNN}\n"
    subject = write(tmp_path, "placeholders.md", text)
    result = run(subject, "--plans-index", index)
    assert result.returncode == 0, result.stdout


def test_exempt_zone_prints_its_count_and_a_mistyped_zone_prints_zero(tmp_path, index):
    zone = tmp_path / "subject" / "templates"
    zone.mkdir(parents=True)
    (zone / "sample.md").write_text("Sprint-01-{Name}\nSession-01-{Name}\n", encoding="utf-8")
    write(tmp_path, "clean.md", CLEAN)
    root = tmp_path / "subject"
    good = run(root, "--plans-index", index, "--exempt", zone)
    assert good.returncode == 0, good.stdout
    assert f"zone {zone}: external-id=0 structure-name=2" in good.stdout
    mistyped = tmp_path / "subject" / "template"
    bad = run(root, "--plans-index", index, "--exempt", mistyped)
    assert bad.returncode == 1
    assert f"zone {mistyped}: external-id=0 structure-name=0" in bad.stdout
    assert "[structure-name] candidate: Sprint-0" in bad.stdout


@pytest.mark.parametrize("case", ["missing-path", "no-args", "missing-index", "empty-index"])
def test_usage_and_unreadable_input_exit_2(tmp_path, case):
    subject = write(tmp_path, "clean.md", CLEAN)
    if case == "missing-path":
        result = run(tmp_path / "absent.md")
    elif case == "no-args":
        result = run()
    elif case == "missing-index":
        result = run(subject, "--plans-index", tmp_path / "absent-index.md")
    else:
        empty = tmp_path / "empty-index.md"
        empty.write_text("# Plans\n\nNo table here.\n", encoding="utf-8")
        result = run(subject, "--plans-index", empty)
    assert result.returncode == 2, result.stdout + result.stderr
