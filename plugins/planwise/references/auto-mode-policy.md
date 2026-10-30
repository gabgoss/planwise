---
description: Auto Mode policy — how any handler behaves when AskUserQuestion cannot be answered
consult-when: A handler can't get an AskUserQuestion answer — taxonomy, gate-behavior matrix, inference defaults
---

# Auto Mode Policy

**Summary lives in** [skill-authoring.md](skill-authoring.md) **§4b** — the summary there is complete for authoring skills. This file is the full reference: taxonomy, gate-behavior matrix, inference defaults, and worked examples, needed when implementing handler gate behavior.

**Purpose:** Define how skill handlers behave when invoked non-interactively ("Auto Mode"),
where `AskUserQuestion` cannot be answered by a user.

### § Auto Mode Context

Auto Mode is a harness-level execution flag that signals the skill is running unattended —
for example, when a handler is invoked as a subroutine by another handler, or when the user
invokes a skill with `--auto` in a scripted context. In Auto Mode, `AskUserQuestion` calls
that are classified as **convenience** questions MUST be answered by inference (no prompt
issued). Questions classified as **critical** MUST emit a `[!gate] User Decision Required`
block and still attempt `AskUserQuestion`; if the harness auto-denies the question, the
handler fails loud with the gate text and instructs the user to re-issue the command with
the required argument inline.

Skill authors MUST classify every `AskUserQuestion` call site in their handler as either
critical or convenience. This classification is enforced at plan-review time via
`<!-- AUTO-MODE: critical -->` and `<!-- AUTO-MODE: convenience -->` inline comments.

### § Critical vs Convenience Taxonomy

| Classification | Definition | Examples |
|---------------|------------|---------|
| **Critical** | Agent CANNOT safely infer a correct answer. Wrong inference causes data loss, incorrect plan structure, or destructive action. User MUST decide. | Plan name, abbreviation (when collision possible), vision/objective, sprint count, sprint purpose, scaffolding source mapping, destructive action confirmation (revert/delete) |
| **Convenience** | Agent CAN safely infer a correct answer from project context. Wrong inference causes cosmetic inconvenience, not data loss. | Install scope, directory names, review approach, lesson capture acknowledgment, recovery resume confirmation |

### § Critical Question Behavior

When a call site is classified as **critical**:

1. Emit a `[!gate] User Decision Required` block immediately before the `AskUserQuestion` call:

   ```markdown
   > [!gate] User Decision Required
   > Auto Mode cannot infer this value. Manual input required.
   > Re-issue the command with the answer inline, or run interactively.
   > Question: {question text}
   ```

2. Call `AskUserQuestion` as normal.

3. If the harness auto-denies the question (Auto Mode blocks it):
   - Print the gate text to output.
   - FAIL LOUD: "Auto Mode: critical question '{question summary}' could not be answered.
     Re-issue `/planwise {handler}` with argument `{arg}={value}` inline."
   - STOP — do not proceed past the gate.

**Exception:** outward-facing posts with a complete fallback degrade to the fallback rather than fail loud — see [Auto Mode — A Deliberate, Documented Deviation](feedback-submission-Part-3-FailureBodySpecAndPrivacy.md#auto-mode--a-deliberate-documented-deviation) in the feedback submission engine.

<!-- AUTO-MODE: critical -->

### § Convenience Question Behavior

When a call site is classified as **convenience**:

1. Do NOT call `AskUserQuestion`.
2. Apply the inferred default (see § Inference Defaults below).
3. Log the inference:

   ```
   Auto-Mode inference: {variable}={inferred_value}  (reason: {brief rationale})
   ```

4. Continue without waiting for user input.

<!-- AUTO-MODE: convenience -->

### § Inline Tagging Convention

Every `AskUserQuestion` call site in a handler MUST be tagged with one of:

```markdown
<!-- AUTO-MODE: critical -->
```

or

```markdown
<!-- AUTO-MODE: convenience -->
```

Place the comment on the line immediately BEFORE the `AskUserQuestion` call, or on the
call line itself. A `<!-- Default: … -->` comment may sit between the marker and the call —
that is the house style, and the compliance check allows for it.

This placement lets a reviewer agent check compliance mechanically. Run from the plugin
root:

```bash
# Every AskUserQuestion mention whose own line, and the two lines above it,
# carry no AUTO-MODE marker. Run from the plugin root.
awk '/AskUserQuestion/ && $0 !~ /AUTO-MODE:/ && p1 !~ /AUTO-MODE:/ && p2 !~ /AUTO-MODE:/ {
       printf "%s:%d: %s\n", FILENAME, FNR, $0
     }
     { p2 = p1; p1 = $0 }' handlers/*.md
```

**Reading the result.** Each printed line is a **candidate**, not a confirmed violation.
Disposition every one of them as either:

- a **call site** — an instruction to issue the question. Tag it. This is a defect.
- a **non-call mention** — a cross-reference to a gate specified elsewhere, a negation
  ("no `AskUserQuestion` is issued"), a retrospective reference ("the `AskUserQuestion`
  turn"), or a WRONG/CORRECT exemplar. Leave it untagged. It is not a call site.

The check deliberately does not try to separate those two classes itself. No lexical
discriminator exists: `via` introduces a real call at one site and a prose aside at
another, so any verb-based filter that suppressed the asides would also suppress real
call sites. A compliance gate must fail toward over-reporting — a false positive costs one
judgement, a false negative ships an untagged gate.

> [!constraint] Prove the check discriminates before trusting a clean run
> Run it against two fixtures — one where every site is tagged, one identical except that
> a single site's marker is removed — and require the two runs to **differ**. A gate only
> ever run against the live tree has never been shown to discriminate, and an empty result
> from such a gate is not evidence of compliance.
>
> The check this replaced used a one-line context window and a line-wise filter. It could
> not suppress a tagged site, so it returned its hits whether or not the tree was clean:
> against a fully-tagged fixture it reported every site in the file.

### § Worked Example

```markdown
### Step 1: Gather Information

<!-- AUTO-MODE: critical -->
Use `AskUserQuestion` to collect:
**Question 1:** What is the name of your plan? (e.g., "UserAuthentication")

<!-- AUTO-MODE: critical -->
**Abbreviation:** What is the 2-4 character abbreviation?

<!-- AUTO-MODE: critical -->
**Vision:** Briefly describe the plan vision (1-2 sentences).

<!-- AUTO-MODE: convenience -->
Use `AskUserQuestion` to collect:
**Question 2 (Step 10):** Plan review approach?
- Auto-review (Recommended)
- Review manually first
- Skip to /planwise run
```

When Auto Mode is active:
- Questions tagged `critical` emit `[!gate]` and attempt `AskUserQuestion` (fail loud if denied).
- Questions tagged `convenience` log inference and proceed:
  "Auto-Mode inference: review_approach=auto-review (reason: recommended option)"

### § Inference Defaults

This table is the single source for every convenience default. A row that names no handler
applies wherever that variable is inferred. A row that names a handler and phase applies to
that call site only.

Two rules follow, and a handler must satisfy both:

1. **Never re-define a default that has a row here.** Cite the row from the call site.
2. **Never leave a default stated only in a handler comment.** Add the row. Otherwise a
   consumer reading this table sees no default while a consumer reading the handler sees
   one, which is the drift rule 1 exists to prevent.

| Variable | Inference Rule |
|----------|----------------|
| Project name | Current git repo name (from `git rev-parse --show-toplevel \| xargs basename`), or `cwd` basename. Strip trailing `-`, `_`, `.git` suffix. |
| Install scope | `project` |
| Planwise root | `planwise` |
| Plans directory | `Plans` |
| Backlog directory | `Backlog` |
| Lessons directory | `LessonsLearned` |
| Abbreviation | Derive from plan name: collect initial capitals of each word, pad or truncate to 2-4 chars. If collision detected in plans index, ESCALATE TO CRITICAL (cannot infer safely). |
| Review approach (plan-Part-3-VerifyConfirmAndReview.md Step 10 Q1) | `auto-review in this session` (recommended option) |
| Review context (plan-Part-3-VerifyConfirmAndReview.md Step 10 Q2) | `this session` (unless plan context exceeds heuristic: >3 sprints or >10 task files → `new session`) |
| Lessons capture acknowledgment | `No` — skip the capture prompt and proceed without confirmation. The user can invoke `/planwise lessons capture` separately. |
| Triage route confirmation (backlog.md Phase 4) | Accept the Phase-3 recommended route (`DIRECT_FIX` / `TASK_LIST` / `SESSION_PLANNING`) (in loop mode: the recommended route, A or B; C is never inferred) |
| Follow-up candidate filing (backlog.md Phase 7) | `skip all` — never file a backlog item unattended. The user invokes `/planwise backlog` explicitly to surface candidates. |
| Loop opt-in (backlog.md Phase 2 Q1) | `No` — a single-item session. Looping is an interactive feature. |
| Loop mode / count (backlog.md Phase 2 Q2) | Not reached, because Q1 defaults to `No`. |
| Lessons capture (backlog.md Phase 8, loop mode) | Decide without asking. File a lesson when the iteration surfaced one, and record its id with `backlog_loop.py --mark --lessons`. Otherwise write `No lesson this iteration.` This row replaces the `No` default of "Lessons capture acknowledgment" inside a loop run. |
| Phase 5 approval (backlog.md Phase 5, loop mode) | Every gate passes: mark `COMPLETE`. A gate fails: documented skip, with nothing reverted and the changes left in the working tree. |
| Phase 3 conflict or failed premise (backlog.md Phase 3, loop mode) | A failed existence-premise probe or a scoped-rule verdict `placement`: documented skip, which writes one `### Q{n}.` block under the item's `## Open Questions`, restores the item's pre-loop status and records `SKIPPED` with `user_input_needed`. A scoped-rule verdict `inject` proceeds with the rules injected. Acceptance criteria already met: unattended close, which writes the proof record under `## Resolution` and records `COMPLETE`. |
| Route C or fix-agent `BLOCKED` (backlog.md Phase 4, loop mode) | Documented skip. A Route C re-assessment also writes `needs_plan: true` into the item (`--needs-plan`), marking it for a planning session. A loop run never dispatches a planner to author a session plan. |
| Refine step (backlog-Part-2-LoopMode.md § Refine step, loop mode) | Run the three dispatches; a QUESTIONS design is written into the item's ## Open Questions and the item is skipped with --note; nothing is asked |
| Follow-up candidate filing (backlog.md Phase 7, loop mode) | File none. Print each candidate in the iteration summary. |
| Held-item notice (backlog.md Phase 2, loop mode) | Not reached. The loop queue never holds a `BLOCKED` item. |
| Answer open questions (`backlog.md --answer`, Part 3) | Critical. Auto Mode lists the unanswered questions and asks nothing. No answer is inferred. |
| Reciprocal-edge migration questions (upgrade.md Step 2.3b) | Answer nothing. Write no answers file and run Step 2.4 without `--migration-answers`. An edge direction cannot be inferred safely. The migrator refuses only the unanswered family and writes nothing for it, and the chat summary names that family as action required. |
| Stale mirror prune question (upgrade handler, orphaned agent mirrors banner) | Do not prune. Deleting files is never inferred. The `REMOVABLE` rows stay in place and the banner keeps listing them. |
| Plan status anomaly question (upgrade handler, Plans anomalies) | Keep the status as is. The inference is logged and the anomaly stays reported. |
| Feedback drafts level (upgrade.md Step 1.6) | `notify`, written by the writer only into an existing `feedback:` block that lacks the key. The inference is logged. |
| Feedback drafts posting opt-in (upgrade.md Step 1.6) | Unchanged. `feedback.enabled` is never set by inference. Posting stays opt-in. |
| Feedback drafts level (init.md Step 1, and every `--auto-from` init) | `notify`, the template value. No `--feedback-drafts` flag is passed. The inference is logged, and `init_project.py` prints the value it read back on its `Feedback keys:` line. |
| Feedback drafts posting opt-in (init.md Step 1, and every `--auto-from` init) | `false`, the template value. `feedback.enabled` is never set by inference, so no `--feedback-enabled` flag is passed. Posting stays opt-in. |
| Transfer file delete question (upgrade-Part-3 Step 4.1 case C) | Skip. A transfer file may hold the only copy of a customization, so an unattended run never deletes one. Delete only on an explicit yes. |
| Upgrade leftover prune question (upgrade-Part-3 Step 4.3, and doctor-Part-2 Stage 14b) | Skip every class. Deleting files is never inferred, and each class is asked on its own. Nothing under an unconfirmed class is touched. |
| Settings grant normalization question (upgrade-Part-3 Step 4.4) | Report only. Print the report and the target value, and change no settings file. Rewriting `additionalDirectories` changes the user's file-access grants. |
| GitHub CLI install question (upgrade-Part-3 Step 4.5) | No. Install nothing. An unattended run never invokes a package manager. |
| Task-tools env var question (upgrade-Part-3 Step 4.6) | Report only. Print the report and change no settings file. An unattended run never rewrites `env`. |
| Thrifty-sonic env var question (upgrade-Part-3 Step 4.7) | Add the key for a file classed `missing`. Report only for a file classed `wrong value` or `invalid JSON`. Adding an absent key to `env` removes nothing and sets the value the init writer sets for every new project. Replacing a value the user set is not additive, so it needs a yes. |
| Feedback directory creation question (doctor-Part-2 Stage 17b) | Skip. Leave the directory absent and repeat the Stage 17 remedy line. |

The only questions a loop run asks after setup are Q1, Q2, Q3 (in `specific` mode) and the HALT question for an item that died mid-work.
