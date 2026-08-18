---
description: Discovery-phase Consolidated Context authoring MUST treat every file:line citation and third-party SDK premise in its task brief as a starting hypothesis, verify it against live source before folding it into the output Part, and surface any false premise as a prominent correction rather than a silent fix
---

# Verify Discovery-Phase Consolidation Against Live Source

Companion to [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) §1-§5 (the Exec-phase SDK/identifier verification core). This file carries §6 — the Discovery-phase extension of the same discipline.

---

## 6. Discovery-Phase Consolidation — Verify Citations and SDK Premises Against Live Source

The discipline of this reference is largely framed around **Exec-phase** specs (EIs, task specs, BLIs). It applies just as much to **Discovery-phase** consolidation: a Consolidated Context Part is authored from source, and source citations drift the moment the live file grows. A `file:line` citation pinned at scaffold-time becomes stale; a third-party SDK premise paraphrased in the task brief (e.g., "this overload is delegate-only — no `MethodInfo` overload") can be a verified-false starting assumption.

Neither failure surfaces in a build — no code is produced at Discovery time. Both can only be caught by **reading the shipped artifact during consolidation**.

> [!constraint] A Discovery / consolidation agent MUST treat every `file:line` citation and every third-party SDK premise in its task brief as a STARTING HYPOTHESIS — verify against live source / reflected DLL, cite the verified position, flag false premises as prominent corrections in the output Part
> WRONG — a discovery / consolidation agent copies the task-brief's `file:line` citations and SDK premises verbatim into the output Part, trusting them because "the planner already verified":
> ```markdown
> ## Part {N} §{X}b — Plugin registration site
>
> The plugin registration is at `Connection.cs:797-812`, with channel/version
> hardcoded at `:807-808` (per task brief). The factory `{SdkFactory}.Create`
> is delegate-only — no `MethodInfo` overload.
> ```
> ```
> [The Part then launders stale line numbers (the file has since grown to 990
>  lines — actual registration is at 835-852) and a verified-false SDK premise
>  (the shipped DLL actually exposes one Delegate and TWO MethodInfo overloads)
>  into the Scaffolding phase, which builds Exec specs on top of them.]
> ```
> CORRECT — open the live file / reflect the shipped artifact, cite the verified position, flag any brief premise that turns out false as a prominent correction in the output Part (not a silent fix):
> ```markdown
> ## Part {N} §{X}b — Plugin registration site
>
> **Verified against live source 2026-MM-DD:** plugin registration is at
> `Connection.cs:835-852` (file has grown to 990 lines since the task brief was
> authored at 797-812). Channel/version hardcoding is now at `:845-846`.
>
> **Task-brief premise correction:** the brief asserts `{SdkFactory}.Create` is
> "delegate-only (no `MethodInfo` overload)". Reflecting `{ExternalSdk}.dll`
> {pinned-version} via `[{SdkFactory}].GetMethods() | Where Name -eq 'Create'`
> returned **three** overloads — one `Delegate` and **two `MethodInfo`**. The
> premise was load-bearing for the registrar feasibility assessment; the
> correction is recorded in §{open-questions} OQ-{N} and re-folds into
> downstream Scaffolding.
> ```

**Operational rule for multi-task Discovery sessions:** when two parallel agents both touch the same large source file, expect citation drift and have the orchestrator consolidate the verified positions into the Recovery `Key Findings` as a single carry-forward note for any dependent (synthesis) task. The Discovery→Scaffolding boundary is where the carry-forward earns its budget — the Scaffolding phase MUST re-verify any file:line / SDK premise carried forward from Discovery rather than treating it as settled.

> [!practice] Mark Discovery-time false-premise corrections as PROMINENT in the Consolidated Context Part — not silent fixes
> When a Discovery agent overturns a load-bearing task-brief premise (an SDK overload set, a delegate-only-ness claim, a member presence assertion), surface the correction explicitly in the output Part with a "Task-brief premise correction" heading. Downstream Scaffolding readers and synthesis tasks rely on the correction being visible; a silent fix laundering the corrected fact back into the Part text leaves the false premise as a latent claim someone else can re-cite.

---

*Companion files: [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md), [verify-cross-repo-fix-discipline.md](verify-cross-repo-fix-discipline.md), [verify-backlog-citation-freshness.md](verify-backlog-citation-freshness.md).*
