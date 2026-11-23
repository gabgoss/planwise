import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { draftIsLive, draftStillOffered } from '../../plugins/planwise/hooks/feedback/live.ts'
import { isDraftFileName, queuedDraftOf } from '../../plugins/planwise/hooks/feedback/queued.ts'
import { renderDraft } from '../../plugins/planwise/hooks/feedback/render.ts'

// Every file below comes from the real producers. renderDraft writes the queued draft, the draft
// script admits, promotes and discards it, and the post script writes the `.posted` sidecar. The
// reader is held to the bytes they write, not to a shape typed from the reader's side.
const SCRIPTS = fileURLToPath(new URL('../../plugins/planwise/scripts/', import.meta.url))
const PYTHON = process.platform === 'win32' ? 'python' : 'python3'
const ID = 'live-id-1'

/** Runs one real script. `-B` keeps bytecode out of the shipped scripts folder. */
const py = (args: string[]): string => {
  const run = spawnSync(PYTHON, ['-B', ...args], { encoding: 'utf8' })
  assert.equal(run.status, 0, `python ${args.join(' ')} -> ${run.status}: ${run.stderr}`)
  return run.stdout.trim()
}

const drafts = (...args: string[]): string => py([join(SCRIPTS, 'feedback_drafts.py'), ...args])

/** A folder holding one admitted, queued draft, as the hooks tool leaves it. It is removed after the body. */
const withDraft = async (body: (dir: string) => void | Promise<void>): Promise<void> => {
  const dir = mkdtempSync(join(tmpdir(), 'card-live-'))
  try {
    const text = renderDraft(
      { draftId: ID, createdAt: new Date().toISOString(), producer: 'hooks-tool', sourceSessionId: 'sess-1', pluginVersion: '9.9.0', cliVersion: '2.1.330', model: 'model-x', os: 'windows', status: 'queued' },
      { kind: 'bug', title: 'Card stays after a post', fields: { what_happened: 'the card stayed', what_expected: 'it clears', steps: 'post in a second session' }, subcommand: 'not command-specific' },
    )
    const path = join(dir, '2026-11-23-draft-bug-card-stays-after-a-post.md')
    writeFileSync(path, text)
    drafts('admit', '--feedback-dir', dir, path)
    await body(dir)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

/** The folder's file names and the text of each draft file, as the card reads them. */
const snapshot = (dir: string): { names: string[]; texts: Record<string, string> } => {
  const names = readdirSync(dir)
  const texts: Record<string, string> = {}
  for (const name of names) if (isDraftFileName(name)) texts[name] = readFileSync(join(dir, name), 'utf8')
  return { names, texts }
}

const isLive = (dir: string, id = ID): boolean => {
  const { names, texts } = snapshot(dir)
  return draftIsLive(id, names, texts)
}

/** Promotes the draft and returns the promoted file's name. */
const promote = (dir: string): string => drafts('promote', '--feedback-dir', dir, ID).split(/[\\/]/).pop()!

/** Writes the real `.posted` sidecar beside a file, with the post script's own function. */
const writeMarker = (file: string): void => {
  py(['-c', 'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import feedback_post; feedback_post.write_posted_marker(Path(sys.argv[2]), "https://example.test/1", "issue")', SCRIPTS, file])
}

/** The two calls the card makes, answered from a real folder. */
const diskIo = {
  list: async (path: string) => readdirSync(path, { withFileTypes: true }).map((entry) => ({ kind: entry.isFile() ? 'file' : 'dir', name: entry.name })),
  read: async (path: string) => readFileSync(path, 'utf8'),
}

test('live a queued draft is live', async () => {
  await withDraft((dir) => assert.equal(isLive(dir), true))
})

test('live a promoted draft that was kept, with no sidecar, is live so a retry can post it', async () => {
  await withDraft((dir) => {
    promote(dir)
    assert.equal(isLive(dir), true)
  })
})

test('live the draft script writes bare values, which the quoted-only session-start reader cannot read', async () => {
  await withDraft((dir) => {
    promote(dir)
    const text = Object.values(snapshot(dir).texts)[0]!
    assert.match(text, /^status: promoted\r?$/m)
    assert.match(text, /^promoted_to: \S+\.md\r?$/m)
    // The known-bad arm: the reader that session start uses sees no status here.
    assert.equal(queuedDraftOf(text), null)
  })
})

test('live a promoted draft with a posted sidecar is gone', async () => {
  await withDraft((dir) => {
    writeMarker(join(dir, promote(dir)))
    assert.equal(isLive(dir), false)
  })
})

test('live a draft posted through the comment route is gone', async () => {
  await withDraft((dir) => {
    const promoted = promote(dir)
    const name = py(['-c', 'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import feedback_post; print(feedback_post._comment_draft_name(1, Path(sys.argv[2])))', SCRIPTS, promoted])
    assert.match(name, /-comment-1-.*\.md$/)
    writeMarker(join(dir, name))
    assert.equal(isLive(dir), false)
  })
})

test('live a discarded draft is gone', async () => {
  await withDraft((dir) => {
    drafts('discard', '--feedback-dir', dir, ID)
    assert.equal(isLive(dir), false)
  })
})

test('live a draft id the folder does not hold is gone', async () => {
  await withDraft((dir) => assert.equal(isLive(dir, 'other-id'), false))
})

test('live draftStillOffered reads a real folder: offered while queued, not offered after the post', async () => {
  await withDraft(async (dir) => {
    assert.equal(await draftStillOffered(diskIo, dir, ID), true)
    writeMarker(join(dir, promote(dir)))
    assert.equal(await draftStillOffered(diskIo, dir, ID), false)
  })
})

test('live draftStillOffered keeps the card when the folder cannot be listed or read', async () => {
  const broken = async (): Promise<never> => {
    throw new Error('EACCES')
  }
  assert.equal(await draftStillOffered({ list: broken, read: broken }, 'nowhere', ID), true)
})
