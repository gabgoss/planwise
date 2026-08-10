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
- [Naming Conventions](#naming-conventions)
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

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

**Plan-specific references (always load):**
1. Read `references/session-planning-protocol.md`
2. Read `references/session-plan-requirements.md`
3. Read `references/session-context-budget.md`
4. Read `references/session-execution-protocol.md` — source for session invariants
5. Read `references/read-confirm-act-protocol.md` — source for READ-CONFIRM-ACT, the structural-findings gate, and the post-step checklist (cited in this handler's checklists)

**Conditional references:**
- If the plan creates or modifies agents: Read `references/agent-authoring.md`
- If the plan creates or modifies skills: Read `references/skill-authoring.md`
- If the plan creates or modifies rules: Read `references/rule-authoring.md`
- If planning a scaffolded multi-sprint plan (Discovery → Scaffolding workflow): Read `references/ei-fidelity.md`, `references/task-content-fidelity.md`, `references/discovery-and-exit-criteria.md`, `references/scaffolding-hygiene.md`
- If the plan contains verification tasks (grep/awk match-pattern + pass/fail gate): Read `references/verification-task-authoring.md`
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

**Explicit indicators** (go directly to Discovery mode):

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

- If user chooses **Discovery** → Read `handlers/plan-discovery.md` and follow it
- If user chooses **Scaffolding** → Read `handlers/plan-scaffolding.md` and follow it
- If user chooses **Standard** → proceed to Step 1

**If Discovery Mode (explicit):** Read `handlers/plan-discovery.md` and follow it instead of Steps 1-9.

#### Scaffolding Mode (Execution Plan from Discovery Outputs)

**Explicit indicators** (go directly to Scaffolding mode):

| Indicator | Action |
|-----------|--------|
| `--scaffold` flag present in arguments | **Scaffolding** |
| User says "scaffold", "scaffolding phase", or "from Discovery" | **Scaffolding** |

**If Scaffolding Mode (explicit):** Read `handlers/plan-scaffolding.md` and follow it instead of Steps 1-9.

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
> The `--scaffold-per-sprint` flag is an **in-conversation pause-and-confirm** mechanism — it does NOT create per-Exec-sprint `Scaffold-{Abbrev}-S{XX}/` sessions with their own Orchestration/Recovery files (a compaction-resume capability considered during design). The simpler pause-only mechanism shipped intentionally as a documented design decision: the full per-sprint Scaffold-session resume mechanism is treated as a new feature, deliberately out of scope for the current contract. Future maintainers — do NOT treat the absence of per-sprint Scaffold sessions as a regression; it is the documented design. If compaction during multi-sprint scaffolding becomes a real problem, file a NEW backlog item (do not silently expand this flag's contract).

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

- If user chooses **Scaffolding** → Read `handlers/plan-scaffolding.md` and follow it
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

**Shared-context pre-pass (measure once, fan out):** Before computing per-task estimates, build the set of files cited in the Required Context of **two or more** tasks (group Required Context rows by file path across the whole session). For each such shared file, measure it **ONCE** — `wc -l` on the live file — and convert to tokens once; then write the **IDENTICAL** `Est. Lines` / `Est. Tokens` values into every citing task's row. A multiply-cited file's size is a single source of truth, never a per-task guess — otherwise one estimation error replicates silently into every citing task's Context subtotal and header `Estimated Tokens`. If a shared doc is edited during authoring, re-measure it and re-fan the new value into all citing rows, then re-roll the affected subtotals, headers, and session totals. The drift is direction-agnostic: an over-estimate merely inflates budgets, but an under-estimate can mis-route a file in the Token Saver Large-File Scan below or under-budget a DELEGATED dispatch.

For each task in the session, compute a bottom-up token estimate:

1. **Measure Required Context files:** For each file in the task's Required Context table, estimate line count (check actual size with Glob/Read or use domain heuristics)
2. **Convert to tokens:** Apply ~13 tokens/line (see [Per-Operation Cost Reference](../references/session-context-budget.md#per-operation-cost-reference))
3. **Add output cost:** Estimate output generation tokens from the operation-level table
4. **Compare:** If the bottom-up estimate exceeds the qualitative category estimate, use the higher number
5. **DELEGATED check:** For DELEGATED tasks, verify `(task estimate + injected path-rule tokens + 54K overhead) < the dispatched model's window` per subagent. A subagent's window is set by its **dispatched model** (Sonnet/Haiku 200K, Opus 1M), NOT the parent tier — a Sonnet runner is 200K even when the orchestrator is on Max. See `references/session-context-budget.md` [§ Subagent Context Window](../references/session-context-budget.md#subagent-context-window).

Update the task's `Estimated Tokens` field and the Orchestration Session Task List with the validated estimates.

#### Token Saver Large-File Scan (gated on the **effective** Token Saver value)

Resolve the **effective** Token Saver value for THIS plan ONCE here — it gates the entire scan, and the resulting flags (`1M-exception`, etc.) are baked into the task files so the spawned runner never re-resolves. Read the plan's Master-Plan `Token Saver:` field (`on`→True, `off`→False, `inherit`/absent→None), then call `config_loader.get_effective_token_saver_config(config, plan_override)` — the per-plan override wins over the project `context.token_saver` default; the project key is the fallback. The measured overheads (`token_saver_runner_overhead`, `token_saver_session_target`, etc.) are ALWAYS project-level and never overridden per-plan.

When the effective `token_saver` is `true`, after the bottom-up estimate above, run a per-file large-file scan over **every** Required Context file in **every** task. This is the plan-author-time instance of the per-file warning ladder anchored in `references/task-content-fidelity.md` §9.A.8 (levels, formulas, and the `reason=cost|read` contract live there — read it before authoring the scan output). The scan folds the carrying-cost ladder and the two FIXED Read-tool gates into one verdict, so it also catches files that are unreadable in a single Read — including files a task will push past a gate once it edits them.

1. **Derive the cost thresholds** from the measured overhead (never hardcode):

   ```
   thresholds = token_saver.derive_thresholds(
       session_target = context.token_saver_session_target,   # default 150000
       runner_overhead = context.token_saver_runner_overhead)  # measured by /planwise calibrate
   # → {available_per_task, critical, warn}
   ```

2. **Classify each Required Context file** against the runner that will read it (the task's assigned **Agent** — Haiku/Sonnet 13 tok/line, Opus 19; the byte cap is model-independent). For a file the **same task will modify**, pass the projected output delta so a file that *will* cross a gate post-edit is flagged pre-emptively:

   ```
   verdict = token_saver.classify_file(
       path,
       model = <task's Agent, lowercased>,
       projected_added_lines = <lines this task adds to this file, else 0>,
       thresholds = thresholds)
   # → {level, reason, bytes, tokens}; level = max(cost_level, read_level)
   ```

3. **Emit a recommendation block per file** at **Notice / Warn / Critical** (Green files are silent), naming the driving `reason`:
   - **Notice** — advisory only. Docs/specs → note a Multi-Part split is advisable; code → note for awareness. No backlog item.
   - **Warn** (`reason=cost` ≥ `warn`, or `reason=read` ≥ 240 KiB / ≥ 22K model-tok) — recommend the remedy by file type (below) **and file a backlog item** via the consumer project's backlog mechanism (`handlers/backlog.md` Phase 7 create flow — generic, no project identifiers).
   - **Critical / `reason=cost`** (≥ `critical`) — warn + file a backlog item + flag the task **`1M-exception`** (dispatch on Opus / 1M) so the plan still completes; the file won't fit a lean task even alone.
   - **Critical / `reason=read`** (≥ 256 KiB byte cap OR ≥ 25K model-tok page cap) — warn + file a backlog item + recommend a **paged read** (`offset`/`limit`/Grep) for read-only context, or **refactor/split + backlog item** for a core or to-be-edited dependency. Do **NOT** flag `1M-exception`: the 1M window does not raise the per-Read page cap, and Opus's tokenizer (19 tok/line) trips it *sooner* than Sonnet/Haiku.
   - The scan is **never a hard stop** — a source-file Critical advises and files an item; it does not abort planning.

4. **Differentiate the remedy by file type** in the recommendation:
   - **Code** → refactor into smaller modules.
   - **Doc / spec / Execution Input** → Multi-Part split (existing [Multi-Part Output Convention](../references/session-context-budget.md#file-size-limits)).
   - **Dense (notebook / minified / compressed JSON)** → measure precisely (`wc -c` alongside `wc -l`) and extract only the needed sections.

5. **Generated artifacts the plan itself authors** that a runner MUST read — task files, Orchestration, Recovery, Consolidated Context parts, Execution Inputs, task Output files — carry a **HARD** read-gate ceiling (MUST Multi-Part split to stay readable), NOT advisory, per `references/session-context-budget.md` [§ File Size Limits — Generated Artifacts](../references/session-context-budget.md#file-size-limits--generated-artifacts-binding-when-token-saver-is-on). External source files the runner reads but does not generate stay advisory (warn + backlog + read tactics).

> [!constraint] Read-Reason Critical Is NOT `1M-Exception`-Resolvable
> WRONG — a Required Context file scans Critical with `reason=read`; the planner flags the task `1M-exception` and dispatches it to Opus, expecting the 1M window to absorb the file:
> ```
> # 280 KiB external doc → classify_file → {level: Critical, reason: read}
> Task flagged: 1M-exception   ← WRONG: the per-Read page cap is unchanged by the window,
>                                and Opus (19 tok/line) trips the token gate SOONER than Sonnet
> ```
> CORRECT — `reason=read` Critical recommends a paged read / refactor and files a backlog item; only `reason=cost` Critical earns `1M-exception`:
> ```
> # reason=read  → paged read (offset/limit/Grep) for read-only; refactor+backlog for a to-be-edited dep
> # reason=cost  → flag 1M-exception (Opus/1M); plan still completes
> ```

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
Verification Commands as a finding (`references/task-file-and-tracking-requirements.md` §Verification
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
> `Verification Commands Plan-Review Enforcement` table in `task-file-and-tracking-requirements.md`).

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
[ ] If effective Token Saver on (plan Master-Plan `Token Saver:` field over the project `context.token_saver` default) — Token Saver large-file scan run over every task's Required Context (Step 8c); Warn+ files have a backlog item; cost-reason Critical tasks flagged 1M-exception (read-reason → paged-read/refactor, never 1M-exception); generated artifacts a runner reads are under the line/byte/token read gates
[ ] If Discovery → Scaffolding: Multi-tier extraction tiers documented in EI header (Tier 1 + Tier 2 + Tier 3 where applicable)
[ ] If Discovery → Scaffolding: Deferred/Out-of-Scope Log present per sprint
[ ] If Discovery → Scaffolding: Retention threshold ≥ 80 % per EI section (auto-reject below)
[ ] If Discovery has user-action gates outside /planwise run: Master Plan Status is IN_PROGRESS with `awaiting {user action}` note (per `references/session-execution-protocol.md` Discovery / Meta-Plan Status section)
[ ] Scope favors the coherent treatment — no known-partial fix is planned without a recorded constraint and a named residual defect (see the callout below)
```

> [!practice] Plan the Right Fix, Not the Easy Fix
> When scoping reveals two treatments — a complete one that touches more surface (a full renumber, a schema migration, propagating a change through every consumer) and a narrower patch that leaves known incoherence behind — scope the complete treatment and cost it honestly. Budget pressure is answered by SPLITTING the coherent fix across tasks or sessions (see `references/session-context-budget.md` § Task-Level Estimation / Task Sizing Categories), never by shrinking it into a partial fix that is cheaper to execute. If a real constraint genuinely forces the partial path (an interface external consumers depend on, an irreversible boundary, a user-set deadline), record the constraint and the residual defect in the plan so the gap is a visible decision, not an accident. Overall project quality comes from doing the hard thing once, not the easy thing twice. Full principle, exception clause, and stage table: [do-the-hard-things.md](../references/do-the-hard-things.md).

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

## Additional Resources

- [session-planning-protocol.md](../references/session-planning-protocol.md) -- Detailed protocol: plan hierarchy, naming conventions, agent delegation, recovery, checklists, git workflow, READ-CONFIRM-ACT
- [templates/](../templates/) -- All plan templates (including scaffolding master plan)
- [examples/sample-plan-output.md](../examples/sample-plan-output.md) -- Example standard plan
- [examples/sample-scaffolding-output.md](../examples/sample-scaffolding-output.md) -- Example scaffolding from Discovery
- [plan-discovery.md](plan-discovery.md) -- Discovery Workflow (Meta-Plan creation); loaded by Step 0 when Discovery mode is detected
- [plan-scaffolding.md](plan-scaffolding.md) -- Scaffolding Workflow (Execution Plan from Discovery outputs); loaded by Step 0 when Scaffolding mode is detected
