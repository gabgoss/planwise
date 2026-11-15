#!/usr/bin/env python3
"""Every `module.name(` call a handler, reference, agent, skill or template
writes must resolve on that module under plugins/planwise/scripts/.

Predicate: for each markdown file under the five consumer directories, each
token of the form `module.name(` whose `module` matches a scripts/<module>.py
file must satisfy hasattr(imported module, name). A markdown handler that tells
an agent to call `module.name(...)` is a consumer of the module exactly like a
Python import (measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md,
sub-rule J).

Exit contract of the pytest run: green when every miss is held in
UNRESOLVED_CALLS, red on a new miss or on a stale exemption.

What this cannot see: a call written without the `module.` prefix, a call on
an alias (`import m as a; a.f()`), a call split across lines, a call inside a
non-markdown file, and the arguments of a call. A hit whose `name` is `py`
is a file name (`module.py(`), not a call, and is skipped.

Run with:  python -m pytest -q -c pytest.ini tests/test_module_call_resolution.py
"""

import functools
import importlib
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

CONSUMER_DIRS = ("handlers", "references", "agents", "skills", "templates")

# A candidate call: `module.name(` not preceded by a word char, dot, slash or
# hyphen (so `a.b.c(`, `path/mod.f(` and `x-mod.f(` are not read as module calls).
CALL_RE = re.compile(r"(?<![\w./-])([a-z][a-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\(")

# Misses found on the real tree. Key: "<file relative to plugins/planwise>:
# <module.name>". Value: the owner who repairs the citing file. A miss is never
# skipped or xfailed: it is held here, reported, and routed.
UNRESOLVED_CALLS: dict[str, str] = {}


def script_modules() -> set[str]:
    return {p.stem for p in SCRIPTS_DIR.glob("*.py")}


def find_calls(text: str, modules: set[str]) -> tuple[list[tuple[int, str, str]], int]:
    """Return ([(line, module, name)] kept, count of candidates excluded)."""
    kept: list[tuple[int, str, str]] = []
    excluded = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in CALL_RE.finditer(line):
            module, name = match.group(1), match.group(2)
            if module in modules and name != "py":
                kept.append((lineno, module, name))
            else:
                excluded += 1
    return kept, excluded


def scan_tree(root: Path, modules: set[str]) -> dict[str, tuple[list, int]]:
    """Per consumer directory: (list of (relpath, line, module, name), excluded)."""
    result: dict[str, tuple[list, int]] = {}
    for dirname in CONSUMER_DIRS:
        calls: list[tuple[str, int, str, str]] = []
        excluded_total = 0
        directory = root / dirname
        if directory.exists():
            for md_path in sorted(directory.rglob("*.md")):
                text = md_path.read_text(encoding="utf-8", errors="replace")
                kept, excluded = find_calls(text, modules)
                rel = md_path.relative_to(root).as_posix()
                calls.extend((rel, ln, m, n) for ln, m, n in kept)
                excluded_total += excluded
        result[dirname] = (calls, excluded_total)
    return result


def resolves(module: str, name: str) -> bool:
    try:
        mod = importlib.import_module(module)
    except ImportError:  # an unimportable module cannot resolve any name
        return False
    return hasattr(mod, name)


def unresolved(calls: list[tuple[str, int, str, str]]) -> list[tuple[str, int, str, str]]:
    return [c for c in calls if not resolves(c[2], c[3])]


def key_of(rel: str, module: str, name: str) -> str:
    return f"{rel}: {module}.{name}"


def all_misses(root: Path = PLUGIN_ROOT) -> list[tuple[str, int, str, str]]:
    misses: list[tuple[str, int, str, str]] = []
    for calls, _ in scan_tree(root, script_modules()).values():
        misses.extend(unresolved(calls))
    return misses


@functools.cache
def real_tree_misses() -> tuple[tuple[str, int, str, str], ...]:
    """One scan of the real tree, shared by every real-tree test."""
    return tuple(all_misses())


def miss_keys(misses) -> set[str]:
    return {key_of(m[0], m[2], m[3]) for m in misses}


def unexempted(misses, exemptions: dict[str, str]) -> list[tuple[str, int, str, str]]:
    """The production check: misses no exemption holds."""
    return [m for m in misses if key_of(m[0], m[2], m[3]) not in exemptions]


def stale_exemptions(misses, exemptions: dict[str, str]) -> list[str]:
    """The production check: exemptions whose call now resolves or is gone."""
    return sorted(set(exemptions) - miss_keys(misses))


# ---- Controls -------------------------------------------------------------


def test_positive_control_real_function_resolves(tmp_path):
    handlers = tmp_path / "handlers"
    handlers.mkdir()
    (handlers / "x.md").write_text(
        "Run `markdown_parser.normalize_id(value)` first.\n", encoding="utf-8"
    )
    tree = scan_tree(tmp_path, script_modules())
    calls = tree["handlers"][0]
    assert calls == [("handlers/x.md", 1, "markdown_parser", "normalize_id")]
    assert unresolved(calls) == []


def test_mutation_control_misspelled_function_is_flagged(tmp_path):
    handlers = tmp_path / "handlers"
    handlers.mkdir()
    (handlers / "x.md").write_text(
        "Run `markdown_parser.normalize_idd(value)` first.\n", encoding="utf-8"
    )
    calls = scan_tree(tmp_path, script_modules())["handlers"][0]
    assert [c[2:] for c in unresolved(calls)] == [("markdown_parser", "normalize_idd")]


def test_non_script_module_and_file_name_hits_are_excluded():
    kept, excluded = find_calls(
        "os.path.join( and `json.dumps(x)` and markdown_parser.py( here\n",
        script_modules(),
    )
    assert kept == []
    assert excluded >= 1


def test_every_consumer_directory_was_scanned():
    missing = [d for d in CONSUMER_DIRS if not (PLUGIN_ROOT / d).is_dir()]
    assert missing == [], f"consumer directories absent from the plugin tree: {missing}"
    tree = scan_tree(PLUGIN_ROOT, script_modules())
    assert set(tree) == set(CONSUMER_DIRS)
    assert sum(len(c) for c, _ in tree.values()) > 0, "scan saw no module calls at all"


# ---- Real tree ------------------------------------------------------------


def test_every_cited_module_call_resolves_or_is_exempt():
    misses = unexempted(real_tree_misses(), UNRESOLVED_CALLS)
    listing = "\n".join(f"{rel}:{line} {mod}.{name}" for rel, line, mod, name in misses)
    assert not misses, f"unresolved module.name( calls:\n{listing}"


def test_unresolved_exemptions_are_not_stale():
    stale = stale_exemptions(real_tree_misses(), UNRESOLVED_CALLS)
    assert not stale, f"exemptions whose call now resolves or whose line is gone: {stale}"


def test_every_exemption_names_an_owner():
    assert [k for k, owner in UNRESOLVED_CALLS.items() if not owner.strip()] == []


def test_stale_check_fires_on_a_planted_exemption():
    """Direction dry-run through the production helpers: a planted exemption for
    a call that resolves is stale, and a planted miss with no exemption is new."""
    planted = {"handlers/x.md: markdown_parser.normalize_id": "owner"}
    assert stale_exemptions(real_tree_misses(), planted) == list(planted)
    fake_miss = [("handlers/x.md", 1, "markdown_parser", "normalize_idd")]
    assert unexempted(fake_miss, {}) == fake_miss
    assert stale_exemptions(fake_miss, {key_of("handlers/x.md", "markdown_parser", "normalize_idd"): "o"}) == []
