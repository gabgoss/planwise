---
description: An anchor accepts exactly the outcome set its own task's Execution Steps can produce — set equality derived at scaffold close, with the branch count carried inline, and never hardened into a count equality (§10.7, Reviewer Check 095); and a re-capture gate over a directory a tool regenerates in place names the environment-attributable files (fetched, session, timing, cost) apart from the extractor-attributable ones, so only the remainder halts (§10.10).
consult-when: Writing a Signoff anchor, exit criterion, Execution Input gate, or a `git diff --stat` allowed set over a regenerated directory — the anchor accepts exactly the task's terminal branches (§10.7, Check 095), the allowed set names environment-attributable files apart from extractor-attributable ones (§10.10)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Anchor Outcome Set and Re-Capture Allowed Set

**Purpose:** The mirror of a vacuous gate is a gate that cannot pass. Both ship green-looking artifacts and both report a wrong verdict on a correct execution. §10.7 covers an anchor's accepted outcomes; §10.10 covers the allowed set of changed paths after a re-capture. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you write or review a Signoff anchor, an exit criterion, an Execution Input gate, or a `git diff --stat` allowed set over a snapshot, fixture, golden-file or report directory.

## Table of Contents

  - [10.7 An anchor accepts exactly the outcome set its own task can produce](#107-an-anchor-accepts-exactly-the-outcome-set-its-own-task-can-produce)
  - [10.10 A re-capture gate's allowed set names the files that change on every capture](#1010-a-re-capture-gates-allowed-set-names-the-files-that-change-on-every-capture)

---

### 10.7 An anchor accepts exactly the outcome set its own task can produce

`gate-pre-edit-baseline.md` §10.2 catches a gate that cannot fail. This section catches the mirror defect: a gate that cannot pass. A task's Execution Steps often define more outcomes than the anchor's author expects, such as a zero-hit, nothing-to-do or already-resolved branch. When the anchor enumerates fewer, it rejects a correct execution, and the runner must halt or invent a result.

> [!constraint] Diff the anchor's accepted-outcome set against the owning task's terminal branches at scaffold close
> If the task's Execution Steps define N terminal outcomes, the anchor accepts N. This is set equality, not a subset relation in either direction.
>
> WRONG — the task defines three terminal outcomes, the anchor accepts two:
> ```markdown
> Task step 4:  hits + unambiguous → repoint
>               hits + ambiguous   → route to the orchestrator
>               zero hits          → drift already resolved; record CLOSED-NO-ACTION
>
> Anchor 6:     PASS when the report records `repoint` or `route`
> ```
> The measured and expected outcome is zero hits. The anchor rejects it.
>
> CORRECT — the anchor's branch list is derived from the task's, not authored beside it:
> ```markdown
> Anchor 6:     PASS when the report records `repoint`, `route`, or `CLOSED-NO-ACTION`
>               (3 branches — matches task step 4's 3 terminal outcomes)
> ```
> Carry the parenthetical count. It is what makes the parity checkable by someone who is not re-reading both files.

**The derivation is mechanical, so it belongs at scaffold close.** Enumerate the task's terminal branches and the anchor's accepted outcomes, and compare the two sets. A mismatch in either direction is a scaffold-time failure. Fewer fails a correct execution. More is unreachable, so narrow the anchor or add the missing task branch.

**Set agreement is not count equality:** `gate-command-semantics.md` §10.8 trap 3 carries the rule against hardening set membership into an equality of totals.

**Where the branch set is written more than once, all copies are derived from the task.** The task file's Execution Steps are the source. The Execution Input and the Signoff anchor are copies, and a copy authored independently is how the sets drift apart.

`scripts/lint_gate_checks_plan.py` Check 26 flags a Signoff anchor row that lists two or more outcomes with no matching branch count. §10.10 covers the same defect for a path-set gate's allowed set.

#### Reviewer Check 095 — Anchor Enumerates Fewer Outcome Branches Than Its Task Produces

- **Severity / Role / Type:** WARNING (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** A mechanical anchor, exit criterion, or Execution Input gate MUST accept every terminal outcome its owning task's Execution Steps can produce. An anchor accepting a strict subset fails a correct execution.
- **Detection:**
  1. Open the owning task file's Execution Steps and enumerate its terminal outcomes — every branch that ends the step rather than continuing it. Include zero-hit, nothing-to-do, and already-resolved branches.
  2. Open every artifact carrying an anchor for that task: the Signoff Mechanical Anchor Checks table, the exit criteria, and the Execution Input's own gate blocks.
  3. Compare the two sets. Accepted set smaller than the task's → WARNING, escalating to ERROR where no accepted outcome remains for the branch the task will actually produce.
  4. Accepted set larger → WARNING. Either the extra branches are unreachable, or the task is missing a branch it should define.
  5. An anchor asserting set membership (`⊇`) whose expectation is written as a count equality → WARNING (`gate-command-semantics.md` §10.8 trap 3).
  6. Where two artifacts state the same branch set and disagree with each other, report against the task file's Execution Steps as the source, never against whichever copy is in the majority.
- **Finding template:**
```
[WARNING] Anchor accepts fewer outcome branches than its task produces
File: {anchor file path} | Location: {anchor row / exit criterion number}
Issue: Task {task id} Execution Steps define {N} terminal outcomes ({list}); anchor accepts {M} ({list}) — the measured-and-expected outcome `{branch}` is not accepted, so a correct execution FAILs this gate
Fix: Widen the anchor to accept all {N} branches and carry the count inline, per references/gate-anchor-outcome-set.md §10.7 | Confidence: HIGH
```

### 10.10 A re-capture gate's allowed set names the files that change on every capture

A snapshot directory holds two classes of file. Extractor-attributable files change only when the extractor or the subject binary changes. Environment-attributable files change on every capture. These are anything fetched from a network, anything that records a session or a machine, and anything that records a timing or a cost. A diff-stat gate that lists only the first class reports the second class as regression every time it runs. In one measured re-capture, three of four HALT paths per build were environment drift, and the runner spent its budget clearing them before it found the one real extractor defect.

> [!constraint] Two lists, reported separately, with the environment list derived from what the capture does
> WRONG — one allowed set, authored from the base commit's snapshot shape:
> ```
> allowed = {<subsets>.json, <tool-table>.json, manifest.json, <identity>.json}
> changed = {<changelog>.json, <session>.json, <run-report>.json, <module-strings>.json, ...}
> changed - allowed = 4 paths per build -> HALT
> # three are noise, one is signal, and the gate cannot tell them apart
> ```
> CORRECT — the extractor list and the environment list are separate, and only the remainder halts:
> ```
> extractor_allowed  = {<subsets>.json, <tool-table>.json, manifest.json, <identity>.json}
> environment_expect = {<changelog>.json, <session>.json, <run-report>.json}   # live children + network fetch
> unexpected = changed - extractor_allowed - environment_expect
> # unexpected = {<module-strings>.json} -> HALT on that one path, with the drift rows listed as expected
> ```

Three operative points:

1. **Classify every captured file at authoring time.** For each file the capture writes, ask one question: would this file change if the extractor and the binary were both frozen? If yes, it belongs in the environment list. It does not belong in the allowed list or the HALT list.
2. **Derive the environment list from the command's side effects, not from one observation.** A `--force` that runs live children rewrites their outputs. A capture that fetches a changelog rewrites the changelog. Read the capture code's write sites. A single prior capture cannot show what varies between captures.
3. **Keep the HALT rare.** A gate that always fires gets waved through. The first time a re-capture gate HALTs on noise, the runner learns to expect a HALT. The second time, the real defect is in the same list. Keep the noise out of it.

This applies to any `git diff --stat` or path-set gate over a directory a tool regenerates in place, and to any brief that pins an allowed-change set for a re-run. The optional script `scripts/path_set_gate.py` implements this path-set gate. §10.7 covers the same defect for an anchor's accepted set.

---

*Cross-references: [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) §10.2 (the gate that cannot fail, this file's mirror) · [gate-command-semantics.md](gate-command-semantics.md) §10.8 trap 3 (set membership hardened into count equality) · [exit-criteria-fidelity.md](exit-criteria-fidelity.md) §16.10.6 (the branch set is written once, in the task file, and copied) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
