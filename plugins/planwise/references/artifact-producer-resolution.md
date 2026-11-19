---
description: Every artifact a Sprint Plan Deliverable, an Orchestration Post-Session Checklist or a Signoff anchor names resolves to exactly one declared producer, and that producer states the artifact's record format and its merge rule (§1, Reviewer Check 111). A question's option payload is a literal fragment of the file its consumer reads, with one question per pair, so no session owes a translation (§2).
consult-when: Scaffolding or reviewing a sprint where several documents read one assembled artifact (a rollup built at signoff from many tasks' outputs) — the artifact resolves to exactly one producer that states its record format and merge rule (§1, Check 111) — or where one session emits a question, another writes its answer and a third reads it — the answer payload is a fragment of the consumer's input file (§2)
paths: {planwise_root}/{plans_dir}/**
---

# Artifact Producer Resolution

**Purpose:** A sprint-level rollup is assembled at signoff from many tasks' outputs. Several documents name it and several anchors read it. This reference requires a producer for it. Without a producer, each consumer guesses the artifact's shape, and a correct sprint fails an anchor that guessed wrong.

**Read this when** you scaffold a sprint whose Deliverables, Orchestration checklists or Signoff anchors name an artifact that no single task writes. Read it also when you review such a sprint. Read §2 when one session emits a question and a later session persists the answer for a third to read.

## Table of Contents

- [1. Every Artifact a Deliverable or Signoff Anchor Names Resolves to Exactly One Producer](#1-every-artifact-a-deliverable-or-signoff-anchor-names-resolves-to-exactly-one-producer)
- [2. A Question's Answer Payload Is a Fragment of the File Its Consumer Reads](#2-a-questions-answer-payload-is-a-fragment-of-the-file-its-consumer-reads)

---

## 1. Every Artifact a Deliverable or Signoff Anchor Names Resolves to Exactly One Producer

A rollup artifact is the typical case. The Sprint Plan lists it as a headline Deliverable. The Orchestration checklists name it. Eight Signoff anchors read it. Every document is consistent with the others, and no task `**Output:**` line and no checklist step builds it. Nothing declares its column order, the merge rule for an id that yields two rows, or the suffix spellings the anchors match. An exit criterion then states a cardinality that the real artifact cannot meet, and its anchor fails a correct sprint.

> [!constraint] One artifact, one producer, and the producer states three things
> A producer is one of two things. It is a named task's `**Output:**` line. Or it is one Post-Session Checklist step or assembly task that states all three of these:
>
> 1. That it assembles the artifact, by path.
> 2. The record format: the column order, and the literal suffix spellings that anchors match.
> 3. The merge rule for an id that legitimately yields more than one row.
>
> Two producers for one artifact is also a defect. Two writers produce two shapes, and the anchors read whichever ran last.
>
> WRONG — eight anchors read a rollup that no step builds:
> ```
> Sprint Plan Deliverables:   `Outputs/Rollup.md`  (headline deliverable)
> Orchestration checklist:    "Confirm `Outputs/Rollup.md` is complete"
> Signoff anchors 1-8:        each reads `Outputs/Rollup.md`
> Task Output lines:          each names only its own file
> -> zero producers; column order, merge rule and suffixes declared nowhere
> ```
> CORRECT — the same rollup with one declared assembly step:
> ```
> Post-Session Checklist step 4: assembles `Outputs/Rollup.md`;
>   columns {id | status | evidence}; suffix spellings `-PASS` and `-FAIL`;
>   an id with two rows merges by keeping the later row
> -> one producer, with the record format and the merge rule stated
> ```

**Boundary with criterion ownership.** A plan can pass an audit that asks whether every success criterion has an owning task and still ship this defect. The criterion has an owner. The artifact the criterion's anchor reads has none. `exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md` §16.16 covers the first question. This section covers the second. The caption-versus-table rule in `scaffolding-hygiene.md` §12.7 is a sibling: it derives a count from its table, and this section derives an artifact from its producer.

**The producer step is not optional prose.** A checklist line that says "assemble the rollup" names the work and omits the record format and the merge rule. It is a producer in name only. The consumers still guess, and a reviewer cannot check an anchor against a format that no document states.

#### Reviewer Check 111 — Consumed Artifact With No Declared Producer

- **Severity / Role / Type:** BLOCKER when a Signoff anchor or a gate-defining exit criterion reads the artifact, ERROR otherwise | Scaffolding Hygiene Reviewer | NEW
- **What:** Every artifact named by two or more consuming documents MUST resolve to exactly one producer. The producer MUST state the record format and the merge rule. A name with zero producers, or two, is a finding.
- **Detection:**
  1. Collect the inline-code artifact names from the Sprint Plan `## Deliverables`, every Orchestration `## Post-Session Checklist`, the Sprint-Signoff anchor tables and the Execution Input exit criteria.
  2. Count the consuming documents per name.
  3. For each name with 2 or more consumers, search every task file's `**Output:**` line, every Post-Session Checklist, and the Deliverables `Producer` cell where the Sprint Plan carries one.
  4. Zero producers, or two producers, is a finding.
  5. A checklist-step or assembly-task producer that omits the record format or the merge rule is an ERROR.
  6. Dry-run the search on one fixture where the artifact has no producer and one where it has a declared step. The first MUST yield one finding and the second none. Identical results mean the search does not discriminate.
- **Finding template:**
```
[BLOCKER] Consumed artifact with no declared producer
File: {Sprint Plan / Orchestration / Signoff} | Location: {Deliverables row | checklist step | anchor {n}}
Issue: `{artifact path}` is read by {N} documents ({list}) and {no task Output line or checklist step builds it} | {two producers build it: {list}} | {the producer step omits the {record format | merge rule}}
Fix: Name exactly one producer for the artifact, and have it state the record format and the merge rule, per references/artifact-producer-resolution.md §1 | Confidence: HIGH
```

---

## 2. A Question's Answer Payload Is a Fragment of the File Its Consumer Reads

A read-only preflight asks a question. A second session writes the answer into a file. A third session reads that file. The payload format is a contract between all three, and each session can be internally consistent while the contract has no owner.

> [!constraint] An option payload is a literal fragment of the consumer's input, and one question covers one pair
> Write each option's payload in the consumer's own input format. Then the answer writer merges fragments without knowing what they mean, and the producer and the consumer can be tested against each other directly. A payload in the producer's private vocabulary needs a translator, and no plan names one. The translator can also lose information the consumer needs.
>
> Two defects came from one measured payload set. The producer offered `{"drop": "both"}` for a pair of reciprocal edges. The consumer reads an `edge_drops` list of pair strings. First, nobody owned the translation from `drop` to `edge_drops`. Second, `"both"` named no pair, so it could not be translated at all. A third defect rode along: the question covered only the first reciprocal pair, so a project with two pairs answered once and was refused again.
>
> WRONG — the payload speaks the producer's vocabulary, and one question covers every pair:
> ```json
> {"label": "Drop both", "answer": {"drop": "both"}}
> ```
> CORRECT — the payload is a fragment of the answers file, and one question covers one pair:
> ```json
> {"label": "Drop both", "answer": {"edge_drops": ["001<->002:both"]}}
> ```

Three obligations follow.

1. **Name the consumer's input key in the producing task.** The task that emits the question states the key and the value shape its payloads fill, and quotes one consumer-side example.
2. **Emit one question per pair, not one per class.** A payload that must name a pair names exactly one. A question that spans several pairs forces a vocabulary word that names none of them.
3. **Test the producer against the consumer.** Feed each emitted payload, unchanged, into the consumer's reader. A payload the reader rejects is a defect in the producer, found before the third session starts.

**Boundary with §1.** §1 asks who builds an artifact and in what record format. This section asks what shape an answer takes on its way into one. A sprint can pass §1 with a single declared producer and still fail here, because the producer's input was assembled from payloads that needed translating.

---

*Cross-references: [scaffolding-hygiene.md](scaffolding-hygiene.md) (§12.7, a count is derived from its table), [exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md](exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md) (§16.16, a success-criterion clause needs an owning task), [gate-input-set-and-compared-window.md](gate-input-set-and-compared-window.md) (§16, a command's match set covers the population its criterion names).*
