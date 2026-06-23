# planwise

**Your AI project manager that never forgets.**

planwise is a plugin for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that helps you plan, execute, review, and track your work across sessions. It keeps everything organized in simple markdown files so nothing gets lost between conversations.

## Table of contents

- [Initialize planwise](#step-1--initialize-planwise-in-your-project)
- [Start using planwise](#step-2--start-using-planwise)
  - [Create a plan](#create-a-plan)
  - [Review a plan](#review-a-plan-before-executing-it)
  - [Execute a plan](#execute-a-plan)
  - [Manage your backlog](#manage-your-backlog)
  - [List all plans](#list-all-your-plans)
  - [Lessons learned](#work-with-lessons-learned)
  - [Get help](#get-help)
- [Quick reference](#quick-reference)
- [How it works under the hood](#how-it-works-under-the-hood)
- [Updating planwise](#updating-planwise)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)

---

### The problem

Ever had Claude Code forget what you were working on? Started a new session and had to re-explain everything? Watched tasks pile up with no way to prioritize them?

**planwise fixes that.** It gives your projects a persistent memory — structured plans, scored backlogs, and lessons learned that survive across every session.

---

## Step 1 — Initialize planwise in your project

Navigate to the project you want to manage, open Claude Code there, and run:

```
/planwise init
```

Claude will ask you a few questions:

1. **Project name** — just type your project's name (e.g., `my-cool-app`)
2. **Planwise root directory** — where to store planwise files (default: `planwise/` in your project root — just press Enter to accept)
3. **Directory names** — for Plans, Backlog, and Lessons Learned (defaults are fine)

Once done, you'll see a new folder structure in your project:

```
your-project/
  planwise/
    config.yaml          <-- your project settings
    Plans/               <-- where session plans live
    Backlog/             <-- where tracked items go
    LessonsLearned/      <-- where insights are saved
  .claude/
    rules/
      planwise/          <-- 4 path-scoped rules installed (the rest load on demand from the plugin)
```

> **You only need to run `init` once per project.** After that, planwise remembers your setup.

#### How `init` works

```mermaid
flowchart LR
    A([Run command]) --> B[Answer a few<br/>questions]
    B --> C[planwise creates<br/>folders &amp; config]
    C --> D([Ready to use])
```

---

## Step 2 — Start using planwise

Here's what you can do now. Each command starts with `/planwise` followed by a subcommand.

---

### Create a plan

```
/planwise plan my-new-feature
```

This walks you through creating a structured session plan. Claude will ask about:
- What abbreviation to use (like `APP` for app features, `BUG` for bug fixes)
- How many sprints you need
- What tasks go in each session

Your plan gets saved as organized markdown files you can review anytime.

> **What's a sprint?** A group of related work sessions. If your feature is small, one sprint with one session is enough. Bigger features might need multiple sprints.

**Scaffold from an existing Discovery phase:**

```
/planwise plan --scaffold APP
```

This takes a Discovery plan you've already written and automatically builds out all the sprints and tasks from it.

#### How `plan` works

```mermaid
flowchart LR
    A([Run command]) --> B[Describe your<br/>plan &amp; sprints] --> C[Plan files<br/>created] --> D([Ready to run])
```

---

### Review a plan before executing it

```
/planwise review
```

This sends your plan through a two-phase AI review:

1. **Structural review** — checks that files are named correctly, links aren't broken, and the plan hierarchy makes sense
2. **Content review** — checks task quality, token estimates, dependencies, and success criteria

You'll get a report with an **APPROVED** or **CHANGES REQUIRED** verdict.

> **Why review?** Catching problems in a plan is much cheaper than catching them mid-execution. Think of it like proofreading before you hit send.

#### How `review` works

```mermaid
flowchart LR
    A([Run command]) --> B[AI checks<br/>structure] --> C[AI checks<br/>content] --> D([Get verdict])
```

---

### Execute a plan

```
/planwise run
```

This starts working through your planned tasks in order. You get two modes:

- **GUIDED mode** — Claude proposes each task and waits for your OK before doing it (recommended for your first time)
- **DELEGATED mode** — Claude works through tasks automatically using a task-runner agent

If you need to stop mid-session, don't worry — planwise saves a recovery file so you can pick up exactly where you left off.

#### How `run` works

```mermaid
flowchart LR
    A([Run command]) --> B[Confirm to start] --> C[Work through<br/>tasks] --> D[Get summary] --> E([Done])
```

---

### Manage your backlog

```
/planwise backlog
```

Opens an interactive view of all your tracked items, scored and prioritized. For each item, you choose a route:

| Route | When to use | What happens |
|-------|-------------|--------------|
| **A — Direct Fix** | Small bugs, quick changes | An AI agent fixes it right away |
| **B — Task List** | Medium scope work | Breaks it into steps and works through them |
| **C — New Plan** | Large features or overhauls | Creates a full plan for it |

**Filter your backlog:**

```
/planwise backlog --priority High
/planwise backlog --status IN_PROGRESS
/planwise backlog BUG-042
```

#### How `backlog` works

```mermaid
flowchart LR
    A([Run command]) --> B[See prioritized<br/>items] --> C[Pick an item] --> D[AI works on it] --> E([Approve &amp; close])
```

---

### List all your plans

```
/planwise list
```

Shows a table of every plan in your project with its status, sprint count, and when it was created.

#### How `list` works

```mermaid
flowchart LR
    A([Run command]) --> B[See table of<br/>all your plans]
```

---

### Work with lessons learned

**Search your lessons:**
```
/planwise lessons database migration
```

**Capture a lesson mid-session:**
```
/planwise lessons capture
```

**Promote a lesson to a formal rule:**
```
/planwise lessons promote LL-003
```

**Curate lessons — categorise new ones and track promotions:**
```
/planwise lessons curate
/planwise lessons curate --phase=categorize
/planwise lessons curate --phase=promote
```

Curate runs two phases against your lesson set. Phase 1 sorts uncategorised lessons into the domain buckets defined in `config.yaml` (Database, Application Code, Process, Tooling — customisable). Phase 2 finds lessons you've already promoted to rules or applied to code, verifies the destination artifact exists, and logs each one in the Rule Promotion Log inside your lessons index. Run `--phase=both` (the default) to do both at once, or scope to just one phase.

**Batch-draft promotion plans for a whole bucket:**
```
/planwise lessons promote-batch --category=A
/planwise lessons promote-batch LL-001,LL-002,LL-003
/planwise lessons promote-batch --all-documented
/planwise lessons promote-batch --category=A --dry-run
```

Where `/planwise lessons promote LL-003` promotes one lesson immediately, `promote-batch` plans the promotion of many lessons at once — grouping them by domain bucket and drafting backlog items (BBs) that describe the rules to be created, with the WRONG/CORRECT examples from each lesson inlined. Execution happens later via `/planwise backlog`. Add `--dry-run` to see the grouping plan without writing any files.

> **What are lessons learned?** When something goes wrong (or right!), planwise can capture that insight so you don't repeat mistakes or forget what worked.

> **Curate before you batch-promote.** `promote-batch` will refuse to run if any lessons in the master index aren't yet categorised. Run `/planwise lessons curate --phase=categorize` first to keep the bucketing file in sync.

#### How `lessons` works

```mermaid
flowchart LR
    A([Run command]) --> B[Search, capture,<br/>promote, curate,<br/>or batch-draft] --> C([Done])
```

---

### Get help

```
/planwise help
```

Shows all available commands at a glance and links to this full user guide.

#### How `help` works

```mermaid
flowchart LR
    A([Run command]) --> B[See command list<br/>&amp; docs link]
```

---

## Quick reference

| Command | What it does |
|---------|-------------|
| `/planwise init` | Set up planwise in your project (once) |
| `/planwise plan [name]` | Create a new session plan |
| `/planwise plan --scaffold [abbrev]` | Build a plan from a Discovery phase |
| `/planwise review` | AI-review a plan before running it |
| `/planwise run` | Execute a planned session |
| `/planwise backlog` | Triage and work on backlog items |
| `/planwise list` | See all plans and their status |
| `/planwise lessons` | Search the lessons learned index |
| `/planwise lessons capture` | Capture a lesson mid-session |
| `/planwise lessons promote <id>` | Promote one lesson to a rule/skill/hook/agent |
| `/planwise lessons curate [--phase=X]` | Categorise new lessons and log promotions |
| `/planwise lessons promote-batch <scope>` | Plan promotion of many lessons as backlog items |
| `/planwise help` | Show available commands and link to user guide |

---

## How it works under the hood

planwise is built entirely on markdown files and Python scripts — no databases, no servers, no external services. Everything lives in your project folder and gets version-controlled with your code.

### Custom agents

planwise uses four specialized AI agents behind the scenes:

| Agent | What it does |
|-------|-------------|
| **structural-reviewer** | Validates plan file structure, naming, and cross-references |
| **plan-reviewer** | Deep content review — task specs, estimates, dependencies |
| **task-runner** | Executes individual tasks during plan runs |
| **fix-agent** | Applies targeted code fixes for small backlog items |

You don't need to interact with these directly — they're called automatically when you use `/planwise review`, `/planwise run`, and `/planwise backlog`.

### Configuration

After running `/planwise init`, your settings live in `planwise/config.yaml`. Here are the key things you might want to customize:

| Setting | What it controls | Default |
|---------|-----------------|---------|
| `project.name` | Your project name (used in headers) | Set during init |
| `abbreviations` | Category prefixes for plans (APP, BUG, etc.) | 4 defaults |
| `scoring` | How backlog items are scored and ranked | Sensible defaults |
| `build_commands.default` | Command to verify builds after changes | `echo '...'` |

### Plugin file structure

```
planwise/                           # Plugin root
  .claude-plugin/
    plugin.json                     # Plugin identity
    marketplace.json                # Marketplace catalog
  skills/planwise/SKILL.md          # The /planwise command router
  handlers/                         # 9 subcommand handlers (init, plan, review, run, upgrade, backlog, list, lessons, help)
  agents/                           # 4 custom AI agents (auto-mirrored into project .claude/agents/ on init)
  references/                       # 23 knowledge base documents (4 installed as path-scoped rules + 19 handler-loaded in-place / consumed inline, incl. the de-scoped session/scaffolding/orchestration/conventions/verification rules)
  templates/                        # 12 markdown templates
  seed/                             # Index file seeds for init
  scripts/                          # 8 Python scripts (7 backlog utilities + init_project.py)
  examples/                         # Sample outputs
  config.yaml.template              # Config template
```

---

## Upgrading

When a new plugin version is published:

1. **Refresh the plugin source**

   ```
   /plugin marketplace update
   /plugin install planwise@planwise-marketplace
   ```

   This updates the plugin's handlers, references, templates, and scripts to the latest version. Files Claude reads directly from the plugin directory are now current.

2. **Propagate updates into your project's `.claude/` directory**

   ```
   /planwise upgrade
   ```

   `/plugin install` does not refresh the rules in `.claude/rules/planwise/` or the agents in `.claude/agents/` — those were installed once during `/planwise init` and are skip-if-exists thereafter. `/planwise upgrade`:

   - Bumps the pinned `plugin_version:` in your `config.yaml`
   - Adds any new top-level config keys (the additive merge previously available via `--migrate`)
   - Refreshes installed rules/agents whose local body still matches the previously-shipped body
   - Writes `.new` sidecars under `{planwise_root}/upgrade-conflicts/<from>-to-<to>/` for any file whose body has diverged from the shipped version, so your customisations are preserved
   - **Retires de-scoped rules:** author-time rules that are now loaded on demand from the plugin's `references/` are removed from `.claude/rules/planwise/` **only when your installed copy is untouched** (body and `paths:` both match the original default). Any copy you customised is **preserved byte-for-byte with an action-required notice** — re-home it as a project-local rule, re-scope its `paths:` to the code dirs it governs, or upstream the change. It is never auto-deleted.
   - **Over-scope advisory:** after upgrading, the script lists any `.claude/rules/**` still scoped to plan/backlog/lessons paths (these inject into every plan-brief read and can overflow a 200K-window task-runner). Run `/planwise doctor` any time for the full read-only report.

   See `handlers/upgrade.md` for the full workflow.

> Running `/planwise init` after a plugin update detects the pinned-version drift and surfaces a SKIPPED row pointing at this command, so the prompt is reachable even if you forget the recipe.

---

## Uninstalling

To remove the plugin:

```
/plugin uninstall planwise
```

To remove the marketplace:

```
/plugin marketplace remove planwise-marketplace
```

> **Note:** Uninstalling the plugin does **not** delete your `planwise/` project folder or any of your plans, backlogs, or lessons. Your data is always safe.

---

## Troubleshooting

**"Command not found" when typing `/planwise`**
- Make sure you installed the plugin from the marketplace
- Run `/reload-plugins` or restart Claude Code to activate newly installed plugins

**"Config not found" when running a subcommand**
- Run `/planwise init` first — most commands need the project to be initialized

**Python scripts show errors**
- Check that Python 3.8+ is installed: `python --version`
- If you see YAML-related warnings, install PyYAML: `pip install pyyaml` (optional but silences warnings)

**Plans or backlog seem out of date after a plugin update**
- Run the two-step upgrade recipe: `/plugin marketplace update` + `/plugin install planwise@planwise-marketplace`, then `/planwise upgrade` to propagate refreshed rules and agents into your project

**Not sure which command to use?**
- Run `/planwise help` to see all available commands and a link to the full user guide

---

## License

MIT — Gabriel Gosselin
