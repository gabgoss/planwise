---
description: An anchor accepts exactly the outcome set its own task's Execution Steps can produce — set equality derived at scaffold close, with the branch count carried inline, and never hardened into a count equality (§10.7, Reviewer Check 095); and a re-capture gate over a directory a tool regenerates in place names the environment-attributable files (fetched, session, timing, cost) apart from the extractor-attributable ones, so only the remainder halts (§10.10); and a task that discharges a sprint criterion quotes it and names a gate that measures the criterion's own property, with sibling criteria reconciled against one real artifact (§10.11, Reviewer Check 112); and an anchor names the phase that produces its subject so a closeout-phase anchor is marked post-verdict, and a stale anchor pattern is widened while a committed artifact of record is never edited to fit it (§10.7.1-§10.7.2, Reviewer Check 095). A criterion that matches an internal table against an external listing names all four cells, and the present-but-unlisted cell is a PARTIAL verdict (§10.12, Reviewer Check 119).
consult-when: Writing a Signoff anchor, exit criterion, Execution Input gate, or a `git diff --stat` allowed set over a regenerated directory — the anchor accepts exactly the task's terminal branches (§10.7, Check 095), the anchor names the phase that produces its subject and a stale anchor pattern is widened, never satisfied by editing the artifact of record (§10.7.1-§10.7.2), the allowed set names environment-attributable files apart from extractor-attributable ones (§10.10), a task's Success Criteria discharge a sprint criterion and its gate must measure that criterion's own property (§10.11), a success criterion matches an internal table against an external listing and must name all four cells (§10.12)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Anchor Outcome Set and Re-Capture Allowed Set

**Purpose:** The mirror of a vacuous gate is a gate that cannot pass. Both ship green-looking artifacts and both report a wrong verdict on a correct execution. §10.7 covers an anchor's accepted outcomes; §10.10 covers the allowed set of changed paths after a re-capture. §10.11 covers a task gate that measures a weaker property than the sprint criterion it discharges. §10.12 covers a criterion over an external listing that names fewer than four cells. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you write or review a Signoff anchor, an exit criterion, an Execution Input gate, or a `git diff --stat` allowed set over a snapshot, fixture, golden-file or report directory.

## Table of Contents

  - [10.7 An anchor accepts exactly the outcome set its own task can produce](#107-an-anchor-accepts-exactly-the-outcome-set-its-own-task-can-produce)
    - [10.7.1 An anchor names the phase that produces its subject](#1071-an-anchor-names-the-phase-that-produces-its-subject)
    - [10.7.2 Repair the measurement, not the evidence](#1072-repair-the-measurement-not-the-evidence)
  - [10.10 A re-capture gate's allowed set names the files that change on every capture](#1010-a-re-capture-gates-allowed-set-names-the-files-that-change-on-every-capture)
  - [10.11 A task gate measures the property of the sprint criterion it discharges](#1011-a-task-gate-measures-the-property-of-the-sprint-criterion-it-discharges)
  - [10.12 A criterion over an external listing names all four cells](#1012-a-criterion-over-an-external-listing-names-all-four-cells)

---

### 10.7 An anchor accepts exactly the outcome set its own task can produce

`gate-pre-edit-baseline.md` §10.2 catches a gate that cannot fail. This section catches the mirror defect: a gate that cannot pass. A task's Execution Steps often define more outcomes than the anchor's author expects, such as a zero-hit, nothing-to-do or already-resolved branch. When the anchor enumerates fewer, it rejects a correct execution, and the runner must halt or invent a result.

> [!constraint] Diff the anchor's accepted-outcome set against the owning task's terminal branches at scaffold close
> If the task's Execution Steps define N terminal outcomes, the anchor accepts N. This is set equality, not a subset relation in either direction.
>
> WRONG — the task defines three terminal outcomes, the anchor accepts two:
> ```markdown
> Task step 4:  hits + unambiguous → repoint
>               hits + ambiguous   → route to the orchestrator
>               zero hits          → drift already resolved; record CLOSED-NO-ACTION
>
> Anchor 6:     PASS when the report records `repoint` or `route`
> ```
> The measured and expected outcome is zero hits. The anchor rejects it.
>
> CORRECT — the anchor's branch list is derived from the task's, not authored beside it:
> ```markdown
> Anchor 6:     PASS when the report records `repoint`, `route`, or `CLOSED-NO-ACTION`
>               (3 branches — matches task step 4's 3 terminal outcomes)
> ```
> Carry the parenthetical count. It is what makes the parity checkable by someone who is not re-reading both files.

**The derivation is mechanical, so it belongs at scaffold close.** Enumerate the task's terminal branches and the anchor's accepted outcomes, and compare the two sets. A mismatch in either direction is a scaffold-time failure. Fewer fails a correct execution. More is unreachable, so narrow the anchor or add the missing task branch.

**Set agreement is not count equality:** `gate-command-semantics.md` §10.8 trap 3 carries the rule against hardening set membership into an equality of totals.

**Where the branch set is written more than once, all copies are derived from the task.** The task file's Execution Steps are the source. The Execution Input and the Signoff anchor are copies, and a copy authored independently is how the sets drift apart.

`scripts/lint_gate_checks_plan.py` Check 26 flags a Signoff anchor row that lists two or more outcomes with no matching branch count. §10.10 covers the same defect for a path-set gate's allowed set.

#### Reviewer Check 095 — Anchor Enumerates Fewer Outcome Branches Than Its Task Produces

- **Severity / Role / Type:** WARNING (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** A mechanical anchor, exit criterion, or Execution Input gate MUST accept every terminal outcome its owning task's Execution Steps can produce. An anchor accepting a strict subset fails a correct execution.
- **Detection:**
  1. Open the owning task file's Execution Steps and enumerate its terminal outcomes — every branch that ends the step rather than continuing it. Include zero-hit, nothing-to-do, and already-resolved branches.
  2. Open every artifact carrying an anchor for that task: the Signoff Mechanical Anchor Checks table, the exit criteria, and the Execution Input's own gate blocks.
  3. Compare the two sets. Accepted set smaller than the task's → WARNING, escalating to ERROR where no accepted outcome remains for the branch the task will actually produce.
  4. Accepted set larger → WARNING. Either the extra branches are unreachable, or the task is missing a branch it should define.
  5. An anchor asserting set membership (`⊇`) whose expectation is written as a count equality → WARNING (`gate-command-semantics.md` §10.8 trap 3).
  6. Where two artifacts state the same branch set and disagree with each other, report against the task file's Execution Steps as the source, never against whichever copy is in the majority.
  7. An anchor whose subject a closeout step creates after the verdict, with no post-verdict tag, no bound re-run and no recorded result → WARNING (§10.7.1).
  8. A fix that edits a committed artifact of record so a stale anchor pattern matches, instead of widening the pattern → ERROR (§10.7.2).
- **Finding template:**
```
[WARNING] Anchor accepts fewer outcome branches than its task produces
File: {anchor file path} | Location: {anchor row / exit criterion number}
Issue: Task {task id} Execution Steps define {N} terminal outcomes ({list}); anchor accepts {M} ({list}) — the measured-and-expected outcome `{branch}` is not accepted, so a correct execution FAILs this gate
Fix: Widen the anchor to accept all {N} branches and carry the count inline, per references/gate-anchor-outcome-set.md §10.7 | Confidence: HIGH
```

#### 10.7.1 An anchor names the phase that produces its subject

§10.7 covers an anchor that rejects an outcome its task can produce. This section covers an anchor whose subject does not exist yet. A closeout step can create the subject after the verdict is issued. The anchor then fails by construction, and the task honestly records FAIL on correct work.

> [!constraint] Tag every anchor with the phase that produces its subject, and mark a closeout-phase anchor post-verdict
> Each anchor carries one phase tag. `task` means a task step creates the subject. `review` means the orchestrator review creates it. `closeout` means a step after the verdict creates it. Read the phase from the step that writes the subject. Do not guess it.
>
> A `closeout` anchor cannot pass at verdict time. It is a defect unless it carries three things: the tag `post-verdict`, a bound re-run (the closeout step after which it runs) and a recorded result. Without them, rewrite the anchor onto a subject a task step produces.
>
> WRONG — the anchor counts sections that a closeout step creates after the verdict:
> ```markdown
> Anchor 5:  Grep pattern='^### From {SESSION}' path='{master plan}' output_mode='count'   (expect: 2)
> ```
> The handler step "Step 4.4: Propagate Cross-Task Coordination Flags" in `handlers/run.md` writes those headings after the task loop issues the verdict. The count is 0 at verdict time, so the row is unsatisfiable.
>
> CORRECT — the phase is named, and the row is bound to the step that creates its subject:
> ```markdown
> Anchor 5:  Phase closeout (post-verdict) — re-run after Step 4.4 completes, result recorded in the Summary
>            Grep pattern='^### From {SESSION}' path='{master plan}' output_mode='count'   (expect: 2)
> ```

The sprint-signoff template carries the tag in its Phase column. `templates/sprint-signoff.md` shows the table.

#### 10.7.2 Repair the measurement, not the evidence

A stale anchor pattern and a committed artifact can disagree. Two fixes exist. One changes the measurement and the other changes the evidence. Only the first is legitimate.

> [!constraint] Widen a stale anchor pattern, and never edit a committed artifact of record to match it
> An artifact of record is a committed output of a finished task or session that later work cites as evidence. When an anchor pattern fails against one, the pattern is the suspect. Widen it to accept the shape the artifact really writes, and record the widening in the Result cell. Editing the artifact rewrites evidence to fit the measurement, and a later reader cannot tell the original from the edit.
>
> WRONG — the artifact is edited so the old pattern matches:
> ```markdown
> Anchor 3:  Grep pattern='\*\*Resolution chain:\*\*' ... (expect: 1)   -> 0 hits
> Fix:       edit the upstream Outputs file, "**Resolution chain**:" becomes "**Resolution chain:**"
> ```
> CORRECT — the pattern is widened to the shape the artifact writes:
> ```markdown
> Anchor 3:  Grep pattern='\*\*Resolution chain(:\*\*|\*\*:)' ... (expect: 1)   -> 1 hit, upstream artifact untouched
> ```
> The guard "Step 4.0: Prior-Sprint Outputs Guard" in `handlers/run.md` protects an upstream output only once its owning sprint is COMPLETE. Before that point nothing blocks the edit, so the author refuses it.

### 10.10 A re-capture gate's allowed set names the files that change on every capture

A snapshot directory holds two classes of file. Extractor-attributable files change only when the extractor or the subject binary changes. Environment-attributable files change on every capture. These are anything fetched from a network, anything that records a session or a machine, and anything that records a timing or a cost. A diff-stat gate that lists only the first class reports the second class as regression every time it runs. In one measured re-capture, three of four HALT paths per build were environment drift, and the runner spent its budget clearing them before it found the one real extractor defect.

> [!constraint] Two lists, reported separately, with the environment list derived from what the capture does
> WRONG — one allowed set, authored from the base commit's snapshot shape:
> ```
> allowed = {<subsets>.json, <tool-table>.json, manifest.json, <identity>.json}
> changed = {<changelog>.json, <session>.json, <run-report>.json, <module-strings>.json, ...}
> changed - allowed = 4 paths per build -> HALT
> # three are noise, one is signal, and the gate cannot tell them apart
> ```
> CORRECT — the extractor list and the environment list are separate, and only the remainder halts:
> ```
> extractor_allowed  = {<subsets>.json, <tool-table>.json, manifest.json, <identity>.json}
> environment_expect = {<changelog>.json, <session>.json, <run-report>.json}   # live children + network fetch
> unexpected = changed - extractor_allowed - environment_expect
> # unexpected = {<module-strings>.json} -> HALT on that one path, with the drift rows listed as expected
> ```

Three operative points:

1. **Classify every captured file at authoring time.** For each file the capture writes, ask one question: would this file change if the extractor and the binary were both frozen? If yes, it belongs in the environment list. It does not belong in the allowed list or the HALT list.
2. **Derive the environment list from the command's side effects, not from one observation.** A `--force` that runs live children rewrites their outputs. A capture that fetches a changelog rewrites the changelog. Read the capture code's write sites. A single prior capture cannot show what varies between captures.
3. **Keep the HALT rare.** A gate that always fires gets waved through. The first time a re-capture gate HALTs on noise, the runner learns to expect a HALT. The second time, the real defect is in the same list. Keep the noise out of it.

This applies to any `git diff --stat` or path-set gate over a directory a tool regenerates in place, and to any brief that pins an allowed-change set for a re-run. The optional script `scripts/path_set_gate.py` implements this path-set gate. §10.7 covers the same defect for an anchor's accepted set.

### 10.11 A task gate measures the property of the sprint criterion it discharges

A verification gate is a claim about a criterion. An unanchored gate is a claim about nothing. A sprint criterion states a property of a named subject. A task that discharges it can pin a gate that measures a weaker property, and both report PASS while the criterion is unmet. In one reported session the criterion demanded a diff against the repaired source notebook. The task's gate compared 14 generated notebooks with the first generated one. All 14 matched, the gate passed, and nobody took the diff against the source. Two sibling criteria in the same sprint also could not both hold on one real notebook.

> [!constraint] Quote the criterion and name the gate that measures its own property
> A task that discharges a sprint criterion quotes the criterion verbatim. It also names the gate that measures the criterion's own property: the anchor or comparand, the population, and the operator. Extra gates beside it are welcome. The criterion's own property must be among them.
>
> WRONG — the criterion names a source anchor, and the gate compares the outputs with each other:
> ```markdown
> Sprint criterion: a diff against the repaired source notebook shows differences only in Zone 1 and Zone 3
> Task gate:        the 14 generated notebooks are byte-identical to the first generated notebook
> ```
> The gate's comparand is the first generated notebook. The criterion's comparand is the source notebook. Fourteen identical files pass the gate when all fourteen carry the same wrong edit.
>
> CORRECT — the gate carries the criterion's comparand, and the sibling gate may stay beside it:
> ```markdown
> Sprint criterion: a diff against the repaired source notebook shows differences only in Zone 1 and Zone 3
> Task gate A:      diff each of the 14 generated notebooks against the source notebook; the changed zones are a subset of {Zone 1, Zone 3}
> Task gate B:      the 14 generated notebooks are byte-identical to the first generated notebook
> ```

**Compare three parts of the property.** For each claiming gate, read the comparand (what the output is compared with), the population (which files or rows it covers), and the operator (equal, subset, count, absence). A difference in any one part is a different property.

**Reconcile sibling criteria against one real artifact.** Take the sprint's criteria that name the same artifact and apply each to one real instance of it. A delta that one criterion requires and a sibling forbids is a defect in the sprint plan. No task gate can discharge both. Report it once against the sprint criteria, not once per task.

#### Reviewer Check 112 — Task Gate Measures a Different Property Than the Sprint Criterion It Discharges

- **Severity / Role / Type:** WARNING when a task discharges a sprint criterion without quoting it or naming its gate; ERROR when no gate of the claiming task measures the criterion's stated property, or when two sibling criteria cannot both hold on one real artifact | Task Reviewer | NEW
- **What:** A task that discharges a sprint Success Criterion MUST quote the criterion and MUST carry a gate whose comparand, population and operator match the criterion's own. A gate that measures a weaker property passes while the criterion is unmet.
- **Detection:**
  1. List each sprint Success Criterion. For each one, find the tasks that claim to discharge it. A task claims a criterion when its Success Criteria, Execution Input or Notes for Agent cite the criterion.
  2. For each claiming task, check that the task quotes the criterion verbatim and names the gate that measures it. A claim with no quote, or with no named gate, is a WARNING.
  3. Read the criterion's property as three parts: comparand, population, operator. Read each claiming gate's property the same way.
  4. Compare the two. When no gate of the claiming task matches the criterion on all three parts, report an ERROR that names the differing part, such as "source notebook" against "first generated notebook".
  5. Group the sprint criteria that name the same artifact. Apply each to one real instance of the artifact, read from disk. When one criterion requires a delta that a sibling forbids, report an ERROR against the sprint criteria.
  6. A task with an extra gate beside the matching one is not a finding.
- **Finding template:**
```
[ERROR] Task gate measures a different property than the sprint criterion it discharges
File: {task file path} | Location: {Success Criteria row / gate}
Issue: Sprint criterion "{quoted criterion}" states comparand `{A}`, population `{B}`, operator `{C}`; the task's gate measures comparand `{A'}`, population `{B'}`, operator `{C'}` — the gate can PASS while the criterion is unmet
Fix: Add a gate that measures the criterion's own property and quote the criterion in the task, per references/gate-anchor-outcome-set.md §10.11 | Confidence: HIGH
```

### 10.12 A criterion over an external listing names all four cells

A success criterion that matches an internal table against an external listing depends on two facts. Internal records may exist for the run date. The source may list them. The second fact does not follow from the first.

In one reported run the criterion named two outcomes. Either every internal record matched the listing, or the day had no records and the task was a clean no-op. The internal table held 7 records for the date and the listing returned 0 entries. The match was 0 of 7. Neither named outcome covered it, so the criterion gave no verdict.

| Internal records exist for the run date? | Source lists them? | Verdict the criterion must state |
|---|---|---|
| yes | yes | matched N of N: PASS |
| no | n/a | off-day: clean no-op, PASS |
| yes | no | present-but-unlisted: PARTIAL. Record the census and the source's coverage rule. Name the re-run condition. |
| no | yes (entries outside the internal table) | orphan entries: record them. The cause is a matching defect or a gap in the internal table. |

> [!constraint] Give each of the four cells its own verdict before dispatch
> A criterion that names two cells leaves the other two to the runner. The runner then invents a verdict or halts.
>
> WRONG — two cells named, and the source's coverage asserted from memory:
> ```markdown
> - [ ] every record on {run date} is matched (or the off-day case: 0 records, clean no-op)
> > The source begins listing on {date}. Before that the listing may return 0 entries.
> ```
> CORRECT — the unlisted cell has its own verdict, and the coverage rule is quoted from the probe document:
> ```markdown
> - [ ] every record on {run date} is matched: PASS. 0 records: off-day PASS. Records present but the
>       source lists none: PARTIAL. Record the census (ids, keys, start times) and the source's
>       coverage rule ({probe document}: {rule}). Re-run on the first date the source covers.
> > Source coverage ({probe document}, probed {date}): {the rule, quoted}.
> ```

1. **Enumerate all four cells.** Ask whether internal records exist and whether the source lists them. Write one verdict per cell.
2. **Make present-but-unlisted PARTIAL.** It is neither a clean pass nor a matching failure. Record the census, quote the source's coverage rule and name the re-run condition.
3. **Record orphan entries.** Entries the source lists and the internal table lacks point to a matching defect or a gap in the internal table. Record them and name which.
4. **Name the gate before the session spends.** The session that reads the table this criterion leaves empty states which cell it is in before it spends anything. Without that step it cannot tell an off-day from a present-but-unlisted day.
5. **Quote the coverage rule.** Check every sentence about the source's coverage against the probe document, per [verify-before-cite.md](verify-before-cite.md) §9.B.27.

#### Reviewer Check 119 — Criterion Over an External Listing Names Fewer Than Four Cells

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** A success criterion that matches an internal table against an external listing MUST give a verdict for each of the four cells. A criterion with exactly two enumerated outcomes leaves the present-but-unlisted case without a verdict.
- **Detection:**
  1. List each sprint or task criterion that matches an internal table, census or record set against an external listing, feed, API response or export.
  2. Count the outcomes the criterion names. A criterion that names a matched outcome and an off-day outcome only is a finding.
  3. Flag a criterion whose present-but-unlisted verdict is PASS or FAIL, or that omits the census, the source's coverage rule or the re-run condition.
  4. A criterion that names all four cells is not a finding. A criterion whose comparand is another internal table is not a finding.
- **Finding template:**
```
[WARNING] Criterion over an external listing names fewer than four cells
File: {sprint or task file path} | Location: {Success Criteria row}
Issue: The criterion "{quoted criterion}" names {the matched and off-day outcomes} and gives no verdict for records present in the internal table but absent from the source's listing
Fix: Add a verdict for each of the four cells, with present-but-unlisted as PARTIAL plus census, coverage rule and re-run condition, per references/gate-anchor-outcome-set.md §10.12 | Confidence: HIGH
```

---

*Cross-references: [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) §10.2 (the gate that cannot fail, this file's mirror) · [gate-command-semantics.md](gate-command-semantics.md) §10.8 trap 3 (set membership hardened into count equality) · [exit-criteria-fidelity.md](exit-criteria-fidelity.md) §16.10.6 (the branch set is written once, in the task file, and copied) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
