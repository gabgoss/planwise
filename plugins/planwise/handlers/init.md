# Handler: /planwise init

**Purpose:** Initialize the Agentic Project Management structure for the current project.

This handler does NOT require `config.yaml` to exist — it creates it.

---

## Tool Usage Rules

This handler MUST use Claude Code's dedicated tools for all file operations:

- **Read** to read plugin source files (references, seeds, templates)
- **Write** to create files in the project
- **Glob** to check if files already exist (skip if they do)
- **Bash** ONLY for `mkdir -p` (directory creation)

Do NOT use `cat`, `cp`, `sed`, `awk`, or other bash commands for file operations.

---

## Workflow

### Step 1 — Gather project information

Use `AskUserQuestion` to collect:

1. **Project name** — The name of this project (e.g., "MyApp", "DataPipeline")
2. **Install scope** — Where to apply planwise settings: `project` (.claude/settings.json, shared with team), `user` (~/.claude/settings.json, personal across all projects), or `local` (.claude/settings.local.json, personal to this project). Default: `project`
3. **Planwise root folder** — Where all planwise files will live (default: `planwise`)
4. **Plans directory** — Subdirectory name for plans within the root (default: `Plans`)
5. **Backlog directory** — Subdirectory name for backlog items within the root (default: `Backlog`)
6. **Lessons directory** — Subdirectory name for lessons learned within the root (default: `LessonsLearned`)

Store responses as:
- `{project_name}` — from question 1
- `{install_scope}` — from question 2 (use `project` if blank; must be one of: `project`, `user`, `local`)
- `{planwise_root}` — from question 3 (use `planwise` if blank)
- `{plans_dir}` — from question 4 (use `Plans` if blank)
- `{backlog_dir}` — from question 5 (use `Backlog` if blank)
- `{lessons_dir}` — from question 6 (use `LessonsLearned` if blank)

---

### Step 2 — Run the init script (fast path)

Try running the Python init script first. It handles directory creation, seed files, config generation, rule installation, and settings configuration (Agent Teams + plugin permissions) in one command.

**Before running the script**, resolve the `CLAUDE_PLUGIN_ROOT` environment variable. Try the marketplace path first, fall back to the cache:

```bash
export CLAUDE_PLUGIN_ROOT="$HOME/.claude/plugins/marketplaces/planwise-marketplace/plugins/planwise"
if [ ! -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  export CLAUDE_PLUGIN_ROOT="$HOME/.claude/plugins/cache/planwise-marketplace/planwise/1.0.0"
fi
```

If neither path exists, fall through to the manual fallback steps (3-8).

Then run the script:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/init_project.py" --name "{project_name}" --root "{planwise_root}" --plans-dir "{plans_dir}" --backlog-dir "{backlog_dir}" --lessons-dir "{lessons_dir}" --scope "{install_scope}"
```

If `python` is not found, try `python3`.

**If the script succeeds:** Check its output for any skipped files (e.g., config.yaml already exists). If config was skipped, ask the user if they want to overwrite — if yes, delete the existing file and re-run the script. Then skip to **Step 9** (team sharing).

**If the script fails** (Python not available or any error): Fall through to Steps 3-8 below.

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

3. **Write** the result to `{planwise_root}/config.yaml`

If `{planwise_root}/config.yaml` already exists, ask the user before overwriting.

---

### Step 6 — Install rules to `.claude/rules/planwise/` (fallback)

The plugin ships 10 reference files that are installed as path-scoped rules. For each rule:

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
| 4 | [../references/session-planning-protocol.md](../references/session-planning-protocol.md) | `.claude/rules/planwise/session-planning-protocol.md` | `{planwise_root}/{plans_dir}/**` |
| 5 | [../references/session-plan-requirements.md](../references/session-plan-requirements.md) | `.claude/rules/planwise/session-plan-requirements.md` | `{planwise_root}/{plans_dir}/**` |
| 6 | [../references/session-context-budget.md](../references/session-context-budget.md) | `.claude/rules/planwise/session-context-budget.md` | `{planwise_root}/{plans_dir}/**` |
| 7 | [../references/session-execution-protocol.md](../references/session-execution-protocol.md) | `.claude/rules/planwise/session-execution-protocol.md` | `{planwise_root}/{plans_dir}/**` |
| 8 | [../references/agent-orchestration.md](../references/agent-orchestration.md) | `.claude/rules/planwise/agent-orchestration.md` | `{planwise_root}/{plans_dir}/**, {planwise_root}/{backlog_dir}/**, {planwise_root}/{lessons_dir}/**` |
| 9 | [../references/callout-conventions.md](../references/callout-conventions.md) | `.claude/rules/planwise/callout-conventions.md` | `{planwise_root}/{plans_dir}/**, {planwise_root}/{backlog_dir}/**, {planwise_root}/{lessons_dir}/**` |
| 10 | [../references/markdown-conventions.md](../references/markdown-conventions.md) | `.claude/rules/planwise/markdown-conventions.md` | `{planwise_root}/{plans_dir}/**, {planwise_root}/{backlog_dir}/**, {planwise_root}/{lessons_dir}/**` |

Replace `{planwise_root}`, `{plans_dir}`, `{backlog_dir}`, `{lessons_dir}` with actual values from Step 1.

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

1. **Read** the same settings file used in Step 7
2. Parse as JSON
3. Add or merge the `permissions.additionalDirectories` key — do NOT overwrite existing entries:
   ```json
   {
     "permissions": {
       "additionalDirectories": [
         "<CLAUDE_PLUGIN_ROOT>"
       ]
     }
   }
   ```
   Where `<CLAUDE_PLUGIN_ROOT>` is the resolved plugin path from Step 2 (e.g., `~/.claude/plugins/cache/planwise-marketplace/planwise/1.0.0`).
4. **Write** the updated JSON back

**Important:** Preserve all existing settings and any existing entries in `additionalDirectories`. Only append the plugin root if it is not already present.

---

### Step 9 — (Optional) Configure team sharing

Use `AskUserQuestion`:

> "Share this planwise plugin with your team via .claude/settings.json? (Yes / No)"

**If Yes:**
- Read `.claude/settings.json` (create if it does not exist)
- Add or merge `enabledPlugins` entry — preserve all existing settings:
  ```json
  {
    "enabledPlugins": {
      "planwise@local": true
    }
  }
  ```
- Write the updated settings back

**If No:** Skip this step silently.

---

### Step 10 — Output confirmation

Output a summary of all actions taken:

```
/planwise init — Complete

Project: {project_name}
Scope: {install_scope}

Directories created:
  ✓ {planwise_root}/
  ✓ {planwise_root}/{plans_dir}/
  ✓ {planwise_root}/{backlog_dir}/
  ✓ {planwise_root}/{lessons_dir}/

Seed files installed:
  ✓ {planwise_root}/{plans_dir}/00-Index-Plans.md
  ✓ {planwise_root}/{backlog_dir}/00-Index-Backlog.md
  ✓ {planwise_root}/{lessons_dir}/00-Index-LessonsLearned.md

Configuration:
  ✓ {planwise_root}/config.yaml (scope: {install_scope})

Agent Teams:
  ✓ CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 → {settings_file}

Plugin permissions:
  ✓ additionalDirectories: {plugin_root} → {settings_file}

Rules installed to .claude/rules/planwise/:
  ✓ agent-authoring.md         (paths: .claude/agents/**)
  ✓ skill-authoring.md         (paths: .claude/skills/**)
  ✓ rule-authoring.md          (paths: .claude/rules/**)
  ✓ session-planning-protocol.md
  ✓ session-plan-requirements.md
  ✓ session-context-budget.md
  ✓ session-execution-protocol.md
  ✓ agent-orchestration.md
  ✓ callout-conventions.md
  ✓ markdown-conventions.md

Next steps:
  /planwise plan          — Create your first plan
  /planwise backlog       — Triage your backlog
  /planwise list          — List all plans
```

Replace `{settings_file}` with the actual path used based on scope. Adjust the output to reflect what was actually created vs. skipped.
