#!/usr/bin/env python3
"""Read-only preflight for `/planwise plan`: the add-on lines of the plan card.

The skill router reads config.yaml once, prints the eight Config Gate lines,
then imports this module lazily for the `plan` subcommand only and appends
`card_lines(config_path, config, plans_path)` before the end marker. The card
holds every value a plan session would otherwise spend tool calls computing:

- `context.plan_authoring` and the effective `token_saver` value from config;
- `index_shape: any_legacy=<bool>`, from the index-shape preflight run in-process;
- `abbreviations_in_use`, the sorted abbreviations of the plans index rows and
  of every `*Master-Plan.md` file and `Meta-{Abbrev}` folder under the plans
  directory, or `(unavailable: <reason>)` when the index cannot be read;
- `fill_inventory`, per template kind, the distinct FILL marker names the
  scaffold renderer emits for a one-of-each spec with no optional sections;
- a `NEXT:` block for the configured authoring mode (`inline` or `delegated`),
  plus what is already done and what not to do.

Each add-on field fails on its own: a failed field prints
`<field>: (unavailable: <ExcType>)` and the card then prints no NEXT block.
When any index is hand-authored, the card prints one index-gate line in place
of the NEXT block. It never writes and never prompts, and nothing it calls
reaches stderr.
"""

import contextlib
import io
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

FILL_MARKER_RE = re.compile(r"<!-- FILL: \{(.+?)\} -->")
ABBREV = r"[A-Z][A-Z0-9]{1,5}"
MASTER_PLAN_RE = re.compile(rf"^(?:Meta-)?({ABBREV})(?:-META)?-Master-Plan\.md$")
META_FOLDER_RE = re.compile(rf"^Meta-({ABBREV})$")
NEXT_DONE = ("the config, index gate and abbreviations above are already resolved: "
             "do not re-read config.yaml or the plans index")
NEXT_DONE_NO_ABBREVS = ("the config and index gate above are already resolved: do not re-read config.yaml; "
                        "abbreviations_in_use is unavailable, so check the plans index and plans folder "
                        "for a clash before you choose an abbreviation")
NEXT_TOOL = ("when mcp__planwise__build_plan is listed, call it for keys, lint and build instead of the "
             "python commands, and fall back to them if it is not listed or refuses the call")
NEXT_WORKFLOW = ("when the Workflow tool is listed, ask the opt-in question in the plan handler before step 4, "
                 "and on a yes run the /planwise:plan-bodies workflow through the Workflow tool "
                 "in place of the per-session dispatches")
NEXT_NO_TEMPLATE = "do not Read a template"
NEXT_NO_TEMPLATE_DELEGATED = "do not Read a template other than templates/plan-notes.md"
NEXT_NO_TASK_FILE = "do not Write a task file; write bodies"
INDEX_GATE_FIRST = ("INDEX GATE FIRST: the {names} index is hand-authored. Run the index-shape gate in "
                    "references/index-shape-gate.md before any write. Nothing above is resolved for building, "
                    "so this card prints no NEXT block")
NO_NEXT_AFTER_FAILURE = ("CARD INCOMPLETE: a card field above is unavailable, so this card prints no NEXT block. "
                         "Follow the plan handler's steps")

# One sprint, one session, one task, no optional sections: the smallest spec the
# renderer accepts. Every template kind renders once, so each kind's FILL names show.
INVENTORY_SPEC = {
    "plan_name": "Inventory", "abbrev": "INV", "created": "2000-01-01", "ordering": "sequential",
    "sprints": [{"number": 1, "name": "One", "purpose": "inventory", "sessions": [{
        "number": 1, "name": "One", "objective": "inventory", "mode": "DIRECT", "prerequisite": "none",
        "tasks": [{"number": 1, "name": "One", "title": "inventory", "agent": "Sonnet", "estimate_k": 1,
                   "depends_on": [], "outputs": ["inventory.md"],
                   "required_context": [{"priority": "P0", "path": "inventory.md", "kib": 1,
                                         "tokens_k": 1, "purpose": "inventory"}]}]}]}],
}


class Unavailable(Exception):
    """A field value the card cannot resolve, with the reason it prints."""


def _flag(value: bool) -> str:
    return "true" if value else "false"


def authoring_fields(config: dict) -> tuple[str, str]:
    """(`context.plan_authoring`, effective `token_saver`) from the config accessors."""
    import config_loader

    mode = config_loader.get_token_saver_extension_config(config)["plan_authoring"]
    saver = config_loader.get_effective_token_saver_config(config)["token_saver"]
    return mode, _flag(saver)


def index_shapes(config: dict) -> dict[str, str]:
    """Each index family's shape, from the index-shape preflight's `inspect`, in-process."""
    import index_shape_preflight as isp

    return {name: isp.inspect(config, key, classify, report_fn, False)["shape"]
            for name, key, classify, report_fn in isp.FAMILIES}


def index_abbreviations(config: dict, plans_shape: str) -> set[str]:
    """The Abbrev cells of a generated plans index. Raises `Unavailable` with the reason otherwise."""
    from generate_plans_index import TABLE_HEADER

    if plans_shape != "generated":
        raise Unavailable(f"{plans_shape} index")
    lines = Path(config["_plans_index"]).read_bytes().decode("utf-8-sig").replace("\r\n", "\n").split("\n")
    if TABLE_HEADER not in lines:
        raise Unavailable("index table header not found")
    found = set()
    for line in lines[lines.index(TABLE_HEADER) + 2:]:  # the header, then the separator row
        if not line.startswith("|"):
            break
        cell = line.strip().strip("|").split("|")[0].strip()
        if cell:
            found.add(cell)
    return found


def folder_abbreviations(plans_dir: Path) -> set[str]:
    """The `{Abbrev}` of every `*Master-Plan.md` file and `Meta-{Abbrev}` folder under the plans directory."""
    found = set()
    if not plans_dir.is_dir():
        return found
    for path in plans_dir.rglob("*Master-Plan.md"):
        match = MASTER_PLAN_RE.match(path.name)
        if match:
            found.add(match.group(1))
    for path in plans_dir.rglob("Meta-*"):
        match = META_FOLDER_RE.match(path.name)
        if path.is_dir() and match:
            found.add(match.group(1))
    return found


def fill_inventory() -> dict[str, int]:
    """Per template kind, the distinct FILL marker names the scaffold renderer emits."""
    import scaffold_plan

    files, _rec = scaffold_plan.render_all(INVENTORY_SPEC)
    names: dict[str, set] = {kind: set() for kind in scaffold_plan.TEMPLATE_FILES}
    for rel, text in files.items():
        kind = scaffold_plan.file_kind(Path(rel).name)
        if kind in names:
            names[kind].update(FILL_MARKER_RE.findall(text))
    return {kind: len(found) for kind, found in names.items()}


def next_block(mode: str, config_path: Path, plans_path: str, abbrevs_known: bool) -> list[str]:
    """The numbered steps of the plan handler's default path for `mode`, then the done and do-not lines."""
    script = (SCRIPTS / "plan_build.py").as_posix()
    keys = f'python -B "{script}" keys --spec <spec.json>'
    lint = f'python -B "{script}" lint --spec <spec.json> --bodies-dir <bodies-dir>'
    build = (f'python -B "{script}" build --spec <spec.json> --bodies-dir <bodies-dir> '
             f'--out "{plans_path}/<PlanName>" --config "{Path(config_path).as_posix()}"')
    plan_bodies = "<bodies-dir>/{Abbrev}-bodies-plan.md"
    if mode == "delegated":
        steps = [
            keys,
            f"Write {plan_bodies} inline (the MASTER and sprint documents)",
            "Write <bodies-dir>/{Abbrev}-PlanNotes.md from templates/plan-notes.md",
            ("for each session in order, dispatch planwise:plan-author once (Agent tool, "
             "run_in_background: false), writing <bodies-dir>/{Abbrev}-bodies-S{XX}-{YY}.md"),
            f"{lint}   (repeat until exit 0)",
            build,
        ]
        no_template = NEXT_NO_TEMPLATE_DELEGATED
        workflow = [NEXT_WORKFLOW]
    else:
        steps = [
            keys,
            (f"Write {plan_bodies} and one <bodies-dir>/{{Abbrev}}-bodies-S{{XX}}-{{YY}}.md per session, "
             "from the keys output"),
            f"{lint}   (repeat until exit 0)",
            build,
        ]
        no_template = NEXT_NO_TEMPLATE
        workflow = []
    return [
        f"NEXT: {mode}",
        *(f"{n}. {step}" for n, step in enumerate(steps, 1)),
        NEXT_TOOL,
        *workflow,
        NEXT_DONE if abbrevs_known else NEXT_DONE_NO_ABBREVS,
        no_template,
        NEXT_NO_TASK_FILE,
    ]


def _unavailable(field: str, exc: BaseException) -> str:
    reason = str(exc) if isinstance(exc, Unavailable) else type(exc).__name__
    return f"{field}: (unavailable: {reason})"


def card_lines(config_path: Path, config: dict, plans_path: str) -> list[str]:
    """The card lines after the eight Config Gate lines. Never raises for a field failure."""
    with contextlib.redirect_stderr(io.StringIO()):  # stderr would merge into the injected text
        return _card_lines(config_path, config, plans_path)


def _card_lines(config_path: Path, config: dict, plans_path: str) -> list[str]:
    lines, failed = [], False
    mode = None
    try:
        mode, saver = authoring_fields(config)
        lines += [f"context.plan_authoring: {mode}", f"token_saver: {saver}"]
    except Exception as exc:  # noqa: BLE001 - a field fails on its own
        lines += [_unavailable("context.plan_authoring", exc), _unavailable("token_saver", exc)]
        failed = True

    shapes = None
    try:
        shapes = index_shapes(config)
        detail = " ".join(f"{name}={shape}" for name, shape in shapes.items())
        legacy = [name for name, shape in shapes.items() if shape == "legacy"]
        lines.append(f"index_shape: any_legacy={_flag(bool(legacy))} ({detail})")
    except Exception as exc:  # noqa: BLE001
        lines.append(_unavailable("index_shape", exc))
        legacy, failed = [], True

    abbrevs_known = False
    try:
        if shapes is None:
            raise Unavailable("index shape unknown")
        found = index_abbreviations(config, shapes.get("plans", "absent"))
        found |= folder_abbreviations(Path(config["_plans_dir"]))
        lines.append(f"abbreviations_in_use: {', '.join(sorted(found)) if found else '(none)'}")
        abbrevs_known = True
    except Unavailable as exc:
        lines.append(_unavailable("abbreviations_in_use", exc))
    except Exception as exc:  # noqa: BLE001
        lines.append(_unavailable("abbreviations_in_use", exc))
        failed = True

    try:
        inventory = fill_inventory()
        lines.append("fill_inventory: " + " ".join(f"{kind}={n}" for kind, n in inventory.items()))
    except Exception as exc:  # noqa: BLE001
        lines.append(_unavailable("fill_inventory", exc))
        failed = True

    if legacy:
        lines.append(INDEX_GATE_FIRST.format(names=", ".join(legacy)))
    elif failed:
        lines.append(NO_NEXT_AFTER_FAILURE)
    else:
        lines += next_block(mode, config_path, plans_path, abbrevs_known)
    return lines
