---
description: The gate that runs after every per-task acceptance check has passed and before consolidation. Covers why a per-task gate is structurally blind to whole-set properties, running a session criterion at the first task that makes it runnable, cross-checking claims that appear in more than one output, and pinning the output vocabulary as literal strings before fan-out. Consult when a parallel batch has returned and every runner reports green.
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

**The blindness is structural, not an oversight.** A per-task gate is scoped to that task's own outputs. That scoping is exactly what makes it cheap and parallelisable, and it is the same property that makes it unable to see anything true only of the set: a claim that appears in two outputs and disagrees with itself, a label vocabulary that diverges three ways, a session criterion that nobody's task owns yet.

**Recompute is not a substitute, and the reason is worth holding.** Recomputing a delegated verdict from its own reported evidence catches an agent that misread its evidence. **It cannot catch an agent that read its evidence correctly and drew a true-but-partial conclusion**, because there is no internal inconsistency to detect. Nothing a stricter per-task gate could do would help — the output is conformant, the reasoning is sound, and the defect is entirely outside the window.

**So the site is forced.** The orchestrator holds more than one slice. It is the only party that can compare them. That is the same argument that makes it the right recompute site, applied one level up.

Fan-out makes this systematic rather than rare. Splitting work across agents to get fresh context means each agent sees a slice. Wherever two slices overlap or must compose, each can be locally right and jointly wrong.

---

## 2. Run Every Session Criterion at the First Task That Makes It Runnable

> [!constraint] Ownership says who must make it pass, not when it may first be checked
> |  | Owning task | First runnable |
> |---|---|---|
> | Who the plan names | Task 4 | — |
> | When the command first executes at all | — | Task 1 |
> | Cost of a defect found here | 3 tasks of rework | 1 corrective dispatch |

**Four operative rules.**

1. **At every acceptance gate, ask which session-level criteria just became runnable.** Then run them, regardless of which task the plan assigns them to.
2. **Distinguish "owns" from "first runnable".** Ownership says who must make the criterion pass. It says nothing about when it may first be checked. Treating the two as the same defers every session gate to the point where rework is most expensive.
3. **A green per-task gate is no evidence about session-level properties.** In the measured session Task 1 passed 5 of 5, and its output still could not satisfy criterion 1.
4. **Prefer a check that is cheap and early over one that is authoritative and late.** A collection-only test run took under a second and was enough to expose the defect three tasks early.

> [!constraint] Run a failing session criterion as a diagnostic, not as a verdict on the runner
> Establish provenance before assigning cause. In the measured case the artifact was byte-identical to the pinned spec, so the defect was upstream in the plan. Skipping that step would have sent a correct runner to "fix" correct work.
>
> **Cost if this is ignored.** A session-level defect surfacing at the last task arrives bundled with that task's own results. It is easily misread as *that task's* failure. The runner is then sent into a retry loop against a defect it did not cause and cannot fix from inside its own scope.

**The measured case.** A four-task session's first success criterion — a full selftest suite green at zero cost — belonged, by the plan's own wording, to Task 4. Task 1 merely created the config file the criterion invokes. The orchestrator ran the session criterion at Task 1's gate anyway, purely because Task 1 had just made it *runnable*. It failed immediately: 321 tests collected from the wrong directory, 9 collection errors, with the root cause in the pinned Execution Input rather than in Task 1's work. Applied at that moment it cost one corrective dispatch. Discovered at Task 4 it would have landed after three tasks had built on the broken contract, and after the same wrong invocation had been copied into three more sets of verification commands.

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

> [!constraint] The field with a pinned literal converged; the field with only a semantic description diverged three ways
> |  | Session A — semantics only | Session B — literal pin |
> |---|---|---|
> | What the task files gave | "a contract across seven dimensions" — a count plus a semantics | the canonical labels as literal strings, in a stated order, with the downstream consumer named |
> | Shapes emitted by three runners | three (bolded prose labels; numbered subsections plus two extra dimensions; `### D1`…`### D7` plus three extra) | one, identical, in canonical order, on the first attempt |
> | Crosswalk needed at the join | nine vocabularies mapped onto seven | none |
> | Residue | one runner also drifted inside its own output, renumbering every dimension after the second and silently turning an internal "see §6 below" into a dangling pointer | one runner emitted the labels unnumbered where the others numbered them — same words, same order, normalized with zero content change |

**The diagnosis.** "Seven dimensions" names a **count and a semantics**, not a **shape**. A runner told what to cover but not what to emit invents a reasonable local format, and every such invention is defensible in isolation. In Session A all three runners delivered all seven dimensions, in full, with citations, and all three passed their own gates.

**Two scaffold-time rules carry the load.**

1. **Pin the output vocabulary in the task scaffold, not just the dimension count.** Give the canonical labels as literal strings to be emitted verbatim, in a stated order, the way a heading contract already does. A count plus a semantics under-determines the artifact. A literal template determines it.
2. **State the downstream consumer.** A runner told that a label is a machine-read contract treats it as one. A runner told a label is "the seven dimensions" treats it as prose.

**What the counterfactual bounds, as well as proves.** Session B ran the identical decomposition the next day with the canonical labels written into all three task files, the consumer named, and supplementary dimensions required to go *after* the canonical set rather than in place of one. The pin fixed the **label set and order**, which is where the expensive divergence lives. It left the **typographic form** unpinned, which is where the cheap divergence lives, and that is exactly where the one residue appeared. Pin the numbering too when a downstream consumer parses positionally.

**The one shape that was pinned in Session A held perfectly.** A heading bound to a literal string, with the stated rationale that two downstream consumers search for that exact prefix, was emitted correctly by all three runners. The single parenthetical deviation was caught in one search, because there was an exact string to compare against.

**Two remaining rules, with their honest status.**

- **Add a cross-runner shape check to the batch gate.** After a parallel batch, diff the emitted section-label sets across outputs and flag divergence before dispatching the consolidator. It is cheap, and it moves discovery from the expensive join to the cheap reconciliation. It is the backstop for a session that inherits un-pinned task files. **It remains unproven** — it was never exercised, because the pin meant there was no divergence for it to catch. Presenting it as validated alongside the pin would misstate the evidence and inflate a backstop into a proven control.
- **When divergence has already happened, crosswalk — do not rewrite.** Rewriting outputs to match risks the content loss consolidation exists to prevent. A crosswalk costs a dozen lines and preserves provenance. File the divergence upstream against the scaffold afterwards.

**The intra-runner variant.** A runner that declares a framework at its own head can still drift across its own sections. Renumbering drift breaks internal `§N` cross-references silently. A shape check inside a single long output is worth the one search it costs.

> [!practice] Keep the pin and the diff in one section
> §4 is the only section here carrying work on both sides of the dispatch — a scaffold-time pin and a batch-time diff. The pin is motivated only by the divergence the diff would otherwise have to catch. Split into a separate scaffold rule, the pin reads as a style preference.

---

*Cross-reference: [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.16, §1.17.4 · [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.24 · [`parallel-layer-shared-objects.md`](parallel-layer-shared-objects.md) (the composition-side rules governing the batch this gate inspects)*
