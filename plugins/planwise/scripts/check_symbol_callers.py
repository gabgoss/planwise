#!/usr/bin/env python3
"""Report each symbol a diff adds that no production caller reaches.

Usage:
    python -B check_symbol_callers.py --repo <repo> --base <sha> [--production <dir>]... -- <path>...

A definition is not a caller. This check reads the lines a diff adds and finds
four symbol kinds:

- a function: an added `def name(` line whose name the base did not define in
  the same file;
- a keyword parameter with a default, new on an added `def` line;
- a CLI flag registered by an added argparse `add_argument` call;
- a config key read by an added dict `get` call with a quoted key.

For each symbol it counts call sites in the production tree and prints up to
three of them as `file:line`. A function's call site is `name(` on a line that
does not define it, in its own module or in a file that names that module. A
parameter's call site is `function(` with `param=` on the same line, under the
same module rule. A flag's call site is a line in another file that names both
the script and the flag. A config key's call site is a `key:` or `"key":` line.

The script runs `git -C <repo> diff <base> -- <path>...`, because the shell
that runs it may start in a different repository. A bare diff is refused: the
base and at least one path are required. Untracked files under the paths are
read as wholly added, because `git diff` cannot see them.

`--production` defaults to the `scripts`, `handlers`, `agents` and `skills`
directories under `plugins/planwise` at the repository's top level, which may
sit above `<repo>`. Every file path is keyed relative to that top level, the
form `git diff` prints. Any path with a `tests` segment or
a `test_*.py` name is skipped, because a test that passes the activating
argument is a false witness.

This check is heuristic. It matches text on one line, so a call that wraps
across lines, a positional activating argument or a dynamic dispatch is not
counted. It reports. It never decides COMPLETE on its own.

The first output line is `N added symbols scanned`, so an empty diff reads
differently from a clean one.

Exit codes: 0 every symbol has at least one call site, 1 a symbol has none
(each printed with `ZERO`), 2 usage, git failure or an unreadable file.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

DEFAULT_PRODUCTION = ("scripts", "handlers", "agents", "skills")
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".template", ".sh", ".toml", ".txt"}
MAX_SITES = 3

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(([^)]*)")
FLAG_RE = re.compile(r"add_argument\(\s*[\"'](--[\w-]+)[\"']")
CONFIG_GET_RE = re.compile(r"\.get\(\s*[\"']([\w.-]+)[\"']")
PARAM_RE = re.compile(r"(\w+)\s*(?::[^=,]+)?=")


class Symbol:
    """One added symbol and where its definition sits."""

    def __init__(self, kind, name, path, line, owner=None):
        self.kind = kind
        self.name = name
        self.path = path
        self.line = line
        self.owner = owner  # the function a parameter belongs to
        self.sites = []

    def label(self):
        if self.kind == "param":
            return f"param {self.owner}({self.name}=)"
        return f"{self.kind} {self.name}"


def _params(signature):
    """Return the keyword-with-default parameter names in one signature text."""
    names = []
    for part in signature.split(","):
        match = PARAM_RE.match(part.strip().lstrip("*"))
        if match and match.group(1) not in ("self", "cls"):
            names.append(match.group(1))
    return names


def parse_diff(text):
    """Return a list of Symbol for every added symbol in a unified diff."""
    files = {}  # path -> {"added": [(line_no, text)], "removed_defs": {name: params}}
    current = None
    new_line = 0
    for raw in text.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            current = target[2:] if target.startswith("b/") else None
            if current is not None:
                files.setdefault(current, {"added": [], "removed_defs": {}})
            continue
        if raw.startswith("--- ") or current is None:
            continue
        hunk = HUNK_RE.match(raw)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        entry = files[current]
        if raw.startswith("+"):
            entry["added"].append((new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-"):
            match = DEF_RE.match(raw[1:])
            if match:
                entry["removed_defs"][match.group(1)] = set(_params(match.group(2)))
        else:
            new_line += 1
    symbols = []
    for path, entry in files.items():
        symbols.extend(_symbols_in(path, entry["added"], entry["removed_defs"]))
    return symbols


def _symbols_in(path, added, removed_defs):
    symbols = []
    for number, text in added:
        match = DEF_RE.match(text)
        if match:
            name = match.group(1)
            if name.startswith("__") and name.endswith("__"):
                continue  # a dunder is reached by the language, not by a call site
            old = removed_defs.get(name)
            if old is None:
                symbols.append(Symbol("function", name, path, number))
                old = set()
            for param in _params(match.group(2)):
                if param not in old:
                    symbols.append(Symbol("param", param, path, number, owner=name))
        for flag in FLAG_RE.findall(text):
            symbols.append(Symbol("flag", flag, path, number))
        for key in CONFIG_GET_RE.findall(text):
            symbols.append(Symbol("config-key", key, path, number))
    return symbols


def untracked_as_diff(repo, paths, top=None):
    """Render untracked files under the paths as wholly-added diff text.

    Each path is relative to the top level ``top`` (``repo`` when None), the
    form ``git diff`` prints, so both halves of the diff key files alike."""
    top = Path(repo) if top is None else Path(top)
    result = _git(repo, ["ls-files", "--others", "--exclude-standard", "--full-name", "--", *paths])
    chunks = []
    for rel in result.splitlines():
        if not rel.strip():
            continue
        try:
            body = (top / rel).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        chunks.append(f"+++ b/{rel}")
        chunks.append(f"@@ -0,0 +1,{len(body)} @@")
        chunks.extend("+" + line for line in body)
    return "\n".join(chunks)


def _git(repo, args):
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {args[0]} exited {completed.returncode}")
    return completed.stdout


def production_files(roots):
    """Yield (path, lines) for every text file under the production roots, tests excluded."""
    for root in roots:
        for folder, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in ("tests", "__pycache__") and not d.startswith("."))
            for name in sorted(names):
                full = Path(folder) / name
                if full.suffix not in TEXT_SUFFIXES or (name.startswith("test_") and name.endswith(".py")):
                    continue
                try:
                    yield full, full.read_text(encoding="utf-8").splitlines()
                except (OSError, UnicodeDecodeError):
                    continue


def _site_pattern(symbol):
    name = re.escape(symbol.name)
    if symbol.kind == "function":
        return re.compile(rf"\b{name}\s*\(")
    if symbol.kind == "param":
        return re.compile(rf"\b{re.escape(symbol.owner)}\s*\(.*\b{name}\s*=")
    if symbol.kind == "flag":
        stem = re.escape(Path(symbol.path).stem)
        return re.compile(rf"\b{stem}\b.*{name}(?![\w-])")
    return re.compile(rf"(?:^|\s|[\"']){name}[\"']?\s*:")


def count_sites(symbols, files, repo):
    """Fill each symbol's sites from the production files."""
    patterns = [(s, _site_pattern(s)) for s in symbols]
    for full, lines in files:
        rel = _relative(full, repo)
        text = "\n".join(lines)
        live = [(s, p) for s, p in patterns if _may_call(s, rel, text)]
        for number, line in enumerate(lines, start=1):
            is_def = DEF_RE.match(line)
            for symbol, pattern in live:
                if not pattern.search(line):
                    continue
                if is_def and is_def.group(1) in (symbol.name, symbol.owner):
                    continue
                if symbol.kind == "config-key" and rel == symbol.path and number == symbol.line:
                    continue
                symbol.sites.append(f"{rel}:{number}")


def _may_call(symbol, rel, text):
    """A function is reached from its own module or a file naming that module; a flag only from elsewhere."""
    same_file = rel == symbol.path
    if symbol.kind == "flag":
        return not same_file
    if symbol.kind in ("function", "param"):
        return same_file or re.search(rf"\b{re.escape(Path(symbol.path).stem)}\b", text) is not None
    return True


def _relative(full, repo):
    try:
        return Path(full).resolve().relative_to(Path(repo).resolve()).as_posix()
    except ValueError:
        return Path(full).as_posix()


def _parser():
    parser = argparse.ArgumentParser(description="Report added symbols with no production caller (heuristic).")
    parser.add_argument("--repo", required=True, help="git repository that holds the base and the paths")
    parser.add_argument("--base", required=True, help="the pinned base sha; never a bare diff")
    parser.add_argument("--production", action="append", default=None,
                        help="production directory to search (repeatable); tests are always excluded")
    parser.add_argument("paths", nargs="+", help="paths to diff, after --")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    repo = Path(args.repo)
    try:
        # git diff prints paths relative to the top level, whatever --repo is,
        # so every path here is keyed relative to the top level.
        top = Path(_git(repo, ["rev-parse", "--show-toplevel"]).strip())
        diff = _git(repo, ["diff", args.base, "--", *args.paths])
        diff += "\n" + untracked_as_diff(repo, args.paths, top)
    except (RuntimeError, OSError) as exc:
        print(f"Error: check_symbol_callers cannot read the diff: {exc}", file=sys.stderr)
        return 2
    symbols = parse_diff(diff)
    if args.production:
        roots = [Path(p) if Path(p).is_absolute() else repo / p for p in args.production]
    else:
        roots = [top / "plugins" / "planwise" / d for d in DEFAULT_PRODUCTION]
    missing = [str(r) for r in roots if not r.is_dir()]
    if args.production and missing:
        print(f"Error: production directory not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    count_sites(symbols, production_files(r for r in roots if r.is_dir()), top)
    print(f"{len(symbols)} added symbols scanned")
    zero = 0
    for symbol in symbols:
        shown = ", ".join(symbol.sites[:MAX_SITES])
        mark = "ZERO " if not symbol.sites else ""
        zero += not symbol.sites
        tail = f": {shown}" if shown else ""
        print(f"{mark}{symbol.label()} ({symbol.path}:{symbol.line}): {len(symbol.sites)} call sites{tail}")
    if zero:
        print(f"{zero} symbols with zero call sites (heuristic report; it does not decide COMPLETE)")
    return 1 if zero else 0


if __name__ == "__main__":
    sys.exit(main())
