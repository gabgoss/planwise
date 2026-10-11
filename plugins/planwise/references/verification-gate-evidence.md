---
description: Family index for verification-gate evidence — which short gate-* reference governs a positive or mutation control, a fixture's provenance, a live gate that disagrees with correct work, an old-home citation sweep, a generated input that silently empties a gate, a script's emitted reason or exit code, or a proof run's scratch root and import order; carries the map from this file's former section numbers to the topic files that now hold them.
paths: {planwise_root}/{plans_dir}/**
---

# Verification-Gate Evidence (Family Index)

**Purpose:** The index for the verification-gate evidence family: the gap between *"the gate returned this"* and *"this is true"*. The rules live in the short topic files below. They were split out of this file on 2026-10-08, when it passed the Read-tool token gate. Each topic file keeps the section numbers this file used, so a citation of the form `verification-gate-evidence.md §N` resolves through the section map at the end of this file. `verification-task-authoring.md` indexes the match-pattern rules, and `verification-gates.md` indexes the instrument's proof obligations.

**Read this when** you author a guard, hook, linter, validation pass or "MUST be empty" check, you are about to cite one as proof, your correct edit and a gate disagree, a gate fails everything, you sweep for citations after moving a section, or a gate reads a generated list, a script's output or a checked-in file's bytes. Open the topic file the table names. Read this index only to find it.

## Table of Contents

- [Topic Files](#topic-files)
- [Section Map](#section-map)

---

## Topic Files

| File | Sections | Read when |
|------|----------|-----------|
| [gate-positive-and-mutation-controls.md](gate-positive-and-mutation-controls.md) | §1-§4, §14 | you author a gate-shaped deliverable or a refusal test, dry-run a MUST-be-N gate, or a gate returns FAIL on every input |
| [gate-fixture-provenance.md](gate-fixture-provenance.md) | §5-§9 | you build a fixture or probe, release a writer or migrator over a user-maintained file, or report what a proof covers |
| [gate-artifact-over-instrument.md](gate-artifact-over-instrument.md) | §10-§13 | your correct edit and a gate's annotated value disagree, a runner says it shaped content to satisfy a gate, or an authoring task is a live gate's subject |
| [gate-old-home-citation-sweep.md](gate-old-home-citation-sweep.md) | §15-§15.3 | you write the exit criterion for a citation sweep after moving a section, or such a sweep returns non-zero on a correct corpus |
| [gate-generated-input-integrity.md](gate-generated-input-integrity.md) | §16, §17, §18, §21 | a gate reads a generated path list or row count, claims bytes or line endings preserved, or a test compares against a checked-in file |
| [gate-script-output-assertions.md](gate-script-output-assertions.md) | §19, §23 | you grade a decision log's rows, or a gate interprets a script's exit code |
| [gate-environment-inputs.md](gate-environment-inputs.md) | §20, §22 | a proof run builds a fixture tree in a shipping tree, or a Python package re-exports or guards imports |

---

## Section Map

A citation written as `verification-gate-evidence.md §N` resolves here. The section keeps its number in the file that now holds it.

| Former section | Now in |
|----------------|--------|
| §1 A Gate-Shaped Deliverable Requires a Positive Control | `gate-positive-and-mutation-controls.md` |
| §2 A Test Whose Subject Is a Refusal Must Be Proven Load-Bearing | `gate-positive-and-mutation-controls.md` |
| §3 Dry-Run Every MUST-be-N Gate in BOTH Directions | `gate-positive-and-mutation-controls.md` |
| §4 Specify the Artifact for the PASS Branch, Not Just the FAIL Branch | `gate-positive-and-mutation-controls.md` |
| §5 A Fixture Must Not Be Built Through the API Under Test | `gate-fixture-provenance.md` |
| §6 A Known-Good Probe Must Name a Real Target | `gate-fixture-provenance.md` |
| §7 A Fixture Set Must Span Input Shapes, §7.1 Writers and Migrators | `gate-fixture-provenance.md` |
| §8 Report What the Proof Does NOT Cover | `gate-fixture-provenance.md` |
| §9 Verify Completeness Against the Spec's Enumeration | `gate-fixture-provenance.md` |
| §10 The Artifact Is Authoritative; the Instrument Is the Defect | `gate-artifact-over-instrument.md` |
| §11 A Gate Annotation Predicts the Shape of Correct Work | `gate-artifact-over-instrument.md` |
| §12 A Disclosure That a Gate Influenced the Artifact Is a Re-Derivation Trigger | `gate-artifact-over-instrument.md` |
| §13 Pre-Adjudicate a Doctrine Artifact's Collision With a Live Gate | `gate-artifact-over-instrument.md` |
| §14 A Gate That Fails Everything Is Not More Trustworthy | `gate-positive-and-mutation-controls.md` |
| §15 An Old-Home Citation Sweep Is a Substring Match, §15.1-§15.3 | `gate-old-home-citation-sweep.md` |
| §16 A File List That Feeds a Gate Is Part of the Gate's Input | `gate-generated-input-integrity.md` |
| §17 A Row-Count Gate and Its Consumer Must Split Lines the Same Way | `gate-generated-input-integrity.md` |
| §18 A Byte-Preservation Claim Is Verified With Bytes | `gate-generated-input-integrity.md` |
| §19 A Decision-Row Gate Asserts the Reason's Value | `gate-script-output-assertions.md` |
| §20 A Proof Run Names Its Scratch Root | `gate-environment-inputs.md` |
| §21 A Test Never Hard-Codes a Checked-In File's Line Endings | `gate-generated-input-integrity.md` |
| §22 A Green Suite Says Nothing About Import Order | `gate-environment-inputs.md` |
| §23 Derive an Exit-Code Gate From the Script's Return Paths | `gate-script-output-assertions.md` |

---

*Cross-references: [verification-gates.md](verification-gates.md) (the instrument's proof obligations and change- versus state-detecting shapes), [verification-task-authoring.md](verification-task-authoring.md) (the match pattern, the verdict and the pre-edit baseline), [gate-predicate-discrimination.md](gate-predicate-discrimination.md), [gate-denominator-integrity.md](gate-denominator-integrity.md), [gate-baseline-independence.md](gate-baseline-independence.md), [measurement-discipline.md](measurement-discipline.md) §8.5 and §8.7.*
