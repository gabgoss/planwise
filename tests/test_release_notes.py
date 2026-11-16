"""Guards for the release-notes folder and for the workflow that publishes it.

`.github/workflows/release.yml` publishes `release-notes/X.Y.Z.md` as the body of the
release for version X.Y.Z. These tests hold the file convention and the workflow together.
"""

import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
sys.path.insert(0, str(REPO / "tools"))

import bump_version as bv

NOTES_DIR = REPO / "release-notes"
WORKFLOW = REPO / ".github" / "workflows" / "release.yml"
README = "README.md"


def notes_problems(path: Path) -> list[str]:
    """Return what is wrong with one release-notes file. An empty list means it is well formed."""
    problems = []
    if not bv.is_semver(path.stem):
        problems.append(f"{path.name}: the file name is not a semver version")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        problems.append(f"{path.name}: the file is empty")
    elif lines[0].lstrip().startswith("#"):
        problems.append(f"{path.name}: a heading comes before the opening paragraph")
    return problems


GOOD = "This release does one thing.\n\n## Fixes\n\n- A fix.\n"


def test_well_formed_notes_have_no_problems(tmp_path):
    notes = tmp_path / "1.2.0.md"
    notes.write_text(GOOD, encoding="utf-8")
    assert notes_problems(notes) == []


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        ("1.0.5.8.md", GOOD, "not a semver version"),
        ("v1.2.0.md", GOOD, "not a semver version"),
        ("next.md", GOOD, "not a semver version"),
        ("1.2.0.md", "", "is empty"),
        ("1.2.0.md", "\n  \n", "is empty"),
        ("1.2.0.md", "## Fixes\n\n- A fix.\n", "heading comes before"),
    ],
)
def test_malformed_notes_are_reported(tmp_path, name, text, expected):
    notes = tmp_path / name
    notes.write_text(text, encoding="utf-8")
    problems = notes_problems(notes)
    assert len(problems) == 1
    assert expected in problems[0]


def test_every_notes_file_in_the_repo_is_well_formed():
    assert (NOTES_DIR / README).is_file(), "the folder under test must exist, or this scan sees nothing"
    problems = []
    for path in sorted(NOTES_DIR.glob("*.md")):
        if path.name != README:
            problems += notes_problems(path)
    assert problems == []


def test_workflow_publishes_the_notes_of_the_released_version():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'notes="release-notes/$VERSION.md"' in text
    assert '--notes-file "$notes"' in text
    # Without a notes file the workflow must still publish a release.
    assert "--generate-notes" in text


def test_notes_folder_is_outside_the_shipped_subtree():
    assert NOTES_DIR.parent == REPO
    assert not (REPO / "plugins" / "planwise" / "release-notes").exists()
