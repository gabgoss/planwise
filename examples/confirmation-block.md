# Confirmation Block Examples

Examples of correctly formatted confirmation blocks for the `/execute` skill.

---

## Standard Format

```
CONTEXT LOADED
File: MyPlan-S01-02-Orchestration.md
Current State: IN_PROGRESS
Last Completed: Task 2 - Design automation approach
Next Action: Execute Task 3 - Create service layer
```

---

## Multiple Files

```
CONTEXT LOADED
File: multiple files (Master-Plan.md, S03-02-Orchestration.md, S03-02-Recovery.md)
Current State: IN_PROGRESS
Last Completed: Task 0 - Aggregate execution context
Next Action: Task 1 - Create entity models
```

---

## Fresh Session Start

```
CONTEXT LOADED
File: PI-S01-01-Orchestration.md
Current State: NOT_STARTED
Last Completed: None (new session)
Next Action: Task 1 - Read schema (5 tables)
```

---

## Session Recovery

```
CONTEXT LOADED
File: S02-03-Recovery.md
Current State: IN_PROGRESS (recovered)
Last Completed: Task 4 - Generate entities
Next Action: Resume Task 5 - Write migration
```

---

## After Confirmation Block

After outputting the confirmation block, use `AskUserQuestion` tool:

**Question:** "Ready to proceed with [Next Action]?"

**Options:**
1. "Yes, proceed" - Continue with the next action
2. "No, stop here" - Do not proceed, await further instructions

---

## What NOT to Do

**Avoid emoji decorators:**
```
CONTEXT LOADED          <- Do NOT use emojis
━━━━━━━━━━━━━━━━━━━━━━━    <- Do NOT use decorative lines
```

**Keep it plain text** for consistency and easy parsing.

