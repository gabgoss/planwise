"""Shared test helpers for the Token Saver engine test split.

`_engine()` is consumed by three sibling test modules that each exercise a
piece of the split — `test_token_saver.py` (the config surface, via the
facade), `test_context_calibration.py` (the calibration engine), and
`test_read_limits.py` (the Read-tool gating engine) — so it lives here rather
than being copy-pasted three times.
"""

import importlib
import sys


def _engine():
    """Import (or re-import) the not-yet-implemented token_saver engine module.

    Imported lazily so a missing module surfaces as a per-test error (TDD red)
    rather than aborting collection of the whole file at import time.
    """
    if "token_saver" in sys.modules:
        return importlib.reload(sys.modules["token_saver"])
    return importlib.import_module("token_saver")
