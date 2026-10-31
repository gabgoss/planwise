# Handler: /planwise plan — Part 3: Verify, Confirm and Review

**Part 3 of 3.** This handler spans three files, split by step range because the combined text exceeds the Read-tool page cap. Each step keeps its own identifier wherever it lands, so an existing `Step N` reference still names exactly one section — only the filename that holds it changes. See [`plan.md`](plan.md) for the full three-part pointer table, the Config Gate, the Required References, the index-shape gate and Step 0. [`plan-Part-2-GatherAndGenerate.md`](plan-Part-2-GatherAndGenerate.md) covers Steps 1-8c.

This file covers **Steps 8d-10**, the **Validation Checklist** and **Deferred Authoring**: update the plans index, populate the Verification Commands, confirm the output, emit the cross-sprint declarations, harmonize the pass, gate the plan review, and check the plan's completeness.

---

## Workflow (continued)

### Step 8d: Update Plans Index

**Runs once, after every sprint has been scaffolded** (not per-sprint like 8/8a-8c/8e).

The plans index is generated from each plan's Master Plan, so `/planwise list` reflects the new plan once the generator runs. The Master Plan written earlier in this handler already carries `**Status:** READY_TO_EXECUTE` and its dates. Nothing writes a row by hand, and no Path is composed.

Run the generator once, after every sprint is scaffolded:

```bash
python "{plugin_root}/scripts/generate_plans_index.py" --config "{planwise_root}/config.yaml" --write
```

Exit 2 means nothing was written. Print the `Error:` line verbatim and route by cause. `hand-authored plans index`: the gate before Step 0 was bypassed, so run it. `neither a hand-authored nor a generated`: `/planwise upgrade` will not migrate it, so name `migrate_plans_index.py --report` and never `--replace-legacy`. `over the … -token budget` (an over-budget render): the render is too large, so tell the user to shard or shorten the index.

To change a plan's row later, edit the Master Plan's `**Status:**` line (and its footer date), then run `generate_plans_index.py --write`. See [`references/plans-schema.md`](../references/plans-schema.md) § The One-Writer Rule.

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
   Commands table — substitute every `{placeholder}` with a concrete shell invocation for a
   build, test, lint, or database check, or a named native tool call (`Read`, `Grep`, or
   `Glob`) for a file-read or content-search check.
4. **Ensure all three command types appear** (connectivity / pre-condition, lint or format,
   exec or smoke test). A task missing one of these types uses the `<!-- NEEDS-COMMAND -->`
   marker carried in the `> [!verify]` skeleton (`templates/task-file.md`) in place of that
   type's command line, so the gap is visible at review time, NOT silently left blank.
5. **Measure at the gate's scope.** Run each per-task Before/After command against the task's
   own paths. Record that value as the gate's pre-edit annotation. Run a whole-population
   command once per plan, before the first task file. A whole-population command is the full
   suite or the whole-repo lint. Run it in the foreground with a timeout above its expected
   duration, and state that duration. Record the value with the repo's `HEAD` sha in the Master
   Plan § Decisions (Locked). Reuse it only in gates that run before any edit to that population.
   Re-check the tree identity at each dispatch. See `references/gate-pre-edit-baseline.md`
   §10.1.1 Scope the measurement to the gate's population.

**Per-File-Type Command Map** (mirrors `templates/task-file.md` §Per-File-Type Commands):

| File Type | Lint / Format | Exec / Smoke | Notes |
|-----------|--------------|--------------|-------|
| `.{src-ext}` (compiled or scripted source) | `{lint-cmd} {path}` / `{format-cmd} {path}` | `{test-cmd} {path}` | Consumer fills `{lint-cmd}` / `{test-cmd}` from `config.yaml.build_commands` |
| `.{notebook-ext}` (runnable-notebook artifact) | `{lint-cmd} {path}` (if applicable) | `{exec-cmd} {path}` | `{exec-cmd}` is the consumer's notebook runner / execute-in-place command |
| `.sql` | `{sql-lint-cmd} {path}` (if applicable) | `{driver-cli} -f {path}` | DB writes also pin schema per `references/schema-pin-requirement.md` |
| `.{build-system-ext}` (e.g., compiled-language sources) | `{format-cmd} {project} --verify-no-changes` | `{build-cmd} {project}` then `{test-cmd} {project}` | Connectivity precheck if integration test |
| `.{view-template-ext}` | `{format-cmd} {project} --verify-no-changes` | `{build-cmd} {project}` | Smoke render if applicable |
| `.{ts-ext}` / `.{tsx-ext}` | `{lint-cmd} {path}` | `{build-cmd}` then `{test-cmd}` | Plus `{type-check-cmd}` if the language supports it |
| `.md` (reference / rule edits) | `{md-lint-cmd} {path}` (if configured) | `python "{plugin_root}/scripts/measure_files.py" {path}` (must land OK — < 22K tokens / < 240 KiB / < 2,000 lines) | Per `references/session-context-budget.md` File Size Limits |
| `.{ext}` (other) | `{lint-cmd} {path}` | `{exec-cmd}` | Consumer-project supplies the binding from `config.yaml.build_commands` |

A planner writes `{plugin_root}` into a task file as the literal token and never substitutes the configured path there. A planner resolves the token only for a command the planner itself runs while planning. A substituted path names one plugin version and keeps running that version after an upgrade.

> [!constraint] Verification Commands MUST Be Populated, Not Templated
> WRONG — task file ships with the literal `{cmd_before_1}` / `{cmd_after_1}` placeholders, or
> with vague prose like "run lint and tests":
> ```markdown
> ## Verification Commands
> > [!verify] Before / After Commands
> > **Before:** {cmd_before_1}
> > **After:**  {cmd_after_1}
> ```
> CORRECT — placeholders resolved to explicit shell invocations (build/test/lint/DB checks) or
> named native tool calls (file-read/search checks) from the per-file-type map, covering all
> three command types (precheck + lint/format + exec):
> ```markdown
> ## Verification Commands
> > [!verify] Before / After Commands
> > **Before:**
> > ```
> > {lint-cmd} src/{module}/        # lint baseline, this module only
> > {test-cmd} src/{module}/        # test baseline, this module only — never the whole suite per task
> > ```
> > **After:**
> > ```
> > {lint-cmd} src/{module}/
> > # pre-edit: 0 findings → invariant: 0
> > {test-cmd} src/{module}/
> > # pre-edit: 41 passed → expect 43 passed
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
- Sprint-{XX}-{sprint_names[XX]}/{Abbrev}-S{XX}-Sprint-Plan.md            (x{sprint_count})
- Sprint-{XX}-.../Session-{YY}-.../{Abbrev}-S{XX}-{YY}-Orchestration.md   (one per session)
- Sprint-{XX}-.../Session-{YY}-.../{Abbrev}-S{XX}-{YY}-Recovery.md        (one per session)
- Sprint-{XX}-.../Session-{YY}-.../{Abbrev}-S{XX}-{YY}-{##}-{Agent}-{Task}.md (one per task)
- Sprint-{XX}-.../Session-{YY}-.../Outputs/.gitkeep                       (one per session)
- ... enumerate the real path of every file, for every sprint AND every session

**Sprints Authored:** {sprint_count}   **Sessions Authored:** {sum of session_count}
**Task Files Created:** {N} files total (one per task, per session)
{If any sprint or session was deliberately not authored, name it here and point at the Master Plan's `## Deferred Authoring` section.}

**Next Steps:**
1. Review and refine the Master Plan
2. Review task files for completeness
3. Run `/planwise review {Abbrev}` to validate the plan (recommended before execution)
4. Execute Sprint-01/Session-01 using `/planwise run` or manually following READ-CONFIRM-ACT
```

### Step 9a: Emit the Cross-Sprint File-Touch Declarations

**Runs when this invocation authored 2+ Sprint Plan files.** It runs after every sprint's files exist — the matrix cannot be built before then — and before Step 9b.

Build the file-touch matrix across the sprints this pass authored: for every path named as an edit target, the set of `(sprint, task)` writers. Take it from each Sprint Plan's `## Write-Set` section. [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](../references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §16 requires it (rule 16.1) and governs the emissions below (rule 16.6). **Intersect every sprint pair, not only the pairs the ordering line joins with `∥`.**

For each path with two or more writing sprints, emit all three of these — none is optional:

| Emit | Into | Content |
|------|------|---------|
| A `## Cross-Sprint File Touches` row | **each** involved Sprint Plan | the file, every writing task, and the region each one touches |
| A Step-1 prerequisite gate | the first writing task of the later sprint — or, where the pair has no declared ordering, of **both** sprints | read the live file and record its observed co-writer state before editing |
| An ordering edge, **or** a `MUST NOT run concurrently (shared file: {path})` row | the Master Plan's Sprint Dependencies table | whichever disposition the pair takes; a blank cell is not a third option |

> [!constraint] An Unordered Shared File Is the Dangerous Case, Not the Exempt One
> The sequential rule speaks of "the *later* sprint". A pair with no declared ordering has no later sprint, so a matrix walked only for ordered pairs skips it — while that pair is precisely the one free to run in either order or at once. Emit into both sprints and close the ordering explicitly.
>
> Add the co-writer content assertion to each writing task's Verification Commands as well: a path-scoped diff count verifies the presence of that task's own edit and can never show the absence of another writer's loss, so it cannot be the control for a shared file no matter how rigorously it is applied.

Record the matrix's outcome — the shared paths found and how each pair was closed, or `no shared paths` — in the Step 9 confirmation block.

### Step 9b: Post-Pass Harmonization

**Runs when this invocation authored 2+ Sprint Plan files** — the same `n_sprints_scaffolded_this_pass` count Step 10 uses — **or fanned out to 2+ scaffolding subagents.** Skip it for a single-sprint pass. It runs after every sprint's files exist and **before** the Step-10 review gate.

The three deviation classes in [`references/scaffolding-hygiene.md`](../references/scaffolding-hygiene.md) §8 accumulate whenever plan files are authored in parallel from one template set. The scaffolder is the cheapest place to catch them, because it still holds every file it just wrote: at authoring time a rename has no consumers, while after the fact the same rename is an edit sweep through every citing task file across every sprint.

Sweep this pass's own output for all three classes, then harmonize what surfaces:

| Class | Sweep | Harmonize to |
|-------|-------|--------------|
| **A — section-header drift** | The gate grades each `##` heading the orchestration, sprint plan and task-file templates mark with a bare `<!-- REQUIRED -->`. `Grep` the rest across every Orchestration, Sprint Plan and task file this pass authored: each conditional `##` heading in the files where its condition holds (for example `## Dispatch Layers` in a DELEGATED Orchestration), and each template `###` heading. A heading whose hit count is below that file count is missing from the remainder | The template's exact wording, restored in every file that dropped it |
| **B — optional formatting lines omitted** | The gate reports each missing formatting line, counted outside code fences: `**Total Estimated:**` and `**Mode:**` in an Orchestration, and `**Total Sessions:**` in a Master Plan | The line restored wherever it is absent |
| **C — `Scaffold-{Abbrev}/` absent** | `Glob` for `Exec-{Abbrev}/` first: absent ⇒ the plan is still at Discovery and this class does not apply. Present ⇒ `Glob` for `Scaffold-{Abbrev}/` | The folder created, per `scaffolding-hygiene.md` §8 Class C |

**A script runs the Class B and Class C sweeps and the graded part of Class A.** On the fan-out path, the orchestrator dispatches `planwise:scaffold-harmonizer` (`handlers/plan-scaffolding.md` Step 4, Fan-Out Path). The harmonizer runs the gate below and harmonizes what it reports. On the inline path, the orchestrator runs the same command itself:

```
python -B "{plugin_root}/scripts/scaffold_deviations.py" check {exec_dir}
```

`{exec_dir}` is the plan's `Exec-{Abbrev}/` folder for a scaffold pass. For a standard pass, which has no `Exec-` folder, it is the plan's own folder, `{plans_dir}/{PlanName}/`. The gate grades Class C only when the folder is named `Exec-{Abbrev}`, so a standard pass always reports `C=0`. The gate prints one `CLASS_A`, `CLASS_B` or `CLASS_C` line per deviation, then a final `deviations: A=<n> B=<n> C=<n>` line. Exit 0 means clean, and exit 1 means deviations were found. Exit 2 means the path is missing or not a folder, a template is unreadable (`ERROR: template unreadable`), or a plan file is unreadable or not UTF-8 (`ERROR: cannot read plan file <path>`). The gate does not grade the conditional `##` headings or the `###` headings, so the orchestrator runs the Class A row's `Grep` sweep for them on both paths. Step 9's confirmation block records the gate's `deviations:` total line and the result of that `Grep` sweep.

> [!constraint] The Output-Naming Scheme Is a Pass-Level Decision, Not a Per-Sprint One
> Task-output filenames may number by **task** ordinal or by **session** ordinal. Either is fine. Mixing the two across sprints in one pass is not.
>
> WRONG — each sprint picks its own scheme, and the single-session sprint hides which one it used:
> ```
> Sprint-01 (1 session):  {Abbrev}-S01-01-{Topic} … {Abbrev}-S01-05-{Topic}   ← numbered by TASK
> Sprint-02 (3 sessions): {Abbrev}-S02-02-{TopicA/B/C}                        ← numbered by SESSION
> ```
> Read across sprints, `{Abbrev}-S01-02-…` parses as sprint-session when it is in fact sprint-task. A single-session sprint never reveals which scheme it used, so the ambiguity stays invisible until a later multi-session sprint picks the other one — by which time every consuming task file cites the old names and harmonizing means editing every citation.
>
> CORRECT — one scheme, chosen for the pass and applied to every sprint in it:
> ```
> Sprint-01 … Sprint-{N}: all task outputs numbered by the SAME ordinal,
>                         with the topic disambiguating within a number
> ```
> Choose the scheme once, apply it uniformly including to single-session sprints, and state the choice in the Master Plan rather than leaving it implicit.

Record the outcome — the classes found and what was harmonized, or `clean` — in the Step 9 confirmation block. Step 10's review then **confirms** the sweep instead of discovering the drift. The review-side checks stay in force regardless: they are what still catches a hand-authored or resumed scaffold that skipped this step.

### Step 10: Plan Review Gate

After outputting the Step 9 confirmation and running Step 9b, offer plan review options.

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

Spawn the review as an Agent subagent:

```
Agent(
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
[ ] COMPLETENESS — Sprint Plan files on disk == Sprint Overview rows in the Master Plan
    (minus any sprint listed under `## Deferred Authoring`). Count both; a mismatch FAILS.
[ ] COMPLETENESS — Session folders on disk == Sessions-table rows summed across all Sprint
    Plans (minus any session listed under `## Deferred Authoring`). Count both; a mismatch FAILS.
    Both checks are counts that can fail, not prose to affirm. Run them by Glob-ing
    `Sprint-*/` and `Sprint-*/Session-*/` and comparing against the declared tables — a plan
    that declares 6 sprints and authored 1 must FAIL here and name the 5 it did not author.
[ ] Every Sprint Plan has Objective and Sessions table
[ ] Orchestration has Task List
[ ] Orchestration has Task Files table with links
[ ] Task files exist (one per task, numbered 01, 02, 03...)
[ ] Task files follow naming: {Abbrev}-S{XX}-{YY}-{##}-{Agent}-{Task}.md
[ ] Recovery file initialized
[ ] Outputs/ folder created
[ ] All files follow naming conventions
[ ] Plans index regenerated (generate_plans_index.py --write; no hand-written row)
[ ] Session token estimates validated (< `practical_session_limit` per session — 100K on Pro, 400K on Max; see `references/session-context-budget.md` §5)
[ ] Each task has a bottom-up estimate: (Required Context tokens) + (output tokens) <= task estimate
[ ] If DELEGATED: each task estimate + 54K overhead < `context_window` (200K on Pro, 1M on Max)
[ ] Execution Strategy declared in Orchestration (DIRECT or DELEGATED)
[ ] If 2+ Opus tasks or META session -> Strategy is DELEGATED
[ ] If DELEGATED: Orchestration Required Context = plan files only
[ ] If DELEGATED: the template's `> [!constraint] Mandatory Context Boundary` callout (Reviewer Check 012) lists what orchestrator never reads
[ ] If effective Token Saver on (plan Master-Plan `Token Saver:` field over the project `context.token_saver` default) — the Step 8c large-file scan was **run, not reproduced by hand**, and its exit code recorded: `python "{plugin_root}/scripts/token_saver.py" --scan --plan {plan_path} --config {config}`. **Exit 0 ticks this box.** A non-zero exit names the Warn+ files: each needs a backlog item, a cost-reason Critical needs its task flagged `1M-exception`, and a read-reason Critical needs a paged-read/refactor note — never `1M-exception`. Re-run until it exits 0, or record per remaining file why it stands. Generated artifacts a runner reads must also be under the line/byte/token read gates. This item is the tool's exit code, not a judgement — a ticked box with no run behind it is the failure the scan exists to prevent
[ ] If Discovery → Scaffolding: Multi-tier extraction tiers documented in EI header (Tier 1 + Tier 2 + Tier 3 where applicable)
[ ] If Discovery → Scaffolding: Deferred/Out-of-Scope Log present per sprint
[ ] If Discovery → Scaffolding: Retention threshold ≥ 80 % per EI section (auto-reject below)
[ ] If Discovery has user-action gates outside /planwise run: Master Plan Status is IN_PROGRESS with `awaiting {user action}` note (per `references/session-execution-protocol.md` Discovery / Meta-Plan Status section)
[ ] Scope favors the coherent treatment — no known-partial fix is planned without a recorded constraint and a named residual defect (see the callout below)
```

### Deferred Authoring

Authoring a later sprint is sometimes correctly postponed — a sprint whose design depends on what an earlier sprint finds cannot be written honestly up front. Deferral is legitimate. **Silent deferral is not**, because an unauthored sprint and a forgotten sprint look identical on disk.

Declare it in the Master Plan, so the two completeness checks above can pass against a declared subset instead of forcing every plan to author everything:

```markdown
## Deferred Authoring

| Sprint / Session | Not authored because | Unblocked when |
|------------------|----------------------|----------------|
| Sprint-{XX} ({Name}) | {why its design depends on an earlier sprint's finding} | {the concrete trigger} |
| Sprint-{XX} Session-{YY} | {reason} | {trigger} |
```

Each row names a concrete trigger, not "later" — the trigger is what a future session tests to know the deferral has expired.

> [!pitfall] Read the Deferral Set From the FIRST Column Only
> The "Unblocked when" cell routinely names another sprint (*"Sprint-01 Recovery shows COMPLETE"*). A check that scans the whole section for `Sprint-NN` counts those trigger mentions as deferrals, over-counts the deferred set, and can subtract away a sprint that was never declared deferred at all — masking the shortfall the check exists to catch. Parse the **Sprint / Session column** only.

> [!constraint] A Deferral Is Declared or It Is a Shortfall
> WRONG — the Master Plan declares 6 sprints, the pass authors 1, the checklist is affirmed as prose, and the plan reports success. Every later session has to be authored mid-execution, in a session whose context budget was sized for running tasks rather than writing them.
>
> CORRECT — either author all `{sprint_count}` sprints and all `sum({session_count[XX]})` sessions, or list the unauthored ones under `## Deferred Authoring` with a trigger apiece. The completeness checks subtract the declared rows and still fail on anything undeclared.

An absent instruction reads as a boundary: without this section, an authoring agent that produced one session of one sprint can pass the checklist and assert the shortfall was prescribed. The counts above are what make that claim testable.

> [!practice] Plan the Right Fix, Not the Easy Fix
> When scoping reveals two treatments — a complete one that touches more surface (a full renumber, a schema migration, propagating a change through every consumer) and a narrower patch that leaves known incoherence behind — scope the complete treatment and cost it honestly. Budget pressure is answered by SPLITTING the coherent fix across tasks or sessions (see `references/session-context-budget.md` § Task-Level Estimation, and the [Task Sizing Categories](plan-Part-2-GatherAndGenerate.md#task-sizing-categories) table in Step 8c), never by shrinking it into a partial fix that is cheaper to execute. If a real constraint genuinely forces the partial path (an interface external consumers depend on, an irreversible boundary, a user-set deadline), record the constraint and the residual defect in the plan so the gap is a visible decision, not an accident. Overall project quality comes from doing the hard thing once, not the easy thing twice. Full principle, exception clause, and stage table: [do-the-hard-things.md](../references/do-the-hard-things.md).

---

