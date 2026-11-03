# Handler: /planwise backlog — Refine Mode (Part 4)

This file is Part 4 of `handlers/backlog.md`. Read it when `--refine` is present. The mode designs the named items and stops, so you can read each design before anything runs it.

---

## Purpose

**Purpose:** `--refine <ids>` designs the named items through the refine path of `references/backlog-creation-process.md` and stops. It commits nothing and sets no status except an `ALREADY_MET` close.

`<ids>` is one item id or a comma-separated list. `--refine` is a different flag from `--refine-max N`, which caps the refine step of a loop run.

The mode dispatches the same three agents as the loop's refine step, in the same order. The orchestrator relays every question, because no spawned agent can ask the user. Every dispatch follows `references/backlog-creation-process.md` § 7 Constraints: foreground only, one preflight and one author per batch, never two authors at once.

---

## Steps

### Step 1: Select the ids

Phase 1 FETCH has run. Keep each named id that is open. Drop a missing or closed id with a warning line that names it.

Note each kept id that carries an empty `Answer:` line under `## Open Questions`. The author keeps that block, so the item stays `refined: false` until the question is answered.

### Step 2: Batch the ids

Split the kept ids into batches of at most 3 items. The cap comes from the preflight agent's 40-turn limit and its measured cost of about 10 tool calls per item with the full protocol. A batch of 3 fits in 40 turns even at one call per turn.

A larger batch still finishes, but the agent drops protocol steps to fit. Measured once on items of 86 to 134 lines: 1 item used 10 tool calls and ran the duplicate scan. A batch of 5 used 32 tool calls and skipped the duplicate scan for every item. Re-measure when the preflight protocol changes.

Create one hand-over directory per batch:

```
{backlog_dir}/Backlog-Runs/{YYYYMMDD-HHMMSS}-refine/batch-{n}/
```

The timestamp is this run's start time. `references/backlog-creation-process.md` § 2 Hand-over directory gives the files each agent writes there.

### Step 3: Prove the batch

Dispatch `planwise:backlog-preflight` once in `refine` mode with the batch ids, in the foreground. Read the `DISPOSITIONS` field of its status block.

A `HOLDS` id goes on to Step 4. An `ALREADY_MET` id skips the planner and goes to the author. Every other disposition follows `references/backlog-creation-process.md` § 6 Dispositions, refine path column.

### Step 4: Design each HOLDS item

Take the `HOLDS` ids one at a time. Dispatch `planwise:backlog-planner` in the foreground under the name `planner-{item-id}`. Never run two planners at once.

On a `QUESTIONS` return, run the interactive branch of `references/backlog-creation-process.md` § 5 The QUESTIONS round-trip:

1. Read the questions from the design file.
2. Ask one `AskUserQuestion` per question, with the planner's options and recommendation.
3. Send all the answers with `SendMessage` to `planner-{item-id}`.
4. When that dispatch cannot be reached, start a fresh planner dispatch with the same item and an `answers:` line that holds the answers keyed by question number.

<!-- AUTO-MODE: convenience -->
<!-- Default: per references/auto-mode-policy.md § Inference Defaults, row "Refine mode question round-trip (backlog-Part-4-Refine.md, `--refine`)". -->
In Auto Mode, ask nothing and follow the unattended branch of `references/backlog-creation-process.md` § 5.

### Step 5: Rewrite the batch

After every planner of the batch has returned its final design, dispatch `planwise:backlog-author` once in `refine` mode with the batch ids, in the foreground. It rewrites each item in place and regenerates the index once.

### Step 6: Close an ALREADY_MET item

<!-- AUTO-MODE: convenience -->
<!-- Default: per references/auto-mode-policy.md § Inference Defaults, row "Refine mode ALREADY_MET close (backlog-Part-4-Refine.md, `--refine`)". -->
The author has written a close record into the item's `## Resolution`. Ask one `AskUserQuestion` per such item: "Close as COMPLETE" or "Keep open".

On close, run the status update, then regenerate the index:

```bash
python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id "{item_id}" --status COMPLETE
python {plugin_root}/scripts/generate_backlog_index.py --config {planwise_root}/config.yaml --write
```

On keep open, change nothing. The close record stays in the item for the user to review. Auto Mode closes without asking.

### Step 7: Resume a stalled agent once

An agent that returns `BLOCKED` or `PARTIAL` is resumed once, with a message that names the missing piece. A second `BLOCKED` or `PARTIAL` return leaves that agent's items untouched. Report each such item with the agent and the reason.

### Step 8: Report and stop

Print one table row per named id, dropped ids included. The columns are:

| Column | Content |
|---|---|
| Id | The item id |
| Disposition | The preflight disposition, or the reason the id was dropped |
| Design | The planner's `DESIGN` value, or `none` |
| Author change | What the author wrote: `refined: true`, open questions, a close record, sub-items, `needs_plan: true`, or `none` |
| Next step | The command the user runs next, from the list after this table |

Pick the next step from this list:

- Review the design: `git diff -- {item file}`.
- Reject the design: `git checkout -- {item file}`. Or edit `## Resolution` and run `/planwise backlog --refine {id}` again.
- Answer a written question: `/planwise backlog --answer {id}`.
- Triage the item: `/planwise backlog {id}`.

Discard each batch's hand-over directory after its author returns and you have read the status blocks. Then STOP. Do not commit, and do not set any other status.
