---
description: Markdown header hierarchy, section length limits, YAML frontmatter, structural signals, emphasis, and cross-reference conventions
---

# Markdown Conventions

## 1. Header Hierarchy

USE exactly one H1 per document as the document title. Place it on line 1 (or after YAML frontmatter).

NEVER skip heading levels. H2 follows H1, H3 follows H2. Do NOT jump from H1 to H3.

STRUCTURE documents as:
- **H1** = Document title (single, required)
- **H2** = Major sections (numbered `## 1.` or named `## Section Name`)
- **H3** = Subsections within an H2
- **H4-H6** = Rarely needed. If you need H4+, the section should probably be split into a separate file.

SEPARATE major H2 sections with horizontal rules (`---`) for visual clarity.

## 2. Section Length Limits

KEEP individual sections between 50-150 lines. Content in the middle of sections over 150 lines gets less attention (Stanford "Lost in the Middle" research — 30%+ degradation).

SPLIT sections exceeding 150 lines into subsections with H3 headers.

ADD a table of contents when a document exceeds 100 lines total.

## 3. YAML Frontmatter

USE YAML frontmatter (`---` delimiters) for all rule files and skill files.

INCLUDE at minimum: `description` field explaining the file's purpose.

USE lowercase property names and plural forms (`tags` not `tag`, `aliases` not `alias`).

FORMAT dates as ISO 8601: `YYYY-MM-DD`.

## 4. Structural Signals (Ranked by Strength)

USE these structural elements in order of signal strength when Claude needs to distinguish content:

| Signal | Strength | When to Use |
|--------|----------|-------------|
| Headers (H1-H6) | PRIMARY | Boundary detection, hierarchy encoding |
| Code blocks (```) | CONTENT TYPE | Mode switch between code and prose |
| Tables (\| col \|) | STRUCTURED DATA | Parallel data, lookup relationships |
| Numbered lists | ENUMERATION | Ordered sequences, workflows |
| Callouts (`> [!type]`) | SEMANTIC MARKUP | Content type disambiguation |
| Horizontal rules (`---`) | WEAK | Visual separator only, no semantic content |

## 5. Emphasis Conventions

USE `**BINDING**` as the single emphasis keyword for enforcement-level content. When a section or rule carries enforcement weight, mark it with **BINDING** — do not alternate between CRITICAL, REQUIRED, MANDATORY, or NON-NEGOTIABLE.

USE `**Purpose:**` bold-colon pattern to open self-describing sections.

USE `**bold**` for key terms on first use in a section.

PREFER descriptive headings over bolded text — headings are addressable via links, bold text is not.

## 6. Cross-Reference Conventions

USE relative markdown links for cross-references: `[display text](relative/path.md)`.

INCLUDE the file extension in links: `[reference](reference.md)` not `[reference](reference)`.

REFERENCE specific sections with anchors when the target file is large: `[Section Name](file.md#section-name)`.

USE `file_path:line_number` format when referencing specific code locations in conversation.

## 7. Content Organization

PLACE the most important information at the beginning of sections — content near headers gets the strongest attention signal.

USE tables for parallel structured data (comparisons, mappings, reference lookups).

USE numbered lists for ordered sequences and workflows.

USE bullet lists for unordered collections of related items.

WRAP long content blocks in callouts (`> [!type]`) when the content type would otherwise be ambiguous.

---

*These conventions apply to all markdown files in this project.*
