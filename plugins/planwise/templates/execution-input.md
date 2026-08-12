# Execution Input Template

Use this template when creating sprint-scoped Execution Input files during scaffolding.

**When to use:** For EACH sprint during scaffolding, extract relevant content from Consolidated Context parts into a sprint-scoped file.

---

```markdown
# Sprint {XX} Execution Input: {Sprint Name}

**Sprint:** {ABBREV}-S{XX}
**Extracted from:** Spec #{N} ({exact-source-filename.md}), Spec #{M} ({exact-source-filename.md})
**Source lines:** {total from source parts} → Extracted: {lines in this file}

---

## How to Use This File

This file contains ALL the specification content needed for Sprint {XX}.
Task files reference specific sections below by number. Agents executing tasks should:
1. Read this file (scoped to your sprint — replaces the original Consolidated Context parts)
2. Focus on sections listed in your task's Required Context table
3. Do NOT load the original Consolidated Context parts — this file supersedes them

---

## Section 1: {Topic} (Tasks {comma-separated task numbers})

{Extracted content from relevant Consolidated Context part section(s).
Include FULL DETAIL — tables, code blocks, field definitions, constraints.
This is NOT a summary. It is a reorganized extraction of the source content.}

---

## Section 2: {Topic} (Tasks {comma-separated task numbers})

{Extracted content from another relevant section.
Each section should be self-contained enough for its listed tasks.}

---

## Section N: Cross-Sprint Conventions (All Tasks)

{Content extracted from cross-sprint reference parts (e.g., DesignDecisions).
Only include decisions/conventions relevant to THIS sprint's scope.}

---

## Cross-References

| Section | Source | Source Section(s) |
|---------|--------|-------------------|
| 1 | Spec #{N} ({exact-source-filename.md}) | {Section name(s)} |
| 2 | Spec #{N} ({exact-source-filename.md}) | {Section name(s)} |
| N | Spec #{N} ({exact-source-filename.md}) | {Decision N, Convention M} |

---

*Extracted during scaffolding from Meta-{ABBREV} Consolidated Context parts.*
*Source parts archived at `Meta-{ABBREV}/Outputs/` for reference if needed.*
```

---

## Rules

1. **Extract, don't summarize.** Copy substantive content verbatim from Consolidated Context parts. Reorganize by sprint scope, but do NOT compress or paraphrase
2. **Section-to-Task mapping.** Each section header lists which tasks use it in parentheses — this tells agents exactly where to look
3. **Self-contained.** Executing agents should NOT need the original Consolidated Context parts. The Execution Input replaces them for that sprint's scope
4. **Cross-references table.** Trace every section back to its source part and section — enables auditing and recovery
5. **500-line limit.** If a sprint needs more, split into parts:
   - `{Abbrev}-S{XX}-Execution-Input-Part-1-{Topic}.md`
   - `{Abbrev}-S{XX}-Execution-Input-Part-2-{Topic}.md`
6. **Cross-sprint content.** Only extract the portions of cross-sprint reference parts that are relevant to THIS sprint. Don't include all design decisions if only 2 of 8 apply
7. **Citation validity.** Every file cited in Cross-References MUST appear in the `Extracted from:` header. If you extract content from a source not originally assigned to this sprint, add it to `Extracted from:` with its global number
8. **Exact filenames.** Cross-References use `Spec #{N} ({exact-filename.md})` format — global number for cross-EI traceability plus filename for unambiguous verification. Never use bare numbers like "Spec #2" without the filename
9. **Cross-sprint imports.** If extracting content from another sprint's primary source (not a cross-sprint reference part), list that source in `Extracted from:` like any other source. The Global Source Map in the Master Plan tracks which sources are shared across sprints

---

## Naming Convention

| Variant | Pattern | When |
|---------|---------|------|
| Single file | `{Abbrev}-S{XX}-Execution-Input.md` | Sprint input under 500 lines |
| Multi-part | `{Abbrev}-S{XX}-Execution-Input-Part-{N}-{Topic}.md` | Sprint input over 500 lines |

---

## Location

Lives in the sprint folder, alongside the sprint plan:

```
Sprint-{XX}-{Name}/
├── {Abbrev}-S{XX}-Execution-Input.md     <-- HERE
├── {Abbrev}-S{XX}-Sprint-Plan.md
└── Session-{YY}-{Name}/
    ├── {Abbrev}-S{XX}-{YY}-Orchestration.md
    ├── {Abbrev}-S{XX}-{YY}-Recovery.md
    ├── Task files...
    └── Outputs/
```

---

## Extraction Process

During scaffolding, for each sprint:

1. **Identify source parts.** Which Consolidated Context parts feed this sprint? (from the Sprint-to-Part mapping)
2. **Read source parts.** Read each identified part fully
3. **Extract by task scope.** For each task in the sprint, identify which sections of which parts it needs
4. **Group into sections.** Organize extracted content into logical sections, noting which tasks use each
5. **Filter cross-sprint parts.** From cross-sprint reference parts, extract ONLY the decisions/conventions this sprint needs
6. **Build cross-references table.** Map each section back to its source part and section
7. **Check line count.** If over 500 lines, split into topic-focused parts

---

## How Task Files Reference Execution Inputs

**Before (referencing Consolidated Context parts directly):**
```markdown
## Required Context

| Priority | File | Purpose |
|----------|------|---------|
| 1 | `Meta-GCW/Outputs/GCW-Consolidated-Context-Part-2-SchemaDesign.md` | Schema fields (Sections 1-4) |
| 2 | `Meta-GCW/Outputs/GCW-Consolidated-Context-Part-5-DesignDecisions.md` | Design rationale |
```

**After (referencing sprint Execution Input):**
```markdown
## Required Context

| Priority | File | Purpose |
|----------|------|---------|
| 1 | `GCW-S01-Execution-Input.md` — Section 1 | Base schema fields (17 common metadata) |
| 2 | `GCW-S01-Execution-Input.md` — Section 2 | Extension schemas (5 type-specific) |
| 3 | `GCW-S01-Execution-Input.md` — Section 3 | YAML templates (copy-paste ready) |
| 4 | `GCW-S01-Execution-Input.md` — Section 4 | Design conventions (ID format, versioning) |
```

**Section reference rule:** Enumerate INDIVIDUAL sections with purpose — never ranges like `(Sections 1-3)`.

**Benefits:**
- Agent reads ONE file instead of multiple parts
- Content is already scoped — no irrelevant sections to skip
- File is in the same sprint folder — simple relative path
- Section numbers in the task file map directly to Execution Input headers
