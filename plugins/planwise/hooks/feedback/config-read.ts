// A minimal reader for the three scalars the feedback tool needs from config.yaml.
// It handles a two-level indented scalar, such as `feedback.drafts`. It is not a
// YAML parser. Only `findConfig` and `mainCheckoutDir` read files, and only through
// the table they are handed.

/** Which feedback.drafts values the tool understands. */
export type DraftsMode = 'notify' | 'quiet' | 'off'

/** Cut a trailing `#` comment, ignoring a `#` inside quotes or glued to a word. */
const stripComment = (text: string): string => {
  let quote = ''
  for (let i = 0; i < text.length; i++) {
    const ch = text.charAt(i)
    if (quote !== '') {
      if (ch === quote) quote = ''
    } else if (ch === '"' || ch === "'") {
      quote = ch
    } else if (ch === '#' && (i === 0 || /\s/.test(text.charAt(i - 1)))) {
      return text.slice(0, i).trim()
    }
  }
  return text.trim()
}

/**
 * Read a two-level scalar and keep its quotes. The comment is stripped.
 *
 * @param yaml the config text
 * @param path the parent key and the child key, such as `['feedback', 'drafts']`
 * @returns the raw scalar text, or undefined when the key is absent
 */
export const readRawScalar = (yaml: string, path: readonly string[]): string | undefined => {
  const [parent, child] = path
  if (parent === undefined || child === undefined) return undefined
  let inParent = false
  for (const line of yaml.split(/\r?\n/)) {
    if (line.trim() === '' || line.trimStart().startsWith('#')) continue
    const indented = /^\s/.test(line)
    if (!indented) {
      const m = /^([A-Za-z0-9_-]+):\s*(?:#.*)?$/.exec(line)
      inParent = m !== null && m[1] === parent
      continue
    }
    if (!inParent) continue
    const m = /^\s+([A-Za-z0-9_-]+):(?:\s+(.*))?$/.exec(line)
    if (m !== null && m[1] === child) return stripComment(m[2] ?? '')
  }
  return undefined
}

/**
 * Read a two-level scalar with its quotes stripped.
 *
 * @param yaml the config text
 * @param path the parent key and the child key
 * @returns the scalar text, or undefined when the key is absent
 */
export const readScalar = (yaml: string, path: readonly string[]): string | undefined => {
  const raw = readRawScalar(yaml, path)
  if (raw === undefined) return undefined
  const m = /^(["'])(.*)\1$/.exec(raw)
  return m !== null ? (m[2] ?? '') : raw
}

/**
 * True when the text is a planwise config, not a foreign file that shares the name. It mirrors
 * the Python loader's test: a top-level `project:` key, with an optional comment after it.
 *
 * @param text the config text
 * @returns whether the text carries the planwise marker
 */
export const isPlanwiseConfig = (text: string): boolean =>
  /^project:[ \t]*(#.*)?$/m.test(text.replace(/^﻿/, '').replace(/\r\n/g, '\n'))

/** The three file calls the config search makes. The caller builds the table from its engine. */
export type ConfigFs = {
  exists: (path: string) => Promise<boolean>
  read: (path: string) => Promise<unknown>
  list: (path: string) => Promise<{ name: string; kind: string }[]>
}

/**
 * Find the planwise config under a root. The search order is planwise/config.yaml, then
 * config.yaml at the root itself, then each top-level directory in name order. A candidate counts
 * only when its text is a planwise config.
 *
 * @param fs the file calls
 * @param root the directory to search under
 * @returns the config text and the directory that holds the file, or null when the root holds none
 */
export const findConfig = async (fs: ConfigFs, root: string): Promise<{ text: string; dir: string } | null> => {
  const tryDir = async (dir: string): Promise<{ text: string; dir: string } | null> => {
    const path = dir + '/config.yaml'
    if (!(await fs.exists(path))) return null
    const text = String(await fs.read(path))
    return isPlanwiseConfig(text) ? { text, dir } : null
  }
  const base = root.replace(/[\\/]+$/, '')
  const first = await tryDir(base + '/planwise')
  if (first !== null) return first
  const atRoot = await tryDir(base)
  if (atRoot !== null) return atRoot
  const names = (await fs.list(root))
    .filter((entry) => entry.kind === 'dir' && entry.name !== 'planwise' && !entry.name.startsWith('.'))
    .map((entry) => entry.name)
    .sort()
  for (const name of names) {
    const found = await tryDir(base + '/' + name)
    if (found !== null) return found
  }
  return null
}

/**
 * Resolve the drafts directory as the Python config loader does. The base is the directory that
 * holds the config file. The relative name is `project.feedback_dir`, or `Feedback/Feedback-Drafts`
 * when it is absent or blank. An absolute value is kept as given. Backslashes become forward slashes.
 *
 * @param configDir the directory that holds config.yaml
 * @param feedbackDirScalar the unquoted `project.feedback_dir` value, or undefined
 * @returns the drafts directory
 */
export const resolveDraftsDir = (configDir: string, feedbackDirScalar: string | undefined): string => {
  const rel = (feedbackDirScalar ?? '').trim() === '' ? 'Feedback/Feedback-Drafts' : (feedbackDirScalar ?? '').trim()
  const joined = /^([A-Za-z]:)?[\\/]/.test(rel) ? rel : configDir.replace(/[\\/]+$/, '') + '/' + rel
  return joined.replace(/\\/g, '/')
}

/** True for a path that starts at a drive or at the file system root. */
const isAbsolute = (path: string): boolean => /^([A-Za-z]:)?\//.test(path)

/** Join a forward-slash path to a base, and resolve its `.` and `..` segments. */
const joinPath = (base: string, path: string): string => {
  const full = isAbsolute(path) ? path : base + '/' + path
  const out: string[] = []
  for (const part of full.split('/')) {
    if (part === '..') out.pop()
    else if (part !== '.' && (part !== '' || out.length === 0)) out.push(part)
  }
  // A UNC share starts with two slashes, and the segment walk keeps one.
  return (full.startsWith('//') ? '/' : '') + out.join('/')
}

/** True when a git config text sets `bare` to a true value under `[core]`. */
const setsBare = (config: string): boolean => {
  let section = ''
  let bare = false
  for (const line of config.split(/\r?\n/)) {
    const text = line.trim()
    if (text.startsWith('[')) {
      section = text.replace(/^\[+|\]+$/g, '').trim().toLowerCase()
      continue
    }
    const at = text.indexOf('=')
    if (section !== 'core' || at < 0 || text.slice(0, at).trim().toLowerCase() !== 'bare') continue
    bare = ['true', 'yes', 'on', '1'].includes(text.slice(at + 1).trim().toLowerCase())
  }
  return bare
}

/**
 * The same folder inside the main checkout, when `dir` sits in a git linked worktree. It mirrors
 * `main_checkout_root` of the Python install check: it reads `.git` files only and runs no
 * process. A linked worktree's `.git` is a file that names an admin folder, and that folder's
 * `commondir` file names the common git folder. An ordinary checkout, a submodule, a bare
 * repository, a folder outside git and any read failure give null.
 *
 * @param fs the file calls
 * @param dir the folder to map, with either separator
 * @returns the mapped folder with forward slashes, or null
 */
export const mainCheckoutDir = async (fs: ConfigFs, dir: string): Promise<string | null> => {
  const start = dir.replace(/\\/g, '/').replace(/\/+$/, '')
  try {
    let base = start
    for (;;) {
      if (await fs.exists(base + '/.git/HEAD')) return null
      if (await fs.exists(base + '/.git')) break
      const cut = base.lastIndexOf('/')
      if (cut < 0) return null
      base = base.slice(0, cut)
    }
    const first = String(await fs.read(base + '/.git')).split(/\r?\n/)[0] ?? ''
    if (!first.startsWith('gitdir:')) return null
    const admin = joinPath(base, first.slice('gitdir:'.length).trim().replace(/\\/g, '/'))
    const named = String(await fs.read(admin + '/commondir')).trim().replace(/\\/g, '/')
    if (named === '') return null
    const common = joinPath(admin, named)
    if (!common.endsWith('/.git')) return null
    // A config that cannot be read counts as not bare, as in the Python lookup.
    const config = await fs.read(common + '/config').then(String, () => '')
    if (setsBare(config)) return null
    return common.slice(0, -'/.git'.length) + start.slice(base.length)
  } catch {
    return null
  }
}

/**
 * Resolve the plans directory as the Python config loader does. The base is the directory that
 * holds the config file. The relative name is `project.plans_dir`, or `Plans` when it is absent
 * or blank. An absolute value is kept as given. Backslashes become forward slashes.
 *
 * @param configDir the directory that holds config.yaml
 * @param plansDirScalar the unquoted `project.plans_dir` value, or undefined
 * @returns the plans directory
 */
export const resolvePlansDir = (configDir: string, plansDirScalar: string | undefined): string => {
  const rel = (plansDirScalar ?? '').trim() === '' ? 'Plans' : (plansDirScalar ?? '').trim()
  const joined = /^([A-Za-z]:)?[\\/]/.test(rel) ? rel : configDir.replace(/[\\/]+$/, '') + '/' + rel
  return joined.replace(/\\/g, '/')
}

/** The unquoted spellings PyYAML reads as a false boolean. */
const YAML_FALSE = new Set(['false', 'False', 'FALSE', 'no', 'No', 'NO', 'off', 'Off', 'OFF'])

/** The unquoted spellings PyYAML reads as a true boolean. */
const YAML_TRUE = new Set(['true', 'True', 'TRUE', 'yes', 'Yes', 'YES', 'on', 'On', 'ON'])

/**
 * Map the raw `feedback.drafts` text to a mode, as the Python config loader does.
 * An unquoted boolean token is a boolean: false-like gives off, true-like gives
 * notify. A quoted value is a string: it is trimmed and lowercased. Anything
 * outside notify, quiet and off gives notify.
 *
 * @param raw the raw scalar text with its quotes, or undefined
 * @returns the mode
 */
export const draftsMode = (raw: string | undefined): DraftsMode => {
  if (raw === undefined) return 'notify'
  const text = raw.trim()
  const quoted = /^(["'])(.*)\1$/.exec(text)
  if (quoted === null) {
    if (YAML_FALSE.has(text)) return 'off'
    if (YAML_TRUE.has(text)) return 'notify'
  }
  const value = (quoted !== null ? (quoted[2] ?? '') : text).trim().toLowerCase()
  return value === 'quiet' || value === 'off' ? value : 'notify'
}
