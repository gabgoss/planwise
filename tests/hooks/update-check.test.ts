import { test } from 'node:test'
import assert from 'node:assert/strict'
import { register as registerLoader } from 'node:module'

// update-check.ts imports the engine's `claude-code` module for types only, and feedback/names.ts and
// loop/reentry.ts may value-import it. This loader hook resolves it to a stub, as draft-feedback.test.ts does.
const stubUrl = (source: string): string => 'data:text/javascript,' + encodeURIComponent(source)
const loaderSource = `
const stubs = {
  'claude-code': ${JSON.stringify(stubUrl('export const atom = (ref, initial) => ({ ref, initial }); export const read = async () => undefined; export const update = async () => undefined'))},
}
export async function resolve(specifier, context, next) {
  if (specifier === 'claude-code') return { url: stubs['claude-code'], shortCircuit: true }
  return next(specifier, context)
}
`
registerLoader(stubUrl(loaderSource), import.meta.url)

// The module under test. UPDATE_CHECK_URL points the same tests at another copy of the module.
const target = process.env.UPDATE_CHECK_URL ?? new URL('../../plugins/planwise/hooks/update-check.ts', import.meta.url).href
const { onSessionStart, checkNow, pressUpdateNow, cardLines, buttonsOf, CACHE_KEY, PENDING_KEY, CACHE_TTL_MS, REDRAW_MS } = await import(target)

const NOW = 1_700_000_000_000
const ROOT = 'C:\\work\\proj'
const SLASHED = 'C:/work/proj'
const MAIN = 'C:/work/main'
const COMMANDS = [{ name: 'planwise:planwise', source: 'skill', plugin: 'planwise' }]

type Check = { verdict: string; running?: string | null; installed?: string | null; latest?: string | null; pin?: string | null; repo?: string | null; main_root?: string | null }
type Resp = { status: number; ok: boolean; text: string; headers: Record<string, string> }

const okList: Resp = {
  status: 200,
  ok: true,
  text: JSON.stringify([{ tag_name: 'planwise--v1.0.9' }, { tag_name: 'planwise--v1.0.7' }]),
  headers: { etag: 'W/"new"' },
}

/** A fake host: in-memory store, recorded calls, a scripted `check` output and a scripted fetch. */
const world = (
  opts: {
    store?: Record<string, unknown>
    check?: (args: readonly string[]) => Check
    fetch?: () => Promise<Resp>
    runCommand?: () => Promise<unknown>
    update?: { exitCode: number; stdout: string }
    exists?: (path: string) => boolean
  } = {},
) => {
  const store = new Map<string, unknown>(Object.entries(opts.store ?? {}))
  const runs: (readonly string[])[] = []
  const fetches: { url: string; init: { headers?: Record<string, string> } }[] = []
  const commands: { command: string; args?: string }[] = []
  const offers: unknown[] = []
  const storeSets: { key: string; value: unknown }[] = []
  const logs: { text: string; to: string }[] = []
  const timers: { ms: number; fn: () => void }[] = []
  const redraws: number[] = []
  let busy = false
  let offer: unknown = null
  const host = {
    after: (ms: number, fn: () => void) => (timers.push({ ms, fn }), { cancel: () => undefined }),
    now: async () => NOW,
    pluginRoot: () => 'C:/plugins/planwise',
    projectRoot: async () => ROOT,
    exists: async (p: string) => (opts.exists ?? ((q: string) => q === SLASHED || q === MAIN))(p),
    run: async (argv: readonly string[]) => {
      runs.push(argv)
      if (argv.includes('update')) return { exitCode: opts.update?.exitCode ?? 0, stdout: opts.update?.stdout ?? '', stderr: '' }
      const body = (opts.check ?? (() => ({ verdict: 'CURRENT' })))(argv)
      const full = { running: '1.0.8', installed: '1.0.8', latest: null, pin: null, repo: null, ...body }
      return { exitCode: 0, stdout: JSON.stringify(full) + '\n', stderr: '' }
    },
    fetch: async (url: string, init: { headers?: Record<string, string> }) => {
      fetches.push({ url, init })
      return (opts.fetch ?? (async () => okList))()
    },
    storeGet: async (key: string) => store.get(key),
    storeSet: async (key: string, value: unknown) => void (store.set(key, value), storeSets.push({ key, value })),
    listCommands: async () => COMMANDS,
    runCommand: async (command: string, args?: string) => {
      commands.push({ command, args })
      return (opts.runCommand ?? (async () => ({})))()
    },
    setOffer: async (value: unknown) => void (offers.push(value), (offer = value)),
    uiLog: (text: string, to: string) => void logs.push({ text, to }),
    redraw: () => void redraws.push(1),
    readOffer: async () => offer,
    readBusy: async () => busy,
    setBusy: async (value: boolean) => void (busy = value),
  }
  return { host, store, runs, fetches, commands, offers, storeSets, logs, timers, redraws, setOffer: (v: unknown) => void (offer = v) }
}

const checkRuns = (w: ReturnType<typeof world>) => w.runs.filter((a) => a.includes('check'))
const lastOffer = (w: ReturnType<typeof world>) => w.offers[w.offers.length - 1] as { verdict: string } | null
const withRepo = (verdict: string, extra: Partial<Check> = {}) => (args: readonly string[]): Check => ({
  verdict,
  repo: 'gabgoss/planwise',
  latest: args.includes('--latest') ? '1.0.9' : null,
  ...extra,
})

test('1 not interactive arms no timer', () => {
  const w = world()
  onSessionStart(w.host as never, false, {})
  assert.equal(w.timers.length, 0)
  onSessionStart(w.host as never, true, {})
  // The check timer, then one redraw request once the start screen has settled.
  assert.deepEqual(w.timers.map((t) => t.ms), [0, REDRAW_MS])
  w.timers[1]!.fn()
  assert.equal(w.redraws.length, 1)
})

test('1b an offer arms one redraw request; no offer arms none', async () => {
  const behind = world({ check: () => ({ verdict: 'PROJECT_BEHIND', pin: '9.8.0', running: '9.9.0', installed: '9.9.0' }) })
  await checkNow(behind.host as never, { update_check: 'offline' })
  assert.equal(lastOffer(behind)?.verdict, 'PROJECT_BEHIND')
  assert.deepEqual(behind.timers.map((t) => t.ms), [REDRAW_MS])
  behind.timers[0]!.fn()
  assert.equal(behind.redraws.length, 1)

  const current = world()
  await checkNow(current.host as never, { update_check: 'offline' })
  assert.equal(lastOffer(current), null)
  assert.equal(current.timers.length, 0)
})

test('2 opt-out off stops the timer body: no script, no fetch, no offer', async () => {
  const w = world({ check: withRepo('PLUGIN_BEHIND') })
  await checkNow(w.host as never, { update_check: 'off' })
  assert.equal(w.runs.length, 0)
  assert.equal(w.fetches.length, 0)
  assert.equal(w.offers.length, 0)
})

test('3 opt-out offline skips the fetch and still runs check', async () => {
  const w = world({ check: withRepo('PLUGIN_BEHIND') })
  await checkNow(w.host as never, { update_check: 'offline' })
  assert.equal(w.fetches.length, 0)
  assert.equal(checkRuns(w).length, 1)
  assert.equal(lastOffer(w)?.verdict, 'PLUGIN_BEHIND')
})

test('4 a fresh cache skips the fetch and feeds its latest to the second check', async () => {
  const w = world({
    store: { [CACHE_KEY]: { checkedAt: NOW - 1000, latest: '1.0.9', etag: 'e1' } },
    check: withRepo('PLUGIN_BEHIND'),
  })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.equal(w.fetches.length, 0)
  assert.equal(checkRuns(w).length, 2)
  assert.ok(checkRuns(w)[1]!.includes('--latest'))
})

test('5 a stale cache fetches with If-None-Match and stores the result', async () => {
  const w = world({
    store: { [CACHE_KEY]: { checkedAt: NOW - CACHE_TTL_MS - 1, latest: '1.0.7', etag: 'e1' } },
    check: withRepo('PLUGIN_BEHIND'),
  })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.equal(w.fetches.length, 1)
  assert.equal(w.fetches[0]!.url, 'https://api.github.com/repos/gabgoss/planwise/releases?per_page=30')
  assert.equal(w.fetches[0]!.init.headers?.['if-none-match'], 'e1')
  assert.deepEqual(w.store.get(CACHE_KEY), { checkedAt: NOW, latest: '1.0.9', etag: 'W/"new"' })
})

test('6 a 304 keeps the cached latest and etag and re-dates the cache', async () => {
  const w = world({
    store: { [CACHE_KEY]: { checkedAt: NOW - CACHE_TTL_MS - 1, latest: '1.0.9', etag: 'e1' } },
    fetch: async () => ({ status: 304, ok: false, text: '', headers: {} }),
    check: withRepo('PLUGIN_BEHIND'),
  })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.deepEqual(w.store.get(CACHE_KEY), { checkedAt: NOW, latest: '1.0.9', etag: 'e1' })
  assert.equal(checkRuns(w).length, 2)
})

test('7 a fetch failure keeps the cache and still runs the script', async () => {
  const stale = { checkedAt: NOW - CACHE_TTL_MS - 1, latest: '1.0.7', etag: 'e1' }
  const w = world({
    store: { [CACHE_KEY]: stale },
    fetch: async () => Promise.reject(new Error('offline')),
    check: withRepo('PLUGIN_BEHIND'),
  })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.deepEqual(w.store.get(CACHE_KEY), stale)
  assert.equal(w.storeSets.filter((s) => s.key === CACHE_KEY).length, 0)
  assert.ok(checkRuns(w).length >= 1)
  assert.ok(w.logs.some((l) => l.to === 'debug' && l.text.includes('release fetch failed')))
})

test('8 a check result with repo null skips the fetch', async () => {
  const w = world({ check: () => ({ verdict: 'CURRENT', repo: null }) })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.equal(w.fetches.length, 0)
  assert.equal(checkRuns(w).length, 1)
})

test('9 the marker with PROJECT_BEHIND runs the skill with upgrade args and sets no offer', async () => {
  const marker = { target: '1.0.8', writtenAt: 5 }
  const w = world({ store: { [PENDING_KEY]: { [SLASHED]: marker } }, check: () => ({ verdict: 'PROJECT_BEHIND', repo: null, pin: '1.0.5' }) })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.deepEqual(w.commands, [{ command: 'planwise:planwise', args: 'upgrade' }])
  assert.equal(lastOffer(w), null)
  // The entry equals the running version, so it is not stale and survives.
  assert.equal(w.storeSets.filter((s) => s.key === PENDING_KEY).length, 0)
})

test('10 the marker with CURRENT clears the marker, and an older target is cleared as stale', async () => {
  const equal = world({ store: { [PENDING_KEY]: { [SLASHED]: { target: '1.0.8', writtenAt: 5 } } }, check: () => ({ verdict: 'CURRENT', repo: null }) })
  await checkNow(equal.host as never, { update_check: 'on' })
  assert.deepEqual(equal.store.get(PENDING_KEY), {})
  assert.equal(equal.commands.length, 0)

  const old = world({ store: { [PENDING_KEY]: { [SLASHED]: { target: '1.0.5', writtenAt: 5 } } }, check: () => ({ verdict: 'PROJECT_BEHIND', repo: null, pin: '1.0.4' }) })
  await checkNow(old.host as never, { update_check: 'on' })
  assert.deepEqual(old.store.get(PENDING_KEY), {})
  assert.equal(old.commands.length, 0)
  assert.equal(lastOffer(old)?.verdict, 'PROJECT_BEHIND')
})

test('11 with no marker for this project, PROJECT_BEHIND sets the offer and runs nothing', async () => {
  const w = world({ store: { [PENDING_KEY]: { 'C:/other/project': { target: '1.0.8', writtenAt: 5 } } }, check: () => ({ verdict: 'PROJECT_BEHIND', repo: null, pin: '1.0.5' }) })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.equal(w.commands.length, 0)
  assert.equal(lastOffer(w)?.verdict, 'PROJECT_BEHIND')
})

test('12 the marker lives in the store under pendingUpgrade, and no script call gets --data-dir', async () => {
  const w = world({
    update: { exitCode: 0, stdout: JSON.stringify({ result: 'UPDATED' }) + '\n' },
    check: () => ({ verdict: 'CURRENT', repo: null }),
  })
  w.setOffer({ verdict: 'PLUGIN_BEHIND', running: '1.0.7', installed: '1.0.7', latest: '1.0.9', pin: null, confirmCommand: null, declaredCommand: null })
  await pressUpdateNow(w.host as never)
  assert.equal(PENDING_KEY, 'pendingUpgrade')
  const written = w.store.get(PENDING_KEY) as Record<string, { target: string }>
  assert.equal(written[SLASHED]?.target, '1.0.9')
  assert.equal(lastOffer(w)?.verdict, 'RESTART')
  await checkNow(w.host as never, { update_check: 'off' })
  const w2 = world({ check: () => ({ verdict: 'CURRENT' }) })
  await checkNow(w2.host as never, { update_check: 'on' })
  for (const argv of [...w.runs, ...w2.runs]) assert.ok(!argv.includes('--data-dir'))
})

test('13 a rejected auto-upgrade run keeps the marker, logs, and sets the PROJECT_BEHIND offer', async () => {
  const marker = { target: '1.0.8', writtenAt: 5 }
  const w = world({
    store: { [PENDING_KEY]: { [SLASHED]: marker } },
    check: () => ({ verdict: 'PROJECT_BEHIND', repo: null, pin: '1.0.5' }),
    runCommand: async () => Promise.reject(new Error('no command named /planwise:planwise in this session')),
  })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.equal(w.commands.length, 1)
  assert.deepEqual((w.store.get(PENDING_KEY) as Record<string, unknown>)[SLASHED], marker)
  assert.equal(lastOffer(w)?.verdict, 'PROJECT_BEHIND')
  assert.ok(w.logs.some((l) => l.to === 'debug' && l.text.includes('auto-upgrade rejected')))
})

test('15 a refused update shows the declared command and the terminal command, and writes no marker', async () => {
  // The script's report for a marketplace-declared command that needs a person to accept it.
  const refusal = { result: 'NEEDS_CONFIRM', command: 'python', retry: 'claude plugin update planwise@planwise-marketplace --scope project' }
  const w = world({
    update: { exitCode: 3, stdout: JSON.stringify(refusal) + '\n' },
    check: () => ({ verdict: 'CURRENT', repo: null }),
  })
  const offer = { verdict: 'PLUGIN_BEHIND', running: '1.0.7', installed: '1.0.7', latest: '1.0.9', pin: null, confirmCommand: null, declaredCommand: null }
  w.setOffer(offer)
  await pressUpdateNow(w.host as never)
  const shown = lastOffer(w) as typeof offer
  assert.equal(shown.verdict, 'NEEDS_CONFIRM')
  assert.equal(shown.declaredCommand, 'python')
  assert.equal(shown.confirmCommand, refusal.retry)
  assert.equal(w.storeSets.filter((s) => s.key === PENDING_KEY).length, 0)
  const lines = cardLines(shown) as string[]
  assert.ok(lines[0]!.includes('python') && lines[0]!.includes('1.0.9'))
  assert.equal(lines[1], refusal.retry)
  // No update button remains, because the CLI ignores acceptance inside a Claude Code session.
  assert.deepEqual(buttonsOf('NEEDS_CONFIRM'), { later: false, now: null })
})

test('15b exit 3 without a readable NEEDS_CONFIRM result is a failed update and leaves the offer alone', async () => {
  const w = world({ update: { exitCode: 3, stdout: 'not json\n' }, check: () => ({ verdict: 'CURRENT', repo: null }) })
  w.setOffer({ verdict: 'PLUGIN_BEHIND', running: '1.0.7', installed: '1.0.7', latest: '1.0.9', pin: null, confirmCommand: null, declaredCommand: null })
  await pressUpdateNow(w.host as never)
  assert.equal(w.offers.length, 0)
  assert.ok(w.logs.some((l) => l.to === 'transcript' && l.text.includes('plugin update failed (exit 3)')))
})

test('16 a pending entry whose root no longer exists is pruned on the next check', async () => {
  const marker = { target: '1.0.8', writtenAt: 5 }
  // PROJECT_BEHIND keeps this project's own entry (case 9), so the store shows only the prune.
  const w = world({ store: { [PENDING_KEY]: { [SLASHED]: marker, 'C:/gone/wt': marker } }, check: () => ({ verdict: 'PROJECT_BEHIND', repo: null, pin: '1.0.5' }) })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.deepEqual(w.store.get(PENDING_KEY), { [SLASHED]: marker })
  assert.equal(w.storeSets.filter((s) => s.key === PENDING_KEY).length, 1)
})

test('17 a worktree session finds the marker stored under its main root and runs the upgrade', async () => {
  const marker = { target: '1.0.8', writtenAt: 5 }
  const w = world({
    store: { [PENDING_KEY]: { [MAIN]: marker } },
    check: () => ({ verdict: 'PROJECT_BEHIND', repo: null, pin: '1.0.5', main_root: MAIN }),
  })
  await checkNow(w.host as never, { update_check: 'on' })
  assert.deepEqual(w.commands, [{ command: 'planwise:planwise', args: 'upgrade' }])
  assert.equal(lastOffer(w), null)
})

test('18 a press from a worktree writes the marker under main_root', async () => {
  const w = world({
    update: { exitCode: 0, stdout: JSON.stringify({ result: 'UPDATED', main_root: MAIN }) + '\n' },
    check: () => ({ verdict: 'CURRENT', repo: null }),
  })
  w.setOffer({ verdict: 'PLUGIN_BEHIND', running: '1.0.7', installed: '1.0.7', latest: '1.0.9', pin: null, confirmCommand: null, declaredCommand: null })
  await pressUpdateNow(w.host as never)
  const written = w.store.get(PENDING_KEY) as Record<string, { target: string }>
  assert.equal(written[MAIN]?.target, '1.0.9')
  assert.equal(written[SLASHED], undefined)
})

test('14 an unset update_check behaves as on: a stale cache fetches', async () => {
  const w = world({ check: withRepo('PLUGIN_BEHIND') })
  await checkNow(w.host as never, {})
  assert.equal(w.fetches.length, 1)
  assert.equal(checkRuns(w).length, 2)
  assert.equal(lastOffer(w)?.verdict, 'PLUGIN_BEHIND')
})
