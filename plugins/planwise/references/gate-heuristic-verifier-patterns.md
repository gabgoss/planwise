---
description: A verification gate's match pattern is derived from the property, never from convenience of measurement — per-unit existence assertions over anchored aggregate counts (§2, Check 058), match patterns cross-read from every sibling extraction format (§3), a coverage denominator scoped to real instances (§4, Check 059), a bare "condition ⇒ defect" heuristic stated with its exclusions (§9), and a counting predicate that names its unit and states both counts when a boundary mints the thing counted (§13).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Heuristic Verifier Patterns (Match Sets, Formats, Denominators, Exclusions, Units)

**Purpose:** Rules for the match pattern of a verification task whose body is a grep or awk pattern plus a count or coverage threshold. The pattern's match set must be the property's extension, and the four failure shapes in §1 are what happens when it is not. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you author or review a verification task built on a count threshold, a coverage ratio, a keyword-proximity heuristic, or a bare "condition ⇒ defect" rule handed to a runner. Read §13 when a predicate asserts a count of sessions, boundaries, files, rows or events.

## Table of Contents

- [1. Failure Shape — Heuristic Verifiers Producing False Verdicts](#1-failure-shape--heuristic-verifiers-producing-false-verdicts)
- [2. Per-Unit Existence Assertions, Not Aggregate Count Thresholds](#2-per-unit-existence-assertions-not-aggregate-count-thresholds)
- [3. Match Patterns Derived From Sibling Extraction Tasks](#3-match-patterns-derived-from-sibling-extraction-tasks)
- [4. Denominator Scoping — Count Real Instances Only](#4-denominator-scoping--count-real-instances-only)
- [9. A bare heuristic in a task brief must state its exclusions](#9-a-bare-heuristic-in-a-task-brief-must-state-its-exclusions)
- [13. A Predicate That Counts Names Its Unit](#13-a-predicate-that-counts-names-its-unit)

---

## 1. Failure Shape — Heuristic Verifiers Producing False Verdicts

Two recurring failure modes in verification-task specs share one root cause: a match pattern that *approximates* the intent is shipped as a pass/fail gate without checking it against the actual output formats the sibling extraction tasks produce.

| Anti-Pattern | Symptom | Cost |
|--------------|---------|------|
| Anchored aggregate count threshold (`grep -cE '^…' … expect ≥N`) | Verifier reports Actual<Expected yet marks PASS with arithmetic fudging, OR marks FAIL when source format produced fewer matchable instances than the threshold requires | Orchestrator hand-reconciles every flagged row; downstream tasks blocked or, worse, allowed to proceed on a fudged PASS |
| Keyword-proximity coverage gate (`grep -B1 keyword \| grep -c tag`) | Verifier reports `N/M` with `M` inflated by prose mentions, table headers, fenced pseudo-code; emits hard BLOCKER on zero genuine misses | Sibling tasks routed back for rework that is not needed; orchestrator must read source to adjudicate |

Both anti-patterns also share a secondary defect: when Actual contradicts Expected, the verifier either fudges to PASS or emits a hard BLOCKER instead of returning FAIL or `[UNCERTAIN]` for orchestrator adjudication. §2-§4 below and §5-§6 in [gate-verdict-contract-and-adjudication.md](gate-verdict-contract-and-adjudication.md) state the binding rules that prevent each collapse.

## 2. Per-Unit Existence Assertions, Not Aggregate Count Thresholds

> [!constraint] Verification tasks MUST assert existence per unit, not aggregate counts over an anchored regex
> WRONG — a single anchored regex with a count threshold sweeps the file once and ships the count as the verdict. If the sibling extraction tasks produce more than one output format (line-start vs backtick-wrapped vs `{PLACEHOLDER}`-substituted), the threshold is structurally unreachable.
> ```bash
> grep -cE '^\[(BLOCKER|ERROR|WARNING|INFO)\]' {file}   # expect ≥{N}
> ```
> CORRECT — enumerate the units the verifier is checking, assert the property holds for each unit individually. The aggregate count, if needed, is *derived* from the per-unit results — not from a single regex sweep.
> ```bash
> # Per-unit: for each ### Check NNN block, assert it contains at least one
> # severity token in any accepted form (concrete word OR placeholder).
> awk '/^### Check [0-9]/{block=$0; next} /^---$/{ ... emit block + match check ... }'
> ```

A count-threshold whose target is structurally unreachable is a **spec bug**, not a verifier failure. The fix is to rewrite the verification step as a per-unit existence assertion, not to relax the threshold.

`scripts/lint_verification_gates.py` detects two shapes of this class in a task file. Check 15 fires on an anchored `grep -c '^…'` gate whose threshold is two or more. Check 10 fires on a `grep -c <one word>` gate over a Markdown file against such a threshold, because `grep -c` counts lines and a soft-wrapped paragraph is one line.

#### Reviewer Check 058 — Verification Task Anchored Aggregate Count Threshold

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** A verification task MUST NOT ship an anchored aggregate count threshold (e.g., `grep -cE '^…' {file}` paired with `expect ≥N`) as its sole pass/fail gate. If sibling extraction tasks produce more than one output format for the measured construct, the threshold is structurally unreachable and the verifier will either FAIL incorrectly or fudge to PASS. Replace with per-unit existence assertions: enumerate the units the verifier is checking and assert the property holds per unit.
- **Detection:**
  1. For each task whose Objective contains verification-style language (`verify`, `count`, `coverage`, `expect ≥/≤`), open the Execution Steps and Verification Commands sections.
  2. Grep for the anchored-count pattern: a `grep -c…` or `grep -cE…` invocation paired with a comparator (`-ge`, `-le`, `≥`, `≤`) and a numeric threshold.
  3. Cross-read the sibling extraction tasks that write to the file the verifier scans; enumerate the output formats each produces.
  4. If ≥2 distinct formats exist AND the verifier's pattern is anchored (`^…` or a single format) → BLOCKER.
  5. If exactly 1 format exists AND the threshold is exactly equal to the produced count, also flag as WARNING (brittle to format drift).
- **Finding template:**
```
[BLOCKER] Verification task uses structurally unreachable anchored count threshold
File: {task file path} | Location: Verification Commands / Execution Steps
Issue: Verifier pattern `{anchored-grep}` paired with `expect {comparator}{N}`; sibling tasks produce {format_count} formats not all matched by the pattern
Fix: Replace with per-unit existence assertions per references/gate-heuristic-verifier-patterns.md §2 (enumerate units, assert per unit, derive aggregate from per-unit results) | Confidence: HIGH
```

## 3. Match Patterns Derived From Sibling Extraction Tasks

> [!constraint] Verification match patterns MUST accept every output format the sibling extraction tasks actually produce
> A verification command's pattern is a contract with the sibling extraction tasks. Before authoring the pattern, cross-read every sibling task that writes to the file the verifier scans, and enumerate every format the source content can take:
>
> - line-start (`^[TAG]`)
> - backtick-wrapped mid-sentence (`` `[TAG] …` ``)
> - placeholder-substituted (`[{PLACEHOLDER}]`)
> - inline within a paragraph
>
> WRONG — author the verifier's regex against the format you happen to remember, ship without cross-reading. Whatever sibling task uses a different format silently fails the gate.
>
> CORRECT — the verifier's pattern accepts every enumerated format, OR the verification step is split per-format so each can be asserted independently.

> [!practice] Cross-read discipline
> When authoring a verification step that scans a file produced by N sibling tasks, the authoring sequence is:
>
> 1. Open every sibling task that appends content to the target file.
> 2. Enumerate the formats each produces (one row per format).
> 3. Design the verifier's pattern to match the union, OR design N per-format verifiers.
> 4. Document the format enumeration in the verification task's `## Required Context` so a reviewer can validate the union without re-deriving it.

## 4. Denominator Scoping — Count Real Instances Only

> [!constraint] A coverage check is only valid if its denominator counts real instances of the measured construct
> A coverage check has the shape `tagged / total ≥ threshold`. The denominator (`total`) MUST count actual occurrences of the thing being measured — NOT every line containing the keyword. Specifically exclude:
>
> - prose that *describes* the construct
> - table headers and column captions
> - fenced code blocks illustrating the construct
> - pseudo-code blocks naming the construct
>
> WRONG — denominator from a bare keyword grep:
> ```bash
> tagged=$(grep -B1 '{keyword}' {file} | grep -c '{tag}')
> total=$(grep -c '{keyword}' {file})            # inflated by prose & pseudo-code
> [ "$tagged" -ge "$total" ]                     # structurally guaranteed false negative
> ```
>
> CORRECT — denominator scoped to real call sites:
> ```bash
> # Match the construct's invocation pattern (e.g., tool-call shape, function-call shape),
> # exclude fenced code blocks (awk between ``` fences), exclude table rows (skip | columns).
> total=$(awk '!/^```/{...exclude fenced...} !/^\|/{...exclude tables...} /<invocation pattern>/' {file} | wc -l)
> ```
>
> If the denominator cannot be made precise (e.g., the construct's invocation shape varies and excluding prose is infeasible), the check is **NOT** a pass/fail gate. Re-classify it as an `INVESTIGATE` signal and surface the ambiguity to the orchestrator instead of emitting FAIL.

A denominator counted in the artifact being gated cannot detect an item nobody scoped. See [gate-denominator-integrity.md](gate-denominator-integrity.md) §3. A predicate that counts also names its unit: see §13 below.

#### Reviewer Check 059 — Verification Task Keyword-Proximity Coverage Gate

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** A verification task MUST NOT ship a keyword-proximity heuristic (e.g., `grep -B{N} keyword {file} | grep -c tag`) paired with a coverage-ratio denominator from a bare keyword grep (`grep -c keyword`) as its pass/fail gate. The denominator is inflated by prose, table headers, and fenced pseudo-code that mention the keyword without invoking the construct, and the proximity bound (`-B1`, `-A1`) misses correctly-tagged sites whose tag sits 2+ lines away. Replace with explicit-site enumeration: verify the spec's enumerated anchors are tagged, do not re-derive the site set from a keyword grep.
- **Detection:**
  1. Grep Verification Commands and Execution Steps for the proximity-gate shape: `grep -[BA]\d+ '{keyword}'` piped to `grep -c '{tag}'`, paired with a denominator `grep -c '{keyword}'` and a coverage comparator (`-ge`, `-eq`).
  2. If the bare denominator `grep -c '{keyword}'` is used AND the file under scan is a prose document (`.md`) — denominator includes prose / table rows / fenced code → BLOCKER.
  3. If the spec lists the explicit sites (e.g., an EI repoint map or an edit-group list) AND the verifier instead uses a keyword grep → BLOCKER (the spec's enumerated sites are the ground truth; verify them by anchor).
  4. Also flag: any verification step that maps `Actual<Expected` to BLOCKER directly without an `INVESTIGATE` escalation path → ERROR (denominator may be inflated; missing adjudication path forces false rework).
- **Finding template:**
```
[BLOCKER] Verification task uses keyword-proximity coverage gate with inflated denominator
File: {task file path} | Location: Verification Commands / Execution Steps
Issue: Verifier uses `grep -B{N} '{keyword}' | grep -c '{tag}'` over denominator `grep -c '{keyword}'`; denominator counts prose/table/fenced-code mentions, proximity bound misses tags ≥2 lines away
Fix: Replace with explicit-site enumeration per references/gate-heuristic-verifier-patterns.md §4 (verify the spec's enumerated anchors by name, scope denominator to real construct instances, or re-classify as INVESTIGATE if denominator cannot be made precise) | Confidence: HIGH
```

## 9. A bare heuristic in a task brief must state its exclusions

> [!constraint] A bare "condition X ⇒ defect" heuristic handed to a runner MUST state its exclusions in the same block
> A rule of the form "condition X ⇒ defect" is normally correct only after exclusions are applied. Stated bare in a task brief, it fires on every legitimately-excluded case, and each firing reads as a defect in work that is correct. When a brief hands a runner a rule of this shape, it MUST state, in the same block, the conditions under which X is expected and is **not** a bug.
>
> WRONG: "Any newly-wired column at 0 non-NULL is a wrong-key finding."
> CORRECT: "Any newly-wired column at 0 non-NULL is a wrong-key finding, EXCEPT where: the source is recorded absent in the reconciliation's evidence tier (expected NULL, not a failed fix); the value is conditional on state not present in the sampled window; the column is wired ahead of a producer that has not yet run. For each exclusion the runner cites the evidence row that establishes it."
>
> A runner who hits an excluded case with the bare rule in hand has three options, two of them bad: report a false defect, silently ignore the rule, or spend an investigation re-deriving the exclusion. Only the third is safe, and it is the most expensive.

**Applies to:** task briefs that hand a runner a bare "condition ⇒ defect" heuristic — distinct from §1's failure-shape table, which covers heuristic *verifiers* (structurally-unreachable count thresholds, keyword-proximity coverage gates) living inside verification commands. §9 covers a *correct* heuristic applied without its exclusions — a different failure shape, arising in task briefs rather than verification commands. This section reserves no further top-level number.

## 13. A Predicate That Counts Names Its Unit

A count without its unit is a prediction about the author's mental model. The reader cannot tell a wrong model from a wrong run. The count was right for the thing the author pictured and wrong for the thing the sentence named. A grader forbidden from adjusting predicates can only record the mismatch.

This section extends the denominator discipline of §4 above ("Denominator Scoping — Count Real Instances Only"), which scopes a denominator to real instances. It adds the step before that scoping: say what the instance is. See also [gate-denominator-integrity.md](gate-denominator-integrity.md) ("Take the denominator from outside the artifact being gated").

> [!constraint] Name the unit, state both counts when a boundary mints the thing counted, and grade against the named unit
> **Example.** A sheet's predicate read "the log should show three distinct session ids". The arm runs a clear after each of three finished steps, and each clear starts a new session id. The author counted the clears and wrote the number as ids. The log showed four ids: the original session plus one per clear. Every other count was three: three clears, three notices, three nonces, three command rows. The runner recorded "not held" with the measured count and a paragraph explaining that "three" most plausibly meant clears. A passing run now carries a not-held clause that a downstream write-up has to adjudicate from prose.
>
> Three consequences:
>
> - **Name the unit in the predicate, and name the off-by-one when a boundary creates the thing counted.** "Three clear boundaries, four session ids (the original plus one per clear)" costs eleven words and removes the ambiguity.
> - **When two units are in play, state both counts.** Boundaries and the sessions they produce differ by exactly one. A predicate that gives both is checked in both directions.
> - **Grade the measured count against the named unit, never the intended one.** The fix belongs upstream in the sheet, not in a grader that learns to guess.
>
> WRONG — the unit named is not the unit counted:
> ```
> predicate: "three distinct session ids"          <- author counted clears
> measured:  4 ids (<id-a>, <id-b>, <id-c>, <id-d>)
> verdict:   not held, 4 != 3                      <- on a run that did what the arm designs
> ```
> CORRECT — both units, both numbers, the off-by-one stated:
> ```
> predicate: "three clear boundaries; four distinct session ids
>             (the original session plus one new id per clear)"
> measured:  3 clear-command rows; 4 ids
> verdict:   held, held
> ```

**Applies to** run sheets, design predicates and success criteria that assert a count of sessions, boundaries, files, rows or events. It matters most where an action mints the thing being counted: a boundary that creates a session, a split that creates a part, a retry that creates a record. A reviewer checking a plan's predicates asks "count of what, and does the initial state count as one?"

---

*Cross-references: [gate-verdict-contract-and-adjudication.md](gate-verdict-contract-and-adjudication.md) (§5-§6, what the verifier returns when Actual contradicts Expected, and how a BLOCKER raised from one of these heuristics is adjudicated) · [gate-denominator-integrity.md](gate-denominator-integrity.md) §3 (the denominator comes from outside the artifact being gated) · [ei-completeness.md](ei-completeness.md) §9 (EI completeness and audit-grep-table coverage — feeds the format enumeration §3 relies on) · [verification-task-authoring.md](verification-task-authoring.md) (the family index and the §7 authoring checklist).*
