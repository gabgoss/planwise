"""Tests for the `scan`, `post` and `card` subcommands of scripts/feedback_post.py.

Every case runs the script in a subprocess with `-B` against the fake `gh` in tests/fake_gh/, with
every file under pytest's tmp_path. No case can reach an installed `gh`: the known-location list is
always replaced, and PATH holds either the fake or an empty folder.

Each expected key list is written from the tier table of Step 4.5 in
references/feedback-submission.md, not from the script's output.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugins" / "planwise" / "scripts"))
import feedback_post as fp

SCRIPT = HERE.parent / "plugins" / "planwise" / "scripts" / "feedback_post.py"
FAKE_DIR = HERE / "fake_gh"
FAKE = FAKE_DIR / "fake_gh.py"
WRAPPER = "gh.cmd" if os.name == "nt" else "gh"
REPO = "example-owner/example-repo"
# The driver skips a `.cmd` or `.bat` shim, so on Windows the fake's wrapper cannot be found on PATH.
# There the default route passes the fake through FEEDBACK_POST_GH_ARGV instead.
PATH_ROUTE = "override" if os.name == "nt" else "path"
POST_PRESS_TS = HERE.parent / "plugins" / "planwise" / "hooks" / "feedback" / "post-press.ts"


def card_pin(code_name: str, mark_name: str) -> "tuple[int, str]":
    """One exit code and the stderr words the review card reads beside it, from post-press.ts.

    The card acts on two results by exit code plus words on the last stderr line: a config file that
    is gone (EXIT_FAILED, CONFIG_GONE_MARK) and a draft that is no longer queued (EXIT_NO_DRAFT,
    NO_DRAFT_MARK). The script and the card must agree on both.
    """
    source = POST_PRESS_TS.read_text(encoding="utf-8")
    code = re.search(rf"^export const {code_name} = (\d+)\s*$", source, re.MULTILINE)
    mark = re.search(rf"^export const {mark_name} = '([^']+)'\s*$", source, re.MULTILINE)
    assert code is not None and mark is not None, f"{code_name} or {mark_name} literal not found in post-press.ts"
    return int(code.group(1)), mark.group(1)


def last_stderr_line(result: "subprocess.CompletedProcess") -> str:
    return [line for line in result.stderr.splitlines() if line.strip()][-1]


# ---------------------------------------------------------------- harness


def read_calls(log: Path) -> "list[list[str]]":
    """Every argv the fake recorded, oldest first. A missing log means no call."""
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def count_calls(log: Path, *words: str) -> int:
    """How many recorded calls hold `words` as a contiguous run of argv elements; no words counts every call."""
    total = 0
    for argv in read_calls(log):
        n = len(words)
        if n == 0 or any(argv[i:i + n] == list(words) for i in range(len(argv) - n + 1)):
            total += 1
    return total


def gh_env(tmp_path: Path, route: str = PATH_ROUTE, scenario: str = "empty", **extra: str) -> "tuple[dict, Path]":
    """An environment for one run, and the fake's log path.

    route: `path` puts the copied wrapper first on PATH; `override` passes `[python, -B, fake_gh.py]`
    through FEEDBACK_POST_GH_ARGV; `known` lists the wrapper as the only known location; `none`
    leaves `gh` unresolvable. Every route replaces the known-location list.
    """
    bin_dir = tmp_path / "bin"
    empty_dir = tmp_path / "empty"
    bin_dir.mkdir(exist_ok=True)
    empty_dir.mkdir(exist_ok=True)
    wrapper = bin_dir / WRAPPER
    shutil.copyfile(FAKE_DIR / WRAPPER, wrapper)
    os.chmod(wrapper, 0o755)
    log = tmp_path / "gh-calls.jsonl"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_GH_", "FEEDBACK_POST_"))}
    env.update(FAKE_GH_PYTHON=sys.executable, FAKE_GH_SCRIPT=str(FAKE), FAKE_GH_LOG=str(log), FAKE_GH_SCENARIO=scenario)
    env["FEEDBACK_POST_GH_CANDIDATES"] = ""
    env["PATH"] = str(empty_dir)
    if route == "path":
        env["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    elif route == "override":
        env["FEEDBACK_POST_GH_ARGV"] = json.dumps([sys.executable, "-B", str(FAKE)])
    elif route == "known":
        env["FEEDBACK_POST_GH_CANDIDATES"] = str(wrapper)
    env.update(extra)
    return env, log


def write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_bytes(f"feedback:\n  repo: {REPO}\n".encode())
    return path


def write_draft(tmp_path: Path, title: str, body: str) -> Path:
    path = tmp_path / "2026-01-01-draft-bug-example.md"
    path.write_bytes(f"---\ndrafted_by: model\nkind: bug\ntitle: {title}\nstatus: queued\n---\n\n{body}".encode())
    return path


def scan(tmp_path: Path, title: str, body: str, env: dict) -> "tuple[int, dict, float]":
    argv = [sys.executable, "-B", str(SCRIPT), "scan", "--config", str(write_config(tmp_path)),
            "--draft", str(write_draft(tmp_path, title, body)), "--json"]
    started = time.monotonic()
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", env=env, cwd=tmp_path, timeout=120, check=False)
    elapsed = time.monotonic() - started
    assert result.returncode == 0, result.stderr
    return result.returncode, json.loads(result.stdout), elapsed


# ---------------------------------------------------------------- fixtures and expected keys

FILE_NAME = (
    "Draft listing skips queued drafts",
    (
        "### What happened\n\nRunning list in scripts/feedback_drafts.py:120 skipped two drafts.\n"
        "Also see references/feedback-submission.md for the rule.\n"
        "The order lives in handlers/run.md step 4.5 there.\n"
        "Section 12 of the guide says so.\n\n"
        "### Environment\n\n- planwise version: 1.0.0 in config.yaml\n"
    ),
    # Tier A, score 4 each, by first appearance. The `:120` suffix is discarded. `step 4.5` joins
    # run.md in its sentence. `Section 12` has no Tier-A key in its sentence, so it is dropped.
    # config.yaml sits in the Environment section, which the keys never read.
    [("feedback_drafts.py", "A"), ("feedback-submission.md", "A"), ("run.md 4.5", "A")],
    # Tier D: title words of 4+ characters, no stopwords, the first 3.
    "Draft listing skips",
)

BACKTICK = (
    "Prepare step rejects clean body",
    (
        "The `prepare-post` command and the `--json` flag fail, and `list --table` too.\n"
        "See `feedback_post.py` for the caller.\n"
        "The `planwise` word, `Ok`, `snake_case` and `one two three four five` are other spans.\n"
    ),
    # feedback_post.py is Tier A (4) and outranks its own Tier-B1 copy. prepare-post and --json hold a
    # separator and list --table spans 2 words: Tier B1 (3). snake_case is B1 too but fifth, so the
    # top-4 cut drops it. `planwise` is a lone stopword, `Ok` is under 3 characters, and the 5-word
    # span is over 4 words.
    [("feedback_post.py", "A"), ("prepare-post", "B1"), ("--json", "B1"), ("list --table", "B1")],
    "Prepare step rejects",
)

SINGLE_WORD_SPAN = (
    "Something odd here",
    "Use the `frobnicate` option.\n",
    # One word, no separator: Tier B2.
    [("frobnicate", "B2")],
    # "odd" is under 4 characters.
    "Something here",
)

ERROR_LINE = (
    "Crash when listing drafts",
    (
        "### What happened\n\nThe list command stopped:\n\n```\nTraceback (most recent call last):\n"
        "  File \"<stdin>\", line 3\nERROR: ModuleNotFoundError raised while importing yaml module\n```\n\n"
        "> cannot open the queue file\n"
    ),
    # Tier C: the Traceback line loses its parenthesised fragment, and ":" fails the 3-character pattern,
    # so 1 word survives, under the minimum of 2. The `File` line carries no error signature. The first
    # fenced line that yields a key is the ERROR line: all 7 words survive. At most one Tier-C
    # key, so the quoted `cannot` line adds nothing. `line 3` has no Tier-A key in its sentence.
    [("ERROR: ModuleNotFoundError raised while importing yaml module", "C")],
    # "when" is a stopword.
    "Crash listing drafts",
)


@pytest.mark.parametrize("case", [FILE_NAME, BACKTICK, SINGLE_WORD_SPAN, ERROR_LINE], ids=["file-name", "backtick", "single-word-span", "error-line"])
def test_scan_keys_follow_the_tier_table(tmp_path, case):
    title, body, expected_keys, title_query = case
    env, log = gh_env(tmp_path)
    before = count_calls(log, "issue", "list")
    _code, report, _elapsed = scan(tmp_path, title, body, env)
    assert [(k["key"], k["tier"]) for k in report["keys"]] == expected_keys
    expected_queries = [key for key, _tier in expected_keys] + [title_query]
    assert [q["query"] for q in report["queries"]] == expected_queries
    assert all(q["status"] == "ok" for q in report["queries"])
    assert count_calls(log, "issue", "list") - before == len(expected_queries)
    assert count_calls(log, "issue", "create") == count_calls(log, "issue", "comment") == 0
    assert report["gh"]["source"] == PATH_ROUTE
    first = report["queries"][0]["argv"]
    assert first[len(report["gh"]["argv"]):] == [
        "issue", "list", "-R", REPO, "--state", "all", "--limit", "20",
        "--search", f"{expected_queries[0]} in:title,body", "--json", "number,title,state,createdAt,url",
    ]
    assert (report["outcome"], report["caveat"]) == (
        "CLEAR", f"Duplicate scan: no matching issues found in {REPO}, open or closed, across {len(expected_queries)} searches.")


def test_pure_prose_runs_title_terms_then_the_recency_listing(tmp_path):
    scenario = tmp_path / "recent.json"
    recent = [{"number": n, "title": f"Issue {n}", "state": "OPEN", "url": f"u{n}", "age_days": n} for n in range(1, 8)]
    scenario.write_text(json.dumps({"responses": [], "recent": recent}), encoding="utf-8")
    env, log = gh_env(tmp_path, scenario=str(scenario))
    before = count_calls(log, "issue", "list")
    # No Tier A-C key. Title terms: "Planwise" is a stopword; menu, feels, slow, sometimes qualify.
    _code, report, _elapsed = scan(tmp_path, "Planwise menu feels slow sometimes", "When I open the menu it takes a while to show anything.\n", env)
    assert report["keys"] == []
    assert [(q["query"], q["kind"]) for q in report["queries"]] == [
        ("menu feels slow", "title"), ("menu", "title-term"), ("feels", "title-term"), ("slow", "title-term"), ("", "recency")]
    recency = report["queries"][-1]["argv"]
    assert "--search" not in recency and recency[-2:] == ["--json", "number,title,state,createdAt,url"]
    assert count_calls(log, "issue", "list") - before == 5
    assert report["outcome"] == "WEAK"
    assert [row["number"] for row in report["ranked"]] == [1, 2, 3, 4, 5]


def test_merge_ranking_and_self_duplicate(tmp_path):
    title, body, _keys, _title_query = FILE_NAME
    scenario = tmp_path / "rows.json"
    scenario.write_text(json.dumps({"responses": [
        {"match": "feedback_drafts.py in:", "rows": [
            {"number": 10, "title": "List skips drafts in feedback_drafts.py", "state": "OPEN", "url": "u10", "age_days": 3},
            {"number": 13, "title": title, "state": "OPEN", "url": "u13", "age_minutes": 2}]},
        {"match": "Draft listing skips in:", "rows": [
            {"number": 10, "title": "List skips drafts in feedback_drafts.py", "state": "OPEN", "url": "u10", "age_days": 3},
            {"number": 11, "title": "Unrelated wording", "state": "CLOSED", "url": "u11", "age_days": 200}]},
        {"match": "feedback-submission.md in:", "rows": [
            {"number": 12, "title": "Spec page", "state": "CLOSED", "url": "u12", "age_days": 400}]},
    ]}), encoding="utf-8")
    env, log = gh_env(tmp_path, scenario=str(scenario))
    _code, report, _elapsed = scan(tmp_path, title, body, env)
    merged = {row["number"]: row for row in report["merged"]}
    assert set(merged) == {10, 11, 12}
    # #10: keys 4 + 1, +2 cited basename in its title, +2 within 14 days.
    assert (merged[10]["score"], merged[10]["best_key_score"], merged[10]["matched_keys"]) == (9, 4, ["feedback_drafts.py", "Draft listing skips"])
    assert (merged[11]["score"], merged[12]["score"]) == (1, 4)
    assert [row["number"] for row in report["ranked"]] == [10, 12]
    assert report["self_duplicate"] == 13
    assert report["notice"] == "This draft appears to have already been posted as #13 — check before posting again."
    assert report["outcome"] == "FOUND"
    assert count_calls(log, "issue", "create") == count_calls(log, "issue", "comment") == 0


def test_title_only_never_outranks_a_strong_key_and_file_name_matches_keep_a_slot():
    def entry(number, score, best):
        return {"number": number, "title": "", "state": "OPEN", "createdAt": "2019-01-01T00:00:00Z", "score": score, "best_key_score": best}

    shown, further, suppressed = fp.rank([entry(1, 5, 1), entry(2, 4, 3), entry(3, 2, 3)])
    assert [e["number"] for e in shown] == [2, 1]
    assert (further, suppressed) == (0, 1)
    crowd = [entry(n, 9, 3) for n in range(10, 16)] + [entry(20, 4, 4), entry(21, 4, 4), entry(22, 4, 4)]
    shown, further, _suppressed = fp.rank(crowd)
    numbers = [e["number"] for e in shown]
    assert len(numbers) == 5 and {20, 21} <= set(numbers) and 22 not in numbers
    assert further == len(crowd) - 5


def test_a_query_over_ten_seconds_is_abandoned_and_the_scan_continues(tmp_path):
    title, body, _keys, _title_query = FILE_NAME
    env, log = gh_env(tmp_path, route="override", FAKE_GH_SLEEP="30", FAKE_GH_MATCH="feedback_drafts.py in:")
    _code, report, elapsed = scan(tmp_path, title, body, env)
    assert [q["status"] for q in report["queries"]] == ["timeout", "ok", "ok", "ok"]
    assert 9.5 <= elapsed < 25
    assert count_calls(log, "issue", "list") == 4
    assert report["outcome"] == "INCOMPLETE"
    assert report["caveat"] == "Duplicate scan was incomplete — 3 of 4 searches returned. Candidates below may be missing entries."


def test_the_scan_budget_stops_further_queries(tmp_path):
    title, body, _keys, _title_query = FILE_NAME
    env, log = gh_env(tmp_path, route="override", FEEDBACK_POST_SCAN_BUDGET="1.0", FAKE_GH_SLEEP="0.8")
    _code, report, elapsed = scan(tmp_path, title, body, env)
    statuses = [q["status"] for q in report["queries"]]
    run = [s for s in statuses if s != "not-run"]
    assert report["budget_stopped"] is True
    assert 1 <= len(run) < 4 and statuses[len(run):] == ["not-run"] * (4 - len(run))
    assert count_calls(log, "issue", "list") == len(run)
    assert elapsed < 10
    assert report["gh"]["source"] == "override"


def test_gh_not_found_reports_unknown_and_calls_nothing(tmp_path):
    title, body, _keys, _title_query = FILE_NAME
    env, log = gh_env(tmp_path, route="none")
    _code, report, _elapsed = scan(tmp_path, title, body, env)
    assert report["gh"] is None and report["queries"] == []
    assert report["outcome"] == "UNKNOWN"
    assert report["caveat"] == "Duplicate scan could not run — gh is not available. Whether this duplicates an existing issue is unknown."
    assert count_calls(log) == 0


@pytest.mark.skipif(os.name == "nt", reason="the fake's Windows wrapper is a .cmd shim, which the driver skips by design")
def test_a_known_location_off_path_is_found_and_reported(tmp_path):
    title, body, _keys, _title_query = FILE_NAME
    env, log = gh_env(tmp_path, route="known")
    _code, report, _elapsed = scan(tmp_path, title, body, env)
    wrapper = str(tmp_path / "bin" / WRAPPER)
    assert report["gh"] == {"argv": [wrapper], "source": "known-location", "note": f"found at {wrapper}, not on this session's PATH"}
    assert count_calls(log, "--version") == 1
    assert count_calls(log, "issue", "list") == 4


# ---------------------------------------------------------------- the post chain
#
# Each expected line is copied from The Unattended Post Path in references/feedback-submission.md,
# not from the script's output.

DRAFT_ID = "d-0001"
POST_BODY = "### What happened\n\nThe list command in feedback_drafts.py skipped a queued draft.\n"
ISSUE_URL = "https://github.com/example-owner/example-repo/issues/77"
COMMENT_URL = "https://github.com/example-owner/example-repo/issues/42#issuecomment-1"

# Runs the read-only fake in-process, then prints the URL a real gh prints after a successful post.
# The fake itself prints nothing for `issue create` and `issue comment`.
URL_WRAPPER = (
    "import runpy, sys\n"
    "fake, args = sys.argv[1], sys.argv[2:]\n"
    "sys.argv = [fake, *args]\n"
    "code = 0\n"
    "try:\n"
    "    runpy.run_path(fake, run_name='__main__')\n"
    "except SystemExit as exc:\n"
    "    code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)\n"
    "if code == 0 and args[:2] == ['issue', 'create']:\n"
    f"    print({ISSUE_URL!r})\n"
    "if code == 0 and args[:2] == ['issue', 'comment']:\n"
    f"    print({COMMENT_URL!r})\n"
    "sys.exit(code)\n"
)


def url_env(tmp_path: Path, scenario: str = "empty", **extra: str) -> "tuple[dict, Path]":
    """The `override` route, with the fake wrapped so a successful post prints a URL."""
    argv = json.dumps([sys.executable, "-B", "-c", URL_WRAPPER, str(FAKE)])
    return gh_env(tmp_path, route="override", scenario=scenario, FEEDBACK_POST_GH_ARGV=argv, **extra)


def post_setup(tmp_path: Path, title: str = "List skips a queued draft", body: str = POST_BODY,
               enabled: str = "true", kind: str = "bug", status: str = "queued") -> "tuple[Path, Path]":
    """A config with posting set, and one model draft in its Feedback/Feedback-Drafts folder. Returns (config, draft)."""
    config = tmp_path / "config.yaml"
    config.write_bytes(f"feedback:\n  enabled: {enabled}\n  repo: {REPO}\n".encode())
    folder = tmp_path / "Feedback" / "Feedback-Drafts"
    folder.mkdir(parents=True, exist_ok=True)
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    draft = folder / f"2026-01-01-draft-{kind}-example.md"
    draft.write_bytes((f"---\ndraft_id: {DRAFT_ID}\ncreated_at: {created}\ndrafted_by: model\nkind: {kind}\n"
                       f"title: {title}\nstatus: {status}\n---\n\n{body}").encode())
    return config, draft


def post(config: Path, env: dict, draft_id: str = DRAFT_ID, *extra: str) -> "subprocess.CompletedProcess":
    argv = [sys.executable, "-B", str(SCRIPT), "post", "--config", str(config), "--draft-id", draft_id, *extra]
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", env=env, cwd=config.parent, timeout=120, check=False)


def match_scenario(tmp_path: Path, rows: list, views: "dict | None" = None, match: str = "feedback_drafts.py in:") -> str:
    """A scenario file whose rows answer one search key, with an optional `views` map for `issue view`."""
    data: dict = {"responses": [{"match": match, "rows": rows}]}
    if views is not None:
        data["views"] = views
    scenario = tmp_path / "rows.json"
    scenario.write_text(json.dumps(data), encoding="utf-8")
    return str(scenario)


def view_calls(log: Path) -> "list[list[str]]":
    return [argv for argv in read_calls(log) if argv[:2] == ["issue", "view"]]


def promoted_files(tmp_path: Path) -> "list[Path]":
    return sorted(p for p in (tmp_path / "Feedback" / "Feedback-Drafts").glob("*.md") if "-draft-" not in p.name and "-comment-" not in p.name)


def posts(log: Path) -> "tuple[int, int]":
    return count_calls(log, "issue", "create"), count_calls(log, "issue", "comment")


def marker(path: Path) -> dict:
    fields: dict[str, str] = {}
    for line in path.with_name(path.name + ".posted").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition(": ")
        fields[key if sep else line.rstrip(":")] = value
    return fields


def test_scan_text_mode_prints_the_em_dash_through_a_pipe(tmp_path):
    title, body, _keys, _title_query = FILE_NAME
    env, log = gh_env(tmp_path, route="none")
    env.pop("PYTHONIOENCODING", None)
    argv = [sys.executable, "-B", str(SCRIPT), "scan", "--config", str(write_config(tmp_path)),
            "--draft", str(write_draft(tmp_path, title, body))]
    result = subprocess.run(argv, capture_output=True, env=env, cwd=tmp_path, timeout=120, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode("utf-8") == (
        "Duplicate scan could not run — gh is not available. Whether this duplicates an existing issue is unknown.\n"
        if os.name != "nt" else
        "Duplicate scan could not run — gh is not available. Whether this duplicates an existing issue is unknown.\r\n")
    assert count_calls(log) == 0


def test_clear_scan_creates_an_issue_and_writes_the_sidecar(tmp_path):
    config, draft = post_setup(tmp_path)
    env, log = url_env(tmp_path)
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"Feedback posted to {REPO} as a new issue: {ISSUE_URL}\n"
    assert posts(log) == (1, 0)
    [promoted] = promoted_files(tmp_path)
    [create] = [argv for argv in read_calls(log) if argv[:2] == ["issue", "create"]]
    assert create == ["issue", "create", "-R", REPO, "--title", "List skips a queued draft",
                      "--body-file", str(promoted), "--label", "bug"]
    assert "status: promoted" in draft.read_text(encoding="utf-8")
    assert marker(promoted) == {"posted": time.strftime("%Y-%m-%d", time.gmtime()), "url": ISSUE_URL, "route": "issue"}
    # The scan ran before the post: the identifier query and the title query.
    assert count_calls(log, "issue", "list") == 2
    assert count_calls(log, "auth", "status") == 1


def test_a_ranked_candidate_is_answered_with_a_comment(tmp_path):
    scenario = tmp_path / "rows.json"
    scenario.write_text(json.dumps({"responses": [{"match": "feedback_drafts.py in:", "rows": [
        {"number": 42, "title": "Queue listing", "state": "OPEN", "url": "u42", "age_days": 200}]}]}), encoding="utf-8")
    config, _draft = post_setup(tmp_path)
    env, log = url_env(tmp_path, scenario=str(scenario))
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"Feedback posted to {REPO} as a comment on #42 \"Queue listing\" (open): {COMMENT_URL}\n"
    assert posts(log) == (0, 1)
    # The live read ran once, before the post, with the three fields the route reads.
    assert view_calls(log) == [["issue", "view", "42", "-R", REPO, "--json", "number,state,labels"]]
    [promoted] = promoted_files(tmp_path)
    # The comment draft keeps the promoted file's own date, so the date appears once in its name.
    [comment_draft] = (tmp_path / "Feedback" / "Feedback-Drafts").glob("*-comment-42-*.md")
    assert comment_draft.name == promoted.name[:10] + "-comment-42-bug-list-skips-a-queued-draft.md"
    [comment] = [argv for argv in read_calls(log) if argv[:2] == ["issue", "comment"]]
    assert comment == ["issue", "comment", "-R", REPO, "42", "--body-file", str(comment_draft)]
    text = comment_draft.read_text(encoding="utf-8")
    assert text == ("Filed with `/planwise feedback` as a comment rather than a new issue — this looked like the same "
                    "subject as this thread. **List skips a queued draft**\n\n" + promoted.read_text(encoding="utf-8"))
    expected = {"posted": time.strftime("%Y-%m-%d", time.gmtime()), "url": COMMENT_URL, "route": "comment"}
    # Both files are marked, so the promoted draft no longer reads as never posted.
    assert marker(comment_draft) == expected and marker(promoted) == expected


OPEN_42 = {"number": 42, "title": "Queue listing", "state": "OPEN", "url": "u42", "age_days": 200}
CLOSED_42 = {**OPEN_42, "state": "CLOSED", "labels": ["bug", "resolved"]}


@pytest.mark.parametrize("rows,views,state,views_made", [
    # Closed and resolved in the scan: no live read is needed to refuse it.
    ([CLOSED_42], None, "closed", 0),
    # Open, but its maintainers already took it in.
    ([{**OPEN_42, "labels": ["bug", "intake"]}], None, "open", 1),
    ([{**OPEN_42, "labels": ["wontfix"]}], None, "open", 1),
    # Open in the scan and closed by the time of the live read.
    ([OPEN_42], {"42": {"state": "CLOSED", "labels": ["resolved"]}}, "closed", 1),
    # The live read failed, so the issue is not confirmed open.
    ([OPEN_42], {"42": None}, "open", 1),
], ids=["closed-resolved", "open-intake", "open-wontfix", "closed-since-the-scan", "view-failed"])
def test_a_match_that_cannot_take_a_comment_gets_a_new_issue_that_names_it(tmp_path, rows, views, state, views_made):
    config, _draft = post_setup(tmp_path)
    env, log = url_env(tmp_path, scenario=match_scenario(tmp_path, rows, views))
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"Feedback posted to {REPO} as a new issue: {ISSUE_URL} (related to #42, which is {state})\n"
    assert posts(log) == (1, 0)
    assert len(view_calls(log)) == views_made
    [promoted] = promoted_files(tmp_path)
    assert promoted.read_text(encoding="utf-8").startswith(f"Possibly related to #42 ({state}).\n\n### What happened\n")
    assert marker(promoted)["route"] == "issue"
    assert not list((tmp_path / "Feedback" / "Feedback-Drafts").glob("*-comment-*"))


def test_a_label_outside_the_lifecycle_set_does_not_stop_a_comment(tmp_path):
    config, _draft = post_setup(tmp_path)
    env, log = url_env(tmp_path, scenario=match_scenario(tmp_path, [{**OPEN_42, "labels": ["bug", "enhancement"]}]))
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"Feedback posted to {REPO} as a comment on #42 \"Queue listing\" (open): {COMMENT_URL}\n"
    assert posts(log) == (0, 1)


def test_the_first_candidate_that_can_take_a_comment_is_the_target(tmp_path):
    # #41 is newer, so it ranks first, and it is closed. #42 is open and clean.
    rows = [{"number": 41, "title": "Queue listing broke", "state": "CLOSED", "url": "u41", "age_days": 3, "labels": ["resolved"]}, OPEN_42]
    config, _draft = post_setup(tmp_path)
    env, log = url_env(tmp_path, scenario=match_scenario(tmp_path, rows))
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"Feedback posted to {REPO} as a comment on #42 \"Queue listing\" (open): {COMMENT_URL}\n"
    assert posts(log) == (0, 1)
    assert [argv[2] for argv in view_calls(log)] == ["42"]
    [promoted] = promoted_files(tmp_path)
    assert not promoted.read_text(encoding="utf-8").startswith("Possibly related")


def test_a_key_match_on_a_different_subject_gets_a_new_issue_that_names_it(tmp_path):
    # #42 matches the draft's file name, so its key score is 3, but its title shares no subject with the
    # draft title. It gets no live read and no comment, and the new issue names it.
    rows = [{"number": 42, "title": "dispatch_preflight overlap --running none form", "state": "OPEN", "url": "u42", "age_days": 200}]
    config, _draft = post_setup(tmp_path)
    env, log = url_env(tmp_path, scenario=match_scenario(tmp_path, rows))
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"Feedback posted to {REPO} as a new issue: {ISSUE_URL} (related to #42, which is open)\n"
    assert posts(log) == (1, 0)
    assert view_calls(log) == []
    [promoted] = promoted_files(tmp_path)
    assert promoted.read_text(encoding="utf-8").startswith("Possibly related to #42 (open).\n\n")
    assert not list((tmp_path / "Feedback" / "Feedback-Drafts").glob("*-comment-*"))


@pytest.mark.parametrize("draft_title,candidate_title,keys,expected", [
    ("List skips a queued draft", "Queue listing", ["feedback_drafts.py"], True),
    ("Draft listing skips queued drafts", "Queue listing", ["feedback_drafts.py"], True),
    ("dispatch_preflight siblings misses a second path on one Files Modified line",
     "dispatch_preflight overlap --running none form", ["dispatch_preflight.py"], False),
    ("Add one session to a built plan", "build_plan tool needs the whole spec object", ["build_plan"], False),
], ids=["same-subject", "same-subject-plural", "shared-file-only", "shared-tool-only"])
def test_shares_subject_ignores_the_words_of_the_matched_keys(draft_title, candidate_title, keys, expected):
    assert fp.shares_subject(draft_title, candidate_title, keys) is expected


def test_a_match_on_title_words_alone_never_takes_a_comment(tmp_path):
    # An open, clean, recent issue matched only by the title query: 1 for the key plus 2 for its age clears
    # the ranking threshold, and it still gets no comment and no related line.
    rows = [{"number": 50, "title": "List skips queued things", "state": "OPEN", "url": "u50", "age_days": 3}]
    config, _draft = post_setup(tmp_path)
    env, log = url_env(tmp_path, scenario=match_scenario(tmp_path, rows, match="List skips queued in:"))
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"Feedback posted to {REPO} as a new issue: {ISSUE_URL}\n"
    assert posts(log) == (1, 0) and view_calls(log) == []
    [promoted] = promoted_files(tmp_path)
    assert promoted.read_text(encoding="utf-8").startswith("### What happened\n")


def test_a_retry_keeps_one_related_line(tmp_path):
    config, _draft = post_setup(tmp_path)
    env, log = url_env(tmp_path, scenario=match_scenario(tmp_path, [CLOSED_42]), FAKE_GH_EXIT="1", FAKE_GH_MATCH="issue create")
    assert post(config, env).returncode == 3
    del env["FAKE_GH_EXIT"], env["FAKE_GH_MATCH"]
    retry = post(config, env)
    assert retry.returncode == 0, retry.stdout + retry.stderr
    [promoted] = promoted_files(tmp_path)
    assert promoted.read_text(encoding="utf-8").count("Possibly related to #42") == 1
    assert posts(log) == (2, 0)


@pytest.mark.parametrize("row,target,related", [
    (OPEN_42, 42, None),
    (CLOSED_42, None, {"number": 42, "state": "CLOSED"}),
], ids=["open", "closed"])
def test_scan_reports_the_comment_target(tmp_path, row, target, related):
    title, body, _keys, _title_query = FILE_NAME
    env, log = gh_env(tmp_path, scenario=match_scenario(tmp_path, [row]))
    _code, report, _elapsed = scan(tmp_path, title, body, env)
    assert (report["comment_target"], report["related"]) == (target, related)
    assert posts(log) == (0, 0)
    argv = [sys.executable, "-B", str(SCRIPT), "scan", "--config", str(write_config(tmp_path)),
            "--draft", str(write_draft(tmp_path, title, body))]
    text = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", env=env, cwd=tmp_path, timeout=120, check=False)
    assert text.stdout.splitlines()[-1] == ("Comment target: #42" if target else "Comment target: none")


@pytest.mark.parametrize("consent,sentence", [
    ((), fp.UNATTENDED_PROVENANCE),
    (("--consent", "none"), fp.UNATTENDED_PROVENANCE),
    (("--consent", "card"), fp.CARD_PROVENANCE),
    (("--consent", "review"), fp.feedback_drafts.PROVENANCE_LINE),
], ids=["default", "none", "card", "review"])
def test_the_consent_value_picks_the_provenance_sentence(tmp_path, consent, sentence):
    config, _draft = post_setup(tmp_path)
    env, _log = url_env(tmp_path)
    assert post(config, env, DRAFT_ID, *consent).returncode == 0
    [promoted] = promoted_files(tmp_path)
    text = promoted.read_text(encoding="utf-8")
    assert text.rstrip("\n").endswith(sentence)
    assert sum(text.count(line) for line in fp.PROVENANCE_BY_CONSENT.values()) == 1


def test_a_self_duplicate_posts_nothing(tmp_path):
    title = "List skips a queued draft"
    scenario = tmp_path / "rows.json"
    scenario.write_text(json.dumps({"responses": [{"match": "feedback_drafts.py in:", "rows": [
        {"number": 13, "title": title, "state": "OPEN", "url": "u13", "age_minutes": 2}]}]}), encoding="utf-8")
    config, _draft = post_setup(tmp_path, title=title)
    env, log = url_env(tmp_path, scenario=str(scenario))
    result = post(config, env)
    assert result.returncode == 3
    assert result.stdout == "This draft appears to have already been posted as #13 — check before posting again.\n"
    assert posts(log) == (0, 0)
    assert not list((tmp_path / "Feedback" / "Feedback-Drafts").glob("*.posted"))


@pytest.mark.parametrize("ranked", [False, True], ids=["issue-route", "comment-route"])
def test_a_privacy_block_posts_nothing(tmp_path, ranked):
    scenario = tmp_path / "rows.json"
    rows = [{"number": 42, "title": "Queue listing", "state": "OPEN", "url": "u42", "age_days": 200}] if ranked else []
    scenario.write_text(json.dumps({"responses": [{"match": "feedback_drafts.py in:", "rows": rows}]}), encoding="utf-8")
    config, _draft = post_setup(tmp_path, body=POST_BODY + "\nReach me at someone@example.com for details.\n")
    env, log = url_env(tmp_path, scenario=str(scenario))
    before = posts(log)
    result = post(config, env)
    assert result.returncode == 3
    assert posts(log) == before == (0, 0)
    posted = next((tmp_path / "Feedback" / "Feedback-Drafts").glob("*-comment-42-*.md")) if ranked else promoted_files(tmp_path)[0]
    line = result.stdout.strip()
    prefix = "Feedback draft kept, not posted: the privacy check blocked it (email at line "
    assert line.startswith(prefix) and line.endswith(f"). Draft: {posted.resolve()}"), line
    assert "someone@example.com" not in result.stdout
    assert posted.is_file() and not list((tmp_path / "Feedback" / "Feedback-Drafts").glob("*.posted"))
    # The block is recorded beside the promoted draft on both routes, and the record holds no draft text.
    [promoted] = promoted_files(tmp_path)
    [sidecar] = (tmp_path / "Feedback" / "Feedback-Drafts").glob("*.blocked")
    assert sidecar.name == promoted.name + ".blocked"
    fields = dict(row.split(": ", 1) for row in sidecar.read_text(encoding="utf-8").splitlines())
    assert (fields["class"], fields["route"]) == ("email", "comment" if ranked else "issue")
    assert line == f"{prefix}{fields['line']}). Draft: {posted.resolve()}"
    assert fp.feedback_drafts.count_blocked(tmp_path / "Feedback" / "Feedback-Drafts") == 1


def test_a_failed_post_keeps_the_draft_unmarked(tmp_path):
    config, _draft = post_setup(tmp_path)
    env, log = url_env(tmp_path, FAKE_GH_EXIT="1", FAKE_GH_MATCH="issue create")
    result = post(config, env)
    assert result.returncode == 3
    [promoted] = promoted_files(tmp_path)
    assert result.stdout == f"Feedback draft kept, not posted: the post to {REPO} failed. Draft: {promoted.resolve()}\n"
    assert posts(log) == (1, 0)
    assert not list((tmp_path / "Feedback" / "Feedback-Drafts").glob("*.posted"))


def test_a_timed_out_post_exits_3_and_says_the_issue_may_exist(tmp_path):
    config, _draft = post_setup(tmp_path)
    env, log = gh_env(tmp_path, route="override", FAKE_GH_SLEEP="30", FAKE_GH_MATCH="issue create")
    result = post(config, env)
    assert result.returncode == 3
    [promoted] = promoted_files(tmp_path)
    assert result.stdout == (f"Feedback draft kept, not confirmed: the post to {REPO} timed out, so the issue may exist. "
                             f"Check {REPO} before posting again. Draft: {promoted.resolve()}\n")
    assert posts(log) == (1, 0)
    assert not list((tmp_path / "Feedback" / "Feedback-Drafts").glob("*.posted"))


def test_a_title_with_quotes_reaches_gh_as_one_argument(tmp_path):
    title = "Title with \"double\" and 'single' quotes & a | pipe"
    config, _draft = post_setup(tmp_path, title=title)
    env, log = url_env(tmp_path)
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    [create] = [argv for argv in read_calls(log) if argv[:2] == ["issue", "create"]]
    at = create.index("--title")
    assert create[at + 1] == title
    assert create[at + 2] == "--body-file" and len(create) == 10


def test_posting_off_makes_no_gh_call_and_writes_nothing(tmp_path):
    config, draft = post_setup(tmp_path, enabled="false")
    before = draft.read_bytes()
    env, log = gh_env(tmp_path)
    result = post(config, env)
    assert result.returncode == 4
    assert result.stdout == ("Posting is off: config.yaml does not set feedback.enabled to true. "
                             "The draft was saved and nothing was posted.\n")
    assert count_calls(log) == 0
    assert draft.read_bytes() == before and promoted_files(tmp_path) == []


def test_gh_not_found_keeps_the_draft(tmp_path):
    config, _draft = post_setup(tmp_path)
    env, log = gh_env(tmp_path, route="none")
    result = post(config, env)
    assert result.returncode == 3
    [promoted] = promoted_files(tmp_path)
    assert result.stdout == f"Feedback draft kept, not posted: gh was not found. Draft: {promoted.resolve()}\n"
    assert count_calls(log) == 0


def test_gh_not_signed_in_keeps_the_draft(tmp_path):
    config, _draft = post_setup(tmp_path)
    env, log = gh_env(tmp_path, route="override", FAKE_GH_EXIT="1", FAKE_GH_MATCH="auth status")
    result = post(config, env)
    assert result.returncode == 3
    [promoted] = promoted_files(tmp_path)
    assert result.stdout == f"Feedback draft kept, not posted: gh is not signed in. Draft: {promoted.resolve()}\n"
    assert posts(log) == (0, 0) and count_calls(log, "issue", "list") == 0


@pytest.mark.parametrize("draft_id,status,reason", [("d-9999", "queued", "unknown"), (DRAFT_ID, "discarded", "discarded")],
                         ids=["unknown-id", "not-queued"])
def test_no_queued_draft_exits_2(tmp_path, draft_id, status, reason):
    config, _draft = post_setup(tmp_path, status=status)
    env, log = gh_env(tmp_path)
    result = post(config, env, draft_id=draft_id)
    assert result.returncode == 2
    assert f"no queued draft with id {draft_id} ({reason})" in result.stderr
    assert count_calls(log) == 0 and promoted_files(tmp_path) == []
    # The review card clears itself on this result.
    card_code, card_mark = card_pin("EXIT_NO_DRAFT", "NO_DRAFT_MARK")
    assert result.returncode == card_code and card_mark in last_stderr_line(result)


def test_a_lesson_posts_with_the_enhancement_label_and_no_url(tmp_path):
    config, _draft = post_setup(tmp_path, kind="lesson")
    env, log = gh_env(tmp_path, route="override")
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"Feedback posted to {REPO} as a new issue: (gh printed no URL)\n"
    [create] = [argv for argv in read_calls(log) if argv[:2] == ["issue", "create"]]
    assert create[-2:] == ["--label", "enhancement"]
    [promoted] = promoted_files(tmp_path)
    assert marker(promoted)["url"] == "" and marker(promoted)["route"] == "issue"


def today_name(suffix: str) -> str:
    return f"{time.strftime('%Y-%m-%d', time.gmtime())}-{suffix}"


@pytest.mark.parametrize("title,found", [("Crash under C:\\Users\\someone\\project", "absolute-path"),
                                         ("Mail someone@example.com about it", "email")], ids=["absolute-path", "email"])
def test_a_title_that_fails_the_privacy_rules_posts_nothing(tmp_path, title, found):
    config, _draft = post_setup(tmp_path, title=title)
    env, log = url_env(tmp_path)
    result = post(config, env)
    assert result.returncode == 3
    [promoted] = promoted_files(tmp_path)
    assert result.stdout == f"Feedback draft kept, not posted: the privacy check blocked its title ({found}). Draft: {promoted.resolve()}\n"
    assert posts(log) == (0, 0)


def test_a_marker_that_cannot_be_written_still_exits_0(tmp_path):
    config, _draft = post_setup(tmp_path)
    blocker = tmp_path / "Feedback" / "Feedback-Drafts" / today_name("bug-list-skips-a-queued-draft.md.posted")
    blocker.mkdir()
    env, log = url_env(tmp_path)
    result = post(config, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == (f"Feedback posted to {REPO} as a new issue: {ISSUE_URL}\n"
                             f"The draft could not be marked posted: the .posted marker could not be written at {blocker.resolve()}\n")
    assert posts(log) == (1, 0)


def test_the_posted_body_says_no_person_reviewed_it(tmp_path):
    config, _draft = post_setup(tmp_path)
    env, _log = url_env(tmp_path)
    assert post(config, env).returncode == 0
    [promoted] = promoted_files(tmp_path)
    text = promoted.read_text(encoding="utf-8")
    assert "approved by the user" not in text
    assert text.rstrip("\n").endswith(fp.UNATTENDED_PROVENANCE)


@pytest.mark.parametrize("case", ["error", "budget"])
def test_a_recency_listing_that_did_not_return_makes_the_scan_incomplete(monkeypatch, case):
    clock = {"t": 0.0}

    def run_query(argv):
        if "--search" in argv:
            clock["t"] += 100.0 if case == "budget" else 0.0
            return "ok", []
        return "error", []

    monkeypatch.setattr(fp, "_run_query", run_query)
    monkeypatch.setattr(fp, "_budget", lambda: 30.0)
    monkeypatch.setattr(fp, "time", SimpleNamespace(monotonic=lambda: clock["t"]))
    report = fp.run_scan({"argv": ["gh"]}, REPO, "Planwise menu", "It is slow.\n")
    assert [(q["kind"], q["status"]) for q in report["queries"]] == [("title", "ok"), ("recency", "error" if case == "error" else "not-run")]
    assert report["budget_stopped"] is (case == "budget")
    assert report["outcome"] == "INCOMPLETE"
    assert report["caveat"] == "Duplicate scan was incomplete — 1 of 2 searches returned. Candidates below may be missing entries."
    assert report["ranked"] == []


def test_a_batch_shim_alone_counts_as_gh_not_found(tmp_path):
    config, _draft = post_setup(tmp_path)
    env, log = gh_env(tmp_path, route="none")
    shims = tmp_path / "shims"
    shims.mkdir()
    for name in ("gh.cmd", "gh.bat"):
        shutil.copyfile(FAKE_DIR / "gh.cmd", shims / name)
    env["PATH"] = str(shims) + os.pathsep + env["PATH"]
    env["FEEDBACK_POST_GH_CANDIDATES"] = os.pathsep.join(str(shims / name) for name in ("gh.cmd", "gh.bat"))
    result = post(config, env)
    assert result.returncode == 3
    [promoted] = promoted_files(tmp_path)
    assert result.stdout == f"Feedback draft kept, not posted: gh was not found. Draft: {promoted.resolve()}\n"
    assert count_calls(log) == 0


def test_a_kept_draft_is_posted_by_a_retry(tmp_path):
    config, draft = post_setup(tmp_path)
    env, log = url_env(tmp_path, FAKE_GH_EXIT="1", FAKE_GH_MATCH="auth status")
    first = post(config, env)
    assert first.returncode == 3 and "gh is not signed in" in first.stdout
    assert "status: promoted" in draft.read_text(encoding="utf-8")
    del env["FAKE_GH_EXIT"], env["FAKE_GH_MATCH"]
    second = post(config, env)
    assert second.returncode == 0, second.stdout + second.stderr
    assert posts(log) == (1, 0)
    [promoted] = promoted_files(tmp_path)
    assert marker(promoted)["route"] == "issue"
    # Once the sidecar records the post, the id no longer resolves, and nothing posts twice.
    third = post(config, env)
    assert third.returncode == 2 and f"no queued draft with id {DRAFT_ID} (promoted)" in third.stderr
    assert posts(log) == (1, 0)


def test_a_comment_draft_that_cannot_be_written_keeps_the_draft(tmp_path):
    scenario = tmp_path / "rows.json"
    scenario.write_text(json.dumps({"responses": [{"match": "feedback_drafts.py in:", "rows": [
        {"number": 42, "title": "Queue listing", "state": "OPEN", "url": "u42", "age_days": 200}]}]}), encoding="utf-8")
    config, _draft = post_setup(tmp_path)
    (tmp_path / "Feedback" / "Feedback-Drafts" / today_name("comment-42-bug-list-skips-a-queued-draft.md")).mkdir()
    env, log = url_env(tmp_path, scenario=str(scenario))
    result = post(config, env)
    assert result.returncode == 3
    [promoted] = promoted_files(tmp_path)
    assert result.stdout == f"Feedback draft kept, not posted: the comment draft could not be written. Draft: {promoted.resolve()}\n"
    assert posts(log) == (0, 0)


def test_a_one_term_title_is_searched_once(tmp_path):
    env, log = gh_env(tmp_path)
    _code, report, _elapsed = scan(tmp_path, "Planwise menu", "It is slow.\n", env)
    assert [(q["query"], q["kind"]) for q in report["queries"]] == [("menu", "title"), ("", "recency")]
    assert count_calls(log, "issue", "list") == 2


@pytest.mark.parametrize("line,expected", [
    # "No" fails the 3-character minimum, and the quotes come off 'yaml'.
    ("ModuleNotFoundError: No module named 'yaml'", ["ModuleNotFoundError: module named yaml"]),
    # The parenthesised fragment goes and ":" fails the pattern, so 1 word survives, under the minimum of 2.
    ("Traceback (most recent call last):", []),
    # "a" fails the 3-character minimum.
    ("fatal: not a git repository", ["fatal: not git repository"]),
    # "ok" fails the 3-character minimum, so 1 word survives.
    ("Error: ok", []),
], ids=["module-not-found", "traceback", "fatal", "one-survivor"])
def test_tier_c_drops_failing_words_and_needs_two_survivors(line, expected):
    body = f"The run stopped:\n\n```\n{line}\n```\n"
    assert [key for key, _score, _at, _tier in fp._tier_c(body, 0)] == expected


def test_a_retry_is_matched_to_its_own_draft_not_its_title(tmp_path):
    scenario = tmp_path / "rows.json"
    scenario.write_text(json.dumps({"responses": [{"match": "feedback_drafts.py in:", "rows": [
        {"number": 42, "title": "Queue listing", "state": "OPEN", "url": "u42", "age_days": 200}]}]}), encoding="utf-8")
    config, first_draft = post_setup(tmp_path)
    second_draft = first_draft.with_name("2026-01-02-draft-bug-example.md")
    second_draft.write_bytes(first_draft.read_bytes().replace(f"draft_id: {DRAFT_ID}".encode(), b"draft_id: d-0002"))
    env, log = url_env(tmp_path, scenario=str(scenario))
    assert post(config, env).returncode == 0
    assert posts(log) == (0, 1)
    # The second draft, with the same title, is kept once and then retried.
    env["FAKE_GH_EXIT"], env["FAKE_GH_MATCH"] = "1", "auth status"
    assert post(config, env, draft_id="d-0002").returncode == 3
    del env["FAKE_GH_EXIT"], env["FAKE_GH_MATCH"]
    retry = post(config, env, draft_id="d-0002")
    assert retry.returncode == 0, retry.stdout + retry.stderr
    assert posts(log) == (0, 2)
    assert len(list((tmp_path / "Feedback" / "Feedback-Drafts").glob("*-comment-42-*.md.posted"))) == 2


def test_a_missing_config_exits_1(tmp_path):
    env, log = gh_env(tmp_path)
    result = post(tmp_path / "absent.yaml", env)
    assert result.returncode == 1
    assert count_calls(log) == 0
    # The review card runs the script again with another config on this result, so nothing may be
    # written before it and the words must match.
    card_code, card_mark = card_pin("EXIT_FAILED", "CONFIG_GONE_MARK")
    assert result.returncode == card_code and card_mark in last_stderr_line(result)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bin", "empty"]


# ---------------------------------------------------------------- the card
#
# The card is local-only and read-only. Every case hashes the Feedback folder before and after, and runs
# with the fake gh resolvable, so a call would show in its log.

CARD_DRAFTS = (
    # (file name, draft_id, kind, title, age in days, status, body)
    ("2026-01-01-draft-bug-list-skips.md", "d-0001", "bug", "List skips a queued draft", 2, "queued",
     "### What happened\n\nThe list command skipped a draft.\n"),
    ("2026-01-02-draft-lesson-name-the-key.md", "d-0002", "lesson", "Name the key the class uses", 5, "queued",
     "### Lesson\n\nCount by the key citers use.\n"),
    ("2026-01-03-draft-idea-card-preview.md", "d-0003", "idea", "Preview the card body", 0, "queued",
     "### Idea\n\nShow the body in the card.\n"),
)


def card_setup(tmp_path: Path, drafts=CARD_DRAFTS, posting: "str | None" = "true") -> "tuple[Path, Path]":
    """A config and a Feedback folder of model drafts. `posting` None leaves `feedback.enabled` out."""
    config = tmp_path / "config.yaml"
    enabled = f"  enabled: {posting}\n" if posting is not None else ""
    config.write_bytes(f"feedback:\n{enabled}  repo: {REPO}\n".encode())
    folder = tmp_path / "Feedback" / "Feedback-Drafts"
    folder.mkdir(parents=True, exist_ok=True)
    for name, draft_id, kind, title, days, status, body in drafts:
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days * 86400 - 60))
        (folder / name).write_bytes((f"---\ndraft_id: {draft_id}\ncreated_at: {created}\ndrafted_by: model\nkind: {kind}\n"
                                     f"title: {title}\nstatus: {status}\n---\n\n{body}").encode())
    return config, folder


def folder_hashes(folder: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def card(config: Path, env: dict, *extra: str) -> "subprocess.CompletedProcess":
    argv = [sys.executable, "-B", str(SCRIPT), "card", "--config", str(config), *extra]
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", env=env, cwd=config.parent, timeout=120, check=False)


def test_card_lists_three_drafts_the_state_and_each_body(tmp_path):
    config, folder = card_setup(tmp_path)
    before = folder_hashes(folder)
    env, log = gh_env(tmp_path, route="override")
    result = card(config, env)
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"Queued drafts (3) in {folder}:\n"
        "d-0001\tbug\tList skips a queued draft\t2d\n"
        "d-0002\tlesson\tName the key the class uses\t5d\n"
        "d-0003\tidea\tPreview the card body\t0d\n"
        "Posting state: enabled\n"
        "Target repository: example-owner/example-repo\n"
        "\n--- draft d-0001: List skips a queued draft ---\n### What happened\n\nThe list command skipped a draft.\n"
        "\n--- draft d-0002: Name the key the class uses ---\n### Lesson\n\nCount by the key citers use.\n"
        "\n--- draft d-0003: Preview the card body ---\n### Idea\n\nShow the body in the card.\n")
    assert folder_hashes(folder) == before and count_calls(log) == 0


def test_card_draft_id_narrows_to_one_draft(tmp_path):
    config, folder = card_setup(tmp_path)
    env, log = gh_env(tmp_path, route="override")
    result = card(config, env, "--draft-id", "d-0002")
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"Queued drafts (1) in {folder}:\n"
        "d-0002\tlesson\tName the key the class uses\t5d\n"
        "Posting state: enabled\n"
        "Target repository: example-owner/example-repo\n"
        "\n--- draft d-0002: Name the key the class uses ---\n### Lesson\n\nCount by the key citers use.\n")
    assert count_calls(log) == 0


def test_card_prints_the_default_repository_for_an_invalid_value(tmp_path):
    config, _folder = card_setup(tmp_path)
    config.write_bytes(b"feedback:\n  enabled: true\n  repo: not a repo\n")
    env, log = gh_env(tmp_path, route="override")
    result = card(config, env)
    assert result.returncode == 0, result.stderr
    assert "\nTarget repository: gabgoss/planwise\n" in result.stdout
    assert "not a repo" not in result.stdout
    assert count_calls(log) == 0


@pytest.mark.parametrize("draft_id", ["d-9999", "d-0004"], ids=["unknown-id", "expired-id"])
def test_card_unknown_id_prints_one_line_and_exits_2(tmp_path, draft_id):
    old = ("2025-01-01-draft-bug-old.md", "d-0004", "bug", "An old draft", 60, "queued", "Old.\n")
    config, folder = card_setup(tmp_path, drafts=CARD_DRAFTS + (old,))
    before = folder_hashes(folder)
    env, log = gh_env(tmp_path, route="override")
    result = card(config, env, "--draft-id", draft_id)
    assert result.returncode == 2
    assert result.stdout == f"No queued draft with id {draft_id}.\n"
    assert folder_hashes(folder) == before and count_calls(log) == 0


def test_card_omits_an_expired_draft_and_leaves_its_bytes(tmp_path):
    old = ("2025-01-01-draft-bug-old.md", "d-0004", "bug", "An old draft", 31, "queued", "Old body.\n")
    config, folder = card_setup(tmp_path, drafts=CARD_DRAFTS + (old,))
    expired = folder / old[0]
    before = folder_hashes(folder)
    env, log = gh_env(tmp_path, route="override")
    result = card(config, env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(f"Queued drafts (3) in {folder}:\n")
    assert "d-0004" not in result.stdout and "Old body." not in result.stdout
    assert folder_hashes(folder) == before and "status: queued" in expired.read_text(encoding="utf-8")
    # --all lists it as expired, computed in memory, and still writes nothing.
    listed = card(config, env, "--all")
    assert listed.returncode == 0, listed.stderr
    assert "Other drafts (1):\nd-0004\texpired\tbug\tAn old draft\t31d\n" in listed.stdout
    assert "Old body." not in listed.stdout
    assert folder_hashes(folder) == before and count_calls(log) == 0


@pytest.mark.parametrize("posting,state", [("true", "enabled"), ("false", "disabled"), (None, "absent")])
def test_card_prints_the_posting_state_line(tmp_path, posting, state):
    config, _folder = card_setup(tmp_path, posting=posting)
    config_before = config.read_bytes()
    env, log = gh_env(tmp_path, route="override")
    result = card(config, env)
    assert result.returncode == 0, result.stderr
    assert f"\nPosting state: {state}\n" in result.stdout
    assert config.read_bytes() == config_before and count_calls(log) == 0


def test_card_makes_no_gh_call_and_no_subprocess(tmp_path, monkeypatch, capsys):
    config, folder = card_setup(tmp_path)
    before = folder_hashes(folder)
    # Control: the fake's log records a call when one is made, so the zero counts in the other card cases can see a call.
    env, log = gh_env(tmp_path, route="override")
    subprocess.run([sys.executable, "-B", str(FAKE), "--version"], env=env, capture_output=True, timeout=60, check=False)
    assert count_calls(log, "--version") == 1

    def refuse(*_args, **_kwargs):
        raise AssertionError("the card ran a subprocess")

    monkeypatch.setattr(fp.subprocess, "run", refuse)
    monkeypatch.setattr(fp, "resolve_gh", refuse)
    assert fp.main(["card", "--config", str(config)]) == 0
    assert capsys.readouterr().out.count("\n--- draft ") == 3
    assert folder_hashes(folder) == before
