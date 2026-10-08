import { test } from 'node:test'
import assert from 'node:assert/strict'
import { steerText } from '../../plugins/planwise/hooks/loop/steer-text.ts'

test('steerText: names the run id, state path, re-entry command, keep and drop sentences', () => {
  const text = steerText({ runId: 'r-42', doneId: '412', remaining: 3, statePath: 'C:\\x y\\run.json' })
  assert.ok(text.includes('r-42'))
  assert.ok(text.includes('C:\\x y\\run.json'))
  assert.ok(text.includes('backlog --loop-resume r-42'))
  assert.ok(text.includes('The summary MUST keep, verbatim'))
  assert.ok(text.includes('The item just closed (412) and its outcome'))
  assert.ok(text.includes('Drop the fix-agent diff and the tool output'))
  assert.ok(text.includes('The run file is the record'))
})
