// Pure decisions behind the boundary: when to go, defer or abandon, which
// pending boundary is current, when the latch is released, how a failure reads.
// Nothing here calls the engine, so node:test covers all of it.
import type { LoopMarker } from './parse-marker.ts'

/** What a boundary check does next. */
export type BoundaryStep = 'go' | 'defer' | 'abandon'

/** What `stepOf` reads. `deferrals` counts the deferrals already made. */
export type StepInput = {
  turnRunning: boolean
  pendingQuestion: boolean
  deferrals: number
  max: number
}

/**
 * Pick the next step of a boundary check. A busy session defers until the cap, then abandons.
 *
 * @param input the liveness flags and the deferral count
 * @returns `go` when the session is idle, else `defer` or `abandon`
 */
export const stepOf = (input: StepInput): BoundaryStep => {
  if (!input.turnRunning && !input.pendingQuestion) return 'go'
  return input.deferrals >= input.max ? 'abandon' : 'defer'
}

/** The latch key of one marker. */
export const keyOf = (marker: LoopMarker): string => marker.runId + ':' + marker.doneId

/**
 * Release the latch after a boundary failed, so the same marker printed again can start a new boundary.
 *
 * @param lastKey the latch now
 * @param key the key of the boundary that failed
 * @returns `null` when the latch still holds that key, else the latch unchanged
 */
export const releaseLatch = (lastKey: string | null, key: string): string | null => (lastKey === key ? null : lastKey)

/**
 * Whether a pending boundary is still the current one. A newer marker or a session end bumps the current token.
 *
 * @param token the token the boundary was scheduled under
 * @param current the token now
 * @returns true when the boundary may still act
 */
export const isCurrent = (token: number, current: number): boolean => token === current

/** The fields of a hook failure that the text reads. */
export type FailureLike = { kind: string; message?: string }

/**
 * Write a hook failure as one readable phrase.
 *
 * @param failure the engine's failure record
 * @returns the kind, plus the message when there is one
 */
export const failureText = (failure: FailureLike): string =>
  failure.message === undefined || failure.message === '' ? failure.kind : failure.kind + ': ' + failure.message
