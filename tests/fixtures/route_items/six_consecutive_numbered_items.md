---
id: 442
title: "Neither cd control stops a cd wrapped in bash -c, sh -c, eval, or an env-assignment prefix"
priority: Medium
status: NOT_STARTED
abbrev: INFRA
created: 2026-10-06
blocks: []
route_hint: A
route_evidence: "one regex family plus fixtures in two files already covered by tooling/hooks/test_deny_cd.py, then a re-run of the §8.2 matrix with the new DENY rows; the permission entry is not changed"
route_dated: 2026-10-06
---

# BB-442-INFRA-WrappedCdEvadesBothControls: Neither cd control stops a cd wrapped in bash -c, sh -c, eval, or an env-assignment prefix

**Priority:** Medium
**Domain:** INFRA
**Filed:** 2026-10-06 from the closeout of BB-440, at the user's request.

---

## Summary

The project's `cd` prohibition is enforced twice: the `"Bash(cd *)"` entry in `permissions.deny` and the `deny-cd.py` PreToolUse hook. Both match `cd` only when it is the first token of a shell segment. A `cd` carried as the *argument* of another command reaches the shell unchallenged. Measured live: `bash -c 'cd cloned-repos/planwise && git status --porcelain'` ran, returned real git output, and left `permission_denials` empty. The hook's own predicate allows `bash -c`, `sh -c`, `eval`, `FOO=1 cd x`, and `env FOO=1 cd x`. Close the wrapped-command class in the hook, with fixtures on both sides, and re-run the matrix.

## Problem

**Evidence, the hook's verdicts (2026-10-06, each payload fed to `.claude/hooks/deny-cd.py` on stdin):**

| Command | Hook verdict |
|---|---|
| `bash -c 'cd cloned-repos/planwise && git status --porcelain'` | allow |
| `sh -c "cd x && make"` | allow |
| `eval "cd x"` | allow |
| `FOO=1 cd x` | allow |
| `env FOO=1 cd x` | allow |
| `cd x` | DENY |

**Evidence, the live probe (2026-10-06, CLI 2.1.292, `claude -p --output-format stream-json --verbose --allowedTools Bash --max-turns 2` from the project root, no `--settings` override, both controls installed):**

```
TOOL_USE:    bash -c 'cd cloned-repos/planwise && git status --porcelain'
TOOL_RESULT: is_error=False
              M plugins/planwise/handlers/plan.md
              M plugins/planwise/handlers/review.md
              … (real output from the plugin repo's working tree)
RESULT:      permission_denials=[]
```

The permission entry did not fire either: `Bash(cd *)` is matched against a segment's leading token, and the segment here begins with `bash`.

**Why the hook misses it, by design so far:** the hook blanks quoted strings before matching, so that a commit message, a `claude -p` prompt, or a log line that *mentions* `(cd X && …)` is not denied. Three such false positives hit the authoring session in one day, and blanking was the fix. The quoted `cd` inside `bash -c '…'` is text to the blanker and a command to the shell. The env-assignment form is a separate miss: `FOO=1 cd x` puts `cd` second in the segment, and the command-position pattern looks only at the first token.

**Why it matters:** the whole point of the hook is to replace a silent denial with a guided one at the moment the model reaches for `cd`. A model that has been denied twice and is still improvising (the exact chain BB-440 closed) has `bash -c` as its next obvious move, and that move currently works. The working-directory change does not persist past the child shell, so the stated hazard in CLAUDE.md rule 3 (persisting cwd state) is not triggered, but the discipline it protects is: every path in the wrapped command is now relative to a directory the transcript never shows.

## Proposed Solution

Change the hook only. Leave `"Bash(cd *)"` as it is; widening a permission pattern is a gate change with its own matrix (`hook-deny-contract.md` §8.2), and the hook is the layer that can be unit-tested.

1. **Wrapped-command check, applied to the raw command before blanking.** For each `bash|sh|zsh|dash` followed by `-c`, `-lc`, `-ec` and similar, and for each `eval`, take the next argument (one quoted string, or one unquoted token) and run the existing command-position pattern on *its contents*. Nested one level is enough; recurse at most twice to stay bounded.
2. **Env-assignment prefix.** Allow `\w+=\S*` tokens, and `env` with its assignments, before the verb in the command-position pattern: `(?:^|sep)\s*(?:env\s+)?(?:\w+=\S*\s+)*(?:cd|pushd)(?=…)`.
3. **Keep the blanker for everything else.** A `git commit -m "… (cd x) …"` and a `claude -p '… (cd x) …'` must still pass. Only the known shell-invoking verbs reach into their arguments.
4. **Fixtures in `tooling/hooks/test_deny_cd.py`.** DENY: the six rows in the table above except `cd x` (already covered), plus `bash -lc "cd x"`, `sh -c 'ls; cd x'`, and `eval 'echo a && cd x'`. PASS: `git commit -m "bash -c is not the problem; (cd x) is"`, `claude -p 'say: bash -c cd x'`, `python -c "print('bash -c cd')"`, `grep -n 'bash -c' notes.txt`, and `bash -c 'ls cloned-repos/planwise'`. Every DENY and PASS row must land on its side before the change ships.
5. **Live matrix.** Re-run `hook-deny-contract.md` §7's shape with three new DENY rows (`bash -c`, `eval`, `FOO=1 cd x`) and the three control rows, graded on `permission_denials` and the tool result, each row a separate child. Record the run in §7 and extend the hook's §8.1 row; remove the sentence that lists `eval "cd x"` and `FOO=1 cd x` as uncovered.
6. **Out of scope.** `python -c "import os; os.chdir(…)"`, PowerShell `Set-Location`, and a script file that itself runs `cd`. Name them in §8.1 as the remaining uncovered class so the next reader does not re-derive the boundary.

## Acceptance Criteria

- [ ] `python -m pytest -q tooling/hooks` passes with every DENY row in step 4 denied and every PASS row allowed
- [ ] The hook fed `bash -c 'cd cloned-repos/planwise && git status --porcelain'` on stdin emits the §1 deny shape, and fed `git commit -m "… (cd x) …"` emits nothing
- [ ] A `claude -p` child attempting `bash -c 'cd …'` receives the hook's reason text and the attempt appears in `permission_denials`; a child running `bash -c 'ls cloned-repos/planwise'` gets real output and an empty array
- [ ] `hook-deny-contract.md` §7 records the re-run with the CLI version, and §8.1's hook row names what is now covered and what remains out of scope
- [ ] `.claude/hooks/deny-cd.py` and `tooling/hooks/test_deny_cd.py` lint clean under `python -m ruff check`
- [ ] `.claude/settings.json` `permissions.deny` is unchanged by this item

## Related

- `.claude/hooks/deny-cd.py` — the predicate to extend; its docstring already names the quote-blanking trade this item has to preserve
- `tooling/hooks/test_deny_cd.py` — the fixtures; run as `python -m pytest -q tooling/hooks`
- `.claude/settings.json` — `"Bash(cd *)"` stays as the backstop and is not widened here
- `.claude/rules/hook-deny-contract.md` §7, §8.1 — where the re-run and the coverage statement go
- Originating item: BB-440 (closed 2026-10-06); BB-441 measures the same two layers inside subagents and is independent of this item

---

*Created: 2026-10-06*
