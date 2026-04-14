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
├── frontend/        Vanilla HTML/CSS/JS - 7 tabs (Next Heat, Scoreboard, Register Score, Teams, Players, Matches, Rules, Admin)
├── infra/           Terraform (Azure resources: RG, Cosmos, ACR, Container App, SWA)
└── .github/workflows/
    ├── ci.yml       PR validation (ruff, basedpyright, pytest, terraform fmt + plan)
    ├── deploy.yml   Push-to-main deploy (tf apply -> build/push image -> update container app -> SWA deploy)
    └── destroy.yml  Manual teardown (tf destroy)
```

**Cosmos containers (all partitioned on `/tournamentId`):**

- `matches` - persisted match results
- `teams` - registered teams (name + member names)
- `players` - registered players (independent entity; not yet linked to teams)
- `state` - runtime tournament state (current heat, stored matchups, timer, tables count)

## Features

- **Next Heat** - shows the current heat number, countdown timer, and the generated matchups for this round (with live scores as they come in)
- **Scoreboard** - live leaderboard sorted by wins desc, then total score desc. Team-highlight on the row you just scored for. Ties count as neither a win nor a loss.
- **Register Score** - form to submit match results. Heat is server-locked to the current heat (the client's heat field is ignored on the backend).
- **Teams** - public list of registered teams and their members
- **Players** - public list of registered players (independent entity - CRUD lives in the Admin tab)
- **Matches** - full match history
- **Rules** - placeholder beer-pong rules (setup, gameplay, re-racks, island, winning, fouls, tournament format)
- **Admin** - PIN-gated panel for:
  - Heat management: set/advance heat, start heat timer
  - Game Settings: configurable match duration (integer minutes) and tables count (integer)
  - Teams: add, remove
  - Players: add, remove
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
just test           # pytest (50+ tests)
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
| GET | `/teams` | List all registered teams |
| GET | `/teams/names` | Sorted list of team names (for dropdowns) |
| POST | `/teams` | Create a team (admin) |
| DELETE | `/teams/{team_id}` | Delete a team (admin) |

### Players

| Method | Endpoint | Description |
|---|---|---|
| GET | `/players` | List all registered players |
| POST | `/players` | Create a player (admin) |
| DELETE | `/players/{player_id}` | Delete a player (admin) |

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

Full OpenAPI docs available at `{backend_url}/docs` after deployment.

## Cost

All resources use serverless/free tiers. Estimated cost for a 1-day event: **< $2**.

- Cosmos DB (serverless): pay-per-request, negligible at event scale
- Container App: scale-to-zero, billed only while handling requests
- Static Web App: free tier
- Container Registry (Basic): ~$0.17/day
- Log Analytics: 30-day retention, minimal ingestion
