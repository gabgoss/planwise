// Backlog loop hooks module. Contract: handlers/backlog-Part-2-LoopMode.md.
// After a one-item backlog session prints its BACKLOG LOOP marker, this module
// compacts the session and re-enters the handler with --loop-resume.
import type { CommandInfo, EngineInterface, On, PluginOptions, Timer } from 'claude-code'

import { register as registerAgentGuard } from './agent-guard.ts'
import { hostOf as buildPlanHostOf, onSessionStart as buildPlanStart, register as registerBuildPlan } from './build-plan.ts'
import { currentDraftsDir, draftsDirOf, hostOf as draftFeedbackHostOf, onSessionStart as draftFeedbackStart, register as registerDraftFeedback } from './draft-feedback.ts'
import { blockedHostOf, register as registerBlockedCard } from './blocked-card.tsx'
import { recountBlocked } from './feedback/blocked.ts'
import { register as registerFeedbackCard } from './feedback-card.tsx'
import { register as registerUpdateBanner } from './update-banner.tsx'
import { hostOf as updateCheckHostOf, onSessionStart as updateCheckStart } from './update-check.ts'
import { failureText, isCurrent, keyOf, releaseLatch, stepOf } from './loop/boundary.ts'
import type { BoundaryStep } from './loop/boundary.ts'
import { decide } from './loop/decide.ts'
import { DEFER_MS, MAX_DEFERRALS } from './loop/names.ts'
import type { LoopMarker } from './loop/parse-marker.ts'
import { parseLoopMarker } from './loop/parse-marker.ts'
import { reentryArgs, skillNameOf } from './loop/reentry.ts'
import { steerText } from './loop/steer-text.ts'
import { decide as decidePlanExit, nextIsPlanItem } from './plan-exit/decide.ts'
import type { PlanContext } from './plan-exit/decide.ts'
import { endsOnLoopMarker, isPlanModeMarker } from './plan-exit/marker.ts'
import { LEFT_TO_USER, PLAN_SESSION_WAIT_MS, answeredLine } from './plan-exit/names.ts'

type Host = {
  after: (ms: number, fn: () => void) => Timer
  compact: (instructions: string) => Promise<{ skip?: string }>
  runCommand: (command: string, args: string) => Promise<unknown>
  listCommands: () => Promise<CommandInfo[]>
  read: (path: string) => Promise<unknown>
  uiLog: (text: string, to?: 'debug' | 'transcript') => void
}

/** One record of module memory. Every field resets with the process. */
type Session = {
  skillName: string | null
  interactive: boolean
  turnRunning: boolean
  pendingQuestion: boolean
  lastKey: string | null
  timer: Timer | null
  token: number
  /** Which planwise context may answer a plan dialog. 'none' leaves every dialog to the person. */
  planContext: PlanContext
  /** Key of the last marker that was the final line of its answer, or null. Only that marker's boundary arms. */
  armKey: string | null
  /** The expiry of a 'plan-session' arming that still waits for its turn. Separate from the boundary's `timer`. */
  planTimer: Timer | null
}

/**
 * The closure table over `$`. It sits at module scope because the validator refuses a `$` handed
 * to a nested function. Every engine call the module makes is spelled here, one per member.
 */
function hostOf($: EngineInterface): Host {
  return {
    after: (ms: number, fn: () => void) => $.clock.after(ms, fn),
    compact: (instructions: string) => $.session.compact({ instructions }),
    runCommand: (command: string, args: string) => $.command.run({ command, args }),
    listCommands: () => $.command.list(),
    read: (path: string) => $.fs.read(path),
    uiLog: (text: string, to?: 'debug' | 'transcript') => (to === undefined ? $.ui.log(text) : $.ui.log(text, { to })),
  }
}

export function register(on: On, options: PluginOptions) {
  void options
  registerDraftFeedback(on, options)
  registerBuildPlan(on, options)
  registerFeedbackCard(on, options)
  registerBlockedCard(on, options)
  // AbovePrompt hooks nest first-outermost: the feedback card, then the blocked banner, then the update card.
  registerUpdateBanner(on, options)
  registerAgentGuard(on, options)
  // `interactive` starts true: a module reload re-runs register() without a new session.start.
  const session: Session = {
    skillName: null,
    interactive: true,
    turnRunning: false,
    pendingQuestion: false,
    lastKey: null,
    timer: null,
    token: 0,
    planContext: 'none',
    armKey: null,
    planTimer: null,
  }

  /** Logs a failure of one hook or of the boundary. Never throws. */
  const failed = (host: Host, where: string, why: string): void => {
    host.uiLog(`backlog loop: ${where} failed: ${why}`)
  }

  /** Cancels the wait of a plan-mode arming. The arming itself stays. */
  const cancelPlanWait = (): void => {
    session.planTimer?.cancel()
    session.planTimer = null
  }

  /** Leaves every dialog to the person again. */
  const disarm = (): void => {
    cancelPlanWait()
    session.planContext = 'none'
  }

  /** Arms the turn after a plan-mode marker. The arming expires when no turn starts in time. */
  const armPlanSession = (host: Host): void => {
    cancelPlanWait()
    session.planContext = 'plan-session'
    const timer = host.after(PLAN_SESSION_WAIT_MS, () => {
      // Only the arming this timer was set for may expire here.
      if (session.planTimer === timer) disarm()
    })
    session.planTimer = timer
  }

  /** True when the run file says the next queued item is a plan item. An unreadable file means no. */
  const planItemNext = async (host: Host, marker: LoopMarker): Promise<boolean> => {
    try {
      return nextIsPlanItem(String(await host.read(marker.statePath)), marker.runId)
    } catch {
      return false
    }
  }

  /**
   * Releases the latch for one marker, so the same marker printed again can start a new boundary.
   * Only a loop arming is cleared: an older boundary must not wipe a newer plan-mode arming.
   */
  const release = (marker: LoopMarker): void => {
    session.lastKey = releaseLatch(session.lastKey, keyOf(marker))
    if (session.planContext === 'loop') disarm()
  }

  /** Resolves the re-entry skill from the command list and logs the result. */
  const resolveSkill = async (host: Host): Promise<void> => {
    session.skillName = skillNameOf(await host.listCommands())
    if (session.skillName === null) host.uiLog('backlog loop: no planwise skill found; re-entry disabled')
    else host.uiLog(`backlog loop: re-entry skill ${session.skillName}`, 'debug')
  }

  /** Arms the one pending timer. A newer boundary replaces it. */
  const schedule = (host: Host, marker: LoopMarker, token: number, deferrals: number, ms: number): void => {
    session.timer?.cancel()
    session.timer = host.after(ms, () => {
      void boundary(host, marker, token, deferrals).then(undefined, (err: unknown) => {
        release(marker)
        failed(host, 'boundary', String(err))
      })
    })
  }

  /** Defers the boundary, or gives up at the cap and releases the latch. */
  const retry = (host: Host, marker: LoopMarker, token: number, deferrals: number, step: BoundaryStep): void => {
    if (step === 'abandon') {
      host.uiLog(`backlog loop: abandoned after ${MAX_DEFERRALS} deferrals`)
      release(marker)
      return
    }
    schedule(host, marker, token, deferrals + 1, DEFER_MS)
  }

  /** Compacts, then re-enters the handler. Defers while a turn or a question is still open. */
  const boundary = async (host: Host, marker: LoopMarker, token: number, deferrals: number): Promise<void> => {
    if (!isCurrent(token, session.token)) return
    const step = stepOf({ turnRunning: session.turnRunning, pendingQuestion: session.pendingQuestion, deferrals, max: MAX_DEFERRALS })
    if (step !== 'go') return retry(host, marker, token, deferrals, step)
    if (session.skillName === null) await resolveSkill(host)
    const skillName = session.skillName
    if (skillName === null) return release(marker)
    let skipped: string | undefined
    try {
      skipped = (await host.compact(steerText(marker))).skip
    } catch {
      // Compaction rejects while a turn still runs: treat it as a deferral.
      return retry(host, marker, token, deferrals, stepOf({ turnRunning: true, pendingQuestion: false, deferrals, max: MAX_DEFERRALS }))
    }
    // Nothing is awaited between the checks below and the re-entry.
    const planNext = session.armKey === keyOf(marker) && (await planItemNext(host, marker))
    if (!isCurrent(token, session.token)) return
    if (skipped === undefined) host.uiLog(`backlog loop: compacted; re-entering run ${marker.runId}`)
    else host.uiLog(`backlog loop: compaction skipped (${skipped}); re-entering run ${marker.runId}`)
    // The only set of 'loop': arms the re-entered turn for a plan item, and only while the session is idle.
    disarm()
    if (planNext && session.armKey === keyOf(marker) && !session.turnRunning && !session.pendingQuestion) session.planContext = 'loop'
    await host.runCommand(skillName, reentryArgs(marker.runId)).then(
      () => host.uiLog(`backlog loop: re-entry resolved for run ${marker.runId}`),
      (err: unknown) => {
        release(marker)
        host.uiLog(`backlog loop: re-entry rejected: ${err instanceof Error ? err.message : String(err)}`)
      },
    )
  }

  on('session.start', async ($, e, next) => {
    disarm()
    // Arms a timer and returns: the network and the upgrade run after session.start.
    updateCheckStart(updateCheckHostOf($), e.isInteractive !== false, options)
    await draftFeedbackStart(draftFeedbackHostOf($))
    // Not awaited: a slow count script must not hold the steps below.
    void recountBlocked(blockedHostOf($), draftsDirOf())
    await buildPlanStart(buildPlanHostOf($))
    session.interactive = e.isInteractive !== false
    await resolveSkill(hostOf($))
    return next(e)
  }).catch(($, e, next) => {
    failed(hostOf($), 'session.start hook', failureText(next.error))
    return next(e)
  })

  on('turn.start', ($, e, next) => {
    // A subagent's run raises no turn.start; its turns surface only as turn.complete with agentId set.
    session.turnRunning = true
    // The opted-in turn may outlast the wait. Its own turn.complete clears the arming.
    cancelPlanWait()
    return next(e)
  }).catch(($, e, next) => {
    failed(hostOf($), 'turn.start hook', failureText(next.error))
    return next(e)
  })

  // The matcher is required: the engine refuses a second unmatched tool.call hook in one module,
  // and agent-guard.ts already holds the unmatched one. The refusal unloads the whole module.
  on('tool.call', { tool: 'AskUserQuestion' }, async ($, e, next) => {
    if (e.agentId !== undefined) return next(e)
    session.pendingQuestion = true
    try {
      return await next(e)
    } finally {
      session.pendingQuestion = false
    }
  }).catch(($, e, next) => {
    failed(hostOf($), 'tool.call hook', failureText(next.error))
    return next(e)
  })

  on('turn.complete', ($, e, next) => {
    if (e.agentId !== undefined) return next(e)
    // Not awaited: a block written during this turn shows once the count returns.
    const blockedHost = blockedHostOf($)
    void currentDraftsDir(draftFeedbackHostOf($)).then((dir) => recountBlocked(blockedHost, dir))
    session.turnRunning = false
    // An arming covers one main-loop turn: every main-loop turn end clears it before any new set.
    disarm()
    if (e.reason !== 'answer' || !session.interactive) return next(e)
    const marker = parseLoopMarker(e.answer)
    // turnRunning is false here by construction; a pending question still defers, and the boundary re-checks both.
    const decision = decide({ marker, lastKey: session.lastKey, turnRunning: false, pendingQuestion: session.pendingQuestion })
    if (marker !== null && decision.action !== 'none') {
      session.lastKey = keyOf(marker)
      session.token += 1
      session.armKey = endsOnLoopMarker(e.answer) ? keyOf(marker) : null
      schedule(hostOf($), marker, session.token, 0, 0)
    } else if (marker === null && isPlanModeMarker(e.answer)) {
      armPlanSession(hostOf($))
    }
    return next(e)
  }).catch(($, e, next) => {
    failed(hostOf($), 'turn.complete hook', failureText(next.error))
    return next(e)
  })

  // The matcher is required for the declared tool set. No other module registers this event.
  on('classic.PermissionRequest', { tool_name: ['ExitPlanMode', 'EnterPlanMode'] }, async ($, e, next) => {
    const host = hostOf($)
    // A subagent's ask is never answered here.
    const context = e.agent_id === undefined ? session.planContext : 'none'
    const answer = decidePlanExit({ tool: e.tool_name, context })
    if (answer.action === 'next') {
      host.uiLog(LEFT_TO_USER, 'debug')
      return next(e)
    }
    host.uiLog(answeredLine(e.tool_name, context))
    return { decision: answer.decision }
  }).catch(($, e, next) => {
    failed(hostOf($), 'classic.PermissionRequest hook', failureText(next.error))
    return next(e)
  })

  on('classic.SessionEnd', ($, e, next) => {
    session.timer?.cancel()
    session.timer = null
    session.token += 1
    disarm()
    session.armKey = null
    return next(e)
  }).catch(($, e, next) => {
    failed(hostOf($), 'classic.SessionEnd hook', failureText(next.error))
    return next(e)
  })
}
