---
description: An old-home citation sweep is a substring match, not a parser — write the sibling citation before the anchor citation on a dual-citation line (§15.1), never tighten the pattern because a bounded wildcard converts a loud false positive into a silent false negative (§15.2), gate on the delta against a recorded ledger of classified hits, never on the raw count (§15.3), and treat a line-keyed ledger as a claim about every line above its entries, re-keyed in every store that holds the pin (§15.4).
consult-when: Writing the exit criterion for a citation sweep after moving a section between files — sibling citation first on a dual-citation line (§15.1), never tighten the pattern (§15.2), gate on the delta against a classified ledger (§15.3), re-derive every line-keyed store that holds a pin after an insert, stamp the pin's measurement date, and read a stale ledger entry as a re-key signal (§15.4)
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
  - [15.4 A line-keyed ledger is a claim about every line above its entries](#154-a-line-keyed-ledger-is-a-claim-about-every-line-above-its-entries)
  - [15.5 A bare section citation means this file to the checker](#155-a-bare-section-citation-means-this-file-to-the-checker)

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
- **Installed-cache targets.** The checker resolves against the root it is given, which is the dev tree. A claim about the copy a consumer has installed needs a separate read of that copy. A bare citation is a fourth hazard, and section 15.5 covers it.

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
> The gate is then `hits − ledgered false positives = 0`, not `hits = 0`. Pass the ledger to the checker as `--ledger {ledger-file}`: one `path:line:citation` entry per reviewed false positive, where `citation` is the citation text on that line. The checker subtracts the entries from the failing findings before it sets the exit code. It still reads the older line-keyed `path:line` form, and prints a "re-key" note on stderr for each such entry. An edit that moves a ledgered line re-derives its entry (see 15.4). Keep the ledger beside the sweep command in the sprint's verification task, because a classification nobody can find is re-derived from scratch, and a blanket-fail gate that keeps firing on known-correct lines gets softened or ignored instead of fixed ([artifact-self-containment.md](artifact-self-containment.md) §4.3).

### 15.4 A line-keyed ledger is a claim about every line above its entries

A ledger entry names a file and a line number. An insert or delete above that line moves the finding, so the entry no longer matches it. The checker then fails the moved finding, because no entry covers its new line. A stale entry with no finding left exits 0 and prints only a stderr note. The same pin often sits in a second store the checker does not read, such as a test constant. The four rules below keep every store in step.

#### A plan that inserts lines re-derives every line-keyed store

A plan that inserts or deletes lines in a ledgered file re-derives every line-keyed store in its own write-set. It proves that the new store exits 0 and that the old store exits 1.

> [!constraint] Pin both exits, not only the passing one
> WRONG — the plan pins "exits 0" against the old ledger after it inserts lines above the entries:
> ```
> insert 3 lines above a ledgered line   # the finding now sits 3 lines lower
> pin: checker --ledger <old-ledger>     # expect exit 0 -> reads exit 1, no entry covers the new line
> ```
> CORRECT — inventory the stores, derive each entry as line plus inserted count, run both, and record both exits:
> ```
> new ledger (line + 3): exit 0
> old ledger:            exit 1   # proves the old keys are stale and the new ones are not
> ```

#### The inventory names every store with its result

Run the inventory Grep over every consumer of the pinned `path:line`. That covers the ledger files and the test constants. Name each store in the claim, with its own result beside it.

> [!constraint] One store read is a claim about one store
> WRONG — one store is read, and the claim is made for all of them:
> ```
> Grep <ledger file> -> re-keyed, exit 0      # claim: "the pin is re-keyed"
> ```
> CORRECT — every store is named with its result, so the claim lists what it covers:
> ```
> ledger file:    re-keyed, exit 0
> test constants: re-keyed, 0 stale
> # both stores named, each with its result
> ```

#### A pin held in two stores is re-keyed in both, in one step

When a pin moves, re-key every store that holds it in the same step, or flag the other store to its owner. Take the new line from the checker's own `dangling` row, not from a hand count. Prove the re-key on the live tree. The checker exits 0, and stderr carries no "matched no" record and no "line-keyed" note.

> [!constraint] Re-key both stores, then prove it on the live tree
> WRONG — the ledger file is re-keyed and the test constant keeps the old line:
> ```
> ledger file:   line 412 -> 415
> test constant: line 412          # still the old line, so the next run fails in the test
> ```
> CORRECT — both stores move in one step, and the live run is clean:
> ```
> line taken from the checker's dangling row: 415
> ledger file and test constant both re-keyed to 415
> checker on the live tree: exit 0, stderr empty
> ```

#### A pinned exit-0 invariant carries its measurement date

Any session that shares the tree can move a ledgered line. A pinned invariant such as "exits 0 with the ledger" therefore carries its measurement date. The plan re-runs it at Session Start. When a peer commit moved a line, the repair is a successor ledger derived from the live run. Never hand-edit the output of a session that closed COMPLETE.

> [!constraint] Date the invariant, re-run it, and repair forward
> WRONG — the invariant is trusted from the plan, a peer moved a line, and the repair edits a closed session's output:
> ```
> plan: "the checker exits 0 with the ledger"      # no date
> peer commit inserts 2 lines in a ledgered file
> repair: hand-edit the COMPLETE session's ledger
> ```
> CORRECT — the invariant is dated, re-run at Session Start, and repaired by a new ledger:
> ```
> plan: "the checker exits 0 with the ledger (measured <date>, tree at <sha>)"
> Session Start: re-run -> exit 1
> repair: successor ledger derived from the live run, old ledger left as written
> ```

Prefer a content key where the store allows one. A test constant keyed by a content snippet does not drift when lines move. The ledger file accepts only the line-keyed forms today.

### 15.5 A bare section citation means this file to the checker

> [!pitfall] A bare section citation means this file to the checker
> A `§` with no file named on its line resolves against the file the line sits in, whatever
> the surrounding prose says. When that file lacks the section, the checker reports the
> citation `dangling`. When that file holds a section with the same number, the checker
> reports `ok` against the wrong section, and nothing flags it. A pointer or compress
> rewrite writes many cross-file citations at once, because it moves claims into a sibling
> file, so each one is a candidate for this failure. Name the file next to every
> cross-file section citation.
>
> WRONG — the reader infers the file from context, and the checker binds the section to
> the file being scanned:
> ```
> - **Detection:** read the Retention figure against the bands of §3.1.
> ```
> CORRECT — the file is named next to the section:
> ```
> - **Detection:** read the Retention figure against the bands of [ei-fidelity.md](ei-fidelity.md) §3.1.
> ```
> Run the checker after every rewrite that adds a pointer, before reporting the task done.
> Put this rule in the brief of any task that rewrites text into pointers.

---

*Cross-references: [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) §5-§6 (hunting `§` pointers after a renumbering, and a renumbering gate's true expected count) · [artifact-self-containment.md](artifact-self-containment.md) §4.3 (the classify-do-not-blanket-fail sweep §15.3 mirrors) · [measurement-discipline.md](measurement-discipline.md) §8.7 (the input-set assertions the sweep is paired with) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
