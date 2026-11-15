#!/usr/bin/env python3
"""Decide a native ``Grep`` tool call written as a verification gate.

A task file may state a gate as ``Grep pattern='...' path='...'
output_mode='count'``. That is the notation the native-tool-use reference
recommends, and it is not a program the operating system can run. This module
decides such a call in-process with Python ``re``. It starts no subprocess for
the search itself. The one subprocess it may start is the read-only ``git``
query that lists a directory's files, and that query goes through the same
policy and hardening as every other ``git`` gate.

Three functions, none of which writes anything:

``parse_grep_call(argv)``
    Turns the argument vector of a ``Grep name=value ...`` line into a
    parameter dict, or says why the call is refused. It accepts ``pattern``,
    ``path``, ``output_mode``, ``glob``, ``-i``, ``-n`` and ``multiline``. It
    refuses every other parameter by name, a ``glob`` it cannot translate, and
    a pattern Python ``re`` cannot compile or that uses syntax the ripgrep
    engine behind the tool rejects.

``run_grep_call(params, cwd, timeout)``
    Searches and returns ``(result, refusal)``. Exactly one of the two is None.
    ``result`` has the shape ``run_command`` returns for a run.

``measured_value(params, stdout)``
    Reads the single number the call's output represents.

Measured semantics the module reproduces:

* A file ``path`` searches that file, and ``glob`` does not filter it.
* A directory inside a git work tree searches the files git lists with
  ``ls-files -co --exclude-standard``: hidden files are searched and ignored
  files are not. A directory outside git is walked, every file.
* A file with a NUL byte in its first 8 KiB is binary and is skipped.
* Count mode reports the number of matching LINES per file, not occurrences.
  In ``multiline`` mode it reports the number of matches. A file with no match
  prints nothing, so an empty result is a measured zero.

A pattern is compiled once and run over file text, so a pattern with
catastrophic backtracking cannot be interrupted. The timeout is checked
between files only.
"""

import os
import re
import subprocess
import time
import warnings
from bisect import bisect_right
from pathlib import Path

from lint_gate_git_policy import git_refusal, hardened_git_argv_env

PARAMETERS = frozenset({"pattern", "path", "output_mode", "glob", "-i", "-n", "multiline"})
OUTPUT_MODES = ("content", "count", "files_with_matches")
DEFAULT_OUTPUT_MODE = "files_with_matches"
DEFAULT_TIMEOUT_SECONDS = 30
BINARY_PROBE_BYTES = 8192

_REJECTED_AS_RIPGREP_ONLY = "uses ripgrep-only syntax that the in-process matcher cannot decide"


def _parse_bool(name, value, default):
    """Return ``(flag, refusal)`` for a ``true`` or ``false`` parameter."""
    if value is None:
        return default, None
    lowered = value.lower()
    if lowered == "true":
        return True, None
    if lowered == "false":
        return False, None
    return None, f"Grep parameter {name!r} takes true or false, not {value!r}"


def _python_only_construct(pattern, multiline):
    """Name a construct Python ``re`` accepts and the ripgrep engine rejects.

    The tool refuses these with an error, so deciding them in-process would
    report a measurement for a call that never produces one. A newline in a
    pattern is one such construct unless ``multiline`` is on: Python compiles
    it and never matches, which would read as a measured zero.
    """
    index, length = 0, len(pattern)
    in_class = False
    after_quantifier = False
    previous_open_group = False
    while index < length:
        char = pattern[index]
        if char == "\n" and not multiline:
            return "a newline without multiline"
        if char == "\\":
            following = pattern[index + 1] if index + 1 < length else ""
            if following == "n" and not multiline:
                return "a newline without multiline"
            if not in_class and following and following in "123456789":
                return "a backreference"
            index += 2
            after_quantifier = False
            previous_open_group = False
            continue
        if in_class:
            if char == "]":
                in_class = False
            index += 1
            continue
        if char == "[":
            in_class = True
            index += 1
            if index < length and pattern[index] == "^":
                index += 1
            if index < length and pattern[index] == "]":
                index += 1
            after_quantifier = False
            previous_open_group = False
            continue
        if char == "(":
            rest = pattern[index + 1:index + 4]
            if rest.startswith(("?=", "?!", "?<=", "?<!")):
                return "a lookaround"
            if rest.startswith("?>"):
                return "an atomic group"
            if rest.startswith("?("):
                return "a conditional group"
            previous_open_group = True
            after_quantifier = False
            index += 1
            continue
        if char in "*+?}":
            if char == "+" and after_quantifier:
                return "a possessive quantifier"
            if char == "?" and previous_open_group:
                previous_open_group = False
                after_quantifier = False
            elif char == "?" and after_quantifier:
                after_quantifier = False
            else:
                after_quantifier = True
                previous_open_group = False
            index += 1
            continue
        after_quantifier = False
        previous_open_group = False
        index += 1
    return None


def _compile_pattern(pattern, ignore_case, multiline):
    """Return ``(regex, refusal)``."""
    construct = _python_only_construct(pattern, multiline)
    if construct is not None:
        return None, f"the Grep pattern {_REJECTED_AS_RIPGREP_ONLY} ({construct})"
    flags = re.MULTILINE | re.DOTALL if multiline else 0
    if ignore_case:
        flags |= re.IGNORECASE
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            return re.compile(pattern, flags), None
    except (re.error, Warning, RecursionError, OverflowError) as exc:
        return None, f"the Grep pattern {_REJECTED_AS_RIPGREP_ONLY} ({exc})"


def _brace_alternatives(glob, start):
    """Split the brace group opening at ``glob[start]``; return ``(alternatives, next)``."""
    depth = 0
    pieces = []
    current = start + 1
    index = start
    while index < len(glob):
        char = glob[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                pieces.append(glob[current:index])
                return pieces, index + 1
        elif char == "," and depth == 1:
            pieces.append(glob[current:index])
            current = index + 1
        index += 1
    raise ValueError("an unclosed { group")


def _translate_glob(glob):
    """Translate gitignore-style glob text into regular expression text."""
    out = []
    index, length = 0, len(glob)
    while index < length:
        char = glob[index]
        if char == "\\" and index + 1 < length:
            out.append(re.escape(glob[index + 1]))
            index += 2
        elif char == "*":
            if glob.startswith("**/", index):
                out.append("(?:.*/)?")
                index += 3
            elif glob.startswith("**", index):
                out.append(".*")
                index += 2
            else:
                out.append("[^/]*")
                index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        elif char == "[":
            end = glob.find("]", index + 2)
            if end < 0:
                raise ValueError("an unclosed [ class")
            body = glob[index + 1:end]
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", "\\\\") + "]")
            index = end + 1
        elif char == "{":
            alternatives, index = _brace_alternatives(glob, index)
            out.append("(?:" + "|".join(_translate_glob(alt) for alt in alternatives) + ")")
        else:
            out.append(re.escape(char))
            index += 1
    return "".join(out)


def _compile_glob(glob):
    """Return ``(regex, anchored, refusal)`` for a ``glob`` parameter."""
    if not glob.strip() or glob != glob.strip() or any(ch.isspace() for ch in glob):
        return None, False, "the Grep glob is empty or holds more than one glob"
    if glob.startswith("!"):
        return None, False, "the Grep glob is negated, which the in-process matcher does not decide"
    if glob.endswith("/"):
        return None, False, "the Grep glob names a directory, which the in-process matcher does not decide"
    anchored = "/" in glob
    body = glob.removeprefix("/")
    try:
        return re.compile(_translate_glob(body)), anchored, None
    except (ValueError, re.error) as exc:
        return None, False, f"the Grep glob {glob!r} cannot be translated ({exc})"


def parse_grep_call(argv):
    """Return ``(params, None)`` for a decidable call, else ``(None, reason)``."""
    if not argv or argv[0] != "Grep":
        return None, "the command is not a Grep tool call"
    raw = {}
    for token in argv[1:]:
        name, separator, value = token.partition("=")
        if not separator:
            return None, f"the Grep argument {token!r} is not written name=value"
        if name not in PARAMETERS:
            return None, f"the Grep parameter {name!r} is not one the gate linter decides"
        if name in raw:
            return None, f"the Grep parameter {name!r} is given twice"
        raw[name] = value

    pattern = raw.get("pattern")
    if not pattern:
        return None, "the Grep call names no pattern"
    output_mode = raw.get("output_mode", DEFAULT_OUTPUT_MODE)
    if output_mode not in OUTPUT_MODES:
        return None, (
            f"the Grep output_mode {output_mode!r} is not one of "
            f"{', '.join(OUTPUT_MODES)}"
        )

    flags = {}
    for name, default in (("-i", False), ("-n", True), ("multiline", False)):
        flags[name], refusal = _parse_bool(name, raw.get(name), default)
        if refusal is not None:
            return None, refusal

    regex, refusal = _compile_pattern(pattern, flags["-i"], flags["multiline"])
    if refusal is not None:
        return None, refusal

    glob_regex, anchored, refusal = None, False, None
    glob = raw.get("glob")
    if glob is not None:
        glob_regex, anchored, refusal = _compile_glob(glob)
        if refusal is not None:
            return None, refusal

    return {
        "pattern": pattern,
        "regex": regex,
        "path": raw.get("path") or None,
        "output_mode": output_mode,
        "glob": glob,
        "glob_regex": glob_regex,
        "glob_anchored": anchored,
        "ignore_case": flags["-i"],
        "line_numbers": flags["-n"],
        "multiline": flags["multiline"],
    }, None


def _run_git(args, directory, timeout):
    """Run one admitted, hardened ``git`` query; return ``(completed, refusal)``."""
    argv = ["git", "-C", str(directory), *args]
    refusal = git_refusal(argv)
    if refusal is not None:
        return None, refusal
    run_argv, run_env = hardened_git_argv_env(argv)
    try:
        completed = subprocess.run(
            run_argv, env=run_env, capture_output=True, timeout=max(timeout, 1), check=False
        )
    except subprocess.TimeoutExpired:
        return None, "the git file listing did not finish in time"
    except OSError as exc:
        return None, f"git could not be started ({exc.strerror or exc})"
    return completed, None


def _has_git_marker(directory):
    return any((candidate / ".git").exists() for candidate in (directory, *directory.parents))


def _walk_files(directory):
    found = []
    for root, _dirs, names in os.walk(directory):
        found.extend(Path(root) / name for name in names)
    return sorted(found)


def _directory_files(directory, timeout):
    """List the files a directory search covers; return ``(files, refusal)``."""
    if not _has_git_marker(directory):
        return _walk_files(directory), None
    inside, refusal = _run_git(["rev-parse", "--is-inside-work-tree"], directory, timeout)
    if refusal is not None:
        return None, f"{refusal}, so .gitignore could not be honoured"
    if inside.returncode != 0:
        detail = inside.stderr.decode("utf-8", errors="replace").strip()
        return None, f"git could not read the work tree ({detail}), so .gitignore could not be honoured"
    if inside.stdout.strip() != b"true":
        return _walk_files(directory), None
    listing, refusal = _run_git(["ls-files", "-co", "--exclude-standard", "-z"], directory, timeout)
    if refusal is not None:
        return None, refusal
    if listing.returncode != 0:
        detail = listing.stderr.decode("utf-8", errors="replace").strip()
        return None, f"the git file listing failed ({detail})"
    names = [n for n in listing.stdout.decode("utf-8", errors="replace").split("\0") if n]
    return sorted({directory / name for name in names}), None


def _glob_admits(params, directory, path):
    regex = params["glob_regex"]
    if regex is None:
        return True
    if params["glob_anchored"]:
        return regex.fullmatch(path.relative_to(directory).as_posix()) is not None
    return regex.fullmatch(path.name) is not None


def _matches_in(text, params):
    """Return ``(count, [(line_number, line_text)])`` for one file's text."""
    regex = params["regex"]
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not params["multiline"]:
        hits = [(n, line) for n, line in enumerate(lines, start=1) if regex.search(line)]
        return len(hits), hits
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    spanned = set()
    count = 0
    for match in regex.finditer(text):
        count += 1
        first = bisect_right(starts, match.start())
        last = bisect_right(starts, max(match.end() - 1, match.start()))
        spanned.update(range(first, last + 1))
    return count, [(n, lines[n - 1]) for n in sorted(spanned) if n <= len(lines)]


def run_grep_call(params, cwd=None, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Search and return ``(result, refusal)``; exactly one is None."""
    base = Path(cwd) if cwd is not None else Path.cwd()
    target = Path(params["path"]) if params["path"] else base
    if not target.is_absolute():
        target = base / target
    if not target.exists():
        return None, f"the Grep path {params['path']!r} does not exist"

    deadline = time.monotonic() + timeout
    is_directory = target.is_dir()
    if is_directory:
        files, refusal = _directory_files(target, timeout)
        if refusal is not None:
            return None, refusal
    else:
        files = [target]

    mode = params["output_mode"]
    out = []
    searched = skipped = 0
    for path in files:
        if time.monotonic() > deadline:
            return None, f"the Grep search did not finish within {timeout} seconds"
        if is_directory and (not path.is_file() or not _glob_admits(params, target, path)):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            skipped += 1
            continue
        if b"\0" in data[:BINARY_PROBE_BYTES]:
            continue
        searched += 1
        count, hits = _matches_in(data.decode("utf-8", errors="replace"), params)
        if not count:
            continue
        label = path.as_posix()
        if mode == "files_with_matches":
            out.append(label)
        elif mode == "count":
            out.append(f"{label}:{count}")
        else:
            for number, text in hits:
                text = text.rstrip("\r")
                head = f"{label}:" if is_directory else ""
                if params["line_numbers"]:
                    head += f"{number}:"
                out.append(head + text)

    stderr = f"searched {searched} files"
    if skipped:
        stderr += f"; {skipped} unreadable"
    return {
        "executed": True,
        "returncode": 0 if out else 1,
        "stdout": "".join(line + "\n" for line in out),
        "stderr": stderr + "\n",
    }, None


def measured_value(params, stdout):
    """Read the number a call's output represents, or None when unreadable.

    Count mode sums the field after the last colon of each ``path:N`` line.
    Every other mode is the number of output lines. An empty output is zero:
    a file with no match prints nothing.
    """
    if not params:
        return None
    lines = stdout.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if params["output_mode"] != "count":
        return len(lines)
    total = 0
    for line in lines:
        try:
            total += int(line.rsplit(":", 1)[-1])
        except ValueError:
            return None
    return total
