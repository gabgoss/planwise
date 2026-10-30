---
description: A gate's passing condition can come apart from the property it protects in two directions - satisfiable by destruction (an absence gate that passes when the protected thing is deleted, §1; a green battery that never executed a new declaration, §2) and unsatisfiable by construction (a prerequisite marker that is not in the file it names, §3; a per-run check on a surface that does not carry the signal, §4) - so ask two questions of every gate before it ships (§5).
consult-when: Authoring an absence gate, a prerequisite-marker gate or a per-run gate, or a change adds a declaration something else must render — what is the cheapest way to make the gate pass (§1 exempt-set clause, §2 execute the path once), and is there a state where the property holds and the gate still fails (§3 marker proven as an upstream addition, §4 eliciting and ordinary probe); the two satisfiability questions (§5)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Satisfiability (Satisfiable by Destruction, Unsatisfiable by Construction)

**Purpose:** A gate's passing condition and the property it protects are written by the same author, and they can come apart. Some gates pass without the property holding. Others fail while it holds. This file names four instances and the question that catches each. The sections are numbered 1 to 5 in this file. They are new rules, not former sections of `verification-gate-evidence.md`. The family index is `verification-gate-evidence.md`.

**Read this when** you author an absence gate ("MUST be empty"), a cross-task prerequisite marker, or a per-run check on a transcript or log, or a change adds a declaration that something else must render, resolve, substitute or dispatch on.

## Table of Contents

- [1. Ask What the Cheapest Way to Make an Absence Gate Pass Would Be](#1-ask-what-the-cheapest-way-to-make-an-absence-gate-pass-would-be)
- [2. Execute a New Declaration's Path Once and Read the Output](#2-execute-a-new-declarations-path-once-and-read-the-output)
- [3. Verify a Prerequisite Marker the Moment the Upstream Work Is Complete](#3-verify-a-prerequisite-marker-the-moment-the-upstream-work-is-complete)
- [4. Verify an Observability Surface Carries the Signal Before Gating on It](#4-verify-an-observability-surface-carries-the-signal-before-gating-on-it)
- [5. The Two Satisfiability Questions](#5-the-two-satisfiability-questions)

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
> 1. *What is the cheapest way to make this pass, and does that way involve the property holding?* (§1, §2)
> 2. *Is there a state of the world in which the property holds and this gate still fails?* (§3, §4)
>
> A gate that fails the first question is satisfiable by destruction. A gate that fails the second is unsatisfiable by construction. Both are authored the same way: by writing a condition adjacent to the property instead of derived from it.

The two directions stay in one file deliberately. Both come from the same authoring mistake. A reader who sees only the destructive-shortcut half does not learn to check the unsatisfiable half.

---

*Cross-references: [verification-gate-evidence.md](verification-gate-evidence.md) (the family index) · [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10, the four obligations a gate discharges before its output is evidence) · [gate-positive-and-mutation-controls.md](gate-positive-and-mutation-controls.md) (§1-§4 and §14, the positive control and the dry-run pair) · [gate-discriminating-case.md](gate-discriminating-case.md) (whether the input set could have contained the failing case).*
