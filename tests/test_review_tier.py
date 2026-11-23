"""Tests for scripts/review_tier.py: the /code-review tier of a working-tree diff.

Every case builds its own git repository under `tempfile.mkdtemp()` and
removes it in `tearDown`. Nothing is written under the plugin repo.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import config_gen
import review_tier

SCRIPT = SCRIPTS / "review_tier.py"
TEMPLATE = SCRIPTS.parent / "config.yaml.template"
BASE_SOURCES = [f"f{i}.py" for i in range(10)]
EXTRA_BASE = ["clean up.py", "über.py", "c/x.c", "s.sh", "w.ps1", "b.bat", "sub/agents/a.md", "sub/hooks/h.py"]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _lines(n, text="x = 1"):
    return "".join(f"{text}\n" for _ in range(n))


class ReviewTierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="review_tier_test_"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "t")
        _git(self.repo, "config", "core.autocrlf", "false")
        for name in [*BASE_SOURCES, *EXTRA_BASE, "README.md", "agents/x.md", "hooks/h.py"]:
            self.write(name, "base\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "init")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def append(self, name, n, text="x = 1"):
        self.write(name, "base\n" + _lines(n, text))

    def config(self, globs):
        path = self.tmp / "config.yaml"
        body = "project:\n  name: t\n"
        if globs is not None:
            body += "review_tier:\n  code_globs:\n" + "".join(f'    - "{g}"\n' for g in globs)
        path.write_bytes(body.encode("utf-8"))
        return path

    def run_tier(self, *args):
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo), *map(str, args)],
            capture_output=True, check=False,
        )
        out = proc.stdout.decode("utf-8")
        self.assertEqual(proc.returncode, 0, out + proc.stderr.decode("utf-8"))
        return dict(line.split(": ", 1) for line in out.splitlines())

    # ---- the six boundaries of the tier table

    def test_no_code_file_reads_none(self):
        self.append("README.md", 50)
        r = self.run_tier()
        self.assertEqual((r["tier"], r["code_files"], r["code_lines"]), ("none", "0", "0"))

    def test_two_files_and_one_hundred_lines_read_low(self):
        self.append("f0.py", 50)
        self.append("f1.py", 50)
        r = self.run_tier()
        self.assertEqual((r["tier"], r["code_files"], r["code_lines"]), ("low", "2", "100"))

    def test_three_files_read_medium(self):
        for name in BASE_SOURCES[:3]:
            self.append(name, 1)
        self.assertEqual(self.run_tier()["tier"], "medium")

    def test_one_file_with_one_hundred_and_one_lines_reads_medium(self):
        self.append("f0.py", 101)
        r = self.run_tier()
        self.assertEqual((r["tier"], r["code_lines"]), ("medium", "101"))

    def test_nine_files_read_high(self):
        for name in BASE_SOURCES[:9]:
            self.append(name, 1)
        self.assertEqual(self.run_tier()["tier"], "high")

    def test_five_hundred_and_one_lines_read_high(self):
        self.append("f0.py", 501)
        self.assertEqual(self.run_tier()["tier"], "high")

    def test_eight_files_and_five_hundred_lines_stay_medium(self):
        for name in BASE_SOURCES[:8]:
            self.append(name, 1)
        self.assertEqual(self.run_tier()["tier"], "medium")
        self.assertEqual(review_tier.tier_from_counts(1, 500), "medium")

    def test_deleted_lines_count_as_changed(self):
        self.write("f0.py", "")
        self.assertEqual(self.run_tier()["code_lines"], "1")

    def test_staged_changes_are_read(self):
        self.append("f0.py", 101)
        _git(self.repo, "add", "f0.py")
        self.assertEqual(self.run_tier()["tier"], "medium")

    # ---- escalators

    def test_an_escalator_raises_low_to_medium(self):
        self.append("f0.py", 1, "os.remove(path)")
        r = self.run_tier()
        self.assertEqual((r["tier"], r["escalators"]), ("medium", "file-delete"))

    def test_an_escalator_raises_medium_to_high(self):
        for name in BASE_SOURCES[:3]:
            self.append(name, 1)
        r = self.run_tier("--judged", "return-shape")
        self.assertEqual((r["tier"], r["escalators"]), ("high", "return-shape"))

    def test_an_escalator_leaves_high_at_high(self):
        self.append("f0.py", 501)
        r = self.run_tier("--judged", "deleted-symbol", "--judged", "return-shape")
        self.assertEqual((r["tier"], r["escalators"]), ("high", "deleted-symbol, return-shape"))

    def test_none_stays_none_under_an_escalator(self):
        self.append("README.md", 3)
        r = self.run_tier("--judged", "deleted-symbol")
        self.assertEqual((r["tier"], r["escalators"]), ("none", "deleted-symbol"))

    def test_each_escalator_raises_one_step(self):
        self.append("f0.py", 1, "shutil.rmtree(path)")
        self.write("new_module.py", "x = 1\n")
        r = self.run_tier()
        self.assertEqual((r["tier"], r["escalators"]), ("high", "new-module, file-delete"))

    def test_a_hook_file_escalates(self):
        self.append("hooks/h.py", 1)
        r = self.run_tier()
        self.assertEqual((r["tier"], r["escalators"]), ("medium", "hook-settings-permission"))

    def test_a_settings_file_escalates(self):
        self.write(".claude/settings.json", "{}\n")
        r = self.run_tier()
        self.assertEqual((r["tier"], r["escalators"]), ("medium", "hook-settings-permission"))

    def test_an_untracked_new_script_reads_as_added(self):
        self.write("tool.py", _lines(7))
        r = self.run_tier()
        self.assertEqual(
            (r["tier"], r["code_files"], r["code_lines"], r["escalators"]),
            ("medium", "1", "7", "new-module"),
        )

    def test_a_delete_call_in_an_untracked_file_escalates(self):
        self.write("cleanup.ps1", "Remove-Item $p\n")
        self.assertIn("file-delete", self.run_tier()["escalators"])

    def test_a_plain_word_ending_in_rm_does_not_escalate(self):
        self.append("f0.py", 1, "confirm = form ")
        self.assertEqual(self.run_tier()["escalators"], "none")

    def test_an_unknown_judged_value_is_refused(self):
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo), "--judged", "max"],
            capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 2)

    # ---- code globs from the config

    def test_an_agent_file_reads_low_with_the_glob(self):
        self.append("agents/x.md", 2)
        r = self.run_tier("--config", self.config(["agents/**"]))
        self.assertEqual((r["tier"], r["code_files"]), ("low", "1"))

    def test_an_agent_file_reads_none_without_the_glob(self):
        self.append("agents/x.md", 2)
        self.assertEqual(self.run_tier("--config", self.config(None))["tier"], "none")
        self.assertEqual(self.run_tier()["tier"], "none")

    def test_a_glob_matches_a_nested_folder(self):
        self.write("plugins/p/agents/y.md", "a\n")
        r = self.run_tier("--config", self.config(["agents/**"]))
        self.assertEqual(r["code_files"], "1")

    def test_a_missing_config_is_an_error(self):
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo), "--config", str(self.tmp / "nope.yaml")],
            capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 2)

    # ---- scope, output and help

    def test_paths_scope_the_diff(self):
        self.append("f0.py", 1)
        self.append("f1.py", 1)
        self.write("tool.py", "x = 1\n")
        r = self.run_tier("f0.py")
        self.assertEqual((r["code_files"], r["escalators"]), ("1", "none"))

    def test_output_is_four_lf_lines_in_order(self):
        self.append("f0.py", 1)
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo)], capture_output=True, check=False,
        )
        self.assertNotIn(b"\r", proc.stdout)
        keys = [line.split(":", 1)[0] for line in proc.stdout.decode("utf-8").splitlines()]
        self.assertEqual(keys, ["tier", "code_files", "code_lines", "escalators"])

    def test_help_prints_the_thresholds_from_the_constants(self):
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--help"], capture_output=True, check=False)
        out = proc.stdout.decode("utf-8")
        self.assertIn(f"at most {review_tier.LOW_MAX_LINES} lines", out)
        self.assertIn(f"more than {review_tier.MEDIUM_MAX_FILES} code files", out)

    def test_the_tier_set_never_holds_max_or_ultra(self):
        self.assertEqual(review_tier.TIERS, ("none", "low", "medium", "high"))

    # ---- regressions from the first code review

    def test_the_users_diff_config_cannot_hide_a_delete(self):
        for key, value in (("diff.mnemonicPrefix", "true"), ("diff.noprefix", "true"),
                           ("diff.external", "no-such-diff-tool")):
            with self.subTest(key=key):
                _git(self.repo, "config", key, value)
                self.append("f0.py", 1, "shutil.rmtree(p)")
                self.assertIn("file-delete", self.run_tier()["escalators"])
                _git(self.repo, "config", "--unset", key)

    def test_a_file_name_with_a_space_or_non_ascii_letter_is_read(self):
        for name in ("clean up.py", "über.py"):
            with self.subTest(name=name):
                self.append(name, 1, "os.remove(x)")
                r = self.run_tier(name)
                self.assertEqual((r["code_files"], r["escalators"]), ("1", "file-delete"))

    def test_an_added_line_starting_with_two_plus_signs_is_not_a_header(self):
        self.write("c/x.c", "base\n++ counter;\nunlink(path);\n")
        self.assertEqual(self.run_tier()["escalators"], "file-delete")

    def test_more_delete_and_move_forms_escalate(self):
        cases = {
            "s.sh": 'mv "$src" "$dst"',
            "w.ps1": "Move-Item $a $b",
            "b.bat": "del /q out.txt",
            "f0.py": "os.rmdir(d)",
            "f1.py": "os.replace(a, b)",
            "f2.py": "Path(a).rename(b)",
            "f3.py": "fs.rmSync(dir)",
        }
        for name, line in cases.items():
            with self.subTest(name=name):
                self.append(name, 1, line)
                self.assertEqual(self.run_tier(name)["escalators"], "file-delete")

    def test_a_python_del_statement_does_not_escalate(self):
        self.append("f0.py", 1, "del cache[key]")
        self.assertEqual(self.run_tier()["escalators"], "none")

    def test_a_malformed_config_exits_two(self):
        bad = self.tmp / "bad.yaml"
        bad.write_bytes(b"project:\n\tname: t\n")
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo), "--config", str(bad)],
            capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr.decode("utf-8"))
        self.assertTrue(proc.stderr.decode("utf-8").startswith("Error: config could not be read"))

    def test_a_config_that_is_a_list_reads_no_globs(self):
        lst = self.tmp / "list.yaml"
        lst.write_bytes(b"- a\n- b\n")
        self.append("agents/x.md", 1)
        self.assertEqual(self.run_tier("--config", lst)["tier"], "none")

    def test_a_subfolder_repo_reads_tracked_and_untracked_paths_alike(self):
        self.append("sub/agents/a.md", 1)
        self.write("sub/agents/b.md", "b\n")
        self.append("sub/hooks/h.py", 1)
        self.append("f0.py", 1)  # outside --repo, so not read
        cfg = self.config(["agents/**"])
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo / "sub"), "--config", str(cfg)],
            capture_output=True, check=False,
        )
        r = dict(line.split(": ", 1) for line in proc.stdout.decode("utf-8").splitlines())
        self.assertEqual((r["code_files"], r["escalators"]), ("3", "hook-settings-permission"))

    def test_a_double_star_slash_glob_matches_a_top_level_file(self):
        self.append("README.md", 1)
        self.assertEqual(self.run_tier("--config", self.config(["**/*.md"]))["code_files"], "1")

    def test_a_repository_with_no_commit_reads_against_the_empty_tree(self):
        fresh = self.tmp / "fresh"
        fresh.mkdir()
        _git(fresh, "init", "-q", "-b", "main")
        _git(fresh, "config", "core.autocrlf", "false")
        (fresh / "a.py").write_bytes(b"x = 1\n")
        (fresh / "b.py").write_bytes(b"y = 2\n")
        _git(fresh, "add", "a.py")
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--repo", str(fresh)], capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
        self.assertIn(b"code_files: 2\n", proc.stdout)


class GlobAndLineTests(unittest.TestCase):
    def test_added_lines_skip_every_header_shape(self):
        patch = "diff --git w/a.py w/a.py\n--- i/a.py\n+++ w/a.py\n@@ -1,0 +2,2 @@\n+++ x\n+y\n"
        self.assertEqual(review_tier.added_lines(patch), ["++ x", "y"])

    def test_double_star_slash_matches_zero_folders(self):
        rx = [review_tier._glob_regex("**/*.md")]
        self.assertTrue(review_tier._glob_matches("README.md", rx))
        self.assertTrue(review_tier._glob_matches("docs/a/README.md", rx))
        self.assertFalse(review_tier._glob_matches("README.txt", rx))


class ReviewTierConfigTests(unittest.TestCase):
    def test_the_template_carries_an_empty_glob_list(self):
        block = config_gen.extract_top_level_block(TEMPLATE.read_text(encoding="utf-8"), "review_tier")
        self.assertIsNotNone(block)
        self.assertIn("  code_globs: []", block.splitlines())

    def test_migrate_adds_the_block(self):
        self.assertIn("review_tier", config_gen.MIGRATABLE_TOP_LEVEL_KEYS)


if __name__ == "__main__":
    unittest.main()
