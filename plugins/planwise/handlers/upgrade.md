# Handler: /planwise upgrade

**Purpose:** Refresh installed plugin artifacts (rules in `.claude/rules/planwise/`) and bump the pinned `plugin_version:` in `config.yaml` after a plugin update.

## Table of Contents

- [Config Gate](#config-gate)
- [Workflow](#workflow)
  - [Step 1 — Detect drift](#step-1--detect-drift)
  - [Step 1.5 — Offer Token Saver mode](#step-15--offer-token-saver-mode)
  - [Step 2.1 — `--list-diverged` pre-scan](#step-21--list-diverged-pre-scan)
  - [Step 2.2 — Comparator fan-out (interactive only)](#step-22--comparator-fan-out-interactive-only)
  - [Step 2.3 — Write `verdicts.json`](#step-23--write-verdictsjson)
  - [Step 2.4 — Invoke the upgrade script](#step-24--invoke-the-upgrade-script)
  - [Step 2.5 — Refresh Token Saver calibration](#step-25--refresh-token-saver-calibration)
  - [Step 2.6 — Lessons scaffolding backfill (PyYAML-missing fallback)](#step-26--lessons-scaffolding-backfill-pyyaml-missing-fallback)
  - [Step 3 — Render the banner](#step-3--render-the-banner)
  - [Step 4 — Resolve conflicts](#step-4--resolve-conflicts)
  - [Step 4.1 — Assisted relocation](#step-41--assisted-relocation)
  - [Step 4.2 — Opt-in upstream GitHub issue](#step-42--opt-in-upstream-github-issue)
  - [Step 4.3 — Interactive per-class cleanup offer](#step-43--interactive-per-class-cleanup-offer)
- [Conflict Resolution Reference](#conflict-resolution-reference)
- [Auto-Init Fallback](#auto-init-fallback)

---

## Config Gate

Locate `config.yaml` by checking, in order:

1. `planwise/config.yaml` (default planwise root)
2. One level down from project root for `*/config.yaml`
3. If still not found → branch to [Auto-Init Fallback](#auto-init-fallback)

Resolve **`{plugin_root}`** — used in every script invocation below — from this handler's own known location (the plugin base directory provided by SKILL.md), the same resolution [init.md](init.md) uses for first-time init. This is the LIVE, currently-invoked plugin; it is NOT read from `config.yaml`.

Extract from `config.yaml`:
- `plugin_root` (config value, distinct from the live `{plugin_root}` above) — the plugin root the last init/upgrade wrote. Display/fallback only — see the Step 1 mismatch note; never substitute it for the live `{plugin_root}` in a script invocation.
- `plugin_version` — currently-pinned plugin version (treat absent as `"0.0.0"`)
- `project.planwise_root`, `project.plans_dir`, `project.backlog_dir`, `project.lessons_dir`, `project.index_files.*`

---

## Workflow

### Step 1 — Detect drift

Read `{plugin_root}/.claude-plugin/plugin.json` and extract `version` — the live root resolved in the Config Gate, always, so this comparison can never be fooled by a stale configured `plugin_root:`. Compare to the user's pinned `plugin_version:`:

> [!gate] Upgrade Gate
> If `pinned == shipped` **and** the config's stored `plugin_root` matches the live `{plugin_root}` → report "Plugin version: {version} — already up to date." and exit.
> If `pinned == shipped` **but** the stored `plugin_root` differs → do NOT exit; skip the comparator fan-out (Steps 2.1–2.3 have nothing to compare — no artifact changed) and run the Step 2.4 script invocation, which repoints the root on its own. Report the result as "Plugin root repointed", not as a version change. See the mismatch note below.
> If `pinned < shipped` (or `pinned` is absent) → proceed to Step 2.1.
> If `pinned > shipped` → emit a warning ("Your config pins {pinned} but the installed plugin is {shipped} — did you downgrade?") and ask the user with `AskUserQuestion` whether to proceed.

> [!practice] A `plugin_root` mismatch is itself upgrade-indicating
> If the config's stored `plugin_root` differs from the live `{plugin_root}` resolved above, that is a defect to act on even when the version pin looks current: it means an earlier upgrade pinned the version without repointing the root (a config written before the writer's commit point started repointing both together), or the directory it still names was later removed. Left alone it does not heal — every handler that resolves scripts through the stored value keeps running a superseded install, or fails outright once that directory is reaped. The script's `--upgrade` invocation (Step 2.4) repoints `plugin_root` to the live root even when the version pin is already current, and does nothing else in that state, so the gate above routes this case to it rather than exiting.

---

### Step 1.5 — Offer Token Saver mode

Token Saver is a budget mode that keeps task sessions under ~150K and warns when a file is too large to fit a lean task (see `references/token-saver-profile.md`). Read `context.token_saver` from the user's `config.yaml` (treat absent as `false`).

> [!gate] Token Saver Upgrade Prompt
> If `context.token_saver` is already `true` → skip this prompt; Token Saver stays enabled, store `{token_saver} = yes`.
> If `context.token_saver` is `false` or absent → use `AskUserQuestion`:
>
> > "A new Token Saver mode is available — enable it? It keeps task sessions under ~150K (avoids the linear carrying-cost of big sessions) and warns when a file is too large to fit a lean task. (Yes / No)"
>
> Store the choice as `{token_saver}` (`yes` / `no`). When `yes`, pass `--token-saver` to the upgrade script in Step 2.4.

---

> [!decide] Interactive upgrade sequence (integration note)
> | Order | Step | Mode | Mutates? |
> |-------|------|------|----------|
> | 1 | Step 1 / 1.5 — detect drift, Token Saver opt-in | both | no |
> | 2 | Step 2.1 — `--list-diverged` pre-scan | both | no |
> | 3 | Step 2.2 — comparator fan-out | interactive only | no |
> | 4 | Step 2.3 — write `verdicts.json` | interactive only | cache only |
> | 5 | Step 2.4 — invoke `--upgrade` (the single writer) consuming `verdicts.json` | both | **yes** |
> | 6 | Step 2.5 — Token Saver recalibration | both | config |
> | 7 | Step 2.6 — Lessons scaffolding backfill fallback | both | config (PyYAML-missing case only) |
>
> Headless / non-interactive: skip rows 3–4; the writer (row 5) runs with no `verdicts.json` and disposes
> every diverged file via the inline `_classify_diverged()` primitive — including the automated
> transfer-then-adopt path for customization-bearing verdicts (see Step 2.4, item 5).

### Step 2.1 — `--list-diverged` pre-scan

Both modes, read-only. Same arg shape as `--upgrade`, minus `--name` (the diagnostic is self-scoped):

```bash
python "{plugin_root}/scripts/init_project.py" --project-root "{project_root}" --root "{planwise_root}" --plans-dir "{plans_dir}" --backlog-dir "{backlog_dir}" --lessons-dir "{lessons_dir}" --scope "{install_scope}" --list-diverged
```

Parse the JSON array printed to stdout. Each row is `{"filename", "kind": "rule", "installed": <project-root-relative POSIX path>, "shipped": <plugin-root-relative POSIX path>}`, stable-sorted by `filename`. The scan walks both the active install set and any de-scoped rules still on disk; the byte/normalized-identical majority never appears here. `[]` → nothing diverges; skip Steps 2.2–2.3 entirely and go straight to Step 2.4 — the writer runs a pure refresh with no fan-out to do. A non-empty list carries into Step 2.2.

---

### Step 2.2 — Comparator fan-out (interactive only)

Gate: a live interactive session **AND** Step 2.1 returned a non-empty list. Otherwise skip — the Step 2.4 writer's inline primitive covers every diverged file on its own.

Spawn `planwise:rule-comparator` **once per diverged file in a single parallel batch** — issue every `Task` call together in one message (no waiting between spawns), mirroring `review.md` Phase 2 (the fan-out batch pattern). Spawns MUST be `planwise:`-namespaced. Each comparator is one-shot: it returns its verdict and goes idle (idle is normal — do not treat it as an error).

```
Task(
  subagent_type: "planwise:rule-comparator",
  description: "Compare {filename} (installed vs shipped)",
  prompt: |
    First action: call ToolSearch(query: "select:SendMessage", max_results: 1) before reading any file.

    Compare ONE artifact pair and return a semantic verdict.
    filename:       {filename}
    kind:           rule
    installed_path: {absolute installed path}
    shipped_path:   {absolute shipped path}

    Follow your Rule Comparator Protocol. Strip the paths: line for rules;
    classify SEMANTICALLY (reflow / reword / reorder are SHARED, not unique).
    Return ONE fenced json verdict in the StructuralVerdict shape with
    source:"agent", filename, and a home_hints map.
    End with: "Comparator complete: {filename} → {classification}"
)
```

Collect the N verdicts (each comparator's returned/`SendMessage`d JSON). If a comparator fails to return, fall back to the inline primitive for that one file (omit it from `verdicts.json`).

---

### Step 2.3 — Write `verdicts.json`

Write the collected verdicts to `{planwise_root}/upgrade-conflicts/{from}-to-{to}/verdicts.json`, keyed by filename — the only place the writer reads this cache from disk. Each entry is the comparator's `StructuralVerdict` shape **plus an `installed_sha256` freshness binding** (see below). A SUBSET entry's `notes` is `""` when clean — non-empty `notes` is reserved for verbatim tolerated installed-only fragment text and routes the file to the customization-handling path (see the notes-contract constraint in [rule-comparator.md](../agents/rule-comparator.md)):

```json
{
  "callout-conventions.md": {
    "classification": "HAS_UNIQUE", "confidence": "unique",
    "unique_blocks": ["[!constraint] Project DB-write callout"],
    "home_hints": {"[!constraint] Project DB-write callout": "localize"},
    "source": "agent", "shared_blocks": 19, "total_installed_blocks": 20,
    "installed_only_chars": 540, "unique_sample_tokens": ["warehouse","merge"], "notes": "",
    "installed_sha256": "9f8a…64-hex-chars…c1d2"
  },
  "scaffolding-hygiene.md": {
    "classification": "SUBSET", "confidence": "contained",
    "unique_blocks": [], "home_hints": {}, "source": "agent",
    "shared_blocks": 12, "total_installed_blocks": 12,
    "installed_only_chars": 0, "unique_sample_tokens": [], "notes": "",
    "installed_sha256": "3b7e…64-hex-chars…a9f0"
  }
}
```

> [!constraint] `installed_sha256` — bind each verdict to the bytes it analyzed
> The writer IGNORES any entry whose `installed_sha256` is missing or does not
> match the sha256 of the installed file's current bytes (one-line stderr note,
> falls back to the inline primitive) — a cached verdict must never drive a
> destructive disposition against content it didn't analyze. YOU (the
> orchestrator) compute and write this hash per entry, over the SAME installed
> file you handed that entry's comparator:
>
> WRONG: omit the hash, or hash the shipped file.
> CORRECT — one command per entry, hashing the installed path:
> ```bash
> python "{plugin_root}/scripts/init_project.py" --hash-installed "{absolute installed path}"
> ```
> The digest is computed over a normalized pre-image, matching the writer's recompute by construction.
>
> After a successful `--upgrade` run consumes the cache, the script renames
> `verdicts.json` to `verdicts.json.consumed` so a stale verdict can never fire
> on a later pair or re-run. Do NOT resurrect a `.consumed` file — re-run the
> fan-out (Step 2.2) if a fresh cache is needed.

---

> [!escalation] Comparator fidelity degradation chain
> 1. **Interactive + agents available** → spawn `rule-comparator` per diverged
>    file, write `verdicts.json`, and the `--upgrade` writer honors each agent
>    verdict (`source: "agent"`). Highest fidelity — the semantic read separates
>    reflow / reword / reorg from genuine installed-only content.
> 2. **Headless, or interactive with fan-out unavailable / declined** → no
>    `verdicts.json`; the writer falls back to the inline `_classify_diverged()`
>    primitive for every diverged file. Always sufficient and safe: with
>    `upgrade.customization_handoff: report+relocate` (the shipped template
>    default) the writer's automated transfer-then-adopt path (Step 2.4, item 5)
>    still runs off the primitive's verdict, so a customization is never deleted
>    — a failed transfer, a failed pre-image backup, or a degraded not-analyzed
>    stand-in verdict falls back to preserve + sidecar. With `report` /
>    `report+issue` (or the key absent) the writer is fully conservative:
>    customization-bearing files are preserved in place + sidecar'd, no transfer,
>    no adoption. (Subagent spawning renders reliably only inside an interactive
>    Claude Code session — expected to be unavailable on some platforms; the
>    inline path is the intended fallback, not an error.)
> 3. **`gh` absent, or `upgrade.github_issue: false`, or non-interactive** → the
>    upstream handoff degrades from a live upstream post
>    (`references/feedback-submission.md`) to a written issue-body draft file
>    under `upgrade-conflicts/{from}-to-{to}/issue-drafts/`. Never blocks the
>    upgrade.
>
> The inline primitive plus the automated transfer-first writer is the floor:
> every path yields a complete, idempotent, headless-safe disposition that never
> destroys a customization without moving it first. The agent path and the
> outward handoffs (Steps 4.1/4.2) only raise fidelity / ergonomics on the
> diverged minority — never required for correctness.

### Step 2.4 — Invoke the upgrade script

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
5. Classifies each **diverged** installed copy with the structural verdict — consuming `verdicts.json` when present (a comparator verdict for a filename **supersedes** the inline primitive; a missing entry, a malformed entry, or an entry whose `installed_sha256` is missing/stale falls back to the primitive). A clean **stale subset** is auto-adopted in place directly: rules refresh via `update_frontmatter()` (the project's `paths:` line is preserved). Any OTHER divergence — HAS_UNIQUE or a subset whose `notes` flag installed-only tolerated content — is **customization-bearing**, gated by `upgrade.customization_handoff`: under `report+relocate` (the shipped template default) the writer first **transfers** the full installed body (plus a generic provenance header — source filename, kind, upgrade pair, date, verdict summary) to `{planwise_root}/upgrade-transfers/{from}-to-{to}/{filename}` — a **dormant preservation document** outside `.claude/rules/`, never loaded as a rule (a collision is uniquified with a numeric suffix loop, never clobbered) — **verifies** the write by reading it back, mirrors the pre-image under `upgrade-backups/`, and only then adopts the shipped body in place (the `DISPOSITIONS.md` row is appended only after the adoption write succeeds). Under `report` / `report+issue` (or the key absent) the writer is conservative: the customization-bearing file is preserved in place + a `.new` sidecar is written — no transfer, no adoption. A failed transfer write, a failed pre-image backup, a failed adoption write, or a degraded not-analyzed stand-in verdict (`structural_compare` unavailable at call time — no evidence to act on) likewise falls back to that conservative branch: installed file untouched, `.new` sidecar under `{planwise_root}/upgrade-conflicts/<from>-to-<to>/` for manual merge. Every auto-adoption — stale-subset or transfer-then-adopt — first mirrors the pre-change file under `{planwise_root}/upgrade-backups/<from>-to-<to>/` (failed backup = no destructive write) and deletes any sidecar it obsoletes from an earlier interrupted run
6. Runs `migrate_installed_rules()` (version-gated on `RESCOPE_MIGRATION_VERSION`) to retire rules that are now handler-loaded from `references/`: it **removes** an installed `.claude/rules/**` copy when it is untouched (normalized-identical body, `paths:` match) **or** when its body is a high-confidence **stale subset** of the grown shipped reference with no installed-only content flagged; it **preserves** byte-for-byte any HAS_UNIQUE (customised) copy, any subset verdict with reorg confidence or a non-empty installed-only-content flag, and — while `upgrade.descope_preserve_paths_edits` is `true` (the default) — any copy with a customised `paths:` line, even over a stale body. Setting that key to `false` opts in to removing paths-edited copies (reported with an `[INFO]` marker). Every removal is backed up under `upgrade-backups/` first, so a disposition is always recoverable without VCS
7. Runs `lint_rule_overscope()` and appends a post-upgrade advisory listing any `.claude/rules/**` still scoped to plan/backlog/lessons paths, with size
8. Bumps `plugin_version:` AND repoints `plugin_root:` together, in `config.yaml`, LAST, as the commit point — one write, so the pair can never disagree (see `_commit_upgrade_pin()` in `scripts/init_project.py`)

Capture stdout — the banner is rendered from it.

---

### Step 2.5 — Refresh Token Saver calibration

Run only when `{token_saver}` (from Step 1.5) resolves to `yes` — i.e., Token Saver is enabled after the upgrade (either pre-existing or just turned on). Skip silently when Token Saver is off.

The measured overheads in `config.yaml` go **stale on upgrade**: a plugin update changes the always-on rule/agent surface a fresh `/context` loads, so `token_saver_runner_overhead` captured against the old version no longer reflects this install. Re-capture so plans size against the new footprint.

**Derivation change.** `calibrate()`'s overhead formula now filters through plugin attribution instead of measuring the whole installation's ambient footprint, and two new keys are recorded — a session-start `{min, median, max}` range and a separate injected-rule-content estimate. Stored values shift accordingly on this recalibration; if budgets were tuned around pre-upgrade numbers, review them again after this step runs.

> **Best-effort capture.** The `/context` report renders reliably only inside an **interactive** Claude Code session. When `token_saver.calibrate()` is invoked from upgrade (headless), the CLI may return conversational text instead of the structured report, and calibration degrades to the conservative fallback (runner ~54K / orchestrator ~60K). This is expected on some platforms — notably Windows. The conservative fallback is safe; recapture from an interactive session with `/planwise token-saver on`.

1. Re-run the calibration capture against the upgraded install:

   ```bash
   python -c "import sys; sys.path.insert(0, r'{plugin_root}/scripts'); import token_saver; from pathlib import Path; r = token_saver.calibrate(config_path=Path(r'{planwise_root}/config.yaml'), plugin_root=r'{plugin_root}'); print(r)"
   ```

   `token_saver.calibrate()` overwrites its six written `token_saver_*` keys in place — `runner_overhead`, `orchestrator_overhead`, `context_breakdown`, `overhead_measured_on`, `session_start_range`, `injected_rules_estimate` (targeted edit — comments and key order preserved) — and degrades to the conservative fallback if the `/context` capture fails or returns non-report text.

2. Report the refreshed numbers in the chat summary (append to the Step 3 banner):

   ```
   Token Saver recalibrated:
     Runner overhead:       {old} → {token_saver_runner_overhead}
     Orchestrator overhead: {old} → {token_saver_orchestrator_overhead}
     Session-start range:   {token_saver_session_start_range}
     Injected rules est.:   {token_saver_injected_rules_estimate}
     Calibrated on:         {token_saver_overhead_measured_on}
   ```

   If the result's `uncalibrated` flag is `true`, note that the conservative fallback was written (capture failed or returned non-report text — expected on some platforms) and suggest running `/planwise token-saver on` from an interactive session to capture real numbers.

---

### Step 2.6 — Lessons scaffolding backfill (PyYAML-missing fallback)

`_run_upgrade()` performs the lessons-scaffolding backfill itself (numbered item 2 in [Step 2.4](#step-24--invoke-the-upgrade-script)) whenever PyYAML is available — the normal case, since `--upgrade` hard-requires PyYAML and otherwise exits with `Upgrade failed: PyYAML is required for --upgrade`. Run this handler-side fallback **only** when the upgrade script aborted for that reason, so the categorization gate that protects `/planwise lessons curate` and `promote-batch` is still unblocked. Mirrors [init-fallback.md](init-fallback.md) Step 5 / [init.md](init.md) Step 5.1 — the same render, reached from the upgrade path.

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
  ({M} were stale subsets, auto-adopted shipped)   ({sub-line omitted when M == 0; pre-change copies live under {planwise_root}/upgrade-backups/<from>-to-<to>/})
  + {file}
  …
Unchanged: {N} (installed body already matches shipped)
Untracked preserved: {N}
  = {file}
  …

Customizations transferred before adoption: {N}   ({section omitted when 0; each entry is also counted under Refreshed above})
  ~ {file}
      moved to: {transfer path under {planwise_root}/upgrade-transfers/<from>-to-<to>/}
  …
  Review each transferred file and re-home it (project-local rule, re-scope, or upstream the change).

Conflicts (preserved in place — action required): {N}   (conservative handoff mode, a transfer/backup/adoption write failed, or the file could not be analyzed — never adopted without evidence, a verified transfer, and a pre-image backup)
  ! {file}
      reason:      installed body diverged and was not auto-adopted (conservative handoff mode, a transfer/backup/adoption write failed, or the file could not be analyzed)
      sidecar:     {sidecar path}
      remediation: diff the sidecar against the installed file, merge manually, then delete the .new
  See {planwise_root}/upgrade-conflicts/<from>-to-<to>/INDEX.md for the full conflict list.

De-scoped rules removed: {N} (now handler-loaded; untouched, a high-confidence stale subset, or — under `customization_handoff: report+relocate`, and only when `paths:` also matches the resolved default or the preserve opt-out is disabled — a genuine customization already transferred to `upgrade-transfers/` first; pre-change copy under upgrade-backups/)
  - {file}
  …
De-scoped rules preserved (action required): {N} (headless-inconclusive, paths: customised with the preserve opt-out enabled, the file could not be analyzed, or — under conservative handoff modes, or a failed transfer/backup — a genuine customization not yet moved)
  ! {file}
      reason: reorg-inconclusive, paths: customised with the preserve opt-out enabled, could not be analyzed (structural comparison unavailable — no evidence to act on), customised but `customization_handoff` is `report`/`report+issue` (or absent), or a transfer/backup write failed
      action: re-home as a project-local rule, OR re-scope paths: to the code dirs it governs, OR upstream the change

Recovery artifacts:
  {path} ({N} file(s)) — {class}: {class description}
  …   ("  None found." when no surface has any content — report-what-exists, never assumes all four surfaces exist)

Over-scope advisory: {N} rule(s) still scoped to plan/backlog paths (~{X}K injected per task-runner)
  run `/planwise doctor` for the full report

Plugin version pinned: {to}
Plugin root repointed: {live_plugin_root}

Upgrade complete.
```

> [!practice] Recovery-artifact disposition classes
> `action-required` — unresolved conflict sidecars. `review-then-discard` — transferred customizations awaiting re-homing. `safe-to-discard` — pre-change backups, once you are satisfied with the upgrade. `inert` — a consumed verdict cache. Step 4.3 offers per-class cleanup for `safe-to-discard` and `inert` only; `action-required` and `review-then-discard` are reported here but resolved through Step 4 / Step 4.1 / Step 4.2.

> [!practice] Interactive elaboration — home hints (when `verdicts.json` exists)
> Raw stdout has no `home_hints` access (handler-side cache only). When `verdicts.json` exists, append to the
> **chat summary** one line per "transferred"/"preserved" file that has a hint: `! {file} ({K} unique block(s)
> — suggested home: {localize|upstream|either})`, then point at Step 4.1 (already transferred → promote to an
> active rule; still preserved → retry the relocation by hand) or Step 4.2 (upstream). No `verdicts.json`
> (headless, or fan-out declined) → no hints to append; the writer still auto-transferred regardless.

Then summarise in the chat with this template:

```
Plugin upgrade: {from} -> {to}

Config keys added:       {N}        ({list, or "(none)"})
Lessons backfilled:      {N}        (categorization file / index seed — gates lessons curate; "(none)" when both present)
Artifacts refreshed:     {N}
Artifacts unchanged:     {N}        (installed body already matched shipped)
Untracked preserved:     {N}        ({list of files outside the manifest allowlist})
Customizations transferred: {N}     (moved to {planwise_root}/upgrade-transfers/ before shipped was adopted — see Step 4.1)
Conflicts:               {N}        (preserved in place — conservative handoff mode, transfer/backup/adoption failed, or not analyzed; see Step 4 if > 0)
De-scoped removed:       {N}        (now handler-loaded; untouched, or customised and transferred first under `report+relocate`)
De-scoped preserved:     {N}        (conservative handoff mode, reorg-inconclusive, or a failed transfer/backup — action required, re-home not delete)
Over-scope advisory:     {N}        (rules still plan/backlog-scoped — run `/planwise doctor`)

Plugin version pinned:   {to}
Plugin root repointed:   {live_plugin_root}
Recovery artifacts:      {N} dir(s) across {M} version pair(s) — run /planwise doctor for disposition

Upgrade complete.
```

If customizations-transferred > 0, list each transferred file and its target path, and point the user at Step 4.1 to promote it into an active rule or Step 4.2 to propose upstreaming it — the file is already safe (moved before the shipped body was adopted); this is a "when convenient" follow-up, not a blocker. If conflicts > 0, append the conflict list verbatim from the script's stdout and direct the user to Step 4 (or Step 4.1 if they want to complete a relocation the automated transfer couldn't). If de-scoped-preserved > 0, surface the re-home notice for each (the action choices: project-local rule / re-scope `paths:` / upstream). If the over-scope advisory is > 0, point the user at `/planwise doctor`.

---

### Step 4 — Resolve conflicts

> [!practice] Resolve, Don't Sidestep
> Prefer fully resolving a divergence through the documented flow (relocation, adoption, or upstream issue) over leaving a sidecar note for later — a deferred resolution must name the constraint that forced deferral. See [do-the-hard-things.md](../references/do-the-hard-things.md).

For each conflict in `{planwise_root}/upgrade-conflicts/<from>-to-<to>/` (files preserved in place: conservative handoff mode — `upgrade.customization_handoff` is `report`/`report+issue` — or a transfer/backup/adoption write failed, or the verdict was the degraded not-analyzed stand-in — see Step 2.4, item 5):

1. The user diffs `<destination>.md` against `<destination>.md.new`
2. If the changes are acceptable → overwrite the installed file with the sidecar content (or merge selectively) → delete the `.new` file
3. If the user wants to keep their local edits → run the Step 4.1 case B relocation (the customization was never moved for this file) instead of merging in place

The `upgrade-conflicts/` directory and its `INDEX.md` can be cleaned up once all sidecars are resolved. See Step 4.3 for the aggregated view of this and every other recovery-artifact surface — the consumed verdict cache in this same directory is offered for cleanup there (`inert`), but the sidecars and any `issue-drafts/` stay `action-required` and must be resolved above first.

---

### Step 4.1 — Assisted relocation

Under `upgrade.customization_handoff: report+relocate`, the Step 2.4 writer already performs an automated transfer for the customization-bearing majority: it writes the full installed body to `{planwise_root}/upgrade-transfers/{from}-to-{to}/{filename}` as a **dormant preservation document** (outside `.claude/rules/` — never loaded as a rule; see the file's own provenance header) before adopting the shipped body. Two cases land here, both interactive-only:

**A. File is listed under "Customizations transferred before adoption"** — the transfer already succeeded; offer to promote the dormant transfer file into an active, `paths:`-scoped project rule:

1. `AskUserQuestion` (`<!-- AUTO-MODE: critical -->` — destructive/structural; never inferred): "Promote the transferred customization for `{filename}` into an active project rule at `.claude/rules/{project_name}/{filename}`?" If declined → leave it as the dormant preservation doc under `upgrade-transfers/` (already safely on disk; nothing else to do).
2. On confirm, `AskUserQuestion` for the code-path glob the new rule should scope to (`paths:`). **Default when the user skips:** write `paths: # TODO scope` plus an advisory comment (`# TODO: scope this rule to the code dirs it governs — do NOT use plan/backlog/lessons globs`).
3. **Copy, strip, scope.** Read the transfer file and extract ONLY the original transferred body: drop everything above it — the provenance frontmatter block (`source_filename:` … `classification:`), the `# Transferred customization: {filename}` heading, the "review and re-home" boilerplate paragraph, and the `---` separator line that precedes the body. What remains must be exactly the original installed file content (which may open with its own `---` frontmatter — that one STAYS; it is the rule's real frontmatter, not the wrapper's).
4. Apply `update_frontmatter(content, paths_value)` to the stripped body so the promoted file carries a real `paths:` line, and **Write** the result to `.claude/rules/{project_name}/{filename}`. The promoted file must be a clean, valid, `paths:`-scoped rule — no provenance keys, no wrapper heading, no doubled frontmatter fences. (If the transferred body is an **agent** file, its frontmatter is agent-shaped — tell the user and let them adapt it into rule form or keep it dormant instead; do not blind-promote.)
5. The transfer file itself stays in place as the preservation record; tell the user it can be deleted once they are satisfied with the promoted rule. Step 4.3 lists this surface (`review-then-discard`) alongside every other recovery-artifact class for visibility, but never offers it for deletion there — a genuine customization needs this human read before it is discarded, so the delete stays a manual step here.

**B. File is listed under "Conflicts (preserved in place — action required)"** — the customization was never moved; secure it FIRST, then resolve the conflict through the existing sidecar mechanism. The installed location is **kind-aware**: rules live at `.claude/rules/planwise/{filename}`, agents at `.claude/agents/{filename}` — never assume the rules path for an agent.

1. `AskUserQuestion` (`<!-- AUTO-MODE: critical -->`): "Relocate the customization in `{filename}` to a project-owned copy at `.claude/rules/{project_name}/{filename}`?" If declined → leave preserved-in-place (diff/merge the `.new` sidecar per Step 4 instead).
2. On confirm, `AskUserQuestion` for the `paths:` glob (same default as case A when skipped).
3. **Secure the customization:** Read the preserved installed body (from its kind-aware installed path) and Write it to `.claude/rules/{project_name}/{filename}` via `update_frontmatter(content, paths_value)`. Read the new copy back and confirm it contains the customization before touching anything else — this copy is the pre-image that makes the next step safe. (For an agent body, same caveat as case A step 4.)
4. **Adopt shipped via the sidecar** — the already-documented Step 4 resolution action, not a new write surface: move the `.new` sidecar content over the installed file at its kind-aware path (overwrite installed with sidecar, then delete the `.new`). Do this **only after** step 3's copy is verified — nothing is ever overwritten without a confirmed surviving copy (the relocated project-owned file; the writer's `upgrade-backups/` pre-image, when one was made, is a second recovery path). Never simply delete the installed file: the shipped body must land in the freed slot, or the install is left missing a managed artifact.

The handler's write surface in both cases stays within its documented boundary — `verdicts.json`, `.claude/rules/{project_name}/**` promotion copies, issue-draft files, and the Step 4 sidecar-over-installed conflict resolution. The `--upgrade` script remains the only automated mutator of the managed tree; everything here is an explicit, per-file, user-confirmed interactive action.

---

### Step 4.2 — Opt-in upstream GitHub issue

For any customization — whether already transferred to `{planwise_root}/upgrade-transfers/{from}-to-{to}/` (Step 2.4) or still preserved in place under a Step 4 conflict — that the human confirms `upstream`, submit the issue **through the shared submission engine**: `references/feedback-submission.md` owns the invocation — its gate chain, draft-first render, explicit `-R` target repo, and fallback posture. Do NOT write a `gh` call here: a locally improvised invocation resolves its target from the consumer's own git remote and files planwise issues in the consumer's own project. Gated by **ALL** of:

- `upgrade.github_issue: true` (config key — read via `get_upgrade_config()`) — an **additional** precondition owned by this step, layered on top of the engine's own gates and never a substitute for them, **AND**
- interactive confirm (`AskUserQuestion`, `<!-- AUTO-MODE: critical -->`), **AND**
- the engine's own gate chain (`references/feedback-submission.md`), whose gate 3 is the `gh`-on-PATH check this step used to restate.

If **any** gate fails (flag off, declined, non-interactive, or `gh` absent) → write an issue-body **draft file** to `upgrade-conflicts/{from}-to-{to}/issue-drafts/{filename}.md` instead of calling out. Never automatic; never blocks the upgrade.

Issue body (project-agnostic template):

```markdown
## Diverged artifact
- File: `{filename}`  ({kind})
- Verdict: HAS_UNIQUE  (confidence: {confidence}, source: {inline|agent})
- Installed-only content: {installed_only_chars} chars across {N} unique block(s)

## Unique blocks (installed-only)
{for each label in unique_blocks: - {label}}

## Sample tokens
{unique_sample_tokens}

## Suggested disposition
Preserved in place during a `1.0.x` → `1.0.y` planwise upgrade; home hint =
`upstream` (a generic improvement, not project-specific). Consider folding it
into the shipped artifact so future consumers benefit.
```

---

### Step 4.3 — Interactive per-class cleanup offer

Runs after the Step 3 banner has reported which `Recovery artifacts:` surfaces currently exist. For **each surface class that exists** — one confirm per disposition class, never one per file, since a per-file prompt loop is exactly the UX this aggregation exists to replace:

| Class | Surface(s) | Offered for deletion here? |
|---|---|---|
| `action-required` | `{planwise_root}/upgrade-conflicts/*/` (unresolved `.new` sidecars); `{planwise_root}/upgrade-conflicts/*/issue-drafts/` | Never — resolve the sidecars via Step 4, the issue drafts via Step 4.2 |
| `review-then-discard` | `{planwise_root}/upgrade-transfers/*/` | Never — a genuine customization needs a human read before it is discarded; promote or delete by hand via Step 4.1 case A |
| `safe-to-discard` | `{planwise_root}/upgrade-backups/*/` | Yes |
| `inert` | `{planwise_root}/upgrade-conflicts/*/verdicts.json.consumed` | Yes |

For each of the two deletable classes that has at least one match:

1. `AskUserQuestion` (`<!-- AUTO-MODE: convenience -->` — a plain confirm-to-delete, not structural; inferred default is **skip**, so an unattended/non-interactive run never deletes a recovery artifact): "Delete the {N} `{class}` recovery artifact(s) at `{path}`?" — state the class's plain-language reason inline (`safe-to-discard`: "pre-change backups, once you are satisfied with the upgrade"; `inert`: "a consumed verdict cache").
2. On confirm → delete the matched files and print each removed path as it goes. On decline, or when no interactive answer is available → skip that class; nothing under it is touched.

`action-required` and `review-then-discard` are listed alongside the two deletable classes so the offer gives a complete picture, but deletion never covers them — see the table above for where each is actually resolved. The default across every class, every run, is **skip-all**: deletion is opt-in and per-class, never assumed.

---

## Conflict Resolution Reference

> [!practice] Why transfer-then-adopt, and not silent overwrite
> Rules in `.claude/rules/planwise/` are user-installable artifacts. A user may have hand-edited a rule to extend its `paths:` glob, refine its prose, or add a project-specific subsection. `/planwise upgrade` MUST NOT silently destroy that work. For the stale-subset majority (reflowed / reordered / reworded, no genuine customization), auto-adopting shipped is safe — there is nothing to lose. For the customization-bearing minority, the writer (under `customization_handoff: report+relocate`) moves the customization to a dormant preservation file under `{planwise_root}/upgrade-transfers/`, verifies the write, backs up the pre-image, and only then adopts shipped — a `.new` sidecar is reserved for the conservative handoff modes and the residual cases where a transfer, backup, or adoption write could not be safely completed.

| Scenario | What the script does | What the user does |
|---|---|---|
| Installed body matches shipped (normalised) | Skips rewrite (no-op) | Nothing — file is current |
| Installed body matches shipped, but `paths:` differs | Skips rewrite | Nothing — `paths:` is per-project |
| Installed body diverged → **SUBSET**, no tolerated notes (stale / reflowed / reordered) | **Auto-adopts shipped in place** (refresh; pre-image under `upgrade-backups/` first — failed backup = no overwrite); NO `.new` sidecar; counted under Refreshed "(was stale subset)". | Nothing — customization-free divergence resolved automatically |
| Installed body diverged → **HAS_UNIQUE** or a SUBSET whose `notes` flag tolerated installed-only content — and `customization_handoff: report+relocate` | **Transfers** the installed body to `{planwise_root}/upgrade-transfers/{from}-to-{to}/{filename}` (verified write; collisions uniquified, never clobbered), backs up the pre-image, **then adopts** shipped in place; NO `.new` sidecar on success | Review the transferred file and re-home it (Step 4.1 promote to an active rule, or Step 4.2 upstream) |
| Same customization-bearing verdicts, but `customization_handoff` is `report` / `report+issue` (or absent) | Preserves byte-for-byte + `.new` sidecar + `INDEX.md` entry — conservative mode: no transfer, no adoption | Diff the sidecar, merge manually, delete `.new` (Step 4) — or relocate by hand (Step 4.1, case B) |
| Customization transfer write failed, pre-image backup failed, adoption write failed, or the verdict is the degraded not-analyzed stand-in | Preserves byte-for-byte + `.new` sidecar + `INDEX.md` entry (never adopts without evidence, a verified transfer, AND a pre-image backup; a post-transfer adoption failure logs no false DISPOSITIONS row) | Diff the sidecar, merge manually, delete `.new` (Step 4) — or retry the relocation by hand (Step 4.1, case B) |
| Diverged file with a comparator verdict in `verdicts.json` | Writer uses the comparator's **semantic** verdict (supersedes the inline primitive); disposition shape unchanged | Nothing — fidelity raised on the minority |
| Installed file absent | Writes shipped body fresh | Nothing — file just appeared |
| File present, not in manifest allowlist | Reports as Untracked | Nothing — file is the user's own |
| De-scoped rule, installed body **and** `paths:` untouched (or a high-confidence stale subset, no tolerated notes) — AND, when `paths:` also diverges from the resolved default, `upgrade.descope_preserve_paths_edits` is `false` (opt-out disabled) | Removes the redundant installed copy (rule is now handler-loaded from `references/`; pre-image under `upgrade-backups/` first) | Nothing — the rule still applies, loaded on demand |
| De-scoped rule, body diverged with a genuine customization (HAS_UNIQUE, or a SUBSET whose `notes` flag tolerated installed-only content), `paths:` matches the resolved default (or the preserve opt-out is disabled) — and `customization_handoff: report+relocate` | **Transfers** the installed body to `{planwise_root}/upgrade-transfers/{from}-to-{to}/{filename}` (verified write), backs up the pre-image, **then removes** the installed copy | Review the transferred file and re-home it (Step 4.1 promote to an active rule, or Step 4.2 upstream) |
| Same customization-bearing verdicts, but `customization_handoff` is `report` / `report+issue` (or absent); or the transfer/backup write failed; or `paths:` is customised — alone, or combined with a customized body — with the preserve opt-out enabled; or the SUBSET is reorg-inconclusive | Preserves byte-for-byte + emits an action-required re-home notice (never auto-deletes without a verified transfer, and a paths-customised copy is never given weaker protection than a body-only customization) | Re-home: keep as a project-local rule, re-scope `paths:` to the code dirs it governs, or upstream the change |

---

## Auto-Init Fallback

If the config gate fails (no `config.yaml` found), the project hasn't been initialised. `--upgrade` will exit non-zero in that case. Surface this clearly:

```
This project doesn't have a planwise config yet. Run `/planwise init` first.
```

Offer to run `/planwise init` via `AskUserQuestion` and, on confirmation, dispatch to `init.md`'s Step 1. Once init completes, the upgrade is unnecessary (the freshly-generated config pins the current plugin version).

---

*Cross-reference: [init.md](init.md), [agents/rule-comparator.md](../agents/rule-comparator.md), [migrate logic in scripts/init_project.py](../scripts/init_project.py).*
