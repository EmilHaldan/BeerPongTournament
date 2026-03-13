"""Tests for the /leaderboard endpoint."""

from fastapi.testclient import TestClient

from beerpong_api.main import app

client = TestClient(app)


def _post_match(t1: str, t2: str, s1: int, s2: int) -> None:
    resp = client.post(
        "/matches",
        json={
            "team1_name": t1,
            "team2_name": t2,
            "team1_score": s1,
            "team2_score": s2,
        },
    )
    assert resp.status_code == 201


def test_leaderboard_empty() -> None:
    resp = client.get("/leaderboard")
    assert resp.status_code == 200
    assert resp.json() == []


def test_leaderboard_single_match() -> None:
    _post_match("Alpha", "Beta", 6, 4)

    resp = client.get("/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    # Alpha won: 6 cups + 1 bonus = 7
    alpha = next(e for e in data if e["team_name"] == "Alpha")
    assert alpha["total_wins"] == 1
    assert alpha["total_loss"] == 0
    assert alpha["total_score"] == 7

    # Beta lost: 4 cups - 1 penalty = 3
    beta = next(e for e in data if e["team_name"] == "Beta")
    assert beta["total_wins"] == 0
    assert beta["total_loss"] == 1
    assert beta["total_score"] == 3


def test_leaderboard_tie_counts_as_neither() -> None:
    _post_match("Alpha", "Beta", 5, 5)

    resp = client.get("/leaderboard")
    data = resp.json()

    for entry in data:
        assert entry["total_wins"] == 0
        assert entry["total_loss"] == 0
        assert entry["total_score"] == 5


def test_leaderboard_sorted_by_wins_then_score() -> None:
    # Alpha beats Beta
    _post_match("Alpha", "Beta", 6, 2)
    # Gamma beats Beta with lower score
    _post_match("Gamma", "Beta", 3, 1)
    # Gamma beats Alpha (now Gamma has 2 wins)
    _post_match("Gamma", "Alpha", 5, 4)

    resp = client.get("/leaderboard")
    data = resp.json()

    names = [e["team_name"] for e in data]
    # Gamma: 2 wins, Alpha: 1 win, Beta: 0 wins
    assert names[0] == "Gamma"
    assert names[1] == "Alpha"
    assert names[2] == "Beta"
