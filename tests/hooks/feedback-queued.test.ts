import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isDraftFileName, newestQueued, queuedDraftOf } from '../../plugins/planwise/hooks/feedback/queued.ts'
import { renderDraft } from '../../plugins/planwise/hooks/feedback/render.ts'

// Each draft text below comes from the real producer, renderDraft, so the reader is held to the
// shape the writer emits, not to a shape typed from the reader's side.
const META = {
  draftId: 'id-1',
  createdAt: '2026-11-22T03:31:30.676Z',
  producer: 'hooks-tool',
  sourceSessionId: 'sess-1',
  pluginVersion: '9.9.0',
  cliVersion: '2.1.330',
  model: 'model-x',
  os: 'windows',
  status: 'queued',
}
const bug = (meta: Partial<typeof META> = {}) =>
  renderDraft({ ...META, ...meta }, { kind: 'bug', title: 'Card stays hidden', fields: { what_happened: 'the card did not return', what_expected: 'it returns', steps: 'press 1' }, subcommand: 'not command-specific' })

test('queued a rendered queued bug reads back with its first body field', () => {
  const draft = queuedDraftOf(bug())
  assert.ok(draft !== null)
  assert.equal(draft.draftId, 'id-1')
  assert.equal(draft.kind, 'bug')
  assert.equal(draft.title, 'Card stays hidden')
  assert.equal(draft.sessionId, 'sess-1')
  assert.equal(draft.fields['what_happened'], 'the card did not return')
  assert.equal(draft.fields['steps'], 'press 1')
})

test('queued a CRLF copy of the same file reads the same', () => {
  const draft = queuedDraftOf(bug().replace(/\n/g, '\r\n'))
  assert.ok(draft !== null)
  assert.equal(draft.fields['what_happened'], 'the card did not return')
})

test('queued a draft whose status moved on reads as null', () => {
  assert.equal(queuedDraftOf(bug({ status: 'posted' })), null)
})

test('queued a half-written file with no closing frontmatter reads as null', () => {
  const text = bug()
  assert.equal(queuedDraftOf(text.slice(0, text.indexOf('status:'))), null)
})

test('queued the newest queued draft wins, and a posted newer one is skipped', () => {
  const old = bug({ draftId: 'old', createdAt: '2026-11-20T00:00:00.000Z' })
  const mid = bug({ draftId: 'mid', createdAt: '2026-11-21T00:00:00.000Z' })
  const posted = bug({ draftId: 'posted', createdAt: '2026-11-23T00:00:00.000Z', status: 'posted' })
  assert.equal(newestQueued([old, posted, mid])?.draftId, 'mid')
  assert.equal(newestQueued([posted]), null)
  assert.equal(newestQueued([]), null)
})

test('queued draft file names follow the producer pattern', () => {
  assert.equal(isDraftFileName('2026-11-22-draft-idea-add-a-hello-world-example-to-planwise.md'), true)
  assert.equal(isDraftFileName('2026-11-22-draft-bug-card-stays-hidden-2.md'), true)
  assert.equal(isDraftFileName('README.md'), false)
  assert.equal(isDraftFileName('2026-11-22-draft-idea-x.md.tmp'), false)
})
