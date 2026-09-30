# Handler: /planwise list

**Purpose:** Display all plans from the plans index. Optionally filter to active plans only.

**Invocation examples:**
```
/planwise list
/planwise list --active
/planwise list --no-check
```

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue. Extract `plugin_root`, `project.planwise_root`, `project.plans_dir`, and `project.index_files.plans` (as `{plans_index}`). The drift-detect pass (Step 2) reuses these same values — `{plugin_root}` to locate the reconcile script, `{planwise_root}` for its `--config` path — no additional config extraction is needed.
3. If NOT found: announce, resolve `{plugin_root}` from handler location, invoke `init_project.py` with `--auto-from "list"`, RE-RESOLVE, fail loud if still missing.

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed, DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise list." STOP.

> [!constraint] Resolution is exactly a) and b) from the invocation directory — never inferred from a path string
> WRONG — neither a) nor b) finds a `config.yaml`, so the handler decodes another project's location out of a directory *name* (a temp directory that embeds the project path, an ancestor, a sibling checkout), reads that project's `config.yaml`, and lists its plans as if they were this one's. The output is a plausible table for the wrong project, with no warning.
> CORRECT — a) and b) both miss → step 3 exactly: announce, auto-init, re-resolve, fail loud. A `config.yaml` that lives anywhere other than a) or b) belongs to a different project and is never read. (`config_loader.py`'s script-side resolver applies the same rule: it accepts only a file carrying a top-level `project:` block and otherwise fails loud.)

All directory paths resolve as `{planwise_root}/{dir_name}`.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

**Conditional references:**
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`

---

## Workflow

### Step 1: Read Plans Index

Read `{plans_dir}/{plans_index}` (e.g., `Plans/00-Index-Plans.md`).

If the file does not exist:

```
Plans index not found at {plans_dir}/{plans_index}.
Run `/planwise init` to create the index, run `generate_plans_index.py --write` to generate it from the Master Plans, or check your config.yaml.
```

### Step 2: Detect Index Drift (Always-On unless `--no-check`)

The plans index is **generated from the Master Plans** by `generate_plans_index.py`. Each row's cells are copies of that plan's own fields, and the generator is the only writer. This step checks the file on disk against a fresh render of the Master Plans, so a Master Plan edited without a regenerate is found here. `list` stays **non-mutating by default** — nothing is written without explicit consent.

**If `--no-check` is present:** skip this entire step (a fast glance with no deep pass) and go straight to Step 3.

**Detect (always-on otherwise):** Run the index-drift audit procedure in [`references/index-drift-audit.md`](../references/index-drift-audit.md) against the **plans** index (`reconcile_plans.py`, banner `planwise list — plans index drift audit`) — the same detect pass `/planwise doctor` Stage 11 runs; neither handler re-implements the comparison.

Read the exit code and the JSON `status`, then print exactly one of these outcomes. The exit table is in the canonical's Plans binding.

- **Exit 0 (`ran`) — a real verdict.** Print the canonical banner, then either the drift and anomaly lines or `No drift detected`. Only this outcome may print `No drift detected`.
- **Exit 3 — audit could not run.** Print `planwise list — plans index drift audit could not run`, then the script's own lines (`Drift audit could not run: 0 of {total} rows compared` or `Drift audit incomplete: {compared} of {total} rows compared`, and any second line). Never print `No drift detected`. When the JSON `status` is `could-not-run` and `drifts` holds `missing-row` records, offer `reconcile_plans.py --write`, and say that it regenerates the whole file and drops every line the render does not produce. On `incomplete`, offer no write: regenerating would drop the unparsed lines the script listed.
- **Exit 2 — legacy-shaped plans index.** Print `planwise list — legacy-shaped plans index — run /planwise upgrade`, then the script's line. Never print `No drift detected`. Offer no write.
- **Exit 1 — index not found.** In detect mode, print the script's `Error: Plans index not found at {index}` line. Step 1 normally stops on a missing index first.

After a consented `reconcile_plans.py --write`, exit 1 has a different meaning: the index was written and the tree has an anomaly. Report `Reconciled {N} row(s).` and the anomaly, not a failed write. If the index was regenerated, re-read the plans index table before proceeding to Step 3 so the regenerated rows are reflected in this same invocation.

**Cost note:** the detect pass reads every Master Plan the disk walk finds — cheap, but `--no-check` skips it entirely for a fast glance.

### Step 3: Display Plans Table

Extract the plans table from the index and display it to the user.

**If `--active` argument is present:**

Filter the table to rows where the Status column value is one of `PLANNING`, `READY_TO_EXECUTE`, `REVIEWED`, `APPROVED`, `NEEDS_FIXES`, or `IN_PROGRESS`. Omit rows with status `NOT_STARTED`, `BLOCKED`, `COMPLETE`, or `CLOSED`. Omit a project-added `plan_statuses:` value too, since it is not in the active set. `/planwise list` without `--active` shows it.

If no plans match the filter:

```
No active plans found (status PLANNING, READY_TO_EXECUTE, REVIEWED, APPROVED, NEEDS_FIXES or IN_PROGRESS).
Use `/planwise list` to see all plans.
```

**If no arguments:**

Display the full table as-is.

### Step 4: Output

After displaying the table, show a one-line summary:

```
{N} plan(s) shown. Run `/planwise plan` to create a new plan.
```

If `--active` was used:

```
{N} active plan(s) shown (filtered to PLANNING, READY_TO_EXECUTE, REVIEWED, APPROVED, NEEDS_FIXES and IN_PROGRESS). Run `/planwise list` to see all.
```
