"""upgrade_apply: prune, the settings offers, the settings-target rule, the interaction matrix and the
transfer-delete guards.

Every project is built by tests/upgrade_card_project.py from this repo's own plugin tree, inside
`tmp_path`, and taken through upgrade_run once with `--no-calibrate`. `_isolate` below patches the
CLI-version probe, so no run starts `claude`.
"""
import hashlib
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import doctor_cli
import doctor_sweeps
import transfer_review
import upgrade_apply
import upgrade_card_project as ucp
import upgrade_run

PAIR, OLD_PAIR = ucp.PAIR, ucp.EARLIER_PAIR
THRIFTY, TODO = ucp.THRIFTY, ucp.TODO
SOURCE = "agent-authoring.md"
FAMILY = ucp.PLUGIN_ROOT.parent.as_posix()  # the plugin-cache family root a grant should name


@pytest.fixture(autouse=True)
def _isolate(_isolated_home, monkeypatch):
    ucp.isolate(monkeypatch)


def apply(capsys, root, *argv):
    capsys.readouterr()
    code = upgrade_apply.main(["--project-root", str(root), *argv])
    return code, capsys.readouterr().out


def settings(root, name="settings.json"):
    return ucp.settings_path(root, name)


def home_settings():
    return Path.home() / ".claude" / "settings.json"


def env_of(path):
    return json.loads(path.read_text(encoding="utf-8-sig")).get("env", {})


def seed_pinned_grant(box, *extra):
    ucp.edit_json(settings(box), lambda d: d.setdefault("permissions", {}).update(
        additionalDirectories=[f"{FAMILY}/{ucp.FROM}", *extra]))


def backups(box):
    return [p.read_bytes() for p in (box / "planwise" / "upgrade-prune-logs").glob("settings-*.bak")]


def row_status(box, path):
    ctx = upgrade_apply.Ctx(box.resolve(), None)
    rows = transfer_review.review_transfers(ctx.cfg, exclude_pair=PAIR)
    return next(r["status"] for r in rows if Path(r["path"]).resolve() == path.resolve())


def test_prune_inert(tmp_path, capsys):
    box = ucp.upgraded(tmp_path)
    kept = sorted(p.relative_to(box).as_posix() for p in (box / "planwise" / "upgrade-backups").rglob("*"))
    assert kept and list(box.glob("planwise/upgrade-conflicts/*/verdicts.json.consumed"))
    code, out = apply(capsys, box, "--prune", "inert")
    assert code == 0, out
    assert not list(box.glob("planwise/upgrade-conflicts/*/verdicts.json.consumed"))
    assert sorted(p.relative_to(box).as_posix() for p in (box / "planwise" / "upgrade-backups").rglob("*")) == kept
    assert list(box.glob("planwise/upgrade-prune-logs/upgrade-leftovers-*/PRUNED-LEFTOVERS.md"))


def test_thrifty_sonic_add_writes_allowed_targets(tmp_path, capsys):
    box = ucp.upgraded(tmp_path)
    ucp.drop_env_key(settings(box), THRIFTY)
    flag = tmp_path / "user" / ".claude" / "settings.json"
    flag.parent.mkdir(parents=True)
    flag.write_bytes(b'{"env": {"KEEP": "1"}}\n')
    home_before = home_settings().read_bytes()
    code, out = apply(capsys, box, "--thrifty-sonic", "add", "--user-settings", str(flag))
    assert code == 0, out
    assert env_of(settings(box))[THRIFTY] == "false"
    assert env_of(flag) == {"KEEP": "1", THRIFTY: "false"}
    assert home_settings().read_bytes() == home_before  # the flag resolved the user file; home is not a target


def test_grants_normalize(tmp_path, capsys):
    box = ucp.upgraded(tmp_path)
    unrelated = "D:/elsewhere/keep"
    seed_pinned_grant(box, unrelated)
    code, out = apply(capsys, box, "--grants", "normalize")
    assert code == 0, out
    grants = json.loads(settings(box).read_text(encoding="utf-8"))["permissions"]["additionalDirectories"]
    norm = [os.path.normcase(os.path.normpath(g)) for g in grants]
    assert norm == [os.path.normcase(os.path.normpath(p)) for p in (unrelated, FAMILY)]


def test_no_flags_prints_nothing_to_apply(tmp_path, capsys):
    code, out = apply(capsys, ucp.upgraded(tmp_path))
    assert code == 0 and out.strip() == "Nothing to apply."


def test_settings_target_rule_refuses_foreign_path(tmp_path, capsys, monkeypatch):
    """A grants finding whose file lies outside the three allowed files stops the whole line before any write.

    The grants sweep itself only names the project's two settings files, so the foreign finding is
    injected at the sweep.
    """
    box = ucp.upgraded(tmp_path)
    ucp.drop_env_key(settings(box), TODO)
    foreign = tmp_path / "foreign" / ".claude" / "settings.json"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b'{"permissions": {"additionalDirectories": []}}\n')
    finding = {"settings_path": foreign, "entry": f"{FAMILY}/{ucp.FROM}", "klass": "version-pinned", "detail": ""}
    monkeypatch.setattr(doctor_cli, "_sweep_settings_grants", lambda cfg: [finding])
    before = (ucp.hash_tree(box), foreign.read_bytes(), home_settings().read_bytes())
    # the earlier flags of the line (prune, task-tools) would each write if the rule ran per write
    code, out = apply(capsys, box, "--prune", "inert", "--task-tools", "add", "--grants", "normalize")
    assert code == 2, out
    assert f"UPGRADE REFUSED: settings target {foreign.as_posix()} is not an allowed settings file" in out
    assert (ucp.hash_tree(box), foreign.read_bytes(), home_settings().read_bytes()) == before
    assert not list(tmp_path.rglob("*.tmp"))
    # the one settings writer re-checks every write
    assert upgrade_apply.write_settings(foreign, {"env": {}}, upgrade_apply.Ctx(box.resolve(), None)) == 2
    assert foreign.read_bytes() == before[1]
    stray = tmp_path / "stray" / "settings.json"
    assert upgrade_apply.write_settings(stray, {"env": {}}, upgrade_apply.Ctx(box.resolve(), None)) == 2
    assert not stray.exists()

    # a planwise_root that leaves the project root is refused before any write
    escaped = ucp.upgraded(tmp_path, name="escaped")
    ucp.edit_config(escaped, r'^  planwise_root: .*$', '  planwise_root: "../outside"')
    before = ucp.hash_tree(escaped)
    code, out = apply(capsys, escaped, "--task-tools", "add")
    assert code == 2 and "planwise_root" in out and ucp.hash_tree(escaped) == before, out


def test_allowed_settings_targets_written(tmp_path, capsys):
    """The project's settings.json, its settings.local.json and the resolved user file are the three targets."""
    box = ucp.upgraded(tmp_path)
    ucp.drop_env_key(settings(box), TODO)
    ucp.drop_env_key(settings(box), THRIFTY)
    flag = tmp_path / "user" / ".claude" / "settings.json"
    flag.parent.mkdir(parents=True)
    flag.write_bytes(b"{}\n")
    code, out = apply(capsys, box, "--task-tools", "add", "--thrifty-sonic", "add", "--user-settings", str(flag))
    assert code == 0, out
    assert env_of(settings(box)) == {**env_of(settings(box)), TODO: "1", THRIFTY: "false"}
    assert env_of(flag) == {THRIFTY: "false"}
    root = box.resolve()
    local = settings(root, "settings.local.json")
    allowed = upgrade_run.settings_targets(root, flag)
    assert [p.name for p in allowed] == ["settings.json", "settings.local.json", "settings.json"]
    assert all(upgrade_run.settings_target_refusal(p, root, flag) == "" for p in allowed)
    assert upgrade_run.settings_target_refusal(home_settings(), root, flag) != ""
    assert upgrade_apply.write_settings(local, {"env": {"LOCAL": "1"}}, upgrade_apply.Ctx(root, str(flag))) == 0
    assert env_of(local) == {"LOCAL": "1"}


def test_apply_interaction_matrix(tmp_path, capsys, monkeypatch):
    cells = {}

    def cell(fn):
        cells[fn.__name__.removeprefix("cell_")] = fn
        return fn

    def new_box(name):
        return ucp.upgraded(tmp_path, name=name)

    def scope_cell(scope):
        box = new_box(f"scope-{scope}")
        ucp.edit_config(box, r'^  install_scope: "project"', f'  install_scope: "{scope}"')
        seed_pinned_grant(box)
        ucp.drop_env_key(settings(box), TODO)
        before = settings(box).read_bytes()
        code, out = apply(capsys, box, "--grants", "normalize", "--task-tools", "add")
        assert code == 0 and out.count(f"scope {scope}: not applied") == 2, out
        assert settings(box).read_bytes() == before

    @cell
    def cell_scope_user():
        scope_cell("user")

    @cell
    def cell_scope_local():
        scope_cell("local")

    @cell
    def cell_unparsable_settings():
        box = new_box("parse")
        settings(box).write_text("{ not json", encoding="utf-8")
        before = ucp.hash_tree(box)
        code, out = apply(capsys, box, "--task-tools", "add", "--thrifty-sonic", "add")
        assert code == 0 and "does not parse" in out and str(settings(box.resolve())) in out, out
        assert ucp.hash_tree(box) == before

    @cell
    def cell_bom_crlf_non_ascii():
        box = new_box("bom")
        data = {"env": {"KEEP": "ü"}, "note": "café ✓"}
        original = b"\xef\xbb\xbf" + json.dumps(data, indent=2, ensure_ascii=False).replace("\n", "\r\n").encode("utf-8")
        settings(box).write_bytes(original)
        code, out = apply(capsys, box, "--task-tools", "add")
        assert code == 0, out
        raw = settings(box).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf") and raw.count(b"\n") == raw.count(b"\r\n")
        assert "café ✓".encode() in raw
        assert json.loads(raw.decode("utf-8-sig"))["env"][TODO] == "1"
        assert backups(box) == [original]

    @cell
    def cell_descope_preserve_edits():
        box = new_box("descope")
        plain, edited = (name for name, _old in doctor_sweeps.DESCOPED_RULES[:2])
        rules = box / ucp.RULES
        (rules / plain).write_text(ucp.shipped(plain), encoding="utf-8", newline="\n")
        (rules / edited).write_text(ucp.shipped(edited) + ucp.LOCAL_BLOCK, encoding="utf-8", newline="\n")
        code, out = apply(capsys, box, "--prune-stale")
        assert code == 0, out
        assert not (rules / plain).exists() and (rules / edited).exists(), out
        # the writer gets the project's whole InitConfig, and a REMOVABLE row that survives fails the run
        again = new_box("descope-rescan")
        (again / ucp.RULES / plain).write_text(ucp.shipped(plain), encoding="utf-8", newline="\n")
        cfgs = []
        with monkeypatch.context() as patch:
            patch.setattr(doctor_cli, "_run_prune_stale", lambda cfg: cfgs.append(cfg) or 0)
            code, out = apply(capsys, again, "--prune-stale")
        assert code == 1 and "REMOVABLE row(s) remain" in out and plain in out, out
        assert [(c.install_scope, c.project_name) for c in cfgs] == [("project", "descope-rescan")], cfgs

    @cell
    def cell_handoff_report():
        box = new_box("handoff")
        ucp.edit_config(box, r"^  customization_handoff: report\+relocate", "  customization_handoff: report")
        target = ucp.seed_transfer(box, OLD_PAIR, "same.md", ucp.shipped(SOURCE))
        code, out = apply(capsys, box, "--transfer-delete", str(target), "--pair", PAIR)
        assert code == 0 and "no transfers under this config" in out and target.is_file(), out

    @cell
    def cell_applied_twice():
        # A fresh project has no plan whose status could flip, so this cell repeats the settings and prune
        # offers; the flip-status writer is covered by the unknown_status cell.
        box = new_box("twice")
        ucp.drop_env_key(settings(box), THRIFTY)
        ucp.drop_env_key(settings(box), TODO)
        flags = ("--prune", "inert", "--thrifty-sonic", "add", "--task-tools", "add")
        first_code, first = apply(capsys, box, *flags)
        assert first_code == 0 and first.count("already applied") == 1, first  # init already set the user file
        after_first = (ucp.hash_tree(box / "planwise"), settings(box).read_bytes(), home_settings().read_bytes())
        code, out = apply(capsys, box, *flags)
        assert code == 0 and out.count("already applied") == 4, out
        assert (ucp.hash_tree(box / "planwise"), settings(box).read_bytes(),
                home_settings().read_bytes()) == after_first

    @cell
    def cell_interrupted_replace():
        box = new_box("interrupt")
        ucp.drop_env_key(settings(box), TODO)
        original = settings(box).read_bytes()

        def boom(*args, **kwargs):
            raise OSError("interrupted")

        with monkeypatch.context() as patch:
            patch.setattr(upgrade_apply.os, "replace", boom)
            code, out = apply(capsys, box, "--task-tools", "add")
        assert code == 1, out
        assert settings(box).read_bytes() == original and not list(box.rglob("*.tmp"))
        assert backups(box) == [original]
        # an unreadable settings file is a named failure, not a traceback
        unreadable = new_box("unreadable")
        ucp.drop_env_key(settings(unreadable), TODO)
        real_read = Path.read_bytes

        def deny(self):
            if self.name == "settings.json":
                raise OSError("denied")
            return real_read(self)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "read_bytes", deny)
            code, out = apply(capsys, unreadable, "--task-tools", "add")
        assert code == 1 and "write failed for" in out and "denied" in out, out

    @cell
    def cell_prune_version_gate_refuses():
        box = new_box("gate")
        ucp.set_pin(box, ucp.FROM)
        consumed = list(box.glob("planwise/upgrade-conflicts/*/verdicts.json.consumed"))
        assert consumed
        code, out = apply(capsys, box, "--prune", "inert")
        assert code == 1 and "remain" in out, out
        assert all(p.is_file() for p in consumed)

    @cell
    def cell_unknown_status():
        box = new_box("status")
        code, out = apply(capsys, box, "--flip-status", "Anything/=BOGUS")
        assert code == 0 and "BOGUS is not in plan_statuses; skipped Anything/" in out and "exit code" not in out, out
        with monkeypatch.context() as patch:  # a helper subprocess that outlives its timeout is a named failure
            patch.setattr(upgrade_apply.pre, "SUBPROCESS_TIMEOUT", 0.001)
            code, out = apply(capsys, box, "--flip-status", "Demo/=CLOSED")
        assert code == 1 and "timed out after" in out, out
        # the index writer exits 1 after a successful write while an anomaly remains: that is not a failed write
        calls = []
        written = json.dumps({"index": "x", "written": True, "anomalies": [{"class": "c", "message": "m"}]})

        def fake(argv, extra_env=None):
            calls.append(Path(argv[2]).name)
            return (0, "changed: 1") if calls[-1] == "flip_plan_status.py" else (1, written)

        with monkeypatch.context() as patch:
            patch.setattr(upgrade_apply.pre, "_run_script", fake)
            code, out = apply(capsys, box, "--flip-status", "Demo/=CLOSED")
        assert code == 0 and "anomalies remain" in out, out
        assert calls == ["flip_plan_status.py", "generate_plans_index.py"]

    @cell
    def cell_foreign_settings_file():
        box = new_box("foreign")
        foreign = tmp_path / "foreign-cell" / "settings.json"
        foreign.parent.mkdir()
        foreign.write_bytes(b'{"env": {"KEEP": "1"}}\n')
        ctx = upgrade_apply.Ctx(box.resolve(), None)
        assert upgrade_apply.write_settings(foreign, {"env": {THRIFTY: "false"}}, ctx) == 2
        assert foreign.read_bytes() == b'{"env": {"KEEP": "1"}}\n'

    failures = []
    for name, fn in cells.items():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - the cell name is the point of the report
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    print("matrix cells:", len(cells), sorted(cells))
    assert len(cells) == 11
    assert not failures, "\n".join(failures)


def test_transfer_delete_guards(tmp_path, capsys, monkeypatch):
    box = ucp.upgraded(tmp_path)
    logs = box / "planwise" / "upgrade-prune-logs"
    body = ucp.shipped(SOURCE)
    same = ucp.seed_transfer(box, OLD_PAIR, "same.md", body)
    lines = body.split("\n")
    subset = ucp.seed_transfer(box, OLD_PAIR, "subset.md", "\n".join(lines[:len(lines) // 2]) + "\n")
    unique = ucp.seed_transfer(box, OLD_PAIR, "unique.md", body + ucp.LOCAL_BLOCK)
    own = ucp.seed_transfer(box, PAIR, "own.md", body)
    original = same.read_bytes()
    assert [row_status(box, p) for p in (same, subset, unique)] == ["now-upstream", "now-upstream", "still-unique"]

    code, out = apply(capsys, box, "--transfer-delete", str(same), "--pair", "9-to-9")  # a pair that is not the pin
    assert code == 2 and same.is_file() and "pinned version" in out, out
    code, out = apply(capsys, box, "--transfer-delete", str(subset), "--pair", PAIR)  # a now-upstream subset
    assert code == 0 and subset.is_file() and "differs" in out, out
    code, out = apply(capsys, box, "--transfer-delete", str(own), "--pair", PAIR)  # this run's own pair
    assert code == 2 and own.is_file(), out
    outside = box / ucp.RULES / "plain-language.md"
    code, out = apply(capsys, box, "--transfer-delete", str(outside), "--pair", PAIR)  # not a transfer file
    assert code == 2 and outside.is_file(), out
    link = same.parent / "link.md"
    try:
        os.symlink(subset, link)
    except (OSError, NotImplementedError):
        link = None
    if link is not None:
        code, out = apply(capsys, box, "--transfer-delete", str(link), "--pair", PAIR)
        assert code == 2 and link.is_symlink() and subset.is_file(), out
    else:  # no privilege to create a link: the guard's check is stood in by a patch
        real_check = Path.is_symlink
        with monkeypatch.context() as patch:
            patch.setattr(Path, "is_symlink", lambda self: self == subset or real_check(self))
            code, out = apply(capsys, box, "--transfer-delete", str(subset), "--pair", PAIR)
        assert code == 2 and "symlink" in out and subset.is_file(), out
    code, out = apply(capsys, box, "--transfer-delete", str(unique), "--pair", PAIR)  # still-unique is kept
    assert code == 0 and unique.is_file() and "still-unique" in out, out
    real_unlink = Path.unlink

    def locked(self, *args, **kwargs):
        if self == same:
            raise OSError("locked")
        return real_unlink(self, *args, **kwargs)

    with monkeypatch.context() as patch:  # the unlink fails: a named error, and no log row for a file still there
        patch.setattr(Path, "unlink", locked)
        code, out = apply(capsys, box, "--transfer-delete", str(same), "--pair", PAIR)
    assert code == 1 and same.is_file() and "could not remove" in out, out
    assert not (logs / "TRANSFER-DELETES.md").exists()

    code, out = apply(capsys, box, "--transfer-delete", str(same), "--pair", PAIR)  # the confirmed delete
    assert code == 0 and not same.exists() and "confirmed" in out, out
    digest = hashlib.sha256(original).hexdigest()
    assert [p.read_bytes() for p in logs.glob("transfer-same.md-*.bak")] == [original]
    log_lines = (logs / "TRANSFER-DELETES.md").read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 1 and digest in log_lines[0]

    crlf = ucp.seed_transfer(box, OLD_PAIR, "crlf.md", body)  # a CRLF transfer file: normalized, then compared
    crlf.write_bytes(crlf.read_bytes().replace(b"\n", b"\r\n"))
    crlf_bytes = crlf.read_bytes()
    code, out = apply(capsys, box, "--transfer-delete", str(crlf), "--pair", PAIR)
    assert code == 0 and not crlf.exists() and "confirmed" in out, out
    assert [p.read_bytes() for p in logs.glob("transfer-crlf.md-*.bak")] == [crlf_bytes]
    assert len((logs / "TRANSFER-DELETES.md").read_text(encoding="utf-8").splitlines()) == 2

    late = ucp.seed_transfer(box, OLD_PAIR, "late.md", body)  # the log append fails after a confirmed delete
    real_open = Path.open

    def no_log(self, *args, **kwargs):
        if self.name == "TRANSFER-DELETES.md":
            raise OSError("log locked")
        return real_open(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", no_log)
        code, out = apply(capsys, box, "--transfer-delete", str(late), "--pair", PAIR)
    assert code == 1 and not late.exists() and "log row could not be written" in out, out
    assert list(logs.glob("transfer-late.md-*.bak"))  # the pre-image survives

    # the shared check reads the shipped rule as utf-8-sig, and an unreadable shipped rule is a reason
    refs = tmp_path / "plugin-with-bom" / "references"
    refs.mkdir(parents=True)
    (refs / SOURCE).write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    bom_cfg = types.SimpleNamespace(plugin_root=refs.parent)
    assert upgrade_run.transfer_check(bom_cfg, ucp.seed_transfer(box, OLD_PAIR, "bom.md", body))[0] == ""
    reason = upgrade_run.transfer_check(bom_cfg, ucp.seed_transfer(box, OLD_PAIR, "gone.md", body, source="no-such.md"))[0]
    assert "unreadable" in reason, reason


def index_check(box):
    return upgrade_apply.pre._json_call([], "generate_plans_index.py", "--config", str(ucp.config_path(box)),
                                        "--check", "--json")


def test_partial_flip_still_rebuilds_the_index(tmp_path, capsys):
    """flip_plan_status exits 1 when one Path is refused, after it rewrote the others: the index follows the rewrite."""
    box = ucp.upgraded(tmp_path)
    ucp.write_master_plan(box, "Alpha", "ALP", "PLANNING")
    code, out = upgrade_apply.run_script(None, [str(upgrade_apply.SCRIPTS / "generate_plans_index.py"),
                                                "--config", str(ucp.config_path(box)), "--write"])
    assert code == 0 and index_check(box)["findings"] == [], out
    code, out = apply(capsys, box, "--flip-status", "Alpha/=COMPLETE", "Nowhere/=COMPLETE")
    assert code == 1, out
    assert "Alpha/: PLANNING -> COMPLETE" in out and "Nowhere/: REFUSED" in out, out
    assert index_check(box)["findings"] == [], out


def test_plans_index_exit_1_is_success_only_when_it_wrote(tmp_path, capsys, monkeypatch):
    """Exit 1 from the index writer is also a traceback or a missing config: only its written signal counts."""
    box = ucp.upgraded(tmp_path)
    calls = []

    def runner(index_result):
        def fake(argv, extra_env=None):
            calls.append(argv)
            return (0, "changed: 1\n") if Path(argv[2]).name == "flip_plan_status.py" else index_result
        return fake

    crashed = (1, "Traceback (most recent call last):\n  File \"x\", line 1\nKeyError: 'plan_statuses'\n")
    monkeypatch.setattr(upgrade_apply.pre, "_run_script", runner(crashed))
    code, out = apply(capsys, box, "--flip-status", "Demo/=CLOSED")
    assert code == 1 and "anomalies remain" not in out, out
    assert "--write" in calls[-1] and "--json" in calls[-1], calls[-1]
    written = (1, json.dumps({"index": "x", "written": True,
                              "anomalies": [{"class": "unknown-status", "message": "m"}]}, indent=2))
    monkeypatch.setattr(upgrade_apply.pre, "_run_script", runner(written))
    code, out = apply(capsys, box, "--flip-status", "Demo/=CLOSED")
    assert code == 0 and "anomalies remain" in out, out


def test_user_settings_target_must_be_a_claude_settings_file(tmp_path, capsys):
    """Only a settings.json or settings.local.json inside a .claude folder is a user-settings target."""
    box = ucp.upgraded(tmp_path)
    ucp.drop_env_key(settings(box), THRIFTY)
    package = box / "package.json"
    package.write_bytes(b'{"name": "demo"}\n')
    stray = tmp_path / "user" / "settings.json"
    stray.parent.mkdir()
    stray.write_bytes(b"{}\n")
    for bad in (package, stray):
        before = (ucp.hash_tree(box), stray.read_bytes())
        code, out = apply(capsys, box, "--thrifty-sonic", "add", "--user-settings", str(bad))
        assert code == 2, out
        refused = [line for line in out.splitlines() if "REFUSED" in line]
        assert len(refused) == 1 and bad.as_posix() in refused[0], out
        assert (ucp.hash_tree(box), stray.read_bytes()) == before
        assert upgrade_run.settings_target_refusal(bad, box.resolve(), bad) != ""
    local = tmp_path / "home-two" / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    code, out = apply(capsys, box, "--thrifty-sonic", "add", "--user-settings", str(local))
    assert code == 0 and env_of(local) == {THRIFTY: "false"}, out
    # the offer the apply would refuse is listed as not applicable
    ucp.drop_env_key(settings(box), THRIFTY)
    offers = upgrade_run.build_offers(box.resolve(), ucp.config_path(box), PAIR, str(package), "")
    thrifty = next(o for o in offers if o["id"] == "thrifty-sonic:add")
    assert thrifty["apply"] is None and "not applicable" in thrifty["text"], thrifty
    assert package.as_posix() in thrifty["text"], thrifty


def test_user_settings_backup_stays_beside_the_user_file(tmp_path, capsys):
    """The user file can hold tokens: its pre-image never lands inside the project tree."""
    box = ucp.upgraded(tmp_path)
    ucp.drop_env_key(settings(box), THRIFTY)
    flag = tmp_path / "user" / ".claude" / "settings.json"
    flag.parent.mkdir(parents=True)
    original = b'{"env": {"TOKEN": "secret"}}\n'
    flag.write_bytes(original)
    code, out = apply(capsys, box, "--thrifty-sonic", "add", "--user-settings", str(flag))
    assert code == 0, out
    assert [p.read_bytes() for p in flag.parent.glob("settings.json.*.bak")] == [original]
    assert not [p for p in box.rglob("*") if p.is_file() and p.read_bytes() == original]
    assert backups(box)  # the project file's pre-image keeps its project location


def test_transfer_refusal_runs_before_any_write(tmp_path, capsys):
    box = ucp.upgraded(tmp_path)
    ucp.drop_env_key(settings(box), TODO)
    own = ucp.seed_transfer(box, PAIR, "own.md", ucp.shipped(SOURCE))
    before = ucp.hash_tree(box)
    code, out = apply(capsys, box, "--prune", "inert", "--task-tools", "add", "--transfer-delete", str(own),
                      "--pair", PAIR)
    assert code == 2 and "this run's pair" in out, out
    assert ucp.hash_tree(box) == before


def test_prune_stale_runs_in_process_with_the_config(tmp_path, capsys, monkeypatch):
    box = ucp.upgraded(tmp_path)
    ucp.edit_config(box, r'^  feedback_dir: .*$', '  feedback_dir: "Inbox"')
    plain = doctor_sweeps.DESCOPED_RULES[0][0]
    (box / ucp.RULES / plain).write_text(ucp.shipped(plain), encoding="utf-8", newline="\n")
    seen = []
    real = doctor_cli._run_prune_stale
    monkeypatch.setattr(doctor_cli, "_run_prune_stale", lambda cfg: seen.append(cfg) or real(cfg))

    def no_child(*args, **kwargs):
        raise AssertionError(f"a child process ran: {args}")

    monkeypatch.setattr(upgrade_apply.pre, "_run_script", no_child)
    code, out = apply(capsys, box, "--prune-stale")
    assert code == 0 and not (box / ucp.RULES / plain).exists(), out
    assert len(seen) == 1 and seen[0].feedback_dir == "Inbox", seen


def pair_files(box, pair):
    return sorted(p.relative_to(box).as_posix() for p in (box / "planwise" / "upgrade-backups" / pair).rglob("*")
                  if p.is_file())


def test_prune_safe_to_discard_keeps_this_runs_pair(tmp_path, capsys):
    """The pre-images this upgrade run just wrote are neither offered nor pruned, as --transfer-delete refuses them."""
    box = ucp.upgraded(tmp_path)
    current = pair_files(box, PAIR)
    assert current  # the run backed up each rule it refreshed
    offers = upgrade_run.build_offers(box.resolve(), ucp.config_path(box), PAIR, None, "")
    assert "prune:safe-to-discard" not in [o["id"] for o in offers], offers
    earlier = ucp.seed_backup(box, OLD_PAIR)
    offers = upgrade_run.build_offers(box.resolve(), ucp.config_path(box), PAIR, None, "")
    offer = next(o for o in offers if o["id"] == "prune:safe-to-discard")
    assert offer["text"].startswith("1 file(s)"), offer
    capsys.readouterr()
    upgrade_run.print_offers([offer], box.resolve(), PAIR)
    accept = capsys.readouterr().out.splitlines()[-1]
    assert accept.endswith(f"--prune safe-to-discard --pair {PAIR}"), accept
    before = ucp.hash_tree(box)
    code, out = apply(capsys, box, "--prune", "safe-to-discard")  # this run's pair is unknown without --pair
    assert code == 2 and "--pair" in out and ucp.hash_tree(box) == before, out
    code, out = apply(capsys, box, "--prune", "safe-to-discard", "--pair", PAIR)
    assert code == 0 and not earlier.exists(), out
    assert pair_files(box, PAIR) == current
    # with both classes, this run's spent verdict cache goes and its pre-images stay
    consumed = list(box.glob("planwise/upgrade-conflicts/*/verdicts.json.consumed"))
    assert consumed
    ucp.seed_backup(box, OLD_PAIR)
    code, out = apply(capsys, box, "--prune", "safe-to-discard,inert", "--pair", PAIR)
    assert code == 0 and not any(p.exists() for p in consumed), out
    assert pair_files(box, PAIR) == current and not pair_files(box, OLD_PAIR)


def test_prune_scans_once_before_and_once_after(tmp_path, capsys, monkeypatch):
    import artifact_upgrade

    box = ucp.upgraded(tmp_path)
    ucp.seed_backup(box, OLD_PAIR)
    calls = []
    for module, name in ((artifact_upgrade, "_scan_recovery_artifacts"), (doctor_sweeps, "sweep_upgrade_leftovers")):
        real = getattr(module, name)
        monkeypatch.setattr(module, name, lambda cfg, _real=real, _name=name: calls.append(_name) or _real(cfg))
    code, out = apply(capsys, box, "--prune", "safe-to-discard,inert", "--pair", PAIR)
    assert code == 0, out
    assert len(calls) == 2, calls


def test_transfer_review_runs_once_per_call(tmp_path, capsys, monkeypatch):
    box = ucp.upgraded(tmp_path)
    body = ucp.shipped(SOURCE)
    first = ucp.seed_transfer(box, OLD_PAIR, "a.md", body)
    second = ucp.seed_transfer(box, OLD_PAIR, "b.md", body)
    calls = []
    real = transfer_review.review_transfers
    monkeypatch.setattr(transfer_review, "review_transfers", lambda cfg, **kw: calls.append(kw) or real(cfg, **kw))
    code, out = apply(capsys, box, "--transfer-delete", str(first), "--transfer-delete", str(second), "--pair", PAIR)
    assert code == 0 and not first.exists() and not second.exists(), out
    assert len(calls) == 1, calls
