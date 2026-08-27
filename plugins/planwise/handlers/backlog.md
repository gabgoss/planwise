# Handler: /planwise backlog

**Purpose:** Parse the project backlog index, let the user select items, assess scope, route each item to the right action (direct fix, task list, or session planning), and update status.

**Arguments:**
- No args — interactive selection
- `$1` = item ID — direct item selection (e.g., `/planwise backlog 002`)
- `--priority High` — filter by priority
- `--abbrev APP` — filter by domain abbreviation
- `--status IN_PROGRESS` — filter by status
- `--no-check` — skip the Phase 1 archival-drift detect pass (fast triage)

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml:
   a. Check `planwise/config.yaml` (default planwise root)
   b. If not found, search one level down from project root for `*/config.yaml`

2. If found → continue to Required References (extract `plugin_root`, `project.planwise_root`, `project.backlog_dir`, `project.index_files.backlog`, `project.lessons_dir`, `project.index_files.lessons`, `build_commands.default`).

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
          --auto-from "backlog"
        ```
      - **If Auto Mode NOT active (interactive):**
        Use `AskUserQuestion` to collect project info (project name, scope, dirs),
        then run `init_project.py` with those values + `--auto-from "backlog"`.
   d. After init completes, RE-RESOLVE `config.yaml` (loop to step 1).
   e. If still NOT found after init:
      FAIL LOUD: "Init did not produce config.yaml. See output above."
      STOP — do not continue.

Where `{inferred_project_name}` = current git repo name or `cwd` basename (strip trailing `-`, `_`, `.git` suffix).

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed (YAMLError), DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise backlog." STOP.

All directory paths resolve as `{planwise_root}/{dir_name}` (e.g., `planwise/Backlog`). All script invocations should pass `--config {planwise_root}/config.yaml`.

The optional top-level `id_format` key (`prefixed` or `bare`) controls how a newly created item's ID is rendered in the index's canonical stored form; when the key is absent, the index's predominant form is inferred. Any other value is treated as `bare` — a typo in this key silently yields the legacy form.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

**Conditional references:**
- Loaded at Phase 3, step 3a (pivot check), for High-priority / top-scored / aged items or multi-item cohorts: Read `references/backlog-triage-pivot-detection.md`
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`
- If resolving a backlog item that touches task files: Read `references/task-content-fidelity.md`
- If resolving a BLI cluster (≥ 2 BLIs same Surfaced by + created): Read `references/verify-against-shipped-artifact.md`
- For the backlog index format, item file schema, scoring formula, script interfaces, status flow, or error handling: Read `references/backlog-schema.md`
- For Auto Mode behavior (how a step behaves when `AskUserQuestion` cannot be answered non-interactively): Read `references/auto-mode-policy.md`

---

## Phase 1: FETCH

**Score and parse the backlog index:**

```bash
python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml
python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml
```

- `score_backlog.py` computes priority scores (8 configurable factors, weights from `config.yaml`) and writes the Score column to the index
  - Items that block other open items get a blocker bonus per blocked item
  - If it prints a stderr `WARNING: computed … score(s) but wrote …` (a computed-vs-written shortfall), the warning MUST be surfaced to the user verbatim rather than swallowed — it means rows below a malformed row kept stale Score cells; recommend inspecting the index body before trusting the displayed ranking
- `parse_backlog.py` reads the backlog index at `{backlog_dir}/{backlog_index}`
- Outputs a formatted table of **selectable** items (excludes COMPLETE, CLOSED, and items blocked by open dependencies)
- Blocked items appear in a separate summary below the main table
- Prints JSON temp file path on the last line: `JSON: /tmp/backlog-XXXXX/items.json`
- If no open items: print "No open backlog items." and **STOP**

**With filters (pass through from `$ARGUMENTS`):**

```bash
python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml --priority High
python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml --abbrev APP
python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml --status IN_PROGRESS
```

**Detect archival drift (always-on unless `--no-check`):**

The backlog index is a denormalized cache: a COMPLETE/CLOSED item's file is moved to `Archive/` and its index link repointed as a **state-coupled** step in `update_backlog.py`. But an item that reaches a closed status by another path — a session closeout that hand-edits the index row + frontmatter — leaves the file stranded in the top-level backlog dir with an index link that never repointed, and nothing on the read side heals it.

**If `--no-check` is present:** skip this step (a fast triage) and go straight to displaying the table.

Otherwise, run the index-drift audit procedure in [`references/index-drift-audit.md`](../references/index-drift-audit.md) against the **backlog** index (`reconcile_backlog.py`, banner `planwise backlog — backlog index drift audit`) — the JSON shape, banner format, and write-on-consent reconcile flow (including the consent prompt) all live there. This is the read-side counterpart of `/planwise list` Step 2's plans-index drift check, and the same detect pass `/planwise doctor` Stage 12 reuses; none re-implements another's comparison.

If a write ran, re-run this Phase's parse so the reconciled links are reflected in this same invocation.

Display the table to the user.

---

## Phase 2: SELECT

**If `$1` was provided** (an item ID):
- Use that item ID directly — skip the selection prompt
- Read the JSON temp file to get the full item data

**If no arguments:**
- Present the table from Phase 1 (only selectable items — blocked items are excluded)
<!-- AUTO-MODE: convenience if $1 provided (use that item ID); critical if interactive (gate on user selection). -->
- Use `AskUserQuestion` to ask: "Which items would you like to triage?"
  - Provide the first 4 item IDs as options (highest priority from selectable items)
  - User can select one or more, or type a custom ID
  - Do NOT offer blocked items — they cannot be worked until their blockers are resolved

**For each selected item**, update status to IN_PROGRESS:

```bash
python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id "{item_id}" --status IN_PROGRESS
```

---

## Phase 3: RESOLVE

**For each selected item:**

1. Get the item's file paths from the JSON data (the `files` array)
2. Read each backlog item file (files have YAML frontmatter with `created`, `blocks`, and `status` fields)
3. **Pre-Routing Existence Gates** (run before the Citation-Freshness Preflight — two sequential checks with separate applicability conditions, never merged):
   - **3a. Pivot check** (High-priority / top-scored / aged items, or multi-item cohorts): skim `git log --oneline -20` for domains adjacent to the item and ask the framing question if a signal lights up, per `references/backlog-triage-pivot-detection.md` §1. If a pivot is confirmed, sweep the cohort to BLOCKED per that reference's §2 and STOP for this item — do not proceed to 3b or to step 4.
   - **3b. Existence-premise probe** (items whose deliverable applies a re-alignment verb — reconcile, re-target, re-align, align to the live shape, update to match — to a target outside the repo): probe the family (bare target, representative variants, siblings) before accepting the re-target framing, per `references/verify-backlog-citation-freshness.md` §11. If the premise fails (bare target and all variants absent), route to SURFACE — commit the probe evidence and route the scope decision to the user — and STOP for this item.

4. **Citation-Freshness Preflight (run before scoping or routing):** A backlog item's body is a snapshot — every reference it pins (a sequential identifier, a `file:line` anchor, an acceptance criterion, a "test/section X does Y" note) is a hypothesis about a live artifact that rots between authoring and execution. Re-prove each against the current artifact before scoping. See `references/verify-backlog-citation-freshness.md` §9.

   > [!checklist] Citation-Freshness Preflight (run before scoping or routing a backlog item)
   > - [ ] For every pinned sequential identifier the item cites (Check NNN, [`references/error-pattern-catalog.md`](../references/error-pattern-catalog.md) row N, reference §N.N), grep the live target for the current max and re-derive the next-free value; renumber the item's deliverables + self-references to match
   > - [ ] For every `file:line` anchor, re-locate the symbol by content grep; treat the cited line number as a cost hint only
   > - [ ] For every acceptance criterion, run the cheapest proof it is still unsatisfied before writing a fix; mark any already-satisfied criterion "already satisfied — verified"
   > - [ ] For every pre-drafted note/callout that asserts "test/section/function X does Y", verify against the live file and re-word to name the artifact that actually carries the behavior

5. **Staleness check:** If the item has measurable acceptance criteria (counts, percentages, coverage targets), run `{build_command}` (from config.yaml `build_commands.default`) *before* routing. If criteria are already met or nearly met, present a "Close as COMPLETE" option instead of routing through a fix workflow.
   - If the BLI's motivating driver is a runtime symptom (keywords: collision, race, hang, missing endpoint, intermittent), run a `grep -rn` for the symptom in `src/` and cross-check against recent session summaries in `Plans/**/Sessions/**/Outputs/`. If the driver is no longer active (no recent matches, fix landed), mark the BLI as STALE per `verify-backlog-citation-freshness.md §3h` and skip routing. Include §3h.untested-axes and §3h.cluster signal checks per the same reference.

6. Assess the item's scope using the routing decision tree in the [Routing Decision Tree](#routing-decision-tree) section below.

7. **Scoped-rule pre-delegation check (§3g):** Read the BLI's `Files` section. For each named destination path, grep `.claude/rules/**/*.md` for `paths:` declarations that include the destination. If any rule scopes a path matching the BLI's destination, flag the placement decision for human review BEFORE spawning the fix-agent.

   ```bash
   grep -rn "paths:" .claude/rules/
   ```

   Compare each `paths:` value against the BLI's destination paths. If a match is found, present a warning:

   > **Scoped-rule conflict detected:** destination `{path}` is covered by a scoped rule in `{rule-file}`. Verify the fix targets the correct file before delegating.

   This gate applies regardless of route (Route A or Route B) — do not skip it.

8. Present the scope assessment to the user:

> [!template] Scope Assessment Block
> ```
> ─────────────────────────────────────────────
> ITEM: {ID} — {Feature}
> Priority: {Priority} | Domain: {Domain}
> ─────────────────────────────────────────────
>
> ## What This Is About
>
> {2-4 sentence plain-language summary of what the backlog item describes}
>
> ## Files Touched
>
> - `{path/to/file1.ext}` — {brief role}
> - `{path/to/file2.ext}` — {brief role}
>
> ## Tasks at a Glance
>
> 1. {First discrete task or step}
> 2. {Second discrete task or step}
> 3. ...
>
> ## Scope Assessment
>
> Route: {DIRECT_FIX | TASK_LIST | SESSION_PLANNING}
> Reason: {why this route was chosen}
> LARGE_SCOPE: {true | false}
> ─────────────────────────────────────────────
> ```
>
> `LARGE_SCOPE` is only meaningful when `Route = SESSION_PLANNING`: `true` means the
> Decision Logic's `ELIF` branch fired (`HAS_MULTI_SPRINT` / `IS_ARCHITECTURAL` /
> `SUB_ITEMS >= 6`); `false` means Route C was reached only via the
> conservative-default `ELSE` branch. Carried forward unchanged into Route C — never
> re-derived there.

---

## Phase 4: ACT

<!-- AUTO-MODE: convenience -->
<!-- Default: Accept Phase 3 recommended route (DIRECT_FIX / TASK_LIST / SESSION_PLANNING). -->
**Use `AskUserQuestion` to confirm the routing:**
- Option 1: Recommended route (from Phase 3 assessment)
- Option 2: Alternative route
- Option 3: Skip this item

### Route A: Direct Fix (fix-agent delegation)

For bugs and targeted fixes with clear scope:

**Pre-spawn: extract cross-cutting audit candidates (§3i):** Before building the spawn prompt, read the BLI file and look for sections named `Cross-cutting check`, `Cross-cutting consideration`, or `Notes`. Extract any cross-cutting items listed there to include in the spawn prompt. If none are found, use `"none identified"`.

Delegate to the `fix-agent` via the Task tool:

```
Task {
  subagent_type: "planwise:fix-agent"
  description: "Fix backlog item {item-id}: {item-summary}"
  prompt: |
    Fix the following backlog item:

    Item ID: {item-id}
    Summary: {item-summary}
    Description: {item-description}
    Affected files: {file-list}
    Build command: {build-command-from-config}
    Cross-cutting audit candidates (in-scope by default): {list extracted from BLI cross-cutting sections, or "none identified" if absent}
}
```

**Result handling:**
- If fix-agent returns status FIXED → proceed to Phase 5 (verify + approve)
- If fix-agent returns status BLOCKED → report blocker to user, offer to route to Session Planning (Route C)

### Route B: Task List

For medium-scope items with 3-5 discrete steps:

1. Analyze the backlog item file to extract discrete steps
2. Create tasks using `TaskCreate` for each step
3. Work through each task sequentially
4. After all tasks complete, proceed to Phase 5

### Route C: Session Planning

<!-- AUTO-MODE: critical --> Step 2 below (EnterPlanMode) requires interactive user
consent the harness cannot obtain unattended. **If Auto Mode is active, skip directly
to step 5's `LARGE_SCOPE: true` dispatch (below) for every Route C item regardless of
LARGE_SCOPE, dispatching `backlog-planner` with item ID/summary/description/affected
files ONLY — no `Approved Approach` block, since steps 1-4 (which would have produced
a plan-mode design) never ran** — this mirrors `handlers/harvest.md` Stage 3's
existing unattended Route C contract exactly (it dispatches `backlog-planner` with
the item's own scope only; `agents/backlog-planner.md` §1 CLASSIFY confirms it
authors from the item's own scope with no such input). Log the skip: "Auto Mode:
skipping EnterPlanMode (no interactive consent channel); dispatching backlog-planner
directly with item scope only."

**Interactive flow (Auto Mode not active):**

1. Summarize the item context (title, files touched, tasks-at-a-glance,
   LARGE_SCOPE) — this seeds the plan-mode design so the ensuing Explore/Plan
   phases don't re-derive what Phase 3 already found.
2. Call `EnterPlanMode`, carrying that summary as the framing for what to design.
3. Once in plan mode, run the standard injected explore -> design workflow scoped
   to *this item's* approach (not full task-by-task detail), then write the plan
   file and call `ExitPlanMode`.
4. If the user declines the `EnterPlanMode` consent gate, or repeatedly picks "No,
   keep planning" without approving: stay in Route C's loop. Do NOT fall back to a
   manual "run /planwise plan yourself" message — offer to retry, or let the user
   explicitly choose Skip for this item (Phase 4's existing Option 3).
5. On `ExitPlanMode` approval, branch on `LARGE_SCOPE` (carried from Phase 3):

   **`LARGE_SCOPE: false`** — the approved plan-mode plan IS the deliverable:
   - Implement it in this session (same posture as Route A/B).
   - Proceed to Phase 5's existing "After Route B" flow (verify tasks done, show
     diff, `AskUserQuestion` Approve/Revert).
   - Phase 6 outcome: "Fix approved" -> COMPLETE, or "Fix reverted" -> NOT_STARTED
     (existing table rows — no new row needed for this branch).

   **`LARGE_SCOPE: true`** — hand off to the full session-planning agent:
   - Dispatch `planwise:backlog-planner` via the Task tool, using the same
     invocation shape Route A uses for `fix-agent` (above), passing: item ID,
     summary, description, affected files — and, ONLY when reached via this
     interactive flow (steps 1-4 ran and produced a plan-mode design), an
     `Approved Approach` block containing the just-approved plan-mode plan file's
     content (backlog-planner authors its Standard plan FROM this approach when
     present). When this dispatch is instead reached via the Auto Mode skip above,
     omit the `Approved Approach` block entirely — backlog-planner authors from the
     item's own scope, exactly as `harvest.md` Stage 3 already does.
   - Read the returned status block (`agents/backlog-planner.md` §Status Block).
     - If `TASK_STATUS: BLOCKED` -> apply `agents/backlog-planner.md`'s own
       Failure Semantics table verbatim: status -> NOT_STARTED (never PLANNING
       with no plan file), Notes `AUTO-PLAN FAILED {date}: {reason} — needs manual
       triage`. Do NOT proceed to the review step below.
     - If `TASK_STATUS: COMPLETE` and `REVIEW_REQUESTED: true` -> immediately run
       `/planwise review {PLAN_PATH}` via the Task tool (mirroring
       `handlers/plan.md` Step 10's auto-review dispatch) — this MUST run exactly
       once here; do NOT also offer `/planwise plan`'s own Step 10 review gate for
       this plan, since `backlog-planner` already skips its side of that gate for
       this exact reason. Recompute the verdict from the review report's own
       Verdict section per `agents/backlog-planner.md`'s Verdict Table
       (BLOCKER > 0, or an unjustified ERROR > 0 -> NEEDS_FIXES; else ->
       APPROVED). Record the verdict in this item's Notes.
   - Proceed to Phase 6 (status -> PLANNING) when a plan file was produced,
     whether the review verdict was APPROVED or NEEDS_FIXES (per
     `backlog-planner`'s own Failure Semantics table: a `NEEDS_FIXES` verdict
     still leaves the item PLANNING — "a plan exists, unapproved" — it does not
     revert to NOT_STARTED).

---

## Phase 5: VERIFY

**After Route A (Direct Fix):**

1. Show the diff:
   ```bash
   git diff --stat
   ```
   ```bash
   git diff
   ```

2. **Self-containment grep gate (BINDING when the BB touches content-bearing artifacts):** If the diff includes any added or modified files under `.claude/rules/**`, `.claude/agents/**`, `.claude/skills/**`, `.claude/commands/**`, or `CLAUDE.md`, run the grep from [`references/artifact-self-containment.md` §4](../references/artifact-self-containment.md#4-mechanical-verification) on the changed files:

   ```bash
   grep -rnE '(LL-[0-9]{3}|BB-[0-9]{3})' {changed-content-artifact-paths}
   # MUST return zero matches.
   ```

   If matches → mark VERIFY as failing, return the grep output to the fix-agent (Route A) or open a follow-up task (Route B) requesting the cited content be inlined. Do NOT proceed to step 4 with grep hits outstanding. A BB whose diff touches ONLY bookkeeping zones (lessons index, backlog index, lesson frontmatter, BB Notes) skips this gate. See [§4.1](../references/artifact-self-containment.md#41-what-the-grep-deliberately-does-not-cover) for the exempt zones.

3. **Native-tool promotion check (BINDING when the diff touches content-bearing artifacts):** For the same changed files, check every instruction that tells an agent to run a shell command against files. If a native tool (`Read`/`Grep`/`Glob`/`Edit`) covers the same act, repoint the instruction to name the native tool call instead. A command counts as flagged only when it sits in command position — the thing an agent is told to run now, or a shell shape a template hands future agents to copy — not when the same word appears in ordinary prose or inside a legitimate pipeline. Exempt any command whose input is not a file tree (git output, a database, an interpreter, or the filesystem itself: `git`, `python`, `psql`, `yq`, `wc -l`, `mkdir`, `mv`) and any build/test/lint invocation — those are correct shell and must never be flagged.

   ```bash
   grep -nE '\b(grep|cat|sed -n|find|cd)\b' {changed-content-artifact-paths}
   # Inspect each hit in context: repoint it to the equivalent native tool call unless it
   # falls in an exempt class above, or the word appears in prose rather than as a command
   # an agent is told to run.
   ```

   If a hit needs repointing, return it to the fix-agent (Route A) or open a follow-up task (Route B) requesting the shell command be repointed. Do NOT proceed to step 4 with unrepointed hits outstanding.

<!-- AUTO-MODE: critical -->
4. Use `AskUserQuestion`:
   - **Approve** — Accept changes, mark COMPLETE
   - **Revert** — Discard changes, mark NOT_STARTED
   - **Skip** — Keep changes, don't update status

5. If Revert:
   ```bash
   git checkout -- {list of modified files}
   ```

**After Route B (Task List):**
1. Verify all tasks are marked completed
2. Show summary of changes made
<!-- AUTO-MODE: critical -->
3. Use `AskUserQuestion`: Approve (COMPLETE) or Revert (NOT_STARTED)

**After Route C (Session Planning):**
- `LARGE_SCOPE: false` items were already verified via the "After Route B" flow
  above — Route C's own step 5 routes them there directly.
- `LARGE_SCOPE: true` items: no additional verification needed here — the
  mandatory `/planwise review` pass Route C's step 5 already ran against
  `PLAN_PATH` before this phase was reached IS this branch's verification

---

## Phase 6: CLOSE

**Update backlog index status based on Phase 5 decision:**

| Outcome | Status Update |
|---------|---------------|
| Fix approved | `--status COMPLETE` |
| Fix reverted | `--status NOT_STARTED` |
| Task list completed | `--status COMPLETE` |
| Session plan created | `--status PLANNING` |
| Session planning failed (backlog-planner BLOCKED) | `--status NOT_STARTED` |
| Skipped | No change |

```bash
python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id "{item_id}" --status "{new_status}"
```

**Re-score after status changes** (skip if outcome was "Skipped" — nothing changed):

```bash
python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml
```

**Automatic archival:** When status is set to COMPLETE or CLOSED, `update_backlog.py` automatically:
- Moves item file(s) to the Archive/ directory within `{backlog_dir}`
- Updates index links to point to `Archive/` subfolder

**Twin-plan reconciliation (run when the outcome is COMPLETE/CLOSED):** If this item shipped deliverables that a live plan was authored to produce, retire that twin plan in the **same** closeout. A plan's status fields and its plans-index row are written only by session closeout (`/planwise run`); a plan whose deliverables were instead satisfied through this backlog route is written nowhere, so it is left live and independently runnable — and a later `/planwise run` will accept it and re-execute idempotency-unsafe steps ("append N rows", "insert at max+1", "add the next check number") against already-satisfied state, corrupting it.

> [!constraint] Retire or link the twin plan at backlog closeout
> 1. **Detect the twin.** Grep the plans index (`{plans_dir}/{plans_index}`) and the Master Plans under `{plans_dir}/**` for a plan that names the same deliverables — or targets the same files — this item just shipped.
> 2. **Reconcile it in this closeout.** For each twin found, set its Master Plan / sprint / orchestration `Status: COMPLETE (superseded — shipped via BB-{item_id} {route} {date})` and update its plans-index row — OR explicitly link the two so the plan is not independently runnable.
> 3. **If you cannot reconcile now, do not leave it silently runnable** — record the twin plan and the blocker so a later closeout retires it.
>
> WRONG — close the item, leave the twin plan alone → `/planwise run` starts it → a task step "append N rows" runs against rows that already exist → N duplicate rows, or a duplicate `## N` section colliding with the shipped one.
> CORRECT — retire/link the twin plan in the same closeout so it is no longer independently runnable.

**Print summary table:**

> [!template] Session Summary
> ```
> ID  | Feature                              | Action        | Status
> ----|--------------------------------------|---------------|--------
> 002 | Fix login redirect bug               | Direct Fix    | COMPLETE
> 001 | Setup project CI pipeline            | Plan Created  | PLANNING
> 003 | Add user profile page                | Skipped       | IN_PROGRESS
> ```

---

## Phase 7: FOLLOW-UP BLI CAPTURE

After closing all triaged items, auto-surface actionable recommendations from resolution Outputs as candidate backlog items.

### Step 7.1: Grep Resolution Outputs

Use Grep to scan resolution Outputs in `{plans_dir}/**/Outputs/` for the declarative follow-up block convention:

```
pattern: > \[!followup\]
path: {plans_dir}
output_mode: content
-A: 20
```

Identify candidate recommendations. Also check task files of recently-closed items for inline `> [!followup]` callouts (per `references/task-file-and-tracking-requirements.md` Declarative Follow-Up Block Convention).

**Field extraction:** For each `> [!followup]` callout found, parse the body lines for fields in the form:

```
- {Recommendation}: {description} (target: {file_path}; severity: {high|medium|low})
```

Extract structured fields using these patterns:

```
target pattern:   /target:\s*([^\s;)]+)/    →  Target file (in Follow-Up Candidate Block)
severity pattern: /severity:\s*(high|medium|low)/i  →  Severity (in Follow-Up Candidate Block)
```

Fallback values when fields are absent or malformed:
- `target:` absent → default `Target file` to the session's source file path
- `severity:` absent → default `Severity` to `medium`

### Step 7.2: Surface Candidates to User

Present each candidate to the user with the auto-recommendation heuristic:

> [!template] Follow-Up Candidate Block
> ```
> ─────────────────────────────────────────────
> CANDIDATE: from {Outputs/source-file.md}
> ─────────────────────────────────────────────
>
> Recommendation: {description}
> Target file: {file_path}
> Severity: {high|medium|low}
> Originating item: {BLI-NNN-..}
> ─────────────────────────────────────────────
> ```

<!-- AUTO-MODE: convenience -->
<!-- Default: skip all (do not auto-create BBs unattended; user explicitly invokes /planwise backlog to surface). -->
Use `AskUserQuestion`: "Create backlog item from this candidate?"
- Option 1: Yes — create BLI
- Option 2: No — skip
- Option 3: Edit — modify before creating
- Option 4: Yes — create item + report upstream — creates the BLI as in Option 1, then routes into `references/feedback-submission.md`'s own `critical` gate, where outward consent is actually taken. This convenience-classified site takes no consent language of its own; the skip-all default above is untouched and can never post.

### Step 7.3: Auto-Create BLI Files

> [!important] Inline the content the capture depends on
> When a backlog item's value rests on specific content — a block to promote, the evidence behind a finding, an exact spec or recipe — **paste that content into the item verbatim**. A pointer (another repo, a path, a session-only artifact) is welcome *alongside* the inlined content for context or provenance, but it must NOT be the *sole* carrier of the substance: the item must stay fully executable if that source becomes unavailable.
> - **Inline:** the verbatim text to promote, the failing command + its output, the exact before/after, the spec.
> - **Reference-only is acceptable** for: large, stable in-repo files that will still exist at execution time AND are not the unique carrier of the item's substance.
> - **Durability test:** "If the originating session or repo vanished tomorrow, could someone execute this item from the file alone?" If no, inline more.
>
> This is a different concern from shipped-artifact self-containment (`references/artifact-self-containment.md`, which strips internal identifiers out of distributed artifacts) — here the goal is that the capture itself carries its own substance.

For the accepted candidate set — the gate below applies per candidate, the routing decision after it applies to the set as a whole:

> [!important] Pre-filing re-verification gate (before any file is written)
> For each candidate, re-prove the condition it asserts against the live repository, per `references/verify-backlog-citation-freshness.md` §10. Candidates sourced from a plan's out-of-scope table, an audit's findings, or a prior session's deferred-work section carry their source's authoring date, not today's state. A candidate whose condition no longer holds is not filed — it is reported with the evidence that retired it, and the source document is reconciled per §10.4.

> [!decide] Delegate the batch, or file inline
> | Accepted candidates | Path |
> |---|---|
> | **N ≥ 2** | Dispatch `backlog-author` once (below), then render Step 7.4 from its status block |
> | **N = 1** | File inline via steps 1-4 below — a single item does not repay a subagent's startup and re-read cost |
>
> The accept/skip decision in Step 7.2 has already happened and stays in this session: the interactive question tool does not exist in a spawned context. Dispatch carries only accepted candidates.

**Delegated path (N ≥ 2)** — dispatch [`agents/backlog-author.md`](../agents/backlog-author.md) via the Task tool:

```
Task {
  subagent_type: "planwise:backlog-author"
  description: "File {N} follow-up backlog items from {item-id} resolution"
  prompt: |
    File the following accepted candidates as backlog items.

    plugin_root:    {plugin_root}
    planwise_root:  {planwise_root}
    backlog_dir:    {backlog_dir}
    Candidates:     {one block per candidate: description, target file, severity, originating item}
    Source docs:    {paths this session already read, for SOURCE_PINS comparison}

    Run the pre-filing re-verification gate on every candidate before writing
    anything. Do not file a candidate whose condition no longer holds — return
    it under ITEMS_RETIRED with the evidence that retired it.
}
```

> [!constraint] One dispatch, never a fan-out
> `backlog-author` owns the backlog index write. Two concurrent dispatches race on the index file and on `parse_backlog.py --next-id`, which computes next-free from live state. Batch every accepted candidate into **one** dispatch. Dispatch **foreground only** — a background subagent silently auto-denies its own Write/Edit/Bash calls, and permission-bypass modes do not override that gate.

**Result handling:** render Step 7.4 from the returned status block. `ITEMS_FILED < CANDIDATES_IN` is a valid COMPLETE — name each retirement and its evidence in the summary. Reconcile each source document listed under `SOURCE_RECONCILE` per `references/verify-backlog-citation-freshness.md` §10.4; the agent does not touch those files. If `SOURCE_PINS` shows a source file whose line count differs from this session's own read, re-read it before trusting the item drafted from it.

**Inline path (N = 1)** — steps 1-4:

1. **Get next BLI ID:**
   ```bash
   python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml --next-id
   ```

2. **Create BLI file** at `{backlog_dir}/BLI-{NNN}-{Domain}-{Topic}.md` using the [backlog-item.md](../templates/backlog-item.md) template; pre-fill:
   - Title from recommendation
   - `created:` today's date
   - `status: NOT_STARTED`
   - Body from candidate description + target file + severity
   - **Self-containment check:** the body inlines every block, spec, or piece of evidence the item depends on — a reference may add context, but the substantive content required to act is pasted in, not only linked. (Apply the durability test above.)

3. **Append row to backlog index:**
   ```bash
   python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --create --id "{NNN}" --feature "{recommendation}" --priority "{inferred from severity}" --abbrev "{Domain}" --files "BLI-{NNN}-{Domain}-{Topic}.md"
   ```

4. **Re-score backlog** after all candidates processed:
   ```bash
   python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml
   ```

### Step 7.4: Output Summary

```
PHASE 7 — FOLLOW-UP BLIs CAPTURED

Candidates surfaced: {N}
BLIs created: {M}
Skipped: {N - M}

New BLI IDs: BLI-{NNN}, BLI-{NNN+1}, ...
```

When the number of items filed differs from the number of candidates surfaced, name each candidate that was retired rather than filed, with the evidence that retired it (from the Step 7.3 pre-filing gate) — a silent count difference is indistinguishable from a dropped candidate.

---

## Phase 8: LESSON CAPTURE

After closing all triaged items, prompt for lessons learned.

<!-- AUTO-MODE: convenience -->
<!-- Default: No. -->
**Ask the user:** "Were any lessons learned during this triage session? (y/n)"

**If no:** Skip this phase and finish.

**If yes:** Read `{lessons_dir}/{lessons_index}` for the lesson file template and the next available lesson number. Create a lesson file at `{lessons_dir}/LL-{NNN}-{Domain}-{Name}.md` and add a row to the master table in the lessons index.

### Backlog Lesson Categories

| Category | When to Capture | Example |
|----------|-----------------|---------|
| `triage-routing` | Routing decision was non-obvious | "Item appeared simple but required planning due to cross-cutting dependencies" |
| `scope-assessment` | Scope signals were misleading | "Bug keyword but actual issue was architectural" |
| `resolution-outcome` | Fix succeeded or failed in a noteworthy way | "Direct fix worked but revealed a related issue" |

---

## Routing Decision Tree

> [!practice] Route by What the Defect Needs
> Pick the route that fully resolves the item, not the cheapest one to execute — a session-sized fix gets Route C, never a quick patch that leaves known incoherence behind. Full principle and exception clause: [do-the-hard-things.md](../references/do-the-hard-things.md).

Use this logic to determine the recommended route in Phase 3.

### Scope Assessment Signals

| Signal | How to Detect | Weight |
|--------|---------------|--------|
| Item predates active work in its own domain, or is cohort-shaped (siblings by period/abbrev/`blocks:`) | Pivot check per `references/backlog-triage-pivot-detection.md` | Gate → run before any routing weight is assigned |
| "Bug" in feature name | Case-insensitive check on Feature column | Strong → Direct Fix |
| Item file < 50 lines | Line count on read | Moderate → Direct Fix (a *proxy* for a small fix — a file that is long only because it is thoroughly documented is NOT large scope) |
| Exact fix evidence: named files + line anchors + before/after content + scope-confinement bound | BB body supplies concrete, bounded edit targets | Strong → Direct Fix — sets `HAS_CLEAR_FIX` regardless of file length |
| Specific file paths mentioned | Regex for code file extensions | Moderate → Direct Fix |
| "multi-sprint" / "phased" keywords | Case-insensitive content search | Strong → Session Planning |
| "refactor" / "redesign" / "architecture" / "migration" | Content keywords | Strong → Session Planning |
| 6+ sub-items or ## headings | Count numbered list items and H2 headers | Moderate → Session Planning |
| Multiple reference files (YY > 01) | Files column has 2+ links | Moderate → Session Planning |
| 3-5 numbered steps | Count discrete steps | Moderate → Task List |

### Decision Logic

```
1. Read item file(s)
2. Compute signals.
   HAS_CLEAR_FIX is true when EITHER the item is short (< 50 lines) OR the BB
   supplies exact fix evidence — named files, line anchors, before/after content,
   and an explicit scope-confinement bound ("do NOT touch X"). Route on the
   *measured* edit scope, never on file length alone: a BB that is long only
   because it is thoroughly documented still has a clear, surgical fix.

0.  Pivot check (High-priority / top-scoring / aged items only).
    IF pivot confirmed -> COHORT SWEEP: batch BLOCKED transition, shared rationale. Do NOT route.

0.5 Existence-premise probe (re-alignment-verb items only).
    IF premise fails (bare target + all variants absent) -> SURFACE: commit probe evidence,
    route the scope decision to the user. Do NOT route to Direct Fix, regardless of edit size.

IF HAS_CLEAR_FIX AND NOT (IS_ARCHITECTURAL OR HAS_MULTI_SPRINT OR SUB_ITEMS >= 6):
    -> DIRECT FIX (Route A)          # IS_BUG strengthens this signal but is not required

ELIF HAS_MULTI_SPRINT OR IS_ARCHITECTURAL OR (SUB_ITEMS >= 6):
    -> SESSION PLANNING (Route C), LARGE_SCOPE = true

ELIF 2 <= STEP_COUNT <= 5:
    -> TASK LIST (Route B)

ELSE:
    -> SESSION PLANNING (Route C) [conservative default], LARGE_SCOPE = false

3. Present recommendation via AskUserQuestion (include LARGE_SCOPE in the Scope
   Assessment Block when Route = SESSION_PLANNING)
4. User can override to any route or skip. If the user overrides TO Route C from a
   different recommended route, LARGE_SCOPE defaults to false (a manual override is,
   by construction, not a signal-driven large-scope match) unless the strong-signal
   conditions above independently hold.
```
