"""Tests for the measurement-rule lint checks in ``lint_gate_checks_measure``.

Each check gets one known-bad fixture that must produce a finding naming it (the
mutation control) and the same fixture repaired, which must produce none for it (the
positive control). The fixtures are built in temporary directories.
"""

import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_gate_checks_measure as measure_module
import lint_verification_gates as lint_module
from lint_verification_gates import lint_plan

KIB_TEN = "x" * 10240  # a 10.0 KiB file


def _task(context_rows=(), verification=""):
    rows = "".join(f"{row}\n" for row in context_rows)
    table = "| Priority | File | KiB | ~Tokens | Purpose |\n|---|---|---:|---:|---|\n" + rows if rows else ""
    return (
        "# Task: Fixture\n\n"
        "**Output:** `out/result.md`\n\n"
        "## Objective\n\nDo the work.\n\n"
        f"## Required Context\n\n{table}\n"
        "## Execution Steps\n\n1. Read the file.\n\n"
        f"{verification}"
    )


def _verification(before="", after=""):
    return (
        "## Verification Commands\n\n"
        f"**Before (runner):**\n```\n{before}\n```\n"
        f"**After (runner):**\n```\n{after}\n```\n"
    )


def _lint(check, text, files=None, name="TASK-01-Fixture.md"):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / name).write_text(text, encoding="utf-8", newline="\n")
        for rel, body in (files or {}).items():
            target = Path(tmp) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8", newline="\n")
        with redirect_stderr(StringIO()):
            return [f for f in lint_plan(Path(tmp), execute=False) if f["check"] == check]


def _context(root: Path):
    class _Context:
        plan_root = root

        def markdown_files(self):
            return sorted(p for p in root.rglob("*.md") if p.is_file())

    return _Context()


class TestCheck48RequiredContextSize(unittest.TestCase):
    def _row(self, cell="`data.md` — whole", kib="10.0", tokens="—"):
        return f"| 1 | {cell} | {kib} | {tokens} | purpose |"

    def test_bad_size_miss_above_tolerance(self):
        findings = _lint(48, _task([self._row(kib="2.0")]), files={"data.md": KIB_TEN})
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(48, "WARNING")])

    def test_good_size_matches(self):
        self.assertEqual(_lint(48, _task([self._row(kib="10.0")]), files={"data.md": KIB_TEN}), [])

    def test_good_size_inside_tolerance(self):
        self.assertEqual(_lint(48, _task([self._row(kib="9.0")]), files={"data.md": KIB_TEN}), [])

    def test_whole_in_the_kib_cell_is_a_whole_file_row(self):
        findings = _lint(48, _task([self._row(cell="`data.md`", kib="2.0 (whole)")]), files={"data.md": KIB_TEN})
        self.assertEqual(len(findings), 1)

    def test_section_slice_row_is_out_of_reach(self):
        for cell, kib in (
            ("`data.md` — §2 only", "2.0"),
            ("`data.md` — by `Grep`, then `offset`/`limit`", "2.0"),
            ("`data.md`", "2.0 (slice of 10.0 whole)"),
        ):
            findings = _lint(48, _task([self._row(cell=cell, kib=kib)]), files={"data.md": KIB_TEN})
            self.assertEqual(findings, [], (cell, kib))

    def test_tokens_used_only_when_kib_is_empty(self):
        bad = _lint(48, _task([self._row(kib="—", tokens="~1.0K")]), files={"data.md": KIB_TEN})
        self.assertEqual(len(bad), 1)
        both = _lint(48, _task([self._row(kib="10.0", tokens="~1.0K")]), files={"data.md": KIB_TEN})
        self.assertEqual(both, [])

    def test_project_root_path_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cloned-repos" / "x").mkdir(parents=True)
            (root / "cloned-repos" / "x" / "big.md").write_text(KIB_TEN, encoding="utf-8")
            plan = root / "plan"
            plan.mkdir()
            (plan / "TASK-01-Fixture.md").write_text(
                _task([self._row(cell="`cloned-repos/x/big.md` — whole", kib="2.0")]), encoding="utf-8", newline="\n"
            )
            summary = measure_module.measure_summary(_context(plan))
        self.assertEqual((summary["examined"], summary["skipped"], summary["measured"]), (1, 0, 1))

    def test_summary_line_counts_skipped_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data.md").write_text(KIB_TEN, encoding="utf-8")
            (Path(tmp) / "TASK-01-Fixture.md").write_text(
                _task([self._row(), self._row(cell="`missing.md` — whole")]), encoding="utf-8", newline="\n"
            )
            summary = measure_module.measure_summary(_context(Path(tmp)))
        self.assertEqual(summary["line"], "rows examined 2, skipped 1 (unresolved), measured 1")

    def test_zero_measured_reads_not_checked_never_clean(self):
        findings = _lint(48, _task([self._row(cell="`missing.md` — whole")]))
        self.assertEqual([f["severity"] for f in findings], ["UNCERTAIN"])
        self.assertIn("NOT CHECKED", findings[0]["message"])

    def test_no_rows_is_silent(self):
        self.assertEqual(_lint(48, _task()), [])

    def test_summary_is_written_to_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data.md").write_text(KIB_TEN, encoding="utf-8")
            (Path(tmp) / "TASK-01-Fixture.md").write_text(_task([self._row()]), encoding="utf-8", newline="\n")
            captured = StringIO()
            with redirect_stderr(captured):
                lint_plan(Path(tmp), execute=False)
        self.assertIn("rows examined 1, skipped 0 (unresolved), measured 1", captured.getvalue())


class TestCheck49DiffMatcherWithoutCounts(unittest.TestCase):
    BAD = "git diff 1bc4e0a -- a.md | grep -c '^+[^+]'"
    NAME_ONLY = "git diff --name-only 1bc4e0a -- a.md | wc -l"
    PORCELAIN = "git status --porcelain -- a.md | grep -c '^??'"

    def test_bad_matcher_without_counts(self):
        findings = _lint(49, _task(verification=_verification(after=self.BAD)))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(49, "ERROR")])

    def test_good_with_name_only_count(self):
        text = _task(verification=_verification(after=f"{self.BAD}\n{self.NAME_ONLY}"))
        self.assertEqual(_lint(49, text), [])

    def test_good_with_porcelain_count(self):
        text = _task(verification=_verification(after=f"{self.BAD}\n{self.PORCELAIN}"))
        self.assertEqual(_lint(49, text), [])

    def test_count_in_another_block_does_not_count(self):
        text = _task(verification=_verification(before=self.NAME_ONLY, after=self.BAD))
        self.assertEqual(len(_lint(49, text)), 1)

    def test_diff_without_a_matcher_is_not_read(self):
        self.assertEqual(_lint(49, _task(verification=_verification(after="git diff --stat 1bc4e0a -- a.md"))), [])

    def test_wrong_line_is_skipped(self):
        self.assertEqual(_lint(49, _task(verification=_verification(after=f"# WRONG {self.BAD}"))), [])


class TestCheck50BaseGate(unittest.TestCase):
    NUMSTAT = "git diff --numstat $X_BASE -- a.md"
    RESOLVE = "git cat-file -e $X_BASE"
    COUNT = "git diff --name-only $X_BASE -- a.md | wc -l"

    def test_bad_base_without_resolve_step(self):
        findings = _lint(50, _task(verification=_verification(after=f"{self.NUMSTAT}\n{self.COUNT}")))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(50, "WARNING")])
        self.assertIn("cat-file -e", findings[0]["message"])

    def test_good_base_with_resolve_and_count(self):
        text = _task(verification=_verification(before=self.RESOLVE, after=f"{self.NUMSTAT}\n{self.COUNT}"))
        self.assertEqual(_lint(50, text), [])

    def test_angle_bracket_operand_is_read(self):
        text = _task(verification=_verification(after=f"git diff --numstat <X_BASE> -- a.md\n{self.COUNT}"))
        self.assertEqual(len(_lint(50, text)), 1)

    def test_bad_literal_base_placeholder(self):
        text = _task(verification=_verification(before=self.RESOLVE, after="git diff --numstat {BASE} -- a.md"))
        findings = [f for f in _lint(50, text) if "{BASE}" in f["message"]]
        self.assertEqual(len(findings), 1)

    def test_bad_base_diff_without_spanned_file_count(self):
        text = _task(verification=_verification(before=self.RESOLVE, after=self.NUMSTAT))
        findings = _lint(50, text)
        self.assertEqual(len(findings), 1)
        self.assertIn("spanned-file count", findings[0]["message"])

    def test_good_with_porcelain_count_instead(self):
        text = _task(verification=_verification(
            before=self.RESOLVE, after=f"{self.NUMSTAT}\ngit status --porcelain -- a.md | grep -c '^??'"
        ))
        self.assertEqual(_lint(50, text), [])

    def test_diff_reported_by_check_49_is_not_reported_again(self):
        text = _task(verification=_verification(before=self.RESOLVE, after="git diff $X_BASE -- a.md | grep -c '^+'"))
        self.assertEqual(_lint(50, text), [])
        self.assertEqual(len(_lint(49, text)), 1)

    def test_a_non_task_file_is_not_read(self):
        text = "# Notes\n\n" + _verification(after=self.NUMSTAT)
        self.assertEqual(_lint(50, text, name="Notes.md"), [])


class TestCheck51CharCountInByteIdentity(unittest.TestCase):
    BAD = "PRE=$(awk '/^Last/ {print length($0)}' a.md)\n[ \"$PRE\" -eq \"$POST\" ]"
    GOOD = "PRE=$(wc -c < a.md)\n[ \"$PRE\" -eq \"$POST\" ]"

    def test_bad_awk_length_in_byte_equality(self):
        findings = _lint(51, _task(verification=_verification(after=self.BAD)))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(51, "ERROR")])
        self.assertIn("measure-aggregate-provenance.md", findings[0]["message"])

    def test_good_byte_instrument(self):
        self.assertEqual(_lint(51, _task(verification=_verification(after=self.GOOD))), [])

    def test_bad_shell_length_operand(self):
        after = "N=${#TEXT}\n[ \"$N\" -eq 58562 ]"
        self.assertEqual(len(_lint(51, _task(verification=_verification(after=after)))), 1)

    def test_bad_len_over_decoded_string(self):
        after = "python -c \"print(len(open('a.md').read()))\"\ntest \"$A\" == \"$B\""
        self.assertEqual(len(_lint(51, _task(verification=_verification(after=after)))), 1)

    def test_good_len_over_raw_bytes(self):
        after = "python -c \"print(len(open('a.md','rb').read()))\"\ntest \"$A\" == \"$B\""
        self.assertEqual(_lint(51, _task(verification=_verification(after=after))), [])

    def test_good_operand_without_an_equality_assertion(self):
        after = "awk '{print length($0)}' a.md"
        self.assertEqual(_lint(51, _task(verification=_verification(after=after))), [])

    def test_good_array_count_is_not_a_string_length(self):
        after = "N=${#FILES[@]}\n[ \"$N\" -eq 3 ]"
        self.assertEqual(_lint(51, _task(verification=_verification(after=after))), [])

    # A real plan line (ZeroCallPlan, SKILL.md size gate) with the raw read swapped for a text-mode read.
    SKILL = "cloned-repos/planwise/plugins/planwise/skills/planwise/SKILL.md"
    RAW_LEN = f"python -c \"import sys; print(len(open(sys.argv[1],'rb').read()))\" {SKILL}"
    DECODED_LEN = RAW_LEN.replace("'rb'", "encoding='utf-8'")
    EQ = "[ \"$A\" -eq \"$B\" ]"

    def _count(self, after):
        return len(_lint(51, _task(verification=_verification(after=after))))

    def test_bad_len_decoded_beside_wc_c_two_commands(self):
        after = f"{self.DECODED_LEN}\nwc -c < {self.SKILL}\n{self.EQ}"
        self.assertEqual(self._count(after), 1)

    def test_bad_len_decoded_and_wc_c_one_command(self):
        after = f"[ \"$({self.DECODED_LEN})\" -eq \"$(wc -c < {self.SKILL})\" ]"
        self.assertEqual(self._count(after), 1)

    def test_bad_len_over_bound_decoded_name(self):
        after = "python -c \"t=open('a.md',encoding='utf-8').read(); print(len(t))\"\n" + self.EQ
        self.assertEqual(self._count(after), 1)

    def test_bad_len_over_text_mode_run_stdout(self):
        after = (
            "python -c \"import subprocess; r=subprocess.run(['git','show','HEAD:a.md'],"
            "capture_output=True,text=True); print(len(r.stdout))\"\n"
            "[ \"$A\" -eq \"$(wc -c < a.md)\" ]"
        )
        self.assertEqual(self._count(after), 1)

    def test_good_len_over_encoded_text(self):
        after = "python -c \"print(len(open('a.md',encoding='utf-8').read().encode('utf-8')))\"\n" + self.EQ
        self.assertEqual(self._count(after), 0)

    def test_good_len_over_raw_bytes_run(self):
        after = (
            "python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'x.py'],capture_output=True); "
            "d=r.stdout; print('bytes',len(d),len(r.stderr))\""
        )
        self.assertEqual(self._count(after), 0)

    def test_good_len_over_list_literal(self):
        after = "python -c \"L=['A','B']; print('labels', len(L))\"\n[ \"$A\" == \"$B\" ]"
        self.assertEqual(self._count(after), 0)

    def test_good_len_over_findall(self):
        after = (
            "python -c \"import re,sys; p=open(sys.argv[1],encoding='utf-8').read(); "
            "print(len(re.findall('x',p))==1)\" a.md"
        )
        self.assertEqual(self._count(after), 0)

    def test_good_len_over_walk_names(self):
        after = (
            "python -I -c \"import os,sys; n=sum(len(f) for _,_,f in os.walk(sys.argv[1])); "
            "print('walked',n,'files')\" lab\n" + self.EQ
        )
        self.assertEqual(self._count(after), 0)

    def test_good_len_over_split_words(self):
        after = "python -c \"print(len(open('f.md').read().split()))\"\n[ \"$A\" -eq 7 ]"
        self.assertEqual(self._count(after), 0)

    # The eight commands the gate linter flagged over the HeadlessPromptToolMeasure plan on 2026-11-21.
    # Each counts items or raw bytes, so none reports Check 51.
    REAL_PLAN_COMMANDS = (
        "C:/Python314/python.exe -B -c \"import re,sys; t=open(sys.argv[1],encoding='utf-8').read(); b={(m.group(1),m.group(2)):m.group(3).strip() for m in re.finditer(r'^BASELINE (\\S+) (before|after): (.*)$',t,re.M)}; arms={a for a,_ in b}; print('baselines equal', sum(b.get((a,'before'))==b.get((a,'after')) is not None for a in arms), 'of', len(arms))\" planwise/Plans/HeadlessPromptToolMeasure/Sprint-01-PromptToolDriver/Session-01-ServerFlagAndGrader/Outputs/HPT-S01-01-03-ProbeFlagProof.md",
        "C:/Python314/python.exe -B -c \"import subprocess,sys,hashlib; r=subprocess.run([sys.executable,'-B',sys.argv[1],'--dry-run','--arm',sys.argv[2]],capture_output=True); d=r.stdout; print(sys.argv[2],r.returncode,len(d),len(r.stderr),hashlib.sha256(d).hexdigest()[:16])\" C:/Users/gabgo/source/repos/planwise-development/hooks_wip/plan-hook-module/driver/probe.py C-permreq-input",
        "C:/Python314/python.exe -I -c \"import os,sys; n=sum(len(f) for _,_,f in os.walk(sys.argv[1])); print('walked',n,'files')\" <Scratch>/lab",
        "C:/Python314/python.exe -B -I -c \"import re,sys; L=['TOOL-ABSENT','DENY-HEADLESS-NO-PROMPT','DENY-ASK-RULE-ON-REWRITE','DENY-NO-APPROVAL-SURFACE','DENY-MCP-NO-INTERACTION','DENY-OTHER','ALLOWED','SERVER-NOT-STARTED','HOOK-NOT-FIRED','HOOK-FIRED']; g=open(sys.argv[1],encoding='utf-8').read(); print('labels in grade.py',sum(bool(re.search(r'[\\\"\\\\']'+x+r'[\\\"\\\\']',g)) for x in L),'of',len(L))\" hooks_wip/plan-hook-module/verify/grade.py",
        "C:/Python314/python.exe -B -I -c \"import re,sys; L=['TOOL-ABSENT','DENY-HEADLESS-NO-PROMPT','DENY-ASK-RULE-ON-REWRITE','DENY-NO-APPROVAL-SURFACE','DENY-MCP-NO-INTERACTION','DENY-OTHER','ALLOWED','SERVER-NOT-STARTED','HOOK-NOT-FIRED','HOOK-FIRED']; p=open(sys.argv[1],encoding='utf-8').read(); m=re.search(r'^## Labels[^\\n]*\\n(.*?)(?=^## |\\Z)',p,re.M|re.S); s=m.group(1) if m else ''; print('labels in proof',sum(len(re.findall(r'^LABEL '+re.escape(x)+r'\\b',s,re.M))==1 for x in L),'of',len(L))\" planwise/Plans/HeadlessPromptToolMeasure/Sprint-01-PromptToolDriver/Session-01-ServerFlagAndGrader/Outputs/HPT-S01-01-04-GraderProof.md",
        "C:/Python314/python.exe -B -I -c \"import subprocess,sys; run=lambda g: subprocess.run([sys.executable,'-B',g,'--archive',sys.argv[3],'--arm',sys.argv[4],'--source','stream-json'],capture_output=True); a=run(sys.argv[1]); b=run(sys.argv[2]); print('exit',a.returncode,b.returncode,'stdout equal',a.stdout==b.stdout,'bytes',len(a.stdout))\" <Scratch>/grade.pre.py hooks_wip/plan-hook-module/verify/grade.py hooks_wip/plan-hook-module/verify/fixtures/full-A-control-p-pass A-control",
        "C:/Python314/python.exe -B -I -c \"import sys; b=set(open(sys.argv[1]).read().splitlines()); a=open(sys.argv[2]).read().splitlines(); P=('hooks_wip/plan-hook-module/verify/grade.py','hooks_wip/plan-hook-module/verify/test_grade.py','hooks_wip/plan-hook-module/verify/fixtures/pt-','hooks_wip/plan-hook-module/verify/fixtures/full-'); n=[l for l in a if l not in b and not l[3:].startswith(P)]; print('unattributed',len(n)); print(*n,sep=chr(10))\" <Scratch>/status-before.txt <Scratch>/status-after.txt",
        "C:/Python314/python.exe -B -c \"import json,subprocess,sys; sheet=open(sys.argv[1],encoding='utf-8').read(); rows=[json.loads(l) for l in sheet.splitlines() if l.startswith('[\\\"')]; arms=['A-control','B-permreq-bare','C-permreq-input']; ok=sum(json.loads(subprocess.run([sys.executable,'-B',sys.argv[2],'--dry-run','--arm',a,'--prompt-tool'],capture_output=True,text=True).stdout.splitlines()[0]) in rows for a in arms); print('ARGV EQUAL:',ok,'of',len(arms))\" hooks_wip/plan-hook-module/runs/RUN-12-p-prompt-tool.md hooks_wip/plan-hook-module/driver/probe.py",
    )

    def test_good_real_plan_commands(self):
        for index, command in enumerate(self.REAL_PLAN_COMMANDS):
            with self.subTest(index=index):
                self.assertEqual(self._count(f"{command}\n{self.EQ}"), 0)


class TestCheck52CharacterClassAfterDiffSign(unittest.TestCase):
    CORRECT = "git diff 1bc4e0a -- a.md | grep -E '^[+-]' | grep -vE '^(\\+\\+\\+|---)'"

    def _bad(self, pattern):
        return f"git diff 1bc4e0a -- a.md | grep -c '{pattern}'"

    def test_bad_removed_line_class_form(self):
        findings = _lint(52, _task(verification=_verification(after=self._bad("^-[^-]"))))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(52, "ERROR")])
        self.assertIn("gate-predicate-discrimination.md", findings[0]["message"])
        self.assertIn("§6", findings[0]["message"])

    def test_bad_added_line_class_form(self):
        self.assertEqual(len(_lint(52, _task(verification=_verification(after=self._bad("^+[^+]"))))), 1)

    def test_bad_both_signs_class_form(self):
        after = "git diff 1bc4e0a -- a.md | grep -E '^[+-][^+-]'"
        self.assertEqual(len(_lint(52, _task(verification=_verification(after=after)))), 1)

    def test_good_section_six_correct_form(self):
        self.assertEqual(_lint(52, _task(verification=_verification(after=self.CORRECT))), [])

    def test_good_added_lines_pair(self):
        after = "git diff 1bc4e0a -- a.md | grep '^+' | grep -v '^+++'"
        self.assertEqual(_lint(52, _task(verification=_verification(after=after))), [])

    def test_good_class_pattern_outside_a_diff_is_not_read(self):
        self.assertEqual(_lint(52, _task(verification=_verification(after="grep -c '^-[^-]' a.md"))), [])

    def test_check_24_form_is_not_reported_here(self):
        after = "git diff 1bc4e0a -- a.md | grep -v '^\\+\\+\\+'"
        self.assertEqual(_lint(52, _task(verification=_verification(after=after))), [])
        self.assertEqual(len(_lint(24, _task(verification=_verification(after=after)))), 1)

    def test_wrong_line_is_skipped(self):
        after = "# WRONG " + self._bad("^-[^-]")
        self.assertEqual(_lint(52, _task(verification=_verification(after=after))), [])


class TestCheck53BlobBytesAgainstCheckoutPin(unittest.TestCase):
    BLOB = "git show 1bc4e0a:a.md | wc -c"
    LINES = "git show 1bc4e0a:a.md | wc -l"
    CHECKOUT = "wc -c a.md"

    def test_bad_blob_bytes_against_checkout_pin(self):
        findings = _lint(53, _task(verification=_verification(after=f"{self.BLOB}\n{self.CHECKOUT}")))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(53, "WARNING")])
        self.assertIn("§8.12", findings[0]["message"])

    def test_bad_blob_bytes_against_literal_pin(self):
        after = "[ \"$(git show 1bc4e0a:a.md | wc -c)\" -eq 258364 ]"
        self.assertEqual(len(_lint(53, _task(verification=_verification(after=after)))), 1)

    def test_good_with_blob_line_count(self):
        after = f"{self.BLOB}\n{self.LINES}\n{self.CHECKOUT}"
        self.assertEqual(_lint(53, _task(verification=_verification(after=after))), [])

    def test_good_blob_against_blob(self):
        after = f"{self.BLOB}\ngit show 1bc4e0a~1:a.md | wc -c"
        self.assertEqual(_lint(53, _task(verification=_verification(after=after))), [])

    def test_good_checkout_on_both_sides(self):
        self.assertEqual(_lint(53, _task(verification=_verification(after=self.CHECKOUT))), [])

    def test_piped_wc_is_not_a_checkout_pin(self):
        after = f"{self.BLOB}\ncat a.md | wc -c"
        self.assertEqual(_lint(53, _task(verification=_verification(after=after))), [])


# The lines below were copied once from real task files of a closed plan. The one path
# each check resolves is renamed to ``big_module.py``, the generated file of a test. The
# other paths stay as written and resolve to nothing in a temp folder.
BIG = "x" * 60000  # 60,000 bytes: 23,077 tokens at the Read gate's ratio, near-cap
SMALL = "x" * 10000  # 10,000 bytes: 3,847 tokens, below the near-cap reading

_PREFIX = "cloned-repos/planwise/plugins/planwise"
# Output line of a task that grows a near-cap script and measures only its new module.
REAL_OUTPUT_UNMEASURED = (
    f"**Output:** `{_PREFIX}/scripts/migrate_backlog_relocate.py` (new), "
    "`big_module.py` (the \"content regeneration would drop\" site and `plan_changelog` wiring), "
    f"`{_PREFIX}/scripts/backlog_migration.py` (ledger count and banner line), "
    "`cloned-repos/planwise/tests/test_migrate_backlog_index.py`, "
    "`cloned-repos/planwise/tests/test_backlog_migration.py`, "
    "and `Outputs/URD-S02-02-ProseRelocation.md`"
)
# The step of that task that measures: it names measure_files and the new module, never the near-cap file.
REAL_STEP_NEW_MODULE_ONLY = (
    "8. **Lint** the three scripts and two tests; `measure_files.py` on the new module (under 8 KiB). "
    "**Scope:** name-only count over the five declared paths → 5; `git -C PLUGIN status --porcelain -- "
    "plugins/planwise/scripts/migrate_backlog_relocate.py` → one `??` line. Then the dirty-set gate: "
    "save `git -C PLUGIN status --porcelain` to `dirty-after.txt`, run `comm -13` on the sorted before "
    "and after files, and remove from its output every line that names one of the five Output scripts "
    "and tests (the new module, `backlog_migration.py` and the two test files appear as new lines; "
    "`migrate_backlog_index.py` is already dirty from Task 01 and does not). Expected: no lines remain. "
    "Presence floor: at least 4 lines named a declared path before the removal."
)
# The ceiling line of another task: measure_files, the file, a ceiling and a HALT in one line.
REAL_CEILING_LINE = (
    "   - `measure_files.py` on `big_module.py`: <!-- ceiling: start figure + 300 tokens, and never "
    "above 25,000 (the page cap; HALT and report if a change would cross it). floor: `config not read "
    "by` >= 1 and `gap detection` >= 1 in init_project.py --> and on `artifact_upgrade.py` "
    "(ceiling: start + 100 tokens)."
)
# Output lines of two tasks of one session that both edit the same near-cap script.
REAL_OUTPUT_SHARED_FIRST = (
    "**Output:** `big_module.py` (the config-read guard, the version check and the "
    f"Skipped rows), `{_PREFIX}/scripts/artifact_upgrade.py` (`load_artifact_manifest`'s degraded "
    f"return), `{_PREFIX}/handlers/init.md` (Step 10's degraded row), "
    "`cloned-repos/planwise/tests/test_init_missing_pyyaml.py` (new), and `Outputs/URD-S03-03-PyYamlSentinel.md`"
)
REAL_OUTPUT_SHARED_SECOND = (
    f"**Output:** `{_PREFIX}/scripts/pyyaml_remedy.py` (new: the remediation command builder), "
    "`big_module.py` (wiring only: the import, the call sites and the two "
    f"bare-command sites in it), `{_PREFIX}/handlers/init.md` (Step 10 offer and the bare-command site "
    f"in the sample row), `{_PREFIX}/handlers/upgrade.md` (Step 2.6, the install offer), "
    "`cloned-repos/planwise/tests/test_init_missing_pyyaml.py`, and `Outputs/URD-S03-03-PyYamlRemedy.md`"
)
BUDGET_OK = (
    "big_module.py: live 24,460 (cap 25,000, headroom 540); Task 01 <= +300 (wiring), "
    "Task 02 <= +100 (wiring); sum 400 < 540"
)
BUDGET_SUM_BAD = (
    "big_module.py: live 24,460 (cap 25,000, headroom 540); Task 01 <= +300 (wiring), "
    "Task 02 <= +350 (wiring); sum 650 < 540"
)
BUDGET_HEADROOM_BAD = (
    "big_module.py: live 24,460 (cap 25,000, headroom 600); Task 01 <= +300 (wiring), "
    "Task 02 <= +100 (wiring); sum 400 < 600"
)


def _near_task(output_line, steps=""):
    return (
        "# Task: Fixture\n\n"
        f"{output_line}\n\n"
        "## Objective\n\nDo the work.\n\n"
        f"## Execution Steps\n\n{steps}\n"
    )


def _orchestration(*lines):
    body = "".join(f"{line}\n" for line in lines)
    return f"# Orchestration: Fixture\n\n## Budget\n\n{body}"


def _stderr_of(text, files):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "TASK-01-Fixture.md").write_text(text, encoding="utf-8", newline="\n")
        for rel, body in files.items():
            (Path(tmp) / rel).write_text(body, encoding="utf-8", newline="\n")
        captured = StringIO()
        with redirect_stderr(captured):
            lint_plan(Path(tmp), execute=False)
    return captured.getvalue()


class TestCheck61NearCapOutputWithoutGate(unittest.TestCase):
    @property
    def FILES(self):
        return {"big_module.py": BIG}

    def _bad(self):
        return _near_task(REAL_OUTPUT_UNMEASURED, REAL_STEP_NEW_MODULE_ONLY)

    def test_bad_near_cap_file_on_the_output_line_with_no_gate_line(self):
        findings = _lint(61, self._bad(), files=self.FILES)
        self.assertEqual([(f["check"], f["severity"], f["file"]) for f in findings],
                         [(61, "WARNING", "TASK-01-Fixture.md")])
        self.assertEqual(findings[0]["line"], 3)
        self.assertIn("big_module.py", findings[0]["message"])
        self.assertIn("§8.14", findings[0]["message"])

    def test_good_repaired_with_the_ceiling_line(self):
        text = _near_task(REAL_OUTPUT_UNMEASURED, REAL_STEP_NEW_MODULE_ONLY + "\n" + REAL_CEILING_LINE)
        self.assertEqual(_lint(61, text, files=self.FILES), [])

    def test_good_below_threshold_control_is_silent(self):
        self.assertEqual(_lint(61, self._bad(), files={"big_module.py": SMALL}), [])

    def test_a_measure_line_without_halt_still_warns(self):
        no_halt = REAL_CEILING_LINE.replace("HALT", "stop")
        text = _near_task(REAL_OUTPUT_UNMEASURED, no_halt)
        self.assertEqual(len(_lint(61, text, files=self.FILES)), 1)

    def test_a_halt_line_that_names_another_file_still_warns(self):
        other = REAL_CEILING_LINE.replace("big_module.py", "other_module.py")
        text = _near_task(REAL_OUTPUT_UNMEASURED, other)
        self.assertEqual(len(_lint(61, text, files=self.FILES)), 1)

    def test_the_gate_line_may_sit_in_a_verification_block(self):
        steps = "```\nmeasure_files.py big_module.py   # HALT above 25,000\n```"
        self.assertEqual(_lint(61, _near_task(REAL_OUTPUT_UNMEASURED, steps), files=self.FILES), [])

    def test_summary_counts_the_paths_and_the_near_cap_file(self):
        err = _stderr_of(self._bad(), self.FILES)
        self.assertRegex(err, r"Check 61: output paths examined \d+, resolved 1, near-cap 1")

    def test_a_run_that_resolves_nothing_says_resolved_zero(self):
        err = _stderr_of(self._bad(), {})
        self.assertRegex(err, r"Check 61: output paths examined \d+, resolved 0, near-cap 0")
        self.assertEqual(_lint(61, self._bad()), [])


class TestCheck62SharedNearCapFileWithoutBudget(unittest.TestCase):
    def _files(self, *orchestration_lines, big=BIG):
        files = {
            "TASK-02-Fixture.md": _near_task(REAL_OUTPUT_SHARED_SECOND),
            "big_module.py": big,
        }
        if orchestration_lines:
            files["TASK-Orchestration.md"] = _orchestration(*orchestration_lines)
        return files

    def _first(self):
        return _near_task(REAL_OUTPUT_SHARED_FIRST)

    def test_bad_two_tasks_name_one_near_cap_file_and_no_budget_line(self):
        findings = _lint(62, self._first(), files=self._files("A budget is a good idea."))
        self.assertEqual([(f["check"], f["severity"], f["file"]) for f in findings],
                         [(62, "WARNING", "TASK-01-Fixture.md")])
        self.assertIn("big_module.py", findings[0]["message"])
        self.assertIn("§8.14", findings[0]["message"])

    def test_bad_no_orchestration_file_at_all(self):
        self.assertEqual(len(_lint(62, self._first(), files=self._files())), 1)

    def test_good_repaired_budget_line(self):
        self.assertEqual(_lint(62, self._first(), files=self._files(BUDGET_OK)), [])

    def test_bad_arithmetic_terms_do_not_sum_below_the_headroom(self):
        findings = _lint(62, self._first(), files=self._files(BUDGET_SUM_BAD))
        self.assertEqual([(f["check"], f["file"]) for f in findings], [(62, "TASK-Orchestration.md")])
        self.assertIn("650", findings[0]["message"])
        self.assertIn("540", findings[0]["message"])

    def test_bad_headroom_is_not_cap_minus_live(self):
        findings = _lint(62, self._first(), files=self._files(BUDGET_HEADROOM_BAD))
        self.assertEqual(len(findings), 1)
        self.assertIn("540", findings[0]["message"])

    def test_good_single_task_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "TASK-01-Fixture.md").write_text(self._first(), encoding="utf-8", newline="\n")
            (Path(tmp) / "big_module.py").write_text(BIG, encoding="utf-8", newline="\n")
            with redirect_stderr(StringIO()):
                found = [f for f in lint_plan(Path(tmp), execute=False) if f["check"] == 62]
        self.assertEqual(found, [])

    def test_good_below_threshold_control_is_silent(self):
        self.assertEqual(_lint(62, self._first(), files=self._files(big=SMALL)), [])

    def test_summary_counts_the_near_cap_file(self):
        err = _stderr_of(self._first(), self._files(BUDGET_OK))
        self.assertRegex(err, r"Check 62: output paths examined \d+, resolved 2, near-cap 2")


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in measure_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_check_numbers(self):
        names = [check.__name__.split("_")[1] for check in measure_module.CHECKS]
        self.assertEqual(names, [f"check{number}" for number in (48, 49, 50, 51, 52, 53, 61, 62)])

    def test_severity_constants_match_the_linter(self):
        for name in ("SEVERITY_ERROR", "SEVERITY_WARNING", "SEVERITY_UNCERTAIN"):
            self.assertEqual(getattr(measure_module, name), getattr(lint_module, name))

    def test_finding_keys_match_make_finding(self):
        fields = {"check": 1, "severity": "WARNING", "file": "f", "line": 1, "command": "c", "message": "m"}
        self.assertEqual(measure_module._finding(**fields), lint_module.make_finding(**fields))

    def test_module_imports_nothing_from_the_linter(self):
        source = (SCRIPTS / "lint_gate_checks_measure.py").read_text(encoding="utf-8")
        self.assertNotIn("lint_verification_gates", source.split('"""', 2)[2])

    def test_cli_run_as_script_reports_the_new_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "TASK-01-Fixture.md").write_text(
                _task(
                    context_rows=["| 1 | `data.md` — whole | 2.0 | — | purpose |"],
                    verification=_verification(after="git diff 1bc4e0a -- a.md | grep -c '^+[^+]'"),
                ),
                encoding="utf-8", newline="\n",
            )
            (Path(tmp) / "data.md").write_text(KIB_TEN, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), tmp, "--no-execute"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
        self.assertIn("[WARNING] Check 48:", completed.stdout, completed.stderr)
        self.assertIn("[ERROR] Check 49:", completed.stdout, completed.stderr)
        self.assertIn("rows examined 1, skipped 0 (unresolved), measured 1", completed.stderr)


if __name__ == "__main__":
    unittest.main()
