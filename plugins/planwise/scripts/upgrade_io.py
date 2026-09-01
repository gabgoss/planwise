"""Shared backup/disposition-log/transfer primitives for the --upgrade flow.

Consumed by both the rule de-scope migration and the artifact refresh, which
call the same three destructive-write-safety primitives (backup pre-image,
disposition log, transfer-then-adopt) — extracted here first so neither of
those two callers has to import the other.
"""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from config_gen import InitConfig  # noqa: F401 -- type-hint only (quoted forward refs)
except ImportError:
    raise ImportError(
        "config_gen is required for upgrade_io's InitConfig type references; "
        "the scripts/ directory appears to be partially installed"
    )

try:
    from rule_divergence import HAS_STRUCTURAL_COMPARE, StructuralVerdict
except ImportError:
    raise ImportError(
        "rule_divergence is required for upgrade_io's verdict-override cache; "
        "the scripts/ directory appears to be partially installed"
    )


def _load_verdicts_cache(cfg: "InitConfig", from_version: str, to_version: str) -> dict:
    """Load the interactive fan-out's verdicts.json cache, if present.

    Path: ``{planwise_root}/upgrade-conflicts/{from}-to-{to}/verdicts.json``. This
    is the ONLY place the cache is read from disk — every ``--upgrade`` writer
    site (the Site-1 de-scope migration and the Sites-2/3 artifact refresh)
    calls this helper once, then looks up its own filename to build an
    override. A missing file, an unreadable file, or malformed (non-dict)
    JSON all degrade to ``{}`` — no ``verdicts.json`` is the headless-complete
    baseline; the writer never requires the cache to run.
    """
    path = (
        cfg.project_root / cfg.planwise_root / "upgrade-conflicts"
        / f"{from_version}-to-{to_version}" / "verdicts.json"
    )
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _installed_hash(source: "Path | str") -> str:
    """Return the sha256 hex digest of an installed file's normalized-text pre-image.

    `source` is either a filesystem `Path` (read here, BOM-stripped via
    `utf-8-sig`) or an already-decoded `str` — a caller that has already read
    the file (e.g. via its own `read_text(encoding="utf-8-sig")`) passes the
    text directly rather than re-reading it. Either way, ALL line endings are
    normalized to `\n` EXPLICITLY before the text is re-encoded `utf-8` and
    hashed — never left to incidental universal-newline behavior, because the
    source tree itself is mixed-ending. This is the ONE pre-image every
    caller in this module hashes against, so the `--hash-installed`
    subcommand and the verdict-override recompute below cannot drift apart
    again.

    The preservation path (`_write_backup_preimage`, via `_copy_bytes_exact`)
    intentionally does the opposite — it copies bytes exactly — and is
    untouched by this helper. (`_transfer_customization` is neither: it writes
    the DECODED installed text under a provenance header, a preservation
    document for re-homing, not a byte pre-image — the backup is the
    pre-image.)
    """
    raw = source.read_text(encoding="utf-8-sig") if isinstance(source, Path) else source
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_verdict_override(
    verdicts: dict, filename: str, installed_raw: str, installed_path: "Path | None" = None
) -> "StructuralVerdict | None":
    """Return a StructuralVerdict built from a verdicts.json cache entry, or None.

    Degrades to None (the conservative inline-primitive path, per
    `_classify_diverged`'s own preserve-on-doubt fallback) whenever: the
    filename has no cache entry, `structural_compare` itself is unavailable
    (`StructuralVerdict` is not importable in degraded mode), the entry is not
    a dict (a string/list/number/null cache value — malformed cache, never
    crash), or `from_dict` raises (`ValueError` when `classification`/
    `confidence` is missing, or `AttributeError` when the entry is dict-shaped
    but a nested field is the wrong type for `.items()`-style access — a
    partial/malformed agent verdict must NEVER crash the `--upgrade` run).

    Freshness-bound: each entry must also carry `installed_sha256` — the
    digest of the installed file's normalized-text pre-image (see the
    shared hash helper above) at the time the comparator analyzed it. It is
    re-hashed against `installed_raw` here via that same helper; a missing or
    mismatched hash means the cached verdict was computed against different
    content than what's on disk NOW (a later edit, a partial rerun, a stale
    carried-over cache) — the override is ignored (one-line stderr note)
    rather than trusted against content it doesn't provably describe.

    When the caller also has `installed_path` (the installed file's location
    on disk) available, a mismatch is additionally checked against the
    file's RAW-BYTE digest (the pre-image an older recipe used before this
    module standardized on normalized text). A raw-byte match means the
    cached digest isn't stale — it was simply computed with the old recipe —
    so the stderr note names that condition and its remedy instead of the
    generic "stale" wording. Both `--upgrade` writer sites pass it, so the
    hint is live on the production path; it stays optional so a caller
    holding only pre-read text can still call this, and the diagnosis then
    degrades to the generic note.

    A well-formed SUBSET verdict may legitimately carry a non-empty `notes`
    field (installed-only sub-noise-floor fragments) — that is not malformed
    and deserializes cleanly.
    """
    if not HAS_STRUCTURAL_COMPARE or filename not in verdicts:
        return None
    entry = verdicts[filename]
    if not isinstance(entry, dict):
        print(
            f"  Warning: verdicts.json entry for {filename} is not an object "
            "— ignoring cached verdict",
            file=sys.stderr,
        )
        return None
    current_hash = _installed_hash(installed_raw)
    cached_hash = entry.get("installed_sha256")
    if not cached_hash or cached_hash != current_hash:
        hint = ""
        if installed_path is not None and cached_hash:
            try:
                raw_byte_hash = hashlib.sha256(installed_path.read_bytes()).hexdigest()
            except OSError:
                raw_byte_hash = None
            if raw_byte_hash == cached_hash:
                hint = (
                    " (this digest was written by the OLD raw-byte hash recipe, not "
                    "the current normalized-text one — re-run the fan-out, or refresh "
                    "it with --hash-installed)"
                )
        print(
            f"  Warning: verdicts.json entry for {filename} has a missing or "
            f"stale installed_sha256 — ignoring cached verdict{hint}",
            file=sys.stderr,
        )
        return None
    try:
        return StructuralVerdict.from_dict(entry)
    except (ValueError, TypeError, AttributeError):
        return None


def _copy_bytes_exact(src: Path, dst: Path) -> None:
    """Copy `src` to `dst` as an exact byte image — the ONE copy primitive
    every pre-image/backup site in the upgrade and prune flows uses.

    Deliberately NOT a text round-trip (`read_text` -> `write_text`): text
    mode applies universal-newline translation on read and the platform's
    native ending on write, so a CRLF file is silently rewritten LF on POSIX
    and an LF file rewritten CRLF on Windows; a leading BOM is dropped by a
    `utf-8-sig` read; and a non-UTF-8 byte raises `UnicodeDecodeError` — a
    ValueError, NOT an OSError, so it escapes a backup site's OSError guard
    and aborts the whole run. A backup that is not the bytes it replaced is
    not a backup.

    This is the opposite of the hash pre-image (`_installed_hash`), which
    normalizes line endings on purpose so a comparator digest stays stable
    across checkouts. The two pipelines have different correct answers and
    must never be unified: normalize-before-hash, preserve-bytes-on-copy.

    Raises OSError on any I/O failure (each caller's failed-backup-blocks-
    destruction contract handles it). `dst`'s parent must already exist.
    """
    dst.write_bytes(src.read_bytes())


def _write_backup_preimage(
    cfg: "InitConfig", from_version: str, to_version: str, dst: Path
) -> bool:
    """Copy dst's CURRENT bytes to upgrade-backups/{from}-to-{to}/, mirroring
    its project-relative path. Call this BEFORE any destructive overwrite or
    removal of `dst`.

    The copy is byte-exact (`_copy_bytes_exact`): line endings, a leading
    BOM, and any non-UTF-8 content survive unchanged, so restoring from the
    backup returns the file that was replaced — never a line-ending-rewritten
    copy of it. No text-mode read or write touches the pre-image path.

    Returns True on success, False on any OSError (a stderr warning is
    printed). Callers MUST treat False as "abort the destructive step; leave
    the file untouched" — the same failed-backup-blocks-destruction contract
    `_run_prune_stale()` already applies to its own removals. Never raises.
    """
    backup_root = (
        cfg.project_root / cfg.planwise_root / "upgrade-backups"
        / f"{from_version}-to-{to_version}"
    )
    try:
        rel = dst.relative_to(cfg.project_root)
    except ValueError:
        rel = Path(dst.name)
    try:
        backup_path = backup_root / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        _copy_bytes_exact(dst, backup_path)
        return True
    except OSError as exc:
        print(
            f"  Warning: could not back up {dst} before a destructive write: {exc}",
            file=sys.stderr,
        )
        return False


def _append_disposition_log(
    cfg: "InitConfig",
    from_version: str,
    to_version: str,
    dst: Path,
    action: str,
    reason: str,
) -> None:
    """Append a DISPOSITIONS.md row recording an ALREADY-COMPLETED destructive
    action.

    Call this ONLY after the destructive write/removal has actually
    succeeded — logging before the fact can produce a false row plus stranded
    state if the write later fails (the interleaving `upgrade_artifacts()`'s
    transfer-then-adopt sites now avoid: transfer, verify, back up, THEN
    write, and only log once that write is confirmed).

    Best-effort: an OSError here is a stderr warning only — the disposition
    itself already happened, so losing the log row (not the file) is the
    worst case. Never raises.
    """
    backup_root = (
        cfg.project_root / cfg.planwise_root / "upgrade-backups"
        / f"{from_version}-to-{to_version}"
    )
    try:
        rel = dst.relative_to(cfg.project_root)
    except ValueError:
        rel = Path(dst.name)
    try:
        log_path = backup_root / "DISPOSITIONS.md"
        header = "" if log_path.exists() else (
            f"# Upgrade dispositions: {from_version} -> {to_version}\n\n"
            "Pre-change copies of every file this upgrade deleted or overwrote\n"
            "live alongside this log, mirroring their project-relative paths.\n\n"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{header}- {date.today().isoformat()} `{rel}` — {action}: {reason}\n")
    except OSError as exc:
        print(
            f"  Warning: could not log disposition for {dst}: {exc}",
            file=sys.stderr,
        )


def _record_disposition(
    cfg: "InitConfig",
    from_version: str,
    to_version: str,
    dst: Path,
    action: str,
    reason: str,
) -> bool:
    """Back up dst's pre-image and append a DISPOSITIONS.md row in one call —
    the convenience wrapper for the SIMPLE destructive sites where the
    caller's own destructive write immediately follows this call with no
    intermediate step that could itself independently fail (e.g. `dst.unlink()`
    right after).

    Returns True iff the backup succeeded; callers MUST skip the destructive
    action when this returns False (same failed-backup-blocks-destruction
    contract as `_write_backup_preimage()`). Sites where the destructive write
    can itself fail AFTER a successful transfer (the transfer-then-adopt
    sites in `upgrade_artifacts()`) call `_write_backup_preimage()` and
    `_append_disposition_log()` directly instead, logging only once the write
    is confirmed to have succeeded.
    """
    ok = _write_backup_preimage(cfg, from_version, to_version, dst)
    if ok:
        _append_disposition_log(cfg, from_version, to_version, dst, action, reason)
    return ok


def _load_raw_config(cfg: "InitConfig") -> dict:
    """Load config.yaml as a plain dict, degrading to {} on any failure.

    Shared by every writer site that needs the `upgrade:` block (the de-scope
    migration's `descope_preserve_paths_edits`, the artifact refresh's
    `customization_handoff`) — tolerant on purpose so a missing/unparsable
    config.yaml degrades to `get_upgrade_config()`'s conservative defaults
    rather than aborting the run.
    """
    if not HAS_YAML:
        return {}
    try:
        loaded = yaml.safe_load(
            (cfg.project_root / cfg.planwise_root / "config.yaml").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError, yaml.YAMLError):
        # ValueError covers UnicodeDecodeError (non-UTF-8 config) — the load
        # is tolerant on purpose; degrade to {} = conservative defaults.
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _transfer_customization(
    cfg: "InitConfig",
    filename: str,
    kind: str,
    installed_raw: str,
    verdict: "StructuralVerdict",
    from_version: str,
    to_version: str,
) -> "Path | None":
    """Move a customization-bearing installed file's content to a dormant
    preservation home BEFORE the writer adopts the shipped body over it.

    Per the automated-transfer-first upgrade policy: a notes-flagged SUBSET
    (installed-only content the matcher tolerated as noise) or a HAS_UNIQUE
    verdict (genuine customization) must never simply be overwritten — the
    customization is written to a separate file, the write is VERIFIED
    (read back and compared), and ONLY THEN may the caller adopt shipped in
    place. Writes the full installed body (the carrier of the customization —
    a granular per-block extract is not available at this layer) to
    ``{planwise_root}/upgrade-transfers/{from}-to-{to}/{filename}`` (beside
    ``upgrade-backups/``), alongside a minimal generic provenance header
    (source filename, kind, upgrade pair, date, verdict summary). The
    transfer file is a dormant preservation document — it lives OUTSIDE
    ``.claude/rules/`` so it is NEVER loaded as a rule and can never collide
    with the managed tree (including on a project literally named
    "planwise"). Promotion into an active ``.claude/rules/<project>/`` rule
    with real ``paths:`` scoping is an interactive, opt-in handler action.
    Never clobbers a pre-existing file at the target (e.g. from a prior
    interrupted run) — collisions are uniquified with a numeric loop
    (``{stem}-{from}-to-{to}``, then ``-2``, ``-3``, ...) until a
    non-existent name is found.

    Returns the transfer file Path on a verified success, or None on ANY
    failure (OSError writing or reading back, or a content mismatch on
    read-back — a filesystem lie is never trusted). The caller MUST treat
    None as "do not adopt/remove; preserve the installed file in place and
    report."
    """
    target_dir = (
        cfg.project_root / cfg.planwise_root / "upgrade-transfers"
        / f"{from_version}-to-{to_version}"
    )
    target = target_dir / filename
    if target.exists():
        stem, suffix = target.stem, target.suffix
        candidate = target_dir / f"{stem}-{from_version}-to-{to_version}{suffix}"
        counter = 2
        while candidate.exists():
            candidate = (
                target_dir / f"{stem}-{from_version}-to-{to_version}-{counter}{suffix}"
            )
            counter += 1
        target = candidate

    unique_blocks = getattr(verdict, "unique_blocks", None) or []
    notes = getattr(verdict, "notes", "") or ""
    header_lines = [
        "---",
        f"source_filename: {filename}",
        f"source_kind: {kind}",
        f"upgrade: {from_version} -> {to_version}",
        f"transferred: {date.today().isoformat()}",
        f"classification: {getattr(verdict, 'classification', 'HAS_UNIQUE')}",
    ]
    if unique_blocks:
        header_lines.append(f"unique_blocks: {unique_blocks!r}")
    if notes:
        header_lines.append(f"notes: {notes!r}")
    header_lines.append("---")
    provenance = (
        "\n".join(header_lines) + "\n\n"
        f"# Transferred customization: {filename}\n\n"
        "This file was auto-transferred from the installed copy before a "
        f"plugin upgrade ({from_version} -> {to_version}) adopted the shipped "
        "body in its place. Review and re-home the content below (port to a "
        "project-local rule, re-scope, or upstream the change), then delete "
        "this file once it is no longer needed.\n\n---\n\n"
    )
    transfer_text = provenance + installed_raw

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(transfer_text, encoding="utf-8")
        if target.read_text(encoding="utf-8") != transfer_text:
            return None
    except OSError:
        return None
    return target

