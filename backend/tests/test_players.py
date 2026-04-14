"""Tests for player management endpoints."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from beerpong_api.main import app

client = TestClient(app)


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
