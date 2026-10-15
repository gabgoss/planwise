// Checks the model's tool input before anything is written. Pure: it reads only
// its argument.
import { KINDS, KIND_FIELDS, MAX_BODY_BYTES, MAX_SUBCOMMAND_CHARS, MAX_TITLE_CHARS, NO_SUBCOMMAND } from './names.ts'
import type { Kind } from './names.ts'

/** The result of validation: the cleaned values, or one error line for the model. */
export type ValidateResult =
  | { ok: true; kind: Kind; title: string; fields: Record<string, string>; subcommand: string }
  | { ok: false; error: string }

const fail = (error: string): ValidateResult => ({ ok: false, error })

/**
 * Validate one tool call's input.
 *
 * @param e the raw input object
 * @returns the cleaned values, or the first problem found
 */
export const validateInput = (e: Record<string, unknown>): ValidateResult => {
  const kind = KINDS.find((k) => k === e['kind'])
  if (kind === undefined) return fail('kind must be one of: ' + KINDS.join(', '))

  const rawTitle = e['title']
  if (typeof rawTitle !== 'string') return fail('title must be a string')
  const title = rawTitle.trim()
  const titleChars = Array.from(title).length
  if (titleChars < 1 || titleChars > MAX_TITLE_CHARS) {
    return fail('title must be 1 to ' + String(MAX_TITLE_CHARS) + ' characters')
  }

  const fields: Record<string, string> = {}
  let bytes = 0
  for (const [name] of KIND_FIELDS[kind]) {
    const value = e[name]
    if (typeof value !== 'string' || value.trim() === '') {
      return fail(name + ' is required for kind ' + kind)
    }
    fields[name] = value.trim()
    bytes += new TextEncoder().encode(fields[name]).length
  }
  if (bytes > MAX_BODY_BYTES) {
    return fail('the body fields total ' + String(bytes) + ' bytes; the limit is ' + String(MAX_BODY_BYTES))
  }

  const rawSub = e['subcommand']
  let subcommand = NO_SUBCOMMAND
  if (rawSub !== undefined && rawSub !== null) {
    if (typeof rawSub !== 'string') return fail('subcommand must be a string')
    const sub = rawSub.trim()
    if (Array.from(sub).length > MAX_SUBCOMMAND_CHARS) {
      return fail('subcommand must be at most ' + String(MAX_SUBCOMMAND_CHARS) + ' characters')
    }
    if (sub !== '') subcommand = sub
  }
  return { ok: true, kind, title, fields, subcommand }
}
