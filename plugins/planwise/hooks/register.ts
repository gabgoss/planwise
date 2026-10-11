// Backlog loop hooks module. Contract: handlers/backlog-Part-2-LoopMode.md.
// After a one-item backlog session prints its BACKLOG LOOP marker, this module
// compacts the session and re-enters the handler with --loop-resume.
import type { CommandInfo, EngineInterface, On, PluginOptions, Timer } from 'claude-code'

import { failureText, isCurrent, keyOf, releaseLatch, stepOf } from './loop/boundary.ts'
import type { BoundaryStep } from './loop/boundary.ts'
import { decide } from './loop/decide.ts'
import { DEFER_MS, MAX_DEFERRALS } from './loop/names.ts'
import type { LoopMarker } from './loop/parse-marker.ts'
import { parseLoopMarker } from './loop/parse-marker.ts'
import { reentryArgs, skillNameOf } from './loop/reentry.ts'
import { steerText } from './loop/steer-text.ts'

type Host = {
  after: (ms: number, fn: () => void) => Timer
  compact: (instructions: string) => Promise<{ skip?: string }>
  runCommand: (command: string, args: string) => Promise<unknown>
  listCommands: () => Promise<CommandInfo[]>
  uiLog: (text: string) => void
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
    uiLog: (text: string) => $.ui.log(text),
  }
}

export function register(on: On, options: PluginOptions) {
  void options
  // `interactive` starts true: a module reload re-runs register() without a new session.start.
  const session: Session = {
    skillName: null,
    interactive: true,
    turnRunning: false,
    pendingQuestion: false,
    lastKey: null,
    timer: null,
    token: 0,
  }

  /** Logs a failure of one hook or of the boundary. Never throws. */
  const failed = (host: Host, where: string, why: string): void => {
    host.uiLog(`backlog loop: ${where} failed: ${why}`)
  }

  /** Releases the latch for one marker, so the same marker printed again can start a new boundary. */
  const release = (marker: LoopMarker): void => {
    session.lastKey = releaseLatch(session.lastKey, keyOf(marker))
  }

  /** Resolves the re-entry skill from the command list and logs the result. */
  const resolveSkill = async (host: Host): Promise<void> => {
    session.skillName = skillNameOf(await host.listCommands())
    if (session.skillName === null) host.uiLog('backlog loop: no planwise skill found; re-entry disabled')
    else host.uiLog(`backlog loop: re-entry skill ${session.skillName}`)
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
    if (!isCurrent(token, session.token)) return
    if (skipped === undefined) host.uiLog(`backlog loop: compacted; re-entering run ${marker.runId}`)
    else host.uiLog(`backlog loop: compaction skipped (${skipped}); re-entering run ${marker.runId}`)
    await host.runCommand(skillName, reentryArgs(marker.runId)).then(
      () => host.uiLog(`backlog loop: re-entry resolved for run ${marker.runId}`),
      (err: unknown) => {
        release(marker)
        host.uiLog(`backlog loop: re-entry rejected: ${err instanceof Error ? err.message : String(err)}`)
      },
    )
  }

  on('session.start', async ($, e, next) => {
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
    return next(e)
  }).catch(($, e, next) => {
    failed(hostOf($), 'turn.start hook', failureText(next.error))
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const toolName: string = e.tool
    if (e.agentId !== undefined || toolName !== 'AskUserQuestion') return next(e)
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
    session.turnRunning = false
    if (e.reason !== 'answer' || !session.interactive) return next(e)
    const marker = parseLoopMarker(e.answer)
    // turnRunning is false here by construction; a pending question still defers, and the boundary re-checks both.
    const decision = decide({ marker, lastKey: session.lastKey, turnRunning: false, pendingQuestion: session.pendingQuestion })
    if (marker !== null && decision.action !== 'none') {
      session.lastKey = keyOf(marker)
      session.token += 1
      schedule(hostOf($), marker, session.token, 0, 0)
    }
    return next(e)
  }).catch(($, e, next) => {
    failed(hostOf($), 'turn.complete hook', failureText(next.error))
    return next(e)
  })

  on('classic.SessionEnd', ($, e, next) => {
    session.timer?.cancel()
    session.timer = null
    session.token += 1
    return next(e)
  }).catch(($, e, next) => {
    failed(hostOf($), 'classic.SessionEnd hook', failureText(next.error))
    return next(e)
  })
}
