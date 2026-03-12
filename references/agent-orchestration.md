---
description: Agent runtime contexts, tool access, context loading, nesting rules, team coordination, and execution modes
---

# Agent Orchestration

**Purpose:** Runtime contexts, tool access, context loading, nesting rules, team coordination, and execution modes for Claude Code agents.

See [agent-authoring.md](agent-authoring.md) for agent definition format and design principles.
See [skill-authoring.md](skill-authoring.md) for skill/forked context authoring.

## Table of Contents

- [1. Runtime Contexts](#1-runtime-contexts)
- [2. Cross-Context Tool Comparison](#2-cross-context-tool-comparison)
- [3. Context Loading Matrix](#3-context-loading-matrix)
- [4. Nesting Rules](#4-nesting-rules)
- [5. Choosing a Context](#5-choosing-a-context)
- [6. Team Lifecycle](#6-team-lifecycle)
- [7. Team Communication](#7-team-communication)
- [8. Scaling Rules](#8-scaling-rules)
- [9. Execution Modes](#9-execution-modes)
- [10. Constraints](#10-constraints)

---

## 1. Runtime Contexts

Claude Code has exactly four runtime contexts. Background mode, worktree isolation, plan mode, and `claude --agent` are **configurations** of these four, not additional types.

| Context | Created Via | System Prompt Identity | Tool Set |
|---------|-------------|----------------------|----------|
| **Main Session** | `claude` CLI / VS Code extension | "You are Claude Code, Anthropic's official CLI" | All tools (~24+) |
| **Subagent** | `Task` tool (`subagent_type` parameter) | **"You are Claude Code, Anthropic's official CLI"** [LoadTest-01] | 18 tools (no Task, AskUserQuestion, PlanMode) |
| **Teammate** | `Task` tool with `team_name` + `name` | **"You are a Claude agent, built on Anthropic's Claude Agent SDK"** [LoadTest-01] | 16 tools (no Task, TeamCreate/Delete, AskUserQuestion, PlanMode) |
| **Skill-Forked** | `Skill` tool with `context: fork` | **"You are Claude Code, Anthropic's official CLI"** [LoadTest-01, NestTest-08] | 18 tools (identical to Subagent) |

> **Surprise 1 [LoadTest-01]:** Subagents receive the **full** Claude Code system prompt. Official docs claim "not the full CC system prompt — custom prompt only." This is wrong. The `prompt` parameter in the Task tool is ADDITIONAL to the system prompt, not a replacement. Skill-Forked contexts receive the same full CC system prompt.

> **Surprise 2 [LoadTest-01]:** Teammates have a **different** identity ("Claude Agent SDK"), not the Claude Code system prompt. Documentation calling them "full, independent Claude Code sessions" is misleading — they use the Agent SDK identity and are pure workers.

### Built-in Subagent Types

| Type | Model | Tools | Best For |
|------|-------|-------|---------|
| `Explore` | Haiku | Read, Glob, Grep only | Fast codebase search, exploration, no writes |
| `Plan` | Inherit | Read, Glob, Grep only | Architecture research in plan mode |
| `general-purpose` | Inherit | All tools | Code changes, file writes, bash commands |
| `Bash` | Inherit | Bash only | Terminal commands in a clean context |
| `statusline-setup` | Sonnet | Read, Edit | Status line configuration via `/statusline` |
| `claude-code-guide` | Haiku | Limited | Questions about Claude Code features |
| Custom agent name | Per definition | Per definition | Project-specific behavior from `.claude/agents/` |

### Modes and Configurations (NOT Separate Contexts)

| Mode/Config | Maps To | Why Not a Separate Context |
|-------------|---------|--------------------------|
| `background: true` | Subagent (background mode) | Execution mode, not agent context type |
| `isolation: worktree` | Subagent (worktree mode) | Filesystem isolation, not context type |
| `mode: "plan"` | Any context (behavioral restriction) | Restricts tools; does not change context type |
| `claude --agent <name>` | Main Session (configured) | Agent definition configures the session; still Main Session |
| Resumed subagent | Subagent (continued) | Retains conversation history; same context type |

---

## 2. Cross-Context Tool Comparison

*Source: ATD-EmpiricalResults.md Appendix — verified by 15 empirical tests.*

| Tool | Main Session | Subagent | Teammate | Skill-Forked |
|------|-------------|----------|----------|-------------|
| Task (spawner) | YES | **NO** | **NO** | **NO** |
| TeamCreate | YES | YES | **NO** | YES |
| TeamDelete | YES | YES | **NO** | YES |
| SendMessage | YES | YES | YES | YES |
| AskUserQuestion | YES | **NO** | **NO** | **NO** |
| EnterPlanMode | YES | **NO** | **NO** | **NO** |
| ExitPlanMode | YES | **NO** | **NO** | **NO** |
| Skill | YES | YES | YES | YES |
| TaskCreate/Get/List/Update | YES | YES | YES | YES |
| Read/Write/Edit | YES | YES | YES | YES |
| Glob/Grep | YES | YES | YES | YES |
| Bash | YES | YES | YES | YES |
| NotebookEdit | YES | YES | YES | YES |
| WebFetch/WebSearch | YES | YES | YES | YES |
| EnterWorktree | YES | YES | YES | YES |

| Context | Total Tools | Key Restrictions |
|---------|------------|-----------------|
| Main Session | ~24+ | None |
| Subagent | 18 | No Task, AskUserQuestion, PlanMode |
| Skill-Forked | 18 | Identical to Subagent |
| Teammate | 16 | No Task, TeamCreate, TeamDelete, AskUserQuestion, PlanMode |

> **Surprise 3 [NestTest-05]:** Teammates have FEWER tools than standalone subagents. TeamCreate/Delete are restricted FROM teammates (to prevent workers from managing teams) but are available to subagents and skill-forked contexts. The restriction is inverted from the expected — team management tools are NOT reserved for team members, they are removed from team members.

---

## 3. Context Loading Matrix

*Source: ATD-S04-03-LoadingMatrix-Working.md — 21 cells, 18 tested (3 skipped, no MCP configured).*

| # | What Loads | Subagent | Teammate | Skill-Forked |
|---|-----------|---------|----------|-------------|
| 1 | System prompt identity | YES (CC CLI) | NO — different identity (Agent SDK) | YES (CC CLI) |
| 2 | CLAUDE.md | YES | YES | YES |
| 3 | All project skill descriptions | YES (via FS discovery) | YES | YES (via FS discovery) |
| 4 | MCP servers | YES (FG); NO (BG) | SKIP (no data) | **[UNVERIFIED — U5]** |
| 5 | Conversation history | NO | NO | NO |
| 6 | Team tools | YES (all incl. TeamCreate/Delete) | PARTIAL (no TeamCreate/Delete) | YES (all) |
| 7 | Path-specific rules | NO (global only) | NO (global only) | NO (global only) |

> **Path rules are main-session-only [LoadTest-07, U2/U3/U4 resolved]:** All spawned contexts see only the global rule files. Path-specific rules load based on the context's OWN file activity — spawned contexts start with zero file activity so no path rules trigger at startup. Spawned contexts CAN trigger path rules after they begin working on matching files, but they do NOT inherit the parent session's active path triggers.

> **Surprise 5 [LoadTest-03] — Skill discoverability:** All contexts discover all project skills via file system access (Glob on `.claude/skills/`). This is file system discoverability, not system-reminder injection. Mid-session created agents are NOT dynamically registered as available `subagent_type` values.

> **Surprise 6 [LoadTest-07] — Path rules:** Even teammates ("full, independent sessions") do NOT load path-specific rules. This is the clearest empirical distinction between teammate and main session contexts. All non-main contexts see the same global rules.

> **U5 — Skill-Forked MCP:** MCP availability in skill-forked contexts is [UNVERIFIED]. Mechanism equivalence with subagents (verified across all other rows) suggests MCP should be available in foreground mode if configured, but requires empirical confirmation with a configured MCP server.

---

## 4. Nesting Rules

*Source: ATD-S04-03-NestingMatrix-Working.md — 8 empirical tests.*

| # | From → To | Result | Enforcement Mechanism |
|---|-----------|--------|----------------------|
| 1 | Main → Subagent | **YES** | N/A (allowed) |
| 2 | Main → Teammate | **YES** | N/A (allowed; requires experimental env var) |
| 3 | Sub → Sub | **NO** | Task tool stripped from subagent at spawn time |
| 4 | Sub → Teammate | **Blocked** (net) | Task tool stripped; TeamCreate works but teammates cannot be added |
| 5 | Teammate → Subagent | **NO** | Task tool stripped from teammate (same restriction as subagent) |
| 6 | Teammate → Teammate | **NO** | Task tool stripped; explicit "No such tool: Task" runtime error |
| 7 | Teammate → Team | **NO** | TeamCreate stripped from teammate at spawn time |
| 8 | Skill-Forked → anything | **NO** | Task tool stripped (identical mechanism to subagent) |

> [!constraint] Universal Spawning Gate
> The Task tool is the SINGLE universal spawning gate. It is stripped from ALL non-main contexts (subagent, teammate, skill-forked) at spawn time. This single mechanism enforces all nesting restrictions — there are no runtime depth checks, no per-context logic. Cannot be bypassed by prompting.
>
> WRONG: Subagent A tries to spawn Subagent B
> CORRECT: Orchestrate all subagents from the main conversation; chain them sequentially if needed

> **Surprise 4 [NestTest-04]:** Subagents CAN create team shells (TeamCreate works), but cannot add teammates (Task tool absent). The enforcement is at the Task tool level, not at TeamCreate. Main session could theoretically add teammates to a subagent-created team. Design around this — do not rely on it.

All spawning MUST go through the Main Session:

```
        Main Session (team lead)
       /    |    |    \
    Sub1  Sub2  TM1  TM2
```

Neither subagents nor teammates can delegate further. The team lead is the ONLY orchestrator.

---

## 5. Choosing a Context

> [!decide] Context Selection
> | Situation | Recommendation | Why |
> |-----------|---------------|-----|
> | Task produces verbose output | Subagent | Isolates context accumulation; lead gets summary |
> | Enforce strict tool restrictions | Subagent | `tools` field is respected |
> | Work is fully self-contained | Subagent | Independent context, clean result |
> | Frequent back-and-forth needed | Main conversation | Shared context, no re-gathering |
> | Multiple phases share intermediate context | Main conversation | No context loss between phases |
> | Quick, targeted single-file change | Main conversation | No subagent startup overhead |
> | Parallel research: independent paths | Multiple subagents | Fresh context each, simultaneous |
> | Parallel coordination with communication | Agent team (teammates) | SendMessage protocol |
> | Reusable user-facing workflow | Skill with `context: fork` | User types /name |

### Delegation Patterns

**Automatic delegation:** Claude reads all agent `description` fields and auto-delegates matching tasks. Including "Use proactively" in the description signals Claude to auto-delegate without explicit prompting.

**Explicit delegation:** User names the agent directly (`Use the code-reviewer agent`). Claude resolves the name against available agents, preloads listed skills, and launches.

**Disabling agents:**
| Method | Scope |
|--------|-------|
| Add `"Task(agent-name)"` to `permissions.deny` in `.claude/settings.json` | Project-wide |
| `--disallowedTools "Task(agent-name)"` CLI flag | Session-only |

### Orchestration Patterns

**Isolate high-volume operations:** Tests, docs, and log scans produce verbose output. Subagents keep it isolated and return only a summary. Use when a step produces output that would fill the main context but only the summary matters.

**Parallel research:** Multiple independent investigations run simultaneously, each in a fresh context. Each subagent explores independently; lead synthesizes after all complete. Works best when research paths are independent with no data dependencies between subagents.

**Chain subagents:** Sequential workflows where each step depends on the previous result. Context is explicitly passed between steps — NOT shared automatically.

**Resume a previous subagent:** Resumed agents retain full conversation history. Prefer resuming when the next step needs prior reasoning; prefer a new instance when independent context budget is more valuable.

> [!constraint] Context Cost Warning
> WRONG: Spawn 10 subagents with verbose output → main conversation hits context ceiling
> CORRECT: Instruct subagents to return summaries only, OR use agent teams for sustained parallelism exceeding the context window

### Agent Scope (Where to Define)

| Location | Scope | Priority |
|----------|-------|----------|
| `--agents` CLI flag | Current session only | 1 (highest) |
| `.claude/agents/` | Current project | 2 |
| `~/.claude/agents/` | All your projects | 3 |
| Plugin `agents/` directory | Where plugin is enabled | 4 (lowest) |

When multiple agents share the same name, the highest-priority location wins.

> [!decide] Where to Define an Agent?
> - Team-shared, version-controlled behavior → `.claude/agents/` (project scope)
> - Personal workflow across many projects → `~/.claude/agents/` (user scope)
> - Testing or one-off automation → `--agents` CLI flag (session scope)
> - Distributed as part of a plugin → plugin `agents/` directory

**Managing agents:** `/agents` — view, create, edit, delete in the UI. `claude agents` — list from the command line.

### Subagent vs Persistent Agent

A **subagent** (spawned via `Task` tool) is ephemeral — one task, returns a result, exits.

A **persistent agent** (defined in `.claude/agents/`) is reusable and named. Use when the same role is needed repeatedly, tool restrictions must be enforced consistently, or automatic delegation by description is desired.

---

## 6. Team Lifecycle

### Tool Quick Reference

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `TeamCreate` | Create team + shared task list | `team_name` (required), `description`, `agent_type` |
| `TeamDelete` | Remove team infrastructure | (none — auto-detects from session context) |
| `SendMessage` | Inter-agent communication | `type`, `recipient`, `content`, `summary` |
| `Task` (team mode) | Spawn teammate into team | `team_name`, `name`, `subagent_type`, `prompt` |

**What TeamCreate produces:**
```
~/.claude/teams/{team-name}/config.json   ← member registry
~/.claude/tasks/{team-name}/              ← shared task list
```

### Lifecycle Sequence

```
[1] TeamCreate(team_name: "{project}-{context}")
[2] Spawn first reviewer → Task(team_name, name, subagent_type, prompt)
[3] Gate on first reviewer results (if phased)
[4] Spawn remaining teammates in parallel
[5] Assign work via TaskCreate + TaskUpdate + SendMessage
[6] Collect findings as messages arrive (incremental synthesis)
[7] SendMessage(shutdown_request) to each teammate
[8] Wait for shutdown_response approvals
[9] TeamDelete
```

> [!constraint] Shutdown Before Delete
> ```
> # WRONG — TeamDelete fails with active members:
> TeamDelete()   # Error: team still has active members
>
> # CORRECT — shut down all teammates first:
> SendMessage(shutdown_request → teammate-1)
> SendMessage(shutdown_request → teammate-2)
> # Wait for shutdown_response approve: true from each
> TeamDelete()
> ```

### Teammate Spawning

```
Task {
  team_name: "plan-review-arc"
  name: "structural-reviewer"     # Unique, descriptive — primary key for messaging
  subagent_type: "Explore"        # Determines tool access
  prompt: "..."                   # MUST be fully self-contained (see below)
}
```

> [!pitfall] Context Not Inherited
> **Problem:** Teammates start with fresh ~100K context — they do NOT inherit the lead's file reads, research, or analysis.
> **Solution:** Include all critical context in the teammate's prompt: file paths, checklists, reporting format, and any findings they need. Share via explicit messages or file references; never assume shared state.

**Subagent type selection for teammates:**
| If task requires... | Use |
|--------------------|-----|
| Read-only (review, research, exploration) | `Explore` |
| Architecture planning | `Plan` |
| Writes, Bash, or team tools | `general-purpose` |
| Project-specific behavior | Custom agent from `.claude/agents/` |

**Naming:** Use unique, descriptive names. Names are the primary key for messaging and task ownership.
```
structural-reviewer     # Role-based
ei-reviewer-1           # Role + index for multiples
impl-reviewer           # Role-based
```
Team names: `plan-review-arc`, `migration-vfa` (`{activity}-{abbrev}`).

### Phase Gating

For multi-phase reviews, gate on the first phase before spawning the rest:
1. Spawn Phase 1 reviewer (structural/validation)
2. WAIT for Phase 1 completion
3. If Phase 1 finds blockers → abort remaining phases
4. If Phase 1 passes → spawn Phase 2-N reviewers in parallel

---

## 7. Team Communication

### SendMessage Types

| Type | Required Fields | Use For |
|------|----------------|---------|
| `message` | `recipient`, `content`, `summary` | DM to single teammate |
| `broadcast` | `content`, `summary` | Message ALL teammates (expensive — N messages for N teammates) |
| `shutdown_request` | `recipient` | Ask teammate to exit |
| `shutdown_response` | `request_id`, `approve` | Teammate approves/rejects shutdown |
| `plan_approval_response` | `request_id`, `recipient`, `approve` | Approve/reject teammate's plan |

> [!practice] Default to DM
> USE `message` (DM) for all routine communication. Reserve `broadcast` for critical abort scenarios only. Broadcasting sends N separate messages for N teammates — costs scale linearly.

### Finding Report Format

Teammates report findings using this structured format:

```
[SEVERITY] Finding summary (one line)
File: {relative path}
Location: {section or line reference}
Issue: {what is wrong}
Fix: {concrete change — file + what to modify}
Confidence: HIGH | MEDIUM | LOW
```

### Uncertain Finding Protocol

When a reviewer has MEDIUM or LOW confidence, prefix the finding with `[UNCERTAIN]`. The team lead cross-checks uncertain findings against other reviewers' context before including in the final report. This is the primary false-positive reduction mechanism.

### When to Broadcast

| Scenario | Type |
|----------|------|
| Report individual finding | DM to lead |
| Flag uncertain finding | DM to lead with `[UNCERTAIN]` |
| Critical abort (structural blockers) | Broadcast |
| Correction affecting all teammates | Broadcast |
| Everything else | DM |

### Idle Teammate Behavior

> [!pitfall] Idle Teammates
> **Problem:** Teammates go idle after every turn. This looks like they stopped working.
> **Solution:** Idle is NORMAL and EXPECTED. Send a message to wake them up — they respond immediately. The standard flow: teammate completes work → goes idle → lead sends next assignment → teammate wakes. Do NOT wait for them to "come back" or treat idle as an error.

Messages from teammates are delivered automatically — do NOT poll for their output manually.

---

## 8. Scaling Rules

> [!decide] Team vs Simple Subagents
> | Plan Size | Approach | Team Size |
> |-----------|----------|-----------|
> | Trivial (no EIs, <3 files) | No team — single Task subagent | 0 |
> | Small (1 EI, 1 sprint) | No team — 2-3 Task subagents sequentially | 0 |
> | Medium (2-3 EIs, 2+ sprints) | Team with standard composition | 3-4 reviewers + lead |
> | Large (4-5 EIs, 3+ sprints) | Full team | 5 reviewers + lead |
> | Very Large (6+ EIs) | Batch into max 5 reviewers | 5 reviewers + lead (batch EIs) |
>
> **Crossover point:** Teams become worthwhile at **2+ EIs or 2+ sprints**. Below that, coordination overhead exceeds the benefit.

### Token Budget Per Teammate Role

| Role | Estimated Context | Notes |
|------|-------------------|-------|
| Structural reviewer | ~10-15K | Fast scan, naming/linking only |
| EI reviewer | ~40-70K | Reads all specs + EI content |
| Task reviewer | ~20-40K | Reads task files + EI sections |
| Implementation reviewer | ~30-50K | Reads task files + codebase modules |

---

## 9. Execution Modes

> [!decide] Foreground vs Background
> | Aspect | Foreground | Background |
> |--------|-----------|------------|
> | Blocking | Yes — blocks main conversation until complete | No — runs concurrently |
> | Permissions | Pass-through to user on each prompt | Pre-approved before launch; auto-denied if not pre-approved |
> | `AskUserQuestion` | Works | Auto-denied — do NOT use |
> | MCP tools | Available | NOT available |
> | How to trigger | Default mode for subagents | `background: true` in frontmatter, or ask Claude, or press Ctrl+B |

### Background Pre-Approval

Before launching a background agent, Claude prompts for all permissions the agent will need. Anything not pre-approved is automatically denied at runtime. Design background agents to:
- Declare all needed permissions upfront
- Never use `AskUserQuestion`
- Not require MCP tools

**Background failure:** If a background agent fails due to missing permissions, resume it in foreground to retry with interactive permission approval.

---

## 10. Constraints

These constraints are empirically verified. The enforcement mechanism column explains why each cannot be bypassed by prompting.

| # | Constraint | Enforcement Mechanism | Impact | Workaround |
|---|-----------|----------------------|--------|------------|
| 1 | No sub-subagent spawning | Task tool stripped from ALL non-main contexts at spawn time | Single-level delegation only | Orchestrate all agents from main conversation; chain sequentially |
| 2 | Teammates lack Task, TeamCreate, TeamDelete | Tool restriction at spawn time [NestTest-05] | Cannot spawn, cannot create/delete teams | All delegation through team lead (hub-and-spoke mandatory) |
| 3 | Context NOT inherited by subagents/teammates | Fresh context per spawn | Teammates start with empty context | Self-contained prompts; share via explicit messages or file references |
| 4 | No AskUserQuestion in spawned contexts | Tool restriction | Cannot interactively prompt user | Pre-gather requirements before spawning |
| 5 | No EnterPlanMode/ExitPlanMode in spawned contexts | Tool restriction | Cannot enter plan mode | Plan in main session before delegating |
| 6 | Path-specific rules are main-session-only | Path rule loading requires OWN file activity [LoadTest-07] | Spawned contexts see only global rules | Include rule content explicitly in task prompt |
| 7 | MCP unavailable in background subagents | Background execution mode restriction | Cannot use external systems | Run in foreground if MCP tools are required |
| 8 | Skill discovery ≠ system-prompt injection | File system access (Glob on `.claude/skills/`) | Mid-session agents not discoverable as subagent_type | Use `skills:` frontmatter to inject domain knowledge; all contexts discover existing skills via FS |
| 9 | Teammate identity is Agent SDK, not CC CLI | System prompt differentiation at spawn time | Teammates self-identify differently; less "Claude Code aware" | Design teammates as workers; orchestrate from main session |

> **Constraint 6 — path rules detail:** Spawned contexts begin with zero file activity. Path rules check the context's OWN active files. If a spawned context later works on files matching a path rule's pattern, those rules CAN trigger dynamically for that context. What they do NOT do is inherit the parent session's already-active path triggers.

> **Constraint 8 — skills note:** The `skills:` frontmatter field injects SKILL.md content into the agent's context at startup — use it for domain knowledge needed immediately. It does not restrict which skills the agent can discover; all contexts with file system access can discover all project skills regardless of the `skills:` field.

> **Team tool compatibility:** TeamCreate and SendMessage are not listed in the `allowed-tools` frontmatter system. Skills that need team functionality should use `context: fork` with `agent: general-purpose`. Do NOT attempt to list TeamCreate or SendMessage in `allowed-tools`.

---

*Cross-reference: [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*
