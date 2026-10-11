// Finds the loop marker in a finished answer.
// The last marker in the text wins.
import { MARKER_RE } from './names.ts'

/** The four fields of one marker line. */
export type LoopMarker = {
  runId: string
  doneId: string
  remaining: number
  statePath: string
}

/**
 * Parse the whole answer text and return the last marker, or `null` when none matches.
 *
 * @param answer the full text of the finished answer
 * @returns the last marker found, or `null`
 */
export const parseLoopMarker = (answer: string): LoopMarker | null => {
  const matches = [...answer.matchAll(MARKER_RE)]
  const last = matches[matches.length - 1]
  if (last === undefined) return null
  return {
    runId: last[1] ?? '',
    doneId: last[2] ?? '',
    remaining: Number(last[3]),
    statePath: last[4] ?? '',
  }
}
