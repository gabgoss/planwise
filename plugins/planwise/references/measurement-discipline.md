---
description: Empirical verification discipline — measure the live, whole-surface truth instead of trusting a secondary, stale, or projected reading; wc-l line-count authority, broad-gate-over-audit-list authority, metric reconciliation, doctrinal-claim sweeps, markdown-field normalization, idempotent-append safety, gate-input-set verification, and behavior-change surface sweeps
paths: {planwise_root}/{plans_dir}/**
---

# Measurement Discipline — Measure It, Don't Infer It

**Purpose:** §8 Empirical Verification Discipline, split out of [verification-gates.md](verification-gates.md) (§1-§7 stay on that anchor). The cross-cutting "measure it, don't infer it" counterpart to that file's cross-process/build/runtime gate discipline — eight cases where an agent or planner trusted a secondary, stale, or projected representation of reality instead of measuring the live, whole-surface truth.

---

## 8. Empirical Verification Discipline

[verification-gates.md](verification-gates.md) §2–§7 each guard a specific "necessary-but-not-sufficient signal treated as the gate" failure. This section generalizes the same discipline to four cross-cutting cases where an agent or planner trusted a **secondary, stale, or projected** representation of reality instead of measuring the live, whole-surface truth. The common cure: **measure it, don't infer it.**

### 8.1 Line-count measurements MUST use `wc -l`, not Read-output line numbers

> [!constraint] Use `wc -l` for any file line-count finding — never the last line number from a Read
> A file's line count for a review finding MUST come from `Bash` running `wc -l <path>` against the actual file. Do NOT treat the last line number observed in a `Read` tool output as the file's length: `Read` may paginate (default cap ~2000 lines), or the reviewer may stop early to manage budget, and a partial read always produces a number structurally smaller than the true count. `wc -l` also counts newline *characters*, so a file with no trailing newline reports one fewer than the visible last line number — a second, independent reason the two measurements can disagree.
>
> WRONG — reviewer Read partway through the file; the last visible line was {N_partial}; reported the file as {N_partial} lines:
> ```
> [WARNING] {reference-file.md} line count overstated
> File: {path}/{reference-file.md}
> Issue: Task declares {N} lines; actual file is {N_partial} (~15% overstatement).
> ```
> (False positive — actual `wc -l` is {N}. The {N_partial} was the last line visible in a paginated read.)
>
> CORRECT — reviewer ran `wc -l` and compared against the plan's declaration:
> ```
> [bash] wc -l {path}/{reference-file.md}
>        {N} {path}/{reference-file.md}
> [reviewer] Plan declares {N} — matches. No finding.
> ```
>
> Four danger signals make this false-positive class easy to fire repeatedly:
> 1. The finding looks plausible — line-count drift is a common, legitimate review signal.
> 2. Reviewer confidence reads MEDIUM–HIGH because it "read the file."
> 3. Accepting it directs fix-work that was never needed (false rework).
> 4. Every file ends in `\n` and partial reads always produce a smaller number than `wc -l`, so the error is systematically biased toward "overstated."
>
> This rule also governs the line-count input to the `task-content-fidelity.md` §9.A.3 per-file-type token rate bands: the `Est. Lines` value fed to a band MUST come from `wc -l`, not from a Read-output last line number. For a whole-file **count**, a Read-output last line number is not authoritative — it reflects how much was read, not how long the file is. This bounds the count only: `Read` remains the correct way to view a file, and its line numbers remain valid for citing a location or setting an `offset`.

#### Reviewer Check 069 — File Line-Count Finding Requires `wc -l`

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Any reviewer finding that claims a file's line count is overstated or understated MUST cite a measured `wc -l` count and name where it came from — ordinarily the review discovery fact sheet, produced once ahead of the reviewer fan-out by a discovery pass that holds `Bash` — NOT the last line number observed in a `Read` tool output. A finding whose count contradicts the review discovery fact sheet MAY re-measure directly, but MUST say so explicitly rather than silently overriding or silently deferring to it. A finding citing a Read-output line number as its evidence, with no `wc -l` source named, is a false-positive candidate — `Read` paginates and partial reads always produce a number smaller than the true count.
- **Detection:**
  1. For each line-count finding in the reviewer's own draft output, verify the evidence method: does it cite a measured `wc -l` count and name its source — the review discovery fact sheet, or an explicit re-measurement note when the finding contradicts the sheet? If the evidence is "Read output showed last line N" or "file appears to be N lines" with no named `wc -l` source → ERROR (promote to FALSE POSITIVE candidate, discard with note).
  2. If the finding's count differs from the review discovery fact sheet's row for that file, confirm the finding states the re-measurement explicitly. A differing count with no such statement → ERROR (silent override, not an explicit re-measurement).
  3. Applies to any plan check that compares a task's `Required Context` `Est. Lines` value against the cited file's actual length.
- **Finding template:**
```
[ERROR] Line-count finding sourced from Read output, not a measured wc -l
File: {reviewed file path} | Location: {task Required Context row / reviewer draft finding}
Issue: Claimed line count {N} derived from last Read-output line, not a wc -l count cited from the review discovery fact sheet (or an explicit re-measurement) — false positive candidate
Fix: Cite the review discovery fact sheet's wc -l count for {file_path}, or re-measure with `wc -l {file_path}` and say so explicitly, before promoting the finding | Confidence: HIGH
```

### 8.2 A broad verification gate is authoritative over an audit's enumerated file list

> [!constraint] Run the full gate; classify every residual match — do NOT trust the audit's file enumeration as the boundary
> When a remediation is scoped by an audit that names specific files, the audit's file list is a starting hypothesis, not the boundary of "clean." Run the full verification gate (grep/lint/diff) and triage every residual match by classification. The gate is the authoritative definition of clean; a broad gate routinely finds sibling instances the audit never named.
>
> WRONG — fix only the audit-named site, then declare done on the audit's word:
> ```
> Audit finding: leak in handlers/plan.md.
> → fix plan.md, mark task complete.   # two sibling leaks in other files survive
> ```
> WRONG — run the gate, see non-empty output, and either fail the task or blindly "fix" every match:
> ```
> grep gate → 50+ matches → treat all as leaks → mangle legitimate naming-convention examples
> ```
> CORRECT — run the full gate, classify every residual match into genuine-citation vs legitimate-illustration, fix the genuine ones, and record the classified residue so a non-empty gate is provably accounted for:
> ```
> grep gate → classify:
>   • a specific project-artifact citation (opaque to any consumer) → genuine leak → SCRUB (3 sites)
>   • an abstract filename pattern under an "Example:" label         → naming illustration → KEEP, document
> → pass criterion = "no genuine citations remain after classification",
>   NOT "grep returns zero lines".
> ```
>
> The distinguishing test: a **citation** references a specific real project artifact (opaque to any downstream consumer) and is a genuine violation; an **illustration** is an abstract filename/identifier pattern under an "Example:" label and is intended documentation. Classify by that test, not by the regex alone. This is the same classification principle [verification-gates.md](verification-gates.md) §2 applies to round-trip runtime evidence — never silently accept a non-empty gate, and never expect literal-empty output when the repo documents the very pattern being scanned.

### 8.3 Sanity-check a projected headline metric against the fixed extraction scope before starting

> [!constraint] An audit-projected metric is an estimate — reconcile it against the fixed scope up front; execute, measure, log the delta; never expand scope to chase the number
> When a plan carries a derived numeric target (post-edit line count, token savings, retention ratio, file-size delta) that originated from an upstream audit or projection, treat it as an estimate subject to measured reconciliation — not a pass/fail gate — especially when the same spec also fixes the scope that determines the number.
>
> WRONG — treat "~460 lines / ~5.6K savings" as a hard gate; on measuring 603, expand the extraction beyond the fixed scope to force the number down:
> ```
> target = 460 lines; measured = 603 → also extract the kept sections, to hit 460   # violates the fixed scope
> ```
> WRONG — round or fudge the reported savings to match the projection.
> CORRECT — execute the fixed scope, `wc -l` the result, report the measured number, and log the projection-vs-reality delta as an Issue with the arithmetic that explains it:
> ```
> fixed scope: keep the first three subsections, extract the rest → wc -l = 603
> report 603 / ~3.8K saved; Issue: projection assumed 460 (280-extract + 460-remainder = 740 ≠ 894 original) — the projection was internally inconsistent, and the section had grown since the audit.
> ```
>
> Before starting, run the up-front sanity check: `original − extracted_block ?= projected_remainder`. If they don't reconcile, surface it before execution, not at verification time. The extraction is correct; only the projection was optimistic. This is the plan-level headline-metric sibling of the "structurally unreachable threshold" concept (Check 058 / `verification-task-authoring.md` §2), which targets grep-count thresholds inside verification tasks — a different surface, no overlap.

#### Reviewer Check 070 — Plan Headline Metric vs Fixed Extraction Scope Reconciliation

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** When a task's Success Criteria carry a derived numeric target (post-edit line count, token savings, retention ratio) AND the same task spec fixes an extraction scope, the two MUST be arithmetically consistent (`original − extracted_block ?= projected_remainder`). A plan that states both a fixed scope and an incompatible headline metric will either produce spec-violating scope creep or a misleading savings report.
- **Detection:**
  1. For each task with Success Criteria containing `~{N} lines` or `~{N}K tokens` AND an extraction scope that names specific sections (keep §X, extract §Y, leave §Z): compute `original_lines − extracted_section_lines` and compare against the stated remainder target.
  2. If the implied remainder differs from the target by >10% → WARNING.
  3. If the task spec also includes language like "if actual differs significantly from target, use the actual" — downgrade to INFO (task already acknowledges the gap).
- **Finding template:**
```
[WARNING] Plan headline metric incompatible with fixed extraction scope
File: {task file path} | Location: Success Criteria + extraction scope
Issue: Fixed scope implies ~{computed} lines remainder; plan targets ~{declared} — {pct}% gap
Fix: Sanity-check up front per references/measurement-discipline.md §8.3; execute fixed scope, measure wc -l, report actual delta as Issue | Confidence: MEDIUM
```

### 8.4 Grep the entire artifact surface for every phrasing of a doctrinal claim before declaring it fixed

> [!constraint] Doctrinal errors propagate across files — sweep the whole surface; surface out-of-scope instances; re-run at end
> A doctrinal error (a rule, a parameter, a threshold, a factual claim stated in a source file and cited by consumers) rarely lives in one place. Before declaring it fixed, grep the entire artifact surface for every phrasing of the claim.
>
> WRONG — edit the file named in scope, confirm that file reads correctly, ship:
> ```
> scope names templates/orchestration.md → fix it, confirm, ship.
> (The same false claim also lived in the section the template CITES — 4 spots —
>  and in handlers/plan.md — 4 more spots. The template now cites a self-contradicting section.)
> ```
> CORRECT — grep the whole surface for every phrasing of the claim (e.g. `parent.{0,2}tier`, `inherit the parent`, the specific false-assertion text); fix all instances — or, where instances fall outside the literal scope, surface them as a structural finding / scope-expansion gate and let the user decide. Re-run the sweep at the end and confirm only correct/negated phrasings remain.
>
> A citation chain is coherent only when the cited source and every consumer agree. When instances fall outside literal task scope, surface them per §1.2 of `read-confirm-act-protocol.md` (structural findings beyond literal scope — surface, don't silently fix or silently ignore), not silently.

### 8.5 Normalize an authored-markdown field on BOTH read and write — and test it with annotated, not clean, fixtures

> [!constraint] When an authored-markdown field feeds a normalized/canonical slot, apply the SAME normalization on comparison AND on write — and regression-test it with realistically messy fixtures, never clean ones
> A value read from a human-authored markdown field (a `**Status:**` line, a table cell a person edits by hand) routinely carries decoration that the canonical slot it feeds must not: wrapping `**bold**` / `_emphasis_`, em-dashes, trailing `(date)` or `— note` annotations, `<!-- comments -->`, `§`, backticks. When that field is compared against a canonical value — OR copied into a normalized (enum / single-token) cell — the normalization must apply consistently on every side, or detection and the write disagree and the slot is silently corrupted. This is a **data-corruption path** whenever the write is destructive, and the class recurs on any tool that copies an authored markdown field into a normalized index/cache cell.
>
> **1. Normalize on both sides, or not at all.** When a field read from authored markdown is compared against a canonical value, apply the normalization to BOTH operands. When such a field is *written* into a normalized (enum / canonical) cell, write the **normalized** value — never the raw authored string.
> WRONG — the comparison normalizes but the write stores the raw source line, so the one-token cell ends up holding a whole annotated sentence, and downstream exact-token filters silently break:
> ```python
> if base_token(row.Status) != base_token(mp_status):   # compare: normalized
>     row.Status = mp_status                             # write: RAW → "**COMPLETE** (2026-05-26) — shipped v1.2.0"
> ```
> CORRECT — the write stores the same normalization detection uses, so detection, the report banner, and the persisted cell all agree on one token:
> ```python
> if base_token(row.Status) != base_token(mp_status):
>     row.Status = base_token(mp_status)                 # write: normalized → "COMPLETE"
> ```
>
> **2. Strip inline formatting when normalizing an authored field.** A whitespace/case-only normalizer is not enough — the field's own value may carry markdown emphasis, so an already-reconciled row reads as false drift.
> WRONG — first-word-uppercase leaves the emphasis attached, so a bolded token never equals its plain canonical form:
> ```python
> def base_token(s): return s.split()[0].upper()          # "**COMPLETE**" → "**COMPLETE**" ≠ "COMPLETE"  (false drift)
> ```
> CORRECT — strip wrapping emphasis (`*` / `_`) after uppercasing:
> ```python
> def base_token(s): return s.split()[0].upper().strip("*_")   # "**COMPLETE**" → "COMPLETE"
> ```
>
> **3. Test with annotated, not clean, fixtures.** A fixture built on a clean canonical value (`"COMPLETE"`) stays green while masking BOTH bugs above — the raw-write corruption and the emphasis false-drift. A regression test MUST feed a realistically messy source and assert the destination receives ONLY the bare token, covering both directions:
> ```python
> # WRONG — clean fixture: green, but exercises none of the decoration the bug actually needs
> write_master_plan(status="COMPLETE")
> # CORRECT — annotated fixtures that an asymmetric or emphasis-blind normalizer would fail
> write_master_plan(status="**COMPLETE** (2026-05-26) — shipped v1.2.0")   # write side: assert the written cell == "COMPLETE"
> #   read side: index cell already "COMPLETE" vs Master Plan "**COMPLETE**" → assert NO drift (no false positive)
> ```
>
> This is the same "a necessary signal is not sufficient" trap §8 opens with, aimed squarely at the test fixture: a green suite built on clean inputs says nothing about the messy authored strings the code will actually meet. It is a direct instance of the pre-commit adversarial-review discipline in `destructive-change-requirements.md` §10.4 ("A green suite is not a review: pre-commit adversarial review for destructive diffs") — the write-side corruption in this class survived a fully green unit suite and fell only to the adversarial review of the destructive write path.

### 8.6 Measure live state before an idempotency-unsafe append/author

§8.1–§8.5 each measure a live surface instead of trusting a secondary reading. This section applies the same discipline to a plan's own task steps: a plan's stated anchors, counts, and "append/author N" instructions are **predictions written when the plan was authored — not facts about the live target now.**

> [!constraint] Re-derive live state before any idempotency-unsafe append/author — never blind-append or blind-author
> Treat a plan's stated anchors, row counts, and "append N rows" / "insert at max+1" / "add the next check number" steps as predictions, not facts. Before executing one, re-derive the live state: grep the shipped artifact and count the rows/sections that already exist. If the deliverable already exists, **verify-in-place** — never blind-append or blind-author on the plan's word.
>
> This matters most when the same deliverable can be shipped through more than one route — a plan session AND a backlog-triage route (direct fix, an in-session task list, a direct commit). A plan's status fields are written only by its own session closeout; a plan whose deliverables were satisfied through a different route is left live and independently runnable, its stale "append N" steps now aimed at already-satisfied state.
>
> WRONG — close the backlog item, leave the twin plan alone → `/planwise run` starts it → a task step "append 10 rows" runs against 10 rows that already exist → 10 duplicate rows, or a duplicate `## 9` section colliding with the shipped `## 8`:
> ```text
> plan step T04: "append 10 Rule-Promotion-Log rows"   # authored when 0 existed
> live index already holds those 10 rows                # shipped via the backlog route
> → blind append → 10 duplicate rows
> ```
> CORRECT — measure the live target first, and reconcile the twin at closeout:
> ```text
> before T04: grep the promotion log → the 10 rows already exist → verify-in-place, do NOT append
> at the shipping route's closeout: retire/link the twin plan so it is never independently run
> ```
> Detection tripwire: at a delegated session's first dispatch layer, grep each deliverable against the live target before authoring. A plan that is **entirely** already-satisfied at that boundary is the signal that a twin was shipped elsewhere and never retired.

### 8.7 Verify the gate's input set before trusting its predicate

An empty result from a verification command is **ambiguous**. It means either "I checked and found nothing" or "I checked nothing." Those are opposite facts and the gate renders them identically. Every downstream reader — the verification report, the sprint signoff, the release battery — consumes the empty result as evidence of cleanliness.

This is worse than a missing gate. A missing gate is visible in review; a gate that *cannot fail* is documented as coverage and actively suppresses the search for one. §8.1–§8.6 each measure a live surface rather than trusting a secondary reading. This section turns the same discipline on the gate itself: **verify the gate's input set, then its predicate.** The two sub-rules below are the two ways a gate ends up unable to fail — one where the input never arrived, one where the objective is satisfied by destroying the thing being checked.

> [!constraint] A — A change-set-derived gate silently excludes whatever the change set omits
> WRONG — the canonical shape. It reports the same empty result whether it inspected everything or nothing:
> ```bash
> git diff $BASE -- <paths> | grep -E '^\+' | grep -E '<forbidden-pattern>'   # expect empty
> ```
> Three independent blind spots, each sufficient on its own to make the gate unfalsifiable:
> 1. **Untracked files never appear in `git diff` at all.** A task that CREATES files gets an empty result from a pipeline those files' content never entered.
> 2. **`^\+` filtering hides everything predating the base.** A defect older than `$BASE` is a context line, not an added line, so it is invisible by construction — and stays invisible across every later session reusing the shape.
> 3. **A pattern narrower than the forms it must catch misses them even unfiltered.** A pattern written as `{PREFIX}-[0-9]` matches only the citation spelling; the same identifier glued into a file name (`…-{PREFIX}SomeTopicName.md` — no hyphen, no digit) slips straight through, so widening the scope without widening the pattern still returns empty on a visibly leaking file.
>
> CORRECT — four remedies, all of them cheap:
>
> **1. Register new files before diffing.** Intent-to-add puts the path in the index without staging content or creating a commit:
> ```bash
> git add -N <each new file>       # then run the gate
> ```
>
> **2. Assert the gate's input was non-empty.** A gate over a diff must prove the diff covered the intended file set — never trust the pattern result alone:
> ```bash
> git status --porcelain <scope> | grep -c '^??'    # must be 0, else some file was never registered
> git diff --name-only $BASE -- <scope> | wc -l     # must equal the expected file count
> ```
>
> **3. Add one unfiltered sweep for pre-existing content.** `^\+`-filtered gates correctly answer "did this change introduce X"; they cannot answer "does X exist". A whole-tree audit or release battery needs a sweep over files **on disk**, not over a diff — and it must **classify** hits rather than blanket-fail, since legitimate template placeholders and rule text that enumerates the forbidden forms will match. Widening a pattern without widening the classification step converts a silent miss into a noisy blanket-fail, which gets ignored just as fast.
>
> **4. Dry-run every gate against known-bad input before trusting it.** Run it once against a file that genuinely carries the pattern and once against a clean file; the two runs MUST produce different results. Each of the three defects above would have surfaced in one such run. A gate that has only ever been run against clean input has never been shown to discriminate.
>
> **Generalisation:** the class is broader than git. Any check deriving its input from a *change set* — a diff, a changelog, a CI touched-files list, a migration delta — silently excludes whatever the change set omits, and inherits this whole failure mode.

> [!constraint] B — A size objective is satisfied by destroying the content the gate was meant to protect
> A pointer's value is not its description — it is the **location**: file + section number + exact heading name. A summary that keeps a rule's topic but drops its section number converts a jump into a search through a long target; one that renames the heading breaks even the search. The pointer no longer points.
>
> WRONG — a consolidation task whose gates are all size- or absence-shaped: a `wc -l` band, a `grep -c` proving the old headings are gone, plus the usual self-containment greps. A runner collapses six pointer sections into one table, flattens nine sub-section numbers into running prose, and rewrites two heading names into shorter paraphrases. **Every gate passes.** The file got smaller, which is what the task asked for — it got smaller *by* discarding the payload. Grepping the target for the table's own wording now returns zero hits.
>
> The failure mode is structurally adversarial: the metric the task optimises improves monotonically with the amount of content destroyed. There is no size at which the gate objects.
>
> CORRECT — four remedies:
>
> **1. Pair every size gate with a content-conservation gate.** Before the task runs, enumerate the specific payload terms that must survive, and check them by exact string:
> ```bash
> for s in '<coordinate-1>' '<coordinate-2>' '<exact heading name>'; do
>   printf '%-40s %s\n' "$s" "$(grep -cF "$s" $FILE)"
> done      # every line must be >= 1
> ```
> Derive the term list from the **pre-edit** file, never from the post-edit result — a list written afterwards inherits whatever was already lost.
>
> **2. Use `grep -F` and mind case.** Proper-noun rule names are part of the payload; lower-casing them breaks findability against the target's actual heading. Run the gate case-sensitively, then re-run case-insensitively to distinguish a genuine loss from a casing slip — they need different fixes.
>
> **3. Never let the output shape truncate the content.** If a three-column table cannot hold the payload readably, widen the cell (`<br>`-separated bullets) or add a sub-list — do not trim the payload to fit the shape. Readability of the container never outranks conservation of what it contains.
>
> **4. Require the gate output in the completion report, and re-run it independently.** In the originating incident the runner did not paste its gate output and reported COMPLETE in good faith; the loss was found only when the orchestrator ran the gate itself. **A conservation claim verified by the same agent that made the cut is not verification.**
>
> **Generalisation:** applies to any consolidation carrying a size objective — merging docs, deduping rules, collapsing config, summarising logs, compressing prompts. Ask what the artifact's *payload* is as distinct from its *prose*, and gate on the payload.

#### Reviewer Check 074 — Diff-Derived Gate Without Input-Set Assertion

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** A task verification gate whose input comes from a change set — `git diff`, a changelog, a CI touched-files list, a migration delta — MUST carry BOTH an untracked-file registration step (`git add -N`) and an input-set assertion proving the diff actually covered the intended files. Without them the gate returns the same empty result whether it inspected everything or nothing, and every downstream reader consumes that empty result as evidence of cleanliness. The defect is worst on tasks that CREATE files: `git diff` does not report untracked paths at all, so a gate over a newly-authored file inspects zero bytes and reports PASS.
- **Detection:**
  1. Identify every Success Criterion / verification step whose command pipes a change set into a matcher (`git diff … | grep`, `git diff --name-only`, a touched-files list).
  2. For each, check whether the task's Execution Steps also register untracked files (`git add -N`) before the gate runs. Absent, on a task whose deliverables include NEW files → ERROR.
  3. Check for an input-set assertion (`git status --porcelain <scope> | grep -c '^??'` expecting 0, and/or `git diff --name-only $BASE -- <scope> | wc -l` compared against an expected file count). Absent → ERROR.
  4. If the task is a whole-tree audit or release battery, also require one unfiltered on-disk sweep — a `^\+`-filtered gate cannot answer "does X exist", only "did this change introduce X". Absent on an audit-scoped task → ERROR.
  5. Inspect the matcher pattern against the forms it must catch. A pattern matching only the hyphen-digit citation spelling of an identifier while the leak also appears glued into file names → ERROR (too narrow to discriminate).
- **Finding template:**
```
[ERROR] Diff-derived gate without input-set assertion
File: {task file path} | Location: Success Criteria / verification step {n}
Issue: Gate derives input from {git diff | change set} with no {git add -N registration | input-set assertion | unfiltered sweep}; task authors {N} new file(s) whose content never enters the pipeline — empty result is unfalsifiable
Fix: Add `git add -N` for each new file, assert `git status --porcelain <scope> | grep -c '^??'` == 0 and `git diff --name-only $BASE -- <scope> | wc -l` == expected count, and dry-run the gate against known-bad input per references/measurement-discipline.md §8.7 | Confidence: HIGH
```

#### Reviewer Check 075 — Size Gate Without Content-Conservation Gate

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** When a task's objective is compaction, consolidation, collapsing, deduplication, or summarisation, its gates MUST include a content-conservation check derived from the **pre-edit** file — not only size gates (`wc -l` bands) and absence gates (`grep -c` for removed headings). Size and absence gates are both satisfied by destroying the payload: the metric improves monotonically with the amount of content lost, and there is no size at which the gate objects. The payload at risk is usually a pointer's coordinates — target section numbers and exact heading names — which a paraphrase drops while keeping the prose intact.
- **Detection:**
  1. Identify tasks whose Objective contains a compaction verb (collapse, consolidate, merge, dedupe, compress, summarise, trim, "reduce to N lines").
  2. Inspect their Success Criteria. If every gate is size-shaped (`wc -l`, line band, token count) or absence-shaped (`grep -c` of what was removed) → WARNING.
  3. Require an explicit conservation term list — section numbers, exact heading names, coordinates — checked by exact string (`grep -cF`), with the list stated as derived from the pre-edit file. A list derived after the edit inherits whatever was lost; flag that phrasing specifically.
  4. Check that the task requires the conservation gate's OUTPUT in the completion report, and that a party other than the editing runner re-runs it. Self-certified conservation → WARNING.
- **Finding template:**
```
[WARNING] Compaction task gated on size only — no content-conservation check
File: {task file path} | Location: Objective / Success Criteria
Issue: Objective is {collapse|consolidate|dedupe} but all gates are size/absence-shaped; payload ({section numbers | exact heading names | coordinates}) can be discarded with every gate green
Fix: Add a pre-edit-derived conservation gate (`for s in '<coordinate>' '<exact heading>'; do grep -cF "$s" $FILE; done`, every count >= 1), run it case-sensitively then case-insensitively, and require its output in the completion report re-run by a second party per references/measurement-discipline.md §8.7 | Confidence: MEDIUM
```

### 8.8 After a behavior change, sweep the surfaces that describe and call it

A behavior change lands on surfaces beyond the code that implements it. **The tests cover the code. Nothing covers the metadata that *describes* the code, or the document that *invokes* it.** Both can therefore be left asserting the old behavior with the suite fully green — and both are read as authoritative: the metadata by tooling and by the next author, the document by the user following it.

§8.7 asks whether a gate can fail. This section asks a prior question: whether the change was even applied everywhere it is stated. The three sub-rules below are one sweep, in causal order — C only ever arises as a consequence of acting on B, so they are not separable.

> [!constraint] A — Update the field, not just the prose beside it
> WRONG — the fix updates the human-readable half and leaves the machine-readable half asserting the old behavior. The row now asserts two contradictory things about the same key, and the authoritative half is the false one:
> ```yaml
>   - id: <some_key>
>     <field>: <old_value>        # ← still says the old behavior
>     notes: >
>       … the commit point now rewrites this key in the SAME write …   # ← says the opposite
> ```
>
> CORRECT — the field moves too, a truthful value is **added** when none exists, and the siblings are swept:
> ```yaml
> # (enum gains a definition comment in the file's own style)
> #   <new_value>: <definition of what this actually means>
>
> <enum_key>: [<existing values>, <new_value>]
>
>   - id: <some_key>
>     <field>: <new_value>
>   - id: <paired_key>
>     <field>: <new_value>   # ← sibling audit: was false before this fix, too
> ```
>
> Three ordered steps:
>
> **(a) Find the field, not just the prose.** Grep the manifests, schemas and frontmatter for the artifact you changed, and read the **structured** values. Free-text `notes:` / `description:` are the easy half — they read as commentary and an author updates them by reflex. The enum, boolean or path-glob two lines above is the half that reads as authoritative to tooling and to the next author, and it is the half that gets left behind.
>
> **(b) If no legal value is true, add one — do not round to the nearest.** Check what consumes the field first: a value that is inert to code but wrong to a reader is a documentation defect; one that drives a loop is a runtime defect. Then add the value to the declared enum **and** write its definition comment in the file's established style. Picking the least-wrong existing value is not a smaller fix than adding one — it encodes a second, subtler lie in a field that now looks deliberately chosen.
>
> **(c) Audit every sibling row carrying the value you just abandoned.** The reason your row was wrong usually applies to its neighbours. **This is the step that pays.** A sibling written by the same mechanism can have been false since before your change existed — no current task owns it, no test covers it, and nothing but this sweep will surface it. Your fix did not cause it; your fix created the occasion to notice it.
>
> When nothing in code validates the field, verify it by hand:
> ```bash
> python -c "
> import yaml; d=yaml.safe_load(open('<manifest>',encoding='utf-8'))
> enum=set(d['<enum_key>'])
> print('off-enum:', [a['id'] for a in d['artifacts'] if a.get('<field>') not in enum] or 'NONE')
> print('grouped:', {v: [a['id'] for a in d['artifacts'] if a.get('<field>')==v] for v in enum})
> "
> ```
> The **grouped** half matters as much as the off-enum half. Off-enum catches a value that is illegal; grouped catches a value that is legal and false — it puts an inherited wrong value directly beside its correct peers, which is the only cheap way to see it.

> [!constraint] B — A detection plus a repair is not a remediation until something routes between them
> Whenever a change adds "X detects a bad state" and "Y can fix it", the deliverable is **not done** until the path from X's recommendation to Y's execution has been traced end to end and shown to be walkable. State the trace explicitly. Do not infer it from the fact that both halves exist and both are tested — that is exactly the evidence that is available when the loop is still open.
>
> **Where the caller is a document** — a handler, a runbook, a README command sequence — the document is part of the change surface, and its gate conditions are as load-bearing as an `if`. A prose gate that exits on the very condition the new repair path exists to serve is a dead end that no test can fail: the user is told they are already fine and left broken, twice.
>
> WRONG — the gate exits on the condition the repair serves, and a nearby note merely *describes* the capability:
> ```
> > If `pinned == shipped` → report "already up to date" and exit.
> …
> > [!practice] A stale root is upgrade-indicating
> > …re-running the script resolves the mismatch…      ← nothing routes here
> ```
>
> CORRECT — the gate itself carries the routing, and names what is skipped and why:
> ```
> > If `pinned == shipped` **and** the stored value matches the live one → report and exit.
> > If `pinned == shipped` **but** the stored value differs → do NOT exit; skip the
> >   comparison stages (nothing changed to compare) and run the writer invocation,
> >   which repairs the value on its own. Report it as a repair, not a version change.
> ```

> [!constraint] C — A previously-unreachable branch is unproven code, regardless of its age or test count
> Fixing a gate per sub-rule B makes a dormant branch live. That is a **behavioral change to everything the branch touches** — the branch's age and the suite's green status say nothing about it, because until now it never ran.
>
> Before declaring it done, walk the branch line by line against every input the newly-routed caller can supply — flags, options, environment — and ask what the branch does with each. **Anything set up after the point where that branch returns is, by construction, not applied there.**
> ```python
>     if pinned_version == target_version:
>         # This branch is now reachable. Everything below the gate — the opt-in
>         # flag application, the backfills — never runs here. Anything a caller
>         # can pass must be honored on THIS path or explicitly declared a no-op.
>         toggled = bool(cfg.opt_in_flag) and _apply_opt_in(config_path)
> ```
>
> The mechanical check is a set difference — enumerate what the caller can request, enumerate what the branch performs before it returns, and subtract:
> ```bash
> # 1. what the caller can ask for: every flag/option the entry point accepts
> grep -nE 'add_argument|opt_in|--[a-z-]+' <entry_point> | sed 's/.*--//' | sort -u
> # 2. what the newly-live branch actually does before returning
> sed -n '<branch_start>,<return_line>p' <module> | grep -nE '_apply_|_backfill_|write|=' 
> ```
> A non-empty difference is either a bug or a decision that needs stating — never a silent no-op.

**Applies-to surface.** Any change to behavior that a manifest, schema, frontmatter field or capability table also describes — **including when the field is documentation-only and no test can fail.** Any change pairing a new diagnostic with a new remediation. Any change relaxing a gate, guard or early return so a previously-dead branch begins executing. And any codebase where prose — a handler, a runbook, a documented command sequence — is the caller of record for a script: there the document's conditions must be edited in the same change as the code's, or the code's new capability is unreachable in practice.

#### Reviewer Check 076 — Detection + Repair With No Routing Deliverable

- **Severity / Role / Type:** WARNING | Plan Reviewer | NEW
- **What:** When a plan's deliverables include BOTH a new diagnostic (a check, warning, doctor stage, lint, drift detector) AND a new repair path (a fixer, migration, self-heal, reconcile-on-consent branch), it MUST also carry a deliverable that edits the **caller** which routes from the diagnostic's recommendation to the repair's execution. Without it, both halves ship, both are tested, the suite is green — and the loop is still open: the diagnostic's advice is a dead end. **The caller is frequently a document**, not code. Where a handler, runbook or documented command sequence is the caller of record, its gate conditions are as load-bearing as an `if`, and a prose gate that exits on the very condition the repair path serves cannot be caught by any test. A secondary signal: a plan that makes a previously-unreachable branch live without a deliverable auditing that branch against every input the newly-routed caller can supply — the branch's age and test count are not evidence, since until now it never ran.
- **Detection:**
  1. Classify each deliverable as diagnostic (detects/reports a bad state), repair (corrects it), or routing (connects a recommendation to an invocation).
  2. If the plan has ≥1 diagnostic and ≥1 repair but zero routing deliverables → WARNING.
  3. Where a routing deliverable exists, check it names the caller **and** its gate condition. A deliverable that only adds a note *describing* the repair capability alongside an unchanged gate does not route — flag it.
  4. Check the handler / runbook / command-sequence docs among the plan's touched files. If the documented flow exits early on the state the repair addresses and no deliverable edits that gate → WARNING.
  5. If any deliverable relaxes a gate, guard or early return so a dormant branch begins executing, require a deliverable that walks that branch against the caller-suppliable inputs (flags, options, environment). Anything set up after the branch's return point is not applied there. Absent → WARNING.
- **Finding template:**
```
[WARNING] Detection and repair ship with nothing routing between them
File: {plan or sprint file path} | Location: Deliverables / Sprint scope
Issue: Plan adds {diagnostic} and {repair} but no deliverable edits the caller ({handler|runbook|entry point}) that routes between them; documented flow exits on {condition} — the repair path is unreachable and the diagnostic's recommendation is a dead end
Fix: Add a deliverable editing the caller's gate to route the detected state to the repair (naming what is skipped and why), and audit the newly-reachable branch against every caller-suppliable input per references/measurement-discipline.md §8.8 | Confidence: MEDIUM
```

---

*Cross-references: [verification-gates.md](verification-gates.md) (§1-§7 — cross-process/build/runtime gate discipline this section generalizes from; split anchor, keeps the original filename).*
