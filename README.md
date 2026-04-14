# Beer Pong Tournament

A simple web app for tracking beer pong matches at a one-day tournament. Hosted on Azure, designed to be spun up quickly and torn down after the event.

## Architecture

```
┌─────────────┐       ┌──────────────────┐       ┌─────────────────┐
│  Frontend   │──────▶│  Backend API     │──────▶│  Cosmos DB      │
│  (SWA)      │       │  (Container App) │       │  (Serverless)   │
│  HTML/JS/CSS│       │  FastAPI/Python  │       │  NoSQL          │
└─────────────┘       └──────────────────┘       └─────────────────┘
```

**Monorepo layout:**

```
├── backend/         Python 3.12 FastAPI API (uv, basedpyright, pytest, just)
├── frontend/        Vanilla HTML/CSS/JS - 7 tabs (Next Heat, Scoreboard, Register Score, Teams, Matches, Rules, Admin)
├── infra/           Terraform (Azure resources: RG, Cosmos, ACR, Container App, SWA)
└── .github/workflows/
    ├── ci.yml       PR validation (ruff, basedpyright, pytest, terraform fmt + plan)
    ├── deploy.yml   Push-to-main deploy (tf apply -> build/push image -> update container app -> SWA deploy)
    └── destroy.yml  Manual teardown (tf destroy)
```

**Cosmos containers (all partitioned on `/tournamentId`):**

- `matches` - persisted match results
- `teams` - registered teams (`name`, `member_ids: list[str]` referencing `Player.id`)
- `players` - registered players (`name`, `team_id: str | None` back-reference to the team)
- `state` - runtime tournament state (current heat, stored matchups, timer, tables count)

The Team/Player relationship is dual-written: every DAL mutation that changes a team's roster updates both `Team.member_ids` AND `Player.team_id` in one logical operation. A player belongs to at most one team; a team may have 0-3 members. 0-member teams are legal but hidden from all public views (admin-only).

## Features

- **Next Heat** - shows the current heat number, countdown timer, and the generated matchups for this round (with live scores as they come in)
- **Scoreboard** - live leaderboard sorted by wins desc, then total score desc. Team-highlight on the row you just scored for. Ties count as neither a win nor a loss.
- **Register Score** - form to submit match results. Heat is server-locked to the current heat (the client's heat field is ignored on the backend).
- **Teams** - public list of registered teams with their members, plus a "Registered Players" sub-section showing every player alphabetically (by `localeCompare`, Danish-accent friendly). Each row has a local highlight checkbox: clicking a team highlights the team name only; clicking a player highlights both the player AND their team at equal intensity. Mutual-exclusion across team + player checkboxes. Highlight survives page reload via `localStorage` with self-healing (cleared if the cached name is no longer in the roster).
- **Matches** - full match history
- **Rules** - placeholder beer-pong rules (setup, gameplay, re-racks, island, winning, fouls, tournament format)
- **Admin** - PIN-gated panel for:
  - **Team Roster Upload** - upload a CSV on tournament day to replace the roster. Two-step dry-run preview -> Confirm flow. On confirm, wipes teams + players + matches + heat state, then recreates from the CSV. 256 KiB cap. All-or-nothing validation (malformed file -> 400 with per-row errors, upload aborted).
  - Heat management: set/advance heat, start heat timer, "Last heat" prioritisation checkbox
  - Game Settings: configurable match duration (integer minutes) and tables count (integer)
  - Create Team: empty team (name only) — useful for late-arriving teams
  - Add Player: single player (name only) — useful for late walk-ins
  - Manage Teams: list + delete (detaches players, players survive as Unassigned)
  - Manage Players: list with team column, "Assign Team" modal to move a player (including to/from Unassigned), delete
  - Reset: wipe all matches

Automatic team-name normalisation (trim + title-case) prevents duplicates. Same for player names.

## Matchmaking

Round-robin via the circle method:

- **Cycle 1** pairs teams alphabetically (circle-method rotation)
- **Cycle 2+** seeds by current standings (wins, then score)
- If no clean circle-method round fits (every pair unplayed), falls back to greedy pairing of the remaining pairs

The `state` Cosmos container persists the current heat, stored matchups, timer state, and tables count across restarts.

## Local Development

### Backend

```bash
cd backend
just install        # uv sync
just run            # uvicorn on :8000 (auto-reload)
just test           # pytest (64 tests)
just typecheck      # basedpyright (standard mode, not strict)
just lint           # ruff
just check          # lint + typecheck + test
just fmt            # ruff format
```

Copy `.env_example` to `.env` and fill in Cosmos DB values for production-like testing. If you leave them empty, the API auto-falls-back to a local SQLite file (`beerpong_local.db`) via the `SqliteContainer` drop-in - works identically to Cosmos for all API operations.

### Frontend

```bash
cd frontend
# Serve with any static file server, e.g.:
python -m http.server 3000
```

Open `http://localhost:3000`. By default, `config.js` points the API URL to `http://localhost:8000`.

## Deployment

### Prerequisites

1. **Azure subscription** with an App Registration configured for [GitHub Actions OIDC](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust)
2. **Federated credentials** for subjects:
   - `repo:EmilHaldan/BeerPongTournament:ref:refs/heads/main` (deploy)
   - `repo:EmilHaldan/BeerPongTournament:pull_request` (CI plan)
3. **Terraform remote state** storage account (`tfstatebeerpong` by default, configured in `infra/versions.tf`)

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `AZURE_CLIENT_ID` | App registration client ID |
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `ADMIN_TOKEN` | Token for admin API endpoints (doubles as the admin PIN in the frontend) |

### Deploy

Push to `main` or trigger the **Deploy** workflow manually. The workflow:

1. Runs `terraform apply` - provisions RG, Cosmos account + 4 containers (`matches`, `teams`, `players`, `state`), ACR, Log Analytics, Container App Environment + Container App (with user-assigned managed identity for ACR pull), and a Static Web App.
2. Builds and pushes the backend Docker image to ACR.
3. Updates the Container App to the new image via `az containerapp update` (Terraform explicitly `ignore_changes = [image]` so the two don't fight).
4. Writes `config.js` with the backend URL and deploys the frontend to Azure Static Web Apps.

### Teardown

Run the **Destroy Infrastructure** workflow (Actions -> Destroy Infrastructure -> Run workflow). This runs `terraform destroy` and removes all Azure resources.

## API Reference

All admin-protected endpoints require an `X-Admin-Token` header matching the `ADMIN_TOKEN` env var. Non-admin endpoints are public.

### Health

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Health check |

### Matches

| Method | Endpoint | Description |
|---|---|---|
| GET | `/matches` | List all matches (newest first) |
| POST | `/matches` | Register a match result (heat is server-locked to current) |
| DELETE | `/matches/{match_id}` | Delete a match (admin) |

### Leaderboard

| Method | Endpoint | Description |
|---|---|---|
| GET | `/leaderboard` | Leaderboard sorted by wins desc, then total score desc |

### Teams

| Method | Endpoint | Description |
|---|---|---|
| GET | `/teams` | List all registered teams (includes 0-member teams; frontend filters for public views) |
| GET | `/teams/names` | Sorted list of team names (for dropdowns) |
| POST | `/teams` | Create a team (admin). Body: `{name, member_ids: list[str]}` — `member_ids` may be empty |
| DELETE | `/teams/{team_id}` | Delete a team (admin). Detaches attached players (sets their `team_id` to null); players survive |

### Players

| Method | Endpoint | Description |
|---|---|---|
| GET | `/players` | List all registered players |
| POST | `/players` | Create a player (admin). New players are Unassigned (`team_id = null`) |
| DELETE | `/players/{player_id}` | Delete a player (admin). Detaches from their team first (removes the id from the team's `member_ids`) |
| POST | `/players/{player_id}/team` | Move a player to a team (admin). Body: `{team_id: str \| null}`. `null` unassigns |

### Admin roster upload

| Method | Endpoint | Description |
|---|---|---|
| POST | `/admin/teams/upload-csv` | Upload a CSV roster (admin). `multipart/form-data` with `file` field; optional `?dry_run=true` returns the preview without mutating. 256 KiB cap (413 on exceed). Strict all-or-nothing validation (400 with per-row errors on any malformed content). On live run, wipes teams + players + matches + heat/tournament state before creating the new roster |

### Heat

| Method | Endpoint | Description |
|---|---|---|
| GET | `/heat` | Current heat info (number, matchups, timer, tables) |
| POST | `/heat/start-next` | Advance to the next heat (admin) |
| POST | `/heat/set` | Set the heat to a specific value (admin) |
| POST | `/heat/start-timer` | Start the heat countdown timer (admin) |
| POST | `/heat/timer-duration` | Update match duration in seconds (admin) |
| POST | `/heat/tables` | Update the number of tables (admin) |

### Admin

| Method | Endpoint | Description |
|---|---|---|
| POST | `/admin/verify` | Verify the admin token without doing anything |
| POST | `/admin/reset` | Delete all matches (admin) |

## Tournament-day flow

1. Admin logs into the Admin tab with the PIN (`ADMIN_TOKEN` value).
2. Admin uploads the roster CSV (`team_name,member1,member2[,member3]` per row) via **Team Roster Upload**. Click "Upload and preview" for a dry-run; review the preview; click "Confirm replacement" to wipe the DB and materialise the new roster.
3. Late walk-ins: create a new empty team via **Create Team**, add the player(s) via **Add Player**, then use the **Assign Team** modal on Manage Players to link them.
4. Matches get registered via the Register Score tab. Heat is server-locked to the current heat.
5. Heat advances manually via **Setup Next Heat** (optionally with the "Last heat" checkbox to prioritise under-played teams).

Full OpenAPI docs available at `{backend_url}/docs` after deployment.

## Cost

All resources use serverless/free tiers. Estimated cost for a 1-day event: **< $2**.

- Cosmos DB (serverless): pay-per-request, negligible at event scale
- Container App: scale-to-zero, billed only while handling requests
- Static Web App: free tier
- Container Registry (Basic): ~$0.17/day
- Log Analytics: 30-day retention, minimal ingestion
