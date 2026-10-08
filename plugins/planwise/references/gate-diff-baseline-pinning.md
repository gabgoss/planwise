---
description: A `git diff` gate names a recorded tree state or it measures the whole working tree — record `$..._BASE` before the first edit behind an empty status over the write paths (§8.1), scope every gate to it (§8.2), path-scope with `-- <paths>` and never with an output filter (§8.3), record a series base once at the first sprint (§8.4), give a scope rule a positive test rather than a list of forbidden directories (§8.5), and treat a base as a statement about one moment that a commit inside the gate's paths invalidates (§8.6); Reviewer Check 077. This file is the definition site for `$..._BASE`.
paths: {planwise_root}/{plans_dir}/**
---

# Gate Diff Baseline Pinning (A Diff-Scoped Gate Pins a Recorded Baseline)

**Purpose:** A gate built on `git diff` is a question about a tree state. A diff that names no state answers about the entire working tree instead of the sprint's own delta, and it goes wrong in both directions at once. This file defines the recorded base and the rules every diff-scoped gate follows. Split from `verification-gates.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gates.md §N` citation translates by filename alone. The family index is `verification-gates.md`.

**Read this when** you write, review or run any gate built on `git diff`, you pin a sprint or series base, or a scope gate is shared with another writer in the same tree.

## Table of Contents

- [8. Diff-Scoped Gates Pin a Recorded Baseline](#8-diff-scoped-gates-pin-a-recorded-baseline)
  - [8.1 Record a baseline before the first edit](#81-record-a-baseline-before-the-first-edit)
  - [8.2 Scope every gate to the recorded base](#82-scope-every-gate-to-the-recorded-base)
  - [8.3 Path-scope with `-- <paths>`, not with an output filter](#83-path-scope-with----paths-not-with-an-output-filter)
  - [8.4 A multi-sprint series records a series base once, at the first sprint](#84-a-multi-sprint-series-records-a-series-base-once-at-the-first-sprint)
  - [8.5 A scope rule gets a positive test, not a list of forbidden directories](#85-a-scope-rule-gets-a-positive-test-not-a-list-of-forbidden-directories)
  - [8.6 A Base Is a Statement About One Moment; Commits After It Inside the Gate's Paths Break Every Delta Gate](#86-a-base-is-a-statement-about-one-moment-commits-after-it-inside-the-gates-paths-break-every-delta-gate)

---

## 8. Diff-Scoped Gates Pin a Recorded Baseline

A gate built on `git diff` is a question about a **tree state**. A `diff` that names no state does not decline to answer — it answers about the entire working tree instead of the sprint's own delta. The command still runs, still prints, and still reads as green or red; it is simply measuring a different tree than the one the sprint wrote. That goes wrong in both directions at once:

- **False FAIL.** Any uncommitted work present when the session opened — an earlier session, a parallel sprint, a human mid-edit — counts against this sprint. Measured once on a live repo: 6 modified files, +575 / −66, three of them under a directory one sprint's exit criterion forbids outright. That state alone failed the scope gates of three sprints in a six-sprint plan **before a single task ran**.
- **False PASS / misattribution.** A self-containment sweep scans added lines the sprint never wrote. A forbidden token on one of those lines is blamed on this sprint, and a leak this sprint really did introduce is just as arbitrarily credited elsewhere once someone commits between gates. A tree that clears an unpinned sweep cleared it by luck, and the report cannot tell the difference.
- **Parallelism breakage.** `git diff --name-only | grep '<dir>/'` asserting "this sprint edited nothing under `<dir>`" trips on a concurrently running sprint's legitimate work in that directory — a hard FAIL caused entirely by someone else's correct behaviour.

The defect is systemic rather than per-plan: one audit found 109 diff-scoped gates across six sprints of a single plan, every one authored from intent rather than from a dry run.

**This section is the definition site for `$..._BASE`.** [measurement-discipline.md](measurement-discipline.md) §8.7 governs the *input-set* half of the same gate — untracked-file registration (`git add -N`), the input-set assertion, the unfiltered on-disk sweep, and the known-bad dry-run — and its examples consume `$BASE` without defining it. The two halves are complementary and neither restates the other: §8.7 asks *did the gate inspect anything*, this section asks *did it inspect the right tree state*. An empty result means nothing until both are answered.

Throughout this section `$BASE` stands for the sprint's own recorded `{ABBREV}_S{NN}_BASE` (or `{ABBREV}_SERIES_BASE` where a whole-series view is meant). It is a **recorded value**, never a literal to copy forward.

### 8.1 Record a baseline before the first edit

> [!constraint] The first task in a sprint that touches the target repo records the base, behind a clean-scope precondition
> ```bash
> git -C <repo> status --porcelain -- <this sprint's write paths>
> # MUST be empty. Non-empty → HALT: an earlier session, a parallel sprint, or a human
> # has uncommitted work inside this sprint's write-set. Commit or stash it, then re-run.
> # Attribute each non-empty path to its owner BEFORE reporting the HALT, and never aim a
> # revert at a path this session did not write (read-confirm-act-protocol.md §1.5).
> # Do NOT pin over a dirty scope — the base would already carry work this sprint did not do,
> # and every gate scoped to it would inherit that work as its own.
> {ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)
> ```
> Record the name, the value, and the recording task in the session Recovery file's Key Findings. That record is the **first write of the session** — before any edit. A base pinned after an edit already contains it, so every gate scoped to that base is blind to the one change it was written to check, and reports empty for the reason that makes an empty result worthless.

The precondition is scoped with `--` to **this sprint's write paths**, not to the whole repo: unrelated dirt outside the sprint's area is not this sprint's problem to stash, and a whole-repo cleanliness demand is the kind of gate sessions learn to override. Carry the recorded value where later sprints can find it — a Sprint Overview status cell is enough:

```markdown
| {Sprint-N} | {Session-Name} | ✅ COMPLETE | Verdict PASS — 7/7 tasks. `{ABBREV}_S{NN}_BASE=5b53607` |
```

### 8.2 Scope every gate to the recorded base

> [!constraint] Every diff-scoped gate names the recorded base — `git diff $BASE -- <paths>`
> Never a bare `git diff`, never `git diff --name-only` with no operand, and never `git diff HEAD`. `HEAD` is not a synonym for the base: it moves with every commit the session makes, so a gate written against it measures the delta since the *last commit*, not since the sprint began. A session that commits mid-way silently erases all of its own earlier work from every later gate — the gates go green because the evidence left the diff, not because the defect left the tree.

### 8.3 Path-scope with `-- <paths>`, not with an output filter

`-- <paths>` restricts the tree git **inspects**. A downstream filter only hides part of what git already inspected and reported, and the difference is exactly the parallel-safety property a scope gate needs. `git diff --name-only | grep '<dir>/'` walks the whole repository, so a sibling sprint's concurrent work under `<dir>` enters the result and is attributed here; under `git diff --name-only $BASE -- <paths>` that work was never in the input at all — invisible by construction.

The filter form fails a second way: it matches **text**, not paths. A pattern for a directory name also matches any file whose *name* contains that string elsewhere in the tree, and misses the same directory reached under a different spelling. `--` matches paths.

### 8.4 A multi-sprint series records a series base once, at the first sprint

A plan whose sprints each pin their own base can gate each sprint's delta but has no way to diff the **series**: the release battery, the whole-refactor self-containment sweep, the "did we edit a file no sprint ever declared" scope test all need a single base predating the first sprint. Record a second name, `{ABBREV}_SERIES_BASE`, at the first task of the first sprint, and carry it verbatim into every later sprint's Recovery.

> [!constraint] First-to-touch — check for an already-recorded series base before minting one
> A task that pins the series base must not assume it ran first. Plans routinely declare sprints INDEPENDENT, and an independent sprint may legitimately execute **and commit** before the nominally-first one starts. Check before claiming the name: Grep for `{ABBREV}_SERIES_BASE` across the plan's Recovery files. If a prior sprint's Recovery already records a value, **adopt that value verbatim** — do not re-derive it. Only when none exists does this task's own HEAD become the series base.
>
> Re-minting a series base that already includes an independent sprint's commits silently narrows the whole-series sweep to the remaining delta: that sprint's added lines are never in the input, so the final cross-check is blind to them while every per-sprint gate still reports green. The failure surfaces at release, in the one gate meant to be the backstop.

### 8.5 A scope rule gets a positive test, not a list of forbidden directories

A scope rule states where a sprint **may** write. Testing it by enumerating the places it may not write permits every directory nobody thought to forbid — including directories that did not exist when the gate was authored. Assert the allowed set instead and require the complement to be empty:

```bash
# WRONG — enumerates the forbidden set; anything unlisted passes silently:
git -C <repo> diff --name-only $BASE -- <root> | grep -E '^<forbidden dir>/'      # expect empty
# CORRECT — asserts the allowed set; anything unlisted FAILS:
git -C <repo> diff --name-only $BASE -- <root> | grep -vE '^(<allowed dir A>|<allowed dir B>)/'   # expect empty
```

The two commands are the same length and read almost identically. Only the second one can fail for a reason nobody anticipated, which is the only kind of failure a scope gate exists to catch.

> [!constraint] The three canonical unpinned shapes, and their baseline-scoped rewrites
> WRONG — none of the three names a tree state; all three read the entire working tree:
> ```bash
> git -C <repo> diff <path>/ | grep -E '^\+' | grep -E '<leak pattern>'   # expect empty
> git -C <repo> diff --name-only | grep '<forbidden dir>'                 # expect empty
> git -C <repo> diff --name-only                                          # expect exactly N files
> ```
> CORRECT — each scoped to the recorded base and path-scoped with `--`:
> ```bash
> git -C <repo> diff $BASE -- <paths> | grep -E '^\+' | grep -E '<leak pattern>'          # expect empty
> git -C <repo> diff --name-only $BASE -- <root> | grep -vE '^(<allowed dir>)/'           # expect empty
> git -C <repo> diff --name-only $BASE -- <paths> | wc -l                                 # expect exactly N
> ```
> **Both failure directions live on the WRONG side, and they are not the same defect.**
> - **False FAIL** — pre-existing uncommitted work counts against the sprint. The file-count form reports more files than N, and the sprint is marked over-scope for edits it never made; the directory-filter form fires on a parallel sprint's legitimate work. The cost is a halted session and a re-litigated scope, paid every time the tree is not pristine.
> - **False PASS / misattribution** — the leak-pattern form scans added lines the sprint never wrote, so a forbidden token belonging to nobody in the plan is reported as this sprint's leak, and a real leak is credited to whichever sprint happens to be running. Nothing in the output distinguishes the two, and the empty case — the one everybody reads as "clean" — is where the misattribution is completely invisible.
>
> The rewrite is mechanical, so there is no case for the WRONG forms: an unpinned gate is not a cheaper gate, it is a gate whose result does not mean what the report says it means.

#### Reviewer Check 077 — Diff-Scoped Gate Not Baseline-Pinned

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Any `git diff` in a task file's Verification Commands or Success Criteria MUST be scoped to a recorded baseline — the sprint's `{ABBREV}_S{NN}_BASE`, or `{ABBREV}_SERIES_BASE` for a whole-series battery — and MUST path-scope with `-- <paths>` rather than by filtering the command's output. A sprint whose first repo-touching task records no baseline at all fails this check for every gate in the sprint, including gates that name a `$..._BASE` operand that is never pinned anywhere. An unpinned gate reads the whole working tree: pre-existing uncommitted work counts against the sprint (false FAIL) and added lines the sprint never wrote are attributed to it (false PASS).
- **Detection:**
  1. Grep the task file for `git diff`; every hit is a candidate.
  2. For each hit, assert **(a)** a `$..._BASE` operand is present, **(b)** a `--` path scope is present — a pipe into a path filter does not satisfy this, and **(c)** the operand names a base the sprint's first repo-touching task actually records. Any one absent → ERROR.
  3. Open that first repo-touching task and confirm it pins the base **before its first edit**, behind a clean-scope precondition (`git status --porcelain -- <write paths>` MUST be empty, else HALT), and records name + value in Recovery Key Findings. Pinned after an edit, or not recorded → ERROR.
  4. On a multi-sprint plan, confirm a `{ABBREV}_SERIES_BASE` is recorded once at the first sprint and **adopted verbatim** by later sprints. A later sprint that re-derives it from its own HEAD → ERROR.
  5. Inspect any scope gate that enumerates forbidden directories rather than asserting the allowed set; the enumerating form permits every directory nobody listed → ERROR.
- **Finding template:**
```
[ERROR] Diff-scoped gate not baseline-pinned
File: {task file path} | Location: Verification Commands / Success Criteria step {n}
Issue: Gate runs `git diff` with {no recorded base | `HEAD` as the operand | no `--` path scope | a base no task in the sprint records}; it reads the whole working tree, so pre-existing uncommitted work fails the sprint (false FAIL) and added lines the sprint never wrote are attributed to it (false PASS)
Fix: Pin `{ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)` in the sprint's first repo-touching task behind an empty-`git status --porcelain -- <write paths>` precondition, record it in Recovery Key Findings before the first edit, and rewrite the gate as `git diff $BASE -- <paths>` per references/gate-diff-baseline-pinning.md §8 | Confidence: HIGH
```

### 8.6 A Base Is a Statement About One Moment; Commits After It Inside the Gate's Paths Break Every Delta Gate

A commit does not remove work from a `$BASE..worktree` diff. It moves that work from "uncommitted" to "committed", and both states sit inside the range. In a repository that a second session can write to, a whole-tree gate measures every writer's work, not this session's. Measured once: a pinned count of 6 files became 14, then 22, while a second session kept editing. Run as pinned, the gate failed a correct tree.

> [!constraint] Four operative points for a shared repository
> 1. **Pin every diff gate to an explicit path list from the start.** Assert on `git diff --name-only $BASE -- <path list> | wc -l`. Print the whole-tree listing so a human can classify it, but do not assert on it.
> 2. **A clean `git status` is not evidence the gate scope is clean.** A clean tree after a bundled commit is the case where a whole-tree base diff is most wrong, because the committed foreign work is still inside the range.
> 3. **Expect the other session's edits to reach your own files.** Path-scoped gates stay correct. The commit then needs hunk-level staging (`git apply --cached` with a patch of only this session's lines), taken from a saved snapshot of the foreign diff.
> 4. **When a pinned count moves (6, then 14, then 22), ask what the diff range contains before asking what changed in your code.**

**Session-start base.** A sprint-wide base serves as a record. A session's own delta gates need a base pinned at that session's start. At each session's preflight, list the commits that landed after the sprint base inside the gates' pathspecs:

```bash
git log --oneline <sprint base>..HEAD -- <the gates' pathspecs>
```

- **Empty:** the sprint base is still exact for this session.
- **Non-empty:** pin a session-start base, record both bases, and name each intervening commit as an attributed delta for any gate that still compares against the sprint base.

> [!constraint] A sprint-wide base goes stale when an earlier session commits under the gates' pathspec
> WRONG — adopt the sprint base unconditionally. The first session's closeout committed three new files under the pathspec, so a frontmatter-key gate matches every `+id:` line of those files and fails correct work:
> ```bash
> git diff <sprint base> -- '<dir>/<prefix>-*.md' | grep -E '^[+-](id|title):'   # hits on 3 new files
> ```
> CORRECT — check for intervening commits, then pin the session's own start:
> ```bash
> git log --oneline <sprint base>..HEAD -- '<dir>/'        # <hash> (3 new files)
> SESSION_START=$(git rev-parse HEAD)
> git diff $SESSION_START -- '<dir>/<prefix>-*.md' | grep -E '^[+-](id|title):'   # empty
> ```

**Corpus count check.** At the same preflight, compare the live file count in the gated directory against the figure the plan carries. A mismatch (302 live against 299 recorded) is the early signal that a commit landed after the base.

Cross-references: §8.4 (the series base, which has the same first-to-touch hazard) and §8.1 (the clean-scope precondition, which also requires attribution per [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.5).

---

*Cross-references: [measurement-discipline.md](measurement-discipline.md) §8.7 (the input-set half of the same gate: untracked registration, the input-set assertion, the on-disk sweep, the known-bad dry run) · [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) (the recorded pre-edit **value**, independent of the recorded base **commit** this file governs) · [gate-baseline-independence.md](gate-baseline-independence.md) (a gate asserting a property of a diff needs a baseline copy the executor did not make) · [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.5 (attribution before a revert at a path this session did not write) · [verification-gates.md](verification-gates.md) (the family index).*
