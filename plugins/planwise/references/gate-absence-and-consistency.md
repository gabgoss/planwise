---
description: An absence-grep criterion scrubs its token from every surface including the gate's own prose and legend (§8.1), a consistency check asserts against the right population rather than a conditional set against an observed union (§8.2), and a file that encodes one fact in two representations is updated in both on every mutation and verified against the file (§8.3).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Absence and Consistency Checks (Scrub, Scope, and Sync)

**Purpose:** Three gate shapes that return a false verdict on a correct artifact: an absence grep that matches its own description, a subset assertion against the wrong population, and a parse-side check that never reads the prose copy of the same fact. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you write a `grep -c TOKEN == 0` criterion, a `conditional ⊆ observed` consistency check, or a status flip over a file that states the same count in a code block and in prose.

## Table of Contents

- [8. Absence and Consistency Gates — Scrub, Scope, and Sync](#8-absence-and-consistency-gates--scrub-scope-and-sync)
  - [8.1 An absence-grep requires scrubbing the token everywhere](#81-an-absence-grep-requires-scrubbing-the-token-everywhere)
  - [8.2 Assert against the right population](#82-assert-against-the-right-population)
  - [8.3 One file encoding a fact twice — every mutation updates both](#83-one-file-encoding-a-fact-twice--every-mutation-updates-both)

---

## 8. Absence and Consistency Gates — Scrub, Scope, and Sync

### 8.1 An absence-grep requires scrubbing the token everywhere

> [!constraint] An absence-grep criterion MUST scrub the literal token from every surface, not just data cells
> A criterion of the form `grep -c 'TOKEN' {file} == 0` proves absence of a TOKEN-class item. Satisfying it requires the literal token to appear nowhere — not merely absent from data cells. It must be scrubbed from the classification legend, count-block labels, section headers, descriptive prose, and any self-referential mention of the grep itself. Replace with a synonym. Grep is case-sensitive, so lowercase variants are safe; run the exact anchor command yourself before declaring the criterion met.
>
> Observed false-FAIL: the criterion's own grep returned 8 against a file with zero unresolved data cells — every hit was the legend, the label, and the criterion's own description.

### 8.2 Assert against the right population

> [!constraint] A consistency check MUST assert against the right population, not a conditional/optional set against an observed/union artifact
> A consistency check asserting a conditional/optional annotation set is a subset of an observed/union artifact encodes the wrong invariant — conditional annotations exist precisely to document things absent from the observed set. Assert "the root is a declared field" instead — skipping glob, brace, and condition-expression entries, failing only on an undeclared root. Scope comment-marker checks to comment-only lines so inline annotations are not matched.
>
> Observed false-FAIL: a `conditional ⊆ observed` assertion failed on 22 legitimate conditional fields.

### 8.3 One file encoding a fact twice — every mutation updates both

> [!constraint] When a file encodes one fact in two representations, every mutation MUST update both and verify against the file
> When a single file encodes the same fact in both a machine-checked form and a human-readable form, a passing gate only ever sees the form it parses. Every mutation MUST update every representation, and the change MUST then verify the written counts against the file.
>
> Observed false-PASS: a status flip updated the parsed code block to a new count but left the prose bullets, summary line, and callout's stated counts stale. The mechanical check stayed green while the document contradicted itself.

A gate that counts a section by its heading text anchors the heading at the start of the line. A substring count also reads prose mentions. See [gate-pinned-from-real-content.md](gate-pinned-from-real-content.md) §11.5.

---

*Cross-references: [gate-pinned-from-real-content.md](gate-pinned-from-real-content.md) §11.5 (a section is counted by a line-anchored heading test, never by substring) · [gate-denominator-integrity.md](gate-denominator-integrity.md) (a prose claim about a grep result is itself grep-visible) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
