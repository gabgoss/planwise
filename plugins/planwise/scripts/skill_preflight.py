#!/usr/bin/env python3
"""Router for the skill's injected shell line.

The skill's `!` line passes one single-quoted value, `'$sub'`. The one-call
fallback passes `list` plus the typed flags as separate argv items. The router
accepts up to three values. A word the user did not type arrives as an empty
string. This script strips each value, drops empty strings and any unexpanded
`$name` placeholder, and treats the first remaining token as the subcommand.

`list` prints the `list_plans` output between two marker comments
(`<!-- planwise:list:begin -->` and `<!-- planwise:list:end -->`). Every input
other than `list`, `upgrade` and `plan` prints nothing (apart from the notices
below), and only `list` imports `list_plans`. Any failure prints one
`PLANWISE_LIST_FALLBACK: <type>: <message>` line. The exit code is always 0.

`upgrade` prints the card from `upgrade_preflight`, which is imported only for
that subcommand. The card runs from `<!-- planwise:upgrade:begin -->` to
`<!-- planwise:upgrade:end -->`. If the preflight raises, the router prints one
`PLANWISE_UPGRADE_FALLBACK: <type>: <message>` line and the end marker.

`plan` prints the plan handler's Config Gate between
`<!-- planwise:plan:begin -->` and `<!-- planwise:plan:end -->`: the
`config.yaml` path, the five fields the gate extracts, and the plans and
lessons directories resolved as `{planwise_root}/{dir_name}`. It finds the
config in the handler's order: `planwise/config.yaml`, then a marked
`*/config.yaml` one level down. A field line prints the value config.yaml
holds, marked ` (default)` when the file does not set it, or
` (missing on disk)` for a stale `plugin_root`. The card then adds the
plan-authoring mode, the effective Token Saver value, the index-shape verdict,
the abbreviations in use, the per-kind FILL inventory and a NEXT block, all
from `plan_preflight`, which is imported only for that subcommand. It imports
neither `list_plans` nor `upgrade_preflight`. When no config is found, or the config
cannot be read or parsed, or anything else fails, the block holds one
`PLANWISE_PLAN_FALLBACK: <type>: <message>` line and the end marker. Extra
words after `plan` are ignored.

`feedback` runs `feedback_post.py card --config <config>` (read-only, local) and
prints its output between `<!-- planwise:feedback:begin -->` and
`<!-- planwise:feedback:end -->`, followed by a NEXT block. The NEXT block
branches on the `ARGUMENTS:` line the model reads: `--post <id>`, `--drafts`, or
any other form. When the card lists no queued draft, nothing prints, so the
handler's own route runs. A non-zero card exit, a missing config or any other
failure prints one `PLANWISE_FEEDBACK_FALLBACK: <cause>` line and the end
marker.

For every input, a `planwise: ...` version notice line prints first when the
config pin differs from this plugin. It prints before the BEGIN marker, never
raises and never changes the exit code.

A second `planwise: {n} feedback draft(s) were blocked by the privacy check ...`
line follows it while `feedback_drafts.count_blocked` counts any draft that is
blocked, not dismissed and not posted. It reads the feedback directory of the
same config, prints nothing when that directory is absent, never raises and
never changes the exit code.

CLI: python -B skill_preflight.py <sub> <flag1> <flag2>
"""

import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

PLACEHOLDERS = {"$0", "$1", "$2", "$sub", "$flag1", "$flag2"}
KNOWN_FLAGS = ("--active", "--no-check")
BEGIN = "<!-- planwise:list:begin -->"
END = "<!-- planwise:list:end -->"
UPGRADE_BEGIN = "<!-- planwise:upgrade:begin -->"
UPGRADE_END = "<!-- planwise:upgrade:end -->"
PLAN_BEGIN = "<!-- planwise:plan:begin -->"
PLAN_END = "<!-- planwise:plan:end -->"
PLAN_FALLBACK = "PLANWISE_PLAN_FALLBACK:"
FEEDBACK_BEGIN = "<!-- planwise:feedback:begin -->"
FEEDBACK_END = "<!-- planwise:feedback:end -->"
FEEDBACK_FALLBACK = "PLANWISE_FEEDBACK_FALLBACK:"
BLOCKED_NOTICE = "planwise: {n} feedback draft(s) were blocked by the privacy check — review with /planwise feedback --status"
CARD_HEADER_RE = re.compile(r"^Queued drafts \((\d+)\) in ")
CARD_STATE_PREFIX = "Posting state:"


def normalise(argv: list[str]) -> list[str]:
    """Strip each value and drop empty strings and unexpanded placeholders."""
    tokens = [a.strip() for a in argv]
    return [t for t in tokens if t and t not in PLACEHOLDERS]


def print_version_notice() -> None:
    """Print the version notice line, if any. Never raises and prints nothing on failure."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import version_notice

        config = version_notice.resolve_config(Path.cwd())
        line = version_notice.notice(config, Path(__file__).resolve().parent.parent) if config else ""
        if line:
            sys.stdout.flush()
            sys.stdout.buffer.write((line + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()
    except BaseException:  # noqa: BLE001 - a notice must never block a subcommand
        return


def print_blocked_notice() -> None:
    """Print the blocked-draft notice line while undismissed blocks exist. Never raises and prints nothing on failure."""
    try:
        import contextlib
        import io

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import config_loader
        import version_notice

        path = version_notice.resolve_config(Path.cwd())
        if path is None:
            return
        with contextlib.redirect_stderr(io.StringIO()):  # stderr would merge into the injected text
            config = config_loader.load_config(config_path=path)
        feedback_dir = Path(config["_feedback_dir"])
        if not feedback_dir.is_dir():
            return
        import feedback_drafts

        n = feedback_drafts.count_blocked(feedback_dir)
        if n > 0:
            _write_utf8([BLOCKED_NOTICE.format(n=n)])
    except BaseException:  # noqa: BLE001 - a notice must never block a subcommand
        return


def _write_utf8(lines: list[str]) -> None:
    """Write the lines as UTF-8 bytes, so a non-ASCII path survives a cp1252 stdout."""
    text = "\n".join(lines) + "\n"
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:  # an in-process caller redirected stdout to a text stream
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    buffer.write(text.encode("utf-8"))
    buffer.flush()


def _one_line(exc: BaseException) -> str:
    """The exception text with every run of whitespace, newlines included, as one space."""
    return " ".join(str(exc).split())


def plan_config_path(root: Path, config_loader) -> Path | None:
    """Find config.yaml in the plan handler's order, which differs from `/planwise list`.

    `planwise/config.yaml` wins whenever it is a file, marker or not. Otherwise
    the first marked `*/config.yaml` one level down, in sorted order, skipping
    dot folders. A `config.yaml` at the project root itself is not a candidate.
    """
    preferred = root / "planwise" / "config.yaml"
    if preferred.is_file():
        return preferred
    for child in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        candidate = child / "config.yaml"
        if candidate.is_file() and config_loader._is_planwise_config(candidate):
            return candidate
    return None


def plan_block_lines(root: Path) -> list[str]:
    """Return the eight Config Gate lines, or one parse-error fallback line. Raises when no config is found."""
    return plan_gate(root)[0]


def plan_gate(root: Path) -> tuple[list[str], Path | None, dict | None, str | None]:
    """Return (lines, config path, config, plans_path), loading config.yaml once.

    `lines` are the eight Config Gate lines. Each field line prints the value
    config.yaml holds. A field the file does not set prints its default plus
    ` (default)`. A configured `plugin_root` that does not exist prints the
    configured value plus ` (missing on disk)`. When the file exists but does
    not read as config, `lines` is one fallback line and the other three items
    are None. Raises when no config is found.
    """
    import contextlib
    import io

    import config_loader

    path = plan_config_path(root, config_loader)
    if path is None:
        raise FileNotFoundError("config.yaml not found")
    yaml_error = getattr(getattr(config_loader, "yaml", None), "YAMLError", None)
    unreadable = (UnicodeDecodeError, PermissionError, *((yaml_error,) if yaml_error else ()))
    try:
        with contextlib.redirect_stderr(io.StringIO()):  # stderr would merge into the injected text
            config = config_loader.load_config(config_path=path)
    except unreadable as exc:  # the file exists but does not read as config
        return [f"{PLAN_FALLBACK} {type(exc).__name__}: config.yaml parse error at {path}: {_one_line(exc)}"], None, None, None
    project = config_loader._project_block(config)
    index_files = project.get("index_files")

    def shown(raw, default) -> str:
        return raw if raw else f"{default} (default)"

    def raw_field(key: str) -> str | None:
        return config_loader._nonempty_str(project.get(key))

    pin = config.get("plugin_root")
    if not pin:
        plugin_root = f"{config['_plugin_root']} (default)"
    elif Path(str(pin)).exists():
        plugin_root = str(pin)
    else:
        plugin_root = f"{pin} (missing on disk)"  # load_config silently falls back; the block does not
    planwise_root = raw_field("planwise_root") or path.parent.name
    lessons_dir = raw_field("lessons_dir")
    lessons_index = config_loader._nonempty_str(index_files.get("lessons")) if isinstance(index_files, dict) else None
    plans_path = config_loader.resolve_index_dir(config, "plans", planwise_root, "Plans")
    lessons_path = config_loader.resolve_index_dir(config, "lessons", planwise_root, "") if lessons_dir else "(not set)"
    lines = [
        f"config: {path}",
        f"plugin_root: {plugin_root}",
        f"project.planwise_root: {shown(raw_field('planwise_root'), planwise_root)}",
        f"project.plans_dir: {shown(raw_field('plans_dir'), 'Plans')}",
        f"project.lessons_dir: {lessons_dir or '(not set)'}",
        f"project.index_files.lessons: {shown(lessons_index, config_loader.resolve_index_name(config, 'lessons'))}",
        f"plans_path: {plans_path}",
        f"lessons_path: {lessons_path}",
    ]
    return lines, path, config, plans_path


def feedback_next_lines(count: int, ids: list[str], state: str) -> list[str]:
    """The NEXT block. Every "done" claim names a value the card computed in this run."""
    listed = ", ".join(ids)
    return [
        "NEXT:",
        f"- Done by this block: the card listed {count} queued draft(s) ({listed}), read the posting state ({state}) and printed each queued draft's body above. Do not list, check the state or read a draft again.",
        "- Check the `ARGUMENTS:` line, then take exactly one branch:",
        f"  - `--post <id>`: use that draft's body from the card above. If the id is not one of {listed}, say that no queued draft has that id and stop.",
        f"  - `--drafts` without `--all`: ask the user one question per queued draft, for {count} question(s), naming each draft by id and title from the card above.",
        "  - any other `feedback` form, `--drafts --all` included: ignore this block and follow the feedback handler.",
        "- Do not Read the feedback handler on the `--post` and `--drafts` branches. Do not run `list`. Do not Read a draft file. Do not run `promote`. Do not call `gh`.",
    ]


def feedback_block(root: Path) -> list[str] | None:
    """Return the feedback block lines, or None when the queue is empty and nothing should print."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import config_loader  # lazy: nothing loads for other subcommands

        path = plan_config_path(root, config_loader)
        if path is None:
            raise FileNotFoundError("config.yaml not found")
        proc = subprocess.run(  # fixed argv, no shell; the card is read-only and local
            [sys.executable, "-B", str(Path(__file__).resolve().parent / "feedback_post.py"), "card", "--config", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            detail = _one_line(RuntimeError(proc.stdout or proc.stderr))
            raise RuntimeError(f"feedback_post.py card exited {proc.returncode}: {detail}")
        lines = proc.stdout.splitlines()
        header = CARD_HEADER_RE.match(lines[0]) if lines else None
        if header is None:
            raise ValueError("card output has no 'Queued drafts (N) in' header line")
        count = int(header.group(1))
        if count == 0:
            return None
        ids: list[str] = []
        state = None
        for line in lines[1:]:
            if line.startswith(CARD_STATE_PREFIX):
                state = line[len(CARD_STATE_PREFIX):].strip()
                break
            ids.append(line.split("\t", 1)[0])
        if state is None or len(ids) != count:
            raise ValueError("card output rows do not match its header count or lack the posting state line")
        return [FEEDBACK_BEGIN, *lines, "", *feedback_next_lines(count, ids, state), FEEDBACK_END]
    except Exception as exc:  # noqa: BLE001 - contract: one fallback line, exit 0
        return [FEEDBACK_BEGIN, f"{FEEDBACK_FALLBACK} {type(exc).__name__}: {_one_line(exc)}", FEEDBACK_END]


def run(argv: list[str]) -> int | None:
    print_version_notice()
    print_blocked_notice()
    tokens = normalise(argv)
    if tokens and tokens[0] == "upgrade":
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import upgrade_preflight  # lazy: nothing loads for other subcommands

            return upgrade_preflight.run(tokens)
        except Exception as exc:  # noqa: BLE001 - contract: one fallback line, exit 0
            print(f"PLANWISE_UPGRADE_FALLBACK: {type(exc).__name__}: {exc}")
            print(UPGRADE_END)
            return 0
    if tokens and tokens[0] == "plan":
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            lines, path, config, plans_path = plan_gate(Path.cwd())  # lazy imports: nothing loads for other subcommands
        except Exception as exc:  # noqa: BLE001 - contract: one fallback line, exit 0
            lines, config = [f"{PLAN_FALLBACK} {type(exc).__name__}: {_one_line(exc)}"], None
        if config is not None:
            try:
                import plan_preflight  # lazy: loads for `plan` only, and only after the gate read the config

                lines = [*lines, *plan_preflight.card_lines(path, config, plans_path)]
            except Exception as exc:  # noqa: BLE001 - the eight gate lines survive a card failure
                lines = [*lines, f"plan_card: (unavailable: {type(exc).__name__})"]
        _write_utf8([PLAN_BEGIN, *lines, PLAN_END])
        return 0
    if tokens and tokens[0] == "feedback":
        block = feedback_block(Path.cwd())
        if block is not None:
            _write_utf8(block)
        return 0
    if not tokens or tokens[0] != "list":
        return
    flags = [t for t in tokens[1:] if t in KNOWN_FLAGS]
    print(BEGIN)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import list_plans

        list_plans.main(flags)
        print(END)
    except Exception as exc:  # noqa: BLE001 - contract: one fallback line, exit 0
        print(f"PLANWISE_LIST_FALLBACK: {type(exc).__name__}: {exc}")
        print(END)


def main(argv: list[str] | None = None) -> int:
    try:
        run(sys.argv[1:] if argv is None else argv)
    except Exception as exc:  # noqa: BLE001
        print(f"PLANWISE_LIST_FALLBACK: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
