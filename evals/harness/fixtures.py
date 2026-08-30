"""Fixture engine: named builders that hand a case a ready-made directory,
plus the derivation helpers family sprints extend.

Two bases, both built under the scratch root's containment (see
`scratch.py`):

* "empty" -- `fx-empty-contained`: a fresh, empty case dir. No template, no
  fixture machinery -- the containment base every smoke case runs on.
* "template" -- `fx-initialized`: a full driven-init tree, built ONCE per
  suite run by shelling out to `/planwise init` with every value injected
  explicitly (name / root / dirs / scope / tier / token-saver), never by
  relying on an unforced auto-init default (that default is
  non-deterministic and is never a fixture-construction mechanism). The
  build is trusted only after its write set matches the pinned 10-path set
  by set equality; each consuming case then gets its own `copytree` of the
  trusted template.

Registering a new derived fixture is one call to `derive()` -- no engine
edits.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Callable

import yaml

from . import envelope as envelope_mod
from . import invoke
from .scratch import ScratchRoot

FixtureBuilder = Callable[[ScratchRoot], Path]
MutationFn = Callable[[Path], None]

FIXTURES: dict[str, FixtureBuilder] = {}

# Build-once-per-run cache for the driven-init template, keyed by
# `scratch.run_id` so two ScratchRoot instances never share a template.
_TEMPLATE_CACHE: dict[str, Path] = {}


class FixtureBuildError(RuntimeError):
    """A fixture failed to build honestly and must not be trusted."""


# The relative paths a correctly driven `/planwise init` writes into a
# freshly initialized project. The template build below is trusted only
# when its write set matches this one EXACTLY, by set equality -- a subset
# or a superset both mean the pinned seed drifted without the harness
# noticing.
INIT_WRITE_SET = frozenset({
    ".claude/settings.json",
    ".claude/rules/planwise/agent-authoring.md",
    ".claude/rules/planwise/artifact-self-containment.md",
    ".claude/rules/planwise/rule-authoring.md",
    ".claude/rules/planwise/skill-authoring.md",
    "planwise/config.yaml",
    "planwise/Backlog/00-Index-Backlog.md",
    "planwise/LessonsLearned/00-Index-LessonsLearned.md",
    "planwise/Plans/00-Index-Plans.md",
    "planwise/LessonsLearned/00-Categorization-By-Domain.md",
})


def _init_prompt(
    name: str, root: Path, dirs: str, scope: str, init_tier: str, token_saver: str,
) -> str:
    """The explicitly driven init command -- every value injected, never an
    interactive default and never the unforced auto-init branch (that
    branch is non-deterministic and is never a fixture-construction
    mechanism; see the lifecycle contract this engine implements).
    """
    return (
        f'/planwise init --name "{name}" --root "{root}" --dirs "{dirs}" '
        f'--scope "{scope}" --tier "{init_tier}" --token-saver "{token_saver}"'
    )


def _get_or_build_template(scratch: ScratchRoot) -> Path:
    """Build the `fx-initialized` template once per run, or return the
    cached build from an earlier fixture in this same run.
    """
    cached = _TEMPLATE_CACHE.get(scratch.run_id)
    if cached is not None:
        return cached

    if scratch.plugin_copy is None:
        raise FixtureBuildError(
            "scratch.copy_plugin_subtree() must run before the initialized "
            "template is built -- its --plugin-dir must be the scratch "
            "plugin copy, never the live tree"
        )

    template_dir = scratch.root / "fx-initialized-template"
    if template_dir.exists():
        raise FixtureBuildError(f"template dir already exists: {template_dir}")
    template_dir.mkdir(parents=True)

    prompt = _init_prompt(
        name="planwise-eval-fixture", root=template_dir, dirs="standard",
        scope="project", init_tier="standard", token_saver="off",
    )

    result = invoke.run_case(
        prompt=prompt, plugin_dir=scratch.plugin_copy, cwd=template_dir, tier="T4",
    )
    if result.outcome != "ok":
        raise FixtureBuildError(
            f"initialized-template build failed to capture: outcome={result.outcome!r}"
        )

    envelope = envelope_mod.parse(result.stdout)
    if envelope.outcome != "ok":
        raise FixtureBuildError(
            f"initialized-template build produced a bad envelope: outcome={envelope.outcome!r}"
        )
    if envelope.result_event and envelope.result_event.get("is_error"):
        raise FixtureBuildError("initialized-template build reported is_error:true")

    written = {
        str(path.relative_to(template_dir)).replace("\\", "/")
        for path in template_dir.rglob("*") if path.is_file()
    }
    if written != INIT_WRITE_SET:
        raise FixtureBuildError(
            "initialized-template write set mismatch: "
            f"missing={sorted(INIT_WRITE_SET - written)} "
            f"extra={sorted(written - INIT_WRITE_SET)}"
        )

    _TEMPLATE_CACHE[scratch.run_id] = template_dir
    return template_dir


def _build_empty(scratch: ScratchRoot, name: str) -> Path:
    """The containment base: a fresh, empty case dir."""
    case_dir = scratch.new_case_dir(f"{name}-{uuid.uuid4().hex[:8]}")
    case_dir.mkdir(parents=True)
    return case_dir


def _build_from_template(scratch: ScratchRoot, name: str) -> Path:
    """A fresh copy of the build-once-per-run driven-init template."""
    template_dir = _get_or_build_template(scratch)
    case_dir = scratch.new_case_dir(f"{name}-{uuid.uuid4().hex[:8]}")
    shutil.copytree(template_dir, case_dir)
    return case_dir


_BASE_BUILDERS: dict[str, Callable[[ScratchRoot, str], Path]] = {
    "empty": _build_empty,
    "template": _build_from_template,
}


def derive(name: str, base: str, mutation: MutationFn | None = None) -> FixtureBuilder:
    """Register a fixture: `base` ("empty" or "template") plus an optional
    mutation applied to the freshly built case dir. Registering a new
    fixture is exactly one call to this function -- the engine (dir naming,
    existence assertion, teardown registration) needs no changes.
    """
    try:
        base_builder = _BASE_BUILDERS[base]
    except KeyError as exc:
        raise ValueError(
            f"unknown fixture base {base!r}; expected one of {sorted(_BASE_BUILDERS)}"
        ) from exc

    def builder(scratch: ScratchRoot) -> Path:
        case_dir = base_builder(scratch, name)
        if mutation is not None:
            mutation(case_dir)
        return case_dir

    FIXTURES[name] = builder
    return builder


# -- Generic mutation helpers for later sprints' derivations -----------------

def mutate_yaml_key(rel_path: str, key: str, value) -> MutationFn:
    """Set one top-level key in a YAML file relative to the case dir. A
    full parse + re-serialize is fine here -- fixture-owned config files
    may be freely rewritten; comment-preserving line splicing is not
    required.
    """
    def _mutate(case_dir: Path) -> None:
        target = case_dir / rel_path
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        data[key] = value
        target.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return _mutate


def mutate_delete(rel_path: str) -> MutationFn:
    """Remove one file relative to the case dir, if present."""
    def _mutate(case_dir: Path) -> None:
        target = case_dir / rel_path
        if target.exists():
            target.unlink()
    return _mutate


def mutate_write_bytes(rel_path: str, content: bytes) -> MutationFn:
    """Write raw bytes to a file relative to the case dir. Byte-pinned on
    purpose -- a helper built on text writes cannot reliably reproduce or
    detect a newline rewrite, so any case asserting byte-level or
    line-ending behavior needs this, not a text write.
    """
    def _mutate(case_dir: Path) -> None:
        target = case_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return _mutate


# -- S01's own two fixtures ---------------------------------------------------

derive("fx-empty-contained", base="empty")
derive("fx-initialized", base="template")
