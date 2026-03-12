# Backlog Triage Fix Prompt

You are fixing a backlog item. Read the context below, locate the relevant source files, make the fix, and verify it works.

---

## Backlog Item

- **ID:** {ITEM_ID}
- **Feature:** {FEATURE}
- **Priority:** {PRIORITY}
- **Domain:** {ABBREV}
- **Status:** IN_PROGRESS

---

## Item Description

{ITEM_FILE_CONTENT}

---

## Source Files to Examine

{FILE_PATHS}

---

## Fix Instructions

1. Read each source file listed above
2. Understand the issue described in the item description
3. Make the targeted fix — change only what is necessary
4. Verify the fix:
   - Run the project's build/test command (see config.yaml build_commands)
   - For documentation: verify links and formatting
5. Report what you changed and the verification result

---

## Constraints

- Make the minimum change needed to resolve the issue
- Do NOT refactor surrounding code unless the item specifically requests it
- Do NOT add features beyond what the item describes
- If the fix requires changes beyond the described scope, STOP and report

---

## Expected Output

After completing the fix, report:

```
FIX COMPLETE
Item: {ITEM_ID} — {FEATURE}
Files modified:
  - {file1}: {what changed}
  - {file2}: {what changed}
Verification: {PASS/FAIL} ({build/test command used})
```

If the fix cannot be completed:

```
FIX BLOCKED
Item: {ITEM_ID} — {FEATURE}
Reason: {why the fix cannot be completed}
Suggested action: {what the user should do}
```
