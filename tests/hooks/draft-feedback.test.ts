import { test } from 'node:test'
import assert from 'node:assert/strict'
import { register as registerLoader } from 'node:module'
import { NOTICE_TEXT, relativeDraftPath } from '../../plugins/planwise/hooks/feedback/names.ts'

// draft-feedback.ts value-imports the engine's `claude-code` module, which has no node runtime.
// This loader hook resolves it to a stub, the way register-logic.test.ts does.
const stubUrl = (source: string): string => 'data:text/javascript,' + encodeURIComponent(source)
const loaderSource = `
const stubs = {
  'claude-code': ${JSON.stringify(stubUrl('export const update = async () => undefined'))},
}
export async function resolve(specifier, context, next) {
  if (specifier === 'claude-code') return { url: stubs['claude-code'], shortCircuit: true }
  return next(specifier, context)
}
`
registerLoader(stubUrl(loaderSource), import.meta.url)

// The module under test. DRAFT_FEEDBACK_URL points the same tests at another copy of the module.
const target = process.env.DRAFT_FEEDBACK_URL ?? new URL('../../plugins/planwise/hooks/draft-feedback.ts', import.meta.url).href
const { hostOf, onSessionStart, register } = await import(target)

const MAIN = 'C:/work/main'
const WORKTREE = 'C:/work/main/.claude/worktrees/wt'
const NOTIFY = 'project:\n  name: demo\nfeedback:\n  drafts: notify\n'
const OFF = 'project:\n  name: demo\nfeedback:\n  drafts: off\n'
const INPUT = { kind: 'bug', title: 'Root follows the session', what_happened: 'a', what_expected: 'b', steps: 'c' }

type Hook = (engine: unknown, event: unknown, next: unknown) => Promise<unknown>

/** A fake engine over in-memory files. `state.root` is what `$.session.root()` reports on each call. */
const world = (files: Record<string, string>) => {
  const store = new Map(Object.entries(files))
  const writes: string[] = []
  const runs: (readonly string[])[] = []
  const logs: { text: string; to: string }[] = []
  const drafts: unknown[] = []
  const state = { root: MAIN }
  const engine = {
    session: {
      root: async () => state.root,
      id: async () => 'sess-1',
      model: async () => 'model-x',
      version: async () => ({ version: '2.1.0' }),
    },
    plugin: { root: 'C:/plugins/planwise' },
    env: { get: async () => 'Windows_NT' },
    fs: {
      read: async (path: string) => store.get(path),
      write: async (path: string, text: string) => {
        store.set(path, text)
        writes.push(path)
      },
      list: async () => [],
      exists: async (path: string) => store.has(path),
    },
    tool: { register: async () => undefined, check: async () => ({ decision: 'allow' }) },
    ui: { log: (text: string, init: { to: string }) => void logs.push({ text, to: init.to }) },
    process: {
      run: async (argv: readonly string[]) => {
        runs.push(argv)
        return { exitCode: 0, stderr: '' }
      },
    },
    state: {
      get: async () => ({ value: drafts.length > 0 ? drafts[drafts.length - 1] : null }),
      set: async (_ref: unknown, draft: unknown) => void drafts.push(draft),
    },
  }
  return { engine, state, writes, runs, logs, drafts }
}

/** Registers the module against a fake `on` and returns the one tool.call hook it adds. */
const capture = (): Hook => {
  let hook: Hook | undefined
  const on = (_name: string, _match: unknown, run: Hook) => {
    hook = run
    return { catch: () => undefined }
  }
  register(on as never, {} as never)
  assert.ok(hook !== undefined)
  return hook
}

const call = (hook: Hook, engine: unknown) => hook(engine, { tool: 'mcp__planwise__draft_feedback', ...INPUT }, () => undefined)

test('draftfeedback control: a call from the session-start root writes under that root', async () => {
  const w = world({ [MAIN + '/planwise/config.yaml']: NOTIFY })
  await onSessionStart(hostOf(w.engine as never))
  const out = (await call(capture(), w.engine)) as { result: string }
  assert.equal(typeof out.result, 'string')
  assert.equal(w.writes.length, 1)
  assert.ok(w.writes[0]!.startsWith(MAIN + '/planwise/Feedback/Feedback-Drafts/'))
})

test('draftfeedback a root that moves after session start moves the draft, the card and the notice', async () => {
  const w = world({ [MAIN + '/planwise/config.yaml']: NOTIFY, [WORKTREE + '/planwise/config.yaml']: NOTIFY })
  await onSessionStart(hostOf(w.engine as never))
  w.state.root = WORKTREE
  const out = (await call(capture(), w.engine)) as { result: string }
  assert.equal(typeof out.result, 'string')

  const dir = WORKTREE + '/planwise/Feedback/Feedback-Drafts'
  assert.equal(w.writes.length, 1)
  assert.ok(w.writes[0]!.startsWith(dir + '/'), w.writes[0])

  assert.equal(w.runs.length, 1)
  const argv = w.runs[0]!
  assert.equal(argv[argv.indexOf('--feedback-dir') + 1], dir)
  assert.equal(argv[argv.indexOf('admit') + 1], w.writes[0])

  assert.equal(w.drafts.length, 1)
  const draft = w.drafts[0] as { feedbackDir: string; configPath: string }
  assert.equal(draft.feedbackDir, dir)
  assert.equal(draft.configPath, WORKTREE + '/planwise/config.yaml')

  const notice = w.logs.find((line) => line.to === 'transcript')
  assert.equal(notice?.text, NOTICE_TEXT(relativeDraftPath(WORKTREE, w.writes[0]!)))
})

test('draftfeedback a worktree config that turns drafting off denies the call and writes nothing', async () => {
  const w = world({ [MAIN + '/planwise/config.yaml']: NOTIFY, [WORKTREE + '/planwise/config.yaml']: OFF })
  await onSessionStart(hostOf(w.engine as never))
  w.state.root = WORKTREE
  const out = (await call(capture(), w.engine)) as { deny: string }
  assert.match(out.deny, /the tool is not active in this session/)
  assert.equal(w.writes.length, 0)
  assert.equal(w.runs.length, 0)
})

test('draftfeedback a root that moves to a tree with no config denies the call', async () => {
  const w = world({ [MAIN + '/planwise/config.yaml']: NOTIFY })
  await onSessionStart(hostOf(w.engine as never))
  w.state.root = 'C:/work/elsewhere'
  const out = (await call(capture(), w.engine)) as { deny: string }
  assert.match(out.deny, /the tool is not active in this session/)
  assert.equal(w.writes.length, 0)
})
