# Handler: /planwise plan

**Purpose:** Create a new plan following structured development best practices.

## Table of Contents

- [Config Gate](#config-gate)
- [Required References](#required-references)
- [Status Field](#status-field)
- [Workflow](#workflow)
  - [Step 0: Detect Mode](#step-0-detect-mode)
  - [Steps 1-9: Standard Plan](#step-1-gather-information)
  - [Step 10: Plan Review Gate](#step-10-plan-review-gate)
- [Validation Checklist](#validation-checklist)
- [Discovery Workflow](#discovery-workflow)
- [Scaffolding Workflow](#scaffolding-workflow)
- [Naming Conventions](#naming-conventions)
- [Token Budget Rules](#token-budget-rules)
- [Agent Assignment](#agent-assignment)
- [Additional Resources](#additional-resources)

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml:
   a. Check `planwise/config.yaml` (default planwise root)
   b. If not found, search one level down from project root for `*/config.yaml`

2. If found → continue to Required References (extract `plugin_root`, `project.planwise_root`, `project.plans_dir`, `project.lessons_dir`, `project.index_files.lessons`).

3. If NOT found:
   a. Announce: "Planwise not initialized in this project. Running /planwise init first…"
   b. Resolve `{plugin_root}` from the handler's own known location (SKILL.md plugin base path).
   c. Invoke init subroutine:
      - **If Auto Mode active:**
        ```bash
        python "{plugin_root}/scripts/init_project.py" \
          --name "{inferred_project_name}" \
          --root "planwise" \
          --plans-dir "Plans" \
          --backlog-dir "Backlog" \
          --lessons-dir "LessonsLearned" \
          --scope "project" \
          --auto-from "plan"
        ```
      - **If Auto Mode NOT active (interactive):**
        Use `AskUserQuestion` to collect project info (project name, scope, dirs),
        then run `init_project.py` with those values + `--auto-from "plan"`.
   d. After init completes, RE-RESOLVE `config.yaml` (loop to step 1).
   e. If still NOT found after init:
      FAIL LOUD: "Init did not produce config.yaml. See output above."
      STOP — do not continue.

Where `{inferred_project_name}` = current git repo name or `cwd` basename (strip trailing `-`, `_`, `.git` suffix).

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed (YAMLError), DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise plan." STOP.

All directory paths resolve as `{planwise_root}/{dir_name}` (e.g., `planwise/Plans`).

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`) are pre-injected by SKILL.md.

**Plan-specific references (always load):**
1. Read `references/session-planning-protocol.md`
2. Read `references/session-plan-requirements.md`
3. Read `references/session-context-budget.md`
4. Read `references/session-execution-protocol.md` — source for READ-CONFIRM-ACT, the structural-findings gate, session invariants, and the post-step checklist (cited in this handler's checklists)

**Conditional references:**
- If the plan creates or modifies agents: Read `references/agent-authoring.md`
- If the plan creates or modifies skills: Read `references/skill-authoring.md`
- If the plan creates or modifies rules: Read `references/rule-authoring.md`
- If planning a scaffolded multi-sprint plan (Discovery → Scaffolding workflow): Read `references/ei-fidelity.md`, `references/task-content-fidelity.md`, `references/discovery-and-exit-criteria.md`, `references/scaffolding-hygiene.md`
- If planning a task with DB writes (SQL INSERT/UPDATE/MERGE): Read `references/schema-pin-requirement.md`

---

## Status Field

When `/planwise plan` completes successfully, it sets `Status: READY_TO_EXECUTE` in the Master Plan.

This status is the **execution gate**. The `/planwise run` command checks this before any work begins.

---

## Workflow

### Step 0: Detect Mode

Before gathering information, check the user's prompt for **Discovery Mode** and **Scaffolding Mode** indicators. Check Discovery first — it is upstream of Scaffolding.

#### Discovery Mode (Meta-Plan Creation)

**Explicit indicators** (go directly to Discovery Workflow):

| Indicator | Action |
|-----------|--------|
| `--meta` flag present in arguments | **Discovery** |
| User says "meta-plan", "discovery phase", or "consolidated context" | **Discovery** |
| User says the context is "too large" or above `meta_plan_threshold` (100K on Pro / 500K on Max — see `references/session-context-budget.md` §5 Threshold Formulas) | **Discovery** |

**Implicit indicators** (recommend Discovery via `AskUserQuestion`):

| Indicator | Action |
|-----------|--------|
| User describes needing to read many source files across multiple domains | **Recommend Discovery** |
| User says there's "too much to read in one session" or "too much context" | **Recommend Discovery** |
| Source material spans multiple large files (estimated total > `meta_plan_threshold` — 100K on Pro, 500K on Max) | **Recommend Discovery** |
| User asks to "organize", "consolidate", or "cross-reference" source material | **Recommend Discovery** |

<!-- AUTO-MODE: critical -->
If **any Discovery implicit indicator** is detected without an explicit indicator, use `AskUserQuestion`. Resolve `meta_plan_threshold` first by reading `context.context_window` from `config.yaml` (100K on Pro, 500K on Max). Substitute that value into the prompt:

> "Your project appears to require more context than fits in a single session (above ~{meta_plan_threshold} tokens for this plan tier). The **Meta-Plan Discovery** workflow reads source material across multiple sessions, consolidates findings into structured Consolidated Context Parts, and then scaffolds an Execution Plan from those parts. **Recommended: use Discovery (Meta-Plan).** Proceed with Discovery, Scaffolding (if you already have Consolidated Context parts), or Standard?"

- If user chooses **Discovery** → follow the [Discovery Workflow](#discovery-workflow) below
- If user chooses **Scaffolding** → follow the [Scaffolding Workflow](#scaffolding-workflow) below
- If user chooses **Standard** → proceed to Step 1

**If Discovery Mode (explicit):** Follow the [Discovery Workflow](#discovery-workflow) section below instead of Steps 1-9.

#### Scaffolding Mode (Execution Plan from Discovery Outputs)

**Explicit indicators** (go directly to Scaffolding Workflow):

| Indicator | Action |
|-----------|--------|
| `--scaffold` flag present in arguments | **Scaffolding** |
| User says "scaffold", "scaffolding phase", or "from Discovery" | **Scaffolding** |

**Optional Scaffolding flag — `--scaffold-per-sprint`:**

When `--scaffold-per-sprint` is present, scaffold ONE sprint at a time, pausing after each for user confirmation. This allows user-action gates between sprints (e.g., user reviews Sprint-01 scaffold before scaffolding Sprint-02).

Behavior:
1. Scaffold Sprint-01 completely (EI + plan files + task files)
2. Set Master Plan Status: `IN_PROGRESS — Sprint-01 scaffolded; awaiting user review`
3. <!-- AUTO-MODE: critical -->
   Use `AskUserQuestion`: "Sprint-01 scaffold complete. Proceed with Sprint-02 scaffolding?"
4. Repeat for each sprint

Without the flag (default), scaffold all sprints in one pass.

> [!practice] Scope — Pause-Between-Sprints, Not Per-Sprint Scaffold Sessions
> The `--scaffold-per-sprint` flag is an **in-conversation pause-and-confirm** mechanism — it does NOT create per-Exec-sprint `Scaffold-{Abbrev}-S{XX}/` sessions with their own Orchestration/Recovery files (which the source PLG-008 spec envisioned for compaction-resume capability). The simpler pause-only mechanism shipped intentionally; per PPU-S08-02 Disposition Ledger row P5-5 (Verdict: JUSTIFIED-SKIP *out-of-remediation-scope*), the full per-sprint Scaffold-session resume mechanism is a new feature beyond the PPU remediation scope. Future maintainers — do NOT treat the absence of per-sprint Scaffold sessions as a regression; it is the documented design. If compaction during multi-sprint scaffolding becomes a real problem, file a NEW backlog item (do not silently expand this flag's contract).

**Implicit indicators** (recommend Scaffolding via `AskUserQuestion`):

| Indicator | Action |
|-----------|--------|
| User-provided paths contain `Meta-` prefix | **Recommend Scaffolding** |
| User references `/Outputs/` directories | **Recommend Scaffolding** |
| User mentions "Consolidated Context parts" or "spec parts" | **Recommend Scaffolding** |
| Existing `Meta-{Abbrev}/Outputs/` folder contains `Consolidated-Context-Part-*` files | **Recommend Scaffolding** |

<!-- AUTO-MODE: critical -->
If **any Scaffolding implicit indicator** is detected without an explicit indicator, use `AskUserQuestion`:

> "Your source material references Meta-Plan Discovery outputs. The Scaffolding workflow creates focused per-sprint Execution Inputs from this research, preventing subagents from reading entire Discovery docs. **Recommended: use Scaffolding.** Proceed with Scaffolding or Standard?"

- If user chooses **Scaffolding** → follow the [Scaffolding Workflow](#scaffolding-workflow) below
- If user chooses **Standard** → proceed to Step 1

#### No Mode Detected

If **no indicators** are detected → proceed to Step 1 (Standard).

---

### Step 1: Gather Information

Parse `$1` for the plan name. If `$1` is empty, use `AskUserQuestion` to collect it.

<!-- AUTO-MODE: critical -->
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
[ ] Abbreviation is 2-4 characters (see validation protocol below)
[ ] Abbreviation is unique (check {plans_dir} for existing)
[ ] Vision is clear and actionable
[ ] At least one sprint is defined
```

If validation fails, ask user to correct.

#### Abbreviation Length Validation

> [!constraint] Never Silently Truncate Abbreviations
> WRONG: User provides `HBS-VBD` → handler silently truncates to `VBD` and proceeds.
>
> CORRECT: User provides `HBS-VBD` → handler prompts with `AskUserQuestion` showing the constraint, what they provided, and alternatives.

<!-- AUTO-MODE: critical -->
> [!protocol] Abbreviation Validation Protocol
> 1. Check if the user-provided abbreviation is 2-4 characters
> 2. If valid (2-4 chars) → proceed to uniqueness check
> 3. If invalid (< 2 or > 4 chars) → use `AskUserQuestion` with the following:
>
>    **Prompt the user with:**
>    - The constraint: "Planwise abbreviations must be 2-4 characters"
>    - What they provided: "`{user_abbrev}` is {N} characters"
>    - Alternatives (present all that apply):
>
>    | # | Alternative | When to Show |
>    |---|-------------|--------------|
>    | 1 | "`{matching_abbrev}` (matches existing `Meta-{matching_abbrev}/` — recommended)" | A `Meta-{portion}/` folder exists in `{plans_dir}` for a substring of the provided abbreviation |
>    | 2 | "`{truncated}` (first 4 characters)" | Always (as fallback) |
>    | 3 | "Other — type your preferred 2-4 character abbreviation" | Always |
>
> 4. Validate the user's choice is 2-4 characters — if not, repeat from step 3

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
│           └── .gitkeep                              # Required so Outputs/ is tracked by git
```

**Task File Naming:** `{##}` = two-digit task number (01, 02, 03...) matching the task list.

> [!constraint] Emit `Outputs/.gitkeep` for Every Session Folder
> WRONG — Outputs/ folder created empty; git does not track empty directories, so the folder disappears on clone:
> ```
> mkdir Session-01-{Name}/Outputs    # ← empty dir, not committed
> ```
> CORRECT — write an `Outputs/.gitkeep` placeholder file inside every session's Outputs/ folder so the directory is preserved in version control:
> ```
> Write {plans_dir}/{PlanName}/Sprint-01-{Name}/Session-01-{Name}/Outputs/.gitkeep
> ```
> Apply this to EVERY session folder created during planning (standard mode here, Scaffolding Step 5 for scaffolded plans). The `.gitkeep` file is an empty placeholder — its purpose is solely to make git track the otherwise-empty `Outputs/` directory.

### Steps 4-7: Generate Files

Use templates from `{plugin_root}/templates/`:

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
5. **DELEGATED check:** For DELEGATED tasks, verify `(task estimate + 54K subagent overhead) < context_window` per subagent. Subagents inherit the parent session's tier, so `context_window` comes from `config.yaml` `context.context_window` (defaults to 200,000 when the block is missing). See `references/session-context-budget.md` §5 Threshold Formulas.

Update the task's `Estimated Tokens` field and the Orchestration Session Task List with the validated estimates.

### Step 8d: Update Plans Index

Add a row to the plans index so `/planwise list` reflects the new plan:

1. Read `{plans_dir}/{plans_index}` (path from `config.yaml`)
2. Add a row to the table:
   - **Abbrev:** `{ABBREV}`
   - **Name:** `{PlanName}`
   - **Status:** `NOT_STARTED`
   - **Created:** `{today's date}`
   - **Last Updated:** `{today's date}`
   - **Path:** `{plans_dir}/{PlanName}/`
3. Write the updated index back to disk

### Step 8e: Populate Verification Commands (Per-File-Type Map)

For every task file generated in Step 8 whose task touches code, tests, or schemas, populate
the **Verification Commands** section using a per-file-type command map — never leave the
section's `{placeholder}` tokens unfilled. The plan-reviewer treats blank, vague, or single-type
Verification Commands as a finding (`references/session-plan-requirements.md` §Verification
Commands Plan-Review Enforcement table; `templates/task-file.md` §Per-File-Type Commands).

**Procedure:**

1. **Inspect** the task's Expected Output and Execution Steps to identify the set of file
   extensions the task creates or modifies (e.g., `.py`, `.ipynb`, `.sql`, `.cs`, `.cshtml`,
   `.ts`, `.tsx`, `.md`).
2. **Look up** the verification command(s) for each extension in the per-file-type command
   map below (resolve `{lint-cmd}`, `{format-cmd}`, `{exec-cmd}`, `{notebook-exec-cmd}` from
   `config.yaml.build_commands` or project convention).
3. **Emit** a `Verification Commands` section in the task file using the
   `templates/task-file.md` `> [!verify] Before / After Commands` block + Per-File-Type
   Commands table — substitute every `{placeholder}` with a concrete shell invocation.
4. **Ensure all three command types appear** (connectivity / pre-condition, lint or format,
   exec or smoke test). A task missing one of these types is downgraded to a `> [!verify]`
   block with a `<!-- NEEDS-COMMAND -->` comment so the gap is visible at review time, NOT
   silently left blank.

**Per-File-Type Command Map** (mirrors `templates/task-file.md` §Per-File-Type Commands):

| File Type | Lint / Format | Exec / Smoke | Notes |
|-----------|--------------|--------------|-------|
| `.{src-ext}` (compiled or scripted source) | `{lint-cmd} {path}` / `{format-cmd} {path}` | `{test-cmd} {path}` | Consumer fills `{lint-cmd}` / `{test-cmd}` from `config.yaml.build_commands` |
| `.{notebook-ext}` (runnable-notebook artifact) | `{lint-cmd} {path}` (if applicable) | `{exec-cmd} {path}` | `{exec-cmd}` is the consumer's notebook runner / execute-in-place command |
| `.sql` | `{sql-lint-cmd} {path}` (if applicable) | `{driver-cli} -f {path}` | DB writes also pin schema per `references/schema-pin-requirement.md` |
| `.{build-system-ext}` (e.g., compiled-language sources) | `{format-cmd} {project} --verify-no-changes` | `{build-cmd} {project}` then `{test-cmd} {project}` | Connectivity precheck if integration test |
| `.{view-template-ext}` | `{format-cmd} {project} --verify-no-changes` | `{build-cmd} {project}` | Smoke render if applicable |
| `.{ts-ext}` / `.{tsx-ext}` | `{lint-cmd} {path}` | `{build-cmd}` then `{test-cmd}` | Plus `{type-check-cmd}` if the language supports it |
| `.md` (reference / rule edits) | `{md-lint-cmd} {path}` (if configured) | `{line-count-cmd} {path}` (file ≤ 500 lines per soft limit) | Per `references/markdown-conventions.md` §2 |
| `.{ext}` (other) | `{lint-cmd} {path}` | `{exec-cmd}` | Consumer-project supplies the binding from `config.yaml.build_commands` |

> [!constraint] Verification Commands MUST Be Populated, Not Templated
> WRONG — task file ships with the literal `{cmd_before_1}` / `{cmd_after_1}` placeholders, or
> with vague prose like "run lint and tests":
> ```markdown
> ## Verification Commands
> > [!verify] Before / After Commands
> > **Before:** {cmd_before_1}
> > **After:**  {cmd_after_1}
> ```
> CORRECT — placeholders resolved to explicit shell invocations from the per-file-type map,
> covering all three command types (precheck + lint/format + exec):
> ```markdown
> ## Verification Commands
> > [!verify] Before / After Commands
> > **Before:**
> > ```
> > {lint-cmd} src/{module}/        # lint baseline
> > {test-cmd} src/{module}/        # test baseline
> > ```
> > **After:**
> > ```
> > {lint-cmd} src/{module}/        # expect: pass
> > {test-cmd} src/{module}/        # expect: green
> > ```
> ```
>
> A blank or vague Verification Commands section is a `/planwise review` finding (per the
> `Verification Commands Plan-Review Enforcement` table in `session-plan-requirements.md`).

**If the task creates no code/test/schema files** (pure documentation, decision-only, or
research): the Verification Commands section MAY be omitted, but the task file MUST then
include a `<!-- VERIFICATION: not-applicable (reason) -->` HTML comment in its `## Notes for
Agent` section so the reviewer can confirm the omission was intentional.

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

**Mega-Scaffold Gate — count sprints authored this pass.**

Before presenting the review options, count `n_sprints_scaffolded_this_pass` — the number of distinct Sprint Plan files this `/planwise plan` invocation authored. For a standard single-sprint plan, this is 1. For an inline mega-scaffold (`/planwise plan --scaffold` against Meta-Plan output, or a multi-sprint `/planwise plan` session that authored 2+ Sprint Plan files in one pass), this can be 2 or more.

If `n_sprints_scaffolded_this_pass ≥ 2`, the "Skip to /planwise run" option is REMOVED from Question 1 below — `/planwise review` becomes mandatory. The rationale and full rule live at `references/scaffolding-hygiene.md` §11 (Mega-Scaffold Review-Gate); the short version is that inline mega-scaffolds trade per-sprint authoring-time self-review for speed, and the post-scaffold review gate is what catches the EI header⇄Cross-References hygiene defects that otherwise ride into execution.

<!-- AUTO-MODE: convenience -->
<!-- Default: auto-review in this session. -->
Use `AskUserQuestion` with:

**Question 1: Plan Review Approach**

*If `n_sprints_scaffolded_this_pass == 1` (standard single-sprint plan):*

- "Auto-review with /planwise review" (Recommended) -- Spawn a subagent to validate the plan and return findings
- "Review manually first" -- User will review plan files before executing
- "Skip to /planwise run" -- Proceed directly to execution

*If `n_sprints_scaffolded_this_pass ≥ 2` (mega-scaffold — review is MANDATORY per `references/scaffolding-hygiene.md` §11):*

- "Auto-review with /planwise review" (Recommended) -- Spawn a subagent to validate the plan and return findings
- "Review manually first" -- User will review plan files before executing

(The "Skip to /planwise run" option is intentionally omitted for multi-sprint scaffolds. If review must legitimately be deferred — e.g., a follow-up session is scheduled — record the deferral in the Master Plan's Status note rather than skipping the gate.)

<!-- AUTO-MODE: convenience -->
<!-- Default: this session; switch to new session if > 3 sprints or > 10 task files. -->
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
[ ] Plans index updated with new row (Abbrev, Name, Status, Created, Last Updated, Path)
[ ] Session token estimates validated (< `practical_session_limit` per session — 100K on Pro, 400K on Max; see `references/session-context-budget.md` §5)
[ ] Each task has a bottom-up estimate: (Required Context tokens) + (output tokens) <= task estimate
[ ] If DELEGATED: each task estimate + 54K overhead < `context_window` (200K on Pro, 1M on Max)
[ ] Execution Strategy declared in Orchestration (DIRECT or DELEGATED)
[ ] If 2+ Opus tasks or META session -> Strategy is DELEGATED
[ ] If DELEGATED: Orchestration Required Context = plan files only
[ ] If DELEGATED: Context Boundary subsection lists what orchestrator never reads
[ ] If Discovery → Scaffolding: Multi-tier extraction tiers documented in EI header (Tier 1 + Tier 2 + Tier 3 where applicable)
[ ] If Discovery → Scaffolding: Deferred/Out-of-Scope Log present per sprint
[ ] If Discovery → Scaffolding: Retention threshold ≥ 80 % per EI section (auto-reject below)
[ ] If Discovery has user-action gates outside /planwise run: Master Plan Status is IN_PROGRESS with `awaiting {user action}` note (per `references/session-execution-protocol.md` Discovery / Meta-Plan Status section)
```

---

## Discovery Workflow

**When:** Total context exceeds ~100K tokens, or the user explicitly requests a Meta-Plan. The Discovery phase reads source material, cross-references it, and produces Consolidated Context Parts — structured, full-detail specification documents organized by execution scope.

**Output:** `Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md` files

> [!constraint] Discovery ≠ Standard Planning
> WRONG: Create a standard execution plan inside `Meta-{Abbrev}/` with implementation tasks and a different abbreviation.
>
> CORRECT: Create a **discovery plan** inside `Meta-{Abbrev}/` with **reading and consolidation tasks** that produce Consolidated Context Parts. The abbreviation MUST match the parent project. The purpose is context discovery and consolidation — NOT implementation.

### Discovery Step 1: Gather Source Inventory

**CONFIRM block (per `references/scaffolding-hygiene.md` §1):**

Before gathering source inventory, output the Discovery context confirmation:

> [!template] Discovery Context Confirmation
> ```
> CONTEXT LOADED — DISCOVERY MODE
> Workflow: Discovery (Meta-Plan creation)
> Trigger: {indicator that triggered Discovery mode}
> Plugin references loaded: {list of loaded conditional refs}
> Next Action: Gather source inventory for {abbreviation}
> ```

<!-- AUTO-MODE: critical -->
Use `AskUserQuestion`: "Confirm Discovery mode for this plan?"
(Auto-default: proceed; user can switch to Standard or Scaffolding.)

Then proceed with the source inventory questions below.

<!-- AUTO-MODE: critical -->
<!-- All Discovery Step 1 questions (Project name, Abbreviation, Vision, Source files, Domains, Expected output) are CRITICAL per S03-03 audit table — no safe inference. -->
Use `AskUserQuestion` to collect:

**Question 1: Project Details**
- What is the project name? (e.g., "DataMigration", "UserAuthentication") — pre-fill from `$1` if provided
- What is the 2-4 character abbreviation? (e.g., "DM", "UA") — this abbreviation will be used across ALL three phases (Meta, Scaffold, Exec)
- Briefly describe the project vision (1-2 sentences)

**Question 2: Source Material**
- What source files/documents need to be read and consolidated? (paths, URLs, or descriptions)
- Are there specific domains or topics to organize findings by?
- What should the consolidated output contain? (e.g., schema definitions, API contracts, design decisions)

### Discovery Step 2: Validate and Design

1. **Validate abbreviation:** 2-4 characters, unique (check `{plans_dir}` for existing). Follow the [Abbreviation Validation Protocol](#abbreviation-length-validation) — never silently truncate or adjust
2. **Inventory source files:** List all source files with estimated line counts and token costs (~13 tokens/line)
3. **Confirm context exceeds 100K:** Sum total source tokens. If < 100K, recommend Standard plan instead
4. **Group sources by domain/topic:** Each group becomes a discovery sprint or session focus area
5. **Define expected Consolidated Context Parts:** One part per execution scope (each part ≤ 500 lines), with anticipated `Scope:` values

### Discovery Step 3: Create Folder Structure

Create the Meta-Plan structure under `{plans_dir}`:

```
{plans_dir}/{PlanName}/
└── Meta-{Abbrev}/
    ├── {Abbrev}-META-Master-Plan.md
    ├── Sprint-01-Discovery/
    │   ├── {Abbrev}-META-S01-Sprint-Plan.md
    │   └── Session-01-{SessionName}/
    │       ├── {Abbrev}-S01-01-Orchestration.md
    │       ├── {Abbrev}-S01-01-Recovery.md
    │       ├── {Abbrev}-S01-01-{##}-{Agent}-{Task}.md
    │       └── Outputs/
    └── Outputs/                                # Consolidated Context Parts go here
```

**Naming rules** (see [Meta-Plan File Naming](#meta-plan-file-naming) for full reference):
- Master Plan: `{Abbrev}-META-Master-Plan.md` (META infix distinguishes from Execution Plan)
- Sprint Plans: `{Abbrev}-META-S{XX}-Sprint-Plan.md` (META infix)
- Orchestration/Recovery: standard naming, no META infix (structural files)
- Task outputs: `{Abbrev}-META-S{XX}-{YY}-{TaskOutput}.md` (in session `Outputs/`)
- Consolidated outputs: `{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md` (in `Meta-{Abbrev}/Outputs/`)

### Discovery Step 4: Generate Meta-Plan Files

Use standard templates with the following overrides:

**Master Plan overrides:**
- Vision: "Context discovery and consolidation for {PlanName}" — NOT implementation
- Purpose: "Read source material, cross-reference findings, and produce Consolidated Context Parts"
- Success Criteria: Define what each Consolidated Context Part must contain
- List all source files/documents to be read (by reference, not loaded into the Master Plan)
- Expected output: Number and topics of Consolidated Context Parts

**Sprint Plan overrides:**
- Objective: "Gather and consolidate context for {domain/topic}" — NOT "implement"
- Sessions focused on reading and cross-referencing, not code generation

**Orchestration overrides:**
- Execution Strategy: **DELEGATED** (mandatory for META sessions — each agent needs fresh context to read sources)
- Context Boundary: Orchestrator reads plan files only; source material is read by task agents

**Task design rules:**
- Tasks are **reading and consolidation** tasks, not implementation tasks
- Each task reads a subset of source files and produces organized findings
- The **final task** in a session (or a dedicated consolidation session) combines findings into Consolidated Context Parts
- Agent assignments: Use **Opus** for cross-referencing and consolidation tasks (complex analysis); use **Sonnet** for straightforward reading tasks

### Discovery Step 5: Define Consolidation Tasks

The most critical part of the Discovery plan. The final task(s) must produce Consolidated Context Parts with this structure:

**Each Consolidated Context Part MUST have:**
- A header with `Scope:` field identifying which execution sprint it feeds
- A `What This Enables` section describing what downstream work this context supports
- Cross-references to other parts where topics overlap
- Full substantive detail — consolidation means organize and deduplicate, NOT summarize
- ≤ 500 lines per part; use multiple parts as needed

**Task file for a consolidation task should specify:**
- **Objective:** "Consolidate findings from {sources} into Consolidated Context Part(s) for {scope}"
- **Required Context:** The reading task outputs from earlier tasks in the session
- **Expected Output:** `Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md`
- **Success Criteria:** All source material covered, no substantive content lost, organized by execution scope

### Discovery Step 6: Validation

Standard checklist applies, plus:

```
[ ] Plan is inside Meta-{Abbrev}/ folder
[ ] Master Plan and Sprint Plans include META infix (e.g., {Abbrev}-META-Master-Plan.md)
[ ] Orchestration and Recovery files use standard naming (no META infix)
[ ] Abbreviation matches the project abbreviation (not a new one)
[ ] Master Plan purpose is "discovery and consolidation" (NOT implementation)
[ ] Tasks are reading/consolidation tasks (NOT implementation tasks)
[ ] Execution Strategy is DELEGATED
[ ] Final task(s) produce Consolidated Context Parts in Meta-{Abbrev}/Outputs/
[ ] Expected Consolidated Context Parts are defined with Scope values
[ ] Source files are listed by reference in Master Plan
[ ] Each Consolidated Context Part target is ≤ 500 lines
[ ] Plans index updated with new row
```

### Discovery Step 7: Output Confirmation

```
META-PLAN CREATED: {PlanName} (Discovery Phase)

**Abbreviation:** {ABBREV}
**Location:** {plans_dir}/{PlanName}/Meta-{Abbrev}/
**Phase:** 1 of 3 (Discovery → Scaffolding → Execution)

**Source Files:** {N} files (~{X}K total tokens)
**Expected Output:** {N} Consolidated Context Parts in Meta-{Abbrev}/Outputs/

**Files Created:**
- {Abbrev}-META-Master-Plan.md
- Sprint-01-Discovery/{Abbrev}-META-S01-Sprint-Plan.md
- Sprint-01-Discovery/Session-01-{Name}/{Abbrev}-S01-01-Orchestration.md
- Sprint-01-Discovery/Session-01-{Name}/{Abbrev}-S01-01-Recovery.md
- Sprint-01-Discovery/Session-01-{Name}/{Abbrev}-S01-01-{##}-{Agent}-{Task}.md (x{N} task files)
- Sprint-01-Discovery/Session-01-{Name}/Outputs/ (folder)
- Outputs/ (folder for Consolidated Context Parts)

**Next Steps:**
1. Review the Meta-Plan files
2. Execute Discovery sessions with `/planwise run`
3. After Discovery completes, scaffold the Execution Plan with `/planwise plan --scaffold`
```

After the confirmation, proceed to [Step 10: Plan Review Gate](#step-10-plan-review-gate).

---

## Scaffolding Workflow

**When:** A Meta-Plan Discovery phase produced Consolidated Context parts, and you need to create the Execution Plan from those parts.

**Input:** `Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md` files

### Scaffolding Step 1: Read Consolidated Context Parts

**CONFIRM block (per `references/scaffolding-hygiene.md` §1):**

Before reading Consolidated Context parts, output the Scaffolding context confirmation:

> [!template] Scaffolding Context Confirmation
> ```
> CONTEXT LOADED — SCAFFOLDING MODE
> Workflow: Scaffolding (Execution Plan from Discovery outputs)
> Source Meta-Plan: Meta-{Abbrev}/
> Plugin references loaded: {list of loaded conditional refs}
> Consolidated Context Parts detected: {list of part filenames}
> Next Action: Read all parts and design sprints from Scope: fields
> ```

<!-- AUTO-MODE: critical -->
Use `AskUserQuestion`: "Confirm Scaffolding mode for this plan?"
(Auto-default: proceed.)

Then proceed with the original steps below.

1. Find all `{Abbrev}-Consolidated-Context-Part-*.md` files in `Meta-{Abbrev}/Outputs/`
2. Read EVERY part completely -- each part's header has `Scope:` (the sprint it feeds) and a `What This Enables` section
3. Note: Part headers contain cross-references between parts
4. Read Tier 1 raw task outputs from `Meta-{Abbrev}/Sprint-XX-Discovery/Session-YY-*/Outputs/` and Tier 3 final consolidated layer (if produced). Tier 2 Consolidated Context Parts (above) are the primary input; Tier 1 + Tier 3 supply detail that Tier 2 shed. See Step 4.5 for the binding extraction rules.

### Scaffolding Step 2: Determine Plan Details

From the user's prompt or by asking:
- **Abbreviation:** Same as the Meta-Plan's abbreviation (e.g., `GCW`)
- **Root:** `{plans_dir}/{PlanName}/Exec-{Abbrev}/` (resolved from config.yaml)
- **Scaffold folder:** Always create `{plans_dir}/{PlanName}/Scaffold-{Abbrev}/` to maintain the three-phase convention (`Meta-{Abbrev}/`, `Scaffold-{Abbrev}/`, `Exec-{Abbrev}/`), even when scaffolding is done inline in the same session as planning
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

### Scaffolding Step 4.5: Multi-Tier Discovery Extraction

When extracting from Meta-Plan Discovery outputs, scaffolding agent MUST consume THREE tiers of source material — Tier 1 raw outputs carry detail that Tier 2/3 consolidated parts shed; skipping any tier is BLOCKER at `/planwise review`:

| Tier | Location | Content |
|------|----------|---------|
| **Tier 1** | `Meta-{Abbrev}/Sprint-XX-Discovery/Session-YY-*/Outputs/{Abbrev}-META-S{XX}-{YY}-{TaskOutput}*.md` | Raw task outputs (per-task detail) |
| **Tier 2** | `Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md` | Per-sprint consolidated context parts |
| **Tier 3** | `Meta-{Abbrev}/Outputs/{Abbrev}-Triage-*.md` or `*-Cross-Reference-*.md` (if produced) | Final consolidated layer |

**Extraction rules** (cross-reference `references/session-plan-requirements.md` §8 Multi-Tier extension):

1. The EI's `Extracted from:` header MUST list all three tiers when applicable.
2. Tier 1 raw outputs carry detail that Tier 2/3 consolidated parts shed; skipping Tier 1 is BLOCKER.
3. Every sprint's EI MUST include a **Deferred / Out-of-Scope Log** at `{Abbrev}-S{XX}-Deferred-OutOfScope-Log.md` enumerating:
   - Content from Tier 1/2/3 NOT extracted into this sprint's EI
   - Rationale for deferral (e.g., "covered by Sprint-03", "out of scope per Master Plan §X")
   - Target sprint or "Out of scope"

**Deferred / Out-of-Scope Log template:**

```markdown
# {Abbrev}-S{XX}-Deferred-OutOfScope-Log

**Sprint:** {XX} - {SprintName}
**Generated:** {ISO date during scaffolding}

## Deferred (covered elsewhere)

| Source | Tier | Content | Target |
|--------|------|---------|--------|
| {Spec #N (filename.md)} | T{1,2,3} | {1-line description} | {Sprint-YY \| Out of scope} |

## Out-of-Scope (no future coverage planned)

| Source | Tier | Content | Rationale |
|--------|------|---------|-----------|
| {Spec #N (filename.md)} | T{1,2,3} | {1-line description} | {why excluded} |
```

**Reviewer retention threshold** (enforced by `agents/plan-reviewer.md` Coverage Reviewer role):
- < 80 % retention → auto-reject
- 80 – 95 % retention → warn
- ≥ 95 % retention → pass

Retention = `(sum of EI section tokens + Deferred/OOS log tokens) / (sum of Tier 1+2+3 source tokens)`.

### Scaffolding Step 5: Generate Plan Files

Use the [scaffolding master plan template](../templates/scaffolding-master-plan.md) for the Master Plan.

Use standard templates for all other files (sprint plans, orchestrations, recovery, task files).

**Critical difference from standard planning:** Every task file's `Required Context` table MUST reference the sprint's **Execution Input** file (with section numbers), NOT the original Consolidated Context parts. The Execution Input replaces the parts for execution purposes.

**Status rule:** Set ALL Sprint Plan files to `**Status:** PLANNED`. Only the Master Plan gets `READY_TO_EXECUTE`. Do NOT copy the Master Plan's status into Sprint Plans — each Sprint Plan starts as PLANNED and transitions to IN_PROGRESS → COMPLETE during execution.

**`.gitkeep` emission (mirrors standard [Step 3](#step-3-create-folder-structure)):** For EVERY session folder created during scaffolding, write an empty `Outputs/.gitkeep` placeholder file inside the session's `Outputs/` directory. Empty directories are not tracked by git, so a missing `.gitkeep` means the `Outputs/` folder disappears on clone and downstream `/planwise run` cannot write summary or task-output files into the expected path. Apply to every sprint × every session — same per-session `.gitkeep` rule as the standard Step 3 constraint. Also populate each task file's Verification Commands per the [Step 8e per-file-type command map](#step-8e-populate-verification-commands-per-file-type-map) — scaffolded plans must NOT ship with blank verification placeholders any more than standard plans do.

> [!constraint] Agent Prompts Must Include Exact Headers
> Subagents start with fresh context (no inherited file reads). Saying "follow the template" forces a subagent to discover and read the template — an extra hop that may be skipped or interpreted loosely.
>
> WRONG: `"Follow the orchestration template to generate the orchestration file."`
>
> CORRECT: Include exact section headers and required formatting lines inline in the Task `prompt` parameter:
> ```
> "Generate the orchestration file with these exact section headers in order:
> ## Session Objective, ## Required Context Files, ## Execution Strategy,
> ## Session Task List, ## Success Criteria, ## Recovery Protocol,
> ## Task Files, ## Post-Session Checklist.
> Include the **Total Estimated:** line after the Session Task List table.
> Include the **Mode:** line in Execution Strategy."
> ```
>
> This applies to ALL file-generation agent prompts during scaffolding: sprint plans, orchestrations, task files.

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
[ ] If Discovery → Scaffolding: Multi-tier extraction tiers documented in EI header (Tier 1 + Tier 2 + Tier 3 where applicable)
[ ] If Discovery → Scaffolding: Deferred/Out-of-Scope Log present per sprint
[ ] If Discovery → Scaffolding: Retention threshold ≥ 80 % per EI section (auto-reject below)
[ ] If Discovery has user-action gates outside /planwise run: Master Plan Status is IN_PROGRESS with `awaiting {user action}` note (per `references/session-execution-protocol.md` Discovery / Meta-Plan Status section)
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

### Meta-Plan File Naming

Files inside `Meta-{Abbrev}/` insert `META` after the abbreviation to distinguish them from Execution Plan files with the same abbreviation. This follows the pattern shown in [session-planning-protocol.md](../references/session-planning-protocol.md#with-meta-plan--100k-context-needed).

| Type | Pattern | Example |
|------|---------|---------|
| META Master Plan | `{Abbrev}-META-Master-Plan.md` | `PI-META-Master-Plan.md` |
| META Sprint Plan | `{Abbrev}-META-S{XX}-Sprint-Plan.md` | `PI-META-S01-Sprint-Plan.md` |
| META Task Output | `{Abbrev}-META-S{XX}-{YY}-{TaskOutput}.md` | `PI-META-S01-01-SourceAnalysis.md` |
| Consolidated Context Part | `{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md` | `PI-Consolidated-Context-Part-1-Schema.md` |

Orchestration and Recovery files inside `Meta-{Abbrev}/` use the standard naming pattern (no META infix) — they are structural files, not discovery artifacts.

### Task Number Convention

- `{##}` = Two-digit task number (01, 02, 03...)
- Task numbers match the `#` column in the Orchestration task list
- One file per task -- NEVER combine multiple tasks into one file

---

## Token Budget Rules

### Session Limits

**Available for work:** scales by tier. On Pro: ~100K. On Max: ~900K (with a 400K practical session cap). See `references/session-context-budget.md` §5 Tier-Specific Budget Table.

The pattern thresholds below are expressed for the Pro tier (the backward-compatible default). On Max, multiply by `available_for_work / 100_000` and cap "Too Large" at `meta_plan_threshold` (500K, not 9×).

| Pattern | Initial Load (Pro) | Growth | Total (Pro) | Guideline |
|---------|--------------------|--------|-------------|-----------|
| Discovery | < 30K | +40-50K | ~70-80K | Don't know files upfront |
| Planned | 30-70K | +10-20K | ~80-90K | Know most files upfront |
| Front-loaded | 70-90K | +5-10K | ~95-100K | Know all files upfront |
| **Too Large** | > `meta_plan_threshold` | - | - | **MUST use Meta-Plan** |

### Task Sizing Categories

The task-size thresholds below are expressed for the Pro tier. On Max, scale by the same ratio used for session limits — a "Too Large" task on Pro is ~80% of `practical_session_limit`. The "always split a task above 80% of one session" principle is tier-invariant.

| Task Size | Token Estimate (Pro) | Guideline |
|-----------|---------------------|-----------|
| Small | < 20K | Single file, simple lookup |
| Medium | 20-50K | Multi-file, code generation |
| Large | 50-80K | Complex analysis, multiple entities |
| Too Large | > 80K (Pro) / > 320K (Max practical) | **MUST SPLIT** |

**These categories are a cross-check, not the primary estimate.** Always compute the bottom-up estimate first, then compare against the category. Use the HIGHER of the two.

**Note:** Session limits apply to DIRECT mode in the main conversation. In DELEGATED mode, each task-runner subagent gets a fresh context budget at the parent's tier. Verify: `(task estimate + 54K overhead) < context_window` per subagent (200K on Pro, 1M on Max).

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
DELEGATED check: Task Estimate + 54K overhead < context_window per subagent
                 (read from config.yaml: context.context_window — defaults to 200000)
```

Subagents inherit the parent session's tier. On Pro, `context_window = 200000`; on Max, `1000000`. See `references/session-context-budget.md` §5 Threshold Formulas.

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
