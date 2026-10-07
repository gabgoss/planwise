---
description: A brief that names the likely answer gets that answer back, and hedging it does not help. Covers separating context from premise in a dispatch brief, supplying the discriminator instead of the destination, fix instructions that name a target number, directional guardrails, routing every branch of a plan's central question, inviting the contradiction, and what to do when the premise is refuted mid-run. Consult while writing a spawn prompt, a task brief, a repair instruction, or a plan's anti-inference guardrail, and at every reconciliation point where new evidence lands.
paths: {planwise_root}/{plans_dir}/**
---
# Dispatch Brief Neutrality — A Brief That Supplies the Answer Gets the Answer Back

**Purpose:** Three separate sessions dispatched work with the dispatching role's own reading embedded in the brief, and in every case the runner returned that reading back. The mechanism is not dishonesty: a stated hypothesis reorganises attention, and contradicting the dispatcher is a higher bar than agreeing with it.

**Read this when** you are writing a spawn prompt, a task brief, or a fix instruction; when a plan states a guardrail against an inference; and at every reconciliation point where a new evidence source lands, a task contradicts a sibling, or a gap statement is closed.

The failure has two properties that make it a rule rather than a matter of vigilance. A premise is **write-once and invisible** — once dispatched it does not re-read the world, and it leaves no trace in the deliverable identifying which conclusions were seeded. And the deliverable is **unfalsifiable after the fact** — a synthesis that reaches the primed conclusion looks exactly like one that reached it independently. Nothing downstream fails loudly.

The orchestrator is the most dangerous source of a premise precisely because of its position: it holds the reconciled cross-task view no single runner has, which makes its readings *usually right* — and therefore rarely challenged. That authority is inherited from the role, not from the evidence, and it survives the evidence changing unless someone retracts it explicitly. All three incidents were caught by generic safety nets, not by anything in the brief.

One neighbouring rule owns the quantitative half of this discipline. [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §1 covers withholding a *figure* the dispatched task exists to re-derive. This file covers the qualitative case — a stated *expectation*, a named cause, a target number in a fix instruction — and what to do once such a premise has already shipped.

## Table of Contents

- [1. Context and Premise Are Indistinguishable in a Brief — Mark Which Is Which](#1-context-and-premise-are-indistinguishable-in-a-brief--mark-which-is-which)
- [2. Supply the Discriminator, Never the Destination](#2-supply-the-discriminator-never-the-destination)
- [3. A Fix Instruction That Names a Target Number Gets the Number](#3-a-fix-instruction-that-names-a-target-number-gets-the-number)
- [4. Guardrails Are Directional — A Guardrail That Names One Inference Blesses the Other](#4-guardrails-are-directional--a-guardrail-that-names-one-inference-blesses-the-other)
- [5. Every Branch of the Plan's Central Question Needs a Route, Not an Enum Slot](#5-every-branch-of-the-plans-central-question-needs-a-route-not-an-enum-slot)
- [6. Invite the Contradiction, in the Prompt](#6-invite-the-contradiction-in-the-prompt)
- [7. When the Evidence Base Changes — Retract Explicitly, Stop the Primed Agent, Resume the Builder](#7-when-the-evidence-base-changes--retract-explicitly-stop-the-primed-agent-resume-the-builder)
- [8. Record the Refutation, and Keep the Real Defect the Wrong Diagnosis Found](#8-record-the-refutation-and-keep-the-real-defect-the-wrong-diagnosis-found)

---

## 1. Context and Premise Are Indistinguishable in a Brief — Mark Which Is Which

> [!constraint] Both are prose the dispatcher writes, and both are read as authoritative
> The difference is what happens when they are wrong: bad context gets corrected by evidence, while a bad premise **redirects what counts as evidence**.
>
> ```
> CONTEXT  — measurements, corrections, file locations, scope limits.
> PREMISE  — "you will probably find", "be willing to conclude",
>            "the likely headline is". Requires a reason to include at all.
> ```
>
> The prime that shipped, hedged, and still functioned as a premise:
>
> ```
> > Be willing to conclude that a substantial part of "hundreds of thousands
> >  of tokens" is an accounting-semantics artifact rather than window pressure.
> ```
>
> It was hedged, labelled as a possibility, and the task file separately required the agent to distinguish the two classes on evidence. It still functioned as a premise: it named a destination, supplied the reasoning that reached it, and carried the dispatching role's authority. **"Be willing to conclude X" is not weaker than "conclude X" in effect** — it names X, supplies the reasoning for X, and adds permission. Nothing in it names not-X.

Classify every sentence of a brief before it ships. A sentence that states a measurement, a correction, a file location, or a scope limit is context and stays. A sentence that names where the runner will probably end up is a premise, and it needs a reason to be in the brief at all — usually there is none, because the runner's value is that it does not already know.

---

## 2. Supply the Discriminator, Never the Destination

> [!constraint] Direct the method, never the destination
> ```
> WRONG — names the destination and supplies the reasoning that reaches it:
>   "this is probably an accounting artifact rather than window pressure"
>
> CORRECT — names the method and leaves the destination open:
>   "distinguish accounting artifacts from window pressure;
>    here is how each would look in the data"
> ```

The repair-time form of the same rule: state what you verified separately from what you inferred, and label which is which. *"This row set is 12, the breakdown says 11"* is evidence. *"The compressed rows probably explain the rest"* is a diagnosis, and it goes in a different sentence.

Where the thing being withheld is a *figure* rather than a reading — a sibling's cost, a prior run's count — [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §1 carries the inject/withhold table and the reason to say out loud that the withholding is deliberate. The two rules meet on one question: could knowing this change what the agent reports? If yes, supply the method for finding it, not the thing itself.

---

## 3. A Fix Instruction That Names a Target Number Gets the Number

> [!constraint] The arithmetic is the argument — the plausible cause was provably not the cause
> A coverage gate FAILed a 252-row disposition table. The orchestrator found a second defect — two rows carrying multiple deliverables against a stated one-row-per-deliverable grain — and a mechanical expansion gave **198** where the table claimed **201**. The natural inference — *the compressed rows explain the 3-row gap* — was wrong: expanding those rows is **arithmetically neutral**, since both were already counted at deliverable grain in the roll-ups. The real cause was three **cluster-level** rows owned by a whole reference-family rather than by any single source item, so no item-ID prefix could carry them: `201 − 3 = 198`, exactly.
>
> The instruction that worked, including the forbidding clause:
>
> ```
> Resolve it whichever way is actually correct: expand the rows and re-derive,
> or document the line-vs-deliverable distinction and reconcile the gap.
> Pick based on what the rows actually represent — do not just make the numbers
> agree. If the gap turns out to be something other than the compressed rows,
> say so and report what it is.
> ```

Had the instruction simply said *"fix the 198-vs-201 discrepancy"*, the most direct route was to declare the compressed rows the cause and adjust a subtotal by 3. The table would have balanced, three real deliverables would have stayed invisible to every prefix-keyed count downstream, and a footnote would have asserted they did not exist. **Numeric agreement is the cheapest thing in an artifact to produce and the least informative thing to verify** — a table forced into balance is indistinguishable from a table that was always right.

Expanding the compressed rows moved the page-level count and not the totals. That neutrality is the finding: the orchestrator was not merely careless, the plausible cause was *provably* not the cause, and only an instruction that forbade forcing agreement left room for the fixer to say so.

---

## 4. Guardrails Are Directional — A Guardrail That Names One Inference Blesses the Other

> [!constraint] A guardrail that names one direction implicitly blesses the other
> ```
> WRONG — anticipates one collision, and implicitly permits its mirror:
>   "Do not reason from the measurement toward `advisory`."
>
> CORRECT — symmetric, and names the destination of the unresolved pair:
>   "Docs and measurement are both evidence. Do not resolve a contradiction
>    between them in EITHER direction. Preserve both; route the reconciliation
>    to the sprint that can test it."
> ```

The plan forbade exactly one inference — reasoning from 408 measured successful `Bash` calls toward "the allowlist is advisory" — because that was the failure it anticipated. The inference actually on offer ran the other way: letting an authoritative `enforced` verdict retro-invalidate the measurement. That second inference is *more* seductive, because it is the one where the confident-looking source wins.

Two supporting rules belong here:

- **A definitive upstream answer is not automatically the stronger evidence.** Documentation states intent about a versioned, moving system; a transcript scan states what a specific build actually did. Neither dominates by category. This is deliberately uncomfortable and must survive editing: a reader who trims it keeps only the half that flatters authoritative sources, which is the direction the incident actually failed in.
- **Preserving the contradiction is the deliverable.** The correct output is not a resolution but both facts, sourced and dated, plus an explicit statement that reconciling them is the next session's empirical job.

---

## 5. Every Branch of the Plan's Central Question Needs a Route, Not an Enum Slot

> [!constraint] The diagnostic question
> **For each branch of the plan's central question, what concretely happens next?** If two branches answer "recorded as a finding and routed to the next sprint as hypothesis H-n" and the third answers "…it just gets written down", the third is unrouted regardless of how prominently it appears in the enum.

A plan invests its routing effort in the outcome it expects, and that investment is visible and reassuring: exact enum spellings mandated as literal strings in two task files, a greppable gate value, a named downstream consumer, a pre-written flag row. The unanticipated branch gets the same *nominal* enumeration and none of the *operational* wiring. **The asymmetry is invisible at review time because the enum looks complete** — all three values are named; only one has a destination.

The cost is concrete. The branch that fired did not merely fill a slot, it changed the shape of the downstream question from *"is the allowlist enforced?"* to *"why did this project measure 408 successful violating calls against an allowlist the vendor documents as enforced?"* — a different investigation, with candidate explanations (transcript mis-attribution, a spawn path applying a different frontmatter subset, version-dependent enforcement, an installed mirror diverging from the shipped definition) that the plan's sketched matrix does not test. An unrouted branch costs more than a missing paragraph: the downstream matrix tests a question that is no longer the question.

---

## 6. Invite the Contradiction, in the Prompt

> [!practice] One sentence is enough to invite it
> Agents will not volunteer a contradiction of the dispatcher unasked.
>
> ```
> At dispatch:  "A contradiction of a sibling task's conclusion is the most
>                valuable thing you can return."
> At repair:    "If the cause is something else, say so and report what it is."
> ```
>
> The first was in a re-dispatch that came back with three overturned conclusions. The second is what let a fixer refute the dispatcher's stated cause instead of building a repair on top of it.

---

## 7. When the Evidence Base Changes — Retract Explicitly, Stop the Primed Agent, Resume the Builder

> [!constraint] Three lifecycle calls that all follow from §1's write-once property
> - **Retract, do not merely append.** The re-dispatch that worked opened with the superseded prior quoted verbatim and labelled WRONG, then gave the corrected finding. Adding new inputs beside a stale prime leaves the agent to adjudicate its dispatcher, which it will not do.
> - **Stop a running agent whose premise has been refuted; do not let it finish "for reference."** Its output is not partially salvageable — the premise is diffused through the ranking, not isolated in one section. Stopping cost a few minutes of Opus; shipping would have ranked a *reporting* fix at the top of a problem that is measurably *load*, and aimed the next sprint at instrumenting a number instead of bounding a window. Re-dispatched over four inputs with the prime retracted, the agent returned the opposite headline and independently ranked three causes **no hypothesis had named** into the top three slots; accounting semantics landed at #8 of 8, contributing *zero* window tokens.
> - **Prefer resuming the agent that built the artifact over re-dispatching a fresh one.** It holds the row semantics the dispatcher does not, and that asymmetry is the whole reason its correction beat the dispatcher's guess.

**Audit primes at every reconciliation point, not only at dispatch.** The trigger is: a new evidence source lands, a task contradicts a sibling, or a gap statement is closed. Each of those is a moment where a premise written earlier may now be false and is still in force, because nothing retracts a premise except an explicit retraction.

---

## 8. Record the Refutation, and Keep the Real Defect the Wrong Diagnosis Found

> [!practice] The corrected causal account outlives the arithmetic that prompted it
> When a diagnosis is refuted, the corrected causal account is worth more than the arithmetic that prompted it — the account of three cluster-level rows plus two further prefix effects that cancel now stands in the artifact as a warning against prefix-keyed verification. And when a wrong diagnosis nonetheless surfaced a real defect, fix it on its own merits: the compressed rows were not the cause and *were* a genuine grain violation, so they were expanded anyway rather than dropped because the theory failed.

§3 and §8 both concern a refuted diagnosis and are deliberately separate. §3 is *how to write the instruction so the refutation is possible*. §8 is *what to do with the artifact once the refutation lands*. A merged section loses the second, which is the half that keeps a real defect from being dropped along with the wrong theory.

---

*Cross-reference: [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §1 (the quantitative half — withhold the figure) · [`verify-verdict-source.md`](verify-verdict-source.md) (the runner's side — a primed verdict is the case where recomputation against the primary source is least likely to happen; link, never merge) · [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.8 (spawn-prompt skeleton)*
