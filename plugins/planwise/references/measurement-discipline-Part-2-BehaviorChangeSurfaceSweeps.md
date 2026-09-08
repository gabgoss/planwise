---
description: Behavior-change surface sweeps — after a change lands, sweep the surfaces that describe and call it: structured manifest/schema fields (not just the prose beside them), the caller that routes a detection to its repair, a newly-reachable branch, the data-cleanup counterpart — the instruction that regenerates a defect, and the value FORM a migration must take — and the claim-truth counterpart: closing an item, retracting a finding, or deleting quoted prose each leave other artifacts asserting the old truth.
paths: {planwise_root}/{plans_dir}/**
---

# Measurement Discipline, Part 2 — Behavior-Change Surface Sweeps

**Purpose:** §8.8, split out of [measurement-discipline.md](measurement-discipline.md) when that file crossed the Read-tool token gate. §8.1–§8.7 stay on that anchor, which keeps the original filename; this half carries §8.8 and Reviewer Check 076 verbatim. Cite either half as `measurement-discipline.md §8.x` for §8.1–§8.7 and as this file for §8.8.

---

### 8.8 After a behavior change, sweep the surfaces that describe and call it

A behavior change lands on surfaces beyond the code that implements it. **The tests cover the code. Nothing covers the metadata that *describes* the code, or the document that *invokes* it.** Both can therefore be left asserting the old behavior with the suite fully green — and both are read as authoritative: the metadata by tooling and by the next author, the document by the user following it.

§8.7 asks whether a gate can fail. This section asks a prior question: whether the change was even applied everywhere it is stated. Sub-rules A–C are one sweep, in causal order — C only ever arises as a consequence of acting on B, so they are not separable. Sub-rules D and E are the same discipline turned on **data cleanup** rather than behavior change: where A–C ask which surfaces still *describe* the old behavior, D asks which surface is still *producing* the old data, and E asks whether the new data actually took the shape the destination scheme defines.

Sub-rules F–H turn it on a third subject: **a claim whose truth changed.** Closing an item, retracting a finding, and deleting a quoted sentence each falsify statements recorded elsewhere, and every one of those statements was correct when written — so no reviewer of those files flags anything. They are wrong only relative to a change made elsewhere, later.

> [!constraint] A — Update the field, not just the prose beside it
> WRONG — the fix updates the human-readable half and leaves the machine-readable half asserting the old behavior. The row now asserts two contradictory things about the same key, and the authoritative half is the false one:
> ```yaml
>   - id: <some_key>
>     <field>: <old_value>        # ← still says the old behavior
>     notes: >
>       … the commit point now rewrites this key in the SAME write …   # ← says the opposite
> ```
>
> CORRECT — the field moves too, a truthful value is **added** when none exists, and the siblings are swept:
> ```yaml
> # (enum gains a definition comment in the file's own style)
> #   <new_value>: <definition of what this actually means>
>
> <enum_key>: [<existing values>, <new_value>]
>
>   - id: <some_key>
>     <field>: <new_value>
>   - id: <paired_key>
>     <field>: <new_value>   # ← sibling audit: was false before this fix, too
> ```
>
> Three ordered steps:
>
> **(a) Find the field, not just the prose.** Grep the manifests, schemas and frontmatter for the artifact you changed, and read the **structured** values. Free-text `notes:` / `description:` are the easy half — they read as commentary and an author updates them by reflex. The enum, boolean or path-glob two lines above is the half that reads as authoritative to tooling and to the next author, and it is the half that gets left behind.
>
> **(b) If no legal value is true, add one — do not round to the nearest.** Check what consumes the field first: a value that is inert to code but wrong to a reader is a documentation defect; one that drives a loop is a runtime defect. Then add the value to the declared enum **and** write its definition comment in the file's established style. Picking the least-wrong existing value is not a smaller fix than adding one — it encodes a second, subtler lie in a field that now looks deliberately chosen.
>
> **(c) Audit every sibling row carrying the value you just abandoned.** The reason your row was wrong usually applies to its neighbours. **This is the step that pays.** A sibling written by the same mechanism can have been false since before your change existed — no current task owns it, no test covers it, and nothing but this sweep will surface it. Your fix did not cause it; your fix created the occasion to notice it.
>
> When nothing in code validates the field, verify it by hand:
> ```bash
> python -c "
> import yaml; d=yaml.safe_load(open('<manifest>',encoding='utf-8'))
> enum=set(d['<enum_key>'])
> print('off-enum:', [a['id'] for a in d['artifacts'] if a.get('<field>') not in enum] or 'NONE')
> print('grouped:', {v: [a['id'] for a in d['artifacts'] if a.get('<field>')==v] for v in enum})
> "
> ```
> The **grouped** half matters as much as the off-enum half. Off-enum catches a value that is illegal; grouped catches a value that is legal and false — it puts an inherited wrong value directly beside its correct peers, which is the only cheap way to see it.

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
> Fixing a gate per sub-rule B makes a dormant branch live. That is a **behavioral change to everything the branch touches** — the branch's age and the suite's green status say nothing about it, because until now it never ran.
>
> Before declaring it done, walk the branch line by line against every input the newly-routed caller can supply — flags, options, environment — and ask what the branch does with each. **Anything set up after the point where that branch returns is, by construction, not applied there.**
> ```python
>     if pinned_version == target_version:
>         # This branch is now reachable. Everything below the gate — the opt-in
>         # flag application, the backfills — never runs here. Anything a caller
>         # can pass must be honored on THIS path or explicitly declared a no-op.
>         toggled = bool(cfg.opt_in_flag) and _apply_opt_in(config_path)
> ```
>
> The mechanical check is a set difference — enumerate what the caller can request, enumerate what the branch performs before it returns, and subtract:
> ```bash
> # 1. what the caller can ask for: every flag/option the entry point accepts
> grep -nE 'add_argument|opt_in|--[a-z-]+' <entry_point> | sed 's/.*--//' | sort -u
> # 2. what the newly-live branch actually does before returning
> sed -n '<branch_start>,<return_line>p' <module> | grep -nE '_apply_|_backfill_|write|=' 
> ```
> A non-empty difference is either a bug or a decision that needs stating — never a silent no-op.

**Applies-to surface (sub-rules A–C).** Any change to behavior that a manifest, schema, frontmatter field or capability table also describes — **including when the field is documentation-only and no test can fail.** Any change pairing a new diagnostic with a new remediation. Any change relaxing a gate, guard or early return so a previously-dead branch begins executing. And any codebase where prose — a handler, a runbook, a documented command sequence — is the caller of record for a script: there the document's conditions must be edited in the same change as the code's, or the code's new capability is unreachable in practice.

> [!constraint] D — Grep for the instruction that regenerates the defect, not only for its instances
> A cleanup item enumerates **instances**: the records carrying the superseded form, the call sites using the removed API, the rows holding the stale value. Before executing one, sweep for the **instruction** — the template, seed, spec, handler, authoring reference, or root project file that still tells someone to produce the old form — and bring it into the item's scope. **A migration whose source keeps emitting the old form is not a fix; it is a pause.**
>
> Where the instruction lives is the operative detail, because it is never where the instances are. Instances sit in the data corpus; the instruction sits in a template, a seed, a handler, an authoring reference, or a root project file injected into every session. **Scoping the sweep to the corpus the item names is therefore precisely how the instruction is missed** — that corpus is the one place guaranteed not to contain it.
>
> WRONG — the sweep is scoped to the records the item enumerated, and the item closes on its own arithmetic:
> ```
> Grep  pattern='<old-key>'  path='<the corpus the item enumerated>'
> → 11 hits, all 11 migrated, done.
> ```
> CORRECT — sweep the whole repo, then triage every hit by whether it **stores** the old form or **mandates** it:
> ```
> Grep  pattern='<old-key>'  path='<repo root>'  output_mode='content'  -n=true
> → triage each hit:
>     an INSTANCE (a record carrying the old form)      → migrate; this is the item's stated scope
>     a MANDATE   (a live instruction to write it)      → fix HERE — it regenerates the defect
>     a TEMPLATE  (ships the old form to consumers)     → fix HERE — it regenerates it downstream too
>     a SPEC      (defines the old form as correct)     → deprecate or realign
> ```
>
> **A hit that instructs outranks a hit that merely stores.** Deferring the instruction to a follow-up does not split the work in half — it leaves a window in which the cleanup is actively being undone. The next write recreates a straggler, and the original item's acceptance criterion silently degrades from that moment on, having been true exactly once.
>
> **Corollary — deprecate rather than delete when the old form must stay readable.** Existing data still carries it, so the instruction becomes *"read this, never write it"*. That stops regeneration without breaking back-compatibility for records already written, and it keeps an account of a form the next reader will still encounter — which deleting the instruction outright would throw away.

> [!constraint] E — Migrate the value FORM, not just the key
> A spec that says *"move the value from the old key into the new one"* describes a **key** mapping and is silent on **shape**. Silence is not conformance. Read literally it is a two-key value swap — which satisfies the item's wording and every stated acceptance criterion while producing a field that no other record in the repo matches.
>
> Two cheap checks, both against live artifacts rather than the item's prose:
>
> 1. **Read the destination scheme's own definition** — the template, seed or spec that states what shape the field holds. If it defines the field as an id and the source values are paths, the transplant is wrong however faithfully it follows the wording.
> 2. **Read the records already written under the target scheme, and match them.** If the migrated rows will not look like their conformant peers, the migration is not finished.
>
> WRONG — the value is transplanted verbatim, and it was already rotting in the source:
> ```yaml
> # the destination scheme defines this field as an ID
> <new-key>: path/to/<record>.md     # transplanted verbatim — and ALREADY STALE:
>                                    # the record it names was archived and moved
> ```
> CORRECT — the value is normalised into the shape the destination scheme defines:
> ```yaml
> <new-key>: <RECORD-ID>             # the id form every conformant record already carries;
>                                    # survives the record moving, which is why the scheme chose it
> ```
>
> **Treat staleness in the source values as an argument for normalising rather than transplanting.** When the old form has already broken for part of the set under migration — 3 of 11 stored paths pointed at records that had since been archived — that is not an incidental data-quality nit to carry across faithfully. It is direct evidence, sitting in the very data being migrated, that the old form is the wrong carrier.
>
> Report the form change in the closeout, so the human sees the migration did more than the spec's literal wording. And note what the criteria cannot do for you: acceptance criteria written in terms of **key names** ("the value now sits in the new field") **pass on a nonconformant value form**. They cannot detect this class at all, so the two reads above are the only check there is.

**Applies-to surface (sub-rules D–E).** Any item whose scope is enumerated instances of a superseded form — a frontmatter-key migration, a renamed field, a deprecated API's call sites, a normalisation pass over archived records. The sweep for the instruction is part of executing such an item, not a follow-up to it.

> [!constraint] F — Closing an item is not complete until every artifact that recorded it open says otherwise
> **Writing a claim down is distributed. Changing its truth is centralized.** A good runner records an open item wherever a reader might need it, which is exactly the behaviour you want. Closing it is one edit, in one file, by whoever owns that file. Nothing in the close touches the recording sites, and nothing errors.
>
> Required close sequence:
>
> ```
> 1. BEFORE closing, Grep for the item's distinctive phrasings and list every site.
>    Do this FIRST — the phrasings are easiest to find while the open text is still in front of you.
> 2. Apply the substantive fix.
> 3. Sweep every site to RESOLVED, carrying the evidence (what was checked, against what,
>    and the outcome) — not merely deleting the sentence.
> 4. Re-run the Grep across the whole tree and confirm no live assertion survives.
>    Expect legitimate hits inside negations ("leaves NO open action item") and inside
>    labelled quotations in bookkeeping files; classify rather than blanket-fail.
> 5. Decrement any open-item tally the assertion fed, and if it reaches zero, say so explicitly.
> ```
>
> Step 4's classify-don't-blanket-fail clause is load-bearing. **A sweep that fails on its own negations trains readers to ignore it.**
>
> **These assertions are instructions to distrust, which is what raises this above tidiness.** One resolved item left three live instructions behind: an Absorption note ending *"a designer working this claim must read this note, not the canonical entry"*, a `### Merged` table row asserting an unverified condition, and a finding ending *"This is the one open action item this task creates."* The edit was routed to the file's owner and verified on disk the same session. All three statements became false, and none changed — so the register now routed a downstream designer **away** from a canonical entry that was in fact complete. That is strictly worse than a stale comment, which merely fails to help.
>
> **Keep the finding, change its status.** A cross-file constraint the decomposition could not satisfy is a real and reusable record, and deleting it loses the evidence that the limit exists. Flip OPEN → RESOLVED with the outcome, and state plainly when the premise turned out not to hold.
>
> **Verification corollary — an agent's idle notification is not a completion signal.** One sweep dispatch reported idle with the target file byte-identical to its pre-instruction size (186 lines / 16,924 bytes). After a second prompt it measured 186 / 18,046 with the edit present. Two readings survive that evidence — the edit had not been written when the check ran, or it was in flight with the reply dropped — and the orchestrator cannot distinguish them from outside, since both present as "idle notification, deliverable absent from disk". **That indistinguishability is what selects the corrective.** Resuming the SAME agent is correct under both readings: under the first it does the missing work, and under the second a competent runner answers "already applied" rather than double-applying. Dispatching a *fresh* agent is wrong under both, because it re-reads everything and may race or duplicate. So check disk, resume the same agent, verify the landed artifact afterward, and treat a dropped reply as expected rather than exceptional. The general liveness reading of an idle notification is [agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md); what is specific here is that this step is what makes step 3 auditable.

> [!constraint] G — A retraction belongs inline at every citation site, not only at the original claim
> A pointer of one clause — *"(justification superseded — see notice at §X)"* — is enough. What fails is placing it only where the claim was first made.
>
> One Master Plan appended a supersession notice directly under its Empirical Baseline table, retracting three findings. Elsewhere in the same file a Binding Constraints section cited those findings as live. The consuming task was scoped to read *"§Expected Output + §Binding Constraints"* — the retraction is in neither. Not hidden, not far away, just outside the two sections it was told to read. Two other retracted findings were cited by two further constraints, so the same trap was set three times over.
>
> **The tempting fix is wrong in the other direction.** When the retraction was routed in by hand, striking the whole constraint would have removed a requirement the new evidence makes *more* necessary:
>
> | Half of the constraint | Disposition |
> |---|---|
> | **Requirement** — fresh temp dir per case, with teardown | **SURVIVES, and is strengthened.** Nondeterminism makes contamination *worse*: a leftover config file deterministically suppresses the auto-init branch in the next case, converting a flaky branch into a silently-wrong one |
> | **Justification** — "a deterministic 10-file tree" | **RETRACTED.** 3 observations, 2 wrote the tree, 1 wrote nothing |
>
> **A retraction invalidates a premise, not necessarily the rule the premise was used to argue for.**
>
> Four further rules:
>
> - **When you retract a finding, `Grep` the document for its citations.** The retracting party is the only one who knows the retraction happened, and every downstream citation is a live claim until someone walks them.
> - **Separate the surviving requirement from the retracted justification explicitly, in a table**, stating each half's disposition. Nothing is then blanket-failed because its stated reason expired, and nothing is preserved silently as if nothing changed.
> - **A section-scoped Required Context is a blind-spot generator.** When a task is scoped to named sections, check whether anything *outside* those sections modifies what is *inside* them. That check belongs to whoever writes the Required Context, at scaffold time.
> - **A retracted premise cited by a passing gate makes the gate's green result meaningless while looking identical to a real pass.**

> [!constraint] H — Cite the load-bearing anchor, not the quotable prose
> ```
> WRONG — defend a decision with the sentence that reads best:
> "…and §8.1 calls Read-output line numbers 'decorative, not authoritative'"
>    ← deleted one sprint later by the row whose whole job was to bound it
>
> CORRECT — defend it with the normative clause, and name file + section so a reword is still findable:
> "…and §8.1's scoped MUST — 'A file's line count for a review finding MUST come
>  from `Bash` running `wc -l <path>`' — which the bounding row's paired gate asserts unchanged"
> ```
>
> **The two citations are not interchangeable, and the quotable one is the fragile one.** Quotable prose — the memorable closing sentence, the vivid phrase — is disproportionately likely to be the target of a later editing pass, precisely because vivid absolutes are what over-reach and get bounded. Here a sibling sprint **deleted the closing sentence by design** one day later: it was an unscoped absolute reaching past its own rule's scope, and bounding it was the entire point of that row. A closeout verifier grepping the flag's quoted evidence then gets 0 tree-wide — correct behaviour, reading as a vanished anchor. The dry, scoped MUST that reads like boilerplate is the load-bearing anchor and the one that survives.
>
> Four practical rules:
>
> - **Prefer the normative clause (MUST / MUST NOT) over the illustrative one.** Illustrative sentences are editorial. Normative clauses are contractual.
> - **Anchor by file + section number + heading, not by quoted string alone.** A section number survives a reword. A quoted string does not.
> - **When you delete or reword prose, `Grep` the open flags for it.** The deleting session is the only party that knows the deletion was intentional.
> - **Supersede, don't rewrite.** Append a supersession notice naming the stale citation, quoting the replacement wording verbatim, and confirming the conclusion still stands. Never edit another session's recorded flag — that destroys the record of what was known when. The sender-side form of this rule is [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4.E.
>
> **Reader-side rule: a citation returning 0 hits means "verify why", not "the justification collapsed."** That is the reading a closeout reconciliation session owes an upstream flag whose quoted evidence has vanished.

**Applies-to surface (sub-rules F–H).** Any close, retraction, or deletion that changes the truth of a claim other artifacts already recorded. F walks forward from a close to the sites that recorded the item open. G walks forward from a retraction to the citations that keep asserting it. H walks backward from a deletion to the flags that quoted the deleted prose. The three directions are distinct and a merged sweep will run only one of them.

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

*Cross-references: [measurement-discipline.md](measurement-discipline.md) (§8.1–§8.7 — the live-measurement and gate-integrity discipline this section builds on; split anchor, keeps the original filename), [verification-gates.md](verification-gates.md) (§1-§7 — cross-process/build/runtime gate discipline).*
