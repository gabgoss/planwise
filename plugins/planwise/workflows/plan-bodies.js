export const meta = {
  name: 'plan-bodies',
  description: 'Author, review and fix the bodies files of every listed plan session, linting each session with plan_build.py lint --session. Never builds the plan.',
  phases: ['Read', 'Author', 'Review', 'Apply'],
}

// Runtime contract this script keeps:
// - Plain JavaScript with top-level await. No module loading, no clock, no random source.
// - The script touches no file and runs no command. Every read, write and lint is an agent's job.
// - No agent can wait on a user answer. A choice that belongs to the user comes back
//   in the result as an open question, and the caller asks it after the run. A cause
//   the caller can fix itself comes back as a caller action, never as a question.
// - agent() resolves to null when the agent was stopped or hit an unrecoverable error.
//   Each null is kept and reported as status PARTIAL with reason 'agent stopped', never as a pass.
// - Every session outside clean_sessions ends with status BLOCKED or PARTIAL.
// - The workflow runs only the per-session lint. The whole-plan lint and the build
//   belong to the caller, because the per-session lint prints no plan summary line.

const REQUIRED_ARGS = ['plugin_root', 'planwise_root', 'plan_name', 'abbrev', 'spec_path', 'notes_path', 'timestamp']

function trimSlash(p) {
  return String(p).replace(/[\\/]+$/, '')
}

function checkArgs(a) {
  if (a === undefined || a === null || typeof a !== 'object') {
    return ['args is missing: pass an object with the required fields plugin_root, planwise_root, plan_name, abbrev, spec_path, notes_path, timestamp and sessions, and the optional fields bodies_dir and clusters']
  }
  const problems = []
  for (const key of REQUIRED_ARGS) {
    if (typeof a[key] !== 'string' || a[key].length === 0) problems.push('args.' + key + ' must be a non-empty string')
  }
  if (!Array.isArray(a.sessions) || a.sessions.length === 0) {
    problems.push('args.sessions must be a non-empty array of session ids in the form SXX-YY')
  } else {
    for (const s of a.sessions) {
      if (typeof s !== 'string' || !/^S\d{2}-\d{2}$/.test(s)) problems.push('args.sessions holds an id not in the form SXX-YY: ' + JSON.stringify(s))
    }
  }
  if (a.clusters !== undefined && !Array.isArray(a.clusters)) problems.push('args.clusters must be an array when given')
  return problems
}

const argProblems = checkArgs(args)
if (argProblems.length > 0) {
  return { error: 'invalid args', problems: argProblems, sessions: [], clean_sessions: [], open_questions: [], caller_actions: [], issues: [] }
}

const pluginRoot = trimSlash(args.plugin_root)
const planwiseRoot = trimSlash(args.planwise_root)
const bodiesDir = trimSlash(args.bodies_dir || (planwiseRoot + '/plan-build/' + args.plan_name))
const planBodiesPath = bodiesDir + '/' + args.abbrev + '-bodies-plan.md'
const specPath = args.spec_path
const notesPath = args.notes_path
const clusters = Array.isArray(args.clusters) ? args.clusters : []

function lintCommand(session) {
  return 'python -B "' + pluginRoot + '/scripts/plan_build.py" lint --spec "' + specPath + '" --bodies-dir "' + bodiesDir + '" --session ' + session
}

function bodiesPath(session) {
  return bodiesDir + '/' + args.abbrev + '-bodies-' + session + '.md'
}

// The bodies grammar, restated in every author and apply prompt. Source: the module
// docstring of scripts/plan_build.py, section "Bodies format".
const BODIES_GRAMMAR = [
  'Bodies grammar (each directive sits alone on one line, outside a fence; a directive inside a fence is body text):',
  '  <!-- doc: ID -->             opens a document block; each doc id appears once across all bodies files',
  '  <!-- fill: name -->          the body of every occurrence of the marker',
  '  <!-- fill: name [k] -->      the body of occurrence k only, counted from 1',
  '  <!-- section: ## Heading --> the body of a whole section; H3 headings work too',
  'A body runs to the next directive. Name a marker as keys prints it, without its braces, and copy a heading exactly as keys prints it.',
  'Write a body only for a key that keys lists. Write no ## line outside a fence. A section body replaces every marker under its heading, so a fill inside that span is a lint error.',
  'Where keys lists {O} or {W}, the body is a plain number. A body for a marker a spec key fills is a lint error.',
  'A section that no template heading covers goes in the body of ## Plan-Specific Sections as an ### H3, only when keys lists that heading for the document.',
].join('\n')

const LINT_LINE = 'The lint prints one LINT: line per error, then the line session=SXX-YY keys_missing=<n> errors=<n>. It exits 0 clean, 1 when a marker has no body, and 2 on any error or refusal.'

const NO_QUESTIONS = 'You cannot ask the user anything and no step may wait on a user answer. A choice that belongs to the user goes into open_questions in your result, with status BLOCKED.'

// ---- Stage 1: Read. One reader per Required Context cluster, when the caller supplies clusters.

const factSchema = {
  type: 'object',
  required: ['facts'],
  properties: {
    facts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim', 'anchor'],
        properties: {
          claim: { type: 'string' },
          anchor: { type: 'string' },
        },
      },
    },
  },
}

const readerResults = await pipeline(clusters, cluster => {
  const name = cluster && cluster.name ? String(cluster.name) : 'cluster'
  const paths = cluster && Array.isArray(cluster.paths) ? cluster.paths : []
  const focus = cluster && cluster.focus ? String(cluster.focus) : 'the facts a plan task body would need to cite'
  return agent(
    [
      'You are a reader for a plan-authoring run. Read these files and report facts. Do not edit any file.',
      'Files: ' + paths.join(', '),
      'Focus: ' + focus,
      'Return each fact as a claim with an anchor. The anchor is the file path plus a heading or symbol, never a line number.',
      'Report only what the files state. Report a measured size only when you ran the plugin measuring script: python "' + pluginRoot + '/scripts/measure_files.py" <files>.',
      NO_QUESTIONS.replace(' with status BLOCKED', ''),
    ].join('\n'),
    { label: 'read ' + name, schema: factSchema },
  )
})

const facts = []
for (const r of readerResults) {
  if (r && Array.isArray(r.facts)) for (const f of r.facts) facts.push(f)
}
const readersSkipped = readerResults.filter(r => !r).length
const factsBlock = facts.length === 0
  ? 'No reader facts were collected. Read what you need yourself.'
  : 'Facts the readers collected (claim -- anchor):\n' + facts.map(f => '- ' + f.claim + ' -- ' + f.anchor).join('\n')

// ---- Stage 2: per session, Author, then Review, then Apply. No barrier between sessions.

const authorSchema = {
  type: 'object',
  required: ['session', 'status', 'bodies_paths', 'keys_missing', 'errors', 'open_questions', 'caller_actions'],
  properties: {
    session: { type: 'string' },
    status: { type: 'string', enum: ['COMPLETE', 'BLOCKED', 'PARTIAL'] },
    bodies_paths: { type: 'array', items: { type: 'string' } },
    keys_missing: { type: ['integer', 'null'] },
    errors: { type: ['integer', 'null'] },
    lint_line: { type: 'string' },
    open_questions: { type: 'array', items: { type: 'string' } },
    caller_actions: { type: 'array', items: { type: 'string' } },
    issues: { type: 'array', items: { type: 'string' } },
  },
}

const reviewSchema = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'doc', 'issue', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['BLOCKER', 'ERROR', 'WARNING', 'INFO'] },
          check: { type: 'string' },
          doc: { type: 'string' },
          key: { type: 'string' },
          issue: { type: 'string' },
          fix: { type: 'string' },
        },
      },
    },
  },
}

const applySchema = {
  type: 'object',
  required: ['keys_missing', 'errors', 'applied', 'open_questions', 'caller_actions'],
  properties: {
    keys_missing: { type: ['integer', 'null'] },
    errors: { type: ['integer', 'null'] },
    lint_line: { type: 'string' },
    applied: { type: 'integer' },
    declined: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
    caller_actions: { type: 'array', items: { type: 'string' } },
    issues: { type: 'array', items: { type: 'string' } },
  },
}

// Causes the caller fixes itself. They go into caller_actions and never reach the user.
const CALLER_ACTIONS = [
  'Put each of these causes into caller_actions, never into open_questions, and return BLOCKED:',
  '  - a needed section has no Plan-Specific Sections heading in keys: name the section and the doc, so the caller adds "Plan-Specific Sections" to that doc\'s optional_sections;',
  '  - an input is missing, or the lint prints a REFUSED: line: name the path or the input;',
  '  - a cited heading or symbol still does not resolve after one Grep: name it, so the caller corrects the spec or the Execution Input.',
  'open_questions holds only a choice that belongs to the user: scope, an architectural option or a documented invariant.',
].join('\n')

function authorPrompt(session) {
  return [
    'Author the bodies of plan session ' + session + '. Follow the protocol in ' + pluginRoot + '/agents/plan-author.md, Steps 1 to 3, with the changes listed under "This run".',
    'Inputs:',
    '  plugin_root: ' + pluginRoot,
    '  planwise_root: ' + planwiseRoot,
    '  metadata spec: ' + specPath,
    '  bodies folder: ' + bodiesDir,
    '  notes file: ' + notesPath,
    '  plan bodies file (context only, never write it): ' + planBodiesPath,
    '  session id: ' + session,
    '  notes timestamp: ' + args.timestamp,
    'Get the keys with: python -B "' + pluginRoot + '/scripts/plan_build.py" keys --spec "' + specPath + '". Read only the doc blocks whose id starts ' + session + '-.',
    'Write the whole session into ' + bodiesPath(session) + ' in one Write. Overflow goes to -part2, -part3 files holding whole document blocks.',
    'Return bodies_paths as absolute paths: the main bodies file first, then every -part{n} file you wrote, in order.',
    BODIES_GRAMMAR,
    'Then run the session lint, plan_build.py lint --session, exactly as:',
    '  ' + lintCommand(session),
    LINT_LINE,
    'Rewrite the file whole and lint again until keys_missing=0 and errors=0, or until you must stop.',
    'This run:',
    '  - Other sessions are authored at the same time and edit the same notes file. Read the notes file again right before each Edit, and touch only this session\'s Authoring Progress row and the entries you add.',
    '  - Never write to the notes file\'s Open Questions section. Return each question only in open_questions in your result.',
    '  - The caller started this run with Open Questions reading none. Never return BLOCKED because of an entry another session wrote in the notes file.',
    '  - Leave the Plan Boundary Note to the caller. Do not rewrite it.',
    '  - Never run build and never run the lint without --session. The caller owns both.',
    '  - ' + NO_QUESTIONS,
    CALLER_ACTIONS,
    'Return the result object. keys_missing and errors come from the last session= line the lint printed, or null when none printed. Put each LINT: line still open, and anything else the caller should read, in issues.',
    factsBlock,
  ].join('\n')
}

function reviewPrompt(session, paths) {
  return [
    'Review the bodies files of plan session ' + session + ': ' + paths.join(', ') + '. The first is the main file, and each -part{n} file holds overflow document blocks. Review every one of them.',
    'This is a read-only review: do not edit, write or create any file.',
    'Read ' + pluginRoot + '/agents/plan-reviewer.md and apply its Task Reviewer role to the task bodies in these files, and read ' + pluginRoot + '/references/review-finding-format.md for severities. Work alone: send no messages and report every finding in your result.',
    'Apply the checks a bodies file can fail: Required Context rows with numeric KiB and ~Tokens; the Context subtotal identity against the estimate; Execution Steps complete and in order; Success Criteria measurable; a Verification Commands Before/After block whose every gate names its owner and records its measured pre-edit value; the USED-helper enumeration where helpers are copied.',
    'Also check the files against the bodies grammar below and the metadata spec ' + specPath + ': every doc id belongs to session ' + session + ', each doc id appears once across the files, and no body contradicts the spec.',
    BODIES_GRAMMAR,
    'Give each finding a severity, the check number when one applies, the doc id, the key, the issue and a concrete fix. Return an empty findings array when the file is clean.',
    NO_QUESTIONS.replace(' with status BLOCKED', ''),
  ].join('\n')
}

function applyPrompt(session, paths, findings) {
  return [
    'Apply review findings to the bodies files of plan session ' + session + ': ' + paths.join(', ') + '. The first is the main file, and each -part{n} file holds overflow document blocks.',
    'Findings (severity | doc | key | issue | fix):',
    findings.map(f => '- ' + f.severity + ' | ' + f.doc + ' | ' + (f.key || '-') + ' | ' + f.issue + ' | ' + f.fix).join('\n'),
    'Fix every BLOCKER, ERROR and WARNING. Fix an INFO finding only when the fix is local. Decline a finding that would contradict the metadata spec ' + specPath + ', and say why in declined.',
    'Find the file that holds each finding\'s doc block, and keep every doc block in the file that holds it. Rewrite each file you change whole in one Write. Do not repair a file with a chain of Edit calls.',
    BODIES_GRAMMAR,
    'Then re-run the session lint, plan_build.py lint --session, exactly as:',
    '  ' + lintCommand(session),
    LINT_LINE,
    'If the lint shows an error your rewrite caused, rewrite the file whole and lint again.',
    'After the last lint, read the notes file ' + notesPath + ' again immediately before one Edit. In that Edit, update only the Authoring Progress row keyed ' + args.abbrev + '-' + session + ': the bodies files, the final keys_missing and errors, and complete when both are 0, otherwise partial. Touch nothing else in the notes file.',
    'Write only this session\'s bodies files and that one notes row. Never run build. ' + NO_QUESTIONS,
    CALLER_ACTIONS,
    'Return keys_missing and errors from the last session= line, or null when none printed, and the number of findings applied. Put each LINT: line still open in issues.',
  ].join('\n')
}

function asList(v) {
  return Array.isArray(v) ? v : []
}

function stopped(session, stage) {
  return { session, status: 'PARTIAL', reason: 'agent stopped', stage, bodies_paths: [bodiesPath(session)], keys_missing: null, errors: null, findings: 0, applied: 0, declined: [], open_questions: [], caller_actions: [], issues: [] }
}

const sessionResults = await pipeline(args.sessions, async session => {
  const author = await agent(authorPrompt(session), { label: 'author ' + session, schema: authorSchema })
  if (!author) return stopped(session, 'author')
  const paths = asList(author.bodies_paths).filter(p => typeof p === 'string' && p.length > 0)
  const base = {
    session,
    bodies_paths: paths.length > 0 ? paths : [bodiesPath(session)],
    keys_missing: author.keys_missing,
    errors: author.errors,
    findings: 0,
    applied: 0,
    declined: [],
    open_questions: asList(author.open_questions),
    caller_actions: asList(author.caller_actions),
    issues: asList(author.issues),
  }
  if (author.status !== 'COMPLETE') {
    return Object.assign(base, { status: author.status, stage: 'author' })
  }

  const review = await agent(reviewPrompt(session, base.bodies_paths), { label: 'review ' + session, schema: reviewSchema })
  if (!review) return Object.assign(base, { status: 'PARTIAL', reason: 'agent stopped', stage: 'review' })
  const findings = asList(review.findings)
  base.findings = findings.length
  if (findings.length === 0) {
    return Object.assign(base, { status: 'COMPLETE', stage: 'review' })
  }

  const applied = await agent(applyPrompt(session, base.bodies_paths, findings), { label: 'apply ' + session, schema: applySchema })
  if (!applied) {
    return Object.assign(base, { status: 'PARTIAL', reason: 'agent stopped', stage: 'apply', keys_missing: null, errors: null })
  }
  const questions = base.open_questions.concat(asList(applied.open_questions))
  const actions = base.caller_actions.concat(asList(applied.caller_actions))
  const clean = applied.keys_missing === 0 && applied.errors === 0
  return Object.assign(base, {
    status: questions.length > 0 || actions.length > 0 ? 'BLOCKED' : (clean ? 'COMPLETE' : 'PARTIAL'),
    stage: 'apply',
    keys_missing: applied.keys_missing,
    errors: applied.errors,
    applied: applied.applied,
    declined: asList(applied.declined),
    open_questions: questions,
    caller_actions: actions,
    issues: base.issues.concat(asList(applied.issues)),
  })
})

// ---- Return. A session is clean only on a lint line that read keys_missing=0 and errors=0.
// Every other session ends BLOCKED or PARTIAL, so the caller has a rule for each one.

function settle(s) {
  const clean = s.keys_missing === 0 && s.errors === 0
  if (asList(s.open_questions).length > 0 || asList(s.caller_actions).length > 0) return Object.assign(s, { status: 'BLOCKED' })
  if (s.status === 'COMPLETE' && clean) return s
  if (s.status === 'BLOCKED') return s
  if (s.status === 'COMPLETE') return Object.assign(s, { status: 'PARTIAL', reason: 'COMPLETE without a clean session= lint line' })
  if (s.status === 'PARTIAL') return s
  return Object.assign(s, { status: 'PARTIAL', reason: 'unknown status ' + JSON.stringify(s.status) })
}

const sessions = sessionResults.map((r, i) => settle(r || stopped(args.sessions[i], 'author')))
const cleanSessions = sessions.filter(s => s.status === 'COMPLETE').map(s => s.session)
const openQuestions = []
const callerActions = []
const issues = []
for (const s of sessions) {
  for (const q of asList(s.open_questions)) openQuestions.push({ session: s.session, question: q })
  for (const a of asList(s.caller_actions)) callerActions.push({ session: s.session, action: a })
  for (const x of asList(s.issues)) issues.push({ session: s.session, issue: x })
}

return {
  sessions,
  clean_sessions: cleanSessions,
  open_questions: openQuestions,
  caller_actions: callerActions,
  issues,
  bodies_dir: bodiesDir,
  reader_facts: facts.length,
  readers_skipped: readersSkipped,
  next: 'The caller routes each caller action, asks each open question, re-dispatches every session not in clean_sessions, writes the Plan Boundary Note, then runs the whole-plan lint and build.',
}
