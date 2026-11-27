"""The derived blocks of the Token Saver write-back.

`token_saver_writeback` prices each Required Context row and writes the task
files. This module derives what depends on those rows:

- the Orchestration's task list and its `## Session Surface` block
- the Sprint Plan's session figures and its `## Write-Set` sizes
- the Master Plan's `### Write-Sets` sizes and total

`scaffold_plan`, `estimate_reconcile` and `lint_gate_checks_layers` call the
same functions, so a rendered figure, a written one and a checked one agree.

This module imports `token_saver_writeback` at the top. The write-back imports
this one only inside the functions that run it, so neither import is circular.
"""

import os
import re
import sys
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

import token_saver_writeback as writeback  # for the one settle-pass limit, read at each use
from read_limits import bytes_per_token
from token_saver_scan import (
    _clean_file_cell,
    content_class_for,
    is_command_corpus,
    parse_agent,
    resolve_context_path,
    substitute_roots,
    unresolved_reason,
)
from token_saver_writeback import (
    _K_TERM_RE,
    _NUM,
    _TOKEN_HEADERS,
    _Buffers,
    _cells,
    _col,
    _FileCache,
    _fmt_k,
    _fmt_k_exact,
    _fmt_kib,
    _parse_token_cell,
    _required_context_table,
    _reroll_breakdown,
    _rewrite_cell,
    _same_file,
    _set_cell,
    _split_eol,
    _table_header_at,
    _table_rows,
    _task_id,
    _text_bytes,
    price_row,
)


def _one_file(folder: Path, pattern: str, report: dict, what: str,
              found: list[Path] | None = None) -> Path | None:
    """The one file that `pattern`, or the caller's own list `found`, names, else a report entry."""
    found = sorted(folder.glob(pattern)) if found is None else found
    if len(found) != 1:
        report["unreadable"].append({"file": str(folder), "what": what,
                                     "reason": f"{len(found)} files match {pattern}"})
        return None
    return found[0]


def _token_tables(lines: list[str], start: int = 0,
                  stop: int | None = None) -> list[tuple[int, int, list[int], list[str]]]:
    """Tables with a token column in lines[start:stop]: (header, token col, rows, header)."""
    out = []
    for i in range(start, len(lines) if stop is None else stop):
        header = _table_header_at(lines, i)
        if header is None or (i > 0 and _split_eol(lines[i - 1])[0].strip().startswith("|")):
            continue
        tok = _col(header, _TOKEN_HEADERS)
        if tok is not None:
            out.append((i, tok, _table_rows(lines, i), header))
    return out


def _section_bounds(lines: list[str], title: str) -> tuple[int, int] | None:
    """(start, stop) line indices of the `## {title}` section, or None."""
    for i, line in enumerate(lines):
        if re.match(rf"^##\s+{title}\b", line):
            stop = next((j for j in range(i + 1, len(lines))
                         if re.match(r"^##?\s", lines[j])), len(lines))
            return i, stop
    return None


def _guard(buf: _Buffers, report: dict, path: Path):
    """Snapshot `path`. The returned `fail` restores it whole and reports why."""
    lines = buf.get(path)
    saved, n_changes = list(lines), len(report["changes"])

    def fail(what: str, reason: str) -> None:
        lines[:] = saved
        del report["changes"][n_changes:]
        report["unreadable"].append({"file": str(path), "what": what, "reason": reason})

    return lines, fail


def _write_orchestration(buf: _Buffers, report: dict, orch: Path,
                         task_totals: list[tuple[str, str, str]]) -> str | None:
    """Re-roll the Session Task List; any failure leaves the file as authored."""
    lines, fail = _guard(buf, report, orch)
    bounds = _section_bounds(lines, "Session Task List") or (0, len(lines))
    return _reroll_task_table(buf, report, orch, bounds, task_totals, fail,
                              "Session Task List", total_required=True)


PLAN_TIME_FLAG = "(plan-time estimate)"
_ROLE_RANK = {"READ": 0, "EDIT": 1, "CREATE": 2}
_SURFACE_COLUMNS = ["path", "role", "kib", "~tokens", "cited by"]
_SURFACE_LABEL = "**Session surface:**"
# A trailing `:line`, `:line-line` or parenthetical, spaced or glued to the name. A drive colon is not
# a qualifier, and neither is text that fills a whole path component, as `(shop)` in `app/(shop)`.
_QUALIFIER_RE = re.compile(
    r"(?:(?<!^[A-Za-z])(?<=[^/]):\d+(?:[-–]\d+)?|(?:(?<=\S)\s+|(?<=[^/\s]))\([^()]*\))$")
_ORCHESTRATION_GLOB = "*-Orchestration.md"
# A session id ends in its session number. A task's file name holds its number and agent before the name.
_ORCHESTRATION_RE = re.compile(r"-S\d+-\d+-Orchestration\.md$")


def _counted_role(cell: str) -> str:
    """The role the session surface reads from a `Role` cell: its first word, else `READ`."""
    first = (cell.split() or ["READ"])[0]
    return first if first in _ROLE_RANK else "READ"


def unknown_roles(lines: list[str]):
    """(row number, line index, cell, role read) per Required Context row whose `Role` cell holds no role.

    A cell holds a role when it is `READ`, `EDIT` or `CREATE`, alone or followed
    by the plan-time flag. A table with no `Role` column yields nothing, and so
    does a row whose cell count differs from the header.
    """
    table = _required_context_table(lines)
    if table is None:
        return
    header_idx, header = table
    at = _col(header, ("role",))
    if at is None:
        return
    for n, row_idx in enumerate(_table_rows(lines, header_idx), start=1):
        cells = _cells(_split_eol(lines[row_idx])[0], len(header))
        if len(cells) != len(header):
            continue
        cell = cells[at].strip()
        if " ".join(cell.split()).removesuffix(f" {PLAN_TIME_FLAG}") not in _ROLE_RANK:
            yield n, row_idx, cell, _counted_role(cell)


def _surface_number(text: str, path: Path) -> int | None:
    """The task number: the Task ID's trailing digits, else the file name's."""
    m = (re.search(r"-(\d+)$", _task_id(text.split("\n"), path))
         or re.search(r"-(\d+)-[A-Za-z]+-[^-]+$", path.stem))
    return int(m.group(1)) if m else None


def _folder_text(folder: Path) -> str:
    """A session folder as a plan-relative path: its sprint folder and its own name."""
    return f"{folder.parent.name}/{folder.name}"


def plain_path(text: str) -> str:
    """`text` with forward slashes, no leading `./` and no trailing slash."""
    return re.sub(r"^(?:\./+)+", "", text.replace("\\", "/")).rstrip("/")


def root_path(text: str, root: Path) -> str:
    """`text` with its root placeholders expanded, as a path from `root` when it is below it, on disk or not."""
    text = plain_path(substitute_roots(text, root.resolve()))
    if text:
        try:
            return (root / text).resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):  # outside the project root, or no valid path: the text is the key
            pass
    return text


def _surface_key(cell: str, task_path: Path, own: dict[str, Path], plan_root: Path,
                 project_root: Path) -> str | None:
    """The one key of the file a Required Context cell names, or None when it names no path.

    `own` maps each plan file's bare name to its session folder. Those files
    are keyed by bare name. Any other file that resolves is keyed by its path
    from the project root, and one that does not by its cleaned text. A
    trailing qualifier drops only when the path resolves without it and not with it.
    A path below the session's own `Outputs/` that does not resolve is cut to start at the sprint folder.
    """
    key, known = _file_key(cell, task_path, own, plan_root, project_root)
    if key is None or known:
        return key
    at = f"/{key}".find(f"/{_folder_text(task_path.parent)}/Outputs/")
    return key[at:] if at >= 0 else key


def _file_key(cell: str, task_path: Path, own: dict[str, Path], plan_root: Path,
              project_root: Path) -> tuple[str | None, bool]:
    """(the key of `_surface_key` before any cut, whether the cell names a known file)."""
    text = plain_path(_clean_file_cell(cell))
    if not text or is_command_corpus(cell):
        return None, False
    bare = text
    while True:
        key = _known_key(bare, task_path, own, plan_root, project_root)
        if key is not None:
            return key, True
        m = _QUALIFIER_RE.search(bare)
        if m is None:
            break
        bare = bare[:m.start()].rstrip("/")
    if text.startswith("Outputs/"):
        text = f"{_folder_text(task_path.parent)}/{text}"
    if unresolved_reason(text, project_root).startswith("not a path"):
        return None, False
    return text, False


def _known_key(text: str, task_path: Path, own: dict[str, Path], plan_root: Path,
               project_root: Path) -> str | None:
    """The key of a path that names a plan file or resolves, else None."""
    if text in own:
        return text
    base, _, name = text.rpartition("/")
    if name in own and f"/{base}".endswith(f"/{_folder_text(own[name])}"):
        return name
    if text.startswith("Outputs/"):
        # An Outputs/ path reads from the session folder, so no other root is tried.
        found = task_path.parent / text
        resolved = found if found.is_file() else None
        text = f"{_folder_text(task_path.parent)}/{text}"
    else:
        resolved = resolve_context_path(text, task_path, plan_root, project_root)
    if resolved is not None:
        full = resolved.resolve()
        if full.name in own and full.parent == own[full.name].resolve():
            return full.name
        try:
            return full.relative_to(project_root.resolve()).as_posix()
        except ValueError:  # outside the project root: the text is the key
            return text
    return None


def surface_entries(tasks: list[tuple[Path, str]], plan_files: list[tuple],
                    plan_root: Path, project_root: Path) -> list[dict]:
    """One entry per file that the task texts name, in the block's row order.

    `tasks` holds (task file path, its text). The path supplies the name and
    the session folder, and need not exist. `plan_files` holds (bare name, KiB
    cell, ~Tokens cell) of the Orchestration and Recovery files, with None
    cells for no figure. An entry is {"path", "role", "kib", "tokens", "by"}.
    `tokens` is None when no row carries a figure. A path takes the highest
    figure any citing row carries, and the KiB cell of that row.
    """
    numbered = sorted(((_surface_number(text, path), path, text) for path, text in tasks),
                      key=lambda t: (t[0] is None, t[0] or 0, t[1].name))
    own = {path.name: path.parent for _, path, _ in numbered}
    if numbered:
        own.update((row[0], numbered[0][1].parent) for row in plan_files)
    entries: dict[str, dict] = {}

    def add(key: str, kib: str | None = None, tokens: str | None = None,
            role: str = "READ", by: str | None = None) -> None:
        entry = entries.setdefault(key, {"path": key, "role": "READ", "kib": "0.0",
                                         "tokens": None, "by": []})
        if by is not None and by not in entry["by"]:
            entry["by"].append(by)
        if _ROLE_RANK.get(role, 0) > _ROLE_RANK[entry["role"]]:
            entry["role"] = role
        value = _parse_token_cell(tokens) if tokens is not None else None
        if value is not None and (entry["tokens"] is None or value > entry["tokens"]):
            entry["tokens"], entry["kib"] = value, (kib or "").strip() or "0.0"

    for name, kib, tokens in plan_files:
        add(name, kib, tokens, by="orchestrator")
    for _, path, _ in numbered:
        add(path.name)
    fixed = len(entries)
    for number, path, text in numbered:
        label = f"{number:02d}" if number is not None else path.stem
        lines = text.split("\n")
        table = _required_context_table(lines)
        if table is None:
            continue
        header_idx, header = table
        file_idx = next((i for i, c in enumerate(header) if c.startswith("file")), None)
        if file_idx is None:
            continue
        columns = [_col(header, ("kib",)), _col(header, _TOKEN_HEADERS), _col(header, ("role",))]
        for row_idx in _table_rows(lines, header_idx):
            cells = _cells(_split_eol(lines[row_idx])[0], len(header))
            if file_idx >= len(cells):
                continue
            key = _surface_key(cells[file_idx], path, own, plan_root, project_root)
            if key is None:
                continue
            whole = len(cells) == len(header)  # a shifted row names its path and no figure
            kib, tokens, role = (cells[i] if whole and i is not None else None for i in columns)
            add(key, kib, tokens, _counted_role(role or ""), label)
    out = list(entries.values())
    return out[:fixed] + sorted(out[fixed:], key=lambda e: e["path"])


def surface_row(entry: dict) -> str:
    """One table row of the block."""
    flagged = entry["role"] == "CREATE" or entry["tokens"] is None
    role = f"{entry['role']} {PLAN_TIME_FLAG}" if flagged else entry["role"]
    path = entry["path"].replace("|", "\\|")
    return (f"| `{path}` | {role} | {entry['kib']} | {_fmt_k(entry['tokens'] or 0)} "
            f"| {', '.join(entry['by']) or 'none'} |")


def surface_total(entries: list[dict]) -> str:
    """The block's total line: the sum of the printed `~Tokens` cells, and the row count."""
    total = sum((_parse_token_cell(_fmt_k(e["tokens"] or 0)) for e in entries), Decimal(0))
    return (f"{_SURFACE_LABEL} {_fmt_k(total)} tokens over {len(entries)} files "
            "(information only)")


def role_spellings(key: str, root: Path) -> list[str]:
    """`key`, then each shorter spelling without a trailing qualifier, up to one that exists."""
    spellings = [key]
    while not os.path.exists(root / spellings[-1]):
        m = _QUALIFIER_RE.search(spellings[-1])
        bare = spellings[-1][:m.start()].rstrip("/") if m else ""
        if not bare:
            break
        spellings.append(bare)
    return spellings


def _write_set_keys(rows: list[tuple], named: dict, own: dict[str, Path], plan_root: Path,
                    project_root: Path) -> list[tuple[str, list[str]]]:
    """(the one key of the file, its known Task IDs) per Write-Set row of (path cell, task cell)."""
    out = []
    for cell, task_cell in rows:
        ids = list(dict.fromkeys(i for i in re.findall(r"[A-Za-z0-9][\w-]*", task_cell) if i in named))
        at = named[ids[0]][0] if ids else plan_root / "row"
        key = _file_key(cell, at, own, plan_root, project_root)[0] or _clean_file_cell(cell)
        if key == "Outputs":
            key = f"{_folder_text(at.parent)}/{key}"
        out.append((_identity(key, own, project_root), ids))
    return out


def _identity(key: str, own: dict[str, Path], project_root: Path) -> str:
    """The comparison key of a file key: its path from the project root, on disk or not, without a qualifier.

    A key that starts at a session folder of `own` reads from that folder.
    """
    if key in own:
        return key
    for folder in dict.fromkeys(own.values()):
        if f"{key}/".startswith(f"{_folder_text(folder)}/Outputs/"):
            key = (folder.resolve().parent.parent / key).as_posix()
            break
    return role_spellings(root_path(key, project_root), project_root)[-1]


def joined_outputs(keys: list[str], own: dict[str, Path]) -> dict[str, str]:
    """{key: the key to compare} for each session output that `keys` spell both in full and from its sprint folder.

    Before a plan is on disk its folder is unknown, so the short spelling joins
    any full one. Two full spellings join only through a short one.
    """
    tails = {f"{_folder_text(folder)}/Outputs/" for folder in own.values()}
    out = {}
    for short in {k for k in keys if any(f"{k}/".startswith(t) for t in tails)}:
        full = {k for k in keys if k.endswith(f"/{short}")}
        target = next(iter(full)) if len(full) == 1 else short
        out.update(dict.fromkeys([short, *full], target))
    return out


def writeset_figures(rows: list[tuple[str, str]], tasks: list[tuple[Path, str]],
                     shares: dict[str, Decimal | None], plan_root: Path, project_root: Path,
                     cache: _FileCache | None = None, size_of=None) -> list[tuple]:
    """(KiB cell, ~Tokens cell, source) per Write-Set row; the first source found wins.

    `rows` holds (path cell, task cell), `tasks` every task file of the sprint
    with its text, and `shares` each Task ID's output tokens. The sources:
    "cited" is the highest Required Context figure for the path, "measured" the
    file's own price for the costliest Agent of its tasks, and "share" the
    output tokens of a task split over its rows that reach this step. A row
    with none of the three gets (None, None, None). Rows that name one file
    get one figure. A row that names no path gets (None, None, "no path") and
    takes no share. `size_of` gives the present size of the file that holds the rows.
    """
    cache = cache if cache is not None else _FileCache()
    named = {_task_id(text.split("\n"), path): (path, parse_agent(text)) for path, text in tasks}
    own = {path.name: path.parent for path, _ in tasks}
    cited: dict[str, tuple[str, Decimal]] = {}
    for entry in surface_entries(tasks, [], plan_root, project_root):
        key = _identity(entry["path"], own, project_root)
        if entry["tokens"] is not None and (key not in cited or entry["tokens"] > cited[key][1]):
            cited[key] = (entry["kib"], entry["tokens"])
    paths = [r for r in rows if not _names_no_path(r[0])]
    keyed = _write_set_keys(paths, named, own, plan_root, project_root)
    joined = joined_outputs([*cited, *(key for key, _ in keyed)], own)
    for key, figure in sorted(cited.items(), key=lambda c: c[1][1]):  # the highest figure last
        cited[joined.get(key, key)] = figure

    keys: list[str] = []
    row_ids: list[list[str]] = []
    ids_of: dict[str, list[str]] = {}
    for key, ids in keyed:
        key = joined.get(key, key)
        keys.append(key)
        row_ids.append(ids)
        ids_of.setdefault(key, []).extend(ids)

    def measure(key: str, ids: list[str]) -> tuple | None:
        at = own[key] / key if key in own else named[ids[0]][0] if ids else plan_root / "row"
        best = None
        for model in {named[i][1] for i in ids} or {None}:
            try:
                price = price_row(key, at, plan_root, project_root, model, cache)
                size = size_of(Path(price["path"])) if size_of and price["priced"] else None
                if size is not None:
                    price = price_row(key, Path(price["path"]), plan_root, project_root,
                                      model, cache, size)
            except OSError:
                continue
            if price["priced"] and (best is None or price["tokens"] > best["tokens"]):
                best = price
        return best and (_fmt_kib(best["bytes"]), _fmt_k(best["tokens"]), "measured")

    figures: dict[str, tuple] = {}
    for key, ids in ids_of.items():
        if key in cited:
            figures[key] = (cited[key][0], _fmt_k(cited[key][1]), "cited")
        elif (found := measure(key, ids)) is not None:
            figures[key] = found
    reached = Counter(i for key, ids in zip(keys, row_ids) if key not in figures for i in ids)
    for key, ids in ids_of.items():
        split = [(shares[i] / reached[i], named[i][1]) for i in ids
                 if key not in figures and shares.get(i) is not None]
        if split:
            tokens, model = max(split, key=lambda s: s[0])
            ratio = bytes_per_token(model or "", content_class_for(Path(key))[1])
            with localcontext() as ctx:
                # An estimate may hold more digits than the default precision, or than a float.
                ctx.prec = max(ctx.prec, tokens.adjusted() + 12)
                kib = (tokens * Decimal(str(ratio)) / 1024).quantize(Decimal("0.1"))
                figures[key] = (f"{kib:,}", _fmt_k(tokens), "share")
    priced = iter([figures.get(key, (None, None, None)) for key in keys])
    return [(None, None, "no path") if _names_no_path(r[0]) else next(priced) for r in rows]


_OUTPUT_ADDEND_RE = re.compile(rf"\+\s*~\s*({_NUM})\s*K\s*\(?output\b")


def _output_tokens(text: str) -> Decimal | None:
    """The output addend of the `**Context subtotal:**` line, in tokens, or None."""
    line = next((ln for ln in text.split("\n") if ln.startswith("**Context subtotal:**")), "")
    m = _OUTPUT_ADDEND_RE.search(line)
    return Decimal(m.group(1).replace(",", "")) * 1000 if m else None


def _write_writeset(buf: _Buffers, report: dict, sprint_plan: Path, plan_root: Path,
                    project_root: Path, cache: _FileCache) -> None:
    """Price the `## Write-Set` rows; any failure leaves the file as it was.

    Only the `KiB` and `~Tokens` cells change. The columns are found by name,
    and a table without them is left alone and not reported. The figures come
    from every task file of the sprint, so every row is priced, also a row of a
    session this run does not name. A row with no figure, or that names no path,
    keeps its cells. The Sprint Plan may be a row itself, so the pass repeats
    until its size settles.
    """
    what = "Write-Set"
    fail = None
    try:
        # A lenient read first, so a Sprint Plan with nothing to price is never loaded.
        lines = buf.lines.get(sprint_plan)
        if lines is None:
            lines = sprint_plan.read_bytes().decode("utf-8", errors="replace").split("\n")
        table = _write_set_table(lines, _section_bounds(lines, what), _WRITE_SET_COLUMNS)
        if table is None:
            return
        lines, fail = _guard(buf, report, sprint_plan)
        head, (path_at, task_at, kib_at, tok_at), width = table
        tasks = [t for folder in sorted(sprint_plan.parent.iterdir()) if folder.is_dir()
                 for t in _surface_tasks(buf, folder) if not _is_orchestration(t[0])]
        shares = {_task_id(text.split("\n"), path): _output_tokens(text) for path, text in tasks}
        before = {}
        for n, i in enumerate(_table_rows(lines, head), start=1):
            cells = _cells(_split_eol(lines[i])[0], width)
            if len(cells) == width:
                before[i] = (n, cells)
            else:
                report["left"].append({"file": str(sprint_plan), "row": f"Write-Set {n}",
                                       "reason": "cell count differs from the header"})

        def size_of(path: Path) -> int | None:
            # Any other file this run rewrites is priced from `cache`.
            return _text_bytes(lines) if _same_file(sprint_plan, path) else None

        for _ in range(writeback._SELF_ROW_PASSES):
            measured = _text_bytes(lines)
            figures = writeset_figures([(c[path_at], c[task_at]) for _, c in before.values()], tasks,
                                       shares, plan_root, project_root, cache, size_of)
            for (i, (_, cells)), (kib, tokens, source) in zip(before.items(), figures):
                if source == "no path":
                    continue
                if source is None:
                    known = _parse_token_cell(cells[tok_at]) is not None
                    kib = cells[kib_at].strip() if known else ""
                    kib, tokens = kib or "0.0", cells[tok_at].strip() if known else _fmt_k(0)
                for at, value in ((kib_at, kib), (tok_at, tokens)):
                    if _cells(_split_eol(lines[i])[0], width)[at].strip() != value:
                        lines[i] = _rewrite_cell(lines[i], at, value, width)
            if _text_bytes(lines) == measured:
                break
        else:
            fail(what, f"the byte count still moved after {writeback._SELF_ROW_PASSES} passes")
            return
    except Exception as exc:  # noqa: BLE001 - the table never blocks the other writes
        reason = f"{type(exc).__name__}: {exc}"
        if fail is not None:
            fail(what, reason)
        else:
            report["unreadable"].append({"file": str(sprint_plan), "what": what, "reason": reason})
        return
    for i, (n, cells) in before.items():
        after = _cells(_split_eol(lines[i])[0], width)
        report["changes"].extend(
            {"file": str(sprint_plan), "line": i + 1, "what": f"{what} row {n} {label}",
             "old": cells[at].strip(), "new": after[at].strip()}
            for at, label in ((kib_at, "KiB"), (tok_at, "~Tokens"))
            if cells[at].strip() != after[at].strip())


_MASTER_LABEL = "**Write-set total:**"
_KIB_CELL_RE = re.compile(rf"^{_NUM}$")
# A path cell that names no path: empty, a dash, `none` with or without a remark, or an unanswered fill.
_NO_PATH_RE = re.compile(r"^(?:[-–—]?|n/a|none(?:[\s(,;:–—].*)?|.*<!-- FILL.*)$", re.IGNORECASE)
_WRITE_SET_COLUMNS = [("path",), ("task",), ("kib",), _TOKEN_HEADERS]


def _names_no_path(cell: str) -> bool:
    """Whether a Write-Set path cell names no path, so its row is neither priced nor counted."""
    return _NO_PATH_RE.match(cell.replace("`", "").replace("*", "").strip()) is not None


def keyed_write_set(rows: list[tuple], tasks: list[tuple[Path, str]], plan_root: Path,
                    project_root: Path) -> list[tuple[str, tuple]]:
    """(path key, row) per Write-Set row that names a path. A row starts with its path and task cells.

    Only an `Outputs/` path reads from its task's session folder. Any other
    spelling has one key in every row.
    """
    rows = [r for r in rows if not _names_no_path(r[0])]
    named = {_task_id(text.split("\n"), path): (path, None) for path, text in tasks}
    own = {path.name: path.parent for path, _ in tasks}
    cells = [(r[0], r[1] if f"{plain_path(_clean_file_cell(r[0]))}/".startswith("Outputs/") else "")
             for r in rows]
    keys = _write_set_keys(cells, named, own, plan_root, project_root)
    return [(key, row) for (key, _ids), row in zip(keys, rows)]


def write_set_paths(rows: list[tuple], tasks: list[tuple[Path, str]], plan_root: Path,
                    project_root: Path) -> dict[str, tuple[Decimal, Decimal]] | None:
    """{path key: (KiB, tokens)} of one sprint's Write-Set rows, or None when a row has no figure.

    `rows` holds (path, task, KiB, ~Tokens) cells and `tasks` every task file of
    the plan, so that a path has one key in every sprint. A path takes its
    highest printed ~Tokens cell, and the KiB cell of that row.
    """
    return path_figures(keyed_write_set(rows, tasks, plan_root, project_root))


def path_figures(keyed: list[tuple[str, tuple]]) -> dict[str, tuple[Decimal, Decimal]] | None:
    """`write_set_paths` over rows that `keyed_write_set` keyed."""
    paths: dict[str, tuple[Decimal, Decimal]] = {}
    for key, (_path, _task, kib, tokens) in keyed:
        value = _parse_token_cell(tokens)
        if value is None:
            return None
        if key not in paths or value > paths[key][1]:
            kib = kib.strip()
            paths[key] = (Decimal(kib.replace(",", "") if _KIB_CELL_RE.match(kib) else 0), value)
    return paths


def write_set_sums(paths: dict[str, tuple[Decimal, Decimal]]) -> tuple[str, str, str]:
    """The (Count, KiB, ~Tokens) cells of one sprint's distinct paths, summed over printed figures."""
    with localcontext() as ctx:
        # An estimate may hold more digits than the default precision.
        ctx.prec = max([ctx.prec, *(v.adjusted() + 12 for pair in paths.values() for v in pair)])
        kib = sum((k for k, _ in paths.values()), Decimal(0)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return str(len(paths)), f"{kib:,}", _fmt_k(sum((t for _, t in paths.values()), Decimal(0)))


def write_set_total(sprints: list[dict[str, tuple[Decimal, Decimal]]]) -> str:
    """The Master Plan's total line: each path of any sprint once, at its highest figure."""
    merged: dict[str, tuple[Decimal, Decimal]] = {}
    for paths in sprints:
        for key, pair in paths.items():
            if key not in merged or pair[1] > merged[key][1]:
                merged[key] = pair
    count, _kib, tokens = write_set_sums(merged)
    return f"{_MASTER_LABEL} {tokens} tokens over {count} distinct paths (information only)"


def _write_set_table(lines: list[str], bounds: tuple[int, int] | None,
                     names: list[tuple[str, ...]]) -> tuple[int, list[int], int] | None:
    """(header line, the columns of `names`, width) of the first table in `bounds` that has them all."""
    for i in range(*bounds) if bounds else ():
        header = _table_header_at(lines, i) or []
        columns = [_col(header, n) for n in names]
        if None not in columns:
            return i, columns, len(header)
    return None


def _sprint_plan_rows(buf: _Buffers, sprint_dir: Path) -> list[tuple] | None:
    """The sized Write-Set rows of a sprint folder's Sprint Plan, or None when it has no readable table."""
    found = sorted(sprint_dir.glob("*Sprint-Plan*.md"))
    if len(found) != 1:
        return None
    lines = buf.lines.get(found[0])
    if lines is None:
        lines = found[0].read_bytes().decode("utf-8", errors="replace").split("\n")
    table = _write_set_table(lines, _section_bounds(lines, "Write-Set"), _WRITE_SET_COLUMNS)
    if table is None:
        return None
    head, columns, width = table
    rows = [_cells(_split_eol(lines[i])[0], width) for i in _table_rows(lines, head)]
    if any(len(cells) != width for cells in rows):
        return None
    return [tuple(cells[at] for at in columns) for cells in rows]


def _write_master(buf: _Buffers, report: dict, plan_dir: Path, plan_root: Path,
                  project_root: Path) -> None:
    """Re-roll the Master Plan's `### Write-Sets` sizes and total.

    Every figure sums the printed cells of the Sprint Plans beside the Master
    Plan: this run's text when loaded, else the disk's. A row whose sprint has no
    sized Write-Set keeps its cells, and the total line then stays too. A
    missing Master Plan, column or total line is left alone and not reported.
    """
    found = sorted(plan_dir.glob("*-Master-Plan.md"))
    if len(found) != 1:
        return
    master, what = found[0], "Write-Sets"
    fail = None
    try:
        # A lenient read first, so a Master Plan with nothing to re-roll is never loaded.
        lines = buf.lines.get(master)
        if lines is None:
            lines = master.read_bytes().decode("utf-8", errors="replace").split("\n")
        start = next((i for i, ln in enumerate(lines) if re.match(rf"^###\s+{what}\b", ln)), None)
        if start is None:
            return
        stop = next((j for j in range(start + 1, len(lines)) if re.match(r"^#{1,3}\s", lines[j])), len(lines))
        table = _write_set_table(lines, (start, stop), [("sprint",), ("count",), ("kib",), _TOKEN_HEADERS])
        total_at = next((i for i in range(start, stop) if lines[i].startswith(_MASTER_LABEL)), None)
        if table is None and total_at is None:
            return
        lines, fail = _guard(buf, report, master)
        folders: dict[int, list[Path]] = {}
        tasks: list[tuple[Path, str]] = []
        for folder in sorted(p for p in plan_dir.iterdir() if p.is_dir()):
            m = re.match(r"Sprint-(\d+)(?:-|$)", folder.name)
            if m is None:
                continue
            folders.setdefault(int(m.group(1)), []).append(folder)
            tasks.extend(t for session in sorted(folder.iterdir()) if session.is_dir()
                         for t in _surface_tasks(buf, session) if not _is_orchestration(t[0]))
        paths = {}
        for number, same in folders.items():
            rows = _sprint_plan_rows(buf, same[0]) if len(same) == 1 else None
            paths[number] = None if rows is None else write_set_paths(rows, tasks, plan_root, project_root)
        head, columns, width = table or (0, [], 0)
        for n, i in enumerate(_table_rows(lines, head) if table else (), start=1):
            cells = _cells(_split_eol(lines[i])[0], width)
            if len(cells) != width:
                report["left"].append({"file": str(master), "row": f"{what} {n}",
                                       "reason": "cell count differs from the header"})
                continue
            m = re.match(r"Sprint-(\d+)(?!\w)", cells[columns[0]].replace("`", "").replace("*", "").strip())
            if m is None:
                continue
            known = paths.setdefault(int(m.group(1)), None)
            if known is not None:
                for at, value, label in zip(columns[1:], write_set_sums(known), ("Count", "KiB", "~Tokens")):
                    _set_cell(buf, report, master, i, at, cells, value, f"{what} {m.group(0)} {label}")
        if total_at is not None and paths and None not in paths.values():
            old, eol = _split_eol(lines[total_at])
            new = write_set_total(list(paths.values()))
            if new != old:
                lines[total_at] = new + eol
                report["changes"].append({"file": str(master), "line": total_at + 1,
                                          "what": "Write-set total", "old": old, "new": new})
    except Exception as exc:  # noqa: BLE001 - the Master Plan never blocks the other writes
        reason = f"{type(exc).__name__}: {exc}"
        if fail is not None:
            fail(what, reason)
        else:
            report["unreadable"].append({"file": str(master), "what": what, "reason": reason})


def _write_write_sets(buf: _Buffers, report: dict, sprint_dirs: list[Path], plan_root: Path,
                      project_root: Path, cache: _FileCache) -> None:
    """Price the Sprint Plans' Write-Sets, then sum them in the Master Plan.

    A Write-Set may name the Master Plan, whose size the sums change, or another
    sprint's Sprint Plan. `token_saver_writeback.write_estimates` repeats the whole
    pass until they settle.
    """
    root = plan_root.resolve()
    for sprint_dir in sprint_dirs:
        found = sorted(sprint_dir.glob("*Sprint-Plan*.md"))
        if len(found) == 1:
            _write_writeset(buf, report, found[0], plan_root, project_root, cache)
    for plan_dir in dict.fromkeys(s.parent for s in sprint_dirs):
        if plan_dir.resolve() == root or root in plan_dir.resolve().parents:
            _write_master(buf, report, plan_dir, plan_root, project_root)


def _is_orchestration(path: Path) -> bool:
    """Whether a file name is an Orchestration's, not that of a task whose name holds the word."""
    return _ORCHESTRATION_RE.search(path.name) is not None


def _session_orchestration(folder: Path, report: dict) -> Path | None:
    """The session's Orchestration: by its exact name, else the one file so called that is no task file."""
    found = [p for p in sorted(folder.glob(_ORCHESTRATION_GLOB)) if _is_orchestration(p)]
    if not found:
        found = [p for p in sorted(folder.glob("*Orchestration*.md"))
                 if not _is_task_text(p.read_bytes().decode("utf-8", errors="replace"))]
    return _one_file(folder, _ORCHESTRATION_GLOB, report, "Orchestration", found)


def _is_task_text(text: str) -> bool:
    """Whether a text is a task file's: it holds an `**Agent:**` line and a Required Context heading."""
    return (re.search(r"^\*\*Agent:\*\*", text, re.MULTILINE) is not None
            and re.search(r"^##+\s*Required Context", text, re.MULTILINE) is not None)


def _surface_tasks(buf: _Buffers, session_dir: Path) -> list[tuple[Path, str]]:
    """(path, text) of every task file in the folder: this run's text when loaded, else the disk's."""
    tasks = []
    for path in sorted(session_dir.glob("*.md")):
        text = ("\n".join(buf.lines[path]) if path in buf.lines
                else path.read_bytes().decode("utf-8", errors="replace"))
        if _is_task_text(text):
            tasks.append((path, text))
    return tasks


def _kept_rows(rows: list[str], kept: Counter) -> list[str]:
    """The path cells of the rows that `kept` counts, in file order."""
    left, out = Counter(kept), []
    for row in rows:
        if left[row] > 0:
            left[row] -= 1
            out.append(_cells(row, len(_SURFACE_COLUMNS))[0])
    return out


def _write_session_surface(buf: _Buffers, report: dict, orch: Path, plan_root: Path,
                           project_root: Path, cache: _FileCache) -> None:
    """Rewrite the `## Session Surface` rows and total; any failure leaves the file as it was.

    An Orchestration without the heading is left alone and not reported. The
    block holds the Orchestration's own row, so the pass repeats until the
    byte count settles, as `token_saver_writeback._write_task` does.
    """
    lines, fail = _guard(buf, report, orch)
    what = "Session Surface"
    try:
        bounds = _section_bounds(lines, what)
        if bounds is None:
            return
        head = next((i for i in range(*bounds) if _table_header_at(lines, i)), None)
        if head is None or _table_header_at(lines, head) != _SURFACE_COLUMNS:
            fail(what, "no table with the block's columns")
            return
        before = [_split_eol(lines[i])[0] for i in _table_rows(lines, head)]
        total_at = next((i for i in range(head, bounds[1])
                         if lines[i].startswith(_SURFACE_LABEL)), None)
        if total_at is None:
            fail(what, "total line not found")
            return
        old_total = _split_eol(lines[total_at])[0]
        present = {}
        for row in before:
            cells = _cells(row, len(_SURFACE_COLUMNS))
            if len(cells) == len(_SURFACE_COLUMNS):
                present[cells[0].replace("`", "").strip()] = (cells[2], cells[3])
        tasks = [t for t in _surface_tasks(buf, orch.parent) if t[0] != orch]
        models = {parse_agent(text) for _, text in tasks} or {None}

        def plan_file(name: str, own_bytes: int) -> tuple:
            best = None
            for model in models:
                try:
                    price = price_row(name, orch, plan_root, project_root, model, cache, own_bytes)
                except OSError:
                    continue
                if price["priced"] and (best is None or price["tokens"] > best["tokens"]):
                    best = price
            if best is None:
                return (name, *present.get(name, (None, None)))
            return name, _fmt_kib(best["bytes"]), _fmt_k(best["tokens"])

        recovery = orch.name.replace("Orchestration", "Recovery")
        eol = _split_eol(lines[head])[1]
        for _ in range(writeback._SELF_ROW_PASSES):
            measured = _text_bytes(lines)
            entries = surface_entries(tasks, [plan_file(orch.name, measured),
                                              plan_file(recovery, measured)],
                                      plan_root, project_root)
            total_at = next(i for i in range(head, len(lines))
                            if lines[i].startswith(_SURFACE_LABEL))
            lines[total_at] = surface_total(entries) + _split_eol(lines[total_at])[1]
            rows = _table_rows(lines, head)
            lines[head + 2:head + 2 + len(rows)] = [surface_row(e) + eol for e in entries]
            if _text_bytes(lines) == measured:
                break
        else:
            fail(what, f"the byte count still moved after {writeback._SELF_ROW_PASSES} passes")
            return
    except Exception as exc:  # noqa: BLE001 - the block never blocks the other writes
        fail(what, f"{type(exc).__name__}: {exc}")
        return
    after = [surface_row(e) for e in entries]
    pairs = [("", row) for row in (Counter(after) - Counter(before)).elements()]
    pairs += [(row, "") for row in (Counter(before) - Counter(after)).elements()]
    old_order, new_order = (_kept_rows(rows, Counter(before) & Counter(after))
                            for rows in (before, after))
    if old_order != new_order:
        pairs.append(("row order: " + ", ".join(old_order), "row order: " + ", ".join(new_order)))
    if surface_total(entries) != old_total:
        pairs.append((old_total, surface_total(entries)))
    report["changes"].extend({"file": str(orch), "line": head + 1, "what": what,
                              "old": old, "new": new} for old, new in pairs)


def _reroll_task_table(buf: _Buffers, report: dict, path: Path, bounds: tuple[int, int],
                       task_totals: list[tuple[str, str, str]], fail, label: str,
                       total_required: bool) -> str | None:
    """Copy each task's header into its row; re-sum `**Total Estimated:**`.

    The table is the one in `bounds` with `#`, Task and token columns. A row
    is the task's when its `#` cell equals the Task ID's trailing number AND
    its Task cell names the task file's name segment. A Task ID is never
    searched for in the row: a Depends On cell cites other tasks' IDs. Any
    task row not found exactly once, or a total that cannot be re-rolled with
    its breakdown, calls `fail`, which leaves the whole file as authored.
    Returns the total text ("" when the optional total line is absent).
    """
    lines = buf.get(path)
    where = str(path)
    tables = [t for t in _token_tables(lines, *bounds)
              if _col(t[3], ("#",)) is not None and _col(t[3], ("task",)) is not None]
    if len(tables) != 1:
        fail(label, f"{len(tables)} tables with #, Task and token columns")
        return None
    _, tok, rows, header = tables[0]
    num_idx, task_idx = _col(header, ("#",)), _col(header, ("task",))
    task_rows = []  # footer and total rows carry no number in `#`
    for r in rows:
        cells = _cells(_split_eol(lines[r])[0], len(header))
        if len(cells) == len(header) and cells[num_idx].strip().isdigit():
            task_rows.append((r, cells))
    found = []
    for task_id, name, total in task_totals:
        m = re.search(r"-(\d+)$", task_id)
        if not m:
            fail(f"task row {task_id}", "the Task ID has no trailing -NN number")
            return None
        hits = [t for t in task_rows if int(t[1][num_idx]) == int(m.group(1))]
        if len(hits) != 1:
            fail(f"task row {task_id}",
                 f"{len(hits)} task rows numbered {int(m.group(1))}")
            return None
        if not re.search(rf"(?<!\w){re.escape(name)}(?!\w)",
                         hits[0][1][task_idx].replace("`", "")):
            fail(f"task row {task_id}",
                 f"row {int(m.group(1))}'s Task cell does not name {name!r}")
            return None
        found.append((hits[0], task_id, total))
    for (r, cells), task_id, total in found:
        _set_cell(buf, report, path, r, tok, cells, total, f"{label} {task_id}")
    values = [_parse_token_cell(_cells(_split_eol(lines[r])[0], len(header))[tok])
              for r, _ in task_rows]
    if None in values:
        fail("Total Estimated", "a task-list cell has no figure")
        return None
    idx = next((i for i in range(*bounds)
                if re.match(r"^\*\*Total Estimated:\*\*", lines[i])), None)
    if idx is None and not total_required:
        return ""
    return _reroll_k_line(lines, idx, [v / 1000 for v in values], fail, report, where,
                          "Total Estimated")


def _reroll_k_line(lines: list[str], idx: int | None, values_k: list[Decimal], fail,
                   report: dict, where: str, what: str) -> str | None:
    """Set the first `~NK` of line `idx` to the sum of `values_k`, with its breakdown."""
    km = _K_TERM_RE.search(lines[idx]) if idx is not None else None
    if km is None:
        fail(what, "line not found")
        return None
    total_text = _fmt_k_exact(sum(values_k, Decimal(0)), km.group(0))
    line = lines[idx][:km.start()] + total_text + lines[idx][km.end():]
    line = _reroll_breakdown(line, km.start() + len(total_text), values_k)
    if line is None:
        fail(what, "its breakdown does not match the rows one-to-one")
        return None
    if line != lines[idx]:
        report["changes"].append({"file": where, "line": idx + 1, "what": what,
                                  "old": _split_eol(lines[idx])[0],
                                  "new": _split_eol(line)[0]})
        lines[idx] = line
    return total_text


def _write_sprint_plan(buf: _Buffers, report: dict, sprint_plan: Path, session_id: str,
                       total_text: str, task_totals: list[tuple[str, str, str]]) -> None:
    """Re-roll the session's Sprint Plan figures, or leave the file as authored.

    The `## Sessions` row whose cell is the ID takes the session total. The
    `**Estimated Tokens:**` header takes the sum of the Sessions rows. Under
    `## Session Details`, the `###` subsection naming the ID has its task
    cells and its optional `**Total Estimated:**` re-rolled.
    """
    lines, fail = _guard(buf, report, sprint_plan)
    what = f"session row {session_id}"
    bounds = _section_bounds(lines, "Sessions")
    if bounds is None:
        fail(what, "no ## Sessions section")
        return
    hits = []
    for _, tok, rows, header in _token_tables(lines, *bounds):
        for r in rows:
            cells = _cells(_split_eol(lines[r])[0], len(header))
            if len(cells) == len(header) and any(
                    c.replace("`", "").strip() == session_id for c in cells):
                hits.append((r, tok, cells, rows, header))
    if len(hits) != 1:
        fail(what, f"{len(hits)} Sessions rows hold the ID")
        return
    r, tok, cells, rows, header = hits[0]
    _set_cell(buf, report, sprint_plan, r, tok, cells, total_text, what)
    rows_cells = [_cells(_split_eol(lines[x])[0], len(header)) for x in rows]
    values = [_parse_token_cell(c[tok]) for c in rows_cells
              if len(c) == len(header) and c[0].strip().isdigit()]
    if None in values:
        fail("Estimated Tokens", "a Sessions cell has no figure")
        return
    idx = next((i for i, ln in enumerate(lines)
                if re.match(r"^\*\*Estimated Tokens:\*\*", ln)), None)
    if _reroll_k_line(lines, idx, [v / 1000 for v in values], fail, report,
                      str(sprint_plan), "Estimated Tokens") is None:
        return
    details = _section_bounds(lines, "Session Details")
    id_re = rf"(?<![\w-]){re.escape(session_id)}(?![\w-])"
    start = next((i for i in range(*details) if re.match(r"^###\s", lines[i])
                  and re.search(id_re, lines[i])), None) if details else None
    if start is None:
        fail("Session Details", f"no ### subsection names {session_id}")
        return
    stop = next((j for j in range(start + 1, details[1])
                 if re.match(r"^#{1,3}\s", lines[j])), details[1])
    _reroll_task_table(buf, report, sprint_plan, (start, stop), task_totals, fail,
                       "Session Details", total_required=False)
