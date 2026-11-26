// Constants for the plan-exit answer: the two decision literals, the log lines and the opt-in marker.
/** The marker line a `/planwise plan --plan-mode` turn prints as the last line of its answer. */
export const PLAN_MARKER_RE = /^PLANWISE PLAN-MODE: command=plan policy=auto$/

/** How long a plan-mode arming waits for its turn to start before it expires, in milliseconds. */
export const PLAN_SESSION_WAIT_MS = 300000

/**
 * The answer to an ExitPlanMode dialog: allow it and send no mode change. The tool then returns the session to
 * the mode it had before plan mode and puts back the allow rules it set aside. A `setMode` here would skip both.
 */
export const EXIT_DECISION = { behavior: 'allow', updatedInput: {} } as const

/** The answer to an EnterPlanMode dialog. `updatedInput` is required: without it the gate ignores the allow. */
export const ENTER_DECISION = { behavior: 'allow', updatedInput: {} } as const

/** Logged on the debug channel when the module leaves a dialog to the person. */
export const LEFT_TO_USER = 'plan exit: dialog left to the user (no planwise context)'

/** The transcript line for an answered dialog. */
export const answeredLine = (tool: string, context: string): string =>
  tool === 'ExitPlanMode'
    ? `plan exit: answered ExitPlanMode (context=${context}, mode=previous)`
    : `plan exit: answered EnterPlanMode (context=${context})`
