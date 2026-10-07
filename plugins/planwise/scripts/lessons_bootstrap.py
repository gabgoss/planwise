"""Lessons-directory scaffolding: categorization schema + bootstrap routine.

Re-exports the fallback categorization schema (DEFAULT_CATEGORIZATION,
defined in generate_lessons_index), and owns the
00-Categorization-By-Domain.md seed, the categorization notes seed, and the
idempotent lessons-index + categorization seeding routine
(bootstrap_lessons_artifacts) that both fresh init and the upgrade-side
backfill path call through.
"""

import dataclasses
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from config_gen import (
        ConfigResult,
        InitConfig,
    )
except ImportError:
    raise ImportError(
        "config_gen is required for lessons_bootstrap's ConfigResult/InitConfig "
        "types; the scripts/ directory appears to be partially installed"
    )

try:
    from config_loader import resolve_index_name, resolve_index_target
except ImportError:
    raise ImportError(
        "config_loader is required for lessons_bootstrap's index-name and "
        "directory resolution; the scripts/ directory appears to be partially "
        "installed"
    )

try:
    from generate_backlog_index import _changelog_filename, _index_naming

    # DEFAULT_CATEGORIZATION is defined beside the companion renderer and
    # re-exported here under the same name for init_project and --migrate.
    from generate_lessons_index import (
        COMPANION_FILENAME,
        DEFAULT_CATEGORIZATION,
        NOTES_FILENAME,
        CategorizationError,
        _promotion_log_filename,
        has_categorization_block,
        render_companion_file,
    )
except ImportError:
    raise ImportError(
        "generate_backlog_index/generate_lessons_index are required for "
        "lessons_bootstrap's companion-filename derivation and companion "
        "rendering; the scripts/ directory appears to be partially installed"
    )


# The hand-written complement to the generated companion. Seeded once and
# never regenerated: curate appends classification edge cases and
# cross-cutting observations to it.
NOTES_SEED_CONTENT = (
    f"[← {COMPANION_FILENAME}]({COMPANION_FILENAME})\n"
    "\n"
    "# Lessons Learned — Categorization Notes\n"
    "\n"
    f"The bucket tables in {COMPANION_FILENAME} are generated from lesson "
    "frontmatter and regenerated whole on every write. This file holds the "
    "hand-written record that the generator never reads or writes: "
    "observations that span buckets, and the lessons whose bucket was a "
    "judgment call.\n"
    "\n"
    "## Cross-cutting observations\n"
    "\n"
    "## Classification edge cases\n"
    "\n"
    "| ID | Why it could fit elsewhere | Final bucket |\n"
    "|---|---|---|\n"
)


def render_categorization_file(cfg: "InitConfig") -> tuple[ConfigResult, str]:
    """Render 00-Categorization-By-Domain.md through the generator's own
    companion renderer (`generate_lessons_index.render_companion_file`),
    called as a library with an empty lesson set -- the same zero-lesson
    path `/planwise lessons curate`'s first `--companion --write` would
    take on a fresh project, so the seeded file and the first regenerated
    one are the identical shape.

    Idempotent — returns SKIPPED_EXISTS if the file already exists.
    Returns SKIPPED_NO_YAML if PyYAML is unavailable (the init handler's
    Step 5.1 fallback renders the file via Claude in that case).

    When the user's config has no `categorization:` block (or the block is
    empty), DEFAULT_CATEGORIZATION is the fallback config the renderer
    receives, and this returns CREATED_FROM_DEFAULT so the banner can flag
    it. The user can edit the buckets afterwards, or run `--migrate` to add
    the template block to their config for full customisation.
    """
    lessons_dir_rel, _ = resolve_index_target(cfg, "lessons")
    dst_rel = f"{lessons_dir_rel}/{COMPANION_FILENAME}"
    dst = cfg.project_root / dst_rel
    if dst.exists():
        return ConfigResult.SKIPPED_EXISTS, dst_rel

    if not HAS_YAML:
        return ConfigResult.SKIPPED_NO_YAML, dst_rel

    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    config_present = config_path.exists()
    full: dict = {}
    used_default = False

    if config_present:
        try:
            config_text = config_path.read_text(encoding="utf-8")
            loaded = yaml.safe_load(config_text) or {}
            if isinstance(loaded, dict):
                full = loaded
        except yaml.YAMLError:
            # Bad config — fall through to default, surface via banner.
            pass

    lessons_index = resolve_index_name(full, "lessons")

    if not has_categorization_block(full):
        full = dict(full)
        full["categorization"] = DEFAULT_CATEGORIZATION
        used_default = True

    if not isinstance(full.get("project"), dict) or not full["project"].get("name"):
        full = dict(full)
        full["project"] = {**(full.get("project") or {}), "name": cfg.project_name}

    naming = _index_naming(Path(lessons_index))
    try:
        rendered = render_companion_file([], full, naming)
    except CategorizationError:
        # The project's own block failed validation (a bucket without an
        # id, a duplicate id, an unresolved default_bucket or
        # decision_tree_order entry). Report it, never raise out of the
        # bootstrap.
        return ConfigResult.SKIPPED_BAD_CONFIG, dst_rel

    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dst, "x", encoding="utf-8") as f:
            f.write(rendered)
    except FileExistsError:
        return ConfigResult.SKIPPED_EXISTS, dst_rel
    return (
        ConfigResult.CREATED_FROM_DEFAULT if used_default else ConfigResult.CREATED,
        dst_rel,
    )


def render_categorization_notes_file(cfg: "InitConfig") -> tuple[ConfigResult, str]:
    """Seed 00-Categorization-Notes-LessonsLearned.md, the hand-written
    file the companion's footer links to, with NOTES_SEED_CONTENT.

    Idempotent — returns SKIPPED_EXISTS if the file already exists, and
    never overwrites it. Needs no config.yaml and no PyYAML: the seed has
    no project-specific content.
    """
    dst_rel = f"{cfg.planwise_root}/{cfg.lessons_dir}/{NOTES_FILENAME}"
    dst = cfg.project_root / dst_rel
    if dst.exists():
        return ConfigResult.SKIPPED_EXISTS, dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dst, "x", encoding="utf-8") as f:
            f.write(NOTES_SEED_CONTENT)
    except FileExistsError:
        return ConfigResult.SKIPPED_EXISTS, dst_rel
    return ConfigResult.CREATED, dst_rel


# The lessons index and its two generated-shape companions' SOURCE names in
# the plugin's own seed/ dir — these never change, regardless of what a
# project names its hub. In the same adjacency order copy_seed_files() uses
# for the backlog index + changelog pair: the hub first, then the files its
# own footer pointers name.
_LESSONS_SEED_SRC_NAMES = (
    "00-Index-LessonsLearned.md",
    "00-Changelog-LessonsLearned.md",
    "00-PromotionLog-LessonsLearned.md",
)


def _lessons_seed_dst_names(hub_name: str) -> tuple[str, str, str]:
    """Derive the on-disk destination filenames for the lessons hub and its
    two companions from `hub_name` (the project's configured
    `index_files.lessons`), through the SAME naming helpers
    `generate_lessons_index.py`'s own footer links use --
    `_index_naming`/`_changelog_filename` (from `generate_backlog_index`)
    and `_promotion_log_filename` (from `generate_lessons_index`) -- never
    re-implemented. A project seeding a custom hub name (e.g.
    `Lessons-Index.md`) then gets companions the generator's footer
    actually points at, instead of the fixed
    `00-Changelog-LessonsLearned.md` / `00-PromotionLog-LessonsLearned.md`
    pair. The seed SOURCE filenames in `_LESSONS_SEED_SRC_NAMES` are the
    plugin's own template names and never change.
    """
    naming = _index_naming(Path(hub_name))
    return hub_name, _changelog_filename(naming), _promotion_log_filename(naming)


def _seed_lessons_index(cfg: "InitConfig") -> list[tuple[ConfigResult, str]]:
    """Seed the lessons index and its changelog/promotion-log companions
    from the plugin seed dir, one file at a time, each independently
    idempotent. Mirrors copy_seed_files for the lessons artifacts alone, so
    the upgrade-side backfill can recreate whichever of the three is
    missing without re-seeding backlog/plans.

    Destination filenames are derived from the project's configured
    `index_files.lessons` via `_lessons_seed_dst_names` -- never the fixed
    default triple -- so a project with a custom hub name backfills
    companions under the names its own generator footer links to.

    Returns one (ConfigResult, dst_rel) pair per file in
    `_LESSONS_SEED_SRC_NAMES`, in that order. Each file independently
    reports SKIPPED_EXISTS when already present (never overwrites a
    populated file) or SKIPPED_NO_TEMPLATE when the plugin seed file is
    absent — a project already carrying the index but not yet the two
    companions backfills only the companions.
    """
    lessons_dir_rel, hub_name = resolve_index_target(cfg, "lessons")
    dst_names = _lessons_seed_dst_names(hub_name)
    results = []
    for src_name, dst_name in zip(_LESSONS_SEED_SRC_NAMES, dst_names):
        dst_rel = f"{lessons_dir_rel}/{dst_name}"
        dst = cfg.project_root / dst_rel
        if dst.exists():
            results.append((ConfigResult.SKIPPED_EXISTS, dst_rel))
            continue
        src = cfg.plugin_root / "seed" / src_name
        try:
            src_content = src.read_bytes()
        except FileNotFoundError:
            results.append((ConfigResult.SKIPPED_NO_TEMPLATE, dst_rel))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(dst, "xb") as f:
                f.write(src_content)
        except FileExistsError:
            results.append((ConfigResult.SKIPPED_EXISTS, dst_rel))
            continue
        results.append((ConfigResult.CREATED, dst_rel))
    return results


@dataclasses.dataclass
class LessonsBootstrap:
    """Outcome of bootstrap_lessons_artifacts, with banner-ready fields.

    Carries the per-artifact ConfigResult so each caller (fresh init / upgrade)
    can render its own banner from the same routine. `index_results` holds
    one (ConfigResult, dst_rel) pair per file in `_LESSONS_SEED_NAMES` — the
    hub plus its two companions — since each seeds independently.
    `notes_result`/`notes_rel` report the categorization notes seed the
    same way `cat_result`/`cat_rel` report the companion.
    """
    index_results: list[tuple[ConfigResult, str]]
    cat_result: ConfigResult
    cat_rel: str
    notes_result: ConfigResult
    notes_rel: str

    @property
    def created_any(self) -> bool:
        created = {ConfigResult.CREATED, ConfigResult.CREATED_FROM_DEFAULT}
        return (
            any(result in created for result, _ in self.index_results)
            or self.cat_result in created
            or self.notes_result in created
        )


def bootstrap_lessons_artifacts(cfg: "InitConfig") -> LessonsBootstrap:
    """Ensure the lessons scaffolding (index + companions + categorization
    file) exists.

    The single idempotent, non-destructive routine wired into BOTH fresh init
    and _run_upgrade(): each sub-step is a no-op when its file is already
    present (SKIPPED_EXISTS), so an already-complete project is left untouched
    and a user-customised file is preserved verbatim. On an upgrade-adopted
    project this backfills 00-Categorization-By-Domain.md — the file that
    gates /planwise lessons curate and promote-batch — which the legacy
    fresh-init-only render never created; it also backfills whichever of the
    lessons index's two companions (changelog, promotion log) a
    pre-companion project has not yet been given, and the categorization
    notes file the companion's footer links to.
    """
    index_results = _seed_lessons_index(cfg)
    cat_result, cat_rel = render_categorization_file(cfg)
    notes_result, notes_rel = render_categorization_notes_file(cfg)
    return LessonsBootstrap(index_results, cat_result, cat_rel, notes_result, notes_rel)


def _emit_lessons_bootstrap_banner(boot: "LessonsBootstrap") -> None:
    """Print the upgrade-side banner for any backfilled lessons scaffolding.

    Names only what was actually created (CREATED / CREATED_FROM_DEFAULT),
    reusing the same lines the fresh-init Step 5 banner prints; stays silent
    when every artifact already existed so an up-to-date project reports
    nothing.
    """
    if not boot.created_any:
        return
    print("Lessons scaffolding backfilled:")
    for result, rel in boot.index_results:
        if result == ConfigResult.CREATED:
            print(f"  + {rel}")
    if boot.cat_result == ConfigResult.CREATED:
        print(f"  + {boot.cat_rel}")
    elif boot.cat_result == ConfigResult.CREATED_FROM_DEFAULT:
        print(
            f"  + {boot.cat_rel} (rendered with default buckets — "
            "config.yaml `categorization:` block missing)"
        )
        print("                  Add the block to customise buckets, or run --migrate to seed it from the template.")
    if boot.notes_result == ConfigResult.CREATED:
        print(f"  + {boot.notes_rel}")
    print()
