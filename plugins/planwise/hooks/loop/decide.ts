// Decides what the module does when a turn completes.
// A pure function of its input; it reads no module state.
import type { LoopMarker } from './parse-marker.ts'

/** What `decide` reads. `lastKey` is the latch, compared as `run + ':' + done`. */
export type DecideInput = {
  marker: LoopMarker | null
  lastKey: string | null
  turnRunning: boolean
  pendingQuestion: boolean
}

export type DecideReason =
  | 'no-marker'
  | 'remaining-zero'
  | 'already-latched'
  | 'turn-running'
  | 'pending-question'
  | 'ok'

export type Decision = {
  action: 'reenter' | 'defer' | 'none'
  reason: DecideReason
}

/**
 * Pick the action for one completed turn.
 *
 * @param input the marker, the latch and the two liveness flags
 * @returns the action and the reason for it
 */
export const decide = (input: DecideInput): Decision => {
  const { marker } = input
  if (marker === null) return { action: 'none', reason: 'no-marker' }
  if (marker.remaining === 0) return { action: 'none', reason: 'remaining-zero' }
  if (input.lastKey === marker.runId + ':' + marker.doneId) {
    return { action: 'none', reason: 'already-latched' }
  }
  if (input.turnRunning) return { action: 'defer', reason: 'turn-running' }
  if (input.pendingQuestion) return { action: 'defer', reason: 'pending-question' }
  return { action: 'reenter', reason: 'ok' }
}
