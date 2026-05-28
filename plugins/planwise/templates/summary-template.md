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

*Mirror every row from the Recovery file's `Scope-Expansion Decisions` section here, with a link back to the Phase-1 approval reference. Omit this subsection entirely if no expansions occurred. See [references/session-execution-protocol.md §1.2](../references/session-execution-protocol.md#12-structural-findings-beyond-literal-scope).*

| Step | Literal Scope | Expanded Scope | Why It Was Expanded | Phase-1 Approval Ref |
|------|---------------|----------------|---------------------|----------------------|
| - | - | - | - | - |

Each row MUST link to the corresponding Recovery row (same Step number) so later reviewers can reconcile the post-session diff against the user-approved scope without re-deriving the rationale.

### Cross-Task Coordination Flags

*Mirror every row from the Recovery file's `Cross-Task Coordination Flags` section here, alongside the file path where the flag was propagated at closeout. Omit this subsection entirely if no flags were surfaced. See [references/session-execution-protocol.md §1.3](../references/session-execution-protocol.md#13-cross-task-coordination-flags).*

| Flag # | Source Task | Downstream Consumer | Observation | Propagated To |
|--------|-------------|---------------------|-------------|---------------|
| - | - | - | - | - |

The `Propagated To` column MUST name the destination file (task / orchestration / sprint plan / master plan) where the flag was added at closeout. A flag with no propagation destination is a closeout error — it means the constraint stayed buried in upstream Recovery.

---

## Next Session

**Ready for:** Session-{YY+1}-{NextSessionName}
**Dependencies satisfied:** Yes / No (explain if No)
**Blocking issues:** None / {list if any}
