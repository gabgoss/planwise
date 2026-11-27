import { test } from 'node:test'
import assert from 'node:assert/strict'
import type { BannerProps, BlockedHost, BlockedRunResult, BlockedState } from '../../plugins/planwise/hooks/feedback/blocked.ts'
import { PYTHON_CANDIDATES } from '../../plugins/planwise/hooks/feedback/names.ts'

// The module under test loads from the environment variable when it is set, so a mutated copy can
// stand in for the real file. With the variable unset the shipped module loads.
const blockedModule = process.env.FEEDBACK_BLOCKED_MODULE ?? '../../plugins/planwise/hooks/feedback/blocked.ts'
const { bannerText, BANNER_PREFIX, blockedListArgv, dismissBlockedArgv, parseBlockedCount, shouldShowBanner, recountBlocked, pressDismiss } = (await import(blockedModule)) as typeof import('../../plugins/planwise/hooks/feedback/blocked.ts')

const ROOT = '/plugin/root'
const DIR = '/proj/planwise/feedback'

/** One scripted answer for one run call: a result, or an error to reject with. */
type Step = BlockedRunResult | Error

const ok = (exitCode: number, stdout = '', stderr = ''): BlockedRunResult => ({ exitCode, stdout, stderr })

type Fake = {
  host: BlockedHost
  runs: { argv: readonly string[]; init: { timeoutMs?: number } | undefined }[]
  logs: { text: string; to: string }[]
  stored: BlockedState[]
}

/** A host that records every call and answers run from a script, one step per call. */
const fake = (steps: Step[]): Fake => {
  const f: Fake = { host: undefined as unknown as BlockedHost, runs: [], logs: [], stored: [] }
  let call = 0
  f.host = {
    run: async (argv, init) => {
      f.runs.push({ argv, init })
      const step = steps[call++]
      if (step === undefined) throw new Error('script exhausted')
      if (step instanceof Error) throw step
      return step
    },
    uiLog: (text, to) => {
      f.logs.push({ text, to })
    },
    pluginRoot: () => ROOT,
    exists: async () => true,
    setBlocked: (state) => {
      f.stored.push(state)
    },
  }
  return f
}

/** A run that stays open until the test answers it. */
const held = (): { run: () => Promise<BlockedRunResult>; answer: (result: BlockedRunResult) => void } => {
  let answer: (result: BlockedRunResult) => void = () => {}
  const result = new Promise<BlockedRunResult>((resolve) => (answer = resolve))
  return { run: () => result, answer: (value) => answer(value) }
}

const tick = (): Promise<void> => new Promise((resolve) => setImmediate(resolve))

test('recount: a drafts folder that does not exist runs nothing and stores a count of 0', async () => {
  const f = fake([])
  f.host.exists = async () => false
  await recountBlocked(f.host, DIR)
  assert.equal(f.runs.length, 0)
  assert.deepEqual(f.stored, [{ count: 0, feedbackDir: DIR }])
  assert.equal(f.logs.length, 0)
})

test('recount: an older count that returns after a newer one is dropped', async () => {
  const slow = held()
  const older = fake([])
  older.host.run = slow.run
  const first = recountBlocked(older.host, DIR)
  await tick()
  const newer = fake([ok(0, '[]')])
  await recountBlocked(newer.host, DIR)
  slow.answer(ok(0, '[{"draft": "a"}]'))
  await first
  assert.deepEqual(newer.stored, [{ count: 0, feedbackDir: DIR }])
  assert.deepEqual(older.stored, [])
})

test('recount: a count that started before a successful dismiss never brings the banner back', async () => {
  const slow = held()
  const counting = fake([])
  counting.host.run = slow.run
  const pending = recountBlocked(counting.host, DIR)
  await tick()
  const dismissing = fake([ok(0, 'dismissed 1 blocked draft(s)\n')])
  await pressDismiss(dismissing.host, DIR)
  slow.answer(ok(0, '[{"draft": "a"}]'))
  await pending
  assert.deepEqual(counting.stored, [])
})

const props: BannerProps = { hasSurvey: false, isWorking: false, maxRows: 24, bodyColumns: 80 }
const some: BlockedState = { count: 2, feedbackDir: DIR }

test('banner text: the prefix, the count and the word draft(s)', () => {
  assert.equal(bannerText(2), 'Feedback post blocked by the privacy check: 2 draft(s)')
  assert.equal(bannerText(1), 'Feedback post blocked by the privacy check: 1 draft(s)')
  assert.equal(BANNER_PREFIX + '7 draft(s)', bannerText(7))
})

test('hidden state: the banner is hidden at count 0 and on a null state', () => {
  assert.equal(shouldShowBanner({ count: 0, feedbackDir: DIR }, props), false)
  assert.equal(shouldShowBanner(null, props), false)
})

test('shown state: the banner shows at count 1 or more in a roomy frame', () => {
  assert.equal(shouldShowBanner(some, props), true)
  assert.equal(shouldShowBanner({ count: 1, feedbackDir: DIR }, props), true)
})

test('hidden state: a survey, a working turn or too little room hides the banner', () => {
  assert.equal(shouldShowBanner(some, { ...props, hasSurvey: true }), false)
  assert.equal(shouldShowBanner(some, { ...props, isWorking: true }), false)
  assert.equal(shouldShowBanner(some, { ...props, maxRows: 3 }), false)
  assert.equal(shouldShowBanner(some, { ...props, maxRows: 4 }), true)
  assert.equal(shouldShowBanner(some, { ...props, bodyColumns: 33 }), false)
  assert.equal(shouldShowBanner(some, { ...props, bodyColumns: 34 }), true)
})

test('argv: both argvs carry --feedback-dir and its value last', () => {
  assert.deepEqual(blockedListArgv('python', ROOT, DIR), ['python', '-B', ROOT + '/scripts/feedback_drafts.py', 'blocked-list', '--json', '--feedback-dir', DIR])
  assert.deepEqual(dismissBlockedArgv('python', ROOT, DIR), ['python', '-B', ROOT + '/scripts/feedback_drafts.py', 'dismiss-blocked', '--all', '--feedback-dir', DIR])
  for (const argv of [blockedListArgv('python', ROOT, DIR), dismissBlockedArgv('python', ROOT, DIR)]) {
    assert.equal(argv[argv.length - 2], '--feedback-dir')
    assert.equal(argv[argv.length - 1], DIR)
  }
})

test('parseBlockedCount: the array length, and null for text that is not an array', () => {
  assert.equal(parseBlockedCount('[]'), 0)
  assert.equal(parseBlockedCount('[\n  {"draft": "a"},\n  {"draft": "b"}\n]\n'), 2)
  assert.equal(parseBlockedCount('{"draft": "a"}'), null)
  assert.equal(parseBlockedCount('no blocked drafts'), null)
  assert.equal(parseBlockedCount(''), null)
})

test('recount: an empty directory runs nothing and stores nothing', async () => {
  const f = fake([ok(0, '[]')])
  await recountBlocked(f.host, '')
  assert.equal(f.runs.length, 0)
  assert.deepEqual(f.stored, [])
  assert.equal(f.logs.length, 0)
})

test('recount: a count from a run is stored with its directory, after one call with a 30000 ms timeout', async () => {
  const f = fake([ok(0, '[{"draft": "a"}, {"draft": "b"}]')])
  await recountBlocked(f.host, DIR)
  assert.equal(f.runs.length, 1)
  assert.deepEqual(f.runs[0]?.argv, blockedListArgv(PYTHON_CANDIDATES[0], ROOT, DIR))
  assert.deepEqual(f.runs[0]?.init, { timeoutMs: 30000 })
  assert.deepEqual(f.stored, [{ count: 2, feedbackDir: DIR }])
  assert.equal(f.logs.length, 0)
})

test('recount: a count of 0 is stored, so a banner can go away', async () => {
  const f = fake([ok(0, '[]')])
  await recountBlocked(f.host, DIR)
  assert.deepEqual(f.stored, [{ count: 0, feedbackDir: DIR }])
})

test('recount: a non-zero exit stores nothing and logs the last stderr line to debug', async () => {
  const f = fake([ok(1, '', 'first\nboom\n')])
  await recountBlocked(f.host, DIR)
  assert.deepEqual(f.stored, [])
  assert.deepEqual(f.logs, [{ text: 'draft feedback: blocked-list exited 1: boom', to: 'debug' }])
})

test('recount: output that is not a JSON array stores nothing and logs to debug', async () => {
  for (const stdout of ['no blocked drafts\n', '{"draft": "a"}', '']) {
    const f = fake([ok(0, stdout)])
    await recountBlocked(f.host, DIR)
    assert.deepEqual(f.stored, [], stdout)
    assert.deepEqual(f.logs, [{ text: 'draft feedback: blocked-list printed no JSON array', to: 'debug' }], stdout)
  }
})

test('recount: a python that cannot start hands over to the next name', async () => {
  const f = fake([new Error('spawn ENOENT'), ok(0, '[{"draft": "a"}]')])
  await recountBlocked(f.host, DIR)
  assert.equal(f.runs.length, 2)
  assert.equal(f.runs[0]?.argv[0], PYTHON_CANDIDATES[0])
  assert.equal(f.runs[1]?.argv[0], PYTHON_CANDIDATES[1])
  assert.deepEqual(f.stored, [{ count: 1, feedbackDir: DIR }])
  assert.equal(f.logs.length, 0)
})

test('recount: no python that starts stores nothing and logs one debug line', async () => {
  const f = fake(PYTHON_CANDIDATES.map(() => new Error('spawn ENOENT')))
  await recountBlocked(f.host, DIR)
  assert.equal(f.runs.length, PYTHON_CANDIDATES.length)
  assert.deepEqual(f.stored, [])
  assert.equal(f.logs.length, 1)
  assert.equal(f.logs[0]?.to, 'debug')
  assert.match(f.logs[0]?.text ?? '', /no python could start for the blocked-draft banner: spawn ENOENT$/)
})

test('recount: a store that throws is logged to debug and never escapes', async () => {
  const f = fake([ok(0, '[]')])
  f.host.setBlocked = () => {
    throw new Error('store failed')
  }
  await recountBlocked(f.host, DIR)
  assert.deepEqual(f.logs, [{ text: 'draft feedback: the blocked-draft recount failed: store failed', to: 'debug' }])
})

test('dismiss: an empty directory runs nothing', async () => {
  const f = fake([ok(0, 'dismissed 2 blocked draft(s)\n')])
  await pressDismiss(f.host, '')
  assert.equal(f.runs.length, 0)
  assert.deepEqual(f.stored, [])
})

test('dismiss: exit 0 sets the count to 0 and logs the last stdout line to the transcript', async () => {
  const f = fake([ok(0, 'working\ndismissed 2 blocked draft(s)\n\n')])
  await pressDismiss(f.host, DIR)
  assert.equal(f.runs.length, 1)
  assert.deepEqual(f.runs[0]?.argv, dismissBlockedArgv(PYTHON_CANDIDATES[0], ROOT, DIR))
  assert.deepEqual(f.runs[0]?.init, { timeoutMs: 30000 })
  assert.deepEqual(f.stored, [{ count: 0, feedbackDir: DIR }])
  assert.deepEqual(f.logs, [{ text: 'dismissed 2 blocked draft(s)', to: 'transcript' }])
})

test('dismiss: exit 0 with empty stdout logs the default line', async () => {
  const f = fake([ok(0)])
  await pressDismiss(f.host, DIR)
  assert.deepEqual(f.logs, [{ text: 'draft feedback: blocked drafts dismissed', to: 'transcript' }])
})

test('dismiss: a non-zero exit keeps the count and logs the last stderr line to the transcript', async () => {
  const f = fake([ok(1, '', 'first\nboom\n')])
  await pressDismiss(f.host, DIR)
  assert.deepEqual(f.stored, [])
  assert.deepEqual(f.logs, [{ text: 'draft feedback: dismiss failed (exit 1); the banner stays: boom', to: 'transcript' }])
})

test('dismiss: a python that cannot start hands over to the next name, and none at all logs one debug line', async () => {
  const next = fake([new Error('spawn ENOENT'), ok(0, 'dismissed 1 blocked draft(s)\n')])
  await pressDismiss(next.host, DIR)
  assert.equal(next.runs[1]?.argv[0], PYTHON_CANDIDATES[1])
  assert.deepEqual(next.stored, [{ count: 0, feedbackDir: DIR }])

  const none = fake(PYTHON_CANDIDATES.map(() => new Error('spawn ENOENT')))
  await pressDismiss(none.host, DIR)
  assert.deepEqual(none.stored, [])
  assert.equal(none.logs.length, 1)
  assert.equal(none.logs[0]?.to, 'debug')
})
