import { test } from 'node:test'
import assert from 'node:assert/strict'
import { decide, nextIsPlanItem } from '../../plugins/planwise/hooks/plan-exit/decide.ts'

const EXIT = { behavior: 'allow', updatedInput: {}, updatedPermissions: [{ type: 'setMode', mode: 'acceptEdits', destination: 'session' }] }
const ENTER = { behavior: 'allow', updatedInput: {} }

test('decide: ExitPlanMode in a loop context answers with the exit literal', () => {
  assert.deepEqual(decide({ tool: 'ExitPlanMode', context: 'loop' }), { action: 'answer', decision: EXIT })
})

test('decide: EnterPlanMode in a loop context answers with the enter literal', () => {
  assert.deepEqual(decide({ tool: 'EnterPlanMode', context: 'loop' }), { action: 'answer', decision: ENTER })
})

test('decide: ExitPlanMode in a plan session answers with the exit literal, as a fresh copy each call', () => {
  const first = decide({ tool: 'ExitPlanMode', context: 'plan-session' })
  assert.deepEqual(first, { action: 'answer', decision: EXIT })
  if (first.action === 'answer') first.decision.updatedPermissions?.pop()
  assert.deepEqual(decide({ tool: 'ExitPlanMode', context: 'plan-session' }), { action: 'answer', decision: EXIT })
})

test('decide: EnterPlanMode in a plan session answers with the enter literal', () => {
  assert.deepEqual(decide({ tool: 'EnterPlanMode', context: 'plan-session' }), { action: 'answer', decision: ENTER })
})

test('decide: ExitPlanMode with no context leaves the dialog to the person', () => {
  assert.deepEqual(decide({ tool: 'ExitPlanMode', context: 'none' }), { action: 'next' })
})

test('decide: EnterPlanMode with no context leaves the dialog to the person', () => {
  assert.deepEqual(decide({ tool: 'EnterPlanMode', context: 'none' }), { action: 'next' })
})

// The keys are the run dict of backlog_loop.py --init and its queue_meta entries, copied verbatim.
const run = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  schema_version: 1,
  run_id: 'r1',
  created: '2026-01-01T00:00:00',
  ended: null,
  mode: 'all',
  n: null,
  filters: { priority: null, abbrev: null, status: null },
  no_check: false,
  refine_max: 0,
  excluded: [],
  warnings: [],
  queue: ['010', '011'],
  queue_meta: {
    '010': { route_at_init: 'C', score: 10, feature: 'Plan item', refined_at_init: false, disposition_at_init: 'plan' },
    '011': { route_at_init: 'A', score: 9, feature: 'Run item', refined_at_init: true, disposition_at_init: 'run' },
  },
  known_ids_at_init: ['005', '010', '011'],
  current: '005',
  items: {},
  history: [{ at: '2026-01-01T00:00:00', event: 'init', id: null, detail: 'mode=all n=- queue=2 excluded=0' }],
  ...over,
})
const planNext = (over: Record<string, unknown> = {}): boolean => nextIsPlanItem(JSON.stringify(run(over), null, 2) + '\n', 'r1')

test('nextIsPlanItem: a plan item at the head of the queue is true', () => {
  assert.equal(planNext(), true)
})

test('nextIsPlanItem: a run item at the head is false, with a plan item behind it', () => {
  assert.equal(planNext({ queue: ['011', '010'] }), false)
})

test('nextIsPlanItem: another run id is false', () => {
  assert.equal(planNext({ run_id: 'r2' }), false)
})

test('nextIsPlanItem: an ended run, or a run with no ended key, is false', () => {
  assert.equal(planNext({ ended: '2026-01-01T01:00:00' }), false)
  assert.equal(planNext({ ended: undefined }), false)
})

test('nextIsPlanItem: an empty, missing or non-array queue is false', () => {
  assert.equal(planNext({ queue: [] }), false)
  assert.equal(planNext({ queue: undefined }), false)
  assert.equal(planNext({ queue: '010' }), false)
  assert.equal(planNext({ queue: [null] }), false)
})

test('nextIsPlanItem: a missing queue_meta, or one with no entry for the item, is false', () => {
  assert.equal(planNext({ queue_meta: undefined }), false)
  assert.equal(planNext({ queue_meta: null }), false)
  assert.equal(planNext({ queue_meta: {} }), false)
})

test('nextIsPlanItem: invalid JSON, or JSON that is no object, is false', () => {
  assert.equal(nextIsPlanItem('{', 'r1'), false)
  assert.equal(nextIsPlanItem('', 'r1'), false)
  assert.equal(nextIsPlanItem('null', 'r1'), false)
  assert.equal(nextIsPlanItem('[]', 'r1'), false)
})

test('decide: an unknown tool in an armed context goes to next', () => {
  assert.deepEqual(decide({ tool: 'Bash', context: 'loop' }), { action: 'next' })
  assert.deepEqual(decide({ tool: 'AskUserQuestion', context: 'plan-session' }), { action: 'next' })
})
