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
- [11. DELEGATED Dispatch Discipline](#11-delegated-dispatch-discipline)
- [12. Verify-Before-Acting on LSP Diagnostics](#12-verify-before-acting-on-lsp-diagnostics)
- [13. Large-File Read Tactics](#13-large-file-read-tactics)

---

## 1. Runtime Contexts

Claude Code has exactly four runtime contexts. Background mode, worktree isolation, plan mode, and `claude --agent` are **configurations** of these four, not additional types.

| Context | Created Via | System Prompt Identity | Tool Set |
|---------|-------------|----------------------|----------|
| **Main Session** | `claude` CLI / VS Code extension | "You are Claude Code, Anthropic's official CLI" | All tools (~24+) |
| **Subagent** | `Task` tool (`subagent_type` parameter) | **"You are Claude Code, Anthropic's official CLI"** | 18 tools (no Task, AskUserQuestion, PlanMode) |
| **Teammate** | `Task` tool with `team_name` + `name` | **"You are a Claude agent, built on Anthropic's Claude Agent SDK"** | 16 tools (no Task, TeamCreate/Delete, AskUserQuestion, PlanMode) |
| **Skill-Forked** | `Skill` tool with `context: fork` | **"You are Claude Code, Anthropic's official CLI"** | 18 tools (identical to Subagent) |

> **Surprise 1:** Subagents receive the **full** Claude Code system prompt. Official docs claim "not the full CC system prompt — custom prompt only." This is wrong. The `prompt` parameter in the Task tool is ADDITIONAL to the system prompt, not a replacement. Skill-Forked contexts receive the same full CC system prompt.

> **Surprise 2:** Teammates have a **different** identity ("Claude Agent SDK"), not the Claude Code system prompt. Documentation calling them "full, independent Claude Code sessions" is misleading — they use the Agent SDK identity and are pure workers.

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

> **Surprise 3:** Teammates have FEWER tools than standalone subagents. TeamCreate/Delete are restricted FROM teammates (to prevent workers from managing teams) but are available to subagents and skill-forked contexts. The restriction is inverted from the expected — team management tools are NOT reserved for team members, they are removed from team members.

---

## 3. Context Loading Matrix

*Source: ATD-S04-03-LoadingMatrix-Working.md — 21 cells, 18 tested (3 skipped, no MCP configured).*

| # | What Loads | Subagent | Teammate | Skill-Forked |
|---|-----------|---------|----------|-------------|
| 1 | System prompt identity | YES (CC CLI) | NO — different identity (Agent SDK) | YES (CC CLI) |
| 2 | CLAUDE.md | YES | YES | YES |
| 3 | All project skill descriptions | YES (via FS discovery) | YES | YES (via FS discovery) |
| 4 | MCP servers | YES (FG); NO (BG) | SKIP (no data) | **[UNVERIFIED]** |
| 5 | Conversation history | NO | NO | NO |
| 6 | Team tools | YES (all incl. TeamCreate/Delete) | PARTIAL (no TeamCreate/Delete) | YES (all) |
| 7 | Path-specific rules | NO (global only) | NO (global only) | NO (global only) |

> **Path rules are main-session-only:** All spawned contexts see only the global rule files. Path-specific rules load based on the context's OWN file activity — spawned contexts start with zero file activity so no path rules trigger at startup. Spawned contexts CAN trigger path rules after they begin working on matching files, but they do NOT inherit the parent session's active path triggers.

> **Surprise 5 — Skill discoverability:** All contexts discover all project skills via file system access (Glob on `.claude/skills/`). This is file system discoverability, not system-reminder injection. Mid-session created agents are NOT dynamically registered as available `subagent_type` values.

> **Surprise 6 — Path rules:** Even teammates ("full, independent sessions") do NOT load path-specific rules. This is the clearest empirical distinction between teammate and main session contexts. All non-main contexts see the same global rules.

> **Skill-Forked MCP:** MCP availability in skill-forked contexts is [UNVERIFIED]. Mechanism equivalence with subagents (verified across all other rows) suggests MCP should be available in foreground mode if configured, but requires empirical confirmation with a configured MCP server.

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

> **Surprise 4:** Subagents CAN create team shells (TeamCreate works), but cannot add teammates (Task tool absent). The enforcement is at the Task tool level, not at TeamCreate. Main session could theoretically add teammates to a subagent-created team. Design around this — do not rely on it.

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

### Plugin Handler Spawns Resolve in the Consumer's Scope Chain

> [!pitfall] Un-Namespaced Plugin-Handler Spawn
> **Problem:** A plugin handler that spawns an agent by bare name (e.g., `subagent_type: "plan-reviewer"`) resolves the agent in the CONSUMER PROJECT's scope chain, not the plugin's scope chain. If the consumer has not run `/planwise init`, the agent file does not exist in `.claude/agents/` and the spawn fails with "agent not found".
>
> This constraint was empirically verified 2026-05-12 (behavior may not be re-verified).
>
> **Solution:** Plugin handlers MUST spawn agents with the plugin-namespaced form: `subagent_type: "{plugin-name}:plan-reviewer"`. The `{plugin-name}:` prefix forces resolution against the plugin's own `agents/` directory, bypassing the consumer scope chain.
>
> WRONG (bare name — fails if consumer has no plan-reviewer agent):
> ```
> Task(
>   subagent_type: "plan-reviewer",
>   ...
> )
> ```
> CORRECT (plugin-namespaced — always resolves against plugin agents/):
> ```
> Task(
>   subagent_type: "{plugin-name}:plan-reviewer",
>   ...
> )
> ```
> See `handlers/review.md` (9 sites), `handlers/run.md` (4 sites), `handlers/backlog.md` (1 site) for spawn-call updates.

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
> **See also:** [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.7 (Idle-Mid-Step Wake-Up via SendMessage) for the operational wake-up protocol used by DELEGATED orchestrators.

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
| 2 | Teammates lack Task, TeamCreate, TeamDelete | Tool restriction at spawn time | Cannot spawn, cannot create/delete teams | All delegation through team lead (hub-and-spoke mandatory) |
| 3 | Context NOT inherited by subagents/teammates | Fresh context per spawn | Teammates start with empty context | Self-contained prompts; share via explicit messages or file references |
| 4 | No AskUserQuestion in spawned contexts | Tool restriction | Cannot interactively prompt user | Pre-gather requirements before spawning |
| 5 | No EnterPlanMode/ExitPlanMode in spawned contexts | Tool restriction | Cannot enter plan mode | Plan in main session before delegating |
| 6 | Path-specific rules are main-session-only | Path rule loading requires OWN file activity | Spawned contexts see only global rules | Include rule content explicitly in task prompt |
| 7 | MCP unavailable in background subagents | Background execution mode restriction | Cannot use external systems | Run in foreground if MCP tools are required |
| 10 | Background pre-approval gate overrides `bypassPermissions` | Background agents auto-deny any permission not explicitly pre-approved at launch; `bypassPermissions` does NOT bypass this gate | Write/Edit/Bash calls silently fail if not pre-approved; agent continues without output | Launch write-producing agents in foreground; reserve background for read-only tasks |
| 8 | Skill discovery ≠ system-prompt injection | File system access (Glob on `.claude/skills/`) | Mid-session agents not discoverable as subagent_type | Use `skills:` frontmatter to inject domain knowledge; all contexts discover existing skills via FS |
| 9 | Teammate identity is Agent SDK, not CC CLI | System prompt differentiation at spawn time | Teammates self-identify differently; less "Claude Code aware" | Design teammates as workers; orchestrate from main session |

> **Constraint 6 — path rules detail:** Spawned contexts begin with zero file activity. Path rules check the context's OWN active files. If a spawned context later works on files matching a path rule's pattern, those rules CAN trigger dynamically for that context. What they do NOT do is inherit the parent session's already-active path triggers.

> **Constraint 8 — skills note:** The `skills:` frontmatter field injects SKILL.md content into the agent's context at startup — use it for domain knowledge needed immediately. It does not restrict which skills the agent can discover; all contexts with file system access can discover all project skills regardless of the `skills:` field.

> **Constraint 10 — background pre-approval detail:** Background subagents use an upfront pre-approval gate: before launch, Claude Code prompts for all permissions the agent will need. At runtime, anything not pre-approved is auto-denied — the tool call fails silently but the agent continues executing. `bypassPermissions` mode does NOT override this gate. Practical consequence: task-runner agents that write output files MUST run in foreground. Background mode is only safe for read-only operations (Explore, research).

> **Constraint 10 — background pre-approval hazard:** Design background agents for read-only operations only. Before launching a background agent that you believe needs Write/Edit/Bash, convert it to foreground mode. The pre-approval gate cannot be bypassed by prompting or by `bypassPermissions` mode — both are enforced at the runtime layer, not the policy layer.

> **Team tool compatibility:** TeamCreate and SendMessage are not listed in the `allowed-tools` frontmatter system. Skills that need team functionality should use `context: fork` with `agent: general-purpose`. Do NOT attempt to list TeamCreate or SendMessage in `allowed-tools`.

---

## 11. DELEGATED Dispatch Discipline

When the Execution Strategy is DELEGATED (orchestrator spawns task-runner subagents), the following subsections govern dispatch behavior. These rules apply whenever any DELEGATED trigger is present (see `references/session-plan-requirements.md` Execution Strategy section for mandatory triggers).

### 11.1 Mandatory Triggers

DELEGATED mode is REQUIRED when ANY of the following triggers are present in a session:
- Session has 2 or more Opus tasks
- Session is part of a META Discovery phase
- Any single task estimates >50K token context load
- Sequential tasks where one task's output is the next task's input (output-chaining)

**The Master Plan's Execution Strategy section MUST name the trigger that fired for every DELEGATED session, and `/planwise review` MUST surface as a BLOCKING finding any DELEGATED declaration without a named trigger.**

Declaring DELEGATED is a PLANNING decision (made in the Orchestration file), not an execution-time inference.

> [!constraint] DELEGATED Declaration — Planning Time Only
> WRONG — orchestrator infers DELEGATED at runtime after reading context:
> ```
> # Orchestration file: Execution Strategy: DIRECT
> # (then orchestrator discovers tasks are too large and pivots at runtime)
> ```
> CORRECT — planner declares DELEGATED trigger in Orchestration before execution:
> ```
> ## Execution Strategy
> Mode: DELEGATED
> Trigger: Task 03 estimates >50K context load (output-chaining to Task 04)
> ```

> [!constraint] Name the Trigger — Not "For Consistency"
> "Consistency" across a multi-session plan is not a trigger; every DELEGATED session must name one of the four mandatory triggers above.
> WRONG: plan declares DELEGATED for all 8 sessions "for consistency"; only Sprint 01 meets a trigger (95K Opus task + output-chaining); Sprints 02-08 each have a single 23-41K task within the 100K DIRECT budget — ~378K of subagent-spawn overhead consumed for no gain.
> CORRECT: Sprint 01 declares DELEGATED (#1 + #4); Sprints 02-08 declare DIRECT.

### 11.2 Task-File Error Recovery

When a DELEGATED subagent fails or produces incomplete output, the orchestrator applies this recovery shape:

1. Read the subagent's partial output (from its output file or Recovery file)
2. Assess whether partial output is usable as-is or requires retry
3. If retry needed: spawn a new subagent with explicit "resume from step N" instructions
4. Cap retries at 3 attempts per task; after 3 failures mark task BLOCKED in Recovery

> [!constraint] Retry Cap — DELEGATED Task Failure
> WRONG — orchestrator retries indefinitely, consuming budget:
> ```
> (Task fails) → retry → (fails again) → retry → (fails again) → retry...
> ```
> CORRECT — retry cap of 3; after 3 mark BLOCKED and report:
> ```
> Attempt 1: FAILED (output file missing)
> Attempt 2: FAILED (partial output, <50% coverage)
> Attempt 3: FAILED (subagent stopped mid-execution)
> → Mark task BLOCKED in Recovery; report to orchestrator
> ```

### 11.3 Orchestration Context Boundary

When Execution Strategy is DELEGATED:
- Orchestration's Required Context MUST list ONLY plan files (Orchestration.md, Recovery.md, task files)
- Heavy context files (reference docs, codebase modules, large output files) MUST appear ONLY in individual task file Required Context sections
- The orchestrator reads plan files only; subagents read their full task-specific context with fresh ~100K budget

> [!constraint] DELEGATED Context Boundary
> WRONG — Orchestration Required Context loads heavy files (orchestrator context fills before dispatching):
> ```
> ## Required Context
> | 1 | references/agent-orchestration.md | ~440 | ~6K | Rule reference |
> | 2 | src/models/schema.sql | ~1200 | ~15K | Schema for tasks |
> | 3 | Outputs/research-part-1.md | ~480 | ~6K | Research for tasks |
> ```
> CORRECT — Orchestration Required Context contains only plan files; heavy context in task files:
> ```
> ## Required Context
> | 1 | {Abbrev}-S{XX}-{YY}-Orchestration.md | ~80 | ~1K | Task list |
> | 2 | {Abbrev}-S{XX}-{YY}-Recovery.md | ~40 | ~0.5K | Progress state |
>
> (Task 03 Required Context loads schema.sql + research-part-1.md in its own section)
> ```

### 11.4–11.15 DELEGATED Dispatch Protocols (extracted)

> **§11.4–§11.15 DELEGATED Dispatch Protocols** have been extracted to [`references/agent-orchestration-delegated.md`](agent-orchestration-delegated.md) (renumbered there as §1.4–§1.15, mapping mechanically from §11.N → §1.N). Read that file when orchestrating a DELEGATED session. The extracted subsections cover: §1.4 inter-dispatch diagnostics verification (+ orchestrator `wc -l` check); §1.5 live-HTTP-probing tool-use budget; §1.6 path-scoped rule injection in spawn prompts; §1.7 idle-mid-step wake-up via SendMessage; §1.8 HARD CONSTRAINTS spawn-prompt skeleton + SCOPE BOUNDARY clause; §1.9 tier-ranking fixes by invasiveness; §1.10 forward-looking-verb detection + resume protocol; §1.11 operational-ceiling disclaimers; §1.12 N>25 edit-task resume protocol; §1.13 shared-edit-target strategy matrix (incl. parallel-dispatch Recovery reconciliation); §1.14 orchestrator-only review commands; §1.15 delegated code task-runners build LAST. Downstream cross-references in `handlers/review.md` (Error Pattern Catalog), `agents/plan-reviewer.md`, and `handlers/run.md` cite the extract's §1.N anchors.

---

## 12. Verify-Before-Acting on LSP Diagnostics

> [!practice] LSP Diagnostic Verification
> LSP diagnostics ({type-checker}/`{linter}`/rust-analyzer/gopls) may go stale when the underlying source file is edited mid-session. Before acting on a diagnostic (e.g., adding an import, fixing a type), verify the diagnostic is still live.

### Stale vs Live Diagnostic Decision Matrix

| Signal | Likely Stale | Likely Live |
|--------|--------------|-------------|
| Diagnostic line number > file's actual line count | Yes | — |
| Diagnostic mentions identifier not present in file | Yes | — |
| Diagnostic timestamp predates last edit | Yes | — |
| Diagnostic re-fired after LSP refresh | — | Yes |
| Same diagnostic appears across multiple unrelated files | Yes (index drift) | — |
| Diagnostic references a type that was recently renamed | Yes | — |

**When a diagnostic is likely stale:**
1. Trigger an LSP refresh (close and reopen the file, or run `{lint-cmd}` from CLI)
2. If diagnostic is gone after refresh → it was stale; do NOT act on it
3. If diagnostic persists after refresh → it is live; act on it

**When to act without refreshing:**
- Diagnostic is confirmed live (matches current file content at the reported line)
- Diagnostic was emitted by a CLI tool run this session (not cached from prior session)

---

## 13. Large-File Read Tactics

> [!practice] Ladder for Files Exceeding a Read-Tool Gate
> The Read tool has **two** mechanical gates (NOT a single ~13K/~1000-line budget):
> - **Token page-cap gate (model-dependent):** above **~25,000 tokens** a single Read returns only the first page (truncates). Tokens use the runner model's tokenizer — `~13 tok/line` Sonnet/Haiku, `~19 tok/line` Opus, so Opus trips at **~1,340 lines** vs Sonnet/Haiku's **~1,920**.
> - **Byte gate (model-independent):** a file ≥ **262,144 bytes (256 KiB)** is refused outright unless `offset`/`limit` is passed.
>
> When a file crosses either gate, apply this ladder in order — stop at the first step that succeeds. These gates and their constants are documented in [`references/session-context-budget.md` § Read-Tool Hard Limits](session-context-budget.md#read-tool-hard-limits); they are FIXED harness facts (defined in `scripts/token_saver.py`), not `/context`-measured budgets, and a `read`-reason Critical is NOT resolvable by routing to a 1M-window model.

**Step 1 — Paged Read (`offset`/`limit`):** Read the file in pages that each stay under the gate, then stitch them. After each page, **check the returned content for the `PARTIAL view` truncation header** — its presence means the Read was truncated and more pages remain; do NOT assume one Read returned the whole file.

```bash
# Example: page a 2,400-line file in ~900-line windows (safe for both models)
Read(path: "{src/module/file.ext}", offset: 1, limit: 900)     # check for "PARTIAL view" header
Read(path: "{src/module/file.ext}", offset: 901, limit: 900)   # continue until the file is fully covered
```

**Step 2 — Output-clear pre-step:** Clear conversation output buffer before reading. Freed budget enables a larger Read call. Effective when the conversation history is large but the file itself is borderline.

**Step 3 — Substitution:** Read a smaller substitute:
- Adjacent `*.md` documentation next to the `{src/module/file.ext}` source file
- A smaller version-compatible equivalent (e.g., a config file that describes the large source file's structure)

**Step 4 — Grep-based scanning:** Use Grep with `output_mode: "content"` and context lines to extract the needed sections without a full Read. Effective when you know which section or function you need.

```bash
# Example: extract a specific function from a large file
Grep(pattern: "def {symbol}", path: "{src/module/file.ext}", output_mode: "content", context: 30)
```

**Step 5 — Script-based extraction:** For structured files (JSON/YAML), use a Bash command via `jq`/`yq` to project only relevant fields:

```bash
# Example: extract a specific key from a large YAML config
Bash("yq '.{config-field}' {src/module/file.ext}")
```

### Module Split Threshold (cross-reference)

For adapter/client modules whose row dataclass exceeds 75-80 fields, see the Module Split Threshold subsection in `references/session-plan-requirements.md`. Large-file read tactics are orthogonal to the module split decision — apply both when applicable.

---

*Cross-reference: [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*
