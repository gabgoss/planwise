"""Read-only git policy for the verification-gate linter.

``lint_verification_gates`` runs a gate's command only when an allowlist admits
it. This module decides which ``git`` invocations that allowlist admits, and it
builds the hardened argument vector and environment those invocations run with.

Two functions, both pure:

``git_refusal(argv)``
    Returns why ``argv`` may not run, or None when the policy admits it. The
    admitted shape is ``git [-C <dir>]... <subcommand> ...`` where the
    subcommand is one of ``status``, ``diff``, ``log``, ``ls-files``,
    ``rev-parse`` or ``show``. Every other global option is refused, and so is
    every flag that writes a file or starts an external program.

``hardened_git_argv_env(argv)``
    Returns ``(argv, env)`` for an argument vector the policy admitted. It adds
    ``-c core.fsmonitor=false -c core.pager=cat`` after ``git``, adds
    ``--no-ext-diff --no-textconv`` after ``diff``, ``log`` and ``show``, and
    sets ``GIT_OPTIONAL_LOCKS=0`` so ``git status`` never rewrites the index.

The policy is an allowlist of shapes, not a denylist of dangerous words. An
option name that is only a prefix of a refused option is refused too, because
git accepts an unambiguous abbreviation of a long option.
"""

import os

ADMITTED_SUBCOMMANDS = frozenset(
    {"status", "diff", "log", "ls-files", "rev-parse", "show"}
)

# Long options that write a file or start a program the plan did not name.
REFUSED_LONG_OPTIONS = ("--output", "--ext-diff", "--textconv", "--show-signature")

# The subcommands that take diff options, and so take the two hardening flags.
DIFF_FAMILY = frozenset({"diff", "log", "show"})

HARDENING_CONFIG = ("-c", "core.fsmonitor=false", "-c", "core.pager=cat")
HARDENING_DIFF_FLAGS = ("--no-ext-diff", "--no-textconv")


def _parse_prefix(argv):
    """Split ``argv`` into ``(directory args, subcommand index, refusal)``."""
    index = 1
    directory_args = []
    while index < len(argv):
        token = argv[index]
        if token == "-C":
            if index + 1 >= len(argv):
                return None, None, "git -C names no directory"
            directory = argv[index + 1]
            if not directory or directory.startswith("-"):
                return None, None, f"git -C names {directory!r}, which is not a directory"
            directory_args.extend(["-C", directory])
            index += 2
            continue
        if token.startswith("-"):
            return None, None, (
                f"git global option {token!r} is not on the read-only allowlist"
            )
        return directory_args, index, None
    return None, None, "git names no subcommand"


def _refused_option(token):
    """Return the refused long option that ``token`` names or abbreviates."""
    if not token.startswith("--") or len(token) == 2:
        return None
    name = token.split("=", 1)[0]
    for refused in REFUSED_LONG_OPTIONS:
        if name == refused or (len(name) > 2 and refused.startswith(name)):
            return refused
    return None


def git_refusal(argv):
    """Return why ``argv`` (``argv[0] == "git"``) may not run, else None."""
    _, sub_index, refusal = _parse_prefix(argv)
    if refusal is not None:
        return refusal
    subcommand = argv[sub_index]
    if subcommand not in ADMITTED_SUBCOMMANDS:
        return f"git subcommand {subcommand!r} is not on the read-only allowlist"
    for token in argv[sub_index + 1:]:
        if token == "--":
            break
        refused = _refused_option(token)
        if refused is not None:
            return f"git flag {token!r} ({refused}) is not on the read-only allowlist"
    return None


def hardened_git_argv_env(argv):
    """Return ``(argv, env)`` to run an admitted git command read-only.

    The caller has already run ``git_refusal`` and got None.
    """
    directory_args, sub_index, refusal = _parse_prefix(argv)
    if refusal is not None:
        raise ValueError(refusal)
    subcommand = argv[sub_index]
    hardened = ["git", *HARDENING_CONFIG, *directory_args, subcommand]
    if subcommand in DIFF_FAMILY:
        hardened.extend(HARDENING_DIFF_FLAGS)
    hardened.extend(argv[sub_index + 1:])
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env.pop("GIT_EXTERNAL_DIFF", None)
    return hardened, env
