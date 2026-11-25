# Handler: /planwise upgrade — Part 4: Post-Run Reports and Backfills

**Part 4 of [upgrade.md](upgrade.md).** Part 1 carries the Config Gate and Steps 1-2.4 of the Workflow, and is the file `/planwise upgrade` dispatches to. This part carries Step 2.5 (Refresh Token Saver calibration) through Step 2.8 (Feedback keys backfill and banner), the reports and backfills that follow the Step 2.4 script run. Read it after Step 2.4. It also holds Step 4.8 (Subagent cache lifetime offer), which runs after Part 3. [`upgrade-Part-3-BannerAndConflictResolution.md`](upgrade-Part-3-BannerAndConflictResolution.md) (Part 3) carries Step 3 and Step 4, and [`upgrade-Part-2-RecoveryAndReference.md`](upgrade-Part-2-RecoveryAndReference.md) (Part 2) carries the scenario table and the recovery procedures. Split at this section boundary so each part stays within one Read-tool page.

## Table of Contents

- [Step 2.5 — Refresh Token Saver calibration](#step-25--refresh-token-saver-calibration)
- [Step 2.6 — Lessons scaffolding backfill (PyYAML-missing fallback)](#step-26--lessons-scaffolding-backfill-pyyaml-missing-fallback)
- [Step 2.7 — Working folders: move, backfill and creation](#step-27--working-folders-move-backfill-and-creation)
- [Step 2.8 — Feedback keys backfill and banner](#step-28--feedback-keys-backfill-and-banner)
- [Step 4.8 — Subagent cache lifetime offer](#step-48--subagent-cache-lifetime-offer)

---

### Step 2.5 — Refresh Token Saver calibration

Applies only when `{token_saver}` (from Step 1.5) resolves to `yes` — i.e., Token Saver is enabled after the upgrade (either pre-existing or just turned on). Skip silently when Token Saver is off.

The Step 2.4 writer runs the calibration itself in that case. Read its calibration line from the Step 2.4 output and report it in the banner. Run no `python -c` calibration call.

The measured overheads in `config.yaml` go **stale on upgrade**: a plugin update changes the always-on rule/agent surface a fresh `/context` loads, so `token_saver_runner_overhead` captured against the old version no longer reflects this install. The writer re-captures so plans size against the new footprint.

**Derivation change.** Stored values shift on this recalibration, so review any budget tuned around pre-upgrade numbers after this step runs. The formula and the role of each key are in [token-saver-profile.md](../references/token-saver-profile.md) under "Which keys feed the session budget".

> **Best-effort capture.** The `/context` report renders reliably only inside an **interactive** Claude Code session. The Step 2.4 writer now calls `token_saver.calibrate()` itself, headless, so the CLI may return conversational text instead of the structured report. A never-measured project then degrades to the conservative fallback (runner ~54K / orchestrator ~60K), and a measured project keeps its measured overheads. This is expected on some platforms — notably Windows. The conservative fallback is safe; recapture from an interactive session with `/planwise token-saver on`.

1. Read the writer's calibration line from the Step 2.4 output. It prints exactly one of these four lines:

   ```
   Token Saver recalibrated: runner overhead {old} -> {new}, orchestrator overhead {old} -> {new}
   Token Saver calibration fell back to defaults; run /planwise token-saver on to retry.
   Token Saver calibration failed; kept the measured overheads.
   Token Saver calibration skipped: {error}
   ```

   The writer's call to `token_saver.calibrate()` overwrites its six written `token_saver_*` keys in place on a successful capture — `runner_overhead`, `orchestrator_overhead`, `context_breakdown`, `overhead_measured_on`, `session_start_range`, `injected_rules_estimate` (targeted edit — comments and key order preserved). It degrades as the callout above describes when the `/context` capture fails or returns non-report text.

2. Report the refreshed numbers in the chat summary (append to the Step 3 banner in [upgrade-Part-3-BannerAndConflictResolution.md](upgrade-Part-3-BannerAndConflictResolution.md)). On the `Token Saver recalibrated:` line, render the two values it prints:

   ```
   Token Saver recalibrated:
     Runner overhead:       {old} → {token_saver_runner_overhead}
     Orchestrator overhead: {old} → {token_saver_orchestrator_overhead}
   ```

   On any of the other three lines, report the line verbatim. On the fell-back-to-defaults line, note that the conservative fallback was written (capture failed or returned non-report text — expected on some platforms) and suggest running `/planwise token-saver on` from an interactive session to capture real numbers.

---

### Step 2.6 — Lessons scaffolding backfill (PyYAML-missing fallback)

`_run_upgrade()` performs the lessons-scaffolding backfill itself (numbered item 2 in [Step 2.4](upgrade.md#step-24--invoke-the-upgrade-script)) whenever PyYAML is available — the normal case, since `--upgrade` hard-requires PyYAML and otherwise exits with `Upgrade failed: PyYAML is required for --upgrade`. Run this handler-side fallback **only** when the upgrade script aborted for that reason, so the categorization gate that protects `/planwise lessons curate` and `promote-batch` is still unblocked. Mirrors [init-fallback.md](init-fallback.md) Step 5 / [init.md](init.md) Step 5.1 — the same render, reached from the upgrade path.

<!-- AUTO-MODE: critical -->
0. **Offer the install first.** When the script aborted with the `PyYAML is required for --upgrade` line, use `AskUserQuestion` once: "PyYAML is not importable by {python_executable}. Run `{install_command}` now and repeat the upgrade?" Take `{install_command}` from the command the abort line names. On yes, run that command, then repeat [Step 2.4](upgrade.md#step-24--invoke-the-upgrade-script) with the same arguments and skip the rest of this step. On no, run the fallback below. An install changes the environment, so this question is `critical`: never answer it by inference in Auto Mode (see [auto-mode-policy.md](../references/auto-mode-policy.md)).
1. Use **Glob** to check whether `{planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md` already exists — **skip this step if it does** (idempotent; never overwrite a populated file).
2. **Read** [../templates/categorization-by-domain.md](../templates/categorization-by-domain.md) as a worked example of the target shape — it is the generator's own zero-lesson output for the ship-default config, not a fill-in-the-blanks template. Match its shape rather than substituting into it: `# Lessons Learned — Categorization by Domain`, a `Generated: <today's date>` line, a `**Companion to:** [{lessons_index}]({lessons_index})` line, then `## Scope`, its scope paragraph and the status paragraph, then one `## {id}. {name} (0)` section per bucket in `decision_tree_order` (with `### {sub_id}. {sub_name} (0)` per sub-bucket) each carrying an empty 3- or 4-column table (per the bucket's `code_bucket:` flag), then a closing `---` and the `[Notes](00-Categorization-Notes-LessonsLearned.md)` / `[Changelog](...)` footer pointers. See [init.md](init.md) Step 5.1 for the full field-by-field rendering steps — this fallback is the same render, reached from the upgrade path. Do NOT render a `## Cross-cutting observations` or `## Classification edge cases` section — those now live in `00-Categorization-Notes-LessonsLearned.md`, never in the companion.
3. Populate it from the user's `config.yaml: categorization:` block, one section per bucket in `decision_tree_order`.
   > [!practice] Missing `categorization:` Block — Render From Defaults
   > When the block is absent or empty, use the 4-bucket default from [../config.yaml.template](../config.yaml.template) (database / code / process / tooling) and add a banner line noting defaults were used. Suggest `python init_project.py --migrate` to seed the block into `config.yaml` for full customisation.
4. For each of the lessons index hub and its two companions — `00-Index-LessonsLearned.md`, `00-Changelog-LessonsLearned.md`, `00-PromotionLog-LessonsLearned.md` — if `{planwise_root}/{lessons_dir}/{name}` is missing, also copy it from `../seed/{name}`.
5. Use **Write** to create the categorization file with the rendered result, and surface it under the banner's `Lessons scaffolding backfilled:` heading.

---

### Step 2.7 — Working folders: move, backfill and creation

Step 2.4's script invocation runs this step. The script functions are `_apply_layout_migration()` and `_apply_feedback_dir()` in `artifact_upgrade.py`. They are not a separate handler-side procedure. This step closes a distinct half of the directory-creation contract. See [init.md](init.md) Step 10 and [doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md](doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md) Stage 17 for the other two entry points.

On every `--upgrade` run that reaches an existing `config.yaml`, the script runs this step. That includes the already-up-to-date early return. The script reads the folders on disk and never the version pin. It therefore works from any starting version, and a re-run at a current pin finishes any move an earlier run left open.

The current layout keeps two working folders one level down:

| Older location | Current location |
|---|---|
| `{planwise_root}/plan-build/` | `{planwise_root}/{plans_dir}/Plan-Build/` |
| `{planwise_root}/feedback-drafts/` and the loose files in `{planwise_root}/Feedback/` | `{planwise_root}/Feedback/Feedback-Drafts/` |

The script then does these things, in order:

1. Creates `Plan-Build/` when no `plan-build/` exists. When `plan-build/` exists, it moves the folder and its files. When both exist, it moves file by file.
2. Moves the drafts into `Feedback/Feedback-Drafts/`. This applies when `project.feedback_dir` is absent, `feedback-drafts` or `Feedback`. It then rewrites a present key to `Feedback/Feedback-Drafts`.
3. Keeps a custom `project.feedback_dir` and moves nothing for it. The output says `custom project.feedback_dir kept`.
4. Backfills `project.feedback_dir` as `Feedback/Feedback-Drafts` when the key is absent.
5. Creates the resolved drafts directory if it does not already exist. `project` is not one of the top-level keys the config merge touches, so nothing else in Step 2.4 would create it.

The move never overwrites and never deletes a file. A name clash, a locked file or a failed move leaves that file where it was. The output lists it as `left in place`. The upgrade still finishes with exit code 0. The step is non-interactive and asks nothing, so Auto Mode needs no inference for it.

`feedback-intake/` is not part of this move.

Pass the script's output through verbatim. The lines are `Plan-Build directory: {created | moved | merged | already present} ({path})`, `Feedback drafts: {moved | merged | already present | kept} ({path})` when drafts moved or a note applies, and `Feedback directory: {created | already present} ({path})`. Each may carry `moved N file(s)` and `left in place` lines under it.

---

### Step 2.8 — Feedback keys backfill and banner

Implemented inside Step 2.4's script invocation, not as a separate handler-side procedure. It runs on both exits, including the already-up-to-date return. The backfill rule:

- **`feedback.drafts` already set:** write nothing, except one `feedback.{key}: {old} -> {new}` line per flagged key that changed. No banner.
- **Key absent:** write the flagged value, or `notify` when `--feedback-drafts` was not passed.
- **No `feedback:` block at a current pin:** write nothing, because the config merge in Step 2.4 adds the block whole.
- **A flag always writes its value.** `--feedback-enabled` writes `feedback.enabled: true`, and `--no-feedback-enabled` writes `feedback.enabled: false`. With neither flag, the key stays as it is.

The banner prints once, when the key was absent or the block missing before the run, because the key exists after it. Pass the `Feedback drafting:` entry through verbatim.

---

### Step 4.8 — Subagent cache lifetime offer

Run this step last, after Part 3 Step 4.7. Claude Code gives a subagent's prompt cache a five-minute lifetime, even on a subscription. planwise runs many subagents. One that waits more than five minutes between its own turns, for example on a test suite, pays to write its whole prompt again. The top-level settings key `subagentPromptCacheTtl: "1h"` keeps that cache for an hour. It needs Claude Code 2.1.242 or later.

Read the project's `.claude/settings.json`, its `.claude/settings.local.json` and the user `settings.json`. If any of them holds `subagentPromptCacheTtl`, or `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` in its `env` block, report "Subagent cache lifetime: already chosen." and skip the offer, whatever the value. Otherwise report that the key is absent. The write target is the settings file of the install scope: `.claude/settings.json` for `project`, `.claude/settings.local.json` for `local`, the user `settings.json` for `user`. When that file does not parse, report it and change nothing.

The **report always renders**. The **write happens only on approval**: `AskUserQuestion` (`<!-- AUTO-MODE: convenience -->`) — "Keep subagent prompt caches for 1 hour instead of 5 minutes, by adding `subagentPromptCacheTtl: "1h"` to {settings_path}? It applies to every subagent under that file, not only planwise's. A 1-hour cache write costs more than a 5-minute one, so it pays off when subagents pause for more than five minutes. Yes (Recommended) / No". List Yes first. The inferred default is the "Subagent cache lifetime question" row of `references/auto-mode-policy.md` § Inference Defaults. On Yes, add the key, preserve every other key, and read the file back. On No, change nothing. The next version upgrade asks again.

---

*Cross-reference: [upgrade.md](upgrade.md) (Part 1 — Config Gate and Steps 1-2.4), [upgrade-Part-3-BannerAndConflictResolution.md](upgrade-Part-3-BannerAndConflictResolution.md) (Part 3 — Steps 3-4.7), [upgrade-Part-2-RecoveryAndReference.md](upgrade-Part-2-RecoveryAndReference.md) (Part 2 — Conflict Resolution Reference and Recovery), [init.md](init.md), [migrate logic in scripts/init_project.py](../scripts/init_project.py).*
