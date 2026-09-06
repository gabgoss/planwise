---
description: Five binding hygiene rules for what a multi-sprint scaffold must compute before it closes — retirement-deliverables deletion-set derivation, config-editing permission-round-trip scaffolding, first-task sprint diff-baseline recording, computed write-set intersection for declared-parallel sprints, and computed write-target intersection for declared-parallel dispatch layers. Part 2 of 2 — §1–§12, the rules governing what the scaffold emits, live in scaffolding-hygiene.md
---
# Scaffolding Hygiene — Part 2: Derivation and Parallelism

**Purpose:** Enforce five mechanical hygiene rules covering what a multi-sprint scaffold must **compute** before it closes — a derived deletion set, a permission round-trip, a diff baseline, and two write-set intersections. Each rule has been re-derived in independent planning sessions; review-cycle tokens are wasted relitigating the same recurring issues.

> [!important] This reference is split across two files — §1–§12 live in Part 1
> This part carries §13–§17. The nine binding rules and three advisory practices governing what the scaffold **emits** — Meta-Plan source detection, folder naming, abbreviation validation, status defaults, `Outputs/` creation, sequential-sprint prerequisites, no-improvisation of artifact types, deviation classes, plan sizing, cohort token uplift, the mega-scaffold review gate, and run-time-sound verification commands — live in [scaffolding-hygiene.md](scaffolding-hygiene.md), which keeps the original filename.
>
> Section numbers are continuous across the two files: §13 here follows §12 there, and a section keeps its `§N` wherever it lands. A citation naming §13–§17 resolves to this file; one naming §1–§12 resolves to Part 1.

This file is part of the §14 expansion referenced from the Companion Files and Extracted Protocols table in [session-planning-protocol.md](session-planning-protocol.md#companion-files-and-extracted-protocols). Read both parts before generating any `Sprint-{XX}-{Name}/` folders.

## Table of Contents

- [13. Retirement Deliverables Must Derive the Deletion Set](#13-retirement-deliverables-must-derive-the-deletion-set)
- [14. Scaffold a Config-Editing Plan for a Permission Round-Trip](#14-scaffold-a-config-editing-plan-for-a-permission-round-trip)
- [15. First Task of Each Sprint Records the Diff Baseline](#15-first-task-of-each-sprint-records-the-diff-baseline)
- [16. Declared Parallelism Requires a Computed Write-Set Intersection](#16-declared-parallelism-requires-a-computed-write-set-intersection)
- [17. A Dispatch Layer Declares a Computed Write-Target Intersection](#17-a-dispatch-layer-declares-a-computed-write-target-intersection)

---

## 13. Retirement Deliverables Must Derive the Deletion Set

A Deliverables list that removes a persistent artifact is produced by a sweep, not written from memory: run the sweep first, paste its output into the plan, and let that output be the list. Two sweep passes are needed because they catch different misses, and the hits must then be classified by ROLE — not file type — because exactly one role can silently undo the retirement.

### 13.1 Derive the Deletion Set Before Authoring Deliverables

> [!constraint] Run the sweep first, paste its output into the plan, and let that output be the list
> A Deliverables list that **removes** a persistent artifact is produced by a sweep, not written from memory.

```bash
# Run BEFORE writing the Deliverables section. Two passes, because they miss different things.
grep -rln --exclude-dir={vcs,cache dirs} "{qualified_artifact_name}" {source_roots} {docs}
find {source_roots} -name "*{artifact_name}*"   # catches members that never mention the name in prose
```

WRONG — the Deliverables section names the files the author remembers touching:

```markdown
6. **Deletions:** `{path}/refresh_helper.{ext}`, `{path}/driving_notebook.{ext}`
```

Both entries correct; the creator artifact absent; nothing in the plan detects the absence, because every gate the plan wrote checks the work that *was* scheduled.

CORRECT — the Deliverables section cites the command and pastes what it returned:

```markdown
6. **Deletions** — derived by `grep -rln "{qualified_name}" {roots}` + `find {roots} -name "*{name}*"`
   (run {date}; full output in `Outputs/{...}-DeletionSweep.md`):
   - `{path}/schema_definition.{ext}`   ← CREATOR (see §13.2 — omission undoes the retirement)
   - `{path}/refresh_helper.{ext}`      ← REFRESHER
   - `{path}/driving_notebook.{ext}`    ← DRIVER
   - 5 citer-only references listed in §13.3 (edit, do not delete)
```

### 13.2 Classify Sweep Hits by ROLE, Not by File Type

The sweep returns paths. What matters is what each path *does* to the artifact, because exactly one role can undo the retirement:

| Role | What it does | Typical members | Cost of omitting it |
|---|---|---|---|
| **Creator** | Re-creates the artifact from nothing | schema DDL, migration, generator script, seed/fixture loader, packaging or re-export declaration | **UNDOES the retirement** — the next routine run resurrects the artifact as an orphan nothing refreshes and nothing drives |
| Refresher | Populates or updates it | helper module, transform, ETL step | Inert dead code — fails or no-ops |
| Driver | Invokes the refresher | notebook, CLI entry point, scheduled job | Inert dead code |
| Citer | Names it in prose | docstrings, comments, docs, index rows, cross-references | Misleads the next reader toward a file that is gone (§13.3) |

The Deliverables list MUST either contain a Creator-role member, or state explicitly which creator is being **kept** and why (a shared file that also defines artifacts staying alive is a legitimate keep — but it must be named as a decision, not omitted as an oversight).

> A deletion list holding a Refresher and a Driver but no Creator is the failure signature. It reads complete — the two things a human remembers touching — and it schedules the artifact's return.

### 13.3 Citers Are Edited, Not Deleted

The same grep that derives the deletion set also finds every Citer. Citers are **edited, not deleted** — a docstring naming a deleted module as a precedent needs the precedent restated or the sentence dropped, not the docstring removed. Enumerate citers in the Deliverables list as a separate group with an explicit count, so the executor can verify the count rather than judge completeness by eye.

---

## 14. Scaffold a Config-Editing Plan for a Permission Round-Trip

When a plan's deliverable includes editing `.claude/rules/**`, `.claude/agents/**`, `.claude/skills/**`, `.claude/commands/**`, or `.claude/settings*.json`, the harness permission classifier gates those writes **independently of planwise authorization**. A task brief, Sprint Plan, and Master Plan that all name the file as the deliverable do **not** pre-clear it, and the classifier's decisions within a single batch are **not deterministic**.

This is a scaffolding obligation, not an execution surprise. Such a plan is predictably going to pause; scaffold it so pausing is cheap rather than destructive.

| # | Obligation | Why |
|---|---|---|
| 1 | **Declare the round-trip in the Orchestration.** Treat it the way a DB-touching task treats a connectivity precheck — a known, planned interruption. | A pause the plan predicted is an interrupt; a pause it did not is a BLOCKED cycle. |
| 2 | **Keep each edit batch to the smallest coherent set.** Do not dispatch many edits to one config file expecting all-or-nothing. | Denials are per-call, so a large batch half-applies and leaves the file internally inconsistent. |
| 3 | **Record applied-vs-denied state in Recovery immediately on any denial.** | The file can then be completed or reverted deterministically instead of re-derived from a half-remembered batch. |
| 4 | **On denial, STOP and ask — never retry verbatim.** Surface the precise file and the exact remaining edit list. | A verbatim retry in the same mode re-denies, burning a round-trip and adding nothing. |
| 5 | **Scope the brief to the minimum required sections.** | Out-of-brief "consistency nicety" edits inflate the edit count against the classifier, and can be the one edit that hits an unclearable block — losing nothing essential while adding interrupts. |

Some denials cannot be cleared by user authorization at all. The plan must be able to record such an edit as a known, non-blocking residual and continue, rather than treating the session as failed.

> [!constraint] Do Not Scaffold a Rule-Editing Task as an Ordinary File Edit
> WRONG:
> ```
> Task 03: edit {rule-file-A} + {rule-file-B}   (no round-trip declared)
> → 16 Edit calls dispatched; the classifier denies 3 of them
> → both files half-flipped and internally inconsistent; session blocked;
>   no recorded partial state, so the next attempt cannot tell applied from pending
> ```
> CORRECT:
> ```
> Orchestration declares the expected permission prompt for Task 03
> → dispatch brief-scoped edits only, smallest coherent batch
> → on first denial: write the applied-vs-denied list to Recovery, STOP, ask the user
> → after the grant: apply the remainder; record any unclearable residual as a
>   known, non-blocking follow-up
> ```

Note that this applies **in every operating configuration** — the classifier is the gate regardless of mode, so Auto Mode does not bypass it.

Planwise-level self-modification authorization does not pre-clear this harness-level gate: [session-execution-protocol.md](session-execution-protocol.md#claude-self-modification-authorization) §3 (Claude Self-Modification Authorization) authorizes Claude to add Bash permissions to `.claude/settings.json` at the planwise/workflow level, but that authorization is independent of the permission classifier described above (`agent-orchestration.md` constraints table row 12, self-modification writes) — satisfying one does not satisfy the other, and a reader who knows only §3 needs this pointer.

---

## 15. First Task of Each Sprint Records the Diff Baseline

A sprint's verification gates are only as trustworthy as the tree state they name, and a gate written as `git diff $..._BASE -- <paths>` is unfalsifiable if no task in the sprint was ever given the job of recording that base. The unset name expands to nothing, the command degrades into a bare whole-tree `diff`, and it still runs, still prints, and still reads as green or red — so the failure is invisible at exactly the moment the report is written. Scaffolding is where that gap is closed: the obligation to pin a baseline is assigned to a task at scaffold time or it does not exist at all.

> [!constraint] Every sprint carries a baseline-recording obligation, assigned to a task at scaffold time
> **Who.** The first task in the sprint that **touches the target repo** records the baseline — identified by **write-set, not by task number**. The first *numbered* task is routinely a read-only survey, inventory, or discovery pass; the first *touching* task is the one whose Output names a file in that repo. Assign the obligation to that task and state in its brief why it holds it, so a later re-ordering of the task list does not silently move the pin off the front.
>
> **Precondition.** Before pinning, the sprint's own write scope MUST be clean:
> ```bash
> git -C <repo> status --porcelain -- <this sprint's write paths>
> # MUST be empty. Non-empty → HALT. Not a warning — a halt.
> ```
> Uncommitted work inside the sprint's own write-set makes every later gate unfalsifiable in both directions: the base already contains changes this sprint did not make, so a scope gate fails the sprint for someone else's edits, while a self-containment sweep either blames it for a token it never wrote or credits its own leak elsewhere. Scope the precondition with `--` to the sprint's write paths rather than the whole repo — unrelated dirt outside the sprint's area is not this sprint's to stash, and a whole-repo cleanliness demand is the kind of gate sessions learn to override.
>
> **What.**
> ```bash
> {ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)
> ```
>
> **Where.** The session Recovery file's Key Findings, as that task's **first** Recovery write — before any file edit, so a compaction or a crash mid-task does not lose the pin. Record the name, the value, and which task recorded it. Every later task in the sprint then **reads the value from Recovery** instead of re-deriving it: a `rev-parse HEAD` taken after the first edit is not the baseline, and a gate scoped to it is blind to every change made before it ran.
>
> **Series base.** A multi-sprint plan additionally records `{ABBREV}_SERIES_BASE` at the first task of the first sprint, for the release / whole-series battery that needs one base predating every sprint. **First-to-touch contingency:** a sprint that may not run first — any sprint the plan's ordering declares INDEPENDENT — MUST check the plan's Recovery files for an already-recorded series base before minting one, and **adopt that value verbatim** if it finds one. Only when none exists does its own HEAD become the series base.

> [!constraint] Scaffold the pin onto a task, or the sprint's gates measure the wrong tree
> WRONG — the sprint's gates all name a base, but the scaffold assigned the pin to nobody; and where a task does pin, it pins after it has already started editing:
> ```
> {Abbrev}-S{XX}-01   Output: <file A>
>   Step 1: edit <file A>   …   Step 5: {ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)
> {Abbrev}-S{XX}-02   Verification: git -C <repo> diff $..._BASE -- <paths> | …   # nothing ever recorded this name
> ```
> Task 02's gate expands to a whole-tree `diff` and reports every uncommitted file in the repo as this sprint's. Task 01's late pin does not rescue it either: a base taken after its own edit already contains that edit, so a gate scoped to it is blind to the one change it was written to check and reports empty for the reason that makes empty worthless.
>
> CORRECT — the pin is step 1 of the first task whose write-set touches the repo, behind the clean-scope HALT, written to Recovery before any edit:
> ```
> {Abbrev}-S{XX}-01   Output: <file A>
>   Step 1: git -C <repo> status --porcelain -- <this sprint's write paths>   # MUST be empty, else HALT
>           {ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)
>           → Recovery Key Findings, as the session's FIRST Recovery write
>           (first sprint of a series: also check the plan's Recovery files for
>            {ABBREV}_SERIES_BASE and adopt it verbatim, else record it here too)
>   Step 2: edit <file A>
> {Abbrev}-S{XX}-02   Step 1: read {ABBREV}_S{NN}_BASE from Recovery — do not re-derive
> ```

This section owns **who** records a baseline, **when**, and **where** it lives; what a gate must then look like once a base exists — the `--` path scoping, the positive allow-list form of a scope test, and the five sub-rules governing each gate shape — belongs to [verification-gates.md](verification-gates.md#8-diff-scoped-gates-pin-a-recorded-baseline) §8, the definition site for `$..._BASE`. Its §8.1 and §8.4 state the pin mechanics and the series-base contingency from the *gate's* side; the scaffolding obligation above is what makes them satisfiable, and neither restates the other. Read §8 before authoring any diff-scoped gate.

---

## 16. Declared Parallelism Requires a Computed Write-Set Intersection

A `∥` in a Master Plan's ordering is not a scheduling preference — it is a claim that two sprints never write the same file. The claim is about file sets, so only a file-set operation can support it, and a sprint's *name* is not evidence of one. "Agents vs handlers, disjoint files" describes two clusters; a cluster is not a write-set, and the distance between the two is exactly where concurrent sessions overwrite each other. This section makes the intersection an artifact the plan has to **show**, so that a parallel declaration is either computed or absent — never inferred, and never asserted behind a marker that cannot fail.

> [!constraint] A declared-parallel pair is unsupported until its write-sets are intersected and the result is shown
> **16.1 — Every sprint declares a write-set.** Each Sprint Plan carries a `## Write-Set` section listing every directory or file the sprint **EDITS** — not the ones it merely reads — as a `| Path | Task |` table naming the task that writes each path. The read/edit distinction is the whole point: nearly every sprint reads broadly while only a handful of paths are ever written to, so an intersection computed over read-sets is meaningless. The `## Write-Set` declaration is distinct from a sequential Cross-Sprint File-Touch declaration, which compares this sprint against a *prior* sprint's already-landed delta; the write-set is the declaration an intersection is computed **from**, independent of landing order.
>
> **16.2 — Every declared-parallel pair states its computed intersection, with the result shown.** The Master Plan's `## Execution Ordering` section carries the declared-ordering line, a `### Write-Sets` table (`| Sprint | Write-set |`) collected from each Sprint Plan's own declaration, and a `### Computed Write-Set Intersection` table (`| Declared pair | Intersection | Verdict |`) with one row per `∥` pair. `∅` means the parallelism stands as declared. A non-empty intersection permits exactly two dispositions: (1) **serialize the pair, dropping `∥`**; or (2) **qualify the parallelism per-file, naming an explicit task-level ordering edge for each shared file (`S0A-01-0x → S0B-01-0y`)**. "We looked and it seemed fine" is neither disposition: an unshown result is an assertion wearing a computation's clothes, which is the precise shape that survives review. **Recompute the matrix whenever any sprint's write-set changes** — a mid-plan coordination flag that admits one new file into a sprint's scope can turn a `∅` row false, and the row does not re-derive itself.
>
> **16.3 — A file appearing under two sprints declared `∥` is a BLOCKER-grade contradiction.** When a plan's own file-touch or write-set tables list the same path under two sprints the ordering line joins with `∥`, the plan contradicts itself in writing. That is caught **mechanically**, by the structural reviewer, not by a reviewer happening to notice — the two statements typically sit sections apart, and the whole failure mode is that nobody reads them against each other.
>
> **16.4 — A gate marker may not be an assumption.** A marker reading `n/a — single-writer per sprint` is not a gate; it is an assertion with no check behind it, and it reports the same result whether or not the property it names holds. A gate marker must be a **runnable command whose failure is possible** against the pre-edit tree — for a write-set concern, typically a baseline-pinned, path-scoped diff whose output must never name the parallel sprint's files (`git -C <repo> diff --name-only $..._BASE -- {dir}/`). Before trusting any marker, confirm it can return the failing result at all: a check that cannot fail is not evidence, it is decoration.
>
> **16.5 — Cross-sprint coordination flags must be reciprocal.** If sprint A raises a flag about a file sprint B also writes, B's flag chain names A and vice versa. Without the return edge each sprint measures a **shared** threshold — a file-size gate, a line budget — against its own contribution alone, and against a baseline the other sprint has already moved. Both sprints then pass a limit their combined delta breaks, and each one's arithmetic is locally correct.

> [!constraint] Compute the intersection, or the `∥` is an unbacked claim
> WRONG — the parallelism inferred from cluster names, while the plan's own tables say otherwise:
> ```
> **Declared ordering:** `{ S0A ∥ S0B }`   ← marked *binding*
>   rationale: "agents vs handlers — disjoint files"
>
> Cross-Sprint File-Touch Matrix (same plan, further down):
>   `{path/to/shared-a.ext}`   touched by S0A, S0B
>   `{path/to/shared-b.ext}`   touched by S0A, S0B
> ```
> Nothing reconciles the two, because nothing ever intersected the write-sets. Run concurrently, two sessions append to the same two files with no lock. The sharpest detail is where the inference came from: the very document whose own resolution invalidated it — an upstream refactor map decided on a **per-source fold into a shared directory**, then a few sections later called the two sprints disjoint. The fold is what created the overlap; the disjointness claim was authored downstream of the decision that broke it and never re-derived.
>
> WRONG — the assumption-shaped gate marker:
> ```
> | `{shared/dir}/` | S0A → S0B → S0C | n/a (single-writer per sprint) |
> ```
> The directory is written by three sprints, two of them declared `∥`. The marker asserts the property the table itself disproves, and it was benign only by accident: the file lists happened not to overlap. A marker that would have read identically had they overlapped is not a gate.
>
> CORRECT — declared per sprint, intersected, the result shown per pair, and the non-empty pair disposed of explicitly:
> ```
> ### Write-Sets
> | Sprint | Write-set |
> | {Sprint-N} (A) | `{dir-one}/`, `{path/to/shared-a.ext}`, `{path/to/shared-b.ext}` |
> | {Sprint-N} (B) | `{dir-two}/`, `{path/to/shared-a.ext}`, `{path/to/shared-b.ext}` |
>
> ### Computed Write-Set Intersection
> | Declared pair | Intersection | Verdict |
> | S0A ∥ S0B | `{path/to/shared-a.ext}`, `{path/to/shared-b.ext}` | ❌ NOT disjoint — qualified per-file: `S0A-01-0x → S0B-01-0y`, `S0A-01-0z → S0B-01-0y` |
> | S0A ∥ S0C | ∅ | ✅ disjoint — parallel stands |
>
> gate marker: `git -C <repo> diff --name-only $..._BASE -- {shared/dir}/`
>                must never name the other sprint's files (pre-edit: empty)
> ```
> The `∅` row is as much a computation as the `❌` row — it is shown, dated, and recomputed when a write-set changes, not left implicit because the answer was expected.

§8 (Parallel-Scaffold Deviation Classes) and this section address different failures of the same scaffolding shape and neither substitutes for the other: §8 governs the **consistency** of the files parallel scaffolders produce — whether they look alike — while §16 governs the **correctness** of the parallel declaration itself, whether the sprints may run at once at all. A plan can pass §8 with perfectly uniform files and still be wrong here.

The mechanical enforcement of 16.3 is Check S05 in `agents/structural-reviewer.md`, which detects the file-under-two-parallel-sprints contradiction during the structural pass. This section owns **what** must be declared, computed, and shown; that check owns the detection procedure, and neither restates the other.

#### Reviewer Check 078 — Declared Parallelism Without a Computed Intersection

- **Severity / Role:** BLOCKER | Scaffolding Hygiene Reviewer | NEW
- **What:** A Master Plan declaring any sprint pair parallel without a computed write-set intersection shown for that pair; or a sprint named on the ordering line with no declared write-set; or a gate marker that is an assertion rather than a runnable command.
- **Detection:** Read the Master Plan's `## Execution Ordering` section. For each `∥` pair on the declared-ordering line, assert a matching row exists in the `### Computed Write-Set Intersection` table carrying a shown result (`∅` or the named paths) and a Verdict; assert every sprint named on that line has a `## Write-Set` section in its own Sprint Plan; then Grep the Verdict and gate-marker cells for assertion-shaped text (`n/a`, `single-writer`, `assumed`, `should be`) with no command behind it. Any one → BLOCKER.
- **Finding template:** `[BLOCKER] Declared-parallel pair {S0A ∥ S0B} has no computed write-set intersection | File: {Master Plan} | Fix per references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md §16 | Confidence: HIGH`

## 17. A Dispatch Layer Declares a Computed Write-Target Intersection

§16 governs parallelism between **sprints**, computed from Sprint-Plan write-sets. This section governs parallelism between **tasks inside one session** — the dispatch layer, written in an Orchestration as `L2 = {2, 3} (disjoint target files)`. Same failure, different granularity, and neither substitutes for the other: a plan can pass §16 with genuinely disjoint sprints and still ship a session whose own layer members write one file.

The evidence is already in the plan. Every task file carries an `**Output:**` line naming what it writes. Nothing intersects them.

### 17.1 Compute the intersection from the Output lines, at scaffold close

For each declared layer, collect every member task's `**Output:**` paths and intersect them pairwise. A non-empty intersection fails the layer. The check needs no judgment and runs against artifacts the scaffold has already produced.

> [!constraint] "Disjoint target files" is a claim, and a claim needs its computation shown
> An annotation asserting disjointness without the computed result is an assertion wearing a computation's clothes. It reads identically whether the property holds or not, which is exactly why it survives review.
>
> WRONG — the annotation asserts what the layer's own two Output lines contradict:
> ```
> Dispatch layers: L2 = {2, 3} (disjoint target files)
>
> Task 02  **Output:** in-place edits to `{handler-a}` — three spawn blocks
> Task 03  **Output:** in-place edits to `{handler-b}`, `{handler-c}`, `{handler-a}`, `{handler-d}`
>                                                        ^^^^^^^^^^^ also Task 02's target
> ```
> Two runners write `{handler-a}` concurrently. Lost-update risk on a shipped file — and Task 02's success criterion *"every existing block byte-untouched"* is unassertable against a file a sibling is writing.
>
> CORRECT — the layer carries the computed result, and the overlapping pair names its disposition:
> ```
> ### Computed Write-Target Intersection
> | Layer | Members | Intersection | Verdict |
> | L1 | {1, 4, 5, 7} | ∅ | ✅ disjoint — parallel stands |
> | L2 | {2, 3} | `{handler-a}` | ❌ NOT disjoint — serialized: 3 after 2 on `{handler-a}` |
> ```
> The `∅` row is as much a computation as the `❌` row. Show it; do not leave it implicit because the answer was expected.

A layer with a non-empty intersection has the four dispositions [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.13 already defines — serialize the pair, shard the target, route deltas to a single writer, or cap parallelism with genuinely disjoint regions inside the file. Name the choice. A bare "disjoint target files" is not one of them.

### 17.2 The shared object may be a counter, not a file

Two tasks can hold genuinely disjoint `**Output:**` paths and still collide, when what they share is an **allocation** rather than a path: the next free reviewer-check number, the next free catalog row, the next free section number. Both runners read the same live maximum, both compute the same next value, and both write it — into *different* files, so a path intersection returns `∅` and the layer passes.

Treat a next-free-identifier allocation as a write target of its own. Either the orchestrator resolves each runner's number **before** dispatch and injects it as a literal, or the allocating tasks serialize. Pre-resolution is preferred: it costs nothing extra and it is the discipline [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.6 already applies to every shared pin.

### 17.3 A per-task gate is scoped to that task's own outputs

A gate that counts changed files across the whole working tree, asserted by a task that edited some of them, false-fails inside a parallel layer. The tree accumulates every layer member's edits with no commit between dispatches, so by the third task the repo-wide count reports three files where the task asserts one — and inside a parallel layer the reading depends on completion order, so the failure is non-deterministic.

Non-determinism is what makes this expensive. An order-dependent gate reads as flakiness rather than as a defect, and runners learn to route around it. A gate routed around is indistinguishable from a gate never written, so any gate whose meaning depends on it becomes vacuous too.

> [!constraint] Scope a per-task count to the paths that task declares
> WRONG — repo-wide count, asserted by a task that edited one file:
> ```
> {vcs} diff --name-only {shared/dir}/ | wc -l   # MUST equal edited-file count
> ```
> CORRECT — scoped to this task's own declared Output paths:
> ```
> {vcs} diff --name-only -- {this task's declared output paths} | wc -l   # 1
> ```
> Keep the repo-wide form for a **session-closing sweep task**, where the whole-session delta genuinely is the subject. The two answer different questions; do not collapse one into the other.

The scaffold emits the scoped form into every per-task gate, so the next plan inherits the correct shape rather than copying a repo-wide snippet out of a project-level document.

#### Reviewer Check 083 — Dispatch Layer Without a Computed Write-Target Intersection

- **Severity / Role:** BLOCKER | Scaffolding Hygiene Reviewer | NEW
- **What:** An Orchestration declaring a multi-member dispatch layer without a computed write-target intersection shown for that layer; or a layer annotated "disjoint" whose member task `**Output:**` lines in fact overlap; or a per-task count gate scoped repo-wide inside a parallel layer.
- **Detection:** For each Orchestration, read the declared dispatch layers. For every layer with 2+ members, collect each member task file's `**Output:**` paths and intersect them pairwise. Assert a `Computed Write-Target Intersection` row exists for that layer carrying a shown result (`∅` or the named paths) plus a Verdict, and that the computed result matches the shown one. Then Grep each member's gate commands for a tree-wide count with no path scoping. Any one → BLOCKER.
- **Finding template:** `[BLOCKER] Dispatch layer {L2 = {2,3}} declared disjoint but write-targets intersect at {path} | File: {Orchestration path} | Fix per references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md §17 | Confidence: HIGH`

---

*Five binding hygiene rules for what a multi-sprint scaffold must compute before it closes — Part 2 of 2. Sections §1–§12, the rules governing what the scaffold emits, live in [scaffolding-hygiene.md](scaffolding-hygiene.md). Cross-referenced from the Companion Files and Extracted Protocols table in [session-planning-protocol.md](session-planning-protocol.md#companion-files-and-extracted-protocols).*
