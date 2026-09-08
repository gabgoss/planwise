---
description: A gate that asserts a property of a diff — comment-only, no-logic-change, N-files-touched — measures nothing when its target is untracked, and reports the file's entire body as additions once `git add -N` registers it. Covers why an untracked target makes such a gate vacuous, why intent-to-add inverts it instead of repairing it, the recorded-baseline form that discriminates, why a baseline taken from version control outranks one the executor made, and why a chained `grep -c` skips the clean case. Consult before writing or accepting any gate whose subject is a diff.
paths: {planwise_root}/{plans_dir}/**
---
# Gate Baseline Independence — a Diff-Property Gate Needs a Baseline It Can Reach, and One It Did Not Make

**Purpose:** Name the corpus before writing the check. Every verification command reads some set of files. The gate is evidence only when that set is the set the claim is about. This file covers the case where the two differ silently, because git cannot see the target at all.

**Read this when** a gate asserts a property of a diff — the change was comment-only, no logic moved, exactly N files were touched. Read it also when you accept such a gate's result from someone else.

`git diff` answers one question. It reports how the working tree differs from **the index**. An untracked file has no index entry, so the honest answer is *nothing*. A `grep -c`-shaped gate cannot tell that answer apart from *no violations found*. Both print `0`.

This is the baseline half of a three-part problem. [`measurement-discipline.md`](measurement-discipline.md) §8.7 owns the **input set**, and [`gate-predicate-discrimination.md`](gate-predicate-discrimination.md) owns the **predicate**. This file owns the **base the diff is taken against**. §8.7's first remedy is to register new files with `git add -N`. That remedy is correct for a gate asking whether a forbidden pattern appears in added lines. §2 below states the gate class where it inverts.

## Table of Contents

- [1. An Untracked Target Makes a Diff-Property Gate Vacuous](#1-an-untracked-target-makes-a-diff-property-gate-vacuous)
- [2. `git add -N` Inverts a Diff-Property Gate Rather Than Repairing It](#2-git-add--n-inverts-a-diff-property-gate-rather-than-repairing-it)
- [3. Record a Baseline Before the First Edit, and Prefer One You Did Not Make](#3-record-a-baseline-before-the-first-edit-and-prefer-one-you-did-not-make)
- [4. A Chained `grep -c` Gate Skips the Case It Most Needs to Confirm](#4-a-chained-grep--c-gate-skips-the-case-it-most-needs-to-confirm)
- [5. Pre-Dispatch Checklist for Verification Commands](#5-pre-dispatch-checklist-for-verification-commands)

---

## 1. An Untracked Target Makes a Diff-Property Gate Vacuous

A task annotated a 32-line hook script with comments and had to prove it changed no logic. The authored gate was:

```bash
git diff -- <old-dir>/<hook>.ps1 | grep -cE '^\+[^+]' && \
git diff -- <old-dir>/<hook>.ps1 | grep -E '^\+[^+]' | grep -vcE '^\+\s*#'
# expect: N added lines, and 0 of them non-comment
```

Two facts about the target defeated it. The file had been **moved in the working tree and never committed**. It was deleted at `<old-dir>/` and recreated, untracked, at `.claude/hooks/`.

- Against the **new** path, `git diff` has no index entry to compare against and emits nothing. `grep -c` returns `0`, then `0`. The gate passes having examined an empty stream.
- Against the **old** path, the diff is a pure deletion. Every line is a `-` line and there are zero `+` lines. The gate again reports `0` added and `0` non-comment.

Either way the gate reports success without ever seeing the edit. A gate in this state and a gate that never ran produce identical output.

> [!constraint] Never gate a change to an untracked file with `git diff`
> WRONG — empty by construction, and it passes without examining anything:
> ```bash
> git diff -- .claude/hooks/<hook>.ps1 | grep -cE '^\+[^+]'   # 0 — vacuous
> ```
> CORRECT — see §3. Snapshot a baseline before the edit, then diff against that file.
>
> The check that costs one command: confirm the named target is actually tracked. `git ls-files --error-unmatch <path>` exits non-zero when it is not. An untracked target means the gate is decorative, whatever it prints.

---

## 2. `git add -N` Inverts a Diff-Property Gate Rather Than Repairing It

Intent-to-add is the obvious repair, and it is the remedy [`measurement-discipline.md`](measurement-discipline.md) §8.7 states for the input-set problem. Registering the path does put it in the diff. For a **pattern-presence** gate that is the correct fix, because the question is whether a forbidden token appears anywhere in the change.

For a **diff-property** gate it is worse than the vacuous form. `git add -N` records the path against an **empty blob**, so every pre-existing line in the file renders as an addition.

> [!constraint] `git add -N` repairs a pattern-presence gate and inverts a diff-property gate
> WRONG — intent-to-add turns the file's own untouched logic into violations:
> ```bash
> git add -N .claude/hooks/<hook>.ps1
> git diff -- .claude/hooks/<hook>.ps1 | grep -E '^\+[^+]' | grep -vcE '^\+\s*#'
> # 22 — the file's 32 pre-existing lines, reported as non-comment additions
> ```
> The first form fails silently and the second fails loudly, so this is not simply the same defect twice. A vacuous gate passes work it never inspected. An inverted gate **fails correct work**, and it names lines the task never touched. A runner under retry pressure then edits code to satisfy a gate that was wrong about it.
>
> Read the gate's class before reaching for `add -N`:
>
> | Gate asks | Register with `add -N`? |
> |---|---|
> | Does a forbidden pattern appear in the change? | Yes — §8.7 remedy 1 applies |
> | Is the change comment-only, logic-identical, or N lines? | No — it inverts. Use §3's recorded baseline |

---

## 3. Record a Baseline Before the First Edit, and Prefer One You Did Not Make

A diff needs two sides. When git cannot supply the left side, supply it yourself, and supply it **before** the edit.

```bash
cp .claude/hooks/<hook>.ps1 "$SCRATCH/baseline.ps1"      # before any edit
# …make the edit…
diff "$SCRATCH/baseline.ps1" .claude/hooks/<hook>.ps1 | grep -c '^<'   # 0 = nothing removed or altered
grep -vE '^\s*#' "$SCRATCH/baseline.ps1" > "$SCRATCH/a"
grep -vE '^\s*#' .claude/hooks/<hook>.ps1 > "$SCRATCH/b"
diff "$SCRATCH/a" "$SCRATCH/b"                            # EMPTY = logic byte-identical
```

The copy must precede the first edit. A baseline taken afterwards already contains the change, so the gate is blind to the one thing it exists to check.

**When the file was tracked at a former path, git still holds a usable baseline.** It is stronger than a self-made copy, because the executor cannot have influenced it:

```bash
git show HEAD:<old-dir>/<hook>.ps1 > "$SCRATCH/orch-baseline.ps1"
diff --strip-trailing-cr "$SCRATCH/orch-baseline.ps1" .claude/hooks/<hook>.ps1 | grep -c '^<'   # 0
```

`--strip-trailing-cr` neutralises CRLF differences between the stored blob and a Windows checkout.

> [!practice] Prefer the version-control baseline when verifying someone else's claim
> An agent that grades its own comment-only edit against a baseline it made itself is checking its work with its own instrument. The git blob is independent evidence. An orchestrator accepting a runner's self-graded verification should reach for the blob form, or ask for the baseline's provenance.

Dry-run the finished gate once against known-bad input and once against known-good input, and require the two runs to differ. The recipe and its rationale live in [`measurement-discipline.md`](measurement-discipline.md) §8.7 remedy 4, and [`gate-predicate-discrimination.md`](gate-predicate-discrimination.md) §1 gives a version-control form that needs no scratch file. Both defects in §1 and §2 would have surfaced in one such run.

---

## 4. A Chained `grep -c` Gate Skips the Case It Most Needs to Confirm

`A && B`, where `A` is a `grep -c`, runs `B` only when `A` succeeds. `grep` exits non-zero when it matches nothing, so a count of `0` short-circuits the chain. That is exactly the clean case the gate was written to confirm.

> [!constraint] Run each check as its own command
> WRONG — the second assertion never executes on the input that matters:
> ```bash
> git diff -- <path> | grep -cE '^\+[^+]' && git diff -- <path> | grep -E '^\+[^+]' | grep -vcE '^\+\s*#'
> ```
> CORRECT — two commands, two results, both reported:
> ```bash
> diff "$SCRATCH/baseline" <path> | grep -c '^>'          # added lines
> diff "$SCRATCH/baseline" <path> | grep '^>' | grep -vcE '^>\s*#'   # non-comment among them
> ```
> The same trap fires in any gate that chains counted checks with `&&`. A zero from an early link silently retires every link after it, and the report shows only the value that did print.

---

## 5. Pre-Dispatch Checklist for Verification Commands

Run this over a task file's Verification Commands before dispatch, and over a runner's returned evidence before accepting it.

- [ ] Any step asserting a property of a diff, where the target may be untracked — a newly created file, a file relocated by an uncommitted move, or anything under a path the ignore file excludes.
- [ ] Each named target is actually tracked (`git ls-files --error-unmatch <path>`), or the gate is decorative whatever it prints.
- [ ] No `git add -N` sits in front of a diff-property gate. It belongs only in front of a pattern-presence gate (§2).
- [ ] Any baseline the gate diffs against was recorded **before** the first edit, and its provenance is stated.
- [ ] Any orchestrator accepting a runner's self-graded verification prefers a baseline the runner did not produce (§3).
- [ ] No counted check is chained behind another with `&&` (§4).
- [ ] Any "nothing leaked into the shipped tree" claim uses a filesystem walk over an **absolute** path, not a git query. A git query cannot see an ignored path, and packaging does not apply the ignore file. A relative path from the wrong directory errors to stderr and leaves stdout empty, which a "MUST be empty" gate reads as a pass.
- [ ] Any `§`-anchor or line-number citation crossing a two-copy boundary — an installed copy and the source tree that ships next — resolves in the tree the claim's tense names. Present tense names the installed copy. Future tense names the source tree.

---

*Cross-references: [measurement-discipline.md](measurement-discipline.md) §8.7 (the input-set half, and the known-bad dry-run this file cites rather than restates), [gate-predicate-discrimination.md](gate-predicate-discrimination.md) (the predicate half, and the version-control paired-input control), [verification-gates.md](verification-gates.md) §8 (the recorded `$BASE` a sprint's diff-scoped gates are pinned to — this file covers the target that base cannot reach), [verification-gate-evidence.md](verification-gate-evidence.md) §3 (dry-running a MUST-be-N gate in both directions).*
