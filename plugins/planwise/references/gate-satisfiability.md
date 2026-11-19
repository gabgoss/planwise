---
description: A gate's passing condition can come apart from the property it protects in two directions - satisfiable by destruction (an absence gate that passes when the protected thing is deleted, §1; a green battery that never executed a new declaration, §2) and unsatisfiable by construction (a prerequisite marker that is not in the file it names, §3; a per-run check on a surface that does not carry the signal, §4; an absence check wider than the edits its own brief lists, §6; a marker or a row that the graded branch never writes, §7) - so ask two questions of every gate before it ships (§5).
consult-when: Authoring an absence gate, a prerequisite-marker gate or a per-run gate, or a change adds a declaration something else must render — what is the cheapest way to make the gate pass (§1 exempt-set clause, §2 execute the path once), and is there a state where the property holds and the gate still fails (§3 marker proven as an upstream addition, §4 eliciting and ordinary probe); an absence check's expected count must match the edits its own brief lists (§6 list every hit with its edit, name each allowed location); a grader or zero-hit gate over a log, transcript or stream — which event writes this evidence, and does that event fire on the branch being graded (§7); the two satisfiability questions (§5)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Satisfiability (Satisfiable by Destruction, Unsatisfiable by Construction)

**Purpose:** A gate's passing condition and the property it protects are written by the same author, and they can come apart. Some gates pass without the property holding. Others fail while it holds. This file names six instances and the question that catches each. The sections are numbered 1 to 7 in this file. They are new rules, not former sections of `verification-gate-evidence.md`. The family index is `verification-gate-evidence.md`.

**Read this when** you author an absence gate ("MUST be empty"), a cross-task prerequisite marker, a per-run check on a transcript or log, a grader or zero-hit gate over a log, transcript or stream, or a change adds a declaration that something else must render, resolve, substitute or dispatch on.

## Table of Contents

- [1. Ask What the Cheapest Way to Make an Absence Gate Pass Would Be](#1-ask-what-the-cheapest-way-to-make-an-absence-gate-pass-would-be)
- [2. Execute a New Declaration's Path Once and Read the Output](#2-execute-a-new-declarations-path-once-and-read-the-output)
- [3. Verify a Prerequisite Marker the Moment the Upstream Work Is Complete](#3-verify-a-prerequisite-marker-the-moment-the-upstream-work-is-complete)
- [4. Verify an Observability Surface Carries the Signal Before Gating on It](#4-verify-an-observability-surface-carries-the-signal-before-gating-on-it)
- [5. The Two Satisfiability Questions](#5-the-two-satisfiability-questions)
- [6. An Absence Check Must Match the Edit Scope of Its Own Brief](#6-an-absence-check-must-match-the-edit-scope-of-its-own-brief)
- [7. A Gate Waits Only for Evidence the Graded Branch Writes](#7-a-gate-waits-only-for-evidence-the-graded-branch-writes)

---

## 1. Ask What the Cheapest Way to Make an Absence Gate Pass Would Be

Before you ship an absence gate, ask what the cheapest way to make it pass would be. If the answer is "delete the thing the system depends on", the gate is mis-specified, whether or not it passes today.

The underlying impossibility is this. An emptiness assertion cannot distinguish *"the migration was completed correctly"* from *"someone removed the migration"*. Both produce an empty result. So does a mistyped path. That is the classic failure of every absence gate: it returns empty for the one reason that makes empty worthless.

A rename gate asserted that a search for the old directory name over the shipped tree returns nothing. Four occurrences were not rename targets, because a shipped migration detects the legacy name. The gate had exactly one way to pass: delete the four literals.

> [!constraint] Pair the residue clause with an exempt-set count
> ```bash
> # WRONG — one clause, satisfiable by destruction, and silently satisfiable by a typo:
> grep -rn 'feedback-drafts' plugins/planwise/          # MUST be empty
>
> # CORRECT — the residue must be empty AND the protected set must still be there:
> # (a) non-exempt residue MUST be empty — the actual rename assertion
> grep -rn 'feedback-drafts' plugins/planwise/ | grep -vE '(scripts/init_project\.py|handlers/upgrade\.md):'
> # (b) exempt set MUST be intact — MUST print 4
> grep -rn 'feedback-drafts' plugins/planwise/ | grep -cE '(scripts/init_project\.py|handlers/upgrade\.md):'
> ```

Clause (b) does three jobs. Each one alone would justify the extra line.

1. **It removes the destructive shortcut.** Deleting the protected literals now *fails* the gate instead of passing it.
2. **It is a live in-tree positive control.** A mistyped path makes (b) print `0` and fail loudly, where the emptiness form returned a false green. The gate carries its own known-bad corpus.
3. **It converts an unbounded assertion into a bounded one.** "Nothing anywhere" is unauditable. "These four, and nothing else" is a set a reviewer can check.

Two closing rules apply.

- **A path-exclusion filter alone is not sufficient.** Stopping at `grep -v` is the tempting half-measure. It makes the gate pass, and it blinds the gate to a genuinely new stale literal in the excluded files.
- **Prefer this shape whenever an exemption exists at all.** The moment a gate needs the phrase "except for", it is an exact-set assertion, whether or not it is written as one.

---

## 2. Execute a New Declaration's Path Once and Read the Output

A change added a config key to a shipped template. The full suite (557 passed), the identifier gates, the read gates and a path-scoped diff count were all green. Every fresh install received the literal `feedback_dir: "{feedback-dir}"`, because nothing substituted the new placeholder.

Each miss was structural, not unlucky:

| Gate | Why it was structurally blind |
|---|---|
| Full test suite (557 passed) | No test asserted the substitution, because the key was new. A suite's coverage of a feature is written by the same mind that wrote the feature. It cannot cover the case nobody imagined. |
| Identifier-isolation gates | They ask whether a forbidden bookkeeping ID appears in added lines. That is a vocabulary question, unrelated to whether a template renders. |
| Read gates | They measure bytes, lines and tokens. A file with a broken placeholder measures exactly as well as a correct one. |
| Path-scoped diff count | It asks whether the expected files were touched. It is satisfied precisely when the work stayed inside a write-set, which is the very boundary that caused the defect. |

The common blind spot: all four inspect the artifact's *text* or the *shape of the change*. None executes the software. A declaration and its renderer are two files, and no textual gate relates them.

This applies to any declaration that something else must render, resolve, substitute or dispatch on: a template placeholder, a config key, a registry entry, a route, an enum case.

1. **A change that adds a declaration consumed elsewhere is not done when the suite goes green.** Run it, and read the output.
2. **Write the regression test against the general form of the invariant.** The test added after the incident sweeps a generated config for **any** unsubstituted `{lowercase-hyphenated}` placeholder. It does not assert on the one new key. The general form catches the next key added to the template, and the specific assertion would not.
3. **Match the siblings' form when you add an item to a list.** A hardcoded literal beside three placeholders is a defect waiting for the first override.
4. **Treat "all gates green" as evidence about the gates' scope.** It is never evidence of correctness.

---

## 3. Verify a Prerequisite Marker the Moment the Upstream Work Is Complete

A cross-task prerequisite gate searched `handlers/feedback.md` for the literal `'Marking a Posted Draft'`. That literal is a section title in a different file. Three of four tasks would have halted on a true premise.

The root cause explains why review cannot catch this. A marker literal is a **claim about a specific file's contents**. It is authored as a pair of strings in a table, and only the strings are ever reviewed. Reading `grep -c 'Marking a Posted Draft' handlers/feedback.md` tells you nothing about whether that literal is in that file. You have to run it, against a tree where the upstream work has already landed. At scaffold time that tree does not exist. So verify the marker the first moment the upstream work is complete, before any dispatch.

The blast radius is wider than one gate. A false-failing gate does not merely fail to protect. It **trains the runner to route around it**. A runner told "if this returns 0, HALT" that sees 0 on a healthy tree must either stop the session or decide the gate is wrong. Whichever it picks, the sound gates beside it lose their authority at the same moment, because nothing distinguishes them. The blast radius of one bad gate is every gate in the same fence.

- **Choose the replacement by evidence, not by convenience.** When a marker is wrong, the tempting fix is to repoint it at the file where the literal *does* live. Reject that. In the incident the engine file already had its own gate, so repointing would have left the intended file with **no** prerequisite gate at all. That is strictly weaker than the broken gate. Keep one gate per file, and find a literal that genuinely exists in that file.
- **Show the replacement discriminates before trusting it.** Take all three measurements:

  ```bash
  grep -c 'marks the draft posted' handlers/feedback.md                  # 1  — it exists
  git diff $SERIES_BASE -- <path> | grep '^+' | grep -i mark             # it is an upstream ADDITION
  # and 0 in the pre-upstream version — so it distinguishes landed from not-landed
  ```

  A marker that exists in the file but predates the upstream work is not a prerequisite gate. It passes identically whether the delta landed or not. The middle check separates a real gate from a vacuous one, and it is the check most likely to be skipped.
- **Correct every site, not only the executing ones.** Fixing only the task files leaves the session-level artifacts teaching the wrong gate to any re-run or reviewer.

The distinguishing question is never "did the gate pass?". It is **"is this marker in this file, and did this work put it there?"**

---

## 4. Verify an Observability Surface Carries the Signal Before Gating on It

A per-run check searched a session transcript for a marker embedded in an injected rule. The transcript does not persist injected prompt text. The check would have returned MISS on every correctly injected run.

The trap is precise. An author validates the check by asking the model to echo the marker, sees a transcript hit, and concludes that the transcript carries injected rule text. It does not. It carried the model's *output*, which happened to contain the marker. Every real prompt lacks that echo. The gate that "worked in testing" therefore fails universally in production, silently, and in the direction that looks like a real finding.

Three properties made it dangerous:

1. **It fails toward a plausible conclusion.** A MISS was pre-defined as a known failure mode, so universal failure would have read as a dramatic empirical result rather than a broken instrument.
2. **Its validation case and its production case differ in the one dimension that matters.** That dimension is whether the prompt elicits the marker into visible output.
3. **Nothing errors.** The search runs, returns cleanly, and writes a column.

So before you build a per-run gate on an observability surface, verify that the surface carries the signal. Use a deliberately eliciting probe AND an ordinary one. The ordinary probe is the one that matches production.

When a control does not fire, suspect the instrument before the feature. When you replace the instrument, **prefer a signal the platform reports as a first-class attribution over one you infer.** In the incident, injection was proven three ways:

- A `/context` capture's Memory Files table named the rule file at 894 tokens. That is a per-file attribution, so it is direct evidence of loading, not inference.
- An attention-control prompt returned the exact marker as its entire result.
- A 1030-token `cache_creation_input_tokens` delta against a no-rule baseline matched the rule's static size of about 990 tokens.

All three worked. The attribution is the strongest, and it needs no control run.

Corollary for design documents: record the correction **in the design authority**, not only as a flag to the next session. A downstream implementer will certainly read the design. They may or may not read a flag list.

---

## 5. The Two Satisfiability Questions

> [!practice] Ask both questions of every gate before it ships
> 1. *What is the cheapest way to make this pass, and does that way involve the property holding?* (§1, §2, §7)
> 2. *Is there a state of the world in which the property holds and this gate still fails?* (§3, §4, §6, §7)
>
> A gate that fails the first question is satisfiable by destruction. A gate that fails the second is unsatisfiable by construction. Both are authored the same way: by writing a condition adjacent to the property instead of derived from it.

Section 7 feeds both questions. A zero-hit gate over a mode that never prints its needle, and a one-branch marker read as absence, pass without the property. A post-call row waited for on a branch that never writes it fails while the property holds.

The two directions stay in one file deliberately. Both come from the same authoring mistake. A reader who sees only the destructive-shortcut half does not learn to check the unsatisfiable half.

---

## 6. An Absence Check Must Match the Edit Scope of Its Own Brief

A brief can carry an absence check ("MUST be 0") that is wider than the edits its Execution Steps list. A runner treats the step enumeration as binding. It edits the sites the steps name and stops. The check then fails on every site the steps never named, so no correct run can satisfy it.

Two incidents showed the shape:

- A re-point brief expected a count of its old name to be 0. Its Execution Steps covered 2 of the 6 hits.
- An orchestrator delta read 1 of its own 2 discovery hits.

> [!constraint] The step list equals the search output, and the check names what stays
> WRONG — an absence check wider than the steps, closed by a judgment call:
> ```
> Execution Steps: re-point hits 1 and 4 of the 6 hits of `OldName`
> Verification:    Grep pattern='OldName' path='plugins/' output_mode='count'   # MUST be 0
> Criterion:       "verify by reading the matches that nothing stale remains"
> # the other 4 hits are in no step, so no runner edit removes them
> ```
> CORRECT — the search at authoring time is the enumeration, and the count names its allowed location:
> ```
> Authoring:       Grep pattern='OldName' path='plugins/' output_mode='content' -n=true   # 6 hits
> Execution Steps: 6 steps, one per hit, each with its edit (5 re-points, 1 left in place)
> Verification:    Grep pattern='OldName' path='plugins/' output_mode='count'   # expect 1, the history line at the Change Log
> ```

1. **Search the target for every old name when you author the brief.** Use `Grep` with `output_mode='content'`. List every hit in the Execution Steps with its edit. The step list then equals the search output. This is the brief-level form of "The Grep is the enumeration" in [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) §7. Still hand the runner the locator and require an occurrence count, per that file's §1.
2. **Write the absence criterion as an exact expected count that names each allowed location.** An example is "expect 1, the history line at the Change Log". Never leave the final count to the runner's judgment.
3. **Treat a hit outside the edit scope as a sibling finding.** The author either missed that site or meant it to stay. Add a step for it, or name it as an allowed location in the criterion. A hit that is neither is noise only to a brief that was never enumerated.

#### Reviewer Check 113 — Absence Check Scope Differs From the Execution Steps' Enumeration

- **Severity / Role / Type:** WARNING (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** A task whose absence criterion searches a wider set than its Execution Steps edit MUST name each allowed location for the difference. Flag a task whose criterion expects 0, or a count with no named location, while its steps cover fewer sites than the search returns.
- **Detection:** Use Grep over the plan's task files for absence criteria: "MUST be 0", "expect 0", "returns nothing", "No matches". For each hit, read the Execution Steps of the same task and count the sites they edit. Compare that count with the search's own hit count. A criterion that expects 0 or an unexplained count while the steps list fewer sites → WARNING. The reported shape: a re-point brief expected 0 old names after steps that covered 2 of 6 hits.
- **Finding template:**
```
[WARNING] Absence check scope differs from the Execution Steps' enumeration
File: {task file path} | Location: {criterion line}
Issue: "{criterion}" searches {N} hits of "{value}", but the Execution Steps edit {M} of them and the criterion names no allowed location for the rest
Fix: List every hit in the Execution Steps with its edit, and write the criterion as an exact count that names each allowed location, per references/gate-satisfiability.md §6 | Confidence: HIGH
```

---

## 7. A Gate Waits Only for Evidence the Graded Branch Writes

> [!constraint] Name the event that writes the evidence, and confirm it fires on the branch being graded
> Every gate reads a record that some event writes. If that event never fires on the branch under test, the gate cannot discriminate. A zero-hit gate then passes on any tree. A presence gate never passes. A marker that one outcome writes cannot prove that a different outcome did not happen.

Three incidents show the three shapes.

### 7.1 A Zero-Hit Gate Whose Needle the Mode Never Prints

A smoke gate had to show that a review card draws nothing under `claude -p`. The gate searched the `-p` stream and stderr for a `ui.render` refusal line. Nobody had seen that line, so the task paid for a run of a deliberately broken plugin under `-p` to capture it. That run printed no refusal at all. Under `-p` the engine draws no band, so a render hook never runs, and no runtime refusal can appear. A static `claude plugin validate` of the same broken plugin printed the refusal and cost nothing.

> [!constraint] Gate a render claim on the static instrument that sees it
> ```
> WRONG — a zero-hit gate whose needle can never fire:
> known-bad plugin under claude -p (paid) -> search 'ui\.render' in run.jsonl and stderr -> 0 -> needle "none observed"
> real run under claude -p -> search <needle> -> 0 -> UNCERTAIN: the gate cannot discriminate
>
> CORRECT — the static instrument that does see the refusal:
> claude plugin validate <known-bad>  -> "no component is named NoSuchBand, so it never runs"   (no cost)
> claude plugin validate <real>       -> "ui.render{component=AbovePrompt}", no refusal line
> ```
> Gate "no card under `-p`" on positive evidence: the tool ran, and validate lists the hook's matcher.

### 7.2 A Marker That One Outcome Writes

A grader asked whether a person answered an interactive permission dialog. The transcript held no dialog record. Its only marker was `toolDenialKind: "user-rejected"` on the tool result, which a person's rejection writes. The grader read the marker's absence as "no dialog". On the arm where a hook approved the call, that label was right by luck. A person who approved the rendered dialog would also leave no marker, so the key could not tell the two apart.

> [!constraint] The marker decides only the case that writes it
> ```python
> # WRONG — absence of the rejection marker read as "no person answered":
> hits = [i for i in range(u + 1, r + 1) if records[i].get("toolDenialKind") == "user-rejected"]
> return "DIALOG" if hits else "NO-DIALOG"      # a person who approved also reads NO-DIALOG
> ```
> ```
> CORRECT — the no-dialog claim needs evidence that covers approval too:
> DIALOG (rejected)   <- toolDenialKind user-rejected on the result record
> NO-DIALOG           <- marker absent AND the keystroke record shows no key AND the screen
>                        shows the hook's allow (or the dialog question never rendered)
> UNPROVEN            <- marker absent, no keystroke record or screen capture
> ```

### 7.3 A Post-Call Row for a Call That Never Ran

A grader required a `PermissionDenied` or `PostToolUseFailure` row in a hook module's log for a `Write` that the session had to refuse. On the interactive CLI the `Write` raised its own permission dialog, and a person rejected it. The transcript recorded the result with `is_error: true` and `toolDenialKind: "user-rejected"`. The log held no row of any event for that call, because a rejection at the dialog ends the call before any post-call hook runs. The predicate graded UNCERTAIN on every such arm, and a re-run reproduced the same records.

> [!constraint] Read the evidence where the branch writes it, and name the substitute
> ```python
> # WRONG — the clause waits for a row that the rejection branch never writes:
> denial = write_rows(ctx, ("PermissionDenied", "PostToolUseFailure"), "out/reentry.txt")
> if denial is None:
>     return UNCERTAIN   # always taken when a person rejected the call; a re-run reproduces it
> ```
> ```python
> # CORRECT — a real denial row still wins. Without one, the transcript's rejection key stands in,
> # the mode comes from the last mode-bearing row before the call, and the evidence names the substitute:
> if denial is None:
>     rejected = records[wr].get("toolDenialKind") == "user-rejected"
>     no_row = not any(row_names(r, "out/reentry.txt") for r in rows)
>     if not rejected or not no_row:
>         return UNCERTAIN
>     enter = last_row(rows, event="PostToolUse", tool_name="EnterPlanMode")
>     denial = {"permission_mode": enter and enter["permission_mode"]}
>     source = "transcript user-rejected; mode from log[%d] PostToolUse EnterPlanMode" % enter["_ln"]
> ```

### 7.4 The Rules and the Review Question

Five rules follow.

1. **Name the writer before you pin the gate.** Write down which event writes the gate's evidence. Confirm that the event fires on the branch under test, from the mode's documented behaviour, the hook order or one probe on that branch.
2. **A negative names the record a positive would leave.** Before a "no X" grade counts, name the record that "yes, X happened" leaves on every branch, not on one. When no such record exists in the archive, grade UNPROVEN, never the negative.
3. **Check for a static instrument before a paid known-bad run.** A validator, a type check or a dry run may already print the needle. Run it first.
4. **Fixture three cases before you trust a substitute.** The substitute holds, the substitute shows the wrong value, and neither record exists. The third case must stay undecided.
5. **Record the marker's limit beside the constant that pins it.** The next reader then does not take the marker's pass as proof of the other outcome.

**Review question.** Which event writes this evidence, and does that event fire on the branch being graded?

**Applies to** zero-hit gates over a stream whose subject may not run in the mode probed, graders that infer a person's action from session records, and gates over hook logs that classify a call a person can refuse at a dialog. Section 4 asks whether the surface carries the signal at all. This section asks whether the branch under test writes it.

---

*Cross-references: [verification-gate-evidence.md](verification-gate-evidence.md) (the family index) · [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10, the four obligations a gate discharges before its output is evidence) · [gate-positive-and-mutation-controls.md](gate-positive-and-mutation-controls.md) (§1-§4 and §14, the positive control and the dry-run pair) · [gate-discriminating-case.md](gate-discriminating-case.md) (whether the input set could have contained the failing case).*
