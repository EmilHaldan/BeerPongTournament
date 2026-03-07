"""HTTP route definitions.

All routes delegate to DAL functions – they never access the DB client directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from beerpong_api.dal.heat import advance_heat, get_heat_info, set_heat, start_heat_timer
from beerpong_api.dal.leaderboard import compute_leaderboard
from beerpong_api.dal.matches import delete_match, insert_match, list_matches, reset_matches
from beerpong_api.dal.teams import create_team, delete_team, get_team_names, list_teams
from beerpong_api.db.models import (
    HeatInfo,
    LeaderboardEntry,
    MatchCreate,
    MatchResult,
    Team,
    TeamCreate,
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
    The heat value is locked to the current heat.
    """
    from beerpong_api.dal.heat import get_current_heat

    registered = get_team_names()
    t1 = payload.team1_name.strip().title()
    t2 = payload.team2_name.strip().title()
    if registered and t1 not in registered:
        raise HTTPException(status_code=400, detail=f"Team '{t1}' is not registered")
    if registered and t2 not in registered:
        raise HTTPException(status_code=400, detail=f"Team '{t2}' is not registered")

    # Override heat with the current heat value
    current_heat = get_current_heat()
    payload_dict = payload.model_dump()
    payload_dict["heat"] = current_heat
    locked_payload = MatchCreate(**payload_dict)

    return insert_match(locked_payload)


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


@router.post("/teams", response_model=Team, status_code=201)
def add_team(
    payload: TeamCreate,
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> Team:
    """Create a new team (admin only)."""
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return create_team(payload)


@router.delete("/teams/{team_id}", status_code=200)
def remove_team(
    team_id: str,
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> dict[str, str]:
    """Delete a team by ID (admin only)."""
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    if not delete_team(team_id):
        raise HTTPException(status_code=404, detail="Team not found")
    return {"status": "deleted", "id": team_id}


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


@router.post("/admin/verify", status_code=200)
def admin_verify(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> dict[str, str]:
    """Verify the admin token without performing any action."""
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return {"status": "ok"}


# ── Heat ──────────────────────────────────────────────────────────────


@router.get("/heat", response_model=HeatInfo)
def get_heat() -> HeatInfo:
    """Return the current heat number and generated matchups.

    Matchups are determined by pairing teams with similar total scores.
    """
    return get_heat_info()


@router.post("/heat/start-next", response_model=HeatInfo, status_code=200)
def start_next_heat(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> HeatInfo:
    """Advance to the next heat and return the new matchups (admin only)."""
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return advance_heat()


@router.post("/heat/set", response_model=HeatInfo, status_code=200)
def set_heat_value(
    payload: dict[str, int],
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> HeatInfo:
    """Set the heat to a specific value (admin only)."""
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    heat_number = payload.get("heat")
    if heat_number is None or heat_number < 1:
        raise HTTPException(status_code=400, detail="Heat must be a positive integer")
    return set_heat(heat_number)


@router.post("/heat/start-timer", response_model=HeatInfo, status_code=200)
def start_timer(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> HeatInfo:
    """Start the heat countdown timer (admin only)."""
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return start_heat_timer()
