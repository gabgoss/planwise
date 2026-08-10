# Handler: /planwise init — Fallback Procedure (Steps 3-8)

Loaded by [handlers/init.md](init.md) Step 2 only when the `init_project.py` fast
path fails (Python is not available, or the script errors). This file is the
manual equivalent of the script for directory creation, seed files, config
generation, rule installation, Agent Teams, and plugin read permissions.

> **Step 5.1 — Seed Categorisation file:** run it from `handlers/init.md`; it is
> shared by both the fast path and this fallback path, so it is not duplicated
> here.

After Step 8 below completes, return to [handlers/init.md](init.md) and
continue at **Step 8.5** (Token Saver calibration capture).

---

### Step 3 — Create directories (fallback)

Use Bash for directory creation only:

```bash
mkdir -p "{planwise_root}/{plans_dir}" "{planwise_root}/{backlog_dir}" "{planwise_root}/{lessons_dir}" ".claude/rules/planwise"
```

---

### Step 4 — Copy seed files (fallback)

The plugin's `seed/` folder contains starter index files. For each seed file:

1. Use **Glob** to check if the destination already exists — **skip if it does**
2. Use **Read** to read the source file from the plugin: [../seed/](../seed/)
3. Use **Write** to create the destination file

| Source (read from plugin) | Destination |
|---------------------------|-------------|
| [../seed/00-Index-Backlog.md](../seed/00-Index-Backlog.md) | `{planwise_root}/{backlog_dir}/00-Index-Backlog.md` |
| [../seed/00-Index-LessonsLearned.md](../seed/00-Index-LessonsLearned.md) | `{planwise_root}/{lessons_dir}/00-Index-LessonsLearned.md` |
| [../seed/00-Index-Plans.md](../seed/00-Index-Plans.md) | `{planwise_root}/{plans_dir}/00-Index-Plans.md` |

---

### Step 5 — Generate config.yaml (fallback)

1. **Read** the config template: [../config.yaml.template](../config.yaml.template)
2. Replace placeholders with user-provided values:

| Placeholder | Replace With |
|-------------|--------------|
| `{project-name}` | `{project_name}` from Step 1 |
| `{install-scope}` | `{install_scope}` from Step 1 |
| `{planwise-root}` | `{planwise_root}` from Step 1 |
| `{plans-dir}` | `{plans_dir}` from Step 1 |
| `{backlog-dir}` | `{backlog_dir}` from Step 1 |
| `{lessons-dir}` | `{lessons_dir}` from Step 1 |
| `{plan-tier}` | `{plan_tier}` from Step 1 |
| `{context-window}` | `200000` if `{plan_tier}` is `pro`, `1000000` if `max` |
| `{token-saver}` | `true` if `{token_saver}` is `yes`, `false` if `no` |

3. **Write** the result to `{planwise_root}/config.yaml`

<!-- AUTO-MODE: critical --> If `{planwise_root}/config.yaml` already exists, ask the user before overwriting.

---

### Step 6 — Install rules to `.claude/rules/planwise/` (fallback)

The plugin installs 4 author-time reference files as path-scoped rules. These are the only rules copied into `.claude/rules/planwise/` — they trigger on `.claude/**` file activity and stay small. For each rule:

1. Use **Glob** to check if the destination already exists — **skip if it does**
2. Use **Read** to read the source file from the plugin (links below)
3. Modify the frontmatter in memory:
   - If the file has existing frontmatter with a `paths:` field, replace its value
   - If the file has existing frontmatter without a `paths:` field, add the `paths:` line
   - If the file has no frontmatter, prepend a new `---` block with `description` and `paths`
4. Use **Write** to create the destination file

#### Rules table

| # | Source (read from plugin) | Destination | `paths:` value |
|---|---------------------------|-------------|----------------|
| 1 | [../references/agent-authoring.md](../references/agent-authoring.md) | `.claude/rules/planwise/agent-authoring.md` | `.claude/agents/**` |
| 2 | [../references/skill-authoring.md](../references/skill-authoring.md) | `.claude/rules/planwise/skill-authoring.md` | `.claude/skills/**` |
| 3 | [../references/rule-authoring.md](../references/rule-authoring.md) | `.claude/rules/planwise/rule-authoring.md` | `.claude/rules/**` |
| 4 | [../references/artifact-self-containment.md](../references/artifact-self-containment.md) | `.claude/rules/planwise/artifact-self-containment.md` | `.claude/rules/**, .claude/agents/**, .claude/skills/**, .claude/commands/**, CLAUDE.md` |

Replace `{planwise_root}`, `{plans_dir}`, `{backlog_dir}`, `{lessons_dir}` with actual values from Step 1 where they appear in `paths:` values.

> [!practice] Plan/Backlog/Lessons Rules Are Handler-Loaded, Not Installed
> The plan-, backlog-, and lessons-scoped reference files (session protocols, scaffolding hygiene, orchestration, conventions, verification rules, and similar) are **no longer installed as path-scoped rules**. Handlers load them on demand from the plugin's `references/` directory when a workflow needs them, instead of injecting them as always-on path-scoped rules. This keeps the always-on context budget small while preserving the guidance. When upgrading a project that previously installed these rules, the upgrade flow removes the untouched installed copies and high-confidence stale-subset copies (each backed up under `upgrade-backups/` first), and preserves any copy carrying user content — see the de-scope migration in `scripts/init_project.py`.

---

### Step 7 — Configure Agent Teams (fallback)

Enable Agent Teams by adding the `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` environment variable to the settings file determined by `{install_scope}`:

| Scope | Settings file |
|-------|---------------|
| `project` | `.claude/settings.json` |
| `user` | `~/.claude/settings.json` |
| `local` | `.claude/settings.local.json` |

1. **Read** the target settings file (if it exists — it may not for new projects)
2. Parse as JSON. If the file does not exist or is empty, start with `{}`
3. Add or merge the `env` key — do NOT overwrite existing env vars:
   ```json
   {
     "env": {
       "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
     }
   }
   ```
4. **Write** the updated JSON back to the same file

**Important:** Preserve all existing settings in the file. Only add/update the `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` key within the `env` object.

---

### Step 8 — Configure plugin read permissions (fallback)

Add the plugin cache directory to `permissions.additionalDirectories` so Claude Code can read plugin files (handlers, references, scripts) without prompting.

The grant uses the **version-agnostic plugin-family root** — the parent of the versioned plugin directory (e.g., `~/.claude/plugins/cache/planwise-marketplace/planwise`) rather than the version-pinned leaf (e.g., `…/planwise/1.0.0`). This keeps the grant stable across upgrades without needing a settings refresh on every version bump.

1. **Read** the same settings file used in Step 7
2. Parse as JSON
3. Determine the grant directory: `{plugin_family_root}` = the parent of `{plugin_root}` (e.g., `~/.claude/plugins/cache/planwise-marketplace/planwise`).
4. Apply **parent-aware, normalized dedup** before modifying `additionalDirectories`:
   - Normalize all paths (collapse separators and canonicalize case) before comparing.
   - If any existing entry is equal to or an ancestor of `{plugin_family_root}` (i.e. it already covers the grant), skip the append entirely — idempotent no-op.
   - Otherwise, first remove any existing entries that are descendants of `{plugin_family_root}` (stale version-pinned entries this grant now subsumes), then append `{plugin_family_root}`.
   - Never remove or alter entries that are unrelated to this plugin's family root.

   Result in settings after a fresh grant:
   ```json
   {
     "permissions": {
       "additionalDirectories": [
         "{plugin_family_root}"
       ]
     }
   }
   ```
5. **Write** the updated JSON back

**Important:** Preserve all existing settings and any existing entries in `additionalDirectories` that are not descendants of `{plugin_family_root}`. Only append the family root when no existing entry already covers it.

---

*Return to [handlers/init.md](init.md) Step 8.5 (Token Saver calibration capture) to continue.*
