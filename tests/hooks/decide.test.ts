import { test } from 'node:test'
import assert from 'node:assert/strict'
import { decide } from '../../plugins/planwise/hooks/loop/decide.ts'
import type { DecideInput } from '../../plugins/planwise/hooks/loop/decide.ts'

/** The happy path: a marker with items left, no latch, nothing running. */
const base: DecideInput = {
  marker: { runId: 'r1', doneId: '5', remaining: 2, statePath: 'a.json' },
  lastKey: null,
  turnRunning: false,
  pendingQuestion: false,
}

test('decide: no marker gives none / no-marker', () => {
  assert.deepEqual(decide({ ...base, marker: null }), { action: 'none', reason: 'no-marker' })
})

test('decide: remaining zero gives none / remaining-zero', () => {
  const marker = { runId: 'r1', doneId: '5', remaining: 0, statePath: 'a.json' }
  assert.deepEqual(decide({ ...base, marker }), { action: 'none', reason: 'remaining-zero' })
})

test('decide: a matching latch gives none / already-latched', () => {
  assert.deepEqual(decide({ ...base, lastKey: 'r1:5' }), { action: 'none', reason: 'already-latched' })
})

test('decide: a running turn gives defer / turn-running', () => {
  assert.deepEqual(decide({ ...base, turnRunning: true }), { action: 'defer', reason: 'turn-running' })
})

test('decide: an open question gives defer / pending-question', () => {
  assert.deepEqual(decide({ ...base, pendingQuestion: true }), { action: 'defer', reason: 'pending-question' })
})

test('decide: the happy path gives reenter / ok', () => {
  assert.deepEqual(decide(base), { action: 'reenter', reason: 'ok' })
})
