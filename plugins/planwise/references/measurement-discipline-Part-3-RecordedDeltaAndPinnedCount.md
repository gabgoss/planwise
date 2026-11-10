---
description: Recorded-figure discipline continued — a recorded delta states both endpoints and says whether it is net or set size, with the figure stated on both sides of any transform (§8.10), and a pinned count names the artifact and version it was read from, with the diff-gate header-line corollary (§8.11), and a byte pin names its instrument because blob bytes and checkout bytes differ by the line count under `core.autocrlf` (§8.12). Split out of measurement-discipline.md when that file crossed the Read-tool token gate.
consult-when: Writing a spec delta, a test assertion copied from a spec, or a pinned count — record both endpoints beside a "+A/-R" delta and say whether it is net or set size, state the figure on both sides of a transform, write the artifact and version beside a pinned count, and count diff lines with a filter anchored on the sign alone that removes the `---` and `+++` header lines by name; a byte count from a blob and one from the checkout differ by the line count under `core.autocrlf`, so name the instrument beside every byte pin; carries §8.10, §8.11 and §8.12 of `measurement-discipline.md`
paths: {planwise_root}/{plans_dir}/**
---

# Measurement Discipline, Part 3 — Recorded Delta and Pinned Count

**Purpose:** §8.10, §8.11 and §8.12, split out of [measurement-discipline.md](measurement-discipline.md) when that file crossed the Read-tool token gate. §8.1–§8.7 and §8.9 stay on that anchor, which keeps the original filename, and §8.8 lives in [measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md](measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md). All three sections extend §8.9 sub-rule A, which re-measures a recorded figure at execution time.

---

### 8.10 A recorded delta states both endpoints and says whether it is net or set size

A delta written "+A/−R" in prose can mean two things: the sizes of the added and removed sets, or the net change with the removals broken out. A spec that does not say which is read the convenient way by whoever writes the assertion. A transform between the measurement and the return value (rename pairing, deduplication, normalisation) makes it worse. A set-difference figure taken before pairing and a return value taken after pairing are both true. They differ by exactly the paired count. Assertions copied from such a figure can contradict each other, and a correct implementation then fails tests written against a correct spec.

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

A literal count depends on the exact artifact and version it was read from. When the artifact is regenerated, the dependency moves and the number does not. The pin in a test fails loudest and latest. The task that regenerates the artifact may not be allowed to edit the test, so a green session ends with a red tier and a round-trip to widen the write-set.

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

**Diff-gate corollary.** A line count over `git diff` output counts the `---` and `+++` header lines too, so a gate that expects 0 removed lines reads 1 on any non-empty diff. Anchor the filter on the sign alone, and remove the header lines by name. A character class written right after the sign also drops every changed line that starts with that character, such as a removed or added bullet. [`gate-predicate-discrimination.md`](gate-predicate-discrimination.md) §6 holds the general rule and its counter-example. Check 52 of `scripts/lint_gate_checks_measure.py` flags a gate that puts a character class right after the diff sign.

```bash
git diff -- <path> | grep -E '^-' | grep -vE '^---' | wc -l          # removed lines
git diff -- <path> | grep -E '^\+' | grep -vE '^\+\+\+' | wc -l      # added lines
```

Applies to test assertions that pin the row, line or entry count of a committed report, fixture or snapshot. It also applies to backlog items and design-spec rows that quote a figure from one build.

### 8.12 A byte pin names its instrument: blob bytes and checkout bytes differ under autocrlf

A byte count from a blob and a byte count from the checkout are two instruments. Under `core.autocrlf=true` a blob holds LF line endings and the checkout holds CRLF. The two counts differ by exactly the number of lines. A pin taken from one instrument and compared to the other reads as drift. The gap is large enough to look like a missing row, and it grows with the file, so it is not noise.

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

Check 53 of `scripts/lint_gate_checks_measure.py` warns on a gate that compares `git show` bytes with a checkout `wc -c` pin and adds no line count.

**A character count is a third instrument.** `awk '{print length($0)}'`, `${#var}` and `len(str)` count decoded characters, not bytes. A byte identity that takes one operand from such a counter false-fails by the extra bytes of the multi-byte characters in the text. [`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) §5 states this form.

- **Take every operand of a byte gate from a byte instrument:** `wc -c`, an `rb` read or a byte regex.
- **Run a pinned measurement command once beside a second instrument before a gate trusts it.** The two figures must agree, or the disagreement is the finding.

Applies to any byte pin, size gate, or conservation identity on a Windows checkout with `core.autocrlf=true`. It applies whenever one operand comes from `git show`, `git cat-file`, or a diff stat and another comes from the working tree.
