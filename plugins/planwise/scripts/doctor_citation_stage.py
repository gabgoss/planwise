#!/usr/bin/env python3
"""Doctor's Consumer Section-Citation Check stage — read-only, always-on.

`run_section_citation_stage(cfg)` resolves every `§` citation in the consumer
project's `.claude/rules/` tree against the installed plugin's `references/`
through `check_section_citations.check_tree`. The installed `cfg.plugin_root`
is the tree checked, because that is the copy the consumer's rules cite.

Each `dangling`, `redirected` or `unresolved-target` finding in a consumer rule
whose cited target is a plugin file prints as an upgrade leftover, followed by
one remedy line. A `redirected` finding names the file that now holds the
section. A target is a plugin file when it resolves under the plugin root, or,
when it does not resolve, when its path starts with a plugin directory such as
`references/`. Findings that cite project files are counted, not printed. The
plugin's own findings are not reported, and `.claude/rules/planwise/` is
excluded from the check: it holds machine-managed installed copies that
`/planwise upgrade` owns. Nothing here asks a question or writes a file. The
caller wraps the stage, so an exception never changes doctor's exit status.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_section_citations import check_tree

_REPORTED = ("dangling", "redirected", "unresolved-target")
_REMEDY = (
    "Edit the citing rule to the section that now holds the text, "
    "or run /planwise upgrade if the citing file is a stale installed copy."
)


def _is_under(path: Path, base: Path) -> bool:
    return path == base or base in path.parents


def _cites_plugin(finding, plugin_root: Path) -> bool:
    """Whether the finding's target is a plugin file, or names a path under a plugin directory."""
    target = finding.target.replace("\\", "/")
    if finding.verdict != "unresolved-target":
        # A resolved target under the plugin root is shown relative to it.
        return not Path(target).is_absolute() and (plugin_root / target).is_file()
    parts = [p for p in target.split("/") if p not in ("", ".", "..")]
    return len(parts) > 1 and (plugin_root / parts[0]).is_dir()


def run_section_citation_stage(cfg) -> None:
    """Print each dangling citation of a plugin file in the consumer's own rules. Read-only."""
    project_root = Path(cfg.project_root).resolve()
    plugin_root = Path(cfg.plugin_root).resolve()
    rules_dir = project_root / ".claude" / "rules"
    managed_dir = rules_dir / "planwise"
    if not rules_dir.is_dir():
        print("No .claude/rules/ directory; no citation to check.")
        return

    findings = check_tree(plugin_root, extra_roots=(rules_dir,), exclude=(managed_dir,))
    leftovers = []
    skipped = 0
    for f in findings:
        path = Path(f.path).resolve()
        if f.verdict not in _REPORTED or not _is_under(path, rules_dir):
            continue
        if not _cites_plugin(f, plugin_root):
            skipped += 1
            continue
        leftovers.append((path.relative_to(project_root).as_posix(), f))
    leftovers.sort(key=lambda item: (item[0], item[1].line))
    skip_note = f"{skipped} citation(s) to project files skipped" if skipped else ""

    if not leftovers:
        print(
            "No dangling section citation in .claude/rules/ "
            "(installed copies under .claude/rules/planwise/ skipped)."
            + (f" {skip_note}." if skip_note else "")
        )
        return

    suffix = f" ({skip_note})" if skip_note else ""
    print(f"{len(leftovers)} dangling section citation(s), likely upgrade leftovers{suffix}:")
    for shown, f in leftovers:
        if f.verdict == "dangling":
            missing = f"section §{f.section} is not in {f.target}"
        elif f.verdict == "redirected":
            missing = f"section §{f.section} now lives in {f.target} ({f.note})"
        else:
            missing = f"file {f.target} does not resolve ({f.note})" if f.note else f"file {f.target} does not resolve"
        print(f"  {shown}:{f.line}: {f.citation} — {missing}")
    print(_REMEDY)
