---
description: Family index for verification-task authoring — which short gate-* reference governs a match pattern, a verdict, an absence check, a pre-edit baseline, an input set, an anchor's outcome set, a command's semantics, or a gate pinned before its subject exists; carries the §7 authoring checklist and the map from this file's former section numbers to the topic files that now hold them.
paths: {planwise_root}/{plans_dir}/**
---

# Verification-Task Authoring (Family Index)

**Purpose:** The index for the verification-task authoring family. The rules live in the short topic files below. They were split out of this file on 2026-10-08, when it passed the Read-tool token gate. Each topic file keeps the section numbers this file used, so a citation of the form `verification-task-authoring.md §N` resolves through the section map at the end of this file.

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
| [gate-absence-and-consistency.md](gate-absence-and-consistency.md) | §8 | you write a `grep -c TOKEN == 0` criterion, a subset consistency check, or a status flip over a file that states one fact twice |
| [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) | §10-§10.4, Check 082 | you write or review an After-block gate, or the gate linter reports Check 1 or Check 2 |
| [gate-input-set-and-compared-window.md](gate-input-set-and-compared-window.md) | §10.6, §12 | a criterion is fed by a pinned diff or a sweep, or a proof compares string literals and reports a difference count |
| [gate-anchor-outcome-set.md](gate-anchor-outcome-set.md) | §10.7, §10.10, Check 095 | you write a Signoff anchor, an exit criterion, an Execution Input gate, or a `git diff --stat` allowed set over a regenerated directory |
| [gate-command-semantics.md](gate-command-semantics.md) | §10.8-§10.9 | you pin any `grep`, `diff`, `wc` or `awk` gate, or a gate returns a plausible value on work you know is correct |
| [gate-pinned-from-real-content.md](gate-pinned-from-real-content.md) | §10.5, §11 | the thing a gate measures does not exist yet, sits in a content block you wrote, comes from a tool whose output you have not seen, or is a Markdown verdict line or heading |

---

## 7. Authoring Checklist

> [!checklist] Verification-task spec — pre-publish checks
> - [ ] No anchored aggregate count threshold (`grep -cE '^…' … expect ≥N`) used as the sole pass/fail gate — replace with per-unit existence assertions (`gate-heuristic-verifier-patterns.md` §2).
> - [ ] Match patterns cross-read against every sibling extraction task's output formats; format union documented in Required Context (`gate-heuristic-verifier-patterns.md` §3).
> - [ ] Coverage denominators scope-restricted to real construct instances; prose, table rows, and fenced code excluded — OR check re-classified as `INVESTIGATE` (`gate-heuristic-verifier-patterns.md` §4).
> - [ ] Verdict-arithmetic contract honored: if Actual contradicts Expected per the comparison operator, the verdict is FAIL or `[UNCERTAIN]`, never PASS (`gate-verdict-contract-and-adjudication.md` §5).
> - [ ] BLOCKER-from-heuristic adjudication protocol declared in the orchestration — orchestrator validates flagged sites against source before routing rework (`gate-verdict-contract-and-adjudication.md` §6).
> - [ ] Every gate carries its measured pre-edit value inline, and that value contradicts the expectation — or the gate is marked `invariant:` (`gate-pre-edit-baseline.md` §10.1-§10.3).
> - [ ] Every anchor's accepted-outcome set diffed against its owning task's terminal branches, and the count carried inline (`gate-anchor-outcome-set.md` §10.7).
> - [ ] All four command-semantics traps checked: `grep -c` counts lines, `-B1` emits the match, set membership is not count equality, every path resolves from the declared cwd (`gate-command-semantics.md` §10.8).
> - [ ] A mutation-control criterion names the guard, not a test: "each guard has a test that fails when only that guard is disabled", with one minimal input per guard and the mutated symbol's own return value asserted (`gate-predicate-discrimination.md` §14 and §15).
> - [ ] A proof that two literal sets are verbatim reports the size of the compared set and extracts from the function body only (`gate-input-set-and-compared-window.md` §12).
> - [ ] An anchor or verification command that runs a writer (`--write`, `--fix`, `--apply`, an upgrade flag) names a scratch target (`exit-criteria-fidelity.md` §16.10.7).

---

## Section Map

A citation written as `verification-task-authoring.md §N` resolves here. The section keeps its number in the file that now holds it.

| Former section | Now in |
|----------------|--------|
| §1 Failure Shape — Heuristic Verifiers Producing False Verdicts | `gate-heuristic-verifier-patterns.md` |
| §2 Per-Unit Existence Assertions, Not Aggregate Count Thresholds (Check 058) | `gate-heuristic-verifier-patterns.md` |
| §3 Match Patterns Derived From Sibling Extraction Tasks | `gate-heuristic-verifier-patterns.md` |
| §4 Denominator Scoping — Count Real Instances Only (Check 059) | `gate-heuristic-verifier-patterns.md` |
| §5 PASS Requires Actual = Expected, §5.1 A Check That Could Not Be Run Returns UNCERTAIN | `gate-verdict-contract-and-adjudication.md` |
| §6 Orchestrator Adjudication of BLOCKER-From-Heuristic (Check 060) | `gate-verdict-contract-and-adjudication.md` |
| §7 Authoring Checklist | this file |
| §8 Absence and Consistency Gates (§8.1-§8.3) | `gate-absence-and-consistency.md` |
| §9 A bare heuristic in a task brief must state its exclusions | `gate-heuristic-verifier-patterns.md` |
| §10 Every Gate Records Its Measured Pre-Edit Value, §10.1-§10.4, Check 082 | `gate-pre-edit-baseline.md` |
| §10.5 A gate over a verification report reads the verdict line | `gate-pinned-from-real-content.md` |
| §10.6 A diff-pinned or sweep-based criterion records its input-set counts | `gate-input-set-and-compared-window.md` |
| §10.7 An anchor accepts exactly the outcome set its own task can produce (Check 095) | `gate-anchor-outcome-set.md` |
| §10.8 Four command semantics, §10.9 Read the command as a program | `gate-command-semantics.md` |
| §10.10 A re-capture gate's allowed set names the files that change on every capture | `gate-anchor-outcome-set.md` |
| §11 A Gate Is Pinned From a Run Over Real Content (§11.1-§11.5) | `gate-pinned-from-real-content.md` |
| §12 A Verbatim-Literal Proof Extracts From the Body | `gate-input-set-and-compared-window.md` |
| §13 A Predicate That Counts Names Its Unit | `gate-heuristic-verifier-patterns.md` |

---

*Cross-references: [verification-gates.md](verification-gates.md) (cross-process runtime gates and the recorded baseline commit a diff gate reads), [verification-gate-evidence.md](verification-gate-evidence.md) (what a gate's output is evidence of), [gate-predicate-discrimination.md](gate-predicate-discrimination.md), [gate-denominator-integrity.md](gate-denominator-integrity.md), [gate-baseline-independence.md](gate-baseline-independence.md) (the three gate references that were never part of this file).*
