---
description: Agent runtime contexts, tool access, context loading, nesting rules, named-agent coordination, and execution modes
consult-when: Choosing agent runtime context, tool access, nesting, named-agent coordination, execution mode
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
| **Subagent** | `Agent` tool, no `name` | `general-purpose`: 20 tools in the background, 31 in the foreground. A custom agent: its `tools:` list (§2) |
| **Named agent** | `Agent` tool with `name` | Not measured |
| **Skill-Forked** | `Skill` tool with `context: fork` | 31 tools, including `Agent` (§2) |

Measured 2026-10-12 on Claude Code 2.1.296: a named spawn returned "Spawned successfully" and said it receives instructions through a mailbox. `ListAgents` lists named agents apart from unnamed subagents. An unnamed spawn returned "Async agent launched successfully".

### Built-in Subagent Types

| Type | Model | Tools | Best For |
|------|-------|-------|---------|
| `Explore` | Sonnet in the measured run, under a Sonnet parent | No Edit, Write or NotebookEdit. Has Read, Glob, Grep, Bash, PowerShell, WebFetch and WebSearch | Fast codebase search, exploration, no writes |
| `Plan` | Inherit | Same set as `Explore` | Architecture research in plan mode |
| `general-purpose` | Inherit | 20 tools in the background, 31 in the foreground (§2) | Code changes, file writes, bash commands |
| `Bash` | Inherit | Bash only | Terminal commands in a clean context |
| `statusline-setup` | Sonnet | Read, Edit | Status line configuration via `/statusline` |
| `claude-code-guide` | Haiku | Limited | Questions about Claude Code features |
| Custom agent name | Per definition | Per definition | Project-specific behavior from `.claude/agents/` |

The `Explore` and `Plan` rows were measured 2026-10-25 on Claude Code 2.1.310, one run each, with tool lists self-reported. Neither agent loads CLAUDE.md or any rule file (§3). Put everything an `Explore` or `Plan` spawn needs in its prompt.

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

*Main session column: measured 2026-10-12 on Claude Code 2.1.296, loaded plus deferred tools. Subagent columns: measured 2026-10-25 on Claude Code 2.1.310, one run per column, self-reported by an unnamed spawn, with the test's own MCP tool left out of the totals. A custom agent's set follows its `tools:` frontmatter, so the task-runner column shows one definition, not a context property.*

| Tool | Main session | `general-purpose`, background | `general-purpose`, foreground | `planwise:task-runner` |
|------|-------------|-------------------------------|-------------------------------|------------------------|
| Agent (spawner) | YES | YES | YES | NO |
| TeamCreate, TeamDelete | NO | NO | NO | NO |
| SendMessage | YES | YES | YES | YES |
| SubagentHandback | NO | YES | YES | YES |
| ListAgents | YES | NO | YES | NO |
| AskUserQuestion | YES | NO | NO | NO |
| EnterPlanMode, ExitPlanMode | YES | NO | NO | NO |
| Skill | YES | YES | YES | NO |
| TaskCreate, TaskGet, TaskList | YES | NO | YES | NO |
| TaskUpdate | YES | NO | NO | NO |
| TaskStop | YES | YES | YES | NO |
| Workflow | YES | NO | NO | NO |
| CronCreate, CronDelete, CronList, PushNotification, RemoteTrigger | not measured | NO | YES | NO |
| DesignSync, ReportFindings | not measured | NO | YES | NO |
| LSP, PowerShell | not measured | YES | YES | NO |
| Read, Write, Edit, Glob, Grep, Bash | YES | YES | YES | YES |
| NotebookEdit, WebFetch, WebSearch, ToolSearch | YES | YES | YES | YES |
| EnterWorktree, ExitWorktree, Monitor | YES | YES | YES | NO |
| Total tools | 56 | 20 | 31 | 12 |

Two tool families share a word. The **Agent tool** spawns a subagent; Claude Code renamed it from `Task` in version 2.1.63, and the old name still works as an alias. The **Task tools** (`TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`) are the session checklist and replaced the legacy `TodoWrite`. This plugin uses the Task tools for progress tracking and never `TodoWrite`.
In the measured lists, a background subagent holds none of the checklist tools. A foreground `general-purpose` subagent listed `TaskCreate`, `TaskGet` and `TaskList`, but not `TaskUpdate`.

---

## 3. Context Loading Matrix

*Measured 2026-10-25 on Claude Code 2.1.310, one run per cell. Each source carried a unique random string, and a spawn with no tool calls was asked to list every such string in its context. The Subagent column covers `general-purpose`, all eight planwise agents and two custom agents.*

| # | What Loads | Subagent | `Explore`, `Plan` | Skill-Forked |
|---|-----------|---------|-------------------|-------------|
| 1 | CLAUDE.md | YES | NO | YES |
| 2 | Global rules (no `paths:`) | YES | NO | YES |
| 3 | Project skill descriptions | YES with the `Skill` tool; NO without it | YES | YES |
| 4 | MCP servers | YES, foreground and background, unless a `tools:` list leaves them out | YES | YES |
| 5 | Conversation history | NO | NO | NO |
| 6 | Path-specific rules at spawn | NO | NO | NO |
| 7 | Path-specific rules after the context's own matching read | YES | Not measured | Not measured |
| 8 | Path-specific rules the parent already triggered | NO | Not measured | Not measured |
| 9 | A plugin reference that is not installed as a rule | NO | NO | NO |

Rows 6 to 8 (path rules) and row 3 (skill listing) are stated as constraints in §10 rows 3, 6 and 8.

> **A reference is not context:** A plugin reference file reaches a spawned context only when the context reads it, or when it is installed as a global rule. Naming a reference in an agent definition loads nothing.

> **Skill-Forked MCP:** A live test confirmed row 4 for the foreground: a `context: fork` skill loaded an MCP tool via `ToolSearch`, and the call returned a real result. Background skill-forked MCP was not exercised.

---

## 4. Nesting Rules

| # | From → To | Result | Basis |
|---|-----------|--------|-------|
| 1 | Main → Subagent | **YES** | Measured 2026-10-12 |
| 2 | Main → Named agent | **YES** | Measured 2026-10-12 |
| 3 | Subagent → anything | **Not used by planwise** | `general-purpose` lists `Agent` (measured 2026-10-12). A nested spawn was not tested. `planwise:task-runner` has no `Agent` |
| 4 | Skill-Forked → anything | **Not used by planwise** | A forked skill lists `Agent` (measured 2026-10-25 on Claude Code 2.1.310). A nested spawn was not tested |

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

**Automatic delegation:** Claude reads every agent `description` and auto-delegates matching tasks. "Use proactively" in the description signals auto-delegation without explicit prompting.

**Explicit delegation:** The user names the agent (`Use the code-reviewer agent`). Claude resolves the name, preloads listed skills, and launches.

**Disabling agents:** Add `"Agent(agent-name)"` to `permissions.deny` in `.claude/settings.json` (project-wide), or pass `--disallowedTools "Agent(agent-name)"` (session only). The older `"Task(agent-name)"` form still works as an alias.

### Orchestration Patterns

- **Isolate high-volume operations:** tests, docs and log scans run in a subagent that returns only a summary, when only the summary matters to the main context.
- **Parallel research:** independent investigations run at once, each in a fresh context, with no data dependencies between them. The lead synthesizes after all complete.
- **Chain subagents:** each step depends on the previous result. Pass context explicitly between steps. It is NOT shared automatically.
- **Resume a previous subagent:** a resumed agent keeps its full history. Resume when the next step needs prior reasoning. Start a new instance when independent context budget matters more.

> [!constraint] Context Cost Warning
> WRONG: Spawn 10 subagents with verbose output → main conversation hits context ceiling
> CORRECT: Instruct subagents to return summaries only

### Agent Scope (Where to Define)

Four locations define an agent, and the highest-priority location wins a name clash. The scope and priority table, with the use case for each location, lives in [agent-authoring.md](agent-authoring.md) §3.

**Managing agents:** `/agents` — view, create, edit, delete in the UI. `claude agents` — list from the command line.

### Subagent vs Persistent Agent

A **subagent** (spawned via `Agent`) is ephemeral: one task, one result. A **persistent agent** (defined in `.claude/agents/`) is reusable and named. Use one when a role recurs, tool restrictions must hold consistently, or delegation by description is wanted.

### Plugin Handler Spawns Resolve in the Consumer's Scope Chain

> [!pitfall] Un-Namespaced Plugin-Handler Spawn
> **Problem:** A plugin handler that spawns an agent by bare name (e.g., `subagent_type: "plan-reviewer"`) resolves it in the CONSUMER PROJECT's scope chain, not the plugin's. The plugin never installs an agent file in `.claude/agents/`, so the spawn fails with "agent not found". Verified 2026-05-12, not re-verified since.
>
> **Solution:** Plugin handlers MUST spawn agents with the plugin-namespaced form: `subagent_type: "{plugin-name}:plan-reviewer"`. The prefix forces resolution against the plugin's own `agents/` directory.
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
> `tests/test_handler_spawn_namespacing.py` fails on any handler `subagent_type` that is neither a built-in type nor prefixed. It pins no site count.

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

Reviewers report each finding in the six-line format (severity and summary, `File`, `Location`, `Issue`, `Fix`, `Confidence`) that [review-finding-format.md](review-finding-format.md) § Finding Report Format holds, with its Severity Classification table.

### Uncertain Finding Protocol

A reviewer with MEDIUM or LOW confidence prefixes the finding with `[UNCERTAIN]`. The orchestrator cross-checks it against other reviewers' context before including it in the final report. This is the primary false-positive reduction mechanism.

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
> | MCP tools | Available | Available |
> | How to trigger | `run_in_background: false` on the `Agent` call | Omit `run_in_background` (the default for an unnamed spawn), set it to `true`, set `background: true` in frontmatter, or press Ctrl+B |

> [!constraint] Ask for foreground explicitly
> Measured 2026-10-25 on Claude Code 2.1.310: an unnamed `Agent` call that omitted `run_in_background` ran in the background in 15 of 15 spawns. That covered `general-purpose`, `Explore`, `Plan`, six planwise agents and two custom agents. The harness reported each with `is_backgrounded: true`. A background `general-purpose` subagent also listed a configured MCP server's tool, so background mode no longer withholds MCP. Re-measured 2026-11-13 on Claude Code 2.1.325, one run per agent: two background `general-purpose` subagents listed and called an MCP tool. A background `planwise:task-runner`, whose `tools:` list names no MCP tool, saw none and could not load one through `ToolSearch`.
>
> WRONG — rely on the default and expect a foreground run:
> ```
> Agent(subagent_type: "planwise:task-runner", prompt: ...)
> ```
> CORRECT — name the mode on every call that needs the foreground:
> ```
> Agent(subagent_type: "planwise:task-runner", run_in_background: false, prompt: ...)
> ```

### Background Pre-Approval

The §9 table and §10 row 10 hold the pre-approval gate: declare every permission upfront, and never use `AskUserQuestion` in the background.

**Background failure:** If a background agent fails due to missing permissions, resume it in foreground to retry with interactive permission approval.

---

## 10. Constraints

Rows 1, 2, 4 and 5 were re-measured on Claude Code 2.1.296 on 2026-10-12, for the `general-purpose` and `planwise:task-runner` subagents. Rows 3, 6, 7 and 8 were re-measured on Claude Code 2.1.310 on 2026-10-25, by the §3 method. The other rows are carried from earlier builds and were not re-measured. The enforcement mechanism column explains why each cannot be bypassed by prompting.

| # | Constraint | Enforcement Mechanism | Impact | Workaround |
|---|-----------|----------------------|--------|------------|
| 1 | No sub-subagent spawning | Planwise spawns only from the main conversation. Measured 2026-10-12 on Claude Code 2.1.296: the planwise task-runner's tool list has no Agent tool. A general-purpose subagent's list includes Agent, and a nested spawn from it was not tested | Single-level delegation only | Orchestrate all agents from main conversation; chain sequentially |
| 2 | Only the `main` address reaches the orchestrator inside its turn | Message routing. Measured 2026-10-12 on Claude Code 2.1.296: 3 of 3 sends to `main` arrived while the orchestrator was working, and 3 of 3 sends to `team-lead` arrived only after its turn ended | A report addressed to `team-lead` misses an orchestrator that waits inside one turn | Address the orchestrator as `main` in every spawn prompt |
| 3 | Conversation NOT inherited by spawned agents | Fresh conversation per spawn | Spawned agents start without the parent's conversation, path triggers and loaded skills. They still load CLAUDE.md and global rules, except `Explore` and `Plan`, which load neither (§3; see row 11 for shell state) | Self-contained prompts; share via explicit messages or file references |
| 4 | No AskUserQuestion in spawned contexts | Tool restriction | Cannot interactively prompt user | Pre-gather requirements before spawning |
| 5 | No EnterPlanMode/ExitPlanMode in spawned contexts | Tool restriction | Cannot enter plan mode | Plan in main session before delegating |
| 6 | Path-specific rules are not inherited at spawn | Path rule loading requires OWN file activity | A spawned context starts with global rules only. A path rule loads after the context itself reads a matching file (one Read loaded it for `general-purpose` and `planwise:task-runner`). The parent's active path triggers never carry over, even for a file the parent read before spawning | Include rule content explicitly in the task prompt when the context needs it before its first matching read |
| 7 | A `tools:` list decides MCP access | The definition's `tools:` allowlist. Background mode does not withhold MCP (§9) | Every measured planwise agent, each with a `tools:` list, had no MCP tool. `general-purpose`, `Explore` and `Plan` had the configured server's tool | Omit `tools:`, or add the server's tools to it (not measured) |
| 8 | The skill listing reaches only contexts with the `Skill` tool | The project skill descriptions arrive with the `Skill` tool | A custom agent whose `tools:` list omits `Skill` sees no project skills unless it searches `.claude/skills/` with `Glob`. A skill the parent invoked does not reach the child. Mid-session agents not discoverable as subagent_type ([agent-authoring.md](agent-authoring.md) §5) | Use `skills:` frontmatter to inject a skill's full body at startup. It does not restrict which skills the agent can find. Measured 2026-10-25 on Claude Code 2.1.310: the body arrived, a supporting file linked from it did not |
| 9 | Do not branch on a spawned agent's self-reported identity | The harness sets the identity line at spawn time. Not re-measured across contexts on this build | A check written against one identity string fails silently when a build changes it | Branch on the tools in the agent's own tool list, never on its identity line |
| 10 | Background pre-approval gate overrides `bypassPermissions` | Before launch, Claude Code prompts for every permission the agent will need, and auto-denies anything not pre-approved. `bypassPermissions` does NOT bypass this gate, and neither does prompting: both act at the runtime layer, not the policy layer | Write/Edit/Bash calls silently fail if not pre-approved; agent continues without output | Launch write-producing agents in foreground; reserve background for read-only tasks. The plugin hook `hooks/agent-guard.ts` denies a `planwise:task-runner` Agent call that sets `run_in_background: true` |
| 11 | Spawned contexts inherit no shell state — the interpreter on `PATH` is the platform default, never the project's | Spawned shells start fresh: no inherited working directory, `PATH`, or activated environment. Extends row 3 (context non-inheritance) from conversational to shell state | Project-package imports fail and project-only dependencies appear absent. The agent typically reports the check as **environmentally impossible rather than failed** — a false PASS on everything it did reach | Name the project's interpreter path explicitly in every spawn prompt that runs project code. Have the first dispatch echo its resolved interpreter and HALT if it is not the project's. Emit the path form matching the project's OS |
| 12 | Writes under agent startup-config paths are gated as Self-Modification, and the decision is non-deterministic | A permission classifier protects agent/rule/skill/settings config paths independently of any workflow authorization; decisions vary **within a single batch**, and some denials are hard blocks that user authorization cannot clear | A multi-edit batch half-applies, leaving a config file internally inconsistent with no record of which edits landed. Naming the file as the deliverable across every plan tier does not pre-clear the gate | Keep config-file edit batches to the smallest coherent set — denials are per-call, so a large batch half-applies. Record applied-vs-denied state immediately. STOP and ask on denial; never retry verbatim in the same mode |

> [!hazard] Self-modification permission gates block live-config edits
> Row 12 is a platform constraint, not a bug, and it is often invisible until the write is attempted. A task whose deliverable changes the agent-config surface (rules, agent definitions, skill manifests) runs with the needed authorization, or stages its output outside that surface for a human to apply. Every rule-promotion task has this shape, so the gate fires routinely.

Row 10 in practice: a task-runner that writes output files MUST run in the foreground. Before launching a background agent that needs Write, Edit or Bash, convert it to the foreground.

---

## 11. DELEGATED Dispatch Discipline

When the Execution Strategy is DELEGATED (orchestrator spawns task-runner subagents), dispatch behavior — mandatory triggers, task-file error recovery, orchestration context boundary, and the full dispatch protocol set — is governed by the four-part DELEGATED dispatch discipline. Section numbers run continuously across the four files, so a `§1.N` anchor names exactly one section.

The part table in [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) names the file that holds each `§1.N`.

The four mandatory DELEGATED triggers are canonical at [`references/session-plan-requirements.md`](session-plan-requirements.md) § Execution Strategy (Set by Planner); do not restate the trigger list here or in the extract — cite that section.

Verify-Before-Acting on LSP Diagnostics has similarly moved to `agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md` §1.18. Large-File Read Tactics (the paged-read ladder for files exceeding a Read-tool gate) has moved to [`references/session-context-budget.md` § Large-File Read Tactics](session-context-budget.md#large-file-read-tactics), the read-gate canonical.

---

*Cross-reference: [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md), [agent-orchestration-delegated.md](agent-orchestration-delegated.md) (§1.1–§1.13), [agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) (§1.14–§1.22), [agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) (§1.23–§1.28), [agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md) (§1.29–§1.32 — the four-part DELEGATED dispatch discipline), [session-context-budget.md](session-context-budget.md) (read-gate canonical + Large-File Read Tactics)*
