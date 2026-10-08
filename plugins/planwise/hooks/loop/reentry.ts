// Builds the re-entry arguments and picks the planwise skill from the command list.
// A missing skill returns `null`; it never throws.
import type { CommandInfo } from 'claude-code'
import { PLUGIN_NAME, SKILL_NAME_PATTERN, SKILL_NAME_PREFERENCE } from './names.ts'

/**
 * The arguments that re-enter the backlog handler for one run.
 *
 * @param runId the run id from the marker
 * @returns the argument string
 */
export const reentryArgs = (runId: string): string => 'backlog --loop-resume ' + runId

/**
 * Pick the skill name to run: apply the name pattern, then the preference
 * order, then prefer a command whose plugin starts with `planwise`.
 *
 * @param commands the engine's command list
 * @returns the chosen name, or `null` when nothing matches
 */
export const skillNameOf = (commands: readonly CommandInfo[]): string | null => {
  const matches = commands.filter((c) => SKILL_NAME_PATTERN.test(c.name))
  if (matches.length === 0) return null
  for (const wanted of SKILL_NAME_PREFERENCE) {
    const hit = matches.find((c) => c.name === wanted)
    if (hit !== undefined) return hit.name
  }
  const owned = matches.find((c) => c.plugin?.startsWith(PLUGIN_NAME) === true)
  return (owned ?? matches[0])?.name ?? null
}
