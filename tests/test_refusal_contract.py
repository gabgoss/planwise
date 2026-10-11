"""The refusal contract: every migration refusal names an edit that closes it.

`Refusal(reason, fix=None, *, question=None)` splits a reason written as
"<reason> -- <fix>" on the last separator and raises TypeError when no fix
remains. An AST walk over every script under scripts/ fails on any call that
would reach that TypeError at run time, so a future fixless call is caught
before it ships. Fixtures are written as bytes under tmp_path, never under
plugins/planwise/."""
import ast
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import migrate_backlog_index as mig
import migrate_backlog_support as sup
import migrate_lessons_support as lsup

NO_GIT = "--allow-untracked-tree"
ALL_FLAGS = ("--backfill-frontmatter", "--write-edges", "--extract-dependency-notes", "--reconcile", "index-wins")
HEADER = "| ID | Feature | Priority | Status | Created | Blocks | Files |\n|---|---|---|---|---|---|---|\n"
FOOTER = "*Last Updated: 2024-01-01 — did something. Prior entry: 2023-12-01 — did something else.*\n"
NAMES = {"001": "ITM-001-SMP-First.md", "002": "ITM-002-SMP-Second.md"}
TITLES = {"001": "First sample item", "002": "Second sample item"}
DEPS_TABLE = "## Dependencies\n\n| ID | Blocks |\n|---|---|\n| 001 | 002 |\n\n"


def fm(item_id, blocks="[]"):
    keys = {"id": item_id, "title": f'"{TITLES[item_id]}"', "priority": "High", "status": "NOT_STARTED",
            "abbrev": "SMP", "created": "2024-01-01", "blocks": blocks}
    return "\n".join(["---"] + [f"{k}: {v}" for k, v in keys.items()] + ["---", ""]) + "\n"


def item(item_id, head=None, body="Body text."):
    return (fm(item_id) if head is None else head) + f"# {TITLES[item_id]}\n\n{body}\n"


def row(item_id, blocks=""):
    cells = [item_id, TITLES[item_id], "High", "NOT_STARTED", "2024-01-01", blocks, f"[{item_id}]({NAMES[item_id]})"]
    return "| " + " | ".join(cells) + " |\n"


def index(*rows, deps=""):
    return f"# Backlog Index\n\n## Backlog Items\n\n{HEADER}{''.join(rows)}\n{deps}{FOOTER}"


def project(tmp_path, index_text, items):
    planwise = tmp_path / "proj" / "planwise"
    backlog = planwise / "Backlog"
    (backlog / "Archive").mkdir(parents=True)
    for item_id, text in items.items():
        (backlog / NAMES[item_id]).write_bytes(text.encode("utf-8"))
    (planwise / "config.yaml").write_bytes(b'project:\n  name: "test-project"\n  backlog_dir: "Backlog"\n'
                                           b'  index_files:\n    backlog: "00-Index-Backlog.md"\n')
    (backlog / "00-Index-Backlog.md").write_bytes(index_text.encode("utf-8"))
    return planwise / "config.yaml"


# --------------------------------------------------------------------------
# The AST rule
# --------------------------------------------------------------------------

UNKNOWN = "\x00"


def ordered_text(node) -> str:
    """The text `node` renders, in order, with UNKNOWN standing for each part whose
    text is not a constant. A Name, Call, Subscript or IfExp is unknown: only one
    branch of a conditional runs, and a variable's text is not known."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else UNKNOWN
                       for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return ordered_text(node.left) + ordered_text(node.right)
    return UNKNOWN


def has_constant_fix(node) -> bool:
    """True when the LAST " -- " is followed by at least one non-whitespace character
    of constant text, so the split the class makes leaves a fix the call wrote."""
    text = ordered_text(node)
    at = text.rfind(" -- ")
    return at >= 0 and bool(text[at + 4:].replace(UNKNOWN, "").strip())


def call_name(node: ast.Call):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def refusal_calls(source: str) -> list:
    """Every Refusal or RefusalSet call in `source` as (lineno, passes)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node)
        if name == "RefusalSet":
            found.append((node.lineno, True))
        elif name == "Refusal":
            if len(node.args) >= 2 or any(kw.arg == "fix" for kw in node.keywords):
                ok = True
            elif len(node.args) == 1:
                ok = has_constant_fix(node.args[0])
            else:
                ok = False
            found.append((node.lineno, ok))
    return found


def violations_in(source: str) -> list:
    """The line numbers of every Refusal call that would lack a fix at run time."""
    return sorted(lineno for lineno, ok in refusal_calls(source) if not ok)


def test_every_refusal_call_carries_a_fix():
    files = sorted(SCRIPTS.glob("*.py"))
    bad, sites, with_sites = [], 0, 0
    for path in files:
        calls = refusal_calls(path.read_text(encoding="utf-8"))
        sites += len(calls)
        with_sites += bool(calls)
        bad += [f"{path.name}:{lineno}" for lineno, ok in calls if not ok]
    assert sites >= 40 and with_sites >= 6, f"blind walk: {sites} call sites in {with_sites} files of {len(files)}"
    assert not bad, f"{len(bad)} Refusal call(s) with no fix:\n" + "\n".join(bad)


SHAPES = [
    ('Refusal(f"a {x} -- b")', []),
    ('Refusal(f"a {x}")', [1]),
    ('Refusal(f"x -- {exc}")', [1]),
    ('Refusal(f"x -- fix {y}")', []),
    ('Refusal("a" + x + " -- b")', []),
    ('Refusal("a" + (x if c else " -- b"))', [1]),
    ("Refusal(detail)", [1]),
    ("Refusal(detail, fix=F)", []),
    ('Refusal("a", "b")', []),
    ("RefusalSet(items)", []),
    ("sup.RefusalSet(items)", []),
    ('sup.Refusal("a")', [1]),
    ('Refusal("\\n".join(x))', [1]),
]


def test_ast_rule_classifies_each_shape():
    wrong = [(snippet, violations_in(snippet), expected) for snippet, expected in SHAPES
             if violations_in(snippet) != expected]
    assert not wrong, wrong


# --------------------------------------------------------------------------
# The class
# --------------------------------------------------------------------------

def test_split_round_trips():
    one = sup.Refusal("a -- b")
    assert (one.reason, one.fix, str(one)) == ("a", "b", "a -- b")
    two = sup.Refusal("a -- b -- c")
    assert (two.reason, two.fix, str(two)) == ("a -- b", "c", "a -- b -- c")
    explicit = sup.Refusal("a", "b", question={"id": "q"})
    assert (explicit.reason, explicit.fix, explicit.question) == ("a", "b", {"id": "q"})


def test_missing_fix_raises():
    with pytest.raises(TypeError):
        sup.Refusal("no fix here")


def test_refusal_set_keeps_its_message_and_exposes_fix():
    refusal = lsup.RefusalSet([(lsup.FIX_LOG_ROW, "row at line 3")])
    expected = ("1 refusal(s); nothing was written. Each group names what closes it:\n"
                f"{lsup.FIX_LOG_ROW} (1):\n  - row at line 3")
    assert str(refusal) == expected
    assert refusal.reason == expected
    assert refusal.fix == lsup.FIX_LOG_ROW
    assert refusal.question is None
    assert isinstance(refusal, sup.Refusal)


def test_generator_refusal_keeps_the_error_in_the_reason(tmp_path):
    """With no hint to give, the generator's own message stays in `reason`, never in `fix`."""
    import config_loader
    bare = "---\nid: 001\n---\n# First sample item\n\nBody text.\n"
    config_path = project(tmp_path, index(row("001")), {"001": bare})
    config = config_loader.load_config(Path(mig.__file__), config_path=config_path)
    with pytest.raises(sup.Refusal) as caught:
        mig.preflight_generator(config, config["_index_path"])
    exc = caught.value
    assert exc.reason.startswith("the generator would refuse this tree: ")
    assert "frontmatter" in exc.reason
    assert exc.fix == "correct the item file the message names so the generator accepts it, then re-run"


def test_reciprocal_fix_names_an_edit(tmp_path, monkeypatch, capsys):
    config_path = project(
        tmp_path, index(row("001", blocks="002"), row("002", blocks="001"), deps=DEPS_TABLE),
        {"001": item("001"), "002": item("002", head=fm("002", blocks="[001]"))})
    captured = []
    real = mig.plan_migration

    def spy(*args, **kwargs):
        try:
            return real(*args, **kwargs)
        except sup.Refusal as exc:
            captured.append(exc)
            raise

    monkeypatch.setattr(mig, "plan_migration", spy)
    monkeypatch.setattr(sys, "argv", ["migrate_backlog_index.py", "--config", str(config_path), NO_GIT,
                                      "--force", "--write", *ALL_FLAGS])
    assert mig.main() == 2
    capsys.readouterr()
    assert len(captured) == 1
    exc = captured[0]
    assert exc.fix != exc.reason
    assert "remove the other item's id" in exc.fix
