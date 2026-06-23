# Handler: /planwise doctor

**Purpose:** Report `.claude/rules/**` that are over-scoped to plan/backlog/lessons paths (an injection-budget risk for DELEGATED task-runners). Read-only — mutates nothing.

**Invocation examples:**
```
/planwise doctor
```

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue. Extract `plugin_root` and `project.planwise_root`.
3. If NOT found: announce, resolve `{plugin_root}` from handler location, invoke `init_project.py` with `--auto-from "doctor"`, RE-RESOLVE, fail loud if still missing.

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed, DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise doctor." STOP.

`{project_root}` is the absolute path of the project root (the directory containing `{planwise_root}/`).

---

## Workflow

### Step 1: Run the over-scope linter

```bash
python "{plugin_root}/scripts/init_project.py" --doctor --project-root "{project_root}"
```

If `python` is not found, try `python3`.

> [!constraint] Read-Only — Never Mutates
> `--doctor` runs `lint_rule_overscope()` standalone (no `--upgrade`, no `--migrate`). It only READS `.claude/rules/**` and prints a report; it writes nothing and changes no files. It exits 0 even when rules are flagged.

The linter flags any `.claude/rules/**` file whose `paths:` target plan/backlog/lessons directories (e.g., `planwise/Plans/**`) rather than code paths. For each flagged rule it reports the path, line count, approximate token cost (~13 tokens/line), and the matched glob.

### Step 2: Present the report verbatim

Pass the script's stdout through to the user unchanged. It follows this shape:

```
Rule over-scope report ({project_root})

Over-scoped rules (injection-budget risk):
  ! .claude/rules/{...}.md
      paths:         {matched plan/backlog/lessons glob}
      size:          {N} lines (~{X}K tokens)
      re-scope hint: narrow paths: to the code dirs this rule actually governs,
                     or load it on demand (handler / references) instead of installing it path-scoped

Total flagged injection budget: ~{X}K tokens across {N} rule(s)
```

If no rules are flagged, the script prints `No overscoped rules found.` — report that the project's rule surface is healthy.

### Step 3: Explain the why (only when rules were flagged)

Briefly note: a rule scoped to `planwise/Plans/**` is injected into EVERY context that reads a plan brief — including a DELEGATED `task-runner` subagent, whose 200K window can overflow ("Prompt is too long") when the flagged surface is large. The fix is to re-scope the rule's `paths:` to the code directories it actually governs, or to load it on demand (handler / `references/`) rather than installing it path-scoped. The `run.md` Model-Floor Bridge is the temporary dispatch safety-net that keeps declared-Sonnet runners alive until the flagged surface is brought down.

---

*Cross-reference: [run.md](run.md) (Model-Floor Bridge), [upgrade.md](upgrade.md) (post-upgrade over-scope advisory), [lint logic in scripts/init_project.py](../scripts/init_project.py).*
