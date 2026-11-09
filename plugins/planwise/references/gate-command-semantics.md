---
description: Four command semantics that make a well-formed gate mean something else — `grep -c` counts lines not matches, `-B1`/`-A1` emit the match line too, set membership is not count equality, and a path resolves from the cwd the anchor's own table declares (§10.8); and four more mismatches between mechanism and claim — a context window cannot see outside itself, a cardinal pattern against an ordinal threshold, a numeric literal without digit boundaries, the regex dialect, and a fixed-size window that must fit its subject (§10.9); and a Verification Command is a claim about the environment, so it uses the project's own interpreter, names an agent-invocable step and an existing path, and carries a pasted exit code, runs a direct script probe under `python -B`, and the `Grep` tool reads alternation as a bare `|` (§10.9.1, Reviewer Check 114); and seven count, selector and smoke anchors that misread correct output — a formatter reshaping the asserted line, a line cap on hand-packed code, paired quiet and verbose flags, a `-k` selector with test-name collisions, a star import then a private name, an over-broad inner grep, and a positive count that expects a mention count (§10.9, Checks 39 to 41).
consult-when: Pinning any `grep`, `diff`, `wc` or `awk` gate — `grep -c` counts lines, context flags emit the match, set membership is not count equality, a path resolves from the declared cwd (§10.8); pattern unit versus threshold unit, digit boundaries, regex dialect, a window that must fit its subject (§10.9); a Verification Command run in the target environment, its exit code pasted into the brief, a direct script probe run under `python -B`, and the `Grep` tool's bare-pipe alternation (§10.9.1, Check 114); a count, selector or smoke anchor that reads wrong on correct output, such as a formatter reshape, a line cap, paired `-q` and `-v`, a `-k` selector with a pass count, a star import then a private name, an inner grep or a mention count (§10.9, Checks 39 to 41)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Command Semantics (Read the Command as a Program)

**Purpose:** These gates are not vacuous and not narrow. They are well-formed commands that do not measure what their author read them as measuring, and a pre-edit annotation does not catch them because the annotation records the same misread value. State in one sentence what the command physically inspects, then compare that to what the criterion claims. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you pin any `grep`, `diff`, `wc` or `awk` gate, you review a Signoff anchor table, or a gate returns a value that is plausible but wrong on work you know is correct. Read it also when you write or review a Verification Commands entry, because a well-formed command can still be unable to run in the target environment.

## Table of Contents

  - [10.8 Four command semantics that make a well-formed gate mean something else](#108-four-command-semantics-that-make-a-well-formed-gate-mean-something-else)
  - [10.9 Read the command as a program — four more mismatches between mechanism and claim](#109-read-the-command-as-a-program--four-more-mismatches-between-mechanism-and-claim)
  - [10.9.1 A Verification Command is a claim about the environment: execute it first](#1091-a-verification-command-is-a-claim-about-the-environment-execute-it-first)

---

### 10.8 Four command semantics that make a well-formed gate mean something else

The gates in this family are not vacuous and not narrow. They are well-formed commands that do not measure what their author read them as measuring. A pre-edit annotation does not catch them, because the annotation records the same misread value.

Check all four before a gate ships:

| # | Trap | What the author assumed | What the command does |
|---|------|-------------------------|-----------------------|
| 1 | `grep -c` counts matches | One count per occurrence | Counts matching **lines**. Use `grep -o … \| wc -l` when occurrences are the subject. |
| 2 | `-B1` / `-A1` / `-C1` emit context only | The output holds only surrounding lines | The output holds the match line **as well**, so a count over it includes every match. |
| 3 | Set membership hardened into count equality | `expected ⊆ actual` and `count(actual) == count(expected)` agree | They disagree on every correct superset. Assert the membership the criterion actually claims, one member per assertion, per `gate-heuristic-verifier-patterns.md` §2. |
| 4 | A path resolves from wherever the runner stands | The anchor, or a task's Verification Commands block, runs from the plan folder or the repo root | It runs from the cwd the anchor's **own table header** declares, or from the base the block's `**Working directory:**` line declares. A plan-relative path under a repo-root base fails unconditionally, and the criterion FAILs work that passed. |

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
> The same rule binds a task file's Verification Commands block. Its `**Working directory:**` line is the declared base, and `.` (the repo root) is the default. A block that mixes a repo-root tool path with a bare `Outputs/` or `../` path leaves no base that satisfies both.
>
> Trap 4 is the cheapest of the four to catch and the easiest to miss, because the anchor reads correctly in the task file it was drafted beside.

Traps 1 and 2 are enforced by `scripts/lint_verification_gates.py`: Check 3 (`_check3_bre_ere_and_line_count_absorption`) flags a `grep -c` count measured as occurrences, and Check 14 (`_check14_context_window_counted`) flags a `-B`/`-A`/`-C` window piped into a count. Trap 4 is enforced by `scripts/lint_gate_checks_plan.py`. Check 27 flags a Signoff anchor path that does not resolve from the declared cwd. Check 34 flags a Verification Commands path that does not resolve from the declared `**Working directory:**`, and a block that mixes a repo-root path with a bare `Outputs/` or `../` path and declares no base. Trap 3 has no linter coverage — run it by hand at scaffold close.

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

**Seven count, selector and smoke anchors that misread correct output.** Each row is a well-formed anchor that reports the wrong verdict on correct work. A runner who trusts the brief then reports a defect in correct work or weakens the gate.

| Mechanism | What correct output reads as | Remedy |
|---|---|---|
| A formatter reshapes the asserted line | An exact-line grep reads 0, because `ruff format` wrapped a long constant line into a parenthesised assignment | Run every grep after the final format. Keep trailing comments on gated lines short |
| A line cap measured on hand-packed code | A cap of 12 lines per cell cannot hold a call the formatter expands to the argument count plus 2 lines | Format a stub call at scaffold time and count. Write wide units into the criterion as named exceptions. Never meet a cap with `# fmt: off` |
| `-q` with `-v` in one pytest command | A passing test reads 0 when `pytest -q -v` feeds a count of `PASSED`, because both flags move one shared counter | Prove a count anchor on a passing run and on a forced failure. Record both results beside the command. Check 39 flags the pair |
| A `-k` selector, and test-name collisions | `-k team_game` with `# 7 passed` prints `2 passed, 5 deselected` on a correct module, and a name defined twice silently replaces the first | Prefix every test name with its half. Gate on the whole module and state module-level counts. Run the duplicate-name check below at scaffold time. Check 40 flags the pair |
| `from module import *`, then a `_name` | A smoke raises `NameError` on a correct module, because a star import never binds a name that starts with an underscore | Import every asserted name explicitly. Check 41 flags the pair |
| An over-broad inner grep feeding a zero-result gate | The inner list pulls in a file that only shares a token, such as a schema name that is also a module path | Read the inner list alone before trusting the outer predicate. Anchor to table names or to a heading. When the gate is the task contract, make the false target true for the right reason and record the over-match |
| A positive-count gate that expects a mention count | `# MUST print 1` fails on a well-documented module, because docstrings and callouts mention the token | Express the invariant as the negation of the failure. Anchor the count to defining syntax such as `^_NAME: type =`. The exact-count half above states the cause |

The duplicate-name check reads definitions, so a name that two tasks mention in prose does not fire. Plant one duplicate in a scratch copy and confirm the command prints it. An empty result from an unplanted run proves nothing.

```bash
grep -ohE "def test_[A-Za-z0-9_]+" task-01.md task-02.md | sort | uniq -d   # MUST print nothing
```

`scripts/lint_gate_checks_commands.py` enforces three of the seven. Check 39 (`_check39_pytest_quiet_with_verbose`) flags `-q` with `-v` in one pytest command. Check 40 (`_check40_selector_paired_with_pass_count`) flags a `-k` selector gated on `N passed`. It reports an ERROR when N equals the number of test names the task file lists but fewer hold the token, which is the signature of a module-level count copied onto a selector. It reports a WARNING when N equals the number of listed names that hold the token. It reports UNCERTAIN when the list may be partial or the selector names a class. Check 41 (`_check41_star_import_then_private_name`) flags `import *` followed by an underscore name on one command line. `/planwise review` runs the linter, so all three reach its report. The other four have no linter coverage, so run them by hand at scaffold close.

> [!practice] When a gate needs N separately-owned repairs to become reachable, every site must say the others exist
> Otherwise a partial landing presents as a failed implementation rather than an incomplete repair, and the runner debugs its own correct work.
>
> The positive instance that motivates it: a gate proven at plan review to return **3 against 1 on a correct implementation** would have halted five tasks on good work. It reached its intended end state only because two independent repairs, owned by two different tasks, both landed.

### 10.9.1 A Verification Command is a claim about the environment: execute it first

> [!constraint] A command that passes review can still be unable to run
> Review checks what a command asserts. It does not check that the command runs. A non-executable anchor is a missing anchor wearing a costume, because the task still reports a verdict from a gate that measured nothing.

**Scenario.** A plan passed three review rounds and shipped six Verification Commands that could not execute:

- A bare `python -c "..."` resolved to a global interpreter with none of the project's dependencies.
- A bare `jupyter nbconvert --execute` ran where `jupyter` was not on `PATH`.
- A step "deploy via the editor extension" named an editor UI feature that a dispatched agent cannot invoke.
- A literal `/tmp/baseline.json` path does not exist on Windows.
- A SQL predicate `WHERE (a IS NULL) <> (b IS NULL)` fails at T-SQL parse time.
- `assert r == (157, 347, 179)` compared a driver row to a tuple, and `Row.__eq__` against a tuple is always False.

**The rule.** For each Verification Commands entry, confirm four facts:

1. **The interpreter or binary is the project's own.** A bare `python` or `jupyter` resolves from `PATH` and may reach a global install. Name the project's launcher, or state that the target environment provides the bare name.
2. **The step is agent-invocable.** A dispatched agent has no editor UI. A step that needs a menu, an extension command or a click is not a command.
3. **Every path exists on the target OS.** `/tmp` does not exist on Windows. Use a path the runner can create, such as the session scratch directory.
4. **A direct script probe runs under `python -B`.** A command that runs `python <script>.py` or `python -c "import <module>"` outside pytest writes bytecode caches. Add `-B`, or state in the brief why the command omits it.

Then execute the command at scaffold time or review time, or run a read-only probe of its mechanism. Paste the exit code into the brief. Only execution exposes the SQL parse error and the tuple comparison. A command with no pasted exit code is unproven.

```
WRONG — each command asserts the right thing and none was ever run:
  python -c "import json; ..."          # bare interpreter, may reach a global install
  assert r == (157, 347, 179)           # Row.__eq__ against a tuple is always False
  (no exit code beside either line)

CORRECT — each command names its environment, was run once, and the brief pastes the result:
  <project launcher> python -c "import json; ..."   # exit 0, run at scaffold time
  assert tuple(r) == (157, 347, 179)                # exit 0, run against the fixture row
```

**The direct-probe rule.** CPython writes the caches next to the modules a direct probe imports, which puts them inside the shipped tree. A verification task's own diagnostic probes are not exempt. In one run, the verifier's own probe regenerated a cache just before the sprint verdict. The report briefly read FAIL on a sprint that otherwise passed. Prefer an environment default such as `PYTHONDONTWRITEBYTECODE=1` over a remembered rule. Two of the six occurrences in that run came from actors whose spawn prompts already named `python -B`, so a prior warning alone did not prevent them. This convention reduces the sweep's workload. It does not replace the sweep, which `gate-environment-inputs.md` §20 specifies.

```
# Writes caches into the shipped tree:
python -c "import <module>; ..."
python "<plugin_root>/scripts/<script>.py" ...

# Suppresses bytecode writing for the probe:
python -B -c "import <module>; ..."
python -B "<plugin_root>/scripts/<script>.py" ...
```

**The `Grep` tool dialect.** The native `Grep` tool uses ripgrep. Ripgrep reads a backslash-pipe as a literal pipe, so an alternation written that way matches the text `alpha|beta` and returns 0. Write alternation as a bare `|`. A bare `|` inside a markdown table cell splits the cell, so no alternation pattern goes in a table cell. Put the call in a fenced block and let the cell point to it. `scripts/lint_verification_gates.py` Check 8 (`_check8_grep_tool_escaped_pipe_alternation`) flags the backslash-pipe form.

```
WRONG:   Grep pattern='alpha\|beta'    -> 0 hits    (a literal pipe)
CORRECT: Grep pattern='alpha|beta'     -> hits on either word
```

**Applies to** every Verification Commands entry and every Signoff anchor command in a task brief. **Sibling rule:** the section above (§10.9) asks what the command physically inspects. This section asks whether the command runs at all.

#### Reviewer Check 114 — Verification Command Not Proven to Run in the Target Environment

- **Severity / Role / Type:** BLOCKER (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** Each Verification Commands entry MUST use the project's own interpreter or binary, name an agent-invocable step, and name only paths that exist on the target OS. The brief MUST carry the exit code of an executed run, or of a read-only probe of the command's mechanism. A non-executable anchor counts as a missing anchor.
- **Detection:** The reviewer has no shell, so it reads the brief. Use Grep over the plan's task files for Verification Commands entries. Flag a bare interpreter or tool name (`python`, `python3`, `jupyter`) with no project launcher and no stated environment. Flag a step that names an editor, IDE or UI action. Flag a POSIX-only literal path such as `/tmp/`. Flag any entry with no pasted exit code or probe result. Also flag a native `Grep` call that writes alternation as a backslash-pipe, and any alternation pattern inside a table cell.
- **Finding template:**
```
[BLOCKER] Verification Command not proven to run in the target environment
File: {task file path} | Location: {Verification Commands entry}
Issue: "{command}" {uses a bare interpreter | names a UI step | names a path absent on the target OS | carries no pasted exit code}, so the anchor may not execute
Fix: Name the project's own interpreter, replace a UI step with a command, use a path that exists on the target OS, then execute the command or a read-only probe of its mechanism and paste the exit code, per references/gate-command-semantics.md §10.9.1 | Confidence: HIGH
```

---

*Cross-references: [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §2 (per-unit assertions, the remedy trap 3 points at) · [gate-anchor-outcome-set.md](gate-anchor-outcome-set.md) §10.7 (set agreement is not count equality) · [gate-pinned-from-real-content.md](gate-pinned-from-real-content.md) (the step these rules assume: the gate was run over the real content) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) (pair every anchor against its known-bad state) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
