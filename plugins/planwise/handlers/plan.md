# Handler: /planwise plan

**Purpose:** Create a new plan following structured development best practices.

This handler spans **three files**, split by step range because the combined text exceeds the Read-tool page cap. Each step keeps its own identifier wherever it lands, so an existing `Step N` reference still names exactly one section — only the filename that holds it changes.

| Part | File | Steps / Sections | Topic |
|---|---|---|---|
| 1 (this file) | `plan.md` | Config Gate, Required References, Status Field, the Workflow gate, Step 0, Naming Conventions | The config gate, the references to load, the index-shape gate, mode detection, and the naming patterns |
| 2 | [`plan-Part-2-GatherAndGenerate.md`](plan-Part-2-GatherAndGenerate.md) | Steps 1, 2, 3, 4-7, 8, 8b, 8c | Gather and validate the plan details, create the folder structure, generate the plan files and task files, and validate the token estimates |
| 3 | [`plan-Part-3-VerifyConfirmAndReview.md`](plan-Part-3-VerifyConfirmAndReview.md) | Steps 8d, 8e, 9, 9a, 9b, 10, Validation Checklist, Deferred Authoring | Update the plans index, populate the Verification Commands, confirm the output, harmonize the pass, gate the plan review, and check completeness |

Reading order by mode: Standard mode reads this file, then Part 2, then Part 3. Discovery mode reads this file, then `plan-discovery.md`, then Part 3 for Step 10. Scaffolding mode reads this file, then `plan-scaffolding.md`, then Part 3 for Steps 9a, 9b and 10, and Part 2 when it follows a Step 3, 4-7, 8 or 8c link.

## Table of Contents

- [Config Gate](#config-gate-auto-init-fallback)
- [Required References](#required-references)
- [Status Field](#status-field)
- [Workflow](#workflow)
  - [Step 0: Detect Mode](#step-0-detect-mode)
  - [Steps 1-9: Standard Plan](plan-Part-2-GatherAndGenerate.md#step-1-gather-information)
  - [Step 10: Plan Review Gate](plan-Part-3-VerifyConfirmAndReview.md#step-10-plan-review-gate)
- [Validation Checklist](plan-Part-3-VerifyConfirmAndReview.md#validation-checklist)
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

> [!practice] Session-Level Effort for Large Plans
> This handler executes inline in the calling session — there is no dispatched planner agent to carry an `effort:` frontmatter field. For a large or multi-sprint scaffold, consider running `/effort high` (or your project's measured preference) before invoking this command, or set a standing default in *your own project's* `.claude/settings.json` (`effortLevel`, or a per-model entry under `modelSettings`). The plugin pins `effort:` only on the agents it dispatches and measured (`references/agent-authoring.md` § Shipped Effort Levels); nothing it ships changes the session level. This recommendation is advisory only.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`, `native-tool-use.md`, `feedback-drafting.md`) are linked from SKILL.md, not loaded by it. Read one only when a step below cites it.

**Plan-specific references (always load):**
1. Read `references/session-plan-requirements.md`

**Conditional references:**
- If a file this plan authors routes or reconciles a cross-task coordination flag (a `## Pre-Known Cross-Task Coordination Flags` block or a flag-routing step), records a Scope-Expansion Decision, or pins a commit-shaped criterion: Read `references/read-confirm-act-protocol.md` (READ-CONFIRM-ACT, the structural-findings gate, §1.2-§1.6) and, to author a flag, `references/read-confirm-act-protocol-Part-2-FlagAuthoringSurfaces.md`
- If Step 0's indicator tables leave Standard vs Meta-Plan undecided, or a task file this plan authors states context-conservation rules (task list format, compaction triggers, minimal prompts, output file strategy): Read `references/context-loading-and-conservation.md`
- If a naming or folder question is not settled by Naming Conventions and Step 3 (the With Meta-Plan tree, full Task ID format in cross-sprint references, agent delegation, pre- or post-session checklists): Read `references/session-planning-protocol.md`
- If Step 8c's Token Saver scan reports a Warn-or-worse file, a task sizes a file that does not exist yet, or a generated artifact must be split into Parts: Read `references/session-context-budget.md` (Per-Operation Cost Reference, File Size Limits, Read-Tool Hard Limits, Threshold Formulas)
- If the plan is a Discovery / Meta-Plan whose Master Plan carries a user-action gate outside `/planwise run`: Read `references/session-execution-protocol.md` §4.5 (Discovery / Meta-Plan Status)
- If the plan creates or modifies agents: Read `references/agent-authoring.md`
- If the plan creates or modifies skills: Read `references/skill-authoring.md`
- If the plan creates or modifies rules: Read `references/rule-authoring.md`
- If planning a scaffolded multi-sprint plan (Discovery → Scaffolding workflow): Read `references/ei-fidelity.md`, `references/task-content-fidelity.md`, `references/discovery-and-exit-criteria.md`, `references/scaffolding-hygiene.md` (§1–§12) **and** `references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md` (§13–§19) — the hygiene reference is split across two files, and Part 2 carries the rules a scaffold must satisfy before it closes
- If the plan contains verification tasks (grep/awk match-pattern + pass/fail gate): Read `references/verification-task-authoring.md` (the family index and its §7 checklist), then `references/gate-heuristic-verifier-patterns.md` (per-unit assertions, sibling formats, denominators, a counting predicate's unit; Checks 058 and 059), `references/gate-verdict-contract-and-adjudication.md` (PASS requires Actual = Expected; Check 060) and `references/gate-absence-and-consistency.md` (absence greps, population, a fact encoded twice)
- If a task's Verification Commands carry an After block, or a Success Criteria item states an expectation over a measured value: Read `references/gate-pre-edit-baseline.md` (every gate records its measured pre-edit value; Check 082) and `references/gate-input-set-and-compared-window.md` (a diff-pinned or sweep criterion records its input-set counts; a verbatim proof prints its compared-set size) (Step 8e)
- If an anchor, exit criterion or Execution Input gate enumerates outcomes, or a gate pins a `git diff --stat` allowed set over a directory a tool regenerates: Read `references/gate-anchor-outcome-set.md` (the anchor accepts exactly the task's terminal branches; Check 095)
- If a task pins any `grep`, `diff`, `wc` or `awk` gate, or pins a pattern, count or count method before its subject exists: Read `references/gate-command-semantics.md` (the four command-semantics traps, regex dialect, digit boundaries, window size) and `references/gate-pinned-from-real-content.md` (a verdict line's bytes, a heading counted by anchor, a gate run over the real content first) (Step 8e)
- If a task's deliverable is a gate (guard, hook, linter, validation pass), or an acceptance criterion cites a gate run as proof: Read `references/verification-gate-evidence.md` (the family index), then `references/gate-positive-and-mutation-controls.md` (the positive control, the mutation control, the dry-run pair) and `references/gate-fixture-provenance.md` (an input set that could have contained the defect; what the proof does not cover)
- If a task's gate checks an extraction boundary or anchor, a sweep that several runners share, a fixture set scored against a threshold, or a per-item gate fed a precomputed value: Read `references/gate-discriminating-case.md` (could the input set have contained the case that fails the gate?)
- If a task's content is a live gate's subject, or a runner may report that it shaped content to satisfy a gate: Read `references/gate-artifact-over-instrument.md` (the artifact is authoritative; pre-adjudicate the collision at dispatch)
- If a task moves a section between references, gates a generated path list or row count, claims bytes or line endings preserved, or grades a decision log or an exit code: Read `references/gate-old-home-citation-sweep.md`, `references/gate-generated-input-integrity.md` and `references/gate-script-output-assertions.md`
- If a proof run builds fixture trees in a repo whose working tree ships, or a Python package re-exports or guards imports: Read `references/gate-environment-inputs.md` (§20, §22)
- If a task's Verification Commands assert a property of a diff (comment-only, no-logic-change, N-files-touched), or the task creates or relocates the file it then gates: Read `references/gate-baseline-independence.md` — an untracked target makes the gate vacuous and `git add -N` inverts it, so pin a baseline copy before the first edit (Step 8e)
- If a task's Verification Commands include a match pattern, a count, or a diff filter: Read `references/gate-predicate-discrimination.md` — write each anchor so it can be paired against a known-bad state, scope a negative claim to a query whose positive would be believed, and anchor a diff filter on the sign alone (Step 8e)
- If a task's Verification Commands include a count, a coverage ratio, an absence criterion, or an `N in = N out` balance: Read `references/gate-denominator-integrity.md` — prove the property on your own hunk or on a literal you authored, not on a count over a shared file, and pair every absence criterion with a positive criterion over the full item set
- If planning a task with DB writes (SQL INSERT/UPDATE/MERGE): Read `references/schema-pin-requirement.md`
- For Auto Mode behavior (how a step behaves when `AskUserQuestion` cannot be answered non-interactively): Read `references/auto-mode-policy.md`
- If a task's deliverable creates or modifies a cross-process boundary (IPC layer, wire-protocol serialization, file-format codec), in-process numeric or codec code, a deploy step, or multi-target runtime code: Read `references/verification-gates.md` (the family index) and `references/gate-runtime-boundary-evidence.md` before populating that task's Verification Commands (Step 8e); `references/gate-exit-verdict-and-smoke-reports.md` governs the Sprint exit verdict and the Verification Commands presence checks
- If a task's Verification Commands use `git diff`: Read `references/gate-diff-baseline-pinning.md` — record `$..._BASE` before the first edit and scope every gate to it (Step 8e)
- If a task's deliverable is a gate, guard, hook, linter or validation pass, or the plan composes a verification battery: Read `references/gate-instrument-proof-obligations.md` (the four obligations) and `references/gate-change-vs-state-detecting.md` (name at least one state-detecting gate)
- If a task writes a run sheet or probe driver that pins flags on a reset or launch line, or a grader over a numeric log field: Read `references/gate-run-sheet-and-grader-fields.md` (§13-§14) — pin the field the hook reads, not the flag whose name matches the intent
- If a task spec cites third-party SDK identifiers, type names, enum members, delegate shapes, framework presence, or destination file paths under scoped-rule triggers: Read `references/verify-against-shipped-artifact.md`
- If the plan authors a task that creates or modifies a rule, agent, skill, handler, or CLAUDE.md callout (promoting lesson/backlog content): Read `references/artifact-self-containment.md`

---

## Status Field

When `/planwise plan` completes successfully, it sets `Status: READY_TO_EXECUTE` in the Master Plan.

This status is the **execution gate**. The `/planwise run` command checks this before any work begins.

---

## Workflow

> [!gate] Before any write in any mode (Standard, Discovery or Scaffolding), run `index_shape_preflight.py` as [`index-shape-gate.md`](../references/index-shape-gate.md) directs. <!-- AUTO-MODE: critical -->

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
