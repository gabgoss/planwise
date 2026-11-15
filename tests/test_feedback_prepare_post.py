"""Tests for the `prepare-post` privacy gate in scripts/feedback_drafts.py.

Every draft is built under pytest's tmp_path. Every private-looking value is invented.
"""

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugins" / "planwise" / "scripts"))
import feedback_drafts as fd

REPO = "gabgoss/planwise"
MARKER = "<!-- planwise:scan-annotation — local annotation, not part of the issue body. Strip before posting. -->"
ANNOTATION = (
    MARKER + "\n\n### Possible duplicates\n\nscan unavailable\n\n"
    "| # | Issue | State | Age | Title | Matched on |\n|---|---|---|---|---|---|\n"
    "| 1 | #12 | OPEN | 3d | Example | `query` |\n\nConfirm none of the above already covers this report before filing it.\n"
)
ENVIRONMENT = "### Environment\n\n- planwise version: 1.0.0\n- Subcommand involved: /planwise feedback\n- OS / shell: Windows 11 / Git Bash\n"


def body(happened: str = "It broke.") -> str:
    """A bug body. Line 3 holds `happened`."""
    return (
        "### What happened\n\n" + happened + "\n\n"
        "### What I expected\n\nIt works.\n\n"
        "### Steps to reproduce\n\nRun it.\n\n" + ENVIRONMENT
    )


def write(tmp_path: Path, text: str, name: str = "2026-01-01-bug-example.md") -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path


def prep(path: Path, include_environment: bool = True):
    return fd.prepare_post(path, include_environment=include_environment, repo=REPO)


# ---------------------------------------------------------------- one positive and one control per class

# (class, sentence template, instance). The control is the same sentence with the instance removed.
CLASS_CASES = [
    ("absolute-path", "The log sits in {} today.", "C:\\Users\\example\\repo\\out.txt"),
    ("absolute-path", "The log sits in {} today.", "C:/Users/example/repo/out.txt"),
    ("absolute-path", "The log sits in {} today.", "/home/example/repo/out.txt"),
    ("absolute-path", "The log sits in {} today.", "~/example/out.txt"),
    ("absolute-path", "The log sits in {} today.", "\\\\fileserver\\share\\out.txt"),
    ("email", "Write to {} about it.", "someone@example.com"),
    ("git-remote", "The remote is {} for this.", "git@example.org:someone/thing.git"),
    ("git-remote", "The remote is {} for this.", "https://github.com/someone-else/other-repo"),
    ("git-remote", "The remote is {} for this.", "https://example.org/someone/thing.git"),
    ("git-remote", "The remote is {} for this.", "ssh://example.org/thing"),
    ("handle", "Ask {} about it.", "@invented-person"),
]


@pytest.mark.parametrize(("expected", "sentence", "instance"), CLASS_CASES)
def test_one_instance_is_blocked_with_its_class_and_line(tmp_path, expected, sentence, instance):
    verdict, found, line, _data = prep(write(tmp_path, body(sentence.format(instance))))
    assert (verdict, found, line) == ("blocked", expected, 3)


@pytest.mark.parametrize(("expected", "sentence", "instance"), CLASS_CASES)
def test_must_fail_control_without_the_instance_reads_clean(tmp_path, expected, sentence, instance):
    assert prep(write(tmp_path, body(sentence.format(""))))[:3] == ("clean", "", 0)


# ---------------------------------------------------------------- false-positive controls

@pytest.mark.parametrize(
    "value",
    [
        "Run `/planwise feedback --drafts` to see it.",
        "See references/feedback-submission.md for the rule.",
        f"Same as https://github.com/{REPO}/issues/1 reported.",
        "```\nplain words in a fenced block\nmore plain words\n```",
        "Read scripts/feedback_drafts.py and handlers/run.md first.",
    ],
)
def test_false_positive_control_reads_clean(tmp_path, value):
    assert prep(write(tmp_path, body(value)))[:3] == ("clean", "", 0)


def test_environment_block_with_version_and_os_shell_reads_clean(tmp_path):
    path = write(tmp_path, "### What happened\n\nIt broke.\n\n" + ENVIRONMENT)
    assert prep(path)[:3] == ("clean", "", 0)
    assert b"### Environment" in path.read_bytes()


def test_email_is_not_reported_as_a_handle(tmp_path):
    assert prep(write(tmp_path, body("Mail someone@example.com now.")))[1] == "email"


# ---------------------------------------------------------------- byte identity and the cut

@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_returned_bytes_equal_the_file_and_the_annotation_is_gone(tmp_path, eol):
    path = write(tmp_path, (body() + "\n" + ANNOTATION).replace("\n", eol))
    verdict, _found, _line, data = prep(path)
    assert verdict == "clean"
    assert data == path.read_bytes()
    assert b"planwise:scan-annotation" not in data
    assert b"Possible duplicates" not in data
    assert data == (body() + "\n").replace("\n", eol).encode("utf-8")


def test_include_environment_false_removes_the_environment_section(tmp_path):
    path = write(tmp_path, body() + "\n" + ANNOTATION)
    _verdict, _found, _line, data = prep(path, include_environment=False)
    assert b"### Environment" not in data
    assert b"planwise version" not in data
    assert b"### Steps to reproduce" in data and b"Run it." in data
    assert data == path.read_bytes()


def test_include_environment_true_keeps_the_environment_section(tmp_path):
    path = write(tmp_path, body())
    _verdict, _found, _line, data = prep(path, include_environment=True)
    assert b"### Environment" in data and b"OS / shell" in data


# ---------------------------------------------------------------- comment-shaped draft

LEAD_IN = "Filed with `/planwise feedback` as a comment rather than a new issue — this looked like the same subject as this thread. **A title**\n\n"


def test_comment_shaped_draft_with_a_bad_value_is_blocked(tmp_path):
    path = write(tmp_path, LEAD_IN + body("Ask @invented-person about it."), "2026-01-01-comment-12-example.md")
    assert prep(path)[:3] == ("blocked", "handle", 5)


def test_comment_shaped_draft_without_the_value_reads_clean(tmp_path):
    path = write(tmp_path, LEAD_IN + body("It broke."), "2026-01-01-comment-12-example.md")
    assert prep(path)[:3] == ("clean", "", 0)


# ---------------------------------------------------------------- blocked and repeated states

def test_blocked_run_leaves_the_draft_in_its_cut_state(tmp_path):
    path = write(tmp_path, body("Write to someone@example.com.") + "\n" + ANNOTATION)
    verdict, found, _line, data = prep(path, include_environment=False)
    assert (verdict, found) == ("blocked", "email")
    assert path.read_bytes() == data
    assert b"planwise:scan-annotation" not in data
    assert b"### Environment" not in data


def test_second_run_on_a_cut_clean_draft_changes_nothing(tmp_path):
    path = write(tmp_path, body() + "\n" + ANNOTATION)
    first = prep(path, include_environment=False)
    before = path.read_bytes()
    second = prep(path, include_environment=False)
    assert first[:3] == second[:3] == ("clean", "", 0)
    assert path.read_bytes() == before == second[3]


def test_draft_with_no_annotation_reads_clean_and_is_unchanged(tmp_path):
    original = body().encode("utf-8")
    path = write(tmp_path, body())
    assert prep(path)[:3] == ("clean", "", 0)
    assert path.read_bytes() == original


# ---------------------------------------------------------------- the command line

SCRIPT = HERE.parent / "plugins" / "planwise" / "scripts" / "feedback_drafts.py"


def cli(*argv):
    result = subprocess.run([sys.executable, "-B", str(SCRIPT), "prepare-post", *argv], capture_output=True, text=True, check=False)
    return result.returncode, result.stdout, result.stderr


def config(tmp_path: Path, extra: str = "") -> Path:
    path = tmp_path / "config.yaml"
    path.write_bytes(("feedback:\n  repo: " + REPO + "\n" + extra).encode("utf-8"))
    return path


def test_cli_clean_exits_0(tmp_path):
    code, out, _err = cli("--config", str(config(tmp_path)), "--draft", str(write(tmp_path, body())))
    assert (code, out.strip()) == (0, "clean")


def test_cli_blocked_exits_3_and_never_prints_the_value(tmp_path):
    draft = write(tmp_path, body("Write to someone@example.com."))
    code, out, err = cli("--config", str(config(tmp_path)), "--draft", str(draft))
    assert (code, out.strip()) == (3, "blocked: email at line 3")
    assert "someone" not in out + err


@pytest.mark.parametrize("missing", ["config", "draft", "argument"])
def test_cli_usage_or_read_problem_exits_1(tmp_path, missing):
    cfg, draft = config(tmp_path), write(tmp_path, body())
    argv = {
        "config": ("--config", str(tmp_path / "none.yaml"), "--draft", str(draft)),
        "draft": ("--config", str(cfg), "--draft", str(tmp_path / "none.md")),
        "argument": ("--config", str(cfg)),
    }[missing]
    code, out, _err = cli(*argv)
    assert (code, out) == (1, "")


def test_cli_reads_include_environment_from_the_config(tmp_path):
    draft = write(tmp_path, body())
    code, _out, _err = cli("--config", str(config(tmp_path, "  include_environment: false\n")), "--draft", str(draft))
    assert code == 0
    assert b"### Environment" not in draft.read_bytes()


def test_read_post_settings_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_bytes(b"project:\n  name: demo\n")
    assert fd.read_post_settings(path) == (True, "gabgoss/planwise")
    path.write_bytes(b"feedback:\n  include_environment: false   # note\n  repo: not a repo\n")
    assert fd.read_post_settings(path) == (False, "gabgoss/planwise")


def test_cli_unknown_flag_is_an_argparse_usage_error_exit_2(tmp_path):
    """Review finding CR9: argparse owns an unknown flag, and it exits 2."""
    code, out, _err = cli("--config", str(config(tmp_path)), "--draft", str(write(tmp_path, body())), "--bogus")
    assert (code, out) == (2, "")


# ---------------------------------------------------------------- review regressions


def line_class(value: str, tmp_path: Path) -> "tuple[str, str]":
    """The verdict and class for a body whose line 3 holds `value`."""
    return prep(write(tmp_path, body(value)))[:2]


@pytest.mark.parametrize(
    "value",
    [
        "The renderer wrote {project}/scripts/foo.py for it.",
        "Match **/scripts/*.py with a glob.",
        "See https://docs.github.com/en/get-started?next=/a/b/ first.",
    ],
)
def test_cr1_public_or_scrubbed_slash_text_is_not_an_absolute_path(tmp_path, value):
    assert line_class(value, tmp_path) == ("clean", "")


def test_cr1_a_forge_url_with_dash_segments_is_git_remote_not_absolute_path(tmp_path):
    assert line_class("See https://gitlab.com/g/p/-/issues/1 there.", tmp_path) == ("blocked", "git-remote")


def test_cr2_a_quoted_marker_mid_report_is_kept_and_only_the_trailing_annotation_is_cut(tmp_path):
    quoted = "I saw `<!-- planwise:scan-annotation` in the draft."
    text = body(quoted).replace("Run it.", "Write to someone@example.com.") + "\n" + ANNOTATION
    path = write(tmp_path, text)
    verdict, found, line, data = prep(path)
    assert (verdict, found, line) == ("blocked", "email", 11)
    assert quoted.encode("utf-8") in data
    assert b"Possible duplicates" not in data
    assert data == path.read_bytes()


def test_cr2_a_quoted_marker_at_line_start_before_the_real_annotation_is_kept(tmp_path):
    quoted = "<!-- planwise:scan-annotation is the marker I mean."
    path = write(tmp_path, body(quoted) + "\n" + ANNOTATION)
    _verdict, _found, _line, data = prep(path)
    assert quoted.encode("utf-8") in data
    assert b"Possible duplicates" not in data


@pytest.mark.parametrize(
    "value",
    [
        "Clone https://git.corp.example.com/team/secret-repo first.",
        "Call https://api.github.com/repos/someone/private first.",
        "See https://gist.github.com/someone/abc123 first.",
        "Fetch raw.githubusercontent.com/someone/private/x first.",
        "Ask https://github.com/someone first.",
        "Clone https://someone:token@example.org/x first.",
    ],
)
def test_cr3_private_forge_and_self_hosted_urls_block_as_git_remote(tmp_path, value):
    assert line_class(value, tmp_path) == ("blocked", "git-remote")


@pytest.mark.parametrize(
    "value",
    [
        "Read https://docs.anthropic.com/en/docs/claude-code/hooks first.",
        "Read https://docs.github.com/en/issues/tracking first.",
        "Read https://code.claude.com/docs/en/plugins first.",
        "Read https://example.com/page first.",
    ],
)
def test_cr3_allowlisted_or_single_segment_urls_read_clean(tmp_path, value):
    assert line_class(value, tmp_path) == ("clean", "")


@pytest.mark.parametrize(
    "value",
    [
        "Run scp someone@host:/home/someone/proj/ now.",
        "It said Error:/Users/someone/repo/out.txt today.",
        "It set PATH=/usr/bin:/home/someone/bin today.",
        "The log sits in \\Users\\someone\\repo\\ today.",
    ],
)
def test_cr4_absolute_paths_after_a_colon_or_rooted_backslash_block(tmp_path, value):
    assert line_class(value, tmp_path) == ("blocked", "absolute-path")


def test_cr4_short_escape_sequences_are_not_a_rooted_backslash_path(tmp_path):
    assert line_class("Join with `\\n\\t` between fields.", tmp_path) == ("clean", "")


@pytest.mark.parametrize(
    "value",
    [
        "Install planwise@planwise-marketplace again.",
        "Pin react@18.3.1 in the package.",
    ],
)
def test_cr5_install_id_and_version_pins_are_not_handles(tmp_path, value):
    assert line_class(value, tmp_path) == ("clean", "")


@pytest.mark.parametrize("value", ["Mark it @dataclass in code.", "Reach foo@bar on chat."])
def test_cr5_decorators_and_tldless_user_at_host_still_block(tmp_path, value):
    assert line_class(value, tmp_path) == ("blocked", "handle")


@pytest.mark.parametrize(
    "value",
    [
        f"Clone https://github.com/{REPO}.git first.",
        f"Clone github.com/{REPO}.git first.",
        f"See https://github.com/{REPO} first.",
        f"See github.com/{REPO}/issues/2 first.",
    ],
)
def test_cr6_the_configured_repo_is_exempt_in_every_http_form(tmp_path, value):
    assert line_class(value, tmp_path) == ("clean", "")


@pytest.mark.parametrize(
    "setting",
    ["  include_environment: true\n", "  include_environment: false\n", "", "  include_environment: 1\n", "  include_environment: null\n"],
)
def test_cr7_include_environment_agrees_with_the_config_loader(tmp_path, setting):
    import config_loader

    path = config(tmp_path, setting)
    expected = config_loader.get_feedback_config(config_loader.load_config(config_path=path))
    assert fd.read_post_settings(path) == (expected["include_environment"], expected["repo"])


def test_cr8_environment_inside_a_fence_is_kept(tmp_path):
    fenced = "```\n### Environment\n- inside a fence\n```"
    path = write(tmp_path, body(fenced))
    _verdict, _found, _line, data = prep(path, include_environment=False)
    assert fenced.encode("utf-8") in data
    assert b"OS / shell" not in data


def test_cr8_a_hash_line_inside_a_fence_does_not_end_the_section(tmp_path):
    env = "   ### Environment\n\n- planwise version: 1.0.0\n```\n# not a heading\n- os: test\n```\n"
    path = write(tmp_path, "### What happened\n\nIt broke.\n\n" + env)
    _verdict, _found, _line, data = prep(path, include_environment=False)
    assert data == b"### What happened\n\nIt broke.\n\n"
