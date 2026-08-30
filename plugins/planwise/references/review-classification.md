---
description: Classification reference for /planwise review -- Reviewer Checklists, Known Patterns Whitelist, Severity Classification, Systemic Finding Classification, and the Token Saver Compliance Check. Loaded by the lead at synthesis.
---

# Review Classification Reference

**Purpose:** Static lookup and classification material used by the lead during `/planwise review` synthesis -- reviewer checklist summaries, the intentional-pattern whitelist, severity and systemic-finding classification rules, and the Token Saver large-file compliance check.
**Loaded by:** [handlers/review.md](../handlers/review.md) Required References, always loaded (needed at synthesis).

---

## Reviewer Checklists

The custom agents (`structural-reviewer` and `plan-reviewer`) carry their own checklists. The following is a summary for the lead's reference during synthesis.

### Structural Reviewer (Phase 1)

- Filenames match `{Abbrev}-S{XX}-{YY}` numbering pattern
- Task files listed in Orchestration's Task Files table resolve to real files
- `Outputs/` directory exists per session
- Status fields present in Recovery and Orchestration files
- Cross-reference links resolve (no dead paths)
- [Meta-Plan] `Meta-{Abbrev}/`, `Scaffold-{Abbrev}/`, `Exec-{Abbrev}/` folders all present

### EI Reviewer (Phase 2)

- Every spec section appears in at least one EI's Cross-References table
- Cross-References table cites real, resolvable files
- Content is extracted verbatim -- not summarized or paraphrased
- Header "Extracted from:" lists all cited source files accurately
- Non-sequential spec numbering within an EI is EXPECTED (global scheme) -- do NOT flag as an error

### Task Reviewer (Phase 2)

- Required Context section references are individual with purpose -- NOT ranges (e.g., "Section 2 (entity fields), Section 4 (validation rules)" is correct; "Sections 2-5" is a BLOCKER)
- Every rule/reference file the plan cites has been opened and the plan's description of it re-verified against the live file (a citation is a claim that rots when the cited file changes — re-verify, don't trust the brief's snapshot)
- Execution steps are concrete actions (not vague directives)
- Success criteria are measurable checkboxes
- Declared dependencies match actual data flow between tasks
- Agent assignment is appropriate: Haiku for lookups, Sonnet for code, Opus for decisions
- [Token Saver on] Each task's Required Context obeys the §9.A.8 large-file ladder: no over-ceiling task without `1M-exception`; Warn+ files carry a backlog item; a `read`-reason Critical is never `1M-exception`'d; oversized generated artifacts are Multi-Part split (see [Token Saver Compliance Check](#token-saver-compliance-check))
- Session Summary's Consumption Record present with `measured|estimated` tags; orchestrator-window total kept distinct from summed dispatch budgets
- Every `git diff` in a task's Verification Commands or Success Criteria is scoped to a recorded baseline and path-scoped with `--`, not a `grep` pipe (Check 077)

### Dependency Reviewer (Phase 2, LARGE/VERY LARGE)

- Task dependency DAG has no cycles
- Implicit dependencies not declared (e.g., Task 3 reads files created by Task 2 but does not declare it)
- Sprint ordering respects cross-sprint dependencies
- Parallel tasks are truly independent

### Coverage Reviewer (Phase 2, VERY LARGE)

- All requirements from Master Plan vision are covered by tasks
- No gaps -- requirements mentioned in Master Plan but not addressed by any task
- No redundant tasks that duplicate effort
- Session objectives align with sprint goals

---

## Known Patterns Whitelist

These patterns look like errors but are intentional. Discard findings that match these patterns.

| Pattern | Why It Is Intentional |
|---------|----------------------|
| Global numbering appearing non-sequential within a single EI | Spec numbers are assigned globally across all sprints. A sprint's EI may reference Spec #1, #3, #7 -- the gaps are other sprints' specs. |
| Cross-sprint spec reference that appears orphaned to a single-sprint reviewer | An EI reviewer given only one sprint's scope may flag a valid cross-sprint reference as unresolved. EI reviewers must receive ALL spec outputs to avoid this. |
| Line-count finding where the evidence is a Read-output last line number (not `wc -l`) | `Read` paginates; the last visible line is structurally smaller than the file's true line count. This is a false-positive candidate — verify via `wc -l <path>` before promoting it from `[UNCERTAIN]`. |
| Doctrinal correction that edits only one named file while sibling files still carry the same claim | Scope was deliberately bounded; the executor surfaced the out-of-scope instances as structural findings per `references/read-confirm-act-protocol.md` §1.2. A non-empty doctrinal grep that returns only classified legitimate-pattern rows is intentional. |

> [!practice] Check Whitelist Before Reporting
> Reviewers should verify each finding against the Known Patterns Whitelist before sending it to the team lead. If the pattern matches, discard it. If uncertain, send with `[UNCERTAIN]` prefix rather than discarding outright.

---

## Severity Classification

> [!practice] Severity Is Impact, Not Fix Size
> Rate every finding by what it breaks, never by how laborious the remedy is. Downgrading a finding because the coherent fix is large inverts the project motto — see [do-the-hard-things.md](do-the-hard-things.md).

### Definitions

| Severity | Definition | Examples | Required Action |
|----------|------------|----------|-----------------|
| BLOCKER | Agent cannot execute the task at all | Missing EI section, broken file reference, required dependency not declared | Must fix before execution begins |
| ERROR | Agent will produce incorrect output | Wrong API call, stale field names, contradictory instructions, missing cross-sprint source in EI header | Should fix before execution |
| WARNING | Agent can work around it but quality will suffer | Vague steps, low token estimate, missing optional context file | Fix if time permits |
| INFO | Observation only; no action required | Style inconsistency, redundant context file, minor formatting issue | Log for feedback loop |

### Decision Tree

> [!decide] How to Classify a Finding
> ```
> Finding discovered ->
>   Can the agent execute the task at all?
>     NO  -> BLOCKER
>     YES -> Will the agent produce incorrect output?
>             YES -> ERROR
>             NO  -> Will quality be meaningfully degraded?
>                     YES -> WARNING
>                     NO  -> INFO
> ```

### Confidence-to-Severity Mapping

| Reviewer Confidence | Processing Rule |
|--------------------|-----------------|
| HIGH | Accept finding at its stated severity. Add directly to findings list. |
| MEDIUM | Cross-check against accumulated context from other reviewers. If corroborated or plausible, accept. If contradicted, investigate before including. |
| LOW / `[UNCERTAIN]` | Check against Known Patterns Whitelist first. Cross-check against other findings. Include only if confirmed. Discard if unconfirmed. |

---

## Systemic Finding Classification

During synthesis, the lead classifies each confirmed finding (BLOCKER, ERROR, WARNING) as one-off or systemic.

### Root Cause Categories

| Category | Definition | Typical Fix Location |
|----------|-----------|---------------------|
| **Template gap** | The task file or plan template is missing a rule, example, or structural element that would have prevented the error | Planning templates |
| **Rule gap** | A project-wide rule is incomplete, ambiguous, or missing the specific case that caused the error | `.claude/rules/` |
| **Skill gap** | The review handler or agent definition lacks instructions, context, or false-positive guards that caused an incorrect finding | Plugin handlers or agents |
| **EI extraction gap** | The Execution Input extraction process failed to carry forward sufficient detail or structure from the source material | Scaffolding phase guidance |
| **Protocol gap** | The session or sprint protocol is missing a step or decision rule that caused a process failure | Workflow rules |
| **One-off** | The error was situational and does not reflect a systemic gap; no template or rule change is warranted | N/A -- document rationale |

### Classification Criteria

> [!decide] One-off vs Systemic
> - Would this same error occur in a DIFFERENT plan that follows the same templates? -> **Systemic**
> - Was this error caused by specific characteristics of THIS plan only? -> **One-off**
> - Does a template, rule, or skill fail to prevent this class of error? -> **Systemic** (identify which artifact)
> - Is the error already covered by existing guidance that was missed during execution? -> **One-off** (execution failure, not artifact gap)

### Output Format

Systemic findings appear in the review report's Systemic Findings section:

```
**[S1]** -- {one-line description of the recurring pattern}

| Field                | Value |
|----------------------|-------|
| Root Cause Category  | {template gap | rule gap | skill gap | EI extraction gap | protocol gap | one-off} |
| Description          | {what pattern recurs across findings -- be specific} |
| Suggested Fix Target | {file path + what to change in the planning artifact} |
| Status               | OPEN |
```

---

## Token Saver Compliance Check

**Gated on the effective Token Saver value for the plan under review.** Resolve it once: read the plan's Master-Plan `Token Saver:` field (`on`→True, `off`→False, `inherit`/absent→None) and overlay it on the project default via `config_loader.get_effective_token_saver_config(config, plan_override)` — the per-plan override wins, the project `context.token_saver` key is the fallback (overheads stay project-level). When the effective value is **off**, this entire check is a **no-op** — skip it; zero behavior change versus a pre-Token-Saver review. When **on**, the lead (No-Team Path) or the Task Reviewer (Team Path) runs the check below over every task in scope and reports findings using the standard finding format. It validates that the planner actually applied the per-task large-file ladder anchored in `references/task-content-fidelity.md` §9.A.8 — read that subsection for the level definitions, the `reason=cost|read` contract, and the FIXED Read-tool gates the ladder folds in.

### Derive the ceilings from config (never hardcode)

Read the thresholds from `config.yaml`, exactly as the `/planwise plan` Step 8c scan does — the review re-derives them so it measures against the same numbers the planner used:

```
available_per_task = context.token_saver_session_target − context.token_saver_runner_overhead − 6000
critical           = available_per_task − 10000
warn               = min(40000, round(0.5 × available_per_task))
over_ceiling(task) = task_estimate + context.token_saver_runner_overhead > context.token_saver_session_target
```

**Read gates (FIXED constants, evaluated per the file's assigned-model bytes-per-token ratio, in priority order tokens → bytes → lines):** `bytes ÷ {model-family B/tok — opus/fable 2.6, sonnet/haiku 3.7 gate-conservative}` ≥ `25000` (page cap), warn ≥ `22000`; OR byte ≥ `262144` (256 KiB), warn ≥ `245760` (240 KiB); OR ≥ `2000` lines (defensive first-page window). Measure with `measure_files.py --model {assigned}`. A file's level is `max(cost_level, read_level)`; `reason` records which gate drove it.

### Findings

Run each check below over every task in scope. Each is HIGH confidence (mechanical):

1. **Over-ceiling without exception** — recompute the task's bottom-up estimate. If `over_ceiling(task)` is true AND the task is **not** flagged `1M-exception` → **finding** (severity ERROR — the runner overflows its budget mid-task).
2. **Warn+ Required Context file with no backlog item** — if a Required Context file classifies **Warn or Critical** (cost or read) but the task records no large-file recommendation / backlog item → **finding** (WARNING).
3. **`1M-exception` task on a 200K-window agent** — if a `1M-exception` task is declared `Agent: Sonnet` or `Agent: Haiku` without the run-time override note (the flag dispatches on Opus / 1M; a 200K-window agent would still overflow) → **finding** (ERROR).
4. **Uncovered read-gate crossing** — if a Required Context file crosses a FIXED read gate (measured bytes ≥ 256 KiB, OR `bytes ÷ {assigned-model B/tok}` ≥ 25K tokens, OR ≥ 2,000 lines) and the task records **neither** a paged-read note (`offset`/`limit`/Grep) **nor** a refactor+backlog item → **finding** (WARNING; the runner gets a truncated or refused Read mid-task).
5. **Read-reason Critical mis-flagged `1M-exception`** — if a file that classifies **Critical with `reason=read`** is flagged `1M-exception` → **finding** (ERROR). The 1M window does not raise the per-Read page cap or the byte refusal, and the Opus/Fable-family tokenizer trips the token gate on *fewer bytes* than Sonnet/Haiku's — a read-Critical is paged or refactored, never `1M-exception`'d. Only a `reason=cost` Critical earns the flag.
6. **Oversized generated artifact not split** — if a plan-generated artifact a runner MUST read (task file, Orchestration, Recovery, Consolidated Context part, Execution Input, task Output file) exceeds the **HARD** read ceiling (≥ 25K tokens at the reading model's ratio, OR ≥ 256 KiB, OR ≥ 2,000 lines) without a Multi-Part split → **finding** (ERROR). For generated artifacts the read-gate ceiling is hard, not advisory (external source files the runner reads but does not generate stay advisory under findings 2 and 4).

> [!constraint] Read-Reason Critical Is NOT `1M-Exception`-Resolvable (review mirror)
> WRONG — flag a finding only when an over-ceiling task lacks `1M-exception`, and treat every Critical the same:
> ```
> if over_ceiling(task) and not task.flagged("1M-exception"): finding   # misses read-Critical mis-flagging
> ```
> CORRECT — split on `reason`: a `cost`-Critical MUST be `1M-exception`'d; a `read`-Critical MUST NOT be (it is paged/refactored), and flagging it `1M-exception` is itself a finding:
> ```
> if verdict.level == Critical and verdict.reason == "cost" and not task.flagged("1M-exception"): finding
> if verdict.level == Critical and verdict.reason == "read" and task.flagged("1M-exception"):     finding
> ```

When Token Saver is off, none of the above runs — the §9.A token-estimation checks (Error Pattern Catalog #14, #37, #38) stand alone, unchanged.
