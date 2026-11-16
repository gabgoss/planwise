# Release notes

**Purpose:** Hold the hand-written notes of each release. The release workflow publishes them.

## How it works

A release is one pull request that changes the plugin version with `tools/bump_version.py`. Add the notes for that version to the same pull request, as `release-notes/X.Y.Z.md`. The file name is the new version and nothing else.

When the pull request merges, `.github/workflows/release.yml` tags the merge commit `planwise--vX.Y.Z` and publishes a GitHub Release. It uses `release-notes/X.Y.Z.md` as the release body. When that file is missing or empty, GitHub builds the body from the merged pull request titles.

This folder sits outside `plugins/planwise/`, so it never ships to a plugin user.

## Format

Write for a plugin user who reads the release page. Keep sentences short, and say what changed for them.

| Part | Content |
|---|---|
| Opening paragraph | Three to five sentences that sum up the release. No heading comes before it |
| Themed sections | One `## <emoji> <theme>` section per area of change. Each bullet starts with a bold lead phrase and a full stop |
| `## 🐛 Fixes` | One plain bullet per fix. State the old behavior and the new one |
| `## ✅ Issues closed in this release` | One bullet per issue: a link, a dash, and one sentence |

Leave a section out when it would be empty.

**Skeleton**

```markdown
This release <what it does for the user>. <Second point.> <Third point.>

## 🧭 <Theme>

- **<Lead phrase>.** <What changed, in one or two sentences.>

## 🐛 Fixes

- <What was wrong, and what happens now.>

## ✅ Issues closed in this release

- [#<number>](https://github.com/<owner>/<repo>/issues/<number>) — <One sentence.>
```

`tests/test_release_notes.py` checks each file in this folder: a semver file name, a non-empty body, and an opening paragraph before the first heading.
