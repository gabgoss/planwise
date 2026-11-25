import { test } from 'node:test'
import assert from 'node:assert/strict'
import { register as registerLoader } from 'node:module'
import { failureText, isCurrent, keyOf, releaseLatch, stepOf } from '../../plugins/planwise/hooks/loop/boundary.ts'

// Node cannot load the .tsx review card, and the engine's `claude-code` module has no node runtime.
// This loader hook resolves both to stubs, so register.ts can load here. The card has its own tests.
const stubUrl = (source: string): string => 'data:text/javascript,' + encodeURIComponent(source)
const loaderSource = `
const stubs = {
  'claude-code': ${JSON.stringify(stubUrl('export const atom = (ref, initial) => ({ ref, initial }); export const read = async () => undefined; export const update = async () => undefined'))},
  feedbackCard: ${JSON.stringify(stubUrl('export const register = () => {}'))},
  updateBanner: ${JSON.stringify(stubUrl('export const register = () => {}'))},
}
export async function resolve(specifier, context, next) {
  if (specifier === 'claude-code') return { url: stubs['claude-code'], shortCircuit: true }
  if (specifier.endsWith('feedback-card.tsx')) return { url: stubs.feedbackCard, shortCircuit: true }
  if (specifier.endsWith('update-banner.tsx')) return { url: stubs.updateBanner, shortCircuit: true }
  return next(specifier, context)
}
`
registerLoader(stubUrl(loaderSource), import.meta.url)

// The module under test. REGISTER_URL points the same tests at another copy of register.ts.
const target = process.env.REGISTER_URL ?? new URL('../../plugins/planwise/hooks/register.ts', import.meta.url).href
const { register } = await import(target)

const MARKER = 'BACKLOG LOOP: run=r1 done=5 remaining=2 state=a.json'
const MARKER_B = 'BACKLOG LOOP: run=r1 done=6 remaining=1 state=a.json'
const COMMANDS = [{ name: 'planwise:planwise', source: 'skill', plugin: 'planwise' }]

// The keys are the run dict of backlog_loop.py --init and its queue_meta entries, copied verbatim.
const runFile = (disposition: string): string =>
  JSON.stringify({
    schema_version: 1,
    run_id: 'r1',
    created: '2026-01-01T00:00:00',
    ended: null,
    mode: 'all',
    n: null,
    filters: { priority: null, abbrev: null, status: null },
    no_check: false,
    refine_max: 0,
    excluded: [],
    warnings: [],
    queue: ['010'],
    queue_meta: { '010': { route_at_init: 'C', score: 10, feature: 'Next item', refined_at_init: false, disposition_at_init: disposition } },
    known_ids_at_init: ['005', '010'],
    current: '005',
    items: {},
    history: [{ at: '2026-01-01T00:00:00', event: 'init', id: null, detail: 'mode=all n=- queue=1 excluded=0' }],
  })

const flush = async () => {
  for (let i = 0; i < 10; i++) await new Promise((resolve) => setImmediate(resolve))
}

/** Registers the module against a fake engine: captured hooks, a manual clock, recorded calls. */
const harness = (
  opts: {
    compact?: () => Promise<{ skip?: string }>
    runCommand?: () => Promise<unknown>
    commands?: typeof COMMANDS
    list?: () => Promise<typeof COMMANDS>
    read?: (path: string) => Promise<unknown>
  } = {},
) => {
  const hooks = new Map<string, { run: (...a: unknown[]) => unknown; catcher?: (...a: unknown[]) => unknown }>()
  const registrations: { name: string; matcher: unknown }[] = []
  // `on(name, hook)` or `on(name, matcher, hook)`. The loop module registers last, so its hook wins the map.
  const on = (name: string, a: unknown, b?: unknown) => {
    const matched = typeof a !== 'function'
    const run = (matched ? b : a) as (...x: unknown[]) => unknown
    registrations.push({ name, matcher: matched ? a : undefined })
    const rec: { run: (...a: unknown[]) => unknown; catcher?: (...a: unknown[]) => unknown } = { run }
    hooks.set(name, rec)
    return { catch: (c: (...a: unknown[]) => unknown) => void (rec.catcher = c) }
  }
  const logs: string[] = []
  const channels: string[] = []
  const calls = { compact: 0, runCommand: 0 }
  const reads: string[] = []
  const timers: { ms: number; fn: () => void; cancelled: boolean; fired: boolean; cancel: () => void }[] = []
  const $ = {
    clock: {
      after: (ms: number, fn: () => void) => {
        const t = { ms, fn, cancelled: false, fired: false, cancel: () => void (t.cancelled = true) }
        timers.push(t)
        return t
      },
    },
    session: { compact: () => (calls.compact++, (opts.compact ?? (async () => ({})))()) },
    command: { run: () => (calls.runCommand++, (opts.runCommand ?? (async () => ({})))()), list: opts.list ?? (async () => opts.commands ?? COMMANDS) },
    fs: { read: (path: string) => (reads.push(path), (opts.read ?? (async () => runFile('plan')))(path)) },
    ui: { log: (text: string, o?: { to?: string }) => void (logs.push(text), channels.push(o?.to ?? 'transcript')) },
    env: { get: async () => '1' },
  }
  register(on, {})
  const run = (name: string, e: Record<string, unknown>, next: (e: unknown) => unknown = (x) => x) => hooks.get(name)!.run($, e, next)
  const caught = (name: string, error: unknown, called: boolean, replay: unknown = 'replayed') => {
    const next = Object.assign(() => replay, { error, called })
    return hooks.get(name)!.catcher!($, {}, next)
  }
  const complete = (answer: string) => run('turn.complete', { reason: 'answer', answer })
  // Fires every pending timer, or only those armed for `ms`.
  const fire = async (ms?: number) => {
    for (const t of timers.filter((x) => !x.cancelled && !x.fired && (ms === undefined || x.ms === ms))) {
      t.fired = true
      t.fn()
    }
    await flush()
  }
  // A plan-dialog ask: the hook's answer, plus every value the fake `next` received.
  const ask = async (tool: string, extra: Record<string, unknown> = {}) => {
    const nexts: unknown[] = []
    const answer = await hooks.get('classic.PermissionRequest')!.run($, { tool_name: tool, ...extra }, (x: unknown) => (nexts.push(x), 'NEXT'))
    return { answer, nexts }
  }
  return { run, caught, complete, fire, ask, logs, channels, calls, reads, timers, registrations }
}

test('load: no event has more than one unmatched registration across the composed module', () => {
  // Claude Code 2.1.325 refuses the whole module when one event is registered twice without a matcher.
  const h = harness()
  const unmatched = new Map<string, number>()
  for (const r of h.registrations) if (r.matcher === undefined) unmatched.set(r.name, (unmatched.get(r.name) ?? 0) + 1)
  const twice = [...unmatched].filter(([, n]) => n > 1).map(([name]) => name)
  assert.deepEqual(twice, [])
  assert.ok(h.registrations.some((r) => r.name === 'tool.call' && r.matcher === undefined), 'agent-guard keeps the unmatched tool.call')
})

test('load: the loop tracks questions through a tool.call hook matched on AskUserQuestion', () => {
  const h = harness()
  const loop = h.registrations.filter((r) => r.name === 'tool.call' && (r.matcher as { tool?: string } | undefined)?.tool === 'AskUserQuestion')
  assert.equal(loop.length, 1)
})

test('stepOf: idle goes, busy defers until the cap, then abandons', () => {
  assert.equal(stepOf({ turnRunning: false, pendingQuestion: false, deferrals: 0, max: 20 }), 'go')
  assert.equal(stepOf({ turnRunning: true, pendingQuestion: false, deferrals: 19, max: 20 }), 'defer')
  assert.equal(stepOf({ turnRunning: false, pendingQuestion: true, deferrals: 20, max: 20 }), 'abandon')
})

test('releaseLatch / keyOf / isCurrent / failureText', () => {
  const marker = { runId: 'r1', doneId: '5', remaining: 2, statePath: 'a.json' }
  assert.equal(keyOf(marker), 'r1:5')
  assert.equal(releaseLatch('r1:5', 'r1:5'), null)
  assert.equal(releaseLatch('r1:6', 'r1:5'), 'r1:6')
  assert.equal(isCurrent(2, 2), true)
  assert.equal(isCurrent(1, 2), false)
  assert.equal(failureText({ kind: 'throw', message: 'boom' }), 'throw: boom')
  assert.equal(failureText({ kind: 'timeout' }), 'timeout')
})

test('finding 1: a rejected compaction defers and the boundary still re-enters', async () => {
  let n = 0
  const h = harness({ compact: async () => (n++ === 0 ? Promise.reject(new Error('turn running')) : {}) })
  await h.run('session.start', { isInteractive: true })
  h.complete(MARKER)
  await h.fire()
  assert.equal(h.calls.runCommand, 0)
  await h.fire()
  assert.equal(h.calls.compact, 2)
  assert.equal(h.calls.runCommand, 1)
})

test('finding 1: a rejected re-entry releases the latch, so the same marker can start again', async () => {
  const h = harness({ runCommand: async () => Promise.reject(new Error('nope')) })
  await h.run('session.start', { isInteractive: true })
  h.complete(MARKER)
  await h.fire()
  assert.ok(h.logs.some((l) => l.startsWith('backlog loop: re-entry rejected: nope')))
  h.complete(MARKER)
  await h.fire()
  assert.equal(h.calls.runCommand, 2)
})

test('finding 2: a marker that arrives during a question is deferred, not lost', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  let release = () => {}
  const open = new Promise<void>((resolve) => (release = resolve))
  const asking = h.run('tool.call', { tool: 'AskUserQuestion' }, () => open)
  h.complete(MARKER)
  await h.fire()
  assert.equal(h.calls.compact, 0)
  release()
  await asking
  await h.fire()
  assert.equal(h.calls.compact, 1)
  assert.equal(h.calls.runCommand, 1)
})

test('finding 3: a hook failure logs its kind and message, never [object Object]', () => {
  const h = harness()
  h.caught('turn.complete', { kind: 'throw', message: 'boom', budget: 1000 }, false)
  assert.ok(h.logs.some((l) => l.includes('throw: boom')))
  assert.ok(!h.logs.some((l) => l.includes('[object Object]')))
})

test('finding 4: a reloaded module with no session.start still resolves the skill and re-enters', async () => {
  const h = harness()
  h.complete(MARKER)
  await h.fire()
  assert.equal(h.calls.runCommand, 1)
})

// timers[0] is the update check's session-start timer and timers[1] its redraw request. The
// boundary timers follow them.
const FIRST_BOUNDARY = 2

test('finding 5: a newer marker cancels the pending boundary, so only one re-entry happens', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete(MARKER)
  h.complete(MARKER_B)
  assert.equal(h.timers[FIRST_BOUNDARY]?.cancelled, true)
  h.timers[FIRST_BOUNDARY]?.fn()
  await h.fire()
  assert.equal(h.calls.compact, 1)
  assert.equal(h.calls.runCommand, 1)
})

test('finding 5: a session end invalidates a pending boundary', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete(MARKER)
  h.run('classic.SessionEnd', {})
  assert.ok(h.timers[FIRST_BOUNDARY] !== undefined, 'the boundary timer must exist, or the absence below proves nothing')
  h.timers[FIRST_BOUNDARY]?.fn()
  await flush()
  assert.equal(h.calls.compact, 0)
})

test('startup: the re-entry skill line goes to debug and the no-skill line stays on the transcript', async () => {
  const found = harness()
  await found.run('session.start', { isInteractive: true })
  const foundAt = found.logs.findIndex((l) => l.startsWith('backlog loop: re-entry skill'))
  assert.notEqual(foundAt, -1)
  assert.equal(found.channels[foundAt], 'debug')

  const missing = harness({ commands: [{ name: 'other:thing', source: 'skill', plugin: 'other' }] })
  await missing.run('session.start', { isInteractive: true })
  const missingAt = missing.logs.findIndex((l) => l === 'backlog loop: no planwise skill found; re-entry disabled')
  assert.notEqual(missingAt, -1)
  assert.equal(missing.channels[missingAt], 'transcript')
})

test('finding 6: a catch handler whose hook already called next replays next(e)', () => {
  const h = harness()
  for (const name of ['session.start', 'turn.start', 'tool.call', 'turn.complete', 'classic.PermissionRequest', 'classic.SessionEnd']) {
    assert.equal(h.caught(name, { kind: 'timeout', budget: 1 }, true), 'replayed', name)
  }
})

// The plan-exit answer. A loop marker that ends its answer is eligible, and only the boundary arms.
const FINAL = 'Item closed.\n' + MARKER
const PLAN_MARKER = 'PLANWISE PLAN-MODE: command=plan policy=auto'
const EXIT_LITERAL = { behavior: 'allow', updatedInput: {}, updatedPermissions: [{ type: 'setMode', mode: 'acceptEdits', destination: 'session' }] }
const ENTER_LITERAL = { behavior: 'allow', updatedInput: {} }
const EXIT_LINE = 'plan exit: answered ExitPlanMode (context=loop, mode=acceptEdits)'
const EXPIRY_MS = 300000
const LEFT_LINE = 'plan exit: dialog left to the user (no planwise context)'

type Harness = ReturnType<typeof harness>

/** Drives a final-line loop marker through its boundary, so the module re-enters armed. */
const armedByBoundary = async (h: Harness) => {
  await h.run('session.start', { isInteractive: true })
  h.complete(FINAL)
  await h.fire()
  assert.equal(h.calls.runCommand, 1, 'the boundary must have re-entered')
}

/** Asserts the armed answer first, so a module that never arms cannot pass the disarm cases. */
const assertAnswered = async (h: Harness, tool = 'ExitPlanMode', extra: Record<string, unknown> = {}) => {
  const { answer, nexts } = await h.ask(tool, extra)
  assert.deepEqual(answer, { decision: tool === 'ExitPlanMode' ? EXIT_LITERAL : ENTER_LITERAL })
  assert.equal(nexts.length, 0)
}

const assertLeftToUser = async (h: Harness, tool = 'ExitPlanMode', extra: Record<string, unknown> = {}) => {
  const { answer, nexts } = await h.ask(tool, extra)
  assert.equal(nexts.length, 1)
  assert.equal(answer, 'NEXT')
}

test('plan exit 1: one classic.PermissionRequest registration carries the two-tool matcher', () => {
  const h = harness()
  const regs = h.registrations.filter((r) => r.name === 'classic.PermissionRequest')
  assert.equal(regs.length, 1)
  assert.deepEqual(regs[0]?.matcher, { tool_name: ['ExitPlanMode', 'EnterPlanMode'] })
})

test('plan exit 2: after the boundary an ExitPlanMode ask gets the exit literal and the answered line', async () => {
  const h = harness()
  await armedByBoundary(h)
  const { answer, nexts } = await h.ask('ExitPlanMode')
  assert.deepEqual(answer, { decision: EXIT_LITERAL })
  assert.equal(nexts.length, 0)
  assert.ok(h.logs.includes(EXIT_LINE))
  assert.equal(h.channels[h.logs.indexOf(EXIT_LINE)], 'transcript')
})

test('plan exit 3: after the boundary an EnterPlanMode ask gets the enter literal', async () => {
  const h = harness()
  await armedByBoundary(h)
  await assertAnswered(h, 'EnterPlanMode')
  assert.ok(h.logs.includes('plan exit: answered EnterPlanMode (context=loop)'))
})

test('plan exit 4: with no marker the ask goes to next once, its value returns, and the debug line lands', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  const { answer, nexts } = await h.ask('ExitPlanMode')
  assert.equal(nexts.length, 1)
  assert.equal(answer, 'NEXT')
  const at = h.logs.indexOf(LEFT_LINE)
  assert.notEqual(at, -1)
  assert.equal(h.channels[at], 'debug')
})

test('plan exit 5: a session end after the boundary disarms the ask', async () => {
  const h = harness()
  await armedByBoundary(h)
  await assertAnswered(h)
  h.run('classic.SessionEnd', {})
  await assertLeftToUser(h)
})

test('plan exit 6: a main-loop answer with no marker after the boundary disarms the ask', async () => {
  const h = harness()
  await armedByBoundary(h)
  await assertAnswered(h)
  h.complete('Plain answer, no marker.')
  await assertLeftToUser(h)
})

test('plan exit 7: a remaining=0 marker after the boundary disarms the ask and schedules no boundary', async () => {
  const h = harness()
  await armedByBoundary(h)
  await assertAnswered(h)
  const timersBefore = h.timers.length
  h.complete('Last item.\nBACKLOG LOOP: run=r1 done=7 remaining=0 state=a.json')
  assert.equal(h.timers.length, timersBefore)
  await h.fire()
  assert.equal(h.calls.runCommand, 1)
  await assertLeftToUser(h)
})

test('plan exit 8: a loop marker above a final sentence still re-enters, and the ask after it goes to next', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete('Item closed.\n' + MARKER + '\nThat is all.')
  await h.fire()
  assert.equal(h.calls.runCommand, 1)
  await assertLeftToUser(h)
})

test('plan exit 9: a subagent turn.complete after the boundary leaves the arming in place', async () => {
  const h = harness()
  await armedByBoundary(h)
  await assertAnswered(h)
  h.run('turn.complete', { agentId: 'a1', reason: 'answer', answer: 'sub answer' })
  await assertAnswered(h)
})

test('plan exit 10: an ask from a subagent goes to next while the main ask is answered', async () => {
  const h = harness()
  await armedByBoundary(h)
  await assertAnswered(h)
  await assertLeftToUser(h, 'ExitPlanMode', { agent_id: 'a1' })
})

test('plan exit 11: a typed turn between the marker and the boundary is unarmed, and the boundary arms its own re-entry', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete(FINAL)
  h.complete('A turn the person typed, no marker.')
  await assertLeftToUser(h)
  await h.fire()
  assert.equal(h.calls.runCommand, 1)
  await assertAnswered(h)
})

test('plan exit 12: a rejected re-entry is armed at the call and disarmed after the rejection', async () => {
  let probe: (() => Promise<unknown>) | undefined
  let during: unknown
  const h = harness({
    runCommand: async () => {
      during = (await probe!() as { answer: unknown }).answer
      throw new Error('nope')
    },
  })
  probe = () => h.ask('ExitPlanMode')
  await h.run('session.start', { isInteractive: true })
  h.complete(FINAL)
  await h.fire()
  assert.deepEqual(during, { decision: EXIT_LITERAL }, 'the ask during the re-entry is answered')
  assert.ok(h.logs.some((l) => l.startsWith('backlog loop: re-entry rejected: nope')))
  await assertLeftToUser(h)
})

test('plan exit 13: the plan-mode marker arms one turn with no boundary, and the next turn end clears it', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  const timersBefore = h.timers.length
  h.complete('Send any message to start.\n' + PLAN_MARKER)
  assert.deepEqual(h.timers.slice(timersBefore).map((t) => t.ms), [EXPIRY_MS], 'only the expiry timer is scheduled, no boundary')
  const { answer } = await h.ask('EnterPlanMode')
  assert.deepEqual(answer, { decision: ENTER_LITERAL })
  assert.ok(h.logs.includes('plan exit: answered EnterPlanMode (context=plan-session)'))
  await assertAnswered(h)
  h.complete('The plan is written.')
  await assertLeftToUser(h)
})

test('plan exit 14: a non-interactive session never arms, for either marker', async () => {
  const control = harness()
  await control.run('session.start', { isInteractive: true })
  control.complete(PLAN_MARKER)
  await assertAnswered(control)

  const h = harness()
  await h.run('session.start', { isInteractive: false })
  h.complete(FINAL)
  await h.fire()
  assert.equal(h.calls.runCommand, 0)
  await assertLeftToUser(h)
  h.complete(PLAN_MARKER)
  await assertLeftToUser(h)
})

test('plan exit 15: a session start after the boundary disarms the ask', async () => {
  const h = harness()
  await armedByBoundary(h)
  await assertAnswered(h)
  await h.run('session.start', { isInteractive: true })
  await assertLeftToUser(h)
})

test('plan exit 16: between the marker and the boundary the ask goes to next, and after the boundary it is answered', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete(FINAL)
  await assertLeftToUser(h)
  await h.fire()
  assert.equal(h.calls.runCommand, 1)
  await assertAnswered(h)
})

/** Drives the boundary and asserts that the re-entry ran unarmed. */
const assertUnarmedReentry = async (h: Harness) => {
  await h.run('session.start', { isInteractive: true })
  h.complete(FINAL)
  await h.fire()
  assert.equal(h.calls.runCommand, 1, 'the re-entry still runs')
  await assertLeftToUser(h)
}

test('plan exit 17: the boundary reads the run file at the state path of the marker, and a plan item next arms', async () => {
  const h = harness()
  await armedByBoundary(h)
  assert.deepEqual(h.reads, ['a.json'])
  await assertAnswered(h)
})

test('plan exit 18: a run item next re-enters unarmed', async () => {
  await assertUnarmedReentry(harness({ read: async () => runFile('run') }))
})

test('plan exit 19: an unreadable, unparsable or non-text run file re-enters unarmed', async () => {
  await assertUnarmedReentry(harness({ read: async () => Promise.reject(new Error('ENOENT')) }))
  await assertUnarmedReentry(
    harness({
      read: () => {
        throw new Error('sync refusal')
      },
    }),
  )
  await assertUnarmedReentry(harness({ read: async () => '{' }))
  await assertUnarmedReentry(harness({ read: async () => ({ base64: '' }) }))
})

test('plan exit 20: a turn that starts during the compaction re-enters unarmed', async () => {
  const h: Harness = harness({ compact: async () => (h.run('turn.start', {}), {}) })
  await assertUnarmedReentry(h)
})

test('plan exit 21: a turn that starts during the read re-enters unarmed', async () => {
  const h: Harness = harness({ read: async () => (h.run('turn.start', {}), runFile('plan')) })
  await assertUnarmedReentry(h)
})

test('plan exit 22: a question that opens during the compaction re-enters unarmed', async () => {
  const h: Harness = harness({
    compact: async () => (void h.run('tool.call', { tool: 'AskUserQuestion' }, () => new Promise(() => {})), {}),
  })
  await assertUnarmedReentry(h)
})

test('plan exit 23: a session end during the read stops the re-entry and leaves the ask unarmed', async () => {
  const h: Harness = harness({ read: async () => (h.run('classic.SessionEnd', {}), runFile('plan')) })
  await h.run('session.start', { isInteractive: true })
  h.complete(FINAL)
  await h.fire()
  assert.deepEqual(h.reads, ['a.json'])
  assert.equal(h.calls.runCommand, 0)
  await assertLeftToUser(h)
})

test('plan exit 24: the plan-mode arming expires after five minutes with no turn', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete(PLAN_MARKER)
  await assertAnswered(h)
  await h.fire(EXPIRY_MS)
  await assertLeftToUser(h)
})

test('plan exit 25: a turn started before the expiry stays armed past it and clears at its own end', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete(PLAN_MARKER)
  const timer = h.timers.find((t) => t.ms === EXPIRY_MS)
  assert.ok(timer !== undefined, 'the expiry timer must exist')
  h.run('turn.start', {})
  assert.equal(timer.cancelled, true)
  timer.fn()
  await assertAnswered(h)
  h.complete('The plan is written.')
  await assertLeftToUser(h)
})

test('plan exit 26: the expiry of an older set never clears a newer one', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete(PLAN_MARKER)
  h.complete(PLAN_MARKER)
  const [older, newer] = h.timers.filter((t) => t.ms === EXPIRY_MS)
  assert.ok(older !== undefined && newer !== undefined, 'each set must arm its own timer')
  assert.equal(older.cancelled, true)
  assert.equal(newer.cancelled, false)
  older.fn()
  await assertAnswered(h)
  newer.fn()
  await assertLeftToUser(h)
})

test('plan exit 27: every disarm cancels the expiry timer, and the boundary timer stays apart', async () => {
  for (const name of ['session.start', 'classic.SessionEnd', 'turn.complete']) {
    const h = harness()
    await h.run('session.start', { isInteractive: true })
    h.complete(FINAL)
    h.complete(PLAN_MARKER)
    const boundary = h.timers[FIRST_BOUNDARY]
    const expiry = h.timers.find((t) => t.ms === EXPIRY_MS)
    assert.ok(boundary !== undefined && expiry !== undefined, 'both timers must exist')
    assert.equal(boundary.cancelled, false, 'arming the expiry leaves the boundary timer')
    await assertAnswered(h)
    await h.run(name, { isInteractive: true, reason: 'answer', answer: 'Plain.' })
    assert.equal(expiry.cancelled, true, name)
    if (name !== 'classic.SessionEnd') assert.equal(boundary.cancelled, false, name)
    await assertLeftToUser(h)
  }
})

test('plan exit 28: a re-entry rejected late leaves a newer plan-mode arming in place', async () => {
  let reject: (err: Error) => void = () => {}
  const h = harness({ runCommand: () => new Promise((_, no) => (reject = no)) })
  await armedByBoundary(h)
  await assertAnswered(h)
  h.complete(PLAN_MARKER)
  reject(new Error('late'))
  await flush()
  assert.ok(h.logs.some((l) => l.startsWith('backlog loop: re-entry rejected: late')))
  await assertAnswered(h)
})

test('plan exit 29: an unarmed re-entry never inherits a pending plan-mode arming', async () => {
  const h = harness({ read: async () => runFile('run') })
  await h.run('session.start', { isInteractive: true })
  h.complete(FINAL)
  h.complete(PLAN_MARKER)
  await assertAnswered(h)
  await h.fire(0)
  assert.equal(h.calls.runCommand, 1)
  await assertLeftToUser(h)
  assert.equal(h.timers.find((t) => t.ms === EXPIRY_MS)?.cancelled, true)
})

test('plan exit 30: a session start disarms before its first await, and a later rejection does not undo it', async () => {
  let failing = false
  const h = harness({ list: async () => (failing ? Promise.reject(new Error('no list')) : COMMANDS) })
  await armedByBoundary(h)
  await assertAnswered(h)
  failing = true
  const starting = h.run('session.start', { isInteractive: true }) as Promise<unknown>
  const during = h.ask('ExitPlanMode')
  await assert.rejects(starting, /no list/)
  assert.equal((await during).answer, 'NEXT')
  await assertLeftToUser(h)
})
