# Handler: /planwise backlog — Loop Mode (Part 2)

This file is Part 2 of `handlers/backlog.md`. Read it when loop mode is active or the `--loop-resume` argument is present. It holds the full loop contract. The handler carries only short hooks that point here by heading.

---

## Purpose

**Purpose:** Triage the backlog one item per session. Each session closes one item, prints a marker line, and ends its turn. The plugin's hooks module watches for that marker, compacts the session, and re-enters `/planwise backlog --loop-resume <run-id>` with no keystroke.

Without the module the marker line prints and nothing else happens; continue by hand with `/planwise backlog --loop-resume <run-id>`.

The loop runs only in the interactive REPL. A non-interactive run ends after its first item.

---

## Run state

All loop state lives in one file per run: `{backlog_dir}/Backlog-Runs/{YYYYMMDD-HHMMSS}.json`. The run id is the file stem. The file is named by the run's start date and time and is never overwritten.

Only `scripts/backlog_loop.py` writes it. The handler never edits the file by hand. This mirrors the run-state convention in `handlers/harvest.md` Step 7: no config key, no template edit, no manifest row.

`Backlog-Runs/` holds `.json` files only. Every backlog reader lists `*.md` files at the top level of `{backlog_dir}`, so the folder is never read as an item.

The queue is frozen at `--init`. A follow-up item filed by Phase 7 during the loop is reported in the end summary and never joins the queue.

Call the script as follows. Every subcommand prints short human lines, then one final single-line JSON object that the handler reads.

```bash
python {plugin_root}/scripts/backlog_loop.py --config {planwise_root}/config.yaml --next --run {run-id}
```

---

## Eligibility

| Item state at `--init` | In the loop set? | Reason recorded |
|---|---|---|
| Selectable, `refined: false`, or refined with a failing shape gate, inside the refine cap or named by `--mode specific` | Yes, disposition `refine` | none |
| Selectable, provisional route A or B, `refined: true` or past the refine cap | Yes, disposition `run` | none |
| Selectable, `refined: false`, route C by the conservative default (`LARGE_SCOPE` false), past the refine cap | No, listed as excluded | `needs refine` |
| Selectable, route C by a strong signal (`LARGE_SCOPE` true), or `refined: true` with a passing shape gate and route C | No, listed as excluded | `plans deferred in loop mode` |
| Selectable, marked `needs_plan: true` in its frontmatter | No, listed as excluded | `marked for a planning session` |
| Selectable, still carrying a legacy `## Loop Decision Needed` section | No, listed as excluded | `decision pending` |
| Selectable, with the scoped-rule verdict `placement` | No, listed as excluded | `placement` |
| Selectable, with an unanswered question under `## Open Questions` | No, listed as excluded | `open questions unanswered` |
| Blocked by an open dependency | No | not selectable |
| Held (`BLOCKED`) or closed | No | not selectable |

Queue order is highest score first, then item id. Mode `n` keeps the first N of that order. Mode `specific` keeps the user's order and drops an ineligible id with a warning line.

Refining is opt-in. `--init --refine-max N` (default 0) queues up to N unrefined items for the refine step, highest score first. `--mode specific` refines every named unrefined item.

An open question is unanswered while its `Answer:` line is empty. It is answered once an `Answer:` line with text follows its `### Q` heading.

An item is excluded with the first reason that holds, in this order: `marked for a planning session`, `decision pending`, `placement`, then the others. A `decision pending` exclusion adds one hint line: fold the legacy sections with `backlog_questions.py --fold`, then answer each question. These checks only read the item.

`--init --dry-run` prints the same report and writes no run file.

An empty queue is an error. `--init` exits 1, prints a JSON line with an `error` key, and writes no run file. A dry run with an empty queue also exits 1. Tell the user and continue as a normal single-item run with Q1 not asked.

`--status` alone is the status subcommand. Combined with `--init`, `--status` is a status filter for the queue.

---

## Per-iteration contract

Each session handles exactly one item. The numbered steps run in order.

1. Phase 1 FETCH. On `--loop-resume`, skip the two drift audits. They ran once at init. `generate_backlog_index.py --check` and `parse_backlog.py` still run.
2. Phase 2. On a fresh run, ask the three questions and run `--init`. On `--loop-resume`, ask nothing. Both paths then run `--next --run {run-id}` and read its JSON line.
3. `--next` exits 3 when the current item died mid-work. Follow the Resume model section below.
4. `{"next": null, ...}` means the queue is empty. Run `--boundary` and finish at Phase 9.
5. Set only the popped item IN_PROGRESS, regenerate the index, then run `--mark --phase selected --run {run-id} --id {item-id}`.

   5a. When `--next` reported disposition `refine`, run § Refine step before Phase 3. An item with disposition `run` skips it.
6. Phase 3 RESOLVE. Re-run `score_backlog.py --route --id {item-id}` and note any divergence from `route_at_init` in `Reason:`.
7. Phase 4 ACT. Ask nothing. Take the recommended route when it is A or B. A Route C result is a documented skip (see § No questions after setup). Run `--mark --phase acting --run {run-id} --id {item-id}` before the Route A or B dispatch.
8. Phase 5 VERIFY. Run `--mark --phase verifying --run {run-id} --id {item-id}` before the gates. Ask nothing. After the gates, run the `build_commands.verify` list (§ Verification is in scope). Apply the Phase 5 default in § No questions after setup.
9. Phase 6 CLOSE. Map the outcome and run `--mark --outcome`:

   | Phase 5 or Phase 4 result | Outcome |
   |---|---|
   | Every gate passed, or task list done | `COMPLETE`, with no `--resolution-file`; a worked item is never an unattended close |
   | Every acceptance criterion already met (Phase 3 step 5) | `COMPLETE`, with `--resolution-file` (§ Unattended close); Phases 4 and 5 are skipped for the item |
   | A decision is needed, or a gate failed | `SKIPPED`, with `--decision` |
   | Route C re-assessed in Phase 4 | `SKIPPED`, with `--needs-plan` and `--decision` |
   | Halted item skipped at the HALT question | `SKIPPED`, with `--note halted-mid-item` |
   | Refine step returned `QUESTIONS` (§ Refine step) | `SKIPPED`, with `--note "open questions"` |
   | Refine step returned `DECOMPOSE` | `SKIPPED`, with `--note "decomposed: {ids}"` |
   | Refine step returned `NEEDS_PLAN` | `SKIPPED`, with `--note "needs plan"` |
   | Refine step returned `ALREADY_MET` | `COMPLETE`, with `--note "already met"` |
   | Refine step ended on an agent `BLOCKED` or `PARTIAL` | `SKIPPED`, with `--note "refine blocked: {agent}: {reason}"` |

   A `SKIPPED` outcome restores the item's pre-loop status. When the script prints `Restored`, regenerate the backlog index.
10. Phases 7 and 8 run every iteration, for the one item of the session. Both ask nothing.
11. Phase 9 LOOP BOUNDARY. Run `--boundary` and end the turn on the marker.

---

## Refine step

**Purpose:** Turn an unrefined item into one the loop can run, before Phase 3. The step runs when `--next` reported disposition `refine`. An item with `disposition: run` skips this section.

The refine step asks nothing. A `QUESTIONS` design is written into the item. In loop mode the question round-trip of `references/backlog-creation-process.md` does not run.

Use this hand-over directory for the item's fact sheet and design file:

```
{backlog_dir}/Backlog-Runs/{run-id}-refine/{item-id}/
```

Make three dispatches, in the foreground and one at a time. `references/backlog-creation-process.md` § 3 and § 4 carry each spawn-prompt shape. Do not restate the shapes here.

1. Dispatch `planwise:backlog-preflight` once, in `refine` mode, with the item id. Read the `DISPOSITIONS` field of its status block.
2. For a `HOLDS` sheet, dispatch `planwise:backlog-planner` under the name `planner-{item-id}`. Read the `DESIGN` field of its status block. An `ALREADY_MET` sheet skips the planner and goes straight to the author.
3. Dispatch `planwise:backlog-author` once, in `refine` mode, with the sheet and the design file. It edits the item in place and reports `ITEMS_REWRITTEN`, `ITEMS_ALREADY_MET` and `ITEMS_RETIRED`.

An item that still holds a legacy `## Loop Decision Needed` section never reaches the refine step. `--init` excludes it as `decision pending`, and `--mode specific` drops it with a warning. Fold its question into `## Open Questions` with `backlog_questions.py --fold`, then answer it with `/planwise backlog --answer`.

Then map the result to the loop action:

| Planner or preflight result | Loop action |
|---|---|
| `REFINED` | `--mark --refined REFINED`. Regenerate the index. Re-run `score_backlog.py --route --id {item-id}`. Continue at Phase 3 in the same iteration |
| `QUESTIONS` | `--mark --refined QUESTIONS`. Run `--mark --outcome SKIPPED --note "open questions"`. Regenerate the index. Continue to Phase 7 |
| `ALREADY_MET` | The author writes the close record. Run `update_backlog.py --status COMPLETE`, then regenerate the index. Run `--mark --refined ALREADY_MET`, then `--mark --outcome COMPLETE --note "already met"` |
| `DECOMPOSE` | The author files the sub-items with `blocks: [{parent}]`. Run `--mark --refined DECOMPOSE --sub-items {ids}`, then `--mark --outcome SKIPPED --note "decomposed: {ids}"`. Regenerate the index |
| `NEEDS_PLAN` | The author writes `needs_plan: true`. Run `--mark --refined NEEDS_PLAN`, then `--mark --outcome SKIPPED --note "needs plan"`. Regenerate the index |
| `RESOLVED` or `DUPLICATE` (refine path) | The author writes one `### Q` block that proposes CLOSED, with the evidence. Run `--mark --refined QUESTIONS`, then skip as for `QUESTIONS`. The loop never sets CLOSED unattended |
| `PREMISE_FAILS` (refine path) | The author writes one `### Q` block that states the absent target and the options re-target, retire and keep. Run `--mark --refined QUESTIONS`, then `--mark --outcome SKIPPED --note "open questions"`. Regenerate the index |
| Any of the three agents returns `BLOCKED` or `PARTIAL` | Resume the same agent once, naming the missing piece. On a second `BLOCKED` or `PARTIAL`, record no refine outcome. Run `--mark --outcome SKIPPED --note "refine blocked: {agent}: {reason}"`. The item stays `refined: false` and is eligible on the next run |
| `--next` reported `disposition: run` | No refine step. Continue at Phase 3. The item carries no `refine` record, and the end summary's `Refine` column shows `-` |

A refine skip uses `--note`, never `--decision`. The `QUESTIONS` skip needs no `## Loop Decision Needed` section, because the question already sits in the item's `## Open Questions`.

---

## No questions after setup

Q1, Q2, Q3 and the HALT question are the only questions in loop mode. Every other decision point either takes the default in the table below or becomes a documented skip. The handler still takes every action it can. It stops asking and acts.

| Decision point | Loop-mode behavior |
|---|---|
| Phase 2 held-item notice | Not reached. The queue never holds a `BLOCKED` item |
| Phase 3 premise probe fails | Documented skip |
| Phase 3 scoped-rule verdict `inject` or `none` | Proceed. An `inject` verdict carries the listed rules into the fix-agent prompt |
| Phase 3 scoped-rule verdict `placement` | Documented skip. The evidence names the destination and the rule or content tree |
| Phase 3 acceptance criteria already met | Unattended close (§ Unattended close): every criterion's proving command is run, the record is written under `## Resolution`, and the item is closed `COMPLETE`; the refine step closes an item whose preflight proved every criterion MET the same way, with the close record under `## Resolution` |
| Refine step returns `QUESTIONS` | Written into `## Open Questions`; skip with the short note; no `--decision` |
| Phase 4 route | Take the recommended route when it is A or B. A Route C result is a documented skip that also writes `needs_plan: true` (`--needs-plan`) |
| Route A fix-agent returns `BLOCKED` | Documented skip. The evidence is the agent's blocker |
| Phase 5 gates pass | Mark `COMPLETE` |
| Phase 5 a gate fails | Documented skip. Revert nothing. The changes stay in the working tree, and the evidence names the failing gate and the changed files |
| Phase 5 a `build_commands.verify` command fails | Fix it once. Route A returns the command's output to the same fix-agent. Route B fixes it in the main session. A second failure is a documented skip whose evidence names the command |
| Phase 7 follow-up candidates | File none. Print each candidate in the iteration summary |
| Phase 8 lessons | Auto-capture (see § Phase 8 in loop mode) |

### Documented skip

A documented skip ends the iteration with the item handed back and the reason on the page. Run one call:

```bash
python {plugin_root}/scripts/backlog_loop.py --config {planwise_root}/config.yaml --mark --outcome SKIPPED --run {run-id} --id {item-id} --decision "{question, options and evidence}"
```

The script does three things:

- It writes one `### Q{n}. Loop decision (run {run-id})` block under the item's `## Open Questions` section, in the block shape below.
- It restores the item's pre-loop status when the loop had set it IN_PROGRESS.
- It records the outcome `SKIPPED` and the flag `user_input_needed` in the run file. The end summary lists every flagged item.

Write the `--decision` text in this shape, at most 1,200 characters (the script refuses a longer text with exit 1 and writes nothing):

```
Question: {the one question that would have been asked}
Options: (A) {first} (B) {second}
Evidence: {at most 3 lines, each naming its source}
```

A route re-assessment to Route C starts the text with `LOOP: re-assessed to Route C` and adds `--needs-plan`.

The script writes the block in this shape:

```markdown
## Open Questions

### Q{n}. Loop decision (run {run-id})
<!-- loop-decision run={run-id} -->
{the --decision text}

Answer:
```

`{n}` is one more than the highest `### Q` number in the section. A section that reads `None.` or is blank has that content replaced. When the item has no `## Open Questions` section, the script inserts one before `## Related`, else before the footer's thematic break, else at the end. A repeated call in the same run writes nothing. A refine skip uses `--note`, never `--decision`.

Answer with `/planwise backlog --answer {item-id}`, or write text after the block's `Answer:` line. An item with an unanswered block is excluded at `--init`.

`--decision` refuses each of these inputs with exit 1:

- a text over 1,200 characters, or an empty text
- a heading line: `#`, `##` or `###` followed by a space, a tab or the end of the line
- an unclosed code fence
- the legacy end-marker string `<!-- loop-decision-end -->`
- outside a fence, a thematic-break line (`---`, `***` or `___`)
- outside a fence, an `Answer:` line, filled or empty

It also refuses, with exit 1, when the item file itself leaves a code fence or its frontmatter block open. On any `--decision` refusal, skip the item with `--mark --outcome SKIPPED --note "{short reason}"`, so the run continues.

A person who opens a code fence in an answer must close it, because an unclosed fence hides every later section.

Regenerate the backlog index after the call. Then continue to Phase 7.

### Unattended close

Phase 3 step 5 found every acceptance criterion already met. The loop closes the item without asking. Write the record to a scratch file in this shape:

```markdown
Closed {YYYY-MM-DD}: every acceptance criterion was already met.

1. {criterion} -- MET -- `{command}` -> {output excerpt}
2. {criterion} -- MET -- `{command}` -> {output excerpt}
```

Every criterion gets one line with the command that proved it and an excerpt of that command's output. A criterion with no runnable proof is not met, and the item is not closed this way. Then run, in this order:

```bash
python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id {item-id} --status COMPLETE --resolution-file {scratch}/{item-id}-resolution.md
python {plugin_root}/scripts/generate_backlog_index.py --config {planwise_root}/config.yaml --write
python {plugin_root}/scripts/backlog_loop.py --config {planwise_root}/config.yaml --mark --outcome COMPLETE --run {run-id} --id {item-id} --resolution-file {scratch}/{item-id}-resolution.md
```

The first call flips the status, moves the file to the archive and appends the record under `## Resolution`. The third records the unattended close in the run file; its own append is a no-op because the section now holds the record, and the script says so. When the item already carries a `## Resolution` section, the first call appends a dated `### Closed {date}` block holding the record below the section's text, and the third call finds that same record and writes nothing. The end summary lists unattended closes under `Closed unattended`. The script takes that label from the run file, not from the flag: an item this run marked `acting` or `verifying` was fixed, so `--resolution-file` on it appends the record but never counts it as an unattended close. The item is now closed, so skip Phases 4 and 5 for it: regenerate the backlog index, then continue to Phase 7, exactly as after a documented skip. Nothing is committed; the user reviews the archive move and the record in the working tree.

### Verification is in scope

Running the build command (`build_commands.default`), the project's test and lint commands, a shipped-tree or workspace sweep the project's rules name, and any command an item's acceptance criteria name is work the loop does. None of them is a reason to skip an item, and "needs an interactive session" is not a skip reason when the only interactive step would have been running those commands. A commit is not required for `COMPLETE`: the loop commits nothing, and the user commits after reviewing the diff. A command that fails is a failing gate, handled by the Phase 5 row above.

The optional `build_commands.verify` list in `config.yaml` names the project's own extra checks. After the Route A gates or the Route B task list, run each entry from the project root. Record each result with `backlog_loop.py --mark --run {run-id} --id {item-id} --check "{command}" --exit {code}`, which takes no other `--mark` option. A non-zero exit is a failing gate, handled by the `build_commands.verify` row above. An absent or empty list means no extra check.

### Phase 8 in loop mode

Decide without asking whether the iteration surfaced a lesson. A lesson exists when something was non-obvious: a routing signal misled, a fix exposed a related defect, or a gate failed for an unexpected reason. A skipped item with a documented question is not a lesson by itself.

If a lesson surfaced, file it the normal way. Run `parse_lessons.py --next-id`, write the file from `templates/lesson.md`, run the lessons index generator, and append the changelog entry. Then record the ids:

```bash
python {plugin_root}/scripts/backlog_loop.py --config {planwise_root}/config.yaml --mark --run {run-id} --id {item-id} --lessons "LL-NNN"
```

If no lesson surfaced, write the line `No lesson this iteration.` in the iteration summary and ask nothing. The session summary and the end summary name every lesson id filed.

---

## The three questions

Ask these only on an interactive run with no item id argument. Q1 is asked on every such run. There is no opt-in flag.

Ask each question in its own call, and ask the next only after the previous one is answered. Never batch Q1, Q2 and Q3 into one call. Q3 appears only when the answer to Q2 is `specific`.

<!-- AUTO-MODE: convenience -->
<!-- Default: per references/auto-mode-policy.md § Inference Defaults, row "Loop opt-in (backlog.md Phase 2 Q1)". -->
**Q1.** Use `AskUserQuestion`: "Loop through the backlog this run? Each session triages one item, then the plugin's hooks module compacts and re-enters `/planwise backlog`. Looping needs the plugin's hooks module; without it this run ends after the first item and you can continue by hand."
- Option 1: No, single session (default)
- Option 2: Yes, loop

If the answer is No, run the normal Phase 2 and skip this file.

<!-- AUTO-MODE: convenience -->
<!-- Default: per references/auto-mode-policy.md § Inference Defaults, row "Loop mode / count (backlog.md Phase 2 Q2)". -->
**Q2.** Use `AskUserQuestion`: "Which items should the loop cover?"
- Option 1: All eligible items
- Option 2: Specific items (you pick)
- Option 3: The top N by score (then ask the number)

<!-- AUTO-MODE: critical -->
**Q3.** Ask only in `specific` mode. It is the existing Phase 2 question, "Which items would you like to triage?". The picks become the ordered loop set.

Then run `--init` with the answers:

```bash
python {plugin_root}/scripts/backlog_loop.py --config {planwise_root}/config.yaml --init --mode {all|specific|n} [--n {N}] [--items {004,009}] [--no-check]
```

Pass the Phase 1 filters (`--priority`, `--abbrev`, `--status`) through. Pass `--no-check` when the run was started with it. Print the init report to the user: the queue with each score and provisional route, then the excluded list with reasons.

---

## Resume model

The run file is the record. `--next` reads it and decides.

| Death point | Primary signal | Recovery |
|---|---|---|
| After `--init`, before the first `--next` | `current` is null and the queue is full | `--next` works as normal |
| After `--next`, before `--mark --outcome` (phase none, `selected`, `acting` or `verifying`) | `current` is set and `items[current].outcome` is null | HALT. `--next` exits 3 and writes nothing. Report the item and its phase (none means the session died right after the pop), then ask the HALT question below |
| After `--mark --outcome`, before the marker printed | `items[current].outcome` is set and no `boundary` event follows | `--boundary` is idempotent and prints the line |
| Run file missing or unparseable | exit 2 | The loop ends. Say so and continue as a normal single-item run with Q1 not asked |

<!-- AUTO-MODE: critical -->
**HALT question.** Use `AskUserQuestion`: "Item {item-id} stopped in phase {phase} with no outcome. What now?"
- Skip: mark it `SKIPPED` with the note `halted-mid-item` and continue
- Retry: run Phases 3-9 again on the same item
- Abort: run `--end --run {run-id}` and stop the loop

The exit codes are 0 ok, 1 usage or config error, 2 run file missing or unparseable, 3 ambiguous resume.

---

## Loop end

The loop ends in one of three ways:

- The queue is empty. `--boundary` applies `--end` and prints the cross-run summary table above the marker. The summary groups excluded items by reason and lists items marked for a planning session and items closed unattended under their own headings. Below the table, `Skipped (by reason):` groups the skipped items by their note, and `Checks:` prints `{item-id}: {passed}/{run} passed` per item with checks, then each failing command.
- The user chooses Abort at the HALT question. `--end` prints the same summary.
- The run file is missing. Exit 2 ends the loop, as in the Resume model.

A `--next` that skips every remaining item as no longer selectable returns `{"next": null, ...}` and leaves the last skipped item as `current`. `--boundary` then ends the run normally.

After `--end` or a final `--boundary`, the run is ended. `--next` and `--mark` refuse an ended run with exit 1 and write nothing. `--end` and `--boundary` stay idempotent.

When `remaining` is 0, write `Loop complete.` above the marker line. The module takes no action on a marker with `remaining=0`.

---

## The marker

`--boundary` prints, in order: the end summary (only when `remaining` is 0), then the marker line, then one final single-line JSON object. The JSON object carries a `marker` field with the same text. The marker line is therefore not the last line of the script's output.

The marker has this shape:

```
BACKLOG LOOP: run=<run-id> done=<item-id> remaining=<N> state=<abs path>
```

Rule: copy `--boundary`'s stdout line that starts `BACKLOG LOOP:` verbatim, or copy the JSON `marker` field. Never compose the line yourself. Never paraphrase it.

Place that line as the last line of the final message. Nothing follows it. No question, no sentence, no closing remark. The hooks module reads the final answer for this line, and a trailing `AskUserQuestion` defers the boundary until the module gives up.

`state` is the absolute run-file path with forward slashes. A second `--boundary` call prints the same line and changes nothing.
