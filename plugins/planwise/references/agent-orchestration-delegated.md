---
description: DELEGATED dispatch discipline — orchestrator protocols (§1.4–§1.15) for spawning task-runner subagents; extracted from agent-orchestration.md §11
---

# DELEGATED Dispatch Discipline

**Purpose:** Operational dispatch protocols for an orchestrator running a DELEGATED session (spawning task-runner subagents). These subsections (§1.4–§1.15) were extracted from [`agent-orchestration.md`](agent-orchestration.md) §11 to keep the core orchestration reference compact on every invocation; they load conditionally when DELEGATED mode is declared.

This file continues the DELEGATED contract begun in [`agent-orchestration.md`](agent-orchestration.md) §11. Read [`agent-orchestration.md`](agent-orchestration.md) §11.1–§11.3 first for the foundation — §11.1 Mandatory Triggers, §11.2 Task-File Error Recovery, §11.3 Orchestration Context Boundary — then this file for the full dispatch discipline (§1.4–§1.15). The subsection numbering is preserved (§11.N → §1.N) so existing downstream citations map mechanically.

## Table of Contents

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

---

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
>   subagent_type: "task-runner",
>   prompt: "...implement X; build; then run /simplify"
> )
> # task-runner: "Unknown subcommand: simplify" — it cannot spawn the review agents.
> ```
> CORRECT — task-runner applies the review lenses inline; orchestrator runs the real review command on the diff after:
> ```
> Task(
>   subagent_type: "task-runner",
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

---

*Continuation of [`agent-orchestration.md`](agent-orchestration.md) §11 — read §11.1–§11.3 there for the DELEGATED foundation (mandatory triggers, task-file error recovery, orchestration context boundary).*
*Cross-reference: [agent-orchestration.md](agent-orchestration.md), [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*
