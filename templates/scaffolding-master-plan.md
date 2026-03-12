# Scaffolding Master Plan Template

Use this template when creating `{Abbrev}-Master-Plan.md` inside `Exec-{Abbrev}/` from Consolidated Context parts.

**When to use:** After a Meta-Plan Discovery phase produces Consolidated Context parts.

---

```markdown
# {PlanName} Execution Plan

**Plan Abbreviation:** {ABBREV}
**Status:** READY_TO_EXECUTE
**Created:** {today's date}
**Type:** Execution Plan (scaffolded from Discovery)
**Prerequisite:** Meta-{ABBREV} (Discovery Phase) — COMPLETE

---

## Vision

{Vision statement — what this plan builds and why it matters. Derived from the Meta-Plan's purpose.}

---

## Input: Consolidated Context Parts

These parts are the PRIMARY INPUT from the Discovery Phase. Every sprint and task references them.

| Part | File | Lines | Sprint Scope |
|------|------|-------|--------------|
| 1 | `Meta-{ABBREV}/Outputs/{ABBREV}-Consolidated-Context-Part-1-{Topic}.md` | {N} | {Sprint name} |
| 2 | `Meta-{ABBREV}/Outputs/{ABBREV}-Consolidated-Context-Part-2-{Topic}.md` | {N} | {Sprint name} |
| 3 | `Meta-{ABBREV}/Outputs/{ABBREV}-Consolidated-Context-Part-3-{Topic}.md` | {N} | {Sprint name} |
| {N} | ... | {N} | {Sprint name or "Cross-sprint reference"} |

**Cross-sprint reference parts** (if any) are not tied to a single sprint — relevant portions are extracted into each sprint's Execution Input.

---

## Execution Inputs

Sprint-scoped files extracted from Consolidated Context parts during scaffolding. Each sprint's Execution Input contains ONLY the content relevant to that sprint's tasks.

| Sprint | Execution Input File | Lines | Extracted From |
|--------|---------------------|-------|----------------|
| 01 | `Sprint-01-{Name}/{ABBREV}-S01-Execution-Input.md` | {N} | Part {N} + Part {N} |
| 02 | `Sprint-02-{Name}/{ABBREV}-S02-Execution-Input.md` | {N} | Part {N} + Part {N} |

Task files reference their sprint's Execution Input (with section numbers), NOT the original Consolidated Context parts.

---

## Sprint Overview

| Sprint | Name | Purpose | Primary Input | Sessions | Status |
|--------|------|---------|---------------|----------|--------|
| 01 | {SprintName} | {What this sprint delivers} | Part {N} | {count} | ⏳ NOT STARTED |
| 02 | {SprintName} | {What this sprint delivers} | Part {N} | {count} | ⏳ NOT STARTED |

**Total Sessions:** {sum}
**Prerequisite For:** {downstream project or "None"}

---

## Sprint-to-Part Mapping

| Sprint | Primary Part(s) | Reference Part(s) | Key Deliverables |
|--------|----------------|-------------------|------------------|
| 01 | Part {N} | Part {N} (cross-ref) | {deliverables} |
| 02 | Part {N} | Part {N} (cross-ref) | {deliverables} |

---

## Global Source Map

Assigns a global number to each spec output for cross-EI traceability. Execution Inputs cite sources using `Spec #{N} ({filename})` format — the number comes from this table.

| # | Source File | Primary Sprint | Also Used By |
|---|-------------|----------------|--------------|
| 1 | `{spec-output-filename-1.md}` | S{XX} | {other sprint(s) or "—"} |
| 2 | `{spec-output-filename-2.md}` | S{XX} | {other sprint(s) or "—"} |

**Shared sources:** When "Also Used By" lists additional sprints, those sprints' Execution Inputs include that source in their `Extracted from:` header.

---

## Session Completion Tracking

> **Update this table when each session completes.**

| Sprint | Session | Status | Summary File | Completed |
|--------|---------|--------|--------------|-----------|
| Sprint-01 | Session-01-{Name} | ⏳ NOT STARTED | - | - |

---

## Dependencies

| Dependency | Required For | Status |
|------------|--------------|--------|
| Meta-{ABBREV} Consolidated Context Parts | All sprints | ✅ COMPLETE |
| {Additional dependency} | {Which sprint} | {Status} |

---

## Success Criteria

### Sprint-01 Complete When:
- [ ] {Measurable criterion from Part's "What This Enables"}
- [ ] {Measurable criterion}

### Project Complete When:
- [ ] All sprints complete
- [ ] {Final deliverable criterion}
- [ ] All Consolidated Context part content implemented

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Context compaction loses progress | High | Recovery file updated after EVERY task |
| Spec parts need revision during execution | Medium | Flag in recovery, note divergence, continue |
| {Project-specific risk} | {Impact} | {Mitigation} |

---

## References

| Document | Purpose |
|----------|---------|
| [Meta-{ABBREV}/Outputs/](../Meta-{ABBREV}/Outputs/) | Consolidated Context Parts (primary input) |
| [{ABBREV}-META-Master-Plan.md](../Meta-{ABBREV}/{ABBREV}-META-Master-Plan.md) | Discovery Phase overview |
| {Additional references} | {Purpose} |

---

*Scaffolded from: Meta-{ABBREV} Discovery Phase ({N} Consolidated Context parts)*
*Last Updated: {today's date}*
```

---

## Key Differences from Standard Master Plan

| Feature | Standard | Scaffolding |
|---------|----------|-------------|
| Vision source | User provides | Derived from Meta-Plan |
| Sprint structure | User defines | Derived from part `Scope:` fields |
| Input section | None | "Input: Consolidated Context Parts" table |
| Execution Inputs | None | One per sprint — extracted from parts |
| Sprint-to-Part mapping | None | Required — maps sprints to source parts |
| Dependencies | Various | Always includes "Meta parts COMPLETE" |
| Task Required Context | Various files | MUST reference sprint Execution Input (NOT original parts) |
