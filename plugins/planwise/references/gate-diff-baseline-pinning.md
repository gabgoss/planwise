---
description: A `git diff` gate names a recorded tree state or it measures the whole working tree — record `$..._BASE` before the first edit behind an empty status over the write paths (§8.1), scope every gate to it (§8.2), path-scope with `-- <paths>` and never with an output filter (§8.3), record a series base once at the first sprint (§8.4), give a scope rule a positive test rather than a list of forbidden directories (§8.5), and treat a base as a statement about one moment that a commit inside the gate's paths invalidates (§8.6), covering a peer commit that moves HEAD under the close gates, pinning the session's own commit, a path re-check before a paid step, and a reading time on a peer-touched literal, then the input-set half of the same gate: a recorded base is carried and never re-minted (§8.7), a shared working tree shares one git index so HEAD is not a stable base (§8.8), and a `^\+` line is a line added to the diff, not content the change introduced (§8.9); Reviewer Check 077. This file is the definition site for `$..._BASE`.
consult-when: Writing, reviewing or running any gate built on `git diff` — the definition site for `$..._BASE`, record it before the first edit (§8.1), scope every gate to it (§8.2), path-scope with `-- <paths>` (§8.3), a series base once (§8.4), a positive scope test (§8.5), a base is one moment (§8.6), a peer commit mid-session moves HEAD, pin the session's own commit, re-check paths before a paid or outward step, a reading time on a peer-touched literal, a base is a recorded value and is never re-minted (§8.7), a shared tree shares one git index (§8.8), a `^\+` line is not content the change introduced (§8.9), Check 077
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
  - [8.7 A base is a recorded value: recover it by carrying it, never by re-minting it](#87-a-base-is-a-recorded-value-recover-it-by-carrying-it-never-by-re-minting-it)
  - [8.8 A shared working tree shares one git index, so HEAD is not a stable base](#88-a-shared-working-tree-shares-one-git-index-so-head-is-not-a-stable-base)
  - [8.9 A `^\+` line is a line added to the diff, not content the change introduced](#89-a--line-is-a-line-added-to-the-diff-not-content-the-change-introduced)

---

## 8. Diff-Scoped Gates Pin a Recorded Baseline

A gate built on `git diff` is a question about a **tree state**. A `diff` that names no state does not decline to answer — it answers about the entire working tree instead of the sprint's own delta. The command still runs, still prints, and still reads as green or red; it is simply measuring a different tree than the one the sprint wrote. That goes wrong in both directions at once:

- **False FAIL.** Any uncommitted work present when the session opened — an earlier session, a parallel sprint, a human mid-edit — counts against this sprint. Measured once on a live repo: 6 modified files, +575 / −66, three of them under a directory one sprint's exit criterion forbids outright. That state alone failed the scope gates of three sprints in a six-sprint plan **before a single task ran**.
- **False PASS / misattribution.** A self-containment sweep scans added lines the sprint never wrote. A forbidden token on one of those lines is blamed on this sprint, and a leak this sprint really did introduce is just as arbitrarily credited elsewhere once someone commits between gates. A tree that clears an unpinned sweep cleared it by luck, and the report cannot tell the difference.
- **Parallelism breakage.** `git diff --name-only | grep '<dir>/'` asserting "this sprint edited nothing under `<dir>`" trips on a concurrently running sprint's legitimate work in that directory — a hard FAIL caused entirely by someone else's correct behaviour.

The defect is systemic rather than per-plan: one audit found 109 diff-scoped gates across six sprints of a single plan, every one authored from intent rather than from a dry run.

**This section is the definition site for `$..._BASE`.** [measurement-discipline.md](measurement-discipline.md) §8.7 governs the *input-set* half of the same gate — untracked-file registration (`git add -N`), the input-set assertion, the unfiltered on-disk sweep, and the known-bad dry-run — and its examples consume `$BASE` without defining it. The two halves are complementary and neither restates the other: §8.7 asks *did the gate inspect anything*, this section asks *did it inspect the right tree state*. An empty result means nothing until both are answered.

Throughout this section `$BASE` stands for the sprint's own recorded `{ABBREV}_S{NN}_BASE` (or `{ABBREV}_SERIES_BASE` where a whole-series view is meant). It is a **recorded value**: pinned once from the live repo, then carried as the resolved SHA. Never copy it from another sprint, and never re-derive it from a later `HEAD`.

**The executed gate carries the base in the same call.** The Bash tool keeps no shell state between calls, so a `BASE=` assignment made in one call is unset in the next. An unset `$BASE` drops out of `git diff $BASE -- <paths>`, and the command then becomes a working-tree-against-index diff that still prints plausible counts. Write the recorded SHA as a literal, or set the variable in the same command: `BASE=<recorded SHA>; git -C <repo> diff "${BASE:?unset}" -- <paths>`. The `${BASE:?unset}` form stops with an error when the variable is empty. `$BASE` in this file is notation for the recorded value.

### 8.1 Record a baseline before the first edit

> [!constraint] The first task in a sprint that touches the target repo records the base, behind a clean-scope precondition
> ```bash
> git -C <repo> status --porcelain -- <this sprint's write paths>
> # MUST be empty. Non-empty → HALT: an earlier session, a parallel sprint, or a human
> # has uncommitted work inside this sprint's write-set. Its owner commits it (never stash), then re-run.
> # Attribute each non-empty path to its owner BEFORE reporting the HALT, and never aim a
> # revert at a path this session did not write (read-confirm-act-protocol.md §1.5).
> # Do NOT pin over a dirty scope — the base would already carry work this sprint did not do,
> # and every gate scoped to it would inherit that work as its own.
> {ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)
> ```
> Record the name, the value, and the recording task in the session Recovery file's Key Findings. That record is the **first write of the session** — before any edit. A base pinned after an edit already contains it, so every gate scoped to that base is blind to the one change it was written to check, and reports empty for the reason that makes an empty result worthless.

The Recovery record is the orchestrator's own copy of the base. It is not a runner input. Under DELEGATED execution the orchestrator reads the recorded value once and injects it as a `Base commit:` line, a resolved SHA literal, into every later spawn prompt. [agent-orchestration-delegated.md](agent-orchestration-delegated.md) §1.6 ("Inject the Literal, Do Not Indirect Through a File") defines that injection. A later task takes the base from its spawn prompt and never reads it back from Recovery. Each receiving task proves the literal with `git -C <repo> cat-file -e <sha>^{commit}` before its first diff gate, and HALTs when it does not resolve ([measurement-discipline.md](measurement-discipline.md) §8.7 sub-rule E). When the pinning task shares a dispatch layer with a diff-gating task, the orchestrator pins in the Orchestration file instead, behind the same `status --porcelain` precondition, before it dispatches that layer.

The precondition is scoped with `--` to **this sprint's write paths**, not to the whole repo: unrelated dirt outside the sprint's area is not this sprint's problem to stash, and a whole-repo cleanliness demand is the kind of gate sessions learn to override. Carry the recorded value where later sprints can find it — a Sprint Overview status cell is enough. Edit that one cell of the sprint's existing row and leave every other column as authored, because the column set is authored per plan. A cell value looks like this:

```markdown
✅ COMPLETE — Verdict PASS, 7/7 tasks. `{ABBREV}_S{NN}_BASE=5b53607`
```

`scripts/lint_verification_gates.py` registers Check 29 (`scripts/lint_gate_checks_plan.py`), which flags a `git diff` against a base that the sprint's first repo-touching task does not pin behind an empty-status precondition, or that no Recovery file records.

### 8.2 Scope every gate to the recorded base

> [!constraint] Every diff-scoped gate names the recorded base — `git diff $BASE -- <paths>`
> Never a bare `git diff`, never `git diff --name-only` with no operand, and never `git diff HEAD`. `HEAD` is not a synonym for the base: it moves with every commit the session makes, so a gate written against it measures the delta since the *last commit*, not since the sprint began. A session that commits mid-way silently erases all of its own earlier work from every later gate — the gates go green because the evidence left the diff, not because the defect left the tree.

`scripts/lint_verification_gates.py` registers Check 21 (`scripts/lint_gate_checks_commands.py`), which flags a `git diff` in Verification Commands or Success Criteria with no recorded-base operand or no `--` path scope. The accepted operands are a `$..._BASE` variable, a base placeholder such as `<base-sha>` or `{base_sha}`, and a literal commit id of 7 to 40 hex digits.

### 8.3 Path-scope with `-- <paths>`, not with an output filter

`-- <paths>` restricts the tree git **inspects**. A downstream filter only hides part of what git already inspected and reported. `git diff --name-only | grep '<dir>/'` walks the whole repository, so a sibling sprint's concurrent work under `<dir>` enters the result and is attributed here. The filter form also matches **text**, not paths. `--` matches paths.

Check 21 (§8.2) flags a diff that is scoped by an output filter instead of `--`.

### 8.4 A multi-sprint series records a series base once, at the first sprint

A plan whose sprints each pin their own base can gate each sprint's delta but has no way to diff the **series**: the release battery, the whole-refactor self-containment sweep, the "did we edit a file no sprint ever declared" scope test all need a single base predating the first sprint. Record a second name, `{ABBREV}_SERIES_BASE`, at the first task of the first sprint, and carry it verbatim into every later sprint's Recovery.

> [!constraint] First-to-touch — check for an already-recorded series base before minting one
> A task that pins the series base must not assume it ran first. Plans routinely declare sprints INDEPENDENT, and an independent sprint may legitimately execute **and commit** before the nominally-first one starts. Check before claiming the name: Grep for `{ABBREV}_SERIES_BASE` across the plan's Recovery files. If a prior sprint's Recovery already records a value, **adopt that value verbatim** — do not re-derive it. Only when none exists does this task's own HEAD become the series base.
>
> Re-minting a series base that already includes an independent sprint's commits silently narrows the whole-series sweep to the remaining delta: that sprint's added lines are never in the input, so the final cross-check is blind to them while every per-sprint gate still reports green. The failure surfaces at release, in the one gate meant to be the backstop.

Check 29 (§8.1) also covers the series base: a diff against a base name that no task pins and no Recovery file records is a finding.

### 8.5 A scope rule gets a positive test, not a list of forbidden directories

A scope rule states where a sprint **may** write. Testing it by enumerating the places it may not write permits every directory nobody thought to forbid — including directories that did not exist when the gate was authored. Assert the allowed set instead and require the complement to be empty. Only that form can fail for a reason nobody anticipated. A file-count gate asserts `wc -l` equals exactly N over a `--`-scoped diff.

`git diff <commit>` lists tracked paths only, so a never-staged new file never appears in it. A `--name-only` gate over a task that creates a file then reads empty, and a literal reading says the task produced nothing. Every `--name-only` scope, list or count gate therefore takes the union form, which adds the untracked files:

```bash
{ git diff --name-only $BASE -- <paths>; git ls-files --others --exclude-standard -- <paths>; } | sort -u
```

Keep the plain diff for a tracked-only check such as "this file is unchanged". A bare `git status --porcelain -uall` also lists new files, but it stops listing them once a mid-sprint commit holds them. `git add -N` stays the remedy for a pattern-presence content gate only (`gate-baseline-independence.md` §2).

`scripts/lint_verification_gates.py` registers Check 21 (`scripts/lint_gate_checks_commands.py`), which flags each unpinned shape below. Choosing the allowed set over a forbidden list stays a review judgment (Reviewer Check 077, step 5).

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
> { git -C <repo> diff --name-only $BASE -- <root>; git -C <repo> ls-files --others --exclude-standard -- <root>; } | sort -u | grep -vE '^(<allowed dir>)/'   # expect empty
> { git -C <repo> diff --name-only $BASE -- <paths>; git -C <repo> ls-files --others --exclude-standard -- <paths>; } | sort -u | wc -l   # expect exactly N
> ```
> The WRONG forms fail in both directions named in §8: the file-count and directory-filter forms false-FAIL on work the sprint never made, and the leak-pattern form misattributes added lines. The `--name-only` rewrites also join the untracked files, because the tracked diff alone cannot list a new file. The rewrite is mechanical.

#### Reviewer Check 077 — Diff-Scoped Gate Not Baseline-Pinned

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Any `git diff` in a task file's Verification Commands or Success Criteria MUST be scoped to a recorded baseline — the sprint's `{ABBREV}_S{NN}_BASE`, or `{ABBREV}_SERIES_BASE` for a whole-series battery — and MUST path-scope with `-- <paths>` rather than by filtering the command's output. A sprint whose first repo-touching task records no baseline at all fails this check for every gate in the sprint, including gates that name a `$..._BASE` operand that is never pinned anywhere. An unpinned gate reads the whole working tree: pre-existing uncommitted work counts against the sprint (false FAIL) and added lines the sprint never wrote are attributed to it (false PASS). A `--name-only` scope, list or count gate MUST also join `git ls-files --others --exclude-standard`, because `git diff <commit>` lists tracked paths only and a never-staged new file reads as absent.
- **Detection:**
  1. Grep the task file for `git diff`; every hit is a candidate.
  2. For each hit, assert **(a)** a `$..._BASE` operand is present, **(b)** a `--` path scope is present — a pipe into a path filter does not satisfy this, and **(c)** the operand names a base the sprint's first repo-touching task actually records. Any one absent → ERROR.
  3. Open that first repo-touching task and confirm it pins the base **before its first edit**, behind a clean-scope precondition (`git status --porcelain -- <write paths>` MUST be empty, else HALT), and records name + value in Recovery Key Findings. Pinned after an edit, or not recorded → ERROR.
  4. On a multi-sprint plan, confirm a `{ABBREV}_SERIES_BASE` is recorded once at the first sprint and **adopted verbatim** by later sprints. A later sprint that re-derives it from its own HEAD → ERROR.
  5. Inspect any scope gate that enumerates forbidden directories rather than asserting the allowed set; the enumerating form permits every directory nobody listed → ERROR.
  6. Inspect each `git diff --name-only` scope, list or count gate for a `git ls-files --others` union over the same paths. A bare `--name-only` gate, with no earlier `git add` of the task's new files, returns empty for a task that creates a file → ERROR.
  7. Where the change relocates content (a split, a move, a rename), require the per-hit lookup `git show <pinned base>:<pre-move path>` as the evidence for every `^\+` hit, classed as relocated or genuinely new (§8.9). A rewrite of the moved lines to turn the gate green, or a blanket waiver because the change is "just a move" → ERROR.
- **Enforced by:** `scripts/lint_verification_gates.py` registers Check 21 (`scripts/lint_gate_checks_commands.py`) for steps 2(a), 2(b) and 6, and Check 29 (`scripts/lint_gate_checks_plan.py`) for steps 2(c) and 3. Check 21 exempts a gate when an earlier command in the same file runs `git add`. Step 3's order inside one file, step 4, step 5 and step 7 stay review steps.
- **Finding template:**
```
[ERROR] Diff-scoped gate not baseline-pinned
File: {task file path} | Location: Verification Commands / Success Criteria step {n}
Issue: Gate runs `git diff` with {no recorded base | `HEAD` as the operand | no `--` path scope | a base no task in the sprint records | a `--name-only` listing with no `git ls-files --others` union, so a never-staged new file never appears}; it reads the whole working tree, so pre-existing uncommitted work fails the sprint (false FAIL) and added lines the sprint never wrote are attributed to it (false PASS)
Fix: Pin `{ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)` in the sprint's first repo-touching task behind an empty-`git status --porcelain -- <write paths>` precondition, record it in Recovery Key Findings before the first edit, and rewrite the gate as `git diff $BASE -- <paths>` per references/gate-diff-baseline-pinning.md §8, and join `git ls-files --others --exclude-standard -- <paths>` for a `--name-only` listing | Confidence: HIGH
```

### 8.6 A Base Is a Statement About One Moment; Commits After It Inside the Gate's Paths Break Every Delta Gate

A commit does not remove work from a `$BASE..worktree` diff. It moves that work from "uncommitted" to "committed", and both states sit inside the range. In a repository that a second session can write to, a whole-tree gate measures every writer's work, not this session's. Measured once: a pinned count of 6 files became 14, then 22, while a second session kept editing. Run as pinned, the gate failed a correct tree.

> [!constraint] Four operative points for a shared repository
> 1. **Pin every diff gate to an explicit path list from the start.** Assert on the union form over that list: `{ git diff --name-only $BASE -- <path list>; git ls-files --others --exclude-standard -- <path list>; } | sort -u | wc -l`. Print the whole-tree listing so a human can classify it, but do not assert on it.
> 2. **A clean `git status` is not evidence the gate scope is clean.** A clean tree after a bundled commit is the case where a whole-tree base diff is most wrong, because the committed foreign work is still inside the range.
> 3. **Expect the other session's edits to reach your own files.** Path-scoped gates stay correct. The commit then needs hunk-level staging (`git apply --cached` with a patch of only this session's lines), taken from a saved snapshot of the foreign diff.
> 4. **When a pinned count moves (6, then 14, then 22), ask what the diff range contains before asking what changed in your code.**

**Session-start base.** A sprint-wide base serves as a record. A session's own delta gates need a base pinned at that session's start. At each session's preflight, list the commits that landed after the sprint base inside the gates' pathspecs:

```bash
git log --oneline <sprint base>..HEAD -- <the gates' pathspecs>
```

- **Empty:** the sprint base is still exact for this session.
- **Non-empty:** pin a session-start base, record both bases, and name each intervening commit as an attributed delta for any gate that still compares against the sprint base.

**Resume compare.** On a resume after a pause, run every content compare the plan pins against the base over the write-set before the first dispatch. Do not wait for the gate that needs it. Two commands show the state: `git -C <repo> status --porcelain -- <write paths>` and `git -C <repo> diff --name-only $BASE -- <write paths>`.

**Per-file base.** A wanted user edit to one in-scope file after the pin is new truth, not drift. Pin a second ref for that one file only, and make every compare on that file take it. Prove the amended compare both ways: clean with the new ref, dirty with the old ref. Send a spec-delta flag to each downstream front door. Never revert the edit, and never replay that file at the old base.

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

**Before-command re-run.** At the same preflight, re-run the Before commands each task file carries and compare each reading with the task's `# pre-edit:` annotation. A changed reading is a structural finding. Three probes cover most drift:

- `git status --porcelain -- <write-scope>` MUST print nothing. A path it lists belongs to another writer.
- Every "does not exist yet" claim gets its own probe. Use `git check-ignore <path>` for an ignored path, or a `Glob` of the files the task creates.
- `git log --oneline --since=<scaffold date> -- <targets>` MUST print nothing. If it prints a commit, read that commit before dispatch.

A `pre-edit:` value that nobody executed is a prediction. When it predicts "exit 1", the After gate reads "exit 0" as success whether or not the edit happened. Run at least one Before block per distinct command shape at the session base, before CONFIRM. A family of near-identical batch tasks copies one wrong annotation into every brief, and one run for each shape catches it. The pair is under "One Before block for each command shape" below.

**Corpus count check.** At the same preflight, compare the live file count in the gated directory against the figure the plan carries. A mismatch (302 live against 299 recorded) is the early signal that a commit landed after the base.

Cross-references: §8.4 (the series base, which has the same first-to-touch hazard) and §8.1 (the clean-scope precondition, which also requires attribution per [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.5).

#### One Before block for each command shape

WRONG — trust the annotation and let the runners discover the error:
```
orchestrator -> re-measure census rows only -> dispatch 5 runners
runner 4     -> <audit> pre-edit: exit 0 (annotation said exit 1) -> reports an ISSUE mid-dispatch
```
CORRECT — run one Before block of each shape at the session base, then pin a gate that discriminates:
```
orchestrator -> <audit> --from 1 --to 18 -> exit 0, 18 warnings   # annotation says exit 1: structural finding
orchestrator -> pin the coverage gate on <worksheet> --missing-keys printing rows=0 in every brief -> CONFIRM
```
In the incident the ranged form exited 0 with warnings, while the whole-set form exited 1 on the same missing keys. An exit code that only warns cannot gate coverage. Pin the gate on an output that discriminates.

#### A peer commit moves HEAD under the close gates

A peer session that commits during this session moves HEAD under every gate that reads it. Before the first close gate, compare `git rev-parse HEAD` with the recorded base. Read `git status -sb` for upstream divergence.

When HEAD moved, run `git log --stat $BASE..HEAD` and attribute each commit to this session or a peer. Record an auto-commit as an observation with its hash, its time, its paths and whether it was pushed. Assert no cause for it. Never rewrite pushed history. Commit the remainder on top and say that a mid-flight snapshot shipped.

Re-scope each gate by what it asserts. A diff or pattern gate pinned to the base and scoped to the session's write paths still stands. An untracked count, an `add -N` registration and a "staged exactly N" gate are void. Record each as n/a with its reason.

> WRONG: the session starts at `<base>` and a peer commit lands. The close gates still read "staged exactly 3 files" and an untracked count. They pass or fail on the peer's state, and the report says clean.
>
> CORRECT: `git rev-parse HEAD` differs from `<base>`, and `git log --stat <base>..HEAD` names the foreign commit. The diff and pattern gates stay pinned to `<base>` and scoped to the session's write paths. The untracked-count and staged-count gates are recorded n/a with the reason.

#### Pin the session's own commit after it exists

Re-pinning a whole-subtree gate to "the latest HEAD" goes stale again while peers commit. Before this session's work is committed, gate against `HEAD` at gate time. Add the attribution check `git diff --name-only $BASE HEAD -- <write paths>`, which must print nothing. Never pre-pin an intermediate SHA into a brief.

Once a commit holds exactly this session's paths, pin the session's own commit. It may be the session's closeout or an auto-commit with a generic message. Accept either. Set `COMMIT` to its hash and run five checks:

1. `git merge-base --is-ancestor $COMMIT HEAD` returns rc 0.
2. `git diff --name-only $BASE $COMMIT^ -- <write paths>` prints nothing.
3. `git diff --name-only $COMMIT HEAD -- <write paths>` prints nothing.
4. `git diff --name-only $COMMIT^ $COMMIT -- <subtree>` lists the expected number of files.
5. The identifier battery runs over `git diff $COMMIT^ $COMMIT`.

> WRONG: the brief pins `<intermediate-sha>` as "the latest HEAD". A peer commits, and the pin names a commit that is no longer the tip.
>
> CORRECT: gate against `HEAD` at gate time with the attribution check empty. After the commit exists, pin `$COMMIT` with the five checks above.

#### Re-check the paths before a paid or outward step

A path check taken at session start describes the tree at session start. Immediately before a paid or outward step, re-run the path-scoped check. A headless matrix and a publish are two such steps. Run `git log --oneline <pinned commit>..HEAD -- <the plan's measured paths>`.

A changed path is a decision for the user, not an automatic HALT. Read the diff and let the user choose. Route the decision into the task, then dispatch.

> WRONG: the start-of-session check passed, so the paid matrix dispatches. A peer changed a measured path in between, and the matrix measures the wrong tree.
>
> CORRECT: the path-scoped `git log` runs immediately before dispatch and lists the peer's commit. The user reads the diff and decides. The decision goes into the task, and then the matrix dispatches.

#### Write a peer-touched literal with its reading time

A literal pinned from state another session can change is a reading, not a constant. HEAD, a dirty-path count and a peer's hunk are examples. Write the literal with its reading time and a note that a peer session is active. Put the live-wins clause beside it, as [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §5 describes.

At acceptance, re-read the state that any close-time plan depends on. A peer commit can remove the problem the plan was built for. A planned hunk-only commit of a shared file is one case.

> WRONG: the spawn prompt says "the tree has 14 dirty paths" with no time and no peer note. The runner trusts it after a peer committed.
>
> CORRECT: the spawn prompt says "14 dirty paths, read `<time>`, a peer session is active, a live measurement wins". At acceptance, the plan's dependency on that state is re-read.

#### Assert the state, not the delta, when the end state is what matters

A delta gate reads "the file gains 2 lines". An unrelated commit that already added one of those lines turns correct work into a +1 and fails it. A state assertion reads the end state, which no earlier commit can move. Keep a delta gate only when the delta itself is the claim.

> [!constraint] A delta gate becomes a state assertion
> WRONG — a delta gate, pinned to a scaffold-time reading:
> ```bash
> git diff --numstat $SESSION_START -- <file>   # expect 2 added; an unrelated commit already added one
> ```
> CORRECT — a state assertion over the end state:
> ```
> Grep  pattern='^{line}$'  path='<file>'  output_mode='count'   # expect 1
> ```

### 8.7 A base is a recorded value: recover it by carrying it, never by re-minting it

A baseline has a recording moment. It is not a command that returns the same answer whenever it runs. The value is pinned once, before the first edit (§8.1), and every later gate carries that value. Recovering a lost base by running `rev-parse` again is the way this section's failure starts.

> [!constraint] Three operands fail a diff gate, and the third fails silently in the passing direction
> | Operand | Why it fails |
> |---|---|
> | `git diff` (no operand) | Reads the whole working tree — pre-existing dirt counts against the session (false FAIL), and added lines the session never wrote get attributed to it (false PASS) |
> | `git diff HEAD` | `HEAD` moves with every commit the session makes; a mid-session commit erases all of the session's own earlier work from every later gate |
> | `$BASE` re-derived after the first edit | The base already contains the change under test, so the gate is blind to precisely the thing it was written to check |
>
> The third is the worst, because the first two can at least fail loudly on a dirty tree, while this one **fails silently and always in the passing direction**.
>
> WRONG — recover an unreachable baseline by re-deriving it:
> ```bash
> BASE=$(git -C <repo> rev-parse HEAD)          # ← now includes task 01's edit
> git -C <repo> diff $BASE -- <paths> | grep '^+' | grep '<pattern>'   # empty. Always.
> ```
> CORRECT — carry the recorded value forward, and never re-mint it:
> ```bash
> BASE=<recorded SHA>; git -C <repo> diff "${BASE:?unset}" -- <paths> | grep '^+' | grep '<pattern>'    # injected at dispatch from the recording task's Recovery entry
> ```

**A gate that cannot fail is worse than a missing gate**, because downstream readers consume it as evidence. Prove that the gate discriminates before trusting an empty result. Run each pattern once against input that genuinely carries the form and once against clean input, and record both readings. An undifferentiated pair invalidates the empty result.

The series corollary is one sentence. A sprint that re-mints `{ABBREV}_SERIES_BASE` after an earlier sprint has committed narrows the whole-series sweep to the remaining delta while every per-sprint gate stays green, so adopt an already-recorded series base verbatim and mint one only when none exists (§8.4).

### 8.8 A shared working tree shares one git index, so HEAD is not a stable base

Two sessions in one checkout share one git index. A `git add` or `git commit` in the other session sees this session's in-flight files exactly as it sees its own. A concurrent commit can sweep this session's uncommitted files into a commit, and every `HEAD`-relative gate then inspects a fraction of the real delta.

> [!constraint] Pin the base once, diff against it everywhere, check the log, and commit by pathspec
> WRONG — the shape every task-file Verification Command defaults to:
> ```bash
> git -C <repo> diff -- <file>  | grep -E '^\+' | grep -E '<pattern>'   # empty — over a third of the change
> git -C <repo> status --porcelain                                      # "M file" — says nothing about a commit
> git add -A && git commit -m "Commit"                                  # commits the OTHER session's files too
> ```
> CORRECT — pin the base once, diff against it everywhere, check the log, commit by pathspec:
> ```bash
> # Preflight (both repos): record the base and put it in Recovery / the spawn prompts
> git -C <repo> rev-parse HEAD      # → the session base
> git rev-parse HEAD
>
> # Every gate, every task: base-relative and path-scoped to THIS session's declared files
> git -C <repo> diff <base> -- <declared files> | grep -E '^\+' | grep -E '<pattern>'
> git -C <repo> diff --stat <base> -- <declared files>   # sanity: growth must match
>
> # When a runner reports a dirty tree: the commit is the invisible mutation
> git -C <repo> log --format='%h %ci %s' -3 --stat
>
> # Undeclared files in the base-relative diff: classify, never touch
> #   in the foreign commit's --stat list or the live foreign M set → out-of-session, not a finding
> #   in neither list → a genuine finding
>
> # Closeout: stage own paths, commit ONLY own paths
> git add <own paths>
> git commit --only -m "…" -- <own paths>
> git push
> ```

Three corollaries follow:

1. **A flag that names the foreign files expires between dispatches.** Route the flag as a procedure: measure `status --porcelain` live, subtract the declared set, and classify the remainder. Give the current list as an example, never as the contract.
2. **The runner's "Before" precondition cannot see this.** `git status --porcelain <file>` returning `M` reads as "my edit is present" whether `HEAD` moved or not. Only the orchestrator, which compares `diff --stat` growth against `wc -l` growth, holds both numbers.
3. **Push state matters for a repo others install from.** `git status -sb` with no `[ahead]` after a foreign commit means the published branch already carries the snapshot. The session's own push repairs it, so a session that closes COMPLETE without pushing leaves the half-edit live.

**The arithmetic tell.** A `diff --stat` that reports fewer insertions than the file's measured line growth is impossible unless `HEAD` moved. One measured instance read 80 insertions and 116 deletions for a file that grew from 184 to 436 lines. Re-based on the true session base, the delta was 267 insertions and 15 deletions.

The close-time form of the same hazard is "A peer commit moves HEAD under the close gates" in §8.6.

### 8.9 A `^\+` line is a line added to the diff, not content the change introduced

A gate that filters `^\+` reads the set of lines the diff reports. That set equals the lines the change introduced only when no content arrived by another route. A file split breaks the equality: every relocated line is an added line. Three `^\+` gates once fired on 269 lines that had shipped weeks earlier. Both obvious responses were wrong, in opposite directions.

> [!constraint] Test each hit against the pre-change revision and report the split
> WRONG — two shapes, and each hides a genuine violation. The first makes the gate green by changing the content it fired on. The second waives the whole result because the change is "just a move":
> ```
> gate fires on N lines inside the moved block
> → rewrite those lines
> # The move is no longer byte-identical. The hash proof is now false, and a
> # content change has been laundered through a commit described as a relocation.
>
> gate fires → "these are all from the split" → proceed
> # Never checked. A genuine new violation in the same diff is now invisible,
> # and so is a pre-existing one the move would have been the moment to catch.
> ```
> CORRECT — test each hit against the pre-change revision, and report the split:
> ```
> for each hit: git show <pinned-baseline>:<pre-move-path> | look for the exact line
>   present  → relocated, not introduced. Out of scope; record it as such.
>   absent   → genuinely new. Fix it before the change lands.
> ```

Three practices follow:

1. **Pin the baseline revision before the move,** in the same session. After the move the old path may not exist and `HEAD` may have advanced. The lookup needs a revision you recorded, never one you infer afterward.
2. **Report the classification, not just the pass.** "N hits, all proven pre-existing at `<sha>`" is evidence. "Gate clean" would be false, and "gate waived, it's a split" is not a result.
3. **A relocation is a legitimate moment to notice a pre-existing defect and an illegitimate moment to fix it.** File the defect. Never fold the fix into a move whose correctness rests on the content being unchanged.

The mirror-image hazard comes from the same place. A `^\+` gate cannot see an untracked file at all, so a split's new file needs `git add -N` before any diff gate runs. Without it the gate inspects zero bytes of the new file and returns a vacuous pass. [measurement-discipline.md](measurement-discipline.md) §8.7 governs that registration.

---

*Cross-references: [measurement-discipline.md](measurement-discipline.md) §8.7 (the input-set half of the same gate: untracked registration, the input-set assertion, the on-disk sweep, the known-bad dry run) · [gate-pre-edit-baseline.md](gate-pre-edit-baseline.md) (the recorded pre-edit **value**, independent of the recorded base **commit** this file governs) · [gate-baseline-independence.md](gate-baseline-independence.md) (a gate asserting a property of a diff needs a baseline copy the executor did not make) · [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.5 (attribution before a revert at a path this session did not write) · [verification-gates.md](verification-gates.md) (the family index).*
