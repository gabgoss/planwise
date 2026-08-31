# Task: {TaskName}

**Task ID:** {ABBREV}-S{NN}-{SS}-{TT}

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:**
> ```
> {cmd_before_1}
> ```
> **After:**
> ```
> {cmd_after_1}   # e.g. lint on files from git diff ${ABBREV}_S{NN}_BASE -- <paths>
> ```

> [!constraint] Diff-Derived Verification Commands Are Baseline-Scoped
> Any command whose input is `git diff` MUST be scoped to a recorded
> `{ABBREV}_S{NN}_BASE` — never a bare `git diff` with no operand. The baseline is
> recorded once, by the sprint's first task that touches the repo, before its first edit.
>
> CORRECT — scoped to the recorded base and to this sprint's own paths:
> ```
> git diff $<ABBREV>_S<NN>_BASE -- <paths>   # expect empty
> ```

---

## Success Criteria

- [ ] Every diff-derived gate names its recorded baseline
