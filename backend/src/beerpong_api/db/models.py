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
    team1_score: int = Field(..., ge=0, description="Score of team 1 (upper bound enforced server-side)")
    team2_score: int = Field(..., ge=0, description="Score of team 2 (upper bound enforced server-side)")
    heat: int = Field(1, ge=0, description="Heat count for the match")
    phase: str = Field(
        default="regular",
        description="Tournament phase at match time (regular | semifinals | finals)",
    )


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
    phase: str = "regular"
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
    """Persisted state tracking the current heat number and game settings."""

    id: str = "heat_state"
    current_heat: int = 1
    stored_matchups: list[HeatMatchup] = []
    sitting_out: list[str] = []
    heat_timer_started_at: str | None = None
    timer_duration: int = 480
    tables: int = 8
    max_cups: int = 6
    phase: str = "regular"
    knockout_seeds: list[str] = []
    frozen: bool = False
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
    teams_sitting_out: list[str] = []
    timer_duration: int = 480
    timer_started_at: str | None = None
    tables: int = 8
    max_cups: int = 6
    phase: str = "regular"
    knockout_seeds: list[str] = []
    frozen: bool = False
    wrap_up_allowed: bool = False
    knockout_allowed: bool = False


# ---------------------------------------------------------------------------
# Team models
# ---------------------------------------------------------------------------


class TeamCreate(BaseModel):
    """Payload for creating a new team.

    Phase 3: the ``members`` field of raw strings is replaced by ``member_ids``
    — a list of ``Player.id`` references. Zero to three ids are permitted so
    that admins can create an empty team awaiting assignment, or a 1-member
    late-walk-in team. CSV uploads enforce the 2–3 member rule separately.
    """

    name: str = Field(..., min_length=1, max_length=100, description="Team name")
    member_ids: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Player.id references; 0-3 permitted at the model level",
    )


class Team(BaseModel):
    """A persisted team.

    Phase 3: the legacy ``members: list[str]`` field is removed entirely. The
    canonical roster lives in ``member_ids`` (Player.id references), and each
    referenced Player carries a back-reference via ``Player.team_id``.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    member_ids: list[str] = Field(default_factory=list, max_length=3)
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    tournament_id: str = Field(default="default", alias="tournamentId")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Player models
# ---------------------------------------------------------------------------


class PlayerCreate(BaseModel):
    """Payload for creating a new player."""

    name: str = Field(..., min_length=1, max_length=100, description="Player name")


class Player(BaseModel):
    """A persisted player.

    Phase 3: ``team_id`` is a scalar back-reference to the Team a player is on.
    ``None`` means unassigned. The canonical roster is ``Team.member_ids``;
    this field is the maintained inverse for O(1) lookups.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    team_id: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    tournament_id: str = Field(default="default", alias="tournamentId")

    model_config = {"populate_by_name": True}


class PlayerTeamAssignment(BaseModel):
    """Payload for assigning (or un-assigning) a player to/from a team."""

    team_id: str | None = None


# ---------------------------------------------------------------------------
# CSV import models
# ---------------------------------------------------------------------------


class ImportError(BaseModel):  # noqa: N818 - domain name, not a Python exception
    """A single validation error encountered while parsing an import CSV."""

    row: int
    reason: str


class ImportSummary(BaseModel):
    """Outcome of a CSV upload — real or dry-run."""

    created_teams: list[str] = Field(default_factory=list)
    created_players: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    replaced_count: int = 0
    errors: list[ImportError] = Field(default_factory=list)
    dry_run: bool
