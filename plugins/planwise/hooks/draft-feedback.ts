// Feedback drafting, composed into the one hooks module (register.ts). Its session.start work
// registers the draft_feedback tool and offers the newest queued draft on the review card, and a
// tool.call hook serves the tool: validate and render here, then pipe the text to the create
// command of scripts/feedback_drafts.py, which checks it, names the file and writes it. A
// non-zero exit is a deny, because no draft was queued. Only when no Python starts does the
// hook write the file itself. The model never sees a permission dialog: the
// hook asks the engine for its verdict first, refuses on a deny, and runs on an allow or an ask.
import { update } from 'claude-code'
import type { EngineInterface, On, PluginOptions, SessionVersion, ToolSpec } from 'claude-code'

import { CAP_TEXT, DESCRIPTION, FULL_TOOL_NAME, INPUT_SCHEMA, MAX_CALLS_PER_SESSION, MAX_NOTICES, NOTICE_TEXT, PYTHON_CANDIDATES, RESULT_TEXT, START_FAILURE_WINDOW_MS, TOOL_NAME, WINDOWS_NOT_FOUND, relativeDraftPath } from './feedback/names.ts'
import { draftsMode, findConfig, mainCheckoutDir, readRawScalar, readScalar, resolveDraftsDir } from './feedback/config-read.ts'
import type { DraftsMode } from './feedback/config-read.ts'
import { previewSourceOf } from './feedback/card-preview.ts'
import { isDraftFileName, newestQueued } from './feedback/queued.ts'
import { renderDraft, scrub } from './feedback/render.ts'
import { draftFileName, slugOf } from './feedback/slug.ts'
import { validateInput } from './feedback/validate.ts'
import type { Kind } from './feedback/names.ts'
import { failureText } from './loop/boundary.ts'
import { refusedByRule } from './permission.ts'
import type { PlanwiseLastDraft } from '../types'

export type Host = {
  root: () => Promise<string>
  sessionId: () => Promise<string>
  model: () => Promise<string>
  version: () => Promise<SessionVersion>
  pluginRoot: () => string
  osEnv: () => Promise<string | undefined>
  read: (path: string) => Promise<unknown>
  write: (path: string, text: string) => Promise<void>
  list: (path: string) => Promise<{ name: string; kind: string }[]>
  exists: (path: string) => Promise<boolean>
  registerTool: (tool: ToolSpec) => Promise<unknown>
  uiLog: (text: string, to: 'debug' | 'transcript') => void
  runProcess: (argv: readonly string[], stdin?: string) => Promise<{ exitCode: number; stdout: string; stderr: string }>
  check: (tool: string, input: unknown) => Promise<{ decision: 'allow' | 'ask' | 'deny'; reason?: string }>
  lastDraft: () => Promise<PlanwiseLastDraft | null>
  setLastDraft: (draft: PlanwiseLastDraft) => Promise<unknown>
  bumpCardsShown: () => Promise<unknown>
}

/** One record of module memory. Every field resets with the process. */
type Session = {
  mode: DraftsMode
  draftsDir: string
  /** The path of the config file, which the review card edits to turn drafting off. */
  configPath: string
  projectRoot: string
  /** The main checkout's copy of the project root in a linked worktree, else the project root. */
  draftsRoot: string
  calls: number
  notices: number
  /** True once the config was resolved in this process. A module reload resets it. */
  resolved: boolean
  /** True when a planwise config was found at resolution. */
  found: boolean
}

/**
 * The closure table over `$`. It sits at module scope because the validator refuses a `$` handed
 * to a nested function. Every engine call the module makes is spelled here, one per member.
 */
export function hostOf($: EngineInterface): Host {
  return {
    root: () => $.session.root(),
    sessionId: () => $.session.id(),
    model: () => $.session.model(),
    version: () => $.session.version(),
    pluginRoot: () => $.plugin.root,
    osEnv: () => $.env.get('OS'),
    read: (path: string) => $.fs.read(path),
    write: (path: string, text: string) => $.fs.write(path, text),
    list: (path: string) => $.fs.list(path),
    exists: (path: string) => $.fs.exists(path),
    registerTool: (tool: ToolSpec) => $.tool.register(tool),
    uiLog: (text: string, to: 'debug' | 'transcript') => $.ui.log(text, { to }),
    runProcess: (argv: readonly string[], stdin?: string) => $.process.run(argv, { stdin }),
    check: (tool: string, input: unknown) => $.tool.check({ tool, input }),
    // The review card reads these two values. Literal refs, as `$.state` requires.
    lastDraft: async () => (await $.state.get({ plugin: 'planwise', key: 'lastDraft' } as const)).value ?? null,
    setLastDraft: (draft: PlanwiseLastDraft) => $.state.set({ plugin: 'planwise', key: 'lastDraft' } as const, draft),
    bumpCardsShown: () => update($, { plugin: 'planwise', key: 'cardsShown' } as const, (n) => (n ?? 0) + 1),
  }
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/** The first non-empty line of a text, or an empty string. */
const firstLine = (text: string): string => text.split(/\r?\n/).find((l) => l.trim() !== '')?.trim() ?? ''

/** The plugin version from plugin.json, or `unknown` when it cannot be read. */
const pluginVersionOf = async (host: Host): Promise<string> => {
  try {
    const text = await host.read(host.pluginRoot() + '/.claude-plugin/plugin.json')
    const parsed: unknown = JSON.parse(String(text))
    const version = typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>)['version'] : undefined
    return typeof version === 'string' && version !== '' ? version : 'unknown'
  } catch {
    return 'unknown'
  }
}

/** One record of module memory. Every field resets with the process. */
const session: Session = { mode: 'off', draftsDir: '', configPath: '', projectRoot: '', draftsRoot: '', calls: 0, notices: 0, resolved: false, found: false }

/** Draft paths reserved by calls still in flight, for the write made when no Python starts. */
const reserved = new Set<string>()

/** The roots a draft's text must not show: the session's, and the main checkout's in a worktree. */
const hiddenRoots = (): string[] => [session.projectRoot, session.draftsRoot]

/** Logs a failure of one hook. Never throws. */
const failed = (host: Host, where: string, why: string): void => {
  host.uiLog(`draft feedback: ${where} failed: ${why}`, 'debug')
}

/**
 * Tells the review card a draft was admitted. A draft takes one of the card's slots only when no
 * draft was waiting, so a draft that replaces an unseen one costs nothing. The count goes up
 * before the draft is set, so the card never draws a draft past its limit. A failure is
 * debug-logged and never reaches the model.
 */
const noteCard = async (host: Host, draft: PlanwiseLastDraft): Promise<void> => {
  try {
    if ((await host.lastDraft()) === null) await host.bumpCardsShown()
    await host.setLastDraft(draft)
  } catch (err) {
    failed(host, 'card state write', errText(err))
  }
}

/**
 * Offers the newest queued draft on the review card at session start, so a draft an earlier
 * session wrote draws before the update card (the review card is the outer card). It reads the
 * drafts dir only and writes no file. A draft already on the card stays. A failure is
 * debug-logged and draws no card.
 */
const offerQueued = async (host: Host): Promise<void> => {
  try {
    if (session.draftsDir === '' || !(await host.exists(session.draftsDir))) return
    const names = (await host.list(session.draftsDir)).filter((entry) => entry.kind === 'file' && isDraftFileName(entry.name)).map((entry) => entry.name)
    const texts = await Promise.all(names.map(async (name) => String(await host.read(session.draftsDir + '/' + name))))
    const draft = newestQueued(texts)
    if (draft === null || (await host.lastDraft()) !== null) return
    await noteCard(host, {
      draftId: draft.draftId,
      kind: draft.kind,
      title: draft.title,
      preview: previewSourceOf(draft.kind, draft.fields, hiddenRoots()),
      feedbackDir: session.draftsDir,
      sessionId: draft.sessionId,
      configPath: session.configPath,
    })
  } catch (err) {
    failed(host, 'queued draft load', errText(err))
  }
}

/** The drafts dir of the resolved session, or an empty string while no planwise config is found. */
export const draftsDirOf = (): string => (session.found ? session.draftsDir : '')

/**
 * The session root moves when the session enters a git worktree, and a module reload re-runs
 * register() without a new session.start. This reads the root and resolves the config again when
 * it is unresolved or the root changed. It logs a failure and never throws.
 */
const resolveIfStale = async (host: Host): Promise<void> => {
  try {
    const root = await host.root()
    if (!session.resolved || slashed(root) !== slashed(session.projectRoot)) await resolveSession(host)
  } catch (err) {
    failed(host, 'config resolution', errText(err))
  }
}

/** draftsDirOf for the root the session is in now. */
export async function currentDraftsDir(host: Host): Promise<string> {
  await resolveIfStale(host)
  return draftsDirOf()
}

/**
 * The session.start body. The loop module's own session.start hook calls it first, because a
 * module may register one session.start hook only. It logs every error itself and never throws.
 */
export async function onSessionStart(host: Host): Promise<void> {
  try {
    await resolveSession(host)
    if (!session.found) {
      host.uiLog('draft feedback: no planwise config.yaml found; tool not registered', 'debug')
      return
    }
    if (session.mode === 'off') {
      host.uiLog('draft feedback: feedback.drafts is off; tool not registered', 'debug')
      return
    }
    // isDeferred false puts the schema in the prompt's tool list, so the first call needs no search.
    await host.registerTool({ name: TOOL_NAME, description: DESCRIPTION, inputSchema: INPUT_SCHEMA, isDeferred: false })
    host.uiLog(`draft feedback: registered ${FULL_TOOL_NAME}`, 'debug')
    await offerQueued(host)
  } catch (err) {
    failed(host, 'session.start hook', errText(err))
  }
}

/** Forward slashes and no trailing separator, so two spellings of one root compare equal. */
const slashed = (path: string): string => path.replace(/\\/g, '/').replace(/\/+$/, '')

/**
 * Resolves the config into the session record: the mode, the project root and the drafts dir.
 * Both session.start and a tool.call whose root changed (or that finds no resolved session) call
 * it. The record always follows the root it was just given. In a linked worktree the drafts dir
 * is the main checkout's, so a draft outlives the worktree, while the config path stays the
 * session's own. A root with no config resets the mode, the drafts dir and the config path, so a
 * stale value never survives a move. It throws on a read failure and leaves `resolved` as it
 * was, so the next caller tries again.
 */
async function resolveSession(host: Host): Promise<void> {
  const root = await host.root()
  const config = await findConfig(host, root)
  const next =
    config === null
      ? { mode: 'off' as const, draftsDir: '', draftsRoot: '', configPath: '' }
      : {
          mode: draftsMode(readRawScalar(config.text, ['feedback', 'drafts'])),
          draftsDir: resolveDraftsDir((await mainCheckoutDir(host, config.dir)) ?? config.dir, readScalar(config.text, ['project', 'feedback_dir'])),
          draftsRoot: (await mainCheckoutDir(host, root)) ?? root,
          configPath: config.dir + '/config.yaml',
        }
  // One assignment with no await before it, so a call in the same turn never reads a record that
  // holds the new root beside the old folders.
  Object.assign(session, next, { found: config !== null, projectRoot: root, resolved: true })
}

/**
 * Runs the helper's create command with the draft text on stdin. It tries each interpreter name in
 * turn and moves on only when the process could not start: the run rejects at once, or it exits
 * with the Windows not-found code. Any other non-zero exit is a result. A late rejection is a run
 * that was stopped, which may have written the draft, so it is thrown and never retried. Null
 * means no interpreter started.
 */
const create = async (host: Host, text: string): Promise<{ exitCode: number; stdout: string; stderr: string } | null> => {
  let why = ''
  for (const python of PYTHON_CANDIDATES) {
    const started = Date.now()
    try {
      const run = await host.runProcess([python, host.pluginRoot() + '/scripts/feedback_drafts.py', 'create', '--feedback-dir', session.draftsDir], text)
      if (run.exitCode !== WINDOWS_NOT_FOUND) return run
      why = firstLine(run.stderr) || `${python} exit ${run.exitCode}`
    } catch (err) {
      if (Date.now() - started >= START_FAILURE_WINDOW_MS) throw err
      why = errText(err)
    }
  }
  host.uiLog('draft feedback: no python could start; writing the draft unchecked: ' + why, 'debug')
  return null
}

/** The id and file name on the last line create printed, or null when the line is not there. */
const createdOf = (stdout: string): { draftId: string; name: string } | null => {
  const match = /^admitted (\S+) (\S+)$/.exec(stdout.trimEnd().split(/\r?\n/).pop() ?? '')
  return match === null ? null : { draftId: match[1]!, name: match[2]! }
}

/**
 * Writes the draft without the helper, which is what is left when no Python starts. A name is free
 * when no call in flight reserved it and no file exists. The second reserved check and the add run
 * with no await between them, so two calls in one process cannot both win. Two processes still can:
 * the engine's write has no exclusive create. Returns the path, or null when every name is taken.
 */
const writeUnchecked = async (host: Host, date: string, kind: Kind, slug: string, text: string): Promise<string | null> => {
  for (let n = 1; n <= 9; n++) {
    const candidate = session.draftsDir + '/' + draftFileName(date, kind, slug, n)
    if (reserved.has(candidate)) continue
    const taken = await host.exists(candidate)
    if (taken || reserved.has(candidate)) continue
    reserved.add(candidate)
    try {
      // fs.write creates missing parent directories. It is not atomic and takes no mode;
      // a partial file fails the helper's head parse and is skipped.
      await host.write(candidate, text)
    } finally {
      reserved.delete(candidate)
    }
    return candidate
  }
  return null
}

/** Registers the matched tool.call hook only. The session.start work runs through onSessionStart. */
export function register(on: On, options: PluginOptions) {
  void options

  on('tool.call', { tool: FULL_TOOL_NAME }, async ($, e, next) => {
    const host = hostOf($)
    // Resolve again when the config is stale (see resolveIfStale). Never register the tool again,
    // and deny only when it is off or no config exists.
    await resolveIfStale(host)
    if (!session.resolved || !session.found || session.mode === 'off') return { deny: 'draft_feedback: the tool is not active in this session' }
    if (session.calls >= MAX_CALLS_PER_SESSION) return { deny: CAP_TEXT }
    const checked = validateInput(e as unknown as Record<string, unknown>)
    if (!checked.ok) return { deny: 'draft_feedback: ' + checked.error }
    // This hook answers the call itself, so core's permission prompt never runs. Honour a deny
    // verdict (a deny rule, a mode that forbids the call). An ask runs silently, by design.
    const refusal = await refusedByRule(host.check, FULL_TOOL_NAME, { kind: checked.kind, title: checked.title })
    if (refusal !== null) return { deny: 'draft_feedback: ' + refusal }
    session.calls += 1

    const [sessionId, model, cli, osName, pluginVersion] = await Promise.all([host.sessionId(), host.model(), host.version(), host.osEnv(), pluginVersionOf(host)])
    const createdAt = new Date().toISOString()
    const draftId = globalThis.crypto.randomUUID()
    const text = scrub(
      renderDraft(
        { draftId, createdAt, producer: 'hooks-tool', sourceSessionId: sessionId, pluginVersion, cliVersion: cli.version, model, os: osName === 'Windows_NT' ? 'windows' : 'posix', status: 'queued' },
        { kind: checked.kind, title: checked.title, fields: checked.fields, subcommand: checked.subcommand },
      ),
      hiddenRoots(),
    )

    let path = ''
    let run: Awaited<ReturnType<typeof create>>
    try {
      run = await create(host, text)
    } catch (err) {
      host.uiLog('draft feedback: create did not finish: ' + errText(err), 'debug')
      return { deny: 'draft_feedback: the helper did not finish; the draft may not be saved' }
    }
    if (run === null) {
      const written = await writeUnchecked(host, createdAt.slice(0, 10), checked.kind, slugOf(checked.title), text)
      if (written === null) return { deny: 'draft_feedback: too many drafts share this title today' }
      path = written
    } else if (run.exitCode !== 0) {
      host.uiLog(`draft feedback: create exit ${run.exitCode}: ${run.stderr}`, 'debug')
      const fallback = run.exitCode === 3 ? 'draft_feedback: the draft was refused' : 'draft_feedback: the draft was not written'
      return { deny: firstLine(run.stderr) || fallback }
    } else {
      const made = createdOf(run.stdout)
      if (made === null) {
        host.uiLog('draft feedback: create exit 0 with no admitted line: ' + run.stdout, 'debug')
        return { deny: 'draft_feedback: the helper did not confirm a saved draft' }
      }
      path = session.draftsDir + '/' + made.name
      // The helper may have replaced a colliding id, so the card takes the id it printed.
      await noteCard(host, { draftId: made.draftId, kind: checked.kind, title: checked.title, preview: previewSourceOf(checked.kind, checked.fields, hiddenRoots()), feedbackDir: session.draftsDir, sessionId, configPath: session.configPath })
    }

    const loud = session.mode === 'notify' && session.notices < MAX_NOTICES
    if (loud) session.notices += 1
    host.uiLog(NOTICE_TEXT(relativeDraftPath(session.draftsRoot, path)), loud ? 'transcript' : 'debug')
    return { result: RESULT_TEXT }
  }).catch(($, e, next) => {
    failed(hostOf($), 'tool.call hook', failureText(next.error))
    return next.called ? next(e) : { deny: 'draft_feedback: internal error; draft not written' }
  })
}
