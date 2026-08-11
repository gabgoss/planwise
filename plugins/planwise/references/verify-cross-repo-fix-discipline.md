---
description: Fix tasks targeting a canonical file outside the working planwise repo MUST treat the live file, not audit excerpts or a Consolidated Context snapshot, as the source of truth — BINDING SOURCE Required Context row, Execution Step 1 full-read mandate, and the content-anchor / data-shape / system-consistent-value / structured-data sub-rules that keep the fix faithful to live state
---

# Cross-Repo Canonical Source — Fix-Task Authoring Discipline

Companion to [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) §1-§5 (the Exec-phase SDK/identifier verification core). This file carries §7 (.1-.7) — the cross-repo execution-time complement to `verify-discovery-consolidation.md` §6's consolidation-time discipline.

## Table of Contents

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

## 7. Cross-Repo Canonical Source — Fix-Task Authoring Discipline

When a fix task modifies a file that lives **outside the working planwise repo** — in a vendored sibling repo, a gitignored subfolder reached via `additionalDirectories`, an out-of-tree package extraction, or an upstream plugin source — the audit excerpts and consolidated specs that drove the fix are NOT the source of truth. The live canonical file is. This section binds the discipline that keeps fix agents from working off stale snapshots.

`verify-discovery-consolidation.md` §6 catches citation drift at consolidation-authoring time (the Discovery agent verifies against live source while writing the Part). §7 catches the same class of drift at fix-task **execution** time, when the consolidated spec has already locked the line citations and a downstream Sonnet agent is about to apply them. §7 is the cross-repo execution-time complement to `verify-discovery-consolidation.md` §6's consolidation-time discipline.

### 7.1 The recurring failure mode

A multi-stage plan (Audit → Consolidate → Scaffold → Execute) routinely produces fix tasks that quote `file:line` ranges and code-fragment excerpts from a source file in a sibling / vendored / external-to-working-repo location. By the time the fix task is dispatched:

- Lines may have shifted (the file was edited between audit and execute)
- Surrounding context (function signatures, sibling sections, conditional branches) is invisible in the excerpt
- Verification grep patterns in the spec assume the file's current state, not the snapshot state

A Sonnet (or any general-purpose) agent that begins reasoning from the excerpt — without first reading the canonical file in full — will either fix the wrong line range, miss a surrounding invariant that the spec author saw but the excerpt didn't capture, OR produce a verification grep that returns a misleading hit because the live file's identifiers have drifted.

### 7.2 Rule — Required Context table MUST include the canonical source as a BINDING SOURCE row

Every fix task whose target file lives in a cross-repo / vendored / external-to-working-repo location MUST include a Priority-1 row in its Required Context table pointing at the canonical file, with this exact annotation in the Purpose column:

```
| 1 | {canonical-cross-repo-path} | ~{N} | ~{X}K | **BINDING SOURCE — full read required, do not work from audit excerpts** |
```

The audit-derivative artifact (findings report, Consolidated Context Part, EI section) stays in Required Context — typically as Priority 2 — because it carries the decision rationale, the proposed edit recipe, and any cross-finding context. But the audit-derivative is NEVER the BINDING SOURCE. That label is reserved for the live canonical file.

> [!constraint] BINDING SOURCE label is reserved for the live cross-repo canonical file
> WRONG — the audit / Consolidated-Context Part is annotated as the source-of-truth in the task's Required Context table; the canonical cross-repo file is either omitted or downgraded to Priority 2:
> ```
> | Priority | File | Purpose |
> |----------|------|---------|
> | 1 | {planwise_root}/{plans_dir}/.../*-Consolidated-Context-Part-{N}.md | Audit edit-recipe + line ranges (BINDING SOURCE) |
> | 2 | {canonical-cross-repo-path} | Reference — read if needed |
> ```
> CORRECT — the canonical cross-repo file is the Priority-1 BINDING SOURCE; the audit / Consolidated Context Part is Priority 2, supporting context only:
> ```
> | Priority | File | Purpose |
> |----------|------|---------|
> | 1 | {canonical-cross-repo-path} | **BINDING SOURCE — full read required, do not work from audit excerpts** |
> | 2 | {planwise_root}/{plans_dir}/.../*-Consolidated-Context-Part-{N}.md | Decision rationale + edit recipe + line ranges (snapshot, may have drifted) |
> ```

### 7.3 Rule — Execution Step 1 MUST be the canonical-file full read

Every fix task targeting a cross-repo canonical file MUST begin its Execution Steps with this exact step (verbatim, not paraphrased, not folded into a generic "read context" preamble):

```
1. Read `{canonical-cross-repo-path}` in full before any fix reasoning. Do NOT begin from audit excerpts or Consolidated-Context Part snippets. The canonical file at the cited path is the source of truth.
```

This is the FIRST step — before "build mental model of fix", before "verify line ranges from audit", before any code edit. The full-read gate exists because agents have historically conflated audit excerpts with live state and shipped fixes that no longer apply.

The full read at Step 1 is necessary but not sufficient. §7.3a–§7.3d bind the execution-time sub-rules that fire *after* the canonical file is in context — the discipline that turns a clean full read into a faithful edit.

### 7.3a — Re-locate every edit by content, not by recipe line/step number

Recipes carry step IDs, line numbers, and section shapes captured at audit time. After reading the canonical file in full at Step 1, find every edit target by its unique content anchor — heading text (`## Step 4 — …`), a function name, or a unique anchor string — never by the recipe's absolute line or step number. Where the recipe's structural claim conflicts with the live file (a list where the recipe shows a table, a different step count, content that has moved), the live file wins.

> [!constraint] Locate edits by content anchor; the live file's shape overrides the recipe's
> WRONG — apply a recipe's "Step 4.4" insert verbatim, overwriting an unrelated step that was renumbered since the recipe was authored; apply a recipe line-range to an already-shifted location:
> ```
> # recipe says: insert the git-commit step at "Step 4.4"
> # → blindly edits the current Step 4.4, which is now a different, unrelated step
> ```
> CORRECT — read the full canonical file (Step 1 done), then locate the insertion point by heading text and function name rather than any recipe-provided step/line number; note the discrepancy in a deviation comment:
> ```
> # locate "## Step 4 — …" by heading text; find the git-commit anchor by content
> # recipe said Step 4.4 but the live file now numbers it Step 4.5 — note the divergence + proceed
> ```

### 7.3b — Verify data shapes against the live file before writing code

Excerpt-only patches can compile-fail or crash at runtime. After Step 1 (full read), verify every data shape, function signature, and argparse behaviour the recipe claims before writing code that relies on them. If the live shape differs from the recipe, implement against the live shape and flag the recipe divergence.

> [!constraint] Read the live function/class to confirm shape before coding the recipe's edit
> WRONG — code directly from the recipe's data-shape claims:
> ```python
> max((int(i.id) for i in items))   # recipe assumes objects; live items are dicts → AttributeError
> _load_index(config)               # recipe calls a function that does not exist in the live file → NameError
> ```
> CORRECT — read the relevant function/class in the live file first, implement against the live shape, flag the divergence:
> ```python
> max(int(i["id"]) for i in items)  # live items are dicts: item["id"]
> # the recipe's _load_index is not present in the live file — use the live index-loading path; note the divergence
> ```

### 7.3c — System-consistent value beats recipe literal — flag the divergence

Where the recipe's literal value conflicts with the live system — an enum, a template default, or a naming convention — the live system's value is the system-consistent choice. Copy the recipe's value only when the live system's authoritative check (the enum list, the constant, the template) confirms it is valid; otherwise implement the system-consistent value and flag the recipe's divergent literal in a deviation note rather than silently copying it.

> [!constraint] When a recipe literal is not in the live enum/template, implement the system value and flag it
> WRONG — copy the recipe literal verbatim, injecting a value the live system rejects:
> ```
> # recipe: new-item --status should default to "Open"
> --status "Open"   # "Open" is not a member of the live status enum
> ```
> CORRECT — implement the system-consistent value confirmed by the live enum + template default; flag the recipe's divergence:
> ```
> --status "NOT_STARTED"   # the live template default and a member of the status enum
> # recipe said "Open"; not a valid status — diverged + noted in a deviation comment
> ```

### 7.3d — Structured-data entries: derive from a same-class on-disk example; parser-load before close

When writing new entries to a self-describing structured file (YAML/JSON/TOML): (1) derive field values from an existing same-class on-disk entry rather than from the recipe/skeleton — the file's own declared enum sets and field names take precedence over a spec example; and (2) run a parser load as the mandatory final step of the editing task, not just a content grep. The parser load is the minimum exit criterion; a passing grep does not prove a schema-valid file.

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

> [!verify] Parser-load is the mandatory final step of any YAML/JSON/TOML edit
> ```bash
> python -c "import yaml; yaml.safe_load(open('{file}'))"
> # Must return without error. Then confirm each written value is a member
> # of the enum block declared at the top of the file.
> ```

#### Reviewer Check 066 — Fix-Task Execution-Time Fidelity (§7.3a–§7.3d)

- **Severity / Role / Type:** BLOCKER/WARNING (tiered) | Task Reviewer | NEW
- **What:** For any fix task whose target file lives cross-repo (a Required Context row annotated `BINDING SOURCE — full read required`), the Execution Steps MUST exhibit execution-time fidelity discipline: (a) a Step-1 canonical-file full-read gate (also enforced by the §7.5 compliance grep); (b) re-locate-by-content language — later steps locate edits by heading text / function name / unique anchor string, with no naked recipe line/step number presented as the authoritative edit target; (c) for any YAML/JSON/TOML edit, a parser-load success criterion (e.g. a `yaml.safe_load` / `json.load` gate) in Success Criteria, not just a content grep. Non-cross-repo fix tasks are out of scope (§7.6 exemptions).
- **Detection:**
  1. Identify fix tasks with a Required Context row annotated `BINDING SOURCE` (cross-repo canonical target). If none, the check is a no-op for that task.
  2. (a) Grep Execution Step 1 for the full-read gate (`Read .* in full before any fix reasoning`). Absent → BLOCKER.
  3. (b) Grep later Execution Steps for a naked recipe line/step reference (`line \d+`, `Step \d+\.\d+`, `L\d+`) used as the edit target without an accompanying content anchor (heading text / function name / unique string). Present without anchor → WARNING.
  4. (c) If Expected Output or Execution Steps touch a `.yaml`/`.yml`/`.json`/`.toml` file, grep Success Criteria for a parser-load gate (`safe_load`, `json.load`, `tomllib`, or equivalent). Absent → WARNING.
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

After `/planwise plan --scaffold` produces fix-task files for a plan whose target files live cross-repo, the planner / reviewer MUST run:

> [!verify] Cross-repo fix-task BINDING SOURCE + Step-1 compliance check
> ```bash
> # Each fix-task file MUST return at least one match for both patterns.
> # Adapt the glob to your plan's abbreviation + sprint/session/task layout:
> grep -lE "BINDING SOURCE . full read required" \
>   {planwise_root}/{plans_dir}/{PlanName}/Sprint-*/Session-*/{Abbrev}-S*-*-*-*.md
> grep -lE "Read .* in full before any fix reasoning" \
>   {planwise_root}/{plans_dir}/{PlanName}/Sprint-*/Session-*/{Abbrev}-S*-*-*-*.md
> ```
>
> Any fix-task file missing either pattern is non-compliant; the scaffolding agent MUST regenerate it. `/planwise review` SHOULD codify this check in its Error Pattern Catalog at BLOCKER severity when the plan's target files live cross-repo.

### 7.6 Exempt task types

§7.2 and §7.3 apply to **FIX tasks** — Sonnet (or general-purpose) agents performing code/markdown edits on cross-repo canonical files. The following task types are exempt:

| Exempt task type | Reason |
|------------------|--------|
| Human-gate decision tasks | The "fix" is a human conversation (release-target choice, scope decision, gate approval); no canonical-file read required at decision time. The follow-up Sonnet edit task IS subject to the rules. |
| Cumulative-diff triage by Opus | When Opus reads the cumulative plan diff (already-applied changes) for a sprint-end readiness signal, the diff itself is the source of truth at that point. Opus may consult canonical files as needed but is not bound by the Step-1-full-read mandate. |
| Audit / discovery / research tasks | Tasks whose output is a findings report, a Consolidated Context Part, or an EI extraction. These are read-only against canonical files; `verify-discovery-consolidation.md` §6 already covers their drift discipline. |
| Tasks whose target file lives inside the working planwise repo | §7 applies to **cross-repo** canonical files. For files inside the same repo as the plan (`{planwise_root}/{plans_dir}/...`, `src/...`, etc.), the standard Required Context discipline and `verify-discovery-consolidation.md` §6 verify-during-consolidation discipline are sufficient. |

All other cross-repo fix tasks MUST comply.

### 7.7 Applies-to surface

§7 binds for plans where the target plugin / package / artifact lives in any of these locations:

- A sibling repo cloned into a gitignored subfolder of the working tree (e.g., a vendored upstream plugin source, an integration test harness checkout, a docs-as-code mirror)
- An out-of-tree path on the consumer's machine reachable only via `additionalDirectories` configuration
- An upstream package cache or vendor extraction whose live state may diverge from the snapshot captured in audit excerpts

The `verify-against-shipped-artifact.md` §3g internal-placement check (the project's own scoped-rules registry) is the in-repo analog of §7; together they cover both axes of "the spec quotes a file path; the agent must verify against the live destination, not the spec snapshot."

---

*Companion files: [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md), [verify-discovery-consolidation.md](verify-discovery-consolidation.md), [verify-backlog-citation-freshness.md](verify-backlog-citation-freshness.md).*
