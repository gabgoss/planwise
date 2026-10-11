---
description: A definition is not a caller. Every presence gate — symbol exists, text is in the file, suite is green — stays green on behaviour that production never reaches, so a deliverable that adds a function, an optional parameter, a CLI flag, a config key, an event subscription or a guarded branch is terminal only when a production caller supplies the activating argument. Covers the call-site search that replaces the definition search, why the natural unit test is a false witness, the call-site quote the closing-sweep ledger owes per deliverable, why a runner's "dormant until a follow-up wires it" note is PARTIAL, never COMPLETE, and why a routed claim that a function, flag, script or writer already exists is grepped before it is written into a task as binding, and why a read-only reporter that predicts another command's behaviour calls that command's own predicate for every question it answers rather than re-deriving them. Consult before marking a behaviour-adding deliverable COMPLETE, before accepting a runner return that adds behaviour, when writing a closing-sweep ledger, before routing a "this is already wired" note into a task, and when authoring or accepting a doctor, lint, dry-run or status stage.
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Caller Before COMPLETE — a Definition Is Not a Caller

**Purpose:** Every gate the verification discipline prescribes measures **presence**: the symbol exists, the message text is in the file, the suite is green, lint is clean. None measures **reachability** — whether production ever executes the thing. Two deliverables landed in one session complete, correct, tested and lint-clean, and unable to run. The same gap opens from the other side: a routed note that says a function, flag, script or writer already exists is a claim about a past plan, and §4 covers it. The file also covers a reporter that predicts another command's behaviour, which must call that command's own predicate (§5).

**Read this when** you are about to mark COMPLETE a deliverable that adds a function, an optional parameter, a CLI flag, a config key, an event subscription or a guarded branch; when a runner's return adds such a behaviour; and when you write the closing-sweep deliverable ledger.

| Deliverable shape | How it landed | Why every presence gate stayed green |
|---|---|---|
| New behaviour behind an **optional parameter** | Implemented and unit-tested; both production call sites kept passing their old positional arguments | Symbol count ≥ 1 ✓, message text present ✓, suite green ✓ — all three measure the definition |
| New **CLI flag** | Handler function implemented and directly tested; never registered with the argument parser | Function exists ✓, its unit test passes ✓, the handler documents the flag ✓ — nothing invokes the CLI path |

Both were caught only because a runner volunteered a note. That is not a control: the same runner could have reported COMPLETE with every declared gate genuinely green, and the session would have shipped a documented flag no user can invoke and a diagnostic that never prints.

The structural cause is the task decomposition. A per-file `**Output:**` boundary is exactly the shape that separates a behaviour from the site that activates it: the definition sits inside one task's scope, the wiring sits in someone else's file, and the runner is correctly scope-bound and *cannot* fix it. Only whoever holds both sides can see the gap — so the gate lives at the orchestrator and closing-sweep layer, not in the task.

> [!constraint] The natural test hides the defect — order activation before test
> A test for behaviour behind an optional parameter **passes that parameter**, because that is how it reaches the code under test. It then goes green against a call shape production never uses: a passing test standing as evidence for dead code. Where one task authors the test and another must activate the behaviour, the dependency runs **activation → test**, so the test asserts the production call shape and covers the degraded branch only as an explicit contrast case.

---

## 1. The gate: assert a caller, not a definition

For every newly added function, optional parameter, CLI flag, config key, event subscription or guarded branch, assert that a **caller** exists — and that at least one caller supplies the **activating** argument. A default that no caller overrides is dead code wearing an API.

> [!constraint] Search the call site, not the definition
> WRONG — the definition search. It counts the `def` line and the test's own call, and both are present on unwired code:
> ```
> Grep  pattern='{symbol}'  path='{repo}'  output_mode='count'                                  # 2 → "present" ✓
> ```
> CORRECT — the call-site search, naming the activating argument or the registration, over production paths only:
> ```
> Grep  pattern='{symbol}\(.*{activating_arg}='  path='{repo}/{production_dir}'  output_mode='content'   # MUST return ≥ 1 site
> Grep  pattern="add_argument\('--{flag}'"       path='{repo}/{production_dir}'  output_mode='content'   # MUST return exactly 1 site
> ```
> The pattern carries the activating argument or the registration call, and the path excludes the test tree — a test supplying the argument is the false witness the constraint above describes.

Dry-run the gate in both directions before trusting it: it must **fire** on a deliberately unwired symbol (a function defined in a scratch module and called from nowhere returns 0 sites) and stay **silent** on a wired one (an existing function with a production caller returns ≥ 1). A reachability gate that has only ever been run against wired code has not been shown to discriminate. The instrument-level obligations — the gate can fail, does not fail correct work, sees the shape it counts — are [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) §10; this file adds the one question those gates do not ask.

---

## 2. The closing-sweep ledger quotes a call site per deliverable

The closing sweep's deliverable ledger answers *"invoked from where?"* for every deliverable that lands new behaviour, with a quoted production call site — `{file}:{line}` plus the calling expression. A deliverable whose only evidence is its own definition is **not terminal**: its row stays open, and the sweep either wires it inside the session or files the wiring as a BLOCKING follow-up that names the missing call. "Definition exists" is explicitly insufficient for a terminal disposition.

---

## 3. "Dormant until a follow-up wires it" is a BLOCKING classification

When a runner reports a deliverable complete but *"dormant until a follow-up task activates it"*, the orchestrator classifies the task **PARTIAL or BLOCKED — never COMPLETE**. Both instances above were resolvable inside the session in one to four lines, with the needed value already in scope at the call site. A deferred activation is indistinguishable from a dropped one once the session closes: the handoff has no owner and no gate.

> [!constraint] Wire it now, or block on it — never hand it off as done
> WRONG — runner: "implemented and tested; the two call sites still pass three positionals, so the hint stays dormant until a follow-up passes the fourth" → orchestrator records COMPLETE and moves on.
> CORRECT — orchestrator: "definition present, caller absent → PARTIAL; both call sites are in scope and the value is already bound there — add the argument now, re-run the call-site search, require ≥ 1" → the deliverable becomes terminal in the same session.

The runner-side statement of this rule is `agents/task-runner.md` §5.B; the orchestrator-side recompute is [agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.16.3.

---

## 4. A Routed Claim That Code Already Shipped Is Grepped Before It Is Written as Binding

> [!constraint] A routing note that says code exists is a claim about a past plan, not about the tree
> It decays like any recorded value. A rewritten task step is not shipped code. §1 ("The gate: assert a caller, not a definition") searches the call site when a deliverable is marked COMPLETE. This section applies the same search one step earlier, at the moment an orchestrator copies "already wired" into a task.

At a Phase-1 preflight, the orchestrator routed a front-door flag into the first task as a `[!binding]` spec delta. The delta said an `<N>`-way promotion-log append map was already wired into the plugin: "`<session>` wired this map into the plugin. Locate the shipped map with Grep." The orchestrator took that sentence from the earlier session's own routing note, which read "`<task>` Step 7 rewritten to the `<N>`-way map". The orchestrator never searched the scripts.

The first task's runner did search. It found no script that implements the map and no `<script>.py` at all. It documented the contract in the reference with a callout saying no script implements it yet. The orchestrator then had to correct the binding deltas already written into two further tasks. Otherwise both sweeps would have told the handlers and references to "name the function", and that function does not exist.

> [!constraint] Verify the claim against the code first
> WRONG — promote a routing note's wording into a binding fact:
> ```
> upstream note: "<task> Step 7 rewritten to the <N>-way map"
> -> binding delta: "<session> wired this map into the plugin; locate it with Grep"
> ```
> CORRECT — search the code, then write what the search found:
> ```
> Grep pattern='<map-name-a>|<map-name-b>' path='<plugin>/scripts'
> -> 0 hits outside the filename helper
> -> binding delta: "no script implements the map; state it as the reference's contract"
> ```

- **Search before you write "shipped" or "wired".** Before a task carries such a claim as binding, search the code for the symbol. Record the hit, or the zero, beside the claim.
- **Write "locate X" so an absent symbol is an expected branch.** A bare "locate X" makes the runner's absence finding look like the runner's error. Write: "locate X. If absent, state the contract and record that no script implements it."
- **Correct every task that received the claim.** A correction must reach each task that got the delta, not only the task that found the gap. Search the session folder for the claim's wording and fix every site.

**Applies to** the Phase-1 flag preflight in any delegated session. It applies to any spec delta that asserts a function, flag, script or writer exists. [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4 governs the receiver side of an inherited flag. This section is the sender's search.

---

## 5. A Read-Only Reporter Calls the Actor's Predicate for Every Question It Answers

> [!constraint] Two implementations of one predicate are a defect, even when each is locally correct
> This holds whenever a component's job is to predict another component's behaviour. Tests do not catch it, because each side's tests run against that side's own predicate. §1 ("The gate: assert a caller, not a definition") searches the call site of a new definition. This section applies the same search to a reporter: the call site that matters is the one that reaches the actor's own predicate.

A read-only check stage (`<reporter>`) reports on the two style rules that an upgrade command (`<actor>`) installs, refreshes and removes. Its whole value is to tell the user what the actor will do. At planning time the orchestrator pinned the reporter's states to the actor's helpers, but only some of them. "Copies that load" came from the actor's copy-search helper. "Carries edits" came from the sync's edit predicate. Everything else was re-derived inside the stage.

The suite passed (2497 tests), and each of the five new test classes caught a recorded mutation. A code review before commit then found five places where the reporter contradicted the actor on the same tree:

- **`OK` external.** The reporter counted any external copy. The actor blocks an install only on its scope-aware blocking-copy search, which ignores a project-tree copy at `user` scope. The reporter said "installs no second copy", and the next run installed one.
- **`CUSTOMIZED`.** The reporter used the sync's edit predicate, but the actor's reconcile reports through its installed-copy comparison. A stale shipped copy was `OK` in the reporter and "customized — kept" in the actor.
- **`off` keys.** The reporter skipped the copy search, so its token total was 0. The actor's own off branch printed "other copies still load".
- **`MISMATCH`.** The reporter always said "Run the upgrade". The actor keeps an edited or symlinked copy, so the user looped between the two commands.
- **Underneath (actor side).** The actor's own verdict helper stripped `paths:`, so under an `off` key it deleted a copy whose only edit was a `paths:` line. The reporter's paths-aware edit predicate called the same copy edited. The disagreement exposed a data-loss path in the actor itself.

The fix round made every reporter state call the actor's predicate. A second review then found that the `paths:` fix had moved the actor's own predicates apart. The reconcile line, the refresh condition and the copy classifier disagreed in two more places.

> [!constraint] The reporter asks the actor
> WRONG — the reporter re-derives the question:
> ```
> reporter: state = "OK" if len(external_copies) == 1      # any copy
> actor:    skip install if find_existing_copy(cfg, f)      # scope-aware
> ```
> CORRECT — the reporter asks the actor:
> ```
> reporter: state = "OK" if find_existing_copy(cfg, f) is not None else "MISSING"
> ```

Four operative points follow.

- **List the questions the report answers, and name the actor function behind each.** Examples: will the actor install, will it remove, is this copy edited, which copies load. Call that function for each question. Do not let a pin cover only some of the questions.
- **Test the agreement, not each side.** For each state, one test builds a tree, runs the actor's disposition and the reporter's state on it, and asserts that they agree. A mutation in either predicate then fails that test.
- **Treat a disagreement as a probe into the actor.** The reporter's stricter predicate exposed the actor's data-loss path. When the two disagree, decide which one is right before you align them.
- **After a fix to one shared predicate, `Grep` every other place that answers the same question.** The `paths:` fix in the verdict helper left the copy classifier, the refresh condition and the reconcile's handoff line answering the old way.

**Applies to** doctor, lint, `--dry-run`, status and preview commands: anything that reports what another command will do. It applies to plan pins of the form "use helper X for state Y". The pin must cover every state, not only the ones the author thought of first.

---

*Companion files: [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10 the instrument's proof obligations), [gate-change-vs-state-detecting.md](gate-change-vs-state-detecting.md) (§11 change- vs state-detecting shapes), [verification-gates.md](verification-gates.md) (the family index, whose §12 points to this file), [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §2 (per-unit assertions over aggregate counts), [templates/sprint-signoff.md](../templates/sprint-signoff.md) (the anchor a behaviour-adding criterion carries).*
