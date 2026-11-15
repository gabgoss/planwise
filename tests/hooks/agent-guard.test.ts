import { test } from 'node:test'
import assert from 'node:assert/strict'

// The module under test. GUARD_URL points the same tests at another copy of agent-guard.ts.
const target = process.env.GUARD_URL ?? new URL('../../plugins/planwise/hooks/agent-guard.ts', import.meta.url).href
const guard = await import(target)
const { register, RUNNER, RESUME_DIRECTIVE, bareVerbs, looksUnfinished, missingClauses, modeOf } = guard

// The clauses the spawn-prompt check must report, listed here and not imported, so a check
// dropped from the module fails this file.
const CLAUSES = [
  'You are dispatched to execute ONE task:',
  '## HARD CONSTRAINTS',
  'Execute ONLY',
  '## SCOPE BOUNDARY',
  'SendMessage',
  'Do NOT proceed to task',
  'FOREGROUND',
]

type Rec = { run: (...a: unknown[]) => unknown; catcher?: (...a: unknown[]) => unknown }

/** A conforming runner spawn prompt: every clause the guard checks. */
const GOOD_PROMPT = [
  'You are dispatched to execute ONE task: T-01. The session has other tasks.',
  '## HARD CONSTRAINTS (non-negotiable)',
  '1a. Execute ONLY T-01.',
  '7. Run every pytest invocation in the FOREGROUND, with a timeout up to 600000 ms.',
  '## SCOPE BOUNDARY',
  '- In scope: the Output paths',
  'Deliver your status block by calling the SendMessage tool with to="main".',
  'Return after writing the expected output files. Do NOT proceed to task T-02.',
].join('\n')

// Prompts copied from workflows/plan-bodies.js: the preflight agent and a reader agent.
const PREFLIGHT_PROMPT = 'Preflight for a plan-bodies run. Report facts only. Write no file and author nothing.'
const READER_PROMPT = 'You are a reader for a plan-authoring run. Read these files and report facts. Do not edit any file.'

/** Registers the guard against a fake engine: captured hooks and recorded log lines. */
const harness = (options: Record<string, unknown> = {}) => {
  const hooks = new Map<string, Rec>()
  const on = (name: string, run: (...a: unknown[]) => unknown) => {
    const rec: Rec = { run }
    hooks.set(name, rec)
    return { catch: (c: (...a: unknown[]) => unknown) => void (rec.catcher = c) }
  }
  const logs: string[] = []
  const $ = { ui: { log: (text: string) => void logs.push(text) } }
  register(on, options)
  let nextCalls = 0
  const passed = { passed: true }
  const run = (name: string, e: Record<string, unknown>, next: (e: unknown) => unknown = () => (nextCalls++, passed)) =>
    hooks.get(name)!.run($, e, next)
  const caught = (name: string, error: unknown, called: boolean) => {
    const next = Object.assign(() => (nextCalls++, 'replayed'), { error, called })
    return hooks.get(name)!.catcher!($, {}, next)
  }
  const spawnRunner = (agentId: string, extra: Record<string, unknown> = {}) =>
    run('agent.spawn', { subagentType: RUNNER, prompt: GOOD_PROMPT, ...extra }, () => ({ model: 'm', agentId }))
  return { run, caught, spawnRunner, logs, passed, nextCount: () => nextCalls }
}

const agentCall = (extra: Record<string, unknown> = {}) => ({
  tool: 'Agent',
  subagent_type: RUNNER,
  prompt: GOOD_PROMPT,
  run_in_background: false,
  ...extra,
})

// --- positive control ---

test('positive: a conforming runner call passes, in both modes, with no log', async () => {
  for (const options of [{}, { agent_guard: 'deny' }]) {
    const h = harness(options)
    assert.equal(await h.run('tool.call', agentCall()), h.passed)
    assert.equal(h.nextCount(), 1)
    assert.deepEqual(h.logs, [])
  }
})

// --- mutation controls, one per kind ---

test('mutation, spawn-prompt: each removed clause is reported by name, and the call proceeds', async () => {
  for (const clause of CLAUSES) {
    const h = harness({ agent_guard: 'deny' })
    const result = await h.run('tool.call', agentCall({ prompt: GOOD_PROMPT.replace(clause, '') }))
    assert.equal(result, h.passed, clause)
    assert.equal(h.logs.length, 1, clause)
    assert.ok(h.logs[0]!.includes(clause), `${clause} not named in: ${h.logs[0]}`)
  }
})

test('mutation, background-call: run_in_background true is denied in deny mode', async () => {
  const h = harness({ agent_guard: 'deny' })
  const result = (await h.run('tool.call', agentCall({ run_in_background: true }))) as { deny?: string }
  assert.equal(typeof result.deny, 'string')
  assert.ok(result.deny!.includes('run_in_background'))
  assert.equal(h.nextCount(), 0)
})

test('mutation, runner-stop: an unfinished runner is blocked with the resume directive in deny mode', async () => {
  const h = harness({ agent_guard: 'deny' })
  await h.spawnRunner('a1')
  const result = await h.run('classic.SubagentStop', {
    agent_id: 'a1',
    agent_type: RUNNER,
    stop_hook_active: false,
    last_assistant_message: "I've dispatched the task-runner and I'll report back when it returns.",
  })
  assert.deepEqual(result, { block: RESUME_DIRECTIVE })
})

test('mutation, Bash-verb: a bare file read and a bare cd are denied inside a runner in deny mode', async () => {
  for (const [command, verb] of [['cat notes.md', 'cat'], ['cd /repo && ls', 'cd'], ['sed -n 10,40p f.md', 'sed -n'], ['ls -R src', 'ls -R']]) {
    const h = harness({ agent_guard: 'deny' })
    await h.spawnRunner('a1')
    const result = (await h.run('tool.call', { tool: 'Bash', agentId: 'a1', command })) as { deny?: string }
    assert.equal(typeof result.deny, 'string', command)
    assert.ok(result.deny!.includes(verb!), `${verb} not named in: ${result.deny}`)
  }
})

// --- scope controls ---

test('scope: another plugin\'s Agent call passes untouched, even in the background and with no clauses', async () => {
  const h = harness({ agent_guard: 'deny' })
  const result = await h.run('tool.call', { tool: 'Agent', subagent_type: 'other:runner', prompt: 'do it', run_in_background: true })
  assert.equal(result, h.passed)
  assert.deepEqual(h.logs, [])
})

test('scope: a Bash call outside a runner passes untouched', async () => {
  const h = harness({ agent_guard: 'deny' })
  await h.spawnRunner('a1')
  assert.equal(await h.run('tool.call', { tool: 'Bash', command: 'cat notes.md' }), h.passed)
  assert.equal(await h.run('tool.call', { tool: 'Bash', agentId: 'b9', command: 'cd /x' }), h.passed)
  assert.deepEqual(h.logs, [])
})

test('scope: another agent type\'s stop passes untouched', async () => {
  const h = harness({ agent_guard: 'deny' })
  const result = await h.run('classic.SubagentStop', {
    agent_id: 'z1', agent_type: 'general-purpose', stop_hook_active: false, last_assistant_message: 'Let me check the file:',
  })
  assert.equal(result, h.passed)
})

// --- workflow scope controls ---

test('workflow scope: plan-bodies agents pass untouched and never count as runners', async () => {
  const h = harness({ agent_guard: 'deny' })
  const workflow = { runId: 'wf_1', agentIndex: 1 }
  await h.run('agent.spawn', { subagentType: 'planwise:plan-preflight', prompt: PREFLIGHT_PROMPT, workflow }, () => ({ model: 'm', agentId: 'w1' }))
  await h.run('agent.spawn', { subagentType: 'general-purpose', prompt: READER_PROMPT, workflow: { runId: 'wf_1', agentIndex: 2 } }, () => ({ model: 'm', agentId: 'w2' }))
  // Even a workflow spawn typed as the runner is not recorded: the guard keys on Agent-tool runners only.
  await h.run('agent.spawn', { subagentType: RUNNER, prompt: READER_PROMPT, workflow: { runId: 'wf_1', agentIndex: 3 } }, () => ({ model: 'm', agentId: 'w3' }))
  assert.equal(await h.run('tool.call', { tool: 'Agent', subagent_type: 'planwise:plan-preflight', prompt: PREFLIGHT_PROMPT }), h.passed)
  assert.equal(await h.run('tool.call', { tool: 'Agent', prompt: READER_PROMPT }), h.passed)
  for (const agentId of ['w1', 'w2', 'w3']) {
    assert.equal(await h.run('tool.call', { tool: 'Bash', agentId, command: 'cat notes.md' }), h.passed, agentId)
  }
  assert.deepEqual(h.logs, [])
})

// --- over-correction controls ---

test('over-correction, Bash-verb: ordinary commands inside a runner pass in deny mode', async () => {
  const h = harness({ agent_guard: 'deny' })
  await h.spawnRunner('a1')
  for (const command of [
    'git status',
    'git show HEAD:f.md | cat -A',
    'git -C repo diff -- a.md | grep -E \'^\\+\' | head -5',
    'python -B scripts/x.py --check',
    'echo "a; cd b"',
    'wc -l a.md',
  ]) {
    assert.equal(await h.run('tool.call', { tool: 'Bash', agentId: 'a1', command }), h.passed, command)
  }
  assert.deepEqual(h.logs, [])
})

test('over-correction, spawn-prompt and background-call: a runner call carrying every clause passes', async () => {
  const h = harness({ agent_guard: 'deny' })
  assert.deepEqual(missingClauses(GOOD_PROMPT), [])
  assert.equal(await h.run('tool.call', agentCall()), h.passed)
})

test('over-correction, runner-stop: a finished runner and a repeated stop pass', async () => {
  const h = harness({ agent_guard: 'deny' })
  await h.spawnRunner('a1')
  const finished = 'Done.\nTASK_STATUS: COMPLETE\nTASK_ID: T-01'
  assert.equal(await h.run('classic.SubagentStop', { agent_id: 'a1', agent_type: RUNNER, stop_hook_active: false, last_assistant_message: finished }), h.passed)
  assert.equal(
    await h.run('classic.SubagentStop', { agent_id: 'a1', agent_type: RUNNER, stop_hook_active: true, last_assistant_message: 'Let me check:' }),
    h.passed,
  )
})

// --- review-fix controls ---

test('runner-stop: a runner that reports its SendMessage delivery passes; a mid-action stop blocks', async () => {
  const h = harness({ agent_guard: 'deny' })
  await h.spawnRunner('a1')
  for (const message of [
    'Status block sent via SendMessage to main.\nNow I\'ll stop here.',
    'Status block sent.\nNow I\'ll stop here.',
  ]) {
    assert.equal(
      await h.run('classic.SubagentStop', { agent_id: 'a1', agent_type: RUNNER, stop_hook_active: false, last_assistant_message: message }),
      h.passed,
      message,
    )
  }
  assert.deepEqual(
    await h.run('classic.SubagentStop', { agent_id: 'a1', agent_type: RUNNER, stop_hook_active: false, last_assistant_message: 'Step 3 ran.\nLet me check the output:' }),
    { block: RESUME_DIRECTIVE },
  )
  // A dispatch-voice reply that promises a later SendMessage is not a delivery.
  assert.equal(looksUnfinished("I've dispatched the task-runner and I'll report back by SendMessage."), true)
})

test('Bash-verb: a here-document body is not a command, and a subshell cd is denied', async () => {
  const h = harness({ agent_guard: 'deny' })
  await h.spawnRunner('a1')
  const heredoc = "python - <<'EOF'\nrows = load()\nhead = rows[:5]\nprint('it's done')\ncat = 1\nEOF"
  for (const command of [heredoc, 'git show HEAD:f.md | cat -A', 'git status', 'tee out.txt <<-EOF\n\tcd /x\n\tEOF']) {
    assert.equal(await h.run('tool.call', { tool: 'Bash', agentId: 'a1', command }), h.passed, command)
  }
  const sub = (await h.run('tool.call', { tool: 'Bash', agentId: 'a1', command: '(cd repo && cat f)' })) as { deny?: string }
  assert.equal(typeof sub.deny, 'string')
  assert.ok(sub.deny!.includes('cd'), `cd not named in: ${sub.deny}`)
  assert.deepEqual(bareVerbs('(cd repo && cat f)'), ['cd', 'cat'])
  assert.deepEqual(bareVerbs('{ head -3 a.md; }'), ['head'])
  // Uncertain parse under-blocks: an unclosed quote or an unterminated here-document reports nothing.
  assert.deepEqual(bareVerbs("cat 'a.md"), [])
  assert.deepEqual(bareVerbs("python - <<'EOF'\nhead = 1"), [])
  // A command after the here-document still counts.
  assert.deepEqual(bareVerbs("python - <<'EOF'\nx = 1\nEOF\ncat a.md"), ['cat'])
})

test('runner-stop: a workflow agent typed as the runner never counts, even mid-action', async () => {
  const h = harness({ agent_guard: 'deny' })
  await h.run('agent.spawn', { subagentType: RUNNER, prompt: READER_PROMPT, workflow: { runId: 'wf_1', agentIndex: 1 } }, () => ({ model: 'm', agentId: 'w1' }))
  const result = await h.run('classic.SubagentStop', {
    agent_id: 'w1', agent_type: RUNNER, stop_hook_active: false, last_assistant_message: 'Let me check the output:',
  })
  assert.equal(result, h.passed)
  assert.deepEqual(h.logs, [])
})

// --- throw control ---

test('throw: a failed hook logs its kind and lets the call proceed', () => {
  for (const name of ['tool.call', 'agent.spawn', 'classic.SubagentStop']) {
    const h = harness({ agent_guard: 'deny' })
    assert.equal(h.caught(name, { kind: 'throw', message: 'boom' }, false), 'replayed', name)
    assert.ok(h.logs.some((l) => l.includes('throw: boom')), name)
    assert.ok(!h.logs.some((l) => l.includes('[object Object]')), name)
  }
})

// --- malformed-event controls ---

test('malformed: a missing prompt, run_in_background, command or last message lets the call proceed', async () => {
  const h = harness({ agent_guard: 'deny' })
  await h.spawnRunner('a1')
  assert.equal(await h.run('tool.call', { tool: 'Agent', subagent_type: RUNNER }), h.passed)
  assert.equal(await h.run('tool.call', { tool: 'Bash', agentId: 'a1' }), h.passed)
  assert.equal(await h.run('classic.SubagentStop', { agent_id: 'a1', agent_type: RUNNER }), h.passed)
  assert.deepEqual(h.logs, [])
})

// --- config-key controls ---

test('config key: absent, report or an unknown value reports and does not deny', async () => {
  for (const options of [{}, { agent_guard: 'report' }, { agent_guard: 'DENY' }, { agent_guard: true }]) {
    const h = harness(options)
    await h.spawnRunner('a1')
    assert.equal(await h.run('tool.call', agentCall({ run_in_background: true })), h.passed)
    assert.equal(await h.run('tool.call', { tool: 'Bash', agentId: 'a1', command: 'cat a.md' }), h.passed)
    assert.equal(
      await h.run('classic.SubagentStop', { agent_id: 'a1', agent_type: RUNNER, stop_hook_active: false, last_assistant_message: 'Now I will run the tests:' }),
      h.passed,
    )
    assert.equal(h.logs.filter((l) => l.startsWith('agent guard (report):')).length, 3, JSON.stringify(options))
  }
  assert.equal(modeOf(undefined), 'report')
  assert.equal(modeOf({ agent_guard: 'deny' }), 'deny')
})

// --- refusal-text control ---

test('refusal text: a deny carries the reason the model reads as the error result', async () => {
  const h = harness({ agent_guard: 'deny' })
  await h.spawnRunner('a1')
  const bg = (await h.run('tool.call', agentCall({ run_in_background: true }))) as { deny: string }
  assert.match(bg.deny, /^agent guard: .*run_in_background: true.*foreground/)
  const bash = (await h.run('tool.call', { tool: 'Bash', agentId: 'a1', command: 'head -5 a.md' })) as { deny: string }
  assert.match(bash.deny, /^agent guard: head in command position; use Read, Grep or Glob/)
})

// --- pure helpers ---

test('helpers: bareVerbs and looksUnfinished', () => {
  assert.deepEqual(bareVerbs('FOO=1 find . -name x'), ['find'])
  assert.deepEqual(bareVerbs("awk -F'|' '{print $1}' a.txt"), ['awk'])
  assert.deepEqual(bareVerbs('git log | tail -3'), [])
  assert.deepEqual(bareVerbs(undefined), [])
  assert.equal(looksUnfinished('All steps ran.'), false)
  assert.equal(looksUnfinished(''), false)
  assert.equal(looksUnfinished('Step 4 is next. Let me write the handler'), false)
  assert.equal(looksUnfinished('Step 4 is next.\nLet me write the handler'), true)
})
