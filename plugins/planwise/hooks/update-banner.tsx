// The update card above the prompt, composed into the one hooks module (register.ts) after the
// feedback card, so the feedback card is the outer hook and one card draws at a time. The
// session-start check (update-check.ts) writes the offer. The card offers Update Later, Update
// Now and Dismiss. Later and Dismiss hide it for this session only and write nothing to the
// store. The press logic lives in update-check.ts, where node tests can load it.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On, PluginOptions } from 'claude-code'

import { failureText } from './loop/boundary.ts'
import type { PressHost } from './update-check.ts'
import { buttonsOf, cardLines, pressUpdateNow, rowsNeeded } from './update-check.ts'
import type { PlanwiseUpdateOffer } from '../types'

// The state scan reads an atom only when it is written in this file, so the three atoms sit here.
/** The verdict the card offers, or null when no card is due. */
const updateOffer = atom({ plugin: 'planwise', key: 'updateOffer' } as const, null)
/** True once the person pressed Update Later or Dismiss. Session only. */
const updateHidden = atom({ plugin: 'planwise', key: 'updateHidden' } as const, false)
/** True while an Update Now press runs. A second press during that time does nothing. */
const updateBusy = atom({ plugin: 'planwise', key: 'updateBusy' } as const, false)

/** The button row draws as `1: Update Later  2: Update Now  0: Dismiss`. Below this width it could wrap. */
const MIN_COLUMNS = 44

/** The card's frame: a rounded border on all four sides, plus one column of padding inside each side. */
const FRAME_ROWS = 2
const FRAME_COLUMNS = 4

/** The frame and title color. A theme key, so it follows the person's theme. */
const ACCENT = 'permission'

/** The badge on the card's first row, drawn in inverse accent. It is cut at the edge, never wrapped. */
const BADGE = ' Planwise Plugin for Claude Code '
/** The badge row plus the blank row under it. */
const BADGE_ROWS = 2

/** The button row plus the blank row above it. */
const BUTTON_ROWS = 2

/**
 * The closure table over `$`. It sits at module scope because the validator refuses a `$` handed
 * to a nested function. Every engine call the card makes is spelled here, one per member.
 */
export function hostOf($: EngineInterface) {
  return {
    resolve: <E extends Parameters<EngineInterface['ui']['resolve']>[0]>(e: E) => $.ui.resolve(e),
    now: () => $.clock.now(),
    pluginRoot: () => $.plugin.root,
    projectRoot: () => $.session.root(),
    run: (argv: readonly string[], init: { timeoutMs: number }) => $.process.run(argv, init),
    storeGet: (key: string) => $.store.get(key),
    storeSet: (key: string, value: unknown) => $.store.set(key, value),
    listCommands: () => $.command.list(),
    runCommand: (command: string, args?: string) => (args === undefined ? $.command.run({ command }) : $.command.run({ command, args })),
    uiLog: (text: string, to: 'debug' | 'transcript') => $.ui.log(text, { to }),
    readOffer: () => read($, updateOffer),
    readHidden: () => read($, updateHidden),
    readBusy: () => read($, updateBusy),
    setOffer: (offer: PlanwiseUpdateOffer | null) => update($, updateOffer, () => offer),
    setBusy: (value: boolean) => update($, updateBusy, () => value),
    hide: () => update($, updateHidden, () => true),
  }
}

export type BannerHost = ReturnType<typeof hostOf>

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/** Buttons 1 and 0: hide the card for this session. Nothing is written to the store. */
const onHide = async (host: BannerHost): Promise<void> => {
  await host.hide()
}

/** Registers the card's one ui.render hook. */
export function register(on: On, options: PluginOptions) {
  void options

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const host = hostOf($)
    // Read every value first: each read subscribes the drawing, so a later write redraws it.
    const offer = await host.readOffer()
    const isHidden = await host.readHidden()
    const isBusy = await host.readBusy()
    if (e.props.hasSurvey || e.props.isWorking) return next(e)
    if (offer === null || isHidden) return next(e)
    // The frame and the badge take their rows and columns first; the content gets what is left.
    const contentRows = e.props.maxRows - FRAME_ROWS - BADGE_ROWS
    const columns = e.props.bodyColumns - FRAME_COLUMNS
    if (columns < MIN_COLUMNS) return next(e)
    const lines = cardLines(offer)
    if (contentRows < rowsNeeded(lines, columns) + BUTTON_ROWS) return next(e)

    const { Box, Button, Text } = host.resolve(e)
    const buttons = buttonsOf(offer.verdict)
    const press: PressHost = host
    const logFail = (what: string) => (err: unknown) => host.uiLog('update check: ' + what + ' press failed: ' + errText(err), 'debug')
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={ACCENT} paddingX={1}>
        <Box marginBottom={1}>
          <Text bold inverse color={ACCENT} wrap="truncate-end">{BADGE}</Text>
        </Box>
        <Text bold color={ACCENT}>{lines[0] ?? ''}</Text>
        {lines.slice(1).map((line, i) => (
          <Text key={String(i)}>{line}</Text>
        ))}
        {isBusy ? (
          <Box marginTop={1}>
            <Text color={ACCENT}>Updating…</Text>
          </Box>
        ) : (
          <Box gap={2} marginTop={1}>
            {buttons.later ? <Button key="later" label="Update Later" hotkey="1" plain onPress={() => void onHide(host).catch(logFail('later'))} /> : null}
            {buttons.now !== null ? <Button key="now" label={buttons.now} hotkey="2" plain onPress={() => void pressUpdateNow(press).catch(logFail('update'))} /> : null}
            <Button key="dismiss" label="Dismiss" hotkey="0" plain role="dismiss" onPress={() => void onHide(host).catch(logFail('dismiss'))} />
          </Box>
        )}
      </Box>
    )
  }).catch(($, e, next) => {
    hostOf($).uiLog('update check: card render failed: ' + failureText(next.error), 'debug')
    return next(e)
  })
}
