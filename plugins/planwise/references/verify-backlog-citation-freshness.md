---
description: BLI triage-time verification recipes (motivating-driver still-active recheck, un-tested-axes-first reproducer ordering, cluster-batch driver recheck, cross-cutting audit-candidate coverage at fix-agent delegation time), verifying source edits when the installed plugin is older than the source, and backlog-item citation freshness (pinned sequential identifiers, code anchors, narrative attributions, hand-authored tallies and membership lists, stated stale-side directions, contested counts) at execution time
consult-when: Triaging a BLI or checking backlog-citation freshness — pinned IDs, code anchors, hand-authored tallies and membership lists, a stated stale-side direction, a contested count, at execution time
---

# BLI Triage-Time Recipes and Backlog-Item Citation Freshness

Companion to [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) §1-§5 (the Exec-phase SDK/identifier verification core). This file carries two co-located disciplines that both operate on the backlog-item (BLI) surface: the BLI triage-time recipes peeled from that file's §3 ladder (§3h, §3h.untested-axes, §3h.cluster, §3i) plus its §8 (installed-plugin-version skew) and §9 (.1-.3) (backlog-item citation freshness at execution time) — original §-numbers preserved — plus this file's own §9.4-§9.6 (tallies, stated directions and contested counts as claims to re-derive), §10 (backlog-item claim verification at filing time), §11 (re-alignment verb premise probing), and §12 (verification task tree-state pin), native to this file rather than peeled from the parent.

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
  - [9.4 Enumerations, counts and memberships are pointers too](#94-enumerations-counts-and-memberships-are-pointers-too)
  - [9.5 A stated direction is a hypothesis scoped to the instance that produced it](#95-a-stated-direction-is-a-hypothesis-scoped-to-the-instance-that-produced-it)
  - [9.6 Derive a contested set; do not pick either number](#96-derive-a-contested-set-do-not-pick-either-number)
- [10. Backlog-Item Claim Verification at Filing Time](#10-backlog-item-claim-verification-at-filing-time)
  - [10.1 An item is a factual claim about the current repository](#101-an-item-is-a-factual-claim-about-the-current-repository)
  - [10.2 "File N items" specifies scope, not that N conditions hold](#102-file-n-items-specifies-scope-not-that-n-conditions-hold)
  - [10.3 Distinguish "already resolved" from "someone else has this in flight"](#103-distinguish-already-resolved-from-someone-else-has-this-in-flight)
  - [10.4 Reconcile the source, or it permanently asserts something false](#104-reconcile-the-source-or-it-permanently-asserts-something-false)
- [11. Re-Alignment Verb Premise Probing](#11-re-alignment-verb-premise-probing)
  - [11.1 Probe the premise at the family level before accepting a re-target framing](#111-probe-the-premise-at-the-family-level-before-accepting-a-re-target-framing)
- [12. Verification Task Tree-State Pin](#12-verification-task-tree-state-pin)
  - [12.1 Name the tree under test; one verdict per tree when they differ](#121-name-the-tree-under-test-one-verdict-per-tree-when-they-differ)
  - [12.2 Pin the tree state at both ends of the read window](#122-pin-the-tree-state-at-both-ends-of-the-read-window)
  - [12.3 Make divergence loud, not resolvable](#123-make-divergence-loud-not-resolvable)

---

### 3h. BLI Motivating Driver Still Active (Triage Time)

A BLI is a snapshot of a problem at filing time. Intervening work may have neutralized its motivating driver: a workaround, a refactor, a fix from a different angle, or a single `if` branch that makes the cited mechanism harmless. The BLI's narrative does not update itself. Without an explicit recheck, triage routes a still-IN_PROGRESS-on-paper item to a plan against a problem already solved.

The drift is most severe when the driver is **a runtime symptom** (collision, race, hang, missing endpoint, binding miss, silent failure, performance regression). The handler's staleness check (Phase 3 of `/planwise backlog`) catches a **measurable acceptance criterion** (line-count target, coverage %, schema diff). It does NOT catch a runtime symptom.

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
> WRONG — read the BLI, treat its "Summary" / "Surfaced by" prose as the current state, and route on scope keywords ("multi-phase", "refactor"):
> ```
> ITEM: {bli-id} — {bli-title}  (rationale: {runtime-symptom})
> Route: SESSION PLANNING   [the symptom was already neutralized in {session-id}]
> ```
> CORRECT — re-verify the motivating SYMPTOM (not the BLI's proposed solution) is still active in current code before routing. If the symptom has been neutralized by intervening work, present a "Close as CLOSED — driver neutralized" option alongside the scope-based routing:
> ```
> Driver recheck: symptom "{keyword}"; current code {file}:{line}; evidence {closeout-evidence-file}
> Driver status: NEUTRALIZED by {session-id}.
> Route options:
>   A. CLOSE — driver neutralized; remaining value does not justify multi-phase cost
>   B. SESSION PLANNING — only after explicit user acknowledgment that the driver is gone
> ```

### 3h.untested-axes Un-Tested Axes — Lead Phase 1 With the BLI's Blind Spots

When a BLI's evidence is intermittent, the original repro failed on some (object-class × count × version) combinations and not on others. The original session left **un-tested axes**. The BLI's prescribed Phase 1 matrix usually re-runs the originally-failed dimension first, which buries the cheapest disconfirmation cells. A coverage-gap analysis at triage time finds the cells the originating evidence never tested. Leading Phase 1 with those cells short-circuits the matrix when one of them PASSes.

> [!constraint] Phase 1 of an intermittent-observation BLI MUST test originally-untested axes FIRST
> WRONG — accept the BLI's prescribed reproducer matrix as-authored; Phase 1 cells mirror the originating session's setup (re-running the originally-failed dimension); the cheapest disconfirmation cell lives 5+ cells deep:
> ```
> Cell #1: {object-class-A} × {count-A} × {version-A}    ← re-runs S{XX}-{YY} setup
> ...
> Cell #6: {object-class-B} × {count-A} × {version-A}    ← UN-TESTED in original
> ```
> CORRECT — coverage-gap analysis enumerates the (axis × value) cells the originating evidence did NOT cover; Phase 1 leads with those cells; the matrix prunes aggressively when one of them PASSes:
> ```
> Coverage-gap analysis of {session-id} evidence:
>   - object-class axis: tested {object-class-A}; UN-TESTED: {object-class-B}
>   - version axis: tested {version-A}; UN-TESTED: {version-B}
> Reproducer matrix (Phase 1 — un-tested axes FIRST):
>   Cell #1: {object-class-B} × {count-A} × {version-A}    ← un-tested
>   Cell #2: {object-class-A} × {count-A} × {version-B}    ← un-tested
> [If Cell #1 PASSes, the object-class hypothesis is disconfirmed and the matrix prunes.]
> ```

> [!practice] When triaging an intermittent-observation BLI, surface the un-tested-axes pre-flight in the route assessment
> State in the routing recommendation that the prescribed matrix re-runs the originating session's failed dimension, and that the cheapest disconfirmation lives in cells that session never tested. Recommend re-ordering Phase 1 to lead with un-tested axes, so the user can approve the reorder before scaffolding cost is incurred.

### 3h.cluster Cluster Batching

The originating session may have fixed a BLI as collateral before its formal closeout. The index status (NOT_STARTED / IN_PROGRESS) then lags the actual state. A triage handler that trusts the index status routes the cluster to a fresh fix-agent session that re-does shipped work.

**Triage-time signals that a BLI may already be fixed by its originating session:**

| Signal | What to check |
|--------|---------------|
| `created` date matches the originating session's active window | Cross-reference `Surfaced by:` session ID's `Last Updated` in Recovery |
| `Surfaced by:` references a session that is IN_PROGRESS or in EVIDENCE_WRITING phase | Read the session's Recovery file Current Step + Phase |
| Multiple BLIs share the same Sprint+Session in `Surfaced by:`, same `created:` date, adjacent IDs | A cluster filed in a single triage pass often gets fixed in a single Step |
| Recovery file mentions the BLI ID in Step Completion or Key Findings | The originating session referenced the BLI during execution |
| Blocker chain: another open item lists this one in `blocks:`, or the body says it was filed from another item's follow-up | Check the blocker first. Closing a stale blocker often makes the dependent's own condition re-checkable with the same evidence |

**Operational rule — two-part driver-recheck for cluster signals:**

1. **Code-level grep** (§3h core recipe): grep the BLI's symptom keyword against `src/` to find any intervening fix.
2. **Live-verification recheck**: read the originating session's Recovery `## Step Completion Status` and `## Key Findings` to confirm the cluster's fixes were shipped together.

`scripts/parse_backlog.py --clusters` prints runs of adjacent ids that share `Surfaced by:` and `created:`, then exits 0.

> [!constraint] When BLI cluster signals fire, driver-recheck per §3h before any fresh routing; surface cluster-batch close option when Recovery confirms shared fix
> WRONG — trust the index status, route fresh fix-agent sessions per BLI in the cluster:
> ```
> Cluster: {bli-id-1}, {bli-id-2}, {bli-id-3} — all NOT_STARTED, same Surfaced by:
> Action: route 3 fresh fix-agent sessions; each re-does shipped work.
> ```
> CORRECT — perform a driver-recheck per §3h before routing; surface a cluster-batch close option when Recovery confirms the shared fix:
> ```
> Driver recheck:
>   - {session-id} Recovery Step {N} Key Findings: "Fixed {symptom-class} across
>     {bli-id-1}/{bli-id-2}/{bli-id-3} via {one-line description of fix}."
>   - grep -rn "{symptom-keyword}" src/ → matched at {file}:{line}: intervening fix
>     present.
>
> Route options:
>   A. CLUSTER CLOSE — mark all three CLOSED with reference to {session-id} Recovery Step {N},
>      pending formal closeout of {session-id}.
>   B. SCAFFOLD as separate items — only if the user disagrees with the cluster-fix evidence.
> ```

### 3i. BLI Cross-Cutting Check Coverage at Fix-Agent Delegation Time

A BLI's "Files Touched" section names the **primary** target file. Other sections may name **additional** files where the same defect class is suspected. The conditions table in this section lists them.

When the BLI routes to DIRECT_FIX, the fix-agent spawn prompt MUST include those audit candidates as in-scope unless the main session explicitly scopes them out. The defect class is repo-wide, so treating only the primary file leaves N-1 latent defects to surface in future live-verifies.

> [!constraint] Fix-agent spawn prompts MUST include the BLI's cross-cutting audit candidates as in-scope by default
> WRONG — copy only the BLI's "Files Touched" primary target into the fix-agent prompt; treat "Cross-cutting check" candidates as separate follow-up work:
> ```
> ## Item: {bli-id} — {defect-pattern}
> File: {src/module}/{PrimaryTarget}.{ext}
> [The same defect stays on N sister files and surfaces over the next N live-verifies.]
> ```
> CORRECT — read the BLI in full, identify the audit candidates from any "Cross-cutting" / "Notes" section, list them in the fix-agent's prompt with a one-line rationale per file:
> ```
> ## Item: {bli-id} — {defect-pattern} (cross-cutting)
> Files (cross-cutting per BLI Acceptance Criteria + Notes):
>   - {src/module}/{PrimaryTarget}.{ext} (primary)
>   - {src/module}/{Sister1}.{ext} (matches defect-class signal)
>   - {src/module}/{Sister3}.{ext} (verify shape; may not match — confirm before applying)
> Apply the same pattern to each. Verify Nth file's shape before applying.
> ```

**Practical pre-flight:** before delegating, verify the cross-cutting scope by grepping the defect-class signal in the candidate folder — e.g., `grep -r "{defect-class-signal}" {src/module}/` returning zero matches confirms the defect was repo-wide. Prefix any candidate the fix-agent should NOT touch with an explicit out-of-scope rationale; otherwise the agent assumes inclusion.

`scripts/parse_backlog.py --cross-cutting <ID> --prompt <FILE>` exits 1 when the item's Cross-cutting note names a file the prompt file does not list.

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

**Deterministic source-level evidence (reliable under version split):** the unit test suite run against the source directory, direct function or script calls against a temp copy of the edited file, read-only `--doctor` output, and static searches on the edited source text.

**Live-behavior signals (unreliable under version split — defer):** dispatched subagent runs, which load the *installed* agent definition, live path-rule injection probes, which reflect the *installed* handler, and any check that depends on the running harness loading the edited artifact.

**Model override weakens live signals further:** if a live acceptance check is forced to a model tier different from the fix's target (e.g., Opus 1M for a 200K-window overflow fix), name it a weakened signal and make the deterministic measurement primary.

**Recording deferred checks:** for each deferred signal, record the exact claim it tests and the post-`upgrade` command to re-run it. A deferred check is NOT a pass. It stays unresolved until post-install.

---

## 9. Backlog-Item Citation Freshness at Execution Time

A backlog item's body is a snapshot, and every reference it pins is a *hypothesis* about a live artifact, re-derived from the current artifact immediately before acting on it and never trusted. §9.1-§9.3 re-prove the pointers: a sequential identifier, a `file:line` code anchor with its acceptance criteria, and a narrative claim about which artifact carries which behavior. §9.4-§9.6 re-derive the claims an item computed for itself: tallies, stated directions and contested counts.

WRONG — apply the item's pinned citation verbatim because it read true when drafted. A stale citation applied this way ships a defect:
```
item: "insert as {next-free-id} at {file}:{line}"  ->  inserted as written
```
CORRECT — re-derive the reference from the current artifact, then act on the derived value:
```
Grep {artifact} for the live maximum and the symbol  ->  insert at the derived id and line
```

This is the backlog-execution sibling of `verify-cross-repo-fix-discipline.md` §7.3a–§7.3d (fix-recipe execution-time fidelity) and §8 above (verification under an older installed plugin). The drifting reference here is the item's own pre-drafted citation, not an audit recipe.

### 9.1 Re-derive pinned sequential identifiers from the live artifact

> [!constraint] A pre-drafted Check number / catalog row / §-number is next-free at DRAFT time only — re-derive it from the live artifact before inserting
>
> A backlog item typically pins a **sequential artifact identifier** — a reviewer Check number, an Error Pattern Catalog row number, a reference §-number — to whatever was next-free *at draft time*. Any change that lands before execution can consume that slot. Before inserting, re-derive the next-free identifier from the **live** artifact. Renumber the deliverable and any in-item self-references (group labels, acceptance criteria) to match.
>
> **Re-derive across every surface the identifier is allocated over, not just the one you remember.** Each reviewer check's body lives under its owning `references/*.md` section as `#### Reviewer Check {NNN}`, while a check whose Source is a handler may be retained **inline** in the agent as `### Check {NNN}`. Reading only the agent understates next-free by the whole relocated range.
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
> The rule generalises to any monotonically-allocated identifier. Two corollaries apply. In a queue of promotions, the later-executed item MUST re-verify, because an earlier-executed sibling may have consumed the slot. And **whenever a change relocates an identifier's bodies, re-derive this recipe's surface list in the same change**, because moved bodies leave the recipe silently allocating into occupied numbers.

**Mechanized form — prefer the script over re-deriving by hand.** `scripts/resolve_anchor.py` performs this re-derivation for three anchor shapes: `--scheme heading-toplevel` (`## N.`), `heading-sub` (`### {prefix}N`, with `--prefix`), and `table-row` (a leading numeric table column). It returns `max_found` and `next_free`. Its `--claim {claimant}` flag closes the first corollary: a per-repository ledger makes a second caller on the same `(file, scheme, prefix)` return one higher than an unconsumed claim. A claim releases itself when the live file's own maximum reaches it, so inserting the anchor IS the release. The script does **not** close the second corollary, because a relocated identifier family is a judgement about where content belongs. It emits an advisory warning when the target file carries a relocation-redirect marker. Treat that warning as a signal to read the redirect table, never as a reason to take a higher number in the same file.

### 9.2 Re-locate cited code anchors by symbol; re-check acceptance criteria against HEAD

> [!constraint] Treat a backlog item's `≈L####` as a hint, never an address; re-check every acceptance criterion against current code before writing a fix
>
> Line numbers and acceptance criteria are snapshots. Before scoping or implementing, re-verify each against the **current** source:
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
> ```

### 9.3 Verify pre-drafted narrative attributions against the live file

> [!constraint] Verbatim fidelity binds the RULE CONTENT being promoted — not incidental wiring prose that names a sibling symbol; re-attribute those to the artifact that actually carries the behavior
>
> An item's **narrative claims about which artifact carries which behavior** drift the same way sequential IDs and code anchors drift. Before inlining a note that asserts "test/section/function X does Y", verify the claim against the live file. Reword it to name the artifact that actually carries the behavior.
>
> WRONG — inline the item's note verbatim because the content was "fully specified":
> ```
> The `test_read_constants_are_fixed_values` test also asserts a cross-model
> ratio band: 1.4 ≤ … ≤ 1.55 (see …::test_cross_model_ratio_band).
> ```
> The note attributes the assertion to one test, then cites a different one. The ratio band lives in the sibling method.
>
> CORRECT — read the live file first, then attribute to the method that actually holds the assertion:
> ```
> The read-constant tripwire is paired with a cross-model ratio-band assertion:
> `…::test_cross_model_ratio_band` asserts 1.4 ≤ opus/sonnet ≤ 1.55 for the same file.
> A ratio drift outside this band signals a tokenizer-weight change.
> ```
>
> Rule of thumb: a "paste verbatim" mandate covers the rule content and its WRONG/CORRECT examples; it never covers a factual claim about which test / section / function / check carries a behavior — those must match the live artifact.

### 9.4 Enumerations, counts and memberships are pointers too

§9.1-§9.3 cover pointers whose *target* moved. A count is a different kind of claim: a measurement taken once at authoring time, against a corpus that has since moved — or one that was never taken carefully in the first place. It degrades the verification rather than the fix, which is why the work passing does not catch it.

> [!constraint] A tally in an item is a claim to re-derive — check membership, not only the named members
> An item's Proposed Solution said *"preserve list-valued pointers as lists (three named records carry YAML lists, not scalars)"*, and an acceptance criterion restated the same three. Dumping the frontmatter of all eleven in-scope records showed **six** carried lists. The parenthetical was not a pointer to anything. It was a count someone derived once and wrote down, wrong by a factor of two.
>
> The consequence is quiet. A migration script branching on the actual node type still handles all six. A reviewer verifying "list-valued pointers remain lists (A, B, C)" checks three files, sees three passes, and signs off having never looked at the other three.
>
> - For every "N items do X" claim, run the query that computes N from the live corpus, and reconcile it against the item's number.
> - For every explicit membership list, compute the true membership set — **check for members the item omitted**, not only that the named ones qualify.
> - Where the item's tally and the live count disagree, fix the item's derived **acceptance criteria** too. A criterion naming the wrong members verifies the wrong thing.
> - Report the correction in the closeout. A silently widened scope reads as unrequested scope creep.
>
> WRONG — verify the named members and stop:
> ```
>   item: "three records carry lists (A, B, C)"  →  check A, B, C  →  3 passes  →  sign off
>   [three other qualifying records were never examined]
> ```
>
> CORRECT — derive the set, then compare it to the item's list:
> ```
>   query every in-scope record for the property  →  {A, B, C, D, E, F}
>   item named 3 of 6  →  widen the criterion to all six; report the correction
> ```
>
> The calibration point: in the same item, two sibling tallies reconciled correctly. That is the argument for the check rather than against it. It is cheap, and it separates the tallies you can trust from the one you cannot.

[measure-aggregate-provenance.md](measure-aggregate-provenance.md) §3 owns the same defect on the reporting side — a bare count in prose is a claim, so name the members inline. This sub-rule is the triage-time consumer of such a count.

### 9.5 A stated direction is a hypothesis scoped to the instance that produced it

> [!constraint] "Which side is wrong" does not distribute across instances — re-derive it for every one
> An item reported that a handler and its binding reference disagreed about write scope, under a heading reading *"Why the handler is the one that is wrong"*, and proposed correcting the handler. For the reported instance that was right, and the reasoning was sound: it argued from the downstream contract. The item also asked, as an acceptance criterion, that the *sibling* mode in the same handler be checked for the same defect. There the disagreement was equally real and the direction was **exactly inverted**. Applying the item's stated direction mechanically would have deleted a correct description and replaced it with a stale one, as a "fix", with the item closing green.
>
> The trap is that the stated direction usually *is* right for the instance that motivated it. That instance was investigated, and the reader inherits well-earned confidence and spends it on instances that were never checked. A contradiction tells you two documents disagree and nothing more. Which one drifted is a separate inference requiring separate evidence, and it does not distribute: same author, same file pair, same defect class, opposite answer — because each side drifted at a different time for a different reason.
>
> 1. Read the stated direction as per-instance. Re-derive it from scratch for every additional instance; "same defect class" is a reason to look, never a reason to conclude.
> 2. **Break the tie on the downstream contract, not on document authority.** "The reference is binding" and "the handler is the entry point" are constant across both instances and therefore cannot distinguish them. Ask what a real consumer's behaviour depends on.
> 3. Use corroboration count as evidence. One isolated cell contradicting three concordant descriptions elsewhere is the stale cell.
> 4. **Write acceptance criteria that mandate the check without presupposing its outcome.**
>    WRONG — presupposes the direction:
>    ```
>    "correct the handler in both places"
>    [corrupts the inverted instance via a reviewer following the item faithfully]
>    ```
>    CORRECT — demands the comparison:
>    ```
>    "checked for the same drift; any mismatch fixed"
>    [leaves the direction open for each instance]
>    ```
>
> An inverted finding changes which file gets edited. Report it at the approval gate; never absorb it silently.

The brief-side of rule 4 — keep the dispatcher's expectation out of the instruction, and supply the discriminator rather than the destination — is [dispatch-brief-neutrality.md](dispatch-brief-neutrality.md) §2.

### 9.6 Derive a contested set; do not pick either number

> [!constraint] When two artifacts disagree on a count, find the rule that generates the set — a disagreement means at least one number was not derived, and usually neither was
> A scaffolded task said add **3** sibling references to a curated list. An upstream flag, recorded after that task was scaffolded, said the task owns all **11** the previous sprint created. Both were defensible. Neither was derived. The generating rule — a sibling joins the list if and only if its split anchor is already in the list — yielded **10 added, 1 excluded**. Neither 3 nor 11.
>
> 1. Treat **both** numbers as suspect.
> 2. **Find the rule that generates the set** from a property of the items themselves — something checkable per item, not a tally.
> 3. **Derive independently at both ends.** A pre-computed answer travels only when labelled as a cross-check with halt-on-disagreement: if the receiving end's own derivation differs from the number it was handed, stop and reconcile before acting. A cross-check that arrives labelled "the answer" is not a check.
> 4. **Record the excluded items with their reason.** "10 added" is unauditable; "10 added, one excluded because its anchor is unlisted" can be re-checked by anyone.
> 5. **Gate on the derivation, not the count.** Assert both the total *and* that the excluded item is absent, because a bare total passes even when the wrong 10 were added.
>
> A count gate confirms arithmetic. A derivation gate confirms **selection**.

The three sub-rules share one premise — the item's own prose is a claim — and fail differently, so their remedies do not substitute. Recomputing a tally does nothing for an inverted direction; re-deriving a direction does nothing for a contested count where **both** stated numbers are wrong. The flag-side of the same discipline — input-set enumeration, preserving a sender's text, re-deriving a flag's conclusion — is [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4.

---

## 10. Backlog-Item Claim Verification at Filing Time

§9 governs the citations an item carries, re-proven when the item is worked. §10 governs the claim an item makes, verified when the item is written. They are the same principle pointed in opposite directions; the second is more expensive to get wrong — a stale citation inside a real item wastes a lookup, a stale premise creates an item describing a condition that does not exist.

### 10.1 An item is a factual claim about the current repository

> [!constraint] An item is a factual claim about the current repository
>
> A backlog item asserts that some condition holds right now. A false one costs a future reader a full investigation, and until then it distorts every prioritization pass. Before creating an item from a pre-computed list — a plan's out-of-scope table, an audit's findings, a prior session's deferred-work section — re-verify each condition against the live repository at filing time. The evidence line in the source is a pointer to how to check, not a substitute for checking. Treat any dated evidence as a statement about that date only, and treat "the plan was authored last week" as a strong signal, not a mild one.
>
> WRONG — file from the list, because each row carries an evidence line.
>
> CORRECT — run the check the evidence line points to. File the item only if the condition still holds, and otherwise record the finding.

### 10.2 "File N items" specifies scope, not that N conditions hold

> [!constraint] "File N items" specifies scope, not that N conditions hold
>
> A brief that says "file N items" specifies which gaps are in play, not that N conditions are still true. When the evidence for one has evaporated, filing N−1 with the discrepancy surfaced is the correct execution of that brief. Surface, do not absorb.
>
> WRONG — file the item anyway, which pollutes the backlog with a false claim, or drop it wordlessly, which makes the next reader re-derive the whole question.
>
> CORRECT — the runner reports, the orchestrator verifies independently, and the decision is recorded.

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
> A fix landed by a differently-scoped change, and no existing item references the artifact → already resolved, do not file, record the finding. A fix in progress, or an existing item already covering it → coordinate rather than duplicate. `scripts/parse_backlog.py --in-flight <ID>` prints `git log -n 5` per artifact path and a backlog search for the item's symbol, then exits 0.
>
> WRONG — stop at "the condition no longer holds" and report it as resolved, so a fix in flight elsewhere goes unseen.
>
> CORRECT — read the artifact's history and the backlog first, then name which of the two verdicts applies.

### 10.4 Reconcile the source, or it permanently asserts something false

> [!constraint] Reconcile the source, or it permanently asserts something false
>
> When re-verification retires a gap, reconcile the source document in the same change: mark the retired gap RESOLVED with the evidence and date, and amend any success criterion whose count the change invalidates. A count stated in a criterion is the same class of load-bearing claim as a count stated anywhere else.
>
> WRONG — skip the filing and leave the source table listing the gap and the criterion still saying "file 5".
>
> CORRECT — mark the source row RESOLVED with evidence and date, and amend the criterion to "file 4", in the same change.

---

## 11. Re-Alignment Verb Premise Probing

Some verbs assert. *Reconcile*, *re-target*, *re-align*, *align to the live shape*, *update to match* — each presupposes the thing being aligned to exists. The premise is never written down, so it is never checked, and it is the difference between a mechanical edit and a decision that needs a human. The preceding sections verify what an item cites and what an item claims; this one verifies what an item's instruction assumes.

### 11.1 Probe the premise at the family level before accepting a re-target framing

> [!constraint] Probe the premise at the family level before accepting a re-target framing
>
> When a backlog item, audit finding, or task brief prescribes reconciling/re-targeting/re-aligning something to "the live shape," treat the existence of that shape as UNVERIFIED until probed. Probe at the family level, not the specific failing path: (1) the bare target — no parameters, no qualifiers; (2) representative variants across the parameter space, not only the one named; (3) the siblings the item groups it with — a shared prefix is not a shared contract.
>
> | Probe result | The task is |
> |---|---|
> | Bare target and variants respond | The mechanical reconciliation described. Proceed. |
> | Bare target and all variants absent | Not a re-target. A scope decision — what happens to consumers, columns, code that pointed at it — goes to the user. |
> | Siblings respond under a different contract | Two tasks of different kinds. Split them; route the design half. |
>
> Only once the premise holds do further verification dimensions (key presence, shape, type alignment) apply, because they all assume the thing responds. Any prescription aimed at an authority outside the repository — a vendor SDK surface, a published schema, an external registry — carries the same unstated premise. The rule is the verb, not the transport.
>
> WRONG — silently re-target to a guessed replacement, or silently delete the consumer half. Both convert a decision into an edit and destroy the record that a decision was ever available.
>
> CORRECT — probe the family first, and let the probe result in the table name the task.

---

## 12. Verification Task Tree-State Pin

This is a state-of-the-source discipline, distinct from §9 above: §9 keeps a backlog item's own citations from rotting between drafting and execution (a document-age concern), and this section keeps a verification task's read window honest about which physical tree it read (a tree-identity concern). Neither §8's install-skew coverage nor §9's citation-freshness coverage requires recording the identity of a source tree being read, addresses two co-existing trees whose answers legitimately differ, or tells a synthesizer how to treat a torn parallel read.

### 12.1 Name the tree under test; one verdict per tree when they differ

> [!constraint] Name the tree under test; give the claim one verdict per tree when they differ
>
> A task whose deliverable is a verdict about code state must record which tree it read. An unpinned verdict is not evidence: it cannot be reproduced, and it silently answers a different question than the one asked.
>
> | Column | Tree | Answers |
> |--------|------|---------|
> | `shipped` | the installed/released artifact | what users hit → sets execution scope and severity |
> | `wip` | the development tree | what is already done → prunes scope |
>
> Never collapse the columns. Never let a closed or archived item status remove something from scope without checking the shipped tree — an item's status tracks authoring, not shipping.
>
> WRONG — give one verdict for both trees, with scope set by the item's closed status.
>
> CORRECT — keep both columns, and give the claim one verdict per tree.

### 12.2 Pin the tree state at both ends of the read window

> [!constraint] Pin the tree state at both ends of the read window — the task's Step 0, and again as its last action
>
> ```bash
> git -C <repo> rev-parse HEAD
> git -C <repo> branch --show-current
> git -C <repo> status --porcelain <subtree>
> diff -q <shipped>/<file> <dev>/<file>     # per file: SAME needs one read, DIFFERENT needs two
> ```
>
> Both stamps go in the output header and the status block. The `SAME`/`DIFFERENT` matrix also halves the reading — only diverged files need a second pass.
>
> WRONG — stamp only the start of the read window, or record no stamps.
>
> CORRECT — stamp at the task's Step 0 and again as its last action.
>
> These stamps pin *which tree* was read. Where a concurrent writer is possible, they do not say whether the files' bytes held still between the two stamps; add the content-hash pins at both ends and both layers from [measure-artifact-identity.md](measure-artifact-identity.md) §2.

`scripts/tree_pin.py stamp` writes the stamps to a file outside the repository. Its `compare` mode re-takes the stamps and compares them with that file.

### 12.3 Make divergence loud, not resolvable

> [!constraint] Make divergence loud, not resolvable
>
> Where parallel readers share a mutating tree, the synthesizer compares the pins *before* adjudicating anything. If the pins differ, or either reader reports CHANGED, the disagreement is a moving-tree artifact: re-read the symbol directly from the named tree. Only when both pins match may a disagreement be settled on evidence quality.
>
> WRONG — resolve a torn read as if it were a reasoning disagreement:
> ```
> Step 2. Verify each claim against the live tree by CONTENT search.
> …
> [synthesis] where they conflict, the more specific evidence wins.
> ```
> CORRECT — compare pins first; a mismatch is re-read, never adjudicated:
> ```
> pins differ, OR either reader reports CHANGED  → moving-tree artifact: re-read the symbol
>                                                    directly from the named tree
> pins match                                      → a real reasoning disagreement: settle on
>                                                    evidence quality
> ```

`scripts/tree_pin.py compare` re-takes a reader's stamps and compares them with its stamp file.

**Applies to:** any task whose deliverable is a verdict about code state — defect verification, drift detection, audit, forensics, shipped-vs-source reconciliation — especially when readers run in parallel, when the repo is not exclusively owned by the session, or when a fix is known to be in flight.

---

*Companion files: [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md), [verify-discovery-consolidation.md](verify-discovery-consolidation.md), [verify-cross-repo-fix-discipline.md](verify-cross-repo-fix-discipline.md), [exit-criteria-fidelity.md](exit-criteria-fidelity.md) (companion discipline — same re-verification principle, from the sprint-signoff entry point rather than backlog-triage).*
