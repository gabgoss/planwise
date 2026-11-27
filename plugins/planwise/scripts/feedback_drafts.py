#!/usr/bin/env python3
"""Shared helper for model-drafted feedback files (stdlib only).

Producers and the review surface call this one script to list, admit, create,
discard, promote and expire model-drafted feedback, to switch on posting, to report whether posting is on, to switch drafting off, and to print the resolved feedback directory.

## The draft file

A model draft lives directly in the feedback directory, named
`{YYYY-MM-DD}-draft-{kind}-{slug}.md`, and starts with a YAML frontmatter block
holding the keys in `FRONTMATTER_KEYS`. Every command acts only on names that
match `DRAFT_NAME_RE` whose frontmatter re-reads `drafted_by: model`. A
hand-written feedback draft, a posted-marker sidecar, and anything under
`Archive/` are never listed, rewritten or deleted.

## Commands and exit codes

| Command | Behaviour | Exit |
|---|---|---|
| `list [--json] [--all]` | Read-only. Reports a queued draft past `EXPIRY_DAYS` as expired without writing it. Reports a promoted draft whose promoted file has an active `.blocked` sidecar as blocked without writing it. Then lists queued, blocked and expired drafts. `--all` adds discarded and promoted. A blocked draft keeps `status: promoted` on disk | 0 |
| `list --table [--all] [--session-id <id>]` | Same groups as `list`, also read-only, printed as one `Queued (n)` / `Blocked by the privacy check (n)` / `Expired (n)` table per group, newest `created_at` first. The Session column uses `--session-id`, else the `CLAUDE_CODE_SESSION_ID` environment variable, else prints `unknown`. Not with `--json` (exit 2) | 0 |
| `sweep-list` | Read-only. Prints each `*.md` file that has a `.md.posted` sidecar and is not a model draft, with its `posted:`, `url:` and `route:` values, then a `blocked sidecar:` line for a candidate that also has a `.blocked` sidecar, then each orphan `.posted` or `.blocked` sidecar and a summary line | 0 |
| `admit <path>` | Needs `--feedback-dir` or `--config`, and the file directly in that directory. A draft already `expired`, `discarded` or `promoted` is left untouched. Otherwise needs `status` to be `pending` or `queued`, no duplicated frontmatter key, and a parseable `created_at`. Fills `pending` ids, replaces a colliding id, replaces a future `created_at` with now, refuses and deletes an oversize or duplicate-title model draft or one whose parsed frontmatter is invalid, refuses and keeps a file whose frontmatter does not parse, then runs expiry and eviction and names each draft it evicts on stderr | 0 admitted, 1 file missing, config unreadable or the directory lock not obtained, 2 name does not match, no usable directory option, `Archive/` directory, file not directly in the directory, or a draft already expired, discarded or promoted, 3 refused, expired on admission, or evicted on admission |
| `create` | Reads the draft text as UTF-8 from stdin. Needs `--feedback-dir` or `--config`, and creates a missing feedback directory. Runs the frontmatter checks of `admit` and refuses a duplicate title before any file is written. Names the file `{date}-draft-{kind}-{slug}.md`, or `-2` to `-9`, and creates it exclusively, so two callers never share one name. Then runs expiry and eviction as `admit` does. Prints `admitted {draft_id} {file name}` | 0 written, 1 config unreadable, the directory lock not obtained or the file not writable (nothing is left behind), 2 no usable directory option or `Archive/` directory, 3 refused, no free file name, expired on admission, or evicted on admission |
| `discard <id>` | Sets `status: discarded` | 0, 1 not found |
| `promote <id>` | Writes the standard draft, sets `status: promoted`, adds `promoted_to:` | 0, 1 not found or discarded, 3 already promoted |
| `expire` | Sets `status: expired` on queued drafts older than `EXPIRY_DAYS`. One of the three commands that write `status: expired`, with `admit` and `create` | 0 |
| `enable-posting --config <path>` | Sets `feedback.enabled: true` by text splice, idempotent, in the block's own indent. The result is parsed before it is written, and a result that would not parse is never written | 0, 1 config problem |
| `posting-state --config <path>` | Reads `feedback.enabled` and prints one word, writing nothing: `enabled` when it is `true`, `disabled` when the key is set to anything else (an explicit decision), `absent` when the `feedback` block or its `enabled` key is missing or empty. A caller uses the word to tell a user who never saw the key from one who turned posting off | 0, 1 config missing or the feedback key is not a block mapping |
| `feedback-dir --config <path>` | Prints the absolute feedback directory the config resolves to, writing nothing. In a linked git worktree that is the main checkout's folder. The folder need not exist, and the command never creates it. A caller that writes a draft by hand uses this path | 0, 1 config missing or unreadable |
| `disable-drafts --config <path>` | Sets `feedback.drafts: off` by the same text splice, idempotent, comments kept, in the block's own indent. A comment line never ends the block or sets its indent. The result is parsed before it is written, and a result that would not parse is never written. Prints the old and new value | 0, 1 config problem |
| `prepare-post --config C --draft D` | Makes the draft file into the exact bytes a post reads, in place: cuts it at the last scan-annotation marker that starts a line and, when `feedback.include_environment` is false, deletes each `### Environment` section outside a code fence. Both settings come from `config_loader.get_feedback_config`. Then scans those bytes for an absolute path, an email address, a git remote URL and an `@handle`, and prints `clean` or `blocked: <class> at line <n>`. Never prints the matched text. A blocked draft stays in its cut state | 0 clean, 1 missing `--config` or `--draft`, or a config or read error, 2 argparse usage error such as an unknown flag, 3 blocked |
| `mark-blocked --draft D --class C --line N --route R` | `R` is `issue` or `comment`. Writes `{D}.blocked` beside the promoted draft: `blocked: {date}`, `class:`, `line:` and `route:`, nothing else. It never holds text from the draft. A second call replaces the file, so a new block clears an earlier `dismissed:`. Needs no directory option. Refuses a model draft. The unattended post path runs it when `prepare-post` exits 3 | 0 written, 1 draft missing, `--line` below 1 or a model draft, 2 argparse usage error such as a class outside the four `prepare-post` prints |
| `blocked-list [--json] [--all]` | Read-only. Lists each draft with a `.blocked` sidecar that has no `dismissed:` line and no `.posted` sidecar, on the draft or on a comment draft made from it. `--all` adds dismissed and posted drafts. A sidecar whose draft is gone is not listed | 0 |
| `dismiss-blocked --draft D` or `dismiss-blocked --all` | Appends `dismissed: {date}` to the sidecar. It never moves, rewrites or deletes a draft. `--draft` is idempotent. `--all` dismisses every blocked draft the list shows without `--all` | 0, 1 no sidecar for `--draft`, or the directory option is missing |

`admit` and `create` hold an operating system lock on one lock file in the feedback
directory while they work, so two sessions run their duplicate-title checks one after
the other. The system frees the lock when its process ends, so a file a dead process
left behind blocks nobody. The command that releases the lock removes the file.

The directory comes from `--feedback-dir <abs>` when given, otherwise from
`--config <path>` through `config_loader.load_config()`. `--feedback-dir` must be an
absolute path to an existing directory, except for `create`, which makes it. A directory resolved from `--config` may
not exist yet, and `list` and `expire` then say so. A feedback directory's own
`Archive/` child is refused by every command except `enable-posting` and `disable-drafts`. An exit of
1 also reports a missing directory option, a missing file or an unreadable config.
Every write resolves a symlink first, so the link stays and its target changes.

Frontmatter is written back by splicing the one changed line, so every other
byte of the file, line endings included, stays as written.

## Read-only functions

A caller that only reports, such as doctor, imports these when it needs a value
without running a subprocess. `list`, `count_queued`, `is_expired`, `was_posted`, `count_blocked` and `blocked_records` all write nothing.

| Function | Returns |
|---|---|
| `is_expired(draft, now)` | True when the draft was created more than `EXPIRY_DAYS` before `now`. The commands above use this same predicate |
| `was_posted(path)` | True when `{path}.posted` exists, or when the sidecar of a comment draft made from `path` sits beside it, under the current name `{draft date}-comment-{NN}-{kind}-{slug}.md.posted` or the older `{date}-comment-{NN}-{stem}.md.posted`. `feedback_post.py` and `blocked-list` use this same predicate. Writes nothing |
| `count_queued(directory)` | The number of drafts `list` would show as `queued`. Writes nothing |
| `count_blocked(directory)` | The number of drafts `blocked-list` would show without `--all`: blocked, not dismissed, not `was_posted`. Writes nothing |
| `blocked_records(directory)` | Every record `blocked-list --all --json` prints: dismissed and posted drafts included, orphan sidecars left out. Writes nothing |
"""

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

import frontmatter_parser

# Errors a config read can raise. PyYAML is optional, so its error type joins only when present.
try:
    import yaml

    _CONFIG_ERRORS: tuple = (OSError, ValueError, KeyError, yaml.YAMLError)
except ImportError:  # pragma: no cover - PyYAML absent
    yaml = None
    _CONFIG_ERRORS = (OSError, ValueError, KeyError)

DRAFT_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-draft-(bug|lesson|idea)-[a-z0-9-]+\.md$")
FRONTMATTER_KEYS = ("draft_id", "created_at", "drafted_by", "producer", "trigger", "kind", "title", "subcommand", "source_session_id", "plugin_version", "cli_version", "model", "os", "status")
QUEUE_CAP = 10
EXPIRY_DAYS = 30
MAX_BYTES = 32768
PROVENANCE_LINE = "Drafted by Claude via planwise feedback drafting; reviewed and approved by the user before posting."

SLUG_MAX = 40
PENDING = "pending"
REQUIRED_KEYS = ("draft_id", "created_at", "kind", "title", "status")
KINDS = ("bug", "lesson", "idea")
# The plain name first, then the collision suffixes.
NAME_SUFFIXES = ("", *(f"-{n}" for n in range(2, 10)))
LOCK_NAME = ".feedback-drafts.lock"
LOCK_WAIT_SECONDS = 5.0
LOCK_RETRY_SECONDS = 0.05

# Frontmatter block located in the raw text: opening line, body, closing line.
_RAW_FM_RE = re.compile(r"\A﻿?---(\r?\n)(.*?)(\r?\n)---(?:\r?\n|\Z)", re.DOTALL)


def slugify(title: str) -> str:
    """Return the filesystem-safe slug for `title`.

    Lowercase, turn each run of characters outside `[a-z0-9]` into one hyphen,
    strip leading and trailing hyphens, cut to 40 characters, strip a trailing
    hyphen the cut exposed, and turn an empty result into `untitled`.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:SLUG_MAX].rstrip("-")
    return slug or "untitled"


@dataclass
class Draft:
    """A model draft that passed the name and `drafted_by` checks."""

    path: Path
    raw: str
    fm: dict

    @property
    def status(self) -> str:
        return self.fm.get("status", "")

    @property
    def draft_id(self) -> str:
        return self.fm.get("draft_id", "")


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="surrogateescape")


def _write(path: Path, text: str) -> None:
    """Replace `path` through a unique temp file, keeping its mode.

    The path is resolved first, so a symlink stays a symlink and its target
    receives the new content.
    """
    target = Path(path).resolve()
    handle, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(text.encode("utf-8", errors="surrogateescape"))
        if target.exists():
            shutil.copymode(target, tmp)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_fm(raw: str) -> "dict | None":
    parts = frontmatter_parser.split_frontmatter_block(raw.replace("\r\n", "\n"))
    if parts is None:
        return None
    fm = frontmatter_parser.parse_frontmatter_map(parts[0])
    if fm is None:
        return None
    return {key: _unquote(value) for key, value in fm.items()}


def _load_draft(path: Path) -> "Draft | None":
    if not DRAFT_NAME_RE.match(path.name) or not path.is_file():
        return None
    raw = _read(path)
    fm = _parse_fm(raw)
    if fm is None or fm.get("drafted_by") != "model":
        return None
    return Draft(path=path, raw=raw, fm=fm)


def _iter_drafts(directory: Path) -> "list[Draft]":
    """Model drafts directly in `directory`; subdirectories are never entered."""
    if not directory.is_dir():
        return []
    drafts = []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        draft = _load_draft(entry)
        if draft is not None:
            drafts.append(draft)
    return drafts


def _delete_model_draft(path: Path) -> bool:
    """Delete `path` only after re-reading it as a named model draft.

    The re-read uses the parsed frontmatter block alone, so a file whose
    frontmatter does not parse is never deleted.
    """
    if not DRAFT_NAME_RE.match(path.name) or not path.is_file():
        return False
    fm = _parse_fm(_read(path))
    if fm is None or fm.get("drafted_by") != "model":
        return False
    path.unlink()
    return True


def _set_fm(raw: str, key: str, value: str, after: "str | None" = None) -> str:
    """Replace the one `key:` line in the frontmatter, or insert it.

    Only that line changes. The line ending in use is kept, so a CRLF file
    stays CRLF.
    """
    match = _RAW_FM_RE.match(raw)
    if match is None:
        raise ValueError("no frontmatter block")
    eol = match.group(1)
    block = match.group(2)
    line_re = re.compile(r"(?m)^" + re.escape(key) + r":[^\r\n]*")
    new_line = f"{key}: {value}"
    if line_re.search(block):
        block = line_re.sub(lambda _m: new_line, block, count=1)
    else:
        anchor = None
        if after is not None:
            anchor = re.search(r"(?m)^" + re.escape(after) + r":[^\r\n]*", block)
        if anchor is not None:
            block = block[: anchor.end()] + eol + new_line + block[anchor.end():]
        else:
            block = block + eol + new_line
    return raw[: match.start(2)] + block + raw[match.end(2):]


def _duplicate_key(raw: str) -> str:
    """The first key written twice in the raw frontmatter block, or an empty string."""
    match = _RAW_FM_RE.match(raw)
    if match is None:
        return ""
    seen = set()
    for line in match.group(2).splitlines():
        key_match = re.match(r"([A-Za-z0-9_-]+)[ \t]*:", line)
        if key_match is None:
            continue
        if key_match.group(1) in seen:
            return key_match.group(1)
        seen.add(key_match.group(1))
    return ""


def _parse_created(value: str) -> "datetime | None":
    text = value.strip()
    if not text or text == PENDING:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _sort_key(draft: Draft) -> datetime:
    created = _parse_created(draft.fm.get("created_at", ""))
    if created is not None:
        return created
    return datetime.fromtimestamp(draft.path.stat().st_mtime, tz=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_expired(draft: Draft, now: datetime) -> bool:
    """True when `draft` was created more than `EXPIRY_DAYS` before `now`.

    This is the one expiry predicate. `expire`, `admit` and `create` apply it and write,
    `list` applies it in memory, and a read-only caller uses it to get the same
    answer without writing. A
    missing or unparseable `created_at` never expires.
    """
    created = _parse_created(draft.fm.get("created_at", ""))
    return created is not None and now - created > timedelta(days=EXPIRY_DAYS)


def count_queued(directory: Path) -> int:
    """How many model drafts `list` would show as `queued` in `directory`.

    Read-only: a queued draft past expiry counts as not queued and is left
    as it is on disk. Only `expire`, `admit` and `create` write its new status.
    """
    now = _now()
    return sum(1 for draft in _iter_drafts(directory) if draft.status == "queued" and not is_expired(draft, now))


def _normalise_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _name_kind(name: str) -> str:
    match = DRAFT_NAME_RE.match(name)
    return match.group(1) if match else ""


def _mark_expired(drafts: "list[Draft]", now: datetime) -> "list[Draft]":
    """Mark queued drafts older than `EXPIRY_DAYS` as expired in memory. Writes nothing.

    Returns the drafts it flipped, so a caller that writes can write exactly those.
    """
    flipped = []
    for draft in drafts:
        if draft.status != "queued" or not is_expired(draft, now):
            continue
        draft.raw = _set_fm(draft.raw, "status", "expired")
        draft.fm["status"] = "expired"
        flipped.append(draft)
    return flipped


def _mark_blocked(drafts: "list[Draft]", directory: Path) -> "list[Draft]":
    """Mark promoted drafts whose promoted file is blocked by the privacy check as `blocked` in memory. Writes nothing.

    A draft qualifies when its `promoted_to:` file exists in `directory`, carries a `.blocked` sidecar with no
    `dismissed:` value, and is not `was_posted`. Only the parsed frontmatter changes, so the file on disk keeps
    `status: promoted` and no later write can persist `blocked`. Returns the drafts it flipped.
    """
    active = {entry["draft"] for entry in _blocked_entries(directory) if entry["active"]}
    flipped = []
    for draft in drafts:
        target = draft.fm.get("promoted_to", "")
        if draft.status != "promoted" or not target or os.path.abspath(directory / target) not in active:
            continue
        draft.fm["status"] = "blocked"
        flipped.append(draft)
    return flipped


def _apply_expiry(drafts: "list[Draft]") -> int:
    """Flip queued drafts older than `EXPIRY_DAYS` to expired on disk. Deletes nothing."""
    flipped = _mark_expired(drafts, _now())
    for draft in flipped:
        _write(draft.path, draft.raw)
    return len(flipped)


def _evict(drafts: "list[Draft]") -> "list[Draft]":
    """Delete the oldest queued model drafts beyond `QUEUE_CAP`. Returns the drafts deleted."""
    queued = sorted((d for d in drafts if d.status == "queued"), key=_sort_key)
    deleted = []
    for draft in queued[: max(0, len(queued) - QUEUE_CAP)]:
        if _delete_model_draft(draft.path):
            deleted.append(draft)
    return deleted


def _resolve_dir(args: argparse.Namespace) -> "Path | None":
    """`--feedback-dir` wins, then `--config`. None when neither is given."""
    if args.feedback_dir:
        return Path(args.feedback_dir)
    if args.config:
        import config_loader

        config = config_loader.load_config(config_path=Path(args.config))
        return Path(config["_feedback_dir"])
    return None


def _in_archive(directory: Path) -> bool:
    """True when `directory` is a feedback directory's own `Archive/` child. The one predicate for every command.

    Listing never enters a subdirectory and admit needs the file directly in the
    directory, so only the directory's own name decides. A project stored under
    an unrelated folder named archive is not affected.
    """
    return directory.resolve().name == "Archive"


def _need_dir(args: argparse.Namespace, refuse_code: int = 1) -> "tuple[Path | None, int]":
    """The feedback directory every directory command uses, or (None, exit code) after one stderr line.

    A missing option, a `--feedback-dir` that is relative or not an existing
    directory, and an `Archive` directory exit with `refuse_code`. An unreadable
    config exits 1. A directory resolved from `--config` may not exist yet.
    """
    try:
        directory = _resolve_dir(args)
    except _CONFIG_ERRORS as exc:
        print(f"feedback_drafts: cannot resolve the feedback directory: {' '.join(str(exc).split())}", file=sys.stderr)
        return None, 1
    if directory is None:
        print("feedback_drafts: pass --feedback-dir <abs> or --config <path>", file=sys.stderr)
        return None, refuse_code
    if args.feedback_dir and not (directory.is_absolute() and directory.is_dir()):
        print(f"feedback_drafts: --feedback-dir must be an absolute path to an existing directory: {directory}", file=sys.stderr)
        return None, refuse_code
    if _in_archive(directory):
        print(f"feedback_drafts: the feedback directory is an Archive/ directory and is never touched: {directory}", file=sys.stderr)
        return None, refuse_code
    return directory, 0


def _missing_note(directory: Path) -> str:
    """A suffix that says the directory does not exist yet, or an empty string."""
    return "" if directory.is_dir() else f" (feedback directory does not exist: {directory})"


def _public(draft: Draft, directory: Path) -> dict:
    record = {key: draft.fm.get(key, "") for key in FRONTMATTER_KEYS}
    record["path"] = draft.path.relative_to(directory).as_posix()
    return record


TABLE_GROUPS = (("queued", "Queued"), ("blocked", "Blocked by the privacy check"), ("expired", "Expired"), ("discarded", "Discarded"), ("promoted", "Promoted"))
TABLE_HEADER = "| Draft | Created | Kind | Title | Producer | Session |"
TABLE_SEPARATOR = "|---|---|---|---|---|---|"


def _cell(value: str) -> str:
    """One table cell: a pipe is escaped and the cell never spans two lines."""
    return " ".join(value.split()).replace("|", "\\|")


def _session_cell(draft: Draft, session_id: "str | None") -> str:
    if not session_id:
        return "unknown"
    return "this session" if draft.fm.get("source_session_id", "") == session_id else "other session"


def _table_row(draft: Draft, directory: Path, session_id: "str | None") -> str:
    fm = draft.fm
    cells = (
        f"`{draft.path.relative_to(directory).as_posix()}`",
        _cell(fm.get("created_at", "")[:10]),
        _cell(fm.get("kind", "")),
        _cell(fm.get("title", "")),
        _cell(fm.get("producer", "")),
        _session_cell(draft, session_id),
    )
    return "| " + " | ".join(cells) + " |"


def _print_tables(shown: "list[Draft]", directory: Path, session_id: "str | None") -> None:
    """One block per non-empty group: a count line, a blank line, the table, a blank line."""
    if not shown:
        print(f"No model drafts found in {directory}." + _missing_note(directory))
        return
    for status, label in TABLE_GROUPS:
        group = sorted((d for d in shown if d.status == status), key=_sort_key, reverse=True)
        if not group:
            continue
        print(f"{label} ({len(group)})")
        print()
        print(TABLE_HEADER)
        print(TABLE_SEPARATOR)
        for draft in group:
            print(_table_row(draft, directory, session_id))
        print()


def cmd_list(args: argparse.Namespace) -> int:
    directory, code = _need_dir(args)
    if directory is None:
        return code
    drafts = _iter_drafts(directory)
    _mark_expired(drafts, _now())
    _mark_blocked(drafts, directory)
    wanted = {"queued", "blocked", "expired"}
    if args.all:
        wanted |= {"discarded", "promoted"}
    shown = [d for d in drafts if d.status in wanted]
    if args.table:
        _print_tables(shown, directory, args.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID") or None)
    elif args.json:
        print(json.dumps([_public(d, directory) for d in shown], indent=2))
    elif not shown:
        print("no drafts" + _missing_note(directory))
    else:
        for d in shown:
            print(f"{d.draft_id}\t{d.status}\t{d.fm.get('kind', '')}\t{d.fm.get('title', '')}\t{d.path.name}")
    return 0


def _sidecar_fields(path: Path) -> "dict[str, str]":
    """The `posted:`, `url:` and `route:` values of a posted-marker sidecar; a missing key reads `unknown`."""
    found = {}
    try:
        text = _read(path)
    except OSError:
        text = ""
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in ("posted", "url", "route") and value.strip():
            found.setdefault(key.strip(), value.strip())
    return {key: found.get(key, "unknown") for key in ("posted", "url", "route")}


def cmd_sweep_list(args: argparse.Namespace) -> int:
    """Print the sweep candidates and orphan sidecars. Read-only: nothing is moved, written or deleted."""
    directory, code = _need_dir(args)
    if directory is None:
        return code
    names = sorted(entry.name for entry in directory.iterdir()) if directory.is_dir() else []
    candidates = []
    for name in names:
        path = directory / name
        if name.endswith(".md") and path.is_file() and (directory / (name + ".posted")).is_file() and _load_draft(path) is None:
            candidates.append(path)
    for path in candidates:
        fields = _sidecar_fields(directory / (path.name + ".posted"))
        print(os.path.abspath(path))
        print(f"  posted: {fields['posted']}")
        print(f"  url: {fields['url']}")
        print(f"  route: {fields['route']}")
        blocked = directory / (path.name + BLOCKED_SUFFIX)
        if blocked.is_file():
            print(f"  blocked sidecar: {os.path.abspath(blocked)}")
    for name in names:
        sidecar = directory / name
        if name.endswith((".md.posted", ".md" + BLOCKED_SUFFIX)) and sidecar.is_file() and not (directory / name.rsplit(".", 1)[0]).exists():
            print(f"orphan sidecar (left in place): {os.path.abspath(sidecar)}")
    if candidates:
        print(f"{len(candidates)} draft(s) already posted are eligible to archive.")
    else:
        print("No posted drafts to archive.")
    return 0


class _LockTimeout(Exception):
    """The directory lock stayed held for the whole wait."""


def _try_lock(handle: int) -> bool:
    """Take the system's lock on an open file without waiting. False when another handle holds it."""
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _is_file_at(handle: int, path: Path) -> bool:
    """True while `path` still names the open file. A holder may have removed it before releasing."""
    try:
        return os.path.samestat(os.fstat(handle), os.stat(path))
    except OSError:
        return False


@contextlib.contextmanager
def _dir_lock(directory: Path) -> "Iterator[None]":
    """Hold the lock of `directory`, so `admit` and `create` never run at once there.

    The system frees the lock when its process ends, so no lock is ever stale.
    """
    lock = directory / LOCK_NAME
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            handle = os.open(lock, os.O_CREAT | os.O_RDWR)
        except PermissionError:
            # Windows can refuse for the moment in which another process removes the file.
            if os.name != "nt" or time.monotonic() >= deadline:
                raise
        else:
            if _try_lock(handle) and _is_file_at(handle, lock):
                break
            os.close(handle)
            if time.monotonic() >= deadline:
                raise _LockTimeout(str(lock))
        time.sleep(LOCK_RETRY_SECONDS)
    try:
        yield
    finally:
        # Windows refuses to remove an open file, so close first there. Elsewhere remove first,
        # while the lock still keeps every other process out of this file.
        if os.name == "nt":
            os.close(handle)
        with contextlib.suppress(OSError):
            lock.unlink()
        if os.name != "nt":
            os.close(handle)


def _claim(directory: Path, stem: str, data: bytes) -> "Path | None":
    """Create `{stem}.md`, or `-2` to `-9`, exclusively and write `data`. None when every name is taken.

    A failed write removes the file, so a caller that gets an error left nothing behind.
    """
    for suffix in NAME_SUFFIXES:
        candidate = directory / f"{stem}{suffix}.md"
        created = False
        try:
            with open(candidate, "xb") as handle:
                created = True
                handle.write(data)
        except FileExistsError:
            continue
        except BaseException:
            # Remove only a file this call made.
            if created:
                candidate.unlink(missing_ok=True)
            raise
        return candidate
    return None


def _refused(reason: str) -> int:
    print(f"feedback draft refused: {reason}", file=sys.stderr)
    return 3


def _refusal(draft_path: Path, reason: str) -> int:
    _delete_model_draft(draft_path)
    return _refused(reason)


def _lock_failed(exc: _LockTimeout) -> int:
    print(f"feedback_drafts: another command holds the lock, nothing written: {exc}", file=sys.stderr)
    return 1


def _frontmatter_problem(raw: str, fm: "dict | None", size: int, name_kind: "str | None") -> "str | None":
    """Why a new draft is refused, or None. `name_kind` is the kind in an existing file name."""
    if size > MAX_BYTES:
        return f"oversize ({size} bytes, limit {MAX_BYTES})"
    if fm is None:
        return "malformed frontmatter"
    duplicated = _duplicate_key(raw)
    if duplicated:
        return f"malformed frontmatter (duplicate key {duplicated})"
    missing = [key for key in REQUIRED_KEYS if not fm.get(key)]
    if missing:
        return f"malformed frontmatter (missing {missing[0]})"
    if name_kind is None:
        if fm["kind"] not in KINDS:
            return "malformed frontmatter (kind must be bug, lesson or idea)"
    elif fm["kind"] != name_kind:
        return "malformed frontmatter (kind does not match the file name)"
    if fm.get("drafted_by") != "model":
        return "malformed frontmatter (drafted_by is not model)"
    if fm["status"].strip() not in (PENDING, "queued"):
        return f"malformed frontmatter (status must be pending or queued, not {fm['status']})"
    if fm["created_at"] != PENDING and _parse_created(fm["created_at"]) is None:
        return "malformed frontmatter (created_at is not a timestamp)"
    return None


def _title_is_queued(drafts: "list[Draft]", title: str) -> bool:
    wanted = _normalise_title(title)
    now = _now()
    return any(d.status == "queued" and not is_expired(d, now) and _normalise_title(d.fm.get("title", "")) == wanted for d in drafts)


def _settle(raw: str, fm: dict, others: "list[Draft]") -> str:
    """Fill the pending values of a new draft and replace a colliding id or a future time. Updates `fm` too."""
    if fm.get("draft_id") == PENDING:
        fm["draft_id"] = str(uuid.uuid4())
        raw = _set_fm(raw, "draft_id", fm["draft_id"])
    elif any(other.draft_id == fm["draft_id"] for other in others):
        old_id = fm["draft_id"]
        fm["draft_id"] = str(uuid.uuid4())
        raw = _set_fm(raw, "draft_id", fm["draft_id"])
        print(f"feedback_drafts: draft_id {old_id} already belongs to another draft, replaced with {fm['draft_id']}", file=sys.stderr)
    if fm["created_at"] == PENDING:
        fm["created_at"] = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
        raw = _set_fm(raw, "created_at", fm["created_at"])
    else:
        supplied = _parse_created(fm["created_at"])
        now = _now()
        if supplied is not None and supplied > now:
            old_value = fm["created_at"]
            fm["created_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            raw = _set_fm(raw, "created_at", fm["created_at"])
            print(f"feedback_drafts: created_at {old_value} is in the future, replaced with {fm['created_at']}", file=sys.stderr)
    if fm["status"].strip() == PENDING:
        raw = _set_fm(raw, "status", "queued")
    return raw


def _upkeep(directory: Path, path: Path) -> "str | None":
    """Run expiry and eviction after `path` joined the queue. Returns why `path` did not stay queued, or None."""
    here = path.resolve()
    drafts = _iter_drafts(directory)
    _apply_expiry(drafts)
    for evicted in _evict(drafts):
        if evicted.path.resolve() != here:
            print(f"feedback_drafts: evicted {evicted.draft_id} ({evicted.path.name}): more than {QUEUE_CAP} queued drafts", file=sys.stderr)
    if not path.exists():
        return "evicted on admission: older than the queued drafts"
    if any(d.path.resolve() == here and d.status == "expired" for d in drafts):
        return "expired on admission: created more than the expiry limit ago"
    return None


def cmd_admit(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not DRAFT_NAME_RE.match(path.name):
        print(f"feedback draft refused: name does not match the draft pattern: {path.name}", file=sys.stderr)
        return 2
    if not path.is_file():
        print(f"feedback_drafts: no such file: {path}", file=sys.stderr)
        return 1
    directory, code = _need_dir(args, refuse_code=2)
    if directory is None:
        return code
    if path.resolve().parent != directory.resolve():
        print(f"feedback draft refused: file is not directly in the feedback directory: {path}", file=sys.stderr)
        return 2
    try:
        with _dir_lock(directory):
            return _admit_locked(path, directory)
    except _LockTimeout as exc:
        return _lock_failed(exc)
    except OSError as exc:
        print(f"feedback_drafts: could not admit the draft: {exc}", file=sys.stderr)
        return 1


def _admit_locked(path: Path, directory: Path) -> int:
    # Another command may have evicted the file while this one waited for the lock.
    if not path.is_file():
        print(f"feedback_drafts: no such file: {path}", file=sys.stderr)
        return 1
    here = path.resolve()
    raw = _read(path)
    fm = _parse_fm(raw)
    # A draft already in a later lifecycle state is a tracked record, not a
    # malformed submission: it is never refused, so it is never deleted here.
    lifecycle = fm.get("status", "").strip() if fm is not None else ""
    if lifecycle in ("expired", "discarded", "promoted"):
        print(f"feedback draft refused: not admissible in status {lifecycle}: {path.name}", file=sys.stderr)
        return 2
    problem = _frontmatter_problem(raw, fm, path.stat().st_size, _name_kind(path.name))
    if problem is not None:
        return _refusal(path, problem)

    others = [d for d in _iter_drafts(directory) if d.path.resolve() != here]
    if _title_is_queued(others, fm["title"]):
        return _refusal(path, "duplicate title among queued drafts")
    _write(path, _settle(raw, fm, others))

    reason = _upkeep(directory, path)
    if reason is not None:
        return _refused(reason)
    print(f"admitted {fm['draft_id']}")
    return 0


def _make_create_dir(args: argparse.Namespace) -> None:
    """Make the missing feedback directory a project's first draft needs. A failure is left for the caller to report."""
    try:
        directory = _resolve_dir(args)
    except _CONFIG_ERRORS:
        return
    if directory is not None and directory.is_absolute() and not _in_archive(directory):
        with contextlib.suppress(OSError):
            directory.mkdir(parents=True, exist_ok=True)


def cmd_create(args: argparse.Namespace) -> int:
    # Read bytes: text-mode stdin is cp1252 on Windows.
    data = sys.stdin.buffer.read()
    _make_create_dir(args)
    directory, code = _need_dir(args, refuse_code=2)
    if directory is None:
        return code
    try:
        raw = data.decode("utf-8")
    except UnicodeDecodeError:
        return _refused("the input is not UTF-8")
    fm = _parse_fm(raw)
    problem = _frontmatter_problem(raw, fm, len(data), None)
    if problem is not None:
        return _refused(problem)
    try:
        with _dir_lock(directory):
            return _create_locked(directory, raw, fm)
    except _LockTimeout as exc:
        return _lock_failed(exc)
    except OSError as exc:
        print(f"feedback_drafts: could not write the draft: {exc}", file=sys.stderr)
        return 1


def _create_locked(directory: Path, raw: str, fm: dict) -> int:
    others = _iter_drafts(directory)
    if _title_is_queued(others, fm["title"]):
        return _refused("duplicate title among queued drafts")
    raw = _settle(raw, fm, others)
    # isoformat pads the year to four digits on every platform; strftime does not.
    day = _parse_created(fm["created_at"]).date().isoformat()
    stem = f"{day}-draft-{fm['kind']}-{slugify(fm['title'])}"
    path = _claim(directory, stem, raw.encode("utf-8"))
    if path is None:
        return _refused(f"no free file name for {stem}")
    # The draft is on disk now, so a failed upkeep step must not report that nothing was written.
    try:
        reason = _upkeep(directory, path)
    except OSError as exc:
        print(f"feedback_drafts: the draft was written, but queue upkeep failed: {exc}", file=sys.stderr)
        reason = None
    if reason is not None:
        return _refused(reason)
    # The name only: a piped stdout on Windows is not UTF-8, and a path may hold any character.
    print(f"admitted {fm['draft_id']} {path.name}")
    return 0


def _find(directory: Path, draft_id: str) -> "Draft | None":
    for draft in _iter_drafts(directory):
        if draft.draft_id == draft_id:
            return draft
    return None


def cmd_discard(args: argparse.Namespace) -> int:
    directory, code = _need_dir(args)
    if directory is None:
        return code
    draft = _find(directory, args.id)
    if draft is None:
        print(f"feedback_drafts: no draft with id {args.id}", file=sys.stderr)
        return 1
    _write(draft.path, _set_fm(draft.raw, "status", "discarded"))
    print(f"discarded {draft.draft_id}")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    directory, code = _need_dir(args)
    if directory is None:
        return code
    draft = _find(directory, args.id)
    if draft is None:
        print(f"feedback_drafts: no draft with id {args.id}", file=sys.stderr)
        return 1
    if draft.status == "promoted":
        print(f"feedback_drafts: draft {args.id} is already promoted", file=sys.stderr)
        return 3
    if draft.status == "discarded":
        print(f"feedback_drafts: draft {args.id} was discarded and cannot be promoted", file=sys.stderr)
        return 1

    parts = frontmatter_parser.split_frontmatter_block(draft.raw.replace("\r\n", "\n"))
    assert parts is not None
    body = parts[1].strip("\n") + "\n\n" + PROVENANCE_LINE + "\n"
    kind = _name_kind(draft.path.name)
    stem = f"{_now().strftime('%Y-%m-%d')}-{kind}-{slugify(draft.fm.get('title', ''))}"
    target = _claim(directory, stem, body.encode("utf-8", errors="surrogateescape"))
    if target is None:
        print(f"feedback_drafts: no free file name for {stem}", file=sys.stderr)
        return 3

    raw = _set_fm(draft.raw, "status", "promoted")
    raw = _set_fm(raw, "promoted_to", target.name, after="status")
    _write(draft.path, raw)
    print(str(target))
    return 0


def cmd_expire(args: argparse.Namespace) -> int:
    directory, code = _need_dir(args)
    if directory is None:
        return code
    print(f"expired {_apply_expiry(_iter_drafts(directory))}" + _missing_note(directory))
    return 0


def _set_feedback_scalar(text: str, key: str, value: str, is_set: "Callable[[str], bool]") -> "tuple[str, str]":
    """Return (new_text, old_value). Only the one `feedback.<key>:` line changes.

    `is_set` takes the old raw value and says whether it already means `value`,
    which makes the splice idempotent. A comment line, at any indent, neither
    ends the block nor sets its indent.
    """
    lines = re.findall(r"[^\n]*\n|[^\n]+", text)
    header = None
    for index, line in enumerate(lines):
        if line.startswith("feedback:"):
            if not re.match(r"^feedback:[ \t]*(#[^\r\n]*)?\r?\n?$", line):
                raise ValueError("the feedback key is not a block mapping")
            header = index
            break
    if header is None:
        eol = "\r\n" if "\r\n" in text else "\n"
        gap = "" if (not text or text.endswith("\n")) else eol
        return text + gap + f"feedback:{eol}  {key}: {value}{eol}", "unset"

    end = len(lines)
    for index in range(header + 1, len(lines)):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            continue
        end = index
        break

    for index in range(header + 1, end):
        match = re.match(r"^([ \t]+)" + re.escape(key) + r":([ \t]*)([^\s#]*)([^\r\n]*)(\r?\n?)$", lines[index])
        if match is None:
            continue
        old = match.group(3)
        if is_set(old):
            return text, old
        gap = match.group(2) or " "
        lines[index] = f"{match.group(1)}{key}:{gap}{value}{match.group(4)}{match.group(5)}"
        return "".join(lines), old or "unset"

    eol = "\r\n" if lines[header].endswith("\r\n") else "\n"
    if not lines[header].endswith("\n"):
        lines[header] += eol
    # Match the block's own indent, so a four-space block stays valid YAML.
    indent = "  "
    for index in range(header + 1, end):
        child = re.match(r"^([ \t]+)[^\s#]", lines[index])
        if child is not None:
            indent = child.group(1)
            break
    lines.insert(header + 1, f"{indent}{key}: {value}{eol}")
    return "".join(lines), "unset"


def _enable_posting_text(text: str) -> "tuple[str, str]":
    """Return (new_text, old_value) for `feedback.enabled: true`."""
    return _set_feedback_scalar(text, "enabled", "true", lambda old: _unquote(old).lower() == "true")


def _disable_drafts_text(text: str) -> "tuple[str, str]":
    """Return (new_text, old_value) for `feedback.drafts: off`."""
    return _set_feedback_scalar(text, "drafts", "off", lambda old: _unquote(old).lower() == "off")


def _posting_enabled(text: str) -> "bool | None":
    """True when `text` parses and sets `feedback.enabled: true`, False when it does not, None without PyYAML."""
    if yaml is None:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    feedback = data.get("feedback") if isinstance(data, dict) else None
    enabled = feedback.get("enabled") if isinstance(feedback, dict) else None
    # The loader also reads a quoted "true" as on, and the splice leaves that value as written.
    return enabled is True or (isinstance(enabled, str) and enabled.strip().lower() == "true")


def _drafts_off(text: str) -> "bool | None":
    """True when `text` parses and sets `feedback.drafts` to off, False when it does not, None without PyYAML."""
    if yaml is None:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    feedback = data.get("feedback") if isinstance(data, dict) else None
    drafts = feedback.get("drafts") if isinstance(feedback, dict) else None
    # An unquoted `off` loads as the boolean False, and the loader also reads a quoted "off" as off.
    return drafts is False or (isinstance(drafts, str) and drafts.strip().lower() == "off")


def _posting_state_text(text: str) -> str:
    """Return `enabled`, `disabled` or `absent` for `feedback.enabled`, reading through the enable splice.

    The splice changes nothing when the key already means true, which is the `enabled` state. Its old value is
    `unset` for a missing block, a missing key or an empty value, which is the `absent` state. Any other old value
    was set on purpose, so it is `disabled`. A key written as the literal word `unset` reads as `absent`.
    """
    new_text, old = _enable_posting_text(text)
    if new_text == text:
        return "enabled"
    return "absent" if old == "unset" else "disabled"


def read_posting_state(config_path: Path) -> str:
    """Return `enabled`, `disabled` or `absent` for the config file at `config_path`, writing nothing.

    The one read behind the `posting-state` command, so a caller that reports the state (doctor) and the
    engine's gate 1 share one predicate. Raises ValueError when the `feedback` key is not a block mapping
    and OSError when the file cannot be read.
    """
    return _posting_state_text(_read(Path(config_path)))


def cmd_posting_state(args: argparse.Namespace) -> int:
    config = Path(args.config)
    if not config.is_file():
        print(f"feedback_drafts: config.yaml not found at {config}", file=sys.stderr)
        return 1
    try:
        state = read_posting_state(config)
    except ValueError as exc:
        print(f"feedback_drafts: {exc}", file=sys.stderr)
        return 1
    print(state)
    return 0


def cmd_feedback_dir(args: argparse.Namespace) -> int:
    try:
        import config_loader

        config = config_loader.load_config(config_path=Path(args.config))
        directory = Path(config["_feedback_dir"])
    except _CONFIG_ERRORS as exc:
        print(f"feedback_drafts: cannot resolve the feedback directory: {' '.join(str(exc).split())}", file=sys.stderr)
        return 1
    # A caller writes a file at this path, and a piped stream on Windows defaults to the ANSI code page.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    print(directory)
    return 0


def cmd_disable_drafts(args: argparse.Namespace) -> int:
    config = Path(args.config)
    if not config.is_file():
        print(f"feedback_drafts: config.yaml not found at {config}", file=sys.stderr)
        return 1
    text = _read(config)
    try:
        new_text, old = _disable_drafts_text(text)
    except ValueError as exc:
        print(f"feedback_drafts: {exc}", file=sys.stderr)
        return 1
    # Check the result before writing: a splice that would leave the config
    # unparsable, or not off, is never written.
    if _drafts_off(new_text) is False:
        print("feedback_drafts: the edit would not leave a valid config with feedback.drafts: off; config.yaml left unchanged", file=sys.stderr)
        return 1
    if new_text != text:
        _write(config, new_text)
    print(f"feedback.drafts: {old} -> off")
    return 0


def cmd_enable_posting(args: argparse.Namespace) -> int:
    config = Path(args.config)
    if not config.is_file():
        print(f"feedback_drafts: config.yaml not found at {config}", file=sys.stderr)
        return 1
    text = _read(config)
    try:
        new_text, old = _enable_posting_text(text)
    except ValueError as exc:
        print(f"feedback_drafts: {exc}", file=sys.stderr)
        return 1
    # Check the result before writing: a splice that would leave the config
    # unparsable, or not enabled, is never written.
    if _posting_enabled(new_text) is False:
        print("feedback_drafts: the edit would not leave a valid config with feedback.enabled: true; config.yaml left unchanged", file=sys.stderr)
        return 1
    if new_text != text:
        _write(config, new_text)
    print(f"feedback.enabled: {old} -> true")
    return 0


# ---------------------------------------------------------------- prepare-post

SCAN_ANNOTATION_MARKER = "<!-- planwise:scan-annotation"
PLUGIN_INSTALL_ID = "planwise@planwise-marketplace"
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_ENVIRONMENT_HEADING_RE = re.compile(r"^ {0,3}###[ \t]+Environment[ \t]*$")
_ANY_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]|$)")

ABSOLUTE_PATH_RE = re.compile(
    r"(?<!\w)[A-Za-z]:[\\/]"
    r"|\\\\[^\s\\/]+[\\/]"
    r"|(?<![\w\\])\\[^\s\\/\"'`<>|]{2,}\\[^\s\\/\"'`<>|]+"
    r"|(?<!\w)~[\\/]"
    r"|\bfile:/"
    r"|(?<![\w/}*])/[^\s/\\<>()\[\]\"'`|]+/"
)
"""absolute-path: a drive, UNC, rooted-backslash, `~/` or `file:` path, or `/a/b` not after a word character, `/`, `}` or `*`, searched with URLs blanked."""

EMAIL_RE = re.compile(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
"""email: `local@domain.tld`."""

GIT_REMOTE_RE = re.compile(r"\bgit@[\w.-]+:|\b(?:ssh|git)://", re.IGNORECASE)
"""git-remote: `git@host:`, `ssh://` or `git://`; `_url_hit` adds the forge and self-hosted http(s) URL rules."""

HANDLE_RE = re.compile(r"(?:(?<!\w)@[A-Za-z0-9_]|(?<=\w)@[A-Za-z_])[\w-]*")
"""handle: an `@name`, searched with emails and the install id blanked; `name@1.2` (a version pin) is exempt."""

# Any scheme URL except `file:`, which the absolute-path detector must still see.
_URL_RE = re.compile(r"\b(?!file:)[A-Za-z][A-Za-z0-9+.-]*://\S*", re.IGNORECASE)
_HTTP_URL_RE = re.compile(r"\bhttps?://(?P<host>[^\s/?#<>()\"'`]+)(?P<path>[^\s<>()\"'`]*)", re.IGNORECASE)
_FORGE_HOST = r"(?:[\w-]+\.)*(?:github\.com|gitlab\.com|bitbucket\.org|githubusercontent\.com)"
_FORGE_HOST_RE = re.compile(_FORGE_HOST + r"$", re.IGNORECASE)
_BARE_FORGE_RE = re.compile(r"(?<![\w.@/-])(?P<host>" + _FORGE_HOST + r")(?P<path>/[^\s<>()\"'`]*)", re.IGNORECASE)
_REPO_HOSTS = ("github.com", "www.github.com")
_PUBLIC_HOSTS = ("docs.anthropic.com", "docs.github.com", "claude.com")
_OWNER_REPO_PATH_RE = re.compile(r"^/[\w.-]+/[\w.-]+")


def _blank(pattern: "re.Pattern[str]", line: str) -> str:
    return pattern.sub(lambda m: " " * len(m.group(0)), line)


def _url_blocks(host: str, path: str, repo: str) -> bool:
    """Whether one http(s) or scheme-less forge URL is a git remote that is not public."""
    host = host.lower()
    if "@" in host:
        return True
    host = host.split(":", 1)[0]
    path = path.rstrip(".,;:!")
    if host in _PUBLIC_HOSTS or host.endswith(".claude.com"):
        return False
    if _FORGE_HOST_RE.match(host):
        own = re.match(r"^/" + re.escape(repo) + r"(?:\.git)?(?:[/#?]|$)", path, re.IGNORECASE)
        return not (host in _REPO_HOSTS and own)
    bare = re.split(r"[?#]", path, maxsplit=1)[0]
    return bool(_OWNER_REPO_PATH_RE.match(bare)) or bare.lower().endswith(".git")


def _url_hit(line: str, repo: str) -> bool:
    for match in _HTTP_URL_RE.finditer(line):
        if _url_blocks(match.group("host"), match.group("path"), repo):
            return True
    for match in _BARE_FORGE_RE.finditer(_blank(_HTTP_URL_RE, line)):
        if _url_blocks(match.group("host"), match.group("path"), repo):
            return True
    return False


def _line_class(line: str, repo: str) -> "str | None":
    """The first class that `line` holds, in the fixed order git-remote, absolute-path, email, handle.

    git-remote runs first so `git@host:` is not reported as an email. The absolute-path search sees
    the line with every URL blanked out. email runs before handle, and the handle search sees the
    line with each email address and the plugin install id blanked out.
    """
    if GIT_REMOTE_RE.search(line) or _url_hit(line, repo):
        return "git-remote"
    if ABSOLUTE_PATH_RE.search(_blank(_URL_RE, line)):
        return "absolute-path"
    if EMAIL_RE.search(line):
        return "email"
    if HANDLE_RE.search(_blank(EMAIL_RE, line.replace(PLUGIN_INSTALL_ID, " " * len(PLUGIN_INSTALL_ID)))):
        return "handle"
    return None


def scan_post_bytes(data: bytes, repo: str) -> "tuple[str, int] | None":
    """Return `(class, line number)` for the first privacy hit in `data`, or None when it is clean."""
    text = data.decode("utf-8", errors="surrogateescape")
    for number, line in enumerate(text.split("\n"), start=1):
        found = _line_class(line.rstrip("\r"), repo)
        if found is not None:
            return found, number
    return None


def _drop_environment(text: str) -> str:
    """Delete each `### Environment` heading and its lines, up to the next heading or the end.

    A line inside a ``` or ~~~ fence is never a heading, so it neither starts nor ends a section.
    """
    kept = []
    skipping = False
    fence = None
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        opener = _FENCE_RE.match(bare)
        if fence is None and opener is None:
            if _ENVIRONMENT_HEADING_RE.match(bare):
                skipping = True
                continue
            if skipping and _ANY_HEADING_RE.match(bare):
                skipping = False
        elif opener is not None:
            if fence is None:
                fence = opener.group(1)[0]
            elif opener.group(1)[0] == fence:
                fence = None
        if not skipping:
            kept.append(line)
    return "".join(kept)


def _annotation_cut(text: str) -> int:
    """The offset of the last scan-annotation marker that starts a line, or -1 when there is none."""
    found = text.rfind("\n" + SCAN_ANNOTATION_MARKER)
    if found != -1:
        return found + 1
    return 0 if text.startswith(SCAN_ANNOTATION_MARKER) else -1


def prepare_post(draft: Path, *, include_environment: bool, repo: str) -> "tuple[str, str, int, bytes]":
    """Make `draft` into the bytes a post reads, then scan exactly those bytes.

    Cuts the file in place at the last scan-annotation marker that starts a line, so a body that
    quotes the marker mid-report keeps the quote. It also deletes each `### Environment`
    section when `include_environment` is false, so the shown, on-disk and posted bytes stay
    identical. A blocked draft keeps that cut state. Returns `("clean", "", 0, data)` or
    `("blocked", class, line, data)`, where `data` is the file as read back after the write.
    Raises OSError when the file cannot be read or written.
    """
    draft = Path(draft)
    text = _read(draft)
    new_text = text
    cut = _annotation_cut(new_text)
    if cut != -1:
        new_text = new_text[:cut]
    if not include_environment:
        new_text = _drop_environment(new_text)
    if new_text != text:
        _write(draft, new_text)
    data = draft.read_bytes()
    hit = scan_post_bytes(data, repo)
    if hit is None:
        return "clean", "", 0, data
    return "blocked", hit[0], hit[1], data


def read_post_settings(config_path: Path) -> "tuple[bool, str]":
    """Return `(include_environment, repo)` for the config file, writing nothing.

    Both values come from `config_loader.get_feedback_config`, so the defaults and the repo shape
    check are the loader's own. Raises what `config_loader.load_config` raises on a bad file.
    """
    import config_loader

    feedback = config_loader.get_feedback_config(config_loader.load_config(config_path=Path(config_path)))
    return feedback["include_environment"], feedback["repo"]


def cmd_prepare_post(args: argparse.Namespace) -> int:
    if not args.config or not args.draft:
        print("feedback_drafts: prepare-post needs --config and --draft", file=sys.stderr)
        return 1
    config = Path(args.config)
    draft = Path(args.draft)
    if not config.is_file():
        print(f"feedback_drafts: config.yaml not found at {config}", file=sys.stderr)
        return 1
    if not draft.is_file():
        print(f"feedback_drafts: draft not found at {draft}", file=sys.stderr)
        return 1
    try:
        include_environment, repo = read_post_settings(config)
        verdict, found, line, _data = prepare_post(draft, include_environment=include_environment, repo=repo)
    except _CONFIG_ERRORS as exc:
        print(f"feedback_drafts: {exc}", file=sys.stderr)
        return 1
    if verdict == "clean":
        print("clean")
        return 0
    print(f"blocked: {found} at line {line}")
    return 3


# ---------------------------------------------------------------- blocked sidecar

BLOCKED_SUFFIX = ".blocked"
BLOCKED_CLASSES = ("git-remote", "absolute-path", "email", "handle")
BLOCKED_ROUTES = ("issue", "comment")
_BLOCKED_KEYS = ("blocked", "class", "line", "route", "dismissed")


def _blocked_fields(sidecar: Path) -> "dict[str, str]":
    """The `blocked:`, `class:`, `line:`, `route:` and `dismissed:` values a `.blocked` sidecar holds.

    A key the file lacks is absent from the result. No other line is read, so text a hand
    edit added is never returned.
    """
    try:
        text = _read(sidecar)
    except OSError:
        return {}
    found: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in _BLOCKED_KEYS and value.strip():
            found.setdefault(key.strip(), value.strip())
    return found


def was_posted(path: Path) -> bool:
    """Whether a `.posted` sidecar records a post of this promoted file, or of a comment draft made from it.

    A comment-route post writes a sidecar on the comment draft as well as on `path`. The comment draft
    is `{draft date}-comment-{NN}-{kind}-{slug}.md`. An older post named it
    `{date}-comment-{NN}-{stem}.md` and marked only that file, so both names count. Read-only.
    """
    if path.with_name(path.name + ".posted").exists():
        return True
    stem = path.stem
    forms = [r"\d{4}-\d{2}-\d{2}-comment-\d+-" + re.escape(stem)]
    if re.match(r"\d{4}-\d{2}-\d{2}-.", stem):
        forms.append(re.escape(stem[:10]) + r"-comment-\d+-" + re.escape(stem[11:]))
    pattern = re.compile("(?:" + "|".join(forms) + r")\.md\.posted")
    return any(pattern.fullmatch(entry.name) for entry in path.parent.iterdir())


def _blocked_entries(directory: Path) -> "list[dict]":
    """One record per `*.md.blocked` sidecar directly in `directory` whose draft file still exists.

    A sidecar with no draft beside it is an orphan and is left out. `active` is true when the
    sidecar has no `dismissed:` value and the draft is not `was_posted`. Read-only.
    """
    if not directory.is_dir():
        return []
    entries = []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        name = entry.name
        if not name.endswith(".md" + BLOCKED_SUFFIX) or not entry.is_file():
            continue
        draft = directory / name[: -len(BLOCKED_SUFFIX)]
        if not draft.is_file():
            continue
        fields = _blocked_fields(entry)
        posted = was_posted(draft)
        dismissed = "dismissed" in fields
        entries.append(
            {
                "draft": os.path.abspath(draft),
                "sidecar": entry,
                "fields": fields,
                "dismissed": dismissed,
                "posted": posted,
                "active": not dismissed and not posted,
            }
        )
    return entries


def count_blocked(directory: Path) -> int:
    """How many drafts `blocked-list` would show without `--all`: blocked, not dismissed, not posted.

    Read-only, like `count_queued`. A sidecar whose draft is gone does not count.
    """
    return sum(1 for entry in _blocked_entries(directory) if entry["active"])


def cmd_mark_blocked(args: argparse.Namespace) -> int:
    draft = Path(args.draft)
    if not draft.is_file():
        print(f"feedback_drafts: draft not found at {draft}", file=sys.stderr)
        return 1
    if args.line < 1:
        print("feedback_drafts: --line must be 1 or more", file=sys.stderr)
        return 1
    if _load_draft(draft) is not None:
        print("feedback_drafts: mark-blocked takes the promoted draft a post reads, never a model draft", file=sys.stderr)
        return 1
    sidecar = draft.with_name(draft.name + BLOCKED_SUFFIX)
    # Date, class, line and route only: the sidecar never holds text from the draft.
    _write(sidecar, f"blocked: {_now().strftime('%Y-%m-%d')}\nclass: {args.block_class}\nline: {args.line}\nroute: {args.route}\n")
    print(f"marked blocked: {os.path.abspath(sidecar)}")
    return 0


def _blocked_record(entry: dict) -> dict:
    record = {"draft": entry["draft"]}
    for key in _BLOCKED_KEYS:
        record[key] = entry["fields"].get(key, "")
    record["posted"] = entry["posted"]
    return record


def blocked_records(directory: Path) -> "list[dict]":
    """Every record `blocked-list --all --json` prints, in the same order.

    Dismissed and posted drafts are included. A sidecar whose draft is gone is left out.
    Read-only, like `count_blocked`. An absent directory gives an empty list.
    """
    return [_blocked_record(entry) for entry in _blocked_entries(directory)]


def cmd_blocked_list(args: argparse.Namespace) -> int:
    directory, code = _need_dir(args)
    if directory is None:
        return code
    shown = [entry for entry in _blocked_entries(directory) if args.all or entry["active"]]
    if args.json:
        print(json.dumps([_blocked_record(entry) for entry in shown], indent=2))
    elif not shown:
        print("no blocked drafts" + _missing_note(directory))
    else:
        for entry in shown:
            fields = entry["fields"]
            state = "posted" if entry["posted"] else ("dismissed" if entry["dismissed"] else "blocked")
            print(f"{entry['draft']}\t{state}\t{fields.get('class', 'unknown')}\tline {fields.get('line', 'unknown')}\t{fields.get('route', 'unknown')}\t{fields.get('blocked', 'unknown')}")
    return 0


def _dismiss(sidecar: Path) -> bool:
    """Append `dismissed: {date}` to `sidecar`. False when it already holds one. Never touches the draft."""
    if "dismissed" in _blocked_fields(sidecar):
        return False
    text = _read(sidecar)
    if text and not text.endswith("\n"):
        text += "\n"
    _write(sidecar, text + f"dismissed: {_now().strftime('%Y-%m-%d')}\n")
    return True


def cmd_dismiss_blocked(args: argparse.Namespace) -> int:
    if args.draft:
        sidecar = Path(args.draft).with_name(Path(args.draft).name + BLOCKED_SUFFIX)
        if not sidecar.is_file():
            print(f"feedback_drafts: no blocked record for {args.draft}", file=sys.stderr)
            return 1
        print(f"dismissed {os.path.abspath(args.draft)}" if _dismiss(sidecar) else f"already dismissed {os.path.abspath(args.draft)}")
        return 0
    directory, code = _need_dir(args)
    if directory is None:
        return code
    dismissed = sum(1 for entry in _blocked_entries(directory) if entry["active"] and _dismiss(entry["sidecar"]))
    print(f"dismissed {dismissed} blocked draft(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="feedback_drafts", description="Manage model-drafted feedback files.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_dir_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--feedback-dir", help="absolute feedback directory; wins over --config")
        p.add_argument("--config", help="path to config.yaml")

    p_list = sub.add_parser("list", help="list queued and expired drafts")
    add_dir_options(p_list)
    p_list.add_argument("--json", action="store_true", help="print a JSON array")
    p_list.add_argument("--all", action="store_true", help="include discarded and promoted drafts")
    p_list.add_argument("--table", action="store_true", help="print the Queued and Expired tables; not with --json")
    p_list.add_argument("--session-id", help="the running session id; marks the Session column of --table. Defaults to the CLAUDE_CODE_SESSION_ID environment variable")
    p_list.set_defaults(func=cmd_list)

    p_sweep = sub.add_parser("sweep-list", help="list posted drafts a sweep would archive; read-only")
    add_dir_options(p_sweep)
    p_sweep.set_defaults(func=cmd_sweep_list)

    p_admit = sub.add_parser("admit", help="admit a freshly written draft")
    p_admit.add_argument("path")
    add_dir_options(p_admit)
    p_admit.set_defaults(func=cmd_admit)

    p_create = sub.add_parser("create", help="validate, name and write a draft read from stdin")
    add_dir_options(p_create)
    p_create.set_defaults(func=cmd_create)

    p_discard = sub.add_parser("discard", help="mark a draft discarded")
    p_discard.add_argument("id")
    add_dir_options(p_discard)
    p_discard.set_defaults(func=cmd_discard)

    p_promote = sub.add_parser("promote", help="write the standard draft for a model draft")
    p_promote.add_argument("id")
    add_dir_options(p_promote)
    p_promote.set_defaults(func=cmd_promote)

    p_expire = sub.add_parser("expire", help="expire queued drafts older than the limit")
    add_dir_options(p_expire)
    p_expire.set_defaults(func=cmd_expire)

    p_enable = sub.add_parser("enable-posting", help="set feedback.enabled: true in config.yaml")
    p_enable.add_argument("--config", required=True, help="path to config.yaml")
    p_enable.set_defaults(func=cmd_enable_posting)

    p_state = sub.add_parser("posting-state", help="print whether feedback.enabled is enabled, disabled or absent")
    p_state.add_argument("--config", required=True, help="path to config.yaml")
    p_state.set_defaults(func=cmd_posting_state)

    p_fdir = sub.add_parser("feedback-dir", help="print the absolute feedback directory the config resolves to; read-only")
    p_fdir.add_argument("--config", required=True, help="path to config.yaml")
    p_fdir.set_defaults(func=cmd_feedback_dir)

    p_disable = sub.add_parser("disable-drafts", help="set feedback.drafts: off in config.yaml")
    p_disable.add_argument("--config", required=True, help="path to config.yaml")
    p_disable.set_defaults(func=cmd_disable_drafts)

    p_prepare = sub.add_parser("prepare-post", help="cut a draft to the bytes a post reads, then scan them for private text")
    p_prepare.add_argument("--config", help="path to config.yaml; required")
    p_prepare.add_argument("--draft", help="path to the draft file the post reads; required")
    p_prepare.set_defaults(func=cmd_prepare_post)

    p_mark = sub.add_parser("mark-blocked", help="record an unattended privacy block in a .blocked sidecar beside the draft")
    p_mark.add_argument("--draft", required=True, help="path to the promoted draft the post would have read")
    p_mark.add_argument("--class", dest="block_class", required=True, choices=BLOCKED_CLASSES, help="the class prepare-post printed")
    p_mark.add_argument("--line", required=True, type=int, help="the line number prepare-post printed")
    p_mark.add_argument("--route", required=True, choices=BLOCKED_ROUTES, help="the route that was blocked")
    p_mark.set_defaults(func=cmd_mark_blocked)

    p_blist = sub.add_parser("blocked-list", help="list drafts an unattended privacy block kept; read-only")
    add_dir_options(p_blist)
    p_blist.add_argument("--json", action="store_true", help="print a JSON array")
    p_blist.add_argument("--all", action="store_true", help="include dismissed and posted drafts")
    p_blist.set_defaults(func=cmd_blocked_list)

    p_dismiss = sub.add_parser("dismiss-blocked", help="mark a blocked draft dismissed; the draft stays in place")
    add_dir_options(p_dismiss)
    which = p_dismiss.add_mutually_exclusive_group(required=True)
    which.add_argument("--draft", help="path to one blocked draft")
    which.add_argument("--all", action="store_true", help="dismiss every blocked draft in the directory")
    p_dismiss.set_defaults(func=cmd_dismiss_blocked)
    return parser


def main(argv: "list[str] | None" = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "list" and args.table and args.json:
        parser.error("argument --table: not allowed with argument --json")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
