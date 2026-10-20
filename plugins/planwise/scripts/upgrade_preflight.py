#!/usr/bin/env python3
"""Read-only preflight for `/planwise upgrade`: prints the upgrade card.

The card holds every value an upgrade run would otherwise spend tool calls
computing, plus the exact next commands. The skill router imports this module
lazily and calls `run(argv)`, after it has printed its own version notice. It
never writes, never prompts, never calls git, and always returns 0. Any
failure prints one `PLANWISE_UPGRADE_FALLBACK: {cause}` line instead of a card.

CLI: python -B upgrade_preflight.py upgrade [--project-root PATH] [--user-settings PATH]
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

BEGIN = "<!-- planwise:upgrade:begin -->"
END = "<!-- planwise:upgrade:end -->"
FALLBACK = "PLANWISE_UPGRADE_FALLBACK:"
HEREDOC = "VERDICTS_JSON"
QUESTION_LIMIT = 4  # AskUserQuestion takes at most this many questions per call
SUBPROCESS_TIMEOUT = 300
PLACEHOLDER_RE = re.compile(r"\$\w+")
TOKEN_SAVER_QUESTION = (
    '"Turn on Token Saver? A new Token Saver mode is available. It keeps task sessions under ~150K '
    '(avoids the linear carrying-cost of big sessions) and warns when a file is too large to fit a '
    'lean task." Options: "Yes (Recommended)" | "No"'
)
FEEDBACK_DRAFTS_QUESTION = (
    "Claude may now save local feedback drafts while planwise runs. Nothing is posted without "
    "`/planwise feedback --drafts` and your approval. How loud should drafting be? "
    "(notify — one line per draft, recommended / quiet — write silently / off — never draft)"
)
FEEDBACK_ENABLED_QUESTION = (
    "Enable upstream posting (`feedback.enabled: true`)? Posting still needs `gh` installed and "
    "authenticated, and every post asks you first. (Yes / No — keep drafts local, recommended)"
)
COMPARATOR_LINE = ("Comparator verdicts: {returned}/{diverged} (late: {n} resumed, {m} recorded after the writer "
                   "ran; failed: {k} — inline primitive used)")


class Fallback(Exception):
    """A cause the card cannot print through; run prints it as one fallback line."""


def version_tuple(text: str) -> tuple:
    parts = [int(p) for p in "".join(c if c.isdigit() else " " for c in str(text)).split()]
    return tuple(parts)


def compare_versions(pinned: str, shipped: str) -> int:
    """-1, 0 or 1 per component, zero-padded. An absent pin is 0.0.0."""
    a, b = version_tuple(pinned or "0.0.0"), version_tuple(shipped or "0.0.0")
    size = max(len(a), len(b))
    a, b = a + (0,) * (size - len(a)), b + (0,) * (size - len(b))
    return (a > b) - (a < b)


def norm_path(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def posix(p) -> str:
    return Path(str(p)).as_posix()


def normalise(argv: list[str]) -> list[str]:
    """Strip each value and drop empty strings and unexpanded `$name` placeholders."""
    tokens = [str(a).strip() for a in argv]
    return [t for t in tokens if t and not PLACEHOLDER_RE.fullmatch(t)]


def parse_flags(rest: list[str]) -> dict:
    flags = {"user_settings": None, "project_root": None}
    i = 0
    while i < len(rest):
        if rest[i] == "--user-settings" and i + 1 < len(rest):
            flags["user_settings"] = rest[i + 1]
            i += 2
        elif rest[i] == "--project-root" and i + 1 < len(rest):
            flags["project_root"] = rest[i + 1]
            i += 2
        else:
            i += 1
    return flags


def resolve_config(project_root: Path) -> tuple[Path, dict]:
    import config_loader

    config_path = config_loader.find_config_upward(project_root, stop_at=project_root)
    if config_path is None:
        raise Fallback(
            f"config.yaml not found at {project_root.as_posix()}/config.yaml "
            f"or {project_root.as_posix()}/*/config.yaml"
        )
    try:
        config = config_loader.load_config(config_path=config_path)
    except Exception as exc:
        raise Fallback(f"config.yaml parse error at {config_path.as_posix()}: {exc}") from exc
    return config_path, config


def _mapping(value) -> dict:
    return value if isinstance(value, dict) else {}


def build_cfg(config: dict, project_root: Path):
    import config_gen

    project = _mapping(config.get("project"))
    context = _mapping(config.get("context"))
    plugin_root = config_gen.get_plugin_root()
    return config_gen.InitConfig(
        project_name=str(project.get("name") or project_root.name),
        project_root=project_root,
        plugin_root=plugin_root,
        planwise_root=str(project.get("planwise_root") or "planwise"),
        plans_dir=str(project.get("plans_dir") or "Plans"),
        backlog_dir=str(project.get("backlog_dir") or "Backlog"),
        lessons_dir=str(project.get("lessons_dir") or "LessonsLearned"),
        feedback_dir=str(project.get("feedback_dir") or "Feedback"),
        install_scope=str(project.get("install_scope") or "project"),
        plan_tier=str(context.get("plan_tier") or "pro"),
        plugin_version=config_gen.read_plugin_version(plugin_root),
        token_saver=bool(context.get("token_saver", False)),
    )


def resolve_user_settings(flag) -> tuple[Path, str]:
    """The two-step order: the --user-settings flag, then the home settings file."""
    if flag:
        return Path(flag), "step 1: --user-settings flag"
    return Path.home() / ".claude" / "settings.json", "step 2: home settings"


def branch_of(pinned: str, shipped: str, stored_root, live_root) -> str:
    cmp = compare_versions(pinned, shipped)
    if cmp < 0:
        return "upgrade"
    if cmp > 0:
        return "downgrade"
    if stored_root and norm_path(stored_root) == norm_path(live_root):
        return "up-to-date"
    return "repoint"


def diverged_rows(cfg) -> list[dict]:
    import doctor_cli
    import rule_divergence

    rows = []
    for row in doctor_cli._list_diverged_rows(cfg):
        installed = cfg.project_root / row["installed"]
        shipped = cfg.plugin_root / row["shipped"]
        i_text = installed.read_text(encoding="utf-8-sig")
        s_text = shipped.read_text(encoding="utf-8-sig")
        verdict = rule_divergence._classify_diverged(*rule_divergence.normalize_pair(i_text, s_text))
        rows.append({
            "filename": row["filename"],
            "set": row.get("set", "installed"),
            "installed_path": installed.as_posix(),
            "shipped_path": shipped.as_posix(),
            "installed_sha256": row["installed_sha256"],
            "inline": f"{verdict.classification}/{verdict.confidence}",
            "agent": "no" if rule_divergence._destructively_removable(verdict) else "yes",
        })
    return rows


def _run_script(argv: list[str], extra_env: dict | None = None) -> tuple[int, str]:
    """Run one child: (exit code, stdout then stderr). A timeout is exit 1 with a named line, never a traceback."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **(extra_env or {}))
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=SUBPROCESS_TIMEOUT, env=env, check=False)
    except subprocess.TimeoutExpired:
        return 1, f"error: {Path(argv[min(2, len(argv) - 1)]).name} timed out after {SUBPROCESS_TIMEOUT} s"
    return r.returncode, r.stdout + r.stderr


def _json_call(argvs: list, script: str, *args: str):
    """Run one script with python -B, record its argv, and parse the JSON in its stdout."""
    argv = [sys.executable, "-B", str(SCRIPTS / script), *args]
    argvs.append(argv)
    try:
        _code, out = _run_script(argv)
        start = next(i for i, line in enumerate(out.splitlines(keepends=True)) if line.startswith("{"))
        text = "".join(out.splitlines(keepends=True)[start:])
        return json.JSONDecoder().raw_decode(text)[0]
    except Exception:  # noqa: BLE001 - an unreadable result is reported as None
        return None


def migration_questions(config_path: Path, argvs: list | None = None) -> dict:
    """The `--questions` JSON, reduced to question lines, any_legacy and would_refuse."""
    data = _json_call(argvs if argvs is not None else [], "index_shape_preflight.py",
                      "--config", str(config_path), "--questions")
    if not isinstance(data, dict) or "error" in data:
        return {"ok": False, "questions": [], "any_legacy": False, "would_refuse": [], "data": data}
    questions, refuse = [], []
    for family in ("backlog", "lessons", "plans"):
        entry = _mapping(data.get(family))
        for q in entry.get("questions") or []:
            questions.append((family, q))
        refuse.extend(f"{family}: {r}" for r in entry.get("would_refuse") or [])
    return {"ok": True, "questions": questions, "any_legacy": bool(data.get("any_legacy")),
            "would_refuse": refuse, "data": data}


def question_line(family: str, q) -> str:
    q = q if isinstance(q, dict) else {"prompt": str(q)}
    prompt = q.get("prompt") or q.get("question") or ""
    labels = [(f"{o.get('label', '')} => {json.dumps(o['answer'], ensure_ascii=False)}"
               if isinstance(o.get("answer"), dict) else str(o.get("label", ""))) if isinstance(o, dict) else str(o)
              for o in q.get("options") or []]
    qid = f" [{q['id']}]" if q.get("id") else ""
    return f"{family}{qid}: {prompt} — options: {' | '.join(labels)}"


def _settings_json(path: Path):
    """(data, klass): klass is '' when the file parses, else 'missing' or 'invalid JSON'."""
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), ""
    except (OSError, ValueError):
        return None, "invalid JSON"


def thrifty_class(path: Path) -> str:
    """The classes of doctor_cli._sweep_thrifty_sonic for one path: ok, missing, wrong value, invalid JSON."""
    data, klass = _settings_json(path)
    if klass:
        return klass
    env = data.get("env") if isinstance(data, dict) else None
    value = env.get("CLAUDE_CODE_THRIFTY_SONIC") if isinstance(env, dict) else None
    if value is None:
        return "missing"
    return "ok" if value == "false" else "wrong value"


def task_tools_state(cfg) -> str:
    for name in ("settings.json", "settings.local.json"):
        data, klass = _settings_json(cfg.project_root / ".claude" / name)
        env = data.get("env") if isinstance(data, dict) else None
        if not klass and isinstance(env, dict) and "CLAUDE_CODE_ENABLE_TODO_TOOLS" in env:
            return "set"
    return "absent"


def gh_state() -> str:
    """ok, unauthenticated, absent or timed-out, from the plugin's single `gh` probe."""
    import doctor_probes

    env = doctor_probes._gh_environment()
    if env.get("timed_out"):
        return "timed-out"
    if not env.get("path"):
        return "absent"
    return "ok" if env.get("authenticated") else "unauthenticated"


def offers(cfg, user_settings: Path) -> dict:
    import doctor_cli

    return {
        "grants": doctor_cli._sweep_settings_grants(cfg),
        "gh": gh_state(),
        "task_tools": task_tools_state(cfg),
        "thrifty": {
            "project": thrifty_class(cfg.project_root / ".claude" / "settings.json"),
            "user": thrifty_class(user_settings),
        },
    }


def offers_pending(found: dict, scope: str) -> str:
    """The first pending offer as a reason, or ''."""
    if scope == "project" and found["grants"]:
        return f"{len(found['grants'])} settings grant(s) need normalizing"
    bad = [k for k, v in found["thrifty"].items() if v != "ok"]
    if bad:
        return f"thrifty-sonic offer pending ({', '.join(bad)})"
    if scope == "project" and found["task_tools"] == "absent":
        return "task-tools offer pending"
    if found["gh"] in ("absent", "unauthenticated"):
        return f"gh is {found['gh']}"
    return ""


def noop_proof(branch: str, rows: list, config: dict, config_path: Path, found: dict,
               scope: str) -> tuple[bool, str, list]:
    """True only when every condition of the no-op row holds. Returns (ok, reason, argvs)."""
    argvs: list = []
    if branch != "up-to-date":
        return False, f"branch is {branch}, not up-to-date", argvs
    if rows:
        return False, f"{len(rows)} diverged rule(s)", argvs
    if "style" not in config:
        return False, "config has no style key", argvs
    if "feedback_dir" not in _mapping(config.get("project")):
        return False, "config has no project.feedback_dir key", argvs

    import config_gen
    import migrate_lessons_index

    if config_gen.drafts_key_state(config) == "absent":
        return False, "config has no feedback.drafts key", argvs

    cfg_arg = ("--config", str(config_path))
    backlog = _json_call(argvs, "migrate_backlog_index.py", *cfg_arg, "--report")
    lessons = _json_call(argvs, "migrate_lessons_index.py", *cfg_arg, "--report")
    plans = _json_call(argvs, "generate_plans_index.py", *cfg_arg, "--check", "--json")
    asked = migration_questions(config_path, argvs)
    lessons_check = _json_call(argvs, "generate_lessons_index.py", *cfg_arg, "--check", "--json")

    for name, report in (("backlog", backlog), ("lessons", lessons), ("plans", plans)):
        if not isinstance(report, dict) or report.get("shape") != "generated":
            shape = report.get("shape") if isinstance(report, dict) else "unreadable"
            return False, f"{name} index shape is {shape}, not generated", argvs
    if plans.get("anomalies"):
        return False, f"plans index has {len(plans['anomalies'])} anomaly(ies)", argvs
    if not asked["ok"]:
        return False, "index_shape_preflight --questions was unreadable", argvs
    if asked["any_legacy"] or asked["would_refuse"]:
        return False, "a legacy index or a would_refuse entry is present", argvs
    if not isinstance(lessons_check, dict):
        return False, "lessons --check output was unreadable", argvs
    classes = {str(f.get("class")) if isinstance(f, dict) else str(f)
               for f in (lessons_check.get("drift") or []) + (lessons_check.get("anomalies") or [])}
    outside = sorted(classes - set(migrate_lessons_index.ACCEPTED_CHECK_CLASSES))
    if outside:
        return False, f"lessons --check findings outside the accepted classes: {', '.join(outside)}", argvs
    pending = offers_pending(found, scope)
    if pending:
        return False, pending, argvs
    return True, "", argvs


def sha_short(sha: str) -> str:
    return f"{sha[:4]}…{sha[-4:]}"


def answers_example(questions: list) -> str:
    """The `answers` object the writer reads: the chosen options' `answer` fragments, merged.

    The keys are answer kinds (`migration_answers.KNOWN_KEYS`), not question ids. List values from several
    questions concatenate under one key. With no question answered the object is empty.
    """
    merged: dict = {}
    for _family, q in questions:
        options = q.get("options") if isinstance(q, dict) else None
        first = next((o["answer"] for o in options or [] if isinstance(o, dict) and isinstance(o.get("answer"), dict)),
                     None)
        for key, value in (first or {}).items():
            if isinstance(value, list):
                merged.setdefault(key, []).extend(value)
            else:
                merged[key] = value
    return json.dumps(merged, ensure_ascii=False)


def next_command(root: Path, project_root: Path, pair: str, token_saver: bool, any_agent: bool,
                 downgrade: bool, user_settings: Path, questions: list | None = None) -> list[str]:
    """The run command lines. With migration questions the stdin document is the verdicts-plus-answers object."""
    parts = [(f'python -B "{root.as_posix()}/scripts/upgrade_run.py" --project-root "{project_root.as_posix()}"'
              f' --pair "{pair}" --user-settings "{user_settings.as_posix()}"')]
    if downgrade:
        parts.append("--allow-downgrade")
    if token_saver:
        parts.append("--token-saver")
    if not any_agent and not questions:
        return [" ".join(parts)]
    verdicts = ('[{"filename": "<rule file>", "source": "agent", "classification": "SUBSET|HAS_UNIQUE", '
                '"confidence": "<level>", "unique_blocks": [], "tolerated_fragments": [], "rationale": "", '
                '"notes": "", "installed_sha256": "<from the card>"}]') if any_agent else "[]"
    if questions:
        parts.append("--answers-json")
        example = f'{{"verdicts": {verdicts}, "answers": {answers_example(questions)}}}'
    else:
        example = verdicts
    parts.append(f"--verdicts-stdin <<'{HEREDOC}'")
    return [" ".join(parts), example, HEREDOC]


def question_steps(token_saver: bool, questions: list, feedback_state: str = "set") -> list[str]:
    """The AskUserQuestion step text: the pre-writer questions and the migration questions, merged when they fit.

    The pre-writer questions are the Token Saver question (when off) and the two feedback questions (when the
    config has no `feedback.drafts` key). The run command takes the answers as flags the model adds.
    """
    ask_feedback = feedback_state != "set"
    pre = (0 if token_saver else 1) + (2 if ask_feedback else 0)
    if not pre and not questions:
        return []
    names = (["the Token Saver question"] if not token_saver else []) + (
        ["the feedback drafts question and the feedback posting question"] if ask_feedback else [])
    pre_what = " and ".join(names)
    lines = []
    if pre and pre + len(questions) <= QUESTION_LIMIT:
        what = pre_what + (" and every migration question listed above" if questions else "")
        lines.append(f"Ask one AskUserQuestion with {what}.")
    elif pre:
        lines.append(f"Ask {pre_what} in one AskUserQuestion, then the migration questions listed "
                     f"above in a second call (at most {QUESTION_LIMIT} per call).")
    else:
        lines.append(f"Ask the migration questions listed above in one AskUserQuestion (at most "
                     f"{QUESTION_LIMIT} per call).")
    if not token_saver:
        lines.append(f"  Token Saver question: {TOKEN_SAVER_QUESTION}")
        lines.append("  On Yes, add --token-saver to the run command below, right after its --user-settings value. "
                     "On No, run it as written.")
    if ask_feedback:
        lines.append(f"  Feedback drafts question: {FEEDBACK_DRAFTS_QUESTION}")
        lines.append(f"  Feedback posting question: {FEEDBACK_ENABLED_QUESTION}")
        lines.append("  On notify / quiet / off, add `--feedback-drafts {value}` to the run command below, right "
                     "after `--user-settings` (or after `--token-saver` when present). On Yes to posting, add "
                     "`--feedback-enabled`. Unattended: add neither; the writer backfills `feedback.drafts: notify` "
                     "into an existing feedback block and leaves `feedback.enabled` as it is.")
    if questions:
        lines.append("  Each migration option above ends in `=> {answer}`. Build the stdin object's \"answers\" by "
                     "merging the answer object of every chosen option: same key, lists concatenate. Example, with "
                     f"each question's first option chosen: {answers_example(questions)}. "
                     "A question left unanswered adds nothing, and no answer at all is {}.")
    return lines


def render_next(branch: str, noop: bool, ctx: dict) -> list[str]:
    if branch == "up-to-date" and noop:
        return ["NEXT", f'Nothing to do. Report: "Plugin version: {ctx["shipped"]} — already up to date."']
    lines = ["NEXT"]
    step = 1
    questions = ctx.get("questions") or []
    asks = question_steps(ctx["token_saver"], questions, ctx.get("feedback_drafts", "set"))
    if asks:
        lines.append(f"{step}. {asks[0]}")
        lines += asks[1:]
        step += 1
    if branch == "downgrade":
        lines.append(f"{step}. Ask the Step 1 downgrade question (read handlers/upgrade.md, Step 1). "
                     "On approval, run the command below, which passes --allow-downgrade. Otherwise stop.")
        step += 1
    elif branch != "repoint" and ctx["any_agent"]:
        lines.append(
            f"{step}. Interactive session only: spawn planwise:rule-comparator once per row with "
            "agent=yes, in one parallel batch. Prompt fields: filename, kind, installed_path, shipped_path "
            "(absolute, from the paths: lines above). A comparator that returns late gets one resume, then the "
            "inline verdict stands. A one-turn `-p` run (no later turn can collect verdicts or answers): skip "
            "to the next step with `[]` as the verdicts.")
        step += 1
    any_agent = ctx["any_agent"] and branch != "repoint"
    command = next_command(ctx["root"], ctx["project_root"], ctx["pair"], ctx["token_saver"],
                           any_agent, branch == "downgrade", ctx["user_settings"], questions)
    if len(command) > 1:
        what = "the merged verdicts and the answers" if questions else "the merged verdicts"
        lines.append(f"{step}. Run once, passing {what} on stdin in the same Bash call "
                     "(no separate verdicts.json Write)."
                     + (" Paste each comparator's JSON entry whole, then add installed_sha256:" if any_agent else ""))
    else:
        lines.append(f"{step}. Run once:")
    lines.extend(command)  # unindented: an indented closing token would not end the heredoc
    if len(command) > 1:
        lines.append("If the harness refuses the heredoc, Write the same JSON to a file and run the same command "
                     "with `--verdicts-file {path}` instead of `--verdicts-stdin`.")
    lines.append(f"{step + 1}. Report the CHAT SUMMARY upgrade_run prints. When the comparator step ran, also print "
                 f"one line `{COMPARATOR_LINE}`: count a file as failed when the writer printed \"ignoring cached "
                 "verdict\" or \"falling back to the inline primitive\", add `degraded` when returned is below "
                 "diverged, and omit the line when the comparator step did not run.")
    lines.append(f"{step + 2}. Ask the user once with the offer list upgrade_run prints, then run upgrade_apply "
                 "with the answers.")
    return lines


def render_card(ctx: dict, rows: list, questions: list, transfers: list, found: dict, artifacts: list,
                noop: tuple) -> str:
    lines = [
        BEGIN,
        "UPGRADE CARD — read-only preflight, nothing was written",
        (f"project_root: {ctx['project_root'].as_posix()}    config: {ctx['config_rel']}    "
         f"plugin_root (live): {ctx['root'].as_posix()}"),
        f"pinned: {ctx['pinned']}  shipped: {ctx['shipped']}  pair: {ctx['pair']}  branch: {ctx['branch']}",
        (f"token_saver: {'on' if ctx['token_saver'] else 'off'}    "
         f"feedback_drafts: {ctx['feedback_drafts'].replace('-', ' ')}    yaml: {ctx['yaml']}"),
        f"user settings: {ctx['user_settings'].as_posix()} ({ctx['user_step']})",
        "",
        f"Diverged rules ({len(rows)}):",
        "| filename | set | installed_sha256 | inline | agent |",
    ]
    lines += [f"| {r['filename']} | {r['set']} | {sha_short(r['installed_sha256'])} | {r['inline']} | {r['agent']} |"
              for r in rows]
    if rows:
        lines.append("shas: " + " ".join(f"{r['filename']}={r['installed_sha256']}" for r in rows))
        lines += [f"paths: {r['filename']}: installed={r['installed_path']} shipped={r['shipped_path']}"
                  for r in rows]
    lines.append(f"Migration questions ({len(questions)}):")
    lines += [f"  {question_line(f, q)}" for f, q in questions]
    lines.append(f"Earlier-pair transfers ({len(transfers)}):")
    lines += [f"  {t['pair']}/{t['filename']}: {t['status']} — {t['classification']}/{t['confidence']}"
              for t in transfers]
    grants = found["grants"]
    grant_text = "none" if not grants else f"{len(grants)} ({', '.join(sorted({g['klass'] for g in grants}))})"
    thrifty = found["thrifty"]
    lines.append(f"Offers: grants={grant_text}; gh={found['gh']}; task-tools={found['task_tools']}; "
                 f"thrifty-sonic={{project:{thrifty['project']}, user:{thrifty['user']}}}")
    if artifacts:
        lines.append("Recovery artifacts: " + " ".join(f"{klass} {str(path).replace(chr(92), '/')} ({count})"
                                                         for path, count, klass in artifacts))
    else:
        lines.append("Recovery artifacts: none")
    lines.append("")
    lines += render_next(ctx["branch"], noop[0], {**ctx, "questions": questions,
                                                  "any_agent": any(r["agent"] == "yes" for r in rows)})
    lines.append(END)
    return "\n".join(lines)


def yaml_state() -> str:
    try:
        import config_loader

        if config_loader.HAS_YAML:
            return "present"
        import pyyaml_remedy

        return f"absent (install: {pyyaml_remedy.pyyaml_install_command()})"
    except Exception:  # noqa: BLE001 - the field is informational
        return "absent"


def build_card(rest: list[str]) -> str:
    import artifact_upgrade
    import config_gen
    import transfer_review

    flags = parse_flags(rest)
    project_root = Path(flags["project_root"]).resolve() if flags["project_root"] else Path.cwd().resolve()
    config_path, config = resolve_config(project_root)
    cfg = build_cfg(config, project_root)
    pinned = str(config.get("plugin_version") or "0.0.0")
    shipped = cfg.plugin_version
    pair = f"{pinned}-to-{shipped}"
    branch = branch_of(pinned, shipped, config.get("plugin_root"), cfg.plugin_root)
    user_settings, user_step = resolve_user_settings(flags["user_settings"])

    rows = diverged_rows(cfg)
    found = offers(cfg, user_settings)
    asked = migration_questions(config_path)
    transfers = transfer_review.review_transfers(cfg, exclude_pair=pair)
    artifacts = artifact_upgrade._scan_recovery_artifacts(cfg)
    noop = noop_proof(branch, rows, config, config_path, found, cfg.install_scope)
    ctx = {
        "project_root": project_root, "root": cfg.plugin_root, "pinned": pinned, "shipped": shipped,
        "pair": pair, "branch": branch, "token_saver": cfg.token_saver, "yaml": yaml_state(),
        "user_settings": user_settings, "user_step": user_step,
        "feedback_drafts": config_gen.drafts_key_state(config),
        "config_rel": config_path.relative_to(project_root).as_posix()
        if project_root in config_path.parents else config_path.as_posix(),
    }
    return render_card(ctx, rows, asked["questions"], transfers, found, artifacts, noop[:2])


def run(argv: list[str]) -> int:
    """Print the card, or one fallback line. Always returns 0."""
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass
    tokens = normalise(list(argv))
    if tokens and tokens[0] == "upgrade":
        tokens = tokens[1:]
    try:
        print(build_card(tokens))
    except Fallback as exc:
        print(f"{FALLBACK} {exc}")
    except Exception as exc:  # noqa: BLE001 - contract: one fallback line, exit 0
        print(f"{FALLBACK} {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
