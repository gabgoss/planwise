---
description: A gate whose pattern is narrower than the claim it is cited to support returns its PASS value against known-bad input. Covers the paired-input control taken from version control, the three ways a pattern ends up narrower than its claim, case blindness in both directions, asserting a negative from a pattern shaped for a different positive, why a wrong figure in a briefing costs more than a wrong gate, the diff-filter character class that silently drops a whole syntactic population, and the pinned pattern that must run against the real expected-hit line (a verbatim fixture row) with a passing branch shown reachable on known-good input, and the "count unchanged" gate that an addition sharing its vocabulary makes unsatisfiable (pin a baseline diff, the old line's full shape, or a predicted total), the delivered gate that compares a PRE-edit constant and passes only before the work it verifies (read its code, prove it on the state it will gate, make it two-mode), the enforcer that decides on one measurement and asserts on another (decide and assert on the same measurement), and two instruments that disagree on one member (locate the member in the source, never pick the instrument that keeps the assertion green), the mutation proof whose assertion must sit on the branch the mutated symbol gates, one minimal input per guard so an earlier guard cannot shadow a later one, and the keyed read that hides a duplicate row (count rows before keying). Consult when about to cite a grep, a count, or a diff filter as proof.
consult-when: About to cite a match pattern, count, or diff filter as proof — pair the anchor against its known-bad state from git, match the claim rather than one phrasing, never assert an absence from a pattern shaped for a different positive, anchor a diff filter on the sign alone, never write `\+` in a basic-syntax header filter or trust an empty pipe without counting its stream, run a pinned pattern against the real expected-hit line as a verbatim fixture row with a passing branch shown reachable on known-good input, and never gate "count unchanged" with a bare count when the addition shares the pattern's vocabulary — pin a baseline diff, the old line's full shape, or a predicted total, read a delivered gate's code and prove it on the state it will gate (a PRE-constant gate passes only before the work), decide and assert on one measurement so no window refuses correct input, and when two instruments disagree on one member locate the member in the source rather than keeping the instrument that leaves the assertion green, a mutation proof asserts on the branch the mutated symbol gates, give each guard one minimal input so an earlier guard cannot shadow it, and count rows before keying a dict so a duplicate row is reported
paths: {planwise_root}/{plans_dir}/**
---
# Gate Predicate Discrimination — a Pattern Narrower Than Its Claim Passes Against Known-Bad Input

**Purpose:** A verification command runs, exits clean, and prints an accurate number that answers a different question than the one asked. The machinery is not broken. The predicate is narrower than the claim it was cited to support, so the gate returns its PASS value over input that genuinely carries the defect.

**Read this when** you are about to cite a match pattern, a count, or a diff filter as evidence — in a status block, a review finding, a briefing figure, or a session closeout. Read §6 when you write a header filter on a diff or a multi-stage pipe that ends in a "MUST be empty" predicate: basic-syntax `\+` deletes every line, and only a count of the stream proves the predicate saw input.

The failure is invisible in the passing direction. A `grep -c` returning `0` looks identical whether it scanned the defect and found it absent, or could never have matched the defect at any point, for any input. Both print `0`.

This is the predicate half of a two-part problem. [`measurement-discipline.md`](measurement-discipline.md) §8.7 owns the **input set** — the ways a gate ends up unable to fail because the thing it should have read never reached it. That section's own premise is that the input-set assertions *"are what make the gate's empty result mean anything"*. This file covers the case where the input set is complete and the **predicate** is vacuous. Both roads end at a green result over something nobody checked.

## Table of Contents

- [1. Prove the Pattern Discriminates Before Citing It as Evidence](#1-prove-the-pattern-discriminates-before-citing-it-as-evidence)
- [2. Three Corollaries on Pattern Width](#2-three-corollaries-on-pattern-width)
- [3. Case Blindness Is a Standing Hazard, and It Fires in Both Directions](#3-case-blindness-is-a-standing-hazard-and-it-fires-in-both-directions)
- [4. Never Assert a Negative From a Pattern Shaped for a Different Positive](#4-never-assert-a-negative-from-a-pattern-shaped-for-a-different-positive)
- [5. A Bad Figure in a Briefing Is Worse Than a Bad Gate](#5-a-bad-figure-in-a-briefing-is-worse-than-a-bad-gate)
- [6. Anchor a Diff Filter on the Sign Alone, and Strip Headers by Name](#6-anchor-a-diff-filter-on-the-sign-alone-and-strip-headers-by-name)
- [7. Fixture-Shape Discipline for Any Diff Instrument](#7-fixture-shape-discipline-for-any-diff-instrument)
- [8. The Author of a Check Cannot Be Its Auditor](#8-the-author-of-a-check-cannot-be-its-auditor)
- [9. A Pinned Pattern Runs Against the Real Line, and Its Passing Branch Is Reachable](#9-a-pinned-pattern-runs-against-the-real-line-and-its-passing-branch-is-reachable)
  - [9.1 The real expected-hit line is a verbatim fixture row](#91-the-real-expected-hit-line-is-a-verbatim-fixture-row)
  - [9.2 A gate whose passing value is 0 is run once on known-good input and shown to print 0](#92-a-gate-whose-passing-value-is-0-is-run-once-on-known-good-input-and-shown-to-print-0)
- [10. A "Count Unchanged" Gate Shares Vocabulary With the Addition It Must Exclude](#10-a-count-unchanged-gate-shares-vocabulary-with-the-addition-it-must-exclude)
- [11. Read a Delivered Gate's Code, and Prove It on the State It Will Gate](#11-read-a-delivered-gates-code-and-prove-it-on-the-state-it-will-gate)
- [12. Decide and Assert on the Same Measurement](#12-decide-and-assert-on-the-same-measurement)
- [13. When Two Instruments Disagree on One Member, Locate the Member in the Source](#13-when-two-instruments-disagree-on-one-member-locate-the-member-in-the-source)
- [14. A Mutation Proof Asserts on the Branch the Mutated Symbol Gates](#14-a-mutation-proof-asserts-on-the-branch-the-mutated-symbol-gates)
- [15. One Minimal Input Per Guard: a Real-Body Fixture Proves the Corpus, Not the Guard](#15-one-minimal-input-per-guard-a-real-body-fixture-proves-the-corpus-not-the-guard)
- [16. A Keyed Read Hides a Duplicate: Count Rows Before Keying](#16-a-keyed-read-hides-a-duplicate-count-rows-before-keying)

---

## 1. Prove the Pattern Discriminates Before Citing It as Evidence

§8.7 of [`measurement-discipline.md`](measurement-discipline.md) mandates the dry-run: run every gate once against input that carries the pattern and once against clean input, and require the two runs to differ. This section supplies a recipe that needs no scratch file, because for a tracked file the known-bad state is already in version control.

> [!constraint] A literal-string anchor run once, against one state, is not evidence
> **Rule.** Pair every anchor against its known-bad state from git, and report it as `HEAD-value → current-value`. An anchor that cannot be shown to move is **non-discriminating**. Report it as such. Never cite it as a pass.
>
> WRONG — literal string, single run, cited as proof:
> ```
> grep -c "owning backlog item has shipped" f.md   # 0 → "clean" (it returned 0 before the defect was fixed, too)
> ```
> CORRECT — a regex covering the claim, paired against HEAD:
> ```
> git show HEAD:f.md | grep -cE "owning (backlog )?item ship"   # 2  known-bad
> grep -cE "owning (backlog )?item ship" f.md                   # 0  current: moved, so it discriminates
> ```
> The live text read *"item shipped"* and *"item ships"*. The literal anchor matched neither, so it returned the pass value in both states.

`scripts/dry_run_pair.py --at-head <repo> <tracked-path> <pattern>` runs the pair mechanically. It exits 0 when the counts at HEAD and in the working file differ, 1 when they are equal, and 2 on usage.

An anchor accepted as a pass is quoted downstream as settled, and every later consumer inherits it without re-deriving.

---

## 2. Three Corollaries on Pattern Width

> [!constraint] A pattern that matches one spelling is evidence about that spelling only
> **Rule.** The general form: the spellings a claim covers are a set, and a pattern that matches one member is evidence about that member only.
>
> - **Match the claim, not a sentence.** Write the pattern against the concept being retired. Then verify it catches every phrasing in the pre-edit text: `"has shipped"`, `"shipped"` and `"ships"` are three surfaces of one claim.
> - **Case matters when the same word appears as prose and as a heading or label.** Use `-i`, or give the capitalised form its own anchor. A lowercase `grep -c "orphaned"` would have reported a two-line change half-landed, because one line read `**Orphaned (owner closed, content absent):**`.
> - **A placeholder is not the identifier form.** A pattern written as `{PREFIX}-[0-9]` cannot see `{PREFIX}-{NNN}`. State which identifier family a count covers.
>
> WRONG — one family's citation spelling, read as a count of every identifier:
> ```
> grep -cE '{PREFIX}-[0-9]' <corpus>   # 0 → "no identifiers"; the corpus writes {PREFIX}-{NNN} and a second family
> ```
> CORRECT — one anchor per spelling, each count labelled with the family it covers:
> ```
> grep -cE '{PREFIX}-([0-9]|\{NNN\})' <corpus>   # {PREFIX} family, both spellings
> grep -cE '{OTHER}-[0-9]' <corpus>              # the second family, reported on its own line
> ```

[`measurement-discipline.md`](measurement-discipline.md) §8.7 sub-rule A carries the narrower case, where an identifier reaches a file glued into a filename with no separator to anchor on.

---

## 3. Case Blindness Is a Standing Hazard, and It Fires in Both Directions

Case blindness fails in both directions, so it is a class rather than an anecdote.

| Direction | Instance |
|---|---|
| Audit false-negative | An orchestrator's case-sensitive search failed to find a runner's `Duplicate label`, briefly making a **correct claim look wrong**. The search was at fault, not the claim. |
| Gate false-negative | A task's after-gate `grep -n 'owner'` ran against a section titled *"Every Verification Command Names Its **O**wner"*. A correct artifact whose only occurrence is the capitalised heading **fails a gate it satisfies**. |

> [!constraint] Fix the pattern, never the wording
> **Rule.** The remedy is to fix the gate with `-i`, and never to adjust the wording to suit a case-sensitive pattern.
>
> WRONG — reword the artifact so the lowercase gate matches:
> ```
> grep -n 'owner' f.md    # no hit: the only occurrence is the heading "…Names Its Owner" → lowercase the heading
> ```
> CORRECT — fix the gate and leave the wording alone:
> ```
> grep -ni 'owner' f.md   # 1 hit, on the heading
> ```

The next author of that section has no reason to preserve a lowercase occurrence they do not know is load-bearing. A wording fix decays on the next edit, and a pattern fix does not. [`gate-artifact-over-instrument.md`](gate-artifact-over-instrument.md) §10 holds the general rule that the instrument yields to correct work.

The second direction has an adjudication half, and it already ships: [`gate-artifact-over-instrument.md`](gate-artifact-over-instrument.md) §12 governs what to do when a runner discloses that it shaped an artifact to satisfy a gate. What §3 adds is the upstream half: the pattern property that puts a runner in that position in the first place.

---

## 4. Never Assert a Negative From a Pattern Shaped for a Different Positive

> [!constraint] A negative claim needs a query whose positive result you would have believed
> **Rule.** A presence query and an absence claim are different questions. A pattern built for the first is not evidence for the second, however correct its output.
>
> WRONG — assert absence from the output of a pattern shaped for a different class of hit:
> ```
> grep -nE '## [345]\.' <file>      # returns the numbered sites
> → "these are the only ### headings in the file"     ← the pattern cannot see unnumbered ones
> ```
> CORRECT — query the class you intend to make a claim about, on its own terms:
> ```
> grep -c '^### ' <file>            # the actual population
> grep -n  '^### ' <file>           # and its members
> → "6 third-level headings; 2 are numbered (### 4.A/4.B), 4 are not"
> ```

The decision test: **if you would not have accepted this command's output as proof the class exists, do not accept its silence as proof the class is absent.**

---

## 5. A Bad Figure in a Briefing Is Worse Than a Bad Gate

The same wrong pattern costs differently depending on which register consumes it.

| Register | Bad pattern produces | Who consumes it | Failure mode |
|---|---|---|---|
| Gate | a false PASS | the verifier | defect ships unnoticed |
| Briefing figure | a false premise | the *runner*, as authoritative fact | runner acts on it, or must spend effort refuting its own orchestrator |

> [!constraint] Supply a briefing figure together with the clause that a live measurement wins
> **Rule.** A runner that trusts a briefing figure skips its own measurement, so a wrong figure **displaces** the measurement it was meant to save. Supply every figure with the standing clause that converts it into a hypothesis.
>
> WRONG — the figure is handed down as fact:
> ```
> spawn prompt: "the file has 2 ### headings"   → runner skips its own count and acts on 2
> ```
> CORRECT — the figure travels with the clause:
> ```
> spawn prompt: "the file has 2 ### headings. If a live measurement disagrees, the live measurement wins — report the disagreement."
> ```

Handing figures down is a genuine efficiency and should continue. [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md) states the clause: *"if a live measurement disagrees, the live measurement wins — report the disagreement."*

---

## 6. Anchor a Diff Filter on the Sign Alone, and Strip Headers by Name

> [!constraint] `^[+-]` and `^\+` are the safe anchors — any character class immediately after them is a candidate blind spot
> **Rule.** Anchor a diff filter on the sign alone, and remove the `+++`/`---` headers by name. A class written to remove noise can remove a whole population, such as every added or removed bullet.
>
> WRONG — excludes `+++`/`---`, and silently also excludes every added or removed bullet (`+- item`):
> ```bash
> git diff -- <path> | grep -E '^[+-][^+-]'
> # Fed a diff whose only change is `+- [Native tool use](…) — …`, this returns nothing.
> ```
> CORRECT — anchor on the sign alone and remove the headers by name:
> ```bash
> git diff -- <path> | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)'
> # For added-lines-only gates the equivalent pair is: grep '^\+' | grep -v '^+++'
> ```

**In basic syntax `\+` is a repetition operator.** GNU `grep` reads a pattern as basic syntax unless `-E` is given. A header filter written `grep -v '^\+\+\+'` therefore matches every line, and `-v` deletes every line. Write the header filter as `grep -Ev '^\+\+\+'` or `grep -v '^+++'`. Never put `\+` inside a basic pattern.

```bash
printf '+++ b/x.py\n+leak <id> here\n+clean line\n' | grep -v  '^\+\+\+'   # prints nothing, exit 1
printf '+++ b/x.py\n+leak <id> here\n+clean line\n' | grep -Ev '^\+\+\+'   # keeps both + lines
```

`scripts/lint_gate_checks_commands.py` Check 24 fires on a basic-syntax `grep` whose pattern carries `\+\+`, the shape of a diff header filter.

**Count the stream first, then run the predicate.** An empty result from a multi-stage pipe is evidence only when input reached the last stage. Report the count beside the gate result, so a reader can tell "0 hits in 1,308 lines" from "0 hits in 0 lines".

```bash
git diff $BASE -- <paths> | grep -E '^\+' | grep -Ev '^\+\+\+' | wc -l                  # MUST be > 0
git diff $BASE -- <paths> | grep -E '^\+' | grep -Ev '^\+\+\+' | grep -E '<pattern>'   # MUST be empty
```

Then inject one known-bad line: pipe one synthetic leaking line through the whole chain with `printf`. It MUST come out of the far end. Dry-run a pinned gate once, in both directions, before anyone copies it into task files. [`measurement-discipline.md`](measurement-discipline.md) §8.7 owns the input-set assertion. [`gate-positive-and-mutation-controls.md`](gate-positive-and-mutation-controls.md) §3 owns the dry-run pair.

---

## 7. Fixture-Shape Discipline for Any Diff Instrument

> [!constraint] Run a diff filter against four line shapes before trusting it
> **Rule.** Before trusting a diff filter, run it against a diff that contains a bullet, a table row, an indented code line and a plain paragraph line. If any shape vanishes and you did not intend it to, the filter is wrong.
>
> WRONG — the filter is tried on one shape:
> ```
> fixture diff: one plain paragraph line → filter keeps it → "the filter works"
> ```
> CORRECT — the fixture carries all four shapes, and each one must survive:
> ```
> fixture diff: +- a bullet / +| a | row | / +    indented code / +a plain paragraph line
> filter output: 4 lines → no character-class blind spot
> ```

Each shape exercises a different leading character, and a character-class blind spot is invisible against any single shape. Two cross-check rules follow:

- **Cross-check a "no changes" result against `git diff --name-only` or `--numstat` before concluding a file is unmodified.** A disagreement between two instruments is what caught the bullet-blind filter.
- **`--numstat` is often the better instrument outright** for "did this file change, and by how much". It cannot be fooled by line shape, and a `+1/−1` result also proves nothing else in the file moved.

---

## 8. The Author of a Check Cannot Be Its Auditor

> [!practice] Cross-reading is part of the verification design, not a happy accident
> **Rule.** A battery can be correctly executed and still miss, because the miss is in its specification. The reader who wrote the pattern reconstructs the claim from the same model that produced it, so only a different reader catches it.
>
> **A runner that surfaces an out-of-scope defect without fixing it is behaving correctly.** A status-block field that carries out-of-scope observations to the orchestrator converts a lucky read into a reliable mechanism.
>
> WRONG — the runner handles an out-of-scope defect silently:
> ```
> runner: repairs the sibling file's pattern (or ignores it) → status block: "COMPLETE, no issues"
> ```
> CORRECT — the runner routes the finding and leaves the decision to the orchestrator:
> ```
> runner: leaves the sibling file untouched → status block: "FINDING (out of scope): <file> pattern misses the capitalised form"
> ```

This section is deliberately written without a mechanical gate. "Have a different session read it" cannot be asserted by a command, and dressing it as a constraint with a fabricated verification command would reproduce the exact defect this file describes.

---

## 9. A Pinned Pattern Runs Against the Real Line, and Its Passing Branch Is Reachable

§1 pairs an anchor against its known-bad state. §2 covers how wide a pattern must be. Both assume the pattern was run over the content it is meant to judge. §9.1 and §9.2 cover two cases where nobody did that. [`gate-heuristic-verifier-patterns.md`](gate-heuristic-verifier-patterns.md) §4 covers the denominator a count gate takes, and [`gate-pinned-from-real-content.md`](gate-pinned-from-real-content.md) §11 covers a gate pinned before its subject exists.

### 9.1 The real expected-hit line is a verbatim fixture row

> [!constraint] A fixture set proves the pattern over the shapes it contains, and says nothing about a real line that is not in it
> **Rule.** When a decision names a real file and line as a pattern's expected hit, the fixture carries that line byte for byte. Not a paraphrase. Not a synthetic line of the same class. The hand-known hits in the task's success criteria are the fixture rows the classifier tests must include.
>
> Execute the pinned pattern against the real line at authoring time, before pinning it. [`gate-pinned-from-real-content.md`](gate-pinned-from-real-content.md) §11 holds the general rule that a gate is pinned from a run over real content.
>
> WRONG — the pattern is pinned in the task's API table. The expected hit is pinned in a plan decision. The fixture holds synthetic lines of the same class:
> ```
> Task API table:     VERSION_RE = r"\b(2\.1\.\d{3})\b"
> Plan decision:      "<index file> line 3 ... the scan's provenance rule reports it"
> Fixture:            pinned <tool> 2.1.200 / MEASURED = "2.1.201" / Written by <tool> 2.1.200 on 2026-01-01
> # 13 tests pass. The real line `<tool>` v2.1.261 never matches, because \b needs a word/non-word
> # transition and "v" and "2" are both word characters.
> ```
> CORRECT — the real line is a fixture row and the pattern was run against it before it was pinned:
> ```
> python -c "import re; print(re.search(r'\b(2\.1\.\d{3})\b', 'Compiled 2026-09-05 from `<tool>` v2.1.261.'))"
> # None  → the pattern is wrong before it is pinned
> VERSION_RE = r"(?<![A-Za-z0-9_.])v?(2\.1\.\d{3})(?![A-Za-z0-9_])"   # the same call prints match='v2.1.261'
> Fixture:  the decision's line verbatim, asserted under the report-only classification
> ```

### 9.2 A gate whose passing value is 0 is run once on known-good input and shown to print 0

> [!constraint] Show both branches of a gate reachable
> **Rule.** A gate has two branches, and each must be shown reachable. Run it against known-bad input to prove it can fail, and against known-good input to prove it can return its passing value. A gate that can only fail teaches its operators to explain the failure away.
>
> **Table-cell gates.** Exclude the header and separator rows before counting. Anchor on the data-row shape, such as a leading ID. Then prove both runs: known-good prints 0, and a planted annotated cell prints 1.
>
> WRONG — the header row `| ID | Blocks |` contains letters, so the count is at least 1 on every file:
> ```bash
> grep -A99 '^## Dependencies' <index>.md | grep -cE '\|[^|]*[a-zA-Z][^|]*\|$'   # header row matches → never 0
> ```
> CORRECT — anchor on the data-row shape first, then count the annotated cells:
> ```bash
> grep -A99 '^## Dependencies' <index>.md | grep -E '^\| *[0-9]{3} *\|' | grep -cE '\|[^|]*[a-zA-Z][^|]*\|$'
> # dry-run: clean file → 0 ; file with one "| 007 | 009 (soft) |" row → 1
> ```

---

## 10. A "Count Unchanged" Gate Shares Vocabulary With the Addition It Must Exclude

§1 to §9 ask whether a pattern can discriminate. This section covers a pattern that discriminates the old content and then meets new content that matches it too. [`gate-change-vs-state-detecting.md`](gate-change-vs-state-detecting.md) §11 separates change-detecting gates from state-detecting gates. [`gate-pre-edit-baseline.md`](gate-pre-edit-baseline.md) §10.3 says to mark a preservation gate with `invariant:`.

> [!constraint] A bare count that expects "unchanged" is a state-detecting instrument pointed at a change-detecting question
> **Rule.** The gate answers "how many lines match?". The criterion asks "did the old lines survive?". The two agree only when the addition shares no vocabulary with the pattern, and an addition that extends a vocabulary shares it by design.
>
> A task added a `low vs medium`, `medium vs high`, `high vs xhigh` ladder beside two fixed-baseline blocks. The ladder's `medium vs high:` lines matched the pinned pattern, so the count read 168 instead of 126 on byte-identical old blocks.
>
> WRONG — a bare count that the new output also satisfies:
> ```
> grep -c 'vs high: ' <summary>.md   # expect 126 (unchanged); reads 168 on correct work
> ```
> CORRECT — one of three shapes, in order of preference:
> ```
> # Shape 1: a baseline diff. Additions only, no d or c hunk:
> cp <summary>.md "$SCRATCH/<summary>.before.md"      # before the first edit
> diff "$SCRATCH/<summary>.before.md" <summary>.md | grep -cE '^[0-9]+(,[0-9]+)?[dc]'   # expect 0
> # Shape 2: a pattern that names the old line's full shape, which the addition cannot produce:
> grep -cE '/ (low|high|xhigh) vs high: ' <summary>.md
> # Shape 3: a count that predicts the new total, with the reason:
> # expect N_VS_HIGH + 14 x N_MODELS — the ladder's medium-high pair adds one line per task per model
> ```

Two rules follow, one for each role:

- **Author.** For every gate marked "unchanged", ask whether the addition contains the pattern. Check it against the spec's own pinned line formats. If it does, the gate is not a gate.
- **Runner.** When a correct implementation cannot satisfy a pinned count, the artifact is authoritative and the instrument is the defect. Prove the property with a stronger instrument, such as `git diff --stat` showing additions only. Report the discrepancy, and never reshape the output to satisfy the pattern. [`gate-artifact-over-instrument.md`](gate-artifact-over-instrument.md) §10 states the artifact-over-instrument rule.

**The same trap in test code.** An assertion such as `assert not any("vs high (" in line for line in lines)`, written before a sibling output type was added, fails the same way. Narrow it to the old line's full shape, for example `"vs high (median"`.

**The sibling failure from the other side.** A bare count over a content block picks up the block's own comment, because the pattern is too loose for the old content ([`gate-pinned-from-real-content.md`](gate-pinned-from-real-content.md) §11.2). Here the pattern is too loose for the new content. In both cases, count a shape instead of a token, or stop counting and diff.

---

## 11. Read a Delivered Gate's Code, and Prove It on the State It Will Gate

> [!constraint] A gate that compares a PRE-edit constant to the live subject is satisfiable only before the work it verifies
> **Rule.** Its passing run at build time is the vacuous case, because the pre-edit value already satisfies the post-edit expectation. Prove a delivered gate on the state it will actually gate.
>
> One task built a migration tool whose `verify` compared the ledger's PRE-edit footer bytes with the live file. Every building criterion passed. After the migration the same gate would have failed correct work. The orchestrator caught it by reading the 300-line script.
>
> WRONG — the gate is accepted because its declared criteria pass:
> ```
> verify: ledger.changelog_footer_bytes == live footer bytes   # 58562 == 58562 → PASS (pre-migration)
> building task criteria: all pass → accept
> # After the migration: 58562 == 90 → FAIL on correct work
> ```
> CORRECT — the gate is read, then proved against the state it will gate:
> ```
> orchestrator reads cmd_verify → sees PRE-only comparison → resumes the runner
> verify: PRE mode when live == PRE constant; POST mode parses `a + b + c = N` cells
> proof: post-migration fixture → PASS; one addend altered → FAIL (exit 1)
> ```

Three operative points:

- **Run a gate against the state it will actually gate.** If the gate runs after a migration, prove it against a post-migration fixture before accepting it. A gate that cannot pass on correct work gets routed around.
- **The orchestrator reads a delivered gate's code before accepting it.** The acceptance test is whether the orchestrator can state, from the code, what a clean POST run compares and what a corrupted run flips.
- **Make the gate state-aware and name both modes.** Keep the PRE comparison while the live subject matches the PRE constant, and otherwise run the POST check.

[`gate-positive-and-mutation-controls.md`](gate-positive-and-mutation-controls.md) §3 runs the correct post-state arm at authoring time. This section covers accepting a gate that a different task built.

---

## 12. Decide and Assert on the Same Measurement

> [!constraint] A gate that decides on one artifact and asserts on another has a window between them
> **Rule.** The window is where the gate refuses correct input. Decide on the shipped shape.
>
> An index generator's splitter measured the table body and returned one leaf under budget. The assembler then added a wrapper, re-measured the whole file, and raised an error at the budget. Inside that gap every mode exited 2, with a false message that the row could not be reduced.
>
> WRONG — the split decides on the body and the assembler measures the file:
> ```
> if estimate_tokens(body) < BUDGET:
>     return [leaf]                      # decided here
> ...
> if estimate_tokens(body + wrapper) >= BUDGET:
>     raise GeneratorError("cannot be reduced by sharding")   # asserted here
> ```
> CORRECT — one measurement, and the raise cannot fire:
> ```
> if estimate_tokens(body) + wrapper_tokens < BUDGET:   # wrapper from the real directory
>     return [leaf]
> ...
> assert estimate_tokens(body + wrapper) < BUDGET  # unreachable for any accepted body
> ```

Three operative points:

- **Decide and assert on the same measurement.** A reserve is acceptable only when it is computed from the actual wrapper, never a constant.
- **A post-assembly raise is a can't-fire assertion, not a second line of defence.** If it can fire, the first line has a hole. Write its docstring to say why it cannot fire.
- **Test the boundary, not the middle.** A boundary test places a body in `[budget − wrapper, budget)` and asserts a split, not a refusal.

In plugin development, `tests/test_index_budget_boundary.py` tests this boundary for the backlog and lessons index generators.

The rule applies to any enforcer whose decision input differs from its output artifact. The window is the size of whatever the decision did not see.

---

## 13. When Two Instruments Disagree on One Member, Locate the Member in the Source

> [!constraint] A disagreement between two instruments on one member measures the instruments, not the member
> **Rule.** Settle it by reading the source at the disputed location. Do not settle it by asking which instrument lets the existing assertion pass, because a guard that passes on the wrong evidence is exactly what an over-broad instrument produces.
>
> A test kept a local unanchored regex over the shared line-anchored one, because the swap "would flip the test from pass to fail". In the source, the disputed member appeared only in comments and in one type union, never as a map key.
>
> WRONG — pick the instrument by whether the assertion stays green:
> ```
> anchored regex   → '<member>' absent  → test would fail
> unanchored regex → '<member>' present → test passes
> → keep the unanchored regex; note "not assertion-neutral"
> ```
> CORRECT — locate every occurrence of the disputed member in the source and classify it:
> ```
> Grep  pattern='<member>'  path='<declaration-file>'  output_mode='content'  -n=true
>   772:  * ... (`<member-a>`, `<member>`)             ← comment
>  3869:  type LateOverload = '<member>' | ...          ← type-union literal
>   (no line of the shape   '<member>': ...)           ← not a map key
> → the anchored regex is right; the assertion was testing the wrong property
> ```

Three rules:

- **The tiebreaker is the source, read at the disputed location.** It is not the assertion's colour, the spec's wording, or which instrument was written first.
- **A member the broad instrument finds and the narrow one does not is a candidate false positive of the broad instrument.** It stays one until the source shows it in the claimed position.
- **When the source shows the member in a different structural position than the assertion claims, split the assertion.** Test the property the narrow instrument measures, and test the literal's presence as its own named check.

**Orchestrator-side corollary.** A runner's stated reason for keeping a duplicate ("not assertion-neutral") is a finding to verify, not a decision to accept.

[`gate-artifact-over-instrument.md`](gate-artifact-over-instrument.md) §10 (The Artifact Is Authoritative; the Instrument Is the Defect) holds the sibling rule that the artifact settles an instrument dispute.

---

## 14. A Mutation Proof Asserts on the Branch the Mutated Symbol Gates

> [!constraint] A mutation proof is a claim about one test and one symbol. The assertion must sit on a value the mutation changes
> **Rule.** A criterion "test X fails when symbol Y is changed to Z" holds only when X asserts on a value the mutation moves. A test that observes an outcome both the correct and the mutated code produce does not cover the symbol.
>
> Under `claims()` → `True`, every file claims every key, so `place()` still returns `undetermined` with both candidates. The first test stayed green and passed the mutated code.
>
> WRONG — assert on the aggregate outcome, which the mutation happens to preserve:
> ```python
> def test_placement_undetermined_when_two_files_claim():
>     result = place(["<KEY>"], [<file_a>, <file_b>])
>     assert result["<KEY>"]["undetermined"] is True     # True under claims()→True as well
>     assert set(result["<KEY>"]["candidates"]) == {<file_a>, <file_b>}
> ```
> CORRECT — assert on the predicate the mutation targets, so the mutated value is the asserted value:
> ```python
> def test_placement_undetermined_when_two_files_claim():
>     conv_a, conv_b, conv_c = (infer_convention(read_key_column(p)) for p in (<file_a>, <file_b>, <file_c>))
>     assert claims(conv_a, "<KEY>") is True
>     assert claims(conv_b, "<KEY>") is True
>     assert claims(conv_c, "<KEY>") is False             # red under claims()→True
>     result = place(["<KEY>"], [<file_a>, <file_b>, <file_c>])
>     assert result["<KEY>"]["undetermined"] is True
> ```

Three operative points:

- **Pick the mutation first, then ask which assertion its value reaches.** "Return `True` unconditionally" changes only `False` results, so the proof needs one input whose correct result is `False`, asserted directly.
- **An aggregate that is invariant under the mutation is the tell.** When the asserted value is a fixed point of the mutation, the test is not a proof.
- **Run the mutation. Do not argue coverage.** A reading of the call graph would have reported the first version as a proof.

A reviewer reading a mutation-proof claim in a status block asks which assertion turned red, not whether the mutation "was run". [`gate-positive-and-mutation-controls.md`](gate-positive-and-mutation-controls.md) §2 (A Test Whose Subject Is a Refusal Must Be Proven Load-Bearing) holds the three-step control this section sharpens.

---

## 15. One Minimal Input Per Guard: a Real-Body Fixture Proves the Corpus, Not the Guard

> [!constraint] When two guards overlap on an input, the earlier guard shadows the later one. A mutation test aimed at the later guard cannot fail on that input
> **Rule.** A fixture drawn from the real corpus proves the corpus is handled. It does not prove that the rule you think excludes a line is the rule that excludes it.
>
> A detect-and-strip pass had two refusal guards: the header-block close and fence tracking. With fence tracking disabled, the named real-body tests still passed, because the header block closed 26 lines before the fence opened. Neither guard had a test that failed without it.
>
> WRONG — the mutation criterion is attached to a real fixture, assuming which rule excludes it:
> ```
> Real fixture: a fenced example after the header block
> Criterion: "disable fence tracking → this test MUST FAIL"
> Actual: the header-block close excludes the line first; the test passes with the guard off
> ```
> CORRECT — derive one minimal input per guard, where that guard is the ONLY rule that excludes the line:
> ```
> Guard A (fence):  status line inside a fence, INSIDE the header block (no --- or ## before it)
> Guard B (close):  status line after a --- close, with no fence and no ## heading
> Mutation check:   A off → only test A fails.  B off → only test B fails.
> ```

Two rules:

- **Run the mutation before the brief asserts its outcome.** Write "each guard has a test that fails when only that guard is disabled", not "test N fails".
- **Treat real-body fixtures and edge-shape fixtures as two different obligations.** Real bytes catch encoding and line-ending hazards. Only synthetic edge shapes exercise grammar the corpus does not use yet: tilde fences, longer backtick runs, indented fences, a hit on the last line with no terminator. A destructive pass needs both kinds. [`gate-fixture-provenance.md`](gate-fixture-provenance.md) §7 (A Fixture Set Must Span Input SHAPES, Not Only Families) holds the shape rule.

---

## 16. A Keyed Read Hides a Duplicate: Count Rows Before Keying

> [!constraint] A dict keyed by id is a lossy read. Count rows as you walk, before you key
> **Rule.** Two rows with one id become one entry, and which one survives depends on file order. Treat a repeated key as data to report, not a collision to resolve.
>
> A generator's `--check` read the index into `{id: cells}`. A planted duplicate row reported clean unless the corrupted copy came last, because the dict write kept the last copy.
>
> WRONG — key on the way in, and let the last copy win:
> ```
> rows_by_id = {}
> for line in table_lines:
>     cells = split_row_cells(line)
>     rows_by_id[cells[COL_ID]] = cells        # second copy overwrites the first
> ```
> CORRECT — count, detect the repeat, quarantine, report:
> ```
> rows_by_id, seen, duplicates, walked = {}, set(), set(), 0
> for line in table_lines:
>     walked += 1
>     cells = split_row_cells(line)
>     item_id = cells[COL_ID]
>     if item_id in seen:
>         duplicates.add(item_id)
>         continue
>     seen.add(item_id)
>     rows_by_id[item_id] = cells
> for item_id in duplicates:
>     rows_by_id.pop(item_id)                 # a repeated id leaves the map entirely
> anomalies += [f"duplicate row for id {i}" for i in sorted(duplicates)]
> assert walked == len(table_lines)            # the walk saw every row, before any keying
> ```

Three operative points:

- **Count rows as you walk, before you key.** Quarantine a repeated id from the map entirely, and report it as an anomaly that names the id. Never last-wins, never silently healed.
- **A two-part contract needs both parts probed.** "Row count equals table count, and cell count equals header count" is two checks. The acceptance gate names the corruption each half catches and drives it.
- **Test a parity check with the corruption it exists for.** A row-count check can see only a duplicate, so test it with a duplicate.

The rule applies to any reader that builds a map from a sequence with a supposedly unique key: index tables, config lists, manifest entries, CSV imports.

---

*Cross-reference: [`measurement-discipline.md`](measurement-discipline.md) §8.7 (the gate's input set — the other half of an unfalsifiable gate, and the dry-run mandate this file gives a recipe for) · [`gate-artifact-over-instrument.md`](gate-artifact-over-instrument.md) §12 (adjudicating a disclosure that a gate shaped its own subject) · [`gate-positive-and-mutation-controls.md`](gate-positive-and-mutation-controls.md) §3 (the correct-post-state arm of the dry-run) · [`gate-diff-baseline-pinning.md`](gate-diff-baseline-pinning.md) §8 (the recorded baseline a diff-scoped gate pins) · [`gate-command-semantics.md`](gate-command-semantics.md) §10.9 (reading a gate command as a program) and [`gate-pinned-from-real-content.md`](gate-pinned-from-real-content.md) §11 (a gate pinned from a run over real content) · [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md) (the live-measurement-wins clause a briefing figure travels with)*
