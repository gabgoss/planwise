# Handler: /planwise init

**Purpose:** Initialize the Agentic Project Management structure for the current project.

This handler does NOT require `config.yaml` to exist — it creates it.

`/planwise init` also exposes a `--migrate` mode (Step 11 below) that idempotently
adds missing top-level keys from `config.yaml.template` to an existing project
config without overwriting user customisations. Use it when the plugin ships a
new config block and your project's config predates it.

---

## Artifact Manifest

Every on-disk artifact the init script produces is registered in
[../manifests/artifacts.yaml](../manifests/artifacts.yaml) along with:

- the config key (or block) it depends on,
- the producer (script function or handler step),
- the downstream consumer skill(s), and
- the missing-key behaviour (`render_from_template_default`, `warn_loud`,
  `fail_loud`, or `migrate_only`).

The manifest is the source of truth for the gap-detection logic implemented by
`init_project.py` and surfaced in the Step 10 banner. When a new handler or skill
introduces a config-driven artifact, add a row to the manifest so the
silent-skip class of failure stays mechanical to prevent.

---

## Tool Usage Rules

This handler MUST use Claude Code's dedicated tools for all file operations:

- **Read** to read plugin source files (references, seeds, templates)
- **Write** to create files in the project
- **Glob** to check if files already exist (skip if they do)
- **Bash** ONLY for `mkdir -p` (directory creation)

Do NOT use `cat`, `cp`, `sed`, `awk`, or other bash commands for file operations.

---

## Workflow

### Step 1 — Gather project information

<!-- AUTO-MODE: convenience -->
<!-- All 8 sub-questions are convenience. Defaults: project_name = cwd basename (strip suffix);
     install_scope = project; planwise_root = planwise; plans_dir = Plans;
     backlog_dir = Backlog; lessons_dir = LessonsLearned; plan_tier = pro;
     token_saver = yes (recommended). -->
Use `AskUserQuestion` to collect:

1. **Project name** — The name of this project (e.g., "MyApp", "DataPipeline")
2. **Install scope** — Where to apply planwise settings: `project` (.claude/settings.json, shared with team), `user` (~/.claude/settings.json, personal across all projects), or `local` (.claude/settings.local.json, personal to this project). Default: `project`
3. **Planwise root folder** — Where all planwise files will live (default: `planwise`)
4. **Plans directory** — Subdirectory name for plans within the root (default: `Plans`)
5. **Backlog directory** — Subdirectory name for backlog items within the root (default: `Backlog`)
6. **Lessons directory** — Subdirectory name for lessons learned within the root (default: `LessonsLearned`)
7. **Claude plan tier** — Which Claude plan you're on: `pro` (200K context window) or `max` (1M context window). This scales all token budgets, Meta-Plan thresholds, and DELEGATED checks. Default: `pro`. See `references/session-context-budget.md` §4 for tier-specific budget tables.
8. **Enable Token Saver mode?** — Keeps task sessions under ~150K (avoids the linear carrying-cost of big sessions) and warns when a file is too large to fit a lean task. Recommended: `yes`. See `references/token-saver-profile.md` for the two-tier policy and derivation formulas.

Store responses as:
- `{project_name}` — from question 1
- `{install_scope}` — from question 2 (use `project` if blank; must be one of: `project`, `user`, `local`)
- `{planwise_root}` — from question 3 (use `planwise` if blank)
- `{plans_dir}` — from question 4 (use `Plans` if blank)
- `{backlog_dir}` — from question 5 (use `Backlog` if blank)
- `{lessons_dir}` — from question 6 (use `LessonsLearned` if blank)
- `{plan_tier}` — from question 7 (use `pro` if blank; must be one of: `pro`, `max`). The companion `{context_window}` is derived: `pro` → 200000, `max` → 1000000.
- `{token_saver}` — from question 8 (use `yes` if blank; must be one of: `yes`, `no`). When `yes`, pass `--token-saver` to `init_project.py` (Step 2 / Step 5) so the generated `config.yaml` sets `context.token_saver: true`.

---

### Step 2 — Run the init script (fast path)

Try running the Python init script first. It handles directory creation, seed files, config generation, rule installation, and settings configuration (Agent Teams + plugin permissions) in one command.

**Resolve `{plugin_root}`:** For first-time init, resolve the plugin root from this handler's known location (the plugin base directory provided by SKILL.md). For re-init, read `plugin_root` from the existing `config.yaml`.

Run the script (append `--token-saver` only when `{token_saver}` is `yes`):

```bash
python "{plugin_root}/scripts/init_project.py" --name "{project_name}" --root "{planwise_root}" --plans-dir "{plans_dir}" --backlog-dir "{backlog_dir}" --lessons-dir "{lessons_dir}" --scope "{install_scope}" --plan-tier "{plan_tier}" --token-saver
```

Omit the trailing `--token-saver` flag when `{token_saver}` is `no` — the generated config then sets `context.token_saver: false`.

If `python` is not found, try `python3`.

**If the script succeeds:** Check its output for any skipped files (e.g., config.yaml already exists). If config was skipped, <!-- AUTO-MODE: critical --> ask the user if they want to overwrite — if yes, delete the existing file and re-run the script. Then run **Step 5.1** (idempotent — the Glob check skips when the categorization file already exists; required because the script silently skips this step on systems without PyYAML), run **Step 8.5** (Token Saver calibration capture), and skip to **Step 9** (team sharing).

**If the script fails** (Python not available or any error): Read [handlers/init-fallback.md](init-fallback.md) and follow Steps 3-8 there, then return here and continue at **Step 8.5**.

---

### Step 5.1 — Seed Categorisation file (fallback)

Render `{planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md` from the plugin template, populated with the user's `categorization:` block. This produces the companion file referenced by `{lessons_dir}/00-Index-LessonsLearned.md` and consumed by `/planwise lessons curate` and `/planwise lessons promote-batch`.

> **Note:** This step runs in both the fast-path (after Step 2's script succeeds) and the fallback path. The script in `{plugin_root}/scripts/init_project.py` renders the categorization file when PyYAML is available; if PyYAML is missing the script falls through to this step and Claude renders the file via Read+Write. The Glob check in step 1 below makes the step idempotent — if the file already exists (either from a prior init or from the script just running) the step is a no-op.

> [!practice] Missing `categorization:` Block — Render From Defaults
> When the user's `config.yaml` has no `categorization:` block (or the block is empty), the script falls back to a built-in default that mirrors the 4-bucket template (database / code / process / tooling) and surfaces an INFO line in the Step 10 banner naming the missing block. The downstream skill (`/planwise lessons curate`) still works against the rendered file. Suggest the user run `python init_project.py --migrate` to seed the block into their `config.yaml` for full customisation.
>
> If Claude runs Step 5.1 in fallback mode (because PyYAML is unavailable), apply the same rule: if the user's `config.yaml` lacks the block, use the bucket list from `config.yaml.template` as the default and add a banner line noting it.

1. Use **Glob** to check if `{planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md` already exists — **skip this step if it does**.
2. **Read** `{planwise_root}/config.yaml` (written in Step 5) and extract the `categorization:` block. The block has these keys: `buckets` (list), `decision_tree_order` (list), `default_bucket` (string), `edge_cases_section` (bool). Each bucket has `id`, `slug`, `name`, `description`, and optionally `triggers` (object with `technology` and/or `domain` lists), `sub_buckets` (list of `{id, name}` objects), and `code_bucket` (bool). `triggers` and `code_bucket` are not used by this rendering step — they are consumed by `/planwise lessons curate` and only need to round-trip cleanly through the read.
3. **Read** the template: [../templates/categorization-by-domain.md](../templates/categorization-by-domain.md).
4. Render the template by substituting placeholders and expanding the iteration directives:

   | Placeholder | Substitute With |
   |-------------|-----------------|
   | `{lessons_dir}` | `{lessons_dir}` from Step 1 |
   | `{lessons_index}` | `00-Index-LessonsLearned.md` (from `config.yaml: project.index_files.lessons`) |
   | `{TODAY}` | Today's date in ISO format (`YYYY-MM-DD`) |
   | `{SCOPE_PARAGRAPH}` | Default sentence: `Lessons captured during {project_name} sessions.` (substitute `{project_name}` from Step 1) |

5. Expand `{FOR EACH BUCKET in config.yaml: categorization.buckets:} ... {END}` once per bucket in `decision_tree_order`. For each bucket render:
   - `## {BUCKET_ID}. {BUCKET_NAME} (0)` heading (the `(0)` is a per-bucket lesson count, initialised to 0)
   - `{BUCKET_DESCRIPTION}` paragraph
   - Empty table:
     - Default 3-column schema: `| ID | Title | Severity |`
     - If the bucket has `code_bucket: true` in `config.yaml`, render 4 columns: `| ID | Title | Module | Severity |`
6. Inside each bucket block, expand `{IF bucket has sub_buckets:} ... {END}` once per sub-bucket (skip entirely if `sub_buckets` is empty or absent). For each sub-bucket render:
   - `### {SUB_ID}. {SUB_NAME} (0)` heading
   - Empty table with the same column schema as the parent bucket
7. Preserve the `## Cross-cutting observations` section with its placeholder bullet and the `## Classification edge cases` section with its 3-column header (no rows).
8. Strip the header HTML comment (lines 3-8 of the template) and the inline `<!-- Column schema: ... -->` comments inside each bucket — those are template-authoring notes, not output content.
9. Use **Write** to create `{planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md` with the rendered result.

---

### Step 8.5 — Capture Token Saver calibration

Run only when `{token_saver}` is `yes` (skip silently when Token Saver is off). This attempts to capture a real `/context` footprint and writes the **measured** overheads back into `config.yaml` so plans size sessions against this install's actual carrying cost — not a hardcoded guess. See `references/token-saver-profile.md` for how the derived thresholds are consumed.

> **Best-effort capture.** The `/context` report renders reliably only inside an **interactive** Claude Code session. When `token_saver.calibrate()` is invoked via headless `claude -p "/context"` (as this step does), the CLI may return conversational text instead of the structured report, and calibration degrades to the conservative fallback (runner ~54K / orchestrator ~60K). This is expected on some platforms — notably Windows, where the `claude` shim may not be reachable from a subprocess without a live shell. The conservative fallback is safe: it is deliberately over-estimated so tasks never exceed the session budget. You can recapture real numbers at any time from an interactive session with `/planwise token-saver on`.

1. Run the calibration capture via the Token Saver engine:

   ```bash
   python -c "import sys; sys.path.insert(0, r'{plugin_root}/scripts'); import token_saver; from pathlib import Path; r = token_saver.calibrate(config_path=Path(r'{planwise_root}/config.yaml'), plugin_root=r'{plugin_root}'); print(r)"
   ```

   `token_saver.calibrate()` shells out to `claude -p "/context"`, parses the report, derives `token_saver_runner_overhead` / `token_saver_orchestrator_overhead`, and writes the six `token_saver_*` keys back into `config.yaml` in place. If the capture fails or returns non-report text, it degrades to the conservative fallback — it never crashes init.

2. Surface the result. Report the measured footprint and flag uncalibrated installs loudly:

   ```
   Token Saver: ON
     Measured runner overhead:       {token_saver_runner_overhead}  tokens
     Measured orchestrator overhead: {token_saver_orchestrator_overhead}  tokens
     Per-task budget (derived):      ~{available_per_task}  tokens  (session_target − runner_overhead − growth_margin)
     Calibrated on:                  {token_saver_overhead_measured_on}
   ```

   If the result's `uncalibrated` flag is `true` (the `/context` capture failed or returned non-report text — expected on some platforms, notably Windows), add:

   ```
     ! Uncalibrated — used conservative fallback (runner ~54K / orchestrator ~60K).
       Run `/planwise token-saver on` from an interactive session to capture real numbers.
   ```

---

### Step 9 — (Optional) Configure team sharing

<!-- AUTO-MODE: convenience -->
<!-- Default: No. SUPPRESSED ENTIRELY when --auto-from flag is set (subroutine mode). -->
Use `AskUserQuestion`:

> "Share this planwise plugin with your team via .claude/settings.json? (Yes / No)"

**If Yes:**
- Read `.claude/settings.json` (create if it does not exist)
- Add or merge `enabledPlugins` entry — preserve all existing settings:
  ```json
  {
    "enabledPlugins": {
      "planwise@local": true
    }
  }
  ```
- Write the updated settings back

**If No:** Skip this step silently.

---

### Step 9.5 — (Optional) GitHub CLI for upstream feedback

<!-- AUTO-MODE: convenience -->
<!-- Default: No — an unattended run NEVER invokes a package manager. SUPPRESSED ENTIRELY when --auto-from flag is set (subroutine mode). -->

Probe for the GitHub CLI by running `gh --version`. If it resolves, skip this step
silently — there is nothing to offer.

If it does not resolve, use `AskUserQuestion`:

> "The GitHub CLI (`gh`) isn't installed. planwise uses it so `/planwise feedback` can
> file your bugs, lessons, and ideas upstream directly. Without it feedback still works —
> your report is saved as a draft file that you paste into the issues page yourself.
> Install it now? (Yes / No)"

**If Yes:** run the install command for the detected platform, then re-probe with
`gh --version` and report the result:

| Platform | Command |
|---|---|
| Windows | `winget install --id GitHub.cli` |
| macOS | `brew install gh` |
| Linux (Debian 12+ / Ubuntu 23.04+) | `sudo apt install gh` |
| Linux (Fedora) | `sudo dnf install gh` |
| Anything else | Do not guess — print https://cli.github.com/manual/installation |

Run **one** command — the one matching the detected platform. If that platform's package
manager is absent, or the install exits non-zero, do NOT retry with a different manager
and do NOT escalate privileges beyond the single command above. Print the failing command,
its exit status, and https://cli.github.com/ so the user can install by hand, then
continue. A failed install NEVER blocks init.

**After a successful install,** print both remaining steps — the binary alone does not
make posting work, and stopping at "installed" strands the user at the engine's next two
gates:

```
gh installed ({version}).

Two things still gate upstream posting:
  1. Authenticate:  gh auth login
     (an interactive browser/device flow — run it yourself; init will not
      authorize an account on your behalf)
  2. Opt in:        set feedback.enabled: true in {planwise_root}/config.yaml
     (posting is opt-in and off by default)

Until both are done, /planwise feedback saves a local draft instead of posting.
```

**If No:** skip silently. `/planwise feedback` degrades to local drafts, which is a
supported configuration and not a degraded install.

---

### Step 10 — Output confirmation

Output a summary of all actions taken:

```
/planwise init — Complete

Project: {project_name}
Scope: {install_scope}

Directories created:
  ✓ {planwise_root}/
  ✓ {planwise_root}/{plans_dir}/
  ✓ {planwise_root}/{backlog_dir}/
  ✓ {planwise_root}/{lessons_dir}/

Seed files installed:
  ✓ {planwise_root}/{plans_dir}/00-Index-Plans.md
  ✓ {planwise_root}/{backlog_dir}/00-Index-Backlog.md
  ✓ {planwise_root}/{lessons_dir}/00-Index-LessonsLearned.md
  ✓ {planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md  (rendered from config.yaml: categorization)

Configuration:
  ✓ {planwise_root}/config.yaml (scope: {install_scope}, plan tier: {plan_tier} → {context_window} context window)

Token Saver:
  ✓ {token_saver} (when ON: runner overhead {token_saver_runner_overhead}, derived per-task budget ~{available_per_task} — from Step 8.5 calibration)

Agent Teams:
  ✓ CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 → {settings_file}

Plugin permissions:
  ✓ additionalDirectories: {plugin_root} → {settings_file}

Rules installed to .claude/rules/planwise/:
  ✓ agent-authoring.md              (paths: .claude/agents/**)
  ✓ skill-authoring.md              (paths: .claude/skills/**)
  ✓ rule-authoring.md               (paths: .claude/rules/**)
  ✓ artifact-self-containment.md    (paths: .claude/rules/**, .claude/agents/**, .claude/skills/**, .claude/commands/**, CLAUDE.md)

  (Plan/backlog/lessons reference rules are handler-loaded on demand from the
   plugin's references/ directory — not installed as path-scoped rules.)

Skipped (action required):
  ! {planwise_root}/config.yaml (key: context)
      reason:      config.yaml has no `context:` block — likely a config that predates this key
      affects:     /planwise plan, /planwise review, /planwise run (token-budget scaling)
      remediation: Run `python {plugin_root}/scripts/init_project.py --name "{project_name}" --migrate` to merge the block from the template.
  ! {planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md
      reason:      PyYAML not installed (cannot read config.yaml from the script path)
      affects:     /planwise lessons curate, /planwise lessons promote-batch
      remediation: Install PyYAML (`pip install pyyaml`), or run /planwise init and let the handler's Step 5.1 fallback render the file via Read+Write.

Next steps:
  /planwise plan          — Create your first plan
  /planwise backlog       — Triage your backlog
  /planwise list          — List all plans
```

Replace `{settings_file}` with the actual path used based on scope. Adjust the output to reflect what was actually created vs. skipped.

> [!constraint] SKIPPED Section MUST Be Loud
> WRONG — the banner is silent about a non-rendered artifact; the gap surfaces later when the downstream skill fails:
> ```
> Categorization: skipped (config.yaml: categorization block missing or unparseable)
>
> Done!
> ```
> CORRECT — the SKIPPED section enumerates every artifact that was not produced with reason, affected consumer skill, and remediation hint; the user can act before the downstream skill is invoked:
> ```
> Categorization: + {planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md (rendered with default buckets — config.yaml `categorization:` block missing)
>                   Add the block to customise buckets, or run --migrate to seed it from the template.
>
> Skipped (action required):
>   ! {planwise_root}/config.yaml (key: context)
>       reason:      config.yaml has no `context:` block — likely a config that predates this key
>       affects:     /planwise plan, /planwise review, /planwise run (token-budget scaling)
>       remediation: Run `python {plugin_root}/scripts/init_project.py --name "{project_name}" --migrate` to merge the block from the template.
>   ! {planwise_root}/config.yaml (key: plugin_version)
>       reason:      pinned plugin_version `1.1.0` is older than the installed plugin `1.2.0` — installed rules/agents may be stale
>       affects:     all handlers (rule and agent freshness)
>       remediation: Run `python {plugin_root}/scripts/init_project.py --name "{project_name}" --upgrade` (or `/planwise upgrade`) to refresh artifacts.
>
> Done!
> ```

When running the fallback path manually (Steps 3-8 in [init-fallback.md](init-fallback.md) instead of the Python script), Claude MUST reproduce the SKIPPED section by tracking, for each step that did not produce its expected artifact, the (artifact, reason, affects, remediation) tuple and emitting them under the `Skipped (action required):` heading. Reference the manifest at [../manifests/artifacts.yaml](../manifests/artifacts.yaml) for the canonical artifact / consumer / remediation mapping.

---

### Step 11 — Migrate an existing project's config.yaml

When the plugin adds a new top-level config block (for example, `context:` for
plan-tier scaling, or `categorization:` for lesson bucketing), projects whose
`config.yaml` predates that block do not pick it up by re-running `/planwise init` —
the config gate sees the file exists and skips regeneration. `--migrate` solves
this without overwriting user customisations.

**Invocation:**

```bash
python "{plugin_root}/scripts/init_project.py" --name "{project_name}" --migrate
```

**What it does (idempotent):**

1. Resolves `{planwise_root}/config.yaml` (must already exist — otherwise it errors and instructs you to run plain `/planwise init`).
2. Reads `config.yaml.template`, replaces the placeholders, and parses both files.
3. For each top-level key in the script's `MIGRATABLE_TOP_LEVEL_KEYS` list (`plugin_root`, `context`, `categorization`):
   - If the key is **absent** in the user's config → copies the template value in.
   - If the key is **present** → leaves it untouched, no value overwriting.
4. Re-emits the merged config preserving the user's leading comment header.
5. Reports which keys were added vs. which were already present.

**When to recommend `--migrate`:**

| Scenario | Action |
|----------|--------|
| Step 10 banner lists a `migrate_only` SKIPPED row | Run `--migrate`, then re-run the affected handler. |
| User upgraded the plugin and a new key appeared in the template | Run `--migrate` once. |
| User edited `config.yaml` and a key disappeared by accident | Run `--migrate` to restore it from the template. |

**What `--migrate` does NOT do:**

- Does NOT re-render seed files, rules, or agents (those are install-time only).
- Does NOT modify `settings.json` (use plain `/planwise init` for settings drift).
- Does NOT touch existing keys — even if the template's default differs from the user's value, the user's value wins.

---

## Called As Subroutine

When another handler detects a missing `config.yaml` and invokes `/planwise init` via the
Auto-Init Fallback, the init handler runs in **subroutine mode**:

- The calling handler passes `--auto-from {handler-name}` to `init_project.py`.
- The team-sharing prompt (Step 9) is suppressed — no `AskUserQuestion` is issued.
- The Step 10 banner is replaced by: "Init complete — resuming /planwise {caller}…"
- All other steps execute normally (directories, seeds, config, rules, settings).
- If Auto Mode is active in the caller, all convenience questions in Step 1
  (project name, install scope, directories) use their inferred defaults
  (see Auto Mode Policy in `references/auto-mode-policy.md` § Inference Defaults). If Auto Mode is NOT
  active, Step 1 runs interactively as normal.
- After the subroutine returns, the calling handler RE-RESOLVES `config.yaml` and
  resumes at its own Step 1.
