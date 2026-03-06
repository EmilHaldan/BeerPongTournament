"""SQLite-backed implementation of ContainerLike for local development.

Stores documents as JSON blobs in named tables, mimicking the Cosmos SDK
methods used by the DAL (upsert_item, query_items, delete_item).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_DEFAULT_DB_PATH = Path("beerpong_local.db")


class SqliteContainer:
    """Drop-in replacement for Cosmos ContainerProxy (local dev only).

    Each instance is scoped to a single logical table (e.g. ``matches`` or
    ``teams``).
    """

    def __init__(self, conn: sqlite3.Connection, table_name: str = "matches") -> None:
        self._conn = conn
        self._table = table_name
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
                id TEXT PRIMARY KEY,
                tournament_id TEXT NOT NULL,
                data TEXT NOT NULL
            )
            """,
        )
        self._conn.commit()

    # ── ContainerLike interface ───────────────────────────────────────

    def upsert_item(self, body: dict[str, object], **kwargs: object) -> dict[str, object]:
        doc_id = str(body.get("id", ""))
        tournament_id = str(body.get("tournamentId", "default"))
        data = json.dumps(body)
        self._conn.execute(
            f"INSERT OR REPLACE INTO {self._table} (id, tournament_id, data) VALUES (?, ?, ?)",
            (doc_id, tournament_id, data),
        )
        self._conn.commit()
        return dict(body)

    def query_items(
        self,
        query: str,
        parameters: list[dict[str, object]] | None = None,
        *,
        enable_cross_partition_query: bool = False,
        **kwargs: object,
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            f"SELECT data FROM {self._table} WHERE tournament_id = ? ORDER BY id",
            ("default",),
        ).fetchall()

        docs: list[dict[str, Any]] = [json.loads(row[0]) for row in rows]

        # Handle "SELECT c.id FROM c ..." – return only {id: ...}
        if "SELECT c.id FROM c" in query:
            return [{"id": doc["id"]} for doc in docs]

        # For "ORDER BY c.created_at DESC" – sort in Python
        if "ORDER BY c.created_at DESC" in query:
            docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)

        return docs

    def delete_item(
        self, item: str | dict[str, object], partition_key: str | object, **kwargs: object
    ) -> None:
        item_id = item if isinstance(item, str) else str(item.get("id", ""))
        self._conn.execute(f"DELETE FROM {self._table} WHERE id = ?", (item_id,))
        self._conn.commit()


def create_sqlite_containers(
    db_path: Path = _DEFAULT_DB_PATH,
) -> tuple[SqliteContainer, SqliteContainer]:
    """Create matches + teams containers sharing one SQLite connection."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    matches = SqliteContainer(conn, table_name="matches")
    teams = SqliteContainer(conn, table_name="teams")
    return matches, teams
