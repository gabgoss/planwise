// Release tags and version order for the update check. A pure module with no engine import, so
// node tests can load it. It reads a GitHub release list and compares plain versions.

/** A release tag: `planwise--vX.Y.Z`, or a bare version such as `1.0.5.3`. A suffix such as `-rc1` never matches. */
const TAG_RE = /^(?:planwise--v)?(\d+(?:\.\d+)*)$/

/**
 * The plain version a release tag names.
 *
 * @param tag the release's tag name
 * @returns the version, or `null` for a tag of another shape or a prerelease suffix
 */
export const versionOfTag = (tag: string): string | null => {
  const match = TAG_RE.exec(tag.trim())
  return match === null ? null : (match[1] ?? null)
}

/** The numeric parts of a version. A part that is not a number counts as 0. */
const partsOf = (version: string): number[] =>
  version
    .trim()
    .split('.')
    .map((part) => {
      const n = Number.parseInt(part, 10)
      return Number.isNaN(n) ? 0 : n
    })

/**
 * Compares two plain versions part by part. The shorter one is padded with zeros, so
 * `1.0.5` equals `1.0.5.0`.
 *
 * @returns -1 when `a` is older, 0 when equal, 1 when `a` is newer
 */
export const compareVersions = (a: string, b: string): number => {
  const left = partsOf(a)
  const right = partsOf(b)
  const length = Math.max(left.length, right.length)
  for (let i = 0; i < length; i += 1) {
    const l = left[i] ?? 0
    const r = right[i] ?? 0
    if (l !== r) return l < r ? -1 : 1
  }
  return 0
}

/**
 * The highest version in a GitHub release list. A draft, a prerelease and a tag of another
 * shape are skipped.
 *
 * @param releases the parsed body of the releases endpoint
 * @returns the highest version, or `null` when none qualifies
 */
export const latestRelease = (releases: unknown): string | null => {
  if (!Array.isArray(releases)) return null
  let best: string | null = null
  for (const item of releases as unknown[]) {
    if (typeof item !== 'object' || item === null) continue
    const release = item as Record<string, unknown>
    if (release['draft'] === true || release['prerelease'] === true) continue
    const tag = release['tag_name']
    if (typeof tag !== 'string') continue
    const version = versionOfTag(tag)
    if (version === null) continue
    if (best === null || compareVersions(version, best) > 0) best = version
  }
  return best
}
