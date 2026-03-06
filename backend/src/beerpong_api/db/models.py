"""Pydantic models for the beerpong API."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class MatchCreate(BaseModel):
    """Payload for creating a new match result."""

    team1_name: str = Field(..., min_length=1, max_length=100, description="Name of team 1")
    team2_name: str = Field(..., min_length=1, max_length=100, description="Name of team 2")
    team1_score: int = Field(..., ge=0, le=6, description="Score of team 1 (0–6)")
    team2_score: int = Field(..., ge=0, le=6, description="Score of team 2 (0–6)")


class MatchResult(BaseModel):
    """A persisted match result."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    team1_name: str
    team2_name: str
    team1_score: int
    team2_score: int
    tournament_id: str = Field(default="default", alias="tournamentId")

    model_config = {"populate_by_name": True}


class LeaderboardEntry(BaseModel):
    """One row of the leaderboard."""

    team_name: str
    total_score: int = 0
    total_wins: int = 0
    total_loss: int = 0


# ---------------------------------------------------------------------------
# Team models
# ---------------------------------------------------------------------------


class TeamCreate(BaseModel):
    """Payload for creating a new team."""

    name: str = Field(..., min_length=1, max_length=100, description="Team name")
    members: list[str] = Field(..., min_length=2, max_length=3, description="List of team member names (2-3)")


class Team(BaseModel):
    """A persisted team."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    members: list[str]
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    tournament_id: str = Field(default="default", alias="tournamentId")

    model_config = {"populate_by_name": True}
