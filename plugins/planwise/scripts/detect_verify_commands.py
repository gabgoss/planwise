#!/usr/bin/env python3
"""Propose `build_commands.verify` candidates from a repository's own test and lint setup.

The detector is read-only. It opens files for reading only, starts no subprocess,
and writes nothing. `scripts/set_verify_commands.py` stores the commands a person
accepts.

## Usage

    python detect_verify_commands.py --root <dir>

## Output

One JSON line per candidate, with the keys in this order:

| Key | Value |
|---|---|
| `command` | The command to run from the repository root. Candidates are deduplicated by this string, and the first source in the table below to name a command keeps it |
| `kind` | `test`, `lint` or `other` |
| `source` | The file the signal came from, relative to `--root`, with forward slashes |
| `confidence` | `high` or `low` |

A directory with no signal prints nothing and exits 0. A `--root` that is not a
directory prints one line on stderr and exits 1.

## Confidence

`high` needs both a tool-specific config signal and an executable that resolves
through `shutil.which`. `low` covers a Makefile target, a CI run line, a .NET
signal, and any candidate whose executable does not resolve. Every candidate is
printed, so a caller offers the low ones too.

## Signals, in the order they are read

| Source | Candidates |
|---|---|
| `pyproject.toml` | `pytest` for a `[tool.pytest.ini_options]` table, `ruff check .` for a `[tool.ruff]` table or a table below it |
| `pytest.ini` | `pytest` for a `[pytest]` section |
| `setup.cfg` | `pytest` for a `[tool:pytest]` section, `flake8` for a `[flake8]` section |
| `ruff.toml`, `.ruff.toml` | `ruff check .` |
| `.flake8` | `flake8` |
| `package.json` | `npm test` for `scripts.test` and `npm run lint` for `scripts.lint`. The placeholder `npm init` writes for `scripts.test` is skipped |
| `Cargo.toml` | `cargo test` |
| `go.mod` | `go test ./...` and `go vet ./...` |
| `*.csproj`, `*.sln` in the root | `dotnet test`, always low |
| `Makefile` | `make test` and `make lint` for those targets, `make check` as kind `other`, always low |
| `.github/workflows/*.yml`, `*.yaml` | Each single-line `run:` command that is a test or lint command, always low |
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

HIGH = "high"
LOW = "low"
NPM_PLACEHOLDER_RE = re.compile(r"no test specified", re.IGNORECASE)
SETUP_PREFIXES = (
    "pip ",
    "pip3 ",
    "python -m pip ",
    "python3 -m pip ",
    "npm ci",
    "npm install",
    "npm i ",
    "yarn install",
    "pnpm install",
    "apt",
    "brew ",
    "echo ",
    "mkdir ",
)
TEST_WORDS_RE = re.compile(r"\b(?:pytest|unittest|tox|nox|jest|vitest|mocha|test|tests)\b", re.IGNORECASE)
LINT_WORDS_RE = re.compile(r"\b(?:ruff|flake8|pylint|eslint|clippy|golangci-lint|lint|mypy)\b", re.IGNORECASE)
RUN_LINE_RE = re.compile(r"^\s*(?:-\s+)?run:\s+(?P<command>\S.*?)\s*$")


def _read(path: Path) -> str:
    """Return the file's text, or an empty string when it cannot be read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            return stream.read()
    except OSError:
        return ""


class Collector:
    """Collects candidates in first-seen order and drops a repeated command."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._seen: set[str] = set()

    def add(self, command: str, kind: str, source: str, signal: bool) -> None:
        """Record one candidate. `signal` is True for a tool-specific config signal."""
        if command in self._seen:
            return
        self._seen.add(command)
        executable = command.split()[0]
        confident = signal and shutil.which(executable) is not None
        self.rows.append(
            {"command": command, "kind": kind, "source": source, "confidence": HIGH if confident else LOW}
        )


def _has_section(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.MULTILINE) is not None


def _read_python_signals(root: Path, out: Collector) -> None:
    text = _read(root / "pyproject.toml")
    if text:
        if _has_section(text, r"^\[tool\.pytest\.ini_options\]"):
            out.add("pytest", "test", "pyproject.toml", True)
        if _has_section(text, r"^\[tool\.ruff(?:[.\]])"):
            out.add("ruff check .", "lint", "pyproject.toml", True)
    if _has_section(_read(root / "pytest.ini"), r"^\[pytest\]"):
        out.add("pytest", "test", "pytest.ini", True)
    cfg = _read(root / "setup.cfg")
    if _has_section(cfg, r"^\[tool:pytest\]"):
        out.add("pytest", "test", "setup.cfg", True)
    if _has_section(cfg, r"^\[flake8\]"):
        out.add("flake8", "lint", "setup.cfg", True)
    for name in ("ruff.toml", ".ruff.toml"):
        if (root / name).is_file():
            out.add("ruff check .", "lint", name, True)
    if (root / ".flake8").is_file():
        out.add("flake8", "lint", ".flake8", True)


def _read_package_json(root: Path, out: Collector) -> None:
    text = _read(root / "package.json")
    if not text:
        return
    try:
        data = json.loads(text)
    except ValueError:
        return
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return
    test = scripts.get("test")
    if isinstance(test, str) and test.strip() and not NPM_PLACEHOLDER_RE.search(test):
        out.add("npm test", "test", "package.json", True)
    lint = scripts.get("lint")
    if isinstance(lint, str) and lint.strip():
        out.add("npm run lint", "lint", "package.json", True)


def _read_other_toolchains(root: Path, out: Collector) -> None:
    if (root / "Cargo.toml").is_file():
        out.add("cargo test", "test", "Cargo.toml", True)
    if (root / "go.mod").is_file():
        out.add("go test ./...", "test", "go.mod", True)
        out.add("go vet ./...", "lint", "go.mod", True)
    for pattern in ("*.csproj", "*.sln"):
        for path in sorted(root.glob(pattern)):
            out.add("dotnet test", "test", path.name, False)


def _read_makefile(root: Path, out: Collector) -> None:
    text = _read(root / "Makefile")
    if not text:
        return
    for target, kind in (("test", "test"), ("lint", "lint"), ("check", "other")):
        if _has_section(text, rf"^{target}\s*:"):
            out.add(f"make {target}", kind, "Makefile", False)


def _classify(command: str) -> "str | None":
    """Return `test` or `lint` for a CI run line worth offering, otherwise None."""
    if command.startswith(SETUP_PREFIXES) or "${{" in command:
        return None
    if LINT_WORDS_RE.search(command):
        return "lint"
    if TEST_WORDS_RE.search(command):
        return "test"
    return None


def _read_workflows(root: Path, out: Collector) -> None:
    folder = root / ".github" / "workflows"
    if not folder.is_dir():
        return
    files = sorted(list(folder.glob("*.yml")) + list(folder.glob("*.yaml")))
    for path in files:
        source = f".github/workflows/{path.name}"
        for line in _read(path).splitlines():
            match = RUN_LINE_RE.match(line)
            if match is None:
                continue
            command = match.group("command")
            if command[:1] in "|>":
                continue
            kind = _classify(command)
            if kind is not None:
                out.add(command, kind, source, False)


def detect(root: Path) -> "list[dict]":
    """Return the candidates for the repository at `root`, in source order."""
    out = Collector()
    _read_python_signals(root, out)
    _read_package_json(root, out)
    _read_other_toolchains(root, out)
    _read_makefile(root, out)
    _read_workflows(root, out)
    return out.rows


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Propose build_commands.verify candidates (read-only).")
    parser.add_argument("--root", required=True, help="the repository root to inspect")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f"detect_verify_commands: {root} is not a directory", file=sys.stderr)
        return 1
    for row in detect(root):
        print(json.dumps(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
