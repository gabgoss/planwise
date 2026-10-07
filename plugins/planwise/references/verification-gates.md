---
description: Sessions delivering IPC/protocol/codec layers MUST include round-trip evidence before COMPLETE; Sprint exit-gate verdicts reflect the gate-defining step's status, not a step-count percentage; build-clean ≠ computation-correct, build-fresh ≠ deploy-fresh, and runtime-correct-on-one-target ≠ all-targets for in-process numeric/codec and multi-target code; §10 turns the discipline on the instrument itself — a gate must be able to fail, must not fail correct work, must see the shape it counts, and must be pointed at the live subject as well as at fixtures; §11 sorts gates into change-detecting and state-detecting shapes — a battery of only diff-shaped gates proves the change was clean and says nothing about the artifact's condition, so every plan names at least one state-detecting gate; §12 points at the reachability gate (verify-caller-before-complete.md) — a definition is not a caller
paths: {planwise_root}/{plans_dir}/**
---

# Verification Gates — Build-Clean Is Not Runtime-Correct

**Purpose:** Gate-discipline rules for planwise sessions whose deliverable creates or modifies a cross-process boundary (IPC layer, wire-protocol serialization, file-format codec). Codifies the two failure modes (build-clean ≠ runtime-correct; partial-PASS ≠ gate progress), the round-trip evidence requirement, the gate-is-the-gate Sprint Overview discipline, and the Recovery-vs-task-spec drift practice surfaced at closeout. Sections 5–7 extend the build-clean-is-not-enough principle past cross-process boundaries into in-process numeric/codec computation (§5), build-vs-deploy freshness (§6), and multi-target runtime parity (§7). §8 turns the same discipline on the verification command itself: a `git diff` gate that names no tree state silently measures the whole working tree instead of the sprint's own delta. §11 asks what a diff-shaped gate can answer at all — a battery composed entirely of change-detecting gates is blind by construction to any defect that predates the diff.
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
- [9. Empirical Verification Discipline → measurement-discipline.md](measurement-discipline.md) — relocated; the number stays reserved so citations to it keep resolving
- [10. The Instrument's Four Proof Obligations](#10-the-instruments-four-proof-obligations)
- [11. Change-Detecting vs State-Detecting Gates](#11-change-detecting-vs-state-detecting-gates)
- [12. Reachability Gates → verify-caller-before-complete.md](verify-caller-before-complete.md) — a definition is not a caller; the section below is a pointer so `§12` citations resolve

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

## 10. The Instrument's Four Proof Obligations

§1–§8 above ask whether the right thing was measured. This section asks a prior question: **is the instrument itself sound?** A gate's output is evidence only after the gate has discharged four obligations, and they are **independent** — passing any one says nothing about the other three. A gate can discriminate perfectly and still be pointed at a sanitised subject. A gate can be pointed at the real subject and be structurally incapable of failing.

| Obligation | The question | Failure it admits |
|---|---|---|
| A | Can it fail at all? | A criterion already satisfied before the work starts |
| B | Does it fail *correct* work? | A gate measuring form, exerting pressure to reformat correct content |
| C | Can it see the shape it counts? | A single-line matcher against a multi-line idiom |
| D | Does a proven instrument mean a clean subject? | A fixture dry-run reported as if it were a live sweep |

> [!constraint] Obligation A — the gate must be able to fail
> ```
> WRONG  AC: "re-run the tool and confirm the open-item count equals the
>             number of non-closed rows"
>          -> 17 open, 17 reported. PASS.
>          # Passes identically against fully-unfixed code, because the two rows
>          # that triggered the bug were reworded yesterday as a workaround. The
>          # criterion measured the data, and the data had been sanitised.
> CORRECT AC: "run every parser on a clean row AND on a row containing a \| b;
>              require identical, correct column assignment"
>          -> fixed tree:   12/12 identical and correct                     PASS
>          -> unfixed tree: field clobbered, priority destroyed, links empty FAIL
>          # The FAIL is the load-bearing half: it proves the gate discriminates.
> ```
>
> Two rules, stated separately because they fail separately:
>
> 1. **A criterion evaluated against live project data measures the data, not the code.** It is a regression guard for after the fix lands — never evidence the fix works. Phrase at least one criterion against a **fixture that reproduces the defect**, and say in the item which criterion is the discriminating one.
> 2. **Run the same probe against the unfixed artifact** — the previous commit, the installed older version, a copy with the fix reverted — **and show it failing.** That second run is what converts "my code passes" into "this gate detects the defect."
>
> Two corollaries:
>
> - **A criterion already satisfied at triage time is a finding, not a tick.** Record it with its reason. A criterion structurally incapable of failing again — because the reflex that sanitised the data will sanitise the next case too — is a defect in the criterion.
> - **Prefer "demonstrably correct" to "demonstrably different."** Two outputs that merely differ can both be wrong.

> [!constraint] Obligation B — the gate must not fail correct work
> A gate must assert **the property you care about**, not a spelling of it. For a citation the property is **resolution**: the file exists at the path given, the section exists in it, no placeholder token remains. Never typography.
>
> ```
> WRONG   — asserts typography. Rejects the house style, accepts a broken link.
>   pattern: '{file}\.md §[0-9]+\.[0-9]+'
>   -> `{file}.md` §1.4      scores 0   # a backtick sits where the pattern wants a space
>   -> nonexistent.md §9.9   scores 1   # the file does not exist; only the shape does
>
> BETTER  — spelling-tolerant. Still only checks the shape.
>   pattern: '{file}\.md`?\s*§[0-9]+(\.[0-9]+)?'
>   -> catches an unpinned citation and a leftover {placeholder}
>   -> still scores 1 for a section number that is not in the file
>
> BEST    — resolves. Asserts the property the gate exists to protect.
>   for each citation:  Read the named file
>                       -> confirm a heading carries that §-number
>                       -> confirm no placeholder token remains
>   -> the only tier that fails a citation whose target moved
> ```
>
> The BETTER tier is shown because it is the tempting stopping point, and it is still not the correct one.
>
> **The authoring test:** *what would a correct-but-differently-formatted artifact score?* If the answer is FAIL, the gate is measuring form. **Dry-run against a known-GOOD file in the house style, not only against known-bad** — the standing dry-run rule proves a gate can *fire*; it does not prove the gate stays silent on correct work.
>
> A gate that fails correct work leaves a runner three options: fail the work, edit its own exit criteria, or reformat correct content. It will reformat, and it may land on a valid form by luck. **When a runner reports that it reformatted content to satisfy a gate, that is a gate-defect report, not a completion detail** — read it as one.

> [!constraint] Obligation C — the gate must be able to see the shape it counts
> A sweep for invalidated patch targets reported **14 sites**. The real count was **64+2**. Every clause of the pattern was single-line; the file's dominant idiom is not.
>
> Two cheap checks, before the pattern is trusted:
>
> ```
> # 1. Count the idiom's ANCHOR and its CONTINUATION separately.
> #    A large gap means the pattern is single-line and the idiom is not.
> Grep  pattern='patch\.object'  path='{target}'  output_mode='count'   #  9  <- what the sweep saw
> Grep  pattern='^\s*ip,'        path='{target}'  output_mode='count'   # 47  <- what it missed
>
> # 2. Read one real instance before writing the pattern.
> Read  file_path='{target}'  offset={first hit}  limit=12
> ```
>
> Prefer structure-independent matchers, in this order:
>
> 1. A **multiline matcher** when the idiom genuinely spans lines.
> 2. Better — a **structural check**: parse the file and walk its call nodes. Immune to formatting entirely.
> 3. For verifying a mechanical rename, a **normalization diff**: undo the rename in the new file and expect an additions-only diff. A line-classifying filter cannot tell a target line from an assertion line when the target sits on a continuation line — the same blindness, one layer up.
>
> **Finding a defect class does not immunize you against it.** The moment of discovery is when the blind spot is most active, because attention is on the target rather than on the instrument. In the originating session, two of the five instances were committed inside the sweeps written to catch the other three — including a verification gate carrying the identical flaw, which would have false-FAILed ~55 legitimate repoints.
>
> **Delegation corollary:** an orchestrator-supplied count is handed down as a **cross-check with halt-on-disagreement**, never as the answer. A runner told "there are 14" will find 14.

> [!practice] Obligation D — discrimination is not cleanliness
> | Run | Question answered | What a pass proves |
> |-----|-------------------|--------------------|
> | Fixture dry-run | *Can this gate tell bad from good?* | The gate is not vacuous |
> | Live sweep | *Is the thing it guards actually clean?* | The subject has no current defects |
>
> A fixture dry-run is bounded by the author's model of the defect — a self-portrait of what was already believed. A live sweep alone, with no dry-run behind it, is worthless: an empty result from an instrument nobody proved discriminating says nothing. Neither substitutes for the other.
>
> The asymmetry that makes this worth a rule: **the dry-run is what acceptance criteria naturally capture**, because it is scoped and predictable. **The live sweep is what gets skipped**, because it is unbounded and its result is not knowable at authoring time — which is exactly why it is where new work comes from. One gate repair met a well-designed dry-run criterion exactly (7/7 on known-bad, 0/6 on clean, every carve-out silent) and passed every acceptance criterion it had. Pointing the repaired gate at the tree it guards — which no criterion asked for — immediately returned eight leaking lines in two shipped files no deliverable had scoped, plus a fourth defect class the item never identified.
>
> 1. **Run both, in order, and report the two outputs separately.** A single merged "verification passed" hides which question was answered.
> 2. **Expect the live sweep to produce findings outside the item's file list, and treat that as the deliverable working.** A repair whose live sweep is clean on the first try is weak evidence the repair was needed.
> 3. **Classify hits before acting**, and prefer a mechanical evidence-based discriminator to judgement.
> 4. **Write the live sweep into the next gate-repair item's acceptance criteria**, phrased so fixtures cannot satisfy it. The criterion form: *"after landing, run one unfiltered sweep for this pattern class across the guarded tree and paste the classified result."*
> 5. **When the live sweep finds a defect class the item did not name, file it rather than absorbing it.** Absorbing it hides the discovery inside a closed item.
>
> This generalises past pattern sweeps: unit tests versus production data, a linter's own suite versus running it over the repo, a migration's fixture round-trip versus a dry-run against the real database. Same two runs, same asymmetry.

#### Reviewer Check 087 — Bug-Fix Criteria With No Fixture and No Unfixed-Artifact Run

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** A plan whose deliverable is a bug fix MUST carry at least one acceptance criterion phrased against a **fixture that reproduces the defect**, AND a requirement to run the same probe against the **unfixed artifact** and show it failing. Criteria phrased against live project data measure the data, not the code — they pass identically against fully-unfixed code whenever the triggering rows were reworded, worked around, or otherwise sanitised before triage. Without the failing run, "my code passes" has never been distinguished from "this gate detects the defect."
- **Detection:**
  1. Identify deliverables whose objective is a fix, repair, or correction of a defect.
  2. Read their acceptance criteria. Classify each as fixture-based (names a constructed input reproducing the defect) or data-based (queries the live project corpus). All data-based → BLOCKER.
  3. Check for a criterion requiring the probe to run against the unfixed artifact — the previous commit, the installed older version, or a reverted copy — with the FAIL result recorded. Absent → BLOCKER.
  4. Check the plan names which criterion is the **discriminating** one. Absent → WARNING (downgrade from BLOCKER when 2 and 3 both pass).
  5. Where a criterion is already satisfied at triage time, check the plan records that as a finding with its reason rather than as a satisfied box. Recorded as satisfied → BLOCKER.
- **Finding template:**
```
[BLOCKER] Bug-fix criteria cannot fail — no fixture, no unfixed-artifact run
File: {plan or task file path} | Location: Acceptance Criteria / Success Criteria
Issue: {N} of {M} criteria query live project data; none is phrased against a fixture reproducing the defect{, and no criterion requires the probe to fail on the unfixed artifact}
Fix: Add one criterion over a constructed input that reproduces the defect, add a criterion requiring the same probe to run on the unfixed artifact with its FAIL output pasted, and name the discriminating criterion, per references/verification-gates.md §10 obligation A | Confidence: HIGH
```

#### Reviewer Check 088 — Gate Asserts Format Where the Property Is Resolution, or Is Fixture-Satisfiable

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** Two instrument defects that ship together often enough to share a check. **(a)** A verification gate asserts a format or spelling pattern where the property at stake is **resolution or existence** — a citation gate matching punctuation rather than confirming the target file and section exist. Such a gate scores 0 on a correctly pinned citation written in the house style and scores 1 on a citation whose file does not exist, and it exerts pressure on the runner to reformat correct content. **(b)** A gate-repair deliverable whose acceptance criteria are satisfiable **entirely by fixtures**, with no live sweep of the guarded subject. A fixture dry-run proves the gate is not vacuous; only a live sweep proves the subject is clean, and the live sweep is the one that finds work no criterion could have named.
- **Detection:**
  1. For every verification gate whose subject is a citation, path, identifier, or section reference: read its pattern. Does it assert punctuation, spacing, or delimiter placement rather than confirming the target resolves? → WARNING.
  2. Apply the authoring test to each such gate — *what would a correct-but-differently-formatted artifact score?* FAIL → WARNING.
  3. Check whether the plan requires a dry-run against a known-GOOD file in the house style, not only against known-bad. Absent on a format-shaped gate → WARNING.
  4. For deliverables whose objective is repairing or authoring a gate: check the criteria for a live sweep of the guarded tree, phrased so fixtures cannot satisfy it. All-fixture criteria → WARNING.
  5. Check the plan states that findings outside the item's file list are expected from the live sweep and get filed rather than absorbed. Absent → WARNING.
- **Finding template:**
```
[WARNING] Gate measures form, or is satisfiable without a live sweep
File: {plan or task file path} | Location: {Verification Commands | Success Criteria} step {n}
Issue: {gate asserts {pattern} where the property is resolution — a house-style citation scores 0 and a citation to a nonexistent file scores 1 | gate-repair criteria are satisfied entirely by fixtures; the guarded tree is never swept}
Fix: {Rewrite the gate to resolve the reference — confirm the named file exists, the section number is present as a heading, and no placeholder token remains — and dry-run it against a known-GOOD house-style file as well as known-bad | Add a live-sweep criterion over the guarded tree phrased so fixtures cannot satisfy it, and state that findings outside this item's file list are filed, not absorbed}, per references/verification-gates.md §10 obligations B and D | Confidence: MEDIUM
```

---

## 11. Change-Detecting vs State-Detecting Gates

§10 asks whether the instrument is sound. This section asks a different question about a battery that is *entirely* sound: **what question is its shape able to answer at all?** A gate can discharge all four proof obligations and still be structurally blind to a defect that was already there when the session opened.

Sort every gate into one of two shapes:

| Shape | Recognisable by | The question it answers |
|---|---|---|
| **Change-detecting** | It reads a diff — `\| grep '^\+'`, `\| grep '^-'`, `--name-only`, a removed-line-set count, any predicate over `git diff` output | *Did this change introduce a defect?* |
| **State-detecting** | It reads the artifact as it stands — a whole-file count, an equality between two surfaces, a directory listing compared against a declaration, a resolve-every-reference pass | *Does a defect exist?* |

The two are not interchangeable, and the gap is not a matter of degree. Anything predating the diff is a **context line**: invisible to a change-detecting gate by construction, not by oversight. A battery composed entirely of change-detecting gates proves your change was clean and says **nothing** about the artifact's condition.

> [!constraint] Every verification plan names at least one state-detecting gate
> Or it records explicitly that no state property is at risk. A battery of only change-shaped gates is not a strong battery with a gap — it is a battery that cannot answer the question a reader will assume it answered.

**Enumeration drift is the worst case for a change-shaped battery.** A missing entry is an *absence* — there is no line for any pattern to match — and a stale count is *syntactically valid*, so nothing is malformed; the number is merely false. Neither leaves a trace in a diff that did not touch them.

### 11.1 The sharp edge — a pre-existing omission can arm a gate against correct work

A pre-existing omission is not only invisible going in. It can **detonate on the way out**, and the resulting failure is undiagnosable from inside the task that hits it.

The shape: a task's exit gate derives its expected figure **from** the very enumeration it is checking. Landing the literal scope — add the new member, derive both figures live — moves one side and not the other, because the pre-existing omission was never in scope. The gate reports a mismatch and fails **correct work**, with the true cause sitting in a line the task had no reason to open.

```bash
# WRONG — the expected value is derived from the enumeration under test.
# A member missing from that parenthetical for reasons predating this task
# makes the gate fail work that is entirely correct.
grep -o '({first-member}.*{last-member})' {doc} | tr ',' '\n' | wc -l   # must equal the declared count
```

Derive the two sides from **independent** surfaces, or the gate is checking a thing against itself.

### 11.2 The cross-surface equality invariant

Where two surfaces enumerate the same set, assert their **equality**. Never assert either one against a remembered number.

```bash
# Table-of-contents entries must equal numbered body sections.
# Both sides derived live; no constant appears anywhere in the gate.
[ "$(grep -cE '^- \[[0-9]+\.' README.md)" = "$(grep -c '^## [0-9]' README.md)" ] || echo MISMATCH
```

Four properties make this the right shape, and a threshold gate has none of them:

| Property | Why |
|---|---|
| Absence-detecting | It compares cardinalities, so a missing member moves one side. No pattern has to match the thing that is not there. |
| State-based | It evaluates the file as it stands. A defect three sprints old fails it today. |
| Self-maintaining | Both sides are derived live. There is no baseline to re-measure and no threshold to drift. |
| Cannot false-fail correct work | Correct work moves both sides together — precisely the failure §11.1 describes. |

> [!verify] The equality gate must reference no constant
> If a number appears on either side, it is a threshold wearing an equality's clothes, and it will drift. The gate above names `README.md` and two patterns; it names no count.

### 11.3 Compare sets, not counts

Cardinality equality is necessary and **not sufficient**. Three surfaces at thirteen rows each can still disagree on membership — one lists a member another omits, and a fourth carries a member that no longer exists. Both counts read thirteen and every count-based gate passes.

Extract the member set from each surface and assert the **symmetric difference is empty** against a designated reference surface — typically the router or dispatch table, the one surface that is executable rather than descriptive:

```bash
# Extract each surface's members, then diff the sorted sets pairwise.
# A non-empty diff names the divergent member, which a count never can.
diff <(sort surface-a.txt) <(sort surface-b.txt)   # MUST be empty
```

Report the divergent member, not the counts. A gate that says `13 != 12` sends the reader to count rows; a gate that says `harvest present in the router, absent from the quick reference` sends them to the line.

### 11.4 Emit the surface set at landing time

The root cause of enumeration drift is that a feature's surfaces are **not mechanically linked**. Nothing fails when one of four is missed, so the set has to be *remembered* — and one landing routinely leaves two or three surfaces stale across sprints.

The durable fix is not a sharper reviewer. It is making the set **enumerable rather than remembered**: a task that lands a new member of any enumerated set names every surface that enumerates it, in the task file, as a checklist the exit gate walks. Where the surfaces live in one repo, §11.3's set comparison then holds the checklist honest without anyone re-deriving it.

> [!constraint] Dry-run an equality gate in BOTH directions before trusting it
> Run it against a state where the defect is genuinely present — an earlier revision is the cheapest source — and show it **FAIL**. Then run it against a correct state and show it **PASS**. The FAIL proves it discriminates; the PASS proves it does not fail correct work, which §11.1 shows is the specific way this gate class goes wrong. A gate never shown to fail is not evidence, and a gate never shown to pass on correct input is a retry loop waiting to happen.

---

## 12. Reachability Gates — a Definition Is Not a Caller

Every gate in §1–§11 measures **presence**; none measures whether production ever reaches the thing. The reachability gate — assert a **caller** that supplies the activating argument, not a definition; quote a production call site per behaviour-adding deliverable in the closing-sweep ledger; classify a runner's "dormant until a follow-up wires it" return as PARTIAL, never COMPLETE — lives in its own reference: [verify-caller-before-complete.md](verify-caller-before-complete.md). This section reserves the number so `§12` citations resolve; the body is not restated here.

---

**Empirical Verification Discipline** — relocated to [measurement-discipline.md](measurement-discipline.md) §8 (wc-l line-count authority over Read-output line numbers, broad-gate authority over an audit's file enumeration, headline-metric reconciliation, doctrinal-claim surface sweeps, markdown-field normalization on both read and write, idempotency-safe append/author, gate-input-set verification before trusting a predicate, and post-behavior-change surface sweeps).

---

*Cross-references: [session-execution-protocol.md](session-execution-protocol.md) (Recovery-file update discipline at closeout), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Sprint exit-gate semantics in Master Plan / Sprint Plan rows), [measurement-discipline.md](measurement-discipline.md) (§8 Empirical Verification Discipline, split from this file).*
