#!/usr/bin/env python3
"""The single writer call of the upgrade card: verdicts in, writer run, summary and offers out.

CLI: python -B upgrade_run.py --project-root P --pair FROM-to-TO [--token-saver] [--allow-downgrade]
     [--verdicts-stdin | --verdicts-file PATH] [--answers-json] [--user-settings PATH] [--no-calibrate]
     [--dry-argv]

Exit codes: 0 done, 1 the writer or a staging step failed, 2 a guard refused. A refusal happens before
stdin is staged and before any write. The writer runs in-process with the real environment.
"""

import argparse
import contextlib
import io
import json
import os
import re
import shlex
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import upgrade_preflight as pre
from upgrade_preflight import _mapping

PAIR_RE = re.compile(r"[0-9]+(\.[0-9]+)*-to-[0-9]+(\.[0-9]+)*")
SHA_RE = re.compile(r"[0-9a-f]{64}")
PRUNE_CLASSES = ("safe-to-discard", "inert")
PASS_THROUGH = ("Orphaned", "Backlog index migration", "Backlog changelog",
                "Lessons index migration", "Lessons changelog", "Plans index migration", "Plans changelog",
                "Style rule", "Plans anomal", "Lessons finding", "Lessons anomal",
                "Token Saver recalibrated", "Token Saver calibration")
LAST_ARGV: list = []  # the writer argv of the latest call; tests read it


def is_inside(child, parent, strict: bool = False) -> bool:
    """True when child resolves to parent or below it (strict: below it only)."""
    kid, top = (Path(os.path.normcase(os.path.realpath(p))) for p in (child, parent))
    return top in kid.parents or (not strict and top == kid)


def same_path(a, b) -> bool:
    """True when both paths resolve to one file (or, for a file not yet on disk, to one location)."""
    if os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b)):
        return True
    try:
        return Path(a).exists() and Path(b).exists() and os.path.samefile(a, b)
    except OSError:
        return False


SETTINGS_NAMES = ("settings.json", "settings.local.json")


def user_settings_refusal(user_settings) -> str:
    """The refusal line when the user-settings path is not a settings file in a .claude folder, else ''.

    The rule reads the resolved path: its name is settings.json or settings.local.json, and its parent
    folder is named .claude. It does not depend on where the path came from.
    """
    real = Path(os.path.realpath(user_settings))
    if os.path.normcase(real.name) in SETTINGS_NAMES and os.path.normcase(real.parent.name) == ".claude":
        return ""
    return (f"UPGRADE REFUSED: user settings target {Path(user_settings).as_posix()} is not a "
            "settings.json or settings.local.json file in a .claude folder")


def settings_targets(project_root: Path, user_settings: Path) -> list[Path]:
    """The only settings files a confirmed offer may write: the project's two, and the user file when it passes."""
    claude = Path(project_root) / ".claude"
    targets = [claude / name for name in SETTINGS_NAMES]
    return targets + ([Path(user_settings)] if not user_settings_refusal(user_settings) else [])


def settings_target_refusal(path: Path, project_root: Path, user_settings: Path) -> str:
    """The refusal line when a settings write to `path` is not allowed, else ''.

    Allowed: the project's .claude/settings.json, its .claude/settings.local.json, and the user-settings path
    the card resolved (the --user-settings flag, else the home settings file) when user_settings_refusal
    passes it.
    """
    if any(same_path(path, target) for target in settings_targets(project_root, user_settings)):
        return ""
    if same_path(path, user_settings):
        return user_settings_refusal(user_settings)
    return f"UPGRADE REFUSED: settings target {Path(path).as_posix()} is not an allowed settings file"


def prunable_leftovers(cfg, pair: str, classes) -> list[dict]:
    """The leftover-sweep findings of `classes` that a prune may delete, without this run's own pre-images.

    The pre-images this run wrote under upgrade-backups/{pair}/ are its recovery copy, so they are never
    offered or pruned, the same way --transfer-delete refuses this run's pair. The offer and the apply both
    use this one list, read from the sweep the prune writer itself reads.
    """
    import doctor_sweeps

    own = str(pair or "").lower()
    return [f for f in doctor_sweeps.sweep_upgrade_leftovers(cfg) if f["klass"] in classes
            and not (f["klass"] == "safe-to-discard" and str(f["pair"]).lower() == own)]


def transfer_check(cfg, path) -> tuple[str, bytes, str]:
    """(reason, raw bytes, source): reason is '' when the transfer body equals its shipped rule after normalize_pair.

    The offer and the delete both use this one check, so an offered delete is one the apply step will perform.
    """
    import rule_divergence
    import transfer_review

    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        return f"unreadable ({exc})", b"", ""
    text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    parsed = transfer_review.split_transfer(text)
    if parsed is None:
        return "unparseable transfer file", raw, ""
    header, body = parsed
    source = str(header.get("source_filename") or Path(path).name)
    try:
        shipped = (cfg.plugin_root / "references" / source).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return f"the shipped {source} is unreadable ({exc})", raw, source
    left, right = rule_divergence.normalize_pair(body, shipped)
    return ("" if left == right else f"body differs from the shipped {source}"), raw, source


def root_refusal(project_root: Path, root: str) -> str:
    """The refusal line when planwise_root resolves outside the project root, else ''."""
    if not is_inside(project_root / root, project_root):
        return f"UPGRADE REFUSED: planwise_root {root} resolves outside {project_root.as_posix()}"
    return ""


def applied_pair_refusal(project_root: Path, config: dict, pair: str) -> str:
    """For upgrade_apply: the pair must end at the pin this run wrote, and stay under upgrade-conflicts/."""
    if not PAIR_RE.fullmatch(pair):
        return f"UPGRADE REFUSED: pair {pair} does not match FROM-to-TO"
    pinned = str(config.get("plugin_version") or "")
    if pair.split("-to-")[1] != pinned:
        return f"UPGRADE REFUSED: pair {pair} does not end at the pinned version {pinned or '(none)'}"
    return _contained(project_root, config, pair)


def _contained(project_root: Path, config: dict, pair: str) -> str:
    root = str(_mapping(config.get("project")).get("planwise_root") or "planwise")
    base = (project_root / root / "upgrade-conflicts").resolve()
    if base not in (base / pair).resolve().parents:
        return f"UPGRADE REFUSED: pair {pair} resolves outside {base.as_posix()}"
    return ""


def pair_refusal(project_root: Path, config: dict, pair: str) -> str:
    """The refusal line when the pair fails a test, else ''. Reads only."""
    import config_gen

    if not PAIR_RE.fullmatch(pair):
        return f"UPGRADE REFUSED: pair {pair} does not match FROM-to-TO"
    from_version, to_version = pair.split("-to-")
    pinned = str(config.get("plugin_version") or "")
    if from_version != pinned:
        return f"UPGRADE REFUSED: pair {pair} starts at {from_version}, but config.yaml pins {pinned or '(none)'}"
    shipped = config_gen.read_plugin_version(SCRIPTS.parent)
    if to_version != shipped:
        return f"UPGRADE REFUSED: pair {pair} ends at {to_version}, but the plugin is {shipped}"
    return _contained(project_root, config, pair)


def parse_stdin(text: str, with_answers: bool) -> tuple[list, dict, str]:
    """(entries, answers, error). The error is '' when the document has a usable shape."""
    if not text.strip():
        return [], {}, "the document is empty"
    try:
        doc = json.loads(text)
    except ValueError as exc:
        return [], {}, f"the document is not JSON ({exc})"
    answers: dict = {}
    if with_answers:
        if not isinstance(doc, dict):
            return [], {}, "--answers-json expects an object with verdicts and answers"
        answers = doc.get("answers") or {}
        if not isinstance(answers, dict):
            return [], {}, "answers must be an object"
        doc = doc.get("verdicts") or []
    if isinstance(doc, dict):
        doc = [dict(v, filename=v.get("filename", k)) if isinstance(v, dict) else v for k, v in doc.items()]
    if not isinstance(doc, list):
        return [], {}, "verdicts must be an array of entries or a filename-keyed object"
    return doc, answers, ""


def screen_entries(entries: list) -> tuple[dict, list]:
    """(filename-keyed accepted entries, rejection lines). Every accepted entry carries a source."""
    accepted, lines = {}, []
    for i, entry in enumerate(entries):
        name = entry.get("filename") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name:
            lines.append(f"verdicts: rejected entry {i}: no filename")
        elif not SHA_RE.fullmatch(str(entry.get("installed_sha256", ""))):
            lines.append(f"verdicts: rejected {name}: installed_sha256 is not 64 lowercase hex")
        else:
            accepted[name] = {**entry, "source": entry.get("source", "agent")}
    return accepted, lines


def writer_argv(args, config: dict, project_root: Path, pair: str, answers_path) -> list:
    project = _mapping(config.get("project"))
    argv = ["--project-root", str(project_root), "--name", str(project.get("name") or project_root.name),
            "--root", str(project.get("planwise_root") or "planwise"),
            "--plans-dir", str(project.get("plans_dir") or "Plans"),
            "--backlog-dir", str(project.get("backlog_dir") or "Backlog"),
            "--lessons-dir", str(project.get("lessons_dir") or "LessonsLearned"),
            "--scope", str(project.get("install_scope") or "project"),
            "--upgrade", "--upgrade-pair", pair]
    if args.token_saver:
        argv.append("--token-saver")
    if args.no_calibrate:
        argv.append("--no-calibrate")
    if args.allow_downgrade:
        argv.append("--allow-downgrade")
    if answers_path is not None:
        argv += ["--migration-answers", str(answers_path)]
    return argv


class Tee(io.TextIOBase):
    """Pass writes through to the stream live and keep a copy."""

    def __init__(self, stream):
        self.stream, self.parts = stream, []

    def write(self, text):
        self.parts.append(text)
        return self.stream.write(text)

    def flush(self):
        self.stream.flush()

    @property
    def text(self) -> str:
        return "".join(self.parts)


def run_writer(argv: list) -> tuple[int, str, str]:
    """init_project.main() in-process under a patched argv: (exit code, stdout, stderr)."""
    import init_project

    out, err = Tee(sys.stdout), io.StringIO()
    saved, code = sys.argv, 0
    sys.argv = ["init_project.py", *argv]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            init_project.main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    finally:
        sys.argv = saved
    return code, out.text, err.getvalue()


def flatten(node, prefix: str = "") -> dict:
    if isinstance(node, dict) and node:
        flat = {}
        for key, value in node.items():
            flat.update(flatten(value, f"{prefix}.{key}" if prefix else str(key)))
        return flat
    return {prefix: node}


def show(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)


def config_changes(before: str, after: str) -> list[tuple[str, str, str]]:
    """(key, old, new) per added key or changed scalar; old is '(absent)' for an added key."""
    import yaml

    old, new = flatten(yaml.safe_load(before) or {}), flatten(yaml.safe_load(after) or {})
    return [(k, show(old[k]) if k in old else "(absent)", show(v)) for k, v in new.items()
            if k not in old or show(old[k]) != show(v)]


def banner_entries(text: str) -> list[list[str]]:
    """The writer's stdout as entries: a column-0 line plus the indented lines that follow it."""
    entries: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip():
            entries.append([])
        elif line[0].isspace() and entries and entries[-1]:
            entries[-1].append(line)
        else:
            entries.append([line])
    return [e for e in entries if e]


def count_line(label: str, text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    return f"{label}{match.group(1) if match else '(none)'}"


def print_summary(out: str, pair: str, added: list) -> None:
    print("CHAT SUMMARY")
    print(f"Plugin upgrade: {pair.replace('-to-', ' -> ')}")
    print()
    print(f"Config keys added:        {len(added) or '(none)'}" + (f" ({', '.join(k for k, _o, _n in added)})" if added else ""))
    print(count_line("Rules refreshed:          ", out, r"^Refreshed: (\d+)"))
    print(count_line("Stale subsets adopted:    ", out, r"\((\d+) were stale subsets"))
    print(count_line("Customizations moved:     ", out, r"^Customizations transferred before adoption: (\d+)"))
    print(count_line("Conflicts preserved:      ", out, r"^(?:Preserved|Conflicts?)[^:\n]*: (\d+)"))
    recovery = re.search(r"^Recovery artifacts:\n((?:[ ]+.*\n?)*)", out, re.MULTILINE)
    surfaces = [ln for ln in (recovery.group(1).splitlines() if recovery else []) if "—" in ln and "(" in ln]
    print(f"Recovery surfaces:        {len(surfaces) or '(none)'}")
    for entry in banner_entries(out):
        if entry[0].startswith(PASS_THROUGH) or "anomal" in entry[0].lower():
            print("\n".join(entry))


def build_offers(project_root: Path, config_path: Path, pair: str, user_settings_flag, out: str) -> list[dict]:
    """The pending offers. An offer whose `apply` is None is listed but left out of the Accept-all line."""
    import transfer_review

    config = pre.resolve_config(project_root)[1]
    cfg = pre.build_cfg(config, project_root)
    user_settings = pre.resolve_user_settings(user_settings_flag)[0]
    found = pre.offers(cfg, user_settings)
    offers = []
    leftovers = prunable_leftovers(cfg, pair, PRUNE_CLASSES)
    for klass in PRUNE_CLASSES:
        rows = [f for f in leftovers if f["klass"] == klass]
        if rows:
            pairs = ", ".join(sorted({str(f["pair"]) for f in rows}))
            offers.append({"id": f"prune:{klass}", "default": "skip", "apply": ["--prune", klass],
                           "text": f"{sum(f['count'] for f in rows)} file(s) in {pairs}"})
    project_scope = cfg.install_scope == "project"
    if project_scope and found["grants"]:
        offers.append({"id": "grants:normalize", "default": "skip", "apply": ["--grants", "normalize"],
                       "text": f"{len(found['grants'])} version-pinned plugin-cache grant(s)"})
    if any(v != "ok" for v in found["thrifty"].values()):
        text = f"project {found['thrifty']['project']}, user {found['thrifty']['user']}"
        refusal = next((r for r in (settings_target_refusal(p, project_root, user_settings)
                                    for p in (project_root / ".claude" / "settings.json", user_settings)) if r), "")
        if refusal:  # upgrade_apply would refuse the whole batch, so the offer is not applicable
            offers.append({"id": "thrifty-sonic:add", "default": "skip", "apply": None,
                           "text": f"{text}; not applicable ({refusal})"})
        else:
            offers.append({"id": "thrifty-sonic:add", "default": "add", "apply": ["--thrifty-sonic", "add"],
                           "text": text})
    if project_scope and found["task_tools"] == "absent":
        offers.append({"id": "task-tools:add", "default": "skip", "apply": ["--task-tools", "add"],
                       "text": "CLAUDE_CODE_ENABLE_TODO_TOOLS is not set"})
    for row in transfer_review.review_transfers(cfg, exclude_pair=pair):
        if row["status"] == "now-upstream" and not transfer_check(cfg, row["path"])[0]:
            offers.append({"id": f"transfer-delete:{row['path']}", "default": "skip",
                           "apply": ["--transfer-delete", Path(row["path"]).as_posix()], "text": f"{row['pair']}/{row['filename']}"})
    if "REMOVABLE" in out:
        offers.append({"id": "prune-stale", "default": "skip", "apply": ["--prune-stale"],
                       "text": "the mirror sweep printed a REMOVABLE row"})
    offers += flip_offers(config, config_path)
    return offers


def flip_offers(config: dict, config_path: Path) -> list[dict]:
    """One flip-status offer per unknown Status the flip writer can rewrite.

    Each offer passes the writer's own checks first (flip_plan_status.plan_path_refusal and
    status_value_refusal), so an accepted offer is one the apply step will perform.
    """
    import flip_plan_status

    statuses = [str(s) for s in config.get("plan_statuses") or []]
    plans_dir = config.get("_plans_dir")
    report = pre._json_call([], "generate_plans_index.py", "--config", str(config_path), "--check", "--json")
    offers = []
    for item in (report or {}).get("anomalies") or []:
        if not isinstance(item, dict) or not item.get("file") or plans_dir is None:
            continue
        directory = Path(str(item["file"])).parent.as_posix() + "/"
        guess = str(item.get("status") or "").upper().replace("-", "_").strip("*_")
        if (guess in statuses and flip_plan_status.plan_path_refusal(Path(plans_dir), directory) is None
                and flip_plan_status.status_value_refusal(str(item.get("raw") or "")) is None):
            offers.append({"id": f"flip-status:{directory}={guess}", "default": "skip",
                           "apply": ["--flip-status", f"{directory}={guess}"], "text": str(item.get("message", ""))})
    return offers


def print_offers(offers: list, project_root: Path, pair: str, user_settings_flag=None) -> None:
    if not offers:
        print("OFFERS: none")
        return
    print("OFFERS")
    for number, offer in enumerate(offers, 1):
        print(f"{number}. {offer['id']} — {offer['text']} (default: {offer['default']})")
    applicable = [o for o in offers if o["apply"]]
    if not applicable:
        print("Accept all: (nothing applicable)")
        return
    argv = ["python", "-B", (SCRIPTS / "upgrade_apply.py").as_posix(), "--project-root", project_root.as_posix()]
    if user_settings_flag:  # apply must resolve the same user-settings file the offers were built against
        argv += ["--user-settings", Path(user_settings_flag).as_posix()]
    classes = [o["apply"][1] for o in applicable if o["apply"][0] == "--prune"]
    if classes:
        argv += ["--prune", ",".join(classes)]
    for offer in applicable:
        if offer["apply"][0] != "--prune":
            argv += offer["apply"]
    if any(o["id"].startswith("transfer-delete:") or o["id"] == "prune:safe-to-discard" for o in applicable):
        argv += ["--pair", pair]  # both exclude this run's own pair
    print("Accept all: " + " ".join(shlex.quote(a) for a in argv))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the planwise upgrade writer once, from the upgrade card")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--pair", required=True)
    parser.add_argument("--token-saver", action="store_true")
    parser.add_argument("--allow-downgrade", action="store_true")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--verdicts-stdin", action="store_true", help="read the verdicts document from stdin")
    source.add_argument("--verdicts-file", default=None, metavar="PATH",
                        help="read the same document from a file (when a heredoc is refused)")
    parser.add_argument("--answers-json", action="store_true",
                        help='the document is {"verdicts": [...], "answers": {...}}')
    parser.add_argument("--user-settings", default=None)
    parser.add_argument("--no-calibrate", action="store_true",
                        help="pass --no-calibrate to the writer: skip the Token Saver recalibration")
    parser.add_argument("--dry-argv", action="store_true", help="write the staged files, print the writer argv, stop")
    return parser


def read_document(args) -> tuple[str, str, str]:
    """(source label, text, error) for the verdicts document: the file, stdin, or nothing."""
    if args.verdicts_file:
        try:
            return "--verdicts-file", Path(args.verdicts_file).read_text(encoding="utf-8-sig"), ""
        except (OSError, UnicodeDecodeError) as exc:
            return "--verdicts-file", "", f"cannot read {args.verdicts_file} ({exc})"
    if args.verdicts_stdin or args.answers_json:
        return "--verdicts-stdin", sys.stdin.read(), ""
    return "", "", ""


def read_stdin(args) -> tuple[dict, dict, str]:
    """(accepted verdicts, answers, error) from stdin or --verdicts-file. Reads only; prints each rejected entry."""
    label, text, error = read_document(args)
    if not label:
        return {}, {}, ""
    if not error:
        entries, answers, error = parse_stdin(text, args.answers_json)
    if error:
        return {}, {}, f"error: {label}: {error}"
    accepted, rejected = screen_entries(entries)
    for line in rejected:
        print(line)
    return accepted, answers, ""


def stale_refusal(conflicts: Path, accepted: dict, answers: dict) -> str:
    """The refusal line when a staged input exists that this call will not write, else ''. Reads only.

    The writer reads verdicts.json and migration-answers.json from the pair folder. A file left by an earlier call
    (a dry run, or a failed writer) must never reach this call's writer, so the call stops before any write.
    """
    stale = [conflicts / name for name, mine in (("verdicts.json", accepted), ("migration-answers.json", answers))
             if not mine and (conflicts / name).is_file()]
    if stale:
        names = ", ".join(p.as_posix() for p in stale)
        return f"UPGRADE REFUSED: stale staged input {names} (this call does not write it; remove it or pass it on stdin)"
    return ""


def stage_inputs(conflicts: Path, accepted: dict, answers: dict) -> str:
    """Write verdicts.json and migration-answers.json for this call. Returns '' or an error line."""
    try:
        if accepted or answers:
            conflicts.mkdir(parents=True, exist_ok=True)
        if accepted:
            (conflicts / "verdicts.json").write_text(json.dumps(accepted, indent=2, ensure_ascii=False) + "\n",
                                                     encoding="utf-8")
            print(f"verdicts: wrote {len(accepted)} entr{'y' if len(accepted) == 1 else 'ies'} to "
                  f"{(conflicts / 'verdicts.json').as_posix()}")
        if answers:
            (conflicts / "migration-answers.json").write_text(
                json.dumps(answers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"answers: wrote {(conflicts / 'migration-answers.json').as_posix()}")
    except OSError as exc:
        return f"error: cannot stage the verdicts inputs under {conflicts.as_posix()}: {exc}"
    return ""


def main(argv=None) -> int:
    global LAST_ARGV
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()
    try:
        config_path, config = pre.resolve_config(project_root)
    except Exception as exc:  # noqa: BLE001 - an unreadable config is a refusal, not a crash
        refusal = f"UPGRADE REFUSED: pair {args.pair} cannot be checked ({exc})"
    else:
        root = str(_mapping(config.get("project")).get("planwise_root") or "planwise")
        refusal = root_refusal(project_root, root) or pair_refusal(project_root, config, args.pair)
    if refusal:
        print(refusal)
        return 2

    root = str(_mapping(config.get("project")).get("planwise_root") or "planwise")
    conflicts = project_root / root / "upgrade-conflicts" / args.pair
    accepted, answers, error = read_stdin(args)
    refusal = error or stale_refusal(conflicts, accepted, answers)
    if refusal:
        print(refusal)
        return 2
    if (args.verdicts_stdin or args.verdicts_file or args.answers_json) and not accepted:
        print("verdicts: none")
    error = stage_inputs(conflicts, accepted, answers)
    if error:
        print(error)
        return 1
    answers_path = conflicts / "migration-answers.json" if answers else None
    LAST_ARGV = writer_argv(args, config, project_root, args.pair, answers_path)
    if args.dry_argv:
        print("writer argv: " + json.dumps(LAST_ARGV))
        return 0

    before = config_path.read_text(encoding="utf-8")  # the CONFIG CHANGES diff compares against this
    code, out, err = run_writer(LAST_ARGV)
    for line in err.splitlines():
        if not line.startswith(("Note:", "Warning:")):
            print(line, file=sys.stderr)
    if code == 2:
        print("UPGRADE REFUSED (writer exit 2) — see the text above")
        return 2

    changes = config_changes(before, config_path.read_text(encoding="utf-8"))
    print("CONFIG CHANGES")
    print("\n".join(f"  {k}: {o} → {n}" for k, o, n in changes) if changes else "  (none)")
    print_summary(out, args.pair, [c for c in changes if c[1] == "(absent)"])
    for line in err.splitlines():
        if line.startswith(("Note:", "Warning:")):
            print(line)
    if code:
        print("OFFERS: none (writer failed)")
        return code
    try:
        offers = build_offers(project_root, config_path, args.pair, args.user_settings, out)
    except Exception as exc:  # noqa: BLE001 - every run ends with an OFFERS line, never a traceback
        print(f"OFFERS: none (the offer scan failed: {type(exc).__name__}: {exc})")
        return 1
    print_offers(offers, project_root, args.pair, args.user_settings)
    return code


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
