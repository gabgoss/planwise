---
description: A gate is pinned from a run over real content, never from a mental image — a gate over a verification report reads the machine-readable verdict line, never a bare substring the report's own vocabulary emits (§10.5); a pattern pinned before its subject exists is a prediction, run at the first reconciliation with the row read on zero matches (§11.1); a count gate pinned beside a content block runs over that block before the task file ships, and when they disagree the content is the deliverable and the gate is the defect (§11.2); a count method matches the command's real output shape, with a zero count a FAIL (§11.3); a verdict-line gate copies the skeleton's bytes including the emphasis between label and value, dry-run on a passing and a failing copy (§11.4); and a section is counted by a line-anchored heading test, never by substring (§11.5).
consult-when: The thing a gate measures does not exist yet, sits in a content block you wrote, or comes from a tool whose output you have not seen — a verdict line is read by its machine-readable form (§10.5) and its skeleton bytes (§11.4), a pattern pinned before its subject exists is re-run when the producer lands (§11.1), a count beside a content block is run over that block (§11.2), a count method matches the real output shape (§11.3), a heading is counted by a line-anchored test (§11.5)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Pinned From a Run Over Real Content

**Purpose:** A pinned gate is a claim about the shape of something. The something may not exist yet, or it may exist in a form the author never looked at. The instrument then returns the wrong value on correct work, or cannot return its passing value at all. Each section covers one way the claim fails. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you pin a regex, a count, a count method or a reproduction command in a task file and the thing it measures does not exist yet, sits in a content block you wrote, or comes from a tool whose output you have not looked at. Read §10.5 and §11.4 when a gate greps a Markdown verdict line, and §11.5 when a gate counts a section by its heading.

## Table of Contents

  - [10.5 A gate over a verification report reads the verdict line, not a bare substring](#105-a-gate-over-a-verification-report-reads-the-verdict-line-not-a-bare-substring)
- [11. A Gate Is Pinned From a Run Over Real Content, Never From a Mental Image](#11-a-gate-is-pinned-from-a-run-over-real-content-never-from-a-mental-image)
  - [11.1 A gate pinned before its subject exists is a prediction](#111-a-gate-pinned-before-its-subject-exists-is-a-prediction)
  - [11.2 A gate pinned beside a content block runs over that block before the task file ships](#112-a-gate-pinned-beside-a-content-block-runs-over-that-block-before-the-task-file-ships)
  - [11.3 A pinned count method matches the command's real output shape](#113-a-pinned-count-method-matches-the-commands-real-output-shape)
  - [11.4 A verdict-line gate copies the skeleton's bytes, emphasis included](#114-a-verdict-line-gate-copies-the-skeletons-bytes-emphasis-included)
  - [11.5 Count a section by a line-anchored heading test, never by substring](#115-count-a-section-by-a-line-anchored-heading-test-never-by-substring)

---

### 10.5 A gate over a verification report reads the verdict line, not a bare substring

A report the work itself produces has no pre-edit tree, and its own headers, legend and prose legitimately contain the tokens a naive gate searches for. [templates/verification-report.md](../templates/verification-report.md) defines a single machine-readable trailing `**Verdict:** PASS|FAIL` line and a per-criterion `| FAIL |` table cell.

> [!constraint] Match the verdict line, never the report's vocabulary
> **Rule.** A gate consuming a verification report MUST match the verdict line, or the `| FAIL |` row-cell pattern that `verification-report.md` defines — never a bare substring search over the whole document. Copy the verdict line's bytes from the skeleton, including the emphasis between label and value: §11.4 below.
>
> WRONG — a bare substring over the whole report, satisfied by the report's own legend:
> ```bash
> grep -c 'FAIL' <report>.md      # expect 0; fires on a passing report whose legend says FAIL
> ```
> CORRECT — the machine-readable verdict line, copied from the skeleton:
> ```bash
> grep -cF '**Verdict:** PASS' <report>.md   # 1 on a passing report, 0 on a failing one
> ```

## 11. A Gate Is Pinned From a Run Over Real Content, Never From a Mental Image

A pinned gate is a claim about the shape of something. The something may not exist yet, or it may exist in a form the author never looked at. The instrument then returns the wrong value on correct work, or cannot return its passing value at all. Each subsection below covers one way the claim fails. `gate-heuristic-verifier-patterns.md` §3 covers the sibling extraction formats a pattern must accept, and `gate-command-semantics.md` §10.9 covers reading a command as a program. This section covers the step both assume: the pinned gate was actually run over the real content.

> [!constraint] Run the pinned gate once over the real content before it is trusted
> **Rule.** A gate is pinned from a run over real content, never from the author's picture of that content. A gate that has never seen its subject is a claim, not a verification.
>
> WRONG — the gate is typed from memory of what the subject will look like, and shipped unrun:
> ```
> pin:      grep -c '<pattern>' <subject>   # expect N, from the author's picture of <subject>
> run:      never, until the consuming task depends on it
> ```
> CORRECT — the gate is run once over the real subject, and the observed result is what gets pinned:
> ```
> run:      grep -c '<pattern>' <subject>   # observed N on the real file
> pin:      the same line, with the observed value and the line it matched
> ```

### 11.1 A gate pinned before its subject exists is a prediction

A same-session gate is often pinned at scaffold time for a table row, a log line or a status word that an earlier task has not yet written.

> [!constraint] Run the pinned pattern when the producer lands, and read the row on zero matches
> **Rule.** A regex written against a cell or line that does not exist yet is a prediction. Backticks, bold, a trailing space or a different first column each turn it into a false negative, and zero matches then hits the empty-is-not-clean hazard.
>
> 1. **Run the pinned pattern at the first reconciliation after the producing task lands**, not at the consuming task's dispatch.
> 2. **On zero matches, read the row before believing either side.** Re-derive the pattern from the landed text and route it into the consuming task as a spec delta, with the line number it matched.
> 3. **Prefer a shape-tolerant pattern while the cell shape is not fixed**, such as `^\| \x60?<arm>\x60? \|`.
>
> WRONG — the gate and the acceptance check share the imagined shape. Both return nothing. The runner is overruled:
> ```
> pinned:   ^\| <arm> \|.*\| (PASS|FAIL|not completed)   → 0 matches
> accept:   ^\| <arm> \|                                  → 0 matches
> runner:   "results row grep confirms <arm> row present"  → ignored
> ```
> CORRECT — zero matches sends the orchestrator to the row. The pattern is re-derived and routed:
> ```
> accept:   ^\| <arm> \|                                  → 0 matches
> Read <results file> ## Arms                             → line 106: | `<arm>` | ...
> re-derive: ^\| `<arm>` \|.*\| (PASS|FAIL|not completed) \|   → 1 match
> route:    <consuming task> flags it — "the un-backticked pattern matches nothing; use this one"
> ```

### 11.2 A gate pinned beside a content block runs over that block before the task file ships

A task file sometimes pins a content block (a script, a config, a template) and a static check on the file it produces.

> [!constraint] Two pinned artifacts in one task file are one claim, and the claim is that they agree
> **Rule.** Save the block to a scratch file and run every static check from the task file over it before the task file ships.
>
> 1. **Anchor a count on the command shape, not on a bare token.** The token also occurs in the comment that explains it.
> 2. **When the content and its gate disagree, the content is the deliverable and the gate is the defect.** The runner ships the block as written and reports the gate.
>
> WRONG — the block and the gate are each true in isolation and were never run together:
> ```
> Step 2:   rem Every step is --resume, so a kill loses nothing …
>           python <driver> --phase run --resume … (x8)
> Verify:   grep -c -- '--resume' <script>.cmd   # expect 8
> Runner:   9. Which one is the spec?
> ```
> CORRECT — the author ran the check over the block before pinning it, and the pattern names the command:
> ```
> Verify:   grep -c -- '--phase run --resume' <script>.cmd   # expect 8 (one per driver call; the rem header also says --resume and is excluded by the shape)
> Author:   saved the block to scratch, ran the line, saw 8, pinned it
> ```

### 11.3 A pinned count method matches the command's real output shape

A count method is part of a pinned command, and it can be wrong while the command is right.

> [!constraint] Pin the extraction from one observed output line, and state the shape
> **Rule.** Before pinning "count lines matching X", run the command once, read one observed output line, and state its shape in the pin. Keep a guard that makes a zero count a FAIL ("zero means the check saw nothing") on every collection-scope count.
>
> WRONG — pin the extraction from memory of the tool's usual output:
> ```
> <runner> --collect-only -q  →  count lines containing "::"   # 0 here: no :: lines exist
> ```
> CORRECT — pin the extraction from one observed output line, and state the shape:
> ```
> <runner> --collect-only -q  →  lines look like "<dir>/<file>.py: 42"
> inside  = sum of the trailing counts on lines starting "<dir>/"
> outside = count of non-blank lines not starting "<dir>/"
> ```

### 11.4 A verdict-line gate copies the skeleton's bytes, emphasis included

A Markdown verdict line's byte form carries emphasis markers between label and value, which the rendered form a reviewer reads does not show.

> [!constraint] Derive the gate pattern from the skeleton's bytes, and dry-run it on the first real output
> **Rule.** Copy the verdict line out of the skeleton and escape it, emphasis included — never retype it from the rendered line.
>
> 1. **Match the bytes:** `grep -cF '**Gate:** PASS'`, or a regex that allows the emphasis, `grep -cE '\*\*Gate:\*\* PASS'`.
> 2. **Dry-run the gate on the first real output before a downstream task depends on it**, on the passing output and on a copy with the value changed to the failing token.
>
> WRONG — the pattern is typed from the rendered line:
> ```bash
> # skeleton says:  **Gate:** PASS | HALT
> grep -c 'Gate: PASS' <snapshot>.md      # 0 on a passing file
> ```
> CORRECT — the bytes are copied from the skeleton, and both arms are run:
> ```bash
> grep -cF '**Gate:** PASS' <snapshot>.md  # 1 on the passing file
> grep -cF '**Gate:** PASS' known-bad.md   # 0 on a copy reading **Gate:** HALT
> ```

`scripts/lint_verification_gates.py` Check 11 fires on a verdict, gate, result or status pattern with no emphasis between label and value: ERROR when the target file writes the bold form, WARNING when the target does not exist yet.

### 11.5 Count a section by a line-anchored heading test, never by substring

A substring pattern answers "does this text occur", not "does this file contain this section", and the plan or reference that introduces a heading is the file most likely to quote it in prose. `gate-absence-and-consistency.md` §8.1 and §8.2 cover scrubbing a token and asserting against the right population.

> [!constraint] Anchor the heading at the start of the line, and record both counts when they differ
> **Rule.** Test the heading at the start of the line, and on a CRLF file anchor the start of the line and never the end, because a `$` anchor fails before `\r`.
>
> 1. **Count per file, not files with a hit.** Only a per-file exact count exposes the extra prose hits.
> 2. **When the substring count and the anchored count differ, record both beside each other with the cause.** The difference is evidence that the file documents the convention.
>
> WRONG — a substring count: 3, one heading plus two prose mentions:
> ```bash
> grep -c '## Index Notes (harvested' <plan>.md
> ```
> CORRECT — an anchored count: 1, the heading only:
> ```bash
> grep -cE '^## Index Notes \(harvested ' <plan>.md
> ```

`scripts/lint_verification_gates.py` Check 12 fires on a pattern that starts with the heading marker and no `^`. Its Check 9 fires on the companion trap in the rule: a `$` anchor with no `\r?` guard, ERROR when the target carries CRLF line endings and WARNING when the target does not exist yet.

---

*Cross-references: [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §3 (the sibling extraction formats a pattern must accept) · [gate-command-semantics.md](gate-command-semantics.md) §10.9 (reading a command as a program) · [gate-absence-and-consistency.md](gate-absence-and-consistency.md) §8.1-§8.2 (scrubbing a token from every surface, asserting against the right population) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §9 (the real expected-hit line as a fixture, and a passing branch that is reachable) and §10 (a "count unchanged" gate beside an addition that shares its vocabulary) · [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) §10 obligation A (the reproduction recipe is run before it is pinned) · [templates/verification-report.md](../templates/verification-report.md) (the verdict-line convention §10.5 and §11.4 read) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
