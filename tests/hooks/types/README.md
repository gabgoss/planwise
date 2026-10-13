# Pinned engine type declarations

**Purpose:** `claude-code.d.ts` comes from the cli-watch static declarations extraction. `claude-code-mcp.d.ts` is a frozen byte copy from an earlier capture. The type check of the hooks module reads both.

## Source and transform

| Item | Value |
|---|---|
| Source file | `claude-code.d.ts` from the cli-watch snapshot for Claude Code 2.1.296, written by `python -m cliwatch declarations` from the executable's embedded declarations asset |
| Source sha256 (core asset) | `cf4afc180ffef03cb8138916c0e8f49b8186242a81e226f01ba24341018e5e90` |
| Snapshot file sha256 | `ea634205532548aa90020ff3a941e570bff5bec8ae242fb96d09dbcc8fc1bfad` |
| Transform | first line deleted; each doc example of a CLI version string (regex `2\.1\.\d{3}`) replaced with `X.Y.Z` |
| Replacements | 6 |
| MCP file | `claude-code-mcp.d.ts` is a frozen byte copy of the file in the 2.1.286 capture, because it carries no version string |

The snapshot file is a header line, the core asset and one trailing newline. The bytes after its first line are therefore the core asset plus one trailing newline. The sha256 of those bytes, minus that one newline, equals the source sha256 above.

The MCP file was not regenerated. No build from 2.1.293 on writes it, because the command that wrote it was removed. Do not regenerate it.

## Hashes of the committed copies

| File | sha256 |
|---|---|
| `claude-code.d.ts` | `aaece9b09e206e6fdb8940cf09b19ed33344adc67b774b21400e93ae051eaa4a` |
| `claude-code-mcp.d.ts` | `47979a1cef42168e2f600c759eb3f650bc33f515baa7a9674a632db16b2533e1` |

The instrument is the sha256 of the working-tree bytes. The bytes are LF. The repo-root `.gitattributes` line `tests/hooks/types/*.d.ts -text` keeps them LF on checkout under `core.autocrlf=true`.

## What the stand-in does not carry

The `/plugin-types` command no longer exists from Claude Code 2.1.293. That command appended a tool-schema tail after the core declarations. The tail is not part of this stand-in. No hooks source narrows on `BuiltinToolInputs`.

## Refresh procedure

1. Run `python -m cliwatch watch` to capture a new build, or `python -m cliwatch declarations --version <v>` to backfill one snapshot.
2. Take `snapshots/<v>/types/claude-code.d.ts`.
3. Delete the first line. The result is the core asset plus one trailing newline. The sha256 of those bytes minus that one newline equals the `sha256` in the snapshot's `declarations.json`.
4. Apply the replacements, and write the result with LF line endings.
5. Update the hashes in this file.
6. Re-run `tsc` with `npx -y -p typescript@7.0.2 tsc --noEmit -p cloned-repos/planwise/tests/hooks/tsconfig.json`.
7. Leave `claude-code-mcp.d.ts` as it is.
