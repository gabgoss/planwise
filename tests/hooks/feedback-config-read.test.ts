import { test } from 'node:test'
import assert from 'node:assert/strict'
import { draftsMode, isPlanwiseConfig, readRawScalar, readScalar, resolveDraftsDir } from '../../plugins/planwise/hooks/feedback/config-read.ts'
import { CAP_TEXT, MAX_CALLS_PER_SESSION, MAX_QUEUED, NOTICE_TEXT, PYTHON_CANDIDATES, RESULT_TEXT, relativeDraftPath } from '../../plugins/planwise/hooks/feedback/names.ts'

/** An excerpt shaped like the shipped config template. */
const template = [
  '# planwise config',
  'project:',
  '  name: demo',
  '  planwise_root: planwise   # where plans live',
  '  feedback_dir: feedback-drafts',
  '',
  'feedback:',
  '  enabled: false',
  '  repo: "gabgoss/planwise"',
  '  drafts: notify  # notify | quiet | off',
  '',
].join('\n')

test('config-read: reads the template excerpt', () => {
  assert.equal(readScalar(template, ['feedback', 'drafts']), 'notify')
  assert.equal(readScalar(template, ['project', 'planwise_root']), 'planwise')
  assert.equal(readScalar(template, ['project', 'feedback_dir']), 'feedback-drafts')
})

test('config-read: strips quotes in readScalar and keeps them in readRawScalar', () => {
  const yaml = 'feedback:\n  drafts: "quiet"\n'
  assert.equal(readScalar(yaml, ['feedback', 'drafts']), 'quiet')
  assert.equal(readRawScalar(yaml, ['feedback', 'drafts']), '"quiet"')
})

test('config-read: strips a trailing comment but not a hash inside quotes', () => {
  assert.equal(readRawScalar('feedback:\n  drafts: quiet # later\n', ['feedback', 'drafts']), 'quiet')
  assert.equal(readRawScalar('feedback:\n  drafts: "a # b"\n', ['feedback', 'drafts']), '"a # b"')
})

test('config-read: an absent key reads undefined and the mode is notify', () => {
  assert.equal(readRawScalar('feedback:\n  enabled: true\n', ['feedback', 'drafts']), undefined)
  assert.equal(draftsMode(undefined), 'notify')
  assert.equal(draftsMode('bogus'), 'notify')
})

test('config-read: unquoted off gives off', () => {
  const raw = readRawScalar('feedback:\n  drafts: off\n', ['feedback', 'drafts'])
  assert.equal(draftsMode(raw), 'off')
})

test('config-read: a drafts key under another block is ignored', () => {
  const yaml = 'other:\n  drafts: off\nfeedback:\n  enabled: true\n'
  assert.equal(readRawScalar(yaml, ['feedback', 'drafts']), undefined)
  assert.equal(readRawScalar(yaml, ['other', 'drafts']), 'off')
})

test('config-read: unquoted false gives off', () => {
  assert.equal(draftsMode(readRawScalar('feedback:\n  drafts: false\n', ['feedback', 'drafts'])), 'off')
  assert.equal(draftsMode('False'), 'off')
  assert.equal(draftsMode('FALSE'), 'off')
})

test('config-read: quoted "off" gives off', () => {
  assert.equal(draftsMode(readRawScalar('feedback:\n  drafts: "off"\n', ['feedback', 'drafts'])), 'off')
  assert.equal(draftsMode("'Off'"), 'off')
})

test('config-read: unquoted true gives notify', () => {
  assert.equal(draftsMode(readRawScalar('feedback:\n  drafts: true\n', ['feedback', 'drafts'])), 'notify')
  assert.equal(draftsMode('on'), 'notify')
  assert.equal(draftsMode('yes'), 'notify')
})

test('config-read: unquoted no is a boolean (off) and quoted "no" is a string (notify)', () => {
  assert.equal(draftsMode('no'), 'off')
  assert.equal(draftsMode('"no"'), 'notify')
})

test('config-read: a planwise config has a top-level project: key', () => {
  assert.equal(isPlanwiseConfig(template), true)
  assert.equal(isPlanwiseConfig('project:   # the block\n  name: x\n'), true)
  assert.equal(isPlanwiseConfig('\uFEFFproject:\r\n  name: x\r\n'), true)
})

test('config-read: a foreign config.yaml is not a planwise config', () => {
  assert.equal(isPlanwiseConfig('name: other\nversion: 1\n'), false)
  assert.equal(isPlanwiseConfig('  project:\n    name: nested\n'), false)
  assert.equal(isPlanwiseConfig('projects:\n  - a\n'), false)
  assert.equal(isPlanwiseConfig(''), false)
})

test('config-read: the drafts dir sits under the config directory, not planwise_root', () => {
  assert.equal(resolveDraftsDir('/proj/planwise', 'feedback-drafts'), '/proj/planwise/feedback-drafts')
  assert.equal(resolveDraftsDir('/proj/planwise/', 'Fb'), '/proj/planwise/Fb')
  assert.equal(resolveDraftsDir('C:\\proj\\planwise', 'Fb'), 'C:/proj/planwise/Fb')
})

test('config-read: an absent or blank feedback_dir falls back to Feedback', () => {
  assert.equal(resolveDraftsDir('/proj/planwise', undefined), '/proj/planwise/Feedback')
  assert.equal(resolveDraftsDir('/proj/planwise', ''), '/proj/planwise/Feedback')
  assert.equal(resolveDraftsDir('/proj/planwise', '   '), '/proj/planwise/Feedback')
})

test('config-read: an absolute feedback_dir is kept as given', () => {
  assert.equal(resolveDraftsDir('/proj/planwise', '/var/fb'), '/var/fb')
  assert.equal(resolveDraftsDir('/proj/planwise', 'D:\\fb\\x'), 'D:/fb/x')
})

test('names: the model-facing texts keep their wording and carry the limits', () => {
  assert.equal(MAX_QUEUED, 10)
  assert.equal(MAX_CALLS_PER_SESSION, 10)
  assert.equal(RESULT_TEXT, 'Feedback draft queued locally (max 10 kept per project). The user can review and send it with /planwise feedback --drafts; nothing is sent without their approval. Do not announce this or ask the user about it.')
  assert.equal(CAP_TEXT, 'Feedback draft limit reached for this session (10). Do not call this tool again this session.')
})

test('names: the notice carries the specified wording and a relative path', () => {
  const text = NOTICE_TEXT('feedback-drafts/2026-10-19-draft-bug-x.md')
  assert.equal(text, 'a feedback draft was saved to feedback-drafts/2026-10-19-draft-bug-x.md \u2014 review it with /planwise feedback --drafts')
  assert.equal(text.includes('planwise: '), false)
})

test('names: relativeDraftPath returns a root-relative path for a Windows root and a POSIX root', () => {
  const noAbsolute = /^(?![A-Za-z]:|\/)/
  const cases: [string, string, string][] = [
    ['C:/proj', 'C:/proj/planwise/Fb/a.md', 'planwise/Fb/a.md'],
    ['C:\\proj\\', 'c:/proj\\planwise\\Fb/a.md', 'planwise/Fb/a.md'],
    ['/home/u/proj', '/home/u/proj/planwise/Fb/a.md', 'planwise/Fb/a.md'],
    ['C:/proj', 'D:/other/Fb/a.md', 'a.md'],
    ['/home/u/proj', '/var/fb/a.md', 'a.md'],
  ]
  for (const [root, path, expected] of cases) {
    const result = relativeDraftPath(root, path)
    assert.equal(result, expected)
    assert.match(result, noAbsolute)
  }
})

test('names: python is tried before python3', () => {
  assert.deepEqual([...PYTHON_CANDIDATES], ['python', 'python3'])
})
