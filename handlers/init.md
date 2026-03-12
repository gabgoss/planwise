# Handler: /planwise init

**Purpose:** Initialize the Agentic Project Management structure for the current project.

This handler does NOT require `config.yaml` to exist — it creates it.

---

## Required References

Before proceeding, read these reference files from `${CLAUDE_PLUGIN_ROOT}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`) are pre-injected by SKILL.md.

**Init-specific references (always load):**
1. Read `references/agent-authoring.md`
2. Read `references/skill-authoring.md`
3. Read `references/rule-authoring.md`

---

## Workflow

### Step 1 — Gather project information

Use `AskUserQuestion` to collect:

1. **Project name** — The name of this project (e.g., "MyApp", "DataPipeline")
2. **Planwise root folder** — Where all planwise files will live (default: `planwise`)
3. **Plans directory** — Subdirectory name for plans within the root (default: `Plans`)
4. **Backlog directory** — Subdirectory name for backlog items within the root (default: `Backlog`)
5. **Lessons directory** — Subdirectory name for lessons learned within the root (default: `LessonsLearned`)

Store responses as:
- `{project_name}` — from question 1
- `{planwise_root}` — from question 2 (use `planwise` if blank)
- `{plans_dir}` — from question 3 (use `Plans` if blank)
- `{backlog_dir}` — from question 4 (use `Backlog` if blank)
- `{lessons_dir}` — from question 5 (use `LessonsLearned` if blank)

---

### Step 2 — Create directories

Create the planwise root and all subdirectories using Bash:

```bash
mkdir -p "{planwise_root}/{plans_dir}"
mkdir -p "{planwise_root}/{backlog_dir}"
mkdir -p "{planwise_root}/{lessons_dir}"
```

---

### Step 3 — Copy seed files

The plugin's `seed/` folder contains starter index files. Copy them to the user's directories.

Resolve the plugin root via `${CLAUDE_PLUGIN_ROOT}` (the directory containing this plugin).

Copy these files (skip if destination already exists):

| Source (plugin seed/) | Destination |
|-----------------------|-------------|
| `seed/00-Index-Backlog.md` | `{planwise_root}/{backlog_dir}/00-Index-Backlog.md` |
| `seed/00-Index-LessonsLearned.md` | `{planwise_root}/{lessons_dir}/00-Index-LessonsLearned.md` |
| `seed/00-Index-Plans.md` | `{planwise_root}/{plans_dir}/00-Index-Plans.md` |

Use Bash to copy. Example:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
cp -n "${PLUGIN_ROOT}/seed/00-Index-Backlog.md" "{planwise_root}/{backlog_dir}/00-Index-Backlog.md"
cp -n "${PLUGIN_ROOT}/seed/00-Index-LessonsLearned.md" "{planwise_root}/{lessons_dir}/00-Index-LessonsLearned.md"
cp -n "${PLUGIN_ROOT}/seed/00-Index-Plans.md" "{planwise_root}/{plans_dir}/00-Index-Plans.md"
```

**Note:** `-n` (no-clobber) skips copy if the destination already exists, preserving user content.

---

### Step 4 — Generate config.yaml

Read `config.yaml.template` from the plugin root. Replace the following placeholders with user-provided values:

| Placeholder | Replace With |
|-------------|--------------|
| `{project-name}` | `{project_name}` from Step 1 |
| `"planwise"` (planwise_root value) | `"{planwise_root}"` |
| `"Plans"` (plans_dir value) | `"{plans_dir}"` |
| `"Backlog"` (backlog_dir value) | `"{backlog_dir}"` |
| `"LessonsLearned"` (lessons_dir value) | `"{lessons_dir}"` |

Write the result to `{planwise_root}/config.yaml`.

If `{planwise_root}/config.yaml` already exists, ask the user before overwriting:
- "config.yaml already exists. Overwrite with new settings? (Yes / No — keep existing)"

---

### Step 5 — Install rules to `.claude/rules/planwise/`

The plugin ships 10 reference files that are installed as path-scoped rules. All rules go into `.claude/rules/planwise/` to keep the user's rules directory clean.

**Step 5a:** Create the rules directory:

```bash
mkdir -p ".claude/rules/planwise"
```

**Step 5b:** Copy each reference file, adding or updating the `paths:` frontmatter to match the user's actual directory choices. Guard condition: skip if destination already exists.

| # | Plugin Source | Install Destination | `paths:` frontmatter to set |
|---|---------------|--------------------|-----------------------------|
| 1 | `references/agent-authoring.md` | `.claude/rules/planwise/agent-authoring.md` | `paths: .claude/agents/**` |
| 2 | `references/skill-authoring.md` | `.claude/rules/planwise/skill-authoring.md` | `paths: .claude/skills/**` |
| 3 | `references/rule-authoring.md` | `.claude/rules/planwise/rule-authoring.md` | `paths: .claude/rules/**` |
| 4 | `references/session-planning-protocol.md` | `.claude/rules/planwise/session-planning-protocol.md` | `paths: {planwise_root}/{plans_dir}/**` |
| 5 | `references/session-plan-requirements.md` | `.claude/rules/planwise/session-plan-requirements.md` | `paths: {planwise_root}/{plans_dir}/**` |
| 6 | `references/session-context-budget.md` | `.claude/rules/planwise/session-context-budget.md` | `paths: {planwise_root}/{plans_dir}/**` |
| 7 | `references/session-execution-protocol.md` | `.claude/rules/planwise/session-execution-protocol.md` | `paths: {planwise_root}/{plans_dir}/**` |
| 8 | `references/agent-orchestration.md` | `.claude/rules/planwise/agent-orchestration.md` | `paths: {planwise_root}/{plans_dir}/**, {planwise_root}/{backlog_dir}/**, {planwise_root}/{lessons_dir}/**` |
| 9 | `references/callout-conventions.md` | `.claude/rules/planwise/callout-conventions.md` | `paths: {planwise_root}/{plans_dir}/**, {planwise_root}/{backlog_dir}/**, {planwise_root}/{lessons_dir}/**` |
| 10 | `references/markdown-conventions.md` | `.claude/rules/planwise/markdown-conventions.md` | `paths: {planwise_root}/{plans_dir}/**, {planwise_root}/{backlog_dir}/**, {planwise_root}/{lessons_dir}/**` |

**Frontmatter rewriting:** When copying, read the source file. If it has an existing YAML frontmatter block (between `---` delimiters):
- If a `paths:` field exists, replace its value with the correct paths from the table above
- If no `paths:` field exists, insert it into the existing frontmatter block

If there is no frontmatter, prepend a new block:

```yaml
---
paths: {resolved-paths}
---
```

Replace `{planwise_root}`, `{plans_dir}`, `{backlog_dir}`, `{lessons_dir}` with the actual values from Step 1.

---

### Step 6 — (Optional) Configure team sharing

Use `AskUserQuestion`:

> "Share this planwise plugin with your team via .claude/settings.json? (Yes / No)"

**If Yes:**
- Read `.claude/settings.json` (create if it does not exist)
- Add or merge `enabledPlugins` entry:
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

### Step 7 — Output confirmation

Output a summary of all actions taken:

```
/planwise init — Complete

Project: {project_name}

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
  ✓ {planwise_root}/config.yaml

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

Adjust the output to reflect what was actually created vs. skipped.
