// The blocked-draft banner's helpers, kept apart from the card so node tests can load them. It
// imports nothing from the engine: every engine call arrives through the BlockedHost table, which
// the card builds from its own hostOf. The banner never reads a sidecar itself. It counts and
// dismisses by running feedback_drafts.py, so the rule for a posted draft stays in one place.
import { PYTHON_CANDIDATES } from './names.ts'

/** The start of the banner line. The count and the word `draft(s)` follow it. */
export const BANNER_PREFIX = 'Feedback post blocked by the privacy check: '

/** The rows the frame takes around the banner. The banner needs one text row and one button row inside it. */
export const FRAME_ROWS = 2

/** The columns the frame takes around the banner. */
export const FRAME_COLUMNS = 4

/** The fewest columns the banner text may have, after the frame. */
export const MIN_COLUMNS = 30

/** The fewest rows the banner may have, after the frame: one text row and one button row. */
export const MIN_CONTENT_ROWS = 2

/** What the banner shows: how many drafts the privacy check kept, and the directory they sit in. */
export type BlockedState = { count: number; feedbackDir: string }

/** The slice of the drawing props the size and mode guards read. */
export type BannerProps = { hasSurvey: boolean; isWorking: boolean; maxRows: number; bodyColumns: number }

/** What one process run returns. */
export type BlockedRunResult = { exitCode: number; stdout: string; stderr: string }

/** The engine calls the banner makes. The card builds this table from its own hostOf. */
export type BlockedHost = {
  /** Runs one process by argv. Rejects when the process could not start. */
  run: (argv: readonly string[], init?: { timeoutMs?: number }) => Promise<BlockedRunResult>
  uiLog: (text: string, to: 'debug' | 'transcript') => void
  pluginRoot: () => string
  /** Stores the state the banner draws from. */
  setBlocked: (state: BlockedState) => void
}

/** The banner line for a count. */
export const bannerText = (n: number): string => BANNER_PREFIX + String(n) + ' draft(s)'

/** The argv of `feedback_drafts.py blocked-list --json` for one interpreter name. The directory option is required. */
export const blockedListArgv = (python: string, pluginRoot: string, feedbackDir: string): string[] => [
  python,
  '-B',
  pluginRoot + '/scripts/feedback_drafts.py',
  'blocked-list',
  '--json',
  '--feedback-dir',
  feedbackDir,
]

/** The argv of `feedback_drafts.py dismiss-blocked --all` for one interpreter name. The directory option is required. */
export const dismissBlockedArgv = (python: string, pluginRoot: string, feedbackDir: string): string[] => [
  python,
  '-B',
  pluginRoot + '/scripts/feedback_drafts.py',
  'dismiss-blocked',
  '--all',
  '--feedback-dir',
  feedbackDir,
]

/** The length of the JSON array `blocked-list --json` printed, or null for text that is not a JSON array. */
export const parseBlockedCount = (stdout: string): number | null => {
  try {
    const parsed: unknown = JSON.parse(stdout)
    return Array.isArray(parsed) ? parsed.length : null
  } catch {
    return null
  }
}

/**
 * True when the banner may draw. It never draws over a survey or a working turn, with no blocked
 * draft, or in a space too small for the frame, one text row and one button row.
 */
export const shouldShowBanner = (blocked: BlockedState | null, props: BannerProps): boolean => {
  if (props.hasSurvey || props.isWorking) return false
  if (blocked === null || blocked.count < 1) return false
  if (props.maxRows - FRAME_ROWS < MIN_CONTENT_ROWS) return false
  return props.bodyColumns - FRAME_COLUMNS >= MIN_COLUMNS
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/** The last non-empty line of a stream, or the fallback text when the stream has none. */
const lastLine = (text: string, fallback: string): string => {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter((line) => line !== '')
  return lines.length === 0 ? fallback : (lines[lines.length - 1] ?? fallback)
}

/**
 * Runs one script call. Each interpreter name is tried in turn, and the next is tried only when a
 * run could not start. Returns null when no name could start, after a debug line.
 */
const runScript = async (host: BlockedHost, argvOf: (python: string) => string[]): Promise<BlockedRunResult | null> => {
  let lastError: unknown = null
  for (const python of PYTHON_CANDIDATES) {
    try {
      // The engine stops the script after 30 seconds.
      return await host.run(argvOf(python), { timeoutMs: 30000 })
    } catch (err) {
      lastError = err
    }
  }
  host.uiLog('draft feedback: no python could start for the blocked-draft banner: ' + errText(lastError), 'debug')
  return null
}

/**
 * Counts the blocked drafts through the real script and stores the count. An empty directory runs
 * nothing. A run that fails, exits non-zero or prints text that is not a JSON array leaves the
 * stored state as it was. It never throws.
 */
export const recountBlocked = async (host: BlockedHost, feedbackDir: string): Promise<void> => {
  if (feedbackDir === '') return
  try {
    const result = await runScript(host, (python) => blockedListArgv(python, host.pluginRoot(), feedbackDir))
    if (result === null) return
    if (result.exitCode !== 0) {
      host.uiLog('draft feedback: blocked-list exited ' + String(result.exitCode) + ': ' + lastLine(result.stderr, 'no error text'), 'debug')
      return
    }
    const count = parseBlockedCount(result.stdout)
    if (count === null) {
      host.uiLog('draft feedback: blocked-list printed no JSON array', 'debug')
      return
    }
    host.setBlocked({ count, feedbackDir })
  } catch (err) {
    host.uiLog('draft feedback: the blocked-draft recount failed: ' + errText(err), 'debug')
  }
}

/**
 * The Dismiss press: marks every blocked draft dismissed through the real script. On exit 0 the
 * count becomes 0 and the script's last stdout line goes to the transcript. Any other result keeps
 * the count and says so. It never throws.
 */
export const pressDismiss = async (host: BlockedHost, feedbackDir: string): Promise<void> => {
  if (feedbackDir === '') return
  try {
    const result = await runScript(host, (python) => dismissBlockedArgv(python, host.pluginRoot(), feedbackDir))
    if (result === null) return
    if (result.exitCode !== 0) {
      host.uiLog('draft feedback: dismiss failed (exit ' + String(result.exitCode) + '); the banner stays: ' + lastLine(result.stderr, 'no error text'), 'transcript')
      return
    }
    host.setBlocked({ count: 0, feedbackDir })
    host.uiLog(lastLine(result.stdout, 'draft feedback: blocked drafts dismissed'), 'transcript')
  } catch (err) {
    host.uiLog('draft feedback: the dismiss press failed: ' + errText(err), 'debug')
  }
}
