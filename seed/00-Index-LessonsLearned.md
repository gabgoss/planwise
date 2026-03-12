# Lessons Learned Index

**Purpose:** Central index and taxonomy reference for all lessons learned.
**Last Updated:** YYYY-MM-DD

---

## Naming Convention

**Format:** `LL-{NNN}-{Domain}-{Name}.md`

| Component | Description | Example |
|-----------|-------------|---------|
| `LL` | Lessons Learned prefix | LL |
| `{NNN}` | Global sequence number (zero-padded to 3 digits) | 001, 023 |
| `{Domain}` | Abbreviation from config.yaml (`abbreviations` + `lesson_abbreviations`) | DOC, TOOL |
| `{Name}` | PascalCase descriptive name | QueryFilterTranslation |

**Next available ID:** LL-001

---

## Status Definitions

| Status | Meaning |
|--------|---------|
| `documented` | Lesson captured but not yet acted on |
| `applied` | Lesson applied to improve a process or pattern |
| `rule` | Lesson promoted to a `.claude/` artifact |

---

## Quick Reference

| Action | How |
|--------|-----|
| Find lessons by tag | `/lessons python regex` |
| Find by domain | `/lessons myproject` |
| Find by category | `/lessons anti-pattern` |
| List all lessons | `/lessons` (no arguments) |
| Create new lesson | Use template below, next ID = LL-001 |

---

## Master Table

| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status |
|----|-------|----------|----------|----------|------------|--------|--------|--------|
| | | | | | | | | |

---

## Lesson File Template

```yaml
---
id: LL-{NNN}
title: {Descriptive title}
date: {YYYY-MM-DD}
source: {session reference}
category: {anti-pattern | pattern | process}
severity: {low | medium | high}
language: [{python | csharp | javascript | ...}]
technology: [{specific tech}]
domain: [{project domains}]
status: documented
applied-as: null
---

# LL-{NNN}-{Domain}: {Same title as frontmatter}

## Context

{What happened — specific file, function, input, error.}

## Lesson

{The insight or fix. Include WRONG/CORRECT code examples for anti-patterns.}

## Applies To

{When this lesson is relevant — technologies, file patterns, scenarios.}
```

---

## Archive

Lessons with status `applied` or `rule` are moved to `Archive/` as part of the `/lessons promote` workflow. Archived lessons remain searchable via `/lessons <terms>` (search globs recurse into `Archive/`).

**Location:** `{lessons-dir}/Archive/`

---

## Rule Promotion Log

| Date | Lesson ID | Artifact Created | File |
|------|-----------|-----------------|------|
| | | | |

---
