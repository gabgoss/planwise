#!/usr/bin/env python3
"""Shared scaffolding for index-drift reconcile scripts.

A reconcile script (e.g. one comparing a denormalized index against its
source of truth) pairs a read-only `detect_drift(config)` with a
race-safe `reconcile(config)` and exposes both through an identical
`--config`/`--write`/`--json` CLI. The domain logic — what counts as
drift, and how to heal it — is intentionally NOT here; only the
scaffolding that would otherwise be re-implemented identically by every
such script lives in this module:

  - `write_json_result(result, prefix)`: write a detect_drift result to a
    JSON temp file, returning its path.
  - `format_drift_report(...)`: the shared drift/anomaly report banner
    shape, parameterized by the caller's domain-specific messages and
    per-row line renderers.
  - `run_reconcile_cli(...)`: the shared `--config`/`--write`/`--json`
    argparse wiring and control flow, parameterized by the caller's own
    config loader, index-path resolver, and detect_drift/reconcile/
    format_report functions.
  - `read_text_preserving_newlines` / `write_text_preserving_newlines`:
    the race-safe-reread + CRLF discipline a destructive reconcile write
    depends on. A destructive write must re-read the index immediately
    before writing (race-safe: a row healed by a concurrent writer since
    an earlier detect() call is read as non-drifted and left untouched)
    and must preserve the file's original line endings exactly — reading
    and writing with `newline=""` disables Python's universal-newline
    translation, so a CRLF file's `\\r\\n` round-trips byte-for-byte
    instead of being rewritten to the platform's `os.linesep` on every
    line, including ones the caller never touched.
  - `AnchoredEdit` / `Rename` / `apply_anchored_edits`: a verified write
    transaction. Every anchor must match exactly once (or sit at a pinned
    offset), an optional pre-state check and a caller invariant must hold,
    and any refusal writes nothing. `prose_mentions` lists the `*.md`
    lines that still name a token, for a caller that reports instead of
    rewriting prose.

Stdlib-only.
"""

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


def read_text_preserving_newlines(path: Path) -> str:
    """Read a file's raw text with newline="" so its original line endings
    (LF or CRLF) survive untranslated into the returned string. Pair with
    `write_text_preserving_newlines` for a byte-exact round-trip on any
    line the caller does not modify. See the module docstring for the
    full race-safe-reread + CRLF discipline this supports.
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text_preserving_newlines(path: Path, content: str) -> None:
    """Write text verbatim with newline="" so no os.linesep translation
    occurs, preserving the file's original CRLF/LF exactly.

    Atomic: the content goes to a temp file in the same directory, named
    `.{name}.tmp-*` so no `*.md` glob matches it, and `os.replace` then
    swaps it onto the target. A failure at any step removes the temp file
    and re-raises, leaving the target's original bytes untouched.
    """
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    try:
        with open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        if path.exists():
            # mkstemp creates the temp file owner-only; keep the target's mode.
            os.chmod(tmp_name, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class AnchoredWriteError(Exception):
    """An anchored write was refused before any file changed.

    Raised by `apply_anchored_edits` for a zero-match or multi-match anchor,
    an anchor not at its pinned offset, a failed pre-state or invariant
    check, an overlapping edit, a missing rename source or an existing
    rename target. It is also re-raised after an I/O failure, once the
    helper has rolled every written file and rename back.
    """


@dataclass(frozen=True)
class AnchoredEdit:
    """One text replacement in one file.

    `anchor` must occur exactly once in the file's text. When `at` is set,
    the anchor must instead sit at that character offset, so a strip of a
    line whose text also repeats elsewhere (for example inside a code
    fence) stays legal. `expect_pre`, when set, receives the file's text
    before any edit and returns True when the file is in the expected
    state. A file's edits are all located against its original text and
    must not overlap.
    """

    path: Path
    anchor: str
    replacement: str
    at: int | None = None
    expect_pre: Callable[[str], bool] | None = None


@dataclass(frozen=True)
class Rename:
    """Move `src` to `dst` after the edits are written. `dst` must be free."""

    src: Path
    dst: Path


def _locate_edit(text: str, edit: AnchoredEdit) -> int:
    """Return the offset where `edit.anchor` applies, or raise."""
    if not edit.anchor:
        raise AnchoredWriteError(f"{edit.path}: empty anchor")
    if edit.at is not None:
        if text[edit.at : edit.at + len(edit.anchor)] != edit.anchor:
            raise AnchoredWriteError(f"{edit.path}: anchor {edit.anchor!r} is not at offset {edit.at}")
        return edit.at
    count = text.count(edit.anchor)
    if count != 1:
        raise AnchoredWriteError(f"{edit.path}: anchor {edit.anchor!r} matches {count} times, expected exactly 1")
    return text.index(edit.anchor)


def _plan_edits(edits: Sequence[AnchoredEdit]) -> tuple[dict[Path, str], dict[Path, str]]:
    """Phase 1: read each file once, validate every edit, return (original, planned) texts."""
    by_path: dict[Path, list[AnchoredEdit]] = {}
    for edit in edits:
        by_path.setdefault(Path(edit.path), []).append(edit)
    originals: dict[Path, str] = {}
    planned: dict[Path, str] = {}
    for path, group in by_path.items():
        try:
            text = read_text_preserving_newlines(path)
        except OSError as exc:
            raise AnchoredWriteError(f"{path}: cannot read ({exc})") from exc
        for edit in group:
            if edit.expect_pre is not None and not edit.expect_pre(text):
                raise AnchoredWriteError(f"{path}: pre-state check failed")
        spans = sorted(((_locate_edit(text, e), e) for e in group), key=lambda span: span[0])
        end_of_previous = 0
        for start, edit in spans:
            if start < end_of_previous:
                raise AnchoredWriteError(f"{path}: two edits overlap at offset {start}")
            end_of_previous = start + len(edit.anchor)
        out = text
        for start, edit in reversed(spans):
            out = out[:start] + edit.replacement + out[start + len(edit.anchor) :]
        originals[path] = text
        planned[path] = out
    return originals, planned


def _check_renames(renames: Sequence[Rename]) -> None:
    targets: set[str] = set()
    for rename in renames:
        src, dst = Path(rename.src), Path(rename.dst)
        if not src.exists():
            raise AnchoredWriteError(f"{src}: rename source does not exist")
        if os.path.lexists(dst):
            raise AnchoredWriteError(f"{dst}: rename target already exists")
        key = os.path.normcase(str(dst))
        if key in targets:
            raise AnchoredWriteError(f"{dst}: two renames share this target")
        targets.add(key)


def apply_anchored_edits(
    edits: Sequence[AnchoredEdit],
    renames: Sequence[Rename] = (),
    invariant: Callable[[dict[Path, str]], str | None] | None = None,
) -> list[str]:
    """Apply anchored edits and renames as one verified transaction.

    Phase 1 reads each file once and plans every edit in memory. An
    unpinned anchor must occur exactly once, a pinned anchor must sit at
    its offset, and an `expect_pre` check must hold. Phase 2 runs
    `invariant(planned)`, where `planned` maps each edited path to its
    post-edit text. The invariant returns None when the planned state is
    sound, or a message when it is not. Any refusal raises
    `AnchoredWriteError` having written nothing.

    Phase 3 writes each changed file once through
    `write_text_preserving_newlines`, then runs the renames. On an I/O
    error the helper reverses the renames, restores each written file from
    memory and re-raises the error. Cross-file atomicity is therefore
    per-file `os.replace` plus in-memory rollback, not one OS transaction.

    Returns one report line per changed file and per rename.
    """
    originals, planned = _plan_edits(edits)
    _check_renames(renames)
    if invariant is not None:
        problem = invariant(dict(planned))
        if problem:
            raise AnchoredWriteError(f"invariant failed: {problem}")

    written: list[Path] = []
    renamed: list[Rename] = []
    report: list[str] = []
    try:
        for path, text in planned.items():
            if text == originals[path]:
                continue
            write_text_preserving_newlines(path, text)
            written.append(path)
            report.append(f"{path}: edited")
        for rename in renames:
            os.rename(rename.src, rename.dst)
            renamed.append(rename)
            report.append(f"{rename.src} -> {rename.dst}")
    except BaseException:
        for rename in reversed(renamed):
            try:
                os.rename(rename.dst, rename.src)
            except OSError:
                pass
        for path in written:
            try:
                write_text_preserving_newlines(path, originals[path])
            except OSError:
                pass
        raise
    return report


def prose_mentions(root: Path, token: str) -> list[str]:
    """List `path:line` rows for each `*.md` line under `root` that names `token`.

    The match is `(?<![\\w-])TOKEN(?!\\d)`, so the token `ID-12` does not
    match `ID-123` or `XID-12`. Paths print relative to `root` with forward
    slashes. A file that is not valid UTF-8 is skipped.
    """
    pattern = re.compile(r"(?<![\w-])" + re.escape(token) + r"(?!\d)")
    root = Path(root)
    rows: list[str] = []
    for md in sorted(root.rglob("*.md")):
        try:
            text = read_text_preserving_newlines(md)
        except (OSError, UnicodeDecodeError):
            continue
        rel = md.relative_to(root).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rows.append(f"{rel}:{number}")
    return rows


def regenerate_index(script_name: str, config: dict) -> int:
    """Run a sibling index generator with `--write` and return its exit code.

    `script_name` is a file beside this module, for example
    `generate_lessons_index.py`. The config path is the `config.yaml` that
    sits in the planwise root, which is where `config_loader` reads it.
    The generator's output is printed so the caller's report carries it.
    """
    import subprocess

    script = Path(__file__).resolve().parent / script_name
    config_file = Path(config["_planwise_root"]) / "config.yaml"
    done = subprocess.run(
        [sys.executable, "-B", str(script), "--config", str(config_file), "--write"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    for stream in (done.stdout, done.stderr):
        if stream.strip():
            print(stream.rstrip())
    return done.returncode


def write_json_result(result: dict, prefix: str) -> str:
    """Write a detect_drift result to a JSON temp file and return its path.

    `prefix` names the caller (e.g. "reconcile-plans-") so concurrent
    callers' temp directories stay distinguishable.
    """
    tmp_dir = tempfile.mkdtemp(prefix=prefix)
    json_path = os.path.join(tmp_dir, "drift.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return json_path


def format_drift_report(
    result: dict,
    *,
    no_drift_message: str,
    no_drift_only_message: str,
    drift_header: str,
    drift_line: Callable[[dict], str],
    anomaly_line: Callable[[dict], str],
) -> str:
    """Render a human-readable drift + anomaly report.

    Shared banner shape: an early-return "nothing to report" message when
    both `result["drifts"]` and `result["anomalies"]` are empty; otherwise
    a drift section (the caller-supplied header followed by one
    `drift_line` per drift, or `no_drift_only_message` when there are
    anomalies but no drifts) followed by a blank-line-separated anomaly
    section when anomalies exist. `drift_header` is a fully-formatted
    string (it already embeds the drift count) rather than a template,
    since callers' headers differ beyond a simple count substitution.
    `drift_line`/`anomaly_line` render one row each, since callers'
    drift/anomaly dict shapes differ.
    """
    drifts = result["drifts"]
    anomalies = result["anomalies"]
    lines = []

    if not drifts and not anomalies:
        return no_drift_message

    if drifts:
        lines.append(drift_header)
        for d in drifts:
            lines.append(drift_line(d))
    else:
        lines.append(no_drift_only_message)

    if anomalies:
        if lines:
            lines.append("")
        lines.append(f"Anomalies ({len(anomalies)}):")
        for a in anomalies:
            lines.append(anomaly_line(a))

    return "\n".join(lines)


def run_reconcile_cli(
    *,
    description: str,
    load_config: Callable[[], dict],
    resolve_index_path: Callable[[dict], Path],
    missing_index_message: Callable[[Path], str],
    detect_drift: Callable[[dict], dict],
    reconcile: Callable[[dict], int],
    format_report: Callable[[dict], str],
    json_prefix: str,
    write_message: Callable[[int], str] = lambda n: f"Reconciled {n} row(s).",
    mode_flags: tuple[str, ...] = (),
) -> None:
    """Shared CLI scaffold for a reconcile script's `main()`.

    Builds the `--config`/`--write`/`--json` argparse surface, resolves
    the index path, exits 1 with `missing_index_message(index_path)` on
    stderr if it does not exist, then dispatches: `--write` reconciles
    (printing `write_message(count)`, plus a fresh `--json` detect_drift
    dump if requested); otherwise runs `detect_drift` and prints
    `format_report(result)` (plus `--json` if requested).

    Domain logic stays with the caller: `load_config`,
    `resolve_index_path`, `detect_drift`, `reconcile`, and `format_report`
    are all supplied by it, since different callers locate their index
    differently (a function call vs. a config dict key) and implement
    different drift semantics. `--config` is declared so `parse_args`
    accepts an explicit `--config <path>` on the command line;
    `load_config` itself is responsible for reading it back out of
    `sys.argv` (matching `config_loader.load_config`'s own contract), not
    this scaffold. An unrecognized flag exits 2. `write_message` is optional. It
    defaults to "Reconciled N row(s).", and a caller whose `--write` does
    not reconcile rows passes its own noun. `mode_flags` names flags the caller
    already consumed in its own pre-parse. The scaffold declares each one so
    the main parse accepts it, and ignores its value.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml; overrides default config search.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Reconcile drifted rows (re-reads the index immediately before writing).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Additionally write a JSON temp file and print its path.",
    )
    for flag in mode_flags:
        parser.add_argument(flag, action="store_true", help="Mode switch, read before this parser runs.")

    args = parser.parse_args()

    config = load_config()
    index_path = resolve_index_path(config)

    if not index_path.exists():
        print(missing_index_message(index_path), file=sys.stderr)
        sys.exit(1)

    if args.write:
        written = reconcile(config)
        print(write_message(written))
        if args.json:
            result = detect_drift(config)
            json_path = write_json_result(result, json_prefix)
            print(f"JSON: {json_path}")
        return

    result = detect_drift(config)
    print(format_report(result))

    if args.json:
        json_path = write_json_result(result, json_prefix)
        print(f"JSON: {json_path}")
