// Builds the instructions a compaction hands the summarizer.
// They say what the summary must keep and what it may drop.
import type { LoopMarker } from './parse-marker.ts'
import { reentryArgs } from './reentry.ts'

/**
 * The summarizer instructions for one loop boundary.
 *
 * @param marker the marker the finished session printed
 * @returns the instructions text
 */
export const steerText = (marker: LoopMarker): string =>
  [
    'This compaction sits between two items of a /planwise backlog loop. The summary MUST keep, verbatim:',
    `1. The run id: ${marker.runId}.`,
    `2. The run file path: ${marker.statePath}.`,
    `3. The re-entry command line: /planwise ${reentryArgs(marker.runId)}.`,
    `4. The item just closed (${marker.doneId}) and its outcome.`,
    'Drop the fix-agent diff and the tool output. The run file is the record.',
  ].join('\n')
