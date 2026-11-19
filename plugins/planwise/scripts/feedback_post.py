#!/usr/bin/env python3
"""Post driver for queued feedback drafts (stdlib only).

This script codes the GitHub side of the feedback pipeline that `references/feedback-submission.md`
describes. It imports the config readers and draft helpers from `feedback_drafts.py` and never edits
that file.

## Commands and exit codes

| Command | Behaviour | Exit |
|---|---|---|
| `scan --config C --draft PATH [--title T] [--json]` | Resolves `gh`, builds the search keys of Step 4.5 from the draft's title and body, runs one `gh issue list` per key, merges and ranks the rows, and prints the result. Writes nothing | 0 the scan ran, whatever it found; 1 the config or draft cannot be read; 2 argparse usage error |
| `post --config C --draft-id ID` | The unattended post path: gate 1, then the queued model draft is promoted (a promoted draft with no `.posted` sidecar is retried as it is), then gates 3 and 4, the scan, Unattended Routing, `prepare_post` on the exact file the route posts, one `gh issue create` or `gh issue comment`, and the `.posted` sidecar. Prints one result line | 0 posted; 3 the draft was kept and nothing was posted, or a timed-out post may have happened; 4 posting is off; 1 the config cannot be read or the promote failed; 2 no queued draft has that id, or an argparse usage error |

Exit 0 and exit 3 are both definite results, and the parent flow continues on either. A post whose outcome
is uncertain never exits 1 or 2.

## Resolving `gh`

`resolve_gh()` follows § Resolving `gh`: the file a bare `gh` runs on PATH, then the known install
locations for the platform, each accepted only when `--version` exits 0. It returns the argv prefix
and where it was found, or None. Three environment variables exist for tests only:
`FEEDBACK_POST_GH_ARGV` (a JSON array used as the argv prefix, checked first),
`FEEDBACK_POST_GH_CANDIDATES` (replaces the known locations, `os.pathsep`-separated, empty means none)
and `FEEDBACK_POST_SCAN_BUDGET` (the whole-scan budget in seconds).

## Budgets

Every `gh` call is an argument list run with a 10 second timeout, and no shell builds a command
line. The scan checks its elapsed time before each query and issues none after 30 seconds.
"""

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

import feedback_drafts
import frontmatter_parser

QUERY_TIMEOUT = 10
SCAN_BUDGET = 30.0
MAX_IDENTIFIER_KEYS = 4
MAX_TITLE_TERMS = 3
LIST_LIMIT = "20"
JSON_FIELDS = "number,title,state,createdAt,url"
SHOW_MAX = 5
THRESHOLD = 3
SELF_DUPLICATE_MINUTES = 10

KNOWN_LOCATIONS = {
    "win32": (
        r"C:\Program Files\GitHub CLI\gh.exe",
        r"%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe",
        r"C:\Program Files (x86)\GitHub CLI\gh.exe",
    ),
    "darwin": ("/opt/homebrew/bin/gh", "/usr/local/bin/gh"),
    "linux": ("/usr/bin/gh", "/usr/local/bin/gh", "/home/linuxbrew/.linuxbrew/bin/gh", "~/.local/bin/gh"),
}

STOPWORDS = frozenset([
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "cannot", "did", "do", "does", "for", "from",
    "had", "has", "have", "how", "i", "if", "in", "into", "is", "it", "its", "not", "of", "on", "or", "should",
    "so", "than", "that", "the", "their", "then", "there", "these", "they", "this", "to", "too", "was", "were",
    "what", "when", "where", "which", "while", "who", "why", "will", "with", "would", "you", "your",
    "bug", "issue", "error", "problem", "planwise",
])

SCORE_A, SCORE_B1, SCORE_B2, SCORE_C, SCORE_D = 4, 3, 2, 3, 1

_EXTENSIONS = "md|py|yml|yaml|json|js|ts|sh|ps1|toml|txt"
_FILE_TOKEN_RE = re.compile(r"^(?P<name>.*\.(?:" + _EXTENSIONS + r"))(?::\d+(?:-\d+)?)?$")
_TOKEN_RE = re.compile(r"[^\s`'\"()\[\]<>,;]+")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n")
_NUMBER_REF_RE = re.compile(r"(?:§\s*|\b(?:section|step|gate|line)\s+)(?P<num>\d+(?:\.\d+)*)", re.IGNORECASE)
_KEY_TOKEN_RE = re.compile(r"^[A-Za-z0-9._/:+#-]{3,60}$")
_BARE_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*$")
_FENCE_RE = feedback_drafts._FENCE_RE  # one fence rule for the draft helpers and the scan
ROW_FIELDS = ("number", "title", "state", "createdAt", "url")
_QUOTE_RE = re.compile(r"^ {0,3}>\s?")
_ERROR_SIGNATURES = ("error", "exception", "traceback", "failed", "fatal:", "exit code", "not found", "cannot", "denied", "refused")
_TITLE_STRIP = ".,;:!?()[]{}\"'`"
_PAREN_RE = re.compile(r"\([^()]*\)")
_WRAPPERS = "\"'`()[]{}<>"
TIER_C_MIN_WORDS = 2


# ---------------------------------------------------------------- resolving gh


def _version_ok(argv: "list[str]") -> bool:
    try:
        result = subprocess.run([*argv, "--version"], capture_output=True, text=True, timeout=QUERY_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _candidates() -> "list[str]":
    # Test hook: replaces the known install locations, so a test never reaches an installed gh.
    override = os.environ.get("FEEDBACK_POST_GH_CANDIDATES")
    if override is not None:
        return [entry for entry in override.split(os.pathsep) if entry]
    platform = "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"
    return [os.path.expanduser(os.path.expandvars(entry)) for entry in KNOWN_LOCATIONS[platform]]


def _is_batch(path: str) -> bool:
    """A Windows batch shim. cmd.exe re-parses its arguments, so a title or search string could split there."""
    return os.path.splitext(path)[1].lower() in (".cmd", ".bat")


def resolve_gh() -> "dict | None":
    """Return `{"argv": [...], "source": ..., "note": ...}` for the first `gh` that answers `--version`, or None.

    The order is the reference's: the file a bare `gh` runs on PATH, folder by folder, then the known
    install locations. A `.cmd` or `.bat` shim is skipped wherever it is found, and the search goes on.
    Nothing is edited or installed.
    """
    # Test hook: a JSON argv prefix read before PATH, so a test can run its fake gh with no cmd.exe layer.
    override = os.environ.get("FEEDBACK_POST_GH_ARGV")
    if override:
        argv = json.loads(override)
        if isinstance(argv, list) and argv and all(isinstance(part, str) for part in argv) and _version_ok(argv):
            return {"argv": argv, "source": "override", "note": "gh argv taken from FEEDBACK_POST_GH_ARGV"}
        return None
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        on_path = shutil.which("gh", path=folder) if folder else None
        if on_path and not _is_batch(on_path) and _version_ok([on_path]):
            return {"argv": [on_path], "source": "path", "note": "found on PATH"}
    for candidate in _candidates():
        if os.path.isfile(candidate) and not _is_batch(candidate) and _version_ok([candidate]):
            return {"argv": [candidate], "source": "known-location", "note": f"found at {candidate}, not on this session's PATH"}
    return None


# ---------------------------------------------------------------- search keys


def _key_ok(key: str) -> bool:
    """The key filter: every whitespace token matches the key charset and length; no leading path root, `@`, bare number or lone stopword."""
    tokens = key.split()
    if not tokens or not all(_KEY_TOKEN_RE.match(token) for token in tokens):
        return False
    if key[0] in "/~\\" or re.match(r"^[A-Za-z]:", key) or "@" in key:
        return False
    return not (_BARE_NUMBER_RE.match(key) or (len(tokens) == 1 and key.lower() in STOPWORDS))


def _file_key(token: str) -> "str | None":
    """The Tier-A key for one token, or None. The extension must end the token, before an optional line suffix."""
    token = token.rstrip(".,;:!?")
    match = _FILE_TOKEN_RE.match(token)
    if match is None:
        return None
    base = re.split(r"[\\/]", match.group("name"))[-1].lstrip("-./")
    return base or None


def _tier_a(text: str, offset: int) -> "list[tuple[str, int, int, str]]":
    """Tier-A keys as (key, score, position, tier). A section, step, gate or line number joins the nearest preceding key in its sentence."""
    found = []
    position = 0
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        start = text.find(sentence, position) if sentence else position
        position = start + len(sentence)
        events = []
        for match in _TOKEN_RE.finditer(sentence):
            key = _file_key(match.group(0))
            if key is not None:
                events.append((match.start(), "key", key))
        for match in _NUMBER_REF_RE.finditer(sentence):
            events.append((match.start(), "num", match.group("num")))
        events.sort(key=lambda event: event[0])
        sentence_keys: list[list] = []
        for at, kind, value in events:
            if kind == "key":
                sentence_keys.append([value, offset + start + at])
            elif sentence_keys and _KEY_TOKEN_RE.match(value):
                sentence_keys[-1][0] = f"{sentence_keys[-1][0]} {value}"
        found.extend((key, SCORE_A, at, "A") for key, at in sentence_keys)
    return found


def _outside_fences(text: str) -> "list[tuple[int, str, bool]]":
    """Each line as (offset, line, inside a fenced block). A fence delimiter line reads as inside."""
    lines = []
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        opener = _FENCE_RE.match(bare)
        if opener is not None:
            if fence is None:
                fence = opener.group(1)[0]
                lines.append((offset, bare, True))
                offset += len(line)
                continue
            if opener.group(1)[0] == fence:
                fence = None
                lines.append((offset, bare, True))
                offset += len(line)
                continue
        lines.append((offset, bare, fence is not None))
        offset += len(line)
    return lines


def _tier_b(text: str, offset: int) -> "list[tuple[str, int, int, str]]":
    found = []
    for at, line, fenced in _outside_fences(text):
        if fenced:
            continue
        for match in _BACKTICK_RE.finditer(line):
            span = match.group(1).strip()
            words = span.split()
            if not span or len(span) > 40 or len(words) > 4:
                continue
            if any(sep in span for sep in "._-/") or 2 <= len(words) <= 4:
                found.append((span, SCORE_B1, offset + at + match.start(), "B1"))
            else:
                found.append((span, SCORE_B2, offset + at + match.start(), "B2"))
    return found


def tier_c_key(content: str) -> str:
    """The Tier-C key of one error line, or "": parenthesised fragments dropped, each word stripped of surrounding
    quotes and brackets, words that fail the per-token pattern dropped, the first 8 survivors kept, 2 at least."""
    count = 1
    while count:  # innermost first, so a nested fragment goes too
        content, count = _PAREN_RE.subn(" ", content)
    words = [word.strip(_WRAPPERS) for word in content.split()]
    kept = [word for word in words if _KEY_TOKEN_RE.match(word)][:8]
    return " ".join(kept) if len(kept) >= TIER_C_MIN_WORDS else ""


def _tier_c(text: str, offset: int) -> "list[tuple[str, int, int, str]]":
    """At most one key: the Tier-C key of the first fenced or quoted error line whose key passes the filter."""
    for at, line, fenced in _outside_fences(text):
        if _FENCE_RE.match(line):
            continue
        quote = _QUOTE_RE.match(line)
        if not fenced and quote is None:
            continue
        content = line[quote.end():] if quote is not None and not fenced else line
        lowered = content.lower()
        if not any(signature in lowered for signature in _ERROR_SIGNATURES):
            continue
        key = tier_c_key(content)
        if key and _key_ok(key):
            return [(key, SCORE_C, offset + at, "C")]
    return []


def title_terms(title: str) -> "list[str]":
    """Tier-D terms: title words of at least 4 characters after stopword removal, in title order, each once."""
    terms = []
    seen = set()
    for word in title.split():
        word = word.strip(_TITLE_STRIP)
        if len(word) < 4 or word.lower() in STOPWORDS or word.lower() in seen or not _key_ok(word):
            continue
        seen.add(word.lower())
        terms.append(word)
    return terms


def select_keys(title: str, body: str) -> "list[dict]":
    """The identifier keys (Tiers A-C) the scan sends: filtered, de-duplicated, ranked, at most 4.

    The title is read before the body for Tiers A and B, so it counts as the first appearance.
    """
    head = title + "\n"
    pool = _tier_a(head, 0) + _tier_a(body, len(head))
    pool += _tier_b(head, 0) + _tier_b(body, len(head))
    pool += _tier_c(body, len(head))
    best: dict[str, tuple[str, int, int, str]] = {}
    for key, score, at, tier in pool:
        if not _key_ok(key):
            continue
        folded = key.lower()
        held = best.get(folded)
        if held is None or score > held[1] or (score == held[1] and at < held[2]):
            best[folded] = (key, score, at, tier)
    ranked = sorted(best.values(), key=lambda item: (-item[1], item[2]))[:MAX_IDENTIFIER_KEYS]
    return [{"key": key, "score": score, "tier": tier} for key, score, _at, tier in ranked]


def plan_queries(title: str, keys: "list[dict]") -> "list[dict]":
    """The queries in run order: identifier keys by score, then the title query; pure prose adds one query per title term."""
    terms = title_terms(title)
    queries = [{"query": item["key"], "score": item["score"], "kind": "identifier"} for item in keys]
    if terms:
        queries.append({"query": " ".join(terms[:MAX_TITLE_TERMS]), "score": SCORE_D, "kind": "title"})
    if not keys:
        queries.extend({"query": term, "score": SCORE_D, "kind": "title-term"} for term in terms[:MAX_TITLE_TERMS])
    # One search per distinct string: a one-term title query equals its own term query.
    seen: set[str] = set()
    unique = []
    for query in queries:
        if query["query"].casefold() not in seen:
            seen.add(query["query"].casefold())
            unique.append(query)
    return unique


# ---------------------------------------------------------------- the draft


def read_draft(path: Path) -> "tuple[str, str]":
    """Return (title, body) for a draft file: the frontmatter `title`, else the first heading; the body without
    its frontmatter, its trailing scan annotation and its `### Environment` sections."""
    raw = feedback_drafts._read(path)
    text = raw.replace("\r\n", "\n")
    title = ""
    parts = frontmatter_parser.split_frontmatter_block(text)
    if parts is not None:
        fm = feedback_drafts._parse_fm(raw) or {}
        title = fm.get("title", "")
        text = parts[1]
    cut = feedback_drafts._annotation_cut(text)
    if cut != -1:
        text = text[:cut]
    body = feedback_drafts._drop_environment(text)
    if not title:
        heading = re.search(r"(?m)^ {0,3}#{1,2}[ \t]+(.+?)[ \t]*$", body)
        title = heading.group(1) if heading else ""
    return title, body


# ---------------------------------------------------------------- running the scan


def _list_argv(gh: "list[str]", repo: str, query: "str | None") -> "list[str]":
    argv = [*gh, "issue", "list", "-R", repo, "--state", "all", "--limit", LIST_LIMIT]
    if query is not None:
        argv += ["--search", f"{query} in:title,body"]
    return argv + ["--json", JSON_FIELDS]


def _run_query(argv: "list[str]") -> "tuple[str, list]":
    """Run one `gh issue list`. Returns (status, rows); status is ok, timeout or error."""
    try:
        result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=QUERY_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return "timeout", []
    except OSError:
        return "error", []
    if result.returncode != 0:
        return "error", []
    try:
        rows = json.loads(result.stdout or "[]")
    except ValueError:
        return "error", []
    return "ok", [row for row in rows if isinstance(row, dict) and "number" in row] if isinstance(rows, list) else []


def _budget() -> float:
    try:
        return float(os.environ.get("FEEDBACK_POST_SCAN_BUDGET", SCAN_BUDGET))
    except ValueError:
        return SCAN_BUDGET


def _created(row: dict) -> "datetime | None":
    return feedback_drafts._parse_created(str(row.get("createdAt", "")))


def _project(row: dict) -> dict:
    """The five fields a candidate row keeps: number, title, state, createdAt and url."""
    return {key: row.get(key) for key in ROW_FIELDS}


def merge_rows(results: "list[tuple[dict, list]]", title: str, now: datetime) -> "tuple[list[dict], int | None]":
    """Union rows on `number`, recording matched keys and the best key score. Drops this draft's own earlier post."""
    merged: dict[int, dict] = {}
    self_duplicate = None
    for query, rows in results:
        for row in rows:
            created = _created(row)
            if row.get("title") == title and created is not None and (now - created).total_seconds() <= SELF_DUPLICATE_MINUTES * 60:
                self_duplicate = row["number"]
                continue
            entry = merged.setdefault(row["number"], {**_project(row), "matched_keys": [], "best_key_score": 0})
            if query["query"] not in entry["matched_keys"]:
                entry["matched_keys"].append(query["query"])
                entry.setdefault("_scores", []).append(query["score"])
            entry["best_key_score"] = max(entry["best_key_score"], query["score"])
    return list(merged.values()), self_duplicate


def score_candidate(entry: dict, basenames: "list[str]", now: datetime) -> int:
    score = sum(entry.get("_scores", []))
    candidate_title = (entry.get("title") or "").lower()
    if any(name.lower() in candidate_title for name in basenames):
        score += 2
    created = _created(entry)
    if created is not None:
        age_days = (now - created).total_seconds() / 86400
        if age_days <= 14:
            score += 2
        elif age_days <= 90:
            score += 1
    return score


def _order_key(entry: dict) -> tuple:
    created = _created(entry)
    stamp = created.timestamp() if created is not None else 0.0
    return (-entry["score"], -entry["best_key_score"], (entry.get("state") or "").upper() != "OPEN", -stamp)


def rank(merged: "list[dict]") -> "tuple[list[dict], int, int]":
    """Return (shown, further, suppressed): candidates scoring at least 3, at most 5 shown.

    A candidate matched only on title terms never outranks one with a key score of 3 or more, and
    the two highest-scoring candidates matched by a cited file name always keep a slot.
    """
    kept = sorted((entry for entry in merged if entry["score"] >= THRESHOLD), key=_order_key)
    suppressed = len(merged) - len(kept)
    high = [index for index, entry in enumerate(kept) if entry["best_key_score"] >= 3]
    if high:
        last = high[-1]
        head = kept[: last + 1]
        kept = [e for e in head if e["best_key_score"] != 1] + [e for e in head if e["best_key_score"] == 1] + kept[last + 1:]
    shown = kept[:SHOW_MAX]
    reserved = [entry for entry in kept if entry["best_key_score"] == 4][:2]
    for entry in reserved:
        if entry in shown:
            continue
        for index in range(len(shown) - 1, -1, -1):
            if shown[index] not in reserved:
                shown[index] = entry
                break
    shown.sort(key=kept.index)
    return shown, len(kept) - len(shown), suppressed


def _public(entry: dict) -> dict:
    return {key: value for key, value in entry.items() if not key.startswith("_")}


def run_scan(gh: "dict | None", repo: str, title: str, body: str) -> dict:
    """Run the duplicate scan and return its result record. Never raises for a `gh` failure."""
    keys = select_keys(title, body)
    queries = plan_queries(title, keys)
    report = {"gh": gh, "repo": repo, "title": title, "keys": keys, "queries": [], "budget_stopped": False,
              "merged": [], "ranked": [], "further": 0, "self_duplicate": None, "notice": "", "outcome": "", "caveat": ""}

    def unknown(reason: str) -> dict:
        report["outcome"] = "UNKNOWN"
        report["caveat"] = f"Duplicate scan could not run — {reason}. Whether this duplicates an existing issue is unknown."
        return report

    if gh is None:
        return unknown("gh is not available")
    if not queries:
        return unknown("the draft gives no usable search key")

    started = time.monotonic()
    budget = _budget()
    results = []
    for query in queries:
        argv = _list_argv(gh["argv"], repo, query["query"])
        record = {**query, "argv": argv, "status": "not-run", "rows": 0}
        report["queries"].append(record)
        if time.monotonic() - started >= budget:
            report["budget_stopped"] = True
            continue
        record["status"], rows = _run_query(argv)
        record["rows"] = len(rows)
        if record["status"] == "ok":
            results.append((query, rows))

    returned = sum(1 for record in report["queries"] if record["status"] == "ok")
    pure_prose = not keys
    recency = None
    if pure_prose and returned == len(queries) and not any(rows for _query, rows in results):
        argv = _list_argv(gh["argv"], repo, None)
        record = {"query": "", "score": 0, "kind": "recency", "argv": argv, "status": "not-run", "rows": 0}
        report["queries"].append(record)
        if time.monotonic() - started >= budget:
            report["budget_stopped"] = True
        else:
            record["status"], recency = _run_query(argv)
            record["rows"] = len(recency)

    now = datetime.now(timezone.utc)
    merged, self_duplicate = merge_rows(results, title, now)
    if self_duplicate is not None:
        report["self_duplicate"] = self_duplicate
        report["notice"] = f"This draft appears to have already been posted as #{self_duplicate} — check before posting again."
    basenames = [item["key"].split()[0] for item in keys if item["score"] == SCORE_A]
    for entry in merged:
        entry["score"] = score_candidate(entry, basenames, now)
    shown, further, suppressed = rank(merged)
    report["merged"] = [_public(entry) for entry in sorted(merged, key=_order_key)]
    report["ranked"] = [_public(entry) for entry in shown]
    report["further"] = further

    # The recency listing counts as one more search: a listing that failed, timed out or was skipped by
    # the budget makes the scan incomplete, never WEAK or CLEAR.
    planned = len(report["queries"])
    returned = sum(1 for record in report["queries"] if record["status"] == "ok")
    if recency is not None and report["queries"][-1]["status"] != "ok":
        recency = None
    if returned == 0:
        return unknown("every search failed or timed out")
    if returned < planned:
        report["outcome"] = "INCOMPLETE"
        report["caveat"] = f"Duplicate scan was incomplete — {returned} of {planned} searches returned. Candidates below may be missing entries."
    elif recency is not None:
        newest = sorted(recency, key=lambda row: (_created(row) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)[:SHOW_MAX]
        report["ranked"] = [_project(row) for row in newest]
        report["outcome"] = "WEAK"
        report["caveat"] = ("Duplicate scan: nothing matched, but the draft cites no file, command, or error string — only title wording "
                            "was searched, which is a weak signal. The 5 most recent issues are listed for comparison.")
    elif shown:
        report["outcome"] = "FOUND"
    elif suppressed:
        report["outcome"] = "CLEAR"
        report["caveat"] = f"Duplicate scan: no close matches in {repo}, open or closed ({suppressed} weak matches suppressed)."
    else:
        report["outcome"] = "CLEAR"
        report["caveat"] = f"Duplicate scan: no matching issues found in {repo}, open or closed, across {planned} searches."
    return report


# ---------------------------------------------------------------- commands


def cmd_scan(args: argparse.Namespace) -> int:
    config = Path(args.config)
    draft = Path(args.draft)
    if not config.is_file():
        print(f"feedback_post: config.yaml not found at {config}", file=sys.stderr)
        return 1
    if not draft.is_file():
        print(f"feedback_post: draft not found at {draft}", file=sys.stderr)
        return 1
    try:
        _include_environment, repo = feedback_drafts.read_post_settings(config)
        title, body = read_draft(draft)
    except feedback_drafts._CONFIG_ERRORS as exc:
        print(f"feedback_post: {exc}", file=sys.stderr)
        return 1
    if args.title is not None:
        title = args.title
    report = run_scan(resolve_gh(), repo, title, body)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    if report["notice"]:
        print(report["notice"])
    if report["caveat"]:
        print(report["caveat"])
    for entry in report["ranked"]:
        print(f"#{entry['number']}\t{entry.get('state', '')}\t{entry.get('title', '')}\t{entry.get('url', '')}")
    if report["further"]:
        print(f"… and {report['further']} further lower-ranked matches (not shown).")
    return 0


# ---------------------------------------------------------------- the post chain

EXIT_POSTED, EXIT_FAILED, EXIT_NO_DRAFT, EXIT_KEPT, EXIT_POSTING_OFF = 0, 1, 2, 3, 4
LABELS = {"bug": "bug", "lesson": "enhancement", "idea": "enhancement"}
POSTING_OFF_LINE = "Posting is off: config.yaml does not set feedback.enabled to true. The draft was saved and nothing was posted."
COMMENT_LEAD_IN = ("Filed with `/planwise feedback` as a comment rather than a new issue — this looked like the same "
                   "subject as this thread. **{title}**")
UNATTENDED_PROVENANCE = ("Drafted by Claude via planwise feedback drafting; filed unattended from a model-written draft, "
                         "and no person reviewed it before posting.")


def _kept(reason: str, path: Path) -> int:
    """Print the one fallback line for a kept draft and return exit 3."""
    print(f"Feedback draft kept, not posted: {reason}. Draft: {path.resolve()}")
    return EXIT_KEPT


def _marker_path(posted: Path) -> Path:
    return posted.with_name(posted.name + ".posted")


def _comment_draft_name(number: int, promoted: Path) -> str:
    """`{date}-comment-{NN}-{promoted stem}.md`. The promoted stem is unique to its source draft, unlike the title slug."""
    return f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-comment-{number}-{promoted.stem}.md"


def _was_posted(promoted: Path) -> bool:
    """Whether a `.posted` sidecar records a post of this promoted file, or of a comment draft made from it."""
    if _marker_path(promoted).exists():
        return True
    pattern = re.compile(r"\d{4}-\d{2}-\d{2}-comment-\d+-" + re.escape(promoted.stem) + r"\.md\.posted")
    return any(pattern.fullmatch(entry.name) for entry in promoted.parent.iterdir())


def _resolve_draft(directory: Path, draft_id: str) -> "tuple[feedback_drafts.Draft | None, Path | None, str]":
    """Return (draft, promoted file, "") for a draft `post` may act on, or (None, None, reason).

    A queued draft returns no promoted file yet. A promoted draft whose promoted file exists and carries no
    `.posted` sidecar is a kept draft from an earlier run: it returns that file, so a retry promotes nothing.
    Read-only: an expired draft is not flipped on disk.
    """
    draft = feedback_drafts._find(directory, draft_id)
    if draft is None:
        return None, None, "unknown"
    if draft.status == "promoted":
        promoted = directory / draft.fm.get("promoted_to", "")
        if draft.fm.get("promoted_to") and promoted.is_file() and not _was_posted(promoted):
            return draft, promoted, ""
        return None, None, "promoted"
    if draft.status == "queued" and feedback_drafts.is_expired(draft, feedback_drafts._now()):
        return None, None, "expired"
    if draft.status != "queued":
        return None, None, draft.status if draft.status in ("expired", "discarded") else "unknown"
    return draft, None, ""


def _mark_unattended(promoted: Path) -> None:
    """Replace the promote step's provenance sentence, which says a person approved the text, with the unattended one."""
    text = feedback_drafts._read(promoted)
    new_text = text.replace(feedback_drafts.PROVENANCE_LINE, UNATTENDED_PROVENANCE)
    if new_text != text:
        feedback_drafts._write(promoted, new_text)


def _promote(config: Path, draft_id: str) -> "tuple[Path | None, str]":
    """Run the promote command on one id. Returns (promoted path, "") or (None, its error text)."""
    args = argparse.Namespace(feedback_dir=None, config=str(config), id=draft_id)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = feedback_drafts.cmd_promote(args)
    lines = out.getvalue().strip().splitlines()
    if code != 0 or not lines:
        return None, " ".join(err.getvalue().split()) or f"promote exited {code}"
    return Path(lines[-1]), ""


def _auth_ok(gh: "list[str]") -> bool:
    try:
        result = subprocess.run([*gh, "auth", "status"], capture_output=True, text=True, timeout=QUERY_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def pick_route(report: dict) -> "tuple[str, int | None]":
    """Unattended Routing, first match wins: self-duplicate, a ranked candidate (comment), else a new issue."""
    if report.get("self_duplicate") is not None:
        return "self-duplicate", report["self_duplicate"]
    if report.get("outcome") in ("FOUND", "INCOMPLETE") and report.get("ranked"):
        return "comment", report["ranked"][0]["number"]
    return "issue", None


def _post_url(stdout: str) -> str:
    """The URL `gh` prints on a successful post: its last line that starts with https://, else empty."""
    urls = [line.strip() for line in (stdout or "").splitlines() if line.strip().startswith("https://")]
    return urls[-1] if urls else ""


def write_posted_marker(posted: Path, url: str, route: str) -> Path:
    """Write the `.posted` sidecar beside the posted file. The posted file itself is never touched. Raises OSError."""
    marker = _marker_path(posted)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(marker, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"posted: {stamp}\nurl: {url}\nroute: {route}\n")
    return marker


def cmd_post(args: argparse.Namespace) -> int:
    config = Path(args.config)
    # Gate 1: posting state. Nothing is written and no gh call runs before it passes.
    if not config.is_file():
        print(f"feedback_post: config.yaml not found at {config}", file=sys.stderr)
        return EXIT_FAILED
    try:
        state = feedback_drafts.read_posting_state(config)
    except (OSError, ValueError) as exc:
        print(f"feedback_post: {exc}", file=sys.stderr)
        return EXIT_FAILED
    if state != "enabled":
        print(POSTING_OFF_LINE)
        return EXIT_POSTING_OFF
    try:
        include_environment, repo = feedback_drafts.read_post_settings(config)
    except feedback_drafts._CONFIG_ERRORS as exc:
        print(f"feedback_post: {exc}", file=sys.stderr)
        return EXIT_FAILED

    # Resolve the queued draft, then promote it. The routes scan and post the promoted file.
    with contextlib.redirect_stderr(io.StringIO()) as err:
        directory, _code = feedback_drafts._need_dir(argparse.Namespace(feedback_dir=None, config=str(config)))
    if directory is None:
        print(f"feedback_post: {' '.join(err.getvalue().split())}", file=sys.stderr)
        return EXIT_FAILED
    draft, promoted, reason = _resolve_draft(directory, args.draft_id)
    if draft is None:
        print(f"feedback_post: no queued draft with id {args.draft_id} ({reason}); nothing was posted.", file=sys.stderr)
        return EXIT_NO_DRAFT
    title = draft.fm.get("title", "")
    label = LABELS.get(feedback_drafts._name_kind(draft.path.name) or draft.fm.get("kind", ""), "bug")
    if promoted is None:
        promoted, error = _promote(config, args.draft_id)
        if promoted is None:
            print(f"feedback_post: the draft could not be promoted: {error}", file=sys.stderr)
            return EXIT_FAILED
    # This path has no reviewer, so the posted text must not say a person approved it.
    try:
        _mark_unattended(promoted)
    except OSError:
        return _kept("the draft file could not be updated", promoted)

    # Gates 3 and 4.
    gh = resolve_gh()
    if gh is None:
        return _kept("gh was not found", promoted)
    if not _auth_ok(gh["argv"]):
        return _kept("gh is not signed in", promoted)

    # Step 4.5 and Unattended Routing.
    _title, body = read_draft(promoted)
    report = run_scan(gh, repo, title, body)
    route, number = pick_route(report)
    if route == "self-duplicate":
        print(report["notice"])
        return EXIT_KEPT
    posted = promoted
    if route == "comment":
        # The number comes from gh's JSON; anything but an integer keeps the draft rather than guessing a target.
        if not isinstance(number, int):
            return _kept("the top-ranked issue has no usable number", promoted)
        posted = promoted.with_name(_comment_draft_name(number, promoted))
        try:
            feedback_drafts._write(posted, COMMENT_LEAD_IN.format(title=title) + "\n\n" + feedback_drafts._read(promoted))
        except OSError:
            return _kept("the comment draft could not be written", promoted)

    # The privacy gate runs on the exact file the route posts, after the last write to it.
    try:
        verdict, found, line, _data = feedback_drafts.prepare_post(posted, include_environment=include_environment, repo=repo)
    except feedback_drafts._CONFIG_ERRORS:
        return _kept("the privacy check could not run", posted)
    if verdict != "clean":
        return _kept(f"the privacy check blocked it ({found} at line {line})", posted)
    # The issue route sends the title outside the body file, so the same rules scan it too.
    if route == "issue":
        title_hit = feedback_drafts.scan_post_bytes(title.encode("utf-8", errors="surrogateescape"), repo)
        if title_hit is not None:
            return _kept(f"the privacy check blocked its title ({title_hit[0]})", posted)

    # The post: one argv list, so a title holding quotes reaches gh as one argument.
    if route == "comment":
        argv = [*gh["argv"], "issue", "comment", "-R", repo, str(number), "--body-file", str(posted)]
    else:
        argv = [*gh["argv"], "issue", "create", "-R", repo, "--title", title, "--body-file", str(posted), "--label", label]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=QUERY_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        print(f"Feedback draft kept, not confirmed: the post to {repo} timed out, so the issue may exist. "
              f"Check {repo} before posting again. Draft: {posted.resolve()}")
        return EXIT_KEPT
    except OSError:
        return _kept(f"the post to {repo} failed", posted)
    if result.returncode != 0:
        return _kept(f"the post to {repo} failed", posted)

    # The post succeeded. Nothing from here on may turn it into a failure exit.
    url = _post_url(result.stdout)
    where = f"as a comment on #{number}" if route == "comment" else "as a new issue"
    print(f"Feedback posted to {repo} {where}: {url or '(gh printed no URL)'}")
    try:
        write_posted_marker(posted, url, route)
    except OSError:
        print(f"The draft could not be marked posted: the .posted marker could not be written at {_marker_path(posted).resolve()}")
    return EXIT_POSTED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="feedback_post", description="Scan for and post feedback drafts to GitHub.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_scan = sub.add_parser("scan", help="run the duplicate scan for one draft; read-only")
    p_scan.add_argument("--config", required=True, help="path to config.yaml")
    p_scan.add_argument("--draft", required=True, help="path to the draft file")
    p_scan.add_argument("--title", help="the issue title; defaults to the draft's frontmatter title, then its first heading")
    p_scan.add_argument("--json", action="store_true", help="print the full result as JSON")
    p_scan.set_defaults(func=cmd_scan)
    p_post = sub.add_parser("post", help="post one queued model draft with no question: the unattended post path")
    p_post.add_argument("--config", required=True, help="path to config.yaml")
    p_post.add_argument("--draft-id", required=True, help="the draft_id of a queued model draft")
    p_post.set_defaults(func=cmd_post)
    return parser


def main(argv: "list[str] | None" = None) -> int:
    # Caveats, notices and result lines carry an em dash, and a piped stream on Windows defaults to the ANSI code page.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
