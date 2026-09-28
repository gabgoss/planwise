"""The `generate_lessons_index` facade must keep every name its callers
reach through it.

The facade re-exports its ten sibling modules, plus a few helpers it imports
from `generate_backlog_index`. A split that drops one of those imports still
passes every test that imports the sibling module directly. It fails only
when a caller reaches the name through the facade, and shipped handler text
does exactly that: `/planwise doctor`'s bookkeeping read-gate calls
`generate_lessons_index.is_generated_index_file` and
`generate_lessons_index._changelog_filename`.

Three checks. The pinned pair must resolve on the facade, be declared in its
`__all__`, and be the same objects `generate_backlog_index` defines. Every
`generate_lessons_index.<name>` that shipped markdown cites must resolve.
Every name a shipped script reads through the facade (an `import ... as`
alias attribute, or a `from generate_lessons_index import` name) must
resolve. The last two scan the shipped tree, so a new citation is covered
without editing this file.
"""
import ast
import re
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_backlog_index
import generate_lessons_index

FACADE = "generate_lessons_index"

# The two helpers the pre-split module imported from generate_backlog_index
# and that shipped text still calls through the facade.
PINNED_BACKLOG_HELPERS = ("is_generated_index_file", "_changelog_filename")

_DOC_CITATION_RE = re.compile(rf"\b{FACADE}\.([A-Za-z_][A-Za-z0-9_]*)")


def _doc_cited_names() -> list:
    """`(file, name)` for every `generate_lessons_index.<name>` in shipped
    markdown, skipping the `.py` file-name form."""
    hits = []
    for path in sorted(PLUGIN.rglob("*.md")):
        for name in _DOC_CITATION_RE.findall(path.read_text(encoding="utf-8")):
            if name != "py":
                hits.append((path.relative_to(PLUGIN).as_posix(), name))
    return hits


def _script_cited_names() -> list:
    """`(file, name)` for every name a shipped script reads through the
    facade: attributes of an `import generate_lessons_index as X` alias,
    and names in a `from generate_lessons_index import ...`."""
    hits = []
    for path in sorted(SCRIPTS.glob("*.py")):
        if path.stem == FACADE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                aliases.update(a.asname or a.name for a in node.names if a.name == FACADE)
            elif isinstance(node, ast.ImportFrom) and node.module == FACADE:
                hits.extend((path.name, a.name) for a in node.names)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id in aliases):
                hits.append((path.name, node.attr))
    return sorted(set(hits))


@pytest.mark.parametrize("name", PINNED_BACKLOG_HELPERS)
def test_pinned_backlog_helper_is_re_exported_by_the_facade(name):
    assert hasattr(generate_lessons_index, name), f"{FACADE} no longer exposes {name}"
    assert name in generate_lessons_index.__all__, f"{name} is missing from {FACADE}.__all__"
    assert getattr(generate_lessons_index, name) is getattr(generate_backlog_index, name)


def test_the_citation_scans_see_their_subjects():
    # An empty scan would pass the two tests below vacuously.
    doc_names = {name for _f, name in _doc_cited_names()}
    assert set(PINNED_BACKLOG_HELPERS) <= doc_names, doc_names
    assert _script_cited_names(), "no shipped script reads through the facade"


def test_every_markdown_citation_resolves_on_the_facade():
    missing = [(f, n) for f, n in _doc_cited_names() if not hasattr(generate_lessons_index, n)]
    assert not missing, f"cited in shipped markdown but absent from {FACADE}: {missing}"


def test_every_script_read_through_the_facade_resolves():
    missing = [(f, n) for f, n in _script_cited_names() if not hasattr(generate_lessons_index, n)]
    assert not missing, f"read through {FACADE} by a shipped script but absent: {missing}"
