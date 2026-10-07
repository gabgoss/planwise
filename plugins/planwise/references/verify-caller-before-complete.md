---
description: A definition is not a caller. Every presence gate — symbol exists, text is in the file, suite is green — stays green on behaviour that production never reaches, so a deliverable that adds a function, an optional parameter, a CLI flag, a config key, an event subscription or a guarded branch is terminal only when a production caller supplies the activating argument. Covers the call-site search that replaces the definition search, why the natural unit test is a false witness, the call-site quote the closing-sweep ledger owes per deliverable, and why a runner's "dormant until a follow-up wires it" note is PARTIAL, never COMPLETE. Consult before marking a behaviour-adding deliverable COMPLETE, before accepting a runner return that adds behaviour, and when writing a closing-sweep ledger.
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Caller Before COMPLETE — a Definition Is Not a Caller

**Purpose:** Every gate the verification discipline prescribes measures **presence**: the symbol exists, the message text is in the file, the suite is green, lint is clean. None measures **reachability** — whether production ever executes the thing. Two deliverables landed in one session complete, correct, tested and lint-clean, and unable to run.

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

Dry-run the gate in both directions before trusting it: it must **fire** on a deliberately unwired symbol (a function defined in a scratch module and called from nowhere returns 0 sites) and stay **silent** on a wired one (an existing function with a production caller returns ≥ 1). A reachability gate that has only ever been run against wired code has not been shown to discriminate. The instrument-level obligations — the gate can fail, does not fail correct work, sees the shape it counts — are [verification-gates.md](verification-gates.md) §10; this file adds the one question those gates do not ask.

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

*Companion files: [verification-gates.md](verification-gates.md) (§10 the instrument's proof obligations, §11 change- vs state-detecting shapes, §12 the pointer to this file), [verification-task-authoring.md](verification-task-authoring.md) (per-unit assertions over aggregate counts), [templates/sprint-signoff.md](../templates/sprint-signoff.md) (the anchor a behaviour-adding criterion carries).*
