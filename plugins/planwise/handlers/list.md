# Handler: /planwise list

**Purpose:** Display all plans from the plans index. Optionally filter to active plans only.

**Invocation examples:**
```
/planwise list
/planwise list --active
```

---

## Config Gate

Locate `config.yaml` by checking:
1. `planwise/config.yaml` (default planwise root)
2. If not found, search one level down from the project root for `*/config.yaml`
3. If not found: "Project not initialized. Run `/planwise init` first."

Extract from `config.yaml`:
- `plugin_root` — the plugin installation path
- `project.planwise_root` — the planwise root folder (default: `planwise`)
- `project.plans_dir` — the Plans directory name (relative to planwise_root, default: `Plans`)
- `project.index_files.plans` — the plans index filename (default: `00-Index-Plans.md`)

All directory paths resolve as `{planwise_root}/{dir_name}` (e.g., `planwise/Plans`).

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`) are pre-injected by SKILL.md.

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
