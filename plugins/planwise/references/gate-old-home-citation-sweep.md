---
description: An old-home citation sweep is a substring match, not a parser — write the sibling citation before the anchor citation on a dual-citation line (§15.1), never tighten the pattern because a bounded wildcard converts a loud false positive into a silent false negative (§15.2), and gate on the delta against a recorded ledger of classified hits, never on the raw count (§15.3).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Old-Home Citation Sweep (After a Reference Split)

**Purpose:** Splitting an oversized reference along a seam and repointing every inbound citation ends with a sweep for citations still pointing at the old home. The sweep can return non-zero on a correctly repointed corpus, and the exit criterion must be written to expect that. Split from `verification-gate-evidence.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gate-evidence.md §N` citation translates by filename alone. The family index is `verification-gate-evidence.md`.

**Read this when** you author the exit criterion for a citation sweep after moving a section between files, or such a sweep returns non-zero on a corpus you believe is correct.

## Table of Contents

- [15. An Old-Home Citation Sweep Is a Substring Match — Order the Content, Classify the Hits, Never Tighten the Pattern](#15-an-old-home-citation-sweep-is-a-substring-match--order-the-content-classify-the-hits-never-tighten-the-pattern)
  - [15.1 The dual-citation false match — write the sibling citation first](#151-the-dual-citation-false-match--write-the-sibling-citation-first)
  - [15.2 Do NOT tighten the pattern — prefer the failure you can inspect](#152-do-not-tighten-the-pattern--prefer-the-failure-you-can-inspect)
  - [15.3 A non-zero sweep is a list to classify, not a verdict](#153-a-non-zero-sweep-is-a-list-to-classify-not-a-verdict)

---

## 15. An Old-Home Citation Sweep Is a Substring Match — Order the Content, Classify the Hits, Never Tighten the Pattern

Splitting an oversized reference along a seam, keeping the anchor's filename, and repointing every inbound citation ends with a sweep for citations still pointing at the old home:

```
grep -rEn '{anchor}\.md.*§({moved-range})' . --include='*.md' | wc -l   # expect 0
```

That pattern is a substring match, not a parser. `{anchor}\.md.*§N` asks only whether the two strings appear in that order on one line. It cannot tell a stale citation from two correct citations that happen to share a line. So **on a correctly-repointed corpus this sweep can return non-zero, and the exit criterion must be written to expect that.** A criterion reading "expect 0" hands the runner three options, and two of them are wrong in ways nothing downstream detects: reword the corpus until the count reaches zero (corrupts the artifact and destroys the gate's signal); tighten the pattern so it cannot span (§15.2 — converts a false positive into a false negative); or order the content so the sibling citation precedes the anchor citation (§15.1 — correct, and it encodes an invariant nothing local explains).

### 15.1 The dual-citation false match — write the sibling citation first

> [!pitfall] A line citing both halves of a former anchor false-matches whenever the anchor's filename precedes the moved section number
> The false-match case is a single line citing **two** files that were once one anchor: one section that stayed, one that moved.
> ```
> WRONG — anchor filename first; §{moved} appears later on the line ⇒ MATCH (false):
>   `{anchor}.md` §{stayed} / `{sibling}.md` §{moved}
>
> CORRECT — sibling citation first; the anchor filename is followed only by §{stayed}:
>   `{sibling}.md` §{moved} / `{anchor}.md` §{stayed}
> ```
> Both lines are accurate. Only the order differs, and only the second passes the sweep. The remedy makes reading order load-bearing, so record it where the next writer of that file will see it — a one-line note beside the citation, or in the file's authoring conventions. The correct form may cite a higher section number before a lower one. That is deliberate, not a typo to fix.

### 15.2 Do NOT tighten the pattern — prefer the failure you can inspect

> [!constraint] Bounding the wildcard converts a loud false positive into a silent false negative
> Replacing `.*` with an adjacency-bounded `[^§]*` looks like the clean fix. Measured over one authoring corpus — every `.md` file in a project tree, re-measured 2026-09-08 — for two anchors whose sections had moved:
>
> | Sweep | `.*` (correct) | `[^§]*` (tightened) |
> |-------|----------------|---------------------|
> | `{anchor-A}.md` §{moved range A} | 334 | **276** |
> | `{anchor-B}.md` §{moved range B} | 405 | **300** |
>
> The hits the bounded form stops matching mix two shapes the pattern cannot tell apart. One is the dual-citation line of §15.1, which the sweep should indeed stop flagging. The other is a **real stale citation** — one file, two sections, only the second of which moved:
> ```
> `{anchor}.md` §{stayed}/§{moved}
> ```
> The bounded pattern stops at `§{stayed}` and never sees the stale `§{moved}`. The tightening trades a false positive a human reads and classifies for a leak that ships behind a green gate — the strictly worse trade for a leak gate, and a reader who reaches for it is making the failure worse while believing they fixed it.
>
> **When a gate is imprecise, prefer the failure mode you can inspect.** Evaluate any loosening or tightening of a gate's pattern on *which direction it fails in*, never on the hit count it returns.

### 15.3 A non-zero sweep is a list to classify, not a verdict

> [!practice] Gate on the delta against a recorded ledger, never on the raw count
> For each hit, read the line and ask whether every citation on it is accurate.
>
> | Every citation on the line accurate? | Disposition |
> |---|---|
> | Yes | False positive — record the line and the reason in the ledger |
> | No | Real stale citation — FAIL; repoint it |
>
> The gate is then `hits − ledgered false positives = 0`, not `hits = 0`. The ledger lives where the next audit reads it — beside the sweep command in the sprint's verification task, or in the file's authoring conventions — because a classification nobody can find is re-derived from scratch, and a blanket-fail gate that keeps firing on known-correct lines gets softened or ignored instead of fixed. This is the discipline the on-disk identifier sweeps already use for the plugin's own scaffold vocabulary: surface candidates, classify each one, gate on what survives classification ([artifact-self-containment.md](artifact-self-containment.md) §4.3).

The three rules assume the sweep inspected what you think it did. Pair them with the input-set assertions — register untracked files, assert zero untracked remain, assert the diff covered the expected file count — from [measurement-discipline.md](measurement-discipline.md) §8.7. Together they are what make an empty *or* non-empty sweep interpretable.

---

*Cross-references: [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) §5-§6 (hunting `§` pointers after a renumbering, and a renumbering gate's true expected count) · [artifact-self-containment.md](artifact-self-containment.md) §4.3 (the classify-do-not-blanket-fail sweep §15.3 mirrors) · [measurement-discipline.md](measurement-discipline.md) §8.7 (the input-set assertions the sweep is paired with) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
