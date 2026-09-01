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
```

`kind` defaults to `bug` when omitted. `kind` selects which body-spec variant
`references/feedback-submission.md` renders (`bug` vs. `lesson`/`idea`).

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
`agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

---

## Workflow

### Step 1: Resolve Config

Attempt to resolve `config.yaml` the normal way (`planwise/config.yaml`, or `*/config.yaml`
one level down from project root). If found and readable, extract `feedback.enabled`,
`feedback.repo`, `feedback.include_environment`, and `plugin_version`. If missing or
unreadable, follow the Config-Gate exception above instead — do not auto-init.

### Step 2: Parse Kind

Read the `kind` argument. Default to `bug` when absent. Valid values: `bug`, `lesson`,
`idea`. Anything else: ask the user to pick one of the three.

### Step 3: Collect the Report

Per `references/feedback-submission.md`'s Issue Body Spec for the resolved `kind`, collect
each `{user-supplied}` field directly from the user as free text — never auto-filled,
never inferred from project state. The only field this handler ever auto-fills is
`plugin_version` (from config, or `unknown` per the exception above). Ask for the
subcommand involved, if any (or "not command-specific"), and the OS/shell.

### Step 4: Delegate to the Engine

Hand the collected `kind`, title, and body fields to `references/feedback-submission.md`.
It owns the whole outward pipeline — gate chain, draft-first write, post-or-fallback,
marking a posted draft, the Auto-Mode deviation — start to finish. This handler does not
re-implement, shortcut, or duplicate any part of that pipeline; it supplies inputs and
reports the result.

### Step 5: Report the Outcome

- If the engine posted the issue: report the URL it returned.
- If the engine posted a comment on an existing issue instead: report the comment URL it
  returned.
- If the engine stopped at any gate (including the Config-Gate exception above), or the
  post failed: report the draft's absolute path and
  `https://github.com/gabgoss/planwise/issues`.

On a successful post the engine also marks the draft posted — a sidecar file beside the
draft, on the issue path and the comment path alike, recording the date and the URL. This
handler never writes that marker itself and never reports an outcome the engine did not
return. A draft whose post did not succeed simply stays unmarked. Nothing here, and nothing
in the engine, ever removes a draft or its marker: that is the user's own action.

This handler never auto-files a report. Detecting a possible bug, lesson, or idea
elsewhere in planwise is **offer-only** — surfacing this handler as an option a user can
take, never invoking it on their behalf. Every post, without exception, rides the engine's
own gate 5 explicit consent — this handler introduces no second consent site.

---

## Notes

This handler has no `## Routing` section — it is a single-argument handler with nothing
to route to.

**Rejected shapes (do not reintroduce):** a flow-extensions-only design (unreachable for a
consumer who just hit a live bug); a subcommand-only design (discards an
already-articulated draft on any interruption); a `lessons` sub-mode (buries an outward
network action inside an inward handler and collides with its own mode parsing); folding
this into `upgrade.md` Step 4.2 (that step only runs at version change, not on demand);
auto-detect-and-file (violates the never-automatic precedent above); a `gh`-less HTTP POST
(would require in-plugin token handling — `gh`'s own auth is the safe borrow).
