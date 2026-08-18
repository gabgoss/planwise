---
description: When to use the dedicated file tools (Read/Grep/Glob/Edit/Write) versus the shell, and the closed list of file-operation verbs a scoped doctrine forbids.
---

# Native Tool Use

An agent with dedicated file tools — one that reads, searches, and edits through
those tools instead of shelling out for the same act — produces reviewable,
individually-permissioned steps: each call names one file and one intent, so a
human watching the tool-call stream can see exactly what changed and why. A
shell command that reads or edits a file collapses that visibility: a pipeline
welding three unrelated probes behind `&&` is unreviewable at a glance, and a
destructive step buried mid-chain is effectively invisible in the permission
prompt — the one place a human can still stop it.

This doctrine is **scoped**, not a blanket shell prohibition. It draws one
line: file-tree reads, searches, and edits route through the dedicated tools;
everything else — git, build/test/lint, database clients, interpreters,
authoritative counts, directory/file management with no tool equivalent —
stays in the shell, because that is where those acts belong. A shell command
whose input is a git diff, a database, or a running process is never a
substitution target: no dedicated file tool covers it.

---

## The Tool Map

| Need | Use | Notes |
|------|-----|-------|
| View a file, or a bounded range of it | **Read** | Pass `offset`/`limit` for a range instead of paging through the whole file. |
| Find text across files | **Grep** | Supports regex, glob filtering, and multiple output modes. |
| Find files by name or path pattern | **Glob** | Sorted by modification time; works at any codebase size. |
| Change part of an existing file | **Edit** | Exact string match; read the file first so the edit has context. |
| Create a new file, or fully replace one | **Write** | Overwrites what's there — read first if the file already exists. |

These four cover the acts a file-operation shell command is usually reached
for: viewing, searching, locating, and changing. When one of them covers the
act exactly, it is the correct call — not the shell command that produces the
same output.

This doctrine covers *which* tool to reach for. Once the tool is `Read`, the
strategy for handling a file too large to read in one call — paging by
`offset`/`limit`, deciding when a partial read is enough — is a separate,
deeper concern: see the read-gate ladder at `references/session-context-budget.md`
§ *Read Gates and Large-File Read Tactics* and the large-file token ladder at
`references/task-content-fidelity.md` §9.A.8.

---

## Where the Shell Is Correct

The dedicated tools do not replace the shell generally — only for file-tree
reads, searches, and edits that a tool already covers exactly. The classes
below have no tool equivalent and stay in the shell:

- **git**, and anything piped from git's output — `git diff`, `git status`,
  `git log`, a search or count chained after any of them. The input there is
  git's own output, not a file tree, so no dedicated tool applies.
- **Build, test, and lint invocations** — a project's own test runner, linter,
  or build command. These have no tool equivalent; a doctrine that tried to
  forbid them would be attacking the wrong target.
- **Database clients and other interpreter CLIs** — a SQL client run against a
  file of statements, a language interpreter run against a script. The input
  is a database or an interpreter, not a file tree.
- **The `wc -l` / `wc -c` family**, for an authoritative line or byte count.
  No dedicated tool produces an authoritative count; a partial or paginated
  read of a large file can under-report, so the shell count is the correct
  instrument here, not a workaround.
- **`mkdir -p`**, for directory creation, and **`mv`**, for moving or
  archiving a file. Neither has a dedicated-tool equivalent.
- **Tool-permission and allowlist configuration** that names a shell binary —
  documenting that a command is a granted capability is not an instruction to
  use it in place of a dedicated tool.
- **Interpreter and environment discipline** — using the explicit interpreter
  an environment provides, activating a virtual environment, or reporting the
  exact command that was run and the exact error it produced. No dedicated
  tool selects an interpreter or activates an environment.

A read that happens mid-pipeline, consuming another command's output rather
than a file tree directly, is likewise legitimate: the object being searched
is a stream of command output, not a file on disk.

---

## Forbidden Verbs for File Operations

For the acts the tool map covers — viewing a file, searching text, listing or
finding files, changing a file — the following verbs are a closed list,
forbidden **only** in that role, because a dedicated tool covers the same act
exactly:

- **`cat`** — reading a file's contents. Use **Read**.
- **`cp`** — duplicating a file's contents in place of writing it via a tool
  call. Use **Read** then **Write**.
- **`sed`** — reading or rewriting a file's contents by pattern. Use **Read**
  to view, **Edit** to change.
- **`awk`** — extracting or transforming file content. Use **Read** or
  **Grep**.
- **`head`** / **`tail`** — reading a bounded range of a file. Use **Read**
  with `offset`/`limit`.
- **`find`**, run against a file tree to locate files by name — use **Glob**.
- **`ls -R`**, a recursive directory listing used to locate files — use
  **Glob**.
- Bare **`cd`**, used to change the working directory before further file
  operations — see [Paths, Not `cd`](#paths-not-cd) below.

### Named Exceptions

The list above is closed, and each exception below is named because it falls
outside the tool map's coverage, not because the list is soft:

1. **A stream consumer after a genuine shell pipe.** A verb from the list
   above, appearing immediately after a real pipe from another command's
   output — `git diff | grep …`, a build tool's output piped to a filter — is
   reading command output, not a file tree. The exception is about the input
   source, not the verb: the same verb applied directly to a file on disk is
   still forbidden.
2. **`tail -f`** (or an equivalent "follow" flag), for watching a live or
   growing output stream. No dedicated tool watches a stream; this is not a
   bounded-range read the tool map covers.
3. **`mkdir -p`**, for directory creation — restated here because it can look
   like a forbidden-list neighbor of `find`/`cd` at a glance; it is Legitimate
   per the shell-is-correct list above, not an exception carved out of the
   forbidden list.

A shell read that lands mid-pipeline and satisfies a tool's own
read-before-edit precondition is a recognized, legitimate way to have read a
file — the doctrine above narrows *which* verbs and *which* input source are
in scope, not whether the shell may ever touch a file at all.

---

## Paths, Not `cd`

`cd` mutates working-directory state that persists into later commands in the
same session, which makes every subsequent relative path dependent on a step
that is easy to lose track of. Two mechanisms avoid it entirely:

- **Absolute paths** for any command run from the project's own working tree.
- **A path-scoping flag** (for example, git's own `-C <path>` option) to run a
  command "as if" started in another directory, without leaving the shell's
  actual working directory there. This is git's own built-in mechanism for
  reaching into a nested repository or subdirectory without a `cd`.

Destructive operations in particular should stand alone in their own command
rather than being chained behind a `cd` and other setup — a step buried in a
longer chain is effectively invisible in the one place a human can still stop
it.

---

## The One Sanctioned Count: `wc -l`

Line counts are the one place a shell command is not merely tolerated but
*required*: no dedicated tool reports an authoritative line count for a file,
and a paginated or partial read can silently under-report one for a large
file. Any rule or gate that needs a trustworthy line count should specify
`wc -l` (or `wc -c` for bytes) explicitly, run against the file on disk —
never inferred from where a paginated read happened to stop.

---

## The Content-Anchor Doctrine

A line number observed once — in a read, a search result, or a prior
conversation — is a hint, not an address. Files change between the moment a
line number is recorded and the moment it is used, and multiple independent
measurements of the same location routinely disagree. Locate an edit target
by its content instead: search for the surrounding symbol, heading, or
quoted sentence, and treat any accompanying line number as a starting point
to confirm, not a coordinate to trust blindly. This is native-tool-adjacent
doctrine — the dedicated search tool is what performs the re-anchoring — and
it applies whether the original hint came from a tool call or from prose.

---

## Applying This Doctrine

None of the above forbids git-piped searches, the `wc -l`/`wc -c` family,
directory or file management with no tool equivalent, build/test/lint
invocations, documentation of which shell commands a workflow is permitted to
run, or interpreter/environment discipline — all of those stay exactly where
they are. The scope is narrow and deliberate: when the object being viewed,
searched, or changed is a file on disk, and a dedicated tool already covers
that exact act, use the dedicated tool instead of a shell command that
produces the same result with less reviewability.
