# Beer Pong Tournament

A simple web app for tracking beer pong matches at a one-day tournament. Hosted on Azure, designed to be spun up quickly and torn down after the event.

## Architecture

```
┌─────────────┐       ┌──────────────────┐       ┌─────────────────┐
│  Frontend   │──────▶│  Backend API     │──────▶│  Cosmos DB      │
│  (SWA)      │       │  (Container App) │       │  (Serverless)   │
│  HTML/JS/CSS│       │  FastAPI/Python   │       │  NoSQL          │
└─────────────┘       └──────────────────┘       └─────────────────┘
```

**Monorepo layout:**

```
├── backend/         Python FastAPI API (uv, basedpyright, pytest, just)
├── frontend/        Vanilla HTML/CSS/JS (2 tabs: Scoreboard + Register)
├── infra/           Terraform (Azure resources)
└── .github/workflows/
    ├── ci.yml       PR validation (lint, typecheck, test, tf plan)
    ├── deploy.yml   Push-to-main deploy (tf apply + backend + frontend)
    └── destroy.yml  Manual teardown (tf destroy)
```

## Features

- **Scoreboard** – live leaderboard showing wins, losses, total score per team
- **Register Score** – form to submit match results (team names + scores)
- **Admin Reset** – protected endpoint to clear all data (`POST /admin/reset`)
- Tie handling: ties count as neither win nor loss
- Team name normalization (trim + title-case) prevents duplicates

## Local Development

### Backend

```bash
cd backend
just install        # uv sy nc
just run            # uvicorn on :8000 (auto-reload)
just test           # pytest
just typecheck      # basedpyright
just lint           # ruff
```

Copy `.env_example` to `.env` and fill in Cosmos DB values for full local testing,
or run without them (the API starts but DB calls will fail until configured).

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

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `AZURE_CLIENT_ID` | App registration client ID |
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `ADMIN_TOKEN` | Token for admin API endpoints |

### Deploy

Push to `main` or trigger the **Deploy** workflow manually. The workflow:
1. Runs `terraform apply` (provisions all Azure resources)
2. Builds & pushes the backend Docker image to ACR
3. Updates the Container App to the new image
4. Writes `config.js` with the backend URL and deploys frontend to SWA

### Teardown

Run the **Destroy Infrastructure** workflow (Actions → Destroy Infrastructure → Run workflow). This runs `terraform destroy` and removes all Azure resources.

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/matches` | Register a match result |
| GET | `/leaderboard` | Get leaderboard (sorted by wins, then score) |
| POST | `/admin/reset` | Delete all matches (requires `X-Admin-Token` header) |

Full OpenAPI docs available at `{backend_url}/docs` after deployment.

## Cost

All resources use serverless/free tiers. Estimated cost for a 1-day event: **< $2**.
