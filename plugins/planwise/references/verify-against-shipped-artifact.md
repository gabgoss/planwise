---
description: Plan/EI/BLI/task-spec citations of third-party SDK identifiers, type names, enum members, delegate shapes, framework presence, destination file paths under scoped-rule triggers, AND BLI motivating drivers (runtime symptoms cited as multi-phase plan rationale) MUST be verified against the shipped artifact (DLL reflection, vendor XML index, package on disk, current src/ code, recent session summaries) or the relevant project-scoped rule before being authored as prescriptive snippets, routed to a multi-session plan, or delegated to a fix-agent
paths: {planwise_root}/{plans_dir}/**
---

# Verify Against Shipped Artifact — Plan-Author-Time Discipline

**Purpose:** Force plan-time verification of every cited third-party identifier, destination file path, and BLI motivating driver against the shipped artifact (or the project's own scoped rules) so drift is caught at planning cost, not build-cycle or run-time cost. Extends from Exec-phase specs (EIs, task specs, BLIs) to Discovery-phase consolidation.

## Table of Contents

- [1. The Recurring Failure Mode](#1-the-recurring-failure-mode)
- [2. Verify Before Pinning](#2-verify-before-pinning)
- [3. Verification Recipes by Drift Surface](#3-verification-recipes-by-drift-surface)
  - [3a. SDK Named Parameters](#3a-sdk-named-parameters)
  - [3a.2 Cross-Sprint Code Symbols](#3a2-cross-sprint-code-symbols)
  - [3b. Type / Enum Presence Across Target Versions](#3b-type--enum-presence-across-target-versions)
  - [3b.archive Already-Derived Findings — Do NOT Re-Run the Probe](#3barchive-already-derived-findings--do-not-re-run-the-probe)
  - [3c. Decompiled Enum Members and Property Names](#3c-decompiled-enum-members-and-property-names)
  - [3d. Tool / Framework Already Wired in the Project](#3d-tool--framework-already-wired-in-the-project)
  - [3e. SDK Delegate Signatures](#3e-sdk-delegate-signatures)
  - [3f. Vendored Harness API Surface](#3f-vendored-harness-api-surface)
  - [3g. Internal Placement / Scoped-Rule Constraints](#3g-internal-placement--scoped-rule-constraints)
  - [3h. BLI Motivating Driver Still Active (Triage Time)](#3h-bli-motivating-driver-still-active-triage-time)
  - [3h.untested-axes Un-Tested Axes — Lead Phase 1 With the BLI's Blind Spots](#3huntested-axes-un-tested-axes--lead-phase-1-with-the-blis-blind-spots)
  - [3h.cluster Cluster Batching](#3hcluster-cluster-batching)
  - [3i. BLI Cross-Cutting Check Coverage at Fix-Agent Delegation Time](#3i-bli-cross-cutting-check-coverage-at-fix-agent-delegation-time)
- [4. Plan-Authoring Pre-Flight Checklist](#4-plan-authoring-pre-flight-checklist)
- [5. Applies To](#5-applies-to)
- [6. Discovery-Phase Consolidation — Verify Citations and SDK Premises Against Live Source](#6-discovery-phase-consolidation--verify-citations-and-sdk-premises-against-live-source)
- [7. Cross-Repo Canonical Source — Fix-Task Authoring Discipline](#7-cross-repo-canonical-source--fix-task-authoring-discipline)
  - [7.1 The recurring failure mode](#71-the-recurring-failure-mode)
  - [7.2 Rule — Required Context table MUST include the canonical source as a BINDING SOURCE row](#72-rule--required-context-table-must-include-the-canonical-source-as-a-binding-source-row)
  - [7.3 Rule — Execution Step 1 MUST be the canonical-file full read](#73-rule--execution-step-1-must-be-the-canonical-file-full-read)
  - [7.4 Why task-level enforcement, not reference-level](#74-why-task-level-enforcement-not-reference-level)
  - [7.5 Scaffold-time verification command](#75-scaffold-time-verification-command)
  - [7.6 Exempt task types](#76-exempt-task-types)
  - [7.7 Applies-to surface](#77-applies-to-surface)

---

## 1. The Recurring Failure Mode

A plan or Execution Input pins a third-party identifier — an SDK named parameter, an enum member, a type's presence in a target version, a delegate signature, or a vendored package's exported surface. The identifier was sourced from memory, paraphrased docs, decompiled output, or speculative templating. The implementing agent copies it verbatim. The build fails at compile time, or — worse — fails silently at run time because a similarly-named member still exists with different semantics.

| Drift surface | Plan-side citation form | Discovery-time miss | Run-time miss |
|---------------|------------------------|--------------------|--------------|
| SDK named parameters | `Foo(jsonSerializerOptions: null)` | Author paraphrased from memory or older SDK docs | Build error against the pinned package version |
| Type / enum presence across versions | Polyfill keyed on `{external-system-api}` for the newest target | Type marked obsolete in current SDK; assumed still-present in older targets | Compile error against the older target |
| Decompiled enum members / property names | `{ConcreteType}.{member}` lifted from raw decompiler output | Decompiled identifiers may be parameter names, internal aliases, or decompiler guesses | Member-not-found at run-time against the shipped DLL |
| Tool / framework already wired | "Tests use {framework-X}" when project has {framework-Y} | Spec author didn't read the project's existing build / test config | Mid-execution pivot or two-step migration |
| SDK delegate signatures | `Filter(ctx, next, ct)` middleware-style sketch | Author guessed shape; SDK uses middleware-factory `(next) => handler` | Registration-site type mismatch / missing type |
| Vendored harness API surface | `{Harness}.SomeContext.CurrentSession()` | Author wrote a name from README narrative; package exposes a different surface | Symbol not found / type missing |
| Internal placement / project scoped-rule constraints | A new public type proposed for an assembly whose project rules forbid that kind of type | Author didn't cross-check the project's own scoped rules — the destination has invariants encoded in a rule file, not in the compiler | Build clean + unit tests pass; silent failure at first live invocation, with no audit trail |
| BLI motivating driver | A runtime symptom (collision, race, hang, missing endpoint) cited as the rationale for a multi-phase plan | Triage handler routed to a meta-plan + execution plan without rechecking whether intervening sessions had already neutralized the driver | Multiple session-budgets spent scaffolding/executing a plan against a problem that no longer exists |

The plan-side cost of verification (one minute of reflection or grep) is two orders of magnitude smaller than the build-cycle cost (build + deviation note + Recovery update + sometimes a Sprint pivot). For internal-placement drift the cost asymmetry is even worse — the failure surfaces only at live invocation time, after a deploy + relaunch + interactive click. For motivating-driver drift the cost asymmetry is the worst of all — the "failure" is sunk planning effort against a non-problem, with no compiler or runtime signal to surface it.

For internal project artifacts (lesson IDs, schema files, function names), see `task-content-fidelity.md §9.B`.

---

## 2. Verify Before Pinning

> [!constraint] Cited identifiers MUST be verified against the shipped artifact at plan-write time
> WRONG — author the EI / task spec from memory, paraphrased SDK docs, decompiled output, or speculative templating, then leave the implementing agent to discover the drift at first build:
> ```markdown
> ## §5 Implementation
>
> Register the audit filter:
>
> ```{lang}
> async (ctx, next, ct) => { ... }
> filters.Add(AuditFilter);
> ```
> ```
> CORRECT — verify the identifier against the shipped artifact before pinning. Cite as **declared by the artifact**, not as paraphrased:
> ```markdown
> ## §5 Implementation
>
> Verified `{InterfaceType}<TReq, TRes>` shape against `{ExternalSdk}.dll`
> {pinned-version} via `typeof({InterfaceType}<,>).GetMethod("Invoke")` — it is a
> middleware-factory delegate `(next) => handler`, NOT a handler with `next` as a
> parameter. Register via method-group reference.
>
> ```{lang}
> {ConcreteType}<TReq, TRes> Create({ConcreteType}<TReq, TRes> next) =>
>     async (ctx, ct) => { ... };
>
> filters.AddCallToolFilter(auditFilter.Create);
> ```
> ```

> [!practice] When verification is impractical, leave the spec underspecified
> If the planner cannot verify a named argument or signature, write the spec with positional arguments and omit the parameter name — let the implementer add the keyword after IDE/IntelliSense confirms it. An honest underspecification beats a confident wrong identifier. Mark the citation `(unverified)` in the spec.

---

## 3. Verification Recipes by Drift Surface

Each recipe states the probe in generic terms (reflection of the shipped artifact, `grep` against the project tree, a scratch build against the pinned package). Adapt the concrete command form to your language / runtime / package manager.

### 3a. SDK Named Parameters

> [!verify] Verify a named-argument signature against the pinned package
> ```
> # Locate the pinned package on disk (consumer adapts to their package manager):
> {pkg-locate-cmd} {package-name} --version {pinned-version}
> # → e.g. <package-cache-root>/{package-name}/{pinned-version}/
> ```
> Open the shipped artifact in a reflection / decompilation tool, OR run a 1-line probe in a scratch project against the pinned reference and check IDE diagnostics / build for an argument-name error. Cite the parameter as declared by the SDK.

### 3a.2 Cross-Sprint Code Symbols

EI sketches at scaffold time can pin (a) non-existent third-party type names sourced from memory ("the interface is called `{InterfaceType}`") and (b) cross-sprint codebase symbols that don't actually exist ("Sprint-N already shipped `{handler-name}`"). The first class fails at first build; the second class fails when the dependent sprint can't find what it was told already exists.

> [!verify] Verify SDK type names and cross-sprint codebase symbols before citing in an EI
> ```
> # SDK types (post-restore — locate the pinned package + reflect public types):
> {pkg-locate-cmd} {package-name} --version {pinned-version}
> # Reflect the package's exported types and grep for the name you intend to cite.
>
> # Cross-sprint codebase symbols (the EI cites a "Sprint-N already-shipped" symbol):
> grep -rln "{SymbolName}" src/
> ```
> If the SDK reflection returns zero rows matching the cited type, the EI is citing a phantom — re-pin to the actual shipped type. If the cross-sprint codebase grep returns zero matches, the prior sprint did NOT ship what the EI assumes — re-spec the EI section to use the actual current API surface OR add a precursor task that produces the missing symbol.

> [!constraint] EI sketches MUST cite SDK type names and cross-sprint codebase symbols only after verification against the shipped artifact / current code
> WRONG — EI sketch in `{Abbrev}-S{XX}-Execution-Input.md` cites a type name from memory and a "Sprint-N already-shipped" symbol without grep:
> ```markdown
> ## §3 Integration
>
> The handler implements `{InterfaceType}` from `{ExternalSdk}` (verified at planning).
> It consumes Sprint-3's `{handler-name}` to dispatch domain events.
> ```
> ```
> grep -rln "{handler-name}" src/   →   (empty)
> reflection probe of {ExternalSdk}.dll   →   public types: { {ConcreteType}, ... }   (no {InterfaceType})
> ```
> CORRECT — verify both citations against the shipped artifact and current source; re-pin with the actual shapes and annotate the verification:
> ```markdown
> ## §3 Integration
>
> Verified `{ExternalSdk}` 1.0.0 exposes the concrete class `{ConcreteType}`, NOT an
> `{InterfaceType}` (reflected 2026-MM-DD via the package on disk; zero rows match
> `{InterfaceType}` in the exported types).
>
> Verified `{handler-name}` is NOT present in the current src/ tree
> (`grep -rln "{handler-name}" src/` → empty as of 2026-MM-DD); the current dispatch
> surface is `{actual-symbol}`. Sprint-N produced the dispatch surface under that
> name — re-pin the integration to consume `{actual-symbol}`.
> ```

### 3b. Type / Enum Presence Across Target Versions

For polyfills, multi-target projects, or any reference to an external system whose API surface drifts across versions, verify the type/member's presence in the **oldest** target version before keying logic on it.

> [!verify] Verify an external-system type / member exists in the OLDEST target version before keying logic on it
> ```
> # Type-level probe — query the vendor's index / shipped artifact for the target version:
> grep -E '"T:{namespace}\.{TypeName}' "{vendor-api-index-for-target-version}"
> # Empty result → the type is gone in this target; redesign the polyfill to avoid keying on it.
>
> # Member-level probe (field / property / method on a type that does exist):
> grep -E '"(F|P|M):{namespace}\.{TypeName}\.{MemberName}' \
>   "{vendor-api-index-for-target-version}"
> ```
> Run for every target version the polyfill is meant to support. A type with zero entries in the oldest target is a **planning blocker**, not an implementation hurdle — re-spec before the task reaches the build stage.

Major-version deprecation in many external systems is a deletion timer, not a permanent compatibility guarantee. The same caution applies to enum members removed in a major version, properties promoted from one type to another, and any "deprecated since vN" type.

### 3b.archive Already-Derived Findings — Do NOT Re-Run the Probe

When a §3b probe has already been run and confirmed a phantom API (an identifier authors keep proposing that does NOT exist in the shipped artifact across the targeted versions), the result is archival. Future authors should NOT re-derive it. Capture the finding in this table, format:

| Phantom API (NOT shipped) | Targeted versions verified absent | Actual shipped APIs | Source |
|---------------------------|----------------------------------|---------------------|--------|
| *(illustrative format row only — populate per-project as findings accumulate)* `{external-system-api}({param-shape})` | `{version-1}`, `{version-2}`, `{version-3}` | `{alternative-api-1}({correct-shape})` (read-only), `{alternative-api-2}({correct-shape})` (destructive, requires transaction) | Verified by `{session-id}` against shipped artifact |

> [!practice] If a phantom-API row exists for an external-system identifier, pivot directly to the listed actual API — do NOT re-run the probe
> Future plans / EIs / fix-agent prompts whose initial spec mentions a phantom API listed above MUST pivot to the listed actual shipped APIs directly. The probe has already been run and the result is archived. Re-running the probe to re-derive an already-known answer wastes a planning cycle and risks producing a different paraphrase that drifts the spec yet again.

### 3c. Decompiled Enum Members and Property Names

Decompilation-derived identifiers — enum members, struct fields, parameter names — are best-effort approximations. The decompiler may insert human-readable guesses, expose internal aliases, or print parameter names that differ from the public API surface.

> [!verify] Verify decompiled identifiers against the shipped artifact via reflection
> ```
> # Enum members (consumer adapts the reflection form to their language):
> {load-assembly-from-path} '{external-system-dll}'
> {GetEnumNames}({external-system-namespace}.{TypeName})
> # → returns the actual public enum names — compare to what the decompiler suggested.
>
> # Struct / class members:
> {GetMembers}({external-system-namespace}.{TypeName})
> #   Filter to Field / Property as needed.
> ```

> [!practice] Mark unverified decompiled identifiers in Discovery-phase Consolidated Context
> When authoring Consolidated Context parts from decompiled output, suffix every uncertain identifier with `(decompiled — verify)` so downstream Execution Inputs preserve the uncertainty signal instead of laundering decompilation guesses into prescriptive adapter snippets.

### 3d. Tool / Framework Already Wired in the Project

When the spec calls for a tool (test framework, formatter, linter, code-gen package) that has not yet been wired into the project, the spec author may not know.

> [!decide] Defer the spec-prescribed tool when ALL three signals fire
> | Signal | Where to check |
> |--------|---------------|
> | The project's existing convention disagrees with the spec | `grep -r '{dependency-declaration-keyword}' {build-config-glob}`; read existing test/source files |
> | A later session in the same plan already plans the migration | Read the Master Plan / Sprint Overview rows |
> | Cross-tool coexistence requires non-trivial config | Mixed-runner / mixed-build research |
>
> When all three fire, the spec was likely written speculatively. Defer to the migration session and document the deviation in the Recovery + Summary; do NOT chase the spec letter at the cost of project consistency.

### 3e. SDK Delegate Signatures

> [!verify] Verify an SDK delegate's invocation signature before sketching consumer code
> ```
> # Scratch program, 5 lines, against the pinned package (consumer adapts to language):
> var m = {reflection-form-for-typeof}({ExternalSdk}.{DelegateType}<TReq, TRes>)
>             .GetMethod("Invoke");
> print(m);
> # → returns the declared Invoke signature.
> #   Compare to the sketch — does it accept (next) and return a handler, or
> #   does it accept (ctx, next, ct) directly?
> ```
> ALSO ACCEPTABLE — open the assembly in a decompiler / reflector and inspect the delegate declaration directly. Both costs are sub-minute.

### 3f. Vendored Harness API Surface

When the spec references a vendored test harness, base class, or helper API, verify the actual exposed surface before authoring per-checkpoint test bodies.

> [!verify] Verify a vendored harness exposes the surface the spec assumes
> ```
> # Locate the package's lib folder:
> {pkg-locate-cmd} {harness-package} --version {pinned-version}
>
> # Reflect public types and inheritance chain (adapt to language):
> {load-assembly-from-path} '<path>/lib/<target-fwk>/{harness-package}.dll'
> {GetExportedTypes}() | for-each { print("$name :: base=$baseName") }
> # Reveals actual class hierarchy and exposed properties — compare to the spec's
> # assumed types, base classes, and property names.
> ```
> Also verify the package namespace order — vendors sometimes invert the canonical order in README narratives and blog posts. Always cite the namespace as it appears in the reflected `FullName`, not as it appears in marketing copy.

### 3g. Internal Placement / Scoped-Rule Constraints

A BLI's "Files" section, a plan task spec's destination paths, and a fix-agent spawn prompt all assert *where* code should live. The destination assembly / module / package frequently carries non-obvious constraints encoded in **the project's own scoped rules** — not in the compiler, not in unit tests. Build-clean and unit-test-green do NOT validate these constraints; the failure mode surfaces only at live invocation.

> [!verify] Cross-check proposed destination paths against the project's own scoped rules before pinning
> Before naming a destination path in a BLI's "Files" section, in a plan task spec, or in a fix-agent spawn prompt, identify whether the path falls under any project rule's force-read trigger. Source of truth: the project's `CLAUDE.md` or scoped-rules index (each project's own rules — there is no global "scoped rules" list authored at plugin level).
>
> ```
> # 1. Locate the project's scoped-rules registry:
> #    Common locations — CLAUDE.md "Force-read when" table, .claude/rules/{domain}/,
> #    or a domain-specific rules folder declared in the project's own conventions.
> #
> # 2. For each path you intend to pin, check whether it matches a force-read trigger:
> grep -E '{proposed-path-glob}' {scoped-rules-registry}
> #
> # 3. If a trigger fires, EITHER (a) read the rule and re-pick the path so the
> #    trigger no longer fires (move the type to a different module), OR (b) inline
> #    the rule's relevant section verbatim into the spawn prompt — path-scoped
> #    rules do NOT auto-load in spawned subagent contexts at startup.
> ```

> [!constraint] Main session MUST force-read project scoped rules before delegating a fix-agent prompt that names paths under their triggers
> WRONG — copy the BLI's "Files" section verbatim into the fix-agent spawn prompt, trust build + unit tests as sufficient evidence:
> ```
> Destination (NEW) | {src/module-A}/Audit/{NewClassifier}.{ext}  (BLI's intent)
>
> [Build clean. Unit tests pass. Live invocation: error response, audit log not
>  written — silent failure because {src/module-A} is governed by a project
>  scoped rule the planner did not read.]
> ```
> CORRECT — recognise the path falls under a force-read trigger, force-load the rule, then either correct the path before delegating OR inline the rule's relevant section so the fix-agent (which has no path-rule auto-load) sees the constraint:
> ```
> Destination (NEW) | {src/module-B}/Audit/{NewClassifier}.{ext}
>                     — per {project's scoped-rule file} §{section}: types of this
>                       kind in {src/module-A} trigger the failure mode documented
>                       in that rule. Stay in {src/module-B}.
> ```

The asymmetry is unforgiving: each project's scoped rule is authored to encode a previous incident's empirical findings — those rules exist precisely because the failure mode silently passes a build + test gate. Skipping the cross-check at delegation time re-runs the original incident.

> [!practice] Project-scoped rules are the source of truth — NOT the plugin's reference set
> This reference (`verify-against-shipped-artifact.md`) describes *the discipline of cross-checking*. It does NOT list any project's specific scoped rules — those live in the consumer project's own `CLAUDE.md` / `.claude/rules/{domain}/` tree. Authors and reviewers MUST consult **the project's own scoped-rules registry**, not this file, for the list of force-read triggers that apply to the work at hand.

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

## 4. Plan-Authoring Pre-Flight Checklist

> [!checklist] Before pinning a third-party identifier OR a file path in an EI / task spec / BLI / fix-agent prompt
> - [ ] **SDK named arguments**: signature checked against the pinned package (reflection, decompiler, or scratch build)
> - [ ] **Type / enum presence**: confirmed in the vendor's index / shipped artifact for the OLDEST target version (every version a polyfill must support)
> - [ ] **Decompiled identifiers**: re-verified via reflection-based enum/member listing; flagged `(decompiled — verify)` if not yet re-checked
> - [ ] **Tool / framework**: presence in the project's existing build / test config confirmed via grep; deferral signals applied if the project disagrees
> - [ ] **SDK delegate signatures**: `typeof(Delegate).GetMethod("Invoke")`-equivalent printed and compared to the sketch
> - [ ] **Vendored harness**: exported types and inheritance chain reflected; package namespace order verified against the reflected `FullName`
> - [ ] **File paths**: each named destination cross-checked against **the project's own scoped-rules registry** (CLAUDE.md "Force-read when" or equivalent) — if any rule fires, the rule has been read AND either the path was re-picked OR the rule's relevant section inlined into the spawn prompt
> - [ ] **Cross-sprint codebase symbols** (when EI cites a "Sprint-N already-shipped" handler / service / helper): `grep -rln "{SymbolName}" src/` returns ≥1 match; if zero matches, re-spec the EI section to use the actual API surface OR add a precursor task that produces the symbol
> - [ ] **BLI cluster recheck** (when triaging a BLI from a currently-IN_PROGRESS originating session OR ≥2 BLIs share `Surfaced by:` + `created:`): two-part driver-recheck per §3h.cluster before any fresh routing; cluster-batch close option surfaced when Recovery confirms shared fix
> - [ ] **Intermittent-observation BLI Phase 1** (when authoring or triaging a BLI with a multi-cell reproducer matrix): coverage-gap analysis enumerates the (axis × value) cells the originating evidence did NOT cover; Phase 1 leads with those cells
> - [ ] **BLI motivating driver** (triage of items > 1 Sprint old, OR runtime-symptom drivers): symptom keyword grepped in current `src/` code AND in recent `{planwise_root}/{plans_dir}/**/Outputs/` session summaries; if neutralized by intervening work, "Close as CLOSED — driver neutralized" surfaced as an explicit route option before scope-based routing
> - [ ] **BLI cross-cutting scope** (DIRECT_FIX delegation): if the BLI names additional audit candidates ("Cross-cutting check" / "Cross-cutting consideration" / "Notes" mentioning latent defects in N other files), the fix-agent prompt lists each candidate with a one-line rationale; defect-class signal grepped in the candidate folder before delegation to confirm repo-wide scope

When verification is impractical or the artifact isn't available, mark the citation `(unverified)` in the spec and leave the keyword/positional choice to the implementer.

---

## 5. Applies To

- Discovery-phase Consolidated Context authoring (`{planwise_root}/{plans_dir}/**/*Discovery*.md`, `*Consolidated-Context*.md`) — see §6 below.
- Execution Input authoring (`{planwise_root}/{plans_dir}/**/*-Execution-Input.md`).
- Task spec authoring (`{planwise_root}/{plans_dir}/**/*-S*-*-*.md`) when the task quotes a third-party SDK call, enum member, type name, harness API, or cross-sprint codebase symbol verbatim.
- Backlog item authoring (`{planwise_root}/{backlog_dir}/BB-*.md`) — the "Files" section is a placement assertion subject to §3g.
- Main-session triage handler (`/planwise backlog`) — Phase 3 (RESOLVE) MUST (a) cross-check every BLI-named path against the §3g table before generating a fix-agent spawn prompt, (b) re-verify the BLI's motivating driver per §3h (including §3h.untested-axes and §3h.cluster) before routing any item whose driver is a runtime symptom or whose `created` date precedes the most recent Sprint by more than one cycle, AND (c) include the BLI's cross-cutting audit candidates per §3i in any fix-agent spawn prompt routed to DIRECT_FIX.
- Reviewers running `/planwise review` — flag any unsourced identifier OR any file path under a force-read trigger of the consumer project's own scoped rules as a verification target before approving the plan.
- Fix-task authoring against canonical files **outside the working planwise repo** (sibling vendored repos, gitignored subfolders reached via `additionalDirectories`, out-of-tree package extractions, upstream plugin sources) — see §7 below for the BINDING SOURCE + Execution Step 1 mandate that binds at task-file authoring time, not just plan-author time.

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

## 7. Cross-Repo Canonical Source — Fix-Task Authoring Discipline

When a fix task modifies a file that lives **outside the working planwise repo** — in a vendored sibling repo, a gitignored subfolder reached via `additionalDirectories`, an out-of-tree package extraction, or an upstream plugin source — the audit excerpts and consolidated specs that drove the fix are NOT the source of truth. The live canonical file is. This section binds the discipline that keeps fix agents from working off stale snapshots.

§6 catches citation drift at consolidation-authoring time (the Discovery agent verifies against live source while writing the Part). §7 catches the same class of drift at fix-task **execution** time, when the consolidated spec has already locked the line citations and a downstream Sonnet agent is about to apply them. §7 is the cross-repo execution-time complement to §6's consolidation-time discipline.

### 7.1 The recurring failure mode

A multi-stage plan (Audit → Consolidate → Scaffold → Execute) routinely produces fix tasks that quote `file:line` ranges and code-fragment excerpts from a source file in a sibling / vendored / external-to-working-repo location. By the time the fix task is dispatched:

- Lines may have shifted (the file was edited between audit and execute)
- Surrounding context (function signatures, sibling sections, conditional branches) is invisible in the excerpt
- Verification grep patterns in the spec assume the file's current state, not the snapshot state

A Sonnet (or any general-purpose) agent that begins reasoning from the excerpt — without first reading the canonical file in full — will either fix the wrong line range, miss a surrounding invariant that the spec author saw but the excerpt didn't capture, OR produce a verification grep that returns a misleading hit because the live file's identifiers have drifted.

### 7.2 Rule — Required Context table MUST include the canonical source as a BINDING SOURCE row

Every fix task whose target file lives in a cross-repo / vendored / external-to-working-repo location MUST include a Priority-1 row in its Required Context table pointing at the canonical file, with this exact annotation in the Purpose column:

```
| 1 | {canonical-cross-repo-path} | ~{N} | ~{X}K | **BINDING SOURCE — full read required, do not work from audit excerpts** |
```

The audit-derivative artifact (findings report, Consolidated Context Part, EI section) stays in Required Context — typically as Priority 2 — because it carries the decision rationale, the proposed edit recipe, and any cross-finding context. But the audit-derivative is NEVER the BINDING SOURCE. That label is reserved for the live canonical file.

> [!constraint] BINDING SOURCE label is reserved for the live cross-repo canonical file
> WRONG — the audit / Consolidated-Context Part is annotated as the source-of-truth in the task's Required Context table; the canonical cross-repo file is either omitted or downgraded to Priority 2:
> ```
> | Priority | File | Purpose |
> |----------|------|---------|
> | 1 | {planwise_root}/{plans_dir}/.../*-Consolidated-Context-Part-{N}.md | Audit edit-recipe + line ranges (BINDING SOURCE) |
> | 2 | {canonical-cross-repo-path} | Reference — read if needed |
> ```
> CORRECT — the canonical cross-repo file is the Priority-1 BINDING SOURCE; the audit / Consolidated Context Part is Priority 2, supporting context only:
> ```
> | Priority | File | Purpose |
> |----------|------|---------|
> | 1 | {canonical-cross-repo-path} | **BINDING SOURCE — full read required, do not work from audit excerpts** |
> | 2 | {planwise_root}/{plans_dir}/.../*-Consolidated-Context-Part-{N}.md | Decision rationale + edit recipe + line ranges (snapshot, may have drifted) |
> ```

### 7.3 Rule — Execution Step 1 MUST be the canonical-file full read

Every fix task targeting a cross-repo canonical file MUST begin its Execution Steps with this exact step (verbatim, not paraphrased, not folded into a generic "read context" preamble):

```
1. Read `{canonical-cross-repo-path}` in full before any fix reasoning. Do NOT begin from audit excerpts or Consolidated-Context Part snippets. The canonical file at the cited path is the source of truth.
```

This is the FIRST step — before "build mental model of fix", before "verify line ranges from audit", before any code edit. The full-read gate exists because agents have historically conflated audit excerpts with live state and shipped fixes that no longer apply.

### 7.4 Why task-level enforcement, not reference-level

Documenting canonical-source discipline only in a reference file (such as this one) has historically produced variable adherence — "the agent should know to do this" devolves into the agent NOT doing it whenever the reference doesn't load into the agent's context window at execution time. By forcing the rule into every fix-task file's Required Context table AND Execution Steps Step 1, the discipline becomes:

- **Visible in the file the agent is reading** — not in a sibling reference doc the agent might or might not load
- **Mechanically grep-checkable by `/planwise review`** — the review handler greps each fix-task file for the BINDING SOURCE annotation and the Step-1 verbatim string; missing-pattern findings are BLOCKER-severity
- **Enforced at scaffold time** — `/planwise plan --scaffold` either emits compliant task files or it doesn't; a non-compliant task file is a structural finding that blocks plan completion

### 7.5 Scaffold-time verification command

After `/planwise plan --scaffold` produces fix-task files for a plan whose target files live cross-repo, the planner / reviewer MUST run:

> [!verify] Cross-repo fix-task BINDING SOURCE + Step-1 compliance check
> ```bash
> # Each fix-task file MUST return at least one match for both patterns.
> # Adapt the glob to your plan's abbreviation + sprint/session/task layout:
> grep -lE "BINDING SOURCE . full read required" \
>   {planwise_root}/{plans_dir}/{PlanName}/Sprint-*/Session-*/{Abbrev}-S*-*-*-*.md
> grep -lE "Read .* in full before any fix reasoning" \
>   {planwise_root}/{plans_dir}/{PlanName}/Sprint-*/Session-*/{Abbrev}-S*-*-*-*.md
> ```
>
> Any fix-task file missing either pattern is non-compliant; the scaffolding agent MUST regenerate it. `/planwise review` SHOULD codify this check in its Error Pattern Catalog at BLOCKER severity when the plan's target files live cross-repo.

### 7.6 Exempt task types

§7.2 and §7.3 apply to **FIX tasks** — Sonnet (or general-purpose) agents performing code/markdown edits on cross-repo canonical files. The following task types are exempt:

| Exempt task type | Reason |
|------------------|--------|
| Human-gate decision tasks | The "fix" is a human conversation (release-target choice, scope decision, gate approval); no canonical-file read required at decision time. The follow-up Sonnet edit task IS subject to the rules. |
| Cumulative-diff triage by Opus | When Opus reads the cumulative plan diff (already-applied changes) for a sprint-end readiness signal, the diff itself is the source of truth at that point. Opus may consult canonical files as needed but is not bound by the Step-1-full-read mandate. |
| Audit / discovery / research tasks | Tasks whose output is a findings report, a Consolidated Context Part, or an EI extraction. These are read-only against canonical files; §6 already covers their drift discipline. |
| Tasks whose target file lives inside the working planwise repo | §7 applies to **cross-repo** canonical files. For files inside the same repo as the plan (`{planwise_root}/{plans_dir}/...`, `src/...`, etc.), the standard Required Context discipline and §6 verify-during-consolidation discipline are sufficient. |

All other cross-repo fix tasks MUST comply.

### 7.7 Applies-to surface

§7 binds for plans where the target plugin / package / artifact lives in any of these locations:

- A sibling repo cloned into a gitignored subfolder of the working tree (e.g., a vendored upstream plugin source, an integration test harness checkout, a docs-as-code mirror)
- An out-of-tree path on the consumer's machine reachable only via `additionalDirectories` configuration
- An upstream package cache or vendor extraction whose live state may diverge from the snapshot captured in audit excerpts

The §3g internal-placement check (the project's own scoped-rules registry) is the in-repo analog of §7; together they cover both axes of "the spec quotes a file path; the agent must verify against the live destination, not the spec snapshot."

---

*Cross-references: [verification-gates.md](verification-gates.md), [scaffolding-hygiene.md](scaffolding-hygiene.md), [ei-fidelity.md](ei-fidelity.md), [task-content-fidelity.md](task-content-fidelity.md), [agent-orchestration.md](agent-orchestration.md).*
