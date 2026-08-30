"""Bookkeeping-family eval cases.

Three Tier-S smoke rows, all on `fx-empty-contained` -- the containment
base every smoke row shares (no fixture template needed or built here; a
canary must not depend on the machinery it validates):

  * EC-help-01 -- the harness canary, runs FIRST in any tier
    (`harness.tiers.CANARY_FIRST`). Defined first in this file, and this
    file collects before `eval_lifecycle.py` under pytest's default
    alphabetic file ordering -- together those two facts are what make it
    run first across the whole session.
  * EC-help-02 -- the unrecognized-subcommand failure path.
  * EC-feedback-02 -- `/planwise feedback`, degrade-to-draft path with no
    local config.yaml.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from conftest import require_cli
from harness import containment
from harness import envelope as envelope_mod
from harness import fixtures, graders, invoke, tiers
from harness.scratch import ScratchRoot
from harness.scratch import teardown as _teardown_scratch_root

CLI_PATH = require_cli()

_PLUGIN_SOURCE = Path(__file__).resolve().parents[2] / "plugins" / "planwise"
_OUTER_REPO = Path(__file__).resolve().parents[4]
_PLUGIN_REPO = Path(__file__).resolve().parents[2]


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
    root = ScratchRoot.create(run_id=f"bookkeeping-{uuid.uuid4().hex[:8]}")
    root.copy_plugin_subtree(_PLUGIN_SOURCE)
    yield root
    print(f"\n[eval_bookkeeping] transcript delta: {root.report_transcript_delta()}")

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
            f"[eval_bookkeeping] scratch root NOT torn down -- "
            f"{len(retained)} retained (failed+kept) case dir(s) hold "
            f"post-mortem evidence: {[str(p) for p in retained]}"
        )
    else:
        _teardown_scratch_root(root.root, root.root, failed=False)
        print(f"[eval_bookkeeping] scratch root torn down: {root.root}")


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


@pytest.mark.smoke
def test_ec_help_01(scratch, eval_keep_failed):
    """EC-help-01 -- `S-help-inline`, happy path, the harness canary
    (`tiers.CANARY_FIRST`). Assertions: A1 (pre-grading gate), A5 (the
    doctor line's descriptive text as an ordinary CONTENT marker only --
    never a working-tree-vs-cache discriminator; the only verified
    tree-vs-cache differentials are the `feedback`/`harvest` subcommand
    words, not this line), A4 (help never writes), A2 (the plain pass
    arm -- exit 0, healthy envelope; this row and EC-migrate-02 are A2's
    two discriminating arms).

    No per-test marker-less guard here -- the `scratch` fixture itself
    skips before building anything when no explicit `-m` marker was
    passed, which this test depends on unconditionally.
    """
    assert tiers.CANARY_FIRST == "EC-help-01"
    case_dir = fixtures.FIXTURES["fx-empty-contained"](scratch)
    failed = True
    try:
        result = invoke.run_case(
            prompt="/planwise help", plugin_dir=scratch.plugin_copy, cwd=case_dir, tier="T1",
        )
        assert result.outcome == "ok", (
            f"got outcome={result.outcome!r} returncode={result.returncode!r} "
            f"stderr={result.stderr!r}"
        )
        envelope = envelope_mod.parse(result.stdout)
        _assert_pre_grading_gate(envelope, scratch)
        cost = (envelope.result_event or {}).get("total_cost_usd")
        print(f"\n[eval-cost] EC-help-01: total_cost_usd={cost}")

        a2 = graders.a2_result_envelope(envelope, returncode=result.returncode)
        assert a2.passed, a2.observed

        # A5 -- doctor-line content marker, never a tree discriminator.
        doctor_marker = "Audit rule scope"
        a5 = graders.a5_marker_in_result(envelope, marker=doctor_marker)
        assert a5.passed, a5.observed

        a4 = graders.a4_write_set_absent(case_dir, fixtures.INIT_WRITE_SET)
        assert a4.passed, a4.observed

        failed = False
    finally:
        scratch.teardown_case(case_dir, failed=failed, keep_failed=eval_keep_failed)


@pytest.mark.smoke
def test_ec_help_02(scratch, eval_keep_failed):
    """EC-help-02 -- `S-help-inline`, failure path. Assertions: A5 (the
    stable `Unknown subcommand:` substring only -- the router's literal
    reply text; the full sentence is deterministic by construction but its
    paraphrase risk under a real model turn is unmeasured, so only the
    stable prefix is asserted), A1 (pre-grading gate), A4 (nothing
    written).

    No per-test marker-less guard here -- the `scratch` fixture itself
    skips before building anything when no explicit `-m` marker was
    passed, which this test depends on unconditionally.
    """
    case_dir = fixtures.FIXTURES["fx-empty-contained"](scratch)
    failed = True
    try:
        result = invoke.run_case(
            prompt="/planwise not-a-real-subcommand",
            plugin_dir=scratch.plugin_copy, cwd=case_dir, tier="T1",
        )
        assert result.outcome == "ok", (
            f"got outcome={result.outcome!r} returncode={result.returncode!r} "
            f"stderr={result.stderr!r}"
        )
        envelope = envelope_mod.parse(result.stdout)
        _assert_pre_grading_gate(envelope, scratch)
        cost = (envelope.result_event or {}).get("total_cost_usd")
        print(f"\n[eval-cost] EC-help-02: total_cost_usd={cost}")

        a5 = graders.a5_marker_in_result(envelope, marker="Unknown subcommand:")
        assert a5.passed, a5.observed

        a4 = graders.a4_write_set_absent(case_dir, fixtures.INIT_WRITE_SET)
        assert a4.passed, a4.observed

        failed = False
    finally:
        scratch.teardown_case(case_dir, failed=failed, keep_failed=eval_keep_failed)


@pytest.mark.smoke
def test_ec_feedback_02(scratch, eval_keep_failed):
    """EC-feedback-02 -- `S-feedback-default`, failure/degrade path.
    `kind` and every body field are injected explicitly in the prompt
    (never left for the handler to auto-fill or ask about) since a
    headless run cannot answer a follow-up question. With no local
    config.yaml, the handler's own Config-Gate exception applies: no
    auto-init, `plugin_version: unknown`, draft-only (feedback.enabled
    cannot be confirmed true without a readable config).

    Assertions: A3 (draft-by-pattern -- the model-generated filename slug
    is not pinned; the write set is asserted to be exactly one file whose
    name matches the pinned `{date}-{kind}-{slug}.md` shape under a
    `feedback-drafts/` directory, never an exact path), A6 (the draft's
    Environment block carries the literal line `planwise version:
    unknown` -- there is no config.yaml in this case dir for the ordinary
    YAML-structured A6 read, so this is checked as literal text in the
    rendered draft instead), A5 (the fallback URL printed in the final
    result), A4b (LOAD-BEARING: with no local config the draft must not
    land in the live authoring tree -- both the parent-scoped filesystem
    scan and a both-repo `git status --porcelain` delta are checked).

    No per-test marker-less guard here -- the `scratch` fixture itself
    skips before building anything when no explicit `-m` marker was
    passed, which this test depends on unconditionally.
    """
    case_dir = fixtures.FIXTURES["fx-empty-contained"](scratch)
    baseline = containment.capture_baseline([_OUTER_REPO, _PLUGIN_REPO])
    failed = True
    try:
        prompt = (
            "/planwise feedback bug\n\n"
            "kind: bug\n"
            "title: Doctor status lags after a token-saver toggle\n"
            "What happened: Running /planwise doctor immediately after "
            "/planwise token-saver on still reports the Token Saver line "
            "as off.\n"
            "What I expected: doctor should reflect the just-toggled "
            "state on its very next invocation.\n"
            "Steps to reproduce: 1) /planwise token-saver on  "
            "2) /planwise doctor  3) Observe the stale Token Saver line.\n"
            "Subcommand involved: /planwise doctor\n"
            "OS/shell: Windows 11, PowerShell\n"
        )
        result = invoke.run_case(
            prompt=prompt, plugin_dir=scratch.plugin_copy, cwd=case_dir, tier="T2",
        )
        assert result.outcome == "ok", (
            f"got outcome={result.outcome!r} returncode={result.returncode!r} "
            f"stderr={result.stderr!r}"
        )
        envelope = envelope_mod.parse(result.stdout)
        _assert_pre_grading_gate(envelope, scratch)
        cost = (envelope.result_event or {}).get("total_cost_usd")
        print(f"\n[eval-cost] EC-feedback-02: total_cost_usd={cost}")

        # A3 -- draft-by-pattern: exactly one file, under a
        # `feedback-drafts/` directory, named `{date}-bug-{slug}.md`.
        draft_matches = [p for p in case_dir.rglob("*.md") if "feedback-drafts" in p.parts]
        assert len(draft_matches) == 1, (
            f"expected exactly one feedback-drafts/*.md file, found "
            f"{[str(p.relative_to(case_dir)) for p in draft_matches]}"
        )
        draft_path = draft_matches[0]
        assert re.match(r"^\d{4}-\d{2}-\d{2}-bug-[a-z0-9-]+\.md$", draft_path.name), (
            f"draft filename does not match the pinned "
            f"{{date}}-{{kind}}-{{slug}}.md shape: {draft_path.name!r}"
        )

        # A6 -- `plugin_version: unknown`, checked as literal text in the
        # rendered draft's Environment block (no config.yaml exists in
        # this case dir for the ordinary YAML-structured A6 read).
        draft_text = draft_path.read_text(encoding="utf-8")
        assert "planwise version: unknown" in draft_text, draft_text

        # A5 -- fallback URL printed in the final result.
        a5 = graders.a5_marker_in_result(
            envelope, marker="https://github.com/gabgoss/planwise/issues",
        )
        assert a5.passed, a5.observed

        # A4b -- LOAD-BEARING containment: the parent-scoped filesystem
        # scan, plus the both-repo porcelain delta that catches a walk-up
        # write the parent-scoped scan cannot see. `scratch` is
        # module-scoped, so sibling rows' case dirs (retained on disk when
        # an earlier row failed, since --eval-keep-failed defaults on) are
        # declared excluded too -- otherwise an earlier row's failure gets
        # misreported here as THIS row's write escaping the case dir.
        a4b = graders.a4b_containment(
            parent=scratch.root, case_dir=case_dir,
            exclude=[scratch.plugin_copy, *scratch.case_dirs],
        )
        assert a4b.passed, a4b.observed

        delta = containment.porcelain_delta([_OUTER_REPO, _PLUGIN_REPO], baseline=baseline)
        for status in delta.statuses:
            # Both must hold: the repo was actually checked (not silently
            # skipped -- `status.dirty` reads as `None`, and `not None` is
            # `True`, for an unchecked repo, so asserting `not dirty` alone
            # lets an unchecked repo sail through) AND it came back clean.
            assert status.checked, (
                f"{status.repo} was never checked for a porcelain delta "
                "(missing path, not a git worktree, or the git call "
                "failed) -- an unchecked repo must never silently pass"
            )
            assert not status.dirty, (
                f"unexpected write outside the case dir landed in {status.repo}: "
                f"baseline={status.baseline!r} current={status.current!r}"
            )

        failed = False
    finally:
        scratch.teardown_case(case_dir, failed=failed, keep_failed=eval_keep_failed)


# rows 04..: authored by the BookkeepingCases sprint
