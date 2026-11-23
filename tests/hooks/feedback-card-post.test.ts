import { test } from 'node:test'
import assert from 'node:assert/strict'
import type { PressDraft, PressHost, PressRunResult } from '../../plugins/planwise/hooks/feedback/post-press.ts'
import { PYTHON_CANDIDATES } from '../../plugins/planwise/hooks/feedback/names.ts'

// The module under test loads from the environment variable when it is set, so a mutated copy can
// stand in for the real file. With the variable unset the shipped module loads.
const pressModule = process.env.FEEDBACK_POST_PRESS_MODULE ?? '../../plugins/planwise/hooks/feedback/post-press.ts'
const { pressPost, postArgv, liveConfigPath, KEEP_LINE, MOVED_OFF_LINE, EXIT_POSTED, EXIT_NO_DRAFT, EXIT_KEPT, EXIT_POSTING_OFF } = (await import(pressModule)) as typeof import('../../plugins/planwise/hooks/feedback/post-press.ts')

const ROOT = '/plugin/root'
const draft: PressDraft = { draftId: 'draft-1', configPath: '/proj/planwise.yaml' }

// A draft written inside a git worktree. Its stored config path dies when the worktree is removed.
const MAIN_CONFIG = 'C:/work/main/planwise/config.yaml'
const WORKTREE_CONFIG = 'C:/work/main/.claude/worktrees/wt/planwise/config.yaml'
const worktreeDraft: PressDraft = { draftId: 'draft-wt', configPath: WORKTREE_CONFIG }

// The stderr line of `feedback_post.py post` on exit 2, copied from the script's own print call.
const NO_DRAFT_LINE = 'feedback_post: no queued draft with id draft-1 (promoted); nothing was posted.'
// The stderr line of the same script on exit 1 when its --config file does not exist.
const GONE_LINE = 'feedback_post: config.yaml not found at ' + WORKTREE_CONFIG

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
  /** One entry for each time the press asked for the current root's config: the value it got. */
  currentCalls: string[]
}

/**
 * A host that records every call and answers run from a script, one step per call. The current
 * root holds no config unless a test replaces that member.
 */
const fake = (steps: Step[], initialPosting = false): Fake => {
  const f: Fake = { host: undefined as unknown as PressHost, runs: [], logs: [], fallbacks: [], cleared: [], posting: [initialPosting], asks: [], currentCalls: [] }
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
    currentConfig: async (): Promise<string> => {
      f.currentCalls.push('')
      return ''
    },
    // Not a PressHost member: a press that asked anything would land here.
    ask: async (...args: unknown[]) => {
      f.asks.push(args)
      return undefined
    },
  }
  f.host = host
  return f
}

/** The script's answer when the draft's config file is gone: exit 1 and the not-found line. */
const GONE = ok(1, '', GONE_LINE + '\n')

/**
 * A fake whose first run reports the draft's config as gone, and whose current root holds
 * `current` ('' for none). `later` scripts the runs after the first.
 */
const moved = (later: Step[], current: string): Fake => {
  const f = fake([GONE, ...later])
  f.host.currentConfig = async () => {
    f.currentCalls.push(current)
    return current
  }
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

// Exit 2 stays in this loop: with any other stderr it is a usage error, and the card stays.
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

test('press: exit 2 for a draft that is no longer queued clears the card and logs once', async () => {
  const f = fake([ok(EXIT_NO_DRAFT, '', NO_DRAFT_LINE + '\n')])
  await pressPost(f.host, draft)
  assert.deepEqual(f.cleared, [draft.draftId])
  assert.deepEqual(f.logs, [{ text: 'draft feedback: nothing to post; the card is cleared: ' + NO_DRAFT_LINE, to: 'transcript' }])
  assert.equal(f.fallbacks.length, 0)
  assert.equal(f.runs.length, 1)
})

test('press: the no-longer-queued words on another exit code keep the card', async () => {
  const f = fake([ok(1, '', NO_DRAFT_LINE + '\n')])
  await pressPost(f.host, draft)
  assert.deepEqual(f.cleared, [])
  assert.deepEqual(f.logs, [{ text: 'draft feedback: post failed (exit 1); the card stays: ' + NO_DRAFT_LINE, to: 'transcript' }])
})

const SWITCH_LOG = { text: "draft feedback: the draft's config file is gone; posting with " + MAIN_CONFIG, to: 'transcript' }

test('press: a stored config in a removed worktree posts with the current root config and says so', async () => {
  const f = moved([ok(EXIT_POSTED, 'posted: https://example.test/2\n')], MAIN_CONFIG)
  await pressPost(f.host, worktreeDraft)
  assert.deepEqual(f.currentCalls, [MAIN_CONFIG])
  assert.equal(f.runs.length, 2)
  assert.equal(f.runs[0]?.argv[5], WORKTREE_CONFIG)
  assert.deepEqual(f.runs[1]?.argv, [PYTHON_CANDIDATES[0], '-B', ROOT + '/scripts/feedback_post.py', 'post', '--config', MAIN_CONFIG, '--draft-id', 'draft-wt'])
  assert.deepEqual(f.logs, [SWITCH_LOG, { text: 'posted: https://example.test/2', to: 'transcript' }])
  assert.deepEqual(f.cleared, ['draft-wt'])
  assert.equal(f.fallbacks.length, 0)
})

test('press: a removed worktree whose draft is gone too clears the card', async () => {
  const f = moved([ok(EXIT_NO_DRAFT, '', 'feedback_post: no queued draft with id draft-wt (unknown); nothing was posted.\n')], MAIN_CONFIG)
  await pressPost(f.host, worktreeDraft)
  assert.equal(f.runs[1]?.argv[5], MAIN_CONFIG)
  assert.deepEqual(f.cleared, ['draft-wt'])
})

test('press: a stored config that works is used unchanged and the current root is never read', async () => {
  const f = fake([ok(EXIT_POSTED)])
  await pressPost(f.host, worktreeDraft)
  assert.deepEqual(f.currentCalls, [])
  assert.equal(f.runs.length, 1)
  assert.equal(f.runs[0]?.argv[5], WORKTREE_CONFIG)
})

test('press: any other exit 1 never reads the current root', async () => {
  const f = fake([ok(1, '', 'feedback_post: the draft could not be promoted: boom\n')])
  await pressPost(f.host, worktreeDraft)
  assert.deepEqual(f.currentCalls, [])
  assert.equal(f.runs.length, 1)
  assert.deepEqual(f.cleared, [])
})

test('press: a removed config with none under the current root runs the fallback once and no second process', async () => {
  const f = moved([ok(EXIT_POSTED)], '')
  await pressPost(f.host, worktreeDraft)
  assert.deepEqual(f.currentCalls, [''])
  assert.equal(f.runs.length, 1)
  assert.deepEqual(f.fallbacks, ['draft-wt'])
  assert.equal(f.cleared.length, 0)
  assert.equal(f.posting[f.posting.length - 1], false)
})

test('press: a current-root search that throws runs the fallback once, so the card does not stay stuck', async () => {
  const f = moved([ok(EXIT_POSTED)], MAIN_CONFIG)
  f.host.currentConfig = async () => {
    throw new Error('list failed')
  }
  await pressPost(f.host, worktreeDraft)
  assert.equal(f.runs.length, 1)
  assert.deepEqual(f.fallbacks, ['draft-wt'])
  assert.equal(f.logs.filter((l) => l.to === 'transcript').length, 0)
  assert.match(f.logs[0]?.text ?? '', /could not be searched for a config: list failed$/)
})

test('press: a current root that names the same missing config keeps the card and runs once', async () => {
  const f = moved([ok(EXIT_POSTED)], WORKTREE_CONFIG)
  await pressPost(f.host, worktreeDraft)
  assert.equal(f.runs.length, 1)
  assert.equal(f.fallbacks.length, 0)
  assert.deepEqual(f.cleared, [])
  assert.deepEqual(f.logs, [{ text: 'draft feedback: post failed (exit 1); the card stays: ' + GONE_LINE, to: 'transcript' }])
})

test('press: posting off in the current root config logs the moved line, not the keep line', async () => {
  const f = moved([ok(EXIT_POSTING_OFF, 'posting is off\n')], MAIN_CONFIG)
  await pressPost(f.host, worktreeDraft)
  assert.deepEqual(f.logs, [SWITCH_LOG, { text: MOVED_OFF_LINE, to: 'transcript' }])
  assert.equal(MOVED_OFF_LINE.includes('saved'), false)
  assert.deepEqual(f.cleared, ['draft-wt'])
})

test('press: a timeout on the second run keeps the card with no fallback', async () => {
  const f = moved([new Error('process timed out')], MAIN_CONFIG)
  await pressPost(f.host, worktreeDraft)
  assert.equal(f.runs.length, 2)
  assert.equal(f.fallbacks.length, 0)
  assert.deepEqual(f.cleared, [])
  assert.deepEqual(f.logs, [SWITCH_LOG, { text: 'draft feedback: post timed out; the card stays: process timed out', to: 'transcript' }])
})

/** A host for liveConfigPath: `present` answers exists, and `current` answers the root search. An Error throws. */
const liveHost = (present: boolean | Error, current: string | Error) => {
  const calls: string[] = []
  return {
    calls,
    exists: async (path: string): Promise<boolean> => {
      calls.push('exists ' + path)
      if (present instanceof Error) throw present
      return present
    },
    currentConfig: async (): Promise<string> => {
      calls.push('current')
      if (current instanceof Error) throw current
      return current
    },
  }
}

test('liveConfigPath: a stored path whose file exists wins and the root is never searched', async () => {
  const host = liveHost(true, MAIN_CONFIG)
  assert.equal(await liveConfigPath(host, WORKTREE_CONFIG), WORKTREE_CONFIG)
  assert.deepEqual(host.calls, ['exists ' + WORKTREE_CONFIG])
})

test('liveConfigPath: a stored path whose file is gone gives the current root config', async () => {
  assert.equal(await liveConfigPath(liveHost(false, MAIN_CONFIG), WORKTREE_CONFIG), MAIN_CONFIG)
  assert.equal(await liveConfigPath(liveHost(false, ''), WORKTREE_CONFIG), '')
})

test('liveConfigPath: an empty stored path searches the root without an existence check', async () => {
  const host = liveHost(true, MAIN_CONFIG)
  assert.equal(await liveConfigPath(host, ''), MAIN_CONFIG)
  assert.deepEqual(host.calls, ['current'])
})

test('liveConfigPath: an existence check that throws keeps the stored path', async () => {
  assert.equal(await liveConfigPath(liveHost(new Error('fs down'), MAIN_CONFIG), WORKTREE_CONFIG), WORKTREE_CONFIG)
})

test('liveConfigPath: a root search that throws gives an empty path, never the dead one', async () => {
  assert.equal(await liveConfigPath(liveHost(false, new Error('list failed')), WORKTREE_CONFIG), '')
})

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
