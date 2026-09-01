"""Artifact refresh + plugin-version upgrade orchestration.

Owns the `--upgrade` writer: refreshing shipped-tracked artifacts whose
upgrade_behavior is `refresh_or_sidecar`, repointing/committing the plugin
version pin, and driving the one-shot de-scope migration (rule_descope_migration)
as the final step of an upgrade pass.
"""

import os
import re
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from config_gen import (
        InitConfig,  # noqa: F401 -- type-hint only (quoted forward refs)
        get_upgrade_config,
        write_config_checked,
        migrate_config,
        _flip_token_saver_on,
    )
except ImportError:
    raise ImportError(
        "config_gen is required for artifact_upgrade's config-write/migrate "
        "helpers; the scripts/ directory appears to be partially installed"
    )

try:
    from upgrade_io import (
        _load_verdicts_cache,
        _load_verdict_override,
        _write_backup_preimage,
        _append_disposition_log,
        _load_raw_config,
        _transfer_customization,
    )
except ImportError:
    raise ImportError(
        "upgrade_io is required for artifact_upgrade's backup/disposition/"
        "transfer primitives; the scripts/ directory appears to be partially "
        "installed"
    )

try:
    from rule_divergence import (
        is_subset,
        _classify_diverged,
        normalize_rule_for_diff,
        _verdict_not_analyzed,
        _extract_paths_value,
    )
except ImportError:
    raise ImportError(
        "rule_divergence is required for artifact_upgrade's structural-verdict "
        "classification; the scripts/ directory appears to be partially "
        "installed"
    )

try:
    from rule_descope_migration import migrate_installed_rules
except ImportError:
    raise ImportError(
        "rule_descope_migration is required for artifact_upgrade's post-refresh "
        "de-scope migration step; the scripts/ directory appears to be "
        "partially installed"
    )

try:
    from doctor_sweeps import lint_rule_overscope
except ImportError:
    raise ImportError(
        "doctor_sweeps is required for artifact_upgrade's post-upgrade overscope "
        "advisory; the scripts/ directory appears to be partially installed"
    )

try:
    from init_project import (
        INSTALLED_RULES,
        resolve_rule_paths_value,
        update_frontmatter,
    )
except ImportError:
    raise ImportError(
        "init_project is required for artifact_upgrade's INSTALLED_RULES table "
        "(R1: the tuple stays on the residual) and its rule-write helper "
        "(seam 8); the scripts/ directory appears to be partially installed"
    )

try:
    from lessons_bootstrap import bootstrap_lessons_artifacts, _emit_lessons_bootstrap_banner
except ImportError:
    raise ImportError(
        "lessons_bootstrap is required for artifact_upgrade's post-refresh "
        "lessons-scaffolding backfill; the scripts/ directory appears to be "
        "partially installed"
    )


def load_artifact_manifest(plugin_root: Path) -> dict:
    """Load manifests/artifacts.yaml from the plugin root.

    The manifest enumerates every artifact the init script produces, the
    config keys it depends on, and the behaviour to take when a key is
    missing. Returns an empty schema if the file or PyYAML is absent so the
    script remains usable in degraded environments — the runtime fallback
    constants (DEFAULT_CATEGORIZATION, MIGRATABLE_TOP_LEVEL_KEYS) carry the
    same defaults the manifest documents.
    """
    if not HAS_YAML:
        return {"artifacts": []}
    manifest_path = plugin_root / "manifests" / "artifacts.yaml"
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"artifacts": []}
    try:
        loaded = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {"artifacts": []}
    if not isinstance(loaded, dict):
        return {"artifacts": []}
    return loaded


def upgrade_artifacts(
    cfg: "InitConfig",
    manifest: dict,
    from_version: str,
    to_version: str,
) -> tuple[list[str], list[str], list[tuple[str, str]], list[str], list[str], list[tuple[str, str]]]:
    """Refresh artifacts whose upgrade_behavior is `refresh_or_sidecar`.

    Returns a 6-tuple:
      refreshed: list of destination paths overwritten cleanly (includes every
        `transferred` entry below — its customization was moved out first)
      unchanged: list of destination paths whose installed body already matched the shipped body
      conflicts: list of (destination_path, sidecar_path) tuples — installed body diverged
        and was not adopted: the customization transfer-first write FAILED, the verdict was
        the degraded not-analyzed stand-in (structural_compare unavailable — no evidence to
        adopt on), a pre-image backup could not be written (failed backup = no destructive
        write), the adoption write itself failed after a verified transfer, or
        `upgrade.customization_handoff` is `report`/`report+issue` (conservative mode: a
        customization-bearing file is preserved in place, never auto-transferred). The file
        is left untouched and a shipped sidecar written for manual merge
      untracked: list of destination paths found in the install dirs but NOT in the manifest allowlist
      refreshed_subsets: subset of `refreshed` whose entries were auto-adopted because the
        installed body was a stale SUBSET of the (grown) shipped body (rules: any confidence;
        agents: exact/contained, or reorg-confidence via the frontmatter-preservation guard) —
        surfaced separately so the caller can print a "N were stale subsets, auto-adopted
        shipped" banner sub-line
      transferred: list of (destination_path, transfer_path) tuples — a customization-bearing
        verdict (HAS_UNIQUE or notes-flagged subset) whose content was VERIFIED-written to
        `transfer_path` (a dormant preservation file under
        `{planwise_root}/upgrade-transfers/{from}-to-{to}/`) before shipped was adopted at
        destination_path; see `_transfer_customization()`

    Config gate (`upgrade.customization_handoff`, read via `get_upgrade_config()`):
    `report+relocate` (the shipped template default) enables the automated
    transfer-then-adopt path below; `report` (the absent-key fallback) and
    `report+issue` (whose extra meaning — gh-issue routing — is handler-side only)
    are conservative for disposition purposes: customization-bearing files are
    preserved in place + sidecar'd, with NO transfer and NO adoption.

    Destructive gates: rules refresh on `is_subset` with empty verdict notes (the project
    paths: line is re-applied via update_frontmatter). Agents are overwritten whole-file:
    they auto-adopt on `is_safe_to_remove` (exact/contained, no notes) unchanged, OR on a
    pure reorg-confidence subset (no notes) via the frontmatter-preservation guard —
    detect-don't-guess: the guard splices a customized single-line model:/tools:/maxTurns:
    pin into shipped's frontmatter, and returns None (routing the file to the
    customization-bearing path instead) for ANY frontmatter delta it cannot provably
    preserve (non-guarded keys, block-style values, BOM'd/unparseable frontmatter). Any
    OTHER divergence (HAS_UNIQUE, or any confidence level whose notes flag tolerated
    installed-only content) is customization-bearing: under `report+relocate`,
    `_transfer_customization()` moves the content to the upgrade-transfers/ preservation
    file, verifies the write, and ONLY THEN adopts shipped in place. Carve-outs fall back
    to the conservative preserve + sidecar branch: a FAILED transfer (never adopt/remove
    without a verified transfer), the degraded not-analyzed stand-in verdict
    (`_verdict_not_analyzed()` — analysis never ran, so there is nothing to adopt on), a
    failed pre-image backup, and a failed adoption write.

    Destructive-write ordering at every adoption site: pre-image backup FIRST
    (`_write_backup_preimage()`; failure aborts the adoption), THEN the adoption write,
    and ONLY on its success the DISPOSITIONS.md row (`_append_disposition_log()`) and
    result bookkeeping — a failed write can never leave a false log row. An adoption
    removes the sidecar it obsoletes. A per-file OSError is contained (stderr warning,
    file left untouched) — the loops always complete.
    """
    refreshed: list[str] = []
    unchanged: list[str] = []
    conflicts: list[tuple[str, str]] = []
    untracked: list[str] = []
    refreshed_subsets: list[str] = []
    transferred: list[tuple[str, str]] = []

    conflict_dir = (
        cfg.project_root / cfg.planwise_root / "upgrade-conflicts"
        / f"{from_version}-to-{to_version}"
    )

    # verdicts.json (if the interactive fan-out produced one) supersedes the
    # inline primitive per-file — loaded once, looked up per diverged file.
    verdicts = _load_verdicts_cache(cfg, from_version, to_version)

    # `upgrade.customization_handoff` gates the automated transfer-then-adopt
    # path. Only the explicit `report+relocate` value (the shipped template
    # default) enables it; `report` (also the absent-key fallback) and
    # `report+issue` (extra gh-issue meaning is handler-side) stay
    # conservative: preserve in place + sidecar, no transfer, no adoption.
    handoff = get_upgrade_config(_load_raw_config(cfg))["customization_handoff"]
    relocate_enabled = handoff == "report+relocate"

    def _write_conflict_sidecar(dst: Path, sidecar_dst: Path, shipped_raw: str) -> None:
        sidecar_dst.parent.mkdir(parents=True, exist_ok=True)
        sidecar_dst.write_text(shipped_raw, encoding="utf-8")
        conflicts.append((str(dst), str(sidecar_dst)))

    # --- planwise_rules ---
    refs_dir = cfg.plugin_root / "references"
    rules_dst_dir = cfg.project_root / ".claude" / "rules" / "planwise"

    for filename, paths_template in INSTALLED_RULES:
        src = refs_dir / filename
        dst = rules_dst_dir / filename
        try:
            # utf-8-sig: a leading BOM must not defeat the frontmatter-anchored
            # comparison/guard helpers (see the comparator's non-substantive
            # framing rules — BOM is never a customization).
            shipped_raw = src.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            print(f"  Warning: shipped reference not found: {src}", file=sys.stderr)
            continue

        try:
            installed_raw = dst.read_text(encoding="utf-8-sig") if dst.exists() else None

            if installed_raw is None:
                # Fresh install — write via update_frontmatter() to set paths:.
                paths_value = resolve_rule_paths_value(cfg, paths_template)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(update_frontmatter(shipped_raw, paths_value), encoding="utf-8")
                refreshed.append(str(dst))
            elif normalize_rule_for_diff(shipped_raw) == normalize_rule_for_diff(installed_raw):
                # Bodies match after stripping per-project paths: — no rewrite needed.
                unchanged.append(str(dst))  # FAST PATH — primitive NOT called
            else:
                verdict = _classify_diverged(
                    normalize_rule_for_diff(installed_raw),
                    normalize_rule_for_diff(shipped_raw),
                    override=_load_verdict_override(verdicts, filename, installed_raw, dst),
                )
                sidecar_dst = (
                    conflict_dir / ".claude" / "rules" / "planwise" / f"{filename}.new")
                if is_subset(verdict) and not (getattr(verdict, "notes", "") or ""):
                    # Stale subset — adopt shipped in place, preserve the project
                    # paths:. Non-empty notes = the matcher tolerated installed-only
                    # content (sub-noise-floor fragments) — that flips to the
                    # customization-bearing branch below: an overwrite must not
                    # destroy a short customization without moving it first.
                    # Failed backup = no destructive write.
                    if not _write_backup_preimage(cfg, from_version, to_version, dst):
                        _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                    else:
                        preserved_paths = (
                            _extract_paths_value(installed_raw)
                            or resolve_rule_paths_value(cfg, paths_template))
                        dst.write_text(
                            update_frontmatter(shipped_raw, preserved_paths), encoding="utf-8")
                        _append_disposition_log(
                            cfg, from_version, to_version, dst, "auto-adopted shipped",
                            "installed rule body was a stale subset of the grown shipped body")
                        refreshed.append(str(dst))
                        refreshed_subsets.append(str(dst))     # banner sub-count
                        if sidecar_dst.exists():
                            # A prior interrupted run flagged this file — the adoption
                            # resolves that conflict; drop the obsoleted sidecar so a
                            # stale INDEX row cannot invite merging outdated content back.
                            sidecar_dst.unlink()
                elif _verdict_not_analyzed(verdict):
                    # Degraded stand-in — the file was never analyzed, so the
                    # automated transfer-then-adopt has no verdict evidence to
                    # act on. Preserve in place + shipped sidecar (always safe).
                    _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                elif not relocate_enabled:
                    # customization_handoff is report/report+issue — conservative
                    # mode: never auto-transfer or adopt over a customization-
                    # bearing verdict. Preserve in place + shipped sidecar.
                    _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                else:
                    # HAS_UNIQUE or noise-flagged subset — customization-bearing.
                    # Ordering: transfer + verify -> pre-image backup (abort on
                    # failure) -> adoption write -> ONLY on success the
                    # DISPOSITIONS row + transferred bookkeeping. A failed
                    # transfer or backup must never destroy the only copy; a
                    # failed adoption write must never leave a false log row.
                    transfer_path = _transfer_customization(
                        cfg, filename, "rule", installed_raw, verdict,
                        from_version, to_version,
                    )
                    if transfer_path is None or not _write_backup_preimage(
                            cfg, from_version, to_version, dst):
                        _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                    else:
                        preserved_paths = (
                            _extract_paths_value(installed_raw)
                            or resolve_rule_paths_value(cfg, paths_template))
                        try:
                            dst.write_text(
                                update_frontmatter(shipped_raw, preserved_paths),
                                encoding="utf-8")
                        except OSError as exc:
                            print(
                                f"  Warning: could not adopt shipped at {dst}: {exc}; "
                                f"preserved in place (customization already transferred "
                                f"to {transfer_path})",
                                file=sys.stderr,
                            )
                            _write_conflict_sidecar(dst, sidecar_dst, shipped_raw)
                        else:
                            _append_disposition_log(
                                cfg, from_version, to_version, dst,
                                "adopted shipped (customization transferred)",
                                f"customization transferred to {transfer_path}")
                            refreshed.append(str(dst))
                            transferred.append((str(dst), str(transfer_path)))
                            if sidecar_dst.exists():
                                sidecar_dst.unlink()
        except OSError as exc:
            # Per-file containment: a read-only/locked file must not abort the
            # whole refresh mid-loop with earlier dispositions unreported.
            print(
                f"  Warning: could not upgrade {dst}: {exc}; installed file left untouched",
                file=sys.stderr,
            )

    # --- Untracked detection ---
    rule_allowlist = {r[0] for r in INSTALLED_RULES}

    for md_file in rules_dst_dir.glob("*.md"):
        if md_file.name not in rule_allowlist:
            untracked.append(str(md_file))

    # --- Conflict INDEX.md ---
    if conflicts:
        index_path = conflict_dir / "INDEX.md"
        lines = [
            f"# Plugin upgrade conflicts: {from_version} -> {to_version}",
            "",
            "| # | Installed file | Sidecar | Notes |",
            "|---|---------------|---------|-------|",
        ]
        for i, (dst_path, sidecar_path) in enumerate(conflicts, start=1):
            lines.append(f"| {i} | {dst_path} | {sidecar_path} | (diff and merge manually) |")
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif conflict_dir.exists():
        # No conflicts this run: if a prior interrupted run's sidecars were all
        # resolved (adopted or hand-merged+deleted), retire the stale INDEX so it
        # cannot instruct merging content the adoption already superseded.
        index_path = conflict_dir / "INDEX.md"
        if index_path.exists() and not any(conflict_dir.rglob("*.new")):
            index_path.unlink()

    return refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred


def _repoint_plugin_root(config_path: Path, new_root: Path) -> None:
    """Update the plugin_root: line in config.yaml in-place, preserving formatting.

    Same shape as _bump_plugin_version(): a line-level edit over a PyYAML
    round-trip so the user's comment layout survives, falling back to
    appending the key as text when it is absent (never a whole-file re-emit,
    which would drop every interior comment and reflow every inline flow
    value). Routes through the parse-checked writer, so a bad edit is rolled
    back instead of bricking the config.

    `new_root` is rendered POSIX-style (forward slashes), matching
    generate_config()'s `{plugin-root}` substitution — the value this writes
    is styled identically to what a fresh init would have written.

    Standalone helper for a repoint with no accompanying version change (see
    the "already up to date" branch of _run_upgrade()). The version-bump
    commit point uses _commit_upgrade_pin() instead, which repoints AND bumps
    in a single write so the pair can never land half-committed.
    """
    text = config_path.read_text(encoding="utf-8")
    posix_root = str(new_root).replace("\\", "/")
    pattern = re.compile(r'^(\s*plugin_root:\s*)("[^"]*"|\S+)\s*$', re.MULTILINE)
    if pattern.search(text):
        new_text = pattern.sub(rf'\1"{posix_root}"', text)
        write_config_checked(config_path, new_text)
        return
    # Fallback — append the key as text after the existing top-level set.
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{config_path} is not a YAML mapping — cannot repoint plugin_root.")
    write_config_checked(
        config_path,
        text.rstrip("\n") + f'\n\nplugin_root: "{posix_root}"\n',
    )


def _commit_upgrade_pin(config_path: Path, new_version: str, new_root: Path) -> None:
    """Atomically pin BOTH plugin_version and plugin_root — the upgrade commit
    point — in a single parse-checked write, so the pair can never disagree.

    A prior version of this commit point bumped plugin_version alone, leaving
    plugin_root aimed at whatever cache directory the PREVIOUS version lived
    in. migrate_config() cannot repair that after the fact — it is purely
    additive and never touches a key that is already present — so every
    handler that resolves scripts through config's plugin_root would keep
    running the superseded version's scripts silently, and a handler that
    trusts plugin_root to locate .claude-plugin/plugin.json for drift
    detection would deadlock on "already up to date" forever (until the
    superseded cache directory is reaped, at which point plugin_root simply
    dangles instead).

    Both edits are applied to ONE in-memory text buffer, then written through
    write_config_checked() exactly ONCE. That single write is what makes this
    atomic: two separate write_config_checked() calls could leave the pair
    half-committed if the second call's parse check failed after the first
    had already landed on disk — precisely the drift this function exists to
    close. On failure the whole buffer is rolled back, so neither key changes.
    """
    text = config_path.read_text(encoding="utf-8")
    posix_root = str(new_root).replace("\\", "/")

    version_pattern = re.compile(r'^(\s*plugin_version:\s*)("[^"]*"|\S+)\s*$', re.MULTILINE)
    if version_pattern.search(text):
        text = version_pattern.sub(rf'\1"{new_version}"', text)
    else:
        text = text.rstrip("\n") + f'\n\nplugin_version: "{new_version}"\n'

    root_pattern = re.compile(r'^(\s*plugin_root:\s*)("[^"]*"|\S+)\s*$', re.MULTILINE)
    if root_pattern.search(text):
        text = root_pattern.sub(rf'\1"{posix_root}"', text)
    else:
        text = text.rstrip("\n") + f'\n\nplugin_root: "{posix_root}"\n'

    write_config_checked(config_path, text)


def _same_path(a: "str | Path", b: "str | Path") -> bool:
    """Case/separator-normalized path equality (Windows-safe comparison).

    Used to decide whether a configured plugin_root already matches the live
    plugin root without needing a write — a plain string/Path `==` would
    false-flag on a case-insensitive filesystem or on a `\\` vs `/` styling
    difference between a hand-edited value and the POSIX form this module
    writes.
    """
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


# Recovery-artifact disposition classes — see _scan_recovery_artifacts() /
# _emit_recovery_artifacts_banner() below. Two of these previously had NO
# stated end-of-life anywhere (pre-change backups, the consumed verdict
# cache) — this taxonomy is that end-of-life.
RECOVERY_ARTIFACT_CLASSES: dict[str, str] = {
    "action-required": "unresolved conflict sidecars",
    "review-then-discard": "transferred customizations awaiting re-homing",
    "safe-to-discard": "pre-change backups, once you are satisfied with the upgrade",
    "inert": "a consumed verdict cache",
}


def _scan_recovery_artifacts(cfg: "InitConfig") -> list[tuple[str, int, str]]:
    """Scan every on-disk recovery-artifact surface across every upgrade pair
    found — the current pair AND any prior pairs left over from earlier
    upgrades, since these leftovers accumulate per upgrade COUNT, not
    version distance, and nothing has swept them before now.

    Returns one (path, count, disposition_class) entry per surface that
    actually has content; a surface with zero matches is omitted entirely.
    Report-what-exists: pre-change backups fire on every overwrite, but
    transfers only fire on a genuine-customization verdict and conflict
    sidecars only on an unresolved divergence, so a typical run populates a
    subset — never assume all surfaces exist.
    """
    root = cfg.project_root / cfg.planwise_root
    surfaces: list[tuple[str, int, str]] = []

    backups_root = root / "upgrade-backups"
    backup_count = sum(
        1
        for pair_dir in backups_root.glob("*-to-*")
        if pair_dir.is_dir()
        for f in pair_dir.rglob("*")
        if f.is_file() and f.name != "DISPOSITIONS.md"
    )
    if backup_count:
        surfaces.append((f"{backups_root}/*/", backup_count, "safe-to-discard"))

    transfers_root = root / "upgrade-transfers"
    transfer_count = sum(
        1
        for pair_dir in transfers_root.glob("*-to-*")
        if pair_dir.is_dir()
        for f in pair_dir.rglob("*")
        if f.is_file()
    )
    if transfer_count:
        surfaces.append((f"{transfers_root}/*/", transfer_count, "review-then-discard"))

    # upgrade-conflicts/{pair}/ carries THREE distinct artifact kinds that
    # do not share a disposition class: unresolved sidecars (action-
    # required), a dormant issue-body draft subfolder (also action-required
    # — an unfiled draft still needs the user's review), and the retired
    # verdict cache (inert) — each reported as its own surface line rather
    # than one rolled-up "conflicts" count that could not carry one class.
    conflicts_root = root / "upgrade-conflicts"
    sidecar_count = 0
    issue_draft_count = 0
    consumed_cache_count = 0
    for pair_dir in conflicts_root.glob("*-to-*"):
        if not pair_dir.is_dir():
            continue
        sidecar_count += sum(1 for f in pair_dir.rglob("*.new") if f.is_file())
        issue_drafts_dir = pair_dir / "issue-drafts"
        if issue_drafts_dir.is_dir():
            issue_draft_count += sum(1 for f in issue_drafts_dir.rglob("*") if f.is_file())
        if (pair_dir / "verdicts.json.consumed").exists():
            consumed_cache_count += 1

    if sidecar_count:
        surfaces.append((f"{conflicts_root}/*/", sidecar_count, "action-required"))
    if issue_draft_count:
        surfaces.append(
            (f"{conflicts_root}/*/issue-drafts/", issue_draft_count, "action-required")
        )
    if consumed_cache_count:
        surfaces.append(
            (f"{conflicts_root}/*/verdicts.json.consumed", consumed_cache_count, "inert")
        )

    return surfaces


def _emit_recovery_artifacts_banner(surfaces: list[tuple[str, int, str]]) -> None:
    """Print the `Recovery artifacts:` banner: report-what-exists, one line
    per surface with its count and disposition class, so leftovers that
    scale with upgrade COUNT never go unreported (see
    RECOVERY_ARTIFACT_CLASSES for what each class means and when it is safe
    to act).
    """
    print("Recovery artifacts:")
    if not surfaces:
        print("  None found.")
        print()
        return
    for path, count, klass in surfaces:
        print(f"  {path} ({count} file(s)) — {klass}: {RECOVERY_ARTIFACT_CLASSES[klass]}")
    print()


def _split_formerly_managed(
    cfg: "InitConfig", untracked: list[str]
) -> tuple[list[str], list[str]]:
    """Partition an `untracked` list into (still-untracked, formerly-managed).

    A file counts as formerly managed only when a PRIOR upgrade's pre-change
    backup mirror exists for it under upgrade-backups/*-to-*/ — concrete
    evidence the plugin actively refreshed this exact path before it dropped
    out of the current shipped set. That backup mirror is the only durable
    prior-managed-set record this codebase persists: there is no snapshot of
    a past manifest or rule allowlist to diff against directly, so the
    detection stays evidence-based rather than guessing — a file with no
    matching backup mirror stays in the generic untracked bucket instead of
    being assumed formerly managed.
    """
    backups_root = cfg.project_root / cfg.planwise_root / "upgrade-backups"
    pair_dirs = [d for d in backups_root.glob("*-to-*") if d.is_dir()]
    still_untracked: list[str] = []
    formerly_managed: list[str] = []
    for path_str in untracked:
        dst = Path(path_str)
        try:
            rel = dst.relative_to(cfg.project_root)
        except ValueError:
            rel = Path(dst.name)
        was_managed = any((pair_dir / rel).exists() for pair_dir in pair_dirs)
        (formerly_managed if was_managed else still_untracked).append(path_str)
    return still_untracked, formerly_managed


def _apply_feedback_dir(cfg: "InitConfig", config_path: Path) -> None:
    """Backfill `project.feedback_dir` and create the resolved directory.

    Delegates the key backfill to init_project's own `_backfill_feedback_dir`
    (the leave-and-re-point disposition already implements the never-moves
    guarantee there — this function does not reimplement it) and then closes
    the second half of the contract that helper does not cover: creating the
    resolved directory when it is still absent, the same way
    `create_directories()` does for a fresh `/planwise init`. Runs on every
    `--upgrade` path that reaches an existing config, including the
    already-up-to-date early return, so a re-run at a current pin still
    closes the gap for an install that predates the key.

    Deferred import, not a module-level one: `_backfill_feedback_dir` is
    defined in init_project.py AFTER the line that imports THIS module
    (artifact_upgrade), so resolving it at module load time would raise
    ImportError against a partially-initialized module. By the time this
    function is actually called, init_project has finished loading.
    """
    from init_project import _backfill_feedback_dir

    notice = _backfill_feedback_dir(cfg, config_path)
    if notice:
        print(notice)

    try:
        parsed = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        parsed = {}
    project = parsed.get("project") if isinstance(parsed, dict) else None
    feedback_rel = (project or {}).get("feedback_dir") or cfg.feedback_dir
    feedback_dir_path = cfg.project_root / cfg.planwise_root / feedback_rel
    already_present = feedback_dir_path.is_dir()
    feedback_dir_path.mkdir(parents=True, exist_ok=True)
    state = "already present" if already_present else "created"
    print(f"Feedback directory: {state} ({feedback_dir_path})")


def _run_upgrade(cfg: "InitConfig") -> int:
    """Execute the --upgrade flow and print a banner. Returns exit code."""
    if not HAS_YAML:
        print(
            "Upgrade failed: PyYAML is required for --upgrade. Install with `pip install pyyaml`.",
            file=sys.stderr,
        )
        return 2

    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    if not config_path.exists():
        print(
            f"Upgrade failed: {config_path} does not exist — run /planwise init before --upgrade.",
            file=sys.stderr,
        )
        return 2

    # 1. Read pinned vs. target version.
    try:
        user_cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"Upgrade failed: cannot parse {config_path}: {exc}", file=sys.stderr)
        return 2
    pinned_version = str(user_cfg.get("plugin_version", "0.0.0"))
    target_version = cfg.plugin_version

    if pinned_version == target_version:
        # The version pin is current, but a SEPARATE key — plugin_root — can
        # still be stale: a legacy upgrade run (predating the commit point
        # that now repoints both together below) bumped plugin_version
        # alone, or a hand-edited plugin_root still names a cache directory
        # that was later reaped. Repoint it now so every OTHER handler that
        # resolves scripts through config's plugin_root stays trustworthy —
        # nothing else here changed, so this is a standalone, single-key
        # write, not the paired commit below.
        configured_root = user_cfg.get("plugin_root")
        needs_repoint = bool(configured_root) and not _same_path(configured_root, cfg.plugin_root)
        # Honor --token-saver on this branch too. The flip below the version
        # gate never runs here, and a flag the caller passed explicitly must
        # not be silently dropped just because no version bump was needed.
        # Unlike that call site this one cannot rely on migrate_config()
        # having seeded the key: _flip_token_saver_on() returns False for an
        # absent key, which is the correct no-op — a config with no
        # token_saver key at a current version pin is already anomalous and
        # is repaired by the next real upgrade's merge.
        toggled = bool(cfg.token_saver) and _flip_token_saver_on(config_path)
        # A re-run at a current pin must still close the feedback-dir gap for
        # an install whose config predates the key — this is the ONLY
        # opportunity that population gets, since the version pin already
        # matches and the guarded block below never runs.
        _apply_feedback_dir(cfg, config_path)
        if needs_repoint:
            _repoint_plugin_root(config_path, cfg.plugin_root)
            print(f"Plugin version: {pinned_version}")
            print(f"Plugin root repointed: {configured_root} -> {cfg.plugin_root}")
            if toggled:
                print("Token Saver enabled.")
            print("Already up to date (plugin_root repointed).")
            return 0
        print(f"Plugin version: {pinned_version}")
        if toggled:
            print("Token Saver enabled.")
        print("Already up to date.")
        return 0

    print(f"Plugin upgrade: {pinned_version} -> {target_version}")
    print()

    # 2. Run additive config merge.
    try:
        _, added, _present = migrate_config(cfg)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Upgrade failed during migrate phase: {exc}", file=sys.stderr)
        return 2
    if added:
        print("Config keys added:")
        for key in added:
            print(f"  + {key}")
        print()

    # 3-6. Everything from here through the version-pin commit point is
    # guarded top-level. State-corruption risk is LOW by construction: the
    # artifact-refresh loop below catches OSError per file (an unreadable or
    # locked file is reported and skipped, never aborts the run), and the
    # pin commit is the LAST statement in this block, written in one atomic,
    # parse-checked call that rolls back whole on failure. So any exception
    # raised anywhere in this block still leaves already-refreshed files
    # idempotent and the version pin untouched — re-running is always safe.
    try:
        # 2a. Honor --token-saver: flip context.token_saver false->true when
        # the user opts in this run. Runs AFTER migrate so the key is
        # guaranteed to be present (migrate seeds it as "false" when absent).
        # Never flips true->false; idempotent when the config already reads
        # true.
        if cfg.token_saver and _flip_token_saver_on(config_path):
            print("Token Saver enabled.")
            print()

        # 2b. Backfill lessons scaffolding (index seed + categorization file).
        # Fresh init renders these, but the legacy fresh-init-only path meant
        # an upgrade-adopted project never got 00-Categorization-By-Domain.md
        # — the file that hard-gates /planwise lessons curate and
        # promote-batch. Runs AFTER migrate_config so a freshly-migrated
        # `categorization:` block is picked up; idempotent and
        # non-destructive — a no-op (silent) when both files already exist,
        # preserving any user-customised content verbatim.
        lessons_boot = bootstrap_lessons_artifacts(cfg)
        _emit_lessons_bootstrap_banner(lessons_boot)

        # 2c. Backfill project.feedback_dir (leave-and-re-point disposition)
        # and create the resolved directory if absent. `project` is not one
        # of MIGRATABLE_TOP_LEVEL_KEYS, so the migrate_config() call above
        # never touches it and never creates the directory either — this is
        # the only place in the --upgrade path that closes both gaps.
        _apply_feedback_dir(cfg, config_path)

        # 3. Refresh artifacts.
        manifest = load_artifact_manifest(cfg.plugin_root)
        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = upgrade_artifacts(
            cfg, manifest, pinned_version, target_version
        )

        if refreshed:
            print(f"Refreshed: {len(refreshed)}")
            if refreshed_subsets:
                print(
                    f"  ({len(refreshed_subsets)} were stale subsets, auto-adopted shipped)"
                )
            for r in refreshed:
                print(f"  + {r}")
        if unchanged:
            print(f"Unchanged: {len(unchanged)} (installed body already matches shipped)")
        still_untracked, formerly_managed = _split_formerly_managed(cfg, untracked)
        if still_untracked:
            print(f"Untracked preserved: {len(still_untracked)}")
            for u in still_untracked:
                print(f"  = {u}")
        if formerly_managed:
            # Distinct from generic untracked: these files were once refreshed
            # by the plugin (a prior upgrade's backup mirror proves it) and
            # have since dropped out of the shipped set — a clarity gap, not
            # data loss.
            print(f"Formerly managed (dropped from the shipped set): {len(formerly_managed)}")
            for u in formerly_managed:
                print(f"  ~ {u}")
        print()

        if transferred:
            print(f"Customizations transferred before adoption: {len(transferred)}")
            for dst, transfer_path in transferred:
                print(f"  ~ {dst}")
                print(f"      moved to: {transfer_path}")
            print("  Review each transferred file and re-home it (project-local rule, "
                  "re-scope, or upstream the change).")
            print()

        if conflicts:
            print("Conflicts (preserved in place — action required):")
            for dst, sidecar in conflicts:
                print(f"  ! {dst}")
                print("      reason:      installed body diverged and was not auto-adopted "
                      "(conservative handoff mode, a transfer/backup/adoption write failed, "
                      "or the file could not be analyzed)")
                print(f"      sidecar:     {sidecar}")
                print("      remediation: diff the sidecar against the installed file, merge manually, then delete the .new")
            index_path = (
                cfg.project_root / cfg.planwise_root / "upgrade-conflicts"
                / f"{pinned_version}-to-{target_version}" / "INDEX.md"
            )
            print(f"  See {index_path} for the full conflict list.")
            print()

        # 4. De-scope migration — remove install-set rules that are now
        # handler-loaded, but only the untouched copies. Runs AFTER artifact
        # refresh and BEFORE the version bump so it executes exactly once, on
        # the upgrade that crosses RESCOPE_MIGRATION_VERSION.
        migration = migrate_installed_rules(cfg, pinned_version, target_version)
        if migration["removed"]:
            print("De-scoped rules removed (now handler-loaded from references/):")
            for entry in migration["removed"]:
                print(f"  - {entry}")
            print()
        if migration["preserved"]:
            print("De-scoped rules preserved (customized — action recommended):")
            for entry in migration["preserved"]:
                print(f"  ! {entry}")
            print()

        # 4b. Retire the consumed verdict cache. A verdicts.json entry is
        # bound to the exact (upgrade pair, installed bytes) it was computed
        # against; once this run has consumed it, leaving it in place would
        # let a stale verdict fire on a later re-run or a different pair.
        # Renamed (not deleted) so the analysis remains inspectable next to
        # INDEX.md.
        verdicts_path = (
            cfg.project_root / cfg.planwise_root / "upgrade-conflicts"
            / f"{pinned_version}-to-{target_version}" / "verdicts.json"
        )
        if verdicts_path.exists():
            try:
                consumed_path = verdicts_path.with_name("verdicts.json.consumed")
                if consumed_path.exists():
                    consumed_path.unlink()
                verdicts_path.rename(consumed_path)
                print(f"Verdict cache consumed: renamed to {consumed_path.name}")
                print()
            except OSError as exc:
                print(
                    f"  Warning: could not retire consumed verdict cache {verdicts_path}: {exc}",
                    file=sys.stderr,
                )

        # 4c. Recovery-artifact aggregation: report every leftover surface
        # still on disk across every upgrade pair found (not just this
        # run's), each with its disposition class. Placed AFTER the
        # verdict-cache retirement above so a cache this run just consumed is
        # picked up as inert rather than missed as still-active.
        _emit_recovery_artifacts_banner(_scan_recovery_artifacts(cfg))

        # 5. Post-upgrade advisory: flag any installed rule still scoped to
        # plan/backlog/lessons globs (read-only — never mutates).
        overscoped = lint_rule_overscope(cfg)
        if overscoped:
            total_tokens = sum(item["approx_tokens"] for item in overscoped)
            print("Advisory — rules scoped to plan/backlog/lessons globs:")
            for item in overscoped:
                print(
                    f"  ~ {item['path']} ({item['line_count']} lines, "
                    f"~{item['approx_tokens']} tokens; matches {item['matched_glob']})"
                )
                print("      hint: re-scope to code paths or convert to a handler-loaded reference")
            print(f"  Total always-on injected budget from flagged rules: ~{total_tokens} tokens")
            print()

        # 6. Commit point: pin plugin_version AND repoint plugin_root
        # together, in ONE write, LAST — see _commit_upgrade_pin(). Never
        # split into two writes here: a config left with a bumped version but
        # a stale root (or vice versa) is exactly the defect this closes.
        _commit_upgrade_pin(config_path, target_version, cfg.plugin_root)
        print(f"Plugin version pinned: {target_version}")
        print(f"Plugin root repointed: {cfg.plugin_root}")
        print()
        print("Upgrade complete.")
        return 0
    except Exception as exc:
        print(f"\nUpgrade failed: {exc}", file=sys.stderr)
        print(
            "partial upgrade — re-run to resume; already-refreshed files are "
            "idempotent and the version pin is unchanged.",
            file=sys.stderr,
        )
        raise


