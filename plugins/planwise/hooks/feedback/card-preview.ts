// Pure helpers for the review card. They import nothing from the engine, so node tests load them.
import type { Kind } from './names.ts'
import { scrub } from './render.ts'

const len = (text: string): number => Array.from(text).length

/** Fold every run of whitespace to one space. */
const fold = (text: string): string => text.replace(/\s+/g, ' ').trim()

/** The label the card shows before the title. */
export const kindLabel = (kind: Kind): string => (kind === 'bug' ? 'Bug draft' : kind === 'lesson' ? 'Lesson draft' : 'Idea draft')

/**
 * How many preview rows fit. The card spends three rows besides the preview: the title row,
 * one margin row and the button row. It shows at most four preview rows, and none under four rows.
 */
export const previewRows = (maxRows: number): number => (maxRows < 4 ? 0 : Math.min(4, maxRows - 3))

/** Wrap text at `width` characters. A word longer than the width is split. */
const wrap = (text: string, width: number): string[] => {
  const lines: string[] = []
  let cur = ''
  for (const word of text.split(' ')) {
    if (word === '') continue
    let rest = word
    while (len(rest) > width) {
      if (cur !== '') {
        lines.push(cur)
        cur = ''
      }
      const chars = Array.from(rest)
      lines.push(chars.slice(0, width).join(''))
      rest = chars.slice(width).join('')
    }
    if (cur === '') cur = rest
    else if (len(cur) + 1 + len(rest) <= width) cur += ' ' + rest
    else {
      lines.push(cur)
      cur = rest
    }
  }
  if (cur !== '') lines.push(cur)
  return lines
}

/**
 * Wrap a draft's details to the band's width and keep the first `maxLines` lines. When text is
 * cut, the last kept line ends in an ellipsis and stays within the width.
 */
export const previewLines = (details: string, columns: number, maxLines = 4): string[] => {
  const width = Math.max(1, Math.floor(columns))
  if (maxLines <= 0) return []
  const all = wrap(fold(details), width)
  if (all.length <= maxLines) return all
  const kept = all.slice(0, maxLines)
  let chars = Array.from(kept[maxLines - 1] ?? '')
  if (chars.length >= width) chars = chars.slice(0, width - 1)
  kept[maxLines - 1] = chars.join('') + '…'
  return kept
}

/** One row: the kind label, a colon and the title, cut to `columns` with an ellipsis. */
export const fitTitle = (label: string, title: string, columns: number): string => {
  const width = Math.max(1, Math.floor(columns))
  const text = label + ': ' + fold(title)
  if (len(text) <= width) return text
  return Array.from(text).slice(0, width - 1).join('') + '…'
}

/**
 * The first body field of a draft, scrubbed of the project roots, folded to one line and cut to
 * 512 characters. The scrub runs first, so a root that straddles the cut cannot leak a partial path.
 */
export const previewSourceOf = (kind: Kind, fields: Record<string, string>, roots: readonly string[]): string => {
  const source = kind === 'bug' ? fields['what_happened'] : fields['learned']
  return Array.from(fold(scrub(source ?? '', roots))).slice(0, 512).join('')
}

/**
 * The value of an atom that holds the card's draft, after a press that spends the draft with
 * `draftId`. It clears the draft only when the atom still holds that same draft, so a newer
 * draft that arrived during the press survives. A press with no id clears nothing.
 */
export const clearIfSame = <T extends { draftId: string }>(current: T | null, draftId: string | null): T | null =>
  current !== null && draftId !== null && current.draftId === draftId ? null : current

/** A press is stale when the card's draft is already gone. A stale press changes nothing. */
export const isStalePress = (draft: object | null): draft is null => draft === null

/** The second dismissal asks to turn drafts off, and only when the draft knows its config path. */
export const shouldAskTurnOff = (dismissals: number, configPath: string): boolean => dismissals === 2 && configPath !== ''
