---
description: Markdown header hierarchy, section structure, YAML frontmatter, structural signals, emphasis, and cross-reference conventions
consult-when: Formatting a markdown doc — header hierarchy, section length limits, frontmatter, cross-refs
---

# Markdown Conventions

## 1. Header Hierarchy

USE exactly one H1 per document as the document title. Place it on line 1 (or after YAML frontmatter).

NEVER skip heading levels. H2 follows H1, H3 follows H2. Do NOT jump from H1 to H3.

STRUCTURE documents as:
- **H1** = Document title (single, required)
- **H2** = Major sections (numbered `## 1.` or named `## Section Name`)
- **H3** = Subsections within an H2
- **H4-H6** = Use when the content genuinely nests that deep. Deep nesting is a signal to check whether the H2 covers more than one concern — it is not by itself a reason to split into a separate file.

SEPARATE major H2 sections with horizontal rules (`---`) for visual clarity.

> [!constraint] One H1, and no skipped heading level
> WRONG — the H1 is followed directly by an H3: `# Title`, then `### Subsection`.
> CORRECT — an H2 sits between them: `# Title`, then `## Section`, then `### Subsection`.

`scripts/lint_markdown.py` checks this section. Its `heading-h1` rule reports a missing or second H1, and its `heading-skip` rule reports a skipped level. A plugin test runs it with `--strict` over the shipped `references/` and requires zero findings.

## 2. Section Structure

SIZE a section by what it covers, not by its line count. One section = one idea; a section is the right length when it fully covers that idea and no more.

SPLIT a section when it covers two distinct concerns a reader would look for separately — not when it crosses a line threshold. Prefer H3 subsections inside the section; promote to a separate file only when the split content is independently addressable.

PLACE the most important content immediately after the header. Attention degrades with position in the whole context, not with a section's length — a long section whose key claim sits under its header reads better than the same content fragmented under invented subheadings.

ADD a table of contents when a document has enough H2 sections that a reader would scan for one (roughly 6+). Do not add one to a short document because it crossed a line count.

NEVER pad a section to reach a minimum length, and NEVER compress, summarize, or drop content to stay under a maximum. File size is governed by the measured Read-tool gates, never by line counts — see [session-context-budget.md](session-context-budget.md) (22,000 tokens / 245,760 bytes / 2,000 lines, whichever binds first).

`scripts/measure_files.py` measures a file against these gates and prints its level. `scripts/read_limits.py` classifies a file against the same limits.

## 3. YAML Frontmatter

USE YAML frontmatter (`---` delimiters) for all rule files and skill files.

INCLUDE at minimum: `description` field explaining the file's purpose.

USE lowercase property names and plural forms (`tags` not `tag`, `aliases` not `alias`).

FORMAT dates as ISO 8601: `YYYY-MM-DD`.

> [!constraint] Plural lowercase property names and ISO dates
> WRONG — a singular property and a non-ISO date: `tag: authoring` and `date: 11/19/2026`.
> CORRECT — the plural property and the ISO 8601 form: `tags: [authoring]` and `date: 2026-11-19`.

`scripts/lint_markdown.py` checks the `description` key. Its `frontmatter-description` rule reports a rule file (a path with a `rules` folder) or a `SKILL.md` file that has no non-empty `description`.

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

> [!constraint] A local link names its file extension
> WRONG — the target has no extension: `[reference](reference)`.
> CORRECT — the target ends in `.md`: `[reference](reference.md)`.

`scripts/lint_markdown.py` checks links. Its `link-extension` rule reports a local link whose target has no file extension at all. A target with another extension, such as `.py`, passes it.

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
