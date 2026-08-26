# Handler: /planwise plan — Scaffolding Workflow

**Loaded by:** [`handlers/plan.md`](plan.md) Step 0, when Scaffolding mode is detected.

**When:** A Meta-Plan Discovery phase produced Consolidated Context parts, and you need to create the Execution Plan from those parts.

**Input:** `Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md` files

## Scaffolding Step 1: Read Consolidated Context Parts

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

## Scaffolding Step 2: Determine Plan Details

From the user's prompt or by asking:
- **Abbreviation:** Same as the Meta-Plan's abbreviation (e.g., `GCW`)
- **Root:** `{plans_dir}/{PlanName}/Exec-{Abbrev}/` (resolved from config.yaml)
- **Scaffold folder:** Always create `{plans_dir}/{PlanName}/Scaffold-{Abbrev}/` to maintain the three-phase convention (`Meta-{Abbrev}/`, `Scaffold-{Abbrev}/`, `Exec-{Abbrev}/`), even when scaffolding is done inline in the same session as planning
- **Sprints:** Derived from each part's `Scope:` field (one sprint per execution-scoped part)
- If stale `Exec-{Abbrev}/` files exist from a placeholder, **delete them first**

## Scaffolding Step 3: Design Sprints from Parts

Map each Consolidated Context part to a sprint. Each part's `Scope:` and `What This Enables` section defines that sprint's work.

**Rules:**
- Parts with `Scope: Cross-sprint reference` are NOT sprints -- they're referenced by all sprints
- Parts with a specific scope (e.g., "Schema Implementation Sprint") become sprints
- Sprint ordering follows dependency logic (schema before registration before queries)
- The user may suggest a sprint structure -- respect it but validate against part content

**Global Source Map:** If using global numbering for source specs (recommended for multi-sprint plans), add a Global Source Map table to the Master Plan. This table assigns each spec output a global number and shows which sprints use it. See the [scaffolding master plan template](../templates/scaffolding-master-plan.md) for the table format.

## Scaffolding Step 4: Create Execution Inputs

For EACH sprint, produce an **Execution Input** file -- a sprint-scoped extraction of the Consolidated Context parts. Use the [execution-input.md](../templates/execution-input.md) template.

**Process:**
1. Identify which Consolidated Context parts feed this sprint (from Step 3 mapping)
2. Read those parts and identify which sections each task in the sprint needs
3. **Extract** the relevant content into sections, noting which tasks use each section
4. From cross-sprint reference parts, extract ONLY the decisions/conventions this sprint needs
5. Add Cross-References table tracing each section back to its source
6. If at/over 22K measured tokens (`python "{plugin_root}/scripts/measure_files.py" {EI file}`), split into parts: `{Abbrev}-S{XX}-Execution-Input-Part-{N}-{Topic}.md`

**Output:** One `{Abbrev}-S{XX}-Execution-Input.md` per sprint, placed in the sprint folder.

**This is extraction, not summarization.** Copy substantive content verbatim -- only reorganize by sprint scope.

**Cross-sprint content handling:**
- **Cross-sprint reference parts** (e.g., DesignDecisions with `Scope: Cross-sprint reference`): Extract relevant portions into each sprint's EI
- **Sprint-scoped sources with cross-relevant sections**: If Sprint 02 needs content from a source primarily assigned to Sprint 01, list that source in the EI's `Extracted from:` header like any other source. The Global Source Map in the Master Plan tracks which sources are shared

## Scaffolding Step 4.5: Multi-Tier Discovery Extraction

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

**Reviewer retention threshold** (enforced by `agents/plan-reviewer.md` EI Reviewer role):
- < 80 % retention → auto-reject
- 80 – 95 % retention → warn
- ≥ 95 % retention → pass

Retention = `(sum of EI section tokens + Deferred/OOS log tokens) / (sum of Tier 1+2+3 source tokens)`.

## Scaffolding Step 5: Generate Plan Files

**Search the lessons index for the artifact classes this plan will touch, before authoring task files.**

A plan that will author schema definitions, verification greps, generated notebooks, module docstrings, or any other recurring artifact class should search the lessons index for each class before writing task files, and cite the hits inline in the Required Context or Verification Commands of the tasks that touch them:

```bash
grep -rliE "{artifact_class_keyword}" {lessons_dir}/**/LL-*.md
```

Capture is a store, not a channel — a lesson reaches a runner only when it is cited in the artifact that runner actually reads (a task file's Required Context, its Verification Commands, or a coordination-flag block).

A lesson sitting correctly indexed and uncited is delivered to nobody.

The payoff scales with repetition: a plan that repeats one task chain across several sprints misses the same lesson once per repetition unless it is cited.

Use the [scaffolding master plan template](../templates/scaffolding-master-plan.md) for the Master Plan.

Use standard templates for all other files (sprint plans, orchestrations, recovery, task files).

**Critical difference from standard planning:** Every task file's `Required Context` table MUST reference the sprint's **Execution Input** file (with section numbers), NOT the original Consolidated Context parts. The Execution Input replaces the parts for execution purposes.

**Status rule:** Set ALL Sprint Plan files to `**Status:** PLANNED`. Only the Master Plan gets `READY_TO_EXECUTE`. Do NOT copy the Master Plan's status into Sprint Plans — each Sprint Plan starts as PLANNED and transitions to IN_PROGRESS → COMPLETE during execution.

**`.gitkeep` emission (mirrors standard [Step 3](plan.md#step-3-create-folder-structure)):** For EVERY session folder created during scaffolding, write an empty `Outputs/.gitkeep` placeholder file inside the session's `Outputs/` directory. Empty directories are not tracked by git, so a missing `.gitkeep` means the `Outputs/` folder disappears on clone and downstream `/planwise run` cannot write summary or task-output files into the expected path. Apply to every sprint × every session — same per-session `.gitkeep` rule as the standard Step 3 constraint. Also populate each task file's Verification Commands per the [Step 8e per-file-type command map](plan.md#step-8e-populate-verification-commands-per-file-type-map) — scaffolded plans must NOT ship with blank verification placeholders any more than standard plans do.

**Token Saver large-file scan (mirrors standard [Step 8c](plan.md#step-8c-validate-token-estimates-bottom-up)):** When the **effective** Token Saver value is `true` (resolve it via the plan's Master-Plan `Token Saver:` field over the project default — `get_effective_token_saver_config(config, plan_override)`, exactly as Step 8c does), run the same per-file warning ladder over every scaffolded task file's Required Context, with one scaffolding-specific addition — a scaffolded task's Required Context references the sprint's **Execution Input** (per the Critical-difference rule above), so scan the **EI-section sizes** the task cites (not the original Consolidated Context parts) plus any direct code references in the task. Derive thresholds via `token_saver.derive_thresholds(...)` and classify each cited file/section with `token_saver.classify_file(path, model=<task's Agent>, projected_added_bytes=<byte delta if the task edits it>, thresholds=...)`, then emit the graduated ladder (Warn/Critical), file a backlog item at Warn+, and flag the task `1M-exception` only for a **cost-reason** Critical — identical contract to Step 8c (`reason=read` Critical → paged read / refactor, never `1M-exception`). The Execution Input itself is a **generated artifact a runner reads**, so its read-gate ceiling is HARD: if a sprint's EI trips the token, byte, OR line gate, split it into `{Abbrev}-S{XX}-Execution-Input-Part-{N}-{Topic}.md` parts at scaffold time rather than letting a runner hit a truncated read.

**Shared-context single measurement (mirrors the standard [Step 8c](plan.md#step-8c-validate-token-estimates-bottom-up) pre-pass):** The measure-once/fan-out rule applies equally to scaffolded plans. A sprint's **Execution Input** is by construction cited in every task of the sprint — measure it (or each cited EI section) **ONCE** with `measure_files.py` on the live file, and write the **IDENTICAL** `KiB` / `~Tokens` into every citing task's Required Context row. The same applies to any cross-sprint shared doc (design pins, shared reference files). Never re-guess a shared file's size per task: one wrong guess otherwise replicates into every task subtotal, header, orchestration total, and the sprint total. If an EI or shared doc changes during scaffolding (e.g., a Multi-Part split), re-measure and re-fan the new value into all citing rows.

**Sprint-signoff scaffold (multi-session sprints):** For each sprint with multi-session work, add a sprint-signoff scaffold using the [sprint-signoff.md](../templates/sprint-signoff.md) template per `references/exit-criteria-fidelity.md` §16.3. Place the signoff file at `{plans_dir}/{PlanName}/Sprint-{XX}-{Name}/Sprint-Signoff.md`. The signoff quotes the sprint's EI exit-criteria verbatim — one row per criterion, one mechanical anchor per row — giving a multi-session sprint a single closeout checkpoint before it is marked COMPLETE. Single-session sprints MAY omit it.

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

## Scaffolding Step 6: Validation

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
[ ] If effective Token Saver on (plan Master-Plan `Token Saver:` field over the project `context.token_saver` default) — Token Saver large-file scan run over each task's cited EI sections + code refs; Warn+ files have a backlog item; cost-reason Critical tasks flagged 1M-exception (read-reason → paged-read/refactor, never 1M-exception); each sprint EI under the line/byte/token read gates (split into Parts if not)
```

## Scaffolding Step 7: Output Confirmation

Same as Step 9 in standard mode, plus include:

```
SCAFFOLDED FROM: Meta-{Abbrev} Discovery Phase
Parts consumed: {N} Consolidated Context parts
Execution Inputs created: {N} (one per sprint)
Sprints created: {N}
```

For a complete scaffolding example, see [sample-scaffolding-output.md](../examples/sample-scaffolding-output.md).

After the scaffolding confirmation, proceed to [handlers/plan.md Step 10: Plan Review Gate](plan.md#step-10-plan-review-gate).

---

**Back to:** [handlers/plan.md](plan.md)
