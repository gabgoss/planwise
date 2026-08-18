---
description: Feedback submission engine — the shared outward-post pipeline for /planwise feedback and every other outward-facing GitHub issue call site
---

# Feedback Submission Engine

**Purpose:** This file is the ONE place the outward submission pipeline is specified: the
gate chain, the draft-first invocation, the fallback posture, the Auto-Mode deviation, the
issue body spec, and the privacy contract. It is a shared engine, not a handler — it has no
entry point of its own.

**Consumers (delegate here; do not re-specify any of the below locally):**
- `handlers/feedback.md`
- `handlers/upgrade.md` Step 4.2
- `handlers/lessons.md` (capture-prompt upstream option)
- `handlers/backlog.md` (create-prompt upstream option)

---

## Gate Chain

ALL gates below MUST pass, in this order, before a post is attempted:

1. **`feedback.enabled: true`** — config key, default `false` (mirrors the upgrade flow's
   opt-in precedent).
2. **Interactive session.** In Auto Mode the pipeline is **draft-only, unconditionally** —
   gates 3-5 are skipped and execution proceeds straight to the draft-write step below.
3. **`gh` resolvable on PATH.**
4. **`gh auth status` exits 0.** An unauthenticated `gh` otherwise fails at post time with
   no fallback; checking auth before rendering moves that failure into the fallback path
   where it belongs.
5. **Explicit `AskUserQuestion` displaying the rendered body verbatim**, immediately before
   the post — the user approves the exact text that will be published, not a summary of it.

<!-- AUTO-MODE: critical -->

**Quick reference:**

| # | Gate | On Auto Mode |
|---|------|---------------|
| 1 | `feedback.enabled: true` | Unaffected — config-based, no session distinction. |
| 2 | Interactive session | Draft-only, unconditionally; gates 3-5 are skipped. |
| 3 | `gh` on PATH | Only evaluated in an interactive session. |
| 4 | `gh auth status` exits 0 | Only evaluated in an interactive session. |
| 5 | Explicit consent (`AskUserQuestion`) | Auto-deny → draft written, exit 0 (see the Auto Mode deviation below, not a fail-loud STOP). |

---

## Draft-First, Then Post

One artifact, two outcomes. The engine ALWAYS writes the draft file first, then posts
*from that file*:

```
gh issue create -R {feedback.repo} --title "{title}" --body-file "{draft_path}" --label {label}
```

- `{feedback.repo}` resolves to the literal `gabgoss/planwise` by default and is **NEVER**
  derived from the consumer's git remote — that would file planwise issues in the
  consumer's own project repo.
- `--title` carries the title; the body file contains **no** `Title:` line.
- `{label}` mirrors the label the repo's own Issue Forms apply for the same kind
  (`.github/ISSUE_TEMPLATE/bug_report.yml` → `bug`; `lesson_or_idea.yml` → `enhancement`)
  — see the `{kind}` → `{label}` mapping below. A CLI-created issue never goes through
  the Issue Forms chooser, so without this flag the issue posts with no label at all,
  silently losing the categorization a web-filed report gets for free.
- Draft path: `{planwise_root}/feedback-drafts/{YYYY-MM-DD}-{kind}-{slug}.md`.
- Draft-first buys three things: approved text and posted text are byte-identical; a
  failed post leaves a recoverable artifact; the fallback path is not a separate code
  path — it is "stop after step 1."

---

## On Any Gate Failure or Post Failure

1. Keep the draft file on disk — do not delete it.
2. Print the draft's absolute path.
3. Print `https://github.com/gabgoss/planwise/issues` so the consumer can paste the draft
   into the web UI by hand.
4. Never block, never error out — the parent flow is unaffected.

---

## Auto Mode — A Deliberate, Documented Deviation

The generic Auto Mode policy says a `critical` site fails loud and STOPs on auto-deny.
**This site deviates on the last step:** on auto-deny the engine writes the draft and
continues, exit 0.

**Rationale:** the policy's fail-loud behavior exists for questions whose absence makes
execution *incorrect*. Here, the declined branch has a complete, correct, documented
outcome — a draft on disk — and failing loud would let an unattended feedback attempt
break an otherwise-successful parent flow. The site still carries
`<!-- AUTO-MODE: critical -->` so it passes the policy's compliance grep.

---

## Issue Body Spec

Deliberately free of any authoring project's bookkeeping vocabulary (no ID prefixes, no
required ID fields — a consumer does not have them).

**`kind: bug`:**

```markdown
### What happened

{user-supplied}

### What I expected

{user-supplied}

### Steps to reproduce

{user-supplied}

### Environment

- planwise version: {plugin_version from config.yaml}
- Subcommand involved: /planwise {subcommand}   (or "not command-specific")
- OS / shell: {user-supplied}
```

**`kind: lesson|idea`:** the first three headings become **What I learned / Why it
matters / Where it would apply**; Environment is unchanged.

```markdown
### What I learned

{user-supplied}

### Why it matters

{user-supplied}

### Where it would apply

{user-supplied}

### Environment

- planwise version: {plugin_version from config.yaml}
- Subcommand involved: /planwise {subcommand}   (or "not command-specific")
- OS / shell: {user-supplied}
```

---

## Privacy Contract — Default-Closed

Only `plugin_version` is auto-filled; everything else is user-typed or user-confirmed.

**NEVER auto-attach:**
- consumer project file contents
- absolute paths inside the consumer's repo
- `config.yaml` verbatim
- plan/backlog/lesson file bodies
- git remote URLs

The consent prompt states plainly the body will be **public** on a third-party repo.
Consumer-side identifiers the user pastes into their own prose are their vocabulary and
harmless — the template does not strip them, and it asks for a self-contained description
so the report stands alone without them.

---

## Placeholder Reference

Every placeholder used above, for the four call sites that render this engine's templates:

| Placeholder | Resolves to |
|---|---|
| `{feedback.repo}` | `gabgoss/planwise` (literal default; never the consumer's own remote). |
| `{title}` | The issue title, supplied by the caller. |
| `{draft_path}` | `{planwise_root}/feedback-drafts/{YYYY-MM-DD}-{kind}-{slug}.md`. |
| `{planwise_root}` | The consumer's configured planwise root directory. |
| `{YYYY-MM-DD}` | The date the draft is written. |
| `{kind}` | `bug`, `lesson`, or `idea` — selects the body variant. |
| `{label}` | The single `gh issue create --label` value for `{kind}`: `bug` → `bug`; `lesson` or `idea` → `enhancement`. Mirrors the repo's own Issue Forms labels so a CLI-filed report is categorized identically to a web-filed one. |
| `{slug}` | A short, filesystem-safe slug derived from the title. |
| `{plugin_version from config.yaml}` | The installed planwise plugin version. |
| `{subcommand}` | The `/planwise` subcommand involved, if any. |
| `{user-supplied}` | Free text the user types or confirms; never auto-filled. |
