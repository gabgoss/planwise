"""Tests for the idempotent `.gitignore` draft entry and its init/upgrade wiring."""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import artifact_upgrade as au
import gitignore_entry as ge
import init_project as ip

DATE_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
DRAFT_LINE = f"planwise/feedback-drafts/{DATE_GLOB}-draft-*.md"


class LineStateTest(unittest.TestCase):
    """`line_state` and `read_state`: the predicate `ensure_line` writes by and
    the read-only form a checker such as doctor calls."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / ".gitignore"

    def test_classifies_each_state(self):
        line = DRAFT_LINE.encode()
        cases = {
            b"": "absent",
            b"dist/\n": "absent",
            line + b"\n": "present",
            line + b"  \r\n": "present",
            b"!" + line + b"\n": "negated",
            b"!" + line + b"  \r\n": "negated",
            line + b"-extra\n": "absent",
            b"# " + line + b"\n": "absent",
        }
        for data, expected in cases.items():
            with self.subTest(data=data):
                self.assertEqual(ge.line_state(data, DRAFT_LINE), expected)

    def test_the_later_of_a_line_and_its_negation_decides(self):
        line = DRAFT_LINE.encode()
        self.assertEqual(ge.line_state(line + b"\n!" + line + b"\n", DRAFT_LINE), "negated")
        self.assertEqual(ge.line_state(b"!" + line + b"\n" + line + b"\n", DRAFT_LINE), "present")

    def test_ensure_line_writes_exactly_when_the_state_is_absent(self):
        line = DRAFT_LINE.encode()
        for data in (b"", b"dist/\n", line + b"\n", b"!" + line + b"\n", line + b"\n!" + line, b"x" + line):
            with self.subTest(data=data):
                self.path.write_bytes(data)
                state = ge.read_state(self.path, DRAFT_LINE)
                self.assertEqual(ge.ensure_line(self.path, DRAFT_LINE), state == "absent")

    def test_a_missing_file_reads_as_absent_and_is_not_created(self):
        self.assertEqual(ge.read_state(self.path, DRAFT_LINE), "absent")
        self.assertFalse(self.path.exists())

    def test_read_state_leaves_the_bytes_alone(self):
        for original in (b"dist/\n*.log", b"a\r\nb", DRAFT_LINE.encode(), b""):
            with self.subTest(original=original):
                self.path.write_bytes(original)
                ge.read_state(self.path, DRAFT_LINE)
                self.assertEqual(self.path.read_bytes(), original)


class EnsureLineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / ".gitignore"

    def test_creates_file_with_lf_and_exactly_one_line(self):
        self.assertTrue(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertEqual(self.path.read_bytes(), DRAFT_LINE.encode() + b"\n")

    def test_appends_once_and_keeps_existing_lines_in_order(self):
        self.path.write_bytes(b"node_modules/\n*.log\n")
        self.assertTrue(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertEqual(
            self.path.read_bytes(), b"node_modules/\n*.log\n" + DRAFT_LINE.encode() + b"\n"
        )

    def test_second_call_is_idempotent_bytes_identical(self):
        self.path.write_bytes(b"node_modules/\n")
        ge.ensure_line(self.path, DRAFT_LINE)
        first = self.path.read_bytes()
        self.assertFalse(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertEqual(self.path.read_bytes(), first)

    def test_existing_line_with_trailing_whitespace_counts_as_present(self):
        original = DRAFT_LINE.encode() + b"  \r\n"
        self.path.write_bytes(original)
        self.assertFalse(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertEqual(self.path.read_bytes(), original)

    def test_crlf_file_stays_crlf_and_gains_a_crlf_line(self):
        self.path.write_bytes(b"a\r\nb\r\n")
        self.assertTrue(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertEqual(self.path.read_bytes(), b"a\r\nb\r\n" + DRAFT_LINE.encode() + b"\r\n")

    def test_missing_trailing_newline_gets_one_before_the_appended_line(self):
        self.path.write_bytes(b"a\nb")
        self.assertTrue(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertEqual(self.path.read_bytes(), b"a\nb\n" + DRAFT_LINE.encode() + b"\n")

    def test_missing_trailing_newline_in_crlf_file_uses_crlf(self):
        self.path.write_bytes(b"a\r\nb")
        self.assertTrue(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertEqual(self.path.read_bytes(), b"a\r\nb\r\n" + DRAFT_LINE.encode() + b"\r\n")

    def test_negated_line_is_an_opt_out_and_file_stays_byte_identical(self):
        original = b"dist/\n!" + DRAFT_LINE.encode() + b"\n"
        self.path.write_bytes(original)
        self.assertFalse(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertEqual(self.path.read_bytes(), original)

    def test_negated_line_with_trailing_whitespace_and_crlf_is_an_opt_out(self):
        original = b"!" + DRAFT_LINE.encode() + b"  \r\n"
        self.path.write_bytes(original)
        self.assertFalse(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertEqual(self.path.read_bytes(), original)

    def test_write_leaves_no_temp_file_behind(self):
        self.path.write_bytes(b"dist/\n")
        ge.ensure_line(self.path, DRAFT_LINE)
        self.assertEqual(os.listdir(self.path.parent), [".gitignore"])

    def test_append_keeps_the_original_bytes_as_an_exact_prefix(self):
        for original in (b"dist/\n", b"a\r\nb", b"x\r\ny\r\n", b""):
            with self.subTest(original=original):
                self.path.write_bytes(original)
                self.assertTrue(ge.ensure_line(self.path, DRAFT_LINE))
                result = self.path.read_bytes()
                self.assertTrue(result.startswith(original))
                self.assertTrue(result.endswith(DRAFT_LINE.encode() + (b"\r\n" if b"\r\n" in original else b"\n")))

    def test_append_to_a_symlinked_gitignore_keeps_the_link_and_writes_the_target(self):
        target = self.path.parent / "shared-ignore"
        target.write_bytes(b"dist/\n")
        try:
            os.symlink(target, self.path)
        except (OSError, NotImplementedError, AttributeError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        self.assertTrue(ge.ensure_line(self.path, DRAFT_LINE))
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_bytes(), b"dist/\n" + DRAFT_LINE.encode() + b"\n")

    @unittest.skipIf(os.name == "nt", "POSIX file modes only")
    def test_new_file_gets_the_mode_a_plain_open_creates(self):
        plain = self.path.parent / "plain"
        with open(plain, "wb"):
            pass
        ge.ensure_line(self.path, DRAFT_LINE)
        self.assertEqual(self.path.stat().st_mode & 0o777, plain.stat().st_mode & 0o777)

    @unittest.skipIf(os.name == "nt", "POSIX file modes only")
    def test_append_keeps_the_existing_file_mode(self):
        self.path.write_bytes(b"dist/\n")
        os.chmod(self.path, 0o640)
        ge.ensure_line(self.path, DRAFT_LINE)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)

    def test_model_draft_line_renders_project_values(self):
        self.assertEqual(ge.model_draft_line("planwise", "feedback-drafts"), DRAFT_LINE)

    def test_model_draft_line_refuses_a_path_a_pattern_cannot_express(self):
        for root, sub in (
            ("planwise", "C:/shared/Feedback"),
            ("planwise", "\\\\server\\share\\Feedback"),
            ("planwise", "/abs/Feedback"),
            ("planwise", "../Feedback"),
            ("planwise", "a/../b"),
            ("planwise", "Feed[back]"),
            ("planwise", "a*b"),
            ("planwise", "a?b"),
            ("!planwise", "Feedback"),
            ("#planwise", "Feedback"),
            ("planwise", ""),
        ):
            with self.subTest(root=root, sub=sub), self.assertRaises(ValueError):
                ge.model_draft_line(root, sub)

    def test_model_draft_line_accepts_a_nested_relative_directory(self):
        self.assertEqual(
            ge.model_draft_line("planwise", "a/b"),
            f"planwise/a/b/{DATE_GLOB}-draft-*.md",
        )

    def test_model_draft_line_uses_forward_slashes(self):
        self.assertEqual(
            ge.model_draft_line("plan\\wise", "Feedback\\sub"),
            f"plan/wise/Feedback/sub/{DATE_GLOB}-draft-*.md",
        )


class DraftGlobTest(unittest.TestCase):
    MODEL_DRAFT = "planwise/feedback-drafts/2026-10-13-draft-bug-x.md"
    USER_DRAFT = "planwise/feedback-drafts/2026-10-13-bug-draft-index-stale.md"

    def test_rendered_line_anchors_draft_directly_after_the_date(self):
        rendered = ge.model_draft_line("planwise", "feedback-drafts")
        self.assertEqual(rendered, DRAFT_LINE)
        self.assertTrue(rendered.endswith(f"/{DATE_GLOB}-draft-*.md"))
        self.assertNotEqual(rendered, "planwise/feedback-drafts/*-draft-*.md")

    @unittest.skipUnless(shutil.which("git"), "requires git to evaluate the pattern")
    def test_git_ignores_a_model_draft_and_keeps_a_user_draft_with_draft_in_the_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            ge.ensure_line(repo / ".gitignore", ge.model_draft_line("planwise", "feedback-drafts"))
            drafts = repo / "planwise" / "feedback-drafts"
            drafts.mkdir(parents=True)
            for rel in (self.MODEL_DRAFT, self.USER_DRAFT):
                (repo / rel).write_text("x", encoding="utf-8")

            def ignored(rel):
                return subprocess.run(
                    ["git", "-C", str(repo), "check-ignore", "-q", rel], check=False
                ).returncode == 0

            self.assertTrue(ignored(self.MODEL_DRAFT))
            self.assertFalse(ignored(self.USER_DRAFT))


def _make_cfg(project_root: Path, **overrides):
    plugin_root = Path(ip.__file__).resolve().parent.parent
    kwargs = {
        "project_name": "TestProject",
        "project_root": project_root,
        "plugin_root": plugin_root,
        "planwise_root": "planwise",
        "plans_dir": "Plans",
        "backlog_dir": "Backlog",
        "lessons_dir": "LessonsLearned",
        "feedback_dir": "feedback-drafts",
        "install_scope": ip.InstallScope.PROJECT,
        "plan_tier": "pro",
        "plugin_version": "0.0.0",
        "token_saver": False,
    }
    kwargs.update(overrides)
    return ip.InitConfig(**kwargs)


class InitWiringTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_init_flow_writes_draft_line_and_second_run_is_byte_identical(self):
        cfg = _make_cfg(self.root)
        (self.root / ".gitignore").write_bytes(b"dist/\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ip.create_directories(cfg)
            ip._ensure_draft_gitignore(cfg, cfg.feedback_dir)
        first = (self.root / ".gitignore").read_bytes()
        self.assertEqual(first, b"dist/\n" + DRAFT_LINE.encode() + b"\n")
        self.assertIn("added draft entry", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as out2:
            ip._ensure_draft_gitignore(cfg, cfg.feedback_dir)
        self.assertEqual((self.root / ".gitignore").read_bytes(), first)
        self.assertIn("already present", out2.getvalue())

    def test_init_calls_the_defining_module_helper_with_the_draft_line(self):
        cfg = _make_cfg(self.root)
        with mock.patch("gitignore_entry.ensure_line") as patched, mock.patch.object(
            ip, "ensure_line", patched
        ), contextlib.redirect_stdout(io.StringIO()):
            ip._ensure_draft_gitignore(cfg, cfg.feedback_dir)
        patched.assert_called_once_with(self.root / ".gitignore", DRAFT_LINE)

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to read the config")
    def test_migrate_flow_writes_the_draft_line_for_the_repointed_directory(self):
        planwise_dir = self.root / "planwise"
        legacy = planwise_dir / "feedback-drafts"
        legacy.mkdir(parents=True)
        (legacy / "note.md").write_text("hi", encoding="utf-8")
        (planwise_dir / "config.yaml").write_text(
            'project:\n  name: "TestProject"\n  plans_dir: Plans\n'
            "  backlog_dir: Backlog\n  lessons_dir: LessonsLearned\n",
            encoding="utf-8",
        )
        cfg = _make_cfg(self.root, feedback_dir="Feedback")
        config_path = planwise_dir / "config.yaml"
        with mock.patch.object(
            ip, "migrate_config", return_value=(str(config_path), [], [])
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ip._run_migrate(cfg), 0)
            first = (self.root / ".gitignore").read_bytes()
            self.assertEqual(ip._run_migrate(cfg), 0)
        self.assertEqual(first, DRAFT_LINE.encode() + b"\n")
        self.assertEqual((self.root / ".gitignore").read_bytes(), first)


    def test_an_unrepresentable_feedback_dir_warns_and_writes_nothing(self):
        cfg = _make_cfg(self.root)
        for bad in ("C:/shared/Feedback", "/abs/Feedback", "../Feedback", "Feed[back]", "a/*/b"):
            with self.subTest(bad=bad):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    ip._ensure_draft_gitignore(cfg, bad)
                self.assertIn("warning", out.getvalue())
                self.assertNotIn("added draft entry", out.getvalue())
                self.assertFalse((self.root / ".gitignore").exists())

    def test_unwritable_gitignore_prints_a_warning_and_does_not_raise(self):
        cfg = _make_cfg(self.root)
        (self.root / ".gitignore").mkdir()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ip._ensure_draft_gitignore(cfg, cfg.feedback_dir)
        self.assertIn("warning", out.getvalue())
        self.assertIn(str(self.root / ".gitignore"), out.getvalue())


class ConfiguredFeedbackDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for patcher in (
            mock.patch.object(Path, "home", return_value=self.root),
            mock.patch.dict(os.environ, {"HOME": str(self.root), "USERPROFILE": str(self.root)}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run_init(self):
        argv = ["init_project.py", "--name", "TestProject", "--project-root", str(self.root)]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            try:
                ip.main()
            except SystemExit as exc:
                self.assertIn(exc.code, (0, None))

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to read the config")
    def test_plain_init_follows_the_feedback_dir_in_an_existing_config(self):
        planwise_dir = self.root / "planwise"
        planwise_dir.mkdir()
        (planwise_dir / "config.yaml").write_text(
            'project:\n  name: "TestProject"\n  lessons_dir: LessonsLearned\n'
            '  feedback_dir: "feedback-drafts"\n',
            encoding="utf-8",
        )
        self._run_init()
        text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(DRAFT_LINE, text.splitlines())
        self.assertNotIn("planwise/Feedback/", text)

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to read the config")
    def test_non_string_feedback_dir_resolves_to_the_loader_default(self):
        planwise_dir = self.root / "planwise"
        planwise_dir.mkdir()
        (planwise_dir / "config.yaml").write_text(
            'project:\n  name: "TestProject"\n  feedback_dir: 2026\n', encoding="utf-8"
        )
        self._run_init()
        text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(f"planwise/Feedback/{DATE_GLOB}-draft-*.md", text.splitlines())
        self.assertNotIn("2026", text)

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to read the config")
    def test_resolver_applies_the_loader_acceptance_rule(self):
        cfg = _make_cfg(self.root, feedback_dir="cli-dir")
        config_path = self.root / "config.yaml"
        cases = (
            ("feedback_dir: 2026", "Feedback"),
            ("feedback_dir: [a, b]", "Feedback"),
            ('feedback_dir: ""', "Feedback"),
            ("feedback_dir: ", "Feedback"),
            ("feedback_dir: mydir", "mydir"),
            ("name: x", "Feedback"),
        )
        for line, expected in cases:
            with self.subTest(line=line):
                config_path.write_text(f"project:\n  {line}\n", encoding="utf-8")
                self.assertEqual(ip._configured_feedback_rel(cfg, config_path), expected)
        config_path.write_text("project: just-a-string\n", encoding="utf-8")
        self.assertEqual(ip._configured_feedback_rel(cfg, config_path), "Feedback")

    def test_resolver_equals_the_loader_for_every_readable_config(self):
        import config_loader

        cfg = _make_cfg(self.root, feedback_dir="cli-dir")
        planwise_dir = self.root / "planwise"
        planwise_dir.mkdir()
        config_path = planwise_dir / "config.yaml"
        bodies = (
            "project:\n  name: x\n  feedback_dir: mydir\n",
            "project:\n  name: x\n",
            "project:\n  name: x\n  feedback_dir: nested/dir\n",
            "other: 1\n",
        )
        for body in bodies:
            with self.subTest(body=body):
                config_path.write_text(body, encoding="utf-8")
                loaded = config_loader.load_config(config_path=config_path)
                expected = Path(loaded["_feedback_dir"]).relative_to(planwise_dir).as_posix()
                self.assertEqual(ip._configured_feedback_rel(cfg, config_path), expected)

    def test_resolver_falls_back_to_the_cli_value_without_a_config(self):
        cfg = _make_cfg(self.root, feedback_dir="Feedback")
        self.assertEqual(
            ip._configured_feedback_rel(cfg, self.root / "planwise" / "config.yaml"), "Feedback"
        )


class UpgradeWiringTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    @unittest.skipUnless(au.HAS_YAML, "requires PyYAML to read the config")
    def test_upgrade_writes_draft_line_and_second_run_is_byte_identical(self):
        planwise_dir = self.root / "planwise"
        planwise_dir.mkdir()
        config_path = planwise_dir / "config.yaml"
        config_path.write_text(
            'project:\n  name: "TestProject"\n  lessons_dir: LessonsLearned\n'
            '  feedback_dir: "feedback-drafts"\n',
            encoding="utf-8",
        )
        cfg = _make_cfg(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            au._apply_feedback_dir(cfg, config_path)
        gitignore = self.root / ".gitignore"
        first = gitignore.read_bytes()
        self.assertEqual(first, DRAFT_LINE.encode() + b"\n")
        with contextlib.redirect_stdout(io.StringIO()):
            au._apply_feedback_dir(cfg, config_path)
        self.assertEqual(gitignore.read_bytes(), first)

    @unittest.skipUnless(au.HAS_YAML, "requires PyYAML to read the config")
    def test_upgrade_passes_the_draft_line_to_the_helper(self):
        planwise_dir = self.root / "planwise"
        planwise_dir.mkdir()
        config_path = planwise_dir / "config.yaml"
        config_path.write_text(
            'project:\n  name: "TestProject"\n  lessons_dir: LessonsLearned\n'
            '  feedback_dir: "feedback-drafts"\n',
            encoding="utf-8",
        )
        cfg = _make_cfg(self.root)
        with mock.patch.object(ip, "ensure_line", return_value=False) as patched, \
                contextlib.redirect_stdout(io.StringIO()):
            au._apply_feedback_dir(cfg, config_path)
        patched.assert_called_once_with(self.root / ".gitignore", DRAFT_LINE)

    @unittest.skipUnless(au.HAS_YAML, "requires PyYAML to read the config")
    def test_upgrade_with_a_scalar_project_block_does_not_raise(self):
        planwise_dir = self.root / "planwise"
        planwise_dir.mkdir()
        config_path = planwise_dir / "config.yaml"
        config_path.write_text("project: just-a-string\n", encoding="utf-8")
        cfg = _make_cfg(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            au._apply_feedback_dir(cfg, config_path)
        # A scalar `project:` block gives the loader's default directory, so the
        # upgrade creates and ignores the directory the drafts helper will use.
        self.assertTrue((planwise_dir / "Feedback").is_dir())
        self.assertEqual(
            (self.root / ".gitignore").read_bytes(),
            f"planwise/Feedback/{DATE_GLOB}-draft-*.md\n".encode(),
        )

    @unittest.skipUnless(au.HAS_YAML, "requires PyYAML to read the config")
    def test_upgrade_with_a_non_string_feedback_dir_uses_the_default_directory(self):
        planwise_dir = self.root / "planwise"
        planwise_dir.mkdir()
        config_path = planwise_dir / "config.yaml"
        config_path.write_text(
            'project:\n  name: "TestProject"\n  feedback_dir: 2026\n', encoding="utf-8"
        )
        cfg = _make_cfg(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            au._apply_feedback_dir(cfg, config_path)
        self.assertTrue((planwise_dir / "Feedback").is_dir())
        self.assertFalse((planwise_dir / "2026").exists())
        self.assertEqual(
            (self.root / ".gitignore").read_bytes(),
            f"planwise/Feedback/{DATE_GLOB}-draft-*.md".encode() + b"\n",
        )

    @unittest.skipUnless(au.HAS_YAML, "requires PyYAML to read the config")
    def test_upgrade_with_unwritable_gitignore_warns_and_does_not_raise(self):
        planwise_dir = self.root / "planwise"
        planwise_dir.mkdir()
        config_path = planwise_dir / "config.yaml"
        config_path.write_text(
            'project:\n  name: "TestProject"\n  lessons_dir: LessonsLearned\n'
            '  feedback_dir: "feedback-drafts"\n',
            encoding="utf-8",
        )
        (self.root / ".gitignore").mkdir()
        cfg = _make_cfg(self.root)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            au._apply_feedback_dir(cfg, config_path)
        self.assertIn("warning", out.getvalue())


if __name__ == "__main__":
    unittest.main()
