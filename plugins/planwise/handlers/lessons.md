# Handler: /planwise lessons

**Purpose:** Search, list, promote, and capture lessons learned.

**Invocation examples:**
```
/planwise lessons
/planwise lessons python regex
/planwise lessons promote LL-022
/planwise lessons capture
```

---

## Config Gate

Locate `config.yaml` by checking:
1. `planwise/config.yaml` (default planwise root)
2. If not found, search one level down from the project root for `*/config.yaml`
3. If not found: "Project not initialized. Run `/planwise init` first."

Extract from `config.yaml`:
- `plugin_root` — the plugin installation path
- `project.planwise_root` — the planwise root folder (default: `planwise`)
- `project.lessons_dir` — the LessonsLearned directory name (relative to planwise_root)
- `project.index_files.lessons` — the lessons index filename (e.g., `00-Index-LessonsLearned.md`)

All directory paths resolve as `{planwise_root}/{dir_name}` (e.g., `planwise/LessonsLearned`).

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`) are pre-injected by SKILL.md.

**Conditional references:**
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`

---

## Routing

| Input | Mode | Action |
|-------|------|--------|
| No arguments | **list** | Display lessons index table |
| `<terms>` (not `promote` or `capture`) | **search** | Search by keyword across lesson files |
| `promote <lesson-id>` | **promote** | Promote a lesson to a Claude Code artifact |
| `capture` | **capture** | Create a new lesson mid-session |

Parse `$1` to determine the mode. If `$1` is `promote`, parse `$2` as the lesson ID. If `$1` is `capture`, enter capture mode. If `$1` is absent, enter list mode. Otherwise, treat all arguments as search terms.

---

## List Mode (no arguments)

Read `{lessons_dir}/{lessons_index}` and display the Master Table.

If the file does not exist:

```
Lessons index not found at {lessons_dir}/{lessons_index}.
Run `/planwise init` to create the index, or check your config.yaml.
```

---

## Search Mode (`/planwise lessons <terms>`)

For each search term in `$ARGUMENTS`:

1. Use Grep to search YAML frontmatter in `{lessons_dir}/LL-*.md`:
   ```
   pattern: {term}
   path: {lessons_dir}
   glob: **/LL-*.md
   output_mode: files_with_matches
   ```
2. Intersect results across all search terms — files must match ALL terms (AND logic)
3. For each matching file, read the frontmatter and first line of each `## ` section

### Output Format

Present results as a table:

```
| ID | Title | Category | Severity | File |
|----|-------|----------|----------|------|
| LL-001 | Example Lesson Title | process | medium | [LL-001]({lessons_dir}/LL-001-DOC-ExampleTopic.md) |
```

After the table, include a 1-line summary of each lesson's key insight.

### No Results

If no lessons match, respond with:
- "No lessons found matching: {terms}"
- Suggest checking valid taxonomy values: `category` (anti-pattern, pattern, process), `domain` (from config.yaml abbreviations)
- Link to the index: `{lessons_dir}/{lessons_index}`

---

## Promote Mode (`/planwise lessons promote <lesson-id>`)

**Purpose:** Promote a lesson to a Claude Code artifact (rule, skill, hook, or agent).

The promotion flows through these stages:

```
Locate → Read → Confirm → Generate → Update → Archive → Log
```

### Stage 1: Locate

Find the lesson file by ID:
```
Glob: {lessons_dir}/**/LL-{id}*
```

This searches both the working directory and Archive in one pass.

If not found, use a broad search to list all available lessons:
```
Glob: {lessons_dir}/**/LL-*
```

List all lesson IDs found and ask the user to confirm the correct one.

### Stage 2: Read

Read the lesson content and determine the appropriate artifact type based on the lesson's content pattern:

| Lesson Content Pattern | Artifact Type | Generated Location |
|------------------------|---------------|-------------------|
| Prescriptive rule (MUST, NEVER, ALWAYS) | Rule | `.claude/rules/{name}.md` |
| Reusable workflow with steps | Skill | `.claude/skills/{name}/SKILL.md` |
| Enforcement check (pre/post action) | Hook | `.claude/hooks/{name}.sh` |
| Delegatable role with constraints | Agent | `.claude/agents/{name}.md` |

Most lessons describe patterns or anti-patterns that map to **Rule** type. Lessons about workflows may map to **Skill**. Hook and agent types are rare.

### Stage 3: Confirm (REQUIRED — never skip)

Present to the user:
- Lesson ID and title
- Proposed artifact type (Rule, Skill, Hook, Agent)
- Proposed artifact name (kebab-case)
- Proposed file path
- Brief rationale for the classification

Wait for user approval before proceeding.

**If rejected:** Ask if they want a different artifact type, or abort. The lesson remains in its current status.

### Stage 4: Generate

Create the artifact file at the approved location:

| Artifact Type | Location |
|---------------|----------|
| Rule | `.claude/rules/{name}.md` |
| Skill | `.claude/skills/{name}/SKILL.md` |
| Hook | `.claude/hooks/{name}.sh` |
| Agent | `.claude/agents/{name}.md` |

Check if the file already exists before writing. If it exists, ask the user to rename or merge.

### Stage 5: Update Frontmatter

Edit the lesson file's YAML frontmatter:

| Field | Value |
|-------|-------|
| `status` | `rule` (for rules) or `applied` (for skills, hooks, agents) |
| `applied-as` | Path to generated artifact (relative to project root) |
| `promoted-date` | ISO date: YYYY-MM-DD |

### Stage 6: Archive

Move the promoted lesson to the Archive folder to keep the working directory clean.

1. Create Archive directory if it does not exist:
   ```bash
   mkdir -p "{lessons_dir}/Archive"
   ```

2. Move the lesson file:
   ```bash
   mv "{lessons_dir}/LL-{NNN}-{Domain}-{Name}.md" "{lessons_dir}/Archive/"
   ```

3. Update the index link in the Master Table using Edit:
   - Old: `](LL-{NNN}-{Domain}-{Name}.md)`
   - New: `](Archive/LL-{NNN}-{Domain}-{Name}.md)`

Skip if the file is already in `Archive/`.

### Stage 7: Log

Add a row to the Rule Promotion Log in `{lessons_dir}/{lessons_index}`:

```markdown
| Date | Lesson ID | Artifact Created | File |
|------|-----------|-----------------|------|
| YYYY-MM-DD | LL-{NNN} | {artifact-name} | `.claude/{type}/{name}` |
```

Also update the lesson's `Status` column in the Master Table from `documented` to `rule` (or `applied`).

### Promotion Error Handling

| Failure | Recovery |
|---------|----------|
| Lesson file not found | Check `{lessons_dir}/LL-{NNN}*` then `{lessons_dir}/Archive/LL-{NNN}*`. Use Glob `{lessons_dir}/**/LL-*` to list all. |
| Ambiguous artifact type | Present options to user and let them choose |
| Artifact file path conflict | Check if file exists; ask user to rename or merge |
| Lesson frontmatter edit fails | Use Edit tool manually on the YAML frontmatter block |
| Index update fails | Manually add row to Rule Promotion Log |

---

## Capture Mode (`/planwise lessons capture`)

Capture a lesson during an active session while context is fresh.

### Step 1: Identify

From the current session context, determine:
- What went wrong or what was learned
- Domain (infer from files being worked on, or ask user)
- Technology and language involved
- Severity assessment (high/medium/low)

Read domain abbreviations from `config.yaml` (`abbreviations` and `lesson_abbreviations` sections) to present valid domain options.

### Step 2: Draft

Create a candidate lesson with pre-filled YAML frontmatter:

```yaml
---
id: LL-{next-available}
title: {auto-generated from context}
date: {today}
source: {current session reference}
category: {inferred: anti-pattern | pattern | process}
severity: {inferred: low | medium | high}
language: [{inferred}]
technology: [{inferred}]
domain: [{inferred domain abbreviation}]
status: documented
applied-as: null
---
```

### Step 3: Approve

Present the draft to the user:
- Show pre-filled frontmatter and draft Context/Lesson/Applies To sections
- Ask: "Capture this lesson? (approve / edit / skip)"

### Step 4: Write

If approved:
1. Read `{lessons_dir}/{lessons_index}` to get the next available ID and the lesson file template
2. Determine `{Domain}` from the first value in the `domain:` field
3. Write file: `{lessons_dir}/LL-{NNN}-{Domain}-{Name}.md`
4. Add a row to the Master Table in `{lessons_dir}/{lessons_index}`
5. Update the "Next available ID" counter in the index

### Step 5: Skip

If skipped, discard the draft. No file is written.

---

## Lesson Status Lifecycle

Lessons graduate through three statuses:

```
documented → applied → rule
```

| Status | Meaning |
|--------|---------|
| `documented` | Lesson captured, available for reference |
| `applied` | Lesson has been manually applied in practice (proven useful) |
| `rule` | Lesson promoted to a Claude Code artifact |

### Promotion Criteria

Promote a lesson when ANY of these apply:
- Severity is `high`
- Lesson recurs 2+ times across different sessions or domains
- Lesson addresses a class of problems (not just one instance)

---

## Search Tips

- Search is case-insensitive against YAML frontmatter
- Multiple terms narrow results (AND logic)
- Common searches: `/planwise lessons python`, `/planwise lessons anti-pattern`, `/planwise lessons high`
