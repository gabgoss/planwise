---
description: A Sprint exit-gate verdict reflects the gate-defining step's status, never a step-count percentage, and the Verification Commands presence checks for the section, the per-file-type table, notebooks, lint and database pre-checks (§3, Reviewer Checks 013, 014, 034, 035 and 036); the operational rules for smoke reports, the Before/After block check, and the Recovery-versus-task-spec drift practice at closeout (§4, Reviewer Check 015).
consult-when: Writing a Sprint Overview status, a smoke report or a closeout Recovery file, or reviewing a task's Verification Commands — the gate is the gate, never a step-count percentage, and the presence checks (§3, Checks 013, 014, 034, 035, 036); smoke-report rules and the Before/After block (§4, Check 015)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Exit Verdict and Smoke Reports (The Gate Is the Gate)

**Purpose:** What a Sprint Overview row, a smoke report and a closeout Recovery file may claim. "M of N smoke steps PASS" is not Sprint progress while the gate-defining step still fails, and a Verification Commands block that omits the notebook run, the lint run or the database pre-check has not been populated. Split from `verification-gates.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gates.md §N` citation translates by filename alone. The family index is `verification-gates.md`.

**Read this when** you write a Sprint Overview status, a smoke report or a Recovery file at closeout, or you review the Verification Commands of a task that touches a notebook, a lint target or a database.

## Table of Contents

- [3. The Gate Is the Gate](#3-the-gate-is-the-gate)
- [4. Operational Rules for Smoke Reports](#4-operational-rules-for-smoke-reports)

---

## 3. The Gate Is the Gate

> [!constraint] Sprint exit-gate verdicts MUST reflect the gate-defining step's status
> WRONG — partial-progress accounting that frames intermediate-step PASS counts as Sprint progress when the gate-defining step is still red. Misleads the next session into lowering follow-up bug priority because "we're closer than last time."
> ```markdown
> ## Smoke Verdict
> - Steps 1-4: PASS (component loads, transport launches, transport connects)
> - Step 5: FAIL (protocol handshake)
> - Steps 6-10: BLOCKED
> - Aggregate: PARTIAL — significant progress from S01-04 baseline
> ```
> CORRECT — the gate is binary. Intermediate-step progress is informational only; it narrows the diagnostic search space but does NOT advance the Sprint exit gate.
> ```markdown
> ## Smoke Verdict
> - Steps 1-4: PASS (component loads, transport launches, transport connects)
> - Step 5 (gate-defining): FAIL (protocol handshake)
> - Steps 6-10: BLOCKED
> - Aggregate: FAIL — gate unchanged from S01-04 baseline.
>   Intermediate-step progress narrows the search space ({backlog-id} filed
>   against handshake error path) but the Sprint exit gate is unchanged.
> ```

> [!constraint] Sprint Overview rows MUST encode gate state, not session-count fraction
> A Master Plan row that flips to ✅ COMPLETE because every session finished, while the smoke verdict is FAIL, misstates the Sprint.
> CORRECT — the row state reflects the exit-gate's verdict, not the session count.
> ```markdown
> | Sprint-01 | Threading + IPC | ⚠️ COMPLETE (verdict PARTIAL — round-trip gate FAIL, {backlog-id}) | 5 / 5 sessions |
> ```

> [!practice] Recovery vs task-spec drift at closeout
> Recovery files paraphrase task-spec scope at closeout time — that paraphrase can drift from the task spec, and downstream readers anchor on the Recovery (more recent, more accessible) rather than the original task spec. The drift manifests as **"in-scope"** silently becoming **"deferred"** between the task spec and the Recovery summary. The closeout reviewer SHOULD cross-check every "deferred" claim in the Recovery against the originating task spec's scope. If the task spec lists the item as in-scope and the Recovery defers it, that is a planning defect — re-open the session and clarify scope, do not accept the deferral.
>
> **Generalized drift example (forwarder / glue boundary):**
>
> - **Task spec (in-scope clause):** *"The routing from the outer transport to the inner consumer is the MVP glue — it may be a simple pass-through (forward every inbound call to the attached client) or defer to a future structured-routing primitive. Document the chosen approach in the Summary."*
> - **Recovery (drifted paraphrase):** *"MVP routing approach: pass-through client stored as DI singleton in the outer host. No forwarding logic implemented. Structured-routing primitive deferred to a later sprint."*
> - The Recovery conflated "no structured-routing primitive used" (a legitimate option per the task spec) with "no forwarder at all" (NOT a legitimate option per the task spec). The Sprint exit gate cleared on an internal probe against the inner consumer, bypassing the outer transport entirely; the defect surfaced days later at first contact with a real external client and was tracked back to the Recovery paraphrase, not to the implementation itself.

> [!practice] When this practice promotes to a constraint
> The practice above is **advisory**, not binding. If the drift pattern recurs — a second HIGH-severity lesson surfaces a similar Recovery-vs-task-spec drift — promote it to a new rule prescribing a mechanical cross-check at session closeout (the new rule's likely home is its own file, e.g., a `recovery-task-spec-cross-check` rule cross-linked from this section).
>
> Cost asymmetry justifies advisory standing today: days of latent in-scope work laundered as deferred vs minutes of cross-check at closeout — real but single-occurrence. On recurrence, open a Backlog item to convert this `> [!practice]` to a `> [!constraint]` with WRONG / CORRECT examples and a mechanical closeout check (grep every "deferred" claim in the Recovery against the originating task spec's in-scope list).

#### Reviewer Check 013 — Task Verification Commands Section Present

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Tasks touching code/tests/schemas MUST include `## Verification Commands` section using placeholder vocabulary.
- **Detection:** Open task; grep `^## Verification Commands` heading. If task touches `{code, test, schema, migration, notebook}` AND section absent → BLOCKER.
- **Script:** `scripts/lint_task_file_structure.py` rule `verification-section` reports `BLOCKER: [verification-section] Reviewer Check 013: …` on the Output line. Fix: append the section per `templates/task-file.md`.

#### Reviewer Check 014 — Per-File-Type Verification Table Populated

- **Severity / Role / Type:** BLOCKER | Task Reviewer | EXTEND
- **What:** Verification Commands section MUST include per-file-type table with placeholder command rows (`{lint-cmd}`, `{format-cmd}`, `{test-cmd}`, `{exec-cmd}`).
- **Detection:** Open Verification Commands section; count rows matching `{[a-z-]+-cmd}`. Zero → BLOCKER.
- **Script:** `scripts/lint_task_file_structure.py` rule `verification-section` reports `BLOCKER: [verification-section] Reviewer Check 014: …` when the section holds no `{...-cmd}` row and no concrete command, or a template slot left unfilled. Fix: add rows per `templates/task-file.md`.

#### Reviewer Check 034 — Verification Commands Notebook Execution Present

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Tasks producing/modifying `{notebook-file}` artifacts MUST include `{exec-cmd}` in Verification Commands.
- **Detection:** Grep Expected Output for notebook artifacts; grep Verification Commands for `{exec-cmd}`. Notebook output + `{exec-cmd}` absent → ERROR.
- **Script:** `scripts/lint_task_file_structure.py` rule `per-type-commands` reports `ERROR: [per-type-commands] Reviewer Check 034: …`. Fix: add an `{exec-cmd}` row per `templates/task-file.md`.

#### Reviewer Check 035 — Verification Commands Lint/Format Present

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Tasks producing/modifying code files MUST include `{lint-cmd}` AND `{format-cmd}` in Verification Commands per-file-type table.
- **Detection:** Code-producing output + missing `{lint-cmd}` OR `{format-cmd}` in Verification Commands → ERROR.
- **Script:** `scripts/lint_task_file_structure.py` rule `per-type-commands` reports `ERROR: [per-type-commands] Reviewer Check 035: …`. A section with concrete commands and no placeholder table owes a lint command only. Fix: add rows per `templates/task-file.md`.

#### Reviewer Check 036 — Verification Commands DB Pre-Check Position

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** DB-write tasks MUST include `{connectivity-check-cmd}` in `> [!verify]` "Before" block (not "After").
- **Detection:** Locate `> [!verify]` callout; check `{connectivity-check-cmd}` position. Misplaced or absent → WARNING.
- **Script:** `scripts/lint_task_file_structure.py` rule `per-type-commands` reports `WARNING: [per-type-commands] Reviewer Check 036: …`. Fix: move the check to the Before block per `references/callout-conventions.md`.

## 4. Operational Rules for Smoke Reports

> [!checklist] Smoke report aggregate-verdict line
> - [ ] Aggregate verdict reflects the gate-defining step's status, not a step-count percentage
> - [ ] If the gate-defining step is FAIL, aggregate is FAIL — regardless of how many other steps are PASS
> - [ ] Follow-up bug priority reflects the un-cleared gate, not the count of newly-passing steps
> - [ ] The Master Plan's Sprint Overview row makes the gate state explicit
> - [ ] The Recovery file's "deferred" claims are cross-checked against the originating task spec's in-scope list (see §3 practice)

#### Reviewer Check 015 — Verification `> [!verify]` Before/After Block Present

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Task files producing executable artifacts MUST include `> [!verify]` callout with Before/After bash commands.
- **Detection:** Grep `> \[!verify\]` callout (multiline). Task Expected Output declares runnable artifact (notebook, script, binary) AND callout absent → BLOCKER.
- **Script:** `scripts/lint_task_file_structure.py` rule `verify-callout` reports `BLOCKER: [verify-callout] Reviewer Check 015: …` when the callout or one of its `**Before` and `**After` lines is missing. Fix: add the callout per `references/callout-conventions.md`.

---

*Cross-references: [gate-runtime-boundary-evidence.md](gate-runtime-boundary-evidence.md) (§1-§2, the failure modes and the round-trip evidence this verdict rule sits beside) · [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Sprint exit-gate semantics in Master Plan and Sprint Plan rows) · [session-execution-protocol.md](session-execution-protocol.md) (Recovery-file update discipline at closeout) · [verification-gates.md](verification-gates.md) (the family index).*
