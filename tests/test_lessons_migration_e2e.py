"""End-to-end tests for the lessons-index retrofit: a legacy 1.0.5.1 fixture
reaches the generated lessons family with zero human steps, through both
`artifact_upgrade._run_upgrade` and a fresh `init_project.main()`. Mirrors
`test_backlog_migration_e2e.py`'s mechanics (byte-built fixture, git init/
commit/dirty-edit, capture, tree snapshot) on the lessons retrofit's own
contract (`lessons_migration.py`, `migrate_lessons_index.py`).

Fixture A (`../Session-06-LessonsMigrator/Outputs/BIR-S05-06-01-
TransformationLedger.md` § Fixture Designs) embeds the shipped 1.0.5.1 seed
as a byte constant, with three lessons added to its Master Table: LL-001
(full frontmatter, a Title-cell sentence beyond the title, exercising the
index-note-append harvest path), LL-002 (bare title cell, missing
`title:`/`category:`, backfilled from its H1, saved under Archive/), and
LL-003 (CRLF, an unquoted `title:` an inline `#` would truncate, and one
lone bare CR inside its Title cell -- CR residue the regenerated table
discards by construction, since it renders Title from frontmatter, never
the legacy row's own bytes).

Every fixture write is byte-built (`bytes`/`.encode()`/`.replace()`), never
`write_text` -- reading a CRLF source through `Path.read_text()` or
`open(..., encoding=...)` applies Python's universal-newline translation
and silently turns it to LF (confirmed empirically while authoring this
module: `Path.read_text()` on the real 1.0.5.1 seed produced zero `\r\n`
occurrences; per LL-149-PROC, a fixture built or read through text mode
cannot be trusted to preserve a newline shape).

Cost guard (`.claude/rules/guard-at-the-cost-layer.md`): the git init/
commit/dirty-edit lives inside the `_project` fixture-building function
itself, so a deselected run of this module builds nothing. BCR's own
`test_backlog_migration_e2e.py` carries no e2e marker and this suite
registers none in `pytest.ini`, so none is applied here either.
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

# `init_project` (the composition root) is imported first by convention,
# mirroring `test_lessons_migration_wiring.py`. The order is no longer
# load-bearing: `test_import_order.py` proves `artifact_upgrade`,
# `promotion_log` and `lessons_changelog` each import first on their own.
import init_project as ip  # noqa: I001 -- composition root first, see comment above
import artifact_upgrade
import config_loader
import generate_lessons_index as gen
import lessons_changelog
import migrate_lessons_index as mig
import migrate_lessons_support as sup
import parse_lessons
import promotion_log
from config_gen import InitConfig, read_plugin_version
from reconcile_common import read_text_preserving_newlines as read_text

REAL_PLUGIN_ROOT = SCRIPTS.parent
FROM = "1.0.5.1"
TO = read_plugin_version(REAL_PLUGIN_ROOT)  # measured live, never hardcoded
INDEX = "00-Index-LessonsLearned.md"
CHANGELOG = "00-Changelog-LessonsLearned.md"
PROMO_ARCHIVE = "Archive/PromotionLog-LessonsLearned-001-050.md"
COMPANION = "00-Categorization-By-Domain.md"
NOTES = "00-Categorization-Notes-LessonsLearned.md"
LEDGER = "00-Lessons-Migration-Ledger.json"
LL1, LL2, LL3 = "LL-001-PROC-First.md", "Archive/LL-002-TOOL-Second.md", "LL-003-PERF-Third.md"

CONFIG_YAML = (
    'project:\n  name: "e2e-lessons"\n  lessons_dir: "LessonsLearned"\n  index_files:\n'
    f'    lessons: "{INDEX}"\n'
    'lesson_statuses:\n  - documented\n  - promoted\n  - applied\n  - rule\n  - orphaned\n'
    'categorization:\n  buckets:\n    - id: A\n      slug: general\n      name: "General"\n'
    '      description: "fixture bucket"\n  decision_tree_order: [A]\n  default_bucket: A\n'
)

# The shipped 1.0.5.1 seed, embedded verbatim as a byte constant (never
# re-read from the marketplace cache at test time). Source:
# C:/Users/gabgo/.claude/plugins/cache/planwise-marketplace/planwise/1.0.5.1/
# seed/00-Index-LessonsLearned.md -- confirmed byte-identical in content to
# the 1.0.5 git tag (git diff --stat exits empty); only line endings differ
# (that installed copy is CRLF, applied explicitly below via `_crlf`).
# Written here with `\n` line endings for source readability; `_crlf()`
# converts the WHOLE assembled string to `\r\n` at fixture-build time, after
# the one intentional lone `\r` (LL-003's Title cell, inserted below) is
# already in place -- `str.replace("\n", "\r\n")` never touches an existing
# lone `\r`, so that byte survives the conversion unpaired.
_SEED_1_0_5_1 = (
    "# Lessons Learned Index\n"
    "\n"
    "**Purpose:** Central index and taxonomy reference for all lessons learned.\n"
    "**Last Updated:** YYYY-MM-DD\n"
    "**Companion:** [00-Categorization-By-Domain.md](00-Categorization-By-Domain.md) \u2014 domain "
    "bucketing view, sync'd by `/planwise lessons curate`.\n"
    "\n---\n\n"
    "## Naming Convention\n\n"
    "**Format:** `LL-{NNN}-{Domain}-{Name}.md`\n\n"
    "| Component | Description | Example |\n"
    "|-----------|-------------|---------|\n"
    "| `LL` | Lessons Learned prefix | LL |\n"
    "| `{NNN}` | Global sequence number (zero-padded to 3 digits) | 001, 023 |\n"
    "| `{Domain}` | Abbreviation from config.yaml (`abbreviations` + `lesson_abbreviations`) | DOC, TOOL |\n"
    "| `{Name}` | PascalCase descriptive name | QueryFilterTranslation |\n\n"
    "**Next available ID:** LL-001\n\n---\n\n"
    "## Status Definitions\n\n"
    "| Status | Meaning |\n"
    "|--------|---------|\n"
    "| `documented` | Captured; not yet owned by any backlog item. |\n"
    "| `promoted` | Fully captured into actionable backlog item(s); archived; awaiting landing; the "
    "backlog item is the live owner. **archived \u2260 landed.** |\n"
    "| `applied` | Lesson applied to improve a process or pattern |\n"
    "| `rule` | Lesson promoted to a `.claude/` artifact |\n"
    "| `orphaned` | Content was fully captured into an owning item that has since closed without "
    "landing it, and no live item currently owns it. Work-surfacing: resurfaces ahead of `documented` "
    "in the next promotion pass. |\n\n---\n\n"
    "## Quick Reference\n\n"
    "| Action | How |\n"
    "|--------|-----|\n"
    "| Find lessons by tag | `/lessons python regex` |\n"
    "| Find by domain | `/lessons myproject` |\n"
    "| Find by category | `/lessons anti-pattern` |\n"
    "| List all lessons | `/lessons` (no arguments) |\n"
    "| Create new lesson | Use template below, next ID = LL-001 |\n\n---\n\n"
    "## Master Table\n\n"
    "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status |\n"
    "|----|-------|----------|----------|----------|------------|--------|--------|--------|\n"
    "| | | | | | | | | |\n"
    "\n---\n\n"
    "## Lesson File Template\n\n"
    "```yaml\n---\n"
    "id: LL-{NNN}\ntitle: {Descriptive title}\ndate: {YYYY-MM-DD}\nsource: {session reference}\n"
    "category: {anti-pattern | pattern | process}\nseverity: {low | medium | high}\n"
    "language: [{python | csharp | javascript | ...}]\ntechnology: [{specific tech}]\n"
    "domain: [{project domains}]\nstatus: documented\napplied-as: null\n"
    "promotion-target: [rule|code|claude-md|agent|skill|settings]   # one or more target types; "
    "multi-value = coarse / split-candidate\n"
    "# promoted-to:                                                  # owning backlog item id(s), "
    "e.g. BB-{NNN}; set at capture-archive\n"
    "# rule-as:                                                      # DEPRECATED alias for "
    "applied-as \u2014 read for back-compat, never written\n---\n\n"
    "# LL-{NNN}-{Domain}: {Same title as frontmatter}\n\n## Context\n\n"
    "{What happened \u2014 specific file, function, input, error.}\n\n## Lesson\n\n"
    "{The insight or fix. Include WRONG/CORRECT code examples for anti-patterns.}\n\n## Applies To\n\n"
    "{When this lesson is relevant \u2014 technologies, file patterns, scenarios.}\n```\n\n"
    "### Pointer Fields \u2014 Authoritative Definition\n\n"
    "Two frontmatter fields answer two different questions. This table is the single source of "
    "truth for their meaning; every other document that mentions them defers here rather than "
    "restating the semantics.\n\n"
    "| Field | Answers | Value form | Written when |\n"
    "|-------|---------|-----------|--------------|\n"
    "| `promoted-to:` | **Who owns the work?** | Backlog item id(s) \u2014 `BB-{NNN}`, listing every "
    "owner when a lesson decomposed across several items | At capture-archive, when the lesson "
    "becomes owned |\n"
    "| `applied-as:` | **Where did it land?** | Path(s) to the artifact(s) actually created \u2014 a "
    "scalar, or a YAML list when a lesson landed in several files | At landing, replacing `null` "
    "or a `PENDING:BB-{NNN}` marker |\n\n"
    "`applied-as:` is the artifact pointer for **both** terminal statuses (`rule` and `applied`) "
    "\u2014 the `status:` field, not a second pointer key, records which kind of landing it was.\n\n"
    "> [!constraint] `rule-as:` is deprecated \u2014 read it, never write it\n"
    "> An older scheme inverted these two fields: `applied-as:` held the owning backlog item and a "
    "separate `rule-as:` held the artifact. That scheme is superseded. Tooling MUST still **read** "
    "`rule-as:` so pre-existing lessons keep resolving, but MUST NOT **write** it, and MUST NOT "
    "treat its presence as an error.\n>\n"
    "> Migrating a legacy lesson is a **value remap between two keys, not a key rename**: the "
    "artifact path moves from `rule-as:` into `applied-as:`, and whatever `applied-as:` previously "
    "held (an owning backlog item) moves into `promoted-to:` \u2014 normalised to id form, since a "
    "stored path to a backlog item breaks as soon as that item is archived. Preserve a list-valued "
    "pointer as a YAML list; do not flatten it to a delimited string.\n>\n"
    "> WRONG \u2014 relabel one key and call it migrated:\n> ```yaml\n> status: rule\n"
    "> applied-as: {backlog-dir}/BB-{NNN}-{SB}-{Domain}-{Topic}.md   # still the OWNER, now under "
    "the artifact key\n> ```\n"
    "> CORRECT \u2014 remap the values, then drop the legacy key:\n> ```yaml\n> status: rule\n"
    "> applied-as: references/{artifact}.md \u00a7{N}                      # the artifact\n"
    "> promoted-to: BB-{NNN}                                          # the owner\n> ```\n\n---\n\n"
    "## Archive\n\n"
    "A lesson is moved to `Archive/` when **fully captured** \u2014 either single-promote "
    "(\u2192 `applied`/`rule`) or promote-batch (\u2192 `promoted`). Archived lessons remain "
    "searchable via `/lessons <terms>` (search globs recurse into `Archive/`).\n\n"
    "**Location:** `{lessons-dir}/Archive/`\n\n---\n\n"
    "## Rule Promotion Log\n\n"
    "| Date | Lesson ID | Artifact Created | File |\n"
    "|------|-----------|-----------------|------|\n"
    "| | | | |\n\n---\n"
)

# Row shapes per Session-06's Fixture A (binding: the ledger's design wins
# over this task's own paraphrase where the two differ -- see KEY_FINDINGS
# in Recovery). LL-001's Title cell carries two sentences beyond its title
# (harvested as an Index Note); LL-002's is bare (equals the H1-backfilled
# title, so nothing is harvested); LL-003's carries one lone bare `\r`
# (never a `\r\n` pair) inside otherwise-plain text.
_MASTER_ROWS = (
    "| LL-001 | First lesson title. Extra sentence one. Extra sentence two. | Process | Medium | "
    "python | pytest | PROC | fixture | documented |\n"
    "| LL-002 | Second lesson title | Tooling | Low | bash | git | TOOL | fixture | promoted |\n"
    "| LL-003 | A title with #hash\r unquoted | Performance | High | csharp | dotnet | PERF | "
    "fixture | documented |\n"
)
# Fixture A names one Rule Promotion Log row for lesson 003 (this task's own
# text says LL-002; the ledger's design -- binding on conflict -- says
# LL-003, recorded as a KEY_FINDINGS divergence).
_PROMO_ROW = "| 2026-09-01 | LL-003 | rule-x.md | rule-x.md |\n"

LL1_TEXT = (
    "---\nid: LL-001\ntitle: First lesson title\ndate: 2024-01-01\ncategory: Process\n"
    "severity: Medium\nlanguage: [python]\ntechnology: [pytest]\ndomain: [PROC]\nsource: fixture\n"
    "status: documented\napplied-as: null\n---\n\n"
    "# LL-001-PROC: First lesson title\n\n## Context\n\nFixture context for LL-001.\n"
)
LL2_TEXT = (
    "---\nid: LL-002\ndate: 2024-02-02\nseverity: Low\nlanguage: [bash]\ntechnology: [git]\n"
    "domain: [TOOL]\nsource: fixture\nstatus: promoted\napplied-as: .claude/rules/x.md\n---\n\n"
    "# LL-002 Second lesson title\n\n## Context\n\nFixture context for LL-002.\n"
)
LL3_TEXT = (
    "---\nid: LL-003\ntitle: A title with #hash unquoted\ndate: 2024-03-03\ncategory: Performance\n"
    "severity: High\nlanguage: [csharp]\ntechnology: [dotnet]\ndomain: [PERF]\nsource: fixture\n"
    "status: documented\napplied-as: null\n---\n\n"
    "# LL-003-PERF: A title with #hash unquoted\n\n## Context\n\nFixture context for LL-003.\n"
)
COMPANION_TEXT = (
    "# Categorization By Domain\n\n**Last Updated:** 2024-01-01\n\n## A. General (1)\n\n"
    "| ID | Title | Severity |\n|----|-------|----------|\n| LL-001 | First lesson title | Medium |\n"
)
# The plugin's own changelog seed, read from disk: `copy_seed_files()` /
# `_seed_lessons_index()` copy it byte for byte on Path 2. Its line ending is
# whatever the checkout gave it (LF, or CRLF under core.autocrlf=true), so
# no line ending is hard-coded here.
CHANGELOG_HEADER_ONLY = (REAL_PLUGIN_ROOT / "seed" / "00-Changelog-LessonsLearned.md").read_bytes()
MISSING_ARTIFACT_ID = "LL-002"


def _crlf(text: str) -> bytes:
    return text.replace("\n", "\r\n").encode("utf-8")


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def _git(root: Path, *argv: str) -> str:
    return subprocess.run(["git", "-c", "core.autocrlf=false", *argv], cwd=str(root), check=True,
                          capture_output=True, text=True).stdout


def _seed_index() -> str:
    """The 1.0.5.1 seed with its two empty placeholder rows filled, LF form
    (converted to bytes -- CRLF for Fixture A's index -- by the caller)."""
    text = _SEED_1_0_5_1.replace("| | | | | | | | | |\n", _MASTER_ROWS, 1)
    return text.replace("| | | | |\n", _PROMO_ROW, 1)


def _project(tmp_path, *, omit_ll002=False, seed_openers=True, dirty=True):
    """Byte-build Fixture A under `tmp_path/proj`, git-init/commit it, then
    (when `dirty`) edit LL-001 so the tree is dirty -- proving the
    orchestrator's git-state report is informational only (never a refusal
    gate) at this layer. `omit_ll002` drops LL-002's file so its Master
    Table row resolves to zero files (the refusal fixture). `seed_openers`
    off leaves the changelog/promotion-log/companion unwritten, so
    Path 2's own bootstrap seeds them fresh (header-only) before the
    migrator runs."""
    root = tmp_path / "proj"
    lessons_dir = root / "planwise" / "LessonsLearned"
    _write(root / "planwise" / "config.yaml", CONFIG_YAML)
    _write(lessons_dir / INDEX, _crlf(_seed_index()))
    _write(lessons_dir / LL1, LL1_TEXT)
    if not omit_ll002:
        _write(lessons_dir / LL2, LL2_TEXT)
    _write(lessons_dir / LL3, _crlf(LL3_TEXT))
    if seed_openers:
        _write(lessons_dir / CHANGELOG, CHANGELOG_HEADER_ONLY)
        _write(lessons_dir / COMPANION, COMPANION_TEXT)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "fixture")
    if dirty:
        _write(lessons_dir / LL1, LL1_TEXT + "\nEdited after the commit, so the tree is dirty.\n")
    cfg = InitConfig(project_name="e2e-lessons", project_root=root, plugin_root=REAL_PLUGIN_ROOT)
    return cfg, lessons_dir


def _snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts}


def _pin(cfg, pinned: str) -> "InitConfig":
    """Prepend plugin_root/plugin_version to the fixture's config.yaml, so
    `_run_upgrade()`'s pin-read/pin-commit logic has something to read --
    mirrors `test_lessons_migration_wiring.py`'s own `_pin` helper."""
    config_path = cfg.project_root / "planwise" / "config.yaml"
    posix_root = str(cfg.plugin_root).replace("\\", "/")
    text = config_path.read_bytes().decode("utf-8")
    _write(config_path, f'plugin_root: "{posix_root}"\nplugin_version: "{pinned}"\n{text}')
    return InitConfig(project_name=cfg.project_name, project_root=cfg.project_root,
                      plugin_root=cfg.plugin_root, plugin_version=TO)


def _config(cfg) -> dict:
    return config_loader.load_config(Path(mig.__file__), config_path=cfg.project_root / "planwise" / "config.yaml")


def _check_exits(cfg) -> tuple:
    """The `--check` facade's in-process functions for the index and the
    companion -- the same ones `lessons_migration._check_generated` calls."""
    config = _config(cfg)
    index_path = config["_lessons_index"]
    naming = mig._index_naming(index_path)
    index_exit = mig._check_index(config["_lessons_dir"], config["_lessons_dir"] / "Archive",
                                  index_path, naming, config)
    companion_exit = gen._run_companion_cli(SimpleNamespace(write=False, json=False, replace_legacy=False),
                                            config["_lessons_dir"], config["_lessons_dir"] / "Archive",
                                            index_path, naming, config)
    return index_exit, companion_exit


def _backups(cfg, pair: str) -> Path:
    return cfg.project_root / "planwise" / "upgrade-backups" / pair / "lessons"


def _dispositions(cfg, pair: str) -> str:
    return (cfg.project_root / "planwise" / "upgrade-backups" / pair / "DISPOSITIONS.md").read_bytes().decode("utf-8")


# ---------------------------------------------------------------------------
# Path 1: artifact_upgrade._run_upgrade, FROM -> TO, lessons_reconcile=None
# ---------------------------------------------------------------------------
def test_path1_run_upgrade_migrates_legacy_lessons_end_to_end(tmp_path, monkeypatch, capsys):
    cfg, lessons_dir = _project(tmp_path)
    original_index = (lessons_dir / INDEX).read_bytes()
    original_ll1 = (lessons_dir / LL1).read_bytes()
    original_ll2 = (lessons_dir / LL2).read_bytes()
    original_ll3 = (lessons_dir / LL3).read_bytes()
    cfg = _pin(cfg, FROM)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    exit_code = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    banner = capsys.readouterr().out
    pair = f"{FROM}-to-{TO}"

    # 1. Banner names the state, the ledger and the backup dir.
    assert exit_code == 0
    assert "Lessons index migration:" in banner and "migrated:" in banner
    assert str(_backups(cfg, pair) / LEDGER) in banner or "ledger:" in banner

    # 2. Backups byte-exact; one DISPOSITIONS row per written file.
    backups = _backups(cfg, pair)
    for rel, original in ((INDEX, original_index), (LL1, original_ll1),
                          (LL2, original_ll2), (LL3, original_ll3), (CHANGELOG, CHANGELOG_HEADER_ONLY)):
        assert backups.joinpath(rel).read_bytes() == (original if isinstance(original, bytes)
                                                       else original.encode("utf-8")), rel
    disp = _dispositions(cfg, pair)
    rows = [r for r in disp.splitlines() if " lessons-" in r]
    assert len(rows) >= 6
    for name in (INDEX, LL1, LL2, LL3, CHANGELOG):
        assert sum(name.rsplit("/", 1)[-1] in r for r in rows) >= 1, name
    for action in ("lessons-rewritten", "lessons-created"):
        assert any(action in r for r in rows), action

    # 3. The hub is generated; parse_lessons agrees.
    hub = read_text(lessons_dir / INDEX)
    assert "Generated:" in hub
    config = _config(cfg)
    parsed = parse_lessons.parse_index(config)
    assert parsed.shape == "generated" and len(parsed.rows) == 3
    assert len(parsed.rows[0].cells) == 10  # the 9 legacy columns plus the generator's own File column
    next_id = parse_lessons.compute_next_id(config)
    assert next_id["next_id"] == "LL-004"

    # 4. `--check` and `--companion --check` exit 0, in process.
    index_exit, companion_exit = _check_exits(cfg)
    assert (index_exit, companion_exit) == (0, 0)

    # 5. LL-002: title/category backfilled, applied-as/status unchanged
    #    (index-wins found no disagreement, since the row's own Status cell
    #    already reads "promoted").
    ll2 = read_text(lessons_dir / LL2)
    assert "title: Second lesson title" in ll2 and "category: Tooling" in ll2
    assert "applied-as: .claude/rules/x.md" in ll2 and "status: promoted" in ll2
    assert "## Index Note" not in ll2  # bare title cell: nothing to harvest

    # 6. LL-003: title quoted, generator reads it whole; file stays CRLF;
    #    the CR residue never reaches the rendered Title cell.
    ll3_bytes = (lessons_dir / LL3).read_bytes()
    assert b"\r\n" in ll3_bytes  # still CRLF
    ll3 = read_text(lessons_dir / LL3)
    assert 'title: "A title with #hash unquoted"' in ll3
    assert "## Index Note" not in ll3  # its unit is already present verbatim (its own H1)
    ll3_row_line = next(ln for ln in hub.split("\n") if "LL-003" in ln).rstrip("\r")
    assert "\r" not in ll3_row_line

    # 7. LL-001 gets exactly the two extra sentences under an Index Note.
    ll1 = read_text(lessons_dir / LL1)
    assert "## Index Note (migrated" in ll1
    assert "Extra sentence one." in ll1 and "Extra sentence two." in ll1

    # 8. Promotion log: the LL-003 row lands in the 001-050 Archive file;
    #    tuple count 1 before and after this run (nothing else migrated).
    promo = read_text(lessons_dir / PROMO_ARCHIVE)
    assert "| LL-003 | rule-x.md | rule-x.md |" in promo.replace("2026-09-01 | ", "")
    # The hub-side file "lists every part" is NOT asserted here: this
    # fixture's one row (id <= 50) never routes to the hub file at all
    # (`log_destination` only writes id >= 201 there), so the MIGRATION never
    # populates it. `_run_upgrade`'s own bootstrap step seeds it fresh
    # (header-only) before the retrofit runs regardless, exactly as it does
    # for the promotion-log/notes pair in the refusal test above, so the
    # file exists but stays at the bootstrap's header-only shape. See
    # Promises Not Asserted.
    assert sup.header_only(read_text(lessons_dir / "00-PromotionLog-LessonsLearned.md"), INDEX)

    # 9. Changelog: Entry 1 carries the relocated header history; since this
    #    fixture's five prose sections all equal the shipped seed's current
    #    text (`SEED_BODIES`), none is relocated -- the ledger's prose
    #    section lists all five as dropped instead (the task's "otherwise"
    #    branch, per KEY_FINDINGS).
    changelog = read_text(lessons_dir / CHANGELOG)
    assert "## Entry 1" in changelog
    ledger = json.loads(read_text(backups.parent.parent / "LessonsLearned" / LEDGER)) if False else \
        json.loads(read_text(lessons_dir / LEDGER))
    assert ledger["prose"]["relocate"] == []
    assert sorted(ledger["prose"]["drop"]) == sorted(
        ["Naming Convention", "Status Definitions", "Quick Reference", "Lesson File Template", "Archive"])

    # 10. Companion: notes file holds the legacy companion's bytes verbatim;
    #     the regenerated companion lists all three lessons in its one bucket.
    assert (lessons_dir / NOTES).read_bytes() == COMPANION_TEXT.encode("utf-8")
    companion = read_text(lessons_dir / COMPANION)
    assert "Generated:" in companion
    for lid in ("LL-001", "LL-002", "LL-003"):
        assert lid in companion

    # 11. The ledger's conservation field: `unaccounted == 0` (the ledger
    # schema's top-level key -- see KEY_FINDINGS on `migrate_lessons_
    # support.unaccounted`, a helper name that no longer exists; the JSON
    # field the code writes is `ledger["unaccounted"]`, read here).
    assert ledger["unaccounted"] == 0

    # 12. `--report --json` now reports `promotion_log` as present.
    report = mig.build_report(config, lessons_dir / INDEX)
    assert report["shape"] == "generated" and report["promotion_log"] == "populated"

    # 13. git_dirty reported True (informational; never a refusal gate at
    #     this layer -- proves the orchestrator's dirty-tree bypass).
    # (captured indirectly: the banner prints "git tree was dirty:      yes")
    assert "git tree was dirty:      yes" in banner

    # 14. A second run at the same pair is silent, byte-identical.
    after_first = _snapshot(cfg.project_root)
    again = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    assert again == 0
    assert _snapshot(cfg.project_root) == after_first


def test_path1_writers_after_migration(tmp_path, monkeypatch):
    """`promotion_log.py --append` and `lessons_changelog.py --append` on
    the migrated tree: one more row, refused on the exact duplicate; the
    changelog gains `## Entry 2`, never renumbering `## Entry 1`."""
    cfg, lessons_dir = _project(tmp_path)
    cfg = _pin(cfg, FROM)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    config_path = cfg.project_root / "planwise" / "config.yaml"

    rc = promotion_log.main(["--config", str(config_path), "--lesson", "LL-001",
                             "--artifact", "rule-a.md", "--file", "rule-a.md"])
    assert rc == 0
    dup_rc = promotion_log.main(["--config", str(config_path), "--lesson", "LL-001",
                                 "--artifact", "rule-a.md", "--file", "rule-a.md"])
    assert dup_rc == 1
    promo = read_text(lessons_dir / PROMO_ARCHIVE)
    assert promo.count("| LL-001 | rule-a.md | rule-a.md |") == 1

    rc2 = lessons_changelog.main(["--config", str(config_path), "--append", "probe"])
    assert rc2 == 0
    changelog = read_text(lessons_dir / CHANGELOG)
    assert "## Entry 2" in changelog and "## Entry 1" in changelog
    assert changelog.index("## Entry 2") < changelog.index("## Entry 1")  # newest first, prepended


def test_path1_hub_lists_every_part_after_a_hub_routed_write(tmp_path, monkeypatch):
    """The hub-side promotion-log file lists every Archive part on disk.

    The migration leaves the hub header-only (the fixture's one row, LL-003,
    routes to the 001-050 part). LL-201 is the first id `log_destination`
    routes to the hub itself, so this write is what makes the hub carry
    rows, and after it the hub's `Parts:` line must name every part file
    that exists. The expected set is read from disk, never hardcoded."""
    cfg, lessons_dir = _project(tmp_path)
    cfg = _pin(cfg, FROM)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    config_path = cfg.project_root / "planwise" / "config.yaml"
    hub_rel = "00-PromotionLog-LessonsLearned.md"

    rc = promotion_log.main(["--config", str(config_path), "--lesson", "LL-201",
                             "--artifact", "rule-y.md", "--file", "rule-y.md", "--date", "2026-09-02"])
    assert rc == 0

    hub = read_text(lessons_dir / hub_rel)
    assert "| 2026-09-02 | LL-201 | rule-y.md | rule-y.md |" in hub
    on_disk = sorted(p.relative_to(lessons_dir).as_posix()
                     for p in (lessons_dir / "Archive").glob("PromotionLog-LessonsLearned-*.md"))
    assert PROMO_ARCHIVE in on_disk
    parts_lines = [ln for ln in hub.splitlines() if ln.startswith("Parts: ")]
    assert len(parts_lines) == 1, hub
    listed = sorted(href for _text, href in re.findall(r"\[([^\]]*)\]\(([^)]*)\)", parts_lines[0]))
    assert listed == on_disk


def test_path1_refusal_leaves_tree_untouched(tmp_path, monkeypatch, capsys):
    """LL-002's row resolves to zero files (its own file is omitted) ->
    state `refused`, grouped in one RefusalSet block naming it, exit code
    unchanged, the retrofit itself writes nothing, the pin still committed.

    KEY_FINDING: `_run_upgrade`'s own bootstrap step (`bootstrap_lessons_
    artifacts`, Step 2b) runs BEFORE the lessons retrofit and unconditionally
    backfills any of the index/changelog/promotion-log/companion openers
    that are absent, regardless of whether the retrofit that follows
    refuses. This fixture pre-seeds the changelog and companion but not the
    hub-side promotion-log file or the categorization notes file, so the
    bootstrap creates those two even though the retrofit refuses -- "nothing
    was written" is a property of the RETROFIT (index, lesson files, no
    `upgrade-backups/.../lessons/` dir), not of the whole `_run_upgrade`
    call, which the task's Step 3 bullet does not separate out."""
    cfg, lessons_dir = _project(tmp_path, omit_ll002=True)
    cfg = _pin(cfg, FROM)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    original_index = (lessons_dir / INDEX).read_bytes()
    original_ll1 = (lessons_dir / LL1).read_bytes()

    exit_code = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    banner = capsys.readouterr().out

    assert exit_code == 0  # a lessons refusal never changes _run_upgrade's own exit code
    committed = yaml.safe_load((cfg.project_root / "planwise" / "config.yaml").read_bytes())
    assert committed["plugin_version"] == TO
    assert (lessons_dir / INDEX).read_bytes() == original_index
    assert (lessons_dir / LL1).read_bytes() == original_ll1
    assert not (cfg.project_root / "planwise" / "upgrade-backups" / f"{FROM}-to-{TO}" / "lessons").exists()
    assert "Lessons index migration: REFUSED" in banner
    assert MISSING_ARTIFACT_ID in banner  # the RefusalSet group names the missing lesson


def test_path1_changelog_split_reached_through_run_upgrade(tmp_path, monkeypatch):
    """An already-generated index whose changelog has grown past budget,
    driven through `_run_upgrade`'s already-up-to-date branch, reaches
    `changelog_split` with backups; a second run at the same pair is
    silent."""
    root = tmp_path / "split"
    lessons_dir = root / "planwise" / "LessonsLearned"
    posix_root = str(REAL_PLUGIN_ROOT).replace("\\", "/")
    config_yaml = (f'plugin_root: "{posix_root}"\nplugin_version: "{TO}"\n' + CONFIG_YAML)
    _write(root / "planwise" / "config.yaml", config_yaml)
    generated_index = (
        "Generated: 2024-01-01\n**Next available ID:** LL-002\n\n"
        "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status | File |\n"
        "|----|----|----|----|----|----|----|----|----|----|\n"
        "| LL-001 | Fixture Lesson One | process | medium | python | claude-code | PROC | fixture | "
        "documented | [001](LL-001-PROC-One.md) |\n"
    )
    _write(lessons_dir / INDEX, generated_index)
    filler = "Lorem ipsum filler text describing a fixture entry body in full. " * 90
    lines = [f"[\u2190 {INDEX}]({INDEX})", ""]
    for n in range(30, 0, -1):
        lines += [f"## Entry {n}", "", filler, ""]
    _write(lessons_dir / CHANGELOG, "\n".join(lines) + "\n")
    cfg = InitConfig(project_name="e2e-lessons", project_root=root, plugin_root=REAL_PLUGIN_ROOT, plugin_version=TO)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    exit_code = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    files = sorted(lessons_dir.glob(f"{CHANGELOG[:-3]}*.md"))
    assert exit_code == 0 and len(files) >= 2
    backups = _backups(cfg, f"{TO}-to-{TO}")
    assert backups.exists()

    after = _snapshot(root)
    exit_code2 = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    assert exit_code2 == 0
    assert _snapshot(root) == after


# ---------------------------------------------------------------------------
# Fix loop (release dry run, Findings 1-3): a generated-index fixture whose
# changelog carries a non-Entry '## ' heading and/or a fenced block, mirroring
# the live project's own changelog shape by BYTES -- never by copying the
# live file. `_generated_fixture` factors the "Generated:" index + config.yaml
# boilerplate `test_path1_changelog_split_reached_through_run_upgrade` above
# already used once; the new tests below reuse it rather than re-deriving it.
# ---------------------------------------------------------------------------

_GENERATED_INDEX = (
    "Generated: 2024-01-01\n**Next available ID:** LL-002\n\n"
    "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status | File |\n"
    "|----|----|----|----|----|----|----|----|----|----|\n"
    "| LL-001 | Fixture Lesson One | process | medium | python | claude-code | PROC | fixture | "
    "documented | [001](LL-001-PROC-One.md) |\n"
)
_FILLER = "Lorem ipsum filler text describing a fixture entry body in full. " * 90


def _generated_fixture(tmp_path, name: str) -> tuple:
    root = tmp_path / name
    lessons_dir = root / "planwise" / "LessonsLearned"
    posix_root = str(REAL_PLUGIN_ROOT).replace("\\", "/")
    config_yaml = f'plugin_root: "{posix_root}"\nplugin_version: "{TO}"\n' + CONFIG_YAML
    _write(root / "planwise" / "config.yaml", config_yaml)
    _write(lessons_dir / INDEX, _GENERATED_INDEX)
    cfg = InitConfig(project_name="e2e-lessons", project_root=root, plugin_root=REAL_PLUGIN_ROOT, plugin_version=TO)
    return cfg, lessons_dir


def test_within_budget_changelog_with_foreign_heading_and_fence_stays_silent(tmp_path, capsys):
    """A within-budget changelog carrying a non-Entry '## ' heading inside
    an entry (`## Drift Record`, matching the live project's own changelog
    shape) and a fenced `## Context` block: `_run_upgrade` stays silent
    (state `generated`), the changelog is untouched byte for byte, and
    `--report --json` agrees (`changelog_resplit: within_budget`,
    `would_refuse` empty) -- Findings 1 and 3."""
    cfg, lessons_dir = _generated_fixture(tmp_path, "silent")
    changelog_text = (
        f"[← {INDEX}]({INDEX})\n\n"
        "## Entry 2\n\n"
        "A short entry.\n\n"
        "## Drift Record\n\n"
        "Counter drift note, byte-built to reproduce the live tree's shape.\n\n"
        "```markdown\n"
        "## Context\n\n{What happened.}\n\n## Lesson\n\n{The fix.}\n"
        "```\n\n"
        "## Entry 1\n\n"
        "The oldest entry.\n\n"
    )
    _write(lessons_dir / CHANGELOG, changelog_text)
    before = changelog_text.encode("utf-8")

    exit_code = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    banner = capsys.readouterr().out

    assert exit_code == 0
    assert "REFUSED" not in banner
    assert (lessons_dir / CHANGELOG).read_bytes() == before

    config = _config(cfg)
    report = mig.build_report(config, lessons_dir / INDEX)
    assert report["changelog_resplit"] == "within_budget"
    assert report["would_refuse"] == []


def test_over_budget_changelog_with_foreign_heading_and_fence_resplits_conserving_bytes(tmp_path):
    """The same foreign-heading/fenced shape, but over budget: the resplit
    conserves every entry's bytes, including the inner `## Drift Record`
    heading and the fenced block, and never renumbers -- including the
    coincidental `## Entry 99` string inside the fence, which must never be
    mistaken for a real delimiter (Finding 1's fence-awareness requirement)."""
    cfg, lessons_dir = _generated_fixture(tmp_path, "resplit")
    special_body = (
        _FILLER + "\n\n"
        "## Drift Record\n\nCounter drift note, byte-built to reproduce the live tree's shape.\n\n"
        "```markdown\n## Entry 99\n\nA coincidental string that must never be treated as a real "
        "delimiter because it sits inside a fence.\n```\n"
    )
    lines = [f"[← {INDEX}]({INDEX})", ""]
    for n in range(30, 0, -1):
        body = special_body if n == 15 else _FILLER
        lines += [f"## Entry {n}", "", body, ""]
    _write(lessons_dir / CHANGELOG, "\n".join(lines) + "\n")

    exit_code = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    assert exit_code == 0

    files = sorted(lessons_dir.glob(f"{CHANGELOG[:-3]}*.md"))
    # A refusal leaves the single original file untouched, which would
    # trivially "conserve" every byte below without a resplit ever having
    # happened -- this is the gate the caveat closure requires, discriminating
    # proof recorded in the fix-loop summary's Gate Caveats subsection.
    assert len(files) >= 2
    family_text = "".join(read_text(p) for p in files)
    assert family_text.count("## Drift Record") == 1
    assert family_text.count("## Entry 99") == 1  # the fenced string survived, never split on
    # The fenced block moved intact, contiguously, with entry 15 -- proving the
    # fence contents (including the coincidental "## Entry 99" delimiter-shaped
    # line) were never parsed apart from their surrounding fence markers.
    assert "```markdown\n## Entry 99\n\nA coincidental" in family_text
    for n in range(1, 31):
        assert family_text.count(f"## Entry {n}\n\n") == 1, n  # every real entry, exactly once


def test_changelog_refusal_names_file_and_line_never_hand_authored(tmp_path, capsys):
    """A genuine refusal (text before the first entry heading that is not a
    backlink) names the changelog file and the 1-based line, and its fix
    text never claims the index is hand-authored -- it is generated; only
    the named changelog line is wrong (Finding 1's banner-text requirement).
    `--report --json` agrees: `changelog_resplit: refused`, the refusal is
    in `would_refuse`, and `ready_with_all_repairs` is false."""
    cfg, lessons_dir = _generated_fixture(tmp_path, "refused")
    lines = [f"[← {INDEX}]({INDEX})", "", "A rogue paragraph nobody wrapped in an entry.", ""]
    for n in range(30, 0, -1):
        lines += [f"## Entry {n}", "", _FILLER, ""]
    _write(lessons_dir / CHANGELOG, "\n".join(lines) + "\n")

    exit_code = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    banner = capsys.readouterr().out

    assert exit_code == 0  # a lessons refusal never changes _run_upgrade's own exit code
    assert "REFUSED" in banner
    assert CHANGELOG in banner
    assert "line 3" in banner
    assert "hand-authored" not in banner

    config = _config(cfg)
    report = mig.build_report(config, lessons_dir / INDEX)
    assert report["changelog_resplit"] == "refused"
    assert any(CHANGELOG in item for item in report["would_refuse"])
    assert report["ready_with_all_repairs"] is False


def _changelog_numbers(lessons_dir: Path) -> list:
    """Every `## Entry N` number in family order: main, archive, parts."""
    stem = CHANGELOG[:-3]
    parts = sorted(lessons_dir.glob(f"{stem}-Archive-*-Part-*.md"))
    files = [lessons_dir / CHANGELOG, *sorted(set(lessons_dir.glob(f"{stem}-Archive-*.md")) - set(parts)), *parts]
    return [int(n) for p in files for n in re.findall(r"^## Entry (\d+)", read_text(p), re.MULTILINE)]


def test_migrated_multi_entry_family_then_append_keeps_numbers_stable(tmp_path, monkeypatch):
    """A legacy index whose header history spills the migrated changelog into
    an archive: the migrator numbers the whole family N..1 (never restarting
    at 1 in the archive), and `--append` then adds N+1 on top."""
    cfg, lessons_dir = _project(tmp_path, dirty=False)
    history = ("<!-- Previous: 2024-06-06 the newest earlier history -->\n"
               f"<!-- Previous: 2024-05-05 {'y' * 30_000} -->\n"
               f"<!-- Previous: 2024-04-04 {'z' * 30_000} -->\n")
    index = _seed_index().replace("**Last Updated:** YYYY-MM-DD\n", "**Last Updated:** YYYY-MM-DD\n" + history, 1)
    _write(lessons_dir / INDEX, _crlf(index))
    cfg = _pin(cfg, FROM)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    assert artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None) == 0
    assert "Generated:" in read_text(lessons_dir / INDEX)
    numbers = _changelog_numbers(lessons_dir)
    # The archive year is the run's own date, so the archive is located by glob.
    assert len(sorted(lessons_dir.glob(f"{CHANGELOG[:-3]}-Archive-*.md"))) >= 1
    assert numbers == list(range(len(numbers), 0, -1)) and len(numbers) >= 4

    config_path = cfg.project_root / "planwise" / "config.yaml"
    assert lessons_changelog.main(["--config", str(config_path), "--append", "probe"]) == 0
    assert _changelog_numbers(lessons_dir) == list(range(len(numbers) + 1, 0, -1))


def test_migrated_family_is_a_fixed_point_of_the_next_upgrade(tmp_path, monkeypatch):
    """Re-review F9 guard: the migrator lays the changelog out through the
    writer's own engine, so the next upgrade's `plan_split` -- which parses
    this family, because one entry is over the page cap -- finds nothing to
    move, and the second upgrade leaves every changelog file byte-identical."""
    cfg, lessons_dir = _project(tmp_path, dirty=False)
    history = ("<!-- Previous: 2024-06-06 the newest earlier history -->\n"
               f"<!-- Previous: 2024-05-05 {'y' * 30_000} -->\n"
               f"<!-- Previous: 2024-04-04 {'o' * 70_000} -->\n")
    index = _seed_index().replace("**Last Updated:** YYYY-MM-DD\n", "**Last Updated:** YYYY-MM-DD\n" + history, 1)
    _write(lessons_dir / INDEX, _crlf(index))
    cfg = _pin(cfg, FROM)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])
    assert artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None) == 0
    assert lessons_changelog.plan_split(_config(cfg), lessons_dir / INDEX) is None
    family = {p.name: p.read_bytes() for p in lessons_dir.glob(f"{CHANGELOG[:-3]}*.md")}
    assert len(family) >= 2
    assert artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None) == 0
    assert {p.name: p.read_bytes() for p in lessons_dir.glob(f"{CHANGELOG[:-3]}*.md")} == family


def test_legacy_positional_family_is_renumbered_by_upgrade_then_silent(tmp_path, capsys):
    """An earlier migrator's positional family (newest is Entry 1, the
    archive restarts at 1), within budget: upgrade #1 renumbers it once by
    position under `changelog_split`, and upgrade #2 is silent and
    byte-identical. `--report` agrees before and after."""
    cfg, lessons_dir = _generated_fixture(tmp_path, "positional")
    archive = f"{CHANGELOG[:-3]}-Archive-2026.md"
    back, arch_back = f"[← {INDEX}]({INDEX})", f"[← {CHANGELOG}]({CHANGELOG})"
    pointer = f"Older entries: [{archive}]({archive})"

    def main_bytes(nums):
        return (f"{back}\r\n\r\n" + "".join(f"## Entry {n}\r\n\r\nMain body {i}.\r\n\r\n" for i, n in enumerate(nums))
                + f"{pointer}\r\n").encode()

    def archive_bytes(nums):
        return (f"{arch_back}\r\n\r\n{back}\r\n\r\n"
                + "".join(f"## Entry {n}\r\n\r\nArchive body {i}.\r\n\r\n" for i, n in enumerate(nums))).encode()

    _write(lessons_dir / CHANGELOG, main_bytes([1, 2, 3, 4, 5]))
    _write(lessons_dir / archive, archive_bytes([1, 2, 3]))
    config = _config(cfg)
    before = mig.build_report(config, lessons_dir / INDEX)
    assert (before["changelog_resplit"], before.get("changelog_renumber")) == ("would_split", True)

    assert artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None) == 0
    banner = capsys.readouterr().out
    assert "Lessons changelog: renumbered 8 entries by position (the oldest is Entry 1)" in banner
    assert (lessons_dir / CHANGELOG).read_bytes() == main_bytes([8, 7, 6, 5, 4])
    assert (lessons_dir / archive).read_bytes() == archive_bytes([3, 2, 1])
    after = mig.build_report(config, lessons_dir / INDEX)
    assert (after["changelog_resplit"], after.get("changelog_renumber")) == ("within_budget", False)

    snapshot = _snapshot(cfg.project_root)
    assert artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None) == 0
    assert "Lessons changelog" not in capsys.readouterr().out
    assert _snapshot(cfg.project_root) == snapshot


_DIVERGED_MARKER = ("\n\nNote: this project's own historical Lesson File Template guidance, "
                    "diverged from the shipped seed on purpose for this test.\n")


def _project_with_diverged_template(tmp_path):
    """`_project`'s Fixture A, except the Lesson File Template section's
    body is edited to no longer equal the shipped seed's -- forcing
    `section_disposition` to "relocate" it (as prose, fenced `## Context`
    etc. intact) instead of "drop" it, so the golden idempotency case below
    actually drives the real relocation path Finding 2 named, not a
    synthetic stand-in."""
    root = tmp_path / "diverged"
    lessons_dir = root / "planwise" / "LessonsLearned"
    _write(root / "planwise" / "config.yaml", CONFIG_YAML)
    seed_text = _seed_index()
    marker = "{When this lesson is relevant — technologies, file patterns, scenarios.}"
    diverged = seed_text.replace(marker, marker + _DIVERGED_MARKER, 1)
    assert diverged != seed_text  # the replace actually fired
    _write(lessons_dir / INDEX, _crlf(diverged))
    _write(lessons_dir / LL1, LL1_TEXT)
    _write(lessons_dir / LL2, LL2_TEXT)
    _write(lessons_dir / LL3, _crlf(LL3_TEXT))
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "fixture")
    cfg = InitConfig(project_name="e2e-lessons", project_root=root, plugin_root=REAL_PLUGIN_ROOT)
    return cfg, lessons_dir


def test_golden_idempotency_with_relocated_fenced_template(tmp_path, monkeypatch, capsys):
    """The relocated fenced Lesson File Template lands in the changelog as
    prose. A second `_run_upgrade` at the same pair is silent, with every
    file byte-identical, including the fenced template's own
    `## Context`/`## Lesson`/`## Applies To` headings (Finding 2)."""
    cfg, lessons_dir = _project_with_diverged_template(tmp_path)
    cfg = _pin(cfg, FROM)
    monkeypatch.setattr(artifact_upgrade, "INSTALLED_RULES", [])

    exit_code = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    assert exit_code == 0
    changelog = read_text(lessons_dir / CHANGELOG)
    assert "## Context" in changelog and "## Lesson" in changelog and "## Applies To" in changelog

    after_first = _snapshot(cfg.project_root)
    capsys.readouterr()  # discard the first run's own banner before capturing the second
    exit_code2 = artifact_upgrade._run_upgrade(cfg, lessons_reconcile=None)
    second_out = capsys.readouterr().out
    assert exit_code2 == 0
    assert _snapshot(cfg.project_root) == after_first
    # A refused second run also writes nothing, which would trivially satisfy
    # the byte-identical check above for the wrong reason -- a truly silent
    # `generated` state prints no banner at all, while a `refused` state
    # prints one (SILENT_STATES = ("absent", "generated")); this is the gate
    # the caveat closure requires. Discriminating proof recorded in the
    # fix-loop summary's Gate Caveats subsection.
    assert "Lessons index migration" not in second_out


# ---------------------------------------------------------------------------
# Path 2: fresh init_project.main() into a directory already holding the
# legacy lessons tree.
# ---------------------------------------------------------------------------
def test_path2_init_migrates_legacy_lessons_end_to_end(tmp_path, capsys):
    cfg, lessons_dir = _project(tmp_path, seed_openers=False, dirty=False)
    original_ll1 = (lessons_dir / LL1).read_bytes()
    old_argv = sys.argv[:]
    sys.argv = ["init_project.py", "--name", "e2e-init", "--project-root", str(cfg.project_root)]
    try:
        ip.main()
    finally:
        sys.argv = old_argv
    banner = capsys.readouterr().out
    pair = f"init-to-{TO}"

    # The bootstrap (here, `copy_seed_files`, which runs first and only
    # creates a file `xb`-exclusively, so it never overwrites the
    # pre-existing legacy index) seeded the changelog before the migrator
    # ran: its backup pre-image is header-only, byte-exact to the plugin's
    # own changelog seed.
    backups = _backups(cfg, pair)
    assert backups.joinpath(CHANGELOG).read_bytes() == CHANGELOG_HEADER_ONLY
    assert backups.joinpath(LL1).read_bytes() == original_ll1

    assert "Lessons index migration:" in banner and "migrated:" in banner
    hub = read_text(lessons_dir / INDEX)
    assert "Generated:" in hub
    config = _config(cfg)
    parsed = parse_lessons.parse_index(config)
    assert parsed.shape == "generated" and len(parsed.rows) == 3
    index_exit, companion_exit = _check_exits(cfg)
    assert (index_exit, companion_exit) == (0, 0)
    promo = read_text(lessons_dir / PROMO_ARCHIVE)
    assert "LL-003" in promo
    ledger = json.loads(read_text(lessons_dir / LEDGER))
    assert ledger["unaccounted"] == 0


def test_path2_refusal_prints_skipped_artifact(tmp_path, capsys):
    """The refusal fixture at init: a `SkippedArtifact` row prints under
    "Skipped (action required)", naming the index and the fix."""
    cfg, lessons_dir = _project(tmp_path, seed_openers=False, dirty=False, omit_ll002=True)
    old_argv = sys.argv[:]
    sys.argv = ["init_project.py", "--name", "e2e-init", "--project-root", str(cfg.project_root)]
    try:
        ip.main()
    finally:
        sys.argv = old_argv
    banner = capsys.readouterr().out

    assert "Skipped (action required):" in banner
    assert str(lessons_dir / INDEX) in banner
    assert "re-run /planwise upgrade" in banner or "close each refusal" in banner
    assert not (cfg.project_root / "planwise" / "upgrade-backups" / f"init-to-{TO}" / "lessons").exists()
