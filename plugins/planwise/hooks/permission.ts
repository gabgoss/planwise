// The permission step for a tool this module serves itself. A tool.call hook that answers with
// { result } never reaches core, and core is where the permission prompt runs. So a plugin tool
// served by a hook gets no prompt unless the hook asks for the decision itself. This step asks
// the engine for its verdict on the call (the session's mode and permission rules) and acts on it.

/** The two engine calls the step needs. Each module spells them in its own host table over `$`. */
export type Gate = {
  check: (tool: string, input: unknown) => Promise<{ decision: 'allow' | 'ask' | 'deny'; reason?: string }>
  ask: (question: string, options: readonly string[]) => Promise<string>
}

export const ALLOW_LABEL = 'Allow'
export const DENY_LABEL = 'Deny'

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/**
 * Decides whether one call may run. Returns null to run it, or the text of a refusal.
 *
 * - allow: run.
 * - deny: refuse with the engine's reason.
 * - ask: put the question to the user. An Allow answer runs the call. Any other answer refuses it.
 *   A question that is dismissed or cannot be asked (a headless run) also refuses it.
 *
 * It never throws. A failed check refuses the call, because nothing has run yet.
 *
 * @param summary what the call will do, for the question: "build_plan to build plans/X"
 */
export async function permit(gate: Gate, tool: string, input: unknown, summary: string): Promise<string | null> {
  let verdict: { decision: 'allow' | 'ask' | 'deny'; reason?: string }
  try {
    verdict = await gate.check(tool, input)
  } catch (err) {
    return 'the permission check failed: ' + errText(err)
  }
  if (verdict.decision === 'allow') return null
  if (verdict.decision === 'deny') return verdict.reason ?? 'the permission settings refuse this call'
  let answer: string
  try {
    answer = await gate.ask(`Allow ${summary}?`, [ALLOW_LABEL, DENY_LABEL])
  } catch {
    return `this call needs permission and no one could be asked; add an allow rule for ${tool} to run it without a question`
  }
  return answer === ALLOW_LABEL ? null : 'the user did not allow this call'
}

/**
 * The check alone, for a tool that must stay silent. A deny refuses the call, and an allow or an
 * ask runs it with no question. Returns null to run it, or the text of a refusal. It never throws.
 * A failed check refuses the call, because nothing has run yet.
 */
export async function refusedByRule(check: Gate['check'], tool: string, input: unknown): Promise<string | null> {
  let verdict: { decision: 'allow' | 'ask' | 'deny'; reason?: string }
  try {
    verdict = await check(tool, input)
  } catch (err) {
    return 'the permission check failed: ' + errText(err)
  }
  return verdict.decision === 'deny' ? verdict.reason ?? 'the permission settings refuse this call' : null
}
