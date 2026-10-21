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

Four green gates in one body of work had input sets that could not contain the failing case. Each hid the case in a different place. The first place is behind a boundary.

An extraction script resolved all 13 content anchors, exited 0 and reported FOUND. One anchor matched a subsection heading ten pages early. Nine pages of required material landed in no section file at all. "The anchor matched" and "the anchor matched the right thing" are different claims. An anchor-found check tests only the first.

The same hole sits in every check of this general form:

- anchor-resolution checks
- regex boundary detection
- "found N matches" assertions
- split and segmentation steps
- scope-boundary derivations

Assert a property of what the step captured. Do not assert that the step ran.

> [!constraint] Assert a property of the captured span, not that the anchor resolved
> ```python
> # WRONG — assert the anchor resolved:
> idx = find_anchor(lines, WORD_LIST_START)
> if idx is None:
>     sys.exit(f"anchor not found: {WORD_LIST_START}")
> write_section("10-dictionary-intro.txt", lines[intro_idx:idx])
> # Exits 0 and reports FOUND whether idx is the true boundary or a heading ten pages early.
> ```
>
> ```python
> # CORRECT — assert a property of what was captured:
> idx = find_anchor(lines, WORD_LIST_START)
> if idx is None:
>     sys.exit(f"anchor not found: {WORD_LIST_START}")
> section = lines[intro_idx:idx]
> write_section("10-dictionary-intro.txt", section)
>
> # Positive control: content known to belong INSIDE this section must be present.
> for probe in REQUIRED_INTERIOR_PROBES:          # e.g. "recurring error", "column 4"
>     if not any(probe in ln.lower() for ln in section):
>         sys.exit(f"boundary suspect: '{probe}' expected inside section but absent")
> # Negative control: content known to belong AFTER it must be absent.
> for probe in FORBIDDEN_PROBES:                  # e.g. a word-list entry shape
>     if any(probe_re.match(ln) for ln in section):
>         sys.exit(f"boundary suspect: word-list content leaked into section")
> ```

Three practices close the hole.

1. **Pair every boundary with an interior probe and an exterior probe.** One term must appear inside the captured span. One term must not. This turns a silent truncation into a loud failure and costs two searches. Take the probes from the consumer's contract, meaning what the downstream task was promised. Do not take them from the extractor's own assumptions.
2. **Prefer an anchor the artifact asserts about itself over an anchor that describes its typography.** "Where the document's own pagination changes series" is a fact the document states. "First short line after a blank gap" is a guess about layout, and any subsection heading can satisfy it. When only a shape heuristic is available, the probes in practice 1 are not optional.
3. **Treat a downstream "required content absent" report as an upstream-scope signal, not a content limitation.** The consuming task is the first place a silent truncation shows. It is the first party that holds the contract for what should have been there. Locate the material in the un-segmented original before you accept the gap as a property of the source.

The two-command diagnosis below settled the case without reading the body text. The first command lists the pages that contain the missing material. The second lists the span the section file captured. Two disjoint ranges are the whole proof.

```bash
# which pages contain the missing material?
awk '/^===== PAGE [0-9]+ =====/{p=$3} tolower($0) ~ /recurring error/{print "page " p}' full.txt
# what span did the section file actually capture?
awk '/^===== PAGE [0-9]+ =====/{if(!f){print "first " $3; f=1} l=$3} END{print "last " l}' section.txt
# Two disjoint ranges is the whole proof.
```

---

## 2. Locate the Gate at the Scope of the Property's Quantifier

The second place the failing case hides is outside the slice a runner was given. Three parallel runners each swept their own section files for verbatim overlap with a source. Each reported clean. One was not clean. Its content collided with an indexed copy on a page it had never been given. Each runner's denominator was a strict subset of the corpus that the property quantified over.

> [!constraint] A runner's self-check is a drafting aid, and a session-scope gate is the evidence
> ```
> WRONG — each runner self-certifies over its own slice, orchestrator aggregates the PASSes:
> runner A: sweep(inputs=A_sections)  → 0 hits → PASS ─┐
> runner B: sweep(inputs=B_sections)  → 0 hits → PASS ─┼→ "all clean"   ← unproven
> runner C: sweep(inputs=C_sections)  → 0 hits → PASS ─┘
> # Collisions against material outside each runner's own slice are undetectable by construction.
>
> CORRECT — runner self-checks are a drafting aid; a session-scope gate is the evidence:
> runner A/B/C: sweep(own inputs) → fast feedback while drafting, NOT the gate
> orchestrator/gate task: sweep(source=FULL corpus, subjects=ALL deliverables) → exit 0
> # Plus: dry-run the gate against known-bad and known-clean first, so "0 hits"
> # is known to be discrimination rather than a gate that cannot fire.
> ```

This failure is invisible from inside the runner. The runner sees a green result over an input set that looks complete. Only the party that holds the full corpus can see that the input set was a subset.

Three practices close the hole.

1. **Locate the gate at the scope of the property's quantifier.** "No deliverable shares 12 words with the source" quantifies over the whole source and all deliverables. It belongs in a session-level task that holds both. It does not belong distributed across runners that each hold a slice.
2. **Say so in the dispatch prompt, and say why.** A capable runner will otherwise shrink the corpus to its own inputs. It reasons that it cannot have copied text it never read. That reasoning is sound about copying and unsound about collision. Carry the one-line mechanism in the prompt, not only the instruction.
3. **Keep the per-task self-check.** In the originating work it caught 42, 51 and 37 first-draft collisions across three runners and saved three round trips. Keep it as fast feedback. Never let it stand in for the session gate.

`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md` §1.29.4 carries the dispatch-prompt requirement. This section owns the case where the denominator is a subset. It does not cover a property that exists only in the relationship between runners.

---

## 3. Assert the Crossing, Not the Direction

The third place the failing case hides is below the threshold. Two fixtures contained exactly the construction their metric looks for. Neither would ever have fired. Both passed a directional test (`bad > clean`) and produced no finding at any threshold the linter ships with.

| Fixture | Metric | Measured | Check limit | Fires? |
|---|---|---:|---:|:--:|
| `choppy.md` | phrasal verbs | 1.0309 /100w | 1.5 | **no** |
| `passive_heavy.md` | present perfect | 0.7874 /100w | 1.5 | **no** |

A metric with a threshold gives a test corpus two failure modes. In the first, the construction is absent. Anyone catches that. In the second, the construction is present but sub-threshold. That one is invisible, and it reads as coverage in every summary.

The sub-threshold case survives casual review. A reader asks whether the fixture contains present-perfect constructions. The reader finds two, answers yes and moves on. Two in 254 words is 0.79 per hundred against a limit of 1.5.

A discrimination table whose bad values cross their own check limits proves that each fixture would fail the gate on that metric alone. A table that shows only `bad > clean` proves the metric is monotonic and nothing else.

Two practices close the hole.

- **Score existing fixtures before you author new ones, and record the numbers.** "Use what exists, author only the gaps" is actionable only if a measurement defines the gap. Reading the fixture does not. In the originating work, scoring first avoided an unnecessary probe and caught two gaps that inspection would have missed.
- **Re-run the discrimination gate after any threshold change.** Thresholds that ship as provisional constants get re-tuned later from real distributions. Raising one can silently stop a metric from firing that a gate had proved discriminating. The evidence is valid only at the values it was measured against.

---

## 4. A Per-Item Gate Is Only as Good as the Provenance of What It Is Fed

The fourth place the failing case hides is on the failure branch that nobody exercised. A per-item gate was fed a classification computed before the operation ran. That value is a prediction that the move would succeed.

No test catches this, for one reason. **A forecast is correct exactly whenever the operation succeeds.** Every test that does not inject a failure exercises the path where prediction and observation agree. A green suite is therefore not evidence. It is the expected reading whether or not the bug is present.

> [!constraint] Feed the gate the operation's observed result, not the forecast
> ```python
> # WRONG — feed the gate the classification computed before the operation ran:
> for f in item["files"]:
>     c = _classify_file(f["path"], ...)
>     link_results.append((c["file"], True, "moved to Archive"))  # a PREDICTION
> ...
> archive_item_files(backlog_dir, archive_dir, move_basenames)     # result discarded
> update_index_links_to_archive(content, item_id, link_results)    # gate trusts the guess
> ```
>
> ```python
> # CORRECT — let the operation's actual result overwrite the prediction for everything it touched:
> for basename, success, message in archive_item_files(backlog_dir, archive_dir, move_basenames):
>     link_results[basename] = (success, message)   # OBSERVED wins over predicted
> update_index_links_to_archive(content, item_id, [...link_results...])
> ```

One detail keeps the fix correct. Entries the operation never touched keep their predicted value. That is right, because the operation was never asked about them. The overlay applies only to what the operation actually attempted.

Three practices close the hole.

1. **Enumerate the call sites before you design the gate, and ask each one the same question.** The question is whether the value is observed or predicted. A call site that computes its own version of the fact ahead of the operation is where the forecast slips in. It looks like the natural place to reuse work already done.
2. **Demand a failure-injection test as part of the fix, not as later hardening.** The discriminating test patches the operation to fail for one item while its sibling genuinely succeeds. It then asserts both the filesystem state and the recorded state. Without it, the buggy version satisfies the fix's own success criteria.
3. **Do not treat a fix that resolves the reported symptom as complete.** Fixing the instance and inheriting the class is how a defect survives its own remediation.

---

## 5. The One Question That Unifies the Four

> [!practice] Ask whether the input set could have contained the case that fails the gate
> Before you cite a gate result, ask this question: *could the input set this gate ran over have contained the case that fails it?*
>
> The answer is no in four places. Those places are the boundary (§1), the scope (§2), the threshold (§3) and the provenance (§4). A gate exercised only on input it accepts has been demonstrated, not tested.

Keep all four places in view together. A reader who meets only the scope case does not learn to look for the threshold case. The value of the list is the enumeration.
