---
description: A diff-pinned or sweep-based criterion records the spanned-file count and the untracked count beside its own verdict, because an empty result reads the same whether the predicate inspected the work or inspected nothing (§10.6); a verbatim-literal proof extracts from the function body only, excludes by the exact token and not a bare word, and prints the compared-set size beside the difference count (§12); a selection pattern that defines a task's scope is dry-run against known-bad input and its count is checked by an independent non-empty assertion (§14); and a fixed context window around a structured entry is sized from the schema's maximum (§15).
consult-when: A criterion is fed by a pinned diff or a sweep, a proof compares string literals, a task selects its own work with a pattern and measures success against that pattern's count, or a pull uses a fixed -B or -A window around a structured entry — record the spanned-file and untracked counts beside the verdict (§10.6), extract from the body and print the compared-set size (§12), dry-run the selection pattern and assert a non-empty input independently (§14), size the window from the schema maximum (§15)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Input Set and Compared Window

**Purpose:** Four rules about what a gate or a task was permitted to look at. §10.6 covers the input set a diff or sweep criterion ran over, recorded before the edit. §12 covers the window an extractor reads and the set size it reports after. §14 covers the pattern that selects a task's own work, and §15 covers the fixed context window that pulls each selected entry. A green result over a smaller set than the criterion names is not the proof the criterion asked for. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** a verification report carries a criterion fed by a pinned diff or an on-disk sweep, a proof script compares string literals between two sources and reports a difference count, a task selects its own work with a pattern and checks success against the count that pattern returned, or a task pulls a structured entry with a fixed `-B` or `-A` window.

## Table of Contents

  - [10.6 A diff-pinned or sweep-based criterion records its input-set counts](#106-a-diff-pinned-or-sweep-based-criterion-records-its-input-set-counts)
- [12. A Verbatim-Literal Proof Extracts From the Body, Excludes by Exact Token, and Prints the Compared-Set Size](#12-a-verbatim-literal-proof-extracts-from-the-body-excludes-by-exact-token-and-prints-the-compared-set-size)
- [14. A Selection Pattern Is Dry-Run Before Its Count Becomes a Denominator](#14-a-selection-pattern-is-dry-run-before-its-count-becomes-a-denominator)
- [15. A Context Window Around a Structured Entry Is Sized From the Schema's Maximum](#15-a-context-window-around-a-structured-entry-is-sized-from-the-schemas-maximum)

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

## 14. A Selection Pattern Is Dry-Run Before Its Count Becomes a Denominator

A task often defines its own scope with a query. It pulls every entry of one kind, then checks success against the count the query returned. The dry-run rule of [measurement-discipline.md](measurement-discipline.md) §8.7 sub-rule A, remedy 4, covers every gate. It covers every selection pattern a task's scope depends on in the same way. A selection pattern is a gate on the task's input: it decides which work exists.

> [!constraint] Dry-run the selection pattern against a known-bad input, and assert a non-empty input from outside the query
> **Rule.** A discovery plan required each pass or refute gate to be shown failing against known-bad input before first use. Five sibling tasks each selected their work with a search for `Field: value` over a schema-defined register. The schema spelled the field `**Field:** value`, with bold markers between the colon and the space. The pattern could not match. Each task pulled zero entries, wrote an empty output, and passed its own acceptance check, "designed count == pulled count", because `0 == 0`. A pulled count of zero reads the same as "no items of this kind exist". Only a later cross-count task could catch it, after five upstream tasks had already run.
>
> Three operative points:
>
> 1. **Dry-run the selection pattern as a pair.** Run it over one fixture that holds an entry in the schema's real spelling and one fixture that holds none. The two counts MUST differ. Identical counts mean the pattern cannot tell a register with work from a register without it.
> 2. **Take the non-empty assertion from outside the query.** Compare the pulled count to a second instrument: the number of entry headings in the register, or a count the schema states. The query that defines the scope cannot also certify that the scope is non-empty.
> 3. **Record the pair beside the pattern.** The task carries the two fixture counts, so a reviewer can see the pattern was shown to discriminate.
>
> **Measured pair.** `dry_run_pair.py --outputs` runs one command over a good and a bad input and reports whether the outputs differ. The fixtures:
>
> - `one.md` holds `### E-001`, then `> excerpt line 1`, then `**Field:** value`.
> - `empty.md` holds `# Register` and `No entries.`
>
> | Pattern | Command | Good output | Bad output | Result |
> |---|---|---|---|---|
> | plain `Field: value` | `dry_run_pair.py --outputs "grep -c 'Field: value' {input}" one.md empty.md` | 0 | 0 | exit 1, `IDENTICAL: the gate cannot tell good from bad` |
> | widened `Field:(\*\*)? value` | `dry_run_pair.py --outputs "grep -cE 'Field:(\*\*)? value' {input}" one.md empty.md` | 1 | 0 | exit 0, `differ` |
>
> The plain pattern fires nothing on the register that holds the entry. The widened pattern counts it.
>
> WRONG — the selection pattern is trusted, and the count checks itself:
> ```
> pull:    grep -c 'Field: value' register.md          -> 0   (the schema spells it **Field:** value)
> check:   designed count == pulled count              -> 0 == 0   PASS
> ```
> CORRECT — the pattern is dry-run as a pair, and a second instrument supplies the non-empty assertion:
> ```
> dry run: dry_run_pair.py --outputs "<pattern command> {input}" one.md empty.md   -> must exit 0 (differ)
> pull:    grep -cE 'Field:(\*\*)? value' register.md  -> 12
> check:   pulled count == count of '^### E-' headings (12), and both are greater than 0
> ```

**Applies to** any task whose scope is the result of its own query and whose acceptance check is measured against that same result. Cross-reference: [gate-predicate-discrimination.md](gate-predicate-discrimination.md) covers the dry-run pair for a pass or refute predicate. This section extends the pair to the predicate that selects the work.

#### Reviewer Check 104 — Self-Derived Count Compared With No Independent Non-Empty Assertion

- **Severity / Role / Type:** WARNING (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** A task whose success criterion compares an output count to a count the task derived itself by query MUST also assert, from an independent source, that the input set is non-empty. Flag a task that has no such assertion.
- **Detection:** Use Grep over the plan's task files for criteria of the shape "designed count == pulled count", "output count equals the number selected", or "N rows written for N entries pulled". For each hit, find where the right-hand count comes from. When a query the same task runs produced it, look for a second instrument or a stated external denominator (a heading count, a schema count) and a greater-than-zero assertion. A hit with neither → WARNING. The reported shape: five sibling tasks each searched a register for `Field: value` while the schema spelled the field `**Field:** value`, and each passed on `0 == 0`.
- **Finding template:**
```
[WARNING] Self-derived count compared with no independent non-empty assertion
File: {task file path} | Location: {criterion line}
Issue: "{criterion}" compares an output count to a count that "{query}" derived inside the same task, so a pattern that selects nothing passes on 0 == 0
Fix: Dry-run the selection pattern against a known-bad input and assert the input count against an independent source, per references/gate-input-set-and-compared-window.md §14 | Confidence: HIGH
```

## 15. A Context Window Around a Structured Entry Is Sized From the Schema's Maximum

A fixed `-B N` or `-A N` window pulls the lines around a match. It captures a structured entry only when the entry fits inside the window. A schema that permits variable-length fields makes the entry's extent vary, so a fixed N is a guess about the longest case.

> [!constraint] Derive the window from the schema's maximum, or cut by entry boundary
> **Rule.** The register's entry schema allowed a verbatim excerpt of one to three lines above the matched field. A pull used a fixed `-B 6 -A 5` window. At the top of the permitted range the window clipped the entry's own ID heading. A correct pattern then yielded entries the task could not index, because the ID that names each entry sat outside the pulled text.
>
> Three operative points:
>
> 1. **Derive N from the schema.** Count the lines from the entry's ID heading to the matched field at the schema's maximum for every variable-length field between them. Add the heading line itself. State that derivation beside the window.
> 2. **Prefer a boundary cut.** Pull from the entry's heading to the next heading, so the entry's extent comes from its own structure and not from a line count.
> 3. **Dry-run the window at the maximum.** Run it over a fixture whose variable-length field is at its maximum length. The entry's ID heading MUST appear in the pulled text.
>
> WRONG — a fixed window, with no derivation:
> ```
> grep -B 6 -A 5 'Field:' register.md    # a 3-line excerpt at the schema maximum pushes the ID heading out of the window
> ```
> CORRECT — a window derived from the schema's maximum, proven at that maximum:
> ```
> # N = lines between the ID heading and the matched field when every variable-length field is at the schema maximum (excerpt: 3 lines)
> window: -B <derived N>   fixture: excerpt of 3 lines -> pulled text starts with '### E-' (heading present)
> ```

**Applies to** any pull that captures a structured entry with a fixed number of context lines. Cross-reference: [gate-command-semantics.md](gate-command-semantics.md) §10.8 covers how `-B1` and `-A1` print the match line itself. This section covers how large the window must be.

#### Reviewer Check 105 — Fixed Context Window Not Sized From the Schema Maximum

- **Severity / Role / Type:** WARNING (MEDIUM confidence) | Verification-Gate Reviewer | NEW
- **What:** A task that pulls a structured entry with a fixed `-B N` or `-A N` window MUST derive N from the schema's own maximum for the variable-length fields inside the entry. Flag a window whose N is not derived.
- **Detection:** Use Grep over the plan's task files for `-B [0-9]`, `-A [0-9]`, `-C [0-9]` and the `context` parameter on a Grep call. For each hit, read the schema the task pulls from. When the schema permits a field of variable length between the entry's ID heading and the matched line, look for a stated derivation of N from that maximum, or a boundary cut. A hit with neither → WARNING.
- **Finding template:**
```
[WARNING] Fixed context window not sized from the schema maximum
File: {task file path} | Location: {pull command}
Issue: "{window}" pulls an entry whose schema permits a {field} of up to {max} lines, and N is not derived from that maximum, so the entry's ID heading can fall outside the window
Fix: Derive N from the schema maximum or cut by entry boundary, and dry-run the window at the maximum, per references/gate-input-set-and-compared-window.md §15 | Confidence: MEDIUM
```

---

*Cross-references: [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) §10.1 (the recorded pre-edit value, which this file's §10.6 complements with the recorded input set) · [measurement-discipline.md](measurement-discipline.md) §8.7 sub-rule E (the liveness proof whose output §10.6 requires to reach the report) · [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §13 (a predicate that counts names its unit) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
