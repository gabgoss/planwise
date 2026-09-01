# Handler: /planwise upgrade — Part 2: Conflict Resolution Reference and Recovery

**Part 2 of [upgrade.md](upgrade.md).** Part 1 carries the Config Gate and the Workflow (Steps 1–4.5) and is the file `/planwise upgrade` dispatches to; this part carries the scenario table the Workflow's Step 4 dispositions point back to, and the recovery procedures that apply when a run — or the Config Gate itself — cannot complete. Read it when Part 1 sends you here, or when diagnosing a failed or un-startable upgrade. Split at this section boundary so each part stays within one Read-tool page.

## Table of Contents

- [Conflict Resolution Reference](#conflict-resolution-reference)
- [Auto-Init Fallback](#auto-init-fallback)
- [Mid-Upgrade Failure](#mid-upgrade-failure)
- [Config Recovery](#config-recovery)

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

## Mid-Upgrade Failure

If an unexpected error interrupts the script anywhere after the config-merge step — during artifact refresh, rule de-scope migration, verdict-cache retirement, the advisory banner, or the version-pin commit itself — the script prints:

```
partial upgrade — re-run to resume; already-refreshed files are idempotent and the version pin is unchanged.
```

and exits non-zero, with the underlying error still surfaced for diagnosis. Re-running is safe, not just convenient: a per-file failure during artifact refresh is caught and reported individually without aborting the run, and the version pin plus the plugin-root path are written together, LAST, in one atomic commit — so a run that fails before reaching that commit leaves the pin at its pre-upgrade value while every file already refreshed keeps its new (idempotent) content. Simply re-run `/planwise upgrade`: already-current files are skipped as no-ops and the run picks up from where it stopped.

---

## Config Recovery

The two recoveries below apply when the Config Gate itself cannot complete — before any Workflow step runs. Both are manual repairs; the second requires no working handler at all.

### Bricked config after an older upgrade

**Symptom:** `config.yaml` fails to parse — the Config Gate can't extract `plugin_root`, `plugin_version`, or any `project.*` value, so every command that resolves through it fails.

**Cause:** plugin versions before 1.0.5 wrote new or migrated keys into `config.yaml` without a parse-health check afterward. A flow-style value (`key: {...}`) rewritten by an older writer could be left with its previous block-style child lines still indented beneath it — a shape that isn't valid YAML.

**Repair:**
1. Get the current plugin version first: run the Stage 1 refresh (`/plugin marketplace update` then `/plugin install planwise@planwise-marketplace`) so you're diagnosing with 1.0.5 or later, which added the check below.
2. If `config.yaml` no longer parses, run `/planwise doctor` — it prints a `Config parse check` block naming the offending key and the fix when the corruption is a recognised one, before failing loud.
3. Hand-repair: open `config.yaml` and find the parent line the report names. The corruption signature is a single-line flow-style value (`{...}`) with its old block-style children still indented beneath it — delete those leftover indented lines; the flow-style value on the parent line already carries them. Save, then re-run `/planwise doctor` to confirm the file parses cleanly.

### Dangling `plugin_root` pin

**Symptom:** `/planwise upgrade` or `/planwise doctor` fails outright trying to read its own scripts, because `config.yaml`'s `plugin_root:` pin still names a version-specific cache directory that a later cache reap removed.

**Repair — an out-of-band, manual pin repair; requires no working handler.** This is the bootstrap for exactly the state where the handler cannot start, since the handler's own commands live under the path that no longer resolves:
1. Locate the live plugin cache — the version-agnostic plugin-family root (e.g. `~/.claude/plugins/cache/planwise-marketplace/planwise`) or the current version's directory beneath it.
2. Edit `config.yaml` directly and set `plugin_root:` to that path.
3. Verify by reading `.claude-plugin/plugin.json` at that path directly — its `version` field confirms which release you just pointed at (no handler required).
4. Once confirmed, run `/planwise upgrade` normally — Step 1 resolves the live root itself and Step 2.4's repoint keeps `plugin_root:` and `plugin_version:` in sync going forward.

---

*Cross-reference: [upgrade.md](upgrade.md) (Part 1 — Config Gate and Workflow), [init.md](init.md), [agents/rule-comparator.md](../agents/rule-comparator.md), [migrate logic in scripts/init_project.py](../scripts/init_project.py).*
