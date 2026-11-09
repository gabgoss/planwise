import { test } from 'node:test'
import assert from 'node:assert/strict'
import { onSessionStart, register, resultText, validateInput } from '../../plugins/planwise/hooks/build-plan.ts'
import type { Host } from '../../plugins/planwise/hooks/build-plan.ts'
import { permit, refusedByRule } from '../../plugins/planwise/hooks/permission.ts'

// build-plan.ts value-imports only plain .ts files, so Node loads it with no loader stub.
// The tests inject a fake process runner. The module sees it through `Host` (session.start work)
// or through a fake `$` (the tool.call hook, which builds its own Host with hostOf).

const REGISTERED = 'mcp__planwise__build_plan'
const NEVER_REGISTERED = 'mcp__planwise__never_registered_tool'
const ROOT = 'C:/work/proj'
const CONFIG = 'project:\n  name: demo\n'
const KNOWN_REPORT = 'session=QZX-S01-01 keys_missing=0 errors=0\n'

type Run = { argv: readonly string[]; init: { cwd: string; timeoutMs: number } }
type Reply = { exitCode: number; stdout: string; stderr: string }

type Verdict = { decision: 'allow' | 'ask' | 'deny'; reason?: string }

/**
 * In-memory files, a recorded log, recorded registrations, process runs, permission checks and
 * questions. The permission verdict defaults to allow; `answer` is what the user picks on an ask,
 * or an Error when no one can be asked.
 */
const world = (
  files: Record<string, string>,
  reply: Reply | (() => Promise<Reply>),
  gate: { verdict?: Verdict; answer?: string | Error } = {},
) => {
  const store = new Map(Object.entries(files))
  const runs: Run[] = []
  const logs: string[] = []
  const registered: unknown[] = []
  const writes: string[] = []
  const checks: { tool: string; input: unknown }[] = []
  const questions: string[] = []
  const check = async (tool: string, input: unknown): Promise<Verdict> => {
    checks.push({ tool, input })
    return gate.verdict ?? { decision: 'allow' }
  }
  const ask = async (question: string): Promise<string> => {
    questions.push(question)
    if (gate.answer instanceof Error) throw gate.answer
    return gate.answer ?? 'Allow'
  }
  const run = async (argv: readonly string[], init: { cwd: string; timeoutMs: number }): Promise<Reply> => {
    runs.push({ argv, init })
    return typeof reply === 'function' ? reply() : reply
  }
  const host: Host = {
    root: async () => ROOT,
    pluginRoot: () => 'C:/plugins/planwise',
    read: async (path) => store.get(path),
    write: async (path, text) => {
      store.set(path, text)
      writes.push(path)
    },
    list: async () => [{ name: 'planwise', kind: 'dir' }],
    exists: async (path) => store.has(path),
    registerTool: async (tool) => {
      registered.push(tool)
    },
    uiLog: (text) => {
      logs.push(text)
    },
    runProcess: run,
    check,
    ask,
  }
  // The fake `$` that hostOf closes over: the same members, shaped as the engine shapes them.
  const engine = {
    session: { root: host.root },
    plugin: { root: host.pluginRoot() },
    fs: { read: host.read, write: host.write, list: host.list, exists: host.exists },
    tool: { register: host.registerTool, check: (args: { tool: string; input: unknown }) => check(args.tool, args.input) },
    ui: { log: (text: string) => host.uiLog(text, 'debug'), ask },
    process: { run },
  }
  return { host, engine, store, runs, logs, registered, writes, checks, questions }
}

type Hook = (engine: unknown, event: unknown, next: unknown) => Promise<unknown>

/** Registers the module against a fake `on` and captures each hook by its matched tool name. */
const capture = () => {
  const hooks = new Map<string, Hook>()
  const on = (_name: string, match: { tool: string }, run: Hook) => {
    hooks.set(match.tool, run)
    return { catch: () => undefined }
  }
  register(on as never, {} as never)
  return hooks
}

/** Engine-style dispatch: a tool.call runs the hook whose matcher names the tool, if any. */
const dispatch = async (hooks: Map<string, Hook>, engine: unknown, tool: string, input: Record<string, unknown>) => {
  const hook = hooks.get(tool)
  if (hook === undefined) return undefined
  return hook(engine, { tool, ...input }, () => undefined)
}

const SPEC = { abbrev: 'QZX', plan_name: 'Demo' }
const KEYS_INPUT = { action: 'keys', spec: SPEC, out: 'planwise/Plans/Demo/QZX' }
const GOOD_FILES = { [ROOT + '/planwise/config.yaml']: CONFIG }

test('buildplan registers the tool when a planwise config exists', async () => {
  const w = world(GOOD_FILES, { exitCode: 0, stdout: '', stderr: '' })
  await onSessionStart(w.host)
  assert.equal(w.registered.length, 1)
  const tool = w.registered[0] as { name: string; isDeferred: boolean; inputSchema: { required: string[] } }
  assert.equal(tool.name, 'build_plan')
  assert.equal(tool.isDeferred, false)
  assert.deepEqual(tool.inputSchema.required, ['action', 'spec', 'out'])
})

test('buildplan registers nothing when no planwise config exists', async () => {
  const w = world({}, { exitCode: 0, stdout: '', stderr: '' })
  await onSessionStart(w.host)
  assert.equal(w.registered.length, 0)
  assert.ok(w.logs.some((line) => line.includes('tool not registered')))
})

test('buildplan keys call returns the known report through the injected runner', async () => {
  const w = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' })
  await onSessionStart(w.host)
  const hooks = capture()
  const out = (await dispatch(hooks, w.engine, REGISTERED, KEYS_INPUT)) as { result: unknown }
  // The engine refuses an object result for a plugin tool; the result must be text.
  assert.equal(typeof out.result, 'string')
  assert.equal(out.result, 'exitCode: 0\n' + KNOWN_REPORT)
  assert.equal(w.runs.length, 1)
  const argv = w.runs[0]!.argv
  assert.equal(argv[0], 'python')
  assert.ok(argv.includes('keys'))
  assert.ok(argv.includes('--spec'))
  assert.equal(w.runs[0]!.init.cwd, ROOT)
  assert.equal(w.runs[0]!.init.timeoutMs, 540_000)
  assert.ok(w.writes.includes(ROOT + '/planwise/Plans/Demo/QZX-build-spec.json'))
})

test('buildplan non-zero exit is a result, not a deny', async () => {
  const w = world(GOOD_FILES, { exitCode: 2, stdout: '', stderr: 'refused' })
  await onSessionStart(w.host)
  const out = (await dispatch(capture(), w.engine, REGISTERED, KEYS_INPUT)) as { result: string }
  assert.equal(out.result, 'exitCode: 2\n--- stderr ---\nrefused')
})

test('buildplan resultText puts the exit code first and omits an empty stderr', () => {
  assert.equal(resultText({ exitCode: 0, stdout: KNOWN_REPORT, stderr: '' }), 'exitCode: 0\n' + KNOWN_REPORT)
  assert.equal(resultText({ exitCode: 1, stdout: '', stderr: '  \n' }), 'exitCode: 1')
})

test('buildplan unknown action is denied with a message naming the field', async () => {
  const w = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' })
  await onSessionStart(w.host)
  const out = (await dispatch(capture(), w.engine, REGISTERED, { ...KEYS_INPUT, action: 'destroy' })) as { deny: string }
  assert.match(out.deny, /action must be one of keys, lint, build/)
  assert.equal(w.runs.length, 0)
  assert.equal(w.writes.length, 0)
})

test('buildplan out outside the project root is denied', async () => {
  assert.deepEqual(validateInput({ ...KEYS_INPUT, out: '../elsewhere/x' }, ROOT), { ok: false, error: 'out must not hold a . or .. segment' })
  const outside = validateInput({ ...KEYS_INPUT, out: 'D:/other/x' }, ROOT)
  assert.equal(outside.ok, false)
})

test('buildplan a . segment that would resolve to the root or its parent is denied', () => {
  for (const out of ['.', 'planwise/.', './.', 'planwise/./Plans/X']) {
    assert.deepEqual(validateInput({ ...KEYS_INPUT, out }, ROOT), { ok: false, error: 'out must not hold a . or .. segment' }, out)
  }
  assert.equal(validateInput({ ...KEYS_INPUT, out: './planwise/Plans/Demo/QZX' }, ROOT).ok, true)
})

test('buildplan root containment ignores case on a drive-letter root only', () => {
  assert.equal(validateInput({ ...KEYS_INPUT, out: 'c:/WORK/proj/planwise/X' }, ROOT).ok, true)
  assert.equal(validateInput({ ...KEYS_INPUT, out: '/home/u/proj/x' }, '/home/u/Proj').ok, false)
  assert.equal(validateInput({ ...KEYS_INPUT, out: '/home/u/Proj/x' }, '/home/u/Proj').ok, true)
})

test('buildplan bodies names follow the script discovery pattern', () => {
  const withBodies = (name: string) => validateInput({ ...KEYS_INPUT, action: 'lint', bodies: { [name]: 'x' } }, ROOT).ok
  assert.equal(withBodies('QZX-bodies-plan.md'), true)
  assert.equal(withBodies('QZX-bodies-S01-01.md'), true)
  assert.equal(withBodies('QZX-bodies-S100-01.v2.md'), true)
  assert.equal(withBodies('QZX-bodies-S01-01-part2.md'), true)
  assert.equal(withBodies('QZX-bodies-S01-01..md'), false)
  assert.equal(withBodies('QZX-bodies-S1-01.md'), false)
  assert.equal(withBodies('OTHER-bodies-plan.md'), false)
})

test('buildplan control: the registered name returns the report', async () => {
  const w = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' })
  await onSessionStart(w.host)
  const out = (await dispatch(capture(), w.engine, REGISTERED, KEYS_INPUT)) as { result: string } | undefined
  assert.equal(out?.result, 'exitCode: 0\n' + KNOWN_REPORT)
})

test('buildplan control: a name the module never registers gets no result', async () => {
  const w = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' })
  await onSessionStart(w.host)
  const hooks = capture()
  assert.ok(hooks.has(REGISTERED))
  assert.equal(hooks.has(NEVER_REGISTERED), false)
  assert.equal(await dispatch(hooks, w.engine, NEVER_REGISTERED, KEYS_INPUT), undefined)
  assert.equal(w.runs.length, 0)
})

const BODIES = { 'QZX-bodies-S01-01.md': '<!-- doc -->\n' }

test('buildplan build passes --config and --force, and lint passes neither', async () => {
  const w = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' })
  await onSessionStart(w.host)
  const hooks = capture()
  await dispatch(hooks, w.engine, REGISTERED, { ...KEYS_INPUT, action: 'build', bodies: BODIES, force: true })
  await dispatch(hooks, w.engine, REGISTERED, { ...KEYS_INPUT, action: 'lint', bodies: BODIES })
  assert.equal(w.runs.length, 2)
  const build = w.runs[0]!.argv
  const lint = w.runs[1]!.argv
  assert.equal(build[build.indexOf('--config') + 1], ROOT + '/planwise/config.yaml')
  assert.equal(build[build.indexOf('--out') + 1], ROOT + '/planwise/Plans/Demo/QZX')
  assert.ok(build.includes('--force'))
  assert.equal(lint.includes('--force'), false)
  assert.equal(lint.includes('--config'), false)
  assert.equal(lint[lint.indexOf('--bodies-dir') + 1], ROOT + '/planwise/Plans/Demo')
  assert.ok(w.writes.includes(ROOT + '/planwise/Plans/Demo/QZX-bodies-S01-01.md'))
  const denied = (await dispatch(hooks, w.engine, REGISTERED, { ...KEYS_INPUT, action: 'lint', bodies: BODIES, force: true })) as { deny: string }
  assert.match(denied.deny, /force applies to build only/)
})

test('buildplan asks the engine for a permission verdict on its own tool before any write', async () => {
  const w = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' })
  await onSessionStart(w.host)
  await dispatch(capture(), w.engine, REGISTERED, { ...KEYS_INPUT, action: 'build', bodies: BODIES, force: true })
  assert.equal(w.checks.length, 1)
  assert.equal(w.checks[0]!.tool, REGISTERED)
  assert.deepEqual(w.checks[0]!.input, { action: 'build', out: ROOT + '/planwise/Plans/Demo/QZX', force: true })
  assert.equal(w.questions.length, 0)
  assert.equal(w.runs.length, 1)
})

test('buildplan a deny verdict refuses the call before anything is written or run', async () => {
  const w = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' }, { verdict: { decision: 'deny', reason: 'plan mode' } })
  await onSessionStart(w.host)
  const out = (await dispatch(capture(), w.engine, REGISTERED, KEYS_INPUT)) as { deny: string }
  assert.equal(out.deny, 'build_plan: plan mode')
  assert.equal(w.writes.length, 0)
  assert.equal(w.runs.length, 0)
})

test('buildplan an ask verdict puts the question to the user and runs only on Allow', async () => {
  const allowed = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' }, { verdict: { decision: 'ask' }, answer: 'Allow' })
  await onSessionStart(allowed.host)
  const ran = (await dispatch(capture(), allowed.engine, REGISTERED, { ...KEYS_INPUT, action: 'build', bodies: BODIES, force: true })) as { result: string }
  assert.equal(ran.result, 'exitCode: 0\n' + KNOWN_REPORT)
  assert.deepEqual(allowed.questions, ['Allow build_plan to run build for planwise/Plans/Demo/QZX with force?'])

  const refused = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' }, { verdict: { decision: 'ask' }, answer: 'Deny' })
  await onSessionStart(refused.host)
  const no = (await dispatch(capture(), refused.engine, REGISTERED, KEYS_INPUT)) as { deny: string }
  assert.equal(no.deny, 'build_plan: the user did not allow this call')
  assert.equal(refused.writes.length, 0)
  assert.equal(refused.runs.length, 0)
})

test('buildplan an ask with no one to ask (a headless run) refuses the call', async () => {
  const w = world(GOOD_FILES, { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' }, { verdict: { decision: 'ask' }, answer: new Error('no one to ask') })
  await onSessionStart(w.host)
  const out = (await dispatch(capture(), w.engine, REGISTERED, KEYS_INPUT)) as { deny: string }
  assert.match(out.deny, /needs permission and no one could be asked; add an allow rule for mcp__planwise__build_plan/)
  assert.equal(w.writes.length, 0)
  assert.equal(w.runs.length, 0)
})

test('buildplan permit refuses on a failed check and gives a default deny reason', async () => {
  const failing = { check: async () => { throw new Error('engine gone') }, ask: async () => 'Allow' }
  assert.equal(await permit(failing, REGISTERED, {}, 'x'), 'the permission check failed: engine gone')
  const bare = { check: async () => ({ decision: 'deny' as const }), ask: async () => 'Allow' }
  assert.equal(await permit(bare, REGISTERED, {}, 'x'), 'the permission settings refuse this call')
})

test('buildplan refusedByRule refuses only on a deny and never asks', async () => {
  const verdict = (decision: 'allow' | 'ask' | 'deny', reason?: string) => async () => ({ decision, reason })
  assert.equal(await refusedByRule(verdict('allow'), REGISTERED, {}), null)
  assert.equal(await refusedByRule(verdict('ask'), REGISTERED, {}), null)
  assert.equal(await refusedByRule(verdict('deny', 'a deny rule'), REGISTERED, {}), 'a deny rule')
  assert.equal(await refusedByRule(verdict('deny'), REGISTERED, {}), 'the permission settings refuse this call')
  assert.equal(await refusedByRule(async () => { throw new Error('gone') }, REGISTERED, {}), 'the permission check failed: gone')
})

test('buildplan the Windows not-found exit moves to the next interpreter name', async () => {
  let calls = 0
  const w = world(GOOD_FILES, async () => {
    calls += 1
    return calls === 1 ? { exitCode: 9009, stdout: '', stderr: 'Python was not found' } : { exitCode: 0, stdout: KNOWN_REPORT, stderr: '' }
  })
  await onSessionStart(w.host)
  const out = (await dispatch(capture(), w.engine, REGISTERED, KEYS_INPUT)) as { result: string }
  assert.equal(w.runs.length, 2)
  assert.equal(w.runs[0]!.argv[0], 'python')
  assert.equal(w.runs[1]!.argv[0], 'python3')
  assert.equal(out.result, 'exitCode: 0\n' + KNOWN_REPORT)
})
