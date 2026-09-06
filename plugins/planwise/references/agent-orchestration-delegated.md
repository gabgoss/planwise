---
description: DELEGATED dispatch discipline, Part 1 of 3 — declaration, foundations, and dispatch-prompt construction (§1.1–§1.13) for spawning task-runner subagents; extracted from agent-orchestration.md §11-§12
---

# DELEGATED Dispatch Discipline — Part 1: Foundations and Dispatch-Prompt Construction

**Purpose:** Operational dispatch protocols for an orchestrator running a DELEGATED session (spawning task-runner subagents). These subsections (§1.1–§1.30) were extracted from [`agent-orchestration.md`](agent-orchestration.md) §11–§12 to keep the core orchestration reference compact on every invocation; they load conditionally when DELEGATED mode is declared.

The discipline spans **three files**, split by topic because the combined text exceeds the Read-tool page cap. Section numbers are continuous and unique across all three. A section keeps its `§1.N` identifier wherever it lands, so an existing `§`-anchor still names exactly one section — only the filename that holds it changes.

| Part | File | Sections | Topic |
|---|---|---|---|
| 1 (this file) | `agent-orchestration-delegated.md` | §1.1–§1.13 | Declaration, foundations, and dispatch-prompt construction |
| 2 | [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) | §1.14–§1.22 | Dispatch mechanics and post-return handling |
| 3 | [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) | §1.23–§1.30 | Cross-cutting dispatch-prompt and orchestrator discipline |

This file holds the foundation and everything that shapes a spawn before it goes out. §1.1 Mandatory Triggers, §1.2 Task-File Error Recovery and §1.3 Orchestration Context Boundary establish the ground rules. §1.4–§1.13 then cover dispatch-prompt construction: diagnostics verification, tool-use budget reservation, path-scoped rule injection, the wake-up protocol, the HARD CONSTRAINTS skeleton, fix tier-ranking, forward-looking-verb detection, ceiling disclaimers, the N>25 resume protocol, and the shared-edit-target strategy matrix.

Part 2 carries dispatch mechanics and what happens after a runner returns. Part 3 carries the cross-cutting discipline binding every spawn prompt and the orchestrator's own conduct. [`agent-orchestration.md`](agent-orchestration.md) §11 retains only a short pointer stub back to this file — the full text lives across these three parts.

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

**Continued in Part 2** (§1.14–§1.22) and **Part 3** (§1.23–§1.30) — see the pointer table above.

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

#### Reviewer Check 010 — Task DELEGATED Mandatory Triggers Honored

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** When task meets DELEGATED trigger (2+ Opus tasks per session, META Discovery phase, single task >50K context, output-chaining), parent Orchestration MUST declare Execution Strategy = DELEGATED.
- **Detection:** Grep Orchestration `Execution Strategy:\s*(DIRECT|DELEGATED)`; count Opus tasks; check largest task tokens. ≥2 Opus AND DIRECT → BLOCKER. Any task >50K AND DIRECT → BLOCKER.
- **Finding template:**
```
[BLOCKER] DELEGATED mandatory trigger violated
File: {Orchestration file path} | Location: Execution Strategy section
Issue: {count} Opus tasks / {max_tokens}K largest, but strategy = DIRECT
Fix: Set Execution Strategy = DELEGATED per references/agent-orchestration-delegated.md §1.1 | Confidence: HIGH
```

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

### The HALT Cluster Is an Upstream-Scope Signal

The retry cap and BLOCKED contract above stop a runner from cascading a fix it is not authorized to make. The HALTs they produce are also **data about the task that ran before this one.**

When a batch of work classified as *mechanical* produces **3 or more HALTs of the same failure mode**, across one batch or consecutive batches, the orchestrator MUST stop treating them as individual exceptions and surface the cluster to the user:

```
{N} of {M} items in this family HALTed with the same upstream-incomplete pattern.
This is a scope measurement of {upstream-task}, not a batch failure.
Recommend a follow-up item scoped to the HALT inventory rather than re-opening {upstream-task}.
```

Three rules follow:

1. **Do not tactical-fix between batches.** Mid-session normalization is the cascade-fix anti-pattern wearing a different hat — *"I'll just patch this one caller before the next batch."* It bypasses whatever architectural review the upstream task performed (was that task's decision the same for this item?) and bleeds upstream scope into a batch that was never scoped for it. The cluster is an **upstream-scope signal, not a patch-through**: each HALT stays HALTed until the follow-up executes.
2. **Size the follow-up from the HALT inventory verbatim — do not re-derive it.** The HALTs collectively *define* the follow-up's scope; the cluster's existence proves the cluster. Each HALTed item's specific non-canonical form becomes one row in the follow-up's brief. Re-opening the upstream task to "find more" re-runs the criterion that already missed them.
3. **The count is the signal even when every individual HALT was handled correctly.** In the measured case the contract held on all six batches and no fix cascaded — and the cluster still revealed that the upstream task had covered 7 of 16. A clean batch is not evidence of complete upstream scope.

#### Reviewer Check 011 — Task-File Error Recovery Semantics Declared

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Task files in DELEGATED mode MUST declare error-recovery behavior in Notes for Agent (partial-failure handling, max retries, fallback).
- **Detection:** Open each DELEGATED task; grep `(?i)error\s+recovery|partial\s+failure|max\s+retries` in Notes for Agent. Absent → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task-file error recovery semantics missing
File: {task file path} | Location: Notes for Agent
Issue: DELEGATED-mode task lacks error-recovery declaration
Fix: Add error-recovery block per references/agent-orchestration-delegated.md §1.2 | Confidence: HIGH
```

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

#### Reviewer Check 012 — Orchestration Context Boundary Callout Present

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** DELEGATED Orchestration MUST contain `> [!constraint] Context Boundary` callout naming which files appear in Orchestration vs Task file Required Context.
- **Detection:** Grep Orchestration `> \[!constraint\][^\n]*Context Boundary` (multiline). DELEGATED AND callout absent → BLOCKER.
- **Finding template:**
```
[BLOCKER] Orchestration Context Boundary callout missing
File: {Orchestration file path} | Location: Execution Strategy section
Issue: DELEGATED mode requires Context Boundary callout
Fix: Add > [!constraint] Context Boundary per references/agent-orchestration-delegated.md §1.3 | Confidence: HIGH
```

#### Reviewer Check 023 — Task DELEGATED Context Boundary Leak

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** In DELEGATED mode, Orchestration Required Context MUST contain ONLY plan files. Heavy context (sources, EIs, references) lives in task file Required Context only.
- **Detection:** Classify each Orchestration Required Context file as plan-file vs heavy-context. Any heavy-context in Orchestration Required Context → BLOCKER.
- **Finding template:**
```
[BLOCKER] DELEGATED Orchestration Required Context boundary leak
File: {Orchestration file path} | Location: Required Context table
Issue: Heavy-context file "{file_path}" present in Orchestration; belongs in task file
Fix: Move per references/agent-orchestration-delegated.md §1.3 | Confidence: HIGH
```

## 1.4 Inter-Dispatch Diagnostics Verification

When DELEGATED dispatches modify shared files (e.g., a shared algorithm module or schema file), the orchestrator MUST independently run the project's primary diagnostic command between dispatches to verify no regression:

- Run `{lint-cmd}` (or equivalent) on the shared file after each dispatch that modifies it
- Run `{precheck-cmd}` if the shared file is a data-layer contract (schema, config)
- If diagnostics fail: halt subsequent dispatches; surface the failure in Recovery before retrying

**Orchestrator output-size verification:**

After each dispatch that produces output files, the orchestrator MUST run `measure_files.py` on every output file and compare against the Expected Output token budget declared in the task file. Deviations >20% from the declared budget are a signal to review before proceeding to the next dispatch.

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

**The same injection discipline governs any shared pin, not only rules.** A baseline SHA — or any equivalent value every task in the session must agree on — is injected by the orchestrator as a **literal** into every task file and every spawn prompt. Instructing a runner to read it back from a shared file (Recovery, the Orchestration file, a scratch note) costs a read the §1.3 context boundary exists to avoid, and breaks outright under parallel dispatch, where that shared file is being written by a sibling runner at the moment the reader opens it. A pin the runner had to fetch is a pin that can arrive empty — and a gate pinned to an empty variable degrades **silently** rather than failing, so nothing downstream announces the loss. See [`measurement-discipline.md`](measurement-discipline.md) §8.7 sub-rule E for the liveness proof that makes such a pin falsifiable.

> [!constraint] Inject the Literal, Do Not Indirect Through a File
> WRONG — the spawn prompt names where the value lives, making every runner fetch it:
> ```
> prompt: "Execute {task file}. Pin every diff gate to the baseline SHA recorded in {Recovery file}."
> ```
> CORRECT — the orchestrator resolves it once and injects the resolved value:
> ```
> prompt: "Execute {task file}. Pin every diff gate to BASE={resolved SHA literal}.
>   Do NOT read this value from any other file — it is authoritative as given here."
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

**A layer annotated "disjoint" must carry the computed evidence.** The matrix above applies whenever N dispatches share a target — which means something has to decide whether they do. That decision is a set intersection over the layer members' own `**Output:**` lines, and it is shown or it did not happen. A bare annotation (`L2 = {2, 3} (disjoint target files)`) reads identically whether the property holds or not, so it can never fail review. Declare the intersection per layer: `∅` means the parallelism stands and the matrix is inert; a non-empty result means the layer must name one of the three strategies above, or serialize. [`scaffolding-hygiene.md`](scaffolding-hygiene.md) §17 owns the scaffold-close computation and its reviewer check; this section owns what to do once the result is non-empty.

**The shared target may be a counter rather than a file.** Two dispatches whose `**Output:**` paths genuinely do not intersect still collide when what they share is an **allocation**: the next free reviewer-check number, the next free catalog row, the next free section number. Both read the same live maximum, both compute the same next value, and both write it into *different* files — so a path-based intersection returns `∅` and the layer passes while the identifier is duplicated. Treat a next-free allocation as a shared target and apply this matrix to it. The cheapest strategy is usually not on the matrix at all: the orchestrator resolves each dispatch's number before dispatch and injects it as a literal, per §1.6.

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
> ## Status Block delivery (REQUIRED)
> Deliver your status block by calling the SendMessage tool with to="team-lead".
> Plain-text output does NOT reach the orchestrator.
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

#### Reviewer Check 052 — DELEGATED Round-2 Compliance

- **Severity / Role / Type:** BLOCKER (bundled 8 sub-checks) | Design-Extension Reviewer | NEW
- **Detection:** For each DELEGATED Orchestration spawn prompt verify: (a) orchestrator output-size measurement (`measure_files.py`) between dispatches; (b) HARD CONSTRAINTS skeleton + SCOPE BOUNDARY clause; (c) tier-rank-by-invasiveness ordering; (d) forward-looking-verb detection; (e) operational-ceiling disclaimers; (f) N>25 Edit-task resume protocol with tool-use budget estimation; (g) shared-edit-target parallelism cap; (h) inter-dispatch diagnostics verification.
- **Finding template:** `[BLOCKER] DELEGATED dispatch round-2 sub-rule {N} violated | Fix per references/agent-orchestration-delegated.md §1.{N}`

---

**Continues in:** [Part 2 — Dispatch Mechanics and Returns](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) (§1.14–§1.22) · [Part 3 — Cross-Cutting Dispatch Discipline](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) (§1.23–§1.30)

*Originally extracted from [`agent-orchestration.md`](agent-orchestration.md) §11-§12 (DELEGATED Dispatch Discipline + Verify-Before-Acting on LSP Diagnostics); §1.19–§1.22 folded from `handlers/run.md`'s Delegated Execution Protocol (2026-08-10). That file now carries only a short §11 pointer stub back to this file. Split into three topical parts (2026-09-06) because the combined text exceeded the Read-tool page cap; section numbers were frozen across the split.*
*Cross-reference: [agent-orchestration.md](agent-orchestration.md), [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*
