---
description: A gate's output is evidence only after four independent obligations are discharged — it can fail, shown by a fixture that reproduces the defect and a run of the same probe on the unfixed artifact (A); it does not fail correct work (B); it can see the shape it counts (C); and it is pointed at the live subject as well as at fixtures (D); Reviewer Checks 087 and 088.
consult-when: A deliverable is a gate, guard, hook, linter or validation pass, or a criterion cites a gate run as proof — the gate can fail (A), does not fail correct work (B), sees the shape it counts (C), is pointed at the live subject (D); Checks 087 and 088; and a success signal must have run the real path — a dry run for an --apply control, a writer's exit 0, a shared version string, a both-raised differential, a native-tool stand-in, node --check on an ES module, a path form (Real-path pitfalls)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Instrument Proof Obligations (Four Things a Gate Proves Before Its Output Is Evidence)

**Purpose:** Split from `verification-gates.md` (the family index) on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gates.md §N` citation translates by filename alone.

**Read this when** a task's deliverable is a gate, a guard, a hook, a linter or a validation pass, an acceptance criterion cites a gate run as proof, or a bug-fix deliverable's criteria name no fixture that reproduces the defect, or a gate extracts identifiers, filters a search's output, or parses source text, or a success signal stands in for the real path: a dry run for an `--apply` control, a writer's exit 0, a version string, a differential over two readers, an in-process tool stand-in, a syntax check, or a path gate tested on synthetic paths.

## Table of Contents

- [10. The Instrument's Four Proof Obligations](#10-the-instruments-four-proof-obligations)

---

## 10. The Instrument's Four Proof Obligations

The runtime, verdict and baseline rules in `gate-runtime-boundary-evidence.md`, `gate-exit-verdict-and-smoke-reports.md` and `gate-diff-baseline-pinning.md` ask whether the right thing was measured. This section asks a prior question: **is the instrument itself sound?** A gate's output is evidence only after the gate has discharged four obligations, and they are **independent** — passing any one says nothing about the other three.

| Obligation | The question | Failure it admits |
|---|---|---|
| A | Can it fail at all? | A criterion already satisfied before the work starts |
| B | Does it fail *correct* work? | A gate measuring form, exerting pressure to reformat correct content |
| C | Can it see the shape it counts? | A single-line matcher against a multi-line idiom |
| D | Does a proven instrument mean a clean subject? | A fixture dry-run reported as if it were a live sweep |

> [!constraint] Obligation A — the gate must be able to fail
> ```
> WRONG  AC: "re-run the tool and confirm the open-item count equals the number of non-closed rows"
>          -> 17 open, 17 reported. PASS — and identically on unfixed code, because the
>             triggering rows were reworded as a workaround. It measured sanitised data.
> CORRECT AC: "run every parser on a clean row AND on a row containing a \| b;
>              require identical, correct column assignment"
>          -> fixed tree: PASS    unfixed tree: FAIL   # the FAIL proves the gate discriminates
> ```
>
> 1. **A criterion evaluated against live project data measures the data, not the code.** It is a regression guard, never evidence the fix works. Phrase at least one criterion against a **fixture that reproduces the defect**, and name the discriminating criterion.
> 2. **Run the same probe against the unfixed artifact** — the previous commit, the installed older version, a copy with the fix reverted — **and show it failing.**
> 3. **Run a reproduction recipe on the known-bad state before pinning it, and read the flag's implementation, not its name.** `--show-blocked` routes blocked items into the selectable list, so its "blocked by:" summary never prints. One `Grep` for the flag in the parser and its consumer settles what it does.
>
> **A criterion already satisfied at triage time is a finding, not a tick.** Record it with its reason. A criterion structurally incapable of failing again is a defect in the criterion. Prefer "demonstrably correct" to "demonstrably different": two outputs that merely differ can both be wrong.

> [!constraint] Obligation B — the gate must not fail correct work
> A gate must assert **the property you care about**, not a spelling of it. For a citation the property is **resolution**: the file exists at the path given, the section exists in it, no placeholder token remains. A typography pattern such as `{file}\.md §[0-9]+` scores 0 on a correct citation whose file name sits in backticks, the house style, and 1 on a citation to a file that does not exist. A spelling-tolerant pattern still checks only the shape. Only a check that reads the named file and confirms the heading fails a citation whose target moved.
>
> **The authoring test:** *what would a correct-but-differently-formatted artifact score?* If FAIL, the gate measures form. **Dry-run against a known-GOOD file in the house style, not only against known-bad.** **When a runner reports that it reformatted content to satisfy a gate, that is a gate-defect report, not a completion detail** — read it as one.

> [!constraint] Obligation C — the gate must be able to see the shape it counts
> A single-line pattern against a multi-line idiom undercounts: one sweep reported 14 sites where the real count was 64+2. Before trusting a pattern, **Count the idiom's ANCHOR and its CONTINUATION separately** (a large gap means the pattern is single-line and the idiom is not), and **Read one real instance before writing the pattern.** Prefer structure-independent matchers, in this order: a **multiline matcher**; better, a **structural check** that parses the file and walks its call nodes; for a mechanical rename, a **normalization diff** that undoes the rename and expects an additions-only diff.
>
> **Finding a defect class does not immunize you against it** — the sweep written to catch it can carry the same flaw. **Delegation corollary:** an orchestrator-supplied count is a **cross-check with halt-on-disagreement**, never the answer.

> [!practice] Obligation D — discrimination is not cleanliness
> A **Fixture dry-run** answers *can this gate tell bad from good?* A **Live sweep** answers *is the thing it guards actually clean?* Neither substitutes for the other: an empty sweep from an instrument nobody proved discriminating says nothing. The live sweep is the one acceptance criteria skip.
>
> 1. **Run both, in order, and report the two outputs separately.**
> 2. **Expect the live sweep to produce findings outside the item's file list**, and treat that as the deliverable working. A repair whose live sweep is clean on the first try is weak evidence the repair was needed.
> 3. **Classify hits before acting**, with a mechanical evidence-based discriminator where one exists. For a new checker, lint, scanner or guard, the live run also measures the instrument's precision on shapes no fixture author imagined: [`gate-fixture-provenance.md`](gate-fixture-provenance.md) §7.2 holds the classification and the accept or reject rules.
> 4. **Write the live sweep into the next gate-repair item's acceptance criteria**, phrased so fixtures cannot satisfy it: *"after landing, run one unfiltered sweep for this pattern class across the guarded tree and paste the classified result."*
> 5. **When the live sweep finds a defect class the item did not name, file it rather than absorbing it.**

#### Extractor pitfalls: an assertion's extraction step is an instrument too

Obligation C covers a matcher that cannot see a multi-line idiom. A gate also extracts before it asserts. It pulls identifiers into a list, filters a search's output, or slices source text. Each step can drop or truncate its subject without an error, and the assertion then compares the damaged result.

| Shape | Symptom | Repair |
|---|---|---|
| A digit-less character class such as `[a-z_]+` | Against `country_3_code`, the line drops or the capture truncates to `country_` | Use `[a-z0-9_]+` or `\w+` |
| An exclusion filter (`grep -v`) over `grep -rn` output | Every file whose path carries the excluded name drops out, so one sweep returned 16 matches against a true 36 | Anchor past the prefix with `:[0-9]+:.*TOKEN`, match executable syntax, or exclude by exact file path |
| String slicing as a parser, such as `.split(` on source text | The slice stops at an unrelated `]`, so one gate counted about 30 entries against a true 99 | Parse with `ast.parse` or the format's real parser |

> [!constraint] Three rules close the extraction hole
> **Assert the length of every derived list before comparing two of them.** A short list is an extractor bug. For example, require `wc -l < ddl_order.txt` to equal the expected parameter count before the diff runs.
>
> **A corrected exclusion must return more matches than the broken one.** Equal counts mean the repair did not take. An exclusion that over-excludes reports fewer problems, and fewer problems reads as better.
>
> **A sweep that passes on few or zero matches needs a planted-positive recall test.** Plant one known positive in a scratch copy and confirm the command finds it.

Checks 36, 37 and 38 of `scripts/lint_gate_checks_verify.py` flag the three shapes statically and report at WARNING. They are heuristics. Run the command against a known-good and a known-bad input before you trust either verdict.

#### Real-path pitfalls: a success signal that never ran the path it vouches for

Obligation A asks whether a gate can fail. An instrument can pass that test on its own fixtures and still never run the path its claim is about. Each shape below produced a green signal from code the real run does not execute. The repair has one form in every row: run the instrument once on the real path, with a must-fail control beside it.

| Shape | What the green signal proved |
|---|---|
| A writer's dry run vouches for an `--apply` control | Only the dry-run path, which skips every guard that runs on apply |
| A writer exits 0 | That the script finished, not that it acted on every flag |
| Two copies of a script share a version string | Which label was installed, not which features the code carries |
| A differential check reports "0 differ" | Nothing, when both readers raised the same error |
| An in-process stand-in for a native tool decides a call | That Python compiles the pattern, not that the tool accepts it |
| `node --check` passes an ES-module script | Nothing, because Node does not report the syntax error for that file shape |
| A path gate passes its unit tests | Only the path form its synthetic fixtures use |

#### A dry run versus the apply path

> [!constraint] A dry run proves only the dry-run path
> A split tool refused an `--apply` run when a resulting file measured over its size warning. Before the apply-mode control was dispatched, the command ran without `--apply` on a scratch copy. It printed `status: planned` and exited 0, and that result was recorded as the control's premise. The control then ran with `--apply`. The size guard refused it with exit 1, because the guard runs only under `--apply`.
>
> WRONG — the dry run's exit code becomes the premise of an apply-mode control:
> ```
> tool --source <scratch>/x.md --sections 16-17            # exit 0, status: planned
> -> record "control premise proven" -> dispatch the control
> tool --source <scratch>/x.md --sections 16-17 --apply    # exit 1: the guard refused
> ```
> CORRECT — run the apply path on a scratch copy before a control depends on it:
> ```
> cp -rp <tree> <scratch>
> tool --source <scratch>/x.md --sections 16-17 --apply    # the guard runs here
> checker --root <scratch>                                 # then the downstream gate
> rm -rf <scratch>; test -e <scratch>                      # exit 1
> ```
>
> The trigger is a pinned command that carries `--apply`, `--write` or `--force` while the check that proved it did not. The one alternative is to read the guard's code path and confirm that the dry run reaches it.

#### Exit 0 and a shared version string

> [!constraint] Exit 0 does not prove the write, and a version string does not prove the code
> A closeout called an installed backlog writer with `--resolution-file`. The writer exited 0, flipped the status and archived the item. The item had no `## Resolution` section afterward. The installed copy predated the flag and parsed with `parse_known_args()`, which drops an unknown flag without a word. The development tree carried the same version string and did support the flag.
>
> WRONG — the command exits 0, so the record is assumed written:
> ```
> update_backlog.py ... --status=COMPLETE --resolution-file r.md   -> exit 0, "moved to Archive"
> report "COMPLETE, record appended"
> ```
> CORRECT — expect the writer's confirmation line for the flag, and read the target back when it is absent:
> ```
> update_backlog.py ... --status=COMPLETE --resolution-file r.md   -> exit 0, no "Resolution:" line
> Grep '^## Resolution' <archived item>                             -> no match
> -> the flag was dropped: Grep the option name in each copy, re-run with the copy that has it
> ```
>
> 1. **After a write whose flag carries the substance, look for the script's confirmation line for that flag.** When the line is missing, read the target before you report.
> 2. **When two copies of a script share a version string, `Grep` the option name in the copy you are about to run.** The version proves the label, not the feature set. `measure-artifact-identity.md` §4 covers the same skew from the error side.
>
> The plugin's backlog and plan writers now exit 2 on an undeclared flag, with `unrecognized arguments:` on stderr. The read-back still applies to an installed copy older than that change, and to any script that tolerates unknown arguments.

#### A differential that counts the cases it could not compare

> [!constraint] A differential check counts the cases it could not compare
> A config reader was extended, and the claim was that no existing reading changed. The old reader and the new reader ran over the two real config files, and the check printed `compared 2 files, 0 differ`. Both readers had raised the same `TypeError` on both files. Two equal errors compare equal, so the check examined nothing. Split into its 32 top-level blocks, the corpus gave 28 identical, 2 differ and 2 raised on both. The 2 differing blocks were a real defect that the item had never listed.
>
> WRONG — a crash on both sides reads as "same":
> ```
> a, b = old(text), new(text); print("differ" if a != b else "same")
> ```
> CORRECT — run each side inside try/except and print three counts beside the verdict:
> ```
> identical 28, differ 2, raised-on-both 2   (of 32 blocks)
> # a nonzero raised-on-both means: split the corpus until it is zero,
> # or name the unreadable part as outside the claim
> ```
>
> Split a corpus that cannot be read whole at the unit the reader handles, such as one top-level block. The split also gives the check its denominator. This applies to any "the new code reads everything the old code did" claim: parsers, generators, migrators, index builders.

#### A stand-in for a native tool

> [!constraint] A stand-in for a native tool refuses what the real tool rejects
> A gate linter decides a native `Grep` call in-process with Python `re`. Its first design refused only a pattern that Python cannot compile. The tool runs the ripgrep engine, which rejects constructs that Python accepts. Python compiles each construct below, and the tool would have errored instead. An absence gate (`expect 0`) over any of them passes on every tree:
> - a lookaround, such as `(?=x)` or `(?<!x)`
> - a backreference, such as `(a)\1`
> - a possessive quantifier or an atomic group, such as `a++` or `(?>x)`
> - a `\n` in a pattern without `multiline`, which a per-line search never matches
>
> WRONG — the stand-in's own compiler is the only gate:
> ```
> re.compile(r"(?=x)")    # compiles, the tool errors, the gate reads a measured 0
> ```
> CORRECT — scan for the constructs the tool rejects, ahead of the compile, and refuse with a reason:
> ```
> _python_only_construct(pattern, multiline)   # "a lookaround" -> refused, never decided
> ```
>
> 1. **Make a compile warning an error** (`warnings.simplefilter("error")`). Python reads `[[:alpha:]]` as a nested set with a `FutureWarning`, and ripgrep reads it as a POSIX class.
> 2. **Treat "no output" as a measured zero only when the stand-in proves it searched.** Report the file count on stderr.
> 3. **Write test fixtures with raw bytes.** A text-mode write on Windows turns each LF into CRLF, so a `\n` pattern fails for the wrong reason.
>
> `scripts/lint_gate_grep_tool.py` applies this scan, and its tests pass each refused construct. Any other checker or test double that re-implements `Grep` or `Glob` needs the same scan.

#### A syntax gate on an ES-module script

> [!constraint] A syntax gate on an ES-module script needs a parse that can fail
> A plan pinned `node --check <workflow>.js` as the syntax gate for a Workflow script. A must-fail control ran first. On Node v22.20.0, a scratch file holding `export const meta = {` and `const x = ;` made `node --check` exit 0. The same file without the `export` line exited 1 with `SyntaxError`. Node detects the file as an ES module and does not report the error.
>
> WRONG — the gate cannot fail on this file shape:
> ```
> node --check <workflow>.js     # exit 0 even with `const x = ;` in the file
> ```
> CORRECT — an async-function-body parse, with its control:
> ```
> node -e "const s=require('fs').readFileSync(f,'utf8').replace(/^export\s+/m,'');
>          new (Object.getPrototypeOf(async function(){}).constructor)('agent','pipeline','parallel','args',s)"
> # control: the same parse on 'const x = ;' must throw SyntaxError
> ```
>
> The parameters are the script's runtime globals. This applies to any syntax gate on a Workflow script, and on any ES-module file without a `package.json` type hint.

#### A path gate and the path form the tool reports

> [!constraint] A path gate is proven on the path form the real tool reports
> A lab driver passed `plugin_dir.as_posix()` (`C:/Users/<user>/.../<plugin>`) as the expected plugin path. The CLI's stream-json init event reported `C:\Users\<user>\...\<plugin>`. The gate matched on a path-segment boundary, so it failed although the plugin loaded from the right copy. The first paid run was graded VOID. Thirteen tests had passed, and every one used synthetic forward-slash paths.
>
> WRONG — the expectation and the tests share one path form:
> ```python
> expect_plugin_path = plugin_dir.as_posix()      # 'C:/Users/.../<plugin>'
> # the init event reports 'C:\\Users\\...\\<plugin>' -> "does not contain" -> VOID
> ```
> CORRECT — fold the separators on both sides, then run the gate once on a captured real init event, with a must-fail control, before any paid launch:
> ```
> plugin_gate(<real init plugins>, gate_expect(scratch_dir))   -> PASS
> plugin_gate(<real init plugins>, gate_expect(other_dir))     -> FAIL   # control
> ```
>
> Capture the init event with a near-free load proof (`--max-budget-usd 0.001`), or take it from any earlier run on the same build. Keep the captured event as a permanent fixture. This applies to any gate that compares a path the harness reports (init plugins, cwd, tool inputs) with a path the driver built.

#### Reviewer Check 087 — Bug-Fix Criteria With No Fixture and No Unfixed-Artifact Run

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** A plan whose deliverable is a bug fix MUST carry at least one acceptance criterion phrased against a **fixture that reproduces the defect**, AND a requirement to run the same probe against the **unfixed artifact** and show it failing. Criteria phrased against live project data measure the data, not the code — they pass identically against fully-unfixed code whenever the triggering rows were reworded, worked around, or otherwise sanitised before triage. Without the failing run, "my code passes" has never been distinguished from "this gate detects the defect."
- **Detection:**
  1. Identify deliverables whose objective is a fix, repair, or correction of a defect.
  2. Read their acceptance criteria. Classify each as fixture-based (names a constructed input reproducing the defect) or data-based (queries the live project corpus). All data-based → BLOCKER.
  3. Check for a criterion requiring the probe to run against the unfixed artifact — the previous commit, the installed older version, or a reverted copy — with the FAIL result recorded. Absent → BLOCKER.
  4. Check the plan names which criterion is the **discriminating** one. Absent → WARNING (downgrade from BLOCKER when 2 and 3 both pass).
  5. Where a criterion is already satisfied at triage time, check the plan records that as a finding with its reason rather than as a satisfied box. Recorded as satisfied → BLOCKER.

#### Reviewer Check 088 — Gate Asserts Format Where the Property Is Resolution, or Is Fixture-Satisfiable

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** Two instrument defects that ship together often enough to share a check. **(a)** A verification gate asserts a format or spelling pattern where the property at stake is **resolution or existence** — a citation gate matching punctuation rather than confirming the target file and section exist. Such a gate scores 0 on a correctly pinned citation written in the house style and scores 1 on a citation whose file does not exist, and it exerts pressure on the runner to reformat correct content. **(b)** A gate-repair deliverable whose acceptance criteria are satisfiable **entirely by fixtures**, with no live sweep of the guarded subject. A fixture dry-run proves the gate is not vacuous; only a live sweep proves the subject is clean, and the live sweep is the one that finds work no criterion could have named.
- **Detection:**
  1. For every verification gate whose subject is a citation, path, identifier, or section reference: read its pattern. Does it assert punctuation, spacing, or delimiter placement rather than confirming the target resolves? → WARNING.
  2. Apply the authoring test to each such gate — *what would a correct-but-differently-formatted artifact score?* FAIL → WARNING.
  3. Check whether the plan requires a dry-run against a known-GOOD file in the house style, not only against known-bad. Absent on a format-shaped gate → WARNING.
  4. For deliverables whose objective is repairing or authoring a gate: check the criteria for a live sweep of the guarded tree, phrased so fixtures cannot satisfy it. All-fixture criteria → WARNING.
  5. Check the plan states that findings outside the item's file list are expected from the live sweep and get filed rather than absorbed. Absent → WARNING.

---

*Cross-references: [gate-positive-and-mutation-controls.md](gate-positive-and-mutation-controls.md) (§1-§4 and §14, the controls that discharge obligations A and B in practice) · [gate-fixture-provenance.md](gate-fixture-provenance.md) (§5-§9, an input set that could have contained the defect: obligation D) · [gate-change-vs-state-detecting.md](gate-change-vs-state-detecting.md) (§11, what shape of question a sound battery can answer at all) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) (pair every anchor against its known-bad state) · [verification-gates.md](verification-gates.md) (the family index).*
