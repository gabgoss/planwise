---
description: A gate's output is evidence only after four independent obligations are discharged — it can fail, shown by a fixture that reproduces the defect and a run of the same probe on the unfixed artifact (A); it does not fail correct work (B); it can see the shape it counts (C); and it is pointed at the live subject as well as at fixtures (D); Reviewer Checks 087 and 088.
paths: {planwise_root}/{plans_dir}/**
---

# Gate Instrument Proof Obligations (Four Things a Gate Proves Before Its Output Is Evidence)

**Purpose:** The sibling rules ask whether the right thing was measured. This file asks a prior question: is the instrument itself sound? A gate can discriminate perfectly and still be pointed at a sanitised subject, and it can be pointed at the real subject and be structurally incapable of failing. Split from `verification-gates.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gates.md §N` citation translates by filename alone. The family index is `verification-gates.md`.

**Read this when** a task's deliverable is a gate, a guard, a hook, a linter or a validation pass, an acceptance criterion cites a gate run as proof, or a bug-fix deliverable's criteria name no fixture that reproduces the defect.

## Table of Contents

- [10. The Instrument's Four Proof Obligations](#10-the-instruments-four-proof-obligations)

---

## 10. The Instrument's Four Proof Obligations

The runtime, verdict and baseline rules in `gate-runtime-boundary-evidence.md`, `gate-exit-verdict-and-smoke-reports.md` and `gate-diff-baseline-pinning.md` (§1–§8 of the former `verification-gates.md`) ask whether the right thing was measured. This section asks a prior question: **is the instrument itself sound?** A gate's output is evidence only after the gate has discharged four obligations, and they are **independent** — passing any one says nothing about the other three. A gate can discriminate perfectly and still be pointed at a sanitised subject. A gate can be pointed at the real subject and be structurally incapable of failing.

| Obligation | The question | Failure it admits |
|---|---|---|
| A | Can it fail at all? | A criterion already satisfied before the work starts |
| B | Does it fail *correct* work? | A gate measuring form, exerting pressure to reformat correct content |
| C | Can it see the shape it counts? | A single-line matcher against a multi-line idiom |
| D | Does a proven instrument mean a clean subject? | A fixture dry-run reported as if it were a live sweep |

> [!constraint] Obligation A — the gate must be able to fail
> ```
> WRONG  AC: "re-run the tool and confirm the open-item count equals the
>             number of non-closed rows"
>          -> 17 open, 17 reported. PASS.
>          # Passes identically against fully-unfixed code, because the two rows
>          # that triggered the bug were reworded yesterday as a workaround. The
>          # criterion measured the data, and the data had been sanitised.
> CORRECT AC: "run every parser on a clean row AND on a row containing a \| b;
>              require identical, correct column assignment"
>          -> fixed tree:   12/12 identical and correct                     PASS
>          -> unfixed tree: field clobbered, priority destroyed, links empty FAIL
>          # The FAIL is the load-bearing half: it proves the gate discriminates.
> ```
>
> Three rules, stated separately because they fail separately:
>
> 1. **A criterion evaluated against live project data measures the data, not the code.** It is a regression guard for after the fix lands — never evidence the fix works. Phrase at least one criterion against a **fixture that reproduces the defect**, and say in the item which criterion is the discriminating one.
> 2. **Run the same probe against the unfixed artifact** — the previous commit, the installed older version, a copy with the fix reverted — **and show it failing.** That second run is what converts "my code passes" into "this gate detects the defect."
> 3. **Run a reproduction recipe on the known-bad state before pinning it, and read the flag's implementation, not its name.** A repro that prints nothing on the broken build is not a repro. `--show-<x>` can mean "print x" or "stop hiding x", and one `Grep` for the flag in the parser and its consumer settles which.
>    - WRONG: `<tool> --config <fixture> --show-blocked` — the flag routes blocked items into the selectable list, so the "blocked by:" summary never prints.
>    - CORRECT: `<tool> --config <fixture>` — run once on the broken state, it prints the summary with the id missing.
>
> Two corollaries:
>
> - **A criterion already satisfied at triage time is a finding, not a tick.** Record it with its reason. A criterion structurally incapable of failing again — because the reflex that sanitised the data will sanitise the next case too — is a defect in the criterion.
> - **Prefer "demonstrably correct" to "demonstrably different."** Two outputs that merely differ can both be wrong.

> [!constraint] Obligation B — the gate must not fail correct work
> A gate must assert **the property you care about**, not a spelling of it. For a citation the property is **resolution**: the file exists at the path given, the section exists in it, no placeholder token remains. Never typography.
>
> ```
> WRONG   — asserts typography. Rejects the house style, accepts a broken link.
>   pattern: '{file}\.md §[0-9]+\.[0-9]+'
>   -> `{file}.md` §1.4      scores 0   # a backtick sits where the pattern wants a space
>   -> nonexistent.md §9.9   scores 1   # the file does not exist; only the shape does
>
> BETTER  — spelling-tolerant. Still only checks the shape.
>   pattern: '{file}\.md`?\s*§[0-9]+(\.[0-9]+)?'
>   -> catches an unpinned citation and a leftover {placeholder}
>   -> still scores 1 for a section number that is not in the file
>
> BEST    — resolves. Asserts the property the gate exists to protect.
>   for each citation:  Read the named file
>                       -> confirm a heading carries that §-number
>                       -> confirm no placeholder token remains
>   -> the only tier that fails a citation whose target moved
> ```
>
> The BETTER tier is shown because it is the tempting stopping point, and it is still not the correct one.
>
> **The authoring test:** *what would a correct-but-differently-formatted artifact score?* If the answer is FAIL, the gate is measuring form. **Dry-run against a known-GOOD file in the house style, not only against known-bad** — the standing dry-run rule proves a gate can *fire*; it does not prove the gate stays silent on correct work.
>
> A gate that fails correct work leaves a runner three options: fail the work, edit its own exit criteria, or reformat correct content. It will reformat, and it may land on a valid form by luck. **When a runner reports that it reformatted content to satisfy a gate, that is a gate-defect report, not a completion detail** — read it as one.

> [!constraint] Obligation C — the gate must be able to see the shape it counts
> A sweep for invalidated patch targets reported **14 sites**. The real count was **64+2**. Every clause of the pattern was single-line; the file's dominant idiom is not.
>
> Two cheap checks, before the pattern is trusted:
>
> ```
> # 1. Count the idiom's ANCHOR and its CONTINUATION separately.
> #    A large gap means the pattern is single-line and the idiom is not.
> Grep  pattern='patch\.object'  path='{target}'  output_mode='count'   #  9  <- what the sweep saw
> Grep  pattern='^\s*ip,'        path='{target}'  output_mode='count'   # 47  <- what it missed
>
> # 2. Read one real instance before writing the pattern.
> Read  file_path='{target}'  offset={first hit}  limit=12
> ```
>
> Prefer structure-independent matchers, in this order:
>
> 1. A **multiline matcher** when the idiom genuinely spans lines.
> 2. Better — a **structural check**: parse the file and walk its call nodes. Immune to formatting entirely.
> 3. For verifying a mechanical rename, a **normalization diff**: undo the rename in the new file and expect an additions-only diff. A line-classifying filter cannot tell a target line from an assertion line when the target sits on a continuation line — the same blindness, one layer up.
>
> **Finding a defect class does not immunize you against it.** The moment of discovery is when the blind spot is most active, because attention is on the target rather than on the instrument. In the originating session, two of the five instances were committed inside the sweeps written to catch the other three — including a verification gate carrying the identical flaw, which would have false-FAILed ~55 legitimate repoints.
>
> **Delegation corollary:** an orchestrator-supplied count is handed down as a **cross-check with halt-on-disagreement**, never as the answer. A runner told "there are 14" will find 14.

> [!practice] Obligation D — discrimination is not cleanliness
> | Run | Question answered | What a pass proves |
> |-----|-------------------|--------------------|
> | Fixture dry-run | *Can this gate tell bad from good?* | The gate is not vacuous |
> | Live sweep | *Is the thing it guards actually clean?* | The subject has no current defects |
>
> A fixture dry-run is bounded by the author's model of the defect — a self-portrait of what was already believed. A live sweep alone, with no dry-run behind it, is worthless: an empty result from an instrument nobody proved discriminating says nothing. Neither substitutes for the other.
>
> The asymmetry that makes this worth a rule: **the dry-run is what acceptance criteria naturally capture**, because it is scoped and predictable. **The live sweep is what gets skipped**, because it is unbounded and its result is not knowable at authoring time — which is exactly why it is where new work comes from. One gate repair met a well-designed dry-run criterion exactly (7/7 on known-bad, 0/6 on clean, every carve-out silent) and passed every acceptance criterion it had. Pointing the repaired gate at the tree it guards — which no criterion asked for — immediately returned eight leaking lines in two shipped files no deliverable had scoped, plus a fourth defect class the item never identified.
>
> 1. **Run both, in order, and report the two outputs separately.** A single merged "verification passed" hides which question was answered.
> 2. **Expect the live sweep to produce findings outside the item's file list, and treat that as the deliverable working.** A repair whose live sweep is clean on the first try is weak evidence the repair was needed.
> 3. **Classify hits before acting**, and prefer a mechanical evidence-based discriminator to judgement.
> 4. **Write the live sweep into the next gate-repair item's acceptance criteria**, phrased so fixtures cannot satisfy it. The criterion form: *"after landing, run one unfiltered sweep for this pattern class across the guarded tree and paste the classified result."*
> 5. **When the live sweep finds a defect class the item did not name, file it rather than absorbing it.** Absorbing it hides the discovery inside a closed item.
>
> This generalises past pattern sweeps: unit tests versus production data, a linter's own suite versus running it over the repo, a migration's fixture round-trip versus a dry-run against the real database. Same two runs, same asymmetry.

#### Reviewer Check 087 — Bug-Fix Criteria With No Fixture and No Unfixed-Artifact Run

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** A plan whose deliverable is a bug fix MUST carry at least one acceptance criterion phrased against a **fixture that reproduces the defect**, AND a requirement to run the same probe against the **unfixed artifact** and show it failing. Criteria phrased against live project data measure the data, not the code — they pass identically against fully-unfixed code whenever the triggering rows were reworded, worked around, or otherwise sanitised before triage. Without the failing run, "my code passes" has never been distinguished from "this gate detects the defect."
- **Detection:**
  1. Identify deliverables whose objective is a fix, repair, or correction of a defect.
  2. Read their acceptance criteria. Classify each as fixture-based (names a constructed input reproducing the defect) or data-based (queries the live project corpus). All data-based → BLOCKER.
  3. Check for a criterion requiring the probe to run against the unfixed artifact — the previous commit, the installed older version, or a reverted copy — with the FAIL result recorded. Absent → BLOCKER.
  4. Check the plan names which criterion is the **discriminating** one. Absent → WARNING (downgrade from BLOCKER when 2 and 3 both pass).
  5. Where a criterion is already satisfied at triage time, check the plan records that as a finding with its reason rather than as a satisfied box. Recorded as satisfied → BLOCKER.
- **Finding template:**
```
[BLOCKER] Bug-fix criteria cannot fail — no fixture, no unfixed-artifact run
File: {plan or task file path} | Location: Acceptance Criteria / Success Criteria
Issue: {N} of {M} criteria query live project data; none is phrased against a fixture reproducing the defect{, and no criterion requires the probe to fail on the unfixed artifact}
Fix: Add one criterion over a constructed input that reproduces the defect, add a criterion requiring the same probe to run on the unfixed artifact with its FAIL output pasted, and name the discriminating criterion, per references/gate-instrument-proof-obligations.md §10 obligation A | Confidence: HIGH
```

#### Reviewer Check 088 — Gate Asserts Format Where the Property Is Resolution, or Is Fixture-Satisfiable

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** Two instrument defects that ship together often enough to share a check. **(a)** A verification gate asserts a format or spelling pattern where the property at stake is **resolution or existence** — a citation gate matching punctuation rather than confirming the target file and section exist. Such a gate scores 0 on a correctly pinned citation written in the house style and scores 1 on a citation whose file does not exist, and it exerts pressure on the runner to reformat correct content. **(b)** A gate-repair deliverable whose acceptance criteria are satisfiable **entirely by fixtures**, with no live sweep of the guarded subject. A fixture dry-run proves the gate is not vacuous; only a live sweep proves the subject is clean, and the live sweep is the one that finds work no criterion could have named.
- **Detection:**
  1. For every verification gate whose subject is a citation, path, identifier, or section reference: read its pattern. Does it assert punctuation, spacing, or delimiter placement rather than confirming the target resolves? → WARNING.
  2. Apply the authoring test to each such gate — *what would a correct-but-differently-formatted artifact score?* FAIL → WARNING.
  3. Check whether the plan requires a dry-run against a known-GOOD file in the house style, not only against known-bad. Absent on a format-shaped gate → WARNING.
  4. For deliverables whose objective is repairing or authoring a gate: check the criteria for a live sweep of the guarded tree, phrased so fixtures cannot satisfy it. All-fixture criteria → WARNING.
  5. Check the plan states that findings outside the item's file list are expected from the live sweep and get filed rather than absorbed. Absent → WARNING.
- **Finding template:**
```
[WARNING] Gate measures form, or is satisfiable without a live sweep
File: {plan or task file path} | Location: {Verification Commands | Success Criteria} step {n}
Issue: {gate asserts {pattern} where the property is resolution — a house-style citation scores 0 and a citation to a nonexistent file scores 1 | gate-repair criteria are satisfied entirely by fixtures; the guarded tree is never swept}
Fix: {Rewrite the gate to resolve the reference — confirm the named file exists, the section number is present as a heading, and no placeholder token remains — and dry-run it against a known-GOOD house-style file as well as known-bad | Add a live-sweep criterion over the guarded tree phrased so fixtures cannot satisfy it, and state that findings outside this item's file list are filed, not absorbed}, per references/gate-instrument-proof-obligations.md §10 obligations B and D | Confidence: MEDIUM
```

---

*Cross-references: [gate-positive-and-mutation-controls.md](gate-positive-and-mutation-controls.md) (§1-§4 and §14, the controls that discharge obligations A and B in practice) · [gate-fixture-provenance.md](gate-fixture-provenance.md) (§5-§9, an input set that could have contained the defect: obligation D) · [gate-change-vs-state-detecting.md](gate-change-vs-state-detecting.md) (§11, what shape of question a sound battery can answer at all) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) (pair every anchor against its known-bad state) · [verification-gates.md](verification-gates.md) (the family index).*
