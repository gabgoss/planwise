---
description: A citation names a copy and an instant, not just a file. Covers why a disputed reading is a question about which artifact was read — an installed copy, the committed tree, or the live working tree — and how line-number offsets settle it when content cannot; why a read whose subject may be concurrently written needs content hashes at both ends and both layers, because git status, diff --stat and mtime all fail to pin identity of content; why a concurrent writer also narrows what the session-close commit may include, and why a shipped script that errors against project data is compared with the development tree's copy before the data is blamed. Consult when two readings of one file disagree, when a read-only sweep runs while another session may be writing the tree, when committing in a tree another session shares, and when a script run from a pinned installed path fails on project data.
paths: {planwise_root}/{plans_dir}/**
---
# Artifact Identity — Which Copy Did You Read, and Did It Hold Still While You Read It

**Purpose:** Two incidents in which a reading of a file was correct about its content and unmoored from the thing it was a reading *of*. Any file that also exists as an installed or cached copy — a plugin's shipped references and the installed copies generated from them, a vendored upstream, a published build — routinely exists in at least three states at once: the installed copy a consumer has, the committed tree, and the dirty working tree. Mid-session they are all different. A citation that names content but not the copy it came from is therefore ambiguous by construction, and a sweep that reads a tree another session is actively writing produces citations that were true for an interval nobody recorded.

**Read this when** two agents disagree about what a file says or where, when a read-only sweep is about to run on a tree another session may be writing, when you are about to cite a line number that a downstream reader cannot re-verify, when committing at session close in a tree you may not own alone, and when a script run from a pinned installed path fails with an error that reads like a data problem.

Both defects are quiet in the same way: the reading itself is verifiable, and the disagreement it produces looks like a dispute about facts. It is not. It is a dispute about **which artifact**, and about **when** — and neither question can be settled by re-asserting the content.

Two neighbouring rules own the tree-naming half. [`verify-backlog-citation-freshness.md`](verify-backlog-citation-freshness.md) §12 requires a verification task to name the tree under test, to pin the tree state — commit, branch, dirty set — at both ends of its read window, and to compare pins before adjudicating a torn parallel read. [`verify-before-cite.md`](verify-before-cite.md) §9.B.20 requires a citation of current file state to record which tree and when. This file adds what those pins do not carry: the third copy and the offsets that identify it (§1), content identity rather than tree identity under a concurrent writer (§2), and the commit-scope consequence (§3).

## Table of Contents

- [1. Treat a Disputed File Reading as a Question About Which Artifact Was Read](#1-treat-a-disputed-file-reading-as-a-question-about-which-artifact-was-read)
- [2. When a Read's Subject May Be Concurrently Written, Pin Content Hashes at Both Ends](#2-when-a-reads-subject-may-be-concurrently-written-pin-content-hashes-at-both-ends)
- [3. Commit Only What This Session Wrote](#3-commit-only-what-this-session-wrote)
- [4. A Shipped Script That Errors Against Project Data Is Compared With the Development Tree Before the Data Is Blamed](#4-a-shipped-script-that-errors-against-project-data-is-compared-with-the-development-tree-before-the-data-is-blamed)
- [5. Two Readings of a Tool's Version Disagree: Name the Resolver](#5-two-readings-of-a-tools-version-disagree-name-the-resolver)

---

## 1. Treat a Disputed File Reading as a Question About Which Artifact Was Read

> [!constraint] Content alone cannot identify the source when several copies share the text; the offsets can, because independent edits move them apart
> "Not applied" is exactly what verifying a working-tree edit against the installed copy always reports.
>
> Mid-session an orchestrator told a task-runner that two approved edits were not on disk, quoting the unedited text at `:428` and `:436`. The runner returned a confident rebuttal: the edits *had* been applied, and the orchestrator had misread the installed copy rather than the development tree — supplying real evidence, since the installed copy genuinely carries that text at `:403` / `:408`. The rebuttal was specific, internally coherent, backed by a real measurement of a real file, and wrong about causation. Three measurements settled it:
>
> | Tree | Text at the disputed lines | Line numbers |
> |------|---------------------------|--------------|
> | Installed copy | old | `:403` / `:408` |
> | Development tree at `HEAD` (pre-session) | old | `:413` / `:418` |
> | Development tree, live, mid-session | old | **`:428` / `:436`** |
>
> The live numbering exists in only one of the three, because earlier edits in the same session had shifted that section down about fifteen lines. Neither the installed copy nor `HEAD` can produce those numbers. The runner's own preceding message corroborated it: a diffstat that had moved `25/2 → 27/4`, exactly the +2/+2 of the two rewords it claimed not to have made.
>
> ```
> WRONG — re-assert, or accept the more confident party:
>   A: "line 428 says X"    B: "no, you read the cache"    → unresolved, or resolved by tone
>
> CORRECT — measure all three candidates:
>   Grep  pattern=PATTERN  path=<installed-copy-path>       output_mode=content  -n=true   → :403 / :408
>   git show HEAD:<path> | grep -n PATTERN                                                  → :413 / :418
>   Grep  pattern=PATTERN  path=<live-working-tree-path>    output_mode=content  -n=true   → :428 / :436   ← only the live tree matches
> ```
>
> Four practices follow:
>
> - **Pin the tree in the claim itself.** `":436` in the live development tree" is falsifiable; "line 436" is not.
> - **Corroborate with an independent signal.** A diffstat, a file length or a `git status` line often settles causation even when line numbers are ambiguous. Here the diffstat's `25/2 → 27/4` was exactly the +2/+2 of the disputed edits.
> - **Verify session work against the development tree and consumer-facing behaviour against the installed copy.** They answer different questions, and the installed copy only moves at a release re-publish.
> - **A downstream verifier must state which tree it swept.** A sweep report that does not is ambiguous by construction.
>
> **The runner's judgement was otherwise correct, and a rule written only as a correction would teach the wrong lesson about it.** It re-read the file before acting and **declined to blindly re-apply** the edits, noting that the approved `old_string`s no longer existed and that a re-apply would either hard-fail or land a second time somewhere unintended. That is correct behaviour on any resume — verify current state before repeating an instruction. Only the causal story was wrong, and the causal story is the part that has to be corrected in the record so nobody inherits it.

This rule is for well-reasoned disagreements. A careless reading is caught by re-reading; a specific, coherent, evidence-backed reading of the wrong copy is caught only by asking which copy.

---

## 2. When a Read's Subject May Be Concurrently Written, Pin Content Hashes at Both Ends

> [!constraint] None of the cheap checks pins identity of content — only a content hash does
> **Trigger.** This section fires only where a concurrent writer is possible: another session open on the same checkout, a parallel dispatch layer sharing a tree, a machine-managed directory an upgrade may refresh. Where no writer can exist, one read is one read, and four hashes are ceremony. Where one can, a clean result without the pins is indistinguishable from a lucky one.
>
> Under a binding "Discovery is read-only" constraint, one of eleven runners reported mid-flight that a file in its zone had grown 223 → 239 lines *during its own execution*, and correctly re-read rather than trusting its baseline. Investigation found a concurrent, unrelated session actively authoring the development tree while eleven runners measured it — not a constraint breach by any runner, since the diff's content had nothing to do with the sweep's subject. The tree was moving fast enough that two consecutive orchestrator commands, seconds apart, disagreed: `git status --porcelain` reported 2 dirty files while `git diff --stat` reported 4; minutes later the same `--stat` had grown from 65 insertions to **285**, one file going +5 → +220. The stakes were unusual: the downstream consumer of that sweep was **forbidden from re-reading the trees** and consumed `file:line` citations only. That inverts the normal economics of staleness — ordinarily a stale citation is self-correcting because the next reader opens the file and notices; here **a wrong line number is permanently unresolvable by anyone downstream, ever.**
>
> | Check | What it misses |
> |---|---|
> | `git status` before the read | Says nothing about what happened *during* it |
> | `git diff --stat` before and after | Insertion counts can coincidentally match after offsetting edits; and it reports against `HEAD`, so it cannot distinguish "unchanged since I looked" from "changed twice" |
> | mtime | Cheap, but a write that restores identical bytes still bumps it, and a fast tool can write within a coarse timestamp granularity |
>
> ```
> orchestrator:  md5sum <files>          # before dispatch
> runner:        md5sum <files>          # FIRST action
> runner:        md5sum <files>          # LAST action before writing
> orchestrator:  md5sum <files>          # on return
> ```
>
> **The runner-side pair is not redundant with the orchestrator-side pair.** The orchestrator's bracket can be wide — dispatch latency, queueing — while the runner's brackets its actual reads. Both together bound the window tightly from outside and inside.
>
> **All four agreeing is proof the window was clean, and any disagreement names exactly which file moved.** Only that file's rows are marked provisional — instead of the whole output carrying a blanket "may be stale" caveat that a downstream consumer cannot act on. That granularity is the operational reason to run four hashes rather than to caveat the output.
>
> **The pins convert an accepted risk into a measured outcome.** Without them, a clean result is indistinguishable from a lucky guess, and the honest report must say "possibly stale" — which downstream must then treat as actually stale.
>
> **When a downstream consumer cannot re-read the source, "document the drift and move on" is the wrong instinct**, because the defect is unrepairable later. That is what justified a bounded delta re-sweep of only the changed files (~30K tokens) over both documenting it (free, and permanently defective) and re-running the affected tasks (~200K, re-deriving far more than had changed).

The tree-state pins in [`verify-backlog-citation-freshness.md`](verify-backlog-citation-freshness.md) §12.2 — commit, branch, dirty set, at both ends — identify *which tree* was read. They do not say whether the bytes of the files read held still between the two stamps. Run both: the tree pins answer "which tree", the content hashes answer "did it move".

§1 and §2 are both "a reading needs provenance", and they answer different questions. §1 asks **which copy** — an identity question, answerable after the fact by triangulation. §2 asks **whether it held still** — a stability question, answerable only by instrumenting the window in advance. The remedies have opposite time directions, one forensic and one prospective, and a merged section is applied at whichever moment the reader happens to be in.

---

## 3. Commit Only What This Session Wrote

> [!practice] A concurrent writer also invalidates the session-close commit convention
> The convention assumes the session owns the tree it commits. When another session's in-flight work is sitting dirty in the same tree, committing it hijacks uncommitted changes into a commit message describing unrelated work. **Commit only what this session wrote, and say plainly why the other tree was left alone.**

The mechanism is a pathspec commit, `git commit -m <msg> -- <this session's paths>`, because a bare `git commit` takes every entry another session staged. Run `git show --stat HEAD` afterward. It MUST list zero foreign paths.

This is a commit-scope consequence of §2's premise, not a general commit policy. The standing convention — `git add` specific files, never the whole tree — is [`session-execution-protocol.md`](session-execution-protocol.md) §7; this section adds only the reason a shared tree makes that convention load-bearing.

---

## 4. A Shipped Script That Errors Against Project Data Is Compared With the Development Tree Before the Data Is Blamed

> [!constraint] A config pin that resolves to an installed cache copy is a claim that the copy's behaviour still matches the project's live conventions
> The claim decays the moment a development-tree change lands that the installed copy predates. Nothing in the pin's syntax signals the drift. §1 asks which copy a reading came from. This section asks which copy a script came from.

The error read as a data problem. A backlog script run from the pinned installed path exited with `Error: Could not find '## Backlog Items' section.` Every file in the backlog directory was checked, and none carried that heading.

The index had already been migrated to a generated hub, overflow-leaf and archive-shard set that has no such heading. The installed scripts had never been taught to read that shape. The development tree already carried a shim that splices the heading onto legacy content and leaves generated content untouched. No release had shipped since the migration. Diagnosing the data would have sent the work the wrong way.

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
2. **Once skew is confirmed, run the development-tree scripts directly for the rest of the session.** Do not patch the installed cache, because an upgrade overwrites it. Do not block on a release cut mid-task.

**Pre-check.** Before editing any generated artifact by hand to satisfy a script, run the same script from the development tree. If it succeeds there, the data was never wrong.

---

## 5. Two Readings of a Tool's Version Disagree: Name the Resolver

> [!constraint] A tool's reported version belongs to the resolver that ran it, not to the machine
> A shell PATH lookup is one resolver. A driver script's own `find_executable()` that prefers a native binary is another. A package update can move one without moving the other. A precondition written as "the version is X" silently assumes one resolver.

A task pinned `<tool> --version # precondition: 2.1.267`. The shell tool resolved the package manager's shim and read 2.1.268. The driver script resolved a native executable and read 2.1.267. Both readings were correct. The validate gate ran on one build, and the design the session existed to measure had been pinned on the other. Nothing errored, and the gates reported a plausible result.

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

*Cross-reference: [`verify-backlog-citation-freshness.md`](verify-backlog-citation-freshness.md) §12.1–§12.3 (name the tree, pin tree state at both ends, compare pins before adjudicating) · [`verify-before-cite.md`](verify-before-cite.md) §9.B.20 (a cited current state records which tree and when) · [`dispatch-batch-gate.md`](dispatch-batch-gate.md) §3 (two runners' incompatible claims about one cached copy, adjudicated by reading the copy itself) · [`session-execution-protocol.md`](session-execution-protocol.md) §7 (git discipline at session close)*
