#!/usr/bin/env python3
"""Every migrator script has a run-twice test, and no migrator escapes the list.

A migrator run a second time on its own output must change nothing. The
run-twice assertions already live beside each migrator's other tests, each on
a fixture built from a shipped seed or a byte-exact legacy shape. This module
adds the piece those tests cannot give: a denominator that comes from the
scripts directory, not from a list a test author kept.

  - The migrator set is enumerated from `plugins/planwise/scripts` by file
    name, never from the registry below.
  - Each migrator maps to the existing test that runs it twice, and the test
    must exist in the named file (and in the named class, when it has one).
  - A migrator on disk with no registry entry fails, and a registry entry
    with no script on disk fails.

Run with:  python -m pytest -q -c pytest.ini tests/test_migrators_idempotent.py
"""

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "planwise" / "scripts"

# script -> (test file, test class or None, test function).
# Each named test runs the migrator a second time and asserts the tree is
# unchanged (or, for the orchestrators, that the second call is silent).
RUN_TWICE = {
    "migrate_backlog_index.py": (
        "test_migrate_backlog_index.py", None,
        "test_already_migrated_state_is_clean_and_rerun_appends_nothing",
    ),
    "migrate_lessons_index.py": (
        "test_migrate_lessons_index.py", "TestFullMigration",
        "test_second_write_is_generated_idempotent",
    ),
    "migrate_plans_index.py": (
        "test_migrate_plans_index.py", None,
        "test_a_clean_second_run_leaves_the_tree_identical",
    ),
    "backlog_migration.py": (
        "test_backlog_migration.py", None,
        "test_second_call_after_migrated_is_generated_and_touches_nothing",
    ),
    "lessons_migration.py": (
        "test_lessons_migration_e2e.py", None,
        "test_golden_idempotency_with_relocated_fenced_template",
    ),
    "plans_migration.py": (
        "test_plans_migration_e2e.py", None,
        "test_path1_run_upgrade_migrates_fixture_b_end_to_end",
    ),
    "rule_descope_migration.py": (
        "test_rule_descope_migration.py", "TestMigrationBranches",
        "test_migration_is_idempotent",
    ),
}


def migrator_scripts(scripts_dir: Path) -> set:
    """Names of the migrator entry points in `scripts_dir`: the three index
    migrators (`migrate_*_index.py`) and the orchestrators (`*_migration.py`).
    Helper modules such as `migrate_lessons_support.py` are not entry points."""
    return {
        p.name for pattern in ("migrate_*_index.py", "*_migration.py")
        for p in scripts_dir.glob(pattern)
    }


def uncovered(found: set, registry: dict) -> tuple:
    """(scripts on disk with no entry, entries with no script on disk)."""
    return found - set(registry), set(registry) - found


def _has_test(path: Path, klass, func: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if klass is not None:
        match = re.search(rf"^class {re.escape(klass)}\b.*?(?=^class |\Z)", text, re.MULTILINE | re.DOTALL)
        if match is None:
            return False
        text = match.group(0)
    return re.search(rf"^\s*def {re.escape(func)}\(", text, re.MULTILINE) is not None


def test_the_enumeration_saw_the_scripts_directory():
    # A walk that saw nothing would make every set check below pass trivially.
    found = migrator_scripts(SCRIPTS)
    assert len(found) >= len(RUN_TWICE), sorted(found)


def test_every_migrator_script_is_in_the_run_twice_registry():
    missing, stale = uncovered(migrator_scripts(SCRIPTS), RUN_TWICE)
    assert not missing, f"migrator with no run-twice test: {sorted(missing)}"
    assert not stale, f"registry names a script that is not on disk: {sorted(stale)}"


def test_the_set_check_fails_for_a_new_migrator_and_for_a_removed_one():
    # Control, both directions: the same check must be able to fail.
    found = migrator_scripts(SCRIPTS)
    missing, _ = uncovered(found | {"migrate_widgets_index.py"}, RUN_TWICE)
    assert missing == {"migrate_widgets_index.py"}
    _, stale = uncovered(found - {"plans_migration.py"}, RUN_TWICE)
    assert stale == {"plans_migration.py"}


def test_every_registered_run_twice_test_exists():
    absent = []
    for script, (test_file, klass, func) in sorted(RUN_TWICE.items()):
        path = TESTS / test_file
        if not path.is_file() or not _has_test(path, klass, func):
            absent.append(f"{script} -> {test_file}::{klass + '::' if klass else ''}{func}")
    assert not absent, absent


def test_the_existence_check_fails_for_a_name_that_is_not_there():
    path = TESTS / "test_migrate_backlog_index.py"
    assert _has_test(path, None, "test_already_migrated_state_is_clean_and_rerun_appends_nothing")
    assert not _has_test(path, None, "test_no_such_run_twice_test")
    assert not _has_test(path, "NoSuchClass", "test_already_migrated_state_is_clean_and_rerun_appends_nothing")
