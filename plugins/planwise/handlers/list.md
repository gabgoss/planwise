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
Run `/planwise init` to create the index, or check your config.yaml.
```

### Step 2: Detect Index Drift (Always-On unless `--no-check`)

The plans index is a **denormalized cache**: each row's Status column is a copy of its Master Plan's own `Status:` field, written at closeout by run.md's Step 4.3 "Update Plan Status" (sub-step 5). Nothing else re-checks the cache against that source of truth between closeouts, so a plan completed outside that step — or before it existed — can carry a stale row indefinitely. This step is the read-side counterpart: run.md's closeout write is write-at-closeout, this detect pass is heal-on-read. `list` stays **non-mutating by default** — nothing is written without explicit consent.

**If `--no-check` is present:** skip this entire step (a fast glance with no deep pass) and go straight to Step 3.

**Detect (always-on otherwise):**

1. Run:
   ```bash
   python {plugin_root}/scripts/reconcile_plans.py --config {planwise_root}/config.yaml --json
   ```
2. Read the JSON file at the path the script prints (`JSON: {path}`), shaped `{"drifts": [...], "anomalies": [...]}` — `drifts` are rows whose index Status diverges from their Master Plan's Status; `anomalies` are rows whose Master Plan could not be resolved or read (reported, never written).

**Warn (only when non-empty):**

If `drifts` or `anomalies` is non-empty, print a banner **before** the plans table:

```
⚠ Index drift detected ({K} row(s) out of sync with Master Plan status):
  • {ABBR}: index={X}  →  Master Plan={Y}
Anomalies:
  • {ABBR}: Master Plan not found at {path}
```

If both `drifts` and `anomalies` are empty, print nothing — the output stays silent and unchanged.

**Write on consent (READ-CONFIRM-ACT):**

After the banner, use `AskUserQuestion` to offer reconciliation: "Reconcile {K} drifted row(s) in the plans index to match their Master Plan status?" On agreement:

```bash
python {plugin_root}/scripts/reconcile_plans.py --config {planwise_root}/config.yaml --write
```

The script re-reads the index immediately before writing, so it is race-safe against a concurrent closeout that may have already healed a row — only rows still drifted at write time are touched. Report `Reconciled {N} row(s).` Anomaly rows are never written (there is no Master Plan to reconcile against). If the user declines, leave the index untouched — the banner already recorded what was found.

If a write ran, re-read the plans index table before proceeding to Step 3 so the reconciled Status/Last Updated values are reflected in this same invocation.

**Cost note:** the detect pass reads one Master Plan per index row — cheap, but `--no-check` skips it entirely for a fast glance.

### Step 3: Display Plans Table

Extract the plans table from the index and display it to the user.

**If `--active` argument is present:**

Filter the table to rows where the Status column value is `IN_PROGRESS` or `PLANNING`. Omit rows with status `COMPLETE`, `CLOSED`, `NOT_STARTED`, or `BLOCKED`.

If no plans match the filter:

```
No active plans found (status IN_PROGRESS or PLANNING).
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
{N} active plan(s) shown (filtered to IN_PROGRESS and PLANNING). Run `/planwise list` to see all.
```
