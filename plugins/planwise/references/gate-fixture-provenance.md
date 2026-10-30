---
description: A fixture is never built through the API under test (§5); a known-good probe names a real target, and both halves the same one (§6); a fixture set spans input shapes, not only families (§7), and a writer's or migrator's fixture is seeded from the live file's real shapes and dry-run twice on a scratch copy (§7.1); a proof reports what it does not cover in the same breath as the result (§8); and completeness is verified against the spec's enumeration, never against the artifact (§9).
consult-when: Building a fixture or probe, releasing a writer or migrator over a user-maintained file, or reporting a proof's coverage — never through the API under test (§5), a real target for both halves (§6), input shapes not families (§7), seed from the live file and dry-run twice on a scratch copy (§7.1), report what is not covered (§8), completeness against the spec's enumeration (§9)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Fixture Provenance (An Input Set That Could Have Contained the Defect)

**Purpose:** The runs happened, the outputs differed, the criterion was satisfied, and the input set could not have contained the defect. This file governs where a gate's inputs come from and what a proof says about the inputs it never saw. Split from `verification-gate-evidence.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gate-evidence.md §N` citation translates by filename alone. The family index is `verification-gate-evidence.md`.

**Read this when** you build a fixture or a probe for a gate, you release a parser, writer or migrator that rewrites a user-maintained markdown file, or you report a proof's result and its coverage.

## Table of Contents

- [5. A Fixture Must Not Be Built Through the API Under Test](#5-a-fixture-must-not-be-built-through-the-api-under-test)
- [6. A Known-Good Probe Must Name a Real Target — and Both Halves the SAME One](#6-a-known-good-probe-must-name-a-real-target--and-both-halves-the-same-one)
- [7. A Fixture Set Must Span Input SHAPES, Not Only Families](#7-a-fixture-set-must-span-input-shapes-not-only-families)
  - [7.1 Writers and Migrators: Seed a Fixture From the Live Artifact, and Dry-Run Twice on a Copy](#71-writers-and-migrators-seed-a-fixture-from-the-live-artifact-and-dry-run-twice-on-a-copy)
- [8. Report What the Proof Does NOT Cover, in the Same Breath as the Result](#8-report-what-the-proof-does-not-cover-in-the-same-breath-as-the-result)
- [9. Verify Completeness Against the Spec's Enumeration, Never Against the Artifact](#9-verify-completeness-against-the-specs-enumeration-never-against-the-artifact)

---

## 5. A Fixture Must Not Be Built Through the API Under Test

`gate-positive-and-mutation-controls.md` §1-§4 assume the control ran. §5-§9 here cover the input set below that control.

**Rule:** when the property under test is how bytes are STORED, write the fixture as bytes. A fixture built through the same convenience API the implementation uses inherits that API's normalization. The test then sees only behavior the normalization has already erased. The sibling cases beyond line endings are byte-order-mark handling, trailing-newline policy, Unicode normalization, and text-mode encoding fallbacks.

> [!constraint] Write the fixture as bytes
> WRONG — the fixture helper uses the API the bug uses, so defect and fixture cancel out:
> ```python
> path.write_text(content, encoding="utf-8")     # newline=None → os.linesep
> ```
> CORRECT — the fixture holds the exact bytes under test:
> ```python
> path.write_bytes(b"| a | b |\n| c | d |\n")    # LF stays LF on every platform
> ```

Both directions are required, because each fails on only one platform:

| Test | Fails pre-fix on | Passes pre-fix on |
|---|---|---|
| LF fixture must stay LF | Windows (`os.linesep == "\r\n"`) | POSIX |
| CRLF fixture must stay CRLF | POSIX | Windows |

Keep both assertions even when one cannot fail on the host you run. Report that half as unexercised-by-platform, never as passing evidence. Make a house discipline such as a newline-preserving read helper reachable from the **task** ("adding a destructive in-place write"), not only from the module that defines it.

A test's hard-coded line endings for a checked-in file: [gate-generated-input-integrity.md](gate-generated-input-integrity.md) §21.

## 6. A Known-Good Probe Must Name a Real Target — and Both Halves the SAME One

**Rule:** a known-good probe must resolve its path, so a fake path makes it unpassable by construction, while a known-bad probe is decided before it executes.

> [!constraint] Both halves name the same real target
> WRONG — one placeholder convention across the pair, and the known-good row can never pass:
> ```
> known-bad:  cd /c/x/agents && wc -l a.md b.md              → DENY
> known-good: wc -l /c/x/agents/a.md /c/x/agents/b.md        → No such file or directory
> ```
> CORRECT — both rows name one real directory, and the expected output is concrete:
> ```
> known-bad:  cd <real dir> && wc -l a.md b.md                → DENY
> known-good: wc -l <real dir>/a.md <real dir>/b.md           → PASS, "232 total"
> ```

Four rules follow:

1. **Do not apply the placeholder convention uniformly.** Placeholders are safe in known-bad probes and fatal in known-good ones.
2. **Repoint the known-bad half to follow the known-good one**, so the pair stays identical modulo the variable under test.
3. **State the expected output concretely** — `50`, `182`, `232 total`. "Genuine stdout" is satisfied by anything.
4. **A re-runnable procedure needs a substitution instruction** naming what a later runner must swap, with the same-target constraint restated at the substitution point.

## 7. A Fixture Set Must Span Input SHAPES, Not Only Families

**Rule:** coverage over input *families* and coverage over input *shapes* are independent axes, so a fixture set covers both and then runs the check against its own defining file.

For any check that runs over authored markdown, fixture one instance of each shape:

| # | Shape |
|---|---|
| 1 | Markdown table row |
| 2 | Fenced code block line |
| 3 | Inline code span in prose |
| 4 | Plain English prose |
| 5 | Comment inside a fence |

> [!constraint] Span both axes, then self-apply
> WRONG — fixture set exhaustive over exempt families, monotone over syntactic shape:
> ```
> known-bad:  2 fenced-code lines
> known-good: 20 lines, one per exempt family — all fenced code or prose
> result:     runs differ → criterion satisfied → gate declared proven
> reality:    blind to every markdown table row; fires on the English word "find"
> ```
> CORRECT — fixture set spans both axes, plus self-application:
> ```
> known-bad:  one per shape (table row, fenced code, inline span, comment) × violating verb
> known-good: one per exempt family × at least two shapes, plus prose using the verb in English
> self-apply: run the check against the rule file that defines it; classify every hit
> result:     three directions, each with a stated expected outcome
> ```

Two corollaries:

- **Self-application is a cheap third direction.** Run the finished check against the artifact that defines it. Expect the WRONG exemplars to fire, and classify every surviving hit. Anything unclassifiable is a defect, not a footnote.
- **A delegated verdict can be accurate in every reported number and still wrong.** Verifying the figures re-verifies the runner's *reading*. Only the orchestrator can check the runner's **choice of fixtures** as a claim.

[`gate-instrument-proof-obligations.md`](gate-instrument-proof-obligations.md) §10 obligation C owns the neighbouring defect: a pattern that cannot see the shape it counts. §7 here is about the fixture set rather than the pattern. Read both.

### 7.1 Writers and Migrators: Seed a Fixture From the Live Artifact, and Dry-Run Twice on a Copy

**Rule:** seed a writer's or migrator's fixture from the live file's real shapes, and dry-run the tool twice on a scratch copy of live data before release. A green suite over invented fixtures says nothing about the shapes people and older tools wrote into the live file.

> [!constraint] The fixture carries what the live file carries
> WRONG — the fixture is the spec:
> ```
> changelog = "## Entry 2\nbody\n\n## Entry 1\nbody\n"   # only the canonical shape
> ```
> CORRECT — the fixture carries what the live file carries:
> ```
> changelog = ("## Entry 2 — <date>\nbody\n```md\n## Context\n```\n\n"
>              "## Drift Record\nnotes\n\n## Entry 1\nbody\n")
> # plus: run the tool twice on a scratch copy of the live tree
> ```

Two operative points:

1. **Seed at least one fixture from the real artifact's shapes.** Take the non-standard headings, fenced content, hand-written variants and mixed line endings the live file holds. Reduce each to its smallest form. Add each shape a dry run finds as a permanent regression fixture.
2. **Dry-run every writer or migrator on a scratch copy of live data before release, and run it twice.** The second run proves the tool accepts its own output.

The plugin repo's `tests/test_migrators_idempotent.py` checks that each registered migrator has a run-twice test.

This applies to any parser, writer, renumberer or migrator that rewrites a user-maintained markdown file, such as a changelog, an index or a log. It also applies to any release gate for such a tool. It applies most when the file predates the tool or people have edited it by hand. §5 covers how the fixture is built, §7 covers which shapes it spans, and this subsection covers where the shapes come from.

## 8. Report What the Proof Does NOT Cover, in the Same Breath as the Result

**Rule:** bound the proof by its own frame, in the sentence that states the result.

> [!constraint] Bound the proof by its own frame
> WRONG — report the proof and let its scope go unstated:
> ```
> Gate proof: known-bad 0 vs 5 (discriminates), known-clean 0 vs 0. PASSED.
> → downstream reads: "the fence count is correct"
> ```
> CORRECT — report the proof bounded by its own frame:
> ```
> Gate proof: known-bad 0 vs 5 (discriminates), known-clean 0 vs 0. PASSED.
> Covers: tagged fences, blockquoted or not.
> Does NOT cover: untagged fences, fences tagged with a non-shell language,
>                 or shell verbs absent from the declared verb set.
> → therefore every fence count in this session is a LOWER BOUND, not a census.
> ```

**Compute no coverage percentage against a lower bound.** A percentage silently converts "at least N" into "exactly N", and that is where an undercount becomes invisible.

A known-clean file returning zero under both patterns carries **no** information about coverage. It would return zero under a pattern for a language nobody writes, too.

**The cheap screen:** for any pattern gate, write down the class the known-bad file exercises. Anything outside that class is unproven, whatever the gate returned.

## 9. Verify Completeness Against the Spec's Enumeration, Never Against the Artifact

**Rule:** verify completeness by walking the spec's clause list against the file, because density and sibling comparison cannot detect one absent clause.

| Question asked | Question needed |
|---|---|
| *Is this file suspiciously thin?* | *Does this file contain every clause the spec requires?* |
| Evidence: density vs siblings, plus a full read of the region judged riskiest | Evidence: the spec's clause list, walked one at a time against the file |

**Completeness is never verifiable from the inside.** A missing clause has no representation in the artifact, and an untested input shape has no representation in the fixture set. The spec-first direction cannot miss, because the enumeration is external to the thing being checked.

> [!constraint] Walk the clause list, not the density
> WRONG — explain the number with density evidence, and close the question:
> ```
> handler: 251 lines against an advisory 450-550
> evidence: heading density matches six siblings; riskiest region read in full
> verdict:  complete       ← one spec-mandated clause is still missing
> ```
> CORRECT — treat the deviation as a prompt and walk the spec's enumeration:
> ```
> handler: 251 lines against an advisory 450-550
> walk:    spec clause 1 … N, each located in the file or reported absent
> verdict:  clause 7 absent → reported to the spec holder, not repaired
> ```

Five application rules:

1. **A budget deviation is a prompt to verify completeness, not a claim to adjudicate.** The correct response to "251 lines against an advisory 450-550" is *walk the clause list*, not *explain the number*.
2. **Structural evidence bounds an explanation, never establishes completeness.** Density, heading count and sibling comparison legitimately answer *"is this truncated?"*. Report them as answering that.
3. **A spot-read of the riskiest region is a sample.** Say so when reporting it.
4. **When a cross-file claim disagrees, go to the spec before deciding which side is wrong.** A dangling "documented in X" reference is symmetric evidence. A required clause that no sibling cites leaves no trace at all.
5. **A verifier that finds a defect reports it rather than repairing it.** Adjudication belongs to whoever holds the spec, the artifact and the authority together.

This section is deliberately written without a mechanical gate. "Walk the spec's enumeration" cannot be asserted by a match pattern, so the pair above shows a report's shape, not a verification command.

---

*Cross-references: [gate-positive-and-mutation-controls.md](gate-positive-and-mutation-controls.md) (§1-§4, the controls these inputs feed) · [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10 obligations C and D) · [gate-generated-input-integrity.md](gate-generated-input-integrity.md) §21 (a test never hard-codes a checked-in file's line endings) · [gate-denominator-integrity.md](gate-denominator-integrity.md) (the denominator comes from outside the artifact) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
