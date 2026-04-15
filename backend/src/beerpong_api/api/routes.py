"""HTTP route definitions.

All routes delegate to DAL functions – they never access the DB client directly.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Header, HTTPException, UploadFile

from beerpong_api.dal.heat import (
    advance_heat,
    get_heat_info,
    is_frozen,
    reset_tournament,
    set_frozen,
    set_heat,
    set_max_cups,
    set_tables,
    set_timer_duration,
    start_heat_timer,
    start_knockout,
)
from beerpong_api.dal.leaderboard import compute_leaderboard
from beerpong_api.dal.matches import (
    DuplicateMatchError,
    delete_match,
    insert_match,
    list_matches,
    reset_matches,
)
from beerpong_api.dal.players import (
    assign_player_to_team,
    create_player,
    delete_player,
    list_players,
    wipe_all_players,
)
from beerpong_api.dal.teams import (
    create_team,
    delete_team,
    get_team_names,
    list_teams,
    replace_all_teams_and_players_from_csv,
    wipe_all_teams,
)
from beerpong_api.db.models import (
    HeatInfo,
    ImportSummary,
    LeaderboardEntry,
    MatchCreate,
    MatchResult,
    Player,
    PlayerCreate,
    PlayerTeamAssignment,
    Team,
    TeamCreate,
)
from beerpong_api.settings import get_settings

router = APIRouter()

# 256 KiB upload cap for the CSV uploader — rejects obvious wrong-file cases
# (photos, Excel binaries) while leaving ample headroom for large rosters.
_MAX_UPLOAD_BYTES = 256 * 1024


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

    if is_frozen():
        raise HTTPException(
            status_code=400,
            detail="Tournament is frozen. Unfreeze it in Game Settings to add scores.",
        )

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

    try:
        return insert_match(locked_payload)
    except (DuplicateMatchError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    """Create a new team (admin only).

    Accepts the Phase 3 ``TeamCreate`` shape (name + optional member_ids).
    When any member_id does not resolve to an existing player, the DAL raises
    ``ValueError`` and this endpoint returns HTTP 400.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    try:
        return create_team(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/teams/{team_id}", status_code=200)
def remove_team(
    team_id: str,
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> dict[str, str]:
    """Delete a team by ID (admin only).

    Players attached to the team are detached (their ``team_id`` is cleared)
    before the team document is removed. Players survive.
    """
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


@router.post("/admin/teams/upload-csv", response_model=ImportSummary, status_code=200)
async def upload_teams_csv(
    file: UploadFile = File(...),  # noqa: B008
    dry_run: bool = False,
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> ImportSummary:
    """Upload a team roster CSV (admin only).

    Strict all-or-nothing replacement semantics: when validation passes (and
    ``dry_run=False``) every team, player, match, and piece of heat/tournament
    state is wiped before the CSV is materialised under the new dual-write
    model. Validation failures return 400 with the full per-row error list so
    the frontend can surface each problem.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    # Size cap enforced server-side — upload.size is populated by FastAPI's
    # multipart parser when the Content-Length is known.
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {_MAX_UPLOAD_BYTES // 1024} KiB max",
        )

    raw = await file.read()
    # Belt-and-braces: re-check after the actual read in case size was missing.
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {_MAX_UPLOAD_BYTES // 1024} KiB max",
        )

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Can't ingest malformed CSV file",
                "errors": [{"row": 0, "reason": "file is not valid UTF-8"}],
            },
        ) from exc

    summary = replace_all_teams_and_players_from_csv(content, dry_run=dry_run)

    if summary.errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Can't ingest malformed CSV file",
                "errors": [e.model_dump() for e in summary.errors],
            },
        )

    return summary


# ── Players ───────────────────────────────────────────────────────────


@router.get("/players", response_model=list[Player])
def get_players() -> list[Player]:
    """Return all registered players."""
    return list_players()


@router.post("/players", response_model=Player, status_code=201)
def add_player(
    payload: PlayerCreate,
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> Player:
    """Create a new player (admin only)."""
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return create_player(payload)


@router.delete("/players/{player_id}", status_code=200)
def remove_player(
    player_id: str,
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> dict[str, str]:
    """Delete a player by ID (admin only).

    If the player is on a team, their id is removed from that team's
    ``member_ids`` before the player document is deleted.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    if not delete_player(player_id):
        raise HTTPException(status_code=404, detail="Player not found")
    return {"status": "deleted", "id": player_id}


@router.post("/players/{player_id}/team", response_model=Player, status_code=200)
def assign_team_to_player(
    player_id: str,
    payload: PlayerTeamAssignment,
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> Player:
    """Assign (or un-assign) a player to a team (admin only).

    The DAL maintains the dual-write invariant: old team's ``member_ids`` is
    updated, new team's ``member_ids`` is updated, and the player's
    ``team_id`` is refreshed in one logical operation.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    try:
        return assign_player_to_team(player_id, payload.team_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.delete("/admin/teams", status_code=200)
def admin_wipe_teams(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> dict[str, object]:
    """Delete every team and detach every player (admin only).

    Players survive with ``team_id=None``. Matches are untouched.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    deleted = wipe_all_teams()
    return {"deleted": deleted, "status": "ok"}


@router.post("/admin/start-knockout", response_model=HeatInfo, status_code=200)
def admin_start_knockout(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> HeatInfo:
    """Begin the top-4 single-elimination bracket (admin only).

    Returns 400 when the tournament is not in the regular phase or when
    fewer than 4 eligible teams (with members) are registered.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    try:
        return start_knockout()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/admin/reset-tournament", status_code=200)
def admin_reset_tournament(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> dict[str, object]:
    """Reset every match and every scrap of heat state (admin only).

    Wipes the matches container AND resets phase / knockout_seeds / frozen
    so the drunk-replay path is a single click.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    deleted = reset_matches()
    reset_tournament()
    return {"deleted": deleted, "status": "ok"}


@router.delete("/admin/players", status_code=200)
def admin_wipe_players(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> dict[str, object]:
    """Delete every player and clear every team's member_ids (admin only).

    Teams survive with empty ``member_ids``. Matches are untouched.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    deleted = wipe_all_players()
    return {"deleted": deleted, "status": "ok"}


# ── Heat ──────────────────────────────────────────────────────────────


@router.get("/heat", response_model=HeatInfo)
def get_heat() -> HeatInfo:
    """Return the current heat number and generated matchups.

    Matchups are determined by pairing teams with similar total scores.
    """
    return get_heat_info()


@router.post("/heat/start-next", response_model=HeatInfo, status_code=200)
def start_next_heat(
    payload: dict[str, bool] | None = None,
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> HeatInfo:
    """Advance to the next heat and return the new matchups (admin only).

    Optional body ``{"last_heat": bool}`` forces the games-balance scheduler
    path so teams with the fewest matches get priority, regardless of the
    table count.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    last_heat = bool((payload or {}).get("last_heat", False))
    try:
        return advance_heat(last_heat=last_heat)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.post("/heat/timer-duration", response_model=HeatInfo, status_code=200)
def set_timer_duration_route(
    payload: dict[str, int],
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> HeatInfo:
    """Set the heat timer duration in seconds (admin only)."""
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    seconds = payload.get("seconds")
    if seconds is None or seconds < 60:
        raise HTTPException(status_code=400, detail="Duration must be at least 60 seconds")
    return set_timer_duration(seconds)


@router.post("/heat/tables", response_model=HeatInfo, status_code=200)
def set_tables_route(
    payload: dict[str, int],
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> HeatInfo:
    """Set the number of physical tables available (admin only).

    Rejects counts below 1 or counts too low to prevent a team from sitting
    out two heats in a row (``count * 4 < len(team_names)``). Each heat seats
    ``2 * count`` teams; sitters total ``teams - 2 * count``. For every sitter
    to fit in the next heat, we need ``sitters <= 2 * count``, i.e.
    ``teams <= 4 * count``.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    count = payload.get("count")
    if count is None or count < 1:
        raise HTTPException(status_code=400, detail="Tables count must be at least 1")
    team_names = get_team_names()
    if count * 4 < len(team_names):
        raise HTTPException(
            status_code=400,
            detail=(
                "Tables count too low: a team would sit out two heats in a row. "
                "Need tables >= ceil(teams / 4)."
            ),
        )
    return set_tables(count)


@router.post("/heat/max-cups", response_model=HeatInfo, status_code=200)
def set_max_cups_route(
    payload: dict[str, int],
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> HeatInfo:
    """Set the per-team max cups (upper bound on a single match score)."""
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    count = payload.get("count")
    if count is None or count < 1:
        raise HTTPException(status_code=400, detail="Max cups must be at least 1")
    return set_max_cups(count)


@router.post("/heat/frozen", response_model=HeatInfo, status_code=200)
def set_frozen_route(
    payload: dict[str, bool],
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> HeatInfo:
    """Freeze or unfreeze the tournament (admin only).

    While frozen, POST /matches is rejected with HTTP 400.
    """
    settings = get_settings()
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    frozen = payload.get("frozen")
    if frozen is None:
        raise HTTPException(status_code=400, detail="Missing 'frozen' boolean in payload")
    return set_frozen(frozen)
