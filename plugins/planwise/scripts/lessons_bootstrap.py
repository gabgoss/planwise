"""Lessons-directory scaffolding: categorization schema + bootstrap routine.

Owns the fallback categorization schema (DEFAULT_CATEGORIZATION), the
00-Categorization-By-Domain.md renderer, and the idempotent lessons-index +
categorization seeding routine (bootstrap_lessons_artifacts) that both fresh
init and the upgrade-side backfill path call through.
"""

import dataclasses
from datetime import date

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from config_gen import ConfigResult, InitConfig  # noqa: F401 -- InitConfig is a quoted forward-ref type hint
except ImportError:
    raise ImportError(
        "config_gen is required for lessons_bootstrap's ConfigResult/InitConfig "
        "types; the scripts/ directory appears to be partially installed"
    )


# Fallback categorization used when the user's config.yaml has no
# `categorization:` block. Mirrors the buckets baked into
# config.yaml.template; consumed by render_categorization_file() and by the
# `--migrate` flow when seeding the block on an existing config.
DEFAULT_CATEGORIZATION = {
    "buckets": [
        {
            "id": "A",
            "slug": "database",
            "name": "Database / SQL",
            "description": "Lessons that touch the live database, schema, or DDL semantics.",
        },
        {
            "id": "B",
            "slug": "code",
            "name": "Application Code",
            "description": "Lessons about language-level patterns, type-checking, lint, runtime behaviour.",
        },
        {
            "id": "C",
            "slug": "process",
            "name": "Planwise / Process",
            "description": "Lessons about planning, scaffolding, dispatch, signoff, review.",
            "sub_buckets": [],
        },
        {
            "id": "D",
            "slug": "tooling",
            "name": "Tooling / Ergonomics",
            "description": "Toolchain, shell, notebook, IDE, harness ergonomics.",
        },
    ],
    "decision_tree_order": ["A", "B", "C", "D"],
    "default_bucket": "D",
    "edge_cases_section": True,
}


def _render_bucket_section(bucket: dict, code_bucket_inherited: bool = False) -> list[str]:
    """Render one top-level bucket plus its sub-buckets to a list of lines."""
    bucket_id = str(bucket.get("id", "?"))
    bucket_name = str(bucket.get("name", ""))
    description = str(bucket.get("description", ""))
    code_bucket = bool(bucket.get("code_bucket", code_bucket_inherited))

    if code_bucket:
        header_row = "| ID | Title | Module | Severity |"
        sep_row = "|----|-------|--------|----------|"
    else:
        header_row = "| ID | Title | Severity |"
        sep_row = "|----|-------|----------|"

    lines = [
        f"## {bucket_id}. {bucket_name} (0)",
        "",
        description,
        "",
        header_row,
        sep_row,
    ]

    for sub in bucket.get("sub_buckets") or []:
        if not isinstance(sub, dict):
            continue
        sub_id = str(sub.get("id", "?"))
        sub_name = str(sub.get("name", ""))
        lines.extend([
            "",
            f"### {sub_id}. {sub_name} (0)",
            "",
            header_row,
            sep_row,
        ])

    return lines


def render_categorization_file(cfg: "InitConfig") -> tuple[ConfigResult, str]:
    """Render 00-Categorization-By-Domain.md from config + categorization schema.

    Idempotent — returns SKIPPED_EXISTS if the file already exists.
    Returns SKIPPED_NO_YAML if PyYAML is unavailable (the init handler's
    Step 5.1 fallback renders the file via Claude in that case).

    When the user's config has no `categorization:` block (or the block is
    empty), the renderer falls back to DEFAULT_CATEGORIZATION and returns
    CREATED_FROM_DEFAULT so the banner can flag it. The user can edit the
    buckets afterwards, or run `--migrate` to add the template block to
    their config for full customisation.
    """
    dst_rel = f"{cfg.planwise_root}/{cfg.lessons_dir}/00-Categorization-By-Domain.md"
    dst = cfg.project_root / dst_rel
    if dst.exists():
        return ConfigResult.SKIPPED_EXISTS, dst_rel

    if not HAS_YAML:
        return ConfigResult.SKIPPED_NO_YAML, dst_rel

    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    config_present = config_path.exists()
    cat: dict | None = None
    used_default = False
    lessons_index = "00-Index-LessonsLearned.md"

    if config_present:
        try:
            config_text = config_path.read_text(encoding="utf-8")
            full = yaml.safe_load(config_text) or {}
            if isinstance(full, dict):
                candidate = full.get("categorization")
                if isinstance(candidate, dict):
                    buckets_candidate = candidate.get("buckets") or []
                    if [b for b in buckets_candidate if isinstance(b, dict)]:
                        cat = candidate
                lessons_index = (
                    full.get("project", {})
                    .get("index_files", {})
                    .get("lessons", "00-Index-LessonsLearned.md")
                )
        except yaml.YAMLError:
            # Bad config — fall through to default, surface via banner.
            pass

    if cat is None:
        cat = DEFAULT_CATEGORIZATION
        used_default = True

    buckets = cat.get("buckets") or []
    buckets = [b for b in buckets if isinstance(b, dict)]
    if not buckets:
        # Defensive — DEFAULT_CATEGORIZATION always has buckets, but guard anyway.
        return ConfigResult.SKIPPED_BAD_CONFIG, dst_rel

    decision_tree_order = cat.get("decision_tree_order") or [b.get("id") for b in buckets]
    buckets_by_id = {b.get("id"): b for b in buckets}
    ordered_buckets = [buckets_by_id[bid] for bid in decision_tree_order if bid in buckets_by_id]
    for b in buckets:
        if b.get("id") not in {bb.get("id") for bb in ordered_buckets}:
            ordered_buckets.append(b)

    bucket_blocks = []
    for b in ordered_buckets:
        bucket_blocks.append("\n".join(_render_bucket_section(b)))

    today = date.today().isoformat()
    scope_paragraph = f"Lessons captured during {cfg.project_name} sessions."

    rendered = (
        "# Lessons Learned — Categorization by Domain\n"
        "\n"
        f"**Purpose:** Group lessons in `{cfg.lessons_dir}/` by domain for scope-specific review and rule-promotion decisions.\n"
        f"**Last Updated:** {today}\n"
        f"**Companion to:** [{lessons_index}]({lessons_index}) (chronological master table)\n"
        "\n"
        "---\n"
        "\n"
        "## Scope\n"
        "\n"
        f"{scope_paragraph}\n"
        "\n"
        "---\n"
        "\n"
        + "\n\n".join(bucket_blocks)
        + "\n"
        "\n"
        "---\n"
        "\n"
        "## Cross-cutting observations\n"
        "\n"
        "_Populated by `/planwise lessons curate` as patterns emerge across buckets._\n"
        "\n"
        "---\n"
        "\n"
        "## Classification edge cases\n"
        "\n"
        "| ID | Why it could fit elsewhere | Final bucket |\n"
        "|----|---------------------------|---------------|\n"
        "\n"
        "---\n"
    )

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


def _seed_lessons_index(cfg: "InitConfig") -> tuple[ConfigResult, str]:
    """Seed the lessons index from the plugin seed dir if missing. Idempotent.

    Mirrors copy_seed_files for the lessons index alone, so the upgrade-side
    backfill can recreate it without re-seeding backlog/plans. Returns
    SKIPPED_EXISTS when the file is already present (never overwrites a
    populated index) and SKIPPED_NO_TEMPLATE when the plugin seed file is
    absent.
    """
    src_name = "00-Index-LessonsLearned.md"
    dst_rel = f"{cfg.planwise_root}/{cfg.lessons_dir}/{src_name}"
    dst = cfg.project_root / dst_rel
    if dst.exists():
        return ConfigResult.SKIPPED_EXISTS, dst_rel
    src = cfg.plugin_root / "seed" / src_name
    try:
        src_content = src.read_bytes()
    except FileNotFoundError:
        return ConfigResult.SKIPPED_NO_TEMPLATE, dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dst, "xb") as f:
            f.write(src_content)
    except FileExistsError:
        return ConfigResult.SKIPPED_EXISTS, dst_rel
    return ConfigResult.CREATED, dst_rel


@dataclasses.dataclass
class LessonsBootstrap:
    """Outcome of bootstrap_lessons_artifacts, with banner-ready fields.

    Carries the per-artifact ConfigResult so each caller (fresh init / upgrade)
    can render its own banner from the same routine.
    """
    index_result: ConfigResult
    index_rel: str
    cat_result: ConfigResult
    cat_rel: str

    @property
    def created_any(self) -> bool:
        created = {ConfigResult.CREATED, ConfigResult.CREATED_FROM_DEFAULT}
        return self.index_result in created or self.cat_result in created


def bootstrap_lessons_artifacts(cfg: "InitConfig") -> LessonsBootstrap:
    """Ensure the lessons scaffolding (index seed + categorization file) exists.

    The single idempotent, non-destructive routine wired into BOTH fresh init
    and _run_upgrade(): each sub-step is a no-op when its file is already
    present (SKIPPED_EXISTS), so an already-complete project is left untouched
    and a user-customised file is preserved verbatim. On an upgrade-adopted
    project this backfills 00-Categorization-By-Domain.md — the file that
    gates /planwise lessons curate and promote-batch — which the legacy
    fresh-init-only render never created.
    """
    index_result, index_rel = _seed_lessons_index(cfg)
    cat_result, cat_rel = render_categorization_file(cfg)
    return LessonsBootstrap(index_result, index_rel, cat_result, cat_rel)


def _emit_lessons_bootstrap_banner(boot: "LessonsBootstrap") -> None:
    """Print the upgrade-side banner for any backfilled lessons scaffolding.

    Names only what was actually created (CREATED / CREATED_FROM_DEFAULT),
    reusing the same lines the fresh-init Step 5 banner prints; stays silent
    when both artifacts already existed so an up-to-date project reports
    nothing.
    """
    if not boot.created_any:
        return
    print("Lessons scaffolding backfilled:")
    if boot.index_result == ConfigResult.CREATED:
        print(f"  + {boot.index_rel}")
    if boot.cat_result == ConfigResult.CREATED:
        print(f"  + {boot.cat_rel}")
    elif boot.cat_result == ConfigResult.CREATED_FROM_DEFAULT:
        print(
            f"  + {boot.cat_rel} (rendered with default buckets — "
            "config.yaml `categorization:` block missing)"
        )
        print("                  Add the block to customise buckets, or run --migrate to seed it from the template.")
    print()
