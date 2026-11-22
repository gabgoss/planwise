// Reads a queued draft back from its file, so session start can offer a draft that an earlier
// session wrote on the review card. Pure text work: it imports nothing from the engine, so node
// tests load it. The file shape is the one render.ts writes: quoted frontmatter, then one
// `### ` heading per body field.
import { KINDS, KIND_FIELDS } from './names.ts'
import type { Kind } from './names.ts'

/** A queued draft as session start needs it for the review card. */
export type QueuedDraft = {
  draftId: string
  createdAt: string
  kind: Kind
  title: string
  sessionId: string
  fields: Record<string, string>
}

/** The frontmatter values of a draft file, or null when the file opens with no frontmatter. */
const frontmatterOf = (text: string): Record<string, string> | null => {
  const lines = text.split(/\r?\n/)
  if (lines[0] !== '---') return null
  const end = lines.indexOf('---', 1)
  if (end < 0) return null
  const values: Record<string, string> = {}
  for (const line of lines.slice(1, end)) {
    const match = /^([a-z_]+): "([^"\r\n]*)"$/.exec(line)
    if (match !== null) values[match[1]!] = match[2]!
  }
  return values
}

/** The text under `### heading`, up to the next `### ` heading, trimmed. Empty when absent. */
const sectionOf = (text: string, heading: string): string => {
  const lines = text.split(/\r?\n/)
  const start = lines.indexOf('### ' + heading)
  if (start < 0) return ''
  const rest = lines.slice(start + 1)
  const stop = rest.findIndex((line) => line.startsWith('### '))
  return (stop < 0 ? rest : rest.slice(0, stop)).join('\n').trim()
}

/**
 * The draft in one file, when its status is `queued` and its frontmatter names a known kind, an
 * id, a title and a creation time. Any other file reads as null, so a half-written or foreign
 * file is skipped.
 */
export const queuedDraftOf = (text: string): QueuedDraft | null => {
  const head = frontmatterOf(text)
  if (head === null || head['status'] !== 'queued') return null
  const kind = head['kind'] as Kind
  if (!KINDS.includes(kind)) return null
  const draftId = head['draft_id'] ?? ''
  const title = head['title'] ?? ''
  const createdAt = head['created_at'] ?? ''
  if (draftId === '' || title === '' || createdAt === '') return null
  const fields: Record<string, string> = {}
  for (const [name, heading] of KIND_FIELDS[kind]) fields[name] = sectionOf(text, heading)
  return { draftId, createdAt, kind, title, sessionId: head['source_session_id'] ?? '', fields }
}

/** The newest queued draft among file texts, by creation time, or null when none is queued. */
export const newestQueued = (texts: readonly string[]): QueuedDraft | null => {
  let newest: QueuedDraft | null = null
  for (const text of texts) {
    const draft = queuedDraftOf(text)
    if (draft !== null && (newest === null || draft.createdAt > newest.createdAt)) newest = draft
  }
  return newest
}

/** True for a name the producer gives a draft file: `<date>-draft-<kind>-<slug>[-n].md`. */
export const isDraftFileName = (name: string): boolean => /^\d{4}-\d{2}-\d{2}-draft-(bug|lesson|idea)-.+\.md$/.test(name)
