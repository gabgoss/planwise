---
description: Family index stub for verification-gate evidence — which short gate-* reference governs a positive or mutation control, a fixture's provenance, a live gate that disagrees with correct work, an old-home citation sweep, a generated input that silently empties a gate, a script's emitted reason or exit code, a proof run's scratch root and import order, an input set that could not have contained the case that fails the gate, or a gate satisfiable by destruction or unsatisfiable by construction; names the topic files, whose library rows carry the read-when text.
consult-when: Finding which gate reference governs what a gate's output is evidence of — the family index: a read-when table over the `gate-*` topic files it indexes and the map from this file's former section numbers to the topic file that now holds each one
paths: {planwise_root}/{plans_dir}/**
---

# Verification-Gate Evidence (Family Index)

**Purpose:** The index stub for the verification-gate evidence family: the gap between *"the gate returned this"* and *"this is true"*. The rules live in short `gate-*` topic files. They were split out of this file on 2026-10-08, when it passed the Read-tool token gate. [00-Reference-Library.md](00-Reference-Library.md) now carries the index: each topic file's row gives its read-when text and its section numbers.

**Topic files:** [gate-positive-and-mutation-controls.md](gate-positive-and-mutation-controls.md), [gate-fixture-provenance.md](gate-fixture-provenance.md), [gate-artifact-over-instrument.md](gate-artifact-over-instrument.md), [gate-old-home-citation-sweep.md](gate-old-home-citation-sweep.md), [gate-generated-input-integrity.md](gate-generated-input-integrity.md), [gate-script-output-assertions.md](gate-script-output-assertions.md), [gate-environment-inputs.md](gate-environment-inputs.md), [gate-discriminating-case.md](gate-discriminating-case.md) and [gate-satisfiability.md](gate-satisfiability.md).

**Former section numbers:** The redirect table in `scripts/check_section_citations.py` resolves a citation of the form `verification-gate-evidence.md §N` to the topic file that keeps the number. `gate-discriminating-case.md` and `gate-satisfiability.md` hold new rules under their own numbering, so such a citation never resolves there.

---

*Cross-references: [verification-gates.md](verification-gates.md) (the instrument's proof obligations and change- versus state-detecting shapes), [verification-task-authoring.md](verification-task-authoring.md) (the match pattern, the verdict and the pre-edit baseline), [gate-predicate-discrimination.md](gate-predicate-discrimination.md), [gate-denominator-integrity.md](gate-denominator-integrity.md), [gate-baseline-independence.md](gate-baseline-independence.md), [measurement-discipline.md](measurement-discipline.md) §8.5 and §8.7.*
