"""De-scope migration for previously handler-loaded rules.

Owns the one-shot, version-gated removal of install-set rules the plugin's
de-scope moved to handler-loading. Backup-before-destroy and transfer-then-
adopt safety are built on the shared upgrade_io primitives; divergence
classification is delegated to rule_divergence.
"""

import re
from pathlib import Path

try:
    from config_gen import InitConfig, get_upgrade_config  # noqa: F401 -- InitConfig type-hint only (quoted forward refs)
except ImportError:
    raise ImportError(
        "config_gen is required for rule_descope_migration's InitConfig type "
        "references and upgrade-config gate; the scripts/ directory appears "
        "to be partially installed"
    )

try:
    from upgrade_io import (
        _load_verdicts_cache,
        _load_verdict_override,
        _write_backup_preimage,
        _append_disposition_log,
        _record_disposition,
        _load_raw_config,
        _transfer_customization,
    )
except ImportError:
    raise ImportError(
        "upgrade_io is required for rule_descope_migration's backup/disposition/"
        "transfer primitives; the scripts/ directory appears to be partially "
        "installed"
    )

try:
    from rule_divergence import (
        is_subset,
        _destructively_removable,
        _classify_diverged,
        normalize_rule_for_diff,
        _verdict_not_analyzed,
        _extract_paths_value,
    )
except ImportError:
    raise ImportError(
        "rule_divergence is required for rule_descope_migration's structural-"
        "verdict classification; the scripts/ directory appears to be "
        "partially installed"
    )

try:
    from init_project import DESCOPED_RULES, resolve_rule_paths_value
except ImportError:
    raise ImportError(
        "init_project is required for rule_descope_migration's DESCOPED_RULES "
        "table (R1: the tuple stays on the residual) and its resolve_rule_paths_value() "
        "helper; the scripts/ directory appears to be partially installed"
    )


# Version this de-scope migration ships in. migrate_installed_rules() only
# acts when from_version < RESCOPE_MIGRATION_VERSION <= to_version, so the
# removal runs exactly once on the upgrade that crosses this boundary. This is
# PINNED to the version the de-scope first shipped in and MUST NOT be bumped to
# track plugin.json. Once plugin.json moves past it, the one-shot migration is
# spent for those installs; `/planwise doctor`'s stale sweep (Stage 8 +
# --prune-stale) is then the only remaining reach.
RESCOPE_MIGRATION_VERSION = "1.0.3"


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable integer tuple.

    Non-numeric / missing components degrade to 0 so a malformed or sentinel
    value ("0.0.0", "", or a partial "1.1") still orders sensibly against a
    well-formed version. Used by the de-scope migration version gate.
    """
    parts: list[int] = []
    for component in str(version).split("."):
        digits = re.match(r"\d+", component.strip())
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def migrate_installed_rules(
    cfg: "InitConfig",
    from_version: str,
    to_version: str,
) -> dict:
    """Remove install-set rules that the de-scope moved to handler-loading.

    Version-gated: acts only when
    ``from_version < RESCOPE_MIGRATION_VERSION <= to_version`` (the single
    upgrade that crosses the de-scope boundary). Outside that window it is a
    pure no-op and touches nothing.

    For each (filename, old_template) in DESCOPED_RULES, the installed copy at
    ``.claude/rules/planwise/{filename}`` is dispositioned as follows.
    Normalized-identical body (fast path — the structural primitive is never
    invoked): paths also match -> removed (provably untouched); paths differ ->
    removed with an INFO notice (scoping is moot once the rule is
    handler-loaded), unless ``upgrade.descope_preserve_paths_edits`` is true ->
    preserved. Diverged body: classified via ``_classify_diverged()`` — a
    stale SUBSET is removed only when the verdict is high-confidence
    (exact/contained) AND its ``notes`` field is empty (non-empty notes means
    the matcher tolerated installed-only content, e.g. sub-noise-floor
    fragments — preserved instead) AND the paths-edit preserve opt-out does
    not apply (a paths-customized copy is kept even over a stale body while
    ``descope_preserve_paths_edits`` is true); a reorg-confidence SUBSET (no
    notes) is always preserved with an explanatory notice — a confidence gap,
    not a genuine customization, so ``customization_handoff`` never applies.
    A notes-flagged SUBSET or a genuine HAS_UNIQUE (customization-bearing)
    verdict is gated on the effective ``upgrade.customization_handoff``,
    read via the SAME accessor the artifact refresh writer uses — BUT the
    paths-edit preserve opt-out takes PRECEDENCE over that gate too, exactly
    as it does for the high-confidence-subset branch above: a paths-
    customized copy (``paths_match`` False) with ``descope_preserve_paths_edits``
    true is preserved in place even when the body ALSO carries a genuine
    customization — a file customized in both paths: and body must never get
    WEAKER protection than one customized in paths: alone. Only when that
    opt-out does not apply does ``customization_handoff`` decide the
    disposition: ``report+relocate`` (the shipped template default)
    verified-transfers the customization to the upgrade transfer helper's
    dormant preservation home (``_transfer_customization()``) and, ONLY on
    that verified success, backs up and removes the stale installed file;
    any other value (``report``, the absent-key fallback, or
    ``report+issue``) preserves in place with a re-home notice, unchanged
    from prior behavior. A failed transfer or a failed pre-removal backup
    means NO removal — the file is preserved in place and the failure
    reported; a customization is never destroyed without a verified copy
    elsewhere. The degraded not-analyzed stand-in
    (structural_compare unavailable) always preserves regardless of
    ``customization_handoff`` — there is no verdict evidence yet to transfer
    on. Every plain removal (the fast-path and high-confidence branches)
    mirrors the pre-image under ``{planwise_root}/upgrade-backups/`` via
    ``_record_disposition()``; a transfer-then-remove instead backs up via
    ``_write_backup_preimage()`` and logs via ``_append_disposition_log()``
    only once the removal itself has succeeded (mirroring the artifact
    refresh's own transfer-then-adopt ordering). The migration never
    defaults a preserve notice to recommending deletion. A per-file OSError
    is contained as a ``skipped`` entry — the loop always completes and
    reports. Rules outside DESCOPED_RULES are never inspected or modified.

    Returns ``{"removed": [...], "preserved": [...], "skipped": [...]}`` where
    each list holds human-readable strings (filename + reason). The shape is
    intentionally loose so the upgrade banner can fold it in directly.
    """
    report: dict[str, list[str]] = {"removed": [], "preserved": [], "skipped": []}

    # Version gate — run exactly once, on the upgrade that crosses the boundary.
    gate = _version_tuple(RESCOPE_MIGRATION_VERSION)
    if not (_version_tuple(from_version) < gate <= _version_tuple(to_version)):
        return report

    refs_dir = cfg.plugin_root / "references"
    rules_dir = cfg.project_root / ".claude" / "rules" / "planwise"

    # The paths-edit opt-out lives under the `upgrade:` block in config.yaml.
    # InitConfig does not carry the raw config dict, so load it at the site;
    # tolerant on purpose — an absent/unparsable config degrades to {} and
    # get_upgrade_config() supplies the conservative defaults.
    config = _load_raw_config(cfg)
    upgrade_config = get_upgrade_config(config)   # dict contract; bind once, read twice below

    preserve_paths_edits = upgrade_config["descope_preserve_paths_edits"]

    # `upgrade.customization_handoff` gates Site-1's own transfer-then-remove
    # path over a preserved, customization-bearing de-scoped rule — read via
    # the SAME accessor and gated exactly like the artifact refresh writer's
    # (Sites 2/3) customization-bearing branch: `report+relocate` (the
    # shipped template default) enables the automated transfer-then-remove
    # flow below; `report` (also the absent-key fallback) and `report+issue`
    # (whose extra gh-issue meaning is handler-side only) stay conservative —
    # preserve in place, no transfer, no removal.
    relocate_enabled = upgrade_config["customization_handoff"] == "report+relocate"

    # verdicts.json entries apply across every --upgrade writer site, not just
    # the artifact refresh (Sites 2/3) — the interactive fan-out's --list-diverged
    # scope includes DESCOPED_RULES, so a de-scoped rule can carry a cached
    # agent verdict too. Same helper, same degrade-to-None-on-absence contract.
    verdicts = _load_verdicts_cache(cfg, from_version, to_version)

    def _transfer_then_remove_or_preserve(
        dst: Path, filename: str, installed_raw: str, verdict, preserve_message: str,
        *, paths_match: bool,
    ) -> None:
        """Disposition for a customization-bearing preserved de-scoped rule.

        Mirrors the artifact refresh writer's (Sites 2/3) customization_handoff
        gate and reuses its `_transfer_customization()` helper exactly: under
        `report+relocate`, the customization is verified-transferred to the
        upgrade transfer helper's dormant preservation home BEFORE the stale
        installed copy is backed up and removed. A failed transfer or a
        failed pre-removal backup means NO removal — the file stays in place
        and the failure is reported (never destroy the only copy of a
        customization). Any other handoff value preserves in place, exactly
        as before (no writes).

        The paths-edit preserve opt-out (`descope_preserve_paths_edits`) takes
        PRECEDENCE over `customization_handoff` here, exactly as it does in the
        sibling high-confidence-subset branch above: a paths-customized copy
        (`paths_match` False) is preserved in place even when the body ALSO
        carries a genuine customization, rather than transferred-then-removed
        under `report+relocate`. A file customized in BOTH paths: and body
        must never receive WEAKER protection than one customized in paths:
        alone.
        """
        if not paths_match and preserve_paths_edits:
            report["preserved"].append(
                f"{filename}: kept (paths-customized; preserve opt-out covers paths: "
                "edits even when the body also carries a customization) — re-home or "
                "re-scope to the code dirs it governs")
            return

        if not relocate_enabled:
            report["preserved"].append(preserve_message)
            return

        transfer_path = _transfer_customization(
            cfg, filename, "rule", installed_raw, verdict, from_version, to_version,
        )
        if transfer_path is None:
            report["preserved"].append(
                f"{filename}: kept — automated transfer failed; installed file "
                "left in place (no removal without a verified transfer)")
            return

        if not _write_backup_preimage(cfg, from_version, to_version, dst):
            report["preserved"].append(
                f"{filename}: kept — customization transferred to {transfer_path}, "
                "but the pre-removal backup failed; installed file left in place "
                "(no removal without a pre-image)")
            return

        try:
            dst.unlink()
        except OSError as exc:
            report["skipped"].append(
                f"{filename}: skipped — customization transferred to "
                f"{transfer_path} and backed up, but removal failed ({exc}); "
                "installed file left in place")
            return

        _append_disposition_log(
            cfg, from_version, to_version, dst, "removed (customization transferred)",
            f"customization transferred to {transfer_path}")
        report["removed"].append(
            f"{filename}: removed — customization transferred to "
            f"{transfer_path} (re-home it there: port to a project-local rule, "
            "re-scope paths:, or upstream the change); the rule is now "
            "handler-loaded from references/")

    for filename, old_template in DESCOPED_RULES:
        dst = rules_dir / filename
        try:
            if not dst.exists():
                # Already absent (fresh install on the new version, or a prior
                # migration run already removed it) — nothing to do, stay idempotent.
                report["skipped"].append(f"{filename}: not installed — nothing to migrate")
                continue

            # utf-8-sig: a leading BOM must not defeat the frontmatter-anchored
            # comparison helpers (startswith("---\n") returns False on a BOM'd
            # file, silently flipping the disposition) — strip it at read time.
            installed_raw = dst.read_text(encoding="utf-8-sig")
            src = refs_dir / filename
            try:
                shipped_raw = src.read_text(encoding="utf-8-sig")
            except FileNotFoundError:
                # Cannot prove the body is untouched without the shipped reference —
                # preserve the installed copy rather than risk deleting a custom one.
                report["preserved"].append(
                    f"{filename}: kept — shipped reference unavailable to compare; "
                    "re-home to a project-local rule or upstream the edit if it is custom"
                )
                continue

            installed_norm = normalize_rule_for_diff(installed_raw)
            shipped_norm = normalize_rule_for_diff(shipped_raw)
            installed_paths = _extract_paths_value(installed_raw)
            paths_match = installed_paths == resolve_rule_paths_value(cfg, old_template)

            if installed_norm == shipped_norm:
                # FAST PATH — normalized-identical; primitive NOT called.
                if paths_match:
                    if _record_disposition(
                            cfg, from_version, to_version, dst, "removed",
                            "untouched de-scoped rule (normalized-identical, paths match)"):
                        dst.unlink()
                        report["removed"].append(
                            f"{filename}: removed — untouched de-scoped rule "
                            "(now handler-loaded from references/)")
                    else:
                        # Failed backup = no deletion (same contract as the
                        # prune writer): the pre-image is the only recovery
                        # path once the file is gone.
                        report["skipped"].append(
                            f"{filename}: skipped — backup write failed; installed "
                            "file left in place (no removal without a pre-image)")
                elif preserve_paths_edits:
                    report["preserved"].append(
                        f"{filename}: kept (paths-customized; preserve opt-out enabled) — "
                        "re-home or re-scope to the code dirs it governs")
                else:
                    if _record_disposition(
                            cfg, from_version, to_version, dst, "removed",
                            "body matches shipped; custom paths: dropped (opt-out disabled)"):
                        dst.unlink()
                        report["removed"].append(
                            f"{filename}: removed [INFO] — body matches shipped; custom paths: "
                            "dropped (scoping is moot once the rule is handler-loaded)")
                    else:
                        report["skipped"].append(
                            f"{filename}: skipped — backup write failed; installed "
                            "file left in place (no removal without a pre-image)")
            else:
                verdict = _classify_diverged(
                    installed_norm, shipped_norm,
                    override=_load_verdict_override(verdicts, filename, installed_raw, dst),
                )
                verdict_notes = getattr(verdict, "notes", "") or ""
                if _destructively_removable(verdict):
                    # Deletion needs BOTH the high-confidence subset verdict AND a
                    # clean notes field — non-empty notes means the primitive
                    # tolerated installed-only content (e.g. sub-noise-floor
                    # fragments), which is exactly what deletion must not destroy.
                    if not paths_match and preserve_paths_edits:
                        # The paths-edit preserve opt-out covers the diverged path
                        # too: a stale body does not forfeit a paths: customization.
                        report["preserved"].append(
                            f"{filename}: kept (paths-customized; body is a stale subset "
                            "but the preserve opt-out covers paths: edits) — re-home or "
                            "re-scope to the code dirs it governs")
                    else:
                        reason = "stale subset of the grown shipped reference"
                        if not paths_match:
                            reason += "; custom paths: dropped (opt-out disabled)"
                        if _record_disposition(
                                cfg, from_version, to_version, dst, "removed", reason):
                            dst.unlink()
                            suffix = (
                                " [INFO] custom paths: dropped (opt-out disabled)"
                                if not paths_match else "")
                            report["removed"].append(
                                f"{filename}: removed — stale subset of the grown shipped "
                                f"reference (now handler-loaded from references/){suffix}")
                        else:
                            report["skipped"].append(
                                f"{filename}: skipped — backup write failed; installed "
                                "file left in place (no removal without a pre-image)")
                elif is_subset(verdict):
                    if verdict_notes:
                        # SUBSET verdict flagged installed-only content the matcher
                        # tolerated as noise — genuine customization-bearing
                        # content. Under `report+relocate` this transfers then
                        # removes (the same customization-bearing gate the
                        # artifact refresh applies); otherwise it preserves as
                        # before, surfacing the primitive's own note either way.
                        _transfer_then_remove_or_preserve(
                            dst, filename, installed_raw, verdict,
                            f"{filename}: kept — subset verdict carries installed-only "
                            f"content ({verdict_notes}); preserved rather than risk "
                            "deleting a short customization. Review manually before "
                            "removal.",
                            paths_match=paths_match)
                    else:                                  # SUBSET but confidence == reorg
                        # Headless-inconclusive reorg is a confidence gap, not a
                        # genuine customization — it always preserves regardless
                        # of customization_handoff (nothing to transfer).
                        report["preserved"].append(
                            f"{filename}: kept — headless inconclusive (content reorganized, "
                            "not a clean subset); run /planwise upgrade interactively to "
                            "agent-verify, or /planwise doctor, before removal")
                else:                                      # HAS_UNIQUE
                    unique_blocks = getattr(verdict, "unique_blocks", []) or []
                    if _verdict_not_analyzed(verdict):
                        # Degraded stand-in (analysis never ran) — always
                        # preserved regardless of customization_handoff,
                        # mirroring the artifact refresh's own bypass: there is
                        # no verdict evidence yet to transfer on. Do NOT assert
                        # "0 customized blocks"; say why it was preserved
                        # unexamined.
                        report["preserved"].append(
                            f"{filename}: kept — {verdict_notes}. The installed copy was "
                            "NOT analyzed and may carry customizations; diff it against "
                            "references/ before deleting anything manually.")
                    else:
                        # Genuine HAS_UNIQUE — customization-bearing. Under
                        # `report+relocate` this transfers then removes;
                        # otherwise it preserves as before.
                        blocks = ", ".join(unique_blocks[:3]) or "see verdict"
                        _transfer_then_remove_or_preserve(
                            dst, filename, installed_raw, verdict,
                            f"{filename}: kept ({len(unique_blocks)} customized block(s): "
                            f"{blocks}) — the orchestrator now loads this rule from "
                            "references/; re-home: port to a project-local rule, re-scope "
                            "paths: to code dirs, or upstream the change. Installed copy "
                            "unchanged.",
                            paths_match=paths_match)
        except OSError as exc:
            # Per-file containment: one unreadable/read-only file must not abort
            # the migration mid-loop (earlier deletions would then go unreported).
            report["skipped"].append(
                f"{filename}: skipped — disposition failed ({exc}); installed file "
                "left in place")

    return report


