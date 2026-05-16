# Lessons Learned — Categorization by Domain

<!--
  Template rendered by `/planwise init` from `config.yaml: categorization`.
  Placeholders in `{CURLY_BRACES}` are substituted at render time.
  Iteration directives `{FOR EACH BUCKET ...}` ... `{END}` expand per bucket.
  After init, this file is maintained by `/planwise lessons curate`.
-->

**Purpose:** Group lessons in `{lessons_dir}/` by domain for scope-specific review and rule-promotion decisions.
**Last Updated:** {TODAY}
**Companion to:** [{lessons_index}]({lessons_index}) (chronological master table)

---

## Scope

{SCOPE_PARAGRAPH}

---

{FOR EACH BUCKET in config.yaml: categorization.buckets:}

## {BUCKET_ID}. {BUCKET_NAME} (0)

{BUCKET_DESCRIPTION}

<!--
  Column schema:
  - Default (3 columns): | ID | Title | Severity |
  - If bucket has `code_bucket: true` in config.yaml: 4 columns: | ID | Title | Module | Severity |
-->

| ID | Title | Severity |
|----|-------|----------|

{IF bucket has sub_buckets:}

### {SUB_ID}. {SUB_NAME} (0)

| ID | Title | Severity |
|----|-------|----------|

{END}

{END}

---

## Cross-cutting observations

_Populated by `/planwise lessons curate` as patterns emerge across buckets._

---

## Classification edge cases

| ID | Why it could fit elsewhere | Final bucket |
|----|---------------------------|---------------|

---
