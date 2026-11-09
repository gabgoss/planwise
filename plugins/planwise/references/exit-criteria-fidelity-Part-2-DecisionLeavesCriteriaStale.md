---
description: Exit-criteria fidelity continued — a decision that leaves a known failure in a verifier's input set rewrites every criterion pinned to that verifier's exit code at the moment of the decision, and a flag that changes how a gate is read names and supersedes the criterion's wording (§16.13), and a size or rate constant is derived from the headline criterion while every closeout reports against the criterion, not the constant (§16.14), and an append-only record numbered from its newest end rewrites every existing identifier on each append (§16.15), and a Master Plan Success Criteria clause names one owning task, because restating a clause in the Sprint Plan or an Orchestration is not ownership (§16.16), and a Success Criteria checkbox that asserts prose content pairs with a command that reads the file, because a checkbox with no command passes on self-report (§16.17), and a per-file requirement cited only in Notes for Agent is a mention that gates nothing until every task that creates such a file carries a per-file command with an expected count (§16.18), and measurement work carries one criterion that ties a produced value to its evidence, because a shape gate passes on a fabricated value (§16.19). Split out of exit-criteria-fidelity.md when that file neared the Read-tool token gate.
consult-when: A go/no-go or fallback decision leaves a known failing input under a verifier, or a criterion reads "`<verifier>` exits 0" — enumerate every pinned criterion with `Grep` at the decision, rewrite each to a scoped this-run clause, and route a flag that names and supersedes the old wording, a plan states a margin or ratio target beside a size constant — derive the constant from the headline and report each closeout against the headline, and a newest-first numbered record renumbers every entry on each append, so key entries by date or number from the oldest end, and a Master Plan Success Criteria clause with no task that answers for it — name one owning task per clause and set-diff the clauses against the task-level Success Criteria and Verification Commands, and a Success Criteria checkbox asserts prose content (a header line, a docstring paragraph) with no command that reads the file, or a per-file requirement appears only in Notes for Agent — pair the checkbox with a command that reads the file, and give every creating task a per-file command with an expected count
---

# Exit-Criteria Fidelity, Part 2 — A Decision Rewrites the Criteria That Depend on It

**Purpose:** §16.13 to §16.19, split out of [exit-criteria-fidelity.md](exit-criteria-fidelity.md) when that file neared the Read-tool token gate. §16.1-§16.12 stay on that anchor, which keeps the original filename. §16.13 extends §16.9 (an absence criterion must exclude its enactor) from the criterion that cannot be satisfied by construction to the decision that makes it so. §16.14 adds a rule for a size or rate constant that must be derived from the plan's headline criterion. §16.15 extends §16.12 (append, never insert) from a list that grows by hand to a record whose numbering counts from the newest end. §16.16 closes the gap between a Master Plan clause and the task that answers for it: each clause names one owning task, and a Coverage Reviewer set-diff catches a clause no task owns. §16.17 and §16.18 extend the SURFACE-versus-MENTION test of §16.2 to two gaps it leaves open. A checkbox that asserts prose content has no command that reads the file. A per-file requirement cited only in Notes for Agent gates no creating task. §16.19 requires measurement work to carry one criterion that ties a produced value to its evidence.

---

### 16.13 A Decision That Leaves a Known Verifier Failure Rewrites Every Criterion Pinned to Its Exit Code

> [!constraint] A decision that leaves a known failure in a verifier's input set changes every claim that verifier's exit code backs
> The claims live in files the decision-maker did not open. "`<verifier>` exits 0" was true when written. It became false at the decision, and nothing in the tree marked it. A routed flag that carries only the grading rule is correct and incomplete. It leaves the criterion standing, so the contradiction surfaces one session later as a structural finding instead of at its cause.

A checker globs every `*.json` file under one probes directory and exits 1 if any file drifts. A go/no-go session found two archived files drifting on a defect in a module. It decided to fix the module and to grant the checker no exemption. The two archived files stayed where the checker reads them. The decision routed a flag to the next sprint: "grade this session on its own output's OK line. A new DRIFT line naming the same event is the same defect."

Three task files, one session orchestration, one sprint plan and the master plan all still read "`<verifier>` exits 0". The receiving orchestrator ran the checker once before its first run. It exited 1, on exactly the two archived lines. Both tasks' success criteria were unsatisfiable before the session's own runs had produced anything.

> [!constraint] WRONG and CORRECT — the decision names and rewrites every dependent criterion
> ```
> WRONG — the decision leaves the inputs, routes a grading hint, and the criteria stand:
> decision: module edit, no checker exemption      (two archived DRIFT lines persist)
> flag ->   "grade on your own output's OK line"
> criteria: "<verifier> exits 0"                    (several files, untouched)
> next session, before its first run: exit=1        -> Phase-1 structural finding
>
> CORRECT — the decision names and rewrites every dependent criterion:
> decision: module edit, no checker exemption
> Grep "<verifier>" over <plan tree>                -> every pinned criterion listed
> each -> "this run's output line reads OK; no DRIFT names it; exit code and non-OK lines recorded"
> flag -> "criterion X in files A..E is superseded by the clause above"
> ```

Three consequences follow.

1. **Enumerate the criteria at the decision.** Run `Grep` over the plan tree for the verifier's name. Every "exits 0", "prints PASS" or "no DRIFT" over it is now a claim to rewrite, not a flag to route around.
2. **Rewrite each into a scoped clause.** Write: "The step-4 line for this run's output reads `OK`. No DRIFT line names this run's output. The exit code and every non-OK line are recorded verbatim." The archived failures then pass through the gate as recorded state, not as this run's defect.
3. **Say that the flag supersedes the criterion.** A flag that changes how a gate is read must say the gate's wording is superseded. "Grade on your own OK line" reads as advice beside a criterion that says "exit 0". Name the criterion, quote it, and replace it.

**Scope.** This is the propagation step after classification. Classifying a non-zero exit code by cause is a separate rule: see [verify-verdict-source.md](verify-verdict-source.md) §8. Carrying the consequence of a decision into every dependent criterion is this rule. It applies to:

- Any verifier that reads an accumulating directory (a glob over output files, logs or archives) where a known-bad input stays by decision.
- Any criterion phrased as an exit code or a single verdict word.
- Go/no-go and fallback decisions that route flags forward.

§16.9 covers an absence criterion that cannot be met because its own enactor trips it. This section covers a criterion that was meetable until a decision made it unmeetable, and the decision-maker was the only party positioned to rewrite it.

### 16.14 A Size or Rate Constant Is Derived From the Headline Criterion, and Every Closeout Reports Against the Criterion

> [!constraint] A budget constant and a headroom target are different quantities. A green budget gate says nothing about the target
> "Under 22,000" and "at least 2x under 25,000" answer different questions. When a plan states a headline target and a design constant that enforces size, derive the constant from the target. Or state explicitly that the constant is the weaker guarantee, and restate the target to match.

**Three design-time steps.**

1. **Compute what the constant permits in the target's units.** A 22,000-token budget against a 25,000-token cap permits 1.14x headroom.
2. **If that falls short, change one side.** Lower the constant (to 12,500 for a 2x target) or restate the target as the weaker guarantee.
3. **Record the measured headroom beside the target at every sprint closeout.** Do not record it against the constant alone.

> [!constraint] WRONG and CORRECT — the constant is derived from the headline, and every closeout reports against the headline
> ```
> WRONG:
> Headline: at least 2x headroom under 25,000 tokens
> <design pin>: budget 22,000 tokens per file          # permits 1.14x, never reconciled
> Sprint closeout: "<index> 15,164 tokens, 6,836 headroom (vs 22,000)"   # reported against the budget only
>
> CORRECT:
> Headline: at least 2x under 25,000  ->  file at most 12,500 tokens
> <design pin>: budget = 12,500 (derived from the headline), or headline restated as "under 22,000 per file"
> every closeout: "<index> 15,164 tokens = 1.65x (target 2x: MISSED)"
> ```

**What happened without it.** The plan's headline criterion was "reads in one `Read` call with at least 2x headroom under the 25,000-token page cap". That is a file at or below 12,500 tokens. The design set a per-file budget of 22,000 tokens, which permits 1.14x. Every size gate reported green. Each sprint closeout recorded the measured size against the budget only. The miss surfaced at the final cutover read, three sprints later. The file measured 1.60x. The cutover was held and the user accepted the miss with a follow-up. Every other criterion had passed. The one the plan was named for was unmeetable from the day the constant was chosen.

**Where it applies.** Any plan whose success criterion is a margin or ratio (headroom, a latency percentile, an error budget) while the implementation enforces a different threshold. It also applies to any closeout that reports a measurement against the implementation's threshold rather than the plan's criterion. §16.11 covers filling the signoff at sprint close. This section covers what the filled signoff must report against.

#### Reviewer Check 096 — Size Constant Cannot Meet the Plan's Headline Margin

- **Severity / Role / Type:** WARNING (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** For each headline margin or ratio criterion, find the design constant that enforces size. Compute the constant's implied margin. Flag a constant that cannot meet the headline and states no weaker-guarantee restatement.
- **Detection:**
  1. List each headline criterion phrased as a margin or ratio (headroom, percentile, error budget).
  2. Find the design pin, budget or threshold that enforces it in the implementation.
  3. Compute the margin the constant permits in the headline's units.
  4. Constant permits less than the headline, and no sentence restates the headline as the weaker guarantee → WARNING.
  5. A closeout or signoff row that reports the measurement against the constant but not against the headline → WARNING.
- **Finding template:**
```
[WARNING] Size constant cannot meet the plan's headline margin
File: {design pin or EI path} | Location: {constant / headline criterion}
Issue: Headline requires {margin}; constant {value} permits {implied margin} and no weaker-guarantee restatement exists
Fix: Derive the constant from the headline or restate the headline, and report each closeout against the headline, per references/exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md §16.14 | Confidence: HIGH
```

### 16.15 A Newest-First Numbered Record Renumbers Every Entry on Each Append

> [!constraint] An append-only record that counts identifiers from the newest end rewrites every existing identifier on each append
> An entry number then stops meaning the same entry over time. Every append also edits lines it did not add. Number from the oldest end, or key each entry by its date or another fixed value. An append then touches only the new entry. The newest entry can still sit at the top of the page.

§16.12 covers a list where an author inserts new entries by hand. This section covers a record that renumbers itself by construction. A changelog numbers its entries newest-first, so `## Entry 1` is always the latest. One append shifted three existing headings: 1 to 2, 2 to 3, and 3 to 4. A ledger that recorded "`## Entry 1 — <date>` present" then named the wrong entry. No step errored. The ledger row read as true and pointed at a different entry.

> [!constraint] WRONG and CORRECT — a stable key per entry, newest still on top
> ```
> WRONG — newest-first counter:
> ## Entry 1 — 2026-09-26   <- new
> ## Entry 2 — 2026-09-23   <- was Entry 1
> ## Entry 3 — 2026-09-19   <- was Entry 2
>
> CORRECT — a stable key per entry, newest still on top:
> ## 2026-09-26 — <title of the newest entry>
> ## 2026-09-23 — <title of the previous entry>
> ## 2026-09-19 — <title of the oldest entry shown>
> ```
> An ascending counter works as well. The oldest entry is `## Entry 1`, and the newest entry carries the highest number and sits on top. The headings then descend top to bottom, and a number never changes once assigned.

- **Until the scheme changes, cite an entry by its date or heading text.** Never cite it by its number.
- **Check the writer first.** A writer that assigns the next number and never renumbers an existing one has the stable form. A record kept by hand, or by a writer that counts from the top, has the unstable form.

**Applies to** any changelog, log, or decision record kept newest-first with numbered headings. It also applies to any ledger or evidence file that cites such an entry by number.

### 16.16 A Master Plan Success Criteria Clause Names One Owning Task

> [!constraint] Restating a clause is not owning it
> A Master Plan Success Criteria clause that appears in the Master Plan, the Sprint Plan and an Orchestration, and in no task's Success Criteria or Verification Commands, has no owner. Each restatement reads as coverage. No task answers for the clause, so a task that forgets the work still passes every check it owns. An exit criterion no task owns is no guarantee at all.

A plan review found one exit criterion in this state. The criterion "expensive designs must be flagged so the user can opt in before the costly work runs" sat in the Master Plan, the Sprint Plan and an Orchestration. No task carried it as a Success Criteria checkbox or a Verification Command. The closeout task confirmed only that a summary section existed, with a heading count. A task that omitted the flag would have passed every check.

**The rule.** Every clause under the Master Plan's `## Success Criteria` names one owning task, written as `— Owner: {task-id}` at the end of the clause. The owning task carries the clause in one of two forms:

1. A Success Criteria checkbox in the owning task file that restates the clause in a machine-checkable form.
2. A Verification Command in the owning task file that proves the clause.

A roll-up clause names the task that answers for the roll-up. "All sprints complete" names the sprint signoff or closeout task. The **Resolves:** clause names the closeout task.

> [!constraint] WRONG and CORRECT — one owner per clause, carried in the owner's own task file
> ```
> WRONG — the clause is restated in three layers and owned by none:
> Master Plan:   - [ ] Expensive designs are flagged before costly work runs
> Sprint Plan:   - [ ] Expensive designs are flagged before costly work runs
> Orchestration: - [ ] Expensive designs are flagged before costly work runs
> every task file: (no checkbox and no command names the flag)
>
> CORRECT — the clause names its owner, and the owner's task file carries it:
> Master Plan:   - [ ] Expensive designs are flagged before costly work runs — Owner: T-03
> T-03 Success Criteria: - [ ] The design step prints the line `EXPENSIVE: opt-in required` before the costly step
> T-03 Verification:     Grep pattern='EXPENSIVE: opt-in required' path='{design step file}' -> 1 match
> ```

**Which layers count.** Only task-level Success Criteria and Verification Commands count as ownership. A Sprint Plan or Orchestration restatement does not. Those layers repeat the Master Plan clause. They do not prove it.

#### Reviewer Check 106 — Master Plan Success Criteria Clause With No Owning Task

- **Severity / Role / Type:** ERROR (HIGH confidence) | Coverage Reviewer | NEW
- **What:** Set-diff the Master Plan Success Criteria clauses against the union of task-level Success Criteria checkboxes and Verification Commands. Report each clause that no task carries, and each clause that names no owner.
- **Detection:**
  1. List every clause under the Master Plan's `## Success Criteria`, including the roll-up clauses.
  2. For each clause, read the task id after `— Owner:`. A clause with no `Owner:` field is a finding.
  3. Open the named task file. Search its Success Criteria and Verification Commands for the clause's checkable content.
  4. Build the union of every task file's Success Criteria checkboxes and Verification Commands. Exclude Sprint Plan and Orchestration text from the union.
  5. A clause absent from the union, or a clause whose named owner does not carry it → ERROR.
- **Finding template:**
```
[ERROR] Master Plan Success Criteria clause has no owning task
File: {Master Plan path} | Location: {clause text}
Issue: No task's Success Criteria or Verification Commands carries the clause, or the clause names no Owner
Fix: Name one owning task on the clause and add a machine-checkable checkbox or a Verification Command to that task, per references/exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md §16.16 | Confidence: HIGH
```

**Scope.** §16.3 covers a Sprint signoff row against the Execution Input's exit criteria. This section covers the layer above it, the Master Plan clause. §16.1 covers a refinement that must echo across layers. Echoing a clause across layers is the restatement this rule says is not ownership.

### 16.17 A Checkbox That Asserts Prose Content Pairs With a Command That Reads the File

> [!constraint] A prose-content checkbox needs a Verification Command that reads the file
> A Success Criteria checkbox can assert what a file says. "The header carries the licence line." "The docstring covers the failure cases." If no Verification Command reads that file, the checkbox passes on the runner's self-report. Pair each such checkbox with a command that reads the file and returns a match or a count.

The command takes one of two forms:

1. A `Grep` call on the new file for the asserted phrase, with an expected count.
2. For a Python docstring, a command that reads `__doc__` and tests for the phrase.

A checkbox about behaviour that a test run exercises is outside this rule. The rule covers a checkbox whose subject is text in a file. §16.2 defines SURFACE for a blocking item. This section applies the same test to a prose claim: a checkbox with no command is a mention.

> [!constraint] WRONG and CORRECT — the checkbox and a reading command travel together
> ```
> WRONG — the checkbox asserts content and no command reads the file:
> Success Criteria:      - [ ] Each module header carries the licence paragraph
> Verification Commands: python -m pytest tests/test_adapter.py     # runs the code, never reads the header
>
> CORRECT — the checkbox pairs with a command that reads the file:
> Success Criteria:      - [ ] Each module header carries the licence paragraph
> Verification Commands: Grep pattern='non-commercial' path='{new module}' output_mode='count'   # >= 1
> ```

#### Reviewer Check 108 — Prose-Content Checkbox With No Verification Command That Reads the File

- **Severity / Role / Type:** WARNING (HIGH confidence) | Task Reviewer | NEW
- **What:** For each Success Criteria checkbox whose subject is text in a file, find a Verification Command in the same task that reads that file. Flag a checkbox with none.
- **Detection:**
  1. List each Success Criteria checkbox that asserts file text: a header, a docstring, a section, a phrase or a line.
  2. Name the file the checkbox is about.
  3. Search the task's Verification Commands for a command that reads that file: a `Grep` call, a read of `__doc__`, or a count of a heading.
  4. A command that only runs code or tests, and never reads the file's text, does not count.
  5. No reading command for the file → WARNING.
- **Finding template:**
```
[WARNING] Prose-content checkbox has no Verification Command that reads the file
File: {task file path} | Location: {checkbox text}
Issue: The checkbox asserts text in {file} and no Verification Command reads that file, so it passes on self-report
Fix: Add a command that reads the file and returns a match or a count, per references/exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md §16.17 | Confidence: HIGH
```

### 16.18 A Per-File Requirement Cited Only in Notes for Agent Gates Nothing

> [!constraint] Every task that creates a file under a per-file requirement carries a per-file command
> A requirement that applies to every file of a family is a mention when only Notes for Agent states it. The runner can read it and still ship a file without it. Each task that creates such a file carries a command that reads that file and returns an expected count. A sprint sweep does not replace those commands.

A plan hazard required a licence credit paragraph in every module docstring of one adapter family. The exit criterion gated the hazard with one sprint-level sweep over the family. The task that created the first three modules carried the hazard in its Notes for Agent. Its Verification Commands had no matching check. Three modules shipped without the paragraph, and four later sessions built on them.

The sweep caught the gap only because its file set was wider than any one task's gate. A sweep that mirrors the tasks' own gates inherits their blind spots. Build the sweep's file set from the union of the creating tasks' Output lines. Then compare that union to the family's real file list.

- A file in the family and in no task's Output has no per-file gate.
- A file in a task's Output and outside the sweep's file set escapes the sweep.

> [!constraint] WRONG and CORRECT — a per-file command in each creating task, and a sweep built from their union
> ```
> WRONG — the requirement sits in Notes for Agent, and one sweep gates the family:
> T-02 Notes for Agent:       Every module docstring carries the licence paragraph.
> T-02 Verification Commands: (no command reads a new module's docstring)
> Sprint exit sweep:          one Grep over the family directory
>
> CORRECT — each creating task gates its own files, and the sweep's file set is the union:
> T-02 Verification Commands: Grep pattern='non-commercial' path='{each module T-02 creates}' output_mode='count'   # >= 1
> T-03 Verification Commands: the same shape, for each module T-03 creates
> Sprint exit sweep:          files_with_matches count MUST equal the number of files in the union of T-02 and T-03 Output lines
> ```

#### Reviewer Check 109 — Per-File Requirement in Notes for Agent With No Per-File Command in the Creating Task

- **Severity / Role / Type:** ERROR (HIGH confidence) | Task Reviewer | NEW
- **What:** For each per-file requirement stated in a task's Notes for Agent, find a per-file Verification Command in every task that creates a file under it. Flag a creating task with none, and a sprint sweep whose file set differs from the union of the creating tasks' Output lines.
- **Detection:**
  1. Search each task's Notes for Agent for a requirement phrased for every file of a family, such as "every module", "each adapter" or "all new files".
  2. List the files each creating task produces from its Output lines.
  3. Search that task's Verification Commands for a command that reads each created file for the required text and states an expected count.
  4. A creating task with no such command → ERROR.
  5. Build the union of the creating tasks' Output files. Compare it to the sprint sweep's file set. A difference in either direction → ERROR.
- **Finding template:**
```
[ERROR] Per-file requirement in Notes for Agent has no per-file command in the creating task
File: {task file path} | Location: {requirement text in Notes for Agent}
Issue: The task creates {files} under the requirement and its Verification Commands carry no per-file command with an expected count
Fix: Add a per-file command with an expected count to each creating task, and build the sprint sweep's file set from the union of their Output lines, per references/exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md §16.18 | Confidence: HIGH
```

### 16.19 Measurement Work Carries One Criterion That Ties a Produced Value to Its Evidence

> [!constraint] A shape gate cannot detect a fabricated value, so one criterion ties each produced value to its evidence
> A gate that counts rows, checks a grain or pairs a span with a source certifies the shape of the data. It cannot tell a measured value from a fabricated one. Measurement work carries at least one criterion that joins a produced value to the source record that justifies it.

A sprint measured a time axis for reference data. All seven success criteria passed, and the orchestrator re-ran each one against the live database. A later review found three committed corruptions:

- An alias era ran 21 years, but the source emitted that exact string on one date only.
- A "neutral" span was byte-identical to the home span of the same venue.
- Records for events that never took place were admitted as evidence.

The gates asserted counts, grains and pairings. The pairing gate certified the fabricated row, because the row had both a span and a source. Two of the three corruptions were defects in the plan's own rule, implemented faithfully.

**Authoring test.** Ask of every measurement criterion: what value could be wrong while this still passes? Any produced value that is a valid answer needs a criterion that checks it against its source.

Two corollaries follow:

- **A re-run proves reproduction, not correctness.** An orchestrator that re-runs a runner's assertions shows they reproduce. Spot-check produced values against the source by hand.
- **Settle the cause before a repair.** Decide whether the code disobeyed the spec or the spec was wrong. Dispatching a repair against a faithful implementation of a wrong rule changes correct code.

> [!constraint] WRONG and CORRECT — a shape gate, and an anti-join to the evidence
> ```
> WRONG — the row has a span and a source, so a fabricated row passes:
> SELECT COUNT(*) FROM era_table WHERE valid_from IS NOT NULL AND source IS NOT NULL;   -- MUST equal the row count
>
> CORRECT — each measured row joins to the source record that justifies it:
> SELECT COUNT(*) FROM era_table a WHERE a.source = 'measured'
>   AND NOT EXISTS (SELECT 1 FROM corpus b WHERE b.emitted_string = a.name AND b.event_date = a.valid_from);  -- MUST be 0
> ```

#### Reviewer Check 124 — Data-State Literal Used as a Pass or Fail Value

- **Severity / Role / Type:** ERROR (MEDIUM confidence) | Task Reviewer | NEW
- **What:** An expected value that is a data-state literal fails §16.10.1 even when the literal is cited. Measurement work with no criterion that ties a produced value to its evidence fails §16.19.
- **Detection:**
  1. List the expected value of each task Success Criterion, each Verification Commands expectation, each EI exit criterion and each Signoff anchor.
  2. Classify each value. A row count, "NULL everywhere" or a corpus distribution that the data held when someone measured it is a data-state literal. A value the change itself produces is not. A data-state literal used as a pass or fail value → ERROR.
  3. Apply the three scaffold tests of §16.10.1 to each remaining literal. A literal that a correct run would fail after the next ingest → ERROR.
  4. For a task that measures or loads data, search its criteria for one that joins a produced value to its source record. None → a second finding.
- **Finding template:**
```
[ERROR] Data-state literal used as a pass or fail value
File: {task or plan file path} | Location: {criterion or anchor text}
Issue: "{criterion}" expects {literal}, a value the data held when it was measured, so a correct run can fail after the next ingest
Fix: Record {literal} as a measurement and assert the invariant the code guarantees, per references/exit-criteria-fidelity.md §16.10.1 | Confidence: MEDIUM

[ERROR] Measurement work has no criterion that ties a produced value to its evidence
File: {task file path} | Location: Success Criteria
Issue: Every criterion checks counts, grains or pairings, so a fabricated value passes
Fix: Add a criterion that joins each produced value to its source record and MUST return 0 unmatched rows, per references/exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md §16.19 | Confidence: MEDIUM
```
