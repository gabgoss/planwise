#!/usr/bin/env python3
"""Compute the `/code-review` tier of a working-tree diff.

A caller that runs `/code-review` after a change asks this script which tier
to pass. The script is the one place that holds the tier thresholds, so a
caller never restates them. It reads the real diff against HEAD, staged and
unstaged, plus every untracked file. A new file never shows in a plain
`git diff`, so the script counts each untracked file as wholly added. In a
repository with no commit yet, it diffs against the empty tree.

Usage:
    review_tier.py [--config <config.yaml>] [--repo <path>]
                   [--judged deleted-symbol|return-shape]... [path ...]

Every path, in the output and in the scope, is relative to `--repo`, and
only files under `--repo` are read. Optional positional paths scope the diff
to those files or folders.

A code file is a file whose suffix is a default source or config suffix, or
a file that matches a glob in the config's `review_tier.code_globs` list.
A trailing `.template`, `.example` or `.sample` suffix is ignored, so
`config.yaml.template` reads as a config file. A glob matches the whole
path or any tail of it that starts at a folder boundary, so `agents/**`
matches `agents/a.md` and `plugins/x/agents/a.md`. A `**/` matches zero or
more folders, so `**/*.md` also matches a top-level `README.md`.

The tier comes from the code-file count and the changed code lines (added
plus deleted). Each escalator that fires raises the tier by one step, and
never past high. A tier of none stays none. The mechanical escalators are:

    hook-settings-permission  a changed code file under a hooks folder, a
                              settings*.json file, or a path naming permission
    new-module                an added or untracked source file
    file-delete               an added code line that deletes or moves files

The session judges two more and passes them with `--judged`:

    deleted-symbol            a deleted or renamed public symbol
    return-shape              a changed return shape

Output, four LF-only lines in this order:

    tier: none|low|medium|high
    code_files: <n>
    code_lines: <n>
    escalators: <comma list>|none

The tier is never max or ultra. Those levels need an explicit user request.

Exit codes: 0 tier printed; 2 usage error, git error or unreadable config.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

# Import shared helpers from the sibling scripts
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from config_loader import load_config

# The thresholds. Every reader takes them from here or from `--help`.
LOW_MAX_FILES = 2
LOW_MAX_LINES = 100
MEDIUM_MAX_FILES = 8
MEDIUM_MAX_LINES = 500

TIERS = ("none", "low", "medium", "high")

SOURCE_SUFFIXES = frozenset({
    ".py", ".pyw", ".ps1", ".psm1", ".sh", ".bash", ".bat", ".cmd",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".kt", ".cs", ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".swift", ".sql", ".lua", ".pl",
})
CONFIG_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"})
IGNORED_TRAILING_SUFFIXES = frozenset({".template", ".example", ".sample"})

HOOK_SETTINGS = "hook-settings-permission"
NEW_MODULE = "new-module"
FILE_DELETE = "file-delete"
JUDGED = ("deleted-symbol", "return-shape")

# A call that deletes or moves files or folders, matched on an added code line.
FILE_DELETE_RE = re.compile(
    r"\bos\.remove\b|\bunlink\b|\brmtree\b|\brmdir\b|\bos\.removedirs\b"
    r"|\bshutil\.move\b|\bos\.rename\b|\bos\.replace\b|\.rename\("
    r"|\bgit\s+(?:-C\s+\S+\s+)?(?:rm|mv)\b|(?<![\w.$-])(?:rm|mv)\s"
    r"|\bRemove-Item\b|\bMove-Item\b|\bfs\.(?:rm|rmSync|rename|renameSync|unlinkSync)\b"
)
# `del` and `rd` delete files only in cmd and PowerShell. In Python `del` is a statement.
SHELL_DELETE_RE = re.compile(r"(?<![\w.$-])(?:del|rd|erase)\s", re.IGNORECASE)
SHELL_DELETE_SUFFIXES = frozenset({".bat", ".cmd", ".ps1", ".psm1"})
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# Flags that make git print a plain patch whatever the user's diff config says.
PLAIN_DIFF = ("--no-ext-diff", "--no-textconv", "--no-color", "--no-renames")


class TierError(Exception):
    """The diff or the config could not be read."""


def _emit(lines: list[str]) -> None:
    """Write lines to stdout with LF endings on every platform."""
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))
    sys.stdout.flush()


def _git(repo: Path, *args: str) -> bytes:
    """Run one git command in `repo` and return its raw stdout."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "-c", "core.quotepath=off", *args],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise TierError(f"git could not run: {exc}") from exc
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip()
        raise TierError(f"git {args[0]} failed: {msg}")
    return proc.stdout


def _glob_regex(pattern: str) -> re.Pattern:
    """Translate a path glob: `**` crosses folders, `*` and `?` do not.

    A `**/` matches zero or more whole folders, so `**/*.md` matches `a.md`.
    """
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _glob_matches(path: str, regexes: list[re.Pattern]) -> bool:
    """True when a glob matches the path or a tail of it at a folder boundary."""
    parts = path.split("/")
    tails = ["/".join(parts[i:]) for i in range(len(parts))]
    return any(rx.match(tail) for rx in regexes for tail in tails)


def _suffix(path: str) -> str:
    """Return the path's suffix, skipping one template-style trailing suffix."""
    p = PurePosixPath(path)
    if p.suffix.lower() in IGNORED_TRAILING_SUFFIXES:
        p = PurePosixPath(p.stem)
    return p.suffix.lower()


def is_source(path: str) -> bool:
    return _suffix(path) in SOURCE_SUFFIXES


def is_code(path: str, glob_regexes: list[re.Pattern]) -> bool:
    suffix = _suffix(path)
    if suffix in SOURCE_SUFFIXES or suffix in CONFIG_SUFFIXES:
        return True
    return _glob_matches(path, glob_regexes)


def is_hook_settings_permission(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    if "hooks" in parts[:-1]:
        return True
    if name.startswith("settings") and name.endswith(".json"):
        return True
    return "permission" in path.lower()


def read_code_globs(config_path: Path | None) -> list[str]:
    """Return `review_tier.code_globs` from the config, or [] when absent."""
    if config_path is None:
        return []
    if not config_path.is_file():
        raise TierError(f"config not found: {config_path}")
    try:
        config = load_config(config_path=config_path)
    except Exception as exc:  # any parse or read failure is an unreadable config
        raise TierError(f"config could not be read: {config_path}: {exc}") from exc
    if not isinstance(config, dict):
        return []
    block = config.get("review_tier")
    if not isinstance(block, dict):
        return []
    globs = block.get("code_globs")
    if not isinstance(globs, list):
        return []
    return [g for g in globs if isinstance(g, str) and g.strip()]


def tier_from_counts(code_files: int, code_lines: int) -> str:
    """Apply the threshold table to the two counts."""
    if code_files == 0:
        return "none"
    if code_files > MEDIUM_MAX_FILES or code_lines > MEDIUM_MAX_LINES:
        return "high"
    if code_files > LOW_MAX_FILES or code_lines > LOW_MAX_LINES:
        return "medium"
    return "low"


def escalate(tier: str, steps: int) -> str:
    """Raise a tier by `steps`, capped at high. None stays none."""
    if tier == "none":
        return "none"
    return TIERS[min(TIERS.index(tier) + steps, len(TIERS) - 1)]


def _split_z(raw: bytes) -> list[str]:
    return [f for f in raw.decode("utf-8", "replace").split("\0") if f]


def _line_count(data: bytes) -> int:
    if not data or b"\0" in data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def _base(repo: Path) -> str:
    """Return HEAD, or the empty tree when the repository has no commit yet."""
    try:
        _git(repo, "rev-parse", "--verify", "-q", "HEAD")
    except TierError:
        return EMPTY_TREE
    return "HEAD"


def _diff(repo: Path, base: str, *args: str) -> bytes:
    """Run `git diff` against `base` with paths relative to `repo`."""
    return _git(repo, "diff", base, "--relative", *PLAIN_DIFF, *args)


def collect(repo: Path, paths: list[str], glob_regexes: list[re.Pattern]) -> dict:
    """Read the diff and return the counts and the mechanical escalators."""
    scope = ["--", *paths] if paths else []
    base = _base(repo)
    files: dict[str, dict] = {}

    for entry in _split_z(_diff(repo, base, "--numstat", "-z", *scope)):
        added, deleted, path = entry.split("\t", 2)
        lines = (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
        files[path] = {"lines": lines, "added": False, "text": None}

    status = _split_z(_diff(repo, base, "--name-status", "-z", *scope))
    for code, path in zip(status[0::2], status[1::2]):
        if code.startswith("A") and path in files:
            files[path]["added"] = True

    for path in _split_z(_git(repo, "ls-files", "--others", "--exclude-standard", "-z", *scope)):
        try:
            data = (repo / path).read_bytes()
        except OSError:
            continue
        files[path] = {"lines": _line_count(data), "added": True, "text": data.decode("utf-8", "replace")}

    code_paths = sorted(p for p in files if is_code(p, glob_regexes))
    escalators = []
    if any(is_hook_settings_permission(p) for p in code_paths):
        escalators.append(HOOK_SETTINGS)
    if any(files[p]["added"] and is_source(p) for p in code_paths):
        escalators.append(NEW_MODULE)
    if any(_adds_file_delete(repo, base, p, files[p]["text"]) for p in code_paths):
        escalators.append(FILE_DELETE)

    return {
        "code_files": len(code_paths),
        "code_lines": sum(files[p]["lines"] for p in code_paths),
        "escalators": escalators,
    }


def is_file_delete_line(path: str, line: str) -> bool:
    """True when one code line calls a delete or a move."""
    if FILE_DELETE_RE.search(line):
        return True
    return _suffix(path) in SHELL_DELETE_SUFFIXES and bool(SHELL_DELETE_RE.search(line))


def added_lines(patch: str) -> list[str]:
    """Return the added lines of a one-file `-U0` patch.

    Every line before the first `@@` is a header, whatever prefix or quoting
    the user's git config gives it. Inside a hunk an added line starts with
    `+`, even when its own text starts with `++`.
    """
    out = []
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith("+"):
            out.append(line[1:])
    return out


def _adds_file_delete(repo: Path, base: str, path: str, untracked_text: str | None) -> bool:
    """True when an added line of one code file calls a delete or a move."""
    if untracked_text is not None:
        lines = untracked_text.splitlines()
    else:
        patch = _diff(repo, base, "-U0", "--", f":(literal){path}")
        lines = added_lines(patch.decode("utf-8", "replace"))
    return any(is_file_delete_line(path, line) for line in lines)


def _epilog() -> str:
    return (
        "Tier thresholds (code files, changed code lines):\n"
        "  none    0 code files\n"
        f"  low     1 to {LOW_MAX_FILES} code files and at most {LOW_MAX_LINES} lines\n"
        f"  medium  {LOW_MAX_FILES + 1} to {MEDIUM_MAX_FILES} code files, "
        f"or {LOW_MAX_LINES + 1} to {MEDIUM_MAX_LINES} lines\n"
        f"  high    more than {MEDIUM_MAX_FILES} code files, or more than {MEDIUM_MAX_LINES} lines\n"
        "Each escalator raises the tier one step, capped at high. None stays none."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute the /code-review tier of a working-tree diff.",
        epilog=_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", type=Path, help="planwise config.yaml that may carry review_tier.code_globs")
    parser.add_argument("--repo", type=Path, default=Path("."), help="git repository to read (default: .)")
    parser.add_argument("--judged", action="append", choices=JUDGED, default=[],
                        help="an escalator the session judged; repeatable")
    parser.add_argument("paths", nargs="*", help="optional paths that scope the diff")
    args = parser.parse_args(argv)

    try:
        globs = read_code_globs(args.config)
        result = collect(args.repo, args.paths, [_glob_regex(g) for g in globs])
    except (TierError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    escalators = result["escalators"] + [j for j in JUDGED if j in args.judged]
    tier = escalate(tier_from_counts(result["code_files"], result["code_lines"]), len(escalators))
    _emit([
        f"tier: {tier}",
        f"code_files: {result['code_files']}",
        f"code_lines: {result['code_lines']}",
        f"escalators: {', '.join(escalators) if escalators else 'none'}",
    ])
    return 0


if __name__ == "__main__":
    sys.exit(main())
