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
            "heat": 2,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["team1_name"] == "Alpha"
    assert data["team2_name"] == "Beta"
    assert data["team1_score"] == 6
    assert data["team2_score"] == 4
    # heat is locked to the current heat (defaults to 1), regardless of input
    assert data["heat"] == 1
    assert "id" in data
    assert "created_at" in data


def test_create_match_heat_defaults_to_zero() -> None:
    resp = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 5,
            "team2_score": 3,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["heat"] == 1


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
    # Insert two matches — distinct team pairs so the duplicate-match guard
    # doesn't reject the second one.
    pairs = [("A", "B"), ("C", "D")]
    for i, (t1, t2) in enumerate(pairs):
        client.post(
            "/matches",
            json={
                "team1_name": t1,
                "team2_name": t2,
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


# ── Duplicate-match guard ─────────────────────────────────────────────

_DUPLICATE_MESSAGE = "Match has already been submitted, talk to Emil or Sophia to reset it"


def test_create_match_duplicate_pair_same_heat_returns_400() -> None:
    # Arrange: first submission succeeds
    first = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 6,
            "team2_score": 4,
        },
    )
    assert first.status_code == 201

    # Act: second submission with identical pair + heat
    second = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 3,
            "team2_score": 2,
        },
    )

    # Assert
    assert second.status_code == 400
    assert second.json()["detail"] == _DUPLICATE_MESSAGE


def test_create_match_reversed_pair_same_heat_returns_400() -> None:
    # Arrange
    first = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 5,
            "team2_score": 1,
        },
    )
    assert first.status_code == 201

    # Act: swap team1/team2 — still the same unordered pair at the same heat
    second = client.post(
        "/matches",
        json={
            "team1_name": "Beta",
            "team2_name": "Alpha",
            "team1_score": 2,
            "team2_score": 4,
        },
    )

    # Assert
    assert second.status_code == 400
    assert second.json()["detail"] == _DUPLICATE_MESSAGE


def test_create_match_same_pair_different_heat_succeeds() -> None:
    # Arrange: submit at current heat (1)
    first = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 6,
            "team2_score": 4,
        },
    )
    assert first.status_code == 201

    # Advance server heat to 2
    bump = client.post(
        "/heat/set",
        json={"heat": 2},
        headers={"X-Admin-Token": "changeme"},
    )
    assert bump.status_code == 200

    # Act: same pair, new heat
    second = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 3,
            "team2_score": 5,
        },
    )

    # Assert
    assert second.status_code == 201
    assert second.json()["heat"] == 2


def test_create_match_different_pair_same_heat_succeeds() -> None:
    # Arrange
    first = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 6,
            "team2_score": 4,
        },
    )
    assert first.status_code == 201

    # Act: different pair, same heat
    second = client.post(
        "/matches",
        json={
            "team1_name": "Gamma",
            "team2_name": "Delta",
            "team1_score": 5,
            "team2_score": 3,
        },
    )

    # Assert
    assert second.status_code == 201
