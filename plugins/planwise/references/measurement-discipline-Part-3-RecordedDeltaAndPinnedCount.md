---
description: Recorded-figure discipline continued — a recorded delta states both endpoints and says whether it is net or set size, with the figure stated on both sides of any transform (§8.10), and a pinned count names the artifact and version it was read from, carries the commit sha, matches a pytest summary with a suffix-tolerant pattern and copies the exact command into a dry-run annotation, with the diff-gate header-line corollary (§8.11), and a byte pin names its instrument because blob bytes and checkout bytes differ by the line count under `core.autocrlf` (§8.12), and a size estimate for a compress, collapse or split has three terms, fixed overhead, keep orders and added pairs, which a flat per-heading figure leaves out (§8.13), and a task that grows a near-cap file measures it before and after against a stated ceiling with a HALT, while tasks that share one near-cap file split one budget line whose terms sum below the headroom (§8.14), and a size ceiling names its gate or says it is an estimate, an overflow rule repeats until every part measures OK, and a cost bound names the planned additions it excludes (§8.15). Split out of measurement-discipline.md when that file crossed the Read-tool token gate. Part 3 of 3. Part 1 of 3 is measurement-discipline.md.
consult-when: Writing a spec delta, a test assertion copied from a spec, or a pinned count — record both endpoints beside a "+A/-R" delta and say whether it is net or set size, state the figure on both sides of a transform, write the artifact and version beside a pinned count, stamp it with the commit sha, match a pytest summary with a suffix-tolerant pattern, copy the exact command into a dry-run annotation, and count diff lines with a filter anchored on the sign alone that removes the `---` and `+++` header lines by name; a byte count from a blob and one from the checkout differ by the line count under `core.autocrlf`, so name the instrument beside every byte pin; sizing a compress, collapse or split of a reference library, or any savings forecast built from heading counts, takes three terms (fixed overhead, keep orders, added pairs) read from the live file; writing or reviewing a task that edits a file near a Read gate (0.9 of the token warn, the line cap or the byte warn) — measure it before and after against a stated ceiling with a HALT, and when two or more tasks of one session edit it, give the Orchestration one budget line whose terms sum below the headroom; writing a size ceiling, an overflow rule or a cost bound in a plan — label the ceiling as a guard or an estimate, state the overflow rule as a repeat procedure, and name the planned additions a cost bound excludes; carries §8.10 to §8.15 of `measurement-discipline.md`
paths: {planwise_root}/{plans_dir}/**
---

# Measurement Discipline, Part 3 — Recorded Delta and Pinned Count

**Purpose:** §8.10, §8.11, §8.12, §8.13, §8.14 and §8.15, split out of [measurement-discipline.md](measurement-discipline.md) when that file crossed the Read-tool token gate. §8.1–§8.7 and §8.9 stay on that anchor, which keeps the original filename, and §8.8 lives in [measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md](measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md). §8.10 to §8.14 extend §8.9 sub-rule A, which re-measures a recorded figure at execution time. §8.15 covers a figure that an author writes before anything is measured.

---

## 8.10 A recorded delta states both endpoints and says whether it is net or set size

A delta written "+A/−R" in prose can mean two things: the sizes of the added and removed sets, or the net change with the removals broken out. A spec that does not say which is read the convenient way by whoever writes the assertion. A transform between the measurement and the return value (rename pairing, deduplication, normalisation) makes it worse. A set-difference figure taken before pairing and a return value taken after pairing are both true. They differ by exactly the paired count. Assertions copied from such a figure can contradict each other, and a correct implementation then fails tests written against a correct spec.

> [!constraint] The spec states which quantity the figure is, and the assertion names the quantity the function returns
> WRONG — lift the figure into the assertion that reads most naturally:
> ```
> spec:  "exports +71/-4"           ->  test:  assert len(exports_added) == 71
> spec:  "events +12/-1, one rename" -> test:  assert set(events_added) == {twelve}
>                                              assert events_removed == []     # contradicts the line above
> ```
> CORRECT — endpoints beside the delta, and the figure on both sides of the transform:
> ```
> spec:  "exports: 192 -> 263 (net +71); removed = {4 names}; added-set size 75"
>        "events: raw +12/-1; after pairing: 11 added, 0 removed, 1 renamed (<key-a> -> <key-b>)"
> test:  assert exports_removed == {four names}
>        assert len(exports_added) == 75 and len(exports_added) - len(exports_removed) == 71   # 71 is the net figure; the docstring says so
>        assert set(events_added) == {eleven}                                                 # <key-b> sits in renamed_suspected
>        assert events_removed == []
>        assert renamed == [{'removed': '<key-a>', 'added': '<key-b>'}]
> ```

- **Record the two endpoint counts beside a delta** (`192 -> 263`). A reader can then tell net from set size by subtraction. A bare "+71/−4" cannot be disambiguated after the fact.
- **State the figure on both sides of a transform, or name which side it quotes.** A test asserts the returned side.
- **Reconcile before dispatching a task whose assertions are literals copied from a spec.** Have the producing task measure the same quantity. Route the measured value as a spec delta. Do not let the runner change the test to whatever passes.

Applies to any task brief whose success criterion is a literal count or list copied from a spec, a finding document or an addendum table, especially a `+N/−M` shape. It also applies to diff tooling with rename or move detection.

## 8.11 A pinned count names the artifact and version it was read from

A literal count depends on the exact artifact and version it was read from. When the artifact is regenerated, the dependency moves and the number does not. The pin in a test fails loudest and latest. The task that regenerates the artifact may not be allowed to edit the test, so a green session ends with a red tier and a round-trip to widen the write-set.

> [!constraint] Write the dependency beside the number
> WRONG — the number alone:
> ```python
> assert len(parsed["rows"]) == 124
> ```
> CORRECT — the number with its dependency, so a regeneration reads as a re-pin trigger and not a regression:
> ```python
> # pinned to the committed reports/<old>__<new>-candidates.md;
> # re-pin whenever that file is regenerated
> assert len(parsed["rows"]) == 110
> ```
> BETTER where the test's purpose allows — assert the property, not the count:
> ```python
> assert {"key", "consumer", "change"} <= parsed["rows"][0].keys()
> assert parsed["old"] == "<old>" and parsed["new"] == "<new>"
> ```

- **Write the artifact and version beside every pinned count.** A reviewer who sees `== 124` cannot tell what it measures. One who sees the comment can re-derive it in one command. This extends sub-rule A of §8.9, which re-measures a recorded figure at execution time.
- **Treat every pin against a regenerated artifact as untrusted until re-read.** `Grep` the tests and briefs for the artifact's path before dispatch. Put the re-pin in the regenerating task's write-set. Otherwise the tier goes red in a file the runner is forbidden to touch.
- **Write a count from a version-dependent source as "N on version V", never as N.** This holds in a backlog item or a spec. The build changes under the item. The item does not.
- **Stamp a count read from a git-tracked subject with the commit sha, not only the date.** Several commits can land on one day. A preflight runs `git -C <repo> log --oneline <sha>..HEAD -- <test files>`, and empty output means the pin still holds.
- **Match a pytest summary with `^N passed[ ,]`, never with `^N passed in `.** Pytest inserts text such as `, N subtests passed` or `, N skipped` before ` in`.
- **Copy the exact command into a dry-run or `pre-edit:` annotation beside a pinned command.** Copy it byte for byte, or name it as a variant. At dispatch, re-run the pinned command, not the annotation's command, and route any mismatch with both figures.

Check 63 of `scripts/lint_gate_checks_verify.py` warns on a checkbox criterion that pins a code symbol's member count with no instrument on the line.

**Diff-gate corollary.** A line count over `git diff` output counts the `---` and `+++` header lines too, so a gate that expects 0 removed lines reads 1 on any non-empty diff. Anchor the filter on the sign alone, and remove the header lines by name. A character class written right after the sign also drops every changed line that starts with that character, such as a removed or added bullet. [`gate-predicate-discrimination.md`](gate-predicate-discrimination.md) §6 holds the general rule and its counter-example. Check 52 of `scripts/lint_gate_checks_measure.py` flags a gate that puts a character class right after the diff sign.

```bash
git diff -- <path> | grep -E '^-' | grep -vE '^---' | wc -l          # removed lines
git diff -- <path> | grep -E '^\+' | grep -vE '^\+\+\+' | wc -l      # added lines
```

Applies to test assertions that pin the row, line or entry count of a committed report, fixture or snapshot. It also applies to backlog items and design-spec rows that quote a figure from one build.

### A stamp carries the commit, a summary match tolerates its tail, and an annotation copies its command

A date does not identify a tree, because several commits land on one day. A pytest summary line has a variable tail, so a rigid match breaks when a subtest or skip count appears. A dry-run annotation that records a variant of the pinned command states a figure the pinned command never produced. The re-pin step is in the `scaffolding-hygiene.md` section "Re-Measure Every Gate-Bound Figure at Preflight, Before Dispatch".

> [!constraint] Stamp the commit, match the tail, copy the command
> WRONG — the date alone, a rigid summary match, and an annotation from a different window:
> ```
> 45 passed (re-measured <date>)  -> matches '^45 passed in '
> pin: git log --since=<d1> ...   # Dry-run (since <d2>): 8 lines
> ```
> CORRECT — the sha beside the count, a tolerant match, a preflight line, and the exact command in the annotation:
> ```
> 58 passed, 8 subtests passed @ <sha> (<date>)  -> matches '^58 passed[ ,]'
> preflight: git -C <repo> log --oneline <sha>..HEAD -- <test files>    # empty output: the pin holds
> pin: git log --since=<d1> ...   # Dry-run <date>, this exact command at <sha>: 31 lines
> ```

## 8.12 A byte pin names its instrument: blob bytes and checkout bytes differ under autocrlf

A byte count from a blob and a byte count from the checkout are two instruments. Under `core.autocrlf=true` a blob holds LF line endings and the checkout holds CRLF. The two counts differ by exactly the number of lines. A pin taken from one instrument and compared to the other reads as drift. The gap is large enough to look like a missing row, and it grows with the file, so it is not noise.

> [!constraint] Use the same instrument on both sides, or carry the line count across
> WRONG — blob bytes compared to a working-tree pin:
> ```
> git show <sha>:<path> | wc -c     # 258072
> baseline pin (wc -c on checkout)  # 258364
> # "292 bytes missing" — no row is missing
> ```
> CORRECT — same instrument on both sides, or the line count carried across:
> ```
> git show <sha>:<path> | wc -c     # 258072  (LF blob)
> git show <sha>:<path> | wc -l     # 292
> 258072 + 292 = 258364             # equals the checkout pin
> ```

- **Pin working-tree bytes with `wc -c` when the subject is the checkout, and say so.** A conservation identity runs against files on disk, so every term comes from disk.
- **Add the line count when a term must come from git history.** Run `git show <sha>:<path> | wc -l` and add it before comparing to a working-tree pin. Or compare blob to blob.
- **Treat a gap that equals the line count as the signature of this trap.** Check `git config core.autocrlf` before looking for a lost row.

Check 53 of `scripts/lint_gate_checks_measure.py` warns on a gate that compares `git show` bytes with a checkout `wc -c` pin and adds no line count.

**A character count is a third instrument.** `awk '{print length($0)}'`, `${#var}` and `len(str)` count decoded characters, not bytes. A byte identity that takes one operand from such a counter false-fails by the extra bytes of the multi-byte characters in the text. [`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) §5 states this form.

- **Take every operand of a byte gate from a byte instrument:** `wc -c`, an `rb` read or a byte regex.
- **Run a pinned measurement command once beside a second instrument before a gate trusts it.** The two figures must agree, or the disagreement is the finding.

Applies to any byte pin, size gate, or conservation identity on a Windows checkout with `core.autocrlf=true`. It applies whenever one operand comes from `git show`, `git cat-file`, or a diff stat and another comes from the working tree.

## 8.13 A size estimate for a compress, collapse or split has three terms

A plan that compresses, collapses or splits references often forecasts each result from a heading count. A flat per-heading figure leaves out three terms. The forecast then sets expectations wrong by 3 to 6 times, even when no runner pads or cuts to reach it.

> [!constraint] Build the estimate from the live file, one term at a time
> A plan compressed four dispatch references at the per-rule-section grain. It estimated each result as headings × 700 B ÷ 2.6. The plan called the figure "a signal, not a target", so no runner padded or cut to hit it. Each result was then measured with `measure_files.py --model opus`:
>
> | File | Before | After | Estimate | After ÷ estimate |
> |------|-------:|------:|---------:|-----------------:|
> | A | 9,864 | 9,585 | 2,962 | 3.2 |
> | B | 10,548 | 9,200 | 1,615 | 5.7 |
> | C | 6,296 | 5,768 | 1,615 | 3.6 |
> | D | 5,685 | 5,507 | 1,346 | 4.1 |
>
> The total fell 7.2%. The runners named three causes:
>
> - **Fixed overhead.** Frontmatter, the Table of Contents, headings and the footer cost 741 to 1,294 tokens per file before any rule text.
> - **Keep orders.** Undecided overlaps were carried, so their sections kept every claim. One file was the survivor for a moved rule. One section had to keep a full check spec. One file's two sections alone held 22.8% of its bytes.
> - **Added pairs.** The grain requires one labelled WRONG/CORRECT pair per rule section. The four files gained 17 new pairs, so a file with no pairs grows before it shrinks.
>
> WRONG — one term:
> ```
> estimate = headings × 700 B ÷ 2.6
> ```
> CORRECT — the three terms the measurement found, each read from the live file:
> ```
> estimate = fixed_overhead(file)
>          + sum(current size of each section under a keep order)
>          + sum(rule sentence + one pair, for each other rule section)
> ```

- **Read each term from the live file.** Measure the overhead, the kept sections and a sample pair. Do not take them from the heading count.
- **Keep the estimate a signal.** A plan that binds itself to the figure as a target invites padding or cutting to reach it.

Applies to sizing a compress, collapse or split of a reference library, and to any savings forecast built from heading counts.

## 8.14 A task that grows a near-cap file gates its figure, and tasks that share one sum their ceilings

A plan promise about the size of a file runs nothing. A task that edits a file close to a Read gate can push it over the gate without any step noticing. Two tasks that edit the same file can each pass their own ceiling while the sum crosses the cap.

**Near-cap** means any one of three readings. Take the three constants from `read_limits` and measure the file with `measure_files` at its default ratio, which is the Read gate's own ratio.

- Tokens at or above 0.9 × `READ_TOKEN_WARN`, which is 19,800.
- Lines at or above 0.9 × `READ_LINE_CAP`, which is 1,800.
- Bytes at or above 0.9 × `READ_BYTE_WARN`, which is 221,184.

**The ceiling** is the lowest Read gate above the before figure. For a file at 24,460 tokens it is the 25,000-token page cap. For a file at 20,000 tokens it is the 22,000-token warn.

### The gate line: measure the file before and after

The gate line is one line of the task. It holds a `measure_files` call on the file, the stated ceiling and the word `HALT`. The task runs it before the first edit and again after the last. A figure above the ceiling halts the task. The task never edits through the gate.

> [!constraint] Every task that edits a near-cap file measures it, against a stated ceiling
> WRONG — measure only the file the task creates:
> ```
> measure_files.py scripts/migrate_backlog_relocate.py        # 3.7 KiB, OK
> # migrate_backlog_index.py is never measured; it crosses 25,000 tokens unseen
> ```
> CORRECT — every task that edits a near-cap file measures it before and after, against a stated ceiling:
> ```
> measure_files.py scripts/migrate_backlog_index.py --model sonnet   # before: ~24,700
> # ... edit ...
> measure_files.py scripts/migrate_backlog_index.py --model sonnet   # after: must stay < 25,000, else HALT
> ```

### The budget line: one budget for a file that tasks share

The budget line belongs to the session's Orchestration file when two or more tasks of the session edit the same near-cap file. It has one shape:

```
{path}: live {n} (cap {c}, headroom {h}); Task 01 <= +{a}, Task 02 <= +{b}; sum {s} < {h}
```

The headroom `h` equals the cap `c` minus the live figure `n`. The terms `a` and `b` sum to `s`, and `s` stays below `h`. The figure `n` is the live reading at the moment the plan was written. A dispatch that waited re-takes it, as `dispatch-preflight-claim-expiry.md` section "1. A Held Plan Re-Takes Every Measurement It Asserts, at the Moment the Gate Clears" requires.

> [!constraint] Tasks that share one near-cap file share one budget
> WRONG — two independent ceilings, each checked only against its own start:
> ```
> Task 01: ceiling start + 300, never above 25,000
> Task 02: ceiling start + 350, never above 25,000   # start = after Task 01
> # live headroom 540 < 650: Task 02 can HALT with Task 01 uncommitted
> ```
> CORRECT — one budget for the file, split across the tasks:
> ```
> init_project.py: live 24,460 (cap 25,000, headroom 540); Task 01 <= +300 (wiring), Task 02 <= +100 (wiring); sum 400 < 540
> builder logic moves to a new module
> ```

### The two lint checks

Two checks of `scripts/lint_gate_checks_measure.py` read the plan for both cases. Each warns and exits 1, and neither blocks the plan.

- **Check 61** warns on a task whose first `**Output:**` line names a near-cap file when no line of the task holds `measure_files`, the file's basename and `HALT`. It cannot see a path the task edits but does not list on its Output line. It cannot see a measurement written in another form than a `measure_files` line. It cannot see a ceiling figure that is itself wrong.
- **Check 62** warns when a near-cap file is named on the Output lines of two or more task files in one folder, and no Orchestration file in that folder holds a budget line for it. It also warns on a budget line whose headroom is not the cap minus the live figure, and on one whose `<= +` terms do not sum below the headroom. It cannot see a stale live figure on a budget line. The dispatch-time re-take above is the control for that.

Both checks print `output paths examined E, resolved R, near-cap K` to stderr. An Output path that resolves to no file counts as examined and never as measured, so a run from the wrong folder shows `resolved 0` and not a clean pass.

Applies to any task that edits a file at or above the near-cap readings, and to any session where two tasks name one such file.

## 8.15 A size or cost figure names its gate, its overflow procedure or its exclusions

A plan author can write a size or cost figure from a guess, from projected inputs, or from a bound set before the plan's own text exists. The figure then binds a runner to a number nobody measured. It is plan prose, so no hooked tool call reads it.

Three checks of `scripts/lint_gate_checks_measure.py` read task files for these cases. Each one warns and exits 1, and none blocks the plan. Each skips a fenced block and a line that holds the word `WRONG`.

### A size ceiling names the gate it guards, or says it is an estimate

A ceiling with no named limit reads as a gate, even when the author guessed the figure.

> [!constraint] Label every size ceiling as a guard or as an estimate
> WRONG — a guessed figure written as a gate:
> ```
> - [ ] recovery_surfaces.py stays under 6 KiB <!-- ceiling: ≤ 6,144 bytes -->
> ```
> CORRECT — a real guard names the limit and the headroom:
> ```
> - [ ] doctor_cli.py grows by at most 300 tokens <!-- guards: the 22,000-token Read warn; start 20,395, later sprints need ~850 -->
> ```
> CORRECT — an estimate says that it is one:
> ```
> - [ ] recovery_surfaces.py: estimated ~6 KiB (not a gate; the governing limit is the 25K-token page cap)
> ```

**Check 69** warns on a checkbox criterion line that holds a ceiling word and a size figure. The ceiling words are `under`, `below`, `at most`, `no more than`, `never above`, `<=` and `≤`. The size units are KiB, KB, bytes and tokens. The check is silent when the line holds `guards:`, `estimat` or `not a gate` outside a code span. It is also silent when every size figure on the line equals a Read gate of `read_limits`: 19,800, 22,000 or 25,000 tokens, or 240 or 256 KiB. A checkbox that carries a §8.14 gate line takes the `guards:` label too, unless its ceiling is a Read gate.

The check reads the whole line. It therefore also warns when `under` or `below` names a location beside a size figure.

**Check 69 cannot see:**

- a ceiling in an Expected Output budget or in a Verification Command, because neither is a checkbox line
- a figure in a unit outside the list, such as lines
- a criterion that wraps, with the ceiling word on one line and the figure on the next
- a `guards:` label that names a limit which does not exist. The reviewer who reads the named gate is the control for this case

### An overflow rule is a repeat-until procedure, not a fixed sibling count

A sibling count fixed from projected inputs leaves the runner no legal exit when the inputs measure larger.

> [!constraint] State the overflow procedure, and price the split from the measured inputs
> WRONG — the sibling count is fixed at scaffold time from projected inputs:
> ```
> Output: Part-9 (plus a declared 9b only if Step 5 splits it)
> inputs projected 4 × 8K → one sibling assumed enough → Part 9 OVER after the 9b move, no legal exit
> ```
> CORRECT — the procedure is stated, and the split comes from the measured inputs at the layer edge:
> ```
> Overflow: move the largest section to the next sibling Part, re-measure, and repeat until every Part measures OK.
> re-price at the L1→L2 edge: inputs 41.9K measured
> expected Part 9 ≈ inputs + headers and amendments > 22K, and > 44K is two siblings
> → declare 9b, and 9c when (inputs − one moved section) still exceeds the warn line
> ```

In the measured case, a task consolidated four task outputs that it had to copy in full. Its overflow rule declared exactly one sibling. The inputs were projected at about 8,000 tokens each. Together they measured 41,853 tokens, 1.3 times the projected total. After the one declared move the Part still measured 27,003 tokens, over the cap.

**Check 70** warns on an `**Output:**` line that declares a lettered sibling Part, such as `Part-9b`, or that holds `declared ... sibling` or `sibling ... only if` within one clause. The check is silent when one prose line of the task holds both `re-measure` and `repeat`. It also warns on a task that only edits an existing lettered Part.

**Check 70 cannot see:**

- whether anyone re-priced the sibling count from the measured inputs at the layer edge, because the inputs exist only after the upstream tasks run
- an overflow rule that the task states outside its Output line
- a sibling declared in other words

### A cost bound excludes the plan's own planned additions

One number set before the plan's text exists can fail content that the user already approved.

> [!constraint] Name what the bound excludes, and report the growth per rule
> WRONG — one number for every branch, set before the branch's text exists:
> ```
> no sample path's COST rises by more than 200 tokens
> # the amend branch adds a paragraph plus approved rewording -> +299 -> FAIL on approved content
> ```
> CORRECT — the bound names what it excludes, and the report attributes growth per rule:
> ```
> no sample path's COST rises by more than 200 tokens beyond the planned additions
> (the new paragraph, the description line); report per-rule deltas from measure_files.py --model opus
> ```

**Check 71** warns on a line that holds `cost` or `load` and then a form of `rise`, `grow` or `increase`, followed by `by more than`, `by at most` or `by no more than` and a figure. The check is silent when the line names `planned additions` and a prose line states per-file or per-rule deltas.

**Check 71 cannot see:**

- a planned addition that the exclusion list omits
- a bound worded without `cost` or `load`
- a figure written in words
- a "report only" instrument that a later step promotes to a gate

Applies to any size ceiling, overflow rule or cost bound that a plan states before the files it measures exist.
