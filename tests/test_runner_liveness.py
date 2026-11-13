"""Controls for scripts/runner_liveness.py (delegated reference §1.30, Liveness)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "runner_liveness.py"


def entry(age_seconds: float = 0.0) -> str:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return json.dumps({"type": "assistant", "timestamp": stamp.isoformat().replace("+00:00", "Z")})


def command(path: Path, interval: str = "1.0", max_age: str = "120") -> list[str]:
    return [sys.executable, "-B", str(SCRIPT), str(path), "--interval", interval, "--max-age", max_age]


def test_positive_growing_transcript_is_alive(tmp_path):
    path = tmp_path / "live.jsonl"
    path.write_text(entry() + "\n", encoding="utf-8")
    proc = subprocess.Popen(command(path, interval="2.0"), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8")
    time.sleep(1.0)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry() + "\n")
    out, err = proc.communicate(timeout=60)
    assert proc.returncode == 0, err
    assert out.startswith("alive:")


def test_mutation_frozen_transcript_is_stalled(tmp_path):
    # Breaks §1.30: no line growth across two samples and a last entry minutes old.
    path = tmp_path / "frozen.jsonl"
    path.write_text(entry(600) + "\n" + entry(600) + "\n", encoding="utf-8")
    result = subprocess.run(command(path, interval="0.2"), capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 3, result.stderr
    assert result.stdout.startswith("stalled:")


def test_mutation_recent_but_not_growing_is_stalled(tmp_path):
    # Breaks §1.30: one recent timestamp without growth is still not proof of life.
    path = tmp_path / "quiet.jsonl"
    path.write_text(entry() + "\n", encoding="utf-8")
    result = subprocess.run(command(path, interval="0.2"), capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 3, result.stderr


def test_usage_missing_path_is_unreadable(tmp_path):
    result = subprocess.run(command(tmp_path / "absent.jsonl", interval="0"),
                            capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 2
    assert "unreadable" in result.stderr


def test_usage_no_timestamp_is_unreadable(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"type": "user"}\nnot json\n', encoding="utf-8")
    result = subprocess.run(command(path, interval="0"), capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 2


def test_usage_bad_argument_exits_2(tmp_path):
    result = subprocess.run([sys.executable, "-B", str(SCRIPT)], capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 2
