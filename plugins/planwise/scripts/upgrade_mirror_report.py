#!/usr/bin/env python3
"""Banner blocks for the read-only post-upgrade sweeps, printed by --upgrade.

`artifact_upgrade._run_upgrade()` runs `sweep_orphaned_agent_mirrors()` on
both of its exits and hands the findings here. The block mirrors what
`/planwise doctor` reports for the same sweep: one row per still-installed
mirror, its class (`REMOVABLE` or `PRESERVE`) and the sweep's own reason.
Only the `REMOVABLE` set is ever offered for pruning. A `PRESERVE` row is
reported and left alone. The real-upgrade branch also hands the rule
over-scope advisory here. Each `emit_*` entry point swallows a raise from its
sweep and writes one stderr warning, so a failed advisory never skips the
version-pin commit. This module only formats; it never touches disk.
"""

from __future__ import annotations

import sys

PRUNE_LINE = "  remove the REMOVABLE set with: /planwise doctor --prune-stale"


def format_mirror_block(findings: list[dict]) -> list[str]:
    """Return the banner lines for `findings`, or [] when there are none."""
    if not findings:
        return []
    lines = [f"Orphaned agent mirrors: {len(findings)}"]
    for finding in findings:
        lines.append(f"  {finding['verdict']:<9}  {finding['path']}  — {finding['reason']}")
    if any(finding["verdict"] == "REMOVABLE" for finding in findings):
        lines.append(PRUNE_LINE)
    return lines


def emit_mirror_block(findings: list[dict]) -> None:
    """Print the block followed by one blank line. Silent when empty."""
    lines = format_mirror_block(findings)
    if lines:
        print("\n".join(lines))
        print()


def emit_mirror_sweep(cfg, sweep) -> None:
    """Run `sweep(cfg)` and print its block. Never raises, so the caller's exit code holds."""
    try:
        emit_mirror_block(sweep(cfg))
    except Exception as exc:  # noqa: BLE001 -- never change the exit code
        print(f"  Warning: orphaned agent mirror sweep raised unexpectedly: {exc}",
              file=sys.stderr)


def emit_overscope_advisory(cfg, lint) -> None:
    """Run `lint(cfg)` and print the over-scope advisory. Never raises.

    The advisory lists installed rules scoped to plan/backlog/lessons globs.
    Nothing prints until the whole block is built, so a raise leaves stdout
    untouched and costs one stderr warning. The caller's exit code holds.
    """
    try:
        overscoped = lint(cfg)
        if not overscoped:
            return
        total_tokens = sum(item["approx_tokens"] for item in overscoped)
        lines = ["Advisory — rules scoped to plan/backlog/lessons globs:"]
        for item in overscoped:
            lines.append(
                f"  ~ {item['path']} ({item['line_count']} lines, "
                f"~{item['approx_tokens']} tokens; matches {item['matched_glob']})"
            )
            lines.append("      hint: re-scope to code paths or convert to a handler-loaded reference")
        lines.append(f"  Total always-on injected budget from flagged rules: ~{total_tokens} tokens")
    except Exception as exc:  # noqa: BLE001 -- never change the exit code
        print(f"  Warning: rule overscope advisory raised unexpectedly: {exc}",
              file=sys.stderr)
        return
    print("\n".join(lines))
    print()
