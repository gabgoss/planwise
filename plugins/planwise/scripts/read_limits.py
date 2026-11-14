#!/usr/bin/env python3
"""Read-tool mechanical limit gates and the file-risk classifier.

These are FIXED, empirically-measured harness facts about the Read tool
(`READ_FILE_BYTE_CAP`, `READ_PAGE_CAP_TOKENS`, `BYTES_PER_TOKEN`, ...) — NOT
derived from a `/context` report and NOT written by any calibration routine.
A file can fit a project's measured session budget yet still be unreadable in
a single Read call; `classify_file` folds these mechanical gates with an
optional cost-budget gate (an externally-derived thresholds dict) and takes
the max severity.

Pure functions only — no filesystem writes, no subprocess. Re-validate the
constants via a headless CLI probe if the harness changes. This file names
no specific CLI build — the build a project's harness was last confirmed
against is consumer-side state in that project's own config.yaml
(`context.verified_cli_version`), not a literal pinned here; see
`READ_LIMITS_MEASURED_ON` and `/planwise doctor`'s verified-CLI-version
drift report.
"""

import math
import os
import re

# ---------------------------------------------------------------------------
# FIXED Read-tool limit constants (empirically re-measured 2026-09-07 across
# Haiku 4.5, Sonnet 5, Opus 5, and Fable 5 — the caps are identical on all
# four; only the tokenizer weight differs).
#
# These are mechanical harness facts about the Read tool, NOT derived from a
# `/context` report and NOT written by calibrate(). Re-validate via a headless
# `claude -p --model X` probe if the harness changes (see READ_LIMITS_MEASURED_ON
# and /planwise doctor's verified-CLI-version drift report, which flags staleness
# against the consuming project's own config.yaml — never a version hardcoded here).
#
# Gate priority: tokens first, then bytes, then lines — whichever comes first.
# The binding split targets for generated artifacts are the WARN thresholds
# (so no warning ever fires), not the hard caps.
# ---------------------------------------------------------------------------

# Token page-cap gate (PRIMARY — binds first on text by ~3.6x): above this a
# single Read without an explicit `limit` returns only the first page
# (~21,200 tokens, ~85% of the cap); an explicit `limit` spanning more than
# the cap hard-errors with zero content (the error reports the exact token
# count). Warn at 22K — the warn threshold produces NO runtime marker, so it
# must be checked proactively (measure_files.py / classify_file).
READ_PAGE_CAP_TOKENS = 25000
READ_TOKEN_WARN = 22000

# Byte gate (SECONDARY, model-independent): without an offset/limit, Read
# refuses a file STRICTLY LARGER than this cap, reporting "exceeds maximum
# allowed size (256KB)". Measured boundary (2026-09-07): a
# 262,145-byte file refuses; a 262,144-byte file does NOT. `_read_level`
# compares with `>=`, so it flags the one exact-cap size a byte early — a
# deliberate conservatism, and unreachable in practice: 256 KiB of text is
# far past the token gate (measured 100,610 tokens) and already Critical
# there. 256 KiB hard cap; warn at 240 KiB.
# Probed 2026-11-14 on CLI v2.1.296 or later: a whole-file Read with
# `allow_large: true` returned a 270,020-byte file whole, so `allow_large`
# lifts this gate (verdict: lifted). Without the parameter the refusal held.
READ_FILE_BYTE_CAP = 262144   # 256 * 1024
READ_BYTE_WARN = 245760       # 240 * 1024

# Line gate (DISTANT THIRD, defensive): first-page line window. Measured
# sessions saw 3,000+-line single pages, so this is a defensive gate, not a
# hard-measured harness fact; it can bind alone only on many-short-line files
# that pass the token and byte gates (e.g. 3,000 lines x ~17 B/line).
# Probed 2026-11-14 on CLI v2.1.296 or later: a 2,500-line file under the
# token cap read whole both with and without `allow_large: true`, so no
# window bound and the probe cannot show `allow_large` lifting it (verdict:
# unclear).
READ_LINE_CAP = 2000

# Empirical bytes-per-token ratios by model family and content class
# (harness-reported token counts / on-disk bytes). Every cell was measured
# 2026-09-07 against a 150 KB corpus of its own content class; no cell is
# derived from another.
#
# The tokenizer splits by model GENERATION, not by model size: Opus 5,
# Sonnet 5 and Fable 5 report the SAME token count for the same file (a 1-2
# token spread over ~54K), and Haiku 4.5 alone is lighter, by ~1.31-1.38x.
# A superseded reading had Sonnet in a "~1.44x lighter Haiku/Sonnet family";
# that grouping is measured false, and it under-estimated Sonnet's token cost
# by ~42% — the unsafe direction, because it returns a passing verdict for a
# file the harness then refuses to read whole.
#
# A SMALLER ratio means MORE tokens per byte, so the gate-conservative choice
# is the smallest ratio available and every cell is rounded DOWN from its
# measurement. Note that code tokenizes DENSER than prose, not lighter.
#
# Measured (bytes / harness-reported tokens), before the rounding down:
#   Claude 5 family   dense-md 2.605 · prose 2.906 · code 2.783
#   Haiku 4.5         dense-md 3.540 · prose 4.023 · code 3.657
#
# Two structured-data classes, added 2026-09-23 (same oracle: the Read
# tool's over-cap error reports the exact token count). Both sit
# BELOW dense-md, and both are identifiable by file extension, which is why
# they are reached only through an explicit or auto-detected content class
# and never through the no-class fallback (see FALLBACK_CONTENT_CLASS).
#
#   notebook — a `.ipynb` file. The Read tool renders a notebook as a cell
#     view rather than returning the raw JSON, and counts tokens on THAT view:
#     the same 76,917 bytes measured 31,395 tokens as `.ipynb` and 37,176 as
#     `.json`. The ratio is on-disk bytes of an outputs-cleared notebook per
#     rendered token. An uncleared notebook's large outputs are elided by the
#     renderer, so for it the estimate is an upper bound; measure the cleared
#     file. Six cleared samples, 62 KB to 203 KB, LF- and CRLF-serialized:
#       Claude 5 family   2.382 · 2.409 · 2.450 · 2.494 · 2.539 · 2.674
#       Haiku 4.5         3.333 · 3.387 · 3.414 · 3.637   (the two smallest
#                         samples read whole under Haiku's cap — no count)
#   json — raw `.json` / `.jsonl` / `.ndjson`. Three notebook-JSON corpora
#     read as plain JSON, 77 KB to 207 KB:
#       Claude 5 family   2.069 · 2.161 · 2.216
#       Haiku 4.5         2.717 · 2.809 · 2.842
#   Cross-family check on every sample: Claude 5 tokens / Haiku tokens landed
#   1.28-1.40, inside the 1.25-1.45 band the tests pin.
DEFAULT_BYTES_PER_TOKEN = 2.6  # most restrictive TEXT class: dense markdown, Claude 5 tokenizer
BYTES_PER_TOKEN = {
    "opus":   {"dense-md": 2.6, "prose": 2.9, "code": 2.7, "notebook": 2.3, "json": 2.0},
    "fable":  {"dense-md": 2.6, "prose": 2.9, "code": 2.7, "notebook": 2.3, "json": 2.0},   # same tokenizer as opus (measured)
    "sonnet": {"dense-md": 2.6, "prose": 2.9, "code": 2.7, "notebook": 2.3, "json": 2.0},   # same tokenizer as opus (measured directly)
    "haiku":  {"dense-md": 3.5, "prose": 4.0, "code": 3.6, "notebook": 3.3, "json": 2.7},   # Haiku 4.5 — the one lighter family
}

# The class `bytes_per_token()` falls back to when no content class is given.
# It is the densest TEXT class: an extension cannot tell prose from a dense
# table index, so the fallback must cover the heaviest text. The structured
# classes below it (notebook, json) are always identifiable by extension, so
# they are selected by `content_class_for_path()` instead of by guessing —
# folding them into the fallback would inflate every markdown estimate.
FALLBACK_CONTENT_CLASS = "dense-md"

# Extension → content class for the classes an extension identifies. Text
# extensions deliberately map to nothing: `.md` may be prose or a dense index,
# and the conservative fallback covers both.
NOTEBOOK_SUFFIXES = frozenset({".ipynb"})
JSON_SUFFIXES = frozenset({".json", ".jsonl", ".ndjson"})

# Provenance so a re-validation task can date-check these constants. No CLI
# build is pinned here — that would need editing every point release. The
# build a project's harness was last confirmed against lives in that
# project's own config.yaml (`context.verified_cli_version`), populated by
# /planwise init and refreshed by /planwise upgrade; /planwise doctor reports
# drift between it and the live `claude --version` without ever writing here.
READ_LIMITS_MEASURED_ON = "2026-09-07"

# Feature floor for the Read tool's `allow_large: true` parameter. The Claude
# Code tools reference documents it as available "on Claude Code v2.1.296 or
# later". At or above this build a whole-file read of an over-cap file is one
# call away, so the token page-cap and the byte cap become advisories (Warn)
# rather than hard stops (Critical). The line window keeps Critical: a probe
# could not show it binding at all, so it cannot show `allow_large` lifting it.
# The version is never discovered here: callers pass the consuming project's
# `context.verified_cli_version` (see `read_verified_cli_version`).
ALLOW_LARGE_MIN_CLI = "2.1.296"

_LEVELS = ("Green", "Notice", "Warn", "Critical")
_LEVEL_RANK = {name: i for i, name in enumerate(_LEVELS)}


# ---------------------------------------------------------------------------
# Read-tool classification
# ---------------------------------------------------------------------------
def _count_lines(path: str) -> int:
    """Count newline-delimited lines in a text file (best-effort, binary-safe)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return 0
    if not data:
        return 0
    lines = data.count(b"\n")
    if not data.endswith(b"\n"):
        lines += 1
    return lines


def _max_level(a: str, b: str) -> str:
    return a if _LEVEL_RANK[a] >= _LEVEL_RANK[b] else b


def _cost_level(tokens: int, thresholds: dict | None) -> str:
    """Classify a token estimate against the cost thresholds, if provided."""
    if not thresholds:
        return "Green"
    critical = thresholds.get("critical")
    warn = thresholds.get("warn")
    if critical is not None and tokens >= critical:
        return "Critical"
    if warn is not None and tokens >= warn:
        return "Warn"
    return "Green"


def content_class_for_path(path: str) -> str | None:
    """Return the content class a file's extension identifies, or None.

    Only the structured classes are extension-identifiable: `.ipynb` is
    "notebook" and `.json` / `.jsonl` / `.ndjson` are "json". Every other
    extension returns None so the caller falls back to the conservative
    text ratio rather than guessing prose for a dense markdown index.
    """
    suffix = os.path.splitext(str(path))[1].lower()
    if suffix in NOTEBOOK_SUFFIXES:
        return "notebook"
    if suffix in JSON_SUFFIXES:
        return "json"
    return None


def bytes_per_token(model: str | None = None, content: str | None = None) -> float:
    """Return the bytes-per-token ratio for a model family / content class.

    Gate-conservative by construction: with no content class the model
    family's densest TEXT ratio (FALLBACK_CONTENT_CLASS) is returned. With
    no/unknown model, a named class resolves to its most restrictive cell
    across every family (the heaviest tokenizer), and no class at all to
    the overall most-restrictive text ratio (DEFAULT_BYTES_PER_TOKEN). The
    structured classes (notebook, json) sit below the fallback and are
    reached only by naming them — pass the result of
    `content_class_for_path()` when the file's extension is known.
    """
    family = BYTES_PER_TOKEN.get((model or "").lower())
    if not family:
        cells = [fam[content] for fam in BYTES_PER_TOKEN.values() if content in fam]
        return min(cells) if cells else DEFAULT_BYTES_PER_TOKEN
    if content and content in family:
        return family[content]
    return family[FALLBACK_CONTENT_CLASS]


def estimate_tokens(
    num_bytes: int, model: str | None = None, content: str | None = None
) -> int:
    """Estimate a byte count's token cost as bytes / bytes-per-token, rounded up."""
    if num_bytes <= 0:
        return 0
    return math.ceil(num_bytes / bytes_per_token(model, content))


def _version_parts(version: str) -> tuple[int, ...] | None:
    """Parse a dotted version into integer parts, or None when unparsable."""
    text = (version or "").strip()
    if not text:
        return None
    parts = text.split(".")
    if not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def allow_large_available(version: str) -> bool:
    """True when `version` is at or above ALLOW_LARGE_MIN_CLI.

    Compares dotted integer parts (so "2.1.1000" > "2.1.296"). An empty or
    unparsable value returns False: an unknown build keeps the hard gates.
    """
    have = _version_parts(version)
    if have is None:
        return False
    floor = _version_parts(ALLOW_LARGE_MIN_CLI)
    if floor is None:
        return False
    width = max(len(have), len(floor))
    padded_have = have + (0,) * (width - len(have))
    padded_floor = floor + (0,) * (width - len(floor))
    return padded_have >= padded_floor


_CONTEXT_BLOCK_RE = re.compile(r"context\s*:\s*(#.*)?$")
_CLI_VERSION_KEY_RE = re.compile(r"verified_cli_version\s*:(.*)$")


def _yaml_scalar(raw: str) -> str:
    """The value of a one-line YAML scalar: quotes and a trailing comment removed.

    A value in one pair of matching single or double quotes returns the text
    between them, and anything after the closing quote is ignored. A bare
    value drops a ` # comment` tail. An unterminated quote is read as bare.
    """
    value = raw.strip()
    if value[:1] in ("'", '"'):
        close = value.find(value[0], 1)
        if close != -1:
            return value[1:close].strip()
    return re.split(r"\s#", value, maxsplit=1)[0].strip()


def read_verified_cli_version(config_path) -> str:
    """Read `context.verified_cli_version` from a config.yaml WITHOUT PyYAML.

    Only a direct child of a top-level `context:` block counts. A key of the
    same name under any other block is ignored. The value may be bare or in
    single or double quotes, with or without a trailing ` # comment`. When
    the file holds the key more than once, the last one wins, as in YAML.

    Returns "" (the uncalibrated sentinel) when the key is absent, empty, or
    the file can't be read -- the field predates any config written before
    this key shipped, so absence is expected, not an error. A caller that
    must reject a missing file checks for it before calling. Accepts a str
    or a Path.
    """
    try:
        with open(config_path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return ""
    found = ""
    in_context = False
    child_indent = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        if indent == 0:
            in_context = _CONTEXT_BLOCK_RE.match(line) is not None
            child_indent = None
            continue
        if not in_context:
            continue
        if child_indent is None:
            child_indent = indent
        if indent != child_indent:
            continue
        match = _CLI_VERSION_KEY_RE.match(stripped)
        if match:
            found = _yaml_scalar(match.group(1))
    return found


def config_cli_version(config) -> str:
    """Read `context.verified_cli_version` from an already loaded config dict.

    The dict-reading twin of `read_verified_cli_version`. A caller that holds
    the config `load_config` returned uses this one, so the version comes from
    the config it loaded and never from a second read of the file. Returns ""
    (the uncalibrated sentinel) for a config that is not a dict, a missing or
    non-mapping `context:` block, a missing key, or a null value.
    """
    context = config.get("context") if isinstance(config, dict) else None
    if not isinstance(context, dict):
        return ""
    value = context.get("verified_cli_version")
    return "" if value is None else str(value).strip()


# Read-gate names, as `classify_file` reports them in `read_gates`.
READ_GATE_TOKEN = "token"
READ_GATE_BYTE = "byte"
READ_GATE_LINE = "line"

# The gates a Read with `allow_large: true` lifts. The line window is not
# here: a probe could not show `allow_large` lifting it.
ALLOW_LARGE_LIFTS = frozenset({READ_GATE_TOKEN, READ_GATE_BYTE})


def fired_read_gates(num_bytes: int, tokens: int, line_count: int = 0) -> tuple:
    """The hard Read-tool caps a file crosses, in gate-priority order.

    Draws from "token" (the page cap), "byte" (the whole-read cap) and
    "line" (the line window). A file in a warn band only, or under every
    cap, returns an empty tuple.
    """
    gates = []
    if tokens >= READ_PAGE_CAP_TOKENS:
        gates.append(READ_GATE_TOKEN)
    if num_bytes >= READ_FILE_BYTE_CAP:
        gates.append(READ_GATE_BYTE)
    if line_count >= READ_LINE_CAP:
        gates.append(READ_GATE_LINE)
    return tuple(gates)


def content_read_gates(text: str, num_bytes: int | None = None, model: str | None = None,
                       content: str | None = None) -> tuple:
    """The hard Read-tool caps `text` crosses once written, as `fired_read_gates` reports them.

    For a writer that holds the content but no file yet. `num_bytes` is the
    written byte count (pass it when the file takes CRLF endings); it defaults
    to the UTF-8 length of `text`. Tokens use `estimate_tokens` with `model`
    and `content`, and lines count as `classify_file` counts them on disk.
    """
    if num_bytes is None:
        num_bytes = len(text.encode("utf-8"))
    line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return fired_read_gates(num_bytes, estimate_tokens(num_bytes, model, content), line_count)


def allow_large_lifts(cli_version: str, read_gates) -> bool:
    """True when `allow_large` reads the file whole.

    The version must be at or above ALLOW_LARGE_MIN_CLI, at least one cap
    must have fired, and every fired cap must be one `allow_large` lifts.
    """
    gates = set(read_gates or ())
    return bool(
        allow_large_available(cli_version) and gates and gates <= ALLOW_LARGE_LIFTS
    )


def read_routes_advice(cli_version: str = "", read_gates=None) -> str:
    """One-line advice naming the read routes open to an over-limit file.

    With `read_gates` None the advice follows the version alone: at or above
    ALLOW_LARGE_MIN_CLI it names `allow_large`, `offset`/`limit` pages and
    Grep. With `read_gates` given (the `classify_file` field), it names
    `allow_large` only when `allow_large_lifts` holds, so a file over the
    line window gets pages and Grep only. Below the floor, or with no
    version, it names pages and Grep only. Both forms recommend a split or
    refactor as advice. The text holds no line break, so a writer can print
    it as one warning line.
    """
    if read_gates is None:
        named = allow_large_available(cli_version)
    else:
        named = allow_large_lifts(cli_version, read_gates)
    if named:
        return (
            "Read it whole with `allow_large: true` (Claude Code v"
            f"{ALLOW_LARGE_MIN_CLI} or later), in `offset`/`limit` pages, or "
            "Grep for the section you need. For a core or to-be-edited file, "
            "consider a split or refactor."
        )
    return (
        "Read it in `offset`/`limit` pages, or Grep for the section you need. "
        "For a core or to-be-edited file, consider a split or refactor."
    )


PLAIN_READ_ADVICE = "A plain Read still returns it whole."


def written_read_advice(text: str, cli_version: str = "", num_bytes: int | None = None) -> str:
    """The read-routes line for content a writer wrote over its own budget.

    Measures the content with `content_read_gates`. When no hard Read cap
    fires, a plain Read returns the file whole, and the line says so. When a
    cap fires, it is `read_routes_advice(cli_version, gates)`, which names
    `allow_large` only when that flag lifts every fired cap.
    """
    gates = content_read_gates(text, num_bytes)
    if not gates:
        return PLAIN_READ_ADVICE
    return read_routes_advice(cli_version, gates)


def _read_level(
    num_bytes: int, tokens: int, line_count: int = 0, *, cli_version: str = ""
) -> str:
    """Classify against the three FIXED Read-tool gates (tokens, bytes, lines).

    With `cli_version` at or above ALLOW_LARGE_MIN_CLI, a token page-cap or
    byte-cap crossing classifies Warn, not Critical: `allow_large` reads
    such a file whole. The line window keeps Critical at every version. The
    default (no version) reproduces the hard-gate levels exactly.
    """
    gates = fired_read_gates(num_bytes, tokens, line_count)
    if gates:
        return "Warn" if allow_large_lifts(cli_version, gates) else "Critical"
    if tokens >= READ_TOKEN_WARN or num_bytes >= READ_BYTE_WARN:
        return "Warn"
    return "Green"


def classify_file(
    path: str,
    model: str,
    projected_added_bytes: int = 0,
    thresholds: dict | None = None,
    content: str | None = None,
    *,
    cli_version: str = "",
) -> dict:
    """Classify a file's read/cost risk for a given runner model.

    Folds two independent gates and takes the max severity:
      * cost gate  — token estimate vs the (optional) cost `thresholds` dict.
      * read gate  — the three FIXED mechanical Read-tool limits, in priority
                     order: token page-cap (bytes / the model's bytes-per-token
                     ratio), byte cap, and the defensive line window.

    The token estimate includes `projected_added_bytes` so a currently-safe
    file that an edit will push past a gate is flagged pre-emptively
    (estimate the delta as added lines x that file's observed bytes/line).

    `cli_version` is the consuming project's verified Claude Code build
    (`read_verified_cli_version`); the classifier never discovers it. At or
    above ALLOW_LARGE_MIN_CLI a token page-cap or byte-cap crossing is Warn,
    because a Read with `allow_large: true` returns the file whole. Below
    the floor, or with no version, those crossings stay Critical. The line
    window stays Critical at every version. A `read`-reason level is NOT
    resolvable by the 1M context exception: every model shares the same
    mechanical caps, and the Claude 5 family tokenizer trips the token gate
    on FEWER bytes. The `read_gates` field names the hard caps the file
    crosses (`fired_read_gates`, projected bytes included). The `advice`
    field names the routes that remain: `read_routes_advice(cli_version,
    read_gates)` when the read gate is Warn or Critical, else "". It names
    `allow_large` only when every fired cap is one `allow_large` lifts.

    When `content` is None the class is auto-detected from the extension
    (`content_class_for_path`): a `.ipynb` prices at the notebook ratio and a
    `.json` at the json ratio, both denser than the text fallback. An explicit
    `content` always wins.

    Returns {"level", "reason", "bytes", "tokens", "lines", "content",
    "advice", "read_gates"} where level is in Green|Notice|Warn|Critical,
    reason is "cost"|"read" naming the driver, content is the class the
    estimate used (None = fallback), advice is the read-routes text or "",
    and read_gates is a tuple drawn from "token", "byte" and "line" (empty
    when no hard cap is crossed).
    """
    if content is None:
        content = content_class_for_path(path)
    try:
        num_bytes = os.path.getsize(path)
    except OSError:
        num_bytes = 0
    line_count = _count_lines(path)
    gated_bytes = num_bytes + max(0, projected_added_bytes)
    tokens = estimate_tokens(gated_bytes, model, content)

    cost = _cost_level(tokens, thresholds)
    read = _read_level(gated_bytes, tokens, line_count, cli_version=cli_version)
    gates = fired_read_gates(gated_bytes, tokens, line_count)

    level = _max_level(cost, read)
    # reason names whichever gate drove the final level; ties go to read because
    # a mechanical read failure is the more actionable (un-resolvable-by-1M)
    # signal.
    if _LEVEL_RANK[read] >= _LEVEL_RANK[cost] and read != "Green":
        reason = "read"
    elif cost != "Green":
        reason = "cost"
    else:
        reason = "read"

    return {
        "level": level,
        "reason": reason,
        "bytes": num_bytes,
        "tokens": tokens,
        "lines": line_count,
        "content": content,
        "advice": (
            read_routes_advice(cli_version, gates) if read in ("Warn", "Critical") else ""
        ),
        "read_gates": gates,
    }
