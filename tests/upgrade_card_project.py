"""Whole planwise projects for the upgrade-card scripts, built from this repo's own plugin tree.

Not a test module (pytest does not collect this name) and not a conftest. Each builder runs the plugin's
own `init_project` in-process for a fresh project, reshapes it for one branch of the card, and returns
the project root. No builder patches anything. The calling test owns its patches, and `isolate` applies
them: `config_gen.probe_cli_version` returns "" so the writer never starts `claude --version`, and no
child process can resolve or start `claude`. The conftest's `_isolated_home` already points `Path.home`
at a temp folder, which `init_project` writes `.claude/settings.json` under.

The planted rule divergences come from `DIVERGENCES`. Each row transforms the text `init_project`
installed at build time, never a stored rule body, so an edit to a shipped reference moves both sides
together and the expected verdict stays known.
"""
import contextlib
import hashlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "planwise" / "scripts"
for _path in (str(SCRIPTS), str(TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import config_gen
import init_project
from test_upgrade_migration_e2e import FROM, build_backlog

PLUGIN_ROOT = SCRIPTS.parent
TO = config_gen.read_plugin_version(PLUGIN_ROOT)  # measured live, never hard-coded
PAIR = f"{FROM}-to-{TO}"
RULES = Path(".claude") / "rules" / "planwise"
THRIFTY, TODO = "CLAUDE_CODE_THRIFTY_SONIC", "CLAUDE_CODE_ENABLE_TODO_TOOLS"
LOCAL_BLOCK = ("\n## Local addition\n\nThe quick brown fox jumps over the lazy dog every single morning.\n"
               "A second wholly unique paragraph that the shipped rule never says anywhere at all.\n")


def drop_last_section(text: str) -> str:
    """The installed text without its last `## ` section: every line left is a shipped line."""
    return text[:text.rindex("\n## ") + 1]


def append_block(text: str) -> str:
    """The installed text plus a block the shipped rule never says."""
    return text.rstrip("\n") + "\n" + LOCAL_BLOCK


# (installed rule, transform, the card's inline verdict, the card's agent column)
DIVERGENCES = (
    ("agent-authoring.md", drop_last_section, "SUBSET/exact", "no"),
    ("skill-authoring.md", append_block, "HAS_UNIQUE/unique", "yes"),
)


def newer_version(version: str) -> str:
    """A version one step above `version` in its last component."""
    parts = version.split(".")
    return ".".join(parts[:-1] + [str(int(parts[-1]) + 1)])


def older_version(version: str) -> str:
    """A version one step below `version` in its last component."""
    parts = version.split(".")
    return ".".join(parts[:-1] + [str(int(parts[-1]) - 1)])


EARLIER_PAIR = f"{older_version(FROM)}-to-{FROM}"  # an upgrade before this one, for transfer files


def isolate(monkeypatch) -> None:
    """The patches a test that uses these builders owns. Call it after `_isolated_home` has run."""
    monkeypatch.setattr(config_gen, "probe_cli_version", lambda timeout=5.0: "")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent))  # a child process cannot resolve `claude`
    wrapped = subprocess.run

    def no_claude(*popenargs, **kwargs):
        args = popenargs[0] if popenargs else kwargs.get("args")
        first = args.split()[0] if isinstance(args, str) and args.split() else (
            args[0] if isinstance(args, (list, tuple)) and args else args)
        if Path(str(first)).stem.lower() == "claude":
            raise RuntimeError(f"test tried to spawn claude: {args!r}")
        return wrapped(*popenargs, **kwargs)

    monkeypatch.setattr(subprocess, "run", no_claude)


def config_path(root: Path) -> Path:
    return root / "planwise" / "config.yaml"


def settings_path(root: Path, name: str = "settings.json") -> Path:
    return root / ".claude" / name


def shipped(name: str) -> str:
    return (PLUGIN_ROOT / "references" / name).read_text(encoding="utf-8")


def installed_sha(path: Path) -> str:
    """SHA-256 of the normalized pre-image: BOM stripped, line endings as LF."""
    text = path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_tree(root: Path) -> dict:
    """{relative posix path: sha256} for every file under root."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


def run_init(root: Path, *extra: str) -> str:
    """`init_project.main()` in-process for a fresh project at `root`; returns its stdout, raises on a non-zero exit."""
    argv = ["init_project.py", "--project-root", str(root), "--name", root.name, "--root", "planwise",
            "--plans-dir", "Plans", "--backlog-dir", "Backlog", "--lessons-dir", "LessonsLearned",
            "--scope", "project", *extra]
    saved, out, code = sys.argv, io.StringIO(), 0
    sys.argv = argv
    try:
        with contextlib.redirect_stdout(out):
            init_project.main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    finally:
        sys.argv = saved
    if code:
        raise RuntimeError(f"init_project exited {code}: {out.getvalue()[-800:]}")
    return out.getvalue()


def edit_config(root: Path, pattern: str, repl: str) -> None:
    """Rewrite one config line by regex; raises unless the pattern matches exactly once."""
    path = config_path(root)
    text, count = re.subn(pattern, repl, path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"expected one match of {pattern!r} in {path}, found {count}")
    path.write_text(text, encoding="utf-8", newline="")


def set_pin(root: Path, version: str) -> None:
    edit_config(root, r"^plugin_version: .*$", f'plugin_version: "{version}"')


def edit_json(path: Path, change) -> None:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    change(data)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def drop_env_key(path: Path, key: str) -> None:
    edit_json(path, lambda d: d.get("env", {}).pop(key, None))


def seed_transfer(root: Path, pair: str, name: str, body: str, source: str = "agent-authoring.md") -> Path:
    """A transfer file in the shape an earlier upgrade leaves under upgrade-transfers/{pair}/."""
    folder = root / "planwise" / "upgrade-transfers" / pair
    folder.mkdir(parents=True, exist_ok=True)
    head = (f"---\nsource_filename: {source}\nunique_blocks: []\n---\n\n"
            f"# Transferred customization: {source}\n\nPreserved by an earlier upgrade.\n\n---\n\n")
    (folder / name).write_bytes((head + body).encode("utf-8"))
    return folder / name


def seed_backup(root: Path, pair: str, name: str = "earlier.md", body: str = "an earlier pre-image\n") -> Path:
    """A refresh pre-image in the shape an earlier upgrade leaves under upgrade-backups/{pair}/."""
    path = root / "planwise" / "upgrade-backups" / pair / RULES / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode("utf-8"))
    return path


def write_master_plan(root: Path, folder: str, abbrev: str, status: str) -> Path:
    """One Master Plan under the project's Plans folder, with the Status value written as given."""
    path = root / "planwise" / "Plans" / folder / f"{abbrev}-Master-Plan.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((f"# {abbrev} Master Plan\n\n**Status:** {status}\n**Created:** 2026-01-01\n"
                      "**Last Updated:** 2026-01-02\n\nBody.\n").encode())
    return path


def plant(root: Path, diverged) -> None:
    for name, transform, _inline, _agent in diverged:
        path = root / RULES / name
        path.write_bytes(transform(path.read_bytes().decode("utf-8")).encode("utf-8"))


def make_project(tmp: Path, *, name: str = "pre", pinned: str = FROM, token_saver: bool = False,
                 diverged=DIVERGENCES, question: bool = False) -> Path:
    """A pre-upgrade project: a fresh init pinned at `pinned`, with the planted divergences.

    `question=True` replaces the backlog with the end-to-end fixture's hand-authored backlog, whose
    reciprocal `blocks:` edge is the one migration question the preflight asks.
    """
    root = Path(tmp) / name
    root.mkdir(parents=True)
    run_init(root, "--no-calibrate", *(["--token-saver"] if token_saver else []))
    set_pin(root, pinned)
    plant(root, diverged)
    if question:
        build_backlog(root / "planwise")
    return root


def make_up_to_date(tmp: Path, *, name: str = "utd") -> Path:
    """A fresh init at the live version: no divergence, and no pending offer except what gh reports."""
    root = Path(tmp) / name
    root.mkdir(parents=True)
    run_init(root, "--no-calibrate")
    return root


def make_no_config(tmp: Path, *, name: str = "no-config") -> Path:
    """A project folder with a planwise/ directory and no config.yaml anywhere."""
    root = Path(tmp) / name
    (root / "planwise").mkdir(parents=True)
    return root


def make_downgrade(tmp: Path, *, name: str = "downgrade") -> Path:
    """A fresh init pinned one step above the live version."""
    return make_project(tmp, name=name, pinned=newer_version(TO), diverged=())


def upgraded(tmp: Path, *, name: str = "post") -> Path:
    """A pre-upgrade project taken through upgrade_run once, with a SUBSET verdict per planted divergence."""
    import upgrade_run

    root = make_project(tmp, name=name)
    entries = [{"filename": n, "classification": "SUBSET", "confidence": "contained", "unique_blocks": [],
                "tolerated_fragments": [], "rationale": "", "notes": "",
                "installed_sha256": installed_sha(root / RULES / n)} for n, *_rest in DIVERGENCES]
    document = Path(tmp) / f"{name}-verdicts.json"
    document.write_text(json.dumps(entries), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()) as out:
        code = upgrade_run.main(["--project-root", str(root), "--pair", PAIR, "--verdicts-file", str(document),
                                 "--no-calibrate"])
    if code:
        raise RuntimeError(f"upgrade_run exited {code}: {out.getvalue()[-800:]}")
    return root
