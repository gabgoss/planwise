---
description: Family index for verification-task authoring — which short gate-* reference governs a match pattern, a verdict, an absence check, a pre-edit baseline, an input set, an anchor's outcome set, a command's semantics, or a gate pinned before its subject exists; carries the §7 authoring checklist; the checker's redirect table resolves this file's former section numbers.
consult-when: Finding which gate reference governs a verification task — the family index: a read-when table over the eight `gate-*` topic files it indexes, the §7 authoring checklist, and the map from this file's former section numbers to the topic file that now holds each one
paths: {planwise_root}/{plans_dir}/**
---

# Verification-Task Authoring (Family Index)

**Purpose:** The index for the verification-task authoring family. The rules live in the short topic files below. They were split out of this file on 2026-10-08, when it passed the Read-tool token gate. Each topic file keeps the section numbers this file used. A citation of the form `verification-task-authoring.md §N` resolves in the topic file that keeps the number, through the checker's redirect table.

**Read this when** you author, review or run a verification task whose body is a match pattern plus a pass/fail criterion. Open the topic file the table names. Read this index only to find it.

## Table of Contents

- [Topic Files](#topic-files)
- [7. Authoring Checklist](#7-authoring-checklist)
- [Section Map](#section-map)

---

## Topic Files

| File | Sections | Read when |
|------|----------|-----------|
| [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) | §1-§4, §9, §13, Checks 058 and 059 | you write a count threshold, a coverage ratio, a keyword-proximity heuristic, a bare "condition ⇒ defect" rule for a runner, or a predicate that counts |
| [gate-verdict-contract-and-adjudication.md](gate-verdict-contract-and-adjudication.md) | §5-§6, Check 060 | you write a verifier's output template, Actual contradicts Expected, or a BLOCKER arrives from a heuristic |
| [gate-absence-and-consistency.md](gate-absence-and-consistency.md) | §8 | you write a `grep -c TOKEN == 0` criterion, a comment-stripped, phrase or prefix-form absence gate, a gate whose expected result is a non-zero constant, a subset consistency check, or a status flip over a file that states one fact twice |
| [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) | §10-§10.4, Check 082 | you write or review an After-block gate, or the gate linter reports Check 1 or Check 2 |
| [gate-input-set-and-compared-window.md](gate-input-set-and-compared-window.md) | §10.6, §12, §14, §14.1, §15, §16, Checks 104, 105 and 110 | a criterion is fed by a pinned diff or a sweep, a proof compares string literals and reports a difference count, a task selects its own work with a pattern and checks success against that pattern's count, a pull uses a fixed `-B` or `-A` window around a structured entry, a relational anchor may compare two empty sides, or a comment or criterion names a population (a file list, every row, a headline count) that a command's pattern must cover |
| [gate-anchor-outcome-set.md](gate-anchor-outcome-set.md) | §10.7-§10.7.2, §10.10, §10.11, §10.12, Checks 095, 112 and 119 | you write a Signoff anchor, an exit criterion, an Execution Input gate, or a `git diff --stat` allowed set over a regenerated directory, a task's Success Criteria discharge a sprint criterion, or a success criterion matches an internal table against an external listing |
| [gate-command-semantics.md](gate-command-semantics.md) | §10.8-§10.9.1, Check 114 | you pin any `grep`, `diff`, `wc` or `awk` gate, a gate returns a plausible value on work you know is correct, or you write a Verification Commands entry that must run in the target environment |
| [gate-pinned-from-real-content.md](gate-pinned-from-real-content.md) | §10.5, §11 | the thing a gate measures does not exist yet, sits in a content block you wrote, comes from a tool whose output you have not seen, or is a Markdown verdict line or heading |

---

## 7. Authoring Checklist

> [!checklist] Verification-task spec — pre-publish checks
> - [ ] No anchored aggregate count threshold (`grep -cE '^…' … expect ≥N`) used as the sole pass/fail gate — replace with per-unit existence assertions (`gate-heuristic-verifier-patterns.md` §2, lint Check 15).
> - [ ] Match patterns cross-read against every sibling extraction task's output formats; format union documented in Required Context (`gate-heuristic-verifier-patterns.md` §3).
> - [ ] Coverage denominators scope-restricted to real construct instances; prose, table rows, and fenced code excluded — OR check re-classified as `INVESTIGATE` (`gate-heuristic-verifier-patterns.md` §4).
> - [ ] Verdict-arithmetic contract honored for every gate type, plain count-equality gates included: if Actual contradicts Expected per the comparison operator, the verdict is FAIL or `[UNCERTAIN]`, never PASS (`gate-verdict-contract-and-adjudication.md` §5).
> - [ ] BLOCKER-from-heuristic adjudication protocol declared in the orchestration — orchestrator validates flagged sites against source before routing rework (`gate-verdict-contract-and-adjudication.md` §6).
> - [ ] Every gate carries its measured pre-edit value inline, and that value contradicts the expectation — or the gate is marked `invariant:` (`gate-pre-edit-baseline.md` §10.1-§10.3, lint Checks 1, 2 and 7).
> - [ ] Every per-task gate is scoped to its task's files. Each whole-population baseline is measured once per plan with its tree identity recorded (`gate-pre-edit-baseline.md` §10.1.1).
> - [ ] Every gate target is classified session-owned or shared, and a shared target asserts a delta from a Before derived in the same invocation (`gate-pre-edit-baseline.md` §10.1.2).
> - [ ] Every anchor's accepted-outcome set diffed against its owning task's terminal branches, and the count carried inline (`gate-anchor-outcome-set.md` §10.7).
> - [ ] Every anchor names the phase that produces its subject, a closeout-phase anchor is marked post-verdict with a bound re-run, and a stale anchor pattern is widened, never satisfied by editing a committed artifact of record (`gate-anchor-outcome-set.md` §10.7.1-§10.7.2).
> - [ ] All four command-semantics traps checked: `grep -c` counts lines, `-B1` emits the match, set membership is not count equality, every path resolves from the declared cwd (`gate-command-semantics.md` §10.8, lint Checks 3 and 14 for the first two; the last two have no check).
> - [ ] Every Verification Commands entry uses the project's own interpreter, names an agent-invocable step and only paths that exist on the target OS, carries the exit code of an executed run or a read-only probe, and runs a direct script probe under `python -B` (`gate-command-semantics.md` §10.9.1).
> - [ ] Every native `Grep` call writes alternation as a bare `|`, and no alternation pattern sits in a markdown table cell (`gate-command-semantics.md` §10.9.1).
> - [ ] A mutation-control criterion names the guard, not a test: "each guard has a test that fails when only that guard is disabled", with one minimal input per guard and the mutated symbol's own return value asserted (`gate-predicate-discrimination.md` §14 and §15).
> - [ ] A proof that two literal sets are verbatim reports the size of the compared set and extracts from the function body only (`gate-input-set-and-compared-window.md` §12).
> - [ ] Every selection pattern a task's scope depends on is dry-run against known-bad input, every count it feeds is checked against an independent non-empty assertion, and every fixed context window is sized from the schema maximum, and every relational anchor prints its vacuity, records PASS (vacuous) and schedules a DEFERRED measurement for the first non-empty day (`gate-input-set-and-compared-window.md` §14, §14.1 and §15).
> - [ ] Every measurement criterion was asked "what value could be wrong while this still passes?". At least one criterion ties a produced value to its evidence, and no expected value is a data-state literal (`exit-criteria-fidelity.md` §16.10.1, `exit-criteria-fidelity-Part-2-DecisionLeavesCriteriaStale.md` §16.19).
> - [ ] Every population a comment or criterion names (a file list, every row, a named pair, a headline count) is listed as one row per member, and the command's expanded pattern reaches exactly those members (`gate-input-set-and-compared-window.md` §16).
> - [ ] A task that discharges a sprint criterion quotes it and names a gate that measures the criterion's own comparand, population and operator, and sibling criteria are reconciled against one real artifact (`gate-anchor-outcome-set.md` §10.11).
> - [ ] A criterion that matches an internal table against an external listing gives a verdict for all four cells (records present or absent, source lists them or not), and a sentence about the source's coverage is quoted from the probe document (`gate-anchor-outcome-set.md` §10.12, `verify-before-cite.md` §9.B.27).
> - [ ] An anchor or verification command that runs a writer (`--write`, `--fix`, `--apply`, an upgrade flag) names a scratch target (`exit-criteria-fidelity.md` §16.10.7).
> - [ ] An absence gate over a file the brief tells the author to document passes the test question "Where does this brief tell the author to write prose, and can my filter see it?". A phrase or prefix-form absence gate uses the joined form or a window check, with its base count recorded (`gate-absence-and-consistency.md` §8.4-§8.6).

---

## Section Map

The redirect table in `scripts/check_section_citations.py` holds this file's former section numbers, and the topic file that holds each one keeps the number. §7 stays here.

---

*Cross-references: [verification-gates.md](verification-gates.md) (cross-process runtime gates and the recorded baseline commit a diff gate reads), [verification-gate-evidence.md](verification-gate-evidence.md) (what a gate's output is evidence of), [gate-predicate-discrimination.md](gate-predicate-discrimination.md), [gate-denominator-integrity.md](gate-denominator-integrity.md), [gate-baseline-independence.md](gate-baseline-independence.md) (the three gate references that were never part of this file).*
