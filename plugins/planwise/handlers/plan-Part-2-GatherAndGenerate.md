# Handler: /planwise plan — Part 2: Gather and Generate

**Part 2 of 3.** This handler spans three files, split by step range because the combined text exceeds the Read-tool page cap. Each step keeps its own identifier wherever it lands, so an existing `Step N` reference still names exactly one section — only the filename that holds it changes. See [`plan.md`](plan.md) for the full three-part pointer table, the Config Gate, the Required References, the index-shape gate and Step 0. [`plan-Part-3-VerifyConfirmAndReview.md`](plan-Part-3-VerifyConfirmAndReview.md) covers Steps 8d-10, the Validation Checklist and Deferred Authoring.

This file covers **Steps 1-8c**: gather and validate the plan details, create the folder structure, generate the plan files and task files, and validate the token estimates.

---

## Workflow (continued)

### Step 1: Gather Information

Parse `$1` for the plan name. If `$1` is empty, use `AskUserQuestion` to collect it.

<!-- AUTO-MODE: critical -->
Use `AskUserQuestion` to collect:

**Question 1: Plan Details**
- What is the name of your plan? (e.g., "UserAuthentication", "DataMigration") — pre-fill from `$1` if provided
- What is the 2-4 character abbreviation? (e.g., "UA", "DM")
- Briefly describe the vision (1-2 sentences)
- Which backlog item(s) does this plan resolve, if any? (item ids, or "none")

**Question 2: Scope**
- How many sprints do you anticipate? (1-5)
- For EACH sprint in that count, what is its name and purpose? (e.g., "Sprint 1: CoreAuth — login and registration; Sprint 2: AdvancedAuth — SSO and MFA")
- For EACH sprint, how many sessions does it need, and what is each session's name? (default: 1 session per sprint)

**Bind the answers before leaving this step.** Later steps consume them by name, so record them explicitly rather than leaving the count in the conversation:

| Bound value | From | Consumed by |
|-------------|------|-------------|
| `{sprint_count}` | the sprint count above | Step 3 (folder tree), Steps 5-7 (per-sprint cardinality), the Validation Checklist |
| `{sprint_names[XX]}` | each sprint's name | Step 3, Step 4's Sprint Overview table |
| `{session_count[XX]}` | sessions in sprint `{XX}` | Step 3, Steps 6-8 (per-session cardinality), the Validation Checklist |
| `{session_names[XX][YY]}` | each session's name | Step 3, Step 9's confirmation block |
| `{resolves}` | the backlog item ids above, or `none` | Step 4's Master Plan `**Resolves:**` header field and its Project Complete When criterion — `/planwise run` closeout closes these items when the plan reaches COMPLETE |

Under Auto Mode, or when the answer is empty, bind `{resolves}` to `none` unless the invoking context names an item. A `/planwise backlog` Route C dispatch always names one.

**Every sprint AND every session named here gets fully scaffolded in this pass** (Steps 3-9 below) — this handler does not stop after Sprint 1, and it does not stop after each sprint's Session-01. `sum({session_count[XX]})` over all sprints is the number of Orchestration files this pass must produce.

If some sprints are deliberately left unauthored, that is legitimate but MUST be declared — see [Deferred Authoring](plan-Part-3-VerifyConfirmAndReview.md#deferred-authoring) before proceeding.

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

On the default path of [Steps 4-7](#steps-4-7-generate-files), `scaffold_plan.py render` creates this whole tree, so create no folder here and go to Steps 4-7. On the fallback path, create the following structure under the configured `{plans_dir}`. **Two nested loops, both bound in Step 1:** repeat the `Sprint-{XX}-{SprintName}/` block for every sprint (`{XX}` = `01` … `{sprint_count}`), and inside each one repeat the `Session-{YY}-{SessionName}/` block for every session of that sprint (`{YY}` = `01` … `{session_count[XX]}`). Do not stop after the first sprint, and do not stop after each sprint's first session.

```
{plans_dir}/{PlanName}/
├── {Abbrev}-Master-Plan.md
└── Sprint-{XX}-{sprint_names[XX]}/                    # for XX = 01 … {sprint_count}
    ├── {Abbrev}-S{XX}-Sprint-Plan.md                  # one per sprint
    └── Session-{YY}-{session_names[XX][YY]}/          # for YY = 01 … {session_count[XX]}
        ├── {Abbrev}-S{XX}-{YY}-Orchestration.md       # one per SESSION
        ├── {Abbrev}-S{XX}-{YY}-Recovery.md            # one per SESSION
        ├── {Abbrev}-S{XX}-{YY}-{##}-{Agent}-{Task}.md # one per task in that session
        └── Outputs/
            └── .gitkeep                               # Required so Outputs/ is tracked by git
```

Worked example — 2 sprints, the second with 2 sessions (`{sprint_count}` = 2, `{session_count}` = `[1, 2]`, so 3 Orchestrations):

```
{plans_dir}/{PlanName}/
├── {Abbrev}-Master-Plan.md
├── Sprint-01-{Sprint1Name}/
│   ├── {Abbrev}-S01-Sprint-Plan.md
│   └── Session-01-{Name}/  → {Abbrev}-S01-01-Orchestration.md, -Recovery.md, task files, Outputs/.gitkeep
└── Sprint-02-{Sprint2Name}/
    ├── {Abbrev}-S02-Sprint-Plan.md
    ├── Session-01-{Name}/  → {Abbrev}-S02-01-Orchestration.md, -Recovery.md, task files, Outputs/.gitkeep
    └── Session-02-{Name}/  → {Abbrev}-S02-02-Orchestration.md, -Recovery.md, task files, Outputs/.gitkeep
```

**Every sprint AND every session bound in Step 1 gets its own folder here.** A plan with 3 sprints creates `Sprint-01/`, `Sprint-02/` and `Sprint-03/` in this same pass; a sprint declaring 4 sessions creates `Session-01/` through `Session-04/` inside it. `{YY}` is a loop variable, not the literal `01`.

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

**Default path: one spec Write, one script render.** The index-shape gate in the router's `## Workflow` has already run, so every write below sits behind it. One metadata-only spec and one `scaffold_plan.py` render produce every file of Steps 3-8. The model then writes only the prose bodies:

1. Run Step 8's lessons search first, so its hits reach the spec's Required Context rows or the task bodies.
2. `Write` ONE spec JSON, outside `{plans_dir}/{PlanName}/`, holding the plan, sprint, session and task metadata bound in Steps 1-2. The spec names no heading, because the templates carry every heading. Its fields are defined once, in the module docstring of `scaffold_plan.py` (section "Spec format").
3. Write each Required Context row as a typed row. `kind` `"path"` (the default) takes `priority`, `path`, `kib`, `tokens_k` and `purpose`. `kind` `"span"` takes the same fields plus `span` (for example `"lines 1-80"`). `kind` `"command"` takes `priority`, `command`, `lines`, `bytes`, `kib`, `tokens_k` and `purpose`, and no `path`. Write a command-corpus row or a span row in its typed form in the spec. Never hand-fill one into the rendered table afterwards. The renderer writes a resolution record line beneath the table for each span or command row.
4. Run `python -B "{plugin_root}/scripts/scaffold_plan.py" lint-spec --spec {spec}`. Exit 0 prints `lint=clean`. Exit 1 prints one `LINT:` line per error, quoting the row or key: fix the spec and re-run. A prose `path`, an unknown key and a malformed typed row are lint errors.
5. Run `python -B "{plugin_root}/scripts/scaffold_plan.py" render --spec {spec} --out {plans_dir}/{PlanName}`. It refuses an `--out` folder that is not empty, so do not pre-create the Step 3 tree. It writes the Master Plan, every Sprint Plan, every Orchestration and Recovery pair, every task file with its Task Files table row, and every `Outputs/.gitkeep`, then prints `rendered <n> files to <out>; fill_markers=<k>; surviving_placeholders=<m>`.
6. Replace every `<!-- FILL: {name} -->` marker with model-written text. The script writes metadata and derived tables only, and every body stays model-written.

**Fallback: the per-template steps.** When `scaffold_plan.py` is absent, or `render` exits non-zero (1: a placeholder survived outside a FILL marker; 2: refused), generate the files with the table below and Step 8's task-file steps. An exit 1 has already written the tree, so write each fallback file over its rendered copy.

Use templates from `{plugin_root}/templates/`:

| Step | Template | Output File | Cardinality |
|------|----------|-------------|-------------|
| 4 | [master-plan.md](../templates/master-plan.md) | `{Abbrev}-Master-Plan.md` | Once — Sprint Overview lists **all** `{sprint_count}` sprints; **Total Sessions** equals `sum({session_count[XX]})` |
| 5 | [sprint-plan.md](../templates/sprint-plan.md) | `{Abbrev}-S{XX}-Sprint-Plan.md` | **Once per sprint** (`{XX}` = `01` … `{sprint_count}`) — its Sessions table lists all `{session_count[XX]}` sessions |
| 6 | [orchestration.md](../templates/orchestration.md) | `{Abbrev}-S{XX}-{YY}-Orchestration.md` | **Once per SESSION** (`{YY}` = `01` … `{session_count[XX]}`, for every sprint) |
| 7 | [recovery.md](../templates/recovery.md) | `{Abbrev}-S{XX}-{YY}-Recovery.md` | **Once per SESSION** |

Step 5 repeats for every sprint; Steps 6-7 repeat for every session of every sprint. Their cardinality is **not** the sprint count — a 3-sprint plan whose second sprint has 3 sessions produces 3 Sprint Plans and **5** Orchestration/Recovery pairs. Do not stop after Sprint-01, and do not stop after each sprint's Session-01.

**A section no template heading covers goes under `## Plan-Specific Sections`, as an `###` H3.** Never add it as a new H2. The catch-all is the last H2 of every plan template, and the render omits it unless the document's `optional_sections` list in the spec names `"Plan-Specific Sections"`. When the need appears after the render, add the heading from the template by hand. For each new H3 heading text, draft one `idea` through `mcp__planwise__draft_feedback`, as [`references/feedback-drafting.md`](../references/feedback-drafting.md) § Triggers describes. With `feedback.drafts` set to `off`, write no draft.

After rendering and filling (or after the fallback writes), run `python -B "{plugin_root}/scripts/scaffold_plan.py" check-headings {plans_dir}/{PlanName}`. Exit 1 lists each stray H2. Move each one under the catch-all as an H3 before Step 9.

### Step 8: Generate Task Files

**Steps 8 through 8e repeat for EVERY Orchestration file created in Step 6 — every session of every sprint, not one per sprint.** Finish one session's task files before moving to the next, and one sprint's sessions before moving to the next sprint. Step 8d (Update Plans Index) is the one exception: it runs once, after every sprint has been scaffolded.

**Search the lessons index for the artifact classes this plan will touch, before authoring task files.**

A plan that will author schema definitions, verification greps, generated notebooks, module docstrings, or any other recurring artifact class should search the lessons index for each class before writing task files, and cite the hits inline in the Required Context or Verification Commands of the tasks that touch them:

```bash
grep -rliE "{artifact_class_keyword}" {lessons_dir}/**/LL-*.md
```

Capture is a store, not a channel — a lesson reaches a runner only when it is cited in the artifact that runner actually reads (a task file's Required Context, its Verification Commands, or a coordination-flag block).

A lesson sitting correctly indexed and uncited is delivered to nobody.

The payoff scales with repetition: a plan that repeats one task chain across several sprints misses the same lesson once per repetition unless it is cited.

**CRITICAL:** Create ONE task file per task in the Orchestration task list.

On the default path of Steps 4-7, `render` has already written one task file per task and its Task Files table row, so fill each task file's FILL markers. The steps below are the fallback.

For each task, create a file using the [task-file.md](../templates/task-file.md) template.

**File name pattern:** `{Abbrev}-S{XX}-{YY}-{##}-{Agent}-{TaskName}.md` (`{XX}` = the sprint being processed, `{YY}` = the session being processed — both loop variables, neither a literal `01`)

After creating task files, update the Orchestration file's Task Files table with links.

> [!constraint] Repair a Generated File With One Whole-File Write
> WRONG — a file needs several repairs after the fill, a lint or a scan, and each repair is its own `Edit`:
> ```
> Edit {Abbrev}-Master-Plan.md  … Edit {Abbrev}-Master-Plan.md   # one tool use per repair
> ```
> CORRECT — read the file once, then `Write` the whole corrected file once:
> ```
> Read {Abbrev}-Master-Plan.md → Write {Abbrev}-Master-Plan.md   # all repairs in one write
> ```
> Never apply the whole-file Write to a file listed under a Sprint Plan's `## Cross-Sprint File Touches`, because a whole-file write discards a co-writer's change. Repair that file with targeted `Edit` calls. The rule's acceptance counts two figures, each with its basis: repair tool uses (each `Edit` or `Write` call) and distinct requests (each model response, which can carry several tool calls). Several `Edit` calls can share one request, so a whole-file Write can save tool uses and no requests.

### Step 8b: Add Lessons Reference to Post-Session Checklist

Each Orchestration file created MUST include this item in its post-session checklist:

```
[ ] Document lessons learned in {lessons_dir}/LL-{NNN}-{Domain}-{Name}.md
    - Get next NNN from `parse_lessons.py --config {config} --next-id`
    - Use the lesson file template from templates/lesson.md
    - Required frontmatter: id, title, date, source (session ID), category, severity,
      language, technology, domain, status, applied-as
    - Run the generator; append the changelog entry
```

Where `{lessons_dir}` comes from `config.yaml`.

### Step 8c: Validate Token Estimates (Bottom-Up)

**Shared-context pre-pass (measure once, fan out):** Before computing per-task estimates, build the set of files cited in the Required Context of **two or more** tasks (group Required Context rows by file path across the whole session). For each such shared file, measure it **ONCE** — `measure_files.py` on the live file — and record its KiB and tokens once; then write the **IDENTICAL** `KiB` / `~Tokens` values into every citing task's row. A multiply-cited file's size is a single source of truth, never a per-task guess — otherwise one estimation error replicates silently into every citing task's Context subtotal and header `Estimated Tokens`. If a shared doc is edited during authoring, re-measure it and re-fan the new value into all citing rows, then re-roll the affected subtotals, headers, and session totals. The drift is direction-agnostic: an over-estimate merely inflates budgets, but an under-estimate can mis-route a file in the Token Saver Large-File Scan below or under-budget a DELEGATED dispatch.

**Default path: the scan writes the estimates.** After the session's task files are filled, run once per session, from the project root, naming every task file of the session with its own `--task`:

```bash
python "{plugin_root}/scripts/token_saver.py" --scan --plan {plan_path} --write-estimates --task {task file} [--task {task file} ...]
```

The scan owns the content-class decision: it prices each row from the live file under the class its suffix gives, so a code file prices at the code ratio. It writes each resolvable row's `KiB` and `~Tokens` cells, every task's Context subtotal and `Estimated Tokens` header, the Orchestration Session Task List cell and `**Total Estimated:**`, and the Sprint Plan Sessions row. It prices every citing row from the same file, so the shared-context pre-pass above holds by construction. It leaves command-corpus, plan-output, missing, prose and qualified rows as authored, and reports each one. `--dry-run` prints the changes and writes nothing. Exit 0 is success with or without changes. Exit 2 is a usage error (no `--task` refuses, as does a `--task` outside `{plan_path}`). Exit 3 is a failed write. This mode computes no Warn levels, so the Token Saver Large-File Scan below still runs. Then apply items 2-5 below to the written figures.

**Fallback: the per-task measure loop.** When the script is absent or exits non-zero, measure with the steps below. For a row the scan left as authored, measure only that row with item 1.

For each task in the session, compute a bottom-up token estimate:

1. **Measure Required Context files:** Run `python "{plugin_root}/scripts/measure_files.py" {files...} --model {task's Agent} --md` over every file in the task's Required Context table — it reports each file's KiB and measured tokens and emits ready-to-paste table rows. Add `--content code` for a code file, so its price matches the scan's code class
2. **Convert to tokens:** For files that do not exist yet, estimate byte size ÷ the reading model's bytes-per-token ratio (≈3.0 prose/code, ≈2.6 dense markdown; see [Per-Operation Cost Reference](../references/session-context-budget.md#per-operation-cost-reference)) — never lines × a rate
3. **Add output cost:** Estimate output generation tokens from the operation-level table
4. **Compare:** If the bottom-up estimate exceeds the qualitative category estimate, use the higher number
5. **DELEGATED check:** For DELEGATED tasks, verify `(task estimate + injected path-rule tokens + 54K overhead) < the dispatched model's window` per subagent. A subagent's window is set by its **dispatched model** (Sonnet/Haiku 200K, Opus 1M), NOT the parent tier — a Sonnet runner is 200K even when the orchestrator is on Max. See `references/session-context-budget.md` [§ Subagent Context Window](../references/session-context-budget.md#subagent-context-window).

On the fallback path, update the task's `Estimated Tokens` field and the Orchestration Session Task List with the validated estimates. On the default path, the scan wrote them, so edit a figure only where items 3-5 raise it.

#### Token Saver Large-File Scan (gated on the **effective** Token Saver value)

Resolve the **effective** Token Saver value for THIS plan ONCE here — it gates the entire scan, and the resulting flags (`1M-exception`, etc.) are baked into the task files so the spawned runner never re-resolves. Read the plan's Master-Plan `Token Saver:` field (`on`→True, `off`→False, `inherit`/absent→None), then call `config_loader.get_effective_token_saver_config(config, plan_override)` — the per-plan override wins over the project `context.token_saver` default; the project key is the fallback. The measured overheads (`token_saver_runner_overhead`, `token_saver_session_target`, etc.) are ALWAYS project-level and never overridden per-plan.

When the effective `token_saver` is `true`, after the bottom-up estimate above, run a per-file large-file scan over **every** Required Context file in **every** task. This is the plan-author-time instance of the per-file warning ladder anchored in `references/task-content-fidelity.md` §9.A.8 (levels, formulas, and the `reason=cost|read` contract live there — read it before authoring the scan output). The scan folds the carrying-cost ladder and the two FIXED Read-tool gates into one verdict, so it also catches files that are unreadable in a single Read — including files a task will push past a gate once it edits them.

**Run the scan — do not hand-annotate it.** The scan is a shipped tool, not a procedure to reproduce by judgement:

```bash
python "{plugin_root}/scripts/token_saver.py" --scan --plan {plan_path} --config {config} [--json]
```

It walks every task file under `{plan_path}`, reads each task's assigned **Agent**, resolves every Required Context row to a path, classifies it, prints one recommendation block per Warn-or-worse file with the citing tasks, prints the backlog filing worklist, and **exits non-zero when any file lands Warn or worse**. Add `--projected {path}={bytes}` for a file this plan will grow. Rows that are not files — a command corpus, a not-yet-written output, a glob — are reported by reason rather than classified.

Run it rather than reproducing it by judgement. Why a *correct* hand-written annotation is the worst case, with the WRONG/CORRECT pair, is [`references/task-content-fidelity.md`](../references/task-content-fidelity.md) §9.A.15.

The contract the tool implements, for reference when reading its output:

1. **Cost thresholds** are derived from the measured overhead, never hardcoded:

   ```
   thresholds = token_saver.derive_thresholds(
       session_target = context.token_saver_session_target,   # default 150000
       runner_overhead = context.token_saver_runner_overhead)  # measured by /planwise calibrate
   # → {available_per_task, critical, warn}
   ```

2. **Each Required Context file is classified** against the runner that will read it (the task's assigned **Agent** — tokens = bytes ÷ that model family's bytes-per-token ratio; the byte cap and line window are model-independent). For a file the **same task will modify**, the projected byte delta (projected added lines × the file's observed average bytes/line) is passed so a file that *will* cross a gate post-edit is flagged pre-emptively:

   ```
   verdict = token_saver.classify_file(
       path,
       model = <task's Agent, lowercased>,
       projected_added_bytes = <bytes this task adds to this file, else 0>,
       thresholds = thresholds)
   # → {level, reason, bytes, tokens, lines}; level = max(cost_level, read_level)
   ```

   Token figures come from **bytes ÷ the reading model's ratio**. Never derive one from a line count: measured per-line rates range 7–365 tokens/line by content, so a per-line band under-reports exactly the dense index files this scan exists to catch.

3. **Emit a recommendation block per file** at **Notice / Warn / Critical** (Green files are silent), naming the driving `reason`:
   - **Notice** — advisory only. Docs/specs → note a Multi-Part split is advisable; code → note for awareness. No backlog item.
   - **Warn** (`reason=cost` ≥ `warn`, or `reason=read` ≥ 240 KiB / ≥ 22K model-tok) — recommend the remedy by file type (below) **and file a backlog item** via the consumer project's backlog mechanism (`handlers/backlog.md` Phase 7 create flow — generic, no project identifiers).
   - **Critical / `reason=cost`** (≥ `critical`) — warn + file a backlog item + flag the task **`1M-exception`** (dispatch on Opus / 1M) so the plan still completes; the file won't fit a lean task even alone.
   - **Critical / `reason=read`** (≥ 25K model-tok page cap OR ≥ 256 KiB byte cap OR ≥ 2,000 lines) — warn + file a backlog item + recommend a **paged read** (`offset`/`limit`/Grep) for read-only context, or **refactor/split + backlog item** for a core or to-be-edited dependency. Do **NOT** flag `1M-exception`: the 1M window does not raise the per-Read page cap, and the Claude 5 tokenizer trips it on *fewer bytes* than Haiku 4.5's.
   - The scan is **never a hard stop** — a source-file Critical advises and files an item; it does not abort planning.

4. **Differentiate the remedy by file type** in the recommendation:
   - **Code** → refactor into smaller modules.
   - **Doc / spec / Execution Input** → Multi-Part split (existing [Multi-Part Output Convention](../references/session-context-budget.md#file-size-limits)).
   - **Dense (notebook / minified / compressed JSON)** → measure precisely (`measure_files.py` auto-detects the notebook and json classes from the extension; minified files take the conservative text ratio) and extract only the needed sections.

5. **Generated artifacts the plan itself authors** that a runner MUST read — task files, Orchestration, Recovery, Consolidated Context parts, Execution Inputs, task Output files — carry a **HARD** read-gate ceiling (MUST Multi-Part split to stay readable), NOT advisory, per `references/session-context-budget.md` [§ File Size Limits — Generated Artifacts](../references/session-context-budget.md#file-size-limits--generated-artifacts-binding). External source files the runner reads but does not generate stay advisory (warn + backlog + read tactics).

> [!constraint] Read-Reason Critical Is NOT `1M-Exception`-Resolvable
> WRONG — a Required Context file scans Critical with `reason=read`; the planner flags the task `1M-exception` and dispatches it to Opus, expecting the 1M window to absorb the file:
> ```
> # 280 KiB external doc → classify_file → {level: Critical, reason: read}
> Task flagged: 1M-exception   ← WRONG: the per-Read page cap is unchanged by the window,
>                                and the Claude 5 tokenizer trips the token gate on FEWER bytes than Haiku 4.5's
> ```
> CORRECT — `reason=read` Critical recommends a paged read / refactor and files a backlog item; only `reason=cost` Critical earns `1M-exception`:
> ```
> # reason=read  → paged read (offset/limit/Grep) for read-only; refactor+backlog for a to-be-edited dep
> # reason=cost  → flag 1M-exception (Opus/1M); plan still completes
> ```

