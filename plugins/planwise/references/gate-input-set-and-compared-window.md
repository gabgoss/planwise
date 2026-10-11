---
description: A diff-pinned or sweep-based criterion records the spanned-file count and the untracked count beside its own verdict, because an empty result reads the same whether the predicate inspected the work or inspected nothing (§10.6); and a verbatim-literal proof extracts from the function body only, excludes by the exact token and not a bare word, and prints the compared-set size beside the difference count (§12).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Input Set and Compared Window

**Purpose:** Two rules about what a gate was permitted to look at. §10.6 covers the input set a diff or sweep criterion ran over, recorded before the edit. §12 covers the window an extractor reads and the set size it reports after. A green result over a smaller set than the criterion names is not the proof the criterion asked for. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** a verification report carries a criterion fed by a pinned diff or an on-disk sweep, or a proof script compares string literals between two sources and reports a difference count.

## Table of Contents

  - [10.6 A diff-pinned or sweep-based criterion records its input-set counts](#106-a-diff-pinned-or-sweep-based-criterion-records-its-input-set-counts)
- [12. A Verbatim-Literal Proof Extracts From the Body, Excludes by Exact Token, and Prints the Compared-Set Size](#12-a-verbatim-literal-proof-extracts-from-the-body-excludes-by-exact-token-and-prints-the-compared-set-size)

---

### 10.6 A diff-pinned or sweep-based criterion records its input-set counts

`gate-pre-edit-baseline.md` §10.1 requires the report to record the *value* a gate measured. This section requires it to record what the gate was permitted to look at. The two are independent: a criterion can carry a correct, properly contradicting pre-edit value and still have run over an input set that excluded the work entirely — and its output is byte-identical either way, because an empty result renders "I checked and found nothing" and "I checked nothing" the same.

The report is where that distinction has to be preserved, because it is the only artifact that outlives the tree state the counts were taken from.

> [!verify] Record the spanned-file count and the untracked count beside the criterion's own result
> Any verification report carrying a criterion whose input comes from a pinned diff or an on-disk sweep MUST record both counts adjacent to that criterion's verdict — not in a preamble, and not once for the report as a whole:
> ```bash
> git -C <repo> diff --name-only $BASE -- <scope> | wc -l    # files the pinned diff actually spanned
> git -C <repo> status --porcelain <scope> | grep -c '^??'   # untracked within scope — MUST be 0
> ```
> A criterion reported PASS on a spanned count of 0, or alongside a non-zero untracked count, is not a PASS — the predicate never met the content it exists to inspect. Return FAIL or `[UNCERTAIN]` per `gate-verdict-contract-and-adjudication.md` §5, showing both counts.

The commands are the liveness proof at [measurement-discipline.md](measurement-discipline.md) §8.7 sub-rule E; this section is the separate requirement that their output reach the report rather than stopping at the runner who ran them.

## 12. A Verbatim-Literal Proof Extracts From the Body, Excludes by Exact Token, and Prints the Compared-Set Size

A literal extractor measures whatever text it is pointed at. Pointed at a file, it measures the file: doc comments, signatures and the function body together. A criterion about the body alone needs an extraction window that is the body alone. A green result over a smaller or wider set than the criterion names is not the proof the criterion asked for.

> [!constraint] Scope the window to the body, exclude by the exact token, and print the set size beside the difference count
> **Rule.** A task ported five texts from one language into string literals of another and had to prove them verbatim. The checker read both source files, pulled every quoted literal out of each function by regex, normalised the `%s` and `${...}` placeholders to one sentinel, and compared the two sets. The first runs reported spurious "extra" entries on the target side from three mechanisms:
>
> - Doc comments above the function quoted the source text in inline code.
> - A parameter default literal in the signature added its own literal.
> - A nested-brace interpolation stopped the normaliser's `\$\{[^}]*\}` at the first `}`, which left the interpolation's tail as literal text.
>
> A fourth defect shrank the set without any warning. An exclusion filter keyed on the bare word `recording` also matched a genuine ported line. A real comparison silently dropped out, and the check stayed green over 13 lines instead of 14.
>
> Four operative points:
>
> 1. **Extract from the body.** Start the window at the token that opens the body (`=> {` or `{`) and end it at the closing brace. Doc comments and parameter lists then sit outside the window by construction.
> 2. **Fix the source under test when the checker's grammar is the limit.** Hoist every non-trivial interpolation into a named local, so every `${...}` inside a template literal holds a bare identifier. A simple regex then holds without a brace-balancing parser, and the source reads better.
> 3. **Exclude by the exact token that makes the excluded line unique.** Key the filter on `${recording}` (the interpolation), not on `recording` (the word). A filter that over-matches shrinks the compared set silently.
> 4. **Report the compared-set size beside the difference count.** `0 differences` over 14 lines and `0 differences` over 13 lines print the same. The set size is the number that exposes a dropped line.
>
> WRONG — whole-file scan, bare-word exclusion, difference count only:
> ```python
> literals = re.findall(r"`([^`]*)`", target_source)          # collects doc comments and defaults too
> literals = [s for s in literals if "recording" not in s]    # also drops a real line
> print(f"{len(source_set ^ target_set)} differences")
> ```
> CORRECT — body-scoped scan, exact-token exclusion, both counts:
> ```python
> body = target_source[target_source.index("=> {", function_start):]   # from the body opener onward
> literals = re.findall(r"`([^`]*)`", body)
> literals = [s for s in literals if "${recording}" not in s]
> print(f"{len(source_set ^ target_set)} differences over {len(source_set)} lines")
> ```

**Authoring rule for the criterion.** A task criterion of the form "the ported text is verbatim" pins two things. The proof prints the compared-set size, and the task states the expected size. A reviewer of a green verbatim proof asks two questions: how many lines it compared, and where the extraction window opened.

**Applies to** a runner-side proof script that compares string literals between two source languages, between a spec and its implementation, or between a template and its rendered output.

**Split from §10.6.** §10.6 above ("A diff-pinned or sweep-based criterion records its input-set counts") covers a count recorded before an edit. This section covers the window an extractor reads and the size it reports after.

---

*Cross-references: [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) §10.1 (the recorded pre-edit value, which this file's §10.6 complements with the recorded input set) · [measurement-discipline.md](measurement-discipline.md) §8.7 sub-rule E (the liveness proof whose output §10.6 requires to reach the report) · [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §13 (a predicate that counts names its unit) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
