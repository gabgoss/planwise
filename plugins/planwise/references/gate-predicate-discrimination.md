---
description: A gate whose pattern is narrower than the claim it is cited to support returns its PASS value against known-bad input. Covers the paired-input control taken from version control, the three ways a pattern ends up narrower than its claim, case blindness in both directions, asserting a negative from a pattern shaped for a different positive, why a wrong figure in a briefing costs more than a wrong gate, the diff-filter character class that silently drops a whole syntactic population, and the pinned pattern that must run against the real expected-hit line (a verbatim fixture row) with a passing branch shown reachable on known-good input, and the "count unchanged" gate that an addition sharing its vocabulary makes unsatisfiable (pin a baseline diff, the old line's full shape, or a predicted total), the delivered gate that compares a PRE-edit constant and passes only before the work it verifies (read its code, prove it on the state it will gate, make it two-mode), the enforcer that decides on one measurement and asserts on another (decide and assert on the same measurement), and two instruments that disagree on one member (locate the member in the source, never pick the instrument that keeps the assertion green), the mutation proof whose assertion must sit on the branch the mutated symbol gates, one minimal input per guard so an earlier guard cannot shadow a later one, and the keyed read that hides a duplicate row (count rows before keying). Consult when about to cite a grep, a count, or a diff filter as proof.
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

§8.7 of [`measurement-discipline.md`](measurement-discipline.md) mandates the dry-run: run every gate once against input that genuinely carries the pattern and once against clean input, and require the two runs to differ. What it does not give is the recipe. This section supplies one that needs no scratch file, because for a tracked file the known-bad state is already in version control.

```bash
# The paired-input control — no scratch file, no shipped-tree pollution:
git show HEAD:path/to/file.md | grep -cE "$PATTERN"   # known-bad  → expect N
grep -cE "$PATTERN" path/to/file.md                   # current    → expect M, M ≠ N
```

Report each anchor as `HEAD-value → current-value`. An anchor that cannot be shown to move is **non-discriminating**. Report it as such. Never cite it as a pass.

> [!constraint] A literal-string anchor run once, against one state, is not evidence
> ```
> WRONG — literal string, single run, cited as proof:
>   grep -c "owning backlog item has shipped" f.md   # 0  → "clean"
>   (returned 0 before the defect was fixed, too)
>
> CORRECT — regex covering the claim, paired against HEAD:
>   git show HEAD:f.md | grep -cE "owning (backlog )?item ship"   # 2
>   grep -cE "owning (backlog )?item ship" f.md                   # 0   ← moved, so it discriminates
> ```
> The live text read *"item shipped"* and *"item ships"*. The anchor was written against a third phrasing that appeared nowhere, so it returned the pass value in both states. A single clean run is consistent with "the defect is absent" and with "this pattern cannot see the defect", and those two readings are indistinguishable from the output alone.

The cost of skipping the control is not the one run you save. An anchor accepted as a pass is quoted downstream as settled, and every later consumer inherits it without re-deriving.

---

## 2. Three Corollaries on Pattern Width

Each is a real miss, and each is a different mechanism by which a pattern ends up narrower than the claim it stands for.

**Match the claim, not a sentence.** Write the pattern against the *concept* being retired, then verify it catches every phrasing present in the pre-edit text. `"has shipped"`, `"shipped"` and `"ships"` are three surfaces of one claim. A pattern anchored on the first is silent on the other two.

**Case matters when the same word appears as prose and as a heading or label.** Use `-i`, or give the capitalised form its own anchor. A lowercase `grep -c "orphaned"` proposed to verify a two-line change would have reported the work half-landed, because one of the two lines read `**Orphaned (owner closed, content absent):**`.

**A placeholder is not the identifier form.** A pattern written as `{PREFIX}-[0-9]` cannot see `{PREFIX}-{NNN}`, and a sweep scoped to one identifier family under-counts a corpus that carries several. State which family a count covers. [`measurement-discipline.md`](measurement-discipline.md) §8.7 sub-rule A carries the narrower case of this, where the same identifier reaches a file glued into a filename with no separator for the pattern to anchor on. The general form is the one stated here: **the spellings a claim covers are a set, and a pattern that matches one member is evidence about that member only.**

---

## 3. Case Blindness Is a Standing Hazard, and It Fires in Both Directions

A hazard shown to fail in both directions is a class rather than an anecdote. Both directions are cheap to produce and neither announces itself.

| Direction | Instance |
|---|---|
| Audit false-negative | An orchestrator's case-sensitive search failed to find a runner's `Duplicate label`, briefly making a **correct claim look wrong**. The search was at fault, not the claim. |
| Gate false-negative | A task's after-gate `grep -n 'owner'` ran against a section titled *"Every Verification Command Names Its **O**wner"*. A correct artifact whose only occurrence is the capitalised heading **fails a gate it satisfies**. |

The remedy is to fix the gate — `grep -ni 'owner'` — and never to adjust the wording. The next author of that section has no reason to preserve a lowercase occurrence they do not know is load-bearing, so a wording fix decays on the next edit while a pattern fix does not.

The second direction has an adjudication half, and it already ships: [`verification-gate-evidence.md`](verification-gate-evidence.md) §12 governs what to do when a runner discloses that it shaped an artifact to satisfy a gate. Read it alongside this section rather than re-deriving it. What §3 adds is the upstream half — the pattern property that puts a runner in that position in the first place.

---

## 4. Never Assert a Negative From a Pattern Shaped for a Different Positive

A presence query and an absence claim are different questions. A pattern built for the first is not evidence for the second, however correct its output.

> [!constraint] A negative claim needs a query whose positive result you would have believed
> ```
> WRONG — assert absence from the output of a pattern shaped for a different class of hit:
>   grep -nE '## [345]\.' <file>      # returns the numbered sites
>   → "these are the only ### headings in the file"     ← the pattern cannot see unnumbered ones
>
> CORRECT — query the class you intend to make a claim about, on its own terms:
>   grep -c '^### ' <file>            # the actual population
>   grep -n  '^### ' <file>           # and its members
>   → "6 third-level headings; 2 are numbered (### 4.A/4.B), 4 are not"
> ```
> The true count was 6, not 2. The presence query was correct for the question it asked, and the answer was written into a runner's spawn prompt as an absence claim about a different question.

The decision test is the memorable form: **if you would not have accepted this command's output as proof the class exists, do not accept its silence as proof the class is absent.**

---

## 5. A Bad Figure in a Briefing Is Worse Than a Bad Gate

The same wrong pattern costs differently depending on which register consumes it.

| Register | Bad pattern produces | Who consumes it | Failure mode |
|---|---|---|---|
| Gate | a false PASS | the verifier | defect ships unnoticed |
| Briefing figure | a false premise | the *runner*, as authoritative fact | runner acts on it, or must spend effort refuting its own orchestrator |

A briefing figure is handed down with institutional weight, so a runner that trusts it skips its own measurement — which is exactly the efficiency the figure exists to buy. A wrong figure does not merely fail to help. It **displaces** the correct measurement it was meant to substitute for.

The corrective is not to stop supplying figures. Handing them down is a genuine efficiency and should continue. What makes it safe is the standing clause every spawn prompt carries, stated in [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md): *"if a live measurement disagrees, the live measurement wins — report the disagreement."* That clause converts an orchestrator error from a directive into a hypothesis. Supply the figure, and supply the clause with it.

---

## 6. Anchor a Diff Filter on the Sign Alone, and Strip Headers by Name

A filter written to remove *noise* can remove a *population*, and the two are indistinguishable in the output.

> [!constraint] `^[+-]` and `^\+` are the safe anchors — any character class immediately after them is a candidate blind spot
> ```bash
> # WRONG — excludes +++/---, and silently also excludes every added or removed bullet (`+- item`):
> git diff -- <path> | grep -E '^[+-][^+-]'
> # Fed a diff whose only change is `+- [Native tool use](…) — …`, this returns nothing,
> # and the change reads as "file unmodified".
>
> # CORRECT — anchor on the sign alone and remove the headers by name:
> git diff -- <path> | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)'
> # For added-lines-only gates the equivalent pair is: grep '^\+' | grep -v '^+++'
> ```

Markdown documentation is mostly bullets and tables, so a diff filter blind to bullets is blind to much of what a documentation change actually is. The `[^+-]` class was written to exclude two header shapes. It also excludes every line whose first content character is `-` or `+`, which is every list item in the corpus the filter was aimed at.

> [!constraint] In basic syntax `\+` is a repetition operator, and the stream that reaches the predicate must be counted
> GNU `grep` reads a pattern as basic syntax unless `-E` is given. There, `\+` means "one or more of the preceding item". It is not a literal plus. A header filter written `grep -v '^\+\+\+'` therefore matches every line, and `-v` deletes every line. Every predicate after it reads an empty stream.
> ```bash
> printf '+++ b/x.py\n+leak <id> here\n+clean line\n' | grep -v  '^\+\+\+'   # prints nothing, exit 1
> printf '+++ b/x.py\n+leak <id> here\n+clean line\n' | grep -Ev '^\+\+\+'   # keeps both + lines
> ```
> Write the header filter in syntax that cannot be misread. Use `grep -Ev '^\+\+\+'`, where extended syntax makes `\+` a literal plus. Or use `grep -v '^+++'`, where basic syntax makes a bare `+` literal. Never put `\+` inside a basic pattern.
>
> An empty result from a multi-stage pipe is evidence only when input reached the last stage. Count the stream first, then run the predicate:
> ```bash
> # WRONG — trust the empty result:
> git diff $BASE -- <paths> | grep -E '^\+' | grep -v '^\+\+\+' | grep -E '<pattern>'    # empty -> "PASS"
>
> # CORRECT — prove the stream is live, then run the predicate:
> git diff $BASE -- <paths> | grep -E '^\+' | grep -Ev '^\+\+\+' | wc -l                  # MUST be > 0
> git diff $BASE -- <paths> | grep -E '^\+' | grep -Ev '^\+\+\+' | grep -E '<pattern>'   # MUST be empty
> ```
> On a diff that adds lines, the count MUST be above zero. Report it beside the gate result, so a reader can tell "0 hits in 1,308 lines" from "0 hits in 0 lines".
>
> Then inject one known-bad line. Pipe one synthetic leaking line through the whole chain with `printf`. It MUST come out of the far end. A chain that swallows it cannot report a real leak either.
>
> A defect in a pinned template spreads to every file that copies the template. Dry-run a pinned gate once, in both directions, before anyone copies it into task files. [`measurement-discipline.md`](measurement-discipline.md) §8.7 owns the input-set assertion. [`verification-gate-evidence.md`](verification-gate-evidence.md) §3 owns the dry-run pair.

---

## 7. Fixture-Shape Discipline for Any Diff Instrument

Before trusting a diff filter, run it against a diff containing all four of these shapes:

- a bullet
- a table row
- an indented code line
- a plain paragraph line

If any of the four vanishes and you did not intend it to, the filter is wrong. Four shapes is the minimum set because each exercises a different leading character, and a character-class blind spot is invisible against any single shape.

Two cross-check rules follow:

- **Cross-check a "no changes" result against `git diff --name-only` or `--numstat` before concluding a file is unmodified.** Disagreement between two instruments is cheaper to notice than a false negative accepted downstream. It is what caught the bullet-blind filter.
- **`--numstat` is often the better instrument outright** for "did this file change, and by how much". It cannot be fooled by line shape at all, and a `+1/−1` result additionally proves nothing *else* in the file moved. That is stronger evidence than a battery of per-symbol searches.

---

## 8. The Author of a Check Cannot Be Its Auditor

> [!practice] Cross-reading is part of the verification design, not a happy accident
> A battery can be **correctly and thoroughly executed** and still miss, because the miss is in the battery's *specification* rather than its execution. Two of the instances in this file were caught only because a different session, holding a different brief, read the artifact for an unrelated reason. No self-check replaces that, because the reader who wrote the pattern reconstructs the claim from the same model that produced the pattern.
>
> Route the finding, rather than relying on the reader. **A runner that surfaces an out-of-scope defect without fixing it is behaving correctly.** Findings reach a decision only when a runner reports them in a status block instead of silently repairing them or silently ignoring them. Both silent options are always available, and neither leaves a trace. A status-block field that carries out-of-scope observations to the orchestrator is what converts a lucky read into a reliable mechanism.

This section is deliberately written without a mechanical gate. "Have a different session read it" cannot be asserted by a command, and dressing it as a constraint with a fabricated verification command would reproduce the exact defect this file describes.

---

## 9. A Pinned Pattern Runs Against the Real Line, and Its Passing Branch Is Reachable

§1 pairs an anchor against its known-bad state. §2 covers how wide a pattern must be. Both assume the pattern was run over the content it is meant to judge. This section covers two cases where nobody did that. In the first, a plan pins a pattern in one place and its expected real-world hit in another. In the second, the gate can fail but cannot return its passing value. [`verification-task-authoring.md`](verification-task-authoring.md) §4 covers the denominator a count gate takes, and §11 there covers a gate pinned before its subject exists.

### 9.1 The real expected-hit line is a verbatim fixture row

> [!constraint] A fixture set proves the pattern over the shapes it contains, and says nothing about a real line that is not in it
> **Rule.** A plan that pins a pattern in one place and the pattern's expected real-world hit in another has made two claims that nobody executed against each other. The fixture set proves the pattern over the shapes the fixture set contains. It says nothing about the real target line unless that line is in the set verbatim.
>
> Two operative points:
>
> 1. **When a decision names a real file and line as the expected hit, the fixture carries that line byte for byte.** Not a paraphrase. Not a synthetic line of the same class. The hand-known hits in the task's success criteria are the fixture rows the classifier tests must include.
> 2. **Execute the pinned pattern against the real line at authoring time, before pinning it.** One interpreter call settles it.
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
> VERSION_RE = r"(?<![A-Za-z0-9_.])v?(2\.1\.\d{3})(?![A-Za-z0-9_])"
> Fixture:  the decision's line verbatim, asserted under the report-only classification
> ```
> Dry run of the two patterns against that line: the boundary form printed `None` and the lookaround form printed `<re.Match object; span=(34, 42), match='v2.1.261'>`.

**Applies to.** Any task file that pins a regex, glob or grep pattern AND any plan decision that names a specific real file and line as that pattern's expected hit: scanners, linters, citation checkers, hand-check criteria. Especially when the fixture set is authored from the task table rather than copied from the real target.

### 9.2 A gate whose passing value is 0 is run once on known-good input and shown to print 0

> [!constraint] Show both branches of a gate reachable
> **Rule.** A gate has two branches, and each must be shown reachable. The usual discipline dry-runs a gate against known-bad input to prove it can fail. It is just as necessary to run it against known-good input to prove it can return its passing value. A gate that can only fail teaches its operators to explain the failure away. That is worse than no gate on a check whose failure is unrecoverable.
>
> **Table-cell gates.** Exclude the header and separator rows before counting. Skip the first two lines under the heading, or anchor on the data-row shape, such as a leading ID. Then prove both runs: known-good prints 0, and a planted annotated cell prints 1.
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
> Dry run on a scratch table with a header row and no annotated cells: the WRONG form printed 1, and the CORRECT form printed 0. With one `| 007 | 009 (soft) |` row added, the CORRECT form printed 1.

**Applies to.** Any `grep -c` or `awk` count gate over a markdown table, and any gate whose passing value is 0. Run it once against a known-good input and record that it printed 0.

---

## 10. A "Count Unchanged" Gate Shares Vocabulary With the Addition It Must Exclude

§1 to §9 ask whether a pattern can discriminate. This section covers a gate whose pattern discriminates the old content and then meets new content that matches it too. [`verification-gates.md`](verification-gates.md) §11 separates change-detecting gates from state-detecting gates. [`verification-task-authoring.md`](verification-task-authoring.md) §10.3 says to mark a preservation gate with `invariant:`. Neither says how to build the preservation gate when the addition shares the pattern's vocabulary.

> [!constraint] A bare count that expects "unchanged" is a state-detecting instrument pointed at a change-detecting question
> **Rule.** The gate answers "how many lines match?". The criterion asks "did the old lines survive?". The two have the same answer only when the addition shares no vocabulary with the pattern. An addition that extends a vocabulary shares it by design: a third block beside two, a new pair beside existing pairs, a new row type in the same table.
>
> **Example.** A task adds an adjacent-level ladder (`low vs medium`, `medium vs high`, `high vs xhigh`) to two scorers. The success criterion is that the two existing fixed-baseline blocks stay byte-identical. The pinned gates were:
> ```
> grep -c 'vs high: ' <summary>.md          # expect N_VS_HIGH (unchanged)
> grep -c 'vs high (' <review>.md           # expect 6 (unchanged from the previous run)
> ```
> The ladder's middle pair is `medium vs high`. Its lines read `- <task> / medium vs high: HOLDS` and `- medium vs high (adjacent, median defects found of 10): HOLDS`. Both contain the pinned pattern. The counts read 168 instead of 126 and 8 instead of 6. The old blocks were byte-identical. The same task file pinned the line format that guaranteed the collision.
>
> WRONG — a bare count that the new output also satisfies:
> ```
> grep -c 'vs high: ' <summary>.md   # expect 126 (unchanged)
> # The addition's own "medium vs high:" lines match. It reads 168 on correct work.
> ```
> CORRECT — one of three shapes, in order of preference.
>
> **Shape 1: a baseline diff.** Pin a copy before the first edit and assert the diff shape: additions only, no `d` or `c` hunk, the old lines present in order. This proves the old block survived without naming any pattern.
> ```
> cp <summary>.md "$SCRATCH/<summary>.before.md"      # before the first edit
> diff "$SCRATCH/<summary>.before.md" <summary>.md | grep -cE '^[0-9]+(,[0-9]+)?[dc]'   # expect 0
> ```
> **Shape 2: a pattern that names the old line's full shape**, including the part the new line will not have. The fixed-baseline line is `- <task> / <level> vs high: <verdict>` under a heading that reads `hold against high?`. The ladder's line is `- <task> / medium vs high: <verdict>` under a heading that reads `adjacent ladder`. Count inside the old section, or count a shape the addition cannot produce:
> ```
> sed -n '/hold against high?/,/^##/p' <summary>.md | grep -c 'vs high: '
> grep -cE '/ (low|high|xhigh) vs high: ' <summary>.md
> ```
> **Shape 3: a count that predicts the new total**, with the reason: `# expect N_VS_HIGH + 14 x N_MODELS — the ladder's medium-high pair adds one line per task per model`. The gate two lines below the wrong one already did this for `vs xhigh: `. The author applied the arithmetic to one pattern and not to its neighbour.
>
> Dry run on a scratch summary of four old `vs high: ` lines, with two ladder lines appended. The bare count printed 6 where 4 was expected. The shape 1 diff census printed 0 on the additions-only file and 1 after one old line was edited. The shape 2 section-scoped count and the full-shape count each printed 4.

Two rules follow, one for each role.

- **Author.** For every gate marked "unchanged", ask whether the addition being gated contains the pattern. Check it against the spec's own pinned line formats, which sit in the same file. If it does, the gate is not a gate.
- **Runner.** When a correct implementation cannot satisfy a pinned count, the artifact is authoritative and the instrument is the defect. Prove the property the gate stood in for with a stronger instrument, such as `git diff --stat` showing additions only and zero deletions. Report the discrepancy. Never reshape the output to satisfy the pattern. [`verification-gate-evidence.md`](verification-gate-evidence.md) §10 states the artifact-over-instrument rule.

**The same trap in test code.** A test assertion such as `assert not any("vs high (" in line for line in lines)`, written before a sibling output type was added, fails the same way. Narrow it to the old line's full shape, for example `"vs high (median"`.

**The sibling failure from the other side.** A bare count over a content block picks up the block's own comment, because the pattern is too loose for the old content ([`verification-task-authoring-Part-2-PinnedFromRealContent.md`](verification-task-authoring-Part-2-PinnedFromRealContent.md) §11.2). Here the pattern is too loose for the new content. In both cases, count a shape instead of a token, or stop counting and diff.

**Applies to.** Any task-file verification block that pairs "add X beside Y" with "count of Y-pattern unchanged". Test assertions written before a sibling output type was added. Generated reports where a new section reuses an existing section's line vocabulary: decision blocks, verdict lines, comparison tables.

---

## 11. Read a Delivered Gate's Code, and Prove It on the State It Will Gate

> [!constraint] A gate that compares a PRE-edit constant to the live subject is satisfiable only before the work it verifies
> Its passing run at build time is the vacuous case. The pre-edit value already satisfies the post-edit expectation. The run proves the gate can print PASS. It proves nothing about whether the gate can detect anything.
>
> One task built a migration tool with a `verify` subcommand. A later task would run it as the session's conservation gate. That later task had to show PASS on the clean ledger and FAIL on a corrupted copy. The runner's `verify` read the ledger's PRE-edit footer and block byte counts and compared them with the live file.
>
> Every success criterion of the building task passed. Lint was clean and the dry-run pairs discriminated. `verify` returned PASS because nothing had been migrated yet. After the footer was replaced, the same gate would have reported FAIL on correct work. The later task would have had to fail the session or route around its only gate. The orchestrator caught it by reading the 300-line script before accepting the task.
>
> ```
> WRONG — the gate is accepted because its declared criteria pass:
> verify: ledger.changelog_footer_bytes == live footer bytes   # 58562 == 58562 → PASS (pre-migration)
> building task criteria: all pass → accept
> # After the migration: 58562 == 90 → FAIL on correct work
>
> CORRECT — the gate is read, then proved against the state it will gate:
> orchestrator reads cmd_verify → sees PRE-only comparison → resumes the runner
> verify: PRE mode when live == PRE constant; POST mode parses `a + b + c = N` cells
> proof: post-migration fixture → PASS; one addend altered → FAIL (exit 1)
> ```
>
> Dry run on a scratch gate that compares a PRE constant. The PRE-only form printed PASS on the pre-migration fixture and FAIL on the post-migration fixture. The two-mode form printed PASS on both fixtures and FAIL after one addend was altered.

Three operative points:

- **Run a gate against the state it will actually gate.** If the gate runs after a migration, prove it against a post-migration fixture before accepting it. A gate that cannot pass on correct work gets routed around, which is worse than no gate.
- **The orchestrator reads a delivered gate's code before accepting it.** The acceptance test for a tool that will judge later tasks is not "its criteria passed". It is "the orchestrator can state, from the code, what a clean POST run compares and what a corrupted run flips". This cost one Read of a 300-line file.
- **Make the gate state-aware and name both modes.** The fix kept the PRE comparison while the live footer matched the PRE constant and otherwise parsed the ledger's POST cells. The proving task then showed that the POST mode flips exactly one line when one addend is altered.

**Applies to** any DELEGATED session where one task builds the instrument that a later task uses as a gate. It matters most for conservation, round-trip and drift checks whose subject changes between the build and the gate run. [`verification-gate-evidence.md`](verification-gate-evidence.md) §3 runs the correct post-state arm at authoring time. This section covers accepting a gate that a different task built.

---

## 12. Decide and Assert on the Same Measurement

> [!constraint] A gate that decides on one artifact and asserts on another has a window between them
> The window is where the gate refuses correct input. Decide on the shipped shape.
>
> A backlog index generator enforces a 22,000-token budget per file by sharding. Its splitter measured the table body and returned one leaf when the body was under budget. The assembler then added a `Generated:` line and a `## Shards` directory, re-measured the whole file, and raised an error when the total reached the budget. Nothing between those two points split.
>
> The gap was about one wrapper's worth of tokens. On the real corpus it sat at open rows 267 and 268, about 84 rows from the live count. Inside it every mode exited 2, and the message said a single row could not be reduced by sharding, which was false. One more row and the same input split cleanly. Four tasks passed their criteria and 823 tests were green. A design review's probe found the window by placing a body at 21,980 tokens on purpose.
>
> ```
> WRONG — the split decides on the body and the assembler measures the file:
> if estimate_tokens(body) < BUDGET:
>     return [leaf]                      # decided here
> ...
> if estimate_tokens(body + wrapper) >= BUDGET:
>     raise GeneratorError("cannot be reduced by sharding")   # asserted here
>
> CORRECT — one measurement, and the raise cannot fire:
> if estimate_tokens(body) + wrapper_tokens < BUDGET:   # wrapper from the real directory
>     return [leaf]
> ...
> assert estimate_tokens(body + wrapper) < BUDGET  # unreachable for any accepted body
> ```

Three operative points:

- **Decide and assert on the same measurement.** If the ship check measures bytes with the wrapper, the split decision measures bytes with the wrapper. A reserve is acceptable only when it is computed from the actual wrapper, never a constant. The wrapper here grows with every archive century.
- **A post-assembly raise is a can't-fire assertion, not a second line of defence.** If it can fire, the first line has a hole. Write its docstring to say why it cannot fire.
- **Test the boundary, not the middle.** The fixture that "must split" used rows three times denser than the budget. The fixture that "fits" used half. Neither visited the window. The boundary test binary-searches a body into `[budget − wrapper, budget)` and asserts a split, not a refusal. It carries a guard that the pre-fix condition held.

**Applies to** any enforcer whose decision input differs from its output artifact: a pagination that measures rows but ships headers, a chunker that counts content but emits envelopes, a budget that measures a body and ships a wrapper. The window is the size of whatever the decision did not see.

---

## 13. When Two Instruments Disagree on One Member, Locate the Member in the Source

> [!constraint] A disagreement between two instruments on one member measures the instruments, not the member
> Settle it by reading the source at the disputed location. Do not settle it by asking which instrument lets the existing assertion pass. That question cannot discriminate. A guard that passes on the wrong evidence is exactly what an over-broad instrument produces.
>
> A test file carried a local copy of an extractor regex, written before the shared module landed:
> ```python
> RE_KEY_LOCAL = re.compile(r"'([a-zA-Z][a-zA-Z0-9]*\.[a-zA-Z0-9]+)'")   # any single-quoted dotted string, anywhere
> ```
> The shared module landed with the line-anchored form its design spec had calibrated to 66 → 77 keys on the pinned pair of files:
> ```python
> RE_KEY_SHARED = re.compile(r"""^\s*['"]([a-z]+\.[A-Za-z]+)['"]\s*:""", re.M)   # a quoted key at line start, followed by ':'
> ```
> A later task said to replace the duplicate with an import if the swap was assertion-neutral. The runner found that the two regexes disagreed on one member the guard asserts, `<member>`. It kept the local regex and reported "replacing would flip the test from pass to fail on the real file".
>
> The orchestrator located the member by script in the pinned declaration file. The anchored regex found 84 keys, and none starts with the member's prefix. The string occurs only in comments and in one type union (`type LateOverload = '<member>' | … ;`). The members of that family are template-typed, not listed in the event map. The local regex had matched a type literal. The guard would have stayed green if every real overload were deleted.
>
> ```
> WRONG — pick the instrument by whether the assertion stays green:
> anchored regex   → '<member>' absent  → test would fail
> unanchored regex → '<member>' present → test passes
> → keep the unanchored regex; note "not assertion-neutral"
>
> CORRECT — locate every occurrence of the disputed member in the source and classify it:
> Grep  pattern='<member>'  path='<declaration-file>'  output_mode='content'  -n=true
>   772:  * ... (`<member-a>`, `<member>`)             ← comment
>  3869:  type LateOverload = '<member>' | ...          ← type-union literal
>   (no line of the shape   '<member>': ...)           ← not a map key
> → the anchored regex is right; the assertion was testing the wrong property
> → assert genuine keys with the anchored regex; assert the type literal
>   separately as a presence check that says what it is
> ```
>
> Dry run on a scratch declaration that carries `ui.lateThing` only in a comment and in a type union, beside two real map keys. The unanchored regex returned four members, including `ui.lateThing`. The anchored regex returned the two real keys and not `ui.lateThing`. The two outputs differ, so the pair discriminates.

Three rules:

- **The tiebreaker is the source, read at the disputed location.** It is not the assertion's colour, the spec's wording, or which instrument was written first.
- **A member the broad instrument finds and the narrow one does not is a candidate false positive of the broad instrument.** It stays one until the source shows it in the claimed position. Treat "the broad one finds more" as suspicion, not coverage.
- **When the source shows the member in a different structural position than the assertion claims, split the assertion.** Test the property the narrow instrument measures. Test the literal's presence as its own named check. Do not loosen the instrument so one assertion covers both.

**Orchestrator-side corollary.** A runner's stated reason for keeping a duplicate ("not assertion-neutral") is a finding to verify, not a decision to accept. Settling it cost one 15-line script.

**Applies to** any guard that reads a structured file with a regex, where a second, differently anchored regex exists for the same field (a shared parser module versus a test-local copy). It applies when a local duplicate is replaced by an import from the module under test. It applies to declaration, JSON, YAML and minified-bundle extractors where one identifier appears in comments, type unions, docstrings and examples as well as in the position that matters. [`verification-gate-evidence.md`](verification-gate-evidence.md) §10 (The Artifact Is Authoritative; the Instrument Is the Defect) holds the sibling rule that the artifact settles an instrument dispute.

---

## 14. A Mutation Proof Asserts on the Branch the Mutated Symbol Gates

> [!constraint] A mutation proof is a claim about one test and one symbol. The assertion must sit on a value the mutation changes
> A criterion of the form "test X fails when symbol Y is changed to Z" holds only when X asserts on a path whose value the mutation moves. A test that observes an outcome both the correct code and the mutated code produce does not cover the symbol. Calling through the symbol many times does not change that.
>
> A criterion required that `test_placement_undetermined_when_two_files_claim` fail when `claims()` is changed to return `True` unconditionally. The first version called `place([...], [<file-a>, <file-b>])` and asserted `undetermined: True` with both files in `candidates`. Under the mutation every file claims every key. The key still has two or more claimants, so `place()` still returns `undetermined` with the full candidate list. The test stayed green, and the proof passed the mutated code.
>
> The runner rewrote the test to call `claims()` directly, re-ran the mutation (red), restored the code, and re-verified green. The criterion caught the defect only because the runner ran the mutation. Reasoning that the test "covers" `claims()` would have accepted the first version.
>
> ```python
> # WRONG — assert on the aggregate outcome, which the mutation happens to preserve:
> def test_placement_undetermined_when_two_files_claim():
>     result = place(["<KEY>"], [<file_a>, <file_b>])
>     assert result["<KEY>"]["undetermined"] is True     # True under claims()→True as well
>     assert set(result["<KEY>"]["candidates"]) == {<file_a>, <file_b>}
>
> # CORRECT — assert on the predicate the mutation targets, so the mutated value is the asserted value:
> def test_placement_undetermined_when_two_files_claim():
>     conv_a, conv_b, conv_c = (infer_convention(read_key_column(p)) for p in (<file_a>, <file_b>, <file_c>))
>     assert claims(conv_a, "<KEY>") is True
>     assert claims(conv_b, "<KEY>") is True
>     assert claims(conv_c, "<KEY>") is False             # red under claims()→True
>     result = place(["<KEY>"], [<file_a>, <file_b>, <file_c>])
>     assert result["<KEY>"]["undetermined"] is True
> ```

Three operative points:

- **Pick the mutation first, then ask which assertion its value reaches.** "Return `True` unconditionally" changes `claims()`'s `False` results. The proof needs at least one input whose correct result is `False`, asserted directly.
- **An aggregate that is invariant under the mutation is the tell.** `undetermined` is the answer for "two or more claimants" and for "every file claims". A mutation that only adds claimants cannot move it. When the asserted value is a fixed point of the mutation, the test is not a proof.
- **Run the mutation. Do not argue coverage.** A reading of the call graph would have reported the first version as a proof.

**Applies to** any criterion of the form "test X fails when Y is changed to Z". Write the proof against Y's return value, not a downstream aggregate. It matters most for predicates consumed by a classifier that maps many predicate outcomes to one label (`undetermined`, `skipped`, `none`). A reviewer reading a mutation-proof claim in a status block asks which assertion turned red, not whether the mutation "was run". [`verification-gate-evidence.md`](verification-gate-evidence.md) §2 (A Test Whose Subject Is a Refusal Must Be Proven Load-Bearing) holds the three-step control this section sharpens.

---

## 15. One Minimal Input Per Guard: a Real-Body Fixture Proves the Corpus, Not the Guard

> [!constraint] When two guards overlap on an input, the earlier guard shadows the later one. A mutation test aimed at the later guard cannot fail on that input
> A fixture drawn from the real corpus proves the corpus is handled. It does not prove that the rule you think excludes a line is the rule that excludes it.
>
> A detect-and-strip pass removes a legacy `**Status:**` line from item files. It has two refusal guards. The header-block close stops the scan at the first `---` line or the first `## ` heading. Fence tracking skips lines inside a fenced code block. The brief named 18 tests built byte-for-byte from real item files and said "disable fence tracking, and tests 4-5 MUST FAIL".
>
> With fence tracking disabled, tests 4-5 still passed. That item's header block closed at a `---` line on line 16, and the fence opened 26 lines later. The header-block rule excluded the line first, so the fence rule never ran on it. A second mutation disabled the header-block close, and all 18 tests passed again. Neither guard had a test that failed without it.
>
> The adversarial review before commit then found three errors on the destructive write path that the real-body tests missed. `~~~` fences were not recognised. A four-backtick fence closed early at an inner fence line. The shared write helper truncated a file before writing, so a mid-write failure left a partial item. No live item contained any of those shapes.
>
> ```
> WRONG — the mutation criterion is attached to a real fixture, assuming which rule excludes it:
> Real fixture: a fenced example after the header block
> Criterion: "disable fence tracking → this test MUST FAIL"
> Actual: an earlier rule (the header-block close) excludes the line first.
>         The test passes with the guard off, and neither guard is tested.
>
> CORRECT — derive one minimal input per guard, where that guard is the ONLY rule that excludes the line:
> Guard A (fence):  status line inside a fence, INSIDE the header block (no --- or ## before it)
> Guard B (close):  status line after a --- close, with no fence and no ## heading
> Mutation check:   A off → only test A fails.  B off → only test B fails.
> ```

Two rules:

- **Run the mutation before the brief asserts its outcome.** Write "each guard has a test that fails when only that guard is disabled", not "test N fails". The first form survives a fixture shadowed by an earlier rule. The second form fails as a criterion, and the reason is not obvious.
- **Treat real-body fixtures and edge-shape fixtures as two different obligations.** Real bytes catch encoding and line-ending hazards that synthetic lines miss. Only synthetic edge shapes exercise grammar the corpus happens not to use yet: tilde fences, longer backtick runs, indented fences, a hit on the last line with no terminator. A destructive pass needs both kinds. [`verification-gate-evidence.md`](verification-gate-evidence.md) §7 (A Fixture Set Must Span Input SHAPES, Not Only Families) holds the shape rule.

**Applies to** any detect-and-strip or reconcile pass with more than one exclusion rule, most of all on a `--write` path. It applies to a task brief that pins a mutation-control criterion to a named test. It applies to a test suite justified as "built from real item bodies" for a parser or scanner.

---

## 16. A Keyed Read Hides a Duplicate: Count Rows Before Keying

> [!constraint] A dict keyed by id is a lossy read. Count rows as you walk, before you key
> Two rows with one id become one entry, and which one survives depends on file order. Treat a repeated key as data to report, not a collision to resolve.
>
> A generator's `--check` reads the on-disk index into `{id: cells}` and compares each entry against what frontmatter would render. An upstream plan had routed a binding contract into the task: on every read, the parsed-row count must equal the table-row count, and every row's cell count must equal the header's. The runner implemented the cell-count half and reported the guard as implemented. The orchestrator recorded that report as a key finding.
>
> A design review planted a duplicated row. An identical copy reported clean, exit 0. A corrupted copy placed first and a clean copy last also reported clean, because the dict write kept the last copy. Only a corrupted copy placed last was detected. A keep-both-sides merge is the ordinary way a duplicate row appears.
>
> ```
> WRONG — key on the way in, and let the last copy win:
> rows_by_id = {}
> for line in table_lines:
>     cells = split_row_cells(line)
>     rows_by_id[cells[COL_ID]] = cells        # second copy overwrites the first
>
> CORRECT — count, detect the repeat, quarantine, report:
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

- **Count rows as you walk, before you key.** Count every table row, track first-seen ids, and quarantine a repeated id from the map entirely. Report it as an anomaly that names the id. Never last-wins, never silently healed.
- **A two-part contract needs both parts probed.** "Row count equals table count, and cell count equals header count" is two checks. The runner's "implemented" claim about the pair was true of one. The acceptance gate names the corruption each half catches and drives it.
- **Test a parity check with the corruption it exists for.** The cell-count check was tested with a dropped cell. The row-count check was never tested with a duplicate, which is the only corruption it can see.

**Applies to** any reader that builds a map from a sequence with a supposedly unique key: index tables, config lists, manifest entries, CSV imports.

---

*Cross-reference: [`measurement-discipline.md`](measurement-discipline.md) §8.7 (the gate's input set — the other half of an unfalsifiable gate, and the dry-run mandate this file gives a recipe for) · [`verification-gate-evidence.md`](verification-gate-evidence.md) §12 (adjudicating a disclosure that a gate shaped its own subject), §3 (the correct-post-state arm of the dry-run) · [`verification-gates.md`](verification-gates.md) §8 (the recorded baseline a diff-scoped gate pins) · [`verification-task-authoring.md`](verification-task-authoring.md) §10.9 (reading a gate command as a program) and §11 (a gate pinned from a run over real content, in [`verification-task-authoring-Part-2-PinnedFromRealContent.md`](verification-task-authoring-Part-2-PinnedFromRealContent.md)) · [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md) (the live-measurement-wins clause a briefing figure travels with)*
