---
description: Agent runtime contexts, tool access, context loading, nesting rules, named-agent coordination, and execution modes
---

# Agent Orchestration

**Purpose:** Runtime contexts, tool access, context loading, nesting rules, named-agent coordination, and execution modes for Claude Code agents.

See [agent-authoring.md](agent-authoring.md) for agent definition format and design principles.
See [skill-authoring.md](skill-authoring.md) for skill/forked context authoring.

## Table of Contents

- [1. Runtime Contexts](#1-runtime-contexts)
- [2. Cross-Context Tool Comparison](#2-cross-context-tool-comparison)
- [3. Context Loading Matrix](#3-context-loading-matrix)
- [4. Nesting Rules](#4-nesting-rules)
- [5. Choosing a Context](#5-choosing-a-context)
- [6. Named-Agent Lifecycle](#6-named-agent-lifecycle)
- [7. Agent Communication](#7-agent-communication)
- [8. Scaling Rules](#8-scaling-rules)
- [9. Execution Modes](#9-execution-modes)
- [10. Constraints](#10-constraints)
- [11. DELEGATED Dispatch Discipline](#11-delegated-dispatch-discipline)

---

## 1. Runtime Contexts

This reference distinguishes four runtime contexts. Background mode, worktree isolation, plan mode, and `claude --agent` are **configurations** of these four, not additional types.

| Context | Created Via | Tool Set |
|---------|-------------|----------|
| **Main Session** | `claude` CLI / VS Code extension | 56 tools, loaded plus deferred (§2) |
| **Subagent** | `Agent` tool, no `name` | `general-purpose`: 38 tools. A custom agent: its `tools:` list (§2) |
| **Named agent** | `Agent` tool with `name` | Not measured |
| **Skill-Forked** | `Skill` tool with `context: fork` | Not re-measured on this build |

Measured 2026-10-12 on Claude Code 2.1.296: a named spawn returned "Spawned successfully" and said it receives instructions through a mailbox. `ListAgents` lists named agents apart from unnamed subagents. An unnamed spawn returned "Async agent launched successfully".

### Built-in Subagent Types

| Type | Model | Tools | Best For |
|------|-------|-------|---------|
| `Explore` | Haiku | Read, Glob, Grep only | Fast codebase search, exploration, no writes |
| `Plan` | Inherit | Read, Glob, Grep only | Architecture research in plan mode |
| `general-purpose` | Inherit | 38 tools (§2) | Code changes, file writes, bash commands |
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

*Measured 2026-10-12 on Claude Code 2.1.296, one sample per column. Main session: loaded plus deferred tools. Subagent columns: self-reported by an unnamed spawn. A custom agent's set follows its `tools:` frontmatter, so the task-runner column shows one definition, not a context property.*

| Tool | Main session | `general-purpose` subagent | `planwise:task-runner` subagent |
|------|-------------|----------------------------|---------------------------------|
| Agent (spawner) | YES | YES | NO |
| TeamCreate, TeamDelete | NO | NO | NO |
| SendMessage | YES | YES | YES |
| SubagentHandback | NO | YES | YES |
| ListAgents | YES | NO | NO |
| AskUserQuestion | YES | NO | NO |
| EnterPlanMode, ExitPlanMode | YES | NO | NO |
| Skill | YES | YES | NO |
| TaskCreate, TaskGet, TaskList, TaskUpdate | YES | NO | NO |
| TaskStop | YES | YES | NO |
| Workflow | YES | NO | NO |
| Read, Write, Edit, Glob, Grep, Bash | YES | YES | YES |
| NotebookEdit, WebFetch, WebSearch, ToolSearch | YES | YES | YES |
| EnterWorktree, ExitWorktree, Monitor | YES | YES | NO |
| Total tools | 56 | 38 | 12 |

Two tool families share a word. The **Agent tool** spawns a subagent; Claude Code renamed it from `Task` in version 2.1.63, and the old name still works as an alias. The **Task tools** (`TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`) are the session checklist and replaced the legacy `TodoWrite`. This plugin uses the Task tools for progress tracking and never `TodoWrite`.
In the measured lists, only the main session holds the checklist tools.

---

## 3. Context Loading Matrix

*Measured on an earlier build. Not re-measured on Claude Code 2.1.296 (2026-10-12).*

| # | What Loads | Subagent | Skill-Forked |
|---|-----------|---------|-------------|
| 1 | CLAUDE.md | YES | YES |
| 2 | All project skill descriptions | YES (via FS discovery) | YES (via FS discovery) |
| 3 | MCP servers | YES (FG); NO (BG) | YES (FG) |
| 4 | Conversation history | NO | NO |
| 5 | Path-specific rules | NO (global only) | NO (global only) |

> **Path rules are main-session-only:** All spawned contexts see only the global rule files. Path-specific rules load based on the context's OWN file activity — spawned contexts start with zero file activity so no path rules trigger at startup. Spawned contexts CAN trigger path rules after they begin working on matching files, but they do NOT inherit the parent session's active path triggers.

> **Surprise 5 — Skill discoverability:** All contexts discover all project skills via file system access (Glob on `.claude/skills/`). This is file system discoverability, not system-reminder injection. Mid-session created agents are NOT dynamically registered as available `subagent_type` values.

> **Skill-Forked MCP:** MCP is reachable from foreground skill-forked contexts. Confirmed by a live test — a `context: fork` skill loaded a configured MCP server's tool via `ToolSearch` and the subsequent call round-tripped to the MCP layer and returned a real result. Background skill-forked MCP behavior was not exercised.

---

## 4. Nesting Rules

| # | From → To | Result | Basis |
|---|-----------|--------|-------|
| 1 | Main → Subagent | **YES** | Measured 2026-10-12 |
| 2 | Main → Named agent | **YES** | Measured 2026-10-12 |
| 3 | Subagent → anything | **Not used by planwise** | `general-purpose` lists `Agent` (measured 2026-10-12). A nested spawn was not tested. `planwise:task-runner` has no `Agent` |
| 4 | Skill-Forked → anything | **NO** (earlier build) | Carried: `Agent` was absent. Not re-measured |

> [!constraint] Spawn Only From the Main Conversation
> Planwise spawns every agent from the main conversation. The planwise reviewer and task-runner agents omit `Agent` from `tools:`, and no planwise prompt asks a spawned agent to spawn another.
>
> WRONG: Subagent A tries to spawn Subagent B
> CORRECT: Orchestrate all subagents from the main conversation; chain them sequentially if needed

All spawning MUST go through the Main Session:

```
        Main conversation (orchestrator, addressed as `main`)
       /    |    |    \
    Sub1  Sub2  NA1  NA2
```

Planwise never asks a spawned agent to delegate further. The main conversation is the only orchestrator.

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
> | Parallel work the orchestrator addresses by name | Named agents | Each reports with a message to `main` |
> | Reusable user-facing workflow | Skill with `context: fork` | User types /name |

### Delegation Patterns

**Automatic delegation:** Claude reads all agent `description` fields and auto-delegates matching tasks. Including "Use proactively" in the description signals Claude to auto-delegate without explicit prompting.

**Explicit delegation:** User names the agent directly (`Use the code-reviewer agent`). Claude resolves the name against available agents, preloads listed skills, and launches.

**Disabling agents:**
| Method | Scope |
|--------|-------|
| Add `"Agent(agent-name)"` to `permissions.deny` in `.claude/settings.json` | Project-wide |
| `--disallowedTools "Agent(agent-name)"` CLI flag | Session-only |

The older `"Task(agent-name)"` form still works as an alias, so settings written before the rename need no change.

### Orchestration Patterns

**Isolate high-volume operations:** Tests, docs, and log scans produce verbose output. Subagents keep it isolated and return only a summary. Use when a step produces output that would fill the main context but only the summary matters.

**Parallel research:** Multiple independent investigations run simultaneously, each in a fresh context. Each subagent explores independently; lead synthesizes after all complete. Works best when research paths are independent with no data dependencies between subagents.

**Chain subagents:** Sequential workflows where each step depends on the previous result. Context is explicitly passed between steps — NOT shared automatically.

**Resume a previous subagent:** Resumed agents retain full conversation history. Prefer resuming when the next step needs prior reasoning; prefer a new instance when independent context budget is more valuable.

> [!constraint] Context Cost Warning
> WRONG: Spawn 10 subagents with verbose output → main conversation hits context ceiling
> CORRECT: Instruct subagents to return summaries only

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

A **subagent** (spawned via `Agent` tool) is ephemeral — one task, returns a result, exits.

A **persistent agent** (defined in `.claude/agents/`) is reusable and named. Use when the same role is needed repeatedly, tool restrictions must be enforced consistently, or automatic delegation by description is desired.

### Plugin Handler Spawns Resolve in the Consumer's Scope Chain

> [!pitfall] Un-Namespaced Plugin-Handler Spawn
> **Problem:** A plugin handler that spawns an agent by bare name (e.g., `subagent_type: "plan-reviewer"`) resolves the agent in the CONSUMER PROJECT's scope chain, not the plugin's scope chain. If the consumer has not run `/planwise init`, the agent file does not exist in `.claude/agents/` (the plugin never installs one there) and the spawn fails with "agent not found".
>
> This constraint was empirically verified 2026-05-12 (behavior may not be re-verified).
>
> **Solution:** Plugin handlers MUST spawn agents with the plugin-namespaced form: `subagent_type: "{plugin-name}:plan-reviewer"`. The `{plugin-name}:` prefix forces resolution against the plugin's own `agents/` directory, bypassing the consumer scope chain.
>
> WRONG (bare name — fails if consumer has no plan-reviewer agent):
> ```
> Agent(
>   subagent_type: "plan-reviewer",
>   ...
> )
> ```
> CORRECT (plugin-namespaced — always resolves against plugin agents/):
> ```
> Agent(
>   subagent_type: "{plugin-name}:plan-reviewer",
>   ...
> )
> ```
> See `handlers/review.md` (9 sites), `handlers/run.md` (5 sites), `handlers/backlog.md` (1 site) for spawn-call updates.

---

## 6. Named-Agent Lifecycle

No team object exists. A named agent is an `Agent` spawn that carries a `name`. The orchestrator addresses it by that name.

### Tool Quick Reference

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `Agent` (named) | Spawn a named agent | `name`, `subagent_type`, `prompt` |
| `SendMessage` | Message the orchestrator or a named agent | `to`, `message` |

### Lifecycle Sequence

```
[1] Spawn first reviewer → Agent(name, subagent_type, prompt)
[2] Gate on its completion message (if phased)
[3] Spawn remaining named agents in parallel
[4] Collect findings as each SendMessage to main arrives
[5] On idle without a completion message: read the idle notification's result, then SendMessage(to: "{name}") one status check
[6] No teardown: there is no team to shut down or delete
```

### Named-Agent Spawning

```
Agent {
  name: "structural-reviewer"     # Unique, descriptive — the address for messages
  subagent_type: "Explore"        # Determines tool access
  prompt: "..."                   # MUST be fully self-contained (see below)
}
```

> [!pitfall] Context Not Inherited
> **Problem:** Named agents start with fresh context — they do NOT inherit the orchestrator's file reads, research, or analysis.
> **Solution:** Include all critical context in the prompt: file paths, checklists, reporting format, and any findings they need. Share via explicit messages or file references; never assume shared state.

**Subagent type selection for named agents:**
| If task requires... | Use |
|--------------------|-----|
| Read-only (review, research, exploration) | `Explore` |
| Architecture planning | `Plan` |
| Writes or Bash | `general-purpose` |
| Project-specific behavior | Custom agent from `.claude/agents/` |

**Naming:** Use unique, descriptive names. Names are the address for messages.
```
structural-reviewer     # Role-based
ei-reviewer-1           # Role + index for multiples
impl-reviewer           # Role-based
```

### Phase Gating

For multi-phase reviews, gate on the first phase before spawning the rest:
1. Spawn Phase 1 reviewer (structural/validation)
2. WAIT for Phase 1 completion
3. If Phase 1 finds blockers → abort remaining phases
4. If Phase 1 passes → spawn Phase 2-N reviewers in parallel

---

## 7. Agent Communication

### Addresses

A spawned agent reaches the orchestrator with `SendMessage`. The address decides when the message arrives.

| Address | Reaches | Delivery, measured 2026-10-12 on Claude Code 2.1.296 | Use |
|---------|---------|------------------------------------------------------|-----|
| `main` | The orchestrator (the main conversation) | 3 of 3 arrived while the orchestrator was still working | Every report to the orchestrator |
| `{name}` | A named agent | The spawn result says it receives instructions through a mailbox. Not timed | Status checks from the orchestrator |
| `team-lead` | Legacy address | 3 of 3 returned success but arrived only after the orchestrator's turn ended | Never |

An unnamed subagent needs no address. Its final message returns to the orchestrator automatically, 3 of 3 in the same measurement.

### What Goes to `main`

| Scenario | Channel |
|----------|---------|
| Report individual finding | Message to `main` |
| Flag uncertain finding | Message to `main` with `[UNCERTAIN]` |
| Completion signal | Message to `main` |
| Status check on an idle agent | Message from the orchestrator to the agent's `name` |

### Finding Report Format

Reviewers report findings using this structured format:

```
[SEVERITY] Finding summary (one line)
File: {relative path}
Location: {section or line reference}
Issue: {what is wrong}
Fix: {concrete change — file + what to modify}
Confidence: HIGH | MEDIUM | LOW
```

### Uncertain Finding Protocol

When a reviewer has MEDIUM or LOW confidence, prefix the finding with `[UNCERTAIN]`. The orchestrator cross-checks uncertain findings against other reviewers' context before including in the final report. This is the primary false-positive reduction mechanism.

### Idle Named Agents

> [!pitfall] Idle Named Agents
> **Problem:** A named agent goes idle after every turn. This looks like it stopped working.
> **Solution:** Idle is NORMAL and EXPECTED. A named agent's plain-text reply is not lost, but it is late: it arrives only after the orchestrator's turn ends, in the `result` field of an idle notification (measured once, 2026-10-12, Claude Code 2.1.296). Have every named agent report with `SendMessage` to `main`, and send one status check by name when it goes idle without its completion message.
> **See also:** [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.7 (Idle-Mid-Step Wake-Up via SendMessage) for the operational wake-up protocol used by DELEGATED orchestrators.

Messages sent to `main` are delivered automatically — do NOT poll for them.

---

## 8. Scaling Rules

A team here means a group of named reviewers that the main conversation spawns. No team object exists.

> [!decide] Team vs Simple Subagents
> | Plan Size | Approach | Team Size |
> |-----------|----------|-----------|
> | Trivial (no EIs, <3 files) | No team — single subagent | 0 |
> | Small (1 EI, 1 sprint) | No team — 2-3 subagents sequentially | 0 |
> | Medium (2-3 EIs, 2+ sprints) | Team with standard composition | 3-4 reviewers + orchestrator |
> | Large (4-5 EIs, 3+ sprints) | Full team | 5 reviewers + orchestrator |
> | Very Large (6+ EIs) | Batch into max 5 reviewers | 5 reviewers + orchestrator (batch EIs) |
>
> **Crossover point:** Teams become worthwhile at **2+ EIs or 2+ sprints**. Below that, coordination overhead exceeds the benefit.

### Token Budget Per Reviewer Role

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

Rows 1, 2, 4 and 5 were re-measured on Claude Code 2.1.296 on 2026-10-12, for the `general-purpose` and `planwise:task-runner` subagents. The other rows are carried from earlier builds and were not re-measured. The enforcement mechanism column explains why each cannot be bypassed by prompting.

| # | Constraint | Enforcement Mechanism | Impact | Workaround |
|---|-----------|----------------------|--------|------------|
| 1 | No sub-subagent spawning | Planwise spawns only from the main conversation. Measured 2026-10-12 on Claude Code 2.1.296: the planwise task-runner's tool list has no Agent tool. A general-purpose subagent's list includes Agent, and a nested spawn from it was not tested | Single-level delegation only | Orchestrate all agents from main conversation; chain sequentially |
| 2 | Only the `main` address reaches the orchestrator inside its turn | Message routing. Measured 2026-10-12 on Claude Code 2.1.296: 3 of 3 sends to `main` arrived while the orchestrator was working, and 3 of 3 sends to `team-lead` arrived only after its turn ended | A report addressed to `team-lead` misses an orchestrator that waits inside one turn | Address the orchestrator as `main` in every spawn prompt |
| 3 | Context NOT inherited by spawned agents | Fresh context per spawn | Spawned agents start with empty context (see row 11 for shell state) | Self-contained prompts; share via explicit messages or file references |
| 4 | No AskUserQuestion in spawned contexts | Tool restriction | Cannot interactively prompt user | Pre-gather requirements before spawning |
| 5 | No EnterPlanMode/ExitPlanMode in spawned contexts | Tool restriction | Cannot enter plan mode | Plan in main session before delegating |
| 6 | Path-specific rules are main-session-only | Path rule loading requires OWN file activity | Spawned contexts see only global rules | Include rule content explicitly in task prompt |
| 7 | MCP unavailable in background subagents | Background execution mode restriction | Cannot use external systems | Run in foreground if MCP tools are required |
| 8 | Skill discovery ≠ system-prompt injection | File system access (Glob on `.claude/skills/`) | Mid-session agents not discoverable as subagent_type | Use `skills:` frontmatter to inject domain knowledge; all contexts discover existing skills via FS |
| 9 | Do not branch on a spawned agent's self-reported identity | The harness sets the identity line at spawn time. Not re-measured across contexts on this build | A check written against one identity string fails silently when a build changes it | Branch on the tools in the agent's own tool list, never on its identity line |
| 10 | Background pre-approval gate overrides `bypassPermissions` | Background agents auto-deny any permission not explicitly pre-approved at launch; `bypassPermissions` does NOT bypass this gate | Write/Edit/Bash calls silently fail if not pre-approved; agent continues without output | Launch write-producing agents in foreground; reserve background for read-only tasks |
| 11 | Spawned contexts inherit no shell state — the interpreter on `PATH` is the platform default, never the project's | Spawned shells start fresh: no inherited working directory, `PATH`, or activated environment. Extends row 3 (context non-inheritance) from conversational to shell state | Project-package imports fail and project-only dependencies appear absent. The agent typically reports the check as **environmentally impossible rather than failed** — a false PASS on everything it did reach | Name the project's interpreter path explicitly in every spawn prompt that runs project code. Have the first dispatch echo its resolved interpreter and HALT if it is not the project's. Emit the path form matching the project's OS |
| 12 | Writes under agent startup-config paths are gated as Self-Modification, and the decision is non-deterministic | A permission classifier protects agent/rule/skill/settings config paths independently of any workflow authorization; decisions vary **within a single batch**, and some denials are hard blocks that user authorization cannot clear | A multi-edit batch half-applies, leaving a config file internally inconsistent with no record of which edits landed. Naming the file as the deliverable across every plan tier does not pre-clear the gate | Keep config-file edit batches to the smallest coherent set — denials are per-call, so a large batch half-applies. Record applied-vs-denied state immediately. STOP and ask on denial; never retry verbatim in the same mode |

> [!hazard] Self-modification permission gates block live-config edits
> A harness may refuse an agent-initiated edit to a file that is itself part of the loaded agent configuration — rules, agent definitions, skill manifests. This is a platform constraint, not a bug, and is not always visible until the write is attempted. Operational consequence: any task whose deliverable is a change to the agent-config surface must be planned to run with the appropriate authorization, or to stage its output outside the config surface for a human to apply. Every rule-promotion task has this shape, so the gate fires routinely rather than exceptionally.

> **Constraint 6 — path rules detail:** Spawned contexts begin with zero file activity. Path rules check the context's OWN active files. If a spawned context later works on files matching a path rule's pattern, those rules CAN trigger dynamically for that context. What they do NOT do is inherit the parent session's already-active path triggers.

> **Constraint 8 — skills note:** The `skills:` frontmatter field injects SKILL.md content into the agent's context at startup — use it for domain knowledge needed immediately. It does not restrict which skills the agent can discover; all contexts with file system access can discover all project skills regardless of the `skills:` field.

> **Constraint 10 — background pre-approval detail:** Background subagents use an upfront pre-approval gate: before launch, Claude Code prompts for all permissions the agent will need. At runtime, anything not pre-approved is auto-denied — the tool call fails silently but the agent continues executing. `bypassPermissions` mode does NOT override this gate. Practical consequence: task-runner agents that write output files MUST run in foreground. Background mode is only safe for read-only operations (Explore, research).

> **Constraint 10 — background pre-approval hazard:** Design background agents for read-only operations only. Before launching a background agent that you believe needs Write/Edit/Bash, convert it to foreground mode. The pre-approval gate cannot be bypassed by prompting or by `bypassPermissions` mode — both are enforced at the runtime layer, not the policy layer.

---

## 11. DELEGATED Dispatch Discipline

When the Execution Strategy is DELEGATED (orchestrator spawns task-runner subagents), dispatch behavior — mandatory triggers, task-file error recovery, orchestration context boundary, and the full dispatch protocol set — is governed by the three-part DELEGATED dispatch discipline below. Section numbers run continuously across the three files, so a `§1.N` anchor names exactly one section.

| Part | File | Sections | Topic |
|---|---|---|---|
| 1 | [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) | §1.1–§1.13 | Declaration, foundations, and dispatch-prompt construction |
| 2 | [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) | §1.14–§1.22 | Dispatch mechanics and post-return handling |
| 3 | [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) | §1.23–§1.32 | Cross-cutting dispatch-prompt and orchestrator discipline |

The four mandatory DELEGATED triggers are canonical at [`references/session-plan-requirements.md`](session-plan-requirements.md) § Execution Strategy (Set by Planner); do not restate the trigger list here or in the extract — cite that section.

Verify-Before-Acting on LSP Diagnostics has similarly moved to `agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md` §1.18. Large-File Read Tactics (the paged-read ladder for files exceeding a Read-tool gate) has moved to [`references/session-context-budget.md` § Large-File Read Tactics](session-context-budget.md#large-file-read-tactics), the read-gate canonical.

---

*Cross-reference: [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md), [agent-orchestration-delegated.md](agent-orchestration-delegated.md) (§1.1–§1.13), [agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) (§1.14–§1.22), [agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) (§1.23–§1.32 — the three-part DELEGATED dispatch discipline), [session-context-budget.md](session-context-budget.md) (read-gate canonical + Large-File Read Tactics)*
