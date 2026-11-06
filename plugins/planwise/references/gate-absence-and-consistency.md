---
description: An absence-grep criterion scrubs its token from every surface including the gate's own prose and legend (§8.1), a consistency check asserts against the right population rather than a conditional set against an observed union (§8.2), and a file that encodes one fact in two representations is updated in both on every mutation and verified against the file (§8.3). A comment-strip pre-filter sees only whole-line comments, so the dialect table says when to reword the prose and when to replace the instrument (§8.4). A phrase-absence criterion counts the joined form (§8.5). A banned form that is a prefix of the correct form needs a window check (§8.6).
consult-when: Writing a `grep -c TOKEN == 0` criterion, a subset consistency check, or a status flip over a file that states one fact twice — scrub the token everywhere (§8.1), assert against the right population (§8.2), update both representations (§8.3), or a comment-stripped, phrase or prefix-form absence gate — the dialect table (§8.4), the joined form (§8.5), the window check (§8.6)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Absence and Consistency Checks (Scrub, Scope, and Sync)

**Purpose:** Six gate shapes that return a false verdict on a correct artifact: an absence grep that matches its own description, a subset assertion against the wrong population, a parse-side check that never reads the prose copy of the same fact, an absence filter that cannot see a docstring or a trailing comment, a phrase wrapped across lines, and a banned form that is a prefix of the correct form. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you write a `grep -c TOKEN == 0` criterion, a `conditional ⊆ observed` consistency check, or a status flip over a file that states the same count in a code block and in prose. Read it too when an absence criterion strips comments first, counts a multi-word phrase, or bans a string that the correct form still contains.

## Table of Contents

- [8. Absence and Consistency Gates — Scrub, Scope, and Sync](#8-absence-and-consistency-gates--scrub-scope-and-sync)
  - [8.1 An absence-grep requires scrubbing the token everywhere](#81-an-absence-grep-requires-scrubbing-the-token-everywhere)
  - [8.2 Assert against the right population](#82-assert-against-the-right-population)
  - [8.3 One file encoding a fact twice — every mutation updates both](#83-one-file-encoding-a-fact-twice--every-mutation-updates-both)
  - [8.4 A comment-strip pre-filter sees only whole-line comments — reword the prose or replace the instrument](#84-a-comment-strip-pre-filter-sees-only-whole-line-comments--reword-the-prose-or-replace-the-instrument)
  - [8.5 A phrase-absence criterion counts the joined form](#85-a-phrase-absence-criterion-counts-the-joined-form)
  - [8.6 A banned form that is a prefix of the correct form needs a window check](#86-a-banned-form-that-is-a-prefix-of-the-correct-form-needs-a-window-check)

---

## 8. Absence and Consistency Gates — Scrub, Scope, and Sync

### 8.1 An absence-grep requires scrubbing the token everywhere

> [!constraint] An absence-grep criterion MUST scrub the literal token from every surface, not just data cells
> A criterion of the form `grep -c 'TOKEN' {file} == 0` proves absence of a TOKEN-class item. Satisfying it requires the literal token to appear nowhere — not merely absent from data cells. It must be scrubbed from the classification legend, count-block labels, section headers, descriptive prose, and any self-referential mention of the grep itself. Replace with a synonym. Grep is case-sensitive, so lowercase variants are safe; run the exact anchor command yourself before declaring the criterion met.
>
> Observed false-FAIL: the criterion's own grep returned 8 against a file with zero unresolved data cells — every hit was the legend, the label, and the criterion's own description.

An absence criterion also false-fails when it counts the artifact that enacts the absence, which must name its target: see [exit-criteria-fidelity.md](exit-criteria-fidelity.md) §16.9.1, "The Enactor Cause — Exclude the Artifact That Enacts the Absence".

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

### 8.4 A comment-strip pre-filter sees only whole-line comments — reword the prose or replace the instrument

A pre-filter that removes comment lines before an absence count depends on the file dialect. It strips a whole-line comment and nothing else. A trailing comment begins with code, so no line filter removes it.

| Target | Pre-filter | What it misses |
|--------|------------|----------------|
| `.py` | `grep -vE '^\s*#'` | Everything except a whole-line comment |
| `.sql` | `grep -vE '^\s*--'` | A `/* ... */` block |
| `.ipynb` | `grep -vE '^\s*"\s*#'` | The `.py` filter strips nothing here, because a notebook comment is a JSON string element |
| Docstring | none | A docstring is a string literal, so no line-anchored filter strips it |
| Markdown cell | none | A markdown cell is a plain JSON string, so no line-anchored filter strips it |
| Trailing comment | none | The line begins with code, so the whole-line filter keeps it |

> [!constraint] Reword the prose when a synonym keeps the meaning, and replace the instrument when the token must appear
> A brief that tells the author to explain why a token is absent, and also requires an absence count of that token to be 0, cannot be satisfied. Two fixes exist.
>
> - Reword the prose to a synonym, but only when the synonym keeps the meaning. Never delete correct documentation to quiet a gate.
> - Replace the instrument when the token must appear. Parse the module with `ast`, drop the docstring nodes, then count. For a notebook, parse with `nbformat` and skip the markdown cells.
>
> Prove the replacement in both directions. Run it against a known-bad fixture and against the shipped file.
>
> Before you pin the gate, ask: "Where does this brief tell the author to write prose, and can my filter see it?"
>
> A criterion written in a backlog item's acceptance list, or in an orchestrator's ad-hoc check, gets no review pass. It carries the pre-filter from the start.

### 8.5 A phrase-absence criterion counts the joined form

A hard-wrapped comment can break a multi-word phrase across two lines. A single-line count then reads 0 on the unedited base file, so the gate cannot fail. [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) Obligation C covers multi-line code idioms. It does not cover wrapped prose.

> [!constraint] Join the lines, strip the comment markers, and record a base count of at least 1
> Count the joined form by default. Record the base count in the brief. A base count of at least 1 proves the gate can see the phrase. The alternative is a short distinctive fragment that fits on one line, with its base count stated.

The recipe below is CRLF-safe. The first command reads the base revision and the second reads the working file.

```bash
git show {base}:{file} | tr -d '\r' | sed 's/^[[:space:]]*-- *//' | tr '\n' ' ' | tr -s ' ' | grep -o "{phrase}" | wc -l   # MUST be >= 1
tr -d '\r' < {file} | sed 's/^[[:space:]]*-- *//' | tr '\n' ' ' | tr -s ' ' | grep -o "{phrase}" | wc -l                    # MUST be 0
```

### 8.6 A banned form that is a prefix of the correct form needs a window check

A fix can append a qualifier to a flag, so `--old-flag` becomes `--old-flag --qualifier`. The banned string now appears at every correct site. No comment filter helps. A line-scoped exclusion fails as soon as the command wraps.

> [!constraint] Check a window after the banned form, and prove it on two trees
> Test whether the banned form lacks its qualifier within the next N lines. Skip deliberate WRONG examples. Prove the check against the pre-fix revision, where it returns a non-zero count that you record. Then prove it against the fixed tree, where it returns 0. Use invented sample flags and paths in the brief.

---

*Cross-references: [gate-pinned-from-real-content.md](gate-pinned-from-real-content.md) §11.5 (a section is counted by a line-anchored heading test, never by substring) · [gate-denominator-integrity.md](gate-denominator-integrity.md) (a prose claim about a grep result is itself grep-visible) · [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) Obligation C (a multi-line code idiom needs a matcher that sees it, and §8.5 covers wrapped prose) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
