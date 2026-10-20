import { test } from 'node:test'
import assert from 'node:assert/strict'
import { draftFileName, slugOf } from '../../plugins/planwise/hooks/feedback/slug.ts'
import { DRAFT_NAME_RE } from '../../plugins/planwise/hooks/feedback/names.ts'

test('slug: spaces and punctuation become single hyphens', () => {
  assert.equal(slugOf('Hello, World!'), 'hello-world')
  assert.equal(slugOf('  --A__b  '), 'a-b')
})

test('slug: uppercase is lowered', () => {
  assert.equal(slugOf('CamelCase TITLE'), 'camelcase-title')
})

test('slug: a long title cuts to 40 characters with no trailing hyphen', () => {
  assert.equal(slugOf('a'.repeat(50)), 'a'.repeat(40))
  assert.equal(slugOf('a'.repeat(39) + '!!!b'), 'a'.repeat(39))
  const sixty = 'word '.repeat(12).trim()
  const slug = slugOf(sixty)
  assert.equal(sixty.length, 59)
  assert.ok(slug.length <= 40)
  assert.ok(!slug.endsWith('-'))
})

test('slug: an empty result becomes untitled', () => {
  assert.equal(slugOf('!!!'), 'untitled')
  assert.equal(slugOf(''), 'untitled')
})

test('slug: file names carry a collision suffix from the second attempt', () => {
  assert.equal(draftFileName('2026-10-14', 'bug', 'a-b'), '2026-10-14-draft-bug-a-b.md')
  assert.equal(draftFileName('2026-10-14', 'bug', 'a-b', 1), '2026-10-14-draft-bug-a-b.md')
  const second = draftFileName('2026-10-14', 'idea', 'a-b', 2)
  assert.equal(second, '2026-10-14-draft-idea-a-b-2.md')
  assert.ok(DRAFT_NAME_RE.test(second))
  assert.ok(DRAFT_NAME_RE.test(draftFileName('2026-10-14', 'lesson', slugOf('x'), 9)))
})
