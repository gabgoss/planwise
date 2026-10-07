# Lesson File Template

Use this template when creating `LL-{NNN}-{Domain}-{Name}.md` under `{lessons_dir}/`.

---

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
promotion-target: [rule|code|claude-md|agent|skill|settings]   # one or more target types; multi-value = coarse / split-candidate
# promoted-to:                                                  # owning backlog item id(s), e.g. BB-{NNN}; set at capture-archive
# rule-as:                                                      # DEPRECATED alias for applied-as — read for back-compat, never written
---

# LL-{NNN}-{Domain}: {Same title as frontmatter}

## Context

{What happened — specific file, function, input, error.}

## Lesson

{The insight or fix. Include WRONG/CORRECT code examples for anti-patterns.}

## Applies To

{When this lesson is relevant — technologies, file patterns, scenarios.}
```

The frontmatter pointer fields' semantics are defined once, in `references/lessons-schema.md § Pointer Fields — Authoritative Definition`. Do not restate them here.
