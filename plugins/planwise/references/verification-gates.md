---
description: Sessions delivering IPC/protocol/codec layers MUST include round-trip evidence before COMPLETE; Sprint exit-gate verdicts reflect the gate-defining step's status, not a step-count percentage; build-clean ≠ computation-correct, build-fresh ≠ deploy-fresh, and runtime-correct-on-one-target ≠ all-targets for in-process numeric/codec and multi-target code
paths: {planwise_root}/{plans_dir}/**
---

# Verification Gates — Build-Clean Is Not Runtime-Correct

**Purpose:** Gate-discipline rules for planwise sessions whose deliverable creates or modifies a cross-process boundary (IPC layer, wire-protocol serialization, file-format codec). Codifies the two failure modes (build-clean ≠ runtime-correct; partial-PASS ≠ gate progress), the round-trip evidence requirement, the gate-is-the-gate Sprint Overview discipline, and the Recovery-vs-task-spec drift practice surfaced at closeout. Sections 5–7 extend the build-clean-is-not-enough principle past cross-process boundaries into in-process numeric/codec computation (§5), build-vs-deploy freshness (§6), and multi-target runtime parity (§7).

## Table of Contents

- [1. The Two Failure Modes](#1-the-two-failure-modes)
- [2. Round-Trip Evidence for Cross-Process Boundaries](#2-round-trip-evidence-for-cross-process-boundaries)
- [3. The Gate Is the Gate](#3-the-gate-is-the-gate)
- [4. Operational Rules for Smoke Reports](#4-operational-rules-for-smoke-reports)
- [5. Build-Clean ≠ Computation-Correct](#5-build-clean--computation-correct)
- [6. Build-Fresh ≠ Deploy-Fresh](#6-build-fresh--deploy-fresh)
- [7. Runtime-Correct on One Target ≠ Correct on All Targets](#7-runtime-correct-on-one-target--correct-on-all-targets)
- [8. Empirical Verification Discipline](#8-empirical-verification-discipline)

---

## 1. The Two Failure Modes

Two recurring planwise gate-discipline failures share one root cause: a verification signal that is **necessary but not sufficient** is being treated as the gate.

| Failure | Symptom | Cost |
|---------|---------|------|
| Build-clean session marked COMPLETE without runtime evidence | Defect introduced N sessions ago surfaces in the integration session | Diagnostic depth = N sessions of code stacked atop the original break |
| "M of N smoke steps PASS" framed as Sprint progress when the gate-defining step still fails | Master Plan / Summary suggests forward motion when the gate is still red | Misleads the next session author into deprioritizing the actual gate-blocker |

Both failures collapse a multi-signal verification surface into a single "looks green" reading. §2 and §3 below state the binding rules that prevent each collapse.

---

## 2. Round-Trip Evidence for Cross-Process Boundaries

> [!constraint] IPC / protocol / codec sessions MUST include round-trip evidence before COMPLETE
> WRONG — declare a session COMPLETE because `{build-cmd}` reports 0 warnings / 0 errors. `{build-cmd}` proves the code COMPILES; it does NOT prove the code RUNS. Defects in IPC handshakes, wire-protocol serialization, and file-format codecs lurk through every static check and surface only at first contact with reality.
> ```markdown
> ## Verification
> - {build-cmd} → 0 W / 0 E ✅
> - All unit tests pass ✅
> - Session-02: COMPLETE
> ```
> CORRECT — at least one round-trip exercise of the boundary, of any of three forms (see picker below):
> ```markdown
> ## Verification
> - {build-cmd} → 0 W / 0 E ✅
> - All unit tests pass ✅
> - Round-trip: IPC client connects to the transport, sends a probe payload,
>   receives a non-empty response ({test-path}) ✅
> - Session-02: COMPLETE
> ```

> [!decide] Pick a round-trip evidence form
> | If... | Use |
> |-------|-----|
> | The boundary can be exercised in-process with paired stub transports | **In-process integration test** — fast, automatable, cheap to re-run |
> | The boundary requires a host application or external runtime (host process, browser, embedded shell) | **Manual smoke step** with documented commands and expected output, captured in the session Summary |
> | Neither is feasible this session | **Round-trip unit test stub** that opens the real transport and asserts a non-empty response — even if the response is just "I received N bytes" |

**Applies to:** any session whose deliverable creates or modifies an IPC layer (sockets, pipes, gRPC, message queues, Unix domain sockets), a wire-protocol serialization (JSON-RPC, protobuf, custom envelope formats), or a file-format codec. The further the deliverable's failure surface is from the compiler, the less weight `{build-cmd}` carries.

---

## 3. The Gate Is the Gate

> [!constraint] Sprint exit-gate verdicts MUST reflect the gate-defining step's status
> WRONG — partial-progress accounting that frames intermediate-step PASS counts as Sprint progress when the gate-defining step is still red. Misleads the next session into lowering follow-up bug priority because "we're closer than last time."
> ```markdown
> ## Smoke Verdict
> - Steps 1-4: PASS (component loads, transport launches, transport connects)
> - Step 5: FAIL (protocol handshake)
> - Steps 6-10: BLOCKED
> - Aggregate: PARTIAL — significant progress from S01-04 baseline
> ```
> CORRECT — the gate is binary. Intermediate-step progress is informational only; it narrows the diagnostic search space but does NOT advance the Sprint exit gate.
> ```markdown
> ## Smoke Verdict
> - Steps 1-4: PASS (component loads, transport launches, transport connects)
> - Step 5 (gate-defining): FAIL (protocol handshake)
> - Steps 6-10: BLOCKED
> - Aggregate: FAIL — gate unchanged from S01-04 baseline.
>   Intermediate-step progress narrows the search space ({backlog-id} filed
>   against handshake error path) but the Sprint exit gate is unchanged.
> ```

> [!constraint] Sprint Overview rows MUST encode gate state, not session-count fraction
> WRONG — Master Plan row that flips to ✅ COMPLETE because the session count finished, even though the smoke verdict is FAIL.
> ```markdown
> | Sprint-01 | Threading + IPC | ✅ COMPLETE | 5 / 5 sessions |
> ```
> CORRECT — the row state reflects the exit-gate's verdict, not the session count.
> ```markdown
> | Sprint-01 | Threading + IPC | ⚠️ COMPLETE (verdict PARTIAL — round-trip gate FAIL, {backlog-id}) | 5 / 5 sessions |
> ```

> [!practice] Recovery vs task-spec drift at closeout
> Recovery files paraphrase task-spec scope at closeout time — that paraphrase can drift from the task spec, and downstream readers anchor on the Recovery (more recent, more accessible) rather than the original task spec. The drift manifests as **"in-scope"** silently becoming **"deferred"** between the task spec and the Recovery summary. The closeout reviewer SHOULD cross-check every "deferred" claim in the Recovery against the originating task spec's scope. If the task spec lists the item as in-scope and the Recovery defers it, that is a planning defect — re-open the session and clarify scope, do not accept the deferral.
>
> **Generalized drift example (forwarder / glue boundary):**
>
> - **Task spec (in-scope clause):** *"The routing from the outer transport to the inner consumer is the MVP glue — it may be a simple pass-through (forward every inbound call to the attached client) or defer to a future structured-routing primitive. Document the chosen approach in the Summary."*
> - **Recovery (drifted paraphrase):** *"MVP routing approach: pass-through client stored as DI singleton in the outer host. No forwarding logic implemented. Structured-routing primitive deferred to a later sprint."*
> - The Recovery conflated "no structured-routing primitive used" (a legitimate option per the task spec) with "no forwarder at all" (NOT a legitimate option per the task spec). The Sprint exit gate cleared on an internal probe against the inner consumer, bypassing the outer transport entirely; the defect surfaced days later at first contact with a real external client and was tracked back to the Recovery paraphrase, not to the implementation itself.

> [!practice] When this practice promotes to a constraint
> The practice above is **advisory**, not binding. If the drift pattern recurs — a second HIGH-severity lesson surfaces a similar Recovery-vs-task-spec drift — promote it to a new rule prescribing a mechanical cross-check at session closeout (the new rule's likely home is its own file, e.g., a `recovery-task-spec-cross-check` rule cross-linked from this section).
>
> Cost asymmetry justifies advisory standing today: days of latent in-scope work laundered as deferred vs minutes of cross-check at closeout — real but single-occurrence. On recurrence, open a Backlog item to convert this `> [!practice]` to a `> [!constraint]` with WRONG / CORRECT examples and a mechanical closeout check (grep every "deferred" claim in the Recovery against the originating task spec's in-scope list).

---

## 4. Operational Rules for Smoke Reports

> [!checklist] Smoke report aggregate-verdict line
> - [ ] Aggregate verdict reflects the gate-defining step's status, not a step-count percentage
> - [ ] If the gate-defining step is FAIL, aggregate is FAIL — regardless of how many other steps are PASS
> - [ ] Follow-up bug priority reflects the un-cleared gate, not the count of newly-passing steps
> - [ ] The Master Plan's Sprint Overview row makes the gate state explicit
> - [ ] The Recovery file's "deferred" claims are cross-checked against the originating task spec's in-scope list (see §3 practice)

---

## 5. Build-Clean ≠ Computation-Correct

§2 covers cross-process boundaries; this section extends the same principle into in-process numeric / codec / computational code, where the failure surface is even further from the compiler.

> [!constraint] For numeric/codec/computational code, a clean build proves compilation, never computation
> For any numeric, codec, or computational module, `{build-cmd}` reporting 0 W / 0 E proves the code **compiles** — never that it **computes the right answer**. Sign inversions, off-by-tolerance errors, and wrong-branch reconstructions all pass every static check and every type test.
> - **Author behavioral tests with independently hand-derived expected values, asserted to tight tolerance** (an exact or near-exact bound, not `± slack`). A test loosened to accommodate the implementation's current output cannot catch the implementation being wrong — it launders the bug into "passing." When a test bound is widened to make a test pass, that is a signal to inspect the **implementation**, not the test.
>
>   WRONG — bound loosened to the acceptance tolerance so an out-of-range result still passes:
>   ```text
>   slack = acceptance_tolerance
>   assert result_min >= 200.0 - slack - 0.1   # "close enough" — launders the error into a PASS
>   ```
>   CORRECT — exact expected bound; the wrong result now fails the test and forces the fix:
>   ```text
>   assert abs(result_min - 200.0) < 1e-6
>   assert abs(result_max - 800.0) < 1e-6
>   ```
> - **Slack/tolerance belongs to acceptance gates, not emitted values.** A tolerance that decides *whether two candidates pair/match* must not leak into the *values* the computation emits. Keep the candidate-acceptance interval (with slack) separate from the value-derivation interval (raw, un-slackened).

---

## 6. Build-Fresh ≠ Deploy-Fresh

> [!constraint] A current build with a stale deploy silently tests pre-change code
> `{build-cmd}` updates the **build-output location**; it does **NOT** touch the **deployed copy** a live gate actually reads. A current build with a stale deploy silently exercises pre-change code — surfacing as a false "artifact not found", or worse, a stale artifact body masquerading as a PASS (a build-clean session marked COMPLETE on runtime evidence that never touched the new code — the §2 failure mode displaced from build→runtime to build→deploy→runtime).
> Before any live gate, confirm the deployed artifact's timestamp is **≥** the latest build's; redeploy if older or absent. Don't infer "a build exists" ⇒ "the live artifact is current."

---

## 7. Runtime-Correct on One Target ≠ Correct on All Targets

> [!constraint] Runtime-correct on one target does not generalize to all targets
> For any code that runs against multiple platform / runtime / version targets, **runtime-correct on one target ≠ correct on all targets**. Platform APIs and their tolerances behave differently across versions: an input accepted by one target's API can throw on another — before any result ceiling or budget engages. No static check surfaces this; only a live per-target round-trip against the real heavy input does.
> - **Run all per-target live gates even when some agree.** The extra data point isolates a version-specific failure from a code defect — two targets agreeing proves a third's throw is a version divergence, not a feature bug. Stopping at the first PASS ships the divergence invisibly.
> - **Distinguish a thrown-exception FAIL from a near-timeout FAIL — the remediation differs.** The §2/§3 near-timeout remedy ("lower the budget/ceiling") does **NOT** apply to an exception thrown *before* the budget engages; the ceiling may already be proven well within budget on the passing targets. The fix is a **source guard** (skip/clamp the offending input), applied **identically across all target adapters** (parity), not a budget recalibration. Read the failure class before reaching for the near-timeout lever.

---

## 8. Empirical Verification Discipline

§2–§7 each guard a specific "necessary-but-not-sufficient signal treated as the gate" failure. This section generalizes the same discipline to four cross-cutting cases where an agent or planner trusted a **secondary, stale, or projected** representation of reality instead of measuring the live, whole-surface truth. The common cure: **measure it, don't infer it.**

### 8.1 Line-count measurements MUST use `wc -l`, not Read-output line numbers

> [!constraint] Use `wc -l` for any file line-count finding — never the last line number from a Read
> A file's line count for a review finding MUST come from `Bash` running `wc -l <path>` against the actual file. Do NOT treat the last line number observed in a `Read` tool output as the file's length: `Read` may paginate (default cap ~2000 lines), or the reviewer may stop early to manage budget, and a partial read always produces a number structurally smaller than the true count.
>
> WRONG — reviewer Read partway through the file; the last visible line was 766; reported the file as 766 lines:
> ```
> [WARNING] ei-fidelity.md line count overstated
> File: cloned-repos/planwise/plugins/planwise/references/ei-fidelity.md
> Issue: Task declares 903 lines; actual file is 766 (~15% overstatement).
> ```
> (False positive — actual `wc -l` is 903. The 766 was the last line visible in a paginated read.)
>
> CORRECT — reviewer ran `wc -l` and compared against the plan's declaration:
> ```
> [bash] wc -l cloned-repos/planwise/plugins/planwise/references/ei-fidelity.md
>        903 cloned-repos/planwise/plugins/planwise/references/ei-fidelity.md
> [reviewer] Plan declares 903 — matches. No finding.
> ```
>
> Four danger signals make this false-positive class easy to fire repeatedly:
> 1. The finding looks plausible — line-count drift is a common, legitimate review signal.
> 2. Reviewer confidence reads MEDIUM–HIGH because it "read the file."
> 3. Accepting it directs fix-work that was never needed (false rework).
> 4. Every file ends in `\n` and partial reads always produce a smaller number than `wc -l`, so the error is systematically biased toward "overstated."
>
> This rule also governs the line-count input to the `task-content-fidelity.md` §9.A.3 per-file-type token rate bands: the `Est. Lines` value fed to a band MUST come from `wc -l`, not from a Read-output last line number. Read-output line numbers are decorative, not authoritative.

### 8.2 A broad verification gate is authoritative over an audit's enumerated file list

> [!constraint] Run the full gate; classify every residual match — do NOT trust the audit's file enumeration as the boundary
> When a remediation is scoped by an audit that names specific files, the audit's file list is a starting hypothesis, not the boundary of "clean." Run the full verification gate (grep/lint/diff) and triage every residual match by classification. The gate is the authoritative definition of clean; a broad gate routinely finds sibling instances the audit never named.
>
> WRONG — fix only the audit-named site, then declare done on the audit's word:
> ```
> Audit finding: leak in handlers/plan.md.
> → fix plan.md, mark task complete.   # two sibling leaks in other files survive
> ```
> WRONG — run the gate, see non-empty output, and either fail the task or blindly "fix" every match:
> ```
> grep gate → 50+ matches → treat all as leaks → mangle legitimate naming-convention examples
> ```
> CORRECT — run the full gate, classify every residual match into genuine-citation vs legitimate-illustration, fix the genuine ones, and record the classified residue so a non-empty gate is provably accounted for:
> ```
> grep gate → classify:
>   • a specific project-artifact citation (opaque to any consumer) → genuine leak → SCRUB (3 sites)
>   • an abstract filename pattern under an "Example:" label         → naming illustration → KEEP, document
> → pass criterion = "no genuine citations remain after classification",
>   NOT "grep returns zero lines".
> ```
>
> The distinguishing test: a **citation** references a specific real project artifact (opaque to any downstream consumer) and is a genuine violation; an **illustration** is an abstract filename/identifier pattern under an "Example:" label and is intended documentation. Classify by that test, not by the regex alone. This is the same classification principle §2 applies to round-trip runtime evidence — never silently accept a non-empty gate, and never expect literal-empty output when the repo documents the very pattern being scanned.

### 8.3 Sanity-check a projected headline metric against the fixed extraction scope before starting

> [!constraint] An audit-projected metric is an estimate — reconcile it against the fixed scope up front; execute, measure, log the delta; never expand scope to chase the number
> When a plan carries a derived numeric target (post-edit line count, token savings, retention ratio, file-size delta) that originated from an upstream audit or projection, treat it as an estimate subject to measured reconciliation — not a pass/fail gate — especially when the same spec also fixes the scope that determines the number.
>
> WRONG — treat "~460 lines / ~5.6K savings" as a hard gate; on measuring 603, expand the extraction beyond the fixed scope to force the number down:
> ```
> target = 460 lines; measured = 603 → also extract the kept sections, to hit 460   # violates the fixed scope
> ```
> WRONG — round or fudge the reported savings to match the projection.
> CORRECT — execute the fixed scope, `wc -l` the result, report the measured number, and log the projection-vs-reality delta as an Issue with the arithmetic that explains it:
> ```
> fixed scope: keep the first three subsections, extract the rest → wc -l = 603
> report 603 / ~3.8K saved; Issue: projection assumed 460 (280-extract + 460-remainder = 740 ≠ 894 original) — the projection was internally inconsistent, and the section had grown since the audit.
> ```
>
> Before starting, run the up-front sanity check: `original − extracted_block ?= projected_remainder`. If they don't reconcile, surface it before execution, not at verification time. The extraction is correct; only the projection was optimistic. This is the plan-level headline-metric sibling of the "structurally unreachable threshold" concept (Check 058 / `verification-task-authoring.md` §2), which targets grep-count thresholds inside verification tasks — a different surface, no overlap.

### 8.4 Grep the entire artifact surface for every phrasing of a doctrinal claim before declaring it fixed

> [!constraint] Doctrinal errors propagate across files — sweep the whole surface; surface out-of-scope instances; re-run at end
> A doctrinal error (a rule, a parameter, a threshold, a factual claim stated in a source file and cited by consumers) rarely lives in one place. Before declaring it fixed, grep the entire artifact surface for every phrasing of the claim.
>
> WRONG — edit the file named in scope, confirm that file reads correctly, ship:
> ```
> scope names templates/orchestration.md → fix it, confirm, ship.
> (The same false claim also lived in the section the template CITES — 4 spots —
>  and in handlers/plan.md — 4 more spots. The template now cites a self-contradicting section.)
> ```
> CORRECT — grep the whole surface for every phrasing of the claim (e.g. `parent.{0,2}tier`, `inherit the parent`, the specific false-assertion text); fix all instances — or, where instances fall outside the literal scope, surface them as a structural finding / scope-expansion gate and let the user decide. Re-run the sweep at the end and confirm only correct/negated phrasings remain.
>
> A citation chain is coherent only when the cited source and every consumer agree. When instances fall outside literal task scope, surface them per §1.2 of `read-confirm-act-protocol.md` (structural findings beyond literal scope — surface, don't silently fix or silently ignore), not silently.

### 8.5 Normalize an authored-markdown field on BOTH read and write — and test it with annotated, not clean, fixtures

> [!constraint] When an authored-markdown field feeds a normalized/canonical slot, apply the SAME normalization on comparison AND on write — and regression-test it with realistically messy fixtures, never clean ones
> A value read from a human-authored markdown field (a `**Status:**` line, a table cell a person edits by hand) routinely carries decoration that the canonical slot it feeds must not: wrapping `**bold**` / `_emphasis_`, em-dashes, trailing `(date)` or `— note` annotations, `<!-- comments -->`, `§`, backticks. When that field is compared against a canonical value — OR copied into a normalized (enum / single-token) cell — the normalization must apply consistently on every side, or detection and the write disagree and the slot is silently corrupted. This is a **data-corruption path** whenever the write is destructive, and the class recurs on any tool that copies an authored markdown field into a normalized index/cache cell.
>
> **1. Normalize on both sides, or not at all.** When a field read from authored markdown is compared against a canonical value, apply the normalization to BOTH operands. When such a field is *written* into a normalized (enum / canonical) cell, write the **normalized** value — never the raw authored string.
> WRONG — the comparison normalizes but the write stores the raw source line, so the one-token cell ends up holding a whole annotated sentence, and downstream exact-token filters silently break:
> ```python
> if base_token(row.Status) != base_token(mp_status):   # compare: normalized
>     row.Status = mp_status                             # write: RAW → "**COMPLETE** (2026-05-26) — shipped v1.2.0"
> ```
> CORRECT — the write stores the same normalization detection uses, so detection, the report banner, and the persisted cell all agree on one token:
> ```python
> if base_token(row.Status) != base_token(mp_status):
>     row.Status = base_token(mp_status)                 # write: normalized → "COMPLETE"
> ```
>
> **2. Strip inline formatting when normalizing an authored field.** A whitespace/case-only normalizer is not enough — the field's own value may carry markdown emphasis, so an already-reconciled row reads as false drift.
> WRONG — first-word-uppercase leaves the emphasis attached, so a bolded token never equals its plain canonical form:
> ```python
> def base_token(s): return s.split()[0].upper()          # "**COMPLETE**" → "**COMPLETE**" ≠ "COMPLETE"  (false drift)
> ```
> CORRECT — strip wrapping emphasis (`*` / `_`) after uppercasing:
> ```python
> def base_token(s): return s.split()[0].upper().strip("*_")   # "**COMPLETE**" → "COMPLETE"
> ```
>
> **3. Test with annotated, not clean, fixtures.** A fixture built on a clean canonical value (`"COMPLETE"`) stays green while masking BOTH bugs above — the raw-write corruption and the emphasis false-drift. A regression test MUST feed a realistically messy source and assert the destination receives ONLY the bare token, covering both directions:
> ```python
> # WRONG — clean fixture: green, but exercises none of the decoration the bug actually needs
> write_master_plan(status="COMPLETE")
> # CORRECT — annotated fixtures that an asymmetric or emphasis-blind normalizer would fail
> write_master_plan(status="**COMPLETE** (2026-05-26) — shipped v1.2.0")   # write side: assert the written cell == "COMPLETE"
> #   read side: index cell already "COMPLETE" vs Master Plan "**COMPLETE**" → assert NO drift (no false positive)
> ```
>
> This is the same "a necessary signal is not sufficient" trap §8 opens with, aimed squarely at the test fixture: a green suite built on clean inputs says nothing about the messy authored strings the code will actually meet. It is a direct instance of the pre-commit adversarial-review discipline in `destructive-change-requirements.md` §10.4 ("A green suite is not a review: pre-commit adversarial review for destructive diffs") — the write-side corruption in this class survived a fully green unit suite and fell only to the adversarial review of the destructive write path.

### 8.6 Measure live state before an idempotency-unsafe append/author

§8.1–§8.5 each measure a live surface instead of trusting a secondary reading. This section applies the same discipline to a plan's own task steps: a plan's stated anchors, counts, and "append/author N" instructions are **predictions written when the plan was authored — not facts about the live target now.**

> [!constraint] Re-derive live state before any idempotency-unsafe append/author — never blind-append or blind-author
> Treat a plan's stated anchors, row counts, and "append N rows" / "insert at max+1" / "add the next check number" steps as predictions, not facts. Before executing one, re-derive the live state: grep the shipped artifact and count the rows/sections that already exist. If the deliverable already exists, **verify-in-place** — never blind-append or blind-author on the plan's word.
>
> This matters most when the same deliverable can be shipped through more than one route — a plan session AND a backlog-triage route (direct fix, an in-session task list, a direct commit). A plan's status fields are written only by its own session closeout; a plan whose deliverables were satisfied through a different route is left live and independently runnable, its stale "append N" steps now aimed at already-satisfied state.
>
> WRONG — close the backlog item, leave the twin plan alone → `/planwise run` starts it → a task step "append 10 rows" runs against 10 rows that already exist → 10 duplicate rows, or a duplicate `## 9` section colliding with the shipped `## 8`:
> ```text
> plan step T04: "append 10 Rule-Promotion-Log rows"   # authored when 0 existed
> live index already holds those 10 rows                # shipped via the backlog route
> → blind append → 10 duplicate rows
> ```
> CORRECT — measure the live target first, and reconcile the twin at closeout:
> ```text
> before T04: grep the promotion log → the 10 rows already exist → verify-in-place, do NOT append
> at the shipping route's closeout: retire/link the twin plan so it is never independently run
> ```
> Detection tripwire: at a delegated session's first dispatch layer, grep each deliverable against the live target before authoring. A plan that is **entirely** already-satisfied at that boundary is the signal that a twin was shipped elsewhere and never retired.

### 8.7 Verify the gate's input set before trusting its predicate

An empty result from a verification command is **ambiguous**. It means either "I checked and found nothing" or "I checked nothing." Those are opposite facts and the gate renders them identically. Every downstream reader — the verification report, the sprint signoff, the release battery — consumes the empty result as evidence of cleanliness.

This is worse than a missing gate. A missing gate is visible in review; a gate that *cannot fail* is documented as coverage and actively suppresses the search for one. §8.1–§8.6 each measure a live surface rather than trusting a secondary reading. This section turns the same discipline on the gate itself: **verify the gate's input set, then its predicate.** The two sub-rules below are the two ways a gate ends up unable to fail — one where the input never arrived, one where the objective is satisfied by destroying the thing being checked.

> [!constraint] A — A change-set-derived gate silently excludes whatever the change set omits
> WRONG — the canonical shape. It reports the same empty result whether it inspected everything or nothing:
> ```bash
> git diff $BASE -- <paths> | grep -E '^\+' | grep -E '<forbidden-pattern>'   # expect empty
> ```
> Three independent blind spots, each sufficient on its own to make the gate unfalsifiable:
> 1. **Untracked files never appear in `git diff` at all.** A task that CREATES files gets an empty result from a pipeline those files' content never entered.
> 2. **`^\+` filtering hides everything predating the base.** A defect older than `$BASE` is a context line, not an added line, so it is invisible by construction — and stays invisible across every later session reusing the shape.
> 3. **A pattern narrower than the forms it must catch misses them even unfiltered.** A pattern written as `{PREFIX}-[0-9]` matches only the citation spelling; the same identifier glued into a file name (`…-{PREFIX}SomeTopicName.md` — no hyphen, no digit) slips straight through, so widening the scope without widening the pattern still returns empty on a visibly leaking file.
>
> CORRECT — four remedies, all of them cheap:
>
> **1. Register new files before diffing.** Intent-to-add puts the path in the index without staging content or creating a commit:
> ```bash
> git add -N <each new file>       # then run the gate
> ```
>
> **2. Assert the gate's input was non-empty.** A gate over a diff must prove the diff covered the intended file set — never trust the pattern result alone:
> ```bash
> git status --porcelain <scope> | grep -c '^??'    # must be 0, else some file was never registered
> git diff --name-only $BASE -- <scope> | wc -l     # must equal the expected file count
> ```
>
> **3. Add one unfiltered sweep for pre-existing content.** `^\+`-filtered gates correctly answer "did this change introduce X"; they cannot answer "does X exist". A whole-tree audit or release battery needs a sweep over files **on disk**, not over a diff — and it must **classify** hits rather than blanket-fail, since legitimate template placeholders and rule text that enumerates the forbidden forms will match. Widening a pattern without widening the classification step converts a silent miss into a noisy blanket-fail, which gets ignored just as fast.
>
> **4. Dry-run every gate against known-bad input before trusting it.** Run it once against a file that genuinely carries the pattern and once against a clean file; the two runs MUST produce different results. Each of the three defects above would have surfaced in one such run. A gate that has only ever been run against clean input has never been shown to discriminate.
>
> **Generalisation:** the class is broader than git. Any check deriving its input from a *change set* — a diff, a changelog, a CI touched-files list, a migration delta — silently excludes whatever the change set omits, and inherits this whole failure mode.

> [!constraint] B — A size objective is satisfied by destroying the content the gate was meant to protect
> A pointer's value is not its description — it is the **location**: file + section number + exact heading name. A summary that keeps a rule's topic but drops its section number converts a jump into a search through a long target; one that renames the heading breaks even the search. The pointer no longer points.
>
> WRONG — a consolidation task whose gates are all size- or absence-shaped: a `wc -l` band, a `grep -c` proving the old headings are gone, plus the usual self-containment greps. A runner collapses six pointer sections into one table, flattens nine sub-section numbers into running prose, and rewrites two heading names into shorter paraphrases. **Every gate passes.** The file got smaller, which is what the task asked for — it got smaller *by* discarding the payload. Grepping the target for the table's own wording now returns zero hits.
>
> The failure mode is structurally adversarial: the metric the task optimises improves monotonically with the amount of content destroyed. There is no size at which the gate objects.
>
> CORRECT — four remedies:
>
> **1. Pair every size gate with a content-conservation gate.** Before the task runs, enumerate the specific payload terms that must survive, and check them by exact string:
> ```bash
> for s in '<coordinate-1>' '<coordinate-2>' '<exact heading name>'; do
>   printf '%-40s %s\n' "$s" "$(grep -cF "$s" $FILE)"
> done      # every line must be >= 1
> ```
> Derive the term list from the **pre-edit** file, never from the post-edit result — a list written afterwards inherits whatever was already lost.
>
> **2. Use `grep -F` and mind case.** Proper-noun rule names are part of the payload; lower-casing them breaks findability against the target's actual heading. Run the gate case-sensitively, then re-run case-insensitively to distinguish a genuine loss from a casing slip — they need different fixes.
>
> **3. Never let the output shape truncate the content.** If a three-column table cannot hold the payload readably, widen the cell (`<br>`-separated bullets) or add a sub-list — do not trim the payload to fit the shape. Readability of the container never outranks conservation of what it contains.
>
> **4. Require the gate output in the completion report, and re-run it independently.** In the originating incident the runner did not paste its gate output and reported COMPLETE in good faith; the loss was found only when the orchestrator ran the gate itself. **A conservation claim verified by the same agent that made the cut is not verification.**
>
> **Generalisation:** applies to any consolidation carrying a size objective — merging docs, deduping rules, collapsing config, summarising logs, compressing prompts. Ask what the artifact's *payload* is as distinct from its *prose*, and gate on the payload.

### 8.8 After a behavior change, sweep the surfaces that describe and call it

A behavior change lands on surfaces beyond the code that implements it. **The tests cover the code. Nothing covers the metadata that *describes* the code, or the document that *invokes* it.** Both can therefore be left asserting the old behavior with the suite fully green — and both are read as authoritative: the metadata by tooling and by the next author, the document by the user following it.

§8.7 asks whether a gate can fail. This section asks a prior question: whether the change was even applied everywhere it is stated. The three sub-rules below are one sweep, in causal order — C only ever arises as a consequence of acting on B, so they are not separable.

> [!constraint] A — Update the field, not just the prose beside it
> WRONG — the fix updates the human-readable half and leaves the machine-readable half asserting the old behavior. The row now asserts two contradictory things about the same key, and the authoritative half is the false one:
> ```yaml
>   - id: <some_key>
>     <field>: <old_value>        # ← still says the old behavior
>     notes: >
>       … the commit point now rewrites this key in the SAME write …   # ← says the opposite
> ```
>
> CORRECT — the field moves too, a truthful value is **added** when none exists, and the siblings are swept:
> ```yaml
> # (enum gains a definition comment in the file's own style)
> #   <new_value>: <definition of what this actually means>
>
> <enum_key>: [<existing values>, <new_value>]
>
>   - id: <some_key>
>     <field>: <new_value>
>   - id: <paired_key>
>     <field>: <new_value>   # ← sibling audit: was false before this fix, too
> ```
>
> Three ordered steps:
>
> **(a) Find the field, not just the prose.** Grep the manifests, schemas and frontmatter for the artifact you changed, and read the **structured** values. Free-text `notes:` / `description:` are the easy half — they read as commentary and an author updates them by reflex. The enum, boolean or path-glob two lines above is the half that reads as authoritative to tooling and to the next author, and it is the half that gets left behind.
>
> **(b) If no legal value is true, add one — do not round to the nearest.** Check what consumes the field first: a value that is inert to code but wrong to a reader is a documentation defect; one that drives a loop is a runtime defect. Then add the value to the declared enum **and** write its definition comment in the file's established style. Picking the least-wrong existing value is not a smaller fix than adding one — it encodes a second, subtler lie in a field that now looks deliberately chosen.
>
> **(c) Audit every sibling row carrying the value you just abandoned.** The reason your row was wrong usually applies to its neighbours. **This is the step that pays.** A sibling written by the same mechanism can have been false since before your change existed — no current task owns it, no test covers it, and nothing but this sweep will surface it. Your fix did not cause it; your fix created the occasion to notice it.
>
> When nothing in code validates the field, verify it by hand:
> ```bash
> python -c "
> import yaml; d=yaml.safe_load(open('<manifest>',encoding='utf-8'))
> enum=set(d['<enum_key>'])
> print('off-enum:', [a['id'] for a in d['artifacts'] if a.get('<field>') not in enum] or 'NONE')
> print('grouped:', {v: [a['id'] for a in d['artifacts'] if a.get('<field>')==v] for v in enum})
> "
> ```
> The **grouped** half matters as much as the off-enum half. Off-enum catches a value that is illegal; grouped catches a value that is legal and false — it puts an inherited wrong value directly beside its correct peers, which is the only cheap way to see it.

> [!constraint] B — A detection plus a repair is not a remediation until something routes between them
> Whenever a change adds "X detects a bad state" and "Y can fix it", the deliverable is **not done** until the path from X's recommendation to Y's execution has been traced end to end and shown to be walkable. State the trace explicitly. Do not infer it from the fact that both halves exist and both are tested — that is exactly the evidence that is available when the loop is still open.
>
> **Where the caller is a document** — a handler, a runbook, a README command sequence — the document is part of the change surface, and its gate conditions are as load-bearing as an `if`. A prose gate that exits on the very condition the new repair path exists to serve is a dead end that no test can fail: the user is told they are already fine and left broken, twice.
>
> WRONG — the gate exits on the condition the repair serves, and a nearby note merely *describes* the capability:
> ```
> > If `pinned == shipped` → report "already up to date" and exit.
> …
> > [!practice] A stale root is upgrade-indicating
> > …re-running the script resolves the mismatch…      ← nothing routes here
> ```
>
> CORRECT — the gate itself carries the routing, and names what is skipped and why:
> ```
> > If `pinned == shipped` **and** the stored value matches the live one → report and exit.
> > If `pinned == shipped` **but** the stored value differs → do NOT exit; skip the
> >   comparison stages (nothing changed to compare) and run the writer invocation,
> >   which repairs the value on its own. Report it as a repair, not a version change.
> ```

> [!constraint] C — A previously-unreachable branch is unproven code, regardless of its age or test count
> Fixing a gate per sub-rule B makes a dormant branch live. That is a **behavioral change to everything the branch touches** — the branch's age and the suite's green status say nothing about it, because until now it never ran.
>
> Before declaring it done, walk the branch line by line against every input the newly-routed caller can supply — flags, options, environment — and ask what the branch does with each. **Anything set up after the point where that branch returns is, by construction, not applied there.**
> ```python
>     if pinned_version == target_version:
>         # This branch is now reachable. Everything below the gate — the opt-in
>         # flag application, the backfills — never runs here. Anything a caller
>         # can pass must be honored on THIS path or explicitly declared a no-op.
>         toggled = bool(cfg.opt_in_flag) and _apply_opt_in(config_path)
> ```
>
> The mechanical check is a set difference — enumerate what the caller can request, enumerate what the branch performs before it returns, and subtract:
> ```bash
> # 1. what the caller can ask for: every flag/option the entry point accepts
> grep -nE 'add_argument|opt_in|--[a-z-]+' <entry_point> | sed 's/.*--//' | sort -u
> # 2. what the newly-live branch actually does before returning
> sed -n '<branch_start>,<return_line>p' <module> | grep -nE '_apply_|_backfill_|write|=' 
> ```
> A non-empty difference is either a bug or a decision that needs stating — never a silent no-op.

**Applies-to surface.** Any change to behavior that a manifest, schema, frontmatter field or capability table also describes — **including when the field is documentation-only and no test can fail.** Any change pairing a new diagnostic with a new remediation. Any change relaxing a gate, guard or early return so a previously-dead branch begins executing. And any codebase where prose — a handler, a runbook, a documented command sequence — is the caller of record for a script: there the document's conditions must be edited in the same change as the code's, or the code's new capability is unreachable in practice.

---

*Cross-references: [session-execution-protocol.md](session-execution-protocol.md) (Recovery-file update discipline at closeout), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Sprint exit-gate semantics in Master Plan / Sprint Plan rows).*
