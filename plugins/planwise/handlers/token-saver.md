# Handler: /planwise token-saver

**Purpose:** Toggle Token Saver mode anytime — not just at init/upgrade. `on` flips the project-level `context.token_saver` key **and re-calibrates** the measured overheads against a fresh `/context`; `off` flips it to a verified no-op; `status` reports the project default, when it was measured, and whether that measurement is stale. An optional `--plan <PlanName>` writes or clears a per-plan override in that plan's Master-Plan frontmatter without touching `config.yaml` or recalibrating.

This closes two gaps: there was no mid-project flip command (the toggle could only be set at `/planwise init` or offered at `/planwise upgrade`), and a hand-edit of `context.token_saver` never re-calibrated the overheads.

**Invocation examples:**
```
/planwise token-saver on
/planwise token-saver off
/planwise token-saver status
/planwise token-saver status --plan MyFeature
/planwise token-saver on --plan MyFeature
/planwise token-saver --plan MyFeature inherit
```

## Table of Contents

- [Config Gate](#config-gate)
- [Required References](#required-references)
- [Argument Parsing](#argument-parsing)
- [Workflow](#workflow)
  - [Subcommand: on](#subcommand-on)
  - [Subcommand: off](#subcommand-off)
  - [Subcommand: status](#subcommand-status)
  - [Per-plan override: --plan](#per-plan-override---plan)
- [Staleness Signal](#staleness-signal)

---

## Config Gate

Resolve `config.yaml` by checking, in order:

1. `planwise/config.yaml` (default planwise root)
2. `*/config.yaml` one level down from project root
3. If NOT found: announce, resolve `{plugin_root}` from this handler's location, invoke `init_project.py` with `--auto-from "token-saver"`, RE-RESOLVE, and fail loud if still missing.

Extract from `config.yaml`:
- `plugin_root` — the plugin installation path
- `plugin_version` — currently-pinned plugin version (for the staleness check)
- `project.planwise_root`, `project.plans_dir`
- the `context:` Token Saver keys (`token_saver`, `token_saver_runner_overhead`, `token_saver_orchestrator_overhead`, `token_saver_session_target`, `token_saver_overhead_measured_on`, `token_saver_context_breakdown`)

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed, DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise token-saver." STOP.

`{config_path}` is the resolved `config.yaml` path. `{plugin_root}` is the plugin installation path. `{plans_dir}` is the absolute plans directory. Resolve all three exactly as `upgrade.md` and `doctor.md` do.

---

## Required References

- The Token Saver budget engine (`scripts/token_saver.py`): `set_token_saver`, `calibrate`, the derivation helpers, and the FIXED Read-tool gates.
- The shared config loader (`scripts/config_loader.py`): `get_effective_token_saver_config` overlays a per-plan on/off decision onto the project surface.
- [doctor.md](doctor.md) — the staleness signal reused by `status` (see [Staleness Signal](#staleness-signal)).
- [upgrade.md](upgrade.md) — the calibrate-on-enable pattern (`on` reuses the same `token_saver.calibrate(...)` call upgrade runs).

Invoke the Python via the standard pattern: `python "{plugin_root}/scripts/..."` (fall back to `python3` if `python` is not found).

---

## Argument Parsing

Parse `$ARGUMENTS` as `{subcommand} [--plan <PlanName>] [inherit]`:

- `{subcommand}` = `$0` — one of `on`, `off`, `status`. An empty `$0` is treated as `status`.
- `--plan <PlanName>` — optional. When present, the operation targets that plan's Master-Plan override instead of the project default.
- `inherit` (or an omitted `on`/`off` when `--plan` is present) — removes the override line so the plan re-inherits the project default.

| Invocation | Behavior |
|------------|----------|
| `on` (no `--plan`) | [Subcommand: on](#subcommand-on) — flip project key true, then re-calibrate. |
| `off` (no `--plan`) | [Subcommand: off](#subcommand-off) — flip project key false, confirm no-op. Do NOT recalibrate. |
| `status` / empty (no `--plan`) | [Subcommand: status](#subcommand-status) — report default + measured-on + staleness. |
| `status --plan <Name>` | [Subcommand: status](#subcommand-status) — also report that plan's effective value. |
| `on`/`off` `--plan <Name>` | [Per-plan override](#per-plan-override---plan) — write the override; do NOT touch `config.yaml`, do NOT recalibrate. |
| `--plan <Name> inherit` (or `on`/`off` omitted) | [Per-plan override](#per-plan-override---plan) — remove the override line; plan re-inherits the default. |

---

## Workflow

### Subcommand: on

Flip the project default to enabled, then re-measure so plans size against the current footprint.

1. Flip the toggle in place (comment- and order-preserving targeted edit):

   ```bash
   python -c "import sys; sys.path.insert(0, r'{plugin_root}/scripts'); import token_saver; from pathlib import Path; print(token_saver.set_token_saver(Path(r'{config_path}'), True))"
   ```

2. Re-calibrate against a fresh `/context` (reuses the upgrade recalibration call):

   ```bash
   python -c "import sys; sys.path.insert(0, r'{plugin_root}/scripts'); import token_saver; from pathlib import Path; r = token_saver.calibrate(config_path=Path(r'{config_path}'), plugin_root=r'{plugin_root}'); print(r)"
   ```

   `token_saver.calibrate()` overwrites the six `token_saver_*` keys in place and degrades to the conservative fallback if the `/context` capture fails or returns non-report text.

   > **Best-effort capture.** The `/context` report renders reliably only inside an **interactive** Claude Code session. If `calibrate()` is invoked from a non-interactive context, the CLI may return conversational text instead of the structured report; calibration then degrades to the conservative fallback (runner ~54K / orchestrator ~60K, `calibrated:False`). This is expected on some platforms. Running `/planwise token-saver on` from an interactive session is the intended recapture path.

3. Report the result. Derive `available_per_task = token_saver_session_target − token_saver_runner_overhead − 6000` (the engine's `derive_thresholds`; never hardcode the ceiling):

   ```
   Token Saver: ON  (project default)
     Measured runner overhead:       {token_saver_runner_overhead}  tokens
     Measured orchestrator overhead: {token_saver_orchestrator_overhead}  tokens
     Per-task budget (derived):      ~{available_per_task}  tokens  (session_target − runner_overhead − growth_margin)
     Calibrated on:                  {token_saver_overhead_measured_on}
   ```

   If the result's `uncalibrated` flag is `true` (the `/context` capture failed or returned non-report text — expected on some platforms), add:

   ```
     ! Uncalibrated — used conservative fallback (runner ~54K / orchestrator ~60K).
       Run this command again from an interactive session to capture real numbers.
   ```

### Subcommand: off

Flip the project default to disabled. This is a verified no-op path — when Token Saver is off the budget engine does not scan, ladder, or raise.

1. Flip the toggle in place:

   ```bash
   python -c "import sys; sys.path.insert(0, r'{plugin_root}/scripts'); import token_saver; from pathlib import Path; print(token_saver.set_token_saver(Path(r'{config_path}'), False))"
   ```

2. Do **NOT** recalibrate — the measured overheads are left exactly as-is so a later re-enable reuses them (until `on` re-measures).

3. Confirm the no-op:

   ```
   Token Saver: OFF  (project default)
     The budget engine is disabled — no read-gate scan, no task-budget ladder, no exceptions.
     Measured overheads are preserved for a future re-enable (run `/planwise token-saver on` to re-measure).
   ```

### Subcommand: status

Read-only. Report the project default and the staleness of its measurement. Mutates nothing.

1. Report the project surface:

   ```
   Token Saver: {ON|OFF}  (project default)
     Measured on:  {token_saver_overhead_measured_on}
     Runner overhead:       {token_saver_runner_overhead}  tokens
     Orchestrator overhead: {token_saver_orchestrator_overhead}  tokens
   ```

2. Evaluate the [Staleness Signal](#staleness-signal). When either signal fires, surface the recommendation (never auto-mutate):

   ```
   ! Token Saver overheads may be STALE ({reason}).
     Re-measure with: /planwise token-saver on   (re-runs calibrate against a fresh /context)
   ```

3. If `--plan <Name>` is given (or a plan is otherwise in scope), read that plan's Master-Plan `Token Saver:` frontmatter field and report the **effective** value:
   - Parse the field to `True` (`on`), `False` (`off`), or `None` (absent → inherit).
   - Resolve the effective value via `get_effective_token_saver_config(config, plan_override)` (the plan flips only the on/off boolean; the measured overheads always come from the project config):

   ```bash
   python -c "import sys; sys.path.insert(0, r'{plugin_root}/scripts'); import config_loader; c = config_loader.load_config(); print(config_loader.get_effective_token_saver_config(c, {plan_override}))"
   ```

   Report:

   ```
   Plan '{PlanName}' override: {on|off|inherit (no override)}
     Effective for this plan:  {ON|OFF}
   ```

### Per-plan override: --plan

The override target is the plan's Master Plan frontmatter `Token Saver:` field — a project-agnostic on/off flip for one plan. It does NOT change `config.yaml` and does NOT recalibrate: the override flips enforcement for that one plan, while the measured overheads stay project-level (there is exactly one `/context` calibration per project).

1. Locate the plan's Master Plan: `{plans_dir}/{PlanName}/{Abbrev}-Master-Plan.md`. If the plan folder or Master Plan is missing, FAIL LOUD naming the path searched.

2. Apply the override by editing the Master-Plan frontmatter only:

   | Invocation | Edit |
   |------------|------|
   | `on --plan <Name>` | Set the frontmatter line to `**Token Saver:** on` (add it under the `**Status:**`/`**Created:**` frontmatter block if absent). |
   | `off --plan <Name>` | Set the frontmatter line to `**Token Saver:** off`. |
   | `--plan <Name> inherit` (or on/off omitted) | Remove the `**Token Saver:**` line entirely so the plan re-inherits the project default. |

   Use the same `**Key:** value` frontmatter style the Master Plan template uses (a sibling of `**Plan Abbreviation:**`, `**Status:**`, `**Created:**`). The field is optional; omitted means inherit.

3. Confirm without touching `config.yaml`:

   ```
   Plan '{PlanName}' Token Saver override: {on|off|removed (inherits project default)}
     config.yaml unchanged — measured overheads stay project-level.
   ```

---

## Staleness Signal

Reused from [doctor.md](doctor.md)'s overhead-staleness check. The stored overheads no longer reflect this install's real `/context` footprint when EITHER signal fires:

| Staleness signal | How to detect |
|------------------|---------------|
| Plugin upgraded since calibration | The pinned `plugin_version` in `config.yaml` differs from the plugin's current shipped version (read `{plugin_root}/.claude-plugin/plugin.json` → `version`). The overheads were measured against the old rule/agent surface. |
| Agent/Skill count changed | The Custom Agents / Skills count in a fresh `/context` differs from the captured `token_saver_context_breakdown` (added/removed agents or skills shift the always-on surface). |
| Overheads uncalibrated | `token_saver_runner_overhead` is `0`/empty, or equals the conservative fallback (`~54000` runner / `~60000` orchestrator) with no live capture recorded. |

`status` only **reports** staleness and recommends the one-command re-measure (`/planwise token-saver on`). It never mutates `config.yaml` itself.

---

*Cross-reference: [upgrade.md](upgrade.md) (Token Saver recalibration), [doctor.md](doctor.md) (overhead-staleness audit, read-gate scan), [token_saver + config_loader in scripts/](../scripts/token_saver.py).*
