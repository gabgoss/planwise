# Handler: /planwise upgrade

**Purpose:** Refresh installed plugin artifacts (rules in `.claude/rules/planwise/`) and bump the pinned `plugin_version:` in `config.yaml` after a plugin update.

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

This handler spans **three files**, split by topic because the combined text exceeds the Read-tool page cap. Each Step keeps its own identifier wherever it lands, so an existing `Step N` reference still names exactly one section — only the filename that holds it changes.

| Part | File | Steps / Sections | Topic |
|---|---|---|---|
| 1 (this file) | `upgrade.md` | Config Gate, Steps 1-2.7 | Drift detection, Token Saver mode offer, comparator fan-out, verdict write, the upgrade script invocation, calibration refresh, lessons/feedback backfill |
| 2 | [`upgrade-Part-2-RecoveryAndReference.md`](upgrade-Part-2-RecoveryAndReference.md) | Conflict Resolution Reference, Auto-Init Fallback, Mid-Upgrade Failure, Config Recovery | The scenario table Part 3's Step 4 dispositions point back to, and recovery procedures for a run — or the Config Gate — that cannot complete |
| 3 | [`upgrade-Part-3-BannerAndConflictResolution.md`](upgrade-Part-3-BannerAndConflictResolution.md) | Steps 3-4.7 | Banner rendering, conflict resolution (relocation, upstream issue, per-class cleanup), settings-grant/GitHub-CLI/task-tools/thrifty-sonic post-upgrade offers |

`/planwise upgrade` dispatches to this file; it reads Part 3 for the banner and conflict-resolution steps, and Part 2 when the Config Gate branches to Auto-Init Fallback or a Part 3 step needs the scenario table.

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
  - [Step 2.7 — Feedback directory backfill and creation](#step-27--feedback-directory-backfill-and-creation)
- [Part 3 — Banner Rendering and Conflict Resolution](#part-3--banner-rendering-and-conflict-resolution) — pointer to the separate file [upgrade-Part-3-BannerAndConflictResolution.md](upgrade-Part-3-BannerAndConflictResolution.md) (Step 3 — Render the banner; Step 4 — Resolve conflicts; Step 4.1 — Assisted relocation; Step 4.2 — Opt-in upstream GitHub issue; Step 4.3 — Interactive per-class cleanup offer; Step 4.4 — Settings-grant normalization offer; Step 4.5 — GitHub CLI availability offer; Step 4.6 — Task-tools env var offer; Step 4.7 — Thrifty-sonic env var offer)
- [Part 2 — Conflict Resolution Reference and Recovery](#part-2--conflict-resolution-reference-and-recovery) — pointer to the separate file [upgrade-Part-2-RecoveryAndReference.md](upgrade-Part-2-RecoveryAndReference.md) (Conflict Resolution Reference, Auto-Init Fallback, Mid-Upgrade Failure, Config Recovery)

---

## Config Gate

Locate `config.yaml` by checking, in order:

1. `planwise/config.yaml` (default planwise root)
2. One level down from project root for `*/config.yaml`
3. If still not found → branch to [Auto-Init Fallback](upgrade-Part-2-RecoveryAndReference.md#auto-init-fallback) (Part 2 of this handler)

Resolve **`{plugin_root}`** — used in every script invocation below — from this handler's own known location (the plugin base directory provided by SKILL.md), the same resolution [init.md](init.md) uses for first-time init. This is the LIVE, currently-invoked plugin; it is NOT read from `config.yaml`.

Extract from `config.yaml`:
- `plugin_root` (config value, distinct from the live `{plugin_root}` above) — the plugin root the last init/upgrade wrote. Display/fallback only — see the Step 1 mismatch note; never substitute it for the live `{plugin_root}` in a script invocation.
- `plugin_version` — currently-pinned plugin version (treat absent as `"0.0.0"`)
- `project.planwise_root`, `project.plans_dir`, `project.backlog_dir`, `project.lessons_dir`, `project.index_files.*`
- `project.install_scope` — the value passed as `--scope "{install_scope}"` in the script invocations below (treat absent as `project`)

---

## Workflow

### Step 1 — Detect drift

Read `{plugin_root}/.claude-plugin/plugin.json` and extract `version` — the live root resolved in the Config Gate, always, so this comparison can never be fooled by a stale configured `plugin_root:`. Compare to the user's pinned `plugin_version:`:

> [!gate] Upgrade Gate
> If `pinned == shipped` **and** the config's stored `plugin_root` matches the live `{plugin_root}` → run the Step 2.4 script invocation, then report "Plugin version: {version} — already up to date." and exit. The script re-checks the backlog, lessons and plans index shapes on this branch too and migrates any hand-authored index automatically; pass its `Backlog index migration:` (or `Backlog changelog:`), `Lessons index migration:` and `Plans index migration:` blocks, plus any `Style rule` lines, through verbatim per the Step 3 callout below — the handler names no migration procedure of its own, only the one-word chat-summary label it derives from each block.
> If `pinned == shipped` **but** the stored `plugin_root` differs → do NOT exit; skip the comparator fan-out (Steps 2.1–2.3 have nothing to compare — no artifact changed) and run the Step 2.4 script invocation, which repoints the root on its own. Report the result as "Plugin root repointed", not as a version change. See the mismatch note below.
> If `pinned < shipped` (or `pinned` is absent) → proceed to Step 2.1.
> If `pinned > shipped` → emit a warning ("Your config pins {pinned} but the installed plugin is {shipped} — did you downgrade?") and ask the user with `AskUserQuestion` whether to proceed. On decline, exit without writing. On approval, continue and append `--allow-downgrade` to the Step 2.4 invocation.

> [!constraint] Compare the two versions numerically, and carry an approval into Step 2.4
> Compare `pinned` and `shipped` **per component, as integers** — never as strings. Read as text, `1.0.10` sorts below `1.0.9`, so a lexical test reads the tenth patch release of any minor line as a downgrade. Zero-pad the shorter side when the component counts differ, so a four-component hotfix (`1.0.5.1`) sorts above the three-component release it patches. The script applies the same rule and refuses a backwards run on its own.
>
> That refusal is the reason an approval here is not self-executing. The Step 2.4 writer exits 2 with `Upgrade refused: config.yaml pins plugin_version {pinned}, which is NEWER than the plugin executing this run …` unless the invocation carries `--allow-downgrade`. Approve the question and omit the flag, and the run stops at the writer with nothing written — the user sees a refusal they already consented past.
>
> WRONG — the gate approves, and Step 2.4 runs its ordinary invocation:
> ```bash
> python "{plugin_root}/scripts/init_project.py" … --upgrade --upgrade-pair "{from}-to-{to}"
> ```
> CORRECT — the approval is carried as the flag the writer requires:
> ```bash
> python "{plugin_root}/scripts/init_project.py" … --upgrade --upgrade-pair "{from}-to-{to}" --allow-downgrade
> ```
> Never add the flag on any other branch. It is the recorded answer to this question, not a default.

> [!constraint] Pin the version pair once, here — never re-derive it mid-run
> Record `{from}` = the pinned `plugin_version` and `{to}` = the `version` just read from the live `plugin.json`, and use those two recorded values verbatim for every later `{from}` / `{to}` in this handler: the Step 2.3 cache path, the Step 2.4 `--upgrade-pair` argument, the Step 3 banner, and every `upgrade-conflicts/` / `upgrade-transfers/` / `upgrade-backups/` path in Step 4. Do NOT re-read `plugin.json` or `config.yaml` later to rebuild them. The comparator fan-out (Step 2.2) analyzes the shipped bodies of THIS pair and writes its verdicts under THIS pair's directory; if the plugin cache is refreshed mid-session, a re-derived `{to}` would point the writer at a different pair directory — the cache silently missed, the fan-out's work discarded, and a shipped body adopted that no comparator analyzed. The Step 2.4 script receives the pinned pair and refuses to run when its own live resolution disagrees; on that refusal, restart from this step.

> [!note] "Already up to date" is a local comparison only
> This check compares the pinned `plugin_version:` against the live plugin's own `.claude-plugin/plugin.json` in your local install cache — no step in this handler reads the marketplace source, so "already up to date" reflects your local cache, not necessarily the newest published release; keep the cache itself current with the two-stage refresh described in README.md's upgrade section.

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
> | 8 | Step 2.7 — Feedback directory backfill/creation — see cross-reference; the write itself is part of Step 2.4's script call | both | (documented by Step 2.4) |
>
> Headless / non-interactive: skip rows 3–4; the writer (row 5) runs with no `verdicts.json` and disposes
> every diverged file via the inline `_classify_diverged()` primitive — including the automated
> transfer-then-adopt path for customization-bearing verdicts (see Step 2.4, item 8).

### Step 2.1 — `--list-diverged` pre-scan

Both modes, read-only. Same arg shape as `--upgrade`, minus `--name` (the diagnostic is self-scoped):

```bash
python "{plugin_root}/scripts/init_project.py" --project-root "{project_root}" --root "{planwise_root}" --plans-dir "{plans_dir}" --backlog-dir "{backlog_dir}" --lessons-dir "{lessons_dir}" --scope "{install_scope}" --list-diverged
```

Parse the JSON array printed to stdout. Each row is `{"filename", "kind": "rule", "installed": <project-root-relative POSIX path>, "shipped": <plugin-root-relative POSIX path>}`, stable-sorted by `filename`. The scan walks both the active install set and any de-scoped rules still on disk; the byte/normalized-identical majority never appears here. `[]` → nothing diverges; skip Steps 2.2–2.3 entirely and go straight to Step 2.4 — the writer runs a pure refresh with no fan-out to do. A non-empty list carries into Step 2.2.

---

### Step 2.2 — Comparator fan-out (interactive only)

Gate: a live interactive session **AND** Step 2.1 returned a non-empty list. Otherwise skip — the Step 2.4 writer's inline primitive covers every diverged file on its own.

Spawn `planwise:rule-comparator` **once per diverged file in a single parallel batch** — issue every `Agent` call together in one message (no waiting between spawns), mirroring `review.md` Phase 2 (the fan-out batch pattern). Spawns MUST be `planwise:`-namespaced. Each comparator is one-shot: it returns its verdict and goes idle (idle is normal — do not treat it as an error).

```
Agent(
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

Write the collected verdicts to `{planwise_root}/upgrade-conflicts/{from}-to-{to}/verdicts.json`, keyed by filename — the only place the writer reads this cache from disk. `{from}` / `{to}` are the values pinned in Step 1. The writer reads exactly this path for the pair it resolves: when that file is absent but a `verdicts.json` exists under a *different* pair directory, it prints a stderr warning naming both paths and falls back to the inline primitive — it never consumes another pair's verdicts, and a genuinely absent cache (headless, or fan-out declined) stays silent. Each entry is the comparator's `StructuralVerdict` shape **plus an `installed_sha256` freshness binding** (see below). A SUBSET entry's `notes` is `""` when clean — non-empty `notes` is reserved for verbatim tolerated installed-only fragment text and routes the file to the customization-handling path (see the notes-contract constraint in [rule-comparator.md](../agents/rule-comparator.md)):

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
>    default) the writer's automated transfer-then-adopt path (Step 2.4, item 8)
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
python "{plugin_root}/scripts/init_project.py" --project-root "{project_root}" --name "{project_name}" --root "{planwise_root}" --plans-dir "{plans_dir}" --backlog-dir "{backlog_dir}" --lessons-dir "{lessons_dir}" --scope "{install_scope}" --upgrade --upgrade-pair "{from}-to-{to}" --token-saver
```

Omit the trailing `--token-saver` when `{token_saver}` is `no` — the upgrade leaves the existing `context.token_saver` value untouched (migration is non-destructive; it never flips a user-set toggle off).

`--upgrade-pair "{from}-to-{to}"` carries the pair pinned in Step 1 — pass it verbatim, always. The script resolves the pair itself (pinned `plugin_version` vs the live `plugin.json`) and, when the two disagree, **refuses** with exit code 2 before writing anything (`Upgrade refused: the handler pinned upgrade pair … but the pair now resolves live as …`). That is the plugin cache or the version pin having moved mid-session, not a script fault: restart from Step 1 so the fan-out and the writer agree on one pair. Never retry by dropping the flag.

`--allow-downgrade` is appended **only** when the Step 1 gate took its `pinned > shipped` branch and the user approved it there. The script runs its own direction check and refuses a backwards run with exit code 2 before any write (`Upgrade refused: config.yaml pins plugin_version … which is NEWER than the plugin executing this run …`), naming the pinned version, the executing plugin's version, and the executing plugin root so the user can see which tree they invoked. The refusal is deliberate coverage for direct invocation: this script is a documented entry point, and the Step 1 gate protects only runs that come through this handler. A sanctioned downgrade takes the ordinary path from here on and reaches the same commit point, so `plugin_version` and `plugin_root` are still written together in one write.

`{project_root}` is the absolute path of the project root (the directory containing `{planwise_root}/`). Pass it explicitly so the upgrade writes to the correct tree even when the user invokes `/planwise upgrade` from a subdirectory — the script's default of `Path.cwd()` is incorrect in that case.

If `python` is not found, try `python3`.

The script:
1. Runs `migrate_config()` to merge any new top-level keys into `config.yaml`
2. Calls `bootstrap_lessons_artifacts()` to backfill the lessons scaffolding — seeds the lessons index hub (`{lessons_dir}/00-Index-LessonsLearned.md`) plus its two companions (`00-Changelog-LessonsLearned.md`, `00-PromotionLog-LessonsLearned.md`), and renders `{lessons_dir}/00-Categorization-By-Domain.md` — whenever any is missing. Idempotent and non-destructive: a no-op when every artifact already exists, and an existing (possibly user-customised) file is preserved verbatim. This recovers the categorization file that gates `/planwise lessons curate` and `promote-batch` on projects adopted via `/planwise upgrade` rather than a fresh `/planwise init` (the render used to be fresh-init-only). Runs after `migrate_config()` so a freshly-migrated `categorization:` block is picked up; falls back to the built-in default buckets (and flags it in the banner) when the block is absent
3. Runs `migrate_backlog_if_legacy()` — when the backlog index is hand-authored it backs up every file it will write under `upgrade-backups/{from}-to-{to}/backlog/`, moves the changelog footer, feature-cell prose and dependency notes into their homes, backfills frontmatter, regenerates the index and checks it; recognise-or-refuse, never best-effort, never fails the upgrade; a refusal names the exact fix and re-fires on the next run. `--backlog-reconcile frontmatter-wins` overrides the default `index-wins` for row/frontmatter disagreements.
4. Runs `migrate_lessons_if_legacy()` — when the lessons index is hand-authored it backs up every file it will write under `upgrade-backups/{from}-to-{to}/lessons/`, relocates the header changelog and the Promotion Log into their own files, drops a prose section whose text equals the seed's and relocates one that differs verbatim into the changelog, renames a hand-written companion to `00-Categorization-Notes-LessonsLearned.md` and regenerates the companion, then runs the generator and checks it; recognise-or-refuse, never best-effort, never fails the upgrade; a refusal names the exact fix and re-fires on the next run. `--lessons-reconcile frontmatter-wins` overrides the default `index-wins` for row/frontmatter disagreements.
5. Runs `migrate_plans_if_legacy()` — when the plans index is hand-authored it backs up the index and every Master Plan it appends to under `upgrade-backups/{from}-to-{to}/plans/`, attaches each index note to the row it followed (appended to that row's Master Plan), regenerates the index from the Master Plans and checks it, and writes `{plans_dir}/00-Plans-Migration-Ledger.md`; recognise-or-refuse, never best-effort, never fails the upgrade; a refusal names the exact fix and re-fires on the next run. The Master Plan's status wins a row/Master Plan disagreement, so this step takes no reconcile flag.
6. Iterates `manifests/artifacts.yaml` rows where `upgrade_behavior == "refresh_or_sidecar"`
7. Refreshes installed copies whose normalised body matches the shipped body
8. Classifies each **diverged** installed copy with the structural verdict — consuming `verdicts.json` when present (a comparator verdict for a filename **supersedes** the inline primitive; a missing entry, a malformed entry, or an entry whose `installed_sha256` is missing/stale falls back to the primitive). A clean **stale subset** is auto-adopted in place directly: rules refresh via `update_frontmatter()` (the project's `paths:` line is preserved). Any OTHER divergence — HAS_UNIQUE or a subset whose `notes` flag installed-only tolerated content — is **customization-bearing**, gated by `upgrade.customization_handoff`: under `report+relocate` (the shipped template default) the writer first **transfers** the full installed body (plus a generic provenance header — source filename, kind, upgrade pair, date, verdict summary) to `{planwise_root}/upgrade-transfers/{from}-to-{to}/{filename}` — a **dormant preservation document** outside `.claude/rules/`, never loaded as a rule (a collision is uniquified with a numeric suffix loop, never clobbered) — **verifies** the write by reading it back, mirrors the pre-image under `upgrade-backups/`, and only then adopts the shipped body in place (the `DISPOSITIONS.md` row is appended only after the adoption write succeeds). Under `report` / `report+issue` (or the key absent) the writer is conservative: the customization-bearing file is preserved in place + a `.new` sidecar is written — no transfer, no adoption. A failed transfer write, a failed pre-image backup, a failed adoption write, or a degraded not-analyzed stand-in verdict (`structural_compare` unavailable at call time — no evidence to act on) likewise falls back to that conservative branch: installed file untouched, `.new` sidecar under `{planwise_root}/upgrade-conflicts/<from>-to-<to>/` for manual merge. Every auto-adoption — stale-subset or transfer-then-adopt — first mirrors the pre-change file under `{planwise_root}/upgrade-backups/<from>-to-<to>/` (failed backup = no destructive write) and deletes any sidecar it obsoletes from an earlier interrupted run
9. Runs `migrate_installed_rules()` (version-gated on `RESCOPE_MIGRATION_VERSION`) to retire rules that are now handler-loaded from `references/`: it **removes** an installed `.claude/rules/**` copy when it is untouched (normalized-identical body, `paths:` match) **or** when its body is a high-confidence **stale subset** of the grown shipped reference with no installed-only content flagged; it **preserves** byte-for-byte any HAS_UNIQUE (customised) copy, any subset verdict with reorg confidence or a non-empty installed-only-content flag, and — while `upgrade.descope_preserve_paths_edits` is `true` (the default) — any copy with a customised `paths:` line, even over a stale body. Setting that key to `false` opts in to removing paths-edited copies (reported with an `[INFO]` marker). Every removal is backed up under `upgrade-backups/` first, so a disposition is always recoverable without VCS
10. Runs `lint_rule_overscope()` and appends a post-upgrade advisory listing any `.claude/rules/**` still scoped to plan/backlog/lessons paths, with size
11. Bumps `plugin_version:` AND repoints `plugin_root:` together, in `config.yaml`, LAST, as the commit point — one write, so the pair can never disagree (see `_commit_upgrade_pin()` in `scripts/init_project.py`)

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

2. Report the refreshed numbers in the chat summary (append to the Step 3 banner in [upgrade-Part-3-BannerAndConflictResolution.md](upgrade-Part-3-BannerAndConflictResolution.md)):

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
2. **Read** [../templates/categorization-by-domain.md](../templates/categorization-by-domain.md) as a worked example of the target shape — it is the generator's own zero-lesson output for the ship-default config, not a fill-in-the-blanks template. Match its shape rather than substituting into it: `# Lessons Learned — Categorization by Domain`, a `Generated: <today's date>` line, a `**Companion to:** [{lessons_index}]({lessons_index})` line, then `## Scope` and its paragraph, then one `## {id}. {name} (0)` section per bucket in `decision_tree_order` (with `### {sub_id}. {sub_name} (0)` per sub-bucket) each carrying an empty 3- or 4-column table (per the bucket's `code_bucket:` flag), then a closing `---` and the `[Notes](00-Categorization-Notes-LessonsLearned.md)` / `[Changelog](...)` footer pointers. See [init.md](init.md) Step 5.1 for the full field-by-field rendering steps — this fallback is the same render, reached from the upgrade path. Do NOT render a `## Cross-cutting observations` or `## Classification edge cases` section — those now live in `00-Categorization-Notes-LessonsLearned.md`, never in the companion.
3. Populate it from the user's `config.yaml: categorization:` block, one section per bucket in `decision_tree_order`.
   > [!practice] Missing `categorization:` Block — Render From Defaults
   > When the block is absent or empty, use the 4-bucket default from [../config.yaml.template](../config.yaml.template) (database / code / process / tooling) and add a banner line noting defaults were used. Suggest `python init_project.py --migrate` to seed the block into `config.yaml` for full customisation.
4. For each of the lessons index hub and its two companions — `00-Index-LessonsLearned.md`, `00-Changelog-LessonsLearned.md`, `00-PromotionLog-LessonsLearned.md` — if `{planwise_root}/{lessons_dir}/{name}` is missing, also copy it from `../seed/{name}`.
5. Use **Write** to create the categorization file with the rendered result, and surface it under the banner's `Lessons scaffolding backfilled:` heading.

---

### Step 2.7 — Feedback directory backfill and creation

Implemented inside Step 2.4's script invocation (`_apply_feedback_dir()` in
`artifact_upgrade.py`), not as a separate handler-side procedure — called
out as its own step here only because it closes a distinct half of the
directory-creation contract; see [init.md](init.md) Step 10 and
[doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md](doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md)
Stage 17 for the other two entry points.

On every `--upgrade` run that reaches an existing `config.yaml` — including
the already-up-to-date early return, so a re-run at a current pin still
closes the gap for an install that predates the key — the script:

1. Backfills `project.feedback_dir` when absent, via the same
   leave-and-re-point disposition `--migrate` uses: a pre-existing,
   non-empty `{planwise_root}/feedback-drafts/` re-points the key there
   (with a one-line notice); otherwise the key defaults to `Feedback`.
   Nothing under `{planwise_root}` is ever moved, renamed, copied, or
   deleted.
2. Creates the resolved directory if it does not already exist — `project`
   is not one of the top-level keys the config merge (item 1 above)
   touches, so nothing else in Step 2.4 would otherwise create it.

Both are additive-only and non-interactive, matching the rest of Step 2.4's
config merge. Pass the script's output through verbatim: `Feedback
directory: {created | already present} ({path})`, plus the re-point notice
when it fires.

---

## Part 3 — Banner Rendering and Conflict Resolution

Step 3 (Render the banner) through Step 4.7 (Thrifty-sonic env var offer) live in [upgrade-Part-3-BannerAndConflictResolution.md](upgrade-Part-3-BannerAndConflictResolution.md) — split at this section boundary so each part stays within one Read-tool page. Read it for:

- [Step 3 — Render the banner](upgrade-Part-3-BannerAndConflictResolution.md#step-3--render-the-banner)
- [Step 4 — Resolve conflicts](upgrade-Part-3-BannerAndConflictResolution.md#step-4--resolve-conflicts)
- [Step 4.1 — Assisted relocation](upgrade-Part-3-BannerAndConflictResolution.md#step-41--assisted-relocation)
- [Step 4.2 — Opt-in upstream GitHub issue](upgrade-Part-3-BannerAndConflictResolution.md#step-42--opt-in-upstream-github-issue)
- [Step 4.3 — Interactive per-class cleanup offer](upgrade-Part-3-BannerAndConflictResolution.md#step-43--interactive-per-class-cleanup-offer)
- [Step 4.4 — Settings-grant normalization offer](upgrade-Part-3-BannerAndConflictResolution.md#step-44--settings-grant-normalization-offer)
- [Step 4.5 — GitHub CLI availability offer](upgrade-Part-3-BannerAndConflictResolution.md#step-45--github-cli-availability-offer)
- [Step 4.6 — Task-tools env var offer](upgrade-Part-3-BannerAndConflictResolution.md#step-46--task-tools-env-var-offer)
- [Step 4.7 — Thrifty-sonic env var offer](upgrade-Part-3-BannerAndConflictResolution.md#step-47--thrifty-sonic-env-var-offer)

---

## Part 2 — Conflict Resolution Reference and Recovery

The remainder of this handler lives in [upgrade-Part-2-RecoveryAndReference.md](upgrade-Part-2-RecoveryAndReference.md) — split at this section boundary so each part stays within one Read-tool page. Read it for:

- [Conflict Resolution Reference](upgrade-Part-2-RecoveryAndReference.md#conflict-resolution-reference) — the scenario table behind [upgrade-Part-3-BannerAndConflictResolution.md](upgrade-Part-3-BannerAndConflictResolution.md)'s Step 4 dispositions
- [Auto-Init Fallback](upgrade-Part-2-RecoveryAndReference.md#auto-init-fallback) — the Config Gate's branch when no `config.yaml` exists
- [Mid-Upgrade Failure](upgrade-Part-2-RecoveryAndReference.md#mid-upgrade-failure) — why re-running after a partial upgrade is safe
- [Config Recovery](upgrade-Part-2-RecoveryAndReference.md#config-recovery) — manual repairs for a bricked config or a dangling `plugin_root` pin

---

*Cross-reference: [upgrade-Part-2-RecoveryAndReference.md](upgrade-Part-2-RecoveryAndReference.md) (Part 2 of this handler), [init.md](init.md), [agents/rule-comparator.md](../agents/rule-comparator.md), [migrate logic in scripts/init_project.py](../scripts/init_project.py).*
