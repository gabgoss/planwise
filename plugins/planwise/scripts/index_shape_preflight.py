"""Read-only preflight for the backlog, lessons and plans indexes.

Prints one JSON object: the shape of each index (`generated`, `legacy`, `unrecognized` or
`absent`) and `any_legacy`, true when at least one index is hand-authored. With
`--questions` it also runs each family's read-only report on a legacy index and adds the
refusals the migration would raise (`would_refuse`) and the questions a handler should ask
the user before it migrates (`questions`). The backlog entry's `questions` also holds one
question for each distinct item status outside `VALID_STATUSES`, whatever the index shape.
It never writes, and it exits 0 whatever the indexes hold, so a handler can run it before
any write and read the answer from stdout.

    python index_shape_preflight.py --config <planwise>/config.yaml [--questions] [--json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

import config_loader
import constants
import migrate_backlog_index as backlog
import migrate_backlog_support as backlog_sup
import migrate_lessons_index as lessons
import migrate_lessons_support as lessons_sup
import migrate_plans_index as plans

FAMILIES = (("backlog", "_index_path", backlog_sup.classify_shape, backlog.build_report),
            ("lessons", "_lessons_index", lessons_sup.classify_shape, lessons.build_report),
            ("plans", "_plans_index", plans.classify_shape, plans.build_report))


_MAX_IDS_SHOWN = 10
# AskUserQuestion takes at most 4 options, and the user's own "Other" reaches the rest.
_STATUS_OPTIONS = ("NOT_STARTED", "IN_PROGRESS", "BLOCKED", "COMPLETE")


def status_question(status: str, ids: list) -> dict:
    """The question for one out-of-set item status. Each option's `answer` is a `status_map` fragment
    that `migration_answers` accepts as written. The statuses no option names ride in the prompt."""
    shown = ", ".join(ids[:_MAX_IDS_SHOWN]) + (f" and {len(ids) - _MAX_IDS_SHOWN} more" if len(ids) > _MAX_IDS_SHOWN else "")
    unlisted = ", ".join(sorted(constants.VALID_STATUSES - set(_STATUS_OPTIONS)))
    return {"id": "item-status",
            "prompt": (f"{len(ids)} open backlog item(s) ({shown}) carry the status '{status}', which is not a valid "
                       f"status. Which status should they take? For {unlisted}, choose Other and type it."),
            "options": [{"label": target, "answer": {"status_map": [f"{status}->{target}"]}}
                        for target in _STATUS_OPTIONS],
            "statuses": [status], "items": list(ids)}


def status_questions(config: dict) -> list:
    """One question for each distinct out-of-set status among the open backlog items, whatever the index shape."""
    import backlog_item_shape

    found = backlog_item_shape.out_of_set_statuses(config["_backlog_dir"])
    return [status_question(status, ids) for status, ids in found.items()]


def _detail(shape: str, detail) -> str:
    return detail if isinstance(detail, str) and shape != "legacy" else ""


def inspect(config: dict, key: str, classify, report_fn, with_questions: bool) -> dict:
    """The preflight entry for one family; an unreadable index reports `error`, never raises."""
    path = config.get(key)
    entry = {"index": str(path) if path else None, "shape": "absent", "detail": ""}
    if path is None or not Path(path).is_file():
        return entry
    try:
        text = Path(path).read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
        shape, detail = classify(text)
        entry["shape"] = "generated" if shape == "migrated" else shape
        entry["detail"] = _detail(shape, detail)
    except Exception as exc:  # noqa: BLE001 -- the preflight reports a failure, it never raises
        entry["shape"], entry["detail"] = "unrecognized", f"could not read the index: {exc!r}"
        return entry
    if with_questions:
        report = {}
        if shape == "legacy":
            try:
                report = report_fn(config, Path(path))
            except Exception as exc:  # noqa: BLE001 -- a report failure keeps the classified shape
                entry["report_error"] = f"could not build the report: {exc!r}"
        entry["would_refuse"] = list(report.get("would_refuse", []))
        entry["questions"] = list(report.get("questions", []))
    return entry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, required=True, help="Path to config.yaml.")
    parser.add_argument("--questions", action="store_true",
                        help="Add the refusals and the questions a migration would raise, per legacy index.")
    parser.add_argument("--json", action="store_true", help="Print JSON (the default and only format).")
    args = parser.parse_args(argv)
    try:
        config = config_loader.load_config(Path(__file__), config_path=args.config)
    except Exception as exc:  # noqa: BLE001 -- exit 0 whatever the config holds
        print(json.dumps({"error": f"could not load the config: {exc!r}", "any_legacy": False}, indent=2))
        return 0
    out = {name: inspect(config, key, classify, report_fn, args.questions)
           for name, key, classify, report_fn in FAMILIES}
    if args.questions and "questions" in out["backlog"]:
        try:
            out["backlog"]["questions"] += status_questions(config)
        except Exception as exc:  # noqa: BLE001 -- a failed item scan is reported, it never raises
            out["backlog"]["report_error"] = f"could not scan the item statuses: {exc!r}"
    out["any_legacy"] = any(out[name]["shape"] == "legacy" for name, *_ in FAMILIES)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
