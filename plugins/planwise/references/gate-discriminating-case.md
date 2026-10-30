---
description: A gate result is evidence only if the input set could have contained the case that fails it, and that case goes missing in four places - behind a boundary the extractor drew wrongly (§1), outside the slice a runner was given (§2), below a metric's own threshold (§3), and on a failure branch that a forecast hides (§4) - so ask one question before citing any gate (§5).
consult-when: About to cite a gate result as proof — could its input set have contained the case that fails it? An extraction boundary needs an interior and an exterior probe (§1), a sweep several runners share is gated at session scope over the full corpus (§2), a fixture must cross its metric's own threshold, not only beat the clean one (§3), and a per-item gate takes the operation's observed result, not a forecast, with a failure-injection test (§4); the one question that unifies the four (§5)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Discriminating Case (An Input Set That Could Have Failed the Gate)

**Purpose:** A gate ran, nothing errored, and the result was recorded as verification. The run carried no information, because the input set could not contain the case that would fail it. This file names the four places that case goes missing and the practice that closes each. The sections are numbered 1 to 5 in this file. They are new rules, not former sections of `verification-gate-evidence.md`. The family index is `verification-gate-evidence.md`.

**Read this when** you author or accept a gate that checks an extraction, a split or an anchor, a sweep that several runners share, a fixture set scored against a threshold, or a per-item gate that is fed a precomputed value.

## Table of Contents

- [1. A Gate That Asserts an Operation Succeeded Has Not Asserted It Produced the Right Output](#1-a-gate-that-asserts-an-operation-succeeded-has-not-asserted-it-produced-the-right-output)
- [2. Locate the Gate at the Scope of the Property's Quantifier](#2-locate-the-gate-at-the-scope-of-the-propertys-quantifier)
- [3. Assert the Crossing, Not the Direction](#3-assert-the-crossing-not-the-direction)
- [4. A Per-Item Gate Is Only as Good as the Provenance of What It Is Fed](#4-a-per-item-gate-is-only-as-good-as-the-provenance-of-what-it-is-fed)
- [5. The One Question That Unifies the Four](#5-the-one-question-that-unifies-the-four)

---

## 1. A Gate That Asserts an Operation Succeeded Has Not Asserted It Produced the Right Output

The first place the failing case hides is behind a boundary. "The anchor matched" and "the anchor matched the right thing" are different claims. An anchor-found check tests only the first. The same hole sits in every check of this general form:

- anchor-resolution checks
- regex boundary detection
- "found N matches" assertions
- split and segmentation steps
- scope-boundary derivations

Assert a property of what the step captured. Do not assert that the step ran.

> [!constraint] Assert a property of the captured span, not that the anchor resolved
> WRONG — assert only that the anchor resolved:
> ```python
> idx = find_anchor(lines, WORD_LIST_START)
> if idx is None:
>     sys.exit(f"anchor not found: {WORD_LIST_START}")
> write_section("10-dictionary-intro.txt", lines[intro_idx:idx])
> # Exits 0 and reports FOUND whether idx is the true boundary or a heading ten pages early.
> ```
> CORRECT — assert a property of what was captured:
> ```python
> section = lines[intro_idx:idx]
> # Positive control: content known to belong INSIDE this section must be present.
> for probe in REQUIRED_INTERIOR_PROBES:
>     if not any(probe in ln.lower() for ln in section):
>         sys.exit(f"boundary suspect: '{probe}' expected inside section but absent")
> # Negative control: content known to belong AFTER it must be absent.
> for probe_re in FORBIDDEN_PROBES:
>     if any(probe_re.match(ln) for ln in section):
>         sys.exit("boundary suspect: exterior content leaked into section")
> write_section("10-dictionary-intro.txt", section)
> ```

Three practices close the hole.

1. **Pair every boundary with an interior probe and an exterior probe.** One term must appear inside the captured span. One term must not. Take the probes from the consumer's contract, meaning what the downstream task was promised. Do not take them from the extractor's own assumptions.
2. **Prefer an anchor the artifact asserts about itself over an anchor that describes its typography.** When only a shape heuristic is available, the probes in practice 1 are not optional.
3. **Treat a downstream "required content absent" report as an upstream-scope signal, not a content limitation.** Locate the material in the un-segmented original before you accept the gap as a property of the source.

---

## 2. Locate the Gate at the Scope of the Property's Quantifier

The second place the failing case hides is outside the slice a runner was given. A runner that gates only its own slice has a denominator that is a strict subset of the corpus. Only the party that holds the full corpus can see that the input set was a subset.

> [!constraint] A runner's self-check is a drafting aid, and a session-scope gate is the evidence
> WRONG — each runner self-certifies over its own slice, and the orchestrator aggregates the PASSes:
> ```
> runner A: sweep(inputs=A_sections)  → 0 hits → PASS ─┐
> runner B: sweep(inputs=B_sections)  → 0 hits → PASS ─┼→ "all clean"   ← unproven
> runner C: sweep(inputs=C_sections)  → 0 hits → PASS ─┘
> # Collisions against material outside each runner's own slice are undetectable by construction.
> ```
> CORRECT — runner self-checks give fast feedback, and a session-scope gate is the evidence:
> ```
> runner A/B/C: sweep(own inputs) → fast feedback while drafting, NOT the gate
> orchestrator/gate task: sweep(source=FULL corpus, subjects=ALL deliverables) → exit 0
> # Plus: dry-run the gate against known-bad and known-clean first, so "0 hits"
> # is known to be discrimination rather than a gate that cannot fire.
> ```

Three practices close the hole.

1. **Locate the gate at the scope of the property's quantifier.** "No deliverable shares 12 words with the source" quantifies over the whole source and all deliverables. It belongs in a session-level task that holds both.
2. **Say so in the dispatch prompt, and say why.** A capable runner otherwise shrinks the corpus to its own inputs. It reasons that it cannot have copied text it never read. That reasoning is sound about copying and unsound about collision.
3. **Keep the per-task self-check as fast feedback.** Never let it stand in for the session gate.

`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md` §1.29.4 carries the dispatch-prompt requirement. This section owns the case where the denominator is a subset. It does not cover a property that exists only in the relationship between runners.

---

## 3. Assert the Crossing, Not the Direction

The third place the failing case hides is below the threshold. A fixture can contain the construction its metric looks for and pass a directional test (`bad > clean`). It can still produce no finding at any threshold the linter ships with. The present but sub-threshold case reads as coverage in every summary.

The two fixtures in this table each contain their metric's construction, and neither fires:

| Fixture | Metric | Measured | Check limit | Fires? |
|---|---|---:|---:|:--:|
| `choppy.md` | phrasal verbs | 1.0309 /100w | 1.5 | **no** |
| `passive_heavy.md` | present perfect | 0.7874 /100w | 1.5 | **no** |

A discrimination table whose bad values cross their own check limits proves that each fixture would fail the gate on that metric alone. A table that shows only `bad > clean` proves the metric is monotonic and nothing else.

> [!constraint] Assert that the bad fixture crosses the check limit, not only that it beats the clean one
> WRONG — assert only the direction:
> ```python
> assert score(bad) > score(clean)    # passes for choppy.md at 1.0309, which never fires at 1.5
> ```
> CORRECT — assert the crossing of the metric's own check limit:
> ```python
> assert score(bad) >= CHECK_LIMIT    # fails for choppy.md at 1.0309: the fixture is sub-threshold
> assert score(clean) < CHECK_LIMIT
> ```

Two practices close the hole.

- **Score existing fixtures before you author new ones, and record the numbers.** A measurement defines the gap. Reading the fixture does not.
- **Re-run the discrimination gate after any threshold change.** Raising a provisional threshold can silently stop a metric from firing. The evidence is valid only at the values it was measured against.

---

## 4. A Per-Item Gate Is Only as Good as the Provenance of What It Is Fed

The fourth place the failing case hides is on the failure branch that nobody exercised. A value computed before the operation ran is a prediction that the operation succeeds.

**A forecast is correct exactly whenever the operation succeeds.** Every test that does not inject a failure exercises the path where prediction and observation agree. A green suite is therefore the expected reading whether or not the bug is present.

> [!constraint] Feed the gate the operation's observed result, not the forecast
> WRONG — feed the gate the classification computed before the operation ran:
> ```python
> for f in item["files"]:
>     c = _classify_file(f["path"], ...)
>     link_results.append((c["file"], True, "moved to Archive"))  # a PREDICTION
> ...
> archive_item_files(backlog_dir, archive_dir, move_basenames)     # result discarded
> update_index_links_to_archive(content, item_id, link_results)    # gate trusts the guess
> ```
> CORRECT — let the operation's actual result overwrite the prediction for everything it touched:
> ```python
> for basename, success, message in archive_item_files(backlog_dir, archive_dir, move_basenames):
>     link_results[basename] = (success, message)   # OBSERVED wins over predicted
> update_index_links_to_archive(content, item_id, [...link_results...])
> ```

Entries the operation never touched keep their predicted value, because the operation was never asked about them. The overlay applies only to what the operation actually attempted.

Three practices close the hole.

1. **Enumerate the call sites before you design the gate, and ask each one the same question.** Is the value observed or predicted? A call site that computes the fact ahead of the operation is where the forecast slips in.
2. **Demand a failure-injection test as part of the fix, not as later hardening.** Patch the operation to fail for one item while its sibling succeeds. Then assert both the filesystem state and the recorded state.
3. **Do not treat a fix that resolves the reported symptom as complete.** Fixing the instance and inheriting the class is how a defect survives its own remediation.

---

## 5. The One Question That Unifies the Four

> [!practice] Ask whether the input set could have contained the case that fails the gate
> Before you cite a gate result, ask this question: *could the input set this gate ran over have contained the case that fails it?*
>
> The answer is no in four places. Those places are the boundary (§1), the scope (§2), the threshold (§3) and the provenance (§4). A gate exercised only on input it accepts has been demonstrated, not tested.

Keep all four places in view together. A reader who meets only the scope case does not learn to look for the threshold case. The value of the list is the enumeration.
