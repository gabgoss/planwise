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

## Execution Ordering <!-- REQUIRED -->

**Declared ordering:** `Sprint-01 → { Sprint-02 ∥ Sprint-03 }`

<!-- The `∥` symbol marks sprints declared to run in parallel. A parallel claim
     inferred from cluster names alone (e.g. "agents vs handlers, disjoint
     files") is not a computed fact — every `∥` pair declared here MUST have
     its write-sets intersected in the Computed Write-Set Intersection table
     below before the ordering is treated as binding. -->

### Write-Sets

<!-- Collected from each sprint's own Sprint Plan `## Write-Set` section. -->

| Sprint | Write-set |
|--------|-----------|
| Sprint-01 | `{path/or/directory}`, `{path/or/directory}` |
| Sprint-02 | `{path/or/directory}`, `{path/or/directory}` |

### Computed Write-Set Intersection

<!-- Every declared-parallel pair above MUST appear here with its computed
     result shown — never asserted, never inferred from cluster names. `∅`
     means the parallelism stands as declared. A non-empty intersection
     permits exactly two dispositions: (1) serialize the pair, dropping `∥`;
     or (2) qualify the parallelism per-file, naming an explicit task-level
     ordering edge for each shared file (`S0A-01-0x → S0B-01-0y`). A gate
     marker that is an assumption rather than a runnable command (e.g. "n/a —
     single-writer per sprint") is not a valid Verdict. -->

| Declared pair | Intersection | Verdict |
|----------------|---------------|---------|
| Sprint-02 ∥ Sprint-03 | `{shared/path.ext}` or `∅` | {✅ disjoint — parallel stands / ❌ NOT disjoint — serialized / ⚠ NOT disjoint — qualified per-file: `S0A-01-0x → S0B-01-0y`} |

**Recompute this matrix whenever any sprint's write-set changes.** Last
recomputed: {today's date}.

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
