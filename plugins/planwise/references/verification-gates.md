---
description: Sessions delivering IPC/protocol/codec layers MUST include round-trip evidence before COMPLETE; Sprint exit-gate verdicts reflect the gate-defining step's status, not a step-count percentage
paths: {planwise_root}/{plans_dir}/**
---

# Verification Gates — Build-Clean Is Not Runtime-Correct

**Purpose:** Gate-discipline rules for planwise sessions whose deliverable creates or modifies a cross-process boundary (IPC layer, wire-protocol serialization, file-format codec). Codifies the two failure modes (build-clean ≠ runtime-correct; partial-PASS ≠ gate progress), the round-trip evidence requirement, the gate-is-the-gate Sprint Overview discipline, and the Recovery-vs-task-spec drift practice surfaced at closeout.

## Table of Contents

- [1. The Two Failure Modes](#1-the-two-failure-modes)
- [2. Round-Trip Evidence for Cross-Process Boundaries](#2-round-trip-evidence-for-cross-process-boundaries)
- [3. The Gate Is the Gate](#3-the-gate-is-the-gate)
- [4. Operational Rules for Smoke Reports](#4-operational-rules-for-smoke-reports)

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

*Cross-references: [session-execution-protocol.md](session-execution-protocol.md) (Recovery-file update discipline at closeout), [session-plan-requirements.md](session-plan-requirements.md) (Sprint exit-gate semantics in Master Plan / Sprint Plan rows).*
