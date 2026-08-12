# Sample Scaffolding Output

This example shows the output produced by `/planwise plan` in **Scaffolding Mode** — when creating an Execution Plan from Consolidated Context parts produced by a Meta-Plan Discovery phase.

---

## User Request

```
/planwise plan MyProject-Warehouse Execution Plan

Context: This is the SCAFFOLDING PHASE of a 3-phase Meta-Plan.
The Discovery Phase (Meta-MPW) produced 5 Consolidated Context parts at:
  Meta-MPW/Outputs/

  Part 1: MPW-Consolidated-Context-Part-1-ArtifactInventory.md (374 lines)
  Part 2: MPW-Consolidated-Context-Part-2-SchemaDesign.md (417 lines)
  Part 3: MPW-Consolidated-Context-Part-3-QueryAndRegistration.md (368 lines)
  Part 4: MPW-Consolidated-Context-Part-4-DomainTaxonomy.md (392 lines)
  Part 5: MPW-Consolidated-Context-Part-5-DesignDecisions.md (473 lines)

Abbreviation: MPW
Location: Exec-MPW/
```

---

## Mode Detection

Scaffolding indicators found:
- User mentions "Consolidated Context parts" ✅
- User provides path to `Meta-MPW/Outputs/` ✅
- User says "scaffolding phase" ✅

**Mode: Scaffolding** (skip Q&A, read parts instead)

---

## Parts Read

| Part | Scope (from header) | Sprint Mapped |
|------|---------------------|---------------|
| 1 (ArtifactInventory) | Registry Population Sprint | Sprint 02 |
| 2 (SchemaDesign) | Schema Implementation Sprint | Sprint 01 |
| 3 (QueryAndRegistration) | API Implementation Sprint | Sprint 02-03 |
| 4 (DomainTaxonomy) | Domain System Sprint | Sprint 03 |
| 5 (DesignDecisions) | Cross-sprint reference | All sprints (extracted per sprint) |

**Sprint ordering rationale:** Schema first (foundation), then registration (needs schema), then query+domain (needs registry populated).

---

## Execution Inputs Created

For each sprint, relevant content was **extracted** from the Consolidated Context parts into a sprint-scoped Execution Input.

| Sprint | Execution Input | Lines | Extracted From |
|--------|----------------|-------|----------------|
| 01 | `MPW-S01-Execution-Input.md` | ~280 | Part 2 (schema fields, YAML templates) + Part 5 (Decisions 1, 6, 7) |
| 02 | `MPW-S02-Execution-Input.md` | ~350 | Part 1 (artifact registry) + Part 3 (registration protocol) + Part 5 (Decisions 2, 3) |
| 03 | `MPW-S03-Execution-Input.md` | ~380 | Part 3 (query functions) + Part 4 (domain taxonomy) + Part 5 (Decisions 4, 5, 8) |

**Key points:**
- Part 5 (DesignDecisions, 473 lines) was NOT copied in full to any sprint — each sprint got only the 2-3 decisions relevant to its scope
- Part 3 (QueryAndRegistration, 368 lines) feeds both Sprint 02 and 03 — registration sections went to S02, query sections to S03
- Each Execution Input is self-contained: agents don't need to read the original parts

---

## Files Created

```
{plans-dir}/MyProject-Warehouse/Exec-MPW/
├── MPW-Master-Plan.md
├── Sprint-01-SchemaFoundation/
│   ├── MPW-S01-Execution-Input.md              <-- NEW: Sprint-scoped spec
│   ├── MPW-S01-Sprint-Plan.md
│   └── Session-01-SchemaDesign/
│       ├── MPW-S01-01-Orchestration.md
│       ├── MPW-S01-01-Recovery.md
│       ├── MPW-S01-01-01-Haiku-ValidatePartContent.md
│       ├── MPW-S01-01-02-Sonnet-CreateBaseSchema.md
│       ├── MPW-S01-01-03-Sonnet-CreateExtensionSchemas.md
│       ├── MPW-S01-01-04-Sonnet-CreateFolderStructure.md
│       └── Outputs/
├── Sprint-02-ArtifactRegistration/
│   ├── MPW-S02-Execution-Input.md              <-- NEW
│   ├── MPW-S02-Sprint-Plan.md
│   └── Session-01-RegisterExisting/
│       ├── MPW-S02-01-Orchestration.md
│       ├── MPW-S02-01-Recovery.md
│       ├── MPW-S02-01-01-Haiku-InventoryCheck.md
│       ├── MPW-S02-01-02-Sonnet-BuildRegistrationModule.md
│       ├── MPW-S02-01-03-Sonnet-RegisterAllArtifacts.md
│       └── Outputs/
└── Sprint-03-QueryAndDomain/
    ├── MPW-S03-Execution-Input.md              <-- NEW
    ├── MPW-S03-Sprint-Plan.md
    └── Session-01-QuerySystem/
        ├── MPW-S03-01-Orchestration.md
        ├── MPW-S03-01-Recovery.md
        ├── MPW-S03-01-01-Sonnet-BuildQueryModule.md
        ├── MPW-S03-01-02-Sonnet-BuildDomainClustering.md
        ├── MPW-S03-01-03-Sonnet-BuildCLI.md
        └── Outputs/
```

---

## Output Message

```
PLAN SCAFFOLDED: MyProject-Warehouse Execution Plan

SCAFFOLDED FROM: Meta-MPW Discovery Phase
Parts consumed: 5 Consolidated Context parts (2,024 lines)
Execution Inputs created: 3 (one per sprint, ~1,010 lines total)
Sprints created: 3

**Abbreviation:** MPW
**Location:** {plans-dir}/MyProject-Warehouse/Exec-MPW/

**Execution Input Mapping:**
  Sprint 01 (Schema Foundation): MPW-S01-Execution-Input.md (~280 lines)
    ← Part 2 (SchemaDesign) + Part 5 (Decisions 1, 6, 7)
  Sprint 02 (Artifact Registration): MPW-S02-Execution-Input.md (~350 lines)
    ← Part 1 (ArtifactInventory) + Part 3 (Registration) + Part 5 (Decisions 2, 3)
  Sprint 03 (Query & Domain): MPW-S03-Execution-Input.md (~380 lines)
    ← Part 3 (Queries) + Part 4 (DomainTaxonomy) + Part 5 (Decisions 4, 5, 8)

**Files Created:** 21 files across 3 sprints (including 3 Execution Inputs)
**Task Files Created:** 10 files (one per task)

**Next Steps:**
1. Review the Master Plan and Execution Input mapping
2. Review Execution Inputs — verify content was extracted correctly from source parts
3. Review task files — verify each references its sprint's Execution Input
4. Execute Sprint-01 Session-01 using `/execute`
```

---

## Example Execution Input (Sprint 01)

This shows the structure of a sprint-scoped Execution Input file:

```markdown
# Sprint 01 Execution Input: Schema & Foundation

**Sprint:** MPW-S01
**Extracted from:** Spec #2 (MPW-Consolidated-Context-Part-2-SchemaDesign.md), Spec #5 (MPW-Consolidated-Context-Part-5-DesignDecisions.md)
**Source lines:** 890 → Extracted: 280

---

## How to Use This File

This file contains ALL the specification content needed for Sprint 01.
Task files reference specific sections below by number. Agents executing tasks should:
1. Read this file (scoped to your sprint — replaces the original Consolidated Context parts)
2. Focus on sections listed in your task's Required Context table
3. Do NOT load the original Consolidated Context parts — this file supersedes them

---

## Section 1: Base Schema Fields (Tasks 2, 3, 5, 6)

### 17 Common Metadata Fields

| # | Field | Type | Required | Description |
|---|-------|------|----------|-------------|
| 1 | id | string | YES | Unique identifier: `{type}-{name}` |
| 2 | name | string | YES | Human-readable name |
| ... | ... | ... | ... | ... |
| 17 | schema_version | string | YES | `warehouse-schema-v1` |

{Full field table extracted verbatim from Part 2 Section 1}

---

## Section 2: Extension Schemas (Tasks 3, 5)

### Rule Extension (4 fields)
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| scope_type | enum | YES | global, path-specific |
| ... | ... | ... | ... |

### Skill Extension (7 fields)
...

{Full extension tables extracted verbatim from Part 2 Section 2}

---

## Section 3: YAML Templates (Task 3)

{Complete YAML block templates from Part 2 Section 4 — copy-paste ready}

---

## Section 4: Design Conventions (Tasks 2, 3, 4, 5)

### Decision 1: Base + Extension Pattern
{Why this pattern was chosen — extracted from Part 5}

### Decision 6: ID Format
{ID format rules — `{type}-{name}` — extracted from Part 5}

### Decision 7: Confidence as Required Field
{Confidence scoring rationale — extracted from Part 5}

---

## Cross-References

| Section | Source | Source Section(s) |
|---------|------------|-------------------|
| 1 | Spec #2 (MPW-Consolidated-Context-Part-2-SchemaDesign.md) | Section 1: Common Metadata Fields |
| 2 | Spec #2 (MPW-Consolidated-Context-Part-2-SchemaDesign.md) | Section 2: Type Extension Schemas |
| 3 | Spec #2 (MPW-Consolidated-Context-Part-2-SchemaDesign.md) | Section 4: Recommended Master Schema |
| 4 | Spec #5 (MPW-Consolidated-Context-Part-5-DesignDecisions.md) | Decisions 1, 6, 7 |

---

*Extracted during scaffolding from Meta-MPW Consolidated Context parts.*
*Source parts archived at `Meta-MPW/Outputs/` for reference if needed.*
```

---

## Example Task File (with Execution Input reference)

This shows how a task file references its sprint's Execution Input instead of the original Consolidated Context parts:

```markdown
# Task: Sonnet-CreateBaseSchema

**Task ID:** MPW-S01-01-02
**Agent:** Sonnet
**Estimated Tokens:** ~30K
**Depends On:** 1

---

## Objective

Create the base YAML schema file (schema.yaml) implementing the 17 common metadata fields
defined in the Execution Input.

---

## Required Context

| Priority | File | Est. Lines | Est. Tokens | Purpose |
|----------|------|-----------|-------------|---------|
| 1 | `MPW-S01-Execution-Input.md` — Section 1 | ~50 | ~0.7K | Base schema fields (17 common metadata) |
| 2 | `MPW-S01-Execution-Input.md` — Section 2 | ~65 | ~0.8K | Extension schemas (rule, skill, hook, agent, plugin) |
| 3 | `MPW-S01-Execution-Input.md` — Section 3 | ~45 | ~0.6K | YAML templates (copy-paste ready blocks) |
| 4 | `MPW-S01-Execution-Input.md` — Section 4 | ~40 | ~0.5K | Design conventions (ID format, versioning) |
| 5 | Task 1 output | ~15 | ~0.2K | Directory verification results |

**Context subtotal:** ~3K tokens (reads) + ~27K (output) = ~30K total

---

## Execution Steps

1. Read Execution Input Section 1 — base schema fields (17 common metadata)
2. Read Execution Input Section 2 — extension schemas (5 type-specific)
3. Read Execution Input Section 3 — YAML templates (copy-paste ready)
4. Read Execution Input Section 4 — ID format and versioning conventions
5. Create `schema.yaml` with all 17 base fields
6. Add all 5 extension schemas
7. Add schema version header

---

## Expected Output

- `schema.yaml` — Complete schema with base + extensions, copy-paste-ready
- Validation against Execution Input Section 1 field table (all 17 fields present)

---

## Success Criteria

- [ ] schema.yaml created with all 17 base fields from Execution Input Section 1
- [ ] All 5 extension schemas present with correct field counts
- [ ] Field types match Execution Input specification exactly
- [ ] ID format follows `{type}-{name}` pattern (per Section 4)
- [ ] schema_version field present (per Section 4)
```

**Note:** The task references `MPW-S01-Execution-Input.md` with individual section numbers and purpose annotations — not ranges like `(Sections 1-3)` and not the original `Meta-MPW/Outputs/` parts. The agent reads ONE file that's already scoped to Sprint 01.

---

## Key Differences from Standard Planning

| Aspect | Standard | Scaffolding |
|--------|----------|-------------|
| Information source | User Q&A | Consolidated Context parts |
| Sprint structure | User-defined | Derived from part `Scope:` fields |
| Execution Inputs | None | One per sprint (extracted from parts) |
| Master Plan template | `master-plan.md` | `scaffolding-master-plan.md` |
| Task Required Context | Various project files | Sprint's Execution Input (with section numbers) |
| Validation | Standard checklist | Standard + Execution Input coverage check |
| Output message | "PLAN CREATED" | "PLAN SCAFFOLDED" with Execution Input mapping |
