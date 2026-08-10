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
  - [3j. Live-Verify Spawn-Prompt Tool-Name Drift](#3j-live-verify-spawn-prompt-tool-name-drift)
- [4. Plan-Authoring Pre-Flight Checklist](#4-plan-authoring-pre-flight-checklist)
- [5. Applies To](#5-applies-to)
- [Segment Index](#segment-index)

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

For internal project artifacts (lesson IDs, schema files, function names), see `verify-before-cite.md §9.B`.

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

*§3h, §3h.untested-axes, §3h.cluster and §3i (BLI triage-time recipes) live in [verify-backlog-citation-freshness.md](verify-backlog-citation-freshness.md), co-located with §9.*

### 3j. Live-Verify Spawn-Prompt Tool-Name Drift

A live-verify spawn prompt or task spec is a spec-like artifact. Any tool NAME it pins is an in-repo identifier subject to the same verify-against-shipped-artifact discipline as a third-party SDK type name or cross-sprint codebase symbol.

> [!constraint] Tool names in a live-verify spawn prompt or task spec MUST be verified against the deployed tool surface before authoring
> WRONG — name ID-lookup tools (or any tools) from convention or memory in the
> spawn prompt; the runner discovers the tools are absent at runtime:
> ```text
> Before acting, obtain ids:
>   --call list_widgets        (widget id)
>   --call list_categories     (category id)
> # Neither tool exists in the live tool surface — the runner discovers this at
> # runtime, mid-gate, costing a discovery cycle and a deviation note.
> ```
> Common failure mode: `list_*` is a plausible-sounding convention that is not
> actually the naming pattern used in the shipped tool surface.
>
> CORRECT — verify names against the deployed surface at authoring time, OR
> underspecify and instruct the runner to enumerate via the runtime's
> tool-discovery command and pick the closest equivalent; do not assume a
> `list_*` convention:
> ```text
> Before acting, obtain ids from the LIVE tool surface:
>   - widget id:   read_widgets       (verified present in the live tool surface)
>   - category id: ensure_categories (Matched outcome) or read_all_categories
> If a named tool is absent, enumerate via the runtime's tool-discovery command
> and pick the closest equivalent — do not assume list_*.
> ```
>
> Either verification approach costs under a minute:
> - The runtime's tool-enumeration / discovery command lists the registered tools
>   (the canonical runtime source of truth).
> - A grep of the tool-registration declarations in the server's source tree
>   confirms the shipped name set statically, without a live launch.

This extends §3d (tool / framework already wired in the project) from build-time framework drift to **runtime tool-name drift** in live-verify orchestration.

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
> - [ ] **BLI cluster recheck** (when triaging a BLI from a currently-IN_PROGRESS originating session OR ≥2 BLIs share `Surfaced by:` + `created:`): two-part driver-recheck per `verify-backlog-citation-freshness.md` §3h.cluster before any fresh routing; cluster-batch close option surfaced when Recovery confirms shared fix
> - [ ] **Intermittent-observation BLI Phase 1** (when authoring or triaging a BLI with a multi-cell reproducer matrix): coverage-gap analysis enumerates the (axis × value) cells the originating evidence did NOT cover; Phase 1 leads with those cells
> - [ ] **BLI motivating driver** (triage of items > 1 Sprint old, OR runtime-symptom drivers): symptom keyword grepped in current `src/` code AND in recent `{planwise_root}/{plans_dir}/**/Outputs/` session summaries; if neutralized by intervening work, "Close as CLOSED — driver neutralized" surfaced as an explicit route option before scope-based routing
> - [ ] **BLI cross-cutting scope** (DIRECT_FIX delegation): if the BLI names additional audit candidates ("Cross-cutting check" / "Cross-cutting consideration" / "Notes" mentioning latent defects in N other files), the fix-agent prompt lists each candidate with a one-line rationale; defect-class signal grepped in the candidate folder before delegation to confirm repo-wide scope

When verification is impractical or the artifact isn't available, mark the citation `(unverified)` in the spec and leave the keyword/positional choice to the implementer.

---

## 5. Applies To

- Discovery-phase Consolidated Context authoring (`{planwise_root}/{plans_dir}/**/*Discovery*.md`, `*Consolidated-Context*.md`) — see `verify-discovery-consolidation.md` §6.
- Execution Input authoring (`{planwise_root}/{plans_dir}/**/*-Execution-Input.md`).
- Task spec authoring (`{planwise_root}/{plans_dir}/**/*-S*-*-*.md`) when the task quotes a third-party SDK call, enum member, type name, harness API, or cross-sprint codebase symbol verbatim.
- Backlog item authoring (`{planwise_root}/{backlog_dir}/BB-*.md`) — the "Files" section is a placement assertion subject to §3g.
- Main-session triage handler (`/planwise backlog`) — Phase 3 (RESOLVE) MUST (a) cross-check every BLI-named path against the §3g table before generating a fix-agent spawn prompt, (b) re-verify the BLI's motivating driver per `verify-backlog-citation-freshness.md` §3h (including §3h.untested-axes and §3h.cluster) before routing any item whose driver is a runtime symptom or whose `created` date precedes the most recent Sprint by more than one cycle, AND (c) include the BLI's cross-cutting audit candidates per `verify-backlog-citation-freshness.md` §3i in any fix-agent spawn prompt routed to DIRECT_FIX.
- Reviewers running `/planwise review` — flag any unsourced identifier OR any file path under a force-read trigger of the consumer project's own scoped rules as a verification target before approving the plan.
- Fix-task authoring against canonical files **outside the working planwise repo** (sibling vendored repos, gitignored subfolders reached via `additionalDirectories`, out-of-tree package extractions, upstream plugin sources) — see `verify-cross-repo-fix-discipline.md` §7 for the BINDING SOURCE + Execution Step 1 mandate that binds at task-file authoring time, not just plan-author time.

---

## Segment Index

This file covers §1-§5 — the core SDK/identifier verification recipes, the pre-flight checklist, and applies-to scope. Three related disciplines split off into sibling files in the same pass, each keeping its original §-numbers:

| Segment | Content | File |
|---------|---------|------|
| §6 | Discovery-Phase Consolidation — Verify Citations and SDK Premises Against Live Source | [verify-discovery-consolidation.md](verify-discovery-consolidation.md) |
| §7 (.1-.7) | Cross-Repo Canonical Source — Fix-Task Authoring Discipline | [verify-cross-repo-fix-discipline.md](verify-cross-repo-fix-discipline.md) |
| §3h, §3h.untested-axes, §3h.cluster, §3i, §8, §9 (.1-.3) | BLI triage-time recipes + verifying source edits under an older installed plugin + backlog-item citation freshness at execution time | [verify-backlog-citation-freshness.md](verify-backlog-citation-freshness.md) |

---

*Companion files: [verify-discovery-consolidation.md](verify-discovery-consolidation.md), [verify-cross-repo-fix-discipline.md](verify-cross-repo-fix-discipline.md), [verify-backlog-citation-freshness.md](verify-backlog-citation-freshness.md), [verification-gates.md](verification-gates.md), [scaffolding-hygiene.md](scaffolding-hygiene.md), [ei-fidelity.md](ei-fidelity.md), [task-content-fidelity.md](task-content-fidelity.md), [agent-orchestration.md](agent-orchestration.md).*
