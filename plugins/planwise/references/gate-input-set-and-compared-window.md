---
description: A diff-pinned or sweep-based criterion records the spanned-file count and the untracked count beside its own verdict, because an empty result reads the same whether the predicate inspected the work or inspected nothing (§10.6); a verbatim-literal proof extracts from the function body only, excludes by the exact token and not a bare word, and prints the compared-set size beside the difference count (§12); a selection pattern that defines a task's scope is dry-run against known-bad input and its count is checked by an independent non-empty assertion (§14); a fixed context window around a structured entry is sized from the schema's maximum (§15); and a Verification Command's match set covers the whole population its comment or criterion names (§16). A no-output-change refactor diffs its base emit-call literals against the working tree and explains each missing one (§17). An extraction step is bounded by markers, never by a literal byte or line count, and asserts its parsed length (§18).
consult-when: A criterion is fed by a pinned diff or a sweep, a proof compares string literals, a task selects its own work with a pattern and measures success against that pattern's count, or a pull uses a fixed -B or -A window around a structured entry — record the spanned-file and untracked counts beside the verdict (§10.6), extract from the body and print the compared-set size (§12), dry-run the selection pattern and assert a non-empty input independently (§14), size the window from the schema maximum (§15); a comment or criterion names a population (N files, every row, fixtures B and C) and a Verification Command matches it — expand the pattern and compare its match set to the named population (§16); a refactor's contract is no output change — diff the emitted text and explain each missing literal (§17); an extraction cuts at a literal byte or line count — bound it by markers and assert the parsed length (§18)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Input Set and Compared Window

**Purpose:** Seven rules about what a gate or a task was permitted to look at. §10.6 covers the input set a diff or sweep criterion ran over, recorded before the edit. §12 covers the window an extractor reads and the set size it reports after. §14 covers the pattern that selects a task's own work, and §15 covers the fixed context window that pulls each selected entry. §14.1 extends §14 to a relational criterion that passes on two empty sides. §16 covers the match set a Verification Command reaches against the population its comment or criterion names. §17 covers the emitted text a no-output-change refactor must keep. §18 covers the bound of an extraction step and the parsed length it asserts. A green result over a smaller set than the criterion names is not the proof the criterion asked for. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. §17 and §18 are native to this file, so no `verification-task-authoring.md` citation maps to them. The family index is `verification-task-authoring.md`.

**Read this when** a verification report carries a criterion fed by a pinned diff or an on-disk sweep, a proof script compares string literals between two sources and reports a difference count, a task selects its own work with a pattern and checks success against the count that pattern returned, a task pulls a structured entry with a fixed `-B` or `-A` window, or a Verification Command sits beside a comment or criterion that names a population (a file list, "every row", a headline count) the command's pattern may match only in part, a refactor's contract is no output change, or an extraction step cuts its input at a literal byte or line count.

## Table of Contents

  - [10.6 A diff-pinned or sweep-based criterion records its input-set counts](#106-a-diff-pinned-or-sweep-based-criterion-records-its-input-set-counts)
- [12. A Verbatim-Literal Proof Extracts From the Body, Excludes by Exact Token, and Prints the Compared-Set Size](#12-a-verbatim-literal-proof-extracts-from-the-body-excludes-by-exact-token-and-prints-the-compared-set-size)
- [14. A Selection Pattern Is Dry-Run Before Its Count Becomes a Denominator](#14-a-selection-pattern-is-dry-run-before-its-count-becomes-a-denominator)
- [14.1 A Relational Criterion Prints Its Vacuity](#141-a-relational-criterion-prints-its-vacuity)
- [15. A Context Window Around a Structured Entry Is Sized From the Schema's Maximum](#15-a-context-window-around-a-structured-entry-is-sized-from-the-schemas-maximum)
- [16. A Verification Command's Match Set Covers the Population Its Criterion Names](#16-a-verification-commands-match-set-covers-the-population-its-criterion-names)
- [17. A No-Output-Change Refactor Gates on Emitted Text](#17-a-no-output-change-refactor-gates-on-emitted-text)
- [18. An Extraction Is Bounded by Markers and Asserts Its Parsed Length](#18-an-extraction-is-bounded-by-markers-and-asserts-its-parsed-length)

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

### Reviewer Check 104 — Self-Derived Count Compared With No Independent Non-Empty Assertion

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

### 14.1 A Relational Criterion Prints Its Vacuity

The §14 non-empty assertion has a relation form. An anchor such as `mem == db` compares two sides, and two empty sides are equal. The relation passes vacuously, and the printed line reads the same as a real match.

> [!constraint] Print the vacuity, record PASS (vacuous), and schedule a DEFERRED measurement
> **Rule.** A relational anchor printed `{} {} MATCH` because the table held 0 rows in every season. The plan's Dependencies row said "populated". The anchor never compared a single row.
>
> Four operative points:
>
> 1. **Print the vacuity.** When both sides are empty, the anchor prints `MATCH (VACUOUS: 0 rows)`, never a bare `MATCH`.
> 2. **Record the verdict as PASS (vacuous).** It is not a full PASS, because the relation was never exercised.
> 3. **Add a DEFERRED measurement.** The task schedules a re-run of the anchor on the first day the inputs are non-empty.
> 4. **Paste the measured count beside a "populated" claim.** A Dependencies row that says "populated" carries the measured `COUNT(*)` and its date.
>
> WRONG — the anchor prints one word for a real match and for two empty sides:
> ```
> print("MATCH" if mem == db else "DIFF")      # {} {} MATCH, on 0 rows
> ```
> CORRECT — the anchor prints the vacuity, and the verdict records it:
> ```
> print("MATCH (VACUOUS: 0 rows)" if not mem and not db else "MATCH" if mem == db else "DIFF")
> # verdict: PASS (vacuous)   DEFERRED: re-run on the first non-empty day
> ```

**Applies to** any criterion that asserts two sides equal, one set contains another, or a join returns no unmatched rows. Cross-reference: §14 covers the selection pattern that feeds a task's scope. This section covers the relation between two sides that may both be empty.

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

### Reviewer Check 105 — Fixed Context Window Not Sized From the Schema Maximum

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

## 16. A Verification Command's Match Set Covers the Population Its Criterion Names

A task's comment or criterion often names a population: four files, every row, fixtures B and C, nine URLs. The Verification Command beside it then matches some set. When that set is smaller than the named population, the command passes on the part it reaches and says nothing about the rest. The result reads green because the command ran, not because the population was checked.

> [!constraint] Compare the command's match set to the population the criterion names
> **Rule.** Five shapes of the same defect were reported against shipped plans:
>
> - **N-1 alternation.** A comment names four files, `alpha.md beta.md gamma.md delta.md`. The pattern lists three branches, `alpha|beta|gamma`. The command passes while `delta.md` goes unchecked.
> - **One row under an all-rows criterion.** The criterion reads "no row is left pending". The command reads one named row.
> - **"N files" over an N+6 population.** The criterion says "all 12 files carry the header". The directory holds 18 such files. The command passes on the 12 it was written for, and the six others go unchecked.
> - **A subset of a named pair.** The criterion names fixtures B and C. The command checks B only.
> - **A headline count beside a `{placeholder}` pattern.** A task states nine URLs and pins a pattern with a `{host}` placeholder. Expanded, the pattern implies 13 URLs. The stated count and the pattern disagree, and the command cannot tell which is right.
>
> Four operative points:
>
> 1. **Enumerate the named population first.** List every member the comment or criterion names, as a table with one row per member. The command is written second.
> 2. **Expand the pattern and compare.** Write out every branch of an alternation and every value a `{placeholder}` takes. The expansion MUST equal the member list, no more and no fewer.
> 3. **Derive the count from the table.** The stated count is the number of rows in the one-row-per-member table. Never write the table to fit a count that was typed first.
> 4. **Dry-run the command against a copy with one member removed.** The command MUST fail on that copy. A command that still passes cannot see the missing member.
>
> WRONG — the comment names four files and the alternation reaches three:
> ```
> # checks alpha.md beta.md gamma.md delta.md
> Grep  pattern='alpha|beta|gamma'  path='{files}'  output_mode='count'   # expect 3
> ```
> CORRECT — the table lists four members, the pattern has four branches, and the count is the row count:
> ```
> # members: alpha.md, beta.md, gamma.md, delta.md   (4 rows)
> Grep  pattern='alpha|beta|gamma|delta'  path='{files}'  output_mode='count'   # expect 4
> # dry run: copy with delta.md removed -> count 3, the gate fails
> ```
>
> The one-row shape has the same fix. A criterion that reads "no row is left pending" points its command at the whole ledger with `pattern='pending'`, never at one named row such as `row-07.*pending`.

**Applies to** any Verification Command whose comment, criterion or headline count names a population the command's own pattern, path or glob must reach. Cross-reference: [gate-denominator-integrity.md](gate-denominator-integrity.md) covers the external denominator a coverage gate takes. This section covers the narrower case where the task states the population in prose and the command reaches less.

### Reviewer Check 110 — Match Set Narrower Than the Population Its Criterion Names

- **Severity / Role / Type:** WARNING (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** A Verification Command whose match set is narrower than the population its adjacent comment or criterion names passes without checking the rest. Flag a command whose pattern, path or glob reaches fewer members than the text names.
- **Detection:** Read each task's Verification Commands beside the comment and the Success Criteria checkbox they serve.
  1. Extract the named population: a file list, "every row", "all N files", a pair such as "fixtures B and C", or a stated count.
  2. Expand the command's reach. Write out each branch of an alternation, each file a glob matches, and each value a `{placeholder}` takes.
  3. Compare the two sets. Flag the shapes below, each as one finding:
     - An alternation with fewer branches than the comment names members (N-1 alternation).
     - A command that reads one row, file or fixture under a criterion that says every, all or a named pair.
     - A criterion that states "N files" or "N rows" while the glob or path reaches a different number.
     - A headline count stated beside a `{placeholder}` pattern, where the expanded pattern implies a different count than the stated one.
  4. For a flagged command, look for a one-row-per-member table or a dry run against a copy with one member removed. A command with either is clear.
- **Finding template:**
```
[WARNING] Match set narrower than the population the criterion names
File: {task file path} | Location: {command line}
Issue: "{command}" reaches {M} of the {N} members that "{comment or criterion}" names ({missing members}), so it passes while the rest go unchecked
Fix: List the named population as one row per member, expand the pattern to cover every row, derive the count from the table, and dry-run the command against a copy with one member removed, per references/gate-input-set-and-compared-window.md §16 | Confidence: HIGH
```

## 17. A No-Output-Change Refactor Gates on Emitted Text

A refactor whose contract is "no output change" can still change what a script prints. A test suite checks behaviour, and it rarely pins the wording of a status line. Every gate can stay green while a changed print line ships.

> [!constraint] Diff the base emit-call literals against the working tree, and explain each missing literal
> **Rule.** A brief told a runner to keep the prints of a script it refactored, and gave no command for it. The refactor changed one print line to report a match count where it had reported a key count. Every gate passed. The orchestrator caught the change only by searching the base revision and the working tree by hand.
>
> Four operative points:
>
> 1. **List every base emit-call string literal that is missing from the files the refactor writes.** Take each base file with `git show <base>:<path>`. Compare the base file set with the union of the destination files in the working tree, because a module split moves literals between files. Then list the working-tree emit literals that are absent from the base. Emit calls are `print(...)` and its kin: a logger call, a `sys.stdout.write`, an `echo`.
> 2. **Explain each missing and each new literal.** A missing literal passes only when the replacement emits the same text through a renamed variable or an engine field. An engine field is a template or format string held outside the script, such as a config entry. The literal check alone cannot see a change carried by a variable or an engine field. So either pass also shows that the value is unchanged. The evidence is the assignment line or the field in base and working tree, or a captured output diff. A new literal is an output change unless the same evidence explains it. Any other missing or new literal is an output change, and the gate fails.
> 3. **The runner runs the gate and the orchestrator re-runs it.** The runner's report is one reading. The orchestrator's re-run on the final bytes is the acceptance.
> 4. **Print both compared-set sizes.** Report the number of base literals beside the missing count, and the number of working-tree literals beside the new count, as §12 point 4 requires. `0 missing` over 40 literals and `0 missing` over 0 literals print the same line otherwise.
>
> WRONG — the brief asks for the prints to stay, and no command checks them:
> ```
> Step 4: Refactor report.py. Keep the prints.
> After:  pytest tests/test_report.py     # green while one print line changed
> ```
> CORRECT — a mechanical diff of the emitted text, with both set sizes and each difference explained:
> ```
> git show <base>:scripts/report.py > <scratch>/report.base.py
> <list the emit-call literals of both sides; print both counts and both difference sets>
> # 14 base literals, 2 missing; 14 tree literals, 2 new (the two replacements below)
> # f"keys: {keys}" -> f"keys: {key_count}": renamed variable; base keys = len(index),
> #   tree key_count = len(index), so the value is unchanged: pass
> # "keys found"   -> replaced by "matches found": output change, FAIL
> ```

**Applies to** any refactor, port or module split whose brief says the output must not change. Cross-reference: §12 covers a verbatim proof between two languages. This section covers the text one script emits before and after its own refactor.

## 18. An Extraction Is Bounded by Markers and Asserts Its Parsed Length

An extraction step that cuts its input at a literal byte or line count reads whatever falls inside the cut. When the subject grows past the cut, the step returns less, and nothing reports it. A gate fed by that step can then pass more easily as the file grows.

> [!constraint] Bound the extraction by markers, assert the parsed length, and ask which way a short read moves the gate
> **Rule.** A gate proved that every column of a table definition was bound in a merge statement. It took the column list from `open(path).read()[:9000]`. The definition block ended at byte 8,528 when the gate was written. A task in the same session added five columns, and the block then ended at about 8,743. A block that crosses the cut makes the parse return fewer columns. The list of missing columns then gets shorter, and the assertion passes more readily. No error and no warning marks the change.
>
> Four operative points:
>
> 1. **Never bound an extraction step with a literal size.** A slice such as `[:N]`, a `head -n N` stage, `grep -m N` and a `Read` call with a `limit` each cut the subject at a number chosen on one day.
> 2. **Bound it by markers.** Start at the token that opens the block and end at the token that closes it. The extent then comes from the block's own structure.
> 3. **Assert the parsed length.** State the count the extraction must return, as in `assert len(ddl) == 73`. The length assertion is the line that fails when the extraction comes back short.
> 4. **Ask the fail-open question.** If this extraction silently returns less than it should, does the assertion get easier or harder to satisfy? Easier means the gate is fail-open, and it needs a completeness assertion. Harder means a short read fails loudly.
>
> WRONG — a literal byte bound, and an assertion that a short read satisfies more easily:
> ```python
> ddl = re.findall(PATTERN, open(SQL).read()[:9000], re.M)
> missing = [c for c in ddl if c not in bound]
> assert not missing
> ```
> CORRECT — marker bounds, and a parsed-length assertion beside the real check:
> ```python
> text = open(SQL).read()
> start = text.index("CREATE TABLE")
> ddl = re.findall(PATTERN, text[start:text.index(");", start)], re.M)
> assert len(ddl) == 73, f"parsed {len(ddl)} columns, expected 73"
> missing = [c for c in ddl if c not in bound]
> assert not missing
> ```

**Enforced by script:** lint Check 68 of `scripts/lint_verification_gates.py`, defined in `scripts/lint_gate_checks_verify.py`. It is static and reports a WARNING once for each command that holds a literal extraction bound and no clearing form. The flagged shapes are these:

- A slice with a literal integer stop on a read result, such as `.read()[:9000]` or `.read_text(...)[:9000]`.
- A `head` stage (`-n N`, `-nN`, `-N`, `-c N` and the long forms) or a `tail` stage with a literal count, when another stage follows it.
- `grep -m N` or `--max-count=N`.
- A native `Read` call with `limit=N` in the Verification Commands or Success Criteria section of a task file. The line after the call is read as its annotation. A paged read under Execution Steps or Required Context is an instruction and is not flagged.

A command clears when its comment or annotation holds the words `parsed length`. A `len(...)` comparison clears only the pipeline that holds the bounded stage, or the command's note. One on the other side of `&&` or `;` does not. A final `wc -l`, `wc -c`, `wc --lines` or `wc --bytes` stage also clears a bound, but only when it directly follows the bounded stage. A filter stage between the cut and the `wc` leaves the bound flagged, because the `wc` then counts the filtered output. A command with several bounds is flagged when any one bound is uncleared. The check does not flag a pipeline whose last stage is `head` or `tail`, because that stage only displays. It does not flag `tail -n +N`, which is a start offset, or a `[:N]` slice on something that is not a read result. It skips a command whose comment or annotation is labelled WRONG, and the word inside a pattern argument is not a label. It cannot see a bound held in a variable, a length asserted in a later command, or a bound that is correct by design.

**Applies to** any gate whose input comes from an extraction step: a slice, a `head -n`, a `Read` with a `limit`, an implicit `TOP`, or any "parse the first N of X" step. Cross-reference: §15 covers a fixed context window around one structured entry. This section covers the cut that decides how much of the subject an extraction reads at all.

---

*Cross-references: [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) §10.1 (the recorded pre-edit value, which this file's §10.6 complements with the recorded input set) · [measurement-discipline.md](measurement-discipline.md) §8.7 sub-rule E (the liveness proof whose output §10.6 requires to reach the report) · [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §13 (a predicate that counts names its unit) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
