---
description: Auto Mode policy — how any handler behaves when AskUserQuestion cannot be answered
---

# Auto Mode Policy

**Summary lives in** [skill-authoring.md](skill-authoring.md) **§4b** — the summary there is complete for authoring skills. This file is the full reference: taxonomy, gate-behavior matrix, inference defaults, and worked examples, needed when implementing handler gate behavior.

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
