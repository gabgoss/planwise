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
- [Token Saver Compliance Check](#token-saver-compliance-check)

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml:
   a. Check `planwise/config.yaml` (default planwise root)
   b. If not found, search one level down from project root for `*/config.yaml`

2. If found → continue to Required References (extract `plugin_root`, `project.planwise_root`, `project.plans_dir`).

3. If NOT found:
   a. Announce: "Planwise not initialized in this project. Running /planwise init first…"
   b. Resolve `{plugin_root}` from the handler's own known location.
   c. Invoke init subroutine with `--auto-from "review"` (interactive or auto per Auto Mode).
   d. After init completes, RE-RESOLVE config.yaml (loop to step 1).
   e. If still NOT found: FAIL LOUD and STOP.

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed (YAMLError), DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise review." STOP.

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
- If reviewing a scaffolded multi-sprint plan: Read `references/ei-fidelity.md`, `references/task-content-fidelity.md`, `references/discovery-and-exit-criteria.md`, `references/scaffolding-hygiene.md`
- If reviewing a plan with DB-write tasks: Read `references/schema-pin-requirement.md`
- If reviewing IPC/protocol/codec sessions: Read `references/verification-gates.md`
- If reviewing tasks with cross-sprint/cross-version symbol citations: Read `references/verify-against-shipped-artifact.md`
- If `context.token_saver: true` in `config.yaml`: Read `references/task-content-fidelity.md` §9.A.8 (the Token Saver Large-File Ladder — source of truth for the [Token Saver Compliance Check](#token-saver-compliance-check))

---

## Phase 0: Plan Discovery

1. Parse `$ARGUMENTS` -- `$1` is the plan folder path or name; check for `--sprint NN`
2. Locate plan in `{plans_dir}` (resolve `$1` as subfolder name or direct path)
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
> | 0 | 2+ | MEDIUM | Team Path (standard) |
> | 1 | 1-2 | SMALL | No-Team Path |
> | 2-3 | any | MEDIUM | Team Path (standard) |
> | 4-5 | any | LARGE | Team Path (full) |
> | 6+ | any | VERY LARGE | Team Path (batched) |

**Sprint-count crossover:** 2+ sprints alone triggers Team Path even with 0 EIs — per `agent-orchestration.md` §8, "Teams become worthwhile at 2+ EIs **or** 2+ sprints." Only a 0-EI single-sprint plan is TRIVIAL (No-Team Path).

---

## No-Team Path (Trivial / Small)

For plans with 0-1 EIs and 1-2 sprints, use sequential subagent spawns with no team overhead.

### Step 1: Structural Review

Spawn `structural-reviewer` agent via Task tool:

```
Task(
  subagent_type: "planwise:structural-reviewer",
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
  subagent_type: "planwise:plan-reviewer",
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
    If the plan is a Meta-Plan, ALSO execute the Scaffolding Hygiene Reviewer
    checklist (Checks 046-050) in addition to the EI Reviewer + Task Reviewer checks.

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
  subagent_type: "planwise:structural-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

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
  subagent_type: "planwise:plan-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

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
  subagent_type: "planwise:plan-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

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
  subagent_type: "planwise:plan-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

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
  subagent_type: "planwise:plan-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

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
  subagent_type: "planwise:plan-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

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
  subagent_type: "planwise:plan-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

    Your assigned role: Design-Extension Reviewer
    Execute Checks 051-054 and 062 from your protocol.
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

Every reviewer spawn prompt MUST include these seven elements:

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
7. **Tool pre-load (BINDING for team-mode spawns):** the first instruction line in the spawn prompt MUST be `First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.` `SendMessage` is a deferred tool; without the schema loaded, the reviewer's findings cannot be delivered. The reviewer's agent definition already carries this rule in its own `## Startup` section — the spawn-prompt instruction is the belt-and-braces gate.

> [!constraint] Spawn prompts MUST front-load the SendMessage schema load
> WRONG — spawn prompt opens with `You are reviewing plan {Abbrev} ...` and the reviewer attempts `SendMessage(finding)` after its first read. The deferred-tool schema was never fetched; the call raises `InputValidationError` and the entire review (40-70K tokens of work for an EI reviewer) is silently lost — the lead never receives a "Phase complete" DM.
>
> CORRECT — spawn prompt opens with `First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.` followed by the role/scope/checklist content. Schema lands before any reporting attempt; the reviewer's DMs are delivered.

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
- [Token Saver on] Each task's Required Context obeys the §9.A.8 large-file ladder: no over-ceiling task without `1M-exception`; Warn+ files carry a backlog item; a `read`-reason Critical is never `1M-exception`'d; oversized generated artifacts are Multi-Part split (see [Token Saver Compliance Check](#token-saver-compliance-check))

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

## Token Saver Compliance Check

**Gated on `context.token_saver: true`.** When `config.yaml` has Token Saver **off**, this entire check is a **no-op** — skip it; zero behavior change versus a pre-Token-Saver review. When **on**, the lead (No-Team Path) or the Task Reviewer (Team Path) runs the check below over every task in scope and reports findings using the standard finding format. It validates that the planner actually applied the per-task large-file ladder anchored in `references/task-content-fidelity.md` §9.A.8 — read that subsection for the level definitions, the `reason=cost|read` contract, and the FIXED Read-tool gates the ladder folds in.

### Derive the ceilings from config (never hardcode)

Read the thresholds from `config.yaml`, exactly as the `/planwise plan` Step 8c scan does — the review re-derives them so it measures against the same numbers the planner used:

```
available_per_task = context.token_saver_session_target − context.token_saver_runner_overhead − 6000
critical           = available_per_task − 10000
warn               = min(40000, round(0.5 × available_per_task))
over_ceiling(task) = task_estimate + context.token_saver_runner_overhead > context.token_saver_session_target
```

**Read gates (FIXED constants, evaluated per the file's assigned-model tokenizer):** byte ≥ `262144` (256 KiB), warn ≥ `245760` (240 KiB), measured with `wc -c`; OR `lines × {haiku 13, sonnet 13, opus 19}` ≥ `25000` (page cap), warn ≥ `22000`. A file's level is `max(cost_level, read_level)`; `reason` records which gate drove it.

### Findings

Run each check below over every task in scope. Each is HIGH confidence (mechanical):

1. **Over-ceiling without exception** — recompute the task's bottom-up estimate. If `over_ceiling(task)` is true AND the task is **not** flagged `1M-exception` → **finding** (severity ERROR — the runner overflows its budget mid-task).
2. **Warn+ Required Context file with no backlog item** — if a Required Context file classifies **Warn or Critical** (cost or read) but the task records no large-file recommendation / backlog item → **finding** (WARNING).
3. **`1M-exception` task on a 200K-window agent** — if a `1M-exception` task is declared `Agent: Sonnet` or `Agent: Haiku` without the run-time override note (the flag dispatches on Opus / 1M; a 200K-window agent would still overflow) → **finding** (ERROR).
4. **Uncovered read-gate crossing** — if a Required Context file crosses a FIXED read gate (`wc -c` bytes ≥ 256 KiB, OR `lines × {assigned-model tok/line}` ≥ 25K) and the task records **neither** a paged-read note (`offset`/`limit`/Grep) **nor** a refactor+backlog item → **finding** (WARNING; the runner gets a truncated or refused Read mid-task).
5. **Read-reason Critical mis-flagged `1M-exception`** — if a file that classifies **Critical with `reason=read`** is flagged `1M-exception` → **finding** (ERROR). The 1M window does not raise the per-Read page cap or the byte refusal, and Opus (19 tok/line) trips the token gate *sooner* than Sonnet/Haiku — a read-Critical is paged or refactored, never `1M-exception`'d. Only a `reason=cost` Critical earns the flag.
6. **Oversized generated artifact not split** — if a plan-generated artifact a runner MUST read (task file, Orchestration, Recovery, Consolidated Context part, Execution Input, task Output file) exceeds the **HARD** read ceiling (`wc -c` ≥ 256 KiB, OR `lines × {reading-model tok/line}` ≥ 25K) without a Multi-Part split → **finding** (ERROR). For generated artifacts the read-gate ceiling is hard, not advisory (external source files the runner reads but does not generate stay advisory under findings 2 and 4).

> [!constraint] Read-Reason Critical Is NOT `1M-Exception`-Resolvable (review mirror)
> WRONG — flag a finding only when an over-ceiling task lacks `1M-exception`, and treat every Critical the same:
> ```
> if over_ceiling(task) and not task.flagged("1M-exception"): finding   # misses read-Critical mis-flagging
> ```
> CORRECT — split on `reason`: a `cost`-Critical MUST be `1M-exception`'d; a `read`-Critical MUST NOT be (it is paged/refactored), and flagging it `1M-exception` is itself a finding:
> ```
> if verdict.level == Critical and verdict.reason == "cost" and not task.flagged("1M-exception"): finding
> if verdict.level == Critical and verdict.reason == "read" and task.flagged("1M-exception"):     finding
> ```

When Token Saver is off, none of the above runs — the §9.A token-estimation checks (Error Pattern Catalog #14, #37, #38) stand alone, unchanged.

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
| 11 | DELEGATED dispatch mandatory trigger violated (`agent-orchestration.md` §11.1) | BLOCKER | Orchestration Execution Strategy |
| 12 | Task-file error recovery semantics missing (`agent-orchestration.md` §11.2) | BLOCKER | Task file Notes for Agent |
| 13 | Schema Pin pre-execution form missing (`schema-pin-requirement.md` §4) | BLOCKER | Task file Required Context |
| 14 | Token estimate uses `~?` placeholder (`task-content-fidelity.md` §9.A.2) | BLOCKER | Task file Estimated Tokens |
| 15 | Cross-sprint Required Context not mirrored in Depends On (`session-plan-requirements.md` §9 cross-sprint) | BLOCKER | Task file Depends On |
| 16 | EI bidirectional consistency violation (every Spec in `Extracted from:` MUST appear in ≥ 1 Cross-References row and vice versa) | WARNING (HIGH confidence) | EI header + Cross-References |
| 17 | DELEGATED inter-dispatch lint/precheck diagnostics missing on shared file (PLG-020 sub-check / `agent-orchestration-delegated.md` §1.4) | BLOCKER | Orchestration between dispatches |
| 18 | DELEGATED output `wc -l` verification missing after dispatch (PLG-020 sub-check / `agent-orchestration-delegated.md` §1.4 PLG-020 extension) | BLOCKER | Orchestration between dispatches |
| 19 | DELEGATED spawn prompt missing HARD CONSTRAINTS skeleton + SCOPE BOUNDARY clause (PLG-020 sub-check / `agent-orchestration-delegated.md` §1.8) | BLOCKER | Orchestration spawn prompts |
| 20 | DELEGATED follow-up fixes not tier-ranked by invasiveness (PLG-020 sub-check / `agent-orchestration-delegated.md` §1.9) | BLOCKER | Orchestration follow-up dispatches |
| 21 | DELEGATED forward-looking-verb detection + SendMessage resume protocol missing (PLG-020 sub-check / `agent-orchestration-delegated.md` §1.10) | BLOCKER | Orchestration post-dispatch scan |
| 22 | DELEGATED spawn prompt missing operational-ceiling disclaimer (PLG-020 sub-check / `agent-orchestration-delegated.md` §1.11) | BLOCKER | Orchestration spawn prompts |
| 23 | DELEGATED edit-heavy task missing N>25 resume protocol + tool-use budget estimation (PLG-020 sub-check / `agent-orchestration-delegated.md` §1.12) | BLOCKER | Orchestration spawn prompts |
| 24 | DELEGATED shared-edit-target dispatches missing parallelism cap/shard/delta strategy (PLG-020 sub-check / `agent-orchestration-delegated.md` §1.13) | BLOCKER | Orchestration dispatch matrix |
| 25 | Verify-before-cite round-2 (`task-content-fidelity.md` §9.B.6..§9.B.9) | BLOCKER (varies by sub-rule) | Task file SQL/MERGE briefs |
| 26 | Sprint exit-gate verdict not reflecting gate-defining step (`verification-gates.md` §3) | BLOCKER | Sprint Plan + Sprint Overview row |
| 27 | Sprint Overview row encoding session-count fraction instead of gate verdict (`verification-gates.md` §4) | ERROR | Master Plan Sprint Overview |
| 28 | EI Cross-References §-citation format violated (`ei-fidelity.md` §7) | BLOCKER | EI Cross-References table |
| 29 | UNCONFIRMED claim missing four-site enforcement (`ei-fidelity.md` §4) | BLOCKER | EI body |
| 30 | Sprint Plan has `READY_TO_EXECUTE` at scaffolding time (PLG-001 / `scaffolding-hygiene.md` §4) | WARNING | Sprint Plan Status field |
| 31 | Per-session `Outputs/` directory missing (PLG-001 / `scaffolding-hygiene.md` §5) | BLOCKER | Session folder |
| 32 | Orchestration `**Prerequisite:**` declaration missing for sequential session (PLG-001 / `scaffolding-hygiene.md` §6) | ERROR | Orchestration Prerequisites |
| 33 | Orchestration Context Boundary callout missing (PLG-002 / `agent-orchestration.md` §11.3) | BLOCKER | Orchestration Execution Strategy |
| 34 | Verification Commands section missing for runnable-artifact task (PLG-003 / `verification-gates.md` §3) — exempt if `<!-- VERIFICATION: not-applicable (reason) -->` comment present in task's Notes for Agent | BLOCKER | Task file Verification Commands |
| 35 | Per-file-type Verification Commands table empty (PLG-003 / `verification-gates.md` §3) — applies to runnable-artifact tasks per `templates/task-file.md` §Per-File-Type Commands | BLOCKER | Task file Verification Commands |
| 36 | Verify Before/After callout missing for runnable artifact (PLG-003 / `verification-gates.md` §4) | BLOCKER | Task file Verification Commands |
| 37 | Required Context not updated when a prior task changed file structure (PLG-004 / `task-content-fidelity.md` §9.A.1) | ERROR | Task Required Context |
| 38 | Per-file-type token rate band violation (PLG-004 / `task-content-fidelity.md` §9.A.3) | WARNING | Task Required Context |
| 39 | User-prompt-cited artifact unverified at scaffolding (PLG-004 / `task-content-fidelity.md` §9.B.1) | BLOCKER | Task file cited paths |
| 40 | Identifier not reconciled with live contract (PLG-004 / `task-content-fidelity.md` §9.B.2) | BLOCKER | Task Execution Steps |
| 41 | Helper-function design not categorized in column-presence check (PLG-004 / `task-content-fidelity.md` §9.B.4) | WARNING | Task helper refs |
| 42 | EI archival fidelity violated — transform happens at EI not Task layer (PLG-005 / `ei-fidelity.md` §1) | ERROR | EI body |
| 43 | EI source severity vocabulary not preserved (PLG-005 / `ei-fidelity.md` §2) | ERROR | EI body |
| 44 | EI threshold misaligned with operational dispatch contract (PLG-005 / `ei-fidelity.md` §3) | BLOCKER | EI vs Sprint Plan |
| 45 | EI cross-tier duplicate not preserved (PLG-005 / `ei-fidelity.md` §5) | ERROR | EI Cross-References |
| 46 | EI cross-tier citation not propagated to implementation surface (PLG-005 / `ei-fidelity.md` §6) | ERROR | EI Cross-References |
| 47 | EI token reconciliation gate failed (PLG-005 / `ei-fidelity.md` §8) | BLOCKER | EI token totals |
| 48 | Discovery count missing execution citation (PLG-006 / `discovery-and-exit-criteria.md` §15.1) | BLOCKER | Discovery outputs |
| 49 | Binding refinement not echoed across plan layers (PLG-006 / `discovery-and-exit-criteria.md` §16.1) | BLOCKER | Multi-layer files |
| 50 | "Surfaces" used as non-enforceable mention not enforcement claim (PLG-006 / `discovery-and-exit-criteria.md` §16.2) | ERROR | EI / Sprint Plan |
| 51 | Sprint signoff row-count mismatch with EI exit criteria (PLG-006 / `discovery-and-exit-criteria.md` §16.3) | BLOCKER | Sprint signoff |
| 52 | Cross-session dependency not mirrored in task `Depends On` (PLG-007 D2 / `session-plan-requirements.md` §9 cross-session) | BLOCKER | Task Depends On |
| 53 | Post-scaffold back-propagation missed after task edit (PLG-007 D3 / `session-plan-requirements.md` §9 post-scaffold sync) | ERROR | Task file + EI section |
| 54 | BLI-cited audit anchor not re-verified before execution (PLG-019 / `verify-against-shipped-artifact.md` §6) | BLOCKER | Orchestration BLI refs |
| 55 | Cohort token-uplift missing for known high-divergence cohort (PLG-022 / `scaffolding-hygiene.md` §10) | WARNING | Master Plan Sprint Overview Notes |
| 56 | Cross-tier audit-finding triage table missing (PLG-022 / `discovery-and-exit-criteria.md` §18) | WARNING | Discovery/audit sessions |
| 57 | EI multi-sprint cumulative state not reconciled (`ei-fidelity.md` §9.1) | BLOCKER | Later-sprint EI Current state block + Sprint Plan Cross-Sprint File Touches + task-file Step-1 prerequisite grep gate |
| 58 | EI repoint map cluster incomplete — fewer enumerated rows than audit cluster cites (`ei-fidelity.md` §9.2) | BLOCKER | EI repoint map vs audit cluster |
| 59 | EI audit-grep-table coverage gap — verification scope wider than upstream repair scope (`ei-fidelity.md` §9.3) | BLOCKER | EI verification task vs repair task Required Context |
| 60 | Consolidated Context body⇄citation promise broken — header names a finding as a Driving Finding (or Cross-References row lists it) but body lacks the prose AND no `[source-doc-only]` marker (`ei-fidelity.md` §10.1) | ERROR | Consolidated Context part body |
| 61 | Task verbatim-extraction targets a section that does not physically carry the cited prose — pre-extraction verification missing AND no fallback-hierarchy step (`ei-fidelity.md` §10.2 + §10.3) | ERROR | Task file Execution Steps |
| 62 | Mega-scaffold skipped review gate — `n_sprints_scaffolded_this_pass ≥ 2` AND Master Plan Status is `READY_TO_EXECUTE` AND no `/planwise review` report referenced (`scaffolding-hygiene.md` §11) | BLOCKER | Master Plan / scaffold-session transcript |
| 63 | Token Saver large-file ladder not applied — `context.token_saver: true` AND (over-ceiling task without `1M-exception`; OR Warn+ Required Context file with no backlog item; OR a `read`-reason Critical wrongly flagged `1M-exception`; OR a `1M-exception` task on a Sonnet/Haiku agent without override note; OR a runner-read generated artifact past the line/byte/token read gate without a Multi-Part split) (`task-content-fidelity.md` §9.A.8) — no-op when Token Saver is off | ERROR (read-Critical mis-flag / over-ceiling / artifact split) · WARNING (missing backlog item / uncovered read gate) | Task Required Context + Notes for Agent ([Token Saver Compliance Check](#token-saver-compliance-check)) |
