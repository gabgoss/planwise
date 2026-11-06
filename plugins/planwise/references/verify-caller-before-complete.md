---
description: A definition is not a caller. Every presence gate — symbol exists, text is in the file, suite is green — stays green on behaviour that production never reaches, so a deliverable that adds a function, an optional parameter, a CLI flag, a config key, an event subscription or a guarded branch is terminal only when a production caller supplies the activating argument. Covers the call-site search that replaces the definition search, why the natural unit test is a false witness, the call-site quote the closing-sweep ledger owes per deliverable, why a runner's "dormant until a follow-up wires it" note is PARTIAL, never COMPLETE, and why a routed claim that a function, flag, script or writer already exists is grepped before it is written into a task as binding, and why a read-only reporter that predicts another command's behaviour calls that command's own predicate for every question it answers rather than re-deriving them, and why a task that adds a parameter, flag or field derives its Output line from a recorded census of the definition site, callers, tests and documents, and why a task that edits an artifact a test pins owns those pin tests. Consult before marking a behaviour-adding deliverable COMPLETE, before accepting a runner return that adds behaviour, when writing a closing-sweep ledger, before routing a "this is already wired" note into a task, when authoring or accepting a doctor, lint, dry-run or status stage, and when writing the Output line of a task that adds a parameter, flag or field.
consult-when: About to mark COMPLETE a deliverable that adds a function, optional parameter, CLI flag, config key or guarded branch, accepting a runner return that adds one, or writing the closing-sweep ledger — a definition is not a caller: search the production call site for the activating argument, quote it per deliverable, and treat "dormant until a follow-up wires it" as PARTIAL, and grep a routed claim that code already shipped before it is binding, and have a read-only reporter (doctor, lint, dry-run, status) call the actor's own predicate for every question it answers (§5), and derive the Output line of a task that adds a parameter, flag or field or changes a shared side effect from a recorded census of its definition site, callers, tests and describing documents, and put the tests that pin an edited artifact's shape in the same task's write-set, Required Context and test gate (§6)
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Caller Before COMPLETE — a Definition Is Not a Caller

**Purpose:** Every gate the verification discipline prescribes measures **presence**: the symbol exists, the message text is in the file, the suite is green, lint is clean. None measures **reachability**: whether production ever executes the thing. A deliverable can land complete, correct, tested and lint-clean, and still be unable to run. §1 to §3 close that gap at the caller. §4 covers a routed note that says code already exists. §5 covers a reporter that predicts another command's behaviour. §6 covers the census that makes a task's `**Output:**` line match the files the live tree forces in.

**The gate lives above the task.** A per-file `**Output:**` boundary separates a behaviour from the site that activates it. The definition sits inside one task's scope, and the wiring sits in someone else's file. The runner is correctly scope-bound and cannot fix the gap. Only whoever holds both sides can see it, so the gate lives at the orchestrator and closing-sweep layer.

**The natural test hides the defect, so order activation before test.** A test for behaviour behind an optional parameter passes that parameter, so it goes green against a call shape production never uses. Where one task authors the test and another must activate the behaviour, the dependency runs **activation → test**. The test then asserts the production call shape and covers the degraded branch only as an explicit contrast case.

---

## 1. The gate: assert a caller, not a definition

For every newly added function, optional parameter, CLI flag, config key, event subscription or guarded branch, assert that a **caller** exists, and that at least one caller supplies the **activating** argument. A default that no caller overrides is dead code wearing an API.

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
> The path excludes the test tree, because a test supplying the argument is a false witness.

Dry-run the gate in both directions before trusting it: it must **fire** on a deliberately unwired symbol and stay **silent** on a wired one. The instrument-level obligations are [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) §10.

`scripts/check_symbol_callers.py` runs this search over the symbols a change adds and prints each symbol with zero call sites. Matching the activating argument stays heuristic, so the script reports and never decides COMPLETE alone.

---

## 2. The closing-sweep ledger quotes a call site per deliverable

The closing sweep's deliverable ledger answers *"invoked from where?"* for every deliverable that lands new behaviour, with a quoted production call site: `{file}:{line}` plus the calling expression. A deliverable whose only evidence is its own definition is **not terminal**: its row stays open, and the sweep either wires it inside the session or files the wiring as a BLOCKING follow-up that names the missing call. "Definition exists" is explicitly insufficient for a terminal disposition.

> [!constraint] Quote the call, not the definition
> WRONG — the row's only evidence is the definition, and the row closes:
> ```
> | adds --export flag | scripts/report_cli.py:88 `def handle_export(args):` | terminal |
> ```
> CORRECT — the row quotes where production invokes the behaviour:
> ```
> | adds --export flag | scripts/report_cli.py:41 `parser.add_argument('--export', action='store_true')` | terminal |
> ```

`scripts/check_sweep_ledger.py` lists each behaviour-adding ledger row that lacks the `file:line` or the calling expression.

---

## 3. "Dormant until a follow-up wires it" is a BLOCKING classification

When a runner reports a deliverable complete but *"dormant until a follow-up task activates it"*, the orchestrator classifies the task **PARTIAL or BLOCKED — never COMPLETE**. In the two recorded instances, the fix took one to four lines inside the session, with the needed value already in scope at the call site. A deferred activation is indistinguishable from a dropped one once the session closes: the handoff has no owner and no gate.

> [!constraint] Wire it now, or block on it — never hand it off as done
> WRONG — runner: "implemented and tested; the two call sites still pass three positionals, so the hint stays dormant until a follow-up passes the fourth" → orchestrator records COMPLETE and moves on.
> CORRECT — orchestrator: "definition present, caller absent → PARTIAL; both call sites are in scope and the value is already bound there — add the argument now, re-run the call-site search, require ≥ 1" → the deliverable becomes terminal in the same session.

The runner-side statement of this rule is `agents/task-runner.md` §5.B; the orchestrator-side recompute is [agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.16.3. `scripts/scan_runner_disclosures.py` flags a COMPLETE status block that claims the work is dormant, not yet wired or waiting on a follow-up.

---

## 4. A Routed Claim That Code Already Shipped Is Grepped Before It Is Written as Binding

A routing note that says code exists is a claim about a past plan, not about the tree. It decays like any recorded value. A rewritten task step is not shipped code. §1 ("The gate: assert a caller, not a definition") searches the call site when a deliverable is marked COMPLETE. This section applies the same search one step earlier, at the moment an orchestrator copies "already wired" into a task.

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

Two implementations of one predicate are a defect, even when each is locally correct. This holds whenever a component's job is to predict another component's behaviour. Tests do not catch it, because each side's tests run against that side's own predicate. §1 ("The gate: assert a caller, not a definition") searches the call site of a new definition. This section applies the same search to a reporter: the call site that matters is the one that reaches the actor's own predicate.

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
- **Treat a disagreement as a probe into the actor.** A reporter's stricter predicate can expose a defect in the actor, including a data-loss path. When the two disagree, decide which one is right before you align them.
- **After a fix to one shared predicate, `Grep` every other place that answers the same question.** A fix to one helper can move it apart from the other predicates that answer that question.

**Applies to** doctor, lint, `--dry-run`, status and preview commands: anything that reports what another command will do. It applies to plan pins of the form "use helper X for state Y". The pin must cover every state, not only the ones the author thought of first.

---

## 6. A Task That Adds a Parameter, Flag or Field Derives Its Output Line From a Change-Surface Census

An `**Output:**` line is the author's decomposition of the change. The live tree decides which files the change really touches. A line written from the design alone omits every file the tree forces in. A gate that counts changed files against the line ("exactly N changed") then false-fails correct work. A rule that exempts every path outside the line hides the omission.

**Trigger.** The task adds a parameter, flag or field, or changes a shared function's side effect (it now starts a process, writes a file or makes a paid call).

**The census.** Before writing the Output line, run four searches against the live tree. Record each search and its hits in the task's Change-Surface Census section (`templates/task-file.md`):

| Surface | Search | Easy to miss |
|---|---|---|
| Definition site | `Grep` for where the symbol or type is defined | A dataclass or schema that lives in a different module than the one the task edits |
| Callers | `Grep` production paths for each call site | A second call site that keeps passing the old arguments |
| Tests that reach it | `Grep` the test tree for the symbol and for the folder it globs. Also `Grep` for the pin helper or pin test-class name and keep the files that name the edited artifact | Existing tests that now start a real process, a test that parametrizes one case per file in a folder, which changes a "baseline plus new tests" count, and a test class that parses the artifact and asserts it equals the writer's tuple |
| Documents and manifests that describe it | `Grep` shipped documents and manifest notes for the old behaviour's wording | A document that a keyword-presence test keeps green after it turns false |

**The rule.** The Output line is the union of the census paths the change edits. A census path left off the line carries a one-line reason beside it. A path that a gate finds changed and that no Output line names is a HALT for the orchestrator (`scaffolding-hygiene-Part-2-DerivationAndParallelism.md` §17.3), never another writer's path.

> [!constraint] Derive the Output line from the tree, not from the design
> WRONG — the Output line names only the file the design says changes:
> ```
> Task: add a `dry_run` field to the report and make `build_report` start a paid export
> Output: scripts/report_cli.py
> # the dataclass, the tests that call build_report and two describing documents are not on the line
> ```
> CORRECT — the census runs first, and the Output line is its union:
> ```
> census: definition site scripts/report_model.py (1 hit) | callers scripts/report_cli.py (1 hit)
>         tests tests/test_report_cli.py (4 hits) | documents docs/usage.md, manifests/notes.yaml (2 hits)
> Output: scripts/report_cli.py, scripts/report_model.py, tests/test_report_cli.py, docs/usage.md, manifests/notes.yaml
> ```

#### Reviewer Check 103 — Named Definition Site Missing From the Task's Output Line

- **Severity / Role / Type:** ERROR (HIGH confidence) | Task Reviewer | NEW
- **What:** A task that adds a parameter, flag or field, or changes a shared function's side effect, MUST carry a Change-Surface Census, and every definition site its Execution Steps name MUST appear on its `**Output:**` line.
- **Detection:** For each task whose steps add a parameter, flag or field or change a shared side effect, find its Change-Surface Census section. Flag the task when the section is absent. Flag each definition site, file or module an Execution Step names for the new symbol that is missing from the `**Output:**` line and carries no one-line reason. → ERROR.
- **Finding template:**
```
[ERROR] Named definition site missing from the task's Output line
File: {task file path} | Location: {Execution Step or Output line}
Issue: Step {n} edits "{definition site}" but the Output line does not list it, or the task has no Change-Surface Census
Fix: Run the four census searches, record them, and derive the Output line from the census, per references/verify-caller-before-complete.md §6 | Confidence: HIGH
```

### 6.1 A Task That Edits a Pinned Artifact Owns Its Pin Tests

A test can pin an artifact's shape. It parses the artifact and asserts the result equals the code's tuple, list or schema. Editing that artifact is then a two-artifact change. The "Tests that reach it" search finds these pin tests at scaffold time, and the runner never discovers them mid-task.

- **Place the hits in three destinations.** The pin test files go on the Output line, into Required Context and into the Verification Commands test gate.
- **Run the pin files at the base commit before the first edit.** Record an already-red pin as a known failure with an owner. A pin that fails before the edit is not the task's regression.
- **Give an unbound column a pin exception.** A column filled by a database default has no writer binding. Exclude it from the writer-tuple compare. The pin still asserts that the column is present.
- **Treat a guarded `ALTER` as an Execution Input decision.** Adding the column only in separate guarded `ALTER` blocks keeps the pins green. The `CREATE` body then no longer shows the full shape. The Execution Input chooses it, never the runner.

> [!constraint] A task that edits a pinned artifact owns the pin tests
> One task added a column to the `CREATE` bodies of 15 tables across 8 SQL files. Its write-set held the 8 files. Six test modules parsed those bodies and asserted the column tuple, and all six broke. The runner finished 2 files, ran one pin file, and halted. The next task ran 3 of the 6 pin files, which left 3 red with no owner. The fix cost two user gates and two runner resumes.
>
> WRONG — the write-set is the edited files alone:
> ```
> Output: the 8 edited SQL files
> Verification: (none of the 6 pin files)
> ```
> CORRECT — the census finds the pins, and the same task owns them:
> ```
> census (tests): Grep pattern='{pin helper}|{pin test class}' path='tests/' -> 6 files that name the edited SQL files
> Output: the 8 edited SQL files, and the 6 pin test files
> Verification: {test runner} {the 6 pin files}   # 0 failed
> pre-edit: {test runner} {the 6 pin files} at the base commit -> 1 failed (known failure, owner: this task)
> ```

#### Reviewer Check 116 — Task Edits a Pinned Artifact With No Pin Tests in Its Write-Set

- **Severity / Role / Type:** ERROR (HIGH confidence) | Task Reviewer | NEW
- **What:** A task whose write-set edits an artifact that a test pins MUST list the pin tests on its `**Output:**` line, in Required Context and in its Verification Commands test gate, per `references/verify-caller-before-complete.md` §6.
- **Detection:** For each task that edits a file whose shape a test parses, use `Grep` on the test tree for the pin helper or pin test-class name and the edited file name. Flag the task when a hit file is absent from the `**Output:**` line, from Required Context or from the test gate. Flag the task again when it has no base-commit run of the pin files. → ERROR.
- **Finding template:**
```
[ERROR] Task edits a pinned artifact with no pin tests in its write-set
File: {task file path} | Location: {Output line, Required Context or Verification Commands}
Issue: The task edits "{artifact}" and {pin test file} pins its shape, but the pin test is missing from {the Output line | Required Context | the test gate}
Fix: Add the pin tests to all three places and run them at the base commit before the first edit, per references/verify-caller-before-complete.md §6 | Confidence: HIGH
```

---

*Companion files: [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10 the instrument's proof obligations), [gate-change-vs-state-detecting.md](gate-change-vs-state-detecting.md) (§11 change- vs state-detecting shapes), [verification-gates.md](verification-gates.md) (the family index, whose §12 points to this file), [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §2 (per-unit assertions over aggregate counts), [templates/sprint-signoff.md](../templates/sprint-signoff.md) (the anchor a behaviour-adding criterion carries).*
