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

The list reads only. For each item with an unanswered block it prints one header line (`{id}: {title} ({priority}, {abbrev}) {file}`), then each block: `{id} Q{n}: {question}`, its `Options:` line and its `Recommendation:` line when present. Run it a second time with `--json` to get the fields Step 2 is built from:

| Payload key | Carries |
|---|---|
| `items[id].title`, `.priority`, `.abbrev`, `.file` | the item's frontmatter and its file path, relative to the backlog folder |
| `items[id].summary`, `.problem` | the first paragraph of `## Summary` and of `## Problem` |
| `items[id].preamble` | the text between `## Open Questions` and its first `### Q` block, where the item records decisions already made |
| `questions[].q`, `.question` | the block number and the question text |
| `questions[].choices` | the `Options:` line split per letter: `[{"letter": "A", "text": "..."}, ...]` |
| `questions[].recommended`, `.reason` | the planner's letter and its one-sentence reason |
| `questions[].context`, `.evidence` | the block's other body lines, and its `Evidence:` line |

A missing value is `null`, or `[]` for `choices`. Never hand-read an item file to recover a field the payload carries.

When the output ends with a legacy-section count and the line `run --fold --all first`, ask once whether to fold now. On yes, show the plan, then fold and regenerate the index:

```bash
python {plugin_root}/scripts/backlog_questions.py --config {planwise_root}/config.yaml --fold --all --dry-run
python {plugin_root}/scripts/backlog_questions.py --config {planwise_root}/config.yaml --fold --all
python {plugin_root}/scripts/generate_backlog_index.py --config {planwise_root}/config.yaml --write
```

Then list again. On no, continue with the blocks already listed. When nothing is unanswered, say so and stop.

### Step 2: Brief the user, then ask each question

<!-- AUTO-MODE: critical -->

The user answers from what the dialog shows. Give them the same context triage gives before a route decision: what the item is, what is already decided, and what the planner recommends. Both parts below are built from the `--json` payload of Step 1.

**2a. Print one Question Briefing Block per item**, before that item's first question:

> [!template] Question Briefing Block
> ```
> ITEM: {id} — {items[id].title}
> Priority: {items[id].priority} | Domain: {items[id].abbrev} | File: {items[id].file}
>
> ## What This Is About
>
> {2-4 sentences from items[id].summary, or from items[id].problem when summary is null}
>
> ## Already Decided
>
> {items[id].preamble, or "Nothing recorded."}
>
> ## Open Questions
>
> - Q{n}: {question} — recommended: {recommended, or "none"}
> ```
>
> When `summary` and `problem` are both `null`, `Read` the item file once and write the 2-4 sentences from it. Otherwise do not open the item file.

**2b. Ask one `AskUserQuestion` per unanswered block, one question per call.** The user may see only the dialog while it is open, so each question carries its own context:

| `AskUserQuestion` field | Value |
|---|---|
| `header` | `Q{n} {id}`, 12 characters at most. Shorten the id, never the Q number |
| `question` | `{id} — {title}.` Then one sentence from `summary`. Then the question text. Then `Why: {context or evidence}`, or `Why: {the first sentence of problem}` when both are null. Four sentences at most |
| option `label` | `({letter}) {choice text}`. The dialog shows a label on one line, so when the choice text runs past eight words, shorten it and open that option's `description` with the full choice text |
| option order | the recommended choice first with ` (Recommended)` appended to its label, then the other choices in letter order, then `Skip this question` |
| recommended option `description` | `reason`, after the full choice text when its label was shortened |
| other option `description` | the full choice text when its label was shortened. Otherwise `Not the planner's choice.`, or `No recommendation recorded.` when `recommended` is null |
| `Skip this question` `description` | `Leaves Answer: empty. The item stays excluded from the loop.` |
| `preview` | none. The context sits in the question and the descriptions |

When `choices` is empty, offer `Skip this question` alone and put the question text and its context in `question`. The user types a free answer through the dialog's own "Other" entry. A skipped block stays unanswered and is not written.

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

- An unrefined item with every block answered is eligible on the next loop run. Or refine it now with `/planwise backlog --refine {id}`.
- A refined item with an answered block fails the shape gate until the refine path folds the answer into `## Resolution`. Run `/planwise backlog --refine {id}` to fold it now. On the next loop run, pick the item in Q2 specific mode (`--mode specific`), or start the run with `/planwise backlog --refine-max N`.

Do not set `refined`, change a status or commit. The user triages the item through the normal route.
