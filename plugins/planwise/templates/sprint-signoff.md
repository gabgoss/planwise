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
> Quote each exit criterion verbatim from this sprint's Execution Input file. NO paraphrasing. See `references/discovery-and-exit-criteria.md` §16.3 for the binding rule.

```
{verbatim block of EI exit criteria, e.g.:
- [ ] All schema migrations applied
- [ ] {row_count} records inserted into `{table}`
- [ ] Round-trip test passes for {ipc-transport} channel}
```

---

## Mechanical Anchor Checks

For each exit criterion, document the mechanical anchor (grep / SQL / file presence) that verifies it. One row per criterion. Re-run BLI-cited anchors at signoff time even if previously checked (per `references/discovery-and-exit-criteria.md` §16.3).

| # | Exit Criterion (verbatim) | Mechanical Anchor | Result |
|---|---------------------------|-------------------|--------|
| 1 | {Criterion 1 verbatim} | `grep -c "{pattern}" {file}` (expect: ≥ 1) | PASS / FAIL |
| 2 | {Criterion 2 verbatim} | `SELECT COUNT(*) FROM {table} WHERE …` (expect: ≥ {N}) | PASS / FAIL |
| 3 | {Criterion 3 verbatim} | File exists: `{path}` | PASS / FAIL |

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

For trivial single-sprint plans without exit criteria, the signoff file is optional. For all multi-sprint scaffolded plans, the signoff is REQUIRED per `references/discovery-and-exit-criteria.md` §16.3.
