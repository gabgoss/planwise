---
description: Feedback submission engine — the shared outward-post pipeline for /planwise feedback and every other outward-facing GitHub issue call site
consult-when: Submitting `/planwise feedback` or a GitHub issue — the shared outward-post pipeline (gate chain, duplicate scan, draft-first, posted-draft marking), with the local draft pipelines in the Part-2 sibling and the fallback posture, body spec and privacy contract in the Part-3 sibling
---

# Feedback Submission Engine

**Purpose:** This engine is the ONE place the outward submission pipeline is specified. It
spans three files, split when this file neared the Read-tool token gate. This file, Part 1,
keeps the original filename and holds the gate chain, the duplicate scan, the draft-first
invocation and the posted-draft marking.
[Part 2](feedback-submission-Part-2-LocalDraftPipelines.md) holds the three local pipelines on
the same draft directory: sweeping posted drafts to an archive, reporting each draft's status,
and the model-draft review routes (`--drafts` lists and discards locally, `--post <draftId>`
posts one draft through the gate chain).
[Part 3](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md) holds the fallback posture,
the Auto-Mode deviation, the issue body spec, the privacy contract and the placeholder
reference. It is a shared engine, not a handler — it has no entry point of its own.

**Consumers (delegate to this engine; do not re-specify any part of it locally):**
- `handlers/feedback.md`
- `handlers/upgrade-Part-3-BannerAndConflictResolution.md` Step 4.2
- `handlers/lessons.md` (capture-prompt upstream option)
- `handlers/backlog.md` (create-prompt upstream option)

**Read-only gate-state consumers** — these evaluate and report the Gate Chain without ever
entering the post pipeline. They are consumers on the same terms: they delegate the gate
definitions here and re-specify none of them locally. What each adds on top is its own
reporting or offer text, which this file does not own.
- `handlers/doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md` Stage 16 (feedback capability probe) — reports whether gates 1, 3 and 4
  are met, with a remedy line per unmet gate. It posts nothing, so gates 2 and 5 do not apply.
- `handlers/init.md` Step 9.5 and `handlers/upgrade-Part-3-BannerAndConflictResolution.md` Step 4.5 (GitHub CLI offer) — evaluate
  gates 3 and 4 to decide whether to offer the install, then own the offer itself.

## Table of Contents

- [Gate Chain](#gate-chain)
  - [The Enable Offer (gate 1, absent state)](#the-enable-offer-gate-1-absent-state)
  - [Resolving `gh`](#resolving-gh)
- [Step 4.5 — Duplicate Scan (Non-Fatal)](#step-45--duplicate-scan-non-fatal)
- [Draft-First, Then Post](#draft-first-then-post)
- [Marking a Posted Draft](#marking-a-posted-draft)

Held in [Part 2](feedback-submission-Part-2-LocalDraftPipelines.md):

- [Sweeping Posted Drafts](feedback-submission-Part-2-LocalDraftPipelines.md#sweeping-posted-drafts)
- [Reporting Draft Status](feedback-submission-Part-2-LocalDraftPipelines.md#reporting-draft-status)
- [Reviewing Model Drafts](feedback-submission-Part-2-LocalDraftPipelines.md#reviewing-model-drafts)

Held in [Part 3](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md):

- [On Any Gate Failure or Post Failure](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md#on-any-gate-failure-or-post-failure)
- [Auto Mode — A Deliberate, Documented Deviation](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md#auto-mode--a-deliberate-documented-deviation)
- [Issue Body Spec](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md#issue-body-spec)
- [Privacy Contract — Default-Closed](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md#privacy-contract--default-closed)
- [Placeholder Reference](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md#placeholder-reference)

---

## Gate Chain

ALL gates below MUST pass, in this order, before a post is attempted:

1. **`feedback.enabled: true`** — config key, default `false` (mirrors the upgrade flow's
   opt-in precedent). The gate reads the key with
   `python "{plugin_root}/scripts/feedback_drafts.py" posting-state --config "{planwise_root}/config.yaml"`,
   which prints one word and writes nothing:
   - `enabled` — the gate passes.
   - `disabled` — `config.yaml` sets the key to a value other than `true`. The user made this
     decision, so the pipeline honours it without a question. It stops at the draft and prints
     `Posting is off: config.yaml sets feedback.enabled to a value other than true. The draft was saved and nothing was posted.`
   - `absent` — the `feedback` block or its `enabled` key is missing. The user never saw the
     key, so this is an unasked question, not a decision. See
     [The Enable Offer](#the-enable-offer-gate-1-absent-state).
   - Exit 1 (config missing or unreadable) — the gate is unmet. The pipeline stops at the draft.
   A model draft's **Review and post** option sets the key to `true` when chosen, and says so in
   its option text first (see Reviewing Model Drafts, in [Part 2](feedback-submission-Part-2-LocalDraftPipelines.md#reviewing-model-drafts)).
2. **Interactive session.** In Auto Mode the pipeline is **draft-only, unconditionally** —
   gates 3-5 are skipped and execution proceeds straight to the draft-write step below.
3. **`gh` resolvable** — on PATH, or at a known install location (see
   [Resolving `gh`](#resolving-gh) below). Gate 3 records the resolved `{gh_path}`, and every
   later `gh` call in this engine runs through it.
4. **`{gh_path} auth status` exits 0.** An unauthenticated `gh` otherwise fails at post time with
   no fallback; checking auth before rendering moves that failure into the fallback path
   where it belongs.
5. **Explicit `AskUserQuestion`** — one call, three outcomes. It shows the duplicate-scan
   result (caveat line, then the ranked candidate table if any), then the rendered body
   **verbatim**, then offers: **post as a new issue**, **comment on #{NN}**, or **cancel**.
   The user approves the exact text that will be published, not a summary of it. This is
   the post pipeline's only consent site — the comment outcome rides this same call and MUST
   NOT be implemented as a second prompt. (The sweep pipeline in Part 2 has its own, separate,
   single consent site; the two are never shared or duplicated.) The gate 1 enable offer is a
   setting selection and not a second consent site: it sends nothing and never replaces this
   call. See [The Enable Offer](#the-enable-offer-gate-1-absent-state).

<!-- AUTO-MODE: critical -->

**Quick reference:**

| # | Gate | On Auto Mode |
|---|------|---------------|
| 1 | `feedback.enabled: true` | `disabled` is unaffected. `absent` asks no question and stops at the draft with the Auto Mode message under The Enable Offer. |
| 2 | Interactive session | Draft-only, unconditionally; gates 3-5 are skipped. |
| 3 | `gh` resolvable (PATH, then known install locations) | Only evaluated in an interactive session. |
| 4 | `{gh_path} auth status` exits 0 | Only evaluated in an interactive session. |
| 4.5 | Duplicate scan (step, not gate) | Runs opportunistically; the result is written into the draft. No consent site. |
| 5 | Explicit consent (`AskUserQuestion`) | Auto-deny → draft written **with the possible-duplicates block**, exit 0 (see the Auto Mode deviation in Part 3, not a fail-loud STOP). |

Row 4.5 is a **step**, not a gate — the "ALL gates below MUST pass" rule above governs
gates 1–5 only, and a scan that fails never stops the pipeline.

### The Enable Offer (gate 1, absent state)

A fresh install can have no `feedback.enabled` key at all, so gate 1 would fail on a setting
the user never saw. In the `absent` state, and only then, the pipeline asks once instead of
stopping. The offer belongs to gate 1, so it runs before the draft is posted and after the
user has written the report.

<!-- AUTO-MODE: critical -->
Ask with `AskUserQuestion`, in an interactive session only. Auto Mode skips the question and
takes the keep branch. The question is: `Posting to GitHub is not set up in this project: config.yaml has no feedback.enabled key. Enable posting and continue to the post, or keep only the draft?` The options are:

| Option | What it does |
|---|---|
| **Enable posting** | Option text: `Enable posting (this sets feedback.enabled to true in config.yaml)`. Runs `python "{plugin_root}/scripts/feedback_drafts.py" enable-posting --config "{planwise_root}/config.yaml"` and prints its one line. On exit 0 the pipeline goes on to gate 2. On exit 1 it prints the stderr line, leaves `config.yaml` unchanged and stops at the draft. |
| **Keep the draft only** (pre-selected) | Stops at the draft and prints `Posting stays off. To stop this question, set feedback.enabled: false in config.yaml.` Any other or unparseable answer is this option. |

Three rules bound the offer:

- **It is a selection, not consent to post.** It changes one config key and sends nothing.
  Gate 5 still shows the exact body and asks before anything is published, and enabling
  posting never skips it. This is the same posture as the model-draft **Review and post**
  option under Reviewing Model Drafts (Part 2).
- **It never overrides a decision.** A key set to `false`, or to any value other than `true`,
  is the `disabled` state and raises no question. Writing `feedback.enabled: false` is how a
  user ends the offer for good.
- **It runs once per invocation.** The pipeline does not ask again after a keep answer or a
  failed enable.

In Auto Mode the `absent` state stops at the draft and prints
`Posting is not set up: config.yaml has no feedback.enabled key. The draft was saved and nothing was posted.`

### Resolving `gh`

A shell started by a running session inherits the PATH the session had at launch. A `gh`
installed after that point works by full path and stays invisible to a bare `gh` for the rest
of the session. A PATH-only check therefore reports "not installed" for a working install.
Gate 3 resolves `gh` in this order and stops at the first success:

1. **PATH.** Run `gh --version`. On exit 0, `{gh_path}` is the bare word `gh`.
2. **Known install locations.** Test each candidate for the detected platform, in the order
   listed. A candidate counts only if the file exists and `"{candidate}" --version` exits 0.
   The first one that counts is `{gh_path}`.

| Platform | Candidates, in order |
|---|---|
| Windows | `C:\Program Files\GitHub CLI\gh.exe`, `%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe`, `C:\Program Files (x86)\GitHub CLI\gh.exe` |
| macOS | `/opt/homebrew/bin/gh`, `/usr/local/bin/gh` |
| Linux | `/usr/bin/gh`, `/usr/local/bin/gh`, `/home/linuxbrew/.linuxbrew/bin/gh`, `~/.local/bin/gh` |

If every step fails, gate 3 is unmet and `{gh_path}` is undefined. A caller that needs only
the yes/no answer reads "undefined" as "not resolvable".

- **Report the source.** A caller that prints the result names where `gh` was found. A hit
  from step 2 reads `found at {gh_path}, not on this session's PATH`. That wording tells the
  user a new terminal will resolve it and that nothing is broken.
- **Quote the path.** Every candidate contains a space or may do so. Write `"{gh_path}"` in a
  command line, and use the quoted form in both Git Bash and PowerShell (in PowerShell, call
  it with the `&` operator).
- **Change nothing.** Resolution never edits PATH, a profile, or a settings file. It also
  never installs anything. The install offers in `handlers/init.md` and
  `handlers/upgrade-Part-3-BannerAndConflictResolution.md` own the install.
- **Resolve once per run.** The result holds for the whole pipeline. Do not re-probe between
  gates 3, 4 and the posting step.

---

## Step 4.5 — Duplicate Scan (Non-Fatal)

Between gate 4 and gate 5 the engine searches `{feedback.repo}` for issues that may already cover
this report, and carries the result into gate 5's prompt. It is a **step, not a gate**: it never
joins the "ALL gates below MUST pass" rule, and every outcome below proceeds to gate 5 with a caveat.

### Search keys

Keys come from the rendered body (excluding `### Environment`) and the title, in this precedence:

| Tier | Source | Score |
|---|---|---|
| A | A cited file name whose extension **ends** the token — one of `md` `py` `yml` `yaml` `json` `js` `ts` `sh` `ps1` `toml` `txt` — optionally followed by a line-or-range suffix (`:12`, `:12-30`) that is discarded. Normalize to the basename, then strip any leading `-` `.` `/`. Anchoring the extension at the end of the token is what stops a compiled-artifact name from being truncated mid-token into a file that does not exist, burning a query slot on a term nothing can match. | 4 |
| B1 | A backticked span (≤ 40 chars, ≤ 4 words) that contains `.` `_` `-` or `/`, **or** that spans 2–4 words | 3 |
| B2 | A single-word backticked span (≤ 40 chars) carrying none of those separators | 2 |
| C | The first 8 words of a quoted or fenced line carrying an error signature — `Error`, `Exception`, `Traceback`, `FAILED`, `fatal:`, `exit code`, `not found`, `cannot`, `denied`, `refused`, every one matched **case-insensitively** so an upper-cased line in a pasted log still qualifies. At most one Tier-C key. | 3 |
| D | A title word ≥ 4 chars after stopword removal | 1 |

A bare section, step, gate, or line number is never a key on its own — it is appended to the
nearest preceding Tier-A key in the same sentence. If that sentence carries no Tier-A key the
number is **dropped**: it never attaches to a Tier-B or Tier-C key, and never becomes a key by itself.

Every key MUST match `^[A-Za-z0-9._/:+#-]{3,60}$`, applied **per whitespace-separated token** — a
multi-word key travels as one double-quoted `--search` argument, so the space between its tokens is
not a shell metacharacter and does not disqualify it. A key must not begin `/` `~` `\` or a drive
letter, must contain no `@`, and must not be a bare number or a lone stopword. A key that fails is
dropped, never escaped or repaired — it degrades the scan to fewer candidates, never to a bad command.

**Closed stopword list** — used by Tier D and by the lone-stopword test, with no additions. The last
five are domain words that appear in nearly every title in this tracker and carry no signal:

```
a an and are as at be but by can cannot did do does for from had has have how i if in into is
it its not of on or should so than that the their then there these they this to too was were
what when where which while who why will with would you your bug issue error problem planwise
```

De-duplicate case-insensitively **within the identifier pool (Tiers A–C)**, keeping the
highest-scoring form of each duplicate; sort by score, then by first appearance in the body; take
the top **4**. Then add exactly one supplementary query built from the 3 strongest title terms —
formed **independently** of the identifier pool, so it may restate a term already sent as an
identifier key; it is a distinct query (its terms are ANDed) and takes its own slot. **At most 5.**

**When the body cites no identifier at all** (a pure-prose report yields no Tier A–C key) the scan
still runs: the title query becomes the primary key, one query per individual title term is added
(up to 3), and if all return nothing the engine lists the 20 most recent issues unkeyed and presents
the newest 5 under an explicit weak-signal caveat. The scan never silently does nothing.

### Invocation

One search, repeated once per key:

```
"{gh_path}" issue list -R {feedback.repo} --state all --limit 20 --search "{query} in:title,body" \
  --json number,title,state,createdAt,url
```

| Element | Rule |
|---|---|
| `--state all` | **Mandatory** — this engine's default would otherwise inject an open-only qualifier. A defect already fixed but not yet released is exactly where a duplicate is most likely and least useful, and searching closed issues costs nothing. |
| `--limit 20` | Per query. The union across all queries is what gets ranked; only the top few are ever shown. |
| `--json` | Exactly these five fields. Do not add fields without first confirming they exist on the installed `gh` — an unknown field name makes the whole call exit non-zero, converting a working scan into a degradation row. |
| `{query}` | One search key, already safety-filtered, always double-quoted. |
| `in:title,body` | Keeps the match off labels and comment threads, where a shared word produces noise. |
| Permitted surface | Read-only. `"{gh_path}" issue view {NN} -R {feedback.repo} --json number,title,state,url` is the only other invocation this step may make, and only to validate a user-named issue number at gate 5. No other `gh` subcommand is permitted here. |

When the body cites no identifier and every title query returns nothing, one unkeyed recency
listing runs in their place:

```
"{gh_path}" issue list -R {feedback.repo} --state all --limit 20 \
  --json number,title,state,createdAt,url
```

**Order and budget.** Queries run in descending key score, identifier keys before the title query,
so a budget that cuts the scan short has already run the strongest keys. 10 seconds per query — on
exceeding it, abandon that key and continue to the next; 30 seconds for the whole scan — on
exceeding it, issue no further queries and rank whatever merged. `gh` has no timeout flag and the
engine must not wrap the call in `timeout` or `Start-Job` (the plugin runs under both Git Bash and
PowerShell; neither wrapper exists in both), so the budget is agent-enforced policy, not a flag.

**Merge.** Union the result rows on `number`; an issue returned by more than one query appears
**once**, recording the keys that matched it (`matched_keys`) and the highest score among them
(`best_key_score`). If a returned issue's title is byte-identical to the draft title and it was
created within the last 10 minutes, it is this same draft posted by an interrupted earlier run: drop
it and report above the table `This draft appears to have already been posted as #{NN} — check
before posting again.`

### Presentation

Score each merged candidate:

```
score = sum(score of every key in matched_keys)
      + 2 if the candidate's own title contains a Tier-A basename the draft also cites
      + 2 if it was created within the last 14 days
      + 1 if it was created within the last 90 days (not cumulative with the 14-day bonus)
```

Keep the candidates scoring **≥ 3** and show at most the top **5**:

| # | Issue | State | Age | Title | Matched on |
|---|-------|-------|-----|-------|------------|
| 1 | #{NN} | OPEN | 3d | {title} (truncated to 60 chars, trailing `…`) | `{query}` |

Age is `floor((now − createdAt) / 1 day)`, rendered `today` / `{n}d` / `{n}mo` / `{n}y{n}mo`. Closed
issues are never penalized — a defect fixed but unreleased is a duplicate the reporter most wants to
know about; state breaks ties only: higher `best_key_score` first, then `OPEN` before `CLOSED`, then
the more recent. If more than 5 clear the threshold, append one line:
`… and {N} further lower-ranked matches (not shown).`

**Distinctive keys outweigh generic ones.** Nothing in the score discounts a key for being common
across the tracker, so several matches on broad vocabulary — a widely-used command span, or title
wording — can out-total one match on a genuinely distinctive identifier. Two rules close that gap:
before the top-5 cut, **reserve a slot for each of the two highest-scoring candidates whose
`best_key_score` is 4** (matched by a cited file name), so a candidate matched by a distinctive
identifier is never pushed off the presented list by candidates matched only on generic vocabulary,
whatever their totals; and a candidate whose only matches are title terms (`best_key_score` 1) never
outranks one whose `best_key_score` is ≥ 3.

### When the scan cannot complete

**The scan never blocks.** It is a step, not a gate — the "ALL gates below MUST pass" rule governs
gates 1–5 only. Every failure mode below proceeds to gate 5 carrying a caveat; none halts, none
errors out, none is retried more than the budget allows.

Two classes, never collapsed into one message:

| Class | When | Caveat must | Example |
|---|---|---|---|
| **UNKNOWN** | The scan did not complete — no repo configured, auth rejected, rate limited, repo unreachable, `gh` unavailable, any other non-zero exit, a 10 s per-query or 30 s whole-scan timeout with nothing returned, or no usable search key | say "could not"/"unknown"; never read as a finding | `Duplicate scan could not run — the GitHub API rate limit was reached. Whether this duplicates an existing issue is unknown.` |
| **CLEAR** | The scan completed — zero matches, or matches all below the relevance threshold | state the positive finding; never read as a failure | `Duplicate scan: no matching issues found in {feedback.repo}, open or closed, across {n} searches.` |

"No duplicates found" and "we could not check" license opposite decisions. A user who reads the
second as the first files the duplicate this step exists to prevent. The branch caveats, verbatim:

| Branch | `{scan_caveat}` |
|---|---|
| Some queries returned, some timed out | `Duplicate scan was incomplete — {k} of {n} searches returned. Candidates below may be missing entries.` — shown **with** whatever candidates merged, never instead of them |
| Matches found, all below the threshold — a CLEAR result, not a zero-result one | `Duplicate scan: no close matches in {feedback.repo}, open or closed ({N} weak matches suppressed).` |
| No identifier cited, so only title wording could be searched — a **weak** clear | `Duplicate scan: nothing matched, but the draft cites no file, command, or error string — only title wording was searched, which is a weak signal. The 5 most recent issues are listed for comparison.` |

Whatever the branch, the caveat is one line — `{scan_caveat}` — the first line of the scan block at
gate 5 and of the possible-duplicates block in a draft. One string, one source of truth, two render
sites.

---

## Draft-First, Then Post

Draft first, always. Every body this engine publishes is written to a file before it is
shown, and posted *from that file*. Before that first write, create the parent directory —
`{planwise_root}/{feedback_dir}` — if it does not already exist; both the issue draft path and
the comment draft path resolve under it:

```
"{gh_path}" issue create -R {feedback.repo} --title "{title}" --body-file "{draft_path}" --label {label}
```

- `{feedback.repo}` resolves to the literal `gabgoss/planwise` by default and is **NEVER**
  derived from the consumer's git remote — that would file planwise issues in the
  consumer's own project repo.
- `--title` carries the title; the body file contains **no** `Title:` line.
- `{label}` mirrors the label the repo's own Issue Forms apply for the same kind
  (`.github/ISSUE_TEMPLATE/bug_report.yml` → `bug`; `lesson_or_idea.yml` → `enhancement`)
  — see the `{kind}` → `{label}` mapping in Part 3's Placeholder Reference. A CLI-created issue never goes through
  the Issue Forms chooser, so without this flag the issue posts with no label at all,
  silently losing the categorization a web-filed report gets for free.
- Issue draft path: `{planwise_root}/{feedback_dir}/{YYYY-MM-DD}-{kind}-{slug}.md`.
- Comment draft path: `{planwise_root}/{feedback_dir}/{YYYY-MM-DD}-comment-{NN}-{slug}.md`.
- Draft-first buys three things: approved text and posted text are byte-identical — on the
  comment path, the posted body is the approved body plus the single lead-in line the
  consent prompt states in advance; a failed post leaves a recoverable artifact; the
  fallback path is not a separate code path — it is "stop after step 1."

**When gate 5's outcome is "comment on #{NN}"**, the comment body is written to
`{comment_draft_path}` first — before it is shown and before anything is posted — then
printed verbatim (its absolute path, then its contents; a print, **not** a prompt), then
posted from that file:

```
"{gh_path}" issue comment -R {feedback.repo} {NN} --body-file "{comment_draft_path}"
```

No `--label` — comments carry none. Both drafts stay on disk afterwards, on success and on
failure alike.

**Resolving `{NN}` — no second prompt.** The target is read out of the answer gate 5 has
already returned: the first `#[0-9]+` token in it if there is one, otherwise the rank-1
candidate that the option's own label named. If neither is available, treat the answer as
cancel and print `No issue number supplied — nothing was posted.` Validate the resolved
target read-only with `"{gh_path}" issue view {NN} -R {feedback.repo} --json number,title,state,url`;
a non-zero exit or an empty result posts nothing and prints
`Could not resolve issue #{NN} in {feedback.repo} — nothing was posted.` No further question
is asked at any step — this post pipeline has exactly one consent site.

---

## Marking a Posted Draft

A draft that has been posted is marked posted. The mark is a **sidecar file** beside the
draft — `{posted_marker_path}`, the draft's own path with `.posted` appended — and never a
change to the draft itself:

```
posted: {posted_date}
url: {post_url}
route: issue
```

`route:` is the literal `issue` for a draft posted with `gh issue create` and `comment` for
one posted with `gh issue comment`. `{post_url}` is the URL `gh` prints on the successful
post — the issue's URL on the issue path, the comment's own anchor URL on the comment path,
which carries its parent issue's number. Date plus URL is the whole record, and it is enough
to identify the tracker item later without a second lookup and without asking the consumer
anything.

**The draft file itself is never touched**, and that is the entire point of the sidecar. The
two alternative shapes both lose on exactly this:

- **Frontmatter — or any other in-body marker — loses.** `--body-file` sends the *whole
  file*, so a mark written inside the draft gets published verbatim the next time that draft
  is posted. That breaks "approved text and posted text are byte-identical" on a re-post,
  silently, in the one case nobody re-reads. This engine's existing in-file annotation makes
  the point from the other side: the scan-annotation block is local, and the remedy is to
  **truncate it away** before any `--body-file` post. A mark that has to survive the post
  cannot live in a place whose only safe disposition is deletion.
- **A filename change loses.** It does keep the body byte-identical, but it moves the file
  out from under the absolute path the pipeline has already printed to the consumer, it gives
  `{draft_path}` and `{comment_draft_path}` a second form every later reader has to know, and
  a filename cannot hold a URL. Under-recording is the one thing that cannot be repaired
  afterwards — the URL is the only handle a post ever hands back.

The sidecar takes a non-`.md` extension so a marker is never mistaken for a draft, and it
sits outside the draft body entirely, so the scan-annotation truncation never reaches it.

**Where in the flow.** Strictly after a post returns success, at both post sites: after
`gh issue create` on the issue path, and after `gh issue comment` on the comment path. Both
drafts stay on disk exactly as before — the marker is an addition beside one, never a
replacement, a move, or an edit of it. A marker is written on each successful post, so a
draft posted more than once carries the most recent post.

**No new consent site.** No question is asked here. Writing the marker is post-success
bookkeeping into a file the consumer already owns, in the directory this engine already
writes drafts to. It is not an outward action, so it introduces no `<!-- AUTO-MODE: -->`
marker and this post pipeline still has exactly one consent site. In Auto Mode nothing is
ever posted, so nothing is ever marked.

**Marking is never a failure path — in either direction:**

1. A post that failed leaves the draft **unmarked**. No marker is written for a post that did
   not succeed, so an unmarked draft means precisely "not known to have been posted." The
   fallback posture in Part 3 is unchanged by any of this.
2. A marker that cannot be written does **not** fail the flow. The post has already succeeded
   and its URL is already the reported outcome. Print one line saying the draft could not be
   marked, then continue, exit 0 — never retry in a loop, never block, and never let a
   bookkeeping write turn a successful post into a failure.

**Nothing sweeps this directory automatically.** Feedback drafts, and the markers beside them,
are the consumer's own prose and their own record of it. No automatic step in this tool moves,
renames, copies, or deletes a draft or a marker — not after a successful post, not at upgrade
time, not as maintenance. The directory is deliberately not a machine-managed recovery
surface: it carries no recovery-artifact disposition class, no upgrade-banner count, and no
cleanup offer, precisely so that no automatic cleanup step can ever remove something a person
wrote. The one disposition that exists is user-invoked and never destructive:
`/planwise feedback --sweep` lists the drafts already recorded as posted and, only on an
explicit answer naming them, moves each one and its marker into an archive subdirectory. It
deletes nothing, it never touches an unmarked draft, and on a non-interactive session it lists
and stops. Removing a draft remains the consumer's own action, taken when they choose to take
it.
This no-automatic-removal rule protects hand-written drafts, with one exception:
`scripts/feedback_drafts.py` deletes a model draft that is over the queue cap or refused at
admission, and only when its frontmatter re-reads `drafted_by: model`.

**Why moving does not contradict the rejection of a filename change above.** That rejection
was about a rename **at post time** — silently, as a side effect of posting, moving a file out
from under the absolute path already printed to the consumer. `/planwise feedback --sweep`
moves a file only when the consumer explicitly asked, after being shown the file's current
path, and it prints the new one. The two are not the same operation.

---

*Continued in [feedback-submission-Part-2-LocalDraftPipelines.md](feedback-submission-Part-2-LocalDraftPipelines.md) (the sweep, status and model-draft pipelines) and [feedback-submission-Part-3-FailureBodySpecAndPrivacy.md](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md) (fallback posture, Auto Mode deviation, issue body spec, privacy contract, placeholders).*
