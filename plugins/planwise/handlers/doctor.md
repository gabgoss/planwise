# Handler: /planwise doctor

**Purpose:** Report `.claude/rules/**` that are over-scoped to plan/backlog/lessons paths (an injection-budget risk for DELEGATED task-runners), flag backlog/lesson captures whose substance is only an external or transient pointer (a capture-durability risk), audit the plans index for drift against a fresh render of each plan's Master Plan, audit the backlog index for archival drift (closed items whose file is not under `Archive/`), audit the lessons index for "Next available ID" counter drift (a lesson authored outside capture mode leaves the counter stale and the next capture reuses an ID), probe whether upstream feedback can actually post (`feedback.enabled`, `gh` on PATH, `gh` authenticated) rather than silently drafting, report whether this session has the Task checklist tools (`TaskCreate` and siblings) and name the opt-in when it does not, always scan the plans/backlog/lessons bookkeeping indexes against the same Read-tool caps regardless of Token Saver, and — when Token Saver is on — audit the measured overheads for staleness, scan the active plan's files against the Read-tool gates, and flag the fixed read-limit constants for harness drift. Read-only — mutates nothing (drift reconciliation is offered only on explicit consent).

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

**Invocation examples:**
```
/planwise doctor
```

This handler spans **three files**, split by topic because the combined text exceeds the Read-tool page cap. Each Stage/Step keeps its own identifier wherever it lands, so an existing `Stage N` or `Step N` reference still names exactly one section — only the filename that holds it changes.

| Part | File | Stages / Steps | Topic |
|---|---|---|---|
| 1 (this file) | `doctor.md` | Preflight, Steps 1-3, Stages 8-13 | Version-state gate, over-scope linter, stale-rule/agent-mirror sweeps, plans/backlog/lessons index drift audits |
| 2 | [`doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md`](doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md) | Stages 14-21 | Upgrade recovery-leftover sweep, settings-grant sweep, feedback capability/directory probes, task-tools advisory, backlog body-status and index-shape audits, lessons index-shape audit |
| 3 | [`doctor-Part-3-TokenSaverAndBookkeepingReadGates.md`](doctor-Part-3-TokenSaverAndBookkeepingReadGates.md) | Steps 4-8 | Token Saver overhead/read-gate/read-constant audits, capture self-containment scan, bookkeeping index read-gate scan |

`/planwise doctor` reads all three files in sequence — this file first, then Part 2, then Part 3 — to produce one continuous report.

---

## Config Gate

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue. Extract `plugin_root`, `project.planwise_root`, `project.plans_dir`, `project.backlog_dir`, `project.lessons_dir` (absent → skip Stage 13), `project.feedback_dir` (absent → default `Feedback`), `project.index_files`, and the `context:` Token Saver keys (`token_saver`, `token_saver_runner_overhead`, `token_saver_orchestrator_overhead`, `token_saver_session_target`, `token_saver_overhead_measured_on`, `token_saver_context_breakdown`) plus the pinned `plugin_version`.
3. If NOT found: this install is **not initialized**. Recommend `/planwise init` and **STOP** — `doctor` is read-only and never initializes on the user's behalf. (This is the same "not initialized" outcome the Preflight version-state gate reports; do not auto-init.)

> [!gate] Config Malformed → diagnose FIRST, then FAIL LOUD
> If `config.yaml` is present but malformed, DO NOT auto-init — and do NOT stop before diagnosing. Run the Step 1 command below against the **currently-executing** plugin's own `scripts/` path (not the unreadable config's `plugin_root:`): the script resolves its own root from its file location and never parses `config.yaml` to dispatch, so it still runs and prints a `Config parse check` block that names the offending key and the fix when the cause is a recognised one. Pass that block through verbatim.
> Then FAIL LOUD: "config.yaml parse error at {path}: {error}. The Config parse check above names the offending key — fix the reported line, then re-run /planwise doctor." STOP.

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

The linter flags any `.claude/rules/**` file whose `paths:` target plan/backlog/lessons directories (e.g., `planwise/Plans/**`) rather than code paths. For each flagged rule it reports the path, byte size, line count, approximate token cost (bytes ÷ the conservative bytes-per-token ratio), and the matched glob.

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

Injection families (rules co-injected by a single path match; ceiling ~{C} tokens):
  ! {glob}
      rules: {N}   size: {L} lines (~{X}K tokens)   OVER CEILING
  ~ {glob}
      rules: {N}   size: {L} lines (~{X}K tokens)   within ceiling
```

If no rules are flagged, the script prints `No overscoped rules found.` — report that the project's rule surface is healthy, and no injection-family block is printed.

The families block groups the same flagged rules above by matched glob: every rule sharing a glob targets the same plan/backlog/lessons subtree, so a single path read under that subtree co-injects the whole family's tokens in one context window — the family total, not any one rule's own size, is the number that matters for overflow risk. A family is marked `OVER CEILING` when its total exceeds the configurable `context.token_saver_injection_ceiling` (default 40000 tokens); the config key is read once, so lowering it on a broad-rule-surface install tightens the warning without editing the linter.

### Step 3: Explain the why (only when rules were flagged)

Briefly note: a rule scoped to `planwise/Plans/**` is injected into EVERY context that reads a plan brief — including a DELEGATED `task-runner` subagent, whose 200K window can overflow ("Prompt is too long") when the flagged surface is large. The fix is to re-scope the rule's `paths:` to the code directories it actually governs, or to load it on demand (handler / `references/`) rather than installing it path-scoped. The Model-Floor Bridge (see [`references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md §1.19`](../references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md)) is the temporary dispatch safety-net that keeps declared-Sonnet runners alive until the flagged surface is brought down.

Nothing here is automatic — the linter only converts an invisible cost into a visible, actionable one. But the visibility is worth acting on: measured up to ~56,000 tokens per affected session on average, and up to ~96,000 tokens in a single turn, on a broad-rule-surface install.

---

> [!note] What `(post-boundary)` means in this handler
> The *boundary* is a **version-migration boundary**. A stage labelled
> `(post-boundary)` is a permanent, always-on diagnostic that catches what a
> version-gated one-shot migration never reached or can no longer reach —
> `sweep_stale_descoped_rules()` walks the leftovers `migrate_installed_rules()`
> missed once its version gate was spent, and `sweep_orphaned_agent_mirrors()`
> is "a permanent, always-on diagnostic rather than a version-boundary-gated
> one-shot" because the mirror behavior it cleans up after was dropped outright.
> Stages 8, 10, 14 and 15 carry the label on that basis.
>
> **The label does not mean "implemented in a script."** Stage 9 runs
> `lint_installed_divergence()` and carries no label, because ongoing divergence
> has no spent migration behind it. Do not re-derive the label from which stages
> happen to be script-backed, and do not apply it to a stage — an environment
> probe, a presence check — whose subject is the current state of the machine
> rather than the residue of a version change.

### Stage 8: Stale de-scoped rule sweep (post-boundary)

> [!constraint] Read-Only — bare doctor only recommends
> Stage 8 runs `sweep_stale_descoped_rules()` standalone. It READS
> `.claude/rules/**` and the plugin's shipped `references/`, then prints a
> report. It writes nothing and deletes nothing. The one-shot de-scope migration
> in `/planwise upgrade` is spent for any install already past the de-scope
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

When `$ARGUMENTS` contains `--prune-stale`, this is one of the three doctor paths
that mutate (the others are `--prune-upgrade-leftovers`, Stage 14b, and
`--create-feedback-dir`, Stage 17b). Run the writer:

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

Every recommendation above routes the divergence through the documented
resolution flow (`/planwise upgrade`, or the customization-relocation
callout) rather than sidestepping it with a sidecar note — the Upgrade /
doctor application of [do-the-hard-things.md](../references/do-the-hard-things.md)'s
Stage Applications table.

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
      reason:  {untouched shipped agent, orphaned by the dropped mirror | byte-exact copy of a previously shipped body of this agent — stale shipped content, not a customization | stale/reorganized subset of the shipped agent}
      action:  remove with /planwise doctor --prune-stale
  ! {filename}.md   PRESERVE
      size:    {N} lines (~{X} tokens)
      reason:  {genuine customization (unique content) [; shipped body is smaller than the installed copy — a content-relocating refactor makes a stale copy look customized, and no previously shipped body matched | the shipped agent-history manifest is unavailable] | matcher tolerated installed-only content | shipped reference unavailable/unreadable | installed file unreadable — cannot classify}
      action:  keep in place — customization detected, do NOT delete

Total REMOVABLE orphaned agent mirror(s): {N} of {M} found.
```

If the sweep returns nothing: `No orphaned agent mirrors found — install has
none of the formerly mirrored agents left, or they already match shipped.`

---

### Stage 11: Plans Index Drift Audit

> [!constraint] Read-Only — audit only recommends
> Stage 11 runs `reconcile_plans.py --json` standalone, reading the plans
> index (`{plans_dir}/{plans_index}`). It writes nothing unless the user
> explicitly consents to reconcile — the audit itself never mutates. On
> consent, `--write` regenerates the whole index through the generator and
> drops any orphan row.

Always-on (independent of Token Saver) — auditing plans-index consistency is
doctor's purpose, so this check has **no `--no-check` escape hatch** (contrast
`/planwise list`, where the same detect pass IS skippable for a fast glance).

Run the index-drift audit procedure in
[`references/index-drift-audit.md`](../references/index-drift-audit.md)
against the **plans** index (`reconcile_plans.py`, banner `planwise doctor —
plans index drift audit`). This is the same detect pass `/planwise list`
runs, reused here alongside doctor's other health checks — neither handler
re-implements the comparison.

Read the exit code and the JSON `status`, then report exactly one of these
outcomes. The exit table is in the canonical's Plans binding.

- **Exit 0 (`ran`) — a real verdict.** Print the canonical banner, then the
  drift and anomaly lines or `No drift detected`. Only this outcome may print
  `No drift detected`.
- **Exit 3 — audit could not run.** Print the script's own lines (`Drift audit
  could not run: 0 of {total} rows compared` or `Drift audit incomplete:
  {compared} of {total} rows compared`) under the doctor banner. Never print
  `No drift detected`. When the JSON `status` is `could-not-run` and `drifts`
  holds `missing-row` records, offer `reconcile_plans.py --write`, and say
  that it regenerates the whole file and drops every line the render does not
  produce. On `incomplete`, offer no write: regenerating would drop the
  unparsed lines the script listed.
- **Exit 2 — legacy-shaped plans index.** Print the script's line and name
  `/planwise upgrade`. Never print `No drift detected`. Offer no write.
- **Exit 1 — index not found.** In detect mode, print the script's
  `Error: Plans index not found at {index}` line.

After a consented `reconcile_plans.py --write`, exit 1 has a different
meaning: the index was written and the tree has an anomaly. Report
`Reconciled {N} row(s).` and the anomaly, not a failed write.

---

### Stage 12: Backlog Index Archival Drift Audit

> [!constraint] Read-Only — audit only recommends
> Stage 12 runs `reconcile_backlog.py --json` standalone. It reads each item
> file's frontmatter status and location under `{backlog_dir}/` and its
> `Archive/`, never the backlog index. The audit itself never mutates. It moves
> files only if the user explicitly consents to reconcile. The consented
> `--write` moves each closed item file into `Archive/` and never writes the
> index. After a move, run `generate_backlog_index.py --write` so the index
> links follow the moved files.

Always-on (independent of Token Saver) — auditing backlog-index consistency is
doctor's purpose, so this check has **no `--no-check` escape hatch** (contrast
`/planwise backlog`, where the same detect pass IS skippable for a fast triage).

Run the index-drift audit procedure in
[`references/index-drift-audit.md`](../references/index-drift-audit.md)
against the **backlog** index (`reconcile_backlog.py`, banner `planwise
doctor — backlog index archival drift audit`) — the archival state-coupling
rationale lives there. This is the backlog-index analogue of the Stage 11
plans-index drift audit; neither re-implements the other's comparison.

---

### Stage 13: Lessons Index Counter Drift Audit

> [!constraint] Read-Only — audit only recommends
> Stage 13 runs `generate_lessons_index.py --check --json`, standalone,
> reading the lessons index (`{lessons_dir}/{lessons_index}`), the lesson
> files in that directory and its `Archive/`. It writes nothing unless the
> user explicitly consents to reconcile — the audit itself never mutates.

Always-on (independent of Token Saver) — auditing index consistency is doctor's
purpose, so this check has **no `--no-check` escape hatch**. Skip the stage
entirely only when `config.yaml` declares no `project.lessons_dir` (a project
with no lessons scaffolding has no counter to audit); report
`Lessons index: not configured — audit skipped`.

Run the index-drift audit procedure in
[`references/index-drift-audit.md`](../references/index-drift-audit.md) §
Lessons against the **lessons** index (`generate_lessons_index.py --check
--json`, banner `planwise doctor — lessons index drift audit`) — the
lessons-index binding there carries the drift-class specifics: the
generator's own classes as it names them, including `stale-counter` (off
the forward-only counter floor) and the file-level anomalies `extra-row`,
`missing-row`, and `duplicate-id` that this same `--check --json` run
reports. This is the lessons-index analogue of Stages 11 and 12; none
re-implements another's comparison.

---

**Continued in Part 2** (Stages 14-21) and **Part 3** (Steps 4-8) — see the pointer table above.
