# Pinned engine type declarations

**Purpose:** `claude-code.d.ts` and `claude-code-mcp.d.ts` come from one cli-watch capture. The type check of the hooks module reads them.

## Source and transform

| Item | Value |
|---|---|
| Source file | `claude-code.d.ts` from the cli-watch capture |
| Source sha256 | `24ee0571ce8e9c46aca7e6dedf9676163fecef33983dd148c68f2886e86545ee` |
| Transform | first line deleted; each doc example of a CLI version string replaced with `X.Y.Z` |
| Replacements | 6 |
| MCP file | `claude-code-mcp.d.ts` is a byte copy, because it carries no version string |

## Hashes of the committed copies

| File | sha256 |
|---|---|
| `claude-code.d.ts` | `8f16e8e9445f74a5d222878f2394824f95ecd4a3f346b01f3f11c5ff97557c24` |
| `claude-code-mcp.d.ts` | `47979a1cef42168e2f600c759eb3f650bc33f515baa7a9674a632db16b2533e1` |

The instrument is the sha256 of the working-tree bytes. The bytes are LF. The repo-root `.gitattributes` line `tests/hooks/types/*.d.ts -text` keeps them LF on checkout under `core.autocrlf=true`.

## Refresh procedure

1. Run the cli-watch capture (`python -m cliwatch watch`).
2. Take the newest snapshot's `types/` files.
3. Apply the same transform to `claude-code.d.ts`, and copy the MCP file as is.
4. Update the hashes in this file.
5. Re-run `tsc` with `npx -y -p typescript@7.0.2 tsc --noEmit -p cloned-repos/planwise/tests/hooks/tsconfig.json`.
