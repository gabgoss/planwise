# Handler: /planwise backlog — Answer Step (Part 3)

This file is Part 3 of `handlers/backlog.md`. Read it when `--answer` is present. The step asks you each open question an item carries and records your answer in the item file.

---

## Purpose

**Purpose:** Answer the `### Q{n}.` blocks under `## Open Questions` without hand-editing item files. The step only writes `Answer:` lines. It never sets `refined`, never changes a status and never commits.

`--answer` takes an optional item id. With an id, the step covers that item. Without one, it covers every open item that has an unanswered block.

`scripts/backlog_questions.py` does every read and write. The handler never edits an item file by hand. Each subcommand prints short human lines, then one final single-line JSON object.

---

## Steps

### Step 1: List the open questions

```bash
python {plugin_root}/scripts/backlog_questions.py --config {planwise_root}/config.yaml --list [--id {item-id}]
```

The list prints each unanswered block: item id, `Q{n}`, the first line of the question and its `Options:` line when present. It reads only.

When the output ends with a legacy-section count and the line `run --fold --all first`, ask once whether to fold now. On yes, show the plan, then fold and regenerate the index:

```bash
python {plugin_root}/scripts/backlog_questions.py --config {planwise_root}/config.yaml --fold --all --dry-run
python {plugin_root}/scripts/backlog_questions.py --config {planwise_root}/config.yaml --fold --all
python {plugin_root}/scripts/generate_backlog_index.py --config {planwise_root}/config.yaml --write
```

Then list again. On no, continue with the blocks already listed. When nothing is unanswered, say so and stop.

### Step 2: Ask each question

<!-- AUTO-MODE: critical -->

Ask one `AskUserQuestion` per unanswered block, one question per call. Build the options from the block's `Options:` line and add "Skip this question". A skipped block stays unanswered and is not written.

Auto Mode cannot infer an answer. It lists the unanswered questions and asks nothing, per the "Answer open questions" row of `references/auto-mode-policy.md`.

### Step 3: Record each answer

Write the answer text to a scratch file, then record it:

```bash
python {plugin_root}/scripts/backlog_questions.py --config {planwise_root}/config.yaml --answer --id {item-id} --q {K} --text-file {scratch_file}
```

The script fills the empty `Answer:` line of `### Q{K}.` with `Answer: {YYYY-MM-DD}: {text}`. A multi-line text keeps its later lines indented by two spaces.

The script refuses with exit 1 and writes nothing when:

- the text file is empty
- the text holds a heading line
- the text holds an unclosed fence
- the text holds a thematic-break line
- the block is already answered
- `Q{K}` is absent from the item

On a refusal, show the message, fix the text with the user and run the call again. Never edit the item file to get around a refusal.

### Step 4: Report the new state

Print one line per item: the id, the blocks answered and the blocks skipped.

- An unrefined item with every block answered is eligible on the next loop run.
- A refined item with an answered block fails the shape gate until the refine path folds the answer into `## Resolution`. Use `--refine-max` or `--mode specific` on the next loop run.

Do not set `refined`, change a status or commit. The user triages the item through the normal route.
