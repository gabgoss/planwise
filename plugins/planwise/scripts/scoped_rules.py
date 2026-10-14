#!/usr/bin/env python3
"""Scoped-rule check for one backlog item: which path-scoped rules govern its edits.

A rule under `.claude/rules/` that declares a frontmatter `paths:` key loads
only when the working agent touches a matching file. An unattended fixer that
never opens such a file before editing never sees the rule. This module
computes, for one item, which destinations the item will touch and which
path-scoped rules match them, so the caller can inject those rules up front.

The item's destinations come from its `## Files Touched` table when it has
one, else from the backtick-quoted paths in its body. Each destination is
matched against every rule's globs, and the item gets one of three verdicts:

- `none`: no path-scoped rule matches any destination.
- `inject`: behaviour rules match; paste or list them in the fixer's prompt.
- `placement`: the item creates a file under a `placement: true` rule, or
  under a content tree (`.claude/rules|agents|skills|commands/`), and no
  promoted lesson owns the item, so a human decides where the file belongs.

This is a library with no CLI. It reads files and never writes them. The
backlog router imports this module, and this module imports nothing from the
router; the fence toggle the router also uses is re-implemented here for
that reason.
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from markdown_parser import normalize_id, split_row_cells_code_aware

CONTENT_TREES = (".claude/rules/", ".claude/agents/", ".claude/skills/", ".claude/commands/")
LOOP_WRITTEN_HEADINGS: tuple[str, ...] = ("Loop Decision Needed",)
VERDICT_NONE = "none"
VERDICT_INJECT = "inject"
VERDICT_PLACEMENT = "placement"
MAX_DESTINATIONS = 50
# A prompt-size budget chosen by design, not a measured threshold: a matched
# rule set at or under this many bytes is pasted whole, a larger one is passed
# as paths the fixer reads before its first edit.
INJECT_CONTENT_MAX_BYTES = 8192

ROLES = ("READ", "EDIT", "CREATE")
_SPAN_RE = re.compile(r"`([^`\n]+)`")
_FILES_TOUCHED_RE = re.compile(r"^##\s+Files Touched\s*$")
_LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")
_WIN_ABS_RE = re.compile(r"^[A-Za-z]:/")
_FORBIDDEN_SPAN_CHARS = set("*{}$<>|()")
_TRAILING_PUNCT = ".,;:)"


@dataclass(frozen=True)
class RuleScope:
    """One path-scoped rule: its file, its raw `paths:` entries and their regexes."""

    path: Path
    rel: str
    patterns: tuple[str, ...]
    regexes: tuple[re.Pattern, ...]
    placement: bool
    description: str

    def matches(self, rel_path: str) -> bool:
        """True when any of the rule's globs matches the project-relative path."""
        return any(rx.match(rel_path) for rx in self.regexes)


@dataclass
class Destination:
    """One file the item will read, edit or create, with its classification."""

    path: str
    role: str
    exists: bool
    source: str
    rules: list[str] = field(default_factory=list)
    placement_rules: list[str] = field(default_factory=list)
    content_tree: bool = False
    verdict: str = VERDICT_NONE


def _unquote(text: str) -> str:
    """Strip one pair of quotes that encloses the whole text, else return it stripped."""
    s = text.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'" and s[0] not in s[1:-1]:
        return s[1:-1].strip()
    return s


def _strip_comment(line: str) -> str:
    """Cut a YAML ` #` comment that sits outside quotes; quoted text is kept whole."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def _split_top_level(text: str) -> list[str]:
    """Split on commas that sit outside braces and outside quotes."""
    parts: list[str] = []
    depth = 0
    quote = ""
    cur: list[str] = []
    for ch in text:
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def split_paths_value(value: str) -> list[str]:
    """Split a frontmatter `paths:` value into its glob entries.

    Handles the documented forms: an unquoted or quoted single pattern, a
    comma-separated list, brace expansion (`"**/*.{py,md}"` stays one entry
    because commas inside braces do not split), and a YAML array of any item
    count. `parse_frontmatter_map` hands an array over as one value with its
    `- ` lines appended, so a value with any line starting with `-` is read
    one entry per `- ` line. Quotes are stripped only when they enclose a
    whole entry, and a ` #` comment is cut only outside quotes.
    """
    lines = [_strip_comment(ln).strip() for ln in value.split("\n")]
    entries: list[str] = []
    if any(ln.startswith("-") for ln in lines):
        for ln in lines:
            if ln.startswith("-"):
                entries.append(_unquote(ln[1:]))
        return [e for e in entries if e]
    text = " ".join(ln for ln in lines if ln)
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    for part in _split_top_level(text):
        # A whole quoted list ("src/**, Docs/**") unquotes to a list: split again.
        for sub in _split_top_level(_unquote(part)):
            sub = _unquote(sub)
            if sub:
                entries.append(sub)
    return entries


def expand_braces(pattern: str) -> list[str]:
    """Expand every `{a,b}` group in a glob into its alternatives.

    `"{src,Docs}/**/*.{py,md}"` yields four patterns. Nested groups expand by
    recursion. A pattern with no braces, or with an unmatched brace, returns
    a one-item list holding the pattern itself.
    """
    start = pattern.find("{")
    if start == -1:
        return [pattern]
    depth = 0
    for end in range(start, len(pattern)):
        if pattern[end] == "{":
            depth += 1
        elif pattern[end] == "}":
            depth -= 1
            if depth == 0:
                break
    else:
        return [pattern]
    prefix, inner, suffix = pattern[:start], pattern[start + 1:end], pattern[end + 1:]
    out: list[str] = []
    for alt in _split_top_level(inner):
        out.extend(expand_braces(prefix + alt + suffix))
    return out


def _translate(alt: str) -> str:
    """Translate one brace-free glob alternative into a regex fragment."""
    if not any(ch in alt for ch in "*?"):
        literal = alt.rstrip("/")
        return re.escape(literal) + "(?:/.*)?"
    out: list[str] = []
    i = 0
    while i < len(alt):
        if alt.startswith("**/", i) and (i == 0 or alt[i - 1] == "/"):
            out.append("(?:.*/)?")
            i += 3
        elif alt.startswith("**", i):
            out.append(".*")
            i += 2
        elif alt[i] == "*":
            out.append(".*")
            i += 1
        elif alt[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(alt[i]))
            i += 1
    return "".join(out)


def glob_to_regex(pattern: str) -> re.Pattern:
    """Compile a `paths:` glob into a regex anchored on a project-relative posix path.

    Braces expand first. A `**/` at the start or after a `/` matches zero or
    more directories, so `**/*.md` matches a root-level `README.md` exactly as
    `*.md` does. Any other `**`, and `*`, cross `/` (the measured Claude Code
    semantics). `?` matches one character other than `/`. A pattern with no
    wildcard matches the exact path or anything below it as a directory
    (`Docs` matches `Docs/a.md`), and `src/**` matches below `src` but not
    `src` itself. A leading `./` is stripped.
    """
    pattern = pattern.strip()
    while pattern.startswith("./"):
        pattern = pattern[2:]
    alts = [_translate(alt) for alt in expand_braces(pattern)]
    return re.compile("^(?:" + "|".join(alts) + ")$")


def load_rule_scopes(project_root: Path) -> list[RuleScope]:
    """Load every path-scoped rule under `project_root/.claude/rules/`, sorted by path.

    Each `*.md` file is read in text mode, so a CRLF checkout parses. Only the
    frontmatter counts: a file with no frontmatter or no `paths:` key is a
    global rule, which loads anyway, and is neither returned nor counted; a
    `paths:` line inside a fenced example in the body never makes a scope.
    `placement` is true only when the frontmatter value, unquoted and
    lower-cased, is `true`.
    """
    project_root = Path(project_root)
    rules_dir = project_root / ".claude" / "rules"
    if not rules_dir.is_dir():
        return []
    scopes: list[RuleScope] = []
    for path in sorted(rules_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        split = split_frontmatter_block(text)
        if split is None:
            continue
        fm = parse_frontmatter_map(split[0])
        if not fm or "paths" not in fm:
            continue
        patterns = tuple(split_paths_value(fm["paths"]))
        if not patterns:
            continue
        scopes.append(RuleScope(
            path=path,
            rel=path.relative_to(project_root).as_posix(),
            patterns=patterns,
            regexes=tuple(glob_to_regex(p) for p in patterns),
            placement=_unquote(_strip_comment(fm.get("placement", ""))).lower() == "true",
            description=_unquote(_strip_comment(fm.get("description", ""))),
        ))
    return scopes


def _blank_fenced_blocks(body: str) -> str:
    """Blank every fenced block's lines, keeping line positions (local fence toggle)."""
    out: list[str] = []
    in_fence = False
    for line in body.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def strip_loop_sections(body: str) -> tuple[str, int]:
    """Remove every loop-written section from an item body; return it and the lines removed.

    A section opens at a line equal to `## {heading}` for a heading in
    `LOOP_WRITTEN_HEADINGS`, outside any fence, and runs to the next `## `
    line outside a fence, or to the end of the body. Fenced text inside the
    section goes with it. A loop heading quoted inside a fenced example never
    opens a section, so the text the loop wrote cannot feed any signal.
    """
    loop_lines = {f"## {h}" for h in LOOP_WRITTEN_HEADINGS}
    out: list[str] = []
    removed = 0
    in_fence = False
    skipping = False
    segments = body.split("\n")
    for idx, line in enumerate(segments):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            skipping = line.strip() in loop_lines
        if skipping:
            # The empty segment after a final newline is not a line of the section.
            if not (idx == len(segments) - 1 and line == "" and idx > 0):
                removed += 1
        else:
            out.append(line)
    return "\n".join(out), removed


def _normalize_path(raw: str, project_root: Path) -> str | None:
    """Return a project-relative posix path, or None for an absolute path outside the root."""
    p = raw.strip()
    if _WIN_ABS_RE.match(p) or p.startswith("/"):
        roots = {project_root.as_posix().rstrip("/")}
        try:
            roots.add(project_root.resolve().as_posix().rstrip("/"))
        except OSError:
            pass
        # A drive-letter path compares case-insensitively, as Windows does.
        fold = _WIN_ABS_RE.match(p) is not None
        for root in sorted(roots):
            want = root + "/"
            head = p[:len(want)]
            same = head.lower() == want.lower() if fold else head == want
            if same:
                p = p[len(want):]
                break
        else:
            return None
    while p.startswith("./"):
        p = p[2:]
    return p or None


def _table_destinations(text: str, project_root: Path) -> list[Destination]:
    """Read `| path | ROLE | ...` rows under a `## Files Touched` heading."""
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if _FILES_TOUCHED_RE.match(ln.strip())), None)
    if start is None:
        return []
    out: list[Destination] = []
    seen: set[str] = set()
    for line in lines[start + 1:]:
        if line.startswith(("## ", "# ")):
            break
        if not line.strip().startswith("|"):
            continue
        # Code-aware: a pipe inside a backticked path or note never shifts the columns.
        cells = split_row_cells_code_aware(line)
        if len(cells) < 2:
            continue
        role = cells[1].strip("`* ").upper()
        if role not in ROLES:
            continue
        path = _normalize_path(cells[0].strip("` "), project_root)
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(Destination(path=path, role=role,
                               exists=(project_root / path).exists(), source="files-touched"))
    return out


def _body_candidate(span: str, project_root: Path) -> str | None:
    """Apply the body token filters to one backtick span; return the path or None."""
    if "/" not in span or any(ch.isspace() for ch in span):
        return None
    if any(ch in _FORBIDDEN_SPAN_CHARS for ch in span):
        return None
    if span.startswith(("http", "-", "~")):
        return None
    token = span.rstrip(_TRAILING_PUNCT)
    token = _LINE_SUFFIX_RE.sub("", token).rstrip(_TRAILING_PUNCT)
    if "." not in token.rsplit("/", 1)[-1]:
        return None
    return _normalize_path(token, project_root)


def extract_destinations(body: str, project_root: Path) -> tuple[list[Destination], str, bool]:
    """Take an item's destinations from its `## Files Touched` table, else from its body.

    Returns `(destinations, source, truncated)`. Loop-written sections are
    stripped and fenced blocks blanked first. A table row is `| path | ROLE |`
    with ROLE one of READ, EDIT, CREATE; source `files-touched`. An empty or
    absent table falls through to the body: every backtick span that looks
    like a file path (has a `/`, no whitespace, no glob or shell characters,
    not a URL or flag, a dot in its last segment after a `:NNN` suffix is cut)
    becomes a destination, `EDIT` when it exists under `project_root`, else
    `CREATE`; source `body`. Absolute paths under the root are relativized and
    others dropped. At most `MAX_DESTINATIONS` body paths are kept, and
    `truncated` says the cap cut the list. Nothing found: `([], "none", False)`.
    """
    project_root = Path(project_root)
    stripped, _ = strip_loop_sections(body)
    text = _blank_fenced_blocks(stripped)
    table = _table_destinations(text, project_root)
    if table:
        return table, "files-touched", False
    seen: list[str] = []
    for span in _SPAN_RE.findall(text):
        path = _body_candidate(span, project_root)
        if path and path not in seen:
            seen.append(path)
    if not seen:
        return [], "none", False
    truncated = len(seen) > MAX_DESTINATIONS
    out = []
    for path in seen[:MAX_DESTINATIONS]:
        exists = (project_root / path).exists()
        out.append(Destination(path=path, role="EDIT" if exists else "CREATE",
                               exists=exists, source="body"))
    return out, "body", truncated


def _list_tokens(value: str) -> list[str]:
    """Split a flow or block list value (`[a, b]`, `a, b`, `- a`) into unquoted tokens."""
    tokens: list[str] = []
    for line in value.split("\n"):
        line = _strip_comment(line).strip().lstrip("-").strip().strip("[]")
        tokens.extend(_unquote(t) for t in _split_top_level(line))
    return [t for t in tokens if t]


def owning_lessons(item_id: str, lessons_dir: Path | None) -> list[str] | None:
    """Return the stems of promoted lessons that own the item, or None without a lessons dir.

    A lesson file (`LL-*.md` under `lessons_dir` or `lessons_dir/Archive`)
    owns the item when its frontmatter `promoted-to:` names the item id
    (each token compared through `normalize_id`, so a prefixed and a bare id
    agree) and its `promotion-target:` lists `rule`. An owned item's
    creations were already decided by the promotion, so they never need a
    placement decision.
    """
    if lessons_dir is None:
        return None
    lessons_dir = Path(lessons_dir)
    want = normalize_id(item_id)
    stems: list[str] = []
    for folder in (lessons_dir, lessons_dir / "Archive"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("LL-*.md")):
            try:
                split = split_frontmatter_block(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            fm = parse_frontmatter_map(split[0]) if split else None
            if not fm:
                continue
            ids = {normalize_id(t) for t in _list_tokens(fm.get("promoted-to", ""))}
            targets = {t.lower() for t in _list_tokens(fm.get("promotion-target", ""))}
            if want in ids and "rule" in targets:
                stems.append(path.stem)
    return stems


def classify(destinations: list[Destination], rules: list[RuleScope], owned: bool) -> str:
    """Classify each destination in place and return the item's overall verdict.

    For an `EDIT` or `CREATE` destination, `rules` lists every matching rule,
    `placement_rules` those declaring `placement: true`, and `content_tree`
    says the path sits under a content tree. Its verdict is `placement` for a
    `CREATE` that is not owned and matches a placement rule or sits in a
    content tree, else `inject` when any rule matches, else `none`. A `READ`
    row is always `none` with empty rule lists. The item verdict is the
    strongest destination verdict: `placement`, then `inject`, then `none`.
    """
    verdicts: set[str] = set()
    for dest in destinations:
        dest.content_tree = dest.path.startswith(CONTENT_TREES)
        if dest.role not in ("EDIT", "CREATE"):
            dest.rules, dest.placement_rules, dest.verdict = [], [], VERDICT_NONE
            continue
        matched = [r for r in rules if r.matches(dest.path)]
        dest.rules = [r.rel for r in matched]
        dest.placement_rules = [r.rel for r in matched if r.placement]
        if dest.role == "CREATE" and not owned and (dest.placement_rules or dest.content_tree):
            dest.verdict = VERDICT_PLACEMENT
        elif dest.rules:
            dest.verdict = VERDICT_INJECT
        else:
            dest.verdict = VERDICT_NONE
        verdicts.add(dest.verdict)
    for verdict in (VERDICT_PLACEMENT, VERDICT_INJECT):
        if verdict in verdicts:
            return verdict
    return VERDICT_NONE


def scoped_rules_block(item_id: str, body: str, config: dict) -> dict[str, Any]:
    """Compute the scoped-rule block for one item: the single entry point.

    Reads `config["_project_root"]` and `config.get("_lessons_dir")`, loads
    the rules once, extracts and classifies the destinations, and returns a
    dict with `verdict`, `source`, `rules_scanned` (the number of path-scoped
    rules; global rules are not counted), `owning_lessons`, `destinations`
    (one dict per destination), `rules_to_inject` (sorted rel paths of every
    matched rule), `rules_bytes` (their total size on disk), `inject_form`
    (`content` at or under `INJECT_CONTENT_MAX_BYTES`, else `paths`, and
    `none` with no rule to inject) and `truncated`.
    """
    project_root = Path(config["_project_root"])
    lessons_dir = config.get("_lessons_dir")
    scopes = load_rule_scopes(project_root)
    destinations, source, truncated = extract_destinations(body, project_root)
    lessons = owning_lessons(item_id, Path(lessons_dir) if lessons_dir else None) or []
    verdict = classify(destinations, scopes, bool(lessons))
    by_rel = {s.rel: s for s in scopes}
    rules_to_inject = sorted({rel for d in destinations for rel in d.rules})
    rules_bytes = sum(by_rel[rel].path.stat().st_size for rel in rules_to_inject)
    if not rules_to_inject:
        inject_form = "none"
    elif rules_bytes <= INJECT_CONTENT_MAX_BYTES:
        inject_form = "content"
    else:
        inject_form = "paths"
    return {
        "verdict": verdict,
        "source": source,
        "rules_scanned": len(scopes),
        "owning_lessons": lessons,
        "destinations": [asdict(d) for d in destinations],
        "rules_to_inject": rules_to_inject,
        "rules_bytes": rules_bytes,
        "inject_form": inject_form,
        "truncated": truncated,
    }
