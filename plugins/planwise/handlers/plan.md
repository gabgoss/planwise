# Handler: /planwise plan

**Purpose:** Create a new plan following structured development best practices.

---

## Config Gate

Locate `config.yaml` by checking:
1. `planwise/config.yaml` (default planwise root)
2. If not found, search one level down from the project root for `*/config.yaml`
3. If not found: "Project not initialized. Run `/planwise init` first."

Extract from `config.yaml`:
- `project.planwise_root` — the planwise root folder (default: `planwise`)
- `project.plans_dir` — the Plans directory name (relative to planwise_root)
- `project.lessons_dir` — the Lessons directory name (relative to planwise_root)
- `project.index_files.lessons` — the lessons index filename

All directory paths resolve as `{planwise_root}/{dir_name}` (e.g., `planwise/Plans`).

---

## Required References

Before proceeding, read these reference files from `${CLAUDE_PLUGIN_ROOT}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`) are pre-injected by SKILL.md.

**Plan-specific references (always load):**
1. Read `references/session-planning-protocol.md`
2. Read `references/session-plan-requirements.md`
3. Read `references/session-context-budget.md`

**Conditional references:**
- If the plan creates or modifies agents: Read `references/agent-authoring.md`
- If the plan creates or modifies skills: Read `references/skill-authoring.md`
- If the plan creates or modifies rules: Read `references/rule-authoring.md`

---

## Status Field

When `/planwise plan` completes successfully, it sets `Status: READY_TO_EXECUTE` in the Master Plan.

This status is the **execution gate**. The `/planwise run` command checks this before any work begins.

---

## Workflow

### Step 0: Detect Mode

Before gathering information, check the user's prompt for **Scaffolding Mode** indicators:

| Indicator | Mode |
|-----------|------|
| User mentions "Consolidated Context parts" or "spec parts" | **Scaffolding** |
| User provides a path to `Meta-{Abbrev}/Outputs/` | **Scaffolding** |
| User says "scaffold", "scaffolding phase", or "from Discovery" | **Scaffolding** |
| `--scaffold` flag present in arguments | **Scaffolding** |
| None of the above | **Standard** (proceed to Step 1) |

**If Scaffolding Mode:** Follow the [Scaffolding Workflow](#scaffolding-workflow) section below instead of Steps 1-9.

---

### Step 1: Gather Information

Parse `$1` for the plan name. If `$1` is empty, use `AskUserQuestion` to collect it.

Use `AskUserQuestion` to collect:

**Question 1: Plan Details**
- What is the name of your plan? (e.g., "UserAuthentication", "DataMigration") — pre-fill from `$1` if provided
- What is the 2-4 character abbreviation? (e.g., "UA", "DM")
- Briefly describe the vision (1-2 sentences)

**Question 2: Scope**
- How many sprints do you anticipate? (1-5)
- What is the first sprint's name and purpose?

### Step 2: Validate

Before creating files, verify:

```
[ ] Abbreviation is 2-4 characters
[ ] Abbreviation is unique (check {plans_dir} for existing)
[ ] Vision is clear and actionable
[ ] At least one sprint is defined
```

If validation fails, ask user to correct.

### Step 3: Create Folder Structure

Create the following structure under the configured `{plans_dir}`:

```
{plans_dir}/{PlanName}/
├── {Abbrev}-Master-Plan.md
├── Sprint-01-{SprintName}/
│   ├── {Abbrev}-S01-Sprint-Plan.md
│   └── Session-01-{FirstSessionName}/
│       ├── {Abbrev}-S01-01-Orchestration.md
│       ├── {Abbrev}-S01-01-Recovery.md
│       ├── {Abbrev}-S01-01-{##}-{Agent}-{Task}.md   # One file per task
│       └── Outputs/
```

**Task File Naming:** `{##}` = two-digit task number (01, 02, 03...) matching the task list.

### Steps 4-7: Generate Files

Use templates from `${CLAUDE_PLUGIN_ROOT}/templates/`:

| Step | Template | Output File |
|------|----------|-------------|
| 4 | [master-plan.md](../templates/master-plan.md) | `{Abbrev}-Master-Plan.md` |
| 5 | [sprint-plan.md](../templates/sprint-plan.md) | `{Abbrev}-S01-Sprint-Plan.md` |
| 6 | [orchestration.md](../templates/orchestration.md) | `{Abbrev}-S01-01-Orchestration.md` |
| 7 | [recovery.md](../templates/recovery.md) | `{Abbrev}-S01-01-Recovery.md` |

### Step 8: Generate Task Files

**CRITICAL:** Create ONE task file per task in the Orchestration task list.

For each task, create a file using the [task-file.md](../templates/task-file.md) template.

**File name pattern:** `{Abbrev}-S01-01-{##}-{Agent}-{TaskName}.md`

After creating task files, update the Orchestration file's Task Files table with links.

### Step 8b: Add Lessons Reference to Post-Session Checklist

Each Orchestration file created MUST include this item in its post-session checklist:

```
[ ] Document lessons learned in {lessons_dir}/LL-{NNN}-{Domain}-{Name}.md
    - Get next NNN from master table in {lessons_dir}/{lessons_index}
    - Use Lesson File Template from {lessons_dir}/{lessons_index}
    - Required frontmatter: id, title, date, source (session ID), category, severity,
      language, technology, domain, status, applied-as
    - Add row to master table in {lessons_dir}/{lessons_index}
```

Where `{lessons_dir}` and `{lessons_index}` come from `config.yaml`.

### Step 8c: Validate Token Estimates (Bottom-Up)

For each task in the session, compute a bottom-up token estimate:

1. **Measure Required Context files:** For each file in the task's Required Context table, estimate line count (check actual size with Glob/Read or use domain heuristics)
2. **Convert to tokens:** Apply ~13 tokens/line (see [Token Estimation Reference](#token-estimation-reference))
3. **Add output cost:** Estimate output generation tokens from the operation-level table
4. **Compare:** If the bottom-up estimate exceeds the qualitative category estimate, use the higher number
5. **DELEGATED check:** For DELEGATED tasks, verify (task estimate + 54K subagent overhead) < 200K

Update the task's `Estimated Tokens` field and the Orchestration Session Task List with the validated estimates.

---

### Step 9: Output Confirmation

After creating all files, output:

```
PLAN CREATED: {PlanName}

**Abbreviation:** {ABBREV}
**Location:** {plans_dir}/{PlanName}/

**Files Created:**
- {Abbrev}-Master-Plan.md
- Sprint-01-{SprintName}/{Abbrev}-S01-Sprint-Plan.md
- Sprint-01-{SprintName}/Session-01-{SessionName}/{Abbrev}-S01-01-Orchestration.md
- Sprint-01-{SprintName}/Session-01-{SessionName}/{Abbrev}-S01-01-Recovery.md
- Sprint-01-{SprintName}/Session-01-{SessionName}/{Abbrev}-S01-01-{##}-{Agent}-{Task}.md (x{N} task files)
- Sprint-01-{SprintName}/Session-01-{SessionName}/Outputs/ (folder)

**Task Files Created:** {N} files (one per task)

**Next Steps:**
1. Review and refine the Master Plan
2. Review task files for completeness
3. Run `/planwise review {Abbrev}` to validate the plan (recommended before execution)
4. Execute Session-01 using `/planwise run` or manually following READ-CONFIRM-ACT
```

### Step 10: Plan Review Gate

After outputting the Step 9 confirmation, offer plan review options.

Use `AskUserQuestion` with:

**Question 1: Plan Review Approach**
- "Auto-review with /planwise review" (Recommended) -- Spawn a subagent to validate the plan and return findings
- "Review manually first" -- User will review plan files before executing
- "Skip to /planwise run" -- Proceed directly to execution

**Question 2: Review Context** (show only if Question 1 = auto-review)
- "Run in this session" (Recommended for standard plans) -- Subagent gets fresh context; no token budget concern
- "Run in a new session" -- Output the command for user to run separately; recommended if this was a large scaffolding session

**If auto-review + this session:**

Spawn the review as a Task subagent:

```
Task(
  subagent_type: "general-purpose",
  description: "Plan review for {Abbrev}",
  prompt: "Run /planwise review {plan-folder-path}. Return: verdict, finding counts
          by severity, systemic finding count, and report file path."
)
```

Present the subagent's results to the user:
- If **APPROVED** -- "Plan validated. Ready to execute with `/planwise run @{orch-path}`"
- If **NEEDS_FIXES** -- "Review found issues. Fix findings in the report, then re-run `/planwise review` or proceed to `/planwise run`"

**If auto-review + new session:**

Output:
```
To review this plan, run in a new session:
/planwise review {plan-path}
```

**If manual review or skip:** No additional action needed.

---

## Validation Checklist

Before completing `/planwise plan`, verify:

```
[ ] Abbreviation is 2-4 chars and unique
[ ] Master Plan has Vision and Sprint Overview
[ ] Sprint Plan has Objective and Sessions table
[ ] Orchestration has Task List
[ ] Orchestration has Task Files table with links
[ ] Task files exist (one per task, numbered 01, 02, 03...)
[ ] Task files follow naming: {Abbrev}-S{XX}-{YY}-{##}-{Agent}-{Task}.md
[ ] Recovery file initialized
[ ] Outputs/ folder created
[ ] All files follow naming conventions
[ ] Session token estimates validated (< 100K per session)
[ ] Each task has a bottom-up estimate: (Required Context tokens) + (output tokens) <= task estimate
[ ] If DELEGATED: each task estimate + 54K overhead < 200K
[ ] Execution Strategy declared in Orchestration (DIRECT or DELEGATED)
[ ] If 2+ Opus tasks or META session -> Strategy is DELEGATED
[ ] If DELEGATED: Orchestration Required Context = plan files only
[ ] If DELEGATED: Context Boundary subsection lists what orchestrator never reads
```

---

## Scaffolding Workflow

**When:** A Meta-Plan Discovery phase produced Consolidated Context parts, and you need to create the Execution Plan from those parts.

**Input:** `Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md` files

### Scaffolding Step 1: Read Consolidated Context Parts

1. Find all `{Abbrev}-Consolidated-Context-Part-*.md` files in `Meta-{Abbrev}/Outputs/`
2. Read EVERY part completely -- each part's header has `Scope:` (the sprint it feeds) and a `What This Enables` section
3. Note: Part headers contain cross-references between parts

### Scaffolding Step 2: Determine Plan Details

From the user's prompt or by asking:
- **Abbreviation:** Same as the Meta-Plan's abbreviation (e.g., `GCW`)
- **Root:** `{plans_dir}/{PlanName}/Exec-{Abbrev}/` (resolved from config.yaml)
- **Sprints:** Derived from each part's `Scope:` field (one sprint per execution-scoped part)
- If stale `Exec-{Abbrev}/` files exist from a placeholder, **delete them first**

### Scaffolding Step 3: Design Sprints from Parts

Map each Consolidated Context part to a sprint. Each part's `Scope:` and `What This Enables` section defines that sprint's work.

**Rules:**
- Parts with `Scope: Cross-sprint reference` are NOT sprints -- they're referenced by all sprints
- Parts with a specific scope (e.g., "Schema Implementation Sprint") become sprints
- Sprint ordering follows dependency logic (schema before registration before queries)
- The user may suggest a sprint structure -- respect it but validate against part content

**Global Source Map:** If using global numbering for source specs (recommended for multi-sprint plans), add a Global Source Map table to the Master Plan. This table assigns each spec output a global number and shows which sprints use it. See the [scaffolding master plan template](../templates/scaffolding-master-plan.md) for the table format.

### Scaffolding Step 4: Create Execution Inputs

For EACH sprint, produce an **Execution Input** file -- a sprint-scoped extraction of the Consolidated Context parts. Use the [execution-input.md](../templates/execution-input.md) template.

**Process:**
1. Identify which Consolidated Context parts feed this sprint (from Step 3 mapping)
2. Read those parts and identify which sections each task in the sprint needs
3. **Extract** the relevant content into sections, noting which tasks use each section
4. From cross-sprint reference parts, extract ONLY the decisions/conventions this sprint needs
5. Add Cross-References table tracing each section back to its source
6. If over 500 lines, split into parts: `{Abbrev}-S{XX}-Execution-Input-Part-{N}-{Topic}.md`

**Output:** One `{Abbrev}-S{XX}-Execution-Input.md` per sprint, placed in the sprint folder.

**This is extraction, not summarization.** Copy substantive content verbatim -- only reorganize by sprint scope.

**Cross-sprint content handling:**
- **Cross-sprint reference parts** (e.g., DesignDecisions with `Scope: Cross-sprint reference`): Extract relevant portions into each sprint's EI
- **Sprint-scoped sources with cross-relevant sections**: If Sprint 02 needs content from a source primarily assigned to Sprint 01, list that source in the EI's `Extracted from:` header like any other source. The Global Source Map in the Master Plan tracks which sources are shared

### Scaffolding Step 5: Generate Plan Files

Use the [scaffolding master plan template](../templates/scaffolding-master-plan.md) for the Master Plan.

Use standard templates for all other files (sprint plans, orchestrations, recovery, task files).

**Critical difference from standard planning:** Every task file's `Required Context` table MUST reference the sprint's **Execution Input** file (with section numbers), NOT the original Consolidated Context parts. The Execution Input replaces the parts for execution purposes.

### Scaffolding Step 6: Validation

Same checklist as standard mode, plus:

```
[ ] Every Consolidated Context part is covered by at least one sprint
[ ] Every sprint has an Execution Input file (or multi-part set)
[ ] Execution Inputs contain extracted content (not just references)
[ ] Execution Input sections map to specific tasks (noted in headers)
[ ] Every Execution Input has a Cross-References table
[ ] Every task file references its sprint's Execution Input (NOT the original parts)
[ ] Cross-sprint reference content is extracted into relevant sprint Execution Inputs
[ ] No Consolidated Context content is orphaned (uncovered by any Execution Input)
[ ] Cross-References use Spec #{N} (filename.md) format -- number + filename together
[ ] Cross-References cite only files listed in "Extracted from:" header
[ ] Task file Required Context enumerates individual section numbers with purpose (no ranges)
[ ] Cross-sprint task references use full Task ID format ({Abbrev}-S{XX}-{YY}-{##})
[ ] If global numbering used, Global Source Map exists in Master Plan
```

### Scaffolding Step 7: Output Confirmation

Same as Step 9 in standard mode, plus include:

```
SCAFFOLDED FROM: Meta-{Abbrev} Discovery Phase
Parts consumed: {N} Consolidated Context parts
Execution Inputs created: {N} (one per sprint)
Sprints created: {N}
```

For a complete scaffolding example, see [sample-scaffolding-output.md](../examples/sample-scaffolding-output.md).

After the scaffolding confirmation, proceed to [Step 10: Plan Review Gate](#step-10-plan-review-gate).

---

## Naming Conventions

### Plan Abbreviation

- **2-4 characters**, unique across project
- Examples: `DVD`, `CI`, `CNSA`, `PI`, `SSU`

### File Naming Patterns

| Type | Pattern | Example |
|------|---------|---------|
| Master Plan | `{Abbrev}-Master-Plan.md` | `PI-Master-Plan.md` |
| Sprint Plan | `{Abbrev}-S{XX}-Sprint-Plan.md` | `PI-S01-Sprint-Plan.md` |
| Orchestration | `{Abbrev}-S{XX}-{YY}-Orchestration.md` | `PI-S01-01-Orchestration.md` |
| Recovery | `{Abbrev}-S{XX}-{YY}-Recovery.md` | `PI-S01-01-Recovery.md` |
| Task (Haiku) | `{Abbrev}-S{XX}-{YY}-{##}-Haiku-{Task}.md` | `PI-S01-01-01-Haiku-Verify.md` |
| Task (Sonnet) | `{Abbrev}-S{XX}-{YY}-{##}-Sonnet-{Task}.md` | `PI-S01-01-02-Sonnet-Generate.md` |
| Task (Opus) | `{Abbrev}-S{XX}-{YY}-{##}-Opus-{Task}.md` | `PI-S01-01-03-Opus-Design.md` |
| Summary | `{Abbrev}-S{XX}-{YY}-Summary.md` | `PI-S01-01-Summary.md` |
| Execution Input | `{Abbrev}-S{XX}-Execution-Input.md` | `PI-S01-Execution-Input.md` |
| Execution Input (multi-part) | `{Abbrev}-S{XX}-Execution-Input-Part-{N}-{Topic}.md` | `PI-S01-Execution-Input-Part-1-Schema.md` |

### Task Number Convention

- `{##}` = Two-digit task number (01, 02, 03...)
- Task numbers match the `#` column in the Orchestration task list
- One file per task -- NEVER combine multiple tasks into one file

---

## Token Budget Rules

### Session Limits

**Available for work:** ~100K (after system overhead)

| Pattern | Initial Load | Growth | Total | Guideline |
|---------|--------------|--------|-------|-----------|
| Discovery | < 30K | +40-50K | ~70-80K | Don't know files upfront |
| Planned | 30-70K | +10-20K | ~80-90K | Know most files upfront |
| Front-loaded | 70-90K | +5-10K | ~95-100K | Know all files upfront |
| **Too Large** | > 100K | - | - | **MUST use Meta-Plan** |

### Task Sizing Categories

| Task Size | Token Estimate | Guideline |
|-----------|----------------|-----------|
| Small | < 20K | Single file, simple lookup |
| Medium | 20-50K | Multi-file, code generation |
| Large | 50-80K | Complex analysis, multiple entities |
| Too Large | > 80K | **MUST SPLIT** |

**These categories are a cross-check, not the primary estimate.** Always compute the bottom-up estimate first, then compare against the category. Use the HIGHER of the two.

**Note:** Session limits (~100K) apply to DIRECT mode in the main conversation. In DELEGATED mode, each task-runner subagent gets a fresh context budget. Verify: (task estimate + 54K overhead) < 200K per subagent.

### Token Estimation Reference

Use this table to compute bottom-up token estimates for each task.

**File Read Costs:**

| Operation | Approx. Tokens | Heuristic |
|-----------|----------------|-----------|
| Read file | ~13 tokens/line | Measure or estimate actual line count |
| Read 100-line file | ~1.3K | Small config, helper |
| Read 200-line file | ~2.6K | Medium file |
| Read 500-line file | ~6.5K | Large reference doc or entity |
| Read 1000-line file | ~13K | Very large file -- consider if full read is needed |

**Output Generation Costs:**

| Operation | Approx. Tokens | Scaling Factor |
|-----------|----------------|----------------|
| Generate C# entity | ~3-5K per entity | Scale by property count |
| Generate controller | ~5-8K | Scale by action count |
| Generate Razor view | ~3-6K | Scale by complexity |
| Generate migration | ~2-4K | Scale by entity count |
| Error analysis + fix | ~5-10K | Includes iteration |
| Complex decision (Opus) | ~10-20K | Architecture/trade-offs |

**Overhead Costs (DELEGATED mode):**

| Component | Approx. Tokens | Notes |
|-----------|----------------|-------|
| System prompt | ~4K | Fixed per subagent |
| System tools | ~22K | Fixed per subagent |
| Global rules + CLAUDE.md | ~27K | Always loaded |
| Skills + agents (descriptions) | ~1K | Always loaded |
| **Total subagent overhead** | **~54K** | Empirical (from /context on fresh session) |

**Bottom-Up Estimation Formula:**

```
Task Estimate = (sum of Required Context file tokens) + (estimated output tokens)
DELEGATED check: Task Estimate + 54K overhead < 200K per subagent (standard context)
```

---

## Agent Assignment

| Task Type | Agent | Examples |
|-----------|-------|----------|
| Lookups, validation | **Haiku** | Counts, find files, verify |
| Code generation | **Sonnet** | Entities, controllers, views |
| Architecture/decisions | **Opus** | Design, trade-offs, analysis |

---

## Additional Resources

- [session-planning-protocol.md](../references/session-planning-protocol.md) -- Detailed protocol: plan hierarchy, naming conventions, agent delegation, recovery, checklists, git workflow, READ-CONFIRM-ACT
- [templates/](../templates/) -- All plan templates (including scaffolding master plan)
- [examples/sample-plan-output.md](../examples/sample-plan-output.md) -- Example standard plan
- [examples/sample-scaffolding-output.md](../examples/sample-scaffolding-output.md) -- Example scaffolding from Discovery
