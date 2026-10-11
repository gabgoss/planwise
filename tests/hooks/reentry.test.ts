import { test } from 'node:test'
import assert from 'node:assert/strict'
import { reentryArgs, skillNameOf } from '../../plugins/planwise/hooks/loop/reentry.ts'

const cmd = (name: string, plugin?: string) => ({
  name,
  description: '',
  source: 'plugin' as const,
  ...(plugin === undefined ? {} : { plugin }),
})

test('reentryArgs: returns the exact argument string', () => {
  assert.equal(reentryArgs('X'), 'backlog --loop-resume X')
})

test('skillNameOf: follows the preference order', () => {
  const list = [cmd('planwise'), cmd('planwise:run'), cmd('planwise:planwise'), cmd('other')]
  assert.equal(skillNameOf(list), 'planwise:planwise')
  assert.equal(skillNameOf([cmd('planwise:run'), cmd('planwise')]), 'planwise')
})

test('skillNameOf: with no preferred name, a planwise-owned command wins the tie', () => {
  const list = [cmd('planwise:run', 'other-plugin'), cmd('planwise:backlog', 'planwise-dev')]
  assert.equal(skillNameOf(list), 'planwise:backlog')
})

test('skillNameOf: returns null when nothing matches', () => {
  assert.equal(skillNameOf([cmd('review'), cmd('myplanwise')]), null)
  assert.equal(skillNameOf([]), null)
})
