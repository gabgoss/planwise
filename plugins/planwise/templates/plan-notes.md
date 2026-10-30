# Plan Notes Template

Use this template when creating `{Abbrev}-PlanNotes.md`, the state file the `plan-author` agent reads first and updates after each task file it writes.

---

```markdown
# {Abbrev} Plan Notes

## Measured Facts

- {fact, located by heading or symbol, with the instrument and the date measured}

## Decisions

1. {authoring choice the metadata spec did not fix} — {reason}

## Open Questions

none

## Authoring Progress

| Session | Task files | Status |
|---------|------------|--------|
| {Abbrev}-S{XX}-{YY} | - | pending |

## Plan Boundary Note

**Next Session:** {Abbrev}-S{XX}-{YY}
**Resume State:** incomplete
**Written At:** -

**Field reference:**

| Line | Content |
|------|---------|
| Next Session | the next session the metadata spec lists, or `none` |
| Resume State | `complete` only when every task file of the last authored session is written with 0 FILL markers and Open Questions reads `none`; otherwise `incomplete` |
| Written At | timestamp of the last write, or `-` |

## Plan-Specific Sections <!-- OPTIONAL -->

Write any section that no heading above covers here, as an `###` H3. Never add it as a new `##` H2 elsewhere in this file, and draft one `idea` feedback draft for each new H3 heading (see `references/feedback-drafting.md`).

### {Section Heading}

{content}
```

---

## Rules

- **Record a fact by heading or symbol, never by line number.** The agent writes task bodies between reads, so a line number recorded before a write no longer matches the file after it. Write `the task file's ## Execution Steps heading`, not `:28`.
- **Open Questions holds `none` or a list.** Any body other than `none` makes the `plan-author` agent return `BLOCKED` before it writes a task file. The caller asks the user, writes each answer under `## Decisions`, and resets the section to `none`.
- **One Authoring Progress row per session.** Status is `pending`, `partial` or `complete`. A `complete` row tells the agent the session is already authored.
- **The Plan Boundary Note mirrors the Recovery file's Session Boundary Note** (`templates/recovery.md`): three bold-label lines, with `Resume State` reading `complete` only when its condition holds.
