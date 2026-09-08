# Sprint Signoff Template

Use this template when closing out a sprint as `{Abbrev}-S{XX}-Sprint-Signoff.md` placed in the sprint folder (same level as `{Abbrev}-S{XX}-Sprint-Plan.md`).

---

```markdown
# Sprint Signoff — {Abbrev}-S{XX}: {Sprint Name}

**Sprint ID:** {Abbrev}-S{XX}
**Sprint Name:** {Sprint Name}
**Signoff Date:** {YYYY-MM-DD}
**Signoff Agent:** {agent or user name}

---

## Sprint Objective <!-- copy verbatim from Sprint Plan -->

{verbatim quote of Sprint Plan Objective section}

---

## Sessions Completed

| Session ID | Name | Verdict | Notes |
|------------|------|---------|-------|
| {Abbrev}-S{XX}-01 | {Session-01 Name} | {PASS \| PARTIAL \| FAIL} | {1-line note} |
| {Abbrev}-S{XX}-02 | {Session-02 Name} | {PASS \| PARTIAL \| FAIL} | {1-line note} |

---

## EI Exit Criteria (verbatim quote)

> [!constraint] Verbatim EI Exit Criteria
> Quote each exit criterion verbatim from this sprint's Execution Input file. NO paraphrasing. See `references/exit-criteria-fidelity.md` §16.3 for the binding rule.

```
{verbatim block of EI exit criteria, e.g.:
- [ ] All schema migrations applied
- [ ] {row_count} records inserted into `{table}`
- [ ] Round-trip test passes for {ipc-transport} channel}
```

---

## Mechanical Anchor Checks

For each exit criterion, document the mechanical anchor (grep / SQL / file presence) that verifies it. One row per criterion. Re-run BLI-cited anchors at signoff time even if previously checked (per `references/exit-criteria-fidelity.md` §16.3).

> [!constraint] A deliverable-count criterion anchors on the Sprint Plan table, never on a copied total
> A criterion reading "all {N} deliverables landed" carries a number copied from somewhere else. Its anchor MUST resolve that number against the Sprint Plan's own `## Deliverables` table. Anchoring it on another copy of {N} confirms the copy, not the work.
>
> WRONG — the anchor names a second copy: `11 items in the Orchestration checklist`.
> CORRECT — the anchor counts the source rows, then checks each one: `count the rows of {Abbrev}-S{XX}-Sprint-Plan.md ## Deliverables (must equal its stated Total), then verify each row's artifact`.
>
> When a criterion states a decomposition ("{a} edits + {b} creates"), verify the classes sum to the table's total before recording PASS. A decomposition that does not sum means two artifacts are counting different sets.
>
> The `verified-absent` class is the usual cause of a mismatch. Read the Sprint Plan's stated ledger treatment for that class. Never infer it. See `references/exit-criteria-fidelity.md` §16.10.5.

> [!constraint] Every anchor is dry-run against the pre-change tree before it ships
> An anchor written from the expected landed state has never been shown to discriminate. Run each one against the **pre-change** tree at scaffold close and record the value it returned in the Pre-Change column.
>
> **An anchor that PASSES pre-change is a scaffold-time failure, not a warning.** It returns the same verdict on an untouched tree as on a finished one, so nothing the sprint does or fails to do can move it. Rewrite it — raise the threshold past the measured baseline, or narrow the pattern to what the work introduces. Do not ship it with a caveat.
>
> The recorded pre-change value doubles as the Before baseline. An anchor asserting a delta ("unchanged vs Before", "Before + 1") without one cannot be computed, and a runner then reports the absolute number and calls it PASS.
>
> A preservation anchor, where `pre == post` is the intended outcome, is exempt — write `invariant: {N}` in the Pre-Change cell instead of a bare value. See `references/verification-task-authoring.md` §10.

> [!constraint] Each anchor accepts every terminal outcome its owning task can produce
> Enumerate the owning task's terminal branches from its Execution Steps, then check that this anchor accepts all of them. Carry the count in the Branches column as `{accepted}/{task}`.
>
> The two numbers MUST match. An anchor accepting fewer fails a correct execution, and the runner must halt or manufacture an outcome the anchor will take. Zero-hit, nothing-to-do, and already-resolved branches are the ones most often dropped, and they are frequently the expected outcome.
>
> Never harden a set-membership claim into an equality of counts — a correct superset then fails a gate whose actual claim it satisfied. See `references/verification-task-authoring.md` §10.7.

> [!constraint] New behaviour anchors on a production caller, never on a definition
> For a criterion that lands a new function, optional parameter, CLI flag, config key, event subscription or guarded branch, the Mechanical Anchor is a call-site search over production paths that names the activating argument or the registration, and the Result cell quotes the site as `{file}:{line}`. A definition search, a unit test that supplies the argument itself, and documentation of the flag all measure presence and stay green on code production never reaches; a criterion whose only anchor is one of those is not PASS. See `references/verify-caller-before-complete.md`.

Before recording any Result, check each anchor's command against the four traps in `references/verification-task-authoring.md` §10.8: `grep -c` counts matching **lines** rather than matches, `-B1`/`-A1` emit the match line itself, a set-membership claim must not become a count equality, and every path MUST resolve from the cwd this table's own header declares.

| # | Exit Criterion (verbatim) | Mechanical Anchor | Pre-Change | Branches | Result |
|---|---------------------------|-------------------|-----------|----------|--------|
| 1 | {Criterion 1 verbatim} | `grep -c "{pattern}" {file}` (expect: ≥ 1) | 0 | 2/2 | PASS / FAIL |
| 2 | {Criterion 2 verbatim} | `SELECT COUNT(*) FROM {table} WHERE …` (expect: ≥ {N}) | {measured} | {a}/{b} | PASS / FAIL |
| 3 | {Criterion 3 verbatim} | File exists: `{path}` | absent | 1/1 | PASS / FAIL |

**Pre-Change** — the value the anchor returned against the pre-change tree, or `invariant: {N}` for a preservation anchor. A value that already satisfies the anchor's expectation is a failure to fix, not a result to record.
**Branches** — `{outcomes this anchor accepts}/{terminal branches the owning task defines}`. The two MUST be equal.

---

## Verdict

> [!gate] Sprint Exit Gate
> Verdict reflects the **gate-defining step's status**, not step-count percentage (per `references/verification-gates.md` §3 "The Gate Is the Gate").

**Verdict:** {PASS \| PARTIAL \| FAIL}

**Rationale:**
- Gate-defining step: {1-line description}
- Step status: {COMPLETE / INCOMPLETE / FAILED}
- All other steps: {N of M COMPLETE} (informational only)

> [!constraint] Verdict Encoding
> WRONG: "Sprint PASSES — 4 of 5 steps COMPLETE (80 %)"
> CORRECT: "Sprint FAILS — round-trip test did not run" / "Sprint PASSES — gate-defining round-trip test PASS; all dependent steps PASS"

---

## Round-Trip Evidence <!-- required for IPC/protocol/codec sessions -->

> [!gate] Round-Trip Evidence Requirement
> If this sprint contains IPC/protocol/codec sessions, ONE of these three evidence forms MUST be present (per `references/verification-gates.md` §1):

- **Form A — In-process integration test:** {test name + result}
- **Form B — Manual smoke step:** {documented commands + observed output}
- **Form C — Round-trip unit test stub:** {stub file path}

If none of A/B/C applies (no IPC/protocol/codec sessions), state "N/A — no IPC/protocol/codec sessions in this sprint."

---

## Sprint Overview Row Encoding

> [!practice] Sprint Overview Row vs Master Plan Status
> The Sprint Overview row state reflects the **exit-gate verdict**, NOT the session-count fraction (per `references/verification-gates.md` §4). When this signoff records PASS, update the Master Plan's Sprint Overview row Status to COMPLETE. PARTIAL or FAIL retains IN_PROGRESS until remediated.

Master Plan Sprint Overview row to update:
```
| {Abbrev}-S{XX} | {Sprint Name} | {Status: COMPLETE | IN_PROGRESS} | {Signoff Date} |
```

---

## Sign-off Notes

{Free-form notes: deferred items, follow-ups, lessons-learned candidates.

If actionable follow-ups exist, encode them as declarative `> [!followup]` blocks so /planwise backlog Phase 7 can auto-surface them at next triage:

> [!followup] Follow-Up Recommendation
> **Recommendation:** {1-line action}
> **Target file:** {path}
> **Severity:** {high | medium | low}
> **Originating item:** {Sprint ID}
}
```

---

## Naming Convention

**Pattern:** `{Abbrev}-S{XX}-Sprint-Signoff.md`

**Location:** Sprint folder (same level as `{Abbrev}-S{XX}-Sprint-Plan.md`).

**Example:** `PI-S03-Sprint-Signoff.md`

---

## When to Use

- When a sprint completes and the Master Plan Sprint Overview row needs a verdict
- Whenever a sprint contains IPC / protocol / codec sessions (round-trip evidence requirement)
- Whenever exit criteria are quoted and verified mechanically (most multi-sprint scaffolded plans)

For trivial single-sprint plans without exit criteria, the signoff file is optional. For all multi-sprint scaffolded plans, the signoff is REQUIRED per `references/exit-criteria-fidelity.md` §16.3.
