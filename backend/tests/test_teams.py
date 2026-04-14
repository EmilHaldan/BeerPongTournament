"""Tests for team management, the dual-write invariant, and the CSV upload endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from beerpong_api.dal.players import create_player
from beerpong_api.dal.teams import create_team
from beerpong_api.db.models import PlayerCreate, TeamCreate
from beerpong_api.main import app

client = TestClient(app)

ADMIN = {"X-Admin-Token": "changeme"}


# ── Helpers ──────────────────────────────────────────────────────────


def _make_players(*names: str) -> list[str]:
    """Create players via the DAL and return their ids in order."""
    ids: list[str] = []
    for name in names:
        player = create_player(PlayerCreate(name=name))
        ids.append(player.id)
    return ids


def _register_team(name: str, member_names: list[str]) -> str:
    """Create the supplied players, then create the team. Returns the team id."""
    ids = _make_players(*member_names)
    team = create_team(TeamCreate(name=name, member_ids=ids))
    return team.id


# ── Team model validation ────────────────────────────────────────────


def test_team_create_rejects_four_members() -> None:
    """TeamCreate model allows at most 3 members."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TeamCreate(name="Big", member_ids=["a", "b", "c", "d"])


def test_team_create_allows_two_members() -> None:
    """Creating a team with exactly two member_ids succeeds."""
    _register_team("Duo", ["Alice", "Bob"])

    names = client.get("/teams/names").json()
    assert "Duo" in names


def test_team_create_allows_three_members() -> None:
    """Creating a team with three member_ids is permitted and fully persisted."""
    _register_team("Trio", ["Alice", "Bob", "Carol"])

    teams = client.get("/teams").json()
    trio = [t for t in teams if t["name"] == "Trio"][0]
    assert len(trio["member_ids"]) == 3


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


# ── POST /teams: dual-write invariant ────────────────────────────────


def test_create_team_with_member_ids_dual_writes() -> None:
    """Creating a team via POST /teams must set team_id on each referenced player."""
    pid1, pid2 = _make_players("Alice", "Bob")

    resp = client.post(
        "/teams",
        json={"name": "Duo", "member_ids": [pid1, pid2]},
        headers=ADMIN,
    )
    assert resp.status_code == 201
    team_id = resp.json()["id"]

    players = {p["id"]: p for p in client.get("/players").json()}
    assert players[pid1]["team_id"] == team_id
    assert players[pid2]["team_id"] == team_id


def test_create_team_with_empty_member_ids() -> None:
    """Admin can create a team with zero members; existing players are untouched."""
    pid = _make_players("Chuck")[0]

    resp = client.post(
        "/teams",
        json={"name": "Empty", "member_ids": []},
        headers=ADMIN,
    )
    assert resp.status_code == 201
    assert resp.json()["member_ids"] == []

    players = {p["id"]: p for p in client.get("/players").json()}
    assert players[pid]["team_id"] is None


def test_create_team_rejects_unknown_member_ids() -> None:
    """Any unknown member_id → 400 and no team is created."""
    resp = client.post(
        "/teams",
        json={"name": "Ghosts", "member_ids": ["not-a-real-id"]},
        headers=ADMIN,
    )
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()

    teams = client.get("/teams").json()
    assert teams == []


def test_create_team_rejects_bad_token() -> None:
    resp = client.post(
        "/teams",
        json={"name": "NoEntry", "member_ids": []},
        headers={"X-Admin-Token": "wrong"},
    )
    assert resp.status_code == 403


# ── DELETE /teams: detach semantics ──────────────────────────────────


def test_delete_team_detaches_players() -> None:
    """Deleting a team detaches its members: players survive with team_id=None."""
    team_id = _register_team("Removable", ["Alice", "Bob"])

    before = client.get("/players").json()
    assert all(p["team_id"] == team_id for p in before)
    member_ids = [p["id"] for p in before]

    resp = client.delete(f"/teams/{team_id}", headers=ADMIN)
    assert resp.status_code == 200

    after = {p["id"]: p for p in client.get("/players").json()}
    assert len(after) == 2
    for pid in member_ids:
        assert after[pid]["team_id"] is None


# ── CSV upload endpoint ──────────────────────────────────────────────


def _upload(content: str, dry_run: bool = False) -> object:
    """POST the given string body to /admin/teams/upload-csv."""
    files = {"file": ("roster.csv", content.encode("utf-8"), "text/csv")}
    params = {"dry_run": str(dry_run).lower()}
    return client.post(
        "/admin/teams/upload-csv",
        files=files,
        params=params,
        headers=ADMIN,
    )


def test_upload_csv_happy_path() -> None:
    """Valid CSV creates teams + players with team_id linked and wipes prior state."""
    # Seed existing roster + a match + heat state so we can assert they were wiped.
    _register_team("Stale", ["Gone1", "Gone2"])
    client.post(
        "/matches",
        json={
            "team1_name": "Stale",
            "team2_name": "Stale",
            "team1_score": 1,
            "team2_score": 2,
        },
    )
    client.post("/heat/set", json={"heat": 7}, headers=ADMIN)

    csv_content = (
        "team_name,member1,member2,member3\n"
        "Alpha,Alice,Bob,Carol\n"
        "Bravo,Dave,Eve\n"
    )
    resp = _upload(csv_content)

    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is False
    assert sorted(body["created_teams"]) == ["Alpha", "Bravo"]
    assert sorted(body["created_players"]) == ["Alice", "Bob", "Carol", "Dave", "Eve"]
    assert body["replaced_count"] == 1
    assert body["errors"] == []

    # Linked
    teams = client.get("/teams").json()
    alpha = [t for t in teams if t["name"] == "Alpha"][0]
    assert len(alpha["member_ids"]) == 3

    players = {p["name"]: p for p in client.get("/players").json()}
    assert players["Alice"]["team_id"] == alpha["id"]

    # Matches wiped
    assert client.get("/matches").json() == []

    # Heat state wiped
    assert client.get("/heat").json()["current_heat"] == 1


def test_upload_csv_dry_run() -> None:
    """Dry-run returns the same shape but does not mutate the DB."""
    _register_team("Original", ["Oa", "Ob"])
    pre_teams = client.get("/teams").json()
    pre_players = client.get("/players").json()

    csv_content = "team_name,member1,member2\nNew,X,Y\n"
    resp = _upload(csv_content, dry_run=True)

    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["created_teams"] == ["New"]
    assert body["created_players"] == ["X", "Y"]
    assert body["replaced_count"] == 1

    # State untouched
    assert client.get("/teams").json() == pre_teams
    assert client.get("/players").json() == pre_players


def test_upload_csv_malformed_rows_rejected() -> None:
    """Rows with bad column counts → 400, DB untouched."""
    _register_team("Safe", ["Sa", "Sb"])

    # Row 2 has only one column (name only).
    csv_content = "team_name,member1,member2\nGood,Alice,Bob\nSoloTeam\n"
    resp = _upload(csv_content)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["message"] == "Can't ingest malformed CSV file"
    assert any(err["row"] == 2 for err in detail["errors"])

    # State untouched
    teams = client.get("/teams").json()
    assert len(teams) == 1
    assert teams[0]["name"] == "Safe"


def test_upload_csv_duplicate_team_name_rejected() -> None:
    """Two rows with the same normalised team name → 400."""
    csv_content = (
        "team_name,member1,member2\n"
        "Alpha,Alice,Bob\n"
        "ALPHA,Carol,Dave\n"
    )
    resp = _upload(csv_content)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert any("duplicate" in err["reason"].lower() for err in detail["errors"])


def test_upload_csv_empty_team_name_rejected() -> None:
    """Row with an empty first cell → 400."""
    # Note: csv.reader treats ,Alice,Bob as [empty, Alice, Bob] – 3 cells total,
    # but the first (team name) cell is empty, which the validator rejects.
    csv_content = "team_name,member1,member2\n,Alice,Bob\n"
    resp = _upload(csv_content)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert any("team name is empty" in err["reason"].lower() for err in detail["errors"])


def test_upload_csv_oversize_rejected() -> None:
    """Uploads over the 256 KiB cap → 413 Payload Too Large."""
    # 260 KiB payload guarantees we're over 256 KiB.
    oversized = "team_name,member1,member2\n" + ("A" * 1024 + "\n") * 260
    resp = _upload(oversized)

    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_upload_csv_requires_admin_token() -> None:
    """No admin token → 403."""
    files = {"file": ("roster.csv", b"team_name,m1,m2\nAlpha,A,B\n", "text/csv")}
    resp = client.post("/admin/teams/upload-csv", files=files, headers={"X-Admin-Token": "wrong"})
    assert resp.status_code == 403


def test_upload_csv_empty_body_rejected() -> None:
    """An empty file still reaches the parser; rejected with a row-0 error."""
    resp = _upload("")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert any(err["row"] == 0 for err in detail["errors"])
