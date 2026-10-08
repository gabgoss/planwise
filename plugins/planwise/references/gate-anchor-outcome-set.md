---
description: An anchor accepts exactly the outcome set its own task's Execution Steps can produce — set equality derived at scaffold close, with the branch count carried inline, and never hardened into a count equality (§10.7, Reviewer Check 095); and a re-capture gate over a directory a tool regenerates in place names the environment-attributable files (fetched, session, timing, cost) apart from the extractor-attributable ones, so only the remainder halts (§10.10).
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

`gate-pre-edit-baseline.md` §10.2 catches a gate that cannot fail. This section catches the mirror defect: a gate that cannot pass. Both ship green-looking artifacts, and both report a wrong verdict on a correct execution.

An anchor is written from the outcome its author expects. A task's Execution Steps usually define more outcomes than that — a zero-hit branch, a nothing-to-do branch, an already-resolved branch. When the anchor enumerates fewer, the runner executes correctly, produces a legitimate terminal outcome, and the gate rejects it. The runner must then halt or invent a result that the anchor will accept.

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

**The derivation is mechanical, so it belongs at scaffold close.** Enumerate the task's terminal branches from its Execution Steps, enumerate the anchor's accepted outcomes, and compare the two sets. A mismatch in either direction is a scaffold-time failure:

| Direction | What it means | Fix |
|-----------|---------------|-----|
| Anchor accepts fewer than the task produces | The gate fails a correct execution | Widen the anchor to the task's full branch set |
| Anchor accepts more than the task produces | The extra branches are unreachable, so the gate is looser than it reads | Narrow the anchor, or add the missing task branch if the task is the incomplete one |

**Set agreement is not count equality.** An anchor asserting that one set contains another must not be hardened into an equality of totals. A correct execution that produces a legitimate superset then fails a gate whose real claim it satisfied. See `gate-command-semantics.md` §10.8 trap 3.

**Where the branch set is written more than once, all copies are derived from the task.** A plan typically states the outcome set in the task file, again in the Execution Input, and again in the Signoff anchor. The task file's Execution Steps are the source. The other two are copies, and a copy authored independently is how the sets drift apart.

A path-set gate over a directory a tool regenerates in place has the same shape of defect for its allowed set. See §10.10.

#### Reviewer Check 095 — Anchor Enumerates Fewer Outcome Branches Than Its Task Produces

- **Severity / Role / Type:** WARNING (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** A mechanical anchor, exit criterion, or Execution Input gate MUST accept every terminal outcome its owning task's Execution Steps can produce. An anchor accepting a strict subset fails a correct execution.
- **Severity rationale — this class false-FAILs, so it is a WARNING, not a BLOCKER.** The defects in `gate-pre-edit-baseline.md` §10.2 hide *incorrect* work behind a gate that cannot fail. This one rejects *correct* work. A false-FAIL is visible at the moment it fires and recoverable by hand, so the class sits a tier below the vacuous-gate family whatever the criterion's status. Escalate to ERROR on one condition only: the anchor's rejection leaves the runner no accepted outcome to record, so the run must either halt or manufacture a result. That is the point at which a reporting defect becomes a data-integrity one.
- **Detection:**
  1. Open the owning task file's Execution Steps and enumerate its terminal outcomes — every branch that ends the step rather than continuing it. Include zero-hit, nothing-to-do, and already-resolved branches.
  2. Open every artifact carrying an anchor for that task: the Signoff Mechanical Anchor Checks table, the exit criteria, and the Execution Input's own gate blocks.
  3. Compare the two sets. Accepted set smaller than the task's → WARNING, escalating to ERROR where no accepted outcome remains for the branch the task will actually produce.
  4. Accepted set larger → WARNING. Either the extra branches are unreachable, or the task is missing a branch it should define.
  5. An anchor asserting set membership (`⊇`) whose expectation is written as a count equality → WARNING. A correct superset fails it.
  6. Where two artifacts state the same branch set and disagree with each other, report against the task file's Execution Steps as the source, never against whichever copy is in the majority.
- **Finding template:**
```
[WARNING] Anchor accepts fewer outcome branches than its task produces
File: {anchor file path} | Location: {anchor row / exit criterion number}
Issue: Task {task id} Execution Steps define {N} terminal outcomes ({list}); anchor accepts {M} ({list}) — the measured-and-expected outcome `{branch}` is not accepted, so a correct execution FAILs this gate
Fix: Widen the anchor to accept all {N} branches and carry the count inline, per references/gate-anchor-outcome-set.md §10.7 | Confidence: HIGH
```

### 10.10 A re-capture gate's allowed set names the files that change on every capture

A snapshot directory holds two classes of file. Extractor-attributable files change only when the extractor or the subject binary changes. Environment-attributable files change on every capture. These are anything fetched from a network, anything that records a session or a machine, and anything that records a timing or a cost. A diff-stat gate that lists only the first class reports the second class as regression every time it runs.

A task re-captured three archived builds with `<capture-command> --force`. It then ran a `git diff --stat` gate against a pinned allowed set of four paths. Any other changed path was a HALT. The gate fired on four paths per build:

- Three were environment drift the extractor never touches. A changelog file changed because an upstream entry had been published since the base commit. A session-record file changed because of session ids and the machine's installed-skill roster. A run-report file changed because of elapsed milliseconds and total cost.
- The fourth, a module-strings file, was a real extractor defect.

The runner spent its investigation budget proving the three drift rows harmless before it could isolate the one that mattered. The allowed set had been authored from one capture at plan time. The author knew the live tier ran two child processes per build and even budgeted their cost. Nothing in the brief connected "runs live children" to "rewrites the files those children produce".

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

This applies to any `git diff --stat` or path-set gate over a directory a tool regenerates in place. It applies to snapshot, fixture, golden-file and report directories that mix extracted content with session, timing, cost or fetched data. It also applies to any brief that pins an allowed-change set for a re-run.

§10.7 covers the same defect for an anchor: the accepted set must equal the set of outcomes the task can produce. This subsection covers the allowed set of changed paths. The allowed set must also cover the files the capture rewrites as a side effect.

---

*Cross-references: [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) §10.2 (the gate that cannot fail, this file's mirror) · [gate-command-semantics.md](gate-command-semantics.md) §10.8 trap 3 (set membership hardened into count equality) · [exit-criteria-fidelity.md](exit-criteria-fidelity.md) §16.10.6 (the branch set is written once, in the task file, and copied) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
