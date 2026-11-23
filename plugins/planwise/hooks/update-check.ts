// The session-start update check, composed into the one hooks module (register.ts). The
// session.start hook only arms a timer. The timer body runs scripts/update_check.py, refreshes
// the cached latest release from GitHub at most once per 6 hours, reads the pending-upgrade
// marker in `$.store`, and either starts `/planwise upgrade` or hands the verdict to the card
// (update-banner.tsx) through the `updateOffer` state value. The card's press logic also lives
// here, because node can load this file and cannot load a .tsx file. The module launches python
// only; the script finds the CLI itself.
import type { CommandInfo, EngineInterface, HttpInit, HttpResponse, PluginOptions, Timer } from 'claude-code'

import { PYTHON_CANDIDATES } from './feedback/names.ts'
import { skillNameOf } from './loop/reentry.ts'
import { compareVersions, latestRelease } from './update/tags.ts'
import type { PlanwiseUpdateOffer } from '../types'

/** The userConfig option that turns the check off (`off`) or keeps it from the network (`offline`). */
export const OPTION_KEY = 'update_check'

/** The `$.store` key of the release cache: `{ checkedAt, latest, etag }`. */
export const CACHE_KEY = 'updateCheck'

/** The `$.store` key of the pending-upgrade marker: `{ [projectRoot]: { target, writtenAt } }`. */
export const PENDING_KEY = 'pendingUpgrade'

/** The release cache is refreshed when it is older than this: 6 hours. */
export const CACHE_TTL_MS = 6 * 60 * 60 * 1000

/** The limit on one `update_check.py check` run. */
export const CHECK_TIMEOUT_MS = 30000

/** The limit on one `update_check.py update` run, which updates the marketplace and the plugin. */
export const UPDATE_TIMEOUT_MS = 300000

/**
 * The delay before a redraw request. On CLI 2.1.330 a card answered while the terminal was still
 * drawing its start screen was not shown until a later redraw (a typed prompt). A fresh draw once
 * the start screen settles puts the card on the screen.
 */
export const REDRAW_MS = 1500

/** The skill arguments that migrate the project to the running plugin. */
export const UPGRADE_ARGS = 'upgrade'

/** The built-in command that reloads plugins in the running session. */
export const RELOAD_COMMAND = 'reload-plugins'

export type OptOut = 'on' | 'offline' | 'off'

/** The fields of `update_check.py check` output that the module reads. */
export type CheckResult = {
  verdict: string
  running: string | null
  installed: string | null
  latest: string | null
  pin: string | null
  repo: string | null
}

export type ReleaseCache = { checkedAt: number; latest: string | null; etag: string | null }

export type PendingEntry = { target: string; writtenAt: number }

export type RunResult = { exitCode: number; stdout: string; stderr: string }

/** The engine calls the timer body makes. */
export type Host = {
  after: (ms: number, fn: () => void) => Timer
  now: () => Promise<number>
  pluginRoot: () => string
  projectRoot: () => Promise<string>
  run: (argv: readonly string[], init: { timeoutMs: number }) => Promise<RunResult>
  fetch: (url: string, init: HttpInit) => Promise<HttpResponse>
  storeGet: (key: string) => Promise<unknown>
  storeSet: (key: string, value: unknown) => Promise<void>
  listCommands: () => Promise<CommandInfo[]>
  runCommand: (command: string, args?: string) => Promise<unknown>
  setOffer: (offer: PlanwiseUpdateOffer | null) => Promise<unknown>
  uiLog: (text: string, to: 'debug' | 'transcript') => void
  /** Asks the engine for a fresh draw of every render hook. */
  redraw: () => void
}

/** The engine calls a card press makes. update-banner.tsx builds it over its own atoms. */
export type PressHost = Omit<Host, 'after' | 'fetch' | 'redraw'> & {
  readOffer: () => Promise<PlanwiseUpdateOffer | null>
  readBusy: () => Promise<boolean>
  setBusy: (value: boolean) => Promise<unknown>
}

/**
 * The closure table over `$`. It sits at module scope because the validator refuses a `$` handed
 * to a nested function. Every engine call the timer body makes is spelled here, one per member.
 */
export function hostOf($: EngineInterface): Host {
  return {
    after: (ms: number, fn: () => void) => $.clock.after(ms, fn),
    now: () => $.clock.now(),
    pluginRoot: () => $.plugin.root,
    projectRoot: () => $.session.root(),
    run: (argv: readonly string[], init: { timeoutMs: number }) => $.process.run(argv, init),
    fetch: (url: string, init: HttpInit) => $.http.fetch(url, init),
    storeGet: (key: string) => $.store.get(key),
    storeSet: (key: string, value: unknown) => $.store.set(key, value),
    listCommands: () => $.command.list(),
    runCommand: (command: string, args?: string) => (args === undefined ? $.command.run({ command }) : $.command.run({ command, args })),
    // The card declares the atom. A literal ref, as `$.state` requires.
    setOffer: (offer: PlanwiseUpdateOffer | null) => $.state.set({ plugin: 'planwise', key: 'updateOffer' } as const, offer),
    uiLog: (text: string, to: 'debug' | 'transcript') => $.ui.log(text, { to }),
    redraw: () => $.ui.invalidate('ui.render'),
  }
}

/** Arms one redraw request. A failure is debug-logged; the card then draws at the next redraw. */
const nudge = (host: Pick<Host, 'after' | 'redraw' | 'uiLog'>): void => {
  try {
    host.after(REDRAW_MS, () => {
      try {
        host.redraw()
      } catch (err) {
        host.uiLog('update check: redraw failed: ' + (err instanceof Error ? err.message : String(err)), 'debug')
      }
    })
  } catch (err) {
    host.uiLog('update check: redraw not armed: ' + (err instanceof Error ? err.message : String(err)), 'debug')
  }
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err))

const debug = (host: Pick<Host, 'uiLog'>, text: string): void => host.uiLog('update check: ' + text, 'debug')

/** Forward slashes and no trailing separator, so two spellings of one root give one marker key. */
export const slashed = (path: string): string => path.replace(/\\/g, '/').replace(/\/+$/, '')

/** The opt-out value. An unset option reads as `on`: a declared default may not reach the module. */
export const optOutOf = (value: unknown): OptOut => (value === 'off' || value === 'offline' ? value : 'on')

const textOrNull = (value: unknown): string | null => (typeof value === 'string' && value !== '' ? value : null)

/** The last non-empty line of a script's stdout, parsed as a JSON object, or `null`. */
export const parseJsonLine = (stdout: string): Record<string, unknown> | null => {
  const line = stdout
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l !== '')
    .pop()
  if (line === undefined) return null
  try {
    const parsed: unknown = JSON.parse(line)
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/** The `check` fields the module reads, or `null` when the output is not a check result. */
export const checkResultOf = (stdout: string): CheckResult | null => {
  const parsed = parseJsonLine(stdout)
  if (parsed === null) return null
  const verdict = parsed['verdict']
  if (typeof verdict !== 'string') return null
  return {
    verdict,
    running: textOrNull(parsed['running']),
    installed: textOrNull(parsed['installed']),
    latest: textOrNull(parsed['latest']),
    pin: textOrNull(parsed['pin']),
    repo: textOrNull(parsed['repo']),
  }
}

/** The release cache, or `null` when the stored value has another shape. */
export const cacheOf = (value: unknown): ReleaseCache | null => {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  const checkedAt = record['checkedAt']
  if (typeof checkedAt !== 'number' || !Number.isFinite(checkedAt)) return null
  return { checkedAt, latest: textOrNull(record['latest']), etag: textOrNull(record['etag']) }
}

/** True while the cache is younger than the TTL. A cache dated in the future counts as stale. */
export const isFresh = (cache: ReleaseCache | null, now: number): boolean =>
  cache !== null && now >= cache.checkedAt && now - cache.checkedAt < CACHE_TTL_MS

/** A GitHub `owner/name`, checked before it goes into a URL. */
const REPO_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/

export const releasesUrl = (repo: string): string => 'https://api.github.com/repos/' + repo + '/releases?per_page=30'

/** The marker map, keeping only well-formed entries. */
export const pendingMapOf = (value: unknown): Record<string, PendingEntry> => {
  const out: Record<string, PendingEntry> = {}
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return out
  for (const [key, entry] of Object.entries(value as Record<string, unknown>)) {
    if (typeof entry !== 'object' || entry === null) continue
    const target = (entry as Record<string, unknown>)['target']
    const writtenAt = (entry as Record<string, unknown>)['writtenAt']
    if (typeof target === 'string' && target !== '' && typeof writtenAt === 'number') out[key] = { target, writtenAt }
  }
  return out
}

/**
 * True when a marker can no longer mean "this project waits for the upgrade to `target`". A
 * store key outlives an uninstall, so an entry whose target is older than the running plugin is
 * left over from an earlier install. An entry equal to the running version is the one the
 * auto-upgrade needs, so it is not stale. An unknown running version keeps the entry.
 */
export const markerIsStale = (entry: PendingEntry, running: string | null): boolean =>
  running !== null && compareVersions(entry.target, running) < 0

/** The card offer for a verdict, or `null` for a verdict that draws no card. */
export const offerOf = (check: CheckResult): PlanwiseUpdateOffer | null => {
  const verdict = check.verdict
  if (verdict !== 'RESTART' && verdict !== 'PLUGIN_BEHIND' && verdict !== 'PROJECT_BEHIND') return null
  return { verdict, running: check.running, installed: check.installed, latest: check.latest, pin: check.pin, confirmCommand: null, declaredCommand: null }
}

/**
 * Runs `scripts/update_check.py` with each interpreter name in turn, moving on only when the
 * launch rejects. Returns `null` when no python could start.
 */
export const runScript = async (host: Pick<Host, 'run' | 'pluginRoot' | 'uiLog'>, args: readonly string[], timeoutMs: number): Promise<RunResult | null> => {
  let lastError: unknown = null
  for (const python of PYTHON_CANDIDATES) {
    try {
      return await host.run([python, '-B', host.pluginRoot() + '/scripts/update_check.py', ...args], { timeoutMs })
    } catch (err) {
      lastError = err
    }
  }
  debug(host, 'no python could start: ' + errText(lastError))
  return null
}

/** One `check` run. Every failure logs at debug level and returns `null`. */
const runCheck = async (host: Host, projectRoot: string, latest: string | null): Promise<CheckResult | null> => {
  const args = ['check', '--running-root', host.pluginRoot(), '--project-root', projectRoot]
  if (latest !== null) args.push('--latest', latest)
  const result = await runScript(host, args, CHECK_TIMEOUT_MS)
  if (result === null) return null
  if (result.exitCode !== 0) {
    debug(host, 'check exit ' + String(result.exitCode) + ': ' + result.stderr.trim())
    return null
  }
  const check = checkResultOf(result.stdout)
  if (check === null) debug(host, 'check printed no verdict')
  return check
}

/**
 * The latest release version, from the cache while it is fresh, else from GitHub with
 * `If-None-Match`. A 304 keeps the cached value and re-dates it. A failure keeps the cache,
 * logs at debug level and returns the cached value. With `mayFetch` false, only the cache is read.
 */
export const refreshLatest = async (host: Host, repo: string, mayFetch: boolean): Promise<string | null> => {
  const cache = cacheOf(await host.storeGet(CACHE_KEY))
  const now = await host.now()
  if (!mayFetch || isFresh(cache, now)) return cache === null ? null : cache.latest
  if (!REPO_RE.test(repo)) {
    debug(host, 'repo ' + repo + ' is not owner/name; no fetch')
    return cache === null ? null : cache.latest
  }
  const headers: Record<string, string> = { accept: 'application/vnd.github+json' }
  if (cache !== null && cache.etag !== null) headers['if-none-match'] = cache.etag
  let response: HttpResponse
  try {
    response = await host.fetch(releasesUrl(repo), { method: 'GET', headers })
  } catch (err) {
    debug(host, 'release fetch failed: ' + errText(err))
    return cache === null ? null : cache.latest
  }
  if (response.status === 304 && cache !== null) {
    await host.storeSet(CACHE_KEY, { checkedAt: now, latest: cache.latest, etag: cache.etag })
    return cache.latest
  }
  if (!response.ok) {
    debug(host, 'release fetch status ' + String(response.status))
    return cache === null ? null : cache.latest
  }
  let latest: string | null
  try {
    latest = latestRelease(JSON.parse(response.text))
  } catch (err) {
    debug(host, 'release list did not parse: ' + errText(err))
    return cache === null ? null : cache.latest
  }
  await host.storeSet(CACHE_KEY, { checkedAt: now, latest, etag: textOrNull(response.headers['etag']) })
  return latest
}

/**
 * Starts `/planwise upgrade` from the timer. A rejected run is an expected outcome right after a
 * plugin update: it logs at debug level, keeps the marker, and the card offers the upgrade.
 */
export const autoUpgrade = async (host: Host, check: CheckResult): Promise<void> => {
  const skill = skillNameOf(await host.listCommands())
  if (skill === null) {
    debug(host, 'no planwise skill found; showing the card instead of the auto-upgrade')
    await host.setOffer(offerOf(check))
    return
  }
  await host.setOffer(null)
  try {
    await host.runCommand(skill, UPGRADE_ARGS)
    debug(host, 'auto-upgrade ran')
  } catch (err) {
    debug(host, 'auto-upgrade rejected; keeping the marker and showing the card: ' + errText(err))
    await host.setOffer(offerOf(check))
  }
}

/**
 * The timer body. Every failure logs at debug level and draws no card.
 */
export async function checkNow(host: Host, options: PluginOptions): Promise<void> {
  const optOut = optOutOf(options[OPTION_KEY])
  if (optOut === 'off') {
    debug(host, 'update_check is off')
    return
  }
  const projectRoot = slashed(await host.projectRoot())
  const first = await runCheck(host, projectRoot, null)
  if (first === null) return
  let check = first
  if (first.repo !== null) {
    const latest = await refreshLatest(host, first.repo, optOut === 'on')
    if (latest !== null) {
      const second = await runCheck(host, projectRoot, latest)
      if (second !== null) check = second
    }
  }
  const pending = pendingMapOf(await host.storeGet(PENDING_KEY))
  let entry = pending[projectRoot] ?? null
  if (entry !== null && markerIsStale(entry, check.running)) {
    debug(host, 'clearing a stale upgrade marker for ' + entry.target)
    delete pending[projectRoot]
    await host.storeSet(PENDING_KEY, pending)
    entry = null
  }
  if (entry !== null && check.verdict === 'PROJECT_BEHIND') {
    await autoUpgrade(host, check)
    return
  }
  if (entry !== null && check.verdict === 'CURRENT') {
    delete pending[projectRoot]
    await host.storeSet(PENDING_KEY, pending)
  }
  const offer = offerOf(check)
  await host.setOffer(offer)
  // The offer can land while the terminal still draws its start screen: ask for a fresh draw.
  if (offer !== null) nudge(host)
}

/**
 * The session.start body. It returns at once when not interactive. Otherwise it arms one timer
 * and returns: `session.start` holds the first prompt, and `$.command.run` rejects inside it.
 * It never throws.
 */
export function onSessionStart(host: Host, isInteractive: boolean, options: PluginOptions): void {
  if (!isInteractive) return
  try {
    host.after(0, () => {
      void checkNow(host, options).catch((err: unknown) => debug(host, 'timer body failed: ' + errText(err)))
    })
  } catch (err) {
    debug(host, 'timer not armed: ' + errText(err))
  }
  // A review card set during session.start (a queued draft) meets the same start-screen draw.
  nudge(host)
}

/** Update Now on `PROJECT_BEHIND`: run the upgrade. A rejected run keeps any marker and the card. */
const pressProjectUpgrade = async (host: PressHost): Promise<void> => {
  const skill = skillNameOf(await host.listCommands())
  if (skill === null) {
    host.uiLog('update check: no planwise skill found; run /planwise upgrade', 'transcript')
    return
  }
  try {
    await host.runCommand(skill, UPGRADE_ARGS)
  } catch (err) {
    host.uiLog('update check: upgrade rejected: ' + errText(err), 'transcript')
    return
  }
  await host.setOffer(null)
}

/**
 * Update Now on `PLUGIN_BEHIND`: run `update_check.py update`. On `UPDATED` write the marker and
 * switch the card to `RESTART`. On `NEEDS_CONFIRM` show the declared command and the terminal command
 * that lets the person accept it.
 */
const pressPluginUpdate = async (host: PressHost, offer: PlanwiseUpdateOffer): Promise<void> => {
  const projectRoot = slashed(await host.projectRoot())
  const result = await runScript(host, ['update', '--running-root', host.pluginRoot(), '--project-root', projectRoot], UPDATE_TIMEOUT_MS)
  if (result === null) {
    host.uiLog('update check: no python could start; the plugin was not updated', 'transcript')
    return
  }
  const parsed = parseJsonLine(result.stdout)
  const outcome = parsed === null ? null : parsed['result']
  if (result.exitCode === 0 && outcome === 'UPDATED') {
    if (offer.latest !== null) {
      const pending = pendingMapOf(await host.storeGet(PENDING_KEY))
      pending[projectRoot] = { target: offer.latest, writtenAt: await host.now() }
      await host.storeSet(PENDING_KEY, pending)
    }
    await host.setOffer({ ...offer, verdict: 'RESTART', installed: offer.latest ?? offer.installed })
    return
  }
  if (result.exitCode === 3 && outcome === 'NEEDS_CONFIRM') {
    // `command` is the marketplace's declared command, for the person to review. `retry` is the
    // terminal command that lets the CLI ask. The CLI ignores acceptance inside a Claude Code session.
    await host.setOffer({
      ...offer,
      verdict: 'NEEDS_CONFIRM',
      confirmCommand: parsed === null ? null : textOrNull(parsed['retry']),
      declaredCommand: parsed === null ? null : textOrNull(parsed['command']),
    })
    return
  }
  const detail = parsed === null ? result.stderr.trim() : String(parsed['detail'] ?? '')
  host.uiLog('update check: plugin update failed (exit ' + String(result.exitCode) + '): ' + detail, 'transcript')
}

/** Button 2 on `RESTART`: reload plugins. The reload re-runs session.start, which re-checks. */
export const pressReload = async (host: PressHost): Promise<void> => {
  try {
    await host.runCommand(RELOAD_COMMAND)
  } catch (err) {
    host.uiLog('update check: reload rejected; restart Claude Code instead: ' + errText(err), 'transcript')
  }
}

/** Button 2 on `PROJECT_BEHIND` or `PLUGIN_BEHIND`. The offer is read fresh, and a press while busy does nothing. */
export const pressUpdateNow = async (host: PressHost): Promise<void> => {
  if (await host.readBusy()) return
  const offer = await host.readOffer()
  if (offer === null) return
  if (offer.verdict === 'RESTART') return pressReload(host)
  if (offer.verdict !== 'PROJECT_BEHIND' && offer.verdict !== 'PLUGIN_BEHIND') return
  await host.setBusy(true)
  try {
    if (offer.verdict === 'PROJECT_BEHIND') await pressProjectUpgrade(host)
    else await pressPluginUpdate(host, offer)
  } finally {
    await host.setBusy(false)
  }
}

/** The card's text lines for an offer. */
export const cardLines = (offer: PlanwiseUpdateOffer): string[] => {
  const v = (value: string | null): string => value ?? 'unknown'
  switch (offer.verdict) {
    case 'RESTART':
      return ['Planwise ' + v(offer.installed) + ' is installed. Reload plugins or restart Claude Code to load it. The project upgrade then runs on its own.']
    case 'PLUGIN_BEHIND':
      return ['Planwise ' + v(offer.latest) + ' is available. You have ' + v(offer.running) + '.']
    case 'PROJECT_BEHIND':
      return ['Planwise ' + v(offer.running) + ' is installed, but this project is set up for ' + v(offer.pin) + '.']
    case 'NEEDS_CONFIRM':
      return [
        'Planwise ' + v(offer.latest) + ' needs you to accept a command that its marketplace declares: ' + v(offer.declaredCommand) + '. Run this in a terminal, then restart:',
        offer.confirmCommand ?? '/plugin',
      ]
  }
}

/** Which buttons the card draws besides `0: Dismiss`: `later` for `1`, and the label of `2` or null. */
export const buttonsOf = (verdict: PlanwiseUpdateOffer['verdict']): { later: boolean; now: string | null } => {
  if (verdict === 'PROJECT_BEHIND' || verdict === 'PLUGIN_BEHIND') return { later: true, now: 'Update Now' }
  if (verdict === 'RESTART') return { later: false, now: 'Reload' }
  return { later: false, now: null }
}

/** The rows the text lines take at a width, wrapped. */
export const rowsNeeded = (lines: readonly string[], columns: number): number =>
  lines.reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / Math.max(1, columns))), 0)
