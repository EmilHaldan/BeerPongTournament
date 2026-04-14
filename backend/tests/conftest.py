"""Shared test fixtures – mock Cosmos DB container so tests run without Azure credentials."""

from __future__ import annotations

from typing import Any

import pytest

from beerpong_api.db.client import (
    set_container,
    set_players_container,
    set_state_container,
    set_teams_container,
)


class FakeContainer:
    """In-memory replacement for the Cosmos ContainerProxy."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def upsert_item(self, body: dict[str, object], **kwargs: object) -> dict[str, object]:
        doc_id = str(body.get("id", ""))
        self._items[doc_id] = dict(body)
        return dict(body)

    def query_items(
        self,
        query: str,
        parameters: list[dict[str, object]] | None = None,
        *,
        enable_cross_partition_query: bool = False,
        **kwargs: object,
    ) -> list[dict[str, Any]]:
        # Simple filter: return all items for the default tournament
        if "SELECT c.id FROM c" in query:
            return [{"id": item["id"]} for item in self._items.values()]

        # Honor @id and @team_id parameters used by the Phase 3 DAL queries.
        # Real Cosmos honors the WHERE clause; the fake must too for the DAL
        # tests that rely on point lookups.
        params = {p["name"]: p.get("value") for p in (parameters or [])}
        items: list[dict[str, Any]] = list(self._items.values())
        if "@id" in params:
            items = [i for i in items if i.get("id") == params["@id"]]
        if "@team_id" in params:
            items = [i for i in items if i.get("team_id") == params["@team_id"]]
        return items

    def delete_item(
        self, item: str | dict[str, object], partition_key: str | object, **kwargs: object
    ) -> None:
        item_id = item if isinstance(item, str) else str(item.get("id", ""))
        if item_id not in self._items:
            raise KeyError(item_id)
        self._items.pop(item_id)


@pytest.fixture(autouse=True)
def _fake_db() -> FakeContainer:
    """Inject FakeContainers for matches, teams, state, and players before every test."""
    matches = FakeContainer()
    teams = FakeContainer()
    state = FakeContainer()
    players = FakeContainer()
    set_container(matches)  # pyright: ignore[reportArgumentType]
    set_teams_container(teams)  # pyright: ignore[reportArgumentType]
    set_state_container(state)  # pyright: ignore[reportArgumentType]
    set_players_container(players)  # pyright: ignore[reportArgumentType]
    return matches
