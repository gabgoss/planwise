// The slug and file name rules for a draft. The slug rule mirrors slugify in
// scripts/feedback_drafts.py.
import type { Kind } from './names.ts'

/** The longest slug, in characters. */
const SLUG_MAX = 40

/**
 * Turn a title into a slug: lowercase, each run of non-alphanumerics becomes one
 * hyphen, trimmed, cut to 40 characters, a hyphen the cut exposes is stripped,
 * and an empty result becomes `untitled`.
 *
 * @param title the draft title
 * @returns the slug
 */
export const slugOf = (title: string): string => {
  const hyphenated = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  const cut = hyphenated.slice(0, SLUG_MAX).replace(/-+$/, '')
  return cut === '' ? 'untitled' : cut
}

/**
 * Build a draft file name. A collision suffix `-2` to `-9` goes after the slug.
 *
 * @param date the day as YYYY-MM-DD
 * @param kind the draft kind
 * @param slug the slug from `slugOf`
 * @param n the attempt number, 1 or absent for the plain name
 * @returns the file name
 */
export const draftFileName = (date: string, kind: Kind, slug: string, n?: number): string =>
  date + '-draft-' + kind + '-' + slug + (n !== undefined && n > 1 ? '-' + String(n) : '') + '.md'
