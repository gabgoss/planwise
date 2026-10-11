---
description: What expires between authoring a plan and dispatching it — the six surfaces a stale premise hides on, quantifier-to-enumeration drift in prerequisites, why a prerequisite-COMPLETE gate re-validates nothing, the Depends On / Required Context split, the sibling-sprint sweep, why a re-measure instruction needs a threshold and an action, and how a router classifies every literal in a routed flag as a decision or a measurement (re-measure the cheap, de-anchor the expensive), why a requirement derived from an unbuilt upstream artifact is tagged and grepped against the shipped artifact at dispatch, why a brief's class-defect count is re-measured over the adjacent directories the class can move to, and why a user-run probe sheet pins the expected build at its head, stops when a launch's banner differs, and treats the first run on a new build as a re-verification of the design, and why a doc section that narrates a pending decision is re-synced by the task that wrote it once the decision lands (swept with `Grep` for the escalation phrase over that task's own prior write-set). Consult at Phase 1, before dispatching any session authored earlier or held behind a gate.
paths: {planwise_root}/{plans_dir}/**
---
# Dispatch Preflight — Claim Expiry (What Aged Between Authoring and Dispatch)

**Purpose:** A gate validates a session against its *stated* premise, and the premise is upstream of every gate. Deferral accrues expiry, and **the waiting is invisible, because nothing re-runs when the gate finally clears.** This file governs what a session re-takes at Phase 1, before it dispatches anything.

**Read this when** a plan was authored before today's dispatch — held BLOCKED behind an external event, scaffolded many sprints in one pass, or waiting on an upstream that has since closed.

Two neighbouring rules own machinery this file builds on and does not restate. [`scaffolding-hygiene.md`](scaffolding-hygiene.md) §12.5 governs re-measuring **gate-bound figures** at preflight — the figures a gate's predicate compares against. §12.3 governs re-deriving a **state-asserting row** at scaffold close. This file covers what neither reaches: the premises that live on surfaces no gate reads, and the reconciliations a resolving dependency graph cannot perform. [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md) §1.4 governs the inherited *flag* specifically.

## Table of Contents

- [1. A Held Plan Re-Takes Every Measurement It Asserts, at the Moment the Gate Clears](#1-a-held-plan-re-takes-every-measurement-it-asserts-at-the-moment-the-gate-clears)
- [2. Quote the Edge, Then Enumerate — Never Enumerate Instead of Quoting](#2-quote-the-edge-then-enumerate--never-enumerate-instead-of-quoting)
- [3. A Prerequisite-COMPLETE Gate Is a Completion Gate, Not a Re-Validation Gate](#3-a-prerequisite-complete-gate-is-a-completion-gate-not-a-re-validation-gate)
- [4. `Depends On` and `Required Context` Are Two Different Assertions](#4-depends-on-and-required-context-are-two-different-assertions)
- [5. Sweep Sibling Sprints That Closed On or After Your Scaffold Date](#5-sweep-sibling-sprints-that-closed-on-or-after-your-scaffold-date)
- [6. A "Re-Measure at Dispatch" Instruction Without a Divergence Action Is a No-Op](#6-a-re-measure-at-dispatch-instruction-without-a-divergence-action-is-a-no-op)
- [7. A Routed Flag Carries Decisions and Measurements: Classify Every Literal, Re-Measure the Cheap, De-Anchor the Expensive](#7-a-routed-flag-carries-decisions-and-measurements-classify-every-literal-re-measure-the-cheap-de-anchor-the-expensive)
- [8. A Requirement Derived From an Unbuilt Upstream Artifact Is Tagged, Then Grepped Against the Shipped One at Dispatch](#8-a-requirement-derived-from-an-unbuilt-upstream-artifact-is-tagged-then-grepped-against-the-shipped-one-at-dispatch)
- [9. A Class Defect Migrates Across a Brief's Scope Boundary: Re-Measure the Adjacent Directories at CONFIRM](#9-a-class-defect-migrates-across-a-briefs-scope-boundary-re-measure-the-adjacent-directories-at-confirm)
- [10. A User-Run Probe Sheet Pins the Build at Its Head, and the First Run on a New Build Re-Verifies the Design](#10-a-user-run-probe-sheet-pins-the-build-at-its-head-and-the-first-run-on-a-new-build-re-verifies-the-design)
- [11. A Doc Section That Narrates a Pending Decision Is Re-Synced by the Task That Wrote It](#11-a-doc-section-that-narrates-a-pending-decision-is-re-synced-by-the-task-that-wrote-it)

---

## 1. A Held Plan Re-Takes Every Measurement It Asserts, at the Moment the Gate Clears

> [!constraint] This is a numbered step of the pre-dispatch gate, never a note
> A plan authored for immediate execution has near-zero expiry. One held behind an external event accrues expiry proportional to how long it waits. Nothing re-runs when the gate clears, so the re-take must be a step that executes.

One sprint held BLOCKED for two days guarded this thoroughly and still shipped six expired facts. Every task brief carried a re-derive instruction. A sweep for pre-committing phrasing returned zero hits across all seven files. All six expired facts sat **outside** task execution steps:

| Expired fact | Surface it lived on |
|---|---|
| a binding "quoted from the live handler" — the binding had moved to a reference section | **two success criteria** |
| a Required Context row describing a section as "the binding definition" — it had become a summary deferring elsewhere | **a Required Context row** |
| a corpus count ("2 active lessons… 18 active items") — actually 8 and 36, with one named defect already repaired | **a Prerequisites block + a Dependencies row** |
| four named coordination-flag consumers — all four sessions had completed | **a task step's "expect at least" list + a Recovery flag table** |
| "Sprints 02–06 are NOT STARTED" + a quoted standing do-not-run note — both false | **a Prerequisites gate callout** |
| eleven line counts, one contradicting a corrected figure in the same file | **Required Context tables + a Context Boundary note** |

**A task file is not the only thing that expires.** A success criterion naming a file is a premise. A gate specification naming a source is a premise. A Required Context row describing what a section contains is a premise. A downstream-consumer list asserting a session is still in the future is a premise. None of them reads like a "brief", and each fails differently:

- A stale criterion is unsatisfiable at closeout.
- A stale Required Context row silently mis-scopes a read.
- A stale consumer list spends real effort drafting for sessions that already finished.

### Four obligations

Each carries its threshold and its action, per §6.

1. **Stamp every measured figure with its measurement date, inline, and name its source command.** The refresh pass then finds them by `Grep` rather than by reading. No threshold applies — this is an authoring rule, not a measurement.
2. **Enumerate the expiring surfaces explicitly**, using the table above as the checklist. **Threshold:** any surface whose re-take disagrees with the recorded value. **Action:** correct it in every copy together, record the cause rather than only the new value, and where the disagreement touches a success criterion or a gate specification, revise that criterion **before dispatch** — not at closeout, where it is unsatisfiable.
3. **Re-derive conclusions, not just counts.** One headline conclusion here survived only by coincidence, resting on eight entirely different lessons, while a sibling claim was outright refuted because the defect it named had been fixed and its owner archived COMPLETE. **Threshold:** the re-derived conclusion differs from the recorded one, in any direction. **Action:** revise the plan before dispatch. Do not annotate the old conclusion and proceed.
4. **A downstream consumer's existence is a measurement too.** Before drafting a coordination flag, check its target is still a future session. **Threshold:** the named consumer has already completed. **Action:** do not draft the flag. Route the observation to the genuine consumer, or record it as discharged with the date the target closed.

**Adding another "re-derive this" sentence to the briefs would have changed nothing.** The briefs already said it, repeatedly and well. What was missing was a step that *runs*.

---

## 2. Quote the Edge, Then Enumerate — Never Enumerate Instead of Quoting

> [!constraint] A prerequisite is a derived artifact, and restating a quantifier as an enumeration is a lossy derivation
> ```
> WRONG — the quantifier restated as the sprint set that existed at authoring time:
>   **Sprints 01–06 ALL COMPLETE** (E6 edge) — verify each Sprint Signoff verdict PASS.
>      ← the edge said "all". Sprints 08, 10 and 11 were dropped silently.
>      ← the citation certifies a narrowing the source does not contain.
>
> CORRECT — the derivation stays visible and re-checkable on the line itself:
>   E6 = all→ES7  ⇒  {ES1…ES6, ES8, ES10, ES11}
>      ← a reader can falsify the enumeration against the edge without leaving the line.
> ```

The citation is what made it dangerous. Written as a bare list, `Sprints 01–06` invites the question *"why those?"*. Written with the edge name attached it reads as already reconciled, and a reader's natural verification — *does the plan say that edge exists?* — returns yes. A 27-finding review fixed 5 BLOCKERs and 9 ERRORs and never flagged it.

Three rules follow.

- **The two forms agree only at the instant of authoring.** A quantifier keeps tracking the set. An enumeration freezes it.
- **When an edge names a quantifier (`all`, `every`, `any`), treat the enumeration as expiring.** Re-derive the member set at Phase 1 whenever new members have been scaffolded since.
- **Add the reconciliation to plan review explicitly.** For every prerequisite citing a graph edge, re-derive the edge's member set and diff it against the stated list. This is mechanical and cheap, and no existing check covers it — prerequisites are treated as premises rather than as derived claims.

### The same expiry lands on what the session publishes

- **A sprint that publishes "final" anything owes a freshness predicate, not a prerequisite.** "Runs last" is meaningful only relative to a set. State the validity condition — *"these counts are final iff no sprint lands after this session"* — so that reordering makes the staleness self-announcing.
- **When such a sprint is suspended mid-flight, re-label its outputs at suspension time, with the void scope enumerated** (which files, which counts). A delta report authored as *the gate* for the next session, and left labelled that way, hands that session an expired claim wearing a gate's name.

---

## 3. A Prerequisite-COMPLETE Gate Is a Completion Gate, Not a Re-Validation Gate

> [!constraint] "Prerequisite COMPLETE" answers a question nobody was worried about
> It establishes that the upstream finished and its outputs exist. The actual risk — that what the upstream *found* invalidates the downstream plan — is untouched by it, and the green checkmark feels like clearance.

In one measured case both upstream sprints were COMPLETE and all six discovery documents existed. The mandated re-read found a routing table in which **14 of 21 hypotheses had no owning task** — ten of them unanswerable by the probe apparatus every authored task had built. The session as written could not have answered two thirds of what it existed to answer.

**Diligence alone will not fix this, for a structural reason.** The context boundary that keeps an orchestrator's budget intact forbids it from reading upstream outputs. So the orchestrator is the one actor guaranteed not to see the evidence that its own plan has gone stale. Everything visible from inside the session — statuses, dependency graph, file existence — reads clean. Staleness is visible only from outside the boundary, which is precisely where nobody is looking.

### Five application rules

1. **Put the re-validation gate in the file the executor is required to read.** Under delegated execution that is the orchestration file, with an explicit statement that the context boundary is suspended for this one read. The same warning existed in four places here. Only the one positioned in the execution path fired.
2. **Make "confirmed unchanged" an artifact.** Require the outcome written down either way. An empty record is indistinguishable from a re-read that never happened, and a resuming session cannot tell the difference.
3. **State the gate as an action with a named input.** *"Re-read X against Y and revise before dispatch"* is executable. *"This decomposition is provisional"* will be read as context.
4. **Author upstream findings in checkable form.** A routing table with an owner column per hypothesis makes staleness countable. The same information as narrative advice is a judgement call under time pressure.
5. **Expect the revision to change the task count, not just the task contents.** Where an upstream finding says an entire class of question is unanswerable by the authored apparatus, widening existing tasks cannot fix it. A gate phrased as "expect scope to change" under-prepares for that.

**Preserve identifiers across the revision** wherever anything downstream cites them.

---

## 4. `Depends On` and `Required Context` Are Two Different Assertions

> [!constraint] Only the first survives a preserved-numbering revision
> ```
> Depends On      says "this task cannot start until that one finishes."
>                 → preserving task numbers keeps it TRUE.
> Required Context says "these specific files contain the evidence I need."
>                 → a new sibling task producing new evidence FALSIFIES it,
>                   and no amount of careful numbering repairs that.
> ```

An upstream added two tasks and deliberately preserved numbering 1–4 so downstream `Depends On` stayed valid. Between them the two new tasks owned **15 of 21 hypotheses**. The downstream's Required Context listed the outputs of Tasks 3 and 4. Dispatched as authored, it would have marked fifteen questions UNRESOLVED and produced a verdict table that looked complete and carried a plausible tally.

**An upstream that revised itself correctly is exactly why nobody caught it.** Numbering was preserved precisely so downstream declarations stayed valid — which is correct for `Depends On`, and is what made the staleness invisible, because the dependency graph still resolved so nothing looked broken. Every safeguard worked as designed and none covered this: the prerequisite gate passed 6/6, seven coordination flags were routed, the upstream's own record was accurate and detailed, and both sessions were internally consistent. The gap lived *between* the two records.

**For the sender.** Recording the revision in your own Recovery is necessary and not sufficient. Your closeout owes every downstream session a flag naming which **output files are new, by path**, and which downstream **deliverables or questions now depend on them**. "We went from 4 tasks to 6" is not that flag. If you preserved numbering to protect the dependency graph, say so *and* say that Required Context is the thing you did not protect.

**For the receiver.** At the step-zero gate, do not check only that `Depends On` still resolves. Enumerate the upstream's output directory and reconcile it against your own Required Context tables, file by file, asking the question the dependency graph cannot answer: *is there evidence on disk that no task of mine has been told to read?*

**A gate that validates relationships between tasks will not catch a change in the artifacts those tasks produce. When an upstream moves, re-derive both.**

---

## 5. Sweep Sibling Sprints That Closed On or After Your Scaffold Date

This is a third Phase-1 preflight source, alongside the sprint plan's Carried-Forward section and the orchestration's own flag block.

> Sweep sibling sprints whose session closed ON OR AFTER this session's scaffold date. Read their Recovery `Files Modified` and `Key Findings`. For each file they touched that intersects this session's edit set OR any sweep surface a task declares, derive the fact and route it into the affected task files as an orchestrator-measured preflight entry — labelled as such, distinct from an upstream-routed flag.

**Threshold and action, per §6.** The threshold is any intersecting file. The action is to route the derived fact into every affected task file before dispatch, and — where the fact changes a gate's expected value — to restate that expected value in the task file itself, not merely to note the change.

**The two-hop flag model cannot cover this.** It routes flags to their consumer. It does not route situational awareness to a concurrent sibling, and a sprint that closes between your scaffold and your dispatch has changed your inputs without owing you a flag. One sibling closed the same day this session ran and routed all three of its flags correctly, to their genuine consumer, a different sprint. Four material side effects reached no file this session's orchestrator reads:

- a brand-new 186-line reference entering a task's file sweep by design, naming forbidden shell verbs;
- a shipped decision resting on two anchors another task was about to edit, one of which it then deleted;
- a landed edit changing a cross-sprint content grep gate's expected value from 1 to 0;
- a reciprocal control that pre-answered part of this session's own gate.

**The intersection test is not just "files we both edit".** That is what a Cross-Sprint File Touches table already covers. It must include **files a task will only read or sweep** — which is how a brand-new file enters a sweep surface with no shared-edit declaration anywhere. A file nobody declared as shared is exactly the file no existing table lists, so an edit-set-only test is blind to the whole class.

Two supporting practices:

- **State the expected value, not just the command, for a cross-sprint gate.** "1 = not yet landed; 0 = landed" merely records a value. "Expect 0, the sibling landed it" converts it into a gate that can *fail*.
- **Label orchestrator measurements distinctly from routed flags.** A runner treats an upstream flag as validated context not to re-derive, and a sweep that echoes the orchestrator's numbers is not independent.

---

## 6. A "Re-Measure at Dispatch" Instruction Without a Divergence Action Is a No-Op

> [!constraint] It reliably produces a measurement and reliably changes nothing
> ```
> Task 1: <!-- Register rows (projected) — re-measure at dispatch, re-roll if >10% off. -->
> Task 2: <!-- Register rows (projected) — re-measure at dispatch. -->
> Task 3: <!-- Register rows (projected) — re-measure at dispatch. -->
> ```
> The `re-roll if >10% off` clause — the only part naming an **action** — was present on the one task whose projection was accurate, and absent from the two that needed it.

Task 2 duly re-measured, reported `85` against a projected `~45` in its verification block, and proceeded on the wrong budget. It surfaced the gap in `ISSUES` at completion: correct behaviour, far too late to change any decision.

Every re-measure instruction needs all three parts:

| Part | Example |
|---|---|
| The measurement | `re-measure the pull count at dispatch` |
| The **threshold** | `if >10% off the projection` |
| The **action** | `re-roll the token estimate AND the output-file budget derived from it, and report the new figures in your status block before authoring` |

Without the third part the runner has no licence to act, so it does the only thing it can: absorbs the divergence and mentions it at the end.

**When a divergence-action clause exists on some siblings and not others, that is a defect, not a style difference.** Sibling task files are usually written by one pass over one template, so a clause present on one and missing on two is an authoring slip that a reviewer reads as intentional variation. `Grep` the sibling set for the clause and normalize it.

This section binds §1 and §5 of this file, and both carry their threshold and their action inline. A rule that prescribes re-measurement without them would ship the exact defect it records.

---

## 7. A Routed Flag Carries Decisions and Measurements: Classify Every Literal, Re-Measure the Cheap, De-Anchor the Expensive

> [!constraint] A flag's decisions route verbatim. A flag's measurements expire on their own
> The orchestrator's protocol routes a validated flag as context and does not re-derive it. That protection covers the flag's decisions. It does not cover a measurement the flag happens to carry. A count, a byte offset, a line number, a wall time and a file inventory expire through a change made in another file, in another session, by another agent.
>
> [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4.C is the receiver side: every inherited value is expired. This section is the router side. [scaffolding-hygiene.md](scaffolding-hygiene.md) §12.5 owns gate-bound figures and is not restated here.

**First example, a test count.** At the close of one session a flag said the proven invocation gave "29 passed / 5 skipped". The next session's preflight routed it verbatim into three briefs as "Step 3's expected tests line reads `tests (ok: 29 passed, 5 skipped)`". The first runner measured the pre-task default tier and got 38 passed / 5 skipped before any edit. The gap predated the session. Six test modules existed that the flag's author had not counted, and the author had quoted an earlier run, not the closing run. A runner that trusted the brief would have reported a defect against correct work, or shrunk the suite to 29.

**Second example, a corpus count.** A closing session measured a corpus on a morning: 238 item files, 50 active and 188 archived. The next session's evening preflight routed the figures as orchestrator-validated context marked "do NOT re-derive". The runner's dry run reported 376 items (183 open, 193 closed). The orchestrator first suspected the scanner. One file count settled it: 185 and 193 files in the two directories. `git log --since=<date> --diff-filter=A` then showed 140 files added by that day's commits. A batch harvest had landed between the two readings.

> [!constraint] Route the decision, and re-anchor or de-anchor the number
> WRONG — route the flag's number as the expected value:
> ```
> Flag:  "proven invocation -> 29 passed / 5 skipped"
> Brief: "Step 3's expected tests line reads `tests (ok: 29 passed, 5 skipped)`"
> # Runner measures 38 before its first edit. The brief now asserts a false number.
> ```
> CORRECT — route the decision, and re-anchor or de-anchor the number:
> ```
> Flag:  "proven invocation -> path argument carries scope; $0 depends on X and Y"
> Brief: "Step 3 records the observed count and asserts on scope: zero node IDs
>         outside <tests-dir>/. The last recorded count was 29
>         (<session>, <date>); a different figure is data, not a defect."
> ```
> WRONG — route a morning measurement as validated context in the evening:
> ```
> 1. Corpus facts the scanner will meet: 238 item files (50 active / 188 archived). Do NOT re-derive.
> ```
> CORRECT — re-measure at dispatch, and route the number with its provenance:
> ```
> 1. Corpus measured at this session's dispatch (<date> evening, `ls <dir>/*.md | wc -l`,
>    `ls <dir>/Archive/*.md | wc -l`): 376 items (183 / 193). The earlier morning count was 238;
>    140 files landed in today's commits between the two readings.
> ```

### Five rules for the router

1. **Classify every literal in a flag as a decision or a measurement.** A decision routes verbatim: which invocation, which path argument, which `$0` condition. A measurement gets rule 2 or rule 3.
2. **Re-measure a cheap anchor at preflight.** Do it in the orchestrator's own window, when the command is read-only and finishes in under a minute (`--collect-only -q | wc -l`, `wc -l`, `grep -c`, `ls | wc -l`). Route the fresh figure with today's date and the earlier figure as history.
3. **De-anchor an expensive anchor.** When re-measuring costs a dispatch, route the number as history ("last recorded N on DATE"). Route the assertion as a property: scope, membership or presence. Never route the assertion as the number.
4. **Write every routed figure with its date and its source command.** "238 files (measured `<date>` morning, `ls <dir>/*.md`)" tells the reader how to refresh it. "238 files" tells the reader to trust it. The sender of a flag has the mirror duty: name the run the count came from, and its date.
5. **When a runner's number disagrees with a routed number, count before diagnosing.** One file count settles whether the scanner or the figure is wrong. Read the commit log afterwards to explain the movement.

**Applies to** any `Pre-Known Cross-Task Coordination Flags` block carrying a pass count, a file count, a line count, an offset, a wall time or a token estimate. Test-suite sizes are the common case, because a suite grows through every session that touches its tree. Corpus sizes are the second, because a concurrent session can add a batch in one commit.

---

## 8. A Requirement Derived From an Unbuilt Upstream Artifact Is Tagged, Then Grepped Against the Shipped One at Dispatch

> [!constraint] A decision row is a claim about a future artifact. Once the artifact ships, the two records are independent
> A row in a Decisions table records what its author believed at planning time. When the implementing plan ships, the decision's wording and the artifact's behaviour are two separate records. Only one of them is what a downstream task's success criterion is measured against.
>
> A task whose acceptance is "matches the upstream tool's output" turns every other content requirement on the same artifact into a claim about that tool. Each such claim is one `Grep` of the tool away from being verified or refuted.

A Master Plan locked two decisions on one day. One said a changelog moves to its own file, with a one-line pointer left behind. The other said a `## Dependencies` section survives as a generated section sourced from `blocks:` frontmatter. A later plan's task files were scaffolded the same day from those decisions.

The first task told the runner to derive a shipped seed from the generator's zero-item output and prove it byte-identical. In the same Execution Steps it told the runner to give the seed a changelog pointer, a title-budget comment and a `## Dependencies` section. The last task and the orchestration's first success criterion asserted all three in a fresh-init hub.

Three weeks later the upstream plan built the generator. It implemented the second decision as a `Blocks` column, not a section, and it emitted no footer at all. Its review recorded that the legacy table and footer disappear at cutover, and routed that to the cutover session. Nothing re-read the earlier plan's task files. They still carried the decision's wording as if it were the tool's behaviour.

One `Grep` per requirement showed the generator matched none of `Dependencies`, `Last Updated`, `Changelog` or a title comment. The init routine copied a fixed list of three seeds, so the changelog seed the first task was told to create could never reach a fresh project. Executed literally, the first task could not satisfy its own success criterion. The last task would have failed against correct upstream behaviour. The gap surfaced at CONFIRM as a structural finding and cost four task-file amendments before the first dispatch.

> [!constraint] Tag the requirement, then check it against the tool before dispatch
> WRONG — the task text is the decision verbatim, and the success criterion measures the tool:
> ```
> Step 2: derive the seed from the generator; diff MUST be empty       <- measures the tool
> Step 7: keep `## Dependencies`, marked as generated from `blocks:`   <- restates the decision
> SC:     `## Dependencies` present and generated                      <- the tool never emits it
> ```
> CORRECT — the requirement carries its provenance, and the orchestrator checks it against the tool before dispatch:
> ```
> Step 7 (per <decision> — verify against <generator> before dispatch): `## Dependencies` generated from `blocks:`
> Orchestrator, Phase-1 READ:  Grep 'Dependencies' <generator> -> no section emitted; blocks -> a column
>                              -> structural finding -> Option A: seed = generator output; decision wording routed for amendment
> ```

Three rules follow.

1. **Tag at scaffold time.** Tag every requirement that depends on an unbuilt upstream artifact with the decision it derives from ("per `<decision>`, generated"). The tag lets the dispatching orchestrator find the claims that need re-checking.
2. **Grep at dispatch time, before CONFIRM.** Search the shipped artifact for each tagged requirement. The cost is one search per requirement. In the example the four searches took under a minute and turned a guaranteed FAIL into an approved scope decision.
3. **Route a departure to every downstream session.** When the implementing plan departs from a locked decision, route the departure as a flag to every downstream session scaffolded from that decision, and amend the Decisions table. Routing it only to the session whose runtime would notice misses the session whose task text already assumed the decision.

**Applies to** any task scaffolded before the artifact it verifies exists. The decision was honest when written and the implementation moved afterwards. This differs from a decision that knowingly expires a downstream criterion. There, the check belongs at the decision. Here, it belongs at dispatch. §4 ("`Depends On` and `Required Context` Are Two Different Assertions") splits what a task needs from what it merely reads. A tagged requirement is a third kind: a claim about an artifact that did not exist when the task was written.

---

## 9. A Class Defect Migrates Across a Brief's Scope Boundary: Re-Measure the Adjacent Directories at CONFIRM

> [!constraint] A baseline count is taken inside a boundary at a date. The class does not respect the boundary
> When items move between directories, a defect moves with them. A re-measurement confined to the brief's own glob reports the class as shrinking while it has only relocated. A "re-enumerate at execution" instruction is correct and insufficient, because it re-runs the same scope.

A brief said 51 of 118 active backlog items lacked frontmatter, measured on `<date-1>`. It scoped the enumeration to `<backlog>/BB-*.md`. The brief was careful. It told the runner to re-enumerate and to treat a different count as a finding.

Twenty-four days later the same command returned 6. The 51 had not been repaired. Forty-five of them had been archived, and `<backlog>/Archive/` now held 53 frontmatter-less files in a directory the brief never named. The literal scope would have backfilled 6 files and reported a clean gate.

A later task strips the body `**Status:**` line corpus-wide. It assumed the first task had given every stripped file a `status:` key. On 53 archived files that strip would have deleted the only status record they had. The existing drift command (`frontmatter != body` over the archive) would then have read clean, because both sides were empty. The orchestrator caught it by running the enumeration over the adjacent directory during CONFIRM, before any dispatch. Three of the session's five scope-expansion decisions came from measurements taken outside the briefs' named directories.

> [!constraint] Re-measure every directory the class can occupy, then reconcile the movement
> WRONG — re-measure inside the brief's glob and accept the smaller count:
> ```
> for f in <backlog>/BB-*.md; do ...; done | wc -l     # 51 -> 6: "the class shrank"
> ```
> CORRECT — re-measure every directory the class can occupy, then reconcile:
> ```
> active:   6      archived: 53      total: 59 (brief said 51 — the set moved, and grew)
> -> Option A / Option B gate before the first dispatch; the later task's precondition re-derived from 59, not 51
> ```

Three rules follow.

1. **Widen the enumeration at CONFIRM.** Run the brief's enumeration over every directory the class can legally live in, not only the one the brief names. [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4.A ("enumerate the input set") states the duty. This rule says what the set includes. For a backlog corpus it is the active directory and its archive. If the count fell inside the boundary, the first question is where it went, not whether the work shrank.
2. **Check downstream assumptions against the widened count.** Do it before dispatching the first task. A later task whose scope is wider than an earlier task's, but whose brief assumes the earlier task covered it, is where a scope gap turns into data loss.
3. **Ask whether the after-state is reachable by deletion.** A gate whose two sides can both be empty passes on destruction. A drift command counts disagreements, and two absent values do not disagree. [gate-denominator-integrity.md](gate-denominator-integrity.md) covers the gate with an empty denominator. Before trusting a before-versus-after proof, ask whether the after-state could be reached by deleting the subject rather than repairing it.

**Applies to** any brief whose baseline count was taken on a tree that has since had items moved, archived, split or promoted between directories. That covers backlog and lessons corpora, plan trees with `Archive/` folders, and any migration whose "remaining" set is measured by a glob.

---

## 10. A User-Run Probe Sheet Pins the Build at Its Head, and the First Run on a New Build Re-Verifies the Design

> [!constraint] A version-era claim expires the instant the tool updates, and an auto-updating tool can do that between two lines of one sheet
> A design's declarations, refusal strings, surface counts and type assumptions are inherited claims, each keyed to one build. None of them carries a check that the build is still the one it describes. An auto-update in the middle of a sheet is a stop condition, not a footnote.

A probe sheet asked the user to launch an auto-updating CLI three times in a row. The banner of launch one read `v<N>`. The banner of launch two, minutes later, read `v<N+1>`. The design had been measured on the build before both.

The new build differed from the design's reference by 218 diff hunks. A first type-check against regenerated declarations found 8 mismatches, including a design assumption the new API no longer supports. The design's counted surface was 24/42/33 names on the design build and 32/45/33 on the new build. The sheet had recorded a version pin at grade time. That pin named the build on disk after the launches, not the build that answered launch one.

> [!constraint] Name the expected build, check it on every launch, and stop on a difference
> WRONG — the version is recorded once, at grade time, from whatever build happens to answer:
> ```
> <cli> --version    # pin value (run after the launches)
> ```
> CORRECT — the expected build is named, every launch's banner is checked against it, and a change stops the sheet:
> ```
> # Expected banner on EVERY launch: <cli> v<X.Y.Z>
> # A different version on any launch -> stop, report the two banners, do not run the next launch.
> # Before grading on a new build: re-extract declarations, re-run the type check,
> # re-count the surface, diff against the design.
> ```

Three consequences follow.

1. **Pin the build at probe start and make the sheet check it.** The sheet does not say "record the version at grade time". It names the expected value, prints the version on the first line of every launch, and stops the run before the next launch if the banner differs.
2. **Treat the first run after a version change as a re-verification of the design, not as the probe.** Re-extract the declarations, re-run the type check, re-count the surface, and diff each against the design's stated values before grading anything. In the measured case the 218-hunk diff and the 8 type-check mismatches were the real result. The answer the probe was written to collect was secondary.
3. **Freeze the binary for a lab that measures a tool's behaviour, or accept that every sheet re-pins.** A lab cannot share a binary with a workflow that updates it silently. Where the binary cannot be frozen, the first launch of every sheet is a version gate.

**Identity point.** A pin file read after the fact records the build at pin time, not the build that ran each launch. When a sheet has more than one launch, record the banner per launch. [measure-artifact-identity.md](measure-artifact-identity.md) § "Treat a Disputed File Reading as a Question About Which Artifact Was Read" governs the copy-and-instant side of the same problem.

**Applies to** any sheet, probe or lab run by a person against a tool that updates itself, and to any design whose counts or signatures were measured on one build and consumed on another. §1 ("A Held Plan Re-Takes Every Measurement It Asserts, at the Moment the Gate Clears") covers the same expiry for a held plan. This section covers the case where the expiry lands inside a single run. [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) § "A Declared API Drifts Between Builds: Regenerate the Declarations and Type-Check on Every Build Change" carries the type-check step.

---

## 11. A Doc Section That Narrates a Pending Decision Is Re-Synced by the Task That Wrote It

> [!constraint] A doc section drafted to describe an in-flight decision is a snapshot of a state expected to change
> Nothing marks the section for a re-visit once the state changes. The task that wrote the narration is the one that knows it is conditional. A downstream task has no way to tell "this reads as final" from "this was true when written".

Two docs (`<doc-a>`, `<doc-b>`) were written while a ceiling escalation was still open. They said: "escalated, not resolved; the ceiling's numeric value is unchanged pending an explicit re-statement decision". The first resume of the task applied the fix, which re-stated the ceiling to `0.25`. That resume was scoped to touch only the test file. The two doc sections kept narrating a decision that had already landed. Left alone, the closeout task would have quoted the superseded `0.05` value and the "unresolved" framing into the sprint's permanent record.

> [!constraint] When a decision lands, sweep every doc section the deciding task itself wrote that narrated the pending state
> WRONG — resolve the decision but scope the fix to only the file that encodes it:
> ```
> Resume scope: <test file> only (the constant + its comment)
> # <doc-a> section still says "escalated, not resolved" — a downstream reader,
> # or a downstream task quoting it, now has an internally inconsistent picture.
> ```
> CORRECT — sweep the narration in the same resume:
> ```
> Resume scope: <test file> (the constant + its comment)
> Resume scope (same round or an immediate follow-up): every doc section THIS task already wrote
>   that describes the decision as pending — Grep the task's own prior edits for the escalation language.
> ```

Two operative points follow.

- **The task that authors a decision-pending doc section owns re-syncing it once the decision lands.** That holds even when the resolution happens in a different resume round with a narrower write-set. Do not assume a downstream consumer will catch the staleness. It will quote the doc's prose as ground truth.
- **A downstream "quote, never run" task is the shape most exposed.** A closeout is the usual case. Its whole contract is trusting an upstream output file or doc section verbatim, so it has no mechanism to notice the source went stale between writing and quoting.

**The mechanical step.** When a resume resolves an escalation, the resume brief lists the escalation phrase. The orchestrator runs `Grep` for that phrase over the task's own prior write-set before it marks the resume complete. A hit is a narration to re-sync, not a quote to preserve.

**Applies to** any doc, report or recovery section written while a decision, escalation or ceiling was open. The section "The same expiry lands on what the session publishes" under §2 covers the freshness predicate a published "final" figure owes. This section covers the prose a task writes about a state it expects to change.

---

*Cross-references: [scaffolding-hygiene.md](scaffolding-hygiene.md) §12.3 (re-derive a state-asserting row at scaffold close) and §12.5 (re-measure every gate-bound figure at preflight) — this file covers the surfaces neither reaches; [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4 (reconciling an inherited flag, receiver side); [scaffolding-hygiene-Part-2-DerivationAndParallelism.md](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §16 (the computed write-set intersection §5's sweep extends to read-or-sweep surfaces).*
