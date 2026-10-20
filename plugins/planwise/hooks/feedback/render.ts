// Renders a draft file: quoted YAML frontmatter in the fixed key order, then the
// issue body headings for the kind. Also holds the path scrubber. Pure text work.
import { FRONTMATTER_KEYS, KIND_FIELDS } from './names.ts'
import type { Kind } from './names.ts'

/** The values the producer adds. The model supplies none of them. */
export type DraftMeta = {
  draftId: string
  createdAt: string
  producer: string
  sourceSessionId: string
  pluginVersion: string
  cliVersion: string
  model: string
  os: string
  status: string
}

/** The model-supplied values, after validation. */
export type DraftInput = {
  kind: Kind
  title: string
  fields: Record<string, string>
  subcommand: string
}

/**
 * Quote a string as a YAML double-quoted scalar on one line.
 * The Python helper strips one quote pair and decodes no escape, so the value must need none.
 *
 * @param text the raw value
 * @returns the quoted value; a line break becomes a space, `"` becomes `'` and `\` becomes `/`
 */
export const yamlQuote = (text: string): string =>
  '"' + text.replace(/\r\n|\r|\n/g, ' ').replace(/"/g, "'").replace(/\\/g, '/') + '"'

/**
 * Replace each root path, in both its `/` and `\` spellings, with `{project}`.
 *
 * @param text the text to clean
 * @param roots the absolute paths to hide
 * @returns the text with every root replaced
 */
export const scrub = (text: string, roots: readonly string[]): string => {
  const spellings: string[] = []
  for (const root of roots) {
    const trimmed = root.replace(/[\\/]+$/, '')
    if (trimmed === '') continue
    const forward = trimmed.replace(/\\/g, '/')
    const back = forward.replace(/\//g, '\\')
    spellings.push(forward, back)
  }
  spellings.sort((a, b) => b.length - a.length)
  let out = text
  for (const spelling of spellings) out = out.split(spelling).join('{project}')
  return out
}

/**
 * Render a draft file.
 *
 * @param meta the producer-added values
 * @param input the validated model values
 * @returns the file text: frontmatter, then one heading per body field, then Environment
 */
export const renderDraft = (meta: DraftMeta, input: DraftInput): string => {
  const values: Record<(typeof FRONTMATTER_KEYS)[number], string> = {
    draft_id: meta.draftId,
    created_at: meta.createdAt,
    drafted_by: 'model',
    producer: meta.producer,
    trigger: 'model_judgment',
    kind: input.kind,
    title: input.title,
    subcommand: input.subcommand,
    source_session_id: meta.sourceSessionId,
    plugin_version: meta.pluginVersion,
    cli_version: meta.cliVersion,
    model: meta.model,
    os: meta.os,
    status: meta.status,
  }
  const lines = ['---']
  for (const key of FRONTMATTER_KEYS) lines.push(key + ': ' + yamlQuote(values[key]))
  lines.push('---', '')
  for (const [field, heading] of KIND_FIELDS[input.kind]) {
    lines.push('### ' + heading, '', input.fields[field] ?? '', '')
  }
  lines.push(
    '### Environment',
    '',
    '- plugin version: ' + meta.pluginVersion,
    '- Claude Code version: ' + meta.cliVersion,
    '- model: ' + meta.model,
    '- os: ' + meta.os,
    '',
  )
  return lines.join('\n')
}
