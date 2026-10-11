"""Read-only preflight for the backlog, lessons and plans indexes.

Prints one JSON object: the shape of each index (`generated`, `legacy`, `unrecognized` or
`absent`) and `any_legacy`, true when at least one index is hand-authored. With
`--questions` it also runs each family's read-only report on a legacy index and adds the
refusals the migration would raise (`would_refuse`) and the questions a handler should ask
the user before it migrates (`questions`). It never writes, and it exits 0 whatever the
indexes hold, so a handler can run it before any write and read the answer from stdout.

    python index_shape_preflight.py --config <planwise>/config.yaml [--questions] [--json]
"""
import argparse
import json
import sys
from pathlib import Path

import config_loader
import migrate_backlog_index as backlog
import migrate_backlog_support as backlog_sup
import migrate_lessons_index as lessons
import migrate_lessons_support as lessons_sup
import migrate_plans_index as plans

FAMILIES = (("backlog", "_index_path", backlog_sup.classify_shape, backlog.build_report),
            ("lessons", "_lessons_index", lessons_sup.classify_shape, lessons.build_report),
            ("plans", "_plans_index", plans.classify_shape, plans.build_report))


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
    out["any_legacy"] = any(out[name]["shape"] == "legacy" for name, *_ in FAMILIES)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
