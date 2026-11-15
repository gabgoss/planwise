---
description: Behavior-change surface sweeps — after a change lands, sweep the surfaces that describe and call it: structured manifest/schema fields (not just the prose beside them), the caller that routes a detection to its repair, a newly-reachable branch, the data-cleanup counterpart — the instruction that regenerates a defect, and the value FORM a migration must take — and the claim-truth counterpart: closing an item, retracting a finding, or deleting quoted prose each leave other artifacts asserting the old truth — and the re-key counterpart: when a rule is re-keyed, enumerate its consumers by medium, because code that calls the shared function inherits the change and prose that restates the rule does not — and the module-split counterpart: a consumer census covers prose (a handler or reference that tells an agent to call `module.name(...)` is a consumer) and keeps every attribute the monolith bound, imported names included.
consult-when: A behavior change has landed, an item is closed or a finding retracted, a rule is re-keyed, or a module is split — sweep the structured manifest and schema fields, the caller that routes a detection to its repair, the newly reachable branch and the data-cleanup counterpart, find the other artifacts that still assert the old truth, enumerate a re-keyed rule's consumers by medium, and cover handler and reference prose in a module split's consumer census, keeping every attribute the monolith bound; carries §8.8 of `measurement-discipline.md`
paths: {planwise_root}/{plans_dir}/**
---

# Measurement Discipline, Part 2 — Behavior-Change Surface Sweeps

**Purpose:** §8.8, split out of [measurement-discipline.md](measurement-discipline.md) when that file crossed the Read-tool token gate. §8.1–§8.7 stay on that anchor, which keeps the original filename; this half carries §8.8 and Reviewer Check 076 verbatim. Cite either half as `measurement-discipline.md §8.x` for §8.1–§8.7 and as this file for §8.8.

---

### 8.8 After a behavior change, sweep the surfaces that describe and call it

A behavior change lands on surfaces beyond the code that implements it. **The tests cover the code. Nothing covers the metadata that *describes* the code, or the document that *invokes* it.** Both can be left asserting the old behavior with the suite fully green. Both are read as authoritative: the metadata by tooling and by the next author, the document by the user following it.

§8.7 asks whether a gate can fail. This section asks a prior question: whether the change was applied everywhere it is stated. The ten sub-rules turn one sweep on five subjects:

- **A–C, a behavior change.** They are one sweep, in causal order. C arises only as a consequence of acting on B.
- **D–E, a data cleanup.** D asks which surface is still *producing* the old data. E asks whether the new data took the shape the destination scheme defines.
- **F–H, a claim whose truth changed.** Closing an item, retracting a finding and deleting a quoted sentence each falsify statements recorded elsewhere. Each statement was correct when written, so no reviewer of those files flags anything.
- **I, a rule re-keyed from one source to another.** Its consumers sit in two media. Code that calls the shared function inherits the change, and prose that restates the rule does not.
- **J, a module split into a facade plus siblings.** The census of names the facade must keep resolving is itself a sweep, and a census read from code alone is too small.

> [!constraint] A — Update the field, not just the prose beside it
> **Rule.** When a change alters behavior that a manifest, schema or frontmatter field describes, move the structured value too, not only the free-text `notes:` or `description:` beside it. A row whose prose was fixed and whose field was not asserts two contradictory things, and the authoritative half is the false one. Three ordered steps:
>
> 1. **Find the field, not just the prose.** Search the manifests, schemas and frontmatter for the artifact you changed, and read the **structured** values. The enum, boolean or path-glob is the half that tooling and the next author read as authoritative, and it is the half that gets left behind.
> 2. **If no legal value is true, add one — do not round to the nearest.** Check what consumes the field first. A value that is inert to code but wrong to a reader is a documentation defect. A value that drives a loop is a runtime defect. Then add the value to the declared enum **and** write its definition comment in the file's established style. Picking the least-wrong existing value encodes a second, subtler lie in a field that now looks deliberately chosen.
> 3. **Audit every sibling row carrying the value you just abandoned.** The reason your row was wrong usually applies to its neighbours. **This is the step that pays.** A sibling can have been false since before your change existed, and nothing but this sweep will surface it.
>
> When nothing in code validates the field, check it by hand in two halves. **Off-enum** catches a value that is illegal. **Grouped** lists each legal value beside the rows that carry it, which catches a value that is legal and false. For the plugin's own `manifests/artifacts.yaml`, `tests/test_artifacts_manifest.py` pins the enum half. No test pins the grouped half, so it stays a check by hand.

> [!constraint] B — A detection plus a repair is not a remediation until something routes between them
> Whenever a change adds "X detects a bad state" and "Y can fix it", the deliverable is **not done** until the path from X's recommendation to Y's execution has been traced end to end and shown to be walkable. State the trace explicitly. Do not infer it from the fact that both halves exist and both are tested — that is exactly the evidence that is available when the loop is still open.
>
> **Where the caller is a document** — a handler, a runbook, a README command sequence — the document is part of the change surface, and its gate conditions are as load-bearing as an `if`. A prose gate that exits on the very condition the new repair path exists to serve is a dead end that no test can fail: the user is told they are already fine and left broken, twice.
>
> WRONG — the gate exits on the condition the repair serves, and a nearby note merely *describes* the capability:
> ```
> > If `pinned == shipped` → report "already up to date" and exit.
> …
> > [!practice] A stale root is upgrade-indicating
> > …re-running the script resolves the mismatch…      ← nothing routes here
> ```
>
> CORRECT — the gate itself carries the routing, and names what is skipped and why:
> ```
> > If `pinned == shipped` **and** the stored value matches the live one → report and exit.
> > If `pinned == shipped` **but** the stored value differs → do NOT exit; skip the
> >   comparison stages (nothing changed to compare) and run the writer invocation,
> >   which repairs the value on its own. Report it as a repair, not a version change.
> ```

> [!constraint] C — A previously-unreachable branch is unproven code, regardless of its age or test count
> Fixing a gate per sub-rule B makes a dormant branch live. That is a **behavioral change to everything the branch touches**. The branch's age and the suite's green status say nothing about it, because until now it never ran.
>
> Before declaring it done, walk the branch line by line against every input the newly-routed caller can supply — flags, options, environment — and ask what the branch does with each. **Anything set up after the point where that branch returns is, by construction, not applied there.** Anything a caller can pass must be honored on that path or explicitly declared a no-op.
>
> The mechanical check is a set difference. Enumerate what the caller can request, enumerate what the branch performs before it returns, and subtract:
> ```
> Grep  pattern='add_argument|opt_in|--[a-z-]+'  path='<entry_point>'  output_mode='content'   # 1. what the caller can ask for
> Read  file_path='<module>'  offset=<branch_start>  limit=<branch_length>                      # 2. what the branch does before returning
> ```
> A non-empty difference is either a bug or a decision that needs stating — never a silent no-op.

**Applies-to surface (sub-rules A–C).** Any change to behavior that a manifest, schema, frontmatter field or capability table also describes — **including when the field is documentation-only and no test can fail.** Any change pairing a new diagnostic with a new remediation. Any change relaxing a gate, guard or early return so a previously-dead branch begins executing. And any codebase where prose — a handler, a runbook, a documented command sequence — is the caller of record for a script: there the document's conditions must be edited in the same change as the code's, or the code's new capability is unreachable in practice.

> [!constraint] D — Grep for the instruction that regenerates the defect, not only for its instances
> A cleanup item enumerates **instances**: the records carrying the superseded form, the call sites using the removed API, the rows holding the stale value. Before executing one, sweep for the **instruction** — the template, seed, spec, handler, authoring reference, or root project file that still tells someone to produce the old form — and bring it into the item's scope. **A migration whose source keeps emitting the old form is not a fix. It is a pause.**
>
> Instances sit in the data corpus. The instruction sits in a template, a seed, a handler, an authoring reference, or a root project file injected into every session. **Scoping the sweep to the corpus the item names is therefore precisely how the instruction is missed.** That corpus is the one place guaranteed not to contain it.
>
> Run the `Grep` over the whole repository, not over the corpus the item enumerated. Then triage every hit by whether it **stores** the old form or **mandates** it:
>
> | Hit | Disposition |
> |---|---|
> | an INSTANCE (a record carrying the old form) | migrate. This is the item's stated scope |
> | a MANDATE (a live instruction to write it) | fix here. It regenerates the defect |
> | a TEMPLATE (ships the old form to consumers) | fix here. It regenerates the defect downstream too |
> | a SPEC (defines the old form as correct) | deprecate or realign |
>
> **A hit that instructs outranks a hit that merely stores.** Deferring the instruction to a follow-up leaves a window in which the cleanup is actively being undone. The next write recreates a straggler, and the item's acceptance criterion silently degrades, having been true exactly once.
>
> **Corollary — deprecate rather than delete when the old form must stay readable.** Existing data still carries it, so the instruction becomes *"read this, never write it"*. That stops regeneration without breaking records already written, and it keeps an account of a form the next reader will still encounter.

> [!constraint] E — Migrate the value FORM, not just the key
> A spec that says *"move the value from the old key into the new one"* describes a **key** mapping and is silent on **shape**. Silence is not conformance. A verbatim transplant satisfies the item's wording and every stated acceptance criterion while producing a field that no other record in the repo matches.
>
> Two cheap checks, both against live artifacts rather than the item's prose:
>
> 1. **Read the destination scheme's own definition** — the template, seed or spec that states what shape the field holds. If it defines the field as an id and the source values are paths, the transplant is wrong however faithfully it follows the wording.
> 2. **Read the records already written under the target scheme, and match them.** If the migrated rows will not look like their conformant peers, the migration is not finished.
>
> **Treat staleness in the source values as an argument for normalising rather than transplanting.** When the old form has already broken for part of the set (3 of 11 stored paths named records that had since been archived), the data under migration is direct evidence that the old form is the wrong carrier.
>
> Report the form change in the closeout. Acceptance criteria written in terms of **key names** ("the value now sits in the new field") **pass on a nonconformant value form**. They cannot detect this class at all, so the two reads above are the only check there is.

**Applies-to surface (sub-rules D–E).** Any item whose scope is enumerated instances of a superseded form — a frontmatter-key migration, a renamed field, a deprecated API's call sites, a normalisation pass over archived records. The sweep for the instruction is part of executing such an item, not a follow-up to it.

> [!constraint] F — Closing an item is not complete until every artifact that recorded it open says otherwise
> **Writing a claim down is distributed. Changing its truth is centralized.** A good runner records an open item wherever a reader might need it. Closing it is one edit, in one file, by whoever owns that file. Nothing in the close touches the recording sites, and nothing errors.
>
> Required close sequence:
>
> 1. Before closing, `Grep` for the item's distinctive phrasings and list every site. Do this first, while the open text is still in front of you.
> 2. Apply the substantive fix.
> 3. Sweep every site to RESOLVED, carrying the evidence (what was checked, against what, and the outcome), not merely deleting the sentence.
> 4. Re-run the `Grep` across the whole tree and confirm no live assertion survives. Expect legitimate hits inside negations ("leaves NO open action item") and inside labelled quotations in bookkeeping files. Classify them rather than blanket-fail. **A sweep that fails on its own negations trains readers to ignore it.**
> 5. Decrement any open-item tally the assertion fed, and if it reaches zero, say so explicitly.
>
> **These assertions are instructions to distrust, which is what raises this above tidiness.** A stale note that tells a designer to read it instead of the canonical entry routes that designer **away** from an entry that is in fact complete. That is strictly worse than a stale comment, which merely fails to help.
>
> **Keep the finding, change its status.** Deleting a finding loses the evidence that the limit existed. Flip OPEN → RESOLVED with the outcome, and state plainly when the premise turned out not to hold.
>
> **Verification corollary — an agent's idle notification is not a completion signal.** A sweep dispatch can report idle with its target file unchanged on disk. Two readings fit: the edit was not written yet, or it was in flight with the reply dropped. The orchestrator cannot tell them apart from outside. Resuming the SAME agent is correct under both readings, and dispatching a *fresh* agent is wrong under both, because it may race or duplicate. So check disk, resume the same agent, and verify the landed artifact afterward. The general liveness reading of an idle notification is [agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md); what is specific here is that this step is what makes step 3 auditable.

> [!constraint] G — A retraction belongs inline at every citation site, not only at the original claim
> A pointer of one clause — *"(justification superseded — see notice at §X)"* — is enough. What fails is placing it only where the claim was first made. A task scoped to read named sections then reads a live citation of the finding, with the retraction outside the sections it was told to read.
>
> **The tempting fix is wrong in the other direction.** Striking a whole constraint that cited a retracted finding can remove a requirement the new evidence makes *more* necessary. **A retraction invalidates a premise, not necessarily the rule the premise was used to argue for.**
>
> Four further rules:
>
> - **When you retract a finding, `Grep` the document for its citations.** The retracting party is the only one who knows the retraction happened, and every downstream citation is a live claim until someone walks them.
> - **Separate the surviving requirement from the retracted justification explicitly, in a table**, stating each half's disposition. Nothing is then blanket-failed because its stated reason expired, and nothing is preserved silently as if nothing changed.
> - **A section-scoped Required Context is a blind-spot generator.** When a task is scoped to named sections, check whether anything *outside* those sections modifies what is *inside* them. That check belongs to whoever writes the Required Context, at scaffold time.
> - **A retracted premise cited by a passing gate makes the gate's green result meaningless while looking identical to a real pass.**

> [!constraint] H — Cite the load-bearing anchor, not the quotable prose
> **Rule.** Defend a decision with the normative clause, and name file + section, so a reword is still findable. Do not defend it with the sentence that reads best. A citation of §8.1's scoped MUST survives. A quote of that section's vivid closing sentence does not, because a later pass deleted that sentence by design.
>
> **The two citations are not interchangeable, and the quotable one is the fragile one.** Vivid absolutes over-reach and get bounded, so quotable prose is disproportionately likely to be the target of a later editing pass. A closeout verifier grepping a flag's quoted evidence then gets 0 tree-wide: correct behaviour, reading as a vanished anchor. The dry, scoped MUST that reads like boilerplate is the load-bearing anchor and the one that survives.
>
> Four practical rules:
>
> - **Prefer the normative clause (MUST / MUST NOT) over the illustrative one.** Illustrative sentences are editorial. Normative clauses are contractual.
> - **Anchor by file + section number + heading, not by quoted string alone.** A section number survives a reword. A quoted string does not. A `§N` anchor is also the form `scripts/check_section_citations.py` checks: it reports each `§N` citation that no longer resolves.
> - **When you delete or reword prose, `Grep` the open flags for it.** The deleting session is the only party that knows the deletion was intentional.
> - **Supersede, don't rewrite.** Append a supersession notice naming the stale citation, quoting the replacement wording verbatim, and confirming the conclusion still stands. Never edit another session's recorded flag — that destroys the record of what was known when. The sender-side form of this rule is [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4.E.
>
> **Reader-side rule: a citation returning 0 hits means "verify why", not "the justification collapsed."** That is the reading a closeout reconciliation session owes an upstream flag whose quoted evidence has vanished.

**Applies-to surface (sub-rules F–H).** Any close, retraction, or deletion that changes the truth of a claim other artifacts already recorded. F walks forward from a close to the sites that recorded the item open. G walks forward from a retraction to the citations that keep asserting it. H walks backward from a deletion to the flags that quoted the deleted prose. The three directions are distinct and a merged sweep will run only one of them.

> [!constraint] I — When a rule is re-keyed, enumerate its consumers by medium
> **Rule.** When a rule is re-keyed (a scoring factor, routing signal, status enum or validation rule now reads one source instead of another), list every consumer of the rule before the edit, and split the list by medium. The two media propagate the change differently. Code that calls the shared function inherits it. Prose that restates the rule inherits nothing.
>
> Three parts to the method:
>
> - **Code that calls the shared function inherits the change.** Verify it once with a fixture. Pin it with a regression test, because "inherits" is a claim about the call graph, and a later refactor can break it silently. The test asserts that the result moves with the new source field.
> - **Prose that restates the rule does not inherit anything.** A template line, a handler step, a backlog item's signal definition: each is a copy of the old rule that outlives the edit. Each one is a coordination flag to its owner. The flag must name the replacement (the resolver, its resolution order, the comparison) so the owner adopts it instead of re-deriving it.
> - **Measure the population the old rule was mis-scoring before retiring it.** Build a per-item delta table, and predict every row of it. The count is often the strongest argument for the re-key, and it is invisible until the table exists. It is also the number the next cutover audit has to explain.
>
> **Relationship to the neighbours.** Sub-rules A–E sweep the surfaces that describe and call a changed behavior. This sub-rule adds the split by medium and the regression test for the inheriting code path. [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) covers counts, section numbers and enum members bound to many sites.

**Applies-to surface (sub-rule I).** Any scoring weight, routing signal, status enum or validation rule that is defined in one function and restated in templates, handler prose, agent instructions or backlog items. The definition is one consumer. The restatements are the ones that drift.

> [!constraint] J — A module split's consumer census covers prose, and keeps every attribute the monolith bound
> **Rule.** A markdown handler or reference that tells an agent to run `module.name(...)` is a consumer of the module, exactly like a Python import. A census taken over `.py` files alone under-counts the surface. A parity gate built on that census reports N of N and passes over a set that is too small.
>
> Two operative points:
>
> - **Census every surface that can call the module.** Cover scripts, tests, handlers, references, templates and manifests. Include every call form: `from m import x`, `import m as alias` followed by `alias.x`, and `m.x` written in prose or in a `python -c 'import m; m.f()'` recipe.
> - **Preserve the monolith's full attribute set, not only the names it defined.** A name the old module imported is still an attribute consumers can reach. The facade re-exports it unless a census proves no consumer uses it.
>
> The census is every top-level name the pre-split module bound (defined or imported), united with the module calls written in every prose surface. The gate passes when every census name resolves on the facade, plus a shipped test that pins each handler-cited name. In the plugin, `tests/test_module_call_resolution.py` resolves every `module.name(...)` call that `handlers/` and `references/` write.
>
> **Relationship to sub-rule I.** I splits the consumers of a re-keyed rule by medium. J applies the same split to a moved module: code that imports it is one medium, and prose that calls it is the other.

**Applies-to surface (sub-rule J).** Any split of a module into a facade plus siblings, where documentation directs an agent or user to call module attributes. It applies most to plugin handlers, which are prose the agent executes.

#### Reviewer Check 076 — Detection + Repair With No Routing Deliverable

- **Severity / Role / Type:** WARNING | Plan Reviewer | NEW
- **What:** When a plan's deliverables include BOTH a new diagnostic (a check, warning, doctor stage, lint, drift detector) AND a new repair path (a fixer, migration, self-heal, reconcile-on-consent branch), it MUST also carry a deliverable that edits the **caller** which routes from the diagnostic's recommendation to the repair's execution. Without it, both halves ship, both are tested, the suite is green — and the loop is still open: the diagnostic's advice is a dead end. **The caller is frequently a document**, not code. Where a handler, runbook or documented command sequence is the caller of record, its gate conditions are as load-bearing as an `if`, and a prose gate that exits on the very condition the repair path serves cannot be caught by any test. A secondary signal: a plan that makes a previously-unreachable branch live without a deliverable auditing that branch against every input the newly-routed caller can supply — the branch's age and test count are not evidence, since until now it never ran.
- **Detection:**
  1. Classify each deliverable as diagnostic (detects/reports a bad state), repair (corrects it), or routing (connects a recommendation to an invocation).
  2. If the plan has ≥1 diagnostic and ≥1 repair but zero routing deliverables → WARNING.
  3. Where a routing deliverable exists, check it names the caller **and** its gate condition. A deliverable that only adds a note *describing* the repair capability alongside an unchanged gate does not route — flag it.
  4. Check the handler / runbook / command-sequence docs among the plan's touched files. If the documented flow exits early on the state the repair addresses and no deliverable edits that gate → WARNING.
  5. If any deliverable relaxes a gate, guard or early return so a dormant branch begins executing, require a deliverable that walks that branch against the caller-suppliable inputs (flags, options, environment). Anything set up after the branch's return point is not applied there. Absent → WARNING.
- **Finding template:**
```
[WARNING] Detection and repair ship with nothing routing between them
File: {plan or sprint file path} | Location: Deliverables / Sprint scope
Issue: Plan adds {diagnostic} and {repair} but no deliverable edits the caller ({handler|runbook|entry point}) that routes between them; documented flow exits on {condition} — the repair path is unreachable and the diagnostic's recommendation is a dead end
Fix: Add a deliverable editing the caller's gate to route the detected state to the repair (naming what is skipped and why), and audit the newly-reachable branch against every caller-suppliable input per references/measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md §8.8 | Confidence: MEDIUM
```

---

*Cross-references: [measurement-discipline.md](measurement-discipline.md) (§8.1–§8.7 — the live-measurement and gate-integrity discipline this section builds on; split anchor, keeps the original filename), [gate-runtime-boundary-evidence.md](gate-runtime-boundary-evidence.md) and [gate-exit-verdict-and-smoke-reports.md](gate-exit-verdict-and-smoke-reports.md) (the former `verification-gates.md` §1-§7 — cross-process/build/runtime gate discipline).*
