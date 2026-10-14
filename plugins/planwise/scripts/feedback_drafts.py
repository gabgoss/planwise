#!/usr/bin/env python3
"""Shared helper for model-drafted feedback files (stdlib only).

Producers and the review surface call this one script to list, admit,
discard, promote and expire model-drafted feedback, and to switch on posting.

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
| `list [--json] [--all]` | Applies expiry, then lists queued and expired drafts. `--all` adds discarded and promoted | 0 |
| `admit <path>` | Needs `--feedback-dir` or `--config`, and the file directly in that directory. A draft already `expired`, `discarded` or `promoted` is left untouched. Otherwise needs `status` to be `pending` or `queued`, no duplicated frontmatter key, and a parseable `created_at`. Fills `pending` ids, replaces a colliding id, replaces a future `created_at` with now, refuses and deletes an oversize or duplicate-title model draft or one whose parsed frontmatter is invalid, refuses and keeps a file whose frontmatter does not parse, then runs expiry and eviction and names each draft it evicts on stderr | 0 admitted, 1 file missing or config unreadable, 2 name does not match, no usable directory option, `Archive/` directory, file not directly in the directory, or a draft already expired, discarded or promoted, 3 refused, expired on admission, or evicted on admission |
| `discard <id>` | Sets `status: discarded` | 0, 1 not found |
| `promote <id>` | Writes the standard draft, sets `status: promoted`, adds `promoted_to:` | 0, 1 not found or discarded, 3 already promoted |
| `expire` | Sets `status: expired` on queued drafts older than `EXPIRY_DAYS` | 0 |
| `enable-posting --config <path>` | Sets `feedback.enabled: true` by text splice, idempotent, in the block's own indent. The result is parsed before it is written, and a result that would not parse is never written | 0, 1 config problem |

The directory comes from `--feedback-dir <abs>` when given, otherwise from
`--config <path>` through `config_loader.load_config()`. `--feedback-dir` must be an
absolute path to an existing directory. A directory resolved from `--config` may
not exist yet, and `list` and `expire` then say so. A feedback directory's own
`Archive/` child is refused by every command except `enable-posting`. An exit of
1 also reports a missing directory option, a missing file or an unreadable config.
Every write resolves a symlink first, so the link stays and its target changes.

Frontmatter is written back by splicing the one changed line, so every other
byte of the file, line endings included, stays as written.

## Read-only functions

A caller that only reports, such as doctor, imports these instead of running
`list`, because `list` applies expiry and so writes.

| Function | Returns |
|---|---|
| `is_expired(draft, now)` | True when the draft was created more than `EXPIRY_DAYS` before `now`. The commands above use this same predicate |
| `count_queued(directory)` | The number of drafts `list` would show as `queued`. Writes nothing |
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

    This is the one expiry predicate. `expire`, `list` and `admit` apply it,
    and a read-only caller uses it to get the same answer without writing. A
    missing or unparseable `created_at` never expires.
    """
    created = _parse_created(draft.fm.get("created_at", ""))
    return created is not None and now - created > timedelta(days=EXPIRY_DAYS)


def count_queued(directory: Path) -> int:
    """How many model drafts `list` would show as `queued` in `directory`.

    Read-only: a queued draft past expiry counts as not queued and is left
    as it is on disk. Only `expire`, `list` and `admit` write its new status.
    """
    now = _now()
    return sum(1 for draft in _iter_drafts(directory) if draft.status == "queued" and not is_expired(draft, now))


def _normalise_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _name_kind(name: str) -> str:
    match = DRAFT_NAME_RE.match(name)
    return match.group(1) if match else ""


def _apply_expiry(drafts: "list[Draft]") -> int:
    """Flip queued drafts older than `EXPIRY_DAYS` to expired. Deletes nothing."""
    now = _now()
    flipped = 0
    for draft in drafts:
        if draft.status != "queued" or not is_expired(draft, now):
            continue
        draft.raw = _set_fm(draft.raw, "status", "expired")
        _write(draft.path, draft.raw)
        draft.fm["status"] = "expired"
        flipped += 1
    return flipped


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


def cmd_list(args: argparse.Namespace) -> int:
    directory, code = _need_dir(args)
    if directory is None:
        return code
    drafts = _iter_drafts(directory)
    _apply_expiry(drafts)
    wanted = {"queued", "expired"}
    if args.all:
        wanted |= {"discarded", "promoted"}
    shown = [d for d in drafts if d.status in wanted]
    if args.json:
        print(json.dumps([_public(d, directory) for d in shown], indent=2))
    elif not shown:
        print("no drafts" + _missing_note(directory))
    else:
        for d in shown:
            print(f"{d.draft_id}\t{d.status}\t{d.fm.get('kind', '')}\t{d.fm.get('title', '')}\t{d.path.name}")
    return 0


def _refusal(draft_path: Path, reason: str) -> int:
    _delete_model_draft(draft_path)
    print(f"feedback draft refused: {reason}", file=sys.stderr)
    return 3


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
    here = path.resolve()
    if here.parent != directory.resolve():
        print(f"feedback draft refused: file is not directly in the feedback directory: {path}", file=sys.stderr)
        return 2

    raw = _read(path)
    fm = _parse_fm(raw)
    # A draft already in a later lifecycle state is a tracked record, not a
    # malformed submission: it is never refused, so it is never deleted here.
    lifecycle = fm.get("status", "").strip() if fm is not None else ""
    if lifecycle in ("expired", "discarded", "promoted"):
        print(f"feedback draft refused: not admissible in status {lifecycle}: {path.name}", file=sys.stderr)
        return 2
    size = path.stat().st_size
    if size > MAX_BYTES:
        return _refusal(path, f"oversize ({size} bytes, limit {MAX_BYTES})")
    if fm is None:
        return _refusal(path, "malformed frontmatter")
    duplicated = _duplicate_key(raw)
    if duplicated:
        return _refusal(path, f"malformed frontmatter (duplicate key {duplicated})")
    missing = [key for key in REQUIRED_KEYS if not fm.get(key)]
    if missing:
        return _refusal(path, f"malformed frontmatter (missing {missing[0]})")
    if fm["kind"] != _name_kind(path.name):
        return _refusal(path, "malformed frontmatter (kind does not match the file name)")
    if fm.get("drafted_by") != "model":
        return _refusal(path, "malformed frontmatter (drafted_by is not model)")
    if fm["status"].strip() not in (PENDING, "queued"):
        return _refusal(path, f"malformed frontmatter (status must be pending or queued, not {fm['status']})")
    if fm["created_at"] != PENDING and _parse_created(fm["created_at"]) is None:
        return _refusal(path, "malformed frontmatter (created_at is not a timestamp)")

    title = _normalise_title(fm["title"])
    others = [d for d in _iter_drafts(directory) if d.path.resolve() != here]
    for other in others:
        if other.status == "queued" and _normalise_title(other.fm.get("title", "")) == title:
            return _refusal(path, "duplicate title among queued drafts")

    if fm["draft_id"] == PENDING:
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
    _write(path, raw)

    drafts = _iter_drafts(directory)
    _apply_expiry(drafts)
    for evicted in _evict(drafts):
        if evicted.path.resolve() != here:
            print(f"feedback_drafts: evicted {evicted.draft_id} ({evicted.path.name}): more than {QUEUE_CAP} queued drafts", file=sys.stderr)
    if not path.exists():
        print("feedback draft refused: evicted on admission: older than the queued drafts", file=sys.stderr)
        return 3
    if any(d.path.resolve() == here and d.status == "expired" for d in drafts):
        print("feedback draft refused: expired on admission: created more than the expiry limit ago", file=sys.stderr)
        return 3
    print(f"admitted {fm['draft_id']}")
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
    target = None
    for suffix in [""] + [f"-{n}" for n in range(2, 10)]:
        candidate = directory / f"{stem}{suffix}.md"
        try:
            with open(candidate, "xb") as handle:
                handle.write(body.encode("utf-8", errors="surrogateescape"))
        except FileExistsError:
            continue
        target = candidate
        break
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


def _enable_posting_text(text: str) -> "tuple[str, str]":
    """Return (new_text, old_value). Only the one `enabled:` line changes."""
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
        return text + gap + f"feedback:{eol}  enabled: true{eol}", "unset"

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
        match = re.match(r"^([ \t]+)enabled:([ \t]*)([^\s#]*)([^\r\n]*)(\r?\n?)$", lines[index])
        if match is None:
            continue
        old = match.group(3)
        if _unquote(old).lower() == "true":
            return text, old
        gap = match.group(2) or " "
        lines[index] = f"{match.group(1)}enabled:{gap}true{match.group(4)}{match.group(5)}"
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
    lines.insert(header + 1, f"{indent}enabled: true{eol}")
    return "".join(lines), "unset"


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
    p_list.set_defaults(func=cmd_list)

    p_admit = sub.add_parser("admit", help="admit a freshly written draft")
    p_admit.add_argument("path")
    add_dir_options(p_admit)
    p_admit.set_defaults(func=cmd_admit)

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
    return parser


def main(argv: "list[str] | None" = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
