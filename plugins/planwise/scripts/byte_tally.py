#!/usr/bin/env python3
"""Per-file line-ending tally, read from bytes.

Usage:
    python -B byte_tally.py <path> [<path> ...]
    python -B byte_tally.py --before <dir> --after <dir>

Every count comes from an 'rb' read. A file is classified as:
    crlf   only CRLF endings
    lf     only bare LF endings
    mixed  CRLF and bare LF together, or any bare CR
    none   no line ending at all

Path mode prints one row per file, then `files=<n> mixed=<n>`.
Snapshot mode matches files by relative path, prints one row per file,
then `files=<n> mixed=<n> changed=<n>`. A file whose class differs
between the snapshots, or that exists in only one, counts as changed.
A wholesale crlf to lf conversion has mixed=0 and still counts.

Exit codes: 0 when mixed=0 and changed=0, 1 otherwise, 2 on usage error
or an unreadable path.
"""

import os
import sys

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__


def classify(data):
    """Return (class, crlf, lf, cr) counted from bytes."""
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    cr = data.count(b"\r") - crlf
    if cr > 0 or (crlf > 0 and lf > 0):
        kind = "mixed"
    elif crlf > 0:
        kind = "crlf"
    elif lf > 0:
        kind = "lf"
    else:
        kind = "none"
    return kind, crlf, lf, cr


def tally(path):
    with open(path, "rb") as handle:
        return classify(handle.read())


def walk(root):
    found = {}
    for base, _dirs, names in os.walk(root):
        for name in names:
            full = os.path.join(base, name)
            found[os.path.relpath(full, root).replace(os.sep, "/")] = full
    return found


def row(label, result):
    kind, crlf, lf, cr = result
    return f"{kind} crlf={crlf} lf={lf} cr={cr} {label}"


def run_paths(paths):
    mixed = 0
    for path in paths:
        result = tally(path)
        mixed += result[0] == "mixed"
        print(row(path, result))
    print(f"files={len(paths)} mixed={mixed}")
    return 1 if mixed else 0


def run_snapshots(before_dir, after_dir):
    before = walk(before_dir)
    after = walk(after_dir)
    mixed = changed = 0
    names = sorted(set(before) | set(after))
    for name in names:
        old = tally(before[name])[0] if name in before else "absent"
        new_result = tally(after[name]) if name in after else None
        new = new_result[0] if new_result else "absent"
        mixed += new == "mixed"
        flag = "CHANGED" if old != new else "same"
        changed += old != new
        counts = row(name, new_result) if new_result else f"absent {name}"
        print(f"{flag} {old}->{new} {counts}")
    print(f"files={len(names)} mixed={mixed} changed={changed}")
    return 1 if (mixed or changed) else 0


def main(argv):
    try:
        if argv and argv[0] in ("--before", "--after"):
            if len(argv) != 4 or {argv[0], argv[2]} != {"--before", "--after"}:
                raise ValueError
            opts = {argv[0]: argv[1], argv[2]: argv[3]}
            for directory in opts.values():
                if not os.path.isdir(directory):
                    raise OSError(f"not a directory: {directory}")
            return run_snapshots(opts["--before"], opts["--after"])
        if not argv or any(a.startswith("--") for a in argv):
            raise ValueError
        return run_paths(argv)
    except ValueError:
        print(
            "usage: byte_tally.py <path> [...] | --before <dir> --after <dir>",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
