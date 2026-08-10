# Handler: /planwise doctor

**Purpose:** Report `.claude/rules/**` that are over-scoped to plan/backlog/lessons paths (an injection-budget risk for DELEGATED task-runners), flag backlog/lesson captures whose substance is only an external or transient pointer (a capture-durability risk), audit the plans index for drift against each plan's Master Plan status, audit the backlog index for archival drift (closed items whose file is not under `Archive/`), audit the lessons index for "Next available ID" counter drift (a lesson authored outside capture mode leaves the counter stale and the next capture reuses an ID), and — when Token Saver is on — audit the measured overheads for staleness, scan the active plan's files against the Read-tool gates, and flag the fixed read-limit constants for harness drift. Read-only — mutates nothing (drift reconciliation is offered only on explicit consent).

**Invocation examples:**
```
/planwise doctor
```

---

## Config Gate

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue. Extract `plugin_root`, `project.planwise_root`, `project.plans_dir`, `project.backlog_dir`, `project.lessons_dir` (absent → skip Stage 13), `project.index_files`, and the `context:` Token Saver keys (`token_saver`, `token_saver_runner_overhead`, `token_saver_orchestrator_overhead`, `token_saver_session_target`, `token_saver_overhead_measured_on`, `token_saver_context_breakdown`) plus the pinned `plugin_version`.
3. If NOT found: this install is **not initialized**. Recommend `/planwise init` and **STOP** — `doctor` is read-only and never initializes on the user's behalf. (This is the same "not initialized" outcome the Preflight version-state gate reports; do not auto-init.)

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed, DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise doctor." STOP.

`{project_root}` is the absolute path of the project root (the directory containing `{planwise_root}/`).

---

## Workflow

### Preflight: Plugin version-state gate

Before any diagnostics, `--doctor` emits an **always-on** version-state gate (independent of Token Saver) — the cheap "is this install even in a sane state to be doctored?" check that precedes everything else. It is read-only: it only *recommends* `init`/`upgrade`; those commands remain the only writers (they bump the `plugin_version` pin and, at the same commit point, repoint `plugin_root`). The same `init_project.py --doctor` invocation shown in Step 1 prints the gate verdict **first**, then either stops or proceeds:

| Gate state | Condition | doctor output | Action |
|------------|-----------|---------------|--------|
| Not initialized | no `config.yaml` resolved | `! Not initialized …` | Recommend `/planwise init` and **STOP** — no diagnostics run |
| Version drift | pinned `plugin_version` ≠ installed plugin (absent / `0.0.0` counts as drift) | `! Version drift — pinned {X} != installed {Y}` | Recommend `/planwise upgrade`, showing both versions, and **STOP** |
| `plugin_root` dangling | pinned == installed, but the configured `plugin_root:` points at a directory that no longer exists | `! plugin_root dangling — {path} does not exist` | Recommend `/planwise upgrade` (repoints `plugin_root` even though the version pin is already current) and **STOP** |
| `plugin_root` version mismatch | pinned == installed, but the configured `plugin_root:` directory's own `.claude-plugin/plugin.json` version ≠ pinned | `! plugin_root version mismatch — {path} is {X}, pinned is {Y}` | Recommend `/planwise upgrade` and **STOP** |
| Up to date | pinned == installed, and the configured `plugin_root:` (when present) resolves to a directory whose own version matches | `plugin version {X} — up to date` | Proceed with the over-scope linter (and the Token-Saver audit when enabled) |

The pinned version is read from `config.yaml` (`plugin_version:`; absent → `0.0.0`); the installed version via `read_plugin_version(plugin_root)` from `.claude-plugin/plugin.json` — always the LIVE currently-executing plugin, never the configured `plugin_root:` value, so this comparison alone is immune to a stale `plugin_root:`. The two `plugin_root` checks below it catch a DIFFERENT residual defect: a version pin that already looks current (a legacy upgrade bumped it without repointing the root, or the cache directory the config still names was later reaped) while the separate `plugin_root:` key every other handler resolves scripts through is still wrong. The gate stops on any non-`up to date` state, so **everything below (over-scope lint, Token-Saver audit) runs only when the full gate — version pin AND `plugin_root` — is healthy.**

### Step 1: Run the over-scope linter

```bash
python "{plugin_root}/scripts/init_project.py" --doctor --project-root "{project_root}"
```

If `python` is not found, try `python3`.

> [!constraint] Read-Only — Never Mutates
> `--doctor` runs the version-state gate followed by `lint_rule_overscope()` standalone (no `--upgrade`, no `--migrate`). It only READS `config.yaml`, `.claude-plugin/plugin.json`, and `.claude/rules/**`, then prints a report; it writes nothing and changes no files. It exits 0 in every state — version drift and flagged rules are reported, not failed.

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

### Stage 8: Stale de-scoped rule sweep (post-boundary)

> [!constraint] Read-Only — bare doctor only recommends
> Stage 8 runs `sweep_stale_descoped_rules()` standalone. It READS
> `.claude/rules/**` and the plugin's `references/`, then prints a report. It
> writes nothing and deletes nothing. The one-shot de-scope migration in
> `/planwise upgrade` is spent for any install already past the de-scope
> boundary; this sweep is the only mechanism that surfaces the leftover
> rules. To actually remove them, the user opts in with the separate writer
> `/planwise doctor --prune-stale` (Stage 8b below).

Always-on (independent of Token Saver). The sweep classifies every still-installed
de-scoped rule under `.claude/rules/planwise/` against its shipped `references/`
copy and recommends one of:

- **REMOVABLE** (`~`) — identical to, or a stale subset of, the now-grown shipped
  reference. The canonical rule is handler-loaded from `references/`; the
  installed copy is dead always-on weight. A subset only qualifies as REMOVABLE
  when its structural verdict carries an empty `notes` field — a subset where
  the matcher tolerated any installed-only content reports PRESERVE instead, so
  a genuine short customization is never silently deleted. *Remove with `/planwise doctor --prune-stale`.*
- **PRESERVE** (`!`) — the installed copy has genuine unique content (a real
  customization), or could not be proven stale. *Re-home to
  `.claude/rules/<project>/<name>.md`; do NOT delete.*
- **RELOCATE** (`~`) — a `<…>-<de-scoped-name>.md` file matching the old
  prefix-rename workaround fingerprint. *Migrate to `.claude/rules/<project>/<name>.md`.*

Print verbatim:

```
planwise doctor — stale de-scoped rule sweep (post-boundary)

Stale de-scoped rules still installed under .claude/rules/planwise/:
  ~ {filename}.md   REMOVABLE
      size:    {N} lines (~{X} tokens)
      reason:  {untouched leftover | stale subset of grown shipped reference}
      action:  remove with /planwise doctor --prune-stale
  ! {filename}.md   PRESERVE
      size:    {N} lines (~{X} tokens)
      reason:  genuine customization (unique content)
      action:  re-home to .claude/rules/<project>/<name>.md — do NOT delete
  ~ {prefix}-{filename}.md   RELOCATE (prefix-rename fingerprint)
      size:    {N} lines (~{X} tokens)
      reason:  prefix-rename hack fingerprint of a de-scoped rule
      action:  migrate to .claude/rules/<project>/<name>.md

Total REMOVABLE always-on budget: ~{X} tokens across {N} rule(s).
```

If the sweep returns nothing: `No stale de-scoped rules found — install is past the boundary and clean.`

### Stage 8b: `--prune-stale` (opt-in writer)

When `$ARGUMENTS` contains `--prune-stale`, this is the ONE doctor path that mutates.
Run the writer:

```bash
python "{plugin_root}/scripts/init_project.py" --prune-stale --project-root "{project_root}"
```

It deletes REMOVABLE-marked artifacts from BOTH sweeps in the same pass — the
Stage 8 de-scoped rules and the Stage 10 orphaned `.claude/agents/*.md`
mirrors (below) — one opt-in writer, two artifact kinds, sharing the same
backup folder, log, and version gate. It never touches a **PRESERVE**
(customized, or not provably stale) or **RELOCATE** one — a customized agent
mirror is left in place exactly like a customized rule. It writes
`{planwise_root}/upgrade-backups/prune-{YYYY-MM-DD}/PRUNED.md` listing every
removed and preserved rule or agent mirror, with its kind and reason. If a
`prune-{YYYY-MM-DD}/` folder already exists (a second run the same day), the
run gets its own `prune-{YYYY-MM-DD}-2/`, `-3/`, ... folder instead — an
earlier run's log and backups are never overwritten. Every deleted file
(rule or agent mirror) is first copied as a pre-image into that same run's
prune folder alongside `PRUNED.md`, so a prune is recoverable; a file whose
deletion fails after a successful backup is reported `REMOVE_FAILED` (left
in place) and its orphan backup copy is removed. Pass the script's stdout
through and point the user at the `PRUNED.md` audit log.

---

### Stage 9: Installed rule divergence lint

> [!constraint] Read-Only — bare doctor only recommends
> Stage 9 runs `lint_installed_divergence()` standalone. It READS the
> still-installed set (`INSTALLED_RULES`) under `.claude/rules/planwise/`,
> plus the plugin's shipped `references/` copies, then prints a report. It
> writes nothing and deletes nothing — there is no opt-in writer for this
> stage.

Always-on (independent of Token Saver). Generalizes the Stage 8 sweep from
the de-scoped rule set to the still-installed set: each installed rule is
normalized with the same `paths:`-stripping normalization the writer uses
(both sides are read `utf-8-sig`, matching the upgrade writer, so a
BOM'd-but-untouched copy is never falsely flagged), a normalized-identical
pair is skipped before the structural primitive is ever invoked, and each
remaining file is classified as one of:

- **SUBSET** (`~`) — the installed copy's content is fully contained in the
  now-grown shipped reference. Notes-clean: *recommend `/planwise upgrade` —
  it auto-adopts the shipped version.* Notes-flagged (the matcher tolerated
  installed-only content): *recommend `/planwise upgrade` — it transfers the
  flagged content first (or preserves in place, per
  `upgrade.customization_handoff`) before adopting shipped* — upgrade never
  auto-adopts unconditionally over flagged content.
- **HAS_UNIQUE** (`!`) — the installed copy carries genuine unique content (a
  real customization). *Re-home per the "Choosing a Home for a Rule
  Customization" decide callout* — do NOT delete.
- **NOT_ANALYZED** (`?`) — the file diverges but structural comparison was
  unavailable, so no analysis ran. Reported explicitly, never as a confident
  HAS_UNIQUE recommendation — diff it against the shipped copy manually.
- **UNVERIFIABLE** (`?`) — the installed file is unreadable (e.g. not
  UTF-8), or the shipped reference is missing/unreadable (broken or partial
  install). Reported explicitly rather than silently skipped, and it never
  crashes the always-exit-0 doctor run.

Print verbatim:

```
planwise doctor — installed rule divergence lint

  ~ {path}   SUBSET
      size:    {N} lines (~{X} tokens)
      action:  {the SUBSET recommendation above — notes-clean or notes-flagged}
  ! {path}   HAS_UNIQUE
      size:    {N} lines (~{X} tokens)
      action:  {the HAS_UNIQUE recommendation above}
  ? {path}   {NOT_ANALYZED | UNVERIFIABLE}
      size:    {N} lines (~{X} tokens)
      action:  {the explicit not-analyzed / unverifiable notice}
```

If nothing diverges AND nothing was unverifiable or not-analyzed:
`All installed rules match shipped — no divergence found.` (The
all-clear line never prints over an unverifiable or not-analyzed row.)

---

### Stage 10: Orphaned agent mirror sweep (post-boundary)

> [!constraint] Read-Only — bare doctor only recommends
> Stage 10 runs `sweep_orphaned_agent_mirrors()` standalone. It READS
> `.claude/agents/*.md` and the plugin's shipped `agents/` copies, then
> prints a report. It writes nothing and deletes nothing. Agent files used
> to be mirrored into every install on init/upgrade; that mirroring
> behavior is gone, so every install's existing mirrored copy became an
> orphan the moment it dropped — there is no one-shot migration to gate,
> so this sweep is a permanent, always-on diagnostic rather than a
> version-boundary-gated one-shot. To actually remove an orphan, the user
> opts in with the same writer described in Stage 8b above
> (`/planwise doctor --prune-stale`).

Always-on (independent of Token Saver). The sweep classifies every installed
agent mirror under `.claude/agents/` against its shipped counterpart
(whole-file identity comparison — an installed agent carries no `paths:`
frontmatter key to normalize away, unlike a rule) and recommends one of:

- **REMOVABLE** (`~`) — untouched (byte-identical to the shipped agent) or a
  stale/reorganized subset of it. *Remove with `/planwise doctor --prune-stale`.*
- **PRESERVE** (`!`) — the installed copy carries genuine unique content (a
  real customization — e.g. a pinned `model:`/`tools:`/`maxTurns:` override
  simply makes the whole file diverge and correctly routes here), a subset
  where the matcher tolerated some installed-only content it could not
  prove was noise, or the file could not be proven stale at all (shipped
  reference missing/unreadable, installed file unreadable, or structural
  comparison degraded/unavailable). *Never a confident recommendation on
  incomplete evidence — do NOT delete.*

An installed file with no shipped counterpart in `agents/` is skipped
silently (not installed via the plugin, or already not a formerly-mirrored
filename — not a broken install, no finding).

Print verbatim:

```
planwise doctor — orphaned agent mirror sweep

Orphaned agent mirrors still installed under .claude/agents/:
  ~ {filename}.md   REMOVABLE
      size:    {N} lines (~{X} tokens)
      reason:  {untouched shipped agent, orphaned by the dropped mirror | stale/reorganized subset of the shipped agent}
      action:  remove with /planwise doctor --prune-stale
  ! {filename}.md   PRESERVE
      size:    {N} lines (~{X} tokens)
      reason:  {genuine customization (unique content) | matcher tolerated installed-only content | shipped reference unavailable/unreadable | installed file unreadable — cannot classify}
      action:  keep in place — customization detected, do NOT delete

Total REMOVABLE orphaned agent mirror(s): {N} of {M} found.
```

If the sweep returns nothing: `No orphaned agent mirrors found — install has
none of the formerly mirrored agents left, or they already match shipped.`

---

### Stage 11: Plans Index Drift Audit

> [!constraint] Read-Only — audit only recommends
> Stage 11 runs `reconcile_plans.py --json` standalone. It READS the plans
> index (`{plans_dir}/{plans_index}`) and each row's Master Plan `Status:`
> field, then prints a report. It writes nothing unless the user explicitly
> consents to reconcile (below) — the audit itself never mutates.

Always-on (independent of Token Saver) — auditing plans-index consistency is
doctor's purpose, so this check has **no `--no-check` escape hatch** (contrast
`/planwise list`, where the same detect pass IS skippable for a fast glance).
The plans index is a denormalized cache: each row's Status column is a copy
of its Master Plan's own `Status:` field, written at closeout by run.md's
Step 4.3 "Update Plan Status" (sub-step 5). Nothing else re-checks the cache
against the source of truth between closeouts, so a plan completed outside
that step — or before it existed — can carry a stale row indefinitely. This
audit runs the same detect pass `/planwise list` runs, reused here as one
more health check alongside doctor's existing over-scope/divergence/
self-containment scans; neither handler re-implements the comparison.

Run the shared script:

```bash
python "{plugin_root}/scripts/reconcile_plans.py" --config "{planwise_root}/config.yaml" --json
```

Read the JSON file at the path it prints (`JSON: {path}`), shaped
`{"drifts": [...], "anomalies": [...]}`. Report every drift and anomaly:

```
planwise doctor — plans index drift audit

Drift detected ({K} row(s) out of sync with Master Plan status):
  ! {ABBR}: index={X}  ->  Master Plan={Y}

Anomalies ({N}):
  ? {ABBR}: Master Plan not found at {path}
```

If both are empty: `No drift detected. All index rows match their Master
Plan status.`

**Optional write-on-consent (same contract as `/planwise list`):** after
reporting, doctor MAY offer to reconcile via `AskUserQuestion` ("Reconcile
{K} drifted row(s) in the plans index to match their Master Plan status?").
On agreement, run:

```bash
python "{plugin_root}/scripts/reconcile_plans.py" --config "{planwise_root}/config.yaml" --write
```

The script re-reads the index immediately before writing (race-safe against
a concurrent closeout), reconciles only rows still drifted, and never writes
an anomaly row. Report `Reconciled {N} row(s).` Declining leaves the index
untouched — the report above already recorded what was found.

---

### Stage 12: Backlog Index Archival Drift Audit

> [!constraint] Read-Only — audit only recommends
> Stage 12 runs `reconcile_backlog.py --json` standalone. It READS the backlog
> index (`{backlog_dir}/{backlog_index}`) and the on-disk location of each
> closed item's file, then prints a report. It writes nothing unless the user
> explicitly consents to reconcile (below) — the audit itself never mutates.

Always-on (independent of Token Saver) — auditing backlog-index consistency is
doctor's purpose, so this check has **no `--no-check` escape hatch** (contrast
`/planwise backlog`, where the same detect pass IS skippable for a fast triage).
Archival is **state-coupled, not transition-coupled**: a COMPLETE/CLOSED item's
file must live under `Archive/` and its index link must point there.
`update_backlog.py` reconciles that on every `--status COMPLETE`/`CLOSED` call,
but an item that reaches a closed status by another path — a session closeout
that hand-edits the index row + frontmatter — leaves the file stranded in the
top-level backlog dir with an index link that never repointed. This audit is the
read-side counterpart, the backlog-index analogue of the Stage 11 plans-index
drift audit; neither re-implements the other's comparison.

Run the shared script:

```bash
python "{plugin_root}/scripts/reconcile_backlog.py" --config "{planwise_root}/config.yaml" --json
```

Read the JSON file at the path it prints (`JSON: {path}`), shaped
`{"drifts": [...], "anomalies": [...]}`. `drifts` are closed rows whose file is
not archived (or whose index link is not repointed); `anomalies` are closed rows
whose linked file exists in neither the top-level backlog dir nor `Archive/`
(deleted/renamed — reported, never fabricated). Report every drift and anomaly:

```
planwise doctor — backlog index archival drift audit

Drift detected ({K} closed row(s) whose file is not archived):
  ! {ID} ({STATUS}): {file} — {reason}

Anomalies ({N}):
  ? {ID} ({STATUS}): {file} — linked file not found in backlog dir or Archive/
```

If both are empty: `No archival drift detected. All closed backlog rows are
archived.`

**Optional write-on-consent (same contract as `/planwise backlog`):** after
reporting, doctor MAY offer to reconcile via `AskUserQuestion` ("Archive {K}
stranded closed row(s) — move the file(s) into `Archive/` and repoint the index
link(s)?"). On agreement, run:

```bash
python "{plugin_root}/scripts/reconcile_backlog.py" --config "{planwise_root}/config.yaml" --write
```

The script re-reads the index immediately before writing (race-safe against a
concurrent closeout), heals only rows still drifted, and never touches an
anomaly row. Report `Reconciled {N} row(s).` Declining leaves the backlog
untouched — the report above already recorded what was found.

---

### Stage 13: Lessons Index Counter Drift Audit

> [!constraint] Read-Only — audit only recommends
> Stage 13 runs `reconcile_lessons.py --json` standalone. It READS the lessons
> index (`{lessons_dir}/{lessons_index}`), the lesson files in that directory
> and its `Archive/`, then prints a report. It writes nothing unless the user
> explicitly consents to reconcile (below) — the audit itself never mutates.

Always-on (independent of Token Saver) — auditing index consistency is doctor's
purpose, so this check has **no `--no-check` escape hatch**. Skip the stage
entirely only when `config.yaml` declares no `project.lessons_dir` (a project
with no lessons scaffolding has no counter to audit); report
`Lessons index: not configured — audit skipped`.

The `**Next available ID:** LL-{NNN}` line is a denormalized cache of one fact —
the highest lesson ID that exists anywhere — with exactly one writer: capture
mode, which bumps it after writing a lesson. Every other route that creates a
lesson (a hand-written closeout capture, a task-runner producing one as a sprint
deliverable) leaves it untouched. The next capture then reads a value below the
true max and either reuses an existing ID — producing two lessons the master
table cannot both represent — or forces a manual fix. This audit is the
read-side counterpart, the lessons-index analogue of the Stage 11 plans-index
and Stage 12 backlog-index drift audits; none re-implements another's
comparison.

Run the shared script:

```bash
python "{plugin_root}/scripts/reconcile_lessons.py" --config "{planwise_root}/config.yaml" --json
```

Read the JSON file at the path it prints (`JSON: {path}`), shaped
`{"drifts": [...], "anomalies": [...], "next_id": "LL-NNN"}`. `drifts` holds at
most one entry — the counter is a single field — and is non-empty only when the
counter is BEHIND the true next ID. `anomalies` covers four separate conditions,
none of which is ever healed automatically:

| Anomaly `kind` | Meaning |
|----------------|---------|
| `missing_counter_line` | The index carries no "Next available ID:" line — nothing to reconcile against; never fabricated at a guessed position |
| `counter_ahead` | The counter is above the true next ID — an ID may have been retired deliberately, and lowering it would let a later capture reuse an ID that cross-references still name |
| `row_without_file` | A master-table row whose lesson file exists in neither the lessons dir nor `Archive/` (deleted/renamed — reported, never fabricated). Its ID still bounds the counter: a retired ID is not free for reuse |
| `file_without_row` | A lesson file on disk with no master-table row — the same off-capture authoring signal from the other direction |

Report every drift and anomaly:

```
planwise doctor — lessons index counter drift audit

Drift detected (the "Next available ID" counter is stale):
  ! stated {STATED} — expected {EXPECTED}: {reason}

Anomalies ({N}):
  ? {ID}: {reason}
```

If both are empty: `No counter drift detected. The lessons index 'Next
available ID' matches the highest lesson ID on disk and in the master table
({next_id}).`

A stale counter is worth surfacing beyond the number itself: it means some
lesson was authored off the capture path, so that lesson's master-table row and
its categorisation entry were hand-made too and may carry their own gaps. Say so
in the report rather than presenting the bump as a bookkeeping nit.

**Optional write-on-consent (same contract as Stages 11 and 12):** after
reporting, doctor MAY offer to reconcile via `AskUserQuestion` ("Bump the
lessons-index counter from {STATED} to {EXPECTED}?"). On agreement, run:

```bash
python "{plugin_root}/scripts/reconcile_lessons.py" --config "{planwise_root}/config.yaml" --write
```

The script re-reads the index immediately before writing (race-safe against a
concurrent capture), rewrites only the counter line's digits — every other line
and the file's original line endings are preserved — and only ever moves the
counter FORWARD. Report `Reconciled the counter: {FROM} → {TO}.` Declining
leaves the index untouched — the report above already recorded what was found.

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
   | Plugin upgraded since calibration | Folded into the **Preflight version-state gate** — `doctor` stops on `pinned ≠ installed` before this audit runs, so reaching Step 4 guarantees pinned == installed. Do not re-compare versions here. (A version-bumping `/planwise upgrade` may shift the rule/agent surface; re-capture overheads with `/planwise token-saver on` after upgrading.) |
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

The read-constant tripwire is paired with a cross-model ratio-band assertion: `scripts/test_token_saver.py::TestReadLimits::test_cross_model_ratio_band` asserts `1.4 ≤ opus_tokens / sonnet_tokens ≤ 1.55` for the same file. A ratio drift outside this band signals a tokenizer-weight change in the `TOKENS_PER_LINE` constants.

---

## Capture Self-Containment Scan

> [!constraint] Read-Only — Always Runs
> This scan is independent of Token Saver; it runs on every `/planwise doctor`. It only READS backlog and lesson files and prints advisory flags — it writes nothing.

A backlog item or lesson whose substantive content is only a pointer to an external or transient source (another repo, an absolute path outside this project, a session-only scratch file, "see the diff in session X") becomes non-executable the moment that source is unavailable. The capture handlers inline this content at capture time ([backlog.md](backlog.md) Step 7.3, [lessons.md](lessons.md) Step 2 / Step 3); this scan is the after-the-fact backstop for captures that predate the discipline or slipped through.

### Step 7: Flag pointer-only captures (advisory)

1. Scan the working-set capture files (exclude `Archive/` — closed items):
   - Backlog: `{planwise_root}/{backlog_dir}/BB-*.md` and `BLI-*.md`
   - Lessons: `{planwise_root}/{lessons_dir}/LL-*.md`

2. For each file, compute two signals (both greps case-insensitive, body only — ignore YAML frontmatter):

   | Signal | How to detect |
   |--------|---------------|
   | **Has an external/transient pointer** | A line referencing an absolute path outside this project (`[A-Za-z]:\\…`, `/Users/`, `/home/`, `/repos/`), another-repo reference, or a transient-source phrase (`see (the )?(session\|diff\|scratch)`, `session-only`, `in scratch`) |
   | **Lacks inlined substance** | The body contains NO fenced code block (```` ``` ````) AND no inlined verbatim example, spec, or command output — i.e., nothing the pointer could be standing in for |

3. Soft-flag any file where the pointer signal fires AND the inlined-substance signal is absent:

   ```
   Capture self-containment (advisory):
     ~ {backlog_dir}/BB-{NNN}-...md
         pointer:  {the matched external/transient reference}
         risk:     substance may live only at that pointer — capture could be
                   non-executable if it vanishes
         remedy:   inline the block/spec/evidence the item depends on
                   (durability test: "executable from this file alone if the origin vanished?")
   ```

   If nothing fires, report: `Capture self-containment: all scanned captures inline their substance.`

This is advisory only — a pointer that merely *supplements* inlined content is fine; the flag is a prompt to verify, not a failure. It complements the capture-time discipline in the handlers rather than gating anything.

---

*Cross-reference: [run.md](run.md) (Model-Floor Bridge, 1M-Exception Dispatch, Step 4.3 Update Plan Status), [upgrade.md](upgrade.md) (post-upgrade over-scope advisory, Token Saver recalibration), [lint + token_saver engine in scripts/](../scripts/init_project.py), [reconcile_plans.py](../scripts/reconcile_plans.py) (plans index drift detect/reconcile, shared with [list.md](list.md)), [reconcile_backlog.py](../scripts/reconcile_backlog.py) (backlog index archival-drift detect/reconcile, shared with [backlog.md](backlog.md)).*
