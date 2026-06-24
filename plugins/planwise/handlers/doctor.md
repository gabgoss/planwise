# Handler: /planwise doctor

**Purpose:** Report `.claude/rules/**` that are over-scoped to plan/backlog/lessons paths (an injection-budget risk for DELEGATED task-runners), and — when Token Saver is on — audit the measured overheads for staleness, scan the active plan's files against the Read-tool gates, and flag the fixed read-limit constants for harness drift. Read-only — mutates nothing.

**Invocation examples:**
```
/planwise doctor
```

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue. Extract `plugin_root`, `project.planwise_root`, `project.plans_dir`, and the `context:` Token Saver keys (`token_saver`, `token_saver_runner_overhead`, `token_saver_orchestrator_overhead`, `token_saver_session_target`, `token_saver_overhead_measured_on`, `token_saver_context_breakdown`) plus the pinned `plugin_version`.
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

## Token Saver Audit

> [!gate] Run only when `context.token_saver` is `true`
> If `token_saver` is `false` or absent in `config.yaml`, skip this entire section — the project does not run the Token Saver budget engine, so there are no measured overheads to audit and no plan-file read-gate scan to perform. Report "Token Saver: OFF — audit skipped" and stop after the over-scope report above.

When Token Saver is on, append the three audits below to the doctor report. All three are **read-only** — `doctor` reports and recommends a one-command re-capture; it NEVER mutates `config.yaml` itself.

> The `token_saver` value reported here is the **project default** (`config.yaml context.token_saver`). Individual plans MAY override it on/off via their Master-Plan `Token Saver:` field (resolved by `get_effective_token_saver_config` at plan/run/review time); the measured overheads remain project-level and are never overridden per-plan. `doctor` itself stays project-scoped — it audits the project default, not any single plan's effective value.

### Step 4: Overhead audit + staleness check

1. Report the stored measured overheads and the date they were captured:

   ```
   Token Saver overheads (config.yaml):
     Runner overhead:       {token_saver_runner_overhead}  tokens
     Orchestrator overhead: {token_saver_orchestrator_overhead}  tokens
     Session target:        {token_saver_session_target}  tokens
     Measured on:           {token_saver_overhead_measured_on}
     Derived per-task ceiling (critical): ~{available_per_task − 10000} tokens
   ```

   Derive `available_per_task = token_saver_session_target − token_saver_runner_overhead − 6000` (the engine's `derive_thresholds`); never hardcode the ceiling.

2. **Flag staleness** when EITHER signal fires (the measured overheads no longer reflect this install's real `/context` footprint):

   | Staleness signal | How to detect |
   |------------------|---------------|
   | Plugin upgraded since calibration | The pinned `plugin_version` in `config.yaml` differs from the plugin's current shipped version (the overheads were measured against the old rule/agent surface) |
   | Agent/Skill count changed | The Custom Agents / Skills count in a fresh `/context` differs from the captured `token_saver_context_breakdown` (added/removed agents or skills shift the always-on surface) |
   | Overheads uncalibrated | `token_saver_runner_overhead` is `0`/empty, or equals the conservative fallback (`~54000` runner / `~60000` orchestrator) with no live capture recorded. **Note:** on some platforms (notably Windows and any headless invocation), the calibration capture always degrades to the conservative fallback because the CLI returns conversational text instead of the structured `/context` report when called non-interactively. This is a platform/capture limitation, not a configuration error — the conservative fallback is safe (over-estimated). To capture real measured numbers, run `/planwise token-saver on` from an **interactive** Claude Code session. |

3. When stale, offer the one-command re-capture (never auto-mutate config without surfacing it):

   ```
   ! Token Saver overheads may be STALE ({reason}).
     Re-capture with: /planwise token-saver on
     (runs token_saver.calibrate(...) → claude -p "/context" → writes measured overheads back into config.yaml)
     Note: re-capture requires an interactive session; headless invocations may degrade to the conservative fallback.
   ```

4. List the plan's largest Required-Context files and any tasks over the derived ceiling or flagged `1M-exception`:
   - Scan the active plan's task files under `{plans_dir}`; for each, sum its Required Context `Est. Tokens` and compare against `critical`.
   - Report any task at or above `critical` (cost overflow → split / trim) and any task already carrying a `Token Budget:` exception marker of `1M (cost)`.

### Step 5: Read-gate scan

Run `token_saver.classify_file(path, model, projected_added_lines, thresholds)` (from `scripts/token_saver.py`) across BOTH (a) the active plan's Required-Context files AND (b) the plan's own generated artifacts (task files, Orchestration, Recovery, Consolidated Context parts, Execution Inputs, task Output files). Use each file's **assigned-model** rate for the token estimate (`TOKENS_PER_LINE`: Sonnet/Haiku `13`, Opus `19` tok/line). Report:

| Finding | Gate | Recommendation |
|---------|------|----------------|
| File ≥ 256 KiB (`READ_FILE_BYTE_CAP`) | byte gate (model-independent) | **read-Critical** → paged read (`offset`/`limit`/Grep); refactor + backlog if it is a core/edited dependency |
| File above the per-assigned-model 25K-token page cap (`READ_PAGE_CAP_TOKENS`) | token gate (model-dependent) | **read-Critical** → paged read; refactor if core/edited |
| File that WILL cross a gate once its task's edits land | byte/token gate (projected) | pass `projected_added_lines` so the will-exceed case is flagged pre-emptively; same remedy as above |
| Task estimate ≥ `critical` (cost) | cost gate | **cost-Critical** → `1M-exception` (raise dispatch to Opus/1M) OR split the task |

> [!constraint] read-Critical → paged-read/refactor, NOT `1M-exception`
> The read gates apply on EVERY model — Opus's heavier tokenizer trips the page cap *sooner* (~1,340 lines vs ~1,920). A `read`-reason Critical (`classify_file` → `reason: read`) is NOT resolved by routing to Opus; recommend paged reads / refactor. Reserve the `1M-exception` recommendation for a `cost`-reason Critical only (`reason: cost`), where the larger window genuinely absorbs the carrying cost. See [run.md](run.md) 1M-Exception Dispatch.

### Step 6: Read-constant drift tripwire

Report the FIXED Read-tool constants and flag them stale when the harness CLI has moved past the measured version — the analogue of the overhead-staleness check, but for the hardcoded read limits (the harness may have changed the caps):

1. Report the constants and their provenance from `scripts/token_saver.py`:

   ```
   Fixed Read-tool limits (token_saver.py):
     READ_FILE_BYTE_CAP:   262144 bytes (256 KiB)   [warn 245760]
     READ_PAGE_CAP_TOKENS: 25000 tokens             [warn 22000]
     TOKENS_PER_LINE:      haiku 13, sonnet 13, opus 19
     Measured on:          {READ_LIMITS_MEASURED_ON}
     Measured CLI:         {READ_LIMITS_MEASURED_CLI}
   ```

2. Compare the live CLI version against the measured one:

   ```bash
   claude --version   # → live CLI build
   ```

   When the live `claude --version` differs from `READ_LIMITS_MEASURED_CLI`, flag drift — the constants were validated against a different harness build and the caps may have changed:

   ```
   ! Read-limit constants measured on CLI {READ_LIMITS_MEASURED_CLI}; live CLI is {live-version}.
     The hardcoded Read-tool caps may be stale. Re-probe with the read-limit re-validation
     procedure (headless `claude -p --model X` probes against synthetic files) and update the
     constants + READ_LIMITS_MEASURED_ON / READ_LIMITS_MEASURED_CLI in scripts/token_saver.py.
   ```

   This is the drift tripwire for the hardcoded read constants. It is advisory — `doctor` never edits the constants; it surfaces the mismatch so the one-shot live re-probe can be run.

---

*Cross-reference: [run.md](run.md) (Model-Floor Bridge, 1M-Exception Dispatch), [upgrade.md](upgrade.md) (post-upgrade over-scope advisory, Token Saver recalibration), [lint + token_saver engine in scripts/](../scripts/init_project.py).*
