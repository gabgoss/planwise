import { test } from 'node:test'
import assert from 'node:assert/strict'
import { renderDraft, scrub, yamlQuote } from '../../plugins/planwise/hooks/feedback/render.ts'
import type { DraftInput, DraftMeta } from '../../plugins/planwise/hooks/feedback/render.ts'
import { FRONTMATTER_KEYS } from '../../plugins/planwise/hooks/feedback/names.ts'

const meta: DraftMeta = {
  draftId: 'pending',
  createdAt: 'pending',
  producer: 'hooks-tool',
  sourceSessionId: 'sess-1',
  pluginVersion: '1.0.0',
  cliVersion: '9.9.9',
  model: 'test-model',
  os: 'win32',
  status: 'pending',
}

const bug: DraftInput = {
  kind: 'bug',
  title: 'Parser drops a row',
  fields: { what_happened: 'It dropped a row.', what_expected: 'All rows kept.', steps: 'Run it twice.' },
  subcommand: 'backlog',
}

const lesson: DraftInput = {
  kind: 'lesson',
  title: 'Count first',
  fields: { learned: 'Counts drift.', why: 'Gates lie.', where: 'Every gate.' },
  subcommand: 'not command-specific',
}

/** The line numbers of each heading, in the order given. */
const positions = (text: string, headings: readonly string[]): number[] =>
  headings.map((h) => text.indexOf('### ' + h + '\n'))

test('render: bug headings appear in the contract order', () => {
  const text = renderDraft(meta, bug)
  const at = positions(text, ['What happened', 'What I expected', 'Steps to reproduce', 'Environment'])
  assert.ok(at.every((n) => n >= 0))
  assert.deepEqual([...at].sort((a, b) => a - b), at)
  assert.ok(text.includes('It dropped a row.'))
})

test('render: lesson headings appear in the contract order', () => {
  const text = renderDraft(meta, lesson)
  const at = positions(text, ['What I learned', 'Why it matters', 'Where it would apply', 'Environment'])
  assert.ok(at.every((n) => n >= 0))
  assert.deepEqual([...at].sort((a, b) => a - b), at)
  assert.ok(!text.includes('What happened'))
})

test('render: every frontmatter key appears once and in order', () => {
  const text = renderDraft(meta, bug)
  const block = text.split('\n---\n')[0] ?? ''
  const keys = block.split('\n').slice(1).map((l) => l.slice(0, l.indexOf(':')))
  assert.deepEqual(keys, [...FRONTMATTER_KEYS])
  assert.ok(text.startsWith('---\n'))
})

test('render: a title with a quote, a backslash, a colon and a line break survives the helper unquote', () => {
  const title = 'He said "stop": C:\\x\nthen left'
  const text = renderDraft(meta, { ...bug, title })
  const line = text.split('\n').find((l) => l.startsWith('title: ')) ?? ''
  const raw = line.slice('title: '.length)
  // Mirror the helper: strip exactly one matching outer quote pair and decode nothing.
  assert.ok(raw.startsWith('"') && raw.endsWith('"'))
  const value = raw.slice(1, -1)
  assert.equal(value, "He said 'stop': C:/x then left")
  assert.equal(yamlQuote(title), raw)
})

test('render: scrub replaces both spellings of a root', () => {
  const roots = ['C:\\work\\proj']
  assert.equal(scrub('see C:\\work\\proj\\a.md and C:/work/proj/b.md', roots), 'see {project}\\a.md and {project}/b.md')
  assert.equal(scrub('x', ['']), 'x')
})

test('render: no absolute path survives a fixture carrying both spellings', () => {
  const dirty: DraftInput = {
    ...bug,
    title: 'Fails in C:\\work\\proj',
    fields: { ...bug.fields, steps: 'open C:/work/proj/x then C:\\work\\proj\\y' },
  }
  const text = scrub(renderDraft(meta, dirty), ['C:/work/proj'])
  assert.ok(!text.includes('work'))
  assert.ok(!/[A-Za-z]:[\\/]/.test(text))
  assert.ok(text.includes('{project}'))
})
