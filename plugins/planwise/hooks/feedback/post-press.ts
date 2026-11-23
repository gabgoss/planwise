// The review card's Post press, kept apart from the card so node tests can load it. It imports
// nothing from the engine: every engine call arrives through the PressHost table, which the card
// builds from its own hostOf. The press runs feedback_post.py directly, so no model turn starts.
import { isStalePress } from './card-preview.ts'
import { PYTHON_CANDIDATES } from './names.ts'

/** The line logged when posting is off in the project. It matches the Enable Offer's keep line. */
export const KEEP_LINE = 'Posting stays off. The draft was saved, and the next feedback flow asks again.'

/** The exit codes of `feedback_post.py post`. */
export const EXIT_POSTED = 0
export const EXIT_NO_DRAFT = 2
export const EXIT_KEPT = 3
export const EXIT_POSTING_OFF = 4

/**
 * The words the post script prints on stderr, with exit 2, when the draft is not queued. A usage
 * error also exits 2, so the press reads these words before it spends the card.
 */
export const NO_DRAFT_MARK = 'no queued draft'

/** What one process run returns. */
export type PressRunResult = { exitCode: number; stdout: string; stderr: string }

/** The two draft fields the press needs. */
export type PressDraft = { draftId: string; configPath: string }

/** The engine calls the press makes. The card builds this table from its own hostOf. */
export type PressHost = {
  /** Runs one process by argv. Rejects when the process could not start. */
  run: (argv: readonly string[], init?: { timeoutMs?: number }) => Promise<PressRunResult>
  uiLog: (text: string, to: 'debug' | 'transcript') => void
  /** The old route: posts through the planwise skill with a model turn. */
  fallback: (draftId: string) => Promise<void>
  readPosting: () => Promise<boolean>
  setPosting: (value: boolean) => Promise<unknown>
  clearLast: (draftId: string | null) => Promise<unknown>
  pluginRoot: () => string
  /** True when a file exists at the path. */
  exists: (path: string) => Promise<boolean>
  /** The config path under the session's current root, or an empty string when the root holds none. */
  currentConfig: () => Promise<string>
}

/**
 * The config path a press runs with. The card stores the path when the draft is written, and the
 * file can go away later: a session that leaves a git worktree keeps its card, and the worktree
 * may then be removed. The stored path wins while its file exists, because the draft file sits
 * beside it. Otherwise the session's current root gives the path. A check that throws keeps the
 * stored path.
 */
export const liveConfigPath = async (host: Pick<PressHost, 'exists' | 'currentConfig'>, stored: string): Promise<string> => {
  try {
    if (stored !== '' && (await host.exists(stored))) return stored
    return await host.currentConfig()
  } catch {
    return stored
  }
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/** The last non-empty line of a stream, or the fallback text when the stream has none. */
const lastLine = (text: string, fallback: string): string => {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter((line) => line !== '')
  return lines.length === 0 ? fallback : (lines[lines.length - 1] ?? fallback)
}

/**
 * A rejection that names a timeout came from a process that started. It must not fall back, or
 * a post that reached GitHub before the timeout could be sent twice.
 */
const isTimeout = (err: unknown): boolean => /time(d)?[\s-]?out/i.test(errText(err))

/** The post script's argv for one interpreter name. */
export const postArgv = (python: string, pluginRoot: string, draft: PressDraft): string[] => [
  python,
  '-B',
  pluginRoot + '/scripts/feedback_post.py',
  'post',
  '--config',
  draft.configPath,
  '--draft-id',
  draft.draftId,
]

/**
 * Acts on one definite result. A posted, kept or posting-off result spends the card. So does a
 * draft that is no longer queued, because no later press could post it.
 */
const route = async (host: PressHost, draft: PressDraft, result: PressRunResult): Promise<void> => {
  if (result.exitCode === EXIT_POSTED) {
    host.uiLog(lastLine(result.stdout, 'draft feedback: posted'), 'transcript')
    await host.clearLast(draft.draftId)
    return
  }
  if (result.exitCode === EXIT_KEPT) {
    host.uiLog(lastLine(result.stdout, 'draft feedback: the draft was kept and nothing was posted'), 'transcript')
    await host.clearLast(draft.draftId)
    return
  }
  if (result.exitCode === EXIT_POSTING_OFF) {
    host.uiLog(KEEP_LINE, 'transcript')
    await host.clearLast(draft.draftId)
    return
  }
  const reason = lastLine(result.stderr, 'no error text')
  if (result.exitCode === EXIT_NO_DRAFT && reason.includes(NO_DRAFT_MARK)) {
    host.uiLog('draft feedback: nothing to post; the card is cleared: ' + reason, 'transcript')
    await host.clearLast(draft.draftId)
    return
  }
  host.uiLog('draft feedback: post failed (exit ' + String(result.exitCode) + '); the card stays: ' + reason, 'transcript')
}

/**
 * Button 2: post the draft with no model turn. A press while a post runs does nothing. The config
 * path is resolved at press time (liveConfigPath), and no path at all takes the old route. Each
 * interpreter name is tried in turn, and the next is tried only when a run could not start. The
 * old route runs only when no process started, so a definite result never posts twice.
 */
export const pressPost = async (host: PressHost, draft: PressDraft | null): Promise<void> => {
  if (isStalePress(draft)) return
  if (await host.readPosting()) return
  await host.setPosting(true)
  try {
    const configPath = await liveConfigPath(host, draft.configPath)
    if (configPath === '') {
      await host.fallback(draft.draftId)
      return
    }
    if (configPath !== draft.configPath) host.uiLog('draft feedback: the stored config path is gone; posting with ' + configPath, 'debug')
    const live: PressDraft = { draftId: draft.draftId, configPath }
    let result: PressRunResult | null = null
    let lastError: unknown = null
    for (const python of PYTHON_CANDIDATES) {
      try {
        // The engine stops the script after two minutes.
        result = await host.run(postArgv(python, host.pluginRoot(), live), { timeoutMs: 120000 })
        break
      } catch (err) {
        if (isTimeout(err)) {
          host.uiLog('draft feedback: post timed out; the card stays: ' + errText(err), 'transcript')
          return
        }
        lastError = err
      }
    }
    if (result === null) {
      host.uiLog('draft feedback: no python could start; posting through the skill: ' + errText(lastError), 'debug')
      await host.fallback(draft.draftId)
      return
    }
    await route(host, draft, result)
  } finally {
    await host.setPosting(false)
  }
}
