---
description: Conventions for authoring .claude/rules/ files — frontmatter, path scoping, and pre-authoring scan workflow — plus the writer-or-gate rule for any artifact sentence that states a format, cap or threshold (§7)
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

Path-specific rules **DO** load in subagents (Agent tool spawns). Behavior:
- **At startup:** Only global rules load (no inherited path triggers from parent session)
- **After file activity:** Path rules trigger dynamically based on the subagent's own file reads

This means path scoping works in all contexts, not just the main session. (confirmed with 7 rules loading dynamically.)

### Context Budget Observation

When total rule content is large, rules may silently fail to load due to context budget competition. The mechanism is unclear, but having many rules increases the risk of individual rules being dropped. Keep rule count and size minimal. (Observed during testing — MEDIUM confidence, mechanism not fully understood.)

## 7. A Rule Is Not a Control: Pair Every Format Rule, Cap or Threshold With a Writer or a Gate

> [!constraint] This section governs any reference, template, agent instruction or handler sentence that states a format, a cap or a threshold, not only `.claude/rules/` files
> A rule that exists only as text an agent might read is a description of the intended state. It is not a control on that state. Reading is not enforcement. An agent under load reads the file in front of it, not the reference two hops away. Stronger wording does not fix this. Two mechanisms do, and the artifact's author decides which one applies.

### 7.1 Mechanism 1 — The writer emits the rule

If a script or agent writes the artifact, the writer emits the required form. Examples:

- A generator caps titles at 120 characters and reports every truncation.
- A generator shards at a token budget instead of documenting a rotation trigger.
- A generator derives the shipped seed from its own zero-item output, so the seed and the live form cannot drift.

A writer that enforces the format makes the reference descriptive again. That is safe, because the description is no longer load-bearing.

### 7.2 Mechanism 2 — A gate checks the artifact

If humans or free-form agents write the artifact, a gate checks it. The gate needs three properties:

- **A number, not an adjective.** Write "at most 120 characters" for "short". An agent can compare a number.
- **A redirect with every prohibition.** Write "history belongs in a changelog file" beside "do not keep prior values". A careful agent told only not to keep information invents a place to keep it. In the measured case, agents chained `Prior entry:` text onto one line rather than destroy information.
- **A check beside the line it governs.** Do not park the check in a conventions section elsewhere. The writer looks at the line, not at the conventions section.

### 7.3 Two tests before a documented rule ships

1. **Name the thing that fires when the rule is broken.** If the answer is "the next reader will notice", the rule has no control. A replacement threshold with no checker is the same defect in a new unit. Name the enforcing writer and the out-of-band checker.
2. **Confirm the rule's unit can fire on the artifact it governs.** A line-count threshold on a file whose lines grow to 53 KB cannot fire. Measure the artifact in the unit that bounds it (bytes or tokens) before writing the number.

### 7.4 Measured table

Four rules governed one index file and its items. Names are stand-ins. Every number is measured.

| Rule as written | Where it lived | Mechanism behind it | What happened |
|---|---|---|---|
| "Every `<item>` MUST follow this structure", with a literal seven-field frontmatter block | a workflow reference | none | 51 of the files it governed omitted the block |
| "Keep the title cell to one line" | the writer agent's instructions | none: no number, no check | one cell reached 3,926 characters |
| Bump `Last Updated:` "with a short parenthetical naming what changed" | a handler and a reference | none: no cap, no instruction to discard the prior value | one line reached 53,251 bytes, and a second header reached 83,732 bytes |
| "Run when the index exceeds about 500 lines" | the schema reference | none, and the unit could never fire: the file was 242 lines and 233 KB | the trigger was dead for the file's whole life |

> [!constraint] WRONG and CORRECT — the obligation is not the control
> WRONG — the obligation is the control:
> ```
> <schema reference>   "Run cleanup when the index exceeds ~500 lines."
>                      (invoked by zero handlers; live file 242 lines / 233 KB)
> ```
> CORRECT — the writer enforces, the reference describes, and the checker is named:
> ```
> <generator>.py   TITLE_MAX_LEN = 120 -> truncate_title(); 22,000-token budget -> split_items_to_budget()
> <schema reference>   "enforced by sharding at --write; --check reports a breach; a doctor
>                       read-gate extension re-checks from outside the generator"
> ```

The shipped seed in that case was structurally identical to the 233 KB live file: same headings, same header, same footer. The live file did not deviate from the design. It followed it. A rule that is correct as prose can be violated at scale.

### 7.5 Where it applies

This section applies to every reference, template, agent instruction and handler sentence that states a format, a cap or a threshold. It is the authoring-side failure: no gate was written because the MUST was mistaken for one. A plan states the same rule at plan level: every deliverable is a writer or a gate, not a paragraph (see `references/session-plan-requirements.md`, "Scaffolding Phase Requirements (Plan Writing)").

A gate that exists but never ran, or that ran and asked the wrong question, is a downstream failure. The gate-evidence references cover it: [verification-gate-evidence.md](verification-gate-evidence.md) and [gate-predicate-discrimination.md](gate-predicate-discrimination.md).

#### Reviewer Check 098 — Format, Cap or Threshold Sentence With Neither a Writer Nor a Gate

- **Severity / Role / Type:** WARNING (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** For each deliverable or rule sentence that states a format, cap or threshold, find the writer that emits it or the gate that rejects the wrong form. Flag a sentence with neither.
- **Detection:** Grep the plan's deliverables and the artifacts it edits for "MUST follow", "keep to", "at most", "short", "about N lines". For each hit, name the script or agent that emits the form, or the check that fires on the wrong form. A hit with neither → WARNING. A threshold whose unit cannot fire on the artifact (lines on a file bounded in bytes) → WARNING.
- **Finding template:**
```
[WARNING] Format, cap or threshold stated with neither a writer nor a gate
File: {deliverable or artifact path} | Location: {sentence}
Issue: "{sentence}" states a {format|cap|threshold}; no writer emits it and no gate rejects the wrong form
Fix: Name the enforcing writer or add a gate beside the line it governs, per references/rule-authoring.md §7 | Confidence: HIGH
```

---

*Reference copy — no path scoping. Intended for subagent use and plugin distribution.*
*Cross-reference: [agent-authoring.md](agent-authoring.md) for agent definition frontmatter, [skill-authoring.md](skill-authoring.md) for skill frontmatter and Auto Mode policy.*
