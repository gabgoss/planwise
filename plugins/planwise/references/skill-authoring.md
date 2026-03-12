---
description: Skill authoring conventions — directory structure, YAML frontmatter, invocation control, forked execution (ATD-verified), tool restrictions, hooks. Loads when authoring .claude/skills/ files.
paths: .claude/skills/**
---

# Skill Authoring Reference

**Purpose:** Conventions for creating and configuring Claude Code skills.

## Table of Contents

- [1. Directory Structure](#1-directory-structure)
- [2. YAML Frontmatter Reference](#2-yaml-frontmatter-reference)
- [3. Invocation Control](#3-invocation-control)
- [4. Argument Passing](#4-argument-passing)
- [5. Forked Execution](#5-forked-execution)
- [6. Dynamic Context Injection](#6-dynamic-context-injection)
- [7. Tool Restrictions](#7-tool-restrictions)
- [8. Skill-Scoped Hooks](#8-skill-scoped-hooks)
- [9. Troubleshooting](#9-troubleshooting)

---

## 1. Directory Structure

Skills use a **directory-based structure** (not single files):

```
.claude/skills/{skill-name}/
├── SKILL.md           # Main instructions (REQUIRED, <500 lines)
├── reference.md       # Detailed docs (loaded when Claude follows link)
├── templates/         # Template files
├── examples/          # Example outputs
└── scripts/
    └── validate.sh    # Scripts Claude can EXECUTE (not loaded into context)
```

### File Loading Behavior

| File Type | Loaded Into Context | When |
|-----------|---------------------|------|
| `SKILL.md` | Yes | On skill invocation |
| `reference.md`, `templates/*.md`, `examples/*.md` | Yes | When Claude follows markdown link |
| `scripts/*.sh` | **NO** | Executed via Bash; only output returned |

Reference supporting files from SKILL.md with markdown links:

```markdown
- For complete details, see [reference.md](reference.md)
- Template: [templates/report.md](templates/report.md)
```

Claude loads these **when it follows the link**, not automatically.

### 500-Line SKILL.md Limit

Keep SKILL.md under 500 lines. Move detailed content to supporting files:

| Content Type | Location |
|--------------|----------|
| Core workflow, key rules | `SKILL.md` |
| Detailed reference tables | `reference.md` |
| Full templates | `templates/` |
| Example outputs | `examples/` |
| Validation/helper scripts | `scripts/` |

### Scope Levels

| Location | Path | Applies To |
|----------|------|-----------|
| Enterprise | Managed settings | All users in organization |
| Personal | `~/.claude/skills/{name}/SKILL.md` | All your projects |
| Project | `.claude/skills/{name}/SKILL.md` | This project only |
| Plugin | `{plugin}/skills/{name}/SKILL.md` | Where plugin is enabled |

**Priority:** Enterprise > Personal > Project. Plugin skills use `plugin-name:skill-name` namespace to avoid conflicts.

**Backward compatibility:** `.claude/commands/` files still work. If a skill and command share the same name, the skill takes precedence.

**Monorepo:** Claude discovers skills from nested `.claude/skills/` directories relative to the active file location.

---

## 2. YAML Frontmatter Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | directory name | Display name. Lowercase, hyphens, max 64 chars |
| `description` | string | 1st paragraph | **RECOMMENDED** — drives auto-triggering and delegation |
| `argument-hint` | string | none | Autocomplete hint shown after `/`. Example: `[issue-number]` |
| `disable-model-invocation` | boolean | `false` | `true` = only user can invoke; Claude cannot invoke autonomously |
| `user-invocable` | boolean | `true` | `false` = hidden from `/` menu; only Claude can invoke |
| `allowed-tools` | string | all | Comma-separated tool allowlist |
| `model` | string | inherit | Force model: `haiku`, `sonnet`, `opus` |
| `context` | string | `inline` | `fork` = run in isolated subagent context |
| `agent` | string | `general-purpose` | Subagent type when `context: fork` |
| `hooks` | object | none | Skill-scoped lifecycle hooks |

The `description` field is the primary auto-triggering signal. Include trigger conditions and task domains to drive correct automatic delegation. Including "Use proactively" signals Claude to auto-invoke without explicit user prompting.

---

## 3. Invocation Control

| Setting | User Can Invoke | Claude Can Invoke | Notes |
|---------|----------------|-------------------|-------|
| (default) | Yes | Yes | Description in context; full skill loads on invocation |
| `disable-model-invocation: true` | Yes | **No** | Description not in context; full skill loads on invocation |
| `user-invocable: false` | **No** (hidden) | Yes | Description in context; full skill loads on invocation |

> [!decide] Which Invocation Setting?
> | Use Case | Setting |
> |----------|---------|
> | Sensitive operations (user-only, e.g., deploy, delete) | `disable-model-invocation: true` |
> | Internal Claude-only helper (hidden from user) | `user-invocable: false` |
> | Default — both user and Claude can use | (no setting needed) |

**Note:** `user-invocable: false` only controls menu visibility, not the Skill tool itself. To block programmatic invocation by Claude, use `disable-model-invocation: true`.

---

## 4. Argument Passing

| Variable | Description | Example |
|----------|-------------|---------|
| `$ARGUMENTS` | All arguments as single string | `/deploy prod --force` → `prod --force` |
| `$ARGUMENTS[0]` / `$0` | First argument | `/deploy prod --force` → `prod` |
| `$ARGUMENTS[1]` / `$1` | Second argument | `/deploy prod --force` → `--force` |
| `${CLAUDE_SESSION_ID}` | Current session ID | Use for logging or output file naming |

**Example with positional arguments:**

```yaml
---
name: migrate-component
description: Migrate a component from one framework to another
argument-hint: "[component] [from-framework] [to-framework]"
---

Migrate the $0 component from $1 to $2:
1. Find the component in the codebase
2. Analyze its $1 patterns
3. Convert to $2 equivalent
4. Update imports and tests
```

**Usage:** `/migrate-component SearchBar React Vue`

---

## 5. Forked Execution

Set `context: fork` to run the skill in an isolated subagent context. Use `agent:` to specify which agent type handles execution.

```yaml
---
name: deep-research
description: Research a topic thoroughly across the codebase
context: fork
agent: Explore
---

Research $ARGUMENTS:
1. Find relevant files using Glob and Grep
2. Read and analyze the code
3. Summarize findings with file:line references
```

### ATD Empirical Findings — Forked Context Behavior

> [!practice] Empirically Verified (ATD Sprint 04, LoadTest-01)
> **Forked contexts receive the full Claude Code CLI system prompt** — NOT "a custom prompt only" as some documentation suggests. The `SKILL.md` content is ADDITIONAL to the system prompt. [LoadTest-01]

> [!practice] Empirically Verified (ATD Sprint 04, NestTest-08)
> **Forked context tool set is identical to a `general-purpose` subagent** (18 tools). Includes TeamCreate/Delete, SendMessage, all file and web tools. Excludes Task, AskUserQuestion, PlanMode. No nesting — a forked skill cannot spawn further subagents. [NestTest-08]

> [!practice] Empirically Verified (ATD Sprint 04, LoadTest-03)
> **All forked contexts discover project skills via file system access** regardless of `skills:` preload. The `skills:` field in agent frontmatter is **context injection** (injects SKILL.md content at startup), not an access restriction. File system discovery always works for all contexts. [LoadTest-03]

> [!practice] Empirically Verified (ATD Sprint 04, LoadTest-07)
> **Path-specific rules do NOT load in forked contexts.** Only the global rules active in the parent session are visible. If a forked skill needs domain-specific rule content, embed it in SKILL.md directly. [LoadTest-07]

> [!practice] [UNVERIFIED — U5] MCP availability in forked context
> No MCP servers were configured in the test environment; all MCP loading tests were skipped. Theoretical mechanism equivalence between forked skills and general-purpose subagents (confirmed for all other tool access) suggests MCP SHOULD be available for foreground-executed forked skills if configured. Empirical confirmation pending. [ATD-EmpiricalResults §7]

### Forked Skill vs Subagent — Comparison

| Approach | System Prompt | Task Content | Forking Tool |
|----------|---------------|--------------|--------------|
| Skill with `context: fork` | Full CC CLI prompt | SKILL.md content | Skill tool |
| Subagent with `skills:` field | Full CC CLI prompt | Claude's delegation message | Task tool |

Both receive the full CC system prompt and identical 18-tool sets. The distinction is invocation mechanism and task content source.

---

## 5b. Forked Execution Mistakes

> [!constraint] `context: fork` Requires Valid `agent:` Value
> WRONG — `agent:` omitted; forks to `general-purpose` when `Explore` is intended:
> ```yaml
> ---
> name: deep-research
> description: Research a topic across the codebase. Use when exploring unfamiliar modules.
> context: fork
> allowed-tools: Read, Grep, Glob
> ---
> ```
> CORRECT — explicitly declare the agent type to match the tool restriction:
> ```yaml
> ---
> name: deep-research
> description: Research a topic across the codebase. Use when exploring unfamiliar modules.
> context: fork
> agent: Explore
> allowed-tools: Read, Grep, Glob
> ---
> ```

> [!constraint] `context: inline` with `allowed-tools` Cannot Spawn Subagents
> WRONG — `agent:` is meaningless when `context: inline` is set; the skill runs in-session:
> ```yaml
> ---
> name: project-index
> description: Maintain project structure indexes. Use when discovering codebase structure.
> context: inline
> agent: general-purpose
> ---
> ```
> CORRECT — set `context: fork` if you want an isolated subagent context; otherwise omit `agent:`:
> ```yaml
> ---
> name: project-index
> description: Maintain project structure indexes. Use when discovering codebase structure.
> context: fork
> agent: general-purpose
> ---
> ```

> [!pitfall] Path-Specific Rules Missing in Forked Skills
> **Problem:** A forked skill that edits `.cs` files expects `csharp-conventions.md` to load. It doesn't — path-specific rules do NOT load in forked contexts. The skill operates without domain rules.
> **Solution:** Embed the relevant rule content directly in SKILL.md, or reference the rule file explicitly in the skill's task instructions:
> ```yaml
> ---
> name: add-controller-action
> description: Add a new action to an existing controller
> context: fork
> agent: general-purpose
> ---
> ## Rules
> Read `.claude/rules/app/csharp-conventions.md` before writing any code.
> ```

---

## 6. Dynamic Context Injection

Commands inside `` !`...` `` run **before** Claude sees the content. Claude receives the output, not the command.

```yaml
---
name: pr-summary
description: Summarize changes in a pull request
context: fork
agent: Explore
allowed-tools: Bash(gh *)
---

## Current PR Context
- PR diff: !`gh pr diff`
- PR comments: !`gh pr view --comments`
- Changed files: !`gh pr diff --name-only`

## Task
Summarize this pull request: what changed, potential risks, testing recommendations.
```

| Pattern | Purpose |
|---------|---------|
| `` !`git status` `` | Inject current repo state |
| `` !`gh pr view` `` | Inject PR details |
| `` !`cat package.json` `` | Inject file contents |
| `` !`date` `` | Inject current timestamp |

---

## 7. Tool Restrictions

### `allowed-tools` Allowlist

```yaml
# Read-only skill:
allowed-tools: Read, Grep, Glob

# Bash with pattern matching:
allowed-tools: Read, Bash(git *), Bash(npm test)
```

| Bash Pattern | Allows |
|-------------|--------|
| `Bash(git *)` | Any git subcommand |
| `Bash(npm test)` | Only `npm test` |
| `Bash(gh pr *)` | Any `gh pr` subcommand |
| `Bash(./scripts/*)` | Any project script |

### Skill Permission Control

Control which skills Claude can invoke via `/permissions` or `permissions.deny` in `.claude/settings.json`:

```
Skill                 # Disable all skill invocation
Skill(commit)         # Exact match — disable this skill
Skill(review-pr *)    # Prefix match — disable skill with any arguments
```

**Permission syntax:** `Skill(name)` for exact match; `Skill(name *)` for prefix + any arguments.

---

## 7b. Tool Restriction Mistakes

> [!constraint] Bash Pattern Must Use Glob Syntax
> WRONG — `Bash(dotnet)` does not allow subcommands; only the literal string `dotnet` would match:
> ```yaml
> ---
> name: visual-fix-agent
> description: Applies targeted code fixes based on VFA visual feedback
> allowed-tools: Read, Edit, Write, Glob, Grep, Bash(dotnet)
> ---
> ```
> CORRECT — use `Bash(dotnet *)` to allow all dotnet subcommands:
> ```yaml
> ---
> name: visual-fix-agent
> description: Applies targeted code fixes based on VFA visual feedback
> allowed-tools: Read, Edit, Write, Glob, Grep, Bash(dotnet *)
> ---
> ```

> [!constraint] `disable-model-invocation` vs `user-invocable` Confusion
> WRONG — using `user-invocable: false` to prevent accidental Claude invocation of a deploy skill:
> ```yaml
> ---
> name: deploy
> description: Deploy application to staging or production environment
> user-invocable: false
> ---
> ```
> This hides the skill from the `/` menu (user can't invoke it) but Claude can still auto-trigger it.
> CORRECT — use `disable-model-invocation: true` to block autonomous Claude invocation:
> ```yaml
> ---
> name: deploy
> description: Deploy application to staging or production environment. Use when deploying code changes.
> disable-model-invocation: true
> user-invocable: true
> ---
> ```

---

## 8. Skill-Scoped Hooks

Run commands before or after tool use within a skill:

```yaml
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-deploy.sh"
  PostToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/log-action.sh"
```

| Event | When |
|-------|------|
| `PreToolUse` | Before any tool matching the matcher pattern |
| `PostToolUse` | After any tool matching the matcher pattern |

Hooks are scoped to this skill — they do not affect the parent session or other skills.

---

## 9. Troubleshooting

| Problem | Solution |
|---------|----------|
| Skill not triggering | Check `description` keywords match user intent; try rephrasing the request |
| Skill triggers too often | Make description more specific; add `disable-model-invocation: true` |
| Token budget exceeded | Set `SLASH_COMMAND_TOOL_CHAR_BUDGET` env var (default 15K chars); run `/context` to see excluded skills |
| Supporting files not loading | Ensure markdown links use correct format: `[file](file.md)` |
| Forked subagent not working | Verify `context: fork` and a valid `agent:` value |
| `skills:` preload not visible | Use `skills:` in agent frontmatter for context injection; file system discovery is always available for all general-purpose contexts regardless of preload |

### Debugging

| Command | Purpose |
|---------|---------|
| "What skills are available?" | List available skills Claude can see |
| `/context` | Check skill token budget and see excluded skills warning |
| `/{skill-name}` | Invoke skill directly if auto-triggering fails |

---

*Scoped to `.claude/skills/**` — loads only when authoring skill files.*
*Cross-reference: [agent-authoring.md](agent-authoring.md) for agent definition format, [agent-orchestration.md](agent-orchestration.md) for delegation patterns.*
