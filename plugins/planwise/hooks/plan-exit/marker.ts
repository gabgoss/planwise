// Reads the final line of a finished answer. Only a marker on that line counts toward arming.
import { parseLoopMarker } from '../loop/parse-marker.ts'
import { PLAN_MARKER_RE } from './names.ts'

const finalLine = (answer: string): string => answer.trimEnd().split(/\r?\n/).pop() ?? ''

/** True when the answer ends on the plan-mode marker. */
export const isPlanModeMarker = (answer: string): boolean => PLAN_MARKER_RE.test(finalLine(answer))

/** True when the answer ends on a loop marker. */
export const endsOnLoopMarker = (answer: string): boolean => parseLoopMarker(finalLine(answer)) !== null
