"""Headless invocation driver — shells out to the `claude` CLI with the
pinned invocation form and never raises.

`run_case` builds the pinned command:

    claude -p "<prompt>" --plugin-dir "<drive-letter subtree path>" --output-format json

Windows routes through `powershell.exe -NoProfile -Command …` — PowerShell
resolves the `claude` shim itself, so no `shutil.which` / `shell=True` is
needed on that branch. The prompt and plugin-dir are embedded as PowerShell
SINGLE-quoted string literals (`_ps_single_quote`), not double-quoted
interpolation: every real fixture-init prompt this driver actually carries
(`/planwise init --name "..." --root "..." ...`) is full of embedded double
quotes, and a double-quoted inner command truncates at the first one,
producing malformed argv instead of a case failure that says so. Inside a
PowerShell single-quoted literal, `"`, backtick, `$`, and `;` are all
ordinary characters — the only character requiring escape is a literal
single quote, which PowerShell's own rule doubles. POSIX resolves the
binary via `shutil.which` and launches an argv list directly — already
injection-safe, since argv items are never shell-parsed.

Every subprocess call is wrapped so this module NEVER raises: a bad tier
label, a timeout, an OS-level launch failure, and an empty-stdout capture
are each their own distinct outcome code on the returned `InvokeResult`,
never folded into one another or into "assertion failed" — a timeout kill,
a launch failure, and a CLI-level failure with nothing to parse each have a
different remedy, so a caller needs to be able to tell them apart.

Two further divergences from the plain shell-out precedent this driver
adapts: per-tier timeouts (a single flat value short enough for the fast
tiers kills every slow-tier case and reports it as a capture failure), and
an explicit UTF-8 capture encoding (the platform-default locale encoding is
how PowerShell's own output-encoding trap mangles non-ASCII prose read back
from a captured pipe).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

# Per-tier timeout table, seconds. Declared explicitly per tier rather than
# one flat value shared by every case — a timeout short enough for the fast
# tiers kills every slower-tier case and reports it as a capture failure
# instead of what it is: a case that legitimately needs longer to run.
TIER_TIMEOUT_S: dict[str, int] = {
    "T1": 60,
    "T2": 120,
    "T3": 240,
    "T4": 600,
    "T5": 1080,
    "T6": 2400,
}


def timeout_for_tier(tier: str) -> int:
    """The declared timeout, in seconds, for a tier label (e.g. "T3").

    Raises `ValueError` for an unrecognized tier — this is a plain utility
    function, not the never-raise entry point. `run_case` below is the
    never-raise boundary: it calls this function through its own guard and
    turns the `ValueError` into a structured "bad-tier" outcome rather than
    letting it propagate.
    """
    try:
        return TIER_TIMEOUT_S[tier]
    except KeyError as exc:
        raise ValueError(
            f"unknown tier {tier!r}; expected one of {sorted(TIER_TIMEOUT_S)}"
        ) from exc


@dataclass
class InvokeResult:
    """The outcome of one `run_case` invocation.

    `outcome` is one of "ok", "timeout", "oserror", "empty-stdout",
    "bad-tier" — the driver's own capture-layer classification. It says
    nothing about whether the CAPTURED envelope is well-formed; that
    judgment belongs to `envelope.parse()` one layer up.
    """

    outcome: str
    returncode: int | None
    stdout: str
    stderr: str
    tier: str
    timeout_s: int


def _ps_single_quote(value) -> str:
    """Escape a value for embedding inside a PowerShell single-quoted
    string literal.

    Inside single quotes PowerShell treats `"`, backtick, `$`, and `;` as
    ordinary characters — none of them can terminate the string early or
    trigger expansion. The only character that needs escaping is a literal
    single quote, which PowerShell's own literal-escape rule doubles
    (`'` -> `''`). This is what keeps a quote-bearing prompt or a
    space/apostrophe-bearing path intact as ONE argument reaching the CLI.
    """
    return str(value).replace("'", "''")


def run_case(prompt: str, plugin_dir, cwd, tier: str) -> InvokeResult:
    """Run one headless case and capture its result. Never raises —
    including for an unrecognized tier, which yields its own "bad-tier"
    outcome instead of letting `timeout_for_tier`'s `ValueError` propagate.

    `plugin_dir` and `cwd` accept anything `str()`-coercible (e.g. a
    `pathlib.Path`). `cwd` is always passed explicitly to `subprocess.run` —
    this driver never shells through `cd`.
    """
    try:
        timeout_s = timeout_for_tier(tier)
    except ValueError:
        return InvokeResult(
            outcome="bad-tier", returncode=None, stdout="", stderr="",
            tier=tier, timeout_s=0,
        )

    if os.name == "nt":
        # PowerShell attaches a console and resolves the `claude` shim
        # itself — no shutil.which / shell=True needed on this branch.
        # Single-quoted PowerShell literals (see _ps_single_quote): a
        # double-quoted inner command truncates at the prompt's first
        # embedded `"` (every real fixture-init prompt has several),
        # silently mangling argv instead of failing loudly.
        inner = (
            f"claude -p '{_ps_single_quote(prompt)}' "
            f"--plugin-dir '{_ps_single_quote(plugin_dir)}' "
            f"--output-format json"
        )
        cmd = ["powershell.exe", "-NoProfile", "-Command", inner]
    else:
        claude_bin = shutil.which("claude") or "claude"
        cmd = [
            claude_bin, "-p", prompt,
            "--plugin-dir", str(plugin_dir),
            "--output-format", "json",
        ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            # Explicit UTF-8 rather than the platform-default locale
            # encoding `text=True` alone would pick — the fix for the
            # PowerShell output-encoding trap (non-ASCII prose otherwise
            # reads back mangled). `errors="replace"` degrades rather than
            # raises, keeping this wrapper never-raise even on a genuinely
            # corrupt byte stream.
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            shell=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        # Its own outcome — a timeout kill is a capture failure with a
        # different remedy than an assertion failure; never folded in.
        return InvokeResult(
            outcome="timeout", returncode=None, stdout="", stderr="",
            tier=tier, timeout_s=timeout_s,
        )
    except (OSError, subprocess.SubprocessError):
        return InvokeResult(
            outcome="oserror", returncode=None, stdout="", stderr="",
            tier=tier, timeout_s=timeout_s,
        )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if not stdout.strip():
        # A CLI-level failure can exit non-zero with zero bytes of stdout
        # (not even an init event) — its own outcome, not a parse failure,
        # since there is nothing here to parse.
        return InvokeResult(
            outcome="empty-stdout", returncode=proc.returncode,
            stdout=stdout, stderr=stderr, tier=tier, timeout_s=timeout_s,
        )

    return InvokeResult(
        outcome="ok", returncode=proc.returncode, stdout=stdout,
        stderr=stderr, tier=tier, timeout_s=timeout_s,
    )
