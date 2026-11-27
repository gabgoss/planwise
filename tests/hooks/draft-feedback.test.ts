import { test } from 'node:test'
import assert from 'node:assert/strict'
import { register as registerLoader } from 'node:module'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
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
      // A folder exists when a file sits under it, and lists the files directly in it.
      list: async (path: string) =>
        [...store.keys()]
          .filter((key) => key.startsWith(path + '/') && !key.slice(path.length + 1).includes('/'))
          .map((key) => ({ name: key.slice(path.length + 1), kind: 'file' })),
      exists: async (path: string) => store.has(path) || [...store.keys()].some((key) => key.startsWith(path + '/')),
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

/** The same fake engine with its file calls on the real file system, for a real git worktree. */
const realWorld = (root: string) => {
  const w = world({})
  w.state.root = root
  w.engine.fs = {
    read: async (path: string) => readFileSync(path, 'utf8'),
    write: async (path: string, text: string) => {
      mkdirSync(dirname(path), { recursive: true })
      writeFileSync(path, text)
      w.writes.push(path)
    },
    list: async (path: string) => readdirSync(path, { withFileTypes: true }).map((entry) => ({ name: entry.name, kind: entry.isDirectory() ? 'dir' : 'file' })),
    exists: async (path: string) => existsSync(path),
  }
  return w
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

test('draftfeedback a call made while another call re-resolves the root never uses a half-set record', async () => {
  const w = world({ [MAIN + '/planwise/config.yaml']: NOTIFY })
  w.state.root = 'C:/work/elsewhere'
  await onSessionStart(hostOf(w.engine as never))
  w.state.root = MAIN
  const hook = capture()
  // Hold the first lookup of a .git folder, so the first call stops in the middle of resolution.
  const exists = w.engine.fs.exists
  let release = () => {}
  let held = () => {}
  const reached = new Promise<void>((resolve) => (held = resolve))
  let holding = false
  w.engine.fs.exists = async (path: string) => {
    if (!holding && path.endsWith('/.git/HEAD')) {
      holding = true
      held()
      await new Promise<void>((resolve) => (release = resolve))
    }
    return exists(path)
  }
  const first = call(hook, w.engine)
  await reached
  await call(hook, w.engine)
  release()
  await first
  assert.equal(w.writes.length, 2)
  for (const path of w.writes) assert.ok(path.startsWith(MAIN + '/planwise/Feedback/Feedback-Drafts/'), path)
})

test('draftfeedback a root that moves to a tree with no config denies the call', async () => {
  const w = world({ [MAIN + '/planwise/config.yaml']: NOTIFY })
  await onSessionStart(hostOf(w.engine as never))
  w.state.root = 'C:/work/elsewhere'
  const out = (await call(capture(), w.engine)) as { deny: string }
  assert.match(out.deny, /the tool is not active in this session/)
  assert.equal(w.writes.length, 0)
})

// A draft file as the producer wrote it on CLI 2.1.330 (the update banner smoke, row 7), copied
// unedited. Its name and id are reused below.
const REAL_DRAFT = `---
draft_id: "f10a0cb0-a791-4119-b14d-f8c886f9e02a"
created_at: "2026-11-22T03:31:30.676Z"
drafted_by: "model"
producer: "hooks-tool"
trigger: "model_judgment"
kind: "idea"
title: "Add a hello world example to planwise"
subcommand: "not command-specific"
source_session_id: "535d4631-5374-49b3-9e4b-964887421207"
plugin_version: "9.9.0"
cli_version: "2.1.330"
model: "claude-fable-5-2"
os: "windows"
status: "queued"
---

### What I learned

Provide a minimal "hello world" plan: a one-sprint, one-session, one-task example that a new user can build and run end to end to see how planwise works.

### Why it matters

A tiny working example lowers the barrier to entry and lets users verify their setup before authoring a real plan.

### Where it would apply

Getting-started documentation and example plans (e.g. a sample build spec and bodies file for build_plan).

### Environment

- plugin version: 9.9.0
- Claude Code version: 2.1.330
- model: claude-fable-5-2
- os: windows
`
const DRAFTS = MAIN + '/planwise/Feedback/Feedback-Drafts'
const REAL_NAME = '2026-11-22-draft-idea-add-a-hello-world-example-to-planwise.md'

test('draftfeedback session start offers a queued draft an earlier session wrote', async () => {
  const w = world({ [MAIN + '/planwise/config.yaml']: NOTIFY, [DRAFTS + '/' + REAL_NAME]: REAL_DRAFT })
  await onSessionStart(hostOf(w.engine as never))
  assert.equal(w.drafts.length, 1)
  const draft = w.drafts[0] as { draftId: string; kind: string; title: string; preview: string; feedbackDir: string; sessionId: string; configPath: string }
  assert.equal(draft.draftId, 'f10a0cb0-a791-4119-b14d-f8c886f9e02a')
  assert.equal(draft.kind, 'idea')
  assert.equal(draft.title, 'Add a hello world example to planwise')
  assert.ok(draft.preview.startsWith('Provide a minimal "hello world" plan'), draft.preview)
  assert.equal(draft.feedbackDir, DRAFTS)
  assert.equal(draft.sessionId, '535d4631-5374-49b3-9e4b-964887421207')
  assert.equal(draft.configPath, MAIN + '/planwise/config.yaml')
  assert.equal(w.writes.length, 0)
  assert.equal(w.runs.length, 0)
})

test('draftfeedback session start skips a draft that is no longer queued', async () => {
  const posted = REAL_DRAFT.replace('status: "queued"', 'status: "posted"')
  const w = world({ [MAIN + '/planwise/config.yaml']: NOTIFY, [DRAFTS + '/' + REAL_NAME]: posted })
  await onSessionStart(hostOf(w.engine as never))
  assert.equal(w.drafts.length, 0)
})

test('draftfeedback session start offers the newest of two queued drafts', async () => {
  const older = REAL_DRAFT.replace('f10a0cb0-a791-4119-b14d-f8c886f9e02a', 'old-id').replace('2026-11-22T03:31:30.676Z', '2026-11-20T09:00:00.000Z')
  const w = world({
    [MAIN + '/planwise/config.yaml']: NOTIFY,
    [DRAFTS + '/2026-11-20-draft-idea-older.md']: older,
    [DRAFTS + '/' + REAL_NAME]: REAL_DRAFT,
  })
  await onSessionStart(hostOf(w.engine as never))
  assert.equal(w.drafts.length, 1)
  assert.equal((w.drafts[0] as { draftId: string }).draftId, 'f10a0cb0-a791-4119-b14d-f8c886f9e02a')
})

test('draftfeedback session start leaves a draft already on the card in place', async () => {
  const w = world({ [MAIN + '/planwise/config.yaml']: NOTIFY, [DRAFTS + '/' + REAL_NAME]: REAL_DRAFT })
  w.drafts.push({ draftId: 'already-there' })
  await onSessionStart(hostOf(w.engine as never))
  assert.equal(w.drafts.length, 1)
  assert.equal((w.drafts[0] as { draftId: string }).draftId, 'already-there')
})

test('draftfeedback session start offers nothing when drafting is off', async () => {
  const w = world({ [MAIN + '/planwise/config.yaml']: OFF, [DRAFTS + '/' + REAL_NAME]: REAL_DRAFT })
  await onSessionStart(hostOf(w.engine as never))
  assert.equal(w.drafts.length, 0)
})

test('draftfeedback a draft from a real linked worktree outlives it and is offered in the main checkout', async () => {
  const temp = realpathSync.native(mkdtempSync(join(tmpdir(), 'draft-wt-'))).replace(/\\/g, '/')
  try {
    const main = temp + '/main'
    const tree = main + '/.claude/worktrees/wt'
    const git = (...args: string[]) => execFileSync('git', args, { cwd: temp, stdio: 'pipe' })
    git('init', '-q', 'main')
    mkdirSync(main + '/planwise', { recursive: true })
    writeFileSync(main + '/planwise/config.yaml', NOTIFY)
    git('-C', 'main', 'add', '-A')
    git('-C', 'main', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'init')
    git('-C', 'main', 'worktree', 'add', '-q', '.claude/worktrees/wt')

    const w = realWorld(tree)
    await onSessionStart(hostOf(w.engine as never))
    const steps = `read ${main}/planwise/config.yaml and ${tree}/notes.md`
    const out = (await capture()(w.engine, { tool: 'mcp__planwise__draft_feedback', ...INPUT, what_happened: steps }, () => undefined)) as { result: string }
    assert.equal(typeof out.result, 'string')

    const dir = main + '/planwise/Feedback/Feedback-Drafts'
    assert.equal(w.writes.length, 1)
    const written = w.writes[0]!
    assert.ok(written.startsWith(dir + '/'), written)
    // Neither the main checkout's path nor the worktree's reaches the file or the card.
    const text = readFileSync(written, 'utf8')
    assert.ok(text.includes('read {project}/planwise/config.yaml and {project}/notes.md'), text)
    assert.equal((w.drafts[0] as { preview: string }).preview, 'read {project}/planwise/config.yaml and {project}/notes.md')
    const argv = w.runs[0]!
    assert.equal(argv[argv.indexOf('--feedback-dir') + 1], dir)
    // Matched on the text only, because earlier cases spend the transcript notices.
    assert.ok(w.logs.some((line) => line.text === NOTICE_TEXT(relativeDraftPath(main, written))), JSON.stringify(w.logs))

    git('-C', 'main', 'worktree', 'remove', '--force', '.claude/worktrees/wt')
    assert.ok(existsSync(written), 'the draft is gone with the worktree')

    const after = realWorld(main)
    await onSessionStart(hostOf(after.engine as never))
    assert.equal(after.drafts.length, 1)
    const id = /^draft_id: "([^"]+)"/m.exec(readFileSync(written, 'utf8'))?.[1]
    assert.equal((after.drafts[0] as { draftId: string }).draftId, id)
  } finally {
    rmSync(temp, { recursive: true, force: true })
  }
})
