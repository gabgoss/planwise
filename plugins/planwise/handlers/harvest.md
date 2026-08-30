# Handler: /planwise harvest

**Purpose:** Run the lesson-to-artifact chain end to end, unattended: categorise documented lessons into their domain buckets, promote them in batch into backlog items, process each resulting item through the triage handler, then land the lessons whose owning items shipped.

The chain is four ordered stages. The order is forced, not conventional: the final stage cannot land a lesson until the per-item stage has flipped its owning item to COMPLETE.

1. **Categorise** — sync the categorisation file and refine each lesson's promotion target. Halts, without modifying any file, if any lesson's bucket assignment is ambiguous. The halt is deliberately conservative: an unresolved lesson either blocks the promote stage outright or drops silently out of a narrowed scope, and this command does not assume which, so it stops rather than promote a set the user did not see.
2. **Promote** — resolve the scope, group by bucket, draft the item files and index rows, then capture each lesson (archive-on-capture). Never self-heals a lesson whose bucket is unknown.
3. **Process** — for each item this run created, pre-flight its frontmatter, triage it, route it, dispatch a foreground agent, verify, and write status centrally. A per-item failure is logged and the loop advances.
4. **Land** — set the final status and artifact pointer on every lesson whose owning item reached COMPLETE, and append the promotion-log row. Heal candidates are reported, never actioned.

This command makes no commits. Every change it lands sits in the working tree for a single aggregate review at the end of the run.

**Invocation examples:**
```
/planwise harvest
/planwise harvest --all-documented
/planwise harvest --category=<bucket>
/planwise harvest --dry-run --all-documented
/planwise harvest --resume
/planwise harvest --include-existing --max-items=8
/planwise harvest --no-auto-approve --all-documented
```

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue. Extract `plugin_root` and `project.planwise_root`. The lesson, categorisation, and backlog index locations each resolve via their own established config keys — the same keys the triage and lessons handlers already use — so no new keys are introduced here.
3. If NOT found: announce, resolve `{plugin_root}` from handler location, invoke `init_project.py` with `--auto-from "harvest"`, RE-RESOLVE, fail loud if still missing.

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed, DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise harvest." STOP.

This unresolved-or-malformed case is HC1 (Halt Conditions, below): nothing later in the chain can be scoped without a valid config, so this gate fires before any stage runs, and — in Auto Mode — never asks a question of its own; it calls the init script directly.

All directory paths resolve as `{planwise_root}/{dir_name}`.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

**Required for this handler:**
- [`references/auto-mode-policy.md`](../references/auto-mode-policy.md) — the canonical gate-tagging convention: critical call-sites emit a `[!gate]` block and fail loud on auto-denial; convenience call-sites ask nothing, apply the inferred default, and log the inference. Every call-site in the Gate Call-Sites step below follows it.
- [`references/agent-orchestration-delegated.md`](../references/agent-orchestration-delegated.md) — the foreground-only dispatch gate and the per-item dispatch discipline the Process stage runs under.
- [`references/verify-backlog-citation-freshness.md`](../references/verify-backlog-citation-freshness.md) — the preflight Route A re-verifies an item's affected files against before dispatch, rather than copying them from the item file.
- [`references/artifact-self-containment.md`](../references/artifact-self-containment.md) — the grep gate Route A's VERIFY step runs unconditionally against any diff touching a content-bearing artifact.

---

## Workflow

### Step 1: Argument Surface & Work-Set Boundary

```
/planwise harvest [<scope>] [--dry-run] [--resume] [--max-items=N]
                  [--include-existing] [--no-auto-approve]
```

| Argument | Default | Behaviour |
|---|---|---|
| `<scope>` | none — bare invocation is a REPORT | Forwarded **verbatim** to stage 2's batch-promote: `--all-documented`, `--category=<bucket>`, or an explicit comma-separated lesson-id list. This argument discharges inherited gate G1. |
| `--dry-run` | off | Runs every precondition and routing decision, writes NOTHING, and prints the full plan: the lessons stage 1 would categorise, the scope stage 2 would receive, and the items plus the route each would take. No dispatch. |
| `--resume` | off | Detects prior state at each death point (Resume Model, below) and continues. |
| `--max-items=N` | unset (= all items this run created) | Caps the stage-3 loop. **Required — fail loud — whenever `--include-existing` is passed** (call-site H4). |
| `--include-existing` | off | Extends stage 3 to pre-existing `NOT_STARTED` items — deliberately gated behind the mandatory cap, because an unattended pass over a full active backlog is exactly the blast radius a user must size deliberately. |
| `--no-auto-approve` | off (auto-approve is ON) | Disables the advance consent that discharges call-site H8 (Auto-Approve Constraint, below). |

**Bare invocation** is neither a no-op nor a full run: it is a **read-only corpus report** — the uncategorised-lesson set, whether the batch-promote categorisation gate would fail-stop, the count of active `NOT_STARTED` items, and the exact invocation to run next. This makes the critical gate's fail-loud path useful rather than obstructive.

**Work-set boundary (decided):** by default stage 3 processes ONLY the items stage 2 created this run — the chain is lesson → artifact, so the coherent unit is the items the lessons just produced. `--include-existing` widens it (see the argument table above).

### Step 2: Gate Call-Sites (H1–H8)

The canonical policy's Inline Tagging Convention applies: critical sites emit a `[!gate]` block, ask the question, and on auto-denial fail loud naming the inline argument; convenience sites ask nothing, apply the inferred default, and log the inference. Each call-site below carries its required inline marker immediately before the block or line that documents it — a corpus compliance sweep greps that marker, not the Tag column here.

| # | Call-site | Tag | Inline argument (critical) / Inference rule (convenience) |
|---|---|---|---|
| H1 | No scope supplied and `--dry-run` not passed | critical | `<scope>` |
| H2 | Stage 1 finds an ambiguous bucket assignment | critical | None is safe — fail loud naming the lessons; the user resolves via one interactive categorize pass, then `--resume` |
| H3 | An id-list scope spans buckets | critical | Re-issue with `--category=<bucket>` or `--all-documented`, or split per bucket |
| H4 | `--include-existing` without `--max-items=N` | critical | `--max-items=N` |
| H5 | Per-item route confirmation | convenience | Accept the recommended route |
| H6 | Create-item-from-follow-up-candidate | convenience | Skip all — never auto-create unattended; the source follow-up callout survives on disk |
| H7 | End-of-triage lesson capture | convenience | No |
| H8 | Diff approval before landing a fix | critical | Advance consent is the default — the answer is supplied by this command's own contract, not by a flag (Auto-Approve Constraint, below) |

<!-- AUTO-MODE: critical -->
> [!gate] User Decision Required
> Auto Mode cannot infer this value. Manual input required.
> Re-issue the command with the answer inline, or run interactively.
> Question: Which lessons should be promoted? Supply a scope:
> `--all-documented`, `--category=<bucket>`, or an explicit id list.

<!-- AUTO-MODE: critical -->
> [!gate] User Decision Required
> Bucket assignment is ambiguous for: {list}. Auto Mode cannot infer a bucket
> safely, and an unresolved lesson either blocks the promote stage or drops
> silently out of a narrowed scope — so this run stops instead of promoting a
> set you have not seen. Resolve with one interactive
> `/planwise lessons curate --phase=categorize`, then re-run with `--resume`.

<!-- AUTO-MODE: critical -->
> [!gate] User Decision Required
> The supplied id list spans multiple buckets, and merge-vs-split cannot be
> inferred. Re-issue with `--category=<bucket>` or `--all-documented`, or split
> into one invocation per bucket.

<!-- AUTO-MODE: critical -->
> [!gate] User Decision Required
> `--include-existing` extends this run beyond the items it created to every
> open item in the backlog. Re-issue with `--max-items=N` to size the pass.

<!-- AUTO-MODE: convenience -->
<!-- Default: Accept the Phase-3 recommended route -->
**H5.** No question is asked; the recommended route from the routing phase is accepted automatically and the inference is logged.

<!-- AUTO-MODE: convenience -->
<!-- Default: Skip all -->
**H6.** An item is never auto-created from a follow-up candidate found during triage; the source follow-up callout is left on disk for a later interactive pass.

<!-- AUTO-MODE: convenience -->
<!-- Default: No -->
**H7.** The end-of-triage capture question defaults to declining — this command's own stage 4 is what captures and lands lessons; the per-item triage pass does not capture on its behalf.

**Inherited gates that never fire in this handler:** the single-lesson promote/capture gates (this command uses batch-promote and never invokes single-lesson capture); the no-args select sub-case (an item id is always supplied); the config-gate collection question (the Auto-Mode branch calls the init script directly, per the Config Gate above); the heal gate (stage 4 never attempts a heal); the scoped-rule gate, which never prompts here — it auto-escalates directly to Route C (Failure Classification, below).

### Step 3: Auto-Approve Constraint (H8)

<!-- AUTO-MODE: critical -->
> [!constraint] The Diff-Approval Gate Is Answered In Advance
> The diff-approval gate before landing a fix is genuinely critical: build/test cleanliness and the self-containment grep catch broken builds, failed tests, and identifier leaks — **not** "this diff is semantically wrong," which only a human judges. Unattended execution is legitimate because the canonical remedy for a critical question is to answer it in advance, inline: invoking `harvest` at all IS that answer, ON by default, because the fixed design decision makes the direct-fix routes auto-executing.
>
> **The bounding safety property: `harvest` makes no commits, ever.** A wrongly-approved fix is a working-tree change, reviewable and revertible in one aggregate `git diff` at run end — never a data-loss event.
>
> **Residual risk, accepted:** a diff that builds, passes tests, and leaks no identifiers, but is semantically wrong, lands in the working tree unreviewed until that aggregate review.
>
> `--no-auto-approve` trades the risk away: each item is fixed, verified, then reverted (`git checkout -- {files}`); its status is left `NOT_STARTED` with a Notes line recording that it verified clean and awaits interactive approval.
>
> There is no bare approve flag — auto-approval is the default, and `--no-auto-approve` is its only opt-out.

### Step 4: Stage Contract

#### Stage 1: Categorise

- **Precondition:** none — always runs first.
- **Action:** compute the uncategorised set (documented lessons minus already-categorised lessons), append bucket rows to the categorisation file, and refine each lesson's promotion target.
- **Failure:** HALT (call-site H2) on any ambiguous bucket assignment — no partial-proceed. This is HC2: the batch-promote categorisation precondition is specified more than one way across the workflow it feeds — under a corpus-wide reading, proceeding is illegal; under a scope-relative reading, it silently promotes a partial set. This command cannot know which reading the live handler implements and must be correct under both, so it halts rather than guess.
- **Writes:** the categorisation file only (rows appended, promotion targets refined) — no lesson file, no item file.

#### Stage 2: Promote

- **Precondition:** the categorisation gate is clear — stage 1 clearing it is what makes this stage legal.
- **Action:** resolve the scope argument (forwarded verbatim to batch-promote) → group by bucket → draft item files and index rows → capture each lesson (archive-on-capture).
- **Failure:** HALT if the categorisation gate still fires after stage 1 (HC3 — self-heal is explicitly forbidden; no legal action remains) or on call-site H3 (an id-list scope spanning buckets).
- **Writes:** item files, backlog index rows, archived lesson files.
- **Delegated drafting:** batch-promote dispatches [`agents/backlog-author.md`](../agents/backlog-author.md) per bucket to draft and file the item files and index rows. That agent is the **one** agent in this pipeline that writes the backlog index itself, so it is dispatched **once per bucket, never concurrently with another instance** — two dispatches race on the index file and on the next-free-id computation. Lesson capture (status flip, archive move, lessons-index update) stays with this stage; the agent never touches a lesson file. `--dry-run` skips the dispatch entirely rather than dispatching with a no-write flag.

#### Stage 3: Process

- **Precondition:** the work set is resolved (below).
- **Action, per item in the work set:** frontmatter pre-flight (Step 8) → triage → route → dispatch a foreground agent → verify → central status write.
- **Failure:** a per-item failure is logged and the loop advances — only the five halt conditions (Step 6, below) stop the run.
- **Writes:** per item, whatever the routed agent produces, plus the single central backlog-index status write for that item.

**Work set (decided):** the union of `promoted-to:` values across the lessons stage 2 archived this run — re-derivable from disk with no bookkeeping at all — extended to pre-existing `NOT_STARTED` items only under `--include-existing` (which requires `--max-items=N`, call-site H4).

**Per-item dispatch contract.** Dispatch is foreground-only for every write-producing agent (the fix agent, `backlog-planner`) — never `run_in_background: true`, never `background: true` in frontmatter; a background subagent auto-denies Write/Edit/Bash silently. Per the delegated-orchestration reference's own table: file output → foreground; shell → foreground; read-only research → background OK. Foreground does not mean sequential: parallel-foreground via multiple dispatch calls in one turn is live precedent.

- Sequential-foreground for 1–2 items, or any edit-target collision (the same source file, or the shared index).
- Parallel-foreground for 3+ independent items with disjoint targets — multiple dispatch calls in one turn.
- **Batch cap: 4, fixed.** The empirical disjoint-write cap; raising it on an untested delta-return argument was explicitly rejected.

**Acceptance gate on every return:** verify each declared output file exists on disk BEFORE accepting a success-claiming return. Narrowed to returns that both claim success AND declare files — an honest BLOCKED with no files is not the signature; a COMPLETE declaring absent files IS, and is HC4.

**Central index write:** neither dispatched agent writes the backlog index itself; each returns a status-block delta (below), and this stage applies the single shared write after each item. This holds for stage 3's two agents (the fix agent and `backlog-planner`) and is unchanged. It does **not** describe stage 2's `backlog-author`, which owns its own index write by design — the reason that agent is dispatched one instance at a time.

**Status-block field set** (every per-item dispatch returns; verbatim):

```
TASK_STATUS:      COMPLETE | BLOCKED
TASK_ID:          {item id}
ROUTE:            A | B | C
OUTPUT_FILES:     {comma-separated absolute paths written, or none}
LINES_PRODUCED:   {sum across OUTPUT_FILES}
VERIFY_RESULT:    clean | build-failed | test-failed | grep-hits | n/a
KEY_FINDINGS:     {2-5 short bullets}
ISSUES:           {one line per issue, or "none"}
```

Route C adds `PLAN_PATH`, `PLAN_MODE: standard | meta-deferred`, `REVIEW_REQUESTED: true | false` (false only when BLOCKED).

**Route behaviour:**
- **Route A** spawns the fix agent with six fields: item id, summary, and description (from the item file); **affected files re-verified via the citation-freshness preflight, never copied** from the item file — under automation, no human catches a stale path; the build command resolved once from `config.yaml`'s `build_commands.default` at Config-Gate time; cross-cutting candidates from the item's own sections (default "none identified").
- **Route B** reuses the same agent and contract — a scope-assessment distinction from Route A, not an execution one. Its internal steps are tracked as sequential tool calls inside the single dispatch, never through the shared harness task list (session-wide state would race across concurrent dispatches).
- **Route C** dispatches the `backlog-planner` agent ([`agents/backlog-planner.md`](../agents/backlog-planner.md)) with the item's own scope. The agent authors a session plan, reports it ready for review, and stops — it never executes the plan and never writes the backlog index. This stage runs the review on the fresh plan and applies the resulting verdict: an approved plan advances the item to `PLANNING`; a verdict requiring fixes is logged and the item stays `PLANNING` unapproved, not auto-retried.
- **Route C standing limitation:** an `APPROVED` verdict does **not** certify destructive-path safety. The review flow spawns no sub-role that audits a plan's destructive dispositions, so an approved plan may still carry a delete/overwrite/prune path nobody assessed. This is a documented limitation of the review contract, not something this command fixes — treat `APPROVED` as "the plan is well-formed", never as "the plan is safe to run unattended".
- **Escalation cascade:** A → (fail) → C → (fail) → skip + log + advance. A BLOCKED fix-agent's Route-C offer is auto-accepted — the human's role there was confirmation, not judgment. Route C is the end of the cascade; nothing escalates past it.
- **Route A VERIFY:** auto-approve (`COMPLETE`) iff build/test are clean AND — when the diff touches a content-bearing artifact under the rules/agents/skills/commands trees or the project instructions file — the self-containment grep gate returns zero; that gate is unconditionally binding regardless of Auto Mode. A failed VERIFY reverts (`git checkout -- {files}`, status → `NOT_STARTED`) — never skips, never halts — then feeds the A→C cascade.
- **Retry cap:** 3 attempts per single dispatch (the existing cap) — distinct from the one-shot route escalation above.

#### Stage 4: Land

- **Precondition:** an item reached COMPLETE this run — stage 3's central write is the source of truth.
- **Action:** set the final status and artifact pointer on every lesson whose owning item(s) reached COMPLETE; append the promotion-log row.
- **Failure:** never heals. Heal candidates are detected and reported, never actioned; a lesson whose owner did not complete stays promoted and lands on a later run.
- **Writes:** the lesson file's status and artifact pointer, the promotion-log row. No file moves in this stage.

### Step 5: Failure Classification

| Failure | Handling |
|---|---|
| fix-agent BLOCKED | escalate once to Route C |
| build/test fail | revert + cascade |
| self-containment grep hits | revert + cascade (unconditionally binding) |
| scoped-rule conflict | auto-escalate directly to Route C, skipping A — a placement judgment the mechanical VERIFY cannot backstop (a misplaced-but-valid file builds clean) |
| unparseable item frontmatter | skip + log + advance |
| planner BLOCKED | Notes `AUTO-PLAN FAILED {date}: {reason} — needs manual triage`, status `NOT_STARTED`, advance |
| review verdict requires fixes | log only — never retried in-loop; Route C plans and reviews exactly once |

### Step 6: Halt Conditions

These are a separate numbering from the H1–H8 call-sites above: a halt condition (HC) stops the run outright, where a call-site (H) asks or infers a single value and continues. H3 and H4 above are pre-run argument validations, not halts; one further halt-like condition surfaces only at resume time (death point (c), Resume Model below).

- **HC1 — Config Gate FAIL LOUD, pre-loop.** Nothing can be scoped without a valid config; this halt fires before any stage runs.
- **HC2 — stage-1 ambiguity, before any write.** Correct under both readings of the self-contradicting precondition and keeps the corpus byte-identical until a lesson's bucket is resolved.
- **HC3 — stage-2's categorisation gate still firing after stage 1.** Self-heal is forbidden unconditionally — no legal action remains once the gate persists.
- **HC4 — silent write denial: a success-claiming dispatch return with declared-but-absent output files.** The dispatch mode itself is broken; every remaining item in the batch would "succeed" identically, so the run stops rather than compound the failure.
- **HC5 — backlog-index write failure (the central-write script exits non-zero).** Continuing corrupts bookkeeping for the whole remainder of the run.

### Step 7: Resume Model

**Run-state file: `{planwise_root}/.harvest-run.json`** — a fixed convention derived from the existing planwise-root value; no new config key, no template edit, no migrate consequence, no manifest row (the manifest tracks config-driven deployment artifacts, not runtime output). Written at every stage boundary and after every item: run id, scope as given, current stage, per-lesson capture status, and per-item `{route, dispatch-issued, verify-outcome, final-status}`.

| Death point | Primary signal | Fallback with no run-state file |
|---|---|---|
| (a) between stages 1–2 | none needed | **No gap** — stage 1 is a no-op re-run by construction (the diff computation); secondary check: `promotion-target:` set while status still shows the lesson as documented |
| (b) mid-stage-2 after some captures | a stage-2 phase marker recording that item-drafting completed → **never re-enter the drafting phase** | Two-signal conjunction (planned item files present AND some lessons still documented) ⇒ drafting done, capture partial — resume remaining captures; **the inference MUST be printed**, never applied silently |
| (c) at item N of stage 3 | the per-item sub-phase record | **HALT and report the ambiguous item** — an in-progress status alone cannot distinguish the sub-phase (nothing is written between the flip in and the flip out; a clean tree is doubly ambiguous), and both guesses are wrong in a recoverable-looking way: re-dispatching compounds an unreviewed diff; skipping drops a died-before-routing item |
| work set | run-state `items[]` | Always re-derivable: the union of `promoted-to:` across the lessons stage 2 archived — holds with no bookkeeping at all |

**Idempotency:** stage 1 by construction; stage 2's drafting phase is NOT idempotent (re-entering re-drafts and re-numbers — exactly what the phase marker prevents); stage 3 is idempotent per item given a correct sub-phase; stage 4 is idempotent by precondition (an already-landed lesson's pointer is no longer pending).

### Step 8: Stage-3 Frontmatter Pre-Flight

Before triaging each item, verify its frontmatter parses as YAML. Skip-and-log on failure — never crash the loop. This resilience belongs to this command; the underlying corpus defect (some active items carry no parseable frontmatter at all) is project-side and out of scope here.

**Abbrev-cell preference:** prefer an item's own frontmatter over the backlog index row's Abbrev cell when the two disagree — index rows can carry stale or corrupted cells that the item file itself does not.
