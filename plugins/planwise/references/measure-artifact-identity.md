---
description: A citation names a copy and an instant, not just a file. Covers why a disputed reading is a question about which artifact was read — an installed copy, the committed tree, or the live working tree — and how line-number offsets settle it when content cannot; why a read whose subject may be concurrently written needs content hashes at both ends and both layers, because git status, diff --stat and mtime all fail to pin identity of content; why a concurrent writer also narrows what the session-close commit may include; why a shipped script that errors against project data is compared with the development tree's copy before the data is blamed, and why a clean refusal from that pinned copy is a claim about the copy; and why two readings of a tool's version that disagree must each name the resolver that produced them. Also covers why a claim about installed-copy behaviour is measured on the comparer that decides the outcome on that path, why an init-time plugin gate proves which plugin loaded and not which files the run executed, and why a stray artifact in an installed tree is dated against its install before a fix layer is chosen. Consult when two readings of one file disagree, when a read-only sweep runs while another session may be writing the tree, when committing in a tree another session shares, when a script run from a pinned installed path fails on project data, when two readings of a tool's version disagree, and when a lab or defect report makes a claim about which copy, which comparer or which writer.
consult-when: Two readings of one file disagree, a read-only sweep runs while another session may be writing the tree, or a session-close commit lands in a shared tree — triangulate line numbers across the installed copy, `HEAD` and the live tree; pin content hashes at both ends and both layers; commit only what this session wrote, and a shipped script run from a pinned installed path errors against project data or prints a clean refusal — check the pin's tag distance, compare the development tree's copy before blaming the data, and name the copy beside every recorded reading, and two readings of a CLI's version that disagree — name the resolver beside each number and pin from the binary the subject runs, and a "will an installed copy read as customized" claim answered by one comparison helper — trace the deciding call and measure every comparer on it (§6), and a lab or arm matrix that measures a plugin from a scratch copy — check the runtime paths, not only the init gate (§7), and a report that a stray file is present in an installed tree — date it against its install and read the upstream copy before choosing the fix layer (§8)
paths: {planwise_root}/{plans_dir}/**
---
# Artifact Identity — Which Copy Did You Read, and Did It Hold Still While You Read It

**Purpose:** A reading of a file can be correct about its content and still be unmoored from the copy and the instant it was a reading *of*. Any file that also exists as an installed or cached copy — a plugin's shipped references and the installed copies generated from them, a vendored upstream, a published build — exists in at least three states at once: the installed copy a consumer has, the committed tree, and the dirty working tree. Mid-session they are all different. A citation that names content but not the copy it came from is therefore ambiguous by construction. A sweep that reads a tree another session is actively writing produces citations that were true for an interval nobody recorded.

**Read this when** two agents disagree about what a file says or where, when a read-only sweep is about to run on a tree another session may be writing, when you are about to cite a line number that a downstream reader cannot re-verify, when committing at session close in a tree you may not own alone, and when a script run from a pinned installed path fails with an error that reads like a data problem.

The reading itself is verifiable, so the disagreement it produces looks like a dispute about facts. It is a dispute about **which artifact** and about **when**, and re-asserting the content settles neither question.

Two neighbouring rules own the tree-naming half. [`verify-backlog-citation-freshness.md`](verify-backlog-citation-freshness.md) §12 requires a verification task to name the tree under test, to pin the tree state — commit, branch, dirty set — at both ends of its read window, and to compare pins before adjudicating a torn parallel read. [`verify-before-cite.md`](verify-before-cite.md) §9.B.20 requires a citation of current file state to record which tree and when. This file adds what those pins do not carry: the third copy and the offsets that identify it (§1), content identity rather than tree identity under a concurrent writer (§2), and the commit-scope consequence (§3).

## Table of Contents

- [1. Treat a Disputed File Reading as a Question About Which Artifact Was Read](#1-treat-a-disputed-file-reading-as-a-question-about-which-artifact-was-read)
- [2. When a Read's Subject May Be Concurrently Written, Pin Content Hashes at Both Ends](#2-when-a-reads-subject-may-be-concurrently-written-pin-content-hashes-at-both-ends)
- [3. Commit Only What This Session Wrote](#3-commit-only-what-this-session-wrote)
- [4. A Shipped Script That Errors Against Project Data Is Compared With the Development Tree Before the Data Is Blamed](#4-a-shipped-script-that-errors-against-project-data-is-compared-with-the-development-tree-before-the-data-is-blamed)
  - [4.1 A Clean Refusal From the Pinned Copy Is a Claim About That Copy](#41-a-clean-refusal-from-the-pinned-copy-is-a-claim-about-that-copy)
- [5. Two Readings of a Tool's Version Disagree: Name the Resolver](#5-two-readings-of-a-tools-version-disagree-name-the-resolver)
- [6. Measure the Comparer That Decides the Outcome on the Path in Question](#6-measure-the-comparer-that-decides-the-outcome-on-the-path-in-question)
- [7. An Init-Time Plugin Gate Proves Which Plugin Loaded, Not Which Files the Run Executed](#7-an-init-time-plugin-gate-proves-which-plugin-loaded-not-which-files-the-run-executed)
- [8. Date a Stray Artifact Against Its Install Before Choosing the Fix Layer](#8-date-a-stray-artifact-against-its-install-before-choosing-the-fix-layer)

---

## 1. Treat a Disputed File Reading as a Question About Which Artifact Was Read

> [!constraint] Content alone cannot identify the source when several copies share the text; the offsets can, because independent edits move them apart
> "Not applied" is exactly what verifying a working-tree edit against the installed copy always reports. When two readings of one file disagree, measure every candidate copy instead of re-asserting a reading. Edits earlier in a session shift line numbers in the live tree only. A numbering that exists in one copy alone therefore names the copy that was read.
>
> WRONG — re-assert, or accept the more confident party:
> ```
> A: "line 428 says X"    B: "no, you read the cache"    → unresolved, or resolved by tone
> ```
> CORRECT — measure all three candidates:
> ```
> Grep  pattern=PATTERN  path=<installed-copy-path>       output_mode=content  -n=true   → :403 / :408
> git show HEAD:<path> | grep -n PATTERN                                                  → :413 / :418
> Grep  pattern=PATTERN  path=<live-working-tree-path>    output_mode=content  -n=true   → :428 / :436   ← only the live tree matches
> ```

Four practices follow:

- **Pin the tree in the claim itself.** `":436` in the live development tree" is falsifiable. "Line 436" is not.
- **Corroborate with an independent signal.** A diffstat, a file length or a `git status` line often settles causation even when line numbers are ambiguous.
- **Verify session work against the development tree and consumer-facing behaviour against the installed copy.** They answer different questions, and the installed copy only moves at a release re-publish.
- **A downstream verifier must state which tree it swept.** A sweep report that does not is ambiguous by construction.

**Re-reading before re-applying stays correct even when the causal story is wrong.** On any resume, verify current state before repeating an instruction. An approved `old_string` that no longer exists either hard-fails or lands a second time somewhere unintended. Correct the causal story in the record, so nobody inherits it.

This rule is for well-reasoned disagreements. A careless reading is caught by re-reading. A specific, coherent, evidence-backed reading of the wrong copy is caught only by asking which copy.

---

## 2. When a Read's Subject May Be Concurrently Written, Pin Content Hashes at Both Ends

> [!constraint] None of the cheap checks pins identity of content — only a content hash does
> **Trigger.** This section fires only where a concurrent writer is possible: another session open on the same checkout, a parallel dispatch layer sharing a tree, a machine-managed directory an upgrade may refresh. Where no writer can exist, one read is one read, and four hashes are ceremony. Where one can, a clean result without the pins is indistinguishable from a lucky one.
>
> | Check | What it misses |
> |---|---|
> | `git status` before the read | Says nothing about what happened *during* it |
> | `git diff --stat` before and after | Insertion counts can coincidentally match after offsetting edits; and it reports against `HEAD`, so it cannot distinguish "unchanged since I looked" from "changed twice" |
> | mtime | Cheap, but a write that restores identical bytes still bumps it, and a fast tool can write within a coarse timestamp granularity |
>
> WRONG — a cheap check stands in for content identity, and two of them disagree seconds apart:
> ```
> git status --porcelain     # 2 dirty files
> git diff --stat            # 4 files; minutes later 65 → 285 insertions
> ```
> CORRECT — four content-hash pins bracket the read window, and the compare names each file that moved:
> ```
> orchestrator:  python <plugin_root>/scripts/snapshot_hashes.py take --label before-dispatch --out <dir>/1.json <files>
> runner:        python <plugin_root>/scripts/snapshot_hashes.py take --label runner-start --out <dir>/2.json <files>   # FIRST action
> runner:        python <plugin_root>/scripts/snapshot_hashes.py take --label runner-end --out <dir>/3.json <files>     # LAST action before writing
> orchestrator:  python <plugin_root>/scripts/snapshot_hashes.py take --label on-return --out <dir>/4.json <files>
> orchestrator:  python <plugin_root>/scripts/snapshot_hashes.py compare <dir>/1.json <dir>/2.json <dir>/3.json <dir>/4.json
> ```

**The runner-side pair is not redundant with the orchestrator-side pair.** They are the two layers of the bracket. The orchestrator's bracket can be wide — dispatch latency, queueing — while the runner's brackets its actual reads. Both together bound the window tightly from outside and inside.

**All four agreeing is proof the window was clean, and any disagreement names exactly which file moved.** Only that file's rows are marked provisional — instead of the whole output carrying a blanket "may be stale" caveat that a downstream consumer cannot act on. That granularity is the operational reason to run four hashes rather than to caveat the output.

**The pins convert an accepted risk into a measured outcome.** Without them, a clean result is indistinguishable from a lucky guess, and the honest report must say "possibly stale" — which downstream must then treat as actually stale.

**When a downstream consumer cannot re-read the source, "document the drift and move on" is the wrong instinct.** A wrong line number is then permanently unresolvable by anyone downstream, so the defect is unrepairable later. Re-sweep only the changed files, as a bounded delta. Documenting the drift is free and permanently defective, and re-running the affected tasks re-derives far more than changed.

The tree-state pins in [`verify-backlog-citation-freshness.md`](verify-backlog-citation-freshness.md) §12.2 — commit, branch, dirty set, at both ends — identify *which tree* was read. They do not say whether the bytes of the files read held still between the two stamps. Run both: the tree pins answer "which tree", the content hashes answer "did it move".

§1 and §2 are both "a reading needs provenance", and they answer different questions. §1 asks **which copy** — an identity question, answerable after the fact by triangulation. §2 asks **whether it held still** — a stability question, answerable only by instrumenting the window in advance. The remedies have opposite time directions, one forensic and one prospective, and a merged section is applied at whichever moment the reader happens to be in.

---

## 3. Commit Only What This Session Wrote

> [!practice] A concurrent writer also invalidates the session-close commit convention
> The convention assumes the session owns the tree it commits. When another session's in-flight work is sitting dirty in the same tree, committing it hijacks uncommitted changes into a commit message describing unrelated work. **Commit only what this session wrote, and say plainly why the other tree was left alone.**
>
> WRONG — stage by path, then commit bare, which takes every entry another session staged:
> ```
> git add <this session's paths>
> git commit -m <msg>
> ```
> CORRECT — commit by pathspec, then check the commit's scope:
> ```
> git commit -m <msg> -- <this session's paths>
> git show --stat HEAD     # MUST list zero foreign paths
> python <plugin_root>/scripts/record_checks.py commit-scope --repo <repo> --declared <declared paths>
> ```

`record_checks.py commit-scope` makes the `git show --stat HEAD` check mechanical. It exits 1 and names each path the commit holds outside the declared set.

This is a commit-scope consequence of §2's premise, not a general commit policy. The standing convention — `git add` specific files, never the whole tree — is [`session-execution-protocol.md`](session-execution-protocol.md) §7. This section adds only the reason a shared tree makes that convention load-bearing.

---

## 4. A Shipped Script That Errors Against Project Data Is Compared With the Development Tree Before the Data Is Blamed

> [!constraint] A config pin that resolves to an installed cache copy is a claim that the copy's behaviour still matches the project's live conventions
> The claim decays the moment a development-tree change lands that the installed copy predates. Nothing in the pin's syntax signals the drift. §1 asks which copy a reading came from. This section asks which copy a script came from.

The error reads as a data problem. The data has moved to a shape the installed copy predates, and the development tree already reads that shape. Diagnosing the data sends the work the wrong way.

> [!constraint] Confirm version skew, then resolve scripts from the development tree
> WRONG — trust the installed cache's error as a statement about the data:
> ```
> python <installed-cache>/scripts/parse_backlog.py --config <project>/config.yaml --id 136
> # Error: Could not find '## Backlog Items' section.
> # -> conclude the index file is malformed, start editing it by hand
> ```
> CORRECT — confirm version skew, then resolve scripts from the development tree:
> ```
> compare config.yaml plugin_version  with  <dev-tree>/.claude-plugin/plugin.json "version"
> # if the dev tree is ahead, use ITS scripts for this session:
> python <dev-tree>/scripts/parse_backlog.py --config <project>/config.yaml --id 136
> ```

Two operative points follow.

1. **Compare before assuming the data is wrong.** When a project has both an installed plugin cache and its own development tree on disk, and a shipped script errors against current project data, compare the development tree's copy of the same script. A mismatch between the version in the project's config and the version in the development tree's plugin manifest is the fast confirmation.

   A matching version does not rule skew out. Two copies can carry the same version string and differ on the exact option in use. When the versions match and the error persists, `Grep` the option or symbol in both copies before you trust either one. `gate-instrument-proof-obligations.md` §10, "Real-path pitfalls", carries the worked case.
2. **Once skew is confirmed, run the development-tree scripts directly for the rest of the session.** Do not patch the installed cache, because an upgrade overwrites it. Do not block on a release cut mid-task.

**Pre-check.** Before editing any generated artifact by hand to satisfy a script, run the same script from the development tree. If it succeeds there, the data was never wrong.

### 4.1 A Clean Refusal From the Pinned Copy Is a Claim About That Copy

A pinned script can also fail without an error. A refusal, a route or a verdict prints cleanly, reads as a statement about the data, and names no copy.

> [!constraint] A clean refusal from a pinned installed copy is a claim about that copy
> A gate's verdict carries the version of the instrument that produced it. When the config pins an installed copy and the development tree is ahead, the verdict describes the installed copy. An error names its instrument. A well-formed refusal does not, so it passes review unread.
>
> WRONG — the installed copy refuses cleanly, and the refusal is recorded as the scorer's verdict on the tree. The reading names no copy:
> ```
> <installed>/scripts/score_backlog.py --route --id <id>   # route C, so the loop drops the item
> ```
> CORRECT — the pin's tag distance is read, the same scorer runs from both copies, and both readings are recorded with the copy named beside each:
> ```
> git -C <dev-tree> describe --tags --always               # <tag>-11-g<sha>: the tree is 11 commits past the pin
> <installed>/scripts/score_backlog.py --route --id <id>   # installed copy: route C
> <dev-tree>/scripts/score_backlog.py --route --id <id>    # development copy: route B
> ```

Three rules follow.

1. **Check the pin's tag distance before trusting a pinned gate.** One `git describe --tags --always` call shows whether the development tree is ahead. When it is, a verdict from the pinned copy needs a second reading from the development copy.
2. **A clean refusal does not prove the refusing copy is current.** An error names the instrument and a refusal does not.
3. **Name the copy beside every recorded reading.** A note that says "route C" without naming the scorer's copy cannot be re-derived once the pin moves.

---

## 5. Two Readings of a Tool's Version Disagree: Name the Resolver

> [!constraint] A tool's reported version belongs to the resolver that ran it, not to the machine
> A shell PATH lookup is one resolver. A driver script's own `find_executable()` that prefers a native binary is another. A package update can move one without moving the other. A precondition written as "the version is X" silently assumes one resolver.

Three consequences follow.

1. **A version precondition names the binary, not only the number.** "`<tool> --version` from the shell is X" and "the executable the driver selects is X" are two checks. Write the one each gate depends on.
2. **Pin from the binary the subject actually runs.** A version pin that gates later drift checks records the build that ran the probe, not the build a helper script happened to prefer.
3. **When two readings disagree, record both and say which gate used which.** The discrepancy is data. Discarding one reading as "wrong" loses the fact that two gates ran on different builds.

> [!constraint] Name the resolver beside the number
> WRONG — one number, resolver implicit:
> ```
> <tool> --version   # precondition: 2.1.267
> ```
> CORRECT — the binary each gate runs, and both readings when they differ:
> ```
> <tool> --version                 # shell PATH shim: 2.1.268 (the validate gate ran here)
> python driver/stage.py           # driver's find_executable(), native exe: 2.1.267 (the version pin records here)
> # differ -> record both; pin from the build that launches the lab
> ```

**Applies to** any precondition, pin or drift check keyed on a CLI's reported version where a package manager leaves a shim and a native executable side by side. It also applies to driver scripts with their own executable discovery that run beside shell-invoked commands in one session, and to reading a version-mismatch line in a session log.

---

## 6. Measure the Comparer That Decides the Outcome on the Path in Question

> [!constraint] Trace the call that decides, then measure every comparer on that path
> A session added a one-line `consult-when:` frontmatter key to every shipped reference. Six of them install into consumer `.claude/rules/`. The open question was whether an untouched installed copy, written before the key existed, would read as customized.
>
> The orchestrator measured a pre-session copy of 20 installed and descoped rules and found a removable subset. It saw `style_rules._has_edits` return False for both style rules. It recorded "22 of 22 refresh silently".
>
> The closeout review contradicted the record. The upgrade path `style_rules._reconcile_one` decides from `compare_installed`, which calls `_verdict`, and it never calls `_has_edits`. Measured on that path, both style rules returned `diverged`, so an untouched copy would be kept as customized. The record was retracted and the comparer fixed in the same session.
>
> WRONG — measure the first comparer that answers the question:
> ```
> _has_edits(shipped, old_copy)        # False → "refreshes silently"
> ```
> CORRECT — trace the deciding call, then measure every comparer on it:
> ```
> Grep "_reconcile_one|compare_installed|_verdict|_has_edits" style_rules.py
> _reconcile_one → compare_installed → _verdict(shipped, old_copy)   # diverged
> _has_edits(shipped, old_copy)                                       # False (duplicate path only)
> → record the result per comparer and per path
> ```

**Applies to** claims about installed-copy behaviour, upgrade dispositions, doctor verdicts and drift reports. It also applies to any "will X read as Y" question answered by calling one function. The risk is highest where the module holds more than one comparison helper, or where the claim reaches another session as measured.

---

## 7. An Init-Time Plugin Gate Proves Which Plugin Loaded, Not Which Files the Run Executed

> [!constraint] Check the runtime paths too, and remove the model's choice of path
> A headless matrix loaded the plugin from a hash-verified scratch copy made with `git archive`. Every run's `plugin_gate` passed on the init event. The fixtures lived inside a project whose instructions file names the plugin development tree.
>
> In all 3 workflow runs the model's first call, a `Skill` call, failed. The model then globbed the disk and found the development tree's plugin directory. It passed that path as the `Workflow` tool's `plugin_root` argument.
>
> The workflow agents ran `plan_build.py` from the development tree. That script imports `scaffold_plan.py`, and that file carried another session's uncommitted +3/-1 diff. The gate had verified the scratch copy while the run executed the other tree.
>
> WRONG — trust the init gate for the whole run:
> ```
> init.plugins planwise -> scratch copy -> plugin_gate PASS -> "the run measured <sha>"
> ```
> CORRECT — check the runtime paths too, and remove the choice:
> ```
> Grep each run's events for tool inputs naming a plugin path outside the scratch copy -> confound or VOID
> Run the fixture outside any repo that holds the plugin source, or drop path arguments the tool can resolve itself
> ```

Section 4 covers a shipped script that errors against project data. This section covers a path the model chose for itself.

**Applies to** any lab, probe or arm matrix that measures a plugin from a scratch copy while the source tree is reachable on disk. It also applies to any tool or workflow that takes a `plugin_root` or script path as an argument.

---

## 8. Date a Stray Artifact Against Its Install Before Choosing the Fix Layer

> [!constraint] A layer question that looks like the user's choice may be a fact nobody measured
> A backlog item reported `scripts/__pycache__/` inside the installed plugin and attributed it to packaging. It offered three fixes at three layers: the script, the handler invocation and packaging. An earlier backlog loop run skipped the item and asked the user to pick the layer, because nobody had dated the artifact.
>
> Two reads settled it. In the install cache, the `scripts/` directory was created at 21:13:51 and `scripts/__pycache__/` at 21:23:06, nine minutes later. The bytecode directory held 143 `.pyc` files running to a week later. The marketplace clone the installer copies from held 467 files and no `__pycache__`.
>
> The scripts wrote the bytecode while running from the install cache. A packaging exclude would have changed nothing. The fix is at the script layer: `sys.dont_write_bytecode = True` before the first sibling import, in every entry script.
>
> WRONG — infer the path from where the artifact sits:
> ```
> __pycache__ found in install cache -> "packaging ships it" -> exclude at packaging time
> ```
> CORRECT — date it, then check the source:
> ```
> install dir ctime 21:13:51, __pycache__ ctime 21:23:06   -> written after install
> marketplace clone: 467 files, no __pycache__             -> packaging is clean
> -> the runtime writes it -> fix the scripts
> ```

Three steps follow.

1. **Compare the artifact's creation time with its parent's.** A cache directory younger than its install was written after the install.
2. **Read the upstream copy as well.** Absence in the clone or archive the installer reads rules out the shipping path.
3. **Pick the layer that matches the writer.** A layer question that looks like a user's choice may be a fact nobody measured. Measure it before routing it to the user.

**Applies to** any defect report of the form "X is present in the installed or deployed tree". Bytecode, logs, lock files and caches are the usual cases.

---

*Cross-reference: [`verify-backlog-citation-freshness.md`](verify-backlog-citation-freshness.md) §12.1–§12.3 (name the tree, pin tree state at both ends, compare pins before adjudicating) · [`verify-before-cite.md`](verify-before-cite.md) §9.B.20 (a cited current state records which tree and when) · [`dispatch-batch-gate.md`](dispatch-batch-gate.md) §3 (two runners' incompatible claims about one cached copy, adjudicated by reading the copy itself) · [`session-execution-protocol.md`](session-execution-protocol.md) §7 (git discipline at session close)*
