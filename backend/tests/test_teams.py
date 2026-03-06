"""Tests for team management and CSV loading."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from beerpong_api.dal.teams import create_team, load_teams_from_csv
from beerpong_api.db.models import TeamCreate
from beerpong_api.main import app

client = TestClient(app)


# ── Helper ────────────────────────────────────────────────────────────

def _register_team(name: str, members: list[str]) -> None:
    """Register a team via the DAL (no HTTP endpoint for team creation)."""
    create_team(TeamCreate(name=name, members=members))


# ── Team model validation ────────────────────────────────────────────


def test_team_create_rejects_one_member() -> None:
    """TeamCreate model requires at least 2 members."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TeamCreate(name="Solo", members=["OnlyOne"])


def test_team_create_rejects_four_members() -> None:
    """TeamCreate model allows at most 3 members."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TeamCreate(name="Big", members=["A", "B", "C", "D"])


def test_team_create_allows_two_members() -> None:
    _register_team("Duo", ["Alice", "Bob"])
    names = client.get("/teams/names").json()
    assert "Duo" in names


def test_team_create_allows_three_members() -> None:
    _register_team("Trio", ["Alice", "Bob", "Carol"])
    teams = client.get("/teams").json()
    trio = [t for t in teams if t["name"] == "Trio"][0]
    assert len(trio["members"]) == 3


# ── Team listing ─────────────────────────────────────────────────────


def test_list_teams_empty() -> None:
    resp = client.get("/teams")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_teams_after_create() -> None:
    _register_team("Bravo", ["Carol", "Dave"])
    resp = client.get("/teams")
    assert resp.status_code == 200
    teams = resp.json()
    assert len(teams) == 1
    assert teams[0]["name"] == "Bravo"


def test_get_team_names() -> None:
    _register_team("Zulu", ["Z1", "Z2"])
    _register_team("Alpha", ["A1", "A2"])
    resp = client.get("/teams/names")
    assert resp.status_code == 200
    names = resp.json()
    assert names == ["Alpha", "Zulu"]


# ── Match / team interaction ─────────────────────────────────────────


def test_match_requires_registered_team() -> None:
    _register_team("Registered", ["R1", "R2"])
    resp = client.post(
        "/matches",
        json={
            "team1_name": "Registered",
            "team2_name": "Unknown",
            "team1_score": 5,
            "team2_score": 3,
        },
    )
    assert resp.status_code == 400
    assert "Unknown" in resp.json()["detail"]


def test_match_succeeds_with_registered_teams() -> None:
    _register_team("Foxes", ["F1", "F2"])
    _register_team("Wolves", ["W1", "W2"])
    resp = client.post(
        "/matches",
        json={
            "team1_name": "Foxes",
            "team2_name": "Wolves",
            "team1_score": 6,
            "team2_score": 4,
        },
    )
    assert resp.status_code == 201


# ── CSV auto-load tests ──────────────────────────────────────────────


def test_load_teams_from_csv_creates_teams() -> None:
    csv_content = "team_name,member1,member2\nAlpha,Alice,Bob\nBravo,Carol,Dave\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        f.flush()
        result = load_teams_from_csv(f.name)

    assert len(result["created"]) == 2
    assert "Alpha" in result["created"]
    assert "Bravo" in result["created"]

    names = client.get("/teams/names").json()
    assert "Alpha" in names
    assert "Bravo" in names
    Path(f.name).unlink(missing_ok=True)


def test_load_teams_from_csv_skips_duplicates() -> None:
    _register_team("Alpha", ["Alice", "Bob"])

    csv_content = "team_name,member1,member2\nAlpha,Alice,Bob\nBravo,Carol,Dave\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        f.flush()
        result = load_teams_from_csv(f.name)

    assert len(result["created"]) == 1
    assert len(result["skipped"]) == 1
    assert "Bravo" in result["created"]
    assert "Alpha" in result["skipped"]
    Path(f.name).unlink(missing_ok=True)


def test_load_teams_from_csv_missing_file() -> None:
    result = load_teams_from_csv("/nonexistent/teams.csv")
    assert result == {"created": [], "skipped": []}


def test_load_teams_from_csv_skips_rows_with_too_few_members() -> None:
    csv_content = "team_name,member1,member2\nSolo,OnlyOne\nValid,Alice,Bob\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        f.flush()
        result = load_teams_from_csv(f.name)

    assert len(result["created"]) == 1
    assert "Valid" in result["created"]
    Path(f.name).unlink(missing_ok=True)


def test_load_teams_from_csv_allows_three_members() -> None:
    csv_content = "team_name,member1,member2,member3\nTrio,Alice,Bob,Carol\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        f.flush()
        result = load_teams_from_csv(f.name)

    assert len(result["created"]) == 1
    assert "Trio" in result["created"]

    teams = client.get("/teams").json()
    trio = [t for t in teams if t["name"] == "Trio"][0]
    assert len(trio["members"]) == 3
    Path(f.name).unlink(missing_ok=True)
