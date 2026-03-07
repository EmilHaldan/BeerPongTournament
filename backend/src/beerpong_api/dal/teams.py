"""DAL functions for team management."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from beerpong_api.db.client import get_teams_container
from beerpong_api.db.models import Team, TeamCreate


def _normalize_name(name: str) -> str:
    """Normalize a name: strip whitespace and title-case."""
    return name.strip().title()


def create_team(payload: TeamCreate) -> Team:
    """Create and persist a new team."""
    team = Team(
        name=_normalize_name(payload.name),
        members=[_normalize_name(m) for m in payload.members],
    )

    container = get_teams_container()
    doc = team.model_dump(by_alias=True)
    container.upsert_item(doc)
    return team


def list_teams() -> list[Team]:
    """Return all registered teams."""
    container = get_teams_container()
    query = "SELECT * FROM c WHERE c.tournamentId = 'default'"
    items = container.query_items(query=query, enable_cross_partition_query=False)
    return [Team(**item) for item in items]  # type: ignore[reportUnknownArgumentType]


def get_team_names() -> list[str]:
    """Return a sorted list of all team names."""
    teams = list_teams()
    return sorted(t.name for t in teams)


def delete_team(team_id: str) -> bool:
    """Delete a team by ID. Returns True if deleted, False if not found."""
    container = get_teams_container()
    try:
        container.delete_item(item=team_id, partition_key="default")
        return True
    except Exception:
        return False


def _import_teams_from_csv_content(content: str) -> dict[str, list[str]]:
    """Parse CSV content and create teams.

    Expected CSV format (first column is team name, remaining columns are members)::

        team_name,member1,member2
        Alpha,Alice,Bob
        Bravo,Carol,Dave

    Each team must have 2 or 3 members.
    The header row is detected and skipped if present.

    Returns a dict with ``created`` and ``skipped`` team name lists.
    """
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    if not rows:
        return {"created": [], "skipped": []}

    # Skip header row if the first cell looks like a header
    start = 0
    first_cell = rows[0][0].strip().lower().replace("_", "").replace(" ", "")
    if first_cell in {"teamname", "team", "name"}:
        start = 1

    existing = set(get_team_names())
    created: list[str] = []
    skipped: list[str] = []

    for row in rows[start:]:
        # Filter out empty cells
        cells = [c.strip() for c in row if c.strip()]
        if len(cells) < 3:
            continue  # Need at least a team name + 2 members

        team_name = cells[0]
        members = cells[1:]

        # Enforce 2-3 members per team
        if len(members) < 2 or len(members) > 3:
            continue

        normalized = _normalize_name(team_name)

        if normalized in existing:
            skipped.append(normalized)
            continue

        create_team(TeamCreate(name=team_name, members=members))
        existing.add(normalized)
        created.append(normalized)

    return {"created": created, "skipped": skipped}


def load_teams_from_csv(csv_path: str) -> dict[str, list[str]]:
    """Load teams from a CSV file on disk.

    If the file does not exist, returns empty results silently
    (allows the service to start without a CSV).
    """
    path = Path(csv_path)
    if not path.is_file():
        return {"created": [], "skipped": []}

    content = path.read_text(encoding="utf-8")
    return _import_teams_from_csv_content(content)
