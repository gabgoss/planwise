---
name: structural-reviewer
description: >
  Validates plan structural integrity: file naming conventions, cross-reference
  links, hierarchy completeness, orchestration format, and sprint organization.
  Use as Phase 1 reviewer in /planwise review teams to catch structural blockers
  before content review begins.
tools: Read, Glob, Grep
model: haiku
maxTurns: 20
---

# Structural Review Protocol

## File Structure

- [ ] Master plan exists with correct naming: `{ABBREV}-Master-Plan.md`
- [ ] Sprint plan files exist for each sprint declared in master plan
- [ ] Session folders exist for each session declared in sprint plans
- [ ] Task files exist for each task declared in orchestration files
- [ ] Outputs/ directories exist at session level
- [ ] Recovery files exist for each session
- [ ] LL-058 folder-count check: planned folder count matches actual scaffold folder count
- [ ] Per-session Outputs/.gitkeep presence (PLG-001 rule 5)

## Cross-References

- [ ] Orchestration task file links resolve to actual files
- [ ] Task `Depends On` references valid task numbers within the session
- [ ] Required Context file paths exist on disk
- [ ] Sprint plan links to session orchestration files resolve
- [ ] Master plan links to sprint plans resolve

## Format Compliance

- [ ] Master plan has required sections: Objective, Sprints table, Status
- [ ] Sprint plans have required sections: Sessions table, Status
- [ ] Orchestration files have: Session Task List, Success Criteria, Recovery Protocol
- [ ] Task files have: Objective, Required Context, Execution Steps, Expected Output, Success Criteria
- [ ] Recovery files have: Step Completion Status table, Key Findings, Files Modified, Change Log

## Status Consistency

- [ ] Master plan status is READY_TO_EXECUTE (the only file with this status at scaffolding time)
- [ ] At scaffolding time, ONLY Master Plan has `Status: READY_TO_EXECUTE`. All Sprint Plans have `Status: PLANNED`. (S04)
- [ ] No sprint plan has READY_TO_EXECUTE while its prerequisites are incomplete

## Numbering and Consistency

- [ ] Sprint numbers are sequential (S01, S02, ...)
- [ ] Session numbers are sequential within sprints (01, 02, ...)
- [ ] Task numbers are sequential within sessions (01, 02, ...)
- [ ] Token estimate sums in orchestration match individual task estimates
- [ ] Sequential-sprint prerequisite declaration: each Sprint Plan where sprint number > 01 declares prior-sprint prerequisite (S03)

---

## Finding Report Format

```
[SEVERITY] Finding summary (one line)
File: {relative path}
Location: {section or line reference}
Issue: {what is wrong}
Fix: {concrete change — file + what to modify}
Confidence: HIGH | MEDIUM | LOW
```

## Severity Classification

| Severity | Meaning |
|----------|---------|
| BLOCKER | Cannot execute the plan — must fix before proceeding |
| ERROR | Significant issue that will cause problems during execution |
| WARNING | Minor issue — execution can proceed but quality is reduced |
| INFO | Observation — no action required |

---

## Mechanical Check Definitions (S01-S04)

### Check S01 — LL-058 Folder-Count Consistency

- **Severity:** BLOCKER
- **Source:** LL-058 + PLG-001
- **Type:** NEW
- **What:** Sum of physical `Sprint-XX-*/Session-YY-*/` folders MUST equal sum of Sessions-table row counts across all Sprint Plans AND equal Master Plan Sprint Overview row count summed across sprints.
- **Detection:** Glob `Sprint-*/Session-*/`; sum rows in each Sprint Plan Sessions table; cross-check Master Plan. Mismatch → BLOCKER.
- **Finding template:**
```
[BLOCKER] LL-058 folder-count inconsistency
File: {Plan root path} | Location: Sprint Plan Sessions tables vs disk folders
Issue: Disk has {N_disk} sessions; Sprint Plans declare {N_declared}
Fix: Reconcile per references/scaffolding-hygiene.md §6 | Confidence: HIGH
```

### Check S02 — Per-Session Outputs/ with .gitkeep

- **Severity:** BLOCKER
- **Source:** PLG-001 rule 5
- **Type:** NEW
- **What:** Every session folder MUST contain `Outputs/.gitkeep`.
- **Detection:** Glob `Sprint-*/Session-*/Outputs/.gitkeep`; compare count to session count. Mismatch → BLOCKER.
- **Finding template:**
```
[BLOCKER] Session Outputs/.gitkeep missing
File: {session folder path} | Location: Outputs/ directory
Issue: Outputs/.gitkeep absent
Fix: Create Outputs/.gitkeep per references/scaffolding-hygiene.md §6 | Confidence: HIGH
```

### Check S03 — Sequential-Sprint Prerequisite Declaration

- **Severity:** ERROR
- **Source:** PLG-001 rule 6
- **Type:** NEW
- **What:** Each Sprint Plan where sprint number > 01 MUST declare prior-sprint prerequisite in Prerequisites section.
- **Detection:** For each Sprint-NN Sprint Plan where NN > 01, grep `Prerequisite:\s*Sprint\s+(\d+)\s+COMPLETE`. Absent → ERROR.
- **Finding template:**
```
[ERROR] Sequential-sprint prerequisite declaration missing
File: {Sprint Plan path} | Location: Prerequisites section
Issue: Sprint {NN} > 01 lacks "Prerequisite: Sprint {NN-1} COMPLETE"
Fix: Add prerequisite per references/scaffolding-hygiene.md §7 | Confidence: HIGH
```

### Check S04 — Master Plan Sole READY_TO_EXECUTE Status

- **Severity:** WARNING
- **Source:** Extension of existing PLG-001 rule 4
- **Type:** EXTEND
- **What:** At scaffolding time, ONLY Master Plan has `Status: READY_TO_EXECUTE`. All Sprint Plans have `Status: PLANNED`. (Current rule already partial in structural-reviewer; extends coverage.)
- **Detection:** Glob all Sprint Plans; grep `Status: READY_TO_EXECUTE`. Any Sprint Plan with this status at scaffolding time → WARNING.
- **Finding template:**
```
[WARNING] Sprint Plan has READY_TO_EXECUTE at scaffolding time
File: {Sprint Plan path}
Issue: Only Master Plan should have READY_TO_EXECUTE at scaffolding time
Fix: Set Sprint Plan Status: PLANNED per references/scaffolding-hygiene.md §5 | Confidence: HIGH
```
