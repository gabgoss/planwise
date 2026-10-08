import { test } from 'node:test'
import assert from 'node:assert/strict'
import { failureText, isCurrent, keyOf, releaseLatch, stepOf } from '../../plugins/planwise/hooks/loop/boundary.ts'

// The module under test. REGISTER_URL points the same tests at another copy of register.ts.
const target = process.env.REGISTER_URL ?? new URL('../../plugins/planwise/hooks/register.ts', import.meta.url).href
const { register } = await import(target)

const MARKER = 'BACKLOG LOOP: run=r1 done=5 remaining=2 state=a.json'
const MARKER_B = 'BACKLOG LOOP: run=r1 done=6 remaining=1 state=a.json'
const COMMANDS = [{ name: 'planwise:planwise', source: 'skill', plugin: 'planwise' }]

const flush = async () => {
  for (let i = 0; i < 10; i++) await new Promise((resolve) => setImmediate(resolve))
}

/** Registers the module against a fake engine: captured hooks, a manual clock, recorded calls. */
const harness = (opts: { compact?: () => Promise<{ skip?: string }>; runCommand?: () => Promise<unknown> } = {}) => {
  const hooks = new Map<string, { run: (...a: unknown[]) => unknown; catcher?: (...a: unknown[]) => unknown }>()
  const on = (name: string, run: (...a: unknown[]) => unknown) => {
    const rec: { run: (...a: unknown[]) => unknown; catcher?: (...a: unknown[]) => unknown } = { run }
    hooks.set(name, rec)
    return { catch: (c: (...a: unknown[]) => unknown) => void (rec.catcher = c) }
  }
  const logs: string[] = []
  const calls = { compact: 0, runCommand: 0 }
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
    command: { run: () => (calls.runCommand++, (opts.runCommand ?? (async () => ({})))()), list: async () => COMMANDS },
    ui: { log: (text: string) => void logs.push(text) },
    env: { get: async () => '1' },
  }
  register(on, {})
  const run = (name: string, e: Record<string, unknown>, next: (e: unknown) => unknown = (x) => x) => hooks.get(name)!.run($, e, next)
  const caught = (name: string, error: unknown, called: boolean, replay: unknown = 'replayed') => {
    const next = Object.assign(() => replay, { error, called })
    return hooks.get(name)!.catcher!($, {}, next)
  }
  const complete = (answer: string) => run('turn.complete', { reason: 'answer', answer })
  const fire = async () => {
    for (const t of timers.filter((x) => !x.cancelled && !x.fired)) {
      t.fired = true
      t.fn()
    }
    await flush()
  }
  return { run, caught, complete, fire, logs, calls, timers }
}

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

test('finding 5: a newer marker cancels the pending boundary, so only one re-entry happens', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete(MARKER)
  h.complete(MARKER_B)
  assert.equal(h.timers[0]?.cancelled, true)
  h.timers[0]?.fn()
  await h.fire()
  assert.equal(h.calls.compact, 1)
  assert.equal(h.calls.runCommand, 1)
})

test('finding 5: a session end invalidates a pending boundary', async () => {
  const h = harness()
  await h.run('session.start', { isInteractive: true })
  h.complete(MARKER)
  h.run('classic.SessionEnd', {})
  h.timers[0]?.fn()
  await flush()
  assert.equal(h.calls.compact, 0)
})

test('finding 6: a catch handler whose hook already called next replays next(e)', () => {
  const h = harness()
  for (const name of ['session.start', 'turn.start', 'tool.call', 'turn.complete', 'classic.SessionEnd']) {
    assert.equal(h.caught(name, { kind: 'timeout', budget: 1 }, true), 'replayed', name)
  }
})
