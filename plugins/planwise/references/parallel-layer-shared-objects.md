---
description: Two tasks in one dispatch layer acting on an object neither of them writes — a next-free identifier namespace, or an entity's decomposition. Carries the eligibility question that replaces the output-path test, the spawn-prompt clause that defers the allocation and not merely the write, and the decomposition diff that makes a missing half visible. Also covers the shared objects that are not files: the key name one task emits and another reads, the scratch folder every runner writes, and a directory a sibling's test enumerates. Consult while composing a parallel dispatch layer, before its spawn prompts are written.
consult-when: Composing a parallel dispatch layer — the allocation namespace, entity decomposition, emitted key names, shared scratch folder or directory listing that tasks share but none writes
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
- [4. Between-Runner Properties — Shared Objects That Are Not Files](#4-between-runner-properties--shared-objects-that-are-not-files)
  - [4.1 Pin the Emitting Key Name, Not Just the Value](#41-pin-the-emitting-key-name-not-just-the-value)
  - [4.2 A Fallback That Substitutes a Knowingly-Degraded Input Is Worse Than a HALT](#42-a-fallback-that-substitutes-a-knowingly-degraded-input-is-worse-than-a-halt)
  - [4.3 Namespace the Scratchpad by Task Id in the Spawn Prompt](#43-namespace-the-scratchpad-by-task-id-in-the-spawn-prompt)
  - [4.4 A Test Asserting an Exact Directory Listing Depends on Everything in That Directory](#44-a-test-asserting-an-exact-directory-listing-depends-on-everything-in-that-directory)
  - [4.5 Audit the Between-Runner Properties Before Dispatch](#45-audit-the-between-runner-properties-before-dispatch)

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

**The namespaces, enumerated, so the check is concrete.** Reviewer-check numbers. Backlog and lesson identifiers. `§N` section numbers. Appended table row numbers. Migration indices. Scratch file names. Every one of them is shared state that each allocator reads and no allocator owns.

Scratch file names belong on the list because every runner in a session writes to one scratch folder. Two runners that each write one generic name collide, and one can read back the other's rows. A per-task prefix taken from the task id is immutable state, so the exemption below applies and no serialization is needed. The spawn prompt carries the prefix. See `agent-orchestration-delegated.md` section 1.8.

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

## 4. Between-Runner Properties — Shared Objects That Are Not Files

Sections 1 to 3 cover objects that a layer's members share and none of them writes: a counter and an entity's decomposition. Three more shared objects are not files. They are a key name that one runner emits and another reads, a working folder that every runner writes into, and a folder that a sibling's test lists. The write-set table shows none of the three. Each runner passes its own gate, because neither runner is wrong. The defect lives in the relationship between them.

**Disjoint declared outputs do not make parallel runners isolated.** An isolation clause covers the files a task declares. The defect lands in what the clause leaves out. It often corrupts how a result was computed, and no deliverable shows it.

### 4.1 Pin the Emitting Key Name, Not Just the Value

A value that passes from one session to the next is an output-vocabulary contract between two runners. "Record the series base" and "read `{ABBREV}_SERIES_BASE`" are two different contracts. Neither runner breaks its own contract when the names differ.

Inject the value as a literal first. Section 1.6 of `agent-orchestration-delegated.md` and the `Base commit:` line of the spawn-prompt skeleton in `templates/orchestration.md` carry that route. A lookup by key name is the fallback, for a value the orchestrator cannot resolve before dispatch.

> [!constraint] Look up the key the emitter writes, and treat a miss as unresolved
> A brief told a downstream session to adopt a series base from its predecessor's Recovery file. The brief's lookup used the key `{ABBREV}_SERIES_BASE`. The predecessor had written `{ABBREV}_S{NN}_BASE`. The lookup returned 0 hits, and the brief's fallback for 0 hits was "mint one here and say so". A 0 that means "named differently" looks the same as a 0 that means "never recorded". The fallback took the degrading reading. The closing identifier sweep would have covered 3 files instead of 7.
>
> WRONG — the consumer looks up a key that the emitter never agreed to use:
> ```
> Grep  pattern='{ABBREV}_SERIES_BASE'  path='.../{Abbrev}-S{NN}-{MM}-Recovery.md'
> # 0 hits -> "the predecessor recorded none" -> mint a base from today's HEAD
> ```
> CORRECT — the consumer looks up the key the emitter writes, and a miss halts the task:
> ```
> Grep  pattern='{ABBREV}_S{NN}_BASE'  path='.../{Abbrev}-S{NN}-{MM}-Recovery.md'
> # 1 hit carrying <sha> -> adopt it verbatim
> # 0 hits -> HALT and report. Never substitute a locally derived value.
> ```

Prefer a lookup by the value's shape, such as a 40-digit hex string next to a labelled row. A stable role name that the Master Plan fixes also works. Both beat an identifier that each session mints for itself.

### 4.2 A Fallback That Substitutes a Knowingly-Degraded Input Is Worse Than a HALT

The lookup miss in section 4.1 was a stumble. The documented recovery turned it into a defect, because the recovery produced a plausible wrong value and did not stop. A HALT is loud and cheap, and it lands on someone who can resolve it. A degrading fallback is silent. It launders a lookup failure into a measurement, and the next gate reports a verdict on that measurement.

> [!constraint] Trace a fallback's output to every gate scoped to it
> When a brief writes a fallback branch for "the upstream value is absent", ask what the branch's output does to each gate that consumes it. If the answer is "narrows the gate", the branch must HALT instead.

The degraded outcome did not fail a gate, which someone would have noticed. It produced an UNCERTAIN, a result that the plan's own criteria permitted and even described. The plan predicted the symptom and still shipped the brief that caused it.

**A correct in-session save is not a reason to skip the capture.** It is evidence that the defect is systemic, not incidental. This defect recurred across consecutive sprints of one plan. The orchestrator handled it correctly both times and recorded it neither time.

### 4.3 Namespace the Scratchpad by Task Id in the Spawn Prompt

Section 1 lists scratch file names among the shared namespaces, and section 1.8 of `agent-orchestration-delegated.md` holds the `Scratch prefix:` constraint. This subsection adds the hazard, three practices and the wider scope.

Runners create undeclared working files in a folder they all share. Examples are helper scripts, probes, intermediate dumps and hash manifests. Capable agents converge on the same obvious name for the same obvious job. **The better the runners, the more alike their file names.**

The observed collision was harmless, and the hazard is not. Three runners had disjoint declared outputs, and two of them wrote `scratchpad/shingle_check.py`. One file overwrote the other after both checks had run, and a later task held the session's authoritative gate. Both facts were luck. A runner that calls a sibling's script gets a result computed by logic written for a different file, with different exclusions. The script runs, prints a number and raises no error. The runner has no way to know.

> [!constraint] Scope the scratchpad in every parallel spawn prompt, with the task id as the namespace
> WRONG — the spawn prompt scopes the declared outputs and says nothing about the shared folder:
> ```
> Files you may write: Sources/Part-2.md
> # The runner also writes scratchpad/shingle_check.py. So does its sibling. The last write wins.
> ```
> CORRECT — the prompt carries the skeleton's scratch line, so the task id names every undeclared file:
> ```
> Files you may write: Sources/Part-2.md
> Scratch prefix:   {task-id}-  (start every scratch file name with this prefix; never read a scratch file you did not write in this run)
> Never write a generically-named helper; a sibling will pick the same name.
> ```

- **Keep the skeleton's `Scratch prefix:` line in every parallel spawn prompt.** One line removes the class. Never rely on runners to invent the convention. One runner in three did so in the observed case, and that rate produces intermittent failures that nobody can reproduce.
- **Treat a collision report as a contract defect.** Both runners behaved well. They reported the collision, left the sibling's file intact and recreated their own under a safe name. The dispatch contract never told them that the folder was shared.
- **Never let a shared-scratchpad result stand as a gate.** A self-check computed by a helper that a sibling may have overwritten is drafting feedback, not evidence. Put the authoritative check in a task that runs its own script over the full deliverable set.

The rule covers every mutable working folder that concurrent agents share. Temp folders, cache folders and shared staging areas are examples.

### 4.4 A Test Asserting an Exact Directory Listing Depends on Everything in That Directory

Declared outputs can be disjoint in the ordinary sense, with different files and no overwrite, and the tasks still collide. The cause is a test that lists a folder which a sibling must add to. The write-set table does not show that coupling.

In the observed case, task 6's brief required probe fixtures in a folder that task 5's suite enumerated. Task 6 did what its brief said. The suite went from 117 passed to 1 failed and 116 passed. The command-line tool was correct and the assertion was brittle. The collision was latent at plan time, because task 6's brief already named the fixture by path.

> [!constraint] Derive the expected listing from the same glob the code under test uses
> WRONG — a hardcoded constant pins the folder, so any legitimate addition fails the test:
> ```python
> def test_cli_recurses_over_a_directory_of_markdown():
>     ...
>     assert scanned == {f.name for f in ALL_FIXTURES}   # ALL_FIXTURES holds the six original fixtures
> ```
> CORRECT — the expectation comes from the glob, the equality stays, and a guard keeps the derived set from passing vacuously:
> ```python
> expected = {p.name for p in FIXTURE_DIR.rglob("*.md")}
> assert scanned == expected
> assert {f.name for f in ALL_FIXTURES} <= expected
> ```

- **Prefer a derived expectation to a hardcoded set for every assertion over a directory.** Both forms test the same property, and only the derived form survives a legitimate addition. Keep the equality, because complete recursion is worth asserting. Keep the guard too. An equality alone passes against an empty folder.
- **Never make a constant with semantic meaning the consumer of a structural assertion.** In the observed case `ALL_FIXTURES` meant "the six original scoring fixtures", and other tests relied on that meaning. The fix left it intact and changed which test consumed it. Widening it would have destroyed a useful distinction.
- **The runner that trips a sibling's gate reports and does not repair.** An independent verifier that edits the module it gates loses its independence, and it lacks the context for what the constants mean elsewhere. Route the report to the owning task's runner. That runner still holds the context.

State the cause accurately when you report this class. In the observed case an earlier scope fix had moved one fixture's path, which looked like the cause and was not. The accurate cause decided whether that earlier fix was sound.

### 4.5 Audit the Between-Runner Properties Before Dispatch

> [!practice] Audit four non-file shared objects before dispatching a parallel layer
> The write-set intersection check proves that the declared outputs are disjoint. It says nothing about four things that are not files:
>
> - **The key names** that each runner emits and consumes (sections 4.1 and 4.2).
> - **The shared working directory** that every runner writes undeclared helpers into (section 4.3).
> - **The directory listings** that any runner's tests enumerate (section 4.4).
> - **Any fallback branch** whose degraded output feeds a later gate (section 4.2).
>
> Audit each of the four before dispatch. No write-set table shows them, and neither runner's own gate can see them afterwards.

---

*Cross-reference: [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.6, §1.8, §1.13 · [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.24 (a structure contract needs a literal template) · [`agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md`](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md) §1.31 (a shared precondition belongs to the orchestrator) · [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17*
