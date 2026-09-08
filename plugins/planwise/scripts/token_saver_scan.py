#!/usr/bin/env python3
"""Step 8c Token Saver large-file scan — the driver for `classify_file`.

`handlers/plan.md` Step 8c makes a per-file large-file scan MANDATORY whenever
the effective Token Saver value is true: derive thresholds from the measured
overhead, classify every Required Context file in every task against the task's
assigned model, emit a per-file recommendation block, and file a backlog item
for every Warn-or-worse file.

The classifier and the budget engine both existed; nothing invoked them. An
authoring agent that wanted the scan had to hand-write Python per file per
task, so in practice it wrote the `PAGED` annotation from judgement and no gate
could tell the difference. A correct annotation reached by the wrong method
produces no symptom, which is why this driver exists.

This module walks the plan, resolves each Required Context row to a real path,
and delegates every size judgement to `read_limits.classify_file`. It carries
NO thresholds of its own — see "Why there is no band here" below.

Run it through the facade, which is the invocation Step 8c cites:

    python token_saver.py --scan --plan {plan_path} --config {config}

Exit codes: 0 when every classified file is Green (or the scan does not apply),
1 when any file classifies Warn or worse, 2 on a usage error.

Why there is no band here
-------------------------
Token estimates come from `classify_file`, which computes `bytes / the reading
model's bytes-per-token ratio`. This module never derives a token figure from a
line count, and defines no ratio of its own. A superseded model classed markdown
flat at a per-line rate; measured per-line rates range from 7 to 365 tokens/line
depending on content, so that model under-reported exactly the dense index files
a scan exists to catch. Bytes predict the gate; lines do not.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

# Fix Windows cp1252 stdout encoding — the report carries U+26A0 and U+2265.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import (  # noqa: E402
    get_effective_token_saver_config,
    load_config,
)
from context_calibration import derive_thresholds  # noqa: E402
from markdown_parser import split_row_cells  # noqa: E402
from read_limits import (  # noqa: E402
    READ_FILE_BYTE_CAP,
    READ_PAGE_CAP_TOKENS,
    classify_file,
)

# A Required Context row whose File cell is a command corpus, not a path: the
# command's OUTPUT is what the task reads, and no file measurement prices it.
_CORPUS_PREFIXES = ("grep ", "glob ", "read ", "bash ", "python ", "git ")

_CODE_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cs", ".go", ".rb", ".rs",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".sh", ".ps1", ".sql", ".css", ".html",
}
_DENSE_SUFFIXES = {".json", ".ipynb", ".ndjson", ".jsonl", ".min.js", ".csv"}

_CONTENT_CLASS = {"code": "code", "dense": "dense-md", "doc": "prose"}


# ---------------------------------------------------------------------------
# Task-file parsing
# ---------------------------------------------------------------------------
def parse_agent(text: str) -> str | None:
    """Return the task's assigned Agent, lowercased, from its header field."""
    m = re.search(r"^\*\*Agent:\*\*\s*(.+?)\s*$", text, re.MULTILINE)
    if not m:
        return None
    # The field may carry a qualifier ("Sonnet (1M-exception)"); take the model.
    return re.split(r"[\s(/|]", m.group(1).strip())[0].strip().lower() or None


def _split_row(line: str) -> list[str]:
    """Split one markdown table row into stripped cells.

    Delegates to the escape-aware helper: a Purpose cell may legitimately
    carry an escaped pipe (e.g. a shell pipeline shown inline), and a naive
    split there would shift every subsequent column right by one.
    """
    return split_row_cells(line)


def parse_required_context(text: str) -> list[dict]:
    """Parse the `## Required Context` table into rows.

    Columns are located by HEADER NAME, never by position. Live plans disagree
    on the column set — the current template emits
    `| Priority | File | KiB | ~Tokens | Purpose |` while plans authored earlier
    emit `| Priority | File | Est. Lines | Est. Tokens | Purpose |`. A
    positional parser silently reads the wrong cell on one of them.
    """
    section = re.search(
        r"^##+\s*Required Context.*?$(.*?)(?=^##+\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not section:
        return []

    rows: list[dict] = []
    file_idx = purpose_idx = None
    for line in section.group(1).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_row(stripped)
        if set("".join(cells)) <= set("-: "):  # the ---|--- separator
            continue
        lowered = [c.lower() for c in cells]
        if file_idx is None:
            if any(c == "file" or c.startswith("file") for c in lowered):
                file_idx = next(
                    i for i, c in enumerate(lowered) if c.startswith("file")
                )
                purpose_idx = next(
                    (i for i, c in enumerate(lowered) if c.startswith("purpose")),
                    None,
                )
            continue
        if file_idx >= len(cells):
            continue
        purpose = (
            cells[purpose_idx]
            if purpose_idx is not None and purpose_idx < len(cells)
            else ""
        )
        rows.append({"file_cell": cells[file_idx], "purpose": purpose})
    return rows


def _clean_file_cell(cell: str) -> str:
    """Strip markdown decoration and any trailing section-span suffix."""
    raw = cell.replace("`", "").replace("**", "").strip()
    # A span row cites `path §X–§Y (...)`; the path ends at the first section mark.
    raw = re.split(r"\s+§", raw)[0]
    raw = re.split(r"\s+—\s|\s+--\s", raw)[0]
    return raw.strip().strip("<>").strip()


def is_command_corpus(cell: str) -> bool:
    """True when the row prices a command's output rather than a file."""
    low = _clean_file_cell(cell).lower()
    return low.startswith(_CORPUS_PREFIXES)


def parse_projected_bytes(purpose: str, path: str | None) -> int:
    """Read an optional `+N lines` / `+N bytes` growth annotation from Purpose.

    Step 8c wants a file the SAME task will modify classified against its
    post-edit size, so a file that only crosses a gate once the edit lands is
    flagged pre-emptively. A line-denominated annotation is converted with the
    file's OWN observed average bytes/line, exactly as Step 8c prescribes —
    never with a global per-line constant.
    """
    m = re.search(r"\+\s*([\d,]+)\s*(bytes|byte|B|lines|line)\b", purpose)
    if not m:
        return 0
    value = int(m.group(1).replace(",", ""))
    unit = m.group(2).lower()
    if unit.startswith("b"):
        return value
    if not path or not os.path.exists(path):
        return 0
    num_bytes = os.path.getsize(path)
    with open(path, "rb") as f:
        lines = max(1, f.read().count(b"\n"))
    return int(value * (num_bytes / lines))


_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def substitute_roots(raw: str, project_root: Path) -> str:
    """Expand the root placeholders task files legitimately cite."""
    return (
        raw.replace("{plugin_root}", str(_PLUGIN_ROOT))
        .replace("{project_root}", str(project_root))
        .replace("{planwise_root}", str(project_root / "planwise"))
    )


def unresolved_reason(cell: str, project_root: Path) -> str:
    """Say WHY a row did not resolve, so the list is triageable.

    An unresolved row is not automatically a defect: a plan legitimately cites
    the outputs it has not produced yet, and a glob row names a set rather than
    a file. Only `missing` is a finding.
    """
    raw = substitute_roots(_clean_file_cell(cell), project_root)
    if "*" in raw or "?" in raw:
        return "pattern"
    if "{" in raw:
        return "placeholder"
    parts = Path(raw).parts
    if "Outputs" in parts or raw.startswith("Outputs"):
        return "plan output (not yet created)"
    if not Path(raw).suffix or "output" in raw.lower():
        # No separator and no extension, or self-described as a command's
        # output: the cell names prose or a corpus, not a file on disk.
        return "not a path (prose or command output)"
    return "missing"


def resolve_context_path(
    cell: str, task_path: Path, plan_root: Path, project_root: Path
) -> Path | None:
    """Resolve a Required Context File cell to an existing file, or None.

    Candidate roots, in order: the project root (rows normally cite a
    project-relative path), the task file's own directory, the plan root, and
    the plan root's parents up to the project root.
    """
    raw = _clean_file_cell(cell)
    if not raw or is_command_corpus(cell):
        return None
    raw = substitute_roots(raw, project_root)
    if "{" in raw or "*" in raw or "?" in raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None

    roots = [project_root, task_path.parent, plan_root]
    parent = plan_root
    while parent != project_root and parent.parent != parent:
        parent = parent.parent
        roots.append(parent)
    for root in roots:
        resolved = root / candidate
        if resolved.is_file():
            return resolved

    # Last resort: a sibling-session citation gives a bare filename that no
    # root above reaches. Accept it ONLY when the plan holds exactly one file
    # of that name — an ambiguous basename would silently measure the wrong
    # file, which is worse than reporting the row unresolved.
    if len(candidate.parts) == 1 and candidate.suffix:
        matches = list(plan_root.rglob(candidate.name))
        if len(matches) == 1:
            return matches[0]
    return None


def content_class_for(path: Path) -> tuple[str, str | None]:
    """Return (file-type label, bytes-per-token content class) for a path.

    The label drives the REMEDY wording; the content class drives the RATIO.
    A doc gets `None`, not "prose": an extension cannot tell narrative prose
    from a dense table index, and `bytes_per_token(model, None)` falls back to
    that model family's smallest (most token-heavy) ratio. Guessing "prose" on
    a dense `.md` under-estimates its tokens, which is the unsafe direction —
    it is exactly the index-shaped file this scan exists to catch.
    """
    suffix = path.suffix.lower()
    if suffix in _DENSE_SUFFIXES:
        return "dense", _CONTENT_CLASS["dense"]
    if suffix in _CODE_SUFFIXES:
        return "code", _CONTENT_CLASS["code"]
    return "doc", None


_REMEDY = {
    "code": "refactor into smaller modules",
    "doc": "Multi-Part split (Multi-Part Output Convention)",
    "dense": "measure precisely and extract only the needed sections",
}


def find_task_files(plan_root: Path) -> list[Path]:
    """Every markdown file under the plan that is a task file.

    Identified by CONTENT — an `**Agent:**` header plus a Required Context
    section — not by filename pattern, so a plan whose naming drifts is still
    scanned rather than silently skipped.
    """
    found = []
    for path in sorted(plan_root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"^\*\*Agent:\*\*", text, re.MULTILINE) and re.search(
            r"^##+\s*Required Context", text, re.MULTILINE
        ):
            found.append(path)
    return found


def parse_plan_token_saver_override(plan_root: Path) -> bool | None:
    """Read the Master Plan's `**Token Saver:**` field: on/off/inherit."""
    for path in sorted(plan_root.rglob("*Master-Plan*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"^\*\*Token Saver:\*\*\s*(\w+)", text, re.MULTILINE)
        if m:
            value = m.group(1).lower()
            if value == "on":
                return True
            if value == "off":
                return False
            return None
    return None


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------
def scan_plan(
    plan_root: Path,
    config: dict,
    project_root: Path,
    projected: dict[str, int] | None = None,
) -> dict:
    """Classify every Required Context file in every task under `plan_root`."""
    projected = projected or {}
    override = parse_plan_token_saver_override(plan_root)
    ts_config = get_effective_token_saver_config(config, override)

    result = {
        "plan": str(plan_root),
        "token_saver_effective": ts_config["token_saver"],
        "thresholds": None,
        "tasks": [],
        "findings": [],
        "unresolved": [],
        "summary": {
            "tasks": 0, "files": 0,
            "green": 0, "notice": 0, "warn": 0, "critical": 0,
        },
    }
    if not ts_config["token_saver"]:
        return result

    thresholds = derive_thresholds(
        session_target=int(ts_config["token_saver_session_target"]),
        runner_overhead=int(ts_config["token_saver_runner_overhead"]),
    )
    result["thresholds"] = thresholds

    for task_path in find_task_files(plan_root):
        text = task_path.read_text(encoding="utf-8", errors="replace")
        model = parse_agent(text)
        rows = parse_required_context(text)
        task_rel = str(task_path.relative_to(project_root)) \
            if _is_relative(task_path, project_root) else str(task_path)
        task_entry = {"task": task_rel, "model": model, "files": []}
        result["summary"]["tasks"] += 1

        for row in rows:
            if is_command_corpus(row["file_cell"]):
                continue
            resolved = resolve_context_path(
                row["file_cell"], task_path, plan_root, project_root
            )
            if resolved is None:
                cleaned = _clean_file_cell(row["file_cell"])
                if cleaned:
                    result["unresolved"].append({
                        "task": task_rel,
                        "cell": cleaned,
                        "reason": unresolved_reason(row["file_cell"], project_root),
                    })
                continue

            file_type, content = content_class_for(resolved)
            added = projected.get(str(resolved)) or projected.get(
                _clean_file_cell(row["file_cell"])
            ) or parse_projected_bytes(row["purpose"], str(resolved))
            verdict = classify_file(
                str(resolved),
                model=model or "",
                projected_added_bytes=added,
                thresholds=thresholds,
                content=content,
            )
            entry = {
                "path": str(resolved),
                "cell": _clean_file_cell(row["file_cell"]),
                "task": task_rel,
                "model": model,
                "file_type": file_type,
                "projected_added_bytes": added,
                **verdict,
            }
            entry["annotations"] = annotations_for(verdict, model)
            entry["recommendation"] = recommend(verdict, file_type)
            task_entry["files"].append(entry)
            result["summary"]["files"] += 1
            result["summary"][verdict["level"].lower()] += 1
            if verdict["level"] != "Green":
                result["findings"].append(entry)

        result["tasks"].append(task_entry)
    return result


def _is_relative(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def annotations_for(verdict: dict, model: str | None) -> list[str]:
    """The mechanical `PAGED` / `REFACTOR` strings for a task-file row.

    Emitting these from the classifier is the point: a hand-written annotation
    and a computed one are otherwise indistinguishable.
    """
    out = []
    if verdict["tokens"] >= READ_PAGE_CAP_TOKENS:
        out.append(f"⚠ PAGED ≥25K {model or 'default'}-tok")
    if verdict["bytes"] >= READ_FILE_BYTE_CAP:
        out.append("⚠ REFACTOR ≥256 KiB")
    return out


def recommend(verdict: dict, file_type: str) -> str:
    """The Step 8c recommendation for one verdict.

    A `read`-reason Critical is NEVER `1M-exception`: the 1M window does not
    raise the per-Read page cap, so the remedy is paged reads or a refactor.
    Only a `cost`-reason Critical earns the flag.
    """
    level, reason = verdict["level"], verdict["reason"]
    if level == "Critical" and reason == "cost":
        return (
            "flag the task 1M-exception (dispatch Opus/1M) + file a backlog item"
        )
    if level == "Critical":
        return (
            "paged read (offset/limit/Grep) for read-only context, or "
            f"{_REMEDY[file_type]} + file a backlog item for a core/edited "
            "dependency. Do NOT flag 1M-exception"
        )
    if level == "Warn":
        return f"{_REMEDY[file_type]} + file a backlog item"
    return f"advisory only — {_REMEDY[file_type]} is advisable; no backlog item"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
_SEVERITY = {"Green": 0, "Notice": 1, "Warn": 2, "Critical": 3}


def group_findings(findings: list[dict]) -> list[dict]:
    """Collapse per-task findings to one entry per file, worst verdict kept.

    Two tasks may cite the same file under different models, which yields
    different token estimates for one file. The severest verdict is the one
    that has to be acted on, so it wins and its model is the one reported.
    Ordered severest first, then largest.
    """
    by_path: dict[str, dict] = {}
    for f in findings:
        current = by_path.get(f["path"])
        if current is None:
            entry = dict(f)
            entry["tasks"] = [f["task"]]
            by_path[f["path"]] = entry
            continue
        if f["task"] not in current["tasks"]:
            current["tasks"].append(f["task"])
        if _SEVERITY[f["level"]] > _SEVERITY[current["level"]] or (
            _SEVERITY[f["level"]] == _SEVERITY[current["level"]]
            and f["tokens"] > current["tokens"]
        ):
            tasks = current["tasks"]
            current.clear()
            current.update(f)
            current["tasks"] = tasks
    return sorted(
        by_path.values(),
        key=lambda e: (-_SEVERITY[e["level"]], -e["tokens"]),
    )


def format_report(result: dict) -> str:
    if not result["token_saver_effective"]:
        return (
            f"Token Saver large-file scan — {result['plan']}\n\n"
            "Effective Token Saver is OFF for this plan; Step 8c's scan does "
            "not apply.\nNothing classified."
        )

    t = result["thresholds"]
    s = result["summary"]
    out = [
        f"Token Saver large-file scan — {result['plan']}",
        "",
        f"Thresholds (derived, never hardcoded): available_per_task="
        f"{t['available_per_task']:,}  warn={t['warn']:,}  "
        f"critical={t['critical']:,}",
        f"Scanned {s['tasks']} task(s), {s['files']} Required Context file(s).",
        "",
    ]

    # One block per FILE, listing every citing task. A multiply-cited file's
    # size is a single source of truth, so repeating its block once per citing
    # task would restate one measurement as if it were several.
    grouped = group_findings(result["findings"])
    if grouped:
        out.append("Per-file recommendations (Green files are silent):")
        out.append("")
        for f in grouped:
            out.append(f"  [{f['level']} / reason={f['reason']}] {f['cell']}")
            projected = (
                f"  (+{f['projected_added_bytes']:,} projected)"
                if f["projected_added_bytes"] else ""
            )
            out.append(
                f"      size:   {f['bytes']:,} B / ~{f['tokens']:,} tok / "
                f"{f['lines']:,} lines{projected}"
            )
            out.append(
                f"      model:  {f['model'] or 'default'}   type: {f['file_type']}"
            )
            if f["annotations"]:
                out.append(f"      annotate: {'  '.join(f['annotations'])}")
            out.append(f"      remedy: {f['recommendation']}")
            out.append(f"      cited by {len(f['tasks'])} task(s):")
            for task in f["tasks"]:
                out.append(f"        - {task}")
            out.append("")
    else:
        out.append("All classified files are Green — no recommendation blocks.")
        out.append("")

    worklist = [f for f in grouped if f["level"] in ("Warn", "Critical")]
    if worklist:
        out.append(
            f"Backlog filing worklist — {len(worklist)} file(s) at Warn or worse "
            "require an item:"
        )
        for f in worklist:
            out.append(f"  - {f['cell']}  ({f['level']}/{f['reason']})")
        out.append("")

    if result["unresolved"]:
        buckets: dict[str, list[dict]] = {}
        for u in result["unresolved"]:
            buckets.setdefault(u["reason"], []).append(u)
        out.append(
            f"Unclassified Required Context rows ({len(result['unresolved'])}) "
            "— by reason. Only `missing` is a defect; a plan legitimately cites "
            "outputs it has not written yet, and a pattern names a set:"
        )
        for reason in sorted(buckets, key=lambda r: (r != "missing", r)):
            rows = buckets[reason]
            cells = sorted({u["cell"] for u in rows})
            out.append(f"  {reason}: {len(rows)} row(s), {len(cells)} distinct")
            for cell in cells[:5]:
                out.append(f"    - {cell}")
            if len(cells) > 5:
                out.append(
                    f"    … {len(cells) - 5} more (full list in --json)"
                )
        out.append("")

    out.append(
        f"Levels (per Required Context row, so a shared file counts once per "
        f"citing task): {s['green']} Green, {s['notice']} Notice, "
        f"{s['warn']} Warn, {s['critical']} Critical"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="token_saver.py --scan",
        description=(
            "Run the handlers/plan.md Step 8c Token Saver large-file scan over "
            "every task's Required Context in a plan."
        ),
    )
    parser.add_argument("--scan", action="store_true",
                        help="run the scan (accepted for the documented form)")
    parser.add_argument("--plan", required=True,
                        help="path to the plan directory to scan")
    parser.add_argument("--config", default=None,
                        help="path to config.yaml (else the usual search order)")
    parser.add_argument("--json", action="store_true",
                        help="also write a JSON temp file and print its path")
    parser.add_argument("--projected", action="append", default=[],
                        metavar="PATH=BYTES",
                        help="projected added bytes for a file this plan edits; "
                             "repeatable")
    args = parser.parse_args(argv)

    plan_root = Path(args.plan).resolve()
    if not plan_root.is_dir():
        print(f"ERROR: --plan is not a directory: {plan_root}", file=sys.stderr)
        return 2

    projected: dict[str, int] = {}
    for pair in args.projected:
        key, _, value = pair.partition("=")
        if not value.strip().isdigit():
            print(f"ERROR: --projected expects PATH=BYTES, got {pair!r}",
                  file=sys.stderr)
            return 2
        projected[str(Path(key).resolve())] = int(value)
        projected[key] = int(value)

    config = load_config()
    project_root = Path(
        config.get("project_root") or config.get("_config_dir") or Path.cwd()
    ).resolve()

    result = scan_plan(plan_root, config, project_root, projected)
    print(format_report(result))

    if args.json:
        tmp_dir = tempfile.mkdtemp(prefix="planwise-tokensaver-scan-")
        json_path = os.path.join(tmp_dir, "scan.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"JSON: {json_path}")

    warn_or_worse = result["summary"]["warn"] + result["summary"]["critical"]
    return 1 if warn_or_worse else 0


if __name__ == "__main__":
    sys.exit(main())
