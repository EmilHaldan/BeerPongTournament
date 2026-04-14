"""Shared name-normalisation helper used across DAL modules.

The canonical rule for all user-facing names in this app is:

    name.strip().title()

Having one copy in the DAL prevents drift between team, player, and future
name-carrying entities.
"""

from __future__ import annotations


def normalize_name(name: str) -> str:
    """Normalize a name: strip surrounding whitespace and title-case."""
    return name.strip().title()
