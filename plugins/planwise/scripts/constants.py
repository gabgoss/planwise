#!/usr/bin/env python3
"""Shared constants for planwise scripts."""

from enum import Enum


class InstallScope(str, Enum):
    PROJECT = "project"
    USER = "user"
    LOCAL = "local"


OPEN_STATUSES = frozenset({"NOT_STARTED", "IN_PROGRESS", "PLANNING", "BLOCKED"})
CLOSED_STATUSES = frozenset({"COMPLETE", "CLOSED"})
ARCHIVE_STATUSES = CLOSED_STATUSES
VALID_STATUSES = OPEN_STATUSES | CLOSED_STATUSES
