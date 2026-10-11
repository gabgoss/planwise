#!/usr/bin/env python3
"""Router for the skill's injected shell line.

The skill's `!` line passes one single-quoted value, `'$sub'`. The one-call
fallback passes `list` plus the typed flags as separate argv items. The router
accepts up to three values. A word the user did not type arrives as an empty
string. This script strips each value, drops empty strings and any unexpanded
`$name` placeholder, and treats the first remaining token as the subcommand.

`list` prints the `list_plans` output between two marker comments
(`<!-- planwise:list:begin -->` and `<!-- planwise:list:end -->`). Every other
input prints nothing and never imports `list_plans`. Any failure prints one
`PLANWISE_LIST_FALLBACK: <type>: <message>` line. The exit code is always 0.

CLI: python -B skill_preflight.py <sub> <flag1> <flag2>
"""

import sys
from pathlib import Path

PLACEHOLDERS = {"$0", "$1", "$2", "$sub", "$flag1", "$flag2"}
KNOWN_FLAGS = ("--active", "--no-check")
BEGIN = "<!-- planwise:list:begin -->"
END = "<!-- planwise:list:end -->"


def normalise(argv: list[str]) -> list[str]:
    """Strip each value and drop empty strings and unexpanded placeholders."""
    tokens = [a.strip() for a in argv]
    return [t for t in tokens if t and t not in PLACEHOLDERS]


def run(argv: list[str]) -> None:
    tokens = normalise(argv)
    if not tokens or tokens[0] != "list":
        return
    flags = [t for t in tokens[1:] if t in KNOWN_FLAGS]
    print(BEGIN)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import list_plans

        list_plans.main(flags)
        print(END)
    except Exception as exc:  # noqa: BLE001 - contract: one fallback line, exit 0
        print(f"PLANWISE_LIST_FALLBACK: {type(exc).__name__}: {exc}")
        print(END)


def main(argv: list[str] | None = None) -> int:
    try:
        run(sys.argv[1:] if argv is None else argv)
    except Exception as exc:  # noqa: BLE001
        print(f"PLANWISE_LIST_FALLBACK: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
