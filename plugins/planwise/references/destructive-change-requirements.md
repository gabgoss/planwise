---
description: Destructive-path and config-gated change requirements — interaction-matrix spec, independent test authorship, gated-branch pin discipline, pre-commit adversarial review, a lexical scorer's absent verdict is not evidence of absence (adjudicate before the writer runs), a similarity heuristic may only escalate in refuse-by-default tooling, and review convergence gated on consequence classes rather than severity labels, what the adversarial review must be told (seven case classes, the fix-diff review and the stopping rule), and an exemption modelled on a reference check copies the whole refusal condition
---

# Destructive-Path and Config-Gated Change Requirements

**Purpose:** Requirements for any task that adds or extends a branch that can DELETE, OVERWRITE, MIGRATE, PRUNE, or SWEEP user data or user customizations.
**Extends session-plan-requirements.md §8; extracted to keep both comfortably within a single Read call.**

---

## 10. Destructive-Path & Config-Gated Change Requirements

*Applies to any task that adds or extends a branch which can DELETE, OVERWRITE, MIGRATE, PRUNE, or SWEEP user data or user customizations. For such code the ordinary per-task gates — lint clean, unit suite green, smoke passing, self-containment greps empty — certify nothing about the inputs and adjacent states nobody named. These requirements are a chain, not duplicates: §10.1 makes the spec cover the whole interaction matrix; §10.2 has an independent test task re-derive the contract; §10.3 pins the gated branch without disturbing default-path evidence; §10.4 backstops all three with an adversarial review before the commit. §10.5 to §10.7 cover a destructive path that a similarity score or a severity label steers: §10.5 says a lexical scorer's "absent" verdict is not evidence of absence, so a semantic adjudicator runs before the writer; §10.6 says a similarity heuristic may only escalate toward refusal; §10.7 gates a review loop's convergence on consequence classes, not on severity labels. §10.8 and §10.9 cover what a review and a guard author each miss when the author of the feature also wrote its fixtures: §10.8 names the case classes the review brief must carry, requires a review of a fix diff, and sets the stopping rule. §10.9 says an exemption modelled on a reference check copies that check's whole refusal condition.*

### 10.1 Enumerate the config-interaction matrix in the spec

> [!constraint] For any change that can DELETE user data, the spec enumerates the interaction matrix and assigns every cell an outcome — it does not transcribe the directive
>
> WRONG — the spec treats the failure modes the directive happened to name as the whole safety surface:
> "the user listed transfer-failure and backup-failure, so those are the safety cases."
>
> CORRECT — the spec decides every combination the target code region can produce:
> "the user listed two cases; the code region has four gates; the spec decides all combinations and says which the user's ruling covers."
>
> Four-step method:
> 1. **Enumerate at spec time.** Grep the target region for every config gate, opt-out, and degraded/fallback state that already influences the sibling branches (e.g. `get_upgrade_config()` keys, `not_analyzed`-style verdict stand-ins, absent-key fallbacks). Each one × the new behavior = a cell the spec must decide: proceed, preserve, or report.
> 2. **Precedence rule of thumb.** An existing protective opt-out must bind the NEW destructive branch at least as strongly as it binds existing branches — a more-customized file must never get weaker protection than a less-customized one. Any cell where the new branch is more aggressive than a sibling is a spec bug until explicitly ruled otherwise.
> 3. **Tests mirror the matrix, not the directive.** The regression class should have one case per cell, including the adjacent-gate cells — not just the failure modes the directive happened to name.
> 4. **Guard the mid-session path.** A spec authored from a chat directive under time pressure is exactly where adjacent-gate enumeration gets skipped. Make the grep-for-gates step mandatory before the spec is dispatched.

#### Reviewer Check 072 — Destructive-Path Spec Missing Interaction Matrix

- **Severity / Role / Type:** ERROR | Plan/Task Reviewer | NEW
- **What:** A task that adds or extends a branch which can DELETE, OVERWRITE, or MIGRATE user data MUST have a spec section enumerating the config-gate / opt-out / degraded-state interaction matrix, with a decided outcome per cell (proceed / preserve / report). A spec that names ONLY the failure modes the directive happened to mention, when the target code region has additional gates the sibling branches honor, is an ERROR — an adjacent opt-out the new destructive branch fails to consult is the likeliest silent-loss vector (a more-customized file getting weaker protection than a less-customized one).
- **Detection:**
  1. Identify tasks whose Objective / Execution Steps add or widen a delete/overwrite/migrate/prune/sweep branch.
  2. For each, check the task spec (or its Execution Input section) for an enumeration of the target region's config gates / opt-outs / degraded states with a per-cell outcome. Absence, or coverage of only the directive-named failure modes → ERROR.
  3. Apply the precedence rule: any cell where the new destructive branch is more aggressive than a sibling preserve/skip branch, without an explicit ruling, is a spec bug.
- **Finding template:**
```
[ERROR] Destructive-path spec missing config-interaction matrix
File: {task file path} | Location: spec / Execution Steps
Issue: Spec covers only directive-named failure modes; target region has additional gates ({list}) with no decided outcome — adjacent-opt-out silent-loss risk
Fix: Enumerate every config gate/opt-out/degraded state × the new behavior, decide each cell (proceed/preserve/report), and mirror the matrix in tests per references/destructive-change-requirements.md §10.1 | Confidence: HIGH
```

### 10.2 Schedule tests as an independent same-sprint task with a surface-don't-patch brief

> [!constraint] For a new primitive/module with a written contract, schedule its test suite as its own same-sprint task (fresh runner context, spec-first), before any consumer sprint wires it in
>
> Two disciplines make a spec-vs-implementation divergence productive instead of destabilizing:
> 1. **Independent test authorship in the same sprint.** A separate task (fresh context, spec-first reading) writing tests against the shipped artifact is a cheap adversarial re-derivation of the contract. Same-author self-verification tends to inherit the implementation's reading of the spec, so it misses the alternate readings the spec actually permits.
> 2. **"Surface, don't silently patch" in the test task's brief.** The test task is forbidden from editing the artifact under test (unless the fix is trivially correct and noted). A spec-vs-impl discrepancy therefore becomes a Recovery Issue + Cross-Task Coordination Flag routed to the consumer sprint, instead of the test author quietly changing the primitive or the assertion to force green — which would destroy the signal.
>
> **Route by failure direction, and classify before deferring:** a conservative divergence (the implementation over-preserves relative to the spec) → coordination flag to the consumer sprint, safe to defer; a divergence in the deleting direction (the implementation removes what the spec would keep) → blocker in-sprint.

### 10.3 Non-default-gated changes add gated-branch pins; keep absent-key pins as default-path evidence

> [!constraint] When new behavior is gated on a non-default config value and the default/absent-key path is deliberately unchanged, budget a NEW pinned test class — never a rewrite of the absent-key pins
>
> - Existing absent-key pins keep passing **by construction** — do not budget task scope to rewrite them. Budget a new pinned test class that sets the gating value explicitly and covers the gated branch plus its failure paths.
> - **Invert the signal.** If an existing absent-key pin DOES break during such a change, that is not "expected pin churn" — it means the default path changed, a spec violation to investigate, not an assertion to update.
> - At plan/spec time, phrase the requirement as "verify existing pins still pass unchanged (default path untouched) + add gated-branch pins," never "update the pinning tests" — the latter invites a runner to modify load-bearing default-path evidence.
>
> For review synthesis: a diff that rewrites absent-key pin assertions during a non-default-gated change is a red flag, not diligence.

#### Reviewer Check 073 — Absent-Key Pin Rewrite During Non-Default-Gated Change

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** When a task's spec gates new behavior on a NON-default config value AND deliberately keeps the default/absent-key path unchanged, the test plan MUST add a new gated-branch pin class — NOT rewrite existing absent-key pin assertions. A task plan that budgets "update the pinning tests" (rather than "verify existing pins still pass unchanged + add gated-branch pins") is a red flag: absent-key pins are load-bearing evidence of default-path stability, and rewriting them during a change that keeps the default path fixed hides a possible default-path regression.
- **Detection:**
  1. Identify tasks whose spec gates new behavior on a non-default config value while stating the default/absent-key path is unchanged.
  2. Inspect the task's test plan / Success Criteria. If it directs rewriting existing absent-key pin assertions rather than adding a new pinned class that sets the gating value → WARNING.
  3. Invert the signal: if the plan expects existing absent-key pins to break, flag it — a broken absent-key pin means the default path changed (a spec violation to investigate), not routine pin churn.
- **Finding template:**
```
[WARNING] Absent-key pins rewritten during non-default-gated change
File: {task file path} | Location: test plan / Success Criteria
Issue: Spec keeps default path fixed but plan rewrites absent-key pin assertions instead of adding a gated-branch pin class — default-path evidence disturbed
Fix: Phrase as "verify existing pins still pass unchanged (default path untouched) + add gated-branch pins"; investigate any absent-key pin that breaks as a default-path regression | Confidence: MEDIUM
```

### 10.4 A green suite is not a review: pre-commit adversarial review for destructive diffs

> [!constraint] For any diff that adds or widens a destructive disposition (delete / overwrite / migrate), run an adversarial multi-agent review BEFORE the commit, then fix-and-regression-test in the same session
>
> WRONG — treat per-task verification (lint + suite green + smoke) as sufficient to commit a new destructive path.
>
> CORRECT — run the adversarial review pre-commit; a fresh feature's tests are written by the same mind that wrote its bugs, so a green suite says nothing about the inputs nobody imagined (BOMs, block-style YAML, non-dict JSON cache entries, retry-after-crash staleness, filename collisions).
>
> "Run script verification" and "run code review" are DIFFERENT gates; the second is mandatory when the diff touches destructive dispositions, even when the first is fully green.

### 10.5 A lexical scorer's absent verdict is not evidence of absence: adjudicate before the writer runs

> [!constraint] A containment score measures shared strings. Let a writer act only on adjudicated absence, never on a low score
> A cell written from a body section rarely shares strings with it when the body spreads the same facts across a lead-in plus a table, a fenced block, a numbered outline or a hard-wrapped paragraph. On such a corpus the scorer's high class is trustworthy in one direction only: a single body line at 0.75 or more is present. A low score says nothing. Treating "no string overlap" as "absent" and letting the writer act on it is the failure. The gate that follows cannot catch it, because a duplicate passes every size check.
>
> One session moved the prose in 193 index cells (640 sentence units, 151,189 characters) into the item files those cells describe, without duplicating what the files already said. The plan built a character-shingle containment scorer and classified every unit ALREADY-PRESENT, MISSING or AMBIGUOUS. It appended the MISSING set verbatim, sent only the AMBIGUOUS band to a semantic reviewer, and gated on byte arithmetic plus a duplication re-score. Three findings changed the run:
> - A hand-check of the three lowest-scoring units found one (score 0.15) whose content was present across a lead-in sentence and a table.
> - A probe scored every unit against 2-line windows. 46 of 121 scorer-MISSING units rose into the AMBIGUOUS band.
> - After the scorer was patched with that window, the reviewer screened the residual 77 MISSING units together with the 331 AMBIGUOUS ones. **70 of the 77 were present in substance.** The final append set was 3 units plus 8 split halves, 749 characters in 11 files. The plan as written would have appended 43,033 characters across about 57 files, and the byte gate would have passed.
>
> WRONG — the writer trusts the low tail:
> ```
> score ≤ low           →  MISSING    →  append verbatim        # 70 of 77 were present; byte gate PASSES
> score in (low, high)  →  AMBIGUOUS  →  semantic reviewer
> ```
> CORRECT — the writer acts only on adjudicated absence:
> ```
> score ≥ high on one body line   →  ALREADY-PRESENT (evidence: line + quote)
> otherwise                       →  semantic reviewer screens: present / missing / split
> reviewer MISSING ∪ split halves →  append once per file
> gate spot-reads the lowest-score ALREADY-PRESENT rulings, not the largest appends
> ```

Four operative points:

- **Classify the scorer's verdicts by what they can evidence, not by symmetry.** ALREADY-PRESENT needs one evidence line the auditor can read. MISSING is an absence claim a lexical instrument cannot make. Widen the band the semantic reviewer sees rather than trusting the low tail.
- **Sequence the semantic adjudicator before the writer.** The plan ran the writer on the MISSING set and the adjudicator on the AMBIGUOUS set in parallel. Reversing them removed the duplication risk and the "merge into the section the writer created" step in one move.
- **Hand-check the extremes, and treat a disagreement at the low end as a class finding.** One disagreement in three low-tail samples was the signal. The runner correctly declined to re-tune thresholds to fit it. The orchestrator's job was to measure how big the class was (one probe, 46 flips) and re-plan.
- **Move the gate's spot-check to where the asymmetric risk now sits.** With 749 characters appended, duplication was trivial to check. The residual risk was a wrong ALREADY-PRESENT ruling, which a later session would turn into permanent loss. The ten spot-reads went to the ten lowest-score ALREADY-PRESENT rulings instead of the ten largest appends.

**Applies to** any migration or dedup session where a mechanical similarity score decides what a writer copies: index-to-item harvests, documentation consolidation, changelog or note merges. It also applies to any plan whose hazard callout names a failure mode that the plan's own gate cannot measure. There the sequencing of writer and reviewer is the control, not the gate.

### 10.6 In refuse-by-default tooling a similarity heuristic may only escalate

> [!constraint] A heuristic may only move a case toward refusal, never toward "safe to drop"
> In a tool whose safety property is "refuse when unsure", similarity can flag AMBIGUOUS. Only an exact match after normalisation may declare content already present. This is the mirror of §10.5. There a lexical scorer's "absent" verdict was not evidence of absence. Here its "present" verdict is not evidence of presence either. In a destructive path the false "present" is the one that loses data.
>
> A migration tool rewrites a consumer's index and appends its prose to item files. Its contract was recognise-or-refuse: move every byte somewhere, or stop. It decided whether prose was "already present" in an item body with 5-character shingle containment of 0.75 or more. The runner and the tests treated that as dedup. A third adversarial review ran two real sentences through it:
> - The body says "should be removed" and the row says "should NOT be removed". Score: 0.87, so ALREADY-PRESENT.
> - The body says "Deferred to Q2" and the row says "Q4". Score: 0.85, so ALREADY-PRESENT.
>
> Both units would be skipped, the ledger would count them as deduplicated, and regeneration would delete the only copy of the differing fact. A near-duplicate is exactly the case where the difference is the information.
>
> WRONG:
> ```
> shingle_containment >= 0.75 → ALREADY-PRESENT → skip append          # negation scores 0.87
> ```
> CORRECT:
> ```
> exact normalised match → ALREADY-PRESENT
> similarity → AMBIGUOUS → refuse unless <flag> (the explicit append-ambiguous opt-in)
> ```
>
> Dry run on short stand-ins for the two pairs. A 5-character shingle containment scorer reported 0.77 for the negation pair and 0.90 for the changed-quarter pair, both at or above 0.75. An exact comparison after lower-casing and whitespace collapse reported no match on both. The longer real sentences scored 0.87 and 0.85.

**Test the rule with the near-miss pair.** The regression test feeds the negation pair and the changed-value pair. It asserts both come out AMBIGUOUS and that neither is skipped. A fixture of exact duplicates and clear misses never reaches the threshold band.

**Applies to** any migration, dedup, merge or prune tool that decides by similarity whether content is safe to discard.

### 10.7 Gate review convergence on consequence classes, not on severity labels

> [!constraint] Write the blocking consequence classes into the stopping rule, then classify each finding yourself
> Block on data loss, silent corruption and false success reports. Style and cost do not block. A rule keyed to the reviewer's labels can be satisfied by a label. Severity does not ratchet on agreement either: see [`verify-verdict-source.md`](verify-verdict-source.md) §3 (Severity Does Not Ratchet on Agreement). A stopping rule keyed on severity has the mirror gap.
>
> Each review round of one destructive diff found new defects: 10, then 10, then 10. To stop the loop the orchestrator set a convergence rule: "the third round blocks only on HIGH findings". Round three returned 0 HIGH and 4 MEDIUM, two of them confirmed silent data loss. Applied mechanically, the rule would have shipped them. The reviewer's severity label measured its confidence and scope, not the consequence to a consumer.
>
> WRONG:
> ```
> convergence: "block on HIGH only" → 0 HIGH → ship          # 4 MEDIUM were data loss
> ```
> CORRECT:
> ```
> convergence: block on {data loss, silent corruption, false success}, classified by the orchestrator
> ```

**Applies to** any iterative review loop that needs a stopping rule, and any destructive diff reviewed pre-commit under §10.4.

### 10.8 What the adversarial review must be told, and when it stops

> [!constraint] The runner that wrote each feature also wrote its fixtures. A review finds defects in the cases nobody fixtured
> The per-task gates check that the code does what its author tested. For a destructive disposition, run the adversarial review of §10.4 before commit as a gate distinct from the suite. A green suite, a clean lint and a PASS sweep are not evidence against the case classes below.
>
> One session added repair flags and budgeted changelog parts to a migrator that overwrites item files, rewrites the index and re-splits changelogs. Each of five tasks passed its own gates: tests, lint, the identifier battery and module size. The orchestrator recomputed each gate independently. The verification task reported all six closing gates PASS on 1,207 passed and 0 failed.
>
> A separate adversarial code review returned 10 correctness findings and 1 identifier leak. A fix pass checked each finding against the code. **13 of 14 were confirmed and none was refuted.** The remaining one was a genuine contradiction in the design, which the user decided. The confirmed defects included:
> - **Silent data loss:** `--reconcile index-wins` overwrote `blocks:` after the edge union and deleted an edge that only the dependencies table recorded.
> - **Stale state:** a re-split into fewer changelog parts left the old higher-numbered parts on disk.
> - **A false budget claim:** a part could exceed the budget while the run printed "within budget".
> - **An unguarded destructive path:** `--split-changelog --write` skipped the git dirty-tree gate.
> - **A broken resume:** after an interrupted `--write`, the rerun refused the files it had already repaired.
> - **A leak no gate could see:** two docstrings named a session folder, and neither leak predicate listed a session token.

Name these case classes in the review brief. Each one produced defects that nobody wrote a fixture for:

| Case class | Shape of the defect |
|------------|---------------------|
| Interaction | Two flags, each correct alone, conflict in combination |
| Shrink | The layout gets smaller rather than larger |
| Interruption | A rerun after a partial write, or a failure after the first replace |
| Rerun | A second run in the same state backs up half-migrated files over the true pre-images, or appends every note again because the "already present" test used the pre-image's newline |
| Alternate path | The same operation through a second entry point that skips a guard, or through CRLF input |
| Unfixtured input | A BOM on part 1, an unclosed comment, a symlinked copy that writes through to the shipped file, a `paths:`-only edit treated as unedited, CRLF on one copy, a flag whose value is `off` |
| Scope | A project-scope run copies a deep, path-scoped project file over the global copy that every project loads |

An alternate path includes a dry run that hits the dirty-tree gate before its own branch, a standalone CLI, an already-migrated branch that regenerates with no backup, and two casings of one path.

Six rules follow:

- **Give the review the destructive surfaces by name.** List each overwrite, delete and re-split path, byte preservation, refuse-or-guess behaviour, and any known edge case. A focused brief found a part-over-budget defect that the task had written off as unreachable ("toy budget only"). In four recurrences the brief named suspected defects, the review confirmed them, and it found more in the same neighbourhood.
- **Verify every finding before fixing it, and route design contradictions to the user.** The fix runner confirms or refutes each claim against the code. It fixes only the confirmed ones and writes a regression test for each that fails on a pre-fix copy. It does not change behaviour where the design contradicts itself.
- **A conservation proof, a golden proof, a release dry run and a mutation score do not replace the review.** A golden proof against a hand migration showed 77 deltas and 0 unexplained. It missed a CRLF/LF mix and an unclosed comment because its base tree had neither. A ledger line `Unaccounted: 0` was a tautology, because it summed only what had been collected. A mutation score of 8 of 8 classes caught measured the tests against breaks the author could think of. The runner chose each mutation, and the mutations probed behaviours its own fixtures already covered. A review then returned 10 findings, and the fix runner reproduced all 10 with a test that failed first. Re-run a release dry run after fixes that touch the upgrade path.
- **Review the fix diff when a fix changes a shared predicate.** A fix that changes what one function answers moves every other function that answers the same question. The first review cannot see that, because the fix did not exist yet. In one session a first review returned 9 findings, one a data-loss path in the previous session's code. A review of the fix diff then found 10 more, including two inconsistencies the first fix itself created: a `paths:`-aware verdict disagreed with the refresh condition and with the copy classifier. The second round cost one dispatch.
- **Stop when a round finds nothing destructive.** Round two had no data-loss finding, so the session fixed it and committed without a third review. Bound the loop by consequence class, not by an empty findings list. §10.7 (Gate review convergence on consequence classes, not on severity labels) names the blocking classes.
- **Widen a leak predicate from a term list toward a shape.** When the review finds a leak the predicate missed, add the shape to every downstream copy of the battery. A session token is one such shape.

**Applies to** any session whose diff adds or widens a delete, overwrite, migrate, prune or sweep disposition. It matters most when one runner wrote both the feature and its tests. It applies to any planned session that ends in a "verification" task. That task re-runs the same questions, so its PASS does not replace the review.

### 10.9 An exemption modelled on a reference check copies its whole refusal condition

> [!constraint] A fix that makes one failing test pass is shaped by that test's fixture. The reference check it imitates refuses on more than one condition, and the other conditions carry the safety property
> When an exemption is modelled on a reference check, copy its whole refusal condition, not the clause that matches the failing fixture. §10.1 (Enumerate the config-interaction matrix in the spec) lists the gates a new branch must consult. This section covers the exemption a new branch copies from one of them.
>
> A backlog index generator gained a guard: `--write` refuses an index that still has the hand-authored (legacy) table shape, so the generator cannot overwrite prose that was never migrated. The first version broke a protected migrator test. After a migration, an index with a custom name keeps a legacy-shaped table whose footer is a pointer to the changelog, and the guard refused it.
>
> The runner exempted any table whose footer matched the migrator's pointer regex (`POINTER_RE`). The fix reused the migrator's own idiom, so it looked principled, and the protected test passed. The review found the flaw. The migrator accepts a pointer footer only when three more conditions hold:
> - The pointer names this index's own changelog.
> - That changelog exists and is populated, not missing or header-only.
> - No row prose is still pending migration.
>
> The exemption checked none of them. After a `write_failed`, or after a hand edit, the next `--write` would pass the guard and overwrite prose that existed only in the table, with no backup.
>
> ```
> WRONG — exempt on the one clause the failing fixture satisfies:
> if POINTER_RE.search(footer): return OK            # foreign pointer, missing changelog, pending prose all pass
>
> CORRECT — call the reference predicate and require its accepted state:
> if changelog_state(index, footer) == "populated" and no_pending_prose(index): return OK
> # tests: foreign pointer → refuse; missing changelog → refuse; header-only changelog → refuse
> ```

Four rules:

- **Read the reference predicate end to end.** List every state it refuses. Mirror each one, or state in writing why it does not apply.
- **Prefer calling the reference predicate over re-implementing it.** The final fix moved the migrator's `_changelog_state` into the shared support module. The migrator delegates to it unchanged, and its 27 protected tests prove that. The guard then requires `populated`, so the two checks cannot drift apart.
- **Write one test per refused state, not one test for the accepted state.** The first fix had a positive test only (the pointer footer passes). The review fix added negative tests for a foreign pointer, a missing changelog and a header-only changelog. Each one fails when its clause is reverted.
- **Name what the exemption cannot check.** Pending row prose needed the migrator's full plan, and the generator could not import it without a cycle. Record that check as a named backlog candidate instead of silently leaving it out.

**Applies to** any guard, refusal or safety check that gains an exemption to unblock a failing test, especially a protected or pinned one. It applies to any code that imitates a sibling module's predicate through a shared regex or constant rather than calling the predicate.

---

*Anchor: [session-plan-requirements.md](session-plan-requirements.md) §8 Required Files Per Level, Execution Strategy (the DELEGATED-trigger canonical). Companion: [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md).*
