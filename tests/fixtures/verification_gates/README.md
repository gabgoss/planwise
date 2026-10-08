# Verification-Gate Linter Fixture Corpus

**Purpose:** Self-contained fake plan trees that the verification-gate linter
is measured against. Each shape fixture isolates one check, the guard fixtures assert a
check must *not* fire, and the regression fixtures reproduce real defects observed live.
The fixture map below is the authoritative list.

Each fixture is a **complete miniature plan tree**. Every command inside a fixture's
task file resolves **relative to that fixture's own directory** — never into the real
repository. A fixture that can be satisfied by the actual plugin tree is measuring the
wrong tree and is broken by definition.

---

## Fixture Map

Task 02's suite asserts against this table. A fixture whose intent lives only in its
directory name gets asserted wrongly, so the expected counts below are **measured**,
not intended.

| Fixture directory | Check | Expected findings | Severity |
|-------------------|:-----:|:-----------------:|----------|
| `shape_01_vacuous_after_gate/` | 1 | 1 | ERROR |
| `shape_02_missing_pre_edit_baseline/` | 2 | 1 | WARNING |
| `shape_03_bre_ere_mismatch/` | 3 | 2 | ERROR |
| `shape_04_self_matching_sweep/` | 4 | 1 | ERROR |
| `shape_05_stale_ownership/` | 5 | 1 | ERROR |
| `shape_06_substring_own_vocabulary/` | 6 | 1 | WARNING |
| `shape_07_contradicted_before_baseline/` | 7 | 2 | ERROR |
| `shape_08_grep_tool_escaped_pipe/` | 8 | 3 | WARNING |
| `shape_09_dollar_anchor_crlf/` | 9 | 1 | WARNING (the absent-target arm; the CRLF ERROR and LF silent arms are built in a temp directory by the suite) |
| `shape_10_single_term_coverage/` | 10 | 1 | WARNING |
| `shape_11_verdict_emphasis_dropped/` | 11 | 1 | ERROR |
| `shape_12_heading_substring/` | 12 | 1 | WARNING |
| `shape_13_bare_numeric_literal/` | 13 | 1 | WARNING |
| `shape_14_context_window_counted/` | 14 | 1 + 1 refusal | WARNING + UNCERTAIN (the pipeline is refused whole by the executor) |
| `shape_15_anchored_aggregate_threshold/` | 15 | 1 | WARNING |
| `shape_16_unscoped_suite_gate/` | 16 | 1 + 1 refusal | WARNING + UNCERTAIN (`python` is not on the allowlist) |
| `invariant_preservation/` | 1 and 2 must **NOT** fire | **0** | — |
| `grep_literal_pipe_ok/` | 8 must **NOT** fire | **0** | — |
| `anchored_heading_ok/` | 9, 10, 11, 12, 13 and 15 must **NOT** fire | **0** | — |
| `scoped_suite_ok/` | 14 and 16 must **NOT** fire (asserted with the executor off) | **0** | — |
| `regression_R1_count_gate_two/` | 1, plus 2 | 1 + 1 | ERROR + WARNING |
| `regression_R2_count_gate_eleven/` | 1, plus 2 and 10 | 1 + 1 + 1 | ERROR + WARNING + WARNING |
| `regression_R3_count_gate_four/` | 1, plus 2 | 1 + 1 | ERROR + WARNING |
| `regression_R4_bre_returns_zero/` | 3 and 1, plus 2 | 1 + 1 + 1 | ERROR + ERROR + WARNING |
| `regression_R5_self_matching_sweep/` | 4, plus 2 | 1 + 1 | ERROR + WARNING |

> [!important] The regression fixtures carry a Check-2 co-finding **by construction**
> Every `regression_R*` fixture reproduces its command **verbatim** from the real
> instance. None of those real gates carried a pre-edit annotation — that absence is
> part of the defect being reproduced. Check 2 therefore fires on each of them in
> addition to the check named in the fixture's directory name, and the suite MUST
> expect it. Adding an annotation to silence it would break verbatim reproduction and
> destroy the regression.
>
> `regression_R4` carries **three** findings for the same reason: the original gate was
> BRE-broken (Check 3), returned `0` against an `expect 0` and so was also vacuous
> (Check 1), and was unannotated (Check 2). All three are real properties of the
> recorded instance. `regression_R2` carries three as well: its recorded gate counts the
> single term `AUTO-MODE` in a Markdown file against `≥2`, which is the single-term
> coverage shape Check 10 reads.

---

## Group A — Shape Fixtures (one per check)

Each shape fixture is tuned so that **exactly one** check fires. Every After-gate
except `shape_02`'s carries a pre-edit annotation whose recorded value equals the
fixture tree's live measured value, so neither Check 2 (missing annotation) nor Check
1's re-measure clause (recorded disagrees with measured) fires as a side effect.

| Fixture | Measured fact the tree makes true |
|---------|-----------------------------------|
| `shape_01_vacuous_after_gate` | `grep -c 'shared-context' references/task-content-fidelity.md` → **2**, which already satisfies the gate's `expect >=1`. Check 1 **executes**, so this count is real. |
| `shape_02_missing_pre_edit_baseline` | Gate carries **no** `pre-edit:` annotation. Its target measures **0** against `expect >=1` — deliberately *not* satisfied, so the fixture is not accidentally also a Check-1 hit. |
| `shape_03_bre_ere_mismatch` | Two gates. (a) `grep -rn` without `-E` over a pattern containing `(`, `)`, `\|` → **0** as written, **2** with `-E`. (b) The absorbed variant: `grep -c` returns **2 lines** where the author meant **3 matches**, because two occurrences share one line. |
| `shape_04_self_matching_sweep` | An `expect 0` tree-wide sweep, an `Output:` field naming three new files, and no path-exclusion filter. The sweep measures **3** — one hit per file the task was told to create. All three parts are required; the check keys on the combination. |
| `shape_05_stale_ownership` | An absence-assertion naming `guides/guide-alpha.md` **and** §8.1, plus a sibling Sprint Plan whose routing table moves all of §8 **out of** that file in the same sprint. Target measures **1** against `expect 0`. |
| `shape_06_substring_own_vocabulary` | A bare `grep -c 'FAIL'` over a generated report that **passed**. The report measures **3** — its legend, its column header, and a criterion row — all emitted by the sibling `templates/verification-report.md`. |
| `shape_07_contradicted_before_baseline` | Two Before-block baselines that disagree with the live tree: stated `5` vs measured **2**, and stated `21 lines` vs measured **19**. Check 7 **executes**, so the disagreement is real, not merely asserted. |
| `shape_08_grep_tool_escaped_pipe` | Three native `Grep` calls whose patterns write alternation as `a\|b`: one in a table row (line 12), one in a fenced block (line 19), and one in a row whose output cell carries `{...}` template slots (line 28). Check 8 reads markdown lines, so no call needs to be an extracted command. The line-12 call is the real gate that first showed the defect, and the line-28 row is verbatim from a finished plan. |
| `shape_09_dollar_anchor_crlf` | A `$`-anchored exact-sentence gate whose target `Outputs/deliverable.md` does not exist yet, so its line endings are unknown: WARNING. No checked-in file carries the CRLF bytes, because a checkout under `core.autocrlf` rewrites them; the suite builds the CRLF (ERROR) and LF (silent) targets in a temp directory. |
| `shape_10_single_term_coverage` | `grep -ci 'intersection' design.md` against `expect >= 2`, where `design.md` covers every clause in one paragraph. Check 1 executes and measures **1**, which does not satisfy the threshold, so only Check 10 fires. |
| `shape_11_verdict_emphasis_dropped` | A Before gate `grep -c 'Gate: PASS' Outputs/snapshot.md` where the snapshot writes `**Gate:** PASS`. The target carries the bold form, so the literal is absent and Check 11 is ERROR. The snapshot carries no `**Verdict:**` marker, so Check 6 stays silent. |
| `shape_12_heading_substring` | A pre-write Before gate `grep -c '## Index Notes' plan.md # expect 0` where `plan.md` quotes the heading twice in prose and carries no heading. The substring count measures **2**; Check 12 fires on the missing `^`. The After gate is marked `invariant:` so Check 1 stays silent. |
| `shape_13_bare_numeric_literal` | `grep -rn '40000' config/` where `config/limits.md` holds `40000` and `400000`. Check 1 executes and measures **2** lines against `expect 1`, so only Check 13 fires. |
| `shape_14_context_window_counted` | `grep -B1 'AskUserQuestion' handlers/review.md \| grep -c 'AUTO-MODE:'` as an After gate. The executor refuses the pipeline whole (one UNCERTAIN refusal); Check 14 reads the two stages and fires on the counted context window. |
| `shape_15_anchored_aggregate_threshold` | `grep -cE '^\[(BLOCKER\|ERROR\|WARNING\|INFO)\]' report.md` against `expect >= 54`, where `report.md` holds three line-start tags and one mid-sentence tag. Check 1 measures **3**, unsatisfied; `-E` keeps Check 3 silent; Check 15 fires. |
| `shape_16_unscoped_suite_gate` | `python -m pytest -q` as a task file's After gate with no path argument. `python` is refused by the allowlist (one UNCERTAIN refusal); Check 16 fires. |

---

## Group B — Invariant / Preservation Fixture

`invariant_preservation/` is the corpus's false-positive guard. Its second gate reads:

```
grep -c '_BASE' templates/task-file.md
# pre-edit: 3 → invariant: 3 (this count must NOT move — a revert drops it, a duplicate raises it)
```

The target genuinely contains **3** `_BASE` lines, so `pre == post` is true and
intended. The `invariant:` marker sits on the annotation line, which is the only place
a mechanical checker can read it.

The suite asserts **zero** findings here. Without this fixture, "Check 1 fires" and
"Check 1 fires on everything" are indistinguishable — and a linter that flags every
preservation gate trains its users to ignore it.

The fixture's *first* gate (`pre-edit: 0 → expect >=1`) is a normal discriminating
gate, included so the fixture is not trivially finding-free.

`grep_literal_pipe_ok/` is the same guard for Check 8. It carries a table-row anchor
(`^\| 1[12] `), a pipe beside whitespace, a bare-pipe alternation and a line marked
WRONG. Each is correct or exempt for the native `Grep` tool, so the suite asserts
**zero** findings.

`anchored_heading_ok/` is the guard for Checks 9 to 15. Its Before block carries the
correct form of each flagged shape: a heading anchored with `^`, a two-word phrase
rather than a single term, the skeleton's bold bytes `**Gate:** PASS` (the snapshot
reads HALT, so Check 1 cannot fire), digit boundaries guarded with `(^|[^0-9])…([^0-9]|$)`,
a count with no threshold, and a `\r\?` guard before a `$` anchor. The suite asserts
**zero** findings with the executor on.

`scoped_suite_ok/` is the guard for Checks 14 and 16: a context window read by eye and
never piped into a count, and a pytest gate scoped to one test module. The suite asserts
**zero** findings with the executor off, because `python` is refused by the allowlist
and that refusal is a report about the executor, not a check finding.

---

## Group C — Regression Fixtures

Five real instances. Each reproduces its command **verbatim**, with a tree built to
make the recorded measured value genuinely true.

| Fixture | Measured fact the tree makes true |
|---------|-----------------------------------|
| `regression_R1_count_gate_two` | `references/task-content-fidelity.md` measures **2** against `# ≥1` |
| `regression_R2_count_gate_eleven` | `references/skill-authoring.md` measures **11** against `# ≥2` |
| `regression_R3_count_gate_four` | `references/agent-orchestration-delegated.md` measures **4** against `# expect ≥1` |
| `regression_R4_bre_returns_zero` | `agents/plan-reviewer.md` measures **0** under BRE and **11** under `-E` — matching the recorded "0 as written, 11 with -E" exactly |
| `regression_R5_self_matching_sweep` | The sweep measures **4** against `# 0` — one hit per sibling file the same task's `Output:` field names, each carrying the required backlink |

---

## Corpus Hygiene

These properties are asserted mechanically; treat them as binding.

> [!constraint] Nothing here may be collected or executed by pytest
> WRONG — a fixture file pytest would import and run:
> ```
> tests/fixtures/verification_gates/shape_01_vacuous_after_gate/test_shape.py
> ```
> CORRECT — inert data only, `.md` / `.txt`:
> ```
> tests/fixtures/verification_gates/shape_01_vacuous_after_gate/VGL-FIX-S01-01-01-Sonnet-CiteSharedContextRule.md
> ```
> No file named `test_*.py`, `*_test.py`, or `conftest.py`, and **no `.py` file at all**,
> may appear anywhere under this corpus root.

- **Self-contained.** No fixture references a path outside its own directory, and no
  fixture can be satisfied by the real repository. A fixture that passes because the
  *actual* `references/skill-authoring.md` happens to contain `AUTO-MODE` is measuring
  the wrong tree — the single most likely way this corpus ships broken.
- **Realistic strings are correct here.** `tests/` sits outside the ship boundary — the
  marketplace copies `./plugins/planwise` by working tree — so these fixtures carry
  realistic bookkeeping identifiers and plan-shaped filenames deliberately. That realism
  is what makes them regressions rather than toys. The plugin identifier-isolation gate
  applies to the shipped linter module, **never** to this corpus. Do not sanitise these
  into generic placeholders; a sanitised fixture no longer reproduces the input the
  linter will meet.
