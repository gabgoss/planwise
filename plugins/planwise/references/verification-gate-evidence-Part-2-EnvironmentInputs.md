---
description: Two environment inputs a proof silently assumes. §20 — a proof run that builds a fixture tree writes to a scratch root named in the brief and outside the repo whose working tree ships, the runner proves the root's removal with `test -e` exiting 1, and the distribution sweep names scratch-shaped directories (`probe_*`) beside test files and caches, with a positive control for that clause. §21 — a test never hard-codes a checked-in file's line endings, because the file's on-disk bytes depend on `core.autocrlf` and the checkout, so the test reads the expected bytes from the file itself. §22 — a green suite is no evidence about import order, because pytest imports modules in collection order inside one interpreter and the first module that loads a hub hides every cycle through it, so the proof imports each globbed module first in its own fresh subprocess and a guarded-import wrapper chains the cause with `from exc`. §23 — an exit-code gate is derived from the script's return paths, never from design prose, so the gate quotes each `return` and `sys.exit` path beside its code, gates on exit code plus status field plus coverage count together, and routes a refuted reading as a binding spec delta.
paths: {planwise_root}/{plans_dir}/**
---

# Verification-Gate Evidence, Part 2 — Environment Inputs a Proof Assumes

**Purpose:** §20 to §23, split out of [verification-gate-evidence.md](verification-gate-evidence.md) when that file approached the Read-tool token gate. §1–§19 stay on that anchor, which keeps the original filename. §20 is the fifth constraint of that file's §2, and §21 extends its §5. §22 and §23 extend its §1 and §3: each names an input a proof or a gate silently assumes (an import order, a reading of an exit code). Cite §20 and §21 as `verification-gate-evidence.md` §2 and §5 and read them here.

**Read this when** a proof run builds a fixture tree and the repo's working tree ships, or when you write the distribution sweep that guards that tree. Read §21 when a test compares output against a checked-in seed, template or golden file. Read §22 when a Python package re-exports names between modules or guards an import. Read §23 when a gate, success criterion or handler branch interprets a script's exit code.

## Table of Contents

- [20. A Proof Run Names Its Scratch Root, Proves Its Removal, and the Sweep Names Scratch Directories](#20-a-proof-run-names-its-scratch-root-proves-its-removal-and-the-sweep-names-scratch-directories)
- [21. A Test Never Hard-Codes a Checked-In File's Line Endings](#21-a-test-never-hard-codes-a-checked-in-files-line-endings)
- [22. A Green Suite Says Nothing About Import Order — Prove It Per Module in a Fresh Interpreter](#22-a-green-suite-says-nothing-about-import-order--prove-it-per-module-in-a-fresh-interpreter)
- [23. Derive an Exit-Code Gate From the Script's Return Paths, Never From Design Prose](#23-derive-an-exit-code-gate-from-the-scripts-return-paths-never-from-design-prose)

---

## 20. A Proof Run Names Its Scratch Root, Proves Its Removal, and the Sweep Names Scratch Directories

§2 lists four constraints on a mutation run. Constraint 1 says the scratch copy lives outside the shipped tree. This section adds the fifth constraint. It covers every proof run that builds a fixture tree, not only a mutation control.

A sweep that names only test files and caches prints a clean result over a tree that holds stray fixtures. One session's proof runs showed three repair assertions failing on pre-fix code. The runs built their fixture trees in the plugin repo's working directory, as two `probe_*_tree` directories under the shipped subtree. The two directories held 4 files. The sweep then in use named `test_*.py`, `*_test.py`, `conftest.py` and the cache directories. A probe tree is none of those, so the sweep printed nothing. The session's bulk commit included the 4 files and the commit was pushed. A later commit removed them.

> [!constraint] Proof runs write to a scratch root outside the repo whose working tree ships
> Two obligations:
>
> 1. **Name the scratch root in the brief, and prove its removal.** The brief gives the root as an explicit path outside the repo whose working tree ships, such as the session scratchpad. Every proof run that builds a fixture tree writes there. The runner deletes the root and proves it with `test -e <scratch-root>` exiting 1 before it returns.
> 2. **Have the distribution sweep name scratch-shaped directories.** List `probe_*` and any other directory name the session's proof runs use. Put them next to test files and caches. Run the sweep last, after the final test run, from an absolute path.
>
> ```
> WRONG — the runs wrote into the repo, and the sweep names only tests and caches:
>   proof run → <repo>/plugins/<plugin>/probe_b_tree/
>   sweep     → find <abs>/plugins/<plugin> \( -name 'test_*.py' -o -name 'conftest.py' \) -o -type d -name '__pycache__'
>   result    → prints nothing while probe_b_tree/ sits in the tree
>
> CORRECT — scratch lives elsewhere, and the sweep names scratch-shaped directories anyway:
>   proof run → <scratch-root>/<round>/        (removed, and `test -e <scratch-root>` exits 1)
>   sweep     → find <abs>/plugins/<plugin> \( -name 'test_*.py' -o -name '*_test.py' -o -name 'conftest.py' \) \
>                 -o -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name 'probe_*' \) -print
> ```

**Give the new clause a positive control.** A sweep clause that has never fired has not been shown to see anything. Create a directory named `probe_control` under the scratch root. Run the same walk with the scratch root as the walk path. It MUST print that one directory. Delete the control directory afterward. Never create the control inside the shipped tree, because a crash between creation and deletion would ship it.

**Delete a scratch-shaped hit, never relocate it.** A `probe_*` directory under the shipped subtree is a proof artifact, not authored source. A blanket delete is safe. Read `git status` for the repo first, and confirm the directory is untracked. A tracked hit has already been committed, and its removal needs its own commit.

**Applies to** any session whose proof runs build fixture trees and whose repo ships its working tree. This covers a marketplace plugin, a container build context and a published package directory.

---

## 21. A Test Never Hard-Codes a Checked-In File's Line Endings

§5 covers a fixture built through the API under test. This section covers the opposite input: the file a test compares against. The two sections split the byte question. §5 and §18 cover the bytes an edit writes. This section covers the bytes a test expects.

A checked-in text file's on-disk bytes are a property of the checkout, not of the repository. `core.autocrlf`, `.gitattributes`, editors and copy tools all change them. A literal line ending in a test that compares against such a file makes the result depend on the machine. The test then fails correct code in some environments and passes broken code in others.

**Scenario.** A test asserted that an upgrade backup equals the plugin's changelog seed, byte for byte. It built the expected value from a constant, `f"[← {INDEX}]({INDEX})\r\n".encode()`. Git stores the seed as LF (`i/lf` in `git ls-files --eol`). On a Windows machine with `core.autocrlf=true` the checkout is CRLF, so the test passed when written. Later the working tree's seed read LF on disk (`w/lf`) and the test failed. A fix round's runner first took the failure for a regression of its own. The orchestrator proved otherwise in a scratch worktree at `HEAD`. The unchanged test passed with a fresh CRLF checkout and failed once the seed was LF. The same test would fail on any Linux clone or CI runner.

> [!constraint] Read the expected bytes from the checked-in file itself
> ```python
> # WRONG — a literal that depends on how this machine checked the file out:
> SEED_HEADER = f"[← {INDEX}]({INDEX})\r\n".encode()
> assert backup.read_bytes() == SEED_HEADER          # depends on autocrlf
>
> # CORRECT — the expected bytes are the checked-in file's bytes on disk:
> SEED = PLUGIN / "seed" / "<seed-file>.md"
> assert backup.read_bytes() == SEED.read_bytes()    # the bytes the bootstrap copied
> ```

Two operative points:

- **Compare against the file itself.** Read the expected bytes with `Path(...).read_bytes()`. Where line endings are not what the test is about, normalize both sides and compare.
- **Keep a literal `\r\n` only for fixtures the test builds itself.** There CRLF is the input under test, so the literal is the fixture. It is not a claim about a checkout. The "CRLF fixture must stay CRLF" row in the §5 table is that case.

**Applies to** tests that compare output against a checked-in seed, template or golden file, in any repo cloned on more than one OS or with more than one `core.autocrlf` setting. It matters most for tests that assert byte fidelity, because any normalization would hide the property under test.

---

## 22. A Green Suite Says Nothing About Import Order — Prove It Per Module in a Fresh Interpreter

A green suite is no evidence about import order. Pytest imports modules in collection order inside one interpreter. The first module that loads a hub hides every cycle through it. Only a first import in a fresh process tests what `python script.py` does for a user.

**Scenario.** A hub module re-exported names from four sibling modules at its bottom. Each sibling imported the hub at its top, before the sibling's own names existed. Importing any one of the four first raised `ImportError`. The full suite passed throughout, because some test always imported the hub first. The guarded-import wrapper made it worse. It caught the `ImportError` and raised a new one saying the package "appears to be partially installed". That message sent the reader to an install diagnosis, and the real cause was a cycle.

The first version of the proof test listed seven modules by hand. A code review asked for a glob. The globbed version covered 61 modules and failed four of them on the pre-fix tree. The repair moved each back-edge import below the module's own definitions.

Three operative points:

- **Test each module as the first import in its own subprocess.** Run `sys.executable -B -c "import <module>"` and assert exit 0. The `-B` flag keeps bytecode out of the shipped tree.
- **Glob the module set. Never list it by hand.** A hand list misses the next module that joins the cycle.
- **Chain guarded-import errors with `from exc`.** A wrapper that replaces the cause turns a cycle into a misleading install diagnosis.

> [!constraint] One fresh subprocess per globbed module, and a chained cause
> ```python
> # WRONG — a hand list, and a wrapper that discards the cause:
> MODULES = ["<mod-a>", "<mod-b>", "<mod-c>", "<hub>"]
> # plus:
> try:
>     import <hub>
> except ImportError:
>     raise ImportError("... appears to be partially installed")
>
> # CORRECT — a globbed set, one subprocess per module, and a chained cause:
> MODULES = sorted(p.stem for p in SCRIPTS.glob("*.py"))
> @pytest.mark.parametrize("mod", MODULES)
> def test_first_import(mod):
>     r = subprocess.run([sys.executable, "-B", "-c", f"import {mod}"], cwd=SCRIPTS)
>     assert r.returncode == 0
> # and:
> except ImportError as exc:
>     raise ImportError("...") from exc
> ```

Run the CORRECT test on the pre-fix tree once. It MUST fail for the modules in the cycle. A proof that has never failed has not been shown to see the defect (`verification-gate-evidence.md` §1).

**Applies to** any Python package whose modules re-export each other or use guarded imports. It applies most to script directories that users run directly.

---

## 23. Derive an Exit-Code Gate From the Script's Return Paths, Never From Design Prose

A gate on an exit code is a claim about the code's return paths. Derive it from those paths, never from a design document's description of them. Design prose assumes the diff-tool convention: 0 means clean and 1 means differences found. A shipped script may overload one code.

**Scenario.** A gate copied "exit 0 or 1 is a real verdict" from design prose. The script used exit 1 for "index not found". A deleted or mis-pathed index would have counted as a passing verdict. The observed return paths of that script:

| Exit | What the code prints |
|------|----------------------|
| 0 | `No drift detected. ...` **or** `Drift detected ({n} row(s) ...):` |
| 1 | `Error: <index> not found at {path}` |
| 2 | the legacy-shape error |
| 3 | `Drift audit could not run ...` or `Drift audit incomplete ...` |

Exit 0 carries two outcomes, and exit 1 carries none of the diff-tool meaning.

**How it surfaced.** A later task's brief said to quote the script's strings from the code, never from the design prose, and that the code wins. The task quoted the report function before it rewrote the handlers. The contradiction appeared at that quote. The quote step made the defect visible.

Three operative rules:

- **Quote before pinning.** Before writing "exit N means X" into a gate or a success criterion, search the script for each `return` and `sys.exit` path. Quote each message beside its code.
- **Gate on the outcome, not the code alone.** When the script emits a machine-readable status, gate on the exit code, the status field and the coverage count (`compared == total`) together. Exit codes get overloaded. A status field names the outcome.
- **Route the correction the moment it lands.** A later task's gate that rests on the refuted reading is an unresolved conditional branch. The orchestrator rewrites it as a binding spec delta at post-task time. The later runner does not rediscover it. The spec-delta mechanics are in [read-confirm-act-protocol.md](read-confirm-act-protocol.md).

> [!constraint] The gate names the observed outcome
> ```
> # WRONG — the gate inherits the convention from prose:
> <audit> --json  ->  exit 0 or 1 is a real verdict (never 3)
> # Result: a deleted or mis-pathed index (exit 1) counts as a passing verdict.
>
> # CORRECT — the gate names the observed outcome:
> <audit> --json  ->  exit 0 AND status == "ran" AND compared == total
> exit 1 (index missing), 2 (legacy shape), 3 (could not run / incomplete)  ->  FAIL
> ```

This section derives the gate before it is pinned. [verify-verdict-source.md](verify-verdict-source.md) § "8. Classify Every Non-Zero Exit by Cause Before Treating It as a Bug or a Result" classifies an exit that was already observed. The two are different questions.

**Applies to** any plan gate, success criterion or handler branch that interprets a script's exit code. It applies most to scripts that overload one code for several outcomes.
