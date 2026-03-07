"""Tests for the /heat endpoints."""

from fastapi.testclient import TestClient

from beerpong_api.main import app
from beerpong_api.settings import get_settings

client = TestClient(app)
ADMIN_TOKEN = get_settings().ADMIN_TOKEN


def _register_team(name: str, members: list[str]) -> None:
    """Helper to register a team via the DAL."""
    from beerpong_api.dal.teams import create_team
    from beerpong_api.db.models import TeamCreate

    create_team(TeamCreate(name=name, members=members))


def test_get_heat_default() -> None:
    """Default heat should be 1 with no matchups (no teams)."""
    resp = client.get("/heat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_heat"] == 1
    assert data["matchups"] == []


def test_get_heat_with_teams() -> None:
    """With registered teams, matchups should be generated."""
    _register_team("Alpha", ["Alice", "Bob"])
    _register_team("Beta", ["Carol", "Dave"])
    _register_team("Gamma", ["Eve", "Frank"])
    _register_team("Delta", ["Grace", "Heidi"])

    resp = client.get("/heat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_heat"] == 1
    assert len(data["matchups"]) == 2  # 4 teams -> 2 matchups


def test_start_next_heat() -> None:
    """Starting next heat should increment the counter."""
    resp = client.post("/heat/start-next", headers={"X-Admin-Token": ADMIN_TOKEN})
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_heat"] == 2

    # Do it again
    resp = client.post("/heat/start-next", headers={"X-Admin-Token": ADMIN_TOKEN})
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_heat"] == 3


def test_start_next_heat_rejects_bad_token() -> None:
    """Starting next heat with wrong token should be rejected."""
    resp = client.post("/heat/start-next", headers={"X-Admin-Token": "wrong"})
    assert resp.status_code == 403


def test_set_heat() -> None:
    """Setting heat to a specific value should work."""
    resp = client.post(
        "/heat/set",
        json={"heat": 5},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_heat"] == 5

    # Verify it persisted
    resp = client.get("/heat")
    assert resp.json()["current_heat"] == 5


def test_set_heat_rejects_bad_token() -> None:
    """Setting heat with wrong token should be rejected."""
    resp = client.post(
        "/heat/set",
        json={"heat": 5},
        headers={"X-Admin-Token": "wrong"},
    )
    assert resp.status_code == 403


def test_set_heat_rejects_invalid_value() -> None:
    """Setting heat to 0 or negative should be rejected."""
    resp = client.post(
        "/heat/set",
        json={"heat": 0},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp.status_code == 400


def test_match_uses_current_heat() -> None:
    """Matches should be locked to the current heat value."""
    # Default heat is 1
    resp = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 3,
            "team2_score": 2,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["heat"] == 1

    # Advance to heat 2
    client.post("/heat/start-next", headers={"X-Admin-Token": ADMIN_TOKEN})

    # New match should use heat 2
    resp = client.post(
        "/matches",
        json={
            "team1_name": "Alpha",
            "team2_name": "Beta",
            "team1_score": 4,
            "team2_score": 1,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["heat"] == 2


def test_matchups_sorted_by_score() -> None:
    """Teams with higher scores should be paired together in the NEXT heat."""
    _register_team("Alpha", ["Alice", "Bob"])
    _register_team("Beta", ["Carol", "Dave"])
    _register_team("Gamma", ["Eve", "Frank"])
    _register_team("Delta", ["Grace", "Heidi"])

    # Record some matches so teams have different scores
    client.post(
        "/matches",
        json={"team1_name": "Alpha", "team2_name": "Delta", "team1_score": 6, "team2_score": 0},
    )
    client.post(
        "/matches",
        json={"team1_name": "Beta", "team2_name": "Gamma", "team1_score": 5, "team2_score": 1},
    )

    # Advance to heat 2 so matchups are regenerated based on new standings
    client.post("/heat/start-next", headers={"X-Admin-Token": ADMIN_TOKEN})

    resp = client.get("/heat")
    data = resp.json()
    matchups = data["matchups"]
    assert len(matchups) == 2

    # First matchup should be the top two teams (Alpha=6, Beta=5)
    first = matchups[0]
    assert first["team1_name"] == "Alpha"
    assert first["team2_name"] == "Beta"

    # Second matchup should be the bottom two teams (Gamma=1, Delta=0)
    second = matchups[1]
    assert second["team1_name"] == "Gamma"
    assert second["team2_name"] == "Delta"


def test_leaderboard_includes_total_matches() -> None:
    """Leaderboard should include total_matches count."""
    _register_team("Alpha", ["Alice", "Bob"])
    _register_team("Beta", ["Carol", "Dave"])

    client.post(
        "/matches",
        json={"team1_name": "Alpha", "team2_name": "Beta", "team1_score": 3, "team2_score": 2},
    )
    client.post(
        "/matches",
        json={"team1_name": "Alpha", "team2_name": "Beta", "team1_score": 4, "team2_score": 1},
    )

    resp = client.get("/leaderboard")
    data = resp.json()
    for entry in data:
        assert "total_matches" in entry
        assert entry["total_matches"] == 2  # Both teams played 2 matches


def test_heat_shows_recorded_status() -> None:
    """Heat info should indicate which matchups have recorded scores."""
    _register_team("Alpha", ["Alice", "Bob"])
    _register_team("Beta", ["Carol", "Dave"])
    _register_team("Gamma", ["Eve", "Frank"])
    _register_team("Delta", ["Grace", "Heidi"])

    # No matches yet – all matchups should be unrecorded
    resp = client.get("/heat")
    data = resp.json()
    for m in data["matchups"]:
        assert m["recorded"] is False
        assert m["winner"] is None
        assert m["team1_score"] is None
        assert m["team2_score"] is None
    assert data["teams_not_recorded"] != []
    assert data["teams_recorded"] == []

    # Record one match for heat 1
    client.post(
        "/matches",
        json={"team1_name": "Alpha", "team2_name": "Beta", "team1_score": 5, "team2_score": 2},
    )

    resp = client.get("/heat")
    data = resp.json()
    recorded_matchup = next(
        m for m in data["matchups"] if {m["team1_name"], m["team2_name"]} == {"Alpha", "Beta"}
    )
    assert recorded_matchup["recorded"] is True
    assert recorded_matchup["winner"] == "Alpha"
    assert recorded_matchup["team1_score"] is not None
    assert recorded_matchup["team2_score"] is not None

    pending_matchup = next(
        m for m in data["matchups"] if {m["team1_name"], m["team2_name"]} != {"Alpha", "Beta"}
    )
    assert pending_matchup["recorded"] is False
    assert pending_matchup["winner"] is None

    assert "Alpha" in data["teams_recorded"]
    assert "Beta" in data["teams_recorded"]
    assert len(data["teams_not_recorded"]) == 2
