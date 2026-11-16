import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'

// Claude Code's hooks-module validator refuses the WHOLE module when a hook hands `$` to a
// function that is neither declared at the top level of its file nor imported. A refused
// module registers no tools and runs no hooks, so this shape is checked statically here.
const HOOKS = new URL('../../plugins/planwise/hooks/', import.meta.url)
const files = readdirSync(HOOKS).filter((name) => /\.tsx?$/.test(name))

/** Names of the functions a file passes `$` to, as the first argument. */
const calleesOf = (source: string): string[] => [...source.matchAll(/\b([A-Za-z_]\w*)\(\$[,)]/g)].map((m) => m[1]!)

/** Names declared at column 0 as a function, or as a const bound to an arrow or function. */
const topLevelOf = (source: string): Set<string> => {
  const names = new Set<string>()
  for (const m of source.matchAll(/^(?:export )?(?:async )?function\s+([A-Za-z_]\w*)/gm)) names.add(m[1]!)
  for (const m of source.matchAll(/^(?:export )?const\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?(?:\(|function)/gm)) names.add(m[1]!)
  return names
}

/** Names brought in by an import statement, including `a as b` aliases. */
const importedOf = (source: string): Set<string> => {
  const names = new Set<string>()
  for (const m of source.matchAll(/^import\s+(?:type\s+)?\{([^}]*)\}\s+from/gm)) {
    for (const part of m[1]!.split(',')) {
      const name = part.trim().split(/\s+as\s+/).pop()
      if (name) names.add(name)
    }
  }
  return names
}

test('the hooks directory holds files to check', () => {
  assert.ok(files.includes('register.ts') && files.includes('agent-guard.ts'), files.join(', '))
})

for (const file of files) {
  test(`${file}: every function handed $ is top-level or imported`, () => {
    const source = readFileSync(new URL(file, HOOKS), 'utf-8')
    const allowed = new Set([...topLevelOf(source), ...importedOf(source)])
    const stray = [...new Set(calleesOf(source))].filter((name) => !allowed.has(name))
    assert.deepEqual(stray, [])
  })
}

test('the check fires on a nested function handed $', () => {
  const nested = "export function register(on) {\n  const hostOf = ($) => ({})\n  on('x', ($, e, next) => hostOf($))\n}\n"
  const allowed = new Set([...topLevelOf(nested), ...importedOf(nested)])
  assert.deepEqual(calleesOf(nested).filter((name) => !allowed.has(name)), ['hostOf'])
})
