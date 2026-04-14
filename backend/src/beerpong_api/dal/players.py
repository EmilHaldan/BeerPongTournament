"""DAL functions for player management.

Phase 3 adds team-membership awareness:

* Every player has a scalar ``team_id`` back-reference (canonical roster still
  lives on the Team).
* All mutations that can change the roster (create/delete/assign) maintain
  the dual-write invariant: Team.member_ids and Player.team_id stay in sync.
"""

from __future__ import annotations

from beerpong_api.dal._normalize import normalize_name
from beerpong_api.db.client import get_players_container, get_teams_container
from beerpong_api.db.models import Player, PlayerCreate, Team

_DEFAULT_PARTITION = "default"


def create_player(payload: PlayerCreate) -> Player:
    """Create and persist a new (unassigned) player."""
    player = Player(name=normalize_name(payload.name))

    container = get_players_container()
    doc = player.model_dump(by_alias=True)
    container.upsert_item(doc)
    return player


def list_players() -> list[Player]:
    """Return all registered players in the default tournament partition."""
    container = get_players_container()
    query = "SELECT * FROM c WHERE c.tournamentId = @tid"
    params: list[dict[str, object]] = [{"name": "@tid", "value": _DEFAULT_PARTITION}]
    items = container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False,
    )
    return [Player(**item) for item in items]  # type: ignore[reportUnknownArgumentType]


def get_player_by_id(player_id: str) -> Player | None:
    """Fetch a single Player by id, or None if not found."""
    container = get_players_container()
    query = "SELECT * FROM c WHERE c.id = @id AND c.tournamentId = @tid"
    params: list[dict[str, object]] = [
        {"name": "@id", "value": player_id},
        {"name": "@tid", "value": _DEFAULT_PARTITION},
    ]
    raw = container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False,
    )
    items = list(raw)  # pyright: ignore[reportArgumentType]
    if not items:
        return None
    return Player(**items[0])  # pyright: ignore[reportArgumentType]


def list_players_by_team(team_id: str) -> list[Player]:
    """Return every player whose ``team_id`` matches the given team."""
    container = get_players_container()
    query = "SELECT * FROM c WHERE c.tournamentId = @tid AND c.team_id = @team_id"
    params: list[dict[str, object]] = [
        {"name": "@tid", "value": _DEFAULT_PARTITION},
        {"name": "@team_id", "value": team_id},
    ]
    items = container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False,
    )
    return [Player(**item) for item in items]  # type: ignore[reportUnknownArgumentType]


def _get_team_raw(team_id: str) -> dict[str, object] | None:
    """Fetch a team doc directly — local helper to avoid a players → teams
    → players import cycle."""
    container = get_teams_container()
    query = "SELECT * FROM c WHERE c.id = @id AND c.tournamentId = @tid"
    params: list[dict[str, object]] = [
        {"name": "@id", "value": team_id},
        {"name": "@tid", "value": _DEFAULT_PARTITION},
    ]
    raw = container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False,
    )
    items = list(raw)  # pyright: ignore[reportArgumentType]
    if not items:
        return None
    return dict(items[0])  # pyright: ignore[reportArgumentType]


def _write_team_members(team_doc: dict[str, object], member_ids: list[str]) -> None:
    """Persist an updated member_ids list on an existing team doc."""
    team_doc["member_ids"] = member_ids
    team = Team(**team_doc)  # pyright: ignore[reportArgumentType]
    get_teams_container().upsert_item(team.model_dump(by_alias=True))


def assign_player_to_team(player_id: str, team_id: str | None) -> Player:
    """Assign (or un-assign) a player to a team — dual-write maintained.

    Behaviour:

    * If the player does not exist → ``ValueError``.
    * If ``team_id`` is not None and the target team does not exist →
      ``ValueError``.
    * If the player's current team equals the target → no-op, returns the
      current ``Player``.
    * Otherwise the player's id is removed from the old team's ``member_ids``
      (when applicable), added to the new team's ``member_ids`` (when
      applicable), and the player's ``team_id`` is updated.

    The route layer converts any ``ValueError`` into an HTTP 400.
    """
    player = get_player_by_id(player_id)
    if player is None:
        raise ValueError(f"Player '{player_id}' not found")

    if team_id is not None:
        target_team_raw = _get_team_raw(team_id)
        if target_team_raw is None:
            raise ValueError(f"Team '{team_id}' not found")
    else:
        target_team_raw = None

    # No-op when the assignment doesn't change.
    if player.team_id == team_id:
        return player

    # Remove from previous team, if any.
    if player.team_id is not None:
        old_team_raw = _get_team_raw(player.team_id)
        if old_team_raw is not None:
            old_members = [m for m in list(old_team_raw.get("member_ids", [])) if m != player_id]  # pyright: ignore[reportArgumentType]
            _write_team_members(old_team_raw, old_members)

    # Update the player.
    player.team_id = team_id
    get_players_container().upsert_item(player.model_dump(by_alias=True))

    # Add to the new team, if any.
    if target_team_raw is not None:
        new_members = list(target_team_raw.get("member_ids", []))  # pyright: ignore[reportArgumentType]
        if player_id not in new_members:
            new_members.append(player_id)
        _write_team_members(target_team_raw, new_members)

    return player


def delete_player(player_id: str) -> bool:
    """Delete a player, detaching them from their team first.

    Dual-write invariant: if the player has a team, their id is removed from
    that team's ``member_ids`` before the player document is deleted so no
    dangling references remain. Returns True if the player existed and was
    deleted, False otherwise (idempotent on re-delete).
    """
    player = get_player_by_id(player_id)
    if player is None:
        return False

    if player.team_id is not None:
        team_raw = _get_team_raw(player.team_id)
        if team_raw is not None:
            surviving = [m for m in list(team_raw.get("member_ids", [])) if m != player_id]  # pyright: ignore[reportArgumentType]
            _write_team_members(team_raw, surviving)

    container = get_players_container()
    try:
        container.delete_item(item=player_id, partition_key=_DEFAULT_PARTITION)
        return True
    except Exception:
        return False
