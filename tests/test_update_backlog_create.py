"""Unit tests for update_backlog.py's `--create` path and its CLI surface.

`--create` writes a new item's file and nothing else. It rejects a
`--feature` over the 120-character title cap rather than truncating it,
validates the configured id format, refuses a colliding id and resolves the
`--files` path. The classes here were split out of test_update_backlog.py,
and build on update_backlog_fixture.py like it.

Each test builds an isolated temp planwise tree; none mutate the live backlog.

Run with:  python -m pytest tests/test_update_backlog_create.py -q
"""

import sys
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for update_backlog_fixture

import generate_backlog_index
from update_backlog_fixture import CONFIG_YAML_FIXTURE, _UpdateBacklogFixtureBase


class TestBacklogCliSurface(_UpdateBacklogFixtureBase):
    """CLI-level behavior of main(): input validation and the --create path.

    TestIdempotentArchival and TestEscapedPipeRows both exercise the
    status-update path's archival semantics; this class covers the
    surrounding CLI surface neither one touches — rejected input, a
    non-archival status transition, and item creation.
    """

    def test_invalid_status_is_rejected_without_changing_the_file(self):
        self.write_index(
            "| 046 | Drift reconcile | Medium | NOT_STARTED | INFRA | - | [01](item.md) |\n"
        )
        self.write_item_file("item.md", status="NOT_STARTED", archived=False)
        before = self.read_index_text()

        _, err, code = self._run_main(
            ["--config", str(self.config_path), "--id", "046", "--status", "BOGUS"]
        )

        self.assertEqual(code, 1)
        self.assertIn("Invalid status", err)
        self.assertEqual(self.read_index_text(), before)  # no partial write

    def test_missing_id_is_rejected_by_argument_parsing(self):
        self.write_index(
            "| 046 | Drift reconcile | Medium | NOT_STARTED | INFRA | - | [01](item.md) |\n"
        )
        before = self.read_index_text()

        _, err, code = self._run_main(
            ["--config", str(self.config_path), "--status", "IN_PROGRESS"]
        )

        self.assertEqual(code, 2)  # argparse's own usage-error exit code
        self.assertIn("--id", err)
        self.assertEqual(self.read_index_text(), before)

    def test_non_archival_transition_does_not_touch_archive(self):
        self.write_index(
            "| 050 | Some item | Medium | NOT_STARTED | INFRA | - | [01](item.md) |\n"
        )
        item = self.write_item_file(
            "item.md", status="NOT_STARTED", archived=False, item_id="050"
        )
        before = self.read_index_text()

        out, _, code = self._run_main(
            ["--config", str(self.config_path), "--id", "050", "--status", "IN_PROGRESS"]
        )

        self.assertIsNone(code)
        self.assertIn("NOT_STARTED → IN_PROGRESS", out)
        self.assertIn("status: IN_PROGRESS", item.read_text(encoding="utf-8"))
        self.assertEqual(self.read_index_text(), before)
        # A non-archival status leaves the file in place and never even
        # creates the Archive directory.
        self.assertTrue((self.backlog_dir / "item.md").exists())
        self.assertFalse(self.archive_dir.exists())

    def test_create_writes_only_the_bli_file(self):
        self.write_index("")  # header + separator only, no data rows
        before = self.read_index_text()

        out, _, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "New reconciliation guard",
                "--priority", "High",
                "--abbrev", "TEST",
                "--files", "new-TEST-item.md",
            ]
        )

        self.assertIsNone(code)
        self.assertIn("Created backlog item 099", out)
        self.assertIn("generate_backlog_index.py --write", out)

        bli_path = self.backlog_dir / "new-TEST-item.md"
        self.assertTrue(bli_path.exists())
        rendered = bli_path.read_text(encoding="utf-8")

        # The frontmatter fence opens the file and closes right after the
        # last required key -- pinned against that specific closing point,
        # not an unqualified count of "---" lines (a later "---" rule also
        # separates the body).
        self.assertTrue(rendered.startswith("---\n"))
        self.assertIn("\nblocks: []\n---\n", rendered)

        # All seven frontmatter keys the schema requires.
        self.assertIn("id: 099", rendered)
        self.assertIn('title: "New reconciliation guard"', rendered)
        self.assertIn("priority: High", rendered)
        self.assertIn("status: NOT_STARTED", rendered)  # --status omitted -> default
        self.assertIn("abbrev: TEST", rendered)
        self.assertRegex(rendered, r"\ncreated: \d{4}-\d{2}-\d{2}\n")
        self.assertIn("blocks: []", rendered)

        # Status lives in frontmatter only -- the body carries no separate
        # status line.
        self.assertNotIn("**Status:**", rendered)

        # --create never appends an index row -- the index is a build
        # artifact generate_backlog_index.py --write produces.
        self.assertEqual(self.read_index_text(), before)

    def test_create_rejects_a_duplicate_id_without_writing_a_file(self):
        self.write_index(
            "| 099 | Existing | High | NOT_STARTED | TEST | - | [01](existing-TEST-item.md) |\n"
        )
        before = self.read_index_text()

        _, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Duplicate attempt",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "dup-TEST-item.md",
            ]
        )

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertEqual(self.read_index_text(), before)
        self.assertFalse((self.backlog_dir / "dup-TEST-item.md").exists())

    def test_create_rejects_a_bare_duplicate_against_an_existing_prefixed_row(self):
        # The existing row is stored in PREFIXED form. Pin id_format
        # explicitly to "bare" so the new item's ID renders bare ("099")
        # instead of following the index's own predominant (prefixed) form --
        # otherwise the duplicate guard could pass for the wrong reason (an
        # exact string match on "PFX-099" == "PFX-099"). With the new ID
        # forced bare, the guard can only catch the clash by normalizing
        # "PFX-099" and "099" to the same numeric component (normalize_id),
        # which is exactly the contract under regression here.
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: bare\n", encoding="utf-8"
        )
        self.write_index(
            "| PFX-099 | Existing | High | NOT_STARTED | TEST | - | "
            "[01](existing-TEST-item.md) |\n"
        )
        before = self.read_index_text()

        _, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Duplicate attempt",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "dup-TEST-item.md",
            ]
        )

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertEqual(self.read_index_text(), before)
        self.assertFalse((self.backlog_dir / "dup-TEST-item.md").exists())


class TestTitleCapAndRenderedBody(_UpdateBacklogFixtureBase):
    """The 120-character title-cap funnel at --create (never a silent
    truncation), and the two `_render_bli_file` divergence fixes: no body
    `**Status:**` line, and `## Related` in link form."""

    def _create(self, feature: str, filename: str = "cap-TEST-item.md") -> tuple[str, str, object]:
        return self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", feature,
                "--priority", "High",
                "--abbrev", "TEST",
                "--files", filename,
            ]
        )

    def test_feature_over_120_chars_is_rejected_and_writes_nothing(self):
        self.write_index("")
        feature = "x" * 121

        _out, err, code = self._create(feature)

        self.assertEqual(code, 1)
        self.assertIn("121", err)
        self.assertIn("120", err)
        self.assertFalse((self.backlog_dir / "cap-TEST-item.md").exists())

    def test_feature_at_120_chars_is_accepted(self):
        self.write_index("")
        feature = "x" * 120

        _out, err, code = self._create(feature)

        self.assertIsNone(code)
        self.assertEqual(err, "")
        self.assertTrue((self.backlog_dir / "cap-TEST-item.md").exists())

    def test_feature_at_120_raw_chars_with_a_quote_is_rejected_after_escaping(self):
        # 120 raw characters, one of them a `"` -- the generator's own
        # `_strip_quotes` never unescapes an inner `\"`, so escaping this
        # for frontmatter storage grows it to 121 characters, over the cap
        # the generator renders and truncates against. Accepting it here on
        # the raw length would let it pass this rejection and still get
        # silently truncated on the next `--write`.
        self.write_index("")
        feature = "x" * 119 + '"'

        _out, err, code = self._create(feature)

        self.assertEqual(code, 1)
        self.assertIn("121", err)  # the escaped length
        self.assertIn("120", err)  # both the raw length and the cap
        self.assertFalse((self.backlog_dir / "cap-TEST-item.md").exists())

    def test_created_item_carries_no_body_status_line(self):
        self.write_index("")

        self._create("A short feature")

        rendered = (self.backlog_dir / "cap-TEST-item.md").read_text(encoding="utf-8")
        self.assertNotIn("**Status:**", rendered)
        self.assertIn("**Priority:**", rendered)
        self.assertIn("**Domain:**", rendered)

    def test_related_section_uses_link_form_not_a_backticked_filename(self):
        self.write_index("")

        self._create("A short feature")

        rendered = (self.backlog_dir / "cap-TEST-item.md").read_text(encoding="utf-8")
        self.assertIn("[cap-TEST-item.md](cap-TEST-item.md)", rendered)
        self.assertNotIn("`cap-TEST-item.md`", rendered)

    def test_create_against_a_generated_heading_less_index_exits_0_and_leaves_it_byte_identical(self):
        generated_index = (
            b"Generated: 2026-01-01\n\n"
            b"| ID  | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
            b"|-----|-------|----------|--------|--------|---------|--------|-------|------|\n"
        )
        index_path = self.backlog_dir / "00-Index-Backlog.md"
        index_path.write_bytes(generated_index)

        _out, _err, code = self._create("A generated-index create")

        self.assertIsNone(code)
        self.assertEqual(index_path.read_bytes(), generated_index)
        self.assertTrue((self.backlog_dir / "cap-TEST-item.md").exists())


class TestIdFormatConfigValidation(_UpdateBacklogFixtureBase):
    """The four branches of the optional top-level `id_format` config key.

    An unrecognized value is announced on stderr and still falls back to
    "bare" — the permissive behavior is deliberate, so the warning must not
    change the outcome, raise, or produce a non-zero exit. The three
    recognized branches (absent, "prefixed", "bare") must stay silent.

    Every fixture seeds the index with a PREFIXED row (read-only, for
    inference and the duplicate check). The frontmatter `id:` line itself is
    ALWAYS bare regardless of which branch runs: the generator's own
    frontmatter reader (`_normalize_id_text`) requires a pure-digit value
    and raises on a prefixed one (proven against the live generator --
    `--check` on a `--create`d item under `id_format: prefixed` exits
    non-zero), so `create_backlog_item` renders the bare form into
    frontmatter no matter what id_format resolves to. What each branch still
    discriminates is silence vs. a WARNING on stderr for an unrecognized
    value -- not the written id.
    """

    def _create_099(self) -> tuple[str, str, object]:
        return self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Id format branch probe",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "idfmt-TEST-item.md",
            ]
        )

    def _seed_prefixed_index(self) -> None:
        self.write_index(
            "| PFX-050 | Existing | High | NOT_STARTED | TEST | - | "
            "[01](existing-TEST-item.md) |\n"
        )

    def _created_file_text(self) -> str:
        return (self.backlog_dir / "idfmt-TEST-item.md").read_text(encoding="utf-8")

    def test_absent_id_format_infers_the_predominant_form_silently(self):
        self._seed_prefixed_index()  # config carries no id_format key

        _, err, code = self._create_099()

        self.assertIsNone(code)
        self.assertEqual(err, "")  # no warning on the inference path
        # Frontmatter is always bare -- see the class docstring.
        self.assertIn("id: 099", self._created_file_text())
        self.assertNotIn("id: PFX-099", self._created_file_text())

    def test_prefixed_id_format_is_accepted_silently(self):
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: prefixed\n", encoding="utf-8"
        )
        self._seed_prefixed_index()

        _, err, code = self._create_099()

        self.assertIsNone(code)
        self.assertEqual(err, "")
        # Frontmatter is always bare -- see the class docstring.
        self.assertIn("id: 099", self._created_file_text())
        self.assertNotIn("id: PFX-099", self._created_file_text())

    def test_bare_id_format_is_accepted_silently(self):
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: bare\n", encoding="utf-8"
        )
        self._seed_prefixed_index()

        _, err, code = self._create_099()

        self.assertIsNone(code)
        self.assertEqual(err, "")
        text = self._created_file_text()
        self.assertNotIn("id: PFX-099", text)  # the explicit pin beat inference
        self.assertIn("id: 099", text)

    def test_unrecognized_id_format_warns_and_still_falls_back_to_bare(self):
        # "prefix" is the near-miss typo the warning exists to catch.
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: prefix\n", encoding="utf-8"
        )
        self._seed_prefixed_index()

        out, err, code = self._create_099()

        # Announced, not fatal: no exception, no non-zero exit, file written.
        self.assertIsNone(code)
        self.assertIn("Created backlog item 099", out)

        # The warning names both the offending value and the accepted set.
        self.assertIn("WARNING", err)
        self.assertIn("'prefix'", err)
        self.assertIn("prefixed", err)
        self.assertIn("bare", err)

        # Behavior is unchanged — still the legacy bare form.
        text = self._created_file_text()
        self.assertNotIn("id: PFX-099", text)
        self.assertIn("id: 099", text)
        self.assertTrue((self.backlog_dir / "idfmt-TEST-item.md").exists())


class TestCreateCollisionSources(_UpdateBacklogFixtureBase):
    """--create's duplicate-id guard must see an id wherever it lives: a
    generated Archive shard, a hub overflow leaf, or a real item file that
    hasn't been folded into any generated index file yet."""

    SOURCE_TABLE = (
        "| ID | Title | Priority | Status | Abbrev | Score | File |\n"
        "|----|-------|----------|--------|--------|-------|------|\n"
        "| 100 | Existing elsewhere | Medium | COMPLETE | INFRA | - | "
        "[shard-item.md](shard-item.md) |\n"
    )

    def _naming(self):
        return generate_backlog_index._index_naming(
            self.backlog_dir / "00-Index-Backlog.md"
        )

    def _create_100(self, files: str) -> tuple[str, str, object]:
        return self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "100",
                "--feature", "Duplicate attempt",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", files,
            ]
        )

    def test_rejects_id_present_only_in_an_archive_shard(self):
        self.write_index("")  # the hub itself carries no row for this id
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        shard = generate_backlog_index._shard_filename(self._naming(), 100, 199)
        (self.archive_dir / shard).write_text(self.SOURCE_TABLE, encoding="utf-8")

        _out, err, code = self._create_100("dup-shard-item.md")

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertFalse((self.backlog_dir / "dup-shard-item.md").exists())

    def test_rejects_id_present_only_in_an_overflow_leaf(self):
        self.write_index("")  # the hub itself carries no row for this id
        leaf = generate_backlog_index._hub_filename(self._naming(), 100, 199, 1)
        (self.backlog_dir / leaf).write_text(self.SOURCE_TABLE, encoding="utf-8")

        _out, err, code = self._create_100("dup-leaf-item.md")

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertFalse((self.backlog_dir / "dup-leaf-item.md").exists())

    def test_rejects_id_present_only_in_an_unregenerated_item_file(self):
        self.write_index("")  # no generated file mentions this id at all
        self.write_item_file(
            "unregenerated-item.md", status="NOT_STARTED", item_id="100"
        )

        _out, err, code = self._create_100("dup-fresh-item.md")

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertFalse((self.backlog_dir / "dup-fresh-item.md").exists())


class TestCreateExistingFileIdVerification(_UpdateBacklogFixtureBase):
    """--create with an existing --files target verifies the existing
    file's OWN frontmatter id before claiming it -- a stale or mistyped
    --files argument must never silently misattribute another item's file.
    """

    def test_rejects_when_existing_file_carries_a_different_id(self):
        self.write_index("")
        existing = self.backlog_dir / "claimed-item.md"
        existing.write_text(
            "---\nid: 050\nstatus: NOT_STARTED\ncreated: 2026-07-06\n---\n\n# x\n",
            encoding="utf-8",
        )
        before = existing.read_bytes()

        _out, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Claim someone else's file",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "claimed-item.md",
            ]
        )

        self.assertEqual(code, 1)
        self.assertIn("claimed-item.md", err)
        self.assertEqual(existing.read_bytes(), before)

    def test_rejects_when_existing_files_frontmatter_cannot_be_read(self):
        self.write_index("")
        existing = self.backlog_dir / "unreadable-item.md"
        existing.write_text("no frontmatter fence at all\n", encoding="utf-8")
        before = existing.read_bytes()

        _out, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Claim an unreadable file",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "unreadable-item.md",
            ]
        )

        self.assertEqual(code, 1)
        self.assertIn("unreadable-item.md", err)
        self.assertEqual(existing.read_bytes(), before)

    def test_accepts_and_reports_created_when_existing_file_already_carries_the_id(self):
        self.write_index("")
        existing = self.backlog_dir / "already-mine.md"
        existing.write_text(
            "---\nid: 099\nstatus: NOT_STARTED\ncreated: 2026-07-06\n---\n\n# x\n",
            encoding="utf-8",
        )
        before = existing.read_bytes()

        out, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Re-run create on my own file",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "already-mine.md",
            ]
        )

        self.assertIsNone(code)
        self.assertEqual(err, "")
        self.assertIn("Created backlog item 099", out)
        self.assertEqual(existing.read_bytes(), before)  # never overwritten


class TestPrefixedIdModeEndToEnd(_UpdateBacklogFixtureBase):
    """--create must write a frontmatter id the generator can actually read
    back. Proven against the live generator: `--check` on a prefixed
    frontmatter id (the OLD behavior under id_format: prefixed) exits
    non-zero with `Error: non-numeric id value 'PFX-005'`. So --create now
    always writes the bare form, and the disk lookups (`_find_items_by_id`,
    `_known_ids_from_disk`) recognize whichever form a file actually
    carries via `normalize_id`, never the generator's pure-digit-only
    `_normalize_id_text`.
    """

    def test_create_under_prefixed_id_format_writes_a_bare_frontmatter_id(self):
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: prefixed\n", encoding="utf-8"
        )
        self.write_index(
            "| PFX-050 | Existing | High | NOT_STARTED | TEST | - | "
            "[01](existing-TEST-item.md) |\n"
        )

        _out, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "060",
                "--feature", "Prefixed mode probe",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "prefixed-probe-item.md",
            ]
        )

        self.assertIsNone(code)
        self.assertEqual(err, "")
        rendered = (self.backlog_dir / "prefixed-probe-item.md").read_text(encoding="utf-8")
        self.assertIn("id: 060", rendered)
        self.assertNotIn("id: PFX-060", rendered)

        # End-to-end proof: scan_backlog is what --check/--write run over
        # every item file. It raising nothing, and returning the new item,
        # IS the proof that --check/--write would succeed on this file.
        items = generate_backlog_index.scan_backlog(
            self.backlog_dir, self.archive_dir, self.backlog_dir / "00-Index-Backlog.md"
        )
        self.assertIn("060", [item["id"] for item in items])

    def test_status_finds_a_file_by_id_after_create_under_prefixed_id_format(self):
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: prefixed\n", encoding="utf-8"
        )
        self.write_index("")
        self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "061",
                "--feature", "Prefixed mode lookup probe",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "prefixed-lookup-item.md",
            ]
        )

        out = self.run_update("061", "IN_PROGRESS")

        self.assertIn("NOT_STARTED → IN_PROGRESS", out)
        rendered = (self.backlog_dir / "prefixed-lookup-item.md").read_text(encoding="utf-8")
        self.assertIn("status: IN_PROGRESS", rendered)


class TestCreateFilesPathResolution(_UpdateBacklogFixtureBase):
    """The first `--files` entry is the new item file. It resolves against the
    config-derived backlog folder: a bare name, a project-relative path, or an
    absolute path is accepted when it names a file directly inside that folder.
    Anything else is refused before a byte is written. The heading and the
    first Related link always carry the bare file name, never a path."""

    ITEM = "BB-099-01-TEST-Probe.md"
    STEM = "BB-099-01-TEST-Probe"

    def _create(self, files: str) -> tuple[str, str, object]:
        return self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Path probe",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", files,
            ]
        )

    def _tree(self) -> list[str]:
        return sorted(
            p.relative_to(self.tmp).as_posix() for p in self.tmp.rglob("*") if p.is_file()
        )

    def _assert_written_directly(self, code) -> str:
        self.assertIsNone(code)
        self.assertEqual(
            self._tree(),
            [
                "planwise/Backlog/00-Index-Backlog.md",
                f"planwise/Backlog/{self.ITEM}",
                "planwise/config.yaml",
            ],
        )
        rendered = (self.backlog_dir / self.ITEM).read_text(encoding="utf-8")
        self.assertIn(f"# {self.STEM}: Path probe\n", rendered)
        self.assertIn(f"- [{self.ITEM}]({self.ITEM}) - file for this item", rendered)
        self.assertNotIn("planwise/Backlog", rendered)
        return rendered

    def _assert_refused_and_nothing_written(self, files: str) -> str:
        before = self._tree()
        # Positive control: the walk saw the two fixture files, so an
        # unchanged tree afterwards is a real "nothing written", not a blind walk.
        self.assertEqual(len(before), 2)

        _out, err, code = self._create(files)

        self.assertEqual(code, 1)
        self.assertEqual(self._tree(), before)
        return err

    def test_bare_name_heading_holds_the_stem(self):
        self.write_index("")

        _out, _err, code = self._create(self.ITEM)

        self._assert_written_directly(code)

    def test_project_relative_path_writes_directly_in_the_backlog_folder(self):
        self.write_index("")

        _out, _err, code = self._create(f"planwise/Backlog/{self.ITEM}")

        self._assert_written_directly(code)

    def test_absolute_path_inside_the_backlog_folder_is_accepted(self):
        self.write_index("")

        _out, _err, code = self._create(str(self.backlog_dir / self.ITEM))

        self._assert_written_directly(code)

    def test_backslash_path_is_accepted(self):
        self.write_index("")

        _out, _err, code = self._create(f"planwise\\Backlog\\{self.ITEM}")

        self._assert_written_directly(code)

    def test_path_outside_the_backlog_folder_is_refused_and_names_the_expected_folder(self):
        self.write_index("")

        err = self._assert_refused_and_nothing_written("src/Some/File.cs")

        self.assertIn("src/Some/File.cs", err)
        self.assertIn("planwise/Backlog", err)

    def test_path_into_the_archive_folder_is_refused(self):
        self.write_index("")

        err = self._assert_refused_and_nothing_written(f"planwise/Backlog/Archive/{self.ITEM}")

        self.assertIn("planwise/Backlog", err)

    def test_dot_dot_escape_out_of_the_backlog_folder_is_refused(self):
        self.write_index("")

        self._assert_refused_and_nothing_written(f"planwise/Backlog/../Other/{self.ITEM}")

    def test_later_entries_keep_their_directory_parts_in_related(self):
        self.write_index("")

        _out, _err, code = self._create(f"planwise/Backlog/{self.ITEM};src/a/B.cs;docs/c.md")

        self.assertIsNone(code)
        rendered = (self.backlog_dir / self.ITEM).read_text(encoding="utf-8")
        self.assertIn(f"- [{self.ITEM}]({self.ITEM}) - file for this item", rendered)
        self.assertIn("- `src/a/B.cs` - affected file", rendered)
        self.assertIn("- `docs/c.md` - affected file", rendered)
        self.assertNotIn("[src/a/B.cs]", rendered)
        self.assertNotIn("[docs/c.md]", rendered)

    def test_help_states_the_accepted_form_of_the_first_entry(self):
        out, _err, _code = self._run_main(["--help"])

        flat = " ".join(out.split())
        self.assertIn("bare file name", flat)
        self.assertIn("directly inside the backlog folder", flat)


if __name__ == "__main__":
    unittest.main()
