# Handler: /planwise upgrade — Part 3: Banner Rendering and Conflict Resolution

**Part 3 of [upgrade.md](upgrade.md).** Part 1 carries the Config Gate and Steps 1-2.7 of the Workflow, and is the file `/planwise upgrade` dispatches to; this part carries Step 3 (Render the banner) through Step 4.6 (Task-tools env var offer) — the banner the upgrade script emits, and every conflict-resolution and post-upgrade offer step that follows it. [`upgrade-Part-2-RecoveryAndReference.md`](upgrade-Part-2-RecoveryAndReference.md) (Part 2) carries the scenario table this file's Step 4 dispositions point back to, and the recovery procedures for a run — or the Config Gate — that cannot complete. Split at this section boundary so each part stays within one Read-tool page.

## Table of Contents

- [Step 3 — Render the banner](#step-3--render-the-banner)
- [Step 4 — Resolve conflicts](#step-4--resolve-conflicts)
- [Step 4.1 — Assisted relocation](#step-41--assisted-relocation)
- [Step 4.2 — Opt-in upstream GitHub issue](#step-42--opt-in-upstream-github-issue)
- [Step 4.3 — Interactive per-class cleanup offer](#step-43--interactive-per-class-cleanup-offer)
- [Step 4.4 — Settings-grant normalization offer](#step-44--settings-grant-normalization-offer)
- [Step 4.5 — GitHub CLI availability offer](#step-45--github-cli-availability-offer)
- [Step 4.6 — Task-tools env var offer](#step-46--task-tools-env-var-offer)

---

### Step 3 — Render the banner

The script emits a structured report. Pass it through verbatim to the user. The output follows this shape:

```
Plugin upgrade: {from} -> {to}
Upgrade pair: {from}-to-{to} (resolved once for this run — matches --upgrade-pair; verdict cache {present|absent}: {planwise_root}/upgrade-conflicts/{from}-to-{to}/verdicts.json)

Config keys added:    {N}  ({list, or "(none)"})

Lessons scaffolding backfilled:           ({omitted entirely when every artifact already exists})
  + {planwise_root}/{lessons_dir}/00-Index-LessonsLearned.md
  + {planwise_root}/{lessons_dir}/00-Changelog-LessonsLearned.md
  + {planwise_root}/{lessons_dir}/00-PromotionLog-LessonsLearned.md
  + {planwise_root}/{lessons_dir}/00-Categorization-By-Domain.md
  …

Backlog index migration:                                   (silent — nothing prints — when the index is already generated and within budget)
  migrated: {index} -> generated hub + {N} shard(s)
    changelog:              {path} + {N-1} part(s) ({N} entries, {N} bytes; each file ≤ {budget} tokens; every footer byte accounted for)
    frontmatter backfilled: {N} item file(s) ({M} had a partial block)
    blocks: edges written:  {N}
    dependency notes moved: {N} bullet(s) into {N} item file(s)
    feature-cell prose moved: {N} unit(s)
    reconciled cells:       {N} ({index-wins|frontmatter-wins}) — {id}.{key}: {frontmatter} -> {index}; …
    ledger:                 {path}
    backups:                {planwise_root}/upgrade-backups/{from}-to-{to}/backlog/ ({N} file(s), listed in DISPOSITIONS.md)
    git tree was dirty:     {yes|no|unknown} (informational — the backup above is the restore point)
    generator --check:      clean
  — or, on a hand-authored index the script refuses to touch:
Backlog index migration: REFUSED (index and item files left untouched)
  reason: {the migrator's own refusal text, verbatim}
  fix:    {the exact edit the refusal names}
          then re-run /planwise upgrade (the migration re-fires on a hand-authored index; nothing else repeats)
  — or, on an index the script cannot classify as either hand-authored or generated:
Backlog index migration: {index} is not a hand-authored or generated index — left untouched
  reason: {the classifier's reason}; inspect it with: {migrate_backlog_index.py --report command}
  — or, on an already-generated index whose changelog grew past the per-file budget:
Backlog changelog: re-split into {N} part(s), each ≤ {budget} tokens; backups: {planwise_root}/upgrade-backups/{from}-to-{to}/backlog/

Lessons index migration:                                   (silent — nothing prints — when the index is already generated)
  migrated: {index} -> generated hub + {N} shard(s)
    changelog:               {path} + {N-1} part(s) ({N} entries)
    promotion log:           {N} row(s) into {N} file(s)
    frontmatter backfilled:  {N} lesson file(s)
    titles quoted:           {N} lesson file(s)
    reconciled status cells: {N} ({index-wins|frontmatter-wins})
    index notes appended:    {N} unit(s) into {N} lesson file(s), {N} already present
    prose sections:          {N} dropped (seed text), {N} relocated
    companion:               regenerated (; hand prose in {path} when a hand-written companion was renamed)
    ledger:                  {path}
    backups:                 {planwise_root}/upgrade-backups/{from}-to-{to}/lessons/ ({N} file(s), listed in DISPOSITIONS.md)
    git tree was dirty:      {yes|no|unknown} (informational — the backup above is the restore point)
    generator --check:       clean
  — or, on an already-generated index whose changelog grew past the per-file budget (state `changelog_split`):
Lessons changelog: re-split into {N} part(s) (main file under {READ_TOKEN_WARN} tokens, each archive part under {READ_PAGE_CAP_TOKENS}; a file holding one larger entry keeps it whole); backups: {planwise_root}/upgrade-backups/{from}-to-{to}/lessons
  — or, when the changelog's entry numbers also do not strictly descend from the newest entry to the oldest (state `changelog_split`):
Lessons changelog: renumbered {N} entries by position (the oldest is Entry 1) and re-split into {N} part(s) (main file under {READ_TOKEN_WARN} tokens, each archive part under {READ_PAGE_CAP_TOKENS}; a file holding one larger entry keeps it whole); backups: {planwise_root}/upgrade-backups/{from}-to-{to}/lessons
  — or, when those numbers are the only defect and every file is within budget (state `changelog_split`):
Lessons changelog: renumbered {N} entries by position (the oldest is Entry 1) across {N} file(s); backups: {planwise_root}/upgrade-backups/{from}-to-{to}/lessons
  — or, on a hand-authored index the script refuses to touch:
Lessons index migration: REFUSED (index and lesson files left untouched)
  reason: {the migrator's own refusal text, verbatim}
  fix:    {the exact edit the refusal names}
          then re-run /planwise upgrade (the migration re-fires on a hand-authored index; nothing else repeats)
  — or, on an index the script cannot classify as either hand-authored or generated:
Lessons index migration: {index} is not a hand-authored or generated index -- left untouched
  reason: {the classifier's reason}; inspect it with: {migrate_lessons_index.py --report command}
  — or, on a backup failure before any write:
Lessons index migration: BACKUP FAILED -- no write was attempted
  {detail}
  fix:    {the exact edit the refusal names}
  — or, on a write failure that rolled every touched file back:
Lessons index migration: WRITE FAILED
  {detail}
  backups: {path} ({note on kept vs. numbered-sibling backups})
  fix:    {the exact edit the refusal names}
  — or, on an unexpected exception the routine caught rather than raised:
Lessons index migration: ERROR (nothing else in this run depends on it)
  {detail}

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
  Nothing above is loaded as a rule or needed for planwise to run — keeping or deleting is housekeeping only.   (printed only when at least one surface exists)

Over-scope advisory: {N} rule(s) still scoped to plan/backlog paths (~{X}K injected per task-runner)
  run `/planwise doctor` for the full report

Plugin version pinned: {to}
Plugin root repointed: {live_plugin_root}

Upgrade complete.
```

> [!practice] The index migration blocks are a pass-through, never a handler procedure
> Pass the `Backlog index migration:` (or `Backlog changelog:`) and `Lessons index migration:` (or `Lessons changelog:`) blocks through verbatim, exactly as the script's own banner prints them — the handler names no repair step of its own. On `refused`, the `fix:` line already carries the re-run instruction; add nothing further to it.

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
Backlog index:           {migrated | changelog re-split | refused | unrecognized | backup failed | write failed | error | already generated}   ({fix} surfaced from the banner above when refused, unrecognized, backup failed, or write failed)
Lessons index:           {migrated | changelog re-split | refused | unrecognized | backup failed | write failed | error | already generated}   ({fix} surfaced from the banner above when refused, unrecognized, backup failed, or write failed)
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

For each conflict in `{planwise_root}/upgrade-conflicts/<from>-to-<to>/` (files preserved in place: conservative handoff mode — `upgrade.customization_handoff` is `report`/`report+issue` — or a transfer/backup/adoption write failed, or the verdict was the degraded not-analyzed stand-in — see upgrade.md Step 2.4, item 7):

1. The user diffs `<destination>.md` against `<destination>.md.new`
2. If the changes are acceptable → overwrite the installed file with the sidecar content (or merge selectively) → delete the `.new` file
3. If the user wants to keep their local edits → run the Step 4.1 case B relocation (the customization was never moved for this file) instead of merging in place

The `upgrade-conflicts/` directory and its `INDEX.md` can be cleaned up once all sidecars are resolved. See Step 4.3 for the aggregated view of this and every other recovery-artifact surface — the consumed verdict cache in this same directory is offered for cleanup there (`inert`), but the sidecars and any `issue-drafts/` stay `action-required` and must be resolved above first.

---

### Step 4.1 — Assisted relocation

Under `upgrade.customization_handoff: report+relocate`, upgrade.md's Step 2.4 writer already performs an automated transfer for the customization-bearing majority: it writes the full installed body to `{planwise_root}/upgrade-transfers/{from}-to-{to}/{filename}` as a **dormant preservation document** (outside `.claude/rules/` — never loaded as a rule; see the file's own provenance header) before adopting the shipped body. Two cases land here, both interactive-only:

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

For any customization — whether already transferred to `{planwise_root}/upgrade-transfers/{from}-to-{to}/` (upgrade.md Step 2.4) or still preserved in place under a Step 4 conflict — that the human confirms `upstream`, submit the issue **through the shared submission engine**: `references/feedback-submission.md` owns the invocation — its gate chain, draft-first render, explicit `-R` target repo, and fallback posture. Do NOT write a `gh` call here: a locally improvised invocation resolves its target from the consumer's own git remote and files planwise issues in the consumer's own project. Gated by **ALL** of:

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

### Step 4.4 — Settings-grant normalization offer

After a successful upgrade, read the project's `.claude/settings.json` (and `.claude/settings.local.json`, if present) for `permissions.additionalDirectories` entries that fall in the plugin-cache path family (the plugin-family root and any of its version-pinned children). Consumer settings files are DATA, never a ship-boundary artifact — this step READS and OFFERS, it never silently rewrites.

> [!practice] Target shape — cross-referenced, not restated
> Grant the plugin-family root once, version-agnostic, never a version-pinned leaf. This doctrine is already landed prose — see `handlers/init-fallback.md`'s grant step ("Apply parent-aware, normalized dedup before modifying `additionalDirectories`") and `handlers/init.md`, which references the same grant. This step is the upgrade-time audit/offer sequel to that init-time writer, not a second, differently-worded copy of its rule.

> [!hazard] A stale grant misdirects reads long before it dangles
> A version-pinned grant does not simply stop working. While the pinned directory still exists, it makes the OLD version's tree the naturally-accessible one. A session that compares an installed artifact against "the shipped reference" can therefore read the superseded copy and never notice. The content it gets is plausible and outdated, which is harder to catch than an outright failure — the comparison has to be redone once someone spots it.
>
> The dangling failure arrives later, and separately. The plugin cache manager marks a superseded version with an `.orphaned_at` file rather than deleting it at once. When the reaper collects that directory, the grant points at nothing and the project loses plugin-file access entirely. That detonates days after the upgrade that caused it, far from any signal connecting the two.
>
> Both harms share one remedy, which is why this step classifies live pins and dangling pins alike rather than only the broken ones. The family root covers every version, survives every upgrade, and needs no refresh.

Classify every matching entry:

| Class | Shape | Offered action |
|---|---|---|
| `version-agnostic parent` | Entry already equals (or covers) the plugin-family root | None — already the correct target shape |
| `version-pinned live` | Entry names a version-pinned child directory that still exists on disk | Offer normalization to the parent grant |
| `version-pinned dangling or orphan-marked` | Entry names a version-pinned child directory that no longer exists on disk, or exists but is superseded by the currently-pinned version | Offer normalization to the parent grant, naming the dangling/orphaned path |

The **report always renders**, regardless of consent — every matching entry and its class is printed even when the user declines to act. The **write happens only on explicit interactive approval**: `AskUserQuestion` (`<!-- AUTO-MODE: convenience -->`), inferred default **report-only, change nothing** (stated inline — an unattended/non-interactive run never rewrites `additionalDirectories`). On confirm, apply the same parent-aware, normalized dedup the init-time writer uses — prune the superseded version-pinned entries, append the family root — then read the file back to confirm the write landed. On decline, or when no interactive answer is available, print the report and leave every settings file untouched.

A report that only names the problem leaves an unattended run with nowhere to go, so the report carries its own remedy. After the entry list, print the exact `additionalDirectories` value the settings file should hold — the family root, with the pinned entries dropped:

```json
"permissions": {
  "additionalDirectories": [
    "{plugin_family_root}"
  ]
}
```

Preserve every entry outside the plugin-cache path family in that snippet. Only the pinned children are replaced, never a user's unrelated grant. This is what makes the headless path complete: it reports, it shows the target state, and it changes nothing.

When no `additionalDirectories` entry falls in the plugin-cache path family at all (a pre-parent-aware-writer install, or the family root is already the only entry present), report "No plugin-cache grants found needing normalization." and skip the offer — there is nothing to act on.

---

### Step 4.5 — GitHub CLI availability offer

After a successful upgrade, probe for the GitHub CLI by running `gh --version`. If it resolves, probe the auth state with `gh auth status` and report the installed-but-unauthenticated case exactly as [init.md](init.md) Step 9.5 specifies — one line, no question, never blocking. On exit 0, skip this step silently; there is nothing to offer.

If it does not resolve, offer the install exactly as [init.md](init.md) Step 9.5 specifies. That step owns the platform command table, the one-command-only failure posture, the unauthenticated-case report line, and the post-install `gh auth login` / `feedback.enabled` instruction; this step invokes it and does not restate or re-derive any of it. `AskUserQuestion` (`<!-- AUTO-MODE: convenience -->`), inferred default **No — install nothing** (an unattended run never invokes a package manager).

> [!practice] Why the offer runs at upgrade time and not only at init
> The two steps reach disjoint populations. Every install that predates this offer has already run its `init` and will never run it again, so an init-only placement leaves those consumers permanently unaware that `/planwise feedback` has been drafting locally rather than posting — the engine's fallback is silent by design ([`references/feedback-submission.md`](../references/feedback-submission.md)), so nothing else would ever tell them.

A declined offer is not remembered — `gh` may be declined once and wanted later — but the question is asked only when `gh` is genuinely absent, so an install already in place is never re-prompted. A failed or declined install NEVER blocks the upgrade.

---

### Step 4.6 — Task-tools env var offer

After a successful upgrade, read the project's `.claude/settings.json` (and `.claude/settings.local.json`, if present) `env` block for `CLAUDE_CODE_ENABLE_TODO_TOOLS`. Consumer settings files are DATA, never a ship-boundary artifact — this step READS and OFFERS, exactly like Step 4.4, and it never silently rewrites.

If the key is already present (any value), report "Task tools: opted in — CLAUDE_CODE_ENABLE_TODO_TOOLS already set." and skip the offer — there is nothing to act on.

If the key is absent, report:

```
Task tools: not opted in — CLAUDE_CODE_ENABLE_TODO_TOOLS is absent from {settings_path}.
Without it, Claude Code omits TaskCreate/TaskUpdate/TaskGet/TaskList (Ctrl+T) on
Opus 4.8, Sonnet 5, Fable 5, Mythos 5 and newer models, and /planwise run falls
back to Recovery-only tracking (Track A).
```

The **report always renders**, regardless of consent. The **write happens only on explicit interactive approval**: `AskUserQuestion` (`<!-- AUTO-MODE: convenience -->`) — "Add `CLAUDE_CODE_ENABLE_TODO_TOOLS: "1"` to {settings_path}'s env block?" — inferred default **report-only, change nothing** (an unattended/non-interactive run never rewrites `env`). On confirm, merge the key into the existing `env` object — preserve every other key, never overwrite an unrelated env var — write, then read the file back to confirm the write landed, and note that a **new session** is required for the tools to appear (the current session's tool list is fixed at startup). On decline, or when no interactive answer is available, print the report and leave every settings file untouched.

> [!practice] Why this offer runs at upgrade time and not only at init
> `scripts/init_project.py::configure_settings()` writes `CLAUDE_CODE_ENABLE_TODO_TOOLS` unconditionally for every new project, same as Agent Teams. But every install that predates that write has already run its `init` and will never run it again, so an init-only placement leaves those consumers permanently dependent on noticing `handlers/doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md` Stage 18's advisory and hand-editing their settings file. This step reaches that population — the same reasoning Step 4.5 already states for the GitHub CLI offer.

---

*Cross-reference: [upgrade.md](upgrade.md) (Part 1 — Config Gate and Steps 1-2.7), [upgrade-Part-2-RecoveryAndReference.md](upgrade-Part-2-RecoveryAndReference.md) (Part 2 — Conflict Resolution Reference and Recovery), [init.md](init.md), [references/feedback-submission.md](../references/feedback-submission.md), [references/do-the-hard-things.md](../references/do-the-hard-things.md).*
