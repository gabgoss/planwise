# Handler: /planwise doctor — Part 2: Recovery, Feedback, and Operational Audits

**Part 2 of 3.** This handler spans three files, split by topic because the combined text exceeds the Read-tool page cap. Each Stage keeps its own identifier wherever it lands, so an existing `Stage N` reference still names exactly one section — only the filename that holds it changes. See [`doctor.md`](doctor.md) for the full three-part pointer table, the Config Gate, the Preflight version-state gate, and Stages 8-13.

This file covers **Stages 14-23**: the upgrade recovery-leftover sweep, the settings-grant sweep, the thrifty-sonic env var sweep, the feedback capability and directory probes, the task-tools availability advisory, the backlog body-status and index-shape audits, the lessons index-shape audit, the plans index-shape audit, and the style-rule audit. **Part 3** ([`doctor-Part-3-TokenSaverAndBookkeepingReadGates.md`](doctor-Part-3-TokenSaverAndBookkeepingReadGates.md)) covers Steps 4-8: the Token Saver audits, the capture self-containment scan, and the bookkeeping index read-gate scan.

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
  *Never offered for deletion here* — resolve per
  `handlers/upgrade-Part-3-BannerAndConflictResolution.md` Step 4.
- **review-then-discard** — transferred customizations under
  `upgrade-transfers/{pair}/`, awaiting the user's re-homing decision.
  *Never offered for deletion here.* The report adds a read-only `review:`
  line that compares each transfer file with the current shipped file and
  counts the files now upstream, still unique, and other. Resolve them per
  `handlers/upgrade-Part-3-BannerAndConflictResolution.md` Step 4.1 case C.
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
      review:  {N} now upstream, {M} still unique, {K} other (compared with the current shipped files, read-only)   [upgrade-transfers rows only]
      action:  {remove with /planwise doctor --prune-upgrade-leftovers | resolve per handlers/upgrade-Part-3-BannerAndConflictResolution.md Step 4 — never auto-pruned | resolve per handlers/upgrade-Part-3-BannerAndConflictResolution.md Step 4.1 case C — never auto-pruned}

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
confirm contract `handlers/upgrade-Part-3-BannerAndConflictResolution.md`
Step 4.3 uses for its own cleanup
offer. *action-required* and *review-then-discard* findings are never
offered here at all. *action-required* findings route to Step 4, and
*review-then-discard* findings route to Step 4.1 case C.

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
plugin-cache path family.** It mirrors
`handlers/upgrade-Part-3-BannerAndConflictResolution.md` Step 4.4's
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

### Stage 15b: Thrifty-sonic env var sweep (post-boundary)

> [!constraint] Read-Only — bare doctor only recommends
> Stage 15b runs `_sweep_thrifty_sonic()` standalone. It READS the project's
> `.claude/settings.json` and the user-global `~/.claude/settings.json`,
> whatever the install scope, then prints a report. It never reads
> `.claude/settings.local.json`. It writes nothing. To set the variable, run
> `/planwise upgrade` — its Step 4.7 offer is the only writer.

Always-on, independent of Token Saver. The sweep checks that
`env.CLAUDE_CODE_THRIFTY_SONIC` equals `"false"` in both files. A file that
already holds `"false"` yields no finding. Every other file lands in one class:

| Class | Meaning |
|---|---|
| `missing` | the file, the `env` block, or the key is absent |
| `wrong value` | the key holds anything other than `"false"` |
| `invalid JSON` | the file does not parse, so doctor reports it and repairs nothing |

Print verbatim:

```
planwise doctor — thrifty-sonic env var sweep

CLAUDE_CODE_THRIFTY_SONIC drift in {N} of 2 settings file(s):
  ~ {settings_path}
      class:     {klass}
      detail:    {detail}
      recommend: run /planwise upgrade (Step 4.7 offers to set it) — doctor is read-only and never rewrites settings
```

If the sweep returns nothing: `CLAUDE_CODE_THRIFTY_SONIC=false is set in both the
user and project settings files.`

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
| 3 — `gh` resolvable | `gh not found on PATH or at a known install location — install from https://cli.github.com/, or run /planwise upgrade to be offered the install` |
| 4 — `gh` authenticated | `gh is installed but not authenticated — run: gh auth login` |

Gate 3 resolves `gh` by the engine's own order: PATH first, then the known install
locations. When gate 3 resolves through a known install location and not through PATH,
the gate is met. Print a note line in place of a remedy line:
`gh found at {gh_path}, not on this session's PATH — a new terminal will resolve it`.
Gate 4 runs `"{gh_path}" auth status`, so a `gh` found by full path is judged on its
real auth state.

`{gh_version_when_present}` is the version string `{gh_path} --version` reports once gate
3 has resolved. It is a reporting detail of this stage, not part of the gate —
the engine's gate 3 tests resolvability and nothing more.

Print verbatim:

```
planwise doctor — feedback capability probe

  feedback.enabled:  {true|false}
  gh resolvable:     {yes — on PATH|yes — at {gh_path}|no}  {gh_version_when_present}
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

### Stage 21: Lessons Index Shape Audit

> [!constraint] Read-Only — audit only reports
> Stage 21 runs `migrate_lessons_index.py --report --json` standalone. It
> classifies the on-disk index shape and measures every lesson file it can
> resolve, and it never writes — remediation runs only when the user invokes
> `/planwise upgrade` or the migrator's own repair flags directly.

Always-on (independent of Token Saver) — auditing lessons-index shape is
doctor's purpose, so this check has **no `--no-check` escape hatch**.

```bash
python {plugin_root}/scripts/migrate_lessons_index.py --config {planwise_root}/config.yaml --report --json
```

Print `shape`, `changelog`, `changelog_resplit`, `changelog_renumber`,
`changelog_oversized`, `promotion_log`, `companion`,
`lessons.without_frontmatter`, `lessons.partial_frontmatter`,
`lessons.titles_needing_quotes`, `lessons.status_mismatches`, `cells.units`,
`prose_sections`, `ready_with_all_repairs`, and `would_refuse` from the
JSON. `changelog_resplit` is computed by the same `lessons_changelog.plan_split`
the upgrade routine calls, and only on a `generated` index, where the
routine calls it, so this stage and the upgrade banner can never disagree.
It reads `not_applicable` on any other shape.

`changelog_resplit` takes one of five values:

- `within_budget`: every changelog file is within its budget, and the entry
  numbers strictly descend from the newest entry to the oldest.
- `would_split`: the next upgrade rewrites the changelog. It re-splits an
  over-budget family, renumbers a family whose numbers do not strictly
  descend, or both. `changelog_renumber` is `true` when it renumbers: by
  position, so the oldest entry becomes Entry 1 and the newest gets the
  highest number. A family numbered in order is never renumbered.
- `converged`: a file stays over its budget only because one entry is
  larger than the budget on its own, and no split can do better. The
  upgrade writes nothing. `changelog_oversized` names each such file, its
  entry, its tokens and its budget.
- `refused`: the changelog carries text the parser cannot place in an
  entry. The reason is in `would_refuse`.
- `not_applicable`: the index is not `generated`, so the migration writes
  the changelog itself.

Then one verdict line by `shape`. `generated`: by `changelog_resplit` —
`within_budget` stays "generated shape, nothing to do"; `converged` says
"generated shape, nothing to do" and prints each `changelog_oversized`
entry; `would_split` says "the next `/planwise upgrade` re-splits the
changelog; backups land under `upgrade-backups/`", or, when
`changelog_renumber` is `true`, "the next `/planwise upgrade` renumbers the
changelog entries by position (the oldest becomes Entry 1); backups land
under `upgrade-backups/`"; `refused` prints the report's own reason (from
`would_refuse`) and says "`/planwise upgrade` will refuse until that
changelog line is fixed". `legacy`: the counts above, then "run
`/planwise upgrade` to migrate automatically; backups land under
`upgrade-backups/`". `unrecognized`: the classifier's reason, then "left
untouched".

---

### Stage 22: Plans Index Shape Audit

> [!constraint] Read-Only — audit only reports
> Stage 22 runs `migrate_plans_index.py --report --json` standalone. It
> classifies the on-disk plans index shape and counts what a migration would
> move, and it never writes — remediation runs only when the user invokes
> `/planwise upgrade` or the migrator's own flags directly.

Always-on (independent of Token Saver) — auditing plans-index shape is
doctor's purpose, so this check has **no `--no-check` escape hatch**.

```bash
python {plugin_root}/scripts/migrate_plans_index.py --config {planwise_root}/config.yaml --report --json
```

Print `shape`, `detail`, `index`, `rows`, `comments`, `narrative_cells`,
`attributable`, `unattributed`, `uncarried_lines`, `root_path_rows`, `prefixed_rows`,
`status_changes`, `append_targets`, `ready`, and `would_refuse` from the
JSON. `shape` is `absent`, `generated`, `legacy` or `unrecognized`. A shape
other than `legacy` prints zero counts and `ready` false. `unknown` (with an
`error` field) means the report itself failed.

Then one verdict line by `shape`. `generated`: "generated shape, nothing to
do". `legacy`: the counts above, then "run `/planwise upgrade` to migrate
automatically; backups land under `upgrade-backups/`". `unrecognized`: the
classifier's reason from `detail`, then "left untouched". `absent`: "no plans
index found".

---

### Stage 23: Style Rules

> [!constraint] Read-Only — audit only reports
> Stage 23 runs `run_style_stage()` standalone. It READS `config.yaml`, the two
> `.claude/rules/` trees, the installed copies and the shipped files in
> `references/`, then prints a report. It writes nothing and removes nothing.
> It never changes doctor's exit status. To install, refresh or remove a
> managed copy, run `/planwise upgrade` — doctor never mutates.

Always-on (independent of Token Saver). Two style rules ship with the plugin,
`plain-language.md` and `plain-presentation.md`. Each has its own switch under
`style:` in `config.yaml`. Each is on by default, and the stage reports each
rule in turn.

Procedure, in order, for each of the two rules:

1. Read the rule's key from `style:` in `config.yaml`: `plain_language` for
   `plain-language.md`, `plain_presentation` for `plain-presentation.md`. An
   absent key means on. A malformed or unknown `style:` value never turns a
   rule off. The stage treats the rule as on. It prints one warning on stderr
   for each malformed value or unknown key, before the report lines. A warning
   is not a report line.
2. Look for a same-name copy **anywhere** under the project's `.claude/rules/`
   and under `~/.claude/rules/`. The search is recursive and ignores case in the
   file name. It excludes only the install target. The other scope's managed copy
   (`rules/planwise/<file>` in the other scope) counts as a copy. Every key runs
   this step, also a key that is off, because a copy that still loads costs
   tokens whatever the key says. At the `user` scope a copy that exists only in
   the project tree does not stop the upgrade from installing the global copy.
   At every other scope any copy stops it.
3. Find the installed copy under `rules/planwise/` in the install scope's
   directory: `~/.claude/` for the `user` scope, the project's `.claude/` for
   every other scope.
4. Compare the installed copy with the shipped file in `references/`. The copy
   **differs** when its text is not the shipped text. A `paths:` difference
   counts as a difference, and a line-ending or BOM difference does not. Doctor
   uses the same comparison as `/planwise upgrade`, so the state it prints
   predicts what the upgrade does to the same tree. A stale copy that is an
   older subset of the shipped file differs, and the upgrade calls it
   customized.
5. Measure bytes, lines and tokens. The figures come from the installed copy
   when one exists, else from the single external copy that stops the upgrade,
   else from the shipped file.

To confirm a finding by hand, use `Glob` to list the same-name files under the
two rules trees and `Read` to compare a copy with the shipped file. Use `Grep`
to locate a line in either.

#### The six states

Each rule reports exactly one `state`. Two or more loading copies give
`DUPLICATE`. That includes the two managed copies, one global and one in the
project, because both load and the rule costs its tokens once per copy.

| State | Meaning | Indented line doctor prints |
|-------|---------|-----------------------------|
| `OK` | Key on, one loading copy, and it is the managed copy with the shipped text (`copy=present`), or it is the only copy and it stops the upgrade from installing at this scope (`copy=external`). That copy may be any same-name file under either rules tree, including the other scope's managed copy under `rules/planwise/` | none when `copy=present`. When `copy=external`: `  The rule loads from <duplicate_paths[0]>. Planwise installs no second copy.` |
| `DUPLICATE` | Key on, and two or more copies load | `  Copies that load: <p1>, <p2>[, <p3>…]. Delete all but one. The rule costs its tokens once per copy until you do.` |
| `CUSTOMIZED` | Key on, the managed copy is the only loading copy, and it differs from the shipped file | `  The installed copy differs from the shipped file. Doctor treats it as your customization, not an error.` |
| `MISSING` | Key on, and no copy stops the upgrade from installing the rule | `  The key is on but no copy is installed. Run /planwise upgrade.` |
| `OFF` | Key off, and no managed copy is installed | `  The key is off. Confirm this is intended.` |
| `MISMATCH` | Key off, and a managed copy is installed | One of the three lines in the list below |

For `DUPLICATE`, `<p1>` is the installed path when a managed copy is installed.
The entries of `duplicate_paths` follow in order, joined with `, `.

The `MISMATCH` line follows what `/planwise upgrade` does to the installed copy
of a rule whose key is off. It tests the three cases in this order:

1. The installed copy differs from the shipped file. The upgrade keeps an edited
   copy:
   `  The key is off but the installed copy differs from the shipped file. Upgrade keeps an edited copy. Delete it by hand if you no longer want it.`
2. The installed copy is a symlink. The upgrade never removes a symlink:
   `  The key is off but the installed copy is a symlink. Upgrade does not remove a symlink. Delete it by hand.`
3. Otherwise the copy has the shipped text, and the upgrade removes it:
   `  The key is off but a copy is installed. Run /planwise upgrade to remove an untouched copy.`

A `MISSING` result with copies in `duplicate_paths` happens at the `user` scope
when the only copies sit in the project tree. The upgrade installs the global
copy, and the project copies load beside it. Doctor adds this line after the
`MISSING` line. A key that is off adds a line of its own after the `OFF` or
`MISMATCH` line when copies in `duplicate_paths` still load:

```
  Upgrade installs the rule. Copies that will also load: <p1>[, <p2>…].
  Other copies still load: <p1>[, <p2>…]. Upgrade does not remove them.
```

Two more extra lines follow, in any state, in this order. They are extra lines,
not states, so the table above stays at six rows.

```
  The two managed copies carry different edits: <install path> and <other managed path>. Upgrade leaves both unchanged. Merge them by hand.
  <path> is a symlink. Upgrade never writes through it.
```

- The first line prints only when both managed copies carry different edits.
  Upgrade leaves both copies unchanged, and the user merges them by hand. A key
  that is off never prints it, because the cross-scope sync runs only for a key
  that is on.
- The second line prints once for each symlinked loading copy, because upgrade
  never writes through a symlink. A key that is off checks every copy that
  loads, the installed copy included. When the `MISMATCH` line already names
  the installed copy as a symlink, this line is left out for that copy. Every
  other symlinked copy keeps its line.

Print verbatim:

```
planwise doctor — style rules

Style rule <filename>: key=<on|off> copy=<present|absent|external> state=<STATE> bytes=<n> lines=<n> ~tokens=<n>
{the indented line for the state, then the line for copies that will also load or still load, then the conflict line, then one symlink line per symlinked copy, each only when it applies}

Style rules inject about <sum> tokens in every session, subagents included (global, always-on).
{the ceiling line, only when config.yaml sets the ceiling to a positive integer:}
That is <p>% of token_saver_injection_ceiling (<ceiling>).
```

`copy` is `present` when a managed copy is installed. Otherwise it is `external`
when the state is `OK`, else `absent`. One main line prints per rule. The
summary line prints once. `<sum>` is the token total of every loading copy, each
at its own size and rounded up per copy. A `MISSING` or `OFF` rule with no
loading copy adds 0. A `MISMATCH` rule adds the installed copy. Any copy in
`duplicate_paths` adds its own tokens, whatever the key says. The ceiling line
prints only when the same `config.yaml` that holds the `style:` keys sets
`context.token_saver_injection_ceiling` to a positive integer. An absent key,
a value of 0 and a value that is not an integer print no ceiling line. `<p>` is
`round(100 * sum / ceiling)`, and `<ceiling>` is that value.

The stage never fails doctor. When the check raises an error, the stage prints
one line and no report, and doctor goes on to its exit:

```
Style rules: the check failed: <error>
```

#### Reading the findings

- A key that is off is a finding to confirm, not the normal state. The rules are
  on by default, so `OFF` and `MISMATCH` ask the user to confirm the choice.
- A customized copy is never an error. `CUSTOMIZED` records the user's own edit,
  or a stale copy the upgrade also treats as customized.
- `MISSING` and `MISMATCH`: run `/planwise upgrade`. It reconciles the style
  rules on every run, also when the plugin version is already current. It keeps
  an edited or symlinked copy of a rule whose key is off, so the user deletes
  that copy by hand.
- `OFF` or `MISMATCH` with a "still load" line: the copies it lists load beside
  the managed copy, or alone. The upgrade never removes them.
- `DUPLICATE`: the user chooses which copies to delete, until one copy remains.
  Doctor changes nothing.

---

**Continued in Part 3** (Steps 4-8) — see [`doctor.md`](doctor.md) for the full pointer table.
