---
description: Family index for verification gates — which short gate-* reference governs a cross-process or build-versus-deploy boundary, a Sprint exit verdict, a diff-scoped gate's recorded base, the instrument's proof obligations, change- versus state-detecting shapes, or a run sheet's control; carries the reserved section numbers (§9 relocated, §12 a pointer), the `$..._BASE` definition pointer, and the map from this file's former section numbers to the topic files that now hold them.
paths: {planwise_root}/{plans_dir}/**
---

# Verification Gates (Family Index)

**Purpose:** The index for the verification-gates family. The rules live in the short topic files below. They were split out of this file on 2026-10-08, when it passed the Read-tool token gate. Each topic file keeps the section numbers this file used, so a citation of the form `verification-gates.md §N` resolves through the section map at the end of this file.

**Read this when** a session touches an IPC, protocol or codec boundary, writes a Sprint exit verdict, builds a gate on `git diff`, delivers a gate-shaped artifact, composes a verification battery, or pins a run sheet. Open the topic file the table names. Read this index only to find it.

## Table of Contents

- [Topic Files](#topic-files)
- [Reserved Section Numbers](#reserved-section-numbers)
- [Section Map](#section-map)

---

## Topic Files

| File | Sections | Read when |
|------|----------|-----------|
| [gate-runtime-boundary-evidence.md](gate-runtime-boundary-evidence.md) | §1, §2, §5, §6, §7 | a deliverable touches an IPC, protocol or codec boundary, in-process numeric or codec code, a deploy step, or multi-target runtime code |
| [gate-exit-verdict-and-smoke-reports.md](gate-exit-verdict-and-smoke-reports.md) | §3, §4, Checks 013, 014, 015, 034, 035, 036 | you write a Sprint Overview status, a smoke report or a closeout Recovery file, or review Verification Commands for a notebook, lint or database task |
| [gate-diff-baseline-pinning.md](gate-diff-baseline-pinning.md) | §8-§8.6, Check 077 | you write, review or run any gate built on `git diff`, or pin a sprint or series base. This file defines `$..._BASE` |
| [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) | §10, Checks 087, 088 | a deliverable is a gate, guard, hook, linter or validation pass, or a criterion cites a gate run as proof |
| [gate-change-vs-state-detecting.md](gate-change-vs-state-detecting.md) | §11-§11.5 | you compose a battery, a change adds a member to an enumerated set, or you write or accept an extractor that anchors on a string |
| [gate-run-sheet-and-grader-fields.md](gate-run-sheet-and-grader-fields.md) | §13, §14 | you write a run sheet or probe driver that pins flags, or a grader predicate over a numeric log field |

---

## Reserved Section Numbers

Two numbers stay reserved here so citations to them keep resolving.

**§9 Empirical Verification Discipline** — relocated to [measurement-discipline.md](measurement-discipline.md) §8 (wc-l line-count authority over Read-output line numbers, broad-gate authority over an audit's file enumeration, headline-metric reconciliation, doctrinal-claim surface sweeps, markdown-field normalization on both read and write, idempotency-safe append/author, gate-input-set verification before trusting a predicate, and post-behavior-change surface sweeps).

**§12 Reachability Gates — a Definition Is Not a Caller.** Every gate in the topic files above measures **presence**; none measures whether production ever reaches the thing. The reachability gate — assert a **caller** that supplies the activating argument, not a definition; quote a production call site per behaviour-adding deliverable in the closing-sweep ledger; classify a runner's "dormant until a follow-up wires it" return as PARTIAL, never COMPLETE — lives in its own reference: [verify-caller-before-complete.md](verify-caller-before-complete.md). The body is not restated here.

**`$..._BASE`** is defined in [gate-diff-baseline-pinning.md](gate-diff-baseline-pinning.md) §8. A citation of "`verification-gates.md` §8 as the definition site" resolves there.

---

## Section Map

A citation written as `verification-gates.md §N` resolves here. The section keeps its number in the file that now holds it.

| Former section | Now in |
|----------------|--------|
| §1 The Two Failure Modes | `gate-runtime-boundary-evidence.md` |
| §2 Round-Trip Evidence for Cross-Process Boundaries | `gate-runtime-boundary-evidence.md` |
| §3 The Gate Is the Gate (Checks 013, 014, 034, 035, 036) | `gate-exit-verdict-and-smoke-reports.md` |
| §4 Operational Rules for Smoke Reports (Check 015) | `gate-exit-verdict-and-smoke-reports.md` |
| §5 Build-Clean ≠ Computation-Correct | `gate-runtime-boundary-evidence.md` |
| §6 Build-Fresh ≠ Deploy-Fresh | `gate-runtime-boundary-evidence.md` |
| §7 Runtime-Correct on One Target ≠ Correct on All Targets | `gate-runtime-boundary-evidence.md` |
| §8 Diff-Scoped Gates Pin a Recorded Baseline, §8.1-§8.6 (Check 077) | `gate-diff-baseline-pinning.md` |
| §9 Empirical Verification Discipline | `measurement-discipline.md` §8 (relocated earlier) |
| §10 The Instrument's Four Proof Obligations (Checks 087, 088) | `gate-instrument-proof-obligations.md` |
| §11 Change-Detecting vs State-Detecting Gates, §11.1-§11.5 | `gate-change-vs-state-detecting.md` |
| §12 Reachability Gates | this file (pointer to `verify-caller-before-complete.md`) |
| §13 A Run Sheet Pins the Field the Hook Reads | `gate-run-sheet-and-grader-fields.md` |
| §14 A Grader Treats a Null Numeric Field as a Failed Measurement | `gate-run-sheet-and-grader-fields.md` |

---

*Decide and assert on the same measurement (a splitter that measures the body while the assembler measures the file leaves a window that refuses correct input): [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §12.*

*Cross-references: [verification-gate-evidence.md](verification-gate-evidence.md) (what a gate's output is evidence of), [verification-task-authoring.md](verification-task-authoring.md) (match patterns, verdicts and pre-edit baselines), [session-execution-protocol.md](session-execution-protocol.md) (Recovery-file update discipline at closeout), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Sprint exit-gate semantics in Master Plan / Sprint Plan rows), [measurement-discipline.md](measurement-discipline.md) (§8 Empirical Verification Discipline, split from this file).*
