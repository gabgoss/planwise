# Handler: /planwise doctor — Part 3: Token Saver and Bookkeeping Read Gates

**Part 3 of 3.** This handler spans three files, split by topic because the combined text exceeds the Read-tool page cap. Each Step keeps its own identifier wherever it lands, so an existing `Step N` reference still names exactly one section — only the filename that holds it changes. See [`doctor.md`](doctor.md) for the full three-part pointer table, the Config Gate, the Preflight version-state gate, and Stages 8-13. [`doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md`](doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md) covers Stages 14-23.

This file covers **Steps 4-8**: the Token Saver overhead audit, the read-gate scan, the read-constant drift tripwire, the capture self-containment scan, and the bookkeeping index read-gate scan.

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

   Derive `available_per_task` and the ceiling per the threshold formulas in [`references/token-saver-profile.md`](../references/token-saver-profile.md) § Token Saver Threshold Derivation; never hardcode the ceiling.

2. **Flag staleness** when EITHER signal fires (the measured overheads no longer reflect this install's real `/context` footprint):

   | Staleness signal | How to detect |
   |------------------|---------------|
   | Plugin upgraded since calibration | Folded into the **Preflight version-state gate** in [`doctor.md`](doctor.md) — `doctor` stops on `pinned ≠ installed` before this audit runs, so reaching Step 4 guarantees pinned == installed. Do not re-compare versions here. (A version-bumping `/planwise upgrade` may shift the rule/agent surface; re-capture overheads with `/planwise token-saver on` after upgrading.) |
   | Agent/Skill count changed | The Custom Agents / Skills count in a fresh `/context` differs from the captured `token_saver_context_breakdown` (added/removed agents or skills shift the always-on surface) |
   | Overheads uncalibrated | `token_saver_runner_overhead` is `0`/empty, or equals a conservative fallback with no live capture recorded. The current fallback is `2400` for both keys. The pre-attribution pair (`54000` runner / `60000` orchestrator) also counts as a fallback. **Note:** on some platforms (notably Windows and any headless invocation), the calibration capture always degrades to the conservative fallback because the CLI returns conversational text instead of the structured `/context` report when called non-interactively. This is a platform/capture limitation, not a configuration error — the conservative fallback is safe (over-estimated). To capture real measured numbers, run `/planwise token-saver on` from an **interactive** Claude Code session. |

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

Run `token_saver.classify_file(path, model, projected_added_bytes, thresholds)` (from `scripts/token_saver.py`) across BOTH (a) the active plan's Required-Context files AND (b) the plan's own generated artifacts (task files, Orchestration, Recovery, Consolidated Context parts, Execution Inputs, task Output files). Use each file's **assigned-model** bytes-per-token ratio for the token estimate (`BYTES_PER_TOKEN`, per [`references/session-context-budget.md`](../references/session-context-budget.md) § Read-Tool Hard Limits). Report:

| Finding | Gate | Recommendation |
|---------|------|----------------|
| File ≥ 256 KiB (`READ_FILE_BYTE_CAP`) | byte gate (model-independent) | **read-Critical** → paged read (`offset`/`limit`/Grep); refactor + backlog if it is a core/edited dependency |
| File above the per-assigned-model 25K-token page cap (`READ_PAGE_CAP_TOKENS`) | token gate (model-dependent) | **read-Critical** → paged read; refactor if core/edited |
| File that WILL cross a gate once its task's edits land | token/byte gate (projected) | pass `projected_added_bytes` so the will-exceed case is flagged pre-emptively; same remedy as above |
| Task estimate ≥ `critical` (cost) | cost gate | **cost-Critical** → `1M-exception` (raise dispatch to Opus/1M) OR split the task |

> [!constraint] read-Critical → paged-read/refactor, NOT `1M-exception`
> Applies the read-vs-cost Critical distinction canonical in [`references/session-context-budget.md`](../references/session-context-budget.md) § Read-Tool Hard Limits (full WRONG/CORRECT box there — not restated here): a `read`-reason Critical is a mechanical Read failure, resolved by paging or refactor, never by routing to a larger window. Only a `cost`-reason Critical is `1M-exception`-eligible — see [`references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md §1.20`](../references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) 1M-Exception Dispatch.

A passing read-gate/cost-gate scan is a necessary signal, not a sufficient one — the general gate-discipline principle canonical in [`references/gate-runtime-boundary-evidence.md`](../references/gate-runtime-boundary-evidence.md) §1: clearing a mechanical check is not proof the plan is runtime-correct.

### Step 6: Read-constant drift tripwire

Report the FIXED Read-tool constants' measured baseline, then defer the actual staleness signal to the verified-CLI-version drift advisory's project-wide check rather than re-comparing a CLI build inline here — no shipped plugin file stores a literal CLI version to compare against (see the callout below for why).

1. Report the constants' provenance — the values themselves are the read-gate canonical in [`references/session-context-budget.md`](../references/session-context-budget.md) § Read-Tool Hard Limits; this step never restates them:

   ```
   Fixed Read-tool limits (read_limits.py) — see references/session-context-budget.md § Read-Tool Hard Limits for the current values
     Measured on: {READ_LIMITS_MEASURED_ON}
   ```

2. Point at the verified-CLI-version drift advisory's own verdict (`doctor_cli.py`'s "verified CLI version drift" report, run earlier in this same `/planwise doctor` pass) rather than re-probing `claude --version` here:

   ```
   ! Read-limit constants measured {READ_LIMITS_MEASURED_ON}. The verified-CLI-version drift advisory above reports
     {drift | uncalibrated | up to date} against context.verified_cli_version.
     On drift or uncalibrated: the hardcoded Read-tool caps may be stale. Re-probe with the
     read-limit re-validation procedure (headless `claude -p --model X` probes against
     synthetic files) and update the constants + READ_LIMITS_MEASURED_ON in scripts/read_limits.py.
     That is where both are DEFINED; scripts/token_saver.py only re-exports them, and editing
     the re-export changes no value.
   ```

   This is the drift tripwire for the hardcoded read constants. It is advisory — `doctor` never edits the constants; it surfaces the mismatch so the one-shot live re-probe can be run.

> [!binding] No shipped plugin file cites a specific CLI build
> `read_limits.py` used to carry its own `READ_LIMITS_MEASURED_CLI` constant naming the exact build its constants were validated against — a version pin baked into shipped plugin source, requiring an edit on every CLI point release just to stay accurate. A project-local drift-watch tool that scans for any non-latest version string anywhere in the repo turned that churn into a large batch of near-identical "citation is stale" backlog items on every release, most of them against citations that were never functional pins to begin with (a measurement-provenance comment, not a compatibility requirement). The constant was removed; the *build a project's harness was last confirmed against* is now consumer-side, mutable state in `config.yaml`'s `context.verified_cli_version` — populated by `/planwise init`, refreshed by `/planwise upgrade`, reported (never written) by `/planwise doctor`'s verified-CLI-version drift advisory. Never reintroduce a literal CLI version into a file under `cloned-repos/planwise/plugins/planwise/`.

The read-constant tripwire is paired with a cross-model ratio-band assertion in the plugin's test suite, which pins two properties of `BYTES_PER_TOKEN` for the same file. A drift in either signals a tokenizer-weight change:

| Property | Assertion |
|---|---|
| Cross-generation band | Opus token count is 1.25–1.45× Haiku (measured 1.31–1.38× across the three text classes and 1.28–1.40× across the notebook and json classes) |
| Intra-family equality | Opus, Sonnet and Fable estimate **identically** — the Claude 5 models share one tokenizer |

The split is by model **generation, not model size**. A drift in the equality pin means a family regrouped, which is the more consequential of the two: it silently re-rates every file measured for that model.

---

## Capture Self-Containment Scan

> [!constraint] Read-Only — Always Runs
> This scan is independent of Token Saver; it runs on every `/planwise doctor`. It only READS backlog and lesson files and prints advisory flags — it writes nothing.

A backlog item or lesson whose substantive content is only a pointer to an external or transient source (another repo, an absolute path outside this project, a session-only scratch file, "see the diff in session X") becomes non-executable the moment that source is unavailable. The capture handlers inline this content at capture time ([backlog.md](backlog.md) Step 7.3, [lessons.md](lessons.md) Step 2 / Step 3); this scan is the after-the-fact backstop for captures that predate the discipline or slipped through.

### Step 7: Flag pointer-only captures (advisory)

The script prints this stage (banner: Capture self-containment). Pass it through verbatim. The scan is advisory only. A pointer that merely *supplements* inlined content is fine, and the flag is a prompt to verify, not a failure.

---

## Bookkeeping Index Read-Gate Scan

> [!constraint] Read-Only — Always Runs
> This scan is independent of Token Saver; it runs on every `/planwise doctor`. It only READS the three bookkeeping indexes and the fixed Read-tool limits, then prints a report. It writes nothing.

### Step 8: Bookkeeping index read-gate scan

The script prints this stage (banner: planwise doctor — bookkeeping index read-gate scan). Pass it through verbatim. Step 5 scans one plan's own files. This step scans the backlog, lessons, plans and companion indexes, and it runs whether or not `context.token_saver` is on. Its scope does not extend to item files or lesson files.

---

*Cross-reference: [run.md](run.md) (Step 4.3 Update Plan Status), [`references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md §1.19`](../references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) (Model-Floor Bridge), [`references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md §1.20`](../references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) (1M-Exception Dispatch), [upgrade.md](upgrade.md) (post-upgrade over-scope advisory, Token Saver recalibration), [lint + token_saver engine in scripts/](../scripts/init_project.py), [reconcile_plans.py](../scripts/reconcile_plans.py) (plans index drift detect, shared with [list.md](list.md); its `--write` delegates to [generate_plans_index.py](../scripts/generate_plans_index.py)), [reconcile_backlog.py](../scripts/reconcile_backlog.py) (backlog index archival-drift detect/reconcile, shared with [backlog.md](backlog.md)), [generate_lessons_index.py](../scripts/generate_lessons_index.py) (lessons index generation and `--check` drift detect, sharing file-level anomaly detect/reconcile with [reconcile_lessons.py](../scripts/reconcile_lessons.py)).*
