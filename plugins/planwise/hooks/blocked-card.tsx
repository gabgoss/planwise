// The blocked-post banner above the prompt, composed into the one hooks module (register.ts) after
// the feedback card, so a waiting draft card keeps the band and the banner draws when it passes.
// It says how many drafts the privacy check kept from posting. register.ts recounts at each session
// start and each main-loop turn end. The card offers Review and Dismiss. The count, the dismiss and
// the size guard live in feedback/blocked.ts, where node tests can load them.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On, PluginOptions } from 'claude-code'

import { FRAME_ROWS, MIN_CONTENT_ROWS, bannerText, pressDismiss, shouldShowBanner } from './feedback/blocked.ts'
import type { BlockedHost, BlockedState } from './feedback/blocked.ts'
import { failureText } from './loop/boundary.ts'
import { skillNameOf } from './loop/reentry.ts'

// The state scan reads an atom only when it is written in this file, so the atom sits here.
/** What the banner draws from, or null before the first count. */
const blocked = atom({ plugin: 'planwise', key: 'blocked' } as const, null)

/** The frame and title color. A theme key, so it follows the person's theme. */
const ACCENT = 'permission'

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

/**
 * The closure table over `$`. It sits at module scope because the validator refuses a `$` handed
 * to a nested function. Every engine call the render hook makes is spelled here, one per member.
 */
function hostOf($: EngineInterface) {
  return {
    resolve: <E extends Parameters<EngineInterface['ui']['resolve']>[0]>(e: E) => $.ui.resolve(e),
    listCommands: () => $.command.list(),
    runCommand: (command: string, args: string) => $.command.run({ command, args }),
    uiLog: (text: string, to: 'debug' | 'transcript') => $.ui.log(text, { to }),
    readBlocked: () => read($, blocked),
  }
}

type CardHost = ReturnType<typeof hostOf>

/** The table the count and the dismiss run through. register.ts builds one for each recount. */
export function blockedHostOf($: EngineInterface): BlockedHost {
  return {
    run: (argv: readonly string[], init?: { timeoutMs?: number }) => (init === undefined ? $.process.run(argv) : $.process.run(argv, init)),
    uiLog: (text: string, to: 'debug' | 'transcript') => $.ui.log(text, { to }),
    pluginRoot: () => $.plugin.root,
    exists: (path: string) => $.fs.exists(path),
    // The write returns a promise, so its failure is caught here and not by the caller.
    setBlocked: (state: BlockedState) =>
      void update($, blocked, () => state).catch((err: unknown) => $.ui.log('draft feedback: the blocked banner state write failed: ' + errText(err), { to: 'debug' })),
  }
}

/** Button 1: list the drafts and their state. The banner stays until the person dismisses it. */
const onReview = async (host: CardHost): Promise<void> => {
  const skill = skillNameOf(await host.listCommands())
  if (skill === null) {
    host.uiLog('draft feedback: no planwise skill found; the banner cannot run it', 'transcript')
    return
  }
  try {
    await host.runCommand(skill, 'feedback --status')
  } catch (err) {
    host.uiLog('draft feedback: banner command rejected: ' + errText(err), 'transcript')
  }
}

/** Registers the banner's one ui.render hook. */
export function register(on: On, options: PluginOptions) {
  void options

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const host = hostOf($)
    // Read first: the read subscribes the drawing, so a later write redraws it.
    const state = await host.readBlocked()
    if (state === null || !shouldShowBanner(state, e.props)) return next(e)

    const { Box, Button, Text } = host.resolve(e)
    const press = blockedHostOf($)
    const logFail = (what: string) => (err: unknown) => host.uiLog('draft feedback: blocked banner ' + what + ' press failed: ' + errText(err), 'debug')
    // The count ends the line, so a narrow band wraps it when a second text row fits.
    const wrap = e.props.maxRows - FRAME_ROWS > MIN_CONTENT_ROWS ? 'wrap' : 'truncate-end'
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={ACCENT} paddingX={1}>
        <Text bold color={ACCENT} wrap={wrap}>{bannerText(state.count)}</Text>
        <Box gap={2}>
          <Button key="review" label="Review" hotkey="1" plain onPress={() => void onReview(host).catch(logFail('review'))} />
          <Button key="dismiss" label="Dismiss" hotkey="0" plain role="dismiss" onPress={() => void pressDismiss(press, state.feedbackDir).catch(logFail('dismiss'))} />
        </Box>
      </Box>
    )
  }).catch(($, e, next) => {
    hostOf($).uiLog('draft feedback: blocked banner render failed: ' + failureText(next.error), 'debug')
    return next(e)
  })
}
