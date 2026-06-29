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
- [4b. Auto Mode Policy](#4b-auto-mode-policy)
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
| `description` | string | 1st paragraph | **REQUIRED** — drives auto-triggering and delegation (without it, the skill cannot be auto-invoked). |
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

## 4b. Auto Mode Policy

**Purpose:** Define how skill handlers behave when invoked non-interactively ("Auto Mode"),
where `AskUserQuestion` cannot be answered by a user.

### § Auto Mode Context

Auto Mode is a harness-level execution flag that signals the skill is running unattended —
for example, when a handler is invoked as a subroutine by another handler, or when the user
invokes a skill with `--auto` in a scripted context. In Auto Mode, `AskUserQuestion` calls
that are classified as **convenience** questions MUST be answered by inference (no prompt
issued). Questions classified as **critical** MUST emit a `[!gate] User Decision Required`
block and still attempt `AskUserQuestion`; if the harness auto-denies the question, the
handler fails loud with the gate text and instructs the user to re-issue the command with
the required argument inline.

Skill authors MUST classify every `AskUserQuestion` call site in their handler as either
critical or convenience. This classification is enforced at plan-review time via
`<!-- AUTO-MODE: critical -->` and `<!-- AUTO-MODE: convenience -->` inline comments.

### § Critical vs Convenience Taxonomy

| Classification | Definition | Examples |
|---------------|------------|---------|
| **Critical** | Agent CANNOT safely infer a correct answer. Wrong inference causes data loss, incorrect plan structure, or destructive action. User MUST decide. | Plan name, abbreviation (when collision possible), vision/objective, sprint count, sprint purpose, scaffolding source mapping, destructive action confirmation (revert/delete) |
| **Convenience** | Agent CAN safely infer a correct answer from project context. Wrong inference causes cosmetic inconvenience, not data loss. | Install scope, directory names, review approach, lesson capture acknowledgment, recovery resume confirmation |

### § Critical Question Behavior

When a call site is classified as **critical**:

1. Emit a `[!gate] User Decision Required` block immediately before the `AskUserQuestion` call:

   ```markdown
   > [!gate] User Decision Required
   > Auto Mode cannot infer this value. Manual input required.
   > Re-issue the command with the answer inline, or run interactively.
   > Question: {question text}
   ```

2. Call `AskUserQuestion` as normal.

3. If the harness auto-denies the question (Auto Mode blocks it):
   - Print the gate text to output.
   - FAIL LOUD: "Auto Mode: critical question '{question summary}' could not be answered.
     Re-issue `/planwise {handler}` with argument `{arg}={value}` inline."
   - STOP — do not proceed past the gate.

<!-- AUTO-MODE: critical -->

### § Convenience Question Behavior

When a call site is classified as **convenience**:

1. Do NOT call `AskUserQuestion`.
2. Apply the inferred default (see § Inference Defaults below).
3. Log the inference:

   ```
   Auto-Mode inference: {variable}={inferred_value}  (reason: {brief rationale})
   ```

4. Continue without waiting for user input.

<!-- AUTO-MODE: convenience -->

### § Inline Tagging Convention

Every `AskUserQuestion` call site in a handler MUST be tagged with one of:

```markdown
<!-- AUTO-MODE: critical -->
```

or

```markdown
<!-- AUTO-MODE: convenience -->
```

Place the comment on the line immediately BEFORE the `AskUserQuestion` call or the
descriptive block that introduces the question. This placement allows reviewer agents to
grep for compliance:

```bash
# Grep: verify every AskUserQuestion has an AUTO-MODE tag on the preceding line
grep -B1 "AskUserQuestion" handlers/*.md | grep -v "AUTO-MODE:"
# Output should be empty if all sites are tagged.
```

### § Worked Example

```markdown
### Step 1: Gather Information

<!-- AUTO-MODE: critical -->
Use `AskUserQuestion` to collect:
**Question 1:** What is the name of your plan? (e.g., "UserAuthentication")

<!-- AUTO-MODE: critical -->
**Abbreviation:** What is the 2-4 character abbreviation?

<!-- AUTO-MODE: critical -->
**Vision:** Briefly describe the plan vision (1-2 sentences).

<!-- AUTO-MODE: convenience -->
Use `AskUserQuestion` to collect:
**Question 2 (Step 10):** Plan review approach?
- Auto-review (Recommended)
- Review manually first
- Skip to /planwise run
```

When Auto Mode is active:
- Questions tagged `critical` emit `[!gate]` and attempt `AskUserQuestion` (fail loud if denied).
- Questions tagged `convenience` log inference and proceed:
  "Auto-Mode inference: review_approach=auto-review (reason: recommended option)"

### § Inference Defaults

These defaults apply to all convenience questions across all handlers. Handlers MUST NOT
re-define these defaults locally — reference this table.

| Variable | Inference Rule |
|----------|----------------|
| Project name | Current git repo name (from `git rev-parse --show-toplevel \| xargs basename`), or `cwd` basename. Strip trailing `-`, `_`, `.git` suffix. |
| Install scope | `project` |
| Planwise root | `planwise` |
| Plans directory | `Plans` |
| Backlog directory | `Backlog` |
| Lessons directory | `LessonsLearned` |
| Abbreviation | Derive from plan name: collect initial capitals of each word, pad or truncate to 2-4 chars. If collision detected in plans index, ESCALATE TO CRITICAL (cannot infer safely). |
| Review approach (plan.md Step 10 Q1) | `auto-review in this session` (recommended option) |
| Review context (plan.md Step 10 Q2) | `this session` (unless plan context exceeds heuristic: >3 sprints or >10 task files → `new session`) |
| Lessons capture acknowledgment | `proceed without confirmation` |

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

> [!practice] Empirically Verified
> **Forked contexts receive the full Claude Code CLI system prompt** — NOT "a custom prompt only" as some documentation suggests. The `SKILL.md` content is ADDITIONAL to the system prompt.

> [!practice] Empirically Verified
> **Forked context tool set is identical to a `general-purpose` subagent** (18 tools). Includes TeamCreate/Delete, SendMessage, all file and web tools. Excludes Task, AskUserQuestion, PlanMode. No nesting — a forked skill cannot spawn further subagents.

> [!practice] Empirically Verified
> **All forked contexts discover project skills via file system access** regardless of `skills:` preload. The `skills:` field in agent frontmatter is **context injection** (injects SKILL.md content at startup), not an access restriction. File system discovery always works for all contexts.

> [!practice] Empirically Verified
> **Path-specific rules do NOT load in forked contexts.** Only the global rules active in the parent session are visible. If a forked skill needs domain-specific rule content, embed it in SKILL.md directly.

> [!practice] [UNVERIFIED] MCP availability in forked context
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

> **Note:** Skill-scoped hooks support `PreToolUse` and `PostToolUse` only. The `Stop` event does **not** propagate to skill-frontmatter hooks (v1.0.2). For Stop-event behavior, use a project-scoped hook (`.claude/settings.json` `"hooks": { "Stop": ... }` + a script in `.claude/hooks/`) or an agent-scoped hook (see `agent-authoring.md §2`). **Empirically confirmed:** a skill-scoped `Stop` hook did not fire on skill-context exit, while an identically-structured project-scoped `Stop` hook fired normally on the same machine.

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
