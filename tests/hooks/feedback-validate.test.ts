import { test } from 'node:test'
import assert from 'node:assert/strict'
import { validateInput } from '../../plugins/planwise/hooks/feedback/validate.ts'
import { MAX_BODY_BYTES } from '../../plugins/planwise/hooks/feedback/names.ts'

const goodBug = {
  kind: 'bug',
  title: 'Parser drops a row',
  what_happened: 'It dropped a row.',
  what_expected: 'All rows kept.',
  steps: 'Run it twice.',
  subcommand: 'backlog',
}

test('validate: a good bug passes with its cleaned fields', () => {
  const r = validateInput(goodBug)
  assert.equal(r.ok, true)
  if (r.ok) {
    assert.equal(r.kind, 'bug')
    assert.equal(r.title, 'Parser drops a row')
    assert.equal(r.fields['steps'], 'Run it twice.')
    assert.equal(r.subcommand, 'backlog')
  }
})

test('validate: a good idea passes with its three fields', () => {
  const r = validateInput({ kind: 'idea', title: 'Cache it', learned: 'a', why: 'b', where: 'c' })
  assert.equal(r.ok, true)
  if (r.ok) assert.deepEqual(Object.keys(r.fields), ['learned', 'why', 'where'])
})

test('validate: an unknown kind is refused', () => {
  const r = validateInput({ ...goodBug, kind: 'rant' })
  assert.equal(r.ok, false)
  if (!r.ok) assert.match(r.error, /kind/)
})

test('validate: a bug without steps is refused and names the field', () => {
  const { steps: _steps, ...rest } = goodBug
  const r = validateInput(rest)
  assert.equal(r.ok, false)
  if (!r.ok) assert.match(r.error, /steps/)
  assert.equal(validateInput({ ...goodBug, steps: '   ' }).ok, false)
})

test('validate: a body over the byte limit is refused', () => {
  const r = validateInput({ ...goodBug, steps: 'x'.repeat(MAX_BODY_BYTES) })
  assert.equal(r.ok, false)
  if (!r.ok) assert.match(r.error, /bytes/)
  assert.equal(validateInput({ ...goodBug, title: '' }).ok, false)
  assert.equal(validateInput({ ...goodBug, title: 't'.repeat(121) }).ok, false)
})

test('validate: an absent subcommand becomes not command-specific', () => {
  const { subcommand: _sub, ...rest } = goodBug
  const r = validateInput(rest)
  assert.equal(r.ok, true)
  if (r.ok) assert.equal(r.subcommand, 'not command-specific')
  assert.equal(validateInput({ ...goodBug, subcommand: 's'.repeat(41) }).ok, false)
})
