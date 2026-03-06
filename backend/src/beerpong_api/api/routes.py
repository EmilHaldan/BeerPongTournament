"""HTTP route definitions.

All routes delegate to DAL functions – they never access the DB client directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from beerpong_api.dal.leaderboard import compute_leaderboard
from beerpong_api.dal.matches import delete_match, insert_match, list_matches, reset_matches
from beerpong_api.dal.teams import get_team_names, list_teams
from beerpong_api.db.models import (
    LeaderboardEntry,
    MatchCreate,
    MatchResult,
    Team,
)
from beerpong_api.settings import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Simple health-check endpoint."""
    return {"status": "ok"}


# ── Matches ───────────────────────────────────────────────────────────


@router.get("/matches", response_model=list[MatchResult])
def get_matches() -> list[MatchResult]:
    """Return all match results ordered by creation date descending."""
    return list_matches()


@router.delete("/matches/{match_id}", status_code=200)
def remove_match(
    match_id: str,
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> dict[str, str]:
    """Delete a single match by ID (admin only).

    Requires the ``X-Admin-Token`` header to match the configured
    ``ADMIN_TOKEN`` environment variable.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    if not delete_match(match_id):
        raise HTTPException(status_code=404, detail="Match not found")
    return {"status": "deleted", "id": match_id}


@router.post("/matches", response_model=MatchResult, status_code=201)
def create_match(payload: MatchCreate) -> MatchResult:
    """Register a new match result.

    Validates inputs, normalises team names, writes to DB, and returns the
    saved match.  Both team names must belong to registered teams.
    """
    registered = get_team_names()
    t1 = payload.team1_name.strip().title()
    t2 = payload.team2_name.strip().title()
    if registered and t1 not in registered:
        raise HTTPException(status_code=400, detail=f"Team '{t1}' is not registered")
    if registered and t2 not in registered:
        raise HTTPException(status_code=400, detail=f"Team '{t2}' is not registered")
    return insert_match(payload)


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
def leaderboard() -> list[LeaderboardEntry]:
    """Return the leaderboard sorted by wins desc, then total score desc.

    Ties (equal scores) count as neither win nor loss.
    """
    return compute_leaderboard()


# ── Teams ─────────────────────────────────────────────────────────────


@router.get("/teams", response_model=list[Team])
def get_teams() -> list[Team]:
    """Return all registered teams."""
    return list_teams()


@router.get("/teams/names", response_model=list[str])
def get_names() -> list[str]:
    """Return a sorted list of registered team names (for dropdowns)."""
    return get_team_names()


# ── Admin ─────────────────────────────────────────────────────────────


@router.post("/admin/reset", status_code=200)
def admin_reset(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> dict[str, object]:
    """Delete all match results (admin only).

    Requires the ``X-Admin-Token`` header to match the configured
    ``ADMIN_TOKEN`` environment variable.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    deleted = reset_matches()
    return {"deleted": deleted, "status": "ok"}
