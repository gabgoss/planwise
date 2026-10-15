// Feedback drafting, composed into the one hooks module (register.ts). Its session.start work
// registers the draft_feedback tool, and a tool.call hook serves it: validate, render, write a
// draft file, then admit it through scripts/feedback_drafts.py. An admit exit other than
// 0, 2 or 3 is debug-logged and the file is kept. The model never sees a permission dialog.
import type { EngineInterface, On, PluginOptions, SessionVersion, ToolSpec } from 'claude-code'

import { CAP_TEXT, DESCRIPTION, FULL_TOOL_NAME, INPUT_SCHEMA, MAX_CALLS_PER_SESSION, MAX_NOTICES, NOTICE_TEXT, PYTHON_CANDIDATES, RESULT_TEXT, TOOL_NAME } from './feedback/names.ts'
import { draftsMode, isPlanwiseConfig, readRawScalar, readScalar, resolveDraftsDir } from './feedback/config-read.ts'
import type { DraftsMode } from './feedback/config-read.ts'
import { renderDraft, scrub } from './feedback/render.ts'
import { draftFileName, slugOf } from './feedback/slug.ts'
import { validateInput } from './feedback/validate.ts'
import { failureText } from './loop/boundary.ts'

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
  runProcess: (argv: readonly string[]) => Promise<{ exitCode: number; stderr: string }>
}

/** One record of module memory. Every field resets with the process. */
type Session = {
  mode: DraftsMode
  draftsDir: string
  projectRoot: string
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
    runProcess: (argv: readonly string[]) => $.process.run(argv),
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

/**
 * Finds the planwise config. The search order is planwise/config.yaml, then config.yaml at the
 * root itself, then each top-level directory in name order. A candidate counts only when its
 * text is a planwise config. `dir` is the directory that holds the file.
 */
const findConfig = async (host: Host, root: string): Promise<{ text: string; dir: string } | null> => {
  const tryDir = async (dir: string): Promise<{ text: string; dir: string } | null> => {
    const path = dir + '/config.yaml'
    if (!(await host.exists(path))) return null
    const text = String(await host.read(path))
    return isPlanwiseConfig(text) ? { text, dir } : null
  }
  const base = root.replace(/[\\/]+$/, '')
  const first = await tryDir(base + '/planwise')
  if (first !== null) return first
  const atRoot = await tryDir(base)
  if (atRoot !== null) return atRoot
  const names = (await host.list(root))
    .filter((entry) => entry.kind === 'dir' && entry.name !== 'planwise' && !entry.name.startsWith('.'))
    .map((entry) => entry.name)
    .sort()
  for (const name of names) {
    const found = await tryDir(base + '/' + name)
    if (found !== null) return found
  }
  return null
}

/** One record of module memory. Every field resets with the process. */
const session: Session = { mode: 'off', draftsDir: '', projectRoot: '', calls: 0, notices: 0, resolved: false, found: false }

/** Draft paths reserved by calls still in flight, so two calls in one turn never pick one file. */
const reserved = new Set<string>()

/** Logs a failure of one hook. Never throws. */
const failed = (host: Host, where: string, why: string): void => {
  host.uiLog(`draft feedback: ${where} failed: ${why}`, 'debug')
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
    await host.registerTool({ name: TOOL_NAME, description: DESCRIPTION, inputSchema: INPUT_SCHEMA })
    host.uiLog(`draft feedback: registered ${FULL_TOOL_NAME}`, 'debug')
  } catch (err) {
    failed(host, 'session.start hook', errText(err))
  }
}

/**
 * Resolves the config into the session record: the mode, the project root and the drafts dir.
 * Both session.start and a tool.call that finds no resolved session call it. It throws on a
 * read failure and leaves `resolved` false, so the next caller tries again.
 */
async function resolveSession(host: Host): Promise<void> {
  const root = await host.root()
  const config = await findConfig(host, root)
  session.found = config !== null
  if (config !== null) {
    session.mode = draftsMode(readRawScalar(config.text, ['feedback', 'drafts']))
    session.projectRoot = root
    session.draftsDir = resolveDraftsDir(config.dir, readScalar(config.text, ['project', 'feedback_dir']))
  }
  session.resolved = true
}

/**
 * Runs the helper's admit command. It tries each interpreter name in turn and moves on only when
 * the run rejects (the process could not start). A non-zero exit is a result, not a rejection.
 */
const admit = async (host: Host, path: string): Promise<{ exitCode: number; stderr: string }> => {
  let last: unknown
  for (const python of PYTHON_CANDIDATES) {
    try {
      return await host.runProcess([python, host.pluginRoot() + '/scripts/feedback_drafts.py', 'admit', path, '--feedback-dir', session.draftsDir])
    } catch (err) {
      last = err
    }
  }
  throw last
}

/** Registers the matched tool.call hook only. The session.start work runs through onSessionStart. */
export function register(on: On, options: PluginOptions) {
  void options

  on('tool.call', { tool: FULL_TOOL_NAME }, async ($, e, next) => {
    const host = hostOf($)
    // A module reload re-runs register() without a new session.start. Resolve the config once
    // here, never register the tool again, and deny only when it is off or no config exists.
    if (!session.resolved) {
      try {
        await resolveSession(host)
      } catch (err) {
        failed(host, 'config resolution', errText(err))
      }
    }
    if (!session.resolved || !session.found || session.mode === 'off') return { deny: 'draft_feedback: the tool is not active in this session' }
    if (session.calls >= MAX_CALLS_PER_SESSION) return { deny: CAP_TEXT }
    const checked = validateInput(e as unknown as Record<string, unknown>)
    if (!checked.ok) return { deny: 'draft_feedback: ' + checked.error }
    session.calls += 1

    const [sessionId, model, cli, osName, pluginVersion] = await Promise.all([host.sessionId(), host.model(), host.version(), host.osEnv(), pluginVersionOf(host)])
    const createdAt = new Date().toISOString()
    const slug = slugOf(checked.title)
    // A candidate is free when no in-flight call reserved it and no file exists. The second
    // reserved check and the add run with no await between them, so two calls cannot both win.
    let path = ''
    for (let n = 1; n <= 9; n++) {
      const candidate = session.draftsDir + '/' + draftFileName(createdAt.slice(0, 10), checked.kind, slug, n)
      if (reserved.has(candidate)) continue
      const taken = await host.exists(candidate)
      if (taken || reserved.has(candidate)) continue
      reserved.add(candidate)
      path = candidate
      break
    }
    if (path === '') return { deny: 'draft_feedback: too many drafts share this title today' }

    try {
      const text = renderDraft(
        { draftId: globalThis.crypto.randomUUID(), createdAt, producer: 'hooks-tool', sourceSessionId: sessionId, pluginVersion, cliVersion: cli.version, model, os: osName === 'Windows_NT' ? 'windows' : 'posix', status: 'queued' },
        { kind: checked.kind, title: checked.title, fields: checked.fields, subcommand: checked.subcommand },
      )
      // fs.write creates missing parent directories. It is not atomic and takes no mode;
      // a partial file fails the helper's head parse and is skipped.
      await host.write(path, scrub(text, [session.projectRoot]))

      try {
        const run = await admit(host, path)
        if (run.exitCode === 2) {
          host.uiLog('draft feedback: admit exit 2: ' + run.stderr, 'debug')
          return { deny: firstLine(run.stderr) || 'draft_feedback: name mismatch; the file was left in place' }
        }
        if (run.exitCode === 3) {
          host.uiLog('draft feedback: admit exit 3: ' + run.stderr, 'debug')
          return { deny: firstLine(run.stderr) || 'draft_feedback: the draft was refused' }
        }
        if (run.exitCode !== 0) host.uiLog(`draft feedback: admit exit ${run.exitCode}: ${run.stderr}`, 'debug')
      } catch (err) {
        host.uiLog('draft feedback: no python could start; the draft was kept: ' + errText(err), 'debug')
      }

      const loud = session.mode === 'notify' && session.notices < MAX_NOTICES
      if (loud) session.notices += 1
      host.uiLog(NOTICE_TEXT(session.draftsDir), loud ? 'transcript' : 'debug')
      return { result: RESULT_TEXT }
    } finally {
      reserved.delete(path)
    }
  }).catch(($, e, next) => {
    failed(hostOf($), 'tool.call hook', failureText(next.error))
    return next.called ? next(e) : { deny: 'draft_feedback: internal error; draft not written' }
  })
}
