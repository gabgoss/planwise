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

### Plugin Handler Spawns Resolve in the Consumer's Scope Chain

> [!pitfall] Un-Namespaced Plugin-Handler Spawn
> **Problem:** A plugin handler that spawns an agent by bare name (e.g., `subagent_type: "plan-reviewer"`) resolves the agent in the CONSUMER PROJECT's scope chain, not the plugin's scope chain. If the consumer has not run `/planwise init`, the agent file does not exist in `.claude/agents/` and the spawn fails with "agent not found".
>
> PLG-017 documents this constraint (empirically verified 2026-05-12; behavior may not be re-verified).
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
> See `handlers/review.md` (7 sites), `handlers/run.md` (4 sites), `handlers/backlog.md` (1 site) for spawn-call updates.

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

### DELEGATED Dispatch Discipline

When the Execution Strategy is DELEGATED (orchestrator spawns task-runner subagents), the following subsections govern dispatch behavior. These rules apply whenever any DELEGATED trigger is present (see `references/session-plan-requirements.md` Execution Strategy section for mandatory triggers).

#### 11.1 Mandatory Triggers (PLG-002)

DELEGATED mode is REQUIRED when ANY of the following triggers are present in a session:
- Session has 2 or more Opus tasks
- Session is part of a META Discovery phase
- Any single task estimates >50K token context load
- Sequential tasks where one task's output is the next task's input (output-chaining)

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

#### 11.2 Task-File Error Recovery (PLG-002)

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

#### 11.3 Orchestration Context Boundary (PLG-002)

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

#### 11.4 Inter-Dispatch Diagnostics Verification (PLG-002 + PLG-020 extension)

When DELEGATED dispatches modify shared files (e.g., a shared algorithm module or schema file), the orchestrator MUST independently run the project's primary diagnostic command between dispatches to verify no regression:

- Run `{lint-cmd}` (or equivalent) on the shared file after each dispatch that modifies it
- Run `{precheck-cmd}` if the shared file is a data-layer contract (schema, config)
- If diagnostics fail: halt subsequent dispatches; surface the failure in Recovery before retrying

**PLG-020 extension — orchestrator `wc -l` verification:**

After each dispatch that produces output files, the orchestrator MUST run `wc -l` on every output file and compare against the Expected Output line budget declared in the task file. Deviations >20% from the declared budget are a signal to review before proceeding to the next dispatch.

> [!constraint] Inter-Dispatch Diagnostic Check
> WRONG — orchestrator dispatches all tasks in sequence without diagnostics between:
> ```
> Dispatch Task 01 → (completes) → Dispatch Task 02 → (completes) → Dispatch Task 03
> (no diagnostic check; regression from Task 01 propagates silently to Task 03)
> ```
> CORRECT — orchestrator runs diagnostics on shared files between dispatches:
> ```
> Dispatch Task 01 → run {lint-cmd} {src/module/file.ext} → CLEAN → Dispatch Task 02
> Dispatch Task 02 → run {lint-cmd} {src/module/file.ext} → 2 errors → HALT → fix before Task 03
> ```

#### 11.5 Live-HTTP-Probing Tool-Use Budget Reservation (PLG-012)

When a DELEGATED subagent performs live HTTP probing (WebFetch/WebSearch calls in a loop), the orchestrator MUST reserve tool-use budget for this activity:

- Cap: 30 WebFetch/WebSearch calls per dispatch (not per session)
- Recovery point: archive fetched bodies to disk (output file) after each successful fetch; if dispatch fails mid-probe, the archive allows resuming without re-fetching
- Spawn prompt MUST declare the probe ceiling explicitly: "Your WebFetch budget for this dispatch is 30 calls."

> [!practice] HTTP Probe Budget Declaration
> Include in every dispatch prompt that involves HTTP probing:
> ```
> **Tool-Use Budget:** Maximum 30 WebFetch/WebSearch calls in this dispatch.
> Archive each successful fetch response to `Outputs/{Abbrev}-{task-id}-Probe-Archive.md`
> before proceeding to the next URL. If you hit the budget ceiling, stop and report
> what was fetched and what remains.
> ```

#### 11.6 Path-Scoped Rule Injection in Spawn Prompts (PLG-012)

Path-specific rules (rules with `paths:` frontmatter patterns) do NOT automatically load for spawned subagents — spawned contexts start with zero file activity and inherit no path triggers from the parent. When a DELEGATED task requires path-specific rules, the orchestrator MUST inject those rule contents explicitly into the spawn prompt.

> [!constraint] Path Rule Injection
> WRONG — orchestrator assumes subagent will load path rules automatically:
> ```
> Task(
>   subagent_type: "general-purpose",
>   prompt: "Execute {Abbrev}-S01-02-01-Haiku-ScanModels.md — the relevant rules will load automatically."
> )
> ```
> CORRECT — orchestrator injects path-rule content or file reference explicitly:
> ```
> Task(
>   subagent_type: "general-purpose",
>   prompt: "Execute {Abbrev}-S01-02-01-Haiku-ScanModels.md.
>   IMPORTANT: The following path-scoped rule applies to {src/module/file.ext} files:
>   [paste rule content or file reference here]"
> )
> ```

#### 11.7 Idle-Mid-Step Wake-Up via SendMessage (PLG-012)

Teammates (in agent team mode) go idle after every turn. This is NORMAL — idle does not mean stopped. When a teammate is idle mid-step (has more work to do but has not been prompted for the next step), the orchestrator sends a wake-up message:

```
SendMessage(
  type: "message",
  recipient: "{teammate-name}",
  content: "Continue from where you stopped. Your remaining work: {bullet list of remaining items from task file}.",
  summary: "Wake-up: continue task execution"
)
```

> [!pitfall] Idle Teammate Mid-Task
> **Problem:** Teammate completes step N and goes idle, waiting for acknowledgment before proceeding to step N+1. Lead session treats idle as "done" and marks task complete.
> **Solution:** After receiving partial results from a teammate, check whether the task file has more steps. If yes, send a continuation message. Only treat idle as "done" when the task file's final step is confirmed complete.

#### 11.8 HARD CONSTRAINTS Spawn-Prompt Skeleton + SCOPE BOUNDARY Clause (PLG-020 §11.5 → §11.8)

Every DELEGATED spawn prompt MUST include a HARD CONSTRAINTS section and a SCOPE BOUNDARY clause:

```markdown
## HARD CONSTRAINTS (non-negotiable)
1. Modify ONLY files listed in this task's Required Context — no other files
2. Do NOT read files not listed in Required Context
3. Do NOT spawn sub-agents or create teams
4. If you encounter an ambiguity requiring a file not in Required Context, STOP and report it; do NOT expand scope

## SCOPE BOUNDARY
This task operates within:
- **In scope:** {list of files/modules this task modifies}
- **Out of scope:** {list of adjacent files/modules this task must NOT touch}
```

> [!constraint] HARD CONSTRAINTS Presence
> WRONG — spawn prompt omits HARD CONSTRAINTS; subagent reads adjacent files and expands scope:
> ```
> "Execute task file {Abbrev}-S02-01-03-Sonnet-GenEntities.md. Good luck!"
> ```
> CORRECT — spawn prompt includes HARD CONSTRAINTS and SCOPE BOUNDARY:
> ```
> "Execute task file {Abbrev}-S02-01-03-Sonnet-GenEntities.md.
>
> ## HARD CONSTRAINTS (non-negotiable)
> 1. Modify ONLY the files listed in the task's Required Context...
> [full HARD CONSTRAINTS + SCOPE BOUNDARY block]"
> ```

#### 11.9 Tier-Rank Fixes by Invasiveness (PLG-020 §11.6 → §11.9)

When a DELEGATED task produces results requiring fixes, rank the fixes by invasiveness before dispatching a follow-up:

| Tier | Fix Type | Invasiveness | Dispatch Approach |
|------|----------|--------------|-------------------|
| Tier 1 | Comment / doc update | Low | Inline in continuation message |
| Tier 2 | Single-file logic fix | Medium | New targeted dispatch |
| Tier 3 | Multi-file refactor | High | New session with full context |

Start with Tier 1 fixes before escalating; do not over-dispatch high-invasiveness fixes when lower-tier corrections suffice.

#### 11.10 Forward-Looking-Verb Detection + SendMessage Resume Protocol (PLG-020 §11.7 → §11.10)

When reviewing a dispatch's output, scan for forward-looking verbs in the last paragraph ("will", "next I will", "the following step will", "planned"). These signal the subagent stopped mid-task and intends to continue but has gone idle.

**Resume protocol:**
```
SendMessage(
  type: "message",
  recipient: "{task-runner}",
  content: "You said you would {forward-looking action}. Please continue now. Resume from your last completed step.",
  summary: "Resume: forward-looking task continuation"
)
```

> [!pitfall] Forward-Looking-Verb Tail
> **Problem:** Subagent ends its turn with "I will next write the schema pin" but goes idle. Orchestrator reads output and marks task complete without checking for completion.
> **Solution:** Grep the last 3 paragraphs of every dispatch output for `\b(will|next I will|the following step will|planned to)\b`. If found, send a resume message rather than marking COMPLETE.

#### 11.11 Operational-Ceiling Disclaimers in Spawn Prompts (PLG-020 §11.8 → §11.11)

Spawn prompts for tasks approaching operational ceilings (>25 file edits, >30 HTTP probes, >100K expected context) MUST include an operational ceiling disclaimer:

```markdown
## Operational Ceiling Notice
This task approaches operational ceilings:
- **Edit ceiling:** ~{N} file edits expected (ceiling: 25 per dispatch)
- **Context ceiling:** ~{X}K expected context load
If you reach a ceiling before completing all steps, STOP, write a partial output file documenting
what was completed and what remains, then signal completion via your final response.
```

#### 11.12 N>25 Edit-Task Resume Protocol with Tool-Use Budget Estimation (PLG-020 §11.9 → §11.12)

When a task requires >25 file edits and cannot be split further, use the N>25 Edit-Task Resume Protocol:

1. Estimate tool-use budget: `({N} edits × 2 tool calls/edit) + {M} reads + {K} overhead = {total} tool calls`
2. Declare the estimate in the spawn prompt under Operational Ceiling Notice
3. After dispatch, if subagent reports incomplete: spawn continuation dispatch with "Resume from file {N+1}" instruction
4. Cap continuation dispatches at 3; if still incomplete after 3 dispatches, escalate to orchestrator for redesign

> [!practice] Tool-Use Budget Estimation for Edit-Heavy Tasks
> Before dispatching >25-edit tasks, estimate: `(edits × 2) + reads + overhead`. If total exceeds 80% of model tool-budget ceiling, split the task. Example: 30 edits = 60 edit calls + 20 reads + 10 overhead = 90 tool calls — review against model ceiling before dispatching.

#### 11.13 Shared-Edit-Target Parallelism Cap (PLG-020 supplemental)

When two or more DELEGATED dispatches modify the same file, they MUST run sequentially — not in parallel. The parallelism cap for shared edit targets is 1 concurrent dispatch per file.

> [!constraint] Shared-Edit-Target Parallelism
> WRONG — two parallel dispatches modify the same schema file:
> ```
> Dispatch Task 02 (modifies schema.sql) ─┐ parallel
> Dispatch Task 03 (modifies schema.sql) ─┘
> (last write wins; one dispatch's changes are silently overwritten)
> ```
> CORRECT — sequential dispatches for shared edit targets:
> ```
> Dispatch Task 02 (modifies schema.sql) → COMPLETE → Dispatch Task 03 (modifies schema.sql)
> ```

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
| 10 | Background pre-approval gate overrides `bypassPermissions` | Background agents auto-deny any permission not explicitly pre-approved at launch; `bypassPermissions` does NOT bypass this gate [LL-001-PROC] | Write/Edit/Bash calls silently fail if not pre-approved; agent continues without output | Launch write-producing agents in foreground; reserve background for read-only tasks |
| 8 | Skill discovery ≠ system-prompt injection | File system access (Glob on `.claude/skills/`) | Mid-session agents not discoverable as subagent_type | Use `skills:` frontmatter to inject domain knowledge; all contexts discover existing skills via FS |
| 9 | Teammate identity is Agent SDK, not CC CLI | System prompt differentiation at spawn time | Teammates self-identify differently; less "Claude Code aware" | Design teammates as workers; orchestrate from main session |

> **Constraint 6 — path rules detail:** Spawned contexts begin with zero file activity. Path rules check the context's OWN active files. If a spawned context later works on files matching a path rule's pattern, those rules CAN trigger dynamically for that context. What they do NOT do is inherit the parent session's already-active path triggers.

> **Constraint 8 — skills note:** The `skills:` frontmatter field injects SKILL.md content into the agent's context at startup — use it for domain knowledge needed immediately. It does not restrict which skills the agent can discover; all contexts with file system access can discover all project skills regardless of the `skills:` field.

> **Constraint 10 — background pre-approval detail [LL-001-PROC]:** Background subagents use an upfront pre-approval gate: before launch, Claude Code prompts for all permissions the agent will need. At runtime, anything not pre-approved is auto-denied — the tool call fails silently but the agent continues executing. `bypassPermissions` mode does NOT override this gate. Practical consequence: task-runner agents that write output files MUST run in foreground. Background mode is only safe for read-only operations (Explore, research).

> **Constraint 10 — background pre-approval hazard (PLG-012 operational guidance):** Design background agents for read-only operations only. Before launching a background agent that you believe needs Write/Edit/Bash, convert it to foreground mode. The pre-approval gate cannot be bypassed by prompting or by `bypassPermissions` mode — both are enforced at the runtime layer, not the policy layer.

> **Team tool compatibility:** TeamCreate and SendMessage are not listed in the `allowed-tools` frontmatter system. Skills that need team functionality should use `context: fork` with `agent: general-purpose`. Do NOT attempt to list TeamCreate or SendMessage in `allowed-tools`.

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

> [!practice] 4-Step Ladder for Files Exceeding Read Tool Token Limit
> When a file exceeds the Read tool's effective token budget (~13K tokens / ~1000 lines at `~13 tokens/line`), apply this ladder in order — stop at the first step that succeeds:

**Step 1 — Output-clear pre-step:** Clear conversation output buffer before reading. Freed budget enables a larger Read call. Effective when the conversation history is large but the file itself is borderline.

**Step 2 — Substitution:** Read a smaller substitute:
- Adjacent `*.md` documentation next to the `{src/module/file.ext}` source file
- A smaller version-compatible equivalent (e.g., a config file that describes the large source file's structure)

**Step 3 — Grep-based scanning:** Use Grep with `output_mode: "content"` and context lines to extract the needed sections without a full Read. Effective when you know which section or function you need.

```bash
# Example: extract a specific function from a large file
Grep(pattern: "def {symbol}", path: "{src/module/file.ext}", output_mode: "content", context: 30)
```

**Step 4 — Script-based extraction:** For structured files (JSON/YAML), use a Bash command via `jq`/`yq` to project only relevant fields:

```bash
# Example: extract a specific key from a large YAML config
Bash("yq '.{config-field}' {src/module/file.ext}")
```

### Module Split Threshold (cross-reference)

For adapter/client modules whose row dataclass exceeds 75-80 fields, see the Module Split Threshold subsection in `references/session-plan-requirements.md`. Large-file read tactics are orthogonal to the module split decision — apply both when applicable.

---

*Cross-reference: [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*
