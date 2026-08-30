---
description: Sessions delivering IPC/protocol/codec layers MUST include round-trip evidence before COMPLETE; Sprint exit-gate verdicts reflect the gate-defining step's status, not a step-count percentage; build-clean ≠ computation-correct, build-fresh ≠ deploy-fresh, and runtime-correct-on-one-target ≠ all-targets for in-process numeric/codec and multi-target code
paths: {planwise_root}/{plans_dir}/**
---

# Verification Gates — Build-Clean Is Not Runtime-Correct

**Purpose:** Gate-discipline rules for planwise sessions whose deliverable creates or modifies a cross-process boundary (IPC layer, wire-protocol serialization, file-format codec). Codifies the two failure modes (build-clean ≠ runtime-correct; partial-PASS ≠ gate progress), the round-trip evidence requirement, the gate-is-the-gate Sprint Overview discipline, and the Recovery-vs-task-spec drift practice surfaced at closeout. Sections 5–7 extend the build-clean-is-not-enough principle past cross-process boundaries into in-process numeric/codec computation (§5), build-vs-deploy freshness (§6), and multi-target runtime parity (§7). §8 turns the same discipline on the verification command itself: a `git diff` gate that names no tree state silently measures the whole working tree instead of the sprint's own delta.
**Companion file:** [measurement-discipline.md](measurement-discipline.md) (§8 Empirical Verification Discipline — the cross-cutting "measure it, don't infer it" counterpart to this file's cross-process/build/runtime gate discipline).

## Table of Contents

- [1. The Two Failure Modes](#1-the-two-failure-modes)
- [2. Round-Trip Evidence for Cross-Process Boundaries](#2-round-trip-evidence-for-cross-process-boundaries)
- [3. The Gate Is the Gate](#3-the-gate-is-the-gate)
- [4. Operational Rules for Smoke Reports](#4-operational-rules-for-smoke-reports)
- [5. Build-Clean ≠ Computation-Correct](#5-build-clean--computation-correct)
- [6. Build-Fresh ≠ Deploy-Fresh](#6-build-fresh--deploy-fresh)
- [7. Runtime-Correct on One Target ≠ Correct on All Targets](#7-runtime-correct-on-one-target--correct-on-all-targets)
- [8. Diff-Scoped Gates Pin a Recorded Baseline](#8-diff-scoped-gates-pin-a-recorded-baseline)
- [9. Empirical Verification Discipline → measurement-discipline.md](measurement-discipline.md)

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

#### Reviewer Check 013 — Task Verification Commands Section Present

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Tasks touching code/tests/schemas MUST include `## Verification Commands` section using placeholder vocabulary.
- **Detection:** Open task; grep `^## Verification Commands` heading. If task touches `{code, test, schema, migration, notebook}` AND section absent → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task Verification Commands section missing
File: {task file path} | Location: Expected after Execution Steps
Issue: Task touches {code|tests|schemas} but lacks Verification Commands
Fix: Append ## Verification Commands per templates/task-file.md | Confidence: HIGH
```

#### Reviewer Check 014 — Per-File-Type Verification Table Populated

- **Severity / Role / Type:** BLOCKER | Task Reviewer | EXTEND
- **What:** Verification Commands section MUST include per-file-type table with placeholder command rows (`{lint-cmd}`, `{format-cmd}`, `{test-cmd}`, `{exec-cmd}`).
- **Detection:** Open Verification Commands section; count rows matching `{[a-z-]+-cmd}`. Zero → BLOCKER.
- **Finding template:**
```
[BLOCKER] Per-file-type Verification Commands table not populated
File: {task file path} | Location: Verification Commands section
Issue: Table has no placeholder-command rows
Fix: Add rows per templates/task-file.md Per-File-Type Commands | Confidence: MEDIUM
```

#### Reviewer Check 034 — Verification Commands Notebook Execution Present

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Tasks producing/modifying `{notebook-file}` artifacts MUST include `{exec-cmd}` in Verification Commands.
- **Detection:** Grep Expected Output for notebook artifacts; grep Verification Commands for `{exec-cmd}`. Notebook output + `{exec-cmd}` absent → ERROR.
- **Finding template:**
```
[ERROR] Notebook execution verification missing
File: {task file path} | Location: Verification Commands section
Issue: Task produces notebook artifact but lacks {exec-cmd}
Fix: Add {exec-cmd} row per templates/task-file.md Per-File-Type Commands | Confidence: HIGH
```

#### Reviewer Check 035 — Verification Commands Lint/Format Present

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Tasks producing/modifying code files MUST include `{lint-cmd}` AND `{format-cmd}` in Verification Commands per-file-type table.
- **Detection:** Code-producing output + missing `{lint-cmd}` OR `{format-cmd}` in Verification Commands → ERROR.
- **Finding template:**
```
[ERROR] Lint/format verification commands missing
File: {task file path} | Location: Verification Commands section
Issue: Code-producing task lacks {lint-cmd}/{format-cmd}
Fix: Add per-file-type rows per templates/task-file.md | Confidence: HIGH
```

#### Reviewer Check 036 — Verification Commands DB Pre-Check Position

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** DB-write tasks MUST include `{connectivity-check-cmd}` in `> [!verify]` "Before" block (not "After").
- **Detection:** Locate `> [!verify]` callout; check `{connectivity-check-cmd}` position. Misplaced or absent → WARNING.
- **Finding template:**
```
[WARNING] DB connectivity pre-check missing or misplaced
File: {task file path} | Location: > [!verify] Before/After block
Issue: {connectivity-check-cmd} absent OR placed in After block
Fix: Move to Before block per references/callout-conventions.md > [!verify] | Confidence: MEDIUM
```

---

## 4. Operational Rules for Smoke Reports

> [!checklist] Smoke report aggregate-verdict line
> - [ ] Aggregate verdict reflects the gate-defining step's status, not a step-count percentage
> - [ ] If the gate-defining step is FAIL, aggregate is FAIL — regardless of how many other steps are PASS
> - [ ] Follow-up bug priority reflects the un-cleared gate, not the count of newly-passing steps
> - [ ] The Master Plan's Sprint Overview row makes the gate state explicit
> - [ ] The Recovery file's "deferred" claims are cross-checked against the originating task spec's in-scope list (see §3 practice)

#### Reviewer Check 015 — Verification `> [!verify]` Before/After Block Present

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Task files producing executable artifacts MUST include `> [!verify]` callout with Before/After bash commands.
- **Detection:** Grep `> \[!verify\]` callout (multiline). Task Expected Output declares runnable artifact (notebook, script, binary) AND callout absent → BLOCKER.
- **Finding template:**
```
[BLOCKER] Verification > [!verify] Before/After block missing
File: {task file path} | Location: Verification Commands section
Issue: Task produces runnable artifact but lacks verify callout
Fix: Add > [!verify] callout per references/callout-conventions.md | Confidence: MEDIUM
```

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

## 8. Diff-Scoped Gates Pin a Recorded Baseline

A gate built on `git diff` is a question about a **tree state**. A `diff` that names no state does not decline to answer — it answers about the entire working tree instead of the sprint's own delta. The command still runs, still prints, and still reads as green or red; it is simply measuring a different tree than the one the sprint wrote. That goes wrong in both directions at once:

- **False FAIL.** Any uncommitted work present when the session opened — an earlier session, a parallel sprint, a human mid-edit — counts against this sprint. Measured once on a live repo: 6 modified files, +575 / −66, three of them under a directory one sprint's exit criterion forbids outright. That state alone failed the scope gates of three sprints in a six-sprint plan **before a single task ran**.
- **False PASS / misattribution.** A self-containment sweep scans added lines the sprint never wrote. A forbidden token on one of those lines is blamed on this sprint, and a leak this sprint really did introduce is just as arbitrarily credited elsewhere once someone commits between gates. A tree that clears an unpinned sweep cleared it by luck, and the report cannot tell the difference.
- **Parallelism breakage.** `git diff --name-only | grep '<dir>/'` asserting "this sprint edited nothing under `<dir>`" trips on a concurrently running sprint's legitimate work in that directory — a hard FAIL caused entirely by someone else's correct behaviour.

The defect is systemic rather than per-plan: one audit found 109 diff-scoped gates across six sprints of a single plan, every one authored from intent rather than from a dry run.

**This section is the definition site for `$..._BASE`.** [measurement-discipline.md](measurement-discipline.md) §8.7 governs the *input-set* half of the same gate — untracked-file registration (`git add -N`), the input-set assertion, the unfiltered on-disk sweep, and the known-bad dry-run — and its examples consume `$BASE` without defining it. The two halves are complementary and neither restates the other: §8.7 asks *did the gate inspect anything*, this section asks *did it inspect the right tree state*. An empty result means nothing until both are answered.

Throughout this section `$BASE` stands for the sprint's own recorded `{ABBREV}_S{NN}_BASE` (or `{ABBREV}_SERIES_BASE` where a whole-series view is meant). It is a **recorded value**, never a literal to copy forward.

### 8.1 Record a baseline before the first edit

> [!constraint] The first task in a sprint that touches the target repo records the base, behind a clean-scope precondition
> ```bash
> git -C <repo> status --porcelain -- <this sprint's write paths>
> # MUST be empty. Non-empty → HALT: an earlier session, a parallel sprint, or a human
> # has uncommitted work inside this sprint's write-set. Commit or stash it, then re-run.
> # Do NOT pin over a dirty scope — the base would already carry work this sprint did not do,
> # and every gate scoped to it would inherit that work as its own.
> {ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)
> ```
> Record the name, the value, and the recording task in the session Recovery file's Key Findings. That record is the **first write of the session** — before any edit. A base pinned after an edit already contains it, so every gate scoped to that base is blind to the one change it was written to check, and reports empty for the reason that makes an empty result worthless.

The precondition is scoped with `--` to **this sprint's write paths**, not to the whole repo: unrelated dirt outside the sprint's area is not this sprint's problem to stash, and a whole-repo cleanliness demand is the kind of gate sessions learn to override. Carry the recorded value where later sprints can find it — a Sprint Overview status cell is enough:

```markdown
| {Sprint-N} | {Session-Name} | ✅ COMPLETE | Verdict PASS — 7/7 tasks. `{ABBREV}_S{NN}_BASE=5b53607` |
```

### 8.2 Scope every gate to the recorded base

> [!constraint] Every diff-scoped gate names the recorded base — `git diff $BASE -- <paths>`
> Never a bare `git diff`, never `git diff --name-only` with no operand, and never `git diff HEAD`. `HEAD` is not a synonym for the base: it moves with every commit the session makes, so a gate written against it measures the delta since the *last commit*, not since the sprint began. A session that commits mid-way silently erases all of its own earlier work from every later gate — the gates go green because the evidence left the diff, not because the defect left the tree.

### 8.3 Path-scope with `-- <paths>`, not with an output filter

`-- <paths>` restricts the tree git **inspects**. A downstream filter only hides part of what git already inspected and reported, and the difference is exactly the parallel-safety property a scope gate needs. `git diff --name-only | grep '<dir>/'` walks the whole repository, so a sibling sprint's concurrent work under `<dir>` enters the result and is attributed here; under `git diff --name-only $BASE -- <paths>` that work was never in the input at all — invisible by construction.

The filter form fails a second way: it matches **text**, not paths. A pattern for a directory name also matches any file whose *name* contains that string elsewhere in the tree, and misses the same directory reached under a different spelling. `--` matches paths.

### 8.4 A multi-sprint series records a series base once, at the first sprint

A plan whose sprints each pin their own base can gate each sprint's delta but has no way to diff the **series**: the release battery, the whole-refactor self-containment sweep, the "did we edit a file no sprint ever declared" scope test all need a single base predating the first sprint. Record a second name, `{ABBREV}_SERIES_BASE`, at the first task of the first sprint, and carry it verbatim into every later sprint's Recovery.

> [!constraint] First-to-touch — check for an already-recorded series base before minting one
> A task that pins the series base must not assume it ran first. Plans routinely declare sprints INDEPENDENT, and an independent sprint may legitimately execute **and commit** before the nominally-first one starts. Check before claiming the name: Grep for `{ABBREV}_SERIES_BASE` across the plan's Recovery files. If a prior sprint's Recovery already records a value, **adopt that value verbatim** — do not re-derive it. Only when none exists does this task's own HEAD become the series base.
>
> Re-minting a series base that already includes an independent sprint's commits silently narrows the whole-series sweep to the remaining delta: that sprint's added lines are never in the input, so the final cross-check is blind to them while every per-sprint gate still reports green. The failure surfaces at release, in the one gate meant to be the backstop.

### 8.5 A scope rule gets a positive test, not a list of forbidden directories

A scope rule states where a sprint **may** write. Testing it by enumerating the places it may not write permits every directory nobody thought to forbid — including directories that did not exist when the gate was authored. Assert the allowed set instead and require the complement to be empty:

```bash
# WRONG — enumerates the forbidden set; anything unlisted passes silently:
git -C <repo> diff --name-only $BASE -- <root> | grep -E '^<forbidden dir>/'      # expect empty
# CORRECT — asserts the allowed set; anything unlisted FAILS:
git -C <repo> diff --name-only $BASE -- <root> | grep -vE '^(<allowed dir A>|<allowed dir B>)/'   # expect empty
```

The two commands are the same length and read almost identically. Only the second one can fail for a reason nobody anticipated, which is the only kind of failure a scope gate exists to catch.

> [!constraint] The three canonical unpinned shapes, and their baseline-scoped rewrites
> WRONG — none of the three names a tree state; all three read the entire working tree:
> ```bash
> git -C <repo> diff <path>/ | grep -E '^\+' | grep -E '<leak pattern>'   # expect empty
> git -C <repo> diff --name-only | grep '<forbidden dir>'                 # expect empty
> git -C <repo> diff --name-only                                          # expect exactly N files
> ```
> CORRECT — each scoped to the recorded base and path-scoped with `--`:
> ```bash
> git -C <repo> diff $BASE -- <paths> | grep -E '^\+' | grep -E '<leak pattern>'          # expect empty
> git -C <repo> diff --name-only $BASE -- <root> | grep -vE '^(<allowed dir>)/'           # expect empty
> git -C <repo> diff --name-only $BASE -- <paths> | wc -l                                 # expect exactly N
> ```
> **Both failure directions live on the WRONG side, and they are not the same defect.**
> - **False FAIL** — pre-existing uncommitted work counts against the sprint. The file-count form reports more files than N, and the sprint is marked over-scope for edits it never made; the directory-filter form fires on a parallel sprint's legitimate work. The cost is a halted session and a re-litigated scope, paid every time the tree is not pristine.
> - **False PASS / misattribution** — the leak-pattern form scans added lines the sprint never wrote, so a forbidden token belonging to nobody in the plan is reported as this sprint's leak, and a real leak is credited to whichever sprint happens to be running. Nothing in the output distinguishes the two, and the empty case — the one everybody reads as "clean" — is where the misattribution is completely invisible.
>
> The rewrite is mechanical, so there is no case for the WRONG forms: an unpinned gate is not a cheaper gate, it is a gate whose result does not mean what the report says it means.

#### Reviewer Check 077 — Diff-Scoped Gate Not Baseline-Pinned

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Any `git diff` in a task file's Verification Commands or Success Criteria MUST be scoped to a recorded baseline — the sprint's `{ABBREV}_S{NN}_BASE`, or `{ABBREV}_SERIES_BASE` for a whole-series battery — and MUST path-scope with `-- <paths>` rather than by filtering the command's output. A sprint whose first repo-touching task records no baseline at all fails this check for every gate in the sprint, including gates that name a `$..._BASE` operand that is never pinned anywhere. An unpinned gate reads the whole working tree: pre-existing uncommitted work counts against the sprint (false FAIL) and added lines the sprint never wrote are attributed to it (false PASS).
- **Detection:**
  1. Grep the task file for `git diff`; every hit is a candidate.
  2. For each hit, assert **(a)** a `$..._BASE` operand is present, **(b)** a `--` path scope is present — a pipe into a path filter does not satisfy this, and **(c)** the operand names a base the sprint's first repo-touching task actually records. Any one absent → ERROR.
  3. Open that first repo-touching task and confirm it pins the base **before its first edit**, behind a clean-scope precondition (`git status --porcelain -- <write paths>` MUST be empty, else HALT), and records name + value in Recovery Key Findings. Pinned after an edit, or not recorded → ERROR.
  4. On a multi-sprint plan, confirm a `{ABBREV}_SERIES_BASE` is recorded once at the first sprint and **adopted verbatim** by later sprints. A later sprint that re-derives it from its own HEAD → ERROR.
  5. Inspect any scope gate that enumerates forbidden directories rather than asserting the allowed set; the enumerating form permits every directory nobody listed → ERROR.
- **Finding template:**
```
[ERROR] Diff-scoped gate not baseline-pinned
File: {task file path} | Location: Verification Commands / Success Criteria step {n}
Issue: Gate runs `git diff` with {no recorded base | `HEAD` as the operand | no `--` path scope | a base no task in the sprint records}; it reads the whole working tree, so pre-existing uncommitted work fails the sprint (false FAIL) and added lines the sprint never wrote are attributed to it (false PASS)
Fix: Pin `{ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)` in the sprint's first repo-touching task behind an empty-`git status --porcelain -- <write paths>` precondition, record it in Recovery Key Findings before the first edit, and rewrite the gate as `git diff $BASE -- <paths>` per references/verification-gates.md §8 | Confidence: HIGH
```

---

**Empirical Verification Discipline** — relocated to [measurement-discipline.md](measurement-discipline.md) §8 (wc-l line-count authority over Read-output line numbers, broad-gate authority over an audit's file enumeration, headline-metric reconciliation, doctrinal-claim surface sweeps, markdown-field normalization on both read and write, idempotency-safe append/author, gate-input-set verification before trusting a predicate, and post-behavior-change surface sweeps).

---

*Cross-references: [session-execution-protocol.md](session-execution-protocol.md) (Recovery-file update discipline at closeout), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Sprint exit-gate semantics in Master Plan / Sprint Plan rows), [measurement-discipline.md](measurement-discipline.md) (§8 Empirical Verification Discipline, split from this file).*
