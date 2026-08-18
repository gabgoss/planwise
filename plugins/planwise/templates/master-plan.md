# Master Plan Template

Use this template when creating `{Abbrev}-Master-Plan.md`.

---

```markdown
# {PlanName} Master Plan

**Plan Abbreviation:** {ABBREV}
**Status:** READY_TO_EXECUTE
**Created:** {today's date}
**Token Saver:** inherit   <!-- optional; "inherit" (or omit) = use config.yaml context.token_saver; "on"/"off" overrides Token Saver for THIS plan only. Overhead numbers are always project-level. -->

---

## Vision <!-- REQUIRED -->

{User's vision statement - 2-3 sentences describing what this plan accomplishes and why it matters}

---

## Sprint Overview <!-- REQUIRED -->

| Sprint | Name | Purpose | Sessions | Status |
|--------|------|---------|----------|--------|
| 01 | {SprintName} | {What this sprint delivers} | {count} | ⏳ NOT STARTED |

**Total Sessions:** {sum of all sessions} <!-- REQUIRED -->
**Prerequisite For:** {next plan or "None - standalone project"}

---

## Dependencies

| Dependency | Required For | Status |
|------------|--------------|--------|
| {Document or prior plan} | {Which sprint needs it} | ⏳ Pending |

---

## Decisions (Locked)

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | {what was decided, in one sentence} | {why; what the alternative was} |

---

## Session Completion Tracking <!-- REQUIRED -->

> **Update this table when each session completes.**

| Sprint | Session | Status | Summary File | Completed |
|--------|---------|--------|--------------|-----------|
| Sprint-01 | Session-01-{Name} | ⏳ NOT STARTED | - | - |

**Status Legend:**
- ✅ COMPLETE - All tasks done, summary written, verification passed
- 🔄 IN PROGRESS - Currently executing
- ⏳ NOT STARTED - Ready to begin
- ⛔ BLOCKED - Cannot proceed (document reason)

---

## Success Criteria <!-- REQUIRED -->

### Sprint-01 Complete When:
- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}

### Project Complete When:
- [ ] All sprints complete
- [ ] {Final deliverable criterion}

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Context compaction loses progress | High | Recovery file updated after EVERY task |
| {Project-specific risk} | {Impact} | {Mitigation} |

---

## References

- [{Reference document}](path) - {What it provides}

---

*Last Updated: {today's date}*
```
