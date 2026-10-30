# Handler: /planwise backlog

**Purpose:** Parse the project backlog index, let the user select items, assess scope, route each item to the right action (direct fix, task list, or session planning), and update status.

**Arguments:**
- No args — interactive selection
- `$1` = item ID — direct item selection (e.g., `/planwise backlog 002`)
- `--priority High` — filter by priority
- `--abbrev APP` — filter by domain abbreviation
- `--status IN_PROGRESS` — filter by status
- `--no-check` — skip both Phase 1 item-file audits, archival drift and body status lines (fast triage)
- `--loop-resume <run-id>` — re-enter a loop run after the hooks module compacts the session; skips the loop questions and processes exactly one item
- `--answer [item-id]` — answer open questions; see `handlers/backlog-Part-3-Answers.md`

Loop mode is offered by Q1 on every interactive no-args run.

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

The optional top-level `id_format` key (`prefixed` or `bare`) controls how a newly created item's ID is rendered in the index's canonical stored form. When the key is absent, the index's predominant form is inferred. Any other value falls back to `bare` and `update_backlog.py --create` prints a stderr `WARNING: unrecognized id_format …` naming the offending value and the accepted set. That warning is deliberately non-fatal — the item is still created — and, like the generator's own stderr warnings in Phase 1, it MUST be surfaced to the user verbatim rather than swallowed.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`, `native-tool-use.md`, `feedback-drafting.md`) are pre-injected by SKILL.md.

**Conditional references:**
- Loaded at Phase 3, step 3a (pivot check), for High-priority / top-scored / aged items or multi-item cohorts: Read `references/backlog-triage-pivot-detection.md`
- Loaded at Phase 3 beside the existence-premise probe and the already-satisfied check, for any item whose Proposed Solution adds a mechanism to a failing system or names a cause from one observed instance: Read `references/verify-cause-before-remedy.md` — count the population before diagnosing, read both writers, and check whether the failure was measured with the proposed remedy already in force
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`
- If resolving a backlog item that touches task files: Read `references/task-content-fidelity.md`
- If resolving a BLI cluster (≥ 2 BLIs same Surfaced by + created): Read `references/verify-against-shipped-artifact.md`
- For the backlog index format, item file schema, scoring formula, script interfaces, status flow, or error handling: Read `references/backlog-schema.md`
- For Auto Mode behavior (how a step behaves when `AskUserQuestion` cannot be answered non-interactively): Read `references/auto-mode-policy.md`
- In loop mode, or on `--loop-resume`: Read `handlers/backlog-Part-2-LoopMode.md`
- With `--answer`: Read `handlers/backlog-Part-3-Answers.md`
- When filing or refining items: Read `references/backlog-creation-process.md`

---

## Phase 1: FETCH

> [!gate] Index shape gate — run first, before any write: run `index_shape_preflight.py` as [`index-shape-gate.md`](../references/index-shape-gate.md) directs <!-- AUTO-MODE: critical -->

**Check the generated index against item frontmatter, then parse it:**

```bash
python {plugin_root}/scripts/generate_backlog_index.py --config {planwise_root}/config.yaml --check
python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml
```

- `--check` computes each Score cell the same way `--write` would (8 configurable factors, weights from `config.yaml`, a blocker bonus per blocked item) — there is no separate scoring call. Exit `0` is clean. Exit `1` names drift or an anomaly on stderr; a `stale-score` report alone never causes exit `1` and needs no action. Exit `2` means the generator refused an item file it cannot render — a missing required key, an unresolvable `blocks:` id, a row whose token budget cannot be met — **or a hand-authored (legacy) index**. Show the `Error:` line on stderr to the user verbatim, and stop before ranking: the index cannot be trusted until the named item file is fixed.
  - If it prints a stderr `Warning: N title(s) truncated to 120 chars (items: …)` line or an `Anomaly: …` line, surface it to the user verbatim. An `Anomaly:` line means the displayed ranking may not match what the item files actually say. The truncation warning is one line per run that lists every affected item id. The full title stays in the item file, and only the index row is shortened.

- If the exit-2 `Error:` line contains `hand-authored index`, the Index shape gate above was bypassed. Print that line verbatim, run the gate (it runs the `/planwise upgrade` migration, with backups), and STOP unless the user migrates — do not proceed to Phase 2 while the index is hand-authored.
- If the exit-2 `Error:` line says the index has an `unrecognized index shape`, `/planwise upgrade` will not migrate it either. Print that line to the user verbatim, point them at the `migrate_backlog_index.py --config {planwise_root}/config.yaml --report` command it names to see why, and STOP.
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

This audit is narrower than `--check` above and does not overlap it. `--check` renders each row from wherever an item's file sits, so it never flags an unmoved file. It cannot catch a COMPLETE/CLOSED item whose file never moved into `Archive/`. `update_backlog.py` makes that move at the status transition (Phase 6), but an item that reaches a closed status another way (a closeout that hand-edits the frontmatter) leaves the file stranded in the top-level backlog dir. This audit reads each item file's frontmatter status and location, never the index, so it sees a stranded file on a generated index too.

**`--no-check` skips this archival audit and the body-status audit below.** The `--check` call above is unconditional.

**If `--no-check` is present:** skip this step and the body-status step below (a fast triage), and go straight to displaying the table.

Otherwise, run the index-drift audit procedure in [`references/index-drift-audit.md`](../references/index-drift-audit.md) against the **backlog** index (`reconcile_backlog.py`, banner `planwise backlog — backlog index archival drift audit`) — the JSON shape, banner format, and write-on-consent reconcile flow (including the consent prompt) all live there. This is the read-side counterpart of `/planwise list` Step 2's plans-index drift check, and the same detect pass `/planwise doctor` Stage 12 reuses.

The consented `--write` moves item files into `Archive/` and never writes the index. If it moved a file, run `generate_backlog_index.py --config {planwise_root}/config.yaml --write` so the index links follow the moved files. Then re-run Phase 1's parse so this same invocation shows the regenerated index. The generator refuses a hand-authored index on its own; a refusal here means Phase 1's Index shape gate was bypassed — run it.

**Detect body status lines (always-on unless `--no-check`):**

This pass audits what an item file says, not where the file sits. An older item writer can leave a `**Status:**` line under an item's title, a second copy of the frontmatter `status:` that nothing keeps in sync. A file in the right place can still carry it, so neither `--check` nor the archival audit sees it.

```bash
python {plugin_root}/scripts/reconcile_backlog.py --config {planwise_root}/config.yaml --body-status --json
```

Run the index-drift audit procedure in [`references/index-drift-audit.md`](../references/index-drift-audit.md) with the body-status binding (banner `planwise backlog — backlog item body-status drift audit`). The [Backlog item body status](../references/index-drift-audit.md#backlog-item-body-status--reconcile_backlogpy---body-status) binding carries the detect flow, the anomaly classes, the consent prompt and the `--body-status --write` run. This is the same detect pass `/planwise doctor` Stage 19 runs. A consented strip changes no frontmatter, so no index regeneration follows it.

**On `--loop-resume`:** skip both drift audits above (they ran once at init). The `--check` call and the parse still run.

Display the table to the user.

---

## Phase 2: SELECT

**If `$1` was provided** (an item ID):
- Use that item ID directly — skip the selection prompt
- Read the JSON temp file to get the full item data
- **Held-item notice:** if the item's `status` is `BLOCKED`, the direct-ID path bypasses the table's own hold filtering entirely, so check this explicitly. Surface the hold and, before proceeding to Phase 3, use `AskUserQuestion` to confirm: "Item {item_id} is BLOCKED. Triage it anyway?" (Yes — proceed / No — leave at BLOCKED). Do NOT route silently past a hold just because it was requested by ID.

**If no arguments:**
- Present the table from Phase 1 (only selectable items — blocked items are excluded)
<!-- AUTO-MODE: convenience if $1 provided (use that item ID); critical if interactive (gate on user selection). -->
- Use `AskUserQuestion` to ask: "Which items would you like to triage?"
  - Provide the first 4 item IDs as options (highest priority from selectable items)
  - User can select one or more, or type a custom ID
  - Do NOT offer blocked items — they cannot be worked until their blockers are resolved

**Loop questions (interactive, no `$1`, not `--loop-resume`).** Read `handlers/backlog-Part-2-LoopMode.md` § The three questions for the wording. Ask Q1 first, then Q2, then Q3 in `specific` mode only. Then run `backlog_loop.py --init`.
<!-- AUTO-MODE: convenience -->
<!-- Default: per references/auto-mode-policy.md § Inference Defaults, row "Loop opt-in (backlog.md Phase 2 Q1)". -->
- Q1 — loop through the backlog this run? (default: No, single session)
<!-- AUTO-MODE: convenience -->
<!-- Default: per references/auto-mode-policy.md § Inference Defaults, row "Loop mode / count (backlog.md Phase 2 Q2)". -->
- Q2 — which items should the loop cover? (all / specific / top N)

**On `--loop-resume`:** ask nothing. Run `backlog_loop.py --next --run {run-id}` and read its JSON line. Exit 3 means a halted item, so follow Part 2 § Resume model. Exit 2 means the run file is gone, so continue as a normal single-item run.

**For each selected item**, update status to IN_PROGRESS. After the last one, regenerate the index once:

```bash
python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id "{item_id}" --status IN_PROGRESS   # loop, once per item
python {plugin_root}/scripts/generate_backlog_index.py --config {planwise_root}/config.yaml --write                        # once, after the loop
```

In loop mode only the one popped item is set IN_PROGRESS. After that write, run `python {plugin_root}/scripts/backlog_loop.py --config {planwise_root}/config.yaml --mark --phase selected --run {run-id} --id {item_id}`. When `--next` reported disposition `refine`, run Part 2 § Refine step before Phase 3.

`--status` writes frontmatter only; a non-zero `--write` exit does not undo it — fix what it names and re-run `--write`. The generator refuses a hand-authored index on its own; a refusal here means Phase 1's Index shape gate was bypassed — run it.

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
   > - [ ] For every pinned sequential identifier the item cites (Check NNN, [`references/error-pattern-catalog.md`](../references/error-pattern-catalog.md) row N, reference §N.N), re-derive the next-free value from the live target with `python {plugin_root}/scripts/resolve_anchor.py --file {target} --scheme heading-toplevel\|heading-sub\|table-row [--prefix "9.B."] --json`, then renumber the item's deliverables and self-references to match. Add `--claim {item_id}` whenever a sibling item may insert into the same space — the ledger makes a second concurrent caller return one higher instead of the same number, and the claim releases itself once the anchor is in the file. The script's relocation-redirect warning is advisory and must not be ignored: a section family that moved to another file needs the redirect table read, not a higher number
   > - [ ] For every `file:line` anchor, re-locate the symbol by content grep; treat the cited line number as a cost hint only
   > - [ ] For every acceptance criterion, run the cheapest proof it is still unsatisfied before writing a fix; mark any already-satisfied criterion "already satisfied — verified"
   > - [ ] For every pre-drafted note/callout that asserts "test/section/function X does Y", verify against the live file and re-word to name the artifact that actually carries the behavior

5. **Staleness check:** If the item has measurable acceptance criteria (counts, percentages, coverage targets), run `{build_command}` (from config.yaml `build_commands.default`) *before* routing. If criteria are already met or nearly met, present a "Close as COMPLETE" option instead of routing through a fix workflow. In loop mode, when every criterion is already met, close the item without asking per Part 2 § Unattended close; when any criterion is unmet, continue to step 6.
   - If the BLI's motivating driver is a runtime symptom (keywords: collision, race, hang, missing endpoint, intermittent), run a `grep -rn` for the symptom in `src/` and cross-check against recent session summaries in `Plans/**/Sessions/**/Outputs/`. If the driver is no longer active (no recent matches, fix landed), mark the BLI as STALE per `verify-backlog-citation-freshness.md §3h` and skip routing. Include §3h.untested-axes and §3h.cluster signal checks per the same reference.

6. **Assess the item's scope: run the mechanical signals, then reconcile the stored hint.** The [Routing Decision Tree](#routing-decision-tree) below is the source of the logic; the script applies it without modification.

   a. Run the mechanical half of the routing signals. The script reads the index row and the item body it already loaded for scoring, applies the Decision Logic, and writes nothing:
      ```bash
      python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml --route --id {item_id}
      ```
      It prints the signal vector (`abbrev`/`is_bug`, whole-file line count, keyword hits with the line each sits on, `##` and numbered-step counts, file count, the `HAS_CLEAR_FIX` evidence shapes), the provisional route, `LARGE_SCOPE`, and the Decision Logic branch that fired. Read the keyword hit lines before accepting `HAS_MULTI_SPRINT` or `IS_ARCHITECTURAL`: an item that quotes the signal table, or names a plan whose title contains "redesign", matches every keyword without being either. `IS_ARCHITECTURAL` reads only the `## Proposed Solution` section when the item has one (an item without that heading is read whole), and inside it drops a stem that sits inside a file name, a multi-segment path, a snake_case identifier, an `**Evidence:**` line or a table row. Every dropped hit is listed under `ignored (N)` with its reason, so a stem in the title, the Summary or a Related line still shows there. A plain-prose hit that remains is still a candidate, so read its line. `HAS_CLEAR_FIX` is reported as its mechanical half only — the evidence shapes are *present*; whether they are *sufficient* is your judgment. The script never runs the pivot check or gates 3b, 4 and 5. It computes gate 7's verdict as the `scoped_rules` block, which step 7 reads.
   b. Read the item's `route_hint` / `route_evidence` / `route_dated` frontmatter when present. The report prints them beside the computed route with a verdict: `agree`, `agree — but the hint predates the item's newest evidence`, `undecided — …`, or `script wins — …`.
   c. Reconcile the two into one recommendation, and state the reconciliation in the Scope Assessment Block's `Reason:` line rather than in a new template:
      - Script and hint agree → recommend that route and note that both agreed.
      - `undecided` → the hint is fresh and names a route that your own reading of the candidate signals could reach. The script flags `IS_ARCHITECTURAL`, `HAS_MULTI_SPRINT` or the sufficiency half of `HAS_CLEAR_FIX`, and the verdict line lists which one the divergence turns on. **You decide.** Read the printed hit lines and the clear-fix evidence, choose the hint's route or the script's, and state the choice and the lines you read in `Reason:`.
      - They disagree and the verdict is `script wins`, or `route_dated` is older than the item's newest `**Evidence:**` / `recorded` date → **the script wins**, and `Reason:` names the divergence. This covers a stale hint, a hint that is not `A`, `B` or `C`, and a disagreement that no reading of a candidate signal reaches: abbrev, line count, file count, sub-item count or step count. A stale hint is data about drift, not an override.
      - No hint → the script vector alone.

      Never adopt a stored hint bare, and never skip a gate because a route is already stored: a stored route is a dated claim about the repository and rots like every other claim.
   In loop mode, re-run `--route --id` anyway and note any divergence from the run's `route_at_init` in `Reason:`.
   d. Override the script's route only on a signal it cannot see — a keyword hit you read and classified as self-quotation, edit evidence you judged insufficient, a `##` count inflated by appended coordination flags — and name that signal in `Reason:`. Carry the script's `LARGE_SCOPE` forward unchanged when the route stays C.

<!-- AUTO-MODE: critical — discharged by auto-escalation, not by a prompt. See step 7's Auto Mode paragraph. -->
7. **Scoped-rule pre-delegation check (`verify-against-shipped-artifact.md` §3g):** Read the `scoped_rules` block that step 6a's `--route --id` report printed. The script took the item's destinations from its `## Files Touched` table (Role `EDIT` or `CREATE`), or, when the item has no table, from the path-like tokens in its body, and matched each one against the frontmatter `paths:` of every rule under `.claude/rules/`. The block ends in one of three verdicts:

   | Verdict | Meaning | What to do |
   |---|---|---|
   | `none` | No rule scopes any destination | Continue to step 8 |
   | `inject` | One or more rules scope a destination, and every one of them is a behaviour rule, or the destination is an edit in place | Continue to step 8. Carry `rules_to_inject` into the Route A spawn prompt's `Scoped rules` field in the form the block's `inject_form` names: `content` pastes each listed rule file (their sizes total at most 8 KiB), `paths` lists each file's absolute path with an instruction to read it before the first edit (both forms per `references/agent-orchestration-delegated.md` §1.6). Route A VERIFY still runs the self-containment grep on any content-tree diff |
   | `placement` | The item would create a file under a rule that declares `placement: true`, or under `.claude/rules/`, `.claude/agents/`, `.claude/skills/` or `.claude/commands/`, and no archived lesson owns the item | Interactive: present the warning below and ask whether the destination is right before delegating. Auto Mode: see the paragraph below. Loop mode: a documented skip (Part 2 § Documented skip) |

   > **Placement decision needed:** destination `{path}` would be created under `{rule-file or content tree}`. Confirm the file belongs there before delegating.

   **Promotion exemption.** An item is exempt from the `placement` verdict, for every destination, when an archived lesson names it in `promoted-to:` and that lesson's `promotion-target:` includes `rule`. The script finds the owning lessons under `{lessons_dir}` and `{lessons_dir}/Archive` and reports them in the block; `promote-batch` already decided the placement of such an item, and its existing-rule check chose between extending a rule and writing a new one. The exemption covers any destination tree, a rule file or a reference alike.

   This gate applies regardless of route (Route A or Route B) — do not skip it. The verdict is the script's; override it only on a signal the script cannot see, and name that signal in `Reason:`.

   **Auto Mode.** This is a human-judgment gate, so it is classified `critical`. It issues no `AskUserQuestion`: under automation an item with a `placement` verdict **auto-escalates to Route C**, which under automation writes the `needs_plan: true` marker and skips (see Route C below). An `inject` or `none` verdict proceeds with no prompt.

   In loop mode a `placement` verdict is a documented skip, never an escalation to Route C.

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
> Reason: {the Decision Logic branch --route fired; the route_hint verdict (agree / undecided / script wins / none); any signal overridden per step 6d}
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
<!-- Default: per references/auto-mode-policy.md § Inference Defaults, row "Triage route confirmation (backlog.md Phase 4)". -->
**Use `AskUserQuestion` to confirm the routing:**
- Option 1: Recommended route (from Phase 3 assessment)
- Option 2: Alternative route
- Option 3: Skip this item

**In loop mode:** ask nothing. Take the recommended route when it is A or B. A Route C result is a documented skip (Part 2 § Documented skip) that also writes the marker: `--mark --outcome SKIPPED --needs-plan` with a `--decision` text that starts `LOOP: re-assessed to Route C`. Before the Route A or B dispatch, run `backlog_loop.py --mark --phase acting --run {run-id} --id {item_id}`. Every other decision point follows Part 2 § No questions after setup. A refined item never reaches the default Route C branch; a `needs_plan` item is skipped per the marker rule.

### Route A: Direct Fix (fix-agent delegation)

For bugs and targeted fixes with clear scope:

**Pre-spawn: extract cross-cutting audit candidates (`verify-backlog-citation-freshness.md` §3i):** Before building the spawn prompt, read the BLI file and look for sections named `Cross-cutting check`, `Cross-cutting consideration`, or `Notes`. Extract any cross-cutting items listed there to include in the spawn prompt. If none are found, use `"none identified"`.

Delegate to the `fix-agent` via the Agent tool:

```
Task {
  subagent_type: "planwise:fix-agent"
  run_in_background: false
  description: "Fix backlog item {item-id}: {item-summary}"
  prompt: |
    Fix the following backlog item:

    Item ID: {item-id}
    Summary: {item-summary}
    Description: {item-description}
    Affected files: {file-list}
    Build command: {build-command-from-config}
    Scoped rules (content to honour): {per the scoped_rules block's inject_form: "content" = the content of each file in rules_to_inject; "paths" = each file's absolute path with "Read each one before your first edit"; or "none"}
    Cross-cutting audit candidates (in-scope by default): {list extracted from BLI cross-cutting sections, or "none identified" if absent}
}
```

A backlog item whose deliverable edits the permission configuration is not a Route A item. See references/backlog-triage-pivot-detection.md, section "A Permission-Change Deliverable Is Not Agent-Executable".

**Result handling:**
- If fix-agent returns status FIXED → proceed to Phase 5 (verify + approve)
- If fix-agent returns status BLOCKED → report blocker to user, offer to route to Session Planning (Route C)

### Route B: Task List

For medium-scope items with 2-5 discrete steps:

1. Analyze the backlog item file to extract discrete steps
2. **(Track B)** When `TaskCreate` is in your tool list: run `TaskList` first, then `TaskCreate` one task per step with subject `[{item-id}-{n}] {step}`. Mark each `in_progress` when you start it and `completed` when it is done. When `TaskCreate` is absent, track the steps as a checklist in the item file and call none of the Task tools. The gate is `references/session-execution-protocol.md` §5.
3. Work through each step sequentially
4. After all steps complete, proceed to Phase 5

### Route C: Session Planning

<!-- AUTO-MODE: critical --> Step 2 below (`EnterPlanMode`) requires interactive user
consent the harness cannot obtain unattended. **If Auto Mode is active, do not run
steps 1 to 5. Mark the item as needing a planning session and skip it:** run
`python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id {item_id} --mark-needs-plan`,
which writes `needs_plan: true` into the item's frontmatter; set `--status
NOT_STARTED`; log `Auto Mode: marked for a planning session; skipping (no plan is
authored unattended)`; regenerate the index; continue to Phase 7. No planner is
dispatched. A later interactive run, or a planning hand-off that reads the marker,
authors the plan.

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

   **`LARGE_SCOPE: true`** — mark the item for a planning session. No plan is authored here:
   - Run `python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id {item_id} --mark-needs-plan`.
     It writes `needs_plan: true` into the item's frontmatter. Phase 6 sets the status.
   - Print the hand-off: "Run `/planwise plan` on this item; the plan-mode file is the
     approved approach", and name the plan-mode file's path.
   - Proceed to Phase 6 (outcome "Marked for a planning session").

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

In loop mode, before step 4 run `backlog_loop.py --mark --phase verifying --run {run-id} --id {item_id}`. Then skip step 4 and step 5: all gates passing means COMPLETE, and a failing gate is a documented skip that reverts nothing (Part 2 § No questions after setup). Verification commands are in scope, never a reason to skip (Part 2 § Verification is in scope).

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
   In loop mode, before step 3 run `backlog_loop.py --mark --phase verifying --run {run-id} --id {item_id}`. Then skip step 3: every task completed means COMPLETE, and any other state is a documented skip.
<!-- AUTO-MODE: critical -->
3. Use `AskUserQuestion`: Approve (COMPLETE) or Revert (NOT_STARTED)

**After Route C (Session Planning):**
- `LARGE_SCOPE: false` items were already verified via the "After Route B" flow
  above — Route C's own step 5 routes them there directly.
- `LARGE_SCOPE: true` items: nothing to verify; the item carries the marker.

---

## Phase 6: CLOSE

**Update backlog index status based on Phase 5 decision:**

| Outcome | Status Update |
|---------|---------------|
| Fix approved | `--status COMPLETE` |
| Fix reverted | `--status NOT_STARTED` |
| Task list completed | `--status COMPLETE` |
| Marked for a planning session | `--status NOT_STARTED`; marker already written |
| Skipped | No change |

```bash
python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id "{item_id}" --status "{new_status}"
```

**In loop mode,** after the `update_backlog.py --status` call, record the outcome with `backlog_loop.py --mark --outcome {COMPLETE|NOT_STARTED|SKIPPED} --run {run-id} --id {item_id}`. Approved or task list done maps to COMPLETE, reverted to NOT_STARTED, skipped to SKIPPED (see Part 2 § Per-iteration contract).

**Regenerate the index once after status changes** (skip if outcome was "Skipped" — nothing changed):

```bash
python {plugin_root}/scripts/generate_backlog_index.py --config {planwise_root}/config.yaml --write
```

`--write` rebuilds the whole index from every item file's frontmatter and computes the Score column itself — there is no separate re-score step. Exit `0` is clean. Exit `1` is unexpected — record it and keep going. Exit `2` means it refused and wrote nothing; the item's frontmatter is still correct, so fix what it names and re-run `--write` rather than repeating `--status`. The generator refuses a hand-authored index on its own; a refusal here means Phase 1's Index shape gate was bypassed — run it.

**Automatic archival:** When status is set to COMPLETE or CLOSED, `update_backlog.py` automatically moves the item file(s) to the Archive/ directory within `{backlog_dir}`. It no longer repoints the index link itself — the `--write` run above does that, because it renders each row from wherever the file actually lives.

**Twin-plan reconciliation (run when the outcome is COMPLETE/CLOSED):** If this item shipped deliverables that a live plan was authored to produce, retire that twin plan in the **same** closeout. Only session closeout (`/planwise run`) writes a plan's status fields, so a plan satisfied through this backlog route stays live and runnable, and a later `/planwise run` re-executes idempotency-unsafe steps ("append N rows", "insert at max+1") against already-satisfied state.

> [!constraint] Retire or link the twin plan at backlog closeout
> 1. **Detect the twin.** Grep the plans index (`{plans_dir}/{plans_index}`) and the Master Plans under `{plans_dir}/**` for a plan that names the same deliverables — or targets the same files — this item just shipped.
> 2. **Reconcile it in this closeout.** For each twin found, set its Master Plan / sprint / orchestration `Status: COMPLETE (superseded — shipped via BB-{item_id} {route} {date})` (and the Master Plan's footer date), then run `generate_plans_index.py --write` (exit 2 wrote nothing; print the `Error:` line verbatim: `hand-authored plans index` means the Phase 1 Index shape gate was bypassed, so run it; `neither a hand-authored nor a generated` means point the user at `migrate_plans_index.py --report`; `over the … -token budget` means tell the user to shard or shorten the index) — OR explicitly link the two so the plan is not independently runnable.
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
> 001 | Setup project CI pipeline            | Marked for planning | NOT_STARTED
> 003 | Add user profile page                | Skipped       | IN_PROGRESS
> ```

In loop mode this prints the one row of the session. The cross-run table comes from `--end`, which Phase 9 triggers at the last item.

---

## Phase 7: FOLLOW-UP BLI CAPTURE

After closing the triaged items of this session (one, in loop mode), auto-surface actionable recommendations from resolution Outputs as candidate backlog items.

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

**In loop mode:** ask nothing, file nothing, and print each candidate in the iteration summary. Skip the rest of Step 7.

<!-- AUTO-MODE: convenience -->
<!-- Default: per references/auto-mode-policy.md § Inference Defaults, row "Follow-up candidate filing (backlog.md Phase 7)". -->
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

For the accepted candidate set — the gate below applies per candidate, the hand-over after it applies to the set as a whole:

> [!important] Pre-filing re-verification gate (before any file is written)
> For each candidate, re-prove the condition it asserts against the live repository, per `references/verify-backlog-citation-freshness.md` §10. Candidates sourced from a plan's out-of-scope table, an audit's findings, or a prior session's deferred-work section carry their source's authoring date, not today's state. A candidate whose condition no longer holds is not filed — it is reported with the evidence that retired it, and the source document is reconciled per §10.4.

**Hand-over to the creation process.** File the accepted set (any N ≥ 1) through the filing path of [`references/backlog-creation-process.md`](../references/backlog-creation-process.md) §3, which holds the spawn-prompt shapes. Pass only accepted candidates: no spawned agent has the question tool.

1. Dispatch `backlog-preflight` once in `file` mode, one block per candidate. It runs the pre-filing re-verification gate above, so a candidate that no longer holds returns as a retirement.
2. Dispatch `backlog-planner` once per `HOLDS` block, named `planner-{id-or-label}`.
3. On a `QUESTIONS` return, ask each question with one `AskUserQuestion` call. Then send the answers with `SendMessage` to the planner's dispatch name (`references/backlog-creation-process.md` §5).
4. Dispatch `backlog-author` once in `file` mode after the last planner returns. It files the batch and regenerates the index. It sets no status: a status change runs through `update_backlog.py --status` here.

> [!constraint] One dispatch, never a fan-out
> **Never dispatch two of these agents concurrently.** The id-allocation race is the only remaining reason. `--next-id` reads the generated index files, and those change only when `generate_backlog_index.py --write` runs at the end of a dispatch. Two concurrent dispatches can therefore read the same next-free id and file two items under it. This guard can retire once id allocation stops depending on the regenerated index. Batch candidates into **one** dispatch rather than fanning out per candidate. One dispatch also costs less than several. Dispatch **foreground only** — a background subagent silently auto-denies its own Write/Edit/Bash calls, and permission-bypass modes do not override that gate.

**Result handling:** render Step 7.4 from the author's status block. `ITEMS_FILED < CANDIDATES_IN` is a valid COMPLETE — name each retirement the author lists under `ITEMS_RETIRED`, with its evidence, in the summary. Reconcile each source document listed under `SOURCE_RECONCILE` per `references/verify-backlog-citation-freshness.md` §10.4; the author does not touch those files. If the preflight's `SOURCE_PINS` shows a source file whose line count differs from this session's own read, re-read it before trusting the item drafted from it.

### Step 7.4: Output Summary

```
PHASE 7 — FOLLOW-UP BLIs CAPTURED

Candidates surfaced: {N}
BLIs created: {M}
Skipped: {N - M}

New BLI IDs: BLI-{NNN}, BLI-{NNN+1}, ...
```

Render this summary from the author's status block: `BLIs created` is its `ITEMS_FILED`. When the number of items filed differs from the number of candidates surfaced, name each candidate that was retired rather than filed, with the evidence that retired it (from the author's `ITEMS_RETIRED` lines) — a silent count difference is indistinguishable from a dropped candidate.

---

## Phase 8: LESSON CAPTURE

After closing the triaged items of this session (one, in loop mode), prompt for lessons learned.

**In loop mode:** ask nothing. Decide whether the iteration surfaced a lesson, file it when it did, and record the ids with `backlog_loop.py --mark --lessons`. Follow `handlers/backlog-Part-2-LoopMode.md` § Phase 8 in loop mode, then continue to Phase 9.

<!-- AUTO-MODE: convenience -->
<!-- Default: per references/auto-mode-policy.md § Inference Defaults, row "Lessons capture acknowledgment". -->
**Ask the user:** "Were any lessons learned during this triage session? (y/n)"

**If no:** Skip this phase; in loop mode continue to Phase 9, otherwise finish.

**If yes:** Derive the next ID with `python {plugin_root}/scripts/parse_lessons.py --config {planwise_root}/config.yaml --next-id`; take the lesson file template from `templates/lesson.md`. Create a lesson file at `{lessons_dir}/LL-{NNN}-{Domain}-{Name}.md`; run the generator; append the changelog entry.

### Backlog Lesson Categories

| Category | When to Capture | Example |
|----------|-----------------|---------|
| `triage-routing` | Routing decision was non-obvious | "Item appeared simple but required planning due to cross-cutting dependencies" |
| `scope-assessment` | Scope signals were misleading | "Bug keyword but actual issue was architectural" |
| `resolution-outcome` | Fix succeeded or failed in a noteworthy way | "Direct fix worked but revealed a related issue" |

---

## Phase 9: LOOP BOUNDARY

Loop mode only. Skip this phase in a single-session run. Run:

```bash
python {plugin_root}/scripts/backlog_loop.py --config {planwise_root}/config.yaml --boundary --run {run-id}
```

Print its stdout. Copy the line that starts `BACKLOG LOOP:` (or the JSON `marker` field) verbatim. That line MUST be the last line of the final message. Ask no question and write no sentence after it. When remaining is 0, write `Loop complete.` above it. See `handlers/backlog-Part-2-LoopMode.md` § The marker.

> [!constraint] The marker is the last line of the final message
> WRONG — a paraphrased marker, or any text after it:
> ```
> Item 004 is done, 2 items remain. Shall I continue?
> ```
> CORRECT — the verbatim `--boundary` line, last:
> ```
> BACKLOG LOOP: run=20261007-141502 done=004 remaining=2 state=C:/proj/planwise/Backlog/Backlog-Runs/20261007-141502.json
> ```

---

## Routing Decision Tree

> [!practice] Route by What the Defect Needs
> Pick the route that fully resolves the item, not the cheapest one to execute — a session-sized fix gets Route C, never a quick patch that leaves known incoherence behind. Full principle and exception clause: [do-the-hard-things.md](../references/do-the-hard-things.md).

Use this logic to determine the recommended route in Phase 3.

### Scope Assessment Signals

| Signal | How to Detect | Weight |
|--------|---------------|--------|
| Item predates active work in its own domain, or is cohort-shaped (siblings by period/abbrev/`blocks:`) | Pivot check per `references/backlog-triage-pivot-detection.md` | Gate → run before any routing weight is assigned |
| `abbrev: BUG` in frontmatter | Read the item's `abbrev` field | Strong → Direct Fix |
| Item file < 50 lines | Line count on read | Moderate → Direct Fix (a *proxy* for a small fix; length alone is never large scope) |
| Exact fix evidence: named files + line anchors + before/after content + scope-confinement bound | BB body supplies concrete, bounded edit targets | Strong → Direct Fix — sets `HAS_CLEAR_FIX` regardless of file length |
| Specific file paths mentioned | Regex for code file extensions | Moderate → Direct Fix |
| "multi-sprint" / "phased" keywords | Case-insensitive content search | Strong → Session Planning |
| "refactor" / "redesign" / "architecture" / "migration" | Content keywords in the `## Proposed Solution` section (the whole body when the item has no such section); a stem in a title, Summary, evidence line, table row or name is listed as ignored | Strong → Session Planning |
| 6+ sub-items or ## headings | Take the larger of two counts: the longest consecutive numbered list (two lists of 2 and 4 are 4 parts, not 6) and the H2 headers, excluding the backlog item template's own section headings (Summary, Problem, Proposed Solution, Acceptance Criteria, Related, Files Touched, Notes, Resolution, Verification, Open Questions, Loop Decision Needed) | Moderate → Session Planning |
| Multiple reference files (YY > 01) | Files column has 2+ links | Moderate → Session Planning |
| 2-5 numbered steps (`ROUTE_B_MIN_STEPS`..`ROUTE_B_MAX_STEPS` in `score_backlog.py`) | Count discrete steps | Moderate → Task List |
| `refined: true` and the shape gate passes (`## Resolution` with at least one numbered step, `## Verification`, no open question) | `score_backlog.py --route --id` shape block | Strong → Task List; its step count, keyword and sub-item signals are read from `## Resolution` only |
| `needs_plan: true` in frontmatter | Read the item's `needs_plan` field | Gate → Session Planning, never A or B |

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

IF NEEDS_PLAN:
    -> SESSION PLANNING (Route C), LARGE_SCOPE = true   # NEEDS_PLAN: true (marked for a planning session)

ELIF HAS_CLEAR_FIX AND NOT (IS_ARCHITECTURAL OR HAS_MULTI_SPRINT OR SUB_ITEMS >= 6):
    -> DIRECT FIX (Route A)          # IS_BUG strengthens this signal but is not required

ELIF HAS_MULTI_SPRINT OR IS_ARCHITECTURAL OR (SUB_ITEMS >= 6):
    -> SESSION PLANNING (Route C), LARGE_SCOPE = true

ELIF REFINED AND SHAPE_OK AND 1 <= STEP_COUNT <= 5:
    -> TASK LIST (Route B)           # REFINED: 1 <= STEP_COUNT <= 5 from ## Resolution

ELIF REFINED:
    -> SESSION PLANNING (Route C), LARGE_SCOPE = false   # REFINED but shape gate failed (see shape block)

ELIF 2 <= STEP_COUNT <= 5:
    -> TASK LIST (Route B)

ELSE:
    -> SESSION PLANNING (Route C) [conservative default], LARGE_SCOPE = false   # ELSE (conservative default)

3. Present recommendation via AskUserQuestion (include LARGE_SCOPE in the Scope
   Assessment Block when Route = SESSION_PLANNING)
4. User can override to any route or skip (except in loop mode, where C is not selectable). If the user overrides TO Route C from a
   different recommended route, LARGE_SCOPE defaults to false (a manual override is,
   by construction, not a signal-driven large-scope match) unless the strong-signal
   conditions above independently hold.
```

`score_backlog.py --route` implements step 2 and the `IF` / `ELIF` / `ELSE` chain above mechanically (`compute_item_shape`, `compute_route_signals` and `decide_route` in that script); Phase 3 step 6 runs it. The shape gate and the `refined` step count are read from `## Resolution`; the handler never re-derives them. `## Open Questions` feeds only the shape gate, no route signal or line count. A script that diverges from this pseudocode is defective. Steps 0 and 0.5, the sufficiency half of `HAS_CLEAR_FIX`, and steps 3-4 stay with the handler.
