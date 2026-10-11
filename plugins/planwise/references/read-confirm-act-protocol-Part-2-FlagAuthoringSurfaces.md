---
description: Cross-task coordination flags continued — a Key Finding that names another session's file is re-filed as a flag, a flag that tells a task to produce something is a write-set delta reconciled against the Output line and write-target row, and an ordering flag is written against the pinned command it sequences. Split out of read-confirm-act-protocol.md §1.3 when that file neared the Read-tool token gate.
---

# READ-CONFIRM-ACT Protocol, Part 2 — Flag Authoring Surfaces

**Purpose:** Three §1.3 subsections, split out of [read-confirm-act-protocol.md](read-confirm-act-protocol.md) when that file neared the Read-tool token gate. §1.1-§1.6 stay on that anchor, which keeps the original filename. Each subsection extends §1.3's "Authoring the Flag (Spec Delta, Not Observation)" test to a surface the earlier text did not name: a finding recorded in the wrong table, a write-set, and a step order.

---

## A Key Finding That Names Another Session's File Is a Flag

> [!constraint] The test is who owns the file and who must act, not how important the observation sounds
> The test for a coordination flag is not "does this sound important" and not "did the runner write the word flagging". It is this: does the observation name a file or task that a different session owns, and must that session act on it? If yes, it is a flag. It belongs in the `Cross-Task Coordination Flags` table, because that table is the only thing closeout propagates. A bullet left in `Key Findings` never leaves Recovery.

Two shapes hide a flag:

- **A Key Finding with a downstream owner in it.** "X is incompatible with Y; reconciling Y is a separate rework" names Y's owner. Move it to the flags table with a consumer and a recommended action at the moment it is written, not at closeout.
- **A code comment that names other files.** "Those readers are not compatible with this layout; reconciling them is a separate rework" is a flag written into a medium no closeout reads. Keep the comment for the reader of the code. Write the flag row for the session that owns the readers.

**Example.** A session built an index generator. Its first task's runner recorded in Key Findings that the new 9-column layout does not match another script's current row shape, and that reconciling the other script was out of scope: "flagging it since it blocks any future integration of the two". The generator's source carried the same statement as a comment: the other readers locate the table by a section heading the generated files do not emit, so they are not compatible with the layout at all. The closeout propagated six flags to the next session. This was not one of them. The next session's runner rediscovered the missing heading while making a parser width-agnostic and fixed it unscoped. The orchestrator then found two more scripts with the same defect and routed the class mid-session. The rework happened as a surprise inside a task that had budgeted for something else.

> [!constraint] Re-file the observation in the table the closeout reads
> WRONG — the observation stays where the runner put it:
> ```
> Key Findings:
> - [<task-a>] The new 9-column layout does not match <script>'s row shape. Reconciling it
>   is out of scope — flagging it since it blocks any future integration.
> (closeout propagates the flags table; this bullet never leaves Recovery)
> ```
> CORRECT — the same observation, in the table the closeout reads:
> ```
> | Flag # | Source Task | Downstream Consumer | Observation | Recommended Action |
> | 7 | <task-a> | <task-b> (owns <script>) | Generated files carry no "<heading>" heading and use a 9-column layout; <script>'s reader requires the heading and reads legacy positions. | Splice the heading before parsing and read positions relatively — same fix as <parser>; verify against a header-cells fixture. |
> ```

**The orchestrator applies the same test.** A runner's Key Findings are a hypothesis about where each observation belongs. Before the next dispatch, re-file any bullet that names another session's file or task as a row in the `Cross-Task Coordination Flags` table. The test applies to every Recovery Key Finding and every runner status-block `KEY_FINDINGS` bullet. A related failure is a repair artifact produced and never routed. This one is the finding-side version: the observation is correct and recorded, and it still never reaches the session that must act.

## A Produce-Flag Is a Write-Set Delta

> [!constraint] The preflight reads a task's behaviour surfaces. A flag that makes the task produce something lands on its write surfaces
> The contradiction check in the Flag-Reconciliation Preflight reads steps, criteria and pins. It skips the task's write surfaces: the `**Output:**` line, the orchestration's write-target row and the sprint plan's write-set. A flag that says "file an item" is invisible to the first set and contradicts the second.

**Example.** A task was scaffolded with an `Output:` line naming one new backlog item "if the memo earned it", and the orchestration's write-target row said the same. Over the next two days three upstream closeouts each routed a flag into the task file reading "Backlog item to file". The orchestration's own flag summary said "Two backlog items for task 3". The preflight ran as written. None of the flags contradicted a step: step 3 says "file the Phase-2 item", and filing two more items does not contradict it. The contradiction sat in the `Output:` line, the write-target table and the sprint write-set, none of which the checklist names. The orchestrator noticed after task 2. A runner dispatched on the literal `Output:` line would have filed one item and left two flags landed as nothing, or filed three items outside its declared write-set. The layer's write-target intersection table would have been wrong either way.

> [!constraint] Add the write-set to the reconciliation targets
> WRONG — reconcile flags against steps, criteria and pins, and accept the `Output:` line as scaffolded:
> ```
> Flag (upstream 1):  "Backlog item to file: <gap A>"
> Flag (upstream 2):  "Backlog item to file: <gap B>"
> Task Output line:   "... one new item (if the memo earned it) ..."
> Step 3:             "If the memo recommends any promotion: file <item> ..."
> Preflight: no step contradicted -> PASS -> dispatch on the one-item Output line
> ```
> CORRECT — add the write-set to the reconciliation targets:
> ```
> For each routed flag: does it name an artifact the task must WRITE?
>   yes -> compare against Output line + orchestration write-target row + sprint write-set
>          mismatch -> structural finding, Option A / Option B, before CONFIRM
>   no  -> the existing step / criterion / pin check applies
> ```

- **The write-set is a contract surface.** The layer intersection table is computed from the `Output:` lines. A flag that adds an output silently changes a table the orchestrator already verified as empty.
- **"File an item" is a spec delta even when no step forbids it.** The spec-delta test applies to the write-set too.
- **Count the produce-verbs across the routed flags before CONFIRM.** Use `Grep` over the task file's Pre-Known section for `item to file|file a|write a|create`, and compare the count with the `Output:` line's artifact count. A mismatch is the finding. A match is one line of evidence in the preflight's Change Log row.

**Applies to** any DELEGATED session whose task files received flags from a closeout after their scaffold date, where the flag's verb is "file", "write", "create" or "append". It also applies to sprint plans whose write-set table was written before the carried-forward flags that feed the same tasks. The write-target intersection check (Reviewer Check 083 in `scaffolding-hygiene-Part-2-DerivationAndParallelism.md` §17) re-reads the flags routed after the table was written.

## An Ordering Flag Reads the Pinned Command First

> [!constraint] An ordering flag is a claim about two steps' dependencies. Read the pinned command before writing "X before Y"
> "Before staging" asserts that the earlier step does not depend on staging. The author wrote the flag from the intent and did not open the pinned command to see what it consumed.

**Example.** An upstream session closed with a flag to a downstream task: no compiler has ever checked the 40 helper files, so run the task's optional type-check step FIRST, before staging, so a helper-layer type error surfaces as its own finding rather than inside the validate gate's output. The downstream task's type-check step, already scaffolded, pinned its command against the **staged** copy: `tsc --noEmit -p <staged-lab>/plugin/tsconfig.json`. That path exists only after the staging step runs. The flag and the step could not both hold. The receiving orchestrator caught it at READ and surfaced it as a structural finding with an Option A / Option B gate. The user chose a redefinition: stage, then type-check, then validate, then checker. That met the flag's intent without touching the pinned command. The redefinition went into the task file as a binding spec delta and into Recovery's scope-expansion table with its approval reference.

> [!constraint] State the order against the dependency, and keep the intent
> WRONG — order stated from intent, dependency unread:
> ```
> flag: "run the type-check gate FIRST, before staging"
> step 6 (already scaffolded): tsc -p <staged-lab>/plugin/tsconfig.json
>        ^ produced by step 2 (stage), so the flag cannot be executed as written
> ```
> CORRECT — order stated against the dependency, intent kept:
> ```
> flag: "run the type-check gate immediately after staging and before validate, so a
>        helper-layer type error surfaces as its own finding; step 6's pinned path is
>        produced by step 2"
> ```

- **Before writing "run X before Y", read X's pinned command and ask what Y produces.** If X consumes anything Y creates, the flag needs another shape. Either "run X immediately after Y and before Z" (the intent, restated against the real dependency), or "run X against the source tree's copy of the config" (a different command, which the flag must then pin).
- **State the intent beside the order.** "So a helper-layer type error surfaces as its own finding" let the receiver resolve the contradiction without guessing. An order with no reason leaves the receiver choosing between two literal readings.
- **The receiver's remedy is a spec delta, not a quiet reorder.** A contradiction between a binding flag and a task step is a Phase-1 structural finding. Surface it, get the choice, write the resolved order into the task file with the approval reference, and let the runner execute one unambiguous sequence.

**Applies to** authoring a cross-session flag that sequences a downstream task's steps, and to the receiver's preflight: a flag that contradicts an Execution Step's pinned command is a structural finding for the CONFIRM block, not a reorder to apply silently. It covers any "do X first" instruction where X's command carries a path, port or artifact that a later step creates.
