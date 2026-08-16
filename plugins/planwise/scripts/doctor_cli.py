"""`/planwise doctor` CLI dispatchers: version-state gate, config parse
check, and the --doctor / --prune-stale / --list-diverged report printers.

Orchestrates doctor_sweeps's four read-only sweeps into printed reports, and
owns the plugin version-state gate every dispatcher runs first.
"""

import datetime
import json
import re
import shutil
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from config_gen import (
        InitConfig,  # noqa: F401 -- type-hint only (quoted forward refs)
        read_plugin_version,
    )
except ImportError:
    raise ImportError(
        "config_gen is required for doctor_cli's read_plugin_version helper; "
        "the scripts/ directory appears to be partially installed"
    )

try:
    from rule_divergence import normalize_rule_for_diff
except ImportError:
    raise ImportError(
        "rule_divergence is required for doctor_cli's diverged-row comparison; "
        "the scripts/ directory appears to be partially installed"
    )

try:
    from doctor_sweeps import (
        lint_rule_overscope,
        compute_injection_families,
        sweep_stale_descoped_rules,
        sweep_orphaned_agent_mirrors,
        lint_installed_divergence,
        sweep_upgrade_leftovers,
    )
except ImportError:
    raise ImportError(
        "doctor_sweeps is required for doctor_cli's report dispatchers; the "
        "scripts/ directory appears to be partially installed"
    )

try:
    from artifact_upgrade import RECOVERY_ARTIFACT_CLASSES
except ImportError:
    raise ImportError(
        "artifact_upgrade is required for doctor_cli's leftover-sweep report "
        "and prune writer (RECOVERY_ARTIFACT_CLASSES); the scripts/ "
        "directory appears to be partially installed"
    )

try:
    from init_project import INSTALLED_RULES, DESCOPED_RULES
except ImportError:
    raise ImportError(
        "init_project is required for doctor_cli's INSTALLED_RULES/"
        "DESCOPED_RULES tables (R1: the tuples stay on the residual); the "
        "scripts/ directory appears to be partially installed"
    )


def _run_prune_stale(cfg: "InitConfig") -> int:
    """WRITER (opt-in): delete ONLY the REMOVABLE stale de-scoped rules and
    orphaned agent mirrors, log to PRUNED.md.

    Explicit opt-in companion to the read-only --doctor sweeps (Stage 8 and
    the orphaned agent-mirror sweep). Runs the plugin version-state gate
    first (mirroring _run_doctor): an uninitialized or version-drifted
    install refuses to prune and returns 0 with the tree untouched. On a
    gate-ok install it runs BOTH sweep_stale_descoped_rules(cfg) and
    sweep_orphaned_agent_mirrors(cfg) in the same pass — one opt-in writer,
    two artifact kinds — unlinks every REMOVABLE finding from either sweep
    (never a PRESERVE / RELOCATE one), and writes the full disposition
    (removed + preserved + why) to a per-run, never-overwritten folder:
    {planwise_root}/upgrade-backups/prune-{YYYY-MM-DD}/PRUNED.md, or
    prune-{YYYY-MM-DD}-2/, -3/, ... when a folder for today already exists (a
    second run the same day never clobbers an earlier run's log). Before each
    deletion, a pre-image of the file is copied into that same prune folder
    alongside PRUNED.md, so a prune is recoverable; a failed backup copy means
    the file is left in place rather than deleted. A failed unlink after a
    successful backup is reported as REMOVE_FAILED (not REMOVABLE) and its
    orphan backup copy is removed. Exits 0.
    """
    gate = _doctor_version_gate(cfg)
    if gate["state"] != "ok":
        print(gate["report"])
        print()
        print("Nothing pruned — see the version-state gate above.")
        return 0

    findings = sweep_stale_descoped_rules(cfg) + sweep_orphaned_agent_mirrors(cfg)
    removable = [f for f in findings if f["verdict"] == "REMOVABLE"]
    kept = [f for f in findings if f["verdict"] != "REMOVABLE"]

    today = datetime.date.today().isoformat()  # YYYY-MM-DD
    backups_root = cfg.project_root / cfg.planwise_root / "upgrade-backups"
    out_dir = backups_root / f"prune-{today}"
    suffix = 2
    while out_dir.exists():
        out_dir = backups_root / f"prune-{today}-{suffix}"
        suffix += 1
    out_dir.mkdir(parents=True, exist_ok=True)

    removed: list[dict] = []
    for f in removable:
        try:
            src = Path(f["path"])
            (out_dir / f["filename"]).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            src.unlink()
            removed.append(f)
        except OSError as exc:
            f["verdict"] = "REMOVE_FAILED"
            f["reason"] = f"could not remove ({exc}) — left in place"
            kept.append(f)
            (out_dir / f["filename"]).unlink(missing_ok=True)

    lines = [f"# Stale de-scoped rule / orphaned agent-mirror prune — {today}", ""]
    lines.append(f"## Removed ({len(removed)})")
    for f in removed:
        lines.append(f"- `{f['filename']}` (~{f['approx_tokens']} tokens) — {f['reason']}")
    lines.append("")
    lines.append(f"## Preserved ({len(kept)})")
    for f in kept:
        lines.append(f"- `{f['filename']}` [{f['verdict']}] — {f['reason']}")
    if removed:
        lines.append("")
        lines.append("Pre-image copies of every removed file above sit alongside this "
                      "log in this same folder, named after their original filename.")
    (out_dir / "PRUNED.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Pruned {len(removed)} stale de-scoped rule(s)/orphaned agent mirror(s); "
          f"preserved {len(kept)}. Log: {out_dir / 'PRUNED.md'}")
    return 0


PRUNABLE_CLASSES = {"inert", "safe-to-discard"}


def _run_prune_upgrade_leftovers(cfg: "InitConfig", classes: "set[str] | None" = None) -> int:
    """WRITER (opt-in): delete ONLY the *inert* and *safe-to-discard* upgrade
    recovery-leftovers Stage 14's read-only sweep reports, log to a
    dedicated PRUNED-LEFTOVERS.md.

    DISTINCT from `_run_prune_stale` above (the `--prune-stale` writer):
    that flag targets a completely different artifact class — de-scoped
    rules and orphaned agent mirrors under `.claude/rules|agents/` — and
    already logs into `upgrade-backups/prune-{date}/`. Giving this writer
    the same flag name would make one flag mean two unrelated things; it
    targets version-pair recovery leftovers instead (`upgrade-backups/
    *-to-*/`, `upgrade-transfers/*-to-*/`, `upgrade-conflicts/*-to-*/`) and
    logs into its own `upgrade-prune-logs/upgrade-leftovers-{date}/` root,
    so the two prune logs never collide.

    That separate root is load-bearing, not cosmetic: this writer prunes
    surfaces that live INSIDE `upgrade-backups/`, so logging there would
    copy a pruned pair to `upgrade-backups/<log>/upgrade-backups/{pair}`
    and delete the original — reclaiming nothing, and hiding the copy from
    the sweep's `*-to-*` glob forever. Keeping the log root disjoint from
    every swept root is what makes "pruned" actually mean pruned.

    `classes` may NARROW the scope to the subset the caller confirmed (the
    doctor handler asks once per PRESENT prunable class and passes only the
    approved ones); it can never widen it — the intersection with the two
    prunable classes is taken, so an action-required or review-then-discard
    finding is unreachable regardless of what is passed.

    KNOWN INTERACTION, deliberately not silently resolved here: pruning the
    `safe-to-discard` backups also removes the pre-image mirrors that the
    refresh loop's formerly-managed detection uses as its ONLY durable
    prior-managed-set evidence. After a prune, a file the plugin stopped
    managing reports as generic untracked rather than formerly managed. The
    copies survive under this writer's log root, so nothing is destroyed —
    but the detector does not look there. Callers who rely on that
    detection should defer pruning the backups class.

    Scope is taxonomy-bound (RECOVERY_ARTIFACT_CLASSES, defined once in
    artifact_upgrade.py and reused here for a grep-identical vocabulary):
    only findings from `sweep_upgrade_leftovers()` classed "inert" (a
    consumed verdict cache) or "safe-to-discard" (pre-change backups) are
    ever eligible. An "action-required" finding (unresolved conflict
    sidecars, or the nested issue-drafts/ subfolder) or a
    "review-then-discard" one (transferred customizations awaiting
    re-homing) is NEVER deleted by this writer, regardless of what the
    caller passes — pruning either of those classes is exactly the mistake
    the taxonomy exists to prevent. The interactive per-class confirm
    (mirroring the upgrade handler's Step 4.3 contract: one AskUserQuestion
    per present prunable class, tagged AUTO-MODE: convenience, inferred
    default skip-all in unattended runs) happens in the /planwise doctor
    handler BEFORE this writer is invoked — this function performs the
    already-confirmed deletion, it does not itself prompt.

    Runs the plugin version-state gate first (mirroring _run_prune_stale):
    an uninitialized or version-drifted install refuses to prune and
    returns 0 with the tree untouched.

    Each pruned path (file or directory) is copied into the run's own log
    folder before removal, mirroring its original location relative to the
    planwise root (e.g. upgrade-backups/{pair}/... stays
    upgrade-backups/{pair}/... under the log folder) — so a prune is
    recoverable. A failed copy leaves the original in place
    (REMOVE_FAILED, not pruned) rather than risk deleting without a
    backup. If the REMOVAL then fails part-way — `shutil.rmtree` is not
    atomic and a locked or read-only file routinely stops it mid-tree — the
    copy is NOT rolled back: it is by then the only surviving record of
    whatever was already deleted, and the log names its path so the user
    restores from it instead of re-running. Exits 0.
    """
    gate = _doctor_version_gate(cfg)
    if gate["state"] != "ok":
        print(gate["report"])
        print()
        print("Nothing pruned — see the version-state gate above.")
        return 0

    findings = sweep_upgrade_leftovers(cfg)
    # Never widen beyond the two prunable classes, whatever the caller asks for:
    # `classes` may NARROW the scope (the handler's per-class confirm passes only
    # the classes the user approved), never extend it to action-required or
    # review-then-discard.
    prunable_classes = PRUNABLE_CLASSES if classes is None else (set(classes) & PRUNABLE_CLASSES)
    prunable = [f for f in findings if f["klass"] in prunable_classes]
    kept = [f for f in findings if f["klass"] not in prunable_classes]

    today = datetime.date.today().isoformat()  # YYYY-MM-DD
    planwise_root = cfg.project_root / cfg.planwise_root

    if not prunable:
        # Return BEFORE creating anything. Creating the log folder up front made
        # every no-op run leave a numbered empty dir (`…-2`, `…-3`, …) behind,
        # accumulating clutter inside the very tree this feature exists to tidy.
        print("Nothing to prune — no inert or safe-to-discard recovery leftovers "
              f"in scope. Preserved {len(kept)} surface(s) (never pruned).")
        return 0

    # The log folder lives in its OWN root, NOT under `upgrade-backups/`. A
    # pruned `upgrade-backups/{pair}` copied to a destination inside
    # `upgrade-backups/` would reclaim nothing — it would relocate the pair to
    # `upgrade-backups/<log>/upgrade-backups/{pair}`, where the sweep's
    # `*-to-*` glob can never see it again, so the surface would be neither
    # gone nor reportable. A separate root keeps "pruned" and "swept" disjoint,
    # and makes non-collision with the de-scoped-rule prune log structural
    # rather than a matter of naming.
    logs_root = planwise_root / "upgrade-prune-logs"
    out_dir = logs_root / f"upgrade-leftovers-{today}"
    suffix = 2
    while out_dir.exists():
        out_dir = logs_root / f"upgrade-leftovers-{today}-{suffix}"
        suffix += 1
    out_dir.mkdir(parents=True, exist_ok=True)

    removed: list[dict] = []
    for f in prunable:
        src = Path(f["path"])
        # Mirror src's path relative to the planwise root (e.g.
        # upgrade-backups/{pair}/ or upgrade-conflicts/{pair}/
        # verdicts.json.consumed) rather than hand-building {pair}/{name} —
        # a whole-pair-directory surface's src.name IS the pair name, so
        # {pair}/{src.name} would double-nest it (…/{pair}/{pair}/file).
        try:
            rel = src.relative_to(planwise_root)
        except ValueError:
            rel = Path(f["pair"]) / src.name  # fallback if src ever lands outside planwise_root
        backup_dst = out_dir / rel

        # STEP 1 — copy. A failure here is safe to roll back: nothing has been
        # removed yet, so discarding a half-written copy loses nothing.
        try:
            backup_dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, backup_dst, dirs_exist_ok=True)
            else:
                backup_dst.write_bytes(src.read_bytes())
        except OSError as exc:
            kept.append({**f, "klass": "REMOVE_FAILED",
                         "reason": f"could not back up ({exc}) — left in place, not removed"})
            if backup_dst.is_dir():
                shutil.rmtree(backup_dst, ignore_errors=True)
            else:
                backup_dst.unlink(missing_ok=True)
            continue

        # STEP 2 — remove, in its OWN try. Once this starts, the copy is the
        # ONLY surviving record of anything already deleted, so the rollback
        # above MUST NOT run here: `shutil.rmtree` is not atomic and routinely
        # fails part-way on a locked or read-only file, which would leave the
        # source partially deleted. Deleting the backup in that state destroys
        # the sole copy of the files that are already gone.
        try:
            if src.is_dir():
                shutil.rmtree(src)
            else:
                src.unlink()
            removed.append(f)
        except OSError as exc:
            kept.append({**f, "klass": "REMOVE_FAILED",
                         "reason": f"removal failed part-way ({exc}) — a complete "
                                   f"pre-removal copy is preserved at `{backup_dst}`; "
                                   "the original may be partially deleted, restore from "
                                   "that copy rather than re-running"})

    lines = [f"# Upgrade recovery-leftover prune — {today}", ""]
    lines.append(f"## Removed ({len(removed)})")
    for f in removed:
        lines.append(f"- `{f['path']}` ({f['count']} file(s), {f['age_days']}d old) — "
                     f"{f['klass']}: {RECOVERY_ARTIFACT_CLASSES[f['klass']]}")
    lines.append("")
    lines.append(f"## Preserved ({len(kept)})")
    for f in kept:
        reason = f.get("reason", RECOVERY_ARTIFACT_CLASSES.get(f["klass"], "out of prune scope"))
        lines.append(f"- `{f['path']}` [{f['klass']}] — {reason}")
    if removed:
        lines.append("")
        lines.append("Pre-removal copies of every pruned path above sit alongside this "
                      "log in this same folder, mirroring each path's original location "
                      "relative to the planwise root.")
    (out_dir / "PRUNED-LEFTOVERS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Pruned {len(removed)} recovery-leftover surface(s) (inert/safe-to-discard); "
          f"preserved {len(kept)} (action-required/review-then-discard, never pruned). "
          f"Log: {out_dir / 'PRUNED-LEFTOVERS.md'}")
    return 0


def _list_diverged_rows(cfg: "InitConfig") -> list[dict]:
    """Read-only: return the diverged rule minority as a list of dict rows.

    Walks DESCOPED_RULES and INSTALLED_RULES present on disk; compares
    installed vs shipped using the SAME normalization the writer uses
    (`normalize_rule_for_diff()`). A row is emitted only when the bodies
    differ — the byte/normalized-identical majority is skipped and never
    reaches the primitive. Stable-sorted by (kind, filename) so a downstream
    fan-out batch is reproducible. Returns `[]` when nothing diverges. Never
    writes or deletes anything; a per-file OSError is skipped rather than
    raised so one unreadable file cannot hide the rest of the diverged set.
    """
    refs_dir = cfg.plugin_root / "references"
    rules_dst_dir = cfg.project_root / ".claude" / "rules" / "planwise"

    rows: list[dict] = []

    for filename, _template in list(INSTALLED_RULES) + list(DESCOPED_RULES):
        dst = rules_dst_dir / filename
        src = refs_dir / filename
        if not dst.is_file() or not src.is_file():
            continue
        try:
            installed_raw = dst.read_text(encoding="utf-8")
            shipped_raw = src.read_text(encoding="utf-8")
        except OSError:
            continue
        if normalize_rule_for_diff(installed_raw) != normalize_rule_for_diff(shipped_raw):
            rows.append({
                "filename": filename,
                "kind": "rule",
                "installed": dst.relative_to(cfg.project_root).as_posix(),
                "shipped": src.relative_to(cfg.plugin_root).as_posix(),
            })

    rows.sort(key=lambda r: (r["kind"], r["filename"]))
    return rows


def _run_list_diverged(cfg: "InitConfig") -> int:
    """Execute the --list-diverged diagnostic. Prints json.dumps(rows) (an
    empty array when nothing diverges) and returns 0. Read-only — mutates
    nothing; the cheap gate that decides whether a fan-out is even worth
    spawning. See `_list_diverged_rows()` for the comparison logic.
    """
    print(json.dumps(_list_diverged_rows(cfg)))
    return 0


def _resolve_doctor_config_path(cfg: "InitConfig") -> "Path | None":
    """Locate config.yaml for the version-state gate, mirroring the doctor
    Config Gate resolution: the default planwise root first, then any
    `*/config.yaml` one level down from the project root. Returns None when no
    config is found (uninitialized install). Read-only."""
    primary = cfg.project_root / cfg.planwise_root / "config.yaml"
    if primary.exists():
        return primary
    for candidate in sorted(cfg.project_root.glob("*/config.yaml")):
        return candidate
    return None


def _read_pinned_plugin_version(config_path: "Path") -> str:
    """Read the pinned top-level plugin_version from config.yaml WITHOUT
    requiring PyYAML, so the read-only doctor gate works even when yaml is
    unavailable. Returns "0.0.0" (the never-pinned sentinel, matching
    read_plugin_version) when the key is absent or the file can't be read."""
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    m = re.search(r'^\s*plugin_version:\s*("([^"]*)"|(\S+))\s*$', text, re.MULTILINE)
    if not m:
        return "0.0.0"
    return (m.group(2) if m.group(2) is not None else m.group(3)).strip()


def _read_configured_plugin_root(config_path: "Path") -> "Path | None":
    """Read the top-level plugin_root from config.yaml WITHOUT requiring
    PyYAML, mirroring _read_pinned_plugin_version() — so the read-only doctor
    gate works even when yaml is unavailable. Returns None when the key is
    absent, empty, or the file can't be read: a missing plugin_root is not
    itself a fault (a pre-migration config never had the key), so the
    version-state gate below simply skips the root checks in that case."""
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^\s*plugin_root:\s*("([^"]*)"|(\S+))\s*$', text, re.MULTILINE)
    if not m:
        return None
    value = (m.group(2) if m.group(2) is not None else m.group(3)).strip()
    return Path(value) if value else None


def _doctor_version_gate(cfg: "InitConfig") -> dict:
    """Read-only plugin version-state preflight for /planwise doctor.

    Compares the project's pinned plugin_version against the installed plugin
    (cfg.plugin_version, from read_plugin_version() against the LIVE plugin
    root — never the configured plugin_root — so this comparison alone is
    immune to a stale plugin_root). Only once that comparison is healthy does
    the gate check the SEPARATE plugin_root: key other handlers resolve
    scripts through: a legacy upgrade could have bumped plugin_version
    without repointing it (predating the commit point that now writes both
    together — see _commit_upgrade_pin()), or the directory it names could
    have been reaped since. Returns a dict with:
      state:  "uninitialized"  (no config.yaml)                        -> recommend /planwise init
              "drift"          (pinned != installed)                   -> recommend /planwise upgrade
              "root_dangling"  (pinned == installed, but the configured
                                plugin_root directory no longer exists) -> recommend /planwise upgrade
              "root_mismatch"  (pinned == installed, but the configured
                                plugin_root directory's own version !=
                                pinned)                                 -> recommend /planwise upgrade
              "ok"             (pinned == installed, and plugin_root,
                                when present, resolves and matches)      -> proceed with diagnostics
      report: the lines to print verbatim.
    Never mutates anything — doctor only recommends; init/upgrade are the only
    writers (they bump the pin and repoint plugin_root together)."""
    installed = cfg.plugin_version
    config_path = _resolve_doctor_config_path(cfg)

    lines = ["Plugin version-state gate"]
    if config_path is None:
        lines.append(f"  ! Not initialized — no config.yaml under {cfg.project_root}.")
        lines.append("    Recommend: /planwise init")
        return {"state": "uninitialized", "report": "\n".join(lines)}

    pinned = _read_pinned_plugin_version(config_path)
    if pinned != installed:
        lines.append(f"  ! Version drift — pinned {pinned} != installed {installed}.")
        lines.append("    Recommend: /planwise upgrade")
        return {"state": "drift", "report": "\n".join(lines)}

    configured_root = _read_configured_plugin_root(config_path)
    if configured_root is not None:
        if not configured_root.exists():
            lines.append(f"  ! plugin_root dangling — {configured_root} does not exist.")
            lines.append("    Recommend: /planwise upgrade (repoints plugin_root)")
            return {"state": "root_dangling", "report": "\n".join(lines)}
        root_version = read_plugin_version(configured_root)
        if root_version != pinned:
            lines.append(
                f"  ! plugin_root version mismatch — {configured_root} is "
                f"{root_version}, pinned is {pinned}."
            )
            lines.append("    Recommend: /planwise upgrade (repoints plugin_root)")
            return {"state": "root_mismatch", "report": "\n".join(lines)}

    lines.append(f"  plugin version {installed} — up to date")
    return {"state": "ok", "report": "\n".join(lines)}


def _detect_orphaned_block_signature(text: str) -> str | None:
    """Return the key name carrying an orphaned child block, or None.

    The signature: a key line whose value is a complete inline flow mapping
    (`key: {...}`) directly followed by deeper-indented bare `key: value` lines.
    That is what a single-line targeted writer leaves behind when it replaces
    the parent line of a block mapping without consuming the block — the old
    children survive under a value that is already complete, and the parser
    stops at the first of them.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)([A-Za-z_][\w-]*):\s*\{.*\}\s*(?:#.*)?$", line)
        if not m:
            continue
        indent = len(m.group(1))
        for nxt in lines[i + 1:]:
            if not nxt.strip():
                break
            nxt_indent = len(nxt) - len(nxt.lstrip())
            if nxt_indent <= indent:
                break
            if nxt.lstrip().startswith("#"):
                continue
            if re.match(r"^\s*[A-Za-z_][\w-]*:", nxt):
                return m.group(2)
            break
    return None


def _doctor_config_parse_check(cfg: "InitConfig") -> dict | None:
    """Read-only YAML parse check of the resolved project config.

    The version gate above reads the pinned version with a regex, so it stays
    green on a config that no longer parses — and every other command then dies
    on a raw parser traceback with no diagnosis. This stage loads the file with
    the real parser and reports the failure loudly, adding a specific hint when
    the orphaned-block signature is present.

    Returns None when there is nothing to check (no config on disk, or no YAML
    parser available), otherwise {"state": "ok"|"unparseable", "report": str}.
    Never mutates anything — doctor only reports and recommends.
    """
    if not HAS_YAML:
        return None
    config_path = _resolve_doctor_config_path(cfg)
    if config_path is None:
        return None

    lines = ["Config parse check"]
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        lines.append(f"  ! {config_path} could not be read.")
        lines.append(f"      error:   {exc}")
        return {"state": "unparseable", "report": "\n".join(lines)}

    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        detail = str(exc).strip().splitlines()
        lines.append(f"  ! {config_path} does not parse as YAML.")
        lines.append(f"      parser:  {detail[0] if detail else exc}")
        orphan_key = _detect_orphaned_block_signature(text)
        if orphan_key:
            lines.append(
                f"      cause:   `{orphan_key}:` holds a complete single-line "
                f"{{...}} value with indented lines still beneath it."
            )
            lines.append(
                "      action:  delete the indented lines under that key — the "
                "single-line value already carries them."
            )
        else:
            lines.append(
                "      action:  fix the reported line, then re-run "
                "/planwise doctor to confirm."
            )
        lines.append("      note:    every planwise command fails until this parses.")
        return {"state": "unparseable", "report": "\n".join(lines)}

    lines.append(f"  {config_path.name} parses cleanly")
    return {"state": "ok", "report": "\n".join(lines)}


def _run_doctor(cfg: "InitConfig") -> int:
    """Run the read-only overscope linter + stale-rule sweep and print a report.

    Standalone diagnostic — does not require or perform an upgrade. Walks the
    installed rules, flags any scoped to plan/backlog/lessons globs, and prints
    one row per flagged rule with its size, a re-scope hint, and a total
    always-on injected-budget line. When any rule is flagged, also prints the
    per-glob-family worst-case injection rollup (compute_injection_families())
    — every rule sharing a glob co-injects on one path match — flagging any
    family over the configurable `context.token_saver_injection_ceiling`
    (default 40000 tokens). Then runs Stage 8, the post-boundary stale
    de-scoped rule sweep (sweep_stale_descoped_rules()), and prints its report
    too — always-on, independent of whether any rule was overscoped. Then runs
    Stage 9, the installed rule divergence lint (lint_installed_divergence()),
    and prints its report — also always-on. Then runs Stage 10, the orphaned
    agent-mirror sweep (sweep_orphaned_agent_mirrors()), and prints its report
    too — also always-on. Then runs Stage 14, the upgrade recovery-leftover
    sweep (sweep_upgrade_leftovers()), and prints its report — also
    always-on; a DISTINCT surface from Stages 8/10 (version-pair recovery
    directories, not installed rules/agents), pruned by a DISTINCT opt-in
    writer (`--prune-upgrade-leftovers`, never `--prune-stale`). Always exits
    0 (diagnostic, not a gate).

    Runs the plugin version-state gate FIRST (always-on, independent of Token
    Saver): an uninitialized or version-drifted install is surfaced with a
    remediation (init / upgrade) and the function returns before linting — no
    point auditing a stale rule surface. The config parse check runs next, and
    deliberately BEFORE that early return: a config that no longer parses is
    the reason every other command is failing, and the version gate cannot see
    it (it reads the pin with a regex). Read-only throughout; init/upgrade
    (and the two separate opt-in writers, `--prune-stale` and
    `--prune-upgrade-leftovers`) are the only writers.
    """
    gate = _doctor_version_gate(cfg)
    print(gate["report"])
    print()

    parse_check = _doctor_config_parse_check(cfg)
    if parse_check is not None:
        print(parse_check["report"])
        print()

    if gate["state"] != "ok":
        return 0

    overscoped = lint_rule_overscope(cfg)
    print("planwise doctor — rule overscope report")
    print()
    if not overscoped:
        print("No overscoped rules found.")
        print("All installed rules are scoped to code paths (.claude/** or narrower).")
    else:
        total_tokens = sum(item["approx_tokens"] for item in overscoped)
        print(f"Flagged {len(overscoped)} rule(s) scoped to plan/backlog/lessons globs:")
        print()
        for item in overscoped:
            print(
                f"  ~ {item['path']} ({item['line_count']} lines, "
                f"~{item['approx_tokens']} tokens; matches {item['matched_glob']})"
            )
            print("      hint: re-scope to code paths or convert to a handler-loaded reference")
        print()
        print(f"Total always-on injected budget from flagged rules: ~{total_tokens} tokens")

        families_result = compute_injection_families(cfg, overscoped)
        ceiling = families_result["ceiling"]
        print()
        print(
            f"Injection families (rules co-injected by a single path match; "
            f"ceiling ~{ceiling} tokens):"
        )
        for fam in families_result["families"]:
            mark = "!" if fam["over_ceiling"] else "~"
            status = "OVER CEILING" if fam["over_ceiling"] else "within ceiling"
            print(f"  {mark} {fam['glob']}")
            print(
                f"      rules: {fam['rule_count']}   size: {fam['total_lines']} lines "
                f"(~{fam['total_tokens']} tokens)   {status}"
            )

    # Stage 8: post-boundary stale de-scoped rule sweep — read-only, always-on.
    print()
    print("planwise doctor — stale de-scoped rule sweep (post-boundary)")
    print()
    stale = sweep_stale_descoped_rules(cfg)
    if not stale:
        print("No stale de-scoped rules found — install is past the boundary and clean.")
    else:
        print("Stale de-scoped rules still installed under .claude/rules/planwise/:")
        for f in stale:
            mark = "!" if f["verdict"] == "PRESERVE" else "~"
            verdict_label = f["verdict"]
            if verdict_label == "RELOCATE":
                verdict_label += " (prefix-rename fingerprint)"
            print(f"  {mark} {f['filename']}   {verdict_label}")
            print(f"      size:    {f['line_count']} lines (~{f['approx_tokens']} tokens)")
            print(f"      reason:  {f['reason']}")
            if f["verdict"] == "REMOVABLE":
                print("      action:  remove with /planwise doctor --prune-stale")
            elif f["verdict"] == "PRESERVE":
                print("      action:  re-home to .claude/rules/<project>/<name>.md — do NOT delete")
            else:  # RELOCATE
                print("      action:  migrate to .claude/rules/<project>/<name>.md")
        removable = [f for f in stale if f["verdict"] == "REMOVABLE"]
        print()
        print(f"Total REMOVABLE always-on budget: ~{sum(f['approx_tokens'] for f in removable)} "
              f"tokens across {len(removable)} rule(s).")

    # Stage 9: installed rule divergence lint — read-only, always-on.
    print()
    print("planwise doctor — installed rule divergence lint")
    print()
    diverged = lint_installed_divergence(cfg)
    if not diverged:
        print("All installed rules match shipped — no divergence found.")
    else:
        mark_by_classification = {
            "SUBSET": "~", "HAS_UNIQUE": "!", "NOT_ANALYZED": "?", "UNVERIFIABLE": "?",
        }
        for f in diverged:
            mark = mark_by_classification.get(f["classification"], "!")
            print(f"  {mark} {f['path']}   {f['classification']}")
            print(f"      size:    {f['line_count']} lines (~{f['approx_tokens']} tokens)")
            print(f"      action:  {f['recommendation']}")

    # Stage 10: orphaned agent-mirror sweep — read-only, always-on.
    print()
    print("planwise doctor — orphaned agent mirror sweep")
    print()
    orphaned_agents = sweep_orphaned_agent_mirrors(cfg)
    if not orphaned_agents:
        print("No orphaned agent mirrors found — install has none of the formerly "
              "mirrored agents left, or they already match shipped.")
    else:
        print("Orphaned agent mirrors still installed under .claude/agents/:")
        for f in orphaned_agents:
            mark = "!" if f["verdict"] == "PRESERVE" else "~"
            print(f"  {mark} {f['filename']}   {f['verdict']}")
            print(f"      size:    {f['line_count']} lines (~{f['approx_tokens']} tokens)")
            print(f"      reason:  {f['reason']}")
            if f["verdict"] == "REMOVABLE":
                print("      action:  remove with /planwise doctor --prune-stale")
            else:
                print("      action:  keep in place — customization detected, do NOT delete")
        removable_agents = [f for f in orphaned_agents if f["verdict"] == "REMOVABLE"]
        print()
        print(f"Total REMOVABLE orphaned agent mirror(s): {len(removable_agents)} of "
              f"{len(orphaned_agents)} found.")

    # Stage 14: upgrade recovery-leftover sweep — read-only, always-on.
    print()
    print("planwise doctor — upgrade recovery-leftover sweep")
    print()
    leftovers = sweep_upgrade_leftovers(cfg)
    if not leftovers:
        print("No leftover recovery directories found — no version-pair backups, "
              "transfers, or conflict artifacts on disk.")
    else:
        pairs = sorted({f["pair"] for f in leftovers})
        print(f"Leftover recovery artifacts across {len(pairs)} version pair(s):")
        for f in leftovers:
            mark = "!" if f["klass"] == "action-required" else "~"
            print(f"  {mark} {f['pair']}   {f['surface']}   {f['klass']}")
            print(f"      path:    {f['path']}")
            print(f"      size:    {f['count']} file(s), {f['age_days']}d old")
            print(f"      meaning: {RECOVERY_ARTIFACT_CLASSES[f['klass']]}")
            if f["klass"] in ("inert", "safe-to-discard"):
                print("      action:  remove with /planwise doctor --prune-upgrade-leftovers")
            else:
                print("      action:  resolve per handlers/upgrade.md Step 4 — never auto-pruned")
        prunable = [f for f in leftovers if f["klass"] in ("inert", "safe-to-discard")]
        print()
        print(f"Total prunable (inert/safe-to-discard) leftover(s): {len(prunable)} of "
              f"{len(leftovers)} found.")
    return 0


