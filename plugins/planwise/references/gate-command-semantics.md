---
description: Four command semantics that make a well-formed gate mean something else — `grep -c` counts lines not matches, `-B1`/`-A1` emit the match line too, set membership is not count equality, and a path resolves from the cwd the anchor's own table declares (§10.8); and four more mismatches between mechanism and claim — a context window cannot see outside itself, a cardinal pattern against an ordinal threshold, a numeric literal without digit boundaries, the regex dialect, and a fixed-size window that must fit its subject (§10.9).
consult-when: Pinning any `grep`, `diff`, `wc` or `awk` gate — `grep -c` counts lines, context flags emit the match, set membership is not count equality, a path resolves from the declared cwd (§10.8); pattern unit versus threshold unit, digit boundaries, regex dialect, a window that must fit its subject (§10.9)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Command Semantics (Read the Command as a Program)

**Purpose:** These gates are not vacuous and not narrow. They are well-formed commands that do not measure what their author read them as measuring, and a pre-edit annotation does not catch them because the annotation records the same misread value. State in one sentence what the command physically inspects, then compare that to what the criterion claims. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you pin any `grep`, `diff`, `wc` or `awk` gate, you review a Signoff anchor table, or a gate returns a value that is plausible but wrong on work you know is correct.

## Table of Contents

  - [10.8 Four command semantics that make a well-formed gate mean something else](#108-four-command-semantics-that-make-a-well-formed-gate-mean-something-else)
  - [10.9 Read the command as a program — four more mismatches between mechanism and claim](#109-read-the-command-as-a-program--four-more-mismatches-between-mechanism-and-claim)

---

### 10.8 Four command semantics that make a well-formed gate mean something else

The gates in this family are not vacuous and not narrow. They are well-formed commands that do not measure what their author read them as measuring. A pre-edit annotation does not catch them, because the annotation records the same misread value.

Check all four before a gate ships:

| # | Trap | What the author assumed | What the command does |
|---|------|-------------------------|-----------------------|
| 1 | `grep -c` counts matches | One count per occurrence | Counts matching **lines**. Use `grep -o … \| wc -l` when occurrences are the subject. |
| 2 | `-B1` / `-A1` / `-C1` emit context only | The output holds only surrounding lines | The output holds the match line **as well**, so a count over it includes every match. |
| 3 | Set membership hardened into count equality | `expected ⊆ actual` and `count(actual) == count(expected)` agree | They disagree on every correct superset. Assert the membership the criterion actually claims, one member per assertion, per `gate-heuristic-verifier-patterns.md` §2. |
| 4 | A path resolves from wherever the runner stands | The anchor runs from the plan folder, or the repo root | It runs from the cwd the anchor's **own table header** declares. A plan-relative path under a repo-root header fails unconditionally, and the criterion FAILs work that passed. |

> [!constraint] Resolve every path in an anchor against the cwd its own table declares
> WRONG — the table header declares the plugin repo as cwd, and the row runs a path relative to the session folder. It cannot resolve, so the anchor fails on every execution:
> ```markdown
> Run all anchors from `{repo}/`.
> | 2 | {criterion} | `test -f Outputs/{Report}.md` | PASS / FAIL |
> ```
> CORRECT — the path is written from the declared cwd, or the header carries a stated exception for the row:
> ```markdown
> | 2 | {criterion} | `test -f {plan_path}/{Session}/Outputs/{Report}.md` | PASS / FAIL |
> ```
> Trap 4 is the cheapest of the four to catch and the easiest to miss, because the anchor reads correctly in the task file it was drafted beside.

Traps 1 and 2 are enforced by `scripts/lint_verification_gates.py`: Check 3 (`_check3_bre_ere_and_line_count_absorption`) flags a `grep -c` count measured as occurrences, and Check 14 (`_check14_context_window_counted`) flags a `-B`/`-A`/`-C` window piped into a count. Trap 4 is enforced by `scripts/lint_gate_checks_plan.py` Check 27, which flags a Signoff anchor path that does not resolve from the declared cwd. Trap 3 has no linter coverage — run it by hand at scaffold close.

### 10.9 Read the command as a program — four more mismatches between mechanism and claim

Three standing checks interrogate a gate's **inputs and expected value**: re-measure the reading, re-derive an inherited threshold, and dry-run against known-bad input. None of them reads the command as a program and asks what it can physically see. A threshold error is detectable by comparison. A mechanism error is detectable only by reading the command.

**State in one sentence what the command physically inspects, then compare that to what the criterion claims.** Where the two differ, the gate is measuring a proxy.

| Mechanism | What it silently cannot see | Consequence |
|---|---|---|
| `grep -B{n}` / `-A{n}` context windows | anything outside the window, and the match line's own content | a correctly-formatted site reads as malformed; a subject larger than the window is only partly compared |
| any pipeline whose filter targets a *neighbouring* line | same-line variants of the thing being filtered | a semantically-null reflow flips the result |
| a dry-run "clean" control | the pattern under test, if the control happens to contain it | the pair stops discriminating **while appearing to run** |
| exact-count assertions (`= N`) | every legitimate additional mention | forbids correct work |

The worked instance for row 2: an AUTO-MODE coverage gate built as `grep -B1 "AskUserQuestion" \| grep -v "AUTO-MODE:"` can only see a tag written on its own line *above* the call. This correctly-tagged same-line bullet counts as untagged:

```markdown
- interactive confirm (`AskUserQuestion`, `<!-- AUTO-MODE: critical -->`), **AND**
```

Reflowing that tag onto its own line — a change with zero semantic content — moves the baseline 33 → 34 and fails a gate-defining exit criterion. Two corollaries: **a formatting change is not automatically gate-neutral**, so record the coupling at the code site when a gate reads line adjacency; and **verify a control before trusting the test it anchors**, because a discrimination proof establishes nothing if both arms match.

> [!constraint] Pattern unit and threshold unit MUST match
> A cardinal command compared against an ordinal threshold is unreachable on any correct post-state. Keep one unit throughout and state the before value, or assert existence when the point is existence rather than cardinality:
> ```
>   grep -c '^## 1[0-9]\.' file.md   # ≥ 13     ← unreachable: returns 3 today, 4 after correct work
>   grep -c '^## [0-9]' file.md      # 12 before → 13 after
>   grep -n '^## 13\.' file.md       # exactly 1 hit
> ```
> **The screen:** for every `grep -c … # N` gate, ask what unit `N` is. If `N` is a section number, a row number, a version, or any other ordinal, the gate is suspect — `grep -c` cannot return an ordinal. Either widen the pattern to count the whole set, or change the assertion from a count to a presence check.
>
> **State the before value too.** `12 → 13` is checkable in a way a bare `≥ 13` is not, because a reader can run it today and confirm the 12. `gate-heuristic-verifier-patterns.md` §2 and trap 3 of §10.8 own the neighbouring rule — assert membership per unit rather than hardening it into count equality.

> [!constraint] A grep for a numeric literal must anchor its digit boundaries
> Write the explicit `[^0-9]` guard, as in `(^|[^0-9])40000([^0-9]|$)`. `\b` is not a sufficient substitute, because a digit is a word character. `scripts/lint_verification_gates.py` Check 13 (`_check13_bare_numeric_literal`) flags a pattern made only of digits.
>
> Two corollaries. **A count is part of the gate's output, not scaffolding around it** — reporting "8 hits, here is what each one is" makes the count a claim, so anchor it before making it. And **direction coverage does not test pattern precision**: this defect dry-runs cleanly in all three directions (known-bad fires, clean baseline empty, correct post-state silent), because every direction shares the same imprecise pattern.

> [!constraint] A gate specification includes its regex dialect
> **Two rules:** write `grep -E` explicitly whenever the pattern contains alternation, escaping, or grouping; and for every gate containing `\|`, `\(`, `\{` or `\+`, confirm the intended dialect — with no `-E`, those escapes are operators, not literals. Under `-E` the polarity flips, and the pipe must be escaped to be literal.
>
> **The detection note:** a vacuous match returns a *large* number, which is exactly the shape a `≥ N` threshold silently accepts. `scripts/lint_verification_gates.py` Check 3 (`_check3_bre_ere_and_line_count_absorption`) flags the `grep` form, and Check 8 (`_check8_grep_tool_escaped_pipe_alternation`) flags a native `Grep` call that writes alternation as a backslash-pipe.

> [!constraint] A fixed-size window is a measurement instrument — the subject must fit inside it
> ```bash
> # WRONG — a guessed window smaller than the subject; compares 13 lines of a 14-line block:
> diff <(grep -A 12 'artifact classes this plan will touch' handlers/plan-Part-2-GatherAndGenerate.md) \
>      <(grep -A 12 'artifact classes this plan will touch' handlers/plan-scaffolding.md)   # EMPTY
>
> # CORRECT — compare the complete added-line sets, which have no window at all:
> diff <(git diff FILE_A | grep '^+' | grep -v '^+++') \
>      <(git diff FILE_B | grep '^+' | grep -v '^+++')     # exit 0
> ```
> A window that under-covers turns *"are these two blocks identical?"* into *"are their first N lines identical?"* — a different and weaker question.
>
> **The exact-count half:** a `grep -c … = N` gate silently forbids every legitimate additional mention of its pattern. `= 1` on a heading phrase cannot distinguish "the heading exists once" from "no other line in this file may mention this phrase", and the second is almost never what the author meant. Prefer `≥ 1` plus a placement assertion — `grep -n`, with the line numbers compared against known anchors.

> [!practice] When a gate needs N separately-owned repairs to become reachable, every site must say the others exist
> Otherwise a partial landing presents as a failed implementation rather than an incomplete repair, and the runner debugs its own correct work.
>
> The positive instance that motivates it: a gate proven at plan review to return **3 against 1 on a correct implementation** would have halted five tasks on good work. It reached its intended end state only because two independent repairs, owned by two different tasks, both landed.

---

*Cross-references: [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §2 (per-unit assertions, the remedy trap 3 points at) · [gate-anchor-outcome-set.md](gate-anchor-outcome-set.md) §10.7 (set agreement is not count equality) · [gate-pinned-from-real-content.md](gate-pinned-from-real-content.md) (the step these rules assume: the gate was run over the real content) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) (pair every anchor against its known-bad state) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
