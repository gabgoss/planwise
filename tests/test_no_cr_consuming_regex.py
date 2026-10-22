"""No shipped script regex may let a value match swallow the carriage return.

A pattern that ends a value token (`.*`, `.+`, `.*?`, `.+?`), then any closing
groups, directly before `\\r?$` consumes the `\\r` of a CRLF line into the
captured value. The safe form is `[^\\r\\n]*`. The scan parses every
`scripts/*.py` with `ast`, collects the pattern of each `re.*` call (a string
literal, or a module-level constant the first argument names) and applies a
regex over the pattern text.

KNOWN_HITS is a ratchet, not an exemption: the test fails on any hit outside
the set and on a set member that no longer hits. Each member is routed to the
owner for a fix and is removed from the set when fixed.

`SCRIPTS_DIR_OVERRIDE` repoints the scan at another directory (used by the
must-fail controls).
"""
import ast
import os
import re
from pathlib import Path

import pytest

SCRIPTS = Path(
    os.environ.get("SCRIPTS_DIR_OVERRIDE")
    or Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
)

RE_FUNCS = {
    "compile", "match", "search", "fullmatch", "sub", "findall", "finditer",
    "subn", "split",
}

# A value token, any closing groups, then \r?$ at the end of the pattern text.
BAD = re.compile(r"(?:\.\*\??|\.\+\??)\)*\\r\?\$$")

# (file name, pattern text) measured at the session base and routed to the
# owning session as a production finding.
KNOWN_HITS = {
    ("migrate_plans_ledger.py", r"^- ([^:\n]+): ?(.*?)\r?$"),
}
if os.environ.get("SCRIPTS_DIR_OVERRIDE"):
    KNOWN_HITS = set()  # a control directory carries no recorded baseline


def _str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_re_call(node):
    f = node.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr in RE_FUNCS
        and isinstance(f.value, ast.Name)
        and f.value.id == "re"
    )


def scan_file(path):
    """Return (patterns_scanned, via_constant, hits) for one file.

    hits is a list of (line, pattern).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    consts = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if not isinstance(target, ast.Name):
                continue
            val = _str(stmt.value)
            call = stmt.value
            if val is None and isinstance(call, ast.Call) and _is_re_call(call) and call.args:
                val = _str(call.args[0])
            if val is not None:
                consts[target.id] = val
    scanned = 0
    via_const = 0
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_re_call(node) and node.args):
            continue
        first = node.args[0]
        pattern = _str(first)
        if pattern is None and isinstance(first, ast.Name) and first.id in consts:
            pattern = consts[first.id]
            via_const += 1
        if pattern is None:
            continue
        scanned += 1
        if BAD.search(pattern):
            hits.append((node.lineno, pattern))
    return scanned, via_const, hits


def scan_all(directory=None):
    directory = directory or SCRIPTS
    files = sorted(directory.glob("*.py"))
    scanned = 0
    via_const = 0
    hits = []
    for path in files:
        s, c, h = scan_file(path)
        scanned += s
        via_const += c
        hits += [(path.name, line, pat) for line, pat in h]
    return len(files), scanned, via_const, hits


def test_the_scan_sees_files_and_patterns():
    # An empty glob or an empty pattern set would pass vacuously.
    n_files, scanned, via_const, _ = scan_all()
    assert n_files > 0, SCRIPTS
    assert scanned > 0, "no regex pattern collected"
    assert via_const <= scanned, (via_const, scanned)


def test_a_constant_pattern_is_resolved_and_reported_as_a_hit(tmp_path):
    # Control for the constant-resolution path: the call names the pattern.
    (tmp_path / "const_mod.py").write_text(
        'import re\n_PAT = r"^key: (.*)\\r?$"\nre.compile(_PAT)\n',
        encoding="utf-8", newline="\n",
    )
    scanned, via_const, hits = scan_file(tmp_path / "const_mod.py")
    assert (scanned, via_const) == (1, 1)
    assert [h[0] for h in hits] == [3]


def test_no_regex_ends_a_value_match_before_cr_dollar():
    _, _, _, hits = scan_all()
    found = {(name, pat) for name, _, pat in hits}
    new = sorted(
        f"{name}:{line}: {pat}" for name, line, pat in hits
        if (name, pat) not in KNOWN_HITS
    )
    assert not new, "CR-consuming regex (use [^\\r\\n]*): " + "; ".join(new)
    stale = sorted(KNOWN_HITS - found)
    assert not stale, f"KNOWN_HITS member no longer hits, remove it: {stale}"


@pytest.mark.parametrize("pattern,expect", [
    (r"(.*)\r?$", True),
    (r"^key: (.*)\r?$", True),
    (r"^key: (.+?)\r?$", True),
    (r"^key: ((.*))\r?$", True),
    (r"^key: ([^\r\n]*)\r?$", False),
    (r"^key: (.*)$", False),
])
def test_predicate_discriminates(pattern, expect):
    assert bool(BAD.search(pattern)) is expect
