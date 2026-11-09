// Plan building, composed into the one hooks module (register.ts). Its session.start work
// registers the build_plan tool, and a tool.call hook serves it: validate the input, write the
// spec and the bodies files beside the plan folder, run scripts/plan_build.py, and return the
// script's exit code and report. The tool is an accelerator: the plan handler works without it.
import type { EngineInterface, On, PluginOptions, ToolSpec } from 'claude-code'

import { isPlanwiseConfig } from './feedback/config-read.ts'
import { PYTHON_CANDIDATES } from './feedback/names.ts'
import { failureText } from './loop/boundary.ts'
import { permit } from './permission.ts'

const TOOL_NAME = 'build_plan'
const FULL_TOOL_NAME = 'mcp__planwise__build_plan' as const

const ACTIONS = ['keys', 'lint', 'build'] as const
type Action = (typeof ACTIONS)[number]

/** How long one plan_build.py run may take. The engine caps a run at ten minutes. */
const RUN_TIMEOUT_MS = 540_000

/**
 * A rejection later than this is not a failed start. A process that cannot start rejects at
 * once, while a run killed at its timeout rejects late, and retrying that run with the next
 * interpreter name would double the wait.
 */
const START_FAILURE_WINDOW_MS = 10_000

/**
 * The Windows exit code for a command that could not be found. The Windows Store alias stub for
 * `python` starts and returns it, so it counts as a failed start and the next name is tried.
 * plan_build.py itself exits 0 to 3 only.
 */
const WINDOWS_NOT_FOUND = 9009

const DESCRIPTION =
  'Build a planwise plan from a JSON build spec and Markdown bodies files by running scripts/plan_build.py. ' +
  'action=keys prints every document id with its fill markers and headings. ' +
  'action=lint checks the bodies files against those keys. ' +
  'action=build lints, writes the plan tree to `out`, and runs the post-build gates; force=true overwrites files a hand edit changed. ' +
  'Every action first writes the spec to <out>/../<abbrev>-build-spec.json and each bodies file to <out>/../<file name>, ' +
  'so a file name must read <abbrev>-bodies-plan.md or <abbrev>-bodies-SXX-YY<suffix>.md. ' +
  'The script reads every bodies file in that folder, including files an earlier call wrote. ' +
  'Returns text: the first line reads exitCode: N, the script report follows, and stderr follows a --- stderr --- line when it holds text. ' +
  'Exit codes: keys 0 printed, 2 refused; ' +
  'lint 0 clean, 1 a marker has no body, 2 errors; build 0 clean, 1 built with findings, 2 refused, 3 a write failed.'

const INPUT_SCHEMA: Record<string, unknown> = {
  type: 'object',
  properties: {
    action: { type: 'string', enum: [...ACTIONS], description: 'keys, lint or build.' },
    spec: {
      type: 'object',
      description: 'The build spec object. Its `abbrev` key names the plan abbreviation and the file names.',
    },
    bodies: {
      type: 'object',
      description: 'Bodies files: file name to Markdown text. Required for lint and build, optional for keys.',
      additionalProperties: { type: 'string' },
    },
    out: {
      type: 'string',
      description: 'The plan folder, relative to the project root or absolute inside it. The spec and bodies go in its parent folder.',
    },
    force: { type: 'boolean', description: 'build only: overwrite files that changed since the last build.' },
  },
  required: ['action', 'spec', 'out'],
}

export type Host = {
  root: () => Promise<string>
  pluginRoot: () => string
  read: (path: string) => Promise<unknown>
  write: (path: string, text: string) => Promise<void>
  list: (path: string) => Promise<{ name: string; kind: string }[]>
  exists: (path: string) => Promise<boolean>
  registerTool: (tool: ToolSpec) => Promise<unknown>
  uiLog: (text: string, to: 'debug' | 'transcript') => void
  runProcess: (argv: readonly string[], init: { cwd: string; timeoutMs: number }) => Promise<{ exitCode: number; stdout: string; stderr: string }>
  check: (tool: string, input: unknown) => Promise<{ decision: 'allow' | 'ask' | 'deny'; reason?: string }>
  ask: (question: string, options: readonly string[]) => Promise<string>
}

/**
 * The closure table over `$`. It sits at module scope because the validator refuses a `$` handed
 * to a nested function. Every engine call the module makes is spelled here, one per member.
 */
export function hostOf($: EngineInterface): Host {
  return {
    root: () => $.session.root(),
    pluginRoot: () => $.plugin.root,
    read: (path: string) => $.fs.read(path),
    write: (path: string, text: string) => $.fs.write(path, text),
    list: (path: string) => $.fs.list(path),
    exists: (path: string) => $.fs.exists(path),
    registerTool: (tool: ToolSpec) => $.tool.register(tool),
    uiLog: (text: string, to: 'debug' | 'transcript') => $.ui.log(text, { to }),
    runProcess: (argv: readonly string[], init: { cwd: string; timeoutMs: number }) => $.process.run(argv, init),
    check: (tool: string, input: unknown) => $.tool.check({ tool, input }),
    ask: (question: string, options: readonly string[]) => $.ui.ask(question, options),
  }
}

/** One record of module memory. Every field resets with the process. */
type Session = {
  projectRoot: string
  /** The path of the planwise config file, which `build` passes to the script. */
  configPath: string
  /** True once the config was resolved in this process. A module reload resets it. */
  resolved: boolean
  /** True when a planwise config was found at resolution. */
  found: boolean
}

const session: Session = { projectRoot: '', configPath: '', resolved: false, found: false }

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/** Logs a failure of one hook. Never throws. */
const failed = (host: Host, where: string, why: string): void => {
  host.uiLog(`build plan: ${where} failed: ${why}`, 'debug')
}

/** Forward slashes and no trailing separator. */
const normPath = (path: string): string => path.replace(/\\/g, '/').replace(/\/+$/, '')

/**
 * Finds the planwise config in the order the feedback module uses: planwise/config.yaml, then
 * config.yaml at the root itself, then each top-level directory in name order.
 */
const findConfig = async (host: Host, root: string): Promise<string | null> => {
  const tryDir = async (dir: string): Promise<string | null> => {
    const path = dir + '/config.yaml'
    if (!(await host.exists(path))) return null
    return isPlanwiseConfig(String(await host.read(path))) ? path : null
  }
  const base = normPath(root)
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

/** Resolves the config into the session record. Throws on a read failure and leaves `resolved` false. */
async function resolveSession(host: Host): Promise<void> {
  const root = await host.root()
  const configPath = await findConfig(host, root)
  session.found = configPath !== null
  session.projectRoot = normPath(root)
  session.configPath = configPath ?? ''
  session.resolved = true
}

/**
 * The session.start body. The loop module's own session.start hook calls it, because a module
 * may register one session.start hook only. It logs every error itself and never throws.
 */
export async function onSessionStart(host: Host): Promise<void> {
  try {
    await resolveSession(host)
    if (!session.found) {
      host.uiLog('build plan: no planwise config.yaml found; tool not registered', 'debug')
      return
    }
    // isDeferred false puts the schema in the prompt's tool list, so the first call needs no search.
    await host.registerTool({ name: TOOL_NAME, description: DESCRIPTION, inputSchema: INPUT_SCHEMA, isDeferred: false })
    host.uiLog(`build plan: registered ${FULL_TOOL_NAME}`, 'debug')
  } catch (err) {
    failed(host, 'session.start hook', errText(err))
  }
}

type Checked =
  | { ok: false; error: string }
  | { ok: true; action: Action; abbrev: string; specText: string; bodies: [string, string][]; out: string; force: boolean }

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isAbsolute = (path: string): boolean => /^([A-Za-z]:)?\//.test(path)

/**
 * Checks the tool input and resolves `out` against the project root. Keys the engine adds beside
 * the tool's own arguments are ignored. A path must stay inside the project root.
 */
export function validateInput(input: Record<string, unknown>, projectRoot: string): Checked {
  const action = input['action']
  if (typeof action !== 'string' || !(ACTIONS as readonly string[]).includes(action)) {
    return { ok: false, error: 'action must be one of keys, lint, build' }
  }
  const spec = input['spec']
  if (!isRecord(spec)) return { ok: false, error: 'spec must be a JSON object' }
  const abbrev = spec['abbrev']
  if (typeof abbrev !== 'string' || !/^[A-Za-z][A-Za-z0-9]{0,15}$/.test(abbrev)) {
    return { ok: false, error: 'spec.abbrev must be 1 to 16 letters or digits, starting with a letter' }
  }

  const rawOut = input['out']
  if (typeof rawOut !== 'string' || rawOut.trim() === '') return { ok: false, error: 'out must be a non-empty path' }
  const outNorm = normPath(rawOut.trim()).replace(/^(\.\/)+/, '')
  if (outNorm.split('/').some((part) => part === '..' || part === '.') || outNorm.includes('\0')) {
    return { ok: false, error: 'out must not hold a . or .. segment' }
  }
  const root = normPath(projectRoot)
  let out = isAbsolute(outNorm) ? outNorm : root + '/' + outNorm
  // A drive-letter root is on Windows, where paths compare without case. Elsewhere case counts.
  const inside = /^[A-Za-z]:/.test(root)
    ? out.toLowerCase().startsWith(root.toLowerCase() + '/')
    : out.startsWith(root + '/')
  if (!inside) {
    return { ok: false, error: 'out must name a folder inside the project root' }
  }
  out = normPath(out)

  const rawBodies = input['bodies']
  const bodies: [string, string][] = []
  if (rawBodies !== undefined) {
    if (!isRecord(rawBodies)) return { ok: false, error: 'bodies must be an object of file name to text' }
    // The script's own discovery pattern is S, two or more digits, a dash, two or more digits, then
    // any suffix. The suffix here admits only file-name characters and never a .. sequence.
    const namePattern = new RegExp('^' + abbrev + '-bodies-(plan|S[0-9]{2,}-[0-9]{2,}[A-Za-z0-9._-]*)\\.md$')
    for (const [name, text] of Object.entries(rawBodies)) {
      if (!namePattern.test(name) || name.includes('..')) {
        return { ok: false, error: `bodies file name ${JSON.stringify(name)} must read ${abbrev}-bodies-plan.md or ${abbrev}-bodies-SXX-YY<suffix>.md` }
      }
      if (typeof text !== 'string') return { ok: false, error: `bodies.${name} must be text` }
      bodies.push([name, text])
    }
  }
  if (action !== 'keys' && bodies.length === 0) return { ok: false, error: `bodies is required for ${action}` }

  const force = input['force']
  if (force !== undefined && typeof force !== 'boolean') return { ok: false, error: 'force must be true or false' }
  if (force === true && action !== 'build') return { ok: false, error: 'force applies to build only' }

  return { ok: true, action: action as Action, abbrev, specText: JSON.stringify(spec, null, 2) + '\n', bodies, out, force: force === true }
}

/** The script arguments after the action, for each action. */
const scriptArgs = (checked: Extract<Checked, { ok: true }>, specPath: string, bodiesDir: string): string[] => {
  if (checked.action === 'keys') return ['--spec', specPath]
  if (checked.action === 'lint') return ['--spec', specPath, '--bodies-dir', bodiesDir]
  const args = ['--spec', specPath, '--bodies-dir', bodiesDir, '--out', checked.out, '--config', session.configPath]
  return checked.force ? [...args, '--force'] : args
}

type RunResult = { exitCode: number; stdout: string; stderr: string }

/**
 * Runs plan_build.py. It tries each interpreter name in turn and moves on only when the process
 * could not start: the run rejects at once, or it exits with the Windows not-found code. Any other
 * non-zero exit is a result, not a failed start.
 */
const runScript = async (host: Host, args: readonly string[]): Promise<RunResult> => {
  let last: unknown
  let notFound: RunResult | undefined
  for (const python of PYTHON_CANDIDATES) {
    const started = Date.now()
    try {
      const run = await host.runProcess([python, '-B', host.pluginRoot() + '/scripts/plan_build.py', ...args], { cwd: session.projectRoot, timeoutMs: RUN_TIMEOUT_MS })
      if (run.exitCode !== WINDOWS_NOT_FOUND) return run
      notFound = run
    } catch (err) {
      if (Date.now() - started >= START_FAILURE_WINDOW_MS) throw err
      last = err
    }
  }
  if (notFound !== undefined) return notFound
  throw last
}

/**
 * The tool result as text. The engine accepts a string, an array or nothing as a plugin tool's
 * result and refuses an object. The first line carries the exit code, the script report follows,
 * and stderr follows a marker line when it holds text.
 */
export const resultText = (run: RunResult): string => {
  const report = run.stdout === '' ? '' : '\n' + run.stdout
  const stderr = run.stderr.trim() === '' ? '' : '\n--- stderr ---\n' + run.stderr
  return `exitCode: ${run.exitCode}` + report + stderr
}

/** Registers the matched tool.call hook only. The session.start work runs through onSessionStart. */
export function register(on: On, options: PluginOptions) {
  void options

  on('tool.call', { tool: FULL_TOOL_NAME }, async ($, e, next) => {
    const host = hostOf($)
    // A module reload re-runs register() without a new session.start. Resolve the config here
    // once, and never register the tool again.
    if (!session.resolved) {
      try {
        await resolveSession(host)
      } catch (err) {
        failed(host, 'config resolution', errText(err))
      }
    }
    if (!session.resolved || !session.found) return { deny: 'build_plan: no planwise config.yaml was found in this project' }
    const checked = validateInput(e as unknown as Record<string, unknown>, session.projectRoot)
    if (!checked.ok) return { deny: 'build_plan: ' + checked.error }

    // This hook answers the call itself, so core's permission prompt never runs. Ask for the
    // engine's verdict before anything is written or run.
    const where = checked.out.startsWith(session.projectRoot + '/') ? checked.out.slice(session.projectRoot.length + 1) : checked.out
    const refusal = await permit(
      host,
      FULL_TOOL_NAME,
      { action: checked.action, out: checked.out, force: checked.force },
      `build_plan to run ${checked.action} for ${where}${checked.force ? ' with force' : ''}`,
    )
    if (refusal !== null) return { deny: 'build_plan: ' + refusal }

    const parent = checked.out.slice(0, checked.out.lastIndexOf('/'))
    const specPath = parent + '/' + checked.abbrev + '-build-spec.json'
    // fs.write creates missing parent directories.
    await host.write(specPath, checked.specText)
    for (const [name, text] of checked.bodies) await host.write(parent + '/' + name, text)

    let run: RunResult
    try {
      run = await runScript(host, [checked.action, ...scriptArgs(checked, specPath, parent)])
    } catch (err) {
      failed(host, 'plan_build.py run', errText(err))
      return { deny: 'build_plan: plan_build.py did not run: ' + errText(err) }
    }
    if (run.exitCode !== 0) host.uiLog(`build plan: ${checked.action} exit ${run.exitCode}`, 'debug')
    return { result: resultText(run) }
  }).catch(($, e, next) => {
    failed(hostOf($), 'tool.call hook', failureText(next.error))
    return next.called ? next(e) : { deny: 'build_plan: internal error; see the debug log' }
  })
}
