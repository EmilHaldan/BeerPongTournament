"""Tests for the /matches endpoint."""

from fastapi.testclient import TestClient

from beerpong_api.main import app

client = TestClient(app)


def test_create_match_success() -> None:
    resp = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 6,
            "team2_score": 4,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["team1_name"] == "Alpha"
    assert data["team2_name"] == "Beta"
    assert data["team1_score"] == 6
    assert data["team2_score"] == 4
    assert "id" in data
    assert "created_at" in data


def test_create_match_normalises_names() -> None:
    resp = client.post(
        "/matches",
        json={
            "team1_name": "  ALPHA  ",
            "team2_name": "beta",
            "team1_score": 5,
            "team2_score": 3,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["team1_name"] == "Alpha"
    assert data["team2_name"] == "Beta"


def test_create_match_rejects_negative_score() -> None:
    resp = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": -1,
            "team2_score": 5,
        },
    )
    assert resp.status_code == 422


def test_create_match_rejects_score_above_six() -> None:
    resp = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 7,
            "team2_score": 3,
        },
    )
    assert resp.status_code == 422


def test_create_match_rejects_empty_name() -> None:
    resp = client.post(
        "/matches",
        json={
            "team1_name": "",
            "team2_name": "Beta",
            "team1_score": 5,
            "team2_score": 3,
        },
    )
    assert resp.status_code == 422


def test_admin_reset_clears_matches() -> None:
    # Insert two matches
    for i in range(2):
        client.post(
            "/matches",
            json={
                "team1_name": "A",
                "team2_name": "B",
                "team1_score": i,
                "team2_score": 0,
            },
        )

    # Reset
    resp = client.post("/admin/reset", headers={"X-Admin-Token": "changeme"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 2
    assert data["status"] == "ok"


def test_admin_reset_rejects_bad_token() -> None:
    resp = client.post("/admin/reset", headers={"X-Admin-Token": "wrong"})
    assert resp.status_code == 403
