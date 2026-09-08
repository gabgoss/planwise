---
description: The Grep is the enumeration — a brief that changes a value bound to many sites instructs a sweep, not a patch, and the half a structure map misses is the half that fails quietly. Covers site-named versus sweep-framed briefs, the zero-site defect, metadata surfaces, spelled-out counts, renumbering at every heading level plus the in-prose pointers, the renumbering gate's true expected count, operative sites versus prose sites when applying an upstream change in place, and why a half-applied edit is worse than a notice. Consult while writing a brief that changes a count, a section number, a selector or an enum member, while renumbering, and while reading a flag that says an upstream change was applied.
paths: {planwise_root}/{plans_dir}/**
---
# Edit Surface Sweep — The Grep Is the Enumeration: Instruct a Sweep, Not a Patch

**Purpose:** An edit brief that changes a value bound to many sites — a count, a section number, an enum member — is written by an author who maps the artifact the way they *think* about it. A count is thought of as living in one sentence; a section number as living in a heading; a partition key as living in the criterion that names it. In every case the artifact carried more referents than the mental model did, and the brief bounded the runner's search set to the ones the author happened to see.

**Read this when** you are writing a brief that changes a count, a section number, a selector or an enum member; when you are renumbering headings; when you are applying an upstream change in place; and when you are reading a flag that asserts such an edit was applied.

The two halves of such a surface are not equally visible, and **the invisible half is the one that fails quietly.** A stale *heading* is self-announcing — a reader sees `## 5.` above `### 4.A` and knows something is wrong. A stale *pointer* reads as a perfectly ordinary instruction and lands nowhere, or worse, on a renumbered section that now means something else. A partially applied edit is worse still: the file reads as updated, which invites nobody to check it.

Recurrence is high and measured. One session carried the same class in three separate files, and in **every** case the authoring brief named fewer sites than the artifact had. The precision of a site-named instruction is what makes it dangerous: it carries a line number, which reads as evidence someone measured — but what was measured is where the value *is*, not where it *isn't*.

Three neighbouring rules own machinery this file builds on. [`scaffolding-hygiene.md`](scaffolding-hygiene.md) §12.4 owns the whole-document count sweep keyed on claim shape, and [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §13.4 owns the four-pass roster-change sweep, including the spelled-out register; this file is about the *brief* that fails to instruct such a sweep, and about the referents no count sweep reaches. [`verification-gate-evidence.md`](verification-gate-evidence.md) §3 owns the correct-post-state arm of any gate; §6 below is its renumbering-specific form. [`measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md`](measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md) §8.8 sub-rules A and D own "update the field, not the prose beside it"; §7 below is that rule applied to a task file's own steps and gates.

## Table of Contents

- [1. Instruct a Sweep, Not a Patch](#1-instruct-a-sweep-not-a-patch)
- [2. A Brief That Names ZERO Sites Is a Distinct Defect From One That Names Too Few](#2-a-brief-that-names-zero-sites-is-a-distinct-defect-from-one-that-names-too-few)
- [3. The Value Lives in Metadata Surfaces, Not Only in Body Prose](#3-the-value-lives-in-metadata-surfaces-not-only-in-body-prose)
- [4. The Locator Must Cover Both Registers, and Spelled-Out Counts May Need a Taxonomy](#4-the-locator-must-cover-both-registers-and-spelled-out-counts-may-need-a-taxonomy)
- [5. Numbering Is a Naming Scheme With Unbounded Referents — Map Every Level, Then Hunt the Pointers](#5-numbering-is-a-naming-scheme-with-unbounded-referents--map-every-level-then-hunt-the-pointers)
- [6. A Renumbering Gate Almost Never Expects Zero — Write the Expected Count and What Each Deviation Means](#6-a-renumbering-gate-almost-never-expects-zero--write-the-expected-count-and-what-each-deviation-means)
- [7. When Applying an Upstream Change in Place, Enumerate the Operative Sites — Not the Prose Sites](#7-when-applying-an-upstream-change-in-place-enumerate-the-operative-sites--not-the-prose-sites)
- [8. A Half-Applied Edit Is Worse Than a Notice, and the Receiver Re-Derives the Claim](#8-a-half-applied-edit-is-worse-than-a-notice-and-the-receiver-re-derives-the-claim)
- [9. A Sweep and a Diff-Shape Gate Collide by Construction — Say So in the Brief](#9-a-sweep-and-a-diff-shape-gate-collide-by-construction--say-so-in-the-brief)

---

## 1. Instruct a Sweep, Not a Patch

> [!constraint] Name the quantity, hand over the locator, make coverage the runner's job
> | Framing | What the runner does | Fails when |
> |---|---|---|
> | **Site-named** — "update the count at `:168`" | Edits exactly that line | The value appears anywhere else |
> | **Sweep-framed** — "sweep the file for every occurrence and re-derive each" | Searches, then edits every hit | Never, for that file |
>
> ```
> WRONG — names a site, so the runner's search set is a set of one, and its
> completeness was never established:
>   The intro sentence at :168 reads "all 11 checks" — update it to 12.
>
> CORRECT — names the QUANTITY, hands over the locator, and makes coverage
> the runner's job:
>   Re-derive every occurrence of this table's row count in this file.
>   Locate with: Grep  pattern='(all|for) [0-9]+ checks|[0-9]+-row'  path=<file>  output_mode='content'  -n=true
>   Report the number of occurrences found and corrected.
> ```

A task appending a 12th row was told to fix the section intro at `:168` reading *"…all **11** checks"*. The runner did that **and swept the file anyway**, finding the identical stale count in a frontmatter `Purpose:` line at `:7`. Obeyed literally, the brief would have shipped the same self-contradiction **one line higher in the same file** — relocating the defect rather than removing it. The orchestrator's own preflight search had surfaced line 7 as a match and it went uninspected: *the instruction was written from a partial read of the very output that contained the answer.*

Two supporting statements. **Precision about location substitutes for completeness of coverage** — the site-named framing is seductive because it is *more specific*, and specificity usually helps a brief. And **requiring the runner to report the occurrence count is what closes the loop**: a "1 found, 1 corrected" is auditable, where a silent single edit is indistinguishable from a missed second site.

---

## 2. A Brief That Names ZERO Sites Is a Distinct Defect From One That Names Too Few

> [!constraint] Only a preflight question about the artifact surfaces the zero-site shape
> The site-named shape has a wrong instruction to review; the zero-site shape has none. A catalog-append brief carried no count-maintenance clause at all while the file's frontmatter read *"the **95-row** quick-reference table"* — correct at the time, stale the instant ten rows appended. Prior sprints had maintained that line through two appends, so the omission was a regression against landed precedent, not an inherited default.

The preflight question is: *what in this file describes the thing this brief changes?* A brief that cannot answer it has not been checked against the artifact, however precise its edit instructions are.

---

## 3. The Value Lives in Metadata Surfaces, Not Only in Body Prose

> [!constraint] A sweep scoped to the section that owns the table finds only the intro
> Sites found across one session: a frontmatter `description:` line, a `**Purpose:**` paragraph, a section intro, and a closing italic footer. The frontmatter is the worst of these — it is the file's own advertised self-description, it renders in rule-injection contexts, and it sits above every heading a body-scoped reader looks at.

[`scaffolding-hygiene.md`](scaffolding-hygiene.md) §12.4 carries the whole-document rule — key the sweep on the claim's shape, reconcile every hit against the measured value, and the two shapes that escape a digit-plus-noun pattern. This section adds the *sites* a body-scoped reader never opens: the metadata above the first heading and the footer below the last.

---

## 4. The Locator Must Cover Both Registers, and Spelled-Out Counts May Need a Taxonomy

> [!constraint] This is where an earlier version of this rule's own locator failed
> Three spelled-out sites survived both a preflight and a prior sprint's sweep of the same class:
>
> ```
> description: Ten binding hygiene rules plus three advisory practices …
> **Purpose:** Enforce seven mechanical hygiene rules — and apply three advisory …
> *Ten binding hygiene rules plus three advisory practices for multi-sprint plan scaffolding.*
> ```
>
> A numeral-only locator — the `(all|for) [0-9]+ checks|[0-9]+-row` pattern §1 hands over — **cannot match any of them**, which is how all three survived. Two of them had already drifted out of agreement with each other before either sprint touched the file (`seven mechanical` + 3 advisory = 10 versus `Ten binding` + 3 = 13) — which is what a count nobody can search for looks like after enough appends. The widened pair:
>
> ```
> Grep  pattern='[0-9]+-row|[0-9]+ rows|(all|for) [0-9]+ (checks|rules|sections)'  path=<file>  output_mode='content'  -n=true  -i=true
> Grep  pattern='\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty)\b [a-z-]*(rule|section|check|practice|item)'  path=<file>  output_mode='content'  -n=true  -i=true
> ```

This is stated as a failure of the earlier prescription, not presented as a complete recipe. A rule that silently ships the widened locator teaches nothing about why the narrow one survived two sweeps. The shipped sweeps in [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §13.4 already run both registers as separate passes; a brief that hands over only the numeral pass has re-narrowed them.

**The taxonomy caveat.** Bumping `Ten binding … three advisory` required first establishing which sections are binding and which advisory — recoverable there only because pre-edit `10 + 3 = 13` matched the live section count exactly, confirming advisory = §8–§10 and binding = the rest, so a new §14 gave `11 + 3 = 14`. **Do that derivation at preflight and hand the runner the resolved numbers**; a runner asked to re-derive a count *and* infer a classification scheme mid-append will reasonably decline or guess.

---

## 5. Numbering Is a Naming Scheme With Unbounded Referents — Map Every Level, Then Hunt the Pointers

> [!constraint] The half a structure map misses is the half that fails quietly
> A brief prescribed *"Renumber OUTPUT→`## 4.` and RECOVERY→`## 5.`; fix any internal cross-references the step-2 search found."* Step 2's structure map was a search for `^## ` — top-level headings only. It returned eight and the brief enumerated all eight. The artifact had four more numbering sites bound to those headings:
>
> | Site | Kind | Visible to `^## `? |
> |---|---|---|
> | `### 4.A Sequential Dispatch` | nested sub-heading | no |
> | `### 4.B Parallel Dispatch` | nested sub-heading | no |
> | `Follow §4.A below — incremental Recovery writes` | in-prose citation, table cell | no |
> | `Follow §4.B below — return a status block` | in-prose citation, table cell | no |
>
> Executed literally, the task ships `## 5. RECOVERY` containing `### 4.A`/`### 4.B` children **and two cross-references pointing at section numbers that no longer exist.**
>
> ```
> WRONG — maps one heading level, so the search set silently excludes
> sub-headings and every in-prose citation:
>   Grep  pattern='^## '  path=<file>                              # 8 headings
>   → "Renumber OUTPUT→## 4. and RECOVERY→## 5."
>
> CORRECT — map every heading level, then separately hunt the referents:
>   Grep  pattern='^#+ '  path=<file>                              # ALL heading levels
>   Grep  pattern='§[0-9]+(\.[0-9A-Z]+)*|section [0-9]'  path=<file>   # in-prose citations
>   → enumerate every site found, at every level, in the instruction
> ```

The failure shape is that the author maps the artifact as a list of sections, and a section list is exactly what a `^## ` search returns, so **the map confirms the mental model instead of testing it.** The visibility asymmetry is the reason this matters: a stale heading announces itself, a stale pointer reads as an ordinary instruction and lands nowhere. The preflight caught the sub-headings by widening the map one level; it did **not** catch the two prose citations, which surfaced only at land time via a content search for `§4.A`/`§4.B`.

The verified payoff: the runner renumbered all six sites, final state `### 5.A`/`### 5.B` with zero `### 4.` remaining and both table cells citing `§5.A`/`§5.B`; the whole-file diff was **42 insertions / 6 deletions**, all six deletions classifying as numbering lines — which is what proves the renumbering touched only numbering and left both section bodies byte-unchanged.

---

## 6. A Renumbering Gate Almost Never Expects Zero — Write the Expected Count and What Each Deviation Means

> [!constraint] Renumbering creates the numbers it searches for
> The brief's After gate was `grep -nE '## [34]\.'`, annotated *"no stale references to the old numbering in prose"*. On a **correct** post-state that returns **2** — the legitimate `## 3.` and `## 4.` headings that now exist. Read as must-be-zero it false-fails correct work into retry ×3 → BLOCKED.
>
> | Result | Meaning |
> |---|---|
> | 2 | correct — the two legitimate headings |
> | 4 | the `### 4.x` sub-headings were left un-renumbered |
> | other | a genuine stale prose reference |
>
> Restated with its true expected value the same command becomes a detector rather than a hazard, because `## 4\.` also matches *inside* `### 4.A`.

Write the full table, not only the expected value. A rule that only says "expected value is 2" teaches a reader to memorise a number rather than to write what each deviation means. The general obligation — build the correct post-state by hand and run the gate against it before annotating an expected value — is [`verification-gate-evidence.md`](verification-gate-evidence.md) §3; [`verification-task-authoring.md`](verification-task-authoring.md) §10.7 requires the anchor to accept exactly the outcome set its own task can produce.

---

## 7. When Applying an Upstream Change in Place, Enumerate the Operative Sites — Not the Prose Sites

> [!constraint] Prose describes intent; steps, searches, gates and projections ARE the behavior
> A brief-owner decision added a sixth value, `interactive`, to a Modality enum partitioning 200 claims across parallel design tasks, and three claims were re-stamped out of `headless`. The settling session applied it in place — correctly — and enumerated what it had touched: *"updated at its objective, its claim-selection criterion, and all four Scope-string sites including its acceptance grep."* What had actually been updated was the objective prose, a new binding callout, and the four Scope strings. What had **not**:
>
> - Execution Step 2's claim-pull procedure, still reading `Grep '\*\*Modality:\*\* observational'` — one modality
> - The Required Context row describing the same pull
> - Both claim-pull dry-run gates, testing only the `observational` spelling
> - The population projection ("~12 expected" against a true 19)
>
> So the file held a binding callout saying *"your pull MUST select on both stamps"* and an Execution Step saying, in the imperative and with a copy-pasteable search, to select on one. A runner following the steps returns 16, silently drops three claims, and the failure surfaces two tasks downstream as a cross-count of `197 ≠ 200` — with no indication which three are missing.
>
> ```
> WRONG — update where the change is described, and report that as done:
>   Objective paragraph      → updated ✓
>   Binding callout added    → ✓
>   Scope strings (×4)       → updated ✓
>   Report: "updated at its objective, its claim-selection criterion,
>            and all four Scope sites"
>   # Execution Step 2's search, the Required Context row, both dry-run gates
>   # and the projected count still encode the OLD partition.
>   # The file now reads as current.
>
> CORRECT — enumerate by site class, then search for the stale token:
>   For the changed key, search the whole file for EVERY occurrence of the old value:
>     Grep  pattern='observational'  path=<task-file>  output_mode='content'  -n=true
>   → objective, callout, Execution Step 2, Required Context row,
>     2 dry-run gates, After gate
>   Update all of them, then re-run the search: any surviving bare occurrence must be
>   deliberate (e.g. naming the old value as one of two) and justified in place.
> ```

Three sub-rules:

- **The Grep is the enumeration.** Do not enumerate sites from memory or from the document's structure — search for the old value and treat every hit as in scope until individually cleared. That single search would have found all four missed sites.
- **A change to a partition key is a change to every gate that tests the key.** Selection criteria, dry-run fixtures, acceptance gates and projected counts all encode the partition; updating the selection while leaving the gate on the old spelling produces a gate that passes vacuously on wrong work.
- **Report which sites were touched in a form the receiver can check** — a list of line numbers or search output, not a prose category like "the claim-selection criterion". A category name cannot be falsified by the reader; a line list can.

---

## 8. A Half-Applied Edit Is Worse Than a Notice, and the Receiver Re-Derives the Claim

> [!constraint] A file that reads as updated invites nobody to check it
> A notice-only flag would have been read as *work outstanding* and routed at the receiving preflight. **A half-applied edit is worse than a notice**, and a confident enumeration actively discourages re-verification. So: a flag asserting an in-place edit is a claim about a file you can read — re-derive it with one `Grep` for the old value before trusting that the file matches its own description.

The §7 assertion was specific, confident, and still incomplete; only re-reading the Execution Steps against the callout exposed the contradiction. A reader who trims this section to "apply changes in place" retains exactly the behaviour that caused the incident.

---

## 9. A Sweep and a Diff-Shape Gate Collide by Construction — Say So in the Brief

> [!practice] Any file whose counts live outside the appended region will produce deletions during a sweep
> In the §4 session the runner found all three sites, surfaced them correctly, and then **declined to fix them**, to keep its diff's `^-` count at the value its brief predicted. A gate annotation predicts the shape of correct work and never constrains it. An append brief that instructs a sweep must also state that the sweep's deletions are expected.

§6 and §9 both concern a gate that misreads correct work and are separated deliberately: §6's gate has a *wrong expected value* and is fixed by writing the right one; §9's gate has a *correct prediction* that the runner mistook for a constraint, and is fixed by saying so in the annotation. Merging them produces "check your gates", which prescribes neither fix. The runner who withholds a correct fix to protect a predicted diff count needs the statement where it is reading — inside the sweep instruction — not only in the gate rule.

---

*Cross-reference: [`scaffolding-hygiene.md`](scaffolding-hygiene.md) §12.4 (whole-document count sweep keyed on claim shape) · [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §13.4 (the four-pass roster-change sweep, both registers) · [`verification-gate-evidence.md`](verification-gate-evidence.md) §3 (the correct-post-state arm) · [`verification-task-authoring.md`](verification-task-authoring.md) §10.7 · [`measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md`](measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md) §8.8 A, D · [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §5 (a flag the sender says it delivered is a claim — the same re-derive-at-the-receiver rule for arrival rather than content)*
