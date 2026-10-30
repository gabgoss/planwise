#!/usr/bin/env python3
"""Path-set gate: changed - extractor_allowed - environment_expect must be empty.

Usage:
    python -B path_set_gate.py <changed-list|-> <extractor-allowed-list> <environment-expect-list>

Each list holds one path per line (the changed list is the output of
`git diff --name-only <base> -- <dir>`). Carriage returns are stripped so a
list written in text mode on Windows still compares equal.

Exit codes: 0 no unexpected path, 1 unexpected paths (printed), 2 usage or an unreadable list
(an `Error:` line goes to stderr, so exit 1 always means a real finding).
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__


def read_paths(text):
    """Return the set of non-blank paths in text, with line endings stripped."""
    return {ln.strip() for ln in text.splitlines() if ln.strip()}


def unexpected(changed, allowed, expected):
    """Return the sorted paths in changed that neither list explains."""
    return sorted(changed - allowed - expected)


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        if argv[0] == "-":
            changed_text = sys.stdin.read()
        else:
            changed_text = Path(argv[0]).read_text(encoding="utf-8-sig")
        allowed_text = Path(argv[1]).read_text(encoding="utf-8-sig")
        expected_text = Path(argv[2]).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: path_set_gate cannot read an input list: {exc}", file=sys.stderr)
        return 2
    changed = read_paths(changed_text)
    allowed = read_paths(allowed_text)
    expected = read_paths(expected_text)
    extra = unexpected(changed, allowed, expected)
    print(
        f"changed={len(changed)} allowed={len(allowed)} expected={len(expected)} "
        f"unexpected={len(extra)}"
    )
    for path in extra:
        print(f"UNEXPECTED: {path}")
    return 1 if extra else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
