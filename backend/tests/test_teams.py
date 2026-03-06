"""Tests for team registration and listing."""

from __future__ import annotations

from fastapi.testclient import TestClient

from beerpong_api.main import app

client = TestClient(app)


def test_create_team() -> None:
    resp = client.post("/teams", json={"name": "Alpha", "members": ["Alice", "Bob"]})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Alpha"
    assert data["members"] == ["Alice", "Bob"]
    assert "id" in data


def test_list_teams_empty() -> None:
    resp = client.get("/teams")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_teams_after_create() -> None:
    client.post("/teams", json={"name": "Bravo", "members": ["Carol", "Dave"]})
    resp = client.get("/teams")
    assert resp.status_code == 200
    teams = resp.json()
    assert len(teams) == 1
    assert teams[0]["name"] == "Bravo"


def test_get_team_names() -> None:
    client.post("/teams", json={"name": "Zulu", "members": ["Z1"]})
    client.post("/teams", json={"name": "Alpha", "members": ["A1"]})
    resp = client.get("/teams/names")
    assert resp.status_code == 200
    names = resp.json()
    # Should be sorted alphabetically
    assert names == ["Alpha", "Zulu"]


def test_duplicate_team_rejected() -> None:
    client.post("/teams", json={"name": "Echo", "members": ["E1", "E2"]})
    resp = client.post("/teams", json={"name": "echo", "members": ["E3"]})
    assert resp.status_code == 409


def test_match_requires_registered_team() -> None:
    # Register one team
    client.post("/teams", json={"name": "Registered", "members": ["R1"]})
    # Try to create match with unregistered team
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
    client.post("/teams", json={"name": "Foxes", "members": ["F1", "F2"]})
    client.post("/teams", json={"name": "Wolves", "members": ["W1", "W2"]})
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

# ── CSV upload tests ──────────────────────────────────────────────────


def test_upload_csv_creates_teams() -> None:
    csv_content = "team_name,member1,member2\nAlpha,Alice,Bob\nBravo,Carol,Dave\n"
    resp = client.post(
        "/teams/upload-csv",
        files={"file": ("teams.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_count"] == 2
    assert data["skipped_count"] == 0
    assert "Alpha" in data["created"]
    assert "Bravo" in data["created"]

    # Verify teams exist
    teams_resp = client.get("/teams/names")
    names = teams_resp.json()
    assert "Alpha" in names
    assert "Bravo" in names


def test_upload_csv_skips_duplicates() -> None:
    # Pre-register one team
    client.post("/teams", json={"name": "Alpha", "members": ["Alice", "Bob"]})

    csv_content = "team_name,member1,member2\nAlpha,Alice,Bob\nBravo,Carol,Dave\n"
    resp = client.post(
        "/teams/upload-csv",
        files={"file": ("teams.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_count"] == 1
    assert data["skipped_count"] == 1
    assert "Bravo" in data["created"]
    assert "Alpha" in data["skipped"]


def test_upload_csv_no_header() -> None:
    csv_content = "Echo,Eve,Frank\nFoxes,Grace,Hank\n"
    resp = client.post(
        "/teams/upload-csv",
        files={"file": ("teams.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_count"] == 2


def test_upload_csv_empty_file() -> None:
    resp = client.post(
        "/teams/upload-csv",
        files={"file": ("empty.csv", "", "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_count"] == 0
    assert data["skipped_count"] == 0


def test_upload_csv_skips_rows_with_only_name() -> None:
    csv_content = "team_name,member1\nOnlyName\nValid,Player1\n"
    resp = client.post(
        "/teams/upload-csv",
        files={"file": ("teams.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_count"] == 1
    assert "Valid" in data["created"]