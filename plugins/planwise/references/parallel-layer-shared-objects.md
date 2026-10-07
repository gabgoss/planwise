---
description: Two tasks in one dispatch layer acting on an object neither of them writes — a next-free identifier namespace, or an entity's decomposition. Carries the eligibility question that replaces the output-path test, the spawn-prompt clause that defers the allocation and not merely the write, and the decomposition diff that makes a missing half visible. Consult while composing a parallel dispatch layer, before its spawn prompts are written.
paths: {planwise_root}/{plans_dir}/**
---
# Parallel Layer — Shared Objects No Task Owns

**Purpose:** A layer whose members write genuinely disjoint files can still be defective. The object two of them share is not always a file. Each runner is individually correct, each passes its own gate, and the defect lives only in the space between them. That space is the one no per-task instrument inspects.

**Read this when** you are composing a dependency layer for parallel dispatch, and again before you write that layer's spawn prompts.

Two neighbouring rules own machinery this file builds on and does not restate. [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.13 owns the shared-edit-target strategy matrix and already states that the shared target may be a counter rather than a file. §1.6 owns injecting a resolved value into every prompt as a literal. [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17 owns the scaffold-time write-target intersection, and §17.2 owns its counter form. Both of those prescribe the same remedy: the orchestrator pre-resolves the number and hands it out. This file covers what neither reaches. It covers the layer where pre-resolution is not available, because how many identifiers each runner needs is not knowable until the runner has done the work. It covers the spawn-prompt wording that makes a deferral actually hold. And it covers a second class of shared object, an entity's decomposition, which allocates nothing at all.

## Table of Contents

- [1. Parallel Eligibility Tests Allocation, Not Just Output Paths](#1-parallel-eligibility-tests-allocation-not-just-output-paths)
- [2. A Deferral Must Name What Is Deferred — the Write, AND the Allocation](#2-a-deferral-must-name-what-is-deferred--the-write-and-the-allocation)
- [3. Two Decompositions of One Entity Leave a Seam Nobody Owns](#3-two-decompositions-of-one-entity-leave-a-seam-nobody-owns)

---

## 1. Parallel Eligibility Tests Allocation, Not Just Output Paths

> [!constraint] Ask the allocation question separately from the file question
> The eligibility test that licenses a layer normally asks one thing: **do two tasks write the same file?** A layer can answer that correctly with "no" and collide anyway. The question that catches this whole class is broader:
>
> **Do two tasks derive a value from shared mutable state that neither of them writes?**
>
> ```
> WRONG — eligibility decided on output paths alone:
> layer = {T2 → fileA, T4 → fileB}
> outputs disjoint  ⇒  dispatch in parallel      # both then compute next-free = NNN
>
> CORRECT — eligibility also tests allocation:
> layer = {T2 → fileA, T4 → fileB}
> outputs disjoint                                       ✓
> allocates from a shared namespace? T2: yes (Check #)
>                                    T4: yes (Check #)   ✗ NOT parallel-safe for allocation
> ⇒ dispatch in parallel, but DEFER allocation to a serialized pass;
>   runners return draft text with numbers explicitly VOID
> ```

**The namespaces, enumerated, so the check is concrete.** Reviewer-check numbers. Backlog and lesson identifiers. `§N` section numbers. Appended table row numbers. Migration indices. Every one of them is shared state that each allocator reads and no allocator owns.

**The collision is deterministic, not a race.** Concurrent runners each read the same pre-dispatch value, and each computes the same "next" value from it. So the collision does not depend on timing. It reproduces on every run. It cannot be tuned away by ordering or by retries. State this plainly wherever the hazard is recorded, because a hazard a reader classifies as a race gets retried instead of designed out.

**Two properties make deferral work, and both are worth copying.**

1. **Separate the content from the identifier.** Draft text is safely produced in parallel. Only the number has to be serialized. Deferring the number costs nothing and blocks nothing.
2. **Make the voiding explicit at the source.** A downstream reader who finds two drafts carrying the same number, with no marking, cannot tell a real allocation from a guess.

> [!decide] The exemption — immutable state does not need serializing
> This section does not apply where the "next" value derives from **immutable** state: a content hash, a timestamp supplied by the orchestrator, a task index passed in at dispatch. Those are collision-free by construction, and switching the allocation onto one of them is the cheap fix when serialization is unwelcome. Without this exemption the rule reads as "serialize anything that computes a next value", which is both wrong and expensive — and a rule that over-fires is routed around.

---

## 2. A Deferral Must Name What Is Deferred — the Write, AND the Allocation

> [!constraint] Deferring the edit does not defer the number
> ```
> WRONG — the deferral names only the write:
> Do NOT author an inline Check block; do NOT edit the shared registry.
> Record `deferred` and include draft Check text in your status block.
>
> CORRECT — the deferral names the allocation too, and says why:
> Do NOT author an inline Check block; do NOT edit the shared registry.
> Record `deferred` plus draft Check TEXT with NO NUMBER ASSIGNED.
> (Two runners in a previous layer independently drafted "NNN" for unrelated
>  rules — that is the collision this rule exists to prevent.)
> ```

**The diagnosis.** Deferring a shared-resource *edit* does not protect a shared *namespace*. Runners that cannot see each other will independently compute the same "next free" value and record it as if it were theirs. A draft artifact carrying a self-assigned identifier is indistinguishable, downstream, from an allocated one. Self-numbering a draft also feels like diligence, so a runner following the WRONG form is behaving well by its own lights.

**Give the reason, not just the prohibition.** A runner told *why* a constraint exists can extend it correctly to cases the wording did not anticipate. A runner given a bare prohibition satisfies its letter. That is exactly how self-numbered "drafts" slipped through a deferral that had already banned the write.

**Every deferred number is void by construction.** However many drafts accumulate, the serializing pass re-derives the live maximum and allocates consecutively. Draft *text* is reusable verbatim. Draft *numbers* are never inherited, including from a runner that appeared to reserve one.

**Measured effect.** One layer ran the WRONG form over a shared check-number namespace with two concurrent allocators and collided. The same namespace then ran a **five-way** parallel layer under the CORRECT form, with one line added — draft text with no number assigned, plus the reason. That layer produced zero numbers claimed and zero collisions.

> [!practice] Keep §1 and §2 as separate obligations
> §1 is the eligibility question an orchestrator asks while **composing** a layer. §2 is the clause it writes into each **spawn prompt** afterwards. Merged, they read as advice to the composer and become invisible to whoever writes the prompts. That is the second failure recorded here: the layer was composed correctly and the prompt still leaked the allocation.

---

## 3. Two Decompositions of One Entity Leave a Seam Nobody Owns

> [!constraint] One decomposition is authoritative; the others declare against it
> When two tasks in one layer each decide independently how many pieces an entity has, the entity is a shared object even though nothing is allocated. Five rules govern it.
>
> 1. **When a session's tasks decompose the same entity, make one task's decomposition authoritative and require the others to declare against it.** Two independent decompositions of one entity in one dependency layer is the hazard. Either hand the second task the first's split, or produce the split first and use it to size the second.
> 2. **Specify the consolidator's reconciliation as a DIFF of decompositions, not a rename of identifiers.** The required output is "N rows in → M sections out, and here is every row that maps to zero, one, or a shared section" — counts stated on both sides. A reconciliation that only harmonizes spelling cannot see a missing half. Had the measured step been specified the usual way ("make the identifiers consistent"), the correct action would have been a **rename**, and the missing half would have shipped invisibly.
> 3. **Count in = count out is necessary but not sufficient — state the mapping shape too.** The measured session's counts matched (8 in, 8 out) while containing one added section, one section with no matrix row, and one section covering two rows. Equal totals concealed three structural deviations. Only naming the shape exposed the gap.
> 4. **A scope narrowing inside a task file is a coverage decision, and it must be visible to the session's Success Criteria.** A task spec that quietly narrows an entity while the orchestration still claims to cover it makes the criteria false at the moment they pass. The narrowing belongs in the criteria as an explicit exception.
> 5. **When the downstream contract is a structural sweep, a missing member is invisible by construction.** Anything a `^## S-`-style Grep would count as complete needs its expected count asserted from an independent source — the matrix row count — never inferred from the artifact being swept.

**The generalisation, which is what makes this a rule rather than an anecdote: a gap that satisfies the completeness check is not detectable by the completeness check.**

**What the measured seam cost.** One task built the authoritative surface matrix and split a handler into **two** surfaces, citing that handler's own two dispatch branches. A second task extracted the same handler's behavioral contract. Its task file scoped the write set to one of the two modes, and it emitted **one** section. The handler's other dispatch contract was extracted by nobody. Both tasks passed every gate. The session's Success Criteria said the handler was covered, which was true for one of its two modes. The un-extracted surface carried six open backlog items and the third-highest change pressure in the matrix.

The opposite failure on the same lever — one writer whose declared `Output:` set is too small for the merge it owns, so the canonical entry it must amend lives in a sibling's file — is [`dispatch-decomposition-graph.md`](dispatch-decomposition-graph.md) §1–§2. Read the two together: this file says never two writers; that one says one writer, but give it the whole operation.

> [!hazard] A layer-level rule derived at review time protects only the namespace someone noticed
> The deferral that caught the allocation collisions in §1 and §2 was added as a **plan-level** rule at a sprint review, reasoning about one sprint's check blocks. It was not derived from the eligibility matrix, and the matrix as written would not have produced it. A future layer that allocates from a namespace nobody happened to notice at review time inherits no such protection. That is why the opening question in §1 is stated over *shared mutable state*, and not over identifiers alone — the decomposition case in this section allocates nothing, and a namespace-only framing loses it entirely.

---

*Cross-reference: [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.6, §1.13 · [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.24 (a structure contract needs a literal template), §1.31 (a shared precondition belongs to the orchestrator) · [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17*
