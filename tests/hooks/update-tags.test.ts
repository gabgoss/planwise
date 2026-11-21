import { test } from 'node:test'
import assert from 'node:assert/strict'
import { compareVersions, latestRelease, versionOfTag } from '../../plugins/planwise/hooks/update/tags.ts'

test('tags: both tag shapes give the plain version', () => {
  assert.equal(versionOfTag('planwise--v1.0.8'), '1.0.8')
  assert.equal(versionOfTag('1.0.5.3'), '1.0.5.3')
  assert.equal(versionOfTag('planwise--v1.0.8-rc1'), null)
  assert.equal(versionOfTag('nightly'), null)
})

test('tags: the highest version wins, by number and not by text', () => {
  const list = [{ tag_name: 'planwise--v1.0.9' }, { tag_name: 'planwise--v1.0.10' }, { tag_name: '1.0.5.3' }]
  assert.equal(latestRelease(list), '1.0.10')
  assert.equal(compareVersions('1.0.5', '1.0.5.0'), 0)
  assert.equal(compareVersions('1.0.8', '1.0.10'), -1)
})

test('tags: a draft is skipped', () => {
  const list = [{ tag_name: 'planwise--v2.0.0', draft: true }, { tag_name: 'planwise--v1.0.8' }]
  assert.equal(latestRelease(list), '1.0.8')
})

test('tags: a prerelease is skipped', () => {
  const list = [{ tag_name: 'planwise--v2.0.0', prerelease: true }, { tag_name: 'planwise--v1.0.8' }]
  assert.equal(latestRelease(list), '1.0.8')
})

test('tags: an empty list, a non-list and a list with no qualifying tag return null', () => {
  assert.equal(latestRelease([]), null)
  assert.equal(latestRelease({}), null)
  assert.equal(latestRelease([{ tag_name: 'nightly' }, null, { tag_name: 5 }]), null)
})
