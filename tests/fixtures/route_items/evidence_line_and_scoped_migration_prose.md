---
id: 439
title: "132 legacy backlog titles over 120 characters print one truncation warning each on every index run"
priority: Low
status: NOT_STARTED
abbrev: INFRA
created: 2026-10-06
blocks: []
route_hint: B
route_evidence: "option (a) edits the frontmatter of 132 item files (28 active, 104 archived) and needs a per-file title shortening plus one regeneration; option (b) is a three-site script change with tests"
route_dated: 2026-10-06
---

# BB-439-INFRA-LegacyOverCapTitlesFloodTruncationWarnings: 132 legacy backlog titles over 120 characters print one truncation warning each on every index run

**Priority:** Low
**Domain:** INFRA
**Filed:** 2026-10-06 from the closeout of BB-437.

---

## Summary

`generate_backlog_index.py --check` and `--write` print one `Warning: title truncated to 120 chars for item NNN` line to stderr for every item whose frontmatter `title:` exceeds 120 characters. On the live backlog that is 132 identical lines per run. The `/planwise backlog` handler tells the agent to surface these warnings to the user verbatim, so every triage run shows the wall, and a new warning of a different kind is easy to miss. `update_backlog.py --create` now rejects an over-cap title, so these 132 titles predate the cap and no new item adds to them. Pick one treatment and remove the noise.

## Problem

**Evidence:** 132 warning lines, one per item, no duplicate ids — verified 2026-10-06 by running the generator and counting its stderr:

```bash
python C:/Users/gabgo/.claude/plugins/cache/planwise-marketplace/planwise/1.0.5.2/scripts/generate_backlog_index.py --config planwise/config.yaml --check
# run from C:/Users/gabgo/source/repos/planwise-development; stdout redirected to one file, stderr to another
# stdout ended with: No drift detected. The index matches item frontmatter.   exit 0
# stderr: 132 lines of the form  Warning: title truncated to 120 chars for item 095
```

The originating session estimated about 114. The re-count at filing gives 132, so the originating figure was low by 18. The ids, sorted:

```
014 018 021 023 024 025 026 027 028 029 032 033 034 035 036 037 038 040 041 042 043 044 045 046 047 048
050 051 052 053 054 055 056 057 058 059 060 061 065 066 067 068 069 070 071 072 073 074 075 076 077 078
079 080 081 082 083 084 085 086 087 088 089 090 091 092 093 094 095 096 097 098 099 100 101 102 103 104
105 106 107 108 109 110 111 112 113 114 115 116 117 129 172 173 174 175 176 177 181 183 184 185 193 196
197 198 199 200 201 203 204 205 206 207 208 209 210 211 212 213 214 215 216 217 218 219 220 221 222 223
376 411
```

**Evidence:** split between live and archived files — verified 2026-10-06 from the same run: the first 28 warning lines name active items (095, 105, 184, 196-199, 204-209, 211-223, 376, 411), and the other 104 name archived items. Active files live in `planwise/Backlog/`, archived files in `planwise/Backlog/Archive/`.

Do not re-derive the population from a raw line-length regex over the item files. A crude regex over `title:` lines in `planwise/Backlog/**/BB-*.md` returned 150 files on 2026-10-06 because of quoting and boundary effects. The generator's own warning list is the authoritative set.

**Evidence:** the warning is printed once per item at three sites in the generator, each a `for item_id in report["truncated_ids"]` loop — verified 2026-10-06 by `Grep pattern='title truncated' path='cloned-repos/planwise/plugins/planwise/scripts'`: `generate_backlog_index.py` lines 432-436 (the `--write` path), 469-473 (the `--check` path) and 582-586 (the third report path). Line numbers drift, so re-locate them by the quoted text.

**Evidence:** the handler instruction that turns the warnings into a wall — verified 2026-10-06 by `Grep pattern='title truncated' path='C:/Users/gabgo/.claude/plugins/cache/planwise-marketplace/planwise/1.0.5.2/handlers/backlog.md'`, line 86: "If it prints a stderr `Warning: title truncated …` or `Anomaly: …` line, surface it to the user verbatim rather than swallowing it". The backlog-author agent's step 3 (`agents/backlog-author.md` line 129) also tells the filing agent to report a truncated-title item in `ISSUES`.

**Evidence:** the writer side is closed — verified 2026-10-06 by `Read planwise/Backlog/Archive/BB-237-01-INFRA-WritersEnforceTitleCapAtWriteTime.md` (status COMPLETE 2026-09-23): `update_backlog.py --create` rejects a `--feature` longer than `TITLE_MAX_LEN` and writes nothing. That item scoped the then-129 pre-existing over-cap titles out on purpose: "A separate, explicitly-scoped migration can trim them if the truncation report proves noisy; this item stops the population growing." This is that migration, filed because the report is now noisy. Item 237 does not cover it, and no open item does: `Grep pattern='truncat|120 char|title cap' path='planwise/Backlog/00-Index-Backlog.md'` matched only an unrelated row about a Master Plan read cap.

**Evidence:** a precedent for one summary line — verified 2026-10-06 by `Grep pattern='title truncated|TITLE_MAX_LEN' path='C:/Users/gabgo/.claude/plugins/cache/planwise-marketplace/planwise/1.0.5.2'`: the lessons index generator (`scripts/lessons_index_run.py` line 108) prints `{n} title(s) truncated at {TITLE_MAX_LEN} ...` as one line naming the count, and `references/lessons-schema.md` line 158 documents it ("A run that truncates one or more titles prints one stderr summary line naming the count, never a line per title"). The backlog generator has no such summary.

Rendering is not at risk. The index cell is the frontmatter title cut at a word boundary, and `--check` reports no drift. The problem is the stderr volume and the handler's verbatim-surface instruction.

## Proposed Solution

Pick one coherent treatment and state why in the closing note. Prefer (a) unless it is shown to lose information.

**(a) Shorten each legacy title in frontmatter to 120 characters or fewer.** Move the overflow into the item's `## Summary` (or `## Problem` for the promotion body shape, which has no Summary). This fixes the data and matches what the writer cap already requires of new items. It is a bulk edit of 132 files, so:

- Keep every file's `id:` and its file name unchanged.
- Edit only the `title:` line and add the overflow to the body. Never drop the overflow text.
- Read the title the current index renders (the word-boundary cut) before choosing the new title, so the index Title cell changes as little as possible.
- Check scoring and routing side effects. The title text is an input to the scoring factors and the route recommendation, so a shortened title can move a Score cell. Compare the index before and after.
- Regenerate the index once at the end with `generate_backlog_index.py --config planwise/config.yaml --write`, after the last file is edited.
- A writer must not edit frontmatter in steady state, so run this as one explicitly scoped migration, not as a new writer behaviour.

**(b) Change the generator so the warning prints once.** Replace each of the three per-item loops with one line that names the count and the ids, in the shape the lessons generator already uses. Update `handlers/backlog.md` line 86 and the `--check` tests. This leaves 132 over-cap titles on disk and keeps the noise out of the transcript. It is also the right shape if any future hand-edit re-introduces an over-cap title.

If both are wanted, do (a) first. After (a) the generator prints nothing, and (b) becomes optional hardening.

## Acceptance Criteria

- [ ] `python <plugin_root>/scripts/generate_backlog_index.py --config planwise/config.yaml --check`, run from the project root, prints no `title truncated` line, or exactly one summary line that names the count
- [ ] The same run still ends with `No drift detected. The index matches item frontmatter.` and exits 0
- [ ] Under option (a): all 132 files keep their `id:` and file name, no overflow text is lost (each shortened title's removed words appear in the item body), and the index was regenerated once
- [ ] Under option (a): a before-and-after comparison of the index Score cells for the 132 ids is recorded, with any change explained
- [ ] Under option (b): `handlers/backlog.md` no longer tells the agent to surface a per-item line, and the generator tests cover the one-line summary and the empty case
- [ ] The count and id list were re-measured at execution time, not taken from this item

## Related

- `cloned-repos/planwise/plugins/planwise/scripts/generate_backlog_index.py` — three `title truncated` print loops (lines 432-436, 469-473, 582-586 on 2026-10-06)
- `cloned-repos/planwise/plugins/planwise/scripts/backlog_index_schema.py` — `TITLE_MAX_LEN = 120`
- `cloned-repos/planwise/plugins/planwise/scripts/lessons_index_run.py` — the one-summary-line precedent
- `cloned-repos/planwise/plugins/planwise/handlers/backlog.md` — Phase 1, the verbatim-surface instruction
- `planwise/Backlog/Archive/BB-237-01-INFRA-WritersEnforceTitleCapAtWriteTime.md` — the writer-side cap that left these titles out of scope
- Originating item: BB-437 (closed 2026-10-06)

---

*Created: 2026-10-06*
