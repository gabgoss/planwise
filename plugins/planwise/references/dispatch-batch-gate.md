---
description: The gate that runs after every per-task acceptance check has passed and before consolidation. Covers why a per-task gate is structurally blind to whole-set properties, running a session criterion at the first task that makes it runnable, cross-checking claims that appear in more than one output, and pinning the output vocabulary as literal strings before fan-out. Consult when a parallel batch has returned and every runner reports green.
consult-when: A parallel batch returned and every per-task gate is green — the three checks only the orchestrator can run before consolidation
paths: {planwise_root}/{plans_dir}/**
---
# Dispatch Batch Gate — the Checks Only the Orchestrator Can Run

**Purpose:** Every runner can pass every acceptance check and the batch can still be defective. This is not a case of gates run sloppily. The gates were run, they were correct, and they could not see the defect, because from inside a single task the output is perfectly conformant.

**Read this when** a parallel batch has returned, its per-task gates are green, and you are about to hand the outputs to consolidation.

Three neighbouring rules own machinery this file builds on and does not restate. [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.16 owns recomputing a delegated verdict from its own primary evidence, and §1.17.4 owns gating acceptance on on-disk evidence rather than a `completed` status. [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.24 owns the structure contract — a literal template file, a heading checklist, and a pre-acceptance Grep. Those are per-task instruments, and §4 below extends the last of them. This file covers what none of them reaches: the properties that are true only of the **set**.

## Table of Contents

- [1. The Batch Gate Is a Distinct Step, and It Is the Orchestrator's](#1-the-batch-gate-is-a-distinct-step-and-it-is-the-orchestrators)
- [2. Run Every Session Criterion at the First Task That Makes It Runnable](#2-run-every-session-criterion-at-the-first-task-that-makes-it-runnable)
- [3. Cross-Check Claims That Appear in More Than One Output](#3-cross-check-claims-that-appear-in-more-than-one-output)
- [4. Pin the Output Vocabulary Before Fan-Out; Diff the Emitted Shapes After](#4-pin-the-output-vocabulary-before-fan-out-diff-the-emitted-shapes-after)

---

## 1. The Batch Gate Is a Distinct Step, and It Is the Orchestrator's

> [!protocol] A named stage between per-task acceptance and consolidation
> The three checks in §2, §3 and §4 run once, after every per-task gate has passed, and before the consolidator is dispatched. Give the stage a name in the orchestration. A check that belongs to "whoever notices" belongs to nobody.

WRONG — the set checks belong to whoever notices, so the batch goes straight to consolidation:
```
every per-task gate green → dispatch the consolidator
```
CORRECT — a named stage runs the set checks between the two steps:
```
every per-task gate green → batch gate (§2, §3, §4) → dispatch the consolidator
```

**The blindness is structural, not an oversight.** A per-task gate is scoped to that task's own outputs. That scoping makes it cheap and parallelisable, and the same property makes it unable to see anything true only of the set: a claim that appears in two outputs and disagrees with itself, a label vocabulary that diverges three ways, a session criterion that nobody's task owns yet.

**Recompute is not a substitute.** Recomputing a delegated verdict from its own reported evidence catches an agent that misread its evidence. **It cannot catch an agent that read its evidence correctly and drew a true-but-partial conclusion**, because there is no internal inconsistency to detect. No stricter per-task gate would help. The output is conformant, the reasoning is sound, and the defect is entirely outside the window.

**So the site is forced.** The orchestrator holds more than one slice, so it is the only party that can compare them. The same argument makes it the right recompute site, applied one level up. Fan-out makes this systematic rather than rare: each agent sees a slice, and wherever two slices overlap or must compose, each can be locally right and jointly wrong.

`scripts/batch_gate.py` runs two of the stage's checks, and `templates/orchestration.md` calls it. Its `labels` command diffs the emitted section-label sets (§4). Its `items --ids` command requires each required id to appear exactly once across the outputs, and names every MISSING and DUPLICATE id.

The single-runner form of the same blindness — a status block whose every field is accurate and which still cannot see a coverage or uniqueness invariant — is [`verify-verdict-source.md`](verify-verdict-source.md) §4, with the member-naming gate output in its §6.

---

## 2. Run Every Session Criterion at the First Task That Makes It Runnable

At every acceptance gate, ask which session-level criteria just became runnable, and run them, whichever task the plan assigns them to.

WRONG — the criterion first runs at the task the plan names as its owner:
```
Task 1 creates the config file the criterion invokes → its own gate passes 5 of 5
Task 4 (owner) runs the criterion → 321 tests collected from the wrong directory, 9 collection errors
→ 3 tasks of rework, and the wrong invocation already copied into three more sets of verification commands
```
CORRECT — the criterion first runs at the task that makes it runnable:
```
Task 1 gate: a collection-only test run, under a second → the same failure, three tasks early
→ 1 corrective dispatch
```

1. **Distinguish "owns" from "first runnable".** Ownership says who must make the criterion pass. It says nothing about when it may first be checked. Treating the two as the same defers every session gate to the point where rework is most expensive.
2. **A green per-task gate is no evidence about session-level properties.** Task 1 passed 5 of 5, and its output still could not satisfy the session criterion.
3. **Prefer a check that is cheap and early over one that is authoritative and late.**

> [!constraint] Run a failing session criterion as a diagnostic, not as a verdict on the runner
> Establish provenance before assigning cause. In the measured case the artifact was byte-identical to the pinned spec, so the defect was upstream in the plan. Skipping that step would have sent a correct runner to "fix" correct work.
>
> **Cost if this is ignored.** A session-level defect surfacing at the last task arrives bundled with that task's own results. It is easily misread as *that task's* failure. The runner is then sent into a retry loop against a defect it did not cause and cannot fix from inside its own scope.

---

## 3. Cross-Check Claims That Appear in More Than One Output

> [!constraint] Adjudicate an overlap collision against primary evidence, never by picking a side
> ```
> WRONG — per-task gates pass, so the batch is accepted and handed to consolidation:
> Task 01 ✓ (output present, budget ok, verdicts recomputed, sections complete)
> Task 03 ✓ (same)
> → consolidate
> # The consolidated Part ships "the help-line marker is a working-tree differential"
> # as validated evidence. It is not. Neither runner was wrong; nobody compared them.
>
> CORRECT — after per-task gates, run one pass over CLAIMS THAT OVERLAP, and adjudicate
> collisions against primary evidence rather than picking a side:
> Task 01: "cached copy's marker = OLD text"           ┐ same object,
> Task 03: "cached copy reproduced the marker verbatim" ┘ incompatible claims
> → orchestrator reads the cached copy itself
> → both true: the cached tree is internally inconsistent between two of its own files
> → marker RETIRED; conclusion re-established on the surviving marker; divergence
>   flagged into the consolidation prompt so the Part states the adjudicated version
> ```

**How to find the overlaps cheaply.** The check is bounded, not quadratic. You do not re-read every output against every other. Build the overlap list from the plan you already hold: tasks whose Required Context shares a file, whose probes hit the same surface, or whose outputs feed the same consolidation section. In the measured session that set was three surfaces, and every one of the three produced either a corroboration worth recording or a defect worth adjudicating.

**Adjudicate against primary evidence, never by seniority or recency.** The reflex is to trust the later runner, the more capable model, or the one whose task "owned" the question. All three are wrong here. The owning task was the one carrying the marker that got retired. The orchestrator resolved it by reading the disputed artifact itself, two bounded searches, and the answer was that *both* reports were accurate and the object itself was inconsistent. No seniority rule would ever have produced that resolution.

**Record the divergence, do not silently reconcile it.** The consolidating agent must be told which source outputs carry superseded claims. It will otherwise copy them forward faithfully, because it has no way to know. Binding the adjudication into the consolidation prompt is what stops a retired marker from reaching the durable artifact.

> [!practice] §2 and §3 are not merge candidates
> Both are "run a check the per-task gate cannot", and that is where the similarity ends. §2 is about **when** a check may first run — a temporal property of one criterion. §3 is about **what** a check compares — a relational property of two outputs. A merged section states only one of them, and the one it drops is §2, because §3's evidence is more vivid.

---

## 4. Pin the Output Vocabulary Before Fan-Out; Diff the Emitted Shapes After

Before fan-out, give every task file the canonical output labels as literal strings, and after the batch returns, diff the label sets the runners emitted.

WRONG — the task files give a count plus a semantics:
```
task files: "a contract across seven dimensions"
→ three runners emit three shapes, and every runner passes its own gate
→ the join needs a crosswalk mapping nine vocabularies onto seven
```
CORRECT — the task files give the labels as literal strings, in a stated order, with the downstream consumer named:
```
task files: the canonical labels verbatim, in order, consumer named
→ three runners emit one identical shape, in canonical order, on the first attempt
→ no crosswalk
```

**The diagnosis.** "Seven dimensions" names a **count and a semantics**, not a **shape**. A runner told what to cover but not what to emit invents a reasonable local format, and every such invention is defensible in isolation.

**Scaffold-time rules.**

1. **Pin the output vocabulary in the task scaffold, not just the dimension count.** Give the canonical labels as literal strings to be emitted verbatim, in a stated order, the way a heading contract already does. A count plus a semantics under-determines the artifact. A literal template determines it. The task template's `**Required headings:**` field holds the list, and Check 46 in `scripts/lint_gate_checks_dispatch.py` flags an Expected Output that lists no backticked label.
2. **State the downstream consumer.** A runner told that a label is a machine-read contract treats it as one. A runner told a label is "the seven dimensions" treats it as prose.
3. **Require supplementary labels to go *after* the canonical set**, never in place of one.
4. **Pin the numbering too when a downstream consumer parses positionally.** The pin fixes the **label set and order**, which is where the expensive divergence lives. A **typographic form** left unpinned is where the cheap divergence lives: one runner emitted the labels unnumbered where the others numbered them, normalized with zero content change.

A pinned literal also makes a deviation cheap to find. A heading bound to a literal string, with the stated rationale that two downstream consumers search for that exact prefix, was emitted correctly by all three runners, and the single parenthetical deviation was caught in one search.

**Batch-time rules.**

- **Add a cross-runner shape check to the batch gate.** Diff the emitted section-label sets across outputs and flag divergence before dispatching the consolidator. `scripts/batch_gate.py labels` runs that diff. It is the backstop for a session that inherits un-pinned task files. **It remains unproven**: in the measured session the pin left no divergence for it to catch. Presenting it as validated alongside the pin would misstate the evidence.
- **When divergence has already happened, crosswalk — do not rewrite.** Rewriting outputs to match risks the content loss consolidation exists to prevent. A crosswalk costs a dozen lines and preserves provenance. File the divergence upstream against the scaffold afterwards.
- **Check the intra-runner variant.** A runner that declares a framework at its own head can still drift across its own sections. Renumbering drift breaks internal `§N` cross-references silently. A shape check inside a single long output is worth the one search it costs.

> [!practice] Keep the pin and the diff in one section
> §4 is the only section here carrying work on both sides of the dispatch — a scaffold-time pin and a batch-time diff. The pin is motivated only by the divergence the diff would otherwise have to catch. Split into a separate scaffold rule, the pin reads as a style preference.

---

*Cross-reference: [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.16, §1.17.4 · [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.24 · [`parallel-layer-shared-objects.md`](parallel-layer-shared-objects.md) (the composition-side rules governing the batch this gate inspects)*
