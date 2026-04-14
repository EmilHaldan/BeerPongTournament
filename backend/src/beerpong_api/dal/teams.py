"""DAL functions for team management.

Phase 3 invariants enforced here:

* **Dual-write**: Team.member_ids is canonical; Player.team_id is a maintained
  back-reference. Every mutation that changes membership updates both sides
  inside the same logical DAL operation.
* **Detach-before-delete**: deleting a team clears its members' team_ids first
  so no Player is left pointing at a non-existent team.
* **CSV replacement is destructive**: the upload path wipes teams, players,
  matches, and heat/tournament state in one go before rebuilding the roster.
"""

from __future__ import annotations

import csv
import io

from beerpong_api.dal._normalize import normalize_name
from beerpong_api.db.client import (
    get_container,
    get_players_container,
    get_state_container,
    get_teams_container,
)
from beerpong_api.db.models import (
    ImportError,
    ImportSummary,
    Player,
    Team,
    TeamCreate,
)

_DEFAULT_PARTITION = "default"


def _get_player_by_id_raw(player_id: str) -> dict[str, object] | None:
    """Fetch a single player document by id from the players container.

    Kept private so `dal/teams.py` can enforce the dual-write invariant without
    creating an import cycle with `dal/players.py`. Callers outside this module
    should use `dal.players.get_player_by_id`.
    """
    container = get_players_container()
    query = "SELECT * FROM c WHERE c.id = @id AND c.tournamentId = @tid"
    params: list[dict[str, object]] = [
        {"name": "@id", "value": player_id},
        {"name": "@tid", "value": _DEFAULT_PARTITION},
    ]
    raw = container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False,
    )
    items = list(raw)  # pyright: ignore[reportArgumentType]
    if not items:
        return None
    return dict(items[0])  # pyright: ignore[reportArgumentType]


def _set_player_team_id(player_id: str, team_id: str | None) -> Player:
    """Low-level helper: update a player's team_id back-reference and upsert.

    Raises ValueError when the player does not exist.
    """
    raw = _get_player_by_id_raw(player_id)
    if raw is None:
        raise ValueError(f"Player '{player_id}' not found")
    raw["team_id"] = team_id
    player = Player(**raw)  # pyright: ignore[reportArgumentType]
    doc = player.model_dump(by_alias=True)
    get_players_container().upsert_item(doc)
    return player


def create_team(payload: TeamCreate) -> Team:
    """Create and persist a new team, dual-writing the back-reference.

    For each id in ``payload.member_ids`` the matching Player's ``team_id`` is
    set to the new Team's id. If any id does not resolve to an existing player,
    a ``ValueError`` is raised before the Team document is written so a Team
    with dangling references never exists on disk. The route layer converts
    that ValueError into a 400 response.
    """
    team = Team(
        name=normalize_name(payload.name),
        member_ids=list(payload.member_ids),
    )

    # Phase 1: verify every referenced player exists. Fail fast before any
    # mutation so a half-written state cannot happen.
    player_docs: list[dict[str, object]] = []
    for pid in team.member_ids:
        raw = _get_player_by_id_raw(pid)
        if raw is None:
            raise ValueError(f"Player '{pid}' not found")
        player_docs.append(raw)

    # Phase 2: update the players first (dual-write back-reference).
    players_container = get_players_container()
    for raw in player_docs:
        raw["team_id"] = team.id
        player = Player(**raw)  # pyright: ignore[reportArgumentType]
        players_container.upsert_item(player.model_dump(by_alias=True))

    # Phase 3: upsert the team. If this fails the players are already updated;
    # the next consistency check on reload will detect orphaned team_ids.
    teams_container = get_teams_container()
    teams_container.upsert_item(team.model_dump(by_alias=True))
    return team


def list_teams() -> list[Team]:
    """Return all registered teams in the default tournament partition."""
    container = get_teams_container()
    query = "SELECT * FROM c WHERE c.tournamentId = @tid"
    params: list[dict[str, object]] = [{"name": "@tid", "value": _DEFAULT_PARTITION}]
    items = container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False,
    )
    return [Team(**item) for item in items]  # type: ignore[reportUnknownArgumentType]


def _get_team_raw(team_id: str) -> dict[str, object] | None:
    """Fetch a single team document by id. None if not found."""
    container = get_teams_container()
    query = "SELECT * FROM c WHERE c.id = @id AND c.tournamentId = @tid"
    params: list[dict[str, object]] = [
        {"name": "@id", "value": team_id},
        {"name": "@tid", "value": _DEFAULT_PARTITION},
    ]
    raw = container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=False,
    )
    items = list(raw)  # pyright: ignore[reportArgumentType]
    if not items:
        return None
    return dict(items[0])  # pyright: ignore[reportArgumentType]


def get_team_by_id(team_id: str) -> Team | None:
    """Return a single Team or None if not found."""
    raw = _get_team_raw(team_id)
    return None if raw is None else Team(**raw)  # pyright: ignore[reportArgumentType]


def get_team_names() -> list[str]:
    """Return a sorted list of all team names."""
    teams = list_teams()
    return sorted(t.name for t in teams)


def delete_team(team_id: str) -> bool:
    """Delete a team by id, detaching its players first.

    Dual-write invariant: every member's ``Player.team_id`` is cleared before
    the Team document is removed, so no player is left with a dangling
    back-reference. Returns True when the team existed and was deleted, False
    when the team was not found (idempotent on re-delete).
    """
    raw = _get_team_raw(team_id)
    if raw is None:
        return False

    member_ids = list(raw.get("member_ids", []))  # pyright: ignore[reportArgumentType]
    # Detach each player first — compensating rollback is not needed because
    # a player ending up with team_id=None is a legal terminal state.
    for pid in member_ids:
        try:
            _set_player_team_id(pid, None)
        except ValueError:
            # Player already gone — ignore; the invariant is still repaired.
            continue

    try:
        get_teams_container().delete_item(item=team_id, partition_key=_DEFAULT_PARTITION)
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# CSV upload — full replacement
# ---------------------------------------------------------------------------


def _wipe_container(container_getter: object) -> int:
    """Delete every doc in the default partition of the given container.

    Returns the number of documents deleted.
    """
    container = container_getter()  # type: ignore[misc]
    query = "SELECT c.id FROM c WHERE c.tournamentId = @tid"
    params: list[dict[str, object]] = [{"name": "@tid", "value": _DEFAULT_PARTITION}]
    items = list(
        container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=False,
        )
    )
    for item in items:
        container.delete_item(item=item["id"], partition_key=_DEFAULT_PARTITION)
    return len(items)


def _parse_and_validate_csv(content: str) -> tuple[list[tuple[str, list[str]]], list[ImportError]]:
    """Parse CSV content and run strict validation.

    Returns a tuple of ``(valid_rows, errors)`` where ``valid_rows`` is a list
    of ``(team_name, member_names)`` tuples (empty if any error was found), and
    ``errors`` is the accumulated list of ImportError records keyed by 1-based
    row index (1 = the first data row; the optional header is row 0).

    Validation rules (all strict — any failure empties ``valid_rows``):

    * row empty or has fewer than 3 non-empty cells (team + 2 members): error
    * team name empty after stripping: error
    * duplicate team name (after normalisation): error
    * member count < 2 or > 3: error
    * duplicate member name within a single row: error

    An optional header row is detected and skipped if the first cell matches a
    known header keyword (``team_name``, ``team``, ``name``).
    """
    errors: list[ImportError] = []
    valid: list[tuple[str, list[str]]] = []

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    if not rows:
        errors.append(ImportError(row=0, reason="CSV is empty"))
        return ([], errors)

    # Detect optional header row
    start = 0
    first_cell = rows[0][0].strip().lower().replace("_", "").replace(" ", "") if rows[0] else ""
    if first_cell in {"teamname", "team", "name"}:
        start = 1

    seen_team_names: set[str] = set()

    for idx, row in enumerate(rows[start:], start=1):
        cells = [c.strip() for c in row]
        # Drop trailing empty cells (spreadsheets often produce these)
        while cells and cells[-1] == "":
            cells.pop()

        if not cells:
            errors.append(ImportError(row=idx, reason="row is empty"))
            continue

        if len(cells) < 3:
            errors.append(
                ImportError(
                    row=idx,
                    reason=(
                        f"row has {len(cells)} column(s); expected team name + 2-3 members"
                    ),
                )
            )
            continue

        team_name_raw = cells[0]
        members_raw = cells[1:]

        if not team_name_raw:
            errors.append(ImportError(row=idx, reason="team name is empty"))
            continue

        if len(members_raw) < 2:
            errors.append(
                ImportError(row=idx, reason=f"team has {len(members_raw)} member(s); minimum is 2")
            )
            continue
        if len(members_raw) > 3:
            errors.append(
                ImportError(row=idx, reason=f"team has {len(members_raw)} members; maximum is 3")
            )
            continue

        if any(not m for m in members_raw):
            errors.append(ImportError(row=idx, reason="one or more member names are empty"))
            continue

        normalized_team = normalize_name(team_name_raw)
        if normalized_team in seen_team_names:
            errors.append(
                ImportError(row=idx, reason=f"duplicate team name '{normalized_team}'")
            )
            continue

        normalized_members = [normalize_name(m) for m in members_raw]
        if len(set(normalized_members)) != len(normalized_members):
            errors.append(
                ImportError(row=idx, reason="duplicate member names within the same team")
            )
            continue

        seen_team_names.add(normalized_team)
        valid.append((normalized_team, normalized_members))

    if errors:
        return ([], errors)
    return (valid, [])


def replace_all_teams_and_players_from_csv(
    content: str, *, dry_run: bool
) -> ImportSummary:
    """Full-replacement CSV import.

    Strict validation first: any malformed row aborts the whole import and the
    returned summary carries the full error list with ``dry_run`` reflecting the
    caller's flag. No mutations happen in that case.

    When validation passes and ``dry_run`` is False, the operation is
    destructive: every team, player, match, and piece of heat/tournament state
    is deleted before the new roster is rebuilt. Player records are created
    fresh for every member name in the CSV, then each team is created with the
    resolved ``member_ids`` via the dual-write ``create_team`` path.

    When ``dry_run`` is True and validation passes, the same summary shape is
    returned but no database writes happen — useful for the upload preview UX.
    """
    valid_rows, errors = _parse_and_validate_csv(content)

    if errors:
        return ImportSummary(
            created_teams=[],
            created_players=[],
            skipped=[],
            replaced_count=0,
            errors=errors,
            dry_run=dry_run,
        )

    if dry_run:
        created_team_names: list[str] = [t for t, _ in valid_rows]
        created_player_names: list[str] = []
        for _, members in valid_rows:
            created_player_names.extend(members)
        replaced_count = len(list_teams())
        return ImportSummary(
            created_teams=created_team_names,
            created_players=created_player_names,
            skipped=[],
            replaced_count=replaced_count,
            errors=[],
            dry_run=True,
        )

    # Count what we're about to replace BEFORE wiping.
    replaced_count = len(list_teams())

    # Destructive wipe — teams, players, matches, state (heat counter + timer).
    _wipe_container(get_teams_container)
    _wipe_container(get_players_container)
    _wipe_container(get_container)
    _wipe_container(get_state_container)

    created_teams: list[str] = []
    created_players: list[str] = []

    players_container = get_players_container()
    for team_name, member_names in valid_rows:
        member_player_ids: list[str] = []
        for name in member_names:
            player = Player(name=name)
            players_container.upsert_item(player.model_dump(by_alias=True))
            member_player_ids.append(player.id)
            created_players.append(name)

        # Use the regular create_team path so the dual-write invariant and any
        # future validation applies to bulk imports too.
        team = create_team(TeamCreate(name=team_name, member_ids=member_player_ids))
        created_teams.append(team.name)

    return ImportSummary(
        created_teams=created_teams,
        created_players=created_players,
        skipped=[],
        replaced_count=replaced_count,
        errors=[],
        dry_run=False,
    )
