---
description: Feedback submission engine, Part 2 — the three local pipelines on the feedback draft directory (sweeping posted drafts to an archive, reporting each draft's status, and reviewing model drafts). Split out of feedback-submission.md when that file neared the Read-tool token gate. Part 2 of 3. Part 1 of 3 is feedback-submission.md.
consult-when: Sweeping posted feedback drafts to an archive, reporting each draft's status, or reviewing model-written drafts — the three local pipelines on the feedback draft directory
---

# Feedback Submission Engine, Part 2 — Local Draft Pipelines

**Purpose:** The three local pipelines of the feedback submission engine, split out of
[feedback-submission.md](feedback-submission.md) when that file neared the Read-tool token
gate. Part 1 keeps the original filename and holds the gate chain, the duplicate scan, the
draft-first invocation and the posted-draft marking. Each pipeline here shares the draft
directory and the posted-marker contract that Part 1 defines.
[Part 3](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md) holds the fallback posture,
the Auto-Mode deviation, the issue body spec, the privacy contract and the placeholder
reference. Consumers delegate here on the same terms as Part 1, and re-specify nothing locally.

## Table of Contents

- [Sweeping Posted Drafts](#sweeping-posted-drafts)
- [Reporting Draft Status](#reporting-draft-status)
- [Reviewing Model Drafts](#reviewing-model-drafts)

---

## Sweeping Posted Drafts

`/planwise feedback --sweep` is a second, separate pipeline in this engine — a local file-move
operation, not an outward post. It shares the draft directory and the posted-marker contract
in Part 1 ([Marking a Posted Draft](feedback-submission.md#marking-a-posted-draft)) with the post pipeline, and nothing else: it makes no network call, and it has its own
single consent site, distinct from the post pipeline's.

### Candidacy

A sweep candidate is a `*.md` file directly in `{planwise_root}/{feedback_dir}`
(non-recursive) that has a sibling posted-marker sidecar — the draft's own path with
`.posted` appended, exactly as Part 1's Marking a Posted Draft describes — and both files must exist. Nothing else is
ever a candidate. A candidate that was blocked before it was posted also has a `.blocked`
sidecar, which is the draft's own path with `.blocked` appended. That sidecar goes with the
draft. **Age is never a candidacy criterion** and there is no age flag: an old
*unposted* draft is exactly what an age rule would catch first, and it is exactly the file
this command must never touch. Non-recursive walking is load-bearing, not incidental — it is
what stops a later `--sweep` run from re-sweeping the archive it just created.
A model draft never has a sidecar, because only the standard draft that `promote` writes is
ever posted and marked, so a model draft is never a candidate.

### Action

Sweeping **archives; it never deletes.** A candidate's draft, its `.posted` sidecar and its
`.blocked` sidecar, when one exists, move together into `{archive_dir}`. It never copies.

- The files move **together or not at all**. If one move fails, the files already moved are
  moved back and the candidate is reported as skipped.
- If a candidate's filename already exists in `{archive_dir}`, that candidate is **skipped,
  left in place, and reported.** Nothing already in `{archive_dir}` is ever overwritten.
- A draft with no `.posted` sidecar is not a candidate. A `.posted` or `.blocked` sidecar with
  no draft is an orphan: reported and left in place, never moved and never removed.
- `{archive_dir}` is created on first use only, after consent is given. A run that is
  cancelled, or that finds no candidates, creates no directory.
- On success, each moved file's new absolute path is printed, so the consumer holds a
  current path for every file that moved.

**No `Delete` option exists, in the prompt or as a flag.** A consumer who wants the bytes
gone deletes `{archive_dir}` themselves — that is genuinely their own action and needs no
tool support.

### Dry-run default

`--sweep` always produces the candidate listing first, before any consent call and before
any file moves. There is no `--dry-run` flag, because the listing is not an opt-in mode: it
is the only thing that happens unless consent is explicitly given.

The pipeline runs this command to build the listing:

```
python "{plugin_root}/scripts/feedback_drafts.py" sweep-list --config "{planwise_root}/config.yaml"
```

Print its stdout verbatim, before any consent call and before any question. The command is
read-only. It moves, writes and deletes nothing.

Per candidate, the listing prints the draft's absolute path, its `posted:` date, `url:`, and
`route:`, then a `blocked sidecar:` line when the candidate has one. After the candidates it
prints each orphan sidecar, then one summary line: `{n} draft(s) already posted are eligible to archive.` With
no candidates: `No posted drafts to archive.`, exit 0 — no prompt is raised.

### Interaction Matrix

One consent site, one `AskUserQuestion` call, raised only when the listing above found at
least one candidate. The prompt shows the listing, states `{archive_dir}` by absolute path,
and names the exact count in the option label.

<!-- AUTO-MODE: critical -->

| # | Branch | Offered as | What it does | Default | Files touched |
|---|---|---|---|---|---|
| 1 | Listing | not an option — runs unconditionally, before the prompt | Prints every candidate's absolute path, posted date, issue URL and route; then the count line | **Yes — always runs, and is all that runs unless branch 2 is explicitly chosen** | none |
| 2 | Archive | `Archive {n} posted draft(s) to {archive_dir}` | Moves each draft + its sidecars into `{archive_dir}`; prints each new absolute path; skips and reports any collision or orphan | No | the `{n}` listed drafts and their sidecars only |
| 3 | Cancel | `Cancel — leave all {n} drafts where they are` | Nothing. Prints `Nothing was moved.` | **Yes — pre-selected** | none |
| 4 | Non-answer / non-interactive — Auto Mode, auto-deny, an unanswered or interrupted prompt, or any state in which `AskUserQuestion` cannot return an answer | not offered; this branch is taken without a question | The listing stands as the complete output. Prints `Non-interactive session — {n} posted draft(s) listed above were not moved. Re-run /planwise feedback --sweep interactively to archive them.` Exit 0. | **Yes — this is the branch taken** | none |
| 5 | Any other answer, an unparseable answer, or an error raising the prompt | — | Treated as branch 3 (Cancel) | — | none |

Branch 4 carries `<!-- AUTO-MODE: critical -->`, the same deviation shape as the post
pipeline's Auto-Mode site in Part 3 ([Auto Mode — A Deliberate, Documented Deviation](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md#auto-mode--a-deliberate-documented-deviation)), for the same reason: the declined branch has a complete,
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
5. **Never separates a draft from its sidecars.** The draft, its `.posted` marker and any
   `.blocked` sidecar move together or none of them moves.
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
"{gh_path}" issue view {NN} -R {feedback.repo} --json number,title,state,url
```

exactly the four fields already documented in Part 1 as the engine's read-only validation call.
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

A comment post marks two files: the issue draft and the comment draft made from it. Both rows
show `comment` and the same issue. The two rows record one post.

### Unmarked Drafts

An unmarked draft is reported, in its own group headed `Not known to have been posted
({n})`, as **`not known to have been posted`** — never as "unposted", never as "failed", and
never omitted. The wording is deliberate: an unmarked draft may have been pasted into the web
UI by hand, the fallback path this engine already prints instructions for, and no marker
would exist for that. Reporting it as "unposted" would assert something `--status` cannot
know.

Their Issue / State / Title cells render `—`, never a guess. `--status` **never** searches
the tracker to find a match for an unmarked draft — not by title, not by content, not by
date — the same UNKNOWN/CLEAR discipline the duplicate scan in Part 1 follows: a result that
could not be determined must never be rendered as a finding.

One trailing line names the remedy without inventing a capability: `A draft with no marker
was either never posted, or was filed by hand outside this tool. Post it with
/planwise feedback, or remove it yourself.`

**Model drafts are not unmarked drafts.** Queued and expired model drafts get their own group,
headed `Model drafts, not yet reviewed ({n})`, with `—` in every cell after Draft. `--status`
reads each one's `status:` frontmatter directly. The group ends with `Review them with /planwise feedback --drafts.`

### Blocked Drafts

A draft that the privacy check of an unattended post blocked gets its own group, headed
`Blocked by the privacy check ({n})`. `--status` builds the group from one local call:

```
python -B "{plugin_root}/scripts/feedback_drafts.py" blocked-list --json --all --config "{planwise_root}/config.yaml"
```

The group holds each row whose `posted` is `false`. Its cells are the draft's file name, the
class, the line number, the route and the dismissed date, with `—` for a row that was not
dismissed. A row never holds the matched text. These drafts leave `Not known to have been
posted`. With no such row, leave the group out.

The group ends with one line: `Fix the named line, then post the draft with /planwise feedback
--drafts, or clear the record with feedback_drafts.py dismiss-blocked. A dismissed draft is no
longer offered.` The call is local, so every Degradation branch still prints this group.

### Degradation

Governed by the same posture as the post pipeline: never block, never error out. **Every
branch below exits 0**, and every branch still prints the complete local half (draft, marked
date, route, URL) read from disk, which needs no network and no permission.

| Case | Behaviour | `{status_caveat}` |
|---|---|---|
| `feedback.enabled` is not `true` (`disabled` or `absent`) | Local half only; no `gh` call is made | `Tracker state not checked — feedback.enabled is not true in config.yaml. Only the local record is shown.` |
| `gh` not resolvable (not on PATH, not at a known install location) | Local half only | `Tracker state unknown — gh was not found on PATH or at a known install location.` |
| `{gh_path} auth status` exits non-zero | Local half only | `Tracker state unknown — gh is not authenticated (gh auth status exited non-zero).` |
| `config.yaml` missing or unreadable | Local half only, `plugin_version: unknown` posture | `Tracker state not checked — config.yaml could not be read, so the feedback repo is unknown.` |
| One `gh issue view` exits non-zero, returns empty, or exceeds its budget | That row only renders `unknown`; the run continues | `Tracker state unknown for {n} of {m} issue(s).` |
| Whole-run budget exceeded | No further calls; remaining rows render `unknown` | `Tracker state unknown for {n} of {m} issue(s) — the lookup budget was reached.` |
| `{planwise_root}/{feedback_dir}` absent or empty | `No feedback drafts found in {planwise_root}/{feedback_dir}.`, exit 0 | none — this is a complete, correct answer, not a degradation |

**UNKNOWN is never rendered as a finding**, mirroring the duplicate scan's rule in Part 1: a row
that could not be read says `unknown`; it never renders `CLOSED`, `missing`, or a blank that
reads as absence. The first two cases above are worded `not checked` rather than `unknown`
because the tool made a deliberate choice not to look, which is a different fact from a
lookup that failed.

`{status_caveat}` is one line, printed once at the head of the `--status` output — one
string, one source of truth, the same shape as `{scan_caveat}` in Part 1.

---

## Reviewing Model Drafts

`/planwise feedback --drafts` and `/planwise feedback --post {draft_id}` are the review routes
for model drafts: feedback files a model wrote during `/planwise` work, which nothing sends
until the user reviews them here. Listing and discarding are local. Posting runs the post
pipeline in Part 1, from gate 1, on the promoted file.

### Candidacy

A `{model draft}` is a `*.md` file directly in `{planwise_root}/{feedback_dir}`
(non-recursive) whose name matches `{model_draft_name}` and whose frontmatter carries
`drafted_by: model`. In a linked git worktree, `{planwise_root}/{feedback_dir}` is the main checkout's feedback folder, and the helper resolves it from the session's own `--config`. Resolve the set with the helper. `list` reports a queued draft past the expiry limit as `expired` and writes nothing. Only the helper's `expire`, `admit` and `create` commands write `status: expired`. `list` also reports a promoted draft as `blocked` when its promoted file has a `.blocked` sidecar with no dismissal and no post. The file on disk keeps `status: promoted`:

```
python "{plugin_root}/scripts/feedback_drafts.py" list --json --config "{planwise_root}/config.yaml"
```

Route the result on the exit code:

- **Exit 0 with a JSON array.** Each object carries the frontmatter keys (`draft_id`,
  `created_at`, `kind`, `title`, `producer`, `source_session_id` and `status` among them) and
  `path`, the filename relative to `{feedback_dir}`.
- **Exit 0 with output that is not JSON.** Treat it as the empty list. A project that has
  never drafted has no feedback directory, and that is its normal state.
- **Any other exit.** Print the helper's stderr line and stop. Nothing else runs.

Every later helper call in this section takes the same `--config` option.

### Listing

`--drafts` always prints the listing first, before any question. Rows are grouped
`Queued ({n})`, then `Blocked by the privacy check ({n})`, then `Expired ({n})`, most recent
`created_at` first. `--drafts --all` reads
`list --json --all` and adds `Discarded ({n})` and `Promoted ({n})`.

The pipeline runs this command to build the listing:

```
python "{plugin_root}/scripts/feedback_drafts.py" list --table --config "{planwise_root}/config.yaml"
```

Print the command's stdout verbatim, before any question. Do not rewrite, reorder or summarize
it. Add `--all` when `--drafts --all` was given. The command reads the running session's id
from the `CLAUDE_CODE_SESSION_ID` environment variable, which the Bash tool sets, so pass no
id for it. Pass `--session-id {id}` only to override that variable. The command prints the
table below, so the table is the contract the command implements.

| Draft | Created | Kind | Title | Producer | Session |
|---|---|---|---|---|---|
| `2026-10-12-draft-bug-helper-exit-code.md` | 2026-10-12 | bug | Helper exits 1 on valid input | prompt | this session |

Draft is the row's `path`. Session reads `this session` when the row's `source_session_id`
equals the session id, `other session` when it differs, and `unknown` when no id is
available. The session id is the `--session-id` value, else `CLAUDE_CODE_SESSION_ID`. An
empty variable counts as no id. A group with no rows is
omitted. With no model drafts at all, print `No model drafts found in {feedback_dir}.` and
exit 0. No question is asked.

### Posting One Draft by Id

`/planwise feedback --post {draft_id}` acts on one named draft. `{draft_id}` is the
`draft_id` frontmatter value, the same id `discard` and `promote` take.

**Card route.** While drafts are queued, the skill's preflight prints a block between
`<!-- planwise:feedback:begin -->` and `<!-- planwise:feedback:end -->`. While a blocked draft
waits, that block holds only a fallback line. When that block is
present with no `PLANWISE_FEEDBACK_FALLBACK:` line, take the id from the `ARGUMENTS:` line and
look it up among the block's rows. The block never carries the id itself. On a match, ask the
per-draft question of the card route below for that draft only, with the body from the block.
When no row carries the id, print `Model draft {draft_id} was not found among queued drafts.`
and stop.

**Without the block.** An empty queue prints no block, and a failed preflight or a blocked
draft prints the fallback line. Resolve the id from `list --json`: the row whose `draft_id`
equals it and whose `status` is `queued` or `blocked`. On a queued match, show that draft's
full body, then ask the per-draft question for that draft only, with the same marker and the
same three options. On a blocked match, follow [A Blocked Draft](#a-blocked-draft), taking the
promoted file from the model draft's `promoted_to:` line. Otherwise print one line:

`Model draft {draft_id} was not found among queued or blocked drafts ({reason}).`

`{reason}` is the row's `status` in `list --json --all`, or `unknown` when no row carries the
id. The route then falls through to `--drafts`, starting at the Listing. It never skips the
per-draft question.

### Per-Draft Action

#### Card Route

This route runs when the preflight block is present with no `PLANWISE_FEEDBACK_FALLBACK:` line,
and the `ARGUMENTS:` line is `--post {draft_id}` or `--drafts` without `--all`. The block holds
a `Queued drafts (N) in {folder}:` header, the queued rows, a `Posting state:` line, a
`Target repository:` line and each body under `--- draft {id}: {title} ---`. The
block already did the listing, the state check and the draft reads, so the route repeats none
of them. Expired drafts are not in the block.

When the `Posting state:` line is not `enabled`, ask the posting question of the fallback below
once, before the first draft. On Enable, run `enable-posting` and print its one line.

One `AskUserQuestion` per draft: the named draft on `--post`, each row in block order on
`--drafts`. The question shows the draft's id, title and body verbatim from the block. It names
the repository on the `Target repository:` line. It says that **Post** publishes the shown body
there with no further question. Three options:

| Option | What it does |
|---|---|
| **Post** | The steps below. While posting is still off, the option text adds `(this sets feedback.enabled to true in config.yaml)`. |
| **Discard** | One call: `python -B "{plugin_root}/scripts/feedback_drafts.py" discard {draft_id} --config "{planwise_root}/config.yaml"`. Exit 1 prints `Model draft {draft_id} was not found.` |
| **Keep** (pre-selected) | Nothing. The draft stays queued. Any other or unparseable answer is Keep. |

**Post** runs these steps:

1. When posting is still off, run `enable-posting --config "{planwise_root}/config.yaml"` and
   print its one line. On exit 1, print its stderr line and stop.
2. Run one call:
   `python -B "{plugin_root}/scripts/feedback_post.py" post --config "{planwise_root}/config.yaml" --draft-id {draft_id} --consent review`.
   `--consent review` keeps the provenance line that says a person reviewed the text. The
   question showed the body, so the line is true on this route.
3. The driver runs the post checks itself, on the exact file it posts. It reads the posting
   state, finds `gh` and checks its sign-in, runs the duplicate scan and picks the route by
   Unattended Routing in [Part 1](feedback-submission.md#unattended-routing), and runs
   `prepare-post` before it posts. On a privacy block it also writes the blocked record. The
   route makes no other call for these checks.
4. The **Post** answer is the consent, so gate 5 is not asked. Route on the driver's exit code.
   Exit 0 posted: print its last stdout line. Exit 3 kept the draft and posted nothing: print
   its last stdout line. Exit 4 means posting is off: print
   `Posting stays off. The draft was saved, and the next feedback flow asks again.` Any other
   exit: print its last stderr line. The draft stays queued.

#### Fallback: Without the Preflight Block

An absent block, a block with the fallback line, and `--drafts --all` take this route. After
the listing, `--drafts` asks the per-draft question once for each Queued draft, in
listing order. It then asks the question of [A Blocked Draft](#a-blocked-draft) for each
Blocked draft. An expired draft is listed only, and is never offered for posting.

<!-- AUTO-MODE: critical -->
Before the first draft, the interactive review runs
`python "{plugin_root}/scripts/feedback_drafts.py" posting-state --config "{planwise_root}/config.yaml"`.
When it prints anything but `enabled`, ask the posting question once, with one
`AskUserQuestion`. It uses the question text of The Enable Offer (gate 1) in
[Part 1](feedback-submission.md#the-enable-offer-gate-1-absent-and-disabled-state), and
**Enable posting (Recommended)** is the first option. On Enable, run
`enable-posting --config "{planwise_root}/config.yaml"` and print its one line. On No, or on
an exit 1 from `enable-posting`, review the drafts with posting off. The review asks this
question once per invocation, never once per draft.

One `AskUserQuestion` per draft. It shows the draft's body below its frontmatter, verbatim,
and offers three options:

| Option | What it does |
|---|---|
| **Review and post** | The steps below. While posting is still off, the option text adds `(this sets feedback.enabled to true in config.yaml)`. After an Enable answer to the posting question, it does not. |
| **Discard** | Runs `discard {draft_id}`. The status becomes `discarded`. It never deletes the file. Exit 1 prints `Model draft {draft_id} was not found.` |
| **Keep** (pre-selected) | Nothing. The draft stays queued. Any other or unparseable answer is Keep. |

On the `--post` and `--drafts` routes, the per-draft question is the consent for the post.
**Review and post** runs these steps:

1. When `feedback.enabled` is not `true`, run `enable-posting --config "{planwise_root}/config.yaml"`
   and print its one line. On exit 1, print its stderr line and stop. `config.yaml` is
   unchanged and nothing is promoted.
2. Run `promote {draft_id}`. Exit 0 prints the promoted file's path, a standard draft at
   `{draft_path}` whose last line is the provenance line. On exit 1, print
   `Model draft {draft_id} is not promotable.` On exit 3, print
   `Model draft {draft_id} was already promoted.` Either line ends the branch, and no
   pipeline runs.
3. Run the post pipeline from gate 1 on the promoted file, duplicate scan included. The
   promoted file is the draft the pipeline posts from, so its draft-first write is done.
   `{title}` and `{kind}` come from the model draft's frontmatter.
4. The **Review and post** answer is the consent, so gate 5 is not asked. The duplicate-scan
   outcome picks the route with no question, by the rules of Unattended Routing in
   [Part 1](feedback-submission.md#unattended-routing). Part 1 is the one statement of those
   rules, and this step restates none of them. A failed post leaves the promoted draft on
   disk, as On Any Gate Failure or Post Failure (Part 3) specifies.

#### A Blocked Draft

A blocked draft is a model draft that `list --json` reports with `status` `blocked`. Its
promoted file is the one its `promoted_to:` line names. Read the class and the line number from
the row of this call whose `draft` is that file:

```
python -B "{plugin_root}/scripts/feedback_drafts.py" blocked-list --json --config "{planwise_root}/config.yaml"
```

<!-- AUTO-MODE: critical -->
Ask one `AskUserQuestion` per blocked draft. It shows the draft's id and title, the class, the
line number and the promoted file's absolute path. It never shows the matched text. It says
that the user fixes the named line in that file before choosing Post. Three options:

| Option | What it does |
|---|---|
| **Post** | The steps below. |
| **Dismiss** | Runs `feedback_drafts.py dismiss-blocked --draft "{promoted file path}"`. The draft stays on disk and is no longer offered. |
| **Keep** (pre-selected) | Nothing. The draft stays blocked. Any other or unparseable answer is Keep. |

**Post** runs these steps. There is no promote step, because the promoted file exists:

1. The unattended attempt may have left a last line that says no person reviewed the text. Make
   the file's last line read
   `Drafted by Claude via planwise feedback drafting; reviewed and approved by the user before posting.`
2. Run the post pipeline from gate 1 on the promoted file, duplicate scan included. `{title}`
   and `{kind}` come from the model draft's frontmatter.
3. Ask gate 5 on the fixed text, as [Part 1](feedback-submission.md#gate-chain) states it. The
   per-draft answer chose the draft, and gate 5 is the consent to post. A cancel or a failed
   post leaves the draft blocked.

### Auto Mode

A non-answer takes this branch: Auto Mode, auto-deny, or an unanswered or interrupted
prompt. `--drafts` prints the listing, then this line, and exits 0:

`Non-interactive session — {n} model draft(s) listed above. Re-run /planwise feedback --drafts interactively to review them.`

`--post {draft_id}` prints this line, posts nothing, and exits 0:

`Non-interactive session — model draft {draft_id} was not posted. Re-run /planwise feedback --post {draft_id} interactively to review it.`

`--drafts` and `--post` stay review commands that need an interactive run. An unattended
context posts a model draft at drafting time instead, as `feedback-drafting.md` § Auto Mode
describes. Gate 2 routes that post at drafting time, never through these two commands.

This is the deviation shape of the sweep's branch 4. The declined branch has a complete
outcome, so failing loud would break an unattended run for no gain. Nothing is enabled,
promoted or discarded.

### Gating

The listing, Discard and Keep are local and not gated on `feedback.enabled`, as `--sweep` is
not. On the card route, **Post** runs the driver's checks: the posting state, `gh` found and
signed in, the duplicate scan with Unattended Routing, and `prepare-post` on the exact file it
posts. On the fallback route, **Review and post** runs the post pipeline from gate 1 on the
promoted file. On both routes, from `--post` and `--drafts` alike, the per-draft answer is the
consent and gate 5 is not asked, so no route adds a consent site. A blocked draft is the one
exception. Its per-draft answer is a selection, and gate 5 is its consent.

---

*Cross-reference: [feedback-submission.md](feedback-submission.md) (Part 1 — gate chain, duplicate scan, draft-first, posted-draft marking), [feedback-submission-Part-3-FailureBodySpecAndPrivacy.md](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md) (Part 3 — fallback posture, Auto Mode deviation, issue body spec, privacy contract, placeholders).*
