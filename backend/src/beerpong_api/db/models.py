"""Pydantic models for the beerpong API."""

from __future__ import annotations

from datetime import UTC, datetime
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
    heat: int = Field(1, ge=0, description="Heat count for the match")


class MatchResult(BaseModel):
    """A persisted match result."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    team1_name: str
    team2_name: str
    team1_score: int
    team2_score: int
    heat: int = 1
    tournament_id: str = Field(default="default", alias="tournamentId")

    model_config = {"populate_by_name": True}


class LeaderboardEntry(BaseModel):
    """One row of the leaderboard."""

    team_name: str
    total_score: int = 0
    total_wins: int = 0
    total_loss: int = 0
    total_matches: int = 0


class HeatState(BaseModel):
    """Persisted state tracking the current heat number."""

    id: str = "heat_state"
    current_heat: int = 1
    stored_matchups: list[HeatMatchup] = []
    heat_timer_started_at: str | None = None
    tournament_id: str = Field(default="default", alias="tournamentId")

    model_config = {"populate_by_name": True}


class HeatMatchup(BaseModel):
    """A single matchup for a heat round."""

    team1_name: str
    team2_name: str
    team1_points: int = 0
    team2_points: int = 0
    team1_score: int | None = None
    team2_score: int | None = None
    recorded: bool = False
    winner: str | None = None


class HeatInfo(BaseModel):
    """Full heat information returned by the API."""

    current_heat: int
    matchups: list[HeatMatchup] = []
    teams_recorded: list[str] = []
    teams_not_recorded: list[str] = []
    timer_duration: int = 600
    timer_started_at: str | None = None


# ---------------------------------------------------------------------------
# Team models
# ---------------------------------------------------------------------------


class TeamCreate(BaseModel):
    """Payload for creating a new team."""

    name: str = Field(..., min_length=1, max_length=100, description="Team name")
    members: list[str] = Field(
        ..., min_length=2, max_length=3, description="List of team member names (2-3)"
    )


class Team(BaseModel):
    """A persisted team."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    members: list[str]
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    tournament_id: str = Field(default="default", alias="tournamentId")

    model_config = {"populate_by_name": True}
