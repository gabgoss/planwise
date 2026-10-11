---
description: Recorded-figure discipline continued — a recorded delta states both endpoints and says whether it is net or set size, with the figure stated on both sides of any transform (§8.10), and a pinned count names the artifact and version it was read from, with the diff-gate header-line corollary (§8.11), and a byte pin names its instrument because blob bytes and checkout bytes differ by the line count under `core.autocrlf` (§8.12). Split out of measurement-discipline.md when that file crossed the Read-tool token gate.
paths: {planwise_root}/{plans_dir}/**
---

# Measurement Discipline, Part 3 — Recorded Delta and Pinned Count

**Purpose:** §8.10, §8.11 and §8.12, split out of [measurement-discipline.md](measurement-discipline.md) when that file crossed the Read-tool token gate. §8.1–§8.7 and §8.9 stay on that anchor, which keeps the original filename, and §8.8 lives in [measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md](measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md). Both subsections extend §8.9 sub-rule A, which re-measures a recorded figure at execution time.

---

### 8.10 A recorded delta states both endpoints and says whether it is net or set size

A delta written "+A/−R" in prose can mean two things: the sizes of the added and removed sets, or the net change with the removals broken out. A spec that does not say which is read the convenient way by whoever writes the assertion. A transform between the measurement and the return value (rename pairing, deduplication, normalisation) makes it worse. A set-difference figure taken before pairing and a return value taken after pairing are both true. They differ by exactly the paired count.

A spec's facts table recorded a pinned pair of files as "exports +71/−4, event keys +12/−1". A downstream brief consumed the row as test assertions:

```python
len(exports_added) == 71
events_added == {the twelve names}      # includes '<key-b>'
events_removed == []                    # after rename pairing
events_renamed_suspected == [{'removed': '<key-a>', 'added': '<key-b>', ...}]
```

The producing task measured the pair with the calibrated regexes: exports 192 -> 263, with 75 added and 4 removed. The spec's 71 was `263 - 192`, a net figure. For events the raw counts were +12/−1, but the rename rule the same spec mandates moves `<key-a>` -> `<key-b>` out of both sets. The diff function returns eleven added, zero removed and one renamed. The brief's three event assertions contradicted each other. "The twelve names" includes `<key-b>`, and "`events_removed` empty after pairing" holds only if `<key-b>` was paired out of `events_added`. A correct implementation would have failed two tests written against a correct spec.

> [!constraint] The spec states which quantity the figure is, and the assertion names the quantity the function returns
> WRONG — lift the figure into the assertion that reads most naturally:
> ```
> spec:  "exports +71/-4"           ->  test:  assert len(exports_added) == 71
> spec:  "events +12/-1, one rename" -> test:  assert set(events_added) == {twelve}
>                                              assert events_removed == []     # contradicts the line above
> ```
> CORRECT — endpoints beside the delta, and the figure on both sides of the transform:
> ```
> spec:  "exports: 192 -> 263 (net +71); removed = {4 names}; added-set size 75"
>        "events: raw +12/-1; after pairing: 11 added, 0 removed, 1 renamed (<key-a> -> <key-b>)"
> test:  assert exports_removed == {four names}
>        assert len(exports_added) == 75 and len(exports_added) - len(exports_removed) == 71   # 71 is the net figure; the docstring says so
>        assert set(events_added) == {eleven}                                                 # <key-b> sits in renamed_suspected
>        assert events_removed == []
>        assert renamed == [{'removed': '<key-a>', 'added': '<key-b>'}]
> ```

- **Record the two endpoint counts beside a delta** (`192 -> 263`). A reader can then tell net from set size by subtraction. A bare "+71/−4" cannot be disambiguated after the fact.
- **State the figure on both sides of a transform, or name which side it quotes.** A test asserts the returned side.
- **Reconcile before dispatching a task whose assertions are literals copied from a spec.** Have the producing task measure the same quantity. Route the measured value as a spec delta. Do not let the runner change the test to whatever passes.

Applies to any task brief whose success criterion is a literal count or list copied from a spec, a finding document or an addendum table, especially a `+N/−M` shape. It also applies to diff tooling with rename or move detection.

### 8.11 A pinned count names the artifact and version it was read from

A literal count depends on the exact artifact and version it was read from. When the artifact is regenerated, the dependency moves and the number does not. One session met four stale counts, each true when written:

| Pin | Written against | Observed | Where it failed |
|-----|-----------------|----------|-----------------|
| `assert len(parsed["rows"]) == 124` | the committed candidates file for one version pair | 110 after regeneration | a test outside the regenerating task's write-set |
| "34 unnamed tool blocks" | an earlier build | 53 on the later build | a backlog item's acceptance box |
| "four `new Set(` subset sites, 11 / 5 / 21 / 9" | one build | seven sites, 1 / 2 / 4 / 5 / 6 / 9 / 21 on three later builds | a design spec |
| `git diff … \| grep -c '^-'  # expect 0` | a diff with no header in mind | 1 on any non-empty diff (the `--- a/` line) | a pinned verification gate |

None of the four was a defect in the code under test. The test pin failed loudest and latest. The task that regenerated the report could not edit the test, so a green session ended with a red tier and an orchestrator round-trip to expand the write-set.

> [!constraint] Write the dependency beside the number
> WRONG — the number alone:
> ```python
> assert len(parsed["rows"]) == 124
> ```
> CORRECT — the number with its dependency, so a regeneration reads as a re-pin trigger and not a regression:
> ```python
> # pinned to the committed reports/<old>__<new>-candidates.md;
> # re-pin whenever that file is regenerated
> assert len(parsed["rows"]) == 110
> ```
> BETTER where the test's purpose allows — assert the property, not the count:
> ```python
> assert {"key", "consumer", "change"} <= parsed["rows"][0].keys()
> assert parsed["old"] == "<old>" and parsed["new"] == "<new>"
> ```

- **Write the artifact and version beside every pinned count.** A reviewer who sees `== 124` cannot tell what it measures. One who sees the comment can re-derive it in one command. This extends sub-rule A of §8.9, which re-measures a recorded figure at execution time.
- **Treat every pin against a regenerated artifact as untrusted until re-read.** `Grep` the tests and briefs for the artifact's path before dispatch. Put the re-pin in the regenerating task's write-set. Otherwise the tier goes red in a file the runner is forbidden to touch.
- **Write a count from a version-dependent source as "N on version V", never as N.** This holds in a backlog item or a spec. The build changes under the item. The item does not.

**Diff-gate corollary.** A `grep -c` over `git diff` output counts the header lines too. Count removed lines with `grep -c '^-[^-]'` and added lines with `grep -c '^+[^+]'`, so the `---` and `+++` header lines do not register.

Applies to test assertions that pin the row, line or entry count of a committed report, fixture or snapshot. It also applies to backlog items and design-spec rows that quote a figure from one build.

### 8.12 A byte pin names its instrument: blob bytes and checkout bytes differ under autocrlf

A byte count from a blob and a byte count from the checkout are two instruments. Under `core.autocrlf=true` a blob holds LF line endings and the checkout holds CRLF. The two counts differ by exactly the number of lines. A pin taken from one instrument and compared to the other reads as drift. The figure has the size of the line count. That is large enough to look like a missing row. It grows with the file, so it is not noise.

> [!constraint] Use the same instrument on both sides, or carry the line count across
> WRONG — blob bytes compared to a working-tree pin:
> ```
> git show <sha>:<path> | wc -c     # 258072
> baseline pin (wc -c on checkout)  # 258364
> # "292 bytes missing" — no row is missing
> ```
> CORRECT — same instrument on both sides, or the line count carried across:
> ```
> git show <sha>:<path> | wc -c     # 258072  (LF blob)
> git show <sha>:<path> | wc -l     # 292
> 258072 + 292 = 258364             # equals the checkout pin
> ```

- **Pin working-tree bytes with `wc -c` when the subject is the checkout, and say so.** A conservation identity runs against files on disk, so every term comes from disk.
- **Add the line count when a term must come from git history.** Run `git show <sha>:<path> | wc -l` and add it before comparing to a working-tree pin. Or compare blob to blob.
- **Treat a gap that equals the line count as the signature of this trap.** Check `git config core.autocrlf` before looking for a lost row.

Applies to any byte pin, size gate, or conservation identity on a Windows checkout with `core.autocrlf=true`. It applies whenever one operand comes from `git show`, `git cat-file`, or a diff stat and another comes from the working tree.
