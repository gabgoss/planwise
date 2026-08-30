"""Lifecycle-family eval cases.

Row 1 -- EC-migrate-02 (Tier-S smoke): `/planwise init --migrate` against a
directory with no pre-existing `config.yaml`. Live `claude` CLI, real
spend (T2 class, ~$0.15-0.30). Runs on `fx-empty-contained` -- no fixture
template is built or needed; a canary must not depend on the machinery it
validates.

The migrate gate is the exact inverse of plain init's config-exists gate:
`_run_migrate` requires `config.yaml` to already exist and raises
`FileNotFoundError` -> the literal `"Migration failed: {exc}"` on stderr,
exit 2, when it does not. That failure belongs to the NESTED
`init_project.py` subprocess call the handler drives via its own tool
call, not to the outer `claude` CLI process -- a real multi-turn agent
session runs here (T2 pricing, never $0), so the outer envelope is a
normal, well-formed `is_error:false` / `subtype:success` turn; only the
inner tool call fails. The "non-zero-exit arm" is therefore checked
against the captured transcript text rather than the outer process's own
`returncode`, which this driver has no reason to expect non-zero here.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from conftest import require_cli
from harness import envelope as envelope_mod
from harness import fixtures, graders, invoke
from harness.scratch import ScratchRoot
from harness.scratch import teardown as _teardown_scratch_root

CLI_PATH = require_cli()

_PLUGIN_SOURCE = Path(__file__).resolve().parents[2] / "plugins" / "planwise"


@pytest.fixture(scope="module")
def scratch(request):
    """One scratch root + one plugin-subtree copy, shared by every row in
    this file (one `copytree` per file, not per case). `--plugin-dir` is
    pointed at the copy, never the live tree -- the copy carries no
    live-project path prefix, so a handler that walks up on a missing
    local config cannot reach the live authoring project.

    Skips BEFORE building anything when no explicit `-m` marker expression
    was passed -- a per-test `pytest.skip()` alone is not enough, because
    fixture setup runs before a test body's own skip check ever executes,
    so a marker-less run would still pay for a scratch root + a full
    plugin-subtree copy for every live row it never invokes.
    """
    if not request.config.option.markexpr:
        pytest.skip(
            "live-spend smoke rows -- only build a scratch root under an "
            "explicit -m marker expression, never a bare marker-less "
            "invocation"
        )
    root = ScratchRoot.create(run_id=f"lifecycle-{uuid.uuid4().hex[:8]}")
    root.copy_plugin_subtree(_PLUGIN_SOURCE)
    yield root
    print(f"\n[eval_lifecycle] transcript delta: {root.report_transcript_delta()}")

    # Tear the whole scratch root down (plugin-subtree copy included) --
    # otherwise every `-m smoke` run leaves a full plugin copy in TEMP
    # permanently. Only when it is actually safe to: `case_dirs` records
    # every case dir this fixture's rows created, and a retained one (a
    # failed row kept for post-mortem, per --eval-keep-failed's default-on
    # posture) must not be swept away along with the root. `teardown()` is
    # the module's own public deletion primitive -- called here with the
    # root as both `case_dir` and `scratch_root`, which its own
    # containment check explicitly permits (a path equal to the root, not
    # just inside it).
    retained = [case_dir for case_dir in root.case_dirs if case_dir.exists()]
    if retained:
        print(
            f"[eval_lifecycle] scratch root NOT torn down -- "
            f"{len(retained)} retained (failed+kept) case dir(s) hold "
            f"post-mortem evidence: {[str(p) for p in retained]}"
        )
    else:
        _teardown_scratch_root(root.root, root.root, failed=False)
        print(f"[eval_lifecycle] scratch root torn down: {root.root}")


def _assert_pre_grading_gate(envelope: envelope_mod.Envelope, scratch: ScratchRoot) -> None:
    """The gate every case runs before its own assertions: init-event
    membership, `plugins[0].path` matches the scratch copy (never the live
    tree), and the envelope itself is a healthy success. Called as the
    first check inside every test body here -- no shared conftest fixture
    is wired for this yet, so this plain function is the uniform gate
    every case goes through instead.
    """
    assert envelope.outcome == "ok", (
        f"expected a well-formed envelope, got outcome={envelope.outcome!r}"
    )
    a1 = graders.a1_init_membership(envelope)
    assert a1.passed, a1.observed

    plugins = (envelope.init_event or {}).get("plugins") or []
    assert plugins, "init event carries no plugins[] entry at all"
    observed_path = Path(plugins[0].get("path", ""))
    assert observed_path.resolve() == scratch.plugin_copy.resolve(), (
        f"--plugin-dir did not register the scratch copy: "
        f"observed={observed_path!r} expected={scratch.plugin_copy!r}"
    )

    result_event = envelope.result_event or {}
    assert result_event.get("is_error") is False, result_event
    assert result_event.get("subtype") == "success", result_event



# The runtime name of Claude Code's own shell-command tool is
# platform-dependent -- confirmed against a real captured transcript
# (2026-08-19 live run): on this Windows host it is `PowerShell`, never
# `Bash` (`invoke.py`'s own docstring: the driver shells the CLI itself
# through `powershell.exe` on Windows, and the AGENT's in-session shell
# tool follows the same platform split). Both names are accepted so this
# stays correct on a POSIX host too, where the agent's shell tool is named
# `Bash`.
_SHELL_TOOL_NAMES = frozenset({"Bash", "PowerShell"})


def _shell_tool_result_text(envelope: envelope_mod.Envelope) -> str:
    """Concatenated text content of every `tool_result` block that pairs
    (via `tool_use_id`) with a shell-command `tool_use` block (see
    `_SHELL_TOOL_NAMES`) -- the authoritative location for a nested
    subprocess's own stderr. `graders.py`'s ratified rule is that an index
    must target the authoritative field, never raw stdout or
    mid-transcript tool-read noise: `result.stdout` is the WHOLE captured
    JSON event array, so a plain substring search over it can be satisfied
    by an assistant text block, a `tool_use` input, or an unrelated tool's
    `tool_result` (e.g. a file read) that happens to contain the same
    literal -- contaminable whether or not the migrate gate ever actually
    fired. Built entirely from the envelope module's own dispatch-evidence
    helpers (`agent_tool_uses` / `tool_use_results`), never a new parser.
    """
    shell_tool_use_ids = {
        block.get("id")
        for block in envelope_mod.agent_tool_uses(envelope)
        if block.get("name") in _SHELL_TOOL_NAMES
    }
    chunks: list[str] = []
    for result in envelope_mod.tool_use_results(envelope):
        if result.get("tool_use_id") not in shell_tool_use_ids:
            continue
        content = result.get("content")
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    chunks.append(block.get("text", ""))
    return "\n".join(chunks)


@pytest.mark.smoke
def test_ec_migrate_02(scratch, eval_keep_failed):
    """EC-migrate-02 -- `S-init-migrate`, failure case. `fx-empty-contained`
    (no pre-existing config.yaml) is exactly the missing-config gate this
    case targets. Assertions: A2 (the non-zero-exit arm -- the migrate
    gate's hardcoded `"Migration failed: {exc}"` stderr message, a stable
    literal since it is hardcoded in the script rather than paraphrased by
    the model), A4 (nothing written -- the gate fires before any file
    touch).

    No per-test marker-less guard here -- the `scratch` fixture itself
    skips before building anything when no explicit `-m` marker was
    passed, which this test depends on unconditionally.
    """
    case_dir = fixtures.FIXTURES["fx-empty-contained"](scratch)
    failed = True  # flipped to False only after every assertion below passes
    try:
        prompt = "/planwise init --migrate --name case"
        result = invoke.run_case(
            prompt=prompt, plugin_dir=scratch.plugin_copy, cwd=case_dir, tier="T2",
        )
        assert result.outcome == "ok", (
            "expected a captured envelope (a real agent turn runs here -- "
            f"T2 pricing, never $0), got outcome={result.outcome!r} "
            f"returncode={result.returncode!r} stderr={result.stderr!r}"
        )
        envelope = envelope_mod.parse(result.stdout)
        _assert_pre_grading_gate(envelope, scratch)
        cost = (envelope.result_event or {}).get("total_cost_usd")
        print(f"\n[eval-cost] EC-migrate-02: total_cost_usd={cost}")

        # A2 -- non-zero-exit arm: the migrate gate's literal stderr
        # message. Scoped to the shell tool's own tool_result content
        # (`_shell_tool_result_text` -- `Bash` on POSIX, `PowerShell` on
        # Windows), never the whole captured `stdout` blob -- the message
        # is a hardcoded, non-paraphrased literal (confirmed against the
        # script's own source), but a raw-stdout substring search is
        # satisfiable by assistant prose, a tool_use input, or an
        # unrelated tool's tool_result that happens to carry the same
        # text, whether or not the migrate gate ever fired.
        marker = "Migration failed:"
        shell_output = _shell_tool_result_text(envelope)
        assert marker in shell_output, (
            f"expected the migrate gate's literal {marker!r} in a shell "
            f"tool's tool_result (the authoritative location for the "
            f"nested subprocess's own stderr); "
            f"shell_tool_result_text={shell_output!r}"
        )

        # A4 -- nothing written: the gate fires (FileNotFoundError) before
        # config.yaml can be read, let alone written -- checked against the
        # full path set a successful init/migrate could have produced.
        a4 = graders.a4_write_set_absent(case_dir, fixtures.INIT_WRITE_SET)
        assert a4.passed, a4.observed

        failed = False
    finally:
        scratch.teardown_case(case_dir, failed=failed, keep_failed=eval_keep_failed)


# rows 02..: authored by the LifecycleCases sprint
