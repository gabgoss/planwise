// Constants for the backlog loop module: the plugin name, the marker pattern,
// the skill-name pattern and order, and the deferral limits.
/** The plugin's own name. */
export const PLUGIN_NAME = 'planwise'

/** The marker line a one-item backlog session prints as the last line of its answer. */
export const MARKER_RE = /^BACKLOG LOOP: run=(\S+) done=(\S+) remaining=(\d+) state=(.+?)\s*$/gm

/** Which command names can be the planwise skill: `planwise` or `planwise:<anything>`. */
export const SKILL_NAME_PATTERN = /^planwise(:|$)/

/** Among the matches, the preferred names in order. */
export const SKILL_NAME_PREFERENCE = ['planwise:planwise', 'planwise'] as const

/** How long a deferred boundary waits before it checks again, in milliseconds. */
export const DEFER_MS = 500

/** How many times a boundary may defer before the module gives up. */
export const MAX_DEFERRALS = 20
