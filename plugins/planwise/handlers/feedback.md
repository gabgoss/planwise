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
body-spec variant `references/feedback-submission.md` renders (`bug` vs. `lesson`/`idea`).
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
>   config that isn't there).
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
  contract are specified. This handler
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
than `true`. This handler does not parse the key itself. If missing or
unreadable, follow the Config-Gate exception above instead — do not auto-init.

### Step 2: Parse Mode

Read `$1`. Five modes, mutually exclusive:

| `$1` | Mode | Notes |
|---|---|---|
| absent, or `bug` \| `lesson` \| `idea` | **post** (default) | `kind` defaults to `bug` when omitted and no mode flag is given. Anything else here: ask the user to pick one of the three. |
| `--status` | **status** | Takes no further argument. |
| `--sweep` | **sweep** | Takes no further argument. |
| `--drafts` | **drafts** | Takes no `kind`. Takes `--all` (read from `$2`) as its only optional argument, and passes it to the engine. |
| `--post <draftId>` | **post-draft** | Takes exactly one value, read from `$2`: the `draft_id` of a queued model draft. Takes no `kind`. The name `post-draft` keeps it distinct from the default **post** mode. |
| `--post` with no value | none | Reject: `--post needs a draft id. Run /planwise feedback --drafts to list the queued drafts.` Do nothing, exit 0. |
| any two of `--status`, `--sweep`, `--drafts`, `--post` | none | Reject: `--status, --sweep, --drafts and --post cannot be combined. Run one at a time.` Do nothing, exit 0. |
| a mode flag plus a `kind` | none | Reject: `--status, --sweep, --drafts and --post take no kind argument.` Do nothing, exit 0 — a `kind` is meaningless to all four, and silently ignoring it would hide a typo. |
| `--all` without `--drafts` | none | Reject: `Unknown option: --all. It is valid only with --drafts.` Do nothing, exit 0. |
| any other `--flag` | none | Reject: `Unknown option: {$1}. Valid: bug, lesson, idea, --status, --sweep, --drafts, --post.` Do nothing, exit 0. |

Every rejection prints one line and exits 0. None of them raises a prompt, and none falls
through to the post flow — a mistyped flag must never begin collecting a report the user did
not ask for.

### Step 3: Collect the Report (post mode only)

Per `references/feedback-submission.md`'s Issue Body Spec for the resolved `kind`, collect
each `{user-supplied}` field directly from the user as free text — never auto-filled,
never inferred from project state. The only fields this handler ever auto-fills are
`plugin_version` (from config, or `unknown` per the exception above) and the OS/shell,
which it observes from its own runtime rather than asking the user to type it. Ask for
the subcommand involved, if any (or "not command-specific").

`status`, `sweep`, `drafts` and `post-draft` mode skip this step entirely — none takes a collected report.

### Step 4: Delegate to the Engine

Dispatch by mode, per `## Routing` below. Each pipeline is owned entirely by
`references/feedback-submission.md`, start to finish; this handler does not re-implement,
shortcut, or duplicate any part of any of them — it supplies inputs and reports the result.

- **post** — hand the collected `kind`, title, and body fields to the engine's gate chain,
  draft-first write, post-or-fallback, posted-draft marking, and Auto-Mode deviation.
- **sweep** — hand off with no arguments to the engine's `## Sweeping Posted Drafts` pipeline.
- **status** — hand off with no arguments to the engine's `## Reporting Draft Status` pipeline.
- **drafts** — hand off to the engine's `## Reviewing Model Drafts` pipeline, with `--all` when given and with no arguments otherwise.
- **post-draft** — hand off with the draft id to the engine's `## Reviewing Model Drafts` route `Post one draft`.

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
enabled. Drafting is not filing. Planwise posts a model draft only through `--drafts` or
`--post <draftId>`, and both ride the engine's gate chain. Detecting a possible bug, lesson,
or idea elsewhere in planwise is **offer-only** — surfacing this handler as an option a user
can take, never invoking it on their behalf. Every post, without exception, rides the
engine's own gate 5 explicit consent — this handler introduces no second consent site. The
engine's gate 1 enable offer for an `absent` key is a setting selection, owned by the engine,
and it never replaces gate 5.

---

## Routing

| Mode | Flow |
|---|---|
| **post** (default) | Step 3 (Collect) → Step 4 (delegate to the post pipeline) → Step 5 |
| **status** | Step 4 (delegate to `## Reporting Draft Status`) → Step 5 — Step 3 is skipped |
| **sweep** | Step 4 (delegate to `## Sweeping Posted Drafts`) → Step 5 — Step 3 is skipped |
| **drafts** | Step 4 (delegate to `## Reviewing Model Drafts`) → Step 5 — Step 3 is skipped |
| **post-draft** | Step 4 (delegate to the `Post one draft` route of `## Reviewing Model Drafts`) → Step 5 — Step 3 is skipped |

## Notes

**Rejected shapes (do not reintroduce):** a flow-extensions-only design (unreachable for a
consumer who just hit a live bug); a subcommand-only design (discards an
already-articulated draft on any interruption); a `lessons` sub-mode (buries an outward
network action inside an inward handler and collides with its own mode parsing); folding
this into `upgrade-Part-3-BannerAndConflictResolution.md` Step 4.2 (that step only runs at version change, not on demand);
auto-detect-and-file and auto-draft-and-post (each posts without the user's explicit review and gate 5 consent); a `gh`-less HTTP POST
(would require in-plugin token handling — `gh`'s own auth is the safe borrow).
