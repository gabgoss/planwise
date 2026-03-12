# Plan Review Report: {plan_name}

**Abbreviation:** {plan_abbrev}
**Review Date:** {review_date}
**Reviewer:** Claude Code /plan-review
**Scope:** {scope}
<!-- scope: list sprints, EIs, and task files reviewed — e.g., "S01–S03 Sprint Plans, 3 Execution Inputs, 12 Task Files" -->
**Plan Type:** {plan_type}
<!-- plan_type: Standard | Meta-Plan -->
**Review Mode:** {review_mode}
<!-- review_mode: team-based | no-team -->

---

## Summary Table

| Severity | Count |
|----------|-------|
| BLOCKER  | {count_blocker} |
| ERROR    | {count_error} |
| WARNING  | {count_warning} |
| INFO     | {count_info} |
| **Total Findings** | **{count_total}** |
| False Positives Filtered | {count_false_positives} |

---

## Verdict

**{verdict}**
<!-- verdict: APPROVED | NEEDS_FIXES -->

{verdict_conditions}
<!-- verdict_conditions: brief explanation of why this verdict was reached.
     Example for APPROVED: "No BLOCKERs or ERRORs found. WARNINGs are advisory."
     Example for NEEDS_FIXES: "2 BLOCKERs must be resolved before execution. See [B1], [B2]." -->

---

## Findings by Severity

### BLOCKERs

<!-- BLOCKERs prevent execution. Must be fixed before the plan is run.
     If none, write: "None." -->

{blockers_section}

---

### ERRORs

<!-- ERRORs are protocol violations that will cause execution failures or context loss.
     If none, write: "None." -->

{errors_section}

---

### WARNINGs

<!-- WARNINGs are deviations from best practice that may cause issues.
     If none, write: "None." -->

{warnings_section}

---

### INFOs

<!-- INFOs are observations, suggestions, or minor notes. Non-blocking.
     If none, write: "None." -->

{infos_section}

---

<!-- FINDING FORMAT (copy per finding, replace placeholders):

**[X1]** — {one-line summary of the issue}

| Field    | Value |
|----------|-------|
| File     | {relative/path/to/file.md} |
| Location | {section name or line reference} |
| Issue    | {what is wrong — specific and actionable} |
| Fix      | {concrete change: file path + what to modify} |
| Reviewer | {reviewer name or role} |

-->

---

## Systemic Findings

<!-- Systemic findings are patterns observed across multiple individual findings.
     They inform the planning feedback loop (template/rule/skill gaps).
     If none, write: "None." -->

{systemic_findings_section}

<!-- SYSTEMIC FINDING FORMAT (copy per finding, replace placeholders):

**[S1]** — {one-line description of the recurring pattern}

| Field                | Value |
|----------------------|-------|
| Root Cause Category  | {template gap | rule gap | skill gap | EI extraction gap | protocol gap | one-off} |
| Description          | {what pattern recurs across findings — be specific} |
| Suggested Fix Target | {file path + what to change in the planning artifact} |
| Status               | OPEN |

-->

---

## False Positive Assessment

| Metric | Value |
|--------|-------|
| Total Uncertain Findings Received | {total_uncertain} |
| Promoted to Confirmed Findings | {promoted} |
| Discarded as False Positives | {discarded} |
| False Positive Rate | {false_positive_rate}% |

<!-- false_positive_rate = discarded / total_uncertain * 100, rounded to 1 decimal place.
     If total_uncertain = 0, write "N/A". -->

---

## Team Composition

<!-- Fill this section only for team-based reviews. Delete or mark "N/A" for no-team reviews. -->

| Reviewer | Role | Phase | Files Checked | Finding Count |
|----------|------|-------|---------------|---------------|
| {reviewer_name} | {role} | {phase} | {files_checked} | {finding_count} |

<!-- Add one row per reviewer. Roles: structural-reviewer, ei-reviewer, task-reviewer, etc.
     Phases: structure, ei, task-files, synthesis. -->

---

## Phase Coverage

| Phase | Reviewer | Files Checked | Finding Count | Duration |
|-------|----------|---------------|---------------|----------|
| {phase_number} | {reviewer} | {files_checked} | {finding_count} | {duration} |

<!-- Add one row per phase executed. Duration: approximate wall-clock time or "N/A".
     Phase numbers should match the review workflow phases (1 = structure, 2 = EI, 3 = task files, 4 = synthesis). -->
