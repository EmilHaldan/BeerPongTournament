"""Tests for the /heat endpoints."""

from fastapi.testclient import TestClient

from beerpong_api.main import app
from beerpong_api.settings import get_settings

client = TestClient(app)
ADMIN_TOKEN = get_settings().ADMIN_TOKEN


def _register_team(name: str, members: list[str]) -> None:
    """Helper to register a team via the DAL.

    Phase 3 replaced the legacy ``members: list[str]`` field on ``TeamCreate``
    with ``member_ids: list[str]`` pointing at persisted players. Create each
    player first, then build the team with their IDs so the dual-write invariant
    holds (Team.member_ids <-> Player.team_id).
    """
    from beerpong_api.dal.players import create_player
    from beerpong_api.dal.teams import create_team
    from beerpong_api.db.models import PlayerCreate, TeamCreate

    player_ids = [create_player(PlayerCreate(name=m)).id for m in members]
    create_team(TeamCreate(name=name, member_ids=player_ids))


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
    # Advance the server heat so the duplicate-match guard doesn't reject the
    # second submission of the same pair.
    client.post(
        "/heat/set",
        json={"heat": 2},
        headers={"X-Admin-Token": ADMIN_TOKEN},
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


def test_post_tables_rejects_when_sit_out_longer_than_one_heat() -> None:
    """POST /heat/tables rejects counts where a team would sit two heats in a row.

    Rule: tables * 4 >= teams_count. Each heat seats 2*tables teams; sitters
    total (teams - 2*tables). For every sitter to get into the next heat, we
    need sitters <= 2*tables, i.e. teams <= 4*tables.
    """
    # Arrange – 9 teams
    for i in range(1, 10):
        _register_team(f"Team{i:02d}", [f"P{i}A", f"P{i}B"])

    # 2 tables is invalid (2*4=8 < 9) — user's example of a broken config.
    resp_two = client.post(
        "/heat/tables",
        json={"count": 2},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp_two.status_code == 400

    # 3 tables is the threshold (3*4=12 >= 9).
    resp_three = client.post(
        "/heat/tables",
        json={"count": 3},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp_three.status_code == 200
    assert resp_three.json()["tables"] == 3


def test_post_tables_accepts_four_to_one_ratio() -> None:
    """6 teams + 2 tables is allowed: 2*4=8 >= 6 — user's explicit OK example."""
    for i in range(1, 7):
        _register_team(f"Team{i:02d}", [f"P{i}A", f"P{i}B"])

    resp = client.post(
        "/heat/tables",
        json={"count": 2},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["tables"] == 2


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


# ── Phase 4: knockout tournament ─────────────────────────────────────


def _post_regular_match(t1: str, t2: str, s1: int, s2: int) -> None:
    """Shortcut for recording a regular-phase match via the API."""
    resp = client.post(
        "/matches",
        json={"team1_name": t1, "team2_name": t2, "team1_score": s1, "team2_score": s2},
    )
    assert resp.status_code == 201


def _register_team_with_members(name: str, player_names: list[str]) -> None:
    """Register a team along with real Player records, so Team.member_ids is populated.

    The bracket-eligibility check counts teams with at least one member,
    so the legacy ``_register_team`` helper (which silently drops the
    ``members=`` kwarg) cannot be used for knockout tests.
    """
    from beerpong_api.dal.players import create_player
    from beerpong_api.dal.teams import create_team
    from beerpong_api.db.models import PlayerCreate, TeamCreate

    player_ids = [create_player(PlayerCreate(name=n)).id for n in player_names]
    create_team(TeamCreate(name=name, member_ids=player_ids))


def _seed_four_teams_with_distinct_scores() -> list[str]:
    """Register four teams + stage regular matches so their scores differ.

    Returns the expected seeding order (highest score first, alphabetical
    tiebreaker). Totals after the three matches:

    * Alpha:  2W, score 14 (cups 6+6 + 1+1 bonus)
    * Beta:   0W, score  1 (cups 0+2 - 1 penalty)
    * Gamma:  1W, score  7 (cups 3+3 + 1 - 0)
    * Delta:  0W, score  3 (cups 2+2 - 1)
    """
    _register_team_with_members("Alpha", ["A1", "A2"])
    _register_team_with_members("Beta", ["B1", "B2"])
    _register_team_with_members("Gamma", ["G1", "G2"])
    _register_team_with_members("Delta", ["D1", "D2"])

    _post_regular_match("Alpha", "Beta", 6, 0)
    _post_regular_match("Alpha", "Delta", 6, 2)
    _post_regular_match("Gamma", "Beta", 3, 2)
    _post_regular_match("Gamma", "Delta", 3, 2)

    # Expected order: Alpha, Gamma, Delta, Beta
    return ["Alpha", "Gamma", "Delta", "Beta"]


def test_start_knockout_top_four_seeded_correctly() -> None:
    """Seeds resolve via total_score desc → wins desc → name asc."""
    # Arrange
    expected = _seed_four_teams_with_distinct_scores()

    # Act
    resp = client.post(
        "/admin/start-knockout",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert data["phase"] == "semifinals"
    assert data["knockout_seeds"] == expected


def test_start_knockout_rejects_fewer_than_four_teams() -> None:
    """Three eligible teams → 400 with clear message."""
    # Arrange
    _register_team_with_members("Alpha", ["A1", "A2"])
    _register_team_with_members("Beta", ["B1", "B2"])
    _register_team_with_members("Gamma", ["G1", "G2"])

    # Act
    resp = client.post(
        "/admin/start-knockout",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )

    # Assert
    assert resp.status_code == 400
    assert "at least 4" in resp.json()["detail"]


def test_start_knockout_pairs_one_vs_four_and_two_vs_three() -> None:
    """SF matchups are seed[0]↔seed[3] and seed[1]↔seed[2]."""
    # Arrange
    expected = _seed_four_teams_with_distinct_scores()

    # Act
    resp = client.post(
        "/admin/start-knockout",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )

    # Assert
    data = resp.json()
    matchups = data["matchups"]
    assert len(matchups) == 2
    pair_a = {matchups[0]["team1_name"], matchups[0]["team2_name"]}
    pair_b = {matchups[1]["team1_name"], matchups[1]["team2_name"]}
    assert pair_a == {expected[0], expected[3]}
    assert pair_b == {expected[1], expected[2]}


def test_knockout_match_scores_excluded_from_leaderboard() -> None:
    """Matches stamped with phase != regular must not count in the leaderboard."""
    # Arrange
    _seed_four_teams_with_distinct_scores()
    resp = client.post(
        "/admin/start-knockout",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    matchups = resp.json()["matchups"]
    lb_before = client.get("/leaderboard").json()

    # Record both SF matches
    for m in matchups:
        _post_regular_match(m["team1_name"], m["team2_name"], 6, 2)

    # Act
    lb_after = client.get("/leaderboard").json()

    # Assert — leaderboard is identical (knockout phase is filtered out).
    assert lb_before == lb_after


def test_advance_heat_semifinals_requires_both_matches_recorded() -> None:
    """advance_heat in SF with only one match recorded raises."""
    # Arrange
    _seed_four_teams_with_distinct_scores()
    resp = client.post(
        "/admin/start-knockout",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    matchups = resp.json()["matchups"]
    _post_regular_match(matchups[0]["team1_name"], matchups[0]["team2_name"], 6, 2)

    # Act
    resp = client.post(
        "/heat/start-next",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )

    # Assert
    assert resp.status_code == 400
    assert "Semi-final" in resp.json()["detail"]


def test_advance_heat_semifinals_to_finals_uses_correct_winners() -> None:
    """Winners of each SF are paired into the single Finals matchup."""
    # Arrange
    _seed_four_teams_with_distinct_scores()
    resp = client.post(
        "/admin/start-knockout",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    matchups = resp.json()["matchups"]
    expected_winners: set[str] = set()
    for m in matchups:
        # team1 wins each SF
        _post_regular_match(m["team1_name"], m["team2_name"], 6, 2)
        expected_winners.add(m["team1_name"])

    # Act
    resp = client.post(
        "/heat/start-next",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert data["phase"] == "finals"
    assert len(data["matchups"]) == 1
    finalists = {data["matchups"][0]["team1_name"], data["matchups"][0]["team2_name"]}
    assert finalists == expected_winners


def test_finals_submission_auto_freezes_tournament() -> None:
    """Recording the Finals score auto-sets frozen=True."""
    # Arrange — walk through SF → F
    _seed_four_teams_with_distinct_scores()
    resp = client.post("/admin/start-knockout", headers={"X-Admin-Token": ADMIN_TOKEN})
    for m in resp.json()["matchups"]:
        _post_regular_match(m["team1_name"], m["team2_name"], 6, 2)
    resp = client.post("/heat/start-next", headers={"X-Admin-Token": ADMIN_TOKEN})
    final = resp.json()["matchups"][0]
    assert client.get("/heat").json()["frozen"] is False

    # Act
    _post_regular_match(final["team1_name"], final["team2_name"], 6, 3)

    # Assert
    data = client.get("/heat").json()
    assert data["frozen"] is True


def test_finals_submission_sets_phase_complete() -> None:
    """After Finals is recorded, the state phase moves to 'complete'."""
    # Arrange
    _seed_four_teams_with_distinct_scores()
    resp = client.post("/admin/start-knockout", headers={"X-Admin-Token": ADMIN_TOKEN})
    for m in resp.json()["matchups"]:
        _post_regular_match(m["team1_name"], m["team2_name"], 6, 2)
    resp = client.post("/heat/start-next", headers={"X-Admin-Token": ADMIN_TOKEN})
    final = resp.json()["matchups"][0]

    # Act
    _post_regular_match(final["team1_name"], final["team2_name"], 6, 4)

    # Assert
    assert client.get("/heat").json()["phase"] == "complete"


def test_knockout_tie_rejected_with_exact_error_message() -> None:
    """Tied SF score → 400 with the verbatim operator-facing message."""
    # Arrange
    _seed_four_teams_with_distinct_scores()
    resp = client.post("/admin/start-knockout", headers={"X-Admin-Token": ADMIN_TOKEN})
    m = resp.json()["matchups"][0]

    # Act
    resp = client.post(
        "/matches",
        json={
            "team1_name": m["team1_name"],
            "team2_name": m["team2_name"],
            "team1_score": 4,
            "team2_score": 4,
        },
    )

    # Assert
    assert resp.status_code == 400
    assert (
        resp.json()["detail"]
        == "Knockout matches cannot end in a tie — play sudden death until someone scores."
    )


def test_admin_reset_tournament_resets_phase_and_unfreezes() -> None:
    """reset-tournament clears phase, seeds, frozen, heat, and wipes matches."""
    # Arrange — drive the bracket to completion so every knockout field is set.
    _seed_four_teams_with_distinct_scores()
    resp = client.post("/admin/start-knockout", headers={"X-Admin-Token": ADMIN_TOKEN})
    for m in resp.json()["matchups"]:
        _post_regular_match(m["team1_name"], m["team2_name"], 6, 2)
    resp = client.post("/heat/start-next", headers={"X-Admin-Token": ADMIN_TOKEN})
    final = resp.json()["matchups"][0]
    _post_regular_match(final["team1_name"], final["team2_name"], 6, 4)
    pre = client.get("/heat").json()
    assert pre["frozen"] is True
    assert pre["phase"] == "complete"

    # Act
    resp = client.post(
        "/admin/reset-tournament",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )

    # Assert
    assert resp.status_code == 200
    post = client.get("/heat").json()
    assert post["phase"] == "regular"
    assert post["knockout_seeds"] == []
    assert post["frozen"] is False
    assert post["current_heat"] == 1
    assert client.get("/matches").json() == []


def test_heat_info_exposes_teams_sitting_out() -> None:
    """GET /heat always exposes teams_sitting_out, empty by default."""
    # Arrange / Act
    resp = client.get("/heat")

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert "teams_sitting_out" in data
    assert data["teams_sitting_out"] == []
