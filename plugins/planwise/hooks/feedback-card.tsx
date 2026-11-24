// The review card above the prompt, composed into the one hooks module (register.ts). When the
// draft_feedback tool admits a draft, or session start finds a queued draft from an earlier
// session (draft-feedback.ts), the card offers Review, Post and Dismiss. Dismiss hides the draft
// for this session only: the file stays queued, so the next session offers it again. A post or a
// discard made by another session clears the card here too: each draw checks the draft file on
// disk, at most once every five seconds (draftIsOffered). It holds one
// ui.render hook and no session.start hook. The values it shows live in `$.state` under the name
// `planwise`, declared by types/index.d.ts. A render hook cannot write state, so every write
// happens in a button press.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On, PluginOptions } from 'claude-code'

import { clearIfSame, fitTitle, isStalePress, kindLabel, previewLines, previewRows, shouldAskTurnOff } from './feedback/card-preview.ts'
import { findConfig } from './feedback/config-read.ts'
import { draftStillOffered } from './feedback/live.ts'
import { PYTHON_CANDIDATES } from './feedback/names.ts'
import { liveConfigPath, pressPost } from './feedback/post-press.ts'
import { failureText } from './loop/boundary.ts'
import { skillNameOf } from './loop/reentry.ts'

// The state scan reads an atom only when it is written in this file, so the five atoms sit here.
/** The draft the card offers, or null when no draft is waiting. */
const lastDraft = atom({ plugin: 'planwise', key: 'lastDraft' } as const, null)
/** How many drafts this session admitted. The card yields after the third. */
const cardsShown = atom({ plugin: 'planwise', key: 'cardsShown' } as const, 0)
/** How many times the person dismissed a card this session. */
const dismissals = atom({ plugin: 'planwise', key: 'dismissals' } as const, 0)
/** True once the person turned drafting off from the card. */
const hidden = atom({ plugin: 'planwise', key: 'hidden' } as const, false)
/** True while a Post press runs the post script. A second press during that time does nothing. */
const posting = atom({ plugin: 'planwise', key: 'posting' } as const, false)

/** The card shows for the first three admitted drafts of a session. */
const MAX_CARDS = 3

/** The button row draws as `1: Review  2: Post  0: Dismiss`. Below this width it could wrap. */
const MIN_COLUMNS = 30

/** The card's frame: a rounded border on all four sides, plus one column of padding inside each side. */
const FRAME_ROWS = 2
const FRAME_COLUMNS = 4

/** The frame and title color. A theme key, so it follows the person's theme: lilac on the dark theme. */
const ACCENT = 'permission'

/** The badge on the card's first row, drawn in inverse accent. It is cut at the edge, never wrapped. */
const BADGE = ' Planwise Plugin for Claude Code '
/** The badge row plus the blank row under it. */
const BADGE_ROWS = 2

/**
 * The closure table over `$`. It sits at module scope because the validator refuses a `$` handed
 * to a nested function. Every engine call the card makes is spelled here, one per member.
 */
export function hostOf($: EngineInterface) {
  return {
    resolve: <E extends Parameters<EngineInterface['ui']['resolve']>[0]>(e: E) => $.ui.resolve(e),
    listCommands: () => $.command.list(),
    runCommand: (command: string, args: string) => $.command.run({ command, args }),
    ask: (question: string, options: readonly string[]) => $.ui.ask(question, options),
    run: (argv: readonly string[], init?: { timeoutMs?: number }) => (init === undefined ? $.process.run(argv) : $.process.run(argv, init)),
    pluginRoot: () => $.plugin.root,
    // The four calls the config search makes at press time. See currentConfigOf.
    root: () => $.session.root(),
    exists: (path: string) => $.fs.exists(path),
    fsRead: (path: string) => $.fs.read(path),
    fsList: (path: string) => $.fs.list(path),
    uiLog: (text: string, to: 'debug' | 'transcript') => $.ui.log(text, { to }),
    readLast: () => read($, lastDraft),
    readShown: () => read($, cardsShown),
    readHidden: () => read($, hidden),
    readPosting: () => read($, posting),
    setPosting: (value: boolean) => update($, posting, () => value),
    clearLast: (draftId: string | null) => update($, lastDraft, (current) => clearIfSame(current, draftId)),
    bumpDismissals: () => update($, dismissals, (n) => n + 1),
    hide: () => update($, hidden, () => true),
  }
}

export type CardHost = ReturnType<typeof hostOf>

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/** How long one disk check of the card's draft stays valid. A render can run many times a second. */
const LIVE_WINDOW_MS = 5000

/**
 * The last disk check of the card's draft. A render hook cannot write state, so module memory
 * holds it. It resets with the process, and a new draft id misses it.
 */
const lastCheck = { draftId: '', at: 0, live: true }

/**
 * True while the draft on the card can still be posted. Another session may have posted it since
 * this session drew the card, and only the disk shows that. The check reads the drafts folder at
 * most once per window, and any failure keeps the card (see draftStillOffered).
 */
const draftIsOffered = async (host: CardHost, draft: { draftId: string; feedbackDir: string }): Promise<boolean> => {
  const now = Date.now()
  if (lastCheck.draftId === draft.draftId && now - lastCheck.at < LIVE_WINDOW_MS) return lastCheck.live
  const live = await draftStillOffered({ list: host.fsList, read: host.fsRead }, draft.feedbackDir, draft.draftId)
  lastCheck.draftId = draft.draftId
  lastCheck.at = now
  lastCheck.live = live
  return live
}

/**
 * The config path under the session's current root, or an empty string when the root holds none.
 * The session root moves when the session enters or leaves a git worktree, so a press reads it
 * fresh. The card's stored path can name a worktree that was removed since.
 */
const currentConfigOf = async (host: CardHost): Promise<string> => {
  const found = await findConfig({ exists: host.exists, read: host.fsRead, list: host.fsList }, await host.root())
  return found === null ? '' : found.dir + '/config.yaml'
}

/**
 * Runs one planwise subcommand through the skill, then spends the card. A rejected run keeps it.
 * The card is spent only while it still holds the draft that was pressed (`pressedId`), so a
 * newer draft that arrived during the run keeps its card.
 */
const runAndSpend = async (host: CardHost, args: string, pressedId: string | null): Promise<void> => {
  const skill = skillNameOf(await host.listCommands())
  if (skill === null) {
    host.uiLog('draft feedback: no planwise skill found; the card cannot run it', 'transcript')
    return
  }
  try {
    await host.runCommand(skill, args)
  } catch (err) {
    host.uiLog('draft feedback: card command rejected: ' + errText(err), 'transcript')
    return
  }
  await host.clearLast(pressedId)
}

/** Button 1: list the queued drafts. */
const onReview = async (host: CardHost): Promise<void> => {
  const draft = await host.readLast()
  await runAndSpend(host, 'feedback --drafts', draft === null ? null : draft.draftId)
}

/**
 * Button 2: post the card's draft with no model turn. The id is read fresh from the atom at press
 * time. When the post script reports that the draft's config file is gone, the press runs it again
 * with the current root's config. The skill route is the fallback for when no python could start.
 */
const onPost = async (host: CardHost): Promise<void> => {
  const draft = await host.readLast()
  await pressPost({ ...host, currentConfig: () => currentConfigOf(host), fallback: (draftId: string) => runAndSpend(host, 'feedback --post ' + draftId, draftId) }, draft)
}

/**
 * Runs the helper's `disable-drafts` command, which splices and re-parses the config before it
 * writes. It tries each interpreter name in turn and moves on only when the run rejects. The
 * card hides only on exit 0. Any other result writes nothing, logs one debug line, and counts as Keep.
 */
const turnOff = async (host: CardHost, configPath: string): Promise<void> => {
  let result: { exitCode: number; stderr: string } | null = null
  let lastError: unknown = null
  for (const python of PYTHON_CANDIDATES) {
    try {
      result = await host.run([python, host.pluginRoot() + '/scripts/feedback_drafts.py', 'disable-drafts', '--config', configPath])
      break
    } catch (err) {
      lastError = err
    }
  }
  if (result === null) {
    host.uiLog('draft feedback: no python could start; drafts stay on: ' + errText(lastError), 'debug')
    return
  }
  if (result.exitCode !== 0) {
    host.uiLog('draft feedback: disable-drafts exit ' + String(result.exitCode) + '; drafts stay on: ' + result.stderr, 'debug')
    return
  }
  await host.hide()
  host.uiLog('draft feedback: feedback.drafts set to off in ' + configPath + '; takes effect next session', 'transcript')
}

/**
 * Button 0: dismiss the card. The second dismissal offers to turn drafting off. The turn-off writes
 * the current root's config, or the draft's own config when that root holds none (liveConfigPath).
 * A stale press does nothing.
 */
const onDismiss = async (host: CardHost): Promise<void> => {
  const draft = await host.readLast()
  if (isStalePress(draft)) return
  await host.clearLast(draft.draftId)
  const count = await host.bumpDismissals()
  if (!shouldAskTurnOff(count, draft.configPath)) return
  // Only the second dismissal reaches the file system. No reachable config means no question.
  const configPath = await liveConfigPath({ exists: host.exists, currentConfig: () => currentConfigOf(host) }, draft.configPath)
  if (configPath === '') return
  let answer = 'Keep'
  try {
    answer = await host.ask('Turn off Claude-drafted feedback for this project?', ['Keep', 'Turn off'])
  } catch (err) {
    host.uiLog('draft feedback: turn-off ask not answered; keeping drafts on: ' + errText(err), 'debug')
  }
  if (answer !== 'Turn off') return
  await turnOff(host, configPath)
}

/** Registers the card's one ui.render hook. */
export function register(on: On, options: PluginOptions) {
  void options

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const host = hostOf($)
    // Read every value first: each read subscribes the drawing, so a later write redraws it.
    const draft = await host.readLast()
    const isHidden = await host.readHidden()
    const shown = await host.readShown()
    const isPosting = await host.readPosting()
    if (e.props.hasSurvey || e.props.isWorking) return next(e)
    if (draft === null || isHidden || shown > MAX_CARDS) return next(e)
    // The frame and the badge take their rows and columns first; the content gets what is left.
    const contentRows = e.props.maxRows - FRAME_ROWS - BADGE_ROWS
    const columns = e.props.bodyColumns - FRAME_COLUMNS
    if (contentRows < 4 || columns < MIN_COLUMNS) return next(e)
    // The disk read comes last, after every guard that skips the card, so it runs only when a card would draw.
    if (!(await draftIsOffered(host, draft))) return next(e)

    const { Box, Button, Text } = host.resolve(e)
    const rows = previewLines(draft.preview, columns, previewRows(contentRows))
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={ACCENT} paddingX={1}>
        <Box marginBottom={1}>
          <Text bold inverse color={ACCENT} wrap="truncate-end">{BADGE}</Text>
        </Box>
        <Text bold color={ACCENT}>{fitTitle(kindLabel(draft.kind), draft.title, columns)}</Text>
        {rows.map((line, i) => (
          <Text key={String(i)}>{line}</Text>
        ))}
        {isPosting ? (
          <Box marginTop={1}>
            <Text color={ACCENT}>Posting…</Text>
          </Box>
        ) : (
          <Box gap={2} marginTop={1}>
            <Button key="review" label="Review" hotkey="1" plain onPress={() => void onReview(host).catch((err: unknown) => host.uiLog('draft feedback: review press failed: ' + errText(err), 'debug'))} />
            <Button key="post" label="Post" hotkey="2" plain onPress={() => void onPost(host).catch((err: unknown) => host.uiLog('draft feedback: post press failed: ' + errText(err), 'debug'))} />
            <Button key="dismiss" label="Dismiss" hotkey="0" plain role="dismiss" onPress={() => void onDismiss(host).catch((err: unknown) => host.uiLog('draft feedback: dismiss press failed: ' + errText(err), 'debug'))} />
          </Box>
        )}
      </Box>
    )
  }).catch(($, e, next) => {
    hostOf($).uiLog('draft feedback: card render failed: ' + failureText(next.error), 'debug')
    return next(e)
  })
}
