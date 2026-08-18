---
description: Shared Startup/ToolSearch mandate, Finding Report Format, and Severity Classification table for the plan-reviewer, structural-reviewer, and rule-comparator agents — cited rather than inlined so the three review/comparator agent definitions share one canonical copy
---

# Review Finding Format

**Purpose:** Canonical Startup/ToolSearch protocol, Finding Report Format, and Severity Classification table shared by `agents/plan-reviewer.md`, `agents/structural-reviewer.md`, and `agents/rule-comparator.md`. Each of those three agents cites this file instead of inlining its own copy; only agent-specific deltas stay inline in the agent file itself.

---

## Startup (BINDING — Required First Action)

When spawned as a teammate, you MUST report via `SendMessage`. `SendMessage` is a deferred tool — its schema is not in your context at startup, and any attempt to call it without loading the schema first raises `InputValidationError` and drops your output on the floor.

Before reading any file, issue this exact call as your first action:

```
ToolSearch(query: "select:SendMessage", max_results: 1)
```

Only after the `<functions>` block for `SendMessage` appears in the tool result may you begin reading files and reporting. If you are spawned in subagent mode (no team), this call is harmless — proceed identically.

**Reporting-cadence adaptation.** No wording is byte-identical across all three citing agents on this point, so the delta is preserved explicitly rather than dropped:

- **multi-finding agents** (`plan-reviewer`, `structural-reviewer`): report each finding separately via `SendMessage` as you find it. A missed `ToolSearch` call drops your entire review on the floor.
- **single-verdict agents** (`rule-comparator`): return exactly one verdict via `SendMessage` at the end of your comparison, not per-finding reports. A missed `ToolSearch` call drops your verdict on the floor.

---

## Finding Report Format

```
[SEVERITY] Finding summary (one line)
File: {relative path}
Location: {section or line reference}
Issue: {what is wrong}
Fix: {concrete change — file + what to modify}
Confidence: HIGH | MEDIUM | LOW
```

## Severity Classification

| Severity | Meaning |
|----------|---------|
| BLOCKER | Cannot execute the plan — must fix before proceeding |
| ERROR | Significant issue that will cause problems during execution |
| WARNING | Minor issue — execution can proceed but quality is reduced |
| INFO | Observation — no action required |

---

**Applies to:** `plan-reviewer` and `structural-reviewer` cite the Finding Report Format and Severity Classification above verbatim (their two copies were byte-identical modulo whitespace before this extraction). `rule-comparator` cites this file for the Startup protocol only — it returns a structured JSON verdict rather than per-finding reports, so the Finding Report Format and Severity Classification do not apply to it.

**Not extracted:** `plan-reviewer`'s Uncertain Finding Protocol (`[UNCERTAIN]` prefix on MEDIUM/LOW confidence findings) is agent-specific — it is not present in `structural-reviewer` or `rule-comparator` at all, so it is not shared across ≥2 agents and stays inline in `plan-reviewer.md` rather than moving here.
