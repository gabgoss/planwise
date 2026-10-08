---
description: A gate is pinned from a run over real content, never from a mental image — a gate over a verification report reads the machine-readable verdict line, never a bare substring the report's own vocabulary emits (§10.5); a pattern pinned before its subject exists is a prediction, run at the first reconciliation with the row read on zero matches (§11.1); a count gate pinned beside a content block runs over that block before the task file ships, and when they disagree the content is the deliverable and the gate is the defect (§11.2); a count method matches the command's real output shape, with a zero count a FAIL (§11.3); a verdict-line gate copies the skeleton's bytes including the emphasis between label and value, dry-run on a passing and a failing copy (§11.4); and a section is counted by a line-anchored heading test, never by substring (§11.5).
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

One adjacent shape cannot be caught by a pre-edit annotation at all, and it belongs here because its outcome is the same — a gate that does not discriminate. When a gate's subject is a **report the work itself produces**, there is no pre-edit tree to measure against: the report does not exist until the work is finished. The protection has to come from the report's format instead.

A verification report necessarily *describes* the checks it ran, so its own column headers, legend, and residual prose legitimately contain the tokens a naive gate searches for. A bare `grep -c 'FAIL' {report}` expecting `0` is satisfied by the report's own vocabulary and fires on a report that passed — and a gate that can never report success is exactly as uninformative as one that can never report failure.

[templates/verification-report.md](../templates/verification-report.md) defines the convention that removes the ambiguity: a single machine-readable trailing `**Verdict:** PASS|FAIL` line, plus per-criterion status carried in a dedicated table cell. A gate consuming a verification report MUST match the verdict line, or the `| FAIL |` row-cell pattern that `verification-report.md` defines — never a bare substring search over the whole document. Copy the verdict line's bytes from the skeleton, including the emphasis between label and value: §11.4 below.

## 11. A Gate Is Pinned From a Run Over Real Content, Never From a Mental Image

A pinned gate is a claim about the shape of something. The something may not exist yet, or it may exist in a form the author never looked at. The instrument then returns the wrong value on correct work, or cannot return its passing value at all. Each subsection below covers one way the claim fails. `gate-heuristic-verifier-patterns.md` §3 covers the sibling extraction formats a pattern must accept, and `gate-command-semantics.md` §10.9 covers reading a command as a program. This section covers the step both assume: the pinned gate was actually run over the real content.

### 11.1 A gate pinned before its subject exists is a prediction

A same-session gate is often pinned at scaffold time for a table row, a log line or a status word that an earlier task has not yet written. The pattern then encodes the author's picture of that text.

> [!constraint] Run the pinned pattern when the producer lands, and read the row on zero matches
> **Rule.** A regex written against a cell or line that does not exist yet is a prediction. Backticks, bold, a trailing space or a different first column each turn the gate into a false negative that reads like the failure it guards. Zero matches then passes through the empty-is-not-clean hazard: an empty result looks the same whether the gate scanned the subject and found nothing or could never have seen it.
>
> Three operative points:
>
> 1. **Run the pinned pattern at the first reconciliation after the producing task lands.** Do not wait for the consuming task's dispatch, where a false negative halts a paid sequence.
> 2. **On zero matches, read the row before believing either side.** The runner says present, the gate says absent, and the row decides. Re-derive the pattern from the landed text. Route the corrected pattern into the consuming task as a spec delta, with the line number it matched.
> 3. **Prefer a shape-tolerant pattern while the cell shape is not fixed.** `^\| \x60?<arm>\x60? \|` costs four characters and survives both the bare and the backticked shape. Pin the strict form only after the row has landed and been read.
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

**Applies to.** Same-session gates on a sibling task's output, pinned at scaffold time. Any grep gate over a markdown table cell, a log line or a status word whose exact rendering the producer decides. The orchestrator's own acceptance checks after a dispatch: a check that could not have seen the subject is not a pass.

### 11.2 A gate pinned beside a content block runs over that block before the task file ships

A task file sometimes pins two artifacts at once. A content block says what to write, such as a script, a config or a template. A static check beside it says what the written file will measure.

> [!constraint] Two pinned artifacts in one task file are one claim, and the claim is that they agree
> **Rule.** If the author never ran the gate over the block, the pair is untested. The runner then faces a fork the spec did not resolve: edit the content to pass the gate, or ship the content and fail the gate.
>
> Three operative points:
>
> 1. **Save the block to a scratch file and run every static check from the task file over it before the task file ships.** A gate that has never seen its subject is a claim, not a verification.
> 2. **Anchor a count on the command shape, not on a bare token.** The token occurs wherever the author mentions it, including the comment that explains it. The shape occurs only on a real call.
> 3. **When the content and its gate disagree, the content is the deliverable and the gate is the defect.** The runner ships the block as written and reports the gate. Editing the content to satisfy an unproven count is how a comment gets deleted to make a number come out.
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
> Dry run on a scratch file holding eight `--phase run --resume` lines and one comment line that contains `--resume`: the bare-token count printed 9 and the shape count printed 8.

**Applies to.** Task files that pin both a content block (a script, a config, a template) and a static check on the file it produces. Any `grep -c` gate whose token can appear in a comment, docstring, log line or echo in the same file. A plan reviewer asks, for each pinned gate: "was this run over the pinned content, and what does the count include besides the thing it is meant to count?"

### 11.3 A pinned count method matches the command's real output shape

A count method is part of a pinned command, and it can be wrong while the command is right.

> [!constraint] Pin the extraction from one observed output line, and state the shape
> **Rule.** Before pinning "count lines matching X", run the command once and look at one line of its real output. State the observed shape in the pin.
>
> **Guard.** A spec that makes a zero count a FAIL ("zero means the check saw nothing") is what exposes this class. Without that guard a count of 0 can read as clean. Keep the guard on every collection-scope count.
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

**Applies to.** Any gate that counts lines from a tool's output: test collection, `grep -c`, `git status --porcelain`, linter statistics. It matters most when one task pins the count and a later task re-runs it, and when the tool's output format depends on its version or configuration.

### 11.4 A verdict-line gate copies the skeleton's bytes, emphasis included

§10.5 says a gate over a verification report matches the verdict line, not a bare substring. This subsection says which bytes to match.

A Markdown verdict line has a rendered form and a byte form. The rendered form is what a reader sees. The byte form is what `grep` sees. Emphasis markers sit inside the byte form, and they usually fall between the label and its value. A reviewer reads both the skeleton and the gate in rendered form, and in that form they match. The failure is invisible in review.

> [!constraint] Derive the gate pattern from the skeleton's bytes, and dry-run it on the first real output
> **Rule.** An Expected Output skeleton prescribes the verdict line as `**Gate:** PASS | HALT`. The runner writes it exactly that way. A later task pinned the Before gate as `grep -c 'Gate: PASS' <snapshot>.md  # expect: 1`. The written line is `**Gate:** PASS`. Its bytes contain `Gate:** PASS`, with two asterisks between the colon and the space. The literal `Gate: PASS` is absent, so the gate returns 0 on a passing snapshot. The orchestration's acceptance text and the success criteria all repeated the rendered form. The defect sat in three places and all three agreed with each other. A stricter runner would have halted a correct run and named the upstream task as the failure.
>
> Two operative points:
>
> 1. **Copy the verdict line out of the skeleton and escape it. Do not retype it.** Include the emphasis: `grep -cF '**Gate:** PASS'`, or a regex that allows it, `grep -cE '\*\*Gate:\*\* PASS'`.
> 2. **Dry-run the gate on the first real output before a downstream task depends on it.** A verdict gate that returns 0 on the passing artifact it was written for has never discriminated. Run the pair: the passing output, and a copy with the value changed to the failing token.
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
> Dry run on a scratch snapshot reading `**Gate:** PASS`: the fixed-string form printed 1, the rendered form printed 0, and the copy reading `**Gate:** HALT` printed 0 under the fixed-string form.

Two other gates in the same task set followed the bytes and worked: `grep -c 'Result:\*\* WRITTEN'` and `grep -cE '^## Verdict: (PASS|FAIL)'`. The difference was whether the author wrote the pattern from the skeleton or from memory of the rendered line.

`scripts/lint_verification_gates.py` Check 11 fires on a verdict, gate, result or status pattern with no emphasis between label and value: ERROR when the target file writes the bold form, WARNING when the target does not exist yet.

**Applies to.** Any gate that greps a Markdown output for a verdict, status or result line: task Before and After blocks, orchestration acceptance tables, session success criteria and signoff checks. It matters most where the skeleton puts the label in bold (`**Verdict:**`, `**Result:**`, `**Gate:**`) and the value outside the bold.

### 11.5 Count a section by a line-anchored heading test, never by substring

A substring pattern answers "does this text occur". It does not answer "does this file contain this section". The two questions agree only in files that never mention the section by name. The file most likely to mention it is the plan, spec or reference that introduces the convention. That file is often among the first to adopt the convention, so the collision is structural, not a coincidence. `gate-absence-and-consistency.md` §8.1 covers scrubbing a token from every surface, and §8.2 there covers asserting against the right population. This subsection covers counting a heading.

> [!constraint] Anchor the heading at the start of the line, and record both counts when they differ
> **Rule.** A harvest appended one `## Index Notes (harvested <date>)` section to each of 32 master plans. The task pinned two substring gates: a pre-write gate `grep -c '## Index Notes (harvested'` expecting 0, and a post-write gate expecting 1 per target. One target was the plan that designed the harvest. It quotes the heading twice in prose, once in a decision row and once in a checklist line. The substring count read 2 before the write and 3 after. A line-anchored heading test read 0 before and 1 after. Without the fix, the pre-write gate halts the harvest on a clean target and the post-write gate fails a correct one.
>
> Three operative points:
>
> 1. **Test the heading at the start of the line.** In Python, test `line.startswith(b'## Index Notes (harvested ')` on each line of the file read as bytes. On a CRLF file, anchor the start of the line and never the end, because a `$` anchor fails before `\r`.
> 2. **Count per file, not files with a hit.** A file-level count such as `... | awk -F: '$NF>0' | wc -l` reads 32 either way. Only a per-file exact count exposes the extra hits.
> 3. **When the substring count and the anchored count differ, record both beside each other with the cause.** The difference is evidence that the file documents the convention. It is not noise to absorb.
>
> WRONG — a substring count: 3, one heading plus two prose mentions:
> ```bash
> grep -c '## Index Notes (harvested' <plan>.md
> ```
> CORRECT — an anchored count: 1, the heading only:
> ```bash
> grep -cE '^## Index Notes \(harvested ' <plan>.md
> ```
> Dry run on a scratch plan that quotes the heading twice in prose: before the append, the substring count printed 2 and the anchored count printed 0. After the append, they printed 3 and 1.

**Applies to.** Any gate that counts, requires or forbids a Markdown section by its heading text: harvest or append gates, "exactly one section" assertions, duplicate-heading checks and migration idempotency guards. It matters most when the target set includes the plan or reference file that defines the heading.

`scripts/lint_verification_gates.py` Check 12 fires on a pattern that starts with the heading marker and no `^`. Its Check 9 fires on the companion trap in operative point 1: a `$` anchor with no `\r?` guard, ERROR when the target carries CRLF line endings and WARNING when the target does not exist yet.

---

*Cross-references: [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §3 (the sibling extraction formats a pattern must accept) · [gate-command-semantics.md](gate-command-semantics.md) §10.9 (reading a command as a program) · [gate-absence-and-consistency.md](gate-absence-and-consistency.md) §8.1-§8.2 (scrubbing a token from every surface, asserting against the right population) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §9 (the real expected-hit line as a fixture, and a passing branch that is reachable) and §10 (a "count unchanged" gate beside an addition that shares its vocabulary) · [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) §10 obligation A (the reproduction recipe is run before it is pinned) · [templates/verification-report.md](../templates/verification-report.md) (the verdict-line convention §10.5 and §11.4 read) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
