# Handler: /planwise upgrade

**Purpose:** Refresh installed plugin artifacts (rules in `.claude/rules/planwise/`, agents in `.claude/agents/`) and bump the pinned `plugin_version:` in `config.yaml` after a plugin update.

## Table of Contents

- [Config Gate](#config-gate)
- [Workflow](#workflow)
  - [Step 1 — Detect drift](#step-1--detect-drift)
  - [Step 1.5 — Offer Token Saver mode](#step-15--offer-token-saver-mode)
  - [Step 2 — Invoke the upgrade script](#step-2--invoke-the-upgrade-script)
  - [Step 2.5 — Refresh Token Saver calibration](#step-25--refresh-token-saver-calibration)
  - [Step 2.6 — Lessons scaffolding backfill (PyYAML-missing fallback)](#step-26--lessons-scaffolding-backfill-pyyaml-missing-fallback)
  - [Step 3 — Render the banner](#step-3--render-the-banner)
  - [Step 4 — Resolve conflicts](#step-4--resolve-conflicts)
- [Conflict Resolution Reference](#conflict-resolution-reference)
- [Auto-Init Fallback](#auto-init-fallback)

---

## Config Gate

Locate `config.yaml` by checking, in order:

1. `planwise/config.yaml` (default planwise root)
2. One level down from project root for `*/config.yaml`
3. If still not found → branch to [Auto-Init Fallback](#auto-init-fallback)

Extract from `config.yaml`:
- `plugin_root` — the plugin installation path
- `plugin_version` — currently-pinned plugin version (treat absent as `"0.0.0"`)
- `project.planwise_root`, `project.plans_dir`, `project.backlog_dir`, `project.lessons_dir`, `project.index_files.*`

---

## Workflow

### Step 1 — Detect drift

Read `{plugin_root}/.claude-plugin/plugin.json` and extract `version`. Compare to the user's pinned `plugin_version:`:

> [!gate] Upgrade Gate
> If `pinned == shipped` → report "Plugin version: {version} — already up to date." and exit.
> If `pinned < shipped` (or `pinned` is absent) → proceed to Step 2.
> If `pinned > shipped` → emit a warning ("Your config pins {pinned} but the installed plugin is {shipped} — did you downgrade?") and ask the user with `AskUserQuestion` whether to proceed.

---

### Step 1.5 — Offer Token Saver mode

Token Saver is a budget mode that keeps task sessions under ~150K and warns when a file is too large to fit a lean task (see `references/session-context-budget.md` "Token Saver Profile"). Read `context.token_saver` from the user's `config.yaml` (treat absent as `false`).

> [!gate] Token Saver Upgrade Prompt
> If `context.token_saver` is already `true` → skip this prompt; Token Saver stays enabled, store `{token_saver} = yes`.
> If `context.token_saver` is `false` or absent → use `AskUserQuestion`:
>
> > "A new Token Saver mode is available — enable it? It keeps task sessions under ~150K (avoids the linear carrying-cost of big sessions) and warns when a file is too large to fit a lean task. (Yes / No)"
>
> Store the choice as `{token_saver}` (`yes` / `no`). When `yes`, pass `--token-saver` to the upgrade script in Step 2.

---

### Step 2 — Invoke the upgrade script

Append `--token-saver` only when `{token_saver}` (from Step 1.5) is `yes`:

```bash
python "{plugin_root}/scripts/init_project.py" --project-root "{project_root}" --name "{project_name}" --root "{planwise_root}" --plans-dir "{plans_dir}" --backlog-dir "{backlog_dir}" --lessons-dir "{lessons_dir}" --scope "{install_scope}" --upgrade --token-saver
```

Omit the trailing `--token-saver` when `{token_saver}` is `no` — the upgrade leaves the existing `context.token_saver` value untouched (migration is non-destructive; it never flips a user-set toggle off).

`{project_root}` is the absolute path of the project root (the directory containing `{planwise_root}/`). Pass it explicitly so the upgrade writes to the correct tree even when the user invokes `/planwise upgrade` from a subdirectory — the script's default of `Path.cwd()` is incorrect in that case.

If `python` is not found, try `python3`.

The script:
1. Runs `migrate_config()` to merge any new top-level keys into `config.yaml`
2. Calls `bootstrap_lessons_artifacts()` to backfill the lessons scaffolding — seeds `{lessons_dir}/00-Index-LessonsLearned.md` and renders `{lessons_dir}/00-Categorization-By-Domain.md` — whenever either is missing. Idempotent and non-destructive: a no-op when both already exist, and an existing (possibly user-customised) file is preserved verbatim. This recovers the categorization file that gates `/planwise lessons curate` and `promote-batch` on projects adopted via `/planwise upgrade` rather than a fresh `/planwise init` (the render used to be fresh-init-only). Runs after `migrate_config()` so a freshly-migrated `categorization:` block is picked up; falls back to the built-in default buckets (and flags it in the banner) when the block is absent
3. Iterates `manifests/artifacts.yaml` rows where `upgrade_behavior == "refresh_or_sidecar"`
4. Refreshes installed copies whose normalised body matches the shipped body
5. Writes `.new` sidecars under `{planwise_root}/upgrade-conflicts/<from>-to-<to>/` for any installed copy that has diverged
6. Runs `migrate_installed_rules()` (version-gated on `RESCOPE_MIGRATION_VERSION`) to retire rules that are now handler-loaded from `references/`: it **removes** an installed `.claude/rules/**` copy ONLY when its body AND its `paths:` both match the original shipped default (i.e., untouched); it **preserves** byte-for-byte any copy whose body OR `paths:` were customised, emitting an action-required re-home notice (never a default delete)
7. Runs `lint_rule_overscope()` and appends a post-upgrade advisory listing any `.claude/rules/**` still scoped to plan/backlog/lessons paths, with size
8. Bumps `plugin_version:` in `config.yaml` LAST, as the commit point

Capture stdout — the banner is rendered from it.

---

### Step 2.5 — Refresh Token Saver calibration

Run only when `{token_saver}` (from Step 1.5) resolves to `yes` — i.e., Token Saver is enabled after the upgrade (either pre-existing or just turned on). Skip silently when Token Saver is off.

The measured overheads in `config.yaml` go **stale on upgrade**: a plugin update changes the always-on rule/agent surface a fresh `/context` loads, so `token_saver_runner_overhead` captured against the old version no longer reflects this install. Re-capture so plans size against the new footprint.

> **Best-effort capture.** The `/context` report renders reliably only inside an **interactive** Claude Code session. When `token_saver.calibrate()` is invoked from upgrade (headless), the CLI may return conversational text instead of the structured report, and calibration degrades to the conservative fallback (runner ~54K / orchestrator ~60K). This is expected on some platforms — notably Windows. The conservative fallback is safe; recapture from an interactive session with `/planwise token-saver on`.

1. Re-run the calibration capture against the upgraded install:

   ```bash
   python -c "import sys; sys.path.insert(0, r'{plugin_root}/scripts'); import token_saver; from pathlib import Path; r = token_saver.calibrate(config_path=Path(r'{planwise_root}/config.yaml'), plugin_root=r'{plugin_root}'); print(r)"
   ```

   `token_saver.calibrate()` overwrites the six `token_saver_*` keys in place (targeted edit — comments and key order preserved) and degrades to the conservative fallback if the `/context` capture fails or returns non-report text.

2. Report the refreshed numbers in the chat summary (append to the Step 3 banner):

   ```
   Token Saver recalibrated:
     Runner overhead:       {old} → {token_saver_runner_overhead}
     Orchestrator overhead: {old} → {token_saver_orchestrator_overhead}
     Calibrated on:         {token_saver_overhead_measured_on}
   ```

   If the result's `uncalibrated` flag is `true`, note that the conservative fallback was written (capture failed or returned non-report text — expected on some platforms) and suggest running `/planwise token-saver on` from an interactive session to capture real numbers.

---

### Step 2.6 — Lessons scaffolding backfill (PyYAML-missing fallback)

`_run_upgrade()` performs the lessons-scaffolding backfill itself (numbered item 2 in [Step 2](#step-2--invoke-the-upgrade-script)) whenever PyYAML is available — the normal case, since `--upgrade` hard-requires PyYAML and otherwise exits with `Upgrade failed: PyYAML is required for --upgrade`. Run this handler-side fallback **only** when the upgrade script aborted for that reason, so the categorization gate that protects `/planwise lessons curate` and `promote-batch` is still unblocked. Mirrors [init.md](init.md) Step 5 / 5.1 — the same render, reached from the upgrade path.

1. Use **Glob** to check whether `{planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md` already exists — **skip this step if it does** (idempotent; never overwrite a populated file).
2. **Read** the template: [../templates/categorization-by-domain.md](../templates/categorization-by-domain.md).
3. Populate it from the user's `config.yaml: categorization:` block, one section per bucket in `decision_tree_order`.
   > [!practice] Missing `categorization:` Block — Render From Defaults
   > When the block is absent or empty, use the 4-bucket default from [../config.yaml.template](../config.yaml.template) (database / code / process / tooling) and add a banner line noting defaults were used. Suggest `python init_project.py --migrate` to seed the block into `config.yaml` for full customisation.
4. If `{planwise_root}/{lessons_dir}/00-Index-LessonsLearned.md` is missing, also copy it from [../seed/00-Index-LessonsLearned.md](../seed/00-Index-LessonsLearned.md).
5. Use **Write** to create the categorization file with the rendered result, and surface it under the banner's `Lessons scaffolding backfilled:` heading.

---

### Step 3 — Render the banner

The script emits a structured report. Pass it through verbatim to the user. The output follows this shape:

```
Plugin upgrade: {from} -> {to}

Config keys added:    {N}  ({list, or "(none)"})

Lessons scaffolding backfilled:           ({omitted entirely when both already exist})
  + {planwise_root}/{lessons_dir}/00-Index-LessonsLearned.md
  + {planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md
  …

Refreshed: {N}
  + {file}
  …
Unchanged: {N} (installed body already matches shipped)
Untracked preserved: {N}
  = {file}
  …

De-scoped rules removed: {N} (now handler-loaded; installed copy was untouched)
  - {file}
  …
De-scoped rules preserved (action required): {N} (customised — re-home, NOT auto-deleted)
  ! {file}
      reason: body or paths customised — not safe to auto-remove
      action: re-home as a project-local rule, OR re-scope paths: to the code dirs it governs, OR upstream the change

Conflicts (action required):
  ! {file}
      reason:      installed body diverged from plugin-shipped version
      sidecar:     {sidecar path}
      remediation: diff the sidecar against the installed file, merge manually, then delete the .new

Over-scope advisory: {N} rule(s) still scoped to plan/backlog paths (~{X}K injected per task-runner)
  run `/planwise doctor` for the full report

Plugin version pinned: {to}

Upgrade complete.
```

Then summarise in the chat with this template:

```
Plugin upgrade: {from} -> {to}

Config keys added:       {N}        ({list, or "(none)"})
Lessons backfilled:      {N}        (categorization file / index seed — gates lessons curate; "(none)" when both present)
Artifacts refreshed:     {N}
Artifacts unchanged:     {N}        (installed body already matched shipped)
Untracked preserved:     {N}        ({list of files outside the manifest allowlist})
De-scoped removed:       {N}        (now handler-loaded; installed copy was untouched)
De-scoped preserved:     {N}        (customised — action required, re-home not delete)
Conflicts:               {N}        (see Step 4 if > 0)
Over-scope advisory:     {N}        (rules still plan/backlog-scoped — run `/planwise doctor`)

Plugin version pinned:   {to}

Upgrade complete.
```

If conflicts > 0, append the conflict list verbatim from the script's stdout and direct the user to Step 4. If de-scoped-preserved > 0, surface the re-home notice for each (the action choices: project-local rule / re-scope `paths:` / upstream). If the over-scope advisory is > 0, point the user at `/planwise doctor`.

---

### Step 4 — Resolve conflicts

For each conflict in `{planwise_root}/upgrade-conflicts/<from>-to-<to>/`:

1. The user diffs `<destination>.md` against `<destination>.md.new`
2. If the changes are acceptable → overwrite the installed file with the sidecar content (or merge selectively) → delete the `.new` file
3. If the user wants to keep their local edits → simply delete the `.new` file

The `upgrade-conflicts/` directory and its `INDEX.md` can be cleaned up once all sidecars are resolved.

---

## Conflict Resolution Reference

> [!practice] Why sidecars and not overwrites
> Rules in `.claude/rules/planwise/` and agents in `.claude/agents/` are user-installable artifacts. A user may have hand-edited a rule to extend its `paths:` glob, refine its prose, or add a project-specific subsection. `/planwise upgrade` MUST NOT silently overwrite that work. Sidecars preserve the user's copy and let them merge intentionally.

| Scenario | What the script does | What the user does |
|---|---|---|
| Installed body matches shipped (normalised) | Skips rewrite (no-op) | Nothing — file is current |
| Installed body matches shipped, but `paths:` differs | Skips rewrite | Nothing — `paths:` is per-project |
| Installed body diverged | Writes `.new` sidecar | Diff, merge, delete `.new` |
| Installed file absent | Writes shipped body fresh | Nothing — file just appeared |
| File present, not in manifest allowlist | Reports as Untracked | Nothing — file is the user's own |
| De-scoped rule, installed body **and** `paths:` untouched | Removes the redundant installed copy (rule is now handler-loaded from `references/`) | Nothing — the rule still applies, loaded on demand |
| De-scoped rule, body **or** `paths:` customised | Preserves byte-for-byte + emits an action-required re-home notice (never auto-deletes) | Re-home: keep as a project-local rule, re-scope `paths:` to the code dirs it governs, or upstream the change |

---

## Auto-Init Fallback

If the config gate fails (no `config.yaml` found), the project hasn't been initialised. `--upgrade` will exit non-zero in that case. Surface this clearly:

```
This project doesn't have a planwise config yet. Run `/planwise init` first.
```

Offer to run `/planwise init` via `AskUserQuestion` and, on confirmation, dispatch to `init.md`'s Step 1. Once init completes, the upgrade is unnecessary (the freshly-generated config pins the current plugin version).

---

*Cross-reference: [init.md](init.md), [migrate logic in scripts/init_project.py](../scripts/init_project.py).*
