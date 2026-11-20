# Handler: /planwise feedback

**Purpose:** Report a planwise bug, lesson, or idea upstream to the plugin's own repo via a
GitHub issue. Collects the report from the user, then delegates the entire outward-post
pipeline to the shared submission engine.

**Invocation examples:**
```
/planwise feedback
/planwise feedback bug
/planwise feedback lesson
/planwise feedback idea
/planwise feedback --status
/planwise feedback --sweep
/planwise feedback --drafts
/planwise feedback --post <draftId>
```

`kind` defaults to `bug` when omitted, **and no mode flag is given**. `kind` selects which
body-spec variant the engine renders (`bug` vs. `lesson`/`idea`), per the Issue Body Spec in `references/feedback-submission-Part-3-FailureBodySpecAndPrivacy.md`.
`--status`, `--sweep`, `--drafts` and `--post <draftId>` are separate modes — see `## Routing`
below — and take no `kind`.

---

> [!constraint] Config-Gate exception — deliberate and documented
> Every other handler opens with `## Config Gate (Auto-Init Fallback)`. This handler
> deliberately does not — this handler's caller may be someone whose `config.yaml` is
> missing or broken, which is exactly what they may want to report. Routing that user
> through auto-init before they can even describe the problem would defeat the purpose.
>
> If `config.yaml` is missing or unreadable:
> - Do **NOT** invoke auto-init.
> - Set `plugin_version: unknown` for the Environment block (it cannot be read from a
>   config that isn't there). `feedback.include_environment` resolves `true` here, matching
>   the loader default. This run is draft-only, so nothing posts.
> - Proceed **draft-only** — `feedback.enabled` cannot be confirmed `true` without a
>   readable config, so no post is attempted regardless of what the user answers.
> - Print the draft's absolute path and `https://github.com/gabgoss/planwise/issues` so
>   the user can still file the report by hand.
>
> This is a deliberate, documented exception to the Config Gate pattern every other
> handler follows — not an oversight, and not something a future edit should "fix" by
> adding a `## Config Gate` section here.

---

## Required References

Before proceeding, read:
- `references/feedback-submission.md` — the shared submission engine. It is the ONE
  place the gate chain, the duplicate scan, draft-first invocation, posted-draft
  marking, fallback posture, Auto-Mode deviation, issue body spec, and privacy
  contract are specified. It spans three files. Part 1, which keeps that filename, holds the gate chain,
  the duplicate scan, draft-first and posted-draft marking.
  `references/feedback-submission-Part-2-LocalDraftPipelines.md` holds the sweep, status and
  model-draft pipelines. `references/feedback-submission-Part-3-FailureBodySpecAndPrivacy.md`
  holds the fallback posture, Auto-Mode deviation, issue body spec, privacy contract and
  placeholders. Read the part each mode needs, per `## Routing`. This handler
  cites and delegates to it end to end; it does not re-specify, shortcut, or duplicate any
  of the above.

**Base references** (`markdown-conventions.md`, `callout-conventions.md`,
`agent-orchestration.md`, `do-the-hard-things.md`, `native-tool-use.md`, `feedback-drafting.md`) are pre-injected by SKILL.md.

---

## Workflow

### Step 1: Resolve Config

Attempt to resolve `config.yaml` the normal way (`planwise/config.yaml`, or `*/config.yaml`
one level down from project root). If found and readable, extract `feedback.repo`,
`feedback.include_environment`, and `plugin_version`. Read `feedback.enabled` only through the
engine's gate 1 (`posting-state`), which tells an `absent` key from one set to a value other
than `true`. This handler does not parse the key itself. Gate 1 re-offers posting while
feedback.enabled is not true, in the absent and the disabled state. The handler passes
`feedback.include_environment` to the engine. The engine's Issue Body Spec and its pre-gate-5
step decide whether the Environment block renders, and this handler does not re-specify that
rule. If missing or
unreadable, follow the Config-Gate exception above instead — do not auto-init.

### Step 2: Parse Mode

Read `$1`. Five modes, mutually exclusive:

| `$1` | Mode | Notes |
|---|---|---|
| absent, or `bug` \| `lesson` \| `idea` | **post** (default) | `kind` defaults to `bug` when omitted and no mode flag is given. Anything else here: ask the user to pick one of the three. |
| `--status` | **status** | Takes no further argument. |
| `--sweep` | **sweep** | Takes no further argument. |
| `--drafts` | **drafts** | Takes no `kind`. Takes `--all` (read from `$2`) as its only optional argument, and passes it to the engine. Without `--all`, it takes the card route below when the preflight block is present. |
| `--post <draftId>` | **post-draft** | Takes exactly one value, read from `$2`: the `draft_id` of a queued model draft. Takes no `kind`. The name `post-draft` keeps it distinct from the default **post** mode. It takes the card route below when the preflight block is present. |
| `--post` with no value | none | Reject: `--post needs a draft id. Run /planwise feedback --drafts to list the queued drafts.` Do nothing, exit 0. |
| any two of `--status`, `--sweep`, `--drafts`, `--post` | none | Reject: `--status, --sweep, --drafts and --post cannot be combined. Run one at a time.` Do nothing, exit 0. |
| a mode flag plus a `kind` | none | Reject: `--status, --sweep, --drafts and --post take no kind argument.` Do nothing, exit 0 — a `kind` is meaningless to all four, and silently ignoring it would hide a typo. |
| `--all` without `--drafts` | none | Reject: `Unknown option: --all. It is valid only with --drafts.` Do nothing, exit 0. |
| any other `--flag` | none | Reject: `Unknown option: {$1}. Valid: bug, lesson, idea, --status, --sweep, --drafts, --post.` Do nothing, exit 0. |

Every rejection prints one line and exits 0. None of them raises a prompt, and none falls
through to the post flow — a mistyped flag must never begin collecting a report the user did
not ask for.

#### Card Route for `--drafts` and `--post`

While model drafts are queued, the skill's preflight prints a block between
`<!-- planwise:feedback:begin -->` and `<!-- planwise:feedback:end -->`. It holds the queued
rows, a `Posting state:` line and each draft's body under `--- draft {id}: {title} ---`. The
card route runs when that block is present with no `PLANWISE_FEEDBACK_FALLBACK:` line, and the
`ARGUMENTS:` line is `--post <draftId>` or `--drafts` without `--all`:

1. Take the flag and the id from the `ARGUMENTS:` line, never from the block.
2. On `--post <draftId>`, find the id among the block's rows. When no row carries it, print
   `Model draft {draft_id} was not found among queued drafts.` and stop.
3. When the `Posting state:` line is not `enabled`, ask the posting question once, before the
   first draft, as the Per-Draft Action section of Part 2 describes.
4. Ask one per-draft question: the named draft on `--post`, each row in block order on
   `--drafts`. Show the body verbatim from the block, and offer **Post**, **Discard** and
   **Keep** (pre-selected). The question says that Post publishes the shown body with no
   further question.
5. On Post, run one `feedback_post.py post` call. On Discard, run one `feedback_drafts.py discard`
   call. On Keep, run nothing. The Per-Draft Action section of Part 2 holds the commands and
   the exit codes.

An absent block, a block with the fallback line, and `--drafts --all` take the engine route of
Step 4. Every other mode ignores the block.

### Step 3: Collect the Report (post mode only)

Per the engine's Issue Body Spec (`references/feedback-submission-Part-3-FailureBodySpecAndPrivacy.md`) for the resolved `kind`, collect
each `{user-supplied}` field directly from the user as free text — never auto-filled,
never inferred from project state. The only fields this handler ever auto-fills are
`plugin_version` (from config, or `unknown` per the exception above) and the OS/shell,
which it observes from its own runtime rather than asking the user to type it. Ask for
the subcommand involved, if any (or "not command-specific").

`status`, `sweep`, `drafts` and `post-draft` mode skip this step entirely — none takes a collected report.

### Step 4: Delegate to the Engine

Dispatch by mode, per `## Routing` below. Each pipeline is owned entirely by the engine
(`references/feedback-submission.md` and its Part-2 and Part-3 files), start to finish; this handler does not re-implement,
shortcut, or duplicate any part of any of them — it supplies inputs and reports the result.

- **post** — hand the collected `kind`, title, and body fields to the engine's gate chain,
  draft-first write, post-or-fallback, posted-draft marking, and Auto-Mode deviation.
- **sweep** — hand off with no arguments to the engine's `## Sweeping Posted Drafts` pipeline, in `references/feedback-submission-Part-2-LocalDraftPipelines.md`. The engine prints the helper's `sweep-list` listing verbatim before any question.
- **status** — hand off with no arguments to the engine's `## Reporting Draft Status` pipeline, in the same Part-2 file.
- **drafts** — with the preflight block present, follow the Card Route in Step 2. Otherwise hand off to the engine's `## Reviewing Model Drafts` pipeline, in the same Part-2 file, with `--all` when given and with no arguments otherwise. The engine prints the helper's `list --table` listing verbatim before any question.
- **post-draft** — with the preflight block present, follow the Card Route in Step 2. Otherwise hand off with the draft id to the engine's `## Reviewing Model Drafts` route `Post one draft`, in the same Part-2 file.

### Step 5: Report the Outcome

- **post** — if the engine posted the issue: report the URL it returned. If the engine
  posted a comment on an existing issue instead: report the comment URL it returned. If the
  engine stopped at any gate (including the Config-Gate exception above), or the post
  failed: report the engine's stop message, the draft's absolute path, and
  `https://github.com/gabgoss/planwise/issues`.
- **sweep** and **status** — print exactly what the engine's pipeline returned: the
  listing, the consent outcome, or the status table. This handler computes none of it.
- **drafts** — print exactly what the engine's pipeline returned: the listing, each per-draft outcome, or the non-interactive line.
- **post-draft** — print exactly what the engine's route returned: the posted URL, the not-found line, or the non-interactive line.

On a successful post the engine also marks the draft posted — a sidecar file beside the
draft, on the issue path and the comment path alike, recording the date and the URL. This
handler never writes that marker itself and never reports an outcome the engine did not
return. A draft whose post did not succeed simply stays unmarked. Nothing in the post path
ever removes or moves a draft or its marker; the only command that relocates one is
`/planwise feedback --sweep`, and only on an explicit answer.

Planwise may **draft** a local feedback file during any `/planwise` work, per
`references/feedback-drafting.md` or through the hooks-module tool when function hooks are
enabled. Drafting is not filing. In an interactive session, Planwise posts a model draft
through `--drafts` or `--post <draftId>`. On those typed routes, the per-draft question is the
consent, and gate 5 is not asked. The duplicate-scan outcome follows Unattended Routing with no
question, as on a card press. A press on the draft card's **Post** button is the consent for
that draft, and no question follows it. In an unattended context with `feedback.enabled: true`,
the engine posts it through its unattended post path. Detecting a possible bug, lesson, or idea
elsewhere in planwise is **offer-only** — surfacing this handler as an option a user can take,
never invoking it on their behalf. The unattended contexts are Auto Mode, a backlog loop
session, and harvest in any session. The manual `/planwise feedback` route keeps gate 5 as its
only consent site, and this handler introduces no second consent site. An unattended context
asks no question and posts only behind `prepare-post`, the engine's privacy gate, run on the
exact file it posts. The engine's gate 1 enable offer for an `absent` key is a setting
selection, owned by the engine, and it never replaces a route's consent site.

---

## Routing

| Mode | Flow | Engine part |
|---|---|---|
| **post** (default) | Step 3 (Collect) → Step 4 (delegate to the post pipeline) → Step 5 | Part 1, plus Part 3 for the body spec, fallback and Auto Mode |
| **status** | Step 4 (delegate to `## Reporting Draft Status`) → Step 5 — Step 3 is skipped | Part 2 |
| **sweep** | Step 4 (delegate to `## Sweeping Posted Drafts`) → Step 5 — Step 3 is skipped | Part 2 |
| **drafts** | Preflight block present, no `PLANWISE_FEEDBACK_FALLBACK:` line, no `--all`: the Card Route in Step 2 → Step 5. Otherwise: Step 4 (delegate to `## Reviewing Model Drafts`) → Step 5. Step 3 is skipped | Part 2 |
| **post-draft** | Preflight block present, no `PLANWISE_FEEDBACK_FALLBACK:` line: the Card Route in Step 2 → Step 5. Otherwise: Step 4 (delegate to the `Post one draft` route of `## Reviewing Model Drafts`) → Step 5. Step 3 is skipped | Part 2, then Part 1 for the post on the engine route |

## Notes

**Rejected shapes (do not reintroduce):** a flow-extensions-only design (unreachable for a
consumer who just hit a live bug); a subcommand-only design (discards an
already-articulated draft on any interruption); a `lessons` sub-mode (buries an outward
network action inside an inward handler and collides with its own mode parsing); folding
this into `upgrade-Part-3-BannerAndConflictResolution.md` Step 4.2 (that step only runs at version change, not on demand);
a `gh`-less HTTP POST (would require in-plugin token handling — `gh`'s own auth is the safe
borrow). The engine's unattended post path replaces the earlier rejection of automatic
filing: it posts only with `feedback.enabled: true`, and only behind `prepare-post`.
