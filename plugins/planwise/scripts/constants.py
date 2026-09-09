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
# (update_backlog.py, cleanup_backlog.py) and must be free to diverge from the
# triage-hide concept below without moving any item's file.
ARCHIVE_STATUSES = frozenset({"COMPLETE", "CLOSED"})
# Statuses that hide an item from selectable triage output without archiving it.
HOLD_STATUSES = frozenset({"BLOCKED"})
VALID_STATUSES = OPEN_STATUSES | CLOSED_STATUSES
