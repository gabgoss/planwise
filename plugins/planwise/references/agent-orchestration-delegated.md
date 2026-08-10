---
description: DELEGATED dispatch discipline — orchestrator protocols (§1.1–§1.22) for spawning task-runner subagents; extracted from agent-orchestration.md §11-§12
---

# DELEGATED Dispatch Discipline

**Purpose:** Operational dispatch protocols for an orchestrator running a DELEGATED session (spawning task-runner subagents). These subsections (§1.1–§1.22) were extracted from [`agent-orchestration.md`](agent-orchestration.md) §11–§12 to keep the core orchestration reference compact on every invocation; they load conditionally when DELEGATED mode is declared.

This file is the complete DELEGATED dispatch discipline: §1.1 Mandatory Triggers, §1.2 Task-File Error Recovery, and §1.3 Orchestration Context Boundary establish the foundation; §1.4–§1.17 cover the full dispatch protocols; §1.18 covers verify-before-acting on LSP diagnostics; §1.19–§1.22 cover DELEGATED task-runner dispatch mechanics — model-tier overrides, launch-mode gating, and an anti-patterns checklist. [`agent-orchestration.md`](agent-orchestration.md) §11 retains only a short pointer stub back to this file — the full text lives here.

## Table of Contents

- [1.1 Mandatory Triggers](#11-mandatory-triggers)
- [1.2 Task-File Error Recovery](#12-task-file-error-recovery)
- [1.3 Orchestration Context Boundary](#13-orchestration-context-boundary)
- [1.4 Inter-Dispatch Diagnostics Verification](#14-inter-dispatch-diagnostics-verification)
- [1.5 Live-HTTP-Probing Tool-Use Budget Reservation](#15-live-http-probing-tool-use-budget-reservation)
- [1.6 Path-Scoped Rule Injection in Spawn Prompts](#16-path-scoped-rule-injection-in-spawn-prompts)
- [1.7 Idle-Mid-Step Wake-Up via SendMessage](#17-idle-mid-step-wake-up-via-sendmessage)
- [1.8 HARD CONSTRAINTS Spawn-Prompt Skeleton + SCOPE BOUNDARY Clause](#18-hard-constraints-spawn-prompt-skeleton--scope-boundary-clause)
- [1.9 Tier-Rank Fixes by Invasiveness](#19-tier-rank-fixes-by-invasiveness)
- [1.10 Forward-Looking-Verb Detection + SendMessage Resume Protocol](#110-forward-looking-verb-detection--sendmessage-resume-protocol)
- [1.11 Operational-Ceiling Disclaimers in Spawn Prompts](#111-operational-ceiling-disclaimers-in-spawn-prompts)
- [1.12 N>25 Edit-Task Resume Protocol with Tool-Use Budget Estimation](#112-n25-edit-task-resume-protocol-with-tool-use-budget-estimation)
- [1.13 Shared-Edit-Target Strategy Matrix](#113-shared-edit-target-strategy-matrix)
- [1.14 Orchestrator-Only Review Commands](#114-orchestrator-only-review-commands)
- [1.15 Delegated Code Task-Runners Build LAST](#115-delegated-code-task-runners-build-last)
- [1.16 Recompute Delegated Verdicts from Primary Evidence — Both Directions](#116-recompute-delegated-verdicts-from-primary-evidence--both-directions)
- [1.17 Task-Runner Dispatch Failure Modes and Resume Protocol](#117-task-runner-dispatch-failure-modes-and-resume-protocol)
- [1.18 Verify-Before-Acting on LSP Diagnostics](#118-verify-before-acting-on-lsp-diagnostics)
- [1.19 Model-Floor Bridge (DELEGATED) — Temporary](#119-model-floor-bridge-delegated--temporary)
- [1.20 1M-Exception Dispatch (DELEGATED) — Token Saver](#120-1m-exception-dispatch-delegated--token-saver)
- [1.21 Background vs Foreground Gate](#121-background-vs-foreground-gate)
- [1.22 Delegated Mode Anti-Patterns Checklist](#122-delegated-mode-anti-patterns-checklist)

---

## 1.1 Mandatory Triggers

DELEGATED mode is REQUIRED when any of the four mandatory triggers is present in a session. The triggers — 2 or more Opus tasks, participation in a META Discovery phase, any single task estimating >50K token context load, or output-chaining between sequential tasks — are normatively defined at [`session-plan-requirements.md`](session-plan-requirements.md) § Execution Strategy (Set by Planner); this section cites that list rather than restating it.

**The Master Plan's Execution Strategy section MUST name the trigger that fired for every DELEGATED session, and `/planwise review` MUST surface as a BLOCKING finding any DELEGATED declaration without a named trigger.**

Declaring DELEGATED is a PLANNING decision (made in the Orchestration file), not an execution-time inference.

> [!constraint] DELEGATED Declaration — Planning Time Only
> WRONG — orchestrator infers DELEGATED at runtime after reading context:
> ```
> # Orchestration file: Execution Strategy: DIRECT
> # (then orchestrator discovers tasks are too large and pivots at runtime)
> ```
> CORRECT — planner declares DELEGATED trigger in Orchestration before execution:
> ```
> ## Execution Strategy
> Mode: DELEGATED
> Trigger: Task 03 estimates >50K context load (output-chaining to Task 04)
> ```

> [!constraint] Name the Trigger — Not "For Consistency"
> "Consistency" across a multi-session plan is not a trigger; every DELEGATED session must name one of the four mandatory triggers above.
> WRONG: plan declares DELEGATED for all 8 sessions "for consistency"; only Sprint 01 meets a trigger (95K Opus task + output-chaining); Sprints 02-08 each have a single 23-41K task within the 100K DIRECT budget — ~378K of subagent-spawn overhead consumed for no gain.
> CORRECT: Sprint 01 declares DELEGATED (#1 + #4); Sprints 02-08 declare DIRECT.

## 1.2 Task-File Error Recovery

When a DELEGATED subagent fails or produces incomplete output, the orchestrator applies this recovery shape:

1. Read the subagent's partial output (from its output file or Recovery file)
2. Assess whether partial output is usable as-is or requires retry
3. If retry needed: spawn a new subagent with explicit "resume from step N" instructions
4. Cap retries at 3 attempts per task; after 3 failures mark task BLOCKED in Recovery

> [!constraint] Retry Cap — DELEGATED Task Failure
> WRONG — orchestrator retries indefinitely, consuming budget:
> ```
> (Task fails) → retry → (fails again) → retry → (fails again) → retry...
> ```
> CORRECT — retry cap of 3; after 3 mark BLOCKED and report:
> ```
> Attempt 1: FAILED (output file missing)
> Attempt 2: FAILED (partial output, <50% coverage)
> Attempt 3: FAILED (subagent stopped mid-execution)
> → Mark task BLOCKED in Recovery; report to orchestrator
> ```

## 1.3 Orchestration Context Boundary

When Execution Strategy is DELEGATED:
- Orchestration's Required Context MUST list ONLY plan files (Orchestration.md, Recovery.md, task files)
- Heavy context files (reference docs, codebase modules, large output files) MUST appear ONLY in individual task file Required Context sections
- The orchestrator reads plan files only; subagents read their full task-specific context with fresh ~100K budget

> [!constraint] DELEGATED Context Boundary
> WRONG — Orchestration Required Context loads heavy files (orchestrator context fills before dispatching):
> ```
> ## Required Context
> | 1 | references/agent-orchestration.md | ~440 | ~6K | Rule reference |
> | 2 | src/models/schema.sql | ~1200 | ~15K | Schema for tasks |
> | 3 | Outputs/research-part-1.md | ~480 | ~6K | Research for tasks |
> ```
> CORRECT — Orchestration Required Context contains only plan files; heavy context in task files:
> ```
> ## Required Context
> | 1 | {Abbrev}-S{XX}-{YY}-Orchestration.md | ~80 | ~1K | Task list |
> | 2 | {Abbrev}-S{XX}-{YY}-Recovery.md | ~40 | ~0.5K | Progress state |
>
> (Task 03 Required Context loads schema.sql + research-part-1.md in its own section)
> ```

## 1.4 Inter-Dispatch Diagnostics Verification

When DELEGATED dispatches modify shared files (e.g., a shared algorithm module or schema file), the orchestrator MUST independently run the project's primary diagnostic command between dispatches to verify no regression:

- Run `{lint-cmd}` (or equivalent) on the shared file after each dispatch that modifies it
- Run `{precheck-cmd}` if the shared file is a data-layer contract (schema, config)
- If diagnostics fail: halt subsequent dispatches; surface the failure in Recovery before retrying

**Orchestrator `wc -l` verification:**

After each dispatch that produces output files, the orchestrator MUST run `wc -l` on every output file and compare against the Expected Output line budget declared in the task file. Deviations >20% from the declared budget are a signal to review before proceeding to the next dispatch.

> [!constraint] Inter-Dispatch Diagnostic Check
> WRONG — orchestrator dispatches all tasks in sequence without diagnostics between:
> ```
> Dispatch Task 01 → (completes) → Dispatch Task 02 → (completes) → Dispatch Task 03
> (no diagnostic check; regression from Task 01 propagates silently to Task 03)
> ```
> CORRECT — orchestrator runs diagnostics on shared files between dispatches:
> ```
> Dispatch Task 01 → run {lint-cmd} {src/module/file.ext} → CLEAN → Dispatch Task 02
> Dispatch Task 02 → run {lint-cmd} {src/module/file.ext} → 2 errors → HALT → fix before Task 03
> ```

## 1.5 Live-HTTP-Probing Tool-Use Budget Reservation

When a DELEGATED subagent performs live HTTP probing (WebFetch/WebSearch calls in a loop), the orchestrator MUST reserve tool-use budget for this activity:

- Cap: 30 WebFetch/WebSearch calls per dispatch (not per session)
- Recovery point: archive fetched bodies to disk (output file) after each successful fetch; if dispatch fails mid-probe, the archive allows resuming without re-fetching
- Spawn prompt MUST declare the probe ceiling explicitly: "Your WebFetch budget for this dispatch is 30 calls."

> [!practice] HTTP Probe Budget Declaration
> Include in every dispatch prompt that involves HTTP probing:
> ```
> **Tool-Use Budget:** Maximum 30 WebFetch/WebSearch calls in this dispatch.
> Archive each successful fetch response to `Outputs/{Abbrev}-{task-id}-Probe-Archive.md`
> before proceeding to the next URL. If you hit the budget ceiling, stop and report
> what was fetched and what remains.
> ```

## 1.6 Path-Scoped Rule Injection in Spawn Prompts

Path-specific rules (rules with `paths:` frontmatter patterns) do NOT automatically load for spawned subagents — spawned contexts start with zero file activity and inherit no path triggers from the parent. When a DELEGATED task requires path-specific rules, the orchestrator MUST inject those rule contents explicitly into the spawn prompt.

> [!constraint] Path Rule Injection
> WRONG — orchestrator assumes subagent will load path rules automatically:
> ```
> Task(
>   subagent_type: "general-purpose",
>   prompt: "Execute {Abbrev}-S01-02-01-Haiku-ScanModels.md — the relevant rules will load automatically."
> )
> ```
> CORRECT — orchestrator injects path-rule content or file reference explicitly:
> ```
> Task(
>   subagent_type: "general-purpose",
>   prompt: "Execute {Abbrev}-S01-02-01-Haiku-ScanModels.md.
>   IMPORTANT: The following path-scoped rule applies to {src/module/file.ext} files:
>   [paste rule content or file reference here]"
> )
> ```

## 1.7 Idle-Mid-Step Wake-Up via SendMessage

Teammates (in agent team mode) go idle after every turn. This is NORMAL — idle does not mean stopped. When a teammate is idle mid-step (has more work to do but has not been prompted for the next step), the orchestrator sends a wake-up message:

```
SendMessage(
  type: "message",
  recipient: "{teammate-name}",
  content: "Continue from where you stopped. Your remaining work: {bullet list of remaining items from task file}.",
  summary: "Wake-up: continue task execution"
)
```

> [!pitfall] Idle Teammate Mid-Task
> **Problem:** Teammate completes step N and goes idle, waiting for acknowledgment before proceeding to step N+1. Lead session treats idle as "done" and marks task complete.
> **Solution:** After receiving partial results from a teammate, check whether the task file has more steps. If yes, send a continuation message. Only treat idle as "done" when the task file's final step is confirmed complete.

## 1.8 HARD CONSTRAINTS Spawn-Prompt Skeleton + SCOPE BOUNDARY Clause

Every DELEGATED spawn prompt MUST include a HARD CONSTRAINTS section and a SCOPE BOUNDARY clause:

```markdown
## HARD CONSTRAINTS (non-negotiable)
1. Modify ONLY files listed in this task's Required Context — no other files
2. Do NOT read files not listed in Required Context
3. Do NOT spawn sub-agents or create teams
4. If you encounter an ambiguity requiring a file not in Required Context, STOP and report it; do NOT expand scope

## SCOPE BOUNDARY
This task operates within:
- **In scope:** {list of files/modules this task modifies}
- **Out of scope:** {list of adjacent files/modules this task must NOT touch}
```

> [!constraint] HARD CONSTRAINTS Presence
> WRONG — spawn prompt omits HARD CONSTRAINTS; subagent reads adjacent files and expands scope:
> ```
> "Execute task file {Abbrev}-S02-01-03-Sonnet-GenEntities.md. Good luck!"
> ```
> CORRECT — spawn prompt includes HARD CONSTRAINTS and SCOPE BOUNDARY:
> ```
> "Execute task file {Abbrev}-S02-01-03-Sonnet-GenEntities.md.
>
> ## HARD CONSTRAINTS (non-negotiable)
> 1. Modify ONLY the files listed in the task's Required Context...
> [full HARD CONSTRAINTS + SCOPE BOUNDARY block]"
> ```

## 1.9 Tier-Rank Fixes by Invasiveness

When a DELEGATED task produces results requiring fixes, rank the fixes by invasiveness before dispatching a follow-up:

| Tier | Fix Type | Invasiveness | Dispatch Approach |
|------|----------|--------------|-------------------|
| Tier 1 | Comment / doc update | Low | Inline in continuation message |
| Tier 2 | Single-file logic fix | Medium | New targeted dispatch |
| Tier 3 | Multi-file refactor | High | New session with full context |

Start with Tier 1 fixes before escalating; do not over-dispatch high-invasiveness fixes when lower-tier corrections suffice.

## 1.10 Forward-Looking-Verb Detection + SendMessage Resume Protocol

When reviewing a dispatch's output, scan for forward-looking verbs in the last paragraph ("will", "next I will", "the following step will", "planned"). These signal the subagent stopped mid-task and intends to continue but has gone idle.

**Resume protocol:**
```
SendMessage(
  type: "message",
  recipient: "{task-runner}",
  content: "You said you would {forward-looking action}. Please continue now. Resume from your last completed step.",
  summary: "Resume: forward-looking task continuation"
)
```

> [!pitfall] Forward-Looking-Verb Tail
> **Problem:** Subagent ends its turn with "I will next write the schema pin" but goes idle. Orchestrator reads output and marks task complete without checking for completion.
> **Solution:** Grep the last 3 paragraphs of every dispatch output for `\b(will|next I will|the following step will|planned to)\b`. If found, send a resume message rather than marking COMPLETE.

## 1.11 Operational-Ceiling Disclaimers in Spawn Prompts

Spawn prompts for tasks approaching operational ceilings (>25 file edits, >30 HTTP probes, >100K expected context) MUST include an operational ceiling disclaimer:

```markdown
## Operational Ceiling Notice
This task approaches operational ceilings:
- **Edit ceiling:** ~{N} file edits expected (ceiling: 25 per dispatch)
- **Context ceiling:** ~{X}K expected context load
If you reach a ceiling before completing all steps, STOP, write a partial output file documenting
what was completed and what remains, then signal completion via your final response.
```

## 1.12 N>25 Edit-Task Resume Protocol with Tool-Use Budget Estimation

When a task requires >25 file edits and cannot be split further, use the N>25 Edit-Task Resume Protocol:

1. Estimate tool-use budget: `({N} edits × 2 tool calls/edit) + {M} reads + {K} overhead = {total} tool calls`
2. Declare the estimate in the spawn prompt under Operational Ceiling Notice
3. After dispatch, if subagent reports incomplete: spawn continuation dispatch with "Resume from file {N+1}" instruction
4. Cap continuation dispatches at 3; if still incomplete after 3 dispatches, escalate to orchestrator for redesign

> [!practice] Tool-Use Budget Estimation for Edit-Heavy Tasks
> Before dispatching >25-edit tasks, estimate: `(edits × 2) + reads + overhead`. If total exceeds 80% of model tool-budget ceiling, split the task. Example: 30 edits = 60 edit calls + 20 reads + 10 overhead = 90 tool calls — review against model ceiling before dispatching.

## 1.13 Shared-Edit-Target Strategy Matrix

When N DELEGATED dispatches in a single session must write the same target (a shared content file, or the shared Recovery file all task-runners update), three strategies are available. Choose by the count of concurrent dispatches sharing the target; **Option C (orchestrator-reconciled delta) is the preferred default** because it remains safe at every band and aligns with the recorded parallel-task-runner Recovery practice.

| Concurrent dispatches sharing the target | Strategy | Mechanism |
|------------------------------------------|----------|-----------|
| ≤ 4 | **Option A — Parallelism cap at 4** | Allow up to 4 parallel dispatches on the same target. Empirically, 4-way parallelism converges when edits are to disjoint regions. Beyond 4, escalate to Option B or C. |
| 5 – 6 | **Option B — Recovery / target shards** | Each dispatch writes to its own per-dispatch shard (e.g., `…-Recovery-shard-{N}.md` or a per-dispatch output file). Orchestrator merges shards after all dispatches return. Avoids last-write-wins clobbering at the cost of a merge step. |
| 7 + | **Option C — Orchestrator-reconciled delta (PREFERRED)** | Each dispatch returns its changes as a status block / delta in its final message instead of writing the shared target directly. The orchestrator applies the deltas centrally — single writer, no clobbering, fully auditable. Also valid (and recommended) at lower bands. |

> [!decide] Choose a Shared-Edit-Target Strategy
> | Situation | Strategy |
> |-----------|----------|
> | N ≤ 4 dispatches editing disjoint regions of a content file | Option A — cap at 4 parallel dispatches |
> | 5–6 dispatches sharing a Recovery or content file | Option B — per-dispatch shards, orchestrator merges |
> | 7+ dispatches sharing any target, **or** when in doubt | Option C — dispatches return deltas, orchestrator reconciles centrally |

> [!constraint] Never Run Uncoordinated Parallel Writes to the Same Target
> WRONG — N parallel dispatches write the same shared file with no cap, no shards, no delta reconciliation:
> ```
> Dispatch Task 02 (writes {shared-file}) ─┐
> Dispatch Task 03 (writes {shared-file}) ─┼ parallel, no coordination
> Dispatch Task 04 (writes {shared-file}) ─┘
> # last write wins; earlier dispatches' changes are silently overwritten
> ```
> CORRECT — pick A, B, or C from the matrix above; if uncertain, default to Option C:
> ```
> # Option C example — task-runners return deltas, orchestrator reconciles:
> Dispatch Task 02 → returns "delta: +rows 5-9"   → orchestrator writes
> Dispatch Task 03 → returns "delta: +rows 10-14" → orchestrator writes
> Dispatch Task 04 → returns "delta: +rows 15-19" → orchestrator writes
> ```

### Recovery File in Parallel DELEGATED Dispatch

The §1.13 cap (≤4 parallel for shared targets) addresses **task output files**, not the Recovery file. The Recovery file is a structurally shared edit target for every DELEGATED task-runner in a session — applying the cap to it would wrongly serialize all parallelizable independent tasks.

For Recovery specifically, **Option C is the binding default whenever 3 or more task-runners dispatch in parallel.** Task-runners do NOT touch the Recovery file in this mode; the orchestrator reconciles Recovery centrally after all parallel runners return. This applies regardless of whether each runner's *output* files are disjoint.

> [!constraint] Parallel-Dispatch Recovery Reconciliation
> When dispatching 3+ task-runners in parallel within a single DELEGATED session:
>
> **Task-runner contract (MUST appear in every spawn prompt):**
> ```markdown
> ## PARALLEL DISPATCH — Recovery Handling
> Do NOT read, edit, or write the Recovery file during this task.
> Return your completion as the structured status block below in your FINAL message.
> The orchestrator reconciles Recovery centrally after all parallel runners return.
>
> ## Status Block (required final-message format)
> ```
> TASK_STATUS:   COMPLETE | BLOCKED | PARTIAL
> TASK_ID:       {Abbrev}-S{XX}-{YY}-{##}
> OUTPUT_FILES:  {comma-separated absolute paths actually written}
> LINES_PRODUCED: {sum of lines across output files}
> KEY_FINDINGS:  {2-5 short bullets — preserved across compaction}
> ISSUES:        {one line per issue, or "none"}
> ```
> ```
>
> **Orchestrator contract (single writer):**
> 1. Dispatch all parallel-eligible task-runners (no inter-dependencies among them)
> 2. Wait for ALL to return their status blocks
> 3. Parse each status block; verify referenced OUTPUT_FILES exist on disk
> 4. Write Recovery ONCE: add one Step Completion row per task, append KEY_FINDINGS, append OUTPUT_FILES to the Files Modified section, append a Change Log row per task with a single timestamp window
> 5. Only then advance Current Step and dispatch the next dependency layer
>
> **WRONG — task-runners race on Recovery:**
> ```
> Dispatch Task 03 (parallel) ─┐
> Dispatch Task 04 (parallel) ─┼ each calls Edit on Recovery file
> Dispatch Task 05 (parallel) ─┘
> # last write wins; Task 03 and 04 completion rows are silently lost
> ```
>
> **CORRECT — task-runners return status blocks; orchestrator writes once:**
> ```
> Dispatch Task 03 (parallel) → status block (no Recovery write) ─┐
> Dispatch Task 04 (parallel) → status block (no Recovery write) ─┼─► orchestrator reconciles Recovery once
> Dispatch Task 05 (parallel) → status block (no Recovery write) ─┘
> ```

> [!pitfall] Sequential-Phase Tail After Parallel Dispatch
> **Problem:** A session that runs 3+ parallel runners followed by a single sequential verification task. If the verifier follows the standard Recovery-write protocol (§4 of task-runner contract), Recovery gets written twice — once by the orchestrator's reconciliation, once by the verifier — and the second write may clobber the first if the verifier read Recovery before reconciliation completed.
> **Solution:** Reconcile Recovery centrally BEFORE dispatching the sequential tail. The tail task may then write Recovery directly per the normal §4 protocol — it runs alone, so no race exists.

## 1.14 Orchestrator-Only Review Commands

Slash-commands that themselves spawn review agents (`/simplify`, `/code-review`, and similar multi-agent review skills) CANNOT run inside a task-runner subagent. Per Constraint 1 (`agent-orchestration.md` §10), the Task tool is stripped from all non-main contexts at spawn time, so a subagent has no way to spawn the review agents the command depends on; the call resolves to "Unknown subcommand" or fails silently.

A DELEGATED task-runner does an INLINE self-review — it applies the review lenses itself, with no agent spawn. The orchestrator (running in the main session) invokes the real review command on the diff after the task-runner returns, before commit.

> [!constraint] Do Not Instruct a Task-Runner to Invoke Orchestrator-Only Commands
> WRONG — spawn prompt instructs the task-runner to run a slash-command that itself spawns review agents:
> ```
> Task(
>   subagent_type: "planwise:task-runner",
>   prompt: "...implement X; build; then run /simplify"
> )
> # task-runner: "Unknown subcommand: simplify" — it cannot spawn the review agents.
> ```
> CORRECT — task-runner applies the review lenses inline; orchestrator runs the real review command on the diff after:
> ```
> Task(
>   subagent_type: "planwise:task-runner",
>   prompt: "...implement X; apply the review lenses INLINE yourself — do NOT invoke /simplify or /code-review, you cannot spawn the review agents"
> )
> # orchestrator, after task-runner returns: Skill(code-review) (or /simplify) on the diff.
> ```

## 1.15 Delegated Code Task-Runners Build LAST

In a DELEGATED code task, the build/verification command is the FINAL step — after any inline self-review edits. This guarantees the reported build result reflects what is actually on disk. A task-runner that builds, then edits, then reports "build clean" has published a stale verification: the build predates the final code, and any post-build edit could silently invalidate the gate.

If the task-runner edits after building (whether by accident or because the spawn prompt allowed it), the orchestrator MUST re-run `{build-cmd}` on the final on-disk code before trusting the gate and before commit.

> [!constraint] Build/Verification Is the Final Step in a Delegated Code Task
> WRONG — build, then refactor, then report (verified build no longer matches on-disk code):
> ```
> 1. write code  2. run {build-cmd} (CLEAN)  3. apply self-review edits  4. report "CLEAN"
> # The reported result is from step 2; step 3's edits are unverified.
> ```
> CORRECT — refactor first, build last, so the reported result matches what is on disk:
> ```
> 1. write code  2. apply self-review edits (inline review lenses)  3. run {build-cmd} LAST  4. report
> # If the agent edits after building despite the prompt, the orchestrator re-runs {build-cmd} on the
> # final on-disk code before trusting the gate.
> ```

## 1.16 Recompute Delegated Verdicts from Primary Evidence — Both Directions

Any session that delegates structured classification — a verdict label, a severity tag, a readiness state — to a sub-agent MUST recompute that classification from the agent's reported raw evidence before consuming the label. Two failure modes bound the gap symmetrically: **under-classification** (the sub-agent softens the verdict against its own enumerated counts) and **over-classification** (the sub-agent manufactures a finding on incomplete cross-file evidence). Capability does not prevent either — a smaller-tier agent (e.g. Sonnet) systematically under-classifies, and a frontier-tier agent (e.g. Opus) can over-classify on cross-file control-flow claims; the rule applies to ALL agent tiers and must not be scoped to one model. The orchestrator, holding the full evidence set, is the only reliable recompute site.

### 1.16.1 Under-classification — recompute verdict from finding counts

In one observed 13-way parallel dispatch, 8 of 13 sub-agents wrote a final verdict line that did not match the classification rule applied to their own enumerated counts; every error softened severity (e.g. BROKEN=2 reported as `YELLOW` instead of `RED`). The aggregate as-reported severity mix understated the canonical mix enough to mis-classify release-blocking findings as negotiable. The orchestrator must recompute the label from the counts, never read it off the agent's summary line.

> [!constraint] Recompute the Verdict from the Reported Counts
> WRONG — orchestrator trusts the verdict line:
> ```
> verdict = read_verdict_line(findings_file)  # may be wrong
> roll_up_to_release_blocker_table(verdict)
> ```
> CORRECT — orchestrator recomputes from counts:
> ```
> counts = read_finding_counts(findings_file)
> verdict = "RED" if counts.broken + counts.contradiction > 0 \
>      else "YELLOW" if counts.drift + counts.missing > 0 \
>      else "GREEN"
> roll_up_to_release_blocker_table(verdict)
> reported = read_verdict_line(findings_file)
> if reported != verdict:
>     log_meta_finding(f"sub-agent verdict mis-classification: reported={reported}, canonical={verdict}")
> ```

Scope note: this applies to any structured-classification dispatch — GREEN/YELLOW/RED verdicts, MUST_FIX/SHOULD_FIX/DEFER labels, BLOCKER/ERROR tags, or readiness states.

### 1.16.2 Over-classification — cross-file control-flow claims require full call-path trace

The mirror failure: a capable task-runner reviewing a cumulative diff returned READY-WITH-NOTES on the strength of a new finding — "`args.config` is never referenced in the script, therefore `--config` is a no-op." The orchestrator read the code and found the claim false: the script calls a loader, which calls a helper in a sibling module that runs its own `argparse.parse_known_args()` over `sys.argv` and returns the `--config` value. The flag is consumed end-to-end through a second file. Capability did not prevent the error — the agent over-classified.

> [!constraint] Trace the Full Call Path Before Accepting a Cross-File Non-Use Claim
> WRONG — accept the agent's new-issue finding because local evidence looks conclusive:
> ```
> # Agent: "args.config never referenced in {script}.py → --{flag} is a no-op → READY-WITH-NOTES"
> # Orchestrator: records READY-WITH-NOTES, files the seed.   # propagates a false positive
> ```
> CORRECT — trace the full call path before accepting a cross-file non-use claim:
> ```
> # Agent: "args.config never referenced → --{flag} inert"
> # Orchestrator: reads {load_fn}() → finds {helper}() re-parses {argv-source}
> #               → confirms --{flag} IS consumed end-to-end → withdraws finding → verdict READY
> ```

A claim of the form "symbol X is declared but never used in this file, therefore feature Y is broken" is only safe to accept after tracing every consumer of X — including consumers in other files that may read the same input independently (e.g. a second argparse over `sys.argv`). Single-file grep proves local non-use, not global inertness.

Highest false-positive risk patterns — any of these warrants an independent code-read before accepting the verdict: "declared-but-unused," "never called," "dead code," "flag has no effect," "interface mismatch," "unreferenced in this file."

Cost note: a false positive in a release-signoff verdict either blocks a shippable tag or spawns phantom backlog work; the verification is a few targeted reads of the disputed call path — NOT a full re-review.

## 1.17 Task-Runner Dispatch Failure Modes and Resume Protocol

A dispatched task-runner has four post-return states — three failure modes and one real completion. Before dispatching the next task — or before treating a "completed" notification as done — classify the return by the final-message voice and the working-tree state; and when the return *reads* as complete, gate acceptance on **on-disk deliverable evidence** before believing it — a stall can masquerade as completion (§1.17.4). For every failure state the corrective is the same: **resume the SAME agent** (its context already holds the full task), never dispatch a fresh runner. A fresh runner re-reads everything and can race or duplicate the first one's partial work.

### 1.17.1 Diagnosis table

Classify every returned runner against this table before acting on its result:

| Signal | Diagnosis | Action |
|--------|-----------|--------|
| Fast return (seconds, a handful of tool calls), dispatch-voice reply ("I've dispatched the task-runner… I'll report back"), clean tree (zero diff in the edit target, Recovery untouched) | Self-delegation — the runner spawned a nested duplicate instead of executing | Resume the same agent with the execute-yourself directive (§1.17.2) |
| Mid-work narration ending in a colon or next-step phrase ("Now let's rewrite each. First, `test_conflict…`:"), dirty tree with genuine partial edits on disk | Message-boundary stall — the runner executed part-way, then ended its message at a narration checkpoint | Resume the SAME agent with a continuation message (§1.17.3); its context holds the full task state |
| `completed` return whose final message ends mid-action ("Now let me…", "Next I'll…") or omits required report fields — reads as done, but deliverables are not yet on disk | Mid-action stall masquerading as completion — the `completed` status is not a deliverable check | Run the on-disk acceptance gate, then resume the SAME agent to finish (§1.17.4) |
| Structured completion report (status + verification results) whose deliverables verify on disk | Real completion | Reconcile normally |

The three failure modes are genuinely distinct: self-delegation is a **clean** tree + **dispatch** voice (the runner never executed); a message-boundary stall is a **dirty** tree + **executor** voice that ends visibly mid-work (the runner executed part-way); a mid-action stall masquerading as completion **reads** as done — a structured-looking report or a clean final line — yet its deliverables are not on disk (§1.17.4). The shared corrective is "resume the same agent," but the resume *message* — and, for the masquerade case, the on-disk check that exposes it — differs; see below.

### 1.17.2 Self-delegation resume

A task-runner whose spawn prompt merely says "Execute the following task:" can pattern-match itself into the ORCHESTRATOR role (the task file and handler prose it reads are full of dispatch language) and delegate the work onward instead of executing. On the self-delegation signature, do NOT re-dispatch a fresh runner — the first may have left a live nested duplicate that will race it. Resume the same agent with this directive (identical to the spawn-prompt role pin the dispatch loop opens with):

> Execute the following task YOURSELF, directly, with your own tool calls. Do NOT spawn, dispatch, or delegate to any other agent (no Agent/Task tool calls) — you ARE the task-runner.

Then verify single-application afterward (`git status` / diff on the edit target; Recovery advanced).

**Secondary consequence to reconcile:** an orphaned nested duplicate can finish AFTER the corrected primary, so "file modified since read" Edit rejections or unexplained concurrent-editor observations in Recovery may be the duplicate — reconcile by verifying the working tree holds a single spec-exact application, rather than assuming an external session raced.

### 1.17.3 Message-boundary-stall resume

On a message-boundary stall the runner's partial edits are real and on disk. Do NOT treat the stall notification as completion (that silently loses the unfinished tail), and do NOT dispatch a fresh runner (it re-reads everything and may re-edit or conflict with the partial work). Send the SAME agent a continuation message that:

1. quotes the runner's own last line so it anchors where it stopped;
2. forbids starting over or re-editing completed work;
3. enumerates ONLY the remaining work items; and
4. restates the required final-report format.

For long remediation prompts, instruct up front: "work through to the end without pausing for narration checkpoints."

**Residual risk to reconcile:** a stalled runner may have half-updated Recovery (e.g. the header + step table but not Files Modified / Change Log). The orchestrator owns reconciling that gap from verified facts — check Recovery section-by-section after any stalled-then-resumed task. Runs approaching the ~50-tool-use regime are the stall-prone range; budget 1–2 resume round-trips into session-time estimates.

### 1.17.4 Acceptance gate: a `completed` status is not a deliverable check

A runner can return with harness `status: completed` and a final message that reads clean, yet have stopped **mid-action** — before writing Recovery and before emitting its completion report. The harness `completed` status only means the agent stopped with no live children; it is NOT a check that the task's deliverables were produced. Accepting such a return at face value ships whatever the runner had not yet done — an unwritten Recovery step a later compaction would lose, or residual defects it had not yet addressed. Before marking a delegated task done, gate acceptance on **on-disk evidence**, not the agent's final message — especially when that message ends mid-action ("Now let me…", "Next I'll…") or omits the required report fields.

This is distinct from the two voice+tree failure modes above: those announce themselves (dispatch voice, or narration ending mid-work). A mid-action stall *reads* as completion, so only an on-disk check exposes it. The corrective is still to resume the SAME agent — but acceptance is gated on the check first.

> [!constraint] Gate acceptance on on-disk evidence, not the final message
> WRONG — the runner returns `status=completed` with the last line "Now let me update the Recovery file"; the orchestrator marks the task COMPLETE and dispatches the next. The Recovery step is never written, and the stale references the runner had not yet cleaned ship:
> ```
> runner → status=completed, final line: "Now let me update the Recovery file"
> orchestrator → mark COMPLETE, dispatch next task
> [Recovery step unwritten; residual stale references remain in the edit target.]
> ```
> CORRECT — the final line ends mid-action / report fields are missing, so the orchestrator does NOT accept on the status alone. It greps the edit target for the symbol that was supposed to change and reads Recovery, detects the unwritten step + residual references, and resumes the SAME agent (context intact) to finish — then re-verifies on disk before accepting:
> ```
> runner → status=completed, final line ends mid-action / report fields missing
> orchestrator → grep edit target for the changed symbol + read Recovery
>              → unwritten step + residual refs detected
>              → resume SAME agent: "you stopped before finishing — do X, write
>                 Recovery, return the full report"
> agent (context intact) → completes
> orchestrator → re-verify on disk, THEN accept
> ```

**Cheap, high-signal acceptance checks for a code-edit task** (run before accepting a `completed` return; each is sub-second):

- `grep` the target for the symbol that was supposed to change (added, removed, or renamed) — confirm the edit is actually present, and that residual references that were supposed to be swept are gone.
- `git status --short` — confirm the expected file set is dirty and nothing unexpected changed.
- A collection / parse check where applicable (the produced file parses; the test file collects).
- Confirm the Recovery step row for the task flipped to its completed state.

On any miss, resume the SAME agent to finish (never re-dispatch a fresh one), then re-run the checks before accepting.

## 1.18 Verify-Before-Acting on LSP Diagnostics

> [!practice] LSP Diagnostic Verification
> LSP diagnostics ({type-checker}/`{linter}`/rust-analyzer/gopls) may go stale when the underlying source file is edited mid-session. Before acting on a diagnostic (e.g., adding an import, fixing a type), verify the diagnostic is still live.

### Stale vs Live Diagnostic Decision Matrix

| Signal | Likely Stale | Likely Live |
|--------|--------------|-------------|
| Diagnostic line number > file's actual line count | Yes | — |
| Diagnostic mentions identifier not present in file | Yes | — |
| Diagnostic timestamp predates last edit | Yes | — |
| Diagnostic re-fired after LSP refresh | — | Yes |
| Same diagnostic appears across multiple unrelated files | Yes (index drift) | — |
| Diagnostic references a type that was recently renamed | Yes | — |

**When a diagnostic is likely stale:**
1. Trigger an LSP refresh (close and reopen the file, or run `{lint-cmd}` from CLI)
2. If diagnostic is gone after refresh → it was stale; do NOT act on it
3. If diagnostic persists after refresh → it is live; act on it

**When to act without refreshing:**
- Diagnostic is confirmed live (matches current file content at the reported line)
- Diagnostic was emitted by a CLI tool run this session (not cached from prior session)

## 1.19 Model-Floor Bridge (DELEGATED) — Temporary

Applies to every DELEGATED task-runner launch, sequential or parallel.

> [!constraint] Raise a 200K-window model to 1M when the plan-path rule surface is large
> This guard governs EVERY DELEGATED dispatch — both sequential and parallel task-runner launches (see `handlers/run.md` § DELEGATED Mode; §1.13 and §1.17 above for dispatch-return handling). It is a **temporary bridge**, not a permanent override (see self-deactivation below). It never changes the model for a healthy (small) rule surface.
>
> **Before dispatching a DELEGATED task whose `Agent:` maps to a 200K-window model (Sonnet or Haiku):**
> 1. **Measure the plan-path rule surface.** Reuse the engine's linter: run `python {plugin_root}/scripts/init_project.py --doctor --project-root {project_root}` and sum the `approx_tokens` of the flagged (over-scoped) rules — those `.claude/rules/**` whose `paths:` target `planwise/Plans/**` (or sibling plan/backlog/lessons paths). If `--doctor` is unavailable, fall back to summing those rule files' sizes at ~13 tokens/line.
> 2. **Project the subagent's worst-case load:** `flagged-rule tokens + ~54K fixed overhead`. If that **approaches the 200K window** — rule of thumb: flagged surface ≳ ~110K, leaving < ~35K of working headroom — the declared 200K-window model will overflow ("Prompt is too long") the instant it reads a plan brief that triggers those path rules.
> 3. **Raise and log.** In that case, raise the dispatch `model` to the **1M tier** (Opus, or a 1M-window Sonnet where available) for THIS dispatch only, and emit a one-line log — never silent:
>    ```
>    MODEL FLOOR: raised {task-id} {declared}→1M (plan-path rule surface ~{N}K exceeds safe {declared} budget)
>    ```
> 4. **Otherwise dispatch verbatim.** If the threshold is NOT tripped, pass the declared `Agent:` model through unchanged — the floor is inert for a small surface.

> [!practice] Self-Deactivating Bridge — Not Permanent
> This floor exists only to keep declared-Sonnet/Haiku runners alive while a project still carries a large author-time rule surface scoped to plan paths. Once the project is de-scoped — plugin author-time rules handler-loaded from `references/` (not installed), and any project-local domain rules re-scoped to code paths per `/planwise doctor` — the flagged surface shrinks toward ~0, step 2's threshold is never tripped, and declared-Sonnet tasks dispatch unchanged. When `--doctor` reports no over-scoped rules for a project, this bridge is already inert; it can be retired entirely once no supported project trips it.

## 1.20 1M-Exception Dispatch (DELEGATED) — Token Saver

Applies to every DELEGATED task-runner launch, sequential or parallel; uses the same override mechanism as §1.19 above.

> [!constraint] Raise a `1M-exception`-flagged task to Opus/1M — a COST remedy ONLY
> This guard governs EVERY DELEGATED dispatch — both sequential and parallel task-runner launches (see `handlers/run.md` § DELEGATED Mode) — exactly like the Model-Floor Bridge (§1.19 above) and using the **same override mechanism** — it raises the dispatch `model`, it does NOT rewrite the task file. It is triggered by the task's own flag, not by the plan-path rule surface.
>
> **Effective Token Saver gate.** The `1M-exception` flags were stamped at plan time under whatever Token Saver value was effective for THIS plan — the plan's Master-Plan `Token Saver:` field (`on`/`off`) over the project `context.token_saver` default, resolved via `config_loader.get_effective_token_saver_config(config, plan_override)`. At dispatch time, read that same effective value (the plan's Master-Plan field, falling back to `config.yaml`); when it resolves `false`, no task carries a Token-Saver `1M-exception` and this guard is inert. The runner does NOT re-resolve — it dispatches the flags the plan already baked in.
>
> **When a task is flagged `1M-exception`** (the warning engine sets this in the task header's `Token Budget:` exception field for a single oversized **indivisible** file whose `cost`-reason estimate exceeds a 200K-window runner's budget):
> 1. **Raise and log.** Raise the dispatch `model` to the **1M tier** (Opus) for THIS dispatch only — a Sonnet/Haiku runner's window is **200K**, so the 1M-exception is the ONLY way an oversized single-file task fits *the window*. Emit a one-line log, never silent:
>    ```
>    1M EXCEPTION: raised {task-id} {declared}→1M (oversized indivisible file — cost-reason Critical, cannot be split)
>    ```
> 2. **Non-flagged tasks dispatch verbatim** on their declared `Agent:` model. The exception is inert for every task the engine did not flag.

> [!constraint] Window ≠ Readability — 1M-Exception Does NOT Fix a `read`-reason Critical
> WRONG — a task's Required Context file is `read`-reason Critical (≥ 256 KiB byte gate, or above the per-Read 25K-token page cap) and the orchestrator routes the dispatch to Opus/1M assuming the larger window absorbs it:
> ```
> read-reason Critical context file  → raise dispatch to 1M  → "the bigger window reads it"  ← FALSE
> ```
> CORRECT — the Read tool's **25K-token page cap** and **256 KiB byte refusal** apply on EVERY model; Opus's tokenizer is ~1.44× heavier so it trips the page cap *sooner* (~1,340 lines vs ~1,920 for Sonnet/Haiku). The 1M-exception covers **only** a `cost`-reason Critical (a context-window/carrying-cost overflow). It does NOT cover a `read`-reason Critical — that file must be **paged** by the runner (`offset`/`limit`/Grep) even on Opus, or refactored:
> ```
> read-reason Critical context file  → log `paged-read required` (NOT 1M-exception)  → runner pages it (offset/limit/Grep) on its declared model
> ```
> The warning engine (Token Saver) does NOT set `1M-exception` for a `read`-reason Critical, and `run.md` MUST NOT infer it. Log such a task with a `paged-read required` note and dispatch it on its declared model — keep the two reasons distinct in the dispatch log: `1M-exception` for `cost`-Critical, `paged-read required` for `read`-Critical.

## 1.21 Background vs Foreground Gate

Governs whether a DELEGATED task-runner launches in foreground or background.

> [!constraint] Write-Producing Agents MUST Run in Foreground
> Background subagents auto-deny any permission not explicitly pre-approved at launch — including Write, Edit, and Bash. The `bypassPermissions` mode does NOT override this gate. Tool calls fail silently: the agent continues executing but produces no output files.
>
> WRONG: Launch task-runner in background when it writes output files:
> ```
> Task(
>   subagent_type: "planwise:task-runner",
>   run_in_background: true,
>   prompt: "Execute task 01..."
> )
> ```
> CORRECT: Launch task-runner in foreground (default) — background is only safe for read-only agents:
> ```
> Task(
>   subagent_type: "planwise:task-runner",
>   prompt: "Execute task 01..."
> )
> ```

| Task Produces | Launch Mode | Rationale |
|---------------|-------------|-----------|
| File output (Write, Edit) | **Foreground** | Permissions resolved interactively |
| Shell commands (Bash) | **Foreground** | Bash permission needs interactive approval |
| Read-only research (Explore) | Background OK | No write permissions needed |

## 1.22 Delegated Mode Anti-Patterns Checklist

Quick-reference checklist for common DELEGATED-mode mistakes; several map to fuller rules elsewhere in this file.

> [!antipattern] Delegated Mode Anti-Patterns
> - **Orchestrator reads Consolidated Context:** Blows context budget; task-runners duplicate the read (full rule: §1.3)
> - **Skip Recovery between tasks (sequential dispatch):** Context compaction loses progress
> - **Skip Recovery reconciliation after a parallel batch:** Context compaction loses the entire batch; status blocks were returned but never persisted (full rule: §1.13)
> - **Combine tasks in one task-runner:** Defeats fresh-context purpose
> - **Launch sequential Task N+1 before Recovery updated:** Compaction loses Task N completion
> - **Allow parallel task-runners to write Recovery:** Last-write-wins races silently drop completion rows (full rule: §1.13)
> - **Orchestrator produces task outputs:** Context accumulates; no fresh budget benefit
> - **Infer DELEGATED at runtime:** Planning should have set this; warn user and re-plan if needed (full rule: §1.1)

---

*Originally extracted from [`agent-orchestration.md`](agent-orchestration.md) §11-§12 (DELEGATED Dispatch Discipline + Verify-Before-Acting on LSP Diagnostics); §1.19–§1.22 folded from `handlers/run.md`'s Delegated Execution Protocol (2026-08-10). That file now carries only a short §11 pointer stub back to this file.*
*Cross-reference: [agent-orchestration.md](agent-orchestration.md), [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*
