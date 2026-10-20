---
description: Feedback submission engine, Part 3 — the fallback posture on any gate or post failure, the Auto Mode deviation, the issue body spec, the privacy contract and the placeholder reference for all three parts. Split out of feedback-submission.md when that file neared the Read-tool token gate.
---

# Feedback Submission Engine, Part 3 — Fallback, Body Spec and Privacy

**Purpose:** The fallback posture, the Auto-Mode deviation, the issue body spec, the privacy
contract and the placeholder reference of the feedback submission engine, split out of
[feedback-submission.md](feedback-submission.md) when that file neared the Read-tool token
gate. Part 1 keeps the original filename and holds the gate chain, the duplicate scan, the
draft-first invocation and the posted-draft marking.
[Part 2](feedback-submission-Part-2-LocalDraftPipelines.md) holds the three local pipelines:
sweep, status and the model-draft review routes. The Placeholder Reference below covers all
three parts. Consumers delegate here on the same terms as Part 1, and re-specify nothing locally.

## Table of Contents

- [On Any Gate Failure or Post Failure](#on-any-gate-failure-or-post-failure)
- [Auto Mode — A Deliberate, Documented Deviation](#auto-mode--a-deliberate-documented-deviation)
- [Issue Body Spec](#issue-body-spec)
- [Privacy Contract — Default-Closed](#privacy-contract--default-closed)
- [Placeholder Reference](#placeholder-reference)

---

## On Any Gate Failure or Post Failure

1. Keep each draft file on disk — do not delete any of them.
2. Print each draft's absolute path.
3. Print `https://github.com/gabgoss/planwise/issues` so the consumer can paste the draft
   into the web UI by hand.
4. Never block, never error out — the parent flow is unaffected. This covers a duplicate
   scan that failed as well as a post that failed.

---

## Auto Mode — A Deliberate, Documented Deviation

The generic Auto Mode policy says a `critical` site fails loud and STOPs on auto-deny.
**The gate 5 consent site (Part 1, [Gate Chain](feedback-submission.md#gate-chain)) deviates on the last step:** on auto-deny the engine writes the draft and
continues, exit 0.

**Rationale:** the policy's fail-loud behavior exists for questions whose absence makes
execution *incorrect*. Here, the declined branch has a complete, correct, documented
outcome — a draft on disk — and failing loud would let an unattended feedback attempt
break an otherwise-successful parent flow. The site still carries
`<!-- AUTO-MODE: critical -->` so it passes the policy's compliance grep.

**The draft carries the scan result.** In Auto Mode the duplicate scan still runs — it is a
step, not a gate, so the gate 3–5 skip does not govern it, and if `gh` is missing or
unauthenticated it simply lands on its own UNKNOWN caveat. Its result is appended to the
draft file, after `### Environment`:

```markdown
<!-- planwise:scan-annotation — local annotation, not part of the issue body. Strip before posting. -->

### Possible duplicates

{scan_caveat}

| # | Issue | State | Age | Title | Matched on |
|---|-------|-------|-----|-------|------------|
| 1 | #{NN} | OPEN | 3d | {title} | `{query}` |

Confirm none of the above already covers this report before filing it.
```

The block is written on every Auto Mode run, including when the scan could not run — an
absent block is indistinguishable from an unimplemented feature, while a present one
carrying the "unknown" caveat is a fact the reviewer can act on.

**Before rendering a draft for gate 5, and before any `--body-file` post, truncate the
draft at the `<!-- planwise:scan-annotation` marker.** The annotation is local; truncating
the file (rather than posting a filtered copy) keeps shown bytes, on-disk bytes, and posted
bytes identical.

This adds **no** consent site: no question is asked, so nothing here is classified
critical or convenience, and no new `<!-- AUTO-MODE: -->` marker is introduced.

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
- OS / shell: {OS/shell, auto-detected}
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
- OS / shell: {OS/shell, auto-detected}
```

**Comment variant.** When gate 5's outcome is "comment on #{NN}", the body posted is the
approved body with one lead-in line prepended:

```markdown
Filed with `/planwise feedback` as a comment rather than a new issue — this looked like the same subject as this thread. **{title}**

{the approved body, verbatim, including its `### Environment` block}
```

The lead-in is the **only** difference. Nothing is dropped, reworded, or reordered, and the
lead-in's exact wording appears in the consent prompt's option description, so every byte
that will be published was shown before consent. The comment carries no draft path — that
is a consumer-local absolute path, which the Privacy Contract forbids attaching.

---

## Privacy Contract — Default-Closed

`plugin_version` and `OS / shell` are auto-filled; everything else is user-typed or user-confirmed.

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

**The duplicate scan queries the tracker before consent.** Step 4.5 (Part 1) sends search keys —
never the body — to `{feedback.repo}` as read-only query parameters, before gate 5 is
reached. Keys are restricted by construction to `^[A-Za-z0-9._/:+#-]{3,60}$` and a key is
dropped, never repaired, if it begins `/` `~` `\` or a drive letter, contains `@`, or is a
bare number. So a consumer-local absolute path, an email, and an `@handle` cannot become a
search key. A query parameter is transient; nothing is published by the scan.

---

## Placeholder Reference

Every placeholder used in the three parts of this engine, for the four call sites that render this engine's templates:

| Placeholder | Resolves to |
|---|---|
| `{feedback.repo}` | `gabgoss/planwise` (literal default; never the consumer's own remote). A configured value that is blank, non-string, or not shaped like `owner/name` also falls back to this default — the loader rejects it before it ever reaches a `gh` invocation. |
| `{title}` | The issue title, supplied by the caller. |
| `{draft_path}` | `{planwise_root}/{feedback_dir}/{YYYY-MM-DD}-{kind}-{slug}.md`. |
| `{planwise_root}` | The consumer's configured planwise root directory. |
| `{feedback_dir}` | The consumer's configured directory for feedback drafts, resolved under `{planwise_root}`; defaults to `Feedback`. |
| `{YYYY-MM-DD}` | The date the draft is written. |
| `{kind}` | `bug`, `lesson`, or `idea` — selects the body variant. |
| `{label}` | The single `gh issue create --label` value for `{kind}`: `bug` → `bug`; `lesson` or `idea` → `enhancement`. Mirrors the repo's own Issue Forms labels so a CLI-filed report is categorized identically to a web-filed one. |
| `{slug}` | A short, filesystem-safe slug derived from the title. |
| `{plugin_version from config.yaml}` | The installed planwise plugin version. |
| `{subcommand}` | The `/planwise` subcommand involved, if any. |
| `{OS/shell, auto-detected}` | The OS and shell the assistant already observes from its own runtime environment. |
| `{user-supplied}` | Free text the user types or confirms; never auto-filled. |
| `{NN}` | The target issue number for a comment outcome — digits only, no `#`. Rendered `#{NN}` in prose. |
| `{comment_draft_path}` | `{planwise_root}/{feedback_dir}/{YYYY-MM-DD}-comment-{NN}-{slug}.md`. |
| `{posted_marker_path}` | The posted-marker sidecar: the draft's own path with `.posted` appended — `{draft_path}.posted` on the issue path, `{comment_draft_path}.posted` on the comment path. |
| `{posted_date}` | The date the post succeeded. Distinct from the `{YYYY-MM-DD}` in the draft's filename, which is the date the draft was written. |
| `{post_url}` | The URL `gh` prints on a successful post — the issue's URL after `gh issue create`, the comment's own anchor URL (which carries its parent issue's number) after `gh issue comment`. |
| `{query}` | One duplicate-scan search key, already restricted to `^[A-Za-z0-9._/:+#-]{3,60}$` and always double-quoted on the command line. |
| `{scan_caveat}` | The single-line duplicate-scan result string — the first line of the scan block at gate 5 and of the possible-duplicates block in a draft. |
| `{archive_dir}` | `{planwise_root}/{feedback_dir}/Archive` — the `--sweep` destination directory; created on first use, only after consent is given. |
| `{status_caveat}` | The single-line `--status` degradation-result string, printed once at the head of the `--status` output — mirrors `{scan_caveat}` in shape. |
| `{draft_id}` | The `draft_id` frontmatter value of one model draft. |
| `{model draft}` | One model-draft file, as Reviewing Model Drafts → Candidacy (Part 2) defines it. |
| `{model_draft_name}` | The model-draft name pattern, `{YYYY-MM-DD}-draft-{kind}-{slug}.md`. |
| `{reason}` | Why a `--post` id matched no queued draft: `expired`, `discarded`, `promoted` or `unknown`. |
| `{plugin_root}` | The installed planwise plugin's root directory. |
| `{n}`, `{k}`, `{N}`, `{m}` | Inline integer counts: `{n}` searches attempted (and the quantity in a rendered age, or of `--sweep` candidates / `--status` drafts / model drafts), `{k}` of them that returned, `{N}` further or suppressed matches (or un-queried issues) not shown, `{m}` the total issues queried by `--status`. |

Two brace forms in this engine are deliberately not placeholders and need no row: `{3,60}` in the search-key
pattern is a regular-expression quantifier, and a self-describing slot inside a template fence
(`{the approved body, verbatim, …}`) names its own contents.

---

*Cross-reference: [feedback-submission.md](feedback-submission.md) (Part 1 — gate chain, duplicate scan, draft-first, posted-draft marking), [feedback-submission-Part-2-LocalDraftPipelines.md](feedback-submission-Part-2-LocalDraftPipelines.md) (Part 2 — sweep, status and model-draft pipelines).*
