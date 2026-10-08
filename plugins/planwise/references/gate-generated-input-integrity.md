---
description: A file list that feeds a gate is part of the gate's input, so count the list before trusting a "MUST print nothing" result that reads it (§16); a row-count gate and its consumer split lines the same way (§17); a byte-preservation claim is verified with a byte tally, never through git under `core.autocrlf` (§18); and a test never hard-codes a checked-in file's line endings, because the on-disk bytes depend on the checkout (§21).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Generated-Input Integrity (Inputs That Silently Empty a Gate)

**Purpose:** Four inputs that vanish or change before the predicate runs: a path list whose lines end in a carriage return, a row a different line splitter reads as two, bytes git normalises before it compares, and line endings a test assumes. Each prints a plausible answer and no error. Split from `verification-gate-evidence.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gate-evidence.md §N` citation translates by filename alone. The family index is `verification-gate-evidence.md`.

**Read this when** a gate reads a generated path list, gates the row count of a generated table, claims "line endings preserved" or "byte-identical" for a scripted edit, or compares output against a checked-in seed, template or golden file.

## Table of Contents

- [16. A File List That Feeds a Gate Is Part of the Gate's Input](#16-a-file-list-that-feeds-a-gate-is-part-of-the-gates-input)
- [17. A Row-Count Gate and Its Consumer Must Split Lines the Same Way](#17-a-row-count-gate-and-its-consumer-must-split-lines-the-same-way)
- [18. A Byte-Preservation Claim Is Verified With Bytes](#18-a-byte-preservation-claim-is-verified-with-bytes)
- [21. A Test Never Hard-Codes a Checked-In File's Line Endings](#21-a-test-never-hard-codes-a-checked-in-files-line-endings)

---

## 16. A File List That Feeds a Gate Is Part of the Gate's Input

> [!constraint] Count the list before you trust a "MUST print nothing" gate that reads it
> A path list consumed by `xargs`, `git --pathspec-from-file`, or a `while read` loop is the gate's input. Gate on the list's count first. Only then trust an empty-passing gate that reads it.
>
> The failure is silent. Git treats an unmatched pathspec on `status` and `diff` as "nothing to report", not as an error. A clean-tree precondition and a "no unexpected change" gate both pass exactly when nothing prints. A list whose every path fails to match therefore passes every one of them.
>
> One session built a 137-path list with a Python one-liner on Windows. Text mode wrote each line ending as `\r\n`. `xargs` splits on `\n` and keeps the `\r`, so git received `<path>\r`, which names no file. Every "MUST print nothing" gate that read the list passed over paths git never saw.
> ```bash
> # WRONG — text-mode list, and an empty-output gate trusted on its own:
> python -c "print('\n'.join(paths))" > <list>.txt
> xargs -a <list>.txt git status --porcelain --      # prints nothing: every path ends in \r
>
> # CORRECT — LF-only list, and a count gate the list must pass first:
> python -c "import sys; open(sys.argv[1],'w',newline='\n').write('\n'.join(paths)+'\n')" <list>.txt
> xargs -a <list>.txt git diff --numstat -- | wc -l   # MUST equal the expected file count
> xargs -a <list>.txt git status --porcelain --        # only now is "prints nothing" evidence
> ```
> The positive count is the only gate in this block that can fail when the list is corrupt. Run it first. It needs a diff that changes every listed file, so run it on the edit set after the edits land. On a corrupt list it prints `0`, and on a sound list it prints the file count.
>
> A list built with `git ls-files -z` and read with `xargs -0` avoids the line-ending question entirely.

## 17. A Row-Count Gate and Its Consumer Must Split Lines the Same Way

> [!constraint] Parse the structure the consumer will parse, not the number of prefixed lines
> A bare carriage return inside one table cell split a row for a consumer that used `str.splitlines()`. The gate used `grep -c`, which splits on LF only, so it counted the row once and reported the expected total. The gate and its consumer disagreed about what a line is, and the gate was the one that never saw the defect.
>
> **Writer side.** Neutralise control bytes when you copy source text into a line-oriented format. Replace CR, other C0 controls, U+2028 and U+2029 with a space or a visible escape in any table cell, CSV field, or one-line log. Treat them the way the writer already treats a pipe.
>
> **Gate side.** A row-count `grep` proves the number of LF-terminated lines that carry a prefix. A cell-count parse that uses the consumer's own splitter proves that each row is a row.
> ```bash
> # WRONG — the gate counts prefixed lines:
> grep -c '^| <key>-' <table>.md      # 88 — passes with a bare CR inside one row
> ```
> ```python
> # CORRECT — the gate parses every row the way its consumer will:
> raw = Path("<table>.md").read_bytes()
> rows = [r for r in raw.decode("utf-8").splitlines() if r.startswith("| <key>-")]
> bad = [r for r in rows if len(re.split(r"(?<!\\)\|", r)[1:-1]) != <expected_cells>]
> assert not bad and b"\r" not in raw.replace(b"\r\n", b"")
> ```
> This applies to any generated markdown table, TSV, or CSV built from text that came from another file. It applies most to text that a repair edited. It applies to any gate whose consumer uses a different line splitter from the gate itself.

## 18. A Byte-Preservation Claim Is Verified With Bytes

> [!constraint] The instrument that checks a byte claim must read bytes
> A "byte-preserving" claim is a claim about bytes. `git diff` under `core.autocrlf` reads a normalized view, so it cannot see a changed line ending. A runner's self-report reads the runner's intent, not the disk. Neither can falsify the claim, so a pass from either is not evidence.
>
> One session ran a scripted edit over 59 CRLF files. The regex matched each whole line with `(.+?)\r?$` and replaced the match. The match included the `\r`, so the replacement wrote the new value and a bare `\n`. 46 files ended with one LF-only line inside a CRLF file. The runner reported "CRLF preserved". The acceptance gate was `git diff --stat`, which showed the expected file and line counts. Git printed `LF will be replaced by CRLF the next time Git touches it` on every affected file, and the session read it as noise.
>
> ```
> # WRONG — splice one line and check with git:
> re.sub(r"^id: (.+?)\r?$", "id: 123", text, flags=re.M)   # match ends after \r; \r is gone
> git diff --stat   # 59 files, +590 -59 — identical before and after the splice
> # runner: "CRLF preserved". warning: LF will be replaced by CRLF ... (ignored)
>
> # CORRECT — match the value, then count the bytes:
> re.sub(r"^id: [^\r\n]*", "id: 123", text, flags=re.M)      # terminator untouched
> tally: crlf 194 / lf 44 / mixed 0                            # mixed MUST be 0
> ```
>
> A dry run on a three-line CRLF file shows the two forms differ. The WRONG form yields `crlf 3 / lf 1 / mixed 1`. The CORRECT form yields `crlf 4 / lf 0 / mixed 0`.

Four operative points:

- **Make the acceptance check a byte-level tally.** Count `\r\n` and bare `\n` per file, before and after the edit. A file that counts both is mixed, and the edit broke it. The tally is about ten lines of Python and runs in under a second over a few hundred files.
- **Match the value, not the line.** `[^\r\n]*` stops before either terminator. `.*` and `.+?` match `\r`. In MULTILINE mode `$` sits between `\r` and `\n`, so a `\r?$` suffix is consumed into the lazy group, and the replacement then drops the `\r`.
- **Treat git's `LF will be replaced by CRLF` warning as a gate failure on a file you just edited.** On a checkout that was clean before the edit, the warning names exactly the files whose working-copy endings no longer match what `autocrlf` would produce.
- **Prefer a whole-block rewrite to a one-line splice when the block is small.** Read the frontmatter as bytes, detect the file's ending once, and re-emit the whole block with that ending.

**Applies to** any scripted edit of a checked-out text file under `core.autocrlf=true`: frontmatter backfills, index-row repairs, status syncs, and template rewrites. It applies to any acceptance gate that reads `git diff` for a property git normalizes away, such as line endings, trailing whitespace under `whitespace=fix`, and a BOM. It applies to any runner report of "preserved" or "byte-identical" that the orchestrator cannot recompute from disk.

**Recovery path.** Never use `git stash`, `git checkout` or `git restore` as a byte-preserving undo, because git restores content in its normalized form and not the bytes that were on disk. Snapshot a tree by copying bytes (`cp -p`, or Python `shutil.copy2`) to a scratch directory instead.

## 21. A Test Never Hard-Codes a Checked-In File's Line Endings

`gate-fixture-provenance.md` §5 covers a fixture built through the API under test. This section covers the opposite input: the file a test compares against. The two sections split the byte question. That §5 and §18 above cover the bytes an edit writes. This section covers the bytes a test expects.

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
- **Keep a literal `\r\n` only for fixtures the test builds itself.** There CRLF is the input under test, so the literal is the fixture. It is not a claim about a checkout. The "CRLF fixture must stay CRLF" row in the `gate-fixture-provenance.md` §5 table is that case.

**Applies to** tests that compare output against a checked-in seed, template or golden file, in any repo cloned on more than one OS or with more than one `core.autocrlf` setting. It matters most for tests that assert byte fidelity, because any normalization would hide the property under test.

---

*Cross-references: [gate-fixture-provenance.md](gate-fixture-provenance.md) §5 (a fixture built through the API under test, the other half of the byte question) · [measurement-discipline.md](measurement-discipline.md) §8.5 and §8.7 (normalize on both read and write; verify the gate's input set before trusting its predicate) · [measure-aggregate-provenance.md](measure-aggregate-provenance.md) (every operand of a byte identity comes from one byte instrument) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
