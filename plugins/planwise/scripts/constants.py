#!/usr/bin/env python3
"""Shared constants for planwise scripts."""

from enum import Enum


class InstallScope(str, Enum):
    PROJECT = "project"
    USER = "user"
    LOCAL = "local"


OPEN_STATUSES = frozenset({"NOT_STARTED", "IN_PROGRESS", "PLANNING", "BLOCKED"})
CLOSED_STATUSES = frozenset({"COMPLETE", "CLOSED"})
# Own literal, not an alias of CLOSED_STATUSES: this set governs archive-on-close
# (update_backlog.py) and must be free to diverge from the triage-hide concept
# below without moving any item's file.
ARCHIVE_STATUSES = frozenset({"COMPLETE", "CLOSED"})
# Statuses that hide an item from selectable triage output without archiving it.
HOLD_STATUSES = frozenset({"BLOCKED"})
VALID_STATUSES = OPEN_STATUSES | CLOSED_STATUSES

# The build folder for plan bodies sits inside the plans folder, beside the plan folders. A
# scanner that walks the plans folder skips it by this name. `config_loader` keeps its own
# literal because that module has no sibling imports, and a test holds the two equal.
PLAN_BUILD_DIRNAME = "Plan-Build"
