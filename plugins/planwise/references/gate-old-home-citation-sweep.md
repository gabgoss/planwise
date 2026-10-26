---
description: An old-home citation sweep is a substring match, not a parser — write the sibling citation before the anchor citation on a dual-citation line (§15.1), never tighten the pattern because a bounded wildcard converts a loud false positive into a silent false negative (§15.2), and gate on the delta against a recorded ledger of classified hits, never on the raw count (§15.3).
consult-when: Writing the exit criterion for a citation sweep after moving a section between files — sibling citation first on a dual-citation line (§15.1), never tighten the pattern (§15.2), gate on the delta against a classified ledger (§15.3)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Old-Home Citation Sweep (After a Reference Split)

**Purpose:** How to write the exit criterion for a sweep of citations still pointing at a section's old home, and which checker replaces the substring sweep. Split from `verification-gate-evidence.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gate-evidence.md §N` citation translates by filename alone. The family index is `verification-gate-evidence.md`.

**Read this when** you author the exit criterion for a citation sweep after moving a section between files, or such a sweep returns non-zero on a corpus you believe is correct.

## Table of Contents

- [15. An Old-Home Citation Sweep Is a Substring Match — Order the Content, Classify the Hits, Never Tighten the Pattern](#15-an-old-home-citation-sweep-is-a-substring-match--order-the-content-classify-the-hits-never-tighten-the-pattern)
  - [15.1 The dual-citation false match — write the sibling citation first](#151-the-dual-citation-false-match--write-the-sibling-citation-first)
  - [15.2 Do NOT tighten the pattern — prefer the failure you can inspect](#152-do-not-tighten-the-pattern--prefer-the-failure-you-can-inspect)
  - [15.3 A non-zero sweep is a list to classify, not a verdict](#153-a-non-zero-sweep-is-a-list-to-classify-not-a-verdict)

---

## 15. An Old-Home Citation Sweep Is a Substring Match — Order the Content, Classify the Hits, Never Tighten the Pattern

Splitting a reference along a seam and repointing every inbound citation ends with a sweep for citations still pointing at the old home. A sweep pattern of the form `{anchor}\.md.*§N` is a substring match, not a parser. It asks only whether the two strings appear in that order on one line. It cannot tell a stale citation from two correct citations that happen to share a line. So **on a correctly-repointed corpus this sweep can return non-zero, and the exit criterion must be written to expect that.**

`scripts/check_section_citations.py` replaces the substring sweep. It pairs each `§` with the nearest file named on its line and resolves the section against that file's headings in the dev tree. It exits 0 when no dangling or unresolved citation is left after the ledger (§15.3), 1 when one is left, and 2 when it could not run.

> [!constraint] Gate the sweep on the resolver and its ledger, never on "expect 0" over a substring match
> WRONG — a substring sweep gated on zero. The runner reaches zero only by rewording correct text or by tightening the pattern (§15.2), and nothing downstream detects either:
> ```
> grep -rEn '{anchor}\.md.*§({moved-range})' . --include='*.md' | wc -l   # expect 0
> ```
> CORRECT — the resolver, with the ledger of reviewed false positives:
> ```
> python -B {plugin_root}/scripts/check_section_citations.py --root {plugin_root} --ledger {ledger-file}   # expect exit 0
> ```

Three shapes stay outside the checker, so read each hit of these by hand:

- **Section-first citations** (`§{N} of {file}.md`). With no file before the `§`, the checker tries the scanned file first, so a stale citation can resolve there by accident.
- **Heading-text anchors** (a `{file}.md#{heading-text}` link with no `§`). The checker parses only `§` citations.
- **Installed-cache targets.** The checker resolves against the root it is given, which is the dev tree. A claim about the copy a consumer has installed needs a separate read of that copy.

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
> Both lines are accurate. Only the order differs, and only the second passes the sweep. `scripts/check_section_citations.py` binds each `§` to the nearest file on its line, so it resolves both orders. Where a substring sweep still gates the corpus, the order is load-bearing: record it beside the citation, because the correct form may cite a higher section number before a lower one on purpose.

### 15.2 Do NOT tighten the pattern — prefer the failure you can inspect

> [!constraint] Bounding the wildcard converts a loud false positive into a silent false negative
> Replacing `.*` with an adjacency-bounded `[^§]*` drops the dual-citation line of §15.1, and it also drops a **real stale citation** of the shape `{anchor}.md §{stayed}/§{moved}`: the bounded pattern stops at `§{stayed}` and never sees the stale `§{moved}`. **When a gate is imprecise, prefer the failure mode you can inspect.** Judge any change to a gate's pattern by *which direction it fails in*, never by the hit count it returns. `scripts/check_section_citations.py` binds a slash continuation to the same file and resolves each section, so it needs no tightened pattern.

### 15.3 A non-zero sweep is a list to classify, not a verdict

> [!practice] Gate on the delta against a recorded ledger, never on the raw count
> For each hit, read the line and ask whether every citation on it is accurate.
>
> | Every citation on the line accurate? | Disposition |
> |---|---|
> | Yes | False positive — record the line and the reason in the ledger |
> | No | Real stale citation — FAIL; repoint it |
>
> The gate is then `hits − ledgered false positives = 0`, not `hits = 0`. Pass the ledger to the checker as `--ledger {ledger-file}`: one `path:line` pair per reviewed false positive, subtracted from the failing findings before the exit code is set. An edit that moves a ledgered line re-derives its pair. Keep the ledger beside the sweep command in the sprint's verification task, because a classification nobody can find is re-derived from scratch, and a blanket-fail gate that keeps firing on known-correct lines gets softened or ignored instead of fixed ([artifact-self-containment.md](artifact-self-containment.md) §4.3).

---

*Cross-references: [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) §5-§6 (hunting `§` pointers after a renumbering, and a renumbering gate's true expected count) · [artifact-self-containment.md](artifact-self-containment.md) §4.3 (the classify-do-not-blanket-fail sweep §15.3 mirrors) · [measurement-discipline.md](measurement-discipline.md) §8.7 (the input-set assertions the sweep is paired with) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
