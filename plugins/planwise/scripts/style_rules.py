"""Always-on style rules: the rule table, the config switch, and the installer.

This module is a leaf. It is imported by the init, upgrade and doctor modules,
so it must never import any of them back, not even at module level. Importing
one of them here would close a cycle, because each of them imports this module
while it is still being initialised. The only sibling imports are `constants`
and `upgrade_io` (neither imports an entry-point module) and a lazy import of
`rule_divergence` inside the one function that needs it.

Two global rules ship under `references/` without a `paths:` line. They install
under `<.claude>/rules/planwise/`, where `<.claude>` is the user directory for
the `user` install scope and the project directory otherwise. The `style:`
config block switches each rule on or off, and an absent key means on.

The duplicate search walks both `.claude/rules/` trees (project and home)
recursively, at any depth, and matches the file name ignoring case. It excludes
exactly one path, the install target itself, so a re-run never reports its own
earlier copy as a duplicate. Every other same-named file counts, including one
inside a subdirectory. The walk records which tree reached each hit, and that
record, never the resolved path, decides whether the hit blocks. Each hit
carries a verdict: `identical`, or the shared rule-divergence classifier's own
verdict string, or `NOT_ANALYZED` when the file cannot be compared.

At `project` and `local` scope, any hit stops the install. At `user` scope only
a copy in the home tree stops it. A copy that exists only in the project tree
never blocks a global install. The global copy is written, and each project
copy is reported so the caller can warn that the project loads both. Init never
overwrites an existing file.
"""

import sys
from pathlib import Path

from constants import InstallScope
from upgrade_io import _load_raw_config

# (shipped filename under references/, key under the `style:` config block)
STYLE_RULES: list[tuple[str, str]] = [
    ("plain-language.md", "plain_language"),
    ("plain-presentation.md", "plain_presentation"),
]

_ON = ("on", "true")
_OFF = ("off", "false")


def style_rule_dir(cfg) -> Path:
    """Directory that holds the managed copies for this install scope.

    `Path.home()` is called on every call, never at import time, so a test can
    redirect the home directory.
    """
    if cfg.install_scope == InstallScope.USER:
        return Path.home() / ".claude" / "rules" / "planwise"
    return cfg.project_root / ".claude" / "rules" / "planwise"


def _read_normalized(path: Path) -> str:
    """Read a rule file as `utf-8-sig` and strip the `paths:` key."""
    from rule_divergence import normalize_rule_for_diff

    return normalize_rule_for_diff(path.read_text(encoding="utf-8-sig"))


def _verdict(shipped: Path, installed: Path) -> str:
    """`identical` when both normalise to equal text, else `diverged`.

    An unreadable file on either side counts as `diverged`.
    """
    try:
        same = _read_normalized(shipped) == _read_normalized(installed)
    except (OSError, ValueError):
        return "diverged"
    return "identical" if same else "diverged"


_NOT_ANALYZED = "NOT_ANALYZED"


def _classify_copy(shipped: Path, found: Path) -> str:
    """Verdict for one found copy against the shipped rule.

    `identical` when both normalise to equal text. Otherwise the shared
    classifier's verdict string, unchanged. `NOT_ANALYZED` when either file is
    unreadable or the classifier returns its degraded stand-in.
    """
    from rule_divergence import _classify_diverged, _verdict_not_analyzed

    try:
        shipped_norm = _read_normalized(shipped)
        found_norm = _read_normalized(found)
    except (OSError, ValueError):
        return _NOT_ANALYZED
    if shipped_norm == found_norm:
        return "identical"
    verdict = _classify_diverged(found_norm, shipped_norm)
    if _verdict_not_analyzed(verdict):
        return _NOT_ANALYZED
    return verdict.classification


def _rules_trees(cfg) -> list[Path]:
    """The two `.claude/rules/` trees to search: project first, then home."""
    return [
        cfg.project_root / ".claude" / "rules",
        Path.home() / ".claude" / "rules",
    ]


def _named_files(tree: Path, filename: str) -> list[Path]:
    """Every file under `tree` whose name equals `filename`, ignoring case.

    The match is case-insensitive on every platform, because a case-sensitive
    filesystem can hold `Plain-Language.md` next to `plain-language.md` and a
    case-insensitive one cannot tell them apart. The result is sorted.
    """
    wanted = filename.casefold()
    return sorted(p for p in tree.rglob("*") if p.name.casefold() == wanted and p.is_file())


def _tagged_copies(cfg, filename: str) -> list[tuple[Path, str, bool]]:
    """Every same-named rule as `(path, verdict, found_in_home_tree)`.

    The tag records which tree the walk reached the file through. Blocking is
    decided from the tag and never from the resolved path, because a home-tree
    entry that is a symlink resolves outside the home tree. A file reachable
    through both trees carries the home tag.
    """
    shipped = shipped_path(cfg, filename)
    target = installed_path(cfg, filename).resolve()
    project_tree, home_tree = _rules_trees(cfg)
    index: dict[Path, int] = {}
    hits: list[tuple[Path, str, bool]] = []
    for tree, in_home in ((project_tree, False), (home_tree, True)):
        if not tree.is_dir():
            continue
        for candidate in _named_files(tree, filename):
            resolved = candidate.resolve()
            if resolved == target:
                continue
            if resolved in index:
                if in_home:
                    path, verdict, _tag = hits[index[resolved]]
                    hits[index[resolved]] = (path, verdict, True)
                continue
            index[resolved] = len(hits)
            hits.append((candidate, _classify_copy(shipped, candidate), in_home))
    return hits


def find_existing_copies(cfg, filename: str) -> list[tuple[Path, str]]:
    """Every same-named rule under the project and home `.claude/rules/` trees.

    Searches both trees recursively, matches the name ignoring case, and skips
    a tree that does not exist. The install target is excluded by resolved-path
    equality, and a file reached twice counts once. Project-tree hits come
    first, then home-tree hits, each group sorted. Each hit is `(path, verdict)`.
    """
    return [(path, verdict) for path, verdict, _in_home in _tagged_copies(cfg, filename)]


def _first_blocking(cfg, hits: list[tuple[Path, str, bool]]) -> tuple[Path, str] | None:
    """The first tagged hit that stops an install at this scope, or None.

    At `project` and `local` scope every hit blocks. At `user` scope only a hit
    found through the home tree blocks.
    """
    for path, verdict, in_home in hits:
        if cfg.install_scope != InstallScope.USER or in_home:
            return path, verdict
    return None


def find_existing_copy(cfg, filename: str) -> tuple[Path, str] | None:
    """The first same-named rule that stops an install at this scope, or None.

    A project-tree copy never stops a `user` install. See `find_existing_copies`
    for the search and the verdict strings.
    """
    return _first_blocking(cfg, _tagged_copies(cfg, filename))


def parse_switch(value, default: bool = True) -> bool:
    """Read an on/off switch. Anything unrecognised returns `default`."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _ON:
            return True
        if lowered in _OFF:
            return False
    return default


def get_style_config(config) -> dict[str, bool]:
    """Return both `style.*` switches, each defaulting to True."""
    block = config.get("style") if isinstance(config, dict) else None
    if not isinstance(block, dict):
        block = {}
    return {key: parse_switch(block.get(key), True) for _, key in STYLE_RULES}


def enabled_style_rules(cfg) -> list[tuple[str, str]]:
    """The `STYLE_RULES` entries whose config switch is on."""
    switches = get_style_config(_load_raw_config(cfg))
    return [(name, key) for name, key in STYLE_RULES if switches[key]]


def shipped_path(cfg, filename: str) -> Path:
    """The shipped copy under the plugin's `references/` directory."""
    return cfg.plugin_root / "references" / filename


def installed_path(cfg, filename: str) -> Path:
    """The managed installed copy for this install scope."""
    return style_rule_dir(cfg) / filename


def compare_installed(cfg, filename: str) -> str:
    """`absent`, `identical` or `diverged` for the managed installed copy."""
    dst = installed_path(cfg, filename)
    if not dst.is_file():
        return "absent"
    return _verdict(shipped_path(cfg, filename), dst)


def install_style_rules(cfg) -> tuple[list[str], list[tuple[str, Path, str, bool]]]:
    """Install each enabled rule by copying the shipped bytes unchanged.

    Returns `(installed filenames, reports)`. Each report is
    `(filename, path, verdict, installed)`.

    A blocking duplicate (see `find_existing_copy`) writes nothing and adds one
    report with `installed=False`. A `user`-scope install that proceeds adds one
    report with `installed=True` for each project-tree copy. An existing managed
    copy is never overwritten. A rule whose directory or file cannot be written
    prints one warning to stderr and is skipped, and the next rule still runs.
    """
    installed: list[str] = []
    reports: list[tuple[str, Path, str, bool]] = []
    for filename, _key in enabled_style_rules(cfg):
        hits = _tagged_copies(cfg, filename)
        blocking = _first_blocking(cfg, hits)
        if blocking is not None:
            reports.append((filename, blocking[0], blocking[1], False))
            continue
        src = shipped_path(cfg, filename)
        try:
            data = src.read_bytes()
        except FileNotFoundError:
            print(f"  Warning: reference not found: {src}", file=sys.stderr)
            continue
        dst = installed_path(cfg, filename)
        try:
            # The user-scope directory sits outside the tree that init creates.
            dst.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"  Warning: could not create {dst.parent} for {filename}: {exc}", file=sys.stderr)
            continue
        try:
            with open(dst, "xb") as f:
                f.write(data)
        except FileExistsError:
            continue
        except OSError as exc:
            # A partial file is left in place: the upgrade refresh repairs it.
            print(f"  Warning: could not write {dst} for {filename}: {exc}", file=sys.stderr)
            continue
        installed.append(filename)
        # Reaching here at `user` scope means every hit is a project-tree copy.
        reports.extend((filename, path, verdict, True) for path, verdict, _in_home in hits)
    return installed, reports


_COPY_DESCRIPTIONS = {
    "identical": "an identical copy",
    "HAS_UNIQUE": "a customized copy",
    "SUBSET": "an older copy",
    _NOT_ANALYZED: "a copy that could not be compared",
}


def format_duplicate_line(filename: str, path, verdict: str, installed: bool = False) -> str:
    """The one message every caller prints for a reported duplicate.

    An unrecognised verdict reads as a customized copy, the conservative choice.
    """
    desc = _COPY_DESCRIPTIONS.get(verdict, "a customized copy")
    if installed:
        return (
            f"Style rule {filename}: installed for all projects, but {desc} also exists "
            f"at {path}; that project loads both until /planwise upgrade reconciles them."
        )
    return f"Style rule {filename}: not installed, {desc} exists at {path}."
