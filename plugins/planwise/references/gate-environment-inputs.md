---
description: A proof run that builds a fixture tree writes to a scratch root named in the brief and outside the repo whose working tree ships, the runner proves the root's removal with `test -e` exiting 1, and the distribution sweep names scratch-shaped directories beside test files and caches (§20); and a green suite is no evidence about import order, so the proof imports each globbed module first in its own fresh subprocess and a guarded-import wrapper chains the cause with `from exc` (§22).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Environment Inputs (The Scratch Root and the Import Order)

**Purpose:** Two environment inputs a proof silently assumes: where its fixture tree lands, and the order in which an interpreter has already imported the modules under test. Split from `verification-gate-evidence.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gate-evidence.md §N` citation translates by filename alone. The family index is `verification-gate-evidence.md`.

**Read this when** a proof run builds a fixture tree and the repo's working tree ships, you write the distribution sweep that guards that tree, or a Python package re-exports names between modules or guards an import.

## Table of Contents

- [20. A Proof Run Names Its Scratch Root, Proves Its Removal, and the Sweep Names Scratch Directories](#20-a-proof-run-names-its-scratch-root-proves-its-removal-and-the-sweep-names-scratch-directories)
- [22. A Green Suite Says Nothing About Import Order — Prove It Per Module in a Fresh Interpreter](#22-a-green-suite-says-nothing-about-import-order--prove-it-per-module-in-a-fresh-interpreter)

---

## 20. A Proof Run Names Its Scratch Root, Proves Its Removal, and the Sweep Names Scratch Directories

`gate-positive-and-mutation-controls.md` §2 lists four constraints on a mutation run. Constraint 1 says the scratch copy lives outside the shipped tree. This section adds the fifth constraint. It covers every proof run that builds a fixture tree, not only a mutation control.

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

Run the CORRECT test on the pre-fix tree once. It MUST fail for the modules in the cycle. A proof that has never failed has not been shown to see the defect (`gate-positive-and-mutation-controls.md` §1).

**Applies to** any Python package whose modules re-export each other or use guarded imports. It applies most to script directories that users run directly.

---

*Cross-references: [gate-positive-and-mutation-controls.md](gate-positive-and-mutation-controls.md) §1-§2 (the positive control and the mutation run whose scratch root §20 names) · [gate-generated-input-integrity.md](gate-generated-input-integrity.md) §21 (the other environment input: a checked-in file's line endings) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
