---
description: A session delivering an IPC, protocol or codec layer includes round-trip evidence before COMPLETE (§2); the two failure modes that collapse a multi-signal verification surface into one "looks green" reading (§1); build-clean ≠ computation-correct for in-process numeric and codec code (§5); build-fresh ≠ deploy-fresh (§6); and runtime-correct on one target ≠ correct on all targets (§7).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Runtime Boundary Evidence (Build-Clean Is Not Runtime-Correct)

**Purpose:** Gate-discipline rules for a session whose deliverable creates or modifies a cross-process boundary, in-process numeric or codec computation, a build-then-deploy step, or code that runs on more than one platform, runtime or version target. A verification signal that is necessary but not sufficient is not the gate. Split from `verification-gates.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gates.md §N` citation translates by filename alone. The family index is `verification-gates.md`.

**Read this when** a session's deliverable touches a cross-process boundary (IPC layer, wire-protocol serialization, file-format codec), in-process numeric or codec code, a deploy step a live gate reads, or multi-target runtime code.

## Table of Contents

- [1. The Two Failure Modes](#1-the-two-failure-modes)
- [2. Round-Trip Evidence for Cross-Process Boundaries](#2-round-trip-evidence-for-cross-process-boundaries)
- [5. Build-Clean ≠ Computation-Correct](#5-build-clean--computation-correct)
- [6. Build-Fresh ≠ Deploy-Fresh](#6-build-fresh--deploy-fresh)
- [7. Runtime-Correct on One Target ≠ Correct on All Targets](#7-runtime-correct-on-one-target--correct-on-all-targets)

---

## 1. The Two Failure Modes

Two recurring planwise gate-discipline failures share one root cause: a verification signal that is **necessary but not sufficient** is being treated as the gate.

| Failure | Symptom | Cost |
|---------|---------|------|
| Build-clean session marked COMPLETE without runtime evidence | Defect introduced N sessions ago surfaces in the integration session | Diagnostic depth = N sessions of code stacked atop the original break |
| "M of N smoke steps PASS" framed as Sprint progress when the gate-defining step still fails | Master Plan / Summary suggests forward motion when the gate is still red | Misleads the next session author into deprioritizing the actual gate-blocker |

Both failures collapse a multi-signal verification surface into a single "looks green" reading. §2 below and §3 in [gate-exit-verdict-and-smoke-reports.md](gate-exit-verdict-and-smoke-reports.md) state the binding rules that prevent each collapse.

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

## 6. Build-Fresh ≠ Deploy-Fresh

> [!constraint] A current build with a stale deploy silently tests pre-change code
> `{build-cmd}` updates the **build-output location**; it does **NOT** touch the **deployed copy** a live gate actually reads. A current build with a stale deploy silently exercises pre-change code — surfacing as a false "artifact not found", or worse, a stale artifact body masquerading as a PASS (a build-clean session marked COMPLETE on runtime evidence that never touched the new code — the §2 failure mode displaced from build→runtime to build→deploy→runtime).
> Before any live gate, confirm the deployed artifact's timestamp is **≥** the latest build's; redeploy if older or absent. Don't infer "a build exists" ⇒ "the live artifact is current."

## 7. Runtime-Correct on One Target ≠ Correct on All Targets

> [!constraint] Runtime-correct on one target does not generalize to all targets
> For any code that runs against multiple platform / runtime / version targets, **runtime-correct on one target ≠ correct on all targets**. Platform APIs and their tolerances behave differently across versions: an input accepted by one target's API can throw on another — before any result ceiling or budget engages. No static check surfaces this; only a live per-target round-trip against the real heavy input does.
> - **Run all per-target live gates even when some agree.** The extra data point isolates a version-specific failure from a code defect — two targets agreeing proves a third's throw is a version divergence, not a feature bug. Stopping at the first PASS ships the divergence invisibly.
> - **Distinguish a thrown-exception FAIL from a near-timeout FAIL — the remediation differs.** The near-timeout remedy of §2 and of `gate-exit-verdict-and-smoke-reports.md` §3 ("lower the budget/ceiling") does **NOT** apply to an exception thrown *before* the budget engages; the ceiling may already be proven well within budget on the passing targets. The fix is a **source guard** (skip/clamp the offending input), applied **identically across all target adapters** (parity), not a budget recalibration. Read the failure class before reaching for the near-timeout lever.

---

*Cross-references: [gate-exit-verdict-and-smoke-reports.md](gate-exit-verdict-and-smoke-reports.md) (§3-§4, the Sprint exit verdict and the smoke-report rules the two failure modes in §1 lead to) · [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10, what the instrument itself must prove) · [measurement-discipline.md](measurement-discipline.md) §8 (the cross-cutting "measure it, don't infer it" counterpart) · [verification-gates.md](verification-gates.md) (the family index).*
