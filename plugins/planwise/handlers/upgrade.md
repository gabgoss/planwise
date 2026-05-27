# Handler: /planwise upgrade

**Purpose:** Refresh installed plugin artifacts (rules in `.claude/rules/planwise/`, agents in `.claude/agents/`) and bump the pinned `plugin_version:` in `config.yaml` after a plugin update.

## Table of Contents

- [Config Gate](#config-gate)
- [Workflow](#workflow)
  - [Step 1 — Detect drift](#step-1--detect-drift)
  - [Step 2 — Invoke the upgrade script](#step-2--invoke-the-upgrade-script)
  - [Step 3 — Render the banner](#step-3--render-the-banner)
  - [Step 4 — Resolve conflicts](#step-4--resolve-conflicts)
- [Conflict Resolution Reference](#conflict-resolution-reference)
- [Auto-Init Fallback](#auto-init-fallback)

---

## Config Gate

Locate `config.yaml` by checking, in order:

1. `planwise/config.yaml` (default planwise root)
2. One level down from project root for `*/config.yaml`
3. If still not found → branch to [Auto-Init Fallback](#auto-init-fallback)

Extract from `config.yaml`:
- `plugin_root` — the plugin installation path
- `plugin_version` — currently-pinned plugin version (treat absent as `"0.0.0"`)
- `project.planwise_root`, `project.plans_dir`, `project.backlog_dir`, `project.lessons_dir`, `project.index_files.*`

---

## Workflow

### Step 1 — Detect drift

Read `{plugin_root}/.claude-plugin/plugin.json` and extract `version`. Compare to the user's pinned `plugin_version:`:

> [!gate] Upgrade Gate
> If `pinned == shipped` → report "Plugin version: {version} — already up to date." and exit.
> If `pinned < shipped` (or `pinned` is absent) → proceed to Step 2.
> If `pinned > shipped` → emit a warning ("Your config pins {pinned} but the installed plugin is {shipped} — did you downgrade?") and ask the user with `AskUserQuestion` whether to proceed.

---

### Step 2 — Invoke the upgrade script

```bash
python "{plugin_root}/scripts/init_project.py" --project-root "{project_root}" --name "{project_name}" --root "{planwise_root}" --plans-dir "{plans_dir}" --backlog-dir "{backlog_dir}" --lessons-dir "{lessons_dir}" --scope "{install_scope}" --upgrade
```

`{project_root}` is the absolute path of the project root (the directory containing `{planwise_root}/`). Pass it explicitly so the upgrade writes to the correct tree even when the user invokes `/planwise upgrade` from a subdirectory — the script's default of `Path.cwd()` is incorrect in that case.

If `python` is not found, try `python3`.

The script:
1. Runs `migrate_config()` to merge any new top-level keys into `config.yaml`
2. Iterates `manifests/artifacts.yaml` rows where `upgrade_behavior == "refresh_or_sidecar"`
3. Refreshes installed copies whose normalised body matches the shipped body
4. Writes `.new` sidecars under `{planwise_root}/upgrade-conflicts/<from>-to-<to>/` for any installed copy that has diverged
5. Bumps `plugin_version:` in `config.yaml` LAST, as the commit point

Capture stdout — the banner is rendered from it.

---

### Step 3 — Render the banner

The script emits a structured report. Pass it through verbatim to the user. The output follows this shape:

```
Plugin upgrade: {from} -> {to}

Config keys added:    {N}  ({list, or "(none)"})

Refreshed: {N}
  + {file}
  …
Unchanged: {N} (installed body already matches shipped)
Untracked preserved: {N}
  = {file}
  …

Conflicts (action required):
  ! {file}
      reason:      installed body diverged from plugin-shipped version
      sidecar:     {sidecar path}
      remediation: diff the sidecar against the installed file, merge manually, then delete the .new

Plugin version pinned: {to}

Upgrade complete.
```

Then summarise in the chat with this template:

```
Plugin upgrade: {from} -> {to}

Config keys added:       {N}        ({list, or "(none)"})
Artifacts refreshed:     {N}
Artifacts unchanged:     {N}        (installed body already matched shipped)
Untracked preserved:     {N}        ({list of files outside the manifest allowlist})
Conflicts:               {N}        (see Step 4 if > 0)

Plugin version pinned:   {to}

Upgrade complete.
```

If conflicts > 0, append the conflict list verbatim from the script's stdout and direct the user to Step 4.

---

### Step 4 — Resolve conflicts

For each conflict in `{planwise_root}/upgrade-conflicts/<from>-to-<to>/`:

1. The user diffs `<destination>.md` against `<destination>.md.new`
2. If the changes are acceptable → overwrite the installed file with the sidecar content (or merge selectively) → delete the `.new` file
3. If the user wants to keep their local edits → simply delete the `.new` file

The `upgrade-conflicts/` directory and its `INDEX.md` can be cleaned up once all sidecars are resolved.

---

## Conflict Resolution Reference

> [!practice] Why sidecars and not overwrites
> Rules in `.claude/rules/planwise/` and agents in `.claude/agents/` are user-installable artifacts. A user may have hand-edited a rule to extend its `paths:` glob, refine its prose, or add a project-specific subsection. `/planwise upgrade` MUST NOT silently overwrite that work. Sidecars preserve the user's copy and let them merge intentionally.

| Scenario | What the script does | What the user does |
|---|---|---|
| Installed body matches shipped (normalised) | Skips rewrite (no-op) | Nothing — file is current |
| Installed body matches shipped, but `paths:` differs | Skips rewrite | Nothing — `paths:` is per-project |
| Installed body diverged | Writes `.new` sidecar | Diff, merge, delete `.new` |
| Installed file absent | Writes shipped body fresh | Nothing — file just appeared |
| File present, not in manifest allowlist | Reports as Untracked | Nothing — file is the user's own |

---

## Auto-Init Fallback

If the config gate fails (no `config.yaml` found), the project hasn't been initialised. `--upgrade` will exit non-zero in that case. Surface this clearly:

```
This project doesn't have a planwise config yet. Run `/planwise init` first.
```

Offer to run `/planwise init` via `AskUserQuestion` and, on confirmation, dispatch to `init.md`'s Step 1. Once init completes, the upgrade is unnecessary (the freshly-generated config pins the current plugin version).

---

*Cross-reference: [init.md](init.md), [migrate logic in scripts/init_project.py](../scripts/init_project.py).*
