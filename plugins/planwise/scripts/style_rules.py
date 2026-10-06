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

An upgrade reconciles each rule with its switch (`reconcile_style_switches`) and
keeps one copy of an enabled rule per scope pair (`sync_cross_scope`). Both
return `(filename, disposition, detail)` rows that `format_reconcile_lines`
turns into printable lines. An edited managed copy is never overwritten or
deleted here, and every overwrite or delete follows a successful backup.
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


def _is_switch(value) -> bool:
    """True when `value` is a boolean or one of the accepted on/off words."""
    if isinstance(value, bool):
        return True
    return isinstance(value, str) and value.strip().lower() in _ON + _OFF


def get_style_config(config, warn: bool = False) -> dict[str, bool]:
    """Return both `style.*` switches, each defaulting to True.

    A malformed value or an unknown key never turns a rule off. With `warn` set,
    each one prints a single stderr warning naming the key and the value and
    saying the rules are treated as on.
    """
    block = config.get("style") if isinstance(config, dict) else None
    problems: list[str] = []
    if block is not None and not isinstance(block, dict):
        problems.append(f"style is {block!r}, not a block of keys")
    if not isinstance(block, dict):
        block = {}
    known = {key for _, key in STYLE_RULES}
    for key, value in block.items():
        if key in known and not _is_switch(value):
            problems.append(f"style.{key} is {value!r}, not on or off")
        elif key not in known:
            problems.append(f"style.{key} is not a known key (value {value!r})")
    if warn:
        for problem in problems:
            print(f"  Warning: {problem}; treated as on.", file=sys.stderr)
    return {key: parse_switch(block.get(key), True) for _, key in STYLE_RULES}


def enabled_style_rules(cfg) -> list[tuple[str, str]]:
    """The `STYLE_RULES` entries whose config switch is on."""
    switches = get_style_config(_load_raw_config(cfg))
    return [(name, key) for name, key in STYLE_RULES if switches[key]]


def other_managed_path(cfg, filename: str) -> Path:
    """The managed path in the scope that is not this install scope's target.

    At `user` scope that is the project's managed path. At `project` and `local`
    scope it is the home managed path. The cross-scope sync owns a rule only when
    this path holds a file, so the version-change refresh leaves such a rule alone.
    """
    target = installed_path(cfg, filename).resolve()
    project_tree, home_tree = _rules_trees(cfg)
    project_copy, home_copy = project_tree / "planwise" / filename, home_tree / "planwise" / filename
    return home_copy if project_copy.resolve() == target else project_copy


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


_STILL_LOAD = "still load"


def _reconcile_one(cfg, filename: str, on: bool, from_version: str, to_version: str,
                   on_version_change: bool = False) -> tuple[str, str, str]:
    """One `(filename, disposition, detail)` row for a rule and its switch."""
    from upgrade_io import _append_disposition_log, _write_backup_preimage

    src = shipped_path(cfg, filename)
    dst = installed_path(cfg, filename)
    if not src.is_file():
        print(f"  Warning: reference not found: {src}", file=sys.stderr)
        return filename, "skipped", f"shipped reference not found: {src}"
    state = compare_installed(cfg, filename)
    if on:
        found = find_existing_copy(cfg, filename)
        if found is not None:
            line = format_duplicate_line(filename, found[0], found[1]).removeprefix(
                f"Style rule {filename}: ")
            if state == "identical":
                line += f" The identical managed copy at {dst} is left in place."
            return filename, "duplicate", line
        if state == "absent":
            data = src.read_bytes()
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(dst, "xb") as f:
                    f.write(data)
            except FileExistsError:
                return filename, "unchanged", f"{dst} appeared during the run and was left alone"
            return filename, "installed", f"wrote {dst}"
        if state == "identical":
            return filename, "unchanged", f"{dst} matches the shipped file"
        if on_version_change and not other_managed_path(cfg, filename).is_file():
            return filename, "customized", f"the edited copy at {dst} goes through the customization handoff in this run"
        return filename, "customized", f"the edited copy at {dst} is kept"
    # The key is off: a copy in the other scope's tree keeps loading, so name it.
    others = find_existing_copies(cfg, filename)
    note = f"; other copies {_STILL_LOAD}: " + ", ".join(str(p) for p, _v in others) if others else ""
    if state == "absent":
        return filename, "skipped", "the key is off and no managed copy exists" + note
    if state == "diverged":
        return filename, "preserved", f"the edited copy at {dst} is kept although the key is off" + note
    if dst.is_symlink():
        return filename, "symlink", f"{dst} is a symlink, so it was not removed" + note
    # The key is off and the copy matches the shipped file: back it up, then delete it.
    if not _write_backup_preimage(cfg, from_version, to_version, dst):
        return filename, "preserved", f"the backup of {dst} failed, so the copy was not removed" + note
    dst.unlink()
    _append_disposition_log(
        cfg, from_version, to_version, dst, "removed",
        "the style switch is off and the copy matched the shipped file")
    return filename, "removed", f"deleted {dst} after writing a backup" + note


def reconcile_style_switches(cfg, from_version: str, to_version: str,
                             on_version_change: bool = False) -> list[tuple[str, str, str]]:
    """Act on each style rule's config switch for this install scope.

    Returns one `(filename, disposition, detail)` row per `STYLE_RULES` entry.
    Dispositions: `duplicate`, `installed`, `unchanged`, `customized`, `skipped`,
    `removed`, `preserved`, `symlink` for a copy that is a symlink, and `failed`
    for an `OSError` on one file. An edited copy under an `on` key is reported as
    `customized` and left for the artifact refresh to resolve. `on_version_change`
    says that refresh runs in this same invocation, so the detail names the
    customization handoff instead of saying the copy is kept. A copy is deleted
    only after its backup succeeded. A second run on an agreeing state writes
    nothing. A malformed switch value or unknown key prints one stderr warning.
    """
    switches = get_style_config(_load_raw_config(cfg), warn=True)
    rows: list[tuple[str, str, str]] = []
    for filename, key in STYLE_RULES:
        try:
            rows.append(_reconcile_one(cfg, filename, switches[key], from_version, to_version,
                                       on_version_change))
        except OSError as exc:
            rows.append((filename, "failed", f"could not reconcile: {exc}"))
    return rows


def format_reconcile_lines(rows) -> list[str]:
    """One printable line per row that did something, in row order.

    Rows whose disposition is `unchanged` or `skipped` print nothing, so a run
    with nothing to report returns an empty list. A `skipped` row that names
    copies which still load is the one exception.
    """
    return [
        f"Style rule {filename}: {disposition} — {detail}"
        for filename, disposition, detail in rows
        if disposition != "unchanged" and (disposition != "skipped" or _STILL_LOAD in detail)
    ]


def _has_edits(shipped: Path, copy: Path) -> bool:
    """True unless `copy` equals the shipped rule or is a stale copy safe to replace.

    A copy carries no edits only when its normalised text equals the shipped
    text, or the shared gate for destructive overwrites accepts its verdict. A
    `paths:` value that differs from the shipped one always counts as an edit. An
    unreadable or never-analysed copy counts as edited, the conservative choice.
    """
    from rule_divergence import (
        _classify_diverged,
        _destructively_removable,
        _extract_paths_value,
        _verdict_not_analyzed,
        normalize_rule_for_diff,
    )

    try:
        shipped_text = shipped.read_text(encoding="utf-8-sig")
        copy_text = copy.read_text(encoding="utf-8-sig")
    except (OSError, ValueError):
        return True
    if _extract_paths_value(shipped_text) != _extract_paths_value(copy_text):
        return True
    shipped_norm, copy_norm = normalize_rule_for_diff(shipped_text), normalize_rule_for_diff(copy_text)
    if shipped_norm == copy_norm:
        return False
    verdict = _classify_diverged(copy_norm, shipped_norm)
    return _verdict_not_analyzed(verdict) or not _destructively_removable(verdict)


def _canonical(path: Path) -> tuple[str, str | None]:
    """The text of a copy as the sync compares it: `paths:` apart, endings and BOM ignored."""
    from rule_divergence import _extract_paths_value

    text = path.read_text(encoding="utf-8-sig")
    return _read_normalized(path), _extract_paths_value(text)


def _overwrite_copy(cfg, from_version: str, to_version: str, filename: str,
                    target: Path, source: Path, reason: str) -> tuple[str, str, str]:
    """Back up `target`, replace its bytes with those of `source`, then log it.

    A failed backup leaves `target` untouched. The log row is written only after
    the write succeeded. A symlinked `target` is never written.
    """
    from upgrade_io import (
        _append_disposition_log,
        _copy_bytes_exact,
        _write_backup_preimage,
    )

    if target.is_symlink():
        return filename, "symlink", f"{target} is a symlink, so it was not overwritten"
    if not _write_backup_preimage(cfg, from_version, to_version, target):
        return filename, "failed", f"the backup of {target} failed, so it was not overwritten"
    try:
        _copy_bytes_exact(source, target)
    except OSError as exc:
        return filename, "failed", f"could not write {target} after its backup: {exc}"
    _append_disposition_log(cfg, from_version, to_version, target, "synced across scopes", reason)
    return filename, "synced", f"{target} now matches {source} ({reason})"


def _sync_one(cfg, filename: str, src: Path, from_version: str, to_version: str) -> list[tuple[str, str, str]]:
    """Rows for one enabled rule held in both managed paths.

    The sync reads and writes `<project>/.claude/rules/planwise/<file>` and
    `~/.claude/rules/planwise/<file>` only. Any other same-name copy is never a
    source or a target. The detail of each row names it.
    """
    project_copy, home_copy = (tree / "planwise" / filename for tree in _rules_trees(cfg))
    if not (project_copy.is_file() and home_copy.is_file()):
        return []
    managed = {project_copy.resolve(), home_copy.resolve()}
    if len(managed) < 2:
        return []
    others = sorted({p for tree in _rules_trees(cfg) if tree.is_dir()
                     for p in _named_files(tree, filename) if p.resolve() not in managed})
    note = "; other same-name copies were not read or changed: " + ", ".join(map(str, others)) if others else ""
    return [(name, disposition, detail + note)
            for name, disposition, detail in _sync_pair(cfg, filename, src, project_copy, home_copy,
                                                        from_version, to_version)]


def _sync_pair(cfg, filename: str, src: Path, project_copy: Path, home_copy: Path,
               from_version: str, to_version: str) -> list[tuple[str, str, str]]:
    """Rows for the two managed copies of one rule: edits win, else the shipped file."""
    project_edited = _has_edits(src, project_copy)
    home_edited = _has_edits(src, home_copy)
    project_text, home_text, shipped_text = _canonical(project_copy), _canonical(home_copy), _canonical(src)
    # An identical pair (line endings and a BOM ignored) is left alone when it is edited
    # or already shipped. An identical unedited stale pair falls through and is refreshed.
    if project_text == home_text and (project_edited or project_text == shipped_text):
        return [(filename, "unchanged", "both copies are identical")]
    if project_edited and home_edited:
        detail = (
            "both copies carry different edits, so neither was overwritten: "
            f"{project_copy} and {home_copy}"
        )
        return [(filename, "conflict", detail)]
    if project_edited or home_edited:
        source, target = (project_copy, home_copy) if project_edited else (home_copy, project_copy)
        return [_overwrite_copy(cfg, from_version, to_version, filename, target, source,
                                f"the edited copy at {source} wins")]
    rows = [
        _overwrite_copy(cfg, from_version, to_version, filename, copy, src,
                        "neither copy carries edits, so both follow the shipped file")
        for copy, text in ((project_copy, project_text), (home_copy, home_text)) if text != shipped_text
    ]
    return rows or [(filename, "unchanged", "both copies already match the shipped file")]


def sync_cross_scope(cfg, from_version: str, to_version: str) -> list[tuple[str, str, str]]:
    """Keep one copy of each enabled rule across the project and home trees.

    Applies only to a rule whose key is `on` and that has a copy in both
    `.claude/rules/planwise/` directories. Edits win, else the shipped file:
    exactly one edited copy is propagated to the other, two unedited copies are
    rewritten with the shipped bytes, and two differently edited copies are
    reported and left alone. Copies are compared with line endings and a BOM
    ignored. Any other same-name copy is never read or written, and the row
    names it. A copy that is a symlink is never written and gets a `symlink`
    row. Each overwrite backs up the old bytes first and logs it after the
    write. This function never writes `config.yaml`.
    """
    switches = get_style_config(_load_raw_config(cfg))
    rows: list[tuple[str, str, str]] = []
    for filename, key in STYLE_RULES:
        src = shipped_path(cfg, filename)
        if not switches[key] or not src.is_file():
            continue
        try:
            rows.extend(_sync_one(cfg, filename, src, from_version, to_version))
        except (OSError, ValueError) as exc:
            rows.append((filename, "failed", f"cross-scope sync stopped: {exc}"))
    return rows


def style_announcement(cfg, added_keys) -> list[str]:
    """The one-time notice printed when this upgrade added the `style:` block.

    Returns an empty list unless `"style"` is in `added_keys` (the top-level keys
    `migrate_config` added in this run). Otherwise returns six lines: what was
    installed, the per-rule and combined token cost, and the two keys that turn a
    rule off. Token counts come from the shipped file sizes through
    `read_limits.estimate_tokens`. A missing shipped file prints `unknown` for
    its number, and the combined figure is then `unknown` too. The notice states
    the default only. The reconcile lines state what happened in this project.
    """
    if "style" not in (added_keys or ()):
        return []
    from read_limits import estimate_tokens

    counts: list[int | None] = []
    for filename, _key in STYLE_RULES:
        try:
            counts.append(estimate_tokens(shipped_path(cfg, filename).stat().st_size))
        except OSError:
            counts.append(None)
    total = "unknown" if None in counts else str(sum(c for c in counts if c is not None))
    width = max(len(name) for name, _key in STYLE_RULES)
    lines = ["Style rules: planwise now installs two global rules, on by default."]
    for (filename, _key), count in zip(STYLE_RULES, counts, strict=True):
        lines.append(f"  {filename:<{width}}  about {'unknown' if count is None else count} tokens per session")
    lines.append(f"Together they add about {total} tokens to every session, subagents included.")
    lines.append(
        f"To turn one off, set it to off under `style:` in {cfg.planwise_root}/config.yaml, "
        "then run /planwise upgrade."
    )
    lines.append("Keys: " + ", ".join(f"style.{key}" for _name, key in STYLE_RULES))
    return lines
