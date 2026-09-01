---
description: Feedback submission engine — the shared outward-post pipeline for /planwise feedback and every other outward-facing GitHub issue call site
---

# Feedback Submission Engine

**Purpose:** This file is the ONE place the outward submission pipeline is specified: the
gate chain, the duplicate scan, the draft-first invocation, the posted-draft marking, the
fallback posture, the Auto-Mode deviation, the issue body spec, and the privacy contract. It
also specifies the two local, non-outward commands that operate on the same draft directory:
sweeping posted drafts to an archive, and reporting each draft's status. It is a shared
engine, not a handler — it has no entry point of its own.

**Consumers (delegate here; do not re-specify any of the below locally):**
- `handlers/feedback.md`
- `handlers/upgrade.md` Step 4.2
- `handlers/lessons.md` (capture-prompt upstream option)
- `handlers/backlog.md` (create-prompt upstream option)

## Table of Contents

- [Gate Chain](#gate-chain)
- [Step 4.5 — Duplicate Scan (Non-Fatal)](#step-45--duplicate-scan-non-fatal)
- [Draft-First, Then Post](#draft-first-then-post)
- [Marking a Posted Draft](#marking-a-posted-draft)
- [Sweeping Posted Drafts](#sweeping-posted-drafts)
- [Reporting Draft Status](#reporting-draft-status)
- [On Any Gate Failure or Post Failure](#on-any-gate-failure-or-post-failure)
- [Auto Mode — A Deliberate, Documented Deviation](#auto-mode--a-deliberate-documented-deviation)
- [Issue Body Spec](#issue-body-spec)
- [Privacy Contract — Default-Closed](#privacy-contract--default-closed)
- [Placeholder Reference](#placeholder-reference)

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
5. **Explicit `AskUserQuestion`** — one call, three outcomes. It shows the duplicate-scan
   result (caveat line, then the ranked candidate table if any), then the rendered body
   **verbatim**, then offers: **post as a new issue**, **comment on #{NN}**, or **cancel**.
   The user approves the exact text that will be published, not a summary of it. This is
   the post pipeline's only consent site — the comment outcome rides this same call and MUST
   NOT be implemented as a second prompt. (The sweep pipeline below has its own, separate,
   single consent site; the two are never shared or duplicated.)

<!-- AUTO-MODE: critical -->

**Quick reference:**

| # | Gate | On Auto Mode |
|---|------|---------------|
| 1 | `feedback.enabled: true` | Unaffected — config-based, no session distinction. |
| 2 | Interactive session | Draft-only, unconditionally; gates 3-5 are skipped. |
| 3 | `gh` on PATH | Only evaluated in an interactive session. |
| 4 | `gh auth status` exits 0 | Only evaluated in an interactive session. |
| 4.5 | Duplicate scan (step, not gate) | Runs opportunistically; the result is written into the draft. No consent site. |
| 5 | Explicit consent (`AskUserQuestion`) | Auto-deny → draft written **with the possible-duplicates block**, exit 0 (see the Auto Mode deviation below, not a fail-loud STOP). |

Row 4.5 is a **step**, not a gate — the "ALL gates below MUST pass" rule above governs
gates 1–5 only, and a scan that fails never stops the pipeline.

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
gh issue list -R {feedback.repo} --state all --limit 20 --search "{query} in:title,body" \
  --json number,title,state,createdAt,url
```

| Element | Rule |
|---|---|
| `--state all` | **Mandatory** — this engine's default would otherwise inject an open-only qualifier. A defect already fixed but not yet released is exactly where a duplicate is most likely and least useful, and searching closed issues costs nothing. |
| `--limit 20` | Per query. The union across all queries is what gets ranked; only the top few are ever shown. |
| `--json` | Exactly these five fields. Do not add fields without first confirming they exist on the installed `gh` — an unknown field name makes the whole call exit non-zero, converting a working scan into a degradation row. |
| `{query}` | One search key, already safety-filtered, always double-quoted. |
| `in:title,body` | Keeps the match off labels and comment threads, where a shared word produces noise. |
| Permitted surface | Read-only. `gh issue view {NN} -R {feedback.repo} --json number,title,state,url` is the only other invocation this step may make, and only to validate a user-named issue number at gate 5. No other `gh` subcommand is permitted here. |

When the body cites no identifier and every title query returns nothing, one unkeyed recency
listing runs in their place:

```
gh issue list -R {feedback.repo} --state all --limit 20 \
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
gh issue comment -R {feedback.repo} {NN} --body-file "{comment_draft_path}"
```

No `--label` — comments carry none. Both drafts stay on disk afterwards, on success and on
failure alike.

**Resolving `{NN}` — no second prompt.** The target is read out of the answer gate 5 has
already returned: the first `#[0-9]+` token in it if there is one, otherwise the rank-1
candidate that the option's own label named. If neither is available, treat the answer as
cancel and print `No issue number supplied — nothing was posted.` Validate the resolved
target read-only with `gh issue view {NN} -R {feedback.repo} --json number,title,state,url`;
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
   fallback posture below is unchanged by any of this.
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

**Why moving does not contradict the rejection of a filename change above.** That rejection
was about a rename **at post time** — silently, as a side effect of posting, moving a file out
from under the absolute path already printed to the consumer. `/planwise feedback --sweep`
moves a file only when the consumer explicitly asked, after being shown the file's current
path, and it prints the new one. The two are not the same operation.

---

## Sweeping Posted Drafts

`/planwise feedback --sweep` is a second, separate pipeline in this file — a local file-move
operation, not an outward post. It shares the draft directory and the posted-marker contract
above with the post pipeline, and nothing else: it makes no network call, and it has its own
single consent site, distinct from the post pipeline's.

### Candidacy

A sweep candidate is a `*.md` file directly in `{planwise_root}/{feedback_dir}`
(non-recursive) that has a sibling posted-marker sidecar — the draft's own path with
`.posted` appended, exactly as described above — and both files must exist. Nothing else is
ever a candidate. **Age is never a candidacy criterion** and there is no age flag: an old
*unposted* draft is exactly what an age rule would catch first, and it is exactly the file
this command must never touch. Non-recursive walking is load-bearing, not incidental — it is
what stops a later `--sweep` run from re-sweeping the archive it just created.

### Action

Sweeping **archives; it never deletes.** A candidate's draft and its `.posted` sidecar move
together, as an inseparable pair, into `{archive_dir}`. It never copies.

- The pair moves **together or not at all**. If a move succeeds for one file and fails for
  the other, the succeeded half is moved back and the pair is reported as skipped.
- If a candidate's filename already exists in `{archive_dir}`, that candidate is **skipped,
  left in place, and reported.** Nothing already in `{archive_dir}` is ever overwritten.
- A draft with no sidecar is not a candidate. A sidecar with no draft is an orphan: reported
  and left in place, never moved and never removed.
- `{archive_dir}` is created on first use only, after consent is given. A run that is
  cancelled, or that finds no candidates, creates no directory.
- On success, each moved pair's new absolute path is printed, so the consumer holds a
  current path for every file that moved.

**No `Delete` option exists, in the prompt or as a flag.** A consumer who wants the bytes
gone deletes `{archive_dir}` themselves — that is genuinely their own action and needs no
tool support.

### Dry-run default

`--sweep` always produces the candidate listing first, before any consent call and before
any file moves. There is no `--dry-run` flag, because the listing is not an opt-in mode: it
is the only thing that happens unless consent is explicitly given.

Per candidate, the listing prints the draft's absolute path, its `posted:` date, `url:`, and
`route:`; then one summary line: `{n} draft(s) already posted are eligible to archive.` With
no candidates: `No posted drafts to archive.`, exit 0 — no prompt is raised.

### Interaction Matrix

One consent site, one `AskUserQuestion` call, raised only when the listing above found at
least one candidate. The prompt shows the listing, states `{archive_dir}` by absolute path,
and names the exact count in the option label.

<!-- AUTO-MODE: critical -->

| # | Branch | Offered as | What it does | Default | Files touched |
|---|---|---|---|---|---|
| 1 | Listing | not an option — runs unconditionally, before the prompt | Prints every candidate's absolute path, posted date, issue URL and route; then the count line | **Yes — always runs, and is all that runs unless branch 2 is explicitly chosen** | none |
| 2 | Archive | `Archive {n} posted draft(s) to {archive_dir}` | Moves each draft + its sidecar into `{archive_dir}`; prints each new absolute path; skips and reports any collision or orphan | No | the `{n}` listed pairs only |
| 3 | Cancel | `Cancel — leave all {n} drafts where they are` | Nothing. Prints `Nothing was moved.` | **Yes — pre-selected** | none |
| 4 | Non-answer / non-interactive — Auto Mode, auto-deny, an unanswered or interrupted prompt, or any state in which `AskUserQuestion` cannot return an answer | not offered; this branch is taken without a question | The listing stands as the complete output. Prints `Non-interactive session — {n} posted draft(s) listed above were not moved. Re-run /planwise feedback --sweep interactively to archive them.` Exit 0. | **Yes — this is the branch taken** | none |
| 5 | Any other answer, an unparseable answer, or an error raising the prompt | — | Treated as branch 3 (Cancel) | — | none |

Branch 4 carries `<!-- AUTO-MODE: critical -->`, the same deviation shape as the post
pipeline's Auto-Mode site below, for the same reason: the declined branch has a complete,
correct outcome — the listing, already printed — so failing loud on auto-deny would break an
otherwise-successful unattended run for no gain. Sweep's auto-deny writes nothing at all,
which is a smaller footprint than the post pipeline's own auto-deny (which still writes a
draft file).

Every branch but 2 touches no file — branch 2 is reachable only through an explicit answer to
a prompt that names the count and the destination, below a listing that names every affected
file by absolute path. **Not gated on `feedback.enabled`.** `--sweep` makes no network call
and touches only local files the consumer already owns; `feedback.enabled` is the consumer's
opt-in for outward posting to a third-party repo, which a local file move is not. (`--status`
below **is** gated on it, because it does call the tracker. The asymmetry is deliberate.)

### Never Does

1. **Never removes or moves an unmarked draft.** An unmarked draft is not a candidate at
   all — no answer to any prompt makes one eligible.
2. **Never runs implicitly as part of any other subcommand** — only an explicit
   `/planwise feedback --sweep` invokes it.
3. **Never invoked by `init`, `upgrade`, `doctor`, or the post pipeline** — not at init
   scaffolding, not at version change, not as a doctor stage, not after a successful post.
4. **Never deletes.** No delete branch, no delete flag, no force flag. Archiving is the only
   disposition, and `{archive_dir}` is never swept, pruned, or emptied by this tool.
5. **Never separates a draft from its marker.** The pair moves together or neither moves.
6. **Never overwrites anything in `{archive_dir}`.** A name collision is skipped and
   reported.
7. **Never acquires a machine-managed disposition.** No recovery-artifact disposition class,
   no upgrade-banner count, no upgrade cleanup offer, and no reachability from any automatic
   cleanup writer. `{feedback_dir}` and `{archive_dir}` alike stay outside every automatic
   cleanup surface.
8. **Never sweeps on age, size, or count.** Candidacy is the presence of a posted marker and
   nothing else.
9. **Never makes a network call.** Sweeping is a local file operation.
10. **Never writes, repairs, or removes a `.posted` marker.** `--sweep` relocates markers;
    it is not a marker writer.

---

## Reporting Draft Status

`/planwise feedback --status` is read-only: it queries the tracker for each locally posted
draft's current state and never writes anything — not a fixed marker, not a cache, not a
report file. It has no consent site: it posts nothing, so it asks no question and introduces
no `<!-- AUTO-MODE: -->` marker. In Auto Mode it behaves exactly as it does interactively.

**Gated on `feedback.enabled`.** Unlike `--sweep`, `--status` makes a network call to the
tracker, so it is gated the same way the post pipeline is — see Degradation below for what it
does instead when the gate is not met.

### Query and Input

`--status` enumerates `*.md` files directly in `{planwise_root}/{feedback_dir}`
(non-recursive, the same set `--sweep` walks), then for each one reads its posted-marker
sidecar if one exists.

De-duplicated issue numbers are queried, one read-only call each:

```
gh issue view {NN} -R {feedback.repo} --json number,title,state,url
```

exactly the four fields already documented above as the engine's read-only validation call.
**`gh search` is never used by `--status`** — every issue number is already on disk in a
posted-marker sidecar, so a search would be a guess where an exact lookup already exists.

**Budget**, mirroring the duplicate scan's: 10 seconds per call; 30 seconds for the whole
run. On exceeding the per-call budget, that row degrades to `unknown` and the run continues;
on exceeding the whole-run budget, no further calls are issued and every remaining row
renders `unknown`. At most **20** distinct issue numbers are queried per run; beyond that,
the run appends `… and {N} further issue(s) not queried (per-run lookup limit).` and renders
those rows `unknown`.

`{NN}` is the segment of `url:` after `/issues/`, truncated at any `#` fragment — the same
rule covers the issue path and the comment path, since a comment's `url:` carries its parent
issue's number. A marker whose `url:` yields no `/issues/{NN}` segment renders `MARKED —
marker unreadable`, is not queried, and is not repaired.

**Output**, one row per draft, grouped, most recent first:

| Draft | Marked | Route | Issue | State | Title |
|---|---|---|---|---|---|
| `2026-08-18-bug-draft-path.md` | 2026-08-18 | issue | #412 | OPEN | Feedback drafts land in the wrong directory |
| `2026-08-19-idea-sweep.md` | — | — | — | — | *not known to have been posted* |

Followed, when `{archive_dir}` exists, by one line: `{N} archived draft(s) in {archive_dir}
(not listed).` The archive is not walked or queried — bounding the output is the point of
archiving.

### Unmarked Drafts

An unmarked draft is reported, in its own group headed `Not known to have been posted
({n})`, as **`not known to have been posted`** — never as "unposted", never as "failed", and
never omitted. The wording is deliberate: an unmarked draft may have been pasted into the web
UI by hand, the fallback path this engine already prints instructions for, and no marker
would exist for that. Reporting it as "unposted" would assert something `--status` cannot
know.

Their Issue / State / Title cells render `—`, never a guess. `--status` **never** searches
the tracker to find a match for an unmarked draft — not by title, not by content, not by
date — the same UNKNOWN/CLEAR discipline the duplicate scan follows above: a result that
could not be determined must never be rendered as a finding.

One trailing line names the remedy without inventing a capability: `A draft with no marker
was either never posted, or was filed by hand outside this tool. Post it with
/planwise feedback, or remove it yourself.`

### Degradation

Governed by the same posture as the post pipeline: never block, never error out. **Every
branch below exits 0**, and every branch still prints the complete local half (draft, marked
date, route, URL) read from disk, which needs no network and no permission.

| Case | Behaviour | `{status_caveat}` |
|---|---|---|
| `feedback.enabled` is false | Local half only; no `gh` call is made | `Tracker state not checked — feedback.enabled is false in config.yaml. Only the local record is shown.` |
| `gh` not on PATH | Local half only | `Tracker state unknown — gh was not found on PATH.` |
| `gh auth status` exits non-zero | Local half only | `Tracker state unknown — gh is not authenticated (gh auth status exited non-zero).` |
| `config.yaml` missing or unreadable | Local half only, `plugin_version: unknown` posture | `Tracker state not checked — config.yaml could not be read, so the feedback repo is unknown.` |
| One `gh issue view` exits non-zero, returns empty, or exceeds its budget | That row only renders `unknown`; the run continues | `Tracker state unknown for {n} of {m} issue(s).` |
| Whole-run budget exceeded | No further calls; remaining rows render `unknown` | `Tracker state unknown for {n} of {m} issue(s) — the lookup budget was reached.` |
| `{planwise_root}/{feedback_dir}` absent or empty | `No feedback drafts found in {planwise_root}/{feedback_dir}.`, exit 0 | none — this is a complete, correct answer, not a degradation |

**UNKNOWN is never rendered as a finding**, mirroring the duplicate scan's rule above: a row
that could not be read says `unknown`; it never renders `CLOSED`, `missing`, or a blank that
reads as absence. The first two cases above are worded `not checked` rather than `unknown`
because the tool made a deliberate choice not to look, which is a different fact from a
lookup that failed.

`{status_caveat}` is one line, printed once at the head of the `--status` output — one
string, one source of truth, the same shape as `{scan_caveat}` above.

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
**This site deviates on the last step:** on auto-deny the engine writes the draft and
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

**The duplicate scan queries the tracker before consent.** Step 4.5 sends search keys —
never the body — to `{feedback.repo}` as read-only query parameters, before gate 5 is
reached. Keys are restricted by construction to `^[A-Za-z0-9._/:+#-]{3,60}$` and a key is
dropped, never repaired, if it begins `/` `~` `\` or a drive letter, contains `@`, or is a
bare number. So a consumer-local absolute path, an email, and an `@handle` cannot become a
search key. A query parameter is transient; nothing is published by the scan.

---

## Placeholder Reference

Every placeholder used above, for the four call sites that render this engine's templates:

| Placeholder | Resolves to |
|---|---|
| `{feedback.repo}` | `gabgoss/planwise` (literal default; never the consumer's own remote). |
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
| `{n}`, `{k}`, `{N}`, `{m}` | Inline integer counts: `{n}` searches attempted (and the quantity in a rendered age, or of `--sweep` candidates / `--status` drafts), `{k}` of them that returned, `{N}` further or suppressed matches (or un-queried issues) not shown, `{m}` the total issues queried by `--status`. |

Two brace forms above are deliberately not placeholders and need no row: `{3,60}` in the search-key
pattern is a regular-expression quantifier, and a self-describing slot inside a template fence
(`{the approved body, verbatim, …}`) names its own contents.
