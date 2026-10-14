# Handler: /planwise list

**Purpose:** Display all plans from the plans index. Optionally filter to active plans only. This handler is the contract of the path the skill takes. The skill's own `## List` section carries the runtime instructions, so a normal `list` call never reads this file.

**Invocation examples:**
```
/planwise list
/planwise list --active
/planwise list --no-check
```

---

## Config Gate

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue. `plugin_root` names the plugin directory in reference commands. The list script reads `project.planwise_root`, `project.plans_dir` and `project.index_files.plans` (as `{plans_index}`) itself. The drift-detect pass (Step 2) reuses the same values, so no additional config extraction is needed.
3. If NOT found: report the cause, and tell the user to run `/planwise init`. Never initialise from `list`. It is a read-only status view, and creating a project structure is a write the user did not ask for.

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed, DO NOT initialise. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise list." STOP.

> [!constraint] Resolution is exactly a) and b) from the invocation directory — never inferred from a path string
> WRONG — neither a) nor b) finds a `config.yaml`, so the handler decodes another project's location out of a directory *name* (a temp directory that embeds the project path, an ancestor, a sibling checkout), reads that project's `config.yaml`, and lists its plans as if they were this one's. The output is a plausible table for the wrong project, with no warning.
> CORRECT — a) and b) both miss → step 3 exactly: report the cause and point to `/planwise init`. A `config.yaml` that lives anywhere other than a) or b) belongs to a different project and is never read. (`config_loader.py`'s script-side resolver applies the same rule: it accepts only a file carrying a top-level `project:` block and otherwise fails loud.)

All directory paths resolve as `{planwise_root}/{dir_name}`.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`, `native-tool-use.md`, `feedback-drafting.md`) are pre-injected by SKILL.md.

**Conditional references:**
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`

---

## Workflow

### Step 1: Render the List in One Call

The skill normally renders the list before the model runs. Its shell line calls `skill_preflight.py` with the subcommand, and the script prints the whole answer between `<!-- planwise:list:begin -->` and `<!-- planwise:list:end -->`. The model displays that block verbatim and runs nothing.

Otherwise, run the command in rule 3 of the skill's `## List` section once with Bash, adding only the flags the user typed, and display what lies between the markers. The harness has already expanded the plugin path in that command, so copy it from the skill byte for byte. The path expands with the platform's separators, and a hand-typed path may not match the skill's `allowed-tools` grant. Its reference form, with `{plugin_root}` resolved from `config.yaml`, is:

```
python -B "{plugin_root}/scripts/skill_preflight.py" list
```

Take this route when no block appears, when the line reads `[shell command execution disabled by policy]`, or when the user typed `--active` or `--no-check`. The shell line passes only the subcommand, so its block is never filtered. Do not Read any file on this path. A Read of a plugin file can be denied when the working directory lies outside the plugin tree.

### Step 2: Read the Banner

The plans index is **generated from the Master Plans** by `generate_plans_index.py`. The list script runs the drift-detect pass of [`references/index-drift-audit.md`](../references/index-drift-audit.md) against the **plans** index in-process, the same pass `/planwise doctor` runs. `list` stays **non-mutating by default**: nothing is written without explicit consent. `--no-check` skips the pass and prints no banner.

The banner opens with one of three headers:

| Header | Meaning |
|---|---|
| `planwise list — plans index drift audit` | A real verdict. The drift and anomaly lines follow, or `No drift detected`. Only this header may print `No drift detected`. |
| `planwise list — plans index drift audit could not run` | The audit compared no rows (`could-not-run`) or only some (`incomplete`). The script's own lines follow. Under `could-not-run`, a last line `{n} Master Plan(s) on disk have no row in the index (missing-row).` prints when at least one drift record is a `missing-row`. Never read this header as clean. |
| `planwise list — legacy-shaped plans index — run /planwise upgrade` | The index predates the generated shape. Offer no write. |

What to offer after the banner:

- **Drift under a real verdict:** offer `reconcile_plans.py --write`, and wait for consent.
- **The `(missing-row).` line is present:** offer `reconcile_plans.py --write`. Say that it regenerates the whole file and drops every line the render does not produce. Without that line, `could-not-run` offers no write.
- **`incomplete`:** offer no write. Regenerating would drop the unparsed lines the script listed.
- **Legacy shape:** offer no write. Point to `/planwise upgrade`.

The consent path is interactive, so a permission prompt for the writer is acceptable. After a consented `reconcile_plans.py --write`, exit 1 has a different meaning: the index was written and the tree has an anomaly. Report `Reconciled {N} row(s).` and the anomaly, not a failed write. Then re-run Step 1 so the regenerated rows show in this same invocation. A legacy-shaped index makes the writer exit 2 and write nothing. Report that exit code and stop.

### Step 3: Filters

**`--active`:** keep rows whose Status is one of `PLANNING`, `READY_TO_EXECUTE`, `REVIEWED`, `APPROVED`, `NEEDS_FIXES`, or `IN_PROGRESS`. Omit rows with status `NOT_STARTED`, `BLOCKED`, `COMPLETE`, or `CLOSED`. Omit a project-added `plan_statuses:` value too, since it is not in the active set. `/planwise list` without `--active` shows it.

If no plans match the filter, the script prints:

```
No active plans found (status PLANNING, READY_TO_EXECUTE, REVIEWED, APPROVED, NEEDS_FIXES or IN_PROGRESS).
Use `/planwise list` to see all plans.
```

**`--no-check`:** skip the drift-detect pass for a fast glance. The pass reads every Master Plan the disk walk finds.

The table closes with one summary line:

```
{N} plan(s) shown. Run `/planwise plan` to create a new plan.
{N} active plan(s) shown (filtered to PLANNING, READY_TO_EXECUTE, REVIEWED, APPROVED, NEEDS_FIXES and IN_PROGRESS). Run `/planwise list` to see all.
```

The second line replaces the first when `--active` was used.

### Step 4: Fallback Lines

On failure the script prints exactly one `PLANWISE_LIST_FALLBACK: <cause>` line instead of the table. Respond by the cause:

| Cause begins with | Response |
|---|---|
| `config.yaml not found` | Say no planwise `config.yaml` was found in that directory, and tell the user to run `/planwise init`. Never initialise from `list`. |
| `config.yaml parse error` | Fail loud: `config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise list.` Stop. |
| `Plans index not found` | Print the line. Suggest `generate_plans_index.py --write` to generate it from the Master Plans, or a check of `config.yaml`. |
| Any other cause | Print the line. |
