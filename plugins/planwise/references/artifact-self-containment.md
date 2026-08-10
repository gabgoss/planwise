---
description: Binding rule — content-bearing artifacts (rules, agents, skills, handlers, CLAUDE.md callouts, BB rule-design sections) MUST inline content from source lessons and backlog items, never cite them. Bookkeeping artifacts (indexes, promotion logs, frontmatter pointers, BB Notes) MAY carry cross-references for traceability.
---

# Artifact Self-Containment

When a lesson (`LL-NNN`) is promoted into a rule, agent, skill, handler, or CLAUDE.md callout, the destination artifact MUST inline the lesson's content — every WRONG/CORRECT example, recipe, and verification command — verbatim or in faithful paraphrase. The same holds when a backlog item (`BB-NNN`) is executed and produces rule/agent/skill/handler/CLAUDE.md content. The destination becomes the canonical source of the rule; the originating lesson or BB becomes archival.

This rule applies in BOTH directions:

1. Rules, agents, skills, handlers, and CLAUDE.md callouts NEVER cite `LL-NNN` or `BB-NNN`.
2. The §1-§N "rule design" deliverables inside a promotion BB NEVER lazy-cite the source lessons — the content is restated. The grep gate in §4 catches drift back into cross-references during execution.

---

## Table of Contents

- [1. Why](#1-why)
- [2. The Asymmetry — Inlined vs Cross-Refs-Allowed](#2-the-asymmetry--inlined-vs-cross-refs-allowed)
- [3. WRONG / CORRECT Examples](#3-wrong--correct-examples)
- [4. Mechanical Verification](#4-mechanical-verification)
- [5. Single-Lesson Promotion Integration](#5-single-lesson-promotion-integration)
- [6. Backlog Item Execution Integration](#6-backlog-item-execution-integration)
- [7. Exemptions](#7-exemptions)

---

## 1. Why

A rule that says *"per LL-NNN, every task must include a Schema Pin (see LL-NNN for examples)"* forces every reader — and every future consumer of the installed plugin — to chase a separate file to recover the actual rule content. When that lesson is renumbered, archived, moved between projects, or simply never existed for the consumer (because the citation came from another repo entirely), the reference dangles and the rule loses its meaning.

The same logic applies to backlog citations. A rule that says *"see BB-NNN P4 for the bidirectional consistency check"* is project bookkeeping leaking into shipped rule prose. The rule must stand alone.

A rule that inlines its source content survives copy-paste, plugin re-distribution, lesson re-numbering, and project-to-project migration. A rule that cites does not.

---

## 2. The Asymmetry — Inlined vs Cross-Refs-Allowed

Not every artifact is a content-bearing artifact. The rule above forbids `LL-NNN` / `BB-NNN` citations in the content body of rule-like artifacts; it explicitly ALLOWS cross-references in artifacts whose entire purpose is traceability.

> [!constraint] Artifact Class Determines Allowed Citations
> WRONG — citing `LL-NNN` or `BB-NNN` inside the content body of these artifact classes:
>
> | Artifact Class | Examples |
> |----------------|----------|
> | Rules | `.claude/rules/**/*.md` |
> | Agents | `.claude/agents/**/*.md` |
> | Skills | `.claude/skills/**/*.md`, `.claude/skills/**/SKILL.md` |
> | Handlers / Commands | `.claude/commands/**/*.md`, plugin `handlers/**/*.md` |
> | CLAUDE.md callouts | `> [!binding]`, `> [!constraint]`, and other callouts anywhere in `CLAUDE.md` |
> | BB rule-design / Deliverables sections | the §1-§N sections of a promotion BB that specify the rule body to write |
>
> CORRECT — cross-references for traceability ARE allowed (and expected) in:
>
> | Artifact Class | Examples |
> |----------------|----------|
> | LessonsLearned index | `{lessons_dir}/00-Index-LessonsLearned.md` — Master Table title/description, Rule Promotion Log |
> | Backlog index | `{backlog_dir}/00-Index-Backlog.md` — Feature/Title column, Dependencies notes |
> | Lesson frontmatter | `applied-as:`, `promoted-to:`, `promotion-target:`, `promoted-date:`, the deprecated `rule-as:`, related-lesson links — field semantics are defined once in `seed/00-Index-LessonsLearned.md` (Pointer Fields) |
> | BB header metadata | `Closes: LL-NNN`, `Related: BB-NNN`, `Source: LL-X + LL-Y` lines ABOVE the Deliverables section |
> | BB Notes section | "Out of scope: LL-X, LL-Y …", "Decomposed across: BB-{P}, BB-{Q}" |
> | Project changelog / release notes | the "Lessons folded in" / "BBs shipped this release" block at the bottom of `README.md` or `CHANGELOG.md` |

The asymmetry is deliberate. Content-bearing artifacts must read as standalone rules that survive being copied into any project, any plugin install, any documentation viewer. Bookkeeping artifacts exist BECAUSE the cross-refs serve traceability — strip those refs and the audit trail vanishes.

---

## 3. WRONG / CORRECT Examples

### 3.1 Rule body must inline, not cite the source lesson

> [!constraint] Rule Body Self-Containment
> WRONG — rule body cites the source lesson, leaving the lesson as a load-bearing reference:
> ```markdown
> ## §1. Schema Pin requirement
> Per LL-X, every task file must include a Schema Pin (see LL-X for the
> WRONG/CORRECT examples and the construction recipe).
> ```
> CORRECT — rule body inlines every WRONG/CORRECT example, recipe, and command from the source lesson(s). The lesson file becomes archival and is NOT cited from the rule body:
> ```markdown
> ## §1. Schema Pin requirement
> Every task file whose Required Context references a DB table MUST include
> a Schema Pin section.
> WRONG: the brief asserts column shapes from the author's mental model.
>     {full WRONG SQL example inlined verbatim from the lesson body}
> CORRECT: the brief includes a Schema Pin section quoting actual columns.
>     {full CORRECT example inlined verbatim from the lesson body}
> ```

### 3.2 CLAUDE.md callouts describe the reason, not the source ID

> [!constraint] CLAUDE.md Callout Reasoning
> WRONG — callout reasons by lesson ID, leaving the reader to chase the citation:
> ```markdown
> > [!binding] Verbatim Extraction
> > Reason: LL-X (verbatim-extraction failure) — see lesson for examples.
> ```
> CORRECT — callout states the reason in plain language and points at the RULE that encodes it:
> ```markdown
> > [!binding] Verbatim Extraction
> > Reason: an Execution Input that cites a "Consolidated Context part" as
> > authoritative MUST carry the full prose, not just a Cross-References row.
> > See `.claude/rules/{path}/verbatim-extraction.md` §2.
> ```

### 3.3 Rules / agents / handlers must not cite backlog items either

> [!constraint] No BB Citations in Content Artifacts
> WRONG — an agent check definition cites a project backlog item as its source:
> ```markdown
> ### Check 042 — Bidirectional EI Consistency
> - **Source:** BB-NNN P4
> - **What:** every Spec in `Extracted from:` MUST appear in Cross-References.
> ```
> CORRECT — agent check definition stands on its own, sourced (if anywhere) from a sibling plugin reference file (`references/*.md §`) or the rule it enforces:
> ```markdown
> ### Check 042 — Bidirectional EI Consistency
> - **Source:** `references/ei-citation-and-token-reconciliation.md` §8.1
> - **What:** every Spec in `Extracted from:` MUST appear in Cross-References.
> ```
> A `Source:` value must be a plugin-internal anchor that ships with the plugin — a sibling `references/*.md §` section, or the rule the check enforces. Do NOT use an external bookkeeping ID (`LL-NNN`, `BB-NNN`, `BLI-NNN`, `PLG-NNN`, `D-NNN`): these point at lessons / backlog items / decisions in this or another project's authoring repo that a downstream consumer cannot resolve.

### 3.4 Bookkeeping artifacts SHOULD carry cross-refs

> [!practice] Bookkeeping Cross-Refs Are Encouraged
> The Rule Promotion Log, the lessons Master Table, the backlog Master Table, the lesson `applied-as:` field, and the BB "Closes:" header all SHOULD carry cross-refs:
> ```markdown
> | Date       | Lesson ID | Artifact Created                         | File                                      |
> |------------|-----------|------------------------------------------|-------------------------------------------|
> | YYYY-MM-DD | LL-NNN    | `.claude/rules/{name}.md` §1            | `[link]({lessons_dir}/Archive/LL-NNN…md)` |
> ```
> These citations exist to answer "where did this rule come from?" — strip them and traceability is lost. The constraints in §3.1-§3.3 cover rule prose, not the audit trail.

---

## 4. Mechanical Verification

Every BB that produces content-bearing artifacts MUST include a self-containment grep in its Acceptance Criteria. The grep covers ALL external-bookkeeping ID families — `LL-`, `BB-`, `BLI-`, `PLG-`, `D-` — across ALL content-bearing artifact paths the BB touched.

> [!constraint] Which Copy Is Canonical — This File's Own Double-Ship
> This file itself ships twice on disk: an in-place reference copy (what you are reading)
> and an installed, path-scoped copy that injects the discipline during artifact authoring.
> The reference copy is the **single canonical source** — the grep below always reads the
> reference copy in place, never the installed copy. The installed copy is
> **injection-only**: it exists solely so this discipline auto-loads while a consumer
> authors a rule/agent/skill/command artifact; it is never read as a source by other code.

> [!verify] Self-Containment Grep
> ```bash
> # Bash / POSIX — replace {paths-touched} with the actual files this BB wrote:
> grep -rnE '(LL-[0-9]|BB-[0-9]|BLI-[0-9]|PLG-[0-9]|\bD-[0-9]|\b(LL|BB|BLI|PLG)([A-Z][a-z]|[0-9]))' \
>   .claude/rules/{paths-touched} \
>   .claude/agents/{paths-touched} \
>   .claude/skills/{paths-touched} \
>   .claude/commands/{paths-touched} \
>   CLAUDE.md
> # MUST return zero matches.
> ```
>
> ```powershell
> # PowerShell (Windows shells):
> Get-ChildItem -Path .claude/rules, .claude/agents, .claude/skills, .claude/commands, CLAUDE.md `
>   -Recurse -Include *.md `
>   | Select-String -Pattern '(LL-\d|BB-\d|BLI-\d|PLG-\d|\bD-\d|\b(LL|BB|BLI|PLG)([A-Z][a-z]|\d))'
> # MUST return zero matches.
> ```

If grep returns matches, the BB executor MUST inline the cited content into the rule body or remove the reference. The check is binary — any `LL-`, `BB-`, `BLI-`, `PLG-`, or `D-` reference in any content-bearing artifact is a fail.

**Why the alternation carries a second, hyphen-less clause.** A prefix pattern written only as `{PREFIX}-[0-9]` matches the *citation* spelling of an identifier and nothing else. The same identifier reaches a shipped file just as often glued into a file name — `…-{PREFIX}SomeTopicName.md`, no hyphen and no digit — so a narrow pattern returns empty on a file that is visibly leaking. The `\b(LL|BB|BLI|PLG)([A-Z][a-z]|[0-9])` clause covers the PascalCase-continuation and run-together-digit spellings for every prefix in the family. It deliberately does NOT fire on the plugin's own vocabulary: a bare `BLI`, the `BLI-{NNN}` template placeholder, and prose plurals like "BBs shipped" all lack the required following character class. Widening the pattern without widening the **classification** step below converts a silent miss into a noisy blanket-fail — so treat every hit from the second clause as a candidate to classify per §4.2, not an automatic failure.

### 4.1 What the grep deliberately does NOT cover

The grep scans content-bearing artifact zones only. It deliberately does NOT scan:

| Zone | Why exempt |
|------|-----------|
| `{lessons_dir}/**` | The Master Table, Rule Promotion Log, and lesson frontmatter all carry cross-refs by design. |
| `{backlog_dir}/**` | BB Notes, BB header metadata, and the backlog index Dependencies notes all carry cross-refs by design. |
| `README.md` Changelog / "Lessons folded in" / "BBs shipped" sections | Historical traceability at the document bottom. The user can read it and decide if it is still useful; it does not load-bear the rule prose. |

### 4.2 Scope the grep to the promoted content; classify pre-existing whole-file hits

A promotion BB's self-containment grep verifies that **the content the BB promotes** is self-contained. It does NOT automatically mean "every pre-existing cite in the destination file must be removed." A destination rule may already carry a §References section, and `CLAUDE.md` may carry a routing/index table whose provenance column is intentional (§3.4/§4.1). Taken as a literal whole-file zero-match check, the §4 grep can be **impossible to satisfy as written** — not because of any defect in the promoted content, but because the destination already contained exempt or pre-existing hits the BB neither authored nor scoped for removal.

> [!protocol] Scope the Grep to the Promoted Content; Classify Pre-Existing Hits
> 1. **Scope the grep mentally to the promoted sections.** Confirm the *new* §/checklist/callout content carries zero `LL-`/`BB-` cites (a sibling-rule relative link like `[some-rule.md](some-rule.md)` is allowed; an `LL-NNN`/`BB-NNN` ID in the body is not). That is the binding pass.
> 2. **Classify every remaining whole-file hit** into: (a) exempt `lessons:` / `closes:` frontmatter provenance; (b) pre-existing content the BB did not touch; (c) intentional bookkeeping/routing tables (e.g. the `CLAUDE.md` rules routing index) that §3.4/§4.1 treat as encouraged traceability.
> 3. **Decide pre-existing cleanup EXPLICITLY — don't silently gut it.** Removing a pre-existing References section or a routing table destroys intentional traceability and is usually outside the BB's scope. Surface the discrepancy at the VERIFY gate and let the human choose between "promoted content is self-contained, leave pre-existing as-is" vs. "also clean the pre-existing cites in this file."

> [!practice] Write the Promotion BB's Grep Criterion to Match Reality
> When authoring a promotion BB's grep Acceptance Criterion, write it so it can actually pass: scope its file list/paths to exclude zones that legitimately carry cross-refs, OR annotate the criterion with the expected exempt/pre-existing hits. Otherwise the executor is forced to choose between an impossible literal pass and an unscoped destructive cleanup.

### 4.3 Widen the Gate to Plan-Structure Names — Semantic vs Syntactic Leaks

The §4 grep matches ID-shaped bookkeeping tokens (`LL-`, `BB-`, `BLI-`, `PLG-`, `D-`). But the isolation rule this file enforces covers a **semantic** class — *any name that only resolves inside the authoring repo* — while that grep tests only a **syntactic** one (dash-number IDs). A plan-structure name such as a resolved sprint folder `Sprint-N`, or the executing plan's abbreviation, is exactly as unresolvable to a marketplace consumer as a bookkeeping ID — yet it is not ID-shaped, so it passes a green gate and leaks.

> [!constraint] Add a Second Pattern for Plan-Structure Names — Both Greps Must Be Empty
> WRONG — a single ID-shaped grep passes on a real leak. A shipped comment like
> `# customization until Sprint-N's transfer flow exists` (with a *resolved* sprint number)
> passes clean:
> ```bash
> git diff plugins/planwise/ | grep -E '^\+' | grep -E '(LL-[0-9]|BB-[0-9]|BLI-[0-9]|PLG-[0-9]|\bD-[0-9])'
> ```
> CORRECT — register untracked files, assert the input set, then run TWO patterns; both must return empty:
> ```bash
> git add -N $(git status --porcelain plugins/planwise/ | awk '/^\?\?/{print $2}')   # 1. register
> git status --porcelain plugins/planwise/ | grep -c '^??'      # 2. MUST be 0
> git diff --name-only plugins/planwise/ | wc -l                # 3. MUST equal the expected file count
> git diff plugins/planwise/ | grep -E '^\+' | grep -E '(LL-[0-9]|BB-[0-9]|BLI-[0-9]|PLG-[0-9]|\bD-[0-9]|\b(LL|BB|BLI|PLG)([A-Z][a-z]|[0-9]))'
> git diff plugins/planwise/ | grep -E '^\+' | grep -E 'Sprint-[0-9]|{PLAN_ABBREV}-'
> ```
> `{PLAN_ABBREV}` is the executing plan's abbreviation, parameterised per plan (substitute the live abbreviation before running).
>
> Steps 1–3 are not optional decoration — they are what makes step 4's empty result mean anything. `git diff` does not report untracked files at all, so a promotion that ADDS a file gets an empty result from a pipeline that never saw the file's content, and an empty result that inspected nothing is indistinguishable from one that inspected everything. See `measurement-discipline.md` §8.7 *Verify the gate's input set before trusting its predicate*.

**Gate semantics:**

- `{PLAN_ABBREV}-` hits are **always** leaks — a plan abbreviation resolves only inside the authoring repo.
- `Sprint-[0-9]` hits are leaks **unless** the line is demonstrably the plugin's own template/example vocabulary — `templates/`, `examples/`, and `handlers/plan.md` legitimately show resolved sprint folder names (e.g. `Sprint-NN-{Name}`) as sample output of the tool itself. Inspect every hit; never ignore one silently.
- The `{Sprint-N}` template placeholder (no digit after the dash) stays legal — the pattern targets resolved numerals, not the placeholder.
- For plan sessions editing non-template plugin files (scripts, handlers, agents, references), expect strictly EMPTY.

**Both gates above are `^\+`-filtered, and that filter has a second blind spot.** They answer "did this change introduce a leak" — they cannot answer "does a leak exist". Anything that predates the diff base is a context line, never an added line, so it is invisible by construction and stays invisible across every subsequent session that reuses the same gate shape. A whole-tree audit or a release battery therefore needs one companion sweep that reads **files on disk**, not a diff:

> [!verify] Unfiltered On-Disk Sweep — Classify, Do Not Blanket-Fail
> ```bash
> # Whole-tree / release use. Reads the working tree, so pre-existing leaks are visible.
> grep -rnE '(LL-[0-9]|BB-[0-9]|BLI-[0-9]|PLG-[0-9]|\bD-[0-9]|\b(LL|BB|BLI|PLG)([A-Z][a-z]|[0-9]))' plugins/planwise/
> grep -rnE 'Sprint-[0-9]|{PLAN_ABBREV}-' plugins/planwise/
> ```
> This sweep is expected to return hits, and a non-empty result is NOT automatically a failure. Classify every hit into exactly one bucket before deciding:
>
> | Bucket | What it looks like | Disposition |
> |--------|--------------------|-------------|
> | Plugin's own scaffold vocabulary | `templates/`, `examples/`, `handlers/plan.md` showing resolved sample structure names, and sample abbreviations invented for the doc | False positive — leave it |
> | Rule text enumerating the forbidden forms | This file, and any prose that must *name* `LL-NNN` / `PLG-NNN` to ban them | False positive — leave it |
> | Declared §7 exemption | Command-syntax samples, seed starting state, template sample rows, bookkeeping frontmatter | False positive — leave it |
> | Anything else | A real authoring repo's abbreviation, its real artifact file names, a resolved sprint reference | **Leak — reword or inline** |
>
> The distinguishing question for the last two rows is whether the token names an artifact that exists in some authoring repo. An invented sample abbreviation in a format example is vocabulary; a real project's abbreviation attached to that project's real file names is a citation wearing an example's clothes.

**Dry-run every one of these gates against known-bad input before trusting it.** Run each gate once against a file that genuinely carries the pattern and once against a clean file; the two runs MUST produce different results. A gate that has only ever been run against clean input has never been shown to discriminate — and all three defects this section corrects (untracked blindness, `^\+` blindness, a too-narrow pattern) would have surfaced in a single such run.

### 4.4 Where the Displaced Note Goes — Banning the Reference Must Not Lose the Information

A plan-name comment usually exists because the code is in a deliberate interim state ("this stays conservative until a later flow lands"). Banning the plan name displaces that information; re-home it, do not drop it.

> [!practice] Re-Home the Interim Note in Three Places
> 1. **Code carries the condition.** The comment states the *generic condition* — true for any consumer regardless of the authoring plan: `# customization until a transfer-to-project-file flow exists`. Never the schedule.
> 2. **Plans carry the schedule.** At the same moment, record a Cross-Task Coordination Flag whose downstream consumer is the sprint that closes the gap, pointing at the code location **by symbol** (not line) and **quoting the interim comment text** so it is greppable.
> 3. **Flags carry the linkage.** The flag's Recommended Action tells the closing session to sweep the now-stale interim comments when its feature lands (grep for the quoted text).
>
> WRONG — delete the plan name and keep only the generic comment: the closing sprint never learns it owes a comment sweep, and the "until X exists" text quietly outlives X.
> CORRECT — generic comment in code + a flag row naming the closing sprint, the symbol, and the quoted comment text.

---

## 5. Single-Lesson Promotion Integration

The single-lesson promote flow (`handlers/lessons.md` Stage 4 Generate) writes one artifact file from one lesson. The same self-containment rule applies:

1. **Generate** the artifact with all WRONG/CORRECT examples, recipes, and verification commands from the source lesson inlined verbatim or in faithful paraphrase.
2. **Run the §4 grep** against the new artifact before completing Stage 4.
3. If matches → revise the artifact body to inline the cited content; do not proceed to Stage 5 (Update Frontmatter) until the grep returns zero.

This is the canonical version of the Stage 4 verification. The lesson frontmatter `applied-as:` pointer written at Stage 5 and the Rule Promotion Log row appended at Stage 7 are bookkeeping artifacts — they carry the `LL-NNN` reference, and that is correct.

---

## 6. Backlog Item Execution Integration

When a BB executes (via `/planwise backlog` Route A direct-fix, Route B task list, or Route C session plan) and the produced changes include edits under `.claude/rules/**`, `.claude/agents/**`, `.claude/skills/**`, `.claude/commands/**`, or `CLAUDE.md`, the Phase 5 VERIFY step MUST run the §4 grep on the produced diff before the BB can be marked COMPLETE.

Before treating any grep hit as a failure, classify it per §4.2: hits inside the BB's **promoted** content are blockers (inline the cited content or remove the reference); hits in exempt frontmatter, pre-existing untouched content, or intentional bookkeeping/routing tables are a human decision at the VERIFY gate, not an automatic revert.

If the grep finds (promoted-content) matches:

- **Route A (fix-agent direct fix):** mark VERIFY as failing, return the grep output to fix-agent, ask for an inlining pass.
- **Route B (task list):** open a follow-up task to inline the cited content; do not mark the BB COMPLETE until the follow-up passes.
- **Route C (session plan):** the produced plan SHOULD include a self-containment grep step in its own acceptance criteria; if the plan is already complete and the grep fails, file a follow-up BB.

A BB whose changes touch ONLY bookkeeping zones (the lessons index, the backlog index, lesson frontmatter, BB Notes) does NOT need the §4 grep gate.

---

## 7. Exemptions

A small set of cases need exemption from the §4 grep. When a BB needs one of these, declare it explicitly in the BB's Acceptance Criteria so the grep call is scoped or grep-excluded:

| Exemption | Pattern | Where it shows up |
|-----------|---------|-------------------|
| Command-syntax usage examples | `/planwise lessons promote LL-NNN` shown as a literal sample | `handlers/lessons.md`, `README.md` usage examples, skill `examples:` blocks |
| Seed template starting state | `Next available ID: LL-001` in a fresh project's lessons index | `seed/00-Index-LessonsLearned.md` and equivalents |
| Sample data rows in template docs | `| LL-NNN | Example Lesson Title | … |` in a "here is the index format" reference table | `handlers/lessons.md` template examples |
| Bookkeeping frontmatter cross-refs | `applied-as:`, `promoted-to:`, `promotion-target:`, and the deprecated `rule-as:` — lesson frontmatter fields pointing at the owning backlog item or promotion target, not content citations. Exempt regardless of which scheme a lesson was written under; see `seed/00-Index-LessonsLearned.md` (Pointer Fields) for what each field means | Lesson frontmatter across `{lessons_dir}/**`, including archived lessons |

Each exemption MUST be a sample/placeholder pattern, NOT a load-bearing cross-reference to recover content from a specific lesson or backlog item. If you find yourself adding an exemption to silence a grep hit that IS actually a citation, the fix is to inline the content — not to widen the exemption list.

---

*Cross-references: [lessons-promote-batch-workflow-Part-2-DraftAndWrite.md §5.2](lessons-promote-batch-workflow-Part-2-DraftAndWrite.md) (specialises this rule for the batch-promotion workflow), [callout-conventions.md](callout-conventions.md), [rule-authoring.md](rule-authoring.md).*
