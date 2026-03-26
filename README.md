# planwise

**Your AI project manager that never forgets.**

planwise is a plugin for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that helps you plan, execute, review, and track your work across sessions. It keeps everything organized in simple markdown files so nothing gets lost between conversations.

## Table of contents

- [Getting started](#getting-started)
- [Step 1 — Add the planwise marketplace](#step-1--add-the-planwise-marketplace)
- [Step 2 — Install the plugin](#step-2--install-the-plugin)
- [Step 3 — Activate the plugin](#step-3--activate-the-plugin)
- [Step 4 — Initialize planwise in your project](#step-4--initialize-planwise-in-your-project)
- [Full user guide](#full-user-guide)
- [Quick reference](#quick-reference)
- [Updating planwise](#updating-planwise)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)

---

### The problem

Ever had Claude Code forget what you were working on? Started a new session and had to re-explain everything? Watched tasks pile up with no way to prioritize them?

**planwise fixes that.** It gives your projects a persistent memory — structured plans, scored backlogs, and lessons learned that survive across every session.

---

## Getting started

This guide walks you through everything from zero. No prior experience with plugins or terminals required.

### What you'll need

- **Claude Code** installed and working ([get it here](https://docs.anthropic.com/en/docs/claude-code) if you haven't already)
- **Python 3.8+** installed on your computer (planwise uses small Python scripts for backlog scoring)
- A project you want to manage

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

## Step 1 — Add the planwise marketplace

A **marketplace** is like an app store for Claude Code plugins. You need to add the planwise marketplace first, then install the plugin from it.

Open Claude Code in your terminal and type:

```
/plugin marketplace add gabgoss/planwise
```

Claude Code will download the marketplace catalog. You should see a confirmation message.

---

## Step 2 — Install the plugin

Now that the marketplace is added, install planwise:

```
/plugin install planwise@planwise-marketplace
```

 > **What does `@planwise-marketplace` mean?** It tells Claude Code *which marketplace* to install from. Think of it like specifying which app store to download from.

---

## Step 3 — Activate the plugin

After installing, you need to activate planwise. Either run:

```
/reload-plugins
```

I personally prefer to close the current Claude Code session with `Ctrl+C` twice, then type `claude` and press Enter to start a fresh session. The `/planwise` command is now available.

---

## Step 4 — Initialize planwise in your project

Navigate to the project you want to manage, open Claude Code there, and run:

```
/planwise init
```

Claude will ask you a few questions — your project name, where to store planwise files, and directory names for Plans, Backlog, and Lessons Learned. The defaults work great, so you can just press Enter through most of them.

Once done, you'll have a `planwise/` folder with your config and three subdirectories, plus rules in `.claude/rules/planwise/` that help Claude work with your plans.

> **You only need to run `init` once per project.** After that, planwise remembers your setup.

---

## Full user guide

For detailed documentation on every command, agents, configuration options, and how planwise works under the hood, see the **[planwise user guide](plugins/planwise/)**.

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
| `/planwise lessons` | Search, capture, or promote lessons |
| `/planwise help` | Show available commands and link to user guide |

---

## Updating planwise

To get the latest version, run:

```
/plugin marketplace update
```

Then reinstall:

```
/plugin install planwise@planwise-marketplace
```

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

**Plans or backlog seem out of date**
- Run `/plugin marketplace update` then reinstall to get the latest plugin version

**Not sure which command to use?**
- Run `/planwise help` to see all available commands and a link to the full user guide

---

## License

MIT — Gabriel Gosselin
