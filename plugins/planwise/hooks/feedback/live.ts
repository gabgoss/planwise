// Tells the review card whether its draft can still be posted, so a card does not outlive a post
// that another session made. Pure text work: it imports nothing from the engine, so node tests
// load it. The rule mirrors the post script's `_resolve_draft`, minus the expiry clock, which the
// script owns. The file shapes are the ones the real producers write. The hooks tool writes quoted
// frontmatter values. The draft script rewrites `status` and adds `promoted_to` as bare values, so
// the reader here takes both forms. The post script writes a `.posted` sidecar beside the promoted
// file, or beside a comment draft made from it.
import { isDraftFileName } from './queued.ts'

/** The frontmatter values of a draft file, quoted or bare, or null when the file has no frontmatter. */
const frontmatterOf = (text: string): Record<string, string> | null => {
  const lines = text.split(/\r?\n/)
  if (lines[0] !== '---') return null
  const end = lines.indexOf('---', 1)
  if (end < 0) return null
  const values: Record<string, string> = {}
  for (const line of lines.slice(1, end)) {
    const match = /^([a-z_]+):[ \t]*(?:"([^"\r\n]*)"|([^\r\n]*?))[ \t]*$/.exec(line)
    if (match !== null) values[match[1]!] = match[2] ?? match[3] ?? ''
  }
  return values
}

const escapeRegExp = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** True when a `.posted` sidecar records a post of this promoted file, or of a comment draft made from it. */
const wasPosted = (promoted: string, names: readonly string[]): boolean => {
  if (names.includes(promoted + '.posted')) return true
  const stem = promoted.replace(/\.md$/, '')
  const comment = new RegExp('^\\d{4}-\\d{2}-\\d{2}-comment-\\d+-' + escapeRegExp(stem) + '\\.md\\.posted$')
  return names.some((name) => comment.test(name))
}

/**
 * True when the draft with this id can still be posted, given the folder's file names and the
 * text of each draft file in it.
 *
 * | The draft file says | Result |
 * | `status: queued` | live |
 * | `status: promoted`, the promoted file present, no `.posted` sidecar | live: a kept draft is retried |
 * | `status: promoted` with a sidecar | gone |
 * | any other status, or no file with this id | gone |
 */
export const draftIsLive = (draftId: string, names: readonly string[], texts: Readonly<Record<string, string>>): boolean => {
  for (const name of names) {
    const text = texts[name]
    if (text === undefined) continue
    const head = frontmatterOf(text)
    if (head === null || head['draft_id'] !== draftId) continue
    if (head['status'] === 'queued') return true
    if (head['status'] !== 'promoted') return false
    const promoted = head['promoted_to'] ?? ''
    return promoted !== '' && names.includes(promoted) && !wasPosted(promoted, names)
  }
  return false
}

/** The two file-system calls the check makes. The card passes its own host members. */
export type LiveIo = {
  list: (path: string) => Promise<readonly { kind: string; name: string }[]>
  read: (path: string) => Promise<unknown>
}

/**
 * Reads the drafts folder and applies draftIsLive. Any list or read failure answers true, so a
 * disk fault never hides a draft that can still be posted. The press runs the post script's own
 * check, which is the backstop.
 */
export const draftStillOffered = async (io: LiveIo, dir: string, draftId: string): Promise<boolean> => {
  try {
    const entries = await io.list(dir)
    const names = entries.map((entry) => entry.name)
    const texts: Record<string, string> = {}
    for (const entry of entries) {
      if (entry.kind === 'file' && isDraftFileName(entry.name)) texts[entry.name] = String(await io.read(dir + '/' + entry.name))
    }
    return draftIsLive(draftId, names, texts)
  } catch {
    return true
  }
}
