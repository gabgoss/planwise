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
> A citation chain is coherent only when the cited source and every consumer agree. When instances fall outside literal task scope, surface them per §1.2 of `session-execution-protocol.md` (structural findings beyond literal scope — surface, don't silently fix or silently ignore), not silently.

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
> This is the same "a necessary signal is not sufficient" trap §8 opens with, aimed squarely at the test fixture: a green suite built on clean inputs says nothing about the messy authored strings the code will actually meet. It is a direct instance of the pre-commit adversarial-review discipline in `session-plan-requirements.md` §10.4 ("A green suite is not a review: pre-commit adversarial review for destructive diffs") — the write-side corruption in this class survived a fully green unit suite and fell only to the adversarial review of the destructive write path.

---

*Cross-references: [session-execution-protocol.md](session-execution-protocol.md) (Recovery-file update discipline at closeout), [session-plan-requirements.md](session-plan-requirements.md) (Sprint exit-gate semantics in Master Plan / Sprint Plan rows).*
