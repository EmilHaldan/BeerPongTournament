"""Cosmos DB client initialisation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.container import ContainerProxy

from beerpong_api.settings import Settings

if TYPE_CHECKING:
    pass


@runtime_checkable
class ContainerLike(Protocol):
    """Protocol describing the subset of ContainerProxy we use."""

    def upsert_item(self, body: dict[str, object], **kwargs: object) -> dict[str, object]: ...  # pyright: ignore[reportMissingSuperCall]
    def query_items(self, query: str, parameters: list[dict[str, object]] | None = None, *, enable_cross_partition_query: bool = False, **kwargs: object) -> object: ...  # pyright: ignore[reportMissingSuperCall]
    def delete_item(self, item: str | dict[str, object], partition_key: str | object, **kwargs: object) -> None: ...  # pyright: ignore[reportMissingSuperCall]


# ── Matches container ─────────────────────────────────────────────────
_container: ContainerLike | None = None

# ── Teams container ───────────────────────────────────────────────────
_teams_container: ContainerLike | None = None


def get_container() -> ContainerLike:
    """Return the matches Cosmos container proxy (singleton)."""
    global _container  # noqa: PLW0603
    if _container is None:
        raise RuntimeError("Database not initialised – call init_db() first")
    return _container


def get_teams_container() -> ContainerLike:
    """Return the teams Cosmos container proxy (singleton)."""
    global _teams_container  # noqa: PLW0603
    if _teams_container is None:
        raise RuntimeError("Database not initialised – call init_db() first")
    return _teams_container


def set_container(container: ContainerLike) -> None:
    """Override the matches container (used in tests)."""
    global _container  # noqa: PLW0603
    _container = container


def set_teams_container(container: ContainerLike) -> None:
    """Override the teams container (used in tests)."""
    global _teams_container  # noqa: PLW0603
    _teams_container = container


def init_db(settings: Settings) -> None:
    """Initialise the Cosmos DB client from application settings."""
    global _container, _teams_container  # noqa: PLW0603

    client = CosmosClient(settings.COSMOS_ENDPOINT, credential=settings.COSMOS_KEY)
    database = client.create_database_if_not_exists(id=settings.COSMOS_DATABASE)
    _container = database.create_container_if_not_exists(
        id=settings.COSMOS_CONTAINER,
        partition_key=PartitionKey(path="/tournamentId"),
    )
    _teams_container = database.create_container_if_not_exists(
        id="teams",
        partition_key=PartitionKey(path="/tournamentId"),
    )


def init_local_db(db_path: str = "beerpong_local.db") -> None:
    """Initialise a local SQLite database for development."""
    global _container, _teams_container  # noqa: PLW0603
    from pathlib import Path

    from beerpong_api.db.sqlite_container import create_sqlite_containers

    matches_c, teams_c = create_sqlite_containers(db_path=Path(db_path))
    _container = matches_c  # pyright: ignore[reportAssignmentType]
    _teams_container = teams_c  # pyright: ignore[reportAssignmentType]
