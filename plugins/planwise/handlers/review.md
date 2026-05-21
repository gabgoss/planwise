# Handler: /planwise review

**Purpose:** Run structured multi-agent review of a plan before execution. Produces a dated review report with findings classified by severity and a NEEDS_FIXES / APPROVED verdict.

**Invocation examples:**
```
/planwise review MyPlan
/planwise review Plans/MyPlan
/planwise review MyPlan --sprint 02
```

---

## Table of Contents

- [Config Gate](#config-gate)
- [Phase 0: Plan Discovery](#phase-0-plan-discovery)
- [Scale Detection](#scale-detection)
- [No-Team Path (Trivial / Small)](#no-team-path-trivial--small)
- [Team Path (Medium / Large / Very Large)](#team-path-medium--large--very-large)
- [Reviewer Prompt Template](#reviewer-prompt-template)
- [Reviewer Checklists](#reviewer-checklists)
- [Known Patterns Whitelist](#known-patterns-whitelist)
- [Severity Classification](#severity-classification)
- [Verdict and Report](#verdict-and-report)
- [Systemic Finding Classification](#systemic-finding-classification)

---

## Config Gate

Locate `config.yaml` by checking:
1. `planwise/config.yaml` (default planwise root)
2. If not found, search one level down from the project root for `*/config.yaml`
3. If not found: "Project not initialized. Run `/planwise init` first."

Extract from `config.yaml`:
- `plugin_root` -- the plugin installation path
- `project.planwise_root` -- the planwise root folder (default: `planwise`)
- `project.plans_dir` -- the Plans directory name (relative to planwise_root)

All directory paths resolve as `{planwise_root}/{dir_name}` (e.g., `planwise/Plans`).

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`) are pre-injected by SKILL.md.

**Review-specific references (always load):**
1. Read `references/session-planning-protocol.md`
2. Read `references/session-plan-requirements.md`

**Conditional references:**
- If the plan creates or modifies agents: Read `references/agent-authoring.md`
- If the plan creates or modifies skills: Read `references/skill-authoring.md`
- If the plan creates or modifies rules: Read `references/rule-authoring.md`

---

## Phase 0: Plan Discovery

1. Parse `$ARGUMENTS` -- `$0` is the plan folder path or name; check for `--sprint NN`
2. Locate plan in `{plans_dir}` (resolve `$0` as subfolder name or direct path)
3. Read Master Plan -- extract abbreviation and plan type (Standard vs Meta-Plan)
4. Detect plan type:
   - Meta-Plan: has `Meta-{Abbrev}/` subfolder and `Exec-{Abbrev}/` subfolder. For Meta-Plan reviews, write the report to the top-level plan folder (`{PlanPath}/Reviews/`), not inside `Exec-{Abbrev}/`.
   - Standard: neither subfolder present
5. Count: sprints, EIs (Glob `*-Execution-Input*.md`), task files, orchestration files
6. Bind `{PlanPath}` = `{plans_dir}/{name}/`. Use this anchored path for all subsequent file writes (report output, git add).

---

## Scale Detection

> [!decide] Path Selection
> | EIs | Sprints | Scale | Path |
> |-----|---------|-------|------|
> | 0 | 1 | TRIVIAL | No-Team Path |
> | 1 | 1-2 | SMALL | No-Team Path |
> | 2-3 | any | MEDIUM | Team Path (standard) |
> | 4-5 | any | LARGE | Team Path (full) |
> | 6+ | any | VERY LARGE | Team Path (batched) |

---

## No-Team Path (Trivial / Small)

For plans with 0-1 EIs and 1-2 sprints, use sequential subagent spawns with no team overhead.

### Step 1: Structural Review

Spawn `structural-reviewer` agent via Task tool:

```
Task(
  subagent_type: "structural-reviewer",
  description: "Structural review for {Abbrev}",
  prompt: |
    You are reviewing plan {Abbrev} for structural integrity.

    Plan type: {Standard | Meta-Plan}
    Plan path: {PlanPath absolute path}

    Read the plan files and check every item in your structural review protocol.

    Global numbering note: Spec numbers are assigned globally across all sprints.
    Non-sequential numbers within a single EI are expected, not errors.

    Report findings using the finding format in your protocol.
    End with: "Phase 1 complete, {N} findings reported"
)
```

Read the subagent output. If BLOCKERs found, write report with blockers only and STOP.

### Step 2: Content Review

If no blockers, spawn `plan-reviewer` agent via Task tool:

```
Task(
  subagent_type: "plan-reviewer",
  description: "Content review for {Abbrev}",
  prompt: |
    You are reviewing plan {Abbrev} for content quality.
    Your assigned role: Combined (EI Reviewer + Task Reviewer)

    Plan type: {Standard | Meta-Plan}
    Plan path: {PlanPath absolute path}
    EI files: {list of EI file paths}
    Task files: {list of task file paths}
    Orchestration files: {list of orchestration file paths}

    Global numbering note: Spec numbers are assigned globally across all sprints.
    Non-sequential numbers within a single EI are expected, not errors.

    Check Known Patterns Whitelist before reporting:
    - Global numbering appearing non-sequential within a single EI is intentional
    - Cross-sprint spec references that appear orphaned to a single-sprint scope are valid

    Execute BOTH the EI Reviewer and Task Reviewer checklists from your protocol.

    Report findings using the finding format in your protocol.
    Prefix uncertain findings (MEDIUM/LOW confidence) with [UNCERTAIN].
    End with: "Phase 2 complete, {N} findings reported"
)
```

### Step 3: Synthesize

1. Collect findings from both subagent outputs
2. Deduplicate: same file + same issue = merge; keep higher severity
3. Cross-check `[UNCERTAIN]` findings against Known Patterns Whitelist
4. Assign finding IDs: BLOCKERs -> [B1], [B2]...; ERRORs -> [E1], [E2]...; WARNINGs -> [W1]...; INFO -> [I1]...
5. Classify systemic findings (see [Systemic Finding Classification](#systemic-finding-classification))
6. Compute verdict (see [Verdict and Report](#verdict-and-report))
7. Write report to `{PlanPath}/Reviews/{Abbrev}-Review-{YYYY-MM-DD}.md`

---

## Team Path (Medium / Large / Very Large)

For plans with 2+ EIs, use full team with phase gating.

### Phase 1: Setup and Structural Gate

1. `TeamCreate(team_name: "plan-review-{abbrev}", description: "Plan review for {abbrev}")`

2. Spawn `structural-reviewer` as teammate:

```
Task(
  team_name: "plan-review-{abbrev}",
  name: "structural-reviewer",
  subagent_type: "structural-reviewer",
  prompt: |
    You are reviewing plan {Abbrev} for structural integrity.

    Plan type: {Standard | Meta-Plan}
    Plan path: {PlanPath absolute path}
    All plan file paths: {list every file path in the plan}

    Read the plan files and check every item in your structural review protocol.

    Global numbering note: Spec numbers are assigned globally across all sprints.
    Non-sequential numbers within a single EI are expected, not errors.

    Report each finding as a separate DM to the team lead.
    Use the finding format in your protocol.
    End with DM: "Phase 1 complete, {N} findings reported"
)
```

3. WAIT for "Phase 1 complete" DM from structural-reviewer. If no DM after reviewer goes idle, send a status check message. If still no response, proceed with any findings received so far.

4. If BLOCKERs received:
   - Write report with blockers only
   - Send `shutdown_request` to structural-reviewer
   - Wait for `shutdown_response`
   - `TeamDelete`
   - STOP -- do not spawn Phase 2 reviewers

### Phase 2: Parallel Content Review

5. Determine reviewer composition by scale:

> [!decide] Team Composition
> | Scale | Plan Reviewers | Roles |
> |-------|---------------|-------|
> | MEDIUM (2-3 EIs) | 2 (+1 optional) | ei-reviewer, task-reviewer (+ scaffolding-hygiene-reviewer if Meta-Plan) |
> | LARGE (4-5 EIs) | 3 (+2 optional) | ei-reviewer, task-reviewer, dependency-reviewer (+ scaffolding-hygiene-reviewer, design-extension-reviewer) |
> | VERY LARGE (6+ EIs) | 4 (+2 optional) | ei-reviewer (batched), task-reviewer, dependency-reviewer, coverage-reviewer (+ both sub-role reviewers) |

6. Spawn ALL Phase 2 reviewers in parallel -- issue all Task calls together in a single batch (do not wait between spawns):

**Role assignments for each reviewer:**

**EI Reviewer(s):**
```
Task(
  team_name: "plan-review-{abbrev}",
  name: "ei-reviewer-{N}",
  subagent_type: "plan-reviewer",
  prompt: |
    You are reviewing plan {Abbrev} for EI content integrity.
    Your assigned role: EI Reviewer

    Plan type: {Standard | Meta-Plan}
    Plan path: {PlanPath absolute path}
    EI files to review: {assigned EI file paths}
    ALL spec/source files: {all spec output paths -- full visibility required}

    Global numbering note: Spec numbers are assigned globally across all sprints.
    Non-sequential numbers within a single EI are expected, not errors.

    Check Known Patterns Whitelist before reporting:
    - Global numbering appearing non-sequential within a single EI is intentional
    - Cross-sprint spec references that appear orphaned to a single-sprint scope are valid

    Execute the EI Reviewer checklist from your protocol.

    Report each finding as a separate DM to the team lead.
    Prefix uncertain findings (MEDIUM/LOW confidence) with [UNCERTAIN].
    End with DM: "Phase 2 complete, {N} findings reported"
)
```

For VERY LARGE plans, batch 2 EIs per ei-reviewer (max 3 ei-reviewers). If a reviewer would exceed ~80K context, split into separate reviewers.

**Task Reviewer:**
```
Task(
  team_name: "plan-review-{abbrev}",
  name: "task-reviewer",
  subagent_type: "plan-reviewer",
  prompt: |
    You are reviewing plan {Abbrev} for task quality.
    Your assigned role: Task Reviewer

    Plan type: {Standard | Meta-Plan}
    Plan path: {PlanPath absolute path}
    Task files: {list of task file paths}
    EI files (for reference): {list of EI file paths}
    Orchestration files: {list of orchestration file paths}

    Execute the Task Reviewer checklist from your protocol.

    Report each finding as a separate DM to the team lead.
    Prefix uncertain findings (MEDIUM/LOW confidence) with [UNCERTAIN].
    End with DM: "Phase 2 complete, {N} findings reported"
)
```

**Dependency Reviewer** (LARGE / VERY LARGE only):
```
Task(
  team_name: "plan-review-{abbrev}",
  name: "dependency-reviewer",
  subagent_type: "plan-reviewer",
  prompt: |
    You are reviewing plan {Abbrev} for dependency accuracy.
    Your assigned role: Dependency Reviewer

    Plan path: {PlanPath absolute path}
    Task files: {list of task file paths}
    Orchestration files: {list of orchestration file paths}

    Execute the Dependency Reviewer checklist from your protocol.

    Report each finding as a separate DM to the team lead.
    Prefix uncertain findings (MEDIUM/LOW confidence) with [UNCERTAIN].
    End with DM: "Phase 2 complete, {N} findings reported"
)
```

**Coverage Reviewer** (VERY LARGE only):
```
Task(
  team_name: "plan-review-{abbrev}",
  name: "coverage-reviewer",
  subagent_type: "plan-reviewer",
  prompt: |
    You are reviewing plan {Abbrev} for requirement coverage.
    Your assigned role: Coverage Reviewer

    Plan path: {PlanPath absolute path}
    Master Plan: {master plan file path}
    Task files: {list of task file paths}
    Sprint plans: {list of sprint plan file paths}

    Execute the Coverage Reviewer checklist from your protocol.

    Report each finding as a separate DM to the team lead.
    Prefix uncertain findings (MEDIUM/LOW confidence) with [UNCERTAIN].
    End with DM: "Phase 2 complete, {N} findings reported"
)
```

**Scaffolding Hygiene Reviewer** (MEDIUM/LARGE/VERY LARGE — Meta-Plan only):
```
Task(
  team_name: "plan-review-{abbrev}",
  name: "scaffolding-hygiene-reviewer",
  subagent_type: "plan-reviewer",
  prompt: |
    Your assigned role: Scaffolding Hygiene Reviewer
    Execute Checks 046-050 from your protocol.
    ...
)
```

**Design-Extension Reviewer** (LARGE/VERY LARGE — when audit/design-extension findings expected):
```
Task(
  team_name: "plan-review-{abbrev}",
  name: "design-extension-reviewer",
  subagent_type: "plan-reviewer",
  prompt: |
    Your assigned role: Design-Extension Reviewer
    Execute Checks 051-054 from your protocol.
    ...
)
```

7. Collect findings incrementally as DMs arrive from reviewers.
8. Track completion: each reviewer sends "Phase 2 complete, {M} findings" DM before going idle.

### Phase 3: Synthesis

9. **Deduplicate:** same file + same issue = merge; keep higher severity.
10. **Cross-check [UNCERTAIN] findings:**
    - Check against [Known Patterns Whitelist](#known-patterns-whitelist)
    - Cross-check against other reviewers' findings
    - Confirmed -> promote to stated severity; contradicted -> discard as false positive
11. **Assign finding IDs:** BLOCKERs -> [B1], [B2]...; ERRORs -> [E1], [E2]...; WARNINGs -> [W1]...; INFO -> [I1]...
12. **Classify systemic findings:** For each confirmed finding (BLOCKER, ERROR, WARNING), determine one-off vs systemic (see [Systemic Finding Classification](#systemic-finding-classification)).
13. **Compute verdict** (see [Verdict and Report](#verdict-and-report)).

### Phase 4: Report and Cleanup

14. Create `{PlanPath}/Reviews/` directory if it does not exist.
15. Write report to `{PlanPath}/Reviews/{Abbrev}-Review-{YYYY-MM-DD}.md` using [templates/review-report.md](../templates/review-report.md).
16. Send `shutdown_request` to each teammate; wait for `shutdown_response` approvals.
17. `TeamDelete`.
18. Output summary to user: verdict, finding counts by severity, systemic finding count, report path.

### Communication Protocol

> [!practice] Default to DM
> USE `message` (DM) for all routine communication between reviewers and the lead. Reserve `broadcast` for critical abort scenarios only. Broadcasting sends N separate messages for N teammates -- costs scale linearly.

| Scenario | Message Type |
|----------|-------------|
| Report individual finding | DM to lead |
| Flag uncertain finding | DM to lead with `[UNCERTAIN]` prefix |
| Phase completion signal | DM to lead |
| Critical abort (structural blockers) | Broadcast |
| Everything else | DM |

### Idle Teammate Behavior

> [!pitfall] Idle Teammates
> **Problem:** Teammates go idle after completing their one-shot review mission. This looks like they stopped working.
> **Solution:** Idle is NORMAL and EXPECTED. Reviewers complete their checklist, send "Phase complete" DM, then go idle. Send `shutdown_request` to wake and terminate idle reviewers when all phases complete. Do NOT wait for them to "come back" or treat idle as an error.

---

## Reviewer Prompt Template

Every reviewer spawn prompt MUST include these six elements:

1. **Plan context:** abbreviation, type (Standard / Meta-Plan), global numbering scheme note
2. **Scope:** explicit file paths to read (never assume inherited context)
3. **Checklist:** the phase-specific items (reviewers carry their own checklist via agent definition)
4. **Finding format:**
   ```
   [SEVERITY] Finding summary (one line)
   File: {relative path}
   Location: {section or line reference}
   Issue: {what is wrong}
   Fix: {concrete change -- file + what to modify}
   Confidence: HIGH | MEDIUM | LOW
   ```
5. **Uncertainty protocol:** flag `[UNCERTAIN]` for MEDIUM or LOW confidence; check Known Patterns Whitelist first before flagging
6. **Completion signal:** "Phase {N} complete, {M} findings reported"

> [!pitfall] Context Not Inherited
> **Problem:** Subagents and teammates start with fresh context -- they do NOT inherit the lead's file reads, research, or analysis.
> **Solution:** Include all critical context in the reviewer's spawn prompt: plan abbreviation, structure type (Meta/Standard), numbering scheme, explicit file paths, and any relevant findings from earlier phases. Never assume shared state.

---

## Reviewer Checklists

The custom agents (`structural-reviewer` and `plan-reviewer`) carry their own checklists. The following is a summary for the lead's reference during synthesis.

### Structural Reviewer (Phase 1)

- Filenames match `{Abbrev}-S{XX}-{YY}` numbering pattern
- Task files listed in Orchestration's Task Files table resolve to real files
- `Outputs/` directory exists per session
- Status fields present in Recovery and Orchestration files
- Cross-reference links resolve (no dead paths)
- [Meta-Plan] `Meta-{Abbrev}/`, `Scaffold-{Abbrev}/`, `Exec-{Abbrev}/` folders all present

### EI Reviewer (Phase 2)

- Every spec section appears in at least one EI's Cross-References table
- Cross-References table cites real, resolvable files
- Content is extracted verbatim -- not summarized or paraphrased
- Header "Extracted from:" lists all cited source files accurately
- Non-sequential spec numbering within an EI is EXPECTED (global scheme) -- do NOT flag as an error

### Task Reviewer (Phase 2)

- Required Context section references are individual with purpose -- NOT ranges (e.g., "Section 2 (entity fields), Section 4 (validation rules)" is correct; "Sections 2-5" is a BLOCKER)
- Execution steps are concrete actions (not vague directives)
- Success criteria are measurable checkboxes
- Declared dependencies match actual data flow between tasks
- Agent assignment is appropriate: Haiku for lookups, Sonnet for code, Opus for decisions

### Dependency Reviewer (Phase 2, LARGE/VERY LARGE)

- Task dependency DAG has no cycles
- Implicit dependencies not declared (e.g., Task 3 reads files created by Task 2 but does not declare it)
- Sprint ordering respects cross-sprint dependencies
- Parallel tasks are truly independent

### Coverage Reviewer (Phase 2, VERY LARGE)

- All requirements from Master Plan vision are covered by tasks
- No gaps -- requirements mentioned in Master Plan but not addressed by any task
- No redundant tasks that duplicate effort
- Session objectives align with sprint goals

---

## Known Patterns Whitelist

These patterns look like errors but are intentional. Discard findings that match these patterns.

| Pattern | Why It Is Intentional |
|---------|----------------------|
| Global numbering appearing non-sequential within a single EI | Spec numbers are assigned globally across all sprints. A sprint's EI may reference Spec #1, #3, #7 -- the gaps are other sprints' specs. |
| Cross-sprint spec reference that appears orphaned to a single-sprint reviewer | An EI reviewer given only one sprint's scope may flag a valid cross-sprint reference as unresolved. EI reviewers must receive ALL spec outputs to avoid this. |

> [!practice] Check Whitelist Before Reporting
> Reviewers should verify each finding against the Known Patterns Whitelist before sending it to the team lead. If the pattern matches, discard it. If uncertain, send with `[UNCERTAIN]` prefix rather than discarding outright.

---

## Severity Classification

### Definitions

| Severity | Definition | Examples | Required Action |
|----------|------------|----------|-----------------|
| BLOCKER | Agent cannot execute the task at all | Missing EI section, broken file reference, required dependency not declared | Must fix before execution begins |
| ERROR | Agent will produce incorrect output | Wrong API call, stale field names, contradictory instructions, missing cross-sprint source in EI header | Should fix before execution |
| WARNING | Agent can work around it but quality will suffer | Vague steps, low token estimate, missing optional context file | Fix if time permits |
| INFO | Observation only; no action required | Style inconsistency, redundant context file, minor formatting issue | Log for feedback loop |

### Decision Tree

> [!decide] How to Classify a Finding
> ```
> Finding discovered ->
>   Can the agent execute the task at all?
>     NO  -> BLOCKER
>     YES -> Will the agent produce incorrect output?
>             YES -> ERROR
>             NO  -> Will quality be meaningfully degraded?
>                     YES -> WARNING
>                     NO  -> INFO
> ```

### Confidence-to-Severity Mapping

| Reviewer Confidence | Processing Rule |
|--------------------|-----------------|
| HIGH | Accept finding at its stated severity. Add directly to findings list. |
| MEDIUM | Cross-check against accumulated context from other reviewers. If corroborated or plausible, accept. If contradicted, investigate before including. |
| LOW / `[UNCERTAIN]` | Check against Known Patterns Whitelist first. Cross-check against other findings. Include only if confirmed. Discard if unconfirmed. |

---

## Verdict and Report

| Condition | Verdict |
|-----------|---------|
| BLOCKER count > 0 | NEEDS_FIXES |
| ERROR count > 0 AND any ERROR lacks accept-risk justification | NEEDS_FIXES |
| All other cases | APPROVED |

### Report Persistence

- **Location:** `{PlanPath}/Reviews/` directory (create if not exists)
- **Naming:** `{Abbrev}-Review-{YYYY-MM-DD}.md`
- **Template:** [templates/review-report.md](../templates/review-report.md)
- **Multiple reviews:** Each review produces a new dated file; history is preserved

### Post-Report Actions

1. Update the plan's Master Plan with status `REVIEWED` (or `APPROVED` / `NEEDS_FIXES`)
2. Commit the report file: `git add {PlanPath}/Reviews/{Abbrev}-Review-{YYYY-MM-DD}.md && git commit -m "docs: Add plan review {Abbrev} {YYYY-MM-DD}"`
3. Output summary to user: verdict, finding counts by severity, systemic finding count, report path
4. If **APPROVED**: "Plan validated. Execute with `/planwise run @{orch-path}`"
5. If **NEEDS_FIXES**: "Review found issues. Fix findings in the report, then re-run `/planwise review` or proceed to `/planwise run`"

---

## Systemic Finding Classification

During synthesis, the lead classifies each confirmed finding (BLOCKER, ERROR, WARNING) as one-off or systemic.

### Root Cause Categories

| Category | Definition | Typical Fix Location |
|----------|-----------|---------------------|
| **Template gap** | The task file or plan template is missing a rule, example, or structural element that would have prevented the error | Planning templates |
| **Rule gap** | A project-wide rule is incomplete, ambiguous, or missing the specific case that caused the error | `.claude/rules/` |
| **Skill gap** | The review handler or agent definition lacks instructions, context, or false-positive guards that caused an incorrect finding | Plugin handlers or agents |
| **EI extraction gap** | The Execution Input extraction process failed to carry forward sufficient detail or structure from the source material | Scaffolding phase guidance |
| **Protocol gap** | The session or sprint protocol is missing a step or decision rule that caused a process failure | Workflow rules |
| **One-off** | The error was situational and does not reflect a systemic gap; no template or rule change is warranted | N/A -- document rationale |

### Classification Criteria

> [!decide] One-off vs Systemic
> - Would this same error occur in a DIFFERENT plan that follows the same templates? -> **Systemic**
> - Was this error caused by specific characteristics of THIS plan only? -> **One-off**
> - Does a template, rule, or skill fail to prevent this class of error? -> **Systemic** (identify which artifact)
> - Is the error already covered by existing guidance that was missed during execution? -> **One-off** (execution failure, not artifact gap)

### Output Format

Systemic findings appear in the review report's Systemic Findings section:

```
**[S1]** -- {one-line description of the recurring pattern}

| Field                | Value |
|----------------------|-------|
| Root Cause Category  | {template gap | rule gap | skill gap | EI extraction gap | protocol gap | one-off} |
| Description          | {what pattern recurs across findings -- be specific} |
| Suggested Fix Target | {file path + what to change in the planning artifact} |
| Status               | OPEN |
```

---

## Error Pattern Catalog

Quick reference for common patterns and their correct classification.

| # | Pattern | Severity | Where to Check |
|---|---------|----------|----------------|
| 1 | Vague section references ("Sections 2-5" instead of individual listings) | BLOCKER | Task file Required Context table |
| 2 | Cross-sprint citation without source listing in EI header | ERROR | EI header + Cross-References table |
| 3 | Rigid mapping where domain+description inference needed | ERROR | Task execution steps |
| 4 | Stale API reference (function renamed or moved) | ERROR | Task steps vs actual codebase |
| 5 | Sequential numbering assumption (global numbering is non-sequential) | FALSE POSITIVE | See Known Patterns Whitelist |
| 6 | Missing dependency in chain | WARNING | Task dependency field |
| 7 | Token estimate too low for declared context | WARNING | Task token estimate vs file count |
| 8 | Orphaned spec section (appears in no EI) | WARNING | EI completeness check |
| 9 | Reviewer prompt missing plan context | ERROR | Reviewer spawn prompt |
| 10 | Idle teammate treated as error | INFO | Normal behavior -- not a failure |
