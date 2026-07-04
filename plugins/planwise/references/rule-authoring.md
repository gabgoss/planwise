---
description: Conventions for authoring .claude/rules/ files — frontmatter, path scoping, and pre-authoring scan workflow
---

# Rule Authoring Conventions

## 1. Frontmatter Requirements

Every rule file MUST have YAML frontmatter with at minimum:

```yaml
---
description: What this rule covers and when it applies
paths: Controllers/**, Views/**
---
```

| Field | Required | Purpose |
|-------|----------|---------|
| `description` | Yes | One-line summary of the rule's purpose |
| `paths` | Yes (unless global) | Directory paths where the rule applies (see supported formats below) |

### Supported `paths:` Formats

| Format | Example | Notes |
|--------|---------|-------|
| Unquoted string | `paths: Controllers/**` | Simplest format |
| Quoted string | `paths: "**/*.cs"` | Required when using `*` or `{` |
| Comma-separated | `paths: Controllers/**, Views/**` | **Recommended** for multiple paths |
| Brace expansion (ext) | `paths: "**/*.{cs,md}"` | Matches multiple extensions |
| Brace expansion (dir) | `paths: "{Controllers,Views}/**"` | Matches multiple directories |
| Dir + extension | `paths: "Controllers/**/*.cs"` | Compound pattern |
| YAML array (1 item) | `paths:\n  - "Controllers/**"` | Works for single item only |
| No paths (global) | *(omit field)* | Loads unconditionally |

> [!pitfall] YAML Multi-Item Arrays Are Broken
> **Problem:** The official Anthropic docs show multi-item YAML arrays as the recommended format:
> ```yaml
> paths:
>   - "Controllers/**"
>   - "Views/**"
> ```
> This format does **NOT** work. The YAML frontmatter parser fails on 2+ array items — the rule silently does not load. (Tested 3 times, reproduced consistently.)
>
> **Solution:** Use comma-separated format instead:
> ```yaml
> paths: Controllers/**, Views/**
> ```

## 2. Path Scoping (BINDING)

USE explicit directory paths in `paths:`. DO NOT use file extension globs.

```yaml
# WRONG — matches every markdown file in the entire project
paths: "**/*.md"

# WRONG — identical behavior to **/*.md (no root-only scoping exists)
paths: "*.md"

# WRONG — matches all files everywhere
paths: "**"

# CORRECT — explicit directories where the rule applies
paths: .claude/rules/**, .claude/skills/**, Docs/**
```

**Why:** Extension globs like `**/*.md` load the rule for files that don't need it (LICENSE files, archive content, external documents, build artifacts). Explicit paths keep context budgets tight and rules relevant.

> [!pitfall] `*.md` Is NOT Root-Only
> **Problem:** Official Anthropic docs claim `*.md` matches "Markdown files in the project root." This is **wrong**. Claude Code's glob treats `*` as matching across path separators, so `*.md` is functionally identical to `**/*.md` — it matches `.md` files at any depth. (Tested and verified in 2 independent runs.)
>
> **Solution:** There is no way to create a root-only glob. Use explicit directory paths instead.

### Global Rules (No paths field)

Omit `paths:` entirely when a rule genuinely applies to ALL work regardless of file context. Global rules consume context budget on every interaction.

| Rule Type | Use `paths:`? | Example |
|-----------|---------------|---------|
| Project-wide protocol | No (global) | session-execution-protocol.md |
| Domain-specific convention | Yes | callout-conventions.md → `.claude/rules/**`, `Docs/**` |
| File-type convention | Yes | csharp-conventions.md → `**/*.cs` (extension glob OK for code files) |

**Exception:** Extension globs like `**/*.cs` are acceptable for source code files because those extensions reliably indicate the rule's domain. The problem is `**/*.md` where markdown exists everywhere.

### Choosing a Home for a Rule Customization

When you need to change behavior that a plugin-installed rule already covers, choose
WHERE the change lives by the nature of the change — never edit the installed copy in
place (it is machine-managed; see the warning below).

> [!decide] Where to Home a Rule Customization
> - **Generic fix** — the change improves the rule for *every* consumer, not just this
>   project → **upstream it.** Open a PR or issue against the shipped reference rule.
>   Do NOT localize a generic improvement: a generic edit left in a local copy is lost
>   on the next refresh and never reaches anyone else.
> - **Project-specific customization** — the change only makes sense for this codebase →
>   **localize it.** Create `.claude/rules/<project>/<name>.md` and scope its `paths:` to
>   the **code directories** the rule governs. NEVER scope a localized rule to plan,
>   backlog, or lessons globs — that re-creates the always-on over-scope that path
>   scoping (§2) exists to prevent.
> - **Mixed** — part generic, part project-specific → **split it.** Upstream the generic
>   portion; localize only the project-specific remainder in `.claude/rules/<project>/`.
> - **Never** leave a customization inside `.claude/rules/planwise/`. That directory is
>   machine-managed: on upgrade an identical copy is auto-refreshed to the shipped body
>   (your edit is silently overwritten). A diverged copy, under the default handoff mode,
>   has its customization transferred to a dormant holding area and the shipped body
>   adopted in its place — your edit survives only as an inert file you must manually
>   re-home, not as an active rule. Only under the conservative handoff mode is a
>   diverged copy instead preserved in place and nagged as an unresolved conflict on
>   every upgrade.

## 2b. Common Frontmatter Mistakes

> [!constraint] YAML Array Syntax for Multi-Path Scoping
> WRONG — multi-item YAML array is silently broken:
> ```yaml
> ---
> description: Conventions for controller code
> paths:
>   - "Controllers/**"
>   - "Views/**"
> ---
> ```
> CORRECT — comma-separated on a single line:
> ```yaml
> ---
> description: Conventions for controller code
> paths: Controllers/**, Views/**
> ---
> ```

> [!constraint] Glob Pattern Overmatch
> WRONG — loads for every `.md` file in the entire project (archives, external content, etc.):
> ```yaml
> ---
> description: Callout conventions for markdown files
> paths: "**/*.md"
> ---
> ```
> CORRECT — explicit directories where these conventions are authored:
> ```yaml
> ---
> description: Callout conventions for markdown files authored in this project
> paths: .claude/rules/**, .claude/skills/**, .claude/agents/**, Docs/**
> ---
> ```

> [!constraint] Missing `paths:` on a Non-Global Rule
> WRONG — omitting `paths:` makes the rule global; it loads on every interaction even when irrelevant:
> ```yaml
> ---
> description: EF Core conventions for entity classes
> ---
> ```
> CORRECT — scoped to the files where it applies:
> ```yaml
> ---
> description: EF Core conventions for entity classes
> paths: Data/**, Migrations/**
> ---
> ```

> [!pitfall] Single-Item YAML Array
> **Problem:** A single-item array `paths:\n  - "Controllers/**"` technically works but creates a maintenance trap — if a second path is added later, the rule silently stops loading.
> **Solution:** Always use comma-separated format even for a single path:
> ```yaml
> paths: Controllers/**
> ```
> This format is safe to extend with additional paths without risk of silent failure.

---

## 3. Pre-Authoring Scan (REQUIRED)

Before setting `paths:` on a new or modified rule, scan the project to identify which directories contain files relevant to the rule's purpose.

### Scan Workflow

1. **Identify the file types** the rule applies to (markdown, C#, config, etc.)
2. **Scan project structure** using `Glob` tool: `**/*.{ext}` to find where target files live
3. **Classify directories** into three buckets:

| Bucket | Action | Examples |
|--------|--------|---------|
| **Include** | Add to `paths:` | Directories where you actively author these files |
| **Exclude** | Omit from `paths:` | Archives, external content, build output, vendored libs |
| **Irrelevant** | Omit from `paths:` | Directories that don't contain the target file type |

4. **Set `paths:`** with only the Include bucket directories

### Domain-Based Path Selection

Classify directories into Include/Exclude/Irrelevant buckets based on your project structure:

- **Include:** Directories where you actively author and maintain the relevant file types (source code, docs, configuration)
- **Exclude:** Directories containing vendor/third-party libs, archived content, build output (`bin/`, `obj/`), package dependencies (`node_modules/`)
- **Irrelevant:** Directories that simply don't contain the target file type

### Exclusion Criteria

These directory patterns should generally be excluded from rule paths:

| Directory Pattern | Reason |
|-------------------|--------|
| Vendor/third-party libs | Not authored by the project team |
| Archived content | Historical content, not actively maintained |
| `bin/`, `obj/` | Build output |
| `node_modules/` | Package dependencies |
| Auto-generated files | Not hand-authored (e.g., migration output, scaffolded code) |

## 4. Rule File Naming

| Convention | Example |
|------------|---------|
| Lowercase with hyphens | `callout-conventions.md` |
| Descriptive of scope | `csharp-conventions.md`, `ef-conventions.md` |
| No abbreviations unless standard | `ef-conventions.md` (EF is standard) |

## 5. Cross-References

When a rule references another rule or document, use relative markdown links:

```markdown
See [session-planning-protocol.md](session-planning-protocol.md) for planning rules.
See [callout-conventions.md](callout-conventions.md) for callout syntax.
```

## 6. Empirically Verified Behavior

These patterns were empirically tested in Claude Code CLI on 2026-02-25. Results supersede prior guidance for listed patterns.

### Confirmed Supported

| Pattern | Test | Result |
|---------|------|--------|
| `paths: Controllers/**` | A1 | Loads for files under Controllers/ |
| `paths:\n  - "Controllers/**"` (1 item) | A2 | Single-item YAML array loads correctly |
| `paths: Controllers/**, Views/**` | A3 | Comma-separated multi-path loads correctly |
| `paths: "**/*.cs"` | B1 | Extension glob loads for matching files |
| `paths: "**/*.{cs,md}"` | C1 | Brace extension expansion works |
| `paths: "{Controllers,Views}/**"` | C2 | Brace directory expansion works |
| `paths: "Controllers/**/*.cs"` | D2 | Combined dir+extension works |
| *(no paths field)* | D3 | Global rules load unconditionally |

### Confirmed NOT Supported

| Pattern | Test | Failure Mode |
|---------|------|-------------|
| YAML array with 2+ items | D1 | Parser fails — rule does not load (reproduced 3x) |

### Unexpected Behavior

| Pattern | Expected | Actual |
|---------|----------|--------|
| `*.md` | Root-only match | Matches at ANY depth — equivalent to `**/*.md` |

### Subagent Rule Loading

Path-specific rules **DO** load in subagents (Task tool spawns). Behavior:
- **At startup:** Only global rules load (no inherited path triggers from parent session)
- **After file activity:** Path rules trigger dynamically based on the subagent's own file reads

This means path scoping works in all contexts, not just the main session. (confirmed with 7 rules loading dynamically.)

### Context Budget Observation

When total rule content is large, rules may silently fail to load due to context budget competition. The mechanism is unclear, but having many rules increases the risk of individual rules being dropped. Keep rule count and size minimal. (Observed during testing — MEDIUM confidence, mechanism not fully understood.)

---

*Reference copy — no path scoping. Intended for subagent use and plugin distribution.*
