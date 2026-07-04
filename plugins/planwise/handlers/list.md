# Handler: /planwise list

**Purpose:** Display all plans from the plans index. Optionally filter to active plans only.

**Invocation examples:**
```
/planwise list
/planwise list --active
```

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue. Extract `plugin_root`, `project.planwise_root`, `project.plans_dir`, and `project.index_files.plans` (as `{plans_index}`).
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

### Step 2: Display Plans Table

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

### Step 3: Output

After displaying the table, show a one-line summary:

```
{N} plan(s) shown. Run `/planwise plan` to create a new plan.
```

If `--active` was used:

```
{N} active plan(s) shown (filtered to IN_PROGRESS and PLANNING). Run `/planwise list` to see all.
```
