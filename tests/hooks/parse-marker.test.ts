import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseLoopMarker } from '../../plugins/planwise/hooks/loop/parse-marker.ts'

const line = (run: string, done: string, remaining: number, state: string): string =>
  `BACKLOG LOOP: run=${run} done=${done} remaining=${remaining} state=${state}`

test('parseLoopMarker: no marker returns null', () => {
  assert.equal(parseLoopMarker('Item closed. Nothing else to report.'), null)
})

test('parseLoopMarker: one marker yields its four fields', () => {
  const m = parseLoopMarker('Done.\n' + line('20261007-141502', '412', 3, 'planwise/Backlog/Backlog-Runs/a.json'))
  assert.deepEqual(m, {
    runId: '20261007-141502',
    doneId: '412',
    remaining: 3,
    statePath: 'planwise/Backlog/Backlog-Runs/a.json',
  })
})

test('parseLoopMarker: two markers, the last wins', () => {
  const text = line('r1', '1', 5, 'a.json') + '\nmore text\n' + line('r2', '2', 4, 'b.json')
  const m = parseLoopMarker(text)
  assert.equal(m?.runId, 'r2')
  assert.equal(m?.doneId, '2')
  assert.equal(m?.remaining, 4)
})

test('parseLoopMarker: a marker inside a code fence still matches', () => {
  const text = 'Output:\n```\n' + line('r1', '7', 2, 'a.json') + '\n```\n'
  assert.equal(parseLoopMarker(text)?.runId, 'r1')
})

test('parseLoopMarker: a Windows path with spaces survives in state=', () => {
  const state = 'C:\\Users\\Some User\\My Project\\Backlog-Runs\\run 1.json'
  const m = parseLoopMarker(line('r1', '9', 1, state))
  assert.equal(m?.statePath, state)
})

test('parseLoopMarker: remaining=0 parses as the number 0', () => {
  const m = parseLoopMarker(line('r1', '9', 0, 'a.json'))
  assert.equal(m?.remaining, 0)
})

test('parseLoopMarker: a trailing sentence on the next line is not part of state', () => {
  const m = parseLoopMarker(line('r1', '3', 2, 'a.json') + '\nThat is the end of this item.\n')
  assert.equal(m?.statePath, 'a.json')
  assert.equal(m?.remaining, 2)
})
