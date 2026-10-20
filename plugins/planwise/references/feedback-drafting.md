---
description: When and how Claude drafts a planwise feedback file silently during /planwise work — triggers, the feedback.drafts setting, the write recipe through the shared helper, and the frontmatter the model fills.
---

# Feedback Drafting

## Purpose and scope

Claude may draft a feedback file when planwise itself misbehaves during `/planwise` work. The user reviews every draft later with `/planwise feedback --drafts`. Nothing is posted without the user's consent at that review.

- Draft only about planwise artifacts: its handlers, references, scripts, templates and hooks.
- A Claude Code or harness defect belongs to the native `SendFeedback` tool, not to a planwise draft.
- One moment can involve both. Then the planwise draft covers only planwise's handling of the moment. It never restates the other draft.

## Triggers

Draft when one of these six happens during `/planwise` work:

1. A handler step failed, or you had to work around it.
2. A shipped planwise script errored on valid input.
3. A planwise reference contradicted the code it describes.
4. The user expressed frustration with planwise in their own words.
5. A reasonable request needed a planwise capability that does not exist.
6. The user corrected your own planwise behaviour.

## Not triggers

Do not draft for these three:

1. A problem in the project's own content, such as a plan, backlog item or lesson.
2. A config typo that the handler reported correctly.
3. A gate that stopped the flow as designed.

## Honour `feedback.drafts`

Read `feedback.drafts` through the running handler's config resolution. Apply its value:

- `off`: write nothing.
- `quiet`: write the draft and run `admit`. Print nothing.
- `notify`: write the draft and run `admit`. When `admit` exits 0, print exactly this one line, and nothing else:
  ```
  planwise: a feedback draft was saved to {relative path} — review it with /planwise feedback --drafts
  ```

A missing or unreadable config counts as `off`. So does a missing key.

## Do not announce

- Never describe, summarise or quote the draft in your reply.
- Never ask the user whether to post it.
- In `notify`, the one line above is the only output. In `quiet`, there is none.
- Never read the draft back to the user unless the user runs `/planwise feedback --drafts`.
- Drafting never pauses, delays or redirects the user's task.

Compare two replies to an unclear user message.

- WRONG: `I'm logging the unclear message as a local planwise feedback draft, then I'll explain the fix.`
- CORRECT: a reply that explains the fix and does not mention the draft.

## One draft per issue per session

Write at most one draft for each distinct issue in a session. Never re-draft an issue you already drafted, even with new wording or new detail. The helper also refuses a draft whose normalised title matches a queued model draft.

## What to write

Map the issue to a kind, then write that kind's body headings in this order:

| Kind | Use for | Body headings |
|---|---|---|
| `bug` | planwise did the wrong thing | `### What happened`, `### What I expected`, `### Steps to reproduce`, `### Environment` |
| `idea` | a missing capability or an improvement | `### What I learned`, `### Why it matters`, `### Where it would apply`, `### Environment` |
| `lesson` | something learned about using planwise | `### What I learned`, `### Why it matters`, `### Where it would apply`, `### Environment` |

- Write facts only. Take each fact from the user's words or from what happened in this session. Never infer.
- Never fabricate or exaggerate the user's sentiment. Quote frustration only in the user's own words.
- Name people by role ("the user", "a reviewer"), never by name, inside quotes too.
- Use paths relative to the project root.
- Put commands and error text in fenced blocks.
- State a cause only if you verified it. Otherwise describe the symptom.
- Keep the title under 80 characters, with no trailing period.
- Under `### Environment`, write the planwise version, the subcommand involved (or `not command-specific`), and the OS and shell.

## Never write

- consumer project file contents, or any plan, backlog or lesson file body
- absolute paths, or the working directory
- `config.yaml` text
- git remote URLs
- secrets, tokens or credentials
- people's names
- anything that makes the file larger than 32 KiB

## Write recipe

Run these steps in order. If any step fails, stop drafting and continue the user's task.

1. Resolve `{planwise_root}/{feedback_dir}` from the config.
2. Call `Glob` with pattern `*` and `path` set to that absolute directory. A `Directory does not exist` error means the directory is absent: do not draft. "No files found" means it exists and is empty.
3. Compose the filename `{YYYY-MM-DD}-draft-{kind}-{slug}.md`. Build the slug from the title: lowercase it, turn each run of non-alphanumerics into one hyphen, and trim hyphens from both ends. Cut it to 40 characters, strip a trailing hyphen the cut exposes, and use `untitled` if it is empty. `Glob` the name in the directory. On a hit, add `-2` to `-9` before `.md`. If all are taken, do not draft.
4. `Write` the file with the frontmatter below, then the body headings for the kind.
5. Run the helper:
   ```
   python "{plugin_root}/scripts/feedback_drafts.py" admit "{path}" --feedback-dir "{abs feedback dir}"
   ```
6. Route on the exit code. No exit code blocks the user's task, and only exit 0 in `notify` prints anything.
   - `0`: admitted. In `notify`, print the one line. In `quiet`, print nothing.
   - `1`: the file or the config could not be read. Print nothing.
   - `2`: not admitted, and the file is untouched. Causes include a name mismatch, a bad directory option, or a draft that is no longer pending. Print nothing.
   - `3`: refused, or expired or evicted on admission. The helper deletes a refused draft whose frontmatter parses as `drafted_by: model`. Print nothing.

## Frontmatter the model fills

Write the keys in this order. `admit` replaces each `pending` id. Write `unknown` for any value you cannot observe.

```yaml
---
draft_id: pending
created_at: pending
drafted_by: model
producer: prompt
trigger: model_judgment
kind: {bug | lesson | idea}
title: {title}
subcommand: {the /planwise subcommand involved, or "not command-specific"}
source_session_id: {the current session id shown in the planwise skill's Argument Forwarding section, else unknown}
plugin_version: {plugin_version from config.yaml, else unknown}
cli_version: unknown
model: {your model id, else unknown}
os: {observed OS and shell, else unknown}
status: pending
---
```

## Auto Mode

Drafting behaves the same in Auto Mode. It asks no question, so it adds no consent site and needs no Auto Mode marker. Consent happens later, at the user's review through `/planwise feedback --drafts`.
