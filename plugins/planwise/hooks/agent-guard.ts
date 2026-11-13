// Dispatch guard for planwise task-runners. Four checks, each scoped to a planwise:task-runner:
//
// - spawn-prompt: an Agent call for planwise:task-runner whose prompt lacks a runner clause
//   (references/agent-orchestration-delegated.md §1.8; Part-3 §1.23, §1.27.1, §1.29.1).
//   Always report-only: the shipped handlers/run.md spawn does not carry every clause yet.
// - background-call: an Agent call for planwise:task-runner with run_in_background: true
//   (references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md §1.21).
// - runner-stop: a planwise:task-runner that stops with no status block and an ending that looks
//   unfinished: a dispatch-voice reply, or a last line cut mid-action (Part-2 §1.17.1). A missing
//   status block alone never counts, and a message reporting the block sent by SendMessage
//   passes. It cannot see the working tree, so the clean-tree signal of that section is not
//   checked here.
// - Bash-verb: a Bash call made inside a planwise:task-runner that runs a bare `cd`, or a
//   file-tree read verb (cat, head, tail, sed -n, awk, find, ls -R) in command position, not fed
//   by a pipe (references/native-tool-use.md, Forbidden Verbs for File Operations). A
//   here-document body is not a command, and a command the parser cannot read passes.
//
// Config key: the plugin option `agent_guard`, read from register()'s options.
//   absent, or any value but "deny"  -> report-only: log one line and let the call proceed.
//   "deny"                           -> refuse a background-call or Bash-verb call with { deny },
//                                       and block a runner-stop with a resume directive.
// The spawn-prompt check reports at every value.
//
// Scope: nothing fires outside a planwise:task-runner. Another plugin's Agent call, a workflow
// agent() spawn and a Bash call outside a runner pass untouched. Every handler fails open: its
// .catch logs the failure and passes the call on, as the module's other handlers do.
import type { On, PluginOptions } from 'claude-code'

import { failureText } from './loop/boundary.ts'

export const RUNNER = 'planwise:task-runner'
export const OPTION_KEY = 'agent_guard'

export type Mode = 'report' | 'deny'

/** The option value, as a mode. Anything but "deny" reports. */
export function modeOf(options: PluginOptions | undefined): Mode {
  return options !== undefined && options[OPTION_KEY] === 'deny' ? 'deny' : 'report'
}

/** The runner clauses a spawn prompt must hold, each matched literally. */
export const CLAUSES: readonly string[] = [
  'You are dispatched to execute ONE task:',
  '## HARD CONSTRAINTS',
  'Execute ONLY',
  '## SCOPE BOUNDARY',
  'SendMessage',
  'Do NOT proceed to task',
  'FOREGROUND',
]

/** The clauses `prompt` lacks, in CLAUSES order. A prompt that is not a string lacks none. */
export function missingClauses(prompt: unknown): string[] {
  if (typeof prompt !== 'string') return []
  return CLAUSES.filter((c) => !prompt.includes(c))
}

const READ_VERBS = new Set(['cat', 'head', 'tail', 'awk', 'find'])

// A here-document operator: `<<WORD`, `<<-WORD`, `<<'WORD'` or `<<"WORD"`. `<<<` is a here-string.
const HEREDOC = /^<<(-?)[ \t]*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\2/

/**
 * Splits a command into its stages: the outer list is the sequence, the inner one the pipes.
 * A here-document body is skipped, not split. Returns null when the command cannot be parsed
 * with confidence (an unclosed quote, or a here-document with no closing line), so the caller
 * under-blocks rather than over-blocks.
 */
function stagesOf(command: string): string[][] | null {
  const seqs: string[][] = [[]]
  let cur = ''
  let quote: string | null = null
  const pending: { word: string; tabs: boolean }[] = []
  const push = () => {
    seqs[seqs.length - 1]!.push(cur)
    cur = ''
  }
  for (let i = 0; i < command.length; i++) {
    const ch = command[i]!
    if (quote !== null) {
      if (quote === '"' && ch === '\\') {
        cur += ch + (command[i + 1] ?? '')
        i++
        continue
      }
      if (ch === quote) quote = null
      cur += ch
    } else if (ch === '\\') {
      cur += ch + (command[i + 1] ?? '')
      i++
    } else if (ch === "'" || ch === '"') {
      quote = ch
      cur += ch
    } else if (ch === '<' && command[i + 1] === '<' && command[i + 2] !== '<') {
      const m = HEREDOC.exec(command.slice(i))
      if (m === null) {
        cur += ch
        continue
      }
      pending.push({ word: m[3]!, tabs: m[1] === '-' })
      cur += m[0]
      i += m[0].length - 1
    } else if ((ch === '&' || ch === '|') && command[i + 1] === ch) {
      push()
      seqs.push([])
      i++
    } else if (ch === ';' || ch === '\n') {
      push()
      seqs.push([])
      if (ch === '\n' && pending.length > 0) {
        // Skip each pending here-document body, through its closing line.
        let pos = i + 1
        for (const doc of pending) {
          for (;;) {
            if (pos >= command.length) return null
            const end = command.indexOf('\n', pos)
            const line = (end === -1 ? command.slice(pos) : command.slice(pos, end)).replace(/\r$/, '')
            pos = end === -1 ? command.length : end + 1
            if ((doc.tabs ? line.replace(/^\t+/, '') : line) === doc.word) break
          }
        }
        pending.length = 0
        i = pos - 1
      }
    } else if (ch === '|') {
      push()
    } else {
      cur += ch
    }
  }
  if (quote !== null || pending.length > 0) return null
  push()
  return seqs
}

/** The words of one stage: a leading subshell `(` or group `{` and VAR=value assignments dropped. */
function wordsOf(stage: string): string[] {
  const words = stage.trim().replace(/^[({\s]+/, '').split(/\s+/).filter((w) => w.length > 0)
  while (words.length > 0 && /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[0]!)) words.shift()
  return words
}

/**
 * The verbs of `command` the Bash-verb check reports, in order. A pipe-fed stage never counts,
 * and a command the parser cannot read with confidence reports nothing.
 */
export function bareVerbs(command: unknown): string[] {
  if (typeof command !== 'string') return []
  const seqs = stagesOf(command)
  if (seqs === null) return []
  const found: string[] = []
  for (const seq of seqs) {
    const words = wordsOf(seq[0] ?? '')
    const verb = words[0]
    if (verb === undefined) continue
    if (verb === 'cd') found.push('cd')
    else if (READ_VERBS.has(verb)) found.push(verb)
    else if (verb === 'sed' && words.includes('-n')) found.push('sed -n')
    else if (verb === 'ls' && words.some((w) => /^-[A-Za-z]*R/.test(w))) found.push('ls -R')
  }
  return found
}

// A message that reports the status block delivered: a runner told to send it by SendMessage
// often ends with no TASK_STATUS line of its own.
const DELIVERED = /\b(?:SendMessage|status block)\b/i
const DELIVERY_VERB = /\b(?:sent|delivered|called)\b/i
// A closing line that names the end of the work, not a next action.
const TERMINAL = /^(?:Now,? )?(?:I'll|I will|let me) (?:stop|end|finish|wrap up|return|hand (?:back|off))\b/i

/**
 * True when a runner's last message looks unfinished. An absent message is not judged, and the
 * absence of a status block alone never counts: the message needs a positive sign, a
 * dispatch-voice reply or a last line cut mid-action. A message that reports the status block
 * delivered is finished.
 */
export function looksUnfinished(message: unknown): boolean {
  if (typeof message !== 'string' || message.trim() === '') return false
  if (message.includes('TASK_STATUS:') || message.includes('BRIEF COLLISION')) return false
  const text = message.trim()
  if (DELIVERED.test(text) && DELIVERY_VERB.test(text)) return false
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== '')
  const last = lines[lines.length - 1]!.trim()
  const dispatchVoice = /\bI(?:'ve| have) (?:dispatched|launched|spawned)\b|\bI'll report back\b/i.test(text)
  if (dispatchVoice) return true
  if (TERMINAL.test(last)) return false
  return last.endsWith(':') || /^(?:Let me|Now (?:let me|I'll|I will)|Next,? I'll)\b/i.test(last)
}

export const RESUME_DIRECTIVE =
  'You stopped before your task finished: no status block, and your last message reads as unfinished. ' +
  'Resume the task yourself, with your own tool calls. Do not dispatch another agent.'

type Host = { log: (text: string) => void }

export function register(on: On, options: PluginOptions) {
  const mode = modeOf(options)
  // Agent ids started as planwise:task-runner by the Agent tool. A workflow agent() is never one.
  const runners = new Set<string>()

  const hostOf = ($: { ui: { log: (text: string) => void } }): Host => ({ log: (text: string) => $.ui.log(text) })
  const failed = (host: Host, where: string, why: string): void => {
    host.log(`agent guard: ${where} failed: ${why}`)
  }

  on('agent.spawn', async ($, e, next) => {
    const answer = await next(e)
    if (e.subagentType === RUNNER && e.workflow === undefined && 'agentId' in answer && typeof answer.agentId === 'string') {
      runners.add(answer.agentId)
    }
    return answer
  }).catch(($, e, next) => {
    failed(hostOf($), 'agent.spawn hook', failureText(next.error))
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const host = hostOf($)
    if (e.tool === 'Agent' && e['subagent_type'] === RUNNER) {
      const missing = missingClauses(e['prompt'])
      if (missing.length > 0) host.log(`agent guard (report): a ${RUNNER} spawn prompt lacks: ${missing.join('; ')}`)
      if (e['run_in_background'] === true) {
        const why = `a ${RUNNER} call sets run_in_background: true; dispatch it in the foreground (run_in_background: false)`
        if (mode === 'deny') return { deny: `agent guard: ${why}` }
        host.log(`agent guard (report): ${why}`)
      }
      return next(e)
    }
    if (e.tool === 'Bash' && e.agentId !== undefined && runners.has(e.agentId)) {
      const verbs = bareVerbs(e['command'])
      if (verbs.length > 0) {
        const why = `${verbs.join(', ')} in command position; use Read, Grep or Glob for files, and absolute paths instead of cd`
        if (mode === 'deny') return { deny: `agent guard: ${why}` }
        host.log(`agent guard (report): ${why}`)
      }
    }
    return next(e)
  }).catch(($, e, next) => {
    failed(hostOf($), 'tool.call hook', failureText(next.error))
    return next(e)
  })

  on('classic.SubagentStop', async ($, e, next) => {
    // Only an id recorded from a non-workflow spawn counts. The stop event carries no workflow
    // marker, so its agent_type alone would also match a workflow agent typed as the runner.
    const isRunner = runners.has(e.agent_id)
    if (!isRunner || e.stop_hook_active === true || !looksUnfinished(e.last_assistant_message)) return next(e)
    if (mode === 'deny') return { block: RESUME_DIRECTIVE }
    hostOf($).log(`agent guard (report): a ${RUNNER} stopped and looks unfinished`)
    return next(e)
  }).catch(($, e, next) => {
    failed(hostOf($), 'classic.SubagentStop hook', failureText(next.error))
    return next(e)
  })
}
