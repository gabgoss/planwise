#!/usr/bin/env python3
"""Dry-run pair helper with two modes.

Usage:
    python -B dry_run_pair.py --outputs "<gate command with {input}>" <good> <bad>
    python -B dry_run_pair.py --at-head <repo> <tracked-path> <pattern>

--outputs runs the gate command once per input (the `{input}` token is
replaced by the path; no shell is used) and compares stdout plus exit code.
A gate that prints the same on a known-good and a known-bad input cannot
discriminate. Exit 0 when the outputs differ, 1 when identical.

--at-head counts the lines matching `pattern` (Python `re`) in the blob at
HEAD and in the working file. Both sides are decoded as UTF-8 with line
endings stripped, so autocrlf cannot move a count. A pattern that returns
the same count on both sides saw no change. Exit 0 when the counts differ,
1 when equal.

Exit 2 on usage in both modes, and on a launch, read or decode failure (an
`Error:` line goes to stderr), so exit 1 always means the script's finding.
"""
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__


def run_gate(template, path):
    """Run the gate command with {input} replaced by path; return (code, stdout)."""
    argv = [part.replace("{input}", path) for part in shlex.split(template)]
    proc = subprocess.run(argv, shell=False, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout


def count_matches(data, pattern):
    """Count lines of data (bytes) matching pattern, with line endings stripped."""
    regex = re.compile(pattern)
    lines = re.split(r"\r\n|\n|\r", data.decode("utf-8"))
    return sum(1 for line in lines if regex.search(line))


def mode_outputs(args):
    if len(args) != 3:
        return None
    template, good, bad = args
    if not shlex.split(template):
        return None
    try:
        good_result = run_gate(template, good)
        bad_result = run_gate(template, bad)
    except (OSError, ValueError) as exc:
        print(f"Error: dry_run_pair cannot launch the gate command: {exc}", file=sys.stderr)
        return 2
    print(f"good: exit={good_result[0]} stdout={good_result[1]!r}")
    print(f"bad:  exit={bad_result[0]} stdout={bad_result[1]!r}")
    identical = good_result == bad_result
    print("IDENTICAL: the gate cannot tell good from bad" if identical else "differ")
    return 1 if identical else 0


def mode_at_head(args):
    if len(args) != 3:
        return None
    repo, path, pattern = args
    try:
        re.compile(pattern)
        proc = subprocess.run(
            ["git", "-C", repo, "show", f"HEAD:{path}"], capture_output=True, check=False
        )
        if proc.returncode != 0:
            print(proc.stderr.decode("utf-8", "replace").strip(), file=sys.stderr)
            return 2
        working = (Path(repo) / path).read_bytes()
        at_head = count_matches(proc.stdout, pattern)
        now = count_matches(working, pattern)
    except (re.error, OSError, UnicodeDecodeError) as exc:
        print(f"Error: dry_run_pair cannot count the pattern: {exc}", file=sys.stderr)
        return 2
    print(f"HEAD={at_head} working={now}")
    equal = at_head == now
    print("EQUAL: the pattern saw no change" if equal else "differ")
    return 1 if equal else 0


def main(argv):
    result = None
    if argv and argv[0] == "--outputs":
        result = mode_outputs(argv[1:])
    elif argv and argv[0] == "--at-head":
        result = mode_at_head(argv[1:])
    if result is None:
        print(__doc__, file=sys.stderr)
        return 2
    return result


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
