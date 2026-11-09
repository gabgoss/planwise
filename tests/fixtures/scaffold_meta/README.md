# scaffold_meta fixture

**Purpose:** a small synthetic Meta-plan that a scaffolding pass can turn into a 2-sprint Execution Plan. A live proof run copies it to a scratch root and drives the fan-out path of `plugins/planwise/handlers/plan-scaffolding.md` over the copy. That path dispatches `planwise:ei-extractor` and `planwise:sprint-scaffolder` once per sprint, and `planwise:scaffold-harmonizer` once per pass.

No test collects this folder. It holds Markdown only, and nothing here is named `test_*.py`. A proof run never writes into this folder. It works on a scratch copy outside both repositories.

The vocabulary (`FXP`, "Fixture Pantry", jars, shelves) is invented. It resolves to nothing outside this fixture.

---

## Contents

| Tier | File | Role |
|------|------|------|
| META | `Meta-FXP/FXP-META-Master-Plan.md` | The Discovery Master Plan |
| 1 | `Meta-FXP/Sprint-01-Discovery/Session-01-Survey/Outputs/FXP-META-S01-01-01-LedgerSurvey.md` | Raw task output: ledger |
| 1 | `Meta-FXP/Sprint-01-Discovery/Session-01-Survey/Outputs/FXP-META-S01-01-02-ExportSurvey.md` | Raw task output: export |
| 2 | `Meta-FXP/Outputs/FXP-Consolidated-Context-Part-1-LedgerCore.md` | `Scope: Ledger Core Sprint` |
| 2 | `Meta-FXP/Outputs/FXP-Consolidated-Context-Part-2-ExportPipeline.md` | `Scope: Export Pipeline Sprint` |
| 2 | `Meta-FXP/Outputs/FXP-Consolidated-Context-Part-3-DesignDecisions.md` | `Scope: Cross-sprint reference` |

No Tier 3 layer exists. The Meta Master Plan says so.

The whole folder stays under 40 KB, so one sprint's sources fit well inside one extractor window.

---

## Expected Scaffold Shape

The parts imply this shape. A scaffold that differs from it is a finding to explain, not an automatic failure.

| Property | Expected |
|----------|----------|
| Sprints | 2: first Ledger Core (Part 1), second Export Pipeline (Part 2) |
| Part 3 | Not a sprint. Its decisions are extracted into both Execution Inputs |
| Sessions | 1 per sprint, 2 in total |
| Tasks | 3 per session, 6 in total. Each part's "Suggested Work Breakdown" lists them |
| Ordering | The first sprint before the second (the export reads the ledger). The write-sets share no path |
| Execution Inputs | 2: `FXP-S01-Execution-Input.md`, `FXP-S02-Execution-Input.md`, each with a Deferred / Out-of-Scope Log |
| Agent dispatches | 2 `ei-extractor`, 2 `sprint-scaffolder`, 1 `scaffold-harmonizer` |

The sources sum to far less than the fan-out threshold. A proof run therefore tells the orchestrator to take the fan-out path anyway, and the `FAN_OUT` line records that the path was forced.

---

## Deviation Gate Target

Run the gate on the scratch `Exec-FXP/` folder the proof run writes, never on this fixture and never on the Meta folder. Every command in this file runs from the plugin repo root:

```
python -B plugins/planwise/scripts/scaffold_deviations.py check <scratch>/Exec-FXP
```

The gate reads the abbreviation from the folder name with `^Exec-(.+)$`. A folder whose name does not start `Exec-` is not an error: the gate exits 0 with `C=0`. Exit 2 means a missing path, a path that is not a folder, an unreadable template or an unreadable plan file. Never read exit 2 as "this folder is not an Exec folder".

---

## Known-Bad Control

The control proves the gate can fail on this scaffold:

1. Copy `<scratch>/Exec-FXP` to `<scratch>/Exec-FXP-control`.
2. In one Orchestration file of the copy, rename the heading `## Session Task List` to `## Task List`.
3. Run the gate on the copy.

Expect exit 1, `A>=1`, and a `CLASS_A` line that names that file and that heading. The clean run and the control run must differ. The copy's folder name makes the gate read the abbreviation `FXP-control`, so a `CLASS_C` line on the control is a naming artifact, not a scaffold defect. Remove the control copy with the rest of the scratch root afterward.
