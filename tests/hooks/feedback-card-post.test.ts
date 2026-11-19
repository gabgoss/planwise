import { test } from 'node:test'
import assert from 'node:assert/strict'
import type { PressDraft, PressHost, PressRunResult } from '../../plugins/planwise/hooks/feedback/post-press.ts'
import { PYTHON_CANDIDATES } from '../../plugins/planwise/hooks/feedback/names.ts'

// The module under test loads from the environment variable when it is set, so a mutated copy can
// stand in for the real file. With the variable unset the shipped module loads.
const pressModule = process.env.FEEDBACK_POST_PRESS_MODULE ?? '../../plugins/planwise/hooks/feedback/post-press.ts'
const { pressPost, postArgv, KEEP_LINE, EXIT_POSTED, EXIT_KEPT, EXIT_POSTING_OFF } = (await import(pressModule)) as typeof import('../../plugins/planwise/hooks/feedback/post-press.ts')

const ROOT = '/plugin/root'
const draft: PressDraft = { draftId: 'draft-1', configPath: '/proj/planwise.yaml' }

/** One scripted answer for one run call: a result, or an error to reject with. */
type Step = PressRunResult | Error

const ok = (exitCode: number, stdout = '', stderr = ''): PressRunResult => ({ exitCode, stdout, stderr })

type Fake = {
  host: PressHost
  runs: { argv: readonly string[]; init: { timeoutMs?: number } | undefined }[]
  logs: { text: string; to: string }[]
  fallbacks: string[]
  cleared: (string | null)[]
  posting: boolean[]
  asks: unknown[]
}

/** A host that records every call and answers run from a script, one step per call. */
const fake = (steps: Step[], initialPosting = false): Fake => {
  const f: Fake = { host: undefined as unknown as PressHost, runs: [], logs: [], fallbacks: [], cleared: [], posting: [initialPosting], asks: [] }
  let call = 0
  const host = {
    run: async (argv: readonly string[], init?: { timeoutMs?: number }): Promise<PressRunResult> => {
      f.runs.push({ argv, init })
      const step = steps[call++]
      if (step === undefined) throw new Error('script exhausted')
      if (step instanceof Error) throw step
      return step
    },
    uiLog: (text: string, to: 'debug' | 'transcript') => {
      f.logs.push({ text, to })
    },
    fallback: async (draftId: string) => {
      f.fallbacks.push(draftId)
    },
    readPosting: async () => f.posting[f.posting.length - 1] as boolean,
    setPosting: async (value: boolean) => {
      f.posting.push(value)
    },
    clearLast: async (draftId: string | null) => {
      f.cleared.push(draftId)
    },
    pluginRoot: () => ROOT,
    // Not a PressHost member: a press that asked anything would land here.
    ask: async (...args: unknown[]) => {
      f.asks.push(args)
      return undefined
    },
  }
  f.host = host
  return f
}

test('press: a started run calls run once and the fallback never', async () => {
  const f = fake([ok(EXIT_POSTED, 'posted: https://example.test/1\n')])
  await pressPost(f.host, draft)
  assert.equal(f.runs.length, 1)
  assert.equal(f.fallbacks.length, 0)
})

test('press: posting off logs the keep line once, clears the card, asks nothing and runs once', async () => {
  const f = fake([ok(EXIT_POSTING_OFF, '', 'posting is off')])
  await pressPost(f.host, draft)
  assert.equal(f.asks.length, 0)
  assert.deepEqual(f.logs.filter((l) => l.text === KEEP_LINE), [{ text: KEEP_LINE, to: 'transcript' }])
  assert.equal(f.logs.length, 1)
  assert.deepEqual(f.cleared, [draft.draftId])
  assert.equal(f.runs.length, 1)
  assert.equal(f.fallbacks.length, 0)
})

test('press: a press while posting is already true calls nothing', async () => {
  const f = fake([ok(EXIT_POSTED)], true)
  await pressPost(f.host, draft)
  assert.equal(f.runs.length, 0)
  assert.equal(f.fallbacks.length, 0)
  assert.equal(f.logs.length, 0)
  assert.equal(f.cleared.length, 0)
  assert.deepEqual(f.posting, [true])
})

test('press: no interpreter starts, so the fallback runs once and the card is kept', async () => {
  const f = fake(PYTHON_CANDIDATES.map(() => new Error('spawn ENOENT')))
  await pressPost(f.host, draft)
  assert.equal(f.runs.length, PYTHON_CANDIDATES.length)
  assert.deepEqual(f.fallbacks, [draft.draftId])
  assert.equal(f.cleared.length, 0)
  assert.equal(f.logs.length, 1)
  assert.equal(f.logs[0]?.to, 'debug')
  assert.match(f.logs[0]?.text ?? '', /no python could start/)
})

test('press: a posted result clears the card and logs the last stdout line once', async () => {
  const f = fake([ok(EXIT_POSTED, 'working\nposted: https://example.test/1\n\n')])
  await pressPost(f.host, draft)
  assert.deepEqual(f.logs, [{ text: 'posted: https://example.test/1', to: 'transcript' }])
  assert.deepEqual(f.cleared, [draft.draftId])
})

test('press: a posted result with empty stdout logs the default line', async () => {
  const f = fake([ok(EXIT_POSTED)])
  await pressPost(f.host, draft)
  assert.deepEqual(f.logs, [{ text: 'draft feedback: posted', to: 'transcript' }])
})

test('press: a kept result clears the card and logs once', async () => {
  const f = fake([ok(EXIT_KEPT, 'kept: nothing posted\n')])
  await pressPost(f.host, draft)
  assert.deepEqual(f.logs, [{ text: 'kept: nothing posted', to: 'transcript' }])
  assert.deepEqual(f.cleared, [draft.draftId])
})

test('press: a kept result with empty stdout logs the default line', async () => {
  const f = fake([ok(EXIT_KEPT)])
  await pressPost(f.host, draft)
  assert.deepEqual(f.logs, [{ text: 'draft feedback: the draft was kept and nothing was posted', to: 'transcript' }])
})

for (const code of [1, 2, 7]) {
  test('press: exit ' + String(code) + ' keeps the card and logs the last stderr line', async () => {
    const f = fake([ok(code, '', 'first\nboom\n')])
    await pressPost(f.host, draft)
    assert.deepEqual(f.cleared, [])
    assert.deepEqual(f.logs, [{ text: 'draft feedback: post failed (exit ' + String(code) + '); the card stays: boom', to: 'transcript' }])
    assert.equal(f.fallbacks.length, 0)
    assert.equal(f.runs.length, 1)
  })
}

test('press: a failure with empty stderr logs the no-error-text reason', async () => {
  const f = fake([ok(1)])
  await pressPost(f.host, draft)
  assert.match(f.logs[0]?.text ?? '', /the card stays: no error text$/)
})

test('press: a rejected first interpreter tries the next one before falling back', async () => {
  const f = fake([new Error('spawn ENOENT'), ok(EXIT_POSTED, 'posted\n')])
  await pressPost(f.host, draft)
  assert.equal(f.runs.length, 2)
  assert.equal(f.runs[0]?.argv[0], PYTHON_CANDIDATES[0])
  assert.equal(f.runs[1]?.argv[0], PYTHON_CANDIDATES[1])
  assert.equal(f.fallbacks.length, 0)
  assert.deepEqual(f.cleared, [draft.draftId])
})

test('press: a definite result stops the interpreter loop', async () => {
  const f = fake([ok(1, '', 'bad'), ok(EXIT_POSTED)])
  await pressPost(f.host, draft)
  assert.equal(f.runs.length, 1)
})

test('press: a timeout-shaped rejection keeps the card with no next interpreter and no fallback', async () => {
  for (const message of ['process timed out', 'Timeout after 120000ms', 'time-out']) {
    const f = fake([new Error(message), ok(EXIT_POSTED)])
    await pressPost(f.host, draft)
    assert.equal(f.runs.length, 1, message)
    assert.equal(f.fallbacks.length, 0, message)
    assert.equal(f.cleared.length, 0, message)
    assert.deepEqual(f.logs, [{ text: 'draft feedback: post timed out; the card stays: ' + message, to: 'transcript' }], message)
    assert.equal(f.posting[f.posting.length - 1], false, message)
  }
})

test('press: an empty config path runs the fallback once and starts no process', async () => {
  const f = fake([ok(EXIT_POSTED)])
  await pressPost(f.host, { draftId: 'draft-2', configPath: '' })
  assert.equal(f.runs.length, 0)
  assert.deepEqual(f.fallbacks, ['draft-2'])
  assert.equal(f.cleared.length, 0)
  assert.equal(f.posting[f.posting.length - 1], false)
})

test('press: a null draft does nothing', async () => {
  const f = fake([ok(EXIT_POSTED)])
  await pressPost(f.host, null)
  assert.equal(f.runs.length, 0)
  assert.equal(f.fallbacks.length, 0)
  assert.equal(f.logs.length, 0)
  assert.deepEqual(f.posting, [false])
})

test('press: the post call carries the exact argv and a 120000 ms timeout', async () => {
  const f = fake([ok(EXIT_POSTED)])
  await pressPost(f.host, draft)
  assert.deepEqual(f.runs[0]?.argv, [PYTHON_CANDIDATES[0], '-B', ROOT + '/scripts/feedback_post.py', 'post', '--config', '/proj/planwise.yaml', '--draft-id', 'draft-1'])
  assert.deepEqual(f.runs[0]?.init, { timeoutMs: 120000 })
  assert.deepEqual(postArgv('python', ROOT, draft), ['python', '-B', ROOT + '/scripts/feedback_post.py', 'post', '--config', '/proj/planwise.yaml', '--draft-id', 'draft-1'])
})

test('press: posting turns on before the run and off after it, on every path', async () => {
  const paths: Step[][] = [[ok(EXIT_POSTED)], [ok(1)], [ok(EXIT_POSTING_OFF)], PYTHON_CANDIDATES.map(() => new Error('spawn ENOENT'))]
  for (const steps of paths) {
    const f = fake(steps)
    await pressPost(f.host, draft)
    assert.deepEqual(f.posting, [false, true, false])
  }
})

test('press: posting turns off again when the card clear throws', async () => {
  const f = fake([ok(EXIT_POSTED)])
  f.host.clearLast = async () => {
    throw new Error('clear failed')
  }
  await assert.rejects(pressPost(f.host, draft), /clear failed/)
  assert.deepEqual(f.posting, [false, true, false])
})
