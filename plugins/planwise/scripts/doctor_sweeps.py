"""Read-only doctor sweeps: overscope lint, stale-rule sweep, orphaned agent
mirrors, and installed-rule divergence lint.

Diagnostic primitives consumed by doctor_cli's `--doctor` / `--prune-stale` /
`--list-diverged` dispatchers. All four sweeps are read-only; divergence
classification is delegated to rule_divergence. `compute_injection_families()`
extends the overscope lint with a per-glob-family worst-case rollup and a
configurable warn ceiling, reusing lint_rule_overscope()'s per-file discovery
rather than re-deriving it.
"""

import re
from pathlib import Path  # noqa: F401 -- used by the nested _check() helper below

try:
    from config_gen import InitConfig  # noqa: F401 -- type-hint only (quoted forward refs)
except ImportError:
    raise ImportError(
        "config_gen is required for doctor_sweeps's InitConfig type "
        "references; the scripts/ directory appears to be partially installed"
    )

try:
    from rule_divergence import (
        normalize_rule_for_diff,
        _classify_diverged,
        _destructively_removable,
        is_subset,
        is_safe_to_remove,
        _verdict_not_analyzed,
        _extract_paths_value,
    )
except ImportError:
    raise ImportError(
        "rule_divergence is required for doctor_sweeps's structural-verdict "
        "classification; the scripts/ directory appears to be partially "
        "installed"
    )

try:
    from init_project import DESCOPED_RULES, INSTALLED_RULES
except ImportError:
    raise ImportError(
        "init_project is required for doctor_sweeps's DESCOPED_RULES/"
        "INSTALLED_RULES tables (R1: the tuples stay on the residual); the "
        "scripts/ directory appears to be partially installed"
    )


# Frozen filename list for the post-boundary orphaned-mirror sweep: the agent
# files formerly mirrored into .claude/agents/ on init. No live install list
# remains after the mirror drop; this frozen copy lets the sweep recognize an
# orphaned mirror without re-deriving the set.
FORMERLY_MIRRORED_AGENTS = [
    "fix-agent.md",
    "plan-reviewer.md",
    "structural-reviewer.md",
    "task-runner.md",
    "rule-comparator.md",
]


def lint_rule_overscope(cfg: "InitConfig") -> list[dict]:
    """Flag installed rules scoped to plan/backlog/lessons globs. Read-only.

    Walks every ``.claude/rules/**/*.md`` file (recursive, including
    project-authored rules), parses its paths: frontmatter, and records a flag
    when the value references the plans, backlog, or lessons globs derived from
    cfg. Each flagged entry carries the path, a line count, an approximate
    injected-token estimate (~13 tokens/line), and the matched glob so the
    caller can render a re-scope hint.

    Never writes or deletes anything — purely diagnostic.
    """
    rules_root = cfg.project_root / ".claude" / "rules"
    if not rules_root.exists():
        return []

    plans_glob = f"{cfg.planwise_root}/{cfg.plans_dir}/**"
    backlog_glob = f"{cfg.planwise_root}/{cfg.backlog_dir}/**"
    lessons_glob = f"{cfg.planwise_root}/{cfg.lessons_dir}/**"
    watched_globs = (plans_glob, backlog_glob, lessons_glob)

    flagged: list[dict] = []
    for md_file in sorted(rules_root.rglob("*.md")):
        if not md_file.is_file():
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # A non-UTF-8/unreadable file cannot be over-scope-linted, and it
            # must never crash the always-exit-0 doctor path — skip it here;
            # the Stage 9 divergence lint surfaces it as UNVERIFIABLE.
            continue
        paths_value = _extract_paths_value(content)
        if not paths_value:
            continue
        matched = next((g for g in watched_globs if g in paths_value), None)
        if matched is None:
            continue
        line_count = content.count("\n") + (0 if content.endswith("\n") else 1)
        flagged.append({
            "path": str(md_file),
            "line_count": line_count,
            "approx_tokens": line_count * 13,
            "matched_glob": matched,
        })
    return flagged


# Fallback ceiling for compute_injection_families() when config.yaml has no
# context.token_saver_injection_ceiling key yet (Task 06 has not landed the
# config-plumbing surface as of this sweep). Derived, not sacred: set below
# the measured ~56,000-tokens-per-affected-session average so a broad-rule-
# surface install still warns. This is the ONLY literal 40000 in this module
# -- every fallback path below reads this constant rather than repeating it.
_INJECTION_CEILING_DEFAULT = 40000


def _read_injection_ceiling(cfg: "InitConfig") -> int:
    """Read context.token_saver_injection_ceiling from config.yaml. Read-only.

    Self-contained regex read -- no config_loader dependency, no PyYAML
    requirement -- mirroring doctor_cli's _read_pinned_plugin_version(). Task
    06 (the config-plumbing surface: config.yaml.template, config_loader,
    config_gen) has not landed when this sweep runs, so this is the single
    default-fallback site; Task 06 reconciles its own writer against this same
    read site rather than introducing a second code path.

    Falls back to _INJECTION_CEILING_DEFAULT when config.yaml cannot be
    resolved, cannot be read, or the key is absent/unparseable.
    """
    config_path = cfg.project_root / cfg.planwise_root / "config.yaml"
    if not config_path.exists():
        candidates = sorted(cfg.project_root.glob("*/config.yaml"))
        if not candidates:
            return _INJECTION_CEILING_DEFAULT
        config_path = candidates[0]
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return _INJECTION_CEILING_DEFAULT
    match = re.search(
        r"^\s*token_saver_injection_ceiling:\s*(\d+)", text, re.MULTILINE
    )
    if not match:
        return _INJECTION_CEILING_DEFAULT
    try:
        return int(match.group(1))
    except ValueError:
        return _INJECTION_CEILING_DEFAULT


def compute_injection_families(cfg: "InitConfig", flagged: list[dict]) -> dict:
    """Group lint_rule_overscope()'s flagged rules into glob families. Read-only.

    A "family" is every flagged rule sharing the same matched_glob: any single
    path read under that plan/backlog/lessons glob co-injects the whole family
    into one context window, so the family's summed tokens (not any one rule's
    own size) is the worst-case injection cost. Reuses the line counts and
    approx_tokens lint_rule_overscope() already computed -- never re-derives
    them, and never touches the filesystem itself.

    Returns {"ceiling": int, "families": [...]} where each family dict is
    {"glob": str, "rule_count": int, "total_lines": int, "total_tokens": int,
    "over_ceiling": bool}, sorted by descending total_tokens (worst first).
    An empty `flagged` list yields an empty `families` list -- the correct
    zero-report on a narrow-rule-surface project.
    """
    ceiling = _read_injection_ceiling(cfg)
    by_glob: dict[str, list[dict]] = {}
    for item in flagged:
        by_glob.setdefault(item["matched_glob"], []).append(item)

    families = []
    for glob, items in by_glob.items():
        total_lines = sum(i["line_count"] for i in items)
        total_tokens = sum(i["approx_tokens"] for i in items)
        families.append({
            "glob": glob,
            "rule_count": len(items),
            "total_lines": total_lines,
            "total_tokens": total_tokens,
            "over_ceiling": total_tokens > ceiling,
        })
    families.sort(key=lambda f: f["total_tokens"], reverse=True)
    return {"ceiling": ceiling, "families": families}


def sweep_stale_descoped_rules(cfg: "InitConfig") -> list[dict]:
    """Post-boundary stale de-scoped rule sweep. Read-only.

    Mirrors lint_rule_overscope(): walks the still-installed DESCOPED_RULES
    under .claude/rules/planwise/ — the leftovers the one-shot
    migrate_installed_rules() never reached (its version gate is spent for any
    install already past RESCOPE_MIGRATION_VERSION) — classifies each against
    the shipped references/ copy, and recommends a disposition. NEVER writes or
    deletes; purely diagnostic.

    Each finding is a dict:
      {path, filename, line_count, approx_tokens (=line_count*13),
       verdict: "REMOVABLE" | "PRESERVE" | "RELOCATE", confidence, reason
       [, unique_blocks]}

    REMOVABLE requires BOTH a high-confidence subset verdict (is_subset AND
    is_safe_to_remove) AND an empty verdict.notes field — non-empty notes means
    the matcher tolerated installed-only content (e.g. sub-noise-floor
    fragments) it could not prove was noise, which flips the disposition to
    PRESERVE rather than risk deleting a genuine short customization.
    """
    rules_planwise = cfg.project_root / ".claude" / "rules" / "planwise"
    rules_root = cfg.project_root / ".claude" / "rules"
    refs_dir = cfg.plugin_root / "references"
    findings: list[dict] = []
    if not rules_root.exists():
        return findings

    descoped_names = {fn for fn, _ in DESCOPED_RULES}

    for filename, _old_template in DESCOPED_RULES:
        dst = rules_planwise / filename
        if not dst.is_file():
            continue  # already migrated/removed — nothing stale here
        try:
            installed_raw = dst.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # An unclassifiable file must never be deletable — preserve
            # unread rather than guess at its disposition.
            findings.append({"path": str(dst), "filename": filename,
                             "line_count": 0, "approx_tokens": 0,
                             "verdict": "PRESERVE", "confidence": "unknown",
                             "reason": f"unreadable ({exc}) — cannot classify; preserved"})
            continue
        line_count = installed_raw.count("\n") + (0 if installed_raw.endswith("\n") else 1)
        base = {"path": str(dst), "filename": filename,
                "line_count": line_count, "approx_tokens": line_count * 13}
        try:
            shipped_raw = (refs_dir / filename).read_text(encoding="utf-8")
        except FileNotFoundError:
            findings.append({**base, "verdict": "PRESERVE", "confidence": "unknown",
                             "reason": "shipped reference unavailable — cannot prove "
                                       "stale; re-home if customized"})
            continue

        inst_norm = normalize_rule_for_diff(installed_raw)
        ship_norm = normalize_rule_for_diff(shipped_raw)
        if inst_norm == ship_norm:
            findings.append({**base, "verdict": "REMOVABLE", "confidence": "exact",
                             "reason": "untouched de-scoped rule the one-shot migration "
                                       "never reached; handler-loaded from references/"})
            continue

        v = _classify_diverged(inst_norm, ship_norm)
        # `v.notes` (set by classify_blocks) flags sub-noise-floor installed-only
        # content tolerated during matching — surface it in the reason whenever
        # present so a human sees the caveat before acting on the verdict.
        notes_suffix = f" ({v.notes})" if getattr(v, "notes", "") else ""
        if _destructively_removable(v):
            findings.append({**base, "verdict": "REMOVABLE", "confidence": v.confidence,
                             "reason": "stale subset of the now-grown shipped reference; "
                                       "handler-loaded from references/"})
        elif is_subset(v) and is_safe_to_remove(v):
            # Safe-to-remove EXCEPT the notes field is non-empty — the matcher
            # tolerated installed-only content (e.g. sub-noise-floor fragments).
            # Deletion needs BOTH the high-confidence subset verdict AND a clean
            # notes field; preserve rather than risk destroying a short
            # customization. The automated transfer-then-adopt flow (and the
            # assisted relocation handoff) apply to the --upgrade artifact
            # refresh, not this read-only sweep, so this finding stays PRESERVE
            # here and the customization is re-homed by hand.
            findings.append({**base, "verdict": "PRESERVE", "confidence": v.confidence,
                             "unique_blocks": v.unique_blocks,
                             "reason": "subset, but the matcher tolerated installed-only "
                                       "content" + notes_suffix + "; preserved rather than "
                                       "risk deleting a customization — re-home to "
                                       ".claude/rules/<project>/<name>.md, do NOT delete"})
        else:
            findings.append({**base, "verdict": "PRESERVE", "confidence": v.confidence,
                             "unique_blocks": v.unique_blocks,
                             "reason": "genuine customization (unique content) — re-home "
                                       "to .claude/rules/<project>/<name>.md, do NOT delete"
                                       + notes_suffix})

    # Hack-detection bonus: the old prefix-rename workaround produced files named
    # "<anything>-<shipped-descoped-name>.md" to dodge the de-scope. Flag the
    # fingerprint and point at the proper project-scoped home.
    for md in sorted(rules_root.rglob("*.md")):
        if not md.is_file():
            continue
        for dn in descoped_names:
            if md.name != dn and md.name.endswith("-" + dn):
                try:
                    raw = md.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                lc = raw.count("\n") + (0 if raw.endswith("\n") else 1)
                findings.append({"path": str(md), "filename": md.name,
                                 "line_count": lc, "approx_tokens": lc * 13,
                                 "verdict": "RELOCATE", "confidence": "fingerprint",
                                 "reason": "prefix-rename hack fingerprint of a de-scoped "
                                           "rule — migrate to .claude/rules/<project>/<name>.md"})
                break
    return findings


def sweep_orphaned_agent_mirrors(cfg: "InitConfig") -> list[dict]:
    """Post-mirror-drop orphaned agent-mirror sweep. Read-only.

    Parallels sweep_stale_descoped_rules(): walks FORMERLY_MIRRORED_AGENTS —
    the frozen filename list of agents that used to be mirrored into
    .claude/agents/ on init/upgrade — classifies each still-installed copy
    against the shipped agents/{filename} reference, and recommends a
    disposition. Every install's mirrored copy became an orphan the moment
    the mirror-on-init/upgrade behavior was dropped (there is no live
    install list left to gate a one-shot migration against), so this sweep
    is a permanent, always-on diagnostic rather than a version-boundary-
    gated one-shot. NEVER writes or deletes; purely diagnostic.

    Comparison is whole-file identity (agents carry no `paths:` frontmatter
    key to normalize away, unlike rules) — a customized `model:`/`tools:`/
    `maxTurns:` pin simply makes the whole file diverge and correctly routes
    to HAS_UNIQUE/PRESERVE; there is no frontmatter-splice guard here.

    Each finding is a dict:
      {path, filename, line_count, approx_tokens (=line_count*13),
       verdict: "REMOVABLE" | "PRESERVE", confidence, reason
       [, unique_blocks]}

    REMOVABLE requires EITHER a byte-identical installed/shipped pair (fast
    path — the primitive is never consulted) OR a high-confidence subset
    verdict from `_classify_diverged()` that clears `_destructively_removable`
    (is_subset AND is_safe_to_remove AND an empty verdict.notes field) —
    non-empty notes means the matcher tolerated installed-only content it
    could not prove was noise, which flips the disposition to PRESERVE
    rather than risk deleting a genuine short customization. A missing
    shipped reference, an unreadable installed/shipped file, and a degraded
    (structural_compare unavailable) verdict all PRESERVE — never a
    confident recommendation on incomplete evidence.
    """
    agents_dir = cfg.project_root / ".claude" / "agents"
    agents_src_dir = cfg.plugin_root / "agents"
    findings: list[dict] = []
    if not agents_dir.exists():
        return findings

    for filename in FORMERLY_MIRRORED_AGENTS:
        dst = agents_dir / filename
        if not dst.is_file():
            continue  # not installed — nothing to do, not a broken install

        try:
            installed_raw = dst.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            # An unclassifiable file must never be deletable — preserve
            # unread rather than guess at its disposition.
            findings.append({"path": str(dst), "filename": filename,
                             "line_count": 0, "approx_tokens": 0,
                             "verdict": "PRESERVE", "confidence": "unknown",
                             "reason": f"unreadable ({exc}) — cannot classify; preserved"})
            continue

        line_count = installed_raw.count("\n") + (0 if installed_raw.endswith("\n") else 1)
        base = {"path": str(dst), "filename": filename,
                "line_count": line_count, "approx_tokens": line_count * 13}

        src = agents_src_dir / filename
        try:
            shipped_raw = src.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            findings.append({**base, "verdict": "PRESERVE", "confidence": "unknown",
                             "reason": "shipped reference unavailable — cannot prove "
                                       "stale; preserved"})
            continue
        except (OSError, UnicodeDecodeError) as exc:
            findings.append({**base, "verdict": "PRESERVE", "confidence": "unknown",
                             "reason": f"shipped reference unreadable ({exc}) — cannot "
                                       "classify; preserved"})
            continue

        if installed_raw == shipped_raw:
            findings.append({**base, "verdict": "REMOVABLE", "confidence": "exact",
                             "reason": "untouched shipped agent, orphaned by the dropped "
                                       "mirror"})
            continue

        v = _classify_diverged(installed_raw, shipped_raw)
        # `v.notes` (set by classify_blocks) flags sub-noise-floor installed-only
        # content tolerated during matching — surface it in the reason whenever
        # present so a human sees the caveat before acting on the verdict.
        notes_suffix = f" ({v.notes})" if getattr(v, "notes", "") else ""
        if _destructively_removable(v):
            findings.append({**base, "verdict": "REMOVABLE", "confidence": v.confidence,
                             "reason": "stale/reorganized subset of the shipped agent"})
        elif is_subset(v) and is_safe_to_remove(v):
            # Safe-to-remove EXCEPT the notes field is non-empty — the matcher
            # tolerated installed-only content. Preserve rather than risk
            # destroying a short customization; this read-only sweep never
            # transfers/relocates content, unlike the --upgrade artifact
            # refresh, so the finding stays PRESERVE here.
            findings.append({**base, "verdict": "PRESERVE", "confidence": v.confidence,
                             "unique_blocks": v.unique_blocks,
                             "reason": "subset, but the matcher tolerated installed-only "
                                       "content" + notes_suffix + "; preserved rather than "
                                       "risk deleting a customization"})
        else:
            findings.append({**base, "verdict": "PRESERVE", "confidence": v.confidence,
                             "unique_blocks": v.unique_blocks,
                             "reason": "genuine customization (unique content) — keep or "
                                       "upstream, do NOT delete" + notes_suffix})
    return findings


def lint_installed_divergence(cfg: "InitConfig") -> list[dict]:
    """Read-only: report still-installed rules whose body diverges
    from the plugin-shipped reference.

    Generalizes the de-scoped-rule sweep (sweep_stale_descoped_rules, above)
    from DESCOPED_RULES to the still-installed set: walks INSTALLED_RULES,
    comparing each installed copy to its shipped reference with the same
    normalization the writer uses (normalize_rule_for_diff()), reading BOTH
    sides with ``utf-8-sig`` — the same encoding the artifact refresh writer
    reads with — so a BOM'd-but-untouched installed file is never falsely
    reported diverged (a BOM defeats normalize_rule_for_diff's
    frontmatter-anchored detection under plain ``utf-8``). A
    normalized-identical pair is skipped before `_classify_diverged` is ever
    called — the byte-identical fast path.

    A diverged pair is classified via `_classify_diverged()` and recommended:
      * The degraded not-analyzed stand-in (`_verdict_not_analyzed()` —
        structural_compare unavailable, no analysis ran) -> an explicit
        NOT_ANALYZED row, never a confident recommendation (mirrors the
        migrate/upgrade NOT-analyzed notice convention).
      * SUBSET with empty ``notes`` -> recommend `/planwise upgrade`
        (auto-adopts shipped; matches the writer's own auto-adopt gate,
        `is_subset(verdict) and not verdict.notes`).
      * SUBSET with non-empty ``notes`` (the matcher tolerated
        installed-only content) -> a recommendation that upgrade will
        transfer that content first (or preserve it in place, depending on
        `upgrade.customization_handoff`) before adopting shipped — NOT the
        unconditional auto-adopt wording, since the writer's auto-adopt gate
        does not fire on a non-empty notes field.
      * HAS_UNIQUE -> re-home per the "Choosing a Home for a Rule
        Customization" decide callout.

    A missing shipped reference (broken/partial install) and an unreadable
    installed or shipped file (`OSError` or `UnicodeDecodeError` — e.g.
    non-UTF-8 content) both surface as an explicit UNVERIFIABLE row rather
    than a silent skip: a silent skip would let the caller's all-clear line
    print on a broken or partially-unreadable install, and an uncaught
    `UnicodeDecodeError` would crash the always-on bare `/planwise doctor`
    path. A rule that is simply not installed (no destination file)
    stays a silent skip — that is the normal, expected case, not a broken
    install. NEVER writes or deletes; purely diagnostic, like the
    de-scoped-rule sweep and lint_rule_overscope(). Wired into
    `_run_doctor()`, which calls `lint_installed_divergence(cfg)` immediately
    after the Stage 8 sweep call so the bare `/planwise doctor` emits this
    report too; the caller's all-clear line ("All installed rules
    match shipped") must print ONLY when this returns `[]` — i.e. nothing
    diverged AND nothing was unverifiable/not-analyzed.

    Each finding is a dict:
      {path, kind ("rule"), classification ("SUBSET" |
       "HAS_UNIQUE" | "NOT_ANALYZED" | "UNVERIFIABLE"), line_count,
       approx_tokens (=line_count*13), recommendation}
    """
    rules_dst_dir = cfg.project_root / ".claude" / "rules" / "planwise"
    refs_dir = cfg.plugin_root / "references"

    def _check(dst: Path, src: Path, kind: str, norm) -> dict | None:
        if not dst.is_file():
            return None   # not installed — nothing to check, not a broken install

        # utf-8-sig: mirrors the artifact refresh writer's own read encoding
        # (see upgrade_artifacts()) so a leading BOM cannot defeat the
        # frontmatter-anchored comparison and falsely report a divergence.
        try:
            installed_raw = dst.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            # A non-UTF-8 (or otherwise unreadable) installed file must
            # never crash the always-exit-0 doctor path — report it as
            # unverifiable instead of letting the exception escape.
            return {"path": str(dst), "kind": kind, "classification": "UNVERIFIABLE",
                    "line_count": 0, "approx_tokens": 0,
                    "recommendation": f"unreadable ({exc}) — cannot verify divergence"}

        line_count = installed_raw.count("\n") + (0 if installed_raw.endswith("\n") else 1)
        base = {"path": str(dst), "kind": kind,
                "line_count": line_count, "approx_tokens": line_count * 13}

        if not src.is_file():
            # Missing shipped reference = a broken/partial install — an
            # explicit unverifiable row, never a silent skip that would let
            # the caller's all-clear line print over it.
            return {**base, "classification": "UNVERIFIABLE",
                    "recommendation": "shipped reference unavailable — cannot verify divergence"}
        try:
            shipped_raw = src.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            return {**base, "classification": "UNVERIFIABLE",
                    "recommendation": f"shipped reference unreadable ({exc}) — cannot verify divergence"}

        inst_norm, ship_norm = norm(installed_raw), norm(shipped_raw)
        if inst_norm == ship_norm:
            return None

        v = _classify_diverged(inst_norm, ship_norm)
        notes = getattr(v, "notes", "") or ""

        if _verdict_not_analyzed(v):
            # Degraded stand-in (structural_compare unavailable at call
            # time) — no analysis actually ran. Must NOT be reported as a
            # confident HAS_UNIQUE recommendation; mirrors the migrate/
            # upgrade NOT-analyzed notice convention.
            return {**base, "classification": "NOT_ANALYZED",
                    "recommendation": "NOT analyzed — structural comparison unavailable; "
                                       "diff it against references/ before acting manually"}

        if is_subset(v):
            if notes:
                # Non-empty notes = the matcher tolerated installed-only
                # content (e.g. sub-noise-floor fragments) — the writer's
                # own auto-adopt gate (`is_subset(verdict) and not
                # verdict.notes`) does NOT fire here; /planwise upgrade
                # instead routes this file through the customization-bearing
                # transfer-then-adopt (or preserve) gate, never an
                # unconditional auto-adopt.
                recommendation = (
                    "recommend /planwise upgrade — installed-only content flagged "
                    f"({notes}); upgrade will transfer it (or preserve it in place, "
                    "depending on upgrade.customization_handoff) before adopting "
                    "shipped, not auto-adopt unconditionally"
                )
            else:
                recommendation = "recommend /planwise upgrade (auto-adopts shipped)"
            return {**base, "classification": "SUBSET", "recommendation": recommendation}

        # HAS_UNIQUE — re-home per the rule decide-callout.
        recommendation = 're-home per the "Choosing a Home for a Rule Customization" decide callout'
        return {**base, "classification": "HAS_UNIQUE", "recommendation": recommendation}

    findings: list[dict] = []
    for filename, _paths_template in INSTALLED_RULES:
        row = _check(rules_dst_dir / filename, refs_dir / filename, "rule", normalize_rule_for_diff)
        if row:
            findings.append(row)
    return findings


