# planwise

**Your AI project manager that never forgets.**

planwise is a plugin for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that helps you plan, execute, review, and track your work across sessions. It keeps everything organized in simple markdown files so nothing gets lost between conversations.

---

### The problem

Ever had Claude Code forget what you were working on? Started a new session and had to re-explain everything? Watched tasks pile up with no way to prioritize them?

**planwise fixes that.** It gives your projects a persistent memory — structured plans, scored backlogs, and lessons learned that survive across every session.

---

## Table of contents

- [Getting started](#getting-started)
  - [Step 1 — Add the planwise marketplace](#step-1--add-the-planwise-marketplace)
  - [Step 2 — Install the plugin](#step-2--install-the-plugin)
  - [Step 3 — Activate the plugin](#step-3--activate-the-plugin)
  - [Step 4 — Initialize planwise in your project](#step-4--initialize-planwise-in-your-project)
  - [Step 5 — Upgrade planwise when a new version ships](#step-5--upgrade-planwise-when-a-new-version-ships)
- [Full user guide](#full-user-guide)
- [Quick reference](#quick-reference)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)

---

## Getting started

This guide walks you through everything from zero. No prior experience with plugins or terminals required.

### What you'll need

- **Claude Code** installed and working ([get it here](https://docs.anthropic.com/en/docs/claude-code) if you haven't already)
- **Python 3.8+** installed on your computer (planwise uses small Python scripts for backlog scoring)
- A project you want to manage
- **Optional: [GitHub CLI](https://cli.github.com/) (`gh`)** — only needed if you want `/planwise feedback` to file its issue for you. Without it, feedback still works: your report is saved as a draft file and you paste it into the issues page yourself. You don't have to install it up front — `/planwise init` and `/planwise upgrade` offer to install it for you if it's missing.

> **How to check if Python is installed:**
> Open your terminal and type `python --version` or `python3 --version`.
> If you see something like `Python 3.11.5`, you're good to go.
> If not, download Python from [python.org](https://www.python.org/downloads/).

### Optional: install PyYAML

planwise works fine without it, but installing PyYAML gives you slightly better config file parsing.

```bash
pip install pyyaml
```

> **What's pip?** It's Python's package installer. It comes bundled with Python.
> If `pip` doesn't work, try `pip3 install pyyaml` instead.

---

### Step 1 — Add the planwise marketplace

A **marketplace** is like an app store for Claude Code plugins. You need to add the planwise marketplace first, then install the plugin from it.

Open Claude Code in your terminal and type:

```
/plugin marketplace add gabgoss/planwise
```

Claude Code will download the marketplace catalog. You should see a confirmation message.

---

### Step 2 — Install the plugin

Now that the marketplace is added, install planwise:

```
/plugin install planwise@planwise-marketplace
```

 > **What does `@planwise-marketplace` mean?** It tells Claude Code *which marketplace* to install from. Think of it like specifying which app store to download from.

---

### Step 3 — Activate the plugin

After installing, you need to activate planwise. Either run:

```
/reload-plugins
```

I personally prefer to close the current Claude Code session with `Ctrl+C` twice, then type `claude` and press Enter to start a fresh session. The `/planwise` command is now available.

---

### Step 4 — Initialize planwise in your project

Navigate to the project you want to manage, open Claude Code there, and run:

```
/planwise init
```

Claude will ask you a few questions — your project name, where to store planwise files, and directory names for Plans, Backlog, and Lessons Learned. The defaults work great, so you can just press Enter through most of them.

Once done, you'll have a `planwise/` folder with your config and three subdirectories, plus rules in `.claude/rules/planwise/` that help Claude work with your plans.

> **You only need to run `init` once per project.** After that, planwise remembers your setup.

---

### Step 5 — Upgrade planwise when a new version ships

You won't need this on day one, but when a new version of planwise is published, upgrading happens in **two stages**: first refresh the plugin itself, then push those updates into your project.

**Stage 1 — Refresh the plugin source**

```
/plugin marketplace update
/plugin install planwise@planwise-marketplace
```

This pulls the latest catalog and reinstalls planwise, updating the handlers, references, templates, and scripts that Claude reads directly from the plugin.

**Stage 2 — Propagate updates into your project**

```
/planwise upgrade
```

Reinstalling the plugin does **not** refresh the rules in `.claude/rules/planwise/` — those were installed during `init` and are left untouched on reinstall. `/planwise upgrade` finishes the job:

- Bumps the pinned `plugin_version:` in your `config.yaml`
- Adds any new config keys and backfills missing lessons scaffolding
- Refreshes installed rules that are untouched — or that are stale copies of an older shipped version you never edited
- Never destroys your edits: a rule you've customized is transferred to a preservation file under `{planwise_root}/upgrade-transfers/` before the shipped version is adopted (or preserved in place with a `.new` sidecar, depending on your `upgrade.customization_handoff` setting), and every automatic change is backed up under `{planwise_root}/upgrade-backups/` first

> **Where did the agents go?** planwise agents now run directly from the plugin (invoked as `planwise:<name>`) — they are no longer copied into your project's `.claude/agents/`. If an older version left mirrored copies there, `/planwise doctor` flags them and `/planwise doctor --prune-stale` removes the ones you never edited (backed up first).

> **Run Stage 2 once per upgrade.** If you skip it, `/planwise init` and `/planwise doctor` both notice the version drift and remind you to run `/planwise upgrade`.

---

## Full user guide

For detailed documentation on every command, agents, configuration options, and how planwise works under the hood, see the **[planwise user guide](plugins/planwise/)**.

---

## Quick reference

| Command | What it does |
|---------|-------------|
| `/planwise init` | Set up planwise in your project (once) |
| `/planwise upgrade` | Refresh installed rules + config after a plugin update |
| `/planwise plan [name]` | Create a new session plan |
| `/planwise plan --scaffold [abbrev]` | Build a plan from a Discovery phase |
| `/planwise review` | AI-review a plan before running it |
| `/planwise run` | Execute a planned session |
| `/planwise doctor` | Audit install health — version gate, stale/diverged rules, orphaned agent mirrors, index drift, feedback capability, Token Saver staleness (`--prune-stale` to clean up) |
| `/planwise token-saver on\|off\|status` | Toggle Token Saver mode anytime (`--plan` to override one plan) |
| `/planwise backlog` | Triage and work on backlog items |
| `/planwise list` | See all plans and their status |
| `/planwise lessons` | Search the lessons learned index |
| `/planwise lessons capture` | Capture a lesson mid-session |
| `/planwise lessons promote <id>` | Promote one lesson to a rule/skill/hook/agent |
| `/planwise lessons curate [--phase=X]` | Categorise new lessons and log promotions |
| `/planwise lessons promote-batch <scope>` | Plan promotion of many lessons as backlog items |
| `/planwise harvest` | Run the lesson-to-artifact chain end to end, unattended |
| `/planwise feedback` | Report a planwise bug, lesson, or idea upstream (needs `gh` to post directly) |
| `/planwise help` | Show available commands and link to user guide |

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
- Make sure you completed both Step 1 (add marketplace) and Step 2 (install plugin)
- Run `/reload-plugins` or restart Claude Code to activate newly installed plugins

**"Config not found" when running a subcommand**
- Run `/planwise init` first — most commands need the project to be initialized

**Python scripts show errors**
- Check that Python 3.8+ is installed: `python --version`
- If you see YAML-related warnings, install PyYAML: `pip install pyyaml` (optional but silences warnings)

**Plans or backlog seem out of date after a plugin update**
- Run the two-step upgrade recipe: `/plugin marketplace update` + `/plugin install planwise@planwise-marketplace`, then `/planwise upgrade` to propagate refreshed rules into your project

**Not sure which command to use?**
- Run `/planwise help` to see all available commands and a link to the full user guide

---

## License

MIT — Gabriel Gosselin
