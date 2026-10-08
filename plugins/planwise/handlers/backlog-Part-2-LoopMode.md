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
| Selectable, provisional route A or B | Yes | none |
| Selectable, provisional route C | No, listed as excluded | `plans deferred in loop mode` |
| Blocked by an open dependency | No | not selectable |
| Held (`BLOCKED`) or closed | No | not selectable |

Queue order is highest score first, then item id. Mode `n` keeps the first N of that order. Mode `specific` keeps the user's order and drops an ineligible id with a warning line.

An empty queue is an error. `--init` exits 1, prints a JSON line with an `error` key, and writes no run file. Tell the user and continue as a normal single-item run with Q1 not asked.

`--status` alone is the status subcommand. Combined with `--init`, `--status` is a status filter for the queue.

---

## Per-iteration contract

Each session handles exactly one item. The numbered steps run in order.

1. Phase 1 FETCH. On `--loop-resume`, skip the two drift audits. They ran once at init. `generate_backlog_index.py --check` and `parse_backlog.py` still run.
2. Phase 2. On a fresh run, ask the three questions and run `--init`. On `--loop-resume`, ask nothing. Both paths then run `--next --run {run-id}` and read its JSON line.
3. `--next` exits 3 when the current item died mid-work. Follow the Resume model section below.
4. `{"next": null, ...}` means the queue is empty. Run `--boundary` and finish at Phase 9.
5. Set only the popped item IN_PROGRESS, regenerate the index, then run `--mark --phase selected --run {run-id} --id {item-id}`.
6. Phase 3 RESOLVE. Re-run `score_backlog.py --route --id {item-id}` and note any divergence from `route_at_init` in `Reason:`.
7. Phase 4 ACT. Ask nothing. Take the recommended route when it is A or B. A Route C result is a documented skip (see § No questions after setup). Run `--mark --phase acting --run {run-id} --id {item-id}` before the Route A or B dispatch.
8. Phase 5 VERIFY. Run `--mark --phase verifying --run {run-id} --id {item-id}` before the gates. Ask nothing. Apply the Phase 5 default in § No questions after setup.
9. Phase 6 CLOSE. Map the outcome and run `--mark --outcome`:

   | Phase 5 or Phase 4 result | Outcome |
   |---|---|
   | Every gate passed, or task list done | `COMPLETE` |
   | A decision is needed, or a gate failed | `SKIPPED`, with `--decision` |
   | Halted item skipped at the HALT question | `SKIPPED`, with `--note halted-mid-item` |

   A `SKIPPED` outcome restores the item's pre-loop status. When the script prints `Restored`, regenerate the backlog index.
10. Phases 7 and 8 run every iteration, for the one item of the session. Both ask nothing.
11. Phase 9 LOOP BOUNDARY. Run `--boundary` and end the turn on the marker.

---

## No questions after setup

Q1, Q2, Q3 and the HALT question are the only questions in loop mode. Every other decision point either takes the default in the table below or becomes a documented skip. The handler still takes every action it can. It stops asking and acts.

| Decision point | Loop-mode behavior |
|---|---|
| Phase 2 held-item notice | Not reached. The queue never holds a `BLOCKED` item |
| Phase 3 premise probe fails | Documented skip |
| Phase 3 scoped-rule conflict | Documented skip |
| Phase 3 acceptance criteria already met | Documented skip. The evidence names the criteria. The handler does not close an item unattended |
| Phase 4 route | Take the recommended route when it is A or B. A Route C result is a documented skip |
| Route A fix-agent returns `BLOCKED` | Documented skip. The evidence is the agent's blocker |
| Phase 5 gates pass | Mark `COMPLETE` |
| Phase 5 a gate fails | Documented skip. Revert nothing. The changes stay in the working tree, and the evidence names the failing gate and the changed files |
| Phase 7 follow-up candidates | File none. Print each candidate in the iteration summary |
| Phase 8 lessons | Auto-capture (see § Phase 8 in loop mode) |

### Documented skip

A documented skip ends the iteration with the item handed back and the reason on the page. Run one call:

```bash
python {plugin_root}/scripts/backlog_loop.py --config {planwise_root}/config.yaml --mark --outcome SKIPPED --run {run-id} --id {item-id} --decision "{question, options and evidence}"
```

The script does three things:

- It appends a dated `## Loop Decision Needed` section to the item file. The section opens with a `[!gate] User input needed` callout.
- It restores the item's pre-loop status when the loop had set it IN_PROGRESS.
- It records the outcome `SKIPPED` and the flag `user_input_needed` in the run file. The end summary lists every flagged item.

Write the `--decision` text as the question that would have been asked, then the options, then the evidence with its source. The next interactive run finds the section and answers it. A route re-assessment to Route C starts the text with `LOOP: re-assessed to Route C`.

Regenerate the backlog index after the call. Then continue to Phase 7.

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

- The queue is empty. `--boundary` applies `--end` and prints the cross-run summary table above the marker.
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
