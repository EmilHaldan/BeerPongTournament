"""Tests for player management endpoints."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from beerpong_api.dal.players import create_player
from beerpong_api.dal.teams import create_team
from beerpong_api.db.models import PlayerCreate, TeamCreate
from beerpong_api.main import app

client = TestClient(app)

ADMIN = {"X-Admin-Token": "changeme"}


def _register_team(name: str, member_names: list[str]) -> str:
    """Create the supplied players via the DAL then create the team. Returns team id."""
    ids: list[str] = []
    for member_name in member_names:
        player = create_player(PlayerCreate(name=member_name))
        ids.append(player.id)
    team = create_team(TeamCreate(name=name, member_ids=ids))
    return team.id


# ── Player listing ───────────────────────────────────────────────────


def test_list_players_empty() -> None:
    resp = client.get("/players")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Player creation ──────────────────────────────────────────────────


def test_create_player_success() -> None:
    resp = client.post(
        "/players",
        json={"name": "Alice"},
        headers={"X-Admin-Token": "changeme"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Alice"
    assert "id" in data
    assert "created_at" in data


def test_create_player_rejects_bad_token() -> None:
    resp = client.post(
        "/players",
        json={"name": "Alice"},
        headers={"X-Admin-Token": "wrong"},
    )
    assert resp.status_code == 403


def test_create_player_normalises_name() -> None:
    resp = client.post(
        "/players",
        json={"name": "  alice  "},
        headers={"X-Admin-Token": "changeme"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Alice"


def test_create_player_rejects_empty_name() -> None:
    resp = client.post(
        "/players",
        json={"name": ""},
        headers={"X-Admin-Token": "changeme"},
    )
    assert resp.status_code == 422


# ── Player deletion ──────────────────────────────────────────────────


def test_delete_player_success() -> None:
    create_resp = client.post(
        "/players",
        json={"name": "Bob"},
        headers={"X-Admin-Token": "changeme"},
    )
    player_id = create_resp.json()["id"]

    resp = client.delete(
        f"/players/{player_id}",
        headers={"X-Admin-Token": "changeme"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


def test_delete_player_not_found() -> None:
    resp = client.delete(
        f"/players/{uuid4()}",
        headers={"X-Admin-Token": "changeme"},
    )
    assert resp.status_code == 404


def test_delete_player_rejects_bad_token() -> None:
    resp = client.delete(
        f"/players/{uuid4()}",
        headers={"X-Admin-Token": "wrong"},
    )
    assert resp.status_code == 403


# ── DELETE /admin/players: wipe-all semantics ────────────────────────


def test_wipe_all_players_clears_team_rosters_and_keeps_matches() -> None:
    """Wiping players deletes every player, empties every team's member_ids, keeps matches."""
    # Arrange: 2 teams × 2 players, plus a match between them.
    _register_team("Foxes", ["F1", "F2"])
    _register_team("Wolves", ["W1", "W2"])
    client.post(
        "/matches",
        json={
            "team1_name": "Foxes",
            "team2_name": "Wolves",
            "team1_score": 6,
            "team2_score": 2,
        },
    )
    pre_players = client.get("/players").json()
    assert len(pre_players) == 4
    pre_matches = client.get("/matches").json()
    assert len(pre_matches) == 1

    # Act
    resp = client.delete("/admin/players", headers=ADMIN)

    # Assert
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["deleted"] == 4

    assert client.get("/players").json() == []

    after_teams = client.get("/teams").json()
    assert len(after_teams) == 2
    assert all(t["member_ids"] == [] for t in after_teams)

    after_matches = client.get("/matches").json()
    assert len(after_matches) == 1


def test_wipe_all_players_empty_state() -> None:
    """Wiping players with no players present returns 200 and deleted==0."""
    # Arrange: nothing seeded.

    # Act
    resp = client.delete("/admin/players", headers=ADMIN)

    # Assert
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0, "status": "ok"}


def test_wipe_all_players_rejects_bad_token() -> None:
    """Wrong admin token → 403 and no state change."""
    # Arrange
    _register_team("Keep", ["Ka", "Kb"])

    # Act
    resp = client.delete("/admin/players", headers={"X-Admin-Token": "wrong"})

    # Assert
    assert resp.status_code == 403
    players = client.get("/players").json()
    assert len(players) == 2
