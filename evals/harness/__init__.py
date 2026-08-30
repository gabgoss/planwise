"""Harness for the planwise eval suite.

This package holds the driver, envelope parser, scratch/fixture engine,
graders, containment predicate, and the tier registry. It is imported only
from under `evals/` (via the `evals/pytest.ini` rootdir re-root) and is never
imported by anything under `plugins/planwise/` — the eval suite lives outside
the shipped subtree.
"""
