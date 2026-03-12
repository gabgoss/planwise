#!/usr/bin/env python3
"""Shared status constants for backlog scripts."""

OPEN_STATUSES = frozenset({"NOT_STARTED", "IN_PROGRESS", "PLANNING", "BLOCKED"})
CLOSED_STATUSES = frozenset({"COMPLETE", "CLOSED"})
ARCHIVE_STATUSES = CLOSED_STATUSES
VALID_STATUSES = OPEN_STATUSES | CLOSED_STATUSES
