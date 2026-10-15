// The review card above the prompt, composed into the one hooks module (register.ts). When the
// draft_feedback tool admits a draft, the card offers Review, Post and Dismiss. It holds one
// ui.render hook and no session.start hook. The values it shows live in `$.state` under the name
// `planwise`, declared by types/index.d.ts. A render hook cannot write state, so every write
// happens in a button press.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On, PluginOptions } from 'claude-code'

import { clearIfSame, fitTitle, isStalePress, kindLabel, previewLines, previewRows, shouldAskTurnOff } from './feedback/card-preview.ts'
import { PYTHON_CANDIDATES } from './feedback/names.ts'
import { failureText } from './loop/boundary.ts'
import { skillNameOf } from './loop/reentry.ts'

// The state scan reads an atom only when it is written in this file, so the four atoms sit here.
/** The draft the card offers, or null when no draft is waiting. */
const lastDraft = atom({ plugin: 'planwise', key: 'lastDraft' } as const, null)
/** How many drafts this session admitted. The card yields after the third. */
const cardsShown = atom({ plugin: 'planwise', key: 'cardsShown' } as const, 0)
/** How many times the person dismissed a card this session. */
const dismissals = atom({ plugin: 'planwise', key: 'dismissals' } as const, 0)
/** True once the person turned drafting off from the card. */
const hidden = atom({ plugin: 'planwise', key: 'hidden' } as const, false)

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
const BADGE_ROWS = 1

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
    run: (argv: readonly string[]) => $.process.run(argv),
    pluginRoot: () => $.plugin.root,
    uiLog: (text: string, to: 'debug' | 'transcript') => $.ui.log(text, { to }),
    readLast: () => read($, lastDraft),
    readShown: () => read($, cardsShown),
    readHidden: () => read($, hidden),
    clearLast: (draftId: string | null) => update($, lastDraft, (current) => clearIfSame(current, draftId)),
    bumpDismissals: () => update($, dismissals, (n) => n + 1),
    hide: () => update($, hidden, () => true),
  }
}

export type CardHost = ReturnType<typeof hostOf>

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

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

/** Button 2: post the card's draft. The id is read fresh from the atom at press time. */
const onPost = async (host: CardHost): Promise<void> => {
  const draft = await host.readLast()
  if (isStalePress(draft)) return
  await runAndSpend(host, 'feedback --post ' + draft.draftId, draft.draftId)
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
  host.uiLog('draft feedback: feedback.drafts set to off in config.yaml; takes effect next session', 'transcript')
}

/** Button 0: dismiss the card. The second dismissal offers to turn drafting off. A stale press does nothing. */
const onDismiss = async (host: CardHost): Promise<void> => {
  const draft = await host.readLast()
  if (isStalePress(draft)) return
  await host.clearLast(draft.draftId)
  const count = await host.bumpDismissals()
  if (!shouldAskTurnOff(count, draft.configPath)) return
  let answer = 'Keep'
  try {
    answer = await host.ask('Turn off Claude-drafted feedback for this project?', ['Keep', 'Turn off'])
  } catch (err) {
    host.uiLog('draft feedback: turn-off ask not answered; keeping drafts on: ' + errText(err), 'debug')
  }
  if (answer !== 'Turn off') return
  await turnOff(host, draft.configPath)
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
    if (e.props.hasSurvey || e.props.isWorking) return next(e)
    if (draft === null || isHidden || shown > MAX_CARDS) return next(e)
    // The frame and the badge take their rows and columns first; the content gets what is left.
    const contentRows = e.props.maxRows - FRAME_ROWS - BADGE_ROWS
    const columns = e.props.bodyColumns - FRAME_COLUMNS
    if (contentRows < 4 || columns < MIN_COLUMNS) return next(e)

    const { Box, Button, Text } = host.resolve(e)
    const rows = previewLines(draft.preview, columns, previewRows(contentRows))
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={ACCENT} paddingX={1}>
        <Text bold inverse color={ACCENT} wrap="truncate-end">{BADGE}</Text>
        <Text bold color={ACCENT}>{fitTitle(kindLabel(draft.kind), draft.title, columns)}</Text>
        {rows.map((line, i) => (
          <Text key={String(i)}>{line}</Text>
        ))}
        <Box gap={2} marginTop={1}>
          <Button key="review" label="Review" hotkey="1" plain onPress={() => void onReview(host).catch((err: unknown) => host.uiLog('draft feedback: review press failed: ' + errText(err), 'debug'))} />
          <Button key="post" label="Post" hotkey="2" plain onPress={() => void onPost(host).catch((err: unknown) => host.uiLog('draft feedback: post press failed: ' + errText(err), 'debug'))} />
          <Button key="dismiss" label="Dismiss" hotkey="0" plain role="dismiss" onPress={() => void onDismiss(host).catch((err: unknown) => host.uiLog('draft feedback: dismiss press failed: ' + errText(err), 'debug'))} />
        </Box>
      </Box>
    )
  }).catch(($, e, next) => {
    hostOf($).uiLog('draft feedback: card render failed: ' + failureText(next.error), 'debug')
    return next(e)
  })
}
