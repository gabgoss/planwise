---
description: A gate's output is evidence only after four independent obligations are discharged — it can fail, shown by a fixture that reproduces the defect and a run of the same probe on the unfixed artifact (A); it does not fail correct work (B); it can see the shape it counts (C); and it is pointed at the live subject as well as at fixtures (D); Reviewer Checks 087 and 088.
consult-when: A deliverable is a gate, guard, hook, linter or validation pass, or a criterion cites a gate run as proof — the gate can fail (A), does not fail correct work (B), sees the shape it counts (C), is pointed at the live subject (D); Checks 087 and 088
paths: {planwise_root}/{plans_dir}/**
---

# Gate Instrument Proof Obligations (Four Things a Gate Proves Before Its Output Is Evidence)

**Purpose:** Split from `verification-gates.md` (the family index) on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gates.md §N` citation translates by filename alone.

**Read this when** a task's deliverable is a gate, a guard, a hook, a linter or a validation pass, an acceptance criterion cites a gate run as proof, or a bug-fix deliverable's criteria name no fixture that reproduces the defect.

## Table of Contents

- [10. The Instrument's Four Proof Obligations](#10-the-instruments-four-proof-obligations)

---

## 10. The Instrument's Four Proof Obligations

The runtime, verdict and baseline rules in `gate-runtime-boundary-evidence.md`, `gate-exit-verdict-and-smoke-reports.md` and `gate-diff-baseline-pinning.md` ask whether the right thing was measured. This section asks a prior question: **is the instrument itself sound?** A gate's output is evidence only after the gate has discharged four obligations, and they are **independent** — passing any one says nothing about the other three.

| Obligation | The question | Failure it admits |
|---|---|---|
| A | Can it fail at all? | A criterion already satisfied before the work starts |
| B | Does it fail *correct* work? | A gate measuring form, exerting pressure to reformat correct content |
| C | Can it see the shape it counts? | A single-line matcher against a multi-line idiom |
| D | Does a proven instrument mean a clean subject? | A fixture dry-run reported as if it were a live sweep |

> [!constraint] Obligation A — the gate must be able to fail
> ```
> WRONG  AC: "re-run the tool and confirm the open-item count equals the number of non-closed rows"
>          -> 17 open, 17 reported. PASS — and identically on unfixed code, because the
>             triggering rows were reworded as a workaround. It measured sanitised data.
> CORRECT AC: "run every parser on a clean row AND on a row containing a \| b;
>              require identical, correct column assignment"
>          -> fixed tree: PASS    unfixed tree: FAIL   # the FAIL proves the gate discriminates
> ```
>
> 1. **A criterion evaluated against live project data measures the data, not the code.** It is a regression guard, never evidence the fix works. Phrase at least one criterion against a **fixture that reproduces the defect**, and name the discriminating criterion.
> 2. **Run the same probe against the unfixed artifact** — the previous commit, the installed older version, a copy with the fix reverted — **and show it failing.**
> 3. **Run a reproduction recipe on the known-bad state before pinning it, and read the flag's implementation, not its name.** `--show-blocked` routes blocked items into the selectable list, so its "blocked by:" summary never prints. One `Grep` for the flag in the parser and its consumer settles what it does.
>
> **A criterion already satisfied at triage time is a finding, not a tick.** Record it with its reason. A criterion structurally incapable of failing again is a defect in the criterion. Prefer "demonstrably correct" to "demonstrably different": two outputs that merely differ can both be wrong.

> [!constraint] Obligation B — the gate must not fail correct work
> A gate must assert **the property you care about**, not a spelling of it. For a citation the property is **resolution**: the file exists at the path given, the section exists in it, no placeholder token remains. A typography pattern such as `{file}\.md §[0-9]+` scores 0 on a correct citation whose file name sits in backticks, the house style, and 1 on a citation to a file that does not exist. A spelling-tolerant pattern still checks only the shape. Only a check that reads the named file and confirms the heading fails a citation whose target moved.
>
> **The authoring test:** *what would a correct-but-differently-formatted artifact score?* If FAIL, the gate measures form. **Dry-run against a known-GOOD file in the house style, not only against known-bad.** **When a runner reports that it reformatted content to satisfy a gate, that is a gate-defect report, not a completion detail** — read it as one.

> [!constraint] Obligation C — the gate must be able to see the shape it counts
> A single-line pattern against a multi-line idiom undercounts: one sweep reported 14 sites where the real count was 64+2. Before trusting a pattern, **Count the idiom's ANCHOR and its CONTINUATION separately** (a large gap means the pattern is single-line and the idiom is not), and **Read one real instance before writing the pattern.** Prefer structure-independent matchers, in this order: a **multiline matcher**; better, a **structural check** that parses the file and walks its call nodes; for a mechanical rename, a **normalization diff** that undoes the rename and expects an additions-only diff.
>
> **Finding a defect class does not immunize you against it** — the sweep written to catch it can carry the same flaw. **Delegation corollary:** an orchestrator-supplied count is a **cross-check with halt-on-disagreement**, never the answer.

> [!practice] Obligation D — discrimination is not cleanliness
> A **Fixture dry-run** answers *can this gate tell bad from good?* A **Live sweep** answers *is the thing it guards actually clean?* Neither substitutes for the other: an empty sweep from an instrument nobody proved discriminating says nothing. The live sweep is the one acceptance criteria skip.
>
> 1. **Run both, in order, and report the two outputs separately.**
> 2. **Expect the live sweep to produce findings outside the item's file list**, and treat that as the deliverable working. A repair whose live sweep is clean on the first try is weak evidence the repair was needed.
> 3. **Classify hits before acting**, with a mechanical evidence-based discriminator where one exists.
> 4. **Write the live sweep into the next gate-repair item's acceptance criteria**, phrased so fixtures cannot satisfy it: *"after landing, run one unfiltered sweep for this pattern class across the guarded tree and paste the classified result."*
> 5. **When the live sweep finds a defect class the item did not name, file it rather than absorbing it.**

#### Reviewer Check 087 — Bug-Fix Criteria With No Fixture and No Unfixed-Artifact Run

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** A plan whose deliverable is a bug fix MUST carry at least one acceptance criterion phrased against a **fixture that reproduces the defect**, AND a requirement to run the same probe against the **unfixed artifact** and show it failing. Criteria phrased against live project data measure the data, not the code — they pass identically against fully-unfixed code whenever the triggering rows were reworded, worked around, or otherwise sanitised before triage. Without the failing run, "my code passes" has never been distinguished from "this gate detects the defect."
- **Detection:**
  1. Identify deliverables whose objective is a fix, repair, or correction of a defect.
  2. Read their acceptance criteria. Classify each as fixture-based (names a constructed input reproducing the defect) or data-based (queries the live project corpus). All data-based → BLOCKER.
  3. Check for a criterion requiring the probe to run against the unfixed artifact — the previous commit, the installed older version, or a reverted copy — with the FAIL result recorded. Absent → BLOCKER.
  4. Check the plan names which criterion is the **discriminating** one. Absent → WARNING (downgrade from BLOCKER when 2 and 3 both pass).
  5. Where a criterion is already satisfied at triage time, check the plan records that as a finding with its reason rather than as a satisfied box. Recorded as satisfied → BLOCKER.

#### Reviewer Check 088 — Gate Asserts Format Where the Property Is Resolution, or Is Fixture-Satisfiable

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** Two instrument defects that ship together often enough to share a check. **(a)** A verification gate asserts a format or spelling pattern where the property at stake is **resolution or existence** — a citation gate matching punctuation rather than confirming the target file and section exist. Such a gate scores 0 on a correctly pinned citation written in the house style and scores 1 on a citation whose file does not exist, and it exerts pressure on the runner to reformat correct content. **(b)** A gate-repair deliverable whose acceptance criteria are satisfiable **entirely by fixtures**, with no live sweep of the guarded subject. A fixture dry-run proves the gate is not vacuous; only a live sweep proves the subject is clean, and the live sweep is the one that finds work no criterion could have named.
- **Detection:**
  1. For every verification gate whose subject is a citation, path, identifier, or section reference: read its pattern. Does it assert punctuation, spacing, or delimiter placement rather than confirming the target resolves? → WARNING.
  2. Apply the authoring test to each such gate — *what would a correct-but-differently-formatted artifact score?* FAIL → WARNING.
  3. Check whether the plan requires a dry-run against a known-GOOD file in the house style, not only against known-bad. Absent on a format-shaped gate → WARNING.
  4. For deliverables whose objective is repairing or authoring a gate: check the criteria for a live sweep of the guarded tree, phrased so fixtures cannot satisfy it. All-fixture criteria → WARNING.
  5. Check the plan states that findings outside the item's file list are expected from the live sweep and get filed rather than absorbed. Absent → WARNING.

---

*Cross-references: [gate-positive-and-mutation-controls.md](gate-positive-and-mutation-controls.md) (§1-§4 and §14, the controls that discharge obligations A and B in practice) · [gate-fixture-provenance.md](gate-fixture-provenance.md) (§5-§9, an input set that could have contained the defect: obligation D) · [gate-change-vs-state-detecting.md](gate-change-vs-state-detecting.md) (§11, what shape of question a sound battery can answer at all) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) (pair every anchor against its known-bad state) · [verification-gates.md](verification-gates.md) (the family index).*
