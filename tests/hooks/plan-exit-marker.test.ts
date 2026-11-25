import { test } from 'node:test'
import assert from 'node:assert/strict'
import { endsOnLoopMarker, isPlanModeMarker } from '../../plugins/planwise/hooks/plan-exit/marker.ts'

const PLAN = 'PLANWISE PLAN-MODE: command=plan policy=auto'
const LOOP = 'BACKLOG LOOP: run=r1 done=5 remaining=2 state=a.json'

test('isPlanModeMarker: the exact marker as the final line is true', () => {
  assert.equal(isPlanModeMarker(PLAN), true)
  assert.equal(isPlanModeMarker('Send any message to start.\n' + PLAN), true)
})

test('isPlanModeMarker: trailing blank lines and CRLF line endings still count', () => {
  assert.equal(isPlanModeMarker('Send a message.\n' + PLAN + '\n\n  \n'), true)
  assert.equal(isPlanModeMarker('Send a message.\r\n' + PLAN + '\r\n\r\n'), true)
})

test('isPlanModeMarker: a near-miss is false', () => {
  assert.equal(isPlanModeMarker('PLANWISE PLAN-MODE: command=plan policy=ask'), false)
  assert.equal(isPlanModeMarker(PLAN + ' extra=1'), false)
  assert.equal(isPlanModeMarker('PLANWISE PLAN-MODE: command=plan'), false)
})

test('isPlanModeMarker: a marker followed by a sentence is false', () => {
  assert.equal(isPlanModeMarker(PLAN + '\nThat is the end.'), false)
})

test('isPlanModeMarker: a marker in a fence, a quote or backticks is false', () => {
  assert.equal(isPlanModeMarker('```\n' + PLAN + '\n```'), false)
  assert.equal(isPlanModeMarker('> ' + PLAN), false)
  assert.equal(isPlanModeMarker('`' + PLAN + '`'), false)
  assert.equal(isPlanModeMarker('  ' + PLAN), false)
})

test('endsOnLoopMarker: true on the last line, false when a line follows it', () => {
  assert.equal(endsOnLoopMarker('Done.\n' + LOOP), true)
  assert.equal(endsOnLoopMarker('Done.\r\n' + LOOP + '\r\n\r\n'), true)
  assert.equal(endsOnLoopMarker(LOOP + '\nThat is all.'), false)
  assert.equal(endsOnLoopMarker('No marker at all.'), false)
})
