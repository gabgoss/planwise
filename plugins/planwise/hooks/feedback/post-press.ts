// The review card's Post press, kept apart from the card so node tests can load it. It imports
// nothing from the engine: every engine call arrives through the PressHost table, which the card
// builds from its own hostOf. The press runs feedback_post.py directly, so no model turn starts.
import { isStalePress } from './card-preview.ts'
import { PYTHON_CANDIDATES } from './names.ts'

/** The line logged when posting is off in the project. It matches the Enable Offer's keep line. */
export const KEEP_LINE = 'Posting stays off. The draft was saved, and the next feedback flow asks again.'

/**
 * The line logged when posting is off in the current folder's config, after the draft's own config
 * went away. It does not say the draft was saved, because the press cannot know that.
 */
export const MOVED_OFF_LINE = "Posting is off in this folder's config, and the draft's own config is gone. Nothing was posted."

/** The exit codes of `feedback_post.py post`. */
export const EXIT_POSTED = 0
export const EXIT_FAILED = 1
export const EXIT_NO_DRAFT = 2
export const EXIT_KEPT = 3
export const EXIT_POSTING_OFF = 4

/**
 * The words the post script prints on stderr, with exit 1, when its --config file does not exist.
 * The script checks the file before it writes anything or calls gh.
 */
export const CONFIG_GONE_MARK = 'config.yaml not found'

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
  /** The config path under the session's current root, or an empty string when the root holds none. */
  currentConfig: () => Promise<string>
}

/** The two calls liveConfigPath makes. */
export type LiveConfigHost = {
  /** True when a file exists at the path. */
  exists: (path: string) => Promise<boolean>
  currentConfig: () => Promise<string>
}

/**
 * The config path the card's turn-off answer writes to. The card stores the path when the draft
 * is written, and the file can go away later: a session that leaves a git worktree keeps its
 * card, and the worktree may then be removed. The stored path wins while its file exists.
 * Otherwise the session's current root gives the path, or an empty string when it holds none or
 * cannot be searched. An existence check that throws keeps the stored path. The Post press does
 * not use this: it lets the post script report a missing config (see pressPost).
 */
export const liveConfigPath = async (host: LiveConfigHost, stored: string): Promise<string> => {
  let present = false
  try {
    present = stored !== '' && (await host.exists(stored))
  } catch {
    return stored
  }
  if (present) return stored
  try {
    return await host.currentConfig()
  } catch {
    return ''
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
 * draft that is no longer queued, because no later press could post it. `moved` is true when the
 * run used the current folder's config in place of the draft's own.
 */
const route = async (host: PressHost, draft: PressDraft, result: PressRunResult, moved: boolean): Promise<void> => {
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
    host.uiLog(moved ? MOVED_OFF_LINE : KEEP_LINE, 'transcript')
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

/** How one run of the post script ended. */
type Attempt = { kind: 'result'; result: PressRunResult } | { kind: 'timeout' } | { kind: 'no-python' }

/**
 * Runs the post script once. Each interpreter name is tried in turn, and the next is tried only
 * when a run could not start. A timeout is logged here and ends the press.
 */
const attempt = async (host: PressHost, draft: PressDraft): Promise<Attempt> => {
  let lastError: unknown = null
  for (const python of PYTHON_CANDIDATES) {
    try {
      // The engine stops the script after two minutes.
      return { kind: 'result', result: await host.run(postArgv(python, host.pluginRoot(), draft), { timeoutMs: 120000 }) }
    } catch (err) {
      if (isTimeout(err)) {
        host.uiLog('draft feedback: post timed out; the card stays: ' + errText(err), 'transcript')
        return { kind: 'timeout' }
      }
      lastError = err
    }
  }
  host.uiLog('draft feedback: no python could start; posting through the skill: ' + errText(lastError), 'debug')
  return { kind: 'no-python' }
}

/** True when the script reports that its --config file does not exist. Nothing ran past that check. */
const configIsGone = (result: PressRunResult): boolean =>
  result.exitCode === EXIT_FAILED && lastLine(result.stderr, '').includes(CONFIG_GONE_MARK)

/** The current root's config path, or an empty string when the root holds none or cannot be searched. */
const currentConfigOf = async (host: PressHost): Promise<string> => {
  try {
    return await host.currentConfig()
  } catch (err) {
    host.uiLog('draft feedback: the current folder could not be searched for a config: ' + errText(err), 'debug')
    return ''
  }
}

/**
 * Button 2: post the draft with no model turn. A press while a post runs does nothing. The old
 * route runs only when no process started, so a definite result never posts twice.
 *
 * The card stores the config path when the draft is written. A session that leaves a git worktree
 * keeps its card, and the worktree may then be removed. The press runs the script with the stored
 * path first, and the script itself reports a config file that is gone. The press then says so in
 * the transcript and runs the script once more with the config under the session's current root.
 * The script checks its config before it writes or calls gh, so the second run cannot post twice.
 * With no config under the current root either, the press takes the old route.
 */
export const pressPost = async (host: PressHost, draft: PressDraft | null): Promise<void> => {
  if (isStalePress(draft)) return
  if (await host.readPosting()) return
  await host.setPosting(true)
  try {
    if (draft.configPath === '') {
      await host.fallback(draft.draftId)
      return
    }
    let live: PressDraft = draft
    let outcome = await attempt(host, live)
    if (outcome.kind === 'result' && configIsGone(outcome.result)) {
      const current = await currentConfigOf(host)
      if (current === '') {
        host.uiLog("draft feedback: the draft's config file is gone and the current folder holds none; posting through the skill", 'debug')
        await host.fallback(draft.draftId)
        return
      }
      if (current !== draft.configPath) {
        host.uiLog("draft feedback: the draft's config file is gone; posting with " + current, 'transcript')
        live = { draftId: draft.draftId, configPath: current }
        outcome = await attempt(host, live)
      }
    }
    if (outcome.kind === 'timeout') return
    if (outcome.kind === 'no-python') {
      await host.fallback(draft.draftId)
      return
    }
    await route(host, live, outcome.result, live !== draft)
  } finally {
    await host.setPosting(false)
  }
}
