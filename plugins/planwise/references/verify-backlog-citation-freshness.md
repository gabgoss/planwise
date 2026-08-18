---
description: BLI triage-time verification recipes (motivating-driver still-active recheck, un-tested-axes-first reproducer ordering, cluster-batch driver recheck, cross-cutting audit-candidate coverage at fix-agent delegation time), verifying source edits when the installed plugin is older than the source, and backlog-item citation freshness (pinned sequential identifiers, code anchors, narrative attributions) at execution time
---

# BLI Triage-Time Recipes and Backlog-Item Citation Freshness

Companion to [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) §1-§5 (the Exec-phase SDK/identifier verification core). This file carries two co-located disciplines that both operate on the backlog-item (BLI) surface: the BLI triage-time recipes peeled from that file's §3 ladder (§3h, §3h.untested-axes, §3h.cluster, §3i) plus its §8 (installed-plugin-version skew) and §9 (.1-.3) (backlog-item citation freshness at execution time) — original §-numbers preserved — plus this file's own §10 (backlog-item claim verification at filing time) and §11 (re-alignment verb premise probing), native to this file rather than peeled from the parent.

## Table of Contents

- [3h. BLI Motivating Driver Still Active (Triage Time)](#3h-bli-motivating-driver-still-active-triage-time)
- [3h.untested-axes Un-Tested Axes — Lead Phase 1 With the BLI's Blind Spots](#3huntested-axes-un-tested-axes--lead-phase-1-with-the-blis-blind-spots)
- [3h.cluster Cluster Batching](#3hcluster-cluster-batching)
- [3i. BLI Cross-Cutting Check Coverage at Fix-Agent Delegation Time](#3i-bli-cross-cutting-check-coverage-at-fix-agent-delegation-time)
- [8. Verifying Source Edits When the Installed Plugin Is Older Than the Source](#8-verifying-source-edits-when-the-installed-plugin-is-older-than-the-source)
- [9. Backlog-Item Citation Freshness at Execution Time](#9-backlog-item-citation-freshness-at-execution-time)
  - [9.1 Re-derive pinned sequential identifiers from the live artifact](#91-re-derive-pinned-sequential-identifiers-from-the-live-artifact)
  - [9.2 Re-locate cited code anchors by symbol; re-check acceptance criteria against HEAD](#92-re-locate-cited-code-anchors-by-symbol-re-check-acceptance-criteria-against-head)
  - [9.3 Verify pre-drafted narrative attributions against the live file](#93-verify-pre-drafted-narrative-attributions-against-the-live-file)
- [10. Backlog-Item Claim Verification at Filing Time](#10-backlog-item-claim-verification-at-filing-time)
  - [10.1 An item is a factual claim about the current repository](#101-an-item-is-a-factual-claim-about-the-current-repository)
  - [10.2 "File N items" specifies scope, not that N conditions hold](#102-file-n-items-specifies-scope-not-that-n-conditions-hold)
  - [10.3 Distinguish "already resolved" from "someone else has this in flight"](#103-distinguish-already-resolved-from-someone-else-has-this-in-flight)
  - [10.4 Reconcile the source, or it permanently asserts something false](#104-reconcile-the-source-or-it-permanently-asserts-something-false)
- [11. Re-Alignment Verb Premise Probing](#11-re-alignment-verb-premise-probing)
  - [11.1 Probe the premise at the family level before accepting a re-target framing](#111-probe-the-premise-at-the-family-level-before-accepting-a-re-target-framing)

---

### 3h. BLI Motivating Driver Still Active (Triage Time)

A BLI is a snapshot of a problem at the moment it was filed. Intervening sessions may have neutralized the motivating driver via independent work — a workaround, a refactor, a fix that addresses the symptom from a different angle, or a single `if` branch that makes the cited mechanism harmless. The BLI's narrative does not auto-update; without an explicit recheck, the triage handler will route a still-IN_PROGRESS-on-paper item to a meta-plan or execution plan against a problem that has already been solved.

The drift surface is most severe for BLIs whose motivating driver is **a runtime symptom** (collision, race, hang, missing endpoint, binding miss, silent failure, performance regression) rather than **a measurable acceptance criterion** (line-count target, coverage %, schema diff). The handler's existing measurable-AC staleness check (Phase 3 of `/planwise backlog`) catches the latter; it does NOT catch the former.

> [!verify] Re-verify a BLI's motivating driver before routing to a multi-session plan
> ```
> # 1. Read the BLI's "Summary" / "Surfaced by" sections — extract the motivating SYMPTOM
> #    (not the BLI's proposed solution).
> #
> # 2. Locate the symptom's mechanism in current code:
> grep -rn "{symptom-keyword}" src/
> #
> # 3. Read the implicated files in full and check whether intervening sessions added
> #    an early-return / identity-match / workaround that makes the cited mechanism harmless.
> #
> # 4. Cross-check recent session Summaries / Closeout Evidence under
> #    {planwise_root}/{plans_dir}/**/Outputs/ for the symptom keyword:
> grep -rln "{symptom-keyword}" {planwise_root}/{plans_dir}/**/Outputs/
> #
> # 5. If a fix is found in the codebase OR a session summary documents the symptom as
> #    resolved by collateral work, surface the finding before routing — present a
> #    "Close as CLOSED — driver neutralized by {session-id}" option in addition to the
> #    standard scope-assessment routing.
> ```
> The check costs ~5 minutes of reading at triage time. It avoids the ~1–3 session-budgets a multi-phase plan would otherwise consume against a non-problem.

> [!constraint] `/planwise backlog` Phase 3 MUST re-verify the BLI's motivating driver before routing
> WRONG — read the BLI, treat its "Summary" / "Surfaced by" prose as the current state, route to SESSION_PLANNING based on scope keywords ("multi-phase", "refactor"). The handler's measurable-AC staleness check fires only when the BLI exposes counts/percentages/coverage; runtime-symptom drivers slip through:
> ```
> ITEM: {bli-id} — {bli-title}  (rationale: {runtime-symptom})
> Route: SESSION PLANNING
> Reason: Multi-phase, mechanical refactor across N modules / manifests / planwise cascade
> [Routes to a Meta-Plan + Exec-Plan; spends sessions producing artifacts; user later
>  realizes the runtime symptom was already neutralized by an intervening fix shipped
>  in {session-id} — work is closed without commit.]
> ```
> CORRECT — re-verify the motivating SYMPTOM (not the BLI's proposed solution) is still active in current code before routing. If the symptom has been neutralized by intervening work, present a "Close as CLOSED — driver neutralized" option alongside the scope-based routing:
> ```
> ITEM: {bli-id} — {bli-title}  (rationale: {runtime-symptom})
>
> Driver recheck:
>   - Symptom cited: "{exact symptom keyword from the BLI}"
>   - Current code: {file}:{line} — {brief description of intervening fix}
>   - Live evidence: {closeout-evidence-file} confirms the symptom is no longer
>     reproducible.
>   - Driver status: NEUTRALIZED by {session-id}.
>
> Route options:
>   A. CLOSE — driver neutralized; remaining value insufficient to justify
>      multi-phase cost
>   B. SESSION PLANNING — proceed anyway for residual value (proceed only after
>      explicit user acknowledgment that the original driver is gone)
> ```

### 3h.untested-axes Un-Tested Axes — Lead Phase 1 With the BLI's Blind Spots

When the BLI's evidence is intermittent — the original repro reliably reproduced on some (object-class × count × version) combination, but not on others — the original session left **un-tested axes**. The BLI's own prescribed Phase 1 matrix typically re-runs the originally-failed dimension first, burying the cheapest disconfirmation cells (the un-tested axes) deep in the queue. A coverage-gap analysis at triage time identifies the cells the originating evidence never tested; leading Phase 1 with those cells short-circuits the matrix aggressively when one of them PASSes.

> [!constraint] Phase 1 of an intermittent-observation BLI MUST test originally-untested axes FIRST
> WRONG — accept the BLI's prescribed reproducer matrix as-authored; Phase 1 cells mirror the originating session's setup (re-running the originally-failed dimension); the cheapest disconfirmation cell lives 5+ cells deep:
> ```
> Reproducer matrix (BLI as filed):
>   Cell #1: {object-class-A} × {count-A} × {version-A}    ← re-runs S{XX}-{YY} setup
>   Cell #2: {object-class-A} × {count-A} × {version-B}
>   Cell #3: {object-class-A} × {count-B} × {version-A}
>   ...
>   Cell #6: {object-class-B} × {count-A} × {version-A}    ← UN-TESTED in original
>   ...
> [If Cell #6 PASSes, the matrix could short-circuit H3 immediately — but the
>  matrix as filed has 5 expensive re-runs ahead of it.]
> ```
> CORRECT — coverage-gap analysis enumerates the (axis × value) cells the originating evidence did NOT cover; Phase 1 leads with those cells; the matrix prunes aggressively when one of them PASSes:
> ```
> Coverage-gap analysis of {session-id} evidence:
>   - object-class axis: tested {object-class-A}; UN-TESTED: {object-class-B}
>   - count axis: tested {count-A}; UN-TESTED: {count-B} (intermittent re-run subset)
>   - version axis: tested {version-A}; UN-TESTED: {version-B}
>
> Reproducer matrix (Phase 1 — un-tested axes FIRST):
>   Cell #1: {object-class-B} × {count-A} × {version-A}    ← un-tested
>   Cell #2: {object-class-A} × {count-A} × {version-B}    ← un-tested
>   Cell #3: {object-class-A} × {count-B} × {version-A}    ← un-tested
>   ...
> [If Cell #1 PASSes, H3 (object-class-dependent) is disconfirmed and the matrix
>  prunes aggressively — saving 4+ expensive re-runs.]
> ```

> [!practice] When triaging an intermittent-observation BLI, surface the un-tested-axes pre-flight in the route assessment
> Include in the routing recommendation: *"BLI's prescribed matrix re-runs the originating session's failed dimension; the cheapest disconfirmation lives in cells the original session never tested. Recommend re-ordering Phase 1 to lead with un-tested axes."* — so the user can approve the reorder before scaffolding cost is incurred.

### 3h.cluster Cluster Batching

A BLI may have been fixed-and-closed-as-collateral by its originating session before the BLI's formal closeout. The index status (NOT_STARTED / IN_PROGRESS) lags actual state — the originating session shipped the fix in a single Step, but didn't yet update the BLI status. When the triage handler trusts the index status, it misroutes the cluster to a fresh fix-agent session that re-does work already shipped.

**Triage-time signals that a BLI may already be fixed by its originating session:**

| Signal | What to check |
|--------|---------------|
| `created` date matches the originating session's active window | Cross-reference `Surfaced by:` session ID's `Last Updated` in Recovery |
| `Surfaced by:` references a session that is IN_PROGRESS or in EVIDENCE_WRITING phase | Read the session's Recovery file Current Step + Phase |
| Multiple BLIs share the same Sprint+Session in `Surfaced by:`, same `created:` date, adjacent IDs | A cluster filed in a single triage pass often gets fixed in a single Step |
| Recovery file mentions the BLI ID in Step Completion or Key Findings | The originating session referenced the BLI during execution |

**Operational rule — two-part driver-recheck for cluster signals:**

1. **Code-level grep** (§3h core recipe): grep the BLI's symptom keyword against `src/` to find any intervening fix.
2. **Live-verification recheck**: read the originating session's Recovery `## Step Completion Status` and `## Key Findings` to confirm the cluster's fixes were shipped together.

> [!constraint] When BLI cluster signals fire, driver-recheck per §3h before any fresh routing; surface cluster-batch close option when Recovery confirms shared fix
> WRONG — trust the index status, route fresh fix-agent sessions per BLI in the cluster:
> ```
> Cluster: {bli-id-1}, {bli-id-2}, {bli-id-3} — all NOT_STARTED, same Surfaced by:
> Action: route 3 fresh fix-agent sessions; each does the work the originating
>         session already shipped.
> ```
> CORRECT — perform a driver-recheck per §3h before routing; surface a cluster-batch close option when Recovery confirms the shared fix:
> ```
> Cluster: {bli-id-1}, {bli-id-2}, {bli-id-3} — same Surfaced by: {session-id};
>          same created: {YYYY-MM-DD}; adjacent IDs.
>
> Driver recheck:
>   - {session-id} Recovery Step {N} Key Findings: "Fixed {symptom-class} across
>     {bli-id-1}/{bli-id-2}/{bli-id-3} via {one-line description of fix}."
>   - grep -rn "{symptom-keyword}" src/ → matched at {file}:{line}: intervening fix
>     present.
>
> Route options:
>   A. CLUSTER CLOSE — mark all three CLOSED with reference to {session-id}
>      Recovery Step {N}; pending formal closeout of {session-id}.
>   B. SCAFFOLD as separate items — proceed only if the user disagrees with the
>      cluster-fix evidence above.
> ```

### 3i. BLI Cross-Cutting Check Coverage at Fix-Agent Delegation Time

A BLI's "Files Touched" section names the **primary** target file. Several other sections may name **additional** files where the same defect class is suspected to exist:

- A "Cross-cutting check" / "Cross-cutting consideration" subsection (e.g., the audit of sister DTOs that share a serialization-drift pattern).
- An acceptance criterion phrased as "Cross-cutting audit of all {category} {pattern}".
- A "Notes" entry like "the cross-cutting audit may surface latent defects in 1-N other {DTOs / files / call sites}".

When the BLI is routed to DIRECT_FIX, the fix-agent spawn prompt MUST include those audit candidates as in-scope unless the main session explicitly scopes them out. The defect class — the same root-cause pattern that produced the primary defect — is repo-wide; treating only the primary file leaves N-1 latent defects to surface in future live-verifies.

> [!constraint] Fix-agent spawn prompts MUST include the BLI's cross-cutting audit candidates as in-scope by default
> WRONG — copy only the BLI's "Files Touched" primary target into the fix-agent prompt; treat "Cross-cutting check" candidates as separate follow-up work:
> ```
> ## Item: {bli-id} — {defect-pattern}
> File: {src/module}/{PrimaryTarget}.{ext}
> [Fix-agent applies pattern to one file. The same defect remains unfixed on N
>  sister files; they surface one-by-one over the next N live-verifies.]
> ```
> CORRECT — read the BLI in full, identify the audit candidates from any "Cross-cutting" / "Notes" section, list them in the fix-agent's prompt with a one-line rationale per file:
> ```
> ## Item: {bli-id} — {defect-pattern} (cross-cutting)
> Files (cross-cutting per BLI Acceptance Criteria + Notes):
>   - {src/module}/{PrimaryTarget}.{ext} (primary)
>   - {src/module}/{Sister1}.{ext} (matches defect-class signal)
>   - {src/module}/{Sister2}.{ext} (matches defect-class signal)
>   - {src/module}/{Sister3}.{ext} (verify shape; may not match — confirm before applying)
> Apply the same pattern to each. Verify Nth file's shape before applying.
> ```

**Practical pre-flight:** before delegating, verify the cross-cutting scope by grepping the defect-class signal in the candidate folder — e.g., `grep -r "{defect-class-signal}" {src/module}/` returning zero matches confirms the defect was repo-wide. Prefix any candidate the fix-agent should NOT touch with an explicit out-of-scope rationale; otherwise the agent assumes inclusion.

**§3i applies when ANY of these conditions hold for the BLI being routed to DIRECT_FIX:**

| Condition | Why it raises scope-incompleteness risk |
|-----------|----------------------------------------|
| BLI has a "Cross-cutting check" / "Cross-cutting consideration" subsection naming additional files | Author flagged the defect class as repo-wide; primary fix alone is incomplete |
| Acceptance criterion includes "Cross-cutting audit of all {category}" | Audit is part of the BLI's contract, not separate follow-up work |
| BLI Notes mentions "may surface latent defects in N other {DTOs / files / call sites}" | Author hedged on count but expects co-discovery during the fix |
| Defect signature is a missing attribute, missing import / using, or missing helper call (mechanical, repo-wide-pattern defects) | A repo-wide grep almost always reveals additional sites |

---

## 8. Verifying Source Edits When the Installed Plugin Is Older Than the Source

When editing the plugin **source** while an older version is **installed and running**, verification signals split into two categories that MUST be treated differently.

> [!constraint] Separate deterministic source-level evidence from live-behavior signals; defer live checks to post-install
>
> WRONG — treat a successful dispatched-subagent run, or live path-rule injection showing ~0 rules, as proof that source edits are correct. Those checks run the *installed* artifacts, not the edited source.
>
> CORRECT — prove source behavior deterministically: run the unit test suite, call edited functions directly against a temp copy, and run a read-only linter (`--doctor`) for before/after measurement. Explicitly mark live-behavior checks (dispatched agent definitions, live injection probes) as **DEFERRED-to-post-install** and record the exact post-`upgrade` re-test to run.

**Deterministic source-level evidence (reliable under version split):**
- Unit test suite run against the source directory directly
- Direct function / script calls against a temp copy of the edited file
- Read-only `--doctor` output (before/after line count, section presence)
- Static grep checks on the edited source text

**Live-behavior signals (unreliable under version split — defer):**
- Dispatched subagent runs (spawn a `{plugin}:task-runner` or equivalent) — these load the *installed* agent definition, not the edited source
- Live path-rule injection probes ("does a brief-read inject N rules?") — these reflect the *installed* handler, not the edited handler
- Any check that depends on the running harness loading the edited artifact

**Model override weakens live signals further:** if a live acceptance check is forced to a model tier different from the fix's target (e.g., Opus 1M for a 200K-window overflow fix), name it a weakened signal and make the deterministic measurement primary.

**Recording deferred checks:** For each live-behavior signal deferred, record:
1. What the check would prove (the exact claim it tests)
2. The post-`upgrade` command to re-run it
3. That the deferred check is NOT a pass — it is explicitly unresolved until post-install

---

## 9. Backlog-Item Citation Freshness at Execution Time

A backlog item's body is a snapshot; every reference it pins — a sequential identifier, a `file:line` code anchor, an acceptance criterion, a narrative claim about which artifact carries which behavior — is a *hypothesis* about a live artifact, and must be re-proven at execution time, never trusted. The item may have been drafted days or sprints before it is worked, and in that interval sibling changes land: a promotion consumes the next-free number, a file grows and its line anchors move, a criterion becomes satisfied by code that arrived after authoring, a symbol the note names turns out to hold a different assertion. Applying any stale citation verbatim ships a defect. Re-derive each cited reference from the current artifact — by content grep or measurement — immediately before acting on it.

This is the backlog-execution sibling of `verify-cross-repo-fix-discipline.md` §7.3a–§7.3d (fix-recipe execution-time fidelity) and §8 below (verification under an older installed plugin): the same "verify against the live artifact, not the snapshot" principle, applied to the triage → fix surface where the drifting reference is the item's own pre-drafted citation rather than an audit recipe.

### 9.1 Re-derive pinned sequential identifiers from the live artifact

> [!constraint] A pre-drafted Check number / catalog row / §-number is next-free at DRAFT time only — re-derive it from the live artifact before inserting
>
> A backlog item drafted ahead of execution typically pins a **sequential artifact identifier** — a reviewer Check number, an Error Pattern Catalog row number, a reference §-number — to whatever was next-free *at draft time*. Those numbers are not stable: any other change that lands between drafting and execution consumes the next slot. Before inserting, re-derive the next-free identifier from the **live** artifact and renumber the deliverable (and any in-item self-references — group labels, acceptance criteria) to match.
>
> **Re-derive across every surface the identifier is allocated over, not just the one you remember.** An identifier space can span more than one file, and a recipe that reads a single surface returns a number another surface has already consumed. Reviewer Check numbers are the worked example: each check's body lives under its owning `references/*.md` section as `#### Reviewer Check {NNN}`, while a check whose Source is a handler may be retained **inline** in the agent as `### Check {NNN}`. Reading only the agent returns the one retained inline number and understates next-free by the whole relocated range.
>
> WRONG — trust the item's drafted number, or re-derive from a single surface:
> ```
> item says "add Check {NNN}" → insert it → two blocks now carry {NNN}.
> grep '^### Check 0' agents/{reviewer}.md      # only the inline-retained body — next-free looks far lower than it is
> # A duplicate identifier silently breaks cross-references and any detection grep keyed on the number.
> ```
>
> CORRECT — take the max across every allocating surface, then renumber:
> ```
> grep -rhoE '^#### Reviewer Check [0-9]{3}' references/ | grep -oE '[0-9]{3}' | sort -u | tail -1   # relocated bodies
> grep -ohE  '^### Check [0-9]{3}' agents/{reviewer}.md | grep -oE '[0-9]{3}' | sort -u | tail -1    # any body retained inline
> next-free = max(both) + 1 → insert at that number; update the item's group label + acceptance criteria to match.
> ```
>
> The rule generalises to any monotonically-allocated identifier (Check number, Error Pattern Catalog row, reference §-number). Cost: one grep per allocating surface per pinned identifier. Failure it prevents: a duplicate ID shipped in an artifact. Two corollaries: in a queue of promotions, the later-executed item MUST re-verify — an earlier-executed sibling may have consumed the slot; and **whenever a change relocates an identifier's bodies, re-derive this recipe's surface list in the same change** — a decomposition that moves the bodies out from under a recipe leaves that recipe silently allocating into occupied numbers.

### 9.2 Re-locate cited code anchors by symbol; re-check acceptance criteria against HEAD

> [!constraint] Treat a backlog item's `≈L####` as a hint, never an address; re-check every acceptance criterion against current code before writing a fix
>
> Line numbers and acceptance criteria are snapshots that rot as the codebase moves on. Before scoping or implementing, re-verify each against the **current** source:
>
> - **Anchors → re-locate by content.** Grep the cited function/symbol name; treat the item's `≈L####` as a hint, never an address. A partially-correct anchor set (some anchors still exact, some stale) is the dangerous case — it lulls you into trusting the rest.
> - **Acceptance criteria → re-check against HEAD.** A criterion may already be satisfied by code that landed after the item was authored. Run the cheapest proof (grep for the constant, a throwaway dry-run) before writing a fix, and record it as "already satisfied — verified" rather than silently dropping it.
>
> WRONG — read the cited line range directly:
> ```
> item cites "the comparison in foo.py (≈L1614–1628)" → read foo.py L1614–1628.
> # After the file grew, the real logic moved to a different function ~400 lines away; the read lands on unrelated code.
> ```
>
> CORRECT — re-locate by symbol, treat the line number as a cost hint only:
> ```
> grep -n "def _run_upgrade" foo.py   → real location of the logic
> # For each acceptance criterion, run the cheapest proof it is still unsatisfied before writing code.
> # A criterion already satisfied by later code → record "already satisfied — verified", never silently drop it.
> ```

### 9.3 Verify pre-drafted narrative attributions against the live file

> [!constraint] Verbatim fidelity binds the RULE CONTENT being promoted — not incidental wiring prose that names a sibling symbol; re-attribute those to the artifact that actually carries the behavior
>
> A backlog item's body is authored ahead of execution; its **narrative claims about which artifact carries which behavior** drift the same way pre-drafted sequential IDs and cited code anchors drift. Before inlining a pre-drafted note that asserts "test/section/function X does Y", verify the claim against the live file and reword to name the artifact that actually carries the behavior.
>
> WRONG — inline the item's note verbatim because the content was "fully specified":
> ```
> The `test_read_constants_are_fixed_values` test also asserts a cross-model
> ratio band: 1.4 ≤ … ≤ 1.55 (see …::test_cross_model_ratio_band).
> ```
> The note is internally contradictory: it attributes the assertion to one test, then cites a different one. `test_read_constants_are_fixed_values` asserts the FIXED caps only; the ratio band lives in the sibling method.
>
> CORRECT — read the live file first, then attribute to the method that actually holds the assertion:
> ```
> The read-constant tripwire is paired with a cross-model ratio-band assertion:
> `…::test_cross_model_ratio_band` asserts 1.4 ≤ opus/sonnet ≤ 1.55 for the same file.
> A ratio drift outside this band signals a tokenizer-weight change.
> ```
>
> Rule of thumb: a "paste verbatim" mandate covers the rule content and its WRONG/CORRECT examples; it never covers a factual claim about which test / section / function / check carries a behavior — those must match the live artifact.

---

## 10. Backlog-Item Claim Verification at Filing Time

§9 governs the citations an item carries, re-proven when the item is worked. §10 governs the claim an item makes, verified when the item is written. They are the same principle pointed in opposite directions; the second is more expensive to get wrong — a stale citation inside a real item wastes a lookup, a stale premise creates an item describing a condition that does not exist.

### 10.1 An item is a factual claim about the current repository

> [!constraint] An item is a factual claim about the current repository
>
> A backlog item asserts that some condition holds right now. Filing a false one is worse than filing nothing: it costs a future reader a full investigation to discover the condition is gone, and until they do, it distorts every prioritization pass reading the backlog. Before creating an item from a pre-computed list — a plan's out-of-scope table, an audit's findings, a prior session's deferred-work section — re-verify each condition against the live repository at filing time. The evidence line in the source is a pointer to how to check, not a substitute for checking. The freshness window is far shorter than it feels — treat any dated evidence as a statement about that date only, and treat "the plan was authored last week" as a strong signal, not a mild one.

### 10.2 "File N items" specifies scope, not that N conditions hold

> [!constraint] "File N items" specifies scope, not that N conditions hold
>
> A brief that says "file N items" specifies which gaps are in play, not that N conditions are still true. When the evidence for one has evaporated, filing N−1 with the discrepancy surfaced is the correct execution of that brief, not a shortfall against it. Surface, do not absorb: filing the item anyway pollutes the backlog with a false claim; dropping it wordlessly makes the next reader re-derive the whole question with no record anyone looked. The correct shape is: the runner reports, the orchestrator verifies independently, the decision is recorded.

### 10.3 Distinguish "already resolved" from "someone else has this in flight"

> [!constraint] Distinguish "already resolved" from "someone else has this in flight"
>
> Discovering a condition no longer holds is only half the verdict.
>
> ```bash
> git log -n 5 --format='%h %ad %an %s' --date=short -- {artifact_path}
> grep -rln "{artifact_or_symbol}" {backlog_dir}/*.md
> ```
>
> A fix landed by a differently-scoped change, and no existing item references the artifact → already resolved, do not file, record the finding. A fix in progress, or an existing item already covering it → coordinate rather than duplicate.

### 10.4 Reconcile the source, or it permanently asserts something false

> [!constraint] Reconcile the source, or it permanently asserts something false
>
> When re-verification retires a gap, the source document must be reconciled in the same change: mark the retired gap RESOLVED with the evidence and date, and amend any success criterion whose count the change invalidates. A count stated in a criterion is the same class of load-bearing claim as a count stated anywhere else.

---

## 11. Re-Alignment Verb Premise Probing

Some verbs assert. *Reconcile*, *re-target*, *re-align*, *align to the live shape*, *update to match* — each presupposes the thing being aligned to exists. The premise is never written down, so it is never checked, and it is the difference between a mechanical edit and a decision that needs a human. The preceding sections verify what an item cites and what an item claims; this one verifies what an item's instruction assumes.

### 11.1 Probe the premise at the family level before accepting a re-target framing

> [!constraint] Probe the premise at the family level before accepting a re-target framing
>
> When a backlog item, audit finding, or task brief prescribes reconciling/re-targeting/re-aligning something to "the live shape," treat the existence of that shape as UNVERIFIED until probed — before accepting the prescription's framing as mechanical. Probe at the family level, not the specific failing path: (1) the bare target — no parameters, no qualifiers; (2) representative variants across the parameter space, not only the one named; (3) the siblings the item groups it with — a shared prefix is not a shared contract.
>
> | Probe result | The task is |
> |---|---|
> | Bare target and variants respond | The mechanical reconciliation described. Proceed. |
> | Bare target and all variants absent | Not a re-target. A scope decision — what happens to consumers, columns, code that pointed at it — goes to the user. |
> | Siblings respond under a different contract | Two tasks of different kinds. Split them; route the design half. |
>
> Do not silently re-target to a guessed replacement, and do not silently delete the consumer half — both convert a decision into an edit and destroy the record that a decision was ever available. Only once the premise holds do further verification dimensions (key presence, shape, type alignment) apply — they all assume the thing responds. Generalizes past endpoints: any prescription aimed at an authority outside the repository — a vendor SDK surface, a published schema, an external registry — carries the same unstated premise. The rule is the verb, not the transport.

---

*Companion files: [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md), [verify-discovery-consolidation.md](verify-discovery-consolidation.md), [verify-cross-repo-fix-discipline.md](verify-cross-repo-fix-discipline.md), [exit-criteria-fidelity.md](exit-criteria-fidelity.md) (companion discipline — same re-verification principle, from the sprint-signoff entry point rather than backlog-triage).*
