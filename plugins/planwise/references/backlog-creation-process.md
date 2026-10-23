---
description: The backlog creation process: three agents (preflight, planner, author) that prove, design and file or refine backlog items, with the hand-over directory, the spawn-prompt shapes, the question round-trip and the disposition table
consult-when: Filing or refining a backlog item through the preflight, planner and author agents, or wiring a new caller to that process
---

# Backlog Creation Process

**Purpose:** One process files new backlog items and refines existing ones. Four callers cite it: the backlog handler's Phase 7 (filing) and the backlog loop's refine step (refining), harvest Stage 2, and the promote-batch workflow's filing step. Each caller dispatches the same three agents in the same order and reads the same status blocks. The agents hold the field-level contracts, and this file holds the order, the hand-over directory, the spawn prompts and the routing.

---

## 1. Roles

| Agent | Dispatches per batch | Input | Output file | Status block fields |
|---|---|---|---|---|
| `backlog-preflight` | 1 | Candidate blocks (`file` mode) or item ids (`refine` mode) | `{handover_dir}/preflight.md` | `TASK_STATUS`, `CANDIDATES_IN`, `FACT_SHEETS`, `DISPOSITIONS`, `OUTPUT_FILES`, `SOURCE_PINS`, `ISSUES` |
| `backlog-planner` | 1 per `HOLDS` item | One block of the fact sheet | `{handover_dir}/{id-or-label}-design.md` | `TASK_STATUS`, `TASK_ID`, `DESIGN`, `OUTPUT_FILES`, `LINES_PRODUCED`, `QUESTIONS_COUNT`, `SUB_ITEMS_COUNT`, `KEY_FINDINGS`, `ISSUES` |
| `backlog-author` | 1 | The fact sheet and every design file | Item files and the regenerated index | `TASK_STATUS`, `CANDIDATES_IN`, `ITEMS_FILED`, `ITEMS_REWRITTEN`, `ITEMS_ALREADY_MET`, `ITEMS_RETIRED`, `OUTPUT_FILES`, `INDEX_REGENERATED`, `SOURCE_RECONCILE`, `ISSUES` |

The preflight proves, the planner designs and the author writes. No agent does a neighbour's work. The orchestrator (the caller's main context) owns the user conversation, every status flip, the index write for a status change and the reconciliation of source documents. The agent files are the source of truth for field names. This table only names them.

---

## 2. Hand-over directory

The three agents pass work through files, never through their final messages. The caller creates one directory per batch and passes its absolute path as `handover_dir`.

- The fact sheet is `{handover_dir}/preflight.md`, one block per candidate.
- Each design file is `{handover_dir}/{id-or-label}-design.md`.
- The backlog loop uses `{backlog_dir}/Backlog-Runs/{run-id}-refine/{item-id}/`. The index readers never walk that path.
- A filing caller uses a scratch directory it names. It sits outside `backlog_dir` so that no item reader sees it.

Discard the directory after the author returns and the caller has read the status blocks.

---

## 3. Filing path

Use this path for candidates from a source document.

1. Write one candidate block per candidate: label, claim, cited paths, acceptance criteria and source document.
2. Dispatch `backlog-preflight` once in `file` mode with every candidate block.
3. Read the fact sheet. A `HOLDS` block goes on to a planner. Every other disposition skips the planner (see section 6).
4. Dispatch `backlog-planner` once per `HOLDS` block. Independent planners may run in parallel, each under its own dispatch name.
5. On a `QUESTIONS` return, run the round-trip of section 5.
6. Dispatch `backlog-author` once in `file` mode, after every planner has returned its final design.
7. Render the summary. Name each retirement in `ITEMS_RETIRED` with its evidence. Reconcile each source document in `SOURCE_RECONCILE`. Re-read a source whose `SOURCE_PINS` differ from your own read.

A short count is valid: `ITEMS_FILED` below `CANDIDATES_IN` is a `COMPLETE` return when `ITEMS_RETIRED` accounts for the difference.

---

## 4. Refine path

Use this path for existing items that are not yet refined.

1. Pass the item ids. Dispatch `backlog-preflight` once in `refine` mode.
2. A `HOLDS` block goes on to a planner. An `ALREADY_MET` block goes straight to the author. Other dispositions follow section 6.
3. Dispatch `backlog-planner` once per `HOLDS` item, and run the round-trip of section 5 for any `QUESTIONS` return.
4. Dispatch `backlog-author` once in `refine` mode. It edits each item in place and keeps the item's `id`, `title`, `created` and `blocks`.

The shape gate reads an item as executable by this predicate, quoted from `references/backlog-schema.md`: `shape_ok`: true when `refined` is true, `## Resolution` has at least one numbered step, `## Verification` exists with a fence, and `open_questions` is `absent` or `empty`.

An answered `### Q{n}.` block still fails that predicate. So before the author writes `refined: true`, it folds each answered question into `## Resolution`, removes that `### Q{n}.` block, and removes `## Open Questions` or leaves it reading `None.`. A question that is still unanswered keeps its block, and the item keeps `refined: false`.

---

## 5. The QUESTIONS round-trip

A planner returns `DESIGN: QUESTIONS` when a choice belongs to the user. No spawned agent can ask the user, so the orchestrator relays.

Spawn the planner in the foreground with a `name:` of the form `planner-{id-or-label}`. The planner's final message is its status block. The planner holds no messaging tool.

- **Interactive run:** read the questions from the design file. Ask the user one `AskUserQuestion` per question, with the planner's options and recommendation. Then send all the answers with `SendMessage` to that dispatch name. The planner resumes from its own transcript, re-decides, overwrites the design file and returns a new status block. A second `QUESTIONS` return names only questions the answers did not cover.
- **Unattended run (a loop or Auto Mode):** ask nothing. Pass the design file to the author. The author writes each question into the item as an unanswered `### Q{n}.` block under `## Open Questions`, and the item stays `refined: false` until a user answers it.

---

## 6. Dispositions

Each preflight disposition names one action on each path. The preflight picks one disposition per candidate by this precedence: `DUPLICATE`, `RESOLVED`, `PREMISE_FAILS`, `ALREADY_MET`, `HOLDS`. In `file` mode a candidate whose criteria all re-check as met reads `RESOLVED`, because `ALREADY_MET` applies in `refine` mode only.

| Disposition | Meaning | Filing path | Refine path |
|---|---|---|---|
| `HOLDS` | The condition holds | Planner, then author files the item | Planner, then author rewrites the item |
| `RESOLVED` | A fix landed and no item references the artifact | No item file. One `ITEMS_RETIRED` line with the landing commit, and the source document in `SOURCE_RECONCILE` | The author writes one `### Q{n}.` block proposing CLOSED, quoting the evidence. The loop never closes an item unattended |
| `DUPLICATE` | An open item covers it | Same as `RESOLVED`, naming the covering item | Same as `RESOLVED` |
| `ALREADY_MET` | Every criterion is met | Not produced in this mode | The author writes a close record into `## Resolution`. The orchestrator flips the status |
| `PREMISE_FAILS` | The re-alignment target is absent | The author writes one open question with the options re-target, retire and keep | Same as the filing path |

A design file's `DESIGN` value maps to the item as the author's mapping table states: `REFINED` writes `refined: true`, `QUESTIONS` writes open questions, `DECOMPOSE` files sub-items that carry the parent in their `blocks:`, and `NEEDS_PLAN` writes `needs_plan: true` for a later planning session. No agent authors a session plan.

---

## 7. Constraints

- Dispatch every agent in the foreground. A background dispatch loses its Write, Edit and Bash calls silently.
- Dispatch one author at a time, and batch every candidate into that one dispatch. Two concurrent authors can read the same next free id.
- Dispatch the preflight once per batch, never once per candidate.
- No spawned agent has a question tool. A user decision is a returned disposition or a `QUESTIONS` return, and the orchestrator asks.
- The orchestrator owns every status flip and every source-document reconciliation. The author sets neither.
- The author regenerates the index once per dispatch. Do not write index rows by hand.
- Keep shipped text project-agnostic: a spawn prompt names paths and modes, never a plan, a session or a tracker identifier.

### Spawn prompt: preflight

```
Task {
  subagent_type: "planwise:backlog-preflight",
  description: "Prove backlog candidates",
  prompt: "mode: {file|refine}
handover_dir: {absolute path}
plugin_root: {absolute path}
planwise_root: {absolute path}
backlog_dir: {absolute path}
{file mode: one candidate block per candidate | refine mode: item ids}"
}
```

### Spawn prompt: planner

```
Task {
  subagent_type: "planwise:backlog-planner",
  name: "planner-{id-or-label}",
  description: "Design one backlog item",
  prompt: "item: {id or candidate label}
handover_dir: {absolute path}
plugin_root: {absolute path}
planwise_root: {absolute path}
backlog_dir: {absolute path}
fact_sheet: {handover_dir}/preflight.md
{refine mode: item_file: {absolute path}}"
}
```

### Spawn prompt: author

```
Task {
  subagent_type: "planwise:backlog-author",
  description: "File or refine backlog items",
  prompt: "mode: {file|refine}
handover_dir: {absolute path}
plugin_root: {absolute path}
planwise_root: {absolute path}
backlog_dir: {absolute path}
{refine mode: item ids}"
}
```
