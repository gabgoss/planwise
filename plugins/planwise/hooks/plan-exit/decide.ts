// Decides whether a plan dialog is answered by the module or left to the person,
// and whether the next queued loop item is one that may arm that answer.
import { ENTER_DECISION, EXIT_DECISION } from './names.ts'

export type PlanContext = 'none' | 'loop' | 'plan-session'

/** A decision literal as the engine takes it: plain mutable arrays, no readonly tuple. */
export type PlanDecision = {
  behavior: 'allow'
  updatedInput: Record<string, unknown>
  updatedPermissions?: { type: 'setMode'; mode: 'acceptEdits'; destination: 'session' }[]
}

export type PlanAnswer = { action: 'answer'; decision: PlanDecision } | { action: 'next' }

/**
 * @param input the asking tool's name and the session's arming state
 * @returns the decision to give, or `next` to leave the dialog to the person
 */
export const decide = (input: { tool: string; context: PlanContext }): PlanAnswer => {
  if (input.context !== 'loop' && input.context !== 'plan-session') return { action: 'next' }
  if (input.tool === 'ExitPlanMode') {
    return { action: 'answer', decision: { ...EXIT_DECISION, updatedInput: {}, updatedPermissions: [...EXIT_DECISION.updatedPermissions] } }
  }
  if (input.tool === 'EnterPlanMode') return { action: 'answer', decision: { ...ENTER_DECISION, updatedInput: {} } }
  return { action: 'next' }
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

/**
 * Whether the next queued item of a live loop run is a plan item. Any parse error or shape mismatch means no.
 *
 * @param text the run file's text
 * @param runId the run id the marker named
 * @returns true only for an open run with that id whose first queued item has disposition `plan`
 */
export const nextIsPlanItem = (text: string, runId: string): boolean => {
  let run: unknown
  try {
    run = JSON.parse(text)
  } catch {
    return false
  }
  if (!isRecord(run) || run.run_id !== runId || run.ended !== null) return false
  const { queue, queue_meta: meta } = run
  if (!Array.isArray(queue) || typeof queue[0] !== 'string' || !isRecord(meta)) return false
  const entry = meta[queue[0]]
  return isRecord(entry) && entry.disposition_at_init === 'plan'
}
