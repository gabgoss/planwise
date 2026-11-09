// Free checks of workflows/plan-bodies.js. No agent runs and no API call is made.
//
// Usage: node plan_bodies_harness.mjs <path to plan-bodies.js>
//
// 1. Syntax: parse the script as an async-function body. `node --check` exits 0 on this
//    ES-module file even with a syntax error, so that command proves nothing. The control
//    appends a broken token to the same text and must raise a SyntaxError.
// 2. Shape: meta.phases holds { title } objects.
// 3. Logic: run the body against stub agents and assert which agents start, case by case.
//
// Exit 0 when every check passes, 1 when a check fails, 2 on a usage error.

import { readFileSync } from 'node:fs'

const path = process.argv[2]
if (!path) {
  console.error('usage: node plan_bodies_harness.mjs <script>')
  process.exit(2)
}
const source = readFileSync(path, 'utf8')
if (!/^export const meta = \{/.test(source)) {
  console.error('FAIL the script does not begin with `export const meta = {`')
  process.exit(1)
}
const body = source.replace(/^export const meta/, 'const meta')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const PARAMS = ['agent', 'pipeline', 'parallel', 'phase', 'log', 'args', 'budget', 'workflow']

let failed = 0
function report(ok, name, detail) {
  if (!ok) failed += 1
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}: ${detail}`)
}

// ---- 1. syntax, with a must-fail control
let fn = null
try {
  fn = new AsyncFunction(...PARAMS, body)
  report(true, 'syntax', `parsed ${source.split('\n').length} lines as an async-function body`)
} catch (e) {
  report(false, 'syntax', String(e))
}
try {
  new AsyncFunction(...PARAMS, body + '\nconst = ;')
  report(false, 'syntax control', 'a broken copy parsed, so the syntax check proves nothing')
} catch (e) {
  report(e instanceof SyntaxError, 'syntax control', `a broken copy raised ${e.name}`)
}
if (!fn) process.exit(1)

// ---- 2. meta shape
const metaMatch = source.match(/phases:\s*\[([\s\S]*?)\]\s*,?\s*\n\}/)
const phaseTitles = metaMatch ? [...metaMatch[1].matchAll(/\{\s*title:\s*'([^']+)'/g)].map(m => m[1]) : []
report(phaseTitles.length >= 4, 'meta.phases', `object entries with a title: [${phaseTitles.join(', ')}]`)

// ---- 3. logic against stub agents
const GOOD_ARGS = {
  planwise_root: 'C:/fx/planwise', plan_name: 'ArmFixture', abbrev: 'AFX',
  spec_path: 'C:/fx/planwise/plan-build/ArmFixture/AFX-spec.json',
  notes_path: 'C:/fx/planwise/plan-build/ArmFixture/AFX-PlanNotes.md',
  timestamp: '2026-01-31 05:00', sessions: ['S01-01', 'S01-02'],
}
const ROOT = 'C:/loaded/plugin'

async function run(args, answers) {
  const calls = []
  const agent = async (prompt, opts = {}) => {
    const label = opts.label || '(no label)'
    calls.push({ label, phase: opts.phase || null, agentType: opts.agentType || null, prompt })
    const key = label.split(' ')[0]
    const answer = answers[key]
    return typeof answer === 'function' ? answer(label, prompt) : answer
  }
  const pipeline = async (items, ...stages) => Promise.all(items.map(async (item, i) => {
    let value = item
    for (const stage of stages) value = await stage(value, item, i)
    return value
  }))
  const parallel = async thunks => Promise.all(thunks.map(t => t().catch(() => null)))
  const result = await fn(agent, pipeline, parallel, () => {}, () => {}, args, { total: null, spent: () => 0, remaining: () => Infinity }, async () => null)
  return { result, calls }
}

// A clean preflight answer. The exit code is null on purpose: an agent does not always
// see exit code 0, and the fill_markers= line alone must prove the spec check ran.
const preflightOk = {
  plugin_root: ROOT, spec_refused: false, spec_lint_lines: [], spec_summary_line: 'fill_markers=188 docs=14', spec_exit: null,
  bodies_dir_exists: true, plan_bodies_exists: true, notes_exists: true, open_questions_none: true, progress_section_exists: true,
}
const author = label => ({ session: label.split(' ')[1], status: 'COMPLETE', bodies_paths: ['C:/fx/b.md'], keys_missing: 0, errors: 0, open_questions: [], caller_actions: [] })
const happy = { preflight: preflightOk, author, review: { findings: [] }, apply: { keys_missing: 0, errors: 0, applied: 0, open_questions: [], caller_actions: [] } }
const withPreflight = patch => ({ ...happy, preflight: { ...preflightOk, ...patch } })
const labels = calls => calls.map(c => c.label).join(', ')

// An early return: only the preflight agent started, every session is BLOCKED at the
// preflight stage, and the result holds exactly `count` caller actions with this first reason.
function early(reason, count) {
  return ({ result, calls }) => {
    const sessions = result.sessions || []
    const ok = calls.length === 1 && calls[0].label === 'preflight'
      && sessions.length === 2 && sessions.every(s => s.status === 'BLOCKED' && s.stage === 'preflight' && s.caller_actions.length === count)
      && sessions[0].reason === reason
      && (result.caller_actions || []).length === count && (result.clean_sessions || []).length === 0
    return [ok, `agents [${labels(calls)}]; reason ${JSON.stringify(sessions[0] && sessions[0].reason)}; caller actions ${(result.caller_actions || []).length}`]
  }
}

const cleanRun = ({ result, calls }) =>
  [!('error' in result) && result.clean_sessions?.length === 2, `error ${JSON.stringify(result.error || null)}; agents ${calls.length}; clean ${JSON.stringify(result.clean_sessions)}`]

const cases = [
  ['object args, clean run', GOOD_ARGS, happy, ({ result, calls }) => {
    const commands = calls.filter(c => c.label.startsWith('author')).every(c => c.prompt.includes(ROOT + '/scripts/plan_build.py'))
    const typed = calls[0].label === 'preflight' && calls[0].agentType === 'planwise:plan-preflight'
    return [result.clean_sessions?.length === 2 && commands && typed && result.plugin_root === ROOT && !('error' in result),
      `agents [${labels(calls)}]; clean ${JSON.stringify(result.clean_sessions)}; author commands use the reported root: ${commands}; preflight agent type: ${calls[0].agentType}`]
  }],
  ['args as a JSON string', JSON.stringify(GOOD_ARGS), happy, cleanRun],
  ['args encoded twice', JSON.stringify(JSON.stringify(GOOD_ARGS)), happy, cleanRun],
  ['args missing', undefined, happy, ({ result, calls }) =>
    [calls.length === 0 && result.error === 'invalid args', `agents ${calls.length}; error ${JSON.stringify(result.error)}`]],
  ['a stale plugin_root argument is ignored', { ...GOOD_ARGS, plugin_root: 'C:/stale/other-tree' }, happy, ({ result, calls }) => {
    const leaked = calls.some(c => c.prompt.includes('C:/stale/other-tree'))
    return [!leaked && !('error' in result), `a prompt names the stale path: ${leaked}`]
  }],
  ['exit code 0 alone proves the spec check ran', GOOD_ARGS, withPreflight({ spec_summary_line: '', spec_exit: 0 }), cleanRun],
  ['refused spec, from the REFUSED: line alone', GOOD_ARGS, withPreflight({ spec_lint_lines: ['LINT: x', 'REFUSED: 6 spec lint error(s)'], spec_summary_line: '' }), early('spec refused', 1)],
  ['refused spec, from the spec_refused flag alone', GOOD_ARGS, withPreflight({ spec_refused: true, spec_summary_line: '' }), early('spec refused', 1)],
  ['spec check gave no proof it ran', GOOD_ARGS, withPreflight({ spec_summary_line: '' }), early('spec check did not run', 1)],
  ['spec check exited non-zero with no refusal line', GOOD_ARGS, withPreflight({ spec_exit: 127, spec_summary_line: '' }), early('spec check did not run', 1)],
  ['notes file missing', GOOD_ARGS, withPreflight({ notes_exists: false, open_questions_none: false, progress_section_exists: false }), early('notes file missing', 1)],
  ['open questions', GOOD_ARGS, withPreflight({ open_questions_none: false }), early('open questions', 1)],
  ['progress section missing', GOOD_ARGS, withPreflight({ progress_section_exists: false }), early('progress section missing', 1)],
  ['bodies folder missing', GOOD_ARGS, withPreflight({ bodies_dir_exists: false, plan_bodies_exists: false }), early('bodies folder missing', 1)],
  ['plan bodies file missing', GOOD_ARGS, withPreflight({ plan_bodies_exists: false }), early('plan bodies file missing', 1)],
  ['three causes come back in one result', GOOD_ARGS, withPreflight({ spec_refused: true, spec_summary_line: '', progress_section_exists: false, plan_bodies_exists: false }), early('spec refused', 3)],
  ['root not resolved', GOOD_ARGS, withPreflight({ plugin_root: '${' + 'CLAUDE_PLUGIN_ROOT}' }), ({ result, calls }) =>
    [calls.length === 1 && result.error === 'plugin root not resolved', `agents ${calls.length}; error ${JSON.stringify(result.error)}`]],
  ['preflight agent stopped', GOOD_ARGS, { ...happy, preflight: null }, ({ result, calls }) =>
    [calls.length === 1 && typeof result.error === 'string', `agents ${calls.length}; error ${JSON.stringify(result.error)}`]],
  ['review finds issues', { ...GOOD_ARGS, sessions: ['S01-01'] }, { ...happy, review: { findings: [{ severity: 'ERROR', doc: 'S01-01-01', issue: 'x', fix: 'y' }] } }, ({ result, calls }) =>
    [labels(calls) === 'preflight, author S01-01, review S01-01, apply S01-01' && result.clean_sessions?.length === 1 && calls.every(c => c.phase),
      `agents [${labels(calls)}]; every agent has a phase: ${calls.every(c => c.phase)}`]],
]

for (const [name, args, answers, verdict] of cases) {
  try {
    const [ok, detail] = verdict(await run(args, answers))
    report(ok, `case: ${name}`, detail)
  } catch (e) {
    report(false, `case: ${name}`, `threw ${e}`)
  }
}

console.log(failed === 0 ? 'plan_bodies_harness: all checks pass' : `plan_bodies_harness: ${failed} check(s) failed`)
process.exit(failed === 0 ? 0 : 1)
