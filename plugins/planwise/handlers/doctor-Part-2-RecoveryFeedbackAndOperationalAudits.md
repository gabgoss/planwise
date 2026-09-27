# Handler: /planwise doctor — Part 2: Recovery, Feedback, and Operational Audits

**Part 2 of 3.** This handler spans three files, split by topic because the combined text exceeds the Read-tool page cap. Each Stage keeps its own identifier wherever it lands, so an existing `Stage N` reference still names exactly one section — only the filename that holds it changes. See [`doctor.md`](doctor.md) for the full three-part pointer table, the Config Gate, the Preflight version-state gate, and Stages 8-13.

This file covers **Stages 14-20**: the upgrade recovery-leftover sweep, the settings-grant sweep, the feedback capability and directory probes, the task-tools availability advisory, and the backlog body-status and index-shape audits. **Part 3** ([`doctor-Part-3-TokenSaverAndBookkeepingReadGates.md`](doctor-Part-3-TokenSaverAndBookkeepingReadGates.md)) covers Steps 4-8: the Token Saver audits, the capture self-containment scan, and the bookkeeping index read-gate scan.

---

### Stage 14: Upgrade recovery-leftover sweep (post-boundary)

> [!constraint] Read-Only — bare doctor only recommends
> Stage 14 runs `sweep_upgrade_leftovers()` standalone. It READS
> `{planwise_root}/upgrade-backups/`, `upgrade-transfers/`, and
> `upgrade-conflicts/` (including the latter's nested `issue-drafts/`
> subfolder), then prints a report. It writes nothing and deletes nothing.
> To actually remove what it reports, the user opts in with the separate
> writer `/planwise doctor --prune-upgrade-leftovers` (Stage 14b below) — a
> DISTINCT flag from `/planwise doctor --prune-stale` (Stage 8b, in
> [`doctor.md`](doctor.md)): that writer targets a completely different
> artifact class (de-scoped rules and orphaned agent mirrors under
> `.claude/rules|agents/`) and already logs into
> `upgrade-backups/prune-{date}/`; reusing that name here would make one
> flag mean two unrelated things.

Always-on (independent of Token Saver). The sweep walks every version-pair
directory a completed `/planwise upgrade` may have left behind — these
accumulate per upgrade COUNT, not version distance, since nothing purges
them on its own — and classifies each one (or, for
`upgrade-conflicts/{pair}/`, each of its three separately-tracked content
kinds — they never share one class) into one of the four disposition
classes the `Recovery artifacts:` banner (`/planwise upgrade` Step 3)
already reports at upgrade time:

- **action-required** — unresolved conflict sidecars (`*.new` files under
  `upgrade-conflicts/{pair}/`) and the pair's `issue-drafts/` subfolder.
  *Never offered for deletion here* — resolve per `handlers/upgrade.md`
  Step 4.
- **review-then-discard** — transferred customizations under
  `upgrade-transfers/{pair}/`, awaiting the user's re-homing decision.
  *Never offered for deletion here.*
- **safe-to-discard** — pre-change backups under `upgrade-backups/{pair}/`,
  once the user is satisfied with the upgrade. *Prunable.*
- **inert** — a consumed verdict cache (`verdicts.json.consumed`) under
  `upgrade-conflicts/{pair}/`. *Prunable.*

Print verbatim:

```
planwise doctor — upgrade recovery-leftover sweep

Leftover recovery artifacts across {N} version pair(s):
  ~ {pair}   {surface}   {klass}
      path:    {absolute path}
      size:    {N} file(s), {B} {B|KiB|MiB}, {D}d old
      meaning: {the class's one-line meaning}
      action:  {remove with /planwise doctor --prune-upgrade-leftovers | resolve per handlers/upgrade.md Step 4 — never auto-pruned}

Total prunable (inert/safe-to-discard) leftover(s): {N} of {M} found, {B} {B|KiB|MiB} reclaimable.
```

The size line carries a file count **and** a byte total, because the two answer different questions. The count says how much there is to review. Only the byte total says how much a prune reclaims, and the two do not track each other — one transferred rule body can outweigh a hundred spent cache markers.

The reclaimable total on the last line covers the **prunable** findings only. Reporting it over every finding would overstate what the Stage 14b writer recovers: it never deletes an action-required or review-then-discard surface, however large.

If the sweep returns nothing: `No leftover recovery directories found — no
version-pair backups, transfers, or conflict artifacts on disk.`

### Stage 14b: `--prune-upgrade-leftovers` (opt-in writer)

When `$ARGUMENTS` contains `--prune-upgrade-leftovers`, this is another doctor
path that mutates (alongside `--prune-stale`, Stage 8b in
[`doctor.md`](doctor.md), and `--create-feedback-dir`, Stage 17b below). Run
the writer:

```bash
python "{plugin_root}/scripts/init_project.py" --prune-upgrade-leftovers --project-root "{project_root}"
```

Before invoking it, ask one `AskUserQuestion` per PRESENT prunable class
(*inert*, *safe-to-discard* — never per file), tagged
`<!-- AUTO-MODE: convenience -->` with an inferred default of **skip-all**
in unattended runs (state the inference inline) — the same per-class
confirm contract `handlers/upgrade.md` Step 4.3 uses for its own cleanup
offer. *action-required* and *review-then-discard* findings are never
offered here at all; they only ever route to Step 4.

It deletes ONLY the *inert* and *safe-to-discard* findings from Stage 14's
sweep — an *action-required* or *review-then-discard* finding is never
touched, no matter what. **This is the one-sentence distinction from
`--prune-stale` (Stage 8b): that writer prunes de-scoped rules and orphaned
agent mirrors under `.claude/rules|agents/`, logging into
`{planwise_root}/upgrade-backups/prune-{YYYY-MM-DD}/`; this writer prunes
version-pair recovery leftovers under `upgrade-backups/`,
`upgrade-transfers/`, and `upgrade-conflicts/`, logging into its own
`{planwise_root}/upgrade-prune-logs/upgrade-leftovers-{YYYY-MM-DD}/`
root — the two logs never collide, and neither opt-in flag is an alias
for the other.**

> [!constraint] The log root is deliberately OUTSIDE every swept root
> This writer prunes surfaces that live *inside* `upgrade-backups/`, so a log
> folder placed there would copy a pruned pair to
> `upgrade-backups/{log}/upgrade-backups/{pair}` and delete the original —
> reclaiming no space and hiding the copy from the Stage-14 sweep's `*-to-*`
> glob permanently, leaving the surface neither gone nor reportable. Keeping
> the log root disjoint from every swept root is what makes a prune actually
> prune. Do not "tidy" it back under `upgrade-backups/`.

If an `upgrade-leftovers-{YYYY-MM-DD}/` folder already exists (a second run
the same day), the run gets its own `-2`, `-3`, ... suffix instead — an
earlier run's log is never overwritten. A run with nothing prunable creates
no folder at all.

Every pruned path is first copied into that same run's folder (mirroring
its original location relative to `{planwise_root}`), so a prune is
recoverable. A failed **copy** leaves the original in place
(`REMOVE_FAILED`) rather than risk deleting without a backup. A **removal**
that fails part-way keeps the copy — `rmtree` is not atomic, and on a
locked or read-only file it can stop mid-tree, at which point that copy is
the only surviving record of whatever was already deleted; the log names
its path so the user restores from it rather than re-running.

Pass `--prune-classes` to narrow the run to the classes the user actually
confirmed (e.g. `--prune-classes inert` to drop consumed verdict caches
while keeping backups). It can only narrow: *action-required* and
*review-then-discard* stay undeletable whatever is passed.

> [!practice] Pruning backups costs the formerly-managed signal
> The *safe-to-discard* backups double as the pre-image mirrors that the
> refresh loop's formerly-managed detection uses as its only durable
> prior-managed-set evidence. After they are pruned, a file the plugin stopped
> managing reports as generic untracked instead. The copies survive under the
> prune log root, but the detector does not look there — so when a user is
> still reconciling what the upgrade changed, offer `--prune-classes inert`
> and leave the backups for a later pass.

Pass the script's stdout through and point the user at the
`PRUNED-LEFTOVERS.md` audit log.

### Stage 15: Settings-grant sweep (post-boundary)

> [!constraint] Read-Only — bare doctor only recommends
> Stage 15 runs `_sweep_settings_grants()` standalone. It READS
> `.claude/settings.json` and `.claude/settings.local.json` (when present),
> then prints a report. It writes nothing and rewrites nothing. To actually
> normalize a grant, run `/planwise upgrade` — its Step 4.4 offer is the only
> writer; doctor never mutates.

Always-on, independent of Token Saver. **This is DISTINCT from the Preflight
plugin version-state gate in [`doctor.md`](doctor.md): that gate reads
`config.yaml`'s `plugin_root:` pin and checks whether the one root the
plugin currently resolves scripts through is live and current; this stage
instead reads `.claude/settings.json`'s `permissions.additionalDirectories`
— the consumer's own Claude Code read-permission grants — for entries in the
plugin-cache path family.** It mirrors `handlers/upgrade.md` Step 4.4's
classification and never restates the target-shape doctrine already
documented at `handlers/init-fallback.md`'s grant step / `handlers/init.md`:

- **version-agnostic parent** — the entry already grants the plugin-family
  root. Correct target shape; no finding reported.
- **version-pinned live** — the entry names a version-pinned child directory
  that still exists on disk. Reported with a normalization recommendation.
- **version-pinned dangling or orphan-marked** — the entry names a
  version-pinned child directory that no longer exists on disk, that still
  exists but carries an `.orphaned_at` marker, or that exists and is
  superseded by the currently-pinned version. Reported with the
  dangling/orphaned path named and the same normalization recommendation.

The three conditions are tested in that order, and the marker check outranks
liveness deliberately. The plugin cache manager marks a superseded version
with an `.orphaned_at` file rather than deleting it at once, so a marked
directory is one the reaper will collect. Reporting it as merely superseded —
or as `version-pinned live`, which is what a config still pinning it would
otherwise produce — understates a grant that is about to dangle.

Print verbatim:

```
planwise doctor — settings-grant sweep

Plugin-cache grants needing normalization across {N} settings file(s):
  ~ {settings_path}   {entry}
      class:     {klass}
      detail:    {detail}
      recommend: run /planwise upgrade (offers normalization to the parent grant) — doctor is read-only and never rewrites settings

Total grant(s) needing normalization: {N} found.
```

If the sweep returns nothing: `No plugin-cache grants found needing
normalization — settings already grant the version-agnostic parent, or no
plugin-cache grant exists yet.`

---

### Stage 16: Feedback capability probe

> [!constraint] Read-Only — probes, never installs
> Stage 16 runs two capability checks against the environment and reads
> `config.yaml`'s `feedback:` block. It installs nothing, authenticates
> nothing, and writes nothing. To install the GitHub CLI, run `/planwise
> init` or `/planwise upgrade` — their offer steps are the only writers;
> doctor never mutates.

Always-on, independent of Token Saver. `/planwise feedback` — and the
upstream options in `upgrade`, `lessons capture`, and `backlog` — post
through the shared engine at
[`references/feedback-submission.md`](../references/feedback-submission.md),
whose gate chain degrades to a local draft when any gate fails. That
degradation is deliberate and never blocks, which also means a consumer can
run for a long time without discovering that their reports never left the
machine. This stage surfaces the gate state up front rather than at the
moment someone tries to file a report.

> [!constraint] The engine defines the gates; this stage only reports them
> The engine is the ONE place the gate chain is specified, and its consumers
> delegate rather than re-specify. So this stage does **not** restate what each
> gate tests or how to evaluate it — read
> [`references/feedback-submission.md`](../references/feedback-submission.md)
> § Gate Chain for that, and evaluate gates 1, 3 and 4 exactly as it defines
> them. What belongs here, and only here, is the **remedy line** each unmet
> gate prints: that is doctor's own reporting, which the engine does not own.
> Gate 2 (interactive session) and gate 5 (explicit consent) are properties of
> a post attempt, not of the install, so a read-only probe cannot evaluate them
> and never reports on them.

Evaluate gates 1, 3 and 4 per the engine, in its own gate order, and report each
unmet one with the matching line:

| Gate (defined by the engine) | Reported when unmet |
|---|---|
| 1 — `feedback.enabled` | `feedback.enabled is false — /planwise feedback drafts locally and posts nothing` |
| 3 — `gh` on PATH | `gh not found on PATH — install from https://cli.github.com/, or run /planwise upgrade to be offered the install` |
| 4 — `gh` authenticated | `gh is installed but not authenticated — run: gh auth login` |

`{gh_version_when_present}` is the version string `gh --version` reports once gate
3 has resolved. It is a reporting detail of this stage, not part of the gate —
the engine's gate 3 tests resolvability and nothing more.

Print verbatim:

```
planwise doctor — feedback capability probe

  feedback.enabled:  {true|false}
  gh on PATH:        {yes|no}  {gh_version_when_present}
  gh authenticated:  {yes|no|n/a — gh absent}

  {one remedy line per unmet gate, from the table above}

Upstream posting: {ENABLED — reports post directly | DRAFT-ONLY — reports are saved to {planwise_root}/{feedback_dir}/ and must be filed by hand}
```

Advisory only. Draft-only is a supported configuration, not a fault — this
stage reports the state so the choice is deliberate, and never fails the
doctor run.

---

### Stage 17: Feedback directory presence check

> [!constraint] Read-Only — bare doctor only recommends
> Stage 17 checks whether the feedback directory resolved from `config.yaml`'s
> `project.feedback_dir` (absent → default `Feedback`) exists on disk. It
> READS `config.yaml` and the filesystem, then prints a report. It writes
> nothing. To actually create the directory, the user opts in with the
> separate writer `/planwise doctor --create-feedback-dir` (Stage 17b below)
> — the same opt-in-writer shape as `--prune-stale` (Stage 8b, in
> [`doctor.md`](doctor.md)) and `--prune-upgrade-leftovers` (Stage 14b) above.

Always-on, independent of Token Saver. A fresh `/planwise init` creates this
directory alongside the plans/backlog/lessons directories, so this stage
exists for every OTHER population an install can reach: a project whose
config predates the key, or whose directory was removed by hand after
creation. Resolve `{feedback_dir_path} = {planwise_root}/{project.feedback_dir}`
(from the Config Gate) and check it with **Glob**.

Print verbatim:

```
planwise doctor — feedback directory presence check

  feedback directory:  {feedback_dir_path}
  exists:               {yes|no}

  {remedy line, only when absent:}
  ! feedback directory is absent — the first draft written there will fail.
      action: create it with /planwise doctor --create-feedback-dir,
              or run /planwise init / /planwise upgrade (both create it)
```

If the directory exists: `Feedback directory: {feedback_dir_path} — present.`

### Stage 17b: `--create-feedback-dir` (opt-in writer)

When `$ARGUMENTS` contains `--create-feedback-dir`, this is another doctor
path that mutates (alongside `--prune-stale` and `--prune-upgrade-leftovers`
above). Ask one `AskUserQuestion` (`<!-- AUTO-MODE: convenience -->`,
inferred default **skip** in unattended runs): "Create the missing feedback
directory at `{feedback_dir_path}`?" On confirm, use **Bash** to create ONLY
that single directory (`mkdir -p {feedback_dir_path}`) — the same
Bash-for-directory-creation scope [init.md](init.md)'s Tool Usage Rules
already establish. This never touches an existing directory's contents,
never renames, never deletes, and never runs when Stage 17 already reported
the directory present. Report the path created. On decline, or when no
interactive answer is available, leave the directory absent and repeat the
Stage 17 remedy line.

---

### Stage 18: Task-tools availability advisory (post-boundary)

> [!constraint] Read-Only — bare doctor only reports
> Stage 18 reads nothing on disk. It inspects this session's own tool list
> and prints one of two blocks. It never edits `.claude/settings.json`.

Always-on, independent of Token Saver, and prose-only: the doctor script
cannot see the session's tool list, so you perform the check. Two tool
families share a word. The Agent tool spawns a subagent. The Task tools
(`TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`) are the checklist shown
by `Ctrl+T`, and `/planwise run` uses them under Track B
(`references/session-execution-protocol.md` §5). Since Claude Code 2.1.233
they are absent on Opus 4.8, Sonnet 5, Fable 5, Mythos 5 and newer models
unless the project opts in.

Check whether `TaskCreate` is in your tool list, then print verbatim.

When present:

```
planwise doctor — task tools

Task tools: present — /planwise run tracks progress in the task list (Ctrl+T) and in Recovery (Track B).
```

When absent:

```
planwise doctor — task tools

Task tools: absent — Claude Code omits them on this model family.
  to enable:  run /planwise upgrade — its Step 4.6 offers to add
              "CLAUDE_CODE_ENABLE_TODO_TOOLS": "1" to .claude/settings.json's
              env block, then start a new session
  in force:   Recovery-only tracking (Track A)
  doctor is read-only and never edits settings
```

---

### Stage 19: Backlog Item Body-Status Audit

> [!constraint] Read-Only — audit only recommends
> Stage 19 runs `reconcile_backlog.py --body-status --json` standalone. It
> reads each item file under `{backlog_dir}/` and its `Archive/`, never the
> backlog index. The audit itself never mutates. It strips lines only if the
> user explicitly consents. The consented `--body-status --write` removes each
> drifted `**Status:**` line from the item's header block and changes no
> frontmatter, so no index regeneration follows.

Always-on (independent of Token Saver) — keeping each item's frontmatter the
only status field is doctor's purpose, so this check has **no `--no-check`
escape hatch** (contrast `/planwise backlog`, where the same detect pass IS
skippable for a fast triage).

Run the index-drift audit procedure in
[`references/index-drift-audit.md`](../references/index-drift-audit.md)
with its body-status binding (banner `planwise doctor — backlog item
body-status drift audit`) — the header-block rule, the anomaly classes and
the consent prompt live there. Doctor runs this as a standing check, not a
one-shot migration: an older item writer can re-introduce the line after a
corpus was cleaned. This is the within-file analogue of the Stage 12
archival audit; neither re-implements the other's comparison.

---

### Stage 20: Backlog Index Shape Audit

> [!constraint] Read-Only — audit only reports
> Stage 20 runs `migrate_backlog_index.py --report --json` standalone. It
> classifies the on-disk index shape and measures every changelog file, and
> it never writes — remediation runs only when the user invokes
> `/planwise upgrade` or the migrator's own repair flags directly.

Always-on (independent of Token Saver) — auditing backlog-index shape is
doctor's purpose, so this check has **no `--no-check` escape hatch**.

```bash
python {plugin_root}/scripts/migrate_backlog_index.py --config {planwise_root}/config.yaml --report --json
```

Print `shape`, `changelog`, `items.without_frontmatter`,
`items.partial_frontmatter`, `dependencies.edges_missing_from_blocks`,
`dependencies.soft_dependency_bullets`, `row_mismatches`,
`ready_with_all_repairs`, and `would_refuse` from the JSON. Print every
`changelog_files` entry whose `level` is `WARN` or `OVER`.

When `changelog_over_budget` is `true`, print: "changelog file(s) over the
read budget — `/planwise upgrade` re-splits them with backups, or run
`migrate_backlog_index.py --config {planwise_root}/config.yaml
--split-changelog`".

Then one verdict line by `shape`. `generated`: "generated shape, nothing to
do" when every changelog file is within budget. `legacy`: the counts above,
then "run `/planwise upgrade` to migrate automatically; backups land under
`upgrade-backups/`". `unrecognized`: the classifier's reason, then "left
untouched; see the migrator's `--report` output".

---

**Continued in Part 3** (Steps 4-8) — see [`doctor.md`](doctor.md) for the full pointer table.
