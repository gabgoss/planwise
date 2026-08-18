---
description: Agent definition format, YAML frontmatter field reference, scope levels, naming conventions, and relationship to runtime contexts. Loads when authoring .claude/agents/ files.
paths: .claude/agents/**
---

# Agent Authoring Reference

**Purpose:** Field-by-field reference for `.claude/agents/*.md` definition files.

---

## 1. Agent Definition Format

An agent definition is a Markdown file in `.claude/agents/` with YAML frontmatter. The file body becomes the system prompt extension when the agent runs.

- **`/agents`** command — view, create, edit, delete agents in the UI
- **`claude agents`** — list available agents from the CLI

**Distinction:** Agent definition (static config file) vs agent instance (running process). An agent definition configures behavior; an instance is a live execution context spawned from that definition.

---

## 2. Frontmatter Fields

### Quick Reference

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `name` | string | **Yes** | N/A | Lowercase, hyphens, max 64 chars. Must match filename. |
| `description` | string | **Yes** | N/A | Max 1024 chars. Drives delegation decisions. |
| `tools` | string | No | All tools | Comma-separated allowlist. `Task(agent_type)` restricts spawning. |
| `disallowedTools` | string | No | None | Comma-separated denylist. Removed from `tools` set (or all tools). |
| `model` | string | No | `inherit` | `haiku`, `sonnet`, `opus`, or `inherit` |
| `permissionMode` | string | No | `default` | `default`, `acceptEdits`, `dontAsk`, `bypassPermissions`, `plan` |
| `maxTurns` | number | No | unlimited | Max agentic turns before agent stops |
| `skills` | list | No | None | Skill names to preload. Full SKILL.md injected at startup. |
| `mcpServers` | object | No | None | Reference existing servers or define inline. Not available in background. |
| `hooks` | object | No | None | PreToolUse, PostToolUse, Stop lifecycle hooks. Scoped to this agent. |
| `memory` | string | No | None | Persistent memory scope: `user`, `project`, or `local` |
| `background` | boolean | No | `false` | `true` = always run as background task. No MCP, no AskUserQuestion. |
| `isolation` | string | No | None | `worktree` = run in temporary git worktree |

### Required Fields

**`name`** — Must match the filename exactly (without `.md`). Lowercase letters, numbers, and hyphens only.

```yaml
# WRONG — name does not match file code-reviewer.md:
name: codeReviewer
# CORRECT:
name: code-reviewer
```

**`description`** — Claude uses this to decide when to delegate. Include: trigger conditions, expertise domain, what problems it solves. "Use proactively" signals automatic delegation without explicit user instruction.

> [!practice] Write descriptions for delegation
> PREFER descriptions that state trigger conditions: "Validates CSV files against database schema. Use proactively when processing CSV imports." over vague labels like "Does data stuff."

### Tool Control

**`tools`** — Allowlist. Agent receives only listed tools. Omit to inherit all tools.

**`disallowedTools`** — Denylist. Removed from the tool set granted by `tools` (or from all tools if `tools` omitted).

```yaml
# disallowedTools applies TO what tools grants:
tools: Read, Grep, Glob, Edit
disallowedTools: Edit   # Result: Read, Grep, Glob
```

**Common tool patterns:**

| Pattern | Tools | Use For |
|---------|-------|---------|
| Read-only | `Read, Glob, Grep` | Review, exploration, analysis |
| Analysis + shell | `Read, Glob, Grep, Bash` | Research with git queries |
| Code modification | `Read, Write, Edit, Glob, Grep` | Implementation, no shell |
| Full access | *(omit `tools`)* | Complex autonomous tasks |

### Execution Control

**`model`** — `haiku` (fast, cheap), `sonnet` (balanced), `opus` (most capable), `inherit` (same as parent).

| Model | Recommended Scope | Rationale |
|-------|-------------------|-----------|
| `haiku` | Read-only or restricted | Avoid high-stakes writes at low cost |
| `sonnet` | Code modification | Balanced cost/quality |
| `opus` | Full access or complex decisions | Reserve for high-stakes reasoning |

**`permissionMode`** — `default` (prompt on sensitive ops), `acceptEdits` (auto-accept edits), `dontAsk` (auto-deny prompts), `bypassPermissions` (skip all checks), `plan` (read-only planning).

**`maxTurns`** — Maximum API round-trips. No value = unlimited.

**`background`** — `true` = always run as background task. MCP unavailable; `AskUserQuestion` unavailable; permissions must be pre-approved.

**`isolation`** — `worktree` = isolated git worktree copy. Auto-cleaned if agent makes no changes.

### Context Injection

**`skills`** — Preloads skill content at startup. Full SKILL.md injected into context. Supporting files load only if Claude follows markdown links. Subagents do NOT inherit parent's skills — list explicitly.

```yaml
skills:
  - planwise
```

**`mcpServers`** — Reference existing configured servers by name or define inline. Not available in `background: true` mode.

**`memory`** — Enables persistent memory across conversations. Auto-adds Read/Write/Edit tools regardless of `tools` field.

| Scope | Path | Version Controlled |
|-------|------|--------------------|
| `user` | `~/.claude/agent-memory/<name>/` | No — cross-project |
| `project` | `.claude/agent-memory/<name>/` | Yes — team-shared |
| `local` | `.claude/agent-memory-local/<name>/` | No — gitignored |

**`hooks`** — Lifecycle hooks scoped to this agent. Evaluated in declaration order.

```yaml
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate.sh"
  Stop:
    - hooks:
        - type: command
          command: "python -c \"print('agent stopped')\""
```

### Validation Notes

- `name` must match filename without `.md` extension
- YAML booleans must be lowercase: `true` / `false`
- Use 2-space indentation (not tabs) in hooks YAML
- `memory: any` auto-enables Read/Write/Edit regardless of `tools`
- Parent `bypassPermissions` overrides subagent `permissionMode` — cannot be narrowed

**Minimal valid frontmatter:**
```yaml
---
name: my-agent
description: One-line summary of what this agent does and when to use it
---
```

**Full example (all 13 fields):**
```yaml
---
name: code-reviewer
description: Reviews pull request diffs for style violations and logic errors. Use proactively when files are modified.
tools: Read, Grep, Glob, Bash(git *)
disallowedTools: Write, Edit
model: sonnet
permissionMode: dontAsk
maxTurns: 30
background: false
isolation: worktree
skills:
  - planwise
memory: project
mcpServers:
  my-server: {}
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/pre-check.sh"
  Stop:
    - hooks:
        - type: command
          command: "./scripts/on-stop.sh"
---
```

---

## 2b. Common Configuration Mistakes

> [!constraint] `name` Must Match Filename Exactly
> WRONG — `name` field uses camelCase but file is `csv-validator.md`:
> ```yaml
> ---
> name: csvValidator
> description: Validates CSV files against database schema
> ---
> ```
> CORRECT — lowercase hyphens matching the filename:
> ```yaml
> ---
> name: csv-validator
> description: Validates CSV files against database schema
> ---
> ```

> [!constraint] `tools` and `disallowedTools` Interaction
> WRONG — listing `Bash(python *)` in both `tools` and `disallowedTools` cancels it out:
> ```yaml
> ---
> name: csv-validator
> description: Validates CSV files using Python analysis scripts
> tools: Read, Glob, Grep, Bash(python *)
> disallowedTools: Edit, Task, Bash(python *)
> ---
> ```
> CORRECT — `disallowedTools` removes from the `tools` grant; list only what you want removed:
> ```yaml
> ---
> name: csv-validator
> description: Validates CSV files using Python analysis scripts
> tools: Read, Glob, Grep, Bash(python *)
> disallowedTools: Edit, Task
> ---
> ```

> [!constraint] `permissionMode: bypassPermissions` on a Restricted Agent
> WRONG — bypassing all permission checks on a read-only exploration agent defeats the restriction:
> ```yaml
> ---
> name: visual-fix-agent
> description: Applies targeted code fixes based on VFA visual feedback
> tools: Read, Edit, Write, Glob, Grep, Bash(dotnet *)
> permissionMode: bypassPermissions
> ---
> ```
> CORRECT — use `acceptEdits` (auto-approves file edits only) or `dontAsk` (auto-denies prompts) for scoped automation:
> ```yaml
> ---
> name: visual-fix-agent
> description: Applies targeted code fixes based on VFA visual feedback
> tools: Read, Edit, Write, Glob, Grep, Bash(dotnet *)
> permissionMode: acceptEdits
> ---
> ```

> [!pitfall] `skills:` Preload vs File System Discovery
> **Problem:** An agent uses `skills: [planwise]` expecting to restrict which skills it can invoke. This does NOT restrict access — all general-purpose contexts can discover all project skills via file system.
> **Solution:** `skills:` is for CONTEXT INJECTION only — it injects SKILL.md content at agent startup so the agent has immediate domain knowledge without following links. To restrict skill invocation, use `disallowedTools: Skill(skill-name)`.
> ```yaml
> # CORRECT use of skills: — inject context at startup
> skills:
>   - planwise
> # To block a skill from being invoked:
> disallowedTools: Skill(execute), Skill(planwise)
> ```

> [!pitfall] `background: true` with MCP-Dependent Logic
> **Problem:** An agent uses `mcpServers` to connect to an external API but also sets `background: true`. MCP is not available in background mode — the agent silently cannot reach the API.
> **Solution:** Remove `background: true` for agents that need MCP. If background execution is required, design the agent to work without MCP by using direct Bash calls instead.

---

## 3. Scope Levels and Priority

| Location | Scope | Priority | Use Case |
|----------|-------|----------|----------|
| `--agents` CLI flag | Current session only | 1 (highest) | Testing, one-off automation |
| `.claude/agents/` | Current project | 2 | Team-shared, version-controlled |
| `~/.claude/agents/` | All your projects | 3 | Personal workflow across projects |
| Plugin `agents/` directory | Where plugin is enabled | 4 (lowest) | Distributed tooling |

When multiple agents share the same name, the highest-priority location wins.

> [!practice] Example: `planwise`'s No-Mirror Design
> The `planwise` plugin illustrates the lowest-priority row above by design: its bundled `agents/` directory ships several agents, invoked as `planwise:<name>` — the plugin does not install a `.claude/agents/` mirror copy of them. This is the intended model, not a missing feature: a consumer who wants bare-name convenience, or a genuine override, opts in by authoring their own `.claude/agents/<name>.md`. The priority table above means that project-level file wins automatically — no cooperation from the plugin required. `/planwise doctor --prune-stale` conservatively removes now-orphaned mirror copies left behind by older installs, preserving any agent file a consumer has customized.

---

## 4. Naming Conventions

- **Filename:** lowercase, hyphens only, max 64 characters. Must match `name` field exactly.
- **Discovery:** Claude Code scans all `.claude/agents/` at session startup. Agents created mid-session are NOT dynamically registered (see Section 5).
- Use the `/agents` command to view currently available agents.

**Descriptive, role-based names:**
```
code-reviewer       # Role-based
csv-validator       # Function-based
visual-fix-agent    # Workflow-based
```

---

## 5. Relationship to Runtime Contexts

An agent definition file maps to runtime behavior in two modes:

1. **`claude --agent <name>`** — Agent definition configures a **Main Session**: full context, all tools, can spawn subagents.
2. **`subagent_type: "<name>"` in Task tool** — Agent definition configures a **Subagent**: fresh context, 18 tools, Task tool absent (no further spawning).

> [!practice] Empirically Verified
> **Custom agents created mid-session are NOT dynamically registered.** If you write a new agent definition to `.claude/agents/` during an active session, it will NOT be discoverable as a `subagent_type` value in that session. Agent discovery happens at session startup only.

### Built-in Subagent Types

| Type | Model | Tools | Purpose |
|------|-------|-------|---------|
| `Explore` | Haiku | Read, Glob, Grep (no Write/Edit) | Fast codebase exploration |
| `Plan` | Inherit | Read, Glob, Grep (no Write/Edit) | Architecture planning |
| `general-purpose` | Inherit | All tools | Complex autonomous tasks |
| `Bash` | Inherit | Bash only | Terminal commands |
| `statusline-setup` | Sonnet | Read, Edit | Status line configuration |
| `claude-code-guide` | Haiku | Limited | Claude Code feature questions |

> [!practice] Claude Code Guide subagent_type
> The built-in guide agent's `subagent_type` string is `claude-code-guide` (lowercase, hyphenated) — confirmed against the live Claude Code agent registry (the Agent tool's available subagent types).

---

*Scoped to `.claude/agents/**` — loads only when authoring agent definition files.*
*Cross-reference: [rule-authoring.md](rule-authoring.md) for rule frontmatter and path-scoping conventions, [skill-authoring.md](skill-authoring.md) for skill frontmatter, [agent-orchestration.md](agent-orchestration.md) for invocation and team patterns.*
