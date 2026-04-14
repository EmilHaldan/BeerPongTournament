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


def test_round_robin_covers_all_pairs() -> None:
    """In cycle 1, round-robin should ensure every pair plays exactly once."""
    _register_team("Alpha", ["Alice", "Bob"])
    _register_team("Beta", ["Carol", "Dave"])
    _register_team("Gamma", ["Eve", "Frank"])
    _register_team("Delta", ["Grace", "Heidi"])

    all_pairs_played: set[tuple[str, str]] = set()

    # Play through 3 heats (N-1 = 3 for 4 teams)
    for heat_num in range(3):
        resp = client.get("/heat")
        data = resp.json()
        matchups = data["matchups"]
        assert len(matchups) == 2, f"Heat {heat_num + 1}: expected 2 matchups"

        # Record every matchup
        for m in matchups:
            t1, t2 = m["team1_name"], m["team2_name"]
            pair = tuple(sorted([t1, t2]))
            assert pair not in all_pairs_played, f"Pair {pair} already played"
            all_pairs_played.add(pair)  # pyright: ignore[reportArgumentType]

            client.post(
                "/matches",
                json={"team1_name": t1, "team2_name": t2, "team1_score": 3, "team2_score": 2},
            )

        # Advance to next heat
        if heat_num < 2:
            client.post("/heat/start-next", headers={"X-Admin-Token": ADMIN_TOKEN})

    # All 6 possible pairs should have been played
    assert len(all_pairs_played) == 6


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


def test_set_tables() -> None:
    """POST /heat/tables with a valid count should update tables and return HeatInfo."""
    # Arrange / Act
    resp = client.post(
        "/heat/tables",
        json={"count": 12},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert data["tables"] == 12

    # And persisted on GET /heat
    get_resp = client.get("/heat")
    assert get_resp.status_code == 200
    assert get_resp.json()["tables"] == 12


def test_set_tables_rejects_bad_token() -> None:
    """POST /heat/tables with a non-admin token should return 403."""
    resp = client.post(
        "/heat/tables",
        json={"count": 4},
        headers={"X-Admin-Token": "wrong"},
    )
    assert resp.status_code == 403


def test_set_tables_rejects_zero_or_negative() -> None:
    """POST /heat/tables with count=0 or negative should return 400."""
    zero_resp = client.post(
        "/heat/tables",
        json={"count": 0},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert zero_resp.status_code == 400

    neg_resp = client.post(
        "/heat/tables",
        json={"count": -1},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert neg_resp.status_code == 400


def test_get_heat_exposes_tables() -> None:
    """GET /heat should expose the tables field with default 8."""
    resp = client.get("/heat")
    assert resp.status_code == 200
    data = resp.json()
    assert "tables" in data
    assert data["tables"] == 8


def test_heat_shows_recorded_status() -> None:
    """Heat info should indicate which matchups have recorded scores."""
    _register_team("Alpha", ["Alice", "Bob"])
    _register_team("Beta", ["Carol", "Dave"])
    _register_team("Gamma", ["Eve", "Frank"])
    _register_team("Delta", ["Grace", "Heidi"])

    # No matches yet — all matchups should be unrecorded
    resp = client.get("/heat")
    data = resp.json()
    assert len(data["matchups"]) == 2
    for m in data["matchups"]:
        assert m["recorded"] is False
        assert m["winner"] is None
        assert m["team1_score"] is None
        assert m["team2_score"] is None
    assert data["teams_not_recorded"] != []
    assert data["teams_recorded"] == []

    # Record one of the generated matchups (whichever the round-robin produced)
    first_matchup = data["matchups"][0]
    t1, t2 = first_matchup["team1_name"], first_matchup["team2_name"]
    client.post(
        "/matches",
        json={"team1_name": t1, "team2_name": t2, "team1_score": 5, "team2_score": 2},
    )

    resp = client.get("/heat")
    data = resp.json()
    recorded_matchup = next(
        m for m in data["matchups"] if {m["team1_name"], m["team2_name"]} == {t1, t2}
    )
    assert recorded_matchup["recorded"] is True
    assert recorded_matchup["winner"] == t1  # t1 scored 5 > 2
    assert recorded_matchup["team1_score"] is not None
    assert recorded_matchup["team2_score"] is not None

    pending_matchup = next(
        m for m in data["matchups"] if {m["team1_name"], m["team2_name"]} != {t1, t2}
    )
    assert pending_matchup["recorded"] is False
    assert pending_matchup["winner"] is None

    assert t1 in data["teams_recorded"]
    assert t2 in data["teams_recorded"]
    assert len(data["teams_not_recorded"]) == 2


# ── Phase 2: tables-aware matchmaking ────────────────────────────────


def test_scheduler_tables_constrained_sits_lowest_score() -> None:
    """With 11 teams and tables=4, 3 teams with most matches+score should sit.

    The priority rule is "lowest (total_matches, total_score) plays first";
    the top of that ascending sort plays and the tail sits out. To get a
    deterministic sit-out list with recorded matches we first give ALL
    teams a match each so total_matches is constant, then layer extra
    matches onto three specific teams so they have the highest total_score
    and get pushed to the sit-out tail.
    """
    # Arrange – 11 teams registered; we sidestep the route-level validator
    # that refuses tables=4 for 11 teams by calling the DAL directly.
    from beerpong_api.dal.heat import set_tables as dal_set_tables

    team_names = [f"Team{i:02d}" for i in range(1, 12)]
    for name in team_names:
        _register_team(name, [f"{name}A", f"{name}B"])

    # Give every team exactly one match so total_matches is equal (1) and
    # the tiebreaker is purely total_score.
    base_pairs = [
        ("Team01", "Team02"),
        ("Team03", "Team04"),
        ("Team05", "Team06"),
        ("Team07", "Team08"),
        ("Team09", "Team10"),
    ]
    for t1, t2 in base_pairs:
        client.post(
            "/matches",
            json={"team1_name": t1, "team2_name": t2, "team1_score": 3, "team2_score": 3},
        )
    # Team11 has no match yet → total_matches = 0 → highest priority to play.
    # We need Team11 IN the playing set too, but then the sitting-out tail
    # has teams with (1, score). So the three teams with the HIGHEST score
    # should end up sitting. We load Team08, Team09, Team10 up with more
    # matches so they rise to the top of the sort (highest matches/score)
    # and fall off the playing list.
    #
    # After base_pairs: every Team01..10 has total_matches=1, score depends
    # on tie = no bonus so score equals cups = 3. Team11 has 0 matches 0 score.
    #
    # Now bump Team09 and Team10 with another tied match vs each other, and
    # Team08 vs Team09 (still ties so no win bonuses). That makes:
    #   Team08: matches=2, score=6
    #   Team09: matches=3, score=9
    #   Team10: matches=2, score=6
    # Others: matches=1, score=3
    # Team11: matches=0, score=0
    client.post(
        "/matches",
        json={"team1_name": "Team09", "team2_name": "Team10", "team1_score": 3, "team2_score": 3},
    )
    client.post(
        "/matches",
        json={"team1_name": "Team08", "team2_name": "Team09", "team1_score": 3, "team2_score": 3},
    )

    # Force tables=4 past the validator, then advance so the scheduler
    # recomputes using the constrained tables count.
    dal_set_tables(4)
    client.post("/heat/start-next", headers={"X-Admin-Token": ADMIN_TOKEN})

    # Act
    resp = client.get("/heat")

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matchups"]) == 4  # 4 tables → 4 games
    playing_teams: set[str] = set()
    for m in data["matchups"]:
        playing_teams.add(m["team1_name"])
        playing_teams.add(m["team2_name"])
    assert len(playing_teams) == 8
    sitting = data["teams_sitting_out"]
    assert len(sitting) == 3
    # Team08 (2,6), Team09 (3,9), Team10 (2,6) have the highest
    # (total_matches, total_score) and therefore sit out. Team11 has
    # zero matches so it definitely plays.
    assert set(sitting) == {"Team08", "Team09", "Team10"}
    assert "Team11" in playing_teams


def test_scheduler_last_heat_forces_balance() -> None:
    """With last_heat=true, the low-matches team must be in the next heat's games."""
    # Arrange – 4 teams, plenty of tables (unconstrained).
    _register_team("Alpha", ["Alice", "Bob"])
    _register_team("Beta", ["Carol", "Dave"])
    _register_team("Gamma", ["Eve", "Frank"])
    _register_team("Delta", ["Grace", "Heidi"])

    # Record several matches for everyone EXCEPT Delta so Delta has the
    # fewest total_matches.
    client.post(
        "/matches",
        json={"team1_name": "Alpha", "team2_name": "Beta", "team1_score": 4, "team2_score": 2},
    )
    client.post(
        "/matches",
        json={"team1_name": "Alpha", "team2_name": "Gamma", "team1_score": 3, "team2_score": 3},
    )
    client.post(
        "/matches",
        json={"team1_name": "Beta", "team2_name": "Gamma", "team1_score": 5, "team2_score": 1},
    )

    # Act – advance to next heat with last_heat flag on
    resp = client.post(
        "/heat/start-next",
        json={"last_heat": True},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )

    # Assert – Delta (the low-matches team) must appear in a matchup
    assert resp.status_code == 200
    data = resp.json()
    playing: set[str] = set()
    for m in data["matchups"]:
        playing.add(m["team1_name"])
        playing.add(m["team2_name"])
    assert "Delta" in playing


def test_scheduler_unconstrained_without_last_heat_keeps_round_robin() -> None:
    """Default unconstrained call should still return a round-robin slate."""
    # Arrange
    _register_team("Alpha", ["Alice", "Bob"])
    _register_team("Beta", ["Carol", "Dave"])
    _register_team("Gamma", ["Eve", "Frank"])
    _register_team("Delta", ["Grace", "Heidi"])

    # Act
    resp = client.get("/heat")

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matchups"]) == 2
    assert data["teams_sitting_out"] == []


def test_post_tables_rejects_less_than_half_teams() -> None:
    """POST /heat/tables must reject counts that can't fit half the teams."""
    # Arrange – register 11 teams
    for i in range(1, 12):
        _register_team(f"Team{i:02d}", [f"P{i}A", f"P{i}B"])

    # Act / Assert – 4 tables cannot cover 11 teams (need at least 6)
    resp_four = client.post(
        "/heat/tables",
        json={"count": 4},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp_four.status_code == 400

    # 5 tables is still too few (10 < 11)
    resp_five = client.post(
        "/heat/tables",
        json={"count": 5},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp_five.status_code == 400

    # 6 tables is enough (12 >= 11)
    resp_six = client.post(
        "/heat/tables",
        json={"count": 6},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp_six.status_code == 200
    assert resp_six.json()["tables"] == 6


def test_start_next_heat_accepts_last_heat_flag() -> None:
    """POST /heat/start-next with {"last_heat": true} must return 200."""
    # Arrange
    _register_team("Alpha", ["Alice", "Bob"])
    _register_team("Beta", ["Carol", "Dave"])
    _register_team("Gamma", ["Eve", "Frank"])
    _register_team("Delta", ["Grace", "Heidi"])

    # Act
    resp = client.post(
        "/heat/start-next",
        json={"last_heat": True},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_heat"] == 2
    assert "teams_sitting_out" in data


def test_heat_info_exposes_teams_sitting_out() -> None:
    """GET /heat always exposes teams_sitting_out, empty by default."""
    # Arrange / Act
    resp = client.get("/heat")

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert "teams_sitting_out" in data
    assert data["teams_sitting_out"] == []
