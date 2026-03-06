"""Shared test fixtures – mock Cosmos DB container so tests run without Azure credentials."""

from __future__ import annotations

from typing import Any

import pytest

from beerpong_api.db.client import set_container, set_state_container, set_teams_container


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
        return list(self._items.values())

    def delete_item(
        self, item: str | dict[str, object], partition_key: str | object, **kwargs: object
    ) -> None:
        item_id = item if isinstance(item, str) else str(item.get("id", ""))
        self._items.pop(item_id, None)


@pytest.fixture(autouse=True)
def _fake_db() -> FakeContainer:
    """Inject FakeContainers for matches, teams, and state before every test."""
    matches = FakeContainer()
    teams = FakeContainer()
    state = FakeContainer()
    set_container(matches)  # pyright: ignore[reportArgumentType]
    set_teams_container(teams)  # pyright: ignore[reportArgumentType]
    set_state_container(state)  # pyright: ignore[reportArgumentType]
    return matches
