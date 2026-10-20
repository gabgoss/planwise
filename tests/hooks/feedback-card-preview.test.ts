import { test } from 'node:test'
import assert from 'node:assert/strict'
import { clearIfSame, fitTitle, isStalePress, previewLines, previewRows, previewSourceOf, shouldAskTurnOff } from '../../plugins/planwise/hooks/feedback/card-preview.ts'

const words = (n: number): string => Array.from({ length: n }, (_, i) => 'word' + String(i % 10)).join(' ')

test('a long preview trims to four lines and the last ends in an ellipsis', () => {
  const lines = previewLines(words(150), 40, 4)
  assert.equal(lines.length, 4)
  assert.ok((lines[3] ?? '').endsWith('…'))
  for (const line of lines) assert.ok(Array.from(line).length <= 40)
})

test('lines wrap at the band width without splitting a word that has a space before it', () => {
  const text = 'alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa quebec romeo sierra tango'
  const lines = previewLines(text, 40, 4)
  assert.ok(lines.length >= 3)
  for (const line of lines) assert.ok(Array.from(line).length <= 40, line)
  assert.equal(lines.join(' ').replace(/…$/, '').split(' ').every((w) => text.includes(w)), true)
})

test('a preview that fits has no ellipsis', () => {
  const lines = previewLines('one short line of text that wraps once into two lines of words here', 40, 4)
  assert.equal(lines.length, 2)
  assert.equal(lines.join('').includes('…'), false)
})

test('the fit rule gives the preview rows for each band height', () => {
  assert.deepEqual([3, 4, 5, 7, 20].map(previewRows), [0, 1, 2, 4, 4])
  const one = previewLines(words(40), 40, previewRows(4))
  assert.equal(one.length, 1)
  assert.ok((one[0] ?? '').endsWith('…'))
})

test('a long title is cut to the width with the kind label kept', () => {
  const out = fitTitle('Bug draft', 'x'.repeat(80), 40)
  assert.equal(Array.from(out).length, 40)
  assert.ok(out.startsWith('Bug draft: '))
  assert.ok(out.endsWith('…'))
})

const draftOf = (draftId: string) => ({ draftId, configPath: '/p/config.yaml' })

test('a press clears the card only while it still holds the pressed draft', () => {
  const held = draftOf('a')
  assert.equal(clearIfSame(held, 'a'), null)
  assert.equal(clearIfSame(draftOf('b'), 'a')?.draftId, 'b')
  assert.equal(clearIfSame(held, null), held)
  assert.equal(clearIfSame(null, 'a'), null)
})

test('a press on an empty card is stale and a press on a held card is not', () => {
  assert.equal(isStalePress(null), true)
  assert.equal(isStalePress(draftOf('a')), false)
})

test('the turn-off ask comes only on the second dismissal of a draft with a config path', () => {
  assert.deepEqual([0, 1, 2, 3].map((n) => shouldAskTurnOff(n, '/p/config.yaml')), [false, false, true, false])
  assert.equal(shouldAskTurnOff(2, ''), false)
})

test('the preview scrubs the project root before it cuts, so a root at the cut leaks nothing', () => {
  const root = 'C:/work/project-root'
  const text = 'x'.repeat(505) + ' ' + root + '/src/file.ts'
  const out = previewSourceOf('bug', { what_happened: text }, [root])
  assert.equal(out.includes('C:/work'), false)
  assert.equal(out.includes('project-root'), false)
  assert.ok(out.endsWith(' {proje'))
  assert.equal(Array.from(out).length, 512)
  assert.equal(previewSourceOf('lesson', { learned: 'a  b\n c' }, []), 'a b c')
})
