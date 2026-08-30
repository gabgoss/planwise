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
| YAML array | `paths:\n  - "Controllers/**"` (any item count) | Works for any number of items — 2+ item arrays were broken as of the original 2026-02-25 test but confirmed FIXED on retest 2026-08-28 (CLI 2.1.250); see §6 |
| No paths (global) | *(omit field)* | Loads unconditionally |

> [!pitfall] YAML Multi-Item Arrays — Fixed 2026-08-28 (Previously Broken)
> **Original problem (tested 2026-02-25):** The official Anthropic docs show multi-item YAML arrays as the recommended format:
> ```yaml
> paths:
>   - "Controllers/**"
>   - "Views/**"
> ```
> This format did **NOT** work at the time — the YAML frontmatter parser failed on 2+ array items and the rule silently did not load. (Tested 3 times, reproduced consistently.)
>
> **Retest (2026-08-28, CLI 2.1.250):** Confirmed FIXED via a dedicated headless test harness — both entries of a 2-item array triggered their rule's dynamic load correctly. Multi-item arrays are safe to use directly:
> ```yaml
> paths:
>   - "Controllers/**"
>   - "Views/**"
> ```
> Comma-separated format remains available as an equally valid, more compact alternative — no longer required to avoid silent failure:
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
> **Problem:** Official Anthropic docs claim `*.md` matches "Markdown files in the project root." This is **wrong**. Claude Code's glob treats `*` as matching across path separators, so `*.md` is functionally identical to `**/*.md` — it matches `.md` files at any depth. (Tested and verified in 2 independent runs; retested 2026-08-28 on CLI 2.1.250 via a dedicated headless test harness — still reproduces.)
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

> [!practice] Comma-Separated vs. YAML Array for Multi-Path Scoping
> Both forms now load correctly (multi-item YAML arrays were broken as of the original 2026-02-25 test; retested and confirmed FIXED 2026-08-28 on CLI 2.1.250 — see §1). PREFER comma-separated for its compactness:
> ```yaml
> ---
> description: Conventions for controller code
> paths: Controllers/**, Views/**
> ---
> ```
> A multi-item YAML array is equally valid if preferred:
> ```yaml
> ---
> description: Conventions for controller code
> paths:
>   - "Controllers/**"
>   - "Views/**"
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

A single-item array (`paths:\n  - "Controllers/**"`) has always worked, and extending it to 2+ items is now safe too — see the retested history in §1's "YAML Multi-Item Arrays" note. Comma-separated remains the more compact style either way.

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

These patterns were empirically tested in Claude Code CLI on 2026-02-25. Results supersede prior guidance for listed patterns. Two rows were retested 2026-08-28 on CLI 2.1.250 via a dedicated headless test harness (see per-row notes below): YAML 2+ item arrays (now fixed) and the `*.md` root-only claim (still reproduces).

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
| `paths:\n  - "a/**"\n  - "b/**"` (2+ items) | D1 (retest) | Was broken 2026-02-25 (parser failed, rule didn't load); retested 2026-08-28 on CLI 2.1.250 — both array entries now load correctly. Moved here from Confirmed NOT Supported. |

### Confirmed NOT Supported

None currently confirmed. (D1 — YAML array with 2+ items — was listed here after the original 2026-02-25 test; retested 2026-08-28 on CLI 2.1.250 and reclassified to Confirmed Supported above.)

### Unexpected Behavior

| Pattern | Expected | Actual |
|---------|----------|--------|
| `*.md` | Root-only match | Matches at ANY depth — equivalent to `**/*.md`. Retested 2026-08-28 on CLI 2.1.250 via a dedicated headless test harness (reading a nested `.md` file still triggered a rule scoped to plain `*.md`) — still reproduces, unchanged from the original 2026-02-25 finding. |

### Subagent Rule Loading

Path-specific rules **DO** load in subagents (Task tool spawns). Behavior:
- **At startup:** Only global rules load (no inherited path triggers from parent session)
- **After file activity:** Path rules trigger dynamically based on the subagent's own file reads

This means path scoping works in all contexts, not just the main session. (confirmed with 7 rules loading dynamically.)

### Context Budget Observation

When total rule content is large, rules may silently fail to load due to context budget competition. The mechanism is unclear, but having many rules increases the risk of individual rules being dropped. Keep rule count and size minimal. (Observed during testing — MEDIUM confidence, mechanism not fully understood.)

---

*Reference copy — no path scoping. Intended for subagent use and plugin distribution.*
*Cross-reference: [agent-authoring.md](agent-authoring.md) for agent definition frontmatter, [skill-authoring.md](skill-authoring.md) for skill frontmatter and Auto Mode policy.*
