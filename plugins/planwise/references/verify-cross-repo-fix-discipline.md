---
description: Fix tasks targeting a canonical file outside the working planwise repo MUST treat the live file, not audit excerpts or a Consolidated Context snapshot, as the source of truth — BINDING SOURCE Required Context row, Execution Step 1 full-read mandate, and the content-anchor / data-shape / system-consistent-value / structured-data sub-rules that keep the fix faithful to live state
consult-when: A fix task targets a file outside the working repo — treat the live file as source of truth, not excerpts
---

# Cross-Repo Canonical Source — Fix-Task Authoring Discipline

Companion to [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) §1-§5 (the Exec-phase SDK/identifier verification core). This file carries §6 (the Discovery-phase consolidation-time discipline) and §7 (.1-.7), its cross-repo execution-time complement.

## Table of Contents

- [6. Discovery-Phase Consolidation — Verify Citations and SDK Premises Against Live Source](#6-discovery-phase-consolidation--verify-citations-and-sdk-premises-against-live-source)
- [7.1 The recurring failure mode](#71-the-recurring-failure-mode)
- [7.2 Rule — Required Context table MUST include the canonical source as a BINDING SOURCE row](#72-rule--required-context-table-must-include-the-canonical-source-as-a-binding-source-row)
- [7.3 Rule — Execution Step 1 MUST be the canonical-file full read](#73-rule--execution-step-1-must-be-the-canonical-file-full-read)
  - [7.3a — Re-locate every edit by content, not by recipe line/step number](#73a--re-locate-every-edit-by-content-not-by-recipe-linestep-number)
  - [7.3b — Verify data shapes against the live file before writing code](#73b--verify-data-shapes-against-the-live-file-before-writing-code)
  - [7.3c — System-consistent value beats recipe literal — flag the divergence](#73c--system-consistent-value-beats-recipe-literal--flag-the-divergence)
  - [7.3d — Structured-data entries: derive from a same-class on-disk example; parser-load before close](#73d--structured-data-entries-derive-from-a-same-class-on-disk-example-parser-load-before-close)
- [7.4 Why task-level enforcement, not reference-level](#74-why-task-level-enforcement-not-reference-level)
- [7.5 Scaffold-time verification command](#75-scaffold-time-verification-command)
- [7.6 Exempt task types](#76-exempt-task-types)
- [7.7 Applies-to surface](#77-applies-to-surface)

---

## 6. Discovery-Phase Consolidation — Verify Citations and SDK Premises Against Live Source

The verification discipline applies to **Discovery-phase** consolidation as much as to **Exec-phase** specs (EIs, task specs, BLIs). A Consolidated Context Part is authored from source, and a `file:line` citation pinned at scaffold-time goes stale the moment the live file grows. A third-party SDK premise paraphrased in the task brief (e.g., "this overload is delegate-only — no `MethodInfo` overload") can be a verified-false starting assumption. Neither failure surfaces in a build, because no code is produced at Discovery time. Both can only be caught by **reading the shipped artifact during consolidation**. `scripts/check_section_citations.py --file-line` checks that each `file:line` citation in a Part names an existing file with that many lines and that its anchor sits in the cited range. SDK premises stay judgment.

> [!constraint] A Discovery / consolidation agent MUST treat every `file:line` citation and every third-party SDK premise in its task brief as a STARTING HYPOTHESIS — verify against live source / reflected DLL, cite the verified position, flag false premises as prominent corrections in the output Part
> WRONG — copy the task-brief's `file:line` citations and SDK premises verbatim into the output Part, trusting them because "the planner already verified". The Part launders stale line numbers (the file has grown to 990 lines) and a verified-false SDK premise into the Scaffolding phase, which builds Exec specs on top of them:
> ```markdown
> The plugin registration is at `Connection.cs:797-812` (per task brief). The factory
> `{SdkFactory}.Create` is delegate-only — no `MethodInfo` overload.
> ```
> CORRECT — open the live file / reflect the shipped artifact, cite the verified position, and flag any brief premise that turns out false as a prominent correction in the output Part (not a silent fix):
> ```markdown
> **Verified against live source 2026-MM-DD:** plugin registration is at
> `Connection.cs:835-852` (file has grown to 990 lines since the task brief).
>
> **Task-brief premise correction:** the brief asserts `{SdkFactory}.Create` is
> "delegate-only". Reflecting `{ExternalSdk}.dll` {pinned-version} via
> `[{SdkFactory}].GetMethods() | Where Name -eq 'Create'` returned **three** overloads —
> one `Delegate` and **two `MethodInfo`**. The premise was load-bearing; the correction
> is recorded in §{open-questions} and re-folds into downstream Scaffolding.
> ```

**Operational rule for multi-task Discovery sessions:** when two parallel agents both touch the same large source file, expect citation drift and have the orchestrator consolidate the verified positions into the Recovery `Key Findings` as a single carry-forward note for any dependent (synthesis) task. The Discovery→Scaffolding boundary is where the carry-forward earns its budget — the Scaffolding phase MUST re-verify any file:line / SDK premise carried forward from Discovery rather than treating it as settled.

> [!practice] Mark Discovery-time false-premise corrections as PROMINENT in the Consolidated Context Part — not silent fixes
> When a Discovery agent overturns a load-bearing task-brief premise (an SDK overload set, a delegate-only-ness claim, a member presence assertion), surface the correction explicitly in the output Part with a "Task-brief premise correction" heading. Downstream Scaffolding readers and synthesis tasks rely on the correction being visible; a silent fix laundering the corrected fact back into the Part text leaves the false premise as a latent claim someone else can re-cite.

---

## 7. Cross-Repo Canonical Source — Fix-Task Authoring Discipline

When a fix task modifies a file that lives **outside the working planwise repo** — in a vendored sibling repo, a gitignored subfolder reached via `additionalDirectories`, an out-of-tree package extraction, or an upstream plugin source — the audit excerpts and consolidated specs that drove the fix are NOT the source of truth. The live canonical file is.

§6 catches citation drift at consolidation-authoring time (the Discovery agent verifies against live source while writing the Part). §7 catches the same class of drift at fix-task **execution** time, when the consolidated spec has already locked the line citations and a downstream Sonnet agent is about to apply them.

> [!constraint] The live canonical file is the source of truth, never the audit derivative
> WRONG — start the fix from the audit excerpts or the consolidated spec.
>
> CORRECT — start the fix from the live canonical file, and treat the excerpts as a snapshot that may have drifted.

### 7.1 The recurring failure mode

A multi-stage plan (Audit → Consolidate → Scaffold → Execute) routinely produces fix tasks that quote `file:line` ranges and code-fragment excerpts from a source file in a sibling / vendored / external-to-working-repo location. By the time the fix task is dispatched:

- Lines may have shifted (the file was edited between audit and execute)
- Surrounding context (function signatures, sibling sections, conditional branches) is invisible in the excerpt
- Verification grep patterns in the spec assume the file's current state, not the snapshot state

A Sonnet (or any general-purpose) agent that begins reasoning from the excerpt — without first reading the canonical file in full — will either fix the wrong line range, miss a surrounding invariant that the spec author saw but the excerpt didn't capture, OR produce a verification grep that returns a misleading hit because the live file's identifiers have drifted.

### 7.2 Rule — Required Context table MUST include the canonical source as a BINDING SOURCE row

Every fix task whose target file lives in another repository has a Priority 1 Required Context row that names that file and carries `BINDING SOURCE — full read required`. `scripts/lint_task_file_structure.py` rule `cross-repo-binding-source` checks it at BLOCKER. When the task file has no repository root to resolve against, the rule reports a WARNING instead. The Purpose column of that row reads `**BINDING SOURCE — full read required, do not work from audit excerpts**`.

The audit-derivative artifact (findings report, Consolidated Context Part, EI section) stays in Required Context — typically as Priority 2 — for its rationale, edit recipe and cross-finding context. It is NEVER the BINDING SOURCE.

> [!constraint] BINDING SOURCE label is reserved for the live cross-repo canonical file
> WRONG — the Consolidated-Context Part is annotated as the source of truth; the canonical cross-repo file is omitted or downgraded to Priority 2:
> ```
> | 1 | {Consolidated-Context-Part} | Audit edit-recipe + line ranges (BINDING SOURCE) |
> | 2 | {canonical-cross-repo-path} | Reference — read if needed |
> ```
> CORRECT — the canonical cross-repo file is the Priority-1 BINDING SOURCE; the Part is Priority 2, supporting context only:
> ```
> | 1 | {canonical-cross-repo-path} | **BINDING SOURCE — full read required, do not work from audit excerpts** |
> | 2 | {Consolidated-Context-Part} | Decision rationale + edit recipe + line ranges (snapshot, may have drifted) |
> ```

### 7.3 Rule — Execution Step 1 MUST be the canonical-file full read

Execution Step 1 of such a task is the verbatim full read of the target file. `scripts/lint_task_file_structure.py` rule `cross-repo-step1-read` checks Step 1 against `Read .* in full before any fix reasoning` at BLOCKER (Reviewer Check 066 (a)). This is the FIRST step — before "build mental model of fix", before "verify line ranges from audit", before any code edit.

> [!constraint] Step 1 is the exact full-read step, not a generic preamble
> WRONG — paraphrase the read or fold it into a generic "read context" preamble:
> ```
> 1. Read context, then verify line ranges from audit.
> ```
> CORRECT — write the exact step, verbatim:
> ```
> 1. Read `{canonical-cross-repo-path}` in full before any fix reasoning. Do NOT begin from audit excerpts or Consolidated-Context Part snippets. The canonical file at the cited path is the source of truth.
> ```

The full read at Step 1 is necessary but not sufficient. §7.3a–§7.3d bind the execution-time sub-rules that fire *after* the canonical file is in context.

### 7.3a — Re-locate every edit by content, not by recipe line/step number

After the Step 1 read, find every edit target by its unique content anchor — heading text (`## Step 4 — …`), a function name, or a unique anchor string — never by the recipe's absolute line or step number, which were captured at audit time. Where the recipe's structural claim conflicts with the live file (a list where the recipe shows a table, a different step count, content that has moved), the live file wins. `scripts/lint_task_file_structure.py` rule `cross-repo-naked-line-ref` reports at WARNING a later step that names `line N`, `Step N.N` or `LN` without a quoted string, `§` citation or code-span anchor. The match is heuristic, so a hit is a signal to read, never a gate (Reviewer Check 066 (b)).

> [!constraint] Locate edits by content anchor; the live file's shape overrides the recipe's
> WRONG — apply a recipe's "Step 4.4" insert or line range verbatim, overwriting a step that was renumbered or shifted since the recipe was authored:
> ```
> # recipe says: insert the git-commit step at "Step 4.4"
> # → blindly edits the current Step 4.4, which is now a different, unrelated step
> ```
> CORRECT — locate the insertion point by heading text and function name, and note the discrepancy in a deviation comment:
> ```
> # locate "## Step 4 — …" by heading text; find the git-commit anchor by content
> # recipe said Step 4.4 but the live file now numbers it Step 4.5 — note the divergence + proceed
> ```

### 7.3b — Verify data shapes against the live file before writing code

After Step 1 (full read), verify every data shape, function signature, and argparse behaviour the recipe claims before writing code that relies on them, because excerpt-only patches can compile-fail or crash at runtime. If the live shape differs, implement against it and flag the recipe divergence.

> [!constraint] Read the live function/class to confirm shape before coding the recipe's edit
> WRONG — code directly from the recipe's data-shape claims:
> ```python
> max((int(i.id) for i in items))   # recipe assumes objects; live items are dicts → AttributeError
> _load_index(config)               # recipe calls a function that does not exist in the live file → NameError
> ```
> CORRECT — read the live function/class first, implement against the live shape, flag the divergence:
> ```python
> max(int(i["id"]) for i in items)  # live items are dicts: item["id"]
> # the recipe's _load_index is not present in the live file — use the live index-loading path; note the divergence
> ```

### 7.3c — System-consistent value beats recipe literal — flag the divergence

Where the recipe's literal value conflicts with the live system — an enum, a template default, or a naming convention — implement the system-consistent value and flag the recipe's divergent literal in a deviation note. Copy the recipe's value only when the live system's authoritative check (the enum list, the constant, the template) confirms it is valid.

> [!constraint] When a recipe literal is not in the live enum/template, implement the system value and flag it
> WRONG — copy the recipe literal verbatim, injecting a value the live system rejects:
> ```
> --status "Open"   # recipe default; not a member of the live status enum
> ```
> CORRECT — implement the value the live enum + template default confirm; flag the divergence:
> ```
> --status "NOT_STARTED"   # the live template default and a member of the status enum
> # recipe said "Open" — diverged + noted in a deviation comment
> ```

### 7.3d — Structured-data entries: derive from a same-class on-disk example; parser-load before close

When writing new entries to a self-describing structured file (YAML/JSON/TOML): (1) derive field values from an existing same-class on-disk entry rather than from the recipe/skeleton — the file's own declared enum sets and field names take precedence over a spec example; and (2) run a parser load as the mandatory final step of the editing task, not just a content grep. The parser load is the minimum exit criterion; a passing grep does not prove a schema-valid file.

`scripts/lint_task_file_structure.py` rule `cross-repo-parser-gate` reports at WARNING when the Output line names such a file and Success Criteria holds no `safe_load`, `json.load` or `tomllib` gate (Reviewer Check 066 (c)).

> [!constraint] Derive structured-file fields from an on-disk same-class entry, then parser-load before closing
> WRONG — copy the skeleton field verbatim; the value belongs to a different enum block and the entry is schema-invalid:
> ```yaml
> missing_key_behavior: not_installed   # invalid: not_installed is an upgrade_behavior, not a missing_key_behavior
> ```
> CORRECT — derive each field from the existing same-class on-disk entry, then parser-load:
> ```yaml
> missing_key_behavior: warn_loud       # matches the canonical same-class on-disk entry
> upgrade_behavior: not_installed
> ```

Run `python -c "import yaml; yaml.safe_load(open('{file}'))"` as the final step. It must return without error. Then confirm each written value is a member of the enum block declared at the top of the file.

#### Reviewer Check 066 — Fix-Task Execution-Time Fidelity (§7.3a–§7.3d)

- **Severity / Role / Type:** BLOCKER/WARNING (tiered) | Task Reviewer | NEW
- **What:** For any fix task whose target file lives cross-repo (a Required Context row annotated `BINDING SOURCE — full read required`), the Execution Steps MUST exhibit execution-time fidelity discipline: (a) a Step-1 canonical-file full-read gate (also enforced by the §7.5 structure lint); (b) re-locate-by-content language — later steps locate edits by heading text / function name / unique anchor string, with no naked recipe line/step number presented as the authoritative edit target; (c) for any YAML/JSON/TOML edit, a parser-load success criterion (e.g. a `yaml.safe_load` / `json.load` gate) in Success Criteria, not just a content grep. Non-cross-repo fix tasks are out of scope (§7.6 exemptions).
- **Detection:**
  1. Identify fix tasks with a Required Context row annotated `BINDING SOURCE` (cross-repo canonical target). If none, the check is a no-op for that task.
  2. (a) Grep Execution Step 1 for the full-read gate (`Read .* in full before any fix reasoning`). Absent → BLOCKER.
  3. (b) Grep later Execution Steps for a naked recipe line/step reference (`line \d+`, `Step \d+\.\d+`, `L\d+`) used as the edit target without an accompanying content anchor (heading text / function name / unique string). Present without anchor → WARNING.
  4. (c) If Expected Output or Execution Steps touch a `.yaml`/`.yml`/`.json`/`.toml` file, grep Success Criteria for a parser-load gate (`safe_load`, `json.load`, `tomllib`, or equivalent). Absent → WARNING.
- **Enforced by:** `scripts/lint_task_file_structure.py` rules `cross-repo-step1-read` (a), `cross-repo-naked-line-ref` (b) and `cross-repo-parser-gate` (c). Rule (c) reads the Output line only, so Detection step 4 stays wider.
- **Finding template:**
```
[{BLOCKER|WARNING}] Fix-task execution-time fidelity gap
File: {task file path} | Location: Execution Steps / Success Criteria
Issue: {Step-1 full-read gate missing on BINDING SOURCE task | naked recipe line/step reference used as edit target without content anchor | structured-data edit lacks parser-load success criterion}
Fix: Apply the §7.3a–§7.3d execution-time discipline per references/verify-cross-repo-fix-discipline.md (Step-1 full read / re-locate by content / verify data shapes / system-consistent value / parser-load before close) | Confidence: HIGH
```

### 7.4 Why task-level enforcement, not reference-level

Documenting canonical-source discipline only in a reference file (such as this one) has historically produced variable adherence — "the agent should know to do this" devolves into the agent NOT doing it whenever the reference doesn't load into the agent's context window at execution time. By forcing the rule into every fix-task file's Required Context table AND Execution Steps Step 1, the discipline becomes:

- **Visible in the file the agent is reading** — not in a sibling reference doc the agent might or might not load
- **Mechanically grep-checkable by `/planwise review`** — the review handler greps each fix-task file for the BINDING SOURCE annotation and the Step-1 verbatim string; missing-pattern findings are BLOCKER-severity
- **Enforced at scaffold time** — `/planwise plan --scaffold` either emits compliant task files or it doesn't; a non-compliant task file is a structural finding that blocks plan completion

### 7.5 Scaffold-time verification command

After `/planwise plan --scaffold` produces fix-task files for a plan whose target files live cross-repo, the planner / reviewer MUST run the structure lint, whose `cross-repo-binding-source` and `cross-repo-step1-read` rules check each file at BLOCKER:

> [!verify] Cross-repo fix-task BINDING SOURCE + Step-1 compliance check
> ```bash
> python -B {plugin_root}/scripts/lint_task_file_structure.py {planwise_root}/{plans_dir}/{PlanName}
> ```
>
> Any fix-task file the lint reports under either rule is non-compliant; the scaffolding agent MUST regenerate it. `/planwise review` SHOULD codify this check in its Error Pattern Catalog at BLOCKER severity when the plan's target files live cross-repo.

### 7.6 Exempt task types

§7.2 and §7.3 apply to **FIX tasks** — Sonnet (or general-purpose) agents performing code/markdown edits on cross-repo canonical files. The following task types are exempt:

| Exempt task type | Reason |
|------------------|--------|
| Human-gate decision tasks | The "fix" is a human conversation (release-target choice, scope decision, gate approval); no canonical-file read required at decision time. The follow-up Sonnet edit task IS subject to the rules. |
| Cumulative-diff triage by Opus | When Opus reads the cumulative plan diff (already-applied changes) for a sprint-end readiness signal, the diff itself is the source of truth at that point. Opus may consult canonical files as needed but is not bound by the Step-1-full-read mandate. |
| Audit / discovery / research tasks | Tasks whose output is a findings report, a Consolidated Context Part, or an EI extraction. These are read-only against canonical files; §6 already covers their drift discipline. |
| Tasks whose target file lives inside the working planwise repo | §7 applies to **cross-repo** canonical files. For files inside the same repo as the plan (`{planwise_root}/{plans_dir}/...`, `src/...`, etc.), the standard Required Context discipline and the §6 verify-during-consolidation discipline are sufficient. |

All other cross-repo fix tasks MUST comply.

### 7.7 Applies-to surface

§7 binds for plans where the target plugin / package / artifact lives in any of these locations:

- A sibling repo cloned into a gitignored subfolder of the working tree (e.g., a vendored upstream plugin source, an integration test harness checkout, a docs-as-code mirror)
- An out-of-tree path on the consumer's machine reachable only via `additionalDirectories` configuration
- An upstream package cache or vendor extraction whose live state may diverge from the snapshot captured in audit excerpts

The `verify-against-shipped-artifact.md` §3g internal-placement check (the project's own scoped-rules registry) is the in-repo analog of §7; together they cover both axes of "the spec quotes a file path; the agent must verify against the live destination, not the spec snapshot."

---

*Companion files: [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md), [verify-discovery-consolidation.md](verify-discovery-consolidation.md), [verify-backlog-citation-freshness.md](verify-backlog-citation-freshness.md).*
