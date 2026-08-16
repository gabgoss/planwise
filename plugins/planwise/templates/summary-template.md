# Session Summary Template

Use this template when generating the session summary at session closeout, written to `Outputs/{Abbrev}-S{XX}-{YY}-Summary.md` (per [orchestration.md](orchestration.md)'s Post-Session Checklist).

---

```markdown
# Session Summary: {Abbrev}-SXX-YY - {Session Name}

**Completed:** {YYYY-MM-DD HH:MM}
**Sprint:** Sprint-{XX}-{SprintName}
**Status:** COMPLETE

---

## Tasks Completed

| # | Task | Agent | Status | Notes |
|---|------|-------|--------|-------|
| 1 | {Task name} | {Agent} | COMPLETE | {brief result} |
| 2 | {Task name} | {Agent} | COMPLETE | {brief result} |

---

## Key Deliverables

| Type | File Path | Description |
|------|-----------|-------------|
| {type} | `{path}` | {description} |

---

## Issues Encountered

| Issue | Severity | Resolution |
|-------|----------|------------|
| {issue description} | {A/B/C/D} | {how resolved} |
| None | - | - |

---

## Verification Results

| Check | Result | Notes |
|-------|--------|-------|
| Build | Pass | No errors |
| Tests (if applicable) | Pass / N/A | {notes} |
| Manual verification | Pass | {what was tested} |
| Destructive-diff adversarial review | Pass / N/A | If the diff adds/widens a delete/overwrite/migrate/prune/sweep disposition: pre-commit adversarial review run as a gate distinct from script verification, findings fixed, regression tests added. N/A if no destructive disposition. |

---

## Success Criteria Status

| Criterion | Status |
|-----------|--------|
| {criterion from Orchestration} | Met |

---

## Context Notes for Next Session

- {Any important context that should carry forward}
- {Dependencies or blockers for next session}
- {Decisions made that affect future work}

### Scope-Expansion Decisions

*Mirror every row from the Recovery file's `Scope-Expansion Decisions` section here, with a link back to the Phase-1 approval reference. Omit this subsection entirely if no expansions occurred. See [references/read-confirm-act-protocol.md §1.2](../references/read-confirm-act-protocol.md#12-structural-findings-beyond-literal-scope).*

| Step | Literal Scope | Expanded Scope | Why It Was Expanded | Phase-1 Approval Ref |
|------|---------------|----------------|---------------------|----------------------|
| - | - | - | - | - |

Each row MUST link to the corresponding Recovery row (same Step number) so later reviewers can reconcile the post-session diff against the user-approved scope without re-deriving the rationale.

### Cross-Task Coordination Flags

*Mirror every row from the Recovery file's `Cross-Task Coordination Flags` section here, alongside the file path where the flag was propagated at closeout. Omit this subsection entirely if no flags were surfaced. See [references/read-confirm-act-protocol.md §1.3](../references/read-confirm-act-protocol.md#13-cross-task-coordination-flags).*

| Flag # | Source Task | Downstream Consumer | Observation | Propagated To |
|--------|-------------|---------------------|-------------|---------------|
| - | - | - | - | - |

The `Propagated To` column MUST name the destination file (task / orchestration / sprint plan / master plan) where the flag was added at closeout. A flag with no propagation destination is a closeout error — it means the constraint stayed buried in upstream Recovery.

---

## Consumption Record

<!-- Field semantics defined ONCE here; every citing surface (the Recovery template's per-task rows,
     session-execution-protocol.md's post-session checklist, agents/plan-reviewer.md's Task Reviewer
     checklist, and its references/review-classification.md mirror) cites this section by name and
     never restates the field list.
     Every measured field carries the tag `measured|estimated` (spelled exactly this way) so a reader
     can tell a harness-reported number from a self-estimated one at a glance.
     `orchestrator_window_total` and `summed_dispatch_budgets` are STRUCTURALLY SEPARATE fields and are
     NEVER summed — one is the orchestrator's own window, the other is the sum of what was handed to
     dispatched agents; conflating them is the aggregate-vs-window confusion this record exists to end. -->

| Field | Value |
|-------|-------|
| `orchestrator_window_total` | {N} tokens ({measured\|estimated}) |
| `summed_dispatch_budgets` | {N} tokens ({measured\|estimated}) — kept distinct from `orchestrator_window_total`, never summed with it |
| `subcommand` | {plan / run / review / backlog / ...} |
| `execution_mode` | {DIRECT / DELEGATED} |
| `injected_rule_volume` | {N} tokens / Not observed |
| `turn_count` | {N} |
| `dispatch_ids` | {one id per dispatched agent, comma-separated — the join key the transcript side lacks / None (DIRECT mode)} |

---

## Next Session

**Ready for:** Session-{YY+1}-{NextSessionName}
**Dependencies satisfied:** Yes / No (explain if No)
**Blocking issues:** None / {list if any}

---

## 8. Lessons Learned

{Bullet list of LL-{NNN} entries created this session, OR the literal text "No lessons captured this session." if none captured.}
```

---

## Naming Convention

**Pattern:** `{Abbrev}-S{XX}-{YY}-Summary.md`

**Location:** `Outputs/` (same session folder as the task files it summarizes).

**Example:** `PI-S01-01-Summary.md`
