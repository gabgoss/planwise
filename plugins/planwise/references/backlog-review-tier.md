---
description: The backlog review tier: how Phase 5 VERIFY computes the /code-review tier of a Route A or Route B diff with review_tier.py, runs the review in the main session, and shows or acts on the findings in interactive and loop mode
consult-when: Running Phase 5 VERIFY of /planwise backlog on a Route A or Route B change, or wiring a new caller that runs /code-review on a diff
---

# Backlog Review Tier

**Purpose:** Phase 5 VERIFY reviews the code of a fix before the Approve or Revert question. This reference owns the procedure. It never restates the tier thresholds, because `scripts/review_tier.py` holds them.
**Loaded by:** `handlers/backlog.md` Phase 5, after Route A step 3 and before Route B step 3.

---

## 1. Procedure

> [!constraint] Run the review in the main session only
> `/code-review` starts its own reviewer agents, and a subagent cannot start agents. A fix-agent therefore never runs the review. The main session runs it after the fix-agent or the task list returns.

1. Compute the tier from the route's changed paths:

   ```bash
   python -B {plugin_root}/scripts/review_tier.py --config {config_path} --repo . {changed paths} --judged deleted-symbol --judged return-shape
   ```

   Pass `--judged deleted-symbol` only when the session judges that the diff deletes or renames a public symbol. Pass `--judged return-shape` only when it judges that the diff changes a return shape. Pass neither flag otherwise. The script prints four lines. The first is `tier: none|low|medium|high`.

2. Read the tier.
   - Tier `none` means the diff holds no code file. Run the existing gates only. Skip the review.
   - Any other tier means run `/code-review {tier}` in the main session.

3. The thresholds live in the script. Read them with `review_tier.py --help`. Never copy them into a handler or a reference.

4. Which files count as code comes from built-in suffixes and from the `review_tier.code_globs` list in `config.yaml`. Add a glob there to make a project's own file kind count.

> [!constraint] Never pass `max` or `ultra` to `/code-review`
> Those levels are the costliest reviews. They need an explicit request from the user. The script never prints them, and no handler or agent path passes them.

---

## 2. Interactive mode

Show the `/code-review` findings before the Approve or Revert question. The user reads the findings, then decides. A finding the user confirms goes back to the fix-agent (Route A) or the main session (Route B) as a fix, and the gates run again.

## 3. Loop mode

A loop session asks nothing. The rule is in `handlers/backlog-Part-2-LoopMode.md` § No questions after setup. Fix each confirmed finding, re-run the item's verification, then close. A failing verification is a documented skip whose evidence names the finding and the failing command.

---

## 4. Output of the script

| Line | Meaning |
|------|---------|
| `tier:` | `none`, `low`, `medium` or `high` |
| `code_files:` | the count of code files in the diff |
| `code_lines:` | the changed code lines, added plus deleted |
| `escalators:` | the escalators that fired, or `none` |

Exit 0 means the tier printed. Exit 2 means a usage error, a git error or an unreadable config. Treat exit 2 as an unrun gate and report it. Never read it as tier `none`.
