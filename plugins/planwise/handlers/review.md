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

- [Config Gate](#config-gate-auto-init-fallback)
- [Phase 0: Plan Discovery](#phase-0-plan-discovery)
- [Scale Detection](#scale-detection)
- [No-Team Path (Trivial / Small)](#no-team-path-trivial--small)
- [Team Path (Medium / Large / Very Large)](#team-path-medium--large--very-large)
- [Reviewer Prompt Template](#reviewer-prompt-template)
- [Verdict and Report](#verdict-and-report)

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

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

**Review-specific references (always load):**
1. Read `references/session-planning-protocol.md`
2. Read `references/session-plan-requirements.md`
3. Read `references/review-classification.md` -- Reviewer Checklists, Known Patterns Whitelist, Severity Classification, Systemic Finding Classification, Token Saver Compliance Check (needed by the lead during synthesis)

**Conditional references:**
- If the plan creates or modifies agents: Read `references/agent-authoring.md`
- If the plan creates or modifies skills: Read `references/skill-authoring.md`
- If the plan creates or modifies rules: Read `references/rule-authoring.md`
- If reviewing a scaffolded multi-sprint plan: Read `references/ei-fidelity.md`, `references/task-content-fidelity.md`, `references/discovery-and-exit-criteria.md`, `references/scaffolding-hygiene.md`
- If reviewing a plan with DB-write tasks: Read `references/schema-pin-requirement.md`
- If reviewing IPC/protocol/codec sessions: Read `references/verification-gates.md`
- If reviewing tasks with cross-sprint/cross-version symbol citations: Read `references/verify-against-shipped-artifact.md`
- If reviewing a plan with verification tasks (match-pattern + pass/fail gate): Read `references/verification-task-authoring.md`
- If reviewing a DELEGATED-orchestration plan: Read `references/agent-orchestration-delegated.md`
- If the **effective** Token Saver value is `true` for the plan under review (its Master-Plan `Token Saver:` field over the project `context.token_saver` default — `get_effective_token_saver_config(config, plan_override)`): Read `references/task-content-fidelity.md` §9.A.8 (the Token Saver Large-File Ladder — source of truth for the [Token Saver Compliance Check](../references/review-classification.md#token-saver-compliance-check))
- When citing Error Pattern Catalog rows during synthesis or in a finding's Fix field: Read `references/error-pattern-catalog.md` (on demand -- not loaded up front)
- For Auto Mode behavior (how a step behaves when `AskUserQuestion` cannot be answered non-interactively): Read `references/auto-mode-policy.md`

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
3. Recompute delegated verdicts: for each subagent that returned a verdict label (GREEN/YELLOW/RED, NEEDS_FIXES/APPROVED, READY/READY-WITH-NOTES, or equivalent), recompute the classification from the reported finding counts using the task's stated classification rule. If the recomputed verdict differs from the reported label, use the recomputed verdict and log a meta-finding -- do NOT accept a verdict label without verifying it against the agent's own evidence. For cross-file control-flow claims ("symbol X never used in this file -> feature Y is broken"), trace the full consumer call path before accepting OR rejecting the finding -- single-file grep proves local non-use, not global inertness (`agent-orchestration-delegated.md` §1.16)
4. Cross-check `[UNCERTAIN]` findings against Known Patterns Whitelist
5. Assign finding IDs: BLOCKERs -> [B1], [B2]...; ERRORs -> [E1], [E2]...; WARNINGs -> [W1]...; INFO -> [I1]...
6. Classify systemic findings (see [Systemic Finding Classification](../references/review-classification.md#systemic-finding-classification))
7. Compute verdict (see [Verdict and Report](#verdict-and-report))
8. Write report to `{PlanPath}/Reviews/{Abbrev}-Review-{YYYY-MM-DD}.md`

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

**Destructive-Path Reviewer** (LARGE/VERY LARGE — when destructive-path or config-gated-change findings expected):
```
Task(
  team_name: "plan-review-{abbrev}",
  name: "destructive-path-reviewer",
  subagent_type: "planwise:plan-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

    Your assigned role: Destructive-Path Reviewer
    Execute Checks 072-073 from your protocol.
    ...
)
```

**Verification-Gate Reviewer** (LARGE/VERY LARGE — when verification-gate findings expected):
```
Task(
  team_name: "plan-review-{abbrev}",
  name: "verification-gate-reviewer",
  subagent_type: "planwise:plan-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

    Your assigned role: Verification-Gate Reviewer
    Execute Checks 074-075 from your protocol.
    ...
)
```

**Change-Surface Reviewer** (LARGE/VERY LARGE — when change-surface findings expected):
```
Task(
  team_name: "plan-review-{abbrev}",
  name: "change-surface-reviewer",
  subagent_type: "planwise:plan-reviewer",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any plan file.

    Your assigned role: Change-Surface Reviewer
    Execute Check 076 from your protocol.
    ...
)
```

7. Collect findings incrementally as DMs arrive from reviewers.
8. Track completion: each reviewer sends "Phase 2 complete, {M} findings" DM before going idle.

### Phase 3: Synthesis

9. **Deduplicate:** same file + same issue = merge; keep higher severity.
10. **Recompute delegated verdicts:** For each reviewer that returned a verdict label (GREEN/YELLOW/RED, NEEDS_FIXES/APPROVED, READY/READY-WITH-NOTES, or equivalent), recompute the classification from the reported finding counts using the task's stated classification rule. If the recomputed verdict differs from the reported label, use the recomputed verdict and log a meta-finding -- do NOT accept a verdict label without verifying it against the agent's own evidence. For cross-file control-flow claims ("symbol X never used in this file -> feature Y is broken"), trace the full consumer call path before accepting OR rejecting the finding -- single-file grep proves local non-use, not global inertness (`agent-orchestration-delegated.md` §1.16).
11. **Cross-check [UNCERTAIN] findings:**
    - Check against [Known Patterns Whitelist](../references/review-classification.md#known-patterns-whitelist)
    - Cross-check against other reviewers' findings
    - Confirmed -> promote to stated severity; contradicted -> discard as false positive
12. **Assign finding IDs:** BLOCKERs -> [B1], [B2]...; ERRORs -> [E1], [E2]...; WARNINGs -> [W1]...; INFO -> [I1]...
13. **Classify systemic findings:** For each confirmed finding (BLOCKER, ERROR, WARNING), determine one-off vs systemic (see [Systemic Finding Classification](../references/review-classification.md#systemic-finding-classification)).
14. **Compute verdict** (see [Verdict and Report](#verdict-and-report)).

### Phase 4: Report and Cleanup

15. Create `{PlanPath}/Reviews/` directory if it does not exist.
16. Write report to `{PlanPath}/Reviews/{Abbrev}-Review-{YYYY-MM-DD}.md` using [templates/review-report.md](../templates/review-report.md).
17. Send `shutdown_request` to each teammate; wait for `shutdown_response` approvals.
18. `TeamDelete`.
19. Output summary to user: verdict, finding counts by severity, systemic finding count, report path.

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
