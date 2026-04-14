"""DAL functions for player management."""

from __future__ import annotations

from beerpong_api.db.client import get_players_container
from beerpong_api.db.models import Player, PlayerCreate


def _normalize_name(name: str) -> str:
    """Normalize a name: strip whitespace and title-case."""
    return name.strip().title()


def create_player(payload: PlayerCreate) -> Player:
    """Create and persist a new player."""
    player = Player(name=_normalize_name(payload.name))

    container = get_players_container()
    doc = player.model_dump(by_alias=True)
    container.upsert_item(doc)
    return player


def list_players() -> list[Player]:
    """Return all registered players."""
    container = get_players_container()
    query = "SELECT * FROM c WHERE c.tournamentId = 'default'"
    items = container.query_items(query=query, enable_cross_partition_query=False)
    return [Player(**item) for item in items]  # type: ignore[reportUnknownArgumentType]


def delete_player(player_id: str) -> bool:
    """Delete a player by ID. Returns True if deleted, False if not found."""
    container = get_players_container()
    try:
        container.delete_item(item=player_id, partition_key="default")
        return True
    except Exception:
        return False
